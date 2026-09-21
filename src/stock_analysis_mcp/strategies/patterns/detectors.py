"""
patterns/detectors.py — 形态检测器 (抽象基类 + 5 个实现 + 注册表)

每个检测器封装一类形态的完整判定逻辑 (gate 硬性前提 + score 评分制),
检测逻辑与原单函数版本逐行一致, 仅重组为类方法。

state: detect 主循环传入的共享可变状态 (used_keys 集合, 防止同一结构重复触发)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from .context import (
    _Ctx,
    _valid,
    fib_levels_from_swings,
    score_range,
    trend_context,
    wave_phase,
)
from .signal import _base_signal


class PatternDetector(ABC):
    """形态检测器基类: 子类实现 detect(), 引擎按 pattern_name 注册分发。"""

    pattern_name: str

    @abstractmethod
    def detect(self, ctx: _Ctx, i: int, symbol: str, name: str,
               tolerance: float, state: dict) -> dict | None:
        """在 K线下标 i 检测形态, 命中返回信号 dict, 否则 None。"""


class TrendPullbackDetector(PatternDetector):
    """形态 1: 趋势回调企稳 (trend_pullback) — 评分制

    gate(硬性逻辑前提): 均线多头 + 120日涨幅>=15% + 回撤[2%,20%] + 峰距[2,35]日
                        + 回调低点距关键点位<=4% + 信号日企稳动作
    score: 回撤深度0.30 + 时长0.20 + 点位贴近度0.35 + 趋势强度0.15
    """

    pattern_name = "trend_pullback"

    def detect(self, ctx: _Ctx, i: int, symbol: str, name: str,
               tolerance: float, state: dict) -> dict | None:
        if not ctx.cand["rebound"][i]:
            return None
        if not (ctx.MA20[i] > ctx.MA60[i] and ctx.close[i] > ctx.MA60[i]):
            return None
        # 前置: 必须处于上涨趋势 (250日显著高低点结构, 详见 trend_context)
        tc = trend_context(ctx, i)
        if tc["trend"] != "up":
            return None
        sh, sl = tc["swing_high"], tc["swing_low"]
        if sh is None or sl is None:
            return None
        trend_gain = sh.price / sl.price - 1.0
        lo120 = max(0, i - 120)
        seg120 = ctx.close[lo120:i + 1]
        if len(seg120) < 121 or seg120[-121] <= 0:
            return None
        if seg120.max() / seg120[-121] - 1.0 < 0.15:
            return None
        lo30 = i - 29 if i >= 29 else 0
        seg30 = ctx.close[lo30:i + 1]
        peak_rel = int(np.argmax(seg30))
        peak_idx = lo30 + peak_rel
        dsp = i - peak_idx
        if not (2 <= dsp <= 35):
            return None
        peak_close = float(seg30[peak_rel])
        since = ctx.close[peak_idx:i + 1]
        min_close_since = float(since.min())
        low_since = ctx.low[peak_idx:i + 1]
        min_low_since = float(low_since.min())
        pullback_low_idx = peak_idx + int(np.argmin(low_since))
        drawdown = (peak_close - min_close_since) / peak_close
        if not (0.02 <= drawdown <= 0.20):
            return None
        # 关键点位: 均线 + 斐波那契 (本轮波段最高点→最低点) + 已确认前高
        levels: dict[str, float] = {}
        for w in ctx.ma_windows:
            v = ctx.ma(w, i)
            if _valid(v):
                levels[f"MA{w}"] = v
        levels.update(fib_levels_from_swings(tc, peak_close))
        for p in reversed(ctx.zz):
            if p.typ == "H" and p.idx < peak_idx - 5:
                levels["prev_high"] = p.price
                break
        main_name, main_lv, main_dist = None, None, None
        for lv_name, lv in levels.items():
            if lv <= 0 or np.isnan(lv) or peak_close < lv * 0.99:
                continue
            if min_low_since > lv * 1.04:
                continue
            dist = abs(min_low_since - lv) / lv
            if dist > 0.04:
                continue
            if main_lv is None or lv > main_lv:
                main_name, main_lv, main_dist = lv_name, lv, dist
        if main_name is None:
            return None
        # 分档: strong_hold / fake_break(假跌破<=3日收回) / near_level(近似形态) / soft
        closes_since = ctx.close[peak_idx:i + 1]
        broken = int((closes_since < main_lv * 0.999).sum())
        break_depth = max(0.0, (main_lv - min_close_since) / main_lv)
        if broken == 0 and main_dist <= tolerance:
            variant = "strong_hold"
        elif broken <= 3 and ctx.close[i] >= main_lv:
            variant = "fake_break"
        elif main_dist > tolerance:
            variant = "near_level"
        else:
            variant = "soft_pullback"
        hit_names = [n for n, lv in levels.items()
                     if lv > 0 and not np.isnan(lv)
                     and abs(min_low_since - lv) / lv <= tolerance
                     and peak_close >= lv * (1 + tolerance)]
        fib_hit = next((h for h in hit_names if h.startswith("fib_")), "")
        up_len = dsp
        up_seg = ctx.volume[max(0, peak_idx - up_len):peak_idx]
        pb_seg = ctx.volume[peak_idx:i + 1]
        vol_shrink = float(pb_seg.mean() / up_seg.mean()) if len(up_seg) and up_seg.mean() > 0 else np.nan
        s_dd = score_range(drawdown, 0.04, 0.13, 0.02, 0.20)
        s_dur = score_range(float(dsp), 4, 20, 2, 35)
        s_touch = 1.0 if main_dist <= tolerance else max(0.0, 1.0 - (main_dist - tolerance) / (0.04 - tolerance))
        s_trend = score_range(trend_gain, 0.30, 2.0, 0.15, 5.0)
        score = 0.30 * s_dd + 0.20 * s_dur + 0.35 * s_touch + 0.15 * s_trend
        high120 = float(seg120.max())
        return _base_signal(
            ctx, i, symbol, name, "trend_pullback", variant,
            hit_levels=",".join(hit_names) or main_name, fib_level=fib_hit,
            resonance=max(1, len(hit_names)), wave_phase=wave_phase(ctx, i),
            break_days=broken, break_depth=round(break_depth, 4),
            pullback_vol_shrink=vol_shrink,
            potential_gain=high120 / ctx.close[i] - 1.0,
            swing_start_date=ctx.dates[sl.idx], swing_start_price=round(float(sl.price), 3),
            swing_peak_date=ctx.dates[peak_idx], swing_peak_price=round(peak_close, 3),
            pullback_low_date=ctx.dates[pullback_low_idx], pullback_low_price=round(min_low_since, 3),
            pullback_pct=round(drawdown, 4), key_level_name=main_name,
            key_level_value=round(float(main_lv), 3),
            score=round(score, 3), trend="up",
        )


class MaReboundDetector(PatternDetector):
    """形态 2: 下跌趋势中长均线企稳反弹 (ma_rebound) — 评分制

    gate: 近60日回撤>=10% + 弱势(MA60下方或MA60向下) + 触及均线±5% + 收盘守住-7%
          + 不再创新低 + 收敛或放量 + 信号日反弹动作
    score: 下跌深度0.25 + 触及贴近0.30 + 守住度0.30 + 震荡收敛0.15
    """

    pattern_name = "ma_rebound"

    def detect(self, ctx: _Ctx, i: int, symbol: str, name: str,
               tolerance: float, state: dict) -> dict | None:
        if not ctx.cand["rebound"][i]:
            return None
        lo60 = i - 59 if i >= 59 else 0
        seg60 = ctx.close[lo60:i + 1]
        max_close60 = float(seg60.max())
        if max_close60 <= 0:
            return None
        dd60 = (max_close60 - ctx.close[i]) / max_close60
        if dd60 < 0.10:
            return None
        ma60_down = i >= 10 and ctx.MA60[i] < ctx.MA60[i - 10]
        if not (ctx.close[i] < ctx.MA60[i] or ma60_down):
            return None
        best = None
        for w in (60, 120, 250):
            ma = ctx.ma(w, i)
            if not _valid(ma) or ma <= 0:
                continue
            lo15 = i - 14 if i >= 14 else 0
            lows15 = ctx.low[lo15:i + 1]
            closes15 = ctx.close[lo15:i + 1]
            touch = float(lows15.min()) / ma - 1.0        # 触及深度(负=跌破)
            if touch > 0.05:                              # 未进入均线±5%区域
                continue
            hold = float(closes15.min()) / ma - 1.0       # 收盘守住度
            if hold < -0.07:                              # 收盘深度破位超过7%
                continue
            lo10 = i - 9 if i >= 9 else 0
            closes10 = ctx.close[lo10:i + 1]
            low10 = float(closes10.min())
            prior_lows = ctx.close[lo60:i - 9] if i - 9 > lo60 else ctx.close[lo60:i + 1]
            no_new_low = low10 > float(prior_lows.min()) * 0.999
            converge = (float(closes10.max()) - low10) / low10
            vol_up = ctx.vol_ratio[i] >= 1.5
            if no_new_low and (converge <= 0.18 or vol_up):
                s_dd = score_range(dd60, 0.20, 0.70, 0.10, 1.00)
                s_touch = score_range(touch, -0.05, 0.0, -0.08, 0.05)
                s_hold = score_range(hold, 0.0, 0.20, -0.07, 0.30)
                s_conv = score_range(converge, 0.03, 0.10, 0.0, 0.18)
                score = 0.25 * s_dd + 0.30 * s_touch + 0.30 * s_hold + 0.15 * s_conv
                best = (w, ma, score)
                break
        if best is None:
            return None
        w, ma, score = best
        lo120 = i - 119 if i >= 119 else 0
        high120 = float(ctx.close[lo120:i + 1].max())
        return _base_signal(
            ctx, i, symbol, name, "ma_rebound", f"MA{w}_hold",
            hit_levels=f"MA{w}", resonance=1,
            wave_phase="downtrend_ma_support",
            potential_gain=high120 / ctx.close[i] - 1.0,
            key_level_name=f"MA{w}", key_level_value=round(float(ma), 3),
            pullback_pct=round(dd60, 4),
            score=round(score, 3), trend="down",
        )


class WBottomDetector(PatternDetector):
    """形态 3: W底右底 (w_bottom) — 评分制

    gate: L1-H-L2 结构 + 右底不破左底8% + 间隔[8,90]日 + 颈线高度>=5%
          + 左底前30日跌幅>=8%
    score: 两底贴近0.35 + 颈线高度0.30 + 间隔0.15 + 前期跌幅0.20
    """

    pattern_name = "w_bottom"

    def detect(self, ctx: _Ctx, i: int, symbol: str, name: str,
               tolerance: float, state: dict) -> dict | None:
        used_keys: set = state["used_keys"]
        zz = ctx.zz
        if len(zz) < 3:
            return None
        l1, h, l2 = zz[-3], zz[-2], zz[-1]
        if not (l1.typ == "L" and h.typ == "H" and l2.typ == "L"):
            return None
        gap = l2.idx - l1.idx
        if not (8 <= gap <= 90):
            return None
        l1p, l2p, hp = l1.price, l2.price, h.price
        if l1p <= 0 or hp <= 0:
            return None
        if l2p < l1p * 0.92:                     # 右底破左底8%以上: 不是W底
            return None
        bottom = min(l1p, l2p)
        neck = hp / bottom - 1.0
        if neck < 0.05:                          # 颈线太浅: 结构无意义(容忍下限)
            return None
        # 前置 (W底必须出现在下跌之后): 左底之前250日内的显著最高点, 左底距其跌幅>=20%
        lo250 = max(0, l1.idx - 250)
        pre_hs = [p for p in ctx.zz if p.typ == "H" and lo250 <= p.idx < l1.idx]
        if not pre_hs:
            return None
        pre_high = max(pre_hs, key=lambda p: p.price)
        pre_drop = (pre_high.price - l1p) / pre_high.price
        if pre_drop < 0.20:
            return None
        s_bottoms = score_range(abs(l2p - l1p) / l1p, 0.0, 0.03, 0.0, 0.08)
        if s_bottoms <= 0:
            return None        # 定义性条件: 两底差超容忍(8%)不是W底, 不允许其他项补偿
        s_neck = score_range(neck, 0.10, 0.80, 0.05, 1.50)
        s_gap = score_range(float(gap), 15, 50, 8, 90)
        s_pre = score_range(pre_drop, 0.30, 0.80, 0.20, 1.50)
        score = 0.35 * s_bottoms + 0.30 * s_neck + 0.15 * s_gap + 0.20 * s_pre
        # MACD 底背离: 右底价格不高于左底2% 但 DIF 抬高 (经典双底确认信号)
        macd_div = 0
        d1, d2 = ctx.DIF[l1.idx], ctx.DIF[l2.idx]
        if _valid(d1) and _valid(d2) and l2p <= l1p * 1.02 and d2 > d1:
            macd_div = 1
        # 信号 (b): 放量收盘突破颈线, 每个颈线一次
        key_b = ("w_neck", h.idx)
        if (key_b not in used_keys and i - h.idx <= 60
                and ctx.close[i] > hp and ctx.close[i - 1] <= hp
                and ctx.cand["yang_vol15"][i]):
            used_keys.add(key_b)
            return _base_signal(
                ctx, i, symbol, name, "w_bottom", "neckline_breakout",
                hit_levels="neckline", resonance=1,
                wave_phase="base_breakout",
                potential_gain=(hp + (hp - bottom)) / ctx.close[i] - 1.0,
                left_bottom_date=ctx.dates[l1.idx], left_bottom_price=round(float(l1p), 3),
                right_bottom_date=ctx.dates[l2.idx], right_bottom_price=round(float(l2p), 3),
                neckline_date=ctx.dates[h.idx], neckline_value=round(float(hp), 3),
                bottom_deviation_pct=round(abs(l2p / l1p - 1.0) * 100, 2),
                score=round(score, 3), trend="down", macd_div=macd_div,
            )
        # 信号 (a): 右底确认后反弹中、未到颈线 (博第二波到颈线)
        key_a = ("w_right", l2.idx)
        if (key_a not in used_keys and 0 < i - l2.idx <= 25
                and ctx.cand["rebound"][i]
                and ctx.close[i] >= ctx.close[l2.idx] * 1.02
                and ctx.close[i] <= hp * 0.97):
            used_keys.add(key_a)
            return _base_signal(
                ctx, i, symbol, name, "w_bottom", "right_bottom",
                hit_levels="second_bottom", resonance=1,
                wave_phase="base_rebound",
                potential_gain=hp / ctx.close[i] - 1.0,
                left_bottom_date=ctx.dates[l1.idx], left_bottom_price=round(float(l1p), 3),
                right_bottom_date=ctx.dates[l2.idx], right_bottom_price=round(float(l2p), 3),
                neckline_date=ctx.dates[h.idx], neckline_value=round(float(hp), 3),
                bottom_deviation_pct=round(abs(l2p / l1p - 1.0) * 100, 2),
                score=round(score, 3), trend="down", macd_div=macd_div,
            )
        return None


class MNecklineDetector(PatternDetector):
    """形态 4: M形颈线支撑 (m_neckline) — 评分制

    gate: H1-N-H2 结构 + 两高差<=8% + 间隔[8,90] + H1前涨幅>=12%
          + 回调触及颈线8%内 + 收盘不破颈线2%以下
    score: 两高贴近0.35 + 前期涨幅0.20 + 间隔0.15 + 颈线守住度0.30
    """

    pattern_name = "m_neckline"

    def detect(self, ctx: _Ctx, i: int, symbol: str, name: str,
               tolerance: float, state: dict) -> dict | None:
        used_keys: set = state["used_keys"]
        if not ctx.cand["rebound"][i]:
            return None
        zz = ctx.zz
        if len(zz) < 3:
            return None
        h1, n, h2 = zz[-3], zz[-2], zz[-1]
        if not (h1.typ == "H" and n.typ == "L" and h2.typ == "H"):
            return None
        gap = h2.idx - h1.idx
        if not (8 <= gap <= 90):
            return None
        h1p, h2p, np_ = h1.price, h2.price, n.price
        two_high = abs(h2p - h1p) / h1p
        if two_high > 0.08 or np_ >= min(h1p, h2p):
            return None
        # 前置 (M顶必须出现在上涨之后): H1之前250日内的显著最低点, H1距其涨幅>=25%
        lo250 = max(0, h1.idx - 250)
        pre_ls = [p for p in ctx.zz if p.typ == "L" and lo250 <= p.idx < h1.idx]
        if not pre_ls:
            return None
        pre_low = min(pre_ls, key=lambda p: p.price)
        if pre_low.price <= 0:
            return None
        pre_rise = (h1p - pre_low.price) / pre_low.price
        if pre_rise < 0.25:
            return None
        if i - h2.idx > 25:
            return None
        lo15 = i - 14 if i >= 14 else 0
        if float(ctx.low[lo15:i + 1].min()) > np_ * 1.08:   # 未回调到颈线附近
            return None
        hold = float(ctx.close[lo15:i + 1].min()) / np_ - 1.0
        if hold < -0.02:                                    # 收盘有效跌破颈线
            return None
        if ctx.close[i] <= np_:
            return None
        key = ("m_neck", h2.idx)
        if key in used_keys:
            return None
        used_keys.add(key)
        up_seg = ctx.volume[n.idx:h2.idx + 1]
        pb_seg = ctx.volume[h2.idx:i + 1]
        vol_shrink = float(pb_seg.mean() / up_seg.mean()) if len(up_seg) and up_seg.mean() > 0 else np.nan
        s_highs = score_range(two_high, 0.0, 0.03, 0.0, 0.08)
        if s_highs <= 0:
            return None        # 定义性条件: 两高差超容忍(8%)不是M顶, 不允许其他项补偿
        s_pre = score_range(pre_rise, 0.40, 2.00, 0.25, 4.00)
        s_gap = score_range(float(gap), 15, 50, 8, 90)
        s_hold = score_range(hold, 0.0, 0.15, -0.02, 0.30)
        score = 0.35 * s_highs + 0.20 * s_pre + 0.15 * s_gap + 0.30 * s_hold
        # MACD 顶背离警示: H2 价格≈H1 但 DIF 降低 (动能衰减, 第二波把握下降)
        macd_div = 0
        d1, d2 = ctx.DIF[h1.idx], ctx.DIF[h2.idx]
        if _valid(d1) and _valid(d2) and h2p >= h1p * 0.98 and d2 < d1:
            macd_div = -1
        return _base_signal(
            ctx, i, symbol, name, "m_neckline", "neckline_hold",
            hit_levels="neckline", resonance=1,
            wave_phase=wave_phase(ctx, i),
            pullback_vol_shrink=vol_shrink,
            potential_gain=max(h1p, h2p) / ctx.close[i] - 1.0,
            first_top_date=ctx.dates[h1.idx], first_top_price=round(float(h1p), 3),
            second_top_date=ctx.dates[h2.idx], second_top_price=round(float(h2p), 3),
            neckline_date=ctx.dates[n.idx], neckline_value=round(float(np_), 3),
            top_deviation_pct=round(two_high * 100, 2),
            score=round(score, 3), trend="up", macd_div=macd_div,
        )


class BoxBreakoutDetector(PatternDetector):
    """形态 5: 平台箱体放量突破 (box_breakout) — 评分制

    gate: 箱体宽度<=25% + 收盘有效突破(0.3%) + 量比>=1.5 + 阳线
    score: 箱体规整度0.40 + 突破量能0.35 + 突破幅度0.25
    """

    pattern_name = "box_breakout"

    def detect(self, ctx: _Ctx, i: int, symbol: str, name: str,
               tolerance: float, state: dict,
               box_window: int = 40) -> dict | None:
        if i < box_window + 5:
            return None
        if not ctx.cand["box"][i]:
            return None
        # 箱体上沿须同时突破近120日高点 ("看前面更多": 突破的级别要够)
        if i >= 120 and ctx.close[i] <= ctx.close[i - 120:i].max() * 0.999:
            return None
        box_high = float(ctx.close[i - box_window:i].max())
        box_low = float(ctx.close[i - box_window:i].min())
        if box_low <= 0:
            return None
        width = (box_high - box_low) / box_low
        if width > 0.25:
            return None
        breakout = ctx.close[i] / box_high - 1.0
        if breakout < 0.003:
            return None
        s_box = score_range(width, 0.05, 0.12, 0.02, 0.25)
        if s_box <= 0:
            return None        # 定义性条件: 宽度超容忍不是平台
        s_vol = score_range(ctx.vol_ratio[i], 2.0, 8.0, 1.5, 20.0)
        s_brk = score_range(breakout, 0.005, 0.05, 0.003, 0.099)
        score = 0.40 * s_box + 0.35 * s_vol + 0.25 * s_brk
        return _base_signal(
            ctx, i, symbol, name, "box_breakout", "box_breakout",
            hit_levels="box_high", resonance=1,
            wave_phase="box_breakout",
            potential_gain=(box_high + (box_high - box_low)) / ctx.close[i] - 1.0,
            box_start_date=ctx.dates[i - box_window], box_end_date=ctx.dates[i - 1],
            box_high=round(box_high, 3), box_low=round(box_low, 3),
            box_width_pct=round(width * 100, 2), breakout_pct=round(breakout * 100, 2),
            score=round(score, 3), trend="range",
        )


# 检测器注册表: pattern_name -> 实例 (engine 主循环据此分发, 消除 if/elif 链)
ALL_DETECTORS: tuple[PatternDetector, ...] = (
    TrendPullbackDetector(),
    MaReboundDetector(),
    WBottomDetector(),
    MNecklineDetector(),
    BoxBreakoutDetector(),
)

DETECTORS: dict[str, PatternDetector] = {d.pattern_name: d for d in ALL_DETECTORS}
