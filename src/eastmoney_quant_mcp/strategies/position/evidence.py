from __future__ import annotations

from dataclasses import asdict

from .models import FibZone


def build_confluence_zones(levels: list[dict | FibZone], *,
                           max_gap_pct: float = 0.01) -> list[dict]:
    """Cluster prices and score dependency groups, not the number of drawn lines."""
    rows = []
    for item in levels:
        row = asdict(item) if isinstance(item, FibZone) else dict(item)
        if "center" not in row:
            row["center"] = float(row["value"])
        row.setdefault("lower", row["center"])
        row.setdefault("upper", row["center"])
        row.setdefault("family", "price_structure")
        row.setdefault("dependency_group", row.get("id", f"value:{row['center']}"))
        rows.append(row)
    clusters: list[list[dict]] = []
    for row in sorted(rows, key=lambda x: x["center"]):
        if not clusters:
            clusters.append([row])
            continue
        low = min(x["lower"] for x in clusters[-1])
        high = max(x["upper"] for x in clusters[-1])
        base = max(abs((low + high) / 2), 1e-12)
        overlaps = row["lower"] <= high and row["upper"] >= low
        if overlaps:
            clusters[-1].append(row)
            continue
        if (row["center"] - high) / base <= max_gap_pct:
            proposed_high = max(high, row["upper"])
            if (proposed_high - low) / base <= max_gap_pct * 2:
                clusters[-1].append(row)
                continue
        clusters.append([row])
    output = []
    for group in clusters:
        dependencies = sorted({str(x["dependency_group"]) for x in group})
        families = sorted({str(x["family"]) for x in group})
        output.append({
            "lower": round(min(x["lower"] for x in group), 8),
            "upper": round(max(x["upper"] for x in group), 8),
            "raw_level_count": len(group),
            "independent_dependency_count": len(dependencies),
            "families": families,
            "dependency_groups": dependencies,
            "score": round(min(1.0, 0.25 * len(dependencies) + 0.1 * len(families)), 4),
            "sources": group,
            "time_window": None,
            "research_only": False,
        })
    return output
