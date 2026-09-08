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
LANE_NAMES = ("explore", "exploit")
KNOWN_SECTIONS = {"project", "paths", "scheduler", "tracker", "commands", *LANE_NAMES}


class MissingCommand(KeyError):
    """A tool needed a command the project did not declare."""


@dataclass(frozen=True)
class Paths:
    paper: str = "paper"


@dataclass(frozen=True)
class Lane:
    """One of the two experiment trees.

    The names are fixed because they carry meaning the system enforces: an
    `explore` run is never evidence. Only where the trees live is configurable.
    """

    name: str
    root: str
    outputs: str = "outputs"
    run_pattern: str | list[str] | None = None

    def dir(self, project_root: Path) -> Path:
        return (Path(project_root) / self.root).resolve()

    def outputs_dir(self, project_root: Path) -> Path:
        return self.dir(project_root) / self.outputs


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    name: str = "unnamed"
    python: str = "python"
    paths: Paths = field(default_factory=Paths)
    lanes: dict[str, Lane] = field(default_factory=dict)
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

    def lane(self, name: str) -> Lane:
        try:
            return self.lanes[name]
        except KeyError as exc:
            declared = ", ".join(sorted(self.lanes)) or "none"
            raise KeyError(
                f"{CONFIG_NAME} declares no lane {name!r}; declared lanes: {declared}"
            ) from exc

    def lane_for_path(self, path: Path) -> Lane | None:
        """Which lane contains `path`, or None.

        Resolved before comparison so that a path traversing `..` is attributed
        to where it actually lands, not to where it appears to start. The
        longest matching root wins, so a lane nested inside a root-level lane is
        reported rather than its container.
        """
        target = (self.root / Path(path)).resolve()
        best: Lane | None = None
        best_depth = -1
        for lane in self.lanes.values():
            lane_dir = lane.dir(self.root)
            if target == lane_dir or lane_dir in target.parents:
                depth = len(lane_dir.parts)
                if depth > best_depth:
                    best, best_depth = lane, depth
        return best

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
        paths=Paths(paper=paths.get("paper", "paper")),
        lanes={
            name: Lane(
                name=name,
                root=data[name].get("root", name),
                outputs=data[name].get("outputs", "outputs"),
                run_pattern=data[name].get("run_pattern"),
            )
            for name in LANE_NAMES
            if name in data
        },
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
