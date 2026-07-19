#!/usr/bin/env python
"""Initialize a local Creator Clone Lab V2 knowledge project."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from knowledge_store import SCHEMA_VERSION, connect_db, now_iso, project_paths, slugify


DIRECTORIES = [
    "00_rules",
    "01_sources/raw",
    "01_sources/media",
    "02_normalized/transcripts",
    "02_normalized/ocr",
    "02_normalized/frames",
    "02_normalized/documents",
    "03_atom_store/shards",
    "04_content_units",
    "05_creator_patterns",
    "06_topic_maps",
    "07_creator_clone",
    "08_creations",
    "09_performance",
    "10_state",
    "11_reports",
    "index",
]


def write_if_missing(path: Path, content: str) -> None:
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def initialize(project: Path, name: str, creator: str, platforms: list[str]) -> None:
    project.mkdir(parents=True, exist_ok=True)
    for directory in DIRECTORIES:
        (project / directory).mkdir(parents=True, exist_ok=True)

    created_at = now_iso()
    platform_list = json.dumps(platforms or ["unknown"], ensure_ascii=False)
    write_if_missing(
        project / "project.yaml",
        f"schema_version: {SCHEMA_VERSION}\nproject_name: {name}\nproject_slug: {slugify(name)}\ncreator_name: {creator or 'unknown'}\nplatforms: {platform_list}\nmode: audit\ncreated_at: {created_at}\n",
    )
    write_if_missing(
        project / "SOURCE_OF_TRUTH.md",
        "# Source Of Truth\n\n"
        "1. Raw sources are immutable. Never rewrite files under `01_sources/raw/` or `01_sources/media/`.\n"
        "2. `source_registry.jsonl` defines registered sources.\n"
        "3. `03_atom_store/atoms.jsonl` and quarterly shards preserve atomic evidence at scale.\n"
        "4. `04_content_units/` and `05_creator_patterns/` contain reviewed units promoted from raw atom IDs.\n"
        "5. SQLite accelerates retrieval and is rebuildable from portable artifacts.\n"
        "6. Facts, patterns, hypotheses, and rejected claims must remain distinguishable.\n"
        "7. Performance data changes confidence; it does not silently rewrite history.\n",
    )
    write_if_missing(
        project / "AGENTS.md",
        "# Project Rules\n\n"
        "Read `SOURCE_OF_TRUTH.md`, `10_state/current_state.json`, and `00_rules/` before editing knowledge.\n"
        "Store atomic evidence in JSONL first and promote only reviewed atoms into Markdown units.\n"
        "Prefer evidence over impression. Cite raw atom IDs, source IDs, and timestamps/pages.\n"
        "Do not call a creator clone stable until quality gates pass.\n"
        "Do not expose cookies, login tokens, API keys, or signed media URLs.\n",
    )
    write_if_missing(
        project / "00_rules" / "knowledge_model.md",
        "# Knowledge Model\n\n"
        "Raw JSON atoms are the evidence inventory. Promote them into Markdown units only after semantic review.\n\n"
        "Content unit types: QST audience question, CON concept, OPI opinion, CAS case, SOL solution.\n"
        "Creator pattern types: HOK hook, STR structure, EXP expression, VIS visual pattern, CTA ending or conversion action.\n\n"
        "Allowed statuses: fact, pattern, hypothesis, rejected.\n"
        "Allowed relationships: responds_to, explains, proves, conflicts_with, follows, adapts_to.\n",
    )
    write_if_missing(
        project / "00_rules" / "evidence_policy.md",
        "# Evidence Policy\n\n"
        "Each atom must cite at least one registered source. Patterns require multiple independent samples.\n"
        "For video, include a timestamp or frame range. For image-text, include a page or image index.\n"
        "For articles, include a section or paragraph locator. Mark metadata-only samples as incomplete.\n",
    )
    write_if_missing(
        project / "00_rules" / "quality_gates.md",
        "# Quality Gates\n\n"
        "- 1-9 understood samples: quick analysis only.\n"
        "- 10-29 understood samples: provisional creator clone.\n"
        "- 30+ samples across high and weak performance bands: stable candidate.\n"
        "- A stable clone requires source traceability, counterexamples, and at least one retrospective update.\n",
    )
    state = {
        "schema_version": SCHEMA_VERSION,
        "mode": "audit",
        "project_name": name,
        "creator_name": creator or None,
        "created_at": created_at,
        "updated_at": created_at,
        "source_count": 0,
        "atom_count": 0,
        "open_questions": [],
        "next_action": "Register source material and process a representative sample.",
    }
    write_if_missing(project / "10_state" / "current_state.json", json.dumps(state, ensure_ascii=False, indent=2))
    write_if_missing(project / "01_sources" / "source_registry.jsonl", "")
    write_if_missing(project / "03_atom_store" / "atoms.jsonl", "")
    paths = project_paths(project)
    with connect_db(paths["database"]):
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", help="New project directory")
    parser.add_argument("--name", required=True, help="Human-readable project name")
    parser.add_argument("--creator", default="", help="Creator or account name")
    parser.add_argument("--platform", action="append", default=[], help="Platform; repeat for multiple platforms")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    initialize(project, args.name, args.creator, args.platform)
    print(f"project: {project}")
    print(f"database: {project / 'index' / 'knowledge.sqlite'}")
    print("mode: audit")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"init_creator_project failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
