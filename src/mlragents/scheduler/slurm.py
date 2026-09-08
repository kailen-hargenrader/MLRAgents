"""Slurm, read through its parsable output formats.

Both formats are pinned here and asserted in tests against output captured from
a live cluster, so a change in Slurm's defaults cannot silently alter parsing.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

SQUEUE_FORMAT = "%i|%j|%T|%M|%R"
SACCT_FORMAT = "JobID,JobName,State,Elapsed,NodeList,ExitCode"

_SBATCH_JOB_ID = re.compile(r"Submitted batch job (\d+)")
_ERROR_LINE = re.compile(
    r"^(?:\w*(?:Error|Exception)\b.*|.*CANCELLED.*|.*Out Of Memory.*)$"
)


@dataclass(frozen=True)
class Job:
    job_id: str
    name: str
    state: str
    elapsed: str
    node: str
    exit_code: str | None = None


UNFINISHED = frozenset({"RUNNING", "PENDING", "SUSPENDED", "REQUEUED", "RESIZING"})


def _parse(text: str, width: int) -> list[Job]:
    jobs = []
    for line in text.splitlines():
        parts = line.strip().split("|")
        if len(parts) < width:
            continue
        state = parts[2]
        exit_code = parts[5] if width > 5 else None
        # sacct prints 0:0 for a job that has not finished; reporting that as an
        # exit code would let a running job read as a clean success.
        if (state.split()[0] if state else "") in UNFINISHED:
            exit_code = None
        jobs.append(
            Job(
                job_id=parts[0],
                name=parts[1],
                state=state,
                elapsed=parts[3],
                node=parts[4],
                exit_code=exit_code,
            )
        )
    return jobs


def parse_squeue(text: str) -> list[Job]:
    return _parse(text, 5)


def parse_sacct(text: str) -> list[Job]:
    return _parse(text, 6)


def _capture(args: list[str], run) -> str | None:
    try:
        result = run(args, capture_output=True, text=True, check=False)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def queue(user: str, run=subprocess.run) -> list[Job]:
    text = _capture(["squeue", "-u", user, "-h", "-o", SQUEUE_FORMAT], run)
    return parse_squeue(text) if text else []


def history(user: str, since: str = "now-7days", run=subprocess.run) -> list[Job]:
    text = _capture(
        [
            "sacct",
            "-u",
            user,
            "-n",
            "-X",
            "--parsable2",
            "--starttime",
            since,
            "--format",
            SACCT_FORMAT,
        ],
        run,
    )
    return parse_sacct(text) if text else []


def parse_sbatch_job_id(text: str) -> str | None:
    match = _SBATCH_JOB_ID.search(text)
    return match.group(1) if match else None


def tail_log(path: Path, lines: int = 40) -> str:
    path = Path(path)
    if not path.is_file():
        return ""
    content = path.read_text(errors="replace").splitlines()
    return "\n".join(content[-lines:])


def first_error(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and _ERROR_LINE.match(stripped):
            return stripped
    return None
