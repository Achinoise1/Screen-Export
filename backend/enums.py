from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    PENDING    = "pending"
    PROCESSING = "processing"
    READY      = "ready"
    GENERATING = "generating"
    DONE       = "done"
    ERROR      = "error"
