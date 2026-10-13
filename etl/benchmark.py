# -*- coding: utf-8 -*-
"""
benchmark.py — SQL 性能调优对照实验（W6）

对 7 个经典调优场景做"朴素写法 vs 调优写法"的对照基准：
  C1 列裁剪        SELECT * vs 只取必要列
  C2 粒度选表      COUNT(DISTINCT) on order_item vs COUNT(*) on delivery（字典 2.4 选表要点）
  C3 先聚合后 join  明细 join 后聚合 vs 先把 payment 聚到订单粒度再 join
  C4 半连接        JOIN + COUNT(DISTINCT) vs WHERE IN 半连接
  C5 窗口函数      相关子查询 vs 窗口函数（7 日移动平均）
  C6 单扫描聚合    3 次扫描 UNION vs 1 次扫描条件聚合
  C7 谓词下推校验   先 join 后过滤 vs 先过滤后 join（验证优化器是否自动下推）

方法论：
  - 每个 SQL 先跑 1 次 warmup（消除 OS 页缓存与首次编译影响），再计时 5 次取中位数
  - 每对 SQL 有结果一致性闸门（gate）：结果必须相等才允许比较耗时
  - 每个 SQL 落盘 EXPLAIN ANALYZE 计划到 docs/benchmark_plans/
  - 结果汇总写 docs/benchmark_plans/results.json

用法：python etl/benchmark.py（任一闸门 FAIL 则退出码 1）
"""
from pathlib import Path
import json
import statistics
import sys
import time

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = (ROOT / "warehouse" / "duck").as_posix()
OUT_DIR = ROOT / "docs" / "benchmark_plans"
RUNS = 5  # warmup 之外的计时次数
TOL = 0.011  # 浮点对账容差（金额保留两位，容差 0.01 + 浮点尾差）

con = duckdb.connect()


def make_view(name, layer, table):
    path = f"{WAREHOUSE}/{layer}/{table}"
    con.execute(
        f"CREATE OR REPLACE VIEW {name} AS "
        f"SELECT * FROM read_parquet('{path}/*/*.parquet', hive_partitioning=true)"
    )


for _name, _layer, _table in [
    ("v_order_item", "dwd", "dwd_fact_order_item"),
    ("v_delivery", "dwd", "dwd_fact_delivery"),
    ("v_payment", "dwd", "dwd_fact_payment"),
    ("v_trade_daily", "dws", "dws_trade_daily"),
]:
    make_view(_name, _layer, _table)


# ---------- 结果一致性闸门 ----------

def _normalize(rows):
    return sorted((tuple(r) for r in rows), key=lambda r: str(r))


def gate_exact(n, t):
    return _normalize(n) == _normalize(t)


def gate_approx(n, t):
    n2, t2 = _normalize(n), _normalize(t)
    if len(n2) != len(t2):
        return False
    for rn, rt in zip(n2, t2):
        if len(rn) != len(rt):
            return False
        for a, b in zip(rn, rt):
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                if abs(float(a) - float(b)) > TOL:
                    return False
            elif a != b:
                return False
    return True


def gate_rowcount(n, t):
    return len(n) == len(t)


def gate_c6(n, t):
    dn = {k: float(v) for k, v in n}
    keys = ["delivered", "canceled", "in_progress"]
    tv = t[0]
    dt = {"delivered": float(tv[0]), "canceled": float(tv[1]), "in_progress": float(tv[2])}
    return all(abs(dn[k] - dt[k]) <= TOL for k in keys)


# ---------- 对照案例 ----------

CASES = [
    {
        "id": "C1_column_pruning",
        "title": "列裁剪：SELECT * vs 只取必要列",
        "naive": "SELECT * FROM v_order_item",
        "tuned": "SELECT order_id, order_status, item_price, freight_value FROM v_order_item",
        "gate": gate_rowcount,
    },
    {
        "id": "C2_right_grain",
        "title": "粒度选表：COUNT(DISTINCT) vs COUNT(*)",
        "naive": "SELECT COUNT(DISTINCT order_id) FROM v_order_item WHERE order_status = 'delivered'",
        "tuned": "SELECT COUNT(*) FROM v_delivery WHERE order_status = 'delivered'",
        "gate": gate_exact,
    },
    {
        "id": "C3_agg_before_join",
        "title": "先聚合后 join：payment 明细直接 join vs 先聚到订单粒度",
        "naive": """
            SELECT d.customer_key, COUNT(DISTINCT d.order_id), SUM(p.payment_value)
            FROM v_delivery d JOIN v_payment p ON d.order_id = p.order_id
            GROUP BY d.customer_key
        """,
        "tuned": """
            WITH pay AS (
                SELECT order_id, SUM(payment_value) AS pay
                FROM v_payment GROUP BY order_id
            )
            SELECT d.customer_key, COUNT(*), SUM(pay.pay)
            FROM v_delivery d JOIN pay ON d.order_id = pay.order_id
            GROUP BY d.customer_key
        """,
        "gate": gate_approx,
    },
    {
        "id": "C4_semi_join",
        "title": "半连接：JOIN + COUNT(DISTINCT) vs WHERE IN",
        "naive": """
            SELECT COUNT(DISTINCT d.order_id)
            FROM v_delivery d JOIN v_payment p ON d.order_id = p.order_id
        """,
        "tuned": """
            SELECT COUNT(*) FROM v_delivery d
            WHERE d.order_id IN (SELECT order_id FROM v_payment)
        """,
        "gate": gate_exact,
    },
    {
        "id": "C5_window_vs_subquery",
        "title": "窗口函数：相关子查询 vs 窗口函数（7 日移动平均，自然日口径）",
        # 注意：trade_daily 有缺日期（616 行 < 730 自然日），两侧统一用"最近 7 个自然日"
        # RANGE 语义才能保证结果一致；ADS 生产代码用的是 ROWS（最近 7 个有成交日），语义不同。
        "naive": """
            SELECT t1.full_date, t1.gmv,
                   (SELECT AVG(t2.gmv) FROM v_trade_daily t2
                    WHERE t2.full_date BETWEEN t1.full_date - 6 AND t1.full_date) AS gmv_ma7
            FROM v_trade_daily t1
        """,
        "tuned": """
            SELECT full_date, gmv,
                   AVG(gmv) OVER (ORDER BY full_date
                                  RANGE BETWEEN INTERVAL 6 DAY PRECEDING AND CURRENT ROW) AS gmv_ma7
            FROM v_trade_daily
        """,
        "gate": gate_approx,
    },
    {
        "id": "C6_cond_agg",
        "title": "单扫描条件聚合 vs 3 次扫描 UNION",
        "naive": """
            SELECT 'delivered' AS k, ROUND(SUM(item_price + freight_value), 2) AS v
            FROM v_order_item WHERE order_status = 'delivered'
            UNION ALL
            SELECT 'canceled', ROUND(SUM(item_price + freight_value), 2)
            FROM v_order_item WHERE order_status = 'canceled'
            UNION ALL
            SELECT 'in_progress', ROUND(SUM(item_price + freight_value), 2)
            FROM v_order_item WHERE order_status NOT IN ('delivered', 'canceled', 'unavailable')
        """,
        "tuned": """
            SELECT
              ROUND(SUM(CASE WHEN order_status = 'delivered' THEN item_price + freight_value END), 2),
              ROUND(SUM(CASE WHEN order_status = 'canceled' THEN item_price + freight_value END), 2),
              ROUND(SUM(CASE WHEN order_status NOT IN ('delivered', 'canceled', 'unavailable')
                             THEN item_price + freight_value END), 2)
            FROM v_order_item
        """,
        "gate": gate_c6,
    },
    {
        "id": "C7_predicate_pushdown",
        "title": "谓词下推校验：先 join 后过滤 vs 先过滤后 join",
        "naive": """
            SELECT SUM(oi.item_price + oi.freight_value)
            FROM v_order_item oi JOIN v_delivery d ON oi.order_id = d.order_id
            WHERE d.order_status = 'delivered'
        """,
        "tuned": """
            SELECT SUM(oi.item_price + oi.freight_value)
            FROM v_order_item oi
            JOIN (SELECT order_id FROM v_delivery WHERE order_status = 'delivered') d
              ON oi.order_id = d.order_id
        """,
        "gate": gate_approx,
    },
]


def timed(sql):
    t0 = time.perf_counter()
    rows = con.execute(sql).fetchall()
    return rows, (time.perf_counter() - t0) * 1000.0


def bench(sql):
    rows, _ = timed(sql)  # warmup，同时取结果用于闸门校验
    samples = []
    for _ in range(RUNS):
        _, ms = timed(sql)
        samples.append(ms)
    return rows, statistics.median(samples), min(samples)


def explain(sql):
    res = con.execute("EXPLAIN ANALYZE " + sql).fetchall()
    return "\n".join(str(r[1]) for r in res)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"仓库目录: {WAREHOUSE}")
    print(f"计划输出: {OUT_DIR}")
    print(f"方法: warmup 1 次 + 计时 {RUNS} 次取中位数（毫秒）")
    print("-" * 78)

    results = []
    all_pass = True
    for case in CASES:
        n_rows, n_med, n_min = bench(case["naive"])
        t_rows, t_med, t_min = bench(case["tuned"])
        ok = case["gate"](n_rows, t_rows)
        all_pass = all_pass and ok

        (OUT_DIR / f"{case['id']}_naive.txt").write_text(
            case["naive"].strip() + "\n\n" + "=" * 60 + "\n" + explain(case["naive"]),
            encoding="utf-8")
        (OUT_DIR / f"{case['id']}_tuned.txt").write_text(
            case["tuned"].strip() + "\n\n" + "=" * 60 + "\n" + explain(case["tuned"]),
            encoding="utf-8")

        speedup = n_med / t_med if t_med > 0 else float("inf")
        results.append({
            "id": case["id"], "title": case["title"],
            "naive_ms": round(n_med, 2), "tuned_ms": round(t_med, 2),
            "naive_min_ms": round(n_min, 2), "tuned_min_ms": round(t_min, 2),
            "speedup": round(speedup, 2), "gate_pass": ok,
        })
        tag = "PASS" if ok else "FAIL"
        print(f"[{tag}] {case['id']:<24} naive {n_med:>9.2f}ms  tuned {t_med:>9.2f}ms  "
              f"加速 {speedup:>7.2f}x  {case['title']}")

    (OUT_DIR / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    print("-" * 78)
    passed = sum(1 for r in results if r["gate_pass"])
    print(f"对账闸门: {passed}/{len(results)} 通过；计划与结果已写入 {OUT_DIR}")
    if not all_pass:
        print("存在结果不一致的闸门，禁止采信该案例的耗时对比。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
