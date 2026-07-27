[中文版](#中文版)

# Eastmoney Quant MCP Server

[![npm version](https://img.shields.io/npm/v/eastmoney-quant-mcp.svg)](https://www.npmjs.com/package/eastmoney-quant-mcp)
[![Python](https://img.shields.io/pypi/pyversions/eastmoney-quant-mcp.svg)](https://pypi.org/project/eastmoney-quant-mcp/)
[![License](https://img.shields.io/github/license/lalal-zzz/eastmoney-quant-mcp)](LICENSE)

A-share quantitative analysis MCP server powered by **Eastmoney** (eastmoney.com) public APIs. Provides professional stock data analysis for Claude Desktop / Claude Code / Codex / opencode.

## Core Capabilities

| Capability | Details |
|------------|---------|
| Market Data | 5530+ A-shares real-time: price / change% / PE / PB / market cap / volume ratio / turnover |
| K-lines | Daily OHLCV with forward/backward/no adjustment |
| Indicators | MA(5~200) / RSI(6/14/24) / MACD / BOLL / KDJ / ATR / VOL_MA |
| Popularity | Eastmoney real-time sentiment rankings + historical trends |
| Sectors | ~400 concepts + ~80 industries with capital flow (super-large/large/medium/small net) |
| Screening | 18 composable conditions: price range / PE / PB / cap / change% / volume / turnover / sector filter |
| Reports | Full technical analysis: trend / support & resistance / risk assessment / stop-loss & position advice |

All data sourced from **Eastmoney** (eastmoney.com) public APIs.

---

## Quick Install

```bash
# Claude Code (recommended)
claude mcp add eastmoney-quant -- npx eastmoney-quant-mcp

# or npm global
npm install -g eastmoney-quant-mcp

# or pip
pip install eastmoney-quant-mcp
```

**Requirements**: Python >= 3.10 | Node.js >= 18

---

## Data Details

### Stock Market Data

| Category | Fields |
|----------|--------|
| Basics | Latest price, open, previous close, high, low |
| Change | Change%, change amount, amplitude, velocity |
| Volume | Volume, turnover amount |
| Activity | Volume ratio, turnover rate |
| Valuation | Dynamic PE, PB, TTM PE |
| Market Cap | Total market cap, circulating market cap |
| Trend | 60-day change%, YTD change% |
| Fund Flow | Net major capital inflow |

### K-line Data

| Category | Details |
|----------|---------|
| Daily K-line | Open, high, low, close, volume, amount |
| Adjustment | Forward (qfq) / backward (hfq) / none |
| Extra Fields | Change%, turnover rate, amplitude |

### Technical Indicators (auto-calculated)

| Category | Indicators |
|----------|------------|
| Moving Avg | MA5, MA10, MA20, MA30, MA60, MA100, MA200 |
| RSI | RSI6, RSI14, RSI24 |
| MACD | DIF, DEA, MACD histogram |
| Bollinger | Upper, middle, lower bands |
| KDJ | K, D, J values |
| Volatility | ATR14 |
| Volume | VOL_MA5, VOL_MA10 |

### Popularity Rankings

| Category | Details |
|----------|---------|
| Rankings | Eastmoney real-time popularity list (rank / price / change% / volume ratio / turnover) |
| Trends | Historical ranking trend for any stock over N days |

### Sector Data

| Category | Details |
|----------|---------|
| Sector List | ~400 concept sectors + ~80 industry sectors |
| Sector Quotes | Sector index, change% |
| Capital Flow | Major net inflow, super-large/large/medium/small net inflow (with % share) |
| Leading Stocks | Top stocks in each sector |
| Sector K-line | Historical sector index trends |
| Sector Members | Individual stock quotes / turnover / volume ratio / PE / PB |

### Analysis Reports

| Module | Content |
|--------|---------|
| Basics | Price, change%, PE, PB, market cap, volume ratio, turnover |
| Trend | MA alignment, 5/10/20/60-day change%, direction assessment |
| Indicators | RSI state, MACD golden/death cross, KDJ overbought/oversold, BOLL position, ATR volatility |
| Support/Resistance | MA support/resistance + BOLL bands, sorted by strength |
| Risk | Overbought/oversold, volatility, valuation, liquidity, trend breakdown risks |
| Position | Stop-loss, take-profit, risk/reward ratio, position sizing advice |

---

## MCP Tools (9)

| Tool | Purpose |
|------|---------|
| `init_full_data` | One-time full download: stocks + sectors to local SQLite |
| `update_daily_data` | Daily incremental refresh (quotes / rankings / sectors) |
| `get_data_status` | View local DB status (record count / last update / storage path) |
| `screen_stocks` | Universal multi-condition screening (18 conditions + sector filter + name search + sort) |
| `get_kline_local_or_net` | K-line with auto-cached technical indicators (local first, network fallback) |
| `get_rank_trend_data` | Historical popularity ranking trend for any stock |
| `get_sector_list` | Browse concept/industry sectors with capital flow data |
| `get_stock_belong_sectors` | Reverse lookup: which sectors a stock belongs to |
| `generate_stock_report` | Full analysis report: trend / support-resistance / risk / position |

Plus 3 Claude Skills that teach the AI how to compose these tools for complex workflows.

---

## Local Database

Data is stored in local SQLite databases. After initial setup, queries are extremely fast with no network needed:

| Database | Default Path | Content |
|----------|-------------|---------|
| Stock DB | `~/Desktop/stock_data/stock_data.db` | 5530 stocks: quotes + K-lines + rankings + indicators |
| Sector DB | `~/Desktop/sector_data/sector_data.db` | 480+ sectors: quotes + capital flow + K-lines + members |

Customize paths via `EASTMONEY_STOCK_DATA_DIR` and `EASTMONEY_SECTOR_DATA_DIR` env vars.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `EASTMONEY_PYTHON` | `python` | Python interpreter path |
| `EASTMONEY_STOCK_DATA_DIR` | `~/Desktop/股票信息` | Stock database directory |
| `EASTMONEY_SECTOR_DATA_DIR` | `~/Desktop/分析板块` | Sector database directory |
| `EASTMONEY_COOKIE` | Auto-extract from Edge | Eastmoney API cookies (improves request success rate) |

---

## Client Configuration

### Claude Desktop / Claude Code

```bash
claude mcp add eastmoney-quant -- npx eastmoney-quant-mcp
```

Or manually edit `claude_desktop_config.json`:

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

### Direct Python

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

## Usage Examples

```python
# 1. First-time init (~10 min, one-time only)
init_full_data(include_sector_members=True)

# 2. Daily update after market close (~2 min)
update_daily_data()

# 3. Screen: stocks with change% >3%, PE<30, volume ratio >1.5
screen_stocks({"min_change_pct":3, "max_pe":30, "min_volume_ratio":1.5})

# 4. Screen: semiconductor sector, PE<50, sorted by popularity
screen_stocks({"max_pe":50}, sector_code="BK1090", sort_by="popularity_rank")

# 5. Screen: search stocks with "bank" in name
screen_stocks(name_keyword="bank")

# 6. Get Ping An Bank K-line with cached indicators
get_kline_local_or_net("000001", days=250)

# 7. Ping An Bank 30-day popularity trend
get_rank_trend_data("000001", days=30)

# 8. Generate full analysis report
generate_stock_report("000001")
# Returns: trend / support-resistance / risk level / position advice
```

---

## Development

```bash
git clone https://github.com/lalal-zzz/eastmoney-quant-mcp.git
cd eastmoney-quant-mcp
pip install -e ".[dev]"
pytest
```

## License

MIT License

---

# 中文版

# 东方财富量化 MCP 服务

[![npm version](https://img.shields.io/npm/v/eastmoney-quant-mcp.svg)](https://www.npmjs.com/package/eastmoney-quant-mcp)
[![Python](https://img.shields.io/pypi/pyversions/eastmoney-quant-mcp.svg)](https://pypi.org/project/eastmoney-quant-mcp/)
[![License](https://img.shields.io/github/license/lalal-zzz/eastmoney-quant-mcp)](LICENSE)

基于**东方财富网**公开数据的 A 股量化分析 MCP 服务，为 Claude Desktop / Claude Code / Codex / opencode 等 AI 客户端提供专业的股票数据分析能力。

## 核心能力

| 能力 | 说明 |
|------|------|
| 全市场行情 | 5530+ 只 A 股实时价格 / 涨跌幅 / PE / PB / 市值 / 量比 / 换手率 |
| 历史 K 线 | 日线数据（开高低收量额），支持前复权/后复权/不复权 |
| 技术指标 | MA(5~200) / RSI(6/14/24) / MACD / BOLL / KDJ / ATR / VOL_MA |
| 人气排名 | 东方财富人气榜单 + 历史排名趋势追踪 |
| 板块分析 | 概念板块(~400个) + 行业板块(~80个)，含主力资金流向(超大单/大单/中单/小单) |
| 多条件选股 | 18 种条件自由组合：价格区间 / PE / PB / 市值 / 涨跌幅 / 量比 / 换手 / 振幅 / 板块限定 |
| 分析报告 | 综合技术分析：趋势判断 / 支撑位与阻力位 / 风险等级评估 / 止损止盈与仓位建议 |

所有数据来源于 **东方财富网** (eastmoney.com) 公开 API。

---

## 快速安装

```bash
# Claude Code 一键安装（推荐）
claude mcp add eastmoney-quant -- npx eastmoney-quant-mcp

# 或 npm 全局安装
npm install -g eastmoney-quant-mcp

# 或 pip 安装
pip install eastmoney-quant-mcp
```

**前置要求**: Python >= 3.10 | Node.js >= 18

---

## 数据详情

### 股票行情数据

| 数据项 | 字段 |
|--------|------|
| 基础行情 | 最新价、今开、昨收、最高、最低 |
| 涨跌 | 涨跌幅、涨跌额、振幅、涨速 |
| 成交 | 成交量、成交额 |
| 活跃度 | 量比、换手率 |
| 估值 | 动态市盈率(PE)、市净率(PB)、TTM 市盈率 |
| 市值 | 总市值、流通市值 |
| 趋势 | 60 日涨跌幅、年初至今涨跌幅 |
| 资金 | 主力资金净流入 |

### 股票 K 线数据

| 数据项 | 说明 |
|--------|------|
| 日线 K 线 | 开盘价、最高价、最低价、收盘价、成交量、成交额 |
| 复权方式 | 前复权(qfq) / 后复权(hfq) / 不复权 |
| 附加字段 | 涨跌幅、换手率、振幅 |

### 技术指标 (自动计算)

| 类别 | 指标 |
|------|------|
| 均线 | MA5、MA10、MA20、MA30、MA60、MA100、MA200 |
| 相对强弱 | RSI6、RSI14、RSI24 |
| MACD | DIF、DEA、MACD 柱 |
| 布林带 | 上轨、中轨、下轨 (BOLL) |
| KDJ | K、D、J 值 |
| 波动率 | ATR14 (平均真实波幅) |
| 量能 | VOL_MA5、VOL_MA10 |

### 人气排名数据

| 数据项 | 说明 |
|--------|------|
| 人气排名 | 东方财富实时人气榜单 (排名/价格/涨跌幅/量比/换手率) |
| 历史趋势 | 支持查询任意股票 N 天内的人气排名变化走势 |

### 板块数据

| 数据项 | 说明 |
|--------|------|
| 板块列表 | 概念板块(~400个) + 行业板块(~80个) |
| 板块行情 | 板块指数、涨跌幅 |
| 资金流向 | 主力净流入、超大单净流入、大单净流入、中单净流入、小单净流入 (含占比%) |
| 领涨股 | 板块龙头股票 |
| 板块 K 线 | 板块历史指数走势 |
| 板块成分股 | 每只成分股的行情/换手率/量比/PE/PB |

### 分析报告

| 模块 | 内容 |
|------|------|
| 基础信息 | 价格、涨跌幅、PE、PB、市值、量比、换手率 |
| 趋势分析 | 均线排列状态、5/10/20/60 日涨跌幅、方向判断 |
| 技术指标 | RSI 状态、MACD 金叉死叉、KDJ 超买超卖、BOLL 位置、ATR 波幅 |
| 支撑阻力 | 均线支撑/阻力位 + BOLL 上下轨，按强度排序 |
| 风险评估 | 超买超卖风险、波动率风险、估值风险、流动性风险、趋势破位风险 |
| 仓位管理 | 止损位、止盈位、风险收益比、仓位比例建议 |

---

## MCP 工具 (9 个)

| 工具 | 功能 |
|------|------|
| `init_full_data` | 首次全量下载股票+板块数据到本地 SQLite 数据库 |
| `update_daily_data` | 增量每日刷新（行情/排名/板块） |
| `get_data_status` | 查看本地数据库状态（数据量/更新时间/存储路径） |
| `screen_stocks` | 万能多条件选股：18 种条件自由组合(价格/PE/PB/市值/涨跌幅/量比/换手/振幅)，支持板块限定、名称搜索、多字段排序 |
| `get_kline_local_or_net` | 获取个股历史 K 线（本地优先，不足自动下载并缓存技术指标） |
| `get_rank_trend_data` | 查询个股 N 天内的人气排名历史走势 |
| `get_sector_list` | 获取概念/行业板块列表及其行情数据 |
| `get_stock_belong_sectors` | 反向查询：某只股票属于哪些板块 |
| `generate_stock_report` | 生成个股综合分析报告（趋势/支撑阻力/风险等级/仓位建议） |

附带 3 个 Claude Skill，教授 AI 如何组合使用这些工具完成复杂选股和报告工作流。

---

## 本地数据库

数据存储在本地 SQLite 数据库中，首次初始化后查询速度极快，无需联网：

| 数据库 | 默认路径 | 内容 |
|--------|----------|------|
| 股票数据库 | `~/Desktop/股票信息/stock_data.db` | 5530 只股票行情 + K 线 + 人气排名 + 技术指标 |
| 板块数据库 | `~/Desktop/分析板块/sector_data.db` | 480+ 板块行情 + 资金流向 + K 线 + 成分股 |

可通过环境变量 `EASTMONEY_STOCK_DATA_DIR` 和 `EASTMONEY_SECTOR_DATA_DIR` 自定义路径。

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `EASTMONEY_PYTHON` | `python` | Python 解释器路径 |
| `EASTMONEY_STOCK_DATA_DIR` | `~/Desktop/股票信息` | 股票数据库目录 |
| `EASTMONEY_SECTOR_DATA_DIR` | `~/Desktop/分析板块` | 板块数据库目录 |
| `EASTMONEY_COOKIE` | 自动从 Edge 提取 | 东方财富 API Cookie（提升请求成功率） |

---

## 客户端配置

### Claude Desktop / Claude Code

```bash
claude mcp add eastmoney-quant -- npx eastmoney-quant-mcp
```

或手动编辑 `claude_desktop_config.json`：

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

### 直接 Python 运行

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

## 使用示例

```python
# 1. 首次初始化数据库（约 10 分钟，只需一次）
init_full_data(include_sector_members=True)

# 2. 每日收盘后更新（约 2 分钟）
update_daily_data()

# 3. 选股：找涨幅>3%、PE<30、量比>1.5 的放量突破股
screen_stocks({"min_change_pct":3, "max_pe":30, "min_volume_ratio":1.5})

# 4. 选股：芯片板块内 PE<50 的股票，按人气排名排序
screen_stocks({"max_pe":50}, sector_code="BK1090", sort_by="popularity_rank")

# 5. 选股：搜索名称含"银行"的股票
screen_stocks(name_keyword="银行")

# 6. 获取平安银行 K 线并缓存技术指标
get_kline_local_or_net("000001", days=250)

# 7. 查看平安银行近 30 天人气变化
get_rank_trend_data("000001", days=30)

# 8. 生成平安银行综合分析报告
generate_stock_report("000001")
# 返回：趋势/支撑阻力/风险等级/仓位建议
```

---

## 开发

```bash
git clone https://github.com/lalal-zzz/eastmoney-quant-mcp.git
cd eastmoney-quant-mcp
pip install -e ".[dev]"
pytest
```

## 许可证

MIT License
