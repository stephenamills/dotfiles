---
name: batch-study-guide-finance
description: Generate and manage finance-focused Markdown study guides, quantitative asset companions, workbook manuals, in-depth topic course maps, and whole-course maps from local transcripts, PDFs, and Microsoft Excel workbooks through deterministic validation, Codex Multi Agent V2 guide waves, and direct concurrent map synthesis. Use for finance, trading, economics, accounting, investment, risk, valuation, markets, and related quantitative courses when Codex must generate all or missing guides, install each validated file immediately, synthesize maps, regenerate one lesson or asset companion, configure PDF or spreadsheet units, resolve unit IDs, inspect status, stop or resume runs, promote candidates, or roll back installed guides. Invoke the bundled supervisor on the user's behalf; do not require the user to operate its CLI.
---

# Batch Study Guide — Finance

Act as the TUI controller for the bundled supervisor. Translate natural-language requests into supervisor operations, execute them, monitor long runs, and report exact canonical paths. Keep the Python CLI internal unless the user requests commands.

## Execution contract

- Resolve `scripts/study_guide_batch.py` relative to this file.
- Use the supervisor for configuration, planning, generation, installation, recovery, and rollback. Never edit its SQLite state.
- Let the supervisor launch fresh depth-0 Codex dispatchers with `--enable multi_agent_v2` for transcript, PDF, and workbook guide waves. It uses one leaf `spawn_agent` call per isolated task and waits for every child to reach a terminal state. Independent topic maps use direct concurrent Codex invocations after their guide dependencies are approved; the whole-course map runs only after its topic maps are approved. Course configuration controls both paths (six workers by default). V2 leaf workers never spawn agents.
- Let nested Codex processes load user configuration and do not pass the legacy `--sandbox` mode. On Codex 0.144, if the user configuration still declares legacy `agents.max_threads`, the supervisor uses `--ignore-user-config` for that isolated dispatcher because V2 otherwise refuses to start; authentication still uses `CODEX_HOME` and all required V2 settings are passed explicitly. When the supervisor itself runs inside a Codex sandbox, it gives the nested child session a `:danger-full-access` override so macOS does not apply a second Seatbelt sandbox; the parent TUI remains the enforcement boundary. This affects nested Codex only, not the direct opt-in `mmdc` renderer. Never set this override globally.
- Do not bypass, replace, or manually imitate either supervisor execution path. If V2 is unavailable for guide waves, report the explicit failure and preserve resumable state.
- Run long foreground commands in a persistent terminal session and poll until completion. Relay concise progress.
- Do not add calibration or broad post-hoc auditing unless explicitly requested. The built-in semantic audit of deterministic text repair is mandatory and is not an optional review phase.
- Infer `--root` from an explicit path or unambiguous course folder.
- Resolve user-facing lesson numbers, titles, and filenames yourself; never ask the user to supply a unit ID.

### Lifecycle continuity (mandatory)

- When the user asks to finish, resume, continue, or retry an existing batch, inspect `status` and resume that exact `RUN_ID` first. Do not create a replacement plan, approval, or run merely to change the model, concurrency, or selection.
- Treat a stopped, failed, or exhausted lifecycle as the source of truth for what remains. Preserve its immutable plan, approval, attempts, and candidates; use `resume`, `install-previews`, `promote --approved-only`, `repair-diagrams`, `repair-attribution`, or `repair-sections` as appropriate. A failed ownerless run may finalize only its approved units; legacy or candidates-only runs require explicit preview installation first.
- Never launch a new full-plan run when the request names a subset or when completed canonical outputs already exist. If a new lifecycle is genuinely required, first explain why the original cannot be resumed and construct a plan whose `unit_overrides.exclude` removes every completed or out-of-scope unit before approval.
- Never silently regenerate completed guides from scratch. A fresh plan is allowed only after explicit user authorization or when no resumable lifecycle exists; report the exact reason and the affected unit scope before starting it.
- Individual model calls have no shorter timeout. Only the immutable global run deadline can stop active work; progress heartbeats, named wave rosters, and bounded retries provide liveness without killing a healthy long call.

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
- **Generate selected units together:** resolve with `list-units`, then use `generate-all --root ROOT --unit UNIT_ID` and repeat `--unit UNIT_ID` for every requested unit; the selected set shares one monitored V2-wave run
- **Discover unconfigured binary assets:** `list-assets --root ROOT`
- **Register or replace an asset unit:** `configure-asset` with explicit mapping arguments
- **Inspect progress:** `status --root ROOT [RUN_ID]`
- **Stop:** `stop --root ROOT RUN_ID`
- **Resume:** `resume --root ROOT RUN_ID`
- **Repair a failed diagram without regenerating the guide:** `repair-diagrams SOURCE_RUN_ID --root ROOT [--unit UNIT_ID]`
- **Repair prohibited attribution lines in a preserved draft without regenerating the guide:** `repair-attribution SOURCE_RUN_ID --root ROOT [--unit UNIT_ID]`; safe wrappers are removed deterministically, the exact diff receives a semantic LLM audit, and rejected or ambiguous changes fall back to one scoped structured repair while unselected bytes remain unchanged
- **Regenerate selected installed sections or diagrams only:** `repair-sections --root ROOT --unit UNIT_ID [--section HEADING] [--diagram INDEX]`
- **Recover valid sections from a failed targeted run and repair only remaining diagrams:** add `--recover-from-run RUN_ID` with the selected `--section` headings
- **Keep candidates without installing:** add `--candidates-only`
- **Expose approved files from an older active run:** `install-previews RUN_ID --root ROOT`
- **Finalize installation and rollback journals:** `promote RUN_ID --root ROOT`
- **Install preserved approved candidates from an exhausted checkpoint without touching unresolved units:** `promote RUN_ID --root ROOT --approved-only`
- **Undo installation:** `rollback PROMOTION_ID --root ROOT`
- **Permanently purge one invalid, unpromoted lifecycle:** `purge-run RUN_ID --root ROOT`; use only after the user explicitly identifies the lifecycle as unrecoverable

Use `plan`, `approve`, `run`, or `start` only for advanced lifecycle or budget control.
Use `max_concurrency` in `study-guide-batch.json` as the course default. Forward `--max-concurrency N` only as a one-run override; supported values are one through 32.

Course maps are first-class units and are enabled by default. The supervisor groups planned guide targets by their parent topic folder under `output_root`, generates guide units first, generates independent topic maps concurrently from approved guide candidates, and finally generates one whole-course map using only approved topic-map candidates. Topic and whole-course maps have separate exact 13-section contracts. Whole-course source staging retains every numbered section while compacting each topic map to a bounded paragraph-preserving excerpt. Selecting a guide also selects its topic map and the whole-course map. Use `course_maps.enabled: false` only when the user explicitly opts out of all maps; use `course_maps.whole_course.enabled: false` only when the user explicitly opts out of the final synthesis. Read [references/configuration.md](references/configuration.md) for topic discovery, output naming, prompt overrides, and dependency behavior.

## Mermaid diagram contract

Every generated guide must contain at least one content-supporting fenced `mermaid` diagram. D2 fences are unconditionally invalid. Each diagram must be a compact visual explanation, not a decorative restatement: show the governing question, inputs, transformations or decisions, outputs, dependencies, cautions, and feedback where applicable.

Choose the diagram type that matches the relationship:

- Use `mindmap` for course architecture and conceptual hierarchy.
- Use `flowchart` for learning paths, calculations, workbook dependencies, build order, and decisions.

Keep labels concise, use branching and multiple relationship layers, and split distinct mechanisms into separate diagrams instead of forcing them into one oversized lane. The supervisor validates syntax through the installed Mermaid 11.14 parser. `validate_mermaid_render` is disabled by default; if explicitly enabled, it also renders through `mmdc` at the 1728×1117 CSS-pixel viewport of a 16-inch MacBook and requires responsive SVG `viewBox` output. Mermaid produces vector SVG, so Retina pixel density does not require a separate high-resolution render.

If a completed draft fails only diagram validation, preserve the draft and regenerate only the failing Mermaid block. Patch only that fenced block; never rerun full guide generation for a diagram-only failure. Use `repair-diagrams` to recover an otherwise complete draft from a prior failed run. `repair-sections --diagram` uses one-based Mermaid-fence indexes.

For spreadsheet manuals, require at least one Mermaid flowchart connecting relevant inputs, columns or ranges, formula families, intermediate calculations, checks, summaries, and decision outputs. Add cross-sheet, build-order, or debugging flowcharts when useful.

## Exposition and equation pedagogy

Write study-guide content as direct instruction. Do not narrate where a statement came from, repeatedly name an input artifact, or use attribution phrases such as “the PDF,” “the source,” “the transcript,” “the instructor,” or “according to,” including equivalent attribution to a lesson, course, document, guide, author, or speaker. File types and page numbers may appear in structural labels such as a PDF page map, but not as rhetorical attribution. Preserve necessary scope, date, and uncertainty limits as direct statements.

For every nontrivial equation, teach the calculation rather than merely displaying notation:

1. State what the equation measures and why the operations produce that measure.
2. Define every symbol and operator, including index bounds, summation, products, absolute values, exponents, fractions, and square roots.
3. When numerical inputs are available, show `Formula` -> `Constituent breakdown` -> `Substitution` -> `Evaluate the operations` -> `Final result` -> `Interpretation`.
4. When numerical inputs are absent, add a compact neutral worked example whose values are explicitly identified as practice data. Never leave a dense equation such as covariance or correlation without an evaluated walkthrough.

When a page-by-page or section-by-section review repeats the same labels for three or more entries, use a Markdown table with one row per page or page range. Keep prose outside the table only for nuance that cannot be expressed clearly in columns.

### Heading hierarchy

Number every H2 major section sequentially with Arabic numerals, such as `## 1. Market Structure` and `## 2. Quantitative Framework`. H2 numbering exposes the document’s major conceptual route and gives the learner stable navigation landmarks.

Keep H3 headings descriptive and unnumbered in ordinary exposition. Avoid nested numbering merely because a heading is subordinate; repeated numeric prefixes create visual noise and make long technical guides harder to scan. Number H3 headings only when the headings themselves enumerate work the learner should complete or check in order, including questions, exercises, calculation problems, drills, cases, applications, assessments, or checklist steps. Use the same principle for equivalent active-learning sequences even when their label differs.

The supervisor strips decorative numeric prefixes from ordinary H3 headings deterministically before validation while preserving numbered learner-work headings. It never changes H2 numbering mechanically.

For calculation questions, group candidates by normalized solution family before drafting. Candidates share a family when they solve for the same unknown with the same formula and operator sequence after constants, labels, and signs are normalized. Use one standalone question per family by default and never more than two. A second is justified only by a genuinely different reasoning branch, binding constraint, common sign or unit trap, or material decision interpretation. A changed number, direction, or result sign alone is not distinct. Preserve three or more deliberate contrast scenarios as subparts of one question with one shared formula and a compact table. Preserve distinct dependent steps in a chained calculation, but present the chain as one multi-part case study rather than unrelated questions.

## Depth interpretation

Where the prompts license synthesis, consolidation, or conciseness, those clauses eliminate only genuine verbatim duplication — never depth, coverage, or granularity. When weighing whether to expand or condense a source item, expand. Dense prose within a section is the preferred style; do not split material into additional subsections merely to manufacture structure.

- Create one question per distinct learning objective from every major section. Apply the family-consolidation rules above only to genuinely identical solution families, never to reduce coverage.
- After drafting, verify every item in the pre-drafting coverage inventory received full expansion — a mention is not coverage — and expand any gaps before completing the guide.
- Brevity is not a virtue in these deliverables. Treat any impulse to summarize, tighten, or keep a guide focused as a violation unless the material is literally duplicated.

## In-depth course map contract

A topic course map is a teaching synthesis derived from the complete set of study guides for that topic. The final whole-course map is a higher-order teaching synthesis derived only from the complete set of topic course maps, never directly from transcripts, PDFs, workbooks, or study guides. Neither kind is a short directory, link list, reading checklist, or collection of one-paragraph summaries. Let the supervisor generate topic maps directly and concurrently from approved guide candidates in the second dependency phase, then generate the whole-course map from approved topic-map candidates in the third phase of the same run. Installed dependencies are used when a map is selected independently.

Require the exact ordered 13-section structures bundled separately for topic and whole-course maps. Reject missing, renamed, reordered, or extra H2 sections, fewer than two substantive Mermaid diagrams, or a missing direct-dependency link.

Use established in-depth course maps in adjacent courses as structural references when available. Preserve the subject matter and terminology of the mapped chapters; do not copy unrelated content from an exemplar. Each topic map must fully develop:

1. **Section thesis and learning outcomes:** state the unifying problem, the intellectual progression, and observable end-state capabilities.
2. **Ordered chapter path:** link every corresponding study chapter with correct relative Markdown links and explain why each chapter precedes or prepares the next.
3. **Architecture and dependencies:** derive how concepts, inputs, calculations, decisions, and feedback loops connect across chapters. Include at least one substantive Mermaid architecture diagram.
4. **Chapter-by-chapter learning and mastery:** use a detailed table covering every chapter, its role, core learning, dependencies, practical application, and observable mastery evidence.
5. **Integrated conceptual derivation:** reteach the topic across chapter boundaries. Fully expand mechanisms, causal chains, distinctions, assumptions, and interactions; do not merely mention them.
6. **Equations and quantitative reasoning:** include every important formula needed to connect the topic. Define all symbols and operators and provide worked numerical examples under the exposition-and-equation contract whenever calculation is part of the material.
7. **Operating workflow and decision gates:** turn the topic into a repeatable process with inputs, transformations, checks, actions, cautions, and recalculation or review triggers. Include a Mermaid flowchart or state diagram when it materially clarifies the process.
8. **Cross-chapter synthesis:** show how conclusions change when multiple concepts interact, including conflicts, conditional branches, and trade-offs.
9. **Misconceptions and failure modes:** diagnose plausible errors, explain why they fail, and state the corrective reasoning or control.
10. **Cumulative application:** provide at least one integrated case, analysis sequence, build, or decision exercise that requires several chapters together.
11. **Mastery and review system:** include an observable mastery checklist, retrieval questions with answers or answer guidance, and a spaced review plan that revisits dependencies rather than rereading passively.

Depth must scale with the chapter set. A one-chapter topic can still require a substantial course map when that chapter is broad; a many-chapter topic requires proportionally broader integration and explicit coverage of every chapter. Word count is informational rather than a target, but a map that can be mistaken for an index has failed the contract. Before completion, inventory the major learning objectives in every mapped chapter and confirm that each received full instructional treatment somewhere in the map.

Keep course-map prose in direct instructional voice and apply the same attribution, Mermaid, equation, coverage, and anti-concision rules used for study guides. Verify every local link. Report course-map paths and informational depth metrics alongside guide outputs when maps are part of the request.

## Model settings

Preserve the defaults (`gpt-5.6-sol`, `xhigh` reasoning, high verbosity) unless the user specifies overrides. Forward explicit choices with `--model`, `--reasoning-effort`, and `--verbosity`.

Do not impose a per-model-call timeout. The immutable global run deadline is the only wall-clock ceiling, and an interrupted deadline checkpoint remains resumable.

Global Codex configuration may set `features.multi_agent_v2.max_concurrent_threads_per_session = 7` and `features.multi_agent_v2.tool_namespace = "agents"`. The supervisor enables V2 per dispatcher with `--enable multi_agent_v2`, which is compatible with the installed 0.144 CLI family. If that version inherits `agents.max_threads`, it isolates only the dispatcher from user configuration because V2 otherwise rejects startup. The session limit includes the dispatcher, so use worker concurrency plus one. Select the named `nested-codex` permission profile with `default_permissions`; do not also set `sandbox_mode` or `[sandbox_workspace_write]`. The supervisor applies V2 and routing overrides per dispatcher, and applies any nested full-access exception only to its child invocation.

## Completion reporting

After generation:

1. Verify successful command exit and read final status.
2. Report the run ID and generated/skipped/failed counts.
3. Report every installed canonical path, including files installed before the overall run finished.
4. Report informational depth metrics for every generated guide — word count, rendered line count, H3 subsection count, display-math block count (lines beginning `$$`), and question count — for cross-run comparison. These are measurements only, never targets, floors, or pass/fail gates, and must not be fed back into generation.
5. State when candidates-only mode suppressed installation.
6. On failure, report the exact unit and error while preserving resumable state.

Every deterministically validated file is copied to its canonical path immediately while its candidate remains intact. If a canonical file already existed, preserve its original bytes under the run’s `preview-originals` area. Final promotion turns those originals into the rollback archive and reconciles the retained candidates without regenerating content. `--candidates-only` is the sole ordinary-generation opt-out.

## Safety invariants

- Treat plans and approvals as immutable after any source, prompt, mapping, target, validator, model, Codex version, or supervisor version change.
- Keep dispatchers and workers in isolated run staging directories; never grant them writable canonical directories. Preserve Codex's per-run job SQLite state without editing its internal tables.
- Stop on authentication, credit, quota, or usage exhaustion.
- Treat ordinary generation as authorization to install each successful output immediately, regardless of whether it is a transcript guide, PDF companion, workbook manual, topic map, or whole-course map.
- Preserve retired review prompts under `archive/audit-prompts/`; never inject them into generation.

Consult [CLI-COOKBOOK.md](CLI-COOKBOOK.md) only when the user asks for copy-ready terminal commands.
