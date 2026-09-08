from mlragents.registry import Registry, Run, default_path


def make_registry(tmp_path) -> Registry:
    return Registry(default_path(tmp_path))


def test_default_path_is_inside_the_repo(tmp_path):
    assert default_path(tmp_path) == tmp_path / ".mlragents" / "registry.sqlite"


def test_record_then_get_round_trips(tmp_path):
    registry = make_registry(tmp_path)
    run = Run(
        run_id="r1",
        grid="ablation",
        cell="softmax_train_prenorm",
        config_path="configs/ablation/softmax_train_prenorm.yaml",
        config_hash="abc123",
        git_sha="0" * 40,
        git_dirty=False,
        seed=1234,
        job_id="66132386",
        node="hpc-92-01",
        submitted_at="2026-09-08T12:00:00",
        status="RUNNING",
        outputs_path="outputs/2026-09-08/ablation/softmax_train_prenorm",
    )
    registry.record(run)
    assert registry.get("r1") == run


def test_record_is_an_upsert(tmp_path):
    registry = make_registry(tmp_path)
    registry.record(Run(run_id="r1", status="PENDING"))
    registry.record(Run(run_id="r1", status="RUNNING"))
    assert registry.get("r1").status == "RUNNING"
    assert len(registry.list()) == 1


def test_list_is_newest_first_and_filters(tmp_path):
    registry = make_registry(tmp_path)
    registry.record(
        Run(
            run_id="old",
            grid="a",
            status="COMPLETED",
            submitted_at="2026-01-01T00:00:00",
        )
    )
    registry.record(
        Run(
            run_id="new",
            grid="b",
            status="RUNNING",
            submitted_at="2026-02-01T00:00:00",
        )
    )
    assert [r.run_id for r in registry.list()] == ["new", "old"]
    assert [r.run_id for r in registry.list(grid="a")] == ["old"]
    assert [r.run_id for r in registry.list(status="RUNNING")] == ["new"]
    assert [r.run_id for r in registry.list(limit=1)] == ["new"]


def test_set_status_updates_by_job_id(tmp_path):
    registry = make_registry(tmp_path)
    registry.record(Run(run_id="r1", job_id="42", status="RUNNING"))
    assert registry.set_status("42", "COMPLETED", finished_at="2026-09-08T13:00:00") == 1
    stored = registry.get("r1")
    assert stored.status == "COMPLETED"
    assert stored.finished_at == "2026-09-08T13:00:00"
    assert registry.set_status("999", "COMPLETED") == 0


def test_get_missing_returns_none(tmp_path):
    assert make_registry(tmp_path).get("nope") is None


def test_opening_twice_is_safe(tmp_path):
    make_registry(tmp_path).record(Run(run_id="r1"))
    assert make_registry(tmp_path).get("r1").run_id == "r1"


def test_lane_round_trips(tmp_path):
    registry = Registry(tmp_path / "r.sqlite")
    registry.record(Run(run_id="exploit/a", lane="exploit"))
    assert registry.get("exploit/a").lane == "exploit"


def test_list_filters_by_lane(tmp_path):
    registry = Registry(tmp_path / "r.sqlite")
    registry.record(Run(run_id="exploit/a", lane="exploit"))
    registry.record(Run(run_id="explore/a", lane="explore"))
    assert [r.run_id for r in registry.list(lane="exploit")] == ["exploit/a"]
    assert len(registry.list()) == 2


def test_a_run_without_a_lane_is_allowed(tmp_path):
    registry = Registry(tmp_path / "r.sqlite")
    registry.record(Run(run_id="x"))
    assert registry.get("x").lane is None
