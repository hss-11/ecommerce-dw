# E-Commerce Data Warehouse

端到端电商数据仓库项目：基于 Olist 巴西电商公开数据集，实现 ODS → DWD → DWS → ADS 四层数仓建模，
使用 DuckDB + Polars 做离线加工，Airflow 做任务编排，Great Expectations 做数据质量校验，
Streamlit 做指标可视化。

## 技术栈

`Python 3.11` `DuckDB` `Polars` `PyArrow` `Airflow` `Great Expectations` `Streamlit` `Spark` `Kafka` `Flink`

## 项目进度

- [x] W1 数据探查与环境搭建
- [ ] W2 维度建模设计
- [ ] W3 ODS 贴源层
- [ ] W4 DWD 明细层
- [ ] W5 DWS 汇总层 + ADS 指标层
- [ ] W6 SQL 性能调优
- [ ] W7 Airflow 任务编排
- [ ] W8 数据质量门禁 + 可视化看板
- [ ] W9 实时链路（Spark / Kafka / Flink）
- [ ] W10 压测与故障演练
- [ ] W11 文档与一键复现
- [ ] W12 A/B 实验分析

## 文档索引

| 文档 | 内容 |
|---|---|
| `docs/exploration_notes.md` | 原始数据探查发现与问题记录 |
| `docs/modeling.md` | 总线矩阵、事实表粒度声明、维度设计 |
| `docs/data_dictionary.md` | 指标口径字典 |
| `docs/benchmark.md` | SQL 性能调优前后对比 |
| `docs/troubleshooting.md` | 踩坑与故障排查记录 |
| `docs/progress.md` | 项目进度日志 |
