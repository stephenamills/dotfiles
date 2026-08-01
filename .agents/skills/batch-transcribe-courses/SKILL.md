---
name: batch-transcribe-courses
description: Recursively transcribe media inside explicit course roots, the immediate course children of author roots, or topic roots containing authors and courses with WhisperKit, writing mirrored .txt files beneath each course root's top-level transcripts directory. Use for course-, author-, or topic-folder transcription, previews, missing transcripts, selective timestamp upgrades, Ω-category exclusion, and resumable batch runs involving audio or video files.
---

# Batch Transcribe Courses

Pass course roots directly to the bundled script:

```bash
python3 ~/.agents/skills/batch-transcribe-courses/scripts/transcribe_courses.py \
  [--author-roots | --topic-roots] [--dry-run | --skip-preflight] \
  [--resume-from COURSE_ROOT] [--limit N] \
  [--overwrite | --overwrite-empty | --upgrade-timestamps] \
  [--language CODE] [--timestamps] [--timestamp-interval SECONDS] \
  [--transcribe-timeout SECONDS] [--transcribe-retries N] \
  [--extract-timeout SECONDS] [--extract-retries N] [--log-file PATH] -- \
  ROOT [ROOT ...]

python3 ~/.agents/skills/batch-transcribe-courses/scripts/transcribe_courses.py \
  --resume STATE [--limit N]

python3 ~/.agents/skills/batch-transcribe-courses/scripts/transcribe_courses.py \
  --retry-failed STATE

fc -ln -1 | python3 \
  ~/.agents/skills/batch-transcribe-courses/scripts/transcribe_courses.py \
  --resume-from-command COURSE_ROOT

python3 ~/.agents/skills/batch-transcribe-courses/scripts/transcribe_courses.py \
  --author-roots --skip-preflight \
  --upgrade-timestamps --timestamp-interval 120 -- \
  AUTHOR_ROOT [...]

python3 ~/.agents/skills/batch-transcribe-courses/scripts/transcribe_courses.py \
  --topic-roots --skip-preflight \
  --upgrade-timestamps --timestamp-interval 120 -- \
  TOPIC_ROOT [...]
```

Without `--author-roots` or `--topic-roots`, treat each argument as one course
root. With `--author-roots`, treat every argument as an author root and use each
immediate child directory as one course root. If an author has no child
directories but contains media directly, promote that author directory to a
flat course root. List only that single directory level; never recursively infer
course boundaries. Preserve author-root argument order and sort the course
roots within each author. Use a separate default-mode invocation for
exceptional course roots that are not beneath an author root.

With `--topic-roots`, expand each supplied root through exactly two directory
levels: immediate author roots, then their immediate course roots. Preserve
topic-root argument order and sort authors within each topic and courses within
each author. Ignore every directory whose normalized name starts with `Ω` and
never descend into it. Apply that exclusion at the topic, author, and all
recursive course-media levels, including after checkpoint resume. Promote a
topic or author directory with no child directories and direct media to a flat
course root. Genuinely empty directories are informational and do not increase
the review issue count; non-media files remain actionable review items.

Do not abort an author- or topic-root run because one supplied root or expanded
author is missing, unreadable, overlapping, or empty. Skip it and continue with
every valid one. Write each exception to a uniquely named
the run's state-directory `.review.txt` file,
print its path immediately, and print its issue count at the end. Also append
course validation and per-course preflight failures encountered during
`--skip-preflight`. Use the report to process exceptional paths manually in a
later explicit-root invocation. If no valid course roots remain, report the
file and exit without starting WhisperKit.

Never pass a broader library or NAS root. Ask for course-, author-, or
topic-root paths if the user has not supplied the appropriate level.

The script recursively maps media within each course:

```text
Course/Module/Lesson.mp4
→ Course/transcripts/Module/Lesson.txt
```

For a course beneath an exact path component named `Music`, the script
discovers video-container extensions only. It ignores audio-only files such as
music, instruments, and samples. Courses outside a `Music` tree retain the
normal audio-and-video discovery behavior.

Use `--dry-run` to preview every mapping. When the user asks to transcribe, run
the live command with the same roots and optional limit, omitting only
`--dry-run`. Keep live output visible and attached.

For a large root list, use `--skip-preflight` to avoid scanning every course
before transcription begins. It validates the supplied root paths once, then
scans and processes one course at a time. In author-root mode it first performs
the one-level directory expansion; in topic-root mode it performs the fixed
two-level expansion. Neither hierarchy expansion scans media recursively. Do
not combine `--skip-preflight` with `--dry-run`.

Every fast-start run atomically writes a local v2 checkpoint beneath
`~/.agents/state/batch-transcribe-courses/` and immediately prints its exact
`--resume STATE` command. The checkpoint stores the expanded ordered course
list, transcription options, the current course cursor, and `failed_courses`.
Advance the cursor only after traversing a whole course. A full cursor with
failures is `complete-with-failures`; use `--retry-failed STATE` to create a
fresh checkpoint containing only those courses. v1 checkpoints load unchanged
and are saved as v2 on their next update. On interruption, resume at that
course; existing transcript files skip completed media within it, and no
earlier course roots are expanded, validated, or scanned. Keep completed
checkpoint files as run records.

For a run started before checkpoint support, add
`--resume-from COURSE_ROOT` to its original `--skip-preflight` invocation.
This performs the author or topic expansion once, starts at that exact expanded
course, and creates the normal checkpoint for subsequent short resumes. If the
full hierarchy command is still the immediately preceding zsh history entry,
pipe `fc -ln -1` to `--resume-from-command COURSE_ROOT` instead. The script
strictly parses that command as argument data and never evaluates or executes
history text. Do not infer progress from shell history or terminal output when
a checkpoint exists.

Existing transcripts are skipped by default. `--overwrite` deliberately selects
them again. The old regular file remains in place while WhisperKit runs; only a
complete, nonempty, written-and-synced `.part` is atomically placed at the
destination. A failed transcription or replacement preserves the old bytes.
Never overwrite symlinks or non-regular paths. The script writes only beneath
each course's `transcripts/` directory and never modifies source media.
Use `--overwrite-empty` to process missing transcripts and replace only
existing transcript files whose size is exactly zero bytes. It skips every
nonempty transcript. If an empty destination becomes nonempty during
transcription, skip the replacement and preserve its new bytes.

Use `--upgrade-timestamps` for a resumable selective migration. It implies
`--timestamps` and processes missing transcripts plus existing regular files
that are empty, whitespace-only, plain text without a valid leading timestamp
marker, or contain legacy `<|...|>` Whisper control tokens. It skips clean
periodic `[HH:MM:SS]` transcripts and exact-segment
`[HH:MM:SS.mmm --> HH:MM:SS.mmm]` transcripts. Any clean timestamp interval
counts as upgraded; use ordinary `--overwrite --timestamps` to deliberately
change an existing interval. The mode is mutually exclusive with
`--overwrite` and `--overwrite-empty`.

During a timestamp upgrade, keep the old transcript until a complete nonempty
timestamped `.part` is written and synced. Compare the existing file with its
per-course preflight snapshot before atomic replacement. If another process
changes it, preserve the concurrent update and skip replacement. A resumed
current course rescans its transcript destinations, so files already upgraded
before interruption are skipped.

Without `--overwrite`, APFS/HFS+ installation is an exclusive atomic rename; on
SMB it uses exclusive destination creation without overwriting an existing
path. An abrupt SMB interruption can leave a partial destination that must be
reviewed manually.

WhisperKit uses `large-v3-v20240930_turbo`, VAD, the M5 Pro compute settings,
and 64 workers. Always suppress Whisper control, language, task, and timestamp
tokens from transcript text. The task is always native-language transcription,
never translation. With the default language setting, infer these exact
recognized trees independently for each course:
`Language/Chinese (Cantonese)` → `yue`, `Language/French` → `fr`,
`Language/Greek` → `el`, `Language/Latin` → `la`, `Language/Russian` → `ru`,
`Language/Spanish` → `es`, and `Language/Thai` → `th`. Other paths default to
English. Use `--language CODE` to override the path inference for the whole
invocation, or `--language auto` for WhisperKit detection.

`--timestamps` preserves the complete transcription and groups text beneath
seek markers every 120 seconds by default. Change the interval with
`--timestamp-interval SECONDS`; use `0` for every WhisperKit segment with exact
start/end times. Prefer 120 seconds for study-guide source navigation and 60
seconds when finer lookup matters. WhisperKit clip ranges are not periodic
markers: they restrict transcription to selected spans and omit everything
outside them. Video and uncommon audio containers are converted through ffmpeg
first.

Live runs invoke `whisperkit-cli transcribe` directly once per selected file.
The child starts in its own process group. By default, a child that has not
finished after 600 seconds is terminated and the file is retried once. Change
those bounds with `--transcribe-timeout SECONDS` and `--transcribe-retries N`.
A failed, timed-out, or empty result is never installed; after its retries it
is reported as `FAIL`, and the batch proceeds to the next file. Keep live
output visible and attached. ffmpeg conversion remains a per-file subprocess
where required, uses an independent size-aware timeout (override with
`--extract-timeout`), retries with a corrupt-frame-tolerant mono downmix, and
defaults to one extraction retry (`--extract-retries N`). A vanished `/Volumes`
mount is probed with `statvfs` plus `scandir`, waited on with bounded backoff,
and never advances the checkpoint cursor until the course can be retried.

Each run writes one consolidated flushed log at
`~/.agents/state/batch-transcribe-courses/logs/run-*.log` (or `--log-file PATH`)
and its actionable companion `run-*.review.txt`. The log includes invocation,
resolved dependencies, every scan/success/skip/failure/retry/timeout/volume
event, course summaries, totals, exit reason, and resume/retry commands.
