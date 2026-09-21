from __future__ import annotations

import hashlib

from ..structure.models import Leg
from .models import FibAnchorCandidate


def select_anchor_candidates(legs_by_scale: dict[str, list[Leg]], *,
                             as_of_idx: int, max_per_scale: int = 5,
                             min_bars: int = 3, min_atr_move: float = 1.0) -> list[FibAnchorCandidate]:
    """Rank confirmed structural legs without looking at current Fib proximity."""
    result = []
    for scale, legs in legs_by_scale.items():
        eligible = [x for x in legs if x.confirmed_at_idx <= as_of_idx and x.bars >= min_bars
                    and (x.atr_move is None or x.atr_move >= min_atr_move)]
        ranked = sorted(eligible, key=lambda x: (
            -(x.atr_move or abs(x.price_change_pct)), -x.bars, -x.end_idx, x.id
        ))[:max_per_scale]
        for order, leg in enumerate(ranked):
            raw = f"{leg.id}:fib-anchor"
            result.append(FibAnchorCandidate(
                id="anchor_" + hashlib.sha1(raw.encode()).hexdigest()[:16],
                source="confirmed_leg", scale=scale,
                rank=round(1.0 / (order + 1), 6),
                a_idx=leg.start_idx, a_price=leg.start_price,
                b_idx=leg.end_idx, b_price=leg.end_price,
                direction=leg.direction, confirmed_at_idx=leg.confirmed_at_idx,
                dependency_group=leg.id,
            ))
    return sorted(result, key=lambda x: (-x.rank, x.scale, -x.b_idx, x.id))
