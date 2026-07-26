# 东方财富量化 MCP 服务 | Eastmoney Quant MCP

[![npm version](https://img.shields.io/npm/v/eastmoney-quant-mcp.svg)](https://www.npmjs.com/package/eastmoney-quant-mcp)
[![Python](https://img.shields.io/pypi/pyversions/eastmoney-quant-mcp.svg)](https://pypi.org/project/eastmoney-quant-mcp/)
[![License](https://img.shields.io/github/license/lalal-zzz/eastmoney-quant-mcp)](LICENSE)

基于东方财富数据的 A 股量化分析 MCP 服务。本地 SQLite 存储，支持多条件选股、板块分析、人气排名追踪，以及包含支撑位/阻力位/风险评估/仓位管理的综合技术分析报告。

A-share quantitative analysis MCP server powered by Eastmoney data. Local SQLite storage, multi-condition stock screening, sector analysis, popularity ranking trends, and comprehensive technical reports with support/resistance/risk/position advice.

---

## 安装 / Install

```bash
# 推荐 / Recommended
claude mcp add eastmoney-quant -- npx eastmoney-quant-mcp

# 或全局安装 / Or global install
npm install -g eastmoney-quant-mcp

# 或 pip 安装 / Or pip install
pip install eastmoney-quant-mcp
```

前置条件 / Prerequisites: Python >= 3.10 | Node.js >= 18

---

## MCP 工具 / Tools (9)

| 工具 Tool | 说明 Description |
|-----------|-----------------|
| `init_full_data` | 首次全量下载到本地数据库 / First-time full data download |
| `update_daily_data` | 增量每日更新 / Daily incremental refresh |
| `get_data_status` | 数据库完整性检查 / Database integrity check |
| `screen_stocks` | 万能多条件选股(价格/PE/PB/市值/量比/板块/名称) / Universal screening |
| `get_kline_local_or_net` | 获取个股K线(自动缓存技术指标) / K-line with auto-cached indicators |
| `get_rank_trend_data` | 人气排名历史趋势 / Historical popularity trend |
| `get_sector_list` | 概念/行业板块列表 / Concept and industry sectors |
| `get_stock_belong_sectors` | 反查股票所属板块 / Reverse: stock to its sectors |
| `generate_stock_report` | 综合分析报告(趋势/支撑阻力/风险/仓位) / Full analysis report |

---

## 技能 / Skills (3)

| 技能 Skill | 触发时机 When to use |
|-----------|---------------------|
| `eastmoney-quant-data-init` | 首次初始化数据库 / First-time database setup |
| `eastmoney-quant-stock-screening` | 多条件选股 / Stock screening |
| `eastmoney-quant-report-generation` | 生成分析报告 / Generate analysis reports |

---

## 环境变量 / Environment Variables

| 变量 Variable | 用途 Purpose | 默认值 Default |
|---------------|-------------|---------------|
| `EASTMONEY_PYTHON` | Python 解释器路径 / Python path | `python` |
| `EASTMONEY_STOCK_DATA_DIR` | 股票数据库目录 / Stock DB dir | `~/Desktop/股票信息` |
| `EASTMONEY_SECTOR_DATA_DIR` | 板块数据库目录 / Sector DB dir | `~/Desktop/分析板块` |
| `EASTMONEY_COOKIE` | 东方财富 Cookie 手动指定 / Manual cookie | 自动从 Edge 提取 / Auto from Edge |

---

## Cookie 适应 / Cookie Adaptation

HTTP 客户端自动从 Edge 浏览器提取东方财富 Cookie，提升 API 请求成功率：

1. 读取 `%LOCALAPPDATA%\...\Edge\User Data\Default\Network\Cookies` (SQLite)
2. 筛选 `eastmoney` 或 `dfcf` 域名相关 Cookie
3. 如 Edge 运行中(DB锁定)或 Cookie 已加密，回退到 `EASTMONEY_COOKIE` 环境变量

The HTTP client auto-extracts Eastmoney cookies from Edge browser:

1. Reads Edge's cookie SQLite database
2. Filters for eastmoney/dfcf domains
3. Falls back to `EASTMONEY_COOKIE` env var if Edge is locked or cookies encrypted

---

## 客户端配置 / Client Config

### Claude Desktop / Claude Code

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

### Codex / opencode

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

### 直接 Python / Direct Python

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

## 快速开始 / Quick Start

```bash
# 1. 初始化数据库 (首次, 约10分钟) / Init database (first time, ~10min)
init_full_data(include_sector_members=True)

# 2. 每日更新 (收盘后, 约2分钟) / Daily update (after market close, ~2min)
update_daily_data()

# 3. 选股 / Screen stocks
screen_stocks({"min_change_pct":3, "max_pe":30, "min_volume_ratio":1.5})

# 4. 分析报告 / Analysis report
generate_stock_report("000001")
```

---

## 开发 / Development

```bash
pip install -e ".[dev]"
pytest
```

---

## 发布 / Publishing

```bash
# npm
npm login
npm publish --access public

# PyPI
python -m build
python -m twine upload dist/*
```

---

## 许可证 / License

MIT
