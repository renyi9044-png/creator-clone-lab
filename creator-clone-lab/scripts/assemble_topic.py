#!/usr/bin/env python
"""Assemble a new evidence-linked content brief from atoms in one topic."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from knowledge_store import connect_db, ensure_project, slugify


ORDER = ["QST", "CON", "OPI", "CAS", "SOL", "HOK", "STR", "EXP", "VIS", "CTA"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--title", required=True)
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    paths = ensure_project(project)
    with connect_db(paths["database"]) as conn:
        rows = conn.execute(
            "SELECT atom_id, atom_type, title, statement, status, confidence, source_ids_json, raw_atom_ids_json FROM atoms WHERE topics_json LIKE ? ORDER BY atom_type, confidence DESC, atom_id",
            (f"%{args.topic}%",),
        ).fetchall()
    by_type: dict[str, list[dict]] = {atom_type: [] for atom_type in ORDER}
    for row in rows:
        item = dict(row)
        item["source_ids"] = json.loads(row["source_ids_json"] or "[]")
        item["raw_atom_ids"] = json.loads(row["raw_atom_ids_json"] or "[]")
        by_type.setdefault(row["atom_type"], []).append(item)
    output_dir = paths["creations"] / "assemblies"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    output = output_dir / f"{stamp}_{slugify(args.title, 'assembly')}.md"
    lines = [
        f"# Content Assembly: {args.title}",
        "",
        f"Topic: {args.topic}",
        "",
        "> This is an evidence assembly, not a finished script. Convert it into an original expression.",
        "",
    ]
    for atom_type in ORDER:
        items = by_type.get(atom_type) or []
        if not items:
            continue
        lines.extend([f"## {atom_type}", ""])
        for item in items:
            lines.append(
                f"- **{item['title']}** (`{item['atom_id']}`, {item['status']}/{item['confidence']})  \n"
                f"  {item['statement']}  \n"
                f"  Raw atoms: {', '.join(item['raw_atom_ids']) or 'not linked'}  \n"
                f"  Sources: {', '.join(item['source_ids'])}"
            )
        lines.append("")
    lines.extend(
        [
            "## Draft Decisions",
            "",
            "- Target audience:",
            "- Primary metric:",
            "- Chosen hook:",
            "- Proof sequence:",
            "- Visual plan:",
            "- Ending action:",
            "- Rules deliberately not used:",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"atoms used: {len(rows)}")
    print(f"assembly: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"assemble_topic failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
