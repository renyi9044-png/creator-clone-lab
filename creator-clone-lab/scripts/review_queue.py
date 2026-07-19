#!/usr/bin/env python
"""Build and operate a persistent human review queue for knowledge candidates."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

from add_knowledge_atom import render_atom
from knowledge_store import connect_db, ensure_project, now_iso


REPORTS = {
    "promoted_duplicate": "duplicate_candidates.json",
    "raw_duplicate": "raw_duplicate_candidates.json",
    "promotion": "promotion_candidates.json",
    "relation": "relation_candidates.json",
}
DECISIONS = {"accept", "reject", "defer"}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def atomic_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    temporary.replace(path)


def candidate_id(candidate: dict) -> str:
    return str(candidate.get("candidate_id") or f"DUP-{candidate.get('left')}-{candidate.get('right')}")


def load_candidates(state_dir: Path) -> list[dict]:
    candidates = []
    for default_kind, filename in REPORTS.items():
        report = read_json(state_dir / filename)
        for candidate in report.get("candidates") or []:
            item = dict(candidate)
            item.setdefault("kind", default_kind)
            item["candidate_id"] = candidate_id(item)
            candidates.append(item)
    return candidates


def render_markdown(items: list[dict]) -> str:
    counts = Counter(item["status"] for item in items if item.get("active", True))
    lines = [
        "# 人工审核队列",
        "",
        f"- 待审核：{counts.get('pending', 0)}",
        f"- 已接受：{counts.get('accepted', 0)}",
        f"- 已拒绝：{counts.get('rejected', 0)}",
        f"- 已暂缓：{counts.get('deferred', 0)}",
        "",
    ]
    labels = {
        "promotion": "晋升候选",
        "relation": "关系候选",
        "raw_duplicate": "原子去重候选",
        "promoted_duplicate": "单元去重候选",
    }
    for kind in ("promotion", "relation", "raw_duplicate", "promoted_duplicate"):
        group = [item for item in items if item["kind"] == kind and item.get("active", True)]
        if not group:
            continue
        lines.extend([f"## {labels[kind]}", ""])
        for item in group:
            mark = "x" if item["status"] == "accepted" else " "
            payload = item["payload"]
            if kind == "promotion":
                description = f"{payload.get('suggested_type')} · {payload.get('suggested_title')}"
            elif kind == "relation":
                description = f"{payload.get('source_title')} --{payload.get('type')}--> {payload.get('target_title')}"
            else:
                description = f"{payload.get('left')} ↔ {payload.get('right')}"
            lines.append(
                f"- [{mark}] `{item['review_id']}` [{item['status']}] {description} "
                f"(score={payload.get('score', 'n/a')})"
            )
            reason = payload.get("reason") or payload.get("classification")
            if reason:
                lines.append(f"  - {reason}")
            if item.get("note"):
                lines.append(f"  - 审核备注：{item['note']}")
        lines.append("")
    if len(lines) <= 8:
        lines.append("- 当前没有候选。")
    return "\n".join(lines) + "\n"


def build_queue(project: Path) -> dict:
    paths = ensure_project(project)
    queue_file = paths["state_dir"] / "review_queue.jsonl"
    previous = {item["review_id"]: item for item in read_jsonl(queue_file)}
    candidates = load_candidates(paths["state_dir"])
    active_ids = set()
    timestamp = now_iso()
    for candidate in candidates:
        review_id = candidate["candidate_id"]
        active_ids.add(review_id)
        old = previous.get(review_id, {})
        previous[review_id] = {
            "review_id": review_id,
            "kind": candidate["kind"],
            "status": old.get("status") or "pending",
            "active": True,
            "payload": candidate,
            "note": old.get("note") or "",
            "created_at": old.get("created_at") or timestamp,
            "updated_at": old.get("updated_at") or timestamp,
        }
    for review_id, item in previous.items():
        if review_id not in active_ids:
            item["active"] = False
    items = sorted(
        previous.values(),
        key=lambda item: (
            not item.get("active", True),
            item["status"] != "pending",
            item["kind"],
            -float(item["payload"].get("score") or 0),
            item["review_id"],
        ),
    )
    atomic_jsonl(queue_file, items)
    markdown = paths["state_dir"] / "review_queue.md"
    markdown.write_text(render_markdown(items), encoding="utf-8")
    counts = Counter(item["status"] for item in items if item.get("active", True))
    return {
        "active_items": sum(counts.values()),
        "statuses": dict(sorted(counts.items())),
        "queue": str(queue_file),
        "markdown": str(markdown),
    }


def apply_relation(project: Path, payload: dict) -> None:
    paths = ensure_project(project)
    source_id, target_id, relation_type = payload["source"], payload["target"], payload["type"]
    with connect_db(paths["database"]) as conn:
        row = conn.execute("SELECT * FROM atoms WHERE atom_id = ?", (source_id,)).fetchone()
        if not row:
            raise ValueError(f"relation source does not exist: {source_id}")
        if not conn.execute("SELECT 1 FROM atoms WHERE atom_id = ?", (target_id,)).fetchone():
            raise ValueError(f"relation target does not exist: {target_id}")
        relations = json.loads(row["relationships_json"] or "[]")
        relation = {"type": relation_type, "target": target_id}
        if relation not in relations:
            relations.append(relation)
        timestamp = now_iso()
        conn.execute(
            "UPDATE atoms SET relationships_json = ?, updated_at = ? WHERE atom_id = ?",
            (json.dumps(relations, ensure_ascii=False), timestamp, source_id),
        )
        evidence = [
            dict(item)
            for item in conn.execute(
                "SELECT source_id, location, modality, excerpt FROM evidence WHERE atom_id = ? ORDER BY evidence_id",
                (source_id,),
            )
        ]
        updated = dict(row)
        updated["relationships_json"] = json.dumps(relations, ensure_ascii=False)
        updated["updated_at"] = timestamp
    atom = {
        "atom_id": updated["atom_id"],
        "atom_type": updated["atom_type"],
        "title": updated["title"],
        "statement": updated["statement"],
        "topics": json.loads(updated["topics_json"] or "[]"),
        "confidence": updated["confidence"],
        "status": updated["status"],
        "performance_segment": updated["performance_segment"],
        "source_ids": json.loads(updated["source_ids_json"] or "[]"),
        "raw_atom_ids": json.loads(updated["raw_atom_ids_json"] or "[]"),
        "keywords": json.loads(updated["keywords_json"] or "[]"),
        "canonical": bool(updated["canonical"]),
        "version": updated["version"],
        "unit_kind": updated["unit_kind"],
        "relationships": relations,
        "created_at": updated["created_at"],
        "updated_at": updated["updated_at"],
    }
    atom_path = project / updated["file_path"]
    atom_path.write_text(render_atom(atom, evidence), encoding="utf-8")


def apply_promotion(project: Path, payload: dict, args: argparse.Namespace) -> None:
    atom_type = args.type or payload["suggested_type"]
    title = args.title or payload["suggested_title"]
    statement = args.statement or payload["suggested_statement"]
    command = [
        sys.executable,
        str(Path(__file__).with_name("add_knowledge_atom.py")),
        str(project),
        "--type", atom_type,
        "--title", title,
        "--statement", statement,
        "--confidence", payload.get("confidence") or "medium",
        "--status", payload.get("status") or "hypothesis",
        "--evidence", json.dumps(payload.get("evidence") or [], ensure_ascii=False),
    ]
    for value in payload.get("topics") or []:
        command.extend(["--topic", value])
    for value in payload.get("source_ids") or []:
        command.extend(["--source-id", value])
    for value in payload.get("raw_atom_ids") or []:
        command.extend(["--raw-atom-id", value])
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def decide(project: Path, review_id: str, args: argparse.Namespace) -> dict:
    paths = ensure_project(project)
    queue_file = paths["state_dir"] / "review_queue.jsonl"
    items = read_jsonl(queue_file)
    match = next((item for item in items if item["review_id"] == review_id), None)
    if not match:
        raise ValueError(f"review item not found: {review_id}")
    if args.decision == "accept":
        if match["kind"] == "relation":
            apply_relation(project, match["payload"])
        elif match["kind"] == "promotion":
            apply_promotion(project, match["payload"], args)
    match["status"] = {"accept": "accepted", "reject": "rejected", "defer": "deferred"}[args.decision]
    match["note"] = args.note or match.get("note") or ""
    match["updated_at"] = now_iso()
    atomic_jsonl(queue_file, items)
    decision_log = paths["state_dir"] / "review_decisions.jsonl"
    with decision_log.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "review_id": review_id,
                    "kind": match["kind"],
                    "decision": args.decision,
                    "note": match["note"],
                    "decided_at": match["updated_at"],
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    (paths["state_dir"] / "review_queue.md").write_text(render_markdown(items), encoding="utf-8")
    return {"review_id": review_id, "status": match["status"], "kind": match["kind"]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build")
    subparsers.add_parser("status")
    decision_parser = subparsers.add_parser("decide")
    decision_parser.add_argument("review_id")
    decision_parser.add_argument("--decision", required=True, choices=sorted(DECISIONS))
    decision_parser.add_argument("--note", default="")
    decision_parser.add_argument("--type", default="")
    decision_parser.add_argument("--title", default="")
    decision_parser.add_argument("--statement", default="")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    paths = ensure_project(project)
    if args.command == "build":
        result = build_queue(project)
    elif args.command == "decide":
        result = decide(project, args.review_id, args)
    else:
        items = read_jsonl(paths["state_dir"] / "review_queue.jsonl")
        counts = Counter(item["status"] for item in items if item.get("active", True))
        result = {"active_items": sum(counts.values()), "statuses": dict(sorted(counts.items()))}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"review_queue failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
