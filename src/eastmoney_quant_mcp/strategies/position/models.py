from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FibAnchorCandidate:
    id: str
    source: str
    scale: str
    rank: float
    a_idx: int
    a_price: float
    b_idx: int
    b_price: float
    direction: str
    confirmed_at_idx: int
    dependency_group: str


@dataclass(frozen=True)
class FibRetracement:
    anchor_id: str
    direction: str
    current_price: float
    retracement_ratio: float
    position_ratio: float
    phase: str
    availability: str = "active"


@dataclass(frozen=True)
class Projection:
    anchor_id: str
    direction: str
    a_price: float
    b_price: float
    c_price: float
    c_confirmed: bool
    current_price: float
    projection_ratio: float
    availability: str


@dataclass(frozen=True)
class FibZone:
    id: str
    anchor_id: str
    kind: str
    ratio: float
    center: float
    lower: float
    upper: float
    dependency_group: str
