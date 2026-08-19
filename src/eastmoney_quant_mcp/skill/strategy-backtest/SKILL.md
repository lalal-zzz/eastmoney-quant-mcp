---
name: eastmoney-quant-strategy-backtest
description: "Pattern strategy backtesting and parameter tuning guide. Validate technical chart patterns, optimize filters via beam-search, evaluate win-rates across market regimes (bull/bear/range), and adapt parameters to investor risk profiles. Triggers: 回测, 策略调优, 胜率, 参数优化, 历史验证, backtest, optimize."
---

# 形态策略历史回测与参数调优指南 (Strategy Backtest & Tuning)

本 Skill 指导 Agent 如何对五大上涨形态（趋势回踩、均线反弹、W底、M头颈线、箱体突破）进行全历史无未来函数回测，并基于市场环境（牛/熊/震荡）与用户风险偏好进行科学调优。

---

## 1. 回测核心原则与防过拟合机制

1. **严格杜绝未来函数**：
   - 摆动点极值（Pivot）严格遵循 `confirm = idx + right` 滞后右确认原则，在确认发生前不可用于生成信号；
   - 信号产生后，一律以 **次日开盘价 (`open[i+1]`)** 作为模拟买入基准，绝不使用信号日收盘价。
2. **多周期时间外切分 (Train/Test Split)**：
   - 训练集：2011 ~ 2021 年全市场信号用于参数空间搜索与特征分层；
   - 验证集：2022 年至今的数据作为时间外样本（Out-of-Sample）独立检验，当训练集与测试集胜率差 $> 8\% \sim 10\%$ 时判定为过拟合并予以剔除。

---

## 2. CLI 常用回测与调优命令矩阵

| 业务场景 | 命令行调用示例 | 预期耗时 | 产出物与用途 |
| :--- | :--- | :---: | :--- |
| **快速抽样验证** | `python -m eastmoney_quant_mcp.cli pattern-backtest --sample 300 --workers 8` | ~1-2 min | 随机抽样 300 标的快速摸底五大形态基准胜率 |
| **股票全量回测** | `python -m eastmoney_quant_mcp.cli pattern-backtest --universe stocks --workers 8 --csv signals.csv` | ~15-30 min | 全市场 5500+ 只股票 15 年全量信号回测，导出信号特征库 |
| **板块指数回测** | `python -m eastmoney_quant_mcp.cli pattern-backtest --universe sectors --workers 8` | ~3-5 min | 480+ 板块指数历史表现回测（历史 $\ge 260$ 根自动纳入） |
| **多因子束搜索优化** | `python -m eastmoney_quant_mcp.cli pattern-optimize --cache signals.csv --target 0.80 --md trials.md` | ~5 min | Beam-Search 搜索最优过滤阈值，输出 Markdown 调优轨迹 |

---

## 3. 六大回测诊断报告深度解读

回测脚本执行后会输出 6 份结构化报告，Agent 应重点提取以下核心维度向用户汇报：

1. **形态 $\times$ 变体胜率总表**：
   - 评估未来 5 日、10 日、20 日胜率与盈亏比；10 日胜率 $> 52\% \sim 55\%$ 且期望收益 $> 2.5\%$ 的变体为高置信度形态。
2. **关键点位与共振分层**：
   - 观察命中单一均线 vs 多重共振（均线 + 斐波那契 + 结构位，`resonance >= 2`）的胜率差异，通常共振数越高，假突破概率越低。
3. **波段结构阶段分层 (`wave_phase`)**：
   - 比较“首次回调 (first_pullback)”、“突破新高 (breakout_new_high)”与“末期回调 (later_pullback)”的表现。
4. **多因子分层 (Factor Quantiles)**：
   - 识别成交量倍率 (`vol_ratio`)、RSI 水平、偏离度 (`bias60`) 等因子的有效过滤阈值。
5. **推荐精细筛选阈值 (Filter Recommendations)**：
   - 给出可直接回写至 `PATTERN_FILTERS` 的边界阈值。
6. **分年度胜率走势 (Annual Robustness)**：
   - 验证策略在 2015 杠杆牛、2018 阴跌熊、2020 核心资产牛、2024 震荡市中的适应能力。

---

## 4. 市场环境自适应策略矩阵

在为用户提供调优建议前，首先调用 `get_kline_local_or_net(symbol="000300", days=120)` 获取沪深300指数走势判定大势：

| 市场环境 | 判定条件 (沪深300) | 优先主打形态 | 严格风控/收紧形态 | 建议配置参数 |
| :--- | :--- | :--- | :--- | :--- |
| **牛市 / 主升** | 价格 > MA60 且 20日涨幅 $> +5\%$ | `trend_pullback` (趋势回踩)<br>`box_breakout` (平台突破) | 忽略 `ma_rebound` (强势行情中超跌股少) | `min_score=0.6`<br>重点抓突破共振 |
| **熊市 / 探底** | 价格 < MA60 且 20日跌幅 $< -5\%$ | `w_bottom` (双底反转)<br>`ma_rebound` (年线/半年线抄底) | 回避 `box_breakout` (假突破多)<br>收紧 `trend_pullback` | `strict=True`<br>`min_score=0.75` |
| **震荡 / 轮动** | 围绕 MA60 纠缠，20日波动在 $\pm 5\%$ 内 | `m_neckline` (颈线支撑)<br>`box_breakout` (箱体内高抛低吸) | 避免盲目追高突破 | `strict=True`<br>仓位严控在 15%~20% |

---

## 5. 调优决策树与报告模板

```markdown
# 📈 量化形态策略调优与历史回测报告
**回测标的宇宙**: {universe} | **时间跨度**: {start_date} ~ {end_date} | **有效样本**: {sample_count} 只

## 一、回测核心结论摘要
- **总触发信号数**: {total_signals} 次 | **10日平均胜率**: {win_rate_10d}% | **10日平均收益**: {avg_ret_10d}%
- **表现最优形态**: `{best_pattern}` (10日胜率: {best_wr}%, 盈亏比: {best_rr}:1)
- **过拟合检验**: 训练集胜率 {train_wr}% vs 验证集胜率 {test_wr}% (差异度: {diff_pct}%, 稳健)

## 二、当前市场环境适配策略
- **大盘指数判定**: 沪深300现价 {index_price} vs MA60 {ma60} $\rightarrow$ **{market_regime}**
- **形态权重推荐**: {pattern_weight_advice}

## 三、用户风险偏好配置方案
- 🛡️ **稳健保守型**: 建议使用 `strict=True, min_score=0.75`，重点关注具备 $\ge 2$ 重共振的信号；
- ⚖️ **均衡波段型**: 建议使用默认标准 `min_score=0.6`，在 60 分钟级别出现金叉企稳时介入；
- 🚀 **积极进攻型**: 可放宽至 `min_score=0.5, no_filter=True`，捕捉早期异动，单笔严格执行 4%~5% 止损。
```
