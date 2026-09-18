"""
patterns/api.py — 对外扫描接口 (供 MCP 工具调用)

scan_universe          全市场/指定标的形态扫描 (并行 + 过滤标注)
get_pattern_history    单标的历史形态信号
get_key_levels         单标的当前关键位 (MA/斐波那契/结构位 + 趋势判定)
"""

from __future__ import annotations

import sys

from ...core.parallel import run_parallel
from .constants import BACKTEST_START, MIN_BARS, PATTERN_STRICT_FILTERS
from .context import _Ctx, _valid, fib_levels_from_swings, trend_context
from .engine import detect_patterns, prepare_df
from .pivots import Pivot, build_pivot_events, update_zigzag
from .signal import _sig_clean, passes_filter
from .universe import (
    get_latest_trade_date,
    get_universe_list,
    resolve_universe_symbol,
)


def scan_universe(universe: str, date: str | None = None,
                  patterns: list[str] | None = None,
                  ma_windows: tuple[int, ...] = (20, 60, 120, 250),
                  tolerance: float = 0.015,
                  strict: bool = False, no_filter: bool = False,
                  workers: int = 8, symbols: list[str] | None = None,
                  sector_type: str | None = None,
                  min_score: float = 0.6,
                  progress: bool = True) -> list[dict]:
    """全市场 (或指定标的) 形态扫描, 返回带 filter_pass/strict_pass 的信号列表。

    universe: stocks|sectors; symbols 非空时只扫指定标的;
    sector_type: 仅板块宇宙生效 (concept/industry, 缺省=全部);
    date: 缺省=本地库最新交易日; 结果只保留指定日期的信号 (scan 语义)。
    """
    if date is None:
        date = get_latest_trade_date(universe)
    if date is None:
        raise RuntimeError(f"{universe} 本地库无K线数据, 请先执行数据初始化/重建")
    if symbols:
        items = []
        for q in symbols:
            try:
                items.append(resolve_universe_symbol(universe, q))
            except ValueError:
                continue
    else:
        lst = get_universe_list(universe, sector_type=sector_type)
        items = list(zip(lst["symbol"].tolist(), lst["name"].tolist()))

    all_sigs: list[dict] = []

    def _scan_one(item: tuple) -> list[dict]:
        sym, nm = item
        try:
            df = prepare_df(universe, sym, end=date, tail=420)
            if len(df) < MIN_BARS:
                return []
            sigs = detect_patterns(df, sym, nm, patterns, ma_windows,
                                   tolerance, min_score=min_score)
            return [s for s in sigs if s["date"] == date]
        except Exception as e:  # 单标的失败不影响整体扫描
            if progress:
                print(f"  [warn] {universe} {sym} {nm}: {e}", file=sys.stderr, flush=True)
            return []

    def _on_progress(done: int, total: int) -> None:
        if progress and done % 500 == 0:
            print(f"进度: {done}/{total} ({done / total:.0%}) "
                  f"信号={len(all_sigs)}", file=sys.stderr, flush=True)

    for _item, result in run_parallel(items, _scan_one, workers=workers,
                                      on_progress=_on_progress):
        all_sigs.extend(result)

    if not all_sigs:
        return []
    for s in all_sigs:
        s["filter_pass"] = passes_filter(s)
        s["strict_pass"] = passes_filter(s, PATTERN_STRICT_FILTERS)
    if strict:
        all_sigs = [s for s in all_sigs if s["strict_pass"]]
    elif not no_filter:
        all_sigs = [s for s in all_sigs if s["filter_pass"]]
    return [_sig_clean(s) for s in all_sigs]


def get_pattern_history(universe: str, symbol: str, start: str | None = None,
                        end: str | None = None, patterns: list[str] | None = None,
                        ma_windows: tuple[int, ...] = (20, 60, 120, 250),
                        tolerance: float = 0.015,
                        min_score: float = 0.6) -> list[dict]:
    """单标的 (股票/板块) 历史形态信号列表, 按日期升序。"""
    sym, name = resolve_universe_symbol(universe, symbol)
    df = prepare_df(universe, sym, start=start or BACKTEST_START, end=end)
    if df.empty:
        raise RuntimeError(f"{sym} {name} 无K线数据")
    sigs = detect_patterns(df, sym, name, patterns, ma_windows, tolerance,
                           min_score=min_score)
    sigs.sort(key=lambda s: s["date"])
    return [_sig_clean(s) for s in sigs]


def get_key_levels(universe: str, symbol: str,
                   ma_windows: tuple[int, ...] = (5, 10, 20, 30, 60, 120, 200, 250),
                   tolerance: float = 0.015) -> dict:
    """单标的当前关键位: MA体系 + 斐波那契 + 结构位 (前高/前低) + 趋势判定。"""
    sym, name = resolve_universe_symbol(universe, symbol)
    df = prepare_df(universe, sym)
    if len(df) < MIN_BARS:
        raise RuntimeError(f"{sym} {name} 数据不足 ({len(df)} < {MIN_BARS} 根K线)")
    i = len(df) - 1
    ctx = _Ctx(df, ())
    close = float(ctx.close[i])
    events = build_pivot_events(df)
    zz: list[Pivot] = []
    for p in events:
        if p.confirm <= i:
            update_zigzag(zz, p)
    ctx.zz = zz
    tc = trend_context(ctx, i)

    levels = []
    for w in ma_windows:
        v = ctx.ma(w, i)
        if _valid(v):
            levels.append({"type": f"MA{w}", "value": round(float(v), 3),
                           "distance_pct": round((v / close - 1) * 100, 2)})
    # 斐波那契 (本轮趋势波段最高点→最低点, 近30日峰覆盖)
    seg30 = ctx.close[i - 29:i + 1]
    for nm, lv in fib_levels_from_swings(tc, float(seg30.max())).items():
        label = f"回调位{nm[4:]}" if nm.startswith("fib") else f"反弹位{nm[5:]}"
        levels.append({"type": label, "value": round(float(lv), 3),
                       "distance_pct": round((lv / close - 1) * 100, 2)})
    # 结构位: 已确认 zigzag 的前高/前低
    hs = [p for p in zz if p.typ == "H"]
    ls = [p for p in zz if p.typ == "L"]
    if hs:
        levels.append({"type": f"前高({ctx.dates[hs[-1].idx]})",
                       "value": round(float(hs[-1].price), 3),
                       "distance_pct": round((hs[-1].price / close - 1) * 100, 2)})
    if ls:
        levels.append({"type": f"前低({ctx.dates[ls[-1].idx]})",
                       "value": round(float(ls[-1].price), 3),
                       "distance_pct": round((ls[-1].price / close - 1) * 100, 2)})
    levels.sort(key=lambda r: abs(r["distance_pct"]))

    # New structure/position evidence is additive.  Legacy flat levels remain
    # intact for existing callers while all consumers migrate to the shared
    # observation engine.
    from ...core.constants import STRUCTURE_ENGINE_VERSION
    from ..structure import analyze_market_structure, compact_market_structure, resample_ohlcv
    structure = compact_market_structure(
        analyze_market_structure(df), current_price=close,
    )
    higher_timeframes = {}
    for timeframe in ("weekly", "monthly"):
        bars = resample_ohlcv(df, timeframe)
        if bars.empty:
            continue
        higher_timeframes[timeframe] = compact_market_structure(
            analyze_market_structure(bars), current_price=float(bars.iloc[-1]["close"]),
        )
        higher_timeframes[timeframe]["bar_count"] = len(bars)
        higher_timeframes[timeframe]["as_of_date"] = str(
            bars.iloc[-1]["source_date"]
        )[:10]
        higher_timeframes[timeframe]["latest_bar_may_be_incomplete"] = bool(
            bars.iloc[-1]["date"] > bars.iloc[-1]["source_date"]
        )
    trend_cn = {"up": "上涨趋势", "down": "下跌趋势", "range": "震荡"}[tc["trend"]]
    return {
        "universe": universe,
        "symbol": sym,
        "name": name,
        "date": ctx.dates[i],
        "close": round(close, 3),
        "trend": tc["trend"],
        "trend_cn": trend_cn,
        "levels": levels,
        "resistance": [r for r in levels if r["distance_pct"] > 0][:6],
        "support": [r for r in levels if r["distance_pct"] <= 0][:6],
        "market_structure": structure,
        "higher_timeframe_structure": higher_timeframes,
        "structure_engine_version": STRUCTURE_ENGINE_VERSION,
        "wave_analysis": None,
    }
