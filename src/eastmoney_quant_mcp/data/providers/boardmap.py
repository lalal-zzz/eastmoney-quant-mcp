"""
板块代码映射层

本地库主键始终是东财 BKxxxx; 腾讯/新浪/搜狐各自的板块代码仅在
"对外抓取"这一层使用, 通过板块名映射, 不进库:
    东财 BKxxxx --名称--> 腾讯 ptXXXX / 新浪 node / 搜狐 bk 数字

名称取值优先级: 调用方显式传入(sync 全量下载时板块名在手) >
本地 sector_basic 表(懒加载路径) > 无(放弃映射, 直接走东财)。
"""

from . import sina, sohu, tencent


def _norm(name: str) -> str:
    return str(name or "").strip().replace(" ", "").replace("（", "(").replace("）", ")")


def sector_name_from_local(bk_code: str) -> str | None:
    """从本地 sector_basic 表查板块名(未初始化时返回 None)"""
    try:
        from ..storage import query_sector_db

        rows = query_sector_db(
            "SELECT sector_name FROM sector_basic WHERE sector_code=? LIMIT 1",
            (bk_code,),
        )
        return rows[0]["sector_name"] if rows else None
    except Exception:
        return None


def _name_variants(name: str) -> list[str]:
    """名称变体: 腾讯概念普遍带"概念"后缀(华为海思→华为海思概念)"""
    n = _norm(name)
    variants = [n]
    if n and not n.endswith("概念"):
        variants.append(n + "概念")
    if n.endswith("概念"):
        variants.append(n[:-2])
    return [v for v in variants if v]


def _resolve(bk_code: str, name: str | None, index_fetcher) -> tuple[str | None, str]:
    """通用解析: 返回 (目标代码 or None, 实际使用的板块名)"""
    sector_name = name or sector_name_from_local(bk_code)
    if not sector_name:
        return None, ""
    index = index_fetcher()
    if not index:
        return None, sector_name
    target = None
    for variant in _name_variants(sector_name):
        target = index.get(variant)
        if target:
            break
    return target, sector_name


def resolve_tencent_pt(bk_code: str, name: str = None) -> str | None:
    """东财 BK → 腾讯 pt 代码(按板块名)"""
    code, _ = _resolve(bk_code, name, tencent.get_name_pt_index)
    return code


def resolve_sina_node(bk_code: str, name: str = None) -> tuple[str | None, str]:
    """东财 BK → 新浪 node (按板块名), 同时返回板块名供日志"""
    maps = sina.get_name_node_index()

    def _idx() -> dict:
        merged = {}
        merged.update(maps.get("industry") or {})
        merged.update(maps.get("concept") or {})
        return merged

    return _resolve(bk_code, name, _idx)


def resolve_sohu_bk(bk_code: str, name: str = None) -> str | None:
    """东财 BK → 搜狐 bk 数字代码(按板块名)"""
    code, _ = _resolve(bk_code, name, sohu.get_name_bk_index)
    return code
