"""Objective market-structure primitives shared by screening and alerts.

This package deliberately contains no Elliott-wave labels.  It turns confirmed
price pivots into observable legs, trend lines and channels.
"""

from .engine import analyze_market_structure
from .models import Channel, DoublePattern, HorizontalRange, Leg, StructureSnapshot, TrendLine
from .pivots import build_legs, build_multiscale_zigzags, confirmed_zigzag
from .trendlines import detect_trendlines
from .channels import detect_channels, detect_horizontal_ranges
from .double_patterns import detect_double_patterns
from .compact import compact_market_structure
from .timeframes import analyze_multi_timeframe_structure, resample_ohlcv

__all__ = [
    "Channel", "DoublePattern", "HorizontalRange", "Leg", "StructureSnapshot", "TrendLine",
    "analyze_market_structure", "build_legs", "build_multiscale_zigzags",
    "confirmed_zigzag", "detect_trendlines", "detect_channels",
    "detect_horizontal_ranges", "detect_double_patterns", "compact_market_structure",
    "analyze_multi_timeframe_structure", "resample_ohlcv",
]
