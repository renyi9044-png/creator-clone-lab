#!/usr/bin/env python
"""Search thousands of JSONL atoms with source traceability and CJK fallback."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from query_knowledge import fallback_terms, substring_score
from raw_atom_store import load_corpus


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("query")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--topic", default="")
    parser.add_argument("--type", default="")
    parser.add_argument("--source-id", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    terms = fallback_terms(args.query)
    ranked = []
    for atom in load_corpus(Path(args.project_dir).resolve()):
        if args.topic and args.topic not in atom["topics"]:
            continue
        if args.type and atom["type"] != args.type:
            continue
        if args.source_id and atom["source_id"] != args.source_id:
            continue
        searchable = " ".join(
            [atom["knowledge"], atom["original"], " ".join(atom["topics"]), " ".join(atom["skills"])]
        )
        score = substring_score(searchable, terms)
        if score:
            ranked.append((score, atom))
    results = [atom for _, atom in sorted(ranked, key=lambda item: item[0], reverse=True)[: args.limit]]
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0
    if not results:
        print("no raw atom found")
        return 0
    for index, atom in enumerate(results, start=1):
        print(f"[{index}] {atom['id']} [{atom['type']}/{atom['confidence']}/{atom['status']}]")
        print(f"    knowledge: {atom['knowledge']}")
        print(f"    original: {atom['original']}")
        print(f"    source: {atom['source_id']} @ {atom['source_locator'] or 'unspecified'}")
        print(f"    topics: {', '.join(atom['topics'])}")
        if atom["unit_ids"]:
            print(f"    promoted to: {', '.join(atom['unit_ids'])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"query_raw_atoms failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
