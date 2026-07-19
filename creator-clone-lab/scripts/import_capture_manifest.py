#!/usr/bin/env python
"""Import a platform capture manifest into a Creator Clone Lab project."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from knowledge_store import ensure_project


BODY_CANDIDATES = ("normalized.md", "transcript.txt", "transcript_local.txt", "transcript_groq.txt", "ocr.txt")


def resolve_manifest_file(value: str, manifest_dir: Path) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else manifest_dir / path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("manifest")
    parser.add_argument("--copy", action="store_true", help="Copy captured local media into immutable project storage")
    parser.add_argument("--auto-body", action="store_true", help="Attach a conventional transcript/normalized file for single-item captures")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    paths = ensure_project(project)
    manifest_path = Path(args.manifest).resolve()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0" or not isinstance(payload.get("items"), list):
        raise ValueError("unsupported or invalid capture manifest")
    manifest_dir = manifest_path.parent
    items = payload["items"]
    auto_body = None
    if args.auto_body and len(items) == 1:
        auto_body = next((manifest_dir / name for name in BODY_CANDIDATES if (manifest_dir / name).exists()), None)

    register_script = Path(__file__).with_name("register_source.py")
    imported = 0
    failed: list[dict[str, str]] = []
    for item in items:
        platform = item.get("platform") or payload.get("platform")
        creator = item.get("creator") or payload.get("creator") or ""
        if not platform or not item.get("content_type") or not item.get("source_id"):
            failed.append({"source_id": item.get("source_id") or "unknown", "error": "missing platform/content_type/source_id"})
            continue
        local_path = resolve_manifest_file(item.get("local_path") or "", manifest_dir)
        body_path = resolve_manifest_file(item.get("body_path") or "", manifest_dir) or auto_body
        command = [
            sys.executable,
            str(register_script),
            str(project),
            "--platform",
            platform,
            "--content-type",
            item["content_type"],
            "--creator",
            creator,
            "--url",
            item.get("url") or "",
            "--title",
            item.get("title") or "",
            "--published-at",
            item.get("published_at") or "",
            "--understanding-level",
            item.get("understanding_level") or "metadata-only",
            "--source-id",
            item["source_id"],
            "--metrics",
            json.dumps(item.get("metrics") or {}, ensure_ascii=False),
        ]
        if local_path and local_path.exists():
            command.extend(["--local-path", str(local_path)])
            if args.copy:
                command.append("--copy")
        if body_path and body_path.exists():
            command.extend(["--body-file", str(body_path)])
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
        if result.returncode == 0:
            imported += 1
        else:
            failed.append({"source_id": item["source_id"], "error": result.stderr.strip() or result.stdout.strip()})

    report = {"manifest": str(manifest_path), "total": len(items), "imported": imported, "failed": failed}
    report_path = paths["state_dir"] / "last_capture_import.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"import_capture_manifest failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
