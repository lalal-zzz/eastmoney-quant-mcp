"""
data/storage/query.py — 只读查询 / meta 元数据 / 重建断点续传进度
"""

from datetime import datetime

from .paths import _resolve_path, get_sector_db, get_stock_db
from .schema import _get_conn, _write_conn


def query_stock_db(sql: str, params: tuple = ()) -> list[dict]:
    conn = _get_conn(get_stock_db())
    try:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def query_sector_db(sql: str, params: tuple = ()) -> list[dict]:
    conn = _get_conn(get_sector_db())
    try:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def set_meta_stock(key: str, value: str):
    with _write_conn(get_stock_db()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key,value,updated_at) VALUES(?,?,?)",
            (key, value, datetime.now().isoformat()),
        )


def set_meta_sector(key: str, value: str):
    with _write_conn(get_sector_db()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key,value,updated_at) VALUES(?,?,?)",
            (key, value, datetime.now().isoformat()),
        )


def get_meta_stock(key: str) -> str | None:
    rows = query_stock_db("SELECT value FROM meta WHERE key=?", (key,))
    return rows[0]["value"] if rows else None


def get_meta_sector(key: str) -> str | None:
    rows = query_sector_db("SELECT value FROM meta WHERE key=?", (key,))
    return rows[0]["value"] if rows else None


# ── 重建断点续传 ──

def record_rebuild_progress(step: str, symbol: str, rows: int) -> None:
    """记录重建断点续传进度"""
    with _write_conn(get_stock_db()) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO rebuild_progress(step, symbol, rows, updated_at) "
            "VALUES(?,?,?,?)",
            (step, symbol, rows, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )


# 各步骤进度与实际数据表的对应关系(用于交叉校验)
_STEP_VERIFY_TABLE = {
    "kline": "stock_kline",
    "guba": "stock_popularity_rank",
}


def get_rebuild_done(step: str) -> set[str]:
    """某步骤已完成的 symbol 集合(断点续传)

    不能盲信 rebuild_progress: 若真实数据表被清空/重建而进度表残留
    (如外部删表、旧库迁移), 这些 symbol 会被永久跳过不再下载。
    故对有数据表映射的步骤做交叉校验, 并清除失效的进度记录。
    """
    rows = query_stock_db("SELECT symbol FROM rebuild_progress WHERE step=?", (step,))
    done = {r["symbol"] for r in rows}
    verify_table = _STEP_VERIFY_TABLE.get(step)
    if verify_table and done:
        present = {
            r["symbol"]
            for r in query_stock_db(f"SELECT DISTINCT symbol FROM {verify_table}")
        }
        stale = done - present
        if stale:
            with _write_conn(get_stock_db()) as conn:
                conn.execute(
                    f"DELETE FROM rebuild_progress WHERE step=? "
                    f"AND symbol NOT IN (SELECT DISTINCT symbol FROM {verify_table})",
                    (step,),
                )
            done = done & present
    return done


def get_db_paths() -> dict:
    return {
        "stock_db": _resolve_path("STOCK_DB"),
        "sector_db": _resolve_path("SECTOR_DB"),
        "stock_dir": _resolve_path("STOCK_DIR"),
        "sector_dir": _resolve_path("SECTOR_DIR"),
    }
