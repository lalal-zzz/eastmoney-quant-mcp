"""
data/storage/paths.py — 数据库路径解析 (懒加载 + 测试重定向)

股票数据库 → STOCK_ANALYSIS_STOCK_DATA_DIR 或 Desktop/股票信息/stock_data.db
板块数据库 → STOCK_ANALYSIS_SECTOR_DATA_DIR 或 Desktop/分析板块/sector_data.db

路径在首次访问时才计算 (不在 import 时触发 mkdir), 保证轻量导入与单元测试
不会创建目录。内部一律通过 get_stock_db() / get_sector_db() / _resolve_path()
取路径, 禁止裸引用 STOCK_DB/SECTOR_DB 常量。
"""

import os
from pathlib import Path

from ...core.config import get_settings

_db_paths_cache: dict[str, str] = {}

# 测试/临时库重定向: 非空时优先生效 (monkeypatch storage.STOCK_DB 等不再影响内部函数)
_path_overrides: dict[str, str | None] = {
    "STOCK_DIR": None, "SECTOR_DIR": None, "STOCK_DB": None, "SECTOR_DB": None,
}


def set_db_paths(stock_db: str | None = None, sector_db: str | None = None) -> None:
    """重定向数据库路径(测试用); 传 None 清除对应重定向。"""
    if stock_db is not None:
        _path_overrides["STOCK_DB"] = stock_db
        _path_overrides["STOCK_DIR"] = str(Path(stock_db).parent)
    else:
        _path_overrides["STOCK_DB"] = None
        _path_overrides["STOCK_DIR"] = None
    if sector_db is not None:
        _path_overrides["SECTOR_DB"] = sector_db
        _path_overrides["SECTOR_DIR"] = str(Path(sector_db).parent)
    else:
        _path_overrides["SECTOR_DB"] = None
        _path_overrides["SECTOR_DIR"] = None


def _ensure_paths() -> None:
    """Compute and cache DB paths on first access."""
    if _db_paths_cache:
        return
    settings = get_settings()
    stock_dir = settings.stock_dir
    sector_dir = settings.sector_dir
    stock_dir.mkdir(parents=True, exist_ok=True)
    sector_dir.mkdir(parents=True, exist_ok=True)
    _db_paths_cache["STOCK_DIR"] = str(stock_dir)
    _db_paths_cache["SECTOR_DIR"] = str(sector_dir)
    _db_paths_cache["STOCK_DB"] = os.path.join(str(stock_dir), "stock_data.db")
    _db_paths_cache["SECTOR_DB"] = os.path.join(str(sector_dir), "sector_data.db")


def _resolve_path(name: str) -> str:
    """优先取重定向路径, 否则懒加载默认路径。"""
    override = _path_overrides.get(name)
    if override:
        return override
    _ensure_paths()
    return _db_paths_cache[name]


def get_stock_db() -> str:
    """Get stock database path (lazy-initialized)."""
    return _resolve_path("STOCK_DB")


def get_sector_db() -> str:
    """Get sector database path (lazy-initialized)."""
    return _resolve_path("SECTOR_DB")
