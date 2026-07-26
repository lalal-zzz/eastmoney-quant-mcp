"""
东方财富 API 网络请求工具

- 使用 curl_cffi 绕过 TLS 指纹检测
- 强制 IPv4 避免 IPv6 连接超时
"""

import json
import os
import re
import socket
import time
from urllib.parse import urlencode

# ── 强制 IPv4 ──
_orig_getaddrinfo = socket.getaddrinfo


def _patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    return _orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)


socket.getaddrinfo = _patched_getaddrinfo

# ── 清除代理 ──
for _key in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
    os.environ[_key] = ""

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


def http_get(url: str, params: dict = None, retries: int = 3, timeout: int = 20) -> dict | None:
    """使用 curl_cffi 发起 GET 请求，返回 JSON dict 或 None"""
    full_url = f"{url}?{urlencode(params)}" if params else url
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                full_url,
                headers=DEFAULT_HEADERS,
                impersonate="edge",
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


def http_get_text(url: str, params: dict = None, retries: int = 3, timeout: int = 20) -> str | None:
    """使用 curl_cffi 发起 GET 请求，返回原始文本"""
    full_url = f"{url}?{urlencode(params)}" if params else url

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                full_url,
                headers=DEFAULT_HEADERS,
                impersonate="edge",
                http_version="v1",
                verify=False,
                timeout=timeout,
                proxies={"http": "", "https": ""},
            )
            if resp.status_code == 200:
                return resp.text
        except Exception:
            pass
        if attempt < retries:
            time.sleep(1.5 * attempt)

    return None


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
