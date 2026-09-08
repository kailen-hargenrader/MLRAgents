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


def pre_tool_use(payload: dict, role: str | None = None) -> dict:
    """Confine a role's writes to the tree that role is answerable for.

    `experiment` is deliberately unconfined: a guardrail that fires during
    ordinary paper-grade work would be turned off, and promoting a finding
    legitimately touches the shared scaffolding. The other three each have a
    narrow deliverable, so confinement costs them nothing they should be doing.
    """
    try:
        role = role if role is not None else os.environ.get("MLRAGENTS_ROLE")
        verdict = CONFINED_ROLES.get(role or "")
        if verdict is None:
            return {}
        tool_args = payload.get("toolArgs")
        if payload.get("toolName") not in WRITE_TOOLS or not isinstance(tool_args, dict):
            return {}
        target = _target_path(tool_args)
        if target is None:
            return {}
        config = config_module.find_project(Path(payload.get("cwd") or "."))
        if config is None:
            return {}
        reason = verdict(config, config.root / Path(target))
        if reason is None:
            return {}
        return {
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
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
