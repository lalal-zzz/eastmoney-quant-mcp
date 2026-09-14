"""
data/storage — 本地 SQLite 数据存储 (股票库 + 板块库)

模块组织:
  paths.py     路径解析 (懒加载 + 测试重定向)
  schema.py    建表 DDL / 原地迁移 / 连接工厂与写连接上下文
  writer.py    行级写入模板与各表 save_* 函数
  snapshot.py  历史快照表 (spot / 人气排名 / combined 合并表)
  query.py     只读查询 / meta 元数据 / 重建断点续传

本 __init__ 为门面: re-export 全部既有公开名, 旧调用方
`from ..data.storage import X` 无需任何改动。
"""

from .paths import (
    _db_paths_cache,
    _path_overrides,
    _resolve_path,
    get_sector_db,
    get_stock_db,
    set_db_paths,
)
from .query import (
    _STEP_VERIFY_TABLE,
    get_db_paths,
    get_meta_sector,
    get_meta_stock,
    get_rebuild_done,
    query_sector_db,
    query_stock_db,
    record_rebuild_progress,
    set_meta_sector,
    set_meta_stock,
)
from .schema import (
    SECTOR_DDL,
    STOCK_DDL,
    _get_conn,
    _init_lock,
    _lock,
    _schema_ready,
    _write_conn,
    init_all,
    init_sector_db,
    init_stock_db,
)
from .snapshot import (
    COMBINED_SPOT_COLUMNS,
    RANK_COLUMNS,
    SPOT_COLUMNS,
    build_combined_from_history,
    save_daily_stock_info,
    save_popularity_rank,
    upsert_combined_rank,
    upsert_combined_spot,
)
from .writer import (
    save_data_coverage,
    save_pattern_signals,
    save_sector_basic,
    save_sector_indicators,
    save_sector_kline,
    save_sector_member,
    save_stock_basic,
    save_stock_indicators,
    save_stock_kline,
    save_stock_rank,
    save_stock_spot,
)

# 兼容旧式 `storage.STOCK_DB` 属性访问 (懒解析, 遵循测试重定向)
_LAZY_ATTRS = ("STOCK_DIR", "SECTOR_DIR", "STOCK_DB", "SECTOR_DB")


def __getattr__(name: str):
    if name in _LAZY_ATTRS:
        return _resolve_path(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
