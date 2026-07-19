#!/usr/bin/env python
"""Import or update a batch in the canonical JSONL raw atom corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from raw_atom_store import jsonl_rows, load_corpus, normalize_atom, write_corpus


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("jsonl_file")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    incoming_path = Path(args.jsonl_file).resolve()
    existing = {atom["id"]: atom for atom in load_corpus(project)}
    incoming = [normalize_atom(atom) for atom in jsonl_rows(incoming_path)]
    for atom in incoming:
        existing[atom["id"]] = atom
    result = write_corpus(project, existing.values())
    report = {"input": str(incoming_path), "imported_or_updated": len(incoming), **result}
    state_dir = project / "10_state"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "last_raw_atom_import.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"import_raw_atom_batch failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
