---
name: batch-transcribe-courses
description: Safely discover course boundaries and recursively transcribe course-folder media into each course root's top-level transcripts directory with WhisperKit. Use for bulk, batch, recursive, NAS, higher-level course-library roots, or individual course-folder transcription and transcript previews involving MP4, FLV, MKV, MOV, other video containers, audio files, missing transcripts, or mirrored module hierarchies.
---

# Batch Transcribe Courses

Use the bundled script to turn explicit course roots or safely inferred course
roots below a library folder into resumable transcript trees:

`Course/Module/Lesson.mp4` → `Course/transcripts/Module/Lesson.txt`

## Safety boundary

Treat every supplied input root as read-only. Treat each course root resolved
during preflight as read-only except for its own top-level `transcripts/`
directory.

- Permit only new directories below `transcripts/`, unique process-owned
  `.part` files, and previously absent `.txt` transcripts.
- Never rename, overwrite, truncate, move, or delete source media, existing
  transcripts, unrelated files in `transcripts/`, or other NAS content.
- Never add an overwrite mode or work around a safety rejection.
- Use explicit mode for known course folders. Use discovery mode only when the
  user identifies a path as a higher-level library or category root.
- In discovery mode, inspect the complete inferred-course list. Stop if any
  inferred boundary is actually a provider, topic, module, or resource folder.
  Pass ambiguous courses explicitly instead of working around the rejection.
- Let the script fail closed on overlapping roots, discovery errors, output
  collisions, missing dependencies, boundary escapes, or unsafe output paths.
- Do not follow media symlinks. Reject a symlinked `transcripts/` directory and
  any symlink or non-directory in an output parent path.

The script performs a complete read-only preflight before any live run writes.
It uses exclusive, atomic installation and never clobbers a path that appears
concurrently.

## Workflow

1. Decide whether each supplied path is an explicit course root or a
   higher-level library root. Do not mix the two modes in one invocation.
2. Run a preview with the exact paths, optional limit, and
   `--discover-course-roots` only for higher-level roots:

   ```bash
   python3 ~/.agents/skills/batch-transcribe-courses/scripts/transcribe_courses.py \
     --dry-run [--limit N] [--discover-course-roots] -- ROOT [ROOT ...]
   ```

3. Inspect the complete preflight result. In discovery mode, verify every
   printed `GROUP` and `Course root:` line before reviewing the media mappings.
   Use the grouping evidence and root reasons to identify wrappers, modules, or
   oddly named course folders. A `REVIEW` warning and exit `2` intentionally
   block live discovery when a single-child chain could be either a
   provider/course pair or a course/download-wrapper pair. Inspect only each
   marked subtree, then rerun in explicit mode with the complete corrected
   course-root list; do not make the script guess.
   Otherwise, stop on any nonzero exit or suspicious boundary.
4. If the user asked only for a preview, stop after the dry run.
5. If the user directly asked to transcribe, treat that request as authorization
   for the verified preflighted outputs. Run the live command with exactly the
   same roots, discovery flag, and limit, omitting only `--dry-run`; do not ask
   for redundant confirmation.
6. Report the combined summary and any individual failures. A live exit status
   of `1` means at least one item failed after preflight; rerunning is safe
   because existing outputs are skipped byte-for-byte.

The only supported interface is:

```text
transcribe_courses.py [--dry-run] [--limit N] [--discover-course-roots] ROOT [ROOT ...]
```

Discovery mode recursively ignores `transcripts/` trees and media symlinks. It
selects directories containing media directly and promotes numbered or
course-section directory sets to their common course parent. It supports
layouts such as:

```text
AutoCAD/Provider/Course/Module/Lesson.mp4
AutoCAD/Topic/Provider/Course/Module/Lesson.mp4
Ω - Astro & Storyblok/Author/Course/Lesson.mp4
```

The dry run prints grouping decisions, every inferred course root, the reason
for each choice, and its exact transcript destination boundary. This evidence
is intended for the driving LLM. Course-root inference is deliberately
conservative; it marks single-child chains for mandatory LLM review and
requires an explicit-root rerun before any write. Also inspect any other
questionable subtree and use explicit mode when modules cannot be identified
reliably.

Do not pass model, language, prompt, compute, output-root, paths-file, or other
advanced options. The script fixes the tested English M5 Pro configuration:
`large-v3-v20240930_turbo`, VAD, encoder `cpuAndNeuralEngine`, decoder
`cpuAndGPU`, WhisperKit's default mel `cpuAndGPU`, 64 workers, and no word
timestamps. It processes media files serially while WhisperKit parallelizes VAD
chunks.

## Monitor progress

The live parent process updates its macOS process title for every item:

```text
batch-transcribe-courses [3/18] Category/Course :: Module/Lesson.mp4
```

Use the background terminal's `/ps` view to see the current parent/course,
lesson, and global item count. The terminal output also logs `TRANSCRIBE`,
`OK`, `FAIL`, and per-course summaries. Do not inspect or manipulate `.part`
files to infer progress; they are private installation artifacts owned by the
running process.
