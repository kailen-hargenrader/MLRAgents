from pathlib import Path

import pytest

from mlragents.config import Lane, ProjectConfig
from mlragents.launcher import ROLES, UnknownRole, build_argv, role_env


def project(tmp_path):
    return ProjectConfig(
        root=tmp_path,
        name="fixture",
        lanes={
            "explore": Lane(name="explore", root="explore"),
            "exploit": Lane(name="exploit", root="exploit"),
        },
    )


def test_explore_launches_its_own_agent(tmp_path):
    argv = build_argv("explore", project(tmp_path))
    assert argv[0] == "copilot"
    assert "--agent=mlragents:explore" in argv


def test_experiment_launches_the_exploit_agent(tmp_path):
    assert "--agent=mlragents:experiment" in build_argv("experiment", project(tmp_path))


def test_explore_is_denied_the_scheduler(tmp_path):
    """A queued job outlives the session that made it, so this is denied at launch."""
    argv = build_argv("explore", project(tmp_path))
    denied = " ".join(a for a in argv if a.startswith("--deny-tool"))
    assert "sbatch" in denied
    assert "srun" in denied


def test_experiment_may_use_the_scheduler(tmp_path):
    argv = build_argv("experiment", project(tmp_path))
    assert not any("sbatch" in a for a in argv)


def test_a_prompt_is_passed_through(tmp_path):
    argv = build_argv("explore", project(tmp_path), prompt="try a thing")
    assert "-p" in argv
    assert "try a thing" in argv


def test_extra_arguments_come_last(tmp_path):
    argv = build_argv("explore", project(tmp_path), extra=["--allow-all-tools"])
    assert argv[-1] == "--allow-all-tools"


def test_role_is_exported_for_hooks(tmp_path):
    assert role_env("explore")["MLRAGENTS_ROLE"] == "explore"


def test_role_env_does_not_discard_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/custom/bin")
    assert role_env("explore")["PATH"] == "/custom/bin"


def test_unknown_role_names_the_known_ones(tmp_path):
    with pytest.raises(UnknownRole) as excinfo:
        build_argv("nonsense", project(tmp_path))
    message = str(excinfo.value)
    assert "explore" in message
    assert "experiment" in message


def test_analysis_launches_its_own_agent(tmp_path):
    assert "--agent=mlragents:analysis" in build_argv("analysis", project(tmp_path))


def test_analysis_may_not_submit_jobs(tmp_path):
    """Analysis reads finished runs. Wanting a new one means wanting a new experiment."""
    argv = build_argv("analysis", project(tmp_path))
    deny = [a for a in argv if a.startswith("--deny-tool")]
    assert deny and "sbatch" in deny[0]


def test_paper_may_not_submit_jobs(tmp_path):
    argv = build_argv("paper", project(tmp_path))
    deny = [a for a in argv if a.startswith("--deny-tool")]
    assert deny and "sbatch" in deny[0]


def test_every_role_names_a_bundled_agent(tmp_path):
    """A role pointing at a missing agent fails only at launch, in the user's face."""
    agents = {p.name.removesuffix(".agent.md") for p in Path("agents").glob("*.agent.md")}
    named = {spec["agent"].split(":", 1)[1] for spec in ROLES.values()}
    assert named <= agents
