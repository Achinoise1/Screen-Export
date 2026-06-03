from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path

import config
from fastapi import APIRouter, BackgroundTasks, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from backend.processor import ProcessParams
from .enums import JobStatus
from .models import JobListItem, JobResponse, ProcessRequest
from .store import _store
from .tasks import _run_docx_builder, _run_processor, _sse_generator

_FRONTEND_HTML = Path(__file__).parent.parent / "frontend" / "index.html"

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    """Return the frontend single-page app."""
    return HTMLResponse(_FRONTEND_HTML.read_text(encoding="utf-8"))


@router.get("/jobs", response_model=list[JobListItem])
async def list_jobs() -> list[JobListItem]:
    """Return all job history (with file-existence flags), newest first."""
    result = []
    for state in _store.list_all():
        result.append(JobListItem(
            job_id=state.job_id,
            status=state.status.value,
            video_filename=state.video_filename,
            screenshot_count=state.screenshot_count,
            output_filename=state.output_filename,
            error_message=state.error_message,
            created_at=state.created_at,
            has_screenshots=(
                state.screenshots_dir.exists()
                and any(state.screenshots_dir.glob("page_*.png"))
            ),
            has_docx=state.output_path.exists(),
        ))
    return result


@router.post("/jobs/upload")
async def upload_video(file: UploadFile) -> dict:
    """Upload a video file and return a new job_id."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        raise HTTPException(status_code=400, detail=f"不支持的视频格式：{suffix}")

    tmp_id = str(uuid.uuid4())
    video_path = config.UPLOAD_DIR / f"{tmp_id}{suffix}"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    video_path.write_bytes(content)

    safe_filename = Path(file.filename).name
    state = _store.create(video_path, video_filename=safe_filename)
    return {"job_id": state.job_id}


@router.post("/jobs/{job_id}/process")
async def start_process(
    job_id: str,
    req: ProcessRequest,
    background: BackgroundTasks,
) -> dict:
    """Start the video processing background task."""
    try:
        state = _store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job 不存在")

    if state.status not in (JobStatus.PENDING, JobStatus.ERROR):
        raise HTTPException(status_code=409, detail=f"Job 当前状态为 {state.status}，无法重新处理")

    params = ProcessParams(
        sample_fps=req.sample_fps,
        change_threshold=req.change_threshold,
        stable_seconds=req.stable_seconds,
        hash_threshold=req.hash_threshold,
    )
    state.queue = asyncio.Queue()
    _store.update_status(job_id, JobStatus.PROCESSING)
    background.add_task(_run_processor, job_id, params)
    return {"job_id": job_id, "status": state.status}


@router.get("/jobs/{job_id}/progress")
async def stream_progress(job_id: str) -> StreamingResponse:
    """SSE endpoint that streams real-time processing progress."""
    try:
        state = _store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job 不存在")

    return StreamingResponse(
        _sse_generator(state),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """Return the current status of a job."""
    try:
        state = _store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job 不存在")

    return JobResponse(
        job_id=state.job_id,
        status=state.status.value,
        video_filename=state.video_filename,
        screenshot_count=state.screenshot_count,
        output_filename=state.output_filename,
        error_message=state.error_message,
        has_screenshots=(
            state.screenshots_dir.exists()
            and any(state.screenshots_dir.glob("page_*.png"))
        ),
        has_docx=state.output_path.exists(),
    )


@router.get("/jobs/{job_id}/screenshots")
async def list_screenshots(job_id: str) -> dict:
    """Return the list of screenshot filenames for a job."""
    try:
        state = _store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job 不存在")

    files = sorted(state.screenshots_dir.glob("page_*.png"))
    return {"screenshots": [f.name for f in files]}


@router.get("/jobs/{job_id}/screenshots/{filename}")
async def get_screenshot(job_id: str, filename: str) -> FileResponse:
    """Return a single screenshot file."""
    try:
        state = _store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job 不存在")

    safe_name = Path(filename).name
    img_path = state.screenshots_dir / safe_name
    if not img_path.exists() or not img_path.is_relative_to(state.screenshots_dir):
        raise HTTPException(status_code=404, detail="截图文件不存在")

    return FileResponse(img_path, media_type="image/png")


@router.post("/jobs/{job_id}/generate-docx")
async def generate_docx(job_id: str, background: BackgroundTasks) -> dict:
    """Start the DOCX generation background task."""
    try:
        state = _store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job 不存在")

    if state.status != JobStatus.READY:
        raise HTTPException(status_code=409, detail=f"Job 状态为 {state.status}，需先完成视频处理")

    _store.update_status(job_id, JobStatus.GENERATING)
    background.add_task(_run_docx_builder, job_id)
    return {"job_id": job_id, "status": JobStatus.GENERATING}


@router.get("/jobs/{job_id}/download")
async def download_docx(job_id: str) -> FileResponse:
    """Download the generated DOCX file with its timestamped filename."""
    try:
        state = _store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job 不存在")

    if state.status != JobStatus.DONE:
        raise HTTPException(status_code=409, detail=f"DOCX 尚未生成，当前状态：{state.status}")

    if not state.output_path.exists():
        raise HTTPException(status_code=404, detail="输出文件不存在")

    return FileResponse(
        state.output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=state.output_filename,
    )


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    """Delete a job and all its associated files from disk."""
    try:
        state = _store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job 不存在")

    shutil.rmtree(state.screenshots_dir, ignore_errors=True)
    shutil.rmtree(state.output_path.parent, ignore_errors=True)
    state.video_path.unlink(missing_ok=True)
    _store.delete(job_id)
    return {"deleted": job_id}
