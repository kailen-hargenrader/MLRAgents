import subprocess
from pathlib import Path

from mlragents.gitinfo import GitState, describe


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def make_repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "a.txt").write_text("one\n")
    git(tmp_path, "add", "a.txt")
    git(tmp_path, "commit", "-qm", "first")
    return tmp_path


def test_clean_repository(tmp_path):
    state = describe(make_repo(tmp_path))
    assert state.branch == "main"
    assert len(state.sha) == 40
    assert state.dirty_files == ()
    assert state.dirty is False


def test_dirty_repository_lists_files(tmp_path):
    root = make_repo(tmp_path)
    (root / "a.txt").write_text("two\n")
    (root / "b.txt").write_text("new\n")
    state = describe(root)
    assert state.dirty is True
    assert set(state.dirty_files) == {"a.txt", "b.txt"}


def test_outside_a_repository_is_empty_not_an_error(tmp_path):
    state = describe(tmp_path)
    assert state == GitState(sha=None, branch=None, dirty_files=())
    assert state.dirty is False


def test_git_failure_is_swallowed(tmp_path):
    def exploding_run(*args, **kwargs):
        raise OSError("git not installed")

    assert describe(tmp_path, run=exploding_run).sha is None
