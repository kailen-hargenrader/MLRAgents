"""jobs_submit and runs_provenance.

Provenance is only recoverable at submission time, so `submit` records before
it returns and refuses rather than submit a job it could not record.
`provenance` runs the inverse and says what disqualifies a run from citation.
"""

from __future__ import annotations

import subprocess
import types

import pytest

from mlragents import submit
from mlragents.config import load
from mlragents.registry import Registry, Run, default_path

CONFIG = """
[project]
name = "fixture"

[explore]
root = "explore"

[exploit]
root = "exploit"

[scheduler]
kind = "slurm"
"""


@pytest.fixture()
def config(tmp_path, monkeypatch):
    monkeypatch.delenv("MLRAGENTS_ALLOW_DIRTY", raising=False)
    (tmp_path / ".mlragents.toml").write_text(CONFIG)
    for d in ("explore", "exploit"):
        (tmp_path / d).mkdir()
    (tmp_path / "job.sh").write_text("#!/bin/bash\necho hi\n")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tmp_path,
        check=True,
    )
    return load(tmp_path / ".mlragents.toml")


def sbatch(job_id="777001", returncode=0, stderr=""):
    def run(*args, **kwargs):
        return types.SimpleNamespace(
            stdout=f"Submitted batch job {job_id}" if job_id else "",
            stderr=stderr,
            returncode=returncode,
        )

    return run


# --- submitting -------------------------------------------------------------


def test_a_clean_submission_records_the_commit(config):
    result = submit.submit(config, "job.sh", lane="exploit", run=sbatch())
    assert result["job_id"] == "777001"
    assert result["recorded"] is True
    assert len(result["git_sha"]) == 40

    record = Registry(default_path(config.root)).get("exploit/job/777001")
    assert record.lane == "exploit"
    assert record.git_sha == result["git_sha"]
    assert record.git_dirty is False
    assert record.status == "submitted"


def test_the_lane_is_recorded_as_given_not_guessed(config):
    submit.submit(config, "job.sh", lane="explore", run=sbatch("777002"))
    record = Registry(default_path(config.root)).get("explore/job/777002")
    assert record.lane == "explore"
    assert record.outputs_path.endswith("explore/outputs")


def test_grid_and_cell_are_recorded_because_no_later_scan_knows_them(config):
    submit.submit(
        config,
        "job.sh",
        lane="exploit",
        grid="ablation",
        cell="log_elu_prenorm",
        config_path="configs/ablation/log_elu.yaml",
        seed=7,
        run=sbatch("777003"),
    )
    record = Registry(default_path(config.root)).get("exploit/job/777003")
    assert (record.grid, record.cell, record.seed) == ("ablation", "log_elu_prenorm", 7)
    assert record.config_path == "configs/ablation/log_elu.yaml"


def test_an_explore_run_is_reported_as_not_citable(config):
    result = submit.submit(config, "job.sh", lane="explore", run=sbatch("777004"))
    assert result["citable"] is False


def test_an_undeclared_lane_names_the_declared_ones(config):
    with pytest.raises(KeyError, match="exploit, explore"):
        submit.submit(config, "job.sh", lane="scratch", run=sbatch())


def test_a_dirty_tree_refuses_and_records_nothing(config):
    (config.root / "src.py").write_text("x = 1")
    subprocess.run(["git", "add", "-A"], cwd=config.root, check=True)
    with pytest.raises(submit.SubmissionRefused, match="MLRAGENTS_ALLOW_DIRTY"):
        submit.submit(config, "job.sh", lane="exploit", run=sbatch())
    assert not default_path(config.root).is_file()


def test_the_dirty_override_lets_a_throwaway_run_through(config, monkeypatch):
    (config.root / "src.py").write_text("x = 1")
    subprocess.run(["git", "add", "-A"], cwd=config.root, check=True)
    monkeypatch.setenv("MLRAGENTS_ALLOW_DIRTY", "1")
    result = submit.submit(config, "job.sh", lane="exploit", run=sbatch("777005"))
    assert result["git_dirty"] is True
    assert result["citable"] is False


def test_a_missing_script_is_refused_by_path(config):
    with pytest.raises(submit.SubmissionRefused, match="no such submission script"):
        submit.submit(config, "absent.sh", lane="exploit", run=sbatch())


def test_a_failed_sbatch_records_nothing(config):
    with pytest.raises(submit.SubmissionRefused, match="did not report a job id"):
        submit.submit(
            config,
            "job.sh",
            lane="exploit",
            run=sbatch(job_id="", returncode=1, stderr="QOSMaxSubmitJobPerUserLimit"),
        )
    assert not default_path(config.root).is_file()


def test_sbatch_output_without_a_job_id_is_not_treated_as_success(config):
    with pytest.raises(submit.SubmissionRefused):
        submit.submit(config, "job.sh", lane="exploit", run=sbatch(job_id=""))


def test_a_project_without_slurm_is_refused_by_kind(tmp_path):
    (tmp_path / ".mlragents.toml").write_text("[project]\nname='x'\n[exploit]\nroot='exploit'\n")
    config = load(tmp_path / ".mlragents.toml")
    with pytest.raises(submit.SubmissionRefused, match="'none'"):
        submit.submit(config, "job.sh", lane="exploit", run=sbatch())


def test_extra_sbatch_args_are_passed_through(config):
    seen = {}

    def run(command, **kwargs):
        seen["command"] = command
        return types.SimpleNamespace(
            stdout="Submitted batch job 777006", stderr="", returncode=0
        )

    submit.submit(config, "job.sh", lane="exploit", args=["--gres=gpu:1"], run=run)
    assert "--gres=gpu:1" in seen["command"]
    assert seen["command"][0] == "sbatch"


# --- judging citability -----------------------------------------------------


def record(config, **kwargs):
    defaults = dict(
        run_id="exploit/job/1",
        lane="exploit",
        git_sha="a" * 40,
        git_dirty=False,
        status="COMPLETED",
    )
    defaults.update(kwargs)
    Registry(default_path(config.root)).record(Run(**defaults))
    return defaults["run_id"]


def test_a_clean_completed_exploit_run_is_citable(config):
    run_id = record(config)
    result = submit.provenance(config, run_id)
    assert result["citable"] is True
    assert result["reasons"] == []


def test_an_explore_run_is_never_citable(config):
    run_id = record(config, run_id="explore/job/2", lane="explore")
    result = submit.provenance(config, run_id)
    assert result["citable"] is False
    assert "never" in result["reasons"][0]


def test_a_run_submitted_dirty_is_not_citable(config):
    run_id = record(config, git_dirty=True)
    assert "dirty at submission" in submit.provenance(config, run_id)["reasons"][0]


def test_a_run_without_a_commit_is_not_citable(config):
    run_id = record(config, git_sha=None)
    assert "no commit" in submit.provenance(config, run_id)["reasons"][0]


def test_an_unfinished_run_is_not_citable(config):
    run_id = record(config, status="RUNNING")
    assert "has not finished" in submit.provenance(config, run_id)["reasons"][0]


def test_a_failed_run_is_not_citable(config):
    run_id = record(config, status="FAILED")
    assert "did not complete successfully" in submit.provenance(config, run_id)["reasons"][0]


def test_every_disqualifying_reason_is_reported_not_just_the_first(config):
    run_id = record(config, run_id="explore/job/3", lane="explore", git_dirty=True, status="FAILED")
    assert len(submit.provenance(config, run_id)["reasons"]) == 3


def test_an_unknown_run_says_so_rather_than_claiming_it_is_uncitable(config):
    record(config)
    result = submit.provenance(config, "exploit/job/absent")
    assert result["found"] is False
    assert "no run" in result["reasons"][0]


def test_no_registry_points_at_runs_sync(config):
    result = submit.provenance(config, "exploit/job/1")
    assert result["found"] is False
    assert "runs sync" in result["reasons"][0]
