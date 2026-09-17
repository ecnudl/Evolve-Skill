"""Offline orchestration tests: no model, network, or generated-code execution."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.validator_pilot import experiment as exp
from skillopt.validator_pilot.api import digest, write_immutable_json
from skillopt.validator_pilot.rubrics import initial_rubric


def task(split="train"):
    return {"id": split + "-1", "split": split, "family": split + "-family", "cluster_id": split + "-cluster",
            "prompt": "Preserve required values while repairing the requested operation.",
            "starter_code": "def f(x): return x", "public_cases": [{"expr": "f(1)", "expected": 1}],
            "private_cases": [{"expected": "PRIVATE_EXPECTED_SENTINEL"}],
            "reference_code": "PRIVATE_REFERENCE_SENTINEL", "metadata": {"secret": "PRIVATE_METADATA_SENTINEL"}}


def evaluation(hard=True):
    return {"execution_ok": True, "hard": hard, "public_observations": [
        {"label": "public", "passed": True, "actual": 1}],
        "private_diagnostics": [{"label": "PRIVATE_DIAGNOSTIC_SENTINEL", "passed": hard}],
        "dimensions": {"requested_behavior": {"passed": 1, "total": 1},
                       "preserved_behavior": {"passed": int(hard), "total": 1}}}


def judgment(rubric=None, decision="pass"):
    rubric = rubric or initial_rubric()
    return {"rubric_version": rubric["version"], "decision": decision,
            "criteria": [{"id": row["id"], "verdict": decision, "evidence": [
                {"source": "candidate_code", "observation": "Concrete code evidence for this obligation."}]}
                         for row in rubric["criteria"]], "feedback": []}


def row(split="train", version="noskill", repeat=0, *, hard=True, decision="pass", origin="natural"):
    incoming = task(split)
    verdict = {**judgment(decision=decision), "schema_valid": True}
    return {"id": incoming["id"], "split": split, "family": incoming["family"],
            "cluster_id": incoming["cluster_id"], "skill_version": version, "repeat": repeat,
            "origin": origin, "target_ok": True, "execution_ok": True, "hard": hard,
            "response": json.dumps({"code": f"artifact-{version}-{repeat}"}),
            "request_hash": digest([split, version, repeat, origin]), "evaluation": evaluation(hard),
            "judge_ok": True, "judgment": verdict, "validator_arm": "static_v0"}


def research_source():
    import hashlib
    text = "Any object can be tested for truth value."
    return {"ok": True, "requested_url": "https://docs.python.org/3/library/stdtypes.html",
            "retrieved_utc": "2026-09-08T00:00:00+00:00", "text": text,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest()}


class FakeAPI:
    instances = []
    fail_kind = None
    fail_key = None

    def __init__(self, repo, root, workers=4, **kwargs):
        self.root = Path(root)
        self.calls = []
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
        request = {"system": system, "user": user, "kind": kind, "key": key,
                   "max_tokens": max_tokens, "repeat": repeat}
        identifier = digest(request)
        cache = self.root / "calls" / (identifier + ".json")
        if cache.exists():
            return exp.read(cache)
        self.calls.append(request)
        ok = not (kind == self.fail_kind and (self.fail_key is None or key == self.fail_key))
        if kind == "target":
            content = json.dumps({"code": "code-for-" + key.rsplit(":", 1)[1]})
        elif kind.startswith("judge_"):
            rubric = json.loads(user)["rubric"]
            content = json.dumps(judgment(rubric))
        elif kind == "skill_patch":
            content = json.dumps({"edits": [{"op": "append", "target": "", "content": "\nCheck missing separately."}]})
        elif key == "revision":
            rubric = deepcopy(initial_rubric())
            rubric["version"] = "revised-" + kind
            rubric["criteria"][1]["checks"].append("Check explicitly permitted false-like inputs separately from missingness.")
            rubric["revision_notes"] = ["Development-only proposal; calibration remains necessary."]
            content = json.dumps(rubric)
        elif key == "plan":
            content = json.dumps({"questions": [{"topic": "Truthiness", "question": "When is false missing?"}],
                                  "urls": [research_source()["requested_url"]]})
        elif key == "synthesis":
            source = research_source()
            content = json.dumps({"findings": [{"topic": "Truthiness", "oldcriterion": "preserved_behavior",
                "gap": "False values and missingness are not interchangeable.", "evidenceurls": [source["requested_url"]],
                "proposedtest": "Exercise valid zero values in a new development diagnostic.",
                "uncertainty": "Task requirements still determine whether zero is allowed.",
                "evidencequotes": [{"url": source["requested_url"], "quote": source["text"]}]}],
                "limits": ["No independent calibration result is claimed."]})
        else:
            content = "Development gap analysis with competing hypotheses."
        record = {"request": request, "request_hash": identifier, "ok": ok,
                  "response": content if ok else "", "usage": {"prompt_tokens": 3, "completion_tokens": 7,
                  "total_tokens": 10}, "http_attempt_count": 1, "wall_seconds": 0.1}
        write_immutable_json(cache, record)
        return record

    def parallel(self, jobs, fn, label):
        return [fn(job) for job in jobs]


@pytest.fixture
def offline(tmp_path, monkeypatch):
    FakeAPI.instances = []
    FakeAPI.fail_kind = FakeAPI.fail_key = None
    monkeypatch.setattr(exp, "CachedAPI", FakeAPI)
    monkeypatch.setattr(exp, "fetch_sources", lambda urls, root: [research_source()])
    events = []
    def evaluate(incoming, response):
        events.append((incoming["split"], response))
        parsed = json.loads(response)["code"]
        return evaluation("mutant" not in parsed)
    fake_tasks = SimpleNamespace(Task=SimpleNamespace(from_dict=lambda value: value), evaluate=evaluate)
    monkeypatch.setitem(sys.modules, "skillopt.validator_pilot.tasks", fake_tasks)
    pilot = exp.Pilot(tmp_path, tmp_path / "run", repeats=1, rounds=1)
    pilot.tasks = {task(split)["id"]: task(split) for split in ("train", "dev", "holdout")}
    pilot.fixtures = [{"id": split + "-1", "kind": kind, "response": json.dumps({"code": kind})}
                      for split in ("dev", "holdout")
                      for kind in ("reference", "requested_mutant", "preservation_mutant")]
    monkeypatch.setattr(pilot, "prepare", lambda: None)
    return pilot, events, fake_tasks


def test_solver_only_visible_fields():
    system, user = exp.solver_messages(task("holdout"), "skill")
    assert "no execution tool" in system
    assert "PRIVATE_" not in user
    assert set(json.loads(user)["task"]) == set(exp.VISIBLE_TASK_KEYS)


def test_public_evidence_excludes_private_diagnostics():
    value = exp.public_evidence(evaluation(False))
    assert value["status"] == "executed" and value["passed"] == value["total"] == 1
    assert "PRIVATE_" not in json.dumps(value)


def test_optimizer_never_receives_train_private_truth():
    incoming = row(hard=False)
    _, user = exp.optimizer_messages("skill", {incoming["id"]: task()}, [incoming])
    assert "PRIVATE_" not in user
    assert "private_diagnostics" not in user and '"hard"' not in user
    assert "fixed_validator" in user


@pytest.mark.parametrize("split", ["dev", "holdout"])
def test_optimizer_rejects_nontrain(split):
    incoming = row(split)
    with pytest.raises(ValueError, match="train only"):
        exp.optimizer_messages("skill", {incoming["id"]: task(split)}, [incoming])


def test_shadow_gate_uses_validator_not_private_outcome():
    old = row(hard=True)
    new = row(version="candidate", hard=False)
    result = exp.shadow_gate([old], [new])
    assert result["decision"] == "shadow_keep_candidate"
    assert result["not_formal_commit"] and not result["uses_private_oracle"]
    new["judgment"]["decision"] = "fail"
    assert exp.shadow_gate([old], [new])["decision"] == "shadow_keep_current"


@pytest.mark.parametrize("field", ["target_ok", "judge_ok"])
def test_shadow_gate_rejects_unusable_calls(field):
    old, new = row(), row(version="candidate")
    new[field] = False
    assert exp.shadow_gate([old], [new])["decision"] == "shadow_keep_current"


def test_shadow_gate_rejects_malformed_judgment():
    old, new = row(), row(version="candidate")
    new["judgment"]["schema_valid"] = False
    assert exp.shadow_gate([old], [new])["decision"] == "shadow_keep_current"


def test_shadow_gate_pair_mismatch():
    with pytest.raises(ValueError, match="paired"):
        exp.shadow_gate([row()], [row(repeat=1)])


@pytest.mark.parametrize("split", ["train", "holdout"])
def test_development_revision_cases_reject_nondev(split):
    incoming = row(split)
    with pytest.raises(ValueError, match="development"):
        exp.development_cases({incoming["id"]: task(split)}, [incoming])


def test_development_cases_permit_only_development_private_feedback():
    incoming = row("dev", hard=False)
    result = exp.development_cases({incoming["id"]: task("dev")}, [incoming])
    assert result[0]["development_hard"] is False
    assert "PRIVATE_DIAGNOSTIC_SENTINEL" in json.dumps(result)
    assert "PRIVATE_REFERENCE_SENTINEL" not in json.dumps(result)
    assert "PRIVATE_EXPECTED_SENTINEL" not in json.dumps(result)


def test_development_cases_deduplicate_identical_draws():
    first = row("dev")
    second = deepcopy(first)
    second["repeat"] = 1
    second["request_hash"] = "different-call"
    result = exp.development_cases({first["id"]: task("dev")}, [first, second])
    assert len(result) == 1


def test_development_context_cap_keeps_controlled_and_prioritizes_natural_errors():
    correct = [row("dev", version=f"correct_{i}", hard=True) for i in range(5)]
    errors = [row("dev", version=f"error_{i}", hard=False) for i in range(2)]
    fixtures = [row("dev", version=kind, hard=kind == "reference", origin="controlled")
                for kind in ("reference", "requested_mutant", "preservation_mutant")]
    selected = exp.development_cases({"dev-1": task("dev")}, correct + errors + fixtures)
    assert len(selected) == 5
    assert sum(item["origin"] == "controlled" for item in selected) == 3
    assert {item["skill_version"] for item in selected if item["origin"] == "natural"} == {"error_0", "error_1"}


@pytest.mark.parametrize("raw", ["not json", "{}", '{"edits":[]}',
    '{"edits":[{"op":"replace","target":"missing","content":"new"}]}',
    '{"edits":[{"op":"append","target":"","content":""}]}'])
def test_invalid_patch_preserves_original(raw):
    output, report = exp.parse_patch(raw, "Original skill")
    assert output == "Original skill" and not report["valid"]


def test_valid_patch_reuses_skillopt_application():
    raw = json.dumps({"edits": [{"op": "append", "target": "", "content": "Check preservation."}]})
    output, report = exp.parse_patch(raw, "Original skill")
    assert "Original skill" in output and "Check preservation." in output
    assert report["valid"] and report["application"]


def test_target_cache_avoids_reexecution(offline):
    pilot, events, _ = offline
    api = FakeAPI(pilot.repo, pilot.root / "api")
    first = pilot.target(api, task(), "", "noskill", 0)
    second = pilot.target(api, task(), "", "noskill", 0)
    assert first == second and len(events) == len(api.calls) == 1


def test_target_api_failure_does_not_execute_code(offline):
    pilot, events, _ = offline
    FakeAPI.fail_kind = "target"
    api = FakeAPI(pilot.repo, pilot.root / "api")
    result = pilot.target(api, task(), "", "noskill", 0)
    assert not result["target_ok"] and result["hard"] is None and not events
    with pytest.raises(RuntimeError, match="Target API failure"):
        pilot.rollout(api, "train", "", "noskill")


def test_judge_payload_excludes_private_truth(offline):
    pilot, _, _ = offline
    api = FakeAPI(pilot.repo, pilot.root / "api")
    result = pilot.judge(api, row("holdout", hard=False), pilot.v0, "static_v0")
    assert result["judge_ok"] and result["judgment"]["schema_valid"]
    assert "PRIVATE_" not in api.calls[-1]["user"]
    assert '"hard"' not in api.calls[-1]["user"]


def test_judge_api_failure_stops_batch(offline):
    pilot, _, _ = offline
    FakeAPI.fail_kind = "judge_static_v0"
    api = FakeAPI(pilot.repo, pilot.root / "api")
    with pytest.raises(RuntimeError, match="Judge API failure"):
        pilot.judges(api, [row("holdout")], pilot.v0, "static_v0")


@pytest.mark.parametrize("arm", ["feedback_repair", "documentation_repair"])
def test_revision_budget_three_calls_and_no_promotion(offline, arm):
    pilot, _, _ = offline
    api = FakeAPI(pilot.repo, pilot.root / "api")
    development = exp.development_cases(pilot.tasks, [row("dev", hard=False)])
    result = pilot.repair(api, development, arm)
    assert result["valid"] and result["not_promoted"]
    assert len(result["request_hashes"]) == len(api.calls) == 3
    assert all(request["max_tokens"] == 6000 for request in api.calls)
    assert pilot.repair(api, development, arm) == json.loads(json.dumps(result)) and len(api.calls) == 3


def test_invalid_research_plan_is_not_feedback_fallback(offline, monkeypatch):
    pilot, _, _ = offline
    api = FakeAPI(pilot.repo, pilot.root / "api")
    monkeypatch.setattr(exp, "parse_plan", lambda raw: (_ for _ in ()).throw(ValueError("invalid plan")))
    result = pilot.repair(api, exp.development_cases(pilot.tasks, [row("dev")]), "documentation_repair")
    assert not result["valid"] and result["research_schema_or_source_failure"]
    assert len(api.calls) == 1


def test_no_successful_document_stops_research_arm_before_synthesis(offline, monkeypatch):
    pilot, _, _ = offline
    api = FakeAPI(pilot.repo, pilot.root / "api")
    monkeypatch.setattr(exp, "fetch_sources", lambda urls, root: [
        {"ok": False, "requested_url": urls[0], "text": "", "error_type": "document_timeout"}])
    result = pilot.repair(api, exp.development_cases(pilot.tasks, [row("dev")]), "documentation_repair")
    assert not result["valid"] and result["research_schema_or_source_failure"]
    assert len(api.calls) == 1


def test_ceiling_stops_skill_learning_but_runs_validator_audit(offline):
    pilot, _, _ = offline
    result = pilot.run()
    calls = FakeAPI.instances[-1].calls
    assert result["status"] == "complete" and result["headroom"]["ceiling_stop"]
    assert result["skill_versions"] == ["noskill", "manual_seed"]
    assert not any(request["kind"] == "skill_patch" for request in calls)
    assert result["no_validator_promoted"] and result["no_cross_domain_claim"]
    assert set(result["holdout"]) == {"static_v0", "feedback_repair", "documentation_repair"}
    # Frozen revisions precede every held-out judgment and are never fed held-out truth.
    last_revision = max(index for index, request in enumerate(calls) if request["key"] == "revision")
    holdout_judges = [index for index, request in enumerate(calls)
                     if request["kind"].startswith("judge_") and '"id": "holdout-1"' in request["user"]]
    assert min(holdout_judges) > last_revision
    for request in calls:
        if request["kind"] in {"feedback_repair", "documentation_repair", "skill_patch"}:
            assert "holdout-1" not in request["user"]
    assert result["holdout"]["static_v0"]["by_origin"]["controlled"]["n_responses"] == 3
    assert result["holdout"]["static_v0"]["main"]["n_responses"] == 2


def test_learned_candidate_does_not_see_private_train_truth(offline, monkeypatch):
    pilot, _, fake_tasks = offline
    def evaluate(incoming, response):
        return evaluation("code-for-noskill" not in response and "mutant" not in response)
    fake_tasks.evaluate = evaluate
    result = pilot.run()
    assert not result["headroom"]["ceiling_stop"]
    assert result["skill_versions"] == ["noskill", "manual_seed", "candidate_1"]
    patches = [request for request in FakeAPI.instances[-1].calls if request["kind"] == "skill_patch"]
    assert len(patches) == 1 and "PRIVATE_" not in patches[0]["user"]
    assert "holdout-1" not in patches[0]["user"] and "dev-1" not in patches[0]["user"]


def test_complete_run_resume_uses_only_cached_calls_and_same_results(offline):
    pilot, _, _ = offline
    first = pilot.run()
    count = first["call_ledger"]["logical_calls"]
    second = pilot.run()
    assert json.loads(json.dumps(first)) == json.loads(json.dumps(second)) and not FakeAPI.instances[-1].calls
    assert second["call_ledger"]["logical_calls"] == count


def test_ledger_counts_http_attempts_and_usage_without_preflight(offline):
    pilot, _, _ = offline
    api = FakeAPI(pilot.repo, pilot.root / "api")
    api.call("system", "user", "unit", "a")
    api.call("system", "user", "unit", "b")
    ledger = pilot.ledger()
    assert ledger["logical_calls"] == ledger["http_attempts"] == 2
    assert ledger["total_tokens"] == 20 and ledger["prompt_tokens"] == 6
    assert not ledger["preflight_included"]


@pytest.mark.parametrize("arm", ["feedback_repair", "documentation_repair"])
def test_repair_rejects_holdout_before_any_api_call(offline, arm):
    pilot, _, _ = offline
    api = FakeAPI(pilot.repo, pilot.root / "api")
    with pytest.raises(ValueError):
        pilot.repair(api, [{"split": "holdout", "task": task("holdout")}], arm)
    assert not api.calls


def test_repair_rejects_unknown_arm_before_any_api_call(offline):
    pilot, _, _ = offline
    api = FakeAPI(pilot.repo, pilot.root / "api")
    with pytest.raises(ValueError):
        pilot.repair(api, [], "typo_arm")
    assert not api.calls


def test_feedback_first_failure_does_not_send_critique(offline):
    pilot, _, _ = offline
    FakeAPI.fail_kind = "feedback_repair"
    FakeAPI.fail_key = "gap_analysis"
    api = FakeAPI(pilot.repo, pilot.root / "api")
    with pytest.raises(RuntimeError):
        pilot.repair(api, exp.development_cases(pilot.tasks, [row("dev")]), "feedback_repair")
    assert len(api.calls) == 1 and api.calls[0]["key"] == "gap_analysis"


def test_shadow_gate_rejects_empty_pairs():
    with pytest.raises(ValueError):
        exp.shadow_gate([], [])


def test_shadow_gate_rejects_duplicate_pairs():
    with pytest.raises(ValueError):
        exp.shadow_gate([row(), row()], [row(version="candidate")])


@pytest.mark.parametrize("field", ["request_hash", "response", "id", "split", "skill_version", "repeat"])
def test_target_resume_checks_response_identity(offline, field):
    pilot, _, _ = offline
    api = FakeAPI(pilot.repo, pilot.root / "api")
    result = pilot.target(api, task(), "", "noskill", 0)
    cache = pilot.root / "targets" / (result["request_hash"] + ".json")
    altered = deepcopy(result)
    altered[field] = 99 if field == "repeat" else "tampered"
    cache.write_text(json.dumps(altered))
    with pytest.raises(ValueError):
        pilot.target(api, task(), "", "noskill", 0)
