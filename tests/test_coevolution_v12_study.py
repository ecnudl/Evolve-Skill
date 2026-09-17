"""Offline full V12 learning/selection/freeze/replay on synthetic tasks only."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v6.native import NativeAdapter
from skillopt.coevolution_v9 import study as transport
from skillopt.coevolution_v12 import runtime
from skillopt.coevolution_v12 import study as s
from skillopt.validator_pilot.api import digest


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def tree(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def forbidden(*args, **kwargs):
    pytest.fail("Completed replay must not call API, execute, or reconstruct evidence")


def task(domain, split, identifier, cluster):
    common = {"split": split, "contract": {"change_scope": "partial_update",
        "preserve_obligations": ["Preserve unrelated cases."], "supersedes_old_policy": False},
        "prompt": "Implement the explicitly requested behavior.", "cluster_id": cluster,
        "id": identifier, "domain": domain}
    if domain == "coding":
        files = {"api.py": 'from helper import compute\ndef solve(data): return {"answer":compute(data["x"])}',
                 "helper.py": "def compute(x): return 0"}
        def case(label, public):
            return {"label": label, "input": {"x": 1 if public else 7}, "expected": {"answer": 2 if public else 8},
                "exception": None, "dimension": "requested_behavior", "public": public}
        return CodingAdapter(RepoTask(id=identifier, split=split, family=cluster, cluster_id=cluster,
            prompt=common["prompt"], files=files, reference_files=files, editable_paths=list(files),
            input_domain={"type": "object"}, public_cases=[case("PUBLIC", True)],
            private_cases=[case("PRIVATE_" + identifier, False)], metadata={"contract": common["contract"]}))
    if domain == "spreadsheet":
        return NativeAdapter({**common, "inputs": {"A1": 7}, "formulas": {"B1": "=A1"}, "editable_cells": ["B1"],
            "public_cases": [{"id": "PUBLIC", "overrides": {}, "expected": {"B1": 9}}],
            "hidden_cases": [{"id": "PRIVATE_" + identifier, "overrides": {"A1": 113}, "expected": {"B1": 115}}]})
    return NativeAdapter({**common, "rules": [{"id": "r", "if": ["ready"], "then": "done"}],
        "editable_rule_ids": ["r"], "vocabulary": ["ready", "done", "blocked"], "answer_facts": ["done"],
        "public_cases": [{"id": "PUBLIC", "facts": ["ready"], "expected": ["done"]}],
        "hidden_cases": [{"id": "PRIVATE_" + identifier, "facts": ["ready"], "expected": ["done"]}]})


def panel():
    result = {"train": [], "selection": [], "final": []}
    for split, key in (("development", "train"), ("selection", "selection")):
        for round_index in range(3):
            result[key].append([task(domain, split, f"{key}-{round_index}-{i}", f"{key}-family-{round_index}-{i}")
                for i, domain in enumerate(("coding", "spreadsheet", "coding", "spreadsheet"))])
    for domain in ("coding", "spreadsheet", "rule_reasoning"):
        for family in range(4):
            for variant in range(3):
                result["final"].append(task(domain, "final", f"final-{domain}-{family}-{variant}",
                                            f"final-{domain}-family-{family}"))
    return result


class FakeAPI:
    model = "glm-5.3"
    service = {"offline_fixture": True, "max_retries": 2}

    def __init__(self, root, maximum, state):
        self.root, self.state = Path(root), state
        put(self.root / "service.json", self.service)
        put(self.root / "budget_protocol.json", {"max_logical_calls": maximum, "model": self.model,
            "workers": 4, "service_sha256": digest(self.service)})

    def call(self, system, user, kind, key, max_tokens=4096, repeat=0):
        request = {"model": self.model, "service": self.service, "system": system, "user": user,
            "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
        identifier = digest(request)
        path = self.root / "calls" / (identifier + ".json")
        if path.exists():
            return json.loads(path.read_text())
        self.state["calls"] += 1
        payload = json.loads(user)
        if kind == "v12_skill_update":
            label = "common" if self.state.get("same_skill") else key
            response = "## When\nUse on appropriate tasks.\n## Procedure\nVerify constraints.\n## Avoid\nUnsupported changes.\n" + label
            if self.state.get("invalid_skill"):
                response = "Invalid optimizer output"
        else:
            public = payload["task"]
            improved = bool(payload["skill"])
            if "files" in public:
                response = "<<<FILE helper.py>>>\ndef compute(x): return " + ("x+1" if improved else "0") + "\n<<<END FILE>>>"
            elif public["domain"] == "spreadsheet":
                response = json.dumps({"formulas": {"B1": "=A1+2" if improved else "=A1"}})
            else:
                rules = deepcopy(public["rules"])
                if not improved:
                    rules[0]["if"] = ["blocked"]
                response = json.dumps({"rules": rules})
        ok = not self.state.get("fail_all")
        receipt = {"request": request, "request_hash": identifier, "ok": ok,
            "response": response if ok else "", "http_attempt_count": 1,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2} if ok else {},
            "finish_reason": "stop"}
        put(self.root / "budget_reservations" / (identifier + ".json"), {"request_hash": identifier, "kind": kind})
        put(path, receipt)
        self.state["receipts"].append(receipt)
        if kind == "v12_skill_update" and self.state.get("source_drift"):
            self.state["source_hash"] = "b" * 64
        if (self.state.get("pause_at") and self.state["calls"] >= self.state["pause_at"]
                and not self.state.get("pause_marked")):
            (self.root.parent / "PAUSE_REQUESTED").touch()
            self.state["pause_marked"] = True
        return receipt

    @staticmethod
    def parallel(jobs, fn, label):
        return [fn(job) for job in jobs]

    def close(self):
        self.state["closed"] += 1


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    repo, root = tmp_path, tmp_path / "outputs/coevolution_v12/test"
    state = {"calls": 0, "executions": 0, "receipts": [], "source_hash": "a"*64, "closed": 0}
    monkeypatch.setattr(s, "source_hashes", lambda _repo: {"fixture": state["source_hash"]})
    monkeypatch.setattr(transport, "audit_pacing", lambda *args: {"offline_fixture": True})
    original = runtime.legacy.evaluate
    def evaluate(adapter, artifact, *, public_only):
        state["executions"] += 1
        if not isinstance(adapter, CodingAdapter) or artifact is None:
            return original(adapter, artifact, public_only=public_only)
        passed = "return x+1" in artifact["helper.py"]
        cases = adapter.task.public_cases + ([] if public_only else adapter.task.private_cases)
        observations = [{"label": case["label"], "input": case["input"], "passed": passed,
            "actual": case["expected"] if passed else {"answer": 0}, "exception": None,
            "input_unchanged": True} for case in cases]
        results = [{"id": case["label"] + ":" + suffix, "passed": passed if suffix == "behavior" else True}
                   for case in cases for suffix in ("behavior", "input_unchanged")]
        return {"files": artifact, "hard": passed, "execution_ok": True, "public_pass": passed,
            "case_results": results, "passed_tests": sum(row["passed"] for row in results),
            "total_tests": len(results), "public_observations": [row for row, case in zip(observations, cases) if case["public"]],
            "private_diagnostics": [{**row, "expected": case["expected"]} for row, case in zip(observations, cases)
                                    if not case["public"] and not passed]}
    monkeypatch.setattr(runtime.legacy, "evaluate", evaluate)

    def factory(_repo, api_root, *, max_calls, workers):
        assert _repo == repo and workers == 4
        return FakeAPI(api_root, max_calls, state)

    def build(design="smoke", task_panel=None):
        return s.Study(repo, root, design=design, panel=task_panel or panel(), api_factory=factory)
    return root, state, build


def test_complete_smoke_learns_twice_and_retains_raw_and_selected(fixture):
    root, state, build = fixture
    result = build().run()
    assert result["complete"] and result["learning"] == {
        "proposals": 2, "valid": 2, "text_changes": 2, "selection_acceptances": 2}
    assert result["ledger"]["cached_logical_calls"] == state["calls"] <= 96
    assert state["closed"] == 1
    assert result["summary"]["success_by_policy"]["no_skill"] == 0
    assert all(result["summary"]["success_by_policy"][p] == 1 for p in s.POLICIES if p != "no_skill")
    learned = [s.read(path) for path in (root / "learning").glob("*.json")]
    assert len({row["evidence_hash"] for row in learned}) == 1
    assert len({row["skill_hash"] for row in learned}) == 2
    grid = s.read(root / "final_rows.json")["rows"]
    for raw in ("independent", "contrastive"):
        for row in [r for r in grid if r["policy"] == raw]:
            selected = next(r for r in grid if r["task_id"] == row["task_id"] and r["policy"] == "selected_" + raw)
            assert selected["request_hashes"] == row["request_hashes"]


def test_learning_requests_contain_only_development_evidence(fixture):
    _, state, build = fixture
    build().run()
    for receipt in state["receipts"]:
        request = receipt["request"]
        if request["kind"] == "v12_skill_update":
            payload = json.loads(request["user"])
            assert {row["task_id"].split("-")[0] for row in payload["observed_records"]} == {"train"}
            assert all(task["id"].startswith("train-") for task in payload["public_tasks"])
            assert "PRIVATE_selection" not in request["user"] and "PRIVATE_final" not in request["user"]
        else:
            assert "PRIVATE_" not in request["user"] and "hidden_cases" not in request["user"]


def test_identical_generated_skill_reuses_exact_solver_requests(fixture):
    root, state, build = fixture
    state["same_skill"] = True
    result = build().run()
    grid = s.read(root / "final_rows.json")["rows"]
    for task_id in {row["task_id"] for row in grid}:
        aliases = [r for r in grid if r["task_id"] == task_id and r["policy"] != "no_skill"]
        assert len({tuple(row["request_hashes"]) for row in aliases}) == 1
    assert result["learning"]["proposals"] == 2
    assert len([r for r in state["receipts"] if r["request"]["kind"] == "v12_skill_update"]) == 2


def test_invalid_skill_keeps_empty_parent_without_omitting_final(fixture):
    root, state, build = fixture
    state["invalid_skill"] = True
    result = build().run()
    assert result["learning"]["valid"] == result["learning"]["text_changes"] == 0
    grid = s.read(root / "final_rows.json")["rows"]
    assert len({row["skill_hash"] for row in grid}) == 1
    assert len(grid) == result["summary"]["positions"]


def test_complete_replay_zero_calls_zero_execution_and_no_file_changes(fixture, monkeypatch):
    root, state, build = fixture
    expected = build().run()
    before, counts = tree(root), (state["calls"], state["executions"])
    monkeypatch.setattr(runtime.legacy, "evaluate", forbidden)
    monkeypatch.setattr(runtime, "write_immutable_json", forbidden)
    monkeypatch.setattr(s, "write_immutable_json", forbidden)
    study = build()
    study.api_factory = forbidden
    assert study.run() == expected
    assert tree(root) == before and (state["calls"], state["executions"]) == counts


@pytest.mark.parametrize("missing", ["protocol.json", "private_panel.json", "final_frozen.json", "final_rows.json"])
def test_missing_completed_stage_refused(fixture, missing):
    root, state, build = fixture
    build().run()
    (root / missing).unlink()
    before, counts = tree(root), (state["calls"], state["executions"])
    with pytest.raises((ValueError, FileNotFoundError)):
        build().run()
    assert tree(root) == before and (state["calls"], state["executions"]) == counts


@pytest.mark.parametrize("directory", ["learning", "learning_intents", "selection", "runtime/solves", "runtime/executions", "api/calls"])
def test_missing_completed_evidence_never_repaired(fixture, directory):
    root, state, build = fixture
    build().run()
    next((root / directory).glob("*.json")).unlink()
    before, counts = tree(root), (state["calls"], state["executions"])
    with pytest.raises((ValueError, FileNotFoundError)):
        build().run()
    assert tree(root) == before and (state["calls"], state["executions"]) == counts


def test_source_change_during_learning_prevents_final(fixture):
    root, state, build = fixture
    state["source_drift"] = True
    with pytest.raises(ValueError, match="[Ff]rozen|[Ss]ource|changed"):
        build().run()
    assert not (root / "final_frozen.json").exists()
    assert not (root / "results.json").exists()
    assert not any(json.loads(row["request"]["user"]).get("task", {}).get("id", "").startswith("final-")
                   for row in state["receipts"] if row["request"]["kind"] != "v12_skill_update")


@pytest.mark.parametrize("orphan", ["execution_intents", "executions"])
def test_unexpected_execution_evidence_refused_on_replay(fixture, orphan):
    root, _, build = fixture
    build().run()
    put(root / "runtime" / orphan / (("a"*64) + ".json"), seal({"unknown_admission": True}))
    before = tree(root)
    with pytest.raises(ValueError):
        build().run()
    assert tree(root) == before


def test_extra_closed_api_request_cannot_hide_outside_actual_grid(fixture):
    root, _, build = fixture
    build().run()
    row = json.loads(next((root / "api/calls").glob("*.json")).read_text())
    row["request"]["key"] = "unplanned-request"
    identifier = digest(row["request"])
    row["request_hash"] = identifier
    put(root / "api/calls" / (identifier + ".json"), row)
    put(root / "api/budget_reservations" / (identifier + ".json"),
        {"request_hash": identifier, "kind": row["request"]["kind"]})
    before = tree(root)
    with pytest.raises(ValueError):
        build().run()
    assert tree(root) == before


def test_pause_drains_current_trajectories_then_cache_resume(fixture):
    root, state, build = fixture
    state["pause_at"] = 1
    with pytest.raises(s.PauseRequested):
        build().run()
    assert state["calls"] == 4  # Two admitted trajectories, each with generation and revision.
    assert not list((root / "learning").glob("*.json"))
    cached = tree(root / "api/calls")
    (root / "PAUSE_REQUESTED").unlink()
    result = build().run()
    assert result["complete"]
    assert all((root / "api/calls" / name).read_bytes() == body for name, body in cached.items())


def test_formal_fixed_budget_has_safe_worst_case_headroom(fixture):
    _, state, build = fixture
    study = build("formal")
    protocol = study.prepare()
    assert protocol["histories"] == protocol["rounds"] == 3
    assert protocol["max_calls"] == 1536
    # Distinct text worst case: training 4+28+28 trajectories; selection
    # 28+52+52; final 36*(1+6 raw+6 selected); every trajectory uses two calls.
    worst_case = 2 * ((4 + 28 + 28) + (28 + 52 + 52) + 36 * 13) + 18
    assert worst_case == 1338 <= study.max_calls <= 1600
    assert state["calls"] == state["executions"] == 0


def test_heldout_domain_cannot_enter_train(fixture):
    _, state, build = fixture
    value = panel()
    value["train"][0][0] = task("rule_reasoning", "development", "heldout-leak", "leak-family")
    with pytest.raises(ValueError, match="Held-out"):
        build(task_panel=value).prepare()
    assert state["calls"] == 0


def test_final_family_overlap_rejected(fixture):
    _, _, build = fixture
    value = panel()
    value["final"][0] = CodingAdapter(replace(value["final"][0].task,
        cluster_id=value["train"][0][0].task.cluster_id))
    with pytest.raises(ValueError, match="families overlap"):
        build("formal", value).prepare()


@pytest.fixture
def production(fixture, monkeypatch):
    from skillopt.coevolution_v12 import tasks

    root, state, injected = fixture
    state["preflights"] = 0
    monkeypatch.setattr(tasks, "build_panel", lambda *, smoke: panel())

    def preflight(actual_panel, *, coding):
        assert coding is True
        state["preflights"] += 1
        adapters = [a for key in ("train", "selection") for group in actual_panel[key] for a in group]
        adapters += actual_panel["final"]
        controls = {name: {"passed": name == "reference", "available": True}
                    for name in ("reference", "starter", "semantic_mutant", "preservation_mutant")}
        return {"all_checked": True, "coding_checked": True, "model_api_calls": 0,
            "checked_tasks": len(adapters), "records": [{"task_id": s.payload(a)["id"],
                "task_hash": digest(s.payload(a)), "controls": deepcopy(controls)} for a in adapters]}

    monkeypatch.setattr(tasks, "self_check", preflight)
    def build():
        fixture_study = injected()
        return s.Study(fixture_study.repo, root, design="smoke", api_factory=fixture_study.api_factory)
    return root, state, build


def test_production_preflight_is_persisted_bound_and_not_reexecuted(production, monkeypatch):
    from skillopt.coevolution_v12 import tasks

    root, state, build = production
    expected = build().run()
    preflight = s.read(root / "task_preflight.json")
    protocol = s.read(root / "protocol.json")
    assert state["preflights"] == 1 and preflight["checked_tasks"] == 6
    assert protocol["task_preflight_hash"] == preflight["record_hash"]
    assert protocol["injected_test_panel"] is False
    before, counts = tree(root), (state["calls"], state["executions"])
    monkeypatch.setattr(tasks, "self_check", forbidden)
    monkeypatch.setattr(runtime.legacy, "evaluate", forbidden)
    assert build().run() == expected
    assert before == tree(root) and counts == (state["calls"], state["executions"])


def test_completed_production_missing_preflight_is_not_rebuilt(production, monkeypatch):
    from skillopt.coevolution_v12 import tasks

    root, state, build = production
    build().run()
    (root / "task_preflight.json").unlink()
    before = tree(root)
    monkeypatch.setattr(tasks, "self_check", forbidden)
    with pytest.raises(ValueError, match="missing task calibration"):
        build().run()
    assert before == tree(root) and state["preflights"] == 1


@pytest.mark.parametrize("change", ["task_hash", "reference", "starter", "semantic_mutant", "api_calls"])
def test_production_resealed_bad_calibration_is_rejected(production, change):
    root, _, build = production
    build().run()
    path = root / "task_preflight.json"
    value = s.read(path)
    value.pop("record_hash")
    if change == "task_hash":
        value["records"][0]["task_hash"] = "f"*64
    elif change == "api_calls":
        value["model_api_calls"] = 1
    else:
        value["records"][0]["controls"][change]["passed"] = change != "reference"
    put(path, seal(value))
    before = tree(root)
    with pytest.raises(ValueError, match="calibration"):
        build().run()
    assert before == tree(root)


def test_changed_production_task_bytes_reject_before_new_calibration(production, monkeypatch):
    from skillopt.coevolution_v12 import tasks

    root, state, build = production
    build().run()
    def changed(*, smoke):
        value = panel()
        value["train"][0][0] = CodingAdapter(replace(value["train"][0][0].task, prompt="Changed task contract"))
        return value
    monkeypatch.setattr(tasks, "build_panel", changed)
    monkeypatch.setattr(tasks, "self_check", forbidden)
    before = tree(root)
    with pytest.raises(ValueError, match="Frozen study"):
        build().run()
    assert before == tree(root) and state["preflights"] == 1


def test_optimizer_response_must_equal_actual_durable_receipt(fixture, monkeypatch):
    root, _, build = fixture
    original = FakeAPI.call
    def changed(self, *args, **kwargs):
        receipt = original(self, *args, **kwargs)
        if receipt["request"]["kind"] == "v12_skill_update":
            return {**receipt, "response": receipt["response"] + "\nUnpersisted alteration"}
        return receipt
    monkeypatch.setattr(FakeAPI, "call", changed)
    with pytest.raises(ValueError, match="exact durable API receipt"):
        build().run()
    assert not (root / "final_frozen.json").exists()
    assert not list((root / "learning").glob("*.json"))
