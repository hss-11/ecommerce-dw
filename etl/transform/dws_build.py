"""
dws_build.py — W5-S1：DWS 汇总层落地（4 张 Parquet，按 dt 分区）

汇总粒度（对应 docs/dws_design.md 第 2 节）：
- dws_trade_daily   粒度 = 下单日           —— GMV/订单量等交易类指标的 DWS 底座
- dws_payment_daily 粒度 = 批准日（代理）   —— 支付流水类指标，与成交类时间口径不同故分表
- dws_user_summary  粒度 = 用户（customer_unique_id）—— 复购/留存/RFM 的用户级底座
- dws_product_summary 粒度 = 商品（product_id）    —— 商品维度排行底座

口径原则：
- 时间口径铁律（字典全局约定）：成交类按下单日、支付类按批准日代理，
  两者时间口径不同，不做同一张日级表的横向对比，故拆成两张日表
- DWS 只存可加度量（金额/单量/次数），不存比率——比率由 ADS 用"先加再除"现算
- 成交口径 = order_status = 'delivered'（与字典 2.1 GMV 一致）

幂等设计：重复运行前先整体删除该表旧目录再写入（同 W3/W4）。

运行方式（PyCharm 终端，项目根目录）：
    python etl/transform/dws_build.py
预期结果：4 张表全部打印 [OK]，退出码 0
"""
from pathlib import Path
import os
import shutil
import sys

import duckdb

# ---------- 路径自适应：以本文件位置反推项目根 ----------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DWD_DIR = Path(os.environ.get("DWD_DIR", PROJECT_ROOT / "warehouse" / "duck" / "dwd"))
DWS_DIR = Path(os.environ.get("DWS_DIR", PROJECT_ROOT / "warehouse" / "duck" / "dws"))

SNAPSHOT_DT = "2018-10-18"
# RFM 锚点：数据集最大日期的后一天（与字典第 1 节时间基准一致），禁用真实当天
RFM_ANCHOR = "2018-10-18"

# DWD 视图注册：视图名 -> dwd 目录名
DWD_VIEWS = {
    "v_fact_order_item": "dwd_fact_order_item",
    "v_fact_payment": "dwd_fact_payment",
    "v_fact_delivery": "dwd_fact_delivery",
    "v_fact_review": "dwd_fact_review",
    "v_dim_product": "dim_product",
}

# ---------- DWS 表 SQL ----------

# 1) 日度交易汇总（按下单日）。
#    gmv/item_amt/freight_amt 均为 delivered 口径，与字典 2.1 对齐——SUM(gmv) 必须能
#    精确对账到全周期 GMV 15,419,773.75；order_cnt 保留全量（含无效/进行中，看下单趋势）；
#    delivered_order_cnt 为字典 2.4 订单量口径。W5 探查确认：无商品明细的 delivered
#    订单为 0 单，故订单数从 order_item 聚合即可精确对账，无需再 join delivery 表。
SQL_DWS_TRADE_DAILY = f"""
WITH item_agg AS (
    SELECT
        date_key,
        -- DWD 的日期是智能键 yyyymmdd，转回 DATE 供报表与窗口函数排序用
        CAST(strptime(CAST(date_key AS VARCHAR), '%Y%m%d') AS DATE) AS full_date,
        COUNT(DISTINCT order_id)                                      AS order_cnt,
        COUNT(DISTINCT CASE WHEN order_status = 'delivered'
                            THEN order_id END)                        AS delivered_order_cnt,
        COUNT(*)                                                      AS item_cnt,
        SUM(CASE WHEN order_status = 'delivered'
                 THEN item_price + freight_value ELSE 0 END)          AS gmv,
        SUM(CASE WHEN order_status = 'delivered'
                 THEN item_price ELSE 0 END)                          AS item_amt,
        SUM(CASE WHEN order_status = 'delivered'
                 THEN freight_value ELSE 0 END)                       AS freight_amt
    FROM v_fact_order_item
    GROUP BY 1, 2
)
SELECT
    date_key,
    full_date,
    order_cnt,
    delivered_order_cnt,
    item_cnt,
    ROUND(gmv, 2)         AS gmv,
    ROUND(item_amt, 2)    AS item_amt,
    ROUND(freight_amt, 2) AS freight_amt,
    '{SNAPSHOT_DT}' AS dt
FROM item_agg
"""

# 2) 日度支付汇总（按批准日代理）。支付流水口径与字典 2.2 一致；含无效单拆分。
SQL_DWS_PAYMENT_DAILY = f"""
WITH pay AS (
    SELECT
        date_key,   -- DWD 支付表 date_key 即批准日代理（yyyymmdd 智能键）
        CAST(strptime(CAST(date_key AS VARCHAR), '%Y%m%d') AS DATE) AS full_date,
        COUNT(DISTINCT order_id)                               AS paid_order_cnt,
        COUNT(*)                                               AS payment_cnt,
        SUM(payment_value)                                     AS payment_flow,
        SUM(CASE WHEN order_status NOT IN ('canceled','unavailable')
                 THEN payment_value ELSE 0 END)                AS platform_income,
        SUM(CASE WHEN order_status IN ('canceled','unavailable')
                 THEN payment_value ELSE 0 END)                AS invalid_payment
    FROM v_fact_payment
    GROUP BY 1, 2
)
SELECT
    date_key,
    full_date,
    paid_order_cnt,
    payment_cnt,
    ROUND(payment_flow, 2)    AS payment_flow,
    ROUND(platform_income, 2) AS platform_income,
    ROUND(invalid_payment, 2) AS invalid_payment,
    '{SNAPSHOT_DT}' AS dt
FROM pay
"""

# 3) 用户汇总（粒度 = customer_unique_id）。
#    F（下单次数）按全状态（含无效/进行中，复购衡量意愿）；M（消费金额）仅 delivered（字典 3.3 口径）。
#    R = 锚点 - 最后下单日；同时产出是否复购标记 is_repurchase（F>=2）。
SQL_DWS_USER_SUMMARY = f"""
WITH orders_per_user AS (
    SELECT
        customer_key                                AS customer_unique_id,
        COUNT(*)                                    AS order_cnt,           -- F
        MAX(CAST(strptime(CAST(purchase_date_key AS VARCHAR), '%Y%m%d') AS DATE)) AS last_order_date,
        MIN(CAST(strptime(CAST(purchase_date_key AS VARCHAR), '%Y%m%d') AS DATE)) AS first_order_date
    FROM v_fact_delivery
    GROUP BY customer_key
),
monetary AS (
    SELECT
        customer_key                                AS customer_unique_id,
        SUM(item_price + freight_value) AS monetary   -- M：仅 delivered 成交口径
    FROM v_fact_order_item
    WHERE order_status = 'delivered'
    GROUP BY customer_key
)
SELECT
    o.customer_unique_id,
    o.order_cnt,
    o.first_order_date,
    o.last_order_date,
    DATE '{RFM_ANCHOR}' - o.last_order_date           AS recency_days,       -- R
    ROUND(COALESCE(m.monetary, 0), 2)                 AS monetary,
    CASE WHEN o.order_cnt >= 2 THEN 1 ELSE 0 END      AS is_repurchase,
    '{SNAPSHOT_DT}' AS dt
FROM orders_per_user o
LEFT JOIN monetary m ON o.customer_unique_id = m.customer_unique_id
"""

# 4) 商品汇总（粒度 = product_id）。商品评分经订单归因（一单多品会重复计数，字典 4.4 局限②）。
SQL_DWS_PRODUCT_SUMMARY = f"""
WITH sales AS (
    SELECT
        product_key                    AS product_id,
        COUNT(*)                       AS sold_item_cnt,
        COUNT(DISTINCT order_id)       AS sold_order_cnt,
        SUM(item_price + freight_value) AS product_gmv,
        SUM(item_price)                AS product_amt,
        SUM(freight_value)             AS product_freight
    FROM v_fact_order_item
    WHERE order_status = 'delivered'
    GROUP BY product_key
),
review_attr AS (
    SELECT
        oi.product_key AS product_id,
        COUNT(*)               AS review_cnt,
        AVG(r.review_score)    AS avg_score
    FROM v_fact_review r
    JOIN v_fact_order_item oi ON r.order_id = oi.order_id
    GROUP BY oi.product_key
)
SELECT
    p.product_id,
    COALESCE(p.product_category_name_english, 'uncategorized') AS category_en,
    p.product_category_name                                    AS category_pt,
    COALESCE(s.sold_item_cnt, 0)              AS sold_item_cnt,
    COALESCE(s.sold_order_cnt, 0)             AS sold_order_cnt,
    ROUND(COALESCE(s.product_gmv, 0), 2)      AS product_gmv,
    ROUND(COALESCE(s.product_amt, 0), 2)      AS product_amt,
    ROUND(COALESCE(s.product_freight, 0), 2)  AS product_freight,
    COALESCE(ra.review_cnt, 0)                AS review_cnt,
    ROUND(ra.avg_score, 4)                    AS avg_score,
    '{SNAPSHOT_DT}' AS dt
FROM v_dim_product p
LEFT JOIN sales s       ON p.product_id = s.product_id
LEFT JOIN review_attr ra ON p.product_id = ra.product_id
"""

BUILDS = [
    ("dws_trade_daily", SQL_DWS_TRADE_DAILY),
    ("dws_payment_daily", SQL_DWS_PAYMENT_DAILY),
    ("dws_user_summary", SQL_DWS_USER_SUMMARY),
    ("dws_product_summary", SQL_DWS_PRODUCT_SUMMARY),
]


def build(con: duckdb.DuckDBPyConnection, name: str, select_sql: str) -> None:
    """建一张表：先删旧目录（幂等）→ 建 DuckDB 表 → 按 dt 分区写 Parquet"""
    table_dir = DWS_DIR / name
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
    if not DWD_DIR.exists():
        print(f"[ERROR] 找不到 DWD 目录: {DWD_DIR}")
        print("        先运行 python etl/transform/dwd_build.py，或检查 DWD_DIR 环境变量")
        return 1

    con = duckdb.connect()
    for view_name, dwd_table in DWD_VIEWS.items():
        path = (DWD_DIR / dwd_table).as_posix() + "/*/*.parquet"
        con.execute(
            f"CREATE OR REPLACE VIEW {view_name} AS "
            f"SELECT * FROM read_parquet('{path}', hive_partitioning = true)"
        )

    print(f"DWD 输入目录: {DWD_DIR}")
    print(f"DWS 输出目录: {DWS_DIR}")
    print(f"批次日期 dt = {SNAPSHOT_DT}（RFM 锚点 {RFM_ANCHOR}）")
    print("-" * 60)

    for name, sql in BUILDS:
        build(con, name, sql)

    con.close()
    print("-" * 60)
    print("DWS 构建完成。下一步运行: python etl/transform/ads_build.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
