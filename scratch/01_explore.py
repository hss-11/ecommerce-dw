"""
Olist 数据集探查脚本
目的：摸清 9 张表的行数、主键、空值、关联完整性、时间范围、数据质量问题
产出：docs/exploration_notes.md 的原始素材
"""
from pathlib import Path
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW = PROJECT_ROOT / 'data' / 'raw'

con = duckdb.connect()          # 不传路径 = 纯内存库，探查阶段够用

# 把 9 个 CSV 注册成视图，之后就能像查表一样查它们
TABLES = {
    'orders':       'olist_orders_dataset.csv',
    'order_items':  'olist_order_items_dataset.csv',
    'payments':     'olist_order_payments_dataset.csv',
    'reviews':      'olist_order_reviews_dataset.csv',
    'customers':    'olist_customers_dataset.csv',
    'products':     'olist_products_dataset.csv',
    'sellers':      'olist_sellers_dataset.csv',
    'geolocation':  'olist_geolocation_dataset.csv',
    'cat_trans':    'product_category_name_translation.csv',
}

for view_name, file_name in TABLES.items():
    con.sql(f"""
        CREATE OR REPLACE VIEW {view_name} AS
        SELECT * FROM read_csv_auto('{RAW / file_name}')
    """)


def show(title, sql):
    """执行 SQL 并打印标题 + 结果表格"""
    print()
    print("=" * 62)
    print(title)
    print("=" * 62)
    con.sql(sql).show(max_rows=25)


# ---------- 模块 1：每张表的行数 ----------
show("模块1：9 张表的行数概览", """
    SELECT 'orders'      AS tbl, COUNT(*) AS row_cnt FROM orders
    UNION ALL SELECT 'order_items',  COUNT(*) FROM order_items
    UNION ALL SELECT 'payments',     COUNT(*) FROM payments
    UNION ALL SELECT 'reviews',      COUNT(*) FROM reviews
    UNION ALL SELECT 'customers',    COUNT(*) FROM customers
    UNION ALL SELECT 'products',     COUNT(*) FROM products
    UNION ALL SELECT 'sellers',      COUNT(*) FROM sellers
    UNION ALL SELECT 'geolocation',  COUNT(*) FROM geolocation
    UNION ALL SELECT 'cat_trans',    COUNT(*) FROM cat_trans
    ORDER BY row_cnt DESC
""")

# ---------- 模块 2：主键唯一性检查 ----------
show("模块2：主键唯一性（total 应等于 uniq，否则有重复）", """
    SELECT 'orders: order_id' AS pk_check,
           COUNT(*) AS total, COUNT(DISTINCT order_id) AS uniq
    FROM orders
    UNION ALL
    SELECT 'order_items: order_id+item_id',
           COUNT(*), COUNT(DISTINCT (order_id, order_item_id))
    FROM order_items
    UNION ALL
    SELECT 'payments: order_id+seq',
           COUNT(*), COUNT(DISTINCT (order_id, payment_sequential))
    FROM payments
    UNION ALL
    SELECT 'reviews: review_id',
           COUNT(*), COUNT(DISTINCT review_id)
    FROM reviews
    UNION ALL
    SELECT 'customers: customer_id',
           COUNT(*), COUNT(DISTINCT customer_id)
    FROM customers
    UNION ALL
    SELECT 'products: product_id',
           COUNT(*), COUNT(DISTINCT product_id)
    FROM products
    UNION ALL
    SELECT 'sellers: seller_id',
           COUNT(*), COUNT(DISTINCT seller_id)
    FROM sellers
""")

# ---------- 模块 3：客户 ID 的双重身份 ----------
show("模块3：customer_id vs customer_unique_id（复购率口径关键）", """
    SELECT
        COUNT(*)                        AS total_rows,
        COUNT(DISTINCT customer_id)     AS uniq_customer_id,
        COUNT(DISTINCT customer_unique_id) AS uniq_real_person,
        ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT customer_unique_id), 4)
                                        AS orders_per_person
    FROM customers
""")

# ---------- 模块 4：一单多品程度（决定事实表粒度）----------
show("模块4：每个订单包含几个商品项", """
    SELECT items_per_order, COUNT(*) AS order_cnt
    FROM (
        SELECT order_id, COUNT(*) AS items_per_order
        FROM order_items GROUP BY order_id
    )
    GROUP BY items_per_order
    ORDER BY items_per_order
""")

# ---------- 模块 5：关联完整性（找孤儿记录）----------
show("模块5：孤儿记录检查（数字应为 0，不为 0 就是数据问题）", """
    SELECT 'order_items 找不到 orders' AS check_name, COUNT(*) AS orphan_cnt
    FROM order_items oi LEFT JOIN orders o USING (order_id)
    WHERE o.order_id IS NULL
    UNION ALL
    SELECT 'payments 找不到 orders', COUNT(*)
    FROM payments p LEFT JOIN orders o USING (order_id)
    WHERE o.order_id IS NULL
    UNION ALL
    SELECT 'order_items 找不到 products', COUNT(*)
    FROM order_items oi LEFT JOIN products p USING (product_id)
    WHERE p.product_id IS NULL
    UNION ALL
    SELECT 'order_items 找不到 sellers', COUNT(*)
    FROM order_items oi LEFT JOIN sellers s USING (seller_id)
    WHERE s.seller_id IS NULL
    UNION ALL
    SELECT 'orders 找不到 customers', COUNT(*)
    FROM orders o LEFT JOIN customers c USING (customer_id)
    WHERE c.customer_id IS NULL
    UNION ALL
    SELECT 'products 类目找不到翻译', COUNT(*)
    FROM products p LEFT JOIN cat_trans t USING (product_category_name)
    WHERE p.product_category_name IS NOT NULL
      AND t.product_category_name_english IS NULL
""")

# ---------- 模块 6：geolocation 的一对多问题 ----------
show("模块6：geolocation 邮编重复度（join 膨胀风险）", """
    SELECT
        COUNT(*)                                   AS total_rows,
        COUNT(DISTINCT geolocation_zip_code_prefix) AS uniq_zip,
        ROUND(COUNT(*) * 1.0
              / COUNT(DISTINCT geolocation_zip_code_prefix), 2) AS rows_per_zip,
        MAX(zip_cnt)                               AS max_rows_for_one_zip
    FROM geolocation
    JOIN (SELECT geolocation_zip_code_prefix AS z, COUNT(*) AS zip_cnt
          FROM geolocation GROUP BY 1) t
      ON geolocation.geolocation_zip_code_prefix = t.z
""")

# ---------- 模块 7：空值率 ----------
show("模块7：关键字段空值统计", """
    SELECT 'orders.order_status' AS field,
           COUNT(*) - COUNT(order_status) AS null_cnt, COUNT(*) AS total
    FROM orders
    UNION ALL
    SELECT 'orders.order_delivered_customer_date',
           COUNT(*) - COUNT(order_delivered_customer_date), COUNT(*)
    FROM orders
    UNION ALL
    SELECT 'order_items.price',
           COUNT(*) - COUNT(price), COUNT(*) FROM order_items
    UNION ALL
    SELECT 'payments.payment_value',
           COUNT(*) - COUNT(payment_value), COUNT(*) FROM payments
    UNION ALL
    SELECT 'products.product_category_name',
           COUNT(*) - COUNT(product_category_name), COUNT(*) FROM products
    UNION ALL
    SELECT 'reviews.review_score',
           COUNT(*) - COUNT(review_score), COUNT(*) FROM reviews
    UNION ALL
    SELECT 'reviews.review_comment_message',
           COUNT(*) - COUNT(review_comment_message), COUNT(*) FROM reviews
""")

# ---------- 模块 8：时间范围与业务合理性 ----------
show("模块8-A：时间范围（决定日期维度边界）", """
    SELECT
        MIN(order_purchase_timestamp)::DATE AS min_date,
        MAX(order_purchase_timestamp)::DATE AS max_date,
        COUNT(DISTINCT order_purchase_timestamp::DATE) AS active_days
    FROM orders
""")

show("模块8-B：业务合理性检查（异常数据）", """
    SELECT '负价格或负运费' AS issue, COUNT(*) AS cnt FROM order_items
    WHERE price < 0 OR freight_value < 0
    UNION ALL
    SELECT '价格为 0', COUNT(*) FROM order_items WHERE price = 0
    UNION ALL
    SELECT '送达时间早于下单时间', COUNT(*)
    FROM orders
    WHERE order_delivered_customer_date < order_purchase_timestamp
    UNION ALL
    SELECT '实际送达晚于承诺送达', COUNT(*)
    FROM orders
    WHERE order_delivered_customer_date > order_estimated_delivery_date
    UNION ALL
    SELECT '支付金额与订单金额不符', COUNT(*) FROM (
        SELECT o.order_id,
               SUM(DISTINCT oi.price + oi.freight_value) AS order_amt,
               SUM(DISTINCT p.payment_value)             AS pay_amt
        FROM orders o
        JOIN order_items oi USING (order_id)
        JOIN payments p     USING (order_id)
        GROUP BY o.order_id
    ) WHERE ABS(order_amt - pay_amt) > 0.01
""")

show("模块8-C：支付方式与分期分布", """
    SELECT payment_type,
           COUNT(*) AS cnt,
           ROUND(AVG(payment_installments), 2) AS avg_installments,
           ROUND(SUM(payment_value), 2)        AS total_value
    FROM payments GROUP BY payment_type ORDER BY cnt DESC
""")

show("模块8-D：评分分布", """
    SELECT review_score, COUNT(*) AS cnt,
           ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
    FROM reviews GROUP BY review_score ORDER BY review_score
""")

print()
print("=" * 62)
print("探查完成。请把每段结果整理进 docs/exploration_notes.md")
print("=" * 62)
