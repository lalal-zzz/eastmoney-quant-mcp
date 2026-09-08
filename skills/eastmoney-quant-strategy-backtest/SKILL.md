---
name: eastmoney-quant-strategy-backtest
description: Run and interpret event studies, executable pattern-strategy backtests, factor commonality tests, and time-split validation for Eastmoney Quant. Use for 回测, 胜率, 历史验证, 参数优化, 共性检验, drawdown, Sharpe, or testing a proposed screening rule.
---

# Pattern strategy backtesting

Backtests test a precisely defined rule under explicit assumptions. They do not validate a visual story or guarantee live performance.

## Choose the layer

- `backtest_pattern_strategy(mode="event")`: forward 5/10/20-day event outcomes by detector and variant.
- `backtest_pattern_strategy(mode="trading")`: executable trade simulation.
- `backtest_pattern_strategy(mode="both")`: preferred when evaluating a candidate rule because event and portfolio results answer different questions.
- CLI `pattern-backtest`: detailed factor/year/regime tables and reusable signal CSV.
- CLI `pattern-optimize`: beam-search candidate thresholds from an existing signal cache.

Use canonical high-level names in prose but pass detector names accepted by the engine when required: `trend_pullback`, `w_bottom`, `m_neckline`, `box_breakout`, `ma_rebound`.

## Record the contract

The callable trading simulation currently assumes:

- signal detection without unconfirmed future pivots;
- entry at the next trading day's open;
- skip a one-price limit-up entry;
- stop based on two ATR, bounded to 2%–8% risk;
- 2R target, maximum 20 holding days;
- conservative stop-first handling if stop and target occur in one bar;
- one-price limit-down bars cannot execute the stop;
- configurable buy/sell costs;
- at most 10 concurrent equal-weight positions and no duplicate active symbol.

Report these assumptions beside the result. Do not silently compare results produced under different costs, dates, universes, or exits.

## Validation requirements

1. Check K-line coverage, adjustment, universe composition, delisted-stock representation, and date range.
2. Use a chronological split such as the callable default `split="2022-01-01"`; do not randomly mix future and past.
3. Report train and out-of-sample sample counts, not only rates.
4. Require enough observations per pattern, year, and factor bucket; label small samples inconclusive.
5. Compare win rate, mean/median return, payoff ratio, total/annualized return, maximum drawdown, Sharpe, turnover/exposure assumptions, and stability across years.
6. Discuss survivorship, suspension/limit execution, corporate-action, liquidity, slippage, overlapping-signal, and multiple-testing bias.
7. Treat a large train/test gap or unstable yearly result as evidence against the rule. Do not use a universal numeric pass threshold without context.

## Commonality and optimization

Separate current-candidate traits, historical winners, and historical failures. A factor is interesting only when its direction persists out of sample with adequate counts and economically meaningful improvement after costs.

Optimizer/commonality output must remain a versioned candidate:

1. save the proposed condition and rationale;
2. rerun on untouched out-of-sample data;
3. compare against the unchanged baseline;
4. inspect failure regimes and parameter sensitivity;
5. request explicit human approval before changing production filters.

Never mutate `PATTERN_FILTERS`, `PATTERN_STRICT_FILTERS`, or live selection behavior automatically.

## Output

Return the universe and period, data coverage, signal/trade counts, assumptions, event table, portfolio metrics, train/test comparison, yearly/regime stability, commonality candidates, limitations, report/CSV paths, and a clear `rules_mutated=false` statement.
