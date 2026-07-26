# 个股分析报告技能 (Stock Analysis Report)

## 前置条件

本技能依赖:
1. **data-init** 技能完成数据库初始化 + K线下载
2. 可选: **stock-screening** 技能选出候选股后, 调用本技能逐只深度分析

> 若 `generate_stock_report` 返回 K 线不足, 会自动触发下载(数据来自 `stock_kline` + `stock_indicators` 表)。

## 数据依赖

`generate_stock_report` 的底层数据流:

```
stock_basic → 股票名称
stock_spot  → PE/PB/市值/量比/60日涨幅 等基本面
stock_kline → open/high/low/close/volume → 计算支撑阻力位
stock_indicators → MA/RSI/MACD/KDJ/BOLL/ATR → 技术状态判定
stock_rank  → (未直接使用, 可补充调 get_rank_trend_data)
```

**核心指标表 `stock_indicators` 字段**:

| 字段 | 报告中使用位置 |
|------|---------------|
| MA5/MA10/MA20/MA60/MA120/MA200 | 趋势分析(均线排列) + 支撑阻力位 |
| RSI14 | 技术指标状态 + 风险评估(超买超卖) |
| DIF/DEA/MACD | 金叉死叉信号判定 |
| BOLL_UPPER/MIDDLE/LOWER | BOLL位置 + 支撑阻力 |
| KDJ_K/D/J | KDJ超买超卖判定 |
| ATR14 | 风险评估(波动率) + 仓位管理(止损计算) |

---

## 核心工具

`generate_stock_report(symbol)` 返回 6 模块 JSON:

```
{
  "basic_info":          价格/涨跌幅/PE/PB/市值/量比/换手
  "trend_analysis":      均线排列/5-60日涨跌幅/短期方向
  "technical_indicators": RSI/MACD/KDJ/BOLL/ATR 状态描述
  "support_resistance":  支撑位(均线+BOLL下轨) / 阻力位(均线+BOLL上轨) / ATR
  "risk_assessment":     综合风险等级 + 具体风险项
  "position_advice":     止损位/止盈位/风险收益比/仓位比例
}
```

---

## 报告格式化规范

输出必须按以下 Markdown 模板格式化。将 JSON 数值填入占位符:

```markdown
# {{name}}({{symbol}}) 技术分析报告
**报告日期**: {{date}}
> ⚠️ 本报告基于技术指标自动生成, 仅供学习参考, 不构成投资建议。投资有风险, 入市需谨慎。

## 📊 基础信息
| 指标 | 数值 |
|------|------|
| 最新价 | {{latest_price}} |
| 涨跌幅 | {{change_pct}} |
| 量比 | {{volume_ratio}} |
| 换手率 | {{turnover_rate}}% |
| PE(动态) | {{pe_dynamic}} |
| PB | {{pb}} |
| 总市值(亿) | {{total_market_cap}} |
| 60日涨跌幅 | {{sixty_day_change}} |
| 年初至今涨幅 | {{ytd_change}} |

## 📈 趋势分析
- **方向**: {{direction}}
- **均线状态**: {{arrangement}}
- **近期涨跌幅**: {{recent_changes 逐项列出}}

## 🔧 技术指标
- **RSI(14)**: {{RSI.value}} — {{RSI.status}}
- **MACD**: {{MACD.signal}} (DIF={{DIF}} DEA={{DEA}})
- **KDJ**: K={{K}} D={{D}} J={{J}} — {{KDJ.status}}
- **BOLL**: {{BOLL.position}}
- **ATR(14)**: {{ATR.value14}} ({{ATR.pct}}% 相对价格)

## 🛡️ 支撑/阻力位
| 类型 | 价格 | 来源 | 强度 |
|------|------|------|------|
| 阻力 | {{resistance.level}} | {{resistance.type}} | {{resistance.strength}} |
| ... | ... | ... | ... |
| 支撑 | {{support.level}} | {{support.type}} | {{support.strength}} |
| ATR(14) | {{atr}} | 真实波幅 | — |

## ⚠️ 风险评估
**综合风险等级**: {{level}}(高/中/低)
{{items 逐条列出}}
- {{item}}

## 💰 仓位管理
- **建议**: {{suggestion}}
- **仓位比例**: {{position_pct}} (若无建议则显示"观望")
- **止损位**: {{stop_loss}} (距现价 {{stop_loss_pct}})
- **止盈位**: {{take_profit}}
- **风险收益比**: {{risk_reward_ratio}} ({{解读: >3优秀, 2-3可接受, <1.5不建议}})
- **最近支撑**: {{nearest_support}}
- **最近阻力**: {{nearest_resistance}}

---

> ⚠️ 技术分析基于历史数据, 无法预测突发利空。仓位建议仅供参考。
```

---

## 解读标准

### 风险收益比 (RR Ratio)
| 值 | 含义 | 建议 |
|----|------|------|
| > 3 | 收益是风险的3倍+ | 可积极关注 |
| 2 - 3 | 可接受 | 适量参与 |
| 1 - 2 | 性价比不高 | 等待更好买点 |
| < 1 或 -1 | 无明确止盈位 | 观望 |

### 仓位管理原则
- **轻仓**: <10% 总资金
- **中等**: 10-20%
- **积极**: 20-30%
- **重仓**: 30-50% (仅低风险+强趋势+高RR时)
- 单只股票不超过总资金30%

### 风险等级解读
- **低**: 指标正常, 无超买信号 → 可正常操作
- **中**: 部分指标偏高/波动加大 → 控制仓位
- **高**: 严重超买/高波动/破位 → 减仓或观望

---

## 批量对比流程

当用户要对比多只股票(如从选股结果中):

1. `screen_stocks(...)` → 选出候选池
2. 对 Top 5-8 逐一 `generate_stock_report`
3. 按 `position_advice.risk_reward_ratio` 降序排列
4. 列出对比表格: 名称/涨跌幅/PE/RR/风险等级/仓位建议
5. 推荐最值得关注的 2-3 只

---

## 关联技能

- **上一环节**: `eastmoney-quant-stock-screening` — 选股技能输出候选列表
- **数据基础**: `eastmoney-quant-data-init` — 确保数据库已初始化且K线已下载
