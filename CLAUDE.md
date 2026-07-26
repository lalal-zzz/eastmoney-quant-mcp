# AGENTS.md

## Architecture

- **Dual-runtime**: `index.js` (Node shim, ESM) spawns `python -m eastmoney_quant_mcp.server` via stdio and proxies I/O. The Python server is the real MCP implementation.
- **Entrypoint**: `src/eastmoney_quant_mcp/server.py` — uses `mcp.server.stdio` and a `@register` decorator to wire tools to MCP handlers.
- **Source layout**:
  - `data/network.py` — HTTP client (curl_cffi) + symbol normalization helpers
  - `data/indicators.py` — technical indicator calcs (MA/RSI/MACD/BOLL/KDJ/ATR)
  - `tools/stock_data.py` — stock list, history, indicators, search
  - `tools/stock_rank.py` — popularity rankings (gainers/volume/turnover)
  - `tools/sector_data.py` — sector list, members, K-line
  - `tools/pattern_scan.py` — technical pattern screening
  - `tools/sector_screen.py` — sector screening + capital flow analysis
  - `skill/SKILL.md` — Claude/OpenCode skill file copied by `install-skill.js`
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

`data/network.py` patches `socket.getaddrinfo` to force IPv4 and clears all proxy env vars (`http_proxy`, `https_proxy`, `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`) at import time. HTTP requests use `curl_cffi` with Edge impersonation to bypass TLS fingerprinting. If you add a new API call, use `http_get`/`http_get_text` from this module, **not** `requests` or `httpx` directly.

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

The Node shim sets `PYTHONPATH` to include `src/` automatically.

## Project config

- **Build**: `hatchling` (Python), no transpilation (Node is plain ESM)
- **Test**: `pytest` with `asyncio_mode = "auto"` — tests are pure unit tests (no network calls), test only normalization + pattern registry
- **Package name**: `eastmoney-quant-mcp` (npm & PyPI)
- **Optional deps**: `browser` extra installs `playwright` — not used by default tools

## Tool registration gotcha

Tools are wired via the `@register(name, desc, schema)` decorator in `server.py`. `screen_sector_by_capital_flow` is imported from `sector_screen` at the top of `server.py` but is **never registered** with `@register` — it's intentionally omitted (no user-facing tool for it yet). When adding new tools, make sure to add both the import and the `@register` block; when removing, clean up both.
