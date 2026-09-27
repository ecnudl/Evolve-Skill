"""Offline control-flow fixtures, NOT model or curriculum-effect experiments.

No candidate Python is executed. Mocked qualification in integration tests is
an explicit path-testing override; the normal fake executor cannot qualify.
The real feedback replay, RuleSkill updater and solver adapters remain active.
"""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation import curriculum_study as study
from skillopt.skill_validation.capability_goals import TASK_ROLES
from skillopt.skill_validation.curriculum_tasks import family_fingerprint
from skillopt.skill_validation.rule_skill import RuleSkill
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_capability_goals import history
from tests.test_skill_validation_public_revision import CODE, FixtureCalls, FixtureExecutor


SPECS = [
    {"steps": [{"op": "filter", "kind": "even"}, {"op": "map", "kind": "abs"}], "aggregate": "sum"},
    {"steps": [{"op": "map", "kind": "negate"}, {"op": "reorder", "kind": "reverse"}], "aggregate": "weighted_sum"},
    {"steps": [{"op": "filter", "kind": "positive"}, {"op": "reorder", "kind": "unique_stable"}], "aggregate": "count"},
]


def pools():
    return {name: [deepcopy(spec)] for name, spec in zip(("confirmation", *study.ARMS), SPECS)}


def test_pool_partitions_are_structurally_disjoint_not_certified_semantic_families():
    value = study.validate_family_pools(pools())
    assert value["structural_and_finite_behavior_disjointness_only"] and not value["semantic_independence_established"]
    shared = pools()
    shared["targeted"] = deepcopy(shared["generic"])
    overlap = study.validate_family_pools(shared)
    assert overlap["development_overlap"] == [family_fingerprint(SPECS[1])]


@pytest.mark.parametrize("within_pool", [True, False])
def test_finite_behavior_alias_not_new_independent_confirmation_family(within_pool):
    alias_a = {"steps": [{"op": "map", "kind": "abs"}, {"op": "filter", "kind": "positive"}], "aggregate": "sum"}
    alias_b = {"steps": [{"op": "filter", "kind": "nonzero"}, {"op": "map", "kind": "abs"}], "aggregate": "sum"}
    assert family_fingerprint(alias_a) != family_fingerprint(alias_b)
    value = pools()
    value["confirmation"] = [alias_a, alias_b] if within_pool else [alias_a]
    if not within_pool:
        value["generic"] = [alias_b]
    with pytest.raises(ValueError, match="behavior"):
        study.validate_family_pools(value)


@pytest.mark.parametrize("change", ["missing", "duplicate", "generic_overlap", "targeted_overlap", "empty"])
def test_pool_conflicts_rejected(change):
    value = pools()
    if change == "missing":
        value.pop("confirmation")
    elif change == "duplicate":
        value["generic"] *= 2
    elif change == "empty":
        value["targeted"] = []
    else:
        value[change.removesuffix("_overlap")] = deepcopy(value["confirmation"])
    with pytest.raises(ValueError):
        study.validate_family_pools(value)


def summary_rows():
    rows = []
    base = ["pass", "fail", "unknown", "pass"]
    outcomes = {"no_skill": base, "generic": ["fail", "pass", "pass", "unknown"],
                "targeted": ["pass", "fail", "unknown", "pass"]}
    for arm, statuses in outcomes.items():
        for index, status in enumerate(statuses):
            rows.append({"arm": arm, "family": "family-a" if index < 2 else "family-b",
                         "role": "preserve", "repeat": index % 2, "status": status})
    return rows


def test_summary_preserves_denominators_unknown_and_family_clusters():
    rows = summary_rows()
    planned = {(r["family"], r["role"], r["repeat"]) for r in rows}
    result = study.summarize(rows, expected_positions=planned)
    arm = result["arms"]["generic"]
    assert arm["positions"] == 4 and arm["role_tasks"] == arm["structural_families"] == 2
    assert arm["status_counts"] == {"pass": 2, "fail": 1, "unknown": 1}
    assert arm["paired_vs_no_skill"] == {"win": 1, "loss": 1, "tie": 0, "unknown": 2}
    assert arm["family_net_paired_wins"] == {"family-a": 0, "family-b": 0}
    assert arm["family_unknown_positions"] == {"family-a": 0, "family-b": 2}
    assert arm["family_complete_comparison"] == {"family-a": True, "family-b": False}
    assert result["independent_semantic_family_count_unknown"]
    assert not result["deployment_authorized"] and not result["cross_domain_evaluated"]


@pytest.mark.parametrize("change", ["duplicate", "missing_arm", "unpaired", "missing_all", "bad_status", "bad_arm"])
def test_summary_does_not_drop_missing_or_invalid_positions(change):
    rows = summary_rows()
    planned = {(r["family"], r["role"], r["repeat"]) for r in rows}
    if change == "duplicate":
        rows += [deepcopy(rows[0])]
    elif change == "missing_arm":
        rows = [r for r in rows if r["arm"] != "targeted"]
    elif change == "unpaired":
        rows.pop()
    elif change == "missing_all":
        rows = [r for r in rows if r["family"] != "family-b"]
    elif change == "bad_status":
        rows[0]["status"] = "not_run"
    else:
        rows[0]["arm"] = "favored"
    with pytest.raises(ValueError):
        study.summarize(rows, expected_positions=planned)


class GenerationCalls(FixtureCalls):
    def call(self, system, user, kind, *, repeat=0, max_tokens):
        return super().call(system, user, kind, repeat=repeat, max_tokens=max_tokens)


def test_teacher_budget_cannot_expand_solver_and_shares_replay_reservations(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    api = FakeAPI(tmp_path, tmp_path / "api")
    calls = study.CurriculumCalls(api, tmp_path / "budget", "frozen", limit=1)
    user = json.dumps({"excluded_pipeline_specs": []})
    def generate(_):
        return calls.call("teacher", user, "curriculum-spec-generic", max_tokens=study.GENERATION_TOKEN_CAP)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(generate, range(2)))
    assert a == b and len(api.fresh_requests) == 1
    assert a["request"]["max_tokens"] == study.GENERATION_TOKEN_CAP
    assert calls.accounting()["reserved_logical_requests"] == 1
    with pytest.raises(ValueError, match="restricted"):
        calls.call("solver", "{}", "public-initial", max_tokens=study.GENERATION_TOKEN_CAP)
    with pytest.raises(ValueError, match="exhausted"):
        calls.call("solver", "{}", "public-initial", max_tokens=2048)


def test_teacher_budget_does_not_resample_an_interrupted_request(tmp_path):
    class Interrupted(FakeAPI):
        def call(self, *args, **kwargs):
            raise OSError("fixture disconnection before a durable response")
    api = Interrupted(tmp_path, tmp_path / "api")
    calls = study.CurriculumCalls(api, tmp_path / "budget", "frozen", limit=2)
    with pytest.raises(OSError):
        calls.call("teacher", "{}", "curriculum-spec-generic", max_tokens=study.GENERATION_TOKEN_CAP)
    with pytest.raises(ValueError, match="Interrupted teacher"):
        calls.call("teacher", "{}", "curriculum-spec-generic", max_tokens=study.GENERATION_TOKEN_CAP)


def test_generation_only_normalizes_the_whole_document_json_fence():
    raw = json.dumps({"families": [SPECS[0]]})
    wrapped = "```json\n" + raw + "\n```"
    result = study._generate(GenerationCalls(wrapped), count=1, condition="generic")
    assert result["status"] == "generated" and result["families"] == [SPECS[0]]
    for malformed in ("Here it is\n" + wrapped, wrapped + "\nExplanation", wrapped + wrapped,
                      " " * 24000 + wrapped):
        result = study._generate(GenerationCalls(malformed), count=1, condition="generic")
        assert result["status"] == "invalid" and not result["families"]


@pytest.mark.parametrize("raw", ["not JSON", "{}", '{"families":[]}',
    json.dumps({"families": [SPECS[0], SPECS[0]]}),
    json.dumps({"families": [SPECS[0]], "answer": 42})])
def test_generation_rejects_format_errors_without_retry_or_padding(raw):
    calls = GenerationCalls(raw)
    result = study._generate(calls, count=1, condition="generic")
    assert result["status"] == "invalid" and result["families"] == []
    assert len(calls.calls) == 1


def test_generation_requires_exact_count_excludes_confirmation_and_retains_failure():
    calls = GenerationCalls(json.dumps({"families": [SPECS[0]]}))
    assert study._generate(calls, count=2, condition="generic")["status"] == "invalid"
    assert study._generate(calls, count=1, condition="generic", excluded=[SPECS[0]])["status"] == "invalid"
    calls.ok = False
    result = study._generate(calls, count=1, condition="generic")
    assert result["status"] == "api_failure" and result["families"] == []
    assert len(calls.calls) == 3


@pytest.mark.parametrize("change", ["request", "hash", "ok_type"])
def test_generation_does_not_adopt_another_request_receipt(change):
    class Mismatched(GenerationCalls):
        def call(self, *args, **kwargs):
            record = super().call(*args, **kwargs)
            if change == "request":
                record["request"]["user"] = "other condition"
                record["request_hash"] = digest(record["request"])
            elif change == "hash":
                record["request_hash"] = "0" * 64
            else:
                record["ok"] = 1
            return record
    with pytest.raises(ValueError, match="another request"):
        study._generate(Mismatched(json.dumps({"families": [SPECS[0]]})), count=1, condition="generic")


class FakeAPI:
    """Durable fixture transport exercising real BoundedCalls/cache identities."""
    instances = []
    updater_response = "candidate"
    generation_response = None

    def __init__(self, repo, root, **kwargs):
        self.root = Path(root)
        self.model = "fixture-no-model"
        self.service = {"fixture": True, "provider": "FIXTURE"}
        self.fresh_requests, self.requests = [], []
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def parallel(self, items, fn, label):
        return [fn(item) for item in items]

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                   "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        self.requests.append(request)
        path = self.root / "calls" / (digest(request) + ".json")
        if path.exists():
            return json.loads(path.read_text())
        self.fresh_requests.append(request)
        payload = json.loads(user)
        if kind == "capability-goal-plan":
            response = json.dumps({"status": "goals", "reason": "Fixture prospective gap, not a causal conclusion.",
                "goals": [{"goal_id": "fixture-constraint", "mechanism": "input_state_preservation",
                    "suspected_rule": "Parent might lack an explicit boundary.",
                    "failure": "Test preservation and exceptions; fixture only.",
                    "competing_hypotheses": ["Advice could interfere.", "Sampling could explain a difference."],
                    "required_task_roles": list(TASK_ROLES),
                    "evidence_ids": [payload["evidence_catalog"][0]["id"]],
                    "desired_observations": ["Compare public before/after state under explicit task contracts."]}]})
        elif kind.startswith("curriculum-spec-"):
            spec = SPECS[2] if kind.endswith("targeted") else SPECS[0] if payload["excluded_pipeline_specs"] else SPECS[1]
            response = self.generation_response if self.generation_response is not None else json.dumps({"families": [spec]})
        elif kind == "public-initial":
            response = json.dumps({"solution.py": CODE})
        elif kind == "public-revision":
            response = "KEEP"
        elif kind == "conditional-rule-update":
            if self.updater_response != "candidate":
                response = self.updater_response
            else:
                evidence = payload["evidence_catalog"][0]["id"]
                rule = {"id": "check-contract", "mechanism": "Constraint Preservation",
                        "procedure": ["Compare stated mutation obligations with the implementation."],
                        "when": "When the contract explicitly describes input mutation.",
                        "exceptions": ["Mutation is allowed when requested; do not preserve forbidden old state."],
                        "scope": {"required_obligation_kinds": ["requested_behavior"], "forbidden_obligation_kinds": []},
                        "evidence_ids": [evidence]}
                response = json.dumps({"parent_hash": payload["parent_hash"], "edits": [
                    {"operation": "add", "rule_id": rule["id"], "rule": rule, "evidence_ids": [evidence],
                     "reason": "Fixture reference tests integrity, not support or useful learning."}]})
        else:
            raise AssertionError("Unexpected paid stage: " + kind)
        record = {"request": request, "request_hash": digest(request), "ok": True,
                  "response": response, "fixture_only": True, "http_attempt_count": 1,
                  "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record))
        return record


class StudyExecutor(FixtureExecutor):
    transport_identity = {"kind": "offline-test-only", "network": False}


@pytest.fixture
def prepared_run(monkeypatch, tmp_path):
    view = history(fail=True, repeats=1)
    parent, feedback = tmp_path / "historical_parent.json", tmp_path / "historical_feedback.json"
    parent.write_text(json.dumps(seal({"text": view["host_only"]["parent_text"]})))
    feedback.write_text(json.dumps(view["host_only"]["bundle"]))
    monkeypatch.setattr(study, "CachedAPI", FakeAPI)
    monkeypatch.setattr(FakeAPI, "instances", [])
    monkeypatch.setattr(FakeAPI, "updater_response", "candidate")
    monkeypatch.setattr(FakeAPI, "generation_response", None)
    output = tmp_path / "run"
    executor = StudyExecutor()
    def invoke(**options):
        return study.run(tmp_path, output, parent, feedback, executor, workers=1, repeats=1,
                         development_families=1, confirmation_families=1, **options)
    return invoke, output, executor


def allow_fixture_control_path(monkeypatch):
    # Deliberately bypass qualification for driver wiring tests, never production.
    monkeypatch.setattr(study, "screen_family", lambda spec, executor, root: seal({
        "status": "qualified", "formal_eligible": True, "fixture_only": True,
        "test_override_only": True, "family_fingerprint": family_fingerprint(spec)}))


def test_unqualified_fixture_cannot_enter_learning(prepared_run):
    invoke, root, _ = prepared_run
    result = invoke()
    assert result["status"] == "pending" and result["stage"] == "qualification"
    assert result["method_effect_evaluated"] is False and not result["deployment_authorized"]
    assert not (root / "frozen_tasks.json").exists() and not (root / "updates").exists()


def test_prepare_freezes_tasks_before_any_learning_and_replays(prepared_run, monkeypatch):
    allow_fixture_control_path(monkeypatch)
    invoke, root, _ = prepared_run
    result = invoke(stop_after="prepare")
    assert result["status"] == "prepared" and not result["method_effect_evaluated"]
    frozen = verify(json.loads((root / "frozen_tasks.json").read_text()))
    protocol = verify(json.loads((root / "protocol.json").read_text()))
    assert frozen["before_learning"] and frozen["not_verifier_calibration"]
    assert protocol["new_feedback_is_shadow_only_no_new_verifier_authorization"]
    assert protocol["research_feedback_arm"] == "pending_independent_calibration_not_run"
    assert not protocol["deployment_authorized"] and not protocol["final_access"]
    assert protocol["development_generators_do_not_see_confirmation_specs"]
    assert not (root / "cold_parent.json").exists() and not (root / "updates").exists()
    assert {r["kind"] for r in FakeAPI.instances[-1].fresh_requests} == {
        "capability-goal-plan", "curriculum-spec-generic", "curriculum-spec-targeted"}
    generation = [r for r in FakeAPI.instances[-1].fresh_requests if r["kind"].startswith("curriculum-spec-")]
    assert [r["kind"] for r in generation] == ["curriculum-spec-generic", "curriculum-spec-targeted", "curriculum-spec-generic"]
    generic, targeted, confirmation = [json.loads(r["user"]) for r in generation]
    assert generic["excluded_pipeline_specs"] == targeted["excluded_pipeline_specs"] == []
    assert confirmation["excluded_pipeline_specs"] == SPECS[1:]
    assert generic["public_learning_goal"] is confirmation["public_learning_goal"] is None
    assert targeted["public_learning_goal"] and "opaque historical advice" not in targeted["public_learning_goal"]
    replay = invoke(stop_after="prepare")
    assert replay == result and FakeAPI.instances[-1].fresh_requests == []


def test_invalid_generation_is_pending_without_resampling_or_solver(prepared_run, monkeypatch):
    invoke, root, _ = prepared_run
    monkeypatch.setattr(FakeAPI, "generation_response", "not JSON")
    result = invoke()
    assert result["status"] == "pending" and result["stage"] == "generation"
    assert len(FakeAPI.instances[-1].fresh_requests) == 4  # Two planners, two retained failed development generations.
    assert not (root / "frozen_tasks.json").exists()


def test_learning_uses_shared_cold_parent_new_public_feedback_and_actual_rule_adapter(prepared_run, monkeypatch):
    allow_fixture_control_path(monkeypatch)
    invoke, root, _ = prepared_run
    result = invoke(stop_after="learn")
    assert result["status"] == "learned_shadow_candidates"
    parent = verify(json.loads((root / "cold_parent.json").read_text()))
    assert parent["text"] == "" and RuleSkill.from_dict(parent["skill"]).rules == ()
    frozen = verify(json.loads((root / "frozen_candidates.json").read_text()))
    assert frozen["before_confirmation_execution"] and not frozen["deployment_authorized"]
    for arm in study.ARMS:
        update = verify(json.loads((root / "updates" / (arm + ".json")).read_text()))["update"]
        assert update["status"] == "candidate" and update["feedback_use"] == "shadow_diagnostic_only"
        assert update["parent_hash"] == RuleSkill.from_dict(parent["skill"]).content_hash
        assert len(RuleSkill.from_dict(frozen["candidates"][arm]).rules) == 1
        assert not update["deployment_authorized"] and not update["semantic_support_verified"]
        feedback = verify(json.loads((root / "feedback" / (arm + ".json")).read_text()))
        assert all(entry["task"]["contract"]["partition"] == "development" for entry in feedback["entries"])
    api = FakeAPI.instances[-1]
    initial = [r for r in api.requests if r["kind"] == "public-initial"]
    assert len(initial) == 12 and len({r["key"] for r in initial}) == 6
    assert all(json.loads(r["user"])["optional_skill"] == "" for r in initial)
    # Cold Current/No-Skill are identity aliases, not two learned experiences.
    assert sum(r["kind"] == "public-initial" for r in api.fresh_requests) == 6
    updates = [json.loads(r["user"]) for r in api.fresh_requests if r["kind"] == "conditional-rule-update"]
    assert len(updates) == 2 and all(u["parent_skill"] == "" and u["parent_rules"] == [] for u in updates)
    assert all("opaque historical advice" not in json.dumps(u) for u in updates)
    assert not (root / "confirmation_rows.json").exists()


def test_full_run_has_frozen_candidate_before_audit_and_keeps_unknown(prepared_run, monkeypatch):
    allow_fixture_control_path(monkeypatch)
    invoke, root, _ = prepared_run
    original = study.audit_artifact
    def assert_freeze(row, artifact, executor, path):
        frozen = verify(json.loads((root / "frozen_candidates.json").read_text()))
        assert frozen["before_confirmation_execution"]
        assert row["task"].contract.partition == "skill_confirmation"
        # Fake execution returns True, not a valid hidden-case vector: unknown.
        return original(row, artifact, executor, path)
    monkeypatch.setattr(study, "audit_artifact", assert_freeze)
    result = invoke()
    assert result["status"] == "completed_shadow_pilot"
    assert not result["deployment_authorized"] and not result["research_increment_evaluated"]
    for arm in result["result"]["arms"].values():
        assert arm["positions"] == arm["role_tasks"] == 3 and arm["structural_families"] == 1
        assert arm["status_counts"] == {"pass": 0, "fail": 0, "unknown": 3}
        assert arm["paired_vs_no_skill"] == {"win": 0, "loss": 0, "tie": 0, "unknown": 3}
    assert (root / "confirmation_rows.json").exists()


def test_invalid_update_falls_back_to_empty_parent_not_handwritten_rule(prepared_run, monkeypatch):
    allow_fixture_control_path(monkeypatch)
    monkeypatch.setattr(FakeAPI, "updater_response", "invalid rule JSON")
    invoke, root, _ = prepared_run
    result = invoke(stop_after="learn")
    assert result["status"] == "learned_shadow_candidates"
    frozen = verify(json.loads((root / "frozen_candidates.json").read_text()))
    assert frozen["update_statuses"] == {"generic": "invalid", "targeted": "invalid"}
    assert all(RuleSkill.from_dict(s).rules == () for s in frozen["candidates"].values())


def test_missing_public_execution_receipts_replay_as_unknown(prepared_run, monkeypatch):
    allow_fixture_control_path(monkeypatch)
    original = study.ExecutionCache
    class ReadOnlyFeedback(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.read_only = True
    monkeypatch.setattr(study, "ExecutionCache", ReadOnlyFeedback)
    invoke, root, _ = prepared_run
    assert invoke(stop_after="learn")["status"] == "learned_shadow_candidates"
    for arm in study.ARMS:
        feedback = verify(json.loads((root / "feedback" / (arm + ".json")).read_text()))
        assert feedback["execution_records"]
        assert all(r["execution"]["status"] == "unsupported" for r in feedback["execution_records"])
        assert all(r["execution"]["reason"] == "common_evidence_missing" for r in feedback["execution_records"])


def test_prepare_learn_full_resume_keeps_same_candidates_and_cache(prepared_run, monkeypatch):
    allow_fixture_control_path(monkeypatch)
    invoke, root, _ = prepared_run
    assert invoke(stop_after="prepare")["status"] == "prepared"
    assert invoke(stop_after="learn")["status"] == "learned_shadow_candidates"
    original_freeze = (root / "frozen_candidates.json").read_bytes()
    result = invoke()
    assert result["status"] == "completed_shadow_pilot"
    assert (root / "frozen_candidates.json").read_bytes() == original_freeze
    assert all(r["kind"] in {"public-initial", "public-revision"} for r in FakeAPI.instances[-1].fresh_requests)
    assert invoke() == result and FakeAPI.instances[-1].fresh_requests == []


def test_historical_parent_evidence_binding_checked_before_paid_calls(prepared_run):
    invoke, root, _ = prepared_run
    path = root.parent / "historical_parent.json"
    path.write_text(json.dumps(seal({"text": "Different history cannot inherit another parent's evidence."})))
    with pytest.raises(ValueError):
        invoke()
    assert FakeAPI.instances == []


def test_resume_rejects_changed_frozen_source_hash(prepared_run, monkeypatch):
    allow_fixture_control_path(monkeypatch)
    invoke, root, _ = prepared_run
    invoke(stop_after="prepare")
    path = root / "protocol.json"
    record = verify(json.loads(path.read_text()))
    record["source_hashes"]["curriculum_study.py"] = "0" * 64
    path.write_text(json.dumps(seal({k: v for k, v in record.items() if k != "record_hash"})))
    with pytest.raises(ValueError):
        invoke(stop_after="prepare")
