"""Rebuild the registry from the substrate.

A run directory is one that carries a resolved config. That is the only
structural assumption made about an outputs tree, and it holds for Hydra and for
any layout that writes its config beside its artefacts.
"""

from __future__ import annotations

import os
from pathlib import Path

from mlragents.config import Lane, ProjectConfig
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


def match_pattern(parts: tuple[str, ...], pattern: str) -> dict[str, str]:
    """Extract named labels from a run path.

    A pattern is a slash-joined sequence of segments: `{name}` captures the
    component, `*` skips one, `**` skips any number and must come last, and
    anything else must match literally. A pattern that does not match yields no
    labels, because a wrong label is worse than an absent one.
    """
    segments = pattern.split("/")
    labels: dict[str, str] = {}
    for index, segment in enumerate(segments):
        if segment == "**":
            return labels if index == len(segments) - 1 else {}
        if index >= len(parts):
            return {}
        part = parts[index]
        if segment.startswith("{") and segment.endswith("}"):
            labels[segment[1:-1]] = part
        elif segment != "*" and segment != part:
            return {}
    return labels if len(segments) == len(parts) else {}


def discover_outputs(config: ProjectConfig) -> list[Run]:
    """Every run in every declared lane, tagged with the lane it came from.

    The lane is read from the filesystem rather than from anything a model
    asserts, which is what makes it usable as evidence.
    """
    runs = []
    for lane in config.lanes.values():
        runs.extend(_discover_lane(config, lane))
    return runs


def _discover_lane(config: ProjectConfig, lane: Lane) -> list[Run]:
    outputs_root = lane.outputs_dir(config.root)
    if not outputs_root.is_dir():
        return []
    pattern = lane.run_pattern
    patterns = [pattern] if isinstance(pattern, str) else list(pattern or ())
    runs = []
    for path in _walk_visible(outputs_root):
        if not _is_run_dir(path):
            continue
        relative = path.relative_to(outputs_root)
        labels: dict[str, str] = {}
        for candidate in patterns:
            labels = match_pattern(relative.parts, candidate)
            if labels:
                break
        runs.append(
            Run(
                # Lane-qualified, so the same relative path in both trees cannot
                # collide and the lane of a cited run is visible in its id.
                run_id=f"{lane.name}/{relative.as_posix()}",
                lane=lane.name,
                grid=labels.get("grid"),
                cell=labels.get("cell"),
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
