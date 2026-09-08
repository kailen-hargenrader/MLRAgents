from pathlib import Path

import pytest

from mlragents.config import Lane, MissingCommand, ProjectConfig, find_project

SAMPLE = """
[project]
name = "surf-2026"
python = "uv run python"

[paths]
paper = "paper"

[explore]
root = "explore"

[exploit]
root = "exploit"
outputs = "runs"
run_pattern = ["{grid}/{cell}/**"]

[scheduler]
kind = "slurm"
log_dir = "slurm_logs"

[tracker]
kind = "wandb"

[commands]
train = "uv run exploit/run_experiment.py --config-name={config}"
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
    assert config.paths.paper == "paper"
    assert config.scheduler_kind == "slurm"
    assert config.tracker_kind == "wandb"


def test_both_lanes_are_loaded(tmp_path):
    config = find_project(write_project(tmp_path))
    assert set(config.lanes) == {"explore", "exploit"}
    assert config.lane("exploit").outputs == "runs"
    assert config.lane("exploit").run_pattern == ["{grid}/{cell}/**"]


def test_a_lane_outputs_directory_is_relative_to_its_root(tmp_path):
    config = find_project(write_project(tmp_path))
    explore, exploit = config.lane("explore"), config.lane("exploit")
    assert explore.outputs_dir(tmp_path) == tmp_path / "explore" / "outputs"
    assert exploit.outputs_dir(tmp_path) == tmp_path / "exploit" / "runs"


def test_a_lane_may_sit_at_the_repository_root(tmp_path):
    text = '[project]\nname = "legacy"\n[exploit]\nroot = "."\n'
    config = find_project(write_project(tmp_path, text))
    assert config.lanes["exploit"].outputs_dir(tmp_path) == tmp_path / "outputs"


def test_lane_for_path_identifies_the_containing_lane(tmp_path):
    config = find_project(write_project(tmp_path))
    inside = tmp_path / "exploit" / "runs" / "a"
    assert config.lane_for_path(inside).name == "exploit"
    assert config.lane_for_path(tmp_path / "exploit").name == "exploit"
    assert config.lane_for_path(tmp_path / "explore" / "x").name == "explore"


def test_lane_for_path_returns_none_outside_every_lane(tmp_path):
    config = find_project(write_project(tmp_path))
    assert config.lane_for_path(tmp_path / "paper" / "main.tex") is None
    assert config.lane_for_path(tmp_path) is None


def test_lane_for_path_is_not_fooled_by_dot_dot(tmp_path):
    """A path that escapes one lane into another must be reported honestly."""
    config = find_project(write_project(tmp_path))
    escaping = tmp_path / "explore" / ".." / "exploit" / "secret"
    assert config.lane_for_path(escaping).name == "exploit"


def test_lane_for_path_prefers_the_longest_matching_root(tmp_path):
    text = '[project]\nname = "n"\n[exploit]\nroot = "."\n[explore]\nroot = "explore"\n'
    config = find_project(write_project(tmp_path, text))
    assert config.lane_for_path(tmp_path / "explore" / "a").name == "explore"
    assert config.lane_for_path(tmp_path / "other").name == "exploit"


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
    assert config.lanes == {}
    assert config.paths.paper == "paper"
    assert config.scheduler_kind == "none"
    assert config.python == "python"


def test_a_declared_lane_defaults_its_outputs(tmp_path):
    config = find_project(write_project(tmp_path, '[explore]\nroot = "e"\n'))
    assert config.lane("explore") == Lane(name="explore", root="e", outputs="outputs")


def test_unknown_lane_names_the_declared_ones(tmp_path):
    config = find_project(write_project(tmp_path))
    with pytest.raises(KeyError) as excinfo:
        config.lane("nonsense")
    assert "explore" in str(excinfo.value)


def test_unknown_sections_are_preserved(tmp_path):
    config = find_project(write_project(tmp_path))
    assert config.extra["future"] == {"unknown_key": 1}


def test_lane_sections_are_not_treated_as_unknown(tmp_path):
    config = find_project(write_project(tmp_path))
    assert "explore" not in config.extra
    assert "exploit" not in config.extra


def test_missing_command_names_the_key(tmp_path):
    config = find_project(write_project(tmp_path))
    assert config.command("train").startswith("uv run")
    with pytest.raises(MissingCommand) as excinfo:
        config.command("collect")
    assert "commands.collect" in str(excinfo.value)


def test_resolve_returns_absolute_paths(tmp_path):
    config = find_project(write_project(tmp_path))
    assert config.resolve("paper") == tmp_path / "paper"


def test_project_config_is_constructible_with_defaults(tmp_path):
    config = ProjectConfig(root=tmp_path)
    assert config.name == "unnamed"
    assert config.scheduler_log_dir == "slurm_logs"
