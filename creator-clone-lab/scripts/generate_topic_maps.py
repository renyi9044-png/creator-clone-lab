#!/usr/bin/env python
"""Generate topic maps from promoted units with raw-atom support counts."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

from knowledge_store import connect_db, ensure_project, slugify


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: generate_topic_maps.py <project_dir>", file=sys.stderr)
        return 2
    project = Path(sys.argv[1]).resolve()
    paths = ensure_project(project)
    topics: dict[str, list[dict]] = defaultdict(list)
    with connect_db(paths["database"]) as conn:
        atoms = conn.execute(
            "SELECT atom_id, atom_type, title, statement, topics_json, confidence, status, source_ids_json FROM atoms ORDER BY atom_type, atom_id"
        ).fetchall()
        for row in atoms:
            item = dict(row)
            item["source_ids"] = json.loads(row["source_ids_json"] or "[]")
            for topic in json.loads(row["topics_json"] or "[]") or ["untagged"]:
                topics[topic].append(item)
        raw_topic_counts: dict[str, int] = defaultdict(int)
        for row in conn.execute("SELECT topics_json FROM raw_atoms").fetchall():
            for topic in json.loads(row["topics_json"] or "[]"):
                raw_topic_counts[topic] += 1
    index_lines = ["# Topic Maps", ""]
    for topic, items in sorted(topics.items(), key=lambda pair: (-len(pair[1]), pair[0])):
        filename = f"{slugify(topic, 'untagged')}.md"
        lines = [
            f"# Topic Map: {topic}",
            "",
            f"Promoted units: {len(items)}",
            f"Supporting raw atoms: {raw_topic_counts.get(topic, 0)}",
            "",
        ]
        by_type: dict[str, list[dict]] = defaultdict(list)
        for item in items:
            by_type[item["atom_type"]].append(item)
        for atom_type, typed_items in sorted(by_type.items()):
            lines.extend([f"## {atom_type}", ""])
            for item in typed_items:
                sources = ", ".join(f"`{source_id}`" for source_id in item["source_ids"]) or "no source"
                lines.append(
                    f"- **{item['title']}** (`{item['atom_id']}`, {item['status']}, {item['confidence']})  \n"
                    f"  {item['statement']}  \n"
                    f"  Sources: {sources}"
                )
            lines.append("")
        (paths["topic_maps"] / filename).write_text("\n".join(lines), encoding="utf-8")
        index_lines.append(
            f"- [{topic}]({filename}) - {len(items)} promoted units / {raw_topic_counts.get(topic, 0)} raw atoms"
        )
    index_path = paths["topic_maps"] / "index.md"
    index_path.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    print(f"topic maps: {len(topics)}")
    print(f"saved: {index_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"generate_topic_maps failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
