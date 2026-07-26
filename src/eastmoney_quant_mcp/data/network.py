"""
东方财富 API 网络请求工具

- 使用 curl_cffi 绕过 TLS 指纹检测
- 强制 IPv4 避免 IPv6 连接超时
- 自动从 Edge 浏览器提取 Cookies 提升请求成功率
"""

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
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
            tmp.close()
            shutil.copy2(cookie_path, tmp.name)
            conn = sqlite3.connect(tmp.name)
            rows = conn.execute(
                "SELECT name, encrypted_value FROM cookies "
                "WHERE host_key LIKE '%eastmoney%' OR host_key LIKE '%dfcf%'"
            ).fetchall()
            conn.close()
            os.unlink(tmp.name)
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

    return None


def _load_cookies() -> str | None:
    global _edge_cookies, _edge_cookies_loaded
    if _edge_cookies_loaded:
        return _edge_cookies
    _edge_cookies_loaded = True
    _edge_cookies = _extract_cookies_from_edge()
    return _edge_cookies


def http_get(url: str, params: dict = None, retries: int = 3, timeout: int = 20) -> dict | None:
    """使用 curl_cffi 发起 GET 请求，返回 JSON dict 或 None"""
    full_url = f"{url}?{urlencode(params)}" if params else url
    headers = dict(DEFAULT_HEADERS)
    cookies = _load_cookies()
    if cookies:
        headers["Cookie"] = cookies
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                full_url,
                headers=headers,
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
    headers = dict(DEFAULT_HEADERS)
    cookies = _load_cookies()
    if cookies:
        headers["Cookie"] = cookies

    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                full_url,
                headers=headers,
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
