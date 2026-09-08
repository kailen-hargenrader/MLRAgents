"""Hook entry points.

A hook that raises is a hook that breaks a session, so every entry point here
returns a dict and never propagates an exception. The CLI wrapper always exits
zero for the events handled so far.
"""

from __future__ import annotations

import getpass
from pathlib import Path

from mlragents import context


def session_start(payload: dict, gather=context.gather) -> dict:
    try:
        cwd = Path(payload.get("cwd") or ".")
        user = payload.get("user") or getpass.getuser()
        text = gather(cwd, user)
    except Exception:
        return {}
    return {"additionalContext": text} if text else {}


HANDLERS = {
    "sessionStart": session_start,
    "SessionStart": session_start,
}


def dispatch(event: str, payload: dict) -> dict:
    handler = HANDLERS.get(event)
    if handler is None:
        return {}
    return handler(payload)
