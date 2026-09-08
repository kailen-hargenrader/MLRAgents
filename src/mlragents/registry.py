"""A cache of run provenance.

Every column here is recoverable from outputs/, git and sacct. Nothing may
depend on a row that only this database has; `mlragents runs sync` rebuilds it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, fields
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    grid         TEXT,
    cell         TEXT,
    config_path  TEXT,
    config_hash  TEXT,
    git_sha      TEXT,
    git_dirty    INTEGER NOT NULL DEFAULT 0,
    seed         INTEGER,
    job_id       TEXT,
    node         TEXT,
    submitted_at TEXT,
    finished_at  TEXT,
    status       TEXT NOT NULL DEFAULT 'unknown',
    outputs_path TEXT,
    tracker_url  TEXT
);
CREATE INDEX IF NOT EXISTS runs_job_id ON runs(job_id);
CREATE INDEX IF NOT EXISTS runs_submitted_at ON runs(submitted_at DESC);
"""


@dataclass
class Run:
    run_id: str
    grid: str | None = None
    cell: str | None = None
    config_path: str | None = None
    config_hash: str | None = None
    git_sha: str | None = None
    git_dirty: bool = False
    seed: int | None = None
    job_id: str | None = None
    node: str | None = None
    submitted_at: str | None = None
    finished_at: str | None = None
    status: str = "unknown"
    outputs_path: str | None = None
    tracker_url: str | None = None


COLUMNS = [f.name for f in fields(Run)]


def default_path(root: Path) -> Path:
    return Path(root) / ".mlragents" / "registry.sqlite"


class Registry:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _to_run(row: sqlite3.Row) -> Run:
        data = dict(row)
        data["git_dirty"] = bool(data["git_dirty"])
        return Run(**data)

    def record(self, run: Run) -> None:
        data = asdict(run)
        data["git_dirty"] = int(data["git_dirty"])
        placeholders = ", ".join(f":{name}" for name in COLUMNS)
        with self._connect() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO runs ({', '.join(COLUMNS)}) "
                f"VALUES ({placeholders})",
                data,
            )

    def get(self, run_id: str) -> Run | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return self._to_run(row) if row else None

    def list(
        self,
        limit: int = 20,
        grid: str | None = None,
        status: str | None = None,
    ) -> list[Run]:
        clauses, params = [], []
        if grid is not None:
            clauses.append("grid = ?")
            params.append(grid)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM runs {where} "
                "ORDER BY submitted_at DESC, run_id DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._to_run(row) for row in rows]

    def set_status(self, job_id: str, status: str, finished_at: str | None = None) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE runs SET status = ?, "
                "finished_at = COALESCE(?, finished_at) WHERE job_id = ?",
                (status, finished_at, job_id),
            )
            return cursor.rowcount
