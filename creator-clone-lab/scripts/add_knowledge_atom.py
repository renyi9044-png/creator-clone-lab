#!/usr/bin/env python
"""Create one promoted content or creator-pattern unit and index it."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from knowledge_store import (
    ATOM_TYPES,
    CONTENT_UNIT_TYPES,
    connect_db,
    ensure_project,
    now_iso,
    slugify,
    stable_id,
    upsert_atom_fts,
)


CONFIDENCE = {"low", "medium", "high"}
STATUS = {"fact", "pattern", "hypothesis", "rejected"}
RELATIONSHIPS = {"responds_to", "explains", "proves", "conflicts_with", "follows", "adapts_to"}


def load_list(value: str, label: str) -> list[dict]:
    if not value:
        return []
    candidate = Path(value)
    data = json.loads(candidate.read_text(encoding="utf-8")) if candidate.exists() else json.loads(value)
    if not isinstance(data, list):
        raise ValueError(f"{label} must be a JSON array")
    return data


def render_atom(atom: dict, evidence: list[dict]) -> str:
    fields = {
        "id": atom["atom_id"],
        "type": atom["atom_type"],
        "title": atom["title"],
        "topics": atom["topics"],
        "confidence": atom["confidence"],
        "status": atom["status"],
        "performance_segment": atom["performance_segment"],
        "source_ids": atom["source_ids"],
        "raw_atom_ids": atom["raw_atom_ids"],
        "keywords": atom["keywords"],
        "canonical": atom["canonical"],
        "version": atom["version"],
        "unit_kind": atom["unit_kind"],
        "relationships": atom["relationships"],
        "created_at": atom["created_at"],
        "updated_at": atom["updated_at"],
    }
    frontmatter = "\n".join(f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in fields.items())
    evidence_lines = []
    for item in evidence:
        evidence_lines.append(
            f"- `{item['source_id']}` | {item.get('location') or 'unspecified'} | "
            f"{item.get('modality') or 'unspecified'} | {item.get('excerpt') or ''}"
        )
    evidence_text = "\n".join(evidence_lines) or "- No evidence recorded."
    return f"---\n{frontmatter}\n---\n\n# {atom['title']}\n\n## Statement\n\n{atom['statement']}\n\n## Evidence\n\n{evidence_text}\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--type", required=True, choices=sorted(ATOM_TYPES))
    parser.add_argument("--title", required=True)
    parser.add_argument("--statement", required=True)
    parser.add_argument("--topic", action="append", default=[])
    parser.add_argument("--confidence", default="medium", choices=sorted(CONFIDENCE))
    parser.add_argument("--status", default="hypothesis", choices=sorted(STATUS))
    parser.add_argument("--performance-segment", default="")
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--raw-atom-id", action="append", default=[])
    parser.add_argument("--keyword", action="append", default=[])
    parser.add_argument("--canonical", choices=["true", "false"], default="true")
    parser.add_argument("--version", type=int, default=1)
    parser.add_argument("--evidence", default="", help="JSON array or JSON file")
    parser.add_argument(
        "--evidence-item",
        action="append",
        default=[],
        help="Evidence as source_id|location|modality|excerpt; repeat as needed",
    )
    parser.add_argument("--relationships", default="", help="JSON array or JSON file")
    parser.add_argument("--atom-id", default="")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    paths = ensure_project(project)
    evidence = load_list(args.evidence, "evidence")
    for raw_item in args.evidence_item:
        parts = raw_item.split("|", 3)
        if len(parts) != 4:
            raise ValueError("evidence-item must be source_id|location|modality|excerpt")
        evidence.append(
            {"source_id": parts[0], "location": parts[1], "modality": parts[2], "excerpt": parts[3]}
        )
    relationships = load_list(args.relationships, "relationships")
    for relation in relationships:
        if relation.get("type") not in RELATIONSHIPS:
            raise ValueError(f"unsupported relationship: {relation.get('type')}")

    source_ids = list(dict.fromkeys(args.source_id + [item.get("source_id") for item in evidence if item.get("source_id")]))
    if not source_ids:
        raise ValueError("at least one --source-id or evidence source_id is required")

    with connect_db(paths["database"]) as conn:
        registered = {row["source_id"] for row in conn.execute("SELECT source_id FROM sources").fetchall()}
        missing = [source_id for source_id in source_ids if source_id not in registered]
        if missing:
            raise ValueError(f"unregistered source IDs: {', '.join(missing)}")
        registered_raw_atoms = {row["atom_id"] for row in conn.execute("SELECT atom_id FROM raw_atoms").fetchall()}
        missing_raw_atoms = [atom_id for atom_id in args.raw_atom_id if atom_id not in registered_raw_atoms]
        if missing_raw_atoms:
            raise ValueError(f"unregistered raw atom IDs: {', '.join(missing_raw_atoms)}")

        timestamp = now_iso()
        atom_id = args.atom_id or stable_id(args.type, args.title, args.statement)
        existing = conn.execute("SELECT created_at FROM atoms WHERE atom_id = ?", (atom_id,)).fetchone()
        created_at = existing["created_at"] if existing else timestamp
        atom = {
            "atom_id": atom_id,
            "atom_type": args.type,
            "title": args.title,
            "statement": args.statement,
            "topics": args.topic,
            "confidence": args.confidence,
            "status": args.status,
            "performance_segment": args.performance_segment or None,
            "source_ids": source_ids,
            "raw_atom_ids": list(dict.fromkeys(args.raw_atom_id)),
            "keywords": list(dict.fromkeys(args.keyword)),
            "canonical": args.canonical == "true",
            "version": args.version,
            "unit_kind": "content" if args.type in CONTENT_UNIT_TYPES else "creator-pattern",
            "relationships": relationships,
            "created_at": created_at,
            "updated_at": timestamp,
        }
        filename = f"{atom_id}_{slugify(args.title, 'atom')}.md"
        output_dir = paths["content_units"] if args.type in CONTENT_UNIT_TYPES else paths["pattern_units"]
        output_dir.mkdir(parents=True, exist_ok=True)
        atom_file = output_dir / filename
        atom_file.write_text(render_atom(atom, evidence), encoding="utf-8")

        conn.execute(
            """
            INSERT INTO atoms(
                atom_id, atom_type, title, statement, topics_json, confidence, status,
                performance_segment, source_ids_json, relationships_json, file_path, created_at, updated_at,
                raw_atom_ids_json, keywords_json, canonical, version, unit_kind
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(atom_id) DO UPDATE SET
                atom_type=excluded.atom_type, title=excluded.title, statement=excluded.statement,
                topics_json=excluded.topics_json, confidence=excluded.confidence, status=excluded.status,
                performance_segment=excluded.performance_segment, source_ids_json=excluded.source_ids_json,
                relationships_json=excluded.relationships_json, file_path=excluded.file_path,
                raw_atom_ids_json=excluded.raw_atom_ids_json, keywords_json=excluded.keywords_json,
                canonical=excluded.canonical, version=excluded.version, unit_kind=excluded.unit_kind,
                updated_at=excluded.updated_at
            """,
            (
                atom_id,
                args.type,
                args.title,
                args.statement,
                json.dumps(args.topic, ensure_ascii=False),
                args.confidence,
                args.status,
                args.performance_segment,
                json.dumps(source_ids, ensure_ascii=False),
                json.dumps(relationships, ensure_ascii=False),
                atom_file.relative_to(project).as_posix(),
                created_at,
                timestamp,
                json.dumps(atom["raw_atom_ids"], ensure_ascii=False),
                json.dumps(atom["keywords"], ensure_ascii=False),
                1 if atom["canonical"] else 0,
                atom["version"],
                atom["unit_kind"],
            ),
        )
        conn.execute("DELETE FROM evidence WHERE atom_id = ?", (atom_id,))
        for index, item in enumerate(evidence, start=1):
            evidence_id = stable_id("EVD", atom_id, item["source_id"], str(index), item.get("location", ""))
            conn.execute(
                "INSERT INTO evidence(evidence_id, atom_id, source_id, location, modality, excerpt, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    evidence_id,
                    atom_id,
                    item["source_id"],
                    item.get("location", ""),
                    item.get("modality", ""),
                    item.get("excerpt", ""),
                    timestamp,
                ),
            )
        upsert_atom_fts(conn, atom_id, args.title, args.statement, args.topic)

    if atom["raw_atom_ids"]:
        from raw_atom_store import load_corpus, write_corpus

        corpus = load_corpus(project)
        selected = set(atom["raw_atom_ids"])
        for raw_atom in corpus:
            if raw_atom["id"] in selected and atom_id not in raw_atom["unit_ids"]:
                raw_atom["unit_ids"].append(atom_id)
        write_corpus(project, corpus)

    print(f"atom_id: {atom_id}")
    print(f"file: {atom_file}")
    print(f"sources: {', '.join(source_ids)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"add_knowledge_atom failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
