import dataclasses
from pathlib import Path

from mlragents.config import Lane, ProjectConfig
from mlragents.registry import Registry, Run, default_path
from mlragents.scheduler.slurm import Job
from mlragents.sync import discover_outputs, match_pattern, merge_jobs, sync


def lanes(**overrides) -> dict[str, Lane]:
    base = {
        "explore": Lane(name="explore", root="explore"),
        "exploit": Lane(name="exploit", root="exploit"),
    }
    base.update(overrides)
    return base


def make_run(root: Path, lane: str, relative: str) -> Path:
    path = root / lane / "outputs" / relative
    (path / ".hydra").mkdir(parents=True)
    (path / ".hydra" / "config.yaml").write_text("seed: 1234\n")
    return path


def make_project(root: Path, **overrides) -> ProjectConfig:
    return ProjectConfig(root=root, name="fixture", lanes=lanes(**overrides))


def test_discover_outputs_finds_run_directories(tmp_path):
    make_run(tmp_path, "exploit", "ablation/softmax_train_prenorm/01-51-37")
    runs = discover_outputs(make_project(tmp_path))
    assert len(runs) == 1
    assert runs[0].run_id == "exploit/ablation/softmax_train_prenorm/01-51-37"
    assert runs[0].lane == "exploit"
    assert runs[0].outputs_path.endswith("01-51-37")


def test_runs_are_tagged_with_the_lane_they_were_found_in(tmp_path):
    make_run(tmp_path, "explore", "hunch/01-00-00")
    make_run(tmp_path, "exploit", "grid/01-00-00")
    by_lane = {run.lane: run for run in discover_outputs(make_project(tmp_path))}
    assert set(by_lane) == {"explore", "exploit"}


def test_identical_relative_paths_in_both_lanes_do_not_collide(tmp_path):
    make_run(tmp_path, "explore", "same/01-00-00")
    make_run(tmp_path, "exploit", "same/01-00-00")
    config = make_project(tmp_path)
    runs = discover_outputs(config)
    assert len({run.run_id for run in runs}) == 2
    assert sync(config, jobs=[]) == 2
    assert len(Registry(default_path(tmp_path)).list()) == 2


def test_each_lane_applies_its_own_pattern(tmp_path):
    make_run(tmp_path, "explore", "a/b/01-00-00")
    make_run(tmp_path, "exploit", "a/b/01-00-00")
    config = make_project(
        tmp_path,
        exploit=Lane(name="exploit", root="exploit", run_pattern="{grid}/{cell}/*"),
    )
    by_lane = {run.lane: run for run in discover_outputs(config)}
    assert (by_lane["exploit"].grid, by_lane["exploit"].cell) == ("a", "b")
    assert by_lane["explore"].grid is None


def test_a_lane_with_no_outputs_directory_is_skipped(tmp_path):
    make_run(tmp_path, "exploit", "a/01-00-00")
    runs = discover_outputs(make_project(tmp_path))
    assert [run.lane for run in runs] == ["exploit"]


def test_a_project_with_no_lanes_discovers_nothing(tmp_path):
    assert discover_outputs(ProjectConfig(root=tmp_path, name="empty")) == []


def test_discover_outputs_ignores_hidden_metadata_directories(tmp_path):
    """.hydra carries a config.yaml but is metadata, not a run."""
    make_run(tmp_path, "exploit", "a/01-51-37")
    assert [run.run_id for run in discover_outputs(make_project(tmp_path))] == [
        "exploit/a/01-51-37"
    ]


def test_labels_are_empty_without_a_declared_pattern(tmp_path):
    """The package must not guess what a path component means."""
    make_run(tmp_path, "exploit", "a/b/01-00-00")
    run = discover_outputs(make_project(tmp_path))[0]
    assert run.grid is None
    assert run.cell is None


def test_pattern_skips_leading_components_with_star(tmp_path):
    make_run(tmp_path, "exploit", "2026-08-23/ablation/softmax/01-00-00")
    config = make_project(
        tmp_path,
        exploit=Lane(name="exploit", root="exploit", run_pattern="*/{grid}/{cell}/**"),
    )
    run = discover_outputs(config)[0]
    assert (run.grid, run.cell) == ("ablation", "softmax")


def test_pattern_that_does_not_match_leaves_labels_empty(tmp_path):
    make_run(tmp_path, "exploit", "a/b/01-00-00")
    config = make_project(
        tmp_path,
        exploit=Lane(name="exploit", root="exploit", run_pattern="wrong/{grid}"),
    )
    assert discover_outputs(config)[0].grid is None


def test_first_matching_pattern_wins(tmp_path):
    shallow = tmp_path / "exploit" / "outputs" / "2026-08-23" / "experiment" / "13-40-02"
    shallow.mkdir(parents=True)
    (shallow / "config.yaml").write_text("seed: 1\n")
    deep = tmp_path / "exploit" / "outputs" / "2026-08-23" / "ablation" / "softmax" / "01-00-00"
    deep.mkdir(parents=True)
    (deep / "config.yaml").write_text("seed: 1\n")
    config = make_project(
        tmp_path,
        exploit=Lane(
            name="exploit",
            root="exploit",
            run_pattern=["*/{grid}/*", "*/{grid}/{cell}/**"],
        ),
    )
    by_id = {run.run_id: run for run in discover_outputs(config)}
    shallow_run = by_id["exploit/2026-08-23/experiment/13-40-02"]
    assert (shallow_run.grid, shallow_run.cell) == ("experiment", None)
    deep_run = by_id["exploit/2026-08-23/ablation/softmax/01-00-00"]
    assert (deep_run.grid, deep_run.cell) == ("ablation", "softmax")


def test_merge_jobs_fills_status_and_node():
    runs = [Run(run_id="r1", job_id="42")]
    merged = merge_jobs(runs, [Job("42", "n", "COMPLETED", "1:00", "hpc-92-01", "0:0")])
    assert merged[0].status == "COMPLETED"
    assert merged[0].node == "hpc-92-01"


def test_merge_jobs_leaves_unmatched_runs_alone():
    runs = [Run(run_id="r1", job_id=None, status="unknown")]
    jobs = [Job("42", "n", "COMPLETED", "1:00", "n1", "0:0")]
    assert merge_jobs(runs, jobs)[0].status == "unknown"


def test_sync_writes_the_registry_and_is_idempotent(tmp_path):
    make_run(tmp_path, "exploit", "a/01-00-00")
    config = make_project(tmp_path)
    assert sync(config, jobs=[]) == 1
    assert sync(config, jobs=[]) == 1
    assert len(Registry(default_path(tmp_path)).list()) == 1


def test_match_pattern_rules():
    assert match_pattern(("a", "b"), "{grid}/{cell}") == {"grid": "a", "cell": "b"}
    assert match_pattern(("a", "b"), "{grid}") == {}
    assert match_pattern(("a", "b", "c", "d"), "{grid}/**") == {"grid": "a"}
    assert match_pattern(("a", "b"), "lit/{cell}") == {}
    assert match_pattern(("lit", "b"), "lit/{cell}") == {"cell": "b"}


def test_lane_dataclass_is_replaceable():
    lane = dataclasses.replace(Lane(name="exploit", root="exploit"), outputs="runs")
    assert lane.outputs == "runs"
