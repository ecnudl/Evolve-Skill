"""Authored, no-Docker/no-API qualification and full-denominator replay controls."""
import base64
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import replay_sheet_v6 as replay
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import runner
from skillopt.continual_eval.core import BENCHMARKS, freeze_plan, read_json, write_json
from skillopt.continual_eval.fixtures import fixture_panel
from tests.test_continual_eval_sheet_recalc import workbook

IMAGE = "sha256:" + "a" * 64


class Fake:
    identity = {"fixture": True}

    def __init__(self, *, crash=False, cleanup=True):
        self.calls, self.crash, self.cleanup = [], crash, cleanup

    def run(self, path):
        path = Path(path)
        self.calls.append(replay.v5.sha(path))
        if self.crash:
            raise RuntimeError("authored interruption")
        raw = path.read_bytes()
        return seal({"identity": self.identity, "status": "available" if self.cleanup else "unknown",
            "reason": "authored_fixture" if self.cleanup else "container_cleanup_unconfirmed",
            "input_sha256": replay.v5.sha(path), "output_sha256": replay.v5.sha(path),
            "output_base64": base64.b64encode(raw).decode(), "model_api_calls": 0,
            "cleanup_confirmed": self.cleanup, "container_execution_attempted": True, "duration_seconds": .25})


def test_durable_engine_attempts_once_and_open_intent_cannot_reexecute(tmp_path):
    lock = tmp_path / "native.lock"
    lock.touch()
    book = workbook(tmp_path / "book.xlsx", cache=5)
    fake = Fake()
    engine = replay.DurableEngine(fake, tmp_path / "run", lock)
    assert engine.run(book) == engine.run(book)
    assert len(fake.calls) == 1
    assert replay._execution(engine)["containers_attempted"] == 1
    crashed = replay.DurableEngine(Fake(crash=True), tmp_path / "crash", lock)
    with pytest.raises(RuntimeError):
        crashed.run(book)
    assert replay._execution(crashed)["open_workbook_intents"] == 1
    with pytest.raises(ValueError, match="Open workbook"):
        crashed.run(book)
    other = workbook(tmp_path / "other.xlsx", cache=6)
    with pytest.raises(ValueError, match="Open workbook"):
        crashed.run(other)
    assert len(crashed.engine.calls) == 1


def test_cleanup_failure_is_durable_and_blocks_following_workbooks(tmp_path):
    lock = tmp_path / "native.lock"
    lock.touch()
    engine = replay.DurableEngine(Fake(cleanup=False), tmp_path / "run", lock)
    book = workbook(tmp_path / "book.xlsx", cache=5)
    assert engine.run(book)["status"] == "unknown"
    with pytest.raises(ValueError, match="cleanup unconfirmed"):
        engine.run(book)
    assert replay._execution(engine)["cleanup_unconfirmed"] == 1
    assert len(engine.engine.calls) == 1


def qualification_fixture(tmp_path):
    """Author a structurally bound qualification; never a real LO claim."""
    root = tmp_path / "qualification-fixture"
    lock = tmp_path / "native.lock"
    lock.touch(exist_ok=True)
    original = workbook(tmp_path / "fixture.xlsx", cache=5)
    native = replay.v6.Recalculator(IMAGE)
    protocol = seal({"version": replay.VERSION, "kind": "qualification", "root": str(root),
        "script_sha256": replay.v5.sha(replay.__file__), "engine": native.identity,
        "native_lock": str(lock), "inventory": replay._files([original]),
        "controls": [{"name": n, "path": str(original), "expected": 5}
                     for n in sorted(replay.CONTROLS | replay.NEW_CONTROLS)]})
    write_json(root / "protocol.json", protocol)
    fake = Fake()
    fake.identity = native.identity
    receipt = replay.DurableEngine(fake, root, lock).run(original)
    controls = []
    for item in protocol["controls"]:
        row = seal({"protocol_hash": protocol["record_hash"], "name": item["name"],
            "qualified": True, "receipt_hash": receipt["record_hash"], "cleanup_confirmed": True})
        write_json(root / "controls" / (item["name"] + ".json"), row)
        controls.append(row)
    q = seal({"version": replay.VERSION, "protocol_hash": protocol["record_hash"],
        "engine": native.identity, "status": "qualified", "model_api_calls": 0, "controls": controls})
    write_json(root / "qualification.json", q)
    return root / "qualification.json", lock


def parent_fixture(tmp_path, *, tasks=80):
    root = tmp_path / "parent"
    gold = workbook(tmp_path / "gold.xlsx", cache=5)
    prediction = workbook(tmp_path / "prediction.xlsx", cache=5)
    prediction.write_bytes(gold.read_bytes())  # Avoid ZIP timestamp differences in dedup fixture.
    panel = fixture_panel("spreadsheetbench")
    base = panel["tasks"][0]
    base.update(partition="development")
    base["public"].update(input_files=[str(prediction)], answer_position="B1")
    base["private"].update(test_files=[str(gold)], answer_position="B1",
                           asset_sha256={str(gold): replay.v5.sha(gold)})
    panel["tasks"] = [{**deepcopy(base), "task_id": f"fixture-{n}", "family_id": f"family-{n}"} for n in range(tasks)]
    path = tmp_path / "panel.json"
    write_json(path, panel)
    config = {"version": "continual-eval-v2", "order": list(BENCHMARKS), "partition": "development",
        "methods": ["no_skill"], "histories": ["h0"], "repeats": 2,
        "model": {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low",
            "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 1800,
                          "initial_health_policy": "completed_response_v1"}},
        "panels": {b: str(path) if b == "spreadsheetbench" else None for b in BENCHMARKS},
        "runtime": {}, "project_disjoint": False, "exposure_manifest": None}
    freeze_plan(config, root)
    n = 0
    def solve(*args, **kwargs):
        nonlocal n
        n += 1
        if n <= 8:
            return {"status": "unknown", "output": None, "reason": "model_response_truncated"}
        return {"status": "available", "reason": "authored_fixture", "output": {"cases": [{"status": "available",
            "output_base64": base64.b64encode(prediction.read_bytes()).decode()}]}}
    runner.generate(root, method="no_skill", history="h0", stage=0, benchmark="spreadsheetbench", fixture_solve=solve)
    runner.score_checkpoint(root, method="no_skill", history="h0", stage=0, benchmark="spreadsheetbench",
        fixture_score=lambda b, p, h, pred, **k: {"status": "unknown" if pred["status"] == "unknown" else "pass",
            "score": None if pred["status"] == "unknown" else 1., "reason": "authored_fixture", "metrics": {}})
    return root


def prepared_fixture(tmp_path, monkeypatch):
    q, lock = qualification_fixture(tmp_path)
    parent = parent_fixture(tmp_path)
    out = tmp_path / "replay"
    replay.prepare(parent, Path(__file__).resolve().parents[1], out, q, lock)
    calls = []
    def execute(self, path):
        fake = Fake()
        fake.identity = self.identity
        row = fake.run(path)
        calls.extend(fake.calls)
        return row
    monkeypatch.setattr(replay.v6.Recalculator, "run", execute)
    return parent, out, calls


def test_full_160_replay_keeps_eight_undelivered_and_never_modifies_parent(tmp_path, monkeypatch):
    parent, output, calls = prepared_fixture(tmp_path, monkeypatch)
    inventory = replay._files(list(parent.rglob("*.json")))
    result = replay.run(output)
    assert result["status"] == "complete" and result["positions"] == result["completed"] == 160
    assert result["counts"] == {"pass": 152, "unknown": 8}
    assert result["execution"]["containers_attempted"] == len(calls) == 1  # Identical fixture books share proof.
    assert result["model_api_calls"] == 0 and not result["historical_scores_replaced"]
    assert replay.run(output) == result and len(calls) == 1
    assert replay._files(list(parent.rglob("*.json"))) == inventory


def test_full_panel_required_and_old_v5_authorization_refused(tmp_path):
    q, lock = qualification_fixture(tmp_path)
    parent = parent_fixture(tmp_path, tasks=79)
    out = tmp_path / "replay"
    with pytest.raises(ValueError, match="80-task"):
        replay.prepare(parent, Path(__file__).resolve().parents[1], out, q, lock)
    assert not out.exists()
    value = read_json(q)
    value.pop("record_hash")
    value["version"] = replay.v5.VERSION
    q.write_text(__import__("json").dumps(seal(value)))
    with pytest.raises(ValueError, match="Independent complete v6"):
        replay.prepare(parent, Path(__file__).resolve().parents[1], out, q, lock)


def test_paused_run_submits_no_container(tmp_path, monkeypatch):
    _, output, calls = prepared_fixture(tmp_path, monkeypatch)
    (output / "PAUSE").touch()
    result = replay.run(output)
    assert result["status"] == "pending" and result["completed"] == 0
    assert not calls


def test_final_position_cleanup_failure_cannot_report_complete(tmp_path, monkeypatch):
    _, output, _ = prepared_fixture(tmp_path, monkeypatch)
    # One failed shared receipt is enough to stop the 160-slot traversal.
    calls = []
    def fail(self, path):
        fake = Fake(cleanup=False)
        fake.identity = self.identity
        calls.append(1)
        return fake.run(path)
    monkeypatch.setattr(replay.v6.Recalculator, "run", fail)
    result = replay.run(output)
    assert result["status"] == "pending" and result["execution"]["cleanup_unconfirmed"] == 1
    assert len(calls) == 1
    with pytest.raises(ValueError, match="cleanup unconfirmed"):
        replay.run(output)
    protocol = read_json(output / "protocol.json", sealed=True)
    for slot in protocol["slots"]:
        path = output / "positions" / (slot["id"] + ".json")
        if not path.exists():
            write_json(path, seal({"protocol_hash": protocol["record_hash"], "slot_id": slot["id"],
                "old_status": slot["old_status"], "status": "unknown", "cases": []}))
    # Even 160 terminal authored rows cannot turn unsafe teardown into complete.
    terminal = replay.report(output)
    assert terminal["completed"] == 160 and terminal["status"] == "pending"


def test_changed_original_prediction_or_engine_blocks_before_execution(tmp_path, monkeypatch):
    parent, output, calls = prepared_fixture(tmp_path, monkeypatch)
    next(parent.glob("predictions/*/prediction.json")).write_text("{}")
    with pytest.raises(ValueError, match="Frozen input changed"):
        replay.run(output)
    assert not calls


def test_failed_qualification_control_cannot_authorize_replay(tmp_path):
    q, lock = qualification_fixture(tmp_path)
    parent = parent_fixture(tmp_path)
    value = read_json(q)
    value.pop("record_hash")
    value["controls"][0]["qualified"] = False
    q.write_text(__import__("json").dumps(seal(value)))
    with pytest.raises(ValueError, match="Independent complete v6"):
        replay.prepare(parent, Path(__file__).resolve().parents[1], tmp_path / "replay", q, lock)


def test_qualification_driver_uses_new_engine_not_old_authorization(tmp_path, monkeypatch):
    q, lock = qualification_fixture(tmp_path)
    old = read_json(q.parent / "protocol.json", sealed=True)
    output = tmp_path / "new-qualification"
    protocol = {k: v for k, v in old.items() if k != "record_hash"}
    protocol["root"] = str(output)
    write_json(output / "protocol.json", seal(protocol))
    calls = []
    def execute(self, path):
        fake = Fake()
        fake.identity = self.identity
        calls.append(1)
        return fake.run(path)
    monkeypatch.setattr(replay.v6.Recalculator, "run", execute)
    def control(spec, receipt, directory):
        return {"name": spec["name"], "qualified": spec["name"] != "format30_wrong",
                "receipt_hash": receipt["record_hash"], "cleanup_confirmed": True, "reason": "authored_fixture"}
    monkeypatch.setattr(replay, "_control_result", control)
    result = replay.qualify(output)
    assert result["status"] == "rejected" and len(result["controls"]) == 20 and len(calls) == 1
    assert replay.qualify(output) == result and len(calls) == 1


@pytest.mark.parametrize("actual,qualified", [(6, True), (5, False)])
def test_wrong_control_requires_correctly_rejecting_wrong_answer(tmp_path, actual, qualified):
    source = workbook(tmp_path / "source.xlsx", "=SUM(A1:A2)+1")
    after = workbook(tmp_path / "after.xlsx", "=SUM(A1:A2)+1", cache=actual)
    fake = Fake()
    receipt = fake.run(after)
    spec = {"name": "wrong", "path": str(source), "expected": 6}
    assert replay._control_result(spec, receipt, tmp_path)["qualified"] is qualified


def test_unsupported_control_is_not_satisfied_by_execution_error(tmp_path):
    source = workbook(tmp_path / "source.xlsx", "=SKILLOPT_NOT_A_FUNCTION(A1)")
    receipt = {"status": "unknown", "reason": "recalculation_execution_error",
               "cleanup_confirmed": True, "record_hash": "fixture"}
    result = replay._control_result({"name": "unsupported", "path": str(source), "expected": "#NAME?"}, receipt, tmp_path)
    assert not result["qualified"]


def test_legacy_control_inputs_are_pinned_not_v6_authorization(tmp_path):
    legacy = tmp_path / "legacy"
    image = replay.v5.Recalculator(IMAGE)
    old_controls = []
    for name in sorted(replay.CONTROLS):
        fixture = legacy / "fixtures" / (name + ".xlsx")
        fixture.parent.mkdir(parents=True, exist_ok=True)
        workbook(fixture, cache=5)
        receipt = seal({"input_sha256": replay.v5.sha(fixture), "identity": image.identity,
                        "cleanup_confirmed": True, "model_api_calls": 0})
        write_json(legacy / "receipts" / (name + ".json"), receipt)
        old_controls.append({"name": name, "expected": 5, "qualified": True, "receipt_hash": receipt["record_hash"]})
    q = seal({"version": replay.v5.VERSION, "status": "qualified", "engine": image.identity,
              "controls": old_controls, "model_api_calls": 0})
    qpath = legacy / "qualification.json"
    write_json(qpath, q)
    lock = tmp_path / "native.lock"
    lock.touch()
    protocol = replay._qual_setup(tmp_path / "new", IMAGE, qpath, lock)
    assert len(protocol["controls"]) == 20 and not protocol["old_authorization_inherited"]
    assert protocol["engine"]["version"] == replay.v6.VERSION
    assert not (tmp_path / "new/qualification.json").exists()
    control = next(c for c in protocol["controls"] if c["name"] == "correct")
    Path(control["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="Frozen input changed"):
        replay._engine(protocol, tmp_path / "new")


def test_intent_reuses_do_not_accept_mismatched_receipt(tmp_path):
    lock = tmp_path / "native.lock"
    lock.touch()
    book = workbook(tmp_path / "book.xlsx", cache=5)
    engine = replay.DurableEngine(Fake(), tmp_path / "run", lock)
    engine.run(book)
    path = next((tmp_path / "run/recalculations").glob("*.json"))
    record = read_json(path)
    record.pop("record_hash")
    record["input_sha256"] = "0" * 64
    path.write_text(__import__("json").dumps(seal(record)))
    with pytest.raises(ValueError, match="Workbook receipt binding"):
        engine.run(book)


def test_published_replay_rows_cannot_be_resealed_to_new_scores(tmp_path, monkeypatch):
    _, output, _ = prepared_fixture(tmp_path, monkeypatch)
    replay.run(output)
    path = next(output.glob("positions/*.json"))
    row = read_json(path)
    row.pop("record_hash")
    row["status"] = "fail"
    path.write_text(__import__("json").dumps(seal(row)))
    with pytest.raises(ValueError, match="Published replay result changed"):
        replay.report(output)


def test_qualification_resume_rechecks_control_judgment(tmp_path, monkeypatch):
    q, _ = qualification_fixture(tmp_path)
    def changed(spec, receipt, directory):
        return {"name": spec["name"], "qualified": False,
                "receipt_hash": receipt["record_hash"], "cleanup_confirmed": True}
    monkeypatch.setattr(replay, "_control_result", changed)
    with pytest.raises(ValueError, match="Qualification control judgment changed"):
        replay.qualify(q.parent)
