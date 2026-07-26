# 东方财富量化 MCP 服务 | Eastmoney Quant MCP

[![npm version](https://img.shields.io/npm/v/eastmoney-quant-mcp.svg)](https://www.npmjs.com/package/eastmoney-quant-mcp)
[![Python](https://img.shields.io/pypi/pyversions/eastmoney-quant-mcp.svg)](https://pypi.org/project/eastmoney-quant-mcp/)
[![License](https://img.shields.io/github/license/lalal-zzz/eastmoney-quant-mcp)](LICENSE)

A-share quantitative analysis MCP server. Local SQLite storage, multi-condition stock screening, sector analysis, and comprehensive technical reports with support/resistance/risk/position advice.

## Quick start

```bash
claude mcp add eastmoney-quant -- npx eastmoney-quant-mcp
```

Prerequisites: Python >= 3.10 + Node.js >= 18

## MCP tools (9)

| Tool | Description |
|------|-------------|
| `init_full_data` | First-time full data download to local SQLite |
| `update_daily_data` | Daily incremental data refresh |
| `get_data_status` | Database integrity check |
| `screen_stocks` | Universal multi-condition screening (price/PE/PB/cap/volume/sector/name) |
| `get_kline_local_or_net` | Stock K-line with auto-cached indicators |
| `get_rank_trend_data` | Historical popularity ranking trend |
| `get_sector_list` | Concept/industry sector browser |
| `get_stock_belong_sectors` | Reverse: stock → its sectors |
| `generate_stock_report` | Full analysis report (trend/support/resistance/risk/position) |

## Skills (3)

- `eastmoney-quant-data-init` — Database setup guide
- `eastmoney-quant-stock-screening` — Screening condition templates
- `eastmoney-quant-report-generation` — Report formatting & interpretation

## Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `EASTMONEY_PYTHON` | Python interpreter path | `python` |
| `EASTMONEY_STOCK_DATA_DIR` | Stock DB directory | `~/Desktop/股票信息` |
| `EASTMONEY_SECTOR_DATA_DIR` | Sector DB directory | `~/Desktop/分析板块` |
| `EASTMONEY_COOKIE` | Manual cookie for Eastmoney APIs | Auto-extract from Edge browser |

## Cookie adaptation

The HTTP client auto-extracts Eastmoney cookies from Edge browser (Windows) to improve API access:

1. Reads `%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Network\Cookies`
2. Filters for eastmoney/dfcf domains
3. Falls back to `EASTMONEY_COOKIE` env var if Edge is locked or cookies are encrypted

## Installation

### npx (recommended)

```bash
claude mcp add eastmoney-quant -- npx eastmoney-quant-mcp
```

### npm global

```bash
npm install -g eastmoney-quant-mcp
```

### pip

```bash
pip install eastmoney-quant-mcp
```

### From source

```bash
git clone https://github.com/lalal-zzz/eastmoney-quant-mcp.git
cd eastmoney-quant-mcp
npm install    # auto runs pip install -e .
```

## MCP client config

### Claude Code

```bash
claude mcp add eastmoney-quant -- npx eastmoney-quant-mcp
```

### Claude Desktop

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

### opencode / Codex

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

### Direct python

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

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
