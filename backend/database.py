from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import JobState


class JobDatabase:
    """SQLite persistence layer. Creates a new connection per operation for thread safety."""

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id           TEXT PRIMARY KEY,
            status           TEXT NOT NULL,
            video_filename   TEXT DEFAULT '',
            video_path       TEXT DEFAULT '',
            screenshot_count INTEGER DEFAULT 0,
            output_filename  TEXT DEFAULT '',
            error_message    TEXT DEFAULT '',
            created_at       TEXT NOT NULL
        )
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = str(db_path)
        with self._conn() as conn:
            conn.execute(self._SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def save(self, state: JobState) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO jobs
                   (job_id, status, video_filename, video_path,
                    screenshot_count, output_filename, error_message, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    state.job_id, state.status.value,
                    state.video_filename, str(state.video_path),
                    state.screenshot_count, state.output_filename,
                    state.error_message, state.created_at,
                ),
            )

    def update(self, state: JobState) -> None:
        with self._conn() as conn:
            conn.execute(
                """UPDATE jobs SET status=?, screenshot_count=?, error_message=?
                   WHERE job_id=?""",
                (state.status.value, state.screenshot_count,
                 state.error_message, state.job_id),
            )

    def load_all(self) -> list[dict]:
        with self._conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC"
            ).fetchall()]

    def delete(self, job_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM jobs WHERE job_id=?", (job_id,))
