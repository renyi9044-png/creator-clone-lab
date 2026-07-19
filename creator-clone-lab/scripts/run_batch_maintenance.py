#!/usr/bin/env python
"""Run the deterministic post-extraction maintenance and review-queue pipeline."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from knowledge_store import ensure_project, now_iso


def run(script_dir: Path, name: str, *args: str) -> dict:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        [sys.executable, str(script_dir / name), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{name} failed: {result.stderr.strip() or result.stdout.strip()}")
    return {"script": name, "stdout": result.stdout.strip()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--skip-vault", action="store_true")
    parser.add_argument("--duplicate-threshold", default="0.86")
    parser.add_argument("--relation-threshold", default="0.58")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    paths = ensure_project(project)
    script_dir = Path(__file__).resolve().parent
    steps = [
        ("generate_duplicate_candidates.py", [str(project)]),
        (
            "generate_atom_candidates.py",
            [str(project), "--duplicate-threshold", args.duplicate_threshold],
        ),
        (
            "generate_relation_candidates.py",
            [str(project), "--threshold", args.relation_threshold],
        ),
        ("review_queue.py", [str(project), "build"]),
        ("generate_relation_map.py", [str(project)]),
        ("generate_topic_maps.py", [str(project)]),
        ("build_creator_clone.py", [str(project)]),
    ]
    if not args.skip_vault:
        steps.extend(
            [
                ("build_obsidian_vault.py", [str(project)]),
                ("validate_obsidian_vault.py", [str(project / "内容资产工程")]),
                ("render_obsidian_graph.py", [str(project / "内容资产工程")]),
            ]
        )
    completed = []
    for name, command_args in steps:
        completed.append(run(script_dir, name, *command_args))
    report = {
        "generated_at": now_iso(),
        "project": str(project),
        "completed_steps": [item["script"] for item in completed],
        "step_count": len(completed),
        "review_queue": str(paths["state_dir"] / "review_queue.jsonl"),
    }
    output = paths["state_dir"] / "batch_maintenance_report.json"
    output.write_text(json.dumps({**report, "details": completed}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**report, "report": str(output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"run_batch_maintenance failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
