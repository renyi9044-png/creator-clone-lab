# Creator Clone Reference

## Clone Artifact

Create `05_creator_clone/creator_clone.md` with:

```text
Positioning
Audience assumptions
Accepted and rejected topic rules
Angle selection rules
Thinking and proof standards
Hook rules
Structure rules
Expression rules
Visual rules
Ending and conversion rules
High-performance patterns
Weak-performance boundaries
Open hypotheses
Counterexamples
Self-check rubric
Version history
```

## Rule Template

```text
Rule:
When to use:
Required input:
Supporting source IDs:
Counterexamples:
High/weak sample coverage:
Expected metric:
Confidence:
Boundary:
```

## Generation Contract

- Retrieve creator rules before generating.
- Use decision logic, not copied wording.
- Make production requirements explicit.
- Reject ideas that only imitate vocabulary or aesthetics.
- Mark output provisional when the supporting clone is provisional.

## Retrospective Contract

Save prediction before publication. After metrics arrive, compare prediction with actual outcome. Add evidence, change confidence, or reject a rule; do not rewrite earlier predictions or raw evidence.

Record multiple snapshots, then generate a traceable retrospective:

```bash
python scripts/record_performance.py <project_dir> <source_id> --stage T+1h --metric views=1000 --metric likes=50
python scripts/record_performance.py <project_dir> <source_id> --stage T+24h --metric views=5000 --metric likes=300
python scripts/generate_retrospective.py <project_dir> <source_id>
```
