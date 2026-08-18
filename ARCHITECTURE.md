# Architecture

`eastmoney-quant-mcp` is a local-first A-share quantitative research platform for AI Agents.

## Module Structure

```
src/eastmoney_quant_mcp/
├── core/           # Configuration & extension registries
│   ├── config.py   # Settings resolution: env → config.toml → defaults
│   └── registry.py # Reserved provider/feature registries for future abstraction
├── data/           # Data acquisition, storage, and synchronization
│   ├── providers/  # Multi-source data adapters (Tencent/Sina/Sohu/Eastmoney)
│   ├── network.py  # HTTP client (curl_cffi) + cookie + symbol normalization
│   ├── storage.py  # SQLite storage engine (stock + sector databases)
│   ├── sync.py     # Full init + incremental daily update coordinator
│   ├── sources.py  # Extended data sources (spot/kline/rank/xuangu)
│   ├── search.py   # Local DB queries with network fallback
│   ├── build.py    # Rebuild/backfill/daily-capture/cleanup workflows
│   ├── indicators.py # Technical indicator calculations
│   └── progress.py # Progress bar shim (tqdm → null)
├── tools/          # Business logic & MCP tool implementations
│   ├── data_manager.py # Data management tools (init/update/status/screen)
│   ├── stock_data.py   # Stock K-line & search tools
│   ├── stock_rank.py   # Popularity ranking tools
│   ├── sector_data.py  # Sector list, members, K-line tools
│   ├── sector_screen.py # Sector screening & capital flow
│   ├── pattern_scan.py # Pattern screening tool
│   └── analysis.py     # Technical analysis report generation
├── strategies/     # Pattern recognition & backtesting
│   ├── patterns.py       # Pattern engine (5 patterns, dual universe)
│   ├── pattern_backtest.py # Historical backtesting CLI
│   └── pattern_optimize.py # Parameter optimization (beam search)
├── skill/          # AI Agent Skill definitions (SKILL.md files)
├── server.py       # MCP server entry point (14 registered tools)
└── cli.py          # CLI entry point (rebuild/backfill/capture/scan/backtest)
```

## Data Flow

1. **Data Acquisition**: `data/sources.py` + `data/providers/` fetch from multiple APIs
2. **Storage**: `data/storage.py` persists to local SQLite (stock + sector databases)
3. **Sync Orchestration**: `data/sync.py` coordinates batch operations with async concurrency
4. **Business Logic**: `tools/` exposes domain-specific functions
5. **MCP Interface**: `server.py` wraps 14 tools via `@register` decorator
6. **CLI Interface**: `cli.py` provides command-line access to data & strategy workflows

## Extension Points

- **New data sources**: Add adapters in `data/providers/`
- **New patterns**: Implement in `strategies/patterns.py`
- **New MCP tools**: Register in `server.py` with `@register(name, desc, schema)`
- **Provider abstraction** (planned): `core/registry.py` provides `PROVIDER_REGISTRY` / `FEATURE_REGISTRY` for future multi-provider routing
# Architecture

`eastmoney-quant-mcp` is a local-first data and research service.

- `core/` owns configuration and extension registration.
- `providers/` will adapt external data sources to shared domain models.
- `repositories/` owns durable storage and caching; current SQLite implementation remains in `data/storage.py` during the compatibility migration.
- `services/` exposes workflows used by CLI and MCP.
- `strategies/` contains reusable screening and pattern-scoring logic.
- `interfaces/` contains thin transports; the stdio MCP server is currently `server.py`.

New data sources belong in `providers/`; new research features belong in `strategies/` and `services/`. Do not add an MCP tool merely because an upstream API was added.
