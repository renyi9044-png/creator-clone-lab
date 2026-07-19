#!/usr/bin/env python
"""Validate Obsidian nodes, resolved wikilinks, edges, and required content-asset directories."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path


REQUIRED_DIRECTORIES = {
    "00-规则与索引",
    "01-原始素材区",
    "02-内容单元库",
    "03-处理状态",
    "04-模板",
    "05-主题地图",
    "06-选题装配",
    "07-脚本与工具",
    "08-人工笔记",
    ".obsidian",
}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_obsidian_vault.py <vault_dir>", file=sys.stderr)
        return 2
    vault = Path(sys.argv[1]).resolve()
    missing_directories = sorted(name for name in REQUIRED_DIRECTORIES if not (vault / name).is_dir())
    marker_path = vault / ".creator-clone-vault.json"
    marker_errors = []
    marker = {}
    if not marker_path.exists():
        marker_errors.append("missing .creator-clone-vault.json")
    else:
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            marker_errors.append(f"invalid marker: {exc}")
    generated_files = marker.get("generated_files") if isinstance(marker, dict) else None
    if not isinstance(generated_files, dict) or not generated_files:
        marker_errors.append("marker has no generated_files manifest")
        generated_files = {}
    missing_generated_files = sorted(
        relative for relative in generated_files if not (vault / relative).is_file()
    )
    modified_generated_files = sorted(
        relative
        for relative, expected_hash in generated_files.items()
        if (vault / relative).is_file()
        and not relative.startswith(".obsidian/")
        and file_sha256(vault / relative) != expected_hash
    )
    files = list(vault.rglob("*.md"))
    by_stem: dict[str, list[Path]] = {}
    for path in files:
        by_stem.setdefault(path.stem, []).append(path)
    duplicate_stems = {stem: [str(path.relative_to(vault)) for path in paths] for stem, paths in by_stem.items() if len(paths) > 1}
    unresolved = []
    edges = set()
    degree = Counter()
    for path in files:
        source = path.stem
        text = path.read_text(encoding="utf-8", errors="replace")
        for target in re.findall(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]", text):
            target_stem = Path(target).stem
            if target_stem not in by_stem:
                unresolved.append({"source": str(path.relative_to(vault)), "target": target})
                continue
            edge = tuple(sorted((source, target_stem)))
            if source != target_stem:
                edges.add(edge)
                degree[source] += 1
                degree[target_stem] += 1
    orphans = sorted(stem for stem in by_stem if degree[stem] == 0)
    manual_markdown = [
        path for path in files if path.relative_to(vault).as_posix().startswith("08-人工笔记/")
    ]
    report = {
        "vault": str(vault),
        "markdown_nodes": len(files),
        "resolved_edges": len(edges),
        "unresolved_links": len(unresolved),
        "duplicate_stems": len(duplicate_stems),
        "orphan_nodes": len(orphans),
        "missing_directories": missing_directories,
        "generated_file_count": len(generated_files),
        "missing_generated_files": missing_generated_files,
        "modified_generated_files": modified_generated_files,
        "manual_markdown_nodes": len(manual_markdown),
        "marker_errors": marker_errors,
        "unresolved_examples": unresolved[:20],
        "duplicate_stem_details": duplicate_stems,
        "orphan_examples": orphans[:20],
        "valid": not missing_directories
        and not unresolved
        and not duplicate_stems
        and not marker_errors
        and not missing_generated_files
        and len(edges) > 0,
    }
    state_dir = vault / "03-处理状态"
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "vault_validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"validate_obsidian_vault failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
