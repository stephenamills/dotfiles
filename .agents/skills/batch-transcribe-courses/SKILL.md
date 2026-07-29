---
name: batch-transcribe-courses
description: Recursively transcribe media inside one or more explicit course-root directories with WhisperKit, writing mirrored .txt files beneath each course root's top-level transcripts directory. Use for course-folder transcription, previews, missing transcripts, and resumable batch runs involving audio or video files.
---

# Batch Transcribe Courses

Pass course roots directly to the bundled script:

```bash
python3 ~/.agents/skills/batch-transcribe-courses/scripts/transcribe_courses.py \
  [--dry-run] [--limit N] -- COURSE_ROOT [COURSE_ROOT ...]
```

Each argument is one course root. Never pass a library, category, provider, or
NAS root and never infer course boundaries. Ask for the course-root paths if the
user has not supplied them.

The script recursively maps media within each course:

```text
Course/Module/Lesson.mp4
→ Course/transcripts/Module/Lesson.txt
```

Use `--dry-run` to preview every mapping. When the user asks to transcribe, run
the live command with the same roots and optional limit, omitting only
`--dry-run`. Keep live output visible and attached.

Existing transcripts are always skipped. The script writes only beneath each
course's `transcripts/` directory and never modifies source media. Re-running is
safe. On APFS/HFS+ installation is an exclusive atomic rename; on SMB it uses
exclusive destination creation without overwriting an existing path. An abrupt
SMB interruption can leave a partial destination that must be reviewed
manually.

WhisperKit settings are fixed: English `large-v3-v20240930_turbo`, VAD, M5 Pro
compute settings, 64 workers, and no word timestamps. Video and uncommon audio
containers are converted through ffmpeg first.
