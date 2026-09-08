"""形态引擎单元测试 (全部离线): pivot/zigzag/因子列/关键位/板块字段映射/信号冒烟

合成K线用"平台段"设计: 每段价格恒定产生局部极值, 确定性构造 W底 / 均线反弹 / 箱体突破。
"""

import sqlite3

import numpy as np
import pandas as pd
import pytest

from eastmoney_quant_mcp.data import storage
from eastmoney_quant_mcp.data.indicators import compute_all_indicators
from eastmoney_quant_mcp.strategies import patterns


# ---------------------------------------------------------------------------
# 合成 K 线 (平台段: [(价格, 根数), ...]) — 段内小阳线, 段间跳变产生极值
# ---------------------------------------------------------------------------


def _make_kline(segments: list, volume_boost_at: dict | None = None) -> pd.DataFrame:
    closes = []
    for price, n in segments:
        closes.extend([price] * n)
    closes = np.array(closes, dtype=float)
    n = len(closes)
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    open_ = closes - 0.05
    close = closes + 0.05
    high = np.maximum(open_, close) + 0.10
    low = np.minimum(open_, close) - 0.10
    volume = np.full(n, 1e6, dtype=float)
    for idx, mult in (volume_boost_at or {}).items():
        volume[idx] = 1e6 * mult
    df = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume,
        "turnover": 2.0,
        "change_rate": pd.Series(close).pct_change().fillna(0).to_numpy() * 100,
    })
    return df


def _seed_stock_lib(db_path: str, kline_df: pd.DataFrame, symbol: str = "600000",
                    name: str = "测试股份") -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executescript(storage.STOCK_DDL)
        conn.execute(
            "INSERT OR REPLACE INTO stock_basic(symbol, name, raw_symbol) VALUES(?,?,?)",
            (symbol, name, symbol))
        cols = ["open", "high", "low", "close", "volume", "turnover_rate", "change_pct"]
        conn.executemany(
            f"INSERT OR REPLACE INTO stock_kline (symbol, date, {','.join(cols)}) "
            f"VALUES (?,?,{','.join('?' * len(cols))})",
            [(symbol, r["date"], float(r["open"]), float(r["high"]), float(r["low"]),
              float(r["close"]), float(r["volume"]), float(r["turnover"]),
              float(r["change_rate"]))
             for r in kline_df.to_dict("records")])
        ind = compute_all_indicators(kline_df)
        ind = ind.rename(columns={"K": "KDJ_K", "D": "KDJ_D", "J": "KDJ_J"})
        icols = ["MA5", "MA10", "MA20", "MA30", "MA60", "MA100", "MA200",
                 "RSI6", "RSI14", "RSI24", "DIF", "DEA", "MACD",
                 "BOLL_UPPER", "BOLL_MIDDLE", "BOLL_LOWER",
                 "KDJ_K", "KDJ_D", "KDJ_J", "VOL_MA5", "VOL_MA10", "ATR14"]
        icols = [c for c in icols if c in ind.columns]
        conn.executemany(
            f"INSERT OR REPLACE INTO stock_indicators (symbol, date, {','.join(icols)}) "
            f"VALUES (?,?,{','.join('?' * len(icols))})",
            [(symbol, r["date"], *[r[c] for c in icols]) for r in ind.to_dict("records")])
        conn.commit()


@pytest.fixture
def stock_lib(tmp_path, monkeypatch):
    db = str(tmp_path / "stock.db")
    monkeypatch.setitem(storage._path_overrides, "STOCK_DB", db)
    monkeypatch.setitem(storage._path_overrides, "STOCK_DIR", str(tmp_path))
    _orig_universe_defs = patterns._universe_defs

    def _patched_defs():
        d = _orig_universe_defs()
        d["stocks"] = (db, "stock_kline", "stock_indicators", "stock_basic",
                       "date", "symbol")
        return d

    monkeypatch.setattr(patterns, "_universe_defs", _patched_defs)
    return db


# ---------------------------------------------------------------------------
# pivot / zigzag 纯函数
# ---------------------------------------------------------------------------


def test_build_pivot_events_confirm_no_future():
    df = _make_kline([(10, 12), (20, 12), (30, 12)])
    events = patterns.build_pivot_events(df, left=5, right=5)
    assert events
    for p in events:
        assert p.confirm == p.idx + 5          # 右确认, 杜绝未来函数
    confirms = [p.confirm for p in events]
    assert confirms == sorted(confirms)        # 排序按 confirm 递增
    highs = [p for p in events if p.typ == "H"]
    lows = [p for p in events if p.typ == "L"]
    # 平台 20/30 的局部高点 (high = base+0.15), 平台 10 的局部低点 (low = base-0.15)
    assert any(abs(p.price - 20.15) < 1e-9 for p in highs)
    assert any(abs(p.price - 30.15) < 1e-9 for p in highs)
    assert any(abs(p.price - 9.85) < 1e-9 for p in lows)


def test_update_zigzag_alternation_and_extremes():
    zz = []
    patterns.update_zigzag(zz, patterns.Pivot(10, "H", 50.0, 15))
    assert [p.typ for p in zz] == ["H"]
    patterns.update_zigzag(zz, patterns.Pivot(20, "H", 60.0, 25))   # 同类型更极端 -> 替换
    assert zz[-1].price == 60.0
    patterns.update_zigzag(zz, patterns.Pivot(30, "L", 59.0, 35))   # 幅度1.7% < 3% 拒绝
    assert len(zz) == 1
    patterns.update_zigzag(zz, patterns.Pivot(30, "L", 50.0, 35))   # 幅度16.7% -> 加入
    assert [p.typ for p in zz] == ["H", "L"]
    patterns.update_zigzag(zz, patterns.Pivot(40, "L", 45.0, 45))   # 同类型更极端 -> 替换
    assert zz[-1].price == 45.0
    patterns.update_zigzag(zz, patterns.Pivot(50, "H", 46.0, 55))   # 幅度2.2% < 3% 拒绝
    assert len(zz) == 2


# ---------------------------------------------------------------------------
# 因子列
# ---------------------------------------------------------------------------


def _factor_input_df(n: int = 320) -> pd.DataFrame:
    df = _make_kline([(50, n)])
    for w in (5, 10, 20, 30, 60, 100, 120, 200, 250):
        df[f"MA{w}"] = df["close"].rolling(w).mean()
    df["VOL_MA5"] = df["volume"].rolling(5).mean()
    df["RSI6"] = 55.0
    df["RSI14"] = 55.0
    df["DIF"] = 0.5
    df["DEA"] = 0.4
    df["K"] = 60.0
    df["D"] = 55.0
    df["J"] = 70.0
    df["BOLL_UPPER"] = 52.0
    df["BOLL_MIDDLE"] = 50.0
    df["BOLL_LOWER"] = 48.0
    return df


def test_add_factor_columns():
    df = _factor_input_df()
    out = patterns.add_factor_columns(df)
    for col in ("updown_ratio_20", "up_days_ratio_20", "turnover_ma20", "vol_ratio",
                "ma_bull", "dif_above_zero", "bias60", "macd_gold3", "dif_below0",
                "kdj_gold3", "boll_pos", "boll_width", "rsi6", "is_yang",
                "above_ma5", "break_high5", "break_high10", "break_close40"):
        assert col in out.columns, f"缺少因子列 {col}"
    # 平台小阳线: is_yang 全 True; bias60 = close/MA60 - 1
    assert out["is_yang"].all()
    close = out["close"].iloc[-1]
    assert abs(out["bias60"].iloc[-1] - (close / df["MA60"].iloc[-1] - 1.0)) < 1e-9


# ---------------------------------------------------------------------------
# 关键位: 斐波那契 / 趋势上下文 / 波段阶段
# ---------------------------------------------------------------------------


def test_fib_levels_from_swings_up_wave():
    sh = patterns.Pivot(100, "H", 50.0, 105)    # 高点在后
    sl = patterns.Pivot(50, "L", 40.0, 55)      # 低点在前
    fib = patterns.fib_levels_from_swings({"swing_high": sh, "swing_low": sl})
    assert fib["fib_382"] == pytest.approx(50 - 10 * 0.382)
    assert fib["fib_500"] == 45.0
    assert fib["fib_618"] == pytest.approx(50 - 10 * 0.618)
    assert fib["fib_786"] == pytest.approx(50 - 10 * 0.786)


def test_fib_levels_from_swings_down_wave():
    sh = patterns.Pivot(50, "H", 50.0, 55)      # 高点在前
    sl = patterns.Pivot(100, "L", 40.0, 105)    # 低点在后
    fib = patterns.fib_levels_from_swings({"swing_high": sh, "swing_low": sl})
    assert fib["retr_382"] == pytest.approx(40 + 10 * 0.382)
    assert "fib_382" not in fib


def _ctx_for(df: pd.DataFrame) -> patterns._Ctx:
    return patterns._Ctx(patterns.add_factor_columns(df), ())


def test_trend_context_up_detection():
    df = _factor_input_df(n=300)
    df["close"] = np.where(np.arange(len(df)) == 299, 55.0, df["close"].to_numpy())
    ctx = _ctx_for(df)
    ctx.zz = [patterns.Pivot(100, "L", 40.0, 105),
              patterns.Pivot(200, "H", 60.0, 205)]
    tc = patterns.trend_context(ctx, 299)
    assert tc["trend"] == "up"
    assert tc["swing_high"].price == 60.0
    assert tc["swing_low"].price == 40.0


def test_wave_phase_markers():
    df = _factor_input_df(n=300)
    ctx = _ctx_for(df)
    # 突破新高: close 为 250 日窗口最大
    ctx.close = np.full(300, 50.0)
    ctx.close[299] = 60.0
    ctx.zz = [patterns.Pivot(100, "L", 40.0, 105),
              patterns.Pivot(250, "H", 55.0, 255)]
    assert patterns.wave_phase(ctx, 299) == "breakout_new_high"
    # 首次回调: 窗口内 1 个高点, close 已回落
    ctx.close = np.full(300, 50.0)
    ctx.close[299] = 49.0
    ctx.zz = [patterns.Pivot(150, "H", 60.0, 155)]
    assert patterns.wave_phase(ctx, 299) == "first_pullback"
    # 二次回调
    ctx.zz = [patterns.Pivot(100, "H", 60.0, 105),
              patterns.Pivot(180, "H", 65.0, 185)]
    assert patterns.wave_phase(ctx, 299) == "second_pullback"


# ---------------------------------------------------------------------------
# 板块字段映射 (sector_kline + sector_indicators -> 统一 df)
# ---------------------------------------------------------------------------


def test_sector_field_mapping(tmp_path, monkeypatch):
    db = str(tmp_path / "sector.db")
    with sqlite3.connect(db) as conn:
        conn.executescript(storage.SECTOR_DDL)
        conn.execute("INSERT INTO sector_basic(sector_code, sector_name, sector_type) "
                     "VALUES('BK1090','人工智能','concept')")
        conn.executemany(
            "INSERT INTO sector_kline(sector_code, trade_date, open, close, high, low, "
            "volume, turnover, change_pct, turnover_rate) VALUES(?,?,?,?,?,?,?,?,?,?)",
            [("BK1090", f"2026-08-{d:02d}", 100.0, 101.0, 102.0, 99.0, 1e6, 1e8,
              1.0, 2.0) for d in range(10, 18)])
        conn.executemany(
            "INSERT INTO sector_indicators(sector_code, trade_date, MA5, MA20, KDJ_K, "
            "KDJ_D, KDJ_J, DIF, DEA, VOL_MA5) VALUES(?,?,?,?,?,?,?,?,?,?)",
            [("BK1090", f"2026-08-{d:02d}", 100.0, 99.0, 55.0, 50.0, 65.0, 0.5, 0.3,
              1e6) for d in range(10, 18)])
        conn.commit()
    _orig_universe_defs = patterns._universe_defs

    def _patched_defs():
        return {
            "stocks": _orig_universe_defs()["stocks"],
            "sectors": (db, "sector_kline", "sector_indicators", "sector_basic",
                        "trade_date", "sector_code"),
        }

    monkeypatch.setattr(patterns, "_universe_defs", _patched_defs)

    df = patterns.load_pattern_df("sectors", "BK1090")
    assert not df.empty
    assert df.iloc[0]["date"] == "2026-08-10"
    assert list(df.columns[:8]) == ["date", "open", "high", "low", "close",
                                    "volume", "change_rate", "turnover"]
    assert df["turnover"].iloc[0] == 2.0                      # turnover <- turnover_rate 列
    assert df["K"].iloc[0] == 55.0 and df["J"].iloc[0] == 65.0  # KDJ_K/J 映射
    assert df["MA120"].isna().all() and df["MA250"].isna().all()  # 历史短: 补算列存在但为 NaN

    lst = patterns.get_universe_list("sectors", sector_type="concept")
    assert lst["symbol"].tolist() == ["BK1090"]
    assert patterns.get_universe_list("sectors", sector_type="industry").empty
    # 裸代码/名称解析
    assert patterns.resolve_universe_symbol("sectors", "1090") == ("BK1090", "人工智能")
    assert patterns.resolve_universe_symbol("sectors", "人工智能") == ("BK1090", "人工智能")


# ---------------------------------------------------------------------------
# 形态信号冒烟: W底 / 均线反弹 / 箱体突破
# ---------------------------------------------------------------------------

# 段 idx: 0~14 铺垫平台80; 15~119 高位100 (H pivot idx=15, 落在 l1 前 250 日窗口内)
#         120~257 下跌至 40 (L1); 258~275 平台40 (L1 确认点)
#         276~295 颈线48 (H); 296~310 右底41.5 (L2); 311~318 反弹46 (信号日 313)
#         319~348 继续上涨
W_BOTTOM_SEGMENTS = [
    (80, 15),
    (100, 105),
    (92, 20), (84, 20), (76, 20), (68, 20), (60, 20), (52, 20), (44, 20),
    (40, 18),
    (48, 20),
    (41.5, 15),
    (46, 8),
    (55, 30),
]


def _detect_from_lib(stock_lib, segments, volume_boost_at=None):
    """合成K线 -> 写库 -> 按真实链路读回 (prepare_df=load+因子列) -> detect_patterns"""
    df = _make_kline(segments, volume_boost_at)
    _seed_stock_lib(stock_lib, df)
    full = patterns.prepare_df("stocks", "600000")
    assert not full.empty
    return full, patterns.detect_patterns(full, "600000", "测试股份")


def test_w_bottom_signal(stock_lib):
    full, sigs = _detect_from_lib(stock_lib, W_BOTTOM_SEGMENTS)
    assert len(full) >= patterns.MIN_BARS
    wb = [s for s in sigs if s["pattern"] == "w_bottom"]
    assert wb, f"期望 W底信号, 实际: {[s['pattern'] for s in sigs]}"
    s = wb[0]
    assert s["variant"] == "right_bottom"
    assert s["score"] >= 0.6
    assert s["date"] == full.iloc[313]["date"]
    for key in ("symbol", "name", "date", "pattern", "pattern_cn", "variant",
                "close", "hit_levels", "fib_level", "resonance", "wave_phase",
                "score", "trend", "vol_ratio", "bias60"):
        assert key in s, f"信号缺少字段 {key}"
    assert s["hit_levels"] == "second_bottom"


def test_ma_rebound_signal(stock_lib):
    # 段 idx: 0~119 铺垫85; 120~204 高位104 (信号日 260 的 60 日窗口内, 回撤19%)
    #         205~249 回落85; 250~259 触底83 (不再创新低); 260~267 企稳84 (信号日 260)
    #         268~297 反弹88
    segments = [
        (85, 120),
        (104, 85),
        (85, 45),
        (83, 10),
        (84, 8),
        (88, 30),
    ]
    full, sigs = _detect_from_lib(stock_lib, segments)
    assert len(full) >= patterns.MIN_BARS
    mr = [s for s in sigs if s["pattern"] == "ma_rebound"]
    assert mr, f"期望均线反弹信号, 实际: {[s['pattern'] for s in sigs]}"
    assert mr[0]["variant"].startswith("MA")
    assert mr[0]["wave_phase"] == "downtrend_ma_support"
    assert mr[0]["trend"] == "down"


def test_box_breakout_signal(stock_lib):
    # 段 idx: 0~220 前高平台50 (覆盖近120日); 221~235 48; 236~245 52; 246~260 49
    #         突破日 i=260: 放量阳线站上箱体上沿
    segments = [
        (50, 221),
        (48, 15),
        (52, 10),
        (49, 15),
    ]
    df = _make_kline(segments, volume_boost_at={260: 3.0})
    assert len(df) == 261
    df.loc[260, "close"] = 54.0
    df.loc[260, "open"] = 53.0
    df.loc[260, "high"] = 54.2
    df.loc[260, "low"] = 52.8
    _seed_stock_lib(stock_lib, df)
    full = patterns.prepare_df("stocks", "600000")
    sigs = patterns.detect_patterns(full, "600000", "测试股份")
    bx = [s for s in sigs if s["pattern"] == "box_breakout"]
    assert bx, f"期望箱体突破信号, 实际: {[s['pattern'] for s in sigs]}"
    assert bx[0]["variant"] == "box_breakout"
    assert bx[0]["hit_levels"] == "box_high"
    assert bx[0]["trend"] == "range"


# ---------------------------------------------------------------------------
# 历史信号 / 关键位 / 扫描 (MCP 工具入口冒烟)
# ---------------------------------------------------------------------------


def test_get_pattern_history_smoke(stock_lib):
    _seed_stock_lib(stock_lib, _make_kline(W_BOTTOM_SEGMENTS))
    hist = patterns.get_pattern_history("stocks", "600000", patterns=["w_bottom"])
    assert isinstance(hist, list)
    if hist:
        assert hist[0]["date"] <= hist[-1]["date"]      # 升序
        assert all(s["pattern"] == "w_bottom" for s in hist)


def test_get_key_levels_smoke(stock_lib):
    _seed_stock_lib(stock_lib, _make_kline([(50, 320)]))
    k = patterns.get_key_levels("stocks", "600000")
    assert k["symbol"] == "600000"
    assert k["trend"] in ("up", "down", "range")
    assert k["levels"]
    for lv in k["levels"]:
        assert {"type", "value", "distance_pct"} <= set(lv.keys())


def test_scan_universe_specific_symbols(stock_lib):
    _seed_stock_lib(stock_lib, _make_kline(W_BOTTOM_SEGMENTS), symbol="000001",
                    name="平安测试")
    sigs = patterns.scan_universe("stocks", symbols=["000001"], workers=2,
                                  no_filter=True, progress=False)
    assert isinstance(sigs, list)
    assert all(s["symbol"] == "000001" for s in sigs)
