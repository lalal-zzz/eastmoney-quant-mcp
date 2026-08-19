# AGENTS.md

## Architecture

- **Dual-runtime**: `index.js` (Node shim, ESM) spawns `python -m eastmoney_quant_mcp.server` via stdio and proxies I/O. The Python server is the real MCP implementation. Python interpreter resolution: `EASTMONEY_PYTHON` env → `~/.eastmoney-quant/runtime.json` (uv-managed venv) → `python`.
- **Entrypoint**: `src/eastmoney_quant_mcp/server.py` — uses `mcp.server.stdio` and a `@register(name, desc, schema)` decorator to wire exactly 14 tools to MCP handlers; every result is wrapped in a `{data, meta, warnings, error}` envelope.
- **Node CLI**: `bin/eastmoney-quant.js` + `lib/` — installer commands `install` / `setup` / `doctor` / `uninstall` / `config show`. `lib/installer.js` creates a `uv` venv under `~/.eastmoney-quant/runtime/` and writes `config.toml` / `runtime.json` / `install-state.json`; `lib/adapters.js` auto-configures 5 agents with backups — Claude Code (`~/.claude.json`), Codex (`~/.codex/config.toml`), Cursor (`~/.cursor/mcp.json`), VS Code Copilot (user `mcp.json`, `servers` key + `type: stdio`), Qoder (`~/.qoder/mcp.json`) — and copies the 6 skills to skill-aware agents (Claude Code / Codex / Qoder); `lib/paths.js` centralizes `~/.eastmoney-quant` paths.
- **Source layout**:
  - `core/config.py` — settings resolution: env vars → `~/.eastmoney-quant/config.toml` → defaults (`get_settings()`)
  - `core/registry.py` — provider/feature registries reserved for future extensions
  - `data/network.py` — HTTP client (curl_cffi) + Edge cookie extraction + symbol normalization + K-line host rotation (`try_kline_hosts`)
  - `data/indicators.py` — technical indicator calcs (MA/RSI/MACD/BOLL/KDJ/ATR)
  - `data/storage.py` — SQLite storage engine (stock database + sector database) with WAL mode, decoupled read-lock concurrency, and column padding defense
  - `data/sync.py` — full init download + incremental daily update coordinator (semaphore-pipelined async concurrency, 16 in flight; `init_all_data(quick=True)` = fast mode)
  - `data/search.py` — local DB queries with fallback to network APIs
  - `data/progress.py` — progress-bar shim: tqdm → null (stderr-only, auto-silent on non-TTY)
  - `data/sources.py` — extended data sources (移植自旧“股票信息”项目): `fetch_full_spot` (push2 clist 三镜像分页), `fetch_kline_history` (腾讯 fqkline 日期分段翻页 + 全局限速, 回退 akshare/搜狐), `fetch_guba_rank_history` (股吧年文件 AES-CBC 解密, key=md5("getUtilsFromFile")), `fetch_xuangu_rankings` (dataapi/xuangu 分页), `is_trade_day`/`previous_trade_day` (新浪交易日历缓存)
  - `data/build.py` — 重建/回填/采集/清理: `rebuild_full_data` (步骤化全量重建 + rebuild_progress 断点续传 + `--dry-run` 预览不联网), `backfill_data` (缺口检测补齐), `daily_capture` (晚间采集: xuangu 排名 + spot 快照 + K 线增量 + 指标缓存, 跳过非交易日), `cleanup_database` (冗余表清理 + VACUUM), 板块全量 K 线下载 + 板块指标缓存
  - `tools/stock_data.py` — stock list, history, indicators, search, multi-period K-line (`get_stock_kline_period`: klt 1/5/15/30/60/101/102/103)
  - `tools/stock_rank.py` — popularity rankings (gainers/volume/turnover)
  - `tools/sector_data.py` — sector list, members, K-line (`get_sector_kline_net` accepts `klt`)
  - `tools/pattern_scan.py` — technical pattern screening
  - `tools/sector_screen.py` — sector screening + capital flow analysis
  - `tools/data_manager.py` — local data management MCP tools (init/update/search/sector→stocks)
  - `tools/analysis.py` — individual stock technical analysis reports (support/resistance/risk/position)
  - `strategies/patterns.py` — 形态引擎 (移植旧项目 stock_patterns.py): 波段引擎 (Pivot/build_pivot_events/update_zigzag/wave_phase), 关键位 (MA5~250 补算 MA120/250, 斐波那契 0.382/0.5/0.618/0.786, 结构位), 因子列 add_factor_columns, 5 形态 (trend_pullback/ma_rebound/w_bottom/m_neckline/box_breakout), PATTERN_FILTERS/PATTERN_STRICT_FILTERS/PATTERN_COOLDOWN; **双宇宙抽象**: `prepare_df(universe, symbol)` 支持 stocks (stock_kline+stock_indicators) / sectors (sector_kline+sector_indicators, trade_date→date、turnover_rate→turnover、KDJ_K→K 映射), MIN_BARS=260 不足自动跳过; 避免未来函数 (pivot 右确认 + 次日开盘入场)
  - `strategies/pattern_backtest.py` — 形态回测 CLI (6 份报告: 形态×变体胜率/关键位分层/wave_phase 分层/因子分层/过滤阈值搜索/分年度胜率), `--universe stocks|sectors`
  - `strategies/pattern_optimize.py` — beam search 多因子规则搜索 + train/test 时间切分防过拟合, 尝试记录 markdown 输出
  - `cli.py` — 统一 CLI 入口 `python -m eastmoney_quant_mcp.cli`: rebuild / backfill / daily-capture / cleanup / pattern-scan / pattern-backtest / pattern-optimize, 通用 `--data-dir` (等价 EASTMONEY_DATA_DIR) 与 `--dry-run`
  - `skill/SKILL.md` — main skill index; sub-skills: `data-init/`, `stock-screening/`, `report-generation/`, `multi-timeframe-analysis/`, `strategy-backtest/`
- **Progress display**: Uses standard `tqdm` directly for progress display across sync/cli operations (stderr-only, auto-silent on non-TTY).
- **Data sources (multi-provider)**: [akshare](https://github.com/akfamily/akshare) for Eastmoney APIs, plus `data/providers/` (`tencent.py` / `sina.py` / `sohu.py` / `boardmap.py`). Degradation chains (local DB keys stay Eastmoney codes):
  - Stock K-line: Tencent `fqkline`/`mkline` (primary) → Eastmoney akshare → Sohu `hisHq` (unadjusted, last resort). This exists because `push2his` IP-bans are frequent; stock/multi-period K-lines keep working during a ban.
  - Sector members: Sina `getHQNodeData` (primary, name-mapped) → Eastmoney clist → Sohu HTML + Tencent quote batch.
  - Sector K-line: **Eastmoney single-source** (Tencent only serves the latest 1 bar for boards and its member set differs → cross-source mixing creates volume steps). Protected by a circuit breaker.
  - Board code mapping: Eastmoney `BKxxxx` ↔ Tencent `ptXXXX` / Sina node / Sohu `bk_` by **board name** (with `概念` suffix variants), cached 24h in-process; unmapped boards fall back to Eastmoney.
  - Circuit breaker (`network.py`): 3 consecutive network failures per provider → 10-min cooldown; `fetch_em_kline` gates Eastmoney K-line calls so a banned IP doesn't amplify retries across the ~580-board batch downloads.
  - Known quirks (all live-tested): Tencent day rows are `[date, open, close, high, low, volume]` (close is 3rd!); `fqkline` max 640 bars/request (larger counts misbehave — page by date range); Sohu WAF rejects the new `edge` TLS fingerprint (use `impersonate="edge99"`), rejects foreign cookies (`use_cookies=False`), rejects `end > today`, and intermittently 503s high-frequency IPs; Sina requires `Referer: https://finance.sina.com.cn`.

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

# 数据重建/回填/采集/清理 + 形态 CLI (统一入口 cli.py)
python -m eastmoney_quant_mcp.cli rebuild --dry-run          # 预览重建步骤, 不联网不写库
python -m eastmoney_quant_mcp.cli rebuild --workers 8 --with-sectors
python -m eastmoney_quant_mcp.cli backfill --start 2026-01-01
python -m eastmoney_quant_mcp.cli daily-capture              # 晚间采集 (任务计划用)
python -m eastmoney_quant_mcp.cli cleanup --dry-run
python -m eastmoney_quant_mcp.cli pattern-scan --universe sectors --date 2026-08-14
python -m eastmoney_quant_mcp.cli pattern-backtest --universe stocks --sample 300
python -m eastmoney_quant_mcp.cli pattern-optimize --cache signals.csv
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

## MCP tools (14 registered)

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
| `scan_patterns` | `strategies/patterns` | Stock chart-pattern scan (full market or symbols, date, normal/strict) |
| `scan_sector_patterns` | `strategies/patterns` | Sector chart-pattern scan (concept/industry or symbols) |
| `get_pattern_history` | `strategies/patterns` | Historical pattern signals for one symbol (stock/sector) |
| `get_key_levels` | `strategies/patterns` | Current key levels: MA system / Fibonacci / structure |

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

Tools are wired via the `@register(name, desc, schema)` decorator in `server.py` — exactly **14 tools** are registered (3 data management, 1 screening, 5 query, 1 report, 4 pattern). The 4 pattern tools (`scan_patterns` / `scan_sector_patterns` / `get_pattern_history` / `get_key_levels`) wrap the synchronous `strategies/patterns.py` functions with `asyncio.to_thread`. Other functions in `tools/` (`stock_rank`, `pattern_scan`, `sector_screen`, most of `sector_data`) are intentionally **not** registered — they are library code that Skills compose through the registered tools. When adding a tool, add both the import and the `@register` block; when removing, clean up both. Also keep the `mcp.tools` list in `package.json` and the tool tables in `README.md` in sync.

## Skill format

All 6 `SKILL.md` files use standard YAML frontmatter:
```yaml
---
name: skill-identifier
description: What it does and when to trigger...
---
```
This matches the [official skill-creator format](https://github.com/anthropics/claude-plugins-official). `lib/adapters.js` (invoked by `eastmoney-quant install`) copies them to `<agent>/skills/<name>/SKILL.md` for skill-aware agents — Claude Code: `~/.claude/skills/`, Codex: `~/.codex/skills/`, Qoder: `~/.qoder/skills/`. Cursor and VS Code Copilot only get the MCP server registration (they do not consume SKILL.md).
