---
name: eastmoney-quant
description: Local-first A-share data and research workflows. Use for Chinese stock data initialization, daily updates, screening, sector research, and evidence-based reports.
---

# 东方财富数据研究中心

先检查 `get_data_status`。数据未初始化时引导用户执行初始化；数据过期时说明日期并建议每日更新。不要假定实时数据已经可用。

对研究任务使用“宽筛 → 个股/板块验证 → 报告”的顺序：先筛选候选，再获取需要的日线、排名和板块背景，最后生成可追溯结论。报告必须写明数据日期、数据缺失和风险，不能输出确定性的买卖或仓位指令。

## 工具速查（10 个）

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

详细流程见子 Skill：`eastmoney-quant-data-init`、`eastmoney-quant-stock-screening`、`eastmoney-quant-report-generation`。
