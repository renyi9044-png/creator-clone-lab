#!/usr/bin/env python
"""Rebuild full-text indexes from sources and promoted Markdown units."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from knowledge_store import (
    connect_db,
    ensure_project,
    parse_generated_atom,
    resolve_stored_path,
    upsert_atom_fts,
    upsert_source_fts,
)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: rebuild_knowledge_index.py <project_dir>", file=sys.stderr)
        return 2
    project = Path(sys.argv[1]).resolve()
    paths = ensure_project(project)
    source_count = 0
    atom_count = 0
    with connect_db(paths["database"]) as conn:
        conn.execute("DELETE FROM sources_fts")
        conn.execute("DELETE FROM atoms_fts")
        for source in conn.execute("SELECT source_id, title, creator, body_path FROM sources").fetchall():
            body_path = resolve_stored_path(source["body_path"], project)
            body = body_path.read_text(encoding="utf-8", errors="replace") if body_path and body_path.exists() else ""
            upsert_source_fts(conn, source["source_id"], source["title"] or "", source["creator"] or "", body)
            source_count += 1
        unit_files = sorted(paths["content_units"].glob("*.md")) + sorted(paths["pattern_units"].glob("*.md"))
        for atom_file in unit_files:
            atom = parse_generated_atom(atom_file)
            atom_id = atom.get("id")
            if not atom_id:
                continue
            topics = atom.get("topics") or []
            statement = atom.get("statement") or ""
            upsert_atom_fts(conn, atom_id, atom.get("title") or atom_file.stem, statement, topics)
            conn.execute(
                "UPDATE atoms SET file_path = ?, topics_json = ?, statement = ?, updated_at = COALESCE(?, updated_at) WHERE atom_id = ?",
                (
                    atom_file.relative_to(project).as_posix(),
                    json.dumps(topics, ensure_ascii=False),
                    statement,
                    atom.get("updated_at"),
                    atom_id,
                ),
            )
            atom_count += 1
    print(f"indexed sources: {source_count}")
    print(f"indexed atoms: {atom_count}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"rebuild_knowledge_index failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
