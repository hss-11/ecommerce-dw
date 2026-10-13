# -*- coding: utf-8 -*-
"""
dws_reconcile.py — DWS / ADS 对账脚本（W5）

对账分三组，全部通过退出码为 0，任一 FAIL 退出码为 1：
  A 组：DWD 底座基准复核 —— 确认 DWD 未漂移，对账地基有效
  B 组：DWS vs 字典基准 —— GMV(2.1) / 订单量(2.4) / 支付流水(2.2) / 平台实收(2.3)
  C 组：ADS vs DWS/基准 —— 客单价(2.5) / 复购率(3.1) / RFM(3.3) / 留存(3.2)

用法：python etl/transform/dws_reconcile.py
"""
from pathlib import Path
import sys

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DWD = (ROOT / "warehouse" / "duck" / "dwd").as_posix()
DWS = (ROOT / "warehouse" / "duck" / "dws").as_posix()
ADS = (ROOT / "warehouse" / "duck" / "ads").as_posix()

# ---- W4 冻结基准（与 docs/data_dictionary.md 口径一一对应）----
BASE_GMV = 15419773.75          # 2.1 GMV：SUM(item_price+freight_value)，仅 delivered
BASE_ORDERS = 96478             # 2.4 订单量：COUNT(*)，仅 delivered
BASE_PAY_FLOW = 16008872.12     # 2.2 支付流水：SUM(payment_value)，不过滤
BASE_PLATFORM = 15739137.01     # 2.3 平台实收：剔除 canceled/unavailable
BASE_USERS = 96096              # 下单用户数（customer_unique_id 去重）
BASE_REPURCHASE = 2997          # 复购用户数（全周期下单 >= 2 次）
BASE_REPURCHASE_PCT = 3.1188    # 3.1 全周期复购率 %
BASE_PRODUCTS = 32951           # 商品数
BASE_AOV = 159.83               # 2.5 客单价 = GMV / 订单量

con = duckdb.connect()
results = []


def t(base, name):
    return f"read_parquet('{base}/{name}/*/*.parquet', hive_partitioning=true)"


def q1(sql):
    return con.execute(sql).fetchone()[0]


def check(label, actual, expected, tol=0.01):
    try:
        ok = actual is not None and abs(float(actual) - float(expected)) <= tol
    except (TypeError, ValueError):
        ok = actual == expected
    results.append(ok)
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {label:<58} actual={actual}  expected={expected}")


print("=" * 78)
print("A 组：DWD 底座基准复核")
print("=" * 78)
check("A1 DWD GMV（delivered）",
      q1(f"SELECT ROUND(SUM(item_price + freight_value), 2) FROM {t(DWD, 'dwd_fact_order_item')} "
         f"WHERE order_status = 'delivered'"), BASE_GMV)
check("A2 DWD 订单量（delivered）",
      q1(f"SELECT COUNT(*) FROM {t(DWD, 'dwd_fact_delivery')} WHERE order_status = 'delivered'"),
      BASE_ORDERS)
check("A3 DWD 下单用户数（customer_key 去重）",
      q1(f"SELECT COUNT(DISTINCT customer_key) FROM {t(DWD, 'dwd_fact_delivery')}"), BASE_USERS)
check("A4 DWD 支付流水（不过滤）",
      q1(f"SELECT ROUND(SUM(payment_value), 2) FROM {t(DWD, 'dwd_fact_payment')}"), BASE_PAY_FLOW)
check("A5 DWD 平台实收（剔除无效）",
      q1(f"SELECT ROUND(SUM(payment_value), 2) FROM {t(DWD, 'dwd_fact_payment')} "
         f"WHERE order_status NOT IN ('canceled', 'unavailable')"), BASE_PLATFORM)

print("=" * 78)
print("B 组：DWS vs 字典基准")
print("=" * 78)
check("B1  dws_trade_daily SUM(gmv) = 字典 2.1 GMV",
      q1(f"SELECT ROUND(SUM(gmv), 2) FROM {t(DWS, 'dws_trade_daily')}"), BASE_GMV)
check("B2  dws_trade_daily SUM(delivered_order_cnt) = 字典 2.4",
      q1(f"SELECT SUM(delivered_order_cnt) FROM {t(DWS, 'dws_trade_daily')}"), BASE_ORDERS)
check("B3  dws_trade_daily item_amt + freight_amt = gmv（自洽）",
      q1(f"SELECT ROUND(SUM(item_amt + freight_amt) - SUM(gmv), 2) FROM {t(DWS, 'dws_trade_daily')}"), 0)
check("B4  dws_payment_daily SUM(payment_flow) = 字典 2.2",
      q1(f"SELECT ROUND(SUM(payment_flow), 2) FROM {t(DWS, 'dws_payment_daily')}"), BASE_PAY_FLOW)
check("B5  dws_payment_daily SUM(platform_income) = 字典 2.3",
      q1(f"SELECT ROUND(SUM(platform_income), 2) FROM {t(DWS, 'dws_payment_daily')}"), BASE_PLATFORM)
check("B6  dws_payment_daily 流水 - 实收 = 无效支付（自洽）",
      q1(f"SELECT ROUND(SUM(payment_flow) - SUM(platform_income) - SUM(invalid_payment), 2) "
         f"FROM {t(DWS, 'dws_payment_daily')}"), 0)
check("B7  dws_user_summary 行数 = 下单用户数",
      q1(f"SELECT COUNT(*) FROM {t(DWS, 'dws_user_summary')}"), BASE_USERS)
check("B8  dws_user_summary SUM(monetary) = 字典 2.1 GMV",
      q1(f"SELECT ROUND(SUM(monetary), 2) FROM {t(DWS, 'dws_user_summary')}"), BASE_GMV)
check("B9  dws_user_summary SUM(is_repurchase) = 复购用户数",
      q1(f"SELECT SUM(is_repurchase) FROM {t(DWS, 'dws_user_summary')}"), BASE_REPURCHASE)
check("B10 dws_product_summary 行数 = 商品数",
      q1(f"SELECT COUNT(*) FROM {t(DWS, 'dws_product_summary')}"), BASE_PRODUCTS)
check("B11 dws_product_summary SUM(product_gmv) = 字典 2.1 GMV",
      q1(f"SELECT ROUND(SUM(product_gmv), 2) FROM {t(DWS, 'dws_product_summary')}"), BASE_GMV)

print("=" * 78)
print("C 组：ADS vs DWS / 字典基准")
print("=" * 78)
check("C1  ads_trade_daily 行数 = dws_trade_daily 行数",
      q1(f"SELECT COUNT(*) FROM {t(ADS, 'ads_trade_daily')}"),
      q1(f"SELECT COUNT(*) FROM {t(DWS, 'dws_trade_daily')}"), tol=0)
check("C2  ads_trade_daily 全周期客单价 = 字典 2.5（先加再除）",
      q1(f"SELECT ROUND(SUM(gmv) / SUM(delivered_order_cnt), 2) FROM {t(ADS, 'ads_trade_daily')}"),
      BASE_AOV)
check("C3  ads_repurchase 全周期：下单用户数",
      q1(f"SELECT user_cnt FROM {t(ADS, 'ads_repurchase')} WHERE window_type = 'all_period'"),
      BASE_USERS, tol=0)
check("C4  ads_repurchase 全周期：复购用户数",
      q1(f"SELECT repurchase_user_cnt FROM {t(ADS, 'ads_repurchase')} WHERE window_type = 'all_period'"),
      BASE_REPURCHASE, tol=0)
check("C5  ads_repurchase 全周期：复购率 % = 字典 3.1",
      q1(f"SELECT repurchase_pct FROM {t(ADS, 'ads_repurchase')} WHERE window_type = 'all_period'"),
      BASE_REPURCHASE_PCT, tol=0.001)
check("C6  ads_repurchase 90D 月末快照数 = 22（2016-12 起）",
      q1(f"SELECT COUNT(*) FROM {t(ADS, 'ads_repurchase')} WHERE window_type = 'rolling_90d'"), 22, tol=0)
check("C7  ads_rfm_segment 行数 = 下单用户数",
      q1(f"SELECT COUNT(*) FROM {t(ADS, 'ads_rfm_segment')}"), BASE_USERS, tol=0)
check("C8  ads_rfm_segment SUM(monetary) = 字典 2.1 GMV",
      q1(f"SELECT ROUND(SUM(monetary), 2) FROM {t(ADS, 'ads_rfm_segment')}"), BASE_GMV)
check("C9  ads_rfm_segment 分层数 = 8（经典八段全覆盖）",
      q1(f"SELECT COUNT(DISTINCT rfm_segment) FROM {t(ADS, 'ads_rfm_segment')}"), 8, tol=0)
check("C10 ads_retention_cohort N 档 = {{7, 30, 90}}",
      q1(f"SELECT COUNT(DISTINCT n) FROM {t(ADS, 'ads_retention_cohort')}"), 3, tol=0)
check("C11 ads_retention_cohort 无观察期不完整队列（cohort+N <= 数据最大日）",
      q1(f"SELECT COUNT(*) FROM {t(ADS, 'ads_retention_cohort')} "
         f"WHERE cohort_date + CAST(n AS INTEGER) > DATE '2018-10-17'"), 0, tol=0)

print("=" * 78)
passed = sum(results)
total = len(results)
print(f"对账完成：{passed}/{total} 项 PASS")
if passed == total:
    print("全部对账通过，DWS / ADS 与 DWD 基准一致。")
    sys.exit(0)
print(f"存在 {total - passed} 项 FAIL，请检查上方明细。")
sys.exit(1)
