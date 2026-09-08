"""Submitting a job that stays citable, and judging whether one is.

Provenance is only recoverable at submission time. A queued job outlives the
session that made it, and the commit it ran from is a fact no later scan can
reconstruct — `sacct` does not know it, and the working tree has moved on. So
`submit` records first and refuses rather than submit a job it could not record.

`provenance` runs the inverse: given a run, whether anything in the paper may
depend on it, and if not, exactly what disqualifies it.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from mlragents.config import ProjectConfig
from mlragents.gitinfo import describe
from mlragents.guardrails import DIRTY_OVERRIDE, MAX_LISTED_FILES
from mlragents.registry import Registry, Run, default_path
from mlragents.scheduler import slurm

CITABLE_LANE = "exploit"
SUCCESS_STATES = frozenset({"COMPLETED", "completed"})
PENDING_STATES = frozenset({"PENDING", "RUNNING", "submitted", "unknown"})


class SubmissionRefused(RuntimeError):
    """The job was not submitted, because its provenance could not be recorded."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def submit(
    config: ProjectConfig,
    script: str,
    lane: str,
    grid: str | None = None,
    cell: str | None = None,
    config_path: str | None = None,
    seed: int | None = None,
    args: list[str] | None = None,
    run=subprocess.run,
) -> dict:
    """Submit `script` and record what it was.

    The lane is required and not inferred. Whether a run is evidence or insight
    is the one thing about it that cannot be recovered from the filesystem
    later, and asking for it here is cheaper than discovering in a manuscript
    that it was assumed.
    """
    lane_obj = config.lane(lane)  # raises with the declared lanes named
    if config.scheduler_kind != "slurm":
        raise SubmissionRefused(
            f"the project declares scheduler.kind = {config.scheduler_kind!r}; "
            "jobs_submit needs 'slurm'"
        )

    script_path = (config.root / script).resolve()
    if not script_path.is_file():
        raise SubmissionRefused(f"no such submission script: {script_path}")

    git = describe(config.root)
    if git.sha is None:
        raise SubmissionRefused(
            f"{config.root} is not a git repository, so this run could not be "
            "attributed to any commit."
        )
    override = bool(os.environ.get(DIRTY_OVERRIDE))
    if git.dirty and not override:
        listed = ", ".join(git.dirty_files[:MAX_LISTED_FILES])
        raise SubmissionRefused(
            f"the working tree is dirty ({listed}), so this job could not be "
            f"reproduced from any commit. Commit first, or set {DIRTY_OVERRIDE}=1 "
            "to submit a deliberately non-citable run."
        )

    command = ["sbatch", *(args or []), str(script_path)]
    completed = run(
        command, cwd=str(config.root), capture_output=True, text=True, check=False
    )
    job_id = slurm.parse_sbatch_job_id(completed.stdout or "")
    if completed.returncode != 0 or job_id is None:
        raise SubmissionRefused(
            "sbatch did not report a job id, so nothing was recorded. "
            f"exit {completed.returncode}: "
            f"{(completed.stderr or completed.stdout or '').strip()[:400]}"
        )

    record = Run(
        run_id=f"{lane}/job/{job_id}",
        lane=lane,
        grid=grid,
        cell=cell,
        config_path=config_path,
        git_sha=git.sha,
        git_dirty=git.dirty,
        seed=seed,
        job_id=job_id,
        submitted_at=_now(),
        status="submitted",
        outputs_path=str(lane_obj.outputs_dir(config.root)),
    )
    Registry(default_path(config.root)).record(record)
    return {
        "job_id": job_id,
        "run_id": record.run_id,
        "lane": lane,
        "git_sha": git.sha,
        "git_dirty": git.dirty,
        "citable": lane == CITABLE_LANE and not git.dirty,
        "recorded": True,
    }


def provenance(config: ProjectConfig, run_id: str) -> dict:
    """Whether the paper may depend on this run, and what disqualifies it.

    Reasons are returned rather than a bare boolean: "not citable" is not
    actionable, and "the tree was dirty at submission" is.
    """
    path = default_path(config.root)
    if not path.is_file():
        return {
            "run_id": run_id,
            "found": False,
            "citable": False,
            "reasons": ["no registry yet; run `mlragents runs sync`"],
        }
    record = Registry(path).get(run_id)
    if record is None:
        return {
            "run_id": run_id,
            "found": False,
            "citable": False,
            "reasons": [f"no run {run_id!r} in the registry"],
        }

    reasons = []
    if record.lane != CITABLE_LANE:
        reasons.append(
            f"the run is in the {record.lane!r} lane, which is insight and never "
            "evidence; only exploit runs may be cited"
        )
    if not record.git_sha:
        reasons.append("no commit was recorded, so the code that produced it is unknown")
    if record.git_dirty:
        reasons.append(
            "the working tree was dirty at submission, so no commit reproduces it"
        )
    if record.status in PENDING_STATES:
        reasons.append(f"the run has not finished (status {record.status!r})")
    elif record.status not in SUCCESS_STATES:
        reasons.append(f"the run did not complete successfully (status {record.status!r})")

    return {
        "run_id": run_id,
        "found": True,
        "citable": not reasons,
        "reasons": reasons,
        "lane": record.lane,
        "grid": record.grid,
        "cell": record.cell,
        "git_sha": record.git_sha,
        "git_dirty": record.git_dirty,
        "seed": record.seed,
        "job_id": record.job_id,
        "status": record.status,
        "config_path": record.config_path,
        "outputs_path": record.outputs_path,
        "tracker_url": record.tracker_url,
    }
