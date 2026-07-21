# Study-Guide Batch CLI Cookbook

Use this reference only when copy-ready terminal commands are requested. Replace `ROOT` with the course root and `SCRIPT` with the installed skill script.

```bash
SCRIPT="$HOME/.agents/skills/study-guide-batch/scripts/study_guide_batch.py"
ROOT="/path/to/course"
```

## Discover and configure units

```bash
python3 "$SCRIPT" list-units --root "$ROOT"
python3 "$SCRIPT" list-units --root "$ROOT" --missing-only
python3 "$SCRIPT" list-assets --root "$ROOT"
```

Register or replace one PDF unit:

```bash
python3 "$SCRIPT" configure-asset \
  --root "$ROOT" \
  --kind pdf \
  --id statistics-reference \
  --title "Statistics Reference" \
  --source "course-assets/statistics.pdf" \
  --transcript "transcripts/02 Statistics.txt" \
  --output "study-guides/statistics-reference.md" \
  --prompt "prompts/pdf-companion.md"
```

For a workbook family, repeat `--source` for each explicitly related workbook and use `--kind spreadsheet`. Repeat `--transcript` to preserve lesson order. Omit `--prompt` to use the configured kind prompt or bundled default.

## Generate

```bash
python3 "$SCRIPT" generate-all --root "$ROOT"
python3 "$SCRIPT" generate-all --root "$ROOT" --missing-only
python3 "$SCRIPT" generate-all --root "$ROOT" --unit UNIT_ID
python3 "$SCRIPT" generate-all --root "$ROOT" --candidates-only
python3 "$SCRIPT" generate-all --root "$ROOT" --max-concurrency 4
```

Override model settings:

```bash
python3 "$SCRIPT" generate-all \
  --root "$ROOT" \
  --model gpt-5.6-sol \
  --reasoning-effort xhigh \
  --verbosity high
```

Preview without model calls:

```bash
python3 "$SCRIPT" plan --root "$ROOT"
```

## Monitor and recover

```bash
python3 "$SCRIPT" status RUN_ID --root "$ROOT"
python3 "$SCRIPT" stop RUN_ID --root "$ROOT"
python3 "$SCRIPT" resume RUN_ID --root "$ROOT"
python3 "$SCRIPT" promote RUN_ID --root "$ROOT"
python3 "$SCRIPT" rollback PROMOTION_ID --root "$ROOT"
```

Permanently purge one user-designated invalid lifecycle only after it has no live owner and was never promoted:

```bash
python3 "$SCRIPT" purge-run RUN_ID --root "$ROOT"
```

## Advanced lifecycle

```bash
python3 "$SCRIPT" plan --root "$ROOT"
python3 "$SCRIPT" approve PLAN_ID --root "$ROOT"
python3 "$SCRIPT" approve PLAN_ID --root "$ROOT" --max-concurrency 4
python3 "$SCRIPT" run APPROVAL_ID --root "$ROOT"
python3 "$SCRIPT" start APPROVAL_ID --detach --root "$ROOT"
```

The supervisor defaults to Codex CSV waves of four workers. `--max-concurrency` accepts one through six. Every generated guide must contain valid D2 and no Mermaid.
