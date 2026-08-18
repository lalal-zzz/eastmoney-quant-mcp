---
name: eastmoney-quant-multi-timeframe
description: "Multi-timeframe stock analysis with cross-period resonance. Use for short/medium/long-term combined analysis, intraday structure confirmation, weekly trend positioning. Triggers: 多周期, 共振, 短周期, 周线, 60分钟, 跨周期, 综合研判."
---

# 多周期共振分析

核心原则: **周K定方向, 日K定节奏, 分时定买卖点**。对候选标的拉取三档周期数据, 综合判定共振等级后给出操作建议。

## 三档周期

| 档位 | 工具调用 | 覆盖 | 核心用途 |
|------|----------|------|----------|
| 周K | `get_stock_kline_period(symbol, period="102", limit=104)` | ~2年 | 中期趋势方向 |
| 日K | `generate_stock_report(symbol)` + `get_key_levels(symbol)` | ~1年 | 形态/关键位/风险/仓位 |
| 60分钟 | `get_stock_kline_period(symbol, period="60", limit=120)` | ~30天 | 分时结构确认 |

辅助: `scan_patterns`(形态宽筛), `get_pattern_history`(历史信号), `get_stock_belong_sectors`(板块归属)。

> `get_stock_kline_period` 纯网络实时, 不写本地库。分钟级时间键是 `datetime`, 日/周级是 `date`。短周期/周K无预计算指标, Agent 需从 K 线原始数据自行计算 MA/RSI/MACD。

## 工作流

**阶段 1 — 宽筛候选** (用户未指定标的时):
- `screen_stocks(conditions, top_n=50)` → 条件选股
- `scan_patterns(min_score=0.6)` → 形态信号宽筛
- 产出 5~15 只候选; 用户已指定则跳过

**阶段 2 — 日K标准分析** (每只候选):
1. `get_kline_local_or_net(symbol, days=250)` — 确保缓存
2. `generate_stock_report(symbol)` — 趋势/指标/支撑阻力/风险/仓位
3. `get_pattern_history(symbol)` — 历史形态频率
4. `get_key_levels(symbol)` — MA/斐波那契/结构位
5. 按 `risk_reward_ratio` 排序, 截取 top 5~8 进入阶段 3

**阶段 3 — 60分钟验证**: 拉 60 分钟 K 线, 计算 MA5/10/20、RSI14、MACD(DIF/DEA), 判定分时结构

**阶段 4 — 周K定位**: 拉周 K 线, 计算周 MA5/10/20/60、周 RSI14, 判定中期趋势

## 分时/周K快速判定表

| 指标 | 多头信号 | 空头信号 |
|------|----------|----------|
| 均线排列 | MA5 > MA10 > MA20 | MA5 < MA10 < MA20 |
| RSI14 | 50~70 (健康) | <30 (超卖) 或 >75 (超买) |
| MACD | DIF > DEA 且 DIF 上行 | DIF < DEA 或顶背离 |
| 关键确认 | 连续 3 根 close > MA20 | 跌破 MA20 不回收 |

周K额外关注: close vs 周 MA60 (半年线) — 跌破则中期偏弱, 不宜做多。

## 共振等级

| 等级 | 周K | 日K | 分时 | 操作建议 |
|------|-----|-----|------|----------|
| **强** | 多头 (close>周MA20, MA5>MA10) | 企稳/上扬, RSI 30~70 | 金叉或站稳MA20 | 正常仓位, 参考日K仓位建议 |
| **中** | 偏多 (close>周MA20, 均线未全多) | 有信号, 可参与 | 未确认 (缠绕/未金叉) | 小仓观察, 分时确认再加仓 |
| **弱** | 方向不明 (均线缠绕) | 有形态信号 | — | 极小仓试探, 严格止损 |
| **逆** | 空头 (close<周MA60) | 反弹信号 | — | **不参与**, 等大周期企稳 |

## 输出模板

```markdown
# {name}({symbol}) 多周期共振分析
**日期**: {date}
> 仅供学习参考, 不构成投资建议。

## 周K中期定位
趋势: {weekly_dir} | 周MA20={w_ma20} 周MA60={w_ma60} | 偏离: {dev}%
周RSI14: {w_rsi} | 中期判断: {weekly_conclusion}

## 日K标准分析
趋势: {daily_dir} ({daily_arrangement})
RSI14: {d_rsi} | MACD: {d_macd}
形态: {patterns} (score={score}, resonance={res})
支撑: {support} | 阻力: {resistance} | 风险: {risk_level}

## 60分钟结构
均线: MA5={i5} MA10={i10} MA20={i20} | RSI: {i_rsi}
结构: {intraday_structure} (金叉/死叉/企稳/破位)

## 共振判定
**等级**: {level} (强/中/弱/逆) — {explanation}

## 操作建议
进场: {entry} | 止损: {stop_loss}({sl_pct}%) | 止盈: {take_profit}({tp_pct}%)
仓位: {position_pct} | 加仓条件: {add_cond}
```

## 批量对比

对多只候选做完三周期分析后, 汇总对比表:

| 名称 | 周K方向 | 日K趋势 | 分时状态 | 共振 | 仓位建议 |
|------|---------|---------|----------|------|----------|
| ... | 多头 | 企稳 | 金叉 | 强 | 20% |

优先推荐强共振标的, 中共振作为观察池。
