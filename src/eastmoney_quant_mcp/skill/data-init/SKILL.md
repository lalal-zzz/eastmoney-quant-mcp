# 数据初始化与管理技能 (Data Init & Management)

## 角色

你负责帮助用户设置和维护东方财富量化本地数据库。这是**选股和报告生成的前置条件**。

## 与其它技能的连接

```
本技能(data-init)  → 初始化数据库
         ↓
stock-screening  → 使用 stock_spot / sector_member 表做多条件选股
         ↓
report-generation → 使用 stock_kline + stock_indicators 表生成报告
```

选股和报告技能**无法工作**，直到本技能完成初始化。当用户输入到达选股或报告技能时，若检测到 `get_data_status` 返回数据为空，应引导回本技能。

---

## 数据库结构 (SQLite)

### 股票数据库 `stock_data.db` — 共 5 张表

| 表名 | 主键 | 关键字段 | 来源 |
|------|------|----------|------|
| `stock_basic` | symbol | symbol, name | `init_full_data` |
| `stock_spot` | symbol | symbol, name, latest_price, change_pct, volume_ratio, turnover_rate, pe_dynamic, pb, total_market_cap, float_market_cap, sixty_day_change, ytd_change, amplitude | `init_full_data` / `update_daily_data` |
| `stock_rank` | rank_date + symbol | symbol, name, rank_date, popularity_rank, change_pct, latest_price | `init_full_data` / `update_daily_data` (每日追加) |
| `stock_kline` | symbol + date | symbol, date, open, high, low, close, volume, amount, change_pct, turnover_rate | `get_kline_local_or_net` / `batch_download_kline` (按需) |
| `stock_indicators` | symbol + date | symbol, date, MA5~MA200, RSI6/14/24, DIF/DEA/MACD, BOLL_UPPER/MIDDLE/LOWER, KDJ_K/D/J, VOL_MA5/10, ATR14 | 自动计算(下载K线时) |

**表间关系**:
- `stock_spot` 是核心选股表，包含每只股票的最新快照
- `stock_rank` 按日期累计历史人气排名
- `stock_kline` + `stock_indicators` 是报告生成的数据源，按 `symbol+date` 关联

### 板块数据库 `sector_data.db` — 共 3 张表

| 表名 | 主键 | 关键字段 | 来源 |
|------|------|----------|------|
| `sector_basic` | sector_code | sector_code, sector_name, sector_type, change_pct, main_net_inflow, large_net, lead_stock_name/code | `init_full_data` / `update_daily_data` |
| `sector_kline` | sector_code + trade_date | sector_code, trade_date, open, close, high, low, volume, change_pct | `init_full_data` / `update_daily_data` |
| `sector_member` | sector_code + stock_code | sector_code, stock_code, stock_name, latest_price, change_pct, turnover_rate, volume_ratio, pe_dynamic, pb | `init_full_data` (include_sector_members=True) |

**表间关系**:
- `sector_member` 实现 板块→股票 查找：给定 sector_code 查成员 stock_code 列表
- 结合 `stock_spot` 实现：板块内多条件选股

---

## 初始化工作流

### 第一步: 确认存储位置

引导用户确认数据库存放路径。默认使用桌面，可自定义:

```
默认路径:
  股票数据 → ~/Desktop/股票信息/
  板块数据 → ~/Desktop/分析板块/

如需更改，设置环境变量:
  EASTMONEY_STOCK_DATA_DIR=D:\my-data\stocks
  EASTMONEY_SECTOR_DATA_DIR=D:\my-data\sectors
```

### 第二步: 全量下载

```
init_full_data(include_sector_members=True)
```

**下载内容**(按顺序)及对应工具:
1. 股票列表(~5000只) → 写入 `stock_basic`
2. 全市场实时行情 → 写入 `stock_spot` (选股核心表)
3. 人气排名榜单 → 写入 `stock_rank`
4. 概念板块(~400个) + 行业板块(~80个) → 写入 `sector_basic`
5. 所有板块K线(近250日) → 写入 `sector_kline`
6. 所有板块成分股(仅 `include_sector_members=True`) → 写入 `sector_member`

**耗时估算**:
- 不含成分股: 约 2-5 分钟
- 含成分股: 约 10-20 分钟

### 第三步: 验证

```
get_data_status()
```

返回每张表的记录数和最后更新日期。全为 `None` 说明初始化失败。

---

## 日常维护

### 每日更新
```
update_daily_data(include_sector_members=True)   # 收盘后, ~5-15分钟
update_daily_data(include_sector_members=False)  # 盘中快速刷新, ~1-3分钟
```

### K 线按需下载(下载时自动计算技术指标)

```
get_kline_local_or_net(symbol="000001", days=365)       # 单只
batch_download_kline(symbols="000001,600000", days=365) # 批量
download_top_klines(top_n=200)                           # 人气前200只
```

## 下一步

初始化完成后, 引导用户到:
- **选股技能**: `eastmoney-quant-stock-screening` — 用 `screen_stocks` 开始筛选
- **报告技能**: `eastmoney-quant-report-generation` — 用 `generate_stock_report` 分析个股
