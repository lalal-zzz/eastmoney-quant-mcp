from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ZoneRule:
    zone_id: str
    symbol: str
    timeframe: str
    lower: float
    upper: float
    approach_pct: float = 0.01
    break_buffer_pct: float = 0.002
    reset_pct: float = 0.015
    invalidated: bool = False

    def __post_init__(self):
        if self.lower > self.upper:
            raise ValueError("zone lower cannot exceed upper")
        if self.lower <= 0:
            raise ValueError("zone prices must be positive")


@dataclass(frozen=True)
class PriceUpdate:
    timestamp: str
    close: float
    high: float | None = None
    low: float | None = None
    closed: bool = False


@dataclass
class AlertState:
    zone_id: str
    episode: int = 1
    relation: str = "unknown"
    emitted: set[str] = field(default_factory=set)
    invalidated: bool = False
    last_timestamp: str | None = None


@dataclass(frozen=True)
class AlertEvent:
    idempotency_key: str
    zone_id: str
    symbol: str
    timeframe: str
    episode: int
    event_type: str
    timestamp: str
    close: float
    lower: float
    upper: float
    confirmed: bool
