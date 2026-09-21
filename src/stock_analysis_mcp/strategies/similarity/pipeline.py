"""
similarity/pipeline.py — IO/编排层: 候选池加载 + 粗筛 + 全量评分 + 对外入口

compare_cross_timeframe_patterns      核心比对 (内存中的候选序列)
find_cross_timeframe_similar_patterns 异步入口 (self / symbols / market 三种候选范围)
"""

from __future__ import annotations

import asyncio
import heapq
from typing import Iterable

import numpy as np

from ...core.parallel import run_parallel
from .features import (
    DEFAULT_WEIGHTS,
    PERIOD_LABELS,
    _coarse_price_scores,
    _component_scores,
    _features,
    _frame,
)
from .outcomes import _forward_stats, _outcome_probabilities, _shape_metrics, _summarize_outcomes


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


# ── 本地候选池加载 ──


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
    from ...data.network import normalize_symbol
    from ...data.storage import query_stock_db

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
    from ...data.search import get_stock_kline_local

    sets = {}
    metadata = {}
    skipped = []

    def load(item):
        local_limit = daily_limit if daily_limit > 0 else 1_000_000
        rows = get_stock_kline_local(item["symbol"], local_limit, adjust)
        sampled = {period: _period_rows(rows, period, period_limit)
                   for period in periods} if len(rows) >= 30 else {}
        return item, sampled

    for _item, result in run_parallel(items, load, workers=max(1, min(workers, 16))):
        if isinstance(result, Exception):
            raise result
        item, sampled = result
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


def _extract_coarse_records(query_rows: list[dict], candidate_sets: dict,
                            metadata: dict, query_bars: int, windows: list[int],
                            search_mode: str,
                            per_series_limit: int = 10) -> tuple[list[dict], int]:
    """Keep diverse coarse matches while the source history is still in memory."""
    query_df = _frame(query_rows)
    query_features, _ = _features(query_df.tail(query_bars))
    query_start = query_df.tail(query_bars).iloc[0]["timestamp"]
    forward_tail = 20 if search_mode == "history" else 0
    records = []
    evaluated = 0
    for candidate_key, rows in candidate_sets.items():
        candidate_df = _frame(rows)
        if candidate_df.empty:
            continue
        latest_end = len(candidate_df) - forward_tail - 1
        if search_mode == "history":
            before_query = np.flatnonzero(candidate_df["timestamp"].to_numpy() < query_start)
            if not len(before_query):
                continue
            latest_end = min(latest_end, int(before_query[-1]) - forward_tail)
        for window in windows:
            if latest_end < window - 1:
                continue
            close = candidate_df["close"].to_numpy(dtype=float)[:latest_end + 1]
            scores = _coarse_price_scores(close, window, query_features["price_path"])
            evaluated += len(scores)
            if search_mode == "latest":
                selected_indices = [len(scores) - 1]
            else:
                selected_indices = []
                min_separation = max(1, window // 2)
                for row_idx in np.argsort(scores)[::-1]:
                    if all(abs(int(row_idx) - kept) >= min_separation
                           for kept in selected_indices):
                        selected_indices.append(int(row_idx))
                    if len(selected_indices) >= per_series_limit:
                        break
            for row_idx in selected_indices:
                end_idx = row_idx + window - 1
                segment = candidate_df.iloc[
                    row_idx:end_idx + forward_tail + 1].copy()
                segment = segment.rename(columns={"timestamp": "date"})
                records.append({
                    "coarse_score": float(scores[row_idx]),
                    "candidate_key": candidate_key,
                    "period": metadata[candidate_key]["period"],
                    "symbol": metadata[candidate_key].get("symbol"),
                    "name": metadata[candidate_key].get("name"),
                    "rows": segment.where(segment.notna(), None).to_dict(orient="records"),
                })
    return records, evaluated


def _compare_local_batches(query_rows: list[dict], items: list[dict], periods: list[str],
                           *, daily_limit: int, period_limit: int, adjust: str,
                           workers: int, query_bars: int, windows: list[int],
                           top_n: int, min_score: float, search_mode: str,
                           probability_sample_size: int, move_threshold_pct: float,
                           batch_size: int = 50) -> tuple[dict, dict]:
    """Load and compare a large local universe in bounded-memory batches."""
    all_skipped = []
    loaded_symbols = set()
    loaded_series = 0
    evaluated = 0
    pool_size = max(top_n, probability_sample_size)
    global_prefilter_limit = max(1000, pool_size * 10)
    coarse_heap = []
    sequence = 0
    for offset in range(0, len(items), batch_size):
        batch = items[offset:offset + batch_size]
        sets, metadata, skipped = _load_local_candidate_sets(
            batch, periods, daily_limit, period_limit, adjust, workers)
        all_skipped.extend(skipped)
        if not sets:
            continue
        loaded_series += len(sets)
        loaded_symbols.update(item.get("symbol") for item in metadata.values())
        records, batch_evaluated = _extract_coarse_records(
            query_rows, sets, metadata, query_bars, windows, search_mode)
        evaluated += batch_evaluated
        for record in records:
            entry = (record["coarse_score"], sequence, record)
            sequence += 1
            if len(coarse_heap) < global_prefilter_limit:
                heapq.heappush(coarse_heap, entry)
            elif entry[0] > coarse_heap[0][0]:
                heapq.heapreplace(coarse_heap, entry)
    if not coarse_heap:
        raise ValueError("候选股票没有足够的本地K线，请先运行sync_stock_kline_universe")
    retained = [entry[2] for entry in sorted(coarse_heap, reverse=True)]
    compact_sets = {}
    compact_metadata = {}
    for index, record in enumerate(retained):
        key = f"{record['candidate_key']}:{index}"
        compact_sets[key] = record["rows"]
        compact_metadata[key] = {
            "period": record["period"], "symbol": record["symbol"],
            "name": record["name"],
        }
    result = compare_cross_timeframe_patterns(
        query_rows, compact_sets, query_bars=query_bars,
        candidate_window_bars=windows, top_n=top_n, min_score=min_score,
        cutoff_at_query_start=search_mode == "history",
        candidate_metadata=compact_metadata, candidate_latest_only=True,
        require_forward=search_mode == "history",
        probability_sample_size=probability_sample_size,
        move_threshold_pct=move_threshold_pct,
        prefilter_limit=global_prefilter_limit,
    )
    result["evaluated_windows"] = evaluated
    stats = {
        "loaded_series": loaded_series,
        "loaded_symbols": len(loaded_symbols),
        "skipped_symbols": all_skipped[:50],
        "skipped_count": len(all_skipped),
    }
    return result, stats


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
    from ...data.network import normalize_symbol
    from ...tools.stock_data import get_stock_kline_period

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
