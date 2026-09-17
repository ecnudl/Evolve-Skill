"""Closed end-to-end V14 synthetic API runs; generated Coding never executes."""

import json
from copy import deepcopy
from pathlib import Path
from threading import Lock

import pytest

from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v9 import study as transport
from skillopt.coevolution_v14 import learning, runtime, tasks
from skillopt.coevolution_v14 import study as s
from skillopt.validator_pilot.api import digest
from tests.test_coevolution_v12_study import forbidden, put, tree


def common_rule(reference):
    return {"id": "check", "mechanism": "verification", "when": "When stated by the task.",
        "procedure": "Verify the applicable constraints.", "avoid": "Do not invent unstated obligations.",
        "claim_type": "task_requirement", "evidence_refs": [reference]}


class FakeAPI:
    model = "glm-5.3"
    service = {"offline_fixture": True, "max_retries": 2}

    def __init__(self, root, maximum, state):
        self.root, self.state = Path(root), state
        put(self.root / "service.json", self.service)
        put(self.root / "budget_protocol.json", {"max_logical_calls": maximum, "model": self.model,
            "workers": 4, "service_sha256": digest(self.service)})

    def call(self, system, user, kind, key, max_tokens=4096, repeat=0):
        with self.state["lock"]:
            request = {"model": self.model, "service": self.service, "system": system, "user": user,
                       "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
            identifier = digest(request)
            path = self.root / "calls" / (identifier + ".json")
            if path.exists():
                return json.loads(path.read_text())
            self.state["calls"] += 1
            value = json.loads(user)
            if kind == "v14_skill_update":
                if "support_registry" in value:
                    ref = next(h for h, row in value["support_registry"].items() if row["claim_type"] == "task_requirement")
                    response = json.dumps({"operations": [{"op": "upsert", **common_rule(ref)}]})
                else:
                    response = learning.render([common_rule("unused-not-rendered")])
                    if not self.state.get("same_skill"):
                        response += "\n" + key
                if self.state.get("invalid_skill"):
                    response = "Invalid updater output"
            else:
                public = value["task"]
                if value["stage"] == "revision":
                    response = json.dumps({"action": "keep"})
                    if self.state.get("bad_revision"):
                        response = "Invalid revision"
                elif "files" in public:
                    path_name = public["editable_paths"][0]
                    content = public["files"][path_name] + ("\n# improved\n" if value["skill"] else "\n")
                    response = f"<<<FILE {path_name}>>>\n{content}<<<END FILE>>>"
                elif public["domain"] == "spreadsheet":
                    response = json.dumps({"formulas": {k: public["formulas"][k] for k in public["editable_cells"]}})
                else:
                    response = json.dumps({"rules": public["rules"]})
            ok = not self.state.get("fail_all")
            receipt = {"request": request, "request_hash": identifier, "ok": ok,
                "response": response if ok else "", "http_attempt_count": 1, "finish_reason": "stop" if ok else None,
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2} if ok else {}}
            put(self.root / "budget_reservations" / (identifier + ".json"), {"request_hash": identifier, "kind": kind})
            put(path, receipt)
            self.state["receipts"].append(receipt)
            if kind == "v14_skill_update" and self.state.get("source_drift"):
                self.state["source_hash"] = "b" * 64
            if self.state.get("pause_at") and self.state["calls"] >= self.state["pause_at"] and not self.state.get("paused"):
                (self.root.parent / "PAUSE").touch()
                self.state["paused"] = True
            if self.state.get("receipt_mismatch") and kind == "v14_skill_update":
                return {**receipt, "response": "not the durable response"}
            return receipt

    def close(self):
        self.state["closed"] += 1


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root = tmp_path / "outputs/coevolution_v14/test"
    state = {"calls": 0, "executions": 0, "receipts": [], "source_hash": "a" * 64, "closed": 0, "lock": Lock()}
    monkeypatch.setattr(s, "source_hashes", lambda repo: {"fixture": state["source_hash"]})
    monkeypatch.setattr(transport, "audit_pacing", lambda *args: {"offline_fixture": True})
    actual = runtime.legacy.evaluate

    def evaluate(adapter, artifact, *, public_only):
        state["executions"] += 1
        if not isinstance(adapter, CodingAdapter) or artifact is None:
            return actual(adapter, artifact, public_only=public_only)
        passed = any("# improved" in source for source in artifact.values())
        cases = adapter.task.public_cases + ([] if public_only else adapter.task.private_cases)
        observations = [{"label": case["label"], "input": case["input"], "passed": passed,
            "actual": case["expected"] if passed else {}, "exception": None, "input_unchanged": True} for case in cases]
        checks = [{"id": case["label"] + ":" + suffix, "passed": passed if suffix == "behavior" else True}
                  for case in cases for suffix in ("behavior", "input_unchanged")]
        return {"files": artifact, "hard": passed, "execution_ok": True, "public_pass": passed,
            "case_results": checks, "passed_tests": sum(c["passed"] for c in checks), "total_tests": len(checks),
            "public_observations": [o for o, c in zip(observations, cases) if c["public"]],
            "private_diagnostics": [{**o, "expected": c["expected"]} for o, c in zip(observations, cases) if not c["public"] and not passed]}

    monkeypatch.setattr(runtime.legacy, "evaluate", evaluate)

    def factory(repo, api_root, *, max_calls, workers):
        assert repo == tmp_path and workers == 4
        return FakeAPI(api_root, max_calls, state)

    def build(design="smoke", panel=None):
        return s.Study(tmp_path, root, design=design,
                       panel=panel or tasks.build_panel(smoke=design == "smoke"), api_factory=factory)

    return root, state, build


def test_smoke_complete_two_updaters_three_final_conditions_and_probe_closure(fixture):
    root, state, build = fixture
    result = build().run()
    assert result["complete"] and result["learning"]["proposals"] == result["learning"]["valid"] == 2
    assert result["learning"]["text_changes"] == 2 and result["learning"]["local_operations"] == 1
    assert result["learning"]["probe_native_evaluations"] == 2
    assert result["evidence_closure"]["all_intents_closed"]
    assert result["ledger"]["cached_logical_calls"] == state["calls"] <= 64
    grid = s.read(root / "final_rows.json")["rows"]
    assert len(grid) == 6 and {row["policy"] for row in grid} == set(s.POLICIES)
    assert all(row["chosen_stage"] == "revision" for row in grid)
    assert not (root / "selection").exists()


def test_learner_sees_only_development_and_control_receives_no_probes(fixture):
    root, state, build = fixture
    study = build()
    study.run()
    final = {s.payload(a)["id"] for a in study.panel["final"]}
    for receipt in state["receipts"]:
        request, body = receipt["request"], json.loads(receipt["request"]["user"])
        if request["kind"] != "v14_skill_update":
            assert "hidden_cases" not in request["user"] and "private_cases" not in request["user"]
            assert "reference_files" not in request["user"]
            continue
        assert all(identifier not in request["user"] for identifier in final)
        assert all(row["feedback"]["phase"] == "development" for row in body["individual_trajectory_records"])
        if request["key"].endswith("independent"):
            assert "constraint_probe_records" not in body and "support_registry" not in body
        else:
            assert len(body["constraint_probe_records"]) == 4
            for probe in body["constraint_probe_records"]:
                assert probe["phase"] == "development" and probe["source_task_id"] not in final
                assert len(probe["case_obligations"]) == 4
    assert len(list((root / "runtime/probes/solves").glob("*.json"))) == 2


def test_completed_replay_zero_api_zero_execution_zero_bytes_changed(fixture, monkeypatch):
    root, state, build = fixture
    expected = build().run()
    before, counts = tree(root), (state["calls"], state["executions"])
    monkeypatch.setattr(runtime.legacy, "evaluate", forbidden)
    monkeypatch.setattr(FakeAPI, "call", forbidden)
    replay = build()
    replay.api_factory = forbidden
    assert replay.run() == expected
    assert tree(root) == before and (state["calls"], state["executions"]) == counts


def test_same_text_aliases_within_history_but_not_distinct_policies_as_new_samples(fixture):
    root, state, build = fixture
    state["same_skill"] = True
    result = build().run()
    rows = s.read(root / "final_rows.json")["rows"]
    for task in {r["task_id"] for r in rows}:
        learned = [r for r in rows if r["task_id"] == task and r["policy"] != "no_skill"]
        assert learned[0]["request_hashes"] == learned[1]["request_hashes"]
    assert result["learning"]["proposals"] == 2


def test_three_formal_histories_have_fresh_base_requests(fixture):
    root, state, build = fixture
    state["same_skill"] = True
    result = build("formal").run()
    assert result["learning"]["proposals"] == 12 and result["ledger"]["cached_logical_calls"] <= 640
    rows = s.read(root / "final_rows.json")["rows"]
    base = [r for r in rows if r["policy"] == "no_skill"]
    assert len(base) == 72 and len({tuple(r["request_hashes"]) for r in base}) == 72
    for task in {r["task_id"] for r in base}:
        assert len({tuple(r["request_hashes"]) for r in base if r["task_id"] == task}) == 3
    assert result["summary"]["no_skill_sampling"]["unique_trajectory_receipts"] == 72
    optimizer = [r for r in state["receipts"] if r["request"]["kind"] == "v14_skill_update"]
    assert max(len(r["request"]["user"]) for r in optimizer) < 300000
    assert all(len(s.read(p)["skill"]) <= learning.MAX_SKILL_CHARS for p in (root / "learning").glob("*.json"))


def test_invalid_updaters_retain_empty_skill_without_dropping_final_positions(fixture):
    root, state, build = fixture
    state["invalid_skill"] = True
    result = build().run()
    assert result["learning"]["valid"] == result["learning"]["text_changes"] == 0
    rows = s.read(root / "final_rows.json")["rows"]
    assert len(rows) == 6
    for task in {r["task_id"] for r in rows}:
        assert len({tuple(r["request_hashes"]) for r in rows if r["task_id"] == task}) == 1


def test_common_delivery_guard_is_used_by_all_conditions(fixture):
    root, state, build = fixture
    state["bad_revision"] = True
    build().run()
    rows = s.read(root / "final_rows.json")["rows"]
    assert all(r["chosen_stage"] == "generation" and r["rollback_reason"] == "revision_delivery_invalid" for r in rows)


def test_pause_drains_admitted_trajectories_and_resume_keeps_receipts(fixture):
    root, state, build = fixture
    state["pause_at"] = 1
    with pytest.raises(s.PauseRequested):
        build().run()
    assert 2 <= state["calls"] <= 4
    receipts = {p.name: p.read_bytes() for p in (root / "api/calls").glob("*.json")}
    assert len(list((root / "runtime/request_intents").glob("*.json"))) == len(receipts)
    assert len(list((root / "runtime/stages").glob("*.json"))) == len(receipts)
    assert not (root / "results.json").exists()
    (root / "PAUSE").unlink()
    assert build().run()["complete"]
    assert all((root / "api/calls" / name).read_bytes() == value for name, value in receipts.items())


def test_source_drift_at_update_prevents_final(fixture):
    root, state, build = fixture
    state["source_drift"] = True
    with pytest.raises(ValueError, match="source"):
        build().run()
    assert not (root / "final_frozen.json").exists() and not (root / "results.json").exists()


def test_optimizer_return_must_equal_its_durable_receipt(fixture):
    root, state, build = fixture
    state["receipt_mismatch"] = True
    with pytest.raises(ValueError, match="durable"):
        build().run()
    assert not (root / "final_frozen.json").exists()


@pytest.mark.parametrize("missing", ["protocol.json", "private_panel.json", "final_frozen.json", "final_rows.json"])
def test_missing_completed_metadata_cannot_be_reconstructed(fixture, missing):
    root, state, build = fixture
    build().run()
    (root / missing).unlink()
    before, calls = tree(root), state["calls"]
    with pytest.raises((ValueError, FileNotFoundError)):
        build().run()
    assert tree(root) == before and state["calls"] == calls


@pytest.mark.parametrize("directory", ["request_intents", "execution_intents", "executions", "probes/execution_intents", "probes/executions", "probes/solves"])
def test_orphan_evidence_rejected_at_completed_closure(fixture, directory):
    root, _, build = fixture
    build().run()
    put(root / "runtime" / directory / ("f" * 64 + ".json"), {"orphan": True})
    before = tree(root)
    with pytest.raises(ValueError, match="runtime evidence"):
        build().run()
    assert tree(root) == before


def test_missing_probe_execution_stops_without_reexecution(fixture, monkeypatch):
    root, state, build = fixture
    build().run()
    next((root / "runtime/probes/executions").glob("*.json")).unlink()
    counts = state["calls"], state["executions"]
    monkeypatch.setattr(runtime.legacy, "evaluate", forbidden)
    with pytest.raises(ValueError, match="execution"):
        build().run()
    assert counts == (state["calls"], state["executions"])


def test_no_final_sample_before_every_skill_is_frozen(fixture):
    root, state, build = fixture
    build().run()
    kinds = [r["request"]["kind"] for r in state["receipts"]]
    last_update = max(i for i, k in enumerate(kinds) if k == "v14_skill_update")
    first_final = min(i for i, r in enumerate(state["receipts"]) if r["request"]["kind"].startswith("v14_solve_")
                      and json.loads(r["request"]["user"])["task"]["id"].find("final") >= 0)
    assert last_update < first_final and s.read(root / "final_frozen.json")["third_domain_used_in_learning"] is False


def test_source_drift_after_last_update_is_caught_before_freeze(fixture, monkeypatch):
    root, state, build = fixture
    actual = s.Study._event
    def event(study, stage, **details):
        actual(study, stage, **details)
        if stage == "skill_updated" and details.get("arm") == "constrained":
            state["source_hash"] = "b" * 64
    monkeypatch.setattr(s.Study, "_event", event)
    with pytest.raises(ValueError, match="source"):
        build().run()
    assert not (root / "final_frozen.json").exists()


def preflight(panel):
    controls = {"reference": {"passed": True, "available": True},
        "starter": {"passed": False, "available": True}, "semantic_mutant": {"passed": False, "available": True},
        "preservation_mutant": {"passed": False, "available": False}}
    records = [{"task_id": s.payload(a)["id"], "domain": a.domain, "task_hash": digest(s.payload(a)),
                "controls": deepcopy(controls)} for group in panel["train"] + [panel["final"]] for a in group]
    probes = []
    for group in panel["train"]:
        for adapter in group:
            task = s.payload(adapter)
            probes.append({"task_id": task["id"], "probe_task_hash": digest(s.payload(tasks.probe_adapter(adapter))),
                "reference_passed": True, "ordinary_inputs_disjoint": True,
                "checks": [{"obligation_id": p["obligation_id"], "probe_id": p["id"], "detected": True,
                            "mutant_hash": digest(p["mutant"])} for p in task["metadata"]["counterexample_probe_pool"]]})
    return {"version": "synthetic-test-preflight", "all_checked": True, "coding_checked": True,
            "model_api_calls": 0, "records": records, "probe_records": probes}


def test_production_preflight_is_bound_and_complete_replay_never_reexecutes(fixture, monkeypatch):
    root, _, build = fixture
    calls = []
    def calibrate(panel, *, coding):
        assert coding is True
        calls.append(1)
        return preflight(panel)
    monkeypatch.setattr(tasks, "self_check", calibrate)
    study = build()
    study.production_panel = True
    result = study.run()
    saved = s.read(root / "task_preflight.json")
    assert s.read(root / "protocol.json")["task_preflight_hash"] == saved["record_hash"]
    assert calls == [1]
    before = tree(root)
    monkeypatch.setattr(tasks, "self_check", forbidden)
    replay = build()
    replay.production_panel = True
    assert replay.run() == result and tree(root) == before


@pytest.mark.parametrize("defect", ["reference_fail", "probe_reference_fail", "duplicate_probe", "mutant_hash", "task_hash"])
def test_production_refuses_bad_preflight_before_any_api(fixture, monkeypatch, defect):
    _, state, build = fixture
    def calibrate(panel, *, coding):
        result = preflight(panel)
        if defect == "reference_fail":
            result["records"][0]["controls"]["reference"]["passed"] = False
        elif defect == "probe_reference_fail":
            result["probe_records"][0]["reference_passed"] = False
        elif defect == "duplicate_probe":
            result["probe_records"][0]["checks"][1] = deepcopy(result["probe_records"][0]["checks"][0])
        elif defect == "mutant_hash":
            result["probe_records"][0]["checks"][0]["mutant_hash"] = "b" * 64
        else:
            result["records"][0]["task_hash"] = "b" * 64
        return result
    monkeypatch.setattr(tasks, "self_check", calibrate)
    study = build()
    study.production_panel = True
    with pytest.raises(ValueError, match="calibration"):
        study.run()
    assert state["calls"] == 0


def test_completed_missing_production_preflight_never_reconstructs(fixture, monkeypatch):
    root, state, build = fixture
    monkeypatch.setattr(tasks, "self_check", lambda panel, **kwargs: preflight(panel))
    study = build()
    study.production_panel = True
    study.run()
    (root / "task_preflight.json").unlink()
    counts = state["calls"], state["executions"]
    monkeypatch.setattr(tasks, "self_check", forbidden)
    replay = build()
    replay.production_panel = True
    with pytest.raises(ValueError, match="preflight"):
        replay.run()
    assert counts == (state["calls"], state["executions"])


def test_probe_support_join_retains_exact_obligation_and_case_definition(fixture):
    _, state, build = fixture
    build().run()
    receipt = next(r for r in state["receipts"] if r["request"]["kind"] == "v14_skill_update"
                   and r["request"]["key"].endswith("constrained"))
    body = json.loads(receipt["request"]["user"])
    supported = [row for row in body["support_registry"].values() if "probe_hash" in row]
    assert supported
    for row in supported:
        case = row["probe_definition"]
        case_id = case.get("id", case.get("label"))
        assert row["observation"]["id"] in {case_id, case_id + ":behavior", case_id + ":input_unchanged"}
        assert case["obligation_id"] == row["obligation"]["id"]
        assert row["role"] in {"current", "no_skill"}
    # These links are observable provenance, NOT proof that input preservation
    # implies the linked unit/boundary obligation's behavioral correctness.
