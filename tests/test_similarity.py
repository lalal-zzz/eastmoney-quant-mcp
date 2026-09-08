import numpy as np

from eastmoney_quant_mcp.strategies.similarity import (
    _period_rows,
    compare_cross_timeframe_patterns,
)


def _rows(close, volume, start, freq):
    dates = np.arange(np.datetime64(start),
                      np.datetime64(start) + len(close) * np.timedelta64(1, freq),
                      np.timedelta64(1, freq))
    return [
        {
            "date": str(day)[:10],
            "open": float(price * 0.998),
            "high": float(price * 1.015),
            "low": float(price * 0.985),
            "close": float(price),
            "volume": float(vol),
        }
        for day, price, vol in zip(dates, close, volume)
    ]


def test_daily_shape_matches_compressed_weekly_shape():
    x = np.linspace(0, 1, 60)
    query_close = 100 * np.exp(0.18 * x + 0.06 * np.sin(4 * np.pi * x))
    query_volume = 1000 * (1.0 + 0.35 * np.cos(4 * np.pi * x))
    query = _rows(query_close, query_volume, "2025-01-01", "D")

    rng = np.random.default_rng(7)
    candidate_close = 80 * np.exp(np.cumsum(rng.normal(0, 0.025, 180)))
    candidate_volume = rng.lognormal(7, 0.4, 180)
    compressed_x = np.linspace(0, 1, 30)
    candidate_close[60:90] = 45 * np.exp(
        0.18 * compressed_x + 0.06 * np.sin(4 * np.pi * compressed_x))
    candidate_volume[60:90] = 600 * (1.0 + 0.35 * np.cos(4 * np.pi * compressed_x))
    weekly = _rows(candidate_close, candidate_volume, "2018-01-01", "W")

    result = compare_cross_timeframe_patterns(
        query, {"102": weekly}, query_bars=60,
        candidate_window_bars=[30], top_n=3, min_score=0.5)

    assert result["matches"]
    assert result["evaluated_windows"] == 131
    best = result["matches"][0]
    assert best["period"] == "102"
    assert best["bars"] == 30
    assert best["score"] > 0.9
    assert best["volume_compared"] is True
    assert {"5", "10", "20"} <= set(best["forward"])
    assert result["outcome_summary"]["20"]["samples"] >= 1
    assert "range_pct" in result["query"]["shape_metrics"]
    probabilities = result["outcome_probabilities"]["20"]["probability_pct"]
    total_probability = probabilities["up"] + probabilities["sideways"] + probabilities["down"]
    assert abs(total_probability - 100.0) < 0.02
    assert result["outcome_probabilities"]["20"]["threshold_pct"] == 2.0


def test_missing_volume_redistributes_weight():
    close = np.linspace(10, 15, 60)
    rows = _rows(close, np.zeros(60), "2020-01-01", "D")
    result = compare_cross_timeframe_patterns(
        rows[-20:], {"101": rows}, query_bars=20,
        candidate_window_bars=[20], top_n=1,
        cutoff_at_query_start=True)

    assert result["matches"]
    assert result["matches"][0]["volume_compared"] is False
    assert "volume_path" not in result["matches"][0]["score_breakdown"]


def test_latest_cross_symbol_results_keep_candidate_identity():
    x = np.linspace(0, 1, 30)
    query_close = 20 * np.exp(0.12 * x + 0.03 * np.sin(3 * np.pi * x))
    query = _rows(query_close, 1000 + 200 * np.sin(2 * np.pi * x),
                  "2025-01-01", "D")
    similar = _rows(query_close * 3, 5000 + 1000 * np.sin(2 * np.pi * x),
                    "2025-01-01", "D")
    unlike = _rows(query_close[::-1], np.linspace(500, 2000, 30),
                   "2025-01-01", "D")
    metadata = {
        "600001:102": {"symbol": "600001", "name": "相似股", "period": "102"},
        "600002:102": {"symbol": "600002", "name": "反向股", "period": "102"},
    }

    result = compare_cross_timeframe_patterns(
        query, {"600001:102": similar, "600002:102": unlike},
        query_bars=30, candidate_window_bars=[30], top_n=2,
        cutoff_at_query_start=False, candidate_metadata=metadata,
        candidate_latest_only=True, require_forward=False)

    assert result["matches"][0]["symbol"] == "600001"
    assert result["matches"][0]["name"] == "相似股"
    assert result["matches"][0]["period"] == "102"
    assert result["matches"][0]["forward"] == {}


def test_daily_rows_resample_to_weekly_ohlcv():
    close = np.arange(10.0, 20.0)
    daily = _rows(close, np.ones(10), "2024-01-01", "D")

    weekly = _period_rows(daily, "102", 10)
    all_daily = _period_rows(daily, "101", 0)

    assert len(weekly) == 2
    assert weekly[0]["open"] == daily[0]["open"]
    assert weekly[0]["close"] == daily[4]["close"]
    assert weekly[0]["high"] == max(row["high"] for row in daily[:5])
    assert weekly[0]["low"] == min(row["low"] for row in daily[:5])
    assert weekly[0]["volume"] == 5.0
    assert len(all_daily) == len(daily)


def test_default_candidate_window_equals_query_window():
    x = np.linspace(0, 1, 30)
    shape = 30 * np.exp(0.1 * x + 0.04 * np.sin(4 * np.pi * x))
    query = _rows(shape, np.linspace(1000, 1500, 30), "2025-01-01", "D")
    candidate = _rows(np.r_[shape[::-1], shape * 2],
                      np.r_[np.linspace(1500, 1000, 30), np.linspace(1000, 1500, 30)],
                      "2024-01-01", "D")

    result = compare_cross_timeframe_patterns(
        query, {"600001:101": candidate}, query_bars=30,
        cutoff_at_query_start=False, candidate_latest_only=True,
        require_forward=False, min_score=0)

    assert result["evaluated_windows"] == 1
    assert result["matches"][0]["bars"] == 30


def test_invalid_zero_price_rows_are_ignored():
    close = np.linspace(10, 15, 31)
    rows = _rows(close, np.ones(31), "2024-01-01", "D")
    rows[0]["low"] = 0

    cleaned = _period_rows(rows, "101", 0)

    assert len(cleaned) == 30
    assert all(row["low"] > 0 for row in cleaned)
