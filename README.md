[English](README.md) | [中文](README.zh-CN.md)

# Eastmoney Intelligent Research MCP

[![npm version](https://img.shields.io/npm/v/eastmoney-quant-mcp.svg)](https://www.npmjs.com/package/eastmoney-quant-mcp)
[![Python](https://img.shields.io/pypi/pyversions/eastmoney-quant-mcp.svg)](https://pypi.org/project/eastmoney-quant-mcp/)
[![License](https://img.shields.io/github/license/lalal-zzz/eastmoney-quant-mcp)](LICENSE)

**Eastmoney Intelligent Research MCP** is a local-first A-share research workbench for AI Agents. It turns Eastmoney public APIs and complementary market providers into reusable local SQLite evidence: market data, indicators, sector flow, chart structure, multi-timeframe review, research reports, and reproducible backtests.

It is designed for a complete research loop: **check data quality → build a candidate universe → inspect numeric and chart evidence → compare scenarios → validate rules with out-of-sample backtests**. It does not provide guaranteed predictions or automatic trading instructions.

See the [unified implementation plan](IMPLEMENTATION_PLAN.md) for the data, rising-pattern, per-stock AI review, and backtest contracts.

## Agent setup (npm)

```bash
npm install -g eastmoney-quant-mcp
eastmoney-quant install --agents auto   # auto-configure detected Agents + copy skills
eastmoney-quant setup --data-root "D:/MarketData"   # choose where SQLite data lives
eastmoney-quant doctor                  # verify runtime / config / agent status
```

**Supported Agents** (auto-detected and configured by `install --agents auto`):

| Agent | Config written | Skills installed |
|-------|----------------|------------------|
| Claude Code | `~/.claude.json` | ✅ `~/.claude/skills/` |
| Codex | `~/.codex/config.toml` | ✅ `~/.codex/skills/` |
| Cursor | `~/.cursor/mcp.json` | — (tools are self-describing) |
| VS Code Copilot | VS Code user `mcp.json` | — |
| Qoder | `~/.qoder/mcp.json` | ✅ `~/.qoder/skills/` |

The installer manages an isolated Python environment with [`uv`](https://docs.astral.sh/uv/); install `uv` first if it is not already available. It asks before changing any Agent configuration and creates a backup (restorable via `eastmoney-quant uninstall`). For OpenCode and other MCP clients, a manual JSON template is printed by `eastmoney-quant install --agents auto --dry-run`.

The data directory is user-owned and is never placed in the npm package directory. Settings resolve as **env var → `~/.eastmoney-quant/config.toml` → default**, so existing `EASTMONEY_STOCK_DATA_DIR`, `EASTMONEY_SECTOR_DATA_DIR`, and `EASTMONEY_PYTHON` environment variables keep working and override the config file.

## Core Capabilities

| Capability | Details |
|------------|---------|
| Market Data | Full listed A-share universe: price / change% / PE / PB / market cap / volume ratio / turnover |
| K-lines | Daily OHLCV with forward/backward/no adjustment |
| Indicators | MA5/10/20/30/60/100/120/200/250, RSI, MACD, BOLL, KDJ, ATR%, volume ratios, returns, rolling ranges and BIAS |
| Popularity | Eastmoney real-time sentiment rankings + historical trends (rolling 1-year Guba rank) |
| Sectors | Concept and industry boards with quotes, capital flow, members, K-lines and indicators |
| Screening | 18 composable conditions: price range / PE / PB / cap / change% / volume / turnover / sector filter |
| Pattern Research | Five detector families plus canonical neckline-reclaim / major-MA-rebound labels and Fibonacci confluence evidence |
| Deep Review | Rank 20 candidates, then inspect every monthly/weekly/daily numeric and chart packet |
| Backtesting | 5/10/20-day event studies and next-open trading simulation with costs and out-of-sample checks |

---

## Quick Install

```bash
# Claude Code (recommended)
claude mcp add eastmoney-quant -- npx eastmoney-quant-mcp

# or npm global
npm install -g eastmoney-quant-mcp

# or pip
pip install eastmoney-quant-mcp
```

**Requirements**: Python >= 3.10 | Node.js >= 18

---

## Data Details

### Stock Market Data

| Category | Fields |
|----------|--------|
| Basics | Latest price, open, previous close, high, low |
| Change | Change%, change amount, amplitude, velocity |
| Volume | Volume, turnover amount |
| Activity | Volume ratio, turnover rate |
| Valuation | Dynamic PE, PB, TTM PE |
| Market Cap | Total market cap, circulating market cap |
| Trend | 60-day change%, YTD change% |
| Fund Flow | Net major capital inflow |

### K-line Data

| Category | Details |
|----------|---------|
| Daily K-line | Open, high, low, close, volume, amount |
| Adjustment | Forward (qfq) / backward (hfq) / none |
| Extra Fields | Change%, turnover rate, amplitude |
| Identity | `symbol + date + adjust_type`, with source and fetch time |
| Compatibility | Existing databases migrate in place; legacy QFQ data is reused without a bulk copy |

### Technical Indicators (auto-calculated)

| Category | Indicators |
|----------|------------|
| Moving Avg | MA5, MA10, MA20, MA30, MA60, MA100, MA120, MA200, MA250 |
| RSI | RSI6, RSI14, RSI24 |
| MACD | DIF, DEA, MACD histogram |
| Bollinger | Upper, middle, lower bands |
| KDJ | K, D, J values |
| Volatility | ATR14 and ATR% |
| Volume | VOL_MA5/10/20 and 5/20-day volume ratios |
| Returns & Range | 5/10/20/60-day returns and 20/60/120-day highs/lows |
| Bias | BIAS20, BIAS60, BIAS250 |

### Popularity Rankings

| Category | Details |
|----------|---------|
| Real-time | Eastmoney popularity board (rank, price, change%, turnover rate) |
| History Trend | Query N-day ranking trend for any stock (AES-decrypted rolling year data) |

### Sector Data

| Category | Details |
|----------|---------|
| Sector List | Concept (~400) + Industry (~80) sectors |
| Quotes | Index level, change% |
| Capital Flow | Net inflow, super-large, large, medium, small net inflow (with %) |
| Leaders | Sector leading stock |
| K-line | Historical sector index K-line (single-source Eastmoney) |
| Members | Member quotes, turnover, volume ratio, PE, PB |

### Analysis Reports

| Section | Content |
|---------|---------|
| Overview | Price, change%, PE, PB, market cap, turnover rate |
| Trend | MA arrangement, 5/10/20/60-day change%, direction assessment |
| Indicators | RSI status, MACD golden/death cross, KDJ overbought/oversold, BOLL pos, ATR |
| S&R Levels | Ranked support and resistance levels from MAs and BOLL bands |
| Risk Assessment | Overbought/oversold, volatility, valuation, liquidity, and breakdown risk |
| Scenarios | Conditional confirmation, invalidation, support/resistance and risk/reward assumptions |

---

## MCP Tools (20 tools)

| Tool | Module | Purpose |
|------|--------|---------|
| `init_full_data` | `data_manager` | `quick`, `research` (320-bar universe), or long-history `full` initialization; legacy `quick` calls remain compatible |
| `update_daily_data` | `data_manager` | Daily incremental refresh with `stock_kline_mode=none|tracked|all` |
| `get_data_status` | `data_manager` | Local DB status (row counts / last update / paths) |
| `screen_stocks` | `data_manager` | Universal screening: 18 conditions + sector filter + name search + sort |
| `get_kline_local_or_net` | `data_manager` | Daily K-line, local-first with cached technical indicators |
| `get_stock_kline_period` | `stock_data` | Multi-period K-line (1/5/15/30/60m, day/week/month, real-time) |
| `get_rank_trend_data` | `data_manager` | Historical popularity ranking trend (N days) |
| `get_sector_list` | `sector_data` | Concept/industry sector list with capital flow |
| `get_stock_belong_sectors` | `data_manager` | Reverse lookup: stock $\rightarrow$ sectors |
| `generate_stock_report` | `analysis` | Technical report: trend / support & resistance / risk / position |
| `render_stock_charts` | `charting` | Render daily/weekly/monthly candlestick PNGs with auto trendlines (chart extra) |
| `scan_patterns` | `strategies/patterns` | Stock chart-pattern scan (normal or strict filter) |
| `scan_sector_patterns` | `strategies/patterns` | Sector chart-pattern scan (concept/industry or symbols) |
| `get_pattern_history` | `strategies/patterns` | Historical pattern signals for one symbol (stock/sector) |
| `get_key_levels` | `strategies/patterns` | Current key levels: MA system / Fibonacci / structure (highs/lows) |
| `sync_stock_kline_universe` | `data/sync` | Research-mode universe K-line and indicator synchronization with coverage reporting |
| `screen_rising_candidates` | `tools/research` | Rank the top 20 rising-pattern candidates with multi-timeframe evidence |
| `prepare_stock_analysis` | `tools/research` | Build the monthly/weekly/daily numeric and chart packet for per-stock AI review |
| `find_cross_timeframe_similar_patterns` | `strategies/similarity` | Compare the latest N bars with all historical N-bar windows and estimate conditional outcome probabilities |
| `backtest_pattern_strategy` | `strategies/trading_backtest` | Event study plus executable 5–20 day trading simulation |

### MCP call contract

Every tool publishes a JSON Schema. The server validates required and unknown fields, basic types, enum values, and numeric ranges. Results use `{data, meta, warnings, error}`: check `error` first, preserve `warnings`, and use both `meta` and the data cutoff date for freshness. The server does not provide persistent monitoring, push notifications, or deterministic buy/sell decisions.

Ships with **8 Agent Skills** (installed automatically by `eastmoney-quant install`):

| Skill | Purpose |
|-------|---------|
| `eastmoney-quant` | Main index — check data readiness before research |
| `eastmoney-quant-data-init` | Existing-data reuse, initialization, coverage-aware updates and troubleshooting |
| `eastmoney-quant-stock-screening` | Composing screening conditions and workflows |
| `eastmoney-quant-report-generation` | Evidence-based single-stock report and conditional scenarios |
| `eastmoney-quant-multi-timeframe` | Monthly/weekly/daily/intraday analysis and conflict resolution |
| `eastmoney-quant-strategy-backtest` | Chart pattern backtesting and parameter optimization |
| `eastmoney-quant-chart-trend` | Per-stock visual structure attribution with pivot and line uncertainty checks |
| `eastmoney-quant-rising-patterns` | Rank 20 candidates, deeply review every monthly/weekly/daily chart, and summarize common traits |

### What each Skill delivers

The Skills are output-oriented: each one turns MCP tool results into a consistent, reviewable artifact rather than a loose paragraph.

| Skill | Result view | Typical result contents |
|-------|-------------|-------------------------|
| `eastmoney-quant` | Research route card | Chosen workflow, data-quality gate, tool chain, warnings, and next action |
| `eastmoney-quant-data-init` | Data health report | Expected trading date, latest date, per-dataset coverage, successes/failures, provider warnings, remaining gaps |
| `eastmoney-quant-stock-screening` | Sortable candidate table | Code/name, cutoff, filters, pattern/stage, score components, sector context, support/resistance/invalidation, rejected or missing-data notes |
| `eastmoney-quant-report-generation` | Single-stock evidence report | Conclusion/confidence, data block, monthly/weekly/daily evidence, key-level table, scenarios, risks, limitations |
| `eastmoney-quant-multi-timeframe` | Timeframe comparison matrix | Monthly/weekly/daily/intraday metrics, agreement/conflict matrix, primary/alternate view, exact confirmation and invalidation levels |
| `eastmoney-quant-chart-trend` | Chart review card | Chart cutoff, pivots, trendlines/channels/ranges/W-M/Fibonacci zones, program-vs-chart agreement, volume evidence |
| `eastmoney-quant-rising-patterns` | Candidate cards + comparison | One evidence card per returned stock, reviewed ranking, current-vs-history commonality, and coverage caveats |
| `eastmoney-quant-strategy-backtest` | Backtest result pack | Universe/period, coverage, signal/trade counts, assumptions, event and portfolio metrics, train/test and yearly stability, report/CSV paths |

Example compact result card:

```text
000001 平安银行 · 2026-09-17 · qfq · 486 daily bars
Structure: weekly pullback / daily neckline reclaim (candidate → triggered)
Evidence: close 12.34 | MA20 12.10 | neckline 12.28 | volume 1.42x
Confirm: daily close above 12.28 and hold; Invalidate: close below 11.86
Warnings: sector data delayed; chart confirmation available
```

Exact values, dates, coverage and warnings always come from the current MCP response; the example above only illustrates the presentation format.

---

## Research workflow

```text
get_data_status
  → update or fill only missing coverage
  → screen_rising_candidates(top_n=20)
  → prepare_stock_analysis for every returned stock
  → inspect monthly, weekly and daily charts
  → compare reviewed candidates and extract common traits
  → backtest_pattern_strategy(mode="both")
  → human approval before any production-rule change
```

A full-market claim requires at least 95% eligible-stock K-line coverage. The five low-level pattern detectors are `trend_pullback`, `w_bottom`, `m_neckline`, `box_breakout`, and `ma_rebound`. High-level reports rename two of them to `neckline_reclaim` and `major_ma_rebound`; `fibonacci_confluence` is supporting evidence rather than a standalone reversal detector.

## Unified CLI

In addition to the MCP server, a unified CLI is provided for database maintenance, backfilling, and quantitative strategy backtesting:

```bash
# Rebuild local databases with dry-run preview
python -m eastmoney_quant_mcp.cli rebuild --dry-run
python -m eastmoney_quant_mcp.cli rebuild --workers 8 --with-sectors

# Auto-detect and backfill historical data gaps
python -m eastmoney_quant_mcp.cli backfill --start 2026-01-01

# Daily evening capture after market close
python -m eastmoney_quant_mcp.cli daily-capture

# Cleanup database redundancy and VACUUM
python -m eastmoney_quant_mcp.cli cleanup

# Pattern scanning and backtesting
python -m eastmoney_quant_mcp.cli pattern-scan --universe sectors --date 2026-08-14
python -m eastmoney_quant_mcp.cli pattern-backtest --universe stocks --sample 300
python -m eastmoney_quant_mcp.cli pattern-optimize --cache signals.csv
```

---

## Local Database

Data is stored in local SQLite databases using WAL mode for high-concurrency read/write operations:

| Database | Default Path (Windows) | Default Path (Linux/macOS) | Contents |
|----------|------------------------|----------------------------|----------|
| Stock DB | `~/Desktop/股票信息/stock_data.db` | `~/.eastmoney-quant/data/stocks/stock_data.db` | stock quotes + adjustment-aware K-lines + popularity + indicators + combined + coverage/signals |
| Sector DB | `~/Desktop/分析板块/sector_data.db` | `~/.eastmoney-quant/data/sectors/sector_data.db` | sector quotes + capital flow + Eastmoney-only K-lines + members + indicators |

Override with `EASTMONEY_STOCK_DATA_DIR` and `EASTMONEY_SECTOR_DATA_DIR`.

---

## Environment Variables

Resolution order: **env var → `~/.eastmoney-quant/config.toml` → default**.

| Variable | Default | Purpose |
|----------|---------|---------|
| `EASTMONEY_PYTHON` | managed runtime $\rightarrow$ `python` | Python interpreter for the Node shim |
| `EASTMONEY_DATA_DIR` | Win: `~/Desktop`; Linux/macOS: `~/.eastmoney-quant/data` | Root directory for both databases |
| `EASTMONEY_STOCK_DATA_DIR` | `<data_root>/股票信息` (Linux/macOS: `stocks`) | Stock database directory |
| `EASTMONEY_SECTOR_DATA_DIR` | `<data_root>/分析板块` (Linux/macOS: `sectors`) | Sector database directory |
| `EASTMONEY_CONFIG` | `~/.eastmoney-quant/config.toml` | Override config.toml path |
| `EASTMONEY_COOKIE` | auto-extract from Edge | Manual Eastmoney API cookie string |

---

## Client Configuration

### Claude Desktop / Claude Code

```bash
claude mcp add eastmoney-quant -- npx eastmoney-quant-mcp
```

Or manually in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "eastmoney-quant": {
      "command": "npx",
      "args": ["eastmoney-quant-mcp"]
    }
  }
}
```

### Codex

Run `eastmoney-quant install --agents codex`, or add to `~/.codex/config.toml`:

```toml
[mcp_servers.eastmoney-quant]
command = "npx"
args = ["eastmoney-quant-mcp"]
```

### Cursor

Run `eastmoney-quant install --agents cursor`, or add the JSON block to `~/.cursor/mcp.json`.

### VS Code Copilot

Run `eastmoney-quant install --agents copilot`, or add to VS Code user `mcp.json` (Windows: `%APPDATA%\Code\User\mcp.json`):

```json
{
  "servers": {
    "eastmoney-quant": {
      "type": "stdio",
      "command": "npx",
      "args": ["eastmoney-quant-mcp"]
    }
  }
}
```

### Qoder

Run `eastmoney-quant install --agents qoder`, or add to `~/.qoder/mcp.json`.

### OpenCode / Other MCP Clients

```json
{
  "mcpServers": {
    "eastmoney-quant": {
      "command": "npx",
      "args": ["eastmoney-quant-mcp"]
    }
  }
}
```

### Direct Python Execution

```json
{
  "mcpServers": {
    "eastmoney-quant": {
      "command": "python",
      "args": ["-m", "eastmoney_quant_mcp.server"]
    }
  }
}
```

---

## Example Usage

```python
# Reuse an existing DB; initialize only when required
init_full_data(mode="quick")

# Recommended before full-market rising-pattern screening
init_full_data(mode="research", workers=6, resume=True)

# Or long-history full init (large resumable download for backtesting)
init_full_data(mode="full", workers=6, resume=True)

# Daily update after market close; compare freshness with the latest trading day
update_daily_data(stock_kline_mode="tracked")

# 3. Screen: change > 3%, PE < 30, volume ratio > 1.5
screen_stocks({"min_change_pct": 3, "max_pe": 30, "min_volume_ratio": 1.5})

# 4. Screen: semiconductor sector with PE < 50, sorted by popularity rank
screen_stocks({"max_pe": 50}, sector_code="BK1090", sort_by="popularity_rank")

# 5. Search: stocks containing "银行" (Bank)
screen_stocks(name_keyword="银行")

# 6. Get Ping An Bank K-line with cached indicators
get_kline_local_or_net("000001", days=250)

# 7. Ping An Bank 30-day popularity trend
get_rank_trend_data("000001", days=30)

# 8. Generate full analysis report
generate_stock_report("000001")

# 9. Chart pattern scan: market-wide strictly filtered signals
scan_patterns(strict=True)

# 10. Rank 20 rising candidates, then prepare every candidate for AI chart review
screen_rising_candidates(top_n=20, strict=True)
prepare_stock_analysis("000001", days=500, include_chart=True)

# 11. Validate event outcomes and executable portfolio assumptions
backtest_pattern_strategy(mode="both", split="2022-01-01")
```

---

## Development

```bash
git clone https://github.com/lalal-zzz/eastmoney-quant-mcp.git
cd eastmoney-quant-mcp
pip install -e ".[dev]"
pytest                    # Python unit tests
npm run test:node         # Node installer tests
pytest -m integration     # Opt-in: real network + local DB writes
```

## License

MIT License
