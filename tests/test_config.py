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


def test_project_config_is_constructible_with_defaults(tmp_path):
    config = ProjectConfig(root=tmp_path)
    assert config.name == "unnamed"
    assert config.scheduler_log_dir == "slurm_logs"
