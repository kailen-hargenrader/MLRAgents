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
