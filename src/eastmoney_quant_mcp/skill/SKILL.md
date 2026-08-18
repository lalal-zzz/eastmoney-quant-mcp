---
name: eastmoney-quant
description: Local-first A-share data and research workflows. Use for Chinese stock data initialization, daily updates, screening, sector research, and evidence-based reports.
---

# 东方财富数据研究中心

先检查 `get_data_status`。数据未初始化时引导用户执行初始化；数据过期时说明日期并建议每日更新。不要假定实时数据已经可用。

对研究任务使用“宽筛 → 个股/板块验证 → 报告”的顺序：先筛选候选，再获取需要的日线、排名和板块背景，最后生成可追溯结论。报告必须写明数据日期、数据缺失和风险，不能输出确定性的买卖或仓位指令。

## 工具速查（14 个）

| 工具 | 用途 |
|------|------|
| `init_full_data` | 首次初始化（优先 `quick=True`，秒级可用） |
| `update_daily_data` | 每日增量更新（建议收盘后） |
| `get_data_status` | 本地数据库状态（任何研究前先调用） |
| `screen_stocks` | 万能选股：18 条件 + 板块限定 + 名称搜索 + 排序 |
| `get_kline_local_or_net` | 个股日线（本地优先，自动缓存技术指标） |
| `get_stock_kline_period` | 多周期 K 线：1/5/15/30/60 分钟 + 日/周/月（网络实时） |
| `get_rank_trend_data` | 个股人气排名历史趋势 |
| `get_sector_list` | 概念/行业板块列表及资金流向 |
| `get_stock_belong_sectors` | 反查个股所属板块 |
| `generate_stock_report` | 个股综合分析报告（趋势/支撑阻力/风险/仓位） |
| `scan_patterns` | 股票形态扫描：五类上涨形态 + 评分/关键位/共振 |
| `scan_sector_patterns` | 板块形态扫描（概念/行业，历史不足自动跳过） |
| `get_pattern_history` | 单标的（股票/板块）历史形态信号列表 |
| `get_key_levels` | 单标的当前关键位（MA/斐波那契/结构位/趋势） |

形态扫描工作流：先 `scan_patterns` 全市场宽筛 → `get_key_levels` 验证候选关键位 → `get_pattern_history` 查历史信号频率 → `generate_stock_report` 出报告。板块侧重型任务用 `scan_sector_patterns` 先找板块信号再下沉个股。

详细流程见子 Skill：`eastmoney-quant-data-init`、`eastmoney-quant-stock-screening`、`eastmoney-quant-report-generation`、`eastmoney-quant-multi-timeframe`、`eastmoney-quant-strategy-backtest`。
