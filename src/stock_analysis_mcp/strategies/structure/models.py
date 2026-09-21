from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Leg:
    id: str
    scale: str
    start_idx: int
    end_idx: int
    start_type: str
    end_type: str
    start_price: float
    end_price: float
    direction: str
    price_change_pct: float
    bars: int
    atr_move: float | None
    confirmed_at_idx: int


@dataclass(frozen=True)
class TrendLine:
    id: str
    scale: str
    role: str
    status: str
    anchor1_idx: int
    anchor1_price: float
    anchor2_idx: int
    anchor2_price: float
    slope: float
    confirmation_idx: int | None
    touch_indices: tuple[int, ...]
    broken_idx: int | None
    tolerance: float
    score: float
    kind: str = "trendline"
    valid_until_idx: int | None = None
    converted_level: float | None = None

    def value_at(self, idx: int) -> float:
        return self.anchor1_price + self.slope * (idx - self.anchor1_idx)


@dataclass(frozen=True)
class Channel:
    id: str
    scale: str
    direction: str
    status: str
    baseline_id: str
    slope: float
    lower_intercept: float
    upper_intercept: float
    lower_touches: tuple[int, ...]
    upper_touches: tuple[int, ...]
    confirmation_idx: int | None
    broken_idx: int | None
    score: float
    construction: str = "translated"
    source_line_id: str | None = None

    def lower_at(self, idx: int) -> float:
        return self.lower_intercept + self.slope * idx

    def upper_at(self, idx: int) -> float:
        return self.upper_intercept + self.slope * idx


@dataclass(frozen=True)
class HorizontalRange:
    id: str
    scale: str
    status: str
    start_idx: int
    end_idx: int
    lower: float
    upper: float
    lower_touches: tuple[int, ...]
    upper_touches: tuple[int, ...]
    broken_direction: str | None
    broken_idx: int | None
    score: float


@dataclass(frozen=True)
class DoublePattern:
    id: str
    scale: str
    pattern: str
    status: str
    left_idx: int
    middle_idx: int
    right_idx: int
    left_price: float
    middle_price: float
    right_price: float
    left_duration: int
    right_duration: int
    total_bars: int
    endpoint_deviation_pct: float
    neckline: float
    depth_pct: float
    confirmation_idx: int
    breakout_idx: int | None
    invalidated_idx: int | None
    score: float


@dataclass
class StructureSnapshot:
    as_of_idx: int
    scales: dict[str, dict[str, Any]] = field(default_factory=dict)
    trendlines: list[TrendLine] = field(default_factory=list)
    channels: list[Channel] = field(default_factory=list)
    ranges: list[HorizontalRange] = field(default_factory=list)
    double_patterns: list[DoublePattern] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of_idx": self.as_of_idx,
            "scales": self.scales,
            "trendlines": [asdict(x) for x in self.trendlines],
            "channels": [asdict(x) for x in self.channels],
            "ranges": [asdict(x) for x in self.ranges],
            "double_patterns": [asdict(x) for x in self.double_patterns],
        }
