"""
ads_build.py — W5-S2：ADS 指标层落地（4 张 Parquet，按 dt 分区）

指标与口径（对应 docs/dws_design.md 第 3 节 + docs/data_dictionary.md）：
- ads_trade_daily      日度交易指标：GMV/订单量/客单价 + 7 日均线（下单日口径）
- ads_repurchase       复购率：全周期一行 + 90 天滚动月末快照（字典 3.1）
- ads_retention_cohort N 日留存：cohort × N(7/30/90)，剔除观察期不完整队列（字典 3.2）
- ads_rfm_segment      RFM 分层：R/M 五等分、F 业务阈值，映射经典 8 段（字典 3.3）

口径原则：
- ADS 只放"可直接上报表"的指标；比率全部在此层用"先加再除"现算
- 复购/留存按全状态下单行为（字典 3.1/3.2：衡量再次下单意愿，非成交）
- RFM 的 M 分量仅 delivered（字典 3.3），与 F 的全状态口径不同，文档已声明

DWD 字段注意：dwd_fact_delivery 的下单日是 purchase_date_key（yyyymmdd 智能键），
用户键是 customer_key（= customer_unique_id），本脚本统一用 strptime 转回 DATE。

幂等设计：重复运行前先整体删除该表旧目录再写入。

运行方式（PyCharm 终端，项目根目录）：
    python etl/transform/ads_build.py
预期结果：4 张表全部打印 [OK]，退出码 0
"""
from pathlib import Path
import os
import shutil
import sys

import duckdb

# ---------- 路径自适应 ----------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DWD_DIR = Path(os.environ.get("DWD_DIR", PROJECT_ROOT / "warehouse" / "duck" / "dwd"))
DWS_DIR = Path(os.environ.get("DWS_DIR", PROJECT_ROOT / "warehouse" / "duck" / "dws"))
ADS_DIR = Path(os.environ.get("ADS_DIR", PROJECT_ROOT / "warehouse" / "duck" / "ads"))

SNAPSHOT_DT = "2018-10-18"
DATA_MAX_DATE = "2018-10-17"   # 数据集最大下单日（字典第 1 节）
RFM_ANCHOR = "2018-10-18"      # RFM 锚点 = 最大日期后一天
# 90 天滚动窗口从该月末起算（此前窗口不足 90 天）
ROLLING_90D_MIN_SNAPSHOT = "2016-12-31"

# 智能键 yyyymmdd -> DATE 的转换片段（DWD 的日期列均为智能键）
PURCHASE_DATE = "CAST(strptime(CAST(purchase_date_key AS VARCHAR), '%Y%m%d') AS DATE)"

DWD_VIEWS = {
    "v_fact_delivery": "dwd_fact_delivery",
}
DWS_VIEWS = {
    "v_dws_trade_daily": "dws_trade_daily",
    "v_dws_user_summary": "dws_user_summary",
}

# ---------- ADS 表 SQL ----------

# 1) 日度交易指标 + 7 日均线。客单价 = GMV ÷ 成交订单量（字典 2.5：分子分母均 delivered）。
SQL_ADS_TRADE_DAILY = f"""
SELECT
    date_key,
    full_date,
    order_cnt,
    delivered_order_cnt,
    gmv,
    ROUND(gmv / NULLIF(delivered_order_cnt, 0), 2) AS aov,
    ROUND(AVG(gmv) OVER (
        ORDER BY full_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ), 2) AS gmv_ma7,
    ROUND(AVG(order_cnt) OVER (
        ORDER BY full_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ), 2) AS order_cnt_ma7,
    '{SNAPSHOT_DT}' AS dt
FROM v_dws_trade_daily
"""

# 2) 复购率：一行全周期 + 90 天滚动月末快照（UNION ALL 两种口径同表）。
#    滚动窗口：每个快照日先按人聚合计数，再算复购占比（避免订单行直接计数）。
SQL_ADS_REPURCHASE = f"""
WITH all_orders AS (
    SELECT
        customer_key AS customer_unique_id,
        {PURCHASE_DATE} AS order_date
    FROM v_fact_delivery
),
full_period AS (
    SELECT
        'all_period' AS window_type,
        DATE '{DATA_MAX_DATE}' AS snapshot_date,
        COUNT(*) AS user_cnt,
        SUM(CASE WHEN n >= 2 THEN 1 ELSE 0 END) AS repurchase_user_cnt
    FROM (
        SELECT customer_unique_id, COUNT(*) AS n
        FROM all_orders
        GROUP BY customer_unique_id
    )
),
-- 月末快照日序列：自 2016-12-31（首个满 90 天窗口）至数据最大日所在月
month_ends AS (
    SELECT DISTINCT LAST_DAY(order_date) AS snapshot_date
    FROM all_orders
    WHERE LAST_DAY(order_date) >= DATE '{ROLLING_90D_MIN_SNAPSHOT}'
      AND LAST_DAY(order_date) <= DATE '{DATA_MAX_DATE}'
),
rolling AS (
    SELECT
        'rolling_90d' AS window_type,
        snapshot_date,
        COUNT(*) AS user_cnt,
        SUM(CASE WHEN n >= 2 THEN 1 ELSE 0 END) AS repurchase_user_cnt
    FROM (
        SELECT me.snapshot_date, o.customer_unique_id, COUNT(*) AS n
        FROM month_ends me
        JOIN all_orders o
          ON o.order_date >  me.snapshot_date - INTERVAL 90 DAY
         AND o.order_date <= me.snapshot_date
        GROUP BY me.snapshot_date, o.customer_unique_id
    )
    GROUP BY snapshot_date
)
SELECT
    window_type,
    snapshot_date,
    user_cnt,
    repurchase_user_cnt,
    ROUND(100.0 * repurchase_user_cnt / NULLIF(user_cnt, 0), 4) AS repurchase_pct,
    '{SNAPSHOT_DT}' AS dt
FROM (
    SELECT * FROM full_period
    UNION ALL
    SELECT * FROM rolling
)
"""

# 3) N 日留存 cohort。"第 N 天" = 日历天 D+N 当日有下单（字典 3.2 当日口径）；
#    分母剔除观察期不完整队列（cohort_date + N > 数据最大日）。
SQL_ADS_RETENTION = f"""
WITH first_order AS (
    SELECT
        customer_key AS customer_unique_id,
        MIN({PURCHASE_DATE}) AS cohort_date
    FROM v_fact_delivery
    GROUP BY customer_key
),
orders AS (
    SELECT DISTINCT
        customer_key AS customer_unique_id,
        {PURCHASE_DATE} AS order_date
    FROM v_fact_delivery
),
ns AS (SELECT 7 AS n UNION ALL SELECT 30 UNION ALL SELECT 90)
SELECT
    c.cohort_date,
    ns.n,
    COUNT(*) AS cohort_size,
    SUM(CASE WHEN o.customer_unique_id IS NOT NULL THEN 1 ELSE 0 END) AS retained_cnt,
    ROUND(100.0 * SUM(CASE WHEN o.customer_unique_id IS NOT NULL THEN 1 ELSE 0 END)
          / NULLIF(COUNT(*), 0), 4) AS retention_pct,
    '{SNAPSHOT_DT}' AS dt
FROM first_order c
CROSS JOIN ns
LEFT JOIN orders o
  ON o.customer_unique_id = c.customer_unique_id
 AND o.order_date = c.cohort_date + ns.n
WHERE c.cohort_date + ns.n <= DATE '{DATA_MAX_DATE}'
GROUP BY c.cohort_date, ns.n
"""

# 4) RFM 分层。R/M 用 NTILE(5)（R 越小越高分），F 用业务阈值（96.88% 用户 F=1，分位数塌缩）。
#    三维 >=4 记为"高"，映射经典 8 段。
SQL_ADS_RFM = f"""
WITH scored AS (
    SELECT
        customer_unique_id,
        recency_days,
        order_cnt,
        monetary,
        NTILE(5) OVER (ORDER BY recency_days DESC, customer_unique_id) AS r_score,  -- 间隔越小分越高；决胜字段保证可复现
        NTILE(5) OVER (ORDER BY monetary ASC, customer_unique_id)      AS m_score,  -- 金额越大分越高；决胜字段保证可复现
        CASE
            WHEN order_cnt >= 3 THEN 5
            WHEN order_cnt = 2  THEN 4
            ELSE 2
        END AS f_score  -- F 业务阈值：1->2, 2->4, >=3->5（F=1 占 96.88%）
    FROM v_dws_user_summary
),
labeled AS (
    SELECT
        customer_unique_id,
        recency_days,
        order_cnt,
        monetary,
        r_score,
        f_score,
        m_score,
        (CASE WHEN r_score >= 4 THEN 1 ELSE 0 END) AS r_hi,
        (CASE WHEN f_score >= 4 THEN 1 ELSE 0 END) AS f_hi,
        (CASE WHEN m_score >= 4 THEN 1 ELSE 0 END) AS m_hi
    FROM scored
)
SELECT
    customer_unique_id,
    recency_days,
    order_cnt,
    monetary,
    r_score,
    f_score,
    m_score,
    CASE
        WHEN r_hi=1 AND f_hi=1 AND m_hi=1 THEN '重要价值用户'
        WHEN r_hi=1 AND f_hi=0 AND m_hi=1 THEN '重要发展用户'  -- R高F低：近期来过但频次低，发展频次
        WHEN r_hi=0 AND f_hi=1 AND m_hi=1 THEN '重要保持用户'  -- R低F高：高频但近期没来，唤回保持
        WHEN r_hi=0 AND f_hi=0 AND m_hi=1 THEN '重要挽留用户'
        WHEN r_hi=1 AND f_hi=1 AND m_hi=0 THEN '一般价值用户'
        WHEN r_hi=1 AND f_hi=0 AND m_hi=0 THEN '一般发展用户'
        WHEN r_hi=0 AND f_hi=1 AND m_hi=0 THEN '一般保持用户'
        ELSE '一般挽留用户'
    END AS rfm_segment,
    '{SNAPSHOT_DT}' AS dt
FROM labeled
"""

BUILDS = [
    ("ads_trade_daily", SQL_ADS_TRADE_DAILY),
    ("ads_repurchase", SQL_ADS_REPURCHASE),
    ("ads_retention_cohort", SQL_ADS_RETENTION),
    ("ads_rfm_segment", SQL_ADS_RFM),
]


def build(con: duckdb.DuckDBPyConnection, name: str, select_sql: str) -> None:
    """建一张表：先删旧目录（幂等）→ 建 DuckDB 表 → 按 dt 分区写 Parquet"""
    table_dir = ADS_DIR / name
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
    for d in (DWD_DIR, DWS_DIR):
        if not d.exists():
            print(f"[ERROR] 找不到目录: {d}")
            print("        先运行 dwd_build.py 和 dws_build.py")
            return 1

    con = duckdb.connect()
    for view_name, dwd_table in DWD_VIEWS.items():
        path = (DWD_DIR / dwd_table).as_posix() + "/*/*.parquet"
        con.execute(
            f"CREATE OR REPLACE VIEW {view_name} AS "
            f"SELECT * FROM read_parquet('{path}', hive_partitioning = true)"
        )
    for view_name, dws_table in DWS_VIEWS.items():
        path = (DWS_DIR / dws_table).as_posix() + "/*/*.parquet"
        con.execute(
            f"CREATE OR REPLACE VIEW {view_name} AS "
            f"SELECT * FROM read_parquet('{path}', hive_partitioning = true)"
        )

    print(f"DWD 输入目录: {DWD_DIR}")
    print(f"DWS 输入目录: {DWS_DIR}")
    print(f"ADS 输出目录: {ADS_DIR}")
    print(f"批次日期 dt = {SNAPSHOT_DT}（数据最大日 {DATA_MAX_DATE}，RFM 锚点 {RFM_ANCHOR}）")
    print("-" * 60)

    for name, sql in BUILDS:
        build(con, name, sql)

    con.close()
    print("-" * 60)
    print("ADS 构建完成。下一步运行: python etl/transform/dws_reconcile.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
