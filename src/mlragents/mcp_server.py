"""The MCP surface.

Every tool takes `cwd` explicitly rather than relying on the server process's
working directory, because one server may be asked about more than one
repository during a session.
"""

from __future__ import annotations

import getpass
import subprocess
from dataclasses import asdict
from pathlib import Path

from mlragents import config as config_module
from mlragents import griddiff, guardrails, paper, submit
from mlragents.config import ProjectConfig
from mlragents.registry import Registry, default_path
from mlragents.scheduler import slurm

MAX_OUTPUT = 20_000


class MissingProject(RuntimeError):
    """No .mlragents.toml was found at or above the given directory."""


def _project(cwd: str) -> ProjectConfig:
    config = config_module.find_project(Path(cwd))
    if config is None:
        raise MissingProject(
            f"no {config_module.CONFIG_NAME} at or above {cwd}; "
            "run the initializing-a-research-repo skill to create one"
        )
    return config


def _registry(config: ProjectConfig) -> Registry | None:
    path = default_path(config.root)
    return Registry(path) if path.is_file() else None


def runs_list(
    cwd: str,
    limit: int = 20,
    grid: str | None = None,
    status: str | None = None,
    lane: str | None = None,
) -> list[dict]:
    """List recorded runs, newest first.

    Pass lane="exploit" for runs that may be cited in the paper. Runs in the
    explore lane are insight only and must never appear in a manuscript.
    """
    registry = _registry(_project(cwd))
    if registry is None:
        return []
    runs = registry.list(limit=limit, grid=grid, status=status, lane=lane)
    return [asdict(run) for run in runs]


def lanes_list(cwd: str) -> list[dict]:
    """The experiment lanes this repository declares, and which may be cited."""
    config = _project(cwd)
    return [
        {
            "name": lane.name,
            "root": str(lane.dir(config.root)),
            "outputs_dir": str(lane.outputs_dir(config.root)),
            "citable": lane.name == "exploit",
        }
        for lane in config.lanes.values()
    ]


def runs_get(cwd: str, run_id: str) -> dict | None:
    """Full provenance for one run: git SHA, config hash, seed, job and device."""
    registry = _registry(_project(cwd))
    if registry is None:
        return None
    run = registry.get(run_id)
    return asdict(run) if run else None


def jobs_queue(cwd: str, user: str | None = None) -> list[dict]:
    """The user's current scheduler queue."""
    _project(cwd)
    return [asdict(job) for job in slurm.queue(user or getpass.getuser())]


def jobs_history(
    cwd: str, user: str | None = None, since: str = "now-7days"
) -> list[dict]:
    """Recently finished jobs and their exit codes."""
    _project(cwd)
    return [asdict(job) for job in slurm.history(user or getpass.getuser(), since=since)]


def jobs_logs(cwd: str, job_id: str, lines: int = 40) -> dict:
    """Tails of a job's stdout and stderr, plus the first error line found."""
    config = _project(cwd)
    log_dir = config.root / config.scheduler_log_dir
    stderr = ""
    stdout = ""
    for path in sorted(log_dir.glob(f"*{job_id}*")):
        text = slurm.tail_log(path, lines=lines)
        if path.suffix == ".err":
            stderr = text
        elif path.suffix == ".out":
            stdout = text
    return {
        "stdout_tail": stdout,
        "stderr_tail": stderr,
        "first_error": slurm.first_error(stderr) or slurm.first_error(stdout),
    }


def runs_provenance(cwd: str, run_id: str) -> dict:
    """Whether the paper may cite this run, and what disqualifies it if not.

    Call this before putting any number from a run into the manuscript. A run
    is citable only if it is in the exploit lane, carries a commit, was
    submitted from a clean tree, and completed.
    """
    return submit.provenance(_project(cwd), run_id)


def jobs_submit(
    cwd: str,
    script: str,
    lane: str,
    grid: str | None = None,
    cell: str | None = None,
    config_path: str | None = None,
    seed: int | None = None,
    args: list[str] | None = None,
) -> dict:
    """Submit a scheduler job and record its provenance in the same step.

    `lane` must be given explicitly: "exploit" for a run the paper may cite,
    "explore" for one it may not. Refuses rather than submit a job whose commit
    cannot be recorded, because provenance is unrecoverable afterwards.
    """
    try:
        return submit.submit(
            _project(cwd),
            script=script,
            lane=lane,
            grid=grid,
            cell=cell,
            config_path=config_path,
            seed=seed,
            args=args,
        )
    except submit.SubmissionRefused as exc:
        return {"submitted": False, "recorded": False, "reason": str(exc)}


def grid_diff(
    cwd: str, left: str, right: str, axes: list[str] | None = None
) -> dict:
    """Compare two config cells and check that only the declared axis differs.

    Pass `axes` — the key or keys the ablation is supposed to vary, such as
    ["model.kernel"]. Any other differing key is reported as a violation: two
    cells that differ in two places cannot attribute an effect to either.
    """
    config = _project(cwd)
    try:
        result = griddiff.diff(config.root / left, config.root / right)
    except (OSError, griddiff.UnsupportedConfig, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    return griddiff.verdict(result, axes)


def paper_build(cwd: str) -> dict:
    """Build the manuscript and report errors, undefined refs and citations."""
    config = _project(cwd)
    try:
        return paper.build(config).as_dict()
    except config_module.MissingCommand as exc:
        return {"ok": False, "error": str(exc)}


def paper_audit_numbers(
    cwd: str, path: str | None = None, text: str | None = None
) -> dict:
    """Find numeric literals in LaTeX that no source is attached to.

    The same check the agentStop hook applies, exposed so it can be run before
    the hook blocks. Structural numbers — font sizes, comments, macro
    arguments — are ignored. Every number it does report should resolve to an
    exploit run, a table generated from one, or a cited source.
    """
    config = _project(cwd)
    if text is None:
        if path is None:
            return {"error": "pass either path or text"}
        target = (config.root / path).resolve()
        try:
            text = target.read_text()
        except OSError as exc:
            return {"error": str(exc)}
    findings = guardrails.numeric_literals(text)
    return {
        "path": path,
        "count": len(findings),
        "findings": [{"line": line, "text": snippet} for line, snippet in findings],
    }


def collect_results(cwd: str) -> dict:
    """Run the project's declared results-collection command."""
    config = _project(cwd)
    try:
        command = config.command("collect")
    except config_module.MissingCommand as exc:
        return {"ok": False, "error": str(exc)}
    completed = subprocess.run(
        command,
        shell=True,
        cwd=str(config.root),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "command": command,
        "stdout": (completed.stdout or "")[-MAX_OUTPUT:],
        "stderr": (completed.stderr or "")[-MAX_OUTPUT:],
    }


TOOLS = [
    runs_list,
    runs_get,
    runs_provenance,
    lanes_list,
    jobs_queue,
    jobs_history,
    jobs_logs,
    jobs_submit,
    grid_diff,
    paper_build,
    paper_audit_numbers,
    collect_results,
]


def build_server():
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("mlragents")
    for tool in TOOLS:
        server.add_tool(tool)
    return server


def run() -> None:
    build_server().run(transport="stdio")
