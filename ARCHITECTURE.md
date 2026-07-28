# Architecture

`eastmoney-quant-mcp` is a local-first data and research service.

- `core/` owns configuration and extension registration.
- `providers/` will adapt external data sources to shared domain models.
- `repositories/` owns durable storage and caching; current SQLite implementation remains in `data/storage.py` during the compatibility migration.
- `services/` exposes workflows used by CLI and MCP.
- `strategies/` contains reusable screening and pattern-scoring logic.
- `interfaces/` contains thin transports; the stdio MCP server is currently `server.py`.

New data sources belong in `providers/`; new research features belong in `strategies/` and `services/`. Do not add an MCP tool merely because an upstream API was added.
