from __future__ import annotations

from .models import FibAnchorCandidate, Projection


PROJECTION_RATIOS = (1.0, 1.272, 1.618, 2.0, 2.618)


def evaluate_projection(anchor: FibAnchorCandidate, *, c_price: float,
                        current_price: float, c_confirmed: bool) -> Projection:
    move = anchor.b_price - anchor.a_price
    if move == 0:
        raise ValueError("A and B cannot have the same price")
    ratio = (current_price - c_price) / move
    return Projection(
        anchor_id=anchor.id, direction=anchor.direction,
        a_price=anchor.a_price, b_price=anchor.b_price, c_price=float(c_price),
        c_confirmed=bool(c_confirmed), current_price=float(current_price),
        projection_ratio=round(ratio, 8),
        availability="active" if c_confirmed else "provisional",
    )


def projection_targets(anchor: FibAnchorCandidate, *, c_price: float,
                       ratios: tuple[float, ...] = PROJECTION_RATIOS) -> list[dict]:
    move = anchor.b_price - anchor.a_price
    if move == 0:
        return []
    return [{"multiple": float(r), "price": round(c_price + r * move, 8)} for r in ratios]
