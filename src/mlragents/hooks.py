"""Hook entry points.

A hook that raises is a hook that breaks a session, so every entry point here
returns a dict and never propagates an exception. The CLI wrapper always exits
zero for the events handled so far.
"""

from __future__ import annotations

import getpass
import os
from pathlib import Path

from mlragents import config as config_module
from mlragents import context

# Tools that create or modify a file. Shell is deliberately absent: deciding
# whether a command line writes somewhere would mean parsing shell, and a guess
# that silently allows a write is worse than no hook at all. Shell is confined
# at launch with --deny-tool instead.
WRITE_TOOLS = frozenset({"create", "edit", "write", "str_replace_editor", "apply_patch"})
PATH_KEYS = ("path", "file_path", "filePath", "target", "notebook_path")


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


def pre_tool_use(payload: dict, role: str | None = None) -> dict:
    """Confine the explore role to the explore lane.

    Deliberately asymmetric: only `explore` is confined. A guardrail that fires
    during ordinary exploit work would be turned off, and promoting a finding
    legitimately touches the paper and the shared scaffolding.
    """
    try:
        role = role if role is not None else os.environ.get("MLRAGENTS_ROLE")
        if role != "explore":
            return {}
        tool_args = payload.get("toolArgs")
        if payload.get("toolName") not in WRITE_TOOLS or not isinstance(tool_args, dict):
            return {}
        target = _target_path(tool_args)
        if target is None:
            return {}
        config = config_module.find_project(Path(payload.get("cwd") or "."))
        if config is None or "explore" not in config.lanes:
            return {}
        lane = config.lane_for_path(Path(target))
        if lane is not None and lane.name == "explore":
            return {}
        return {
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"{target} is outside the explore lane "
                f"({config.lane('explore').root}/). Exploratory work stays in its "
                "own tree so that nothing it produces can be cited. To promote a "
                "finding, re-run the experiment in the exploit lane rather than "
                "writing there from an explore session."
            ),
        }
    except Exception:
        return {}


HANDLERS = {
    "sessionStart": session_start,
    "SessionStart": session_start,
    "preToolUse": pre_tool_use,
    "PreToolUse": pre_tool_use,
}


def dispatch(event: str, payload: dict, role: str | None = None) -> dict:
    handler = HANDLERS.get(event)
    if handler is None:
        return {}
    if handler is pre_tool_use:
        return handler(payload, role=role)
    return handler(payload)
