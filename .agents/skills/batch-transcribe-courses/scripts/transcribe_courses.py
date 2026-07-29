#!/usr/bin/env python3
"""Safely transcribe course media in place with WhisperKit CLI.

Every supplied course root is read-only except for its top-level
``transcripts/`` directory. A complete preflight succeeds before live work can
create output directories, process-owned ``.part`` files, or absent ``.txt``
transcripts.

This is a simplified derivative of ``bulk_transcribe_network_whisperkit.py``.
Its intentionally fixed M5 Pro configuration is:

* model: ``large-v3-v20240930_turbo``
* language/task: English transcription
* chunking: VAD
* audio encoder: CPU + Neural Engine
* text decoder: CPU + GPU
* mel spectrogram: WhisperKit's CPU + GPU default
* concurrent VAD workers: 64
* word timestamps: disabled
"""

from __future__ import annotations

import argparse
import ctypes
from dataclasses import dataclass
import errno
from enum import Enum
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Iterator
import unicodedata


MODEL = "large-v3-v20240930_turbo"
LANGUAGE = "en"
CHUNKING_STRATEGY = "vad"
AUDIO_ENCODER_COMPUTE_UNITS = "cpuAndNeuralEngine"
TEXT_DECODER_COMPUTE_UNITS = "cpuAndGPU"
CONCURRENT_WORKERS = 64

DIRECT_AUDIO_EXTENSIONS = frozenset(
    {
        ".aac",
        ".aif",
        ".aiff",
        ".caf",
        ".flac",
        ".m4a",
        ".mp3",
        ".wav",
    }
)
AUDIO_EXTENSIONS = DIRECT_AUDIO_EXTENSIONS | frozenset(
    {
        ".ac3",
        ".amr",
        ".ape",
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
RENAME_EXCL = 0x00000004


@dataclass(frozen=True)
class Course:
    root: Path

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
    selected: bool = False


@dataclass(frozen=True)
class Programs:
    whisperkit: str
    ffmpeg: str


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


class PreflightError(Exception):
    """A fail-closed preflight rejection."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Recursively transcribe course media into each supplied course "
            "root's top-level transcripts directory."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="run the complete preflight and print mappings without writing",
    )
    parser.add_argument(
        "--limit",
        type=non_negative_int,
        metavar="N",
        help="process at most N missing transcripts across all course roots",
    )
    parser.add_argument(
        "roots",
        nargs="+",
        metavar="ROOT",
        help="one or more course-root directories",
    )
    return parser


def path_overlap(first: Path, second: Path) -> bool:
    return first == second or first.is_relative_to(second) or second.is_relative_to(first)


def validate_input_roots(raw_roots: list[str]) -> list[Path]:
    roots: list[Path] = []
    errors: list[str] = []
    for raw in raw_roots:
        try:
            root = Path(raw).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(f"invalid input root {raw!r}: {exc}")
            continue
        try:
            root_stat = root.stat()
        except OSError as exc:
            errors.append(f"could not inspect input root {root}: {exc}")
            continue
        if not stat.S_ISDIR(root_stat.st_mode):
            errors.append(f"input root is not a directory: {root}")
            continue
        if not root.name:
            errors.append(f"input root must not be a filesystem root: {root}")
            continue
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


def identity_from_stat(file_stat: os.stat_result) -> MediaIdentity:
    return MediaIdentity(
        device=file_stat.st_dev,
        inode=file_stat.st_ino,
        size=file_stat.st_size,
        modified_ns=file_stat.st_mtime_ns,
    )


def discover_media(course: Course) -> tuple[list[WorkItem], list[str]]:
    items: list[WorkItem] = []
    errors: list[str] = []

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
            if directory_path == course.root:
                dirnames[:] = [
                    name for name in dirnames if name.casefold() != "transcripts"
                ]

            for filename in filenames:
                media = directory_path / filename
                if media.suffix.casefold() not in MEDIA_EXTENSIONS:
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


def inspect_output(item: WorkItem) -> tuple[bool, str | None]:
    current = item.course.transcript_root
    for component in item.relative_output.parent.parts:
        current = current / component
        try:
            parent_stat = lstat_or_missing(current)
        except OSError as exc:
            return False, f"could not inspect output parent {current}: {exc}"
        if parent_stat is None:
            return False, None
        if stat.S_ISLNK(parent_stat.st_mode):
            return False, f"output parent must not be a symlink: {current}"
        if not stat.S_ISDIR(parent_stat.st_mode):
            return False, f"output parent is not a directory: {current}"

    destination = item.course.transcript_root / item.relative_output
    try:
        return lstat_or_missing(destination) is not None, None
    except OSError as exc:
        return False, f"could not inspect transcript destination {destination}: {exc}"


def collision_key(item: WorkItem) -> str:
    normalized = unicodedata.normalize("NFC", item.relative_output.as_posix())
    return normalized.casefold()


def perform_preflight(
    raw_roots: list[str],
    limit: int | None,
) -> Preflight:
    courses = [Course(root) for root in validate_input_roots(raw_roots)]
    errors: list[str] = []

    whisperkit, whisperkit_error = resolve_program("whisperkit-cli", "WhisperKit CLI")
    ffmpeg, ffmpeg_error = resolve_program("ffmpeg", "ffmpeg")
    if whisperkit_error:
        errors.append(whisperkit_error)
    if ffmpeg_error:
        errors.append(ffmpeg_error)

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
            exists, output_error = inspect_output(item)
            item.existing = exists
            if output_error:
                errors.append(output_error)

    if errors:
        raise PreflightError(errors)
    assert whisperkit is not None
    assert ffmpeg is not None

    work_total = 0
    for item in all_items:
        if item.existing:
            continue
        if limit is None or work_total < limit:
            item.selected = True
            work_total += 1

    return Preflight(
        courses=courses,
        items=all_items,
        programs=Programs(whisperkit=whisperkit, ffmpeg=ffmpeg),
        work_total=work_total,
    )


def print_settings() -> None:
    print(
        "WhisperKit settings: "
        f"model={MODEL} language={LANGUAGE} task=transcribe "
        f"chunking={CHUNKING_STRATEGY} input=direct-common-audio/ffmpeg-other "
        f"compute=encoder:{AUDIO_ENCODER_COMPUTE_UNITS}/"
        f"decoder:{TEXT_DECODER_COMPUTE_UNITS}/mel:cpuAndGPU "
        f"workers={CONCURRENT_WORKERS} word_timestamps=off",
        flush=True,
    )


def summary_for_course(preflight: Preflight, course: Course) -> CourseSummary:
    summary = CourseSummary()
    for item in preflight.items:
        if item.course != course:
            continue
        summary.discovered += 1
        if item.existing:
            summary.skipped += 1
        elif item.selected:
            summary.would_transcribe += 1
        else:
            summary.limited += 1
    return summary


def print_preflight(preflight: Preflight, dry_run: bool) -> None:
    action = "WOULD" if dry_run else "READY"
    for course in preflight.courses:
        summary = summary_for_course(preflight, course)
        if not dry_run:
            print(
                f"PREFLIGHT course={course.root} "
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
            if item.existing:
                print(
                    f"{prefix} SKIP existing {item.relative_media} -> "
                    f"transcripts/{item.relative_output}",
                    flush=True,
                )
            elif item.selected:
                print(
                    f"{prefix} {action} ({item.input_kind}) "
                    f"{item.relative_media} -> transcripts/{item.relative_output}",
                    flush=True,
                )
            else:
                print(
                    f"{prefix} LIMIT {item.relative_media} -> "
                    f"transcripts/{item.relative_output}",
                    flush=True,
                )
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
    returncode: int, stderr: str, stdout: str = "", limit: int = 1200
) -> str:
    detail = stderr.strip() or stdout.strip()
    if len(detail) > limit:
        detail = detail[-limit:]
    return f"exit {returncode}: {detail}" if detail else f"exit {returncode}"


def extract_audio(media: Path, wav_path: Path, ffmpeg: str) -> str | None:
    command = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(media),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-n",
        str(wav_path),
    ]
    try:
        process = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return f"could not run ffmpeg: {exc}"
    if process.returncode != 0:
        return short_process_error(
            process.returncode, stderr=process.stderr, stdout=process.stdout
        )
    try:
        if not wav_path.is_file() or wav_path.stat().st_size == 0:
            return "ffmpeg produced no audio"
    except OSError as exc:
        return f"could not inspect extracted audio: {exc}"
    return None


def whisperkit_command(audio_path: Path, executable: str) -> list[str]:
    return [
        executable,
        "transcribe",
        "--audio-path",
        str(audio_path),
        "--model",
        MODEL,
        "--language",
        LANGUAGE,
        "--task",
        "transcribe",
        "--chunking-strategy",
        CHUNKING_STRATEGY,
        "--audio-encoder-compute-units",
        AUDIO_ENCODER_COMPUTE_UNITS,
        "--text-decoder-compute-units",
        TEXT_DECODER_COMPUTE_UNITS,
        "--concurrent-worker-count",
        str(CONCURRENT_WORKERS),
        "--without-timestamps",
    ]


def run_whisperkit(audio_path: Path, executable: str) -> tuple[str | None, str | None]:
    try:
        process = subprocess.run(
            whisperkit_command(audio_path, executable),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return None, f"could not run WhisperKit CLI: {exc}"
    if process.returncode != 0:
        return None, short_process_error(
            process.returncode, stderr=process.stderr, stdout=process.stdout
        )

    transcript = process.stdout.strip()
    if transcript == "Transcription failed" or any(
        line.startswith("Error when transcribing ")
        for line in transcript.splitlines()
    ):
        detail = transcript
        if process.stderr.strip():
            detail = f"{detail}\n{process.stderr.strip()}"
        return None, detail[-1200:]
    return transcript, None


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
) -> InstallResult:
    if destination_path is None:
        destination_path = Path(destination_name)
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
    item: WorkItem, programs: Programs, parent_fd: int
) -> InstallResult:
    if item.input_kind == "direct":
        transcript, error = run_whisperkit(item.media, programs.whisperkit)
    else:
        try:
            with tempfile.TemporaryDirectory(
                prefix="batch-transcribe-courses-"
            ) as temporary:
                wav_path = Path(temporary) / "audio.wav"
                error = extract_audio(item.media, wav_path, programs.ffmpeg)
                if error:
                    return InstallResult.failed(
                        f"audio extraction failed: {error}"
                    )
                transcript, error = run_whisperkit(wav_path, programs.whisperkit)
        except OSError as exc:
            return InstallResult.failed(
                f"could not create temporary audio workspace: {exc}"
            )
    if error:
        return InstallResult.failed(error)
    assert transcript is not None
    return install_transcript(
        parent_fd,
        item.relative_output.name,
        transcript,
        destination_path=item.course.transcript_root / item.relative_output,
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


def run_live(preflight: Preflight, title: ProcessTitle | None) -> int:
    summaries = {
        course.root: CourseSummary(
            discovered=sum(
                1 for item in preflight.items if item.course == course
            )
        )
        for course in preflight.courses
    }
    selected_index = 0

    for item in preflight.items:
        summary = summaries[item.course.root]
        if item.existing:
            summary.skipped += 1
            continue
        if not item.selected:
            summary.limited += 1
            continue

        selected_index += 1
        set_title(
            title,
            f"batch-transcribe-courses [{selected_index}/{preflight.work_total}] "
            f"{course_progress_label(item.course)} :: {item.relative_media}",
        )
        prefix = (
            f"[{item.course.name} {selected_index}/{preflight.work_total}]"
        )
        print(
            f"{prefix} TRANSCRIBE ({item.input_kind}) {item.relative_media} -> "
            f"transcripts/{item.relative_output}",
            flush=True,
        )

        source_error = revalidate_media(item)
        if source_error:
            summary.failed += 1
            print(
                f"{prefix} FAIL {item.relative_media}: {source_error}",
                file=sys.stderr,
                flush=True,
            )
            continue

        parent_fd: int | None = None
        try:
            parent_fd = open_safe_output_parent(item)
            if destination_exists(parent_fd, item.relative_output.name):
                summary.skipped += 1
                print(
                    f"{prefix} SKIP destination now exists "
                    f"transcripts/{item.relative_output}",
                    flush=True,
                )
                continue
            summary.attempted += 1
            result = transcribe_item(item, preflight.programs, parent_fd)
        except OSError as exc:
            result = InstallResult.failed(
                f"unsafe output path or directory creation failed: {exc}"
            )
        finally:
            if parent_fd is not None:
                os.close(parent_fd)

        if result.status is InstallStatus.FAILED:
            summary.failed += 1
            print(
                f"{prefix} FAIL {item.relative_media}: {result.detail}",
                file=sys.stderr,
                flush=True,
            )
        elif result.status is InstallStatus.SKIPPED:
            summary.skipped += 1
            print(
                f"{prefix} SKIP destination now exists "
                f"transcripts/{item.relative_output}: {result.detail}",
                flush=True,
            )
        else:
            summary.succeeded += 1
            print(
                f"{prefix} OK transcripts/{item.relative_output}",
                flush=True,
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
    combined = combine_summaries(summaries)
    print(
        f"Combined summary: courses={len(preflight.courses)} "
        f"discovered={combined.discovered} attempted={combined.attempted} "
        f"succeeded={combined.succeeded} skipped={combined.skipped} "
        f"limited={combined.limited} failed={combined.failed}",
        flush=True,
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


def main(argv: Iterator[str] | None = None) -> int:
    title = ProcessTitle.capture()
    parser = build_parser()
    args = parser.parse_args(argv)
    print(
        f"PREFLIGHT scanning roots={len(args.roots)} "
        f"limit={args.limit if args.limit is not None else 'none'}",
        flush=True,
    )
    set_title(title, "batch-transcribe-courses preflight")
    try:
        preflight = perform_preflight(args.roots, args.limit)
    except PreflightError as exc:
        set_title(title, "batch-transcribe-courses preflight-failed")
        for error in exc.errors:
            print(f"error: {error}", file=sys.stderr, flush=True)
        return 2

    print_settings()
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
        return 0
    return run_live(preflight, title)


if __name__ == "__main__":
    raise SystemExit(main())
