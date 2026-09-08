from pathlib import Path

from mlragents.scheduler.slurm import (
    Job,
    first_error,
    history,
    parse_sacct,
    parse_sbatch_job_id,
    parse_squeue,
    queue,
    tail_log,
)

SQUEUE_TEXT = "2541417|pers_comp|RUNNING|28:52|hpc-92-09\n"
SACCT_TEXT = "2541417|pers_comp|RUNNING|00:28:52|hpc-92-09|0:0\n"


def fake_run(stdout: str, returncode: int = 0):
    class Result:
        pass

    def runner(*args, **kwargs):
        result = Result()
        result.stdout = stdout
        result.stderr = ""
        result.returncode = returncode
        return result

    return runner


def test_parse_squeue():
    assert parse_squeue(SQUEUE_TEXT) == [
        Job("2541417", "pers_comp", "RUNNING", "28:52", "hpc-92-09", None)
    ]


def test_parse_squeue_ignores_blank_and_short_lines():
    assert parse_squeue("\n\nbroken|line\n" + SQUEUE_TEXT) == [
        Job("2541417", "pers_comp", "RUNNING", "28:52", "hpc-92-09", None)
    ]


def test_parse_sacct_keeps_exit_code():
    text = "2185255|pers_comp|TIMEOUT|4-00:00:18|hpc-22-15|1:0\n"
    assert parse_sacct(text) == [
        Job("2185255", "pers_comp", "TIMEOUT", "4-00:00:18", "hpc-22-15", "1:0")
    ]


def test_queue_uses_the_runner():
    assert queue("khargenr", run=fake_run(SQUEUE_TEXT))[0].job_id == "2541417"


def test_history_uses_the_runner():
    assert history("khargenr", run=fake_run(SACCT_TEXT))[0].state == "RUNNING"


def test_missing_binary_yields_empty_list():
    def exploding_run(*args, **kwargs):
        raise FileNotFoundError("squeue")

    assert queue("khargenr", run=exploding_run) == []
    assert history("khargenr", run=exploding_run) == []


def test_nonzero_return_yields_empty_list():
    assert queue("khargenr", run=fake_run("", returncode=1)) == []


def test_parse_sbatch_job_id():
    assert parse_sbatch_job_id("Submitted batch job 66132386\n") == "66132386"
    assert parse_sbatch_job_id("something else") is None


def test_tail_log_returns_last_lines(tmp_path: Path):
    log = tmp_path / "job.err"
    log.write_text("\n".join(str(i) for i in range(100)) + "\n")
    assert tail_log(log, lines=3).splitlines() == ["97", "98", "99"]


def test_tail_log_missing_file_is_empty(tmp_path: Path):
    assert tail_log(tmp_path / "absent.err") == ""


def test_first_error_finds_the_signal():
    text = (
        "warming up\n"
        "Traceback (most recent call last):\n"
        "  ...\n"
        "RuntimeError: CUDA out of memory\n"
    )
    assert first_error(text) == "RuntimeError: CUDA out of memory"
    assert first_error("all good\n") is None


def test_unfinished_jobs_have_no_exit_code():
    """sacct reports 0:0 for a running job; reading that as success is wrong."""
    text = (
        "2541417|pers_comp|RUNNING|00:48:34|hpc-92-09|0:0\n"
        "2185254|pers_comp|PENDING|00:00:00|None assigned|0:0\n"
        "2185255|pers_comp|TIMEOUT|4-00:00:18|hpc-22-15|0:0\n"
    )
    running, pending, timeout = parse_sacct(text)
    assert running.exit_code is None
    assert pending.exit_code is None
    assert timeout.exit_code == "0:0"
