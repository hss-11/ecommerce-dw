# DWS / ADS 设计文档

> 版本：v1.0｜创建日期：2026-10-12（W5 落地）
> 本文档记录 DWS 汇总层与 ADS 指标层的表设计、口径映射与已知局限。
> 指标口径的权威定义见 docs/data_dictionary.md，本文档只做"表怎么建"的工程说明。

## 1. 分层定位与原则

| 层 | 职责 | 存放内容 | 存放原则 |
| --- | --- | --- | --- |
| DWD | 明细事实 | 一行 = 一个业务事件（订单项/支付/订单生命周期/评价） | 保留全部字段与标记，不做聚合 |
| DWS | 轻度汇总 | 按常用维度组合的可加度量（金额、单数、件数） | 只存可加度量；比率禁止入库 |
| ADS | 指标应用 | 可直接上报表的指标值（GMV、客单价、复购率、留存率、RFM 分层） | 比率在此层"先加总分子分母、再相除"现算 |

三条硬规则：
1. **比率不可加**：客单价、复购率、留存率、准时率都不能对日值求和，任意聚合粒度
   必须用分子分母各自加总后再相除。DWS 因此只存分子（GMV）与分母（订单量）两个
   可加度量，ADS 现算比率。
2. **时间口径不混放**：成交类指标按下单日归属，资金类指标按批准日（代理）归属。
   两种口径拆成两张日级表（trade_daily / payment_daily），不做同日对比。
3. **成交口径统一 delivered**：GMV、订单量、客单价的分子分母全部只算
   `order_status = 'delivered'`，与字典 2.1 / 2.4 / 2.5 一一对应。

## 2. DWS 汇总层（4 表）

### 2.1 dws_trade_daily — 日度交易汇总（下单日口径）

| 要素 | 说明 |
| --- | --- |
| 粒度 | 一行 = 一个下单日 |
| 来源 | dwd_fact_order_item |
| 行数 | 616（2016-09-04 ~ 2018-09-03 有成交的日期数） |
| date_key | 下单日智能键 yyyymmdd（继承 DWD） |
| full_date | 由 date_key 经 strptime 转回 DATE，供报表与窗口函数排序 |
| order_cnt | 当日全部下单订单数（含无效与进行中，看下单趋势） |
| delivered_order_cnt | 当日 delivered 订单数（字典 2.4 订单量的日级分子） |
| item_cnt | 当日商品明细行数 |
| gmv | 当日 delivered 订单的 SUM(item_price + freight_value)（字典 2.1） |
| item_amt / freight_amt | gmv 的拆分量（仅 delivered），item_amt + freight_amt = gmv 自洽 |

设计说明：
- GMV 只对 delivered 过滤。W5 首轮曾误用全量口径（15,843,553.24），与字典 2.1 的
  15,419,773.75 对不上，已修正为 CASE WHEN order_status='delivered' 过滤。
- 订单数保留两个口径：order_cnt（全量，看下单量趋势）与 delivered_order_cnt
  （成交口径，做客单价分母）。两者只差 0.08%（98,666 vs 96,478 的全周期和）。
- 探查确认：无商品明细的 delivered 订单为 0 单（字典 2.4 担心的 1% 情况实际不存在），
  故 delivered_order_cnt 从 order_item 聚合即可精确对账到 96,478，无需 join delivery 表。
- 日期覆盖止于 2018-09-03 而非数据末端 2018-10-17：2018-09-04 之后全库仅 16 个订单，
  且全部无商品明细、全部为 canceled，天然不进本表。交易日序列提前结束是数据真实边界，
  不是聚合丢数——报表展示时需说明该口径边界。

### 2.2 dws_payment_daily — 日度资金汇总（批准日口径）

| 要素 | 说明 |
| --- | --- |
| 粒度 | 一行 = 一个批准日（order_approved_at 代理） |
| 来源 | dwd_fact_payment |
| 行数 | 611 行 = 610 个有日期的批准日 + 1 行 NULL date_key（未批准订单的支付，无法归属日期，保留以保全流水 37,129.77 BRL） |
| paid_order_cnt | 当日有支付的订单数 |
| payment_cnt | 当日支付笔数（一单多笔） |
| payment_flow | 当日 SUM(payment_value)，不过滤（字典 2.2 支付流水） |
| platform_income | 剔除 canceled/unavailable 后的当日支付（字典 2.3 平台实收） |
| invalid_payment | 无效订单的当日支付（退款场景资金流出） |

设计说明：
- 三兄弟口径并排存放：payment_flow = platform_income + invalid_payment 自洽
  （对账 B6 断言 = 0）。
- NULL date_key 行必须保留：删掉它会让 payment_flow 对不上 16,008,872.12 的基准。

### 2.3 dws_user_summary — 用户汇总

| 要素 | 说明 |
| --- | --- |
| 粒度 | 一行 = 一个下单用户（customer_unique_id） |
| 来源 | dwd_fact_delivery（R/F）+ dwd_fact_order_item（M） |
| 行数 | 96,096 |
| order_cnt | 全周期下单次数（全部状态，字典 3.3 的 F） |
| first_order_date / last_order_date | 首次 / 最近一次下单日 |
| recency_days | 2018-10-18 − last_order_date（字典 3.3 的 R） |
| monetary | 全周期 delivered 成交额（字典 3.3 的 M，继承 GMV 口径） |
| is_repurchase | order_cnt >= 2 标记（全周期复购判定） |

### 2.4 dws_product_summary — 商品汇总

| 要素 | 说明 |
| --- | --- |
| 粒度 | 一行 = 一个商品（product_id） |
| 来源 | dwd_dim_product LEFT JOIN 销量聚合 LEFT JOIN 评分聚合 |
| 行数 | 32,951（含 0 销量商品，LEFT JOIN 保留全量商品） |
| sold_item_cnt / sold_order_cnt | 销量件数 / 成交订单数（delivered） |
| product_gmv | 该商品 delivered 成交额（字典 2.1 商品级口径） |
| product_amt / product_freight | 商品金额 / 运费拆分 |
| review_cnt / avg_score | 经订单明细归因的评价数与均分 |

已知局限：评价挂在订单而非商品，一单多品时同一评价会计入该单全部商品
（字典 4.4 局限②），review_cnt 存在重复计数，只用于相对比较，不用于精确对账。

## 3. ADS 指标层（4 表）

### 3.1 ads_trade_daily — 日度交易指标

| 要素 | 说明 |
| --- | --- |
| 来源 | dws_trade_daily 直接派生 |
| aov | 客单价 = gmv / delivered_order_cnt（字典 2.5，先加再除的日级形态） |
| gmv_ma7 / order_cnt_ma7 | 7 日移动平均（窗口函数 AVG OVER 前 6 行到当前行） |

全周期客单价 = SUM(gmv) / SUM(delivered_order_cnt) = 159.83 BRL。

### 3.2 ads_repurchase — 复购率（字典 3.1）

| 要素 | 说明 |
| --- | --- |
| window_type = 'all_period' | 全周期一行：96,096 用户 / 2,997 复购 / 3.1188% |
| window_type = 'rolling_90d' | 90 天滚动月末快照，2016-12-31 起共 22 期 |
| 统计行为 | 下单行为（全部订单状态计入，衡量"再次下单"意愿） |

月末快照从 2016-12-31 开始：此前的 90 天窗口不完整（数据从 2016-09-04 起），
提前出数会被系统性低估。

### 3.3 ads_retention_cohort — N 日留存（字典 3.2）

| 要素 | 说明 |
| --- | --- |
| 粒度 | cohort_date（首购日）× n（7 / 30 / 90） |
| cohort_size | 该首购日的新用户数 |
| retained_cnt | 首购后第 n 天再次下单的用户数 |
| retention_pct | retained_cnt / cohort_size × 100 |

剔除规则：cohort_date + n > 2018-10-17（数据最大日）的队列观察期不完整，
不出行（对账 C11 断言 = 0），避免留存率被系统性低估。
参考值：7 日留存均值 ≈ 0.02%——复购率本身仅 3.12%，留存天然接近 0，
这是 Olist 一次性消费业务的真实特征，不是计算错误。

### 3.4 ads_rfm_segment — RFM 分层（字典 3.3）

打分规则（W5 定稿，字典 3.3 同步）：
- R：NTILE(5) OVER (ORDER BY recency_days DESC, customer_unique_id)，间隔越小分越高
- M：NTILE(5) OVER (ORDER BY monetary ASC, customer_unique_id)，金额越大分越高
- F：业务阈值——order_cnt >= 3 → 5 分，= 2 → 4 分，= 1 → 2 分
  （96.88% 用户 F=1，NTILE 在 F 上塌缩成同一档，失去区分度，故改用阈值）
- 高/低判定：得分 >= 4 为"高"
- R / M 的 ORDER BY 末尾必须带 customer_unique_id 决胜字段：recency_days 与 monetary
  存在大量并列值，缺决胜字段时 NTILE 的并列分档在重跑间会漂移（W5 实测 5 次运行
  一般发展在 22,208 / 22,209 之间跳动），违反项目 09-14 定下的"窗口函数排序必须加
  唯一决胜字段"铁律

八段映射（R高=近期来过，F高=频次高，M高=金额高；发展=R高F低，保持=R低F高）：

| rfm_segment | R | F | M | 人数 | 占比 | GMV 贡献（BRL） |
| --- | --- | --- | --- | --- | --- | --- |
| 一般挽留用户 | 低 | 低 | 低 | 34,798 | 36.21% | 2,340,219.99 |
| 一般发展用户 | 高 | 低 | 低 | 22,212 | 23.11% | 1,541,760.71 |
| 重要挽留用户 | 低 | 低 | 高 | 21,168 | 22.03% | 6,202,709.21 |
| 重要发展用户 | 高 | 低 | 高 | 14,921 | 15.53% | 4,434,526.24 |
| 重要保持用户 | 低 | 高 | 高 | 1,300 | 1.35% | 457,084.21 |
| 重要价值用户 | 高 | 高 | 高 | 1,049 | 1.09% | 385,876.95 |
| 一般保持用户 | 低 | 高 | 低 | 392 | 0.41% | 35,176.97 |
| 一般价值用户 | 高 | 高 | 低 | 256 | 0.27% | 22,419.47 |

业务解读：高金额群体（重要挽留 + 重要发展 = 36,089 人 / 37.6%）贡献了 10,637,235 BRL
（约 69% GMV），是运营重点。一次性消费特征明显——F高 群体合计仅 2,997 人（3.12%），
与全周期复购率精确一致。

NTILE 边界说明：recency_days / monetary 存在大量并列值，若 NTILE(5) 不带决胜字段，
并列用户的分档在重跑间会漂移（W5 实测：同一份 DWS 数据独立计算 5 次，一般发展在
22,208 / 22,209 之间跳动）。现已补 customer_unique_id 作为决胜字段，8 段人数完全
可复现（5 次运行逐段一致，落库产物与独立重算一致）。monetary 总和恒等于 GMV。

## 4. 对账体系（dws_reconcile.py）

27 项断言分三组，全部 PASS 退出码为 0：
- A 组（5 项）：DWD 底座基准复核——确认对账地基未漂移
- B 组（11 项）：DWS vs 字典基准——GMV / 订单量 / 支付三兄弟 / 用户数 / 商品数
- C 组（11 项）：ADS vs DWS 与字典——客单价 / 复购率 / RFM 行数与 GMV / 留存队列完整性

基准值全部冻结在脚本头部常量（BASE_GMV = 15419773.75 等），与 W4 dwd_reconcile 同源。
金额断言容差 0.01（浮点求和尾差），计数断言容差 0。

## 5. 已知局限汇总

1. payment_daily 有 1 行 NULL date_key（未批准订单的支付），无法归属日期但保留以保全流水；
   报表按日统计时该行天然不落任何日期，属预期行为。
2. trade_daily 的 gmv 仅含 delivered，进行中订单成交后会让历史日期的 gmv 增大——
   这是"成交口径可回溯"的固有代价（字典 2.1 已声明），静态快照下不影响。
3. 商品评价的订单归因在一单多品时重复计数（见 2.4）。
4. RFM 的 NTILE 分档原本对并列值有漂移（实测同一数据 5 次运行，单段最多差 9 人），
   已通过补 customer_unique_id 决胜字段消除（见 3.4）；注意对账脚本的 27 项断言不覆盖
   分段稳定性（只验行数 / GMV 合计 / 段数），属断言盲区，稳定性靠本次实测复核保障。
5. 90 天滚动复购率临近数据末端的快照窗口不完整，后期数值被低估（字典 3.1 局限②）。
