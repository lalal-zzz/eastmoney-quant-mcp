from __future__ import annotations

import hashlib

import pandas as pd

from ..patterns.pivots import Pivot
from .models import TrendLine


def _id(scale: str, role: str, a: Pivot, b: Pivot) -> str:
    raw = f"{scale}:{role}:{a.idx}:{a.price:.8f}:{b.idx}:{b.price:.8f}"
    return "line_" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def detect_trendlines(df: pd.DataFrame, pivots: list[Pivot], *, scale: str,
                      atr: pd.Series, as_of_idx: int | None = None,
                      tolerance_atr: float = 0.35,
                      break_atr: float = 0.5,
                      min_separation: int = 3,
                      max_points_per_role: int = 48,
                      max_lines_per_role: int = 8,
                      max_extension_bars: int = 120,
                      max_span_bars: int = 120) -> list[TrendLine]:
    """Two pivots define a line; a later independent pivot confirms it."""
    if df.empty:
        return []
    end = len(df) - 1 if as_of_idx is None else min(as_of_idx, len(df) - 1)
    close = df["close"].astype(float).to_numpy()
    output: list[TrendLine] = []
    for typ, role in (("L", "support"), ("H", "resistance")):
        # Long history remains represented by coarse-scale pivots, while an
        # interactive snapshot only needs a bounded set of recent anchors.
        # This prevents O(P²*N) line validation from growing without limit.
        points = [p for p in pivots if p.typ == typ and p.idx <= end][-max_points_per_role:]
        role_output: list[TrendLine] = []
        for ai, a in enumerate(points[:-1]):
            for b in points[ai + 1:]:
                if b.idx - a.idx < min_separation:
                    continue
                slope = (b.price - a.price) / (b.idx - a.idx)
                if (role == "support" and slope <= 0) or (role == "resistance" and slope >= 0):
                    continue
                touches = [a.idx, b.idx]
                confirm_idx = None
                for p in points:
                    if p.idx <= b.idx or p.idx - touches[-1] < min_separation:
                        continue
                    expected = a.price + slope * (p.idx - a.idx)
                    tol = max(float(atr.iloc[p.idx]) * tolerance_atr, abs(expected) * 0.002)
                    if abs(p.price - expected) <= tol:
                        touches.append(p.idx)
                        if confirm_idx is None:
                            confirm_idx = p.confirm
                # Validate the whole segment from the first anchor onward.
                # A line that was crossed between its anchors (or before the
                # third touch) is already invalid; it must not be promoted to
                # confirmed merely because a later pivot happens to align.
                broken = None
                for idx in range(max(a.idx + 1, 0), end + 1):
                    expected = a.price + slope * (idx - a.idx)
                    av = float(atr.iloc[idx]) if pd.notna(atr.iloc[idx]) else abs(expected) * 0.02
                    if role == "support" and close[idx] < expected - break_atr * av:
                        broken = idx
                        break
                    if role == "resistance" and close[idx] > expected + break_atr * av:
                        broken = idx
                        break
                status = "broken" if broken is not None else ("confirmed" if confirm_idx is not None else "candidate")
                # A sloping line is a local geometric relationship.  Once the
                # second anchor is far behind the active price, keep the
                # historical evidence but convert the current interpretation
                # to a horizontal level instead of extrapolating forever.
                span = b.idx - a.idx
                valid_until = b.idx + max(20, min(max_extension_bars, span))
                kind = "trendline"
                converted_level = None
                # A very long anchor-to-anchor slope is no longer a local
                # trendline.  Keep it as evidence, but expose the level that
                # traders can actually use as horizontal support/resistance.
                # This also prevents a chart from drawing a diagonal across
                # an entire regime and calling it a trendline.
                if (span > max_span_bars or end > valid_until) and status == "confirmed":
                    kind = "horizontal_level"
                    converted_level = float(b.price) if span > max_span_bars else a.price + slope * (valid_until - a.idx)
                    status = "converted"
                current = a.price + slope * (end - a.idx)
                tol_now = max(float(atr.iloc[end]) * tolerance_atr, abs(current) * 0.002)
                score = min(1.0, 0.45 + 0.15 * max(0, len(touches) - 2) + min(0.25, (b.idx - a.idx) / 200))
                role_output.append(TrendLine(
                    id=_id(scale, role, a, b), scale=scale, role=role, status=status,
                    anchor1_idx=a.idx, anchor1_price=float(a.price),
                    anchor2_idx=b.idx, anchor2_price=float(b.price), slope=float(slope),
                    confirmation_idx=confirm_idx, touch_indices=tuple(touches),
                    broken_idx=broken, tolerance=round(tol_now, 6), score=round(score, 4),
                    kind=kind, valid_until_idx=int(valid_until),
                    converted_level=round(float(converted_level), 6) if converted_level is not None else None,
                ))
        role_output.sort(key=lambda x: (
            x.kind != "trendline", x.status != "confirmed", x.status == "broken", -x.score, -x.anchor2_idx,
        ))
        # Keep a bounded set of each interpretation.  Otherwise a handful of
        # recent short slopes can crowd out converted long-span levels and the
        # caller cannot see that those old diagonals should now be horizontal.
        slopes = [x for x in role_output if x.kind == "trendline"][:max_lines_per_role]
        levels = [x for x in role_output if x.kind == "horizontal_level"][:max_lines_per_role]
        output.extend(slopes + levels)
    output.sort(key=lambda x: (x.status != "confirmed", x.status == "broken", -x.score, -x.anchor2_idx))
    return output
