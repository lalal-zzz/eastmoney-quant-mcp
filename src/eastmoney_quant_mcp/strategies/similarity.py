"""Price-volume shape similarity across different K-line timeframes.

The engine compares normalized paths rather than absolute prices or bar duration.
It is intentionally descriptive: a high score means the shapes are alike, not
that the historical outcome must repeat.
"""
from __future__ import annotations

import asyncio
import heapq
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def compare_cross_timeframe_patterns(
    query_rows: Iterable[dict],
    candidate_sets: dict[str, Iterable[dict]],
    *,
    query_bars: int = 30,
    candidate_window_bars: Iterable[int] | None = None,
    top_n: int = 10,
    min_score: float = 0.55,
    forward_bars: Iterable[int] = (5, 10, 20),
    cutoff_at_query_start: bool = True,
    candidate_metadata: dict[str, dict] | None = None,
    candidate_latest_only: bool = False,
    require_forward: bool = True,
    prefilter_limit: int | None = None,
    probability_sample_size: int = 100,
    move_threshold_pct: float = 2.0,
) -> dict:
    """Compare the latest query shape with historical windows of any bar duration."""
    query_df = _frame(query_rows)
    if len(query_df) < query_bars:
        raise ValueError(f"查询周期K线不足: 需要{query_bars}根, 实际{len(query_df)}根")
    query_df = query_df.tail(query_bars).reset_index(drop=True)
    query_features, query_has_volume = _features(query_df)
    query_start = query_df.iloc[0]["timestamp"]
    horizons = sorted({int(value) for value in forward_bars if int(value) > 0})
    requested_windows = candidate_window_bars or [query_bars]
    windows = sorted({int(value) for value in requested_windows if int(value) >= 12})
    if not windows:
        raise ValueError("candidate_window_bars 至少需要一个不小于12的窗口")

    prefilter_limit = prefilter_limit or max(1000, top_n * 100)
    coarse_heap = []
    sequence = 0
    evaluated = 0
    frames = {}
    metadata = candidate_metadata or {}
    for candidate_key, rows in candidate_sets.items():
        item_meta = metadata.get(candidate_key, {})
        period = str(item_meta.get("period", candidate_key))
        candidate_df = _frame(rows)
        if candidate_df.empty:
            continue
        frames[candidate_key] = candidate_df
        forward_tail = max(horizons, default=0) if require_forward else 0
        latest_end = len(candidate_df) - forward_tail - 1
        if cutoff_at_query_start:
            before_query = np.flatnonzero(candidate_df["timestamp"].to_numpy() < query_start)
            if len(before_query):
                # Keep both the matched window and its forward outcome strictly
                # before the query starts, otherwise the result leaks current data.
                latest_end = min(
                    latest_end,
                    int(before_query[-1]) - forward_tail,
                )
            else:
                continue
        for window in windows:
            if latest_end < window - 1:
                continue
            usable_close = candidate_df["close"].to_numpy(dtype=float)[:latest_end + 1]
            coarse_scores = _coarse_price_scores(
                usable_close, window, query_features["price_path"])
            if candidate_latest_only:
                indices = np.array([len(coarse_scores) - 1])
            else:
                indices = np.arange(len(coarse_scores))
            evaluated += len(indices)
            for row_idx in indices:
                end_idx = int(row_idx) + window - 1
                start_idx = end_idx - window + 1
                record = (float(coarse_scores[row_idx]), sequence, candidate_key,
                          period, start_idx, end_idx, window)
                sequence += 1
                if len(coarse_heap) < prefilter_limit:
                    heapq.heappush(coarse_heap, record)
                elif record[0] > coarse_heap[0][0]:
                    heapq.heapreplace(coarse_heap, record)

    raw_matches = []
    for coarse_score, _, candidate_key, period, start_idx, end_idx, window in sorted(
            coarse_heap, reverse=True):
        candidate_df = frames[candidate_key]
        item_meta = metadata.get(candidate_key, {})
        sample = candidate_df.iloc[start_idx:end_idx + 1]
        features, has_volume = _features(sample)
        score, parts = _component_scores(
            query_features, features, query_has_volume and has_volume)
        if score < min_score:
            continue
        start_ts = sample.iloc[0]["timestamp"]
        end_ts = sample.iloc[-1]["timestamp"]
        raw_matches.append({
            "period": period,
            "period_label": PERIOD_LABELS.get(str(period), str(period)),
            "symbol": item_meta.get("symbol"),
            "name": item_meta.get("name"),
            "start": start_ts.isoformat(),
            "end": end_ts.isoformat(),
            "bars": window,
            "calendar_days": int((end_ts - start_ts).days),
            "coarse_price_score": round(coarse_score, 4),
            "score": round(score, 4),
            "score_breakdown": {key: round(value, 4) for key, value in parts.items()},
            "volume_compared": bool(query_has_volume and has_volume),
            "shape_metrics": _shape_metrics(sample),
            "forward": _forward_stats(candidate_df, end_idx, horizons),
            "_start_idx": start_idx,
            "_end_idx": end_idx,
        })

    selected = []
    selection_limit = max(top_n, probability_sample_size)
    for match in sorted(raw_matches, key=lambda item: item["score"], reverse=True):
        duplicate = False
        for kept in selected:
            if (kept["period"], kept.get("symbol")) != (
                    match["period"], match.get("symbol")):
                continue
            overlap = max(0, min(kept["_end_idx"], match["_end_idx"]) -
                          max(kept["_start_idx"], match["_start_idx"]) + 1)
            if overlap / min(kept["bars"], match["bars"]) >= 0.5:
                duplicate = True
                break
        if not duplicate:
            selected.append(match)
        if len(selected) >= selection_limit:
            break
    for match in selected:
        match.pop("_start_idx", None)
        match.pop("_end_idx", None)

    return {
        "query": {
            "start": query_df.iloc[0]["timestamp"].isoformat(),
            "end": query_df.iloc[-1]["timestamp"].isoformat(),
            "bars": len(query_df),
            "volume_available": query_has_volume,
            "shape_metrics": _shape_metrics(query_df),
        },
        "matches": selected[:top_n],
        "outcome_summary": _summarize_outcomes(selected, horizons),
        "outcome_probabilities": _outcome_probabilities(
            selected, horizons, move_threshold_pct),
        "probability_sample_size": len(selected),
        "evaluated_windows": evaluated,
        "fully_scored_windows": len(coarse_heap),
        "method": {
            "normalization_points": 64,
            "window_policy": ("uniform_query_bars" if windows == [query_bars]
                              else "explicit_temporal_stretching"),
            "price_alignment": "banded_dtw",
            "retrieval": "vectorized_price_prefilter_then_full_score",
            "weights": DEFAULT_WEIGHTS,
            "note": "相似度描述历史形状，不代表后续走势必然重复",
        },
    }


def _period_rows(daily_rows: Iterable[dict], period: str, limit: int) -> list[dict]:
    df = _frame(daily_rows)
    if df.empty:
        return []
    if period == "101":
        sampled = df.tail(limit).copy() if limit > 0 else df.copy()
    else:
        rule = {"102": "W-FRI", "103": "ME"}[period]
        sampled = (df.set_index("timestamp")
                   .resample(rule)
                   .agg({"open": "first", "high": "max", "low": "min",
                         "close": "last", "volume": "sum"})
                   .dropna(subset=["high", "low", "close"]))
        if limit > 0:
            sampled = sampled.tail(limit)
        sampled = sampled.reset_index()
    sampled = sampled.rename(columns={"timestamp": "date"})
    return sampled.where(sampled.notna(), None).to_dict(orient="records")


def _candidate_universe(scope: str, symbols: list[str] | None,
                        max_symbols: int) -> list[dict]:
    from ..data.network import normalize_symbol
    from ..data.storage import query_stock_db

    if scope == "symbols":
        if not symbols:
            raise ValueError("candidate_scope=symbols 时必须提供 candidate_symbols")
        normalized = list(dict.fromkeys(normalize_symbol(value) for value in symbols))
        if max_symbols > 0 and len(normalized) > max_symbols:
            normalized = normalized[:max_symbols]
        placeholders = ",".join("?" for _ in normalized)
        names = query_stock_db(
            f"SELECT symbol, name FROM stock_basic WHERE symbol IN ({placeholders})",
            tuple(normalized),
        )
        name_map = {row["symbol"]: row.get("name") for row in names}
        return [{"symbol": value, "name": name_map.get(value)} for value in normalized]

    sql = """SELECT b.symbol, b.name, c.row_count
           FROM stock_basic b
           JOIN data_coverage c ON c.symbol=b.symbol
           WHERE c.data_type='stock_kline' AND c.period='daily'
             AND c.adjust_type='qfq' AND c.row_count>=260
             AND b.name NOT LIKE '%ST%'
           ORDER BY c.row_count DESC, b.symbol"""
    if max_symbols > 0:
        sql += " LIMIT ?"
        return query_stock_db(sql, (max_symbols,))
    return query_stock_db(sql)


def _load_local_candidate_sets(items: list[dict], periods: list[str],
                               daily_limit: int, period_limit: int,
                               adjust: str, workers: int) -> tuple[dict, dict, list[str]]:
    from ..data.search import get_stock_kline_local

    sets = {}
    metadata = {}
    skipped = []

    def load(item):
        local_limit = daily_limit if daily_limit > 0 else 1_000_000
        rows = get_stock_kline_local(item["symbol"], local_limit, adjust)
        sampled = {period: _period_rows(rows, period, period_limit)
                   for period in periods} if len(rows) >= 30 else {}
        return item, sampled

    with ThreadPoolExecutor(max_workers=max(1, min(workers, 16))) as pool:
        futures = [pool.submit(load, item) for item in items]
        for future in as_completed(futures):
            item, sampled = future.result()
            if not sampled:
                skipped.append(item["symbol"])
                continue
            for period in periods:
                rows = sampled[period]
                if len(rows) < 12:
                    continue
                key = f"{item['symbol']}:{period}"
                sets[key] = rows
                metadata[key] = {
                    "symbol": item["symbol"],
                    "name": item.get("name"),
                    "period": period,
                }
    return sets, metadata, skipped


def _compare_local_batches(query_rows: list[dict], items: list[dict], periods: list[str],
                           *, daily_limit: int, period_limit: int, adjust: str,
                           workers: int, query_bars: int, windows: list[int],
                           top_n: int, min_score: float, search_mode: str,
                           probability_sample_size: int, move_threshold_pct: float,
                           batch_size: int = 200) -> tuple[dict, dict]:
    """Load and compare a large local universe in bounded-memory batches."""
    all_matches = []
    all_skipped = []
    loaded_symbols = set()
    loaded_series = 0
    evaluated = 0
    fully_scored = 0
    base_result = None
    for offset in range(0, len(items), batch_size):
        batch = items[offset:offset + batch_size]
        sets, metadata, skipped = _load_local_candidate_sets(
            batch, periods, daily_limit, period_limit, adjust, workers)
        all_skipped.extend(skipped)
        if not sets:
            continue
        loaded_series += len(sets)
        loaded_symbols.update(item.get("symbol") for item in metadata.values())
        pool_size = max(top_n, probability_sample_size)
        partial = compare_cross_timeframe_patterns(
            query_rows, sets, query_bars=query_bars,
            candidate_window_bars=windows, top_n=pool_size, min_score=min_score,
            cutoff_at_query_start=search_mode == "history",
            candidate_metadata=metadata,
            candidate_latest_only=search_mode == "latest",
            require_forward=search_mode == "history",
            probability_sample_size=pool_size,
            move_threshold_pct=move_threshold_pct,
        )
        base_result = base_result or partial
        evaluated += partial["evaluated_windows"]
        fully_scored += partial["fully_scored_windows"]
        all_matches.extend(partial["matches"])
    if base_result is None:
        raise ValueError("候选股票没有足够的本地K线，请先运行sync_stock_kline_universe")
    probability_pool = sorted(
        all_matches, key=lambda item: item["score"], reverse=True)[:pool_size]
    base_result["matches"] = probability_pool[:top_n]
    base_result["outcome_summary"] = _summarize_outcomes(
        probability_pool, (5, 10, 20))
    base_result["outcome_probabilities"] = _outcome_probabilities(
        probability_pool, (5, 10, 20), move_threshold_pct)
    base_result["probability_sample_size"] = len(probability_pool)
    base_result["evaluated_windows"] = evaluated
    base_result["fully_scored_windows"] = fully_scored
    stats = {
        "loaded_series": loaded_series,
        "loaded_symbols": len(loaded_symbols),
        "skipped_symbols": all_skipped[:50],
        "skipped_count": len(all_skipped),
    }
    return base_result, stats


async def find_cross_timeframe_similar_patterns(
    symbol: str,
    query_period: str = "101",
    candidate_periods: list[str] | None = None,
    query_bars: int = 30,
    candidate_window_bars: list[int] | None = None,
    search_bars: int = 0,
    top_n: int = 10,
    min_score: float = 0.55,
    adjust: str = "qfq",
    candidate_scope: str = "market",
    candidate_symbols: list[str] | None = None,
    search_mode: str = "history",
    max_symbols: int = 0,
    workers: int = 8,
    probability_sample_size: int = 100,
    move_threshold_pct: float = 2.0,
) -> dict:
    """Search self, a symbol pool, or the local market across timeframes."""
    from ..data.network import normalize_symbol
    from ..tools.stock_data import get_stock_kline_period

    symbol = normalize_symbol(symbol)
    query_period = str(query_period)
    candidate_periods = [str(value) for value in (candidate_periods or [query_period])]
    periods = {query_period, *candidate_periods}
    invalid = periods.difference(PERIOD_LABELS)
    if invalid:
        raise ValueError(f"不支持的周期: {sorted(invalid)}")
    if candidate_scope not in {"self", "symbols", "market"}:
        raise ValueError("candidate_scope 仅支持 self/symbols/market")
    if search_mode not in {"history", "latest"}:
        raise ValueError("search_mode 仅支持 history/latest")
    windows = candidate_window_bars or [query_bars]
    network_history = search_bars if search_bars > 0 else 1000
    fetch_limit = max(network_history, max(windows) + 21, query_bars)
    query_rows = await get_stock_kline_period(symbol, query_period, fetch_limit, adjust)

    if candidate_scope == "self":
        missing_periods = [period for period in candidate_periods if period != query_period]
        fetched = await asyncio.gather(*(
            get_stock_kline_period(symbol, period, fetch_limit, adjust)
            for period in missing_periods
        ))
        by_period = {query_period: query_rows, **dict(zip(missing_periods, fetched))}
        candidate_sets = {period: by_period[period] for period in candidate_periods}
        metadata = {period: {"symbol": symbol, "period": period}
                    for period in candidate_periods}
        scan_stats = {"loaded_series": len(candidate_sets), "loaded_symbols": 1,
                      "skipped_symbols": [], "skipped_count": 0}
        requested_count = 1
    else:
        if any(period not in {"101", "102", "103"} for period in candidate_periods):
            raise ValueError("跨股票搜索使用本地数据，candidate_periods 仅支持101/102/103")
        items = await asyncio.to_thread(
            _candidate_universe, candidate_scope, candidate_symbols, max_symbols)
        items = [item for item in items if item["symbol"] != symbol]
        if not items:
            raise ValueError("本地候选股票池为空，请先同步日K数据或检查candidate_symbols")
        requested_count = len(items)
        factor = max({"101": 1, "102": 5, "103": 22}[period]
                     for period in candidate_periods)
        needed_period_bars = search_bars if search_mode == "history" else max(windows)
        daily_limit = (0 if search_mode == "history" and search_bars == 0 else
                       min(5000, max(260, (needed_period_bars + 21) * factor)))
        result, scan_stats = await asyncio.to_thread(
            _compare_local_batches, query_rows, items, candidate_periods,
            daily_limit=daily_limit,
            period_limit=search_bars if search_mode == "history" else max(windows) + 1,
            adjust=adjust, workers=workers, query_bars=query_bars, windows=windows,
            top_n=top_n, min_score=min_score, search_mode=search_mode,
            probability_sample_size=probability_sample_size,
            move_threshold_pct=move_threshold_pct)

    if candidate_scope == "self":
        result = await asyncio.to_thread(
            compare_cross_timeframe_patterns, query_rows, candidate_sets,
            query_bars=query_bars, candidate_window_bars=windows,
            top_n=top_n, min_score=min_score,
            cutoff_at_query_start=search_mode == "history",
            candidate_metadata=metadata,
            candidate_latest_only=search_mode == "latest",
            require_forward=search_mode == "history",
            probability_sample_size=probability_sample_size,
            move_threshold_pct=move_threshold_pct)
    result["symbol"] = symbol
    result["query"]["period"] = query_period
    result["query"]["period_label"] = PERIOD_LABELS[query_period]
    loaded_symbols = scan_stats["loaded_symbols"]
    result["search"] = {
        "candidate_scope": candidate_scope,
        "search_mode": search_mode,
        "requested_symbols": requested_count,
        "loaded_series": scan_stats["loaded_series"],
        "loaded_symbols": loaded_symbols,
        "coverage_ratio": round(loaded_symbols / requested_count, 4) if requested_count else 0.0,
        "skipped_symbols": scan_stats["skipped_symbols"],
        "skipped_count": scan_stats["skipped_count"],
        "local_history_bars": ("all" if candidate_scope != "self" and daily_limit == 0
                               else daily_limit if candidate_scope != "self" else None),
    }
    return result
