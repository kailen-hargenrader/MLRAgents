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
