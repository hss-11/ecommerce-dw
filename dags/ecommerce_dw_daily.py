# -*- coding: utf-8 -*-
"""
ecommerce_dw_daily.py — ecommerce-dw 离线数仓每日编排（W7）

任务链（对账任务即质量门禁：任一 FAIL 阻断下游并触发重试与告警）：
    ods_load → ods_reconcile → dwd_build → dwd_reconcile
             → dws_build → ads_build → dws_reconcile

W7 四个验收维度在本文件中的落点：
- 幂等：各 ETL 脚本自身"先删后写"（OVERWRITE 语义，见各脚本 docstring），
  整条链任意次数重跑 / 补跑产物一致；DAG 层不再重复实现幂等逻辑
- 重试：default_args retries=2 + retry_delay=5min + 指数退避（上限 30min）
- 回刷：start_date 固定 + catchup=True + max_active_runs=1；本管线是全量重刷，
  回刷 = 按逻辑日期逐个重放同一幂等链路（产物相同，用于演示串行补数）
- 告警：on_failure_callback 追加写 logs/airflow_alerts.log
  （本地无 SMTP 的落地告警；云上把回调体换成邮件 / Webhook 即可，签名不变）

兼容：Airflow 2.10+ / 3.x（schedule 参数与 PythonOperator 路径已按 3.3.2 实测）
"""
from datetime import datetime, timedelta
from pathlib import Path
import subprocess
import sys

from airflow import DAG

try:  # Airflow 3.x 推荐路径
    from airflow.providers.standard.operators.python import PythonOperator
except ImportError:  # Airflow 2.x 兼容
    from airflow.operators.python import PythonOperator

ROOT = Path(__file__).resolve().parents[1]
ALERT_LOG = ROOT / "logs" / "airflow_alerts.log"

# (task_id, 脚本相对路径) —— 列表顺序即依赖链
PIPELINE = [
    ("ods_load", "etl/extract/ods_load.py"),
    ("ods_reconcile", "etl/extract/reconcile.py"),
    ("dwd_build", "etl/transform/dwd_build.py"),
    ("dwd_reconcile", "etl/transform/dwd_reconcile.py"),
    ("dws_build", "etl/transform/dws_build.py"),
    ("ads_build", "etl/transform/ads_build.py"),
    ("dws_reconcile", "etl/transform/dws_reconcile.py"),
]


def run_script(script_rel):
    """以子进程运行一个 ETL 脚本；非零退出码抛异常 → Airflow 标记失败 → 重试 / 告警。"""
    script = ROOT / script_rel
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"{script.name} 退出码 {result.returncode}")


def alert_on_failure(context):
    """任务失败回调：向 logs/airflow_alerts.log 追加一行告警记录。"""
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    logical_date = context.get("logical_date")
    line = (
        f"{datetime.now().isoformat(timespec='seconds')} "
        f"dag={context['dag'].dag_id} "
        f"task={context['task_instance'].task_id} "
        f"logical_date={logical_date.isoformat() if logical_date else 'None'} "
        f"error={context.get('exception')}"
    )
    with ALERT_LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(f"[ALERT] {line}")


default_args = {
    "owner": "ecommerce-dw",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "on_failure_callback": alert_on_failure,
}

with DAG(
    dag_id="ecommerce_dw_daily",
    description="ODS → DWD → DWS → ADS 每日全量编排（对账即质量门禁）",
    default_args=default_args,
    start_date=datetime(2026, 10, 1),
    schedule="@daily",
    catchup=True,
    max_active_runs=1,
    tags=["ecommerce-dw", "w7", "offline"],
) as dag:
    previous = None
    for task_id, script_rel in PIPELINE:
        current = PythonOperator(
            task_id=task_id,
            python_callable=run_script,
            op_kwargs={"script_rel": script_rel},
        )
        if previous is not None:
            previous >> current
        previous = current
