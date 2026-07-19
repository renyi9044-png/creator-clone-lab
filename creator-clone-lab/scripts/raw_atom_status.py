#!/usr/bin/env python
"""Report scale, coverage, types, topics, and promotion rate of the raw atom corpus."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from raw_atom_store import load_corpus


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: raw_atom_status.py <project_dir>", file=sys.stderr)
        return 2
    atoms = load_corpus(Path(sys.argv[1]).resolve())
    promoted = sum(1 for atom in atoms if atom["unit_ids"])
    report = {
        "atom_count": len(atoms),
        "shards": dict(Counter(atom["shard"] for atom in atoms)),
        "types": dict(Counter(atom["type"] for atom in atoms)),
        "statuses": dict(Counter(atom["status"] for atom in atoms)),
        "top_topics": Counter(topic for atom in atoms for topic in atom["topics"]).most_common(20),
        "source_count": len({atom["source_id"] for atom in atoms}),
        "promoted_atom_count": promoted,
        "promotion_rate": round(promoted / len(atoms), 4) if atoms else 0.0,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"raw_atom_status failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
