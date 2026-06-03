from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, AsyncGenerator

import config
from .database import JobDatabase
from .enums import JobStatus

if TYPE_CHECKING:
    from backend.processor import ProgressEvent


@dataclass
class JobState:
    """Runtime snapshot for a single processing job."""
    job_id: str
    status: JobStatus = JobStatus.PENDING
    video_path: Path = field(default_factory=Path)
    screenshots_dir: Path = field(default_factory=Path)
    output_path: Path = field(default_factory=Path)
    screenshot_count: int = 0
    error_message: str = ""
    queue: asyncio.Queue[ProgressEvent] | None = None
    # persisted fields
    video_filename: str = ""
    output_filename: str = "output.docx"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


_db = JobDatabase(config.DATABASE_PATH)


class JobStore:
    _instance: JobStore | None = None

    def __new__(cls) -> JobStore:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._jobs: dict[str, JobState] = {}
        return cls._instance

    def create(self, video_path: Path, video_filename: str = "") -> JobState:
        """Create a new job, persist to SQLite, and return its state."""
        job_id = str(uuid.uuid4())
        screenshots_dir = config.SCREENSHOTS_DIR / job_id
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")
        output_filename = f"截图整理_{ts}.docx"
        output_path = config.OUTPUTS_DIR / job_id / output_filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        state = JobState(
            job_id=job_id,
            video_path=video_path,
            screenshots_dir=screenshots_dir,
            output_path=output_path,
            video_filename=video_filename,
            output_filename=output_filename,
            created_at=datetime.now().isoformat(),
        )
        self._jobs[job_id] = state
        _db.save(state)
        return state

    def get(self, job_id: str) -> JobState:
        if job_id not in self._jobs:
            raise KeyError(job_id)
        return self._jobs[job_id]

    def list_all(self) -> list[JobState]:
        return sorted(self._jobs.values(), key=lambda s: s.created_at, reverse=True)

    def update_status(self, job_id: str, status: JobStatus, **kwargs) -> None:
        state = self.get(job_id)
        state.status = status
        for key, val in kwargs.items():
            setattr(state, key, val)
        _db.update(state)

    def delete(self, job_id: str) -> None:
        if job_id in self._jobs:
            del self._jobs[job_id]
        _db.delete(job_id)


_store = JobStore()


@asynccontextmanager
async def lifespan(app):
    """Restore all historical jobs from SQLite into memory on startup."""
    for row in _db.load_all():
        job_id = row["job_id"]
        status_str = row["status"]
        error_message = row.get("error_message") or ""

        # Jobs interrupted by a server restart are marked as error
        if status_str in ("processing", "generating"):
            status_str = "error"
            error_message = "服务重启，任务中断"
            tmp = JobState(
                job_id=job_id,
                status=JobStatus.ERROR,
                screenshot_count=row.get("screenshot_count", 0),
                error_message=error_message,
                video_filename=row.get("video_filename") or "",
                output_filename=row.get("output_filename") or "output.docx",
                created_at=row["created_at"],
            )
            _db.update(tmp)

        output_filename = row.get("output_filename") or "output.docx"
        state = JobState(
            job_id=job_id,
            status=JobStatus(status_str),
            video_path=Path(row["video_path"]) if row.get("video_path") else Path(),
            screenshots_dir=config.SCREENSHOTS_DIR / job_id,
            output_path=config.OUTPUTS_DIR / job_id / output_filename,
            screenshot_count=row.get("screenshot_count", 0),
            error_message=error_message,
            video_filename=row.get("video_filename") or "",
            output_filename=output_filename,
            created_at=row["created_at"],
        )
        _store._jobs[job_id] = state
    yield
