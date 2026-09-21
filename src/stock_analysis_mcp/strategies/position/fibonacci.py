from __future__ import annotations

import hashlib

from .models import FibAnchorCandidate, FibRetracement, FibZone


RETRACEMENT_RATIOS = (0.236, 0.382, 0.5, 0.618, 0.786, 1.0)


def evaluate_retracement(anchor: FibAnchorCandidate, current_price: float, *,
                         path_after_b: list[float] | None = None,
                         resume_buffer: float = 0.0,
                         over_buffer: float = 0.0) -> FibRetracement:
    move = anchor.b_price - anchor.a_price
    if move == 0:
        raise ValueError("A and B cannot have the same price")
    retracement = (anchor.b_price - current_price) / move
    position = (current_price - anchor.a_price) / move
    path = path_after_b or [current_price]
    adverse = [(anchor.b_price - p) / move for p in path]
    max_retrace = max(adverse) if adverse else retracement
    had_retrace = max_retrace > 0.0
    if retracement > 1.0 + over_buffer:
        phase = "over_retraced"
    elif had_retrace and position > 1.0 + resume_buffer:
        phase = "resumed"
    elif had_retrace and retracement <= 0:
        phase = "retracement_confirming"
    elif had_retrace:
        phase = "retracing"
    else:
        phase = "impulse"
    return FibRetracement(
        anchor_id=anchor.id, direction=anchor.direction,
        current_price=float(current_price), retracement_ratio=round(retracement, 8),
        position_ratio=round(position, 8), phase=phase,
    )


def fibonacci_zones(anchor: FibAnchorCandidate, *, atr: float,
                    ratios: tuple[float, ...] = RETRACEMENT_RATIOS,
                    tolerance_atr: float = 0.15,
                    tick_size: float = 0.01) -> list[FibZone]:
    move = anchor.b_price - anchor.a_price
    if move == 0:
        return []
    tolerance = max(abs(float(atr)) * tolerance_atr, tick_size)
    result = []
    for ratio in ratios:
        center = anchor.b_price - ratio * move
        raw = f"{anchor.id}:retracement:{ratio:.6f}"
        result.append(FibZone(
            id="fib_" + hashlib.sha1(raw.encode()).hexdigest()[:16],
            anchor_id=anchor.id, kind="retracement", ratio=float(ratio),
            center=round(center, 8), lower=round(center - tolerance, 8),
            upper=round(center + tolerance, 8), dependency_group=anchor.dependency_group,
        ))
    return result
