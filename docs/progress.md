# 项目进度日志

## 当前状态
- 阶段：W4 完成 ✅ → W5 待启动
- 上次更新：2026-10-12
- 卡点：无
- 待办：W5 启动（DWS 汇总层 + ADS 指标层：8 个核心指标，窗口函数实战）


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
- [x] W2 产出 docs/modeling.md 与 docs/data_dictionary.md（S5 交叉核对通过）
- [x] W3 ODS 贴源层：etl/extract/ods_load.py + reconcile.py（9 表 CSV→Parquet 按 dt 分区，行数/主键/金额三方对账全 PASS，二次运行幂等验证通过）
- [x] W4 DWD 明细层：etl/transform/dwd_build.py + dwd_reconcile.py（5 维 + 4 事实共 9 表；44 项断言全 PASS；GMV/支付流水/平台实收/准时率/复购率等核心指标与原始 CSV 独立复算逐项吻合）
- [x] W4 文档 v1.1：data_dictionary.md 与 modeling.md 按落地结果精确化（delivered 缺送达时间戳 138→8、is_review_id_reused 口径细化为 789 个 review_id / 1,603 行 / 膨胀 814 行）

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
| 09-18 | "最近/当前"类计算锚点写死 2018-10-18 | 静态数据集禁用真实当天日期；锚点 = 最大日期后一天，唯一化后任何时间重跑结果一致（S4 定稿时补硬编码） |
| 09-18 | 复购率/N 日留存按下单行为计入全部订单状态 | 衡量"再次下单"意愿而非成交；全周期参考值 3.5% 即基于全状态订单集计算；例外：RFM 的 M 分量绑定 GMV 口径只算 delivered |
| 09-18 | order_status 显式保留在事实表内（2.1/2.2/2.4） | S5 交叉核对发现：字典过滤依赖 order_status，建模原文未声明保留该字段——补状态字段要素行 + ER 图属性，消除设计断点 |
| 10-12 | ODS 分区口径：dt = 数据快照批次日期 2018-10-18，9 表统一 | order_items/payments 无日期列无法按业务日期分区；贴源层按同步批次分区是业界标准，业务日期分区留给 DWD；口径改动只需改脚本配置表一行 |
| 10-12 | ODS 贴源层 all_varchar 读取，不做类型转换 | 贴源层必须忠实源文件；类型转换显式留给 DWD，避免解析歧义在源头被静默固化 |
| 10-12 | Parquet 写入幂等 = 先删表目录再写入 | DuckDB 分区写是追加文件语义，不删目录重跑会多出一批文件导致数据翻倍 |
| 10-12 | is_on_time 用时间戳级比较（实际送达 <= 承诺送达），不用日期级 | 日期级会把"承诺当日稍晚送达"算作准时，延迟单由 7,827 变成 6,535，与 W1 基准及字典 4.2 的约 91.9% 口径不符 |
| 10-12 | 类型转换集中在 DWD 层（ID 一律 VARCHAR、金额 DOUBLE、时间戳 TIMESTAMP、计数与标记 INTEGER） | ODS 层 all_varchar 忠实源文件，解析歧义只在 DWD 显式处理一次；S3a 的 INTEGER/VARCHAR 教训由本层承接 |
| 10-12 | dim_seller 实做 SCD2：对订单数最多的卖家模拟 2018-01-01 城市变更（v1 关闭 / v2 生效），事实表按下单日点对点匹配 join | 静态快照数据本无属性变更，用确定性选定的对象做 SCD2 工程练手；3,095 个自然键 → 3,096 行（1 条历史版本），可验证 |
| 10-12 | customer_key 一律取 customer_unique_id；dim_customer 按 Type 1 取该自然人最近一次订单的城市（决胜字段 customer_id） | customer_id 一单一号会让复购率恒为 0；加唯一决胜字段消除时间戳并列导致的随机结果 |
| 10-12 | payment_type 作为低基数描述属性留在 dwd_fact_payment 内，不单独建维度表 | 支付方式仅 5 个取值且无描述性属性，打平进事实表省一次 join（总线矩阵"支付方式"维度的落地方式） |



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
| 09-14 | PyCharm 终端 git 无法识别 | 环境变量是程序启动时的快照，PyCharm 在装 Git 前打开 | 完全退出 PyCharm 重启；装完命令行工具必须重启已打开的终端/IDE |
| 09-14 | cd /d 在 PyCharm 终端报错 | PyCharm 终端是 PowerShell，/d 是 cmd 专属开关 | 看提示符区分终端：PS 开头=PowerShell（直接 cd 路径）；盘符开头=cmd（需 /d） |
| 09-15 | mermaid.live 语法错误 | 粘贴时把围栏语言标识 mermaid 当成了代码第一行 | Mermaid 代码必须从 erDiagram 等图表类型关键字开始 |
| 09-15 | mermaid.live 报 JSON 错误 | 代码残留进入了 Config 标签页（JSON 编辑器） | 无痕窗口重开；读报错先抓关键词定方向 |
| 09-15 | GitHub 上 ER 图只显示代码 | 围栏用了三个单引号而非反引号（中文输入法反引号键输出 ·） | 切英文输入法打反引号 |
| 10-12 | DWD 构建与对账连锁失败：`WinError 32`（文件被占用）、`No magic bytes found at end of file` | 上一次运行被中断，Parquet 未写完即被杀，留下缺尾部魔数的残缺文件；该文件又被外部进程句柄占用（无删除共享），脚本"先删后写"的幂等第一步必然失败 | 中断后先清理残表目录再重跑；占用无法释放期间用脚本预留的 `ODS_DIR` 环境变量把输入临时指向完好副本；对账脚本对残缺文件报魔数错误属"可发现的硬失败"，比静默出数安全 |


## 下一步
- [ ] W5-S1 确定 DWS 汇总粒度：按"维度组合"设计汇总表（用户 / 商品 / 卖家 / 地区 / 时间），先对齐字典里 8 个核心指标各自需要的粒度，避免建了用不上的表
- [ ] W5-S2 建 DWS 汇总层：窗口函数实战落地（复购率与 N 日留存的分母口径、RFM 三分量与锚点 2018-10-18、转化漏斗的累计通过率、评分分布）
- [ ] W5-S3 建 ADS 指标层：将字典口径固化为指标表（GMV / 客单价 / 订单量 / 支付流水 / 平台实收 / 准时交付率 / 平均配送时长 / 留评率）
- [ ] W5-S4 逐项对账：ADS 指标值 vs 字典参考值与 dwd_reconcile 基准（复用冻结基准 + 容差断言模式）→ 里程碑 commit
- [ ] W5 封盘后开 W6：SQL 性能调优专项（EXPLAIN ANALYZE / 索引 / 调优前后耗时对比 → docs/benchmark.md，🔴 投递节点）

