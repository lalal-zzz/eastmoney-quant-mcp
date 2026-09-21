# Stock Analysis MCP + Skills unified implementation plan

## Product objective

Deliver a local-first research loop:

```text
multi-provider acquisition
→ reliable local SQLite storage
→ market-wide K-lines and indicators
→ programmatic rising-pattern recall
→ ranked top-20 candidate set
→ monthly/weekly/daily numeric and chart review for every stock
→ current/winner/failure commonality comparison
→ event study and executable trading backtest
→ human-approved strategy revision
```

The first research horizon is 5–20 trading days. Automatic order placement, live portfolio execution, and a full-market minute-history warehouse are outside scope.

## Implemented scope

### Data reliability

- Preserve the original 15 MCP APIs and add four research APIs, for 19 total.
- Support `quick`, `research` (at least 320 daily bars per eligible stock), and resumable long-history `full` initialization.
- Reuse existing databases. Legacy K-line/indicator schemas migrate in place without copying or deleting multi-gigabyte files.
- Distinguish QFQ/HFQ/unadjusted data by adjustment type and retain provider/fetch metadata.
- Track schema, indicator and pattern-engine versions independently.
- Track coverage and errors by data type, symbol, period and adjustment.
- Support daily `none|tracked|all` K-line scope, trading-calendar checks, idempotent gap fill, resumable sync, provider throttling and circuit breaking.
- Do not claim a full-market scan below 95% eligible-symbol coverage.

### Indicators and levels

- MA5/10/20/30/60/100/120/200/250.
- RSI6/14/24, MACD, BOLL, KDJ, ATR14 and ATR%.
- Volume averages/ratios, 5/10/20/60-day returns, rolling 20/60/120-day ranges, and BIAS20/60/250.
- Confirmed pivots, structure highs/lows, trendline candidates and Fibonacci 0.382/0.5/0.618/0.786 prices.
- Indicator-only version changes recompute indicators without downloading K-lines.

### Pattern research

The engine contains five detector families: trend pullback, W-bottom, M-neckline, box breakout and major-MA rebound. The high-level layer canonicalizes legacy names and adds Fibonacci confluence as supporting evidence.

Every normalized signal exposes pattern, lifecycle stage, confirmation, score and breakdown, trend, entry status, support, resistance, neckline, invalidation, Fibonacci levels, evidence, factors and warnings.

The lifecycle is:

```text
forming → candidate → triggered → confirmed → retesting
                                      ↓
                               failed / expired
```

### Top-20 analysis

- `screen_rising_candidates` ranks the best available candidates and discloses coverage.
- `prepare_stock_analysis` returns adjustment/data quality, monthly/weekly/daily summaries, exact levels, recent patterns, sector/popularity context and chart paths.
- The rising-pattern Skill requires independent inspection of every returned monthly, weekly and daily chart.
- Program/chart disagreement is retained as evidence and lowers confidence.
- Fewer than 20 qualifying names is reported honestly; the list is never padded.

### Backtesting and governance

- Event layer: forward 5/10/20-day win rate and mean/median return by pattern/variant.
- Trading layer: next-open entry, limit execution checks, 2R target, ATR-based bounded stop, 20-day timeout, conservative same-bar ordering, costs and a 10-position equal-weight cap.
- Time-split factor commonality marks candidates for manual review.
- Reports include JSON, Markdown and trade CSV paths plus portfolio return, drawdown, payoff and Sharpe where defined.
- Backtest and optimizer code never writes production pattern filters.

## Remaining hardening

- Add a scheduler-friendly retry queue for sector-history gaps after Eastmoney circuit-breaker cooldown.
- Expand integration fixtures for provider schema changes, holidays, suspended/delisted stocks and adjustment transitions.
- Add explicit data-version/status reporting for sector-indicator coverage.
- Add portfolio benchmark/exposure series and richer slippage/liquidity models.
- Add a reviewed-rule registry with human approval, activation date, rollback metadata and walk-forward comparison.

## Acceptance criteria

- Python unit tests and Node adapter tests pass.
- MCP registry and `package.json` expose the same 20 tools.
- All eight Skills pass the skill validator and use current tool names/parameters.
- README, architecture, agent guidance and implementation plan agree on tool/skill counts and workflow.
- Old databases retain rows through migration; adjustment variants coexist.
- Market-wide outputs disclose coverage and suppress completion claims below 95%.
- Every selected stock can produce a numeric packet; missing charts are explicitly reported.
- Backtests disclose assumptions and return `rules_mutated=false`.
