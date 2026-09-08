"""Launch a Copilot session in a role.

A role is not a personality; it is a set of restrictions that hold for the whole
session. They are applied here, at launch, because the alternative — asking the
model to observe them — is a request rather than a guarantee.
"""

from __future__ import annotations

import os

from mlragents.config import ProjectConfig

# Scheduler submission is denied to explore at launch rather than in a hook: a
# queued job outlives the session that created it, so there is no point at which
# a later check could undo it.
EXPLORE_DENY = "shell(sbatch:*), shell(srun:*), shell(salloc:*)"

ROLES = {
    "explore": {"agent": "mlragents:explore", "deny": EXPLORE_DENY},
    "experiment": {"agent": "mlragents:experiment", "deny": None},
}


class UnknownRole(KeyError):
    """Asked for a role that does not exist."""


def role_env(role: str, env: dict | None = None) -> dict:
    """The environment a role's session runs in.

    Command hooks inherit the CLI process environment (verified 2026-09-08),
    which is how a hook learns the role that the tool payload omits.
    """
    merged = dict(os.environ if env is None else env)
    merged["MLRAGENTS_ROLE"] = role
    return merged


def build_argv(
    role: str,
    config: ProjectConfig,
    prompt: str | None = None,
    extra: list[str] | None = None,
) -> list[str]:
    try:
        spec = ROLES[role]
    except KeyError as exc:
        raise UnknownRole(
            f"unknown role {role!r}; known roles: {', '.join(sorted(ROLES))}"
        ) from exc

    argv = ["copilot", f"--agent={spec['agent']}"]
    if spec["deny"]:
        argv.append(f"--deny-tool={spec['deny']}")
    if prompt:
        argv += ["-p", prompt]
    argv += list(extra or ())
    return argv
