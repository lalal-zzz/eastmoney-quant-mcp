---
name: eastmoney-quant-stock-screening
description: Multi-condition A-share stock screening using local database. Use when the user wants to find stocks matching specific criteria (price, PE, PB, market cap, volume, turnover, sector, name keyword), rank stocks by any metric, or discover stocks within a specific sector. Triggered by phrases like "选股", "筛选", "帮我找", "有什么股票", "板块内选股", "涨幅榜", "人气排名". All screening uses a single tool: screen_stocks.
---

# Stock screening

Uses `screen_stocks` as the universal query tool. All searches, rankings, sector filtering, and condition combinations go through this one tool.

## The tool

```
screen_stocks(conditions, top_n=50, sort_by="change_pct", sector_code=None, name_keyword=None)
```

## Condition keys

All optional — combine freely in a JSON object:

| Key | Meaning | Example |
|-----|---------|---------|
| `min_price` / `max_price` | Price range | `{"min_price":10,"max_price":50}` |
| `min_change_pct` / `max_change_pct` | Change % | `{"min_change_pct":3,"max_change_pct":9.5}` |
| `min_volume_ratio` | Min volume ratio | `{"min_volume_ratio":1.5}` |
| `min_turnover_rate` / `max_turnover_rate` | Turnover rate | `{"min_turnover_rate":5}` |
| `min_pe` / `max_pe` | PE range | `{"max_pe":30}` |
| `min_pb` / `max_pb` | PB range | `{"max_pb":3}` |
| `min_market_cap` / `max_market_cap` | Market cap (100M CNY) | `{"min_market_cap":100}` |
| `min_float_market_cap` | Float cap (100M CNY) | `{"min_float_market_cap":50}` |
| `min_sixty_day_change` | 60-day change | `{"min_sixty_day_change":0}` |
| `min_ytd_change` | YTD change | `{"min_ytd_change":10}` |
| `min_amplitude` / `max_amplitude` | Amplitude | `{"min_amplitude":3}` |

## sort_by options

`change_pct` | `volume_ratio` | `turnover_rate` | `pe_dynamic` | `pb` | `total_market_cap` | `latest_price` | `volume` | `amplitude` | `popularity_rank`

## Recipe book

### Search & browse
- Search "银行": `screen_stocks(name_keyword="银行")`
- Search "000001": `screen_stocks(name_keyword="000001")` (matches both name and code)
- Full market snapshot: `screen_stocks({})`

### Rankings (all via sort_by)
- Top gainers: `screen_stocks(sort_by="change_pct")`
- Most active: `screen_stocks({"min_change_pct":0}, sort_by="turnover_rate")`
- Volume leaders: `screen_stocks({}, sort_by="volume")`
- Popularity: `screen_stocks(sort_by="popularity_rank")` (ascending, lower = hotter)
- Cheapest PE: `screen_stocks({"max_pe":500}, sort_by="pe_dynamic")`

### Pattern-based (condition combinations)
- Volume breakout: `{"min_change_pct":3,"min_volume_ratio":2,"max_pe":50}`
- Low-PE blue chips: `{"max_pe":15,"max_pb":1.5,"min_market_cap":500}`
- Strong small-caps: `{"min_change_pct":5,"min_turnover_rate":10,"max_market_cap":100}`
- Oversold bounce: `{"max_change_pct":-5,"min_turnover_rate":2,"max_pe":30}`
- Quality pullback: `{"max_change_pct":-2,"max_pe":20,"min_sixty_day_change":10}`
- Hot momentum: `{"min_change_pct":2}`, sort_by `popularity_rank`

### Sector-driven
- View sector members: `screen_stocks(sector_code="BK1090")`
- Screen within sector: `screen_stocks({"max_pe":30}, sector_code="BK1090", sort_by="change_pct")`
- Find sector code: `get_sector_list("concept")` → search for name → use code

## Post-screening analysis

For the top 5-10 results from any screen, do:

1. `get_kline_local_or_net(symbol)` — download K-line if not cached
2. `generate_stock_report(symbol)` — full analysis report
3. `get_rank_trend_data(symbol)` — popularity trend
4. `get_stock_belong_sectors(symbol)` — sector context
5. `get_stock_kline_period(symbol, period="60")` — optional intraday structure check (1/5/15/30/60-min, network real-time)

Sort final candidates by `risk_reward_ratio` from the report.

## Decision principles

1. Screen broad first, narrow down: use `screen_stocks` with loose conditions → refine → deep dive
2. Default `top_n=50`, warn user if they ask for >100
3. Cross-verify: technical + capital flow (sector) + popularity + valuation
4. After screening, always offer to generate reports for top candidates
