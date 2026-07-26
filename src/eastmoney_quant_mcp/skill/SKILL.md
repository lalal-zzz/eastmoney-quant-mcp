# 东方财富量化 MCP — 主技能

## 技能体系

三个子技能形成完整分析链路，按顺序依次调用:

```
eastmoney-quant-data-init         eastmoney-quant-stock-screening    eastmoney-quant-report-generation
(数据初始化与管理)     ──────────→ (多条件选股)          ──────────→  (个股分析报告)
       │                              │                                    │
  初始化 SQLite 数据库           查询 stock_spot + sector_member    查询 stock_kline + stock_indicators
  下载全量历史数据               筛选符合条件的股票                  计算支撑/阻力/风险/仓位
       │                              │                                    │
       └── get_data_status ───────────┴── generate_stock_report ───────────┘
          检查数据是否就绪                生成综合分析报告
```

**技能间交互规则**:
- 选股技能发现 `get_data_status` 数据为空 → 自动引导到初始化技能
- 选股结果输出 Top N 后 → 引导到报告技能深度分析
- 报告技能检测 K 线不足 → 自动触发下载再生成

## 数据库架构总览

### 股票 DB (`stock_data.db`)

```
stock_basic ──── 股票列表 (symbol, name)
stock_spot  ──── 实时行情快照 ★选股核心表★
stock_rank  ──── 历史人气排名 (每日追加)
stock_kline ──── K线数据 (按需下载)
stock_indicators ─ 技术指标 ★报告核心表★ (下载K线时自动计算)
```

### 板块 DB (`sector_data.db`)

```
sector_basic  ── 板块行情 + 资金流向
sector_kline  ── 板块K线历史
sector_member ── 板块成分股 ★板块→股票关键表★
```

### 数据流

```
网络API(akshare)
    │
    ├─ init_full_data ──→ stock_basic + stock_spot + stock_rank
    │                  └─→ sector_basic + sector_kline + sector_member
    │
    ├─ update_daily_data ──→ 增量刷新所有表
    │
    └─ get_kline_local_or_net ──→ stock_kline + stock_indicators (自动计算)
```

## 工具总览

| 类别 | 工具 | 数据源 |
|------|------|--------|
| 数据管理 | `init_full_data` `update_daily_data` `get_data_status` | 网络 → 本地 |
| K线管理 | `get_kline_local_or_net` `batch_download_kline` `download_top_klines` | 本地+网络 |
| 多条件选股 | `screen_stocks` | 本地 |
| 形态选股 | `screen_by_pattern` `get_pattern_list` | 网络 |
| 股票搜索 | `search_stock_full` `search_stock` | 本地+网络 |
| 实时行情 | `get_latest_indicators` | 网络 |
| 股票K线+指标 | `get_stock_indicators` `get_stock_history` | 网络 |
| 人气排名 | `get_popularity_rankings` `get_top_gainers_rank` `get_top_volume_rank` `get_top_turnover_rank` | 网络 |
| 历史人气 | `get_rank_history` `get_rank_trend_data` | 本地 |
| 板块搜索 | `search_sector_full` `get_sector_list` | 本地/网络 |
| 板块K线 | `get_sector_kline` `get_sector_kline_local` | 网络/本地 |
| 板块排行 | `get_top_sectors_rank` `screen_top_sectors` `screen_main_inflow_sectors` | 本地/网络 |
| 板块→股票 | `get_sector_members_flow` `screen_sector_with_leaders` `get_full_sector_analysis` | 本地/网络 |
| 股票→板块 | `get_stock_belong_sectors` `get_sector_members` | 本地/网络 |
| 分析报告 | `generate_stock_report` | 本地 |

## 快速开始

```bash
# 1. 安装
claude mcp add eastmoney-quant -- npx eastmoney-quant-mcp

# 2. 初始化 (首次)
init_full_data(include_sector_members=True)

# 3. 每日更新
update_daily_data()

# 4. 选股 + 报告
screen_stocks({"min_change_pct":3,"max_pe":30})
generate_stock_report("000001")
```
