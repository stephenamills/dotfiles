#!/usr/bin/env python3
"""Safely transcribe course media with one persistent WhisperKit worker.

Every supplied course root is read-only except for its top-level
``transcripts/`` directory. Live runs stream discovery and transcription in one
pass; ``--scan`` and ``--dry-run`` retain the complete fail-closed preflight
before any live work can create output directories, process-owned ``.part``
files, or absent ``.txt`` transcripts.

This is a simplified derivative of ``bulk_transcribe_network_whisperkit.py``.
Its intentionally fixed M5 Pro configuration is:

* model: ``large-v3-v20240930_turbo``
* task: native-language transcription (with recognized Language-tree codes)
* chunking: VAD
* audio encoder: CPU + Neural Engine
* text decoder: CPU + GPU
* mel spectrogram: WhisperKit's CPU + GPU default
* concurrent VAD workers: 16
* word timestamps: disabled

Transcription runs through one long-lived ``whisperkit-worker`` child that keeps
the Core ML model resident across every file in a run, with exactly one request
in flight. The worker is built from vendored Swift source against one pinned
clean Argmax checkout, and its decoding options reproduce those
``whisperkit-cli transcribe`` would build for the same invocation. There is no
fallback to ``whisperkit-cli``: a worker that cannot build, load, or answer is a
run failure. Video and uncommon audio containers first require one ffmpeg
conversion subprocess.
"""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass, field, replace
import errno
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import selectors
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from typing import Iterator
import unicodedata


MODEL = "large-v3-v20240930_turbo"
MODEL_ROOT = Path(
    os.environ.get("WHISPERKIT_MODEL_ROOT")
    or Path.home() / "Documents/huggingface/models/argmaxinc/whisperkit-coreml"
)
MODEL_PATH = MODEL_ROOT / f"openai_whisper-{MODEL}"
MODEL_REQUIRED_BUNDLES = ("AudioEncoder.mlmodelc", "TextDecoder.mlmodelc")
DEFAULT_LANGUAGE = "en"
LANGUAGE_PATH_CODES = {
    "chinese (cantonese)": "yue",
    "french": "fr",
    "greek": "el",
    "latin": "la",
    "russian": "ru",
    "spanish": "es",
    "thai": "th",
}
CHUNKING_STRATEGY = "vad"
AUDIO_ENCODER_COMPUTE_UNITS = "cpuAndNeuralEngine"
TEXT_DECODER_COMPUTE_UNITS = "cpuAndGPU"
CONCURRENT_WORKERS = 16
DEFAULT_TRANSCRIBE_TIMEOUT_SECONDS = 600
DEFAULT_TRANSCRIBE_RETRIES = 1
DEFAULT_EXTRACT_RETRIES = 1
DEFAULT_TIMESTAMP_INTERVAL_SECONDS = 120
CHILD_TERMINATE_GRACE_SECONDS = 10
# A cold Core ML load of the turbo model, including Neural Engine
# specialization, has been measured at roughly 90 seconds on this machine.  The
# ready timeout is deliberately several times that so a slow first load after an
# OS update is never mistaken for a hung worker.
WORKER_READY_TIMEOUT_SECONDS = 600
WORKER_BUILD_TIMEOUT_SECONDS = 3600
WORKER_CHECK_TIMEOUT_SECONDS = 120
WORKER_DUPLICATE_RESPONSE_GRACE_SECONDS = 0.01
# A resident Core ML model degrades over a long run: after a few hundred files a
# worker starts failing to allocate IOSurface-backed buffers and then returns
# empty output indefinitely.  Recycling the worker well before that point costs
# one warm model load (well under a second) and bounds the growth.
WORKER_RECYCLE_REQUEST_LIMIT = 100
# If that many files fail back to back, something is wrong with the worker, the
# model, or the volume.  Stop the run so it can be resumed after a fix instead
# of marching through hundreds of files producing nothing.
MAX_CONSECUTIVE_TRANSCRIPTION_FAILURES = 10
WORKER_SOURCE = Path(__file__).resolve().parent.parent / "whisperkit-worker"
WORKER_CACHE_ROOT = Path.home() / ".agents" / "cache" / "whisperkit-worker"
# The worker may only be built against this exact Argmax revision, checked out
# clean.  Both the path and the revision are folded into the cache fingerprint.
ARGMAX_SOURCE_PATH = Path(
    os.environ.get("ARGMAX_OSS_SWIFT_PATH")
    or "/Users/steph/Downloads/argmax-oss-swift"
)
ARGMAX_REQUIRED_REVISION = "dcf3a00f0ae4d5b57bc0aad92063b102b70d5fd1"
# Directories holding one of these manifests are self-contained source
# repositories shipped alongside a course, not lesson media.  Anything below
# them (bundled UI sounds, sample clips, node_modules fixtures) is pruned during
# discovery so it never becomes a transcript.
SOURCE_MANIFEST_NAMES = frozenset(
    {
        "cargo.toml",
        "composer.json",
        "gemfile",
        "go.mod",
        "package.json",
        "package.swift",
        "pom.xml",
        "pubspec.yaml",
        "pyproject.toml",
        "requirements.txt",
        "build.gradle",
        "build.gradle.kts",
    }
)
LEGACY_WHISPER_TOKEN_PATTERN = re.compile(r"<\|[^|\r\n]*\|>")
TIMESTAMP_CLOCK_PATTERN = r"\d{2,}:[0-5]\d:[0-5]\d"
LEADING_TIMESTAMP_PATTERN = re.compile(
    rf"\A(?:\ufeff)?\[(?:"
    rf"{TIMESTAMP_CLOCK_PATTERN}|"
    rf"{TIMESTAMP_CLOCK_PATTERN}\.\d{{3}} --> "
    rf"{TIMESTAMP_CLOCK_PATTERN}\.\d{{3}}"
    rf")\](?=\s|\Z)"
)

DIRECT_AUDIO_EXTENSIONS = frozenset(
    {
        ".flac",
        ".m4a",
        ".mp3",
        ".wav",
    }
)
AUDIO_EXTENSIONS = DIRECT_AUDIO_EXTENSIONS | frozenset(
    {
        ".aac",
        ".ac3",
        ".aif",
        ".aiff",
        ".amr",
        ".ape",
        ".caf",
        ".mka",
        ".ogg",
        ".opus",
        ".ra",
        ".wma",
    }
)
VIDEO_EXTENSIONS = frozenset(
    {
        ".3gp",
        ".asf",
        ".avi",
        ".f4v",
        ".flv",
        ".m2ts",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".mts",
        ".mxf",
        ".ogv",
        ".rm",
        ".rmvb",
        ".ts",
        ".vob",
        ".webm",
        ".wmv",
    }
)
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
AMBIGUOUS_MPEG_TS_EXTENSION = ".ts"
MPEG_TS_PACKET_SIZES = (188, 192, 204)
MPEG_TS_MIN_SYNC_PACKETS = 4
MPEG_TS_PROBE_BYTES = max(MPEG_TS_PACKET_SIZES) * (
    MPEG_TS_MIN_SYNC_PACKETS + 1
)
RENAME_EXCL = 0x00000004
RESUME_STATE_VERSION = 4
SUPPORTED_RESUME_STATE_VERSIONS = frozenset({1, 2, 3, 4})
# v3 serialized the retired engine selector.  Both recognized values now mean
# the same thing -- one persistent WhisperKit worker -- so both migrate, but an
# unrecognized value still means the checkpoint was written by something this
# script does not understand.
LEGACY_ENGINE_VALUES = frozenset({"whisperkit", "parakeet"})

# The active run log is intentionally process-local.  Keeping it out of the
# public function signatures preserves the small API used by older callers and
# tests while allowing main() to tee structured events to one file.
_ACTIVE_RUN_LOG: "RunLog | None" = None
_ACTIVE_RUN_ID: str | None = None
_ACTIVE_WORKER: "WhisperKitWorker | None" = None
_LAST_ENGINE_METRICS: "EngineMetrics | None" = None
_CONSECUTIVE_TRANSCRIPTION_FAILURES = 0


@dataclass(frozen=True)
class Course:
    root: Path
    ignore_omega_directories: bool = False

    @property
    def transcript_root(self) -> Path:
        return self.root / "transcripts"

    @property
    def name(self) -> str:
        return self.root.name


@dataclass(frozen=True)
class MediaIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int


@dataclass(frozen=True)
class TranscriptSnapshot:
    device: int
    inode: int
    size: int
    modified_ns: int
    changed_ns: int
    sha256: str


class InstallStatus(Enum):
    INSTALLED = "installed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True)
class InstallResult:
    status: InstallStatus
    detail: str | None = None

    @classmethod
    def installed(cls) -> InstallResult:
        return cls(InstallStatus.INSTALLED)

    @classmethod
    def skipped(cls, detail: str) -> InstallResult:
        return cls(InstallStatus.SKIPPED, detail)

    @classmethod
    def failed(cls, detail: str) -> InstallResult:
        return cls(InstallStatus.FAILED, detail)


@dataclass
class WorkItem:
    course: Course
    media: Path
    relative_media: Path
    relative_output: Path
    identity: MediaIdentity
    input_kind: str
    existing: bool = False
    existing_empty: bool = False
    timestamp_upgrade_needed: bool = False
    transcript_snapshot: TranscriptSnapshot | None = None
    selected: bool = False


@dataclass(frozen=True)
class Programs:
    ffmpeg: str
    worker: str | None = None


@dataclass(frozen=True)
class TranscriptionOptions:
    language: str | None = DEFAULT_LANGUAGE
    timestamps: bool = False
    timestamp_interval_seconds: int = DEFAULT_TIMESTAMP_INTERVAL_SECONDS
    timeout_seconds: int = DEFAULT_TRANSCRIBE_TIMEOUT_SECONDS
    retries: int = DEFAULT_TRANSCRIBE_RETRIES
    extract_timeout_seconds: int | None = None
    extract_retries: int = DEFAULT_EXTRACT_RETRIES
    overwrite: bool = False
    overwrite_empty: bool = False
    upgrade_timestamps: bool = False


@dataclass(frozen=True)
class TimedPhrase:
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class EngineMetrics:
    audio_seconds: float | None
    engine_seconds: float

    @property
    def rtf(self) -> float | None:
        if self.audio_seconds is None or self.engine_seconds <= 0:
            return None
        return self.audio_seconds / self.engine_seconds


@dataclass(frozen=True)
class WorkerBootstrapInfo:
    worker_path: Path
    model_path: Path | None = None
    worker_version: str | None = None
    audio_encoder_compute_units: str | None = None
    text_decoder_compute_units: str | None = None
    argmax_revision: str | None = None
    model_load_seconds: float | None = None


@dataclass
class CourseSummary:
    discovered: int = 0
    attempted: int = 0
    succeeded: int = 0
    skipped: int = 0
    limited: int = 0
    failed: int = 0
    would_transcribe: int = 0


@dataclass
class Preflight:
    courses: list[Course]
    items: list[WorkItem]
    programs: Programs
    work_total: int
    options: TranscriptionOptions = TranscriptionOptions()


StreamResult = tuple[CourseSummary, int, bool, bool]


@dataclass(frozen=True)
class RecoveredInvocation:
    roots: list[str]
    limit: int | None
    source_mode: str = "author-roots"
    scan: bool = False


class PreflightError(Exception):
    """A fail-closed preflight rejection."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


class ResumeStateError(Exception):
    """A local resume checkpoint could not be created, read, or updated."""


class WorkerProtocolError(Exception):
    """The persistent worker violated its one-request JSONL protocol."""


class WorkerModelLoadError(WorkerProtocolError):
    """A previously bootstrapped worker could not load its resident model."""


class WorkerRequestTimeout(Exception):
    """The persistent worker did not answer the in-flight request in time."""


class WorkerHealthError(Exception):
    """Too many files failed in a row for the run to be worth continuing."""


class VolumeUnavailable(Exception):
    """The filesystem containing a course disappeared and did not recover."""

    def __init__(self, volume_root: Path, detail: str | None = None):
        self.volume_root = volume_root
        message = detail or f"volume unavailable: {volume_root}"
        super().__init__(message)


def volume_root_for(path: Path) -> Path:
    """Return the longest mounted-volume prefix for *path*.

    SMB paths on macOS conventionally live beneath ``/Volumes/<name>``.  For
    ordinary paths, walk upwards to the nearest mount point so a transient
    filesystem failure is still checked at the right boundary.
    """

    try:
        resolved = Path(path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError, TypeError):
        resolved = Path(path).expanduser()
    parts = resolved.parts
    if len(parts) >= 3 and parts[0] == os.sep and parts[1] == "Volumes":
        return Path(os.sep) / "Volumes" / parts[2]
    candidate = resolved
    while candidate.parent != candidate:
        try:
            if os.path.ismount(candidate):
                return candidate
        except OSError:
            pass
        candidate = candidate.parent
    return Path(resolved.anchor or os.sep)


def volume_is_live(root: Path) -> bool:
    """Probe a volume rather than trusting a stale directory entry."""

    try:
        os.statvfs(root)
        with os.scandir(root) as entries:
            # A single directory entry forces the kernel/SMB client to answer
            # a real request while keeping the probe cheap on large shares.
            next(entries, None)
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _record_run_event(kind: str, message: str, *, issue: bool = False) -> None:
    if _ACTIVE_RUN_LOG is not None:
        _ACTIVE_RUN_LOG.event(kind, message, issue=issue)


def wait_for_volume(
    root: Path,
    review_log: "ReviewLog | None" = None,
    log: "RunLog | None" = None,
    *,
    timeout: int = 600,
) -> bool:
    """Wait for a vanished volume with bounded exponential backoff."""

    started = time.monotonic()
    delay = 5
    attempt = 1
    print(
        f"VOLUME LOST {root} - waiting up to {timeout}s for it to come back",
        flush=True,
    )
    if log is not None:
        log.event("VOLUME LOST", f"root={root} attempt={attempt}", issue=True)
    else:
        _record_run_event("VOLUME LOST", f"root={root} attempt={attempt}", issue=True)
    while True:
        if volume_is_live(root):
            detail = f"root={root} attempt={attempt}"
            print(f"VOLUME RESTORED {root} - continuing", flush=True)
            if log is not None:
                log.event("VOLUME RESTORED", detail)
            else:
                _record_run_event("VOLUME RESTORED", detail)
            return True
        elapsed = time.monotonic() - started
        if elapsed >= timeout:
            detail = f"root={root} timeout={timeout}s"
            print(
                f"VOLUME UNAVAILABLE {root} - gave up after {timeout}s",
                flush=True,
            )
            if review_log is not None:
                review_log.record("VOLUME UNAVAILABLE", root, detail)
            if log is not None:
                log.event("VOLUME LOST", detail, issue=True)
            else:
                _record_run_event("VOLUME LOST", detail, issue=True)
            return False
        wait = min(delay, max(0, timeout - elapsed))
        print(
            f"VOLUME RETRY attempt {attempt + 1} - next check in {wait:.0f}s",
            flush=True,
        )
        if log is not None:
            log.event(
                "RETRY",
                f"volume root={root} attempt={attempt + 1} wait={delay}s",
            )
        else:
            _record_run_event(
                "RETRY",
                f"volume root={root} attempt={attempt + 1} wait={delay}s",
            )
        time.sleep(wait)
        delay = min(delay * 2, 120)
        attempt += 1


@dataclass
class RunLog:
    """One flushed audit stream for a run, with lightweight event totals."""

    path: Path
    review_path: Path
    handle: object | None = None
    counts: dict[str, int] = field(default_factory=dict)
    started_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S %Z"))

    def __del__(self) -> None:
        global _ACTIVE_RUN_LOG
        handle = getattr(self, "handle", None)
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        if _ACTIVE_RUN_LOG is self:
            _ACTIVE_RUN_LOG = None

    @classmethod
    def for_current_run(
        cls,
        *,
        argv: list[str] | None = None,
        options: TranscriptionOptions | None = None,
        source_mode: str = "course-roots",
        course_count: int | None = None,
        checkpoint_path: Path | None = None,
        log_file: str | Path | None = None,
        run_id: str | None = None,
    ) -> "RunLog":
        global _ACTIVE_RUN_ID
        if run_id is None:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            run_id = f"{timestamp}-{os.getpid()}-{secrets.token_hex(4)}"
        _ACTIVE_RUN_ID = run_id
        directory = resume_state_directory() / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        path = Path(log_file).expanduser() if log_file else directory / f"run-{run_id}.log"
        review_path = directory / f"run-{run_id}.review.txt"
        review_path.parent.mkdir(parents=True, exist_ok=True)
        review_path.touch(exist_ok=True)
        result = cls(path=path, review_path=review_path)
        result._open()
        result.header(
            argv=argv or sys.argv,
            options=options,
            source_mode=source_mode,
            course_count=course_count,
            checkpoint_path=checkpoint_path,
        )
        global _ACTIVE_RUN_LOG
        _ACTIVE_RUN_LOG = result
        return result

    def _open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a", encoding="utf-8", newline="\n")

    def _write(self, line: str, *, sync: bool = False) -> None:
        if self.handle is None:
            self._open()
        assert self.handle is not None
        self.handle.write(line.rstrip("\n") + "\n")
        self.handle.flush()
        if sync:
            try:
                os.fsync(self.handle.fileno())
            except OSError:
                pass

    def header(
        self,
        *,
        argv: list[str],
        options: TranscriptionOptions | None,
        source_mode: str,
        course_count: int | None,
        checkpoint_path: Path | None,
    ) -> None:
        self._write("Batch Transcribe Courses - Run Log")
        self._write(f"Invocation: {shlex.join(argv)}")
        self._write(f"Start: {self.started_at}")
        self._write(f"Source mode: {source_mode}")
        self._write(f"Course count: {course_count if course_count is not None else 'unknown'}")
        self._write(f"Checkpoint: {checkpoint_path or 'pending'}")
        if options is not None:
            self._write(f"Transcription options: {options!r}")
        self._write(f"ffmpeg: {shutil.which('ffmpeg') or 'unresolved'}")
        worker_path, worker_error = worker_cache_path()
        self._write(
            f"whisperkit worker: {worker_path or worker_error or 'unresolved'}"
        )
        self._write(f"model path: {MODEL_PATH}")
        self._write(f"argmax source: {ARGMAX_SOURCE_PATH}")
        self._write(f"argmax revision: {ARGMAX_REQUIRED_REVISION}")
        self._write(
            f"compute units: encoder:{AUDIO_ENCODER_COMPUTE_UNITS}/"
            f"decoder:{TEXT_DECODER_COMPUTE_UNITS}"
        )

    def event(self, kind: str, message: str, *, issue: bool = False) -> None:
        self.counts[kind] = self.counts.get(kind, 0) + 1
        self._write(f"{kind} {message}", sync=issue)

    def footer(
        self,
        exit_code: int,
        reason: str,
        *,
        checkpoint_path: Path | None = None,
        retry_failed_command: str | None = None,
        issue_count: int | None = None,
    ) -> None:
        totals = " ".join(
            f"{name.lower()}={count}" for name, count in sorted(self.counts.items())
        ) or "none"
        self._write(f"Totals: {totals}")
        if issue_count is not None:
            self._write(f"Issue count: {issue_count}")
        self._write(f"Exit code: {exit_code} reason={reason}")
        if checkpoint_path is not None:
            resume = ["python3", str(Path(__file__)), "--resume", str(checkpoint_path)]
            self._write(f"Resume command: {shlex.join(resume)}")
        if retry_failed_command:
            self._write(f"Retry-failed command: {retry_failed_command}")
        self._write(f"Review log: {self.review_path}")
        if self.handle is not None:
            self.handle.close()
            self.handle = None
        global _ACTIVE_RUN_LOG
        if _ACTIVE_RUN_LOG is self:
            _ACTIVE_RUN_LOG = None


@dataclass
class ReviewLog:
    """Lazily write hierarchy exceptions for later manual handling."""

    path: Path
    issue_count: int = 0
    run_log: RunLog | None = None

    def __post_init__(self) -> None:
        self.path = Path(self.path)

    @classmethod
    def for_current_run(cls, run_log: RunLog | None = None) -> ReviewLog:
        if run_log is not None:
            return cls(run_log.review_path, run_log=run_log)
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"batch-transcribe-courses-review-{timestamp}-{os.getpid()}.txt"
        return cls(resume_state_directory() / filename)

    def info(self, category: str, path: str | Path, detail: str) -> None:
        """Write informational hierarchy notes without increasing issue_count."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as output:
                output.write(f"[INFO] {category}\nPath: {path}\nReason: {detail}\n\n")
                output.flush()
        except OSError:
            pass
        if self.run_log is not None:
            self.run_log.event(category, f"path={path} reason={detail}")

    def record(self, category: str, path: str | Path, reason: str) -> None:
        issue_number = self.issue_count + 1
        first_issue = self.issue_count == 0
        mode = "x" if first_issue and not self.path.exists() else "w" if first_issue else "a"
        try:
            with self.path.open(mode, encoding="utf-8", newline="\n") as output:
                if first_issue:
                    output.write(
                        "Batch Transcribe Courses - Manual Review\n"
                        f"Created: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
                        "These paths or runtime events may need follow-up; "
                        "valid work continued.\n\n"
                    )
                output.write(
                    f"[{issue_number}] {category}\n"
                    f"Path: {path}\n"
                    f"Reason: {reason}\n\n"
                )
                output.flush()
                os.fsync(output.fileno())
        except OSError as exc:
            print(
                f"warning: could not write review log {self.path}: {exc}",
                file=sys.stderr,
                flush=True,
            )
            print(
                f"REVIEW {category} path={path}: {reason}",
                file=sys.stderr,
                flush=True,
            )
        else:
            if first_issue:
                print(f"REVIEW LOG path={self.path}", flush=True)
        if self.run_log is not None:
            self.run_log.event(
                category,
                f"path={path} reason={reason}",
                issue=True,
            )
        self.issue_count = issue_number

    def print_summary(self) -> None:
        if self.issue_count:
            print(
                f"Review summary: issues={self.issue_count} log={self.path}",
                flush=True,
            )


def resume_state_directory() -> Path:
    return Path.home() / ".agents" / "state" / "batch-transcribe-courses"


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ResumeStateError(
            f"could not create resume-state directory {path.parent}: {exc}"
        ) from exc

    part = path.with_name(
        f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.part"
    )
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    try:
        descriptor = os.open(part, flags, 0o600)
        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
                newline="\n",
            ) as output:
                json.dump(
                    payload,
                    output,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
        except BaseException:
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
        os.replace(part, path)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException as exc:
        try:
            part.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise ResumeStateError(
            f"could not atomically update resume state {path}: {exc}"
        ) from exc


@dataclass
class ResumeCheckpoint:
    path: Path
    course_roots: list[str]
    source_roots: list[str]
    source_mode: str
    next_index: int
    status: str
    created_at: str
    updated_at: str
    current_course: str | None = None
    options: TranscriptionOptions = TranscriptionOptions()
    failed_courses: list[str] = field(default_factory=list)
    # The on-disk version this checkpoint was read from.  Anything below the
    # current version still needs migrating, which deliberately does not happen
    # until a worker has actually built and loaded.
    loaded_version: int = RESUME_STATE_VERSION

    @classmethod
    def create(
        cls,
        course_roots: list[str],
        source_roots: list[str],
        source_mode: str,
        next_index: int = 0,
        directory: Path | None = None,
        options: TranscriptionOptions = TranscriptionOptions(),
    ) -> ResumeCheckpoint:
        if not course_roots:
            raise ResumeStateError("cannot create resume state without courses")
        if next_index < 0 or next_index >= len(course_roots):
            raise ResumeStateError(
                f"resume start index {next_index} is outside "
                f"{len(course_roots)} courses"
            )
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        state_directory = directory or resume_state_directory()
        run_suffix = _ACTIVE_RUN_ID if _ACTIVE_RUN_LOG is not None else None
        if run_suffix is None:
            run_suffix = f"{timestamp}-{os.getpid()}-{secrets.token_hex(4)}"
        path = state_directory / f"resume-{run_suffix}.json"
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        checkpoint = cls(
            path=path,
            course_roots=list(course_roots),
            source_roots=list(source_roots),
            source_mode=source_mode,
            next_index=next_index,
            status="active",
            created_at=now,
            updated_at=now,
            current_course=course_roots[next_index],
            options=options,
            failed_courses=[],
        )
        checkpoint.save()
        return checkpoint

    @classmethod
    def load(cls, raw_path: str | Path) -> ResumeCheckpoint:
        path = Path(raw_path).expanduser()
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                file_stat = os.fstat(descriptor)
                if not stat.S_ISREG(file_stat.st_mode):
                    raise ResumeStateError(
                        f"resume state is not a regular file: {path}"
                    )
                with os.fdopen(descriptor, "r", encoding="utf-8") as source:
                    descriptor = -1
                    payload = json.load(source)
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
        except ResumeStateError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ResumeStateError(
                f"could not read resume state {path}: {exc}"
            ) from exc

        if not isinstance(payload, dict):
            raise ResumeStateError(f"invalid resume state object: {path}")
        version = payload.get("version")
        if version not in SUPPORTED_RESUME_STATE_VERSIONS:
            raise ResumeStateError(
                f"unsupported resume state version in {path}: "
                f"{version!r}"
            )
        course_roots = payload.get("course_roots")
        source_roots = payload.get("source_roots")
        source_mode = payload.get("source_mode")
        next_index = payload.get("next_index")
        status_value = payload.get("status")
        created_at = payload.get("created_at")
        updated_at = payload.get("updated_at")
        current_course = payload.get("current_course")
        failed_courses = payload.get("failed_courses", [])
        raw_options = payload.get("transcription_options", {})
        if (
            not isinstance(course_roots, list)
            or not course_roots
            or not all(
                isinstance(root, str) and root
                for root in course_roots
            )
            or not isinstance(source_roots, list)
            or not all(
                isinstance(root, str) and root
                for root in source_roots
            )
            or source_mode not in {
                "topic-roots",
                "author-roots",
                "course-roots",
            }
            or not isinstance(next_index, int)
            or isinstance(next_index, bool)
            or next_index < 0
            or next_index > len(course_roots)
            or status_value not in {
                "active",
                "interrupted",
                "paused",
                "complete",
                "complete-with-failures",
            }
            or not isinstance(created_at, str)
            or not isinstance(updated_at, str)
            or (
                current_course is not None
                and not isinstance(current_course, str)
            )
            or not isinstance(raw_options, dict)
            or not isinstance(failed_courses, list)
            or not all(isinstance(course, str) and course for course in failed_courses)
        ):
            raise ResumeStateError(f"invalid resume state fields: {path}")
        language = raw_options.get("language", DEFAULT_LANGUAGE)
        timestamps = raw_options.get("timestamps", False)
        timestamp_interval_seconds = raw_options.get(
            "timestamp_interval_seconds",
            DEFAULT_TIMESTAMP_INTERVAL_SECONDS,
        )
        timeout_seconds = raw_options.get(
            "timeout_seconds",
            DEFAULT_TRANSCRIBE_TIMEOUT_SECONDS,
        )
        retries = raw_options.get("retries", DEFAULT_TRANSCRIBE_RETRIES)
        overwrite = raw_options.get("overwrite", False)
        overwrite_empty = raw_options.get("overwrite_empty", False)
        upgrade_timestamps = raw_options.get("upgrade_timestamps", False)
        extract_timeout_seconds = raw_options.get("extract_timeout_seconds")
        extract_retries = raw_options.get("extract_retries", DEFAULT_EXTRACT_RETRIES)
        # v3 carried an engine selector.  Both of its recognized values now
        # resolve to the one persistent WhisperKit worker; anything else came
        # from a writer this script does not understand and stays fatal.
        legacy_engine = raw_options.get("engine")
        if legacy_engine is not None and legacy_engine not in LEGACY_ENGINE_VALUES:
            raise ResumeStateError(
                f"unsupported transcription engine in resume state {path}: "
                f"{legacy_engine!r}"
            )
        if (
            language is not None
            and (not isinstance(language, str) or not language)
        ) or (
            not isinstance(timestamps, bool)
            or not isinstance(timestamp_interval_seconds, int)
            or isinstance(timestamp_interval_seconds, bool)
            or timestamp_interval_seconds < 0
            or not isinstance(timeout_seconds, int)
            or isinstance(timeout_seconds, bool)
            or timeout_seconds <= 0
            or not isinstance(retries, int)
            or isinstance(retries, bool)
            or retries < 0
            or (
                extract_timeout_seconds is not None
                and (
                    not isinstance(extract_timeout_seconds, int)
                    or isinstance(extract_timeout_seconds, bool)
                    or extract_timeout_seconds <= 0
                )
            )
            or not isinstance(extract_retries, int)
            or isinstance(extract_retries, bool)
            or extract_retries < 0
            or not isinstance(overwrite, bool)
            or not isinstance(overwrite_empty, bool)
            or not isinstance(upgrade_timestamps, bool)
            or sum(
                (overwrite, overwrite_empty, upgrade_timestamps)
            )
            > 1
            or (upgrade_timestamps and not timestamps)
        ):
            raise ResumeStateError(
                f"invalid transcription options in resume state: {path}"
            )
        if status_value == "complete" and next_index != len(course_roots):
            raise ResumeStateError(
                f"completed resume state has an unfinished cursor: {path}"
            )
        if status_value == "complete-with-failures" and next_index != len(course_roots):
            raise ResumeStateError(
                f"failed-complete resume state has an unfinished cursor: {path}"
            )
        if status_value not in {"complete", "complete-with-failures"} and next_index >= len(course_roots):
            raise ResumeStateError(
                f"active resume state has no remaining course: {path}"
            )
        return cls(
            path=path.resolve(),
            course_roots=course_roots,
            source_roots=source_roots,
            source_mode=source_mode,
            next_index=next_index,
            status=status_value,
            created_at=created_at,
            updated_at=updated_at,
            current_course=current_course,
            options=TranscriptionOptions(
                language=language,
                timestamps=timestamps,
                timestamp_interval_seconds=timestamp_interval_seconds,
                timeout_seconds=timeout_seconds,
                retries=retries,
                extract_timeout_seconds=raw_options.get("extract_timeout_seconds"),
                extract_retries=raw_options.get("extract_retries", DEFAULT_EXTRACT_RETRIES),
                overwrite=overwrite,
                overwrite_empty=overwrite_empty,
                upgrade_timestamps=upgrade_timestamps,
            ),
            failed_courses=list(dict.fromkeys(failed_courses)),
            loaded_version=version,
        )

    @property
    def needs_migration(self) -> bool:
        return self.loaded_version != RESUME_STATE_VERSION

    def migrate(self) -> None:
        """Rewrite an older checkpoint at the current version.

        Callers must only reach this after a worker has successfully built and
        loaded, so a checkpoint written by an earlier version survives a failed
        bootstrap byte-for-byte.
        """

        if not self.needs_migration:
            return
        previous = self.loaded_version
        self.loaded_version = RESUME_STATE_VERSION
        self.save()
        _record_run_event(
            "CHECKPOINT MIGRATED",
            f"path={self.path} from=v{previous} to=v{RESUME_STATE_VERSION}",
        )
        print(
            f"CHECKPOINT MIGRATED v{previous} -> v{RESUME_STATE_VERSION} "
            f"state={self.path}",
            flush=True,
        )

    def save(self) -> None:
        self.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        atomic_write_json(
            self.path,
            {
                "version": RESUME_STATE_VERSION,
                "status": self.status,
                "source_mode": self.source_mode,
                "source_roots": self.source_roots,
                "course_roots": self.course_roots,
                "next_index": self.next_index,
                "current_course": self.current_course,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
                "failed_courses": self.failed_courses,
                "transcription_options": {
                    "language": self.options.language,
                    "timestamps": self.options.timestamps,
                    "timestamp_interval_seconds": (
                        self.options.timestamp_interval_seconds
                    ),
                    "timeout_seconds": self.options.timeout_seconds,
                    "retries": self.options.retries,
                    "extract_timeout_seconds": self.options.extract_timeout_seconds,
                    "extract_retries": self.options.extract_retries,
                    "overwrite": self.options.overwrite,
                    "overwrite_empty": self.options.overwrite_empty,
                    "upgrade_timestamps": (
                        self.options.upgrade_timestamps
                    ),
                },
            },
        )

    def set_cursor(self, next_index: int, status_value: str) -> None:
        if next_index < 0 or next_index > len(self.course_roots):
            raise ResumeStateError(
                f"resume cursor {next_index} is outside "
                f"{len(self.course_roots)} courses"
            )
        if status_value in {"complete", "complete-with-failures"} and next_index != len(self.course_roots):
            raise ResumeStateError(
                "resume state can be complete only after its final course"
            )
        self.next_index = next_index
        self.status = status_value
        self.current_course = (
            self.course_roots[next_index]
            if next_index < len(self.course_roots)
            else None
        )
        self.save()

    def record_failed_course(self, root: str | Path) -> None:
        value = str(root)
        if value not in self.failed_courses:
            self.failed_courses.append(value)
        self.save()

    def final_status(self) -> str:
        return "complete-with-failures" if self.failed_courses else "complete"

    def print_command(self) -> None:
        command = [
            "python3",
            str(Path(__file__)),
            "--resume",
            str(self.path),
        ]
        print(f"RESUME COMMAND: {shlex.join(command)}", flush=True)


class ProcessTitle:
    """Update argv in place so macOS process listings show live progress."""

    def __init__(self, argv_pointer: object, start: int, capacity: int):
        self._argv_pointer = argv_pointer
        self._start = start
        self._capacity = capacity

    @classmethod
    def capture(cls) -> ProcessTitle | None:
        if sys.platform != "darwin":
            return None
        try:
            libc = ctypes.CDLL(None)
            get_argv = libc._NSGetArgv
            get_argv.restype = ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
            argv = get_argv().contents
            addresses: list[int] = []
            index = 0
            while argv[index]:
                addresses.append(argv[index])
                index += 1
            if not addresses:
                return None

            # macOS stores argv strings contiguously. Refuse to write if this
            # process does not have that expected layout.
            expected = addresses[0]
            for address in addresses:
                if address != expected:
                    return None
                expected = address + len(ctypes.string_at(address)) + 1
            capacity = expected - addresses[0]
            if capacity < 2 or capacity > 1024 * 1024:
                return None
            return cls(argv, addresses[0], capacity)
        except (AttributeError, OSError, TypeError, ValueError):
            return None

    def set(self, text: str) -> None:
        encoded = text.encode("utf-8", "replace")[: self._capacity - 1]
        encoded = encoded.decode("utf-8", "ignore").encode("utf-8")
        ctypes.memset(self._start, 0, self._capacity)
        ctypes.memmove(self._start, encoded, len(encoded))
        self._argv_pointer[0] = self._start
        self._argv_pointer[1] = 0


def set_title(title: ProcessTitle | None, text: str) -> None:
    if title is not None:
        title.set(text)


def retry_failed_command(checkpoint: ResumeCheckpoint | None) -> str | None:
    if checkpoint is None or not getattr(checkpoint, "failed_courses", []):
        return None
    return shlex.join(
        ["python3", str(Path(__file__)), "--retry-failed", str(checkpoint.path)]
    )


def course_progress_label(course: Course) -> str:
    if course.root.parent.name:
        return f"{course.root.parent.name}/{course.name}"
    return course.name


def non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a non-negative integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def positive_int(value: str) -> int:
    parsed = non_negative_int(value)
    if parsed == 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Recursively transcribe media into each course root's top-level "
            "transcripts directory."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run the complete preflight and print mappings without writing",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="run a complete per-course preflight before live transcription",
    )
    parser.add_argument(
        "--limit",
        type=non_negative_int,
        metavar="N",
        help="process at most N selected transcripts across all course roots",
    )
    overwrite_group = parser.add_mutually_exclusive_group()
    overwrite_group.add_argument(
        "--overwrite",
        action="store_true",
        help=(
            "retranscribe selected media and atomically replace existing "
            "regular transcript files after a complete nonempty result"
        ),
    )
    overwrite_group.add_argument(
        "--overwrite-empty",
        action="store_true",
        help=(
            "retranscribe missing media and replace only existing regular "
            "transcript files whose size is exactly zero bytes"
        ),
    )
    overwrite_group.add_argument(
        "--upgrade-timestamps",
        action="store_true",
        help=(
            "enable timestamps and retranscribe only missing, empty, plain, "
            "or legacy-token transcripts; keep clean timestamped files"
        ),
    )
    parser.add_argument(
        "--language",
        default=DEFAULT_LANGUAGE,
        metavar="CODE",
        help=(
            "spoken-language code passed to the worker; default en also "
            "infers the supported Language/<name> path conventions; use "
            "'auto' for WhisperKit language detection"
        ),
    )
    parser.add_argument(
        "--timestamps",
        action="store_true",
        help="write periodic timestamp markers into each transcript",
    )
    parser.add_argument(
        "--timestamp-interval",
        type=non_negative_int,
        default=DEFAULT_TIMESTAMP_INTERVAL_SECONDS,
        metavar="SECONDS",
        help=(
            "seconds between timestamp blocks; 0 emits every engine "
            f"segment/phrase (default: {DEFAULT_TIMESTAMP_INTERVAL_SECONDS})"
        ),
    )
    parser.add_argument(
        "--transcribe-timeout",
        type=positive_int,
        default=DEFAULT_TRANSCRIBE_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help="deprecated compatibility option; transcription requests do not time out",
    )
    parser.add_argument(
        "--transcribe-retries",
        type=non_negative_int,
        default=DEFAULT_TRANSCRIBE_RETRIES,
        metavar="N",
        help=(
            "retry a failed or empty engine result N times "
            f"(default: {DEFAULT_TRANSCRIBE_RETRIES})"
        ),
    )
    parser.add_argument(
        "--extract-timeout",
        type=positive_int,
        default=None,
        metavar="SECONDS",
        help=(
            "ffmpeg extraction timeout; default is max(1800, 600 + "
            "file-size/250000)"
        ),
    )
    parser.add_argument(
        "--extract-retries",
        type=non_negative_int,
        default=DEFAULT_EXTRACT_RETRIES,
        metavar="N",
        help=f"retry ffmpeg extraction N times (default: {DEFAULT_EXTRACT_RETRIES})",
    )
    parser.add_argument(
        "--log-file",
        metavar="PATH",
        help="write the consolidated run log to PATH",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help=(
            "deprecated no-op; streaming is now the default live mode"
        ),
    )
    hierarchy_group = parser.add_mutually_exclusive_group()
    hierarchy_group.add_argument(
        "--author-roots",
        action="store_true",
        help=(
            "treat every supplied root as an author directory whose immediate "
            "child directories are course roots"
        ),
    )
    hierarchy_group.add_argument(
        "--topic-roots",
        action="store_true",
        help=(
            "treat every supplied root as a topic directory containing "
            "immediate authors whose immediate children are course roots; "
            "ignore directories beginning with Ω"
        ),
    )
    parser.add_argument(
        "--resume",
        metavar="STATE",
        help=(
            "resume a prior fast-start run from its local checkpoint; do not "
            "supply roots"
        ),
    )
    parser.add_argument(
        "--retry-failed",
        metavar="STATE",
        help="retry the failed_courses recorded in a completed checkpoint",
    )
    parser.add_argument(
        "--resume-from",
        metavar="COURSE_ROOT",
        help=(
            "start a new fast-start checkpoint at this course while retaining "
            "all subsequent supplied roots"
        ),
    )
    parser.add_argument(
        "--resume-from-command",
        metavar="COURSE_ROOT",
        help=(
            "read one prior author- or topic-root invocation from stdin as "
            "data and resume it at this course"
        ),
    )
    parser.add_argument(
        "roots",
        nargs="*",
        metavar="ROOT",
        help=(
            "one or more course roots, author roots with --author-roots, "
            "or topic roots with --topic-roots"
        ),
    )
    return parser


def options_from_args(args: argparse.Namespace) -> TranscriptionOptions:
    raw_language = args.language.strip()
    if not raw_language:
        raise ValueError("--language must not be empty")
    language = None if raw_language.casefold() == "auto" else raw_language
    return TranscriptionOptions(
        language=language,
        timestamps=args.timestamps or args.upgrade_timestamps,
        timestamp_interval_seconds=args.timestamp_interval,
        timeout_seconds=args.transcribe_timeout,
        retries=args.transcribe_retries,
        extract_timeout_seconds=args.extract_timeout,
        extract_retries=args.extract_retries,
        overwrite=args.overwrite,
        overwrite_empty=args.overwrite_empty,
        upgrade_timestamps=args.upgrade_timestamps,
    )


def path_overlap(first: Path, second: Path) -> bool:
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)


def resolve_input_root(raw: str) -> tuple[Path | None, str | None]:
    try:
        root = Path(raw).expanduser().resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as exc:
        return None, f"invalid input root {raw!r}: {exc}"
    try:
        root_stat = root.stat()
    except OSError as exc:
        return None, f"could not inspect input root {root}: {exc}"
    if not stat.S_ISDIR(root_stat.st_mode):
        return None, f"input root is not a directory: {root}"
    if not root.name:
        return None, f"input root must not be a filesystem root: {root}"
    return root, None


def _recover_volume_or_raise(path: Path, review_log: ReviewLog | None) -> None:
    volume = volume_root_for(path)
    if volume_is_live(volume):
        return
    if wait_for_volume(volume, review_log, _ACTIVE_RUN_LOG):
        return
    raise VolumeUnavailable(volume)


def validate_input_roots(raw_roots: list[str]) -> list[Path]:
    roots: list[Path] = []
    errors: list[str] = []
    for raw in raw_roots:
        root, error = resolve_input_root(raw)
        if error:
            errors.append(error)
        else:
            assert root is not None
            roots.append(root)
    for index, first in enumerate(roots):
        for second in roots[index + 1 :]:
            if path_overlap(first, second):
                errors.append(
                    f"input roots overlap: {first} and {second}"
                )
    if errors:
        raise PreflightError(errors)
    return roots


def author_course_sort_key(path: Path) -> tuple[str, str]:
    normalized = unicodedata.normalize("NFC", path.name)
    return normalized.casefold(), path.name


def has_mpeg_transport_stream_signature(path: Path) -> bool | None:
    """Recognize packet sync bytes without invoking ffmpeg for every .ts file.

    The .ts suffix is shared by MPEG transport streams and TypeScript source.
    Four equally spaced MPEG sync bytes make ordinary source text ineligible
    while retaining the common 188-, 192-, and 204-byte packet variants.  A
    read error returns None so discovery preserves its historical fail-open
    behavior for an actual but temporarily unreadable media file.
    """

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        sample = os.read(descriptor, MPEG_TS_PROBE_BYTES)
    except OSError:
        return None
    finally:
        os.close(descriptor)

    for packet_size in MPEG_TS_PACKET_SIZES:
        required_span = packet_size * (MPEG_TS_MIN_SYNC_PACKETS - 1)
        possible_starts = min(packet_size, len(sample) - required_span)
        for start in range(max(0, possible_starts)):
            if all(
                sample[start + packet_size * packet_index] == 0x47
                for packet_index in range(MPEG_TS_MIN_SYNC_PACKETS)
            ):
                return True
    return False


def media_path_is_eligible(path: Path, allowed_extensions: frozenset[str]) -> bool:
    suffix = path.suffix.casefold()
    if suffix not in allowed_extensions:
        return False
    if suffix != AMBIGUOUS_MPEG_TS_EXTENSION:
        return True
    signature = has_mpeg_transport_stream_signature(path)
    return signature is not False


def direct_media_files(root: Path) -> list[Path]:
    """Return regular media files directly beneath a hierarchy directory."""
    allowed = VIDEO_EXTENSIONS if is_music_tree(root) else MEDIA_EXTENSIONS
    media: list[Path] = []
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                try:
                    if (
                        entry.is_file(follow_symlinks=False)
                        and media_path_is_eligible(Path(entry.path), allowed)
                    ):
                        media.append(Path(entry.path))
                except OSError:
                    continue
    except OSError:
        return []
    return media


def _safe_scandir(root: Path) -> list[os.DirEntry[str]]:
    try:
        with os.scandir(root) as entries:
            return list(entries)
    except OSError:
        return []


def has_direct_files(root: Path) -> bool:
    for entry in _safe_scandir(root):
        try:
            if entry.is_file(follow_symlinks=False):
                return True
        except OSError:
            continue
    return False


def is_omega_directory_name(name: str) -> bool:
    return unicodedata.normalize("NFC", name).startswith("Ω")


def lexical_path_key(raw_path: str | Path) -> str:
    expanded = os.path.expanduser(os.fspath(raw_path))
    return os.path.normpath(os.path.abspath(expanded))


def resume_course_index(course_roots: list[str], raw_course: str) -> int:
    target = lexical_path_key(raw_course)
    for index, course_root in enumerate(course_roots):
        if lexical_path_key(course_root) == target:
            return index
    raise ResumeStateError(
        f"resume course is not present in the expanded course list: {raw_course}"
    )


def recover_author_invocation(command_text: str) -> RecoveredInvocation:
    command_text = command_text.replace("\\\r\n", "").replace("\\\n", "")
    try:
        tokens = shlex.split(command_text, posix=True)
    except ValueError as exc:
        raise ResumeStateError(
            f"could not parse prior shell command: {exc}"
        ) from exc
    script_indices = [
        index
        for index, token in enumerate(tokens)
        if Path(token).name == "transcribe_courses.py"
    ]
    if len(script_indices) != 1:
        raise ResumeStateError(
            "stdin must contain exactly one transcribe_courses.py invocation"
        )
    invocation = tokens[script_indices[0] + 1 :]
    try:
        delimiter = invocation.index("--")
    except ValueError as exc:
        raise ResumeStateError(
            "prior invocation has no '--' root delimiter"
        ) from exc

    options = invocation[:delimiter]
    roots = invocation[delimiter + 1 :]
    if not roots:
        raise ResumeStateError("prior invocation contains no roots")
    if any("\0" in root for root in roots):
        raise ResumeStateError("prior invocation contains an invalid root")

    source_mode: str | None = None
    scan = False
    limit: int | None = None
    option_index = 0
    while option_index < len(options):
        option = options[option_index]
        if option == "--author-roots":
            if source_mode is not None:
                raise ResumeStateError(
                    "prior invocation contains multiple hierarchy modes"
                )
            source_mode = "author-roots"
        elif option == "--topic-roots":
            if source_mode is not None:
                raise ResumeStateError(
                    "prior invocation contains multiple hierarchy modes"
                )
            source_mode = "topic-roots"
        elif option == "--skip-preflight":
            pass
        elif option == "--scan":
            scan = True
        elif option == "--limit":
            option_index += 1
            if option_index >= len(options):
                raise ResumeStateError(
                    "prior invocation has --limit without a value"
                )
            try:
                limit = non_negative_int(options[option_index])
            except argparse.ArgumentTypeError as exc:
                raise ResumeStateError(
                    f"invalid prior --limit value: {options[option_index]!r}"
                ) from exc
        elif option.startswith("--limit="):
            try:
                limit = non_negative_int(option.partition("=")[2])
            except argparse.ArgumentTypeError as exc:
                raise ResumeStateError(
                    f"invalid prior --limit option: {option!r}"
                ) from exc
        else:
            raise ResumeStateError(
                f"unsupported option in prior invocation: {option!r}"
            )
        option_index += 1

    if source_mode is None:
        raise ResumeStateError(
            "prior invocation must use --author-roots or --topic-roots"
        )
    return RecoveredInvocation(
        roots=roots,
        limit=limit,
        source_mode=source_mode,
        scan=scan,
    )


def expand_author_roots(
    raw_roots: list[str],
    review_log: ReviewLog,
) -> list[str]:
    """Expand each author root to its immediate child directories only."""

    author_roots: list[Path] = []
    course_roots: list[Path] = []

    for raw in raw_roots:
        author_root, error = resolve_input_root(raw)
        if error:
            review_log.record("AUTHOR ROOT", raw, error)
            continue
        assert author_root is not None
        overlapping = next(
            (
                accepted
                for accepted in author_roots
                if path_overlap(author_root, accepted)
            ),
            None,
        )
        if overlapping is not None:
            review_log.record(
                "AUTHOR ROOT",
                author_root,
                f"overlaps earlier author root {overlapping}",
            )
            continue
        author_roots.append(author_root)

    for author_root in author_roots:
        children: list[Path] = []
        try:
            with os.scandir(author_root) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=True):
                            children.append(Path(entry.path))
                    except OSError as exc:
                        review_log.record(
                            "AUTHOR ROOT CHILD",
                            entry.path,
                            f"could not inspect child of {author_root}: {exc}",
                        )
        except OSError as exc:
            review_log.record(
                "AUTHOR ROOT",
                author_root,
                f"could not list directory: {exc}",
            )
            continue

        children.sort(key=author_course_sort_key)
        if not children:
            media = direct_media_files(author_root)
            if media:
                course_roots.append(author_root)
                review_log.info(
                    "FLAT COURSE ROOT",
                    author_root,
                    f"promoted directory containing {len(media)} media file(s)",
                )
            elif has_direct_files(author_root):
                review_log.record(
                    "AUTHOR ROOT",
                    author_root,
                    "contains no immediate course directories (non-media files only)",
                )
            else:
                review_log.info(
                    "AUTHOR ROOT EMPTY",
                    author_root,
                    "contains no immediate course directories",
                )
            continue
        course_roots.extend(children)

    return [str(course_root) for course_root in course_roots]


def expand_topic_roots(
    raw_roots: list[str],
    review_log: ReviewLog,
) -> list[str]:
    """Expand topic roots through immediate authors to immediate courses."""

    topic_roots: list[Path] = []
    course_roots: list[Path] = []

    for raw in raw_roots:
        topic_root, error = resolve_input_root(raw)
        if error:
            review_log.record("TOPIC ROOT", raw, error)
            continue
        assert topic_root is not None
        overlapping = next(
            (
                accepted
                for accepted in topic_roots
                if path_overlap(topic_root, accepted)
            ),
            None,
        )
        if overlapping is not None:
            review_log.record(
                "TOPIC ROOT",
                topic_root,
                f"overlaps earlier topic root {overlapping}",
            )
            continue
        topic_roots.append(topic_root)

    for topic_root in topic_roots:
        author_roots: list[Path] = []
        try:
            with os.scandir(topic_root) as entries:
                for entry in entries:
                    if is_omega_directory_name(entry.name):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=True):
                            author_roots.append(Path(entry.path))
                    except OSError as exc:
                        review_log.record(
                            "TOPIC ROOT CHILD",
                            entry.path,
                            f"could not inspect child of {topic_root}: {exc}",
                        )
        except OSError as exc:
            review_log.record(
                "TOPIC ROOT",
                topic_root,
                f"could not list directory: {exc}",
            )
            continue

        author_roots.sort(key=author_course_sort_key)
        if not author_roots:
            media = direct_media_files(topic_root)
            if media:
                course_roots.append(topic_root)
                review_log.info(
                    "FLAT COURSE ROOT",
                    topic_root,
                    f"promoted directory containing {len(media)} media file(s)",
                )
            elif _safe_scandir(topic_root):
                # There are entries, but all are excluded/otherwise not
                # hierarchy roots.  Keep this actionable; a truly empty
                # directory is informational and has no issue count.
                review_log.record(
                    "TOPIC ROOT",
                    topic_root,
                    "contains no immediate author directories after Ω exclusions",
                )
            else:
                review_log.info(
                    "TOPIC ROOT EMPTY",
                    topic_root,
                    "contains no immediate author directories after Ω exclusions",
                )
            continue

        for author_root in author_roots:
            children: list[Path] = []
            try:
                with os.scandir(author_root) as entries:
                    for entry in entries:
                        if is_omega_directory_name(entry.name):
                            continue
                        try:
                            if entry.is_dir(follow_symlinks=True):
                                children.append(Path(entry.path))
                        except OSError as exc:
                            review_log.record(
                                "TOPIC AUTHOR CHILD",
                                entry.path,
                                "could not inspect child of "
                                f"{author_root}: {exc}",
                            )
            except OSError as exc:
                review_log.record(
                    "TOPIC AUTHOR ROOT",
                    author_root,
                    f"could not list directory: {exc}",
                )
                continue

            children.sort(key=author_course_sort_key)
            if not children:
                media = direct_media_files(author_root)
                if media:
                    course_roots.append(author_root)
                    review_log.info(
                        "FLAT COURSE ROOT",
                        author_root,
                        f"promoted directory containing {len(media)} media file(s)",
                    )
                elif has_direct_files(author_root):
                    review_log.record(
                        "TOPIC AUTHOR ROOT",
                        author_root,
                        "contains no immediate course directories (non-media files only)",
                    )
                else:
                    review_log.info(
                        "TOPIC AUTHOR ROOT EMPTY",
                        author_root,
                        "contains no immediate course directories after Ω exclusions",
                    )
                continue
            course_roots.extend(children)

    return [str(course_root) for course_root in course_roots]


def resolve_program(name: str, label: str) -> tuple[str | None, str | None]:
    resolved = shutil.which(name)
    if resolved is None:
        return None, f"missing dependency: {label} executable {name!r} is not on PATH"
    try:
        candidate = Path(resolved)
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            return None, f"invalid dependency: {label} is not executable: {resolved}"
    except OSError as exc:
        return None, f"could not inspect {label} executable {resolved}: {exc}"
    return resolved, None


def resolve_model_path() -> tuple[Path | None, str | None]:
    try:
        if not MODEL_PATH.is_dir():
            return None, (
                f"missing dependency: WhisperKit model directory not found: {MODEL_PATH}; "
                f"set WHISPERKIT_MODEL_ROOT to the directory containing "
                f"openai_whisper-{MODEL}"
            )
        missing = [
            bundle
            for bundle in MODEL_REQUIRED_BUNDLES
            if not (MODEL_PATH / bundle).exists()
        ]
    except OSError as exc:
        return None, f"could not inspect WhisperKit model directory {MODEL_PATH}: {exc}"
    if missing:
        return None, (
            f"invalid dependency: WhisperKit model directory {MODEL_PATH} is missing "
            f"{', '.join(missing)}"
        )
    return MODEL_PATH, None


def worker_environment() -> dict[str, str]:
    """Environment for every worker invocation.

    The compute placement and model path are passed explicitly so the fixed
    configuration documented here, rather than the worker's own defaults, is
    what actually runs.
    """

    environment = dict(os.environ)
    environment["WHISPERKIT_WORKER_MODEL_PATH"] = str(MODEL_PATH)
    environment["WHISPERKIT_AUDIO_ENCODER_COMPUTE_UNITS"] = (
        AUDIO_ENCODER_COMPUTE_UNITS
    )
    environment["WHISPERKIT_TEXT_DECODER_COMPUTE_UNITS"] = (
        TEXT_DECODER_COMPUTE_UNITS
    )
    return environment


def worker_fingerprint(
    source_directory: Path = WORKER_SOURCE,
) -> tuple[str | None, str | None]:
    """Fingerprint the vendored worker source and its pinned Argmax revision.

    ``Package.resolved`` is deliberately excluded.  Its only pin is
    swift-argument-parser, which belongs to the Argmax CLI target and is never
    linked into this worker; what the worker actually runs is fixed by the
    verified Argmax revision below.
    """

    sources = source_directory / "Sources"
    try:
        source_files = sorted(
            path for path in sources.rglob("*") if path.is_file()
        )
    except OSError as exc:
        return None, f"could not inspect WhisperKit worker source: {exc}"
    if not source_files:
        return None, f"WhisperKit worker source is missing beneath {sources}"
    files = [source_directory / "Package.swift", *source_files]
    digest = hashlib.sha256()
    # A cached binary is only valid for the exact Argmax checkout it was linked
    # against, so the path and required revision are part of the identity.
    for label in (str(ARGMAX_SOURCE_PATH), ARGMAX_REQUIRED_REVISION):
        marker = label.encode("utf-8")
        digest.update(len(marker).to_bytes(8, "big"))
        digest.update(marker)
    try:
        for path in files:
            if not path.is_file():
                return None, f"WhisperKit worker source file is missing: {path}"
            relative = path.relative_to(source_directory).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            payload = path.read_bytes()
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
    except (OSError, ValueError) as exc:
        return None, f"could not fingerprint WhisperKit worker source: {exc}"
    return digest.hexdigest(), None


def worker_cache_path() -> tuple[Path | None, str | None]:
    fingerprint, error = worker_fingerprint()
    if error:
        return None, error
    assert fingerprint is not None
    return WORKER_CACHE_ROOT / fingerprint / "whisperkit-worker", None


def _run_git(arguments: list[str]) -> tuple[str | None, str | None]:
    git = shutil.which("git")
    if git is None:
        return None, "missing dependency: git is not on PATH"
    try:
        completed = subprocess.run(
            [git, "-C", str(ARGMAX_SOURCE_PATH), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"could not run git in {ARGMAX_SOURCE_PATH}: {exc}"
    if completed.returncode != 0:
        detail = completed.stderr.strip() or f"exit {completed.returncode}"
        return None, (
            f"git {' '.join(arguments)} failed in {ARGMAX_SOURCE_PATH}: {detail}"
        )
    return completed.stdout, None


def verify_argmax_checkout() -> str | None:
    """Require the pinned Argmax revision, checked out with no local edits."""

    try:
        if not ARGMAX_SOURCE_PATH.is_dir():
            return (
                "missing dependency: Argmax checkout not found at "
                f"{ARGMAX_SOURCE_PATH}; set ARGMAX_OSS_SWIFT_PATH to the "
                "clean argmax-oss-swift working copy"
            )
    except OSError as exc:
        return f"could not inspect Argmax checkout {ARGMAX_SOURCE_PATH}: {exc}"

    revision_output, error = _run_git(["rev-parse", "HEAD"])
    if error:
        return error
    assert revision_output is not None
    revision = revision_output.strip()
    if revision != ARGMAX_REQUIRED_REVISION:
        return (
            f"Argmax checkout {ARGMAX_SOURCE_PATH} is at "
            f"{revision or 'an unknown revision'}; the worker requires "
            f"{ARGMAX_REQUIRED_REVISION}"
        )

    status_output, error = _run_git(["status", "--porcelain"])
    if error:
        return error
    assert status_output is not None
    dirty = [line for line in status_output.splitlines() if line.strip()]
    if dirty:
        return (
            f"Argmax checkout {ARGMAX_SOURCE_PATH} has {len(dirty)} local "
            "modifications; the worker requires a clean checkout"
        )
    return None


def _worker_mode_frame(
    worker_path: Path,
    mode: str,
    timeout_seconds: int,
) -> tuple[dict[str, object] | None, str | None]:
    command = [str(worker_path), mode]
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=True,
            env=worker_environment(),
        )
    except OSError as exc:
        return None, f"could not start WhisperKit worker {mode}: {exc}"
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        terminate_owned_child(process)
        stdout, stderr = process.communicate()
        return None, (
            f"WhisperKit worker {mode} timed out after {timeout_seconds} seconds"
        )
    except KeyboardInterrupt:
        terminate_owned_child(process)
        raise
    if stderr and _ACTIVE_RUN_LOG is not None:
        _ACTIVE_RUN_LOG.event(
            "WORKER STDERR",
            stderr.strip().replace("\n", r"\n"),
        )
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        return None, (
            f"WhisperKit worker {mode} returned {len(lines)} protocol frames; "
            "expected exactly one"
        )
    try:
        frame = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        return None, f"WhisperKit worker {mode} returned invalid JSON: {exc}"
    if not isinstance(frame, dict):
        return None, f"WhisperKit worker {mode} returned a non-object frame"
    if process.returncode != 0:
        if mode == "--check" and process.returncode == 3:
            return frame, None
        message = frame.get("message")
        detail = message if isinstance(message, str) and message else stderr.strip()
        return None, (
            f"WhisperKit worker {mode} failed with exit {process.returncode}"
            + (f": {detail}" if detail else "")
        )
    return frame, None


def build_whisperkit_worker(worker_path: Path) -> str | None:
    """Build and atomically cache the pinned release worker."""

    checkout_error = verify_argmax_checkout()
    if checkout_error:
        return checkout_error
    try:
        worker_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f"could not create WhisperKit worker cache {worker_path.parent}: {exc}"
    _record_run_event(
        "WORKER BUILD",
        f"building source={WORKER_SOURCE} argmax={ARGMAX_SOURCE_PATH} "
        f"revision={ARGMAX_REQUIRED_REVISION} output={worker_path}",
    )
    print(f"WORKER BUILD building worker={worker_path}", flush=True)
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(
            prefix="build-",
            dir=worker_path.parent,
        ) as raw_scratch:
            scratch = Path(raw_scratch)
            command = [
                "swift",
                "build",
                "-c",
                "release",
                "--product",
                "whisperkit-worker",
                "--package-path",
                str(WORKER_SOURCE),
                "--scratch-path",
                str(scratch),
            ]
            environment = dict(os.environ)
            environment["ARGMAX_OSS_SWIFT_PATH"] = str(ARGMAX_SOURCE_PATH)
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    start_new_session=True,
                    env=environment,
                )
            except OSError as exc:
                return f"could not start Swift release build: {exc}"
            try:
                stdout, stderr = process.communicate(
                    timeout=WORKER_BUILD_TIMEOUT_SECONDS
                )
            except subprocess.TimeoutExpired:
                terminate_owned_child(process)
                process.communicate()
                return (
                    "WhisperKit worker release build timed out after "
                    f"{WORKER_BUILD_TIMEOUT_SECONDS} seconds"
                )
            except KeyboardInterrupt:
                terminate_owned_child(process)
                raise
            if process.returncode != 0:
                return (
                    "WhisperKit worker release build failed: "
                    f"{short_process_error(process.returncode, stderr, stdout)}"
                )
            product = scratch / "release" / "whisperkit-worker"
            if not product.is_file():
                return f"Swift release build produced no worker binary at {product}"
            part = worker_path.with_name(
                f".{worker_path.name}.{os.getpid()}.{secrets.token_hex(4)}.part"
            )
            try:
                shutil.copyfile(product, part)
                part.chmod(0o700)
                descriptor = os.open(part, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                os.replace(part, worker_path)
                directory_fd = os.open(
                    worker_path.parent,
                    os.O_RDONLY | os.O_DIRECTORY,
                )
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError as exc:
                try:
                    part.unlink()
                except OSError:
                    pass
                return f"could not cache WhisperKit worker binary: {exc}"
    except OSError as exc:
        return f"could not create temporary WhisperKit build directory: {exc}"
    elapsed = time.monotonic() - started
    _record_run_event(
        "WORKER BUILD",
        f"complete worker={worker_path} seconds={elapsed:.1f}",
    )
    print(f"WORKER BUILD complete seconds={elapsed:.1f}", flush=True)
    return None


def _worker_info_from_frame(
    worker_path: Path,
    frame: dict[str, object],
) -> tuple[WorkerBootstrapInfo | None, str | None]:
    if frame.get("ready") is not True:
        return None, (
            f"WhisperKit model is not usable at {MODEL_PATH}; the worker "
            "reported its required Core ML bundles are missing"
        )
    if frame.get("model") != MODEL:
        return None, (
            "WhisperKit worker reported unexpected model "
            f"{frame.get('model')!r}"
        )
    if frame.get("argmax_revision") != ARGMAX_REQUIRED_REVISION:
        return None, (
            "WhisperKit worker was built against Argmax revision "
            f"{frame.get('argmax_revision')!r}, not {ARGMAX_REQUIRED_REVISION}"
        )
    worker_version = frame.get("worker_version")
    if worker_version != worker_path.parent.name:
        return None, (
            "WhisperKit worker fingerprint mismatch: expected "
            f"{worker_path.parent.name!r}, received {worker_version!r}"
        )
    raw_model_path = frame.get("model_path")
    raw_encoder = frame.get("audio_encoder_compute_units")
    raw_decoder = frame.get("text_decoder_compute_units")
    raw_load_seconds = frame.get("model_load_seconds")
    return (
        WorkerBootstrapInfo(
            worker_path=worker_path,
            model_path=(
                Path(raw_model_path) if isinstance(raw_model_path, str) else None
            ),
            worker_version=worker_version,
            audio_encoder_compute_units=(
                raw_encoder if isinstance(raw_encoder, str) else None
            ),
            text_decoder_compute_units=(
                raw_decoder if isinstance(raw_decoder, str) else None
            ),
            argmax_revision=ARGMAX_REQUIRED_REVISION,
            model_load_seconds=(
                float(raw_load_seconds)
                if isinstance(raw_load_seconds, (int, float))
                and not isinstance(raw_load_seconds, bool)
                else None
            ),
        ),
        None,
    )


def bootstrap_worker(
    *,
    allow_build: bool = True,
) -> tuple[Programs | None, WorkerBootstrapInfo | None, str | None]:
    """Resolve ffmpeg, the local model, and the cached worker binary.

    This never falls back to ``whisperkit-cli``; if the worker cannot be
    resolved the run fails.
    """

    ffmpeg, ffmpeg_error = resolve_program("ffmpeg", "ffmpeg")
    if ffmpeg_error:
        return None, None, ffmpeg_error
    assert ffmpeg is not None

    _, model_error = resolve_model_path()
    if model_error:
        return None, None, model_error

    worker_path, path_error = worker_cache_path()
    if path_error:
        return None, None, path_error
    assert worker_path is not None
    try:
        worker_ready = worker_path.is_file() and os.access(worker_path, os.X_OK)
    except OSError as exc:
        return None, None, f"could not inspect WhisperKit worker cache: {exc}"
    if not worker_ready:
        if not allow_build:
            return None, None, (
                f"WhisperKit worker is not built at {worker_path}; "
                "dry-run will not build it"
            )
        build_error = build_whisperkit_worker(worker_path)
        if build_error:
            return None, None, build_error

    frame, check_error = _worker_mode_frame(
        worker_path,
        "--check",
        WORKER_CHECK_TIMEOUT_SECONDS,
    )
    if check_error:
        return None, None, check_error
    assert frame is not None
    info, readiness_error = _worker_info_from_frame(worker_path, frame)
    if readiness_error:
        return None, None, readiness_error
    assert info is not None
    _record_run_event(
        "WORKER BOOTSTRAP",
        f"ready worker={worker_path} model={info.model_path} "
        f"encoder={info.audio_encoder_compute_units} "
        f"decoder={info.text_decoder_compute_units}",
    )
    return Programs(ffmpeg, str(worker_path)), info, None


def identity_from_stat(file_stat: os.stat_result) -> MediaIdentity:
    return MediaIdentity(
        device=file_stat.st_dev,
        inode=file_stat.st_ino,
        size=file_stat.st_size,
        modified_ns=file_stat.st_mtime_ns,
    )


def is_music_tree(path: Path) -> bool:
    return any(part.casefold() == "music" for part in path.parts)


def language_code_from_course_path(path: Path) -> str | None:
    parts = path.parts
    for index, component in enumerate(parts[:-1]):
        if component.casefold() != "language":
            continue
        language_name = unicodedata.normalize(
            "NFC",
            parts[index + 1],
        ).casefold()
        return LANGUAGE_PATH_CODES.get(language_name)
    return None


def effective_options_for_course(
    options: TranscriptionOptions,
    course: Course,
) -> TranscriptionOptions:
    if options.language != DEFAULT_LANGUAGE:
        return options
    inferred = language_code_from_course_path(course.root)
    if inferred is None:
        return options
    return replace(options, language=inferred)


def is_source_repository(directory: Path, filenames: list[str]) -> bool:
    """Report whether *directory* looks like a bundled source repository.

    A course root itself is never treated this way: a coding course may
    legitimately keep a manifest beside its lessons.  Only nested directories
    qualify, so bundled starter projects and their sample assets drop out of
    discovery.
    """

    del directory
    return any(name.casefold() in SOURCE_MANIFEST_NAMES for name in filenames)


def discover_media(course: Course) -> tuple[list[WorkItem], list[str]]:
    items: list[WorkItem] = []
    errors: list[str] = []
    pruned: list[Path] = []
    allowed_extensions = (
        VIDEO_EXTENSIONS if is_music_tree(course.root) else MEDIA_EXTENSIONS
    )

    def onerror(error: OSError) -> None:
        errors.append(
            f"discovery failed at {error.filename or course.root}: "
            f"{error.strerror or error}"
        )

    try:
        for directory, dirnames, filenames in os.walk(
            course.root, topdown=True, followlinks=False, onerror=onerror
        ):
            directory_path = Path(directory)
            if course.ignore_omega_directories:
                dirnames[:] = [
                    name
                    for name in dirnames
                    if not is_omega_directory_name(name)
                ]
            if directory_path == course.root:
                dirnames[:] = [
                    name for name in dirnames if name.casefold() != "transcripts"
                ]
            elif is_source_repository(directory_path, filenames):
                # Pruning a bundled repository is routine housekeeping, not a
                # course failure: it is recorded and the walk moves on.
                dirnames[:] = []
                pruned.append(directory_path)
                continue

            for filename in filenames:
                media = directory_path / filename
                if not media_path_is_eligible(media, allowed_extensions):
                    continue
                try:
                    media_stat = media.lstat()
                except OSError as exc:
                    errors.append(f"could not inspect media candidate {media}: {exc}")
                    continue
                if stat.S_ISLNK(media_stat.st_mode):
                    continue
                if not stat.S_ISREG(media_stat.st_mode):
                    continue

                try:
                    relative_media = media.relative_to(course.root)
                except ValueError:
                    errors.append(f"discovered media escapes course root: {media}")
                    continue
                relative_output = relative_media.with_suffix(".txt")
                destination = course.transcript_root / relative_output
                try:
                    destination.relative_to(course.transcript_root)
                except ValueError:
                    errors.append(
                        f"transcript destination escapes course boundary: {destination}"
                    )
                    continue
                items.append(
                    WorkItem(
                        course=course,
                        media=media,
                        relative_media=relative_media,
                        relative_output=relative_output,
                        identity=identity_from_stat(media_stat),
                        input_kind=(
                            "direct"
                            if media.suffix.casefold() in DIRECT_AUDIO_EXTENSIONS
                            else "ffmpeg"
                        ),
                    )
                )
    except (OSError, RuntimeError) as exc:
        errors.append(f"discovery failed at {course.root}: {exc}")

    for directory_path in pruned:
        try:
            relative = directory_path.relative_to(course.root).as_posix()
        except ValueError:
            relative = str(directory_path)
        _record_run_event(
            "SOURCE TREE PRUNED",
            f"course={course.root} directory={relative}",
        )
        print(
            f"SOURCE TREE PRUNED course={course.name} directory={relative}",
            flush=True,
        )

    items.sort(
        key=lambda item: (
            unicodedata.normalize("NFC", item.relative_media.as_posix()).casefold(),
            item.relative_media.as_posix(),
        )
    )
    return items, errors


def lstat_or_missing(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def read_regular_file_snapshot(
    path: str | Path,
    *,
    dir_fd: int | None = None,
) -> tuple[bytes, TranscriptSnapshot]:
    flags = os.O_RDONLY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags, dir_fd=dir_fd)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise OSError(
                errno.EINVAL,
                f"transcript destination is not a regular file: {path}",
            )
        chunks: list[bytes] = []
        digest = hashlib.sha256()
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
            digest.update(chunk)
        after = os.fstat(descriptor)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if before_identity != after_identity:
            raise OSError(
                errno.EAGAIN,
                f"transcript destination changed while being read: {path}",
            )
        payload = b"".join(chunks)
        if len(payload) != after.st_size:
            raise OSError(
                errno.EAGAIN,
                f"transcript destination size changed while being read: {path}",
            )
        return payload, TranscriptSnapshot(
            device=after.st_dev,
            inode=after.st_ino,
            size=after.st_size,
            modified_ns=after.st_mtime_ns,
            changed_ns=after.st_ctime_ns,
            sha256=digest.hexdigest(),
        )
    finally:
        os.close(descriptor)


def transcript_needs_timestamp_upgrade(payload: bytes) -> bool:
    try:
        transcript = payload.decode("utf-8")
    except UnicodeDecodeError:
        return True
    if not transcript.strip():
        return True
    if LEGACY_WHISPER_TOKEN_PATTERN.search(transcript):
        return True
    return LEADING_TIMESTAMP_PATTERN.match(transcript) is None


def validate_transcript_root(course: Course) -> list[str]:
    try:
        root_stat = lstat_or_missing(course.transcript_root)
    except OSError as exc:
        return [f"could not inspect transcript root {course.transcript_root}: {exc}"]
    if root_stat is None:
        return []
    if stat.S_ISLNK(root_stat.st_mode):
        return [f"transcript root must not be a symlink: {course.transcript_root}"]
    if not stat.S_ISDIR(root_stat.st_mode):
        return [f"transcript root is not a directory: {course.transcript_root}"]
    return []


def inspect_output(item: WorkItem) -> tuple[bool, bool, str | None]:
    current = item.course.transcript_root
    for component in item.relative_output.parent.parts:
        current = current / component
        try:
            parent_stat = lstat_or_missing(current)
        except OSError as exc:
            return False, False, f"could not inspect output parent {current}: {exc}"
        if parent_stat is None:
            return False, False, None
        if stat.S_ISLNK(parent_stat.st_mode):
            return (
                False,
                False,
                f"output parent must not be a symlink: {current}",
            )
        if not stat.S_ISDIR(parent_stat.st_mode):
            return (
                False,
                False,
                f"output parent is not a directory: {current}",
            )

    destination = item.course.transcript_root / item.relative_output
    try:
        destination_stat = lstat_or_missing(destination)
    except OSError as exc:
        return (
            False,
            False,
            f"could not inspect transcript destination {destination}: {exc}",
        )
    if destination_stat is None:
        return False, False, None
    if stat.S_ISLNK(destination_stat.st_mode):
        return (
            False,
            False,
            f"transcript destination must not be a symlink: {destination}",
        )
    if not stat.S_ISREG(destination_stat.st_mode):
        return (
            False,
            False,
            f"transcript destination is not a regular file: {destination}",
        )
    return True, destination_stat.st_size == 0, None


def collision_key(item: WorkItem) -> str:
    normalized = unicodedata.normalize("NFC", item.relative_output.as_posix())
    return normalized.casefold()


def perform_preflight(
    raw_roots: list[str],
    limit: int | None,
    options: TranscriptionOptions = TranscriptionOptions(),
    ignore_omega_directories: bool = False,
    programs: Programs | None = None,
) -> Preflight:
    courses = [
        Course(
            root,
            ignore_omega_directories=ignore_omega_directories,
        )
        for root in validate_input_roots(raw_roots)
    ]
    errors: list[str] = []

    if programs is None:
        programs, _info, bootstrap_error = bootstrap_worker(allow_build=False)
        if bootstrap_error:
            errors.append(bootstrap_error)

    all_items: list[WorkItem] = []
    for course in courses:
        errors.extend(validate_transcript_root(course))
        items, discovery_errors = discover_media(course)
        errors.extend(discovery_errors)
        all_items.extend(items)

        collisions: dict[str, list[WorkItem]] = {}
        for item in items:
            collisions.setdefault(collision_key(item), []).append(item)
        for colliding in collisions.values():
            if len(colliding) > 1:
                sources = ", ".join(
                    str(item.relative_media) for item in colliding
                )
                errors.append(
                    f"output collision in {course.root}: {sources} all map to "
                    f"transcripts/{colliding[0].relative_output}"
                )

        for item in items:
            exists, empty, output_error = inspect_output(item)
            item.existing = exists
            item.existing_empty = empty
            if output_error:
                errors.append(output_error)
                continue
            if not options.upgrade_timestamps:
                continue
            if not exists:
                item.timestamp_upgrade_needed = True
                continue
            destination = course.transcript_root / item.relative_output
            try:
                payload, snapshot = read_regular_file_snapshot(destination)
            except FileNotFoundError:
                item.existing = False
                item.existing_empty = False
                item.timestamp_upgrade_needed = True
            except OSError as exc:
                errors.append(
                    "could not inspect transcript contents for timestamp "
                    f"upgrade {destination}: {exc}"
                )
            else:
                item.existing_empty = snapshot.size == 0
                item.timestamp_upgrade_needed = (
                    transcript_needs_timestamp_upgrade(payload)
                )
                item.transcript_snapshot = snapshot

    if errors:
        raise PreflightError(errors)
    if programs is None:
        raise PreflightError(errors or ["could not resolve transcription programs"])

    work_total = 0
    for item in all_items:
        if not item_is_eligible(item, options):
            continue
        if limit is None or work_total < limit:
            item.selected = True
            work_total += 1

    return Preflight(
        courses=courses,
        items=all_items,
        programs=programs,
        work_total=work_total,
        options=options,
    )


def item_is_eligible(
    item: WorkItem,
    options: TranscriptionOptions,
) -> bool:
    if not item.existing:
        return True
    if options.overwrite:
        return True
    if options.overwrite_empty and item.existing_empty:
        return True
    return options.upgrade_timestamps and item.timestamp_upgrade_needed


def item_can_replace_existing(
    item: WorkItem,
    options: TranscriptionOptions,
) -> bool:
    if options.overwrite:
        return True
    if options.overwrite_empty and item.existing_empty:
        return True
    return (
        options.upgrade_timestamps
        and item.existing
        and item.timestamp_upgrade_needed
        and item.transcript_snapshot is not None
    )


def print_settings(options: TranscriptionOptions = TranscriptionOptions()) -> None:
    language = options.language or "auto"
    overwrite = (
        "all"
        if options.overwrite
        else "empty-only"
        if options.overwrite_empty
        else "timestamp-upgrade"
        if options.upgrade_timestamps
        else "off"
    )
    timestamp_mode = (
        (
            "segment"
            if options.timestamp_interval_seconds == 0
            else f"{options.timestamp_interval_seconds}s"
        )
        if options.timestamps
        else "off"
    )
    detail = (
        f"model={MODEL} language={language}/recognized-paths task=transcribe "
        "backend=persistent-worker "
        f"chunking={CHUNKING_STRATEGY} "
        "input=direct-common-audio/ffmpeg-other music-trees=video-only "
        f"compute=encoder:{AUDIO_ENCODER_COMPUTE_UNITS}/"
        f"decoder:{TEXT_DECODER_COMPUTE_UNITS}/mel:cpuAndGPU "
        f"workers={CONCURRENT_WORKERS} "
        f"argmax={ARGMAX_REQUIRED_REVISION[:12]}"
    )
    print(
        f"Transcription settings: engine=whisperkit {detail} "
        f"timestamps={timestamp_mode} "
        f"timeout=disabled retries={options.retries} "
        f"overwrite={overwrite}",
        flush=True,
    )


def summary_for_course(preflight: Preflight, course: Course) -> CourseSummary:
    summary = CourseSummary()
    for item in preflight.items:
        if item.course != course:
            continue
        summary.discovered += 1
        if item.selected:
            summary.would_transcribe += 1
        elif item_is_eligible(item, preflight.options):
            summary.limited += 1
        else:
            summary.skipped += 1
    return summary


def print_preflight(preflight: Preflight, dry_run: bool) -> None:
    action = "WOULD" if dry_run else "READY"
    for course in preflight.courses:
        summary = summary_for_course(preflight, course)
        if not dry_run:
            language = (
                effective_options_for_course(preflight.options, course).language
                or "auto"
            )
            print(
                f"PREFLIGHT course={course.root} "
                f"language={language} "
                f"discovered={summary.discovered} skipped={summary.skipped} "
                f"ready={summary.would_transcribe} limited={summary.limited}",
                flush=True,
            )
            continue

        print(f"Course: {course.root}", flush=True)
        course_items = [item for item in preflight.items if item.course == course]
        total = len(course_items)
        for index, item in enumerate(course_items, start=1):
            prefix = f"[{course.name} {index}/{total}]"
            if (
                item.selected
                and item.existing
                and preflight.options.upgrade_timestamps
            ):
                print(
                    f"{prefix} UPGRADE-TIMESTAMPS ({item.input_kind}) "
                    f"{item.relative_media} -> transcripts/{item.relative_output}",
                    flush=True,
                )
            elif (
                item.selected
                and item.existing_empty
                and preflight.options.overwrite_empty
            ):
                print(
                    f"{prefix} REPAIR-EMPTY ({item.input_kind}) "
                    f"{item.relative_media} -> transcripts/{item.relative_output}",
                    flush=True,
                )
            elif item.selected and item.existing:
                print(
                    f"{prefix} OVERWRITE ({item.input_kind}) "
                    f"{item.relative_media} -> transcripts/{item.relative_output}",
                    flush=True,
                )
            elif item.selected:
                print(
                    f"{prefix} {action} ({item.input_kind}) "
                    f"{item.relative_media} -> transcripts/{item.relative_output}",
                    flush=True,
                )
            elif item_is_eligible(item, preflight.options):
                print(
                    f"{prefix} LIMIT {item.relative_media} -> "
                    f"transcripts/{item.relative_output}",
                    flush=True,
                )
            elif item.existing:
                print(
                    f"{prefix} SKIP existing {item.relative_media} -> "
                    f"transcripts/{item.relative_output}",
                    flush=True,
                )
            else:
                raise AssertionError("ineligible missing transcript")
        print(
            f"Preflight summary [{course.name}]: "
            f"discovered={summary.discovered} skipped={summary.skipped} "
            f"{'would_transcribe' if dry_run else 'ready'}="
            f"{summary.would_transcribe} limited={summary.limited}",
            flush=True,
        )


def open_safe_output_parent(item: WorkItem) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    current_fd = os.open(item.course.root, flags)
    components = ("transcripts", *item.relative_output.parent.parts)
    try:
        for component in components:
            if component in ("", ".", "..") or os.sep in component:
                raise OSError(errno.EINVAL, f"unsafe output component {component!r}")
            try:
                os.mkdir(component, mode=0o755, dir_fd=current_fd)
            except FileExistsError:
                pass
            next_fd = os.open(component, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def open_safe_output_root(course: Course) -> int:
    """Create and open one course's top-level transcripts directory."""
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    current_fd = os.open(course.root, flags)
    try:
        try:
            os.mkdir("transcripts", mode=0o755, dir_fd=current_fd)
        except FileExistsError:
            pass
        next_fd = os.open("transcripts", flags, dir_fd=current_fd)
        os.close(current_fd)
        return next_fd
    except BaseException:
        os.close(current_fd)
        raise


def destination_exists(parent_fd: int, name: str) -> bool:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    return True


def revalidate_media(item: WorkItem) -> str | None:
    try:
        media_stat = item.media.lstat()
    except OSError as exc:
        return f"could not revalidate source media: {exc}"
    if stat.S_ISLNK(media_stat.st_mode):
        return "source media became a symlink after preflight"
    if not stat.S_ISREG(media_stat.st_mode):
        return "source media is no longer a regular file"
    if identity_from_stat(media_stat) != item.identity:
        return "source media changed after preflight"
    return None


def short_process_error(
    returncode: int, stderr: str, stdout: str = "", limit: int = 300
) -> str:
    detail = stderr.strip() or stdout.strip()
    lines = detail.splitlines()
    compact: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        end = index + 1
        while end < len(lines) and lines[end].strip() == line:
            end += 1
        compact.append(line if end == index + 1 else f"{line} ... ×{end - index}")
        index = end
    if len(compact) > 8:
        compact = compact[:2] + ["..."] + compact[-6:]
    detail = "\n".join(compact)
    detail_limit = max(0, limit - len(f"exit {returncode}: "))
    if len(detail) > detail_limit:
        # Preserve the beginning and end, which are generally the useful
        # decoder diagnosis and final exit context.
        head = min(120, detail_limit // 2)
        tail = max(0, detail_limit - head - 5)
        detail = detail[:head].rstrip() + " ... " + (detail[-tail:].lstrip() if tail else "")
    return f"exit {returncode}: {detail}" if detail else f"exit {returncode}"


def communicate_with_progress(
    process: subprocess.Popen[str],
    timeout_seconds: int,
) -> tuple[str, str]:
    """Collect ffmpeg output while timing out only after no progress.

    Mocked children and platforms without selectable text pipes retain the
    ordinary ``communicate`` path used by the unit tests.
    """
    stdout_pipe = process.stdout
    stderr_pipe = process.stderr
    if stdout_pipe is None or stderr_pipe is None:
        return process.communicate(timeout=timeout_seconds)
    try:
        stdout_fd = stdout_pipe.fileno()
        stderr_fd = stderr_pipe.fileno()
    except (AttributeError, OSError, ValueError, TypeError):
        return process.communicate(timeout=timeout_seconds)
    if not isinstance(stdout_fd, int) or not isinstance(stderr_fd, int):
        return process.communicate(timeout=timeout_seconds)
    selector = selectors.DefaultSelector()
    buffers: dict[int, list[bytes]] = {stdout_fd: [], stderr_fd: []}
    try:
        selector.register(stdout_pipe, selectors.EVENT_READ)
        selector.register(stderr_pipe, selectors.EVENT_READ)
    except (OSError, ValueError):
        selector.close()
        return process.communicate(timeout=timeout_seconds)
    last_progress = time.monotonic()
    try:
        while selector.get_map():
            if process.poll() is not None:
                wait_timeout = 0.05
            else:
                wait_timeout = 0.5
            ready = selector.select(wait_timeout)
            if not ready and time.monotonic() - last_progress >= timeout_seconds:
                raise subprocess.TimeoutExpired("ffmpeg", timeout_seconds)
            for key, _mask in ready:
                try:
                    chunk = os.read(key.fileobj.fileno(), 64 * 1024)
                except OSError:
                    chunk = b""
                if chunk:
                    buffers[key.fileobj.fileno()].append(chunk)
                    last_progress = time.monotonic()
                else:
                    try:
                        selector.unregister(key.fileobj)
                    except Exception:
                        pass
            if process.poll() is not None and not ready:
                break
        process.wait(timeout=1)
    finally:
        selector.close()
    return (
        b"".join(buffers[stdout_fd]).decode("utf-8", "replace"),
        b"".join(buffers[stderr_fd]).decode("utf-8", "replace"),
    )


def extract_audio(
    media: Path,
    wav_path: Path,
    ffmpeg: str,
    timeout_seconds: int = DEFAULT_TRANSCRIBE_TIMEOUT_SECONDS,
    review_log: ReviewLog | None = None,
    extract_retries: int = 0,
) -> str | None:
    filters = [
        "aformat=channel_layouts=mono,aresample=16000",
        "pan=mono|c0=c0",
    ]
    last_error: str | None = None
    attempts = max(0, extract_retries) + 1
    for attempt in range(1, attempts + 1):
        for filter_expression in filters:
            command = [
                ffmpeg,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-fflags",
                "+discardcorrupt",
                "-err_detect",
                "ignore_err",
                "-i",
                str(media),
                "-map",
                "0:a:0?",
                "-vn",
                "-af",
                filter_expression,
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                "-progress",
                "pipe:1",
                "-n",
                str(wav_path),
            ]
            try:
                process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    start_new_session=True,
                )
            except OSError as exc:
                return f"could not run ffmpeg: {exc}"
            try:
                stdout, stderr = communicate_with_progress(process, timeout_seconds)
            except subprocess.TimeoutExpired:
                terminate_owned_child(process)
                process.communicate()
                last_error = (
                    f"ffmpeg timed out after {timeout_seconds} seconds and was terminated"
                )
                if review_log is not None:
                    review_log.record("FFMPEG TIMEOUT", media, f"{last_error}; attempt={attempt}/{attempts}")
                _record_run_event("TIMEOUT", f"ffmpeg={media} attempt={attempt}/{attempts}", issue=True)
                break
            except KeyboardInterrupt:
                terminate_owned_child(process)
                raise
            if process.returncode != 0:
                if stderr and _ACTIVE_RUN_LOG is not None:
                    _ACTIVE_RUN_LOG.event(
                        "FFMPEG STDERR",
                        f"media={media} {stderr.strip().replace(chr(10), r'\\n')}",
                    )
                last_error = short_process_error(process.returncode, stderr=stderr, stdout=stdout)
                try:
                    if wav_path.exists():
                        wav_path.unlink()
                except OSError:
                    pass
                continue
            try:
                if not wav_path.is_file() or wav_path.stat().st_size == 0:
                    last_error = "ffmpeg produced no audio"
                    continue
            except OSError as exc:
                last_error = f"could not inspect extracted audio: {exc}"
                continue
            return None
        if attempt < attempts:
            _record_run_event("RETRY", f"ffmpeg={media} next={attempt + 1}/{attempts}")
            if review_log is not None:
                review_log.info("FFMPEG RETRY", media, f"next attempt={attempt + 1}/{attempts}")
    return last_error or "ffmpeg extraction failed"


def terminate_owned_child(process: subprocess.Popen[str]) -> None:
    """Terminate the process group created for one WhisperKit invocation."""

    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        process.terminate()
    try:
        process.wait(timeout=CHILD_TERMINATE_GRACE_SECONDS)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except OSError:
        process.kill()
    process.wait()


class WhisperKitWorker:
    """One long-lived, single-flight WhisperKit JSONL worker."""

    def __init__(
        self,
        executable: str | Path,
        *,
        arguments: tuple[str, ...] = (),
        ready_timeout_seconds: int = WORKER_READY_TIMEOUT_SECONDS,
    ):
        self.executable = str(executable)
        self.arguments = arguments
        self.ready_timeout_seconds = ready_timeout_seconds
        self.process: subprocess.Popen[bytes] | None = None
        self.ready: dict[str, object] | None = None
        self.completed_requests = 0
        self._stdout_buffer = bytearray()
        self._stderr_thread: threading.Thread | None = None

    def _drain_stderr(self, stream: object) -> None:
        try:
            for raw_line in stream:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                if line:
                    _record_run_event("WORKER STDERR", line)
        except (OSError, ValueError):
            return

    @staticmethod
    def _close_process_streams(process: subprocess.Popen[bytes]) -> None:
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:
                pass

    def start(self) -> None:
        if self.process is not None and self.process.poll() is None:
            return
        self.process = None
        self.ready = None
        self._stdout_buffer.clear()
        try:
            process = subprocess.Popen(
                [self.executable, *self.arguments],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                start_new_session=True,
                env=worker_environment(),
            )
        except OSError as exc:
            raise WorkerProtocolError(
                f"could not start WhisperKit worker: {exc}"
            ) from exc
        self.process = process
        assert process.stderr is not None
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr,
            args=(process.stderr,),
            name="whisperkit-worker-stderr",
            daemon=True,
        )
        self._stderr_thread.start()
        try:
            frame = self._read_frame(self.ready_timeout_seconds)
            if frame.get("type") == "error":
                error_type = (
                    WorkerModelLoadError
                    if frame.get("code") == "model_load_failed"
                    else WorkerProtocolError
                )
                raise error_type(
                    "WhisperKit worker model load failed: "
                    f"{frame.get('message', 'unknown error')}"
                )
            if (
                frame.get("type") != "ready"
                or frame.get("engine") != "whisperkit"
                or frame.get("model") != MODEL
                or frame.get("argmax_revision") != ARGMAX_REQUIRED_REVISION
            ):
                raise WorkerProtocolError(
                    f"invalid WhisperKit ready frame: {frame!r}"
                )
            self.ready = frame
            _record_run_event(
                "WORKER READY",
                " ".join(
                    (
                        f"worker={self.executable}",
                        f"model={frame.get('model')}",
                        f"model_path={frame.get('model_path')}",
                        f"argmax={frame.get('argmax_revision')}",
                        f"encoder={frame.get('audio_encoder_compute_units')}",
                        f"decoder={frame.get('text_decoder_compute_units')}",
                        f"load_seconds={frame.get('model_load_seconds')}",
                    )
                ),
            )
        except BaseException:
            self.terminate("startup failure")
            raise

    def _read_line(self, timeout_seconds: float | None) -> bytes:
        process = self.process
        if process is None or process.stdout is None:
            raise WorkerProtocolError("WhisperKit worker is not running")
        deadline = (
            None
            if timeout_seconds is None
            else time.monotonic() + timeout_seconds
        )
        selector = selectors.DefaultSelector()
        selector.register(process.stdout.fileno(), selectors.EVENT_READ)
        try:
            while True:
                newline = self._stdout_buffer.find(b"\n")
                if newline >= 0:
                    line = bytes(self._stdout_buffer[:newline])
                    del self._stdout_buffer[: newline + 1]
                    return line
                if deadline is None:
                    ready = selector.select()
                    if not ready:
                        continue
                else:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise WorkerRequestTimeout(
                            "WhisperKit worker timed out after "
                            f"{timeout_seconds:g} seconds"
                        )
                    if not selector.select(remaining):
                        raise WorkerRequestTimeout(
                            "WhisperKit worker timed out after "
                            f"{timeout_seconds:g} seconds"
                        )
                chunk = os.read(process.stdout.fileno(), 65_536)
                if not chunk:
                    raise WorkerProtocolError(
                        "WhisperKit worker closed its protocol stream"
                    )
                self._stdout_buffer.extend(chunk)
                if len(self._stdout_buffer) > 64 * 1024 * 1024:
                    raise WorkerProtocolError(
                        "WhisperKit worker emitted an oversized protocol frame"
                    )
        finally:
            selector.close()

    def _read_frame(self, timeout_seconds: float | None) -> dict[str, object]:
        raw_line = self._read_line(timeout_seconds)
        try:
            decoded = raw_line.decode("utf-8")
            frame = json.loads(decoded)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise WorkerProtocolError(
                f"WhisperKit worker emitted invalid JSON: {exc}"
            ) from exc
        if not isinstance(frame, dict):
            raise WorkerProtocolError(
                "WhisperKit worker emitted a non-object protocol frame"
            )
        if frame.get("type") not in {"ready", "result", "error"}:
            raise WorkerProtocolError(
                "WhisperKit worker emitted an invalid frame type: "
                f"{frame.get('type')!r}"
            )
        return frame

    def _additional_response_pending(self) -> bool:
        if b"\n" in self._stdout_buffer:
            return True
        process = self.process
        if process is None or process.stdout is None:
            return False
        selector = selectors.DefaultSelector()
        selector.register(process.stdout.fileno(), selectors.EVENT_READ)
        try:
            if not selector.select(WORKER_DUPLICATE_RESPONSE_GRACE_SECONDS):
                return False
            chunk = os.read(process.stdout.fileno(), 65_536)
            if not chunk:
                raise WorkerProtocolError(
                    "WhisperKit worker closed its protocol stream after a response"
                )
            self._stdout_buffer.extend(chunk)
            if len(self._stdout_buffer) > 64 * 1024 * 1024:
                raise WorkerProtocolError(
                    "WhisperKit worker emitted an oversized protocol frame"
                )
            return b"\n" in self._stdout_buffer
        finally:
            selector.close()

    def transcribe(
        self,
        audio_path: Path,
        timeout_seconds: int | None,
        *,
        language: str | None = None,
        timestamps: bool = False,
    ) -> dict[str, object]:
        self.start()
        assert self.process is not None and self.process.stdin is not None
        request_id = secrets.token_hex(16)
        request = json.dumps(
            {
                "id": request_id,
                "type": "transcribe",
                "audio_path": str(audio_path),
                "language": language,
                "timestamps": timestamps,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8") + b"\n"
        try:
            self.process.stdin.write(request)
            self.process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            raise WorkerProtocolError(
                f"could not send request to WhisperKit worker: {exc}"
            ) from exc
        frame = self._read_frame(timeout_seconds)
        if frame.get("type") == "ready":
            raise WorkerProtocolError(
                "WhisperKit worker emitted a duplicate ready frame"
            )
        if frame.get("id") != request_id:
            raise WorkerProtocolError(
                "WhisperKit worker response id does not match the in-flight request"
            )
        if self._additional_response_pending():
            raise WorkerProtocolError(
                "WhisperKit worker emitted a duplicate response for one request"
            )
        self.completed_requests += 1
        return frame

    def terminate(self, reason: str) -> None:
        process = self.process
        self.process = None
        self.ready = None
        self._stdout_buffer.clear()
        if process is not None:
            _record_run_event(
                "WORKER RESTART",
                f"worker={self.executable} reason={reason}",
            )
            terminate_owned_child(process)
        thread = self._stderr_thread
        self._stderr_thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1)
        if process is not None:
            self._close_process_streams(process)

    def shutdown(self) -> None:
        process = self.process
        if process is None:
            return
        if process.poll() is None and process.stdin is not None:
            request = json.dumps(
                {"id": secrets.token_hex(16), "type": "shutdown"},
                separators=(",", ":"),
            ).encode("utf-8") + b"\n"
            try:
                process.stdin.write(request)
                process.stdin.flush()
                process.wait(timeout=2)
            except (BrokenPipeError, OSError, ValueError, subprocess.TimeoutExpired):
                terminate_owned_child(process)
        self.process = None
        self.ready = None
        self._stdout_buffer.clear()
        thread = self._stderr_thread
        self._stderr_thread = None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1)
        self._close_process_streams(process)


def active_worker(executable: str) -> WhisperKitWorker:
    global _ACTIVE_WORKER
    if _ACTIVE_WORKER is None or _ACTIVE_WORKER.executable != str(executable):
        if _ACTIVE_WORKER is not None:
            _ACTIVE_WORKER.shutdown()
        _ACTIVE_WORKER = WhisperKitWorker(executable)
    return _ACTIVE_WORKER


def reset_worker(reason: str) -> None:
    global _ACTIVE_WORKER
    worker = _ACTIVE_WORKER
    _ACTIVE_WORKER = None
    if worker is not None:
        worker.terminate(reason)


def shutdown_worker() -> None:
    global _ACTIVE_WORKER
    worker = _ACTIVE_WORKER
    _ACTIVE_WORKER = None
    if worker is not None:
        worker.shutdown()


def format_transcript_timestamp(raw_seconds: object) -> str:
    if not isinstance(raw_seconds, (int, float)) or isinstance(
        raw_seconds,
        bool,
    ):
        raise ValueError(f"invalid timestamp value: {raw_seconds!r}")
    seconds = max(0.0, float(raw_seconds))
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return (
        f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}."
        f"{milliseconds:03d}"
    )


def format_timestamp_marker(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, whole_seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d}"


def render_timed_transcript(
    phrases: list[TimedPhrase],
    interval_seconds: int = DEFAULT_TIMESTAMP_INTERVAL_SECONDS,
) -> tuple[str | None, str | None]:
    """Render engine-neutral timed phrases in the established text format."""

    if interval_seconds < 0:
        return None, "timestamp interval must be non-negative"
    if interval_seconds == 0:
        transcript = "\n".join(
            f"[{format_transcript_timestamp(phrase.start)} --> "
            f"{format_transcript_timestamp(phrase.end)}] {phrase.text}"
            for phrase in phrases
        )
    else:
        buckets: dict[int, list[str]] = {}
        for phrase in phrases:
            bucket = int(phrase.start // interval_seconds) * interval_seconds
            buckets.setdefault(bucket, []).append(phrase.text)
        transcript = "\n\n".join(
            f"[{format_timestamp_marker(bucket)}]\n{' '.join(buckets[bucket])}"
            for bucket in sorted(buckets)
        )
    if not transcript.strip():
        return None, "engine produced an empty timestamped transcript"
    return transcript, None


def phrases_from_segments(segments: object) -> list[TimedPhrase]:
    """Convert worker segments into the renderer's engine-neutral phrases.

    The accepted shape and the clamping below match what the retired
    report-file reader did, so the rendered byte-for-byte transcript format is
    unchanged.
    """

    if not isinstance(segments, list):
        raise ValueError("worker result contains no segment list")
    parsed: list[TimedPhrase] = []
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError("segment is not an object")
        text = segment.get("text")
        if not isinstance(text, str):
            raise ValueError("segment text is missing")
        text = text.strip()
        if not text:
            continue
        raw_start = segment.get("start")
        raw_end = segment.get("end")
        if (
            isinstance(raw_start, bool)
            or not isinstance(raw_start, (int, float))
            or isinstance(raw_end, bool)
            or not isinstance(raw_end, (int, float))
        ):
            raise ValueError("segment timestamp is missing")
        start = float(raw_start)
        end = float(raw_end)
        if not math.isfinite(start) or not math.isfinite(end):
            raise ValueError("segment timestamp is not finite")
        parsed.append(TimedPhrase(max(0.0, start), max(0.0, end), text))
    return parsed


def timestamped_transcript(
    segments: object,
    interval_seconds: int = DEFAULT_TIMESTAMP_INTERVAL_SECONDS,
) -> tuple[str | None, str | None]:
    if interval_seconds < 0:
        return None, "timestamp interval must be non-negative"
    try:
        parsed_segments = phrases_from_segments(segments)
    except ValueError as exc:
        return None, f"invalid WhisperKit segments: {exc}"
    return render_timed_transcript(parsed_segments, interval_seconds)


def validate_worker_result(
    frame: dict[str, object],
) -> tuple[str, float, float, object]:
    text = frame.get("text")
    segments = frame.get("segments")
    raw_duration = frame.get("duration")
    raw_processing_time = frame.get("processing_time")
    if not isinstance(text, str):
        raise ValueError("worker result text is not a string")
    if not isinstance(segments, list):
        raise ValueError("worker result segments is not a list")
    if (
        isinstance(raw_duration, bool)
        or not isinstance(raw_duration, (int, float))
    ):
        raise ValueError("worker result duration is not numeric")
    duration = float(raw_duration)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("worker result duration must be finite and positive")
    if (
        isinstance(raw_processing_time, bool)
        or not isinstance(raw_processing_time, (int, float))
    ):
        raise ValueError("worker result processing_time is not numeric")
    processing_time = float(raw_processing_time)
    if not math.isfinite(processing_time) or processing_time < 0:
        raise ValueError(
            "worker result processing_time must be finite and non-negative"
        )
    return text, duration, processing_time, segments


def _clear_transcription_failures() -> None:
    global _CONSECUTIVE_TRANSCRIPTION_FAILURES
    _CONSECUTIVE_TRANSCRIPTION_FAILURES = 0


def _record_transcription_failure(error: str) -> str:
    """Count one failed file and stop the run once failures stop being isolated.

    Returning the error keeps call sites terse; raising happens only at the
    threshold, so ordinary one-off failures still just fail their own file.
    """

    global _CONSECUTIVE_TRANSCRIPTION_FAILURES
    _CONSECUTIVE_TRANSCRIPTION_FAILURES += 1
    if _CONSECUTIVE_TRANSCRIPTION_FAILURES >= MAX_CONSECUTIVE_TRANSCRIPTION_FAILURES:
        count = _CONSECUTIVE_TRANSCRIPTION_FAILURES
        _CONSECUTIVE_TRANSCRIPTION_FAILURES = 0
        reset_worker("consecutive transcription failures")
        raise WorkerHealthError(
            f"{count} files failed in a row; last error: {error}"
        )
    return error


def run_whisperkit_worker(
    executable: str,
    audio_path: Path,
    options: TranscriptionOptions,
    workspace: Path,
    review_log: ReviewLog | None = None,
    source_path: Path | None = None,
) -> tuple[str | None, str | None]:
    """Run one request through the persistent WhisperKit worker with retries."""

    del workspace
    global _LAST_ENGINE_METRICS
    _LAST_ENGINE_METRICS = None
    attempts = options.retries + 1
    last_error = "WhisperKit worker did not run"
    model_load_failures = 0
    for attempt in range(1, attempts + 1):
        worker = active_worker(executable)
        if worker.completed_requests >= WORKER_RECYCLE_REQUEST_LIMIT:
            reset_worker(
                f"scheduled recycle after {worker.completed_requests} requests"
            )
            worker = active_worker(executable)
        started = time.monotonic()
        try:
            frame = worker.transcribe(
                audio_path,
                None,
                language=options.language,
                timestamps=options.timestamps,
            )
        except WorkerRequestTimeout as exc:
            last_error = str(exc)
            reset_worker("request timeout")
            if review_log is not None:
                review_log.record(
                    "WHISPERKIT TIMEOUT",
                    source_path or audio_path,
                    f"{last_error}; attempt={attempt}/{attempts}",
                )
        except WorkerModelLoadError as exc:
            last_error = str(exc)
            model_load_failures += 1
            reset_worker("mid-run model load failure")
            if model_load_failures >= 2:
                return None, last_error
        except WorkerProtocolError as exc:
            last_error = str(exc)
            reset_worker("protocol violation or crash")
        except KeyboardInterrupt:
            reset_worker("keyboard interrupt")
            raise
        else:
            if frame.get("type") == "error":
                code = frame.get("code")
                message = frame.get("message")
                last_error = (
                    message
                    if isinstance(message, str) and message
                    else f"WhisperKit worker error {code!r}"
                )
                if code == "invalid_audio" or frame.get("retriable") is not True:
                    return None, _record_transcription_failure(last_error)
                if code == "model_load_failed":
                    model_load_failures += 1
                    reset_worker("mid-run model load failure")
                    if model_load_failures >= 2:
                        return None, _record_transcription_failure(last_error)
                else:
                    # Core ML resource exhaustion surfaces here (for example a
                    # failed IOSurface-backed allocation).  Retrying into the
                    # same resident model just reproduces it.
                    reset_worker(f"retriable worker error: {code}")
            else:
                try:
                    (
                        text,
                        duration,
                        worker_processing_time,
                        segments,
                    ) = validate_worker_result(frame)
                    if options.timestamps:
                        transcript, render_error = timestamped_transcript(
                            segments,
                            options.timestamp_interval_seconds,
                        )
                        if render_error:
                            raise ValueError(render_error)
                        assert transcript is not None
                    else:
                        transcript = text.strip()
                        if not transcript:
                            raise ValueError(
                                "WhisperKit produced an empty transcript"
                            )
                except ValueError as exc:
                    # A worker whose resident model has degraded returns empty
                    # output for every file.  Treat that as the worker being
                    # sick: restart it and retry before blaming the file.
                    last_error = f"invalid WhisperKit result: {exc}"
                    reset_worker("empty or malformed result")
                    if attempt < attempts:
                        print(
                            f"WHISPERKIT RETRY next={attempt + 1}/{attempts}: "
                            f"{last_error}",
                            file=sys.stderr,
                            flush=True,
                        )
                        continue
                    return None, _record_transcription_failure(
                        f"{last_error}; attempts={attempts}"
                    )
                elapsed = time.monotonic() - started
                _LAST_ENGINE_METRICS = EngineMetrics(duration, elapsed)
                _record_run_event(
                    "WHISPERKIT TIMING",
                    f"source={source_path or audio_path} "
                    f"worker_seconds={worker_processing_time:.3f} "
                    f"wall_seconds={elapsed:.3f} audio_seconds={duration:.3f}",
                )
                _clear_transcription_failures()
                return transcript, None

        if attempt < attempts:
            print(
                f"WHISPERKIT RETRY next={attempt + 1}/{attempts}: {last_error}",
                file=sys.stderr,
                flush=True,
            )
    return None, _record_transcription_failure(
        f"{last_error}; attempts={attempts}"
    )


def exclusive_rename(
    directory_fd: int, source_name: str, destination_name: str
) -> bool:
    """Use macOS RENAME_EXCL; return False when it is unsupported."""

    if sys.platform != "darwin":
        return False
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameatx_np = libc.renameatx_np
    except AttributeError:
        return False
    renameatx_np.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameatx_np.restype = ctypes.c_int
    result = renameatx_np(
        directory_fd,
        os.fsencode(source_name),
        directory_fd,
        os.fsencode(destination_name),
        RENAME_EXCL,
    )
    if result == 0:
        return True
    error_number = ctypes.get_errno()
    if error_number in (errno.ENOSYS, errno.ENOTSUP, errno.EINVAL):
        return False
    if error_number == errno.EEXIST:
        raise FileExistsError(error_number, os.strerror(error_number), destination_name)
    raise OSError(error_number, os.strerror(error_number), destination_name)


def transcript_payload(transcript: str) -> bytes:
    payload = transcript.encode("utf-8")
    if payload and not payload.endswith(b"\n"):
        payload += b"\n"
    return payload


def write_payload_and_sync(file_descriptor: int, payload: bytes) -> None:
    """Write, flush, fsync, and close a descriptor, preserving the first error."""

    try:
        output = os.fdopen(file_descriptor, "wb", closefd=True)
    except BaseException:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        raise

    operation_error: BaseException | None = None
    try:
        written = output.write(payload)
        if written != len(payload):
            raise OSError(
                errno.EIO,
                f"short transcript write: wrote {written} of {len(payload)} bytes",
            )
        output.flush()
        os.fsync(output.fileno())
    except BaseException as exc:
        operation_error = exc

    try:
        output.close()
    except BaseException as exc:
        if operation_error is None:
            operation_error = exc
        elif hasattr(operation_error, "add_note"):
            operation_error.add_note(f"closing the transcript also failed: {exc}")

    if operation_error is not None:
        raise operation_error


def unlink_part(parent_fd: int, part_name: str) -> str | None:
    try:
        os.unlink(part_name, dir_fd=parent_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        return f"could not remove process-owned part file {part_name}: {exc}"
    return None


def cleanup_created_destination(
    parent_fd: int,
    destination_name: str,
    destination_path: Path,
    created_identity: FileIdentity | None,
) -> str | None:
    """Remove only the destination inode created by this process."""

    if created_identity is None:
        return (
            "could not prove the partial destination's filesystem identity; "
            f"left untouched for manual review: {destination_path}"
        )
    try:
        current_stat = os.stat(
            destination_name,
            dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None
    except OSError as exc:
        return (
            "could not inspect the partial destination before cleanup "
            f"({exc}); left untouched for manual review: {destination_path}"
        )

    current_identity = FileIdentity(current_stat.st_dev, current_stat.st_ino)
    if (
        not stat.S_ISREG(current_stat.st_mode)
        or current_identity != created_identity
    ):
        return (
            "the partial destination's filesystem identity could not be "
            f"verified; left untouched for manual review: {destination_path}"
        )
    try:
        os.unlink(destination_name, dir_fd=parent_fd)
    except OSError as exc:
        return (
            f"could not remove the verified partial destination ({exc}); "
            f"left for manual review: {destination_path}"
        )
    return None


def failure_with_cleanup(
    operation: str,
    error: BaseException,
    cleanup_error: str | None,
) -> InstallResult:
    detail = f"{operation}: {error}"
    if cleanup_error:
        detail = f"{detail}; {cleanup_error}"
    return InstallResult.failed(detail)


def add_cleanup_note(error: BaseException, cleanup_error: str | None) -> None:
    if cleanup_error and hasattr(error, "add_note"):
        error.add_note(cleanup_error)


def install_transcript(
    parent_fd: int,
    destination_name: str,
    transcript: str,
    *,
    destination_path: Path | None = None,
    overwrite: bool = False,
    overwrite_empty: bool = False,
    expected_snapshot: TranscriptSnapshot | None = None,
) -> InstallResult:
    if destination_path is None:
        destination_path = Path(destination_name)
    if not transcript.strip():
        return InstallResult.failed(
            "engine produced an empty transcript; destination was not changed"
        )
    payload = transcript_payload(transcript)
    part_name = (
        f".{destination_name}.{os.getpid()}.{secrets.token_hex(8)}.part"
    )
    open_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        open_flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        open_flags |= os.O_NOFOLLOW

    try:
        part_fd = os.open(part_name, open_flags, 0o600, dir_fd=parent_fd)
    except OSError as exc:
        return InstallResult.failed(
            f"could not create process-owned part file {part_name}: {exc}"
        )

    try:
        write_payload_and_sync(part_fd, payload)
    except BaseException as exc:
        cleanup_error = unlink_part(parent_fd, part_name)
        if isinstance(exc, Exception):
            return failure_with_cleanup(
                "could not write and sync process-owned part file",
                exc,
                cleanup_error,
            )
        add_cleanup_note(exc, cleanup_error)
        raise

    if overwrite or overwrite_empty or expected_snapshot is not None:
        if expected_snapshot is not None:
            try:
                _payload, current_snapshot = read_regular_file_snapshot(
                    destination_name,
                    dir_fd=parent_fd,
                )
            except OSError as exc:
                cleanup_error = unlink_part(parent_fd, part_name)
                detail = (
                    "timestamp-upgrade destination could not be verified "
                    "unchanged; existing path was not changed: "
                    f"{destination_path} ({exc})"
                )
                if cleanup_error:
                    return InstallResult.failed(f"{detail}; {cleanup_error}")
                return InstallResult.skipped(detail)
            if current_snapshot != expected_snapshot:
                cleanup_error = unlink_part(parent_fd, part_name)
                detail = (
                    "timestamp-upgrade destination changed after preflight; "
                    f"existing bytes were not changed: {destination_path}"
                )
                if cleanup_error:
                    return InstallResult.failed(f"{detail}; {cleanup_error}")
                return InstallResult.skipped(detail)
            try:
                destination_stat = os.stat(
                    destination_name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except OSError as exc:
                cleanup_error = unlink_part(parent_fd, part_name)
                detail = (
                    "timestamp-upgrade destination changed after verification; "
                    f"existing path was not changed: {destination_path} ({exc})"
                )
                if cleanup_error:
                    return InstallResult.failed(f"{detail}; {cleanup_error}")
                return InstallResult.skipped(detail)
            current_path_identity = (
                destination_stat.st_dev,
                destination_stat.st_ino,
                destination_stat.st_size,
                destination_stat.st_mtime_ns,
                destination_stat.st_ctime_ns,
            )
            expected_path_identity = (
                expected_snapshot.device,
                expected_snapshot.inode,
                expected_snapshot.size,
                expected_snapshot.modified_ns,
                expected_snapshot.changed_ns,
            )
            if (
                not stat.S_ISREG(destination_stat.st_mode)
                or current_path_identity != expected_path_identity
            ):
                cleanup_error = unlink_part(parent_fd, part_name)
                detail = (
                    "timestamp-upgrade destination changed after verification; "
                    f"existing bytes were not changed: {destination_path}"
                )
                if cleanup_error:
                    return InstallResult.failed(f"{detail}; {cleanup_error}")
                return InstallResult.skipped(detail)
        else:
            try:
                destination_stat = os.stat(
                    destination_name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                destination_stat = None
            except BaseException as exc:
                cleanup_error = unlink_part(parent_fd, part_name)
                if isinstance(exc, Exception):
                    return failure_with_cleanup(
                        "could not inspect overwrite destination",
                        exc,
                        cleanup_error,
                    )
                add_cleanup_note(exc, cleanup_error)
                raise
            if destination_stat is not None and not stat.S_ISREG(
                destination_stat.st_mode
            ):
                cleanup_error = unlink_part(parent_fd, part_name)
                detail = (
                    "overwrite destination is not a regular file; existing "
                    f"path was not changed: {destination_path}"
                )
                if cleanup_error:
                    detail = f"{detail}; {cleanup_error}"
                return InstallResult.failed(detail)
            if (
                overwrite_empty
                and destination_stat is not None
                and destination_stat.st_size != 0
            ):
                cleanup_error = unlink_part(parent_fd, part_name)
                detail = (
                    "destination is no longer empty; existing bytes were not "
                    f"changed: {destination_path}"
                )
                if cleanup_error:
                    return InstallResult.failed(f"{detail}; {cleanup_error}")
                return InstallResult.skipped(detail)
        try:
            os.replace(
                part_name,
                destination_name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
        except BaseException as exc:
            cleanup_error = unlink_part(parent_fd, part_name)
            if isinstance(exc, Exception):
                return failure_with_cleanup(
                    "atomic transcript overwrite failed; existing path was "
                    "not changed",
                    exc,
                    cleanup_error,
                )
            add_cleanup_note(exc, cleanup_error)
            raise
        return InstallResult.installed()

    try:
        renamed = exclusive_rename(parent_fd, part_name, destination_name)
    except FileExistsError:
        cleanup_error = unlink_part(parent_fd, part_name)
        if cleanup_error:
            return InstallResult.failed(cleanup_error)
        return InstallResult.skipped(
            "destination appeared during exclusive rename; "
            "existing path was not changed"
        )
    except BaseException as exc:
        cleanup_error = unlink_part(parent_fd, part_name)
        if isinstance(exc, Exception):
            return failure_with_cleanup(
                "exclusive transcript rename failed",
                exc,
                cleanup_error,
            )
        add_cleanup_note(exc, cleanup_error)
        raise

    if renamed:
        return InstallResult.installed()

    part_cleanup_error = unlink_part(parent_fd, part_name)
    if part_cleanup_error:
        return InstallResult.failed(part_cleanup_error)

    try:
        destination_fd = os.open(
            destination_name,
            open_flags,
            0o600,
            dir_fd=parent_fd,
        )
    except FileExistsError:
        return InstallResult.skipped(
            "destination appeared during exclusive creation; "
            "existing path was not changed"
        )
    except OSError as exc:
        return InstallResult.failed(
            f"could not exclusively create transcript destination: {exc}"
        )

    try:
        destination_stat = os.fstat(destination_fd)
    except BaseException as exc:
        try:
            os.close(destination_fd)
        except OSError as close_error:
            if hasattr(exc, "add_note"):
                exc.add_note(
                    f"closing the unverified destination also failed: {close_error}"
                )
        cleanup_error = cleanup_created_destination(
            parent_fd,
            destination_name,
            destination_path,
            None,
        )
        if isinstance(exc, Exception):
            return failure_with_cleanup(
                "could not inspect the newly created transcript destination",
                exc,
                cleanup_error,
            )
        add_cleanup_note(exc, cleanup_error)
        raise

    created_identity = FileIdentity(
        destination_stat.st_dev,
        destination_stat.st_ino,
    )
    if not stat.S_ISREG(destination_stat.st_mode):
        error = OSError(
            errno.EINVAL,
            "exclusive transcript destination is not a regular file",
        )
        try:
            os.close(destination_fd)
        except OSError as close_error:
            if hasattr(error, "add_note"):
                error.add_note(
                    f"closing the invalid destination also failed: {close_error}"
                )
        return failure_with_cleanup(
            "could not validate the newly created transcript destination",
            error,
            cleanup_created_destination(
                parent_fd,
                destination_name,
                destination_path,
                created_identity,
            ),
        )

    try:
        write_payload_and_sync(destination_fd, payload)
    except BaseException as exc:
        cleanup_error = cleanup_created_destination(
            parent_fd,
            destination_name,
            destination_path,
            created_identity,
        )
        if isinstance(exc, Exception):
            return failure_with_cleanup(
                "could not write, sync, and close transcript destination",
                exc,
                cleanup_error,
            )
        add_cleanup_note(exc, cleanup_error)
        raise
    return InstallResult.installed()


def transcribe_item(
    item: WorkItem,
    programs: Programs,
    parent_fd: int,
    options: TranscriptionOptions,
    review_log: ReviewLog | None = None,
) -> InstallResult:
    effective_options = effective_options_for_course(options, item.course)
    try:
        with tempfile.TemporaryDirectory(
            prefix="batch-transcribe-courses-"
        ) as temporary:
            workspace = Path(temporary)
            audio_path = item.media
            if item.input_kind != "direct":
                wav_path = Path(temporary) / "audio.wav"
                try:
                    media_size = item.media.stat().st_size
                except OSError:
                    media_size = 0
                extract_timeout = effective_options.extract_timeout_seconds
                if extract_timeout is None:
                    extract_timeout = max(1800, 600 + media_size // 250_000)
                error = extract_audio(
                    item.media,
                    wav_path,
                    programs.ffmpeg,
                    extract_timeout,
                    review_log,
                    effective_options.extract_retries,
                )
                if error:
                    return InstallResult.failed(
                        f"audio extraction failed: {error}"
                    )
                audio_path = wav_path
            if programs.worker is None:
                return InstallResult.failed(
                    "WhisperKit worker was not resolved; destination was not changed"
                )
            transcript, error = run_whisperkit_worker(
                programs.worker,
                audio_path,
                effective_options,
                workspace,
                review_log,
                item.media,
            )
    except OSError as exc:
        return InstallResult.failed(
            f"could not create temporary audio workspace: {exc}"
        )
    if error:
        return InstallResult.failed(error)
    assert transcript is not None
    if (
        options.upgrade_timestamps
        and transcript_needs_timestamp_upgrade(transcript.encode("utf-8"))
    ):
        return InstallResult.failed(
            "engine produced no clean leading timestamp marker; "
            "destination was not changed"
        )
    return install_transcript(
        parent_fd,
        item.relative_output.name,
        transcript,
        destination_path=item.course.transcript_root / item.relative_output,
        overwrite=options.overwrite,
        overwrite_empty=(
            options.overwrite_empty and item.existing_empty
        ),
        expected_snapshot=(
            item.transcript_snapshot
            if (
                options.upgrade_timestamps
                and item.existing
                and item.timestamp_upgrade_needed
            )
            else None
        ),
    )


def combine_summaries(summaries: dict[Path, CourseSummary]) -> CourseSummary:
    combined = CourseSummary()
    for summary in summaries.values():
        combined.discovered += summary.discovered
        combined.attempted += summary.attempted
        combined.succeeded += summary.succeeded
        combined.skipped += summary.skipped
        combined.limited += summary.limited
        combined.failed += summary.failed
        combined.would_transcribe += summary.would_transcribe
    return combined


def process_item(
    item: WorkItem,
    programs: Programs,
    options: TranscriptionOptions,
    summary: CourseSummary,
    prefix: str,
    review_log: ReviewLog | None = None,
) -> None:
    """Process one selected item, including all volume and install retries."""

    if item.existing and options.upgrade_timestamps:
        action = "UPGRADE-TIMESTAMPS"
    elif item.existing_empty and options.overwrite_empty:
        action = "REPAIR-EMPTY"
    elif item.existing:
        action = "OVERWRITE"
    else:
        action = "TRANSCRIBE"
    print(
        f"{prefix} {action} "
        f"({item.input_kind}) {item.relative_media} -> "
        f"transcripts/{item.relative_output}",
        flush=True,
    )

    source_error = revalidate_media(item)
    if source_error:
        volume = volume_root_for(item.media)
        if not volume_is_live(volume):
            if not wait_for_volume(volume, review_log, _ACTIVE_RUN_LOG):
                raise VolumeUnavailable(volume, source_error)
            source_error = revalidate_media(item)
            if source_error is None:
                _record_run_event("RETRY", f"source={item.media} after volume restore")
        if source_error is None:
            pass
        else:
            summary.failed += 1
            if review_log is not None:
                review_log.record("SOURCE CHANGED", item.media, source_error)
            _record_run_event(
                "FAIL",
                f"source={item.media} reason={source_error}",
                issue=True,
            )
            print(
                f"{prefix} FAIL {item.relative_media}: {source_error}",
                file=sys.stderr,
                flush=True,
            )
            return

    parent_fd: int | None = None
    result: InstallResult | None = None
    for output_attempt in range(2):
        try:
            parent_fd = open_safe_output_parent(item)
            if (
                not item_can_replace_existing(item, options)
                and destination_exists(parent_fd, item.relative_output.name)
            ):
                summary.skipped += 1
                print(
                    f"{prefix} SKIP destination now exists "
                    f"transcripts/{item.relative_output}",
                    flush=True,
                )
                result = InstallResult.skipped("destination now exists")
                break
            summary.attempted += 1
            result = transcribe_item(
                item,
                programs,
                parent_fd,
                options,
                review_log,
            )
            break
        except OSError as exc:
            volume = volume_root_for(item.media)
            if output_attempt == 0 and not volume_is_live(volume):
                if wait_for_volume(volume, review_log, _ACTIVE_RUN_LOG):
                    _record_run_event("RETRY", f"item={item.media} after volume restore")
                    continue
                raise VolumeUnavailable(volume, str(exc)) from exc
            if not volume_is_live(volume):
                raise VolumeUnavailable(volume, str(exc)) from exc
            result = InstallResult.failed(
                f"unsafe output path or directory creation failed: {exc}"
            )
            break
        finally:
            if parent_fd is not None:
                os.close(parent_fd)
                parent_fd = None
    assert result is not None

    if result.status is InstallStatus.FAILED:
        summary.failed += 1
        if review_log is not None:
            review_log.record(
                "TRANSCRIPTION FAILURE",
                item.media,
                result.detail or "unknown failure",
            )
        print(
            f"{prefix} FAIL {item.relative_media}: {result.detail}",
            file=sys.stderr,
            flush=True,
        )
        _record_run_event(
            "FAIL",
            f"item={item.media} reason={result.detail or 'unknown failure'}",
            issue=True,
        )
    elif result.status is InstallStatus.SKIPPED:
        summary.skipped += 1
        print(
            f"{prefix} SKIP destination now exists "
            f"transcripts/{item.relative_output}: {result.detail}",
            flush=True,
        )
        _record_run_event(
            "SKIP",
            f"item={item.media} reason={result.detail or 'race'}",
        )
    else:
        summary.succeeded += 1
        print(
            f"{prefix} OK transcripts/{item.relative_output}",
            flush=True,
        )
        metrics = _LAST_ENGINE_METRICS
        timing = ""
        if metrics is not None:
            rtf = metrics.rtf
            timing = (
                f" engine=whisperkit seconds={metrics.engine_seconds:.3f} "
                + (f"rtf={rtf:.3f}" if rtf is not None else "rtf=unknown")
                + (
                    f" audio_seconds={metrics.audio_seconds:.3f}"
                    if metrics.audio_seconds is not None
                    else ""
                )
            )
        _record_run_event(
            "OK",
            f"item={item.media} output=transcripts/{item.relative_output}{timing}",
        )


def _open_stream_output_directory(output_root_fd: int, relative_directory: Path) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    component = relative_directory.as_posix() or "."
    return os.open(component, flags, dir_fd=output_root_fd)


def stream_course(
    course: Course,
    programs: Programs,
    options: TranscriptionOptions,
    remaining: int | None,
    title: ProcessTitle | None,
    review_log: ReviewLog | None,
    course_label: str,
) -> StreamResult:
    """Discover and process one course without a whole-course preflight."""

    transcript_errors = validate_transcript_root(course)
    if transcript_errors:
        raise PreflightError(transcript_errors)

    summary = CourseSummary()
    consumed = 0
    limited = False
    failed = False
    collision_sources: dict[str, Path] = {}
    output_root_fd: int | None = None

    def raise_if_volume_unavailable(exc: OSError, path: Path) -> None:
        volume = volume_root_for(path)
        if not volume_is_live(volume):
            raise VolumeUnavailable(volume, str(exc)) from exc

    try:
        try:
            output_root_fd = open_safe_output_root(course)
        except OSError as exc:
            volume = volume_root_for(course.root)
            if not volume_is_live(volume):
                if wait_for_volume(volume, review_log, _ACTIVE_RUN_LOG):
                    try:
                        output_root_fd = open_safe_output_root(course)
                    except OSError as retry_exc:
                        raise VolumeUnavailable(volume, str(retry_exc)) from retry_exc
                else:
                    raise VolumeUnavailable(volume, str(exc)) from exc
            else:
                detail = f"could not create course output root: {exc}"
                summary.failed += 1
                failed = True
                if review_log is not None:
                    review_log.record("COURSE OUTPUT ROOT", course.root, detail)
                _record_run_event(
                    "FAIL", f"course={course.root} {detail}", issue=True
                )
                print(f"FAIL course={course.root}: {detail}", file=sys.stderr, flush=True)
                return summary, consumed, limited, failed

        assert output_root_fd is not None
        allowed_extensions = (
            VIDEO_EXTENSIONS if is_music_tree(course.root) else MEDIA_EXTENSIONS
        )
        discovery_errors: list[str] = []
        stop_walk = False

        def onerror(error: OSError) -> None:
            raise_if_volume_unavailable(error, course.root)
            discovery_errors.append(
                f"discovery failed at {error.filename or course.root}: "
                f"{error.strerror or error}"
            )

        try:
            walker = os.walk(
                course.root,
                topdown=True,
                followlinks=False,
                onerror=onerror,
            )
            for directory, dirnames, filenames in walker:
                directory_path = Path(directory)
                if course.ignore_omega_directories:
                    dirnames[:] = [
                        name
                        for name in dirnames
                        if not is_omega_directory_name(name)
                    ]
                if directory_path == course.root:
                    dirnames[:] = [
                        name
                        for name in dirnames
                        if name.casefold() != "transcripts"
                    ]
                elif is_source_repository(directory_path, filenames):
                    # Bundled source repositories are pruned rather than
                    # transcribed.  This is routine, so it is logged as
                    # information and never counted as a course failure.
                    dirnames[:] = []
                    try:
                        relative = directory_path.relative_to(
                            course.root
                        ).as_posix()
                    except ValueError:
                        relative = str(directory_path)
                    _record_run_event(
                        "SOURCE TREE PRUNED",
                        f"course={course.root} directory={relative}",
                    )
                    print(
                        f"SOURCE TREE PRUNED course={course.name} "
                        f"directory={relative}",
                        flush=True,
                    )
                    continue
                sort_key = lambda name: (
                    unicodedata.normalize("NFC", name).casefold(),
                    name,
                )
                dirnames.sort(key=sort_key)
                filenames.sort(key=sort_key)

                try:
                    relative_directory = directory_path.relative_to(course.root)
                except ValueError:
                    discovery_errors.append(
                        f"discovered directory escapes course root: {directory_path}"
                    )
                    continue
                try:
                    mirrored_fd = _open_stream_output_directory(
                        output_root_fd,
                        relative_directory,
                    )
                    mirrored_unusable = False
                except FileNotFoundError:
                    mirrored_fd = None
                    mirrored_unusable = False
                except OSError as exc:
                    raise_if_volume_unavailable(exc, directory_path)
                    mirrored_fd = None
                    mirrored_unusable = True
                    destination = course.transcript_root / relative_directory
                    if review_log is not None:
                        review_log.record(
                            "OUTPUT DESTINATION",
                            destination,
                            f"could not inspect mirrored output directory: {exc}",
                        )

                try:
                    for filename in filenames:
                        media = directory_path / filename
                        if not media_path_is_eligible(media, allowed_extensions):
                            continue
                        try:
                            media_stat = media.lstat()
                        except OSError as exc:
                            raise_if_volume_unavailable(exc, media)
                            discovery_errors.append(
                                f"could not inspect media candidate {media}: {exc}"
                            )
                            continue
                        if stat.S_ISLNK(media_stat.st_mode):
                            continue
                        if not stat.S_ISREG(media_stat.st_mode):
                            continue
                        try:
                            relative_media = media.relative_to(course.root)
                        except ValueError:
                            discovery_errors.append(
                                f"discovered media escapes course root: {media}"
                            )
                            continue
                        relative_output = relative_media.with_suffix(".txt")
                        destination = course.transcript_root / relative_output
                        try:
                            destination.relative_to(course.transcript_root)
                        except ValueError:
                            discovery_errors.append(
                                f"transcript destination escapes course boundary: {destination}"
                            )
                            continue

                        item = WorkItem(
                            course=course,
                            media=media,
                            relative_media=relative_media,
                            relative_output=relative_output,
                            identity=identity_from_stat(media_stat),
                            input_kind=(
                                "direct"
                                if media.suffix.casefold() in DIRECT_AUDIO_EXTENSIONS
                                else "ffmpeg"
                            ),
                        )
                        summary.discovered += 1
                        key = collision_key(item)
                        first_source = collision_sources.get(key)
                        if first_source is not None:
                            if review_log is not None:
                                review_log.record(
                                    "OUTPUT COLLISION",
                                    destination,
                                    f"{first_source} and {item.relative_media} both map to "
                                    f"transcripts/{item.relative_output}",
                                )
                            summary.skipped += 1
                            continue
                        collision_sources[key] = item.relative_media

                        if mirrored_unusable:
                            summary.skipped += 1
                            continue

                        if mirrored_fd is None:
                            exists = False
                            empty = False
                        else:
                            try:
                                exists = destination_exists(
                                    mirrored_fd,
                                    item.relative_output.name,
                                )
                            except OSError as exc:
                                raise_if_volume_unavailable(exc, destination)
                                if review_log is not None:
                                    review_log.record(
                                        "OUTPUT DESTINATION",
                                        destination,
                                        f"could not inspect transcript destination: {exc}",
                                    )
                                summary.skipped += 1
                                continue
                            empty = False
                            if exists:
                                try:
                                    destination_stat = os.stat(
                                        item.relative_output.name,
                                        dir_fd=mirrored_fd,
                                        follow_symlinks=False,
                                    )
                                except FileNotFoundError:
                                    exists = False
                                except OSError as exc:
                                    raise_if_volume_unavailable(exc, destination)
                                    if review_log is not None:
                                        review_log.record(
                                            "OUTPUT DESTINATION",
                                            destination,
                                            f"could not inspect transcript destination: {exc}",
                                        )
                                    summary.skipped += 1
                                    continue
                                else:
                                    if stat.S_ISLNK(destination_stat.st_mode):
                                        if review_log is not None:
                                            review_log.record(
                                                "OUTPUT DESTINATION",
                                                destination,
                                                "transcript destination must not be a symlink",
                                            )
                                        summary.skipped += 1
                                        continue
                                    if not stat.S_ISREG(destination_stat.st_mode):
                                        if review_log is not None:
                                            review_log.record(
                                                "OUTPUT DESTINATION",
                                                destination,
                                                "transcript destination is not a regular file",
                                            )
                                        summary.skipped += 1
                                        continue
                                    empty = destination_stat.st_size == 0
                        item.existing = exists
                        item.existing_empty = empty

                        if options.upgrade_timestamps:
                            if not exists:
                                item.timestamp_upgrade_needed = True
                            elif mirrored_fd is not None:
                                try:
                                    payload, snapshot = read_regular_file_snapshot(
                                        item.relative_output.name,
                                        dir_fd=mirrored_fd,
                                    )
                                except FileNotFoundError:
                                    item.existing = False
                                    item.existing_empty = False
                                    item.timestamp_upgrade_needed = True
                                except OSError as exc:
                                    raise_if_volume_unavailable(exc, destination)
                                    if review_log is not None:
                                        review_log.record(
                                            "TIMESTAMP UPGRADE",
                                            destination,
                                            f"could not inspect transcript contents: {exc}",
                                        )
                                    summary.skipped += 1
                                    continue
                                else:
                                    item.existing_empty = snapshot.size == 0
                                    item.timestamp_upgrade_needed = (
                                        transcript_needs_timestamp_upgrade(payload)
                                    )
                                    item.transcript_snapshot = snapshot

                        if not item_is_eligible(item, options):
                            summary.skipped += 1
                            continue
                        if remaining is not None and consumed >= remaining:
                            limited = True
                            stop_walk = True
                            break

                        consumed += 1
                        set_title(
                            title,
                            f"batch-transcribe-courses [{course_label}] "
                            f"{course_progress_label(course)} "
                            f":: {item.relative_media}",
                        )
                        process_item(
                            item,
                            programs,
                            options,
                            summary,
                            f"[{course.name} {consumed}]",
                            review_log,
                        )
                    if stop_walk:
                        break
                finally:
                    if mirrored_fd is not None:
                        os.close(mirrored_fd)
        except (OSError, RuntimeError) as exc:
            discovery_errors.append(f"discovery failed at {course.root}: {exc}")

        if discovery_errors:
            failed = True
            for error in discovery_errors:
                if review_log is not None:
                    review_log.record("COURSE PREFLIGHT", course.root, error)
                _record_run_event("FAIL", f"course={course.root} {error}", issue=True)
    finally:
        if output_root_fd is not None:
            os.close(output_root_fd)

    limited_label = "paused" if limited else str(summary.limited)
    print(
        f"Course summary [{course.name}]: discovered={summary.discovered} "
        f"attempted={summary.attempted} succeeded={summary.succeeded} "
        f"skipped={summary.skipped} limited={limited_label} "
        f"failed={summary.failed}",
        flush=True,
    )
    _record_run_event(
        "COURSE SUMMARY",
        f"course={course.root} discovered={summary.discovered} attempted={summary.attempted} "
        f"succeeded={summary.succeeded} skipped={summary.skipped} limited={limited_label} failed={summary.failed}",
    )
    if summary.failed:
        failed = True
    return summary, consumed, limited, failed


def run_live(
    preflight: Preflight,
    title: ProcessTitle | None,
    review_log: ReviewLog | None = None,
) -> int:
    summaries = {
        course.root: CourseSummary(
            discovered=sum(
                1 for item in preflight.items if item.course == course
            )
        )
        for course in preflight.courses
    }
    course_output_failures: set[Path] = set()
    # Establish each course's output root once.  A permission or mount error
    # is therefore one course-level event, never one event per media item.
    for course in preflight.courses:
        try:
            output_fd = open_safe_output_root(course)
        except OSError as exc:
            volume = volume_root_for(course.root)
            if not volume_is_live(volume):
                if wait_for_volume(volume, review_log, _ACTIVE_RUN_LOG):
                    try:
                        output_fd = open_safe_output_root(course)
                    except OSError as retry_exc:
                        raise VolumeUnavailable(volume, str(retry_exc)) from retry_exc
                else:
                    raise VolumeUnavailable(volume, str(exc)) from exc
            else:
                output_fd = None
            if output_fd is None:
                course_output_failures.add(course.root)
                summaries[course.root].failed += 1
                detail = f"could not create course output root: {exc}"
                if review_log is not None:
                    review_log.record("COURSE OUTPUT ROOT", course.root, detail)
                _record_run_event("FAIL", f"course={course.root} {detail}", issue=True)
        else:
            os.close(output_fd)
            _record_run_event("SCAN", f"course={course.root} output-root=ready")
    selected_index = 0

    for item in preflight.items:
        summary = summaries[item.course.root]
        if item.course.root in course_output_failures:
            continue
        if not item.selected:
            if item_is_eligible(item, preflight.options):
                summary.limited += 1
            else:
                summary.skipped += 1
            continue

        selected_index += 1
        set_title(
            title,
            f"batch-transcribe-courses [{selected_index}/{preflight.work_total}] "
            f"{course_progress_label(item.course)} :: {item.relative_media}",
        )
        process_item(
            item,
            preflight.programs,
            preflight.options,
            summary,
            f"[{item.course.name} {selected_index}/{preflight.work_total}]",
            review_log,
        )

    for course in preflight.courses:
        summary = summaries[course.root]
        print(
            f"Course summary [{course.name}]: discovered={summary.discovered} "
            f"attempted={summary.attempted} succeeded={summary.succeeded} "
            f"skipped={summary.skipped} limited={summary.limited} "
            f"failed={summary.failed}",
            flush=True,
        )
        _record_run_event(
            "COURSE SUMMARY",
            f"course={course.root} discovered={summary.discovered} attempted={summary.attempted} "
            f"succeeded={summary.succeeded} skipped={summary.skipped} limited={summary.limited} failed={summary.failed}",
        )
    combined = combine_summaries(summaries)
    print(
        f"Combined summary: courses={len(preflight.courses)} "
        f"discovered={combined.discovered} attempted={combined.attempted} "
        f"succeeded={combined.succeeded} skipped={combined.skipped} "
        f"limited={combined.limited} failed={combined.failed}",
        flush=True,
    )
    _record_run_event(
        "SUMMARY",
        f"courses={len(preflight.courses)} discovered={combined.discovered} attempted={combined.attempted} "
        f"succeeded={combined.succeeded} skipped={combined.skipped} limited={combined.limited} failed={combined.failed}",
    )
    if combined.failed:
        set_title(title, f"batch-transcribe-courses failed={combined.failed}")
        return 1
    set_title(
        title,
        f"batch-transcribe-courses complete={combined.succeeded} "
        f"skipped={combined.skipped}",
    )
    return 0


def validate_fast_start_roots(
    raw_roots: list[str],
    review_log: ReviewLog | None,
) -> list[Path]:
    """Keep valid roots and report invalid or overlapping roots."""

    roots: list[Path] = []
    for raw in raw_roots:
        root, error = resolve_input_root(raw)
        if error:
            if review_log is None:
                raise PreflightError([error])
            review_log.record("COURSE ROOT", raw, error)
            continue
        assert root is not None
        overlapping = next(
            (accepted for accepted in roots if path_overlap(root, accepted)),
            None,
        )
        if overlapping is not None:
            reason = f"overlaps earlier course root {overlapping}"
            if review_log is None:
                raise PreflightError(
                    [f"input roots overlap: {overlapping} and {root}"]
                )
            review_log.record("COURSE ROOT", root, reason)
            continue
        roots.append(root)
    return roots


def prepare_worker_for_live_run(options: TranscriptionOptions) -> str | None:
    """Build the worker if needed and prove it can load its resident model.

    The worker started here stays resident for the whole run, so this is the
    only model load a run pays.  Callers rely on a clean return as the proof
    that migrating an older checkpoint is safe.
    """

    del options
    programs, info, error = bootstrap_worker(allow_build=True)
    if error:
        return error
    assert programs is not None and programs.worker is not None
    assert info is not None
    try:
        worker = active_worker(programs.worker)
        worker.start()
    except (WorkerProtocolError, WorkerRequestTimeout) as exc:
        reset_worker("bootstrap load failure")
        return f"WhisperKit worker could not load its model: {exc}"
    ready = worker.ready or {}
    load_seconds = ready.get("model_load_seconds")
    _record_run_event(
        "WORKER BOOTSTRAP",
        " ".join(
            (
                f"loaded worker={info.worker_path}",
                f"model={ready.get('model_path')}",
                f"worker_version={ready.get('worker_version')}",
                f"argmax={ready.get('argmax_revision')}",
                f"encoder={ready.get('audio_encoder_compute_units')}",
                f"decoder={ready.get('text_decoder_compute_units')}",
                f"load_seconds={load_seconds}",
            )
        ),
    )
    if isinstance(load_seconds, (int, float)) and not isinstance(load_seconds, bool):
        print(
            f"WORKER READY model={MODEL} load_seconds={float(load_seconds):.1f}",
            flush=True,
        )
    return None


def run_fast_start(
    raw_roots: list[str],
    limit: int | None,
    title: ProcessTitle | None,
    options: TranscriptionOptions = TranscriptionOptions(),
    review_log: ReviewLog | None = None,
    checkpoint: ResumeCheckpoint | None = None,
    start_index: int = 0,
    roots_prevalidated: bool = False,
    ignore_omega_directories: bool = False,
    scan: bool = False,
) -> int:
    """Process one explicit course root at a time, streaming by default."""

    if roots_prevalidated:
        roots = [Path(raw_root) for raw_root in raw_roots]
    else:
        try:
            roots = validate_fast_start_roots(raw_roots, review_log)
        except PreflightError as exc:
            set_title(title, "batch-transcribe-courses validation-failed")
            for error in exc.errors:
                print(f"error: {error}", file=sys.stderr, flush=True)
            return 2
    if not roots:
        set_title(title, "batch-transcribe-courses no-valid-roots")
        print("error: no valid course roots to process", file=sys.stderr, flush=True)
        return 2
    if start_index < 0 or start_index >= len(roots):
        set_title(title, "batch-transcribe-courses invalid-resume-cursor")
        print(
            f"error: resume cursor {start_index} is outside "
            f"{len(roots)} course roots",
            file=sys.stderr,
            flush=True,
        )
        return 2

    programs, _worker_info, bootstrap_error = bootstrap_worker(allow_build=False)
    if bootstrap_error:
        if review_log is not None:
            review_log.record("PROGRAM", "transcription programs", bootstrap_error)
        print(f"error: {bootstrap_error}", file=sys.stderr, flush=True)
        return 2
    assert programs is not None

    print_settings(options)
    remaining = limit
    processed = 0
    preflight_failures = 0
    transcription_failures = 0

    root_index = start_index
    while root_index < len(roots):
        root = roots[root_index]
        display_index = root_index + 1
        if remaining == 0:
            if checkpoint is not None and checkpoint.status != "paused":
                checkpoint.set_cursor(root_index, "paused")
            break
        if checkpoint is not None:
            checkpoint.set_cursor(root_index, "active")
        course = Course(
            root,
            ignore_omega_directories=ignore_omega_directories,
        )
        if scan:
            print(
                f"SCAN [{display_index}/{len(roots)}] course={root}",
                flush=True,
            )
            _record_run_event(
                "SCAN", f"course={root} index={display_index}/{len(roots)}"
            )
            set_title(
                title,
                f"batch-transcribe-courses scan "
                f"[{display_index}/{len(roots)}] {root.name}",
            )
            try:
                preflight = perform_preflight(
                    [str(root)],
                    remaining,
                    options,
                    ignore_omega_directories=ignore_omega_directories,
                    programs=programs,
                )
            except PreflightError as exc:
                volume = volume_root_for(root)
                if not volume_is_live(volume):
                    if wait_for_volume(volume, review_log, _ACTIVE_RUN_LOG):
                        # The same cursor is deliberately retried after a mount
                        # recovery; no course is discarded while the share is down.
                        continue
                    raise VolumeUnavailable(volume, str(exc)) from exc
                preflight_failures += 1
                if checkpoint is not None:
                    checkpoint.record_failed_course(str(root))
                for error in exc.errors:
                    if review_log is not None:
                        review_log.record("COURSE PREFLIGHT", root, error)
                    print(
                        f"FAIL course={root}: {error}",
                        file=sys.stderr,
                        flush=True,
                    )
                if checkpoint is not None:
                    checkpoint.set_cursor(
                        root_index + 1,
                        "active"
                        if root_index + 1 < len(roots)
                        else checkpoint.final_status(),
                    )
                root_index += 1
                continue

            print_preflight(preflight, dry_run=False)
            course_was_limited = any(
                item_is_eligible(item, options) and not item.selected
                for item in preflight.items
            )
            result = run_live(preflight, title, review_log)
            consumed = preflight.work_total
            processed += 1
            if result:
                transcription_failures += 1
                if checkpoint is not None:
                    checkpoint.record_failed_course(str(root))
        else:
            print(
                f"COURSE [{display_index}/{len(roots)}] course={root}",
                flush=True,
            )
            _record_run_event(
                "COURSE", f"course={root} index={display_index}/{len(roots)}"
            )
            set_title(
                title,
                f"batch-transcribe-courses course "
                f"[{display_index}/{len(roots)}] {root.name}",
            )
            try:
                _summary, consumed, course_was_limited, stream_failed = stream_course(
                    course,
                    programs,
                    options,
                    remaining,
                    title,
                    review_log,
                    f"{display_index}/{len(roots)}",
                )
            except PreflightError as exc:
                volume = volume_root_for(root)
                if not volume_is_live(volume):
                    if wait_for_volume(volume, review_log, _ACTIVE_RUN_LOG):
                        continue
                    raise VolumeUnavailable(volume, str(exc)) from exc
                preflight_failures += 1
                if checkpoint is not None:
                    checkpoint.record_failed_course(str(root))
                for error in exc.errors:
                    if review_log is not None:
                        review_log.record("COURSE PREFLIGHT", root, error)
                    print(
                        f"FAIL course={root}: {error}",
                        file=sys.stderr,
                        flush=True,
                    )
                if checkpoint is not None:
                    checkpoint.set_cursor(
                        root_index + 1,
                        "active"
                        if root_index + 1 < len(roots)
                        else checkpoint.final_status(),
                    )
                root_index += 1
                continue
            processed += 1
            result = 1 if stream_failed else 0
            if result:
                transcription_failures += 1
                if checkpoint is not None:
                    checkpoint.record_failed_course(str(root))

        if remaining is not None:
            remaining -= consumed
        if checkpoint is not None:
            if course_was_limited:
                checkpoint.set_cursor(root_index, "paused")
            else:
                checkpoint.set_cursor(
                    root_index + 1,
                    "active"
                    if root_index + 1 < len(roots)
                    else checkpoint.final_status(),
                )
        _record_run_event(
            "COURSE SUMMARY",
            f"course={root} result={'failed' if result else 'ok'}",
        )
        root_index += 1
    print(
        f"Fast-start summary: roots={len(roots)} processed={processed} "
        f"preflight_failed={preflight_failures} "
        f"transcription_failed={transcription_failures}",
        flush=True,
    )
    if preflight_failures:
        return 2
    if transcription_failures:
        return 1
    return 0


def _main(argv: Iterator[str] | None = None) -> int:
    title = ProcessTitle.capture()
    parser = build_parser()
    raw_argv = list(argv) if argv is not None else None
    args = parser.parse_args(raw_argv)
    args.scan = args.scan or args.dry_run
    try:
        options = options_from_args(args)
    except ValueError as exc:
        parser.error(str(exc))
    if args.resume_from_command:
        if (
            args.roots
            or args.resume
            or args.resume_from
            or args.author_roots
            or args.topic_roots
            or args.skip_preflight
            or args.dry_run
        ):
            parser.error(
                "--resume-from-command accepts only COURSE_ROOT and "
                "optional --limit"
            )
        try:
            recovered = recover_author_invocation(sys.stdin.read())
        except ResumeStateError as exc:
            print(f"error: {exc}", file=sys.stderr, flush=True)
            return 2
        args.roots = recovered.roots
        args.author_roots = recovered.source_mode == "author-roots"
        args.topic_roots = recovered.source_mode == "topic-roots"
        args.scan = recovered.scan
        args.resume_from = args.resume_from_command
        if args.limit is None:
            args.limit = recovered.limit
    if args.skip_preflight and args.dry_run:
        parser.error("--skip-preflight cannot be combined with --dry-run")
    if args.skip_preflight:
        print(
            "warning: --skip-preflight is deprecated; streaming is now the default",
            file=sys.stderr,
            flush=True,
        )
    retry_baseline = TranscriptionOptions()
    if args.retry_failed and (
        args.resume
        or args.roots
        or args.author_roots
        or args.topic_roots
        or args.dry_run
        or args.resume_from
        or args.resume_from_command
        or options != retry_baseline
    ):
        parser.error(
            "--retry-failed accepts only its state path and --log-file"
        )
    resume_baseline = TranscriptionOptions()
    if args.resume and (
        args.roots
        or args.author_roots
        or args.topic_roots
        or args.dry_run
        or args.resume_from
        or args.resume_from_command
        or options != resume_baseline
    ):
        parser.error(
            "--resume accepts only its state path and optional --limit"
        )
    if not args.resume and not args.retry_failed and not args.roots:
        parser.error("at least one ROOT is required unless --resume is used")

    run_log = RunLog.for_current_run(
        argv=list(sys.argv if raw_argv is None else [str(Path(__file__)), *raw_argv]),
        options=options,
        source_mode=(
            "retry-failed"
            if args.retry_failed
            else "topic-roots"
            if args.topic_roots
            else "author-roots"
            if args.author_roots
            else "resume"
            if args.resume
            else "course-roots"
        ),
        course_count=len(args.roots) if args.roots else None,
        log_file=args.log_file,
    )
    global _ACTIVE_RUN_LOG
    _ACTIVE_RUN_LOG = run_log
    review_log = ReviewLog.for_current_run(run_log)

    if args.retry_failed:
        try:
            source_checkpoint = ResumeCheckpoint.load(args.retry_failed)
        except ResumeStateError as exc:
            print(f"error: {exc}", file=sys.stderr, flush=True)
            run_log.footer(2, "invalid retry-failed state")
            return 2
        if not source_checkpoint.failed_courses:
            print(
                "error: resume state contains no failed_courses to retry",
                file=sys.stderr,
                flush=True,
            )
            run_log.footer(2, "empty failed_courses")
            return 2
        retry_options = source_checkpoint.options
        bootstrap_error = prepare_worker_for_live_run(retry_options)
        if bootstrap_error:
            print(f"error: {bootstrap_error}", file=sys.stderr, flush=True)
            run_log.footer(2, "worker bootstrap failed")
            return 2
        run_log._write(f"Expanded course count: {len(source_checkpoint.failed_courses)}")
        try:
            checkpoint = ResumeCheckpoint.create(
                list(source_checkpoint.failed_courses),
                list(source_checkpoint.source_roots),
                source_checkpoint.source_mode,
                options=retry_options,
            )
        except ResumeStateError as exc:
            print(f"error: {exc}", file=sys.stderr, flush=True)
            run_log.footer(2, "could not create retry checkpoint")
            return 2
        print(
            f"RETRY FAILED courses={len(checkpoint.course_roots)} "
            f"state={checkpoint.path}",
            flush=True,
        )
        checkpoint.print_command()
        try:
            result = run_fast_start(
                checkpoint.course_roots,
                args.limit,
                title,
                options=checkpoint.options,
                review_log=review_log,
                checkpoint=checkpoint,
                start_index=0,
                roots_prevalidated=True,
                ignore_omega_directories=(source_checkpoint.source_mode == "topic-roots"),
                scan=args.scan,
            )
        except VolumeUnavailable as exc:
            checkpoint.set_cursor(checkpoint.next_index, "interrupted")
            print(f"VOLUME UNAVAILABLE: {exc}", file=sys.stderr, flush=True)
            checkpoint.print_command()
            run_log.footer(75, "volume unavailable", checkpoint_path=checkpoint.path)
            return 75
        except WorkerHealthError as exc:
            checkpoint.set_cursor(checkpoint.next_index, "interrupted")
            print(f"WORKER UNHEALTHY: {exc}", file=sys.stderr, flush=True)
            checkpoint.print_command()
            run_log.footer(70, "worker unhealthy", checkpoint_path=checkpoint.path)
            return 70
        except KeyboardInterrupt:
            checkpoint.set_cursor(checkpoint.next_index, "interrupted")
            checkpoint.print_command()
            run_log.footer(130, "interrupted", checkpoint_path=checkpoint.path)
            return 130
        checkpoint.print_command()
        review_log.print_summary()
        run_log.footer(result, "complete" if result == 0 else "course failures", checkpoint_path=checkpoint.path, retry_failed_command=retry_failed_command(checkpoint), issue_count=review_log.issue_count)
        return result
    if args.resume:
        try:
            checkpoint = ResumeCheckpoint.load(args.resume)
        except ResumeStateError as exc:
            print(f"error: {exc}", file=sys.stderr, flush=True)
            return 2
        if checkpoint.status in {"complete", "complete-with-failures"}:
            print(
                f"RESUME {checkpoint.status} state={checkpoint.path} "
                f"courses={len(checkpoint.course_roots)}",
                flush=True,
            )
            if checkpoint.failed_courses:
                print(
                    "Retry failed courses with --retry-failed "
                    f"{checkpoint.path}",
                    flush=True,
                )
            run_log.footer(0, checkpoint.status, checkpoint_path=checkpoint.path, retry_failed_command=retry_failed_command(checkpoint), issue_count=review_log.issue_count)
            return 0
        bootstrap_error = prepare_worker_for_live_run(checkpoint.options)
        if bootstrap_error:
            # The worker never loaded, so an older checkpoint stays exactly as
            # it was found on disk.
            print(f"error: {bootstrap_error}", file=sys.stderr, flush=True)
            run_log.footer(
                2,
                "worker bootstrap failed",
                checkpoint_path=checkpoint.path,
            )
            return 2
        try:
            checkpoint.migrate()
        except ResumeStateError as exc:
            print(f"error: {exc}", file=sys.stderr, flush=True)
            run_log.footer(
                2,
                "resume state migration failed",
                checkpoint_path=checkpoint.path,
            )
            return 2
        run_log._write(f"Expanded course count: {len(checkpoint.course_roots)}")
        print(
            f"RESUME state={checkpoint.path} "
            f"next={checkpoint.next_index + 1}/"
            f"{len(checkpoint.course_roots)} "
            f"course={checkpoint.current_course}",
            flush=True,
        )
        try:
            result = run_fast_start(
                checkpoint.course_roots,
                args.limit,
                title,
                options=checkpoint.options,
                review_log=review_log,
                checkpoint=checkpoint,
                start_index=checkpoint.next_index,
                roots_prevalidated=True,
                ignore_omega_directories=(
                    checkpoint.source_mode == "topic-roots"
                ),
                scan=args.scan,
            )
        except KeyboardInterrupt:
            try:
                checkpoint.set_cursor(
                    checkpoint.next_index,
                    "interrupted",
                )
            except ResumeStateError as exc:
                print(f"RESUME FAIL: {exc}", file=sys.stderr, flush=True)
            print(
                f"INTERRUPTED resume={checkpoint.path}",
                file=sys.stderr,
                flush=True,
            )
            checkpoint.print_command()
            review_log.print_summary()
            run_log.footer(130, "interrupted", checkpoint_path=checkpoint.path)
            return 130
        except VolumeUnavailable as exc:
            try:
                checkpoint.set_cursor(checkpoint.next_index, "interrupted")
            except ResumeStateError as state_exc:
                print(f"RESUME FAIL: {state_exc}", file=sys.stderr, flush=True)
            print(f"VOLUME UNAVAILABLE: {exc}", file=sys.stderr, flush=True)
            checkpoint.print_command()
            review_log.print_summary()
            run_log.footer(75, "volume unavailable", checkpoint_path=checkpoint.path)
            return 75
        except WorkerHealthError as exc:
            try:
                checkpoint.set_cursor(checkpoint.next_index, "interrupted")
            except ResumeStateError as state_exc:
                print(f"RESUME FAIL: {state_exc}", file=sys.stderr, flush=True)
            print(f"WORKER UNHEALTHY: {exc}", file=sys.stderr, flush=True)
            checkpoint.print_command()
            review_log.print_summary()
            run_log.footer(70, "worker unhealthy", checkpoint_path=checkpoint.path)
            return 70
        except ResumeStateError as exc:
            print(f"RESUME FAIL: {exc}", file=sys.stderr, flush=True)
            review_log.print_summary()
            run_log.footer(2, "resume state failure", checkpoint_path=checkpoint.path)
            return 2
        checkpoint.print_command()
        review_log.print_summary()
        run_log.footer(result, "complete" if result == 0 else "course failures", checkpoint_path=checkpoint.path, retry_failed_command=retry_failed_command(checkpoint), issue_count=review_log.issue_count)
        return result

    roots = args.roots
    if args.topic_roots:
        print(
            f"TOPIC ROOTS expanding roots={len(roots)}",
            flush=True,
        )
        set_title(title, "batch-transcribe-courses expanding-topic-roots")
        roots = expand_topic_roots(roots, review_log)
        print(
            f"TOPIC ROOTS expanded topics={len(args.roots)} "
            f"courses={len(roots)} review={review_log.issue_count}",
            flush=True,
        )
        if not roots:
            set_title(title, "batch-transcribe-courses no-valid-topic-roots")
            print(
                "error: no course roots were found beneath the supplied "
                "topic roots",
                file=sys.stderr,
                flush=True,
            )
            review_log.print_summary()
            run_log.footer(2, "no valid topic roots", issue_count=review_log.issue_count)
            return 2
    elif args.author_roots:
        print(
            f"AUTHOR ROOTS expanding roots={len(roots)}",
            flush=True,
        )
        set_title(title, "batch-transcribe-courses expanding-author-roots")
        roots = expand_author_roots(roots, review_log)
        print(
            f"AUTHOR ROOTS expanded authors={len(args.roots)} "
            f"courses={len(roots)} review={review_log.issue_count}",
            flush=True,
        )
        if not roots:
            set_title(title, "batch-transcribe-courses no-valid-author-roots")
            print(
                "error: no course roots were found beneath the supplied "
                "author roots",
                file=sys.stderr,
                flush=True,
            )
            review_log.print_summary()
            run_log.footer(2, "no valid author roots", issue_count=review_log.issue_count)
            return 2

    # Hierarchy expansion happens after the run-log header is opened.  Record
    # the exact expanded count as a header-adjacent line for auditability.
    run_log._write(f"Expanded course count: {len(roots)}")

    if not args.dry_run:
        roots_prevalidated = args.author_roots or args.topic_roots
        if not roots_prevalidated:
            try:
                validated_roots = validate_fast_start_roots(
                    roots,
                    review_log,
                )
            except PreflightError as exc:
                for error in exc.errors:
                    print(f"error: {error}", file=sys.stderr, flush=True)
                review_log.print_summary()
                return 2
            roots = [str(root) for root in validated_roots]
            roots_prevalidated = True
            if not roots:
                print(
                    "error: no valid course roots to process",
                    file=sys.stderr,
                    flush=True,
                )
                review_log.print_summary()
                return 2
        start_index = 0
        if args.resume_from:
            try:
                start_index = resume_course_index(roots, args.resume_from)
            except ResumeStateError as exc:
                print(f"error: {exc}", file=sys.stderr, flush=True)
                review_log.print_summary()
                return 2
        bootstrap_error = prepare_worker_for_live_run(options)
        if bootstrap_error:
            # No checkpoint is created when the worker cannot be prepared.
            print(f"error: {bootstrap_error}", file=sys.stderr, flush=True)
            review_log.print_summary()
            run_log.footer(2, "worker bootstrap failed")
            return 2
        try:
            checkpoint = ResumeCheckpoint.create(
                roots,
                args.roots,
                (
                    "topic-roots"
                    if args.topic_roots
                    else "author-roots"
                    if args.author_roots
                    else "course-roots"
                ),
                next_index=start_index,
                options=options,
            )
        except ResumeStateError as exc:
            print(f"error: {exc}", file=sys.stderr, flush=True)
            review_log.print_summary()
            return 2
        print(
            f"RESUME STATE path={checkpoint.path} "
            f"start={start_index + 1}/{len(roots)}",
            flush=True,
        )
        checkpoint.print_command()
        print(
            f"FAST START roots={len(roots)} "
            f"start={start_index + 1} "
            f"limit={args.limit if args.limit is not None else 'none'}",
            flush=True,
        )
        try:
            result = run_fast_start(
                roots,
                args.limit,
                title,
                options=options,
                review_log=review_log,
                checkpoint=checkpoint,
                start_index=start_index,
                roots_prevalidated=roots_prevalidated,
                ignore_omega_directories=args.topic_roots,
                scan=args.scan,
            )
        except KeyboardInterrupt:
            try:
                checkpoint.set_cursor(
                    checkpoint.next_index,
                    "interrupted",
                )
            except ResumeStateError as exc:
                print(f"RESUME FAIL: {exc}", file=sys.stderr, flush=True)
            print(
                f"INTERRUPTED resume={checkpoint.path}",
                file=sys.stderr,
                flush=True,
            )
            checkpoint.print_command()
            review_log.print_summary()
            run_log.footer(130, "interrupted", checkpoint_path=checkpoint.path)
            return 130
        except VolumeUnavailable as exc:
            try:
                checkpoint.set_cursor(checkpoint.next_index, "interrupted")
            except ResumeStateError as state_exc:
                print(f"RESUME FAIL: {state_exc}", file=sys.stderr, flush=True)
            print(f"VOLUME UNAVAILABLE: {exc}", file=sys.stderr, flush=True)
            checkpoint.print_command()
            review_log.print_summary()
            run_log.footer(75, "volume unavailable", checkpoint_path=checkpoint.path)
            return 75
        except WorkerHealthError as exc:
            try:
                checkpoint.set_cursor(checkpoint.next_index, "interrupted")
            except ResumeStateError as state_exc:
                print(f"RESUME FAIL: {state_exc}", file=sys.stderr, flush=True)
            print(f"WORKER UNHEALTHY: {exc}", file=sys.stderr, flush=True)
            checkpoint.print_command()
            review_log.print_summary()
            run_log.footer(70, "worker unhealthy", checkpoint_path=checkpoint.path)
            return 70
        except ResumeStateError as exc:
            print(f"RESUME FAIL: {exc}", file=sys.stderr, flush=True)
            review_log.print_summary()
            return 2
        checkpoint.print_command()
        review_log.print_summary()
        run_log.footer(result, "complete" if result == 0 else "course failures", checkpoint_path=checkpoint.path, retry_failed_command=retry_failed_command(checkpoint), issue_count=review_log.issue_count)
        return result

    print(
        f"PREFLIGHT scanning roots={len(roots)} "
        f"limit={args.limit if args.limit is not None else 'none'}",
        flush=True,
    )
    set_title(title, "batch-transcribe-courses preflight")
    try:
        preflight = perform_preflight(
            roots,
            args.limit,
            options,
            ignore_omega_directories=args.topic_roots,
        )
    except PreflightError as exc:
        set_title(title, "batch-transcribe-courses preflight-failed")
        for error in exc.errors:
            review_log.record("PREFLIGHT", "supplied roots", error)
            print(f"error: {error}", file=sys.stderr, flush=True)
        review_log.print_summary()
        run_log.footer(2, "preflight failure", issue_count=review_log.issue_count)
        return 2

    print_settings(options)
    print_preflight(preflight, args.dry_run)
    if args.dry_run:
        combined = CourseSummary()
        for course in preflight.courses:
            summary = summary_for_course(preflight, course)
            combined.discovered += summary.discovered
            combined.skipped += summary.skipped
            combined.limited += summary.limited
            combined.would_transcribe += summary.would_transcribe
        print(
            f"Combined preflight: courses={len(preflight.courses)} "
            f"discovered={combined.discovered} skipped={combined.skipped} "
            f"would_transcribe={combined.would_transcribe} "
            f"limited={combined.limited} failed=0",
            flush=True,
        )
        set_title(title, "batch-transcribe-courses preflight-complete")
        review_log.print_summary()
        run_log.footer(0, "dry-run complete", issue_count=review_log.issue_count)
        return 0


def main(argv: Iterator[str] | None = None) -> int:
    try:
        return _main(argv)
    finally:
        shutdown_worker()


if __name__ == "__main__":
    raise SystemExit(main())
