#!/usr/bin/env python
"""Validate atom relationships and build machine/human-readable relation maps."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from knowledge_store import connect_db, ensure_project, now_iso


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: generate_relation_map.py <project_dir>", file=sys.stderr)
        return 2
    project = Path(sys.argv[1]).resolve()
    paths = ensure_project(project)
    with connect_db(paths["database"]) as conn:
        rows = conn.execute("SELECT atom_id, title, relationships_json, source_ids_json FROM atoms ORDER BY atom_id").fetchall()
    atom_ids = {row["atom_id"] for row in rows}
    edges = []
    missing_targets = []
    source_links = []
    for row in rows:
        for relation in json.loads(row["relationships_json"] or "[]"):
            target = relation.get("target")
            edge = {"source": row["atom_id"], "type": relation.get("type"), "target": target}
            edges.append(edge)
            if target not in atom_ids:
                missing_targets.append(edge)
        for source_id in json.loads(row["source_ids_json"] or "[]"):
            source_links.append({"atom_id": row["atom_id"], "source_id": source_id})
    relation_counts = Counter(edge["type"] for edge in edges)
    report = {
        "generated_at": now_iso(),
        "atom_count": len(rows),
        "edge_count": len(edges),
        "relation_counts": dict(relation_counts),
        "missing_target_count": len(missing_targets),
        "missing_targets": missing_targets,
        "edges": edges,
        "source_links": source_links,
    }
    json_path = paths["state_dir"] / "relation_index.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Relation Overview",
        "",
        f"- Atoms: {len(rows)}",
        f"- Relationships: {len(edges)}",
        f"- Missing targets: {len(missing_targets)}",
        "",
        "## Relationship Counts",
        "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in sorted(relation_counts.items()))
    lines.extend(["", "## Missing Targets", ""])
    lines.extend(
        f"- `{item['source']}` --{item['type']}--> `{item['target']}`" for item in missing_targets
    )
    if not missing_targets:
        lines.append("- None")
    markdown_path = paths["topic_maps"] / "relation_overview.md"
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"relationships: {len(edges)}")
    print(f"missing targets: {len(missing_targets)}")
    print(f"saved: {json_path}")
    return 1 if missing_targets else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"generate_relation_map failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
