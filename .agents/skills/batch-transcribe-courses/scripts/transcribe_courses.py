#!/usr/bin/env python3
"""Safely transcribe course media in place with WhisperKit CLI.

Every resolved course root is read-only except for its top-level
``transcripts/`` directory. Inputs can be explicit course roots or, with
``--discover-course-roots``, higher-level library roots whose course boundaries
are resolved during preflight. A complete preflight succeeds before live work
can create output directories, process-owned ``.part`` files, or absent
``.txt`` transcripts.

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
import os
from pathlib import Path
import re
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
MODULE_PREFIX_RE = re.compile(
    r"""(?ix)
    ^\s*
    (?:
        (?:\[\s*)?(?:\d{1,3}|[ivxlcdm]{1,8})\s*
        (?:\]\s*|[._)\]-]\s*|\s+)
        |
        (?:appendix|bonus|chapter|conclusion|day|disc|disk|exercise|
           final|getting\ started|intro(?:duction)?|lesson|module|overview|
           part|section|unit|week|welcome)\b
    )
    """
)
STRONG_MODULE_PREFIX_RE = re.compile(
    r"""(?ix)
    ^\s*
    (?:
        (?:\[\s*)?(?:\d{1,3}|[ivxlcdm]{1,8})\s*
        (?:\]\s*|[._)\]-]\s*)
        |
        (?:appendix|bonus|chapter|conclusion|day|disc|disk|exercise|
           final|getting\ started|intro(?:duction)?|lesson|module|overview|
           part|section|unit|week|welcome)\b
    )
    """
)
GENERIC_MEDIA_DIRECTORY_NAMES = frozenset(
    {
        "course content",
        "course videos",
        "lectures",
        "lessons",
        "training",
        "video",
        "videos",
    }
)


@dataclass(frozen=True)
class Course:
    root: Path
    discovery_reason: str = "explicit input"
    review_reason: str | None = None

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
    input_roots: list[Path]
    courses: list[Course]
    items: list[WorkItem]
    programs: Programs
    work_total: int
    discovered_course_roots: bool
    inference_notes: list[str]


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
            "Recursively transcribe course media into each resolved course "
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
        "--discover-course-roots",
        action="store_true",
        help=(
            "treat positional paths as higher-level library roots and infer "
            "non-overlapping course roots during preflight"
        ),
    )
    parser.add_argument(
        "roots",
        nargs="+",
        metavar="ROOT",
        help="one or more explicit course roots or higher-level library roots",
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


def module_directory_signal(name: str) -> bool:
    normalized = unicodedata.normalize("NFC", name).strip().casefold()
    return (
        normalized in GENERIC_MEDIA_DIRECTORY_NAMES
        or MODULE_PREFIX_RE.match(normalized) is not None
    )


def strong_module_directory_signal(name: str) -> bool:
    normalized = unicodedata.normalize("NFC", name).strip().casefold()
    return (
        normalized in GENERIC_MEDIA_DIRECTORY_NAMES
        or STRONG_MODULE_PREFIX_RE.match(normalized) is not None
    )


def directory_children_form_course(children: list[Path]) -> bool:
    if not children:
        return False
    if len(children) == 1:
        return strong_module_directory_signal(children[0].name)
    signaled = sum(module_directory_signal(child.name) for child in children)
    return signaled >= 2 and signaled * 2 >= len(children)


def scan_media_layout(
    input_root: Path,
) -> tuple[set[Path], dict[Path, list[Path]], list[str]]:
    """Return direct-media directories and traversed child directories."""

    direct_media: set[Path] = set()
    children: dict[Path, list[Path]] = {}
    errors: list[str] = []

    def onerror(error: OSError) -> None:
        errors.append(
            f"course-root discovery failed at {error.filename or input_root}: "
            f"{error.strerror or error}"
        )

    try:
        for directory, dirnames, filenames in os.walk(
            input_root, topdown=True, followlinks=False, onerror=onerror
        ):
            directory_path = Path(directory)
            safe_dirnames: list[str] = []
            child_paths: list[Path] = []
            for name in dirnames:
                if name.casefold() == "transcripts":
                    continue
                child = directory_path / name
                try:
                    child_stat = child.lstat()
                except OSError as exc:
                    errors.append(
                        f"could not inspect directory during course-root "
                        f"discovery {child}: {exc}"
                    )
                    continue
                if stat.S_ISLNK(child_stat.st_mode):
                    continue
                if not stat.S_ISDIR(child_stat.st_mode):
                    continue
                safe_dirnames.append(name)
                child_paths.append(child)
            dirnames[:] = safe_dirnames
            children[directory_path] = child_paths

            for filename in filenames:
                media = directory_path / filename
                if media.suffix.casefold() not in MEDIA_EXTENSIONS:
                    continue
                try:
                    media_stat = media.lstat()
                except OSError as exc:
                    errors.append(
                        f"could not inspect media candidate during course-root "
                        f"discovery {media}: {exc}"
                    )
                    continue
                if stat.S_ISLNK(media_stat.st_mode):
                    continue
                if stat.S_ISREG(media_stat.st_mode):
                    direct_media.add(directory_path)
    except (OSError, RuntimeError) as exc:
        errors.append(f"course-root discovery failed at {input_root}: {exc}")

    return direct_media, children, errors


def infer_course_roots(
    input_root: Path,
) -> tuple[list[Course], list[str], list[str]]:
    direct_media, traversed_children, errors = scan_media_layout(input_root)
    if errors:
        return [], [], errors

    contains_media: set[Path] = set()
    for directory in direct_media:
        current = directory
        while True:
            contains_media.add(current)
            if current == input_root:
                break
            try:
                current = current.parent
            except RuntimeError as exc:
                errors.append(
                    f"could not resolve media ancestry below {input_root}: {exc}"
                )
                break
            if not current.is_relative_to(input_root):
                errors.append(
                    f"media directory escapes input root during discovery: "
                    f"{directory}"
                )
                break
    if errors:
        return [], [], errors

    inferred: list[Course] = []
    notes: list[str] = []

    def add_inferred_course(
        directory: Path, reason: str, singleton_chain: list[Path]
    ) -> None:
        review_reason: str | None = None
        if singleton_chain:
            chain = " -> ".join(
                path.relative_to(input_root).as_posix()
                for path in (*singleton_chain, directory)
            )
            review_reason = (
                "a single-child chain does not prove which level is the "
                f"course boundary: {chain}"
            )
        inferred.append(
            Course(
                directory,
                discovery_reason=reason,
                review_reason=review_reason,
            )
        )

    def visit(directory: Path, singleton_chain: list[Path]) -> None:
        media_children = [
            child
            for child in traversed_children.get(directory, [])
            if child in contains_media
        ]
        media_children.sort(
            key=lambda path: (
                unicodedata.normalize("NFC", path.name).casefold(),
                path.name,
            )
        )
        if directory in direct_media:
            add_inferred_course(
                directory,
                reason="contains media directly",
                singleton_chain=singleton_chain,
            )
            return
        if directory_children_form_course(media_children):
            child_examples = ", ".join(child.name for child in media_children[:4])
            if len(media_children) > 4:
                child_examples += f", … (+{len(media_children) - 4})"
            add_inferred_course(
                directory,
                reason=f"module layout: {child_examples}",
                singleton_chain=singleton_chain,
            )
            return
        if media_children:
            relative = (
                "."
                if directory == input_root
                else directory.relative_to(input_root).as_posix()
            )
            child_examples = ", ".join(child.name for child in media_children[:6])
            if len(media_children) > 6:
                child_examples += f", … (+{len(media_children) - 6})"
            notes.append(
                f"GROUP {relative}: descended into {len(media_children)} "
                f"media-bearing children [{child_examples}]"
            )
        next_chain = (
            [*singleton_chain, directory]
            if len(media_children) == 1
            else []
        )
        for child in media_children:
            visit(child, next_chain)

    visit(input_root, [])
    if not inferred:
        errors.append(f"no course media found below library root: {input_root}")
        return [], notes, errors

    inferred.sort(
        key=lambda course: (
            unicodedata.normalize("NFC", course.root.as_posix()).casefold(),
            course.root.as_posix(),
        )
    )
    return inferred, notes, []


def resolve_courses(
    raw_roots: list[str], discover_course_roots: bool
) -> tuple[list[Path], list[Course], list[str]]:
    input_roots = validate_input_roots(raw_roots)
    if not discover_course_roots:
        return input_roots, [Course(root) for root in input_roots], []

    courses: list[Course] = []
    notes: list[str] = []
    errors: list[str] = []
    for input_root in input_roots:
        inferred, input_notes, inference_errors = infer_course_roots(input_root)
        courses.extend(inferred)
        notes.extend(f"{input_root}: {note}" for note in input_notes)
        errors.extend(inference_errors)

    for index, first in enumerate(courses):
        for second in courses[index + 1 :]:
            if path_overlap(first.root, second.root):
                errors.append(
                    f"inferred course roots overlap: {first.root} and "
                    f"{second.root}"
                )
    if errors:
        raise PreflightError(errors)
    return input_roots, courses, notes


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
    discover_course_roots: bool = False,
) -> Preflight:
    input_roots, courses, inference_notes = resolve_courses(
        raw_roots, discover_course_roots
    )
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
        input_roots=input_roots,
        courses=courses,
        items=all_items,
        programs=Programs(whisperkit=whisperkit, ffmpeg=ffmpeg),
        work_total=work_total,
        discovered_course_roots=discover_course_roots,
        inference_notes=inference_notes,
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
    if preflight.discovered_course_roots:
        print(
            f"Inferred course roots: inputs={len(preflight.input_roots)} "
            f"courses={len(preflight.courses)}",
            flush=True,
        )
        review_count = sum(
            course.review_reason is not None for course in preflight.courses
        )
        print(
            f"Inference review: required={review_count}",
            flush=True,
        )
        print("Inference grouping evidence:", flush=True)
        for note in preflight.inference_notes:
            print(f"  {note}", flush=True)
        for input_root in preflight.input_roots:
            print(f"Library root: {input_root}", flush=True)
            for course in preflight.courses:
                if course.root.is_relative_to(input_root):
                    print(
                        f"  Course root: {course.root} "
                        f"[{course.discovery_reason}]",
                        flush=True,
                    )
                    if course.review_reason:
                        print(
                            f"    REVIEW: {course.review_reason}",
                            flush=True,
                        )
    for course in preflight.courses:
        print(f"Course: {course.root}", flush=True)
        course_items = [item for item in preflight.items if item.course == course]
        total = len(course_items)
        for index, item in enumerate(course_items, start=1):
            prefix = f"[{course.name} {index}/{total}]"
            if item.existing:
                print(
                    f"{prefix} SKIP existing transcripts/{item.relative_output}",
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
        summary = summary_for_course(preflight, course)
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
    """Use macOS RENAME_EXCL; return False when a hard-link fallback is needed."""

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


def install_transcript(
    parent_fd: int, destination_name: str, transcript: str
) -> str | None:
    part_name = (
        f".{destination_name}.{os.getpid()}.{secrets.token_hex(8)}.part"
    )
    open_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_CLOEXEC"):
        open_flags |= os.O_CLOEXEC
    if hasattr(os, "O_NOFOLLOW"):
        open_flags |= os.O_NOFOLLOW

    part_created = False
    try:
        part_fd = os.open(part_name, open_flags, 0o600, dir_fd=parent_fd)
        part_created = True
        with os.fdopen(part_fd, "w", encoding="utf-8", newline="") as part_file:
            if transcript:
                part_file.write(transcript)
                if not transcript.endswith("\n"):
                    part_file.write("\n")
            part_file.flush()
            os.fsync(part_file.fileno())

        if not exclusive_rename(parent_fd, part_name, destination_name):
            os.link(
                part_name,
                destination_name,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            os.unlink(part_name, dir_fd=parent_fd)
        part_created = False
        return None
    except FileExistsError:
        return "destination appeared after preflight; existing path was not changed"
    except OSError as exc:
        return f"could not install transcript atomically: {exc}"
    finally:
        if part_created:
            try:
                os.unlink(part_name, dir_fd=parent_fd)
            except OSError:
                pass


def transcribe_item(
    item: WorkItem, programs: Programs, parent_fd: int
) -> str | None:
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
                    return f"audio extraction failed: {error}"
                transcript, error = run_whisperkit(wav_path, programs.whisperkit)
        except OSError as exc:
            return f"could not create temporary audio workspace: {exc}"
    if error:
        return error
    assert transcript is not None
    return install_transcript(parent_fd, item.relative_output.name, transcript)


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
            error = transcribe_item(item, preflight.programs, parent_fd)
        except OSError as exc:
            error = f"unsafe output path or directory creation failed: {exc}"
        finally:
            if parent_fd is not None:
                os.close(parent_fd)

        if error:
            summary.failed += 1
            print(
                f"{prefix} FAIL {item.relative_media}: {error}",
                file=sys.stderr,
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
    set_title(title, "batch-transcribe-courses preflight")
    try:
        preflight = perform_preflight(
            args.roots,
            args.limit,
            discover_course_roots=args.discover_course_roots,
        )
    except PreflightError as exc:
        set_title(title, "batch-transcribe-courses preflight-failed")
        for error in exc.errors:
            print(f"error: {error}", file=sys.stderr)
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
        review_courses = [
            course for course in preflight.courses if course.review_reason
        ]
        if review_courses:
            print(
                "error: inferred course boundaries require LLM review; "
                "inspect the marked subtrees and rerun with the complete "
                "corrected course-root list in explicit mode",
                file=sys.stderr,
                flush=True,
            )
            set_title(title, "batch-transcribe-courses review-required")
            return 2
        set_title(title, "batch-transcribe-courses preflight-complete")
        return 0
    review_courses = [
        course for course in preflight.courses if course.review_reason
    ]
    if review_courses:
        print(
            "error: live discovery is blocked because inferred course "
            "boundaries require LLM review; run the dry-run, inspect the "
            "marked subtrees, and rerun with explicit course roots",
            file=sys.stderr,
            flush=True,
        )
        set_title(title, "batch-transcribe-courses review-required")
        return 2
    return run_live(preflight, title)


if __name__ == "__main__":
    raise SystemExit(main())
