---
name: eastmoney-quant
description: Route A-share research requests across the Eastmoney Quant MCP data, screening, chart, report, multi-timeframe, rising-pattern, and backtest workflows. Use for broad stock-research requests or when the correct specialized workflow is unclear.
---

# Eastmoney Quant research router

Use the MCP as a local-first evidence service. Programs fetch, normalize, calculate, rank, render, and backtest; the agent interprets the evidence and states uncertainty. Never turn a score or chart label into a guaranteed price prediction.

## Start with data quality

Call `get_data_status` before market-wide work or when freshness matters.

- Compare the latest date with the latest completed A-share trading day, not the calendar date.
- For a full-market claim, require `stock.kline_coverage.full_market_ready=true` or coverage of at least 95%. Otherwise label the result partial.
- Reuse an existing database. Initialize only missing datasets; use incremental synchronization for stale data.
- State the adjustment type, data cutoff, missing fields, provider warnings, and whether intraday data is live or delayed.

## Route the request

| Request | Skill | Primary tools |
|---|---|---|
| Initialize, update, inspect, repair data | `eastmoney-quant-data-init` | `get_data_status`, `init_full_data`, `update_daily_data`, `sync_stock_kline_universe` |
| General factor/sector/name screening | `eastmoney-quant-stock-screening` | `screen_stocks`, `get_sector_list`, `scan_patterns` |
| Find rising structures and deeply review 20 stocks | `eastmoney-quant-rising-patterns` | `screen_rising_candidates`, `prepare_stock_analysis` |
| Analyze one stock | `eastmoney-quant-report-generation` | `prepare_stock_analysis`, `generate_stock_report`, `get_key_levels` |
| Compare monthly/weekly/daily/intraday structure or historical shape similarity | `eastmoney-quant-multi-timeframe` | `prepare_stock_analysis`, `get_stock_kline_period`, `find_cross_timeframe_similar_patterns` |
| Read candlestick images and attribute structure | `eastmoney-quant-chart-trend` | `render_stock_charts`, `get_key_levels` |
| Validate signals or candidate rules | `eastmoney-quant-strategy-backtest` | `backtest_pattern_strategy`, pattern backtest/optimize CLI |

## Shared analysis contract

1. Separate observed data, calculated evidence, interpretation, and conditional scenario.
2. Prefer exact dates and prices over adjectives such as “near support”.
3. Treat the five detector families as programmatic candidates: `trend_pullback`, `w_bottom`, `m_neckline`, `box_breakout`, and `ma_rebound`. In high-level output use canonical labels `neckline_reclaim` and `major_ma_rebound`; Fibonacci confluence is supporting evidence, not an independent reversal.
4. Resolve timeframe conflicts explicitly. Monthly and weekly structure constrain the daily thesis; intraday bars refine timing but do not overturn a broken higher timeframe.
5. Every bullish thesis needs confirmation conditions, invalidation level, nearby resistance, chase risk, and data-quality caveats.
6. Do not fabricate missing values, pad a candidate list, claim a causal explanation from price patterns, or issue deterministic buy/sell commands.
7. Backtest discoveries remain candidate rules. Production filters change only after out-of-sample evidence and explicit human approval.

## Tool result handling

All MCP results use `{data, meta, warnings, error}`. Check `error` first, preserve `warnings`, and cite `meta.fetched_at` or the underlying market-data cutoff when freshness matters.
