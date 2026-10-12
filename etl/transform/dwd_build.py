"""
dwd_build.py — W4：DWD 明细层构建（5 张维度表 + 4 张事实表）

设计依据：docs/modeling.md（六要素）与 docs/data_dictionary.md（指标口径）
输入：warehouse/duck/ods/（W3 产出，all_varchar 贴源；类型在 DWD 层显式 CAST）
输出：warehouse/duck/dwd/<表名>/dt=2018-10-18/*.parquet（幂等：先删后写，同 W3）

关键实现决策：
1. 类型集中在 DWD 定：ID 一律 VARCHAR、金额 DOUBLE、时间戳 TIMESTAMP、计数与标记 INTEGER
2. dim_seller 为 SCD2 结构。Olist 是静态快照数据，脚本对"订单数最多的卖家"模拟一次
   2018-01-01 生效的城市变更（v1 关闭、v2 生效），事实表按下单日做点对点匹配 join
3. customer_key 一律取 customer_unique_id（自然人）；dim_customer 按 Type 1 思路
   取该自然人最近一次订单的城市（决胜字段 customer_id，保证可重跑结果一致）
4. payment_type 作为低基数描述属性留在支付事实表内（总线矩阵"支付方式"维度的落地，
   不单独建维度表）
5. 所有表带 dt 批次分区列，与 ODS 同批次日期，全量重刷口径
6. ODS 输入目录可用环境变量 ODS_DIR 覆盖（默认 warehouse/duck/ods）。规范目录被
   宿主句柄锁残留占用期间，可临时指向验证目录：
   PowerShell:  $env:ODS_DIR = "warehouse/duck/ods_verify"
   取消覆盖:    Remove-Item Env:ODS_DIR

运行（PyCharm 终端，项目根目录）：
    python etl/transform/dwd_build.py
预期：5 维 + 4 事实共 9 个 [OK]，行数见 docs/progress.md 的 W4 验收口径
"""
from pathlib import Path
import os
import shutil
import sys

import duckdb

# ---------- 路径自适应 + ODS 目录环境变量覆盖 ----------
PROJECT_ROOT = Path(__file__).resolve().parents[2]

_env_ods = os.environ.get("ODS_DIR")
ODS_DIR = Path(_env_ods) if _env_ods else PROJECT_ROOT / "warehouse" / "duck" / "ods"
if not ODS_DIR.is_absolute():
    ODS_DIR = (PROJECT_ROOT / ODS_DIR).resolve()
DWD_DIR = PROJECT_ROOT / "warehouse" / "duck" / "dwd"

SNAPSHOT_DT = "2018-10-18"     # 与 ODS 批次、口径字典锚点一致
DATE_DIM_START = "2016-09-01"  # dim_date 起点（覆盖数据最早月份 2016-09）
DATE_DIM_END = "2018-12-31"    # dim_date 终点（数据到 2018-10-17，留余量防边界丢数）
SCD2_SIM_DATE = "2018-01-01"   # dim_seller 模拟变更生效日

ODS_VIEWS = {
    "v_orders": "ods_orders",
    "v_order_items": "ods_order_items",
    "v_order_payments": "ods_order_payments",
    "v_order_reviews": "ods_order_reviews",
    "v_customers": "ods_customers",
    "v_products": "ods_products",
    "v_sellers": "ods_sellers",
    "v_geolocation": "ods_geolocation",
    "v_cat_trans": "ods_category_translation",
}

# ---------- 维度表 ----------

SQL_DIM_DATE = f"""
SELECT
    CAST(strftime(d, '%Y%m%d') AS INTEGER) AS date_key,
    d                                      AS full_date,
    CAST(year(d) AS INTEGER)               AS year,
    CAST(quarter(d) AS INTEGER)            AS quarter,
    CAST(month(d) AS INTEGER)              AS month,
    strftime(d, '%Y-%m')                   AS year_month,
    CAST(day(d) AS INTEGER)                AS day,
    CAST(weekofyear(d) AS INTEGER)         AS week_of_year,
    CAST(isodow(d) AS INTEGER)             AS day_of_week,
    dayname(d)                             AS day_name,
    isodow(d) >= 6                         AS is_weekend,
    '{SNAPSHOT_DT}'                        AS dt
FROM generate_series(DATE '{DATE_DIM_START}', DATE '{DATE_DIM_END}', INTERVAL 1 DAY) AS t(d)
"""

SQL_DIM_SELLER = f"""
WITH base AS (
    SELECT
        seller_id,
        seller_city,
        seller_state,
        CAST(ROW_NUMBER() OVER (ORDER BY seller_id) AS INTEGER) AS seller_key
    FROM v_sellers
),
target AS (
    -- SCD2 模拟对象：订单数最多的卖家（确定性选择，可重跑结果一致）
    SELECT seller_id
    FROM v_order_items
    GROUP BY seller_id
    ORDER BY COUNT(*) DESC, seller_id
    LIMIT 1
),
unioned AS (
    -- 未变更卖家：单一当前版本
    SELECT
        seller_key, seller_id, seller_city, seller_state,
        DATE '{DATE_DIM_START}' AS effective_start_date,
        CAST(NULL AS DATE)      AS effective_end_date,
        TRUE                    AS is_current
    FROM base
    WHERE seller_id NOT IN (SELECT seller_id FROM target)

    UNION ALL
    -- 目标卖家 v1：{SCD2_SIM_DATE} 起关闭（模拟）
    SELECT
        seller_key, seller_id, seller_city, seller_state,
        DATE '{DATE_DIM_START}',
        DATE '{SCD2_SIM_DATE}',
        FALSE
    FROM base
    WHERE seller_id IN (SELECT seller_id FROM target)

    UNION ALL
    -- 目标卖家 v2：模拟搬迁至新城市（SCD2 工程练手，非真实业务事件）
    SELECT
        CAST((SELECT MAX(seller_key) FROM base) + 1 AS INTEGER),
        seller_id,
        CASE WHEN seller_city <> 'rio de janeiro' THEN 'rio de janeiro' ELSE 'sao paulo' END,
        CASE WHEN seller_city <> 'rio de janeiro' THEN 'RJ' ELSE 'SP' END,
        DATE '{SCD2_SIM_DATE}',
        CAST(NULL AS DATE),
        TRUE
    FROM base
    WHERE seller_id IN (SELECT seller_id FROM target)
)
SELECT *, '{SNAPSHOT_DT}' AS dt FROM unioned
"""

SQL_DIM_CUSTOMER = f"""
SELECT
    customer_unique_id,
    CAST(customer_zip_code_prefix AS INTEGER) AS customer_zip_code_prefix,
    customer_city,
    customer_state,
    '{SNAPSHOT_DT}' AS dt
FROM (
    SELECT
        c.customer_unique_id,
        c.customer_zip_code_prefix,
        c.customer_city,
        c.customer_state,
        ROW_NUMBER() OVER (
            PARTITION BY c.customer_unique_id
            ORDER BY CAST(o.order_purchase_timestamp AS TIMESTAMP) DESC, c.customer_id DESC
        ) AS rn
    FROM v_customers c
    JOIN v_orders o ON c.customer_id = o.customer_id
)
WHERE rn = 1
"""

SQL_DIM_PRODUCT = f"""
SELECT
    p.product_id,
    p.product_category_name,
    CASE
        WHEN p.product_category_name IS NULL OR trim(p.product_category_name) = ''
            THEN 'uncategorized'
        WHEN t.product_category_name_english IS NULL
            THEN 'unknown'
        ELSE t.product_category_name_english
    END AS product_category_name_english,
    CAST(p.product_weight_g AS DOUBLE)    AS product_weight_g,
    CAST(p.product_length_cm AS DOUBLE)   AS product_length_cm,
    CAST(p.product_height_cm AS DOUBLE)   AS product_height_cm,
    CAST(p.product_width_cm AS DOUBLE)    AS product_width_cm,
    CAST(p.product_photos_qty AS INTEGER) AS product_photos_qty,
    '{SNAPSHOT_DT}' AS dt
FROM v_products p
LEFT JOIN v_cat_trans t ON p.product_category_name = t.product_category_name
"""

SQL_DIM_GEOLOCATION = f"""
SELECT
    CAST(geolocation_zip_code_prefix AS INTEGER) AS zip_code_prefix,
    AVG(CAST(geolocation_lat AS DOUBLE))         AS lat,
    AVG(CAST(geolocation_lng AS DOUBLE))         AS lng,
    MIN(geolocation_city)                        AS city,
    MIN(geolocation_state)                       AS state,
    '{SNAPSHOT_DT}' AS dt
FROM v_geolocation
GROUP BY CAST(geolocation_zip_code_prefix AS INTEGER)
"""

# ---------- 事实表 ----------

SQL_FACT_ORDER_ITEM = f"""
SELECT
    oi.order_id,
    CAST(oi.order_item_id AS INTEGER) AS order_item_id,
    CAST(strftime(CAST(o.order_purchase_timestamp AS TIMESTAMP), '%Y%m%d') AS INTEGER) AS date_key,
    c.customer_unique_id AS customer_key,
    oi.product_id AS product_key,
    s.seller_key,
    CAST(c.customer_zip_code_prefix AS INTEGER) AS geo_key,
    CAST(oi.price AS DOUBLE)         AS item_price,
    CAST(oi.freight_value AS DOUBLE) AS freight_value,
    1 AS quantity,
    o.order_status,
    CASE WHEN o.order_status NOT IN ('canceled', 'unavailable') THEN 1 ELSE 0 END AS is_valid_order,
    '{SNAPSHOT_DT}' AS dt
FROM v_order_items oi
JOIN v_orders o    ON oi.order_id = o.order_id
JOIN v_customers c ON o.customer_id = c.customer_id
JOIN dim_seller s  ON oi.seller_id = s.seller_id
                  AND CAST(o.order_purchase_timestamp AS DATE) >= s.effective_start_date
                  AND (s.effective_end_date IS NULL
                       OR CAST(o.order_purchase_timestamp AS DATE) < s.effective_end_date)
"""

SQL_FACT_PAYMENT = f"""
SELECT
    p.order_id,
    CAST(p.payment_sequential AS INTEGER) AS payment_sequential,
    CAST(strftime(CAST(o.order_approved_at AS TIMESTAMP), '%Y%m%d') AS INTEGER) AS date_key,
    c.customer_unique_id AS customer_key,
    p.payment_type,
    CAST(p.payment_installments AS INTEGER) AS payment_installments,
    CAST(p.payment_value AS DOUBLE)         AS payment_value,
    o.order_status,
    CASE WHEN p.payment_type = 'not_defined' THEN 1 ELSE 0 END AS is_not_defined_payment,
    '{SNAPSHOT_DT}' AS dt
FROM v_order_payments p
JOIN v_orders o    ON p.order_id = o.order_id
JOIN v_customers c ON o.customer_id = c.customer_id
"""

SQL_FACT_REVIEW = f"""
SELECT
    r.review_id,
    r.order_id,
    CAST(strftime(CAST(r.review_creation_date AS TIMESTAMP), '%Y%m%d') AS INTEGER) AS date_key,
    c.customer_unique_id AS customer_key,
    CAST(r.review_score AS INTEGER) AS review_score,
    CASE WHEN r.review_comment_message IS NOT NULL
              AND trim(r.review_comment_message) <> '' THEN 1 ELSE 0 END AS has_comment,
    CASE WHEN u.review_id IS NOT NULL THEN 1 ELSE 0 END AS is_review_id_reused,
    '{SNAPSHOT_DT}' AS dt
FROM v_order_reviews r
JOIN v_orders o    ON r.order_id = o.order_id
JOIN v_customers c ON o.customer_id = c.customer_id
LEFT JOIN (
    SELECT review_id
    FROM v_order_reviews
    GROUP BY review_id
    HAVING COUNT(DISTINCT order_id) > 1
) u ON r.review_id = u.review_id
"""

SQL_FACT_DELIVERY = f"""
SELECT
    o.order_id,
    c.customer_unique_id AS customer_key,
    o.order_status,
    CAST(strftime(CAST(o.order_purchase_timestamp AS TIMESTAMP), '%Y%m%d') AS INTEGER)      AS purchase_date_key,
    CAST(strftime(CAST(o.order_delivered_carrier_date AS TIMESTAMP), '%Y%m%d') AS INTEGER)  AS carrier_date_key,
    CAST(strftime(CAST(o.order_delivered_customer_date AS TIMESTAMP), '%Y%m%d') AS INTEGER) AS delivered_date_key,
    CAST(o.order_purchase_timestamp AS TIMESTAMP)      AS order_purchase_timestamp,
    CAST(o.order_approved_at AS TIMESTAMP)             AS order_approved_at,
    CAST(o.order_delivered_carrier_date AS TIMESTAMP)  AS order_delivered_carrier_date,
    CAST(o.order_delivered_customer_date AS TIMESTAMP) AS order_delivered_customer_date,
    CAST(o.order_estimated_delivery_date AS TIMESTAMP)                 AS order_estimated_delivery_ts,
    CAST(CAST(o.order_estimated_delivery_date AS TIMESTAMP) AS DATE)   AS order_estimated_delivery_date,
    date_diff('second', CAST(o.order_purchase_timestamp AS TIMESTAMP),
              CAST(o.order_approved_at AS TIMESTAMP)) / 86400.0             AS days_purchase_to_approve,
    date_diff('second', CAST(o.order_approved_at AS TIMESTAMP),
              CAST(o.order_delivered_carrier_date AS TIMESTAMP)) / 86400.0  AS days_approve_to_carrier,
    date_diff('second', CAST(o.order_delivered_carrier_date AS TIMESTAMP),
              CAST(o.order_delivered_customer_date AS TIMESTAMP)) / 86400.0 AS days_carrier_to_delivered,
    date_diff('second', CAST(o.order_purchase_timestamp AS TIMESTAMP),
              CAST(o.order_delivered_customer_date AS TIMESTAMP)) / 86400.0 AS days_purchase_to_delivered,
    date_diff('second', CAST(o.order_estimated_delivery_date AS TIMESTAMP),
              CAST(o.order_delivered_customer_date AS TIMESTAMP)) / 86400.0 AS days_actual_vs_estimated,
    -- 时间戳级比较（与 W1 探查基准 7,827 延迟单 / 准时率 91.9% 同口径；
    -- 若用日期级比较，同日稍晚送达不算延迟，延迟单会变成 6,535）
    CASE
        WHEN o.order_delivered_customer_date IS NOT NULL
             AND o.order_estimated_delivery_date IS NOT NULL
        THEN CASE
                 WHEN CAST(o.order_delivered_customer_date AS TIMESTAMP)
                   <= CAST(o.order_estimated_delivery_date AS TIMESTAMP)
                 THEN 1 ELSE 0
             END
    END AS is_on_time,
    CASE WHEN pay.order_id IS NULL THEN 1 ELSE 0 END AS is_payment_missing,
    CASE WHEN o.order_status NOT IN ('canceled', 'unavailable') THEN 1 ELSE 0 END AS is_valid_order,
    '{SNAPSHOT_DT}' AS dt
FROM v_orders o
JOIN v_customers c ON o.customer_id = c.customer_id
LEFT JOIN (SELECT DISTINCT order_id FROM v_order_payments) pay ON o.order_id = pay.order_id
"""

BUILDS = [
    ("dim_date", SQL_DIM_DATE),
    ("dim_seller", SQL_DIM_SELLER),          # 必须早于事实表：order_item 的 seller_key 依赖它
    ("dim_customer", SQL_DIM_CUSTOMER),
    ("dim_product", SQL_DIM_PRODUCT),
    ("dim_geolocation", SQL_DIM_GEOLOCATION),
    ("dwd_fact_order_item", SQL_FACT_ORDER_ITEM),
    ("dwd_fact_payment", SQL_FACT_PAYMENT),
    ("dwd_fact_review", SQL_FACT_REVIEW),
    ("dwd_fact_delivery", SQL_FACT_DELIVERY),
]


def build(con: duckdb.DuckDBPyConnection, name: str, select_sql: str) -> None:
    """建一张表：先删旧目录（幂等）→ 建 DuckDB 表 → 按 dt 分区写 Parquet"""
    table_dir = DWD_DIR / name
    if table_dir.exists():
        shutil.rmtree(table_dir)
    table_dir.mkdir(parents=True, exist_ok=True)

    con.execute(f"CREATE OR REPLACE TABLE {name} AS\n{select_sql}")
    con.execute(
        f"COPY (SELECT * FROM {name}) TO '{table_dir.as_posix()}' "
        f"(FORMAT PARQUET, PARTITION_BY (dt))"
    )
    n = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    print(f"[OK] {name:<22} {n:>10,} 行")


def main() -> int:
    if not ODS_DIR.exists():
        print(f"[ERROR] 找不到 ODS 目录: {ODS_DIR}")
        print("        先运行 python etl/extract/ods_load.py，或检查 ODS_DIR 环境变量")
        return 1

    con = duckdb.connect()
    for view_name, ods_table in ODS_VIEWS.items():
        path = (ODS_DIR / ods_table).as_posix() + "/*/*.parquet"
        con.execute(
            f"CREATE OR REPLACE VIEW {view_name} AS "
            f"SELECT * FROM read_parquet('{path}', hive_partitioning = true)"
        )

    print(f"ODS 输入目录: {ODS_DIR}")
    print(f"DWD 输出目录: {DWD_DIR}")
    print(f"批次日期 dt = {SNAPSHOT_DT}（SCD2 模拟变更生效日 {SCD2_SIM_DATE}）")
    print("-" * 60)

    for name, sql in BUILDS:
        build(con, name, sql)

    con.close()
    print("-" * 60)
    print("DWD 构建完成。下一步运行: python etl/transform/dwd_reconcile.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
