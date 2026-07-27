# Transcript-only configuration

## Contents

- Configuration
- Grouping and ordering
- Course-map dependency phases
- Validation and lifecycle

## Configuration

Place `study-guide-batch.json` at the course root. All paths must remain under that root. Supported
sources are UTF-8 `.txt` transcripts only. The supervisor rejects asset, PDF, spreadsheet, and
workbook fields.

```json
{
  "input_roots": ["transcripts"],
  "include_globs": ["**/*.txt", "*.txt"],
  "exclude_globs": [],
  "transcript_encoding": "utf-8",
  "models": {"generator": "gpt-5.6-sol"},
  "model_reasoning_effort": "xhigh",
  "model_verbosity": "high",
  "max_concurrency": 6,
  "lesson_catalog": {
    "enabled": false,
    "label_style": "readable",
    "topic_maps": false,
    "whole_course": false
  },
  "generation": {"include_existing_target_context": true},
  "prompts": {
    "root": null,
    "per_unit": {},
    "by_kind": {"transcript": null, "course_map": null}
  },
  "grouping_overrides": [],
  "course_maps": {
    "enabled": true,
    "output_folder": "0 Course Maps",
    "whole_course": {"enabled": true, "title": null, "output": null}
  },
  "unit_overrides": {},
  "approved_unit_flags": [],
  "validators": {
    "required_headings": [],
    "require_completion_marker": true,
    "require_mermaid_diagram": true,
    "validate_mermaid_syntax": true,
    "validate_mermaid_render": false,
    "forbid_source_attribution": true,
    "enforce_heading_numbering": true
  },
  "output_root": "study chapters",
  "candidate_root": ".study-guide-batch/candidates",
  "archive_root": ".study-guide-batch/archive",
  "existing_roots": ["study chapters"],
  "ecc_mirror": true
}
```

Defaults are `gpt-5.6-sol`, `xhigh`, high verbosity, and six leaf workers. Individual model calls
have no shorter timeout; the immutable run hard deadline is the only wall-clock stop. Concurrency
may be set from one through 32.

`lesson_catalog.enabled` adds an ordered, readable lesson-name catalog to every transcript chapter.
Labels are derived only from transcript filenames; media files are neither read nor validated.
`topic_maps` propagates chapter lesson names into each topic map, while `whole_course` controls
whether the complete-course map repeats them. The only supported label style is `readable`.

Set `generation.include_existing_target_context` to false for genuinely fresh regeneration. Existing
targets remain fingerprinted and are still archived during atomic promotion, but their contents are
not supplied to generation workers.

## Grouping and ordering

Planning recognizes numbered modules and lessons, Roman-numeral parts, common part suffixes, and
parent folders. It uses natural culinary filename order and never creates fixed-size bundles.
`grouping_overrides` can merge ordered sources, explicitly exclude sources, rename a unit, approve a
flag, or assign its exact Markdown target. Every exclusion is reported in the immutable plan.

## Course-map dependency phases

Topic folders are the immediate parents of chapter targets under `output_root`. With maps enabled,
generation proceeds in three dependency phases:

1. Generate and validate transcript study chapters.
2. Generate topic maps from only approved chapter candidates.
3. Generate the whole-course map from only approved topic-map candidates.

Topic maps default to `<output_root>/<output_folder>/<topic> — Course Map.md`. The whole-course map
defaults to `<output_root>/<output_folder>/0 <course> — Complete Course Map.md`. Each map must link
every direct dependency, match its exact 13-section structure, and contain at least two Mermaid
diagrams. Selecting a chapter also selects its topic map and the whole-course map.

## Validation and lifecycle

Every candidate requires the completion marker, at least one valid Mermaid diagram, direct
instruction without rhetorical source attribution, sequentially numbered H2 headings, and ordinary
unnumbered H3 headings. Numbered H3 headings are allowed only for exercises, drills, questions,
applications, assessments, and checklist steps. Topic and whole-course maps have separate bundled
prompts and exact heading structures.

Plans, approvals, fingerprints, candidates, attempts, leases, promotion journals, and rollback
archives live under `.study-guide-batch/`. Plans are immutable. Resume retries only unresolved work;
targeted diagram, attribution, and section repairs preserve unaffected bytes. Promotion rechecks
fingerprints and installs atomically. Rollback restores archived targets. Never edit the SQLite state.
