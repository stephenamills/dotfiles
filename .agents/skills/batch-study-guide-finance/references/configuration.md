# Configuration and run contract

## Contents

- Configuration example
- Transcript grouping
- Declarative PDF and spreadsheet units
- Automatic topic course-map units
- Source extraction and Mermaid validation
- Lifecycle, state, and recovery

## Configuration example

Place `study-guide-batch.json` at the course root. Every configured path must remain under that root.

```json
{
  "input_roots": ["transcripts"],
  "include_globs": ["**/*.txt", "*.txt"],
  "exclude_globs": [],
  "transcript_encoding": "utf-8",
  "max_concurrency": 6,
  "prompts": {
    "root": "prompts/transcript.md",
    "per_unit": {},
    "by_kind": {
      "transcript": null,
      "pdf": "prompts/pdf-companion.md",
      "spreadsheet": "prompts/workbook-manual.md",
      "course_map": null
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
  "course_maps": {
    "enabled": true,
    "output_folder": "0 Course Maps"
  },
  "grouping_overrides": [],
  "unit_overrides": {},
  "approved_unit_flags": [],
  "validators": {
    "required_headings": [],
    "require_completion_marker": true,
    "require_mermaid_diagram": true,
    "validate_mermaid_syntax": true,
    "validate_mermaid_render": false,
    "enforce_heading_numbering": true
  },
  "output_root": "study-guides",
  "candidate_root": ".study-guide-batch/candidates",
  "archive_root": ".study-guide-batch/archive",
  "existing_roots": ["study-guides"],
  "ecc_mirror": true
}
```

The supervisor defaults to `gpt-5.6-sol`, `xhigh` reasoning, high verbosity, and six concurrent Multi Agent V2 leaf workers. Set `max_concurrency` to a course-level value from one through 32; `--max-concurrency` is a one-run override.

`validators.enforce_heading_numbering` defaults to `true`. It requires sequentially numbered H2 major sections and rejects numbered H3 headings outside active learner-work sections such as questions, exercises, problems, drills, cases, applications, assessments, and checklists.

Concurrency does not define a pedagogical group: each unit remains one independent leaf task. The supervisor drains the selected units in batches no larger than the configured limit so completed artifacts can be validated and resumed independently. For roughly 35–40 normal text transcripts, start with six leaves (seven V2 sessions including the dispatcher); use three for unusually long PDF/workbook work, and increase to eight or 12 only after a representative run is stable. A burst of 28 is supported, but creates 29 concurrent sessions and amplifies account-rate, quota, or systematic-prompt failures without improving per-guide quality.

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

## Automatic topic course-map units

`course_maps.enabled` defaults to `true`. After planning transcript, PDF, and spreadsheet units, the supervisor groups their canonical targets by the target’s immediate parent folder under `output_root`. Each parent folder is treated as one major topic and receives a native `course_map` unit. `course_maps.whole_course.enabled` also defaults to `true` and adds one final `course_map` unit whose only sources and dependencies are the topic course maps. A flat output root already represents one whole course, so its single topic map is the final map. Default targets are:

```text
<output_root>/<course_maps.output_folder>/<topic folder name> — Course Map.md
<output_root>/<course_maps.output_folder>/0 <course name> — Complete Course Map.md
```

Each topic-map unit depends on every planned study guide in its topic. The whole-course unit depends on every topic-map unit and has no direct study-guide or original-asset sources. Generation occurs in three dependency phases within the same immutable run:

1. Study-guide units generate and validate in concurrent V2 waves.
2. Course-map units read the approved candidate bytes from phase one, generate concurrently by topic, and pass course-map-specific structure, Mermaid, and relative-link validation.
3. The whole-course unit reads only the approved topic-map candidate bytes from phase two and passes the same in-depth structure, Mermaid, and complete relative-link validation.

Promotion remains atomic across both phases. Existing course maps are archived with the other canonical outputs and restored by the same rollback journal.

Selecting a study-guide unit with `--unit` automatically selects its corresponding topic course map and the whole-course map. `--missing-only` includes missing maps as well as missing guides. Selecting a course-map unit alone is allowed when all of its dependencies are already installed. Disable automatic maps only with an explicit course-level override:

```json
{
  "course_maps": {
    "enabled": false,
    "output_folder": "0 Course Maps"
  }
}
```

To keep topic maps while explicitly suppressing only the final synthesis:

```json
{
  "course_maps": {
    "whole_course": {
      "enabled": false
    }
  }
}
```

Use `unit_overrides` with the generated `course-map-...` unit ID to customize a map title, prompt, target, or exclusion. `prompts.by_kind.course_map` supplies a course-specific map prompt; otherwise the bundled in-depth prompt is used.

## Source extraction and Mermaid validation

PDF extraction uses `pdftotext` with page boundaries and a deterministic context budget. Spreadsheet extraction uses `openpyxl` to inventory worksheets, formulas, formula archetypes, populated cells, styles, merged ranges, tables, validations, conditional formatting, charts, images, hidden dimensions, widths, freeze panes, and cross-sheet structure. Repeated worksheet layouts are compacted by structural signature.

OOXML workbooks are supported for `.xlsx` and `.xlsm`, including OOXML content with a misleading `.xls` suffix. A genuine legacy BIFF `.xls` requires a separately produced read-only `.xlsx` inspection copy and otherwise blocks before generation.

Every candidate must contain at least one fenced Mermaid diagram. D2 fences are unconditionally invalid. With `validate_mermaid_syntax` enabled, every block must pass the installed Mermaid 11.14 parser. `validate_mermaid_render` is disabled by default; when explicitly enabled, every block must also render through `mmdc` at a 1728×1117 CSS-pixel desktop viewport, and every SVG must expose a positive responsive `viewBox` without a fixed pixel width. That opt-in check launches Chromium and therefore needs an unsandboxed macOS process. Parser and render failures enter the diagram-only repair path. Spreadsheet unit instructions additionally require a source-grounded Mermaid dependency flowchart.

The supervisor fingerprints original source bytes, prompts, targets, dependency identities, validators, models, and supervisor/Codex versions. Each wave writes isolated, self-contained row inputs with explicit byte budgets. Model processes cannot write source, output, candidate, or archive roots. Course-map validation additionally requires the full structural contract, at least two valid Mermaid diagrams, and a resolvable relative link to every dependent study chapter.

## Lifecycle, state, and recovery

`generate-all` plans, approves conservative budgets, dispatches generation in bounded leaf-agent waves, waits for every child to reach a terminal state, validates each isolated Markdown artifact, and atomically installs successful candidates. Later waves contain only unresolved units or targeted repairs. Use `--unit` for one configured unit, `--missing-only` for absent canonical targets, or `--candidates-only` to suppress installation.

`repair-sections` creates a fresh immutable run for one installed unit, regenerates only explicitly selected H2 sections and/or one-based Mermaid blocks, validates the patched whole guide, and preserves all unselected bytes. Its successful candidate uses the same promotion and rollback journal as ordinary generation.

When a targeted run produced valid section replacements but failed Mermaid parsing or rendering, `repair-sections --recover-from-run RUN_ID` recovers only the selected sections from the immutable attempt log and routes remaining diagram failures through diagram-only repair. It never installs the failed run's diagram or rewrites unaffected content.

Supervisor SQLite state, leases, attempts, events, status reports, candidates, dispatcher inputs and manifests, isolated Codex thread SQLite state, and promotion journals live under `.study-guide-batch/`. The supervisor never edits Codex's internal state. Resume restarts only interrupted work and never regenerates approved units. Promotion rechecks fingerprints, archives existing targets, and installs candidates atomically. Rollback restores archived targets and returns installed candidates to candidate storage.

`purge-run` is an explicitly destructive lifecycle operation. It refuses a live process owner, any promotion, a shared approval, or a shared plan. Eligible run, candidate, dispatcher, approval, and plan directories are staged before their database rows are deleted in one transaction; a failed transaction restores the staged directories.

Recommended global Codex settings are:

```toml
default_permissions = "nested-codex"

[features.multi_agent_v2]
max_concurrent_threads_per_session = 7
hide_spawn_agent_metadata = false
tool_namespace = "agents"
expose_spawn_agent_model_overrides = false
non_code_mode_only = false

```

Define the matching `[permissions.nested-codex]` profile in the same global configuration. The supervisor loads user configuration and does not pass the legacy `--sandbox` mode. It uses `--ignore-user-config` only for the isolated dispatcher when it detects the Codex 0.144-incompatible `agents.max_threads` setting. When it detects that it is already running inside a Codex sandbox, it passes the child-only `default_permissions=":danger-full-access"` override to avoid a rejected nested macOS Seatbelt application. The parent TUI remains sandboxed. Do not set this override globally, and do not combine permission profiles with `sandbox_mode` or `[sandbox_workspace_write]`.

`max_concurrent_threads_per_session` includes the dispatcher, so the example permits six leaf workers plus one root dispatcher. The V2 settings keep GPT-5.6 Sol on the `agents` tool namespace with visible spawn metadata; `wait_agent` is present by default. The supervisor enables V2 with `--enable multi_agent_v2` and repeats the common table settings as per-invocation overrides, so a dispatcher does not depend on global feature persistence. The explicit command-line enable avoids the incompatible `enabled = true` table syntax in the installed 0.144 CLI family. On that version, a user-level `agents.max_threads` still makes V2 reject startup, so the supervisor detects it and starts only the isolated dispatcher with `--ignore-user-config`; authentication continues to use `CODEX_HOME` and the required V2 configuration is passed explicitly. `enable_fanout`, `agents.max_depth`, `agents.max_threads`, and `agents.job_max_runtime_seconds` are legacy CSV/V1 controls and do not configure V2 waves.
