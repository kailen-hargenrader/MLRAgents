import json

import pytest

from mlragents import hooks

CONFIG = """
[project]
name = "fixture"

[explore]
root = "explore"

[exploit]
root = "exploit"
"""


@pytest.fixture()
def project(tmp_path):
    (tmp_path / ".mlragents.toml").write_text(CONFIG)
    for lane in ("explore", "exploit", "paper"):
        (tmp_path / lane).mkdir()
    return tmp_path


def payload(project, path, tool="create", role="explore"):
    return {
        "cwd": str(project),
        "toolName": tool,
        "toolArgs": {"path": str(path)},
        "_role": role,
    }


def decide(project, path, tool="create", role="explore", monkeypatch=None):
    data = payload(project, path, tool, role)
    role_value = data.pop("_role")
    return hooks.pre_tool_use(data, role=role_value)


def test_explore_may_write_inside_its_own_lane(project):
    assert decide(project, project / "explore" / "notes.md") == {}


def test_explore_may_not_write_into_exploit(project):
    decision = decide(project, project / "exploit" / "run.py")
    assert decision["permissionDecision"] == "deny"
    assert "explore" in decision["permissionDecisionReason"]


def test_the_denial_explains_how_to_promote(project):
    reason = decide(project, project / "exploit" / "run.py")["permissionDecisionReason"]
    assert "promote" in reason.lower() or "re-run" in reason.lower()


def test_explore_may_not_write_into_the_paper(project):
    assert decide(project, project / "paper" / "main.tex")["permissionDecision"] == "deny"


def test_explore_may_not_write_outside_the_project(project, tmp_path):
    outside = tmp_path.parent / "elsewhere.txt"
    assert decide(project, outside)["permissionDecision"] == "deny"


def test_a_path_escaping_via_dot_dot_is_still_denied(project):
    sneaky = project / "explore" / ".." / "exploit" / "run.py"
    assert decide(project, sneaky)["permissionDecision"] == "deny"


def test_reads_are_never_denied(project):
    assert decide(project, project / "exploit" / "run.py", tool="view") == {}


def test_the_exploit_role_is_not_confined(project):
    assert decide(project, project / "paper" / "main.tex", role="exploit") == {}


def test_no_role_means_no_restriction(project):
    assert decide(project, project / "exploit" / "run.py", role=None) == {}


def test_a_project_without_lanes_is_not_restricted(tmp_path):
    (tmp_path / ".mlragents.toml").write_text('[project]\nname = "bare"\n')
    data = {
        "cwd": str(tmp_path),
        "toolName": "create",
        "toolArgs": {"path": str(tmp_path / "x")},
    }
    assert hooks.pre_tool_use(data, role="explore") == {}


def test_a_missing_project_is_not_restricted(tmp_path):
    data = {
        "cwd": str(tmp_path),
        "toolName": "create",
        "toolArgs": {"path": str(tmp_path / "x")},
    }
    assert hooks.pre_tool_use(data, role="explore") == {}


def test_a_malformed_payload_never_blocks(project):
    assert hooks.pre_tool_use({"toolArgs": None}, role="explore") == {}
    assert hooks.pre_tool_use({}, role="explore") == {}


def test_shell_is_not_parsed_for_redirections(project):
    """Guessing at a shell command line is the inference this design forbids."""
    data = {
        "cwd": str(project),
        "toolName": "bash",
        "toolArgs": {"command": f"echo x > {project / 'exploit' / 'y'}"},
    }
    assert hooks.pre_tool_use(data, role="explore") == {}


def test_dispatch_routes_the_event(project):
    data = payload(project, project / "exploit" / "run.py")
    data.pop("_role")
    decision = hooks.dispatch("preToolUse", data, role="explore")
    assert decision["permissionDecision"] == "deny"


def test_dispatch_still_serialises(project):
    data = payload(project, project / "exploit" / "run.py")
    data.pop("_role")
    json.dumps(hooks.dispatch("preToolUse", data, role="explore"))


def test_analysis_may_write_under_the_paper_directory(project):
    assert decide(project, project / "paper" / "figures" / "fig1.py", role="analysis") == {}


def test_analysis_may_not_write_training_code(project):
    decision = decide(project, project / "exploit" / "train.py", role="analysis")
    assert decision["permissionDecision"] == "deny"
    assert "paper/" in decision["permissionDecisionReason"]


def test_analysis_may_not_write_in_the_explore_lane(project):
    assert decide(project, project / "explore" / "x.py", role="analysis")


def test_paper_may_write_tex(project):
    assert decide(project, project / "paper" / "main.tex", role="paper") == {}


def test_paper_may_write_bib(project):
    assert decide(project, project / "paper" / "refs.bib", role="paper") == {}


def test_paper_may_not_write_a_figure_script(project):
    decision = decide(project, project / "paper" / "fig1.py", role="paper")
    assert decision["permissionDecision"] == "deny"
    assert ".tex" in decision["permissionDecisionReason"]


def test_paper_may_not_write_tex_outside_the_paper_directory(project):
    assert decide(project, project / "exploit" / "notes.tex", role="paper")


def test_experiment_is_unconfined(project):
    assert decide(project, project / "explore" / "x.py", role="experiment") == {}


def test_an_unknown_role_is_unconfined(project):
    assert decide(project, project / "explore" / "x.py", role="wizard") == {}
