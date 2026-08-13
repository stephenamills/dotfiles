# transcribe-courses

Recursively transcribe media inside course roots, author roots, or topic roots
with one persistent WhisperKit worker. Mirrored text files are written beneath
each course root's top-level `transcripts` directory.

```bash
transcribe-courses \
  [--author-roots | --topic-roots] [--dry-run | --scan | --skip-preflight] \
  [--resume-from COURSE_ROOT] [--limit N] \
  [--overwrite | --overwrite-empty | --upgrade-timestamps] \
  [--language CODE] [--timestamps] [--timestamp-interval SECONDS] \
  [--transcribe-retries N] \
  [--extract-timeout SECONDS] [--extract-retries N] [--log-file PATH] -- \
  ROOT [ROOT ...]

transcribe-courses --resume STATE [--limit N]

transcribe-courses --retry-failed STATE

fc -ln -1 | transcribe-courses \
  --resume-from-command COURSE_ROOT

transcribe-courses \
  --author-roots \
  --upgrade-timestamps --timestamp-interval 120 -- \
  AUTHOR_ROOT [...]

transcribe-courses \
  --topic-roots \
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
every valid one. Write each exception to a uniquely named `.review.txt` file in
the run's state directory,
print its path immediately, and print its issue count at the end. Also append
course validation and streaming course failures encountered during the run.
Streaming output collisions are recorded there as `OUTPUT COLLISION` entries;
the colliding item is skipped while the rest of the course continues. Use the
report to process exceptional paths manually in a
later explicit-root invocation. If no valid course roots remain, report the
file and exit without starting WhisperKit.

Never pass a broader library or NAS root. Ask for course-, author-, or
topic-root paths if the user has not supplied the appropriate level.

The script recursively maps media within each course:

```text
Course/Module/Lesson.mp4
→ Course/transcripts/Module/Lesson.txt
```

Because `.ts` is shared by MPEG transport-stream video and TypeScript source,
discovery accepts that suffix only when the file contains the repeated MPEG
packet-sync signature. This check applies to streaming, scan/dry-run, and
author/topic flat-course promotion; ordinary `.ts` source files are ignored.

For a course beneath an exact path component named `Music`, the script
discovers video-container extensions only. It ignores audio-only files such as
music, instruments, and samples. Courses outside a `Music` tree retain the
normal audio-and-video discovery behavior.

WAV files (`.wav`) are ignored in every course tree because bundled game and UI
sound effects are not useful transcription inputs.

Use `--dry-run` to preview every mapping. When the user asks to transcribe, run
the live command with the same roots and optional limit, omitting only
`--dry-run`. Keep live output visible and attached.

Live runs stream by default: each course is walked and transcribed in one pass,
so the first eligible file can start before the rest of the course has been
enumerated. Use `--scan` to opt into the complete per-course preflight used by
older runs, including accurate discovered/ready/limited counts and fail-closed
collision detection. `--dry-run` implies the scan path and prints every
mapping without writing. `--skip-preflight` remains accepted for compatibility
but is a deprecated no-op; it prints a warning and keeps streaming enabled.
Streaming item progress intentionally has no denominator (for example,
`[Season 4 3] TRANSCRIBE`); the course header retains the real batch position.
In author-root mode the one-level directory expansion still happens first; in
topic-root mode the fixed two-level expansion still happens first. Neither
hierarchy expansion scans media recursively.

Every fast-start run atomically writes a local v4 checkpoint beneath
`~/.agents/state/batch-transcribe-courses/` and immediately prints its exact
`--resume STATE` command. The checkpoint stores the expanded ordered course
list, the transcription options, the current course cursor, and
`failed_courses`.
Advance the cursor only after traversing a whole course. A full cursor with
failures is `complete-with-failures`; use `--retry-failed STATE` to create a
fresh checkpoint containing only those courses. On interruption, resume at that
course; existing transcript files skip completed media within it, and no
earlier course roots are expanded, validated, or scanned. Keep completed
checkpoint files as run records. v1, v2, and v3 checkpoints all load and
migrate to v4. The retired v3 `engine` field is dropped on migration: both
`whisperkit` and `parakeet` now mean the same persistent WhisperKit worker, and
any other value fails loudly rather than being reinterpreted.

Migration is deliberately gated on the worker. A resumed run builds the worker
if needed and loads its model before the checkpoint is rewritten, and a new run
does the same before any checkpoint is created. If the build, the Argmax
checkout verification, the model validation, or the model load fails, an
existing checkpoint remains byte-for-byte unchanged and a new run creates no
checkpoint. There is no fallback to `whisperkit-cli` or any other engine.

For a run started before checkpoint support, add
`--resume-from COURSE_ROOT` to its original invocation (with or without the
now-deprecated `--skip-preflight` flag).
This performs the author or topic expansion once, starts at that exact expanded
course, and creates the normal checkpoint for subsequent short resumes. If the
full hierarchy command is still the immediately preceding zsh history entry,
pipe `fc -ln -1` to `--resume-from-command COURSE_ROOT` instead. The script
strictly parses that command as argument data and never evaluates or executes
history text. Do not infer progress from shell history or terminal output when
a checkpoint exists.

Existing transcripts are skipped by default. `--overwrite` deliberately selects
them again. The old regular file remains in place while the selected engine runs; only a
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
timestamped `.part` is written and synced. Read and compare the existing file
snapshot immediately before considering that one replacement. If another
process changes it, preserve the concurrent update and skip replacement. A
resumed current course rescans its transcript destinations, so files already
upgraded before interruption are skipped.

Without `--overwrite`, APFS/HFS+ installation is an exclusive atomic rename; on
SMB it uses exclusive destination creation without overwriting an existing
path. An abrupt SMB interruption can leave a partial destination that must be
reviewed manually.

Transcription uses `large-v3-v20240930_turbo`, VAD, the M5 Pro compute
settings, and 16 workers. Always suppress Whisper control, language, task, and
timestamp tokens from transcript text. The task is always native-language
transcription, never translation. With the default language setting, infer
these exact recognized trees independently for each course:
`Language/Chinese (Cantonese)` → `yue`, `Language/French` → `fr`,
`Language/Greek` → `el`, `Language/Latin` → `la`, `Language/Russian` → `ru`,
`Language/Spanish` → `es`, and `Language/Thai` → `th`. Other paths default to
English. Use `--language CODE` to override the path inference for the whole
invocation, or `--language auto` for WhisperKit detection. Every language the
model supports is available on every course; there is no English-only gate.

Discovery prunes bundled source repositories. Any directory below a course root
that contains a recognized project manifest — `package.json`, `pyproject.toml`,
`Cargo.toml`, `go.mod`, `Gemfile`, `Package.swift`, `composer.json`, `pom.xml`,
`pubspec.yaml`, `requirements.txt`, or a Gradle build file — is skipped whole,
along with everything beneath it. This keeps starter projects' bundled UI
sounds and sample clips out of the transcript tree. The course root itself is
never pruned, so a coding course may keep a manifest beside its lessons.
Pruning is logged as `SOURCE TREE PRUNED` information and never counted as a
course failure. The `.ts` MPEG transport-stream signature check still decides
ambiguous files outside pruned repositories, so a real transport stream is
transcribed while a TypeScript file is not.

The vendored worker source is `whisperkit-worker/`, a small Swift package that
depends on one pinned local Argmax checkout. The required revision is recorded
in both `Package.swift`'s default path and the worker source, and the checkout
is verified to be at that exact revision with no local modifications before any
build. A live run builds the release worker on demand into
`~/.agents/cache/whisperkit-worker/<fingerprint>/whisperkit-worker`. The
fingerprint covers the manifest, every worker source file, the Argmax checkout
path, and the required revision, so a moved, dirty, or re-pinned checkout can
never reuse a stale binary. `--dry-run` checks readiness only and never builds.
Point `ARGMAX_OSS_SWIFT_PATH` at a relocated checkout if needed.

The worker's decoding options reproduce what `whisperkit-cli transcribe` builds
for the same invocation, including the CLI's unset `firstTokenLogProbThreshold`
rather than the `DecodingOptions` default. `--timestamps` maps to the CLI's
report path and plain mode maps to `--without-timestamps`, so the two modes
decode exactly as they did through the CLI.

`--timestamps` preserves the complete transcription and groups text beneath
seek markers every 120 seconds by default. Change the interval with
`--timestamp-interval SECONDS`; use `0` for every WhisperKit segment with exact
start/end times. Prefer 120 seconds for study-guide source navigation and 60
seconds when finer lookup matters. WhisperKit clip ranges are not periodic
markers: they restrict transcription to selected spans and omit everything
outside them. Video and uncommon audio containers are converted through ffmpeg
first.

Returned segments feed the shared renderer: the segment start assigns the whole
segment to a bucket, silent buckets are absent, interval 0 renders each segment
range, and installed transcript bytes retain the existing format and
trailing-newline rules. Malformed, missing, or non-finite segment timestamps
fail the file without installing anything.

A live run lazily starts one persistent worker, waits up to 600 seconds for its
ready frame, and reuses its resident model across every file and course, so a
run pays the model load once instead of once per file.

A resident Core ML model does not stay healthy indefinitely. In a long run it
eventually fails to allocate IOSurface-backed buffers and then returns empty
output for every file that follows, without crashing or writing to stderr. Two
guards bound that. The worker is recycled every 100 requests, which costs one
warm load of well under a second and keeps allocations from accumulating. And
an empty or malformed result is treated as a statement about the worker rather
than about the file: it restarts the worker and retries before the file is
allowed to fail. After the configured attempts are exhausted, that file is
recorded as a normal transcription failure and the next file is processed. The
batch completes all available work, then exits 1 if any files failed. The child starts in its
own process group. A request has exactly one in-flight ID; invalid JSON, stale
IDs, duplicate results, premature EOF, and crashes terminate and
restart the worker before a retry, as does any retriable engine error, because
retrying into the same resident model reproduces resource exhaustion. A ready
frame reporting the wrong model or a different Argmax revision is rejected. Worker stderr is continuously drained
into the run log and cannot share the JSON protocol descriptor. Normal exit,
interruption, and volume failure all shut down the worker. A transcription
request has no wall-clock timeout and is allowed to finish the file end to end;
the legacy `--transcribe-timeout` option remains accepted only for checkpoint
compatibility. Change retry count with `--transcribe-retries N`. A failed or
empty result is never installed; after its retries it is reported as `FAIL`, and the batch proceeds
to the next file. Keep live output visible and attached. ffmpeg conversion
remains a per-file subprocess where required, uses an independent size-aware
timeout (override with `--extract-timeout`), retries with a
corrupt-frame-tolerant mono downmix, and defaults to one extraction retry
(`--extract-retries N`). A vanished `/Volumes` mount is probed with `statvfs`
plus `scandir`, waited on with bounded backoff, and never advances the
checkpoint cursor until the course can be retried.

Each run writes one consolidated flushed log at
`~/.agents/state/batch-transcribe-courses/logs/run-*.log` (or `--log-file PATH`)
and its actionable companion `run-*.review.txt`. The review file includes
runtime categories such as `OUTPUT COLLISION`, destination hazards, source
changes, and transcription failures. The log includes invocation, resolved
dependencies, worker and model paths, the Argmax revision, compute placement,
model load time, worker restarts, worker stderr, pruned source trees, every
scan/success/skip/failure/retry/timeout/volume event, per-file worker seconds,
audio duration, RTF, course summaries, totals, exit reason, and resume/retry
commands. Transcript files contain no engine provenance.

The hardware-free default test suite covers checkpoint migration, worker
bootstrap immutability, fingerprint pinning, shared rendering, protocol
corruption, restart/reuse/shutdown, source-repository pruning, transport-stream
preservation, and atomic-install isolation. Set `WHISPERKIT_LIVE_TESTS=1`, with
`WHISPERKIT_LIVE_SHORT_AUDIO` and `WHISPERKIT_LIVE_LONG_AUDIO`, only for
separately provisioned real-model fixtures. Use
`benchmark_whisperkit_worker.py` on direct-audio files copied to local
SSD; it reports model load time, per-file time, audio duration, and RTF, and
repeated `--placement ENCODER:DECODER` flags compare Core ML placements and
hash each placement's transcripts.

Live verification on 2026-08-04/05 used Swift 6.3.3/Xcode 26.6 on macOS 26.5.1
arm64 against Argmax `dcf3a00f0ae4`. The vendored release worker built in about
22 seconds with the SwiftPM dependency cache warm. The first model load after a
build took 90.9 seconds because Core ML specializes the Neural Engine model;
every later load in the same cache state took 0.7-0.8 seconds. That difference
is the whole point of the persistent worker: a run pays the load once rather
than once per file.

Worker output was compared against `whisperkit-cli` built from the same
checkout with identical settings. On a 30-second and a 60-second English
fixture, plain text and rendered 120-second timestamps were byte-identical in
both directions (matching SHA-256 and identical segment counts of 6 and 14).
Matching the CLI's unset `firstTokenLogProbThreshold` rather than the
`DecodingOptions` default of -1.5 is what makes this hold.

A five-placement sweep on one representative 18m23s lesson, two runs each with
120-second timestamps, measured 66.2x for `cpuAndNeuralEngine`/`cpuAndGPU`,
65.5x for `cpuAndNeuralEngine`/`all`, 43.3x for `all`/`all`, 43.2x for
`cpuAndGPU`/`cpuAndGPU`, and 26.8x for `cpuAndNeuralEngine`/`cpuAndNeuralEngine`.
Only `cpuAndNeuralEngine`/`all` matched the baseline transcript hash, and it was
slower. The production placement therefore stays encoder `cpuAndNeuralEngine`,
decoder `cpuAndGPU`: it is simultaneously the fastest measured placement and
the byte-identical reference.
