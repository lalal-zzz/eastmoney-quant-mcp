"""数据源层单元测试 (全部离线): guba 解密固定向量 / 代码格式化 / K线裁剪"""

import pytest

from eastmoney_quant_mcp.data import sources


# ---------------------------------------------------------------------------
# guba 年文件 AES-CBC 解密 (固定向量)
# ---------------------------------------------------------------------------

# 由 AES-128-CBC (key=md5("getUtilsFromFile"), IV="getClassFromFile") 加密
# {"data":[{"CALCTIME":"2026-08-14 15:00:00","RANK":42}]} 得到的固定密文
GUBA_CIPHER_VECTOR = "yAEdlIbHUbCbKb2ZMbAHsKxOIdO4xRTrBMIOLDuSugy7Mvq+f8vXMYz5IxmwzHYzj777dl0cl9cnOMlr/0QErQ=="
GUBA_PLAIN_VECTOR = '{"data":[{"CALCTIME":"2026-08-14 15:00:00","RANK":42}]}'


def test_guba_decrypt_fixed_vector():
    assert sources._guba_decrypt(GUBA_CIPHER_VECTOR) == GUBA_PLAIN_VECTOR


def test_guba_decrypt_roundtrip():
    """用相同参数加密一个已知明文, 解密必须还原 (验证 key/IV 派生一致)"""
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad

    import base64
    import hashlib

    plain = '{"data":[{"CALCTIME":"2026-08-13 15:00:00","RANK":7}]}'
    key = hashlib.md5(sources._GUBA_KEY_RAW.encode("utf-8")).hexdigest().encode("utf-8")
    cipher = AES.new(key, AES.MODE_CBC, sources._GUBA_IV)
    ct = base64.b64encode(cipher.encrypt(pad(plain.encode("utf-8"), 16))).decode()
    assert sources._guba_decrypt(ct) == plain


# ---------------------------------------------------------------------------
# 股吧代码格式化
# ---------------------------------------------------------------------------


def test_guba_format_code():
    assert sources._guba_format_code("000001") == "SZ000001"
    assert sources._guba_format_code("600000") == "SH600000"
    assert sources._guba_format_code("830799") == "BJ830799"
    assert sources._guba_format_code("SH600519") == "SH600519"
    assert sources._guba_format_code("sz000001") == "SZ000001"
    assert sources._guba_format_code("300750.SZ") == "SZ300750"


# ---------------------------------------------------------------------------
# K线历史裁剪/排序/限条数
# ---------------------------------------------------------------------------


def test_clip_and_sort_iso_ranges():
    rows = [
        {"date": "20260810", "close": 1},
        {"date": "2026-08-12", "close": 3},
        {"date": "2026-08-14", "close": 5},
        {"date": "2026-08-11", "close": 2},
        {"date": "2026-08-13", "close": 4},
    ]
    out = sources._clip_and_sort(rows, "2026-08-11", "2026-08-13", limit=None)
    assert [r["close"] for r in out] == [2, 3, 4]   # 升序 + 区间裁剪


def test_clip_and_sort_limit_keeps_tail():
    rows = [{"date": f"2026-08-{d:02d}", "close": d} for d in range(1, 15)]
    out = sources._clip_and_sort(rows, "2026-08-01", "2026-08-31", limit=3)
    assert [r["close"] for r in out] == [12, 13, 14]


# ---------------------------------------------------------------------------
# SPOT 字段映射: 英文字段集合覆盖存储层 SPOT_COLUMNS 所需键
# ---------------------------------------------------------------------------


def test_spot_field_map_covers_storage_columns():
    from eastmoney_quant_mcp.data.storage import SPOT_COLUMNS

    mapped = set(sources.SPOT_FIELD_MAP.values())
    for col in ("latest_price", "pe_ttm", "main_net_inflow", "sector_name",
                "five_min_change", "volume_ratio_5d", "amplitude_5d"):
        assert col in mapped, f"SPOT_FIELD_MAP 缺少 {col}"
    # 存储层 SPOT_COLUMNS 中需要由接口直接提供的字段 (symbol/trade_date 由调用方拼)
    required = {c for c in SPOT_COLUMNS
                if c not in ("symbol", "trade_date", "name")}
    assert required <= mapped | {"latest_price"}, (
        f"SPOT_COLUMNS 存在未映射字段: {required - mapped}")
