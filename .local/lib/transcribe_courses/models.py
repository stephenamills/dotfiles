from .config import *

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


class VolumeUnavailable(Exception):
    """The filesystem containing a course disappeared and did not recover."""

    def __init__(self, volume_root: Path, detail: str | None = None):
        self.volume_root = volume_root
        message = detail or f"volume unavailable: {volume_root}"
        super().__init__(message)

