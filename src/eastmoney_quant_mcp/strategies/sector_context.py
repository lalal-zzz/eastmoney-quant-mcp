from __future__ import annotations

import math
from statistics import median

import pandas as pd

from ..data.search import get_sector_kline_local, get_sector_members_local, get_sectors_by_stock
from .structure import analyze_market_structure, compact_market_structure


def classify_sector_trend(df: pd.DataFrame) -> str:
    """Classify a sector with only information available in its own series."""
    if len(df) < 20:
        return "unknown"
    close = pd.to_numeric(df["close"], errors="coerce")
    ma20 = close.rolling(20).mean()
    slope = float(ma20.iloc[-1] - ma20.iloc[-5]) if len(df) >= 24 else 0.0
    last = float(close.iloc[-1])
    if last > float(ma20.iloc[-1]) and slope > 0:
        return "up"
    if last < float(ma20.iloc[-1]) and slope < 0:
        return "down"
    return "range"


def score_sector_alignment(stock_trend: str, sector_trend: str, *,
                           sector_type: str | None,
                           main_net_pct: float | None,
                           breadth_up_pct: float | None) -> tuple[float, str]:
    score = 0.0
    if stock_trend == sector_trend and stock_trend in {"up", "down"}:
        score += 0.45
    elif sector_trend == "range" or stock_trend == "range":
        score += 0.15
    else:
        score -= 0.25
    if sector_type == "industry":
        score += 0.15
    if main_net_pct is not None:
        score += max(-0.15, min(0.15, float(main_net_pct) / 10.0))
    if breadth_up_pct is not None:
        score += max(-0.20, min(0.20, (float(breadth_up_pct) - 50.0) / 100.0))
    score = round(max(-1.0, min(1.0, score)), 4)
    same_direction = stock_trend == sector_trend and stock_trend in {"up", "down"}
    opposite_direction = {stock_trend, sector_trend} == {"up", "down"}
    label = (
        "aligned" if same_direction and score >= 0.35
        else "conflicting" if opposite_direction or score < 0
        else "mixed"
    )
    return score, label


def _finite(value) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def build_stock_sector_context(stock_code: str, *, stock_trend: str,
                               max_sectors: int = 6,
                               kline_limit: int = 1500) -> dict:
    memberships = get_sectors_by_stock(stock_code)
    # Industry first, then specific concepts with smaller membership.  Broad
    # index/risk labels remain available but do not crowd out the industry.
    memberships.sort(key=lambda x: (
        x.get("sector_type") != "industry",
        -(int(x.get("kline_bars") or 0)),
        int(x.get("member_count") or 10**9),
        str(x.get("sector_code") or ""),
    ))
    selected = memberships[:max(0, int(max_sectors))]
    rows = []
    for item in selected:
        code = item["sector_code"]
        klines = get_sector_kline_local(code, limit=kline_limit)
        if not klines:
            rows.append({**item, "data_status": "missing", "trend": "unknown"})
            continue
        df = pd.DataFrame(klines).rename(columns={"trade_date": "date"})
        for col in ("open", "high", "low", "close", "volume"):
            if col in df:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
        trend = classify_sector_trend(df)
        members = get_sector_members_local(code)
        changes = [_finite(x.get("change_pct")) for x in members]
        changes = [x for x in changes if x is not None]
        breadth = round(sum(x > 0 for x in changes) / len(changes) * 100, 2) if changes else None
        median_change = round(float(median(changes)), 4) if changes else None
        score, alignment = score_sector_alignment(
            stock_trend, trend, sector_type=item.get("sector_type"),
            main_net_pct=_finite(item.get("main_net_pct")), breadth_up_pct=breadth,
        )
        structure = compact_market_structure(
            analyze_market_structure(df, include_positions=False),
            current_price=float(df.iloc[-1]["close"]),
        )
        bars = len(df)
        rows.append({
            **item,
            "trend": trend,
            "alignment": alignment,
            "alignment_score": score,
            "breadth_up_pct": breadth,
            "median_member_change_pct": median_change,
            "data_status": "ready" if bars >= 260 else "short_history",
            "structure": structure,
        })
    ready = [x for x in rows if x.get("data_status") in {"ready", "short_history"}]
    aligned = [x for x in ready if x.get("alignment") == "aligned"]
    conflicting = [x for x in ready if x.get("alignment") == "conflicting"]
    return {
        "stock_code": stock_code,
        "membership_count": len(memberships),
        "analyzed_count": len(rows),
        "aligned_count": len(aligned),
        "conflicting_count": len(conflicting),
        "coverage_warning": (
            "sector history is shorter than 260 daily bars for one or more sectors; "
            "do not use it as long-cycle monthly evidence"
            if any(x.get("data_status") == "short_history" for x in rows) else None
        ),
        "sectors": rows,
    }
