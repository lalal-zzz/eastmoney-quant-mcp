"""
patterns/context.py — 单标的检测上下文与关键点位引擎

_Ctx           numpy 数组化的单标的上下文 (含截至 current i 的 zigzag)
score_range    形态标准度评分 (理想区间=1, 线性衰减到容忍边界=0)
wave_phase     客观波段阶段标记 (突破新高 / 首次回调 / 二次回调 / 后期回调)
trend_context  趋势上下文引擎 —— 一切形态判定的前置层 (up/down/range)
fib_levels_from_swings  斐波那契回调位/反弹位 (以波段最高点与最低点为锚)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import FIB_RATIOS
from .pivots import Pivot


class _Ctx:
    """单标的检测上下文: numpy 数组 + 截至 current i 的 zigzag。"""

    _COLUMNS = ("open", "high", "low", "close", "volume", "change_rate",
                "turnover", "MA5", "MA10", "MA20", "MA30", "MA60", "MA100",
                "MA120", "MA200", "MA250", "RSI14", "DIF", "VOL_MA5",
                "updown_ratio_20", "up_days_ratio_20", "turnover_ma20",
                "vol_ratio", "ma_bull", "dif_above_zero", "bias60",
                "macd_gold3", "dif_below0", "kdj_gold3", "J", "K", "D",
                "boll_pos", "boll_width", "rsi6")

    def __init__(self, df: pd.DataFrame, ma_windows: tuple[int, ...]):
        self.df = df
        self.n = len(df)
        self.dates = df["date"].tolist()
        for col in self._COLUMNS:
            self.__setattr__(col, df[col].to_numpy(dtype=float))
        self.cand = {
            "rebound": df["is_yang"].to_numpy() & df["above_ma5"].to_numpy()
                       & df["break_high5"].to_numpy(),
            "yang_vol15": df["is_yang"].to_numpy() & (df["vol_ratio"].to_numpy() >= 1.5),
            "box": df["is_yang"].to_numpy() & df["break_close40"].to_numpy()
                   & (df["vol_ratio"].to_numpy() >= 1.5),
        }
        self.ma_windows = ma_windows
        self.zz: list[Pivot] = []

    def ma(self, w: int, i: int) -> float:
        return getattr(self, f"MA{w}")[i]


# 支持的均线窗口集合 —— 由 _Ctx._COLUMNS 单一来源派生, 避免两处硬编码漂移
MA_WINDOW_WHITELIST = frozenset(
    int(c[2:]) for c in _Ctx._COLUMNS if c.startswith("MA") and c[2:].isdigit()
)


def _valid(x: float) -> bool:
    return x is not None and not np.isnan(x)


def score_range(value: float, ideal_lo: float, ideal_hi: float,
                tol_lo: float, tol_hi: float) -> float:
    """形态标准度评分: 值在 [ideal_lo, ideal_hi] 内=1.0, 线性衰减到容忍边界 [tol_lo, tol_hi]=0。

    真实形态是"类似的"而非精确落在固定阈值内 —— 评分制让边界外的近似形态
    也能被识别 (低分), 而不是被硬性拒绝。返回 0~1。
    """
    if np.isnan(value):
        return 0.0
    if ideal_lo <= value <= ideal_hi:
        return 1.0
    if value < ideal_lo:
        span = ideal_lo - tol_lo
        return max(0.0, 1.0 - (ideal_lo - value) / span) if span > 0 else 0.0
    span = tol_hi - ideal_hi
    return max(0.0, 1.0 - (value - ideal_hi) / span) if span > 0 else 0.0


def wave_phase(ctx: _Ctx, i: int, lookback: int = 250) -> str:
    """客观波段阶段标记 (非主观数浪): 突破新高 / 首次回调 / 二次回调 / 后期回调。"""
    lo = max(0, i - lookback)
    seg = ctx.close[lo:i + 1]
    if len(seg) == 0:
        return ""
    if ctx.close[i] >= seg.max() * 0.995:
        return "breakout_new_high"
    nh = sum(1 for p in ctx.zz if p.typ == "H" and p.idx >= lo)
    return {1: "first_pullback", 2: "second_pullback"}.get(nh, "later_pullback")


def trend_context(ctx: _Ctx, i: int, lookback: int = 250,
                  min_span: float = 0.20) -> dict:
    """趋势上下文引擎 —— 一切形态判定的前置层。

    基于近 lookback 日的已确认 zigzag 波段:
      swing_high / swing_low  显著最高点与最低点 (斐波那契的锚点)
      结构: HH+HL (高点低点都抬高) = 上升结构; LH+LL = 下降结构
    判定:
      up   = 低点在前高点在后, 波段涨幅>=min_span, 且(站上MA120 或 HH/HL结构)
      down = 高点在前低点在后, 波段跌幅>=min_span, 且(跌破MA120 或 LH/LL结构)
      其余 = range 震荡
    """
    lo = i - lookback
    recent: list[Pivot] = []
    for p in reversed(ctx.zz):
        if p.idx < lo:
            break
        recent.append(p)
    recent.reverse()
    hs = [p for p in recent if p.typ == "H"]
    lls = [p for p in recent if p.typ == "L"]
    swing_high = max(hs, key=lambda p: p.price) if hs else None
    swing_low = min(lls, key=lambda p: p.price) if lls else None

    hh_hl = (len(hs) >= 2 and hs[-1].price > hs[-2].price
             and len(lls) >= 2 and lls[-1].price > lls[-2].price)
    lh_ll = (len(hs) >= 2 and hs[-1].price < hs[-2].price
             and len(lls) >= 2 and lls[-1].price < lls[-2].price)

    trend = "range"
    if swing_high is not None and swing_low is not None:
        span = swing_high.price / swing_low.price - 1.0
        if span >= min_span:
            ma120 = ctx.MA120[i]
            ma_ok_up = (not _valid(ma120)) or ctx.close[i] > ma120
            ma_ok_dn = (not _valid(ma120)) or ctx.close[i] < ma120
            if swing_low.idx < swing_high.idx and ma_ok_up and (hh_hl or span >= 0.30):
                trend = "up"
            elif swing_high.idx < swing_low.idx and ma_ok_dn and (lh_ll or span >= 0.30):
                trend = "down"
    return {"trend": trend, "swing_high": swing_high, "swing_low": swing_low,
            "hh_hl": hh_hl, "lh_ll": lh_ll}


def fib_levels_from_swings(tc: dict, peak_close: float | None = None) -> dict[str, float]:
    """斐波那契回调位 —— 以本轮趋势波段的最高点与最低点为锚。

    低点在前、高点在后 (上涨波段) → 从高点回撤的支撑位 0.382/0.5/0.618/0.786;
    高点在前、低点在后 (下跌波段) → 从低点反弹的压力位 0.382/0.5/0.618。
    peak_close: 若当前峰尚未确认为 pivot, 用它覆盖波段高点 (取更高者)。
    """
    sh, sl = tc.get("swing_high"), tc.get("swing_low")
    if sh is None or sl is None or sh.price <= 0 or sl.price <= 0:
        return {}
    if sl.idx < sh.idx:                          # 上涨波段 → 回调支撑位
        high = max(sh.price, peak_close) if peak_close else sh.price
        span = high - sl.price
        return {f"fib_{int(r * 1000)}": high - span * r for r in FIB_RATIOS}
    high, low = sh.price, sl.price               # 下跌波段 → 反弹压力位
    span = high - low
    return {f"retr_{int(r * 1000)}": low + span * r for r in (0.382, 0.5, 0.618)}
