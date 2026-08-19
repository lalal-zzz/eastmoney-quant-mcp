# CLAUDE.md

Guidance for Claude Code when working in this repository. Deep-dive details live in [AGENTS.md](AGENTS.md) and [ARCHITECTURE.md](ARCHITECTURE.md) — this file covers the essentials and the gotchas most likely to bite.

## What this project is

Local-first A-share (Chinese stock market) quantitative analysis MCP server. Downloads Eastmoney and multi-source market data into local SQLite databases (WAL mode), then exposes **14 MCP tools** for screening, K-line queries, sector analysis, chart pattern recognition, and technical reports. Ships **6 Claude Skills** that teach agents how to compose the tools into end-to-end investment research workflows.

## Architecture (dual-runtime)

- `index.js` — Node shim (ESM): resolves a Python interpreter (`EASTMONEY_PYTHON` env → `~/.eastmoney-quant/runtime.json` → `python`), sets `PYTHONPATH` to `src/`, spawns `python -m eastmoney_quant_mcp.server` and proxies stdio. The Python server is the real MCP implementation.
- `src/eastmoney_quant_mcp/server.py` — MCP entrypoint. Exactly 14 tools are wired with a local `@register(name, desc, schema)` decorator; results are wrapped in a `{data, meta, warnings, error}` envelope.
- `bin/eastmoney-quant.js` + `lib/` — Node CLI installer (`install` / `setup` / `doctor` / `uninstall` / `config show`). Creates a `uv`-managed venv under `~/.eastmoney-quant/runtime/`, writes `~/.eastmoney-quant/config.toml`, auto-configures Claude Code / Codex / Cursor / VS Code Copilot / Qoder (with backups) and copies the 6 skills to skill-aware agents.
- Key Python modules:
  - `core/config.py` — settings resolution: env vars → `~/.eastmoney-quant/config.toml` → defaults
  - `data/network.py` — curl_cffi HTTP client, Edge cookie extraction, symbol normalization, K-line host rotation, provider circuit breaker
  - `data/storage.py` — SQLite engine (stock DB + sector DB) with WAL mode and decoupled read concurrency
  - `data/sync.py` — full init + incremental daily update (async, 16 concurrent)
  - `data/sources.py` — multi-source market data (clist snapshot, Tencent fqkline history, Guba AES rank history, Xuangu snapshot)
  - `data/build.py` — database rebuild, gap backfill, daily capture, cleanup routines
  - `strategies/patterns.py` — chart pattern engine (5 patterns, dual-universe `stocks` / `sectors`, no lookahead bias via Pivot lag confirmation and next-day open entry, key levels & Fibonacci)
  - `strategies/pattern_backtest.py` & `pattern_optimize.py` — pattern backtesting and beam-search parameter optimization
  - `cli.py` — unified CLI (`rebuild`, `backfill`, `daily-capture`, `cleanup`, `pattern-scan`, `pattern-backtest`, `pattern-optimize`)
  - `tools/` — MCP tool implementations (data_manager, stock_data, sector_data, analysis, ...)
  - `skill/` — main `SKILL.md` + sub-skills `data-init/`, `stock-screening/`, `report-generation/`, `multi-timeframe-analysis/`, `strategy-backtest/`
- Uses standard `tqdm` directly for progress display (stderr-only, auto-silent on non-TTY).

## Commands

```bash
# dev install (editable + dev deps)
pip install -e ".[dev]"

# unit tests (pytest-asyncio auto mode; integration tests excluded by default)
pytest

# single test
pytest tests/test_core.py::test_normalize_symbol

# integration tests (real network + writes local DBs — opt-in)
pytest -m integration

# manual smoke test (real network)
python tests/test_smoke.py

# Node installer/adapter tests
npm run test:node

# CLI maintenance & pattern backtest commands
python -m eastmoney_quant_mcp.cli rebuild --dry-run
python -m eastmoney_quant_mcp.cli pattern-scan --universe stocks --strict
```

There is **no linter, formatter, or typechecker** configured in this repo.

`npm install` triggers `node bin/eastmoney-quant.js postinstall`, which only prompts interactively on a TTY (skipped in CI) before configuring agents. Nothing is modified without confirmation.

## Prerequisites

- Python >= 3.10
- Node.js >= 18 (for `npx` usage and the CLI)
- `uv` (only needed for `eastmoney-quant install`'s managed Python runtime)
- No external services — all data comes from public Eastmoney and financial APIs.

## Critical gotchas

1. **HTTP calls**: always use `http_get` / `http_get_text` from `data/network.py` — never `requests` or `httpx` directly. The module force-IPv4-patches `socket.getaddrinfo`, clears proxy env vars, sets `NO_PROXY=*`, and uses curl_cffi Edge impersonation to pass TLS fingerprinting.
2. **Rate limiting**: `push2his.eastmoney.com` (K-line API) IP-bans after sustained heavy use (~thousands of requests/hour). Symptom: `curl: (56)` on all K-line hosts while clist keeps working. Multi-source degradation in `sources.py` automatically falls back to Tencent `fqkline` / Akshare / Sohu, protected by a circuit breaker.
3. **Tool registration**: `server.py` registers exactly **14 tools** via `@register`. Other functions in `tools/` (e.g. `pattern_scan`, `sector_screen`, `stock_rank`) are library code composed by Skills, intentionally not registered. When adding a tool, add both the import and the `@register` block; when removing, clean up both, and keep `package.json`'s `mcp.tools` list plus README in sync.
4. **Cookies**: fallback order `EASTMONEY_COOKIE` env → Edge browser cookie DB (Windows) → none. Falls back silently if Edge is running (DB locked) or cookies are encrypted.
5. **No Lookahead Bias**: in `patterns.py`, pivots are confirmed only after `right` bars (`p.confirm <= i`), and all backtest returns enter on next-day open (`open[i+1]`).

## Symbol conventions

| Format | Example |
|--------|---------|
| Stock (bare 6-digit) | `000001`, `600000` |
| Stock (prefixed) | `sh600000`, `sz000001`, `bj920000` |
| Sector code | `BK1090` or bare `1090` |

Use `normalize_symbol()` / `to_prefixed_symbol()` / `normalize_sector_code()` from `data/network.py`. Prefix rules: `6` → sh, `8`/`9` → bj, others → sz.

## Configuration

Resolution order: **env var → `~/.eastmoney-quant/config.toml` → default** (see `core/config.py`).

| Variable | Purpose | Default |
|----------|---------|---------|
| `EASTMONEY_PYTHON` | Python interpreter for the Node shim | managed runtime → `python` |
| `EASTMONEY_DATA_DIR` | Root directory for both DBs | Win: `~/Desktop`; Linux/macOS: `~/.eastmoney-quant/data` |
| `EASTMONEY_STOCK_DATA_DIR` | Stock SQLite DB directory | `<data_root>/股票信息` (Linux/macOS default: `stocks`) |
| `EASTMONEY_SECTOR_DATA_DIR` | Sector SQLite DB directory | `<data_root>/分析板块` (Linux/macOS default: `sectors`) |
| `EASTMONEY_CONFIG` | Override config.toml path | `~/.eastmoney-quant/config.toml` |
| `EASTMONEY_COOKIE` | Manual Eastmoney cookie string | auto-extract from Edge |
| `EASTMONEY_QUANT_HOME` | Override `~` for the Node CLI state | user home |

## Local data workflow

First use requires `init_full_data` — `quick=True` (~15s: stocks + quotes + ranks; sector members lazy-load on first use) or `quick=False` (full, a few minutes). Then `update_daily_data` for incremental refresh. After init, most queries (screening, K-line, rankings, sector members, pattern scanning) are served from local SQLite without network.

Tool flow: `init_full_data` → `update_daily_data` → `screen_stocks` / `get_kline_local_or_net` / `get_stock_kline_period` / `get_rank_trend_data` / `get_sector_list` / `get_stock_belong_sectors` / `generate_stock_report` / `scan_patterns` / `scan_sector_patterns` / `get_pattern_history` / `get_key_levels`.

## Skill format

All 6 `SKILL.md` files use standard YAML frontmatter (`name` + `description`), matching the official skill-creator format. The installer (`lib/adapters.js`) copies them to `<agent>/skills/<name>/SKILL.md` for skill-aware agents: Claude Code (`~/.claude/skills/`), Codex (`~/.codex/skills/`), Qoder (`~/.qoder/skills/`). Cursor / VS Code Copilot only get the MCP server registration.
