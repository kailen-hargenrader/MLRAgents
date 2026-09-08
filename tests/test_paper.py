"""paper_build: the four log lines that matter, out of thousands."""

from __future__ import annotations

import subprocess
import types

import pytest

from mlragents import paper
from mlragents.config import MissingCommand, load

CONFIG = """
[project]
name = "fixture"

[paths]
paper = "paper"

[exploit]
root = "exploit"

[commands]
paper = "latexmk -pdf main.tex"
"""


@pytest.fixture()
def config(tmp_path):
    (tmp_path / ".mlragents.toml").write_text(CONFIG)
    (tmp_path / "paper").mkdir()
    return load(tmp_path / ".mlragents.toml")


def fake_run(stdout="", stderr="", returncode=0):
    def run(*args, **kwargs):
        return types.SimpleNamespace(
            stdout=stdout, stderr=stderr, returncode=returncode
        )

    return run


def test_a_clean_build_is_ok(config):
    result = paper.build(config, run=fake_run("Output written on main.pdf"), read_log=False)
    assert result.ok is True
    assert "no errors" in result.summary()


def test_a_nonzero_exit_is_not_ok(config):
    result = paper.build(config, run=fake_run(returncode=1), read_log=False)
    assert result.ok is False
    assert "exited 1" in result.summary()


def test_latex_errors_are_extracted(config):
    log = "blah\n! Undefined control sequence.\nl.42 \\foo\n"
    result = paper.build(config, run=fake_run(log, returncode=1), read_log=False)
    assert result.errors == ["Undefined control sequence."]


def test_undefined_references_are_extracted(config):
    log = "LaTeX Warning: Reference `fig:loss' on page 3 undefined on input line 88."
    result = paper.build(config, run=fake_run(log), read_log=False)
    assert result.undefined_references == ["fig:loss"]
    assert result.ok is False


def test_undefined_citations_are_called_out_as_unsourced_claims(config):
    log = "LaTeX Warning: Citation `vaswani2017' on page 2 undefined on input line 9."
    result = paper.build(config, run=fake_run(log), read_log=False)
    assert result.undefined_citations == ["vaswani2017"]
    assert "no source behind it" in result.summary()


def test_a_citation_warning_without_a_page_is_still_caught(config):
    log = "LaTeX Warning: Citation `smith2020' undefined."
    result = paper.build(config, run=fake_run(log), read_log=False)
    assert result.undefined_citations == ["smith2020"]


def test_a_missing_input_file_is_reported(config):
    log = "! LaTeX Error: File `results/table1.tex' not found."
    result = paper.build(config, run=fake_run(log, returncode=1), read_log=False)
    assert result.missing_files == ["results/table1.tex"]


def test_repeated_warnings_are_reported_once(config):
    log = "\n".join(
        [
            "LaTeX Warning: Reference `fig:loss' on page 3 undefined on input line 8.",
            "LaTeX Warning: Reference `fig:loss' on page 4 undefined on input line 9.",
        ]
    )
    result = paper.build(config, run=fake_run(log), read_log=False)
    assert result.undefined_references == ["fig:loss"]


def test_the_log_on_disk_is_read_when_the_command_is_quiet(config):
    """Build wrappers silence the engine; the warnings survive only in the log."""
    (config.root / "paper" / "main.log").write_text(
        "LaTeX Warning: Citation `hidden2024' on page 1 undefined on input line 3."
    )
    result = paper.build(config, run=fake_run("done."), read_log=True)
    assert result.undefined_citations == ["hidden2024"]
    assert result.log_path.endswith("main.log")


def test_the_newest_log_wins(config, tmp_path):
    import os
    import time

    old = config.root / "paper" / "old.log"
    new = config.root / "paper" / "new.log"
    old.write_text("old")
    new.write_text("new")
    os.utime(old, (time.time() - 100, time.time() - 100))
    assert paper.newest_log(config.root / "paper") == new


def test_no_logs_is_not_an_error(config):
    assert paper.newest_log(config.root / "paper") is None


def test_an_undeclared_paper_command_names_the_key(tmp_path):
    (tmp_path / ".mlragents.toml").write_text("[project]\nname = 'x'\n")
    with pytest.raises(MissingCommand, match="commands.paper"):
        paper.build(load(tmp_path / ".mlragents.toml"))


def test_a_command_that_cannot_run_is_reported_not_raised(config):
    def boom(*args, **kwargs):
        raise OSError("no such binary")

    result = paper.build(config, run=boom, read_log=False)
    assert result.ok is False
    assert "could not run" in result.errors[0]


def test_as_dict_is_json_safe(config):
    import json

    result = paper.build(config, run=fake_run("ok"), read_log=False)
    json.dumps(result.as_dict())


# --- the backstop -----------------------------------------------------------
# Found live: paper_build reported ok=True while its own log tail contained
# "Citation `ghost2024 undefined". A named pattern had not matched, so nothing
# was reported — the exact silent failure this tool exists to prevent.


def test_an_undefined_line_no_pattern_names_still_fails_the_build(config):
    log = "LaTeX Warning: Citation `ghost2024 undefined."
    result = paper.build(config, run=fake_run(log), read_log=False)
    assert result.ok is False
    assert result.unparsed_undefined == [log]
    assert "could not name" in result.summary()


def test_a_named_citation_is_not_also_reported_as_unparsed(config):
    log = "LaTeX Warning: Citation `vaswani2017' on page 2 undefined on input line 9."
    result = paper.build(config, run=fake_run(log), read_log=False)
    assert result.undefined_citations == ["vaswani2017"]
    assert result.unparsed_undefined == []


def test_a_named_reference_is_not_also_reported_as_unparsed(config):
    log = "LaTeX Warning: Reference `fig:loss' on page 3 undefined on input line 8."
    result = paper.build(config, run=fake_run(log), read_log=False)
    assert result.unparsed_undefined == []


def test_an_unrelated_mention_of_undefined_does_not_fail_the_build(config):
    """The backstop keys on a warning or error, not on the word alone."""
    log = "Package foo: behaviour for undefined keys is documented in the manual."
    result = paper.build(config, run=fake_run(log), read_log=False)
    assert result.ok is True


def test_there_were_undefined_references_summary_line_is_caught(config):
    log = "LaTeX Warning: There were undefined references."
    result = paper.build(config, run=fake_run(log), read_log=False)
    assert result.ok is False
