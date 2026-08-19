---
name: eastmoney-quant-stock-screening
description: "Universal multi-condition and chart-pattern stock screening engine. Combine 18 fundamental/technical criteria (PE, PB, market cap, change%, volume ratio, turnover, amplitude) with 5 classical chart patterns (trend pullback, MA rebound, W-bottom, M-neckline, box breakout), sector filtering, and multi-period verification. Triggers: 选股, 筛选, 帮我找, 有什么股票, 形态选股, 板块选股, 放量突破, 抄底, 牛股."
---

# 全维量化选股与形态筛选指南 (Stock Screening)

本 Skill 提供基于**基本面估值、行情动量、资金流向与五大经典上涨形态**的全方位智能选股策略。支持从宽基全市场初筛到精细多周期过滤的全流程。

---

## 1. 核心选股工具组合

选股流程主要由以下工具协同完成：

1. `screen_stocks(conditions, top_n=50, sort_by="change_pct", sector_code=None, name_keyword=None)`: 全市场18维财务与量价多条件极速初筛；
2. `scan_patterns(patterns=None, strict=False, min_score=0.6, workers=8, symbols=None)`: 针对全市场或指定股票识别 5 类标准技术形态；
3. `scan_sector_patterns(sector_type="concept")`: 识别板块指数走势，实现“自上而下 (Top-Down)”的板块共振选股；
4. `get_stock_belong_sectors(stock_code)`: 反查个股概念与行业归属，验证板块资金支持；
5. `get_stock_kline_period(symbol, period="102")`: 多周期二次校验（周K大势与分时节奏）。

---

## 2. 五大形态专属选股指令与应用场景

用户若要求按形态选股，直接调用 `scan_patterns`（可选参数 `strict=True` 开启优中选优档）：

| 形态标识 (`patterns`) | 中文形态名称 | 核心特征与逻辑 | 适用市场风格 | 推荐调用示例 |
| :--- | :--- | :--- | :--- | :--- |
| `trend_pullback` | **趋势回调企稳** | 上升趋势中缩量回踩 MA20/MA60 或斐波那契 0.382/0.5/0.618 企稳 | 牛市/主升浪阶段 | `scan_patterns(patterns=["trend_pullback"], strict=True)` |
| `box_breakout` | **平台放量突破** | 长时间窄幅箱体震荡后放量大阳线突破上轨 | 震荡市突破/新热点启动 | `scan_patterns(patterns=["box_breakout"], strict=True)` |
| `w_bottom` | **W底右底反弹** | 经历两波探底，右底不破左底或假跌破后迅速收回，放量突破颈线 | 熊市末期/超跌反弹 | `scan_patterns(patterns=["w_bottom"], min_score=0.65)` |
| `m_neckline` | **M形颈线支撑** | 股价突破前高后回踩原颈线位置，由阻力转为强支撑，博二次主升 | 强势股回踩波段 | `scan_patterns(patterns=["m_neckline"], strict=True)` |
| `ma_rebound` | **下跌均线反弹** | 深度下跌后在半年线(MA120)或年线(MA250)处出现企稳反弹 | 左侧抄底/防御配置 | `scan_patterns(patterns=["ma_rebound"], min_score=0.7)` |

---

## 3. 经典量化策略配方库 (Condition Recipes)

通过 `screen_stocks` 的 `conditions` 参数自由组合 18 维条件：

### ① 价值白马低估突破策略
- **逻辑**：低估值、高流动性大市值蓝筹，技术面刚刚放量启动。
- **参数**：
  ```python
  screen_stocks(
      conditions={"max_pe": 20, "max_pb": 2.0, "min_market_cap": 300, "min_change_pct": 2.5, "min_volume_ratio": 1.5},
      sort_by="pe_dynamic"
  )
  ```

### ② 高弹性游资爆发策略
- **逻辑**：中小盘、高换手、高量比、日内极强上攻动能。
- **参数**：
  ```python
  screen_stocks(
      conditions={"min_change_pct": 5.0, "min_turnover_rate": 8.0, "min_volume_ratio": 2.0, "max_market_cap": 150},
      sort_by="turnover_rate"
  )
  ```

### ③ 中期强势慢牛回踩策略
- **逻辑**：60日与年初至今大幅走强，近期出现良性温和回踩。
- **参数**：
  ```python
  screen_stocks(
      conditions={"min_sixty_day_change": 20.0, "min_ytd_change": 15.0, "max_change_pct": -0.5, "min_change_pct": -3.0},
      sort_by="popularity_rank"
  )
  ```

### ④ 热门概念板块内淘金策略 (自上而下)
- **步骤**：
  1. `get_sector_list("concept")` 按 `main_net_inflow` 排序找出今日主力狂买的概念板块（如“低空经济”、“半导体”）；
  2. 获取板块代码（如 `BK1090`）；
  3. `screen_stocks({"min_volume_ratio": 1.2}, sector_code="BK1090", sort_by="change_pct")` 挑选板块内部领涨与蓄势标的。

---

## 4. 选股后的标准化多层过滤链路

选股不等于直接买入。从海选到最终标的必须经过四步过滤：

```text
[第一步: 全市场初筛 (screen_stocks / scan_patterns)]
              ↓ 产出 10 ~ 20 只候选
[第二步: 题材与资金校验 (get_stock_belong_sectors / get_rank_trend_data)]
              ↓ 剔除冷门边缘股，保留 5 ~ 8 只
[第三步: 多周期大势检验 (周K get_stock_kline_period + 小时K)]
              ↓ 排除周线破位或分时顶部钝化股，保留 2 ~ 3 只
[第四步: 深度研报生成与仓位锚定 (generate_stock_report + get_key_levels)]
              ↓ 输出最终具备高盈亏比的操作计划
```

---

## 5. 选股输出与决策呈现模板

对于筛选出的候选标的集合，统一采用对比矩阵呈现：

```markdown
# 🎯 量化选股决策矩阵 ({strategy_name})
**筛选时间**: {date} | **符合条件标的数**: {total_matches} 只

## 推荐优选标的池 (Top Candidates)

| 股票代码 | 名称 | 现价 | 今日涨跌 | PE/PB | 识别形态 (评分) | 关键支撑位 | 盈亏比 | 综合评级 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| 600xxx | 示例A | 15.20 | +3.4% | 18.5/1.8 | 平台突破 (0.85) | 14.60 (MA20) | 3.5:1 | ⭐⭐⭐⭐ |
| 002xxx | 示例B | 28.50 | +1.8% | 24.2/2.5 | 趋势回踩 (0.78) | 27.20 (斐波0.5) | 2.8:1 | ⭐⭐⭐ |

---

## 深度执行指引
- **首选标的**: `{top_stock}`
  - **核心逻辑**: {reasons}
  - **建议建仓**: 在 {entry_zone} 附近分批吸纳；
  - **止损防线**: 跌破 {stop_loss} 坚决离场；
  - **后续验证**: 建议查看该标的的 60 分钟 K 线金叉或调用 `generate_stock_report` 查看全维度研报。
```
