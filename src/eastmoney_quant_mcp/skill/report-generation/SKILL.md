---
name: eastmoney-quant-report-generation
description: Generate comprehensive A-share stock technical analysis reports with support/resistance levels, risk assessment, and position management advice. Use when the user wants a detailed analysis of a specific stock, asks about support/resistance (支撑位/阻力位), risk level (风险), position sizing (仓位), stop-loss (止损), or wants a professional report for any 6-digit stock code. Also use after stock screening to analyze top candidates.
---

# Stock analysis report

## The tool

```
generate_stock_report(symbol)
```

Returns a structured JSON with 6 sections. Format into a clean Markdown report for the user.

## Report structure

Always present the report using this template:

```markdown
# {name}({symbol}) 技术分析报告
**报告日期**: {report_date}
> ⚠️ 基于技术指标自动生成，仅供学习参考，不构成投资建议。

## 基础信息
| 指标 | 数值 |
|------|------|
| 最新价 | {latest_price} |
| 涨跌幅 | {change_pct} |
| 量比 | {volume_ratio} |
| 换手率 | {turnover_rate}% |
| PE(动态) | {pe_dynamic} |
| PB | {pb} |
| 总市值(亿) | {total_market_cap} |
| 60日涨跌幅 | {sixty_day_change} |

## 趋势分析
- **方向**: {direction}
- **均线状态**: {arrangement}
- **近期涨跌幅**: {list recent_changes}

## 技术指标
- **RSI(14)**: {value} — {status}
- **MACD**: {signal} (DIF={DIF} DEA={DEA})
- **KDJ**: K={K} D={D} J={J} — {status}
- **BOLL**: {position}
- **ATR(14)**: {value14} ({pct}%)

## 支撑/阻力位
| 类型 | 价格 | 来源 | 强度 |
|------|------|------|------|
{list each resistance and support}

## 风险评估
**风险等级**: {level} (高/中/低)
{list each risk item as bullet}

## 仓位管理
- **建议**: {suggestion}
- **仓位比例**: {position_pct}
- **止损位**: {stop_loss} (距现价 {stop_loss_pct})
- **止盈位**: {take_profit}
- **风险收益比**: {risk_reward_ratio}
- **最近支撑**: {nearest_support} / **最近阻力**: {nearest_resistance}

> ⚠️ 技术分析基于历史数据，无法预测突发利空。仓位建议仅供参考。
```

## Interpreting the report

### Risk-reward ratio
| Value | Meaning | Action |
|-------|---------|--------|
| > 3 | Reward 3x risk | Worth attention |
| 2-3 | Acceptable | Moderate position |
| 1-2 | Poor value | Wait for better entry |
| < 1 or -1 | No clear target | Avoid |

### Position sizing principle
- Single stock max 30% of capital
- Position size = (total capital × risk%) / (entry - stop_loss)
- Low risk → up to 30% position
- Medium risk → 10-20%
- High risk → <10% or pass

### Support/resistance usage
- Break above resistance + hold → bullish
- Break below support + fail to recover → bearish
- MA60/MA120 is the medium-term trend dividing line

## Batch comparison workflow

When comparing multiple candidates (e.g., from screening results):

1. `screen_stocks(...)` → top 5-8 candidates
2. For each: `generate_stock_report(symbol)`
3. Sort by `risk_reward_ratio` descending
4. Show comparison table: name | price | change% | PE | RR | risk | position
5. Recommend top 2-3

## Risk disclaimer

Every report must include this warning:

> ⚠️ 技术分析基于历史数据，无法预测突发利空（政策/财报/黑天鹅）。本报告不构成投资建议，入市需谨慎，请结合基本面综合判断。
