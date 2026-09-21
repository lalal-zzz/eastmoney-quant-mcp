from __future__ import annotations

import pandas as pd

from .engine import analyze_market_structure


TIMEFRAME_RULES = {"daily": None, "weekly": "W-FRI", "monthly": "ME"}


def resample_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Build real daily/weekly/monthly OHLCV bars for structure analysis."""
    if timeframe not in TIMEFRAME_RULES:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    work = df.copy()
    work["date"] = pd.to_datetime(work["date"])
    work = work.sort_values("date").reset_index(drop=True)
    work["source_date"] = work["date"]
    if timeframe == "daily":
        return work
    agg: dict[str, str] = {
        "open": "first", "high": "max", "low": "min", "close": "last",
        "source_date": "last",
    }
    if "volume" in work.columns:
        agg["volume"] = "sum"
    return (work.set_index("date")
            .resample(TIMEFRAME_RULES[timeframe])
            .agg(agg)
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index())


def analyze_multi_timeframe_structure(
    df: pd.DataFrame,
    *,
    timeframes: tuple[str, ...] = ("daily", "weekly", "monthly"),
    include_positions: bool = True,
) -> dict:
    """Analyze each timeframe independently; no daily-shape promotion."""
    output = {}
    for timeframe in timeframes:
        bars = resample_ohlcv(df, timeframe)
        snapshot = analyze_market_structure(bars, include_positions=include_positions)
        snapshot["timeframe"] = timeframe
        snapshot["bar_count"] = len(bars)
        snapshot["as_of_date"] = (
            str(pd.Timestamp(bars.iloc[-1]["source_date"]).date()) if len(bars) else None
        )
        snapshot["latest_bar_may_be_incomplete"] = bool(
            len(bars)
            and timeframe != "daily"
            and pd.Timestamp(bars.iloc[-1]["date"]).date()
            > pd.Timestamp(bars.iloc[-1]["source_date"]).date()
        )
        output[timeframe] = snapshot
    return output
