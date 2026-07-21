# Configuration and run contract

## Contents

- Configuration example
- Transcript grouping
- Declarative PDF and spreadsheet units
- Source extraction and D2 validation
- Lifecycle, state, and recovery

## Configuration example

Place `study-guide-batch.json` at the course root. Every configured path must remain under that root.

```json
{
  "input_roots": ["transcripts"],
  "include_globs": ["**/*.txt", "*.txt"],
  "exclude_globs": [],
  "transcript_encoding": "utf-8",
  "prompts": {
    "root": "prompts/transcript.md",
    "per_unit": {},
    "by_kind": {
      "transcript": null,
      "pdf": "prompts/pdf-companion.md",
      "spreadsheet": "prompts/workbook-manual.md"
    }
  },
  "asset_units": [
    {
      "id": "statistics-reference",
      "kind": "pdf",
      "title": "Statistics Reference",
      "sources": ["course-assets/statistics.pdf"],
      "transcripts": ["transcripts/02 Statistics.txt"],
      "output": "study-guides/statistics-reference.md",
      "prompt": "prompts/pdf-companion.md"
    },
    {
      "id": "risk-model-workbook",
      "kind": "spreadsheet",
      "title": "Risk Model Workbook",
      "sources": ["course-assets/model-a.xlsx", "course-assets/model-b.xlsm"],
      "transcripts": ["transcripts/07 Workbook Class.txt"],
      "output": "study-guides/risk-model-workbook.md",
      "prompt": "prompts/workbook-manual.md"
    }
  ],
  "grouping_overrides": [],
  "unit_overrides": {},
  "approved_unit_flags": [],
  "validators": {
    "required_headings": [],
    "require_completion_marker": true,
    "require_d2_diagram": true,
    "forbid_mermaid": true,
    "validate_d2_syntax": true,
    "validate_d2_layout": true
  },
  "output_root": "study-guides",
  "candidate_root": ".study-guide-batch/candidates",
  "archive_root": ".study-guide-batch/archive",
  "existing_roots": ["study-guides"],
  "ecc_mirror": true
}
```

The supervisor defaults to `gpt-5.6-sol`, `xhigh` reasoning, high verbosity, and CSV waves with `max_concurrency = 4`. Advanced runs may use `--max-concurrency` from one through six.

## Transcript grouping

Transcript planning recognizes numbered lessons, hierarchical numbers, parent lesson folders, module/lesson parts, Roman-numeral parts, and common part suffixes. It never makes fixed-size bundles.

Use `grouping_overrides` to merge, exclude, rename, approve a flagged group, or choose an exact target. Use `unit_overrides` for a planned unit ID. Regenerate the plan after any change.

## Declarative PDF and spreadsheet units

Binary assets never become units from filename inference. `list-assets` only inventories supported files (`.pdf`, `.xlsx`, `.xlsm`, and `.xls`). Register an asset through `configure-asset` or an `asset_units` entry.

Each asset unit requires:

- `id`: stable lowercase letters, digits, and hyphens;
- `kind`: `pdf` or `spreadsheet`;
- `title`: human-readable unit title;
- `sources`: one PDF, one workbook, or an explicitly established coherent workbook family;
- `transcripts`: zero or more corresponding text transcripts in lesson order;
- `output`: exact canonical Markdown path; and
- optional `prompt`: exact course-specific prompt path.

An asset unit's explicit prompt overrides `prompts.per_unit`, followed by `prompts.by_kind`; bundled kind-specific defaults are the final fallback. The legacy `prompts.root` applies to transcript units only.

## Source extraction and D2 validation

PDF extraction uses `pdftotext` with page boundaries and a deterministic context budget. Spreadsheet extraction uses `openpyxl` to inventory worksheets, formulas, formula archetypes, populated cells, styles, merged ranges, tables, validations, conditional formatting, charts, images, hidden dimensions, widths, freeze panes, and cross-sheet structure. Repeated worksheet layouts are compacted by structural signature.

OOXML workbooks are supported for `.xlsx` and `.xlsm`, including OOXML content with a misleading `.xls` suffix. A genuine legacy BIFF `.xls` requires a separately produced read-only `.xlsx` inspection copy and otherwise blocks before generation.

Every candidate must contain at least one fenced D2 diagram, must contain no Mermaid fence, and must pass the installed D2 parser when `validate_d2_syntax` is enabled. When `validate_d2_layout` is enabled, diagrams with more than six semantic nodes must also fit the supervisor's balanced rendered-footprint limits; excessively tall or wide diagrams enter the existing diagram-only repair path. Spreadsheet unit instructions additionally require a source-grounded dependency diagram.

The supervisor fingerprints original source bytes, prompts, targets, validators, models, and supervisor/Codex versions. Each wave writes isolated, self-contained row inputs with explicit byte budgets. Model processes cannot write source, output, candidate, or archive roots.

## Lifecycle, state, and recovery

`generate-all` plans, approves conservative budgets, dispatches generation in waves of four, validates exported CSV identity and every reported Markdown artifact, and atomically installs successful candidates. Later waves contain only unresolved units or targeted repairs. Use `--unit` for one configured unit, `--missing-only` for absent canonical targets, or `--candidates-only` to suppress installation.

`repair-sections` creates a fresh immutable run for one installed unit, regenerates only explicitly selected H2 sections and/or one-based D2 blocks, validates the patched whole guide, and preserves all unselected bytes. Its successful candidate uses the same promotion and rollback journal as ordinary generation.

When a targeted run produced valid section replacements but failed diagram layout, `repair-sections --recover-from-run RUN_ID` recovers only the selected sections from the immutable attempt log and routes remaining D2 failures through diagram-only repair. It never installs the failed run's diagram or rewrites unaffected content.

Supervisor SQLite state, leases, attempts, events, status reports, candidates, dispatcher inputs, exported CSVs, Codex job SQLite state, and promotion journals live under `.study-guide-batch/`. The supervisor never edits Codex's internal job tables. Resume restarts only interrupted work and never regenerates approved units. Promotion rechecks fingerprints, archives existing targets, and installs candidates atomically. Rollback restores archived targets and returns installed candidates to candidate storage.

`purge-run` is an explicitly destructive lifecycle operation. It refuses a live process owner, any promotion, a shared approval, or a shared plan. Eligible run, candidate, dispatcher, approval, and plan directories are staged before their database rows are deleted in one transaction; a failed transaction restores the staged directories.

Recommended global Codex settings are:

```toml
default_permissions = "nested-codex"

[features]
multi_agent = true
enable_fanout = true

[features.multi_agent_v2]
hide_spawn_agent_metadata = false
tool_namespace = "agents"

[agents]
max_threads = 6
max_depth = 2
job_max_runtime_seconds = 1800
```

Define the matching `[permissions.nested-codex]` profile in the same global configuration. The supervisor loads user configuration and does not pass `--sandbox` or `--ignore-user-config`. When it detects that it is already running inside a Codex sandbox, it passes the child-only `default_permissions=":danger-full-access"` override to avoid a rejected nested macOS Seatbelt application. The parent TUI remains sandboxed. Do not set this override globally, and do not combine permission profiles with `sandbox_mode` or `[sandbox_workspace_write]`.

`enable_fanout` is the under-development Codex gate for `spawn_agents_on_csv`. The V2 settings keep GPT-5.6 Sol on the `agents` tool namespace with spawn controls visible. The supervisor repeats all three as per-invocation overrides so a dispatcher does not depend on global feature persistence.
