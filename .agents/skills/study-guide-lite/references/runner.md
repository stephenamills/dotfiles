# Study Guide Lite Runner

Each domain wrapper resolves this runner from `STUDY_GUIDE_LITE_RUNNER`, the sibling `.agents/skills` directory, or `~/.agents/skills`. Roots are supplied at invocation. `list-units` discovers one source file per unit; `generate-all` stages isolated wave tasks and installs non-empty artifacts immediately; `status` reads `.study-guide-lite/runs.json`. Existing targets are archived before overwrite. A missing artifact is a failure and is never retried.

Staging uses `dispatch/<run>/wave-NNN/tasks/NN-id/{input.md,artifact.md,sources/}` and `tasks.json`. Dry runs create this layout without invoking Codex.
