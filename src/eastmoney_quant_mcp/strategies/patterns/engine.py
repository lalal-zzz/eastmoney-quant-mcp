"""
patterns/engine.py — 形态检测主循环 (注册表分发) 与 DataFrame 准备
"""

import pandas as pd

from .constants import MIN_BARS, PATTERN_COOLDOWN, PATTERN_NAMES
from .context import MA_WINDOW_WHITELIST, _Ctx, _valid
from .detectors import DETECTORS
from .factors import add_factor_columns
from .pivots import build_pivot_events, update_zigzag
from .universe import load_pattern_df


def detect_patterns(df: pd.DataFrame, symbol: str, name: str = "",
                    patterns: list[str] | None = None,
                    ma_windows: tuple[int, ...] = (20, 60, 120, 250),
                    tolerance: float = 0.015,
                    pivot_left: int = 5, pivot_right: int = 5,
                    swing_min: float = 0.03,
                    min_score: float = 0.6) -> list[dict]:
    """对单标的 DataFrame (load_pattern_df + add_factor_columns 后) 检测全部形态信号。

    股票/板块通用; 历史不足 MIN_BARS 的标的自动跳过 (历史短的板块自然过滤)。
    min_score: 形态标准度阈值 (0~1)。评分制下"类似形态" (参数偏离理想区间但在
    容忍范围内) 也会被识别, 只是 score 较低; score 低于 min_score 的丢弃。
    """
    if len(df) < MIN_BARS:
        return []
    if patterns is None:
        patterns = list(PATTERN_NAMES.keys())
    unknown = [p for p in patterns if p not in DETECTORS]
    if unknown:
        raise ValueError(f"unknown patterns: {unknown}")
    events = build_pivot_events(df, pivot_left, pivot_right)
    ctx = _Ctx(df, tuple(w for w in ma_windows if w in MA_WINDOW_WHITELIST))
    signals: list[dict] = []
    cooldown: dict[str, int] = {}
    state = {"used_keys": set()}
    ei = 0
    ne = len(events)

    for i in range(MIN_BARS, ctx.n):
        while ei < ne and events[ei].confirm <= i:
            update_zigzag(ctx.zz, events[ei], swing_min)
            ei += 1
        # 通用排除: 停牌 / 低价股 / 一字涨停无法买入 / 关键数据缺失
        if ctx.volume[i] <= 0 or ctx.close[i] < 1.5:
            continue
        if not (_valid(ctx.open[i]) and _valid(ctx.close[i])
                and _valid(ctx.MA5[i]) and _valid(ctx.VOL_MA5[i])):
            continue
        if ctx.high[i] == ctx.low[i] and ctx.change_rate[i] >= 9.5:
            continue
        for pat in patterns:
            last_i = cooldown.get(pat, -10**9)
            if i - last_i < PATTERN_COOLDOWN[pat]:
                continue
            sig = DETECTORS[pat].detect(ctx, i, symbol, name, tolerance, state)
            if sig is not None:
                if sig["score"] < min_score:
                    continue
                cooldown[pat] = i
                signals.append(sig)
    return signals


def prepare_df(universe: str, symbol: str, start: str = "2010-01-01",
               end: str | None = None, tail: int | None = None) -> pd.DataFrame:
    """load_pattern_df + add_factor_columns 一步到位 (股票/板块通用)。"""
    df = load_pattern_df(universe, symbol, start=start, end=end, tail=tail)
    if df.empty:
        return df
    return add_factor_columns(df)
