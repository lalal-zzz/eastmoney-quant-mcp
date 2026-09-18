from __future__ import annotations


def _take_grouped(rows: list[dict], keys: tuple[str, ...], per_group: int) -> list[dict]:
    output, counts = [], {}
    for row in rows:
        key = tuple(str(row.get(k, "")) for k in keys)
        if counts.get(key, 0) >= per_group:
            continue
        output.append(row)
        counts[key] = counts.get(key, 0) + 1
    return output


def compact_market_structure(snapshot: dict, *, current_price: float,
                             recent_pivots: int = 20,
                             recent_legs: int = 20) -> dict:
    """Bound a public MCP payload while preserving internal full snapshots."""
    compact = {
        "as_of_idx": snapshot["as_of_idx"],
        "counts": {
            "trendlines": len(snapshot["trendlines"]),
            "channels": len(snapshot["channels"]),
            "ranges": len(snapshot["ranges"]),
            "double_patterns": len(snapshot["double_patterns"]),
        },
        "scales": {},
    }
    for name, data in snapshot["scales"].items():
        compact["scales"][name] = {
            "pivot_count": len(data["pivots"]),
            "leg_count": len(data["legs"]),
            "pivots": data["pivots"][-recent_pivots:],
            "legs": data["legs"][-recent_legs:],
        }
    trendline_rows = [x for x in snapshot["trendlines"] if x.get("kind", "trendline") == "trendline"]
    compact["trendlines"] = _take_grouped(trendline_rows, ("scale", "role"), 2)
    converted = [x for x in snapshot["trendlines"] if x.get("kind") == "horizontal_level"]
    compact["converted_levels"] = _take_grouped(converted, ("scale", "role"), 2)
    compact["channels"] = _take_grouped(snapshot["channels"], ("scale",), 3)
    compact["ranges"] = _take_grouped(snapshot["ranges"], ("scale",), 3)
    # Pattern selection must not silently lose candidates.  Keep all detected
    # W/M rows in the public structure payload; callers may sort/filter them
    # explicitly, while ``counts.double_patterns`` remains auditable.
    compact["double_patterns"] = list(snapshot["double_patterns"])

    positions = snapshot.get("positions", {})
    anchors = _take_grouped(positions.get("anchors", []), ("scale",), 3)
    anchor_ids = {x["id"] for x in anchors}
    retracements = [x for x in positions.get("retracements", []) if x["anchor_id"] in anchor_ids]
    projections = [x for x in positions.get("projections", []) if x["anchor_id"] in anchor_ids]
    zones = [x for x in positions.get("fib_zones", []) if x["anchor_id"] in anchor_ids]
    clusters = []
    for row in positions.get("confluence_zones", []):
        if not any(s.get("anchor_id") in anchor_ids for s in row.get("sources", [])):
            continue
        clusters.append({
            **{k: v for k, v in row.items() if k != "sources"},
            "source_refs": [
                {"id": s.get("id"), "anchor_id": s.get("anchor_id"),
                 "family": s.get("family"), "center": s.get("center")}
                for s in row.get("sources", []) if s.get("anchor_id") in anchor_ids
            ],
        })
    clusters.sort(key=lambda x: (abs((x["lower"] + x["upper"]) / 2 - current_price), -x["score"]))
    compact["positions"] = {
        "counts": {k: len(positions.get(k, [])) for k in (
            "anchors", "retracements", "projections", "fib_zones", "confluence_zones"
        )},
        "anchors": anchors,
        "retracements": retracements,
        "projections": projections,
        "fib_zones": zones,
        "confluence_zones": clusters[:12],
    }
    return compact
