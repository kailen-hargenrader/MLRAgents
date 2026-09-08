# MLRAgents Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship an installable Copilot CLI plugin backed by a Python package that reads a research repository's layout, records and queries run provenance, reports live Slurm state, and injects those facts into every session.

**Architecture:** One repository that is both a Copilot CLI plugin (`.claude-plugin/plugin.json`, `hooks/`, `.mcp.json`) and a Python package (`src/mlragents/`). The Python layer never infers repository semantics: it reads a committed `.mlragents.toml` for paths and commands, and otherwise touches only universal substrates — git, Slurm, SQLite. Hooks and MCP tools are thin shims over the same Python functions, so both surfaces are covered by one set of unit tests.

**Tech Stack:** Python ≥3.11 (`tomllib`, `sqlite3`, `dataclasses`), `mcp` SDK (FastMCP), `pytest`, `uv`/`uvx` for install and execution, GitHub Copilot CLI 1.0.83.

**Spec:** `docs/superpowers/specs/2026-09-08-mlragents-design.md`

## Global Constraints

- Python floor is `>=3.11`. `tomllib` is used from the standard library; do not add `tomli`. The system interpreter on the target cluster is 3.9, so every invocation goes through `uv`/`uvx`, which supplies its own interpreter.
- **The Python layer never infers repository semantics.** A tool either operates on a universal substrate (git, Slurm, SQLite, LaTeX) or shells out to a command declared in `.mlragents.toml`. When a needed command is undeclared, fail loudly with the missing key named. Never guess a path or a command.
- **Hooks must never break a session.** Every hook entry point catches all exceptions, exits 0, and emits nothing on failure. The only exception is `preToolUse` denial, which is out of scope for this plan.
- **The registry is a cache, never a source of truth.** Every field must be recoverable from `outputs/`, git and `sacct`. No workflow may depend on a row that only the registry has.
- Subprocess calls go through an injectable runner parameter so tests never invoke real `git`, `squeue` or `sacct`.
- Unknown keys in `.mlragents.toml` are preserved, not rejected.
- Commit after every task. Conventional commit prefixes: `feat:`, `test:`, `chore:`, `docs:`.

---

### Task 1: Package skeleton and CLI entry point

**Files:**
- Create: `pyproject.toml`
- Create: `src/mlragents/__init__.py`
- Create: `src/mlragents/cli.py`
- Create: `tests/test_cli.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: `mlragents.__version__: str`; `mlragents.cli.main(argv: list[str] | None = None) -> int`; console scripts `mlragents` and `mlragents-mcp`.

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:

```python
import mlragents
from mlragents.cli import main


def test_version_is_a_string():
    assert isinstance(mlragents.__version__, str)
    assert mlragents.__version__


def test_version_command_prints_version(capsys):
    exit_code = main(["--version"])
    assert exit_code == 0
    assert mlragents.__version__ in capsys.readouterr().out


def test_unknown_command_is_an_error(capsys):
    assert main(["no-such-command"]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mlragents'`

- [ ] **Step 3: Write minimal implementation**

`pyproject.toml`:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "mlragents"
version = "0.1.0"
description = "Agentic system for machine learning research"
requires-python = ">=3.11"
dependencies = ["mcp>=1.2"]

[project.scripts]
mlragents = "mlragents.cli:run"
mlragents-mcp = "mlragents.mcp_server:run"

[dependency-groups]
dev = ["pytest>=8.0"]

[tool.hatch.build.targets.wheel]
packages = ["src/mlragents"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`src/mlragents/__init__.py`:

```python
__version__ = "0.1.0"
```

`src/mlragents/cli.py`:

```python
"""Command line entry point. Hooks and scripts call into this."""

from __future__ import annotations

import argparse
import sys

import mlragents


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mlragents")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_subparsers(dest="command")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if argv and not argv[0].startswith("-"):
        known = {"hook"}
        if argv[0] not in known:
            print(f"mlragents: unknown command {argv[0]!r}", file=sys.stderr)
            return 2
    args = parser.parse_args(argv)
    if args.version:
        print(mlragents.__version__)
        return 0
    parser.print_help()
    return 0


def run() -> None:
    raise SystemExit(main())
```

`.gitignore`:

```
__pycache__/
*.egg-info/
.venv/
.pytest_cache/
.mlragents/
*.log
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/mlragents/__init__.py src/mlragents/cli.py tests/test_cli.py .gitignore
git commit -m "feat: package skeleton with mlragents CLI entry point"
```

---

### Task 2: Project adapter — reading `.mlragents.toml`

**Files:**
- Create: `src/mlragents/config.py`
- Create: `tests/test_config.py`
- Create: `docs/mlragents-toml.md`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `mlragents.config.Paths` — frozen dataclass, fields `outputs: str`, `configs: str`, `paper: str`, `scratch: str`, `protected: tuple[str, ...]`.
  - `mlragents.config.ProjectConfig` — frozen dataclass, fields `root: Path`, `name: str`, `python: str`, `paths: Paths`, `scheduler_kind: str`, `scheduler_log_dir: str`, `tracker_kind: str`, `commands: dict[str, str]`, `extra: dict`.
  - `ProjectConfig.command(key: str) -> str` — raises `MissingCommand` naming the key.
  - `ProjectConfig.resolve(path_name: str) -> Path` — absolute path for a `paths` field.
  - `mlragents.config.find_project(start: Path) -> ProjectConfig | None` — walks upward for `.mlragents.toml`.
  - `mlragents.config.MissingCommand` — exception.

- [ ] **Step 1: Write the failing test**

`tests/test_config.py`:

```python
from pathlib import Path

import pytest

from mlragents.config import MissingCommand, ProjectConfig, find_project

SAMPLE = """
[project]
name = "surf-2026"
python = "uv run python"

[paths]
outputs = "outputs"
configs = "configs"
paper = "paper"
scratch = "scratch"
protected = ["src", "experiments", "configs"]

[scheduler]
kind = "slurm"
log_dir = "slurm_logs"

[tracker]
kind = "wandb"

[commands]
train = "uv run experiments/run_experiment.py --config-name={config}"
paper = "bash scripts/build_paper.sh"

[future]
unknown_key = 1
"""


def write_project(tmp_path: Path, text: str = SAMPLE) -> Path:
    (tmp_path / ".mlragents.toml").write_text(text)
    return tmp_path


def test_loads_declared_fields(tmp_path):
    config = find_project(write_project(tmp_path))
    assert config is not None
    assert config.name == "surf-2026"
    assert config.python == "uv run python"
    assert config.paths.outputs == "outputs"
    assert config.paths.protected == ("src", "experiments", "configs")
    assert config.scheduler_kind == "slurm"
    assert config.tracker_kind == "wandb"


def test_walks_upward_from_a_subdirectory(tmp_path):
    write_project(tmp_path)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    config = find_project(nested)
    assert config is not None
    assert config.root == tmp_path


def test_returns_none_when_absent(tmp_path):
    assert find_project(tmp_path) is None


def test_defaults_fill_omitted_sections(tmp_path):
    config = find_project(write_project(tmp_path, '[project]\nname = "bare"\n'))
    assert config.paths.outputs == "outputs"
    assert config.paths.protected == ()
    assert config.scheduler_kind == "none"
    assert config.python == "python"


def test_unknown_sections_are_preserved(tmp_path):
    config = find_project(write_project(tmp_path))
    assert config.extra["future"] == {"unknown_key": 1}


def test_missing_command_names_the_key(tmp_path):
    config = find_project(write_project(tmp_path))
    assert config.command("train").startswith("uv run")
    with pytest.raises(MissingCommand) as excinfo:
        config.command("collect")
    assert "commands.collect" in str(excinfo.value)


def test_resolve_returns_absolute_paths(tmp_path):
    config = find_project(write_project(tmp_path))
    assert config.resolve("outputs") == tmp_path / "outputs"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mlragents.config'`

- [ ] **Step 3: Write minimal implementation**

`src/mlragents/config.py`:

```python
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
```

`docs/mlragents-toml.md`: document each key with the sample above, stating that unknown sections are preserved and that omitted keys take the defaults shown in `Paths` and `ProjectConfig`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mlragents/config.py tests/test_config.py docs/mlragents-toml.md
git commit -m "feat: read project layout from .mlragents.toml"
```

---

### Task 3: Git provenance

**Files:**
- Create: `src/mlragents/gitinfo.py`
- Create: `tests/test_gitinfo.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `mlragents.gitinfo.GitState` — frozen dataclass, fields `sha: str | None`, `branch: str | None`, `dirty_files: tuple[str, ...]`. Property `dirty: bool`.
  - `mlragents.gitinfo.describe(root: Path, run=subprocess.run) -> GitState`. Returns an all-empty `GitState` outside a repository; never raises.

- [ ] **Step 1: Write the failing test**

`tests/test_gitinfo.py`:

```python
import subprocess
from pathlib import Path

from mlragents.gitinfo import GitState, describe


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def make_repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "a.txt").write_text("one\n")
    git(tmp_path, "add", "a.txt")
    git(tmp_path, "commit", "-qm", "first")
    return tmp_path


def test_clean_repository(tmp_path):
    state = describe(make_repo(tmp_path))
    assert state.branch == "main"
    assert len(state.sha) == 40
    assert state.dirty_files == ()
    assert state.dirty is False


def test_dirty_repository_lists_files(tmp_path):
    root = make_repo(tmp_path)
    (root / "a.txt").write_text("two\n")
    (root / "b.txt").write_text("new\n")
    state = describe(root)
    assert state.dirty is True
    assert set(state.dirty_files) == {"a.txt", "b.txt"}


def test_outside_a_repository_is_empty_not_an_error(tmp_path):
    state = describe(tmp_path)
    assert state == GitState(sha=None, branch=None, dirty_files=())
    assert state.dirty is False


def test_git_failure_is_swallowed(tmp_path):
    def exploding_run(*args, **kwargs):
        raise OSError("git not installed")

    assert describe(tmp_path, run=exploding_run).sha is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_gitinfo.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mlragents.gitinfo'`

- [ ] **Step 3: Write minimal implementation**

`src/mlragents/gitinfo.py`:

```python
"""Git facts, gathered without ever raising into a caller's face."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitState:
    sha: str | None
    branch: str | None
    dirty_files: tuple[str, ...]

    @property
    def dirty(self) -> bool:
        return bool(self.dirty_files)


def _capture(root: Path, args: list[str], run) -> str | None:
    try:
        result = run(
            ["git", *args], cwd=str(root), capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def describe(root: Path, run=subprocess.run) -> GitState:
    sha = _capture(root, ["rev-parse", "HEAD"], run)
    branch = _capture(root, ["rev-parse", "--abbrev-ref", "HEAD"], run)
    status = _capture(root, ["status", "--porcelain"], run)
    files: tuple[str, ...] = ()
    if status:
        files = tuple(
            line[3:].strip() for line in status.splitlines() if line.strip()
        )
    return GitState(
        sha=sha.strip() if sha else None,
        branch=branch.strip() if branch else None,
        dirty_files=files,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_gitinfo.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mlragents/gitinfo.py tests/test_gitinfo.py
git commit -m "feat: collect git provenance without raising"
```

---

### Task 4: Run registry

**Files:**
- Create: `src/mlragents/registry.py`
- Create: `tests/test_registry.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `mlragents.registry.Run` — dataclass with fields `run_id: str`, `grid: str | None`, `cell: str | None`, `config_path: str | None`, `config_hash: str | None`, `git_sha: str | None`, `git_dirty: bool`, `seed: int | None`, `job_id: str | None`, `node: str | None`, `submitted_at: str | None`, `finished_at: str | None`, `status: str`, `outputs_path: str | None`, `tracker_url: str | None`. All except `run_id` default to `None`, `git_dirty` to `False`, `status` to `"unknown"`.
  - `mlragents.registry.Registry(path: Path)` with `.record(run: Run) -> None` (upsert by `run_id`), `.get(run_id: str) -> Run | None`, `.list(limit: int = 20, grid: str | None = None, status: str | None = None) -> list[Run]` (newest `submitted_at` first), `.set_status(job_id: str, status: str, finished_at: str | None = None) -> int` (returns rows updated).
  - `mlragents.registry.default_path(root: Path) -> Path` — `root / ".mlragents" / "registry.sqlite"`.

- [ ] **Step 1: Write the failing test**

`tests/test_registry.py`:

```python
from mlragents.registry import Registry, Run, default_path


def make_registry(tmp_path) -> Registry:
    return Registry(default_path(tmp_path))


def test_default_path_is_inside_the_repo(tmp_path):
    assert default_path(tmp_path) == tmp_path / ".mlragents" / "registry.sqlite"


def test_record_then_get_round_trips(tmp_path):
    registry = make_registry(tmp_path)
    run = Run(
        run_id="r1",
        grid="ablation",
        cell="softmax_train_prenorm",
        config_path="configs/ablation/softmax_train_prenorm.yaml",
        config_hash="abc123",
        git_sha="0" * 40,
        git_dirty=False,
        seed=1234,
        job_id="66132386",
        node="hpc-92-01",
        submitted_at="2026-09-08T12:00:00",
        status="RUNNING",
        outputs_path="outputs/2026-09-08/ablation/softmax_train_prenorm",
    )
    registry.record(run)
    assert registry.get("r1") == run


def test_record_is_an_upsert(tmp_path):
    registry = make_registry(tmp_path)
    registry.record(Run(run_id="r1", status="PENDING"))
    registry.record(Run(run_id="r1", status="RUNNING"))
    assert registry.get("r1").status == "RUNNING"
    assert len(registry.list()) == 1


def test_list_is_newest_first_and_filters(tmp_path):
    registry = make_registry(tmp_path)
    registry.record(Run(run_id="old", grid="a", status="COMPLETED", submitted_at="2026-01-01T00:00:00"))
    registry.record(Run(run_id="new", grid="b", status="RUNNING", submitted_at="2026-02-01T00:00:00"))
    assert [r.run_id for r in registry.list()] == ["new", "old"]
    assert [r.run_id for r in registry.list(grid="a")] == ["old"]
    assert [r.run_id for r in registry.list(status="RUNNING")] == ["new"]
    assert [r.run_id for r in registry.list(limit=1)] == ["new"]


def test_set_status_updates_by_job_id(tmp_path):
    registry = make_registry(tmp_path)
    registry.record(Run(run_id="r1", job_id="42", status="RUNNING"))
    assert registry.set_status("42", "COMPLETED", finished_at="2026-09-08T13:00:00") == 1
    stored = registry.get("r1")
    assert stored.status == "COMPLETED"
    assert stored.finished_at == "2026-09-08T13:00:00"
    assert registry.set_status("999", "COMPLETED") == 0


def test_get_missing_returns_none(tmp_path):
    assert make_registry(tmp_path).get("nope") is None


def test_opening_twice_is_safe(tmp_path):
    make_registry(tmp_path).record(Run(run_id="r1"))
    assert make_registry(tmp_path).get("r1").run_id == "r1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mlragents.registry'`

- [ ] **Step 3: Write minimal implementation**

`src/mlragents/registry.py`:

```python
"""A cache of run provenance.

Every column here is recoverable from outputs/, git and sacct. Nothing may
depend on a row that only this database has; `mlragents runs sync` rebuilds it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, fields
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    grid         TEXT,
    cell         TEXT,
    config_path  TEXT,
    config_hash  TEXT,
    git_sha      TEXT,
    git_dirty    INTEGER NOT NULL DEFAULT 0,
    seed         INTEGER,
    job_id       TEXT,
    node         TEXT,
    submitted_at TEXT,
    finished_at  TEXT,
    status       TEXT NOT NULL DEFAULT 'unknown',
    outputs_path TEXT,
    tracker_url  TEXT
);
CREATE INDEX IF NOT EXISTS runs_job_id ON runs(job_id);
CREATE INDEX IF NOT EXISTS runs_submitted_at ON runs(submitted_at DESC);
"""


@dataclass
class Run:
    run_id: str
    grid: str | None = None
    cell: str | None = None
    config_path: str | None = None
    config_hash: str | None = None
    git_sha: str | None = None
    git_dirty: bool = False
    seed: int | None = None
    job_id: str | None = None
    node: str | None = None
    submitted_at: str | None = None
    finished_at: str | None = None
    status: str = "unknown"
    outputs_path: str | None = None
    tracker_url: str | None = None


COLUMNS = [f.name for f in fields(Run)]


def default_path(root: Path) -> Path:
    return Path(root) / ".mlragents" / "registry.sqlite"


class Registry:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _to_run(row: sqlite3.Row) -> Run:
        data = dict(row)
        data["git_dirty"] = bool(data["git_dirty"])
        return Run(**data)

    def record(self, run: Run) -> None:
        data = asdict(run)
        data["git_dirty"] = int(data["git_dirty"])
        placeholders = ", ".join(f":{name}" for name in COLUMNS)
        with self._connect() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO runs ({', '.join(COLUMNS)}) "
                f"VALUES ({placeholders})",
                data,
            )

    def get(self, run_id: str) -> Run | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return self._to_run(row) if row else None

    def list(
        self,
        limit: int = 20,
        grid: str | None = None,
        status: str | None = None,
    ) -> list[Run]:
        clauses, params = [], []
        if grid is not None:
            clauses.append("grid = ?")
            params.append(grid)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM runs {where} "
                "ORDER BY submitted_at DESC, run_id DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._to_run(row) for row in rows]

    def set_status(
        self, job_id: str, status: str, finished_at: str | None = None
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE runs SET status = ?, "
                "finished_at = COALESCE(?, finished_at) WHERE job_id = ?",
                (status, finished_at, job_id),
            )
            return cursor.rowcount
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_registry.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mlragents/registry.py tests/test_registry.py
git commit -m "feat: SQLite run registry with upsert and filtered listing"
```

---

### Task 5: Slurm adapter

**Files:**
- Create: `src/mlragents/scheduler/__init__.py`
- Create: `src/mlragents/scheduler/slurm.py`
- Create: `tests/test_slurm.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `mlragents.scheduler.slurm.Job` — frozen dataclass, fields `job_id: str`, `name: str`, `state: str`, `elapsed: str`, `node: str`, `exit_code: str | None`.
  - `SQUEUE_FORMAT = "%i|%j|%T|%M|%R"`, `SACCT_FORMAT = "JobID,JobName,State,Elapsed,NodeList,ExitCode"`.
  - `parse_squeue(text: str) -> list[Job]`, `parse_sacct(text: str) -> list[Job]`.
  - `queue(user: str, run=subprocess.run) -> list[Job]`, `history(user: str, since: str = "now-7days", run=subprocess.run) -> list[Job]`.
  - `parse_sbatch_job_id(text: str) -> str | None`.
  - `tail_log(path: Path, lines: int = 40) -> str`, `first_error(text: str) -> str | None`.
  - All query functions return `[]` when the binary is absent; none raise.

- [ ] **Step 1: Write the failing test**

`tests/test_slurm.py`:

```python
from pathlib import Path

from mlragents.scheduler.slurm import (
    Job,
    first_error,
    history,
    parse_sacct,
    parse_sbatch_job_id,
    parse_squeue,
    queue,
    tail_log,
)

SQUEUE_TEXT = "2541417|pers_comp|RUNNING|28:52|hpc-92-09\n"
SACCT_TEXT = "2541417|pers_comp|RUNNING|00:28:52|hpc-92-09|0:0\n"


def fake_run(stdout: str, returncode: int = 0):
    class Result:
        pass

    def runner(*args, **kwargs):
        result = Result()
        result.stdout = stdout
        result.stderr = ""
        result.returncode = returncode
        return result

    return runner


def test_parse_squeue():
    assert parse_squeue(SQUEUE_TEXT) == [
        Job("2541417", "pers_comp", "RUNNING", "28:52", "hpc-92-09", None)
    ]


def test_parse_squeue_ignores_blank_and_short_lines():
    assert parse_squeue("\n\nbroken|line\n" + SQUEUE_TEXT) == [
        Job("2541417", "pers_comp", "RUNNING", "28:52", "hpc-92-09", None)
    ]


def test_parse_sacct_keeps_exit_code():
    assert parse_sacct(SACCT_TEXT) == [
        Job("2541417", "pers_comp", "RUNNING", "00:28:52", "hpc-92-09", "0:0")
    ]


def test_queue_uses_the_runner():
    assert queue("khargenr", run=fake_run(SQUEUE_TEXT))[0].job_id == "2541417"


def test_history_uses_the_runner():
    assert history("khargenr", run=fake_run(SACCT_TEXT))[0].state == "RUNNING"


def test_missing_binary_yields_empty_list():
    def exploding_run(*args, **kwargs):
        raise FileNotFoundError("squeue")

    assert queue("khargenr", run=exploding_run) == []
    assert history("khargenr", run=exploding_run) == []


def test_nonzero_return_yields_empty_list():
    assert queue("khargenr", run=fake_run("", returncode=1)) == []


def test_parse_sbatch_job_id():
    assert parse_sbatch_job_id("Submitted batch job 66132386\n") == "66132386"
    assert parse_sbatch_job_id("something else") is None


def test_tail_log_returns_last_lines(tmp_path: Path):
    log = tmp_path / "job.err"
    log.write_text("\n".join(str(i) for i in range(100)) + "\n")
    assert tail_log(log, lines=3).splitlines() == ["97", "98", "99"]


def test_tail_log_missing_file_is_empty(tmp_path: Path):
    assert tail_log(tmp_path / "absent.err") == ""


def test_first_error_finds_the_signal():
    text = "warming up\nTraceback (most recent call last):\n  ...\nRuntimeError: CUDA out of memory\n"
    assert first_error(text) == "RuntimeError: CUDA out of memory"
    assert first_error("all good\n") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_slurm.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mlragents.scheduler'`

- [ ] **Step 3: Write minimal implementation**

`src/mlragents/scheduler/__init__.py`:

```python
```

(An empty file. The package exists so that other schedulers can be added beside
`slurm` without changing callers.)

`src/mlragents/scheduler/slurm.py`:

```python
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


def _parse(text: str, width: int) -> list[Job]:
    jobs = []
    for line in text.splitlines():
        parts = line.strip().split("|")
        if len(parts) < width:
            continue
        jobs.append(
            Job(
                job_id=parts[0],
                name=parts[1],
                state=parts[2],
                elapsed=parts[3],
                node=parts[4],
                exit_code=parts[5] if width > 5 else None,
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
            "sacct", "-u", user, "-n", "-X", "--parsable2",
            "--starttime", since, "--format", SACCT_FORMAT,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_slurm.py -v`
Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add src/mlragents/scheduler tests/test_slurm.py
git commit -m "feat: Slurm queue, history and log triage adapters"
```

---

### Task 6: Session-start context builder and hook entry point

**Files:**
- Create: `src/mlragents/context.py`
- Create: `src/mlragents/hooks.py`
- Modify: `src/mlragents/cli.py`
- Create: `tests/test_context.py`
- Create: `tests/test_hooks.py`

**Interfaces:**
- Consumes: `mlragents.config.find_project`, `mlragents.gitinfo.describe`, `mlragents.registry.Registry`, `mlragents.registry.default_path`, `mlragents.scheduler.slurm.queue`, `mlragents.scheduler.slurm.Job`.
- Produces:
  - `mlragents.context.session_context(cwd: Path, user: str, jobs: list[Job], git_state: GitState, runs: list[Run], config: ProjectConfig | None) -> str` — pure formatting, no I/O.
  - `mlragents.context.gather(cwd: Path, user: str) -> str` — performs the I/O and calls `session_context`.
  - `mlragents.hooks.session_start(payload: dict, gather=context.gather) -> dict` — returns `{}` or `{"additionalContext": str}`.
  - `mlragents.hooks.dispatch(event: str, payload: dict) -> dict`.
  - `mlragents hook <event>` CLI subcommand: reads JSON from stdin, writes the decision JSON to stdout, always exits 0.

- [ ] **Step 1: Write the failing tests**

`tests/test_context.py`:

```python
from pathlib import Path

from mlragents.config import ProjectConfig
from mlragents.context import session_context
from mlragents.gitinfo import GitState
from mlragents.registry import Run
from mlragents.scheduler.slurm import Job


def test_reports_project_git_queue_and_runs():
    text = session_context(
        cwd=Path("/repo"),
        user="khargenr",
        jobs=[Job("2541417", "pers_comp", "RUNNING", "28:52", "hpc-92-09")],
        git_state=GitState(sha="a" * 40, branch="main", dirty_files=("a.txt",)),
        runs=[Run(run_id="r1", cell="softmax_train_prenorm", status="COMPLETED")],
        config=ProjectConfig(root=Path("/repo"), name="surf-2026"),
    )
    assert "surf-2026" in text
    assert "main" in text
    assert "1 uncommitted" in text
    assert "2541417" in text
    assert "softmax_train_prenorm" in text


def test_clean_tree_says_so():
    text = session_context(
        cwd=Path("/repo"), user="u", jobs=[], git_state=GitState("a" * 40, "main", ()),
        runs=[], config=ProjectConfig(root=Path("/repo"), name="p"),
    )
    assert "clean" in text
    assert "no jobs queued" in text


def test_without_a_project_config_returns_empty():
    assert session_context(
        cwd=Path("/tmp"), user="u", jobs=[], git_state=GitState(None, None, ()),
        runs=[], config=None,
    ) == ""
```

`tests/test_hooks.py`:

```python
import json
import subprocess
import sys

from mlragents.hooks import dispatch, session_start


def test_session_start_wraps_context():
    result = session_start({"cwd": "/repo"}, gather=lambda cwd, user: "FACTS")
    assert result == {"additionalContext": "FACTS"}


def test_session_start_with_no_context_is_empty():
    assert session_start({"cwd": "/tmp"}, gather=lambda cwd, user: "") == {}


def test_session_start_swallows_errors():
    def exploding(cwd, user):
        raise RuntimeError("boom")

    assert session_start({"cwd": "/repo"}, gather=exploding) == {}


def test_dispatch_ignores_unknown_events():
    assert dispatch("preToolUse", {}) == {}


def test_hook_cli_reads_stdin_and_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "mlragents.cli", "hook", "sessionStart"],
        input=json.dumps({"cwd": "/nonexistent-path-xyz"}),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout or "{}") == {}


def test_hook_cli_survives_malformed_stdin():
    proc = subprocess.run(
        [sys.executable, "-m", "mlragents.cli", "hook", "sessionStart"],
        input="not json",
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_context.py tests/test_hooks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mlragents.context'`

- [ ] **Step 3: Write minimal implementation**

`src/mlragents/context.py`:

```python
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
```

`src/mlragents/hooks.py`:

```python
"""Hook entry points.

A hook that raises is a hook that breaks a session, so every entry point here
returns a dict and never propagates an exception. The CLI wrapper always exits
zero for the events handled in this plan.
"""

from __future__ import annotations

import getpass
from pathlib import Path

from mlragents import context


def session_start(payload: dict, gather=context.gather) -> dict:
    try:
        cwd = Path(payload.get("cwd") or ".")
        user = payload.get("user") or getpass.getuser()
        text = gather(cwd, user)
    except Exception:
        return {}
    return {"additionalContext": text} if text else {}


HANDLERS = {
    "sessionStart": session_start,
    "SessionStart": session_start,
}


def dispatch(event: str, payload: dict) -> dict:
    handler = HANDLERS.get(event)
    if handler is None:
        return {}
    return handler(payload)
```

Modify `src/mlragents/cli.py` — replace `build_parser` and `main` with:

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mlragents")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    subparsers = parser.add_subparsers(dest="command")
    hook_parser = subparsers.add_parser("hook", help="run a Copilot CLI hook")
    hook_parser.add_argument("event")
    return parser


def _run_hook(event: str) -> int:
    import json

    from mlragents.hooks import dispatch

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        payload = {}
    try:
        decision = dispatch(event, payload if isinstance(payload, dict) else {})
    except Exception:
        decision = {}
    print(json.dumps(decision))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if argv and not argv[0].startswith("-") and argv[0] not in {"hook"}:
        print(f"mlragents: unknown command {argv[0]!r}", file=sys.stderr)
        return 2
    args = parser.parse_args(argv)
    if args.version:
        print(mlragents.__version__)
        return 0
    if args.command == "hook":
        return _run_hook(args.event)
    parser.print_help()
    return 0


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -v`
Expected: all tests pass, including the two subprocess tests in `tests/test_hooks.py`.

- [ ] **Step 5: Commit**

```bash
git add src/mlragents/context.py src/mlragents/hooks.py src/mlragents/cli.py tests/test_context.py tests/test_hooks.py
git commit -m "feat: session-start fact block and hook dispatch"
```

---

### Task 7: Plugin manifest, hook wiring, and live install verification

This is the de-risking task from spec §7 phase 0. It converts the platform
assumptions in spec §2 into executed checks. **If any check fails, stop and
record the finding in the spec before continuing** — later tasks depend on
these behaviours.

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude-plugin/marketplace.json`
- Create: `hooks/hooks.json`
- Create: `hooks/mlragents-hook`
- Create: `agents/experiment.agent.md`
- Create: `docs/verification/2026-09-08-phase0.md`
- Create: `.mlragents.toml` (this repository describes itself, so the plugin can be exercised in place)

**Interfaces:**
- Consumes: `mlragents hook sessionStart` from Task 6.
- Produces: an installable plugin. Later tasks add `mcpServers` to `plugin.json`.

- [ ] **Step 1: Write the manifests and shim**

`.claude-plugin/plugin.json`:

```json
{
  "name": "mlragents",
  "description": "Agents, skills and tools for machine learning research: run provenance, cluster state, and reproducible papers.",
  "version": "0.1.0",
  "author": { "name": "Kailen Hargenrader" },
  "repository": "https://github.com/kailen-hargenrader/MLRAgents",
  "license": "MIT",
  "keywords": ["research", "machine-learning", "slurm", "reproducibility"],
  "agents": "agents/",
  "skills": "skills/",
  "hooks": "hooks/hooks.json"
}
```

`.claude-plugin/marketplace.json`:

```json
{
  "name": "mlragents",
  "owner": { "name": "Kailen Hargenrader" },
  "plugins": [
    {
      "name": "mlragents",
      "source": "./",
      "description": "Agents, skills and tools for machine learning research.",
      "version": "0.1.0"
    }
  ]
}
```

`hooks/hooks.json`:

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [
      {
        "type": "command",
        "command": "./hooks/mlragents-hook sessionStart",
        "timeoutSec": 15
      }
    ]
  }
}
```

The relative command form is used because it is observed to work: the
`superpowers` plugin installed on this machine declares
`"command": "./hooks/run-hook.cmd session-start"` and its context reaches the
model, which means plugin hook commands resolve against the plugin root rather
than the session's working directory. Step 4 verifies this for our plugin
rather than assuming it transfers.

`hooks/mlragents-hook` (mode 755):

```bash
#!/usr/bin/env bash
# Thin shim. All logic lives in Python so it is unit-testable.
# Never fail: a broken hook must not break a session, so every path ends by
# printing valid JSON and exiting 0.
set -u
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out=""

if command -v mlragents >/dev/null 2>&1; then
    out="$(mlragents hook "$1" 2>/dev/null)" || out=""
elif command -v uv >/dev/null 2>&1; then
    out="$(uv run --directory "$root" mlragents hook "$1" 2>/dev/null)" || out=""
fi

[ -n "$out" ] || out='{}'
printf '%s\n' "$out"
exit 0
```

The `mlragents`-on-PATH branch comes first because an installed plugin
directory has no virtualenv, and `uv run` there would attempt a network
install while the user waits for their session to start. Installing the
package once with `uv tool install mlragents` makes the fast path the normal
one; the `uv run` branch covers development from a checkout.

`agents/experiment.agent.md` (a minimal real agent; its body is expanded in the
phase 2 plan):

```markdown
---
description: Runs paper-grade machine learning experiments. Use when launching, monitoring or recording experiments whose results may appear in a publication.
tools: ["read", "search", "edit", "shell"]
---

You run experiments whose results may enter a paper. Before launching a grid,
state three things and get agreement: the axis under test, the set held fixed,
and the outcome that would falsify the hypothesis.

Never launch from a dirty working tree. Never hand-edit a generated config;
change the generator and regenerate. Report what was observed in the runs
tested; do not assert a mechanism.
```

`.mlragents.toml`:

```toml
[project]
name = "mlragents"
python = "uv run python"

[paths]
outputs = "outputs"
configs = "configs"
paper = "paper"
scratch = "scratch"
protected = ["src"]

[scheduler]
kind = "slurm"
log_dir = "slurm_logs"

[commands]
test = "uv run pytest"
```

- [ ] **Step 2: Verify the shim in isolation**

Run:

```bash
chmod +x hooks/mlragents-hook
echo '{"cwd":"'"$PWD"'"}' | ./hooks/mlragents-hook sessionStart
```

Expected: a single line of JSON containing `additionalContext` with the project
name `mlragents`, the git branch, and the Slurm line. Exit code 0.

- [ ] **Step 3: Install the plugin locally and verify discovery**

Run:

```bash
copilot plugin install ./
copilot plugin list
```

Expected: `mlragents` appears in the list. Record the exact install path it
reports.

- [ ] **Step 4: Verify agent loading and hook firing in non-interactive mode**

Run:

```bash
copilot -p "Reply with exactly: AGENT OK" --agent=experiment --allow-tool='read' -s
```

Expected: the reply is `AGENT OK`, which proves plugin-contributed agents load
in `-p` mode (a v1.0.83 fix).

Then run, in a directory containing `.mlragents.toml`:

```bash
copilot -p "Repeat verbatim the MLRAgents fact block you were given at session start." -s
```

Expected: the project name, branch and Slurm line come back, which proves the
`sessionStart` hook fired and its `additionalContext` reached the model.

- [ ] **Step 5: Check the two unverified platform assumptions from spec §3.3**

Run:

```bash
MLRAGENTS_ROLE=explore copilot -p "Run: printenv MLRAGENTS_ROLE" --allow-tool='shell' -s
copilot -p "Run: sbatch --version" --deny-tool='shell(sbatch:*)' --allow-tool='shell' -s
```

Expected, and to be recorded either way in `docs/verification/2026-09-08-phase0.md`:
1. whether a command hook's environment includes `MLRAGENTS_ROLE` (determines
   whether role propagation uses the environment or a session file);
2. whether `--deny-tool='shell(sbatch:*)'` blocks the call (determines whether
   the `explore` agent's confinement is enforceable at launch).

Write the file with one section per check: the command, the observed output,
and the consequence for the spec. If either answer is "no", amend spec §3.3
in the same commit.

- [ ] **Step 6: Commit**

```bash
git add .claude-plugin hooks agents .mlragents.toml docs/verification
git commit -m "feat: installable plugin manifest with session-start hook"
```

---

### Task 8: MCP server exposing the read-only tools

**Files:**
- Create: `src/mlragents/mcp_server.py`
- Create: `.mcp.json`
- Modify: `.claude-plugin/plugin.json` (add `"mcpServers": ".mcp.json"`)
- Create: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: `config.find_project`, `Registry`, `default_path`, `slurm.queue`, `slurm.history`, `slurm.tail_log`, `slurm.first_error`.
- Produces module-level functions, each returning JSON-serializable data and each raising `MissingProject` when no `.mlragents.toml` is found:
  - `runs_list(cwd: str, limit: int = 20, grid: str | None = None, status: str | None = None) -> list[dict]`
  - `runs_get(cwd: str, run_id: str) -> dict | None`
  - `jobs_queue(cwd: str, user: str | None = None) -> list[dict]`
  - `jobs_history(cwd: str, user: str | None = None, since: str = "now-7days") -> list[dict]`
  - `jobs_logs(cwd: str, job_id: str, lines: int = 40) -> dict` with keys `stdout_tail`, `stderr_tail`, `first_error`
  - `mlragents.mcp_server.MissingProject` — exception
  - `mlragents.mcp_server.run()` — console script entry point starting FastMCP over stdio.

- [ ] **Step 1: Write the failing test**

`tests/test_mcp_server.py`:

```python
import pytest

from mlragents import mcp_server
from mlragents.registry import Registry, Run, default_path

CONFIG = """
[project]
name = "fixture"
[scheduler]
kind = "slurm"
log_dir = "slurm_logs"
"""


@pytest.fixture()
def project(tmp_path):
    (tmp_path / ".mlragents.toml").write_text(CONFIG)
    return tmp_path


def test_runs_list_returns_dicts(project):
    Registry(default_path(project)).record(
        Run(run_id="r1", grid="ablation", status="COMPLETED", submitted_at="2026-01-01T00:00:00")
    )
    rows = mcp_server.runs_list(str(project))
    assert rows[0]["run_id"] == "r1"
    assert rows[0]["grid"] == "ablation"


def test_runs_list_without_registry_is_empty(project):
    assert mcp_server.runs_list(str(project)) == []


def test_runs_get_returns_none_when_absent(project):
    assert mcp_server.runs_get(str(project), "nope") is None


def test_tools_require_a_project(tmp_path):
    with pytest.raises(mcp_server.MissingProject):
        mcp_server.runs_list(str(tmp_path))


def test_jobs_queue_serializes_jobs(project, monkeypatch):
    from mlragents.scheduler.slurm import Job

    monkeypatch.setattr(
        mcp_server.slurm, "queue",
        lambda user: [Job("1", "n", "RUNNING", "1:00", "node-1")],
    )
    assert mcp_server.jobs_queue(str(project), user="u") == [
        {
            "job_id": "1", "name": "n", "state": "RUNNING",
            "elapsed": "1:00", "node": "node-1", "exit_code": None,
        }
    ]


def test_jobs_logs_reads_the_log_dir(project):
    log_dir = project / "slurm_logs"
    log_dir.mkdir()
    (log_dir / "job_42.err").write_text("RuntimeError: CUDA out of memory\n")
    (log_dir / "job_42.out").write_text("starting\n")
    result = mcp_server.jobs_logs(str(project), "42")
    assert result["first_error"] == "RuntimeError: CUDA out of memory"
    assert "starting" in result["stdout_tail"]


def test_jobs_logs_missing_logs_are_empty(project):
    (project / "slurm_logs").mkdir()
    result = mcp_server.jobs_logs(str(project), "999")
    assert result == {"stdout_tail": "", "stderr_tail": "", "first_error": None}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_mcp_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mlragents.mcp_server'`

- [ ] **Step 3: Write minimal implementation**

`src/mlragents/mcp_server.py`:

```python
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
    cwd: str, limit: int = 20, grid: str | None = None, status: str | None = None
) -> list[dict]:
    """List recorded runs, newest first."""
    registry = _registry(_project(cwd))
    if registry is None:
        return []
    return [asdict(run) for run in registry.list(limit=limit, grid=grid, status=status)]


def runs_get(cwd: str, run_id: str) -> dict | None:
    """Full provenance for one run."""
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
    return [
        asdict(job) for job in slurm.history(user or getpass.getuser(), since=since)
    ]


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


TOOLS = [runs_list, runs_get, jobs_queue, jobs_history, jobs_logs]


def build_server():
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("mlragents")
    for tool in TOOLS:
        server.add_tool(tool)
    return server


def run() -> None:
    build_server().run()
```

`.mcp.json`:

```json
{
  "mcpServers": {
    "mlragents": {
      "type": "local",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/kailen-hargenrader/MLRAgents@v0.1.0",
        "mlragents-mcp"
      ],
      "tools": ["*"]
    }
  }
}
```

Add `"mcpServers": ".mcp.json"` to `.claude-plugin/plugin.json`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 5: Verify the server starts and the CLI sees it**

Run:

```bash
uv run mlragents-mcp --help >/dev/null 2>&1 || uv run python -c "from mlragents.mcp_server import build_server; build_server(); print('server builds')"
copilot -p "List the mlragents MCP tools available to you." -s
```

Expected: `server builds`, and the reply names `runs_list`, `jobs_queue` and
`jobs_logs`. If the `uvx --from git+...` form fails because the tag does not
exist yet, temporarily point `.mcp.json` at the local checkout with
`"command": "uv", "args": ["run", "--directory", "<abs path>", "mlragents-mcp"]`,
note it in `docs/verification/2026-09-08-phase0.md`, and restore the pinned form
when the tag is pushed.

- [ ] **Step 6: Commit**

```bash
git add src/mlragents/mcp_server.py .mcp.json .claude-plugin/plugin.json tests/test_mcp_server.py
git commit -m "feat: MCP server exposing run registry and Slurm state"
```

---

### Task 9: Registry reconciliation (`mlragents runs sync`)

The registry is a cache, so it must be rebuildable from the substrate. This task
also provides the only way to populate a registry for a repository whose runs
predate the plugin.

**Files:**
- Create: `src/mlragents/sync.py`
- Modify: `src/mlragents/cli.py`
- Create: `tests/test_sync.py`

**Interfaces:**
- Consumes: `ProjectConfig`, `Registry`, `Run`, `slurm.history`, `slurm.Job`.
- Produces:
  - `mlragents.sync.discover_outputs(config: ProjectConfig) -> list[Run]` — one `Run` per directory containing a `.hydra/config.yaml` or a `config.yaml`, with `run_id` set to the path relative to `outputs`, `outputs_path` set, and `grid`/`cell` taken from the first two path components below `outputs` when present.
  - `mlragents.sync.merge_jobs(runs: list[Run], jobs: list[Job]) -> list[Run]` — fills `status`, `node` and `finished_at` for runs whose `job_id` matches, and returns runs for unmatched jobs untouched.
  - `mlragents.sync.sync(config: ProjectConfig, jobs: list[Job]) -> int` — records the merged runs and returns the count.
  - CLI: `mlragents runs sync [--since now-7days]`.

- [ ] **Step 1: Write the failing test**

`tests/test_sync.py`:

```python
from pathlib import Path

from mlragents.config import ProjectConfig
from mlragents.registry import Registry, Run, default_path
from mlragents.scheduler.slurm import Job
from mlragents.sync import discover_outputs, merge_jobs, sync


def make_outputs(root: Path) -> ProjectConfig:
    cell = root / "outputs" / "ablation" / "softmax_train_prenorm" / "01-51-37"
    (cell / ".hydra").mkdir(parents=True)
    (cell / ".hydra" / "config.yaml").write_text("seed: 1234\n")
    return ProjectConfig(root=root, name="fixture")


def test_discover_outputs_finds_run_directories(tmp_path):
    config = make_outputs(tmp_path)
    runs = discover_outputs(config)
    assert len(runs) == 1
    assert runs[0].run_id == "ablation/softmax_train_prenorm/01-51-37"
    assert runs[0].grid == "ablation"
    assert runs[0].cell == "softmax_train_prenorm"
    assert runs[0].outputs_path.endswith("01-51-37")


def test_discover_outputs_without_an_outputs_dir_is_empty(tmp_path):
    assert discover_outputs(ProjectConfig(root=tmp_path, name="empty")) == []


def test_merge_jobs_fills_status_and_node():
    runs = [Run(run_id="r1", job_id="42")]
    merged = merge_jobs(runs, [Job("42", "n", "COMPLETED", "1:00", "hpc-92-01", "0:0")])
    assert merged[0].status == "COMPLETED"
    assert merged[0].node == "hpc-92-01"


def test_merge_jobs_leaves_unmatched_runs_alone():
    runs = [Run(run_id="r1", job_id=None, status="unknown")]
    assert merge_jobs(runs, [Job("42", "n", "COMPLETED", "1:00", "n1", "0:0")])[0].status == "unknown"


def test_sync_writes_the_registry_and_is_idempotent(tmp_path):
    config = make_outputs(tmp_path)
    assert sync(config, jobs=[]) == 1
    assert sync(config, jobs=[]) == 1
    assert len(Registry(default_path(tmp_path)).list()) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'mlragents.sync'`

- [ ] **Step 3: Write minimal implementation**

`src/mlragents/sync.py`:

```python
"""Rebuild the registry from the substrate.

A run directory is one that carries a resolved config. That is the only
structural assumption made about an outputs tree, and it holds for Hydra and for
any layout that writes its config beside its artefacts.
"""

from __future__ import annotations

from pathlib import Path

from mlragents.config import ProjectConfig
from mlragents.registry import Registry, Run, default_path
from mlragents.scheduler.slurm import Job

CONFIG_MARKERS = (".hydra/config.yaml", "config.yaml")


def _is_run_dir(path: Path) -> bool:
    return any((path / marker).is_file() for marker in CONFIG_MARKERS)


def discover_outputs(config: ProjectConfig) -> list[Run]:
    outputs_root = config.resolve("outputs")
    if not outputs_root.is_dir():
        return []
    runs = []
    for path in sorted(p for p in outputs_root.rglob("*") if p.is_dir()):
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
```

Add to `build_parser` in `src/mlragents/cli.py`, after the `hook` subparser:

```python
    runs_parser = subparsers.add_parser("runs", help="query and rebuild the run registry")
    runs_sub = runs_parser.add_subparsers(dest="runs_command")
    sync_parser = runs_sub.add_parser("sync", help="rebuild the registry from outputs/ and sacct")
    sync_parser.add_argument("--since", default="now-7days")
```

Add to `main`, before the final `parser.print_help()`, and add `"runs"` to the
known-command set in the guard:

```python
    if args.command == "runs" and args.runs_command == "sync":
        import getpass

        from mlragents.config import find_project
        from mlragents.scheduler import slurm
        from mlragents.sync import sync

        config = find_project(Path.cwd())
        if config is None:
            print("mlragents: no .mlragents.toml found", file=sys.stderr)
            return 1
        jobs = (
            slurm.history(getpass.getuser(), since=args.since)
            if config.scheduler_kind == "slurm"
            else []
        )
        print(f"recorded {sync(config, jobs)} run(s)")
        return 0
```

Add `from pathlib import Path` to the imports at the top of `cli.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/mlragents/sync.py src/mlragents/cli.py tests/test_sync.py
git commit -m "feat: rebuild the run registry from outputs and sacct"
```

---

### Task 10: Validate against a real research repository, read-only

The package is only useful if it works on the repository it was designed from.
This task runs it against `SURF_2026` **without writing to that repository**.

**Files:**
- Create: `docs/verification/2026-09-08-surf2026.md`
- Create: `examples/surf-2026.mlragents.toml`

**Interfaces:**
- Consumes: everything above.
- Produces: a written record of what worked, and `examples/surf-2026.mlragents.toml` as the reference adapter for a Hydra + Slurm + W&B project.

- [ ] **Step 1: Write the example adapter**

`examples/surf-2026.mlragents.toml`:

```toml
[project]
name = "surf-2026"
python = "uv run python"

[paths]
outputs = "outputs"
configs = "configs"
paper = "paper"
scratch = "scratch"
protected = ["src", "experiments", "configs"]

[scheduler]
kind = "slurm"
log_dir = "slurm_logs"

[tracker]
kind = "wandb"

[commands]
train = "uv run experiments/run_experiment.py --config-name={config}"
collect = "uv run scripts/collect_ablation_eval.py"
paper = "bash scripts/build_paper.sh"
```

- [ ] **Step 2: Run the read-only checks against a copy of the config**

Run, from a scratch directory that is **not** the research repository:

```bash
SURF=/resnick/groups/astuart/khargenr/SURF_2026
WORK=$(mktemp -d)
cp examples/surf-2026.mlragents.toml "$WORK/.mlragents.toml"
uv run python - "$SURF" "$WORK" <<'PY'
import sys
from pathlib import Path
from mlragents.config import find_project
from mlragents.sync import discover_outputs

surf, work = Path(sys.argv[1]), Path(sys.argv[2])
config = find_project(work)
config = type(config)(**{**config.__dict__, "root": surf})
runs = discover_outputs(config)
print(f"discovered {len(runs)} run directories")
for run in runs[:5]:
    print(" ", run.run_id, "|", run.grid, "|", run.cell)
PY
```

Expected: a non-zero count, and `grid`/`cell` values that match the directory
names under `outputs/`. Record the actual numbers.

- [ ] **Step 3: Check the live cluster path**

Run:

```bash
uv run python -c "
import getpass
from mlragents.scheduler import slurm
jobs = slurm.queue(getpass.getuser())
print(len(jobs), 'queued'); [print(' ', j) for j in jobs[:5]]
print(len(slurm.history(getpass.getuser())), 'in history')
"
```

Expected: counts consistent with `squeue -u $USER` and `sacct` run by hand.
Compare the two outputs and record any discrepancy.

- [ ] **Step 4: Write the verification record**

`docs/verification/2026-09-08-surf2026.md` records, for each check: the command,
the observed output, and whether the design assumption held. Where
`discover_outputs` missed or over-counted directories, state the rule that would
have been correct — that rule becomes the first change in the phase 2 plan.

- [ ] **Step 5: Commit**

```bash
git add examples docs/verification/2026-09-08-surf2026.md
git commit -m "docs: verify the adapter and discovery against SURF_2026"
```

---

## What this plan deliberately excludes

These are spec sections held for later plans, listed so their absence is not
mistaken for an oversight:

- **Spec §4.1 agents** beyond the single `experiment` agent used to prove
  loading, and **§4.2 skills** entirely — phase 2 plan. They depend on Task 7's
  verification results for how confinement is expressed.
- **Spec §4.3 `preToolUse`, `postToolUse` and `agentStop` hooks** — phase 3
  plan. Shipping enforcement before there is evidence about what the agents
  actually do is the risk named in spec §8.
- **Spec §4.4 `grid_diff`, `paper_build`, `paper_audit_numbers`,
  `collect_results`** — phase 4 plan.
- **`jobs_submit`** — belongs with the provenance-recording `postToolUse` hook
  in phase 3; a submit path without automatic recording would create exactly the
  unprovenanced runs the system exists to prevent.
