#!/usr/bin/env python
"""Prepare representative source jobs for semantic atom extraction by an Agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from knowledge_store import connect_db, ensure_project, resolve_stored_path


def metric_value(metrics: dict, key: str) -> float:
    value = metrics.get(key)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def representative_order(rows: list[dict]) -> list[dict]:
    ranked = sorted(rows, key=lambda row: metric_value(row["metrics"], "views"), reverse=True)
    result = []
    left, right = 0, len(ranked) - 1
    while left <= right:
        result.append(ranked[left])
        left += 1
        if left <= right:
            result.append(ranked[right])
            right -= 1
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--include-partial", action="store_true")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    paths = ensure_project(project)
    allowed = ("full", "partial") if args.include_partial else ("full",)
    placeholders = ",".join("?" for _ in allowed)
    with connect_db(paths["database"]) as conn:
        rows = conn.execute(
            f"SELECT * FROM sources WHERE understanding_level IN ({placeholders}) ORDER BY updated_at DESC", allowed
        ).fetchall()
    candidates = []
    for row in rows:
        item = dict(row)
        item["metrics"] = json.loads(row["metrics_json"] or "{}")
        body_path = resolve_stored_path(row["body_path"], project)
        if not body_path or not body_path.exists():
            continue
        item["resolved_body_path"] = str(body_path)
        candidates.append(item)
    selected = representative_order(candidates)[: args.limit]
    jobs = []
    for item in selected:
        jobs.append(
            {
                "source_id": item["source_id"],
                "platform": item["platform"],
                "creator": item["creator"],
                "title": item["title"],
                "body_path": item["resolved_body_path"],
                "metrics": item["metrics"],
                "understanding_level": item["understanding_level"],
                "extract": [
                    "observation", "quote", "metric", "question", "concept", "opinion", "case",
                    "solution", "hook", "structure", "expression", "visual", "cta", "requirement", "decision",
                ],
                "rules": [
                    "Extract compact atomic evidence into JSONL, not Markdown units.",
                    "Every raw atom must preserve original evidence and a precise source locator.",
                    "Do not turn every sentence into an atom.",
                    "Use fact for direct evidence and hypothesis for interpretations.",
                    "Preserve counterexamples and weak-performance evidence.",
                    "Leave unit_ids empty until semantic promotion review.",
                ],
            }
        )
    output = paths["state_dir"] / "atom_extraction_jobs.jsonl"
    output.write_text("".join(json.dumps(job, ensure_ascii=False) + "\n" for job in jobs), encoding="utf-8")
    print(f"extraction jobs: {len(jobs)}")
    print(f"saved: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"prepare_atom_extraction failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
