"""新功能存储层单元测试: 5 张新表 DDL / 写入 / 合并构建 (全部离线, tmp 库)"""

import sqlite3

import pytest

from eastmoney_quant_mcp.data import storage


@pytest.fixture
def dbs(tmp_path, monkeypatch):
    """把股票/板块库指向 tmp 路径并建表"""
    monkeypatch.setattr(storage, "STOCK_DB", str(tmp_path / "stock.db"))
    monkeypatch.setattr(storage, "SECTOR_DB", str(tmp_path / "sector.db"))
    storage.init_all()
    return storage


def _tables(conn) -> set:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {r[0] for r in rows}


def test_new_tables_created(dbs):
    with sqlite3.connect(dbs.STOCK_DB) as conn:
        tables = _tables(conn)
    for t in ("daily_stock_info", "stock_popularity_rank",
              "stock_daily_combined", "rebuild_progress"):
        assert t in tables
    with sqlite3.connect(dbs.SECTOR_DB) as conn:
        assert "sector_indicators" in _tables(conn)


def test_save_daily_stock_info(dbs):
    rows = [
        {"symbol": "000001", "name": "平安银行", "latest_price": 10.5,
         "change_pct": 1.2, "pe_ttm": 5.1, "main_net_inflow": 123.0,
         "sector_name": "银行"},
        {"symbol": "600000", "name": "浦发银行", "latest_price": 8.0,
         "change_pct": -0.5},
    ]
    n = dbs.save_daily_stock_info("2026-08-14", "2026-08-14 16:10:00", rows)
    assert n == 2
    got = dbs.query_stock_db(
        "SELECT trade_date, symbol, pe_ttm, sector_name FROM daily_stock_info "
        "WHERE trade_date='2026-08-14' ORDER BY symbol")
    assert got[0]["symbol"] == "000001"
    assert got[0]["pe_ttm"] == 5.1
    assert got[1]["pe_ttm"] is None          # 缺列补 NULL


def test_save_popularity_rank_guba_ignore_then_xuangu_replace(dbs):
    # guba 年文件回填 (INSERT OR IGNORE): 首写生效
    dbs.save_popularity_rank([
        {"trade_date": "2026-08-14", "symbol": "000001", "rank": 100, "source": "guba"},
    ], replace=False)
    # 同日期再写 guba (重复): 不覆盖
    dbs.save_popularity_rank([
        {"trade_date": "2026-08-14", "symbol": "000001", "rank": 999, "source": "guba"},
    ], replace=False)
    rows = dbs.query_stock_db(
        "SELECT rank, source FROM stock_popularity_rank "
        "WHERE trade_date='2026-08-14' AND symbol='000001'")
    assert rows[0]["rank"] == 100
    assert rows[0]["source"] == "guba"
    # xuangu 快照 (ON CONFLICT DO UPDATE): 覆盖当日权威值
    dbs.save_popularity_rank([
        {"trade_date": "2026-08-14", "symbol": "000001", "rank": 50,
         "hot_rank_score": 99.5, "source": "xuangu"},
    ], replace=True)
    rows = dbs.query_stock_db(
        "SELECT rank, hot_rank_score, source FROM stock_popularity_rank "
        "WHERE trade_date='2026-08-14' AND symbol='000001'")
    assert rows[0]["rank"] == 50
    assert rows[0]["hot_rank_score"] == 99.5
    assert rows[0]["source"] == "xuangu"


def test_build_combined_pipeline(dbs):
    dbs.save_stock_basic([{"symbol": "000001", "name": "平安银行", "raw_symbol": "sz000001"}])
    dbs.save_stock_kline([{
        "symbol": "000001", "date": "2026-08-14", "open": 10.0, "high": 10.6,
        "low": 9.9, "close": 10.5, "volume": 1e6, "amount": 1e7,
        "amplitude": 6.0, "change_pct": 2.0, "change_amount": 0.2,
        "turnover_rate": 1.5,
    }])
    dbs.save_popularity_rank([
        {"trade_date": "2026-08-14", "symbol": "000001", "rank": 42, "source": "guba"},
    ], replace=False)
    dbs.save_daily_stock_info("2026-08-14", "2026-08-14 16:10:00", [{
        "symbol": "000001", "name": "平安银行", "latest_price": 10.5,
        "main_net_inflow": 999.0,
    }])

    n_hist = dbs.build_combined_from_history()      # K线 JOIN 排名
    assert n_hist == 1
    n_spot = dbs.upsert_combined_spot()             # spot 列并入
    assert n_spot == 1
    n_rank = dbs.upsert_combined_rank("2026-08-14")  # 排名列并入
    assert n_rank == 1

    rows = dbs.query_stock_db(
        "SELECT * FROM stock_daily_combined WHERE trade_date='2026-08-14' AND symbol='000001'")
    assert len(rows) == 1
    r = rows[0]
    assert r["close"] == 10.5
    assert r["change_pct"] == 2.0
    assert r["popularity_rank"] == 42
    assert r["rank_source"] == "guba"
    assert r["main_net_inflow"] == 999.0
    assert r["name"] == "平安银行"


def test_rebuild_progress(dbs):
    dbs.record_rebuild_progress("kline", "000001", 1200)
    dbs.record_rebuild_progress("kline", "600000", 800)
    assert dbs.get_rebuild_done("kline") == {"000001", "600000"}
    assert dbs.get_rebuild_done("spot") == set()


def test_save_sector_indicators(dbs):
    rows = [{
        "sector_code": "BK1090", "trade_date": "2026-08-14",
        "MA5": 100.0, "MA20": 95.0, "RSI14": 55.0, "KDJ_J": 60.0,
        "DIF": 0.5, "DEA": 0.3, "VOL_MA5": 1e6,
    }]
    dbs.save_sector_indicators(rows)
    got = dbs.query_sector_db(
        "SELECT sector_code, MA5, KDJ_J FROM sector_indicators "
        "WHERE sector_code='BK1090' AND trade_date='2026-08-14'")
    assert got[0]["MA5"] == 100.0
    assert got[0]["KDJ_J"] == 60.0
