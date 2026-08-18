"""
cli.py — 重建 / 回填 / 采集 / 清理 / 形态分析 统一命令行入口
(移植自"股票信息"项目 rebuild_stock_db.py / backfill_daily_spot.py /
eastmoney_rank_scheduler.py 的 CLI 部分)

用法:
    python -m eastmoney_quant_mcp.cli rebuild --dry-run          # 预览步骤, 不联网
    python -m eastmoney_quant_mcp.cli rebuild --workers 8 --with-sectors
    python -m eastmoney_quant_mcp.cli backfill --start 2026-01-01
    python -m eastmoney_quant_mcp.cli daily-capture              # 晚间采集(任务计划用)
    python -m eastmoney_quant_mcp.cli cleanup --dry-run
    python -m eastmoney_quant_mcp.cli pattern-scan --universe sectors --date 2026-08-14
    python -m eastmoney_quant_mcp.cli pattern-backtest --sample 300 --workers 8
    python -m eastmoney_quant_mcp.cli pattern-optimize --cache signals.csv --universe stocks
"""

import argparse
import json
import os
import sys


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="eastmoney-quant",
        description="东方财富量化: 本地库重建/回填/采集/清理 + 形态扫描与回测")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--data-dir", default=None,
                        help="覆盖数据根目录 (等价 EASTMONEY_DATA_DIR)")
        sp.add_argument("--dry-run", action="store_true",
                        help="只打印执行计划, 不联网不写库")

    # ── rebuild ──
    r = sub.add_parser("rebuild", help="步骤化全量重建本地库 (断点续传)")
    add_common(r)
    r.add_argument("--force", action="store_true", help="重建前删除旧数据库")
    r.add_argument("--workers", type=int, default=8)
    r.add_argument("--skip-spot", action="store_true")
    r.add_argument("--skip-kline", action="store_true")
    r.add_argument("--skip-rank", action="store_true")
    r.add_argument("--skip-combined", action="store_true")
    r.add_argument("--skip-indicators", action="store_true")
    r.add_argument("--with-sectors", action="store_true", help="含板块全量K线+指标缓存")
    r.add_argument("--sector-limit", type=int, default=5000)

    # ── backfill ──
    b = sub.add_parser("backfill", help="缺口检测补齐 (history/rank/combined)")
    add_common(b)
    b.add_argument("--start", default=None)
    b.add_argument("--end", default=None)
    b.add_argument("--no-history", action="store_true")
    b.add_argument("--no-rank", action="store_true")
    b.add_argument("--no-combined", action="store_true")
    b.add_argument("--symbols", default=None, help="逗号分隔股票代码 (默认全部)")
    b.add_argument("--workers", type=int, default=8)

    # ── daily-capture ──
    d = sub.add_parser("daily-capture", help="晚间采集: xuangu排名+spot快照+K线增量+指标缓存")
    add_common(d)
    d.add_argument("--no-spot", action="store_true")
    d.add_argument("--no-kline", action="store_true")
    d.add_argument("--no-indicators", action="store_true")
    d.add_argument("--page-size", type=int, default=500)
    d.add_argument("--max-pages", type=int, default=None)
    d.add_argument("--workers", type=int, default=8)

    # ── cleanup ──
    c = sub.add_parser("cleanup", help="清理冗余/过期数据 + VACUUM")
    add_common(c)
    c.add_argument("--no-vacuum", action="store_true")

    # ── pattern-scan ──
    s = sub.add_parser("pattern-scan", help="形态扫描 (股票/板块, 依赖本地库K线)")
    s.add_argument("--universe", default="stocks", choices=("stocks", "sectors"))
    s.add_argument("--date", default=None, help="扫描日期, 默认本地库最新交易日")
    s.add_argument("--patterns", default=None, help="逗号分隔形态 key/中文名 (默认全部)")
    s.add_argument("--strict", action="store_true", help="只留优中选优档信号")
    s.add_argument("--no-filter", action="store_true", help="不过滤返回全部原始信号")
    s.add_argument("--workers", type=int, default=8)
    s.add_argument("--symbols", default=None, help="逗号分隔标的代码/名称 (默认全部)")
    s.add_argument("--sector-type", choices=("concept", "industry"),
                   help="板块类型 (仅 sectors 宇宙)")
    s.add_argument("--json", action="store_true", help="以 JSON 输出信号")

    # ── pattern-backtest / pattern-optimize (转发) ──
    pb = sub.add_parser("pattern-backtest", help="形态历史回测 (详见 strategies/pattern_backtest.py)")
    pb.add_argument("args", nargs=argparse.REMAINDER)
    po = sub.add_parser("pattern-optimize", help="形态参数优化 (详见 strategies/pattern_optimize.py)")
    po.add_argument("args", nargs=argparse.REMAINDER)

    return p


def _parse_patterns(text: str | None) -> list[str] | None:
    if not text:
        return None
    from .strategies.patterns import PATTERN_NAMES
    keys = []
    for tok in text.replace("，", ",").split(","):
        tok = tok.strip()
        if tok in PATTERN_NAMES:
            keys.append(tok)
        else:
            matched = [k for k, cn in PATTERN_NAMES.items() if tok and (tok in cn or cn in tok)]
            keys.extend(matched)
    return list(dict.fromkeys(keys)) or None


def _cmd_rebuild(a) -> int:
    from .data.build import rebuild_full_data
    return rebuild_full_data(
        force=a.force, workers=a.workers,
        skip_spot=a.skip_spot, skip_kline=a.skip_kline, skip_rank=a.skip_rank,
        skip_combined=a.skip_combined, skip_indicators=a.skip_indicators,
        with_sectors=a.with_sectors, sector_limit=a.sector_limit,
        dry_run=a.dry_run)


def _cmd_backfill(a) -> int:
    from .data.build import backfill_data
    symbols = a.symbols.split(",") if a.symbols else None
    return backfill_data(
        start=a.start, end=a.end,
        do_history=not a.no_history, do_rank=not a.no_rank,
        do_combined=not a.no_combined, symbols=symbols,
        max_workers=a.workers, dry_run=a.dry_run)


def _cmd_daily_capture(a) -> int:
    from .data.build import daily_capture
    return daily_capture(
        save_spot=not a.no_spot, save_kline=not a.no_kline,
        save_indicators=not a.no_indicators,
        page_size=a.page_size, max_pages=a.max_pages,
        workers=a.workers, dry_run=a.dry_run)


def _cmd_cleanup(a) -> int:
    from .data.build import cleanup_database
    return cleanup_database(dry_run=a.dry_run, vacuum=not a.no_vacuum)


def _cmd_pattern_scan(a) -> int:
    from .strategies.patterns import scan_universe
    symbols = a.symbols.split(",") if a.symbols else None
    sigs = scan_universe(
        a.universe, date=a.date, patterns=_parse_patterns(a.patterns),
        strict=a.strict, no_filter=a.no_filter,
        workers=a.workers, symbols=symbols, sector_type=a.sector_type)
    if a.json:
        print(json.dumps(sigs, ensure_ascii=False, indent=2))
    elif sigs:
        print(f"共 {len(sigs)} 个信号 ({a.universe}):")
        for s in sigs:
            print(f"  {s['date']} {s['symbol']} {s.get('name', '')} "
                  f"[{s['pattern_cn']}/{s['variant']}] score={s['score']} "
                  f"resonance={s['resonance']} levels={s['hit_levels']} "
                  f"{'(strict)' if s.get('strict_pass') else ''}")
    else:
        print("无信号")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if getattr(args, "data_dir", None):          # 数据目录覆盖 (等价 EASTMONEY_DATA_DIR)
        os.environ["EASTMONEY_DATA_DIR"] = args.data_dir

    handlers = {
        "rebuild": _cmd_rebuild,
        "backfill": _cmd_backfill,
        "daily-capture": _cmd_daily_capture,
        "cleanup": _cmd_cleanup,
        "pattern-scan": _cmd_pattern_scan,
    }
    if args.command in handlers:
        return handlers[args.command](args)

    if args.command == "pattern-backtest":
        from .strategies import pattern_backtest
        pattern_backtest.main(args.args)
        return 0
    if args.command == "pattern-optimize":
        from .strategies import pattern_optimize
        pattern_optimize.main(args.args)
        return 0
    _build_parser().print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
