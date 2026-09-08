---
name: eastmoney-quant-rising-patterns
description: Rank rising-structure A-share candidates and deeply review every candidate with monthly, weekly, and daily numeric and chart evidence. Use for 上涨形态选股, W底, 趋势回调, 颈线收复, 平台突破, 大均线反弹, 斐波那契共振, or requests to find and analyze the top 20 stocks.
---

# Rising-pattern screening and 20-stock deep review

The program is a recall-and-ranking layer. The agent must independently interpret every returned stock; a program label is evidence, not the conclusion.

## Required workflow

1. Call `get_data_status`. Require the latest completed trading day and `full_market_ready=true` for a full-market claim. If coverage is low, update or explicitly limit the universe.
2. Call `screen_rising_candidates(top_n=20, lookback_days=20, strict=true)`.
3. Preserve `universe_size`, `scanned`, `skipped`, `coverage_ratio`, score breakdowns, stages, and warnings.
4. Call `prepare_stock_analysis(symbol, days=500, include_chart=true)` for every returned candidate.
5. Actually inspect monthly → weekly → daily images for every candidate. If an image is unavailable, perform the numeric review and mark visual confirmation missing.
6. Compare the detector output with the charts and exact values. State agreement, partial agreement, or conflict.
7. Produce one analysis card per stock, then a 20-stock comparison and commonality analysis. If fewer than 20 qualify, analyze all returned names and do not pad the list.

## Structure lifecycle

Use `forming → candidate → triggered → confirmed → retesting`, with terminal `failed` or `expired`. Do not call an unconfirmed right bottom or MA touch “completed”.

- `w_bottom`: give both low dates/prices, deviation, neckline price, breakout volume, and retest status.
- `trend_pullback`: identify the prior impulse, pullback start/end, retracement percentage, volume contraction, and whether higher highs/higher lows survive.
- `neckline_reclaim`: canonical form of `m_neckline`; distinguish reclaim-and-hold from a failed rebound under the neckline.
- `box_breakout`: give box dates/range, upper boundary, breakout date, volume multiple, and return-inside-box risk.
- `major_ma_rebound`: canonical form of `ma_rebound`; identify MA120/250 price and call it a rebound unless weekly structure also reverses.
- `fibonacci_confluence`: supporting evidence only; list the actual 0.382/0.5/0.618/0.786 prices and the independent level that creates confluence.

## Per-stock evidence card

Each card must include:

- symbol/name, adjustment type, first/last data date, bar count, stale flag;
- monthly/weekly/daily trend and the exact moving-average values used;
- current phase: advancing, pullback, basing, rebound, distribution, or acceleration;
- primary structure, lifecycle stage, program/chart agreement, and confidence with reasons;
- latest meaningful swing-low/high dates and prices, swing return, and current retracement;
- MA20/60/120/250, trendline, neckline, structural high/low, and Fibonacci levels where available;
- 5/20-day volume ratios and whether breakout expansion or pullback contraction is actually present;
- nearest support, resistance, invalidation, and the confirmation still required;
- sector trend/capital-flow freshness, popularity trend, 5–20-day risks, and chase distance.

Never infer a precise line or wave point that is not supported by the packet or visible chart. When plausible pivot choices differ, show the main and alternate interpretation.

## Ranking and commonality

Rank only after all cards are complete. Prefer confirmed structures with aligned weekly/monthly context and healthy volume over candidates, late acceleration, and countertrend rebounds. Keep the original program score visible so readers can distinguish model ranking from the agent's reviewed ranking.

Separate four commonality sets:

1. traits in the current candidates;
2. traits in historical winners;
3. traits in historical failures;
4. differences between the current set and historical winners.

Validate proposed common factors with `backtest_pattern_strategy(mode="both")`. Commonality and optimizer output are candidate rules only; do not modify `PATTERN_FILTERS` without out-of-sample support and explicit human approval.

End with data limitations and a non-advisory statement. Use conditional scenarios, not guaranteed returns or direct trade instructions.
