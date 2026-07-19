#!/usr/bin/env python
"""Render an Obsidian vault's resolved wikilinks as a portable PNG preview."""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import networkx as nx
from PIL import Image, ImageDraw, ImageFont


PALETTE = {
    "来源": "#1677ff",
    "证据原子": "#7a828d",
    "问题单元": "#f59e0b",
    "概念单元": "#06b6d4",
    "观点单元": "#ef4444",
    "案例单元": "#22c55e",
    "方案单元": "#14b8a6",
    "创作模式": "#8b5cf6",
    "主题地图": "#eab308",
    "选题装配": "#ec4899",
    "规则与索引": "#111827",
    "其他": "#9ca3af",
}


def node_type(path: Path, vault: Path) -> str:
    relative = path.relative_to(vault).as_posix()
    if relative.startswith("01-原始素材区"):
        return "来源"
    if relative.startswith("02-内容单元库/证据原子"):
        return "证据原子"
    for name in ("问题单元", "概念单元", "观点单元", "案例单元", "方案单元"):
        if f"/{name}/" in f"/{relative}":
            return name
    if relative.startswith("02-内容单元库/创作模式单元"):
        return "创作模式"
    if relative.startswith("05-主题地图"):
        return "主题地图"
    if relative.startswith("06-选题装配"):
        return "选题装配"
    if relative.startswith("00-规则与索引") or path.name in {
        "README.md",
        "SOURCE_OF_TRUTH.md",
        "AGENTS.md",
        "CLAUDE.md",
    }:
        return "规则与索引"
    return "其他"


def load_graph(vault: Path) -> tuple[nx.Graph, dict[str, Path]]:
    files = list(vault.rglob("*.md"))
    by_stem = {path.stem: path for path in files}
    graph = nx.Graph()
    for stem, path in by_stem.items():
        graph.add_node(stem, kind=node_type(path, vault), path=str(path.relative_to(vault)))
    for source, path in by_stem.items():
        text = path.read_text(encoding="utf-8", errors="replace")
        for target in re.findall(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]", text):
            target_stem = Path(target).stem
            if target_stem in by_stem and source != target_stem:
                graph.add_edge(source, target_stem)
    return graph, by_stem


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def shorten(value: str, limit: int = 24) -> str:
    value = re.sub(r"^[A-Z]{3}-[A-Z0-9-]+_", "", value)
    return value if len(value) <= limit else value[: limit - 1] + "…"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vault_dir")
    parser.add_argument("--output", default="")
    parser.add_argument("--width", type=int, default=2200)
    parser.add_argument("--height", type=int, default=1500)
    args = parser.parse_args()

    vault = Path(args.vault_dir).resolve()
    output = Path(args.output).resolve() if args.output else vault / "03-处理状态" / "关系图谱预览.png"
    graph, _ = load_graph(vault)
    if not graph.nodes or not graph.edges:
        raise RuntimeError("vault has no resolved graph to render")

    width, height = args.width, args.height
    sidebar_width = 520
    graph_width = width - sidebar_width
    margin = 90
    canvas = Image.new("RGB", (width, height), "#fafafa")
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, 0, graph_width, height), fill="#ffffff")

    positions = nx.spring_layout(
        graph,
        seed=26,
        k=max(0.28, 2.2 / math.sqrt(max(len(graph), 1))),
        iterations=350,
        weight=None,
    )
    normalized = {}
    for node, (x, y) in positions.items():
        px = margin + (x + 1) * (graph_width - 2 * margin) / 2
        py = margin + (y + 1) * (height - 2 * margin) / 2
        normalized[node] = (px, py)

    for left, right in graph.edges:
        draw.line((*normalized[left], *normalized[right]), fill="#b8c0cc66", width=2)

    degrees = dict(graph.degree())
    for node in sorted(graph.nodes, key=lambda item: degrees[item]):
        x, y = normalized[node]
        degree = degrees[node]
        radius = min(18, 4 + math.sqrt(max(degree, 1)) * 2.2)
        color = PALETTE[graph.nodes[node]["kind"]]
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color, outline="#ffffff", width=2)

    labeled = set(sorted(graph.nodes, key=lambda item: degrees[item], reverse=True)[:14])
    labeled.update(node for node in graph.nodes if graph.nodes[node]["kind"] == "主题地图")
    label_font = font(19)
    for node in labeled:
        x, y = normalized[node]
        label = shorten(node)
        box = draw.textbbox((0, 0), label, font=label_font)
        text_width = box[2] - box[0]
        text_height = box[3] - box[1]
        tx = min(graph_width - text_width - 14, x + 10)
        ty = max(8, min(height - text_height - 8, y - text_height - 8))
        draw.rounded_rectangle(
            (tx - 5, ty - 3, tx + text_width + 5, ty + text_height + 3),
            radius=4,
            fill="#ffffffdd",
        )
        draw.text((tx, ty), label, fill="#1f2937", font=label_font)

    title_font = font(38, bold=True)
    heading_font = font(25, bold=True)
    body_font = font(20)
    small_font = font(17)
    side_x = graph_width + 42
    draw.text((side_x, 48), "内容资产关系图谱", fill="#111827", font=title_font)
    draw.text(
        (side_x, 112),
        f"{len(graph.nodes)} 个节点  ·  {len(graph.edges)} 条关系",
        fill="#4b5563",
        font=body_font,
    )
    draw.line((side_x, 158, width - 42, 158), fill="#d1d5db", width=2)

    draw.text((side_x, 195), "节点类型", fill="#111827", font=heading_font)
    y = 248
    counts = {}
    for node in graph.nodes:
        kind = graph.nodes[node]["kind"]
        counts[kind] = counts.get(kind, 0) + 1
    for kind, color in PALETTE.items():
        count = counts.get(kind, 0)
        if not count:
            continue
        draw.ellipse((side_x, y + 4, side_x + 18, y + 22), fill=color)
        draw.text((side_x + 32, y), f"{kind}  {count}", fill="#374151", font=body_font)
        y += 42

    y += 22
    draw.text((side_x, y), "核心连接节点", fill="#111827", font=heading_font)
    y += 52
    for index, node in enumerate(sorted(graph.nodes, key=lambda item: degrees[item], reverse=True)[:10], 1):
        draw.text(
            (side_x, y),
            f"{index:02d}  {shorten(node, 19)}",
            fill="#374151",
            font=small_font,
        )
        draw.text((width - 86, y), str(degrees[node]), fill="#6b7280", font=small_font)
        y += 34

    draw.text(
        (side_x, height - 76),
        "由 Obsidian 双链实时生成 · 无填充节点",
        fill="#6b7280",
        font=small_font,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=95)
    print(f"rendered {len(graph.nodes)} nodes and {len(graph.edges)} edges to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
