import sqlite3

import pandas as pd


def test_indicator_extension_has_research_factors():
    from stock_analysis_mcp.data.indicators import compute_all_indicators
    n = 300
    df = pd.DataFrame({
        "close": [10 + i * 0.01 for i in range(n)],
        "high": [10.1 + i * 0.01 for i in range(n)],
        "low": [9.9 + i * 0.01 for i in range(n)],
        "volume": [1000 + i for i in range(n)],
    })
    out = compute_all_indicators(df)
    for col in ("MA120", "MA250", "VOL_MA20", "VOL_RATIO20", "ATR_PCT",
                "BIAS250", "RETURN_60", "HIGH_120", "LOW_120"):
        assert col in out.columns
    assert pd.notna(out.iloc[-1]["MA250"])


def test_stock_schema_supports_adjustment_variants(tmp_path):
    from stock_analysis_mcp.data import storage
    stock = str(tmp_path / "stock.db")
    sector = str(tmp_path / "sector.db")
    storage.set_db_paths(stock, sector)
    storage._schema_ready.clear()
    try:
        storage.init_all()
        base = {"symbol": "000001", "date": "2026-01-01", "open": 10,
                "high": 11, "low": 9, "close": 10.5, "volume": 100}
        storage.save_stock_kline([{**base, "adjust_type": "qfq"},
                                  {**base, "adjust_type": "hfq", "close": 20.5}])
        rows = storage.query_stock_db(
            "SELECT adjust_type,close FROM stock_kline ORDER BY adjust_type")
        assert len(rows) == 2
        assert {r["adjust_type"] for r in rows} == {"qfq", "hfq"}
        tables = {r[0] for r in sqlite3.connect(stock).execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"data_coverage", "pattern_signals"} <= tables
    finally:
        storage.set_db_paths(None, None)
        storage._schema_ready.clear()


def test_v1_stock_schema_migrates_without_data_loss(tmp_path):
    from stock_analysis_mcp.data import storage
    stock = str(tmp_path / "legacy.db")
    sector = str(tmp_path / "sector.db")
    conn = sqlite3.connect(stock)
    conn.executescript("""
        CREATE TABLE stock_kline (
          symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
          volume REAL, amount REAL, amplitude REAL, change_pct REAL,
          change_amount REAL, turnover_rate REAL, PRIMARY KEY(symbol,date));
        CREATE TABLE stock_indicators (
          symbol TEXT, date TEXT, MA5 REAL, PRIMARY KEY(symbol,date));
        INSERT INTO stock_kline(symbol,date,close) VALUES('000001','2025-01-02',10.5);
        INSERT INTO stock_indicators(symbol,date,MA5) VALUES('000001','2025-01-02',10.0);
    """)
    conn.close()
    storage.set_db_paths(stock, sector)
    storage._schema_ready.clear()
    try:
        storage.init_all()
        row = storage.query_stock_db("SELECT symbol,date,adjust_type,source,close FROM stock_kline")[0]
        assert row == {"symbol": "000001", "date": "2025-01-02",
                       "adjust_type": "qfq", "source": "legacy", "close": 10.5}
        ind = storage.query_stock_db(
            "SELECT adjust_type,indicator_version,MA5 FROM stock_indicators")[0]
        assert ind["adjust_type"] == "qfq"
        assert ind["indicator_version"]
        assert ind["MA5"] == 10.0
        storage.save_stock_kline([{"symbol": "000001", "date": "2025-01-02",
                                   "adjust_type": "hfq", "close": 20.5}])
        from stock_analysis_mcp.data.search import get_stock_kline_local
        assert get_stock_kline_local("000001", 10, "qfq")[0]["close"] == 10.5
        assert get_stock_kline_local("000001", 10, "hfq")[0]["close"] == 20.5
    finally:
        storage.set_db_paths(None, None)
        storage._schema_ready.clear()


def test_http_get_text_injects_cookie(monkeypatch):
    from stock_analysis_mcp.data import network

    class Response:
        status_code = 200
        text = "ok"
        content = b"ok"

    seen = {}
    monkeypatch.setattr(network, "_load_cookies", lambda: "token=abc")
    monkeypatch.setattr(network.requests, "get",
                        lambda *args, **kwargs: seen.update(kwargs) or Response())
    assert network.http_get_text("https://example.invalid", retries=1) == "ok"
    assert seen["headers"]["Cookie"] == "token=abc"


def test_high_level_tools_registered():
    from stock_analysis_mcp.server import TOOL_HANDLERS
    assert {"sync_stock_kline_universe", "screen_rising_candidates",
            "prepare_stock_analysis", "find_cross_timeframe_similar_patterns",
            "backtest_pattern_strategy"} <= set(TOOL_HANDLERS)


def test_signal_stage_and_alias():
    from stock_analysis_mcp.tools.research import _enrich_signal
    signal = {"symbol": "000001", "date": "2026-01-01", "pattern": "m_neckline",
              "variant": "neckline_hold", "score": 0.8, "trend": "up",
              "vol_ratio": 1.2, "resonance": 2, "hit_levels": "neckline"}
    levels = {"trend": "up", "levels": [],
              "support": [{"value": 10.0}], "resistance": [{"value": 12.0}]}
    out = _enrich_signal(signal, levels, {"higher_score": 15}, 8)
    assert out["pattern"] == "neckline_reclaim"
    assert out["stage"] == "retesting"
    assert out["confirmed"] is True
    assert out["invalid_level"] == 10.0


def test_portfolio_backtest_respects_position_limit():
    from stock_analysis_mcp.strategies.trading_backtest import _portfolio_summary
    trades = [{"symbol": f"{i:06d}", "entry_date": "2025-01-02",
               "exit_date": "2025-01-20", "net_return": 0.01} for i in range(15)]
    result = _portfolio_summary(trades, max_positions=10)
    assert result["trades"] == 10
    assert result["total_return"] > 0
