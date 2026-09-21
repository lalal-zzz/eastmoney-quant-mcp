from __future__ import annotations

from dataclasses import asdict
import pandas as pd

from .channels import detect_channels, detect_horizontal_ranges
from .double_patterns import detect_double_patterns
from .models import StructureSnapshot
from .pivots import DEFAULT_SCALES, build_legs, build_multiscale_zigzags
from .trendlines import detect_trendlines


def _atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    prev = df["close"].astype(float).shift(1)
    tr = pd.concat([
        df["high"].astype(float) - df["low"].astype(float),
        (df["high"].astype(float) - prev).abs(),
        (df["low"].astype(float) - prev).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window, min_periods=1).mean()


def analyze_market_structure(df: pd.DataFrame, *, as_of_idx: int | None = None,
                             scales: dict | None = None,
                             include_positions: bool = True) -> dict:
    """Return observable structures only; no wave labels or predictions."""
    required = {"high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing OHLC columns: {sorted(missing)}")
    if df.empty:
        return StructureSnapshot(as_of_idx=-1).to_dict()
    end = len(df) - 1 if as_of_idx is None else min(int(as_of_idx), len(df) - 1)
    specs = scales or DEFAULT_SCALES
    atr = _atr(df)
    zigzags = build_multiscale_zigzags(df, as_of_idx=end, scales=specs)
    snapshot = StructureSnapshot(as_of_idx=end)
    legs_by_scale = {}
    for scale, pivots in zigzags.items():
        legs = build_legs(pivots, scale=scale, atr=atr)
        legs_by_scale[scale] = legs
        snapshot.scales[scale] = {
            "pivots": [
                {"idx": p.idx, "type": p.typ, "price": round(float(p.price), 6),
                 "confirmed_at_idx": p.confirm}
                for p in pivots
            ],
            "legs": [vars(x) for x in legs],
        }
        lines = detect_trendlines(df, pivots, scale=scale, atr=atr, as_of_idx=end)
        snapshot.trendlines.extend(lines)
        snapshot.channels.extend(detect_channels(df, pivots, lines, scale=scale, atr=atr, as_of_idx=end))
        snapshot.ranges.extend(detect_horizontal_ranges(df, pivots, scale=scale, as_of_idx=end))
        monitor_bars = {"fine": 120, "medium": 250, "coarse": 750}.get(scale, 250)
        snapshot.double_patterns.extend(detect_double_patterns(
            df, pivots, scale=scale, as_of_idx=end,
            max_monitor_bars=monitor_bars, max_results=None,
        ))
    result = snapshot.to_dict()
    if include_positions:
        # Local import keeps the observation layer independent from position.
        from ..position import (
            build_confluence_zones,
            evaluate_projection,
            evaluate_retracement,
            fibonacci_zones,
            projection_targets,
            select_anchor_candidates,
        )
        anchors = select_anchor_candidates(legs_by_scale, as_of_idx=end)
        current = float(df["close"].iloc[end])
        av = float(atr.iloc[end])
        retracements, projections, zones = [], [], []
        leg_index = {(x.scale, x.start_idx): x for legs in legs_by_scale.values() for x in legs}
        for anchor in anchors:
            path = df["close"].iloc[anchor.b_idx:end + 1].astype(float).tolist()
            retracements.append(asdict(evaluate_retracement(anchor, current, path_after_b=path)))
            anchor_zones = fibonacci_zones(anchor, atr=av)
            zones.extend(anchor_zones)
            next_leg = leg_index.get((anchor.scale, anchor.b_idx))
            if next_leg is not None and next_leg.confirmed_at_idx <= end:
                projection = evaluate_projection(
                    anchor, c_price=next_leg.end_price, current_price=current, c_confirmed=True,
                )
                projections.append({
                    **asdict(projection),
                    "c_idx": next_leg.end_idx,
                    "targets": projection_targets(anchor, c_price=next_leg.end_price),
                })
        zone_rows = [{**asdict(x), "family": "fibonacci_same_swing"} for x in zones]
        result["positions"] = {
            "anchors": [asdict(x) for x in anchors],
            "retracements": retracements,
            "projections": projections,
            "fib_zones": zone_rows,
            "confluence_zones": build_confluence_zones(zone_rows),
        }
    return result
