from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

from stock_analysis_mcp.core.config import get_settings


def test_config_file_sets_data_root(monkeypatch):
    temp_path = Path(mkdtemp(dir=Path.cwd()))
    try:
        config = temp_path / "config.toml"
        root = temp_path / "market-data"
        config.write_text(f'data_root = "{root.as_posix()}"\n', encoding="utf-8")
        monkeypatch.setenv("EASTMONEY_CONFIG", str(config))
        settings = get_settings()
        assert settings.data_root == root
        assert settings.stock_dir == root / "股票信息"
    finally:
        rmtree(temp_path)


def test_environment_overrides_config(monkeypatch):
    temp_path = Path(mkdtemp(dir=Path.cwd()))
    try:
        config = temp_path / "config.toml"
        config.write_text('data_root = "ignored"\n', encoding="utf-8")
        override = temp_path / "custom-stock"
        monkeypatch.setenv("EASTMONEY_CONFIG", str(config))
        monkeypatch.setenv("EASTMONEY_STOCK_DATA_DIR", str(override))
        assert get_settings().stock_dir == override
    finally:
        rmtree(temp_path)


def test_new_environment_names_take_precedence(monkeypatch, tmp_path):
    preferred = tmp_path / "preferred"
    legacy = tmp_path / "legacy"
    monkeypatch.setenv("STOCK_ANALYSIS_DATA_DIR", str(preferred))
    monkeypatch.setenv("EASTMONEY_DATA_DIR", str(legacy))
    assert get_settings().data_root == preferred
