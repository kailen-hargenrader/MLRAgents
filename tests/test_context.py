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
        config=ProjectConfig(root=Path("/repo"), name="surf-2026", scheduler_kind="slurm"),
    )
    assert "surf-2026" in text
    assert "main" in text
    assert "1 uncommitted" in text
    assert "2541417" in text
    assert "softmax_train_prenorm" in text


def test_clean_tree_says_so():
    text = session_context(
        cwd=Path("/repo"),
        user="u",
        jobs=[],
        git_state=GitState("a" * 40, "main", ()),
        runs=[],
        config=ProjectConfig(root=Path("/repo"), name="p", scheduler_kind="slurm"),
    )
    assert "clean" in text
    assert "no jobs queued" in text


def test_without_a_project_config_returns_empty():
    assert (
        session_context(
            cwd=Path("/tmp"),
            user="u",
            jobs=[],
            git_state=GitState(None, None, ()),
            runs=[],
            config=None,
        )
        == ""
    )


def test_a_project_without_a_scheduler_is_not_told_about_slurm():
    """The block exists to be true. A laptop project has no queue to report."""
    text = session_context(
        cwd=Path("/repo"),
        user="u",
        jobs=[],
        git_state=GitState("a" * 40, "main", ()),
        runs=[],
        config=ProjectConfig(root=Path("/repo"), name="laptop"),
    )
    assert "slurm" not in text
    assert "laptop" in text
