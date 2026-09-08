"""Phase 3 guardrails.

These are the denials whose violation would silently corrupt a paper, so they
are enforced rather than requested. Each one is narrow, names an override, and
fails open on anything it cannot establish: a guardrail that fires when it
cannot tell is a guardrail that gets disabled.
"""

import subprocess

import pytest

from mlragents import guardrails, hooks
from mlragents.config import load

CONFIG = """
[project]
name = "fixture"

[paths]
paper = "paper"
generated = ["exploit/configs"]

[explore]
root = "explore"

[exploit]
root = "exploit"

[scheduler]
kind = "slurm"

[commands]
generate = "uv run scripts/make_configs.py"
"""


@pytest.fixture()
def project(tmp_path):
    (tmp_path / ".mlragents.toml").write_text(CONFIG)
    for d in ("explore", "exploit", "exploit/configs", "paper"):
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    return tmp_path


def config_for(project):
    return load(project / ".mlragents.toml")


# --- submitting from a dirty tree ------------------------------------------


def test_a_submission_from_a_clean_tree_is_allowed(project):
    assert guardrails.submission_verdict(config_for(project), "sbatch job.sh", dirty=()) is None


def test_a_submission_from_a_dirty_tree_is_refused(project):
    reason = guardrails.submission_verdict(
        config_for(project), "sbatch job.sh", dirty=("src/train.py",)
    )
    assert reason is not None
    assert "src/train.py" in reason


def test_the_refusal_names_an_override(project):
    reason = guardrails.submission_verdict(
        config_for(project), "sbatch job.sh", dirty=("src/train.py",)
    )
    assert "MLRAGENTS_ALLOW_DIRTY" in reason


def test_a_command_that_is_not_a_submission_is_ignored(project):
    assert guardrails.submission_verdict(config_for(project), "ls -la", dirty=("a.py",)) is None


@pytest.mark.parametrize("command", ["srun python x.py", "salloc -N1", "  sbatch  job.sh"])
def test_every_submission_form_is_covered(project, command):
    assert guardrails.submission_verdict(config_for(project), command, dirty=("a.py",))


def test_a_mention_of_sbatch_inside_a_word_is_not_a_submission(project):
    assert guardrails.submission_verdict(config_for(project), "echo resbatching", dirty=("a.py",)) is None


def test_a_submission_later_in_a_pipeline_is_still_a_submission(project):
    assert guardrails.submission_verdict(config_for(project), "cd x && sbatch job.sh", dirty=("a.py",))


def test_a_repository_without_a_scheduler_does_not_gate_submissions(tmp_path):
    (tmp_path / ".mlragents.toml").write_text("[project]\nname='x'\n")
    config = load(tmp_path / ".mlragents.toml")
    assert guardrails.submission_verdict(config, "sbatch job.sh", dirty=("a.py",)) is None


# --- hand-editing generated configs ----------------------------------------


def test_writing_a_generated_config_is_refused(project):
    reason = guardrails.generated_verdict(config_for(project), project / "exploit/configs/a.yaml")
    assert reason is not None
    assert "uv run scripts/make_configs.py" in reason


def test_writing_outside_the_generated_tree_is_allowed(project):
    assert guardrails.generated_verdict(config_for(project), project / "exploit/train.py") is None


def test_a_repository_declaring_no_generated_tree_is_not_gated(tmp_path):
    (tmp_path / ".mlragents.toml").write_text("[project]\nname='x'\n")
    config = load(tmp_path / ".mlragents.toml")
    assert guardrails.generated_verdict(config, tmp_path / "configs/a.yaml") is None


def test_the_generator_itself_may_be_edited(project):
    assert guardrails.generated_verdict(config_for(project), project / "scripts/make_configs.py") is None


# --- the hook surface -------------------------------------------------------


def shell_payload(project, command):
    return {"cwd": str(project), "toolName": "shell", "toolArgs": {"command": command}}


def test_the_hook_denies_a_dirty_submission(project, monkeypatch):
    monkeypatch.setattr(
        guardrails, "dirty_files", lambda root: ("src/train.py",)
    )
    decision = hooks.pre_tool_use(shell_payload(project, "sbatch job.sh"), role="experiment")
    assert decision["permissionDecision"] == "deny"


def test_the_hook_allows_a_clean_submission(project, monkeypatch):
    monkeypatch.setattr(guardrails, "dirty_files", lambda root: ())
    assert hooks.pre_tool_use(shell_payload(project, "sbatch job.sh"), role="experiment") == {}


def test_the_override_environment_variable_permits_a_dirty_submission(project, monkeypatch):
    monkeypatch.setattr(guardrails, "dirty_files", lambda root: ("src/train.py",))
    monkeypatch.setenv("MLRAGENTS_ALLOW_DIRTY", "1")
    assert hooks.pre_tool_use(shell_payload(project, "sbatch job.sh"), role="experiment") == {}


def test_the_submission_gate_applies_to_every_role(project, monkeypatch):
    """Provenance is not a role's preference; a dirty run is unusable to anyone."""
    monkeypatch.setattr(guardrails, "dirty_files", lambda root: ("src/train.py",))
    decision = hooks.pre_tool_use(shell_payload(project, "sbatch job.sh"), role=None)
    assert decision["permissionDecision"] == "deny"


def test_the_hook_denies_editing_a_generated_config(project):
    payload = {
        "cwd": str(project),
        "toolName": "create",
        "toolArgs": {"path": str(project / "exploit/configs/a.yaml")},
    }
    assert hooks.pre_tool_use(payload, role="experiment")["permissionDecision"] == "deny"


# --- provenance on submission ----------------------------------------------


def test_a_job_id_is_read_from_the_submission_output():
    assert guardrails.submitted_job_id("Submitted batch job 1249067") == "1249067"


def test_output_without_a_job_id_yields_none():
    assert guardrails.submitted_job_id("sbatch: error: invalid partition") is None


def test_a_successful_submission_is_recorded(project, monkeypatch):
    from mlragents.registry import Registry, default_path

    monkeypatch.setattr(guardrails, "dirty_files", lambda root: ())
    payload = {
        "cwd": str(project),
        "toolName": "shell",
        "toolArgs": {"command": "sbatch job.sh"},
        "toolResult": {"stdout": "Submitted batch job 4242\n", "exitCode": 0},
    }
    hooks.post_tool_use(payload, role="experiment")
    runs = Registry(default_path(project)).list()
    assert [r.job_id for r in runs] == ["4242"]
    assert runs[0].lane == "exploit"


def test_a_failed_submission_is_not_recorded(project):
    from mlragents.registry import Registry, default_path

    payload = {
        "cwd": str(project),
        "toolName": "shell",
        "toolArgs": {"command": "sbatch job.sh"},
        "toolResult": {"stdout": "sbatch: error: bad partition", "exitCode": 1},
    }
    hooks.post_tool_use(payload, role="experiment")
    assert Registry(default_path(project)).list() == []


def test_a_non_submission_is_not_recorded(project):
    from mlragents.registry import Registry, default_path

    payload = {
        "cwd": str(project),
        "toolName": "shell",
        "toolArgs": {"command": "ls"},
        "toolResult": {"stdout": "Submitted batch job 9", "exitCode": 0},
    }
    hooks.post_tool_use(payload, role="experiment")
    assert Registry(default_path(project)).list() == []


def test_the_recorded_run_carries_the_commit_it_ran(project, monkeypatch):
    from mlragents.gitinfo import GitState
    from mlragents.registry import Registry, default_path

    monkeypatch.setattr(
        guardrails, "dirty_files", lambda root: ()
    )
    monkeypatch.setattr(
        "mlragents.hooks.describe",
        lambda root: GitState(sha="abc123", branch="main", dirty_files=()),
    )
    payload = {
        "cwd": str(project),
        "toolName": "shell",
        "toolArgs": {"command": "sbatch job.sh"},
        "toolResult": {"stdout": "Submitted batch job 77", "exitCode": 0},
    }
    hooks.post_tool_use(payload, role="experiment")
    assert Registry(default_path(project)).list()[0].git_sha == "abc123"


# --- the numeric audit ------------------------------------------------------


def test_a_measurement_is_flagged():
    assert guardrails.numeric_literals("The loss reached 0.0271 after training.")


def test_a_macro_is_not_flagged():
    assert guardrails.numeric_literals("The loss reached \\finalloss after training.") == []


def test_structural_numbers_are_not_flagged():
    tex = "\\documentclass[11pt]{article}\n\\usepackage[margin=1in]{geometry}\n"
    assert guardrails.numeric_literals(tex) == []


def test_a_commented_number_is_not_flagged():
    assert guardrails.numeric_literals("% we measured 0.31 here") == []


def test_an_escaped_percent_does_not_hide_the_rest_of_the_line():
    assert guardrails.numeric_literals("A 40\\% drop, and 0.52 after.")


def test_the_reported_line_number_is_one_based():
    assert guardrails.numeric_literals("clean\nthe value 12 appears")[0][0] == 2


def test_the_audit_blocks_when_a_tex_file_gained_a_number(project):
    tex = project / "paper" / "main.tex"
    tex.write_text("The final loss was 0.0271.\n")
    decision = hooks.agent_stop({"cwd": str(project), "changedFiles": [str(tex)]})
    assert decision.get("decision") == "block"
    assert "0.0271" in decision["reason"]


def test_the_audit_is_silent_when_no_tex_changed(project):
    assert hooks.agent_stop({"cwd": str(project), "changedFiles": ["src/train.py"]}) == {}


def test_the_audit_is_silent_on_a_clean_tex_file(project):
    tex = project / "paper" / "main.tex"
    tex.write_text("The final loss was \\finalloss.\n")
    assert hooks.agent_stop({"cwd": str(project), "changedFiles": [str(tex)]}) == {}
