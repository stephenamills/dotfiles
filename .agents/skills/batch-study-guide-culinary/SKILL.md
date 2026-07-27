---
name: batch-study-guide-culinary
description: Generate and manage transcript-grounded culinary study chapters, in-depth topic maps, and whole-course maps through deterministic Codex Multi Agent V2 waves. Use for cooking-school, culinary-technique, ingredient, kitchen-tool, food-preparation, and service courses when Codex must plan all or missing chapters, synthesize maps, regenerate selected lessons, resolve unit IDs, inspect status, stop or resume runs, perform targeted repairs, promote candidates, or roll back installed guides. Invoke the bundled transcript-only supervisor on the user's behalf.
---

# Batch Study Guide — Culinary

Act as the controller for `scripts/study_guide_batch.py`. Translate natural-language requests into
supervisor operations, execute them, monitor long runs, and report canonical paths. Keep CLI details
internal unless requested.

## Execution

- Use the supervisor for planning, generation, validation, recovery, promotion, and rollback.
- Never edit its SQLite state or imitate its Multi Agent V2 dispatcher.
- Preserve defaults: `gpt-5.6-sol`, `xhigh`, high verbosity, and six leaves unless the course
  configuration explicitly sets another concurrency. Individual calls have no shorter timeout;
  the immutable run deadline is the only wall-clock stop.
- Run long work in a persistent terminal and relay concise progress.
- Infer the course root from an explicit or unambiguous folder and resolve user-facing lesson names
  through `list-units`; never ask for a unit ID.
- Keep sources transcript-only. Reject PDF, spreadsheet, workbook, and generic asset pathways.
- Read [references/configuration.md](references/configuration.md) before configuring a course.

## Lifecycle continuity

For finish, continue, resume, or retry requests, inspect `status` and resume the exact existing run
first. Preserve immutable plans, approvals, attempts, and candidates. Do not replace a lifecycle to
change timeout, model, concurrency, or selection. Never silently regenerate installed chapters.
Promote approved candidates from an exhausted run with `promote --approved-only` when applicable.

Progress heartbeats and bounded retries provide liveness visibility; retries, repairs, and three
dependency phases can make a run long, but an individual call is not terminated by a shorter timer.

## Natural-language routing

- Generate configured work: `generate-all --root ROOT`
- Generate absent targets: add `--missing-only`
- Generate selected units: resolve with `list-units`, then repeat `--unit UNIT_ID`
- Preview without model calls: `plan --root ROOT`
- Inspect: `status --root ROOT [RUN_ID]`
- Stop or resume: `stop --root ROOT RUN_ID`; `resume --root ROOT RUN_ID`
- Repair: `repair-diagrams`, `repair-attribution`, or `repair-sections`
- Keep candidates uninstalled: add `--candidates-only`
- Install: `promote RUN_ID --root ROOT`
- Undo: `rollback PROMOTION_ID --root ROOT`

Use `approve`, `run`, and `start` only for advanced immutable lifecycle control. Treat ordinary
generation as authorization to install validated output. Never start generation when the user asks
only for planning.

## Culinary grounding

Ground each chapter exclusively in its ordered transcripts. Prohibit browsing, external facts,
invented recipes, and unsupported safety or temperature rules. Silently repair only unambiguous
transcription artifacts while preserving culinary terms, qualifications, measurements, and sequence.

Teach through every applicable dimension: purpose, mise en place, tools, ingredients, preparation,
physical technique, transformations, heat/moisture/fat control, timing, sensory cues, decision points,
doneness, troubleshooting, recovery, holding, storage, service, and practice. Preserve exact
measurements, ratios, times, and temperatures; explain function or scaling only when supported.
Prefer plain Markdown over unnecessary KaTeX.

Require a substantive Mermaid workflow, decision, or state diagram. Never diagram exact knife or
hand positioning. Number H2 headings sequentially. Keep ordinary H3 headings unnumbered; number them
only for exercises, drills, questions, applications, assessments, or checklist steps. End chapters
with practical mastery checks and answered retrieval or scenarios centered on observable cues and
corrective decisions. Decorative numeric prefixes on ordinary H3 headings are normalized
deterministically before validation, so they do not trigger a costly model retry.

When `lesson_catalog.enabled` is configured, require every transcript chapter to preserve all
ordered readable lesson names in its `Original Video Lessons` section with transcript-grounded
watch-for cues. Treat names as navigation metadata only: do not read, link, or validate media files.

## Course maps

Generate chapters first, topic maps second, and the complete-course map third. Topic maps use only
approved chapter candidates; the complete-course map uses only approved topic-map candidates. Every
map links every direct dependency, uses its bundled exact 13-section structure, and contains at least
two substantive Mermaid diagrams.

When configured, topic maps repeat every chapter's ordered lesson names under `Ordered Chapter Path`.
The complete-course map repeats them only when `lesson_catalog.whole_course` is enabled.

Do not accept a map that is merely an index or summaries. Require technique architecture, dependency
teaching, ingredient/tool/mise-en-place integration, culinary transformations, sensory decision
gates, timing and service, troubleshooting and recovery, cumulative kitchen application, observable
mastery, answered retrieval, and spaced practice.

## Completion

Verify the final status and report the run ID, generated/skipped/failed counts, every installed path,
and informational depth metrics. State when candidates-only mode prevented installation. On failure,
report the exact unit and error while preserving resumable state. Existing targets are archived for
rollback during atomic promotion.
