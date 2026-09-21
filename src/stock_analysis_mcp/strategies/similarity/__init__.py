"""
strategies/similarity 包 — 跨周期/跨标的价量形态相似引擎
(原 similarity.py 拆分, 本包为门面 re-export)

模块布局:
    features.py  纯数学层: K线清洗 / 归一化特征 / DTW / 粗筛评分
    outcomes.py  统计层: 前向收益统计 / 汇总 / 条件概率
    pipeline.py  IO/编排层: 候选池加载 + 粗筛 + 全量评分 + 对外入口

The engine compares normalized paths rather than absolute prices or bar duration.
It is intentionally descriptive: a high score means the shapes are alike, not
that the historical outcome must repeat.
"""

from .features import (
    DEFAULT_WEIGHTS,
    PERIOD_LABELS,
    _coarse_price_scores,
    _component_scores,
    _dtw_distance,
    _features,
    _frame,
    _relative_drawdown,
    _resample,
    _standardize,
)
from .outcomes import (
    _forward_stats,
    _outcome_probabilities,
    _shape_metrics,
    _summarize_outcomes,
)
from .pipeline import (
    _candidate_universe,
    _compare_local_batches,
    _extract_coarse_records,
    _load_local_candidate_sets,
    _period_rows,
    compare_cross_timeframe_patterns,
    find_cross_timeframe_similar_patterns,
)

__all__ = [
    "compare_cross_timeframe_patterns",
    "find_cross_timeframe_similar_patterns",
    "PERIOD_LABELS", "DEFAULT_WEIGHTS",
    "_period_rows", "_candidate_universe", "_compare_local_batches",
]
