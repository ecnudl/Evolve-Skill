"""v2.4 candidate-only patience and actual run-output feedback; authored zero-call fixtures."""
import copy
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.coevo5.data import item_hash
from skillopt.execskill import engineer_payload, profiles as p, rounds, step, zebralogic as z
from skillopt.execskill.registry import run_identity


def train_rounds(monkeypatch, configuration, outcomes):
    """Drive the real six-round loop with scripted checked proposals and training verdicts."""
    parent = SimpleNamespace(sha256="parent")
    st = SimpleNamespace(parent=parent, setting=SimpleNamespace(extra={"configuration": configuration}))
    asked, evaluated = [], []
    def propose(st, cut, r, incumbent, **given):
        asked.append({"round": r, **copy.deepcopy(given)})
        candidate = None if outcomes[r - 1] == "none" else "candidate-%d" % r
        return {"candidate_sha256": candidate, "engineer": {
            "changes": [], "analysis": {"items": []}, "disclosed": [], "lint": []}}
    def evaluate(st, cut, r, incumbent, candidate, generated, **given):
        evaluated.append(r)
        adopted = outcomes[r - 1] == "adopt"
        verdict = {"adopted": adopted, "items": 1, "generated": 0, "fixed": ["a"] if adopted else [],
                   "broken": [], "net": "1/1" if adopted else "0/1", "p_sign": 0.5,
                   "reason": None if adopted else "gain:fixed_over_broken"}
        return {"candidate_sha256": candidate.sha256, "cells": 2, "adopted": adopted,
                "verdict": verdict, "feedback": {"round": r}}
    monkeypatch.setattr(step, "_engineer_train", propose)
    monkeypatch.setattr(step, "_train_eval", evaluate)
    monkeypatch.setattr(step, "_package", lambda st, sha: SimpleNamespace(sha256=sha))
    monkeypatch.setattr(step, "_current", lambda st, done: [])
    final, records, last = step._train(st, {"run": []}, None)
    return final, records, asked, evaluated


def test_no_candidate_rounds_do_not_use_patience_but_six_round_maximum_remains(monkeypatch):
    final, records, asked, evaluated = train_rounds(monkeypatch, p.ZEBRA_PC_V2, ["none"] * 6)
    assert p.TRAIN_ROUNDS == 6 and len(records) == len(asked) == 6
    assert final.sha256 == "parent" and evaluated == []
    assert all(row["patience_counted"] is False and row["candidate"] is False for row in records)
    assert asked[5]["history"] == [{k: v for k, v in row.items()
                                    if k not in ("candidate_sha256", "incumbent_sha256")} for row in records[:5]]


def test_only_two_unsuccessful_candidate_rounds_trigger_patience(monkeypatch):
    _, records, asked, evaluated = train_rounds(monkeypatch, p.ZEBRA_PC_V2,
        ["none", "miss", "none", "miss", "adopt", "adopt"])
    assert evaluated == [2, 4] and len(records) == len(asked) == 4
    assert [row["patience_counted"] for row in records] == [False, True, False, True]


def test_adoption_resets_candidate_patience_across_no_candidate_rounds(monkeypatch):
    final, records, _, evaluated = train_rounds(monkeypatch, p.ZEBRA_PC_V2,
        ["miss", "none", "adopt", "miss", "none", "miss"])
    assert len(records) == 6 and evaluated == [1, 3, 4, 6] and final.sha256 == "candidate-3"
    assert [row["patience_counted"] for row in records] == [True, False, True, True, False, True]


@pytest.mark.parametrize("configuration", (p.MAIN_V2, p.MAIN_V2_1, p.MAIN_V2_2, p.MAIN_V2_3, p.ZEBRA_PC_V1))
def test_older_training_counts_no_candidate_rounds_and_keeps_record_fields(configuration, monkeypatch):
    _, records, asked, evaluated = train_rounds(monkeypatch, configuration, ["none"] * 6)
    assert len(records) == len(asked) == 2 and evaluated == []
    assert all("patience_counted" not in row for row in records)
    assert all("patience_counted" not in row for request in asked for row in request["history"])


def feedback_fixture(tmp_path, *, configuration=None, count=8):
    items = []
    for n in range(count):
        items.append({"task_id": "run-%d" % n, "benchmark": z.BENCH,
            "public": {"question": "There are 5 houses, numbered 1 to 5 from left to right, as seen from across "
                       "the street. Authored clue set %d." % n, "columns": ["Color"]},
            "private": {"answer": {"House %d" % h: {"Color": "RUNPRIVATE-%d-%d-" % (n, h) + "x" * 300}
                                    for h in range(1, 6)}}})
    root, label = tmp_path / "run", lambda name: "D/s1-zebralogic/" + name
    entries = {item["task_id"]: {"state": "decided", "unit": label("run"), "purpose": "run",
        "run_root": run_identity(root), "item_hash": item_hash(item)} for item in items}
    st = SimpleNamespace(bench=z.BENCH, label=label, purpose=lambda name: name, namespace="D-zpc2",
        runtime=lambda: {}, setting=SimpleNamespace(root=root, extra={"configuration": configuration or p.ZEBRA_PC_V2}),
        services=SimpleNamespace(registry=SimpleNamespace(entries=lambda namespace, bench: entries)))
    cut = {"run": items, **{name: [{"private": {"answer": name.upper() + "PRIVATE-SENTINEL"}}]
                          for name in ("accept", "smoke", "spare", "sealed")}}
    return st, cut, entries


def trajectory(item, arm, token, *, note="", run=0):
    key = rounds.key(z.BENCH, item["task_id"])
    return {"cell": "%s/%s/%d" % (arm, key, run), "task_id": key, "arm": arm,
            "arm_kind": "candidate" if arm == "S'" else "parent", "bench": z.BENCH, "run": run,
            "token": token, "calls": [{"user": z.render_user(item["public"], note)}],
            "replies": ["first response", "FINAL-ANSWER-" + item["task_id"] + "a" * 900]}


def add_cell(cells, made, trajectory):
    cell = {"cell": {"id": trajectory["cell"], "task_id": trajectory["task_id"], "arm": trajectory["arm"],
                      "run": trajectory["run"]}, "judge": {"v2": {"token": trajectory["token"]}}, "faults": []}
    cells.setdefault((trajectory["arm"], trajectory["task_id"]), []).append(cell)
    made[trajectory["cell"]] = trajectory


def feedback(st, cut, cells, made, *, identical=(), current=()):
    keys = list(dict.fromkeys(key for arm, key in cells))
    run_keys = step._run_keys(st, cut)
    verdict = step.train_verdict(cells, [key for key in keys if key in run_keys] + list(identical),
        [key for key in keys if key not in run_keys], set(), predicate_faults=0, routed=len(keys) + len(identical),
        sign=False, identical=list(identical))
    routed = {key: {"incumbent": [], "candidate": []} for key in set(keys) | set(identical)}
    package = SimpleNamespace(order=(), narrowed={})
    return step._feedback(st, cut, "train-r1", verdict, routed, package, package, cells, made, current=current)


def test_unfixed_feedback_is_bounded_deterministic_and_prefers_actual_failed_cells(tmp_path):
    st, cut, _ = feedback_fixture(tmp_path)
    cells, made = {}, {}
    note = "ACTUAL-SOLVER-NOTE-" + "n" * 1400
    for index, item in enumerate(cut["run"]):
        for arm, token in (("S", "fail"), ("S'", "pass" if index == 6 else "unknown" if index == 7 else "fail")):
            add_cell(cells, made, trajectory(item, arm, token, note=note))
    # Admitted generated or foreign partition identifiers can never supply next-round output examples.
    foreign = {**cut["run"][0], "task_id": "sealed-foreign"}
    for arm in ("S", "S'"):
        add_cell(cells, made, trajectory(foreign, arm, "fail", note="SEALEDPRIVATE-SENTINEL"))
    result = feedback(st, cut, cells, made)
    examples = result["unfixed_examples"]
    assert len(examples) == 4 and all(row["token"] == "fail" and row["source"] == "candidate" for row in examples)
    assert len({row["task_id"] for row in examples}) == 4
    for row in examples:
        item = next(item for item in cut["run"] if rounds.key(z.BENCH, item["task_id"]) == row["task_id"])
        assert row["notes"] == note[:1000]
        assert row["answer"] == made[row["cell"]]["replies"][-1][:500]
        assert row["reference"] == engineer_payload.reference_excerpt(item["private"]["answer"])
        assert len(row["reference"]) == 1000
    assert all(name + "PRIVATE-SENTINEL" not in json.dumps(examples) for name in ("ACCEPT", "SMOKE", "SPARE", "SEALED"))
    reversed_cut = {**cut, "run": list(reversed(cut["run"]))}
    assert feedback(st, reversed_cut, dict(reversed(list(cells.items()))), dict(reversed(list(made.items())))) == result


def test_t2_identical_requests_show_labelled_current_output_and_no_notes(tmp_path):
    st, cut, _ = feedback_fixture(tmp_path, count=2)
    current = [trajectory(item, "S", "fail") for item in cut["run"]]
    keys = [entry["task_id"] for entry in current]
    result = feedback(st, cut, {}, {}, identical=keys, current=current)
    assert result["identical_items"] == sorted(keys)
    assert len(result["unfixed_examples"]) == 2
    assert all(row["notes"] == "no notes" and row["source"] == "identical_current"
               for row in result["unfixed_examples"])
    assert {row["cell"] for row in result["unfixed_examples"]} == {entry["cell"] for entry in current}


def test_actual_candidate_failures_take_priority_over_identical_current_failures(tmp_path):
    st, cut, _ = feedback_fixture(tmp_path)
    cells, made = {}, {}
    for item in cut["run"][:3]:
        for arm in ("S", "S'"):
            add_cell(cells, made, trajectory(item, arm, "fail"))
    current = [trajectory(item, "S", "fail") for item in cut["run"][3:]]
    value = feedback(st, cut, cells, made, identical=[entry["task_id"] for entry in current], current=current)
    assert [row["source"] for row in value["unfixed_examples"]] == ["candidate"] * 3 + ["identical_current"]


def test_feedback_references_require_registered_consumed_run_items(tmp_path):
    st, cut, entries = feedback_fixture(tmp_path, count=1)
    current = [trajectory(cut["run"][0], "S", "fail")]
    entries[cut["run"][0]["task_id"]]["purpose"] = "accept"
    with pytest.raises(ValueError, match="consumed run items"):
        feedback(st, cut, {}, {}, identical=[current[0]["task_id"]], current=current)


@pytest.mark.parametrize("configuration", (p.MAIN_V2_3, p.ZEBRA_PC_V1))
def test_older_feedback_has_no_v24_output_fields(tmp_path, configuration):
    st, cut, _ = feedback_fixture(tmp_path, configuration=configuration, count=1)
    cells, made = {}, {}
    for arm in ("S", "S'"):
        add_cell(cells, made, trajectory(cut["run"][0], arm, "fail"))
    value = feedback(st, cut, cells, made)
    assert "unfixed_examples" not in value and "identical_items" not in value


def test_actual_training_payload_shows_failed_run_outputs_and_resumes_without_calls(tmp_path, monkeypatch):
    from skillopt.execskill import engineer, examiner
    from skillopt.execskill.package import FIXTURE, empty
    from tests.execskill_fakes import engineer_reply
    from tests import test_execskill_zpc_pipeline as fixture
    from tests.test_execskill_zpc_reference_isolation import GENERIC, private_pool

    setting, services, fake_solver, glm = fixture.build(tmp_path, monkeypatch)
    setting = replace(setting, extra={**setting.extra, "configuration": p.ZEBRA_PC_V2})
    cut, sentinels = private_pool(setting.pools[z.BENCH])
    by_question = {item["public"]["question"]: item for item in setting.pools[z.BENCH]}
    def answer(system, user):
        view = z.parse_user(user)
        grid = copy.deepcopy(by_question[view["question"]]["private"]["answer"])
        grid["House 1"][view["columns"][0]] = "wrong authored response"
        return json.dumps({"reasoning": "Scripted fixture failure.", "solution": grid})
    def role(system, payload):
        if system == examiner.DETECTOR_SYSTEM:
            return engineer_reply({"detectors": []}, [])
        if system == engineer.ANALYST_SYSTEM:
            return engineer_reply({"findings": []}, [])
        if system == engineer.ENGINEER_SYSTEM_ZPC_V24:
            if payload["request"] == "fix" or payload["round"] == 1:
                return engineer_reply({"changes": [{"kind": "new", "description": "Checks the public clues.",
                    "hooks": ["applies", "before_call"], "max_note_chars": 4000,
                    "excluded_benches": list(p.BENCHES)}]}, [GENERIC])
            return engineer_reply({"changes": []}, [])
        return {"verdict": "no", "reason": "A generic public method."}
    fake_solver.rules, glm.replies = [(None, answer)], role
    parent = empty(step="D/s0", evidence=FIXTURE)
    result = step.run_step(setting, "D", z.BENCH, 1, parent, services=services)
    assert result.record["decision"] == "not_run"
    records = result.record["training"]["rounds"]
    assert len(records) == 6 and [r["patience_counted"] for r in records] == [True] + [False] * 5
    proposals = [payload for system, payload in glm.seen
                 if system == engineer.ENGINEER_SYSTEM_ZPC_V24 and payload["request"] == "propose"]
    assert [request["round"] for request in proposals] == list(range(1, 7))
    examples = proposals[1]["training"]["unfixed_examples"]
    assert len(examples) == 4
    run_keys = {rounds.key(z.BENCH, item["task_id"]) for item in cut["run"]}
    assert all(row["task_id"] in run_keys and row["token"] == "fail" and row["source"] == "candidate"
               and "Check all public clues" in row["notes"] and row["answer"] and "RUNPRIVATE" in row["reference"]
               for row in examples)
    assert all(value not in json.dumps(glm.seen) for partition, values in sentinels.items() if partition != "run"
               for value in values)
    counts = len(fake_solver.requests), len(glm.seen)
    resumed = step.run_step(setting, "D", z.BENCH, 1, parent, services=services)
    assert resumed.record == result.record and (len(fake_solver.requests), len(glm.seen)) == counts


def test_interrupted_training_rebuilds_candidate_patience_without_repeating_calls(tmp_path, monkeypatch):
    """Resume unfinished training from durable units, before the completed-step shortcut can apply."""
    from skillopt.execskill import engineer
    from skillopt.execskill.package import FIXTURE, empty
    from tests.execskill_fakes import engineer_reply
    from tests import test_execskill_zpc_pipeline as fixture
    from tests.test_execskill_zpc_reference_isolation import GENERIC

    setting, services, fake_solver, glm = fixture.build(tmp_path, monkeypatch, effect="no_gain")
    setting = replace(setting, extra={**setting.extra, "configuration": p.ZEBRA_PC_V2})
    other_roles = glm.replies

    def role(system, payload):
        if system != engineer.ENGINEER_SYSTEM_ZPC_V24:
            return other_roles(system, payload)
        assert payload["request"] == "propose", payload.get("failed")
        assert payload["round"] <= 4, "Two unsuccessful candidates must exhaust patience at round 4"
        if payload["round"] in (1, 4):
            source = GENERIC if payload["round"] == 1 else GENERIC.replace("Check all", "Review all")
            return engineer_reply({"changes": [{"kind": "new", "description": "Checks the public clues.",
                "hooks": ["applies", "before_call"], "max_note_chars": 4000,
                "excluded_benches": list(p.BENCHES)}]}, [source])
        return engineer_reply({"changes": []}, [])

    glm.replies = role
    parent = empty(step="D/s0", evidence=FIXTURE)
    root = setting.root / "D" / "s1-zebralogic"
    real_unit = step._Step.unit
    resuming, replayed, new_units = False, [], []

    class InterruptedBetweenRounds(RuntimeError):
        pass

    def interrupt_then_observe(st, name, work, **kwargs):
        if not resuming and name == "engineer-r3":
            raise InterruptedBetweenRounds("rounds 1 and 2 are durable; round 3 has not started")
        completed = (st.root / name / "unit.json").exists()
        before = len(fake_solver.requests), len(glm.seen)
        result = real_unit(st, name, work, **kwargs)
        if resuming:
            if completed:
                # Check each recovered unit separately: later new rounds legitimately make new calls.
                assert (len(fake_solver.requests), len(glm.seen)) == before, name
                replayed.append(name)
            else:
                new_units.append(name)
        return result

    monkeypatch.setattr(step._Step, "unit", interrupt_then_observe)
    with pytest.raises(InterruptedBetweenRounds, match="rounds 1 and 2 are durable"):
        step.run_step(setting, "D", z.BENCH, 1, parent, services=services)
    completed_units = ["run", "diagnose", "generate", "engineer-r1", "train-r1", "engineer-r2"]
    assert not (root / step.STEP_FILE).exists() and not (root / "engineer-r3").exists()
    assert fixture.result(root, "engineer-r1")["candidate_sha256"] is not None
    assert fixture.result(root, "train-r1")["adopted"] is False
    assert fixture.result(root, "train-r1")["cells"] == 120
    assert fixture.result(root, "engineer-r2")["candidate_sha256"] is None
    assert not (root / "train-r2").exists()
    durable = {}
    for name in completed_units:
        for relative in ("unit.json", "attempt-1/started.json", "role-calls.jsonl"):
            path = root / name / relative
            if relative != "role-calls.jsonl" or path.exists():
                durable[path] = path.read_bytes()

    resuming = True
    result = step.run_step(setting, "D", z.BENCH, 1, parent, services=services)
    assert replayed == completed_units
    assert new_units == ["engineer-r3", "engineer-r4", "train-r4", "freeze"]
    assert all(path.read_bytes() == contents for path, contents in durable.items())
    assert all(not (root / name / "attempt-2").exists() for name in completed_units)
    assert (root / step.STEP_FILE).exists()
    assert result.record["decision"] == "not_run" and result.record["reason"] == "no_training_gain"
    records = result.record["training"]["rounds"]
    assert [row["round"] for row in records] == [1, 2, 3, 4]
    assert [row["patience_counted"] for row in records] == [True, False, False, True]
    assert sum(row["patience_counted"] for row in records) == p.TRAIN_PATIENCE == 2
    assert not any(row["adopted"] for row in records)
    assert not (root / "engineer-r5").exists()
    proposals = [payload for system, payload in glm.seen if system == engineer.ENGINEER_SYSTEM_ZPC_V24]
    assert [payload["round"] for payload in proposals] == [1, 2, 3, 4]
    assert [row["patience_counted"] for row in proposals[2]["history"]] == [True, False]
    assert [row["patience_counted"] for row in proposals[3]["history"]] == [True, False, False]
