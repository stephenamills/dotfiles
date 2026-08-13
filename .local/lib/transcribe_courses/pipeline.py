from .config import *
from .models import *
from .state import *
from .state import _record_run_event
from .discovery import *
from .worker import *
from .media import *

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
            if not wait_for_volume(volume, review_log, active_run_log()):
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
                if wait_for_volume(volume, review_log, active_run_log()):
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
        metrics = last_engine_metrics()
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
                if wait_for_volume(volume, review_log, active_run_log()):
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
                        if media_path_is_ignored(media):
                            continue
                        if not media_path_is_eligible(media, allowed_extensions):
                            try:
                                media_stat = media.lstat()
                            except OSError as exc:
                                raise_if_volume_unavailable(exc, media)
                                discovery_errors.append(
                                    f"could not inspect file candidate {media}: {exc}"
                                )
                                continue
                            if stat.S_ISREG(media_stat.st_mode):
                                discovery_errors.append(
                                    f"{media}: {unsupported_file_type_error(media)}"
                                )
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
                            f"transcribe-courses [{course_label}] "
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
                if wait_for_volume(volume, review_log, active_run_log()):
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
            f"transcribe-courses [{selected_index}/{preflight.work_total}] "
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
        set_title(title, f"transcribe-courses failed={combined.failed}")
        return 1
    set_title(
        title,
        f"transcribe-courses complete={combined.succeeded} "
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
            set_title(title, "transcribe-courses validation-failed")
            for error in exc.errors:
                print(f"error: {error}", file=sys.stderr, flush=True)
            return 2
    if not roots:
        set_title(title, "transcribe-courses no-valid-roots")
        print("error: no valid course roots to process", file=sys.stderr, flush=True)
        return 2
    if start_index < 0 or start_index >= len(roots):
        set_title(title, "transcribe-courses invalid-resume-cursor")
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
                f"transcribe-courses scan "
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
                    if wait_for_volume(volume, review_log, active_run_log()):
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
                f"transcribe-courses course "
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
                    if wait_for_volume(volume, review_log, active_run_log()):
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
