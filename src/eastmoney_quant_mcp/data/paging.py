"""push2 clist 通用分页拉取: 第1页拿 total, 剩余页信号量并发。

stock_data / sector_data / stock_rank 三处原各自实现同一模式,
此处统一为单一实现; 各调用方只提供 取页函数 与 提取函数。
"""
from __future__ import annotations

import asyncio
import math


async def fetch_all_pages(
    fetch_page,
    extract,
    *,
    page_size: int,
    concurrency: int = 16,
    serial_fallback: bool = False,
) -> list[dict]:
    """分页拉取全部记录。

    fetch_page(pn: int) -> payload   同步取页函数, 在线程池执行
    extract(payload) -> (rows, total)  从 payload 提取记录与总数(total 缺失为 0)
    serial_fallback: total 缺失(=0)且首页满页时, 串行向后翻页直到短页
                     (人气排名接口 count 字段常缺失)
    """
    first = await asyncio.to_thread(fetch_page, 1)
    rows, total = extract(first)
    if not rows:
        return []

    if total > len(rows):
        pages = math.ceil(total / page_size)
        sem = asyncio.Semaphore(concurrency)

        async def _page(pn: int) -> list:
            async with sem:
                return extract(await asyncio.to_thread(fetch_page, pn))[0]

        for chunk in await asyncio.gather(*(_page(p) for p in range(2, pages + 1))):
            rows.extend(chunk)
        return rows

    if serial_fallback and len(rows) % page_size == 0:
        page = 2
        while True:
            chunk, _ = extract(await asyncio.to_thread(fetch_page, page))
            if not chunk:
                break
            rows.extend(chunk)
            if len(chunk) < page_size:
                break
            page += 1
    return rows
