---
name: eastmoney-quant-data-init
description: Initialize and maintain the local SQLite database for A-share quantitative analysis. Use when the user needs to set up stock data for the first time, update daily data, check database status, change storage paths, or troubleshoot database issues. Triggered by phrases like "初始化数据", "更新数据", "数据库状态", "数据存储位置", "init database".
---

# Data initialization & management

## Prerequisites

Tell the user this must be done before any screening or report generation.

## Storage paths

Resolution order: env var → `~/.eastmoney-quant/config.toml` (written by `eastmoney-quant setup`) → default.

| Database | Default path | Env var |
|----------|-------------|---------|
| Stock | `~/Desktop/股票信息/stock_data.db` | `EASTMONEY_STOCK_DATA_DIR` |
| Sector | `~/Desktop/分析板块/sector_data.db` | `EASTMONEY_SECTOR_DATA_DIR` |

Ask the user if they want to change paths. If yes, guide them to set env vars (or run `eastmoney-quant setup --data-root <dir>`) before running init.

## First-time setup

Prefer quick mode — usable in seconds:

```
init_full_data(quick=True)
```

Downloads stock list + real-time quotes + popularity rankings only (~15s). Sector members lazy-load automatically on first sector query.

Full mode (all sector K-lines + members up front, a few minutes):

```
init_full_data(include_sector_members=True)
```

Tables created (8 data tables + `meta` in each DB):

| Table | Content | Rows |
|-------|---------|------|
| `stock_basic` | Stock list | ~5500 |
| `stock_spot` | Real-time snapshot (price/PE/PB/cap/volume_ratio/turnover_rate) | ~5500 |
| `stock_rank` | Daily popularity ranking | ~5500/day |
| `stock_kline` | Per-stock daily K-line (downloaded on demand) | grows with use |
| `stock_indicators` | Cached MA/RSI/MACD/BOLL/KDJ/ATR per stock | grows with use |
| `sector_basic` | Concept + industry sectors | ~480 |
| `sector_kline` | Sector K-line (250 days) | ~120K (full mode) |
| `sector_member` | Sector member stocks | ~15K (full mode / lazy) |

## Daily update

```
update_daily_data(include_sector_members=True)
```

- Refreshes `stock_spot` (full, 1 API call)
- Appends to `stock_rank` (accumulates history, 1 API call)
- Updates `stock_basic` (detects new/delisted stocks)
- Updates `sector_basic` (full, 2 API calls)
- Updates sector K-lines for top 50 active sectors (concurrent, ~1min)
- Optionally updates sector members for top 50 (if `include_sector_members=True`)

## K-line on demand

Stock K-lines are NOT downloaded during init/update (too many stocks). Download per stock:

```
get_kline_local_or_net(symbol="000001", days=365)
```

This auto-computes and stores MA/RSI/MACD/BOLL/KDJ/ATR for the downloaded period. Caching is permanent — subsequent calls read from local DB instantly.

## Checking status

```
get_data_status()
```

Returns row counts and last update dates for all tables. If any date is not today, suggest `update_daily_data`.

## Troubleshooting

- **Database corruption**: delete `stock_data.db` and/or `sector_data.db`, rerun `init_full_data`
- **Disk space**: base data ~100MB, each stock K-line ~0.5MB
- **Network errors during init**: rerun `init_full_data` — it uses `INSERT OR REPLACE` so partial data is safe

## Next steps

After successful init, guide user to:
- `eastmoney-quant-stock-screening` for multi-condition screening
- `eastmoney-quant-report-generation` for individual stock analysis
