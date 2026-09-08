"""Rebuild the registry from the substrate.

A run directory is one that carries a resolved config. That is the only
structural assumption made about an outputs tree, and it holds for Hydra and for
any layout that writes its config beside its artefacts.
"""

from __future__ import annotations

import os
from pathlib import Path

from mlragents.config import ProjectConfig
from mlragents.registry import Registry, Run, default_path
from mlragents.scheduler.slurm import Job

CONFIG_MARKERS = (".hydra/config.yaml", "config.yaml")


def _is_run_dir(path: Path) -> bool:
    return any((path / marker).is_file() for marker in CONFIG_MARKERS)


def _walk_visible(root: Path):
    """Yield directories under root, never descending into hidden ones.

    A hidden directory is never a run directory, and skipping them keeps a
    config-carrying metadata directory such as .hydra from being mistaken for
    the run that owns it. It also keeps the walk out of .git.
    """
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        if Path(dirpath) != root:
            yield Path(dirpath)


def discover_outputs(config: ProjectConfig) -> list[Run]:
    outputs_root = config.resolve("outputs")
    if not outputs_root.is_dir():
        return []
    runs = []
    for path in _walk_visible(outputs_root):
        if not _is_run_dir(path):
            continue
        relative = path.relative_to(outputs_root)
        parts = relative.parts
        runs.append(
            Run(
                run_id=relative.as_posix(),
                grid=parts[0] if len(parts) > 1 else None,
                cell=parts[1] if len(parts) > 2 else None,
                outputs_path=str(path),
            )
        )
    return runs


def merge_jobs(runs: list[Run], jobs: list[Job]) -> list[Run]:
    by_id = {job.job_id: job for job in jobs}
    for run in runs:
        job = by_id.get(run.job_id) if run.job_id else None
        if job is None:
            continue
        run.status = job.state
        run.node = job.node or run.node
        if job.state not in {"RUNNING", "PENDING"}:
            run.finished_at = run.finished_at or job.elapsed
    return runs


def sync(config: ProjectConfig, jobs: list[Job]) -> int:
    runs = merge_jobs(discover_outputs(config), jobs)
    registry = Registry(default_path(config.root))
    for run in runs:
        registry.record(run)
    return len(runs)
