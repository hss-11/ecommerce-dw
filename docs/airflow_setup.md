# Airflow 编排环境搭建与验收指南（W7）

> 版本：v1.0｜日期：2026-10-13
> 对应交付物：dags/ecommerce_dw_daily.py
> 沙箱验证基线：Airflow 3.3.2 + Python 3.12（DagBag 导入零错误，7 任务全链 success）

## 1. 为什么在 WSL2 里跑

- Airflow 官方仅支持 POSIX（Linux / macOS），Win11 原生无法安装运行
- 不用 Docker：Docker Desktop 的 WSL2 后端常驻吃 2-8GB 内存，交接文档已明确排除
- 方案：WSL2 Ubuntu 内直接 pip 安装；用 .wslconfig 限制 WSL2 内存 3GB，守住整机 6GB 预算

## 2. 一次性安装（约 15 分钟）

PowerShell（管理员）：

```powershell
wsl --install -d Ubuntu-24.04    # 默认源即 Python 3.12，与沙箱验证版本一致
```

限制 WSL2 内存——新建文件 `C:\Users\<你的用户名>\.wslconfig`：

```ini
[wsl2]
memory=3GB
```

然后 `wsl --shutdown` 后重新进入 Ubuntu 生效。

Ubuntu 内：

```bash
sudo apt update && sudo apt install -y python3-venv
cd /mnt/d/projects/ecommerce-dw        # 项目根目录（WSL2 里 D 盘挂在 /mnt/d）
python3 -m venv .venv-airflow
source .venv-airflow/bin/activate
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple apache-airflow duckdb polars pyarrow
```

说明：/mnt/d 跨文件系统 IO 比 Linux 原生慢，但数据只有 45MB，无感；项目路径由 DAG 自动解析
（`Path(__file__).resolve().parents[1]`），Windows / WSL2 / Linux 下均无需改代码。

## 3. 初始化与首次验收

```bash
export AIRFLOW_HOME=~/airflow
export AIRFLOW__CORE__DAGS_FOLDER=/mnt/d/projects/ecommerce-dw/dags
export AIRFLOW__CORE__LOAD_EXAMPLES=False

airflow db migrate
airflow dags list | grep ecommerce_dw_daily      # ✓ 应列出该 DAG
airflow dags test ecommerce_dw_daily 2026-10-01  # 全链验收（约 1-2 分钟）
```

全链通过的标志（7 个任务依次 success）：

| 任务 | 通过标志 |
| --- | --- |
| ods_load | 9 张表落地完成 |
| ods_reconcile | 对账结果: 9 张表全部 PASS |
| dwd_build | 5 维 + 4 事实共 9 表构建完成 |
| dwd_reconcile | 全部断言通过（DWD 明细层与冻结基准一致） |
| dws_build | DWS 4 表构建完成 |
| ads_build | ADS 4 表构建完成 |
| dws_reconcile | 对账完成：27/27 项 PASS |

## 4. 四维验收清单（W7 交付标准）

- **幂等**：把 `airflow dags test ecommerce_dw_daily 2026-10-01` 连跑两遍，
  两遍 dws_reconcile 都应 27/27 PASS（各层脚本"先删后写"，重复执行产物一致）。
- **重试 + 告警**：临时把 `data/raw/olist_orders_dataset.csv` 改名，再跑 dags test——
  ods_load 失败 → 自动重试 2 次（5 分钟起步、指数退避）→ 最终失败 →
  `logs/airflow_alerts.log` 追加告警行（该文件在项目根目录 logs/ 下，Windows 侧可直接查看）。
  ⚠️ on_failure_callback 只在**重试全部耗尽后**触发，全程约 15 分钟；
  想快速验证告警落盘，可临时把 DAG 里 retries 改为 0 再测。测完改回 CSV 文件名并重跑一遍恢复。
- **回刷**：`airflow standalone` 启动完整服务（控制台会打印 admin 密码），
  浏览器打开 localhost:8080，把 ecommerce_dw_daily 开关打开——catchup=True 会自动
  补跑 start_date（2026-10-01）以来错过的每个逻辑日，max_active_runs=1 保证串行不打架。
  也可用 `airflow dags test ecommerce_dw_daily <日期>` 逐日手动重放。
- **留证**：UI 的 Graph / Grid 视图截图留一张，是面试讲编排时的直接素材。

## 5. 与生产形态的差异（面试话术）

1. 本地是 45MB 静态数据集的全量重刷；生产是增量分区 + 逻辑日期传参——幂等设计（先删后写）
   与门禁思路（对账即任务）原样迁移。
2. 告警落文件是本地无 SMTP 的落地替代；回调签名不变，云上只把发送体换成邮件 / 企业微信
   Webhook，一行改动。
3. PythonOperator + subprocess 是最简单的可移植形态；生产可换 BashOperator 或容器化
   Operator，任务边界与脚本接口不变。

## 6. 已知边界

- retries=2 + retry_delay=5min + 指数退避（上限 30min）是演示与真实场景兼顾的配置；
  沙箱实测失败任务正确进入 up_for_retry，但 5 分钟起步的等待意味着失败路径验证要预留时间。
- `airflow tasks test` 只单次执行不触发重试，适合逐任务调试；`airflow dags test` 才走完整
  重试 / 回调逻辑，失败路径验收请用后者。
