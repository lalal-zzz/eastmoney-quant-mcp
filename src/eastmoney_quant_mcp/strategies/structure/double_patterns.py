from __future__ import annotations

import hashlib

import pandas as pd

from ..patterns.pivots import Pivot
from .models import DoublePattern


def _id(scale: str, pattern: str, a: Pivot, b: Pivot, c: Pivot) -> str:
    raw = f"{scale}:{pattern}:{a.idx}:{b.idx}:{c.idx}:{a.price:.8f}:{b.price:.8f}:{c.price:.8f}"
    return "double_" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def detect_double_patterns(df: pd.DataFrame, pivots: list[Pivot], *, scale: str,
                           as_of_idx: int | None = None,
                           max_endpoint_deviation: float = 0.10,
                           min_depth_pct: float = 0.05,
                           break_buffer_pct: float = 0.01,
                           invalidation_pct: float = 0.03,
                           max_monitor_bars: int | None = None,
                           max_results: int | None = None) -> list[DoublePattern]:
    """Detect asymmetric W/M skeletons without a maximum left/right duration.

    Fine internal oscillations are absorbed by selecting a coarser pivot scale;
    duration asymmetry is an output feature, never a rejection by itself.
    """
    if df.empty or len(pivots) < 3:
        return []
    end = len(df) - 1 if as_of_idx is None else min(as_of_idx, len(df) - 1)
    close = df["close"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()
    high = df["high"].astype(float).to_numpy()
    result = []
    for left, middle, right in zip(pivots, pivots[1:], pivots[2:]):
        if right.confirm > end:
            continue
        if max_monitor_bars is not None and end - right.confirm > max_monitor_bars:
            continue
        types = left.typ + middle.typ + right.typ
        if types not in {"LHL", "HLH"}:
            continue
        pattern = "w_bottom" if types == "LHL" else "m_top"
        reference = max(abs(left.price), 1e-12)
        deviation = abs(right.price - left.price) / reference
        if deviation > max_endpoint_deviation:
            continue
        if pattern == "w_bottom":
            base = min(left.price, right.price)
            depth = middle.price / base - 1.0 if base > 0 else 0.0
        else:
            top = max(left.price, right.price)
            depth = 1.0 - middle.price / top if top > 0 else 0.0
        if depth < min_depth_pct:
            continue
        breakout_idx = None
        invalidated_idx = None
        status = "right_bottom_confirmed" if pattern == "w_bottom" else "right_top_confirmed"
        for idx in range(right.confirm, end + 1):
            if pattern == "w_bottom":
                if low[idx] < min(left.price, right.price) * (1 - invalidation_pct):
                    invalidated_idx, status = idx, "invalidated"
                    break
                if close[idx] > middle.price * (1 + break_buffer_pct):
                    breakout_idx, status = idx, "neckline_breakout"
                    break
            else:
                if high[idx] > max(left.price, right.price) * (1 + invalidation_pct):
                    invalidated_idx, status = idx, "invalidated"
                    break
                if close[idx] < middle.price * (1 - break_buffer_pct):
                    breakout_idx, status = idx, "neckline_breakdown"
                    break
        symmetry_score = max(0.0, 1.0 - deviation / max_endpoint_deviation)
        depth_score = min(1.0, depth / 0.20)
        score = 0.65 * symmetry_score + 0.35 * depth_score
        result.append(DoublePattern(
            id=_id(scale, pattern, left, middle, right), scale=scale,
            pattern=pattern, status=status,
            left_idx=left.idx, middle_idx=middle.idx, right_idx=right.idx,
            left_price=float(left.price), middle_price=float(middle.price),
            right_price=float(right.price), left_duration=middle.idx - left.idx,
            right_duration=right.idx - middle.idx, total_bars=right.idx - left.idx,
            endpoint_deviation_pct=round(deviation * 100, 4),
            neckline=float(middle.price), depth_pct=round(depth * 100, 4),
            confirmation_idx=right.confirm, breakout_idx=breakout_idx,
            invalidated_idx=invalidated_idx, score=round(score, 4),
        ))
    ordered = sorted(result, key=lambda x: (
        x.status == "invalidated", -x.score, -x.right_idx,
    ))
    return ordered if max_results is None else ordered[:max_results]
