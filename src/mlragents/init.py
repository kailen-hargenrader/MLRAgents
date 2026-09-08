"""Scaffold the prescribed repository structure.

The two lanes are the point, so the scaffolding writes down what each one means
rather than leaving two empty directories whose distinction lives only in
somebody's memory.
"""

from __future__ import annotations

from pathlib import Path

from mlragents.config import CONFIG_NAME

IGNORE_ENTRY = ".mlragents/"

EXPLORE_README = """# explore

Insight, not evidence.

Runs here exist to tell you what to try next. They may use a dirty tree, a
single seed, a half-finished idea. **Nothing in this directory is ever cited in
the paper.**

Promoting a finding means re-running the experiment in `../exploit` from a clean
tree. Never copy results across the boundary: that launders the provenance and
destroys the only thing this separation buys you.
"""

EXPLOIT_README = """# exploit

The paper's experiment repository.

Every number in the manuscript traces to a run under here. That is the whole
contract. In exchange, work in this directory is disciplined: clean tree before
launching, configs written by the generator rather than by hand, every run
recorded.

If you are not sure whether an experiment belongs here, it belongs in
`../explore`.
"""

CONFIG_TEMPLATE = """[project]
name = "{name}"
python = "{python}"

[paths]
paper = "paper"

# Insight. Never cited.
[explore]
root = "explore"
outputs = "outputs"

# Evidence. Everything in the paper comes from here.
[exploit]
root = "exploit"
outputs = "outputs"
# Declare how a run's path encodes its experiment, e.g.
# run_pattern = ["{{grid}}/{{cell}}/**"]

[scheduler]
kind = "{scheduler}"
log_dir = "slurm_logs"

[commands]
# Declare the commands this repository uses. Tools that need one and do not
# find it fail with the name of the missing key.
"""


class AlreadyInitialised(FileExistsError):
    """The directory already has a .mlragents.toml."""


def init_project(
    root: Path,
    name: str,
    python: str = "uv run python",
    scheduler: str = "slurm",
) -> list[Path]:
    root = Path(root)
    config_path = root / CONFIG_NAME
    if config_path.exists():
        raise AlreadyInitialised(
            f"{config_path} already exists; edit it rather than re-running init"
        )

    created: list[Path] = []
    for lane, readme in (("explore", EXPLORE_README), ("exploit", EXPLOIT_README)):
        (root / lane / "outputs").mkdir(parents=True, exist_ok=True)
        readme_path = root / lane / "README.md"
        if not readme_path.exists():
            readme_path.write_text(readme)
            created.append(readme_path)
    (root / "paper").mkdir(parents=True, exist_ok=True)

    config_path.write_text(
        CONFIG_TEMPLATE.format(name=name, python=python, scheduler=scheduler)
    )
    created.append(config_path)

    ignore = root / ".gitignore"
    existing = ignore.read_text() if ignore.is_file() else ""
    if IGNORE_ENTRY not in existing.split():
        prefix = existing if existing.endswith("\n") or not existing else existing + "\n"
        ignore.write_text(f"{prefix}{IGNORE_ENTRY}\n")
        created.append(ignore)
    return created
