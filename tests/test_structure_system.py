from dataclasses import asdict

import pandas as pd
import pytest

from eastmoney_quant_mcp.strategies.patterns import Pivot
from eastmoney_quant_mcp.strategies.position import (
    FibAnchorCandidate,
    build_confluence_zones,
    evaluate_projection,
    evaluate_retracement,
    fibonacci_zones,
    projection_targets,
)
from eastmoney_quant_mcp.strategies.structure import (
    analyze_market_structure,
    compact_market_structure,
    detect_channels,
    detect_double_patterns,
    detect_horizontal_ranges,
    detect_trendlines,
)
from eastmoney_quant_mcp.strategies.structure.models import TrendLine
from eastmoney_quant_mcp.strategies.structure.timeframes import resample_ohlcv


def _frame(n=60):
    close = [15.0 + i * 0.05 for i in range(n)]
    return pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=n, freq="D"),
        "open": close,
        "high": [x + 1.0 for x in close],
        "low": [x - 1.0 for x in close],
        "close": close,
        "volume": [1000.0] * n,
    })


def _anchor(direction="up"):
    a, b = ((10.0, 20.0) if direction == "up" else (20.0, 10.0))
    return FibAnchorCandidate(
        id="a1", source="confirmed_leg", scale="medium", rank=1.0,
        a_idx=1, a_price=a, b_idx=10, b_price=b, direction=direction,
        confirmed_at_idx=12, dependency_group="leg1",
    )


def test_trendline_two_points_define_third_confirms_without_moving_anchors():
    df = _frame()
    atr = pd.Series([2.0] * len(df))
    pivots = [
        Pivot(5, "L", 10.0, 7), Pivot(10, "H", 18.0, 12),
        Pivot(15, "L", 12.0, 17), Pivot(20, "H", 20.0, 22),
        Pivot(25, "L", 14.0, 27),
    ]
    lines = detect_trendlines(df, pivots, scale="medium", atr=atr,
                              as_of_idx=30, tolerance_atr=0.01, break_atr=10.0)
    confirmed = [x for x in lines if x.role == "support" and x.status == "confirmed"]
    assert confirmed
    line = next(x for x in confirmed if x.anchor1_idx == 5 and x.anchor2_idx == 15)
    assert line.confirmation_idx == 27
    assert line.touch_indices == (5, 15, 25)
    assert line.value_at(25) == pytest.approx(14.0)


def test_old_slope_converts_to_horizontal_level_after_extension_window():
    df = _frame(60)
    atr = pd.Series([2.0] * len(df))
    pivots = [
        Pivot(5, "L", 10.0, 7), Pivot(15, "L", 12.0, 17),
        Pivot(25, "L", 14.0, 27),
    ]
    lines = detect_trendlines(
        df, pivots, scale="medium", atr=atr, max_extension_bars=5,
        break_atr=10.0,
    )
    converted = [x for x in lines if x.anchor1_idx == 5 and x.anchor2_idx == 15]
    assert converted
    assert converted[0].kind == "horizontal_level"
    assert converted[0].status == "converted"
    assert converted[0].valid_until_idx == 35
    assert converted[0].converted_level == pytest.approx(16.0)


def test_trendline_is_broken_by_wick_even_when_close_stays_inside():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=35, freq="D"),
        "open": [15.0] * 35,
        "high": [15.5] * 35,
        "low": [14.5] * 35,
        "close": [15.0] * 35,
        "volume": [1000.0] * 35,
    })
    # Resistance through (5,20) and (15,18); the close remains below it, but
    # the wick at 20 crosses it by more than the break buffer.
    df.loc[20, "high"] = 18.5
    pivots = [
        Pivot(5, "H", 20.0, 7), Pivot(15, "H", 18.0, 17),
        Pivot(25, "H", 16.0, 27),
    ]
    lines = detect_trendlines(
        df, pivots, scale="medium", atr=pd.Series([1.0] * len(df)),
        as_of_idx=30, tolerance_atr=0.01, break_atr=0.5,
    )
    line = next(x for x in lines if x.anchor1_idx == 5 and x.anchor2_idx == 15)
    assert line.status == "broken"
    assert line.broken_idx == 20


def test_channel_is_broken_by_wick_even_when_close_stays_inside():
    df = pd.DataFrame({
        "date": pd.date_range("2026-01-01", periods=35, freq="D"),
        "open": [15.0] * 35,
        "high": [16.0] * 35,
        "low": [14.0] * 35,
        "close": [15.0] * 35,
        "volume": [1000.0] * 35,
    })
    # Horizontal closes remain inside the rising channel; a single upper wick
    # exits the fixed upper boundary after confirmation.
    df.loc[26, "high"] = 20.0
    line = TrendLine(
        id="support", scale="medium", role="support", status="confirmed",
        anchor1_idx=5, anchor1_price=10.5, anchor2_idx=15,
        anchor2_price=11.5, slope=0.1, confirmation_idx=25,
        touch_indices=(5, 15, 25), broken_idx=None, tolerance=0.1,
        score=0.9,
    )
    pivots = [
        Pivot(5, "L", 10.5, 7), Pivot(8, "H", 16.8, 10),
        Pivot(15, "L", 11.5, 17), Pivot(18, "H", 17.8, 20),
        Pivot(25, "L", 12.5, 27), Pivot(28, "H", 18.8, 30),
    ]
    channels = detect_channels(
        df, pivots, [line], scale="medium", atr=pd.Series([1.0] * len(df)),
        as_of_idx=30, tolerance_atr=0.01, break_atr=0.6,
    )
    assert channels
    assert channels[0].status == "broken"
    assert channels[0].broken_idx == 26


def test_horizontal_range_requires_both_sides_retested():
    df = _frame(50)
    pivots = [
        Pivot(5, "H", 20.0, 7), Pivot(10, "L", 10.0, 12),
        Pivot(15, "H", 20.2, 17), Pivot(20, "L", 10.1, 22),
        Pivot(25, "H", 19.9, 27), Pivot(30, "L", 9.9, 32),
    ]
    ranges = detect_horizontal_ranges(df, pivots, scale="medium", tolerance_pct=0.025)
    assert ranges
    assert ranges[0].upper == pytest.approx(20.0)
    assert ranges[0].lower == pytest.approx(10.0)
    assert len(ranges[0].upper_touches) >= 2
    assert len(ranges[0].lower_touches) >= 2


def test_asymmetric_w_has_no_maximum_right_duration_and_reports_it():
    df = _frame(180)
    df.loc[150:, "close"] = 17.0
    pivots = [
        Pivot(10, "L", 10.0, 12),
        Pivot(25, "H", 15.0, 27),
        Pivot(140, "L", 10.4, 142),
    ]
    patterns = detect_double_patterns(df, pivots, scale="coarse", break_buffer_pct=0.01)
    assert len(patterns) == 1
    pattern = patterns[0]
    assert pattern.pattern == "w_bottom"
    assert pattern.right_duration == 115
    assert pattern.left_duration == 15
    assert pattern.status == "neckline_breakout"


def test_retracement_position_and_projection_have_distinct_origins():
    anchor = _anchor("up")
    retracement = evaluate_retracement(anchor, 21.0, path_after_b=[20.0, 15.0, 21.0])
    projection = evaluate_projection(anchor, c_price=15.0, current_price=21.0, c_confirmed=True)
    assert retracement.retracement_ratio == pytest.approx(-0.1)
    assert retracement.position_ratio == pytest.approx(1.1)
    assert retracement.phase == "resumed"
    assert projection.projection_ratio == pytest.approx(0.6)
    assert projection_targets(anchor, c_price=15.0)[0] == {"multiple": 1.0, "price": 25.0}


def test_down_move_retracement_is_direction_aware_and_over_retrace_is_separate():
    anchor = _anchor("down")
    half = evaluate_retracement(anchor, 15.0, path_after_b=[10.0, 15.0])
    over = evaluate_retracement(anchor, 21.0, path_after_b=[10.0, 21.0])
    assert half.retracement_ratio == pytest.approx(0.5)
    assert half.phase == "retracing"
    assert over.retracement_ratio == pytest.approx(1.1)
    assert over.phase == "over_retraced"


def test_same_swing_levels_do_not_fake_independent_confluence():
    zones = fibonacci_zones(_anchor(), atr=2.0, ratios=(0.5,))
    row = {**asdict(zones[0]), "family": "fibonacci_same_swing"}
    duplicate = {**row, "id": "indicator-wrapper"}
    clusters = build_confluence_zones([row, duplicate])
    assert len(clusters) == 1
    assert clusters[0]["raw_level_count"] == 2
    assert clusters[0]["independent_dependency_count"] == 1


def test_market_structure_snapshot_contains_positions_but_no_wave_labels():
    df = _frame(120)
    snapshot = analyze_market_structure(df)
    assert {"scales", "trendlines", "channels", "ranges", "double_patterns", "positions"} <= snapshot.keys()
    compact = compact_market_structure(snapshot, current_price=float(df.iloc[-1]["close"]))
    assert "converted_levels" in compact
    assert {"anchors", "retracements", "projections", "fib_zones", "confluence_zones"} <= snapshot["positions"].keys()
    assert "wave" not in snapshot


def test_weekly_monthly_resampling_preserves_real_ohlc_and_source_date():
    dates = pd.bdate_range("2024-01-02", periods=45)
    df = pd.DataFrame({
        "date": dates,
        "open": range(100, 145),
        "high": range(102, 147),
        "low": range(98, 143),
        "close": range(101, 146),
        "volume": [10] * 45,
    })
    weekly = resample_ohlcv(df, "weekly")
    monthly = resample_ohlcv(df, "monthly")
    assert len(weekly) >= 8
    assert len(monthly) >= 2
    assert weekly.iloc[0]["open"] == df.iloc[0]["open"]
    assert weekly.iloc[0]["high"] == df.iloc[:4]["high"].max()
    assert pd.Timestamp(weekly.iloc[0]["source_date"]) == dates[3]
    assert monthly["volume"].sum() == df["volume"].sum()


def test_compact_snapshot_preserves_counts_and_bounds_public_details():
    df = _frame(240)
    full = analyze_market_structure(df)
    compact = compact_market_structure(full, current_price=float(df.iloc[-1]["close"]))
    for scale, row in compact["scales"].items():
        assert row["pivot_count"] == len(full["scales"][scale]["pivots"])
        assert len(row["pivots"]) <= 20
        assert len(row["legs"]) <= 20
    assert len(compact["positions"]["anchors"]) <= 9
    assert len(compact["positions"]["confluence_zones"]) <= 12
