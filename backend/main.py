"""
backend/main.py

FastAPI 应用入口，包含：
  - JobState  dataclass  — 单个 job 的状态快照
  - JobStore  singleton  — 内存 job 生命周期管理
  - 8 个 REST/SSE 路由
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import AsyncGenerator

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

# 将项目根目录加入 sys.path，使 config 可被直接导入
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from backend.processor import DocxBuilder, ProcessParams, ProgressEvent, VideoProcessor


# ──────────────────────────────────────────────────────────────────────────────
# Job 状态枚举
# ──────────────────────────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    GENERATING = "generating"
    DONE = "done"
    ERROR = "error"


# ──────────────────────────────────────────────────────────────────────────────
# Job 数据结构
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class JobState:
    """表示一个处理任务的完整状态。"""
    job_id: str
    status: JobStatus = JobStatus.PENDING
    video_path: Path = field(default_factory=Path)
    screenshots_dir: Path = field(default_factory=Path)
    output_path: Path = field(default_factory=Path)
    screenshot_count: int = 0
    error_message: str = ""
    # asyncio.Queue 用于 SSE 推送，None 表示任务未启动
    queue: asyncio.Queue[ProgressEvent] | None = None


# ──────────────────────────────────────────────────────────────────────────────
# JobStore 单例
# ──────────────────────────────────────────────────────────────────────────────

class JobStore:
    """
    内存 job 仓库（单例）。

    线程安全说明：FastAPI 在单线程 asyncio 事件循环中运行路由函数，
    视频处理在 run_in_executor 线程池中执行但通过 asyncio 通信，
    因此 dict 读写无需额外锁。
    """

    _instance: "JobStore | None" = None

    def __new__(cls) -> "JobStore":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._jobs: dict[str, JobState] = {}
        return cls._instance

    # ── 公共方法 ──────────────────────────────────────

    def create(self, video_path: Path) -> JobState:
        """创建新 job 并返回 JobState。"""
        job_id = str(uuid.uuid4())
        screenshots_dir = config.SCREENSHOTS_DIR / job_id
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        output_path = config.OUTPUTS_DIR / job_id / "output.docx"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        state = JobState(
            job_id=job_id,
            video_path=video_path,
            screenshots_dir=screenshots_dir,
            output_path=output_path,
        )
        self._jobs[job_id] = state
        return state

    def get(self, job_id: str) -> JobState:
        """获取 JobState，不存在时抛出 KeyError。"""
        if job_id not in self._jobs:
            raise KeyError(job_id)
        return self._jobs[job_id]

    def update_status(self, job_id: str, status: JobStatus, **kwargs) -> None:
        """更新 job 状态及附加字段。"""
        state = self.get(job_id)
        state.status = status
        for key, val in kwargs.items():
            setattr(state, key, val)


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI 应用
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Screen-Export API",
    root_path=config.BACKEND_ROOT_PATH,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_store = JobStore()


# ── Pydantic 请求/响应模型 ────────────────────────────

class ProcessRequest(BaseModel):
    sample_fps: int = 5
    change_threshold: float = 3.0
    stable_seconds: float = 2.0
    hash_threshold: int = 5


class JobResponse(BaseModel):
    job_id: str
    status: str
    screenshot_count: int
    error_message: str


# ── 路由 ──────────────────────────────────────────────

@app.post("/jobs/upload")
async def upload_video(file: UploadFile) -> dict:
    """上传视频文件，返回 job_id。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        raise HTTPException(status_code=400, detail=f"不支持的视频格式：{suffix}")

    # 为每次上传创建独立临时文件，避免并发覆盖
    tmp_id = str(uuid.uuid4())
    video_path = config.UPLOAD_DIR / f"{tmp_id}{suffix}"
    video_path.parent.mkdir(parents=True, exist_ok=True)

    content = await file.read()
    video_path.write_bytes(content)

    state = _store.create(video_path)
    return {"job_id": state.job_id}


@app.post("/jobs/{job_id}/process")
async def start_process(
    job_id: str,
    req: ProcessRequest,
    background: BackgroundTasks,
) -> dict:
    """启动视频处理后台任务。"""
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


@app.get("/jobs/{job_id}/progress")
async def stream_progress(job_id: str) -> StreamingResponse:
    """SSE 端点，实时推送处理进度。"""
    try:
        state = _store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job 不存在")

    return StreamingResponse(
        _sse_generator(state),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 告知 nginx 禁用缓冲
        },
    )


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """查询 job 状态。"""
    try:
        state = _store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job 不存在")

    return JobResponse(
        job_id=state.job_id,
        status=state.status.value,
        screenshot_count=state.screenshot_count,
        error_message=state.error_message,
    )


@app.get("/jobs/{job_id}/screenshots")
async def list_screenshots(job_id: str) -> dict:
    """返回截图文件名列表。"""
    try:
        state = _store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job 不存在")

    files = sorted(state.screenshots_dir.glob("page_*.png"))
    return {"screenshots": [f.name for f in files]}


@app.get("/jobs/{job_id}/screenshots/{filename}")
async def get_screenshot(job_id: str, filename: str) -> FileResponse:
    """返回单张截图文件。"""
    try:
        state = _store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job 不存在")

    # 防止路径穿越
    safe_name = Path(filename).name
    img_path = state.screenshots_dir / safe_name
    if not img_path.exists() or not img_path.is_relative_to(state.screenshots_dir):
        raise HTTPException(status_code=404, detail="截图文件不存在")

    return FileResponse(img_path, media_type="image/png")


@app.post("/jobs/{job_id}/generate-docx")
async def generate_docx(job_id: str, background: BackgroundTasks) -> dict:
    """启动 DOCX 生成后台任务。"""
    try:
        state = _store.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Job 不存在")

    if state.status != JobStatus.READY:
        raise HTTPException(status_code=409, detail=f"Job 状态为 {state.status}，需先完成视频处理")

    _store.update_status(job_id, JobStatus.GENERATING)
    background.add_task(_run_docx_builder, job_id)
    return {"job_id": job_id, "status": JobStatus.GENERATING}


@app.get("/jobs/{job_id}/download")
async def download_docx(job_id: str) -> FileResponse:
    """下载生成的 DOCX 文件。"""
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
        filename="output.docx",
    )


# ──────────────────────────────────────────────────────────────────────────────
# 后台任务函数
# ──────────────────────────────────────────────────────────────────────────────

async def _run_processor(job_id: str, params: ProcessParams) -> None:
    """后台任务：运行视频处理器并更新 job 状态。"""
    state = _store.get(job_id)
    processor = VideoProcessor(state.video_path, state.screenshots_dir, params)
    try:
        count = await processor.run(state.queue)
        _store.update_status(job_id, JobStatus.READY, screenshot_count=count)
    except Exception as exc:
        _store.update_status(job_id, JobStatus.ERROR, error_message=str(exc))


async def _run_docx_builder(job_id: str) -> None:
    """后台任务：运行 DOCX 构建器并更新 job 状态。"""
    state = _store.get(job_id)
    builder = DocxBuilder(state.screenshots_dir, state.output_path)
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, builder.build)
        _store.update_status(job_id, JobStatus.DONE)
    except Exception as exc:
        _store.update_status(job_id, JobStatus.ERROR, error_message=str(exc))


async def _sse_generator(state: JobState) -> AsyncGenerator[str, None]:
    """将 queue 中的 ProgressEvent 序列化为 SSE 格式流式输出。"""
    # 等待 queue 就绪（最多 5 秒）
    for _ in range(50):
        if state.queue is not None:
            break
        await asyncio.sleep(0.1)

    if state.queue is None:
        yield "data: {\"type\": \"error\", \"message\": \"Queue 未初始化\"}\n\n"
        return

    while True:
        try:
            event: ProgressEvent = await asyncio.wait_for(state.queue.get(), timeout=30.0)
        except asyncio.TimeoutError:
            yield ": keepalive\n\n"
            continue

        yield f"data: {event.to_json()}\n\n"

        if event.type in ("done", "error"):
            break


# ──────────────────────────────────────────────────────────────────────────────
# 启动入口
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=config.BACKEND_PORT,
        reload=False,
    )
