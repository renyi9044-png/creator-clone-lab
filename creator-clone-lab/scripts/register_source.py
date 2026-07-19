#!/usr/bin/env python
"""Register or update one source in a Creator Clone Lab V2 project."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from knowledge_store import (
    UNDERSTANDING_LEVELS,
    connect_db,
    ensure_project,
    load_json_argument,
    now_iso,
    relative_or_absolute,
    rewrite_registry,
    sha256_file,
    stable_id,
    upsert_source_fts,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--platform", required=True)
    parser.add_argument("--content-type", required=True, choices=["video", "image-text", "article", "audio", "mixed", "other"])
    parser.add_argument("--creator", default="")
    parser.add_argument("--url", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--published-at", default="")
    parser.add_argument("--local-path", default="")
    parser.add_argument("--body-file", default="")
    parser.add_argument("--understanding-level", default="metadata-only", choices=sorted(UNDERSTANDING_LEVELS))
    parser.add_argument("--metrics", default="", help="JSON string or JSON file")
    parser.add_argument("--metric", action="append", default=[], help="Metric as key=value; repeat as needed")
    parser.add_argument("--source-id", default="")
    parser.add_argument("--copy", action="store_true", help="Copy local source into the immutable raw/media area")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    paths = ensure_project(project)
    local_path = Path(args.local_path).resolve() if args.local_path else None
    body_file = Path(args.body_file).resolve() if args.body_file else None
    identity = args.url or (str(local_path) if local_path else f"{args.creator}|{args.title}|{args.published_at}")
    source_id = args.source_id or stable_id(args.platform.upper()[:4], identity)

    if local_path and not local_path.exists():
        raise FileNotFoundError(local_path)
    if body_file and not body_file.exists():
        raise FileNotFoundError(body_file)

    stored_local = local_path
    if local_path and args.copy:
        bucket = "media" if args.content_type in {"video", "audio", "mixed"} else "raw"
        destination = project / "01_sources" / bucket / f"{source_id}{local_path.suffix.lower()}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.resolve() != local_path:
            shutil.copy2(local_path, destination)
        stored_local = destination

    document_path = None
    body = ""
    if body_file:
        body = body_file.read_text(encoding="utf-8", errors="replace")
        document_path = paths["documents"] / f"{source_id}.md"
        document_path.write_text(body, encoding="utf-8")

    metrics = load_json_argument(args.metrics, {})
    for item in args.metric:
        if "=" not in item:
            raise ValueError(f"metric must be key=value: {item}")
        key, raw_value = item.split("=", 1)
        try:
            metrics[key] = json.loads(raw_value)
        except json.JSONDecodeError:
            metrics[key] = raw_value
    timestamp = now_iso()
    checksum = sha256_file(stored_local) if stored_local and stored_local.is_file() else None
    with connect_db(paths["database"]) as conn:
        existing = conn.execute("SELECT created_at FROM sources WHERE source_id = ?", (source_id,)).fetchone()
        created_at = existing["created_at"] if existing else timestamp
        conn.execute(
            """
            INSERT INTO sources(
                source_id, platform, creator, content_type, url, title, published_at,
                local_path, body_path, understanding_level, metrics_json, sha256, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id) DO UPDATE SET
                platform=excluded.platform, creator=excluded.creator, content_type=excluded.content_type,
                url=excluded.url, title=excluded.title, published_at=excluded.published_at,
                local_path=excluded.local_path, body_path=excluded.body_path,
                understanding_level=excluded.understanding_level, metrics_json=excluded.metrics_json,
                sha256=excluded.sha256, updated_at=excluded.updated_at
            """,
            (
                source_id,
                args.platform,
                args.creator,
                args.content_type,
                args.url,
                args.title,
                args.published_at,
                relative_or_absolute(stored_local, project),
                relative_or_absolute(document_path, project),
                args.understanding_level,
                json.dumps(metrics, ensure_ascii=False),
                checksum,
                created_at,
                timestamp,
            ),
        )
        upsert_source_fts(conn, source_id, args.title, args.creator, body)
        rewrite_registry(conn, paths["registry"])

    print(f"source_id: {source_id}")
    print(f"understanding_level: {args.understanding_level}")
    print(f"registry: {paths['registry']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"register_source failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
