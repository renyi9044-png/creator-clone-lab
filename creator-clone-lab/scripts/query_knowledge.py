#!/usr/bin/env python
"""Search source documents and evidence-backed knowledge atoms with citations."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from knowledge_store import connect_db, ensure_project


def fts_query(text: str) -> str:
    tokens = [token.replace('"', '') for token in text.split() if token.strip()]
    return " OR ".join(f'"{token}"' for token in tokens) or '""'


def fallback_terms(text: str, limit: int = 32) -> list[str]:
    """Build substring terms for CJK queries that unicode61 cannot segment."""
    terms = re.findall(r"[a-z0-9_]{2,}", text.lower())
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        if len(run) <= 4:
            terms.append(run)
        for size in (2, 3):
            terms.extend(run[index : index + size] for index in range(len(run) - size + 1))
    return list(dict.fromkeys(term for term in terms if term))[:limit]


def substring_score(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(min(lowered.count(term), 3) * len(term) for term in terms)


def text_snippet(text: str, terms: list[str], width: int = 120) -> str:
    positions = [text.lower().find(term) for term in terms if text.lower().find(term) >= 0]
    start = max(0, (min(positions) if positions else 0) - 24)
    snippet = text[start : start + width].replace("\n", " ").strip()
    return ("..." if start else "") + snippet + ("..." if start + width < len(text) else "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    paths = ensure_project(project)
    match = fts_query(args.query)
    terms = fallback_terms(args.query)
    results: list[dict] = []
    with connect_db(paths["database"]) as conn:
        atoms = conn.execute(
            """
            SELECT a.*, bm25(atoms_fts) AS score
            FROM atoms_fts JOIN atoms a ON a.atom_id = atoms_fts.atom_id
            WHERE atoms_fts MATCH ?
            ORDER BY score LIMIT ?
            """,
            (match, args.limit),
        ).fetchall()
        for row in atoms:
            evidence = conn.execute(
                "SELECT source_id, location, modality, excerpt FROM evidence WHERE atom_id = ? ORDER BY evidence_id",
                (row["atom_id"],),
            ).fetchall()
            results.append(
                {
                    "kind": "atom",
                    "id": row["atom_id"],
                    "type": row["atom_type"],
                    "title": row["title"],
                    "statement": row["statement"],
                    "confidence": row["confidence"],
                    "status": row["status"],
                    "score": row["score"],
                    "evidence": [dict(item) for item in evidence],
                }
            )
        seen_atoms = {item["id"] for item in results if item["kind"] == "atom"}
        fallback_atoms = []
        for row in conn.execute("SELECT * FROM atoms").fetchall():
            score = substring_score(f"{row['title']} {row['statement']} {row['topics_json']}", terms)
            if score and row["atom_id"] not in seen_atoms:
                fallback_atoms.append((score, row))
        for relevance, row in sorted(fallback_atoms, key=lambda item: item[0], reverse=True)[: args.limit]:
            evidence = conn.execute(
                "SELECT source_id, location, modality, excerpt FROM evidence WHERE atom_id = ? ORDER BY evidence_id",
                (row["atom_id"],),
            ).fetchall()
            results.append(
                {
                    "kind": "atom",
                    "id": row["atom_id"],
                    "type": row["atom_type"],
                    "title": row["title"],
                    "statement": row["statement"],
                    "confidence": row["confidence"],
                    "status": row["status"],
                    "score": 50.0 - relevance,
                    "evidence": [dict(item) for item in evidence],
                }
            )
        sources = conn.execute(
            """
            SELECT s.*, snippet(sources_fts, 3, '[', ']', '...', 24) AS snippet, bm25(sources_fts) AS score
            FROM sources_fts JOIN sources s ON s.source_id = sources_fts.source_id
            WHERE sources_fts MATCH ?
            ORDER BY score LIMIT ?
            """,
            (match, args.limit),
        ).fetchall()
        for row in sources:
            results.append(
                {
                    "kind": "source",
                    "id": row["source_id"],
                    "platform": row["platform"],
                    "title": row["title"],
                    "creator": row["creator"],
                    "url": row["url"],
                    "understanding_level": row["understanding_level"],
                    "snippet": row["snippet"],
                    "score": row["score"],
                }
            )
        seen_sources = {item["id"] for item in results if item["kind"] == "source"}
        fallback_sources = []
        for row in conn.execute(
            "SELECT s.*, f.body AS indexed_body FROM sources s LEFT JOIN sources_fts f ON s.source_id = f.source_id"
        ).fetchall():
            searchable = f"{row['title'] or ''} {row['creator'] or ''} {row['indexed_body'] or ''}"
            score = substring_score(searchable, terms)
            if score and row["source_id"] not in seen_sources:
                fallback_sources.append((score, row, searchable))
        for relevance, row, searchable in sorted(fallback_sources, key=lambda item: item[0], reverse=True)[: args.limit]:
            results.append(
                {
                    "kind": "source",
                    "id": row["source_id"],
                    "platform": row["platform"],
                    "title": row["title"],
                    "creator": row["creator"],
                    "url": row["url"],
                    "understanding_level": row["understanding_level"],
                    "snippet": text_snippet(searchable, terms),
                    "score": 50.0 - relevance,
                }
            )
        raw_atoms = conn.execute(
            """
            SELECT r.*, bm25(raw_atoms_fts) AS score
            FROM raw_atoms_fts JOIN raw_atoms r ON r.atom_id = raw_atoms_fts.atom_id
            WHERE raw_atoms_fts MATCH ?
            ORDER BY score LIMIT ?
            """,
            (match, args.limit),
        ).fetchall()
        for row in raw_atoms:
            results.append(
                {
                    "kind": "raw-atom",
                    "id": row["atom_id"],
                    "title": row["knowledge"],
                    "knowledge": row["knowledge"],
                    "original": row["original"],
                    "source_id": row["source_id"],
                    "source_locator": row["source_locator"],
                    "type": row["atom_type"],
                    "confidence": row["confidence"],
                    "status": row["status"],
                    "score": row["score"],
                }
            )
        seen_raw_atoms = {item["id"] for item in results if item["kind"] == "raw-atom"}
        fallback_raw_atoms = []
        for row in conn.execute("SELECT * FROM raw_atoms").fetchall():
            searchable = f"{row['knowledge']} {row['original']} {row['topics_json']}"
            score = substring_score(searchable, terms)
            if score and row["atom_id"] not in seen_raw_atoms:
                fallback_raw_atoms.append((score, row))
        for relevance, row in sorted(fallback_raw_atoms, key=lambda item: item[0], reverse=True)[: args.limit]:
            results.append(
                {
                    "kind": "raw-atom",
                    "id": row["atom_id"],
                    "title": row["knowledge"],
                    "knowledge": row["knowledge"],
                    "original": row["original"],
                    "source_id": row["source_id"],
                    "source_locator": row["source_locator"],
                    "type": row["atom_type"],
                    "confidence": row["confidence"],
                    "status": row["status"],
                    "score": 50.0 - relevance,
                }
            )
    results.sort(key=lambda item: item.get("score", 0))
    results = results[: args.limit]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    if not results:
        print("no evidence-backed result found")
        return 0
    for index, item in enumerate(results, start=1):
        print(f"[{index}] {item['kind']} {item['id']} | {item.get('title') or ''}")
        if item["kind"] == "atom":
            print(f"    {item['statement']}")
            print(f"    status={item['status']} confidence={item['confidence']}")
            for evidence in item["evidence"]:
                print(
                    f"    evidence: {evidence['source_id']} @ {evidence.get('location') or 'unspecified'} "
                    f"({evidence.get('modality') or 'unspecified'}) {evidence.get('excerpt') or ''}"
                )
        elif item["kind"] == "raw-atom":
            print(f"    {item['knowledge']}")
            print(f"    original: {item['original']}")
            print(
                f"    source: {item['source_id']} @ {item.get('source_locator') or 'unspecified'} "
                f"status={item['status']} confidence={item['confidence']}"
            )
        else:
            print(f"    {item.get('snippet') or ''}")
            print(f"    source: {item.get('url') or item['id']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"query_knowledge failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
