#!/usr/bin/env python
"""Shared SQLite and file helpers for Creator Clone Lab V2."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "2.3"
ATOM_TYPES = {"QST", "CON", "OPI", "CAS", "SOL", "HOK", "STR", "EXP", "VIS", "CTA"}
CONTENT_UNIT_TYPES = {"QST", "CON", "OPI", "CAS", "SOL"}
PATTERN_UNIT_TYPES = {"HOK", "STR", "EXP", "VIS", "CTA"}
UNDERSTANDING_LEVELS = {"metadata-only", "partial", "full"}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slugify(value: str, fallback: str = "project") -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value).strip("-")
    return value or fallback


def stable_id(prefix: str, *parts: str, length: int = 12) -> str:
    payload = "\x1f".join(part.strip() for part in parts if part is not None)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:length].upper()
    return f"{prefix}-{digest}"


def project_paths(project: Path) -> dict[str, Path]:
    project = project.resolve()
    return {
        "root": project,
        "registry": project / "01_sources" / "source_registry.jsonl",
        "documents": project / "02_normalized" / "documents",
        "raw_atoms": project / "03_atom_store",
        "raw_atom_aggregate": project / "03_atom_store" / "atoms.jsonl",
        "raw_atom_shards": project / "03_atom_store" / "shards",
        "content_units": project / "04_content_units",
        "pattern_units": project / "05_creator_patterns",
        "topic_maps": project / "06_topic_maps",
        "creator_clone": project / "07_creator_clone",
        "creations": project / "08_creations",
        "performance": project / "09_performance",
        "state_dir": project / "10_state",
        "reports": project / "11_reports",
        "database": project / "index" / "knowledge.sqlite",
        "state": project / "10_state" / "current_state.json",
    }


def ensure_project(project: Path) -> dict[str, Path]:
    paths = project_paths(project)
    if not (paths["root"] / "project.yaml").exists():
        raise RuntimeError(f"not a Creator Clone Lab V2 project: {paths['root']}")
    return paths


def connect_db(database: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    initialize_schema(conn)
    return conn


def initialize_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sources (
            source_id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            creator TEXT,
            content_type TEXT NOT NULL,
            url TEXT,
            title TEXT,
            published_at TEXT,
            local_path TEXT,
            body_path TEXT,
            understanding_level TEXT NOT NULL,
            metrics_json TEXT NOT NULL DEFAULT '{}',
            sha256 TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS atoms (
            atom_id TEXT PRIMARY KEY,
            atom_type TEXT NOT NULL,
            title TEXT NOT NULL,
            statement TEXT NOT NULL,
            topics_json TEXT NOT NULL DEFAULT '[]',
            confidence TEXT NOT NULL,
            status TEXT NOT NULL,
            performance_segment TEXT,
            source_ids_json TEXT NOT NULL DEFAULT '[]',
            relationships_json TEXT NOT NULL DEFAULT '[]',
            file_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS raw_atoms (
            atom_id TEXT PRIMARY KEY,
            knowledge TEXT NOT NULL,
            original TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_locator TEXT,
            source_url TEXT,
            atom_date TEXT,
            topics_json TEXT NOT NULL DEFAULT '[]',
            skills_json TEXT NOT NULL DEFAULT '[]',
            atom_type TEXT NOT NULL,
            confidence TEXT NOT NULL,
            status TEXT NOT NULL,
            creator TEXT,
            platform TEXT,
            unit_ids_json TEXT NOT NULL DEFAULT '[]',
            shard TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(source_id) REFERENCES sources(source_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS evidence (
            evidence_id TEXT PRIMARY KEY,
            atom_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            location TEXT,
            modality TEXT,
            excerpt TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(atom_id) REFERENCES atoms(atom_id) ON DELETE CASCADE,
            FOREIGN KEY(source_id) REFERENCES sources(source_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS project_state (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS sources_fts USING fts5(
            source_id UNINDEXED,
            title,
            creator,
            body,
            tokenize='unicode61'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS atoms_fts USING fts5(
            atom_id UNINDEXED,
            title,
            statement,
            topics,
            tokenize='unicode61'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS raw_atoms_fts USING fts5(
            atom_id UNINDEXED,
            knowledge,
            original,
            topics,
            tokenize='unicode61'
        );
        """
    )
    atom_columns = {row[1] for row in conn.execute("PRAGMA table_info(atoms)").fetchall()}
    migrations = {
        "raw_atom_ids_json": "TEXT NOT NULL DEFAULT '[]'",
        "keywords_json": "TEXT NOT NULL DEFAULT '[]'",
        "canonical": "INTEGER NOT NULL DEFAULT 1",
        "version": "INTEGER NOT NULL DEFAULT 1",
        "unit_kind": "TEXT NOT NULL DEFAULT 'content'",
    }
    for column, definition in migrations.items():
        if column not in atom_columns:
            conn.execute(f"ALTER TABLE atoms ADD COLUMN {column} {definition}")
    conn.commit()


def json_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def load_json_argument(value: str | None, default: Any) -> Any:
    if not value:
        return default
    candidate = Path(value)
    if candidate.exists() and candidate.is_file():
        return json.loads(candidate.read_text(encoding="utf-8"))
    return json.loads(value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_or_absolute(path: Path | None, root: Path) -> str | None:
    if path is None:
        return None
    path = path.resolve()
    try:
        return path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def resolve_stored_path(value: str | None, root: Path) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else root / path


def rewrite_registry(conn: sqlite3.Connection, registry: Path) -> None:
    registry.parent.mkdir(parents=True, exist_ok=True)
    rows = conn.execute("SELECT * FROM sources ORDER BY created_at, source_id").fetchall()
    content = "".join(json.dumps(dict(row), ensure_ascii=False) + "\n" for row in rows)
    registry.write_text(content, encoding="utf-8")


def upsert_source_fts(conn: sqlite3.Connection, source_id: str, title: str, creator: str, body: str) -> None:
    conn.execute("DELETE FROM sources_fts WHERE source_id = ?", (source_id,))
    conn.execute(
        "INSERT INTO sources_fts(source_id, title, creator, body) VALUES (?, ?, ?, ?)",
        (source_id, title, creator, body),
    )


def upsert_atom_fts(conn: sqlite3.Connection, atom_id: str, title: str, statement: str, topics: Iterable[str]) -> None:
    conn.execute("DELETE FROM atoms_fts WHERE atom_id = ?", (atom_id,))
    conn.execute(
        "INSERT INTO atoms_fts(atom_id, title, statement, topics) VALUES (?, ?, ?, ?)",
        (atom_id, title, statement, " ".join(topics)),
    )


def upsert_raw_atom_fts(
    conn: sqlite3.Connection, atom_id: str, knowledge: str, original: str, topics: Iterable[str]
) -> None:
    conn.execute("DELETE FROM raw_atoms_fts WHERE atom_id = ?", (atom_id,))
    conn.execute(
        "INSERT INTO raw_atoms_fts(atom_id, knowledge, original, topics) VALUES (?, ?, ?, ?)",
        (atom_id, knowledge, original, " ".join(topics)),
    )


def parse_generated_atom(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError("missing JSON-compatible YAML frontmatter")
    _, frontmatter, body = text.split("---", 2)
    values: dict[str, Any] = {}
    for raw_line in frontmatter.strip().splitlines():
        if not raw_line.strip() or ":" not in raw_line:
            continue
        key, raw_value = raw_line.split(":", 1)
        raw_value = raw_value.strip()
        try:
            values[key.strip()] = json.loads(raw_value)
        except json.JSONDecodeError:
            values[key.strip()] = raw_value
    marker = "## Statement"
    if marker in body:
        values["statement"] = body.split(marker, 1)[1].split("\n## ", 1)[0].strip()
    return values
