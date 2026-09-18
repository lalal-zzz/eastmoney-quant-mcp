from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from ..patterns.pivots import Pivot
from .models import Channel, HorizontalRange, TrendLine


def _hash(prefix: str, *parts) -> str:
    raw = ":".join(str(x) for x in parts)
    return prefix + hashlib.sha1(raw.encode()).hexdigest()[:16]


def detect_channels(df: pd.DataFrame, pivots: list[Pivot], lines: list[TrendLine], *,
                    scale: str, atr: pd.Series, as_of_idx: int | None = None,
                    tolerance_atr: float = 0.45,
                    break_atr: float = 0.6) -> list[Channel]:
    """Build fixed-width parallel channels from confirmed trend lines."""
    if df.empty:
        return []
    end = len(df) - 1 if as_of_idx is None else min(as_of_idx, len(df) - 1)
    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()
    result = []
    confirmed_lines = [x for x in lines if x.scale == scale and x.status == "confirmed" and x.kind == "trendline"]
    for line in confirmed_lines:
        if line.scale != scale:
            continue
        opposite = "H" if line.role == "support" else "L"
        candidates = [p for p in pivots if p.typ == opposite and line.anchor1_idx <= p.idx <= end]
        if not candidates:
            continue
        baseline_intercept = line.anchor1_price - line.slope * line.anchor1_idx
        offsets = [p.price - (baseline_intercept + line.slope * p.idx) for p in candidates]
        valid = [(p, off) for p, off in zip(candidates, offsets)
                 if (line.role == "support" and off > 0) or (line.role == "resistance" and off < 0)]
        if not valid:
            continue
        # Use the most extreme opposite pivot to fix the width; never resize later
        edge_pivot, offset = (max(valid, key=lambda x: x[1]) if line.role == "support"
                              else min(valid, key=lambda x: x[1]))
        opposite_intercept = baseline_intercept + offset
        lower_i, upper_i = ((baseline_intercept, opposite_intercept) if line.role == "support"
                            else (opposite_intercept, baseline_intercept))
        lower, upper = [], []
        for p in pivots:
            if p.idx < line.anchor1_idx or p.idx > end:
                continue
            av = float(atr.iloc[p.idx]) if pd.notna(atr.iloc[p.idx]) else p.price * 0.02
            tol = max(tolerance_atr * av, p.price * 0.002)
            if p.typ == "L" and abs(p.price - (lower_i + line.slope * p.idx)) <= tol:
                lower.append(p.idx)
            if p.typ == "H" and abs(p.price - (upper_i + line.slope * p.idx)) <= tol:
                upper.append(p.idx)
        confirmation = None
        if len(set(lower)) >= 2 and len(set(upper)) >= 2:
            confirmation = max(sorted(set(lower))[1], sorted(set(upper))[1])
        broken_idx = None
        for idx in range(confirmation or edge_pivot.confirm, end + 1):
            midline = (lower_i + upper_i) / 2 + line.slope * idx
            av = float(atr.iloc[idx]) if pd.notna(atr.iloc[idx]) else abs(midline) * 0.02
            if low[idx] < lower_i + line.slope * idx - break_atr * av:
                broken_idx = idx
                break
            if high[idx] > upper_i + line.slope * idx + break_atr * av:
                broken_idx = idx
                break
        status = "broken" if broken_idx is not None else ("confirmed" if confirmation is not None else "candidate")
        # The opposite boundary is either an independently confirmed
        # trendline with the same slope, or a fixed translation of the
        # baseline through a tested opposite pivot.  Expose which one was
        # used so a daily snapshot does not present a guessed channel as fact.
        construction = "translated"
        source_line_id = None
        for other in confirmed_lines:
            if other.id == line.id or other.role == line.role:
                continue
            if abs(other.slope - line.slope) <= max(float(atr.iloc[end]) * 0.01, abs(line.slope) * 0.15):
                other_intercept = other.anchor1_price - other.slope * other.anchor1_idx
                if abs(other_intercept - opposite_intercept) <= max(float(atr.iloc[end]) * tolerance_atr, abs(opposite_intercept) * 0.002):
                    construction = "independent_trendlines"
                    source_line_id = other.id
                    break
        score = min(1.0, 0.35 + 0.1 * len(set(lower)) + 0.1 * len(set(upper)))
        result.append(Channel(
            id=_hash("channel_", line.id, edge_pivot.idx), scale=scale,
            direction="up" if line.slope > 0 else "down", status=status,
            baseline_id=line.id, slope=line.slope,
            lower_intercept=float(lower_i), upper_intercept=float(upper_i),
            lower_touches=tuple(sorted(set(lower))), upper_touches=tuple(sorted(set(upper))),
            confirmation_idx=confirmation, broken_idx=broken_idx, score=round(score, 4),
            construction=construction, source_line_id=source_line_id,
        ))
    result.sort(key=lambda x: (x.status != "confirmed", x.status == "broken", -x.score))
    return result


def _clusters(points: list[Pivot], tolerance_pct: float) -> list[list[Pivot]]:
    result: list[list[Pivot]] = []
    for point in sorted(points, key=lambda p: p.price):
        placed = False
        for cluster in result:
            center = float(np.median([p.price for p in cluster]))
            if center > 0 and abs(point.price / center - 1) <= tolerance_pct:
                cluster.append(point)
                placed = True
                break
        if not placed:
            result.append([point])
    return result


def detect_horizontal_ranges(df: pd.DataFrame, pivots: list[Pivot], *, scale: str,
                             as_of_idx: int | None = None,
                             tolerance_pct: float = 0.025,
                             min_width_pct: float = 0.05,
                             max_drift_pct: float = 0.03,
                             max_results: int = 12) -> list[HorizontalRange]:
    """Find ranges with repeated, independently tested upper and lower zones."""
    if df.empty:
        return []
    end = len(df) - 1 if as_of_idx is None else min(as_of_idx, len(df) - 1)
    highs = [c for c in _clusters([p for p in pivots if p.typ == "H" and p.idx <= end], tolerance_pct)
             if len(c) >= 2]
    lows = [c for c in _clusters([p for p in pivots if p.typ == "L" and p.idx <= end], tolerance_pct)
            if len(c) >= 2]
    close = df["close"].astype(float).to_numpy()
    result = []
    for hc in highs:
        upper = float(np.median([p.price for p in hc]))
        for lc in lows:
            lower = float(np.median([p.price for p in lc]))
            if lower <= 0 or upper / lower - 1 < min_width_pct:
                continue
            hidx, lidx = sorted(p.idx for p in hc), sorted(p.idx for p in lc)
            start, finish = min(hidx[0], lidx[0]), max(hidx[-1], lidx[-1])
            if max(hidx[0], lidx[0]) > min(hidx[-1], lidx[-1]):
                continue  # no temporal overlap between both tested zones
            h_drift = (max(p.price for p in hc) - min(p.price for p in hc)) / upper
            l_drift = (max(p.price for p in lc) - min(p.price for p in lc)) / lower
            if h_drift > max_drift_pct or l_drift > max_drift_pct:
                continue
            broken_direction = None
            broken_idx = None
            for idx in range(finish + 1, end + 1):
                if close[idx] > upper * (1 + tolerance_pct):
                    broken_direction, broken_idx = "up", idx
                    break
                if close[idx] < lower * (1 - tolerance_pct):
                    broken_direction, broken_idx = "down", idx
                    break
            status = "broken" if broken_idx is not None else "confirmed"
            result.append(HorizontalRange(
                id=_hash("range_", scale, round(lower, 6), round(upper, 6), start),
                scale=scale, status=status, start_idx=start, end_idx=finish,
                lower=round(lower, 6), upper=round(upper, 6),
                lower_touches=tuple(lidx), upper_touches=tuple(hidx),
                broken_direction=broken_direction, broken_idx=broken_idx,
                score=round(min(1.0, 0.4 + 0.1 * len(lidx) + 0.1 * len(hidx)), 4),
            ))
    result.sort(key=lambda x: (x.status == "broken", -x.score, -x.end_idx))
    return result[:max_results]
