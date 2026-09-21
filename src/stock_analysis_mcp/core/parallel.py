"""
core/parallel.py — 统一的线程池并行执行器

项目内多处采用同一模板: ThreadPoolExecutor + as_completed + futures 字典 + 单项
异常隔离 + 周期性进度打印。本模块把该模板收敛为一个生成器, 调用方只需决定
如何处理成功值与异常, 以及如何展示进度。
"""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Iterator, TypeVar

T = TypeVar("T")
R = TypeVar("R")

# 进度回调: (已完成数, 总数) -> None
ProgressFn = Callable[[int, int], None]


def run_parallel(items: list[Any], fn: Callable[[Any], R], *,
                 workers: int = 8,
                 on_progress: ProgressFn | None = None) -> Iterator[tuple[Any, Any]]:
    """对每个 item 并行执行 fn(item), 按完成顺序产出 (item, result_or_exception)。

    - fn 正常返回 → result_or_exception 为返回值
    - fn 抛异常   → result_or_exception 为该异常对象 (单项失败不影响整体)
    - on_progress 非空时, 每完成一项回调一次 (可在回调中按间隔打印)

    用法:
        for item, result in run_parallel(items, fetch, workers=8):
            if isinstance(result, Exception):
                failed.append(item); continue
            consume(result)
    """
    items = list(items)
    total = len(items)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fn, it): it for it in items}
        for done_count, fut in enumerate(as_completed(futures), 1):
            item = futures[fut]
            try:
                result: Any = fut.result()
            except Exception as e:  # noqa: BLE001 — 异常作为结果交给调用方处理
                result = e
            yield item, result
            if on_progress is not None:
                on_progress(done_count, total)


def log_progress(prefix: str = "") -> ProgressFn:
    """生成一个每 200 项打印一次进度的回调 (stderr, 立即刷新)。"""
    state = {"count": 0}

    def _log(done: int, total: int) -> None:
        state["count"] += 1
        if state["count"] % 200 == 0 or done == total:
            print(f"  {prefix}{done}/{total}", file=sys.stderr, flush=True)

    return _log
