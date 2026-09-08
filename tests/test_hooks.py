import json
from pathlib import Path
import subprocess
import sys

from mlragents import hooks
from mlragents.hooks import dispatch, session_start


def test_session_start_wraps_context():
    result = session_start({"cwd": "/repo"}, gather=lambda cwd, user: "FACTS")
    assert result == {"additionalContext": "FACTS"}


def test_session_start_with_no_context_is_empty():
    assert session_start({"cwd": "/tmp"}, gather=lambda cwd, user: "") == {}


def test_session_start_swallows_errors():
    def exploding(cwd, user):
        raise RuntimeError("boom")

    assert session_start({"cwd": "/repo"}, gather=exploding) == {}


def test_dispatch_ignores_unknown_events():
    assert dispatch("preToolUse", {}) == {}


def test_hook_cli_reads_stdin_and_exits_zero():
    proc = subprocess.run(
        [sys.executable, "-m", "mlragents.cli", "hook", "sessionStart"],
        input=json.dumps({"cwd": "/nonexistent-path-xyz"}),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert json.loads(proc.stdout or "{}") == {}


def test_hook_cli_survives_malformed_stdin():
    proc = subprocess.run(
        [sys.executable, "-m", "mlragents.cli", "hook", "sessionStart"],
        input="not json",
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0


def test_session_start_without_a_cwd_reports_nothing(tmp_path, monkeypatch):
    """The shim must not let a missing cwd resolve to the plugin's own project.

    `uv run --directory` changes the working directory to the plugin root, whose
    own .mlragents.toml would then be discovered and injected into an unrelated
    session as if it were the user's project.
    """
    monkeypatch.chdir(tmp_path)
    assert hooks.session_start({}) == {}


def test_every_registered_hook_event_has_a_handler():
    """A manifest event with no handler is a shim invoked for nothing."""
    manifest = json.loads(Path("hooks/hooks.json").read_text())
    for event in manifest["hooks"]:
        assert event in hooks.HANDLERS, f"{event} is registered but not handled"


def test_every_handled_event_that_matters_is_registered():
    manifest = json.loads(Path("hooks/hooks.json").read_text())
    registered = set(manifest["hooks"])
    assert {"sessionStart", "preToolUse", "postToolUse", "agentStop"} <= registered
