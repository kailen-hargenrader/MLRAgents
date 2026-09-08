"""Command line entry point. Hooks and scripts call into this."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import mlragents

KNOWN_COMMANDS = {"hook", "runs"}


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
    return parser


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
    parser.print_help()
    return 0


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
