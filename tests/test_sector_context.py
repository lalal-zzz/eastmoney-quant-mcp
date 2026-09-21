import pandas as pd

from stock_analysis_mcp.strategies.sector_context import (
    build_stock_sector_context,
    classify_sector_trend,
    score_sector_alignment,
)


def _frame(values):
    return pd.DataFrame({"close": values})


def test_sector_trend_requires_price_and_ma_slope_agreement():
    assert classify_sector_trend(_frame(list(range(1, 31)))) == "up"
    assert classify_sector_trend(_frame(list(range(31, 1, -1)))) == "down"
    assert classify_sector_trend(_frame([10.0] * 30)) == "range"
    assert classify_sector_trend(_frame([10.0] * 10)) == "unknown"


def test_sector_alignment_keeps_structure_flow_and_breadth_separate():
    aligned, label = score_sector_alignment(
        "up", "up", sector_type="industry", main_net_pct=1.0, breadth_up_pct=60,
    )
    conflicting, conflict_label = score_sector_alignment(
        "up", "down", sector_type="concept", main_net_pct=-1.0, breadth_up_pct=30,
    )
    assert aligned > 0.35
    assert label == "aligned"
    assert conflicting < 0
    assert conflict_label == "conflicting"

    range_score, range_label = score_sector_alignment(
        "range", "down", sector_type="industry", main_net_pct=2.0, breadth_up_pct=90,
    )
    assert range_score > 0
    assert range_label == "mixed"


def test_stock_sector_context_prioritizes_industry_and_discloses_short_history(monkeypatch):
    import stock_analysis_mcp.strategies.sector_context as module

    memberships = [
        {"sector_code": "BK_C", "sector_name": "concept", "sector_type": "concept",
         "kline_bars": 300, "member_count": 20, "main_net_pct": 1.0},
        {"sector_code": "BK_I", "sector_name": "industry", "sector_type": "industry",
         "kline_bars": 30, "member_count": 10, "main_net_pct": 1.0},
    ]
    monkeypatch.setattr(module, "get_sectors_by_stock", lambda _: memberships)

    def klines(code, limit):
        count = 30 if code == "BK_I" else 300
        return [
            {"trade_date": f"2024-01-{(i % 28) + 1:02d}", "open": i + 1,
             "high": i + 2, "low": i + 0.5, "close": i + 1.5, "volume": 10}
            for i in range(count)
        ]

    monkeypatch.setattr(module, "get_sector_kline_local", klines)
    monkeypatch.setattr(module, "get_sector_members_local", lambda _: [
        {"change_pct": 1.0}, {"change_pct": -0.5}, {"change_pct": 0.2},
    ])
    result = build_stock_sector_context("600000", stock_trend="up", max_sectors=1)
    assert result["sectors"][0]["sector_code"] == "BK_I"
    assert result["sectors"][0]["data_status"] == "short_history"
    assert result["coverage_warning"] is not None
