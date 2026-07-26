---
name: eastmoney-quant
description: A-share stock quantitative analysis. Use when the user mentions Chinese A-share stocks (股票), stock screening (选股), sector analysis (板块分析), technical indicators (技术指标), popularity rankings (人气排名), or wants to analyze any stock with code like 000001/600000. Provides local database initialization, multi-condition stock screening, sector-to-stock workflows, and comprehensive technical analysis reports with support/resistance/risk/position advice.
---

# 东方财富量化 MCP

9 MCP tools for A-share quantitative analysis. All screening and reporting use local SQLite data after `init_full_data`.

## Tool overview

| Tool | Purpose |
|------|---------|
| `init_full_data` | First-time database setup |
| `update_daily_data` | Daily incremental refresh |
| `get_data_status` | Check database state |
| `screen_stocks` | Universal multi-condition screening (replaces search/ranking/sector filtering) |
| `get_kline_local_or_net` | Stock K-line + computed indicators |
| `get_rank_trend_data` | Historical popularity ranking trend |
| `get_sector_list` | Concept/industry sector browsing |
| `get_stock_belong_sectors` | Reverse lookup: stock → its sectors |
| `generate_stock_report` | Full analysis: trend/support-resistance/risk/position |

## Workflow

### Stock screening
```
screen_stocks(conditions, sort_by, sector_code, name_keyword)
```
18 condition keys: `min_price`, `max_price`, `min_change_pct`, `max_change_pct`, `min_volume_ratio`, `min_turnover_rate`, `max_turnover_rate`, `min_pe`, `max_pe`, `min_pb`, `max_pb`, `min_market_cap`, `max_market_cap`, `min_float_market_cap`, `min_sixty_day_change`, `min_ytd_change`, `min_amplitude`, `max_amplitude`.

`sort_by`: `change_pct` | `volume_ratio` | `turnover_rate` | `pe_dynamic` | `pb` | `total_market_cap` | `popularity_rank`

Common patterns (all via `screen_stocks`):
- Search by name: `screen_stocks(name_keyword="银行")`
- Search by code: `screen_stocks(name_keyword="000001")`
- Volume breakout: `screen_stocks({"min_change_pct":3,"min_volume_ratio":2,"max_pe":50})`
- Low PE + market cap: `screen_stocks({"max_pe":15,"min_market_cap":500,"max_pb":1.5})`
- Sector members: `screen_stocks(sector_code="BK1090", sort_by="change_pct")`
- Popularity ranking: `screen_stocks(sort_by="popularity_rank", top_n=100)`
- Full market: `screen_stocks({})` or `screen_stocks(sort_by="change_pct")`

### Sector → stocks
```
get_sector_list("concept") → pick top by change_pct → screen_stocks(sector_code="BKxxxx")
```

### Stock → report
```
get_kline_local_or_net(symbol)  →  download + cache K-line + indicators
generate_stock_report(symbol)   →  full analysis
get_rank_trend_data(symbol)     →  popularity trend
get_stock_belong_sectors(symbol) →  sector context
```

Report output: basic_info / trend_analysis / technical_indicators / support_resistance / risk_assessment / position_advice

## Database schema

```
stock_data.db:
  stock_basic ── symbol, name
  stock_spot  ── ★ screening core: 20+ fields (price/PE/PB/cap/ratio)
  stock_rank  ── daily popularity history
  stock_kline ── K-line (on demand)
  stock_indicators ─ ★ report core: MA/RSI/MACD/BOLL/KDJ/ATR

sector_data.db:
  sector_basic ── 328 sectors + capital flow
  sector_kline ── sector K-line history
  sector_member ── ★ sector↔stock bridge
```

## Init & maintenance

```
init_full_data(include_sector_members=True)   # first time, ~10min
update_daily_data(include_sector_members=True) # daily, ~2-5min
get_data_status()                              # check integrity
```

## Sub-skills

See detailed workflows in:
- `eastmoney-quant-data-init` — database setup guide
- `eastmoney-quant-stock-screening` — screening condition templates
- `eastmoney-quant-report-generation` — report interpretation + formatting
