"""Command line entry point. Hooks and scripts call into this."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import mlragents

KNOWN_COMMANDS = {"hook", "runs", "init", "run"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mlragents")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    subparsers = parser.add_subparsers(dest="command")
    hook_parser = subparsers.add_parser("hook", help="run a Copilot CLI hook")
    hook_parser.add_argument("event")
    runs_parser = subparsers.add_parser(
        "runs", help="query and rebuild the run registry"
    )
    runs_sub = runs_parser.add_subparsers(dest="runs_command")
    sync_parser = runs_sub.add_parser(
        "sync", help="rebuild the registry from outputs/ and sacct"
    )
    sync_parser.add_argument("--since", default="now-7days")
    init_parser = subparsers.add_parser(
        "init", help="scaffold the explore/exploit structure in this directory"
    )
    init_parser.add_argument("--name", default=None, help="project name")
    init_parser.add_argument("--python", default="uv run python")
    init_parser.add_argument("--scheduler", default="slurm")
    run_parser = subparsers.add_parser(
        "run", help="start a Copilot session in a role, with that role's limits"
    )
    run_parser.add_argument("role", help="explore or experiment")
    run_parser.add_argument("-p", "--prompt", default=None)
    run_parser.add_argument("--print-argv", action="store_true")
    run_parser.add_argument("extra", nargs="*", help="passed through to copilot")
    return parser


def _run_role(role: str, prompt: str | None, print_argv: bool, extra: list[str]) -> int:
    import os

    from mlragents.config import find_project
    from mlragents.launcher import UnknownRole, build_argv, role_env

    config = find_project(Path.cwd())
    if config is None:
        print(
            "mlragents: no .mlragents.toml found; run `mlragents init` first",
            file=sys.stderr,
        )
        return 1
    try:
        argv = build_argv(role, config, prompt=prompt, extra=extra)
    except UnknownRole as exc:
        print(f"mlragents: {exc}", file=sys.stderr)
        return 2
    if print_argv:
        print(" ".join(argv))
        return 0
    os.execvpe(argv[0], argv, role_env(role))
    return 0


def _run_init(name: str | None, python: str, scheduler: str) -> int:
    from mlragents.init import AlreadyInitialised, init_project

    root = Path.cwd()
    try:
        created = init_project(
            root, name=name or root.name, python=python, scheduler=scheduler
        )
    except AlreadyInitialised as exc:
        print(f"mlragents: {exc}", file=sys.stderr)
        return 1
    for path in created:
        print(f"created {path.relative_to(root)}")
    print("explore/ is insight; exploit/ is what the paper cites.")
    return 0


def _run_sync(since: str) -> int:
    import getpass

    from mlragents.config import find_project
    from mlragents.scheduler import slurm
    from mlragents.sync import sync

    config = find_project(Path.cwd())
    if config is None:
        print("mlragents: no .mlragents.toml found", file=sys.stderr)
        return 1
    jobs = (
        slurm.history(getpass.getuser(), since=since)
        if config.scheduler_kind == "slurm"
        else []
    )
    print(f"recorded {sync(config, jobs)} run(s)")
    return 0


def _run_hook(event: str) -> int:
    from mlragents.hooks import dispatch

    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except (ValueError, OSError):
        payload = {}
    try:
        decision = dispatch(event, payload if isinstance(payload, dict) else {})
    except Exception:
        decision = {}
    print(json.dumps(decision))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if argv and not argv[0].startswith("-") and argv[0] not in KNOWN_COMMANDS:
        print(f"mlragents: unknown command {argv[0]!r}", file=sys.stderr)
        return 2
    args = parser.parse_args(argv)
    if args.version:
        print(mlragents.__version__)
        return 0
    if args.command == "hook":
        return _run_hook(args.event)
    if args.command == "runs" and args.runs_command == "sync":
        return _run_sync(args.since)
    if args.command == "init":
        return _run_init(args.name, args.python, args.scheduler)
    if args.command == "run":
        return _run_role(args.role, args.prompt, args.print_argv, args.extra)
    parser.print_help()
    return 0


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
