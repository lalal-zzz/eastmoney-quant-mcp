"""cli.py 入口测试: dry-run 全链路不联网不写库 + 参数解析"""
import os

import pytest

from stock_analysis_mcp import cli


@pytest.fixture(autouse=True)
def _clean_data_dir_env():
    """cli.main 内部会写 STOCK_ANALYSIS_DATA_DIR, 测试后必须还原, 否则污染 config 测试"""
    saved = os.environ.get("STOCK_ANALYSIS_DATA_DIR")
    yield
    if saved is None:
        os.environ.pop("STOCK_ANALYSIS_DATA_DIR", None)
    else:
        os.environ["STOCK_ANALYSIS_DATA_DIR"] = saved


@pytest.fixture(autouse=True)
def _no_net(monkeypatch):
    """任何网络入口被调用都直接炸 -> 证明 dry-run 分支完全短路未触网"""
    import stock_analysis_mcp.data.build as build

    def boom(*a, **k):
        raise AssertionError("network touched in dry-run")

    monkeypatch.setattr(build, "wait_for_internet", boom)
    monkeypatch.setattr(build, "fetch_xuangu_rankings", boom)
    monkeypatch.setattr(build, "fetch_full_spot", boom)
    monkeypatch.setattr(build, "fetch_kline_history", boom)
    monkeypatch.setattr(build, "fetch_guba_rank_history", boom)


def _run(argv, capsys):
    code = cli.main(argv)
    out = capsys.readouterr().out
    return code, out


def test_rebuild_dry_run(capsys, tmp_path, _no_net):
    code, out = _run(["rebuild", "--dry-run", "--data-dir", str(tmp_path),
                      "--with-sectors", "--workers", "4"], capsys)
    assert code == 0
    assert "[DRY-RUN] rebuild plan" in out
    assert "[DRY-RUN] done" in out
    for step in ("spot", "kline", "guba", "combined", "indicators",
                 "sector-kline", "sector-indicators"):
        assert f"STEP {step}" in out
    # 断点续传/force 删除旧库在 dry-run 下不应发生
    assert "deleting old database" not in out


def test_rebuild_dry_run_force_no_delete(capsys, tmp_path, _no_net):
    code, out = _run(["rebuild", "--force", "--dry-run", "--data-dir", str(tmp_path)], capsys)
    assert code == 0
    assert "deleting old database" not in out


def test_backfill_dry_run(capsys, tmp_path, _no_net):
    code, out = _run(["backfill", "--dry-run", "--start", "2026-01-01",
                      "--data-dir", str(tmp_path)], capsys)
    assert code == 0
    assert "[DRY-RUN] backfill plan" in out


def test_daily_capture_dry_run(capsys, tmp_path, _no_net):
    code, out = _run(["daily-capture", "--dry-run", "--data-dir", str(tmp_path)], capsys)
    assert code == 0
    assert "[DRY-RUN] daily capture plan" in out
    assert "[DRY-RUN] Nothing was downloaded or written." in out


def test_cleanup_dry_run(capsys, tmp_path, _no_net):
    code, out = _run(["cleanup", "--dry-run", "--data-dir", str(tmp_path)], capsys)
    assert code == 0
    assert "VACUUM done" not in out


def test_parse_patterns():
    from stock_analysis_mcp.strategies.patterns import PATTERN_NAMES
    keys = cli._parse_patterns("回调,ma_rebound,w底,不存在的形态")
    assert keys is not None
    assert "ma_rebound" in keys
    for k in keys:
        assert k in PATTERN_NAMES


def test_parse_patterns_empty():
    assert cli._parse_patterns(None) is None
    assert cli._parse_patterns("") is None
