from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from backend.processor import DocxBuilder, ProgressEvent, VideoProcessor
from .enums import JobStatus
from .store import JobState, _store


async def _run_processor(job_id: str, params) -> None:
    state = _store.get(job_id)
    processor = VideoProcessor(state.video_path, state.screenshots_dir, params)
    try:
        count = await processor.run(state.queue)
        _store.update_status(job_id, JobStatus.READY, screenshot_count=count)
    except Exception as exc:
        _store.update_status(job_id, JobStatus.ERROR, error_message=str(exc))


async def _run_docx_builder(job_id: str) -> None:
    state = _store.get(job_id)
    builder = DocxBuilder(state.screenshots_dir, state.output_path)
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, builder.build)
        _store.update_status(job_id, JobStatus.DONE)
    except Exception as exc:
        _store.update_status(job_id, JobStatus.ERROR, error_message=str(exc))


async def _sse_generator(state: JobState) -> AsyncGenerator[str, None]:
    for _ in range(50):
        if state.queue is not None:
            break
        await asyncio.sleep(0.1)

    if state.queue is None:
        yield 'data: {"type":"error","message":"Queue 未初始化"}\n\n'
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
