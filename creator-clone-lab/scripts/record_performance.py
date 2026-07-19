#!/usr/bin/env python
"""Append a publishing-performance snapshot and update source metrics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from knowledge_store import connect_db, ensure_project, now_iso


def parse_metrics(items: list[str]) -> dict:
    metrics = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"metric must be key=value: {item}")
        key, raw = item.split("=", 1)
        try:
            metrics[key] = json.loads(raw)
        except json.JSONDecodeError:
            metrics[key] = raw
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("source_id")
    parser.add_argument("--metric", action="append", default=[], required=True)
    parser.add_argument("--observed-at", default="")
    parser.add_argument("--stage", default="manual", help="T+1h, T+24h, T+7d, final, or manual")
    parser.add_argument("--note", default="")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    paths = ensure_project(project)
    observed_at = args.observed_at or now_iso()
    metrics = parse_metrics(args.metric)
    with connect_db(paths["database"]) as conn:
        source = conn.execute("SELECT metrics_json FROM sources WHERE source_id = ?", (args.source_id,)).fetchone()
        if not source:
            raise ValueError(f"unknown source_id: {args.source_id}")
        merged = json.loads(source["metrics_json"] or "{}")
        merged.update(metrics)
        conn.execute(
            "UPDATE sources SET metrics_json = ?, updated_at = ? WHERE source_id = ?",
            (json.dumps(merged, ensure_ascii=False), observed_at, args.source_id),
        )
        affected_atoms = [
            row["atom_id"]
            for row in conn.execute(
                "SELECT atom_id FROM atoms WHERE source_ids_json LIKE ? ORDER BY atom_id", (f'%"{args.source_id}"%',)
            ).fetchall()
        ]
    snapshot = {
        "source_id": args.source_id,
        "observed_at": observed_at,
        "stage": args.stage,
        "metrics": metrics,
        "note": args.note,
        "affected_atoms": affected_atoms,
    }
    ledger = paths["performance"] / "performance_snapshots.jsonl"
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    print(f"source_id: {args.source_id}")
    print(f"affected atoms: {len(affected_atoms)}")
    print(f"ledger: {ledger}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"record_performance failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
