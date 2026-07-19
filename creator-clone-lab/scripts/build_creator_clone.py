#!/usr/bin/env python
"""Build a versioned evidence-first creator clone from project atoms."""

from __future__ import annotations

import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from knowledge_store import connect_db, ensure_project, now_iso


SECTIONS = {
    "QST": "Audience Problems",
    "CON": "Concepts And Definitions",
    "OPI": "Thinking And Opinions",
    "CAS": "Cases And Proof",
    "SOL": "Solutions",
    "HOK": "Hook Rules",
    "STR": "Structure Rules",
    "EXP": "Expression Rules",
    "VIS": "Visual Rules",
    "CTA": "Ending And Conversion Rules",
}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: build_creator_clone.py <project_dir>", file=sys.stderr)
        return 2
    project = Path(sys.argv[1]).resolve()
    paths = ensure_project(project)
    with connect_db(paths["database"]) as conn:
        source_rows = conn.execute("SELECT understanding_level FROM sources").fetchall()
        atom_rows = conn.execute("SELECT * FROM atoms ORDER BY atom_type, status, atom_id").fetchall()
        evidence_rows = conn.execute(
            "SELECT atom_id, source_id, location, modality FROM evidence ORDER BY atom_id, evidence_id"
        ).fetchall()
    full_count = sum(1 for row in source_rows if row["understanding_level"] == "full")
    segments = {row["performance_segment"] for row in atom_rows if row["performance_segment"]}
    if full_count < 10:
        maturity = "quick-analysis-only"
    elif full_count < 30:
        maturity = "provisional"
    elif any("high" in segment for segment in segments) and any("weak" in segment for segment in segments):
        maturity = "stable-candidate"
    else:
        maturity = "provisional-needs-performance-bands"
    evidence_by_atom: dict[str, list[dict]] = defaultdict(list)
    for evidence in evidence_rows:
        evidence_by_atom[evidence["atom_id"]].append(dict(evidence))
    atoms_by_type: dict[str, list[dict]] = defaultdict(list)
    rejected = []
    hypotheses = []
    for row in atom_rows:
        item = dict(row)
        item["source_ids"] = json.loads(row["source_ids_json"] or "[]")
        item["raw_atom_ids"] = json.loads(row["raw_atom_ids_json"] or "[]")
        if row["status"] == "rejected":
            rejected.append(item)
        elif row["status"] == "hypothesis":
            hypotheses.append(item)
        else:
            atoms_by_type[row["atom_type"]].append(item)

    generated_at = now_iso()
    lines = [
        "# Evidence-Backed Creator Clone",
        "",
        f"Generated: {generated_at}",
        f"Maturity: `{maturity}`",
        f"Fully understood sources: {full_count}",
        f"Knowledge atoms: {len(atom_rows)}",
        "",
        "> This file is generated from registered evidence. Edit source atoms, then rebuild; do not hand-edit rules here.",
        "",
    ]
    for atom_type, section in SECTIONS.items():
        lines.extend([f"## {section}", ""])
        items = atoms_by_type.get(atom_type, [])
        if not items:
            lines.append("- No supported rule yet.")
        for item in items:
            evidence = evidence_by_atom.get(item["atom_id"], [])
            citations = "; ".join(
                f"{entry['source_id']}@{entry.get('location') or 'unspecified'}" for entry in evidence
            ) or ", ".join(item["source_ids"])
            raw_atoms = ", ".join(item["raw_atom_ids"])
            lines.append(
                f"- **{item['title']}** [{item['status']}/{item['confidence']}]  \n"
                f"  {item['statement']}  \n"
                f"  Raw atoms: {raw_atoms or 'not linked'}  \n"
                f"  Evidence: {citations or 'missing'}"
            )
        lines.append("")
    lines.extend(["## Rejected Or Bounded Rules", ""])
    lines.extend(f"- **{item['title']}**: {item['statement']}" for item in rejected)
    if not rejected:
        lines.append("- None recorded.")
    lines.extend(["", "## Open Hypotheses", ""])
    lines.extend(
        f"- **{item['title']}** [{item['confidence']}]: {item['statement']} (sources: {', '.join(item['source_ids'])})"
        for item in hypotheses
    )
    if not hypotheses:
        lines.append("- None recorded.")
    lines.extend(
        [
            "",
            "## Self-Check",
            "",
            "- Does the topic match a supported audience problem or opinion?",
            "- Does the opening use a supported hook rather than copied wording?",
            "- Does the structure have source-backed proof or cases?",
            "- Do the visual and expression choices match the target format?",
            "- Does the ending optimize the intended metric?",
            "- Is any used rule still only a hypothesis?",
            "- Are there counterexamples or rejected rules that apply?",
            "",
        ]
    )
    output_dir = paths["creator_clone"]
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "creator_clone.md"
    content = "\n".join(lines)
    if output.exists() and output.read_text(encoding="utf-8") != content:
        versions = output_dir / "versions"
        versions.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(output, versions / f"creator_clone_{stamp}.md")
    output.write_text(content, encoding="utf-8")
    state_path = paths["state_dir"] / "clone_state.json"
    state_path.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "maturity": maturity,
                "fully_understood_sources": full_count,
                "atom_count": len(atom_rows),
                "performance_segments": sorted(segments),
                "clone_file": output.relative_to(project).as_posix(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"maturity: {maturity}")
    print(f"clone: {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"build_creator_clone failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
