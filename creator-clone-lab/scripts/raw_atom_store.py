#!/usr/bin/env python
"""Canonical JSONL atom corpus helpers for Creator Clone Lab."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from knowledge_store import connect_db, ensure_project, now_iso, stable_id, upsert_raw_atom_fts


RAW_ATOM_TYPES = {
    "observation",
    "quote",
    "metric",
    "question",
    "concept",
    "opinion",
    "case",
    "solution",
    "hook",
    "structure",
    "expression",
    "visual",
    "cta",
    "requirement",
    "decision",
    "insight",
}
CONFIDENCE = {"low", "medium", "high"}
STATUS = {"fact", "pattern", "hypothesis", "rejected"}


def quarter_for(value: str | None) -> str:
    text = (value or now_iso())[:10]
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = datetime.now().astimezone()
    return f"{parsed.year}Q{((parsed.month - 1) // 3) + 1}"


def jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"atom must be an object at {path}:{line_number}")
        rows.append(value)
    return rows


def normalize_atom(raw: dict[str, Any]) -> dict[str, Any]:
    atom = dict(raw)
    knowledge = str(atom.get("knowledge") or "").strip()
    original = str(atom.get("original") or "").strip()
    source_id = str(atom.get("source_id") or "").strip()
    source_locator = str(atom.get("source_locator") or "").strip()
    atom_type = str(atom.get("type") or "observation").strip().lower()
    confidence = str(atom.get("confidence") or "medium").strip().lower()
    status = str(atom.get("status") or "fact").strip().lower()
    if not knowledge or not original or not source_id:
        raise ValueError("knowledge, original, and source_id are required")
    if atom_type not in RAW_ATOM_TYPES:
        raise ValueError(f"unsupported raw atom type: {atom_type}")
    if confidence not in CONFIDENCE:
        raise ValueError(f"unsupported confidence: {confidence}")
    if status not in STATUS:
        raise ValueError(f"unsupported status: {status}")
    atom_date = str(atom.get("date") or atom.get("created_at") or now_iso())
    timestamp = now_iso()
    atom_id = str(atom.get("id") or stable_id("ATM", source_id, source_locator, original, knowledge))
    return {
        "id": atom_id,
        "knowledge": knowledge,
        "original": original,
        "source_id": source_id,
        "source_locator": source_locator,
        "source_url": str(atom.get("source_url") or ""),
        "date": atom_date,
        "topics": list(dict.fromkeys(str(item) for item in atom.get("topics") or [] if str(item).strip())),
        "skills": list(dict.fromkeys(str(item) for item in atom.get("skills") or [] if str(item).strip())),
        "type": atom_type,
        "confidence": confidence,
        "status": status,
        "creator": str(atom.get("creator") or ""),
        "platform": str(atom.get("platform") or ""),
        "unit_ids": list(dict.fromkeys(str(item) for item in atom.get("unit_ids") or [] if str(item).strip())),
        "shard": quarter_for(atom_date),
        "created_at": str(atom.get("created_at") or timestamp),
        "updated_at": timestamp,
    }


def load_corpus(project: Path) -> list[dict[str, Any]]:
    paths = ensure_project(project)
    aggregate = paths["raw_atom_aggregate"]
    if aggregate.exists():
        return [normalize_atom(atom) for atom in jsonl_rows(aggregate)]
    rows = []
    for path in sorted(paths["raw_atom_shards"].glob("atoms_*.jsonl")):
        rows.extend(normalize_atom(atom) for atom in jsonl_rows(path))
    return rows


def write_corpus(project: Path, atoms: Iterable[dict[str, Any]]) -> dict[str, int]:
    paths = ensure_project(project)
    normalized = {atom["id"]: atom for atom in (normalize_atom(item) for item in atoms)}
    ordered = sorted(normalized.values(), key=lambda item: (item["date"], item["id"]))
    with connect_db(paths["database"]) as conn:
        registered = {row["source_id"] for row in conn.execute("SELECT source_id FROM sources")}
        missing = sorted({atom["source_id"] for atom in ordered if atom["source_id"] not in registered})
        if missing:
            raise ValueError(f"raw atoms reference unregistered sources: {', '.join(missing)}")
        conn.execute("DELETE FROM raw_atoms")
        conn.execute("DELETE FROM raw_atoms_fts")
        for atom in ordered:
            conn.execute(
                """
                INSERT INTO raw_atoms(
                    atom_id, knowledge, original, source_id, source_locator, source_url, atom_date,
                    topics_json, skills_json, atom_type, confidence, status, creator, platform,
                    unit_ids_json, shard, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    atom["id"], atom["knowledge"], atom["original"], atom["source_id"],
                    atom["source_locator"], atom["source_url"], atom["date"],
                    json.dumps(atom["topics"], ensure_ascii=False),
                    json.dumps(atom["skills"], ensure_ascii=False), atom["type"],
                    atom["confidence"], atom["status"], atom["creator"], atom["platform"],
                    json.dumps(atom["unit_ids"], ensure_ascii=False), atom["shard"],
                    atom["created_at"], atom["updated_at"],
                ),
            )
            upsert_raw_atom_fts(conn, atom["id"], atom["knowledge"], atom["original"], atom["topics"])
    paths["raw_atoms"].mkdir(parents=True, exist_ok=True)
    paths["raw_atom_shards"].mkdir(parents=True, exist_ok=True)
    for old_shard in paths["raw_atom_shards"].glob("atoms_*.jsonl"):
        old_shard.unlink()
    aggregate_text = "".join(json.dumps(atom, ensure_ascii=False) + "\n" for atom in ordered)
    paths["raw_atom_aggregate"].write_text(aggregate_text, encoding="utf-8")
    by_shard: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for atom in ordered:
        by_shard[atom["shard"]].append(atom)
    for shard, shard_atoms in sorted(by_shard.items()):
        path = paths["raw_atom_shards"] / f"atoms_{shard}.jsonl"
        path.write_text("".join(json.dumps(atom, ensure_ascii=False) + "\n" for atom in shard_atoms), encoding="utf-8")
    return {"atom_count": len(ordered), "shard_count": len(by_shard)}
