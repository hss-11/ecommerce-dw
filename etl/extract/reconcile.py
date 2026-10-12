"""
reconcile.py — W3-S3：ODS 对账脚本（加载的验收闸门）

对账三指标（CSV 侧 vs Parquet 侧，逐表核对）：
1. 行数            —— 落地有没有丢行/多行
2. 主键去重数       —— 主键唯一性是否在两侧一致（geolocation 无业务主键，跳过）
3. 金额 SUM        —— order_items 的 price/freight_value、payments 的 payment_value，
                     两侧各保留 2 位小数后比较，容差 0.01（浮点求和顺序差异）

另设"预期行数"基准（Olist 官方数据规模，W1 探查已确认）：
- 两侧一致但都与预期不符 -> 说明源 CSV 本身有问题，同样 FAIL
- 这是"第三方基准交叉验证"，防止"错得一致"的假象

退出码约定（W7 Airflow 编排会直接利用）：
- 全部 PASS -> 退出码 0
- 任一 FAIL -> 退出码 1，并打印差异清单

运行方式（PyCharm 终端，项目根目录）：
    python etl/extract/reconcile.py
"""
from pathlib import Path
import sys

import duckdb

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
ODS_DIR = PROJECT_ROOT / "warehouse" / "duck" / "ods"

# 逐表对账配置：主键列 / 金额列 / 预期行数
CHECKS = {
    "ods_orders": {
        "csv": "olist_orders_dataset.csv",
        "pk": ["order_id"],
        "sums": [],
        "expected_rows": 99_441,
    },
    "ods_order_items": {
        "csv": "olist_order_items_dataset.csv",
        "pk": ["order_id", "order_item_id"],
        "sums": ["price", "freight_value"],
        "expected_rows": 112_650,
    },
    "ods_order_payments": {
        "csv": "olist_order_payments_dataset.csv",
        "pk": ["order_id", "payment_sequential"],
        "sums": ["payment_value"],
        "expected_rows": 103_886,
    },
    "ods_order_reviews": {
        "csv": "olist_order_reviews_dataset.csv",
        # W1 决策：组合主键 (review_id, order_id)，不去重
        "pk": ["review_id", "order_id"],
        "sums": [],
        "expected_rows": 99_224,
    },
    "ods_customers": {
        "csv": "olist_customers_dataset.csv",
        "pk": ["customer_id"],
        "sums": [],
        "expected_rows": 99_441,
    },
    "ods_products": {
        "csv": "olist_products_dataset.csv",
        "pk": ["product_id"],
        "sums": [],
        "expected_rows": 32_951,
    },
    "ods_sellers": {
        "csv": "olist_sellers_dataset.csv",
        "pk": ["seller_id"],
        "sums": [],
        "expected_rows": 3_095,
    },
    "ods_geolocation": {
        "csv": "olist_geolocation_dataset.csv",
        "pk": [],  # 无业务主键（同邮编多行经纬度），只对行数
        "sums": [],
        "expected_rows": 1_000_163,
    },
    "ods_category_translation": {
        "csv": "product_category_name_translation.csv",
        "pk": ["product_category_name"],
        "sums": [],
        "expected_rows": 71,
    },
}


def stats_sql(source: str, pk: list[str], sums: list[str]) -> str:
    """生成单侧统计 SQL：行数 + 主键去重数 + 各金额列合计（保留 2 位小数）"""
    ctes = [f"src AS (SELECT * FROM {source})"]
    cols = ["(SELECT COUNT(*) FROM src) AS row_count"]
    if pk:
        ctes.append(f"pk AS (SELECT DISTINCT {', '.join(pk)} FROM src)")
        cols.append("(SELECT COUNT(*) FROM pk) AS pk_distinct_count")
    for col in sums:
        cols.append(
            f"(SELECT ROUND(SUM(CAST({col} AS DOUBLE)), 2) FROM src) AS sum_{col}"
        )
    return f"WITH {', '.join(ctes)} SELECT {', '.join(cols)}"


def main() -> int:
    con = duckdb.connect()
    all_pass = True

    print("ODS 对账开始（CSV vs Parquet）")
    print("=" * 60)

    for table, cfg in CHECKS.items():
        csv_src = (
            f"read_csv('{(RAW_DIR / cfg['csv']).as_posix()}', "
            f"header = true, all_varchar = true)"
        )
        pq_src = (
            f"read_parquet('{(ODS_DIR / table).as_posix()}/*/*.parquet', "
            f"hive_partitioning = true)"
        )

        parquet_dir = ODS_DIR / table
        if not parquet_dir.exists():
            print(f"[FAIL] {table}: 目录不存在 {parquet_dir}（先跑 ods_load.py）")
            all_pass = False
            continue

        sql = stats_sql(csv_src, cfg["pk"], cfg["sums"])
        csv_stats = con.execute(sql).fetchone()
        pq_stats = con.execute(stats_sql(pq_src, cfg["pk"], cfg["sums"])).fetchone()

        problems = []

        # 指标 1：行数（两侧互比 + 与预期基准比）
        csv_rows, pq_rows = csv_stats[0], pq_stats[0]
        if csv_rows != pq_rows:
            problems.append(f"行数不一致: CSV={csv_rows:,} Parquet={pq_rows:,}")
        if csv_rows != cfg["expected_rows"]:
            problems.append(
                f"行数与预期不符: CSV={csv_rows:,} 预期={cfg['expected_rows']:,}"
            )

        # 指标 2、3 按列位置依次取（row_count, [pk_distinct], [sum1, sum2...]）
        idx = 1
        if cfg["pk"]:
            if csv_stats[idx] != pq_stats[idx]:
                problems.append(
                    f"主键去重数不一致: CSV={csv_stats[idx]:,} "
                    f"Parquet={pq_stats[idx]:,}"
                )
            idx += 1
        for col in cfg["sums"]:
            a, b = csv_stats[idx], pq_stats[idx]
            if abs(a - b) > 0.01:
                problems.append(f"{col} 金额不一致: CSV={a:,.2f} Parquet={b:,.2f}")
            idx += 1

        if problems:
            all_pass = False
            print(f"[FAIL] {table}")
            for p in problems:
                print(f"       - {p}")
        else:
            print(
                f"[PASS] {table:<26} 行数 {csv_rows:>10,} "
                f"(与 Parquet、预期基准三方一致)"
            )

    con.close()
    print("=" * 60)
    if all_pass:
        print("对账结果: 9 张表全部 PASS，ODS 层与源数据一致，可以进入 DWD")
        return 0
    print("对账结果: 存在 FAIL，请先排查修复，不要带错进入 DWD")
    return 1


if __name__ == "__main__":
    sys.exit(main())
