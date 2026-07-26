# 多条件选股技能 (Stock Screening)

## 前置条件

本技能依赖本地数据库。首次使用前必须由 **data-init** 技能完成:
1. `init_full_data(include_sector_members=True)` — 初始化
2. `update_daily_data()` — 每日更新

> 若用户未初始化, 引导到 `eastmoney-quant-data-init` 技能。

## 数据依赖

`screen_stocks` 查询的是 `stock_spot` 表(全市场实时行情快照), JOIN `stock_rank`(人气排名)。
板块过滤时额外查询 `sector_member` 表。

**关键字段速查**:

| 字段 | 来源表 | 含义 |
|------|--------|------|
| `symbol`, `name` | stock_spot | 代码, 名称 |
| `latest_price` | stock_spot | 最新价 |
| `change_pct` | stock_spot | 涨跌幅(%) |
| `volume_ratio` | stock_spot | 量比 |
| `turnover_rate` | stock_spot | 换手率(%) |
| `pe_dynamic` | stock_spot | 动态市盈率 |
| `pb` | stock_spot | 市净率 |
| `total_market_cap` | stock_spot | 总市值(亿) |
| `float_market_cap` | stock_spot | 流通市值(亿) |
| `sixty_day_change` | stock_spot | 60日涨跌幅(%) |
| `ytd_change` | stock_spot | 年初至今涨跌幅(%) |
| `amplitude` | stock_spot | 振幅(%) |
| `popularity_rank` | stock_rank | 人气排名(越小越热) |

---

## 选股工具

### 1. `screen_stocks` — 万能多条件组合

```
screen_stocks(conditions, top_n=50, sort_by="change_pct", sector_code=None, name_keyword=None)
```

**conditions 全部可选键** (JSON):

| 键 | 含义 | 示例 |
|----|------|------|
| `min_price` / `max_price` | 价格区间 | `{"min_price":10,"max_price":50}` |
| `min_change_pct` / `max_change_pct` | 涨跌幅区间 | `{"min_change_pct":3,"max_change_pct":9.5}` |
| `min_volume_ratio` | 最小量比 | `{"min_volume_ratio":1.5}` |
| `min_turnover_rate` / `max_turnover_rate` | 换手率区间 | `{"min_turnover_rate":5}` |
| `min_pe` / `max_pe` | PE区间 | `{"max_pe":30}` |
| `min_pb` / `max_pb` | PB区间 | `{"max_pb":3}` |
| `min_market_cap` / `max_market_cap` | 总市值区间(亿) | `{"min_market_cap":100}` |
| `min_float_market_cap` | 最小流通市值(亿) | `{"min_float_market_cap":50}` |
| `min_sixty_day_change` | 最小60日涨幅 | `{"min_sixty_day_change":0}` |
| `min_ytd_change` | 最小年初至今涨幅 | `{"min_ytd_change":10}` |
| `min_amplitude` / `max_amplitude` | 振幅区间 | `{"min_amplitude":3}` |

**sort_by**: `change_pct` | `volume_ratio` | `turnover_rate` | `pe_dynamic` | `pb` | `total_market_cap` | `popularity_rank`

**sector_code**: 限定板块, 如 `"BK1090"` (需 `include_sector_members=True` 初始化)

**name_keyword**: 股票名称关键词模糊匹配

---

## 典型组合模板

| 场景 | conditions | sort_by |
|------|------------|---------|
| 放量突破 | `{"min_change_pct":3,"min_volume_ratio":2,"max_pe":50}` | change_pct |
| 低估值蓝筹 | `{"max_pe":15,"max_pb":1.5,"min_market_cap":500}` | change_pct |
| 强势小盘 | `{"min_change_pct":5,"min_turnover_rate":10,"max_market_cap":100}` | change_pct |
| 超跌反弹 | `{"max_change_pct":-5,"min_turnover_rate":2,"max_pe":30}` | change_pct |
| 高人气追涨 | `{"min_change_pct":2}` | popularity_rank |
| 业绩驱动 | `{"max_pe":20,"min_sixty_day_change":10,"min_ytd_change":20}` | pe_dynamic |
| 板块内选股 | `sector_code="BK1090"` + `{"min_volume_ratio":1.5}` | change_pct |

### 2. `screen_by_pattern` — 5种预置形态

| 形态 | 描述 |
|------|------|
| `oversold_reversal` | 超跌反弹(当日收涨) |
| `volume_surge` | 放量突破(量比≥2 + 上涨) |
| `strong_breakout` | 强势突破(涨幅≥5% + 换手≥5%) |
| `low_pe_growth` | 低估值成长(PE<20 + 量比>1 + 上涨) |
| `ma_bullish` | 多头排列(涨+量比>1+60日涨幅>0) |

### 3. 板块→股票挖掘

```
get_sector_list(sector_type="concept")  → 获取全部板块, 客户端按 change_pct 排序取 top N
get_sector_members_flow(sector_code)    → 板块内龙头+资金流向+人气
get_stock_belong_sectors("000001")      → 反向查股票所属板块
```

### 4. K线批量预热(技能内循环)

当选出候选池后, 对候选股逐一调 `get_kline_local_or_net` 可提前缓存K线+指标:
```
for symbol in candidates:
    get_kline_local_or_net(symbol, days=250)
```
无需专用 `batch_download_kline` 工具。

### 5. 人气排名多维度排序(技能内处理)

```
get_popularity_rankings(top_n=100)
→ 客户端按 change_pct 排序 → 相当于 get_top_gainers_rank
→ 客户端按 volume 排序     → 相当于 get_top_volume_rank
→ 客户端按 turnover_rate 排序 → 相当于 get_top_turnover_rank
```

---

## 筛选后深度分析

选股结果需进一步验证，引导到 **报告技能**:

1. `generate_stock_report(symbol)` — 生成完整分析报告(趋势/支撑阻力/风险/仓位)
2. `get_rank_trend_data(symbol, days=30)` — 人气排名是否持续上升
3. `get_stock_belong_sectors(symbol)` — 所属板块是否强势

---

## 决策原则

1. 先用 `screen_stocks` 粗筛(本地毫秒级)
2. 对 Top 5-10 调用 `generate_stock_report` 深度分析
3. 按风险收益比排序, 选出最值得关注的标的
4. 默认 `top_n=50`, 超100提醒用户缩小范围

---

## 下一个技能

选股完成后, 对候选个股使用 **report-generation** 技能生成分析报告 → `eastmoney-quant-report-generation`
