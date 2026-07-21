---
name: study-guide-batch
description: Generate and manage Markdown study guides from local transcripts, PDFs, and Microsoft Excel workbooks through deterministic Codex-native CSV subagent waves. Use when Codex must generate all or missing guides, regenerate one lesson or asset companion, configure PDF companions or spreadsheet study-and-build manuals, resolve unit IDs, inspect status, stop or resume runs, promote candidates, or roll back installed guides. Invoke the bundled supervisor on the user's behalf; do not require the user to operate its CLI.
---

# Study Guide Batch

Act as the TUI controller for the bundled supervisor. Translate natural-language requests into supervisor operations, execute them, monitor long runs, and report exact canonical paths. Keep the Python CLI internal unless the user requests commands.

## Execution contract

- Resolve `scripts/study_guide_batch.py` relative to this file.
- Use the supervisor for configuration, planning, generation, installation, recovery, and rollback. Never edit its SQLite state.
- Let the supervisor launch fresh depth-0 Codex dispatchers with `features.multi_agent=true` and the experimental `features.enable_fanout=true` gate that process generation and repair work through `spawn_agents_on_csv`. For GPT-5.6 Sol V2 sessions, expose spawn metadata and select the `agents` tool namespace per invocation. The default worker concurrency is four; each CSV worker reports exactly one structured result. Use depth two and prohibit worker-spawned agents in the row instruction.
- Let nested Codex processes load user configuration and do not pass the legacy `--sandbox` mode. When the supervisor itself runs inside a Codex sandbox, it gives the child session the scoped `:danger-full-access` permission override so macOS does not attempt a second Seatbelt sandbox; the parent TUI remains the enforcement boundary. Never set this override globally.
- Do not bypass, replace, or manually imitate the CSV dispatcher. If the experimental capability is unavailable, report the supervisor's explicit failure and preserve resumable state.
- Run long foreground commands in a persistent terminal session and poll until completion. Relay concise progress.
- Do not add calibration or independent auditing unless explicitly requested.
- Infer `--root` from an explicit path or unambiguous course folder.
- Resolve user-facing lesson numbers, titles, and filenames yourself; never ask the user to supply a unit ID.

Define the command prefix conceptually as:

```bash
python3 "<skill-directory>/scripts/study_guide_batch.py"
```

## Units and asset registration

Transcript units are discovered from configured text roots. PDF and spreadsheet units are declarative: the supervisor never infers relationships or output names from course-specific filenames.

For a requested PDF or workbook output:

1. Run `list-units --root ROOT`.
2. If the exact asset unit exists, generate it by ID.
3. Otherwise run `list-assets --root ROOT`, resolve the primary source or coherent workbook family, corresponding transcripts, course prompt, and canonical output from the user's request and local course structure.
4. Register the mapping with `configure-asset`, supplying an explicit kind, ID, title, every source, every corresponding transcript, output, and optional prompt.
5. Run `list-units` again, then generate the registered unit.

Register multiple workbook sources in one spreadsheet unit only when the user or course structure establishes a coherent workbook family. Do not group files by similar names alone. Read [references/configuration.md](references/configuration.md) for the asset schema and extraction behavior.

## Natural-language routing

- **Generate everything configured:** `generate-all --root ROOT`
- **Generate only absent canonical outputs:** `generate-all --root ROOT --missing-only`
- **Generate selected units together:** resolve with `list-units`, then use `generate-all --root ROOT --unit UNIT_ID` and repeat `--unit UNIT_ID` for every requested unit; the selected set shares one monitored CSV-wave run
- **Discover unconfigured binary assets:** `list-assets --root ROOT`
- **Register or replace an asset unit:** `configure-asset` with explicit mapping arguments
- **Inspect progress:** `status --root ROOT [RUN_ID]`
- **Stop:** `stop --root ROOT RUN_ID`
- **Resume:** `resume --root ROOT RUN_ID`
- **Repair a failed diagram without regenerating the guide:** `repair-diagrams SOURCE_RUN_ID --root ROOT [--unit UNIT_ID]`
- **Repair prohibited attribution lines in a preserved draft without regenerating the guide:** `repair-attribution SOURCE_RUN_ID --root ROOT [--unit UNIT_ID]`; all flagged lines are rewritten in one structured CSV job and applied atomically while unselected bytes remain unchanged
- **Regenerate selected installed sections or diagrams only:** `repair-sections --root ROOT --unit UNIT_ID [--section HEADING] [--diagram INDEX]`
- **Recover valid sections from a failed targeted run and repair only remaining diagrams:** add `--recover-from-run RUN_ID` with the selected `--section` headings
- **Keep candidates without installing:** add `--candidates-only`
- **Install candidates:** `promote RUN_ID --root ROOT`
- **Install preserved approved candidates from an exhausted checkpoint without touching unresolved units:** `promote RUN_ID --root ROOT --approved-only`
- **Undo installation:** `rollback PROMOTION_ID --root ROOT`
- **Permanently purge one invalid, unpromoted lifecycle:** `purge-run RUN_ID --root ROOT`; use only after the user explicitly identifies the lifecycle as unrecoverable

Use `plan`, `approve`, `run`, or `start` only for advanced lifecycle or budget control.
Use the default concurrency of four unless the user requests an advanced override. Forward an explicit value with `--max-concurrency N`; supported values are one through six.

## D2 diagram contract

Every generated guide must contain at least one content-supporting fenced `d2` diagram. Mermaid is forbidden. Choose diagrams that materially clarify mastery relationships, causal structure, sequence, dependencies, decisions, build order, or debugging.

Keep diagrams readable at normal zoom. Prefer balanced landscape layouts, group long flows into labeled phases, and avoid more than five or six nodes in one uninterrupted lane. Split an overview from detailed flows when one compact diagram cannot preserve legibility. Never rely on scaling a multi-page diagram down until its text becomes unreadable. The supervisor validates the rendered D2 footprint and treats an oversized or excessively wide diagram as a diagram-only repair failure.

If a completed draft fails only diagram validation, preserve the draft and regenerate only the failing diagram. Patch only the targeted fenced block (or convert the targeted Mermaid block); never rerun full guide generation for a diagram-only failure. Use `repair-diagrams` to recover an otherwise complete draft from a prior failed run.

For spreadsheet manuals, require at least one D2 dependency map connecting relevant inputs, columns or ranges, formula families, intermediate calculations, checks, summaries, and decision outputs. Add cross-sheet, build-order, or debugging diagrams when useful. The supervisor validates D2 presence and syntax before approval.

## Exposition and equation pedagogy

Write study-guide content as direct instruction. Do not narrate where a statement came from, repeatedly name an input artifact, or use attribution phrases such as “the PDF,” “the source,” “the transcript,” “the instructor,” or “according to,” including equivalent attribution to a lesson, course, document, guide, author, or speaker. File types and page numbers may appear in structural labels such as a PDF page map, but not as rhetorical attribution. Preserve necessary scope, date, and uncertainty limits as direct statements.

For every nontrivial equation, teach the calculation rather than merely displaying notation:

1. State what the equation measures and why the operations produce that measure.
2. Define every symbol and operator, including index bounds, summation, products, absolute values, exponents, fractions, and square roots.
3. When numerical inputs are available, show `Formula` -> `Constituent breakdown` -> `Substitution` -> `Evaluate the operations` -> `Final result` -> `Interpretation`.
4. When numerical inputs are absent, add a compact neutral worked example whose values are explicitly identified as practice data. Never leave a dense equation such as covariance or correlation without an evaluated walkthrough.

When a page-by-page or section-by-section review repeats the same labels for three or more entries, use a Markdown table with one row per page or page range. Keep prose outside the table only for nuance that cannot be expressed clearly in columns.

For calculation questions, group candidates by normalized solution family before drafting. Candidates share a family when they solve for the same unknown with the same formula and operator sequence after constants, labels, and signs are normalized. Use one standalone question per family by default and never more than two. A second is justified only by a genuinely different reasoning branch, binding constraint, common sign or unit trap, or material decision interpretation. A changed number, direction, or result sign alone is not distinct. Preserve three or more deliberate contrast scenarios as subparts of one question with one shared formula and a compact table. Preserve distinct dependent steps in a chained calculation, but present the chain as one multi-part case study rather than unrelated questions.

## Model settings

Preserve the defaults (`gpt-5.6-sol`, `xhigh` reasoning, high verbosity) unless the user specifies overrides. Forward explicit choices with `--model`, `--reasoning-effort`, and `--verbosity`.

The default per-model-call timeout is 20 minutes. Calibration may raise it as high as 30 minutes; advanced lifecycle commands may explicitly override it within the supported 10–30 minute range.

Global Codex configuration should explicitly set `features.multi_agent = true`, `features.enable_fanout = true`, `agents.max_threads = 6`, `agents.max_depth = 2`, and `agents.job_max_runtime_seconds = 1800`. Select the named `nested-codex` permission profile with `default_permissions`; do not also set `sandbox_mode` or `[sandbox_workspace_write]`. The supervisor also applies the fan-out and Sol V2 routing overrides per dispatcher, and applies any nested full-access exception only to its child invocation.

## Completion reporting

After generation:

1. Verify successful command exit and read final status.
2. Report the run ID and generated/skipped/failed counts.
3. Report every installed canonical path.
4. State when candidates-only mode suppressed installation.
5. On failure, report the exact unit and error while preserving resumable state.

Existing canonical files are archived for rollback during installation.

## Safety invariants

- Treat plans and approvals as immutable after any source, prompt, mapping, target, validator, model, Codex version, or supervisor version change.
- Keep dispatchers and workers in isolated run staging directories; never grant them writable canonical directories. Preserve Codex's per-run job SQLite state without editing its internal tables.
- Stop on authentication, credit, quota, or usage exhaustion.
- Treat ordinary generation as authorization to install successful outputs.
- Preserve retired review prompts under `archive/audit-prompts/`; never inject them into generation.

Consult [CLI-COOKBOOK.md](CLI-COOKBOOK.md) only when the user asks for copy-ready terminal commands.
