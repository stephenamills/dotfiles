---
name: batch-study-guide-language
description: Generate language study guides from local source files with one-pass Codex workers.
---
# Execution
Resolve and run `scripts/run.py` relative to this file. The runner stages waves and installs artifacts immediately. Use a persistent terminal for long runs.

A unit is one discovered source file. There are no quality gates: one attempt, installed as-is, failures reported without retries. Regenerate with `--unit` or edit the prompt; never add validation loops.

Requests map to `generate-all`, `--missing-only`, `--unit`, `list-units`, and `status`; “resume” means `--missing-only`. Pass the source folder as `--root`. `pdftotext` is required for PDFs and `openpyxl` for workbooks.
