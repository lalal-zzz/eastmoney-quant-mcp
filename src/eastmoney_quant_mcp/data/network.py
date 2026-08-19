"""
东方财富 API 网络请求工具

- 使用 curl_cffi 绕过 TLS 指纹检测
- 强制 IPv4 避免 IPv6 连接超时
- 自动从 Edge 浏览器提取 Cookies 提升请求成功率
"""

import itertools
import json
import os
import re
import shutil
import socket
import sqlite3
import tempfile
import time
from pathlib import Path
from urllib.parse import urlencode

# ── 强制 IPv4 ──
_orig_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _patched_getaddrinfo

# ── 清除代理 ──
# 清空代理环境变量; 同时设 NO_PROXY=* 覆盖 Windows 注册表系统代理,
# 否则 requests/akshare 会绕过环境变量直接读注册表, 走不稳定的系统代理
for _key in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
    os.environ[_key] = ""
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

from curl_cffi import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

SYMBOL_RE = re.compile(r"(\d{6})$")
SECTOR_CODE_RE = re.compile(r"(?:BK)?(\d{4})$", re.IGNORECASE)

DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://data.eastmoney.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0 Safari/537.36 Edg/120.0.0.0"
    ),
}

# ── Cookie 管理 ──

_edge_cookies: str | None = None
_edge_cookies_loaded: bool = False


def _get_edge_cookie_paths() -> list[str]:
    """Edge 浏览器 Cookie 数据库可能路径"""
    localappdata = os.environ.get("LOCALAPPDATA", "")
    base = Path(localappdata) / "Microsoft" / "Edge" / "User Data"
    candidates = [
        base / "Default" / "Network" / "Cookies",
        base / "Default" / "Cookies",
        base / "Profile 1" / "Network" / "Cookies",
    ]
    return [str(p) for p in candidates if p.exists()]


def _extract_cookies_from_edge() -> str | None:
    """从 Edge 浏览器提取东方财富相关 Cookies"""
    env_cookie = os.environ.get("EASTMONEY_COOKIE")
    if env_cookie:
        return env_cookie

    for cookie_path in _get_edge_cookie_paths():
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp_path = tmp.name
        tmp.close()
        try:
            shutil.copy2(cookie_path, tmp_path)
            conn = sqlite3.connect(tmp_path)
            rows = conn.execute(
                "SELECT name, encrypted_value FROM cookies "
                "WHERE host_key LIKE '%eastmoney%' OR host_key LIKE '%dfcf%'"
            ).fetchall()
            conn.close()
            if rows:
                # Edge 新版可能已不加密, 直接拼接 name=value 格式
                # 若加密则回退到明文环境变量
                pairs = []
                for name, val in rows:
                    try:
                        decoded = val.decode("utf-8", errors="replace")
                        if len(decoded) > 2 and not any(c in decoded[:10] for c in ["\x00", "\x01", "\x10"]):
                            pairs.append(f"{name}={decoded}")
                    except Exception:
                        pass
                if pairs:
                    return "; ".join(pairs)
        except Exception:
            pass
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    return None


def _load_cookies() -> str | None:
    global _edge_cookies, _edge_cookies_loaded
    if _edge_cookies_loaded:
        return _edge_cookies
    _edge_cookies_loaded = True
    _edge_cookies = _extract_cookies_from_edge()
    return _edge_cookies


def http_get(url: str, params: dict = None, retries: int = 3, timeout: int = 20,
             extra_headers: dict = None, impersonate: str = "edge",
             use_cookies: bool = True) -> dict | None:
    """使用 curl_cffi 发起 GET 请求，返回 JSON dict 或 None

    impersonate: TLS 指纹模拟目标。搜狐 WAF 会拒绝新版 edge 指纹但放行
    edge99/safari17_0, 搜狐相关请求需显式传 impersonate="edge99"。
    use_cookies: 携带东财 Cookie(搜狐 WAF 会因域外 Cookie 直接 503,
    搜狐相关请求需传 False)。
    """
    full_url = f"{url}?{urlencode(params)}" if params else url
    headers = dict(DEFAULT_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    if use_cookies:
        cookies = _load_cookies()
        if cookies:
            headers["Cookie"] = cookies
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                full_url,
                headers=headers,
                impersonate=impersonate,
                http_version="v1",
                verify=False,
                timeout=timeout,
                proxies={"http": "", "https": ""},
            )
            if resp.status_code == 200:
                return resp.json()
            last_error = f"HTTP {resp.status_code}"
        except Exception as exc:
            last_error = str(exc)
        if attempt < retries:
            time.sleep(1.5 * attempt)

    return None


def http_get_text(url: str, params: dict = None, retries: int = 3, timeout: int = 20,
                  encoding: str = None, extra_headers: dict = None,
                  impersonate: str = "edge", use_cookies: bool = True) -> str | None:
    """使用 curl_cffi 发起 GET 请求，返回原始文本。

    encoding: 显式指定响应解码(如 GBK 站点 qt.gtimg.cn / sohu / sina);
    为 None 时使用 curl_cffi 自带的 charset 推断。
    """
    full_url = f"{url}?{urlencode(params)}" if params else url
    headers = dict(DEFAULT_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    if use_cookies:
        cookies = _load_cookies()
        if cookies:
            headers["Cookie"] = cookies

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                full_url,
                headers=headers,
                impersonate=impersonate,
                http_version="v1",
                verify=False,
                timeout=timeout,
                proxies={"http": "", "https": ""},
            )
            if resp.status_code == 200:
                if encoding:
                    return resp.content.decode(encoding, errors="replace")
                return resp.text
        except Exception:
            pass
        if attempt < retries:
            time.sleep(1.5 * attempt)

    return None


# ── 数据源健康熔断 ──
# 连续失败的源进入冷却期, 降级链跳过冷却中的源, 避免对已限流的
# 服务商继续重试放大退避(东财 push2his 被封时的典型症状)。

import threading

_HEALTH_LOCK = threading.Lock()
_provider_fail_count: dict[str, int] = {}
_provider_cooldown_until: dict[str, float] = {}
_FAIL_THRESHOLD = 3        # 连续失败次数阈值
_COOLDOWN_SECONDS = 600.0  # 冷却 10 分钟


def mark_provider_ok(name: str) -> None:
    """记录数据源一次成功调用, 清零连续失败计数"""
    with _HEALTH_LOCK:
        _provider_fail_count.pop(name, None)
        _provider_cooldown_until.pop(name, None)


def mark_provider_fail(name: str) -> None:
    """记录数据源一次失败(网络层失败), 达到阈值后进入冷却"""
    with _HEALTH_LOCK:
        count = _provider_fail_count.get(name, 0) + 1
        _provider_fail_count[name] = count
        if count >= _FAIL_THRESHOLD:
            _provider_cooldown_until[name] = time.time() + _COOLDOWN_SECONDS
            _provider_fail_count[name] = 0


def provider_available(name: str) -> bool:
    """数据源是否可用(未处于冷却期)"""
    with _HEALTH_LOCK:
        until = _provider_cooldown_until.get(name)
        return until is None or time.time() >= until


def provider_health_status() -> dict:
    """当前各数据源健康状态(调试用)"""
    with _HEALTH_LOCK:
        now = time.time()
        return {
            name: {"cooldown_remaining": max(0, int(until - now))}
            for name, until in _provider_cooldown_until.items()
            if until > now
        }


# ── K 线接口 host 轮转 ──

KLINE_HOSTS = [
    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://82.push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://73.push2his.eastmoney.com/api/qt/stock/kline/get",
]

# 入口 host 轮转计数器: 并发批量下载时把请求均匀分散到各镜像 host,
# 避免单 host 触发限流(限流会放大重试退避耗时)
_rr_counter = itertools.count()


def rotated(hosts: list) -> list:
    """按全局计数器轮转 host 列表入口"""
    start = next(_rr_counter) % len(hosts)
    return hosts[start:] + hosts[:start]


def try_kline_hosts(params: dict, timeout: int = 15) -> dict | None:
    """K 线接口多 host 轮转重试, 成功返回 payload(data 非空), 全失败返回 None"""
    for host in rotated(KLINE_HOSTS):
        r = http_get(host, params=params, retries=2, timeout=timeout)
        if r and r.get("data"):  # 偶发空 data(null) 时继续尝试下一个 host
            return r
    return None


# ── 东财 K 线熔断包装 ──
# push2his 被封的典型症状: 所有 kline host 连接关闭(clist 正常)。
# 连续 3 次失败后冷却 10 分钟, 期间调用方直接跳过东财走降级链,
# 避免批量下载时对已被限流的服务商放大重试。

EM_KLINE = "em_kline"


def fetch_em_kline(params: dict, timeout: int = 15) -> dict | None:
    """try_kline_hosts + 健康熔断(冷却期直接返回 None 不发请求)"""
    if not provider_available(EM_KLINE):
        return None
    result = try_kline_hosts(params, timeout=timeout)
    if result:
        mark_provider_ok(EM_KLINE)
    else:
        mark_provider_fail(EM_KLINE)
    return result


def normalize_symbol(symbol: str) -> str:
    """将 sh600000 / sz000001 / bj920000 等格式统一为 6 位数字"""
    text = str(symbol).strip().lower()
    match = SYMBOL_RE.search(text)
    if not match:
        raise ValueError(f"无法识别股票代码: {symbol}")
    return match.group(1)


def to_prefixed_symbol(symbol: str) -> str:
    """6 位数字 → sh/sz/bj 前缀格式"""
    symbol = normalize_symbol(symbol)
    if symbol.startswith("6"):
        return f"sh{symbol}"
    if symbol.startswith(("8", "9")):
        return f"bj{symbol}"
    return f"sz{symbol}"


def normalize_sector_code(code: str) -> str:
    """标准化板块代码为 BKxxxx 格式"""
    code = str(code).strip().upper()
    match = SECTOR_CODE_RE.search(code)
    if match:
        return f"BK{match.group(1)}"
    if code.startswith("BK") and len(code) == 6:
        return code
    raise ValueError(f"无法识别板块代码: {code}")
