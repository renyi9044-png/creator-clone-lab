#!/usr/bin/env python
"""Build a real Obsidian content-asset vault from a Creator Clone Lab project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from knowledge_store import connect_db, ensure_project, now_iso, resolve_stored_path, slugify
from raw_atom_store import load_corpus


TYPE_FOLDERS = {
    "QST": "问题单元",
    "CON": "概念单元",
    "OPI": "观点单元",
    "CAS": "案例单元",
    "SOL": "方案单元",
    "HOK": "创作模式单元/开头模式",
    "STR": "创作模式单元/结构模式",
    "EXP": "创作模式单元/表达模式",
    "VIS": "创作模式单元/画面模式",
    "CTA": "创作模式单元/结尾模式",
}


def safe_title(value: str, limit: int = 64) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", value).strip(" .-")
    return (cleaned or "未命名")[:limit].rstrip(" .-")


def frontmatter(values: dict) -> str:
    return "---\n" + "\n".join(
        f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in values.items()
    ) + "\n---\n"


def wikilink(stem: str, label: str | None = None) -> str:
    return f"[[{stem}|{label}]]" if label and label != stem else f"[[{stem}]]"


def normalize_locator(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def matching_raw_atom_ids(evidence: dict, raw_ids: list[str], raw_by_id: dict[str, dict]) -> list[str]:
    candidates = [
        raw_by_id[raw_id]
        for raw_id in raw_ids
        if raw_id in raw_by_id and raw_by_id[raw_id]["source_id"] == evidence["source_id"]
    ]
    location = normalize_locator(evidence.get("location"))
    if location:
        exact = [atom["id"] for atom in candidates if normalize_locator(atom.get("source_locator")) == location]
        if exact:
            return exact
    excerpt = (evidence.get("excerpt") or "").strip()
    if excerpt:
        excerpt_matches = [
            atom["id"]
            for atom in candidates
            if excerpt in (atom.get("original") or "") or excerpt in (atom.get("knowledge") or "")
        ]
        if excerpt_matches:
            return excerpt_matches
    return [candidates[0]["id"]] if len(candidates) == 1 else []


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative_path(value: str | Path) -> str:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe vault-relative path: {value}")
    return path.as_posix()


class VaultWriter:
    """Incrementally replace generated files while preserving user-authored work."""

    def __init__(self, vault: Path, state_dir: Path) -> None:
        self.vault = vault
        self.state_dir = state_dir
        self.marker_path = vault / ".creator-clone-vault.json"
        self.previous_files: dict[str, str] = {}
        self.generated_files: set[str] = set()
        self.backups: list[dict[str, str]] = []
        self.backup_root: Path | None = None
        self.legacy_snapshot: Path | None = None
        if vault.exists():
            if not self.marker_path.exists():
                raise RuntimeError(f"refusing to update an unrecognized directory: {vault}")
            marker = json.loads(self.marker_path.read_text(encoding="utf-8"))
            previous = marker.get("generated_files") or {}
            if isinstance(previous, dict):
                self.previous_files = {
                    safe_relative_path(str(key)): str(value) for key, value in previous.items()
                }
            if not self.previous_files:
                self.legacy_snapshot = self._backup_directory("legacy-full-snapshot")
        vault.mkdir(parents=True, exist_ok=True)

    def _timestamp(self) -> str:
        return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")

    def _backup_directory(self, reason: str) -> Path:
        destination = self.state_dir / "vault_backups" / f"{self._timestamp()}-{reason}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.vault, destination)
        self.backups.append({"reason": reason, "source": ".", "backup": str(destination)})
        return destination

    def _ensure_backup_root(self) -> Path:
        if self.backup_root is None:
            self.backup_root = self.state_dir / "vault_backups" / f"{self._timestamp()}-modified-files"
            self.backup_root.mkdir(parents=True, exist_ok=True)
        return self.backup_root

    def _backup_file(self, relative: str, reason: str) -> None:
        source = self.vault / relative
        if not source.is_file() or self.legacy_snapshot is not None:
            return
        destination = self._ensure_backup_root() / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            destination = destination.with_name(f"{destination.name}.{self._timestamp()}.bak")
        shutil.copy2(source, destination)
        self.backups.append({"reason": reason, "source": relative, "backup": str(destination)})

    def _protect_existing(self, relative: str) -> None:
        path = self.vault / relative
        if not path.is_file() or self.legacy_snapshot is not None:
            return
        previous_hash = self.previous_files.get(relative)
        current_hash = file_sha256(path)
        if previous_hash is None:
            self._backup_file(relative, "generated-path-collision")
        elif current_hash != previous_hash:
            self._backup_file(relative, "modified-generated-file")

    def write_bytes(self, relative: str | Path, content: bytes) -> None:
        relative_text = safe_relative_path(relative)
        self._protect_existing(relative_text)
        path = self.vault / relative_text
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
        temporary.write_bytes(content)
        temporary.replace(path)
        self.generated_files.add(relative_text)

    def write_text(self, relative: str | Path, content: str) -> None:
        self.write_bytes(relative, content.encode("utf-8"))

    def copy_file(self, source: Path, relative: str | Path) -> None:
        self.write_bytes(relative, source.read_bytes())

    def preserve_existing_or_write(self, relative: str | Path, content: str) -> None:
        relative_text = safe_relative_path(relative)
        path = self.vault / relative_text
        if path.exists():
            self.generated_files.add(relative_text)
            return
        self.write_text(relative_text, content)

    def finalize(self, marker: dict) -> dict:
        stale_files = sorted(set(self.previous_files) - self.generated_files)
        removed_files = []
        for relative in stale_files:
            path = self.vault / relative
            if not path.is_file():
                continue
            if file_sha256(path) != self.previous_files[relative]:
                self._backup_file(relative, "modified-stale-generated-file")
            path.unlink()
            removed_files.append(relative)
        generated_hashes = {
            relative: file_sha256(self.vault / relative)
            for relative in sorted(self.generated_files)
            if (self.vault / relative).is_file()
        }
        marker = {**marker, "generated_files": generated_hashes}
        temporary = self.marker_path.with_name(f".{self.marker_path.name}.tmp-{os.getpid()}")
        temporary.write_text(json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.marker_path)
        report = {
            "generated_at": marker["generated_at"],
            "mode": "incremental",
            "generated_file_count": len(generated_hashes),
            "removed_stale_files": removed_files,
            "backup_count": len(self.backups),
            "backups": self.backups,
            "manual_zone": str(self.vault / "08-人工笔记"),
        }
        report_path = self.state_dir / "vault_build_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report


def write_obsidian_config(writer: VaultWriter) -> None:
    writer.preserve_existing_or_write(
        ".obsidian/app.json",
        json.dumps(
            {
                "newLinkFormat": "shortest",
                "useMarkdownLinks": False,
                "alwaysUpdateLinks": True,
                "showUnsupportedFiles": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    color_groups = [
        ("path:\"01-原始素材区\"", 10070709),
        ("path:\"02-内容单元库/证据原子\"", 8421504),
        ("path:\"02-内容单元库/问题单元\"", 16753920),
        ("path:\"02-内容单元库/概念单元\"", 3373055),
        ("path:\"02-内容单元库/观点单元\"", 16724787),
        ("path:\"02-内容单元库/案例单元\"", 6737151),
        ("path:\"02-内容单元库/方案单元\"", 3394611),
        ("path:\"02-内容单元库/创作模式单元\"", 13224393),
        ("path:\"05-主题地图\"", 16766720),
        ("path:\"06-选题装配\"", 16729344),
    ]
    graph = {
        "collapse-filter": False,
        "search": "",
        "showTags": False,
        "showAttachments": False,
        "hideUnresolved": True,
        "showOrphans": True,
        "collapse-color-groups": False,
        "colorGroups": [{"query": query, "color": {"a": 1, "rgb": rgb}} for query, rgb in color_groups],
        "collapse-display": False,
        "showArrow": True,
        "textFadeMultiplier": -0.45,
        "nodeSizeMultiplier": 0.8,
        "lineSizeMultiplier": 0.7,
        "collapse-forces": False,
        "centerStrength": 0.45,
        "repelStrength": 9,
        "linkStrength": 1,
        "linkDistance": 120,
        "scale": 0.55,
        "close": True,
    }
    writer.preserve_existing_or_write(
        ".obsidian/graph.json", json.dumps(graph, ensure_ascii=False, indent=2)
    )
    workspace = {
        "main": {
            "id": "main",
            "type": "split",
            "children": [
                {
                    "id": "main-tabs",
                    "type": "tabs",
                    "children": [
                        {
                            "id": "relationship-graph",
                            "type": "leaf",
                            "state": {
                                "type": "graph",
                                "state": {},
                                "icon": "lucide-git-fork",
                                "title": "关系图谱",
                            },
                        }
                    ],
                    "currentTab": 0,
                }
            ],
            "direction": "vertical",
        },
        "left": {
            "id": "left-sidebar",
            "type": "split",
            "children": [
                {
                    "id": "left-tabs",
                    "type": "tabs",
                    "children": [
                        {
                            "id": "file-explorer",
                            "type": "leaf",
                            "state": {
                                "type": "file-explorer",
                                "state": {"sortOrder": "alphabetical", "autoReveal": True},
                                "icon": "lucide-folder-closed",
                                "title": "文件列表",
                            },
                        }
                    ],
                }
            ],
            "direction": "horizontal",
            "width": 320,
        },
        "right": {
            "id": "right-sidebar",
            "type": "split",
            "children": [
                {
                    "id": "right-tabs",
                    "type": "tabs",
                    "children": [
                        {
                            "id": "backlinks",
                            "type": "leaf",
                            "state": {
                                "type": "backlink",
                                "state": {"collapseAll": False, "extraContext": False, "sortOrder": "alphabetical"},
                                "icon": "links-coming-in",
                                "title": "反向链接",
                            },
                        }
                    ],
                }
            ],
            "direction": "horizontal",
            "width": 300,
            "collapsed": True,
        },
        "active": "relationship-graph",
        "lastOpenFiles": ["README.md", "00-规则与索引/知识工程入口.md"],
    }
    writer.preserve_existing_or_write(
        ".obsidian/workspace.json", json.dumps(workspace, ensure_ascii=False, indent=2)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir")
    parser.add_argument("--output", default="", help="Vault directory; default: <project>/内容资产工程")
    parser.add_argument("--exclude-raw-atoms", action="store_true")
    args = parser.parse_args()
    project = Path(args.project_dir).resolve()
    paths = ensure_project(project)
    output = Path(args.output).resolve() if args.output else project / "内容资产工程"
    writer = VaultWriter(output, paths["state_dir"])
    directories = [
        "00-规则与索引",
        "01-原始素材区/完整副本",
        "01-原始素材区/来源索引",
        "02-内容单元库/问题单元",
        "02-内容单元库/概念单元",
        "02-内容单元库/观点单元",
        "02-内容单元库/案例单元",
        "02-内容单元库/方案单元",
        "02-内容单元库/证据原子",
        "02-内容单元库/创作模式单元/开头模式",
        "02-内容单元库/创作模式单元/结构模式",
        "02-内容单元库/创作模式单元/表达模式",
        "02-内容单元库/创作模式单元/画面模式",
        "02-内容单元库/创作模式单元/结尾模式",
        "03-处理状态",
        "04-模板",
        "05-主题地图",
        "06-选题装配",
        "07-脚本与工具",
        "08-人工笔记",
    ]
    for directory in directories:
        (output / directory).mkdir(parents=True, exist_ok=True)
    write_obsidian_config(writer)

    with connect_db(paths["database"]) as conn:
        sources = [dict(row) for row in conn.execute("SELECT * FROM sources ORDER BY source_id")]
        units = [dict(row) for row in conn.execute("SELECT * FROM atoms ORDER BY atom_type, atom_id")]
        evidence = [dict(row) for row in conn.execute("SELECT * FROM evidence ORDER BY atom_id, evidence_id")]
    raw_atoms = [] if args.exclude_raw_atoms else load_corpus(project)
    evidence_by_unit: dict[str, list[dict]] = defaultdict(list)
    for item in evidence:
        evidence_by_unit[item["atom_id"]].append(item)

    unit_stems = {
        unit["atom_id"]: f"{unit['atom_id']}_{safe_title(unit['title'])}"
        for unit in units
    }
    source_stems = {
        source["source_id"]: f"{source['source_id']}_{safe_title(source.get('title') or '来源')}"
        for source in sources
    }
    raw_stems = {
        atom["id"]: f"{atom['id']}_{safe_title(atom['knowledge'], 48)}"
        for atom in raw_atoms
    }
    raw_by_id = {atom["id"]: atom for atom in raw_atoms}
    topic_names = sorted(
        {topic for unit in units for topic in json.loads(unit["topics_json"] or "[]")}
        | {topic for atom in raw_atoms for topic in atom["topics"]}
    )
    topic_stems = {topic: f"主题_{safe_title(topic)}" for topic in topic_names}

    units_by_source: dict[str, list[str]] = defaultdict(list)
    for unit in units:
        for source_id in json.loads(unit["source_ids_json"] or "[]"):
            units_by_source[source_id].append(unit["atom_id"])
    raws_by_source: dict[str, list[str]] = defaultdict(list)
    for atom in raw_atoms:
        raws_by_source[atom["source_id"]].append(atom["id"])

    for source in sources:
        source_id = source["source_id"]
        body_path = resolve_stored_path(source.get("body_path"), project)
        body = body_path.read_text(encoding="utf-8", errors="replace") if body_path and body_path.exists() else ""
        copy_name = ""
        if body_path and body_path.exists():
            copy_name = (
                f"{source_id}_{safe_title(source.get('title') or body_path.stem)}_原始副本"
                f"{body_path.suffix or '.md'}"
            )
            writer.copy_file(body_path, Path("01-原始素材区") / "完整副本" / copy_name)
        links = [wikilink(unit_stems[unit_id]) for unit_id in units_by_source[source_id] if unit_id in unit_stems]
        raw_links = [wikilink(raw_stems[atom_id]) for atom_id in raws_by_source[source_id] if atom_id in raw_stems]
        content = frontmatter(
            {
                "id": source_id,
                "type": "来源",
                "platform": source["platform"],
                "creator": source.get("creator") or "",
                "url": source.get("url") or "",
                "understanding_level": source["understanding_level"],
                "aliases": [source.get("title") or source_id],
                "tags": ["来源"],
            }
        )
        content += f"\n# {source.get('title') or source_id}\n\n"
        if copy_name:
            content += f"原始副本：[[{Path(copy_name).stem}]]\n\n"
        content += "## 晋升单元\n\n" + ("\n".join(f"- {link}" for link in links) or "- 暂无") + "\n\n"
        content += "## 证据原子\n\n" + ("\n".join(f"- {link}" for link in raw_links) or "- 暂无") + "\n\n"
        content += "## 标准化正文\n\n" + (body or "暂无正文") + "\n"
        writer.write_text(
            Path("01-原始素材区") / "来源索引" / f"{source_stems[source_id]}.md", content
        )

    for atom in raw_atoms:
        unit_links = [wikilink(unit_stems[unit_id]) for unit_id in atom["unit_ids"] if unit_id in unit_stems]
        topic_links = [wikilink(topic_stems[topic]) for topic in atom["topics"] if topic in topic_stems]
        content = frontmatter(
            {
                "id": atom["id"],
                "type": "证据原子",
                "atom_type": atom["type"],
                "source_id": atom["source_id"],
                "source_locator": atom["source_locator"],
                "topics": atom["topics"],
                "confidence": atom["confidence"],
                "status": atom["status"],
                "aliases": [atom["knowledge"]],
                "tags": ["证据原子", atom["type"]],
            }
        )
        content += f"\n# {atom['knowledge']}\n\n## 知识\n\n{atom['knowledge']}\n\n"
        content += f"## 原始证据\n\n{atom['original']}\n\n"
        content += f"来源：{wikilink(source_stems[atom['source_id']])} @ `{atom['source_locator'] or '未指定'}`\n\n"
        content += "主题：" + (" · ".join(topic_links) or "未分类") + "\n\n"
        content += "晋升为：" + (" · ".join(unit_links) or "尚未晋升") + "\n"
        writer.write_text(
            Path("02-内容单元库") / "证据原子" / f"{raw_stems[atom['id']]}.md", content
        )

    for unit in units:
        unit_id = unit["atom_id"]
        topics = json.loads(unit["topics_json"] or "[]")
        source_ids = json.loads(unit["source_ids_json"] or "[]")
        raw_ids = json.loads(unit["raw_atom_ids_json"] or "[]")
        relationships = json.loads(unit["relationships_json"] or "[]")
        related_links = [
            f"- `{relation.get('type')}` → {wikilink(unit_stems[relation['target']])}"
            for relation in relationships if relation.get("target") in unit_stems
        ]
        content = frontmatter(
            {
                "id": unit_id,
                "type": unit["atom_type"],
                "title": unit["title"],
                "themes": topics,
                "keywords": json.loads(unit["keywords_json"] or "[]"),
                "status": unit["status"],
                "confidence": unit["confidence"],
                "canonical": bool(unit["canonical"]),
                "version": unit["version"],
                "source_documents": source_ids,
                "raw_atom_ids": raw_ids,
                "relationships": relationships,
                "aliases": [unit["title"]],
                "tags": ["内容单元", unit["atom_type"]],
            }
        )
        content += f"\n# {unit['title']}\n\n## 核心内容\n\n{unit['statement']}\n\n"
        content += "## 来源依据\n\n"
        for item in evidence_by_unit.get(unit_id, []):
            source_link = wikilink(source_stems[item["source_id"]])
            matched_raw_ids = matching_raw_atom_ids(item, raw_ids, raw_by_id)
            raw_links = [wikilink(raw_stems[raw_id]) for raw_id in matched_raw_ids if raw_id in raw_stems]
            content += (
                f"- {source_link} @ `{item.get('location') or '未指定'}`：{item.get('excerpt') or ''}"
                + (f" · {' · '.join(raw_links)}" if raw_links else "") + "\n"
            )
        content += "\n## 主题\n\n" + (" · ".join(wikilink(topic_stems[t]) for t in topics) or "未分类") + "\n\n"
        content += "## 关联单元\n\n" + ("\n".join(related_links) or "- 暂无") + "\n"
        folder = Path("02-内容单元库") / TYPE_FOLDERS[unit["atom_type"]]
        writer.write_text(folder / f"{unit_stems[unit_id]}.md", content)

    units_by_topic: dict[str, list[dict]] = defaultdict(list)
    raw_count_by_topic: dict[str, int] = defaultdict(int)
    for unit in units:
        for topic in json.loads(unit["topics_json"] or "[]"):
            units_by_topic[topic].append(unit)
    for atom in raw_atoms:
        for topic in atom["topics"]:
            raw_count_by_topic[topic] += 1
    for topic in topic_names:
        lines = [
            frontmatter({"type": "主题地图", "topic": topic, "aliases": [topic], "tags": ["主题地图"]}),
            f"# 主题地图：{topic}",
            "",
            f"底层证据原子：{raw_count_by_topic[topic]} 条",
            f"晋升内容单元：{len(units_by_topic[topic])} 个",
            "",
        ]
        by_type: dict[str, list[dict]] = defaultdict(list)
        for unit in units_by_topic[topic]:
            by_type[unit["atom_type"]].append(unit)
        for unit_type, items in sorted(by_type.items()):
            lines.extend([f"## {TYPE_FOLDERS[unit_type].split('/')[-1]}", ""])
            lines.extend(f"- {wikilink(unit_stems[item['atom_id']], item['title'])}" for item in items)
            lines.append("")
        writer.write_text(Path("05-主题地图") / f"{topic_stems[topic]}.md", "\n".join(lines))

    assembly_source = paths["creations"] / "assemblies"
    assembly_count = 0
    assembly_stems = []
    if assembly_source.exists():
        for source_file in sorted(assembly_source.glob("*.md")):
            text = source_file.read_text(encoding="utf-8")
            for unit_id, stem in unit_stems.items():
                text = text.replace(f"`{unit_id}`", wikilink(stem, unit_id))
            for topic, stem in topic_stems.items():
                text = re.sub(rf"(?m)^Topic:\s*{re.escape(topic)}\s*$", f"Topic: {wikilink(stem, topic)}", text)
            writer.write_text(Path("06-选题装配") / source_file.name, text)
            assembly_count += 1
            assembly_stems.append(source_file.stem)

    topic_links = [wikilink(topic_stems[topic], topic) for topic in topic_names]
    assembly_links = [wikilink(stem) for stem in sorted(assembly_stems)]
    source_links = [wikilink(source_stems[source["source_id"]]) for source in sources]
    relation_lines = []
    for unit in units:
        source_link = wikilink(unit_stems[unit["atom_id"]], unit["title"])
        for relation in json.loads(unit["relationships_json"] or "[]"):
            target = relation.get("target")
            if target in unit_stems:
                relation_lines.append(
                    f"- {source_link} --`{relation.get('type') or 'related_to'}`--> "
                    f"{wikilink(unit_stems[target])}"
                )

    review_items = []
    review_queue_path = paths["state_dir"] / "review_queue.jsonl"
    if review_queue_path.exists():
        review_items = [
            json.loads(line)
            for line in review_queue_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    review_lines = ["# 待审核队列", ""]
    active_review_items = [item for item in review_items if item.get("active", True)]
    if not active_review_items:
        review_lines.append("- 当前没有审核候选。")
    for item in active_review_items:
        payload = item.get("payload") or {}
        kind = item.get("kind")
        status = item.get("status") or "pending"
        links = []
        if kind == "relation":
            if payload.get("source") in unit_stems:
                links.append(wikilink(unit_stems[payload["source"]]))
            if payload.get("target") in unit_stems:
                links.append(wikilink(unit_stems[payload["target"]]))
        elif kind == "promotion":
            links.extend(
                wikilink(raw_stems[raw_id])
                for raw_id in payload.get("raw_atom_ids") or []
                if raw_id in raw_stems
            )
        else:
            for key in ("left", "right"):
                candidate_id = payload.get(key)
                if candidate_id in raw_stems:
                    links.append(wikilink(raw_stems[candidate_id]))
                elif candidate_id in unit_stems:
                    links.append(wikilink(unit_stems[candidate_id]))
        label = payload.get("suggested_title") or payload.get("reason") or payload.get("classification") or kind
        review_lines.append(
            f"- `{item['review_id']}` [{status}/{kind}] {label}"
            + (f" · {' · '.join(links)}" if links else "")
        )
    review_lines.extend(["", "返回：[[知识工程入口]] · [[处理状态总览]]"])
    writer.write_text(Path("03-处理状态") / "待审核队列.md", "\n".join(review_lines) + "\n")

    writer.write_text(
        Path("00-规则与索引") / "知识工程入口.md",
        "# 知识工程入口\n\n"
        "这是整个内容资产库的导航节点。\n\n"
        "## 核心规则\n\n"
        "- [[SOURCE_OF_TRUTH|唯一事实源]]\n"
        "- [[节点类型说明]]\n"
        "- [[关系索引]]\n"
        "- [[处理状态总览]]\n\n"
        "- [[待审核队列]]\n\n"
        "- [[人工笔记入口]]\n\n"
        "## 主题地图\n\n"
        + ("\n".join(f"- {link}" for link in topic_links) or "- 尚未生成")
        + "\n\n## 选题装配\n\n"
        + ("\n".join(f"- {link}" for link in assembly_links) or "- 尚未生成")
        + "\n",
    )
    writer.write_text(
        Path("00-规则与索引") / "关系索引.md",
        "# 关系索引\n\n"
        "这里汇总显式内容单元关系；来源、证据、主题之间的关系由各节点双链维护。\n\n"
        "## 单元关系\n\n"
        + ("\n".join(relation_lines) or "- 当前没有显式单元关系")
        + "\n\n## 来源入口\n\n"
        + ("\n".join(f"- {link}" for link in source_links) or "- 尚无来源")
        + "\n",
    )
    writer.write_text(
        Path("05-主题地图") / "主题地图总览.md",
        "# 主题地图总览\n\n"
        + ("\n".join(f"- {link}" for link in topic_links) or "- 尚未生成主题地图")
        + "\n\n返回：[[知识工程入口]]\n",
    )
    writer.write_text(
        Path("06-选题装配") / "选题装配总览.md",
        "# 选题装配总览\n\n"
        + ("\n".join(f"- {link}" for link in assembly_links) or "- 尚未生成装配稿")
        + "\n\n返回：[[知识工程入口]]\n",
    )

    templates = {
        "问题单元模板.md": "# {{问题}}\n\n## 问题边界\n\n## 触发场景\n\n## 来源证据\n\n## 关联单元\n",
        "概念单元模板.md": "# {{概念}}\n\n## 定义\n\n## 适用边界\n\n## 来源证据\n\n## 关联单元\n",
        "观点单元模板.md": "# {{观点}}\n\n## 核心判断\n\n## 论据\n\n## 反例与边界\n\n## 来源证据\n",
        "案例单元模板.md": "# {{案例}}\n\n## 背景\n\n## 行动\n\n## 结果\n\n## 可迁移结论\n\n## 来源证据\n",
        "方案单元模板.md": "# {{方案}}\n\n## 适用问题\n\n## 操作步骤\n\n## 验收标准\n\n## 来源证据\n",
        "创作模式模板.md": "# {{模式}}\n\n## 模式定义\n\n## 使用条件\n\n## 结构或画面\n\n## 对标证据\n",
    }
    template_links = []
    for filename, body in templates.items():
        relative = Path("04-模板") / filename
        writer.write_text(relative, body + "\n返回：[[节点类型说明]]\n")
        template_links.append(wikilink(relative.stem))

    writer.write_text(
        Path("07-脚本与工具") / "维护工具说明.md",
        "# 维护工具说明\n\n"
        "本库由项目脚本增量生成和校验。系统只更新受管文件，不会删除 `08-人工笔记`。"
        "受管节点被人工修改后，重建前会自动备份到项目的 `10_state/vault_backups`。\n\n"
        "- 入口：[[知识工程入口]]\n"
        "- 状态：[[处理状态总览]]\n"
        "- 规则：[[SOURCE_OF_TRUTH]]\n",
    )

    writer.write_text(
        Path("00-规则与索引") / "人工笔记入口.md",
        "# 人工笔记入口\n\n"
        "请把手工研究、临时判断和补充说明放入 `08-人工笔记`。系统不会覆盖该目录。\n\n"
        "需要让人工笔记进入图谱时，请在笔记中主动链接来源、原子或内容单元。\n\n"
        "返回：[[知识工程入口]] · [[维护工具说明]]\n",
    )

    writer.write_text(
        Path("00-规则与索引") / "节点类型说明.md",
        "# 节点类型说明\n\n"
        "- QST：问题单元\n- CON：概念单元\n- OPI：观点单元\n- CAS：案例单元\n- SOL：方案单元\n"
        "- HOK：开头模式\n- STR：结构模式\n- EXP：表达模式\n- VIS：画面模式\n- CTA：结尾模式\n\n"
        "## 建库模板\n\n"
        + "\n".join(f"- {link}" for link in template_links)
        + "\n\n返回：[[知识工程入口]]\n",
    )
    writer.write_text(
        Path("03-处理状态") / "处理状态总览.md",
        f"# 处理状态总览\n\n生成时间：{now_iso()}\n\n"
        f"- 来源节点：{len(sources)}\n- JSON 证据原子节点：{len(raw_atoms)}\n"
        f"- 内容与模式单元：{len(units)}\n- 主题地图：{len(topic_names)}\n- 选题装配：{assembly_count}\n\n"
        f"- 待审核候选：{len(active_review_items)}\n\n"
        "导航：[[知识工程入口]] · [[关系索引]] · [[待审核队列]] · [[维护工具说明]] · [[人工笔记入口]]\n",
    )
    writer.write_text(
        "README.md",
        "# 创作者内容资产工程\n\n"
        "这是可直接用 Obsidian 打开的知识工程。打开左侧关系图谱即可查看来源、证据原子、内容单元、"
        "创作模式、主题地图和选题装配之间的双向链接。\n\n"
        f"当前规模：{len(sources)} 个来源，{len(raw_atoms)} 条证据原子，{len(units)} 个晋升单元，"
        f"{len(topic_names)} 张主题地图。\n\n"
        "开始使用：[[知识工程入口]] · [[主题地图总览]] · [[选题装配总览]] · [[关系索引]]\n\n"
        "规则与状态：[[SOURCE_OF_TRUTH]] · [[节点类型说明]] · [[处理状态总览]] · [[待审核队列]]\n\n"
        "人工内容：[[人工笔记入口]]\n",
    )
    writer.write_text(
        "SOURCE_OF_TRUTH.md",
        "# Source Of Truth\n\n"
        "原始来源不可改写。证据原子必须链接来源。内容单元必须链接证据原子。"
        "主题地图和选题装配只能调用现有单元，不得伪造证据。\n\n"
        "系统节点由底层证据重新生成；人工补充必须放在 `08-人工笔记` 并通过双链引用。\n\n"
        "入口：[[README|创作者内容资产工程]] · [[知识工程入口]] · [[人工笔记入口]]\n",
    )
    writer.write_text(
        "AGENTS.md",
        "# Agent Rules\n\n编辑前读取 [[SOURCE_OF_TRUTH]]。新增节点必须使用双向链接并保持来源可追溯。\n",
    )
    writer.write_text(
        "CLAUDE.md",
        "# Vault Rules\n\n本目录是 Obsidian 内容资产工程。不要删除 ID、来源链接或关系链接。详见 [[SOURCE_OF_TRUTH]]。\n",
    )
    marker = {
        "schema_version": "2.0",
        "generated_at": now_iso(),
        "project": str(project),
        "source_count": len(sources),
        "raw_atom_count": len(raw_atoms),
        "unit_count": len(units),
        "topic_count": len(topic_names),
        "assembly_count": assembly_count,
    }
    build_report = writer.finalize(marker)
    print(json.dumps({"vault": str(output), **marker, **build_report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"build_obsidian_vault failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
