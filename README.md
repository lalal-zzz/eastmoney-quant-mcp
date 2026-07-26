# 东方财富量化 MCP 服务

[![npm version](https://img.shields.io/npm/v/eastmoney-quant-mcp.svg)](https://www.npmjs.com/package/eastmoney-quant-mcp)
[![Python](https://img.shields.io/pypi/pyversions/eastmoney-quant-mcp.svg)](https://pypi.org/project/eastmoney-quant-mcp/)
[![License](https://img.shields.io/github/license/lalal-zzz/eastmoney-quant-mcp)](LICENSE)

基于东方财富数据的 A 股量化分析 MCP (Model Context Protocol) 服务。为 Claude Desktop、Claude Code、Codex、opencode 等 AI 助手提供股票数据下载、人气榜单、板块分析和形态选股能力。

## 一键安装 (npx，推荐)

```bash
# Claude Code 一键安装
claude mcp add eastmoney-quant -- npx eastmoney-quant-mcp

# 或手动添加到配置文件
```

前置条件: Python >= 3.10 + Node.js >= 18

## 功能特性

### 股票数据
- 获取 A 股全部股票列表
- 下载历史 K 线数据（日线，支持前/后复权）
- 获取实时行情（价格/涨跌幅/量比/换手/PE/PB/市值）
- 计算技术指标（MA/RSI/MACD/BOLL/KDJ/ATR）

### 人气榜单
- 东方财富人气排名榜
- 按涨幅排序的人气榜
- 按成交量排序的人气榜
- 按换手率排序的人气榜

### 板块数据
- 概念/行业板块列表及行情
- 板块主力资金净流入
- 板块成分股详情
- 板块历史 K 线

### 形态选股
- 超跌反弹扫描
- 放量突破扫描
- 强势突破扫描
- 低估值成长扫描
- 多头排列扫描

### 板块选择
- 涨跌幅最强板块
- 主力净流入最强板块
- 强势板块 + 龙头成分股
- 板块综合分析

## 安装方式

### 方式一: npx 一键安装 (推荐)

```bash
# Claude Code 自动配置
claude mcp add eastmoney-quant -- npx eastmoney-quant-mcp

# Claude Desktop / 其他客户端: 手动编辑配置
```

### 方式二: npm 全局安装

```bash
npm install -g eastmoney-quant-mcp
```

### 方式三: pip 安装

```bash
pip install eastmoney-quant-mcp
```

### 方式四: 源码安装

```bash
git clone https://github.com/lalal-zzz/eastmoney-quant-mcp.git
cd eastmoney-quant-mcp
npm install    # 自动 pip install -e .
```

## MCP 客户端配置

### Claude Code

```bash
claude mcp add eastmoney-quant -- npx eastmoney-quant-mcp
```

### Claude Desktop

在 `%APPDATA%\Claude\claude_desktop_config.json` (Windows) 或 `~/.config/claude/claude_desktop_config.json` (Mac/Linux) 中添加:

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

### Codex

```yaml
mcpServers:
  eastmoney-quant:
    command: npx
    args:
      - eastmoney-quant-mcp
```

### opencode

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

### 使用 python 命令 (备选)

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

## MCP + Skill 组合使用

本项目同时提供 MCP 服务端和 Skill 指导文件。安装 Skill 后，AI 助手会自动获得形态选股和板块选择工作流指导。

```bash
# Claude Code
mkdir -p ~/.claude/skills/eastmoney-quant
cp src/eastmoney_quant_mcp/skill/SKILL.md ~/.claude/skills/eastmoney-quant/

# Claude Desktop
mkdir -p ~/.claude/skills/eastmoney-quant
cp src/eastmoney_quant_mcp/skill/SKILL.md ~/.claude/skills/eastmoney-quant/

# opencode
mkdir -p ~/.agents/skills/eastmoney-quant
cp src/eastmoney_quant_mcp/skill/SKILL.md ~/.agents/skills/eastmoney-quant/
```

## MCP 工具列表

| 工具名 | 说明 |
|--------|------|
| `get_stock_list` | 获取 A 股全部股票列表 |
| `get_stock_history` | 获取股票历史 K 线 |
| `get_latest_indicators` | 获取全市场实时行情 |
| `get_stock_indicators` | 获取股票 K 线 + 技术指标 |
| `search_stock` | 模糊搜索股票 |
| `get_popularity_rankings` | 获取人气排名榜 |
| `get_top_gainers_rank` | 涨幅最高人气榜 |
| `get_top_volume_rank` | 成交量最大人气榜 |
| `get_top_turnover_rank` | 换手率最高人气榜 |
| `get_sector_list` | 获取板块列表及行情 |
| `get_sector_members` | 获取板块成分股 |
| `get_sector_kline` | 获取板块 K 线 |
| `screen_by_pattern` | 按技术形态选股 |
| `get_pattern_list` | 查看可选形态列表 |
| `screen_top_sectors` | 涨跌幅最强板块 |
| `screen_main_inflow_sectors` | 主力净流入最强板块 |
| `screen_sector_with_leaders` | 强势板块 + 龙头股 |
| `get_full_sector_analysis` | 板块综合分析 |

## 发布到 MCP 官方插件市场

### 步骤 1: 发布到 npm

```bash
npm login
npm publish --access public
```

### 步骤 2: 发布到 PyPI

```bash
python -m pip install --upgrade build twine
python -m build
python -m twine upload dist/*
```

### 步骤 3: 提交到 MCP 官方市场

在 [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) 仓库提交 PR，将以下配置添加到 `servers.json`:

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

同时添加 README 链接和描述到 `servers/` 目录。

### 步骤 4: 发布到 Smithery

在 [Smithery](https://smithery.ai) 注册并发布，提供 `.mcp.json` 中的配置信息。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `EASTMONEY_PYTHON` | Python 解释器路径 | `python` |

## 开发

```bash
git clone https://github.com/lalal-zzz/eastmoney-quant-mcp.git
cd eastmoney-quant-mcp
pip install -e ".[dev]"
pytest
```

## 许可证

MIT License
