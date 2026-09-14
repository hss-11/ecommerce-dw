# 项目进度日志

## 当前状态
- 阶段：W1 完成 ✅ → 进入 W2 维度建模设计
- 上次更新：2026-09-14
- 卡点：无
- 待办：补查 9/10/11 → 补全 exploration_notes.md 第五节 → Day 5 Git 首次推送


## 环境信息（重装或换设备时看这里）
- 电脑：i7-10750H（6核12线程），内存 15.9GB，独显（本项目不用），Win11
- Miniconda：D:\Miniconda（本体已在 D 盘，无需迁移）
- conda 环境：base(3.13) / master_env / python_3.9 / time_llm / **dataeng(3.11)**
- 本项目环境：dataeng → D:\Miniconda\envs\dataeng
- 已装包：duckdb 1.5.5、polars 1.44.2、pyarrow 25.0.1
- pip 源：清华镜像（全局生效）
- 项目路径：D:\projects\ecommerce-dw
- 磁盘策略：软件优先装 D 盘；Git 例外装 C 盘（写注册表和右键菜单）
- 不装 Docker Desktop（WSL2 吃 2-8GB），实时链路 W9 上云
- PyCharm 工作目录：已设为项目根目录（配置模板方式，新脚本自动继承）

## 已完成
- [x] Day 1 下载 Olist 数据集（9 CSV）到 data/raw，zip 备份至 D:\backup
- [x] Day 1 建立完整目录骨架
- [x] Day 2 配 pip 清华源
- [x] Day 2 创建 dataeng 环境（Python 3.11），装 duckdb/polars/pyarrow
- [x] Day 2 导出 requirements.txt（误生成的 C:\Users\胡士尚\requirements.txt 已删）
- [x] Day 2 创建 .gitignore 和 README.md（PyCharm 校验语法无误）
- [x] Day 3 PyCharm 解释器指向 dataeng，包列表可见三个包
- [x] Day 3 test_env.py 跑通（退出码 0）
- [x] Day 3 采用 pathlib 路径自适应模式，解决工作目录导致的 FileNotFoundError
- [x] Day 4 完成 01_explore.py 八模块探查（退出码 0）
- [x] Day 4 产出 docs/exploration_notes.md（11 项发现 + 6 项待决策）
- [x] Day 4 补查 01b_explore_fix.py（8 项完成，3 项待跑）
- [x] Day 4 修正金额对账逻辑（SUM(DISTINCT) → CTE 先聚合再 join）
- [x] Day 4 推翻并重建 reviews 去重方案（改为组合主键不去重）
- [x] Day 4 定位 776 差额真因（内连接静默丢弃，非"无支付"）
- [x] Day 5 Git配置完成

## 关键决策记录（面试讲项目的素材）
| 日期 | 决策 | 理由 |
|---|---|---|
| 09-13 | 数据集只用 Kaggle Olist | 45MB 适配 16GB 内存；天池 3.76G 与点击流 5.67G 放弃 |
| 09-13 | DuckDB 替代 Hive + ClickHouse | 嵌入式列存 OLAP，无服务进程，SQL 概念可迁移 |
| 09-13 | Polars 替代 Spark | 惰性执行/分区裁剪/谓词下推概念一致，内存占用小 |
| 09-13 | 本地不装 Docker | WSL2 后端吃 2-8GB，16GB 机器扛不住 |
| 09-13 | GMV 口径：只算 delivered | canceled/unavailable 无真实交易；进行中订单会让历史数据不可回溯 |
| 09-13 | 用户指标一律用 customer_unique_id | customer_id 与订单数相等，用它算复购率恒为 0 |
| 09-13 | geolocation 先聚合再 join | 邮编平均 52.6 行，直接 join 数据膨胀 52 倍且静默无报错 |
| 09-13 | reviews 按 review_id 去重取最新 | 主键重复 814 条，不去重则评价指标失真 |
| 09-13 | payment 与 order 事实表分开建 | 一单多笔支付（多 4,445 行），合并会虚增订单数 |
| 09-13 | 事实表粒度 = 订单内单个商品项 | 最细粒度可向上汇总任意口径，反之丢失明细 |
| 09-14 | GMV 用 order_items.price+freight_value，不用 payments.payment_value | 支付金额含分期利息（属金融机构收入）；补查8证实差异与分期数单调正相关，是系统性偏移 |
| 09-14 | reviews 不去重，主键改为 (review_id, order_id) 组合键 | 同 review_id 对应不同 order_id 且其余字段全同，去重会丢失订单关联 |
| 09-14 | 窗口函数排序必须加唯一决胜字段 | answer_timestamp 并列导致 ROW_NUMBER 结果不确定，同数据两次跑出不同结果 |
| 09-14 | dim_geolocation LEFT JOIN + COALESCE 兜底 | 邮编覆盖率 98.95%，157 个缺失不能因此丢订单 |
| 09-14 | 类目缺失归 unknown/uncategorized 并在字典声明 | 兜底值不得混入真实类目参与 Top 排名 |
| 09-14 | 算总数类指标前必须核对 join 是否丢行 | 内连接静默丢弃 776 单（0.78%），不报错 |
| 09-14 | 776 单无商品明细：98.87% 属 canceled/unavailable，排除出有效订单集 | 业务正常现象，非数据事故；用 order_items JOIN 会静默丢这 0.78% |
| 09-14 | 唯一 1 单"已送达无支付"不删除，加 is_payment_missing 标记并纳入日常监控 | 金额影响可忽略，但突增即意味支付链路故障，需可发现 |
| 09-14 | 区分 GMV / 平台实收 / 支付流水三个指标 | 775 个无效订单实收 16.26 万 BRL 涉及退款，三者混用是最常见分析错误 |



## 踩坑记录
| 日期 | 现象 | 原因 | 解决 |
|---|---|---|---|
| 09-12 | Parser Error at "COUNT" | 手敲代码混入全角逗号 | 改用英文标点；建 check_fullwidth.py 体检脚本 |
| 09-12 | FileNotFoundError: scratch/test_env.py | PyCharm 工作目录是 scratch/，相对路径解析错位 | 配置模板设工作目录为项目根；脚本改用 pathlib 自适应 |
| 09-13 | 金额对账报 8,182 条不符 | SUM(DISTINCT) 把相同金额的不同商品行去重 | 改用 CTE 先各自聚合到订单粒度再 join |
| 09-14 | 金额对账误报 8,182 条 | SUM(DISTINCT) 把金额相同的不同商品行去重 | 改 CTE 先各自聚合到订单粒度再 join，实际仅 380 条 |
| 09-14 | reviews 去重方案作废 | ORDER BY 时间戳存在并列值，ROW_NUMBER 分配随机 | 改组合主键不去重；若去重须加 order_id 做 tie-breaker |
| 09-14 | 误判"776 个订单无支付" | 未审查自己的 SQL 就下结论；实际是内连接取了交集 | 补查 7 验证否定假设，真因是 776 单无商品明细 |
| 09-14 | git push 反复询问指纹，日志出现 `Could not create directory '/c/Users/\272\372.../.ssh'` | Git 自带 ssh 按 UTF-8 解析路径，中文用户名是 GBK 字节，写不了 known_hosts（认证因 -i 显式指定密钥未受影响） | `git config core.sshCommand "C:/Windows/System32/OpenSSH/ssh.exe"` 改用系统自带 ssh |


## 下一步
- [ ] 跑补查 9/10/11，填完 exploration_notes.md 第五节表格
- [ ] 手敲 SQL 模式笔记：CASE WHEN 分桶、HAVING vs WHERE、窗口函数决胜键、内连接丢数据
- [ ] Day 5 装 Git（C 盘，Initial branch 填 main）
- [ ] Day 5 配 git config 五条（含 core.quotepath false 解决中文乱码）
- [ ] Day 5 生成 SSH 密钥（ed25519）并上传公钥到 GitHub
- [ ] Day 5 GitHub 建空仓库 ecommerce-dw（三个勾全不勾，Public）
- [ ] Day 5 给 10 个空目录加 .gitkeep
- [ ] Day 5 git init → remote add → add → **status 检查** → commit → push
- [ ] Day 5 README 补「数据获取」和「快速开始」两节
- [ ] W2 产出 docs/modeling.md（总线矩阵 + 4 事实表粒度声明 + 5 维度表设计 + ER 图）
- [ ] W2 产出 docs/data_dictionary.md（指标口径字典）

