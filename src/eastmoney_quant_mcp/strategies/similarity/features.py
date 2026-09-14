"""
similarity/features.py — 纯数学层: K线清洗 / 归一化特征 / DTW 距离 / 粗筛评分

比较的是归一化后的路径形状, 与绝对价格和K线数量无关。
"""

from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd

PERIOD_LABELS = {
    "1": "1m", "5": "5m", "15": "15m", "30": "30m", "60": "60m",
    "101": "daily", "102": "weekly", "103": "monthly",
}
DEFAULT_WEIGHTS = {
    "price_path": 0.45,
    "drawdown_path": 0.15,
    "range_path": 0.10,
    "volume_path": 0.15,
    "turning_path": 0.15,
}


def _frame(rows: Iterable[dict]) -> pd.DataFrame:
    df = pd.DataFrame(list(rows))
    if df.empty:
        return df
    time_col = "datetime" if "datetime" in df.columns else "date"
    required = {time_col, "high", "low", "close"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"K线缺少字段: {sorted(missing)}")
    df = df.rename(columns={time_col: "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["timestamp", "high", "low", "close"])
    df = df[(df["close"] > 0) & (df["high"] > 0) & (df["low"] > 0)]
    df = df[df["high"] >= df["low"]]
    return (df.sort_values("timestamp")
            .drop_duplicates("timestamp", keep="last")
            .reset_index(drop=True))


def _resample(values: np.ndarray, points: int) -> np.ndarray:
    if len(values) == points:
        return values.astype(float)
    source = np.linspace(0.0, 1.0, len(values))
    target = np.linspace(0.0, 1.0, points)
    return np.interp(target, source, values).astype(float)


def _standardize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    scale = float(np.std(values))
    if not math.isfinite(scale) or scale < 1e-12:
        return np.zeros_like(values)
    return (values - float(np.mean(values))) / scale


def _relative_drawdown(close: np.ndarray) -> np.ndarray:
    drawdown = close / np.maximum.accumulate(close) - 1.0
    scale = abs(float(np.min(drawdown)))
    return drawdown / scale if scale > 1e-12 else drawdown


def _features(df: pd.DataFrame, points: int = 64) -> tuple[dict[str, np.ndarray], bool]:
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float)
    low = df["low"].to_numpy(dtype=float)
    log_close = np.log(close)

    price = _standardize(_resample(log_close, points))
    drawdown = _resample(_relative_drawdown(close), points)
    intrabar_range = np.maximum(high - low, 0.0) / close
    range_path = _standardize(_resample(intrabar_range, points))

    # A smoothed first derivative encodes turning points without hard Elliott labels.
    smooth = pd.Series(price).rolling(5, center=True, min_periods=1).mean().to_numpy()
    turning = _standardize(np.gradient(smooth))

    has_volume = "volume" in df.columns and int((df["volume"] > 0).sum()) >= len(df) // 2
    if has_volume:
        volume = _standardize(_resample(np.log1p(df["volume"].fillna(0).to_numpy()), points))
    else:
        volume = np.zeros(points)
    return {
        "price_path": price,
        "drawdown_path": drawdown,
        "range_path": range_path,
        "volume_path": volume,
        "turning_path": turning,
    }, has_volume


def _dtw_distance(left: np.ndarray, right: np.ndarray, band: int = 8) -> float:
    """Banded DTW average absolute distance."""
    n, m = len(left), len(right)
    band = max(band, abs(n - m))
    costs = np.full((n + 1, m + 1), np.inf)
    steps = np.zeros((n + 1, m + 1), dtype=int)
    costs[0, 0] = 0.0
    for i in range(1, n + 1):
        for j in range(max(1, i - band), min(m, i + band) + 1):
            choices = ((costs[i - 1, j], steps[i - 1, j]),
                       (costs[i, j - 1], steps[i, j - 1]),
                       (costs[i - 1, j - 1], steps[i - 1, j - 1]))
            prior_cost, prior_steps = min(choices, key=lambda item: item[0])
            costs[i, j] = prior_cost + abs(float(left[i - 1] - right[j - 1]))
            steps[i, j] = prior_steps + 1
    return float(costs[n, m] / max(steps[n, m], 1))


def _component_scores(query: dict[str, np.ndarray], candidate: dict[str, np.ndarray],
                      use_volume: bool) -> tuple[float, dict[str, float]]:
    weights = dict(DEFAULT_WEIGHTS)
    if not use_volume:
        removed = weights.pop("volume_path")
        total = sum(weights.values())
        weights = {key: value * (total + removed) / total for key, value in weights.items()}

    scores = {}
    for key in weights:
        if key == "price_path":
            distance = _dtw_distance(query[key], candidate[key])
        else:
            distance = float(np.sqrt(np.mean((query[key] - candidate[key]) ** 2)))
        scores[key] = math.exp(-distance)
    total_score = sum(scores[key] * weights[key] for key in weights)
    return total_score, scores


def _coarse_price_scores(close: np.ndarray, window: int,
                         query_price: np.ndarray) -> np.ndarray:
    """Vectorized fixed-window price-path scores used before full DTW scoring."""
    source = np.lib.stride_tricks.sliding_window_view(np.log(close), window)
    positions = np.linspace(0.0, window - 1, len(query_price))
    lower = np.floor(positions).astype(int)
    upper = np.ceil(positions).astype(int)
    fraction = positions - lower
    sampled = source[:, lower] * (1.0 - fraction) + source[:, upper] * fraction
    means = sampled.mean(axis=1, keepdims=True)
    scales = sampled.std(axis=1, keepdims=True)
    normalized = np.divide(sampled - means, scales,
                           out=np.zeros_like(sampled), where=scales >= 1e-12)
    distances = np.sqrt(np.mean((normalized - query_price) ** 2, axis=1))
    return np.exp(-distances)
