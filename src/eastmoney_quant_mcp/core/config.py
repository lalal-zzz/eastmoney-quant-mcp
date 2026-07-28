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
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


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
    root = Path(os.environ.get("EASTMONEY_DATA_DIR", values.get("data_root", default_root))).expanduser()
    if "data_root" in values or "EASTMONEY_DATA_DIR" in os.environ:
        default_stock, default_sector = root / "股票信息", root / "分析板块"
    stock_dir = Path(os.environ.get("EASTMONEY_STOCK_DATA_DIR", values.get("stock_data_dir", default_stock))).expanduser()
    sector_dir = Path(os.environ.get("EASTMONEY_SECTOR_DATA_DIR", values.get("sector_data_dir", default_sector))).expanduser()
    return Settings(root, stock_dir, sector_dir, config_path())
