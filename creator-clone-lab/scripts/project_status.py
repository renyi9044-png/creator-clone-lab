#!/usr/bin/env python
"""Print knowledge-project coverage and the next quality gate."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from knowledge_store import connect_db, ensure_project, now_iso


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: project_status.py <project_dir>", file=sys.stderr)
        return 2
    project = Path(sys.argv[1]).resolve()
    paths = ensure_project(project)
    with connect_db(paths["database"]) as conn:
        sources = conn.execute("SELECT platform, understanding_level FROM sources").fetchall()
        atoms = conn.execute("SELECT atom_type, status, confidence FROM atoms").fetchall()
        evidence_count = conn.execute("SELECT COUNT(*) AS count FROM evidence").fetchone()["count"]
        raw_atom_count = conn.execute("SELECT COUNT(*) AS count FROM raw_atoms").fetchone()["count"]
        promoted_raw_atom_count = conn.execute(
            "SELECT COUNT(*) AS count FROM raw_atoms WHERE unit_ids_json != '[]'"
        ).fetchone()["count"]
    duplicate_path = paths["state_dir"] / "duplicate_candidates.json"
    relation_path = paths["state_dir"] / "relation_index.json"
    clone_path = paths["state_dir"] / "clone_state.json"
    performance_path = paths["performance"] / "performance_snapshots.jsonl"
    processing_queue_path = paths["state_dir"] / "processing_queue.jsonl"
    review_queue_path = paths["state_dir"] / "review_queue.jsonl"
    duplicate_state = json.loads(duplicate_path.read_text(encoding="utf-8")) if duplicate_path.exists() else {}
    relation_state = json.loads(relation_path.read_text(encoding="utf-8")) if relation_path.exists() else {}
    clone_state = json.loads(clone_path.read_text(encoding="utf-8")) if clone_path.exists() else {}
    performance_count = (
        sum(1 for line in performance_path.read_text(encoding="utf-8").splitlines() if line.strip())
        if performance_path.exists()
        else 0
    )
    topic_map_count = len(
        [path for path in paths["topic_maps"].glob("*.md") if path.name not in {"index.md", "relation_overview.md"}]
    )
    retrospective_count = len(list(paths["reports"].glob("retrospective_*.md")))
    processing_jobs = (
        [json.loads(line) for line in processing_queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if processing_queue_path.exists()
        else []
    )
    review_items = (
        [json.loads(line) for line in review_queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if review_queue_path.exists()
        else []
    )
    active_reviews = [item for item in review_items if item.get("active", True)]
    processing_statuses = Counter(item["status"] for item in processing_jobs)
    review_statuses = Counter(item["status"] for item in active_reviews)
    review_kinds = Counter(item["kind"] for item in active_reviews)
    source_count = len(sources)
    full_count = sum(1 for row in sources if row["understanding_level"] == "full")
    missing_targets = int(relation_state.get("missing_target_count", 0))
    duplicate_candidates = int(duplicate_state.get("candidate_count", 0))
    clone_maturity = clone_state.get("maturity", "not-built")
    if missing_targets:
        mode = "repair"
        next_action = f"Repair {missing_targets} missing relationship targets before rebuilding maps or the clone."
    elif full_count < 10:
        mode = "audit"
        next_action = f"Process {10 - full_count} more fully understood samples before creating a provisional clone."
    elif full_count < 30:
        mode = "sample"
        next_action = f"Provisional clone allowed; process {30 - full_count} more samples across high and weak bands."
    else:
        mode = "batch"
        next_action = "Audit counterexamples and performance bands, then complete at least one publishing retrospective."
    if duplicate_candidates and missing_targets == 0:
        next_action += f" Review {duplicate_candidates} duplicate candidates; do not merge them automatically."
    pending_processing = processing_statuses.get("pending", 0) + processing_statuses.get("failed", 0)
    if pending_processing:
        next_action += f" Claim the next extraction batch from {pending_processing} pending or failed jobs."
    if review_statuses.get("pending", 0):
        next_action += f" Review {review_statuses['pending']} queued promotion, relation, or duplicate candidates."
    state = {
        "updated_at": now_iso(),
        "mode": mode,
        "source_count": source_count,
        "fully_understood_sources": full_count,
        "platforms": Counter(row["platform"] for row in sources),
        "promoted_unit_count": len(atoms),
        "content_unit_count": sum(1 for row in atoms if row["atom_type"] in {"QST", "CON", "OPI", "CAS", "SOL"}),
        "creator_pattern_count": sum(1 for row in atoms if row["atom_type"] in {"HOK", "STR", "EXP", "VIS", "CTA"}),
        "atom_count": len(atoms),
        "raw_atom_count": raw_atom_count,
        "promoted_raw_atom_count": promoted_raw_atom_count,
        "raw_atom_promotion_rate": round(promoted_raw_atom_count / raw_atom_count, 4) if raw_atom_count else 0.0,
        "atom_types": Counter(row["atom_type"] for row in atoms),
        "atom_statuses": Counter(row["status"] for row in atoms),
        "evidence_count": evidence_count,
        "duplicate_candidates": duplicate_candidates,
        "missing_relation_targets": missing_targets,
        "topic_map_count": topic_map_count,
        "clone_maturity": clone_maturity,
        "performance_snapshot_count": performance_count,
        "retrospective_count": retrospective_count,
        "processing_job_count": len(processing_jobs),
        "processing_statuses": processing_statuses,
        "active_review_count": len(active_reviews),
        "review_statuses": review_statuses,
        "review_kinds": review_kinds,
        "next_action": next_action,
    }
    serializable = {key: dict(value) if isinstance(value, Counter) else value for key, value in state.items()}
    paths["state"].write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(serializable, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"project_status failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
