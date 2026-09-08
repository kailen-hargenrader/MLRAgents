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
        Run(
            run_id="r1",
            grid="ablation",
            status="COMPLETED",
            submitted_at="2026-01-01T00:00:00",
        )
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
        mcp_server.slurm,
        "queue",
        lambda user: [Job("1", "n", "RUNNING", "1:00", "node-1")],
    )
    assert mcp_server.jobs_queue(str(project), user="u") == [
        {
            "job_id": "1",
            "name": "n",
            "state": "RUNNING",
            "elapsed": "1:00",
            "node": "node-1",
            "exit_code": None,
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


def test_server_builds_with_every_tool_registered():
    """Derived from TOOLS, so adding a tool cannot leave it unregistered."""
    import asyncio

    server = mcp_server.build_server()
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert names == {tool.__name__ for tool in mcp_server.TOOLS}
    assert "runs_list" in names


LANE_CONFIG = """
[project]
name = "fixture"
[explore]
root = "explore"
[exploit]
root = "exploit"
[scheduler]
kind = "slurm"
log_dir = "slurm_logs"
"""


@pytest.fixture()
def lane_project(tmp_path):
    (tmp_path / ".mlragents.toml").write_text(LANE_CONFIG)
    return tmp_path


def test_runs_list_filters_by_lane(lane_project):
    registry = Registry(default_path(lane_project))
    registry.record(Run(run_id="exploit/a", lane="exploit"))
    registry.record(Run(run_id="explore/a", lane="explore"))
    rows = mcp_server.runs_list(str(lane_project), lane="exploit")
    assert [r["run_id"] for r in rows] == ["exploit/a"]


def test_runs_list_reports_the_lane(lane_project):
    Registry(default_path(lane_project)).record(Run(run_id="exploit/a", lane="exploit"))
    assert mcp_server.runs_list(str(lane_project))[0]["lane"] == "exploit"


def test_lanes_list_describes_the_declared_lanes(lane_project):
    lanes = mcp_server.lanes_list(str(lane_project))
    by_name = {lane["name"]: lane for lane in lanes}
    assert set(by_name) == {"explore", "exploit"}
    assert by_name["exploit"]["citable"] is True
    assert by_name["explore"]["citable"] is False
    assert by_name["explore"]["outputs_dir"].endswith("explore/outputs")


# --- phase 4: the paper loop ------------------------------------------------

PAPER_CONFIG = """
[project]
name = "fixture"

[paths]
paper = "paper"

[explore]
root = "explore"

[exploit]
root = "exploit"

[scheduler]
kind = "slurm"

[commands]
collect = "echo collected"
paper = "echo built"
"""


@pytest.fixture()
def paper_project(tmp_path):
    (tmp_path / ".mlragents.toml").write_text(PAPER_CONFIG)
    for d in ("explore", "exploit", "paper", "exploit/configs"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_grid_diff_reports_a_second_axis(paper_project):
    left = paper_project / "exploit/configs/a.yaml"
    right = paper_project / "exploit/configs/b.yaml"
    left.write_text("model:\n  kernel: elu\nlr: 0.001\n")
    right.write_text("model:\n  kernel: softmax\nlr: 0.01\n")
    result = mcp_server.grid_diff(
        str(paper_project),
        "exploit/configs/a.yaml",
        "exploit/configs/b.yaml",
        axes=["model.kernel"],
    )
    assert result["ok"] is False
    assert result["violations"] == ["lr"]


def test_grid_diff_reports_a_missing_file_rather_than_raising(paper_project):
    result = mcp_server.grid_diff(str(paper_project), "absent.yaml", "gone.yaml")
    assert result["ok"] is False
    assert "error" in result


def test_paper_build_runs_the_declared_command(paper_project):
    result = mcp_server.paper_build(str(paper_project))
    assert result["returncode"] == 0
    assert result["command"] == "echo built"


def test_paper_build_without_the_command_names_the_key(project):
    result = mcp_server.paper_build(str(project))
    assert result["ok"] is False
    assert "commands.paper" in result["error"]


def test_paper_audit_numbers_reads_a_file(paper_project):
    (paper_project / "paper/main.tex").write_text("We reach 92.4\\% accuracy.\n")
    result = mcp_server.paper_audit_numbers(str(paper_project), path="paper/main.tex")
    assert result["count"] == 1
    assert result["findings"][0]["line"] == 1


def test_paper_audit_numbers_accepts_literal_text(paper_project):
    result = mcp_server.paper_audit_numbers(str(paper_project), text="loss fell to 0.31")
    assert result["count"] == 1


def test_paper_audit_numbers_needs_one_of_path_or_text(paper_project):
    assert "error" in mcp_server.paper_audit_numbers(str(paper_project))


def test_paper_audit_numbers_reports_an_unreadable_file(paper_project):
    result = mcp_server.paper_audit_numbers(str(paper_project), path="absent.tex")
    assert "error" in result


def test_collect_results_runs_the_declared_command(paper_project):
    result = mcp_server.collect_results(str(paper_project))
    assert result["ok"] is True
    assert "collected" in result["stdout"]


def test_collect_results_without_the_command_names_the_key(project):
    result = mcp_server.collect_results(str(project))
    assert result["ok"] is False
    assert "commands.collect" in result["error"]


def test_jobs_submit_returns_a_reason_rather_than_raising(paper_project):
    result = mcp_server.jobs_submit(str(paper_project), "absent.sh", lane="exploit")
    assert result["submitted"] is False
    assert result["recorded"] is False
    assert "no such submission script" in result["reason"]


def test_runs_provenance_judges_a_recorded_run(paper_project):
    Registry(default_path(paper_project)).record(
        Run(run_id="exploit/job/9", lane="exploit", git_sha="a" * 40, status="COMPLETED")
    )
    assert mcp_server.runs_provenance(str(paper_project), "exploit/job/9")["citable"] is True


def test_every_tool_is_documented_and_takes_cwd():
    """The docstring is the only description an agent sees."""
    for tool in mcp_server.TOOLS:
        assert tool.__doc__, f"{tool.__name__} has no docstring"
        assert "cwd" in tool.__code__.co_varnames, f"{tool.__name__} does not take cwd"


def test_the_tool_list_has_no_duplicates():
    names = [tool.__name__ for tool in mcp_server.TOOLS]
    assert len(names) == len(set(names))
