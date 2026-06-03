"""
backend/main.py

FastAPI application entry point.
Business logic is split across:
  enums.py    — JobStatus
  database.py — SQLite persistence (JobDatabase)
  store.py    — runtime state (JobState, JobStore, lifespan)
  models.py   — Pydantic request/response models
  tasks.py    — background tasks and SSE generator
  routes.py   — API route handlers (APIRouter)
"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from backend.routes import router
from backend.store import lifespan

_STATIC_DIR = Path(__file__).parent.parent / "frontend" / "static"

app = FastAPI(
    title="Screenshot-Export",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=config.BACKEND_PORT,
        root_path=config.BACKEND_ROOT_PATH,
        reload=False,
    )
