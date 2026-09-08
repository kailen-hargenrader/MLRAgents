"""The denials whose violation would silently corrupt a paper.

Each verdict function returns a reason string when the action must be refused
and None when it must not. They are pure and take their facts as arguments, so
the judgement is testable without a git repository or a cluster.

Every one of them fails open. A guardrail that fires because it could not
establish the facts trains the user to disable it, and a disabled guardrail
protects nothing.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

from mlragents.config import ProjectConfig
from mlragents.gitinfo import describe

SUBMIT_COMMANDS = frozenset({"sbatch", "srun", "salloc"})
DIRTY_OVERRIDE = "MLRAGENTS_ALLOW_DIRTY"
MAX_LISTED_FILES = 5


def dirty_files(root: Path) -> tuple[str, ...]:
    return describe(root, run=subprocess.run).dirty_files


def _submits(command: str) -> bool:
    """Whether a command line runs a scheduler submission.

    Tokenised rather than substring-matched, so `echo resbatching` is not a
    submission. Unparseable input is treated as no submission: this gate exists
    to catch the ordinary case, and refusing on a quoting error would be the
    kind of misfire that gets the whole mechanism turned off.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    return any(Path(token).name in SUBMIT_COMMANDS for token in tokens)


def submission_verdict(
    config: ProjectConfig, command: str, dirty: tuple[str, ...]
) -> str | None:
    """Refuse a scheduler submission from a tree that cannot be reconstructed.

    A queued job outlives the session that made it. If the code it ran is not
    committed, the run's provenance is already lost by the time anyone notices,
    and no later check can recover it. That is why this is enforced here rather
    than asked for in a prompt.
    """
    if config.scheduler_kind != "slurm" or not dirty or not _submits(command):
        return None
    if os.environ.get(DIRTY_OVERRIDE):
        return None
    listed = ", ".join(dirty[:MAX_LISTED_FILES])
    more = f" and {len(dirty) - MAX_LISTED_FILES} more" if len(dirty) > MAX_LISTED_FILES else ""
    return (
        f"The working tree is dirty ({listed}{more}), so a job submitted now "
        "could not be reproduced from any commit. Commit or stash first. If "
        f"this run is deliberately throwaway, set {DIRTY_OVERRIDE}=1 for the "
        "session — but its results are then not citable."
    )


def generated_verdict(config: ProjectConfig, target: Path) -> str | None:
    """Refuse a hand-edit to a tree that a generator owns.

    Editing one generated config is how a second axis enters an ablation
    without anyone deciding to add it, and the resulting config still sits
    beside the artefacts looking authoritative.
    """
    generated = config.generated_dirs()
    if not generated:
        return None
    resolved = Path(target).resolve()
    if not any(d == resolved or d in resolved.parents for d in generated):
        return None
    try:
        generator = config.command("generate")
        instruction = f"Change the generator and regenerate: {generator}"
    except KeyError:
        instruction = (
            "Change the generator that writes this tree and regenerate. "
            "Declaring commands.generate in .mlragents.toml would name it here."
        )
    return (
        f"{target} is generated. Editing it by hand makes the config that sits "
        "beside the run's artefacts stop describing what produced them. "
        f"{instruction}"
    )


JOB_ID = re.compile(r"Submitted batch job (\d+)")


def submitted_job_id(output: str) -> str | None:
    """The job id Slurm reports, or None.

    Read from the submission's own output rather than by polling the queue
    afterwards, which would race with a job that finishes immediately.
    """
    match = JOB_ID.search(output or "")
    return match.group(1) if match else None


NUMBER = re.compile(r"(?<![\w\\.])\d+(?:\.\d+)?(?![\w])")
COMMENT = re.compile(r"(?<!\\)%.*$")
# Structural numbers are not measurements: lengths, font sizes, column counts,
# figure placement and version-like strings say nothing about an experiment.
STRUCTURAL_CONTEXT = re.compile(
    r"\\(?:documentclass|usepackage|setlength|vspace|hspace|includegraphics|"
    r"begin|end|cite|ref|label|input|include|scalebox|resizebox|multicolumn|"
    r"multirow|cmidrule|columnwidth|textwidth|linewidth|arraystretch|"
    r"section|subsection|footnote|url|href|newcommand|renewcommand|def)"
)


def numeric_literals(tex: str) -> list[tuple[int, str]]:
    """Lines carrying a number that looks like a measurement.

    Deliberately conservative in what it *ignores* and permissive in what it
    flags: this feeds a warning a human reads, so a false positive costs a
    glance while a false negative costs a wrong number in a published table.
    """
    found = []
    for number, line in enumerate(tex.splitlines(), start=1):
        stripped = COMMENT.sub("", line)
        if not stripped.strip() or STRUCTURAL_CONTEXT.search(stripped):
            continue
        if NUMBER.search(stripped):
            found.append((number, line.strip()))
    return found
