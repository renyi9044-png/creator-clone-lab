# Knowledge Project Reference

## Directory Responsibilities

```text
00_rules              schemas, evidence policy, quality gates
01_sources/raw        immutable article, text, and metadata source copies
01_sources/media      immutable video/audio source copies
02_normalized         transcripts, OCR, frames, normalized documents
03_atom_store         aggregate JSONL atom corpus and quarterly shards
04_content_units      reviewed QST/CON/OPI/CAS/SOL Markdown units
05_creator_patterns   reviewed HOK/STR/EXP/VIS/CTA Markdown units
06_topic_maps         maps that organize units and show raw-atom support
07_creator_clone      creator rules, boundaries, self-checks, versions
08_creations          generated topics, assemblies, scripts, predictions
09_performance        publishing metric snapshots
10_state              coverage, indexes, import reports, next action
11_reports            exportable distillation and retrospective reports
index                 SQLite data and FTS search index
内容资产工程            generated Obsidian product with one clickable file per graph node
```

## Obsidian Product Layer

The canonical backend remains JSONL, reviewed Markdown units, and SQLite. The user-facing knowledge base is a generated Obsidian vault:

```text
内容资产工程/
  00-规则与索引
  01-原始素材区
  02-内容单元库
  03-处理状态
  04-模板
  05-主题地图
  06-选题装配
  07-脚本与工具
  08-人工笔记
  .obsidian
```

The generator expands raw JSON atoms into independent Markdown notes, while retaining the canonical JSONL store for safe batch updates. Obsidian `[[wikilinks]]` connect source copies, source indexes, evidence atoms, promoted units, creator patterns, topics, and assemblies. Do not create synthetic nodes to imitate a dense graph; graph size must reflect imported evidence.

Vault rebuilds are incremental and managed by `.creator-clone-vault.json`:

- Every generated file has a stored SHA-256 hash.
- Only generated files are updated or removed.
- `08-人工笔记` and untracked files are preserved.
- A modified generated file is copied to `10_state/vault_backups` before replacement.
- A pre-V2.5 vault receives one full legacy snapshot before its first incremental build.
- Obsidian app, graph, and workspace settings are preserved after their initial creation.

Each evidence row in a promoted unit resolves raw-atom links by source and exact locator first, then by supporting excerpt. Ambiguous evidence remains unlinked rather than pointing at an unrelated atom.

Build and validate after every material update:

```bash
python scripts/build_obsidian_vault.py <project_dir>
python scripts/validate_obsidian_vault.py <project_dir>/内容资产工程
```

Validation must report zero unresolved links, duplicate stems, marker errors, and missing generated files. A successful build also saves an Obsidian workspace that opens the relationship graph first.

The `03-处理状态/待审核队列.md` Vault node mirrors active items from `10_state/review_queue.jsonl` and links them back to raw atoms or promoted units.

## Source Rules

- Register a source before using it as evidence.
- Do not overwrite immutable source copies.
- Use a stable source ID based on platform and canonical URL/path.
- Store signed download URLs only transiently; never place them in the registry.
- Store the permanent public URL when available.
- Track `metadata-only`, `partial`, or `full` understanding explicitly.

## Raw Atom Rules

Raw atoms are compact JSON objects in `atoms.jsonl` and `shards/atoms_YYYYQn.jsonl`. They preserve atomic evidence at scale and are not one-file-per-atom Markdown notes.

Required fields: `id`, `knowledge`, `original`, `source_id`, `source_locator`, `date`, `topics`, `skills`, `type`, `confidence`, `status`, and `unit_ids`.

## Promotion Rules

A promoted unit is one reusable claim or creator pattern, not a source summary. Split unrelated claims and cite supporting raw atom IDs.

Required dimensions:

- Type: QST, CON, OPI, CAS, SOL, HOK, STR, EXP, VIS, CTA.
- Status: fact, pattern, hypothesis, rejected.
- Confidence: low, medium, high.
- Sources and precise evidence locations.
- Topics and performance segment when known.
- Relationships only when they improve retrieval or reasoning.
- Raw atom IDs supporting the promoted unit.

Allowed relationships:

```text
responds_to / explains / proves / conflicts_with / follows / adapts_to
```

## Retrieval Rules

- Search raw atoms, promoted units, and normalized source documents.
- Prefer high-confidence patterns only when evidence coverage is sufficient.
- Include counterexamples when answering "how this creator works".
- Cite source ID and timestamp/page/section.
- Say "not enough evidence" instead of filling gaps with generic creator advice.

## Progressive Modes

1. Audit: inventory sources, formats, tools, duplicates, and boundaries.
2. Sample: process representative high and weak samples; stabilize atom types.
3. Batch: process fixed batches, review errors and duplicates after each batch.
4. Stable: allow broad generation only after evidence, counterexample, and retrospective gates pass.

## Maintenance Commands

```bash
python scripts/generate_duplicate_candidates.py <project_dir>
python scripts/rebuild_raw_atom_store.py <project_dir>
python scripts/raw_atom_status.py <project_dir>
python scripts/generate_relation_map.py <project_dir>
python scripts/generate_topic_maps.py <project_dir>
python scripts/build_creator_clone.py <project_dir>
python scripts/project_status.py <project_dir>
python scripts/processing_queue.py <project_dir> status
python scripts/run_batch_maintenance.py <project_dir>
python scripts/review_queue.py <project_dir> status
python scripts/build_obsidian_vault.py <project_dir>
python scripts/validate_obsidian_vault.py <project_dir>/内容资产工程
```

Duplicate candidates require human or Agent review; never merge them automatically. Repair missing relationship targets before rebuilding the clone.

## Source Of Truth

`SOURCE_OF_TRUTH.md` defines conflict rules. JSONL raw atoms and Markdown promoted units are portable source artifacts; SQLite is the searchable acceleration layer. If they disagree, repair and rebuild the index rather than silently choosing one.
