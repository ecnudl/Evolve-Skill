"""execskill consumption registry (registration §3.4; plan §2.7): T-REG-1..6 on a temporary history root."""
import json
import re
import threading

import pytest

from skillopt.execskill import registry as reg
from skillopt.execskill import supply
from skillopt.execskill.errors import ConsumptionConflict
from skillopt.validator_pilot.api import digest
from tests.fixtures.execskill import items as fx

BENCH = "searchqa"


def _registry(tmp_path, **kwargs):
    return reg.Registry(tmp_path / "history", evidence="engineering_fixture", **kwargs)


def _lines(registry, chain, bench=BENCH):
    path = registry.path(chain, bench)
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_lines_are_versioned_records_at_a_run_root_independent_path(tmp_path):
    registry = _registry(tmp_path)
    items = fx.searchqa_items(3)
    assert registry.register("D", BENCH, items, unit="pilot/u1", purpose="run", run_root="/r/pilot") == 3
    assert registry.path("D", BENCH) == tmp_path / "history" / "consumption" / "D" / "searchqa.jsonl"
    for text in _lines(registry, "D"):
        line = json.loads(text)
        assert set(line) == reg.FIELDS
        assert line["version"] == "fivebench-execskill-v1-consumption"
        assert line["evidence"] == "engineering_fixture" and line["state"] == "registered"
        assert line["record_sha256"] == digest({k: v for k, v in line.items() if k != "record_sha256"})
    with pytest.raises(ValueError):
        reg.Registry(tmp_path / "other", evidence="formal_guess")
    with pytest.raises(ValueError):
        registry.path("E", BENCH)


def test_states_move_forward_only(tmp_path):  # T-REG-1
    registry = _registry(tmp_path)
    a, b, c = fx.searchqa_items(3)
    registry.register("G", BENCH, [a, b, c], unit="u1", purpose="accept", run_root="/r")
    with pytest.raises(ValueError, match="decided before dispatched"):
        registry.decide("G", BENCH, [a], unit="u1")
    assert registry.dispatch("G", BENCH, [a, b], unit="u1") == 2
    with pytest.raises(ValueError, match="cannot be released"):
        registry.release("G", BENCH, [a], unit="u1")
    assert registry.decide("G", BENCH, [a], unit="u1") == 1
    with pytest.raises(ValueError, match="forward only"):
        registry.dispatch("G", BENCH, [a], unit="u1")
    with pytest.raises(ValueError, match="consumed"):
        registry.register("G", BENCH, [a], unit="u1", purpose="accept", run_root="/r")
    with pytest.raises(ValueError, match="not registered"):
        registry.dispatch("G", BENCH, fx.searchqa_items(4)[3:], unit="u1")
    states = {i: line["state"] for i, line in registry.entries("G", BENCH).items()}
    assert states == {a["task_id"]: "decided", b["task_id"]: "dispatched", c["task_id"]: "registered"}
    assert registry.consumed("G", BENCH) == {a["task_id"], b["task_id"], c["task_id"]}


def test_another_unit_conflicts_and_a_failing_call_writes_nothing(tmp_path):  # T-REG-2
    registry = _registry(tmp_path)
    a, b, c = fx.searchqa_items(3)
    registry.register("D", BENCH, [a], unit="u1", purpose="run", run_root="/r")
    before = _lines(registry, "D")
    for call in (lambda: registry.register("D", BENCH, [c, a], unit="u2", purpose="run", run_root="/r"),
                 lambda: registry.dispatch("D", BENCH, [a], unit="u2"),
                 lambda: registry.release("D", BENCH, [a], unit="u2")):
        with pytest.raises(ConsumptionConflict):
            call()
    assert _lines(registry, "D") == before  # c was free, yet nothing of the failing call was written
    registry.dispatch("D", BENCH, [a], unit="u1")
    registry.decide("D", BENCH, [a], unit="u1")
    with pytest.raises(ConsumptionConflict):  # a decided item stays consumed for every other unit
        registry.register("D", BENCH, [a, b], unit="u3", purpose="accept", run_root="/r")
    assert b["task_id"] not in registry.consumed("D", BENCH)


def test_redo_reuses_its_own_registration(tmp_path):  # T-REG-3
    registry = _registry(tmp_path)
    block = fx.searchqa_items(4)
    registry.register("G", BENCH, block, unit="accept-b1", purpose="accept", run_root="/r", attempt=1)
    registry.dispatch("G", BENCH, block, unit="accept-b1", attempt=1)
    count = len(_lines(registry, "G"))
    # attempt 2 re-dispatches the whole block with the same registry entries: nothing new is written
    assert registry.register("G", BENCH, block, unit="accept-b1", purpose="accept", run_root="/r", attempt=2) == 0
    assert registry.dispatch("G", BENCH, block, unit="accept-b1", attempt=2) == 0
    assert len(_lines(registry, "G")) == count
    assert registry.decide("G", BENCH, block, unit="accept-b1", attempt=2) == 4
    assert {line["attempt"] for line in registry.entries("G", BENCH).values()} == {2}
    extra = fx.searchqa_items(5)[4:]
    registry.register("G", BENCH, extra, unit="x", purpose="run", run_root="/r")
    with pytest.raises(ValueError, match="for purpose run"):
        registry.register("G", BENCH, extra, unit="x", purpose="accept", run_root="/r")
    changed = dict(block[0], public={"question": "changed", "context": "changed"})
    other = _registry(tmp_path / "second")
    other.register("D", BENCH, block[:1], unit="u", purpose="run", run_root="/r")
    with pytest.raises(ValueError, match="changed"):
        other.dispatch("D", BENCH, [changed], unit="u")


def test_release_returns_items_to_the_supply(tmp_path):  # T-REG-4
    registry = _registry(tmp_path)
    a, b = fx.searchqa_items(2)
    registry.register("D", BENCH, [a, b], unit="accept-s1", purpose="accept", run_root="/r")
    registry.dispatch("D", BENCH, [a], unit="accept-s1")
    assert registry.release("D", BENCH, [b], unit="accept-s1") == 1  # routed outside A*
    assert registry.release("D", BENCH, [b], unit="accept-s1") == 0
    assert registry.consumed("D", BENCH) == {a["task_id"]}
    assert registry.entries("D", BENCH)[b["task_id"]]["state"] == "routed_not_dispatched"
    with pytest.raises(ValueError, match="register it first"):
        registry.dispatch("D", BENCH, [b], unit="accept-s1")
    registry.register("D", BENCH, [b], unit="accept-s2", purpose="accept", run_root="/r")  # back in the supply
    registry.dispatch("D", BENCH, [b], unit="accept-s2")
    assert registry.entries("D", BENCH)[b["task_id"]]["unit"] == "accept-s2"


def test_root_independence_and_tamper_refusal(tmp_path):  # T-REG-5
    history = tmp_path / "history"
    smoke_side = reg.Registry(history, evidence="smoke")
    pilot_side = reg.Registry(history, evidence="pilot_real_run")
    item = fx.searchqa_items(1)
    smoke_side.register("G", BENCH, item, unit="u-pre", purpose="run", run_root="/data/execskill-20261021-pre")
    with pytest.raises(ConsumptionConflict):  # another run root, the same history: the same registry
        pilot_side.register("G", BENCH, item, unit="u-pilot", purpose="run", run_root="/data/execskill-20261021-pilot")
    assert reg.Registry(tmp_path / "elsewhere", evidence="smoke").consumed("G", BENCH) == frozenset()
    path = smoke_side.path("G", BENCH)
    line = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps(dict(line, unit="u-other")) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="not a valid record"):
        pilot_side.consumed("G", BENCH)
    forged = dict(line, state="decided")
    forged["record_sha256"] = digest({k: v for k, v in forged.items() if k != "record_sha256"})
    path.write_text(json.dumps(forged) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="forward move"):
        pilot_side.consumed("G", BENCH)


def test_chains_have_separate_namespaces_and_smoke_items_leave_both_supplies(tmp_path):  # T-REG-6
    registry = _registry(tmp_path)
    pool = fx.searchqa_items(20)
    registry.register("D", BENCH, pool[:3], unit="D:run", purpose="run", run_root="/r")
    registry.dispatch("D", BENCH, pool[:3], unit="D:run")
    registry.decide("D", BENCH, pool[:3], unit="D:run")
    assert registry.register("G", BENCH, pool[:3], unit="G:run", purpose="run", run_root="/r") == 3
    assert registry.dispatch("G", BENCH, pool[:3], unit="G:run") == 3  # once in chain G as well
    with pytest.raises(ConsumptionConflict):
        registry.register("G", BENCH, pool[:1], unit="G:accept", purpose="accept", run_root="/r")
    with pytest.raises(ValueError, match="smoke"):
        registry.register("smoke", BENCH, pool[3:4], unit="S2", purpose="run", run_root="/r")
    with pytest.raises(ValueError, match="smoke"):
        registry.register("G", BENCH, pool[3:4], unit="G:x", purpose="smoke", run_root="/r")
    order = supply.order(BENCH, pool)
    smoke = supply.slices(BENCH, order, {"smoke": 5})["smoke"]
    registry.register("smoke", BENCH, smoke, unit="S-N1", purpose="smoke", run_root="/data/execskill-20261021-pre")
    held = registry.consumed("smoke", BENCH)
    cut = supply.slices(BENCH, order, {"smoke": 5, "run": 10}, consumed=held)  # the same cut for G and D
    assert not {i["task_id"] for i in cut["run"]} & held and len(cut["run"]) == 10
    assert cut["run"] == supply.slices(BENCH, order, {"smoke": 5, "run": 10})["run"]


def test_concurrent_writers_are_serialised_by_the_lock(tmp_path):
    registry = _registry(tmp_path)
    item = fx.searchqa_items(1)
    outcomes = []

    def claim(unit):
        try:
            outcomes.append(_registry(tmp_path).register("D", BENCH, item, unit=unit, purpose="run", run_root="/r"))
        except ConsumptionConflict:
            outcomes.append("conflict")

    threads = [threading.Thread(target=claim, args=("unit-%d" % n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes, key=str) == [1] + ["conflict"] * 7
    assert len(_lines(registry, "D")) == 1


def test_codex7_identical_labels_in_two_run_roots_never_share_an_item(tmp_path):
    """Codex finding #7 (registration §3.1-§3.4): a unit is its label AND its run root. Labels such as
    ``G/s1-searchqa/run`` repeat in every run root of one history, so the same label under another root conflicts on
    every move (register, dispatch, decide, release) while the owning root's redo reuses its own registration and
    settles idempotently; a registry bound to one root refuses a move naming another, a registration names its root,
    and a correctly hashed line moving the item for the same label of another root is not a forward move."""
    registry = _registry(tmp_path)
    first, second, label = tmp_path / "pilot", tmp_path / "main", "G/s1-searchqa/run"
    a, b = fx.searchqa_items(2)
    assert registry.register("G", BENCH, [a], unit=label, purpose="run", run_root=first) == 1
    before, other, own = _lines(registry, "G"), registry.bound(second), registry.bound(first)
    for call in (lambda: other.register("G", BENCH, [b, a], unit=label, purpose="run"),
                 lambda: other.dispatch("G", BENCH, [a], unit=label),
                 lambda: registry.dispatch("G", BENCH, [a], unit=label, run_root=second),
                 lambda: other.release("G", BENCH, [a], unit=label)):
        with pytest.raises(ConsumptionConflict, match=re.escape("of run root " + reg.run_identity(first))):
            call()
    assert _lines(registry, "G") == before  # b was free, yet nothing of the failing calls was written
    assert own.register("G", BENCH, [a], unit=label, purpose="run", attempt=2) == 0  # the owning root's redo
    assert own.dispatch("G", BENCH, [a], unit=label, attempt=2) == 1
    with pytest.raises(ConsumptionConflict):
        other.decide("G", BENCH, [a], unit=label, attempt=2)
    assert own.decide("G", BENCH, [a], unit=label, attempt=2) == 1
    assert own.decide("G", BENCH, [a], unit=label, attempt=3) == 0  # settled again: nothing written (Codex #8)
    with pytest.raises(ConsumptionConflict):  # decided: consumed for the same label of every other root
        other.register("G", BENCH, [a], unit=label, purpose="run")
    with pytest.raises(ValueError, match="another run root"):
        own.dispatch("G", BENCH, [a], unit=label, run_root=second)
    with pytest.raises(ValueError, match="names its run root"):
        registry.register("G", BENCH, [b], unit=label, purpose="run")
    line = registry.entries("G", BENCH)[a["task_id"]]
    assert (line["state"], line["run_root"], line["unit"]) == ("decided", reg.run_identity(first), label)
    assert other.register("G", BENCH, [b], unit=label, purpose="run") == 1  # a free item: the other root's own
    path = registry.path("G", BENCH)
    texts = path.read_text(encoding="utf-8").splitlines()
    dispatched = json.loads(texts[1])
    assert (dispatched["state"], dispatched["item_id"]) == ("dispatched", a["task_id"])
    forged = dict(dispatched, run_root=reg.run_identity(second))
    forged["record_sha256"] = digest({k: v for k, v in forged.items() if k != "record_sha256"})
    path.write_text("\n".join([texts[0], json.dumps(forged)] + texts[2:]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="forward move"):
        registry.entries("G", BENCH)
