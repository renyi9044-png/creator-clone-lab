#!/usr/bin/env python
"""Generate reviewable duplicate unit candidates without merging automatically."""

from __future__ import annotations

import argparse
import json
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

from knowledge_store import connect_db, ensure_project, now_iso


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", text.lower())


def ngrams(text: str, size: int = 2) -> set[str]:
    text = normalize(text)
    if len(text) <= size:
        return {text} if text else set()
    return {text[index : index + size] for index in range(len(text) - size + 1)}


def similarity(left: str, right: str) -> float:
    left_normalized = normalize(left)
    right_normalized = normalize(right)
    sequence = SequenceMatcher(None, left_normalized, right_normalized).ratio()
    left_grams = ngrams(left)
    right_grams = ngrams(right)
    union = left_grams | right_grams
    jaccard = len(left_grams & right_grams) / len(union) if union else 0.0
    return max(sequence, jaccard)


def classify(score: float) -> str:
    if score >= 0.97:
        return "exact_or_synonym"
    if score >= 0.90:
        return "near_duplicate"
    return "repeated_telling"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--threshold", type=float, default=0.84)
    parser.add_argument("--cross-type", action="store_true")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    paths = ensure_project(project)
    with connect_db(paths["database"]) as conn:
        atoms = [dict(row) for row in conn.execute("SELECT atom_id, atom_type, title, statement, status FROM atoms ORDER BY atom_id")]
    candidates = []
    for index, left in enumerate(atoms):
        for right in atoms[index + 1 :]:
            if not args.cross_type and left["atom_type"] != right["atom_type"]:
                continue
            score = similarity(f"{left['title']} {left['statement']}", f"{right['title']} {right['statement']}")
            if score < args.threshold:
                continue
            candidates.append(
                {
                    "left": left["atom_id"],
                    "right": right["atom_id"],
                    "left_type": left["atom_type"],
                    "right_type": right["atom_type"],
                    "score": round(score, 4),
                    "classification": classify(score),
                    "action": "review",
                }
            )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    report = {"generated_at": now_iso(), "threshold": args.threshold, "candidate_count": len(candidates), "candidates": candidates}
    output = paths["state_dir"] / "duplicate_candidates.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"duplicate candidates: {len(candidates)}")
    print(f"saved: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"generate_duplicate_candidates failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
