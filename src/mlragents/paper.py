"""Building the manuscript and reading what LaTeX said about it.

A LaTeX log is thousands of lines in which the four that matter are not
distinguished from the rest. `build` runs the project's declared paper command
and extracts the failures that change what a reader sees: errors, undefined
references, and undefined citations. An undefined citation is not cosmetic — it
is a claim in the text with no source behind it.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from mlragents.config import ProjectConfig

ERROR = re.compile(r"^! (.*)$", re.MULTILINE)
UNDEFINED_REFERENCE = re.compile(r"Reference [`'\"]([^'\"]+)' on page [^ ]+ undefined")
UNDEFINED_CITATION = re.compile(r"Citation [`'\"]([^'\"]+)' on page [^ ]+ undefined")
# Some engines omit the page for citations entirely.
BARE_CITATION = re.compile(r"Citation [`'\"]([^'\"]+)' undefined")
MISSING_FILE = re.compile(r"^! LaTeX Error: File [`'\"]([^'\"]+)' not found", re.MULTILINE)
# A backstop. The patterns above name what is wrong, which is what makes a
# result actionable — but a log line saying something is undefined must never
# be reported as a clean build just because no pattern happened to match its
# phrasing. Engines vary, and a false "ok" here is the exact silent failure
# this tool exists to prevent.
UNDEFINED_LINE = re.compile(
    r"^.*(?:Warning|Error).*undefined.*$", re.MULTILINE | re.IGNORECASE
)
# LaTeX's own end-of-run tally. It restates what the per-item warnings already
# said, so it is redundant once those have been named — but if nothing was
# named, it is the only evidence there was, and the backstop must keep it.
SUMMARY_UNDEFINED = re.compile(r"There were undefined (references|citations)")
TAIL_LINES = 40


@dataclass
class BuildResult:
    ok: bool
    returncode: int
    command: str
    errors: list[str] = field(default_factory=list)
    undefined_references: list[str] = field(default_factory=list)
    undefined_citations: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    unparsed_undefined: list[str] = field(default_factory=list)
    log_tail: str = ""
    log_path: str | None = None

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "returncode": self.returncode,
            "command": self.command,
            "errors": self.errors,
            "undefined_references": self.undefined_references,
            "undefined_citations": self.undefined_citations,
            "missing_files": self.missing_files,
            "unparsed_undefined": self.unparsed_undefined,
            "log_tail": self.log_tail,
            "log_path": self.log_path,
            "summary": self.summary(),
        }

    def summary(self) -> str:
        if self.ok:
            return "the paper built with no errors, undefined references or undefined citations."
        parts = []
        if self.errors:
            parts.append(f"{len(self.errors)} LaTeX error(s)")
        if self.missing_files:
            parts.append(f"{len(self.missing_files)} missing file(s)")
        if self.undefined_references:
            parts.append(f"{len(self.undefined_references)} undefined reference(s)")
        if self.undefined_citations:
            parts.append(
                f"{len(self.undefined_citations)} undefined citation(s) — "
                "each is a claim with no source behind it"
            )
        if self.unparsed_undefined:
            parts.append(
                f"{len(self.unparsed_undefined)} log line(s) reporting something "
                "undefined in a form this tool could not name; read log_tail"
            )
        if not parts:
            parts.append(f"the build command exited {self.returncode}")
        return "; ".join(parts) + "."


def _unique(values) -> list[str]:
    seen, out = set(), []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out


def newest_log(paper_dir: Path) -> Path | None:
    """The most recently written .log under the paper directory.

    Build wrappers often silence the engine, so the log on disk carries
    warnings the command output does not.
    """
    logs = [p for p in paper_dir.rglob("*.log") if p.is_file()]
    if not logs:
        return None
    return max(logs, key=lambda p: p.stat().st_mtime)


def parse(text: str) -> dict[str, list[str]]:
    citations = _unique(UNDEFINED_CITATION.findall(text) + BARE_CITATION.findall(text))
    references = _unique(UNDEFINED_REFERENCE.findall(text))
    named = set(citations) | set(references)
    unparsed = [
        line.strip()
        for line in _unique(m.strip() for m in UNDEFINED_LINE.findall(text))
        if not any(key in line for key in named)
        and not (named and SUMMARY_UNDEFINED.search(line))
    ]
    return {
        "errors": _unique(m.strip() for m in ERROR.findall(text)),
        "undefined_references": references,
        "undefined_citations": citations,
        "missing_files": _unique(MISSING_FILE.findall(text)),
        "unparsed_undefined": unparsed,
    }


def build(config: ProjectConfig, run=subprocess.run, read_log: bool = True) -> BuildResult:
    command = config.command("paper")
    try:
        completed = run(
            command,
            shell=True,
            cwd=str(config.root),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        return BuildResult(
            ok=False, returncode=-1, command=command, errors=[f"could not run: {exc}"]
        )

    output = (completed.stdout or "") + "\n" + (completed.stderr or "")
    log_path = None
    if read_log:
        candidate = newest_log(config.resolve("paper"))
        if candidate is not None:
            log_path = str(candidate)
            try:
                output += "\n" + candidate.read_text(errors="replace")
            except OSError:
                log_path = None

    found = parse(output)
    ok = completed.returncode == 0 and not any(found.values())
    tail = "\n".join(output.strip().splitlines()[-TAIL_LINES:])
    return BuildResult(
        ok=ok,
        returncode=completed.returncode,
        command=command,
        log_tail=tail,
        log_path=log_path,
        **found,
    )
