from .config import *
from .models import *
from .state import *
from .state import _record_run_event
from .worker import bootstrap_worker, resolve_program, worker_cache_path

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
    if wait_for_volume(volume, review_log, active_run_log()):
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


def media_path_is_ignored(path: Path) -> bool:
    return path.suffix.casefold() in IGNORED_MEDIA_EXTENSIONS


def unsupported_file_type_error(path: Path) -> str:
    suffix = path.suffix.casefold() or "<no extension>"
    return f"unsupported file type {suffix}; allowlisted media types only"


def direct_media_files(root: Path) -> list[Path]:
    """Return regular media files directly beneath a hierarchy directory."""
    allowed = VIDEO_EXTENSIONS if is_music_tree(root) else MEDIA_EXTENSIONS
    media: list[Path] = []
    try:
        with os.scandir(root) as entries:
            for entry in entries:
                try:
                    path = Path(entry.path)
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if media_path_is_ignored(path):
                        continue
                    if media_path_is_eligible(path, allowed):
                        media.append(path)
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
        if Path(token).name in {COMMAND_NAME, "transcribe_courses.py"}
    ]
    if len(script_indices) != 1:
        raise ResumeStateError(
            "stdin must contain exactly one transcribe-courses or "
            "transcribe_courses.py invocation"
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
                if media_path_is_ignored(media):
                    continue
                if not media_path_is_eligible(media, allowed_extensions):
                    try:
                        media_stat = media.lstat()
                    except OSError as exc:
                        errors.append(f"could not inspect file candidate {media}: {exc}")
                        continue
                    if stat.S_ISREG(media_stat.st_mode):
                        errors.append(f"{media}: {unsupported_file_type_error(media)}")
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
