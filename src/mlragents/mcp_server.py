"""The MCP surface.

Every tool takes `cwd` explicitly rather than relying on the server process's
working directory, because one server may be asked about more than one
repository during a session.
"""

from __future__ import annotations

import getpass
from dataclasses import asdict
from pathlib import Path

from mlragents import config as config_module
from mlragents.config import ProjectConfig
from mlragents.registry import Registry, default_path
from mlragents.scheduler import slurm


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


TOOLS = [runs_list, runs_get, lanes_list, jobs_queue, jobs_history, jobs_logs]


def build_server():
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("mlragents")
    for tool in TOOLS:
        server.add_tool(tool)
    return server


def run() -> None:
    build_server().run(transport="stdio")
