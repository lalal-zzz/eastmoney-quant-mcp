---
name: eastmoney-quant-multi-timeframe
description: Analyze one or more A-shares across monthly, weekly, daily, 60-minute, and 15/30-minute bars, resolving timeframe conflicts with exact numeric evidence. Use for 多周期, 月周日联立, 60分钟, 分时, 周期共振, trend hierarchy, or entry-timing context.
---

# Multi-timeframe structure analysis

Use higher timeframes to define context, daily bars to define the research setup, and intraday bars only to refine timing. “Resonance” means independently measured evidence agrees; it is not a fixed win rate.

## Data sources and completeness

- `prepare_stock_analysis` resamples the local QFQ daily series into monthly and weekly evidence and provides matching charts and key levels.
- `get_stock_kline_period(period="103"|"102"|"101")` provides current network month/week/day bars when an independent refresh is needed.
- `get_stock_kline_period(period="60"|"30"|"15")` provides intraday bars. State retrieval time and whether the latest bar is incomplete.
- `find_cross_timeframe_similar_patterns` compares normalized price-volume paths across different periods and window lengths. Treat its score as geometric similarity, then inspect each match's forward return, maximum gain, and drawdown separately.
- `get_key_levels` returns the daily `market_structure` plus independently resampled weekly/monthly snapshots in `higher_timeframe_structure`. Each higher-timeframe snapshot rebuilds pivots, lines, channels, W/M and directional position evidence from its own OHLCV bars. Its structural scale is not a fixed synonym for monthly/weekly/daily timeframe.
- Do not compare differently adjusted series as if their prices were identical. Disclose adjustment and provider.

For cross-timeframe analogy requests, set one common `query_bars` horizon for the whole comparison. When `candidate_window_bars` is omitted every candidate uses exactly that same bar count; run 30-bar and 100-bar studies separately rather than mixing their scores. Use `candidate_window_bars` only when the user explicitly asks for temporal stretching. The default `candidate_scope=market, search_mode=history, max_symbols=0, search_bars=0` compares the target's latest window with every same-length historical window from all locally covered stocks and all locally available history. The engine vectorizes a price-path prefilter before fully scoring the retained candidates. Report `outcome_probabilities` for 5/10/20-bar horizons, including sample size, raw and similarity-weighted up/sideways/down percentages, threshold, and confidence. Use `search_bars` to impose a recent-history limit when runtime matters, `candidate_scope=self` for one-stock history, and `candidate_scope=symbols` for a named pool. Do not describe a match as predictive; report the historical outcome dispersion and exact matched dates.

## Required top-down pass

### Monthly

Identify long-cycle direction, major pivot range, price relative to MA20/60 when enough bars exist, and whether the stock is in expansion, contraction, base, or long decline. Do not call a low price a valuation bottom without fundamental evidence.
Monthly W/M, trendlines and Fibonacci anchors are independent large structures. Use the last real trading day stored as the cutoff; do not confirm a monthly structure from an unfinished calendar month.

### Weekly

Identify higher-high/higher-low or lower-high/lower-low structure, weekly MA5/10/20/60 values, recent swing dates/prices, and whether the latest move is impulse, pullback, or rebound.
Weekly W/M and channels must be detected from weekly OHLCV rather than promoted from a daily pattern. Treat the current unfinished week as preview evidence until its close.

### Daily

Identify the active detector family and lifecycle, MA20/60/120/250 values, volume ratios, ATR%, recent returns, and exact confirmation/invalidation. From `market_structure`, report a line as confirmed only after its third independent touch; distinguish parallel channels, horizontal ranges, non-symmetric W/M, and each Fibonacci anchor scale.

### Intraday, when requested

Use 60-minute for the short swing and 15/30-minute for execution context. Check structure and volume rather than relying on a single MACD/KDJ cross. An intraday signal cannot repair a broken weekly thesis.

## Conflict resolution

| Higher timeframe | Daily | Interpretation |
|---|---|---|
| rising | confirmed continuation | aligned advancing structure |
| rising | pullback candidate | potentially constructive; wait for daily confirmation |
| falling | daily rebound | countertrend rebound until weekly structure changes |
| range | breakout candidate | require close/volume/retest evidence |
| rising | late acceleration/divergence | trend intact but chase and exhaustion risk elevated |

If monthly and weekly disagree, state both. Do not collapse them into an arbitrary score without showing the components.

## Structure and position rules

- Timeframe and structure scale are separate. An hourly and daily swing may each have Fibonacci zones; always name the timeframe, scale, and anchors.
- Retracement is A/B-based. Projection and measured move require A/B/C; `position_ratio` from A and `projection_ratio` from C are different quantities.
- Higher-timeframe and lower-timeframe evidence derived from the same underlying swing is correlated. Do not count the same A/B path twice merely because it was resampled.
- Wave parsing is not implemented in the current structure engine. Use higher-timeframe context, Pivot/Leg/Segment evidence, and conditional scenarios without assigning Elliott degrees.
- Current MCP tools do not create persistent background alert subscriptions. A key-level result is a snapshot, not a promise to monitor it.

## Numeric output

For each timeframe provide cutoff, bars, close, trend definition, moving averages, recent return, range, and selected pivots. Then provide:

- agreement/conflict matrix;
- primary and alternate structure interpretation;
- exact support, resistance, confirmation, and invalidation;
- volume/volatility evidence;
- data and incomplete-bar warnings;
- conditional bull/base/bear scenarios.

Do not attach universal success percentages, fixed stop percentages, or position sizes to a resonance label. Those require strategy-specific backtest evidence and user-specific constraints.
