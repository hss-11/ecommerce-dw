"""
环境连通性测试
"""
from pathlib import Path
import duckdb
import polars as pl
import pyarrow as pa

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CSV = str(PROJECT_ROOT / 'data' / 'raw' / 'olist_orders_dataset.csv')


def line(title):
    print("=" * 55)
    print(title)


line("0. 路径确认")
print(f"  项目根目录：{PROJECT_ROOT}")
print(f"  CSV 路径：  {CSV}")
print(f"  文件存在？  {Path(CSV).exists()}")

line("1. 版本检查")
print("  duckdb :", duckdb.__version__)
print("  polars :", pl.__version__)
print("  pyarrow:", pa.__version__)

line("2. DuckDB 无库查询测试")
duckdb.sql("SELECT 42 AS answer, 'OK' AS status").show()

line("3. DuckDB 读取真实 CSV 测试")
duckdb.sql(f"""
    SELECT
        COUNT(*)                    AS row_cnt,
        COUNT(DISTINCT order_id)    AS uniq_orders,
        COUNT(DISTINCT customer_id) AS uniq_customers
    FROM read_csv_auto('{CSV}')
""").show()

line("4. 订单状态分布（GMV 口径决策的依据）")
duckdb.sql(f"""
    SELECT
        order_status,
        COUNT(*) AS cnt,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
    FROM read_csv_auto('{CSV}')
    GROUP BY order_status
    ORDER BY cnt DESC
""").show()

line("5. Polars 读取同一份数据测试")
pl_df = pl.read_csv(CSV)
print(f"  Polars 读到 {pl_df.shape[0]} 行，{pl_df.shape[1]} 列")
print(f"  字段名：{pl_df.columns}")

line("全部通过，环境就绪")
