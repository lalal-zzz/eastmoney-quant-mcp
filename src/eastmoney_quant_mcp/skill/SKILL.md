# 东方财富量化 MCP — 主技能

## 工具总览 (仅 9 个 MCP 工具)

```
┌─────────────────────────────────────────────────────────┐
│  数据管理    │ 选股      │ 数据查询               │ 报告  │
│──────────────│──────────│────────────────────────│──────│
│ init_full_   │ screen_  │ get_kline_local_or_net │ gene- │
│ data         │ stocks   │ get_rank_trend_data    │ rate_ │
│ update_daily_│          │ get_sector_list        │ stock_│
│ _data        │          │ get_stock_belong_      │ report│
│ get_data_    │          │ sectors                │       │
│ status       │          │                        │       │
└─────────────────────────────────────────────────────────┘
```

**核心设计**: `screen_stocks` 承担 80% 的查询工作(代替搜索/筛选/板块成分股/排行榜)。其余 8 个工具各司专职。

---

## 每个工具详解及技能使用指南

### 1. `screen_stocks` — 万能查询入口

```
screen_stocks(conditions={}, top_n=50, sort_by="change_pct", sector_code=None, name_keyword=None)
```

**技能用它替代的工具**: `search_stock`, `get_latest_indicators`, `get_popularity_rankings`, `get_sector_members`, `screen_by_pattern`, 所有排行榜、板块筛选工具

**conditions 支持的18个键**(全部可选):

| 键 | 说明 | 示例 |
|----|------|------|
| `min_price` `max_price` | 价格区间 | `{"min_price":10,"max_price":50}` |
| `min_change_pct` `max_change_pct` | 涨跌幅 | `{"min_change_pct":3}` |
| `min_volume_ratio` | 最小量比 | `{"min_volume_ratio":2}` |
| `min_turnover_rate` `max_turnover_rate` | 换手率 | `{"min_turnover_rate":5}` |
| `min_pe` `max_pe` | PE区间 | `{"max_pe":30}` |
| `min_pb` `max_pb` | PB区间 | `{"max_pb":3}` |
| `min_market_cap` `max_market_cap` | 总市值(亿) | `{"min_market_cap":100}` |
| `min_float_market_cap` | 流通市值(亿) | `{"min_float_market_cap":50}` |
| `min_sixty_day_change` | 60日涨幅 | `{"min_sixty_day_change":0}` |
| `min_ytd_change` | 年初至今涨幅 | `{"min_ytd_change":10}` |
| `min_amplitude` `max_amplitude` | 振幅 | `{"min_amplitude":3}` |

**sort_by** 可选: `change_pct`, `volume_ratio`, `turnover_rate`, `pe_dynamic`, `pb`, `total_market_cap`, `latest_price`, `volume`, `amplitude`, `popularity_rank`

**sector_code**: 限定板块(如 `"BK1090"`) — 等效于查看该板块所有成分股
**name_keyword**: 按名称或代码模糊搜索(匹配 symbol 和 name 两列)

---

### 技能: 用 screen_stocks 实现一切查询

#### 股票搜索
```
// 按名称: screen_stocks(name_keyword="银行")
// 按代码: screen_stocks(name_keyword="000001")  → 也匹配代码
// 全市场行情: screen_stocks(conditions={}) → 等效 get_latest_indicators
```

#### 人气排名
```
// 全市场人气榜: screen_stocks(conditions={}, sort_by="popularity_rank", top_n=100)
// 涨幅榜: screen_stocks(conditions={"min_change_pct":0}, sort_by="change_pct")
// 成交量榜: screen_stocks(conditions={}, sort_by="volume")
// 换手率榜: screen_stocks(conditions={}, sort_by="turnover_rate")
```

#### 板块筛选
```
// 某板块成分股: screen_stocks(sector_code="BK1090", sort_by="change_pct")
// 板块内选股: screen_stocks({"max_pe":30,"min_volume_ratio":1.5}, sector_code="BK1090")
```

#### 形态选股(替代 screen_by_pattern)
```
// 超跌反弹: screen_stocks({"min_change_pct":0}, sort_by="change_pct") → 取涨幅最小的正向股
// 放量突破: screen_stocks({"min_change_pct":3,"min_volume_ratio":2})
// 强势突破: screen_stocks({"min_change_pct":5,"min_turnover_rate":5})
// 低估值成长: screen_stocks({"min_change_pct":0,"max_pe":20,"min_volume_ratio":1})
// 多头排列: screen_stocks({"min_change_pct":0,"min_volume_ratio":1,"min_sixty_day_change":0})
```

#### 全市场/板块排行(Top N)
```
// 板块涨跌幅排行:  get_sector_list("concept") → 客户端按change_pct排序取top
// 板块资金流入排行: get_sector_list("concept") → 客户端按main_net_inflow排序取top
// 板块+龙头: get_sector_list → 取top5 → 对每个调screen_stocks(sector_code=该板块)
```

### 2. `get_kline_local_or_net` — K线+指标

```
get_kline_local_or_net(symbol, days=250, adjust="qfq")
```

技能用法: 对选股结果的 top 5-10 逐只下载, 下载即自动缓存技术指标到本地。

### 3. `get_rank_trend_data` — 人气趋势

```
get_rank_trend_data(symbol, days=30)
```

技能用法: 报告技能调用, 看人气排名是否持续上升(热度加速)或下降。

### 4. `get_sector_list` — 板块浏览

```
get_sector_list(sector_type="concept")
```

返回字段含: `sector_code`, `sector_name`, `change_pct`, `main_net_inflow`, `large_net`, `lead_stock_name/code`...

技能用法: 客户端按 `change_pct` 排序得涨幅榜, 按 `main_net_inflow` 排序得资金榜。

### 5. `get_stock_belong_sectors` — 反向查找

```
get_stock_belong_sectors("000001")
```

技能用法: 报告技能调用, 判断个股所处板块是否强势。

### 6. `generate_stock_report` — 分析报告

```
generate_stock_report(symbol)
```

返回 6 模块: `basic_info` / `trend_analysis` / `technical_indicators` / `support_resistance` / `risk_assessment` / `position_advice`

---

## 完整工作流

### 流一: 选股 → 报告
```
screen_stocks({筛选条件}) → top 5-8 候选
  ↓ for each candidate:
get_kline_local_or_net(symbol)     → 缓存K线+指标
get_rank_trend_data(symbol)        → 人气趋势
get_stock_belong_sectors(symbol)   → 板块强弱
generate_stock_report(symbol)      → 完整报告
  ↓
按 risk_reward_ratio 排序 → 推荐 2-3 只
```

### 流二: 板块 → 个股
```
get_sector_list(类型) → 客户端排序 → top 5 板块
  ↓ for each sector:
screen_stocks(sector_code=板块码, sort_by="change_pct", top_n=10)
  ↓
对龙头股调 generate_stock_report(...)
```

### 流三: 个股分析
```
screen_stocks(name_keyword="000001") → 确认股票存在
get_kline_local_or_net("000001")     → K线
generate_stock_report("000001")      → 报告
get_rank_trend_data("000001")        → 人气
get_stock_belong_sectors("000001")   → 板块
```

---

## 初始化与维护

```
init_full_data(include_sector_members=True)  // 首次, 10-20分钟
update_daily_data(include_sector_members=True)  // 每日, 5-10分钟
get_data_status()  // 随时检查数据完整性

// K线按需下载(首次分析某只股时自动触发)
get_kline_local_or_net(symbol)
```

---

## 数据库

```
stock_data.db:   stock_basic / stock_spot★ / stock_rank / stock_kline / stock_indicators★
sector_data.db:  sector_basic / sector_kline / sector_member★
```

`stock_spot` 是选股核心表，`stock_indicators` 是报告核心表，`sector_member` 实现板块↔股票双向查找。
