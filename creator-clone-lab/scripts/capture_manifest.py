#!/usr/bin/env python
"""Portable capture-manifest helpers shared by platform adapters."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


MANIFEST_VERSION = "1.0"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def canonical_public_url(url: str | None) -> str:
    if not url:
        return ""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def stable_source_id(platform: str, identity: str, explicit_id: str | None = None) -> str:
    if explicit_id:
        safe = "".join(ch for ch in explicit_id if ch.isalnum() or ch in "-_")
        return f"{platform.upper()[:4]}-{safe}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12].upper()
    return f"{platform.upper()[:4]}-{digest}"


def relative_file(path: Path | None, out_dir: Path) -> str:
    if path is None:
        return ""
    path = path.resolve()
    try:
        return path.relative_to(out_dir.resolve()).as_posix()
    except ValueError:
        return str(path)


def write_capture_manifest(
    out_dir: Path,
    *,
    platform: str,
    creator: str,
    items: list[dict[str, Any]],
    capture_kind: str,
) -> Path:
    normalized_items = []
    for item in items:
        normalized = dict(item)
        normalized["url"] = canonical_public_url(normalized.get("url"))
        normalized.setdefault("creator", creator)
        normalized.setdefault("platform", platform)
        normalized.setdefault("understanding_level", "metadata-only")
        normalized.setdefault("metrics", {})
        normalized_items.append(normalized)
    payload = {
        "schema_version": MANIFEST_VERSION,
        "platform": platform,
        "creator": creator,
        "capture_kind": capture_kind,
        "captured_at": now_iso(),
        "items": normalized_items,
    }
    path = out_dir / "capture_manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
