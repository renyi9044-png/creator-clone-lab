#!/usr/bin/env python
"""Validate and import promoted content or creator-pattern units from JSONL."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from knowledge_store import ATOM_TYPES, ensure_project


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("jsonl_file")
    parser.add_argument("--continue-on-error", action="store_true")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    ensure_project(project)
    jsonl_path = Path(args.jsonl_file).resolve()
    add_script = Path(__file__).with_name("add_knowledge_atom.py")
    imported = 0
    failures: list[dict[str, object]] = []

    for line_number, raw_line in enumerate(jsonl_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            atom = json.loads(raw_line)
            atom_type = atom.get("type")
            if atom_type not in ATOM_TYPES:
                raise ValueError(f"unsupported atom type: {atom_type}")
            if not atom.get("title") or not atom.get("statement"):
                raise ValueError("title and statement are required")
            if not atom.get("source_ids") and not atom.get("evidence"):
                raise ValueError("source_ids or evidence is required")
            command = [
                sys.executable,
                str(add_script),
                str(project),
                "--type",
                atom_type,
                "--title",
                atom["title"],
                "--statement",
                atom["statement"],
                "--confidence",
                atom.get("confidence", "medium"),
                "--status",
                atom.get("status", "hypothesis"),
                "--performance-segment",
                atom.get("performance_segment") or "",
                "--evidence",
                json.dumps(atom.get("evidence") or [], ensure_ascii=False),
                "--relationships",
                json.dumps(atom.get("relationships") or [], ensure_ascii=False),
            ]
            if atom.get("id"):
                command.extend(["--atom-id", atom["id"]])
            for topic in atom.get("topics") or []:
                command.extend(["--topic", topic])
            for source_id in atom.get("source_ids") or []:
                command.extend(["--source-id", source_id])
            for raw_atom_id in atom.get("raw_atom_ids") or []:
                command.extend(["--raw-atom-id", raw_atom_id])
            for keyword in atom.get("keywords") or []:
                command.extend(["--keyword", keyword])
            command.extend(["--canonical", "true" if atom.get("canonical", True) else "false"])
            command.extend(["--version", str(atom.get("version", 1))])
            result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip())
            imported += 1
        except Exception as exc:
            failures.append({"line": line_number, "error": str(exc)})
            if not args.continue_on_error:
                break

    report = {"input": str(jsonl_path), "imported": imported, "failed": failures}
    report_path = ensure_project(project)["state_dir"] / "last_atom_import.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"import_atom_batch failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
