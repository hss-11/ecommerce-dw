# 维度建模设计文档

> 版本：v1.0｜创建日期：2026-09-15
> 本文档是 ecommerce-dw 数仓的设计图纸：总线矩阵 → 事实表设计 → 维度表设计 → ER图。
> 设计依据：docs/exploration_notes.md 中的 15 项探查结论。

## 1. 总线矩阵

| 业务过程 \ 维度 | 日期 | 客户 | 商品 | 卖家 | 地理 | 支付方式 |
| --- | --- | --- |----| --- | --- |-----|
| 下单（订单商品项） | √ | √ | √  | √ | √ | —   |
| 支付 | √ | √ | —  | — | — | √   |
| 评价 | √ | √ | —  | — | — | —   |
| 物流配送 | √ | √ | —  | √ | √ | —   |


### 设计说明
1. 支付行没有商品维度：payments 表只有 order_id，一单多品时无法把一笔支付
   分摊到具体商品，这是数据本身的边界。
2. 评价行没有商品维度：reviews 挂在订单上而非商品上；虽可经订单明细间接
   关联商品，但一单多品时一条评价对应多个商品，直接关联会重复计数。
3. 下单行没有支付方式：下单时支付尚未发生，支付方式对下单过程无意义。
4. 日期维度全打勾，但各行含义不同（下单日/支付日/评价创建日/发货日），
   这正是一致性维度要管理的：同一张 dim_date，不同事实表通过不同外键挂接。

## 2.事实表的设计

### 2.1 dwd_fact_order_item (订单商品项事实表·事务事实表)
| 要素 | 内容 |
| -- | -- |
| 粒度 | 一行 = 一个订单中的一个商品项；主键（order_id, order_item_id） |
| 数据来源 | order_items INNER JOIN orders |
| 度量 | item_price 商品金额（可加）、freight_value 运费（可加）、quantity 恒为1（可加，便于SUM计数） |
| 维度外键 | date_key(下单日)、customer_key、product_key、seller_key、geo_key |
| 退化维度 | order_id (单据号，留在表内用于回查与对账) |
| 过滤规则 | 不过滤，保留全量；canceled/unavailable 订单以标记区分 |
| 标记字段 | is_valid_order (delivered 及进行中 = 1，canceled/unavailable = 0) |

### 2.2 dwd_fact_payment (支付事实表·事务事实表)
| 要素 | 内容 |
| -- | -- |
| 粒度 | 一行 = 一笔支付；主键 (order_id, payment_sequential) |
| 数据来源 | payments INNER JOIN orders |
| 度量 | payment_value 支付金额 (可加，但含分期利息，≠ GMV),payment_installments 分期数 (不可加) |
| 维度外键 | date_key (以 order_approved_at 代理，payments 无独立时间字段)、customer_key |
| 退化维度 | order_id、payment_sequential (组合起来定位一笔支付) |
| 过滤规则 | 不过滤，保留全量 (含775个无效订单的支付记录，用于平台实收口径) |
| 标记字段 | is_not_defined_payment (payment_type = 'not_defined' 时 = 1，标记异常支付) | 

### 2.3 dwd_fact_review (评价事实表·事务事实表)
| 要素 | 内容 |
| -- | -- |
| 粒度 | 一行 = 一条评价与一个订单的关联；主键(order_id,review_id) |
| 数据来源 | reviews INNER JOIN orders |
| 度量 | review_score 评分(不可加);has_comment (有评论文字 = 1，无 = 0)，SUM起来就是"留评数" |
| 维度外键 | date_key (评价创建日review_creation_date)、customer_key |
| 退化维度 | review_id |
| 过滤规则 | 不过滤 (W1发现①不去重) |
| 标记字段 | is_review_id_reused（同一 review_id 关联多个订单时 = 1，对应 W1 发现① 的 814 条） |

### 2.4 dwd_fact_delivery (物流事实表·累积快照事实表)
| 要素 | 内容 |
| -- | -- |
| 粒度 | 一行 = 一个订单的物流全生命周期；主键就是 order_id |
| 数据来源 | orders 表自身 |
| 度量 | 各阶段时长 (下单 -> 批准、批准-> 发货、发货 -> 送达、承诺送达 VS 实际送达的差值)，单位小时或天(理论可加，实务只用AVG) |
| 维度外键 | 多个date_key 角色 (下单日、发货日、送达日——对应总线矩阵"日期含义不同") |
| 退化维度 | order_id |
| 过滤规则 | 保留全量（含 canceled/unavailable），以 is_valid_order 标记区分。理由：①与 order_item 事实表口径一致，降低使用者的记忆成本；②无效订单的物流时间戳为 NULL，不参与 AVG 计算，不污染时长类指标；③保留取消订单可支持"订单在履约哪个环节被终止"的归因分析 |
| 标记字段 | is_valid_order、is_on_time（实际送达 <= 承诺送达 = 1）、is_payment_missing（W1 发现⑬ 的那 1 单） |

## 3. 维度表设计

### 3.1 dim_date (日期维度表)
- 覆盖范围：2016-09-01 至 2018-12-31（数据实际到 2018-10-17，留余量防边界丢数）
- 生成方式：脚本生成（不来自业务表）

| 字段 | 类型 | 说明 |
| -- | -- | -- |
| date_key | INTEGER | 主键，智能键 yyyymmdd,如 20160904 |
| full_date | DATE | 完整日期 |
| year | INTEGER | 年 |
| quarter | INTEGER | 季度，1~4 |
| month | INTEGER | 月 |
| year_month | VARCHAR | '2016-09',便于按月聚合展示 |
| day | INTEGER | 日 |
| week_of_year | INTEGER | 年内第几周 |
| day_of_week | INTEGER | 周几，1=周一 ... 7 = 周日 |
| day_name | VARCHAR | 星期名（英文，避免系统语言差异） |
| is_weekend | BOOLEAN | 是否周末 |


### 3.2 dim_seller (卖家维度表，SCD Type 2)
- 来源：sellers 表
- 变化属性：seller_city、seller_state（卖家搬迁场景）
- 注：Olist 为静态快照数据，SCD2 结构用于工程练手，W4 将模拟属性变更

| 字段 | 类型 | 说明 |
| -- | -- | -- |
| seller_key | INTEGER | 主键，代理键（自增）|
| seller_id | VARCHAR | 自然键（业务系统编号），SCD2下不唯一 |
| seller_city | VARCHAR | 卖家城市（变化属性） |
| seller_state | VARCHAR | 卖家州（变化属性） |
| effective_start_date | DATE | 本版本生效起始日 |
| effective_end_date | DATE | 本版本生效截止日，当前版本为 NULL |
| is_current | BOOLEAN | 是否当前生效版本 |

### 3.3 dim_customer（客户维度表）
- 来源：customers 表
- 主键决策：主键用 customer_unique_id（96,096 个自然人）；customer_id 不进维度表——
  一个自然人有多个 customer_id（每单一个），进表会破坏主键唯一性（W1 发现②）
- 城市口径：同一自然人可能因搬家出现多个城市，本数据集为静态快照，
  直接取最近一次订单的城市（Type 1 思路，不追踪历史）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| customer_unique_id | VARCHAR | 主键，自然人标识（32 位哈希字符串） |
| customer_zip_code_prefix | INTEGER | 邮编前缀，关联 dim_geolocation 的桥字段 |
| customer_city | VARCHAR | 客户城市，按地区切片/展示用 |
| customer_state | VARCHAR | 客户州，按地区切片/展示用 |

### 3.4 dim_product（商品维度表）
- 来源：products LEFT JOIN cat_trans（类目英文翻译退化进来打平，使用者无需再 join）
- 兜底值决策：无类目的 610 个商品归 'uncategorized'；有类目但无翻译的归 'unknown'。
  两者含义不同，均不得混入真实类目参与 Top 排名

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| product_id | VARCHAR | 主键（32 位哈希字符串） |
| product_category_name | VARCHAR | 类目原名（葡萄牙语，溯源用） |
| product_category_name_english | VARCHAR | 类目英文名，分析展示主用字段 |
| product_weight_g | DOUBLE | 重量（克），运费/物流成本分析用 |
| product_length_cm | DOUBLE | 长（厘米），体积测算用 |
| product_height_cm | DOUBLE | 高（厘米） |
| product_width_cm | DOUBLE | 宽（厘米） |
| product_photos_qty | INTEGER | 商品图片数，listing 质量分析用（W12 差评归因候选因子） |

### 3.5 dim_geolocation（地理维度表）
- 来源：geolocation 表聚合（GROUP BY 邮编前缀：lat/lng 取 AVG，city/state 取 MIN），
  聚合后 19,015 行（W1 发现⑤：不聚合直接 join 会膨胀 52 倍）
- 覆盖决策：客户邮编匹配率 98.95%，157 个缺失邮编由事实表侧
  COALESCE(city, 'unknown') 兜底，本表不加 unknown 行

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| zip_code_prefix | INTEGER | 主键，邮编前缀（巴西 CEP 前 5 位） |
| lat | DOUBLE | 纬度（邮编内均值），W8 看板地图可视化用 |
| lng | DOUBLE | 经度（邮编内均值） |
| city | VARCHAR | 城市，切片/展示用 |
| state | VARCHAR | 州，切片/展示用 |


## 4. ER 图

'''mermaid
erDiagram
    dim_date ||--o{ dwd_fact_order_item: "date_key 下单日"
    dim_date ||--o{ dwd_fact_payment:"date_key 批准日代理"
    dim_date ||--o{ dwd_fact_review : "date_key 评价创建日"
    dim_date ||--o{ dwd_fact_delivery : "多角色日期"
    dim_customer ||--o{ dwd_fact_order_item: "customer_key"
    dim_customer ||--o{ dwd_fact_payment: "customer_key"
    dim_customer ||--o{ dwd_fact_review: "customer_key"
    dim_customer ||--o{ dwd_fact_delivery: "customer_key"
    dim_product ||--o{ dwd_fact_order_item : "product_key"
    dim_seller ||--o{ dwd_fact_order_item : "seller_key"
    dim_geolocation ||--o{ dwd_fact_order_item: "geo_key"

    dim_date {
        INTEGER date_key PK
        DATE full_date
        INTEGER year
        INTEGER month
        BOOLEAN is_weekend
    }
    dim_customer {
        VARCHAR customer_unique_id PK
        INTEGER customer_zip_code_prefix
        VARCHAR customer_city
        VARCHAR customer_state
    }
    dim_product {
        VARCHAR product_id PK
        VARCHAR product_category_name_english
        DOUBLE product_weight_g
    }
    dim_seller {
        INTEGER seller_key PK
        VARCHAR seller_id
        VARCHAR seller_city
        BOOLEAN is_current
    }
    dim_geolocation {
        INTEGER zip_code_prefix PK
        VARCHAR city
        VARCHAR state
    }
    dwd_fact_order_item {
        VARCHAR order_id PK
        INTEGER order_item_id PK
        INTEGER date_key FK
        VARCHAR customer_key FK
        VARCHAR product_key FK
        INTEGER seller_key FK
        INTEGER geo_key FK
        DOUBLE item_price
        DOUBLE freight_value
        INTEGER is_valid_order
    }
    dwd_fact_payment {
        VARCHAR order_id PK
        INTEGER payment_sequential PK
        INTEGER date_key FK
        VARCHAR customer_key FK
        DOUBLE payment_value
        INTEGER payment_installments
    }
    dwd_fact_review {
        VARCHAR review_id PK
        VARCHAR order_id PK
        INTEGER date_key FK
        VARCHAR customer_key FK
        INTEGER review_score
        INTEGER has_comment
    }
    dwd_fact_delivery {
        VARCHAR order_id PK
        VARCHAR customer_key FK
        INTEGER is_on_time
        INTEGER is_payment_missing
    }
'''