# 项目进度日志

## 当前状态
- 阶段：W7 完成 ✅ → W8 待启动
- 上次更新：2026-10-13
- 卡点：无（本机 WSL2 + Airflow 部署非阻塞项，按 docs/airflow_setup.md 择期复现即可）
- 待办：W8 启动（GE 质量门禁 + Streamlit 看板 → dq/ + dashboard/，定义见交接文档第十三节路线图）


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
- [x] W5 DWS 汇总层 + ADS 指标层：etl/transform/dws_build.py + ads_build.py + dws_reconcile.py（DWS 4 表：trade_daily 616 / payment_daily 611 / user_summary 96,096 / product_summary 32,951；ADS 4 表：trade_daily 616 / repurchase 23 / retention_cohort 1,821 / rfm_segment 96,096；27 项对账断言全 PASS，GMV 15,419,773.75 / 订单量 96,478 / 客单价 159.83 / 复购率 3.1188% 与字典基准逐项吻合）
- [x] W5 文档：docs/dws_design.md 新建（分层原则 / 8 表设计 / RFM 打分定稿 / 对账体系 / 局限）；data_dictionary.md v1.2（3.3 RFM 打分规则与八段映射定稿）
- [x] W6 SQL 性能调优：etl/benchmark.py + docs/benchmark.md + docs/benchmark_plans/ 15 份证据（7 个"朴素 vs 调优"对照，沙箱 7/7 闸门 PASS，本地复跑 7/7 PASS；有效案例：列裁剪 2.76x / 粒度选表 7.62x / 窗口函数 4.97x / 半连接 1.33x / 先聚合 1.15x（温和）；反直觉案例：UNION vs 条件聚合沙箱反转 0.73x、本地 1.01x 平局——结论绑定环境，双环境数字已写入报告；手动谓词下推无效 0.89x/本地 0.98x，优化器已自动下推+布隆过滤）
- [x] W7 Airflow 编排：dags/ecommerce_dw_daily.py + docs/airflow_setup.md（7 任务链 ODS→DWD→DWS→ADS 含两级对账门禁；retries=2 指数退避；catchup+max_active_runs=1 回刷；失败回调落 logs/airflow_alerts.log；沙箱 Airflow 3.3.2 实测：DagBag 导入零错误、tasks test 7 任务全链 success、dws_reconcile 27/27 PASS、失败任务正确进入 up_for_retry）

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
| 09-14 | 775 单无商品明细：98.97%（767/775）属 canceled/unavailable，排除出有效订单集 | 业务正常现象，非数据事故；用 order_items JOIN 会静默丢这 0.78%（776 是交集差额，含 1 单有明细无支付） |
| 09-14 | 唯一 1 单"已送达无支付"不删除，加 is_payment_missing 标记并纳入日常监控 | 金额影响可忽略，但突增即意味支付链路故障，需可发现 |
| 09-14 | 区分 GMV / 平台实收 / 支付流水三个指标 | 775 个无效订单实收 16.26 万 BRL 涉及退款，三者混用是最常见分析错误 |
| 09-18 | "最近/当前"类计算锚点写死 2018-10-18 | 静态数据集禁用真实当天日期；锚点 = 最大日期后一天，唯一化后任何时间重跑结果一致（S4 定稿时补硬编码） |
| 09-18 | 复购率/N 日留存按下单行为计入全部订单状态 | 衡量"再次下单"意愿而非成交；全周期参考值 3.5% 即基于全状态订单集计算（该近似值已于 10-12 精确化为 3.12%，见下行）；例外：RFM 的 M 分量绑定 GMV 口径只算 delivered |
| 09-18 | order_status 显式保留在事实表内（2.1/2.2/2.4） | S5 交叉核对发现：字典过滤依赖 order_status，建模原文未声明保留该字段——补状态字段要素行 + ER 图属性，消除设计断点 |
| 10-12 | ODS 分区口径：dt = 数据快照批次日期 2018-10-18，9 表统一 | order_items/payments 无日期列无法按业务日期分区；贴源层按同步批次分区是业界标准，业务日期分区留给 DWD；口径改动只需改脚本配置表一行 |
| 10-12 | ODS 贴源层 all_varchar 读取，不做类型转换 | 贴源层必须忠实源文件；类型转换显式留给 DWD，避免解析歧义在源头被静默固化 |
| 10-12 | Parquet 写入幂等 = 先删表目录再写入 | DuckDB 分区写是追加文件语义，不删目录重跑会多出一批文件导致数据翻倍 |
| 10-12 | is_on_time 用时间戳级比较（实际送达 <= 承诺送达），不用日期级 | 日期级会把"承诺当日稍晚送达"算作准时，延迟单由 7,827 变成 6,535，与 W1 基准及字典 4.2 的约 91.9% 口径不符 |
| 10-12 | 类型转换集中在 DWD 层（ID 一律 VARCHAR、金额 DOUBLE、时间戳 TIMESTAMP、计数与标记 INTEGER） | ODS 层 all_varchar 忠实源文件，解析歧义只在 DWD 显式处理一次；S3a 的 INTEGER/VARCHAR 教训由本层承接 |
| 10-12 | dim_seller 实做 SCD2：对订单数最多的卖家模拟 2018-01-01 城市变更（v1 关闭 / v2 生效），事实表按下单日点对点匹配 join | 静态快照数据本无属性变更，用确定性选定的对象做 SCD2 工程练手；3,095 个自然键 → 3,096 行（1 条历史版本），可验证 |
| 10-12 | customer_key 一律取 customer_unique_id；dim_customer 按 Type 1 取该自然人最近一次订单的城市（决胜字段 customer_id） | customer_id 一单一号会让复购率恒为 0；加唯一决胜字段消除时间戳并列导致的随机结果 |
| 10-12 | payment_type 作为低基数描述属性留在 dwd_fact_payment 内，不单独建维度表 | 支付方式仅 5 个取值且无描述性属性，打平进事实表省一次 join（总线矩阵"支付方式"维度的落地方式） |
| 10-12 | 复购率参考值精确化为 3.12%（2,997 ÷ 96,096） | W1 的 ≈3.5% 系"超额 customer_id 数"近似算法，三单以上用户被重复计数 348 个；W4 起以 dwd_fact_delivery 按自然人分组计数为唯一权威口径 |
| 10-12 | W1 发现⑦"138 单缺送达时间"修正为 8 单 | 138 系探查笔记行数歧义；raw 复核 delivered 缺实际送达时间戳仅 8 单，承诺送达字段 0 缺失——探查结论也要带可复算的 SQL 出处 |
| 10-12 | 支付流水口径细分：全量无效单支付 269,735.11 BRL | W1 的 162,591.95 实为 775 个无明细订单（含 8 个进行中）的支付；纯无效状态子集 767 单 / 822 笔 / 161,676.89 BRL |
| 10-12 | DWS 只存可加度量，比率一律在 ADS 用"先加总分子分母再相除"现算 | 客单价/复购率/留存率不可加，对日值直接求和是最常见报表错误；DWS 存分子（GMV）与分母（订单量）两个可加度量即可支撑任意粒度重算 |
| 10-12 | 成交类指标（下单日）与资金类指标（批准日）拆成 trade_daily / payment_daily 两张日级表 | 时间口径不同的指标不做日级对比（字典全局约定）；混放一张表会诱导错误的同日 GMV vs 支付流水对比 |
| 10-12 | dws_trade_daily 的 GMV 只过滤 delivered；订单数保留全量 order_cnt 与 delivered_order_cnt 双口径 | 首轮误用全量口径（15,843,553.24）对不上字典 2.1 基准；探针确认无明细 delivered 单为 0，单来源聚合即可精确对账，无需 join delivery 表 |
| 10-12 | RFM 的 F 分量用业务阈值（1→2 / 2→4 / ≥3→5）替代 NTILE | 96.88% 用户 F=1，NTILE(5) 在 F 上塌缩成同一档失去区分度；R/M 保持 NTILE(5) |
| 10-12 | RFM 八段映射定稿：发展=R高F低、保持=R低F高 | 首轮把"发展/保持"写反，分布数据暴露异常（F高群体占 40% 与复购率 3.12% 矛盾）后对照行业标准修正；修正后 F高 群体 2,997 人，与复购用户数精确一致 |
| 10-12 | RFM 的 R/M 两个 NTILE 排序列末尾补 customer_unique_id 决胜字段（复审修复） | recency_days 与 monetary 大量并列，缺决胜字段时 NTILE 对并列用户的分档在重跑间漂移（实测同一数据 5 次运行：一般发展 22,208/22,209 跳动，单段最多差 9 人）；补字段后 8 段 5 次运行逐段一致，可复现。这是 09-14 铁律"窗口函数排序必须加唯一决胜字段"的再次踩中 |
| 10-13 | 基准测试结论必须标注来源环境；未在本地复跑过的结论不进"可迁移清单" | W6 复核发现 C6 的"反转"是环境属性：沙箱（DuckDB 1.5.6）0.73x，本地（1.5.5）1.01x 平局；C2 幅度也从 7.62x 漂到 11.83x。绝对毫秒不可外推之外，**方向性结论同样要带环境出处**，报告已改为双环境并列表述 |
| 10-13 | 对账任务直接编进 DAG 当质量门禁 | ods/dwd/dws 三级 reconcile 非零退出即阻断下游并触发重试告警；质量检查不是事后抽查，而是管线的一部分 |
| 10-13 | 本地告警用文件落盘替代邮件 | 本地无 SMTP；on_failure_callback 签名与云上告警一致，只换发送体（邮件/Webhook），演示与迁移成本都低 |
| 10-13 | Airflow 装在 WSL2 Ubuntu 而非 Win 原生 / Docker | 官方仅支持 POSIX；Docker Desktop 常驻吃 2-8GB 已排除；.wslconfig 限 3GB 守住 6GB 内存预算 |



## 踩坑记录
| 日期 | 现象 | 原因 | 解决 |
|---|---|---|---|
| 09-12 | Parser Error at "COUNT" | 手敲代码混入全角逗号 | 改用英文标点；建 check_fullwidth.py 体检脚本 |
| 09-12 | FileNotFoundError: scratch/test_env.py | PyCharm 工作目录是 scratch/，相对路径解析错位 | 配置模板设工作目录为项目根；脚本改用 pathlib 自适应 |
| 09-13 | 金额对账报 8,182 条不符 | SUM(DISTINCT) 把相同金额的不同商品行去重 | 改用 CTE 先各自聚合到订单粒度再 join |
| 09-14 | 金额对账误报 8,182 条 | SUM(DISTINCT) 把金额相同的不同商品行去重 | 改 CTE 先各自聚合到订单粒度再 join，实际仅 380 条 |
| 09-14 | reviews 去重方案作废 | ORDER BY 时间戳存在并列值，ROW_NUMBER 分配随机 | 改组合主键不去重；若去重须加 order_id 做 tie-breaker |
| 09-14 | 误判"776 个订单无支付" | 未审查自己的 SQL 就下结论；实际是内连接取了交集 | 补查 7 验证否定假设，真因是 775 单无商品明细（差额 776 = 775 无明细 + 1 有明细无支付） |
| 09-14 | git push 反复询问指纹，日志出现 `Could not create directory '/c/Users/\272\372.../.ssh'` | Git 自带 ssh 按 UTF-8 解析路径，中文用户名是 GBK 字节，写不了 known_hosts（认证因 -i 显式指定密钥未受影响） | `git config core.sshCommand "C:/Windows/System32/OpenSSH/ssh.exe"` 改用系统自带 ssh |
| 09-14 | PyCharm 终端 git 无法识别 | 环境变量是程序启动时的快照，PyCharm 在装 Git 前打开 | 完全退出 PyCharm 重启；装完命令行工具必须重启已打开的终端/IDE |
| 09-14 | cd /d 在 PyCharm 终端报错 | PyCharm 终端是 PowerShell，/d 是 cmd 专属开关 | 看提示符区分终端：PS 开头=PowerShell（直接 cd 路径）；盘符开头=cmd（需 /d） |
| 09-15 | mermaid.live 语法错误 | 粘贴时把围栏语言标识 mermaid 当成了代码第一行 | Mermaid 代码必须从 erDiagram 等图表类型关键字开始 |
| 09-15 | mermaid.live 报 JSON 错误 | 代码残留进入了 Config 标签页（JSON 编辑器） | 无痕窗口重开；读报错先抓关键词定方向 |
| 09-15 | GitHub 上 ER 图只显示代码 | 围栏用了三个单引号而非反引号（中文输入法反引号键输出 ·） | 切英文输入法打反引号 |
| 10-12 | DWD 构建与对账连锁失败：`WinError 32`（文件被占用）、`No magic bytes found at end of file` | 上一次运行被中断，Parquet 未写完即被杀，留下缺尾部魔数的残缺文件；该文件又被外部进程句柄占用（无删除共享），脚本"先删后写"的幂等第一步必然失败 | 中断后先清理残表目录再重跑；占用无法释放期间用脚本预留的 `ODS_DIR` 环境变量把输入临时指向完好副本；对账脚本对残缺文件报魔数错误属"可发现的硬失败"，比静默出数安全 |
| 10-12 | DWD 断言延迟单 6,535 对不上 W1 基准 7,827 | 承诺送达是日期语义（时间分量恒 00:00:00），日期级比较粒度与 W1 探查 SQL 不一致 | is_on_time 改时间戳级比较；教训：**探查基准必须记录 SQL 比较粒度，落地实现逐字对齐** |
| 10-12 | W5 首轮 SUM(dws_trade_daily.gmv) = 15,843,553.24 对不上字典 GMV 基准 | 构建时未按字典 2.1 过滤 delivered，把全量订单金额当成 GMV | 先跑探针摸清真实数字再冻结对账断言；gmv/item_amt/freight_amt 改 CASE WHEN delivered 过滤，新增 delivered_order_cnt 列，aov 分母同步修正——对账驱动开发，而非事后补对账 |
| 10-12 | W5 复审发现 RFM 分层人数不可复现（27 项断言却全 PASS） | NTILE 排序列有大量并列值且无唯一决胜字段；断言只覆盖行数 / GMV 合计 / 段数，恰好全落在漂移盲区 | 两处 NTILE 各补 customer_unique_id 决胜字段并重跑；并固化教训——**对账断言要通过"同数据多跑几次比对"来验证，断言全绿不等于结果稳定** |
| 10-13 | W6 报告初稿两处"数字归因错位"：C6 反转 0.73x 被写成数据集固有现象；C5 的 190,036 行被解释为"616 日 × 平均窗口天数" | 引用数字未标注来源环境（数字实际出自沙箱 1.5.6，本地 1.5.5 复跑是 1.01x 平局）；190,036 未回到执行计划逐算子核对——它实为去相关化 range join 首阶段只应用 `<=` 条件产生的上三角候选对 616×617/2，FILTER 后才收敛至 4,243 | 报告改为双环境并列表述；C5 机制按计划真实算子重写；立规矩：**报告里每个引用数字必须在计划或数据里有可指认的出处，方向性结论也要有环境出处** |
| 10-13 | 沙箱→项目目录挂载写入持续"权限拒绝"：两份 W7 文档降级到 artifacts 未同步、progress.md 的 W7 更新实际一处未落（但工具层回执显示"写入成功"） | 跨系统挂载的文件权限/句柄问题（同 10-12 ODS 文件被锁一脉相承：Windows 宿主句柄与 Linux 侧写入互踩）；且"写成功"回执不等于落盘 | 教训固化：**交付物必须读回校验**（本机 read/哈希比对才算数）；两份原件后经网盘找回，airflow_setup.md 以哈希校验覆盖归位，progress.md 六处按原补丁落盘；协作者另在无 Airflow 环境下用桩模块对 DAG 做了结构验证（拓扑/重试配置/回调/失败传导 22/22 通过），作为沙箱结论的本地旁证 |
| 10-13 | Airflow 失败告警看似没触发 | on_failure_callback 只在重试全部耗尽后触发（up_for_retry 期间不触发）；retries=2 + 5min 起步的指数退避意味着告警约 15 分钟后才落盘 | 快速验证告警路径时把 retries 临时改 0；讲告警机制时主动说明这个时序 |


## 下一步
- [x] W5-S1 汇总粒度：对齐字典指标需求，落成 4 张 DWS 表（日交易 / 日资金 / 用户 / 商品）
- [x] W5-S2 DWS 汇总层：dws_build.py 落地（RFM 三分量锚点 2018-10-18；F 用业务阈值替代塌缩的 NTILE）
- [x] W5-S3 ADS 指标层：ads_build.py 落地（客单价先加再除 / 7 日均线 / 全周期+90D 滚动复购 / N 日留存剔除不完整队列 / RFM 八段）
- [x] W5-S4 逐项对账：dws_reconcile.py 27 项断言全 PASS（复用 W4 冻结基准 + 容差断言模式）→ 待里程碑 commit
- [x] W6：SQL 性能调优专项（etl/benchmark.py + docs/benchmark.md + docs/benchmark_plans/ 15 份证据；沙箱 7/7 闸门 PASS，本地复跑 7/7 PASS，报告已改双环境表述）
- [x] W7：Airflow 编排（幂等/重试/回刷/告警 → dags/ecommerce_dw_daily.py + docs/airflow_setup.md，沙箱 Airflow 3.3.2 全链实测通过）
- [ ] W8：GE 质量门禁 + Streamlit 看板（→ dq/ + dashboard/，交接文档第十三节路线图）

