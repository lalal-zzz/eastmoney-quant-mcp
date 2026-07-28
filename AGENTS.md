# AGENTS.md

## Architecture

- **Dual-runtime**: `index.js` (Node shim, ESM) spawns `python -m eastmoney_quant_mcp.server` via stdio and proxies I/O. The Python server is the real MCP implementation.
- **Entrypoint**: `src/eastmoney_quant_mcp/server.py` — uses `mcp.server.stdio` and a `@register` decorator to wire tools to MCP handlers.
- **Source layout**:
  - `data/network.py` — HTTP client (curl_cffi) + Edge cookie extraction + symbol normalization + K-line host rotation (`try_kline_hosts`)
  - `data/indicators.py` — technical indicator calcs (MA/RSI/MACD/BOLL/KDJ/ATR)
  - `data/storage.py` — SQLite storage engine (stock database + sector database)
  - `data/sync.py` — full init download + incremental daily update coordinator (semaphore-pipelined async concurrency, 16 in flight; `init_all_data(quick=True)` = fast mode)
  - `data/search.py` — local DB queries with fallback to network APIs
  - `data/progress.py` — progress-bar shim: funny-progress → plain tqdm → null (all stderr-only, auto-silent on non-TTY)
  - `tools/stock_data.py` — stock list, history, indicators, search, multi-period K-line (`get_stock_kline_period`: klt 1/5/15/30/60/101/102/103)
  - `tools/stock_rank.py` — popularity rankings (gainers/volume/turnover)
  - `tools/sector_data.py` — sector list, members, K-line (`get_sector_kline_net` accepts `klt`)
  - `tools/pattern_scan.py` — technical pattern screening
  - `tools/sector_screen.py` — sector screening + capital flow analysis
  - `tools/data_manager.py` — local data management MCP tools (init/update/search/sector→stocks)
  - `tools/analysis.py` — individual stock technical analysis reports (support/resistance/risk/position)
  - `skill/SKILL.md` — main skill index; sub-skills: `data-init/`, `stock-screening/`, `report-generation/`
- **Sibling package**: `funny-progress/` — standalone animated progress-bar package (tqdm + mascot animations, stderr-only). Reusable in other projects; install with `pip install -e ./funny-progress`. Not yet on PyPI — `data/progress.py` degrades gracefully without it.
- **Data source**: [akshare](https://github.com/akfamily/akshare) for all Eastmoney APIs.

## Commands

```bash
# dev install (editable + dev deps)
pip install -e ".[dev]"

# run all tests (async via pytest-asyncio, no @pytest.mark.asyncio needed)
pytest

# run a single test
pytest tests/test_core.py::test_normalize_symbol
```

`npm install` runs `pip install -e .` + `install-skill.js` automatically via `postinstall`. The skill copier silently tries `~/.claude/skills/` and `~/.agents/skills/`.

There is **no linter, formatter, or typechecker** configured in this repo.

## Prerequisites

- Python >= 3.10
- Node.js >= 18 (for `npx` usage)
- No external services needed — all data comes from public Eastmoney APIs.

## Network quirk

`data/network.py` patches `socket.getaddrinfo` to force IPv4 and clears all proxy env vars (`http_proxy`, `https_proxy`, `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`) at import time. It also sets `NO_PROXY=*` because `requests`/akshare would otherwise read the Windows registry system proxy directly (bypassing env clearing). HTTP requests use `curl_cffi` with Edge impersonation to bypass TLS fingerprinting. If you add a new API call, use `http_get`/`http_get_text` from this module, **not** `requests` or `httpx` directly.

### Rate limiting (learned the hard way)

`push2his.eastmoney.com` (K-line API) will **IP-ban after sustained heavy use** (~thousands of requests/hour, e.g. running full init repeatedly). Symptom: `curl: (56) Connection closed abruptly` on ALL kline hosts while `push2` (clist) keeps working. The ban is temporary — wait it out (minutes to hours). `try_kline_hosts` treats empty `data: null` as failure and rotates to the next host. Normal usage (one full init + daily updates) is well below the threshold.

### Cookie adaptation

`network.py` auto-extracts Eastmoney cookies from Edge browser on Windows:

1. Reads `%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Network\Cookies` (SQLite)
2. Filters for domains containing `eastmoney` or `dfcf`
3. Appends cookies to request headers

Fallback order: `EASTMONEY_COOKIE` env var → Edge browser cookies → no cookies.

- **Edge is running**: cookie DB is locked → falls back silently
- **Edge cookies are encrypted**: newer Edge may encrypt cookie values → falls back to env var
- Set `EASTMONEY_COOKIE` explicitly to skip auto-detection (e.g., `EASTMONEY_COOKIE="qgqp_b_id=xxx; st_pvi=yyy"`)

## Symbol / code conventions

| Format | Example |
|--------|---------|
| Stock (bare 6-digit) | `000001`, `600000` |
| Stock (prefixed) | `sh600000`, `sz000001`, `bj920000` |
| Sector code | `BK1090` or bare `1090` |

Use `normalize_symbol()` / `to_prefixed_symbol()` / `normalize_sector_code()` from `data/network.py`. Prefix rules: `6` → sh, `8`/`9` → bj, others → sz.

## Environment

| Variable | Purpose | Default |
|----------|---------|---------|
| `EASTMONEY_PYTHON` | Override Python interpreter path | `python` |
| `EASTMONEY_STOCK_DATA_DIR` | Stock SQLite DB directory | `~/Desktop/股票信息` |
| `EASTMONEY_SECTOR_DATA_DIR` | Sector SQLite DB directory | `~/Desktop/分析板块` |
| `EASTMONEY_COOKIE` | Manual cookie string for Eastmoney APIs | auto-extract from Edge |

The Node shim sets `PYTHONPATH` to include `src/` automatically.

## Local data workflow

First-time use requires `init_full_data` — `quick=True` (~15s, stocks+quotes+ranks only, sector data lazy-loads on first use via `_ensure_sector_members`) or `quick=False` (full, ~3-4 min). Then use `update_daily_data` for incremental daily refresh. After initialization, most queries (search, K-line, rankings, sector members) work from local DB without network calls.

Key local tools: `init_full_data` → `update_daily_data` → `screen_stocks` / `get_kline_local_or_net` / `get_sector_members_flow` (sector→stocks workflow) / `get_stock_belong_sectors` (stock→sectors reverse lookup) / `get_rank_trend_data` (historical popularity trend).

`get_sector_kline` fetches from network; `get_sector_kline_local` reads from local DB after init.

## Project config

- **Build**: `hatchling` (Python), no transpilation (Node is plain ESM)
- **Test**: `pytest` with `asyncio_mode = "auto"` — tests are pure unit tests (no network calls), test only normalization + pattern registry
- **Package name**: `eastmoney-quant-mcp` (npm & PyPI)
- **Optional deps**: `browser` extra installs `playwright` — not used by default tools

## Tool registration gotcha

Tools are wired via the `@register(name, desc, schema)` decorator in `server.py`. `screen_sector_by_capital_flow` is imported from `sector_screen` at the top of `server.py` but is **never registered** with `@register` — it's intentionally omitted (no user-facing tool for it yet). When adding new tools, make sure to add both the import and the `@register` block; when removing, clean up both.

## Skill format

All 4 `SKILL.md` files use standard YAML frontmatter:
```yaml
---
name: skill-identifier
description: What it does and when to trigger...
---
```
This matches the [official skill-creator format](https://github.com/anthropics/claude-plugins-official). The `install-skill.js` copies them to `~/.claude/skills/<name>/SKILL.md`.
