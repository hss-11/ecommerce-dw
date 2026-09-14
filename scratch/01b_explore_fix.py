"""
探查补充脚本（修正 + 补查）
背景：01_explore.py 模块8-B 用了 SUM(DISTINCT)，会把金额相同的不同商品行去重，
      导致订单金额被少算、误报 8182 条不匹配。本脚本用 CTE 先聚合再 join 重做。
新增：geolocation 邮编覆盖率、reviews 重复样本查看
"""
from pathlib import Path
import duckdb

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW = PROJECT_ROOT / 'data' / 'raw'

con = duckdb.connect()

TABLES = {
    'orders':      'olist_orders_dataset.csv',
    'order_items': 'olist_order_items_dataset.csv',
    'payments':    'olist_order_payments_dataset.csv',
    'reviews':     'olist_order_reviews_dataset.csv',
    'customers':   'olist_customers_dataset.csv',
    'products':    'olist_products_dataset.csv',
    'geolocation': 'olist_geolocation_dataset.csv',
}
for view_name, file_name in TABLES.items():
    con.sql(f"""
        CREATE OR REPLACE VIEW {view_name} AS
        SELECT * FROM read_csv_auto('{RAW / file_name}')
    """)


def show(title, sql):
    print()
    print("=" * 62)
    print(title)
    print("=" * 62)
    con.sql(sql).show(max_rows=25)


# ---------- 补查 1：修正版金额对账（先聚合再 join）----------
show("补查1：修正版金额对账（对比原版误报的 8182 条）", """
    WITH order_amt AS (
        SELECT order_id, SUM(price + freight_value) AS amt
        FROM order_items
        GROUP BY order_id
    ),
    pay_amt AS (
        SELECT order_id, SUM(payment_value) AS amt
        FROM payments
        GROUP BY order_id
    )
    SELECT
        COUNT(*)                                          AS matched_orders,
        SUM(CASE WHEN ABS(o.amt - p.amt) > 0.01
                 THEN 1 ELSE 0 END)                       AS mismatch_cnt,
        ROUND(SUM(CASE WHEN ABS(o.amt - p.amt) > 0.01
                       THEN 1 ELSE 0 END) * 100.0
              / COUNT(*), 2)                              AS mismatch_pct,
        ROUND(AVG(ABS(o.amt - p.amt)), 2)                 AS avg_diff
    FROM order_amt o
    JOIN pay_amt p USING (order_id)
""")

# ---------- 补查 2：不匹配样本长什么样 ----------
show("补查2：金额不匹配的订单样本（看真实原因）", """
    WITH order_amt AS (
        SELECT order_id, SUM(price + freight_value) AS amt
        FROM order_items GROUP BY order_id
    ),
    pay_amt AS (
        SELECT order_id, SUM(payment_value) AS amt,
               COUNT(*) AS pay_cnt,
               STRING_AGG(DISTINCT payment_type, '+') AS pay_types
        FROM payments GROUP BY order_id
    )
    SELECT o.order_id,
           ROUND(o.amt, 2) AS order_amt,
           ROUND(p.amt, 2) AS pay_amt,
           ROUND(p.amt - o.amt, 2) AS diff,
           p.pay_cnt, p.pay_types
    FROM order_amt o JOIN pay_amt p USING (order_id)
    WHERE ABS(o.amt - p.amt) > 0.01
    ORDER BY ABS(o.amt - p.amt) DESC
    LIMIT 15
""")

# ---------- 补查 3：geolocation 邮编覆盖率 ----------
show("补查3：客户邮编能否在 geolocation 里找到", """
    WITH cust AS (
        SELECT DISTINCT customer_zip_code_prefix AS zip FROM customers
    ),
    geo AS (
        SELECT DISTINCT geolocation_zip_code_prefix AS zip FROM geolocation
    )
    SELECT
        (SELECT COUNT(*) FROM cust)                       AS cust_zip_cnt,
        (SELECT COUNT(*) FROM geo)                        AS geo_zip_cnt,
        (SELECT COUNT(*) FROM cust JOIN geo USING (zip))  AS matched_cnt,
        ROUND((SELECT COUNT(*) FROM cust JOIN geo USING (zip)) * 100.0
              / (SELECT COUNT(*) FROM cust), 2)           AS coverage_pct
""")

# ---------- 补查 4：reviews 重复样本 ----------
show("补查4：review_id 重复的样本（确认去重策略）", """
    SELECT review_id, COUNT(*) AS dup_cnt
    FROM reviews
    GROUP BY review_id
    HAVING COUNT(*) > 1
    ORDER BY dup_cnt DESC
    LIMIT 10
""")

show("补查5：某个重复 review_id 的完整记录对比", """
    WITH dup AS (
        SELECT review_id FROM reviews
        GROUP BY review_id HAVING COUNT(*) > 1 LIMIT 1
    )
    SELECT r.review_id, r.order_id, r.review_score,
           r.review_creation_date, r.review_answer_timestamp
    FROM reviews r JOIN dup USING (review_id)
""")

# ---------- 补查 6：products 类目覆盖情况 ----------
show("补查6：商品类目覆盖与翻译缺失", """
    SELECT
        COUNT(DISTINCT product_category_name)                        AS total_categories,
        COUNT(DISTINCT t.product_category_name_english)              AS translated_cnt,
        SUM(CASE WHEN p.product_category_name IS NULL THEN 1 ELSE 0 END) AS null_category_rows
    FROM products p
    LEFT JOIN read_csv_auto('""" + str(RAW / 'product_category_name_translation.csv') + """') t
           USING (product_category_name)
""")

# ---------- 补查 7：无支付记录的订单是什么状态 ----------
show("补查7：776 个无支付订单的状态分布", """
    SELECT o.order_status, COUNT(*) AS cnt
    FROM orders o
    LEFT JOIN payments p USING (order_id)
    WHERE p.order_id IS NULL
    GROUP BY o.order_status
    ORDER BY cnt DESC
""")

# ---------- 补查 8：金额差异比例分布（判断是否为分期利息）----------
show("补查8：pay 与 order 金额差异比例（验证分期利息假设）", """
    WITH order_amt AS (
        SELECT order_id, SUM(price + freight_value) AS amt
        FROM order_items GROUP BY order_id
    ),
    pay_amt AS (
        SELECT order_id, SUM(payment_value) AS amt,
               MAX(payment_installments) AS installments
        FROM payments GROUP BY order_id
    )
    SELECT
        CASE WHEN ABS(o.amt - p.amt) <= 0.01 THEN '0_完全一致'
             WHEN ABS(p.amt - o.amt) / o.amt < 0.05 THEN '1_差异<5%'
             WHEN ABS(p.amt - o.amt) / o.amt < 0.20 THEN '2_差异5-20%'
             ELSE '3_差异>20%' END          AS diff_bucket,
        COUNT(*)                            AS order_cnt,
        ROUND(AVG(p.installments), 2)       AS avg_installments
    FROM order_amt o JOIN pay_amt p USING (order_id)
    GROUP BY 1 ORDER BY 1
""")


# ---------- 补查 9：有支付但无商品明细的 776 个订单 ----------
show("补查9：无商品明细订单的状态分布（真·776 之谜）", """
    SELECT o.order_status, COUNT(*) AS cnt,
           ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
    FROM orders o
    LEFT JOIN order_items oi USING (order_id)
    WHERE oi.order_id IS NULL
    GROUP BY o.order_status
    ORDER BY cnt DESC
""")

show("补查10：这 776 个订单的支付金额（钱到底收了多少）", """
    WITH no_items AS (
        SELECT o.order_id
        FROM orders o LEFT JOIN order_items oi USING (order_id)
        WHERE oi.order_id IS NULL
    )
    SELECT COUNT(DISTINCT n.order_id)      AS order_cnt,
           COUNT(*)                        AS payment_cnt,
           ROUND(SUM(p.payment_value), 2)  AS total_paid
    FROM no_items n JOIN payments p USING (order_id)
""")

show("补查11：反向检查——有商品明细但无支付的订单", """
    SELECT COUNT(DISTINCT oi.order_id) AS cnt
    FROM order_items oi
    LEFT JOIN payments p USING (order_id)
    WHERE p.order_id IS NULL
""")



print()
print("=" * 62)
print("补查完成。请把结果补进 exploration_notes.md 第五节")
print("=" * 62)
