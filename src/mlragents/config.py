"""The project adapter.

The one thing a research repository must provide is `.mlragents.toml`. Nothing
in this package guesses a repository's layout; it is read from here or it is an
error that names the missing key.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_NAME = ".mlragents.toml"
KNOWN_SECTIONS = {"project", "paths", "scheduler", "tracker", "commands"}


class MissingCommand(KeyError):
    """A tool needed a command the project did not declare."""


@dataclass(frozen=True)
class Paths:
    outputs: str = "outputs"
    configs: str = "configs"
    paper: str = "paper"
    scratch: str = "scratch"
    protected: tuple[str, ...] = ()
    run_pattern: str | list[str] | None = None


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    name: str = "unnamed"
    python: str = "python"
    paths: Paths = field(default_factory=Paths)
    scheduler_kind: str = "none"
    scheduler_log_dir: str = "slurm_logs"
    tracker_kind: str = "none"
    commands: dict[str, str] = field(default_factory=dict)
    extra: dict = field(default_factory=dict)

    def command(self, key: str) -> str:
        try:
            return self.commands[key]
        except KeyError as exc:
            raise MissingCommand(
                f"{CONFIG_NAME} does not declare commands.{key}; "
                f"add it to {self.root / CONFIG_NAME}"
            ) from exc

    def resolve(self, path_name: str) -> Path:
        return self.root / getattr(self.paths, path_name)


def load(path: Path) -> ProjectConfig:
    data = tomllib.loads(path.read_text())
    project = data.get("project", {})
    paths = data.get("paths", {})
    scheduler = data.get("scheduler", {})
    tracker = data.get("tracker", {})
    return ProjectConfig(
        root=path.parent,
        name=project.get("name", "unnamed"),
        python=project.get("python", "python"),
        paths=Paths(
            outputs=paths.get("outputs", "outputs"),
            configs=paths.get("configs", "configs"),
            paper=paths.get("paper", "paper"),
            scratch=paths.get("scratch", "scratch"),
            protected=tuple(paths.get("protected", ())),
            run_pattern=paths.get("run_pattern"),
        ),
        scheduler_kind=scheduler.get("kind", "none"),
        scheduler_log_dir=scheduler.get("log_dir", "slurm_logs"),
        tracker_kind=tracker.get("kind", "none"),
        commands=dict(data.get("commands", {})),
        extra={k: v for k, v in data.items() if k not in KNOWN_SECTIONS},
    )


def find_project(start: Path) -> ProjectConfig | None:
    current = Path(start).resolve()
    for candidate in [current, *current.parents]:
        config_path = candidate / CONFIG_NAME
        if config_path.is_file():
            return load(config_path)
    return None
