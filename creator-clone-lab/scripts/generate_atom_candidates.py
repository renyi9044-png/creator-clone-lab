#!/usr/bin/env python
"""Generate reviewable raw-atom duplicate and promotion candidates at batch scale."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from generate_duplicate_candidates import classify, ngrams, normalize, similarity
from knowledge_store import ensure_project, now_iso, stable_id
from raw_atom_store import load_corpus


PROMOTION_TYPES = {
    "question": "QST",
    "concept": "CON",
    "opinion": "OPI",
    "case": "CAS",
    "solution": "SOL",
    "hook": "HOK",
    "structure": "STR",
    "expression": "EXP",
    "visual": "VIS",
    "cta": "CTA",
}


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, value: str) -> str:
        self.parent.setdefault(value, value)
        if self.parent[value] != value:
            self.parent[value] = self.find(self.parent[value])
        return self.parent[value]

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def candidate_pairs(atoms: list[dict], max_bucket: int) -> set[tuple[str, str]]:
    inverted: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for atom in atoms:
        topics = atom["topics"] or ["__unclassified__"]
        grams = ngrams(atom["knowledge"])
        for topic in topics:
            for gram in grams:
                inverted[(atom["type"], topic, gram)].append(atom["id"])
    pairs: set[tuple[str, str]] = set()
    for ids in inverted.values():
        unique = sorted(set(ids))
        if len(unique) < 2 or len(unique) > max_bucket:
            continue
        pairs.update(combinations(unique, 2))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--duplicate-threshold", type=float, default=0.86)
    parser.add_argument("--promotion-threshold", type=float, default=0.90)
    parser.add_argument("--max-bucket", type=int, default=300)
    parser.add_argument("--max-candidates", type=int, default=5000)
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    paths = ensure_project(project)
    atoms = load_corpus(project)
    by_id = {atom["id"]: atom for atom in atoms}
    pairs = candidate_pairs(atoms, args.max_bucket)
    duplicates = []
    union = UnionFind()
    for left_id, right_id in pairs:
        left, right = by_id[left_id], by_id[right_id]
        score = similarity(left["knowledge"], right["knowledge"])
        if score < args.duplicate_threshold:
            continue
        shared_topics = sorted(set(left["topics"]) & set(right["topics"]))
        candidate = {
            "candidate_id": stable_id("DUP", left_id, right_id),
            "kind": "raw_duplicate",
            "left": left_id,
            "right": right_id,
            "score": round(score, 4),
            "classification": classify(score),
            "same_source": left["source_id"] == right["source_id"],
            "shared_topics": shared_topics,
            "left_knowledge": left["knowledge"],
            "right_knowledge": right["knowledge"],
            "recommendation": "review",
        }
        duplicates.append(candidate)
        if score >= args.promotion_threshold and left["type"] == right["type"]:
            union.union(left_id, right_id)
    duplicates.sort(key=lambda item: (-item["score"], item["candidate_id"]))
    duplicates = duplicates[: args.max_candidates]

    groups: dict[str, list[str]] = defaultdict(list)
    for atom_id in union.parent:
        groups[union.find(atom_id)].append(atom_id)
    promotions = []
    for ids in groups.values():
        unique_ids = sorted(set(ids))
        group_atoms = [by_id[atom_id] for atom_id in unique_ids]
        sources = sorted({atom["source_id"] for atom in group_atoms})
        promoted_sets = [set(atom.get("unit_ids") or []) for atom in group_atoms]
        common_promoted_units = set.intersection(*promoted_sets) if promoted_sets else set()
        raw_type = group_atoms[0]["type"]
        promoted_type = PROMOTION_TYPES.get(raw_type)
        if not promoted_type or len(unique_ids) < 2 or len(sources) < 2 or common_promoted_units:
            continue
        representative = max(
            group_atoms,
            key=lambda atom: (len(atom["knowledge"]), atom["confidence"] == "high", atom["id"]),
        )
        topics = sorted({topic for atom in group_atoms for topic in atom["topics"]})
        evidence = [
            {
                "source_id": atom["source_id"],
                "location": atom["source_locator"],
                "modality": "raw-atom",
                "excerpt": atom["original"],
            }
            for atom in group_atoms
        ]
        promotions.append(
            {
                "candidate_id": stable_id("PRM", promoted_type, *unique_ids),
                "kind": "promotion",
                "suggested_type": promoted_type,
                "suggested_title": representative["knowledge"][:60],
                "suggested_statement": representative["knowledge"],
                "raw_atom_ids": unique_ids,
                "source_ids": sources,
                "topics": topics,
                "evidence": evidence,
                "confidence": "high" if len(sources) >= 3 else "medium",
                "status": "pattern" if len(sources) >= 3 else "hypothesis",
                "reason": f"{len(unique_ids)} similar atoms across {len(sources)} independent sources",
                "recommendation": "review",
            }
        )
    promotions.sort(key=lambda item: (-len(item["source_ids"]), -len(item["raw_atom_ids"]), item["candidate_id"]))
    generated_at = now_iso()
    duplicate_report = {
        "generated_at": generated_at,
        "atom_count": len(atoms),
        "pair_count": len(pairs),
        "threshold": args.duplicate_threshold,
        "candidate_count": len(duplicates),
        "candidates": duplicates,
    }
    promotion_report = {
        "generated_at": generated_at,
        "candidate_count": len(promotions),
        "candidates": promotions,
    }
    duplicate_path = paths["state_dir"] / "raw_duplicate_candidates.json"
    promotion_path = paths["state_dir"] / "promotion_candidates.json"
    duplicate_path.write_text(json.dumps(duplicate_report, ensure_ascii=False, indent=2), encoding="utf-8")
    promotion_path.write_text(json.dumps(promotion_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "raw_atoms": len(atoms),
                "duplicate_candidates": len(duplicates),
                "promotion_candidates": len(promotions),
                "duplicate_report": str(duplicate_path),
                "promotion_report": str(promotion_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"generate_atom_candidates failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
