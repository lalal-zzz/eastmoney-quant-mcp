---
name: eastmoney-quant-report-generation
description: "Generate deep institutional-grade technical analysis reports for Chinese A-share stocks. Integrates multi-timeframe trends (Monthly/Weekly/Daily/Hourly), support and resistance key levels (MA system, Fibonacci, structural pivots), 5 chart patterns, risk rating, and exact position/stop-loss management. Triggers: 股票分析, 诊断, 技术报告, 支撑位, 阻力位, 风险评估, 仓位, 止损, 研报, 深度分析."
---

# 个股全维深度技术研报生成指南 (Report Generation)

本 Skill 规范了单只股票深度分析研报的生成标准。报告必须整合**多周期趋势定位 (月/周/日/小时K)、形态结构、关键技术点位 (MA/斐波那契/结构位)、风险评估与动态仓位管理**，以机构级标准输出。

---

## 1. 数据装配流水线

在为指定股票生成完整研报时，必须按序完成以下工具调用与数据装配：

```python
# 1. 基础技术指标与报告底稿 (日K)
report_data = generate_stock_report(symbol)

# 2. 关键点位体系 (MA均线/斐波那契/前高前低结构位)
key_levels = get_key_levels("stocks", symbol)

# 3. 历史形态信号与当前形态
pattern_history = get_pattern_history("stocks", symbol)

# 4. 所属板块背景与资金流
sectors = get_stock_belong_sectors(symbol)

# 5. 周K与小时K结构确认 (网络实时)
weekly_kline = get_stock_kline_period(symbol, period="102", limit=52)
hourly_kline = get_stock_kline_period(symbol, period="60", limit=60)
```

---

## 2. 研报核心维度解读原则

### ① 趋势与均线系统
- **多头排列**：MA5 > MA10 > MA20 > MA60，且价格依托 MA20 稳健上行；
- **生命线划分**：
  - 短线生命线：MA10 / MA20；
  - 中期强弱分水岭：MA60 (季线) / MA120 (半年线)；
  - 牛熊分水岭：MA250 (年线)。

### ② 关键技术点位 (Support & Resistance)
- **复合共振点位**：当某一价格区域同时重合了 **“均线 (如 MA60) + 斐波那契关键位 (0.382/0.5/0.618) + 前期波段高点/低点”** 时，该点位强度为最高级，极易引发大级别反弹或受阻回落。

### ③ 盈亏比与动态仓位算法
- **盈亏比公式**：`风险收益比 = (预期第一阻力位 - 当前现价) / (当前现价 - 核心支撑止损位)`；
- **准入标准**：
  - 盈亏比 $\ge 3.0$：优秀交易机会，建议配置合理上限仓位；
  - 盈亏比 $2.0 \sim 3.0$：可接受机会，建议适中仓位；
  - 盈亏比 $< 1.5$：性价比过低，即使看好也应等待回踩后再考虑进场。

---

## 3. 机构级技术研报标准模板

```markdown
# 📊 {name} ({symbol}) 全维度技术量化研报
**报告日期**: {report_date} | **收盘价**: {latest_price}元 ({change_pct}%)
> ⚠️ 风险声明：本报告基于历史量化数据、形态识别与数学模型自动生成，仅供投研学习参考，不构成直接买卖指令。

---

## 一、基本面与行情概览
| 指标 | 对应数值 | 行业横向评价 | 指标 | 对应数值 | 市场热度 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **市盈率(动态)** | {pe_dynamic} | {pe_evaluation} | **换手率** | {turnover_rate}% | {turnover_eval} |
| **市净率(PB)** | {pb} | {pb_evaluation} | **量比** | {volume_ratio} | {vol_eval} |
| **总市值** | {total_market_cap} 亿元 | 大/中/小盘 | **人气排名** | 第 {popularity_rank} 名 | 近30日趋势: {rank_trend} |
| **所属核心板块** | {sector_names} | 板块主力资金近况: {sector_inflow} |

---

## 二、多周期趋势综合评定
- 🌕 **月K宏观位置**: {monthly_summary} (处于历史高位 / 中枢震荡 / 底部蓄势)
- 🌓 **周K中期波段**: **{weekly_direction}** (周MA20={w_ma20}，中期排列状态: {w_arrangement})
- 🌔 **日K主运行态**: **{daily_direction}** (日线均线排列: {daily_arrangement})
  - 近期涨跌幅表现: 5日 {chg_5d} | 20日 {chg_20d} | 60日 {chg_60d} | 年初至今 {chg_ytd}
- 🌒 **60分钟微观节奏**: {hourly_summary} (小时线处于回踩确认 / 金叉加速 / 顶部钝化)

---

## 三、形态识别与关键点位矩阵
- **当前技术形态**: `{pattern_name}` (标准度评分: {pattern_score} / 1.0, 关键位共振数: {resonance_count})
- **关键位分层矩阵 (按价格与强度排序)**:

| 类型 | 价格 | 点位来源 (均线/斐波那契/结构) | 强度等级 | 距离现价幅度 |
| :--- | :--- | :--- | :---: | :---: |
| **强阻力位** | {r2_price} | {r2_source} | ★★★ | +{r2_pct}% |
| **近期阻力** | {r1_price} | {r1_source} | ★★☆ | +{r1_pct}% |
| **当前现价** | **{latest_price}** | **当前市场价格** | — | — |
| **第一支撑** | {s1_price} | {s1_source} | ★★☆ | -{s1_pct}% |
| **核心防线** | {s2_price} | {s2_source} | ★★★ | -{s2_pct}% |

---

## 四、核心技术指标体检
- **动量与超买超卖**: RSI(14)={rsi14} ({rsi_status}) | KDJ(9,3,3): K={k}, D={d}, J={j} ({kdj_status})
- **趋势与能量**: MACD DIF={dif}, DEA={dea}, MACD柱={macd_bar} ({macd_signal})
- **通道与波动率**: BOLL 通道处于 {boll_status}，现价位于带内 {boll_pos}% 位置；ATR(14)={atr} (对应日内平均波幅 {atr_pct}%)

---

## 五、综合风险评估
- **综合风险等级**: **{risk_level}** (低 / 中 / 高)
- **核心风险预警清单**:
  - {risk_item_1}
  - {risk_item_2}
  - {risk_item_3}

---

## 六、交易策略与仓位管理建议
- **策略导向**: **{strategy_suggestion}** (观望等待 / 分批低吸 / 顺势突破跟进 / 逢高减仓)
- **参考买入区间**: `{entry_range}`
- **目标止盈点位**:
  - 第一目标位 (轻仓减仓): `{take_profit_1}` (预期收益: +{tp1_pct}%)
  - 第二目标位 (主阻力区): `{take_profit_2}` (预期收益: +{tp2_pct}%)
- **纪律止损点位**: `{stop_loss}` (距离现价: {sl_pct}%)
- **综合风险收益比**: **{risk_reward_ratio} : 1**
- **建议最大持仓比例**: **{position_pct}%** (单票上限严控在 30% 以内)
```
