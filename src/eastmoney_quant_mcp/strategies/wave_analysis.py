"""Objective wave/Fibonacci analysis built on confirmed zigzag pivots.

This module intentionally does not try to "count Elliott waves" as facts. It
scores whether the latest confirmed pivot sequence resembles a common impulse
or correction structure, then reports the Fibonacci zones where prior pullbacks
or rebounds actually turned.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from statistics import mean

import numpy as np
import pandas as pd

from .patterns import (
    BACKTEST_START,
    Pivot,
    build_pivot_events,
    load_pattern_df,
    resolve_universe_symbol,
    update_zigzag,
)

FIB_RETRACEMENTS = (0.236, 0.382, 0.5, 0.618, 0.786)
FIB_EXTENSIONS = (1.0, 1.272, 1.618, 2.0, 2.618)


@dataclass(frozen=True)
class FibMatch:
    label: str
    ratio: float
    distance: float


def _date_at(dates: list[str], idx: int) -> str:
    if 0 <= idx < len(dates):
        return str(dates[idx])
    return ""


def _nearest(value: float, candidates: tuple[float, ...]) -> FibMatch:
    ratio = min(candidates, key=lambda r: abs(value - r))
    if ratio >= 1:
        label = f"{ratio:.3g}x"
    else:
        label = f"{ratio:.3f}".rstrip("0").rstrip(".")
    return FibMatch(label=label, ratio=ratio, distance=value - ratio)


def build_confirmed_zigzag(
    df: pd.DataFrame,
    pivot_left: int = 5,
    pivot_right: int = 5,
    swing_min: float = 0.03,
    as_of_idx: int | None = None,
) -> list[Pivot]:
    """Build a zigzag from pivots confirmed no later than ``as_of_idx``."""
    if df.empty:
        return []
    last_idx = len(df) - 1 if as_of_idx is None else min(as_of_idx, len(df) - 1)
    zz: list[Pivot] = []
    for p in build_pivot_events(df, pivot_left, pivot_right):
        if p.confirm <= last_idx:
            update_zigzag(zz, p, swing_min)
    return zz


def _leg_dict(a: Pivot, b: Pivot, dates: list[str]) -> dict:
    direction = "up" if b.price > a.price else "down"
    pct = (b.price / a.price - 1.0) * 100 if a.price else 0.0
    return {
        "start_date": _date_at(dates, a.idx),
        "end_date": _date_at(dates, b.idx),
        "start_idx": a.idx,
        "end_idx": b.idx,
        "from_type": a.typ,
        "to_type": b.typ,
        "direction": direction,
        "start_price": round(float(a.price), 3),
        "end_price": round(float(b.price), 3),
        "change_pct": round(float(pct), 2),
        "bars": int(b.idx - a.idx),
    }


def _wave_lengths(points: list[Pivot]) -> list[float]:
    return [abs(points[i + 1].price - points[i].price) for i in range(len(points) - 1)]


def _score_impulse(points: list[Pivot], dates: list[str]) -> dict:
    """Score the latest six pivots as an Elliott-like 5-wave impulse."""
    if len(points) < 6:
        return {
            "structure": "insufficient",
            "score": 0,
            "direction": "",
            "checks": ["少于6个已确认 pivot, 不足以评估5浪结构"],
            "anchors": [],
        }

    pts = points[-6:]
    typs = "".join(p.typ for p in pts)
    if typs == "LHLHLH":
        direction = "up"
    elif typs == "HLHLHL":
        direction = "down"
    else:
        return {
            "structure": "mixed",
            "score": 0,
            "direction": "",
            "checks": [f"最近6个 pivot 类型为 {typs}, 不是标准 L-H-L-H-L-H 或 H-L-H-L-H-L"],
            "anchors": [_point_dict(p, dates) for p in pts],
        }

    lengths = _wave_lengths(pts)
    checks: list[str] = []
    passed = 0
    total = 5

    if direction == "up":
        higher_highs = pts[3].price > pts[1].price and pts[5].price > pts[3].price
        higher_lows = pts[2].price > pts[0].price and pts[4].price > pts[2].price
        no_wave4_overlap = pts[4].price > pts[1].price
    else:
        higher_highs = pts[3].price < pts[1].price and pts[5].price < pts[3].price
        higher_lows = pts[2].price < pts[0].price and pts[4].price < pts[2].price
        no_wave4_overlap = pts[4].price < pts[1].price

    wave2 = lengths[1] / lengths[0] if lengths[0] else np.nan
    wave4 = lengths[3] / lengths[2] if lengths[2] else np.nan
    wave3_not_short = lengths[2] >= min(lengths[0], lengths[4])

    for ok, text in (
        (higher_highs, "推动方向的连续高/低点延续"),
        (higher_lows, "回撤点保持同方向抬高/降低"),
        (0.236 <= wave2 <= 0.786, f"2浪回撤 {wave2:.2f} 在常见 Fibonacci 区间"),
        (0.236 <= wave4 <= 0.618, f"4浪回撤 {wave4:.2f} 在常见浅回撤区间"),
        (wave3_not_short, "3浪不是1/3/5浪中最短的一段"),
    ):
        checks.append(("OK " if ok else "NO ") + text)
        passed += int(bool(ok))

    if not no_wave4_overlap:
        checks.append("WARN 4浪与1浪区域重叠, A股个股中可见但会降低标准5浪可信度")

    return {
        "structure": "impulse",
        "score": round(passed / total * 100),
        "direction": direction,
        "checks": checks,
        "wave2_retrace": _nearest(float(wave2), FIB_RETRACEMENTS).__dict__,
        "wave4_retrace": _nearest(float(wave4), FIB_RETRACEMENTS).__dict__,
        "anchors": [_point_dict(p, dates) for p in pts],
    }


def _score_correction(points: list[Pivot], dates: list[str]) -> dict:
    """Score the latest four pivots as an ABC correction."""
    if len(points) < 4:
        return {"structure": "insufficient", "score": 0, "direction": "", "checks": []}
    pts = points[-4:]
    typs = "".join(p.typ for p in pts)
    if typs not in ("HLHL", "LHLH"):
        return {
            "structure": "mixed",
            "score": 0,
            "direction": "",
            "checks": [f"最近4个 pivot 类型为 {typs}, 不像简单 ABC 修正"],
            "anchors": [_point_dict(p, dates) for p in pts],
        }

    direction = "down" if typs == "HLHL" else "up"
    lengths = _wave_lengths(pts)
    b_retrace = lengths[1] / lengths[0] if lengths[0] else np.nan
    c_vs_a = lengths[2] / lengths[0] if lengths[0] else np.nan
    checks = [
        ("OK " if 0.382 <= b_retrace <= 0.786 else "NO ")
        + f"B段反抽/回撤 {b_retrace:.2f} 是否在常见 0.382-0.786 区间",
        ("OK " if 0.618 <= c_vs_a <= 1.618 else "NO ")
        + f"C段相对A段 {c_vs_a:.2f} 是否在常见 0.618-1.618 区间",
    ]
    passed = sum(1 for c in checks if c.startswith("OK"))
    return {
        "structure": "abc_correction",
        "score": round(passed / 2 * 100),
        "direction": direction,
        "checks": checks,
        "b_retrace": _nearest(float(b_retrace), FIB_RETRACEMENTS).__dict__,
        "c_extension": _nearest(float(c_vs_a), FIB_EXTENSIONS).__dict__,
        "anchors": [_point_dict(p, dates) for p in pts],
    }


def _point_dict(p: Pivot, dates: list[str]) -> dict:
    return {
        "date": _date_at(dates, p.idx),
        "idx": p.idx,
        "type": p.typ,
        "price": round(float(p.price), 3),
        "confirm_idx": p.confirm,
    }


def _fib_turns(legs: list[dict]) -> tuple[list[dict], dict]:
    turns: list[dict] = []
    buckets: dict[str, Counter] = {"up_pullback": Counter(), "down_rebound": Counter()}
    ratios: dict[str, list[float]] = {"up_pullback": [], "down_rebound": []}

    for prev, cur in zip(legs, legs[1:]):
        if prev["direction"] == cur["direction"]:
            continue
        prev_span = abs(prev["end_price"] - prev["start_price"])
        cur_span = abs(cur["end_price"] - cur["start_price"])
        if prev_span <= 0:
            continue
        ratio = cur_span / prev_span
        fib = _nearest(ratio, FIB_RETRACEMENTS)
        kind = "up_pullback" if prev["direction"] == "up" else "down_rebound"
        row = {
            "kind": kind,
            "from_date": cur["start_date"],
            "turn_date": cur["end_date"],
            "direction": cur["direction"],
            "ratio": round(float(ratio), 3),
            "nearest_fib": fib.label,
            "fib_distance": round(float(fib.distance), 3),
            "turn_price": cur["end_price"],
            "prior_leg_change_pct": prev["change_pct"],
            "leg_change_pct": cur["change_pct"],
        }
        turns.append(row)
        buckets[kind][fib.label] += 1
        ratios[kind].append(float(ratio))

    summary = {}
    for kind, counter in buckets.items():
        total = sum(counter.values())
        summary[kind] = {
            "total": total,
            "avg_ratio": round(mean(ratios[kind]), 3) if ratios[kind] else None,
            "distribution": dict(counter.most_common()),
            "most_common": counter.most_common(1)[0][0] if counter else "",
        }
    return turns, summary


def _active_leg(points: list[Pivot], dates: list[str], current_close: float) -> dict:
    if not points:
        return {}
    last = points[-1]
    direction = "up" if current_close >= last.price else "down"
    active = {
        "from_date": _date_at(dates, last.idx),
        "from_type": last.typ,
        "from_price": round(float(last.price), 3),
        "current_close": round(float(current_close), 3),
        "direction": direction,
        "change_pct": round((current_close / last.price - 1.0) * 100, 2) if last.price else 0.0,
        "status": "未确认结束",
        "end_rule": "需要出现反向 pivot 并经过右侧K线确认后, 这一段才算客观结束",
    }
    if len(points) >= 2:
        prev = points[-2]
        span = abs(last.price - prev.price)
        if span > 0:
            if last.typ == "L":
                targets = {f"retr_{int(r * 1000)}": last.price + span * r
                           for r in (0.382, 0.5, 0.618)}
                targets["prior_high"] = prev.price
            else:
                targets = {f"fib_{int(r * 1000)}": last.price - span * r
                           for r in FIB_RETRACEMENTS}
                targets["prior_low"] = prev.price
            active["reference_levels"] = {
                k: round(float(v), 3) for k, v in sorted(targets.items(), key=lambda item: item[1])
            }
    return active


def analyze_pivots(
    pivots: list[Pivot],
    dates: list[str],
    current_close: float | None = None,
    max_legs: int = 12,
) -> dict:
    """Analyze a confirmed pivot sequence and return JSON-serializable output."""
    points = sorted(pivots, key=lambda p: p.idx)
    legs = [_leg_dict(a, b, dates) for a, b in zip(points, points[1:])]
    turns, turn_summary = _fib_turns(legs)
    current = current_close if current_close is not None else (points[-1].price if points else np.nan)

    return {
        "pivot_count": len(points),
        "pivots": [_point_dict(p, dates) for p in points[-8:]],
        "recent_legs": legs[-max_legs:],
        "fib_turns": turns[-max_legs:],
        "fib_summary": turn_summary,
        "elliott_like_impulse": _score_impulse(points, dates),
        "abc_like_correction": _score_correction(points, dates),
        "active_leg": _active_leg(points, dates, float(current)) if points else {},
        "limitations": [
            "波浪划分是基于 pivot 参数的假设, 不是唯一答案",
            "最后一段在反向 pivot 确认前都可能延伸或重画",
            "Fibonacci 档位只说明历史转折贴近程度, 不能单独作为买卖依据",
        ],
    }


def analyze_wave(
    universe: str,
    symbol: str,
    start: str = BACKTEST_START,
    end: str | None = None,
    tail: int | None = 720,
    pivot_left: int = 5,
    pivot_right: int = 5,
    swing_min: float = 0.03,
) -> dict:
    """Load one symbol from the local database and analyze its wave structure."""
    sym, name = resolve_universe_symbol(universe, symbol)
    df = load_pattern_df(universe, sym, start=start, end=end, tail=tail)
    if df.empty:
        raise RuntimeError(f"{sym} {name} 无K线数据")
    dates = df["date"].astype(str).tolist()
    zz = build_confirmed_zigzag(df, pivot_left, pivot_right, swing_min)
    report = analyze_pivots(zz, dates, float(df["close"].iloc[-1]))
    report.update({
        "universe": universe,
        "symbol": sym,
        "name": name,
        "date": dates[-1],
        "close": round(float(df["close"].iloc[-1]), 3),
        "pivot_left": pivot_left,
        "pivot_right": pivot_right,
        "swing_min": swing_min,
    })
    return report
