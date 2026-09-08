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
    import asyncio

    server = mcp_server.build_server()
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert names == {
        "runs_list",
        "runs_get",
        "lanes_list",
        "jobs_queue",
        "jobs_history",
        "jobs_logs",
    }


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
