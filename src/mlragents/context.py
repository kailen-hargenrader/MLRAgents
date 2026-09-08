"""The fact block injected at session start.

Formatting is separated from collection so the wording is testable without a
cluster, a repository or a clock.
"""

from __future__ import annotations

import getpass
from pathlib import Path

from mlragents import config as config_module
from mlragents import gitinfo
from mlragents.config import ProjectConfig
from mlragents.gitinfo import GitState
from mlragents.registry import Registry, Run, default_path
from mlragents.scheduler import slurm
from mlragents.scheduler.slurm import Job

RECENT_RUN_LIMIT = 5


def session_context(
    cwd: Path,
    user: str,
    jobs: list[Job],
    git_state: GitState,
    runs: list[Run],
    config: ProjectConfig | None,
) -> str:
    if config is None:
        return ""
    lines = [f"MLRAgents: project '{config.name}' at {config.root}"]

    if git_state.branch:
        tree = (
            f"{len(git_state.dirty_files)} uncommitted file(s)"
            if git_state.dirty
            else "clean"
        )
        lines.append(f"git: {git_state.branch} @ {(git_state.sha or '')[:8]} ({tree})")

    if config.scheduler_kind == "slurm":
        if jobs:
            lines.append(f"slurm ({user}): {len(jobs)} job(s)")
            for job in jobs[:RECENT_RUN_LIMIT]:
                lines.append(
                    f"  {job.job_id} {job.name} {job.state} {job.elapsed} {job.node}"
                )
        else:
            lines.append(f"slurm ({user}): no jobs queued")

    if runs:
        lines.append(f"recent runs (last {len(runs)}):")
        for run in runs:
            label = run.cell or run.grid or run.run_id
            lines.append(f"  {label} {run.status} job={run.job_id or '-'}")
    else:
        lines.append("recent runs: registry empty (run `mlragents runs sync`)")

    return "\n".join(lines)


def gather(cwd: Path, user: str | None = None) -> str:
    cwd = Path(cwd)
    user = user or getpass.getuser()
    config = config_module.find_project(cwd)
    if config is None:
        return ""
    jobs = slurm.queue(user) if config.scheduler_kind == "slurm" else []
    runs: list[Run] = []
    registry_path = default_path(config.root)
    if registry_path.is_file():
        runs = Registry(registry_path).list(limit=RECENT_RUN_LIMIT)
    return session_context(
        cwd=cwd,
        user=user,
        jobs=jobs,
        git_state=gitinfo.describe(config.root),
        runs=runs,
        config=config,
    )
