"""Fixes v28-1 C7 classification and bounded container starts; authored offline fixtures."""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

from skillopt.execskill import engineer, profiles, replay, step
from skillopt.execskill.package import FIXTURE, empty
from tests.execskill_fakes_env import FakeSandbox
from tests.test_execskill_v24_engineer import GOOD, PUBLIC, change, context, detail
from tests.test_execskill_v28_execution import SeedWorkers, entries, procedure


def test_c7_ten_name_faults_cannot_hide_the_eleventh_nonverbatim_binding():
    entry, proc = entries()[0], procedure()
    outcome = replay.Outcome(entry["cell"], entry["bench"], applies=True)
    outcome.faults = [{"hook": "bindings", "step": None, "kind": "note_name", "detail": str(n)}
                      for n in range(10)]
    outcome.faults.append({"hook": "bindings", "step": None, "kind": "note_not_verbatim", "detail": "fatal"})
    result = replay.registrar_checks(proc, {entry["cell"]: entry}, {entry["cell"]: outcome})
    assert not result["passed"] and not result["measured_passed"]
    assert result["problem_count"] == 11 and result["fatal_problem_count"] == 1
    assert len(result["problems"]) == result["informational_problem_count"] == 10
    assert result["fatal_problems"][0]["kind"] == "note_not_verbatim"


class LosingWorkers(SeedWorkers):
    def __init__(self, fault):
        super().__init__()
        self.fault = fault

    @contextmanager
    def __call__(self, package, **options):
        with super().__call__(package, **options) as worker:
            original, ordinal = worker.call, len(self.opened)
            def call(pid, hook, args, **kwargs):
                if ordinal == 1 and hook == "before_call":
                    if self.fault == "dropped":
                        worker.dropped = [pid]
                    return {"ok": False, "fault": "worker" if self.fault == "dropped" else self.fault}
                return original(pid, hook, args, **kwargs)
            worker.call = call
            yield worker


@pytest.mark.parametrize("fault", ["worker", "not_loaded", "dropped"])
def test_c6_reopens_after_sticky_loss_and_continues_remaining_items(fault):
    values, workers = entries(), LosingWorkers(fault)
    report, first = replay.zero_crash(procedure(), values, workers)
    assert len(workers.opened) == 3 and workers.seeds == [0, 0, 0]
    assert first[values[0]["cell"]].faults and not first[values[0]["cell"]].notes
    assert all(first[value["cell"]].notes for value in values[1:])
    assert report["replay_workers"] == "per_pass" and report["informational"]


@pytest.mark.parametrize("fault", ["timeout", "exception"])
def test_c6_retains_healthy_worker_after_an_ordinary_hook_fault(fault):
    values, workers = entries(), LosingWorkers(fault)
    replay.zero_crash(procedure(), values, workers)
    assert len(workers.opened) == 2


def test_c6_separates_mounts_but_reuses_the_same_mount(tmp_path):
    values, workers = entries(), SeedWorkers()
    first, second = tmp_path / "input-a", tmp_path / "input-b"
    first.mkdir()
    second.mkdir()
    mounts = {value["cell"]: (first if n < 2 else second) for n, value in enumerate(values)}
    replay.zero_crash(procedure(), values, workers, inputs_dirs=mounts)
    assert [directory for _, directory, _ in workers.opened] == [first, second, second, first]
    assert workers.seeds == [0] * 4


@pytest.mark.parametrize("configuration", [profiles.ZEBRA_PC_V6, profiles.ALFWORLD_V3])
def test_training_package_pass_recovers_after_worker_loss(configuration):
    proc = procedure()
    # Route loss occurs in applies, so use a faulting router result on the first item.
    calls = []
    @contextmanager
    def opened(package, **options):
        calls.append(options)
        yield SimpleNamespace(dropped=[])
    st = SimpleNamespace(bench="searchqa", setting=SimpleNamespace(extra={"configuration": configuration}),
                         services=SimpleNamespace(workers=opened, item_workers=None))
    package = replay.solo(proc)
    from unittest.mock import patch
    def route(package, bench, view, worker):
        if view["n"] == 0:
            worker.dropped = [proc.id]
        return SimpleNamespace(faults=({"kind": "worker"},) if view["n"] == 0 else (), enabled=())
    with patch.object(step.router, "route", route):
        result = step._routes(st, package, [(str(n), {"n": n}) for n in range(60)], {})
    assert len(result) == 60 and len(calls) == 2
    assert all(options["hashseed"] == 0 for options in calls)
    assert result["0"].faults and not result["59"].faults


def test_sixty_item_engineer_check_uses_four_workers_and_retains_first_pass():
    ctx, workers = context(configuration=profiles.ZEBRA_PC_V6, views=[deepcopy(PUBLIC) for _ in range(60)])
    report = engineer.check(change(ctx, GOOD), ctx)
    assert report["passed"] and len(workers.opened) == 4  # C5, C6 forward/reverse, C6b+C6c.
    assert detail(report, "C6")["replay_workers"] == "per_pass"
    assert detail(report, "C6")["trajectories"] == 60
    assert detail(report, "C6c")["nonempty"] == 60


@pytest.mark.parametrize("configuration", [profiles.ZEBRA_PC_V6, profiles.ALFWORLD_V3])
@pytest.mark.parametrize("custom", [False, True])
def test_real_training_context_enables_shared_routing_only_for_common_mounts(tmp_path, monkeypatch,
                                                                          configuration, custom):
    parent, opened = empty(step="D/s0", evidence=FIXTURE), []
    @contextmanager
    def workers(package, **options):
        worker = FakeSandbox().start(package, kind=options["kind"], inputs_dir=options.get("inputs_dir"))
        opened.append((worker, options))
        try:
            yield worker
        finally:
            worker.close()
    @contextmanager
    def item_workers(package, item):
        with workers(package, kind="cell", hashseed=0) as worker:
            yield worker
    setting = SimpleNamespace(extra={"configuration": configuration}, evidence=FIXTURE, cards={}, runtime={"searchqa": {}})
    st = step._Step(setting, SimpleNamespace(workers=workers, item_workers=item_workers if custom else None),
                    "D", "searchqa", 1, parent, tmp_path)
    cut = {"run": [{"benchmark": "searchqa", "task_id": str(n),
                    "public": {"question": "Public question", "context": ["Public fact"]},
                    "private": {"answers": ["authored"]}} for n in range(60)]}
    def capture(ctx):
        assert ctx.routing_shared_worker is (not custom)
        passed, result = engineer._firing(procedure(), ctx)
        assert passed and result["fires_on"] == result["items"] == 60
        return None, {"captured": True}
    monkeypatch.setattr(st, "unit", lambda name, work, **kwargs: work(tmp_path))
    monkeypatch.setattr(st, "roles", lambda _: None)
    for name in ("_earlier", "_run_trajectories", "_current", "_evaluated"):
        monkeypatch.setattr(step, name, lambda *args, **kwargs: [])
    monkeypatch.setattr(engineer, "run_train", capture)
    step._engineer_train(st, cut, 1, parent, done=[], fed=None, history=[], training=None, lint=[],
                         reserved=[], analysed=[], disclosed=[])
    assert len(opened) == (60 if custom else 1)
    assert sum(len(worker.calls) for worker, _ in opened) == 60
    assert all(options["hashseed"] == 0 and worker.closed for worker, options in opened)


def test_training_custom_mount_boundaries_remain_item_scoped():
    opened = []
    @contextmanager
    def item_workers(package, item):
        opened.append(item)
        yield SimpleNamespace()
    st = SimpleNamespace(bench="spreadsheetbench", setting=SimpleNamespace(extra={"configuration": profiles.ZEBRA_PC_V6}),
                         services=SimpleNamespace(item_workers=item_workers))
    package = SimpleNamespace(for_bench=lambda bench: ["p"])
    from unittest.mock import patch
    with patch.object(step.router, "route", lambda *args: SimpleNamespace(faults=())):
        step._routes(st, package, [("a", {}), ("b", {})], {})
    assert opened == ["a", "b"]
