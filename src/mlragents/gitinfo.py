"""Git facts, gathered without ever raising into a caller's face."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitState:
    sha: str | None
    branch: str | None
    dirty_files: tuple[str, ...]

    @property
    def dirty(self) -> bool:
        return bool(self.dirty_files)


def _capture(root: Path, args: list[str], run) -> str | None:
    try:
        result = run(
            ["git", *args], cwd=str(root), capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def describe(root: Path, run=subprocess.run) -> GitState:
    sha = _capture(root, ["rev-parse", "HEAD"], run)
    branch = _capture(root, ["rev-parse", "--abbrev-ref", "HEAD"], run)
    status = _capture(root, ["status", "--porcelain"], run)
    files: tuple[str, ...] = ()
    if status:
        files = tuple(line[3:].strip() for line in status.splitlines() if line.strip())
    return GitState(
        sha=sha.strip() if sha else None,
        branch=branch.strip() if branch else None,
        dirty_files=files,
    )
