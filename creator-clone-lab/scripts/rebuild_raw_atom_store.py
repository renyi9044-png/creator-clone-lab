#!/usr/bin/env python
"""Validate, deduplicate, shard, aggregate, and reindex the JSONL atom corpus."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from knowledge_store import ensure_project
from raw_atom_store import jsonl_rows, normalize_atom, write_corpus


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: rebuild_raw_atom_store.py <project_dir>", file=sys.stderr)
        return 2
    project = Path(sys.argv[1]).resolve()
    paths = ensure_project(project)
    inputs = sorted(paths["raw_atom_shards"].glob("atoms_*.jsonl"))
    if not inputs and paths["raw_atom_aggregate"].exists():
        inputs = [paths["raw_atom_aggregate"]]
    atoms = []
    for path in inputs:
        atoms.extend(normalize_atom(atom) for atom in jsonl_rows(path))
    result = write_corpus(project, atoms)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"rebuild_raw_atom_store failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
