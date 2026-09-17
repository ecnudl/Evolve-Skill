"""Synthetic receipt projections only: no actual tasks, API, or execution."""

import copy
import fcntl
import json
from collections import Counter

import pytest

from scripts import diagnose_coevolution_v12 as d
from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest

POLICIES = ("no_skill", "independent", "contrastive", "selected_independent", "selected_contrastive")


def put(path, value, *, sealed=True):
    if sealed:
        value = seal({k: v for k, v in value.items() if k != "record_hash"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return value


def score(success=1, *, oracle=True, delivery=True):
    return {"all_attempt_success": success, "oracle_available": oracle, "delivery_valid": delivery,
            "semantic_success": success if oracle else None, "native_error": "SECRET_NATIVE_ERROR"}


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root = tmp_path / "outputs/coevolution_v12/fixture"
    root.mkdir(parents=True)
    (root / ".run.lock").touch()
    protocol = put(root / "protocol.json", {"design": "smoke", "histories": 1, "rounds": 1,
        "learning_arms": ["independent", "contrastive"], "policies": list(POLICIES), "source_hashes": {}})
    skills = {arm: "SECRET_SKILL_SENTINEL_" + arm for arm in ("independent", "contrastive")}
    skill_hashes = {arm: d.hashlib.sha256(text.encode()).hexdigest() for arm, text in skills.items()}
    skill_hashes["no_skill"] = d.EMPTY_SKILL_HASH
    calls, solves = {}, {}

    def call(kind, key, user="SECRET_TASK_GOLD_SENTINEL", *, ok=True):
        request = {"kind": kind, "key": key, "user": user}
        h = digest(request)
        row = {"request": request, "request_hash": h, "ok": ok, "response": "SECRET_RESPONSE",
               "http_attempt_count": 1, "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        calls[h] = put(root / "api/calls" / (h + ".json"), row, sealed=False)
        return row

    def solve(phase, domain, arm, final_score, *, initial_ok=True):
        task = phase + "-" + domain
        hashes = []
        for i, stage in enumerate(("generation", "revision")):
            receipt = call("v12_solve_" + stage, f"{task}-{arm}-{stage}", ok=initial_ok if i == 0 else True)
            h = receipt["request_hash"]
            hashes.append(h)
            public = score(0, oracle=False, delivery=False) if i == 0 and not initial_ok else score(int(i == 1))
            put(root / "runtime/stages" / (h + ".json"), {"stage": stage, "receipt": receipt,
                "public_score": public, "artifact": "SECRET_PUBLIC_ARTIFACT"})
        row = put(root / "runtime/solves" / (digest([task, arm]) + ".json"), {
            "task_id": task, "domain": domain, "cluster_id": "cluster-" + domain,
            "phase": phase, "skill_hash": skill_hashes[arm], "request_hashes": hashes,
            "stage_api_ok": [initial_ok, True], "score": final_score, "artifact": "SECRET_FINAL_ARTIFACT"})
        solves[phase, domain, arm] = row
        return row

    domains = ("coding", "spreadsheet")
    training = [solve("development", domain, "no_skill", score(i)) for i, domain in enumerate(domains)]
    for domain in domains:
        for arm in ("no_skill", "independent", "contrastive"):
            solve("selection", domain, arm, score(int(arm == "contrastive")))
    for domain in (*domains, "rule_reasoning"):
        for arm in ("no_skill", "independent", "contrastive"):
            value = score(0) if (domain, arm) == ("coding", "independent") else score()
            if (domain, arm) == ("rule_reasoning", "contrastive"):
                value = score(0, oracle=False, delivery=False)
            solve("final", domain, arm, value, initial_ok=(domain, arm) != ("coding", "contrastive"))
    for arm in ("independent", "contrastive"):
        observed = [{"task_id": row["task_id"], "domain": row["domain"], "role": role,
            "score": row["score"], "request_hashes": row["request_hashes"], "artifact": "SECRET_TRAIN_ARTIFACT",
            "executed_checks": "SECRET_DEVELOPMENT_CHECKS"} for row in training for role in ("no_skill", "current")]
        receipt = call("v12_skill_update", arm, json.dumps({"observed_records": observed,
                       "public_tasks": "SECRET_TASK_TEXT", "parent_skill": ""}))
        identity = {"history": 0, "round": 0, "arm": arm}
        put(root / "learning" / ("h0-r0-" + arm + ".json"), {**identity,
            "request_hash": receipt["request_hash"], "api_receipt_hash": digest(receipt),
            "evidence_hash": digest(observed), "parent_hash": d.EMPTY_SKILL_HASH, "valid": True,
            "changed": True, "reason": "valid_text_candidate", "skill": skills[arm]})
        accepted = arm == "contrastive"
        put(root / "selection" / ("h0-r0-" + arm + ".json"), {**identity,
            "solver_records": [solves["selection", domain, a]["record_hash"] for a in ("no_skill", arm) for domain in domains],
            "parent_hash": d.EMPTY_SKILL_HASH, "candidate_hash": skill_hashes[arm], "accept": accepted,
            "macro_delta": float(accepted), "domain_differences": dict.fromkeys(domains, float(accepted))})
    final_rows = []
    for policy in POLICIES:
        arm = "no_skill" if policy == "selected_independent" else policy.removeprefix("selected_")
        for domain in (*domains, "rule_reasoning"):
            row = solves["final", domain, arm]
            final_rows.append({k: row[k] for k in ("task_id", "domain", "cluster_id", "skill_hash", "request_hashes", "score")}
                | {"history": 0, "policy": policy, "solver_record_hash": row["record_hash"]})
    grid = put(root / "final_rows.json", {"rows": final_rows})
    ledger = {"cached_logical_calls": len(calls), "successful_calls": sum(r["ok"] for r in calls.values()),
              "terminal_errors": sum(not r["ok"] for r in calls.values()), "http_attempts_from_cached_records": len(calls),
              "prompt_tokens": 10 * len(calls), "completion_tokens": 5 * len(calls), "total_tokens": 15 * len(calls),
              "missing_usage_calls": 0}
    result = put(root / "results.json", {"complete": True, "protocol_hash": protocol["record_hash"],
        "final_grid_hash": grid["record_hash"], "ledger": ledger,
        "learning": {"proposals": 2, "valid": 2, "text_changes": 2, "selection_acceptances": 1}})
    state = {"replays": 0, "mutate": None}

    class Replay:
        def __init__(self, repo, output, *, design, api_factory):
            self.complete, self.api_factory = True, api_factory
            assert output == root and design == "smoke"

        def run(self):
            state["replays"] += 1
            return state["mutate"](self) if state["mutate"] else d.study.read(root / "results.json")

    monkeypatch.setattr(d.study, "Study", Replay)
    monkeypatch.setattr(d.study, "source_hashes", lambda _: {})
    return {"repo": tmp_path, "root": root, "protocol": protocol, "result": result,
            "solves": solves, "calls": calls, "skills": skills, "state": state}


def diagnose(f):
    return d.diagnose(f["root"], repo=f["repo"])


def test_completed_diagnostics_sealed_readonly_no_body_leakage(fixture):
    before = d._tree(fixture["repo"])
    result = verify(diagnose(fixture))
    assert result["posthoc_descriptive_only"] and result["smoke_not_scientific_inference"]
    assert result["new_primary_tests"] == result["new_selection_decisions"] == 0
    assert result["audit"]["files_written"] == result["audit"]["model_api_calls"] == result["audit"]["native_executions"] == 0
    assert d._tree(fixture["repo"]) == before and fixture["state"]["replays"] == 1
    assert "SECRET_" not in json.dumps(result)
    assert result == diagnose(fixture)


def test_all_learning_rounds_parent_train_not_candidate_gain(fixture):
    result = diagnose(fixture)
    assert len(result["learning_process"]) == 2
    for row in result["learning_process"]:
        assert row["history"] == row["round"] == 0 and row["valid"] and row["changed"]
        assert row["skill_chars"] == len(fixture["skills"][row["arm"]])
        train = row["parent_current_training_vs_base"]
        assert train["before"]["macro"] == train["after"]["macro"] == .5
        assert train["macro_delta"] == 0 and train["identical_paired_trajectories"] == 2
        assert row["training_is_parent_before_update_not_candidate_after_update"]
        selection = row["selection_old_to_candidate"]
        gain = int(row["arm"] == "contrastive")
        assert selection["macro_delta"] == selection["after"]["macro"] == gain
        assert selection["before"]["macro"] == 0 and selection["accepted"] is bool(gain)


def test_final_raw_vs_selected_worst_domain_and_loss_classes(fixture):
    final = diagnose(fixture)["final"]
    policies = final["policies"]
    assert policies["independent"]["macro"] == pytest.approx(2 / 3)
    assert policies["independent"]["maximum_domain_drop_vs_base"] == 1
    assert policies["selected_independent"]["macro"] == 1
    assert policies["selected_independent"]["selected_diagnostic_only"]
    assert policies["contrastive"]["worst_domain_success"] == 0
    assert policies["contrastive"]["paired_counts"] == {"wins": 0, "losses": 1, "ties": 2, "paired_unknown": 1}
    losses = final["loss_positions_vs_no_skill"]
    assert len(losses) == 3
    assert {r["failure_class"] for r in losses} == {"delivery_invalid", "oracle_evaluated_failure_not_pure_reasoning_attribution"}
    assert all(set(r) == {"history", "policy", "task_id", "domain", "failure_class"} for r in losses)


def test_public_revisions_unique_and_never_called_hidden_improvements(fixture):
    public = diagnose(fixture)["public_revision_transitions"]
    assert public["unique_trajectories"] == 17
    groups = public["by_phase_and_domain"]
    assert groups["all"]["trajectories"] == 17 and groups["all"]["all_attempt_0_to_1"] == 17
    assert groups["all"]["unavailable_to_pass"] == 1 and groups["all"]["fail_to_pass"] == 16
    assert groups["final"]["trajectories"] == 9  # not 15 policy/history positions
    assert public["both_scores_public_only"] and public["not_initial_to_final_hidden_gain"]
    assert not public["skill_causal_contribution_identified"]


def test_cost_by_kind_deduplicates_all_shared_requests(fixture):
    cost = diagnose(fixture)["api_costs"]
    assert cost["totals"]["unique_logical_calls"] == 36
    assert cost["by_kind"]["v12_skill_update"]["unique_logical_calls"] == 2
    assert cost["by_kind"]["v12_solve_generation"]["unique_logical_calls"] == 17
    assert cost["by_kind"]["v12_solve_revision"]["total_tokens"] == 255
    assert cost["totals"]["total_tokens"] == 540 and cost["totals"]["terminal_errors"] == 1


@pytest.mark.parametrize("name", ["results.json", ".run.lock"])
def test_no_incomplete_run_inspection(fixture, name):
    (fixture["root"] / name).unlink()
    with pytest.raises(ValueError, match="completed evidence"):
        diagnose(fixture)
    assert fixture["state"]["replays"] == 0


def test_lock_does_not_inspect_running_experiment(fixture):
    with (fixture["root"] / ".run.lock").open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            diagnose(fixture)
    assert fixture["state"]["replays"] == 0


@pytest.mark.parametrize("action", ["factory", "api", "execution"])
def test_no_api_no_execution_tripwires(fixture, action):
    def attempt(replay):
        if action == "factory":
            replay.api_factory()
        elif action == "api":
            d.study.OfflineAPI.call(None)
        else:
            d.runtime.legacy.evaluate(None)
    fixture["state"]["mutate"] = attempt
    with pytest.raises(ValueError, match="model access or native execution"):
        diagnose(fixture)


def test_replay_mutation_refused(fixture):
    def mutate(_):
        (fixture["root"] / "supervisor.log").write_text("mutation")
        return fixture["result"]
    fixture["state"]["mutate"] = mutate
    with pytest.raises(ValueError, match="changed evidence"):
        diagnose(fixture)


def test_replay_result_drift_refused(fixture):
    fixture["state"]["mutate"] = lambda _: {**fixture["result"], "complete": False}
    with pytest.raises(ValueError, match="replay differs"):
        diagnose(fixture)


def test_source_drift_refused(fixture, monkeypatch):
    monkeypatch.setattr(d.study, "source_hashes", lambda _: {"changed": True})
    with pytest.raises(ValueError, match="Frozen sources"):
        diagnose(fixture)


def test_final_exact_grid_rejects_missing_policy(fixture):
    path = fixture["root"] / "final_rows.json"
    grid = d.study.read(path)
    grid["rows"].pop()
    grid = put(path, grid)
    put(fixture["root"] / "results.json", {**fixture["result"], "final_grid_hash": grid["record_hash"]})
    with pytest.raises(ValueError, match="complete shared task grid"):
        diagnose(fixture)


@pytest.mark.parametrize("directory", ["learning", "selection"])
def test_process_grid_closed(fixture, directory):
    put(fixture["root"] / directory / "orphan.json", {})
    with pytest.raises(ValueError, match="grid is incomplete or orphaned"):
        diagnose(fixture)


def test_optimizer_evidence_binding(fixture):
    path = fixture["root"] / "learning/h0-r0-independent.json"
    row = d.study.read(path)
    put(path, {**row, "evidence_hash": "wrong"})
    with pytest.raises(ValueError, match="evidence digest differs"):
        diagnose(fixture)


def test_optimizer_receipt_hash_binding(fixture):
    path = fixture["root"] / "learning/h0-r0-independent.json"
    row = d.study.read(path)
    put(path, {**row, "api_receipt_hash": "wrong"})
    with pytest.raises(ValueError, match="receipt binding differs"):
        diagnose(fixture)


def test_selection_recomputed_delta_matches_frozen_decision(fixture):
    path = fixture["root"] / "selection/h0-r0-independent.json"
    row = d.study.read(path)
    put(path, {**row, "macro_delta": .9})
    with pytest.raises(ValueError, match="scores disagree"):
        diagnose(fixture)


def test_public_stage_order_checked(fixture):
    h = fixture["solves"]["final", "coding", "contrastive"]["request_hashes"][0]
    path = fixture["root"] / "runtime/stages" / (h + ".json")
    put(path, {**d.study.read(path), "stage": "revision"})
    with pytest.raises(ValueError, match="stage ordering"):
        diagnose(fixture)


def test_cost_ledger_disagreement_refused(fixture):
    result = copy.deepcopy(fixture["result"])
    result["ledger"]["total_tokens"] += 1
    put(fixture["root"] / "results.json", result)
    with pytest.raises(ValueError, match="closed ledger"):
        diagnose(fixture)


def test_unexpected_request_not_added_to_cost(fixture):
    put(fixture["root"] / "api/calls/orphan.json", {}, sealed=False)
    with pytest.raises(ValueError, match="orphan/missing requests"):
        diagnose(fixture)


@pytest.mark.parametrize("value,stage,expected", [
    (score(), [False, True], "success"),
    (score(0), [True, True], "oracle_evaluated_failure_not_pure_reasoning_attribution"),
    (score(0, oracle=False, delivery=False), [True, False], "delivery_api_unavailable"),
    (score(0, oracle=False, delivery=False), [True, True], "delivery_invalid"),
    (score(0, oracle=False), [True, True], "delivered_oracle_unknown"),
])
def test_failure_class_does_not_conflate_api_delivery_and_semantic(value, stage, expected):
    assert d._failure_class({"score": value, "stage_api_ok": stage}) == expected


def test_cluster_and_domain_hierarchy_is_not_pooled_positions():
    rows = [{"task_id": str(i), "domain": "coding", "cluster_id": "large", "score": score()}
            for i in range(20)]
    rows += [{"task_id": "fail", "domain": "coding", "cluster_id": "small", "score": score(0)},
             {"task_id": "other", "domain": "spreadsheet", "cluster_id": "other", "score": score(0)}]
    for row in list(rows):
        rows.append(copy.deepcopy(row))  # extra history does not overweight a task
    result = d._hierarchy(rows)
    assert result == {"macro": .25, "by_domain": {"coding": .5, "spreadsheet": 0}}


def test_api_usage_missing_is_separate_from_recorded_zero(fixture):
    h = next(h for h, row in fixture["calls"].items() if row["request"]["kind"] == "v12_solve_revision")
    path = fixture["root"] / "api/calls" / (h + ".json")
    row = json.loads(path.read_text())
    put(path, {**row, "usage": {}}, sealed=False)
    result = copy.deepcopy(fixture["result"])
    for field, delta in (("prompt_tokens", -10), ("completion_tokens", -5), ("total_tokens", -15), ("missing_usage_calls", 1)):
        result["ledger"][field] += delta
    cost = d._api_costs(fixture["root"], result, set(fixture["calls"]))
    assert cost["totals"]["missing_usage_calls"] == 1 and cost["totals"]["total_tokens"] == 525


def test_main_cli_prints_metadata_json(monkeypatch, capsys, tmp_path):
    seen = []
    def fake(path):
        seen.append(path)
        return {"posthoc_descriptive_only": True}
    monkeypatch.setattr(d, "diagnose", fake)
    assert d.main(["--output", str(tmp_path)]) == 0
    assert seen == [tmp_path] and json.loads(capsys.readouterr().out)["posthoc_descriptive_only"]


def test_counter_fixture_has_no_duplicates(fixture):
    count = Counter(r["request"]["kind"] for r in fixture["calls"].values())
    assert count == {"v12_skill_update": 2, "v12_solve_generation": 17, "v12_solve_revision": 17}
