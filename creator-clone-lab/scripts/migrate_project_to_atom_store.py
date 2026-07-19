#!/usr/bin/env python
"""Migrate a V2.2 project into the V2.3 JSONL atom -> unit -> map architecture."""

from __future__ import annotations

import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

from add_knowledge_atom import render_atom
from knowledge_store import CONTENT_UNIT_TYPES, connect_db, ensure_project, now_iso, stable_id
from raw_atom_store import write_corpus


DIRECTORY_MIGRATIONS = {
    "04_topic_maps": "06_topic_maps",
    "05_creator_clone": "07_creator_clone",
    "06_creations": "08_creations",
    "07_performance": "09_performance",
    "08_state": "10_state",
    "09_reports": "11_reports",
}


def merge_directory(source: Path, target: Path) -> None:
    if not source.exists():
        target.mkdir(parents=True, exist_ok=True)
        return
    target.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        destination = target / item.name
        if item.is_dir() and destination.exists():
            merge_directory(item, destination)
        elif destination.exists():
            if item.is_file() and item.read_bytes() == destination.read_bytes():
                item.unlink()
            else:
                raise RuntimeError(f"migration collision: {destination}")
        else:
            shutil.move(str(item), str(destination))
    source.rmdir()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: migrate_project_to_atom_store.py <project_dir>", file=sys.stderr)
        return 2
    project = Path(sys.argv[1]).resolve()
    paths = ensure_project(project)
    for old_name, new_name in DIRECTORY_MIGRATIONS.items():
        merge_directory(project / old_name, project / new_name)
    for directory in (
        paths["raw_atom_shards"], paths["content_units"], paths["pattern_units"], paths["topic_maps"],
        paths["creator_clone"], paths["creations"], paths["performance"], paths["state_dir"], paths["reports"],
    ):
        directory.mkdir(parents=True, exist_ok=True)

    with connect_db(paths["database"]) as conn:
        units = [dict(row) for row in conn.execute("SELECT * FROM atoms ORDER BY atom_id").fetchall()]
        sources = {
            row["source_id"]: dict(row)
            for row in conn.execute(
                "SELECT source_id, url, published_at, creator, platform FROM sources"
            ).fetchall()
        }
        evidence_by_unit: dict[str, list[dict]] = defaultdict(list)
        for row in conn.execute(
            "SELECT atom_id, source_id, location, modality, excerpt FROM evidence ORDER BY atom_id, evidence_id"
        ).fetchall():
            evidence_by_unit[row["atom_id"]].append(dict(row))

    raw_atoms = []
    raw_ids_by_unit: dict[str, list[str]] = defaultdict(list)
    for unit in units:
        topics = json.loads(unit["topics_json"] or "[]")
        evidence_items = evidence_by_unit.get(unit["atom_id"]) or [
            {"source_id": source_id, "location": "", "modality": "unit", "excerpt": unit["statement"]}
            for source_id in json.loads(unit["source_ids_json"] or "[]")
        ]
        for item in evidence_items:
            source = sources[item["source_id"]]
            raw_id = stable_id(
                "ATM", item["source_id"], item.get("location") or "", item.get("excerpt") or "", unit["statement"]
            )
            raw_ids_by_unit[unit["atom_id"]].append(raw_id)
            raw_atoms.append(
                {
                    "id": raw_id,
                    "knowledge": unit["statement"],
                    "original": item.get("excerpt") or unit["statement"],
                    "source_id": item["source_id"],
                    "source_locator": item.get("location") or "",
                    "source_url": source.get("url") or "",
                    "date": source.get("published_at") or unit["created_at"],
                    "topics": topics,
                    "skills": ["creator-clone-lab"],
                    "type": {
                        "QST": "question", "CON": "concept", "OPI": "opinion", "CAS": "case",
                        "SOL": "solution", "HOK": "hook", "STR": "structure", "EXP": "expression",
                        "VIS": "visual", "CTA": "cta",
                    }[unit["atom_type"]],
                    "confidence": unit["confidence"],
                    "status": unit["status"],
                    "creator": source.get("creator") or "",
                    "platform": source.get("platform") or "",
                    "unit_ids": [unit["atom_id"]],
                    "created_at": unit["created_at"],
                }
            )
    atom_result = write_corpus(project, raw_atoms)

    old_unit_dir = project / "03_atoms"
    with connect_db(paths["database"]) as conn:
        for unit in units:
            evidence = evidence_by_unit.get(unit["atom_id"]) or []
            topics = json.loads(unit["topics_json"] or "[]")
            relationships = json.loads(unit["relationships_json"] or "[]")
            source_ids = json.loads(unit["source_ids_json"] or "[]")
            raw_atom_ids = list(dict.fromkeys(raw_ids_by_unit[unit["atom_id"]]))
            unit_kind = "content" if unit["atom_type"] in CONTENT_UNIT_TYPES else "creator-pattern"
            render_data = {
                "atom_id": unit["atom_id"],
                "atom_type": unit["atom_type"],
                "title": unit["title"],
                "statement": unit["statement"],
                "topics": topics,
                "confidence": unit["confidence"],
                "status": unit["status"],
                "performance_segment": unit["performance_segment"],
                "source_ids": source_ids,
                "raw_atom_ids": raw_atom_ids,
                "keywords": topics,
                "canonical": True,
                "version": 1,
                "unit_kind": unit_kind,
                "relationships": relationships,
                "created_at": unit["created_at"],
                "updated_at": now_iso(),
            }
            destination_dir = paths["content_units"] if unit_kind == "content" else paths["pattern_units"]
            old_file = project / unit["file_path"] if unit.get("file_path") else None
            filename = old_file.name if old_file and old_file.suffix == ".md" else f"{unit['atom_id']}.md"
            destination = destination_dir / filename
            destination.write_text(render_atom(render_data, evidence), encoding="utf-8")
            conn.execute(
                """
                UPDATE atoms SET file_path = ?, raw_atom_ids_json = ?, keywords_json = ?, canonical = 1,
                    version = 1, unit_kind = ?, updated_at = ? WHERE atom_id = ?
                """,
                (
                    destination.relative_to(project).as_posix(), json.dumps(raw_atom_ids, ensure_ascii=False),
                    json.dumps(topics, ensure_ascii=False), unit_kind, render_data["updated_at"], unit["atom_id"],
                ),
            )
    if old_unit_dir.exists():
        shutil.rmtree(old_unit_dir)

    project_file = project / "project.yaml"
    text = project_file.read_text(encoding="utf-8")
    lines = ["schema_version: 2.3" if line.startswith("schema_version:") else line for line in text.splitlines()]
    project_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = {
        "migrated_at": now_iso(),
        "raw_atom_count": atom_result["atom_count"],
        "shard_count": atom_result["shard_count"],
        "content_unit_count": sum(1 for unit in units if unit["atom_type"] in CONTENT_UNIT_TYPES),
        "creator_pattern_count": sum(1 for unit in units if unit["atom_type"] not in CONTENT_UNIT_TYPES),
    }
    (paths["state_dir"] / "v23_migration.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"migrate_project_to_atom_store failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
