---
name: batch-study-guide-powerbi
description: Generate transcript-grounded Power BI study guides from local Maven Analytics course folders. Use for listing, generating, resuming missing guides, checking status, or generating selected Power BI topics.
---
# Power BI batch generation

Run `scripts/run.py` on the user’s behalf. The default configuration names the three Maven Analytics Power BI course directories; repeat `--root` to override them with either a course directory or its `transcripts/` directory.

The runner groups every immediate transcript topic folder into one unit, concatenates `.txt` files in natural filename order, and installs one Markdown file in the course sibling `study guides/` directory. Unit IDs include course and topic slugs, so duplicate topic names cannot collide. Use `list-units`, `generate-all`, and `status`; “resume” means `generate-all --missing-only`. `--unit` may be repeated. Preserve `--concurrency`, model, reasoning, verbosity, timeout, `--json`, and `--dry-run` flags.

Each selected topic invokes one isolated `codex exec` process, with at most six concurrent workers. A successful process must return a non-empty final response; there are no quality gates, retries, repair passes, or regeneration loops. Failures are recorded and remaining topics continue; the batch exits 1 if any unit fails. Existing guides are archived under the run state directory before atomic replacement. Ctrl-C terminates active children and leaves completed files installed.

The bundled [depth contract](references/depth-contract.md) adapts the finance skill’s successful instructional standard without coupling this skill to the finance runner.

Per-course state is stored under `.study-guide-powerbi/` with run IDs, unit statuses, source files, errors, and canonical output paths. Dry runs only discover and report units and do not invoke Codex or write state.
