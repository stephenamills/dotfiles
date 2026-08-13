from .config import *
from .models import *
from .state import *
from .state import _record_run_event
from .discovery import *
from .worker import *

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
                if stderr and active_run_log() is not None:
                    active_run_log().event(
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
            prefix="transcribe-courses-"
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

