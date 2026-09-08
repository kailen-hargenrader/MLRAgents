"""Hook entry points.

A hook that raises is a hook that breaks a session, so every entry point here
returns a dict and never propagates an exception. The CLI wrapper always exits
zero for the events handled so far.
"""

from __future__ import annotations

import getpass
import os
from datetime import datetime, timezone
from pathlib import Path

from mlragents import config as config_module
from mlragents import context, guardrails
from mlragents.gitinfo import describe
from mlragents.registry import Registry, Run, default_path

# Tools that create or modify a file. Shell is deliberately absent: deciding
# whether a command line writes somewhere would mean parsing shell, and a guess
# that silently allows a write is worse than no hook at all. Shell is confined
# at launch with --deny-tool instead.
WRITE_TOOLS = frozenset({"create", "edit", "write", "str_replace_editor", "apply_patch"})
PATH_KEYS = ("path", "file_path", "filePath", "target", "notebook_path")
SHELL_TOOLS = frozenset({"shell", "bash", "run_command", "execute"})


def session_start(payload: dict, gather=context.gather) -> dict:
    try:
        cwd = Path(payload.get("cwd") or ".")
        user = payload.get("user") or getpass.getuser()
        text = gather(cwd, user)
    except Exception:
        return {}
    return {"additionalContext": text} if text else {}


def _target_path(tool_args: dict) -> str | None:
    for key in PATH_KEYS:
        value = tool_args.get(key)
        if isinstance(value, str) and value:
            return value
    return None


PAPER_SUFFIXES = (".tex", ".bib")


def _within(target: Path, root: Path) -> bool:
    resolved = target.resolve()
    root = root.resolve()
    return resolved == root or root in resolved.parents


def _explore_verdict(config, target: Path) -> str | None:
    if "explore" not in config.lanes:
        return None
    lane = config.lane_for_path(target)
    if lane is not None and lane.name == "explore":
        return None
    return (
        f"{target} is outside the explore lane ({config.lane('explore').root}/). "
        "Exploratory work stays in its own tree so that nothing it produces can "
        "be cited. To promote a finding, re-run the experiment in the exploit "
        "lane rather than writing there from an explore session."
    )


def _analysis_verdict(config, target: Path) -> str | None:
    paper = config.resolve("paper")
    if _within(target, paper):
        return None
    return (
        f"{target} is outside {config.paths.paper}/. Analysis reads the exploit "
        "lane and writes only the scripts and artefacts that produce the paper's "
        "figures and tables. Changing training code here would let a "
        "disappointing result be fixed upstream of the analysis that found it; "
        "if the experiment is wrong, re-run it in the experiment role."
    )


def _paper_verdict(config, target: Path) -> str | None:
    paper = config.resolve("paper")
    if _within(target, paper) and target.suffix in PAPER_SUFFIXES:
        return None
    return (
        f"{target} is not a .tex or .bib file under {config.paths.paper}/. The "
        "paper role writes prose and references, nothing else. A quantity in the "
        "manuscript comes from a macro or table that the analysis role generated, "
        "so that no number exists which no script produced."
    )


CONFINED_ROLES = {
    "explore": _explore_verdict,
    "analysis": _analysis_verdict,
    "paper": _paper_verdict,
}


def _deny(reason: str) -> dict:
    return {"permissionDecision": "deny", "permissionDecisionReason": reason}


def _write_reason(config, role: str | None, target: str) -> str | None:
    """Why this write must be refused, or None.

    Role confinement is checked first so its message wins: it explains the
    structure, which is the more useful thing to hear when both apply.
    """
    resolved = config.root / Path(target)
    confine = CONFINED_ROLES.get(role or "")
    if confine is not None:
        reason = confine(config, resolved)
        if reason is not None:
            return reason
    return guardrails.generated_verdict(config, resolved)


def pre_tool_use(payload: dict, role: str | None = None) -> dict:
    """Refuse the actions whose damage cannot be undone later.

    Two independent gates. Role confinement is asymmetric — `experiment` is
    unconfined, because a guardrail firing during ordinary paper-grade work
    would be turned off. The submission and generated-config gates apply to
    every role, because a dirty run and a hand-edited config are unusable to
    anyone, whatever their intent.
    """
    try:
        role = role if role is not None else os.environ.get("MLRAGENTS_ROLE")
        tool_args = payload.get("toolArgs")
        if not isinstance(tool_args, dict):
            return {}
        tool = payload.get("toolName")
        config = config_module.find_project(Path(payload.get("cwd") or "."))
        if config is None:
            return {}

        if tool in SHELL_TOOLS:
            command = tool_args.get("command")
            if not isinstance(command, str):
                return {}
            reason = guardrails.submission_verdict(
                config, command, guardrails.dirty_files(config.root)
            )
            return _deny(reason) if reason else {}

        if tool in WRITE_TOOLS:
            target = _target_path(tool_args)
            if target is None:
                return {}
            reason = _write_reason(config, role, target)
            return _deny(reason) if reason else {}
        return {}
    except Exception:
        return {}


TEX_SUFFIXES = (".tex",)


def _changed_files(payload: dict) -> list[str]:
    for key in ("changedFiles", "changed_files", "files"):
        value = payload.get(key)
        if isinstance(value, list):
            return [v for v in value if isinstance(v, str)]
    return []


def _result_text(payload: dict) -> tuple[str, int | None]:
    result = payload.get("toolResult")
    if isinstance(result, str):
        return result, payload.get("exitCode")
    if isinstance(result, dict):
        text = " ".join(
            str(result.get(k, "")) for k in ("stdout", "output", "stderr", "content")
        )
        code = result.get("exitCode", result.get("exit_code"))
        return text, code if isinstance(code, int) else None
    return "", None


def post_tool_use(payload: dict, role: str | None = None) -> dict:
    """Record a submission the moment it succeeds.

    The registry is a cache and `runs sync` can rebuild it, but only for jobs
    whose artefacts survive. Recording here also captures the commit the job was
    launched from, which `sacct` does not know and no later scan could recover.
    """
    try:
        if payload.get("toolName") not in SHELL_TOOLS:
            return {}
        tool_args = payload.get("toolArgs")
        if not isinstance(tool_args, dict):
            return {}
        command = tool_args.get("command")
        if not isinstance(command, str) or not guardrails._submits(command):
            return {}
        text, exit_code = _result_text(payload)
        if exit_code not in (None, 0):
            return {}
        job_id = guardrails.submitted_job_id(text)
        if job_id is None:
            return {}
        config = config_module.find_project(Path(payload.get("cwd") or "."))
        if config is None:
            return {}
        git = describe(config.root)
        lane = "exploit" if "exploit" in config.lanes else next(iter(config.lanes), None)
        Registry(default_path(config.root)).record(
            Run(
                run_id=f"job/{job_id}",
                lane=lane,
                job_id=job_id,
                git_sha=git.sha,
                git_dirty=git.dirty,
                submitted_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                status="submitted",
            )
        )
    except Exception:
        return {}
    return {}


def agent_stop(payload: dict, role: str | None = None) -> dict:
    """Warn when a number appears in the manuscript that no script produced.

    This blocks rather than denies, because it runs after the fact: the text is
    already written, and the useful action is to make the author look at the
    line before it becomes a published quantity.
    """
    try:
        config = config_module.find_project(Path(payload.get("cwd") or "."))
        if config is None:
            return {}
        offences = []
        for name in _changed_files(payload):
            path = config.root / Path(name)
            if path.suffix not in TEX_SUFFIXES or not path.is_file():
                continue
            for line_no, line in guardrails.numeric_literals(path.read_text()):
                offences.append(f"  {name}:{line_no}: {line}")
        if not offences:
            return {}
        listed = "\n".join(offences[:10])
        return {
            "decision": "block",
            "reason": (
                "These lines carry a numeric literal that no macro or generated "
                "table produced:\n" + listed + "\n\nA typed number is correct "
                "only until the experiment is re-run, and nothing will report "
                "when it stops being correct. Replace each with a macro emitted "
                "by the analysis step, or say which quantity is missing."
            ),
        }
    except Exception:
        return {}


HANDLERS = {
    "sessionStart": session_start,
    "SessionStart": session_start,
    "preToolUse": pre_tool_use,
    "PreToolUse": pre_tool_use,
    "postToolUse": post_tool_use,
    "PostToolUse": post_tool_use,
    "agentStop": agent_stop,
    "AgentStop": agent_stop,
    "Stop": agent_stop,
}

ROLE_AWARE = {pre_tool_use, post_tool_use, agent_stop}


def dispatch(event: str, payload: dict, role: str | None = None) -> dict:
    handler = HANDLERS.get(event)
    if handler is None:
        return {}
    if handler in ROLE_AWARE:
        return handler(payload, role=role)
    return handler(payload)
