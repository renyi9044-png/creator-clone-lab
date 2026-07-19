# Semantic Atom Extraction

## Responsibility Split

- Use scripts for capture, ASR, OCR, JSONL validation, sharding, indexing, deduplication, and relationship checks.
- Use the Agent to read normalized sources and extract atomic evidence.
- Use semantic review to promote repeated, conflicting, or strategically useful atoms into units.
- Never infer creator logic from keyword frequency alone.

## Batch Workflow

```bash
python scripts/processing_queue.py <project_dir> sync
python scripts/processing_queue.py <project_dir> claim --limit 5
# Agent reads 10_state/extraction_batches/<BAT-ID>.jobs.json.
# Agent writes the expected <BAT-ID>.raw_atoms.jsonl.
python scripts/processing_queue.py <project_dir> complete --batch-id <BAT-ID> --atoms <BAT-ID>.raw_atoms.jsonl
python scripts/run_batch_maintenance.py <project_dir>
python scripts/review_queue.py <project_dir> status
```

If extraction fails, return jobs to the queue with:

```bash
python scripts/processing_queue.py <project_dir> fail --batch-id <BAT-ID> --error "reason"
```

The next claim recovers stale `in_progress` jobs and retries failed jobs up to the configured attempt limit. Submitted atom source IDs must belong to the claimed batch.

## Candidate Review

`run_batch_maintenance.py` creates four candidate classes:

- Raw atom duplicates: similar evidence that may represent repeated support.
- Promoted unit duplicates: overlapping reusable units that require canonical review.
- Promotions: repeated same-type raw atoms across independent sources.
- Relations: typed `responds_to/explains/proves/follows/adapts_to` suggestions with scores and reasons.

Candidates are stored in `10_state/review_queue.jsonl` and mirrored to the Obsidian `待审核队列` node. Decisions are appended to `10_state/review_decisions.jsonl`.

Never auto-merge duplicate evidence. Accepting a duplicate confirms similarity only. Accept relation and promotion candidates only after reading the linked sources and raw atoms.

## Raw Atom Schema

```json
{
  "id": "ATM-OPTIONAL-STABLE-ID",
  "knowledge": "One normalized atomic fact.",
  "original": "Short original evidence or faithful evidence description.",
  "source_id": "SOURCE-ID",
  "source_locator": "00:00-00:05",
  "source_url": "https://permanent-public-url.example/item",
  "date": "2026-07-14",
  "topics": ["topic-slug"],
  "skills": ["creator-clone-lab"],
  "type": "observation",
  "confidence": "medium",
  "status": "fact",
  "creator": "creator name",
  "platform": "douyin",
  "unit_ids": []
}
```

## Promotion Schema

A promoted unit uses `QST/CON/OPI/CAS/SOL` for content or `HOK/STR/EXP/VIS/CTA` for creator patterns. It must include `raw_atom_ids`, `source_ids`, `topics`, `keywords`, `canonical`, `version`, evidence, and relationships.

## Rules

- Extract atomic evidence, not every sentence and not a source summary.
- Keep thousands of raw atoms in JSONL; do not create thousands of Markdown files.
- Default interpretations to `hypothesis`; use `pattern` only after repeated independent evidence.
- Promote only stable, repeated, conflicting, or strategically useful atoms.
- Preserve weak-performing samples and counterexamples.
- Cite precise timestamps, image indices, pages, sections, or paragraphs.
- Never invent missing scenes, speech, metrics, or creator intent.
