---
name: eastmoney-quant-chart-trend
description: Render and inspect A-share candlestick charts for confirmed trendlines, parallel or horizontal channels, non-symmetric W/M structures, key levels, and directional Fibonacci position. Use for 看图, 画K线, 趋势线, 通道, 横盘箱体, W底, M顶, 颈线, or visual confirmation of a programmatic signal.
---

# Candlestick chart structure review

Charts are evidence to inspect, not decorative output. Automatic lines are hypotheses derived from selected pivots and must be checked against prices and dates.

## Workflow

1. Check data freshness and adjustment.
2. Call `render_stock_charts(symbol, days=500)` or use chart paths from `prepare_stock_analysis`.
3. Inspect the monthly, weekly, and daily images in that order.
4. Cross-check visual observations with `get_key_levels`. Prefer its `market_structure` snapshot for pivots, legs, line status, channels, ranges, W/M skeletons, anchors, retracements, projections, and zones.
5. Report the primary interpretation, a plausible alternate interpretation, confirmation, invalidation, and chart limitations.

If chart rendering fails, do not claim visual confirmation. Continue with numeric OHLCV analysis and state that the image was unavailable.

## What to inspect

- Trend structure: two confirmed pivots define a candidate line; a later independent third touch confirms it. Report anchor/touch dates, current line value, confirmation date, broken status, and scale. Do not move the first two anchors to fit the third.
- Channels: distinguish a confirmed baseline from the parallel opposite boundary. Report lower/upper touches separately; one confirmed side does not prove a two-sided channel.
- Horizontal range: give both boundary zones and their independent retests, start/end, current location, breakout direction, and return-inside risk.
- W-bottom and M-top: use the non-symmetric skeletons in `market_structure.double_patterns`; report left/middle/right dates, unequal durations, endpoint deviation, neckline, lifecycle, breakout/breakdown, and invalidation. `m_top` is bearish breakdown evidence; legacy `m_neckline` means neckline-hold/reclaim and is a different result.
- Neckline reclaim: prior top/neckline construction, reclaim close, volume, and hold/failure.
- Box: start/end, upper/lower prices, contraction, breakout close, volume multiple, and return inside.
- Major-MA rebound: actual MA120/250 value and higher-timeframe direction; label rebound versus reversal.
- Fibonacci: name the anchor scale and A→B swing. Retracement uses A/B; projection requires A/B/C. Report `retracement_ratio`, `position_ratio`, `phase`, and actual zones. A ratio is relative position; its support/resistance role requires path and reaction evidence.
- Projection: distinguish the A-based position from the C-based projection. A 1.0 measured move is the same evidence as a 1.0 projection from the same anchors.
- Confluence: use dependency groups/families from the snapshot; do not count several labels derived from the same swing as independent evidence.
- Volume: expansion on impulse/breakout and contraction on pullback, using numeric ratios where possible.

## Drawing and interpretation cautions

- A line's apparent screen angle depends on chart aspect ratio and axis scaling. Do not classify strength from visual degrees such as 25° or 45°.
- A two-point line is a candidate. Call it confirmed only when the snapshot records a third independent touch.
- Check the full candle range from the first anchor through the cutoff. A wick crossing the ATR break buffer invalidates the geometric trendline or channel even when the close remains inside.
- The new engine deliberately returns `wave_analysis=null`. Do not add Elliott labels from visual inspection. Describe observed Pivot/Leg/Segment structure instead.
- Trendline, pattern, volume, volatility, and higher-timeframe structure are jointly evaluated; no single overlay is an absolute judge.

## Output card

Include symbol/name, chart cutoff, adjustment, observed monthly/weekly/daily structure, selected scale and pivots, program-versus-chart agreement, exact trendline/channel/range/neckline/Fibonacci zones, movement phase, independent evidence groups, volume evidence, confirmation, invalidation, nearby resistance, and confidence reasons.

Treat a diagonal as local: two anchors define it and a later independent third touch confirms it. Respect its reported validity window and anchor span. Once the structure is `converted`/`horizontal_level`, stop describing or drawing it as a trendline; report the retained price as horizontal support or resistance.
For weekly and monthly visual review, load the available long daily history before resampling. A short daily display window must not limit the higher-timeframe structure history.
Evaluate each daily snapshot with its `as_of` cutoff. A touch that appears later cannot be used to confirm an earlier day's line. For channels, report `construction`: independently confirmed parallel trendlines or a fixed translation of one confirmed baseline with independent opposite-side tests.

Use conditional language and include a non-advisory statement.
