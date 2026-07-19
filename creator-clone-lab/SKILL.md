---
name: creator-clone-lab
description: Evidence-first creator intelligence system for capturing Douyin, Xiaohongshu, Kuaishou, Bilibili, WeChat, web, and local content; building a traceable local knowledge base; distilling topic selection, thinking, expression, and visual patterns; creating an AI creator clone; generating and reviewing content; and updating the clone from publishing performance. Use for 抓取对标, 蒸馏博主, 创作者知识库, AI 分身, 选题/脚本生成, 稿件诊断, 数据复盘, or incremental creator updates.
---

# Creator Clone Lab V1.1

## Mission

Turn creator evidence into a local system that can be queried, challenged, reused, and improved:

```text
capture -> understand -> JSONL atoms -> promote units -> topic maps -> Obsidian vault -> assemble -> publish -> retro -> update
```

Do not produce impression-only creator analysis. Produce artifacts with traceable sources.

## Knowledge Architecture

Use four canonical storage layers plus one generated Obsidian product layer. Do not manually maintain thousands of atom files; generate them from the canonical store.

```text
03_atom_store/atoms.jsonl + quarterly shards
-> 04_content_units + 05_creator_patterns
-> 06_topic_maps
-> 08_creations/assemblies
-> 内容资产工程 (generated Obsidian vault)
```

- Raw JSON atoms scale to thousands and retain knowledge, original evidence, source, locator, topics, type, confidence, and promoted unit IDs.
- Content units are reviewed `QST/CON/OPI/CAS/SOL` Markdown assets.
- Creator patterns are reviewed `HOK/STR/EXP/VIS/CTA` Markdown rules.
- Topic maps organize promoted units; assemblies call units to build new content.
- SQLite accelerates search and relations. JSONL and Markdown remain portable source artifacts.
- `内容资产工程` is the user-facing Obsidian vault. It expands every source, raw atom, promoted unit, topic map, and assembly into clickable Markdown nodes with `[[wikilinks]]`.
- The generated vault must contain the `00-规则与索引` through `08-人工笔记` product structure. JSONL or SQLite alone is not a finished knowledge-base delivery.
- Vault builds are incremental. Generated-file hashes control updates; user edits to managed nodes are backed up under `10_state/vault_backups`, and `08-人工笔记` is never overwritten.
- Evidence lines link raw atoms only when source plus locator or excerpt resolves the supporting atom. Never attach every evidence line to the first raw atom in a unit.

## Route The Request

Classify the user's immediate intent before doing work. Run only the required path.

| Intent | Action |
|---|---|
| Capture a link/account | Check tools, use the platform adapter, register captured sources |
| Analyze one item | Capture enough evidence, then return a provisional analysis |
| Distill a creator | Audit sample coverage, segment performance, extract patterns and counterexamples |
| Build a knowledge base | Initialize a project, register sources, create evidence-backed atoms, build the index |
| Query the knowledge base | Search atoms and normalized documents; answer with source IDs and locations |
| Create a creator clone | Build rules only after sample quality gates pass |
| Generate topics/scripts | Retrieve relevant evidence first; state which rules were used |
| Review a draft | Diagnose topic, hook, structure, evidence, expression, and clone fit |
| Analyze publishing data | Import metrics, attribute failure/success, update confidence or hypotheses |
| Update a creator | Capture only new sources, deduplicate, rebuild affected maps and clone rules |
| Process a large corpus | Sync and claim the resumable extraction queue; complete one bounded batch at a time |
| Review candidates | Build the unified review queue; accept, reject, or defer one candidate with evidence |
| Show status | Run `scripts/project_status.py <project_dir>` |

If the request is ambiguous, ask one short question about the desired output. Do not force a full distillation for a simple download.

## First-Run Tool Check

Run from the skill directory:

```bash
python scripts/check_install_media_tools.py
```

Install missing dependencies when needed:

```bash
python scripts/check_install_media_tools.py --install --install-system
```

Core capabilities:

- The `playwright` browser-automation skill is the mandatory controller for every web-platform capture.
- Node.js and `npx` launch Playwright CLI when the dedicated skill wrapper is unavailable.
- `yt-dlp` for public media/page extraction.
- `websocket-client` for logged-in Chrome debug sessions.
- `ffmpeg` and `ffprobe` for media processing.
- `GROQ_API_KEY` for the preferred Groq Whisper ASR path.
- `faster-whisper` as the local ASR fallback when Groq cannot be configured or reached.
- `rapidocr-onnxruntime`, OpenCV, and Pillow for OCR/frame processing.
- NetworkX and Pillow for portable Obsidian relationship-graph previews.
- Python `sqlite3` with FTS5 for the local knowledge index.

Use one Python environment for the checker and all scripts. On Windows decoding errors, set `PYTHONUTF8=1`.
For speech-to-text, configure `GROQ_API_KEY` first and run `transcribe_audio.py` with its default `auto` provider. If the user cannot configure Groq, run `check_install_media_tools.py --install-local-asr`; `auto` then uses local faster-whisper. If Groq is configured but a request fails, `auto` also falls back locally when faster-whisper is installed. Never ask the user to commit or package the key, and do not claim speech was understood until one ASR path succeeds.

## Knowledge Project Quick Start

Initialize one isolated project per creator or research scope:

```bash
python scripts/init_creator_project.py projects/<slug> --name "<project name>" --creator "<creator>" --platform douyin
```

Capture adapters write a portable `capture_manifest.json`. Import the whole capture instead of manually retyping metadata:

```bash
python scripts/import_capture_manifest.py projects/<slug> <capture_manifest.json> --copy --auto-body
```

Register every captured item before deriving knowledge:

```bash
python scripts/register_source.py projects/<slug> \
  --platform douyin \
  --content-type video \
  --creator "<creator>" \
  --url "<source url>" \
  --title "<title>" \
  --body-file "<transcript or normalized document>" \
  --understanding-level full \
  --metric views=10000 \
  --metric likes=500
```

Import extracted raw atoms before creating reusable units:

```bash
python scripts/import_raw_atom_batch.py projects/<slug> <raw_atoms.jsonl>
python scripts/rebuild_raw_atom_store.py projects/<slug>
python scripts/query_raw_atoms.py projects/<slug> "<question>"
python scripts/raw_atom_status.py projects/<slug>
```

Promote repeated or strategically useful atoms into a content or creator-pattern unit:

```bash
python scripts/add_knowledge_atom.py projects/<slug> \
  --type HOK \
  --title "先展示结果再解释工具" \
  --statement "高表现工具内容先展示可见结果，再解释流程。" \
  --topic "工具内容" \
  --status hypothesis \
  --confidence medium \
  --raw-atom-id ATM-EXAMPLE \
  --source-id DY-EXAMPLE \
  --evidence-item "DY-EXAMPLE|00:00-00:04|ASR+visual|先出现结果界面"
```

Rebuild and query:

```bash
python scripts/rebuild_knowledge_index.py projects/<slug>
python scripts/query_knowledge.py projects/<slug> "怎么展示工具结果"
python scripts/project_status.py projects/<slug>
```

Build the Obsidian content-asset product after sources, atoms, units, maps, or assemblies change:

```bash
python scripts/build_obsidian_vault.py projects/<slug>
python scripts/validate_obsidian_vault.py projects/<slug>/内容资产工程
python scripts/render_obsidian_graph.py projects/<slug>/内容资产工程
```

The vault is complete only when validation reports no missing directories, unresolved links, duplicate stems, marker errors, or missing generated files. Open the `内容资产工程` directory as an Obsidian vault; its saved workspace opens the relationship graph as the primary view.

Put all human-authored research in `内容资产工程/08-人工笔记`. Do not hand-edit generated source, atom, unit, map, or assembly nodes as the primary workflow. If a managed node was edited, inspect the automatic backup in `10_state/vault_backups` after rebuilding and move durable additions into the manual zone.

Read [references/knowledge-project.md](references/knowledge-project.md) before building or modifying a knowledge project.

## Semantic Extraction Loop

Do not use a deterministic keyword script as a substitute for understanding content. Use scripts to select and validate work; use the Agent to read transcripts, OCR, frame descriptions, metrics, and source context.

```bash
python scripts/processing_queue.py projects/<slug> sync
python scripts/processing_queue.py projects/<slug> claim --limit 5
# Agent reads the returned batch manifest and writes its expected raw_atoms.jsonl output.
python scripts/processing_queue.py projects/<slug> complete --batch-id <BAT-ID> --atoms <batch.raw_atoms.jsonl>
```

The queue persists `pending/in_progress/completed/failed/blocked`, attempts, batch IDs, and errors. Never mark a source complete when its batch returned no atoms. Recover stale jobs through the next claim instead of duplicating work.

Then run the knowledge maintenance chain:

```bash
python scripts/run_batch_maintenance.py projects/<slug>
python scripts/review_queue.py projects/<slug> status
```

This generates raw and promoted duplicate candidates, promotion candidates, typed relation candidates, the unified review queue, topic maps, clone, validated Vault, and graph preview. Candidates are proposals, not facts.

Review one item explicitly:

```bash
python scripts/review_queue.py projects/<slug> decide <REVIEW-ID> --decision accept --note "evidence checked"
python scripts/review_queue.py projects/<slug> decide <REVIEW-ID> --decision reject --note "false similarity"
python scripts/review_queue.py projects/<slug> decide <REVIEW-ID> --decision defer --note "need more samples"
```

Accepting a relation writes the typed edge to its source unit. Accepting a promotion creates the reviewed unit; use `--type`, `--title`, or `--statement` to correct the suggestion. Duplicate acceptance records confirmation but does not destructively merge evidence. Repair missing relation targets before rebuilding maps or the clone. Read [references/atom-extraction.md](references/atom-extraction.md) for schemas and queue rules.

## Capture And Understanding

Invoke the installed `playwright` skill before every web-platform capture. Use Playwright to open and resolve the URL, take a fresh snapshot, inspect visible page state, detect authentication, perform required interaction, and inspect network activity. Use one named Playwright session per platform or creator so browser state is isolated and reusable.

Do not make a direct HTTP client, `yt-dlp`, or a platform-specific script the first contact with a web source. Those tools may run only after Playwright has confirmed the canonical page, visible access level, and capture target. They are downstream media/data extractors, not replacements for browser verification.

If the `playwright` skill is unavailable, check `npx` and use `npx --yes --package @playwright/cli playwright-cli`. If neither path is available, install Node.js/npm or stop and tell the user exactly what is missing. Do not silently switch to an unverified requests-only workflow.

For every web platform use this Playwright-controlled fallback order:

```text
Playwright opens the public page without login
-> Playwright snapshot + visible DOM/network inspection
-> reuse an authenticated named Playwright session
-> user-assisted login or verification in the headed Playwright window
-> Playwright screenshot + OCR/manual evidence fallback
```

For content understanding use:

```text
metadata/title/description
-> OCR for on-screen text
-> ASR for speech/dialogue
-> visual frame understanding
-> comments and performance context
```

Never label a sample `full` when only metadata was captured.

Understanding levels:

- `metadata-only`: title, description, tags, or metrics only.
- `partial`: some media/text evidence exists, but key speech, images, or scenes are missing.
- `full`: media is captured and the important speech/text/visual information has been processed.

Read [references/platform-capture.md](references/platform-capture.md) for platform-specific commands and fallbacks.

## Evidence-First Knowledge

Promoted unit types:

```text
QST audience question     CON concept          OPI opinion
CAS case or proof         SOL solution         HOK hook
STR structure             EXP expression       VIS visual pattern
CTA ending/conversion
```

Separate these statuses:

- `fact`: directly supported by a source or confirmed metric.
- `pattern`: repeated across independent samples.
- `hypothesis`: plausible but under-tested.
- `rejected`: contradicted by evidence or later performance.

Every raw atom must include a source ID, original evidence, and precise locator. Every promoted unit must cite supporting raw atom IDs. Video evidence should include timestamps; image-text evidence should include page/image indices; article evidence should include section/paragraph locators.

Every generated Obsidian node must have a unique filename stem. Source indexes must link immutable source copies; atom nodes must link sources, topics, and promoted units; promoted units must link the exact supporting raw atom for each evidence locator, plus sources, topics, and related units. Never create filler nodes merely to make the graph look dense.

Do not silently upgrade a hypothesis to a pattern. Record counterexamples and performance bands.

## Quality Gates

- `1-9` fully understood samples: quick analysis only.
- `10-29`: provisional creator clone allowed.
- `30+` across high and weak performance bands: stable candidate.
- A stable clone also requires source traceability, counterexamples, and at least one publishing retrospective.

Do not copy thresholds mechanically when the creator has mixed formats. Separate video, image-text, article, and live content before deriving rules.

## Creator Distillation

Distill five layers:

1. Positioning: recurring audience promise and hidden genre.
2. Topic selection: accepted/rejected topics, triggers, tension, novelty/familiarity balance.
3. Thinking: audience assumptions, decisions, proof standards, what detail becomes content.
4. Expression: hook, scene/paragraph order, voice, visuals, captions, silence, ending.
5. Transferable rules: when to use, inputs required, expected metric, boundary and risk.

For each rule record:

```text
claim
supporting sources
counterexamples
high/weak sample coverage
confidence
applicable formats
failure boundary
```

Read [references/creator-clone.md](references/creator-clone.md) before creating or updating a clone.

## Generate And Review

Retrieve relevant atoms before generation. For every idea or script state:

- Which creator rule it uses.
- Which evidence supports the rule.
- Expected strength: watch time, likes, comments, shares, saves, or follows.
- Production requirements and risks.

The clone must be able to reject a request when it copies surface wording without matching the creator's decision logic.

Write video scripts as scene beats, not generic essays:

```text
shot/visual
spoken line or subtitle
character/action
beat purpose
evidence or creator rule used
```

Build an evidence-linked topic brief before drafting:

```bash
python scripts/assemble_topic.py projects/<slug> --topic "<topic>" --title "<working title>"
```

## Publishing Retrospective

Compare prediction with real performance and classify the cause:

```text
topic / promise / hook / visual proof / information density / pacing /
audience fit / distribution / conversion path
```

Retrospective actions are limited to:

1. Add evidence or a new hypothesis.
2. Raise/lower confidence in an existing rule.
3. Mark a rule rejected or format-specific.

Never rewrite historical evidence to fit a later result.

```bash
python scripts/record_performance.py projects/<slug> <source_id> --stage T+1h --metric views=1000
python scripts/record_performance.py projects/<slug> <source_id> --stage T+24h --metric views=5000
python scripts/generate_retrospective.py projects/<slug> <source_id>
```

After reviewing the retrospective, update affected atoms explicitly, then rebuild topic maps and the clone. The scripts never change rule confidence automatically.

## Safety And Packaging

- Never save or expose cookies, login tokens, signed media URLs, API keys, or browser session secrets.
- Keep raw evidence and generated analysis separate.
- Do not claim official platform access when using browser-visible data.
- Respect creator copyright and platform terms; learn structures and decision patterns rather than reproducing content verbatim.
- Do not copy third-party non-commercial templates or method text into a commercial package. Reimplement general architecture using original schemas and instructions.

## Completion Standard

A knowledge-base task is complete only when:

- The project exists and passes `project_status.py`.
- Sources are registered with understanding levels.
- Captured facts exist in the JSONL atom store and pass atom-store validation.
- Reusable claims are promoted into units linked back to raw atom IDs.
- Search returns source IDs and locations.
- The user is told what is complete, what remains partial, and the next quality gate.
