from __future__ import annotations

import hashlib

import pandas as pd

from ..patterns.pivots import Pivot, build_pivot_events, update_zigzag
from .models import Leg


DEFAULT_SCALES = {
    "fine": {"left": 3, "right": 3, "swing_min": 0.02},
    "medium": {"left": 5, "right": 5, "swing_min": 0.04},
    "coarse": {"left": 10, "right": 10, "swing_min": 0.08},
}


def confirmed_zigzag(df: pd.DataFrame, *, left: int = 5, right: int = 5,
                     swing_min: float = 0.03, as_of_idx: int | None = None) -> list[Pivot]:
    """Build a zigzag using only pivots confirmed by ``as_of_idx``."""
    if df.empty:
        return []
    last = len(df) - 1 if as_of_idx is None else min(int(as_of_idx), len(df) - 1)
    result: list[Pivot] = []
    for event in build_pivot_events(df, left=left, right=right):
        if event.confirm > last:
            continue
        update_zigzag(result, event, swing_min=swing_min)
    return result


def build_multiscale_zigzags(df: pd.DataFrame, *, as_of_idx: int | None = None,
                             scales: dict | None = None) -> dict[str, list[Pivot]]:
    specs = scales or DEFAULT_SCALES
    return {
        name: confirmed_zigzag(df, as_of_idx=as_of_idx, **spec)
        for name, spec in specs.items()
    }


def _leg_id(scale: str, a: Pivot, b: Pivot) -> str:
    raw = f"{scale}:{a.idx}:{a.typ}:{a.price:.8f}:{b.idx}:{b.typ}:{b.price:.8f}"
    return "leg_" + hashlib.sha1(raw.encode()).hexdigest()[:16]


def build_legs(pivots: list[Pivot], *, scale: str, atr: pd.Series | None = None) -> list[Leg]:
    result = []
    for a, b in zip(pivots, pivots[1:]):
        move = b.price - a.price
        atr_value = None
        if atr is not None and 0 <= b.idx < len(atr):
            v = atr.iloc[b.idx]
            if pd.notna(v) and float(v) > 0:
                atr_value = abs(move) / float(v)
        result.append(Leg(
            id=_leg_id(scale, a, b), scale=scale,
            start_idx=a.idx, end_idx=b.idx, start_type=a.typ, end_type=b.typ,
            start_price=float(a.price), end_price=float(b.price),
            direction="up" if move > 0 else "down",
            price_change_pct=round(move / a.price * 100, 6) if a.price else 0.0,
            bars=b.idx - a.idx, atr_move=round(atr_value, 6) if atr_value is not None else None,
            confirmed_at_idx=b.confirm,
        ))
    return result
