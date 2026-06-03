from __future__ import annotations

from pydantic import BaseModel


class ProcessRequest(BaseModel):
    sample_fps: int = 5
    change_threshold: float = 3.0
    stable_seconds: float = 2.0
    hash_threshold: int = 5


class JobResponse(BaseModel):
    job_id: str
    status: str
    video_filename: str
    screenshot_count: int
    output_filename: str
    error_message: str
    has_screenshots: bool
    has_docx: bool


class DocxRequest(BaseModel):
    cols: int = 2


class JobListItem(BaseModel):
    job_id: str
    status: str
    video_filename: str
    screenshot_count: int
    output_filename: str
    error_message: str
    created_at: str
    has_screenshots: bool
    has_docx: bool
