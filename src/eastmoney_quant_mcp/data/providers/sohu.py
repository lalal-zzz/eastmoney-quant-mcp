"""
搜狐证券数据源

- 个股日 K: q.stock.sohu.com/hisHq (一次可拉全上市历史, 0.3s/6年)
- 板块列表: q.stock.sohu.com/cn/bk.shtml (GBK HTML, 行业+概念名单)
- 板块成分: q.stock.sohu.com/cn/bk_XXXX.shtml (GBK HTML, 仅代码+名称)

注意: 搜狐日K为**不复权**数据, 仅作为腾讯/东财均不可用时的最后兜底,
或 adjust="" 时的常规降级源。单位: volume 手, amount 万元(转元 ×10000)。
"""

import re
import threading

from ..util import TtlCache
import time

from ..network import (
    http_get,
    http_get_text,
    mark_provider_fail,
    mark_provider_ok,
)

PROVIDER = "sohu"

HISHQ_URL = "https://q.stock.sohu.com/hisHq"
BK_LIST_URL = "https://q.stock.sohu.com/cn/bk.shtml"
BK_PAGE_URL = "https://q.stock.sohu.com/cn/bk_{code}.shtml"

_SOHU_HEADERS = {"Referer": "https://q.stock.sohu.com/"}
# 搜狐 WAF 拒绝新版 edge 指纹(500/503), 实测放行 edge99 / safari17_0
_SOHU_IMPERSONATE = "edge99"

_MEMBER_RE = re.compile(r'/cn/(\d{6})/index\.shtml"[^>]*>([^<]+)</a>')
_BK_LINK_RE = re.compile(r'href="bk_(\d{4,6})\.shtml"[^>]*>([^<]+)<')

_BK_INDEX_TTL = 24 * 3600


def _f(val) -> float | None:
    try:
        v = float(str(val).replace("%", "").replace(",", ""))
        return v
    except (TypeError, ValueError):
        return None


# ── 个股日 K ──


def fetch_stock_kline_daily(symbol: str, start_date: str = None,
                            end_date: str = None) -> list[dict]:
    """
    搜狐日K(不复权)。返回行按时间升序, 字段与东财对齐:
    date/symbol/open/high/low/close/volume(手)/amount(元)/amplitude/
    change_pct/change_amount/turnover_rate。失败(网络)返回 []。
    """
    from ..network import provider_available

    if not provider_available(PROVIDER):
        return []

    bare = str(symbol).strip().lower()[-6:]
    # 搜狐拒绝远期日期(end>今天会返回错误页), 上限截到今天
    import datetime as _dt

    today = _dt.date.today().strftime("%Y%m%d")
    start = (start_date or "19900101").replace("-", "")
    end = min((end_date or today).replace("-", ""), today)
    params = {
        "code": f"cn_{bare}", "start": start, "end": end,
        "stat": "1", "order": "A", "period": "d",  # order=A 时间升序
    }
    payload = http_get(HISHQ_URL, params=params, retries=3, timeout=20,
                       extra_headers=_SOHU_HEADERS, impersonate=_SOHU_IMPERSONATE, use_cookies=False)
    if payload is None:
        mark_provider_fail(PROVIDER)
        return []
    mark_provider_ok(PROVIDER)
    return _parse_hishq(payload, bare)


def _parse_hishq(payload, symbol: str) -> list[dict]:
    """解析 hisHq 响应(时间升序), amount 万元→元, 振幅按前收盘计算"""
    if not isinstance(payload, list) or not payload:
        return []
    box = payload[0]
    if box.get("status") != 0 or not box.get("hq"):
        return []

    items = []
    prev_close = None
    for row in box["hq"]:
        # [date, open, close, change, pct%, low, high, volume(手), amount(万), turnover%, ...]
        if not isinstance(row, (list, tuple)) or len(row) < 9:
            continue
        open_ = _f(row[1])
        close = _f(row[2])
        change_amount = _f(row[3])
        low = _f(row[5])
        high = _f(row[6])
        volume = _f(row[7])
        amount_wan = _f(row[8])
        turnover_rate = _f(row[9]) if len(row) > 9 else None
        if close is None:
            continue
        item = {
            "date": str(row[0]), "symbol": symbol,
            "open": open_, "high": high, "low": low, "close": close,
            "volume": volume,
            "amount": amount_wan * 10000 if amount_wan is not None else None,
            "change_pct": _f(row[4]),
            "change_amount": change_amount,
            "turnover_rate": turnover_rate,
        }
        prev = prev_close if prev_close is not None else (
            close - change_amount if change_amount is not None else None
        )
        if None not in (high, low, prev) and prev:
            item["amplitude"] = round((high - low) / prev * 100, 4)
        else:
            item["amplitude"] = None
        items.append(item)
        prev_close = close
    return items


# ── 板块列表 + 成分股(HTML) ──


def _parse_member_html(html: str, sector_code: str) -> list[dict]:
    """解析板块详情页成分股表格(仅代码+名称), 去重并过滤导航链接"""
    # 导航栏(页面头部, 先于成分股表格出现)有同形链接, 其文字是栏目名而非股票名
    nav_names = {"个 股", "指 数", "排 行", "板 块", "自选股", "首 页"}
    items = []
    seen = set()
    for m in _MEMBER_RE.finditer(html):
        stock_code, stock_name = m.group(1), m.group(2).strip()
        if not stock_name or stock_name in nav_names or stock_code in seen:
            continue
        seen.add(stock_code)
        items.append({
            "sector_code": sector_code,
            "stock_code": stock_code,
            "stock_name": stock_name,
        })
    return items


def _fetch_bk_index() -> dict[str, str] | None:
    text = http_get_text(BK_LIST_URL, retries=2, timeout=25, encoding="gbk",
                         extra_headers=_SOHU_HEADERS, impersonate=_SOHU_IMPERSONATE, use_cookies=False)
    if text is None:
        mark_provider_fail(PROVIDER)
        return None
    mark_provider_ok(PROVIDER)

    index = {}
    for m in _BK_LINK_RE.finditer(text):
        code, name = m.group(1), m.group(2).strip()
        if name:
            index.setdefault(name, code)
    return index or None


_bk_index_cache = TtlCache(_BK_INDEX_TTL)


def get_name_bk_index(refresh: bool = False) -> dict[str, str]:
    """{板块名: 搜狐 bk 数字代码}, 来自 bk.shtml 服务端渲染名单, 缓存 24h"""
    return _bk_index_cache.get(_fetch_bk_index, refresh=refresh) or {}


def fetch_sector_members(bk_code: str, sector_code: str = "",
                         quote_fetcher=None) -> list[dict]:
    """
    搜狐板块成分股(仅代码+名称)。quote_fetcher 传入腾讯 fetch_quote_batch
    等函数可为成分股补充实时行情字段。失败(网络)返回 []。
    """
    from ..network import provider_available

    if not provider_available(PROVIDER):
        return []

    code = str(bk_code).strip().lower().replace("bk_", "")
    text = http_get_text(BK_PAGE_URL.format(code=code), retries=2, timeout=20,
                         encoding="gbk", extra_headers=_SOHU_HEADERS,
                         impersonate=_SOHU_IMPERSONATE, use_cookies=False)
    if text is None:
        mark_provider_fail(PROVIDER)
        return []
    mark_provider_ok(PROVIDER)

    unique = _parse_member_html(text, sector_code)

    if quote_fetcher and unique:
        try:
            quotes = quote_fetcher([
                ("sh" if q["stock_code"].startswith("6") else
                 "bj" if q["stock_code"].startswith(("8", "9", "4")) else "sz") + q["stock_code"]
                for q in unique
            ])
            by_code = {q.get("raw_code"): q for q in quotes}
            for it in unique:
                q = by_code.get(it["stock_code"]) or {}
                it.update({
                    "latest_price": q.get("latest_price"),
                    "change_pct": q.get("change_pct"),
                    "change_amount": q.get("change_amount"),
                    "volume": q.get("volume"),
                    "turnover": q.get("amount"),
                    "turnover_rate": q.get("turnover_rate"),
                    "high": q.get("high"),
                    "low": q.get("low"),
                    "open_today": q.get("open"),
                    "close_yesterday": q.get("pre_close"),
                    "pe_dynamic": q.get("pe_dynamic"),
                    "amplitude": None, "volume_ratio": None, "pb": None,
                })
        except Exception:
            pass
    return unique
