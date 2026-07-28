"""Tests for eastmoney-quant-mcp"""

import pytest
from eastmoney_quant_mcp.data.network import normalize_symbol, to_prefixed_symbol, normalize_sector_code
from eastmoney_quant_mcp.tools.pattern_scan import PATTERNS, PATTERN_DESCRIPTIONS


def test_normalize_symbol():
    assert normalize_symbol("000001") == "000001"
    assert normalize_symbol("sh600000") == "600000"
    assert normalize_symbol("sz000001") == "000001"
    assert normalize_symbol("bj920000") == "920000"


def test_to_prefixed_symbol():
    assert to_prefixed_symbol("600000") == "sh600000"
    assert to_prefixed_symbol("000001") == "sz000001"
    assert to_prefixed_symbol("920000") == "bj920000"


def test_normalize_sector_code():
    assert normalize_sector_code("BK1090") == "BK1090"
    assert normalize_sector_code("bk1090") == "BK1090"
    assert normalize_sector_code("1090") == "BK1090"


def test_pattern_list():
    assert len(PATTERNS) == len(PATTERN_DESCRIPTIONS)
    for name in PATTERNS:
        assert name in PATTERN_DESCRIPTIONS


def test_normalize_klt():
    from eastmoney_quant_mcp.tools.stock_data import _normalize_klt

    assert _normalize_klt("60") == "60"
    assert _normalize_klt(101) == "101"  # int 入参也可
    assert _normalize_klt(" 5 ") == "5"  # 容忍空白
    with pytest.raises(ValueError):
        _normalize_klt("7")
    with pytest.raises(ValueError):
        _normalize_klt("abc")
