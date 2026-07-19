#!/usr/bin/env python
"""Generate a non-destructive retrospective scaffold from performance snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from knowledge_store import connect_db, ensure_project


def numeric_delta(previous: dict, current: dict) -> dict:
    deltas = {}
    for key, value in current.items():
        if isinstance(value, (int, float)) and isinstance(previous.get(key), (int, float)):
            deltas[key] = value - previous[key]
    return deltas


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("source_id")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    paths = ensure_project(project)
    ledger = paths["performance"] / "performance_snapshots.jsonl"
    if not ledger.exists():
        raise RuntimeError("no performance snapshots found")
    snapshots = [
        json.loads(line)
        for line in ledger.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("source_id") == args.source_id
    ]
    if not snapshots:
        raise RuntimeError(f"no snapshots for {args.source_id}")
    current = snapshots[-1]
    previous = snapshots[-2] if len(snapshots) > 1 else {"metrics": {}}
    deltas = numeric_delta(previous.get("metrics") or {}, current.get("metrics") or {})
    with connect_db(paths["database"]) as conn:
        source = conn.execute("SELECT title, platform, url FROM sources WHERE source_id = ?", (args.source_id,)).fetchone()
        atoms = conn.execute(
            "SELECT atom_id, atom_type, title, statement, status, confidence FROM atoms WHERE source_ids_json LIKE ? ORDER BY atom_type, atom_id",
            (f'%"{args.source_id}"%',),
        ).fetchall()
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    output = paths["reports"] / f"retrospective_{args.source_id}_{stamp}.md"
    lines = [
        f"# Retrospective: {source['title'] if source else args.source_id}",
        "",
        f"Source: `{args.source_id}`",
        f"Platform: {source['platform'] if source else 'unknown'}",
        f"URL: {source['url'] if source else ''}",
        f"Latest stage: {current.get('stage')}",
        f"Observed at: {current.get('observed_at')}",
        "",
        "## Current Metrics",
        "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in sorted((current.get("metrics") or {}).items()))
    lines.extend(["", "## Delta From Previous Snapshot", ""])
    lines.extend(f"- `{key}`: {value:+}" for key, value in sorted(deltas.items()))
    if not deltas:
        lines.append("- No comparable previous snapshot.")
    lines.extend(["", "## Linked Knowledge Rules", ""])
    for atom in atoms:
        lines.append(
            f"- `{atom['atom_id']}` **{atom['title']}** [{atom['status']}/{atom['confidence']}]  \n"
            f"  {atom['statement']}"
        )
    if not atoms:
        lines.append("- No linked atom. Register knowledge before changing clone rules.")
    lines.extend(
        [
            "",
            "## Attribution Review",
            "",
            "- Topic:",
            "- Promise:",
            "- Hook:",
            "- Visual proof:",
            "- Information density:",
            "- Pacing:",
            "- Audience fit:",
            "- Distribution:",
            "- Conversion path:",
            "",
            "## Knowledge Action",
            "",
            "Choose only after review: add evidence, change confidence, mark format-specific, or reject a rule.",
            "Do not rewrite historical evidence or the original prediction.",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"snapshots: {len(snapshots)}")
    print(f"retrospective: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"generate_retrospective failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
