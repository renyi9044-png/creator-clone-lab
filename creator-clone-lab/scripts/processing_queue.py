#!/usr/bin/env python
"""Manage resumable source batches for Agent-driven semantic atom extraction."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from knowledge_store import connect_db, ensure_project, now_iso, resolve_stored_path, stable_id
from raw_atom_store import jsonl_rows, load_corpus, normalize_atom, write_corpus


EXTRACT_TYPES = [
    "observation", "quote", "metric", "question", "concept", "opinion", "case",
    "solution", "hook", "structure", "expression", "visual", "cta", "requirement",
    "decision", "insight",
]


def queue_path(project: Path) -> Path:
    return ensure_project(project)["state_dir"] / "processing_queue.jsonl"


def read_queue(project: Path) -> list[dict]:
    path = queue_path(project)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_queue(project: Path, jobs: list[dict]) -> None:
    path = queue_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        "".join(json.dumps(job, ensure_ascii=False) + "\n" for job in sorted(jobs, key=lambda item: item["job_id"])),
        encoding="utf-8",
    )
    temporary.replace(path)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def sync_queue(project: Path, include_partial: bool = False) -> list[dict]:
    paths = ensure_project(project)
    existing = {job["source_id"]: job for job in read_queue(project)}
    allowed = {"full", "partial"} if include_partial else {"full"}
    with connect_db(paths["database"]) as conn:
        sources = [dict(row) for row in conn.execute("SELECT * FROM sources ORDER BY source_id")]
        raw_counts = {
            row["source_id"]: row["count"]
            for row in conn.execute("SELECT source_id, COUNT(*) AS count FROM raw_atoms GROUP BY source_id")
        }
    jobs = []
    timestamp = now_iso()
    for source in sources:
        if source["understanding_level"] not in allowed:
            continue
        body_path = resolve_stored_path(source.get("body_path"), project)
        previous = existing.get(source["source_id"], {})
        atom_count = int(raw_counts.get(source["source_id"], 0))
        status = previous.get("status") or "pending"
        error = previous.get("error") or ""
        if atom_count:
            status = "completed"
            error = ""
        elif not body_path or not body_path.exists():
            status = "blocked"
            error = "normalized body is missing"
        elif status == "completed":
            status = "pending"
        jobs.append(
            {
                "job_id": previous.get("job_id") or stable_id("JOB", source["source_id"]),
                "source_id": source["source_id"],
                "platform": source["platform"],
                "creator": source.get("creator") or "",
                "title": source.get("title") or source["source_id"],
                "body_path": str(body_path) if body_path else "",
                "metrics": json.loads(source.get("metrics_json") or "{}"),
                "understanding_level": source["understanding_level"],
                "status": status,
                "attempts": int(previous.get("attempts") or 0),
                "batch_id": previous.get("batch_id") or "",
                "atom_count": atom_count,
                "error": error,
                "created_at": previous.get("created_at") or timestamp,
                "updated_at": timestamp,
            }
        )
    write_queue(project, jobs)
    return jobs


def summary(jobs: list[dict]) -> dict:
    counts = Counter(job["status"] for job in jobs)
    return {"job_count": len(jobs), "statuses": dict(sorted(counts.items()))}


def claim(project: Path, limit: int, retry_stale_hours: int, max_attempts: int) -> dict:
    jobs = sync_queue(project, include_partial=True)
    stale_before = datetime.now().astimezone() - timedelta(hours=retry_stale_hours)
    for job in jobs:
        updated = parse_time(job.get("updated_at"))
        if job["status"] == "in_progress" and updated and updated < stale_before:
            job["status"] = "failed"
            job["error"] = "stale in-progress job recovered"
    candidates = [
        job for job in jobs
        if job["status"] in {"pending", "failed"} and int(job.get("attempts") or 0) < max_attempts
    ]
    candidates.sort(key=lambda item: (item["attempts"], item["updated_at"], item["job_id"]))
    selected = candidates[:limit]
    batch_id = stable_id("BAT", now_iso(), *(job["source_id"] for job in selected)) if selected else ""
    timestamp = now_iso()
    selected_ids = {job["job_id"] for job in selected}
    for job in jobs:
        if job["job_id"] in selected_ids:
            job["status"] = "in_progress"
            job["attempts"] += 1
            job["batch_id"] = batch_id
            job["error"] = ""
            job["updated_at"] = timestamp
    write_queue(project, jobs)
    paths = ensure_project(project)
    batch_dir = paths["state_dir"] / "extraction_batches"
    batch_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = batch_dir / f"{batch_id}.jobs.json" if batch_id else batch_dir / "empty.jobs.json"
    manifest = {
        "schema_version": "1.0",
        "batch_id": batch_id,
        "created_at": timestamp,
        "jobs": [
            {
                **job,
                "extract": EXTRACT_TYPES,
                "rules": [
                    "Extract compact atomic evidence, not a source summary.",
                    "Preserve original evidence and a precise source locator.",
                    "Use fact only for direct evidence; interpretations default to hypothesis.",
                    "Preserve weak-performance evidence and counterexamples.",
                    "Leave unit_ids empty until promotion review.",
                ],
            }
            for job in selected
        ],
        "expected_output": str(batch_dir / f"{batch_id}.raw_atoms.jsonl") if batch_id else "",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"batch_id": batch_id, "claimed": len(selected), "manifest": str(manifest_path)}


def complete(project: Path, batch_id: str, atoms_path: Path) -> dict:
    jobs = read_queue(project)
    batch_jobs = [job for job in jobs if job.get("batch_id") == batch_id and job["status"] == "in_progress"]
    if not batch_jobs:
        raise ValueError(f"no in-progress jobs for batch: {batch_id}")
    allowed_sources = {job["source_id"] for job in batch_jobs}
    incoming = [normalize_atom(atom) for atom in jsonl_rows(atoms_path)]
    unexpected = sorted({atom["source_id"] for atom in incoming} - allowed_sources)
    if unexpected:
        raise ValueError(f"submitted atoms reference sources outside batch: {', '.join(unexpected)}")
    existing = {atom["id"]: atom for atom in load_corpus(project)}
    for atom in incoming:
        existing[atom["id"]] = atom
    store_report = write_corpus(project, existing.values())
    counts = Counter(atom["source_id"] for atom in incoming)
    timestamp = now_iso()
    completed = 0
    failed = 0
    for job in jobs:
        if job.get("batch_id") != batch_id or job["status"] != "in_progress":
            continue
        count = counts.get(job["source_id"], 0)
        job["atom_count"] = count
        job["updated_at"] = timestamp
        if count:
            job["status"] = "completed"
            job["error"] = ""
            completed += 1
        else:
            job["status"] = "failed"
            job["error"] = "no atoms submitted for source"
            failed += 1
    write_queue(project, jobs)
    report = {
        "batch_id": batch_id,
        "submitted_atoms": len(incoming),
        "completed_jobs": completed,
        "failed_jobs": failed,
        **store_report,
    }
    report_path = ensure_project(project)["state_dir"] / "extraction_batches" / f"{batch_id}.result.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def fail_batch(project: Path, batch_id: str, error: str) -> dict:
    jobs = read_queue(project)
    changed = 0
    for job in jobs:
        if job.get("batch_id") == batch_id and job["status"] == "in_progress":
            job["status"] = "failed"
            job["error"] = error
            job["updated_at"] = now_iso()
            changed += 1
    write_queue(project, jobs)
    return {"batch_id": batch_id, "failed_jobs": changed, "error": error}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    subparsers = parser.add_subparsers(dest="command", required=True)
    sync_parser = subparsers.add_parser("sync")
    sync_parser.add_argument("--include-partial", action="store_true")
    claim_parser = subparsers.add_parser("claim")
    claim_parser.add_argument("--limit", type=int, default=5)
    claim_parser.add_argument("--retry-stale-hours", type=int, default=24)
    claim_parser.add_argument("--max-attempts", type=int, default=3)
    complete_parser = subparsers.add_parser("complete")
    complete_parser.add_argument("--batch-id", required=True)
    complete_parser.add_argument("--atoms", required=True)
    fail_parser = subparsers.add_parser("fail")
    fail_parser.add_argument("--batch-id", required=True)
    fail_parser.add_argument("--error", required=True)
    subparsers.add_parser("status")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    ensure_project(project)
    if args.command == "sync":
        result = summary(sync_queue(project, args.include_partial))
    elif args.command == "claim":
        result = claim(project, args.limit, args.retry_stale_hours, args.max_attempts)
    elif args.command == "complete":
        result = complete(project, args.batch_id, Path(args.atoms).resolve())
    elif args.command == "fail":
        result = fail_batch(project, args.batch_id, args.error)
    else:
        result = summary(read_queue(project))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"processing_queue failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
