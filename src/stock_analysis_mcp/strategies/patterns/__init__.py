"""
strategies/patterns 包 — 形态识别 (原 patterns.py 拆分, 本包为门面 re-export)

模块布局:
    constants.py   常量 (形态名/过滤阈值/冷却期/斐波那契比率)
    universe.py    标的宇宙定义与本地库数据加载 (股票/板块双宇宙)
    pivots.py      摆动点检测 + zigzag 事件流
    factors.py     因子列补算 (add_factor_columns)
    context.py     单标的检测上下文 (_Ctx) + 趋势/波段/斐波那契关键位引擎
    signal.py      信号构造 / JSON 清洗 / 形态过滤
    detectors.py   形态检测器 (抽象基类 + 5 个实现 + 注册表)
    engine.py      detect_patterns 主循环 (注册表分发) + prepare_df
    api.py         对外扫描接口 (scan_universe / get_pattern_history / get_key_levels)

兼容性: 对外符号与原 patterns.py 完全一致 (含测试使用的私有名)。
"""

from .api import get_key_levels, get_pattern_history, scan_universe
from .constants import (
    BACKTEST_START,
    FIB_RATIOS,
    MIN_BARS,
    PATTERN_COOLDOWN,
    PATTERN_FILTERS,
    PATTERN_NAMES,
    PATTERN_STRICT_FILTERS,
)
from .context import (
    MA_WINDOW_WHITELIST,
    _Ctx,
    _valid,
    fib_levels_from_swings,
    score_range,
    trend_context,
    wave_phase,
)
from .detectors import (
    ALL_DETECTORS,
    DETECTORS,
    BoxBreakoutDetector,
    MaReboundDetector,
    MNecklineDetector,
    PatternDetector,
    TrendPullbackDetector,
    WBottomDetector,
)
from .engine import detect_patterns, prepare_df
from .factors import add_factor_columns
from .pivots import Pivot, build_pivot_events, update_zigzag
from .signal import _base_signal, _sig_clean, passes_filter
from .universe import (
    _KLINE_COLS,
    _IND_COLS,
    _backfill_missing_columns,
    _connect,
    _current_universe_defs,
    _universe_defs,
    get_latest_trade_date,
    get_universe_list,
    load_pattern_df,
    resolve_universe_symbol,
)

__all__ = [
    # 对外 API
    "scan_universe", "get_pattern_history", "get_key_levels",
    "detect_patterns", "prepare_df",
    "load_pattern_df", "get_universe_list", "get_latest_trade_date",
    "resolve_universe_symbol",
    # 常量
    "BACKTEST_START", "MIN_BARS", "PATTERN_NAMES", "PATTERN_FILTERS",
    "PATTERN_STRICT_FILTERS", "PATTERN_COOLDOWN", "FIB_RATIOS",
    # 枢轴 / 因子 / 上下文
    "Pivot", "build_pivot_events", "update_zigzag", "add_factor_columns",
    "_Ctx", "MA_WINDOW_WHITELIST", "_valid", "score_range", "wave_phase",
    "trend_context", "fib_levels_from_swings",
    # 信号
    "_base_signal", "_sig_clean", "passes_filter",
    # 检测器 (抽象基类 + 注册表)
    "PatternDetector", "TrendPullbackDetector", "MaReboundDetector",
    "WBottomDetector", "MNecklineDetector", "BoxBreakoutDetector",
    "ALL_DETECTORS", "DETECTORS",
    # 宇宙内部设施 (测试 monkeypatch 兼容)
    "_universe_defs", "_current_universe_defs", "_connect",
    "_backfill_missing_columns", "_KLINE_COLS", "_IND_COLS",
]
