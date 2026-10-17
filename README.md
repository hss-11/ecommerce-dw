# E-Commerce Data Warehouse

端到端电商数据仓库项目：基于 Olist 巴西电商公开数据集，实现 ODS → DWD → DWS → ADS 四层数仓建模，
使用 DuckDB + Polars 做离线加工，Airflow 做任务编排，Great Expectations 做数据质量校验，Streamlit 做指标可视化。

## 技术栈

| 状态 | 组件 |
|---|---|
| 已落地 | Python 3.11 · DuckDB 1.5.5 · Polars 1.44.2 · PyArrow 25.0.1 · Airflow 3.3.2（WSL2，W7） · Git |
| 计划中 | Great Expectations + Streamlit（W8）· Spark / Kafka / Flink（W9，云上） |

## 项目进度

- [x] W1 数据探查与环境搭建
- [x] W2 维度建模设计
- [x] W3 ODS 贴源层
- [x] W4 DWD 明细层
- [x] W5 DWS 汇总层 + ADS 指标层
- [x] W6 SQL 性能调优
- [x] W7 Airflow 任务编排
- [ ] W8 数据质量门禁 + 可视化看板
- [ ] W9 实时链路（Spark / Kafka / Flink）
- [ ] W10 压测与故障演练
- [ ] W11 文档与一键复现
- [ ] W12 A/B 实验分析

各周的关键决策、踩坑与验收口径见 `docs/progress.md`。

## 数据获取

数据集：Kaggle **Olist Brazilian E-Commerce Public Dataset**（约 45MB，9 张 CSV，
覆盖 2016-09 ~ 2018-10，币种 BRL，不做汇率转换）。

把 9 个 CSV 放入 `data/raw/` 即可（该目录与 `*.parquet` 均被 `.gitignore` 忽略，不入库）。

## 快速开始

```powershell
# 1. 环境（本机使用 conda 环境 dataeng）
conda activate dataeng
pip install -r requirements.txt

# 2. 全链路按序执行：每一步都自带对账，非 0 退出即停
python etl/extract/ods_load.py          # 9 张 CSV → Parquet（dt=2018-10-18 分区；先删后写，幂等）
python etl/extract/reconcile.py         # ODS 对账：行数 / 主键去重数 / 金额 SUM 三方一致
python etl/transform/dwd_build.py       # DWD：5 张维度表 + 4 张事实表
python etl/transform/dwd_reconcile.py   # DWD 对账：44 项断言（结构 + 指标 + 口径标记）
python etl/transform/dws_build.py       # DWS：4 张汇总表
python etl/transform/ads_build.py       # ADS：4 张指标表
python etl/transform/dws_reconcile.py   # DWS/ADS 对账：27 项断言

# 3. SQL 性能基准（可选，产出 docs/benchmark_plans/ 执行计划证据）
python etl/benchmark.py

# 4. 任务编排（在 WSL2 内执行，环境搭建见 docs/airflow_setup.md）
airflow dags test ecommerce_dw_daily 2026-10-01
```

**顺序不可颠倒**：`ods_load.py` 必须最先跑，ODS 层是后续所有层的输入。ODS 对账对残缺
Parquet 是硬失败（报错误而非静默出数）——中途被中断的运行需重跑 `ods_load.py` 自愈。

## 文档索引

| 文档 | 内容 |
|---|---|
| `docs/exploration_notes.md` | 原始数据探查发现与问题记录（15 项发现 + 补查结果） |
| `docs/modeling.md` | 总线矩阵、4 张事实表六要素、5 张维度表设计、Mermaid ER 图 |
| `docs/data_dictionary.md` | 指标口径字典（12 个条目，含 RFM 打分与八段映射） |
| `docs/dws_design.md` | DWS / ADS 分层设计、8 张表要素、对账体系与已知局限 |
| `docs/benchmark.md` | SQL 性能调优基准报告（7 组对照，双环境数字） |
| `docs/airflow_setup.md` | Airflow（WSL2）环境搭建与四维验收清单 |
| `docs/progress.md` | 项目进度日志、关键决策记录与踩坑记录 |
| `docs/benchmark_plans/` | 性能基准原始证据（14 份 EXPLAIN ANALYZE 计划 + results.json） |

> `docs/troubleshooting.md` 计划在 W10（压测与故障演练）产出。
