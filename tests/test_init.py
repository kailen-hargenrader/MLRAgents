import pytest

from mlragents.config import find_project
from mlragents.init import AlreadyInitialised, init_project


def test_creates_the_prescribed_structure(tmp_path):
    init_project(tmp_path, name="demo")
    assert (tmp_path / "explore").is_dir()
    assert (tmp_path / "exploit").is_dir()
    assert (tmp_path / "paper").is_dir()
    assert (tmp_path / ".mlragents.toml").is_file()


def test_each_lane_states_what_it_means(tmp_path):
    """A bare directory does not carry the distinction the split exists for."""
    init_project(tmp_path, name="demo")
    explore = (tmp_path / "explore" / "README.md").read_text()
    exploit = (tmp_path / "exploit" / "README.md").read_text()
    assert "never" in explore.lower()
    assert "cite" in explore.lower() or "evidence" in explore.lower()
    assert "paper" in exploit.lower()


def test_written_config_round_trips(tmp_path):
    init_project(tmp_path, name="demo")
    config = find_project(tmp_path)
    assert config.name == "demo"
    assert set(config.lanes) == {"explore", "exploit"}
    assert config.lane("exploit").outputs_dir(tmp_path) == tmp_path / "exploit" / "outputs"


def test_registry_directory_is_ignored_by_git(tmp_path):
    init_project(tmp_path, name="demo")
    assert ".mlragents/" in (tmp_path / ".gitignore").read_text()


def test_an_existing_gitignore_is_appended_to_not_replaced(tmp_path):
    (tmp_path / ".gitignore").write_text("*.pyc\n")
    init_project(tmp_path, name="demo")
    text = (tmp_path / ".gitignore").read_text()
    assert "*.pyc" in text
    assert ".mlragents/" in text


def test_the_ignore_entry_is_not_duplicated(tmp_path):
    (tmp_path / ".gitignore").write_text(".mlragents/\n")
    init_project(tmp_path, name="demo")
    assert (tmp_path / ".gitignore").read_text().count(".mlragents/") == 1


def test_refuses_to_overwrite_an_initialised_project(tmp_path):
    init_project(tmp_path, name="demo")
    with pytest.raises(AlreadyInitialised) as excinfo:
        init_project(tmp_path, name="other")
    assert ".mlragents.toml" in str(excinfo.value)


def test_existing_lane_directories_are_left_alone(tmp_path):
    keep = tmp_path / "explore" / "old"
    keep.mkdir(parents=True)
    (keep / "note.md").write_text("prior work\n")
    init_project(tmp_path, name="demo")
    assert (keep / "note.md").read_text() == "prior work\n"


def test_returns_the_paths_it_created(tmp_path):
    created = init_project(tmp_path, name="demo")
    assert tmp_path / ".mlragents.toml" in created


def test_the_scaffolded_structure_survives_a_clone(tmp_path):
    """git does not track directories; without .gitkeep the layout is lost."""
    init_project(tmp_path, name="p")
    for empty in ("explore/outputs", "exploit/outputs", "paper"):
        assert (tmp_path / empty / ".gitkeep").is_file(), f"{empty} would vanish"


def test_the_keepfiles_are_reported_as_created(tmp_path):
    created = init_project(tmp_path, name="p")
    names = {p.name for p in created}
    assert ".gitkeep" in names


def test_a_run_directory_is_not_mistaken_for_a_keepfile(tmp_path):
    """.gitkeep must not make an empty outputs tree look like it holds runs."""
    from mlragents.config import load
    from mlragents.sync import discover_outputs

    init_project(tmp_path, name="p")
    assert discover_outputs(load(tmp_path / ".mlragents.toml")) == []


def test_the_scaffolded_config_parses_and_commented_keys_are_valid(tmp_path):
    """The commented examples are what users uncomment; they must be real TOML."""
    import re
    import tomllib

    init_project(tmp_path, name="demo")
    text = (tmp_path / ".mlragents.toml").read_text()
    tomllib.loads(text)

    # Uncomment only the lines that are a commented-out key/value pair.
    kv = re.compile(r"^# ([A-Za-z_]+\s*=)")
    uncommented = "\n".join(
        line[2:] if kv.match(line) else line for line in text.splitlines()
    )
    parsed = tomllib.loads(uncommented)
    assert "train" in parsed["commands"]
    assert parsed["paths"]["generated"] == ["exploit/configs"]
