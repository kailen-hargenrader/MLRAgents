"""The plugin's markdown assets are load-bearing, so they are checked here.

A skill with a malformed header does not error; it is simply never offered, and
the session proceeds slightly worse with nothing to indicate why. These tests
turn that silence into a failure.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AGENTS = sorted((ROOT / "agents").glob("*.agent.md"))
SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))

EXPECTED_AGENTS = {"explore", "experiment", "analysis", "paper"}
EXPECTED_SKILLS = {
    "designing-an-ablation",
    "promoting-an-experiment",
    "reading-run-results",
    "debugging-a-failed-job",
    "writing-results-prose",
    "keeping-the-paper-reproducible",
    "initializing-a-research-repo",
}


def frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text().splitlines()
    assert lines and lines[0] == "---", f"{path} does not open with frontmatter"
    end = lines.index("---", 1)
    fields = {}
    key = None
    for line in lines[1:end]:
        if line and not line[0].isspace() and ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
        elif key:
            fields[key] += " " + line.strip()
    return fields


def test_the_four_agents_exist():
    assert {p.name.removesuffix(".agent.md") for p in AGENTS} == EXPECTED_AGENTS


def test_the_seven_skills_exist():
    assert {p.parent.name for p in SKILLS} == EXPECTED_SKILLS


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.name)
def test_every_agent_describes_when_to_use_it(path):
    assert frontmatter(path).get("description")


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.name)
def test_every_agent_names_its_mcp_tools_individually(path):
    """Naming the server alone silently loses the tools (verified 2026-09-08)."""
    tools = frontmatter(path).get("tools", "")
    assert "mlragents-" in tools, f"{path.name} lists no mlragents MCP tool"
    assert '"mlragents"' not in tools, f"{path.name} names the server, not its tools"


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_every_skill_name_matches_its_directory(path):
    assert frontmatter(path).get("name") == path.parent.name


@pytest.mark.parametrize("path", SKILLS, ids=lambda p: p.parent.name)
def test_every_skill_says_when_to_use_it(path):
    description = frontmatter(path).get("description", "").lower()
    assert description.startswith("use "), (
        f"{path.parent.name}: a description that does not say when to use the "
        "skill gives the model nothing to match against"
    )


def agent_tools(name: str) -> str:
    return frontmatter(ROOT / "agents" / f"{name}.agent.md").get("tools", "")


@pytest.mark.parametrize("path", AGENTS, ids=lambda p: p.name)
def test_every_listed_mcp_tool_actually_exists(path):
    """A misspelled tool name is not an error; the tool is just absent."""
    from mlragents import mcp_server

    available = {f"mlragents-{tool.__name__}" for tool in mcp_server.TOOLS}
    listed = set(re.findall(r"mlragents-\w+", agent_tools(path.name.removesuffix(".agent.md"))))
    assert listed <= available, f"{path.name} lists unknown tools: {listed - available}"


@pytest.mark.parametrize("role", sorted(EXPECTED_AGENTS - {"experiment"}))
def test_only_experiment_may_submit_jobs(role):
    """jobs_submit would otherwise bypass the launcher's scheduler denial.

    explore, analysis and paper are launched with --deny-tool=shell(sbatch:*).
    An MCP tool that submits would route around that denial, so it is withheld
    from their allowlists — which is what actually hides it from them.
    """
    from mlragents.launcher import ROLES

    assert ROLES[role]["deny"], f"{role} is expected to be denied the scheduler"
    assert "mlragents-jobs_submit" not in agent_tools(role)


def test_experiment_may_submit_jobs():
    assert "mlragents-jobs_submit" in agent_tools("experiment")


def test_the_paper_agent_can_build_and_audit():
    tools = agent_tools("paper")
    assert "mlragents-paper_build" in tools
    assert "mlragents-paper_audit_numbers" in tools
    assert "mlragents-runs_provenance" in tools
