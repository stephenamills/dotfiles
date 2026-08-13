from .config import *
from .models import *

# Process-local runtime state belongs with the run/checkpoint log lifecycle.
_ACTIVE_RUN_LOG: "RunLog | None" = None
_ACTIVE_RUN_ID: str | None = None

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


def active_run_log() -> "RunLog | None":
    return _ACTIVE_RUN_LOG


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
        from .worker import worker_cache_path

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
            resume = [COMMAND_NAME, "--resume", str(checkpoint_path)]
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
            COMMAND_NAME,
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
        [COMMAND_NAME, "--retry-failed", str(checkpoint.path)]
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


