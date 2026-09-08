import pytest

from eastmoney_quant_mcp.strategies.patterns import Pivot
from eastmoney_quant_mcp.strategies.wave_analysis import (
    analyze_pivots,
    build_confirmed_zigzag,
)


def _dates(n=220):
    return [f"2026-01-{(i % 28) + 1:02d}" for i in range(n)]


def test_impulse_wave_scores_and_fib_retracements():
    pivots = [
        Pivot(10, "L", 100.0, 12),
        Pivot(30, "H", 130.0, 32),
        Pivot(50, "L", 111.46, 52),   # wave2 retrace ~= 0.618
        Pivot(80, "H", 170.0, 82),
        Pivot(100, "L", 147.65, 102), # wave4 retrace ~= 0.382
        Pivot(130, "H", 190.0, 132),
    ]
    rep = analyze_pivots(pivots, _dates(), current_close=185.0)

    impulse = rep["elliott_like_impulse"]
    assert impulse["structure"] == "impulse"
    assert impulse["direction"] == "up"
    assert impulse["score"] >= 80
    assert impulse["wave2_retrace"]["label"] == "0.618"
    assert impulse["wave4_retrace"]["label"] == "0.382"

    fib_summary = rep["fib_summary"]["up_pullback"]
    assert fib_summary["total"] == 2
    assert fib_summary["most_common"] in {"0.618", "0.382"}


def test_downtrend_rebound_summary_and_active_leg_levels():
    pivots = [
        Pivot(10, "H", 200.0, 12),
        Pivot(30, "L", 150.0, 32),
        Pivot(50, "H", 175.0, 52),  # rebound 0.5 of prior drop
        Pivot(80, "L", 120.0, 82),
        Pivot(100, "H", 154.0, 102), # rebound ~= 0.618 of prior drop
    ]
    rep = analyze_pivots(pivots, _dates(), current_close=140.0)

    summary = rep["fib_summary"]["down_rebound"]
    assert summary["total"] == 2
    assert summary["distribution"]["0.5"] == 1
    assert summary["distribution"]["0.618"] == 1
    assert rep["active_leg"]["direction"] == "down"
    assert rep["active_leg"]["status"] == "未确认结束"
    assert "fib_618" in rep["active_leg"]["reference_levels"]


def test_build_confirmed_zigzag_respects_confirmation():
    import pandas as pd

    df = pd.DataFrame({
        "date": [f"2026-02-{i + 1:02d}" for i in range(13)],
        "high": [10, 11, 12, 13, 14, 20, 14, 13, 12, 11, 10, 9, 8],
        "low": [9, 10, 11, 12, 13, 19, 13, 12, 11, 10, 9, 8, 7],
    })

    early = build_confirmed_zigzag(df, pivot_left=2, pivot_right=2, as_of_idx=5)
    confirmed = build_confirmed_zigzag(df, pivot_left=2, pivot_right=2, as_of_idx=7)

    assert early == []
    assert confirmed
    assert confirmed[0].typ == "H"
    assert confirmed[0].idx == 5
