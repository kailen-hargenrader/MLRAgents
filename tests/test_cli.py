import mlragents
from mlragents.cli import main


def test_version_is_a_string():
    assert isinstance(mlragents.__version__, str)
    assert mlragents.__version__


def test_version_command_prints_version(capsys):
    exit_code = main(["--version"])
    assert exit_code == 0
    assert mlragents.__version__ in capsys.readouterr().out


def test_unknown_command_is_an_error(capsys):
    assert main(["no-such-command"]) == 2


def test_init_scaffolds_in_the_working_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init", "--name", "demo"]) == 0
    assert (tmp_path / "exploit" / "outputs").is_dir()
    assert "explore/ is insight" in capsys.readouterr().out


def test_init_refuses_twice(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(["init", "--name", "demo"])
    assert main(["init", "--name", "demo"]) == 1
    assert "already exists" in capsys.readouterr().err


def test_run_prints_the_argv_for_a_role(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(["init", "--name", "demo"])
    capsys.readouterr()
    assert main(["run", "explore", "--print-argv"]) == 0
    printed = capsys.readouterr().out
    assert "--agent=mlragents:explore" in printed
    assert "sbatch" in printed


def test_run_rejects_an_unknown_role(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    main(["init", "--name", "demo"])
    capsys.readouterr()
    assert main(["run", "nonsense", "--print-argv"]) == 2
    assert "known roles" in capsys.readouterr().err


def test_run_without_a_project_explains_how_to_start(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["run", "explore", "--print-argv"]) == 1
    assert "mlragents init" in capsys.readouterr().err
