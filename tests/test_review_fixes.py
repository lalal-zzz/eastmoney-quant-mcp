"""回归测试: code-review 修复项的行为锁定。"""

import os
import sys
from pathlib import Path

import pytest

from eastmoney_quant_mcp.data import network
from eastmoney_quant_mcp.core import config


# ── 熔断器: 空数据不应计入网络失败 ──

@pytest.fixture(autouse=True)
def _reset_health():
    network.mark_provider_ok(network.EM_KLINE)
    network._provider_fail_count.pop(network.EM_KLINE, None)
    network._provider_cooldown_until.pop(network.EM_KLINE, None)
    yield
    network.mark_provider_ok(network.EM_KLINE)


def test_em_kline_empty_data_does_not_trip_breaker(monkeypatch):
    """host 返回 HTTP 200 但 data 为空(退市股) → 返回 None 且不熔断。"""
    monkeypatch.setattr(network, "http_get",
                        lambda *a, **k: {"code": 0, "data": None})
    for _ in range(5):
        assert network.fetch_em_kline({"secid": "1.600000"}) is None
    assert network.provider_available(network.EM_KLINE)


def test_em_kline_network_failure_trips_breaker(monkeypatch):
    """host 连接失败(http_get 返回 None) → 连续 3 次进入冷却。"""
    monkeypatch.setattr(network, "http_get", lambda *a, **k: None)
    for _ in range(3):
        assert network.fetch_em_kline({"secid": "1.600000"}) is None
    assert not network.provider_available(network.EM_KLINE)
    # 冷却期内不发请求
    monkeypatch.setattr(network, "http_get",
                        lambda *a, **k: {"code": 0, "data": {"klines": ["x"]}})
    assert network.fetch_em_kline({"secid": "1.600000"}) is None


def test_em_kline_success_resets(monkeypatch):
    monkeypatch.setattr(network, "http_get",
                        lambda *a, **k: {"code": 0, "data": {"klines": ["x"]}})
    assert network.fetch_em_kline({"secid": "1.600000"}) == {"code": 0, "data": {"klines": ["x"]}}
    assert network.provider_available(network.EM_KLINE)


# ── config: 空字符串环境变量回退 default ──

def test_empty_env_vars_fall_back(monkeypatch, tmp_path):
    monkeypatch.setenv("EASTMONEY_DATA_DIR", "")
    monkeypatch.setenv("EASTMONEY_STOCK_DATA_DIR", "")
    monkeypatch.setenv("EASTMONEY_SECTOR_DATA_DIR", "")
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "nonexistent.toml")
    s = config.get_settings()
    assert s.data_root != Path("")            # 不能落到当前目录
    assert s.stock_dir == s.data_root / "股票信息"
    assert s.sector_dir == s.data_root / "分析板块"


def test_toml_inline_comment_stripped(monkeypatch, tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('data_root = "D:/quant/data" # 主数据目录\n', encoding="utf-8")
    monkeypatch.setattr(config, "config_path", lambda: cfg)
    monkeypatch.delenv("EASTMONEY_DATA_DIR", raising=False)
    monkeypatch.delenv("EASTMONEY_STOCK_DATA_DIR", raising=False)
    monkeypatch.delenv("EASTMONEY_SECTOR_DATA_DIR", raising=False)
    s = config.get_settings()
    assert s.data_root == Path("D:/quant/data")   # 不带 " # 主数据目录"


# ── CLI: pattern-backtest 透传失败返回码 ──

def test_cli_backtest_failure_returns_nonzero(monkeypatch):
    from eastmoney_quant_mcp import cli

    def boom(argv):
        raise RuntimeError("cache missing")
    monkeypatch.setattr("eastmoney_quant_mcp.strategies.pattern_backtest.main", boom)
    rc = cli.main(["pattern-backtest", "--cache", "x.csv"])
    assert rc == 1


def test_cli_backtest_help_exit_code(monkeypatch):
    from eastmoney_quant_mcp import cli

    def _help(argv):
        raise SystemExit(0)
    monkeypatch.setattr("eastmoney_quant_mcp.strategies.pattern_backtest.main", _help)
    assert cli.main(["pattern-backtest"]) == 0
