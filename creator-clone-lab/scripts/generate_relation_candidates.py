#!/usr/bin/env python
"""Discover typed, reviewable relationships between promoted knowledge units."""

from __future__ import annotations

import argparse
import json
import sys
from itertools import combinations
from pathlib import Path

from generate_duplicate_candidates import similarity
from knowledge_store import connect_db, ensure_project, now_iso, stable_id


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def typed_relation(left: dict, right: dict) -> tuple[dict, dict, str, float] | None:
    by_type = {left["atom_type"]: left, right["atom_type"]: right}
    types = {left["atom_type"], right["atom_type"]}
    if types == {"QST", "SOL"}:
        return by_type["SOL"], by_type["QST"], "responds_to", 0.50
    if "CON" in types and len(types & {"QST", "OPI", "SOL"}) == 1:
        other_type = next(item for item in types if item != "CON")
        return by_type["CON"], by_type[other_type], "explains", 0.42
    if "CAS" in types and len(types & {"OPI", "SOL"}) == 1:
        other_type = next(item for item in types if item != "CAS")
        return by_type["CAS"], by_type[other_type], "proves", 0.48
    if types == {"HOK", "STR"}:
        return by_type["STR"], by_type["HOK"], "follows", 0.45
    if types == {"STR", "CTA"}:
        return by_type["CTA"], by_type["STR"], "follows", 0.45
    if len(types & {"EXP", "VIS"}) == 1 and len(types & {"HOK", "STR"}) == 1:
        expression_type = next(item for item in types if item in {"EXP", "VIS"})
        structure_type = next(item for item in types if item in {"HOK", "STR"})
        return by_type[expression_type], by_type[structure_type], "adapts_to", 0.38
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--threshold", type=float, default=0.58)
    parser.add_argument("--max-candidates", type=int, default=3000)
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    paths = ensure_project(project)
    with connect_db(paths["database"]) as conn:
        rows = [dict(row) for row in conn.execute("SELECT * FROM atoms ORDER BY atom_id")]
    atoms = []
    existing = set()
    for row in rows:
        row["topics"] = set(json.loads(row["topics_json"] or "[]"))
        row["sources"] = set(json.loads(row["source_ids_json"] or "[]"))
        row["keywords"] = set(json.loads(row["keywords_json"] or "[]"))
        for relation in json.loads(row["relationships_json"] or "[]"):
            existing.add((row["atom_id"], relation.get("type"), relation.get("target")))
        atoms.append(row)
    candidates = []
    for left, right in combinations(atoms, 2):
        typed = typed_relation(left, right)
        if not typed:
            continue
        source, target, relation_type, base = typed
        if (source["atom_id"], relation_type, target["atom_id"]) in existing:
            continue
        topic_score = jaccard(source["topics"], target["topics"])
        source_score = jaccard(source["sources"], target["sources"])
        keyword_score = jaccard(source["keywords"], target["keywords"])
        text_score = similarity(
            f"{source['title']} {source['statement']}", f"{target['title']} {target['statement']}"
        )
        if topic_score == 0 and keyword_score == 0 and text_score < 0.18:
            continue
        score = min(0.99, base + topic_score * 0.24 + text_score * 0.12 + source_score * 0.08 + keyword_score * 0.08)
        if score < args.threshold:
            continue
        reasons = [f"type rule {source['atom_type']}->{target['atom_type']}"]
        if topic_score:
            reasons.append(f"topic overlap {topic_score:.2f}")
        if source_score:
            reasons.append(f"source overlap {source_score:.2f}")
        if text_score >= 0.18:
            reasons.append(f"text affinity {text_score:.2f}")
        candidates.append(
            {
                "candidate_id": stable_id("REL", source["atom_id"], relation_type, target["atom_id"]),
                "kind": "relation",
                "source": source["atom_id"],
                "source_title": source["title"],
                "type": relation_type,
                "target": target["atom_id"],
                "target_title": target["title"],
                "score": round(score, 4),
                "shared_topics": sorted(source["topics"] & target["topics"]),
                "reason": "; ".join(reasons),
                "recommendation": "review",
            }
        )
    candidates.sort(key=lambda item: (-item["score"], item["candidate_id"]))
    candidates = candidates[: args.max_candidates]
    report = {
        "generated_at": now_iso(),
        "unit_count": len(atoms),
        "existing_relation_count": len(existing),
        "threshold": args.threshold,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    output = paths["state_dir"] / "relation_candidates.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"relation_candidates": len(candidates), "report": str(output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"generate_relation_candidates failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
