# AGENTS.md

## Architecture

- **Dual-runtime**: `index.js` (Node shim, ESM) spawns `python -m eastmoney_quant_mcp.server` via stdio and proxies I/O. The Python server is the real MCP implementation. Python interpreter resolution: `EASTMONEY_PYTHON` env → `~/.eastmoney-quant/runtime.json` (uv-managed venv) → `python`.
- **Entrypoint**: `src/eastmoney_quant_mcp/server.py` — uses `mcp.server.stdio` and a `@register(name, desc, schema)` decorator to wire exactly 10 tools to MCP handlers; every result is wrapped in a `{data, meta, warnings, error}` envelope.
- **Node CLI**: `bin/eastmoney-quant.js` + `lib/` — installer commands `install` / `setup` / `doctor` / `uninstall` / `config show`. `lib/installer.js` creates a `uv` venv under `~/.eastmoney-quant/runtime/` and writes `config.toml` / `runtime.json` / `install-state.json`; `lib/adapters.js` auto-configures 5 agents with backups — Claude Code (`~/.claude.json`), Codex (`~/.codex/config.toml`), Cursor (`~/.cursor/mcp.json`), VS Code Copilot (user `mcp.json`, `servers` key + `type: stdio`), Qoder (`~/.qoder/mcp.json`) — and copies the 4 skills to skill-aware agents (Claude Code / Codex / Qoder); `lib/paths.js` centralizes `~/.eastmoney-quant` paths.
- **Source layout**:
  - `core/config.py` — settings resolution: env vars → `~/.eastmoney-quant/config.toml` → defaults (`get_settings()`)
  - `core/registry.py` — provider/feature registries reserved for future extensions
  - `data/network.py` — HTTP client (curl_cffi) + Edge cookie extraction + symbol normalization + K-line host rotation (`try_kline_hosts`)
  - `data/indicators.py` — technical indicator calcs (MA/RSI/MACD/BOLL/KDJ/ATR)
  - `data/storage.py` — SQLite storage engine (stock database + sector database)
  - `data/sync.py` — full init download + incremental daily update coordinator (semaphore-pipelined async concurrency, 16 in flight; `init_all_data(quick=True)` = fast mode)
  - `data/search.py` — local DB queries with fallback to network APIs
  - `data/progress.py` — progress-bar shim: funny-tqdm → plain tqdm → null (all stderr-only, auto-silent on non-TTY)
  - `tools/stock_data.py` — stock list, history, indicators, search, multi-period K-line (`get_stock_kline_period`: klt 1/5/15/30/60/101/102/103)
  - `tools/stock_rank.py` — popularity rankings (gainers/volume/turnover)
  - `tools/sector_data.py` — sector list, members, K-line (`get_sector_kline_net` accepts `klt`)
  - `tools/pattern_scan.py` — technical pattern screening
  - `tools/sector_screen.py` — sector screening + capital flow analysis
  - `tools/data_manager.py` — local data management MCP tools (init/update/search/sector→stocks)
  - `tools/analysis.py` — individual stock technical analysis reports (support/resistance/risk/position)
  - `skill/SKILL.md` — main skill index; sub-skills: `data-init/`, `stock-screening/`, `report-generation/`
- **Standalone package**: [`funny-tqdm`](https://pypi.org/project/funny-tqdm/) — animated progress-bar package (tqdm + mascot animations, stderr-only), published on PyPI. Install with `pip install funny-tqdm`. The `funny-progress/` subdirectory in this repo is the legacy source; the canonical repo is [github.com/lalal-zzz/funny-tqdm](https://github.com/lalal-zzz/funny-tqdm). `data/progress.py` degrades gracefully without it.
- **Data source**: [akshare](https://github.com/akfamily/akshare) for all Eastmoney APIs.

## Commands

```bash
# dev install (editable + dev deps)
pip install -e ".[dev]"

# run all tests (async via pytest-asyncio, no @pytest.mark.asyncio needed)
pytest

# run a single test
pytest tests/test_core.py::test_normalize_symbol

# integration tests (real network + writes local DBs; excluded by default via addopts)
pytest -m integration

# manual smoke test of the tool chain (real network, not collected by pytest)
python tests/test_smoke.py

# Node installer/adapter tests (node:test)
npm run test:node
```

`npm install` triggers `node bin/eastmoney-quant.js postinstall`, which asks before configuring anything (TTY-only prompt; silently skipped in CI / non-interactive installs). For a checked setup run `eastmoney-quant install --agents auto` explicitly.

There is **no linter, formatter, or typechecker** configured in this repo.

## Prerequisites

- Python >= 3.10
- Node.js >= 18 (for `npx` usage and the CLI)
- `uv` — required only by `eastmoney-quant install` / `setup` for the managed Python runtime
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

Settings resolve as **env var → `~/.eastmoney-quant/config.toml` → default** (`core/config.py`). The CLI's `eastmoney-quant setup --data-root <dir>` writes `config.toml`.

| Variable | Purpose | Default |
|----------|---------|---------|
| `EASTMONEY_PYTHON` | Override Python interpreter path | managed runtime → `python` |
| `EASTMONEY_DATA_DIR` | Root directory for both DBs | Win: `~/Desktop`; Linux/macOS: `~/.eastmoney-quant/data` |
| `EASTMONEY_STOCK_DATA_DIR` | Stock SQLite DB directory | `<data_root>/股票信息` (Linux/macOS default: `stocks`) |
| `EASTMONEY_SECTOR_DATA_DIR` | Sector SQLite DB directory | `<data_root>/分析板块` (Linux/macOS default: `sectors`) |
| `EASTMONEY_CONFIG` | Override config.toml path | `~/.eastmoney-quant/config.toml` |
| `EASTMONEY_COOKIE` | Manual cookie string for Eastmoney APIs | auto-extract from Edge |
| `EASTMONEY_QUANT_HOME` | Override home dir for Node CLI state | user home |

The Node shim sets `PYTHONPATH` to include `src/` automatically.

## MCP tools (10 registered)

| Tool | Module | Purpose |
|------|--------|---------|
| `init_full_data` | `data_manager` | First-time download to local SQLite (`quick=true` ≈ seconds; full ≈ minutes) |
| `update_daily_data` | `data_manager` | Incremental daily refresh (quotes / rankings / sectors) |
| `get_data_status` | `data_manager` | Local DB status (row counts / last update / paths) |
| `screen_stocks` | `data_manager` | Universal screening: 18 conditions + sector filter + name keyword + sort |
| `get_kline_local_or_net` | `data_manager` | Daily K-line, local-first with cached indicators |
| `get_stock_kline_period` | `stock_data` | Multi-period K-line (klt 1/5/15/30/60/101/102/103, network real-time) |
| `get_rank_trend_data` | `data_manager` | Historical popularity ranking trend |
| `get_sector_list` | `sector_data` | Concept/industry sector list with capital flow |
| `get_stock_belong_sectors` | `data_manager` | Reverse lookup: stock → sectors |
| `generate_stock_report` | `analysis` | Technical report: trend / S&R / risk / position |

## Local data workflow

First-time use requires `init_full_data` — `quick=True` (~15s, stocks+quotes+ranks only, sector data lazy-loads on first use via `_ensure_sector_members`) or `quick=False` (full, a few minutes). Then use `update_daily_data` for incremental daily refresh. After initialization, most queries (search, K-line, rankings, sector members) work from local DB without network calls.

Typical flow: `init_full_data` → `update_daily_data` → `screen_stocks` → `get_kline_local_or_net` / `generate_stock_report` / `get_rank_trend_data` / `get_stock_belong_sectors`.

Unregistered library helpers used by Skills/internal code: `get_sector_members_flow` (sector→stocks with capital flow), `get_sector_kline` (network) vs `get_sector_kline_local` (local DB after init), pattern/sector screeners in `pattern_scan.py` / `sector_screen.py`.

## Project config

- **Build**: `hatchling` (Python), no transpilation (Node is plain ESM)
- **Test**: `pytest` with `asyncio_mode = "auto"`. Default run is unit-only (`addopts = "-m 'not integration'"`): symbol/klt normalization, pattern registry, config resolution. `tests/test_integration.py` is marked `integration` (real network + DB writes). `node-tests/` covers the installer adapters via `node:test`.
- **Package name**: `eastmoney-quant-mcp` (npm & PyPI)
- **Optional deps**: `browser` extra installs `playwright` — not used by default tools

## Tool registration gotcha

Tools are wired via the `@register(name, desc, schema)` decorator in `server.py` — exactly **10 tools** are registered (3 data management, 1 screening, 5 query, 1 report). Other functions in `tools/` (`stock_rank`, `pattern_scan`, `sector_screen`, most of `sector_data`) are intentionally **not** registered — they are library code that Skills compose through the registered tools. When adding a tool, add both the import and the `@register` block; when removing, clean up both. Also keep the `mcp.tools` list in `package.json` and the tool tables in `README.md` in sync.

## Skill format

All 4 `SKILL.md` files use standard YAML frontmatter:
```yaml
---
name: skill-identifier
description: What it does and when to trigger...
---
```
This matches the [official skill-creator format](https://github.com/anthropics/claude-plugins-official). `lib/adapters.js` (invoked by `eastmoney-quant install`) copies them to `<agent>/skills/<name>/SKILL.md` for skill-aware agents — Claude Code: `~/.claude/skills/`, Codex: `~/.codex/skills/`, Qoder: `~/.qoder/skills/`. Cursor and VS Code Copilot only get the MCP server registration (they do not consume SKILL.md).
