"""patterns/constants.py — 形态引擎常量 (形态名 / 过滤阈值 / 冷却 / 斐波那契)"""

from ...core.constants import MIN_PATTERN_BARS

BACKTEST_START = "2010-01-01"          # 回测/历史数据起点 (用户要求 2010 之后)
MIN_BARS = MIN_PATTERN_BARS             # backward-compatible public constant

PATTERN_NAMES = {
    "trend_pullback": "趋势回调企稳",
    "ma_rebound": "下跌均线反弹",
    "w_bottom": "W底右底",
    "m_neckline": "M形颈线支撑",
    "box_breakout": "平台放量突破",
}

# 每形态精细筛选 (per-pattern)。由 pattern_backtest.py v3 趋势上下文版全量回测校准
# (2011-2026, ~25万信号, 全期贪心2因子): 基线10日胜率 46.9~49.7% → 筛后 52.7~55.3%。
PATTERN_FILTERS = {
    "trend_pullback": {"change_rate": (None, 1.8), "potential_gain": (0.0, 0.028)},
    "w_bottom": {"change_rate": (None, 1.75), "turnover_ma20": (0.02, 0.6)},
    "m_neckline": {"bias60": (None, 0.04), "up_days_ratio_20": (0.6, None)},
    "box_breakout": {"vol_ratio": (1.0, 1.75), "change_rate": (None, 2.1)},
    "ma_rebound": {"up_days_ratio_20": (0.6, None), "bias60": (0.045, None)},
}

# 优中选优档: 后缀 _in 为类别条件 (字段值必须属于列表)
# 由 pattern_optimize.py 双稳健搜索产生 (train<2022 搜索, test 2022+ 时间外验证)。
PATTERN_STRICT_FILTERS = {
    "trend_pullback": {"change_rate": (None, 1.81), "fib_in": ["fib_618"]},
    "w_bottom": {"bias60": (None, -0.07), "vol_ratio": (0.4, 1.87)},
    "m_neckline": {"bias60": (None, 0.024), "change_rate": (None, 1.24)},
    "box_breakout": {"bias60": (None, 0.074), "turnover": (0.05, 1.16)},
    "ma_rebound": {"variant_in": ["MA250_hold"], "potential_gain": (0.01, 0.151)},
}

# 同形态信号冷却交易日数 (避免同一形态密集重复触发)
PATTERN_COOLDOWN = {
    "trend_pullback": 10, "ma_rebound": 20, "w_bottom": 15,
    "m_neckline": 15, "box_breakout": 15,
}

FIB_RATIOS = (0.382, 0.5, 0.618, 0.786)
