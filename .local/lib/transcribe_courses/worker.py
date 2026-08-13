from .config import *
from .models import *
from .state import *
from .state import _record_run_event

_ACTIVE_WORKER: "WhisperKitWorker | None" = None
_LAST_ENGINE_METRICS: "EngineMetrics | None" = None


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
        detail = detail[:detail_limit].rstrip() + "..."
    return f"exit {returncode}: {detail}" if detail else f"exit {returncode}"

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
    if stderr and active_run_log() is not None:
        active_run_log().event(
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
                    return None, last_error
                if code == "model_load_failed":
                    model_load_failures += 1
                    reset_worker("mid-run model load failure")
                    if model_load_failures >= 2:
                        return None, last_error
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
                    return None, f"{last_error}; attempts={attempts}"
                elapsed = time.monotonic() - started
                _LAST_ENGINE_METRICS = EngineMetrics(duration, elapsed)
                _record_run_event(
                    "WHISPERKIT TIMING",
                    f"source={source_path or audio_path} "
                    f"worker_seconds={worker_processing_time:.3f} "
                    f"wall_seconds={elapsed:.3f} audio_seconds={duration:.3f}",
                )
                return transcript, None

        if attempt < attempts:
            print(
                f"WHISPERKIT RETRY next={attempt + 1}/{attempts}: {last_error}",
                file=sys.stderr,
                flush=True,
            )
    return None, f"{last_error}; attempts={attempts}"


def last_engine_metrics() -> EngineMetrics | None:
    return _LAST_ENGINE_METRICS

