[English](README.md) | [中文](README.zh-CN.md)

# Eastmoney Quant MCP Server

[![npm version](https://img.shields.io/npm/v/eastmoney-quant-mcp.svg)](https://www.npmjs.com/package/eastmoney-quant-mcp)
[![Python](https://img.shields.io/pypi/pyversions/eastmoney-quant-mcp.svg)](https://pypi.org/project/eastmoney-quant-mcp/)
[![License](https://img.shields.io/github/license/lalal-zzz/eastmoney-quant-mcp)](LICENSE)

Local-first A-share data and research center powered by **Eastmoney** public APIs and multi-source market providers. It maintains daily stock and sector data in high-concurrency local SQLite databases (WAL mode), enabling AI Agents to compose professional screening, chart pattern scanning, and financial research workflows.

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
| Market Data | 5530+ A-shares real-time: price / change% / PE / PB / market cap / volume ratio / turnover |
| K-lines | Daily OHLCV with forward/backward/no adjustment |
| Indicators | MA(5~200) / RSI(6/14/24) / MACD / BOLL / KDJ / ATR / VOL_MA |
| Popularity | Eastmoney real-time sentiment rankings + historical trends (rolling 1-year Guba rank) |
| Sectors | ~400 concepts + ~80 industries with capital flow (super-large/large/medium/small net) |
| Screening | 18 composable conditions: price range / PE / PB / cap / change% / volume / turnover / sector filter |
| Pattern Scanning | 5 chart patterns (trend pullback / MA rebound / W-bottom / M-neckline / box breakout) for stocks **and sectors**, with key levels (MA / Fibonacci / structure) |
| Reports | Full technical analysis: trend / support & resistance / risk assessment / stop-loss & position advice |

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

### Technical Indicators (auto-calculated)

| Category | Indicators |
|----------|------------|
| Moving Avg | MA5, MA10, MA20, MA30, MA60, MA100, MA200 |
| RSI | RSI6, RSI14, RSI24 |
| MACD | DIF, DEA, MACD histogram |
| Bollinger | Upper, middle, lower bands |
| KDJ | K, D, J values |
| Volatility | ATR14 (Average True Range) |
| Volume | VOL_MA5, VOL_MA10 |

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
| Position Advice | Stop-loss, take-profit, risk-reward ratio, suggested allocation |

---

## MCP Tools (14 tools)

| Tool | Module | Purpose |
|------|--------|---------|
| `init_full_data` | `data_manager` | Initial download to local SQLite (`quick=true` ~15s; full ~3-4 mins) |
| `update_daily_data` | `data_manager` | Daily incremental refresh (quotes / rankings / sectors) |
| `get_data_status` | `data_manager` | Local DB status (row counts / last update / paths) |
| `screen_stocks` | `data_manager` | Universal screening: 18 conditions + sector filter + name search + sort |
| `get_kline_local_or_net` | `data_manager` | Daily K-line, local-first with cached technical indicators |
| `get_stock_kline_period` | `stock_data` | Multi-period K-line (1/5/15/30/60m, day/week/month, real-time) |
| `get_rank_trend_data` | `data_manager` | Historical popularity ranking trend (N days) |
| `get_sector_list` | `sector_data` | Concept/industry sector list with capital flow |
| `get_stock_belong_sectors` | `data_manager` | Reverse lookup: stock $\rightarrow$ sectors |
| `generate_stock_report` | `analysis` | Technical report: trend / support & resistance / risk / position |
| `scan_patterns` | `strategies/patterns` | Stock chart-pattern scan (normal or strict filter) |
| `scan_sector_patterns` | `strategies/patterns` | Sector chart-pattern scan (concept/industry or symbols) |
| `get_pattern_history` | `strategies/patterns` | Historical pattern signals for one symbol (stock/sector) |
| `get_key_levels` | `strategies/patterns` | Current key levels: MA system / Fibonacci / structure (highs/lows) |

Ships with **6 Claude Skills** (installed automatically by `eastmoney-quant install`):

| Skill | Purpose |
|-------|---------|
| `eastmoney-quant` | Main index — check data readiness before research |
| `eastmoney-quant-data-init` | First-time download, daily updates, troubleshooting |
| `eastmoney-quant-stock-screening` | Composing screening conditions and workflows |
| `eastmoney-quant-report-generation` | Technical analysis report formatting and interpretation |
| `eastmoney-quant-multi-timeframe` | Multi-timeframe resonance analysis (weekly/daily/60m) |
| `eastmoney-quant-strategy-backtest` | Chart pattern backtesting and parameter optimization |

---

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
| Stock DB | `~/Desktop/股票信息/stock_data.db` | `~/.eastmoney-quant/data/stocks/stock_data.db` | 5530 stock quotes + K-lines + popularity + indicators + combined |
| Sector DB | `~/Desktop/分析板块/sector_data.db` | `~/.eastmoney-quant/data/sectors/sector_data.db` | 480+ sectors + capital flow + K-lines + members + indicators |

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
# 1a. Quick init (~15s: stocks + quotes + ranks; sectors lazy-load on first use)
init_full_data(quick=True)

# 1b. Or full init (~3-4 mins, includes all sector K-lines and members)
init_full_data(include_sector_members=True)

# 2. Daily update after market close (~30s)
update_daily_data()

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
