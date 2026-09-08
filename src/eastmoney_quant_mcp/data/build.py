"""
数据构建 / 维护模块 —— 移植自"股票信息"项目
(rebuild_stock_db.py / backfill_daily_spot.py / eastmoney_rank_scheduler.py)

功能:
- rebuild_full_data()  步骤化全量重建 (spot → 股票列表 → 全量K线 → guba排名 → combined → 指标缓存)
                        + 可选板块全量K线/指标; rebuild_progress 断点续传; 支持 --dry-run
- backfill_data()      缺口检测补齐 (history / rank / combined)
- daily_capture()      晚间采集 (xuangu 排名 + spot 快照 + 最近K线增量 + 指标缓存), 跳过非交易日
- cleanup_database()   报告表规模 + VACUUM + 清理重建进度表过期步骤

所有函数为同步实现(网络层直接复用 data/sources.py 与 providers), 供 CLI 与任务计划调用。
"""

import os
import re
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import pandas as pd

from .indicators import compute_all_indicators
from .storage import (
    get_sector_db,
    get_stock_db,
    build_combined_from_history,
    get_rebuild_done,
    init_all,
    query_sector_db,
    query_stock_db,
    record_rebuild_progress,
    save_daily_stock_info,
    save_popularity_rank,
    save_sector_indicators,
    save_sector_kline,
    save_stock_basic,
    save_stock_indicators,
    save_stock_kline,
    upsert_combined_rank,
    upsert_combined_spot,
)
from .sources import (
    fetch_full_spot,
    fetch_guba_rank_history,
    fetch_kline_history,
    fetch_xuangu_rankings,
    is_trade_day,
    load_trade_dates,
    previous_trade_day,
    wait_for_internet,
)
from .sync import _stocks_from_spot


# ── 通用小工具 ──


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _table_count(db: str, table: str) -> int:
    with sqlite3.connect(db) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def _get_symbols() -> list[str]:
    return [r["symbol"] for r in query_stock_db("SELECT symbol FROM stock_basic ORDER BY symbol")]


from .indicators import indicator_rows_from_df as _indicator_rows_from_df  # noqa: E402


def _fetch_full_history(symbol: str, adjust: str = "qfq", limit: int = None) -> list[dict]:
    """全量历史K线: 腾讯单次最多 5000 根, 超过时按日期分段向前翻页"""
    if limit:
        return fetch_kline_history(symbol, adjust, limit)
    all_rows: list[dict] = []
    end: str | None = None
    for _ in range(8):  # 5000*8 根, 覆盖 A 股全部历史
        rows = fetch_kline_history(symbol, adjust, limit=5000, end_date=end)
        if not rows:
            break
        all_rows = rows + all_rows
        earliest = rows[0]["date"]
        if earliest <= "1990-12-01" or len(rows) < 5000:
            break
        end = (datetime.strptime(earliest, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    return all_rows


# ═══════════════════ 全量重建 ═══════════════════


def step_spot(dry_run: bool = False) -> int:
    """全市场 spot -> stock_basic + daily_stock_info (最近交易日快照) """
    if dry_run:
        print("[DRY-RUN] step spot: fetch full-market spot -> stock_basic + daily_stock_info")
        return 0
    if _table_count(get_stock_db(), "stock_basic") > 0:
        print("step spot: stock_basic already populated, skip.")
        return 0

    print("step spot: fetching full-market spot ...", flush=True)
    rows = fetch_full_spot(verbose=True)
    if not rows:
        raise RuntimeError("fetch_full_spot returned no rows")

    capture_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    spot_trade_date = _today() if is_trade_day(_today()) else previous_trade_day(_today())
    print(f"step spot: {len(rows)} rows, snapshot trade_date={spot_trade_date}", flush=True)

    list_rows = _stocks_from_spot(rows)
    save_stock_basic(list_rows)
    written = save_daily_stock_info(spot_trade_date, capture_time, rows)
    print(f"step spot: stock_basic={len(list_rows)}, daily_stock_info={written}", flush=True)
    return written


def step_kline(workers: int = 8, max_passes: int = 3, dry_run: bool = False) -> int:
    """全市场K线 -> stock_kline (按 symbol 断点续传; 空结果视为失败, 多轮重试) """
    if dry_run:
        print("[DRY-RUN] step kline: download full history for all stocks "
              "(tencent fqkline primary, workers={})".format(workers))
        return 0
    symbols = _get_symbols()
    done = get_rebuild_done("kline")
    pending = [s for s in symbols if s not in done]
    print(f"step kline: {len(symbols)} symbols, {len(done)} done, {len(pending)} pending",
          flush=True)
    if not pending:
        return 0
    if dry_run:
        print(f"[DRY-RUN] step kline: download full history for {len(pending)} symbols "
              f"(tencent fqkline primary, workers={workers})")
        return 0

    start = time.time()
    total_bars = 0
    pass_num = 0
    while pending and pass_num < max_passes:
        pass_num += 1
        if pass_num > 1:
            wait_s = 30 * (pass_num - 1)
            print(f"kline pass {pass_num}: retry {len(pending)} failed symbols "
                  f"after {wait_s}s cooldown...", flush=True)
            time.sleep(wait_s)

        processed = 0
        failed = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_fetch_full_history, s): s for s in pending}
            for fut in as_completed(futures):
                symbol = futures[fut]
                try:
                    bars = fut.result()
                except Exception as e:
                    failed.append(symbol)
                    print(f"  kline {symbol} FAILED: {e}", flush=True)
                    continue
                if not bars:
                    failed.append(symbol)
                    continue
                save_stock_kline(bars)
                record_rebuild_progress("kline", symbol, len(bars))
                total_bars += len(bars)
                processed += 1
                if processed % 200 == 0:
                    elapsed = int(time.time() - start)
                    print(f"  kline pass {pass_num}: {processed}/{len(pending)}, "
                          f"total {total_bars} bars, {elapsed}s elapsed", flush=True)
        pending = failed

    print(f"step kline: done, +{total_bars} bars in {int(time.time() - start)}s, "
          f"unresolved after {pass_num} passes={len(pending)} {pending[:10]}", flush=True)
    return total_bars


def step_guba_rank(workers: int = 8, dry_run: bool = False) -> int:
    """股吧年文件 -> stock_popularity_rank (按 symbol 断点续传, 不覆盖已有 xuangu 值) """
    if dry_run:
        print("[DRY-RUN] step guba: fetch guba yearly files for all stocks "
              "(rolling one year, INSERT OR IGNORE)")
        return 0
    symbols = _get_symbols()
    done = get_rebuild_done("guba")
    pending = [s for s in symbols if s not in done]
    print(f"step guba: {len(symbols)} symbols, {len(done)} done, {len(pending)} pending",
          flush=True)
    if not pending:
        return 0
    if dry_run:
        print(f"[DRY-RUN] step guba: fetch guba yearly files for {len(pending)} symbols "
              f"(rolling one year, INSERT OR IGNORE)")
        return 0

    start = time.time()
    processed = 0
    total_rows = 0
    failed = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_guba_rank_history, s): s for s in pending}
        for fut in as_completed(futures):
            symbol = futures[fut]
            try:
                recs = fut.result()
            except Exception as e:
                failed.append(symbol)
                print(f"  guba {symbol} FAILED: {e}", flush=True)
                continue
            save_popularity_rank(recs, replace=False)
            record_rebuild_progress("guba", symbol, len(recs))
            total_rows += len(recs)
            processed += 1
            if processed % 200 == 0:
                elapsed = int(time.time() - start)
                print(f"  guba progress: {processed}/{len(pending)}, "
                      f"{total_rows} records, {elapsed}s elapsed", flush=True)

    print(f"step guba: done, +{total_rows} records in {int(time.time() - start)}s, "
          f"failed={len(failed)} {failed[:10]}", flush=True)
    return total_rows


def step_combined(dry_run: bool = False) -> int:
    """stock_daily_combined <- K线 INNER JOIN 排名 + 已有 spot 快照"""
    if dry_run:
        print("[DRY-RUN] step combined: rebuild stock_daily_combined "
              "(stock_kline JOIN stock_popularity_rank + daily_stock_info)")
        return 0
    start = time.time()
    kline_rows = build_combined_from_history()
    spot_rows = upsert_combined_spot()
    total = _table_count(get_stock_db(), "stock_daily_combined")
    print(f"step combined: kline-join rows={kline_rows}, spot rows={spot_rows}, "
          f"total={total}, {int(time.time() - start)}s", flush=True)
    return kline_rows + spot_rows


def compute_all_stock_indicators(workers: int = 8, dry_run: bool = False) -> int:
    """遍历全部股票, 从 stock_kline 计算技术指标并写入 stock_indicators"""
    if dry_run:
        print("[DRY-RUN] step indicators: compute indicators for all stocks -> stock_indicators")
        return 0
    symbols = _get_symbols()
    if not symbols:
        print("step indicators: no stocks in stock_basic, skip.")
        return 0
    print(f"step indicators: computing indicators for {len(symbols)} stocks ...", flush=True)
    start = time.time()
    success = 0

    def _calc(sym: str) -> int:
        rows = query_stock_db(
            "SELECT date, open, high, low, close, volume FROM stock_kline "
            "WHERE symbol=? AND adjust_type='qfq' ORDER BY date", (sym,))
        if len(rows) < 30:
            return 0
        df = pd.DataFrame(rows)
        ind_rows = _indicator_rows_from_df(df, index_cols=("date",))
        if not ind_rows:
            return 0
        for r in ind_rows:
            r["symbol"] = sym
        save_stock_indicators(ind_rows)
        return len(ind_rows)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_calc, s): s for s in symbols}
        done_count = 0
        for fut in as_completed(futures):
            try:
                if fut.result() > 0:
                    success += 1
            except Exception:
                pass
            done_count += 1
            if done_count % 500 == 0 or done_count == len(symbols):
                print(f"  indicators: {done_count}/{len(symbols)} ok={success}, "
                      f"{int(time.time() - start)}s", flush=True)
    print(f"step indicators: done, {success} stocks cached in {int(time.time() - start)}s",
          flush=True)
    return success


def update_stock_indicators_since(start_date: str, workers: int = 8,
                                  lookback: int = 320) -> int:
    """Recompute enough history for indicators, but persist only new dates."""
    symbols = _get_symbols()
    success = 0
    written = 0
    started = time.time()

    def _calc(sym: str) -> int:
        rows = query_stock_db(
            "SELECT date,open,high,low,close,volume FROM ("
            " SELECT date,open,high,low,close,volume FROM stock_kline"
            " WHERE symbol=? AND adjust_type='qfq' ORDER BY date DESC LIMIT ?"
            ") ORDER BY date", (sym, lookback))
        if len(rows) < 30:
            return 0
        df = pd.DataFrame(rows)
        values = _indicator_rows_from_df(df, index_cols=("date",))
        values = [r for r in values if r.get("date") and r["date"] >= start_date]
        for row in values:
            row["symbol"] = sym
            row["adjust_type"] = "qfq"
        return save_stock_indicators(values) if values else 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_calc, symbol): symbol for symbol in symbols}
        done_count = 0
        for future in as_completed(futures):
            try:
                count = future.result()
                if count:
                    success += 1
                    written += count
            except Exception:
                pass
            done_count += 1
            if done_count % 500 == 0 or done_count == len(symbols):
                print(f"  incremental indicators: {done_count}/{len(symbols)} "
                      f"ok={success} rows={written}, {int(time.time() - started)}s",
                      flush=True)
    return written


# ── 板块全量K线 + 板块指标 ──


def _sector_codes() -> list[tuple[str, str | None]]:
    """板块代码列表 (优先本地 sector_basic, 无数据时网络拉取)"""
    rows = query_sector_db("SELECT sector_code, sector_name FROM sector_basic")
    if rows:
        return [(r["sector_code"], r["sector_name"]) for r in rows]
    import asyncio

    from ..tools.sector_data import get_sector_list

    items = asyncio.run(get_sector_list("concept")) + asyncio.run(get_sector_list("industry"))
    return [(i["sector_code"], i.get("sector_name")) for i in items]


def _sector_kline_full(code: str, name: str | None, limit: int) -> list[dict]:
    from ..tools.sector_data import _sector_kline_net_sync

    return _sector_kline_net_sync(code, limit=limit, klt=101, sector_name=name)


def download_sector_full_history(workers: int = 8, limit: int = 5000,
                                 dry_run: bool = False) -> int:
    """全量板块K线 -> sector_kline (东财单源, 带熔断; ~580 板块) """
    if dry_run:
        print(f"[DRY-RUN] step sector-kline: download full history for all sectors "
              f"(eastmoney single-source, limit={limit}, workers={workers})")
        return 0
    codes = _sector_codes()
    print(f"step sector-kline: {len(codes)} sectors, limit={limit} ...", flush=True)
    start = time.time()
    total = 0
    failed = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_sector_kline_full, c, n, limit): c for c, n in codes}
        done_count = 0
        for fut in as_completed(futures):
            code = futures[fut]
            try:
                bars = fut.result()
            except Exception as e:
                failed.append(code)
                print(f"  sector {code} FAILED: {e}", flush=True)
                continue
            if not bars:
                failed.append(code)
                continue
            save_sector_kline(bars)
            total += len(bars)
            done_count += 1
            if done_count % 100 == 0:
                print(f"  sector-kline: {done_count}/{len(codes)}, +{total} bars, "
                      f"{int(time.time() - start)}s", flush=True)
    print(f"step sector-kline: done, +{total} bars in {int(time.time() - start)}s, "
          f"failed={len(failed)} {failed[:10]}", flush=True)
    return total


def compute_all_sector_indicators(workers: int = 8, dry_run: bool = False) -> int:
    """从 sector_kline 计算板块技术指标 -> sector_indicators"""
    if dry_run:
        print("[DRY-RUN] step sector-indicators: compute indicators for all sectors "
              "-> sector_indicators")
        return 0
    codes = [r["sector_code"] for r in query_sector_db("SELECT sector_code FROM sector_basic")]
    if not codes:
        print("step sector-indicators: no sectors in sector_basic, skip.")
        return 0
    if dry_run:
        print(f"[DRY-RUN] step sector-indicators: compute indicators for {len(codes)} sectors "
              f"-> sector_indicators")
        return 0
    print(f"step sector-indicators: {len(codes)} sectors ...", flush=True)
    start = time.time()
    success = 0

    def _calc(code: str) -> int:
        rows = query_sector_db(
            "SELECT trade_date AS date, open, high, low, close, volume, turnover_rate "
            "FROM sector_kline WHERE sector_code=? ORDER BY trade_date", (code,))
        if len(rows) < 30:
            return 0
        df = pd.DataFrame(rows)
        ind_rows = _indicator_rows_from_df(df, index_cols=("date",))
        if not ind_rows:
            return 0
        for r in ind_rows:
            r["sector_code"] = code
            r["trade_date"] = r.pop("date")
        save_sector_indicators(ind_rows)
        return len(ind_rows)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_calc, c): c for c in codes}
        done_count = 0
        for fut in as_completed(futures):
            try:
                if fut.result() > 0:
                    success += 1
            except Exception:
                pass
            done_count += 1
            if done_count % 100 == 0 or done_count == len(codes):
                print(f"  sector-indicators: {done_count}/{len(codes)} ok={success}, "
                      f"{int(time.time() - start)}s", flush=True)
    print(f"step sector-indicators: done, {success} sectors cached in "
          f"{int(time.time() - start)}s", flush=True)
    return success


# ═══════════════════ 重建主流程 ═══════════════════


def rebuild_full_data(force: bool = False, workers: int = 8,
                      skip_spot: bool = False, skip_kline: bool = False,
                      skip_rank: bool = False, skip_combined: bool = False,
                      skip_indicators: bool = False,
                      with_sectors: bool = False, sector_limit: int = 5000,
                      dry_run: bool = False) -> int:
    """步骤化全量重建 (断点续传 + dry-run 预览, 不下载不写库)"""
    if force and not dry_run:
        for db_path in (get_stock_db(), get_sector_db()):
            if os.path.exists(db_path):
                print(f"deleting old database: {db_path}", flush=True)
                os.unlink(db_path)
                for suffix in ("-wal", "-shm"):
                    side = db_path + suffix
                    if os.path.exists(side):
                        os.unlink(side)

    if dry_run:
        print("=" * 60)
        print("[DRY-RUN] rebuild plan (no network / no writes):")
        print("=" * 60)
    else:
        init_all()  # 幂等建表
    steps = []
    if not skip_spot:
        steps.append(("spot", lambda: step_spot(dry_run=dry_run)))
    if not skip_kline:
        steps.append(("kline", lambda: step_kline(workers=workers, dry_run=dry_run)))
    if not skip_rank:
        steps.append(("guba", lambda: step_guba_rank(workers=workers, dry_run=dry_run)))
    if not skip_combined:
        steps.append(("combined", lambda: step_combined(dry_run=dry_run)))
    if not skip_indicators:
        steps.append(("indicators",
                      lambda: compute_all_stock_indicators(workers=workers, dry_run=dry_run)))
    if with_sectors:
        steps.append(("sector-kline",
                      lambda: download_sector_full_history(workers=workers,
                                                           limit=sector_limit, dry_run=dry_run)))
        steps.append(("sector-indicators",
                      lambda: compute_all_sector_indicators(workers=workers, dry_run=dry_run)))

    if not dry_run and not wait_for_internet(timeout_seconds=120):
        print("no internet, abort.", flush=True)
        return 1

    overall_start = time.time()
    for name, fn in steps:
        print("=" * 60)
        print(f"STEP {name}")
        print("=" * 60, flush=True)
        fn()

    if not dry_run:
        with sqlite3.connect(get_stock_db()) as conn:
            for table in ("stock_basic", "stock_kline", "daily_stock_info",
                          "stock_popularity_rank", "stock_daily_combined"):
                print(f"final count {table}: "
                      f"{conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]}")
        print(f"rebuild finished in {int(time.time() - overall_start)}s.", flush=True)
    else:
        print("[DRY-RUN] done. Nothing was downloaded or written.")
    return 0


# ═══════════════════ 回填 ═══════════════════


def _date_symbol_counts(table: str, date_col: str, start: str, end: str) -> dict[str, int]:
    rows = query_stock_db(
        f"SELECT {date_col} AS d, COUNT(DISTINCT symbol) AS cnt FROM {table} "
        f"WHERE {date_col} >= ? AND {date_col} <= ? GROUP BY {date_col}", (start, end))
    return {r["d"]: r["cnt"] for r in rows}


def _reference_count(table: str, date_col: str) -> int:
    rows = query_stock_db(
        f"SELECT MAX(cnt) AS m FROM ("
        f"  SELECT {date_col} AS d, COUNT(DISTINCT symbol) AS cnt FROM {table} "
        f"  WHERE {date_col} >= date('now', '-30 days') GROUP BY {date_col})")
    return (rows[0]["m"] or 5000) if rows else 5000


def get_missing_trade_dates(table: str, date_col: str, start: str, end: str) -> list[str]:
    """[start, end] 内缺失的交易日 (有数据股票数 < 基准90%)"""
    try:
        all_trade_dates = load_trade_dates()
    except Exception as e:
        print(f"警告: 无法获取交易日历 ({e})，将用周一到周五近似", flush=True)
        all_trade_dates = None

    date_counts = _date_symbol_counts(table, date_col, start, end)
    ref_count = _reference_count(table, date_col)

    missing = []
    cur = datetime.strptime(start, "%Y-%m-%d").date()
    end_d = datetime.strptime(end, "%Y-%m-%d").date()
    while cur <= end_d:
        cur_str = cur.strftime("%Y-%m-%d")
        if all_trade_dates is not None:
            is_trade = cur_str in all_trade_dates
        else:
            is_trade = cur.weekday() < 5
        if is_trade:
            have = date_counts.get(cur_str, 0)
            if have < ref_count * 0.9:
                missing.append(cur_str)
        cur += timedelta(days=1)

    if missing:
        print(f"基准单日股票数: {ref_count}", flush=True)
        for d in missing:
            print(f"  缺失 {d}: 仅 {date_counts.get(d, 0)}/{ref_count} 只股票有数据", flush=True)
    return missing


def _estimate_lmt(start_date: str) -> int:
    """估算覆盖 start_date 至今需要的K线根数 (交易日数 × 1.5 + 20 缓冲)"""
    try:
        trade_dates = load_trade_dates()
        today = datetime.now().strftime("%Y-%m-%d")
        n = sum(1 for d in trade_dates if start_date <= d <= today)
        return min(max(int(n * 1.5) + 20, 30), 5000)
    except Exception:
        days = (datetime.now() - datetime.strptime(start_date, "%Y-%m-%d")).days
        return min(max(int(days * 1.1) + 20, 30), 5000)


def backfill_history(start: str, end: str, symbols: list[str] | None = None,
                     max_workers: int = 8, dry_run: bool = False) -> int:
    """补齐 stock_kline 缺失日期的K线 (INSERT OR REPLACE 幂等)"""
    if dry_run:
        n_sym = len(symbols) if symbols else "all"
        print(f"[DRY-RUN] backfill history: {start} ~ {end}, symbols={n_sym}, "
              f"workers={max_workers}")
        return 0
    if symbols is None:
        symbols = _get_symbols()
    missing_dates = get_missing_trade_dates("stock_kline", "date", start, end)
    if not missing_dates:
        print(f"stock_kline 在 {start} ~ {end} 范围内没有缺失的交易日。")
        return 0
    print(f"发现 {len(missing_dates)} 个缺失交易日: {missing_dates[:10]}...", flush=True)

    lmt = _estimate_lmt(min(missing_dates))
    print(f"每股取最近 {lmt} 根K线 (INSERT OR REPLACE, 已有数据幂等覆盖)", flush=True)

    total_rows = 0
    completed = 0
    success = 0
    failed = 0

    def _fetch(sym: str):
        return fetch_kline_history(sym, "qfq", limit=lmt)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_symbol = {executor.submit(_fetch, s): s for s in symbols}
        for future in as_completed(future_to_symbol):
            symbol = future_to_symbol[future]
            try:
                bars = future.result()
                if bars:
                    save_stock_kline(bars)
                    total_rows += len(bars)
                    success += 1
            except Exception as e:
                failed += 1
                print(f"  {symbol}: 失败 ({e})", flush=True)
            completed += 1
            if completed % 200 == 0 or completed == len(symbols):
                print(f"  进度: {completed}/{len(symbols)} 成功={success} 失败={failed} "
                      f"写入行={total_rows}", flush=True)

    print(f"\nstock_kline 补全完成: 写入 {total_rows} 行 ({success} 只股票成功)")
    return total_rows


def backfill_rank(start: str, end: str, max_workers: int = 8,
                  dry_run: bool = False) -> int:
    """补齐 stock_popularity_rank 缺失日期 (股吧年文件, 只覆盖滚动一年)"""
    if dry_run:
        print(f"[DRY-RUN] backfill rank: {start} ~ {end}, workers={max_workers} "
              "(guba yearly files, rolling one year)")
        return 0
    missing_dates = get_missing_trade_dates("stock_popularity_rank", "trade_date", start, end)
    if not missing_dates:
        print(f"stock_popularity_rank 在 {start} ~ {end} 范围内没有缺失的交易日。")
        return 0
    print(f"发现 {len(missing_dates)} 个缺失交易日: {missing_dates[:10]}...", flush=True)

    symbols = _get_symbols()
    missing_date_set = set(missing_dates)

    total_rows = 0
    completed = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_guba_rank_history, s): s for s in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                recs = [r for r in future.result()
                        if r.get("trade_date") in missing_date_set]
                save_popularity_rank(recs, replace=False)
                total_rows += len(recs)
            except Exception as e:
                failed += 1
                print(f"  {symbol}: 失败 ({e})", flush=True)
            completed += 1
            if completed % 200 == 0 or completed == len(symbols):
                print(f"  进度: {completed}/{len(symbols)} 失败={failed} 写入行={total_rows}",
                      flush=True)

    print(f"\nstock_popularity_rank 补全完成: 写入 {total_rows} 行, 失败 {failed}")
    return total_rows


def rebuild_combined(dry_run: bool = False) -> int:
    """用 history + rank + spot 全量重建 stock_daily_combined"""
    if dry_run:
        print("[DRY-RUN] 将重建 stock_daily_combined "
              "(stock_kline JOIN stock_popularity_rank + daily_stock_info)。")
        return 0
    kline_rows = build_combined_from_history()
    spot_rows = upsert_combined_spot()
    print(f"stock_daily_combined 重建完成: kline-join={kline_rows}, spot={spot_rows}")
    return kline_rows + spot_rows


def backfill_data(start: str | None = None, end: str | None = None,
                  do_history: bool = True, do_rank: bool = True, do_combined: bool = True,
                  symbols: list[str] | None = None,
                  max_workers: int = 8, dry_run: bool = False) -> int:
    """缺口检测补齐入口"""
    end = end or _today()
    if dry_run:
        print(f"[DRY-RUN] backfill plan: {start or end} ~ {end}, "
              f"history={do_history}, rank={do_rank}, combined={do_combined}")
        return 0
    if (do_history or do_rank) and not start:
        rows = query_stock_db(
            "SELECT date FROM stock_kline WHERE adjust_type='qfq' AND date >= date('now', '-30 days') "
            "GROUP BY date ORDER BY COUNT(DISTINCT symbol) DESC, date DESC LIMIT 1")
        start = rows[0]["date"] if rows else end
    print(f"补数据日期范围: {start} ~ {end}")

    total = 0
    if do_history:
        print("=" * 60)
        print("步骤1: 补全 stock_kline (K线数据)")
        print("=" * 60, flush=True)
        total += backfill_history(start, end, symbols=symbols, max_workers=max_workers,
                                  dry_run=dry_run)
        print()
    if do_rank:
        print("=" * 60)
        print("步骤2: 补全 stock_popularity_rank (股吧年文件)")
        print("=" * 60, flush=True)
        total += backfill_rank(start, end, max_workers=max_workers, dry_run=dry_run)
        print()
    if do_combined:
        print("=" * 60)
        print("步骤3: 重建 stock_daily_combined")
        print("=" * 60, flush=True)
        total += rebuild_combined(dry_run=dry_run)
    return total


# ═══════════════════ 晚间采集 ═══════════════════


def save_rank_snapshot(rows: list[dict], trade_date: str, capture_time: str) -> int:
    """xuangu 快照行 -> stock_popularity_rank (source='xuangu') + combined 排名列"""
    rank_rows = []
    for r in rows:
        match = re.search(r"(\d{6})", str(r.get("SECURITY_CODE") or ""))
        symbol = match.group(1) if match else None
        rank = r.get("POPULARITY_RANK")
        if not symbol or rank is None:
            continue
        try:
            rank_val = int(float(rank))
        except (ValueError, TypeError):
            continue
        rank_rows.append({
            "trade_date": trade_date,
            "symbol": symbol,
            "rank": rank_val,
            "rank_time": capture_time,
            "source": "xuangu",
        })
    written = save_popularity_rank(rank_rows, replace=True)
    if is_trade_day(trade_date):
        upsert_combined_rank(trade_date)
    return written


def save_spot_snapshot(capture_time: str, trade_date: str) -> int:
    """全市场 spot -> daily_stock_info + stock_basic 刷新 + combined"""
    spot_rows = fetch_full_spot(verbose=True)
    if not spot_rows:
        raise RuntimeError("fetch_full_spot returned no rows")
    list_rows = _stocks_from_spot(spot_rows)
    save_stock_basic(list_rows)
    written = save_daily_stock_info(trade_date, capture_time, spot_rows)
    upsert_combined_spot()
    return written


def save_recent_klines(workers: int = 8, limit: int = 5) -> int:
    """全市场最近 N 根日K -> stock_kline (增量, INSERT OR REPLACE)"""
    symbols = _get_symbols()
    start = time.time()
    total_bars = 0
    failed = 0

    def _fetch(sym: str):
        return fetch_kline_history(sym, "qfq", limit=limit)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_fetch, s): s for s in symbols}
        for fut in as_completed(futures):
            try:
                bars = fut.result()
            except Exception:
                failed += 1
                continue
            if bars:
                save_stock_kline(bars)
                total_bars += len(bars)
    print(f"kline incremental: {total_bars} bars, failed={failed}, "
          f"{int(time.time() - start)}s", flush=True)
    return total_bars


def daily_capture(skip_non_trading_day: bool = True, save_spot: bool = True,
                  save_kline: bool = True, save_indicators: bool = True,
                  page_size: int = 500, max_pages: int | None = None,
                  workers: int = 8, dry_run: bool = False) -> int:
    """晚间采集: xuangu 排名 + spot 快照 + 最近K线增量 + 指标缓存"""
    now = datetime.now()
    capture_time = now.strftime("%Y-%m-%d %H:%M:%S")
    date_part = now.strftime("%Y-%m-%d")

    # dry-run 必须在一切网络调用(含交易日历)之前短路: 只打印计划, 不联网不写库
    if dry_run:
        print("[DRY-RUN] daily capture plan:")
        print(f"  - xuangu rankings (page_size={page_size}, max_pages={max_pages})")
        if save_spot:
            print("  - full-market spot snapshot -> daily_stock_info + stock_basic")
        if save_kline:
            print("  - recent klines (limit=5) -> stock_kline")
        if save_indicators:
            print("  - compute stock indicators -> stock_indicators")
        if skip_non_trading_day:
            print("  - skip if not a trading day")
        print("[DRY-RUN] Nothing was downloaded or written.")
        return 0

    if not wait_for_internet(timeout_seconds=120):
        raise RuntimeError("Network connection not available after 120 seconds.")

    if skip_non_trading_day and not is_trade_day(now.date()):
        message = f"{capture_time} capture: skipped, {date_part} is not a trading day"
        print(message, flush=True)
        return 0

    rows = fetch_xuangu_rankings(page_size=page_size, max_pages=max_pages, verbose=True)
    if not rows:
        raise RuntimeError("no rows returned from Eastmoney xuangu API")

    init_all()  # 幂等建表保险

    rank_written = save_rank_snapshot(rows, date_part, capture_time)
    spot_message = ""
    if save_spot:
        spot_written = save_spot_snapshot(capture_time, date_part)
        spot_message = f", spot={spot_written}"
    kline_message = ""
    if save_kline:
        bars = save_recent_klines(workers=workers)
        kline_message = f", kline_bars={bars}"
    indicators_message = ""
    if save_indicators:
        print("正在计算并缓存全部股票的技术指标...", flush=True)
        try:
            compute_all_stock_indicators(workers=max(workers, 10))
            indicators_message = ", indicators=cached"
        except Exception as e:
            indicators_message = f", indicators=failed({e})"
            print(f"指标缓存失败: {e}", flush=True)

    message = (f"{capture_time} capture: rank={rank_written}"
               f"{spot_message}{kline_message}{indicators_message}")
    print(message, flush=True)
    return rank_written


# ═══════════════════ 清理 ═══════════════════


def cleanup_database(dry_run: bool = False, vacuum: bool = True) -> int:
    """清理: 报告表规模 + 可选 VACUUM + 清理重建进度表过期步骤"""
    removed = 0
    for db_path, name in ((get_stock_db(), "stock"), (get_sector_db(), "sector")):
        if not os.path.exists(db_path):
            continue
        size_mb = os.path.getsize(db_path) / 1024 / 1024
        print(f"[{name}] {db_path} ({size_mb:.1f} MB)")
        with sqlite3.connect(db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            for (t,) in tables:
                try:
                    cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    print(f"    {t}: {cnt} rows")
                except Exception:
                    pass
        if vacuum and not dry_run:
            with sqlite3.connect(db_path) as conn:
                conn.execute("VACUUM")
            print(f"[{name}] VACUUM done")

    # 清理重建进度表中除 kline/guba 外的历史步骤 (断点续传只关心这两步)
    if not dry_run:
        for step in ("spot", "combined", "indicators", "sector-kline", "sector-indicators"):
            query_stock_db("DELETE FROM rebuild_progress WHERE step=?", (step,))
        print("rebuild_progress 已清理历史步骤 (仅保留 kline/guba)")
    return removed
