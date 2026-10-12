"""
ods_load.py — W3-S2：ODS 贴源层落地（9 张 CSV -> Parquet，按 dt 分区）

口径（W3-S1 拍板，方案 A）：
- dt = 数据快照批次日期（= 口径字典锚点 2018-10-18）
- order_items / payments 两张表没有日期列，无法按业务日期分区；
  ODS 层按"同步批次"分区是业界标准做法，业务日期分区留给 DWD 层
- all_varchar：贴源层不做类型转换，原样落地（类型转换是 DWD 层的事）
  好处：ODS 永远忠实于源文件，任何解析歧义都在下游显式处理

幂等设计：
- 重复运行前先整体删除该表旧目录再写入
- 原因：DuckDB 的分区写入是"追加文件"语义，不删目录直接重跑
  会在 dt=xxxx/ 下多出一批 data_1.parquet，数据翻倍

运行方式（PyCharm 终端，项目根目录）：
    python etl/extract/ods_load.py
预期结果：9 张表全部打印 [OK]，退出码 0
"""
from pathlib import Path
import shutil
import sys

import duckdb

# ---------- 路径自适应：以本文件位置反推项目根，任何机器上都能跑 ----------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
ODS_DIR = PROJECT_ROOT / "warehouse" / "duck" / "ods"

# 快照批次日期：与 docs/data_dictionary.md 第 1 节锚点保持一致
SNAPSHOT_DT = "2018-10-18"

# ODS 表名 -> 源 CSV 文件名（改口径、加新表都只动这里）
TABLES = {
    "ods_orders": "olist_orders_dataset.csv",
    "ods_order_items": "olist_order_items_dataset.csv",
    "ods_order_payments": "olist_order_payments_dataset.csv",
    "ods_order_reviews": "olist_order_reviews_dataset.csv",
    "ods_customers": "olist_customers_dataset.csv",
    "ods_products": "olist_products_dataset.csv",
    "ods_sellers": "olist_sellers_dataset.csv",
    "ods_geolocation": "olist_geolocation_dataset.csv",
    "ods_category_translation": "product_category_name_translation.csv",
}


def main() -> int:
    if not RAW_DIR.exists():
        print(f"[ERROR] 找不到原始数据目录: {RAW_DIR}")
        return 1

    con = duckdb.connect()  # 内存模式：只读写 CSV/Parquet，不落 .duckdb 文件
    print(f"快照批次日期 dt = {SNAPSHOT_DT}")
    print(f"原始数据目录: {RAW_DIR}")
    print(f"ODS 输出目录: {ODS_DIR}")
    print("-" * 60)

    for table_name, csv_name in TABLES.items():
        csv_path = RAW_DIR / csv_name
        table_dir = ODS_DIR / table_name

        if not csv_path.exists():
            print(f"[ERROR] 缺文件: {csv_path}")
            return 1

        # 幂等关键：先删后写
        if table_dir.exists():
            shutil.rmtree(table_dir)
        table_dir.mkdir(parents=True, exist_ok=True)

        con.execute(f"""
            COPY (
                SELECT *, '{SNAPSHOT_DT}' AS dt
                FROM read_csv('{csv_path.as_posix()}',
                              header = true,
                              all_varchar = true)
            ) TO '{table_dir.as_posix()}'
            (FORMAT PARQUET, PARTITION_BY (dt))
        """)

        # 写完立刻回读行数（Parquet 元数据查询，几乎不耗时）
        n = con.execute(
            "SELECT COUNT(*) FROM read_parquet("
            f"'{table_dir.as_posix()}/*/*.parquet')"
        ).fetchone()[0]
        print(f"[OK] {table_name:<26} {n:>12,} 行")

    con.close()
    print("-" * 60)
    print("9 张表落地完成。下一步运行: python etl/extract/reconcile.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
