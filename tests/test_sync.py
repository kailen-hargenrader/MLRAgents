import dataclasses
from pathlib import Path

from mlragents.config import Paths, ProjectConfig
from mlragents.registry import Registry, Run, default_path
from mlragents.scheduler.slurm import Job
from mlragents.sync import discover_outputs, match_pattern, merge_jobs, sync


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
    assert runs[0].outputs_path.endswith("01-51-37")


def test_discover_outputs_without_an_outputs_dir_is_empty(tmp_path):
    assert discover_outputs(ProjectConfig(root=tmp_path, name="empty")) == []


def test_discover_outputs_ignores_hidden_metadata_directories(tmp_path):
    """.hydra carries a config.yaml but is metadata, not a run."""
    config = make_outputs(tmp_path)
    assert [run.run_id for run in discover_outputs(config)] == [
        "ablation/softmax_train_prenorm/01-51-37"
    ]


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
    config = make_outputs(tmp_path)
    assert sync(config, jobs=[]) == 1
    assert sync(config, jobs=[]) == 1
    assert len(Registry(default_path(tmp_path)).list()) == 1


def test_labels_are_empty_without_a_declared_pattern(tmp_path):
    """The package must not guess what a path component means."""
    config = make_outputs(tmp_path)
    run = discover_outputs(config)[0]
    assert run.grid is None
    assert run.cell is None


def test_pattern_names_the_grid_and_cell(tmp_path):
    config = make_outputs(tmp_path)
    config = dataclasses.replace(
        config, paths=dataclasses.replace(config.paths, run_pattern="{grid}/{cell}/*")
    )
    run = discover_outputs(config)[0]
    assert run.grid == "ablation"
    assert run.cell == "softmax_train_prenorm"


def test_pattern_skips_leading_components_with_star(tmp_path):
    cell = tmp_path / "outputs" / "2026-08-23" / "ablation" / "softmax" / "01-00-00"
    (cell / ".hydra").mkdir(parents=True)
    (cell / ".hydra" / "config.yaml").write_text("seed: 1\n")
    config = ProjectConfig(
        root=tmp_path, name="f", paths=Paths(run_pattern="*/{grid}/{cell}/**")
    )
    run = discover_outputs(config)[0]
    assert (run.grid, run.cell) == ("ablation", "softmax")


def test_pattern_that_does_not_match_leaves_labels_empty(tmp_path):
    config = make_outputs(tmp_path)
    config = dataclasses.replace(
        config, paths=dataclasses.replace(config.paths, run_pattern="wrong/{grid}")
    )
    run = discover_outputs(config)[0]
    assert run.grid is None


def test_match_pattern_rules():
    assert match_pattern(("a", "b"), "{grid}/{cell}") == {"grid": "a", "cell": "b"}
    assert match_pattern(("a", "b"), "{grid}") == {}
    assert match_pattern(("a", "b", "c", "d"), "{grid}/**") == {"grid": "a"}
    assert match_pattern(("a", "b"), "lit/{cell}") == {}
    assert match_pattern(("lit", "b"), "lit/{cell}") == {"cell": "b"}


def test_first_matching_pattern_wins(tmp_path):
    shallow = tmp_path / "outputs" / "2026-08-23" / "experiment" / "13-40-02"
    shallow.mkdir(parents=True)
    (shallow / "config.yaml").write_text("seed: 1\n")
    deep = tmp_path / "outputs" / "2026-08-23" / "ablation" / "softmax" / "01-00-00"
    deep.mkdir(parents=True)
    (deep / "config.yaml").write_text("seed: 1\n")
    config = ProjectConfig(
        root=tmp_path,
        name="f",
        paths=Paths(run_pattern=["*/{grid}/*", "*/{grid}/{cell}/**"]),
    )
    by_id = {run.run_id: run for run in discover_outputs(config)}
    shallow_run = by_id["2026-08-23/experiment/13-40-02"]
    assert (shallow_run.grid, shallow_run.cell) == ("experiment", None)
    deep_run = by_id["2026-08-23/ablation/softmax/01-00-00"]
    assert (deep_run.grid, deep_run.cell) == ("ablation", "softmax")
