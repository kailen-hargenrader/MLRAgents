"""Command line entry point. Hooks and scripts call into this."""

from __future__ import annotations

import argparse
import json
import sys

import mlragents

KNOWN_COMMANDS = {"hook"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mlragents")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    subparsers = parser.add_subparsers(dest="command")
    hook_parser = subparsers.add_parser("hook", help="run a Copilot CLI hook")
    hook_parser.add_argument("event")
    return parser


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
    parser.print_help()
    return 0


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())
