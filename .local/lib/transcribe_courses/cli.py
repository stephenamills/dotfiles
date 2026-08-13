from .config import *
from .models import *
from .state import *
from .state import _record_run_event
from .discovery import *
from .worker import *
from .media import *
from .pipeline import *

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
        argv=list(sys.argv if raw_argv is None else [COMMAND_NAME, *raw_argv]),
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
        set_title(title, "transcribe-courses expanding-topic-roots")
        roots = expand_topic_roots(roots, review_log)
        print(
            f"TOPIC ROOTS expanded topics={len(args.roots)} "
            f"courses={len(roots)} review={review_log.issue_count}",
            flush=True,
        )
        if not roots:
            set_title(title, "transcribe-courses no-valid-topic-roots")
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
        set_title(title, "transcribe-courses expanding-author-roots")
        roots = expand_author_roots(roots, review_log)
        print(
            f"AUTHOR ROOTS expanded authors={len(args.roots)} "
            f"courses={len(roots)} review={review_log.issue_count}",
            flush=True,
        )
        if not roots:
            set_title(title, "transcribe-courses no-valid-author-roots")
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
    set_title(title, "transcribe-courses preflight")
    try:
        preflight = perform_preflight(
            roots,
            args.limit,
            options,
            ignore_omega_directories=args.topic_roots,
        )
    except PreflightError as exc:
        set_title(title, "transcribe-courses preflight-failed")
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
        set_title(title, "transcribe-courses preflight-complete")
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
