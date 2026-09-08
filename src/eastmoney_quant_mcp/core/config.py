"""User configuration with environment variables taking precedence."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def config_path() -> Path:
    explicit = os.environ.get("EASTMONEY_CONFIG")
    if explicit:
        return Path(explicit).expanduser()
    return Path.home() / ".eastmoney-quant" / "config.toml"


def _read_simple_toml(path: Path) -> dict[str, str]:
    """极简 TOML 读取: 仅支持顶层 key = "value" (带行内注释剔除)。

    完整配置需求(分节/多行)出现时应改用标准库 tomllib (Py3.11+)。
    """
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value.startswith(('"', "'")):
            quote = value[0]
            end = value.find(quote, 1)
            value = value[1:end] if end != -1 else value.lstrip(quote)
        else:
            # 裸值: 剔除行内注释 (值内不含 #, 路径/目录名场景足够)
            hash_pos = value.find(" #")
            if hash_pos != -1:
                value = value[:hash_pos].strip()
        values[key.strip()] = value
    return values


def _env_path(name: str, fallback: Path) -> Path:
    """环境变量路径; 空字符串视为未设置, 回退 fallback。"""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return fallback
    return Path(raw).expanduser()


@dataclass(frozen=True)
class Settings:
    data_root: Path
    stock_dir: Path
    sector_dir: Path
    config_file: Path


def _default_dirs() -> tuple[Path, Path, Path]:
    """Windows keeps the historical Desktop layout; Linux/macOS use hidden app dirs (headless-friendly)."""
    if os.name == "nt":
        root = Path.home() / "Desktop"
        return root, root / "股票信息", root / "分析板块"
    root = Path.home() / ".eastmoney-quant" / "data"
    return root, root / "stocks", root / "sectors"


def get_settings() -> Settings:
    values = _read_simple_toml(config_path())
    default_root, default_stock, default_sector = _default_dirs()
    toml_root = values.get("data_root", "").strip()
    root = _env_path("EASTMONEY_DATA_DIR", Path(toml_root).expanduser() if toml_root else default_root)
    if toml_root or "EASTMONEY_DATA_DIR" in os.environ:
        default_stock, default_sector = root / "股票信息", root / "分析板块"

    def _dir(env_name: str, toml_key: str, default: Path) -> Path:
        toml_value = values.get(toml_key, "").strip()
        fallback = Path(toml_value).expanduser() if toml_value else default
        return _env_path(env_name, fallback)

    stock_dir = _dir("EASTMONEY_STOCK_DATA_DIR", "stock_data_dir", default_stock)
    sector_dir = _dir("EASTMONEY_SECTOR_DATA_DIR", "sector_data_dir", default_sector)
    return Settings(root, stock_dir, sector_dir, config_path())
