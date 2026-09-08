"""data 包内共享的小工具函数 (sync.py / build.py 编排层共用)。"""
from __future__ import annotations

import threading
from datetime import date


def today() -> str:
    """当前日期(每次调用时求值, 避免长驻进程跨天后日期固化)"""
    return date.today().isoformat()


def stocks_from_spot(spots: list[dict]) -> list[dict]:
    """从全市场行情快照提取股票基础信息(代码/名称), 避免 akshare 50+ 页串行拉列表"""
    return [
        {"symbol": s["symbol"], "name": s.get("name") or "",
         "raw_symbol": s.get("raw_code") or s["symbol"]}
        for s in spots if s.get("symbol")
    ]


def safe_float(val) -> float | None:
    """行情 API 数值解析: None/""/"-"/非法值 → None"""
    if val is None or val == "-" or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_em_kline_rows(klines_list, fixed: dict, time_key: str, cols: list[str]) -> list[dict]:
    """东财 push2his klines 逗号串解析: parts[0]=时间列, 其后依次对应 cols。

    短行跳过; "-" / "" → None; 非数值(异常场景)原样保留字符串。
    """
    items = []
    for row_str in klines_list or []:
        parts = row_str.split(",")
        if len(parts) < len(cols) + 1:
            continue
        item = dict(fixed)
        item[time_key] = parts[0].strip()
        for i, c in enumerate(cols, start=1):
            v = parts[i].strip()
            try:
                item[c] = float(v) if v not in ("-", "") else None
            except ValueError:
                item[c] = v
        items.append(item)
    return items


class TtlCache:
    """带 TTL 的进程内缓存 (线程安全): fetcher 失败/空结果时保留旧值。

    fetcher() -> value | None; None 视为获取失败, 返回旧缓存。
    """

    def __init__(self, ttl_seconds: float):
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._value = None
        self._ts = 0.0

    def get(self, fetcher, refresh: bool = False):
        import time
        with self._lock:
            if not refresh and self._value and time.time() - self._ts < self._ttl:
                return self._value
        value = fetcher()
        if value is None:
            with self._lock:
                return self._value
        with self._lock:
            self._value = value
            self._ts = time.time()
        return value
