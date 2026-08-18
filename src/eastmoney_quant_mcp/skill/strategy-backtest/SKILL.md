---
name: eastmoney-quant-strategy-backtest
description: "Pattern strategy backtesting and parameter tuning guide. Use for validating strategy effectiveness, tuning pattern parameters, comparing win rates across market regimes, or generating adjustment recommendations. Triggers: 回测, 策略调优, 胜率, 参数优化, 历史验证, backtest, optimize."
---

# 形态策略回测与参数调优

对五类上涨形态的历史信号回测验证, 结合市场环境和用户风险偏好, 给出策略调整建议报告。

## 前置条件

`get_data_status()` 确认 stock_kline + stock_indicators 有数据。不足则先 `init_full_data(quick=False)`。

## 命令速查

| 场景 | 命令 | 耗时 | 说明 |
|------|------|------|------|
| 快速验证 | `python -m eastmoney_quant_mcp.cli pattern-backtest --sample 300 --workers 8` | 2~5min | 随机抽样, 首次推荐 |
| 全量回测 | `pattern-backtest --workers 8 --csv signals.csv` | 30~60min | 全市场, 保存信号供 optimize |
| 板块回测 | `pattern-backtest --universe sectors --workers 8` | 5~15min | 板块指数, <260根自动跳过 |
| 参数优化 | `pattern-optimize --cache signals.csv --target 0.80` | 5~10min | beam search, 训练2011-21/验证2022+ |

加 `--md trials.md` 可输出 optimize 全部搜索尝试。回测输出 6 份报告到 stdout, Agent 解析文本提取关键数据。

## 报告解读要点

| 报告 | 核心问题 | 关键指标 |
|------|----------|----------|
| 形态×变体胜率 | 哪些变体值得信赖? | 10日胜率>50%可用, >55%优先; <45%考虑过滤 |
| 关键点位分层 | 命中哪些位置胜率更高? | resonance>=2 的信号置信度高; 仅小均线支撑偏弱 |
| 波段结构分层 | 哪个阶段入场最优? | first_pullback/breakout 胜率最高; deep_pullback 最低 |
| 因子分层 | score/RSI/换手 什么区间好? | 按四分位找"涨vs不涨"的共性阈值 |
| 推荐筛选阈值 | 参数该怎么调? | 回测推荐值可直接回写 PATTERN_FILTERS |
| 分年度胜率 | 哪年表现差? | 对应市场周期, 判断策略适应性 |

**信号质量判断**: max_gain_10 高但胜率低 → 少数大涨拉均值, 不稳定; 筛后胜率提升3~5%且样本缩减<50% → 有效筛选。

## 策略调整框架

### 市场环境判定

用 `get_kline_local_or_net(symbol="000300", days=120)` 获取沪深300日K:

| 市场 | 条件 | 优先形态 | 收紧形态 |
|------|------|----------|----------|
| 牛市 | 沪深300 > MA60 且 20日涨>5% | trend_pullback, box_breakout | ma_rebound(信号少) |
| 熊市 | 沪深300 < MA60 且 20日跌>5% | w_bottom, ma_rebound(抄底) | trend_pullback |
| 震荡 | MA60附近, 20日涨跌幅±5% | m_neckline, box_breakout | 整体收紧 min_score≥0.7 |

### 风险偏好适配

| 类型 | 参数 | 预期信号/月 | 止损纪律 |
|------|------|-------------|----------|
| 保守 | `strict=true, min_score=0.75` | 3~8 | 跌破信号日低点 |
| 均衡 | `min_score=0.6` (默认) | 10~30 | 跌破支撑-1×ATR |
| 激进 | `min_score=0.5, no_filter=true` | 50~100+ | 固定5%止损 |

### 参数调优决策树

```
胜率 < 50%?
  信号充足(>30/月) → 收紧 PATTERN_FILTERS, min_score 提至 0.7
  信号不足(<10/月) → 参数过紧, 放宽阈值
  仅特定变体低   → 排除该变体

信号量 < 10/月?
  min_score>0.7 → 降至 0.6
  数据覆盖不足  → init_full_data(quick=False)

train vs test 胜率差 > 10%? → 过拟合, 降 max_depth / 提 min_samples / 减因子

某变体连续 3 年负期望? → 排除或提高该形态 min_score 至 0.8
```

### 形态 × 市场矩阵

| 形态 | 牛市 | 熊市 | 震荡 |
|------|------|------|------|
| trend_pullback | 首选 ≥0.6 | 回避/strict | ≥0.7 |
| ma_rebound | 忽略 | 首选(抄底) | ≥0.7 |
| w_bottom | 少出现 | 首选(反转) | ≥0.65 |
| m_neckline | 注意追高 | 回避 | 首选 |
| box_breakout | 首选(突破) | strict(假突破多) | 首选 |

## 输出模板

```markdown
# 策略回测与调优报告
**日期**: {date} | 范围: {start}~{end} | 样本: {n}只

## 回测概要
信号: {total} | 有效: {valid} | 10日胜率: {wr}% | 10日均收益: {avg}%

## 形态胜率
| 形态 | 信号数 | 10日胜率 | 20日胜率 | 评价 |
|------|--------|----------|----------|------|
{table}

## 最优阈值 (vs 当前 PATTERN_FILTERS)
{diff}

## 市场环境: {regime}
依据: 沪深300 {price} vs MA60 {ma60}, 20日 {chg}%
推荐权重: {weights}

## 参数调整建议
{recommendations}

## 风险偏好方案
保守: strict, min_score=0.75, 优先{cons}
均衡: min_score=0.6, 优先{bal}
激进: no_filter, min_score=0.5, 优先{agg}

## 局限性
回测基于历史, 不保证未来; 未计入滑点/佣金; 板块参数待专属校准; 过拟合风险(train/test差>5%时谨慎)。
> 建议纸面交易验证 3~6 个月再实盘。
```
