---
name: eastmoney-quant-chart-trend
description: Render and inspect daily, weekly, and monthly A-share candlestick charts to attribute trend, W-bottom, neckline, box, rebound, and Fibonacci structure. Use for 看图, 画K线, 趋势线, 波段结构, W底, 颈线, 箱体, 波浪, or visual confirmation of a programmatic signal.
---

# Candlestick chart structure review

Charts are evidence to inspect, not decorative output. Automatic lines are hypotheses derived from selected pivots and must be checked against prices and dates.

## Workflow

1. Check data freshness and adjustment.
2. Call `render_stock_charts(symbol, days=500)` or use chart paths from `prepare_stock_analysis`.
3. Inspect the monthly, weekly, and daily images in that order.
4. Cross-check visual observations with `get_key_levels` and the numeric packet.
5. Report the primary interpretation, a plausible alternate interpretation, confirmation, invalidation, and chart limitations.

If chart rendering fails, do not claim visual confirmation. Continue with numeric OHLCV analysis and state that the image was unavailable.

## What to inspect

- Trend structure: pivot dates/prices, higher highs/lows or lower highs/lows, and whether a line has multiple meaningful touches.
- W-bottom: two low dates/prices, tolerance relative to volatility, neckline, right-bottom volume, breakout and retest.
- Neckline reclaim: prior top/neckline construction, reclaim close, volume, and hold/failure.
- Box: start/end, upper/lower prices, contraction, breakout close, volume multiple, and return inside.
- Major-MA rebound: actual MA120/250 value and higher-timeframe direction; label rebound versus reversal.
- Fibonacci: selected swing anchors and actual 0.382/0.5/0.618/0.786 prices; require independent confluence.
- Volume: expansion on impulse/breakout and contraction on pullback, using numeric ratios where possible.

## Drawing and wave cautions

- A line's apparent screen angle depends on chart aspect ratio and axis scaling. Do not classify strength from visual degrees such as 25° or 45°.
- A two-point trendline is fragile. State touch count and alternate pivot choice.
- Wave counts are hypotheses, not facts. Show anchor dates/prices, invalidation, and an alternate count when ambiguity is material.
- Trendline, pattern, volume, volatility, and higher-timeframe structure are jointly evaluated; no single overlay is an absolute judge.

## Output card

Include symbol/name, chart cutoff, adjustment, observed monthly/weekly/daily structure, selected pivots, program-versus-chart agreement, exact neckline/trendline/box/Fibonacci values, volume evidence, primary/alternate attribution, confirmation condition, invalidation, nearby resistance, and confidence reasons.

Use conditional language and include a non-advisory statement.
