"""Command line entry point. Hooks and scripts call into this."""

from __future__ import annotations

import argparse
import sys

import mlragents


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mlragents")
    parser.add_argument("--version", action="store_true", help="print version and exit")
    parser.add_subparsers(dest="command")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if argv and not argv[0].startswith("-"):
        known = {"hook"}
        if argv[0] not in known:
            print(f"mlragents: unknown command {argv[0]!r}", file=sys.stderr)
            return 2
    args = parser.parse_args(argv)
    if args.version:
        print(mlragents.__version__)
        return 0
    parser.print_help()
    return 0


def run() -> None:
    raise SystemExit(main())
