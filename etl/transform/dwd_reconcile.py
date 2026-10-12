"""
dwd_reconcile.py — DWD 明细层对账脚本（W4）

对 dwd_build.py 产出的 9 张 DWD 表执行四类断言：
  ① 行数断言：每张表行数 == 冻结基准值
  ② 指标断言：GMV / 支付流水 / 平台实收 / 无效单支付 / 留评率 / 准时率 / 复购率等 == 冻结基准值
  ③ 结构断言：主键唯一、关键外键无 NULL、SCD2 当前版本数正确、日期维度边界正确
  ④ 口径断言：标记字段计数与 W1 探查基准一致

所有基准值均为 2026-10-12 在沙箱对真实 Olist 数据实测冻结；
任何一项失败都会打印 [FAIL] 并以退出码 1 结束，全部通过才打印 [PASS] 汇总。

运行方式（项目根目录，PyCharm 内置 PowerShell）：
    python etl/transform/dwd_reconcile.py

路径自适应：无论从哪个目录运行，都以本脚本位置反推项目根目录。
"""

import os
import sys
from pathlib import Path

import duckdb

# ---------------- 路径自适应 ----------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DWD_DIR = Path(os.environ.get("DWD_DIR", PROJECT_ROOT / "warehouse" / "duck" / "dwd"))

# ---------------- 冻结基准值（2026-10-12 staging 实测） ----------------
EXPECTED_ROWS = {
    "dim_date": 852,
    "dim_seller": 3096,
    "dim_customer": 96096,
    "dim_product": 32951,
    "dim_geolocation": 19015,
    "dwd_fact_order_item": 112650,
    "dwd_fact_payment": 103886,
    "dwd_fact_review": 99224,
    "dwd_fact_delivery": 99441,
}

GMV = 15419773.75           # 2.1 GMV（delivered，item_price+freight_value）
PAY_ALL = 16008872.12       # 2.2 支付流水（不过滤）
PAY_VALID = 15739137.01     # 2.3 平台实收（剔除 canceled/unavailable）
PAY_INVALID = 269735.11     # 全量无效单支付
DELIVERED_ORDERS = 96478    # 2.4 订单量
LATE_ORDERS = 7827          # is_on_time=0（时间戳级）
ONTIME_ORDERS = 88649       # is_on_time=1
ONTIME_NULL = 2965          # is_on_time IS NULL（delivered缺8 + 进行中/无效）
DELIVERED_TS_NULL = 8       # delivered 缺送达/承诺时间戳
ONTIME_RATE = 91.89         # 4.2 准时交付率 %
PAY_MISSING = 1             # is_payment_missing=1（W1 发现⑬）
NOT_DEFINED_PAY = 3         # is_not_defined_payment=1
REVIEW_REUSED_ROWS = 1603   # is_review_id_reused=1（789 个 review_id 卷入）
REVIEW_DUP_ROWS = 814       # COUNT(*)-COUNT(DISTINCT review_id)
HAS_COMMENT_PCT = 41.29     # 4.4 留评率 %
REPURCHASE_USERS = 2997     # 复购用户（全周期，全部状态）
REPURCHASE_PCT = 3.12       # 3.1 复购率 %（精确值）
SELLER_ROWS = 3096          # dim_seller 总行（含 1 条 SCD2 模拟）
SELLER_CURRENT = 3095       # is_current=true 行数
SCORE_DIST = {1: 11424, 2: 3151, 3: 8179, 4: 19142, 5: 57328}
AVG_DELIVERY_DAYS = 12.56   # 4.3 平均配送时长

# ---------------- 工具 ----------------
con = duckdb.connect()
fails = []


def t(name: str) -> str:
    return f"read_parquet('{DWD_DIR.as_posix()}/{name}/*/*.parquet', hive_partitioning=true)"


def check(label: str, actual, expected, tol: float = 0.0) -> None:
    """比较 actual 与 expected；数值允许 tol 绝对容差。失败记入 fails 并打印。"""
    ok = False
    if tol > 0:
        try:
            ok = abs(float(actual) - float(expected)) <= tol
        except (TypeError, ValueError):
            ok = False
    else:
        ok = actual == expected
    status = "PASS" if ok else "FAIL"
    if not ok:
        fails.append(label)
    print(f"[{status}] {label:<42} 实际={actual}  期望={expected}")


# ================= ① 行数断言 =================
print("=" * 70)
print("① 行数断言")
print("=" * 70)
for name, exp in EXPECTED_ROWS.items():
    try:
        actual = con.execute(f"SELECT COUNT(*) FROM {t(name)}").fetchone()[0]
    except Exception as e:
        print(f"[FAIL] {name:<42} 读取失败: {e}")
        fails.append(f"{name}_rows")
        continue
    check(f"行数 {name}", actual, exp)

# ================= ② 指标断言 =================
print("=" * 70)
print("② 指标断言（金额精确到分，比率保留两位）")
print("=" * 70)
check("GMV（delivered，含运费）",
      con.execute(f"SELECT ROUND(SUM(item_price+freight_value),2) FROM {t('dwd_fact_order_item')} WHERE order_status='delivered'").fetchone()[0],
      GMV, tol=0.01)
check("支付流水（不过滤）",
      con.execute(f"SELECT ROUND(SUM(payment_value),2) FROM {t('dwd_fact_payment')}").fetchone()[0],
      PAY_ALL, tol=0.01)
check("平台实收（剔除无效）",
      con.execute(f"SELECT ROUND(SUM(payment_value),2) FROM {t('dwd_fact_payment')} WHERE order_status NOT IN ('canceled','unavailable')").fetchone()[0],
      PAY_VALID, tol=0.01)
check("全量无效单支付",
      con.execute(f"SELECT ROUND(SUM(payment_value),2) FROM {t('dwd_fact_payment')} WHERE order_status IN ('canceled','unavailable')").fetchone()[0],
      PAY_INVALID, tol=0.01)
check("订单量（delivered）",
      con.execute(f"SELECT COUNT(*) FROM {t('dwd_fact_delivery')} WHERE order_status='delivered'").fetchone()[0],
      DELIVERED_ORDERS)
check("留评率 %",
      con.execute(f"SELECT ROUND(100.0*SUM(has_comment)/COUNT(*),2) FROM {t('dwd_fact_review')}").fetchone()[0],
      HAS_COMMENT_PCT, tol=0.01)
check("准时交付率 %",
      con.execute(f"SELECT ROUND(100.0*SUM(is_on_time)/COUNT(*),2) FROM {t('dwd_fact_delivery')} WHERE is_on_time IS NOT NULL").fetchone()[0],
      ONTIME_RATE, tol=0.01)
check("平均配送时长（天）",
      con.execute(f"SELECT ROUND(AVG(days_purchase_to_delivered),2) FROM {t('dwd_fact_delivery')} WHERE order_status='delivered' AND days_purchase_to_delivered IS NOT NULL").fetchone()[0],
      AVG_DELIVERY_DAYS, tol=0.01)
check("复购率 %（全周期，全部状态）",
      con.execute(f"""WITH c AS (SELECT customer_key, COUNT(*) n FROM {t('dwd_fact_delivery')} GROUP BY 1)
SELECT ROUND(100.0*SUM(CASE WHEN n>=2 THEN 1 ELSE 0 END)/COUNT(*),2) FROM c""").fetchone()[0],
      REPURCHASE_PCT, tol=0.01)

# 评分分布（五档逐一核对）
dist = dict(con.execute(f"SELECT review_score, COUNT(*) FROM {t('dwd_fact_review')} GROUP BY 1").fetchall())
for score, exp in SCORE_DIST.items():
    check(f"评分分布 {score} 分", dist.get(score, 0), exp)

# ================= ③ 结构断言 =================
print("=" * 70)
print("③ 结构断言（主键唯一 / 外键无 NULL / SCD2 / 日期边界）")
print("=" * 70)
# 主键唯一性
check("order_item 主键 (order_id,order_item_id) 重复行",
      con.execute(f"SELECT COUNT(*) FROM (SELECT order_id, order_item_id FROM {t('dwd_fact_order_item')} GROUP BY 1,2 HAVING COUNT(*)>1)").fetchone()[0], 0)
check("payment 主键 (order_id,payment_sequential) 重复行",
      con.execute(f"SELECT COUNT(*) FROM (SELECT order_id, payment_sequential FROM {t('dwd_fact_payment')} GROUP BY 1,2 HAVING COUNT(*)>1)").fetchone()[0], 0)
check("delivery 主键 order_id 重复行",
      con.execute(f"SELECT COUNT(*) FROM (SELECT order_id FROM {t('dwd_fact_delivery')} GROUP BY 1 HAVING COUNT(*)>1)").fetchone()[0], 0)
# 关键外键无 NULL
check("order_item.date_key NULL 数",
      con.execute(f"SELECT COUNT(*) FROM {t('dwd_fact_order_item')} WHERE date_key IS NULL").fetchone()[0], 0)
check("order_item.customer_key NULL 数",
      con.execute(f"SELECT COUNT(*) FROM {t('dwd_fact_order_item')} WHERE customer_key IS NULL").fetchone()[0], 0)
check("order_item.seller_key NULL 数",
      con.execute(f"SELECT COUNT(*) FROM {t('dwd_fact_order_item')} WHERE seller_key IS NULL").fetchone()[0], 0)
check("review.date_key NULL 数",
      con.execute(f"SELECT COUNT(*) FROM {t('dwd_fact_review')} WHERE date_key IS NULL").fetchone()[0], 0)
check("delivery.customer_key NULL 数",
      con.execute(f"SELECT COUNT(*) FROM {t('dwd_fact_delivery')} WHERE customer_key IS NULL").fetchone()[0], 0)
# SCD2 结构
check("dim_seller 总行数", con.execute(f"SELECT COUNT(*) FROM {t('dim_seller')}").fetchone()[0], SELLER_ROWS)
check("dim_seller is_current=true 行数", con.execute(f"SELECT COUNT(*) FROM {t('dim_seller')} WHERE is_current").fetchone()[0], SELLER_CURRENT)
check("dim_seller 自然键 seller_id 去重数", con.execute(f"SELECT COUNT(DISTINCT seller_id) FROM {t('dim_seller')}").fetchone()[0], SELLER_CURRENT)
# 日期维度边界
mn, mx = con.execute(f"SELECT MIN(full_date), MAX(full_date) FROM {t('dim_date')}").fetchone()
check("dim_date 起始日", str(mn)[:10], "2016-09-01")
check("dim_date 结束日", str(mx)[:10], "2018-12-31")

# ================= ④ 口径/标记断言 =================
print("=" * 70)
print("④ 口径/标记断言（W1 探查基准）")
print("=" * 70)
check("延迟订单 is_on_time=0（时间戳级）",
      con.execute(f"SELECT COUNT(*) FROM {t('dwd_fact_delivery')} WHERE is_on_time=0").fetchone()[0], LATE_ORDERS)
check("准时订单 is_on_time=1",
      con.execute(f"SELECT COUNT(*) FROM {t('dwd_fact_delivery')} WHERE is_on_time=1").fetchone()[0], ONTIME_ORDERS)
check("is_on_time IS NULL",
      con.execute(f"SELECT COUNT(*) FROM {t('dwd_fact_delivery')} WHERE is_on_time IS NULL").fetchone()[0], ONTIME_NULL)
check("delivered 缺时间戳",
      con.execute(f"SELECT COUNT(*) FROM {t('dwd_fact_delivery')} WHERE order_status='delivered' AND is_on_time IS NULL").fetchone()[0], DELIVERED_TS_NULL)
check("is_payment_missing=1",
      con.execute(f"SELECT COUNT(*) FROM {t('dwd_fact_delivery')} WHERE is_payment_missing=1").fetchone()[0], PAY_MISSING)
check("is_not_defined_payment=1",
      con.execute(f"SELECT COUNT(*) FROM {t('dwd_fact_payment')} WHERE is_not_defined_payment=1").fetchone()[0], NOT_DEFINED_PAY)
check("is_review_id_reused=1 行数",
      con.execute(f"SELECT COUNT(*) FROM {t('dwd_fact_review')} WHERE is_review_id_reused=1").fetchone()[0], REVIEW_REUSED_ROWS)
check("review 膨胀行数 COUNT-DISTINCT",
      con.execute(f"SELECT COUNT(*)-COUNT(DISTINCT review_id) FROM {t('dwd_fact_review')}").fetchone()[0], REVIEW_DUP_ROWS)

# ================= 汇总 =================
print("=" * 70)
total = len(fails)
if total == 0:
    print("✅ 全部断言通过（DWD 明细层与冻结基准一致）。")
    sys.exit(0)
else:
    print(f"❌ {total} 项断言失败：")
    for f in fails:
        print(f"   - {f}")
    sys.exit(1)
