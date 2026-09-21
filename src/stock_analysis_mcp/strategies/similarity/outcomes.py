"""
similarity/outcomes.py — 统计层: 相似窗口的历史后验统计

前向收益/回撤统计、形态自身度量、汇总与条件概率 (等权 + 相似度加权)。
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


def _forward_stats(df: pd.DataFrame, end_idx: int, horizons: Iterable[int]) -> dict:
    close = float(df.iloc[end_idx]["close"])
    result = {}
    for horizon in horizons:
        future = df.iloc[end_idx + 1:end_idx + horizon + 1]
        if len(future) < horizon:
            continue
        result[str(horizon)] = {
            "return_pct": round((float(future.iloc[-1]["close"]) / close - 1.0) * 100.0, 2),
            "max_gain_pct": round((float(future["high"].max()) / close - 1.0) * 100.0, 2),
            "max_drawdown_pct": round((float(future["low"].min()) / close - 1.0) * 100.0, 2),
        }
    return result


def _shape_metrics(df: pd.DataFrame) -> dict:
    first = float(df.iloc[0]["close"])
    last = float(df.iloc[-1]["close"])
    close = df["close"].to_numpy(dtype=float)
    drawdown = close / np.maximum.accumulate(close) - 1.0
    return {
        "return_pct": round((last / first - 1.0) * 100.0, 2),
        "max_drawdown_pct": round(float(np.min(drawdown)) * 100.0, 2),
        "range_pct": round((float(df["high"].max()) / float(df["low"].min()) - 1.0) * 100.0, 2),
    }


def _summarize_outcomes(matches: list[dict], horizons: Iterable[int]) -> dict:
    summary = {}
    for horizon in horizons:
        values = [match["forward"][str(horizon)]["return_pct"] for match in matches
                  if str(horizon) in match["forward"]]
        drawdowns = [match["forward"][str(horizon)]["max_drawdown_pct"] for match in matches
                     if str(horizon) in match["forward"]]
        if values:
            summary[str(horizon)] = {
                "samples": len(values),
                "average_return_pct": round(float(np.mean(values)), 2),
                "median_return_pct": round(float(np.median(values)), 2),
                "win_rate_pct": round(sum(value > 0 for value in values) / len(values) * 100.0, 2),
                "worst_return_pct": round(min(values), 2),
                "average_max_drawdown_pct": round(float(np.mean(drawdowns)), 2),
            }
    return summary


def _outcome_probabilities(matches: list[dict], horizons: Iterable[int],
                           move_threshold_pct: float) -> dict:
    """Historical conditional frequencies, both equal- and similarity-weighted."""
    result = {}
    for horizon in horizons:
        usable = [match for match in matches if str(horizon) in match["forward"]]
        if not usable:
            continue
        returns = np.array(
            [match["forward"][str(horizon)]["return_pct"] for match in usable], dtype=float)
        weights = np.array([max(float(match["score"]), 1e-9) for match in usable])
        weights /= weights.sum()
        up = returns > move_threshold_pct
        down = returns < -move_threshold_pct
        sideways = ~(up | down)

        def raw_pct(mask):
            return round(float(np.mean(mask)) * 100.0, 2)

        def weighted_pct(mask):
            return round(float(weights[mask].sum()) * 100.0, 2)

        gains = np.array(
            [match["forward"][str(horizon)]["max_gain_pct"] for match in usable])
        drawdowns = np.array(
            [match["forward"][str(horizon)]["max_drawdown_pct"] for match in usable])
        sample_size = len(usable)
        result[str(horizon)] = {
            "sample_size": sample_size,
            "threshold_pct": move_threshold_pct,
            "probability_pct": {
                "up": raw_pct(up),
                "sideways": raw_pct(sideways),
                "down": raw_pct(down),
                "positive_close": raw_pct(returns > 0),
                "reached_plus_5": raw_pct(gains >= 5.0),
                "touched_minus_5": raw_pct(drawdowns <= -5.0),
            },
            "similarity_weighted_probability_pct": {
                "up": weighted_pct(up),
                "sideways": weighted_pct(sideways),
                "down": weighted_pct(down),
            },
            "average_return_pct": round(float(np.mean(returns)), 2),
            "median_return_pct": round(float(np.median(returns)), 2),
            "confidence": ("high" if sample_size >= 50 else
                           "medium" if sample_size >= 20 else "low"),
        }
    return result
