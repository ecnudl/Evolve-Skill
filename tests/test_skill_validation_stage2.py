"""Stage-2 orchestration tests: scripted fixture observations, never exec/eval."""
from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation.research import BoundedResearch, ModelReply
from skillopt.skill_validation.stage2 import ARMS, export_pool, import_pool, run_study
from skillopt.skill_validation.stage2_fixtures import fixture_pool, scripted_fetcher, scripted_model
from skillopt.validator_pilot.api import digest


class FixtureExecutor:
    """Hand-coded observer for these fixtures only, not a general code runner.

    No Python source evaluation or task-audit access. Public arguments and exact
    known fixture code select a hand-authored operation, all explicitly fixture.
    """
    def __init__(self, *, unsupported=False):
        self.calls = []
        self.unsupported = unsupported
        self.known_sources = {a.files[0].content for row in fixture_pool() for a in row["artifacts"]}

    @property
    def identity(self):
        return {"kind": "scripted-fixture-executor-no-code-execution", "version": "v1",
                "unsupported_fixture": self.unsupported}

    def run(self, files, module, function, args, kwargs):
        assert set(files) == {"solution.py"} and module == "solution" and function == "solve"
        source = files["solution.py"]
        assert source in self.known_sources, "Unknown code must not be run by a fixture observer"
        self.calls.append({"files": deepcopy(files), "module": module, "function": function,
                           "args": deepcopy(args), "kwargs": deepcopy(kwargs)})
        call = {"module": module, "function": function, "args": args, "kwargs": kwargs}
        base = {"status": "unsupported" if self.unsupported else "observed",
                "input_hash": digest({"files": files, **call}), "source_hash": digest(files),
                "call_hash": digest(call), "executor_identity": self.identity, "duration_seconds": 0.0,
                "reason": "fixture_handwritten_observation_not_executed", "exception": None}
        if self.unsupported:
            return seal(base)
        before, after = deepcopy(args), deepcopy(args)
        if len(args) == 2:
            actual = {k: v for k, v in args[0].items() if v >= args[1]}
            mutates = "del values[key]" in source
        elif "dict.fromkeys" in source:
            actual = list(dict.fromkeys(args[0]))
            mutates = "values[:]" in source
        else:
            actual = sorted(args[0])
            mutates = "values.sort()" in source
        if mutates:
            after[0] = deepcopy(actual)
        return seal({**base, "actual": actual, "before_args": before, "after_args": after,
                     "before_kwargs": deepcopy(kwargs), "after_kwargs": deepcopy(kwargs)})


class FixtureModel:
    def __init__(self, callback=scripted_model):
        self.calls, self.callback = [], callback

    def __call__(self, system, user, cap):
        self.calls.append({"system": system, "payload": json.loads(user), "cap": cap})
        return self.callback(system, user, cap)


def study(tmp_path, *, pool=None, model=None, executor=None, **kwargs):
    model = model or FixtureModel()
    executor = executor or FixtureExecutor()
    research = BoundedResearch(model=model, fetcher=scripted_fetcher, cache_root=tmp_path / "research_cache")
    result = run_study(fixture_pool() if pool is None else pool, research=research, executor=executor,
                       output=tmp_path, transport_identity={"kind": "scripted_fixture", "real_model_calls": 0,
                                                            "real_document_retrievals": 0}, **kwargs)
    return result, model, executor


def test_full_fixture_study_and_exact_replay(tmp_path):
    result, model, executor = study(tmp_path)
    assert result["pool_artifact_count"] == 27 and result["model_artifact_count"] == 0
    assert result["learning_or_generalization_effect_established"] is False
    assert result["proposal_status"] == {"fixed": "no_update", "adaptive_no_research": "update", "adaptive_research": "update"}
    assert len(model.calls) == 4 and executor.calls
    assert result["total_unique_execution_cost"]["executor_requests_including_development_and_shared_preparation"] == 126
    assert result["proposal_cost_accounting"]["scripted_fixture_actual_provider_and_network_requests"] == 0
    for arm in ARMS[1:]:
        actual = result["outcomes"]["verifier_calibration"][arm]["report"]["actual_cost"]["candidate"]
        assert actual["model_calls"] == actual["retrievals"] == 0
    before = {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*.json")}
    original_counts = (len(model.calls), len(executor.calls))
    repeated, _, _ = study(tmp_path, model=model, executor=executor)
    assert repeated == result
    assert (len(model.calls), len(executor.calls)) == original_counts
    assert before == {str(p.relative_to(tmp_path)): p.read_bytes() for p in tmp_path.rglob("*.json")}


def test_fixture_success_never_becomes_natural_effect_or_authorization(tmp_path):
    result, _, _ = study(tmp_path)
    for arm in ARMS[1:]:
        calibrated = result["outcomes"]["verifier_calibration"][arm]
        audited = result["outcomes"]["verifier_audit"][arm]
        assert calibrated["decision"]["status"] == "pending"
        assert calibrated["report"]["new_detection_count"] == 0
        assert calibrated["report"]["full_natural"]["candidate"]["common_obligation_rows"] == 0
        assert calibrated["report"]["diagnostic_only"]["candidate"]["common_obligation_rows"] > 0
        assert audited["decision"]["reason"] == "independent_audit_has_no_admission_authority"
        assert "none" in audited["report"]["authority"]


def test_unsupported_execution_remains_unknown_not_semantic_failure(tmp_path):
    result, _, executor = study(tmp_path, executor=FixtureExecutor(unsupported=True))
    assert executor.calls
    for path in (tmp_path / "comparisons").glob("*.json"):
        value = verify(json.loads(path.read_text()))
        for reports in value["reports"].values():
            for report in reports:
                assert report["status"] == "unknown"
                assert "fail" not in report["obligations"].values()
    assert all(result["outcomes"]["verifier_calibration"][a]["decision"]["status"] == "pending" for a in ARMS[1:])


def test_no_update_proposals_have_no_new_gate_authority(tmp_path):
    model = FixtureModel(lambda *_: ModelReply({"status": "no_update", "questions": [], "urls": []}, 0, 0))
    result, _, _ = study(tmp_path, model=model)
    assert len(model.calls) == 2
    assert set(result["proposal_status"].values()) == {"no_update"}
    assert not (tmp_path / "gate" / "freezes").exists()
    for arm in ARMS[1:]:
        assert result["outcomes"]["verifier_calibration"][arm]["decision"]["reason"] == "no_new_verifier"


def test_failed_transport_is_retained_with_unknown_usage_and_fallback(tmp_path):
    def failed(*_):
        raise RuntimeError("PROVIDER-SECRET-SHOULD-NOT-APPEAR")
    result, model, _ = study(tmp_path, model=FixtureModel(failed))
    assert len(model.calls) == 2
    assert result["proposal_status"]["adaptive_research"] == "invalid"
    assert result["proposal_costs"]["adaptive_research"]["input_tokens"] is None
    assert result["outcomes"]["verifier_calibration"]["adaptive_research"]["report"]["actual_cost"]["candidate"] is None
    assert result["outcomes"]["verifier_calibration"]["adaptive_research"]["decision"]["reason"] == "no_new_verifier"
    assert "PROVIDER-SECRET" not in json.dumps(result)


def test_model_view_excludes_audit_identity_and_heldout_tasks(tmp_path):
    result, model, executor = study(tmp_path)
    prohibited = {"audit", "audit_status", "expected_json", "condition", "skill_hash", "skill_version",
                  "family_id", "near_miss", "task_id", "partition", "project_id", "original_task_id"}
    def inspect(value):
        if isinstance(value, dict):
            assert not prohibited.intersection(value)
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    for call in model.calls:
        for visible in call["payload"]["development"]:
            inspect(visible)
            assert visible["purpose"] == "proposal_development_not_blind_evaluation"
            assert "sorted in ascending order" in visible["task"]["prompt"]
            assert "threshold" not in visible["task"]["prompt"]
            assert "first-occurrence order" not in visible["task"]["prompt"]
            assert all(g["information_origin"] == "development_audit_summary"
                       and g["research_independent_discovery"] is False for g in visible["development_gaps"])
    for call in executor.calls:
        # The runner observes actual source/input, never reference output or H.
        assert set(call) == {"files", "module", "function", "args", "kwargs"}
    assert result["model_artifact_count"] == 0


def test_proposals_freeze_before_any_calibration_and_audit_is_last(tmp_path, monkeypatch):
    from skillopt.skill_validation import stage2
    events = []
    originals = {name: getattr(stage2, name) for name in ("register_freeze", "calibrate", "evaluate_comparison")}
    def freeze(*args, **kwargs):
        events.append("freeze")
        return originals["register_freeze"](*args, **kwargs)
    def calibrate(*args, **kwargs):
        assert events.count("freeze") == 2
        assert "audit" not in events
        events.append("calibration")
        return originals["calibrate"](*args, **kwargs)
    def evaluate(*args, **kwargs):
        if kwargs.get("purpose") == "verifier_audit":
            assert events.count("calibration") == 2
            events.append("audit")
        return originals["evaluate_comparison"](*args, **kwargs)
    monkeypatch.setattr(stage2, "register_freeze", freeze)
    monkeypatch.setattr(stage2, "calibrate", calibrate)
    monkeypatch.setattr(stage2, "evaluate_comparison", evaluate)
    study(tmp_path)
    assert events == ["freeze", "freeze", "calibration", "calibration", "audit", "audit"]


def test_independent_audit_changes_cannot_change_model_proposals_or_calibration(tmp_path):
    first, model_a, _ = study(tmp_path / "a")
    pool = fixture_pool()
    for row in pool:
        if row["task"].contract.partition == "verifier_audit":
            for labels in row["audit"].values():
                for key in labels:
                    labels[key] = "unknown"
    second, model_b, _ = study(tmp_path / "b", pool=pool)
    assert model_a.calls == model_b.calls
    assert first["proposal_status"] == second["proposal_status"]
    for arm in ARMS[1:]:
        before = first["outcomes"]["verifier_calibration"][arm]
        after = second["outcomes"]["verifier_calibration"][arm]
        assert before["report"] == after["report"]
        # Independent runs have different measured proposal wall times and thus
        # receipt hashes. The calibrated evidence and decision must not change.
        for key in ("status", "rubric_pipeline_hash", "config_hash", "comparison_hash", "reasons", "scope_status"):
            assert before["decision"][key] == after["decision"][key]
    assert first["outcomes"]["verifier_audit"] != second["outcomes"]["verifier_audit"]


def test_pool_roundtrip_separates_private_labels(tmp_path):
    pool = fixture_pool()
    export_pool(pool, tmp_path)
    assert import_pool(tmp_path) == pool
    public = json.loads((tmp_path / "pool.json").read_text())
    assert all(set(r) == {"id", "task", "artifacts"} for r in public["rows"])
    assert (tmp_path / "host_only" / "audit.json").exists()


@pytest.mark.parametrize("target", ["public", "private"])
def test_unsealed_pool_tampering_fails(tmp_path, target):
    export_pool(fixture_pool(), tmp_path)
    path = tmp_path / ("pool.json" if target == "public" else "host_only/audit.json")
    value = json.loads(path.read_text())
    if target == "public":
        value["rows"][0]["task"]["contract"]["prompt"] += " hidden mutation"
    else:
        value["rows"][0]["near_miss"] = not value["rows"][0]["near_miss"]
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        import_pool(tmp_path)


def test_resealed_other_pool_audit_is_rejected(tmp_path):
    export_pool(fixture_pool(), tmp_path)
    path = tmp_path / "host_only" / "audit.json"
    value = verify(json.loads(path.read_text()))
    value.pop("record_hash", None)
    value["public_pool_hash"] = "a" * 64
    path.write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError, match="another frozen pool"):
        import_pool(tmp_path)


def _rebind_row(row, contract):
    task = replace(row["task"], contract=contract)
    artifacts = tuple(replace(a, task_hash=contract.content_hash) for a in row["artifacts"])
    audit = {new.content_hash: row["audit"][old.content_hash] for old, new in zip(row["artifacts"], artifacts)}
    return {**row, "task": task, "artifacts": artifacts, "audit": audit}


@pytest.mark.parametrize("overlap", ["task", "family"])
def test_split_overlap_is_rejected_before_execution(tmp_path, overlap):
    pool = fixture_pool()
    source = pool[0]["task"].contract
    for index, row in enumerate(pool):
        if row["task"].contract.partition == "verifier_calibration":
            change = {"original_task_id": source.original_task_id} if overlap == "task" else {"family_id": source.family_id}
            pool[index] = _rebind_row(row, replace(row["task"].contract, **change))
    model, executor = FixtureModel(), FixtureExecutor()
    with pytest.raises(ValueError):
        study(tmp_path, pool=pool, model=model, executor=executor)
    assert not model.calls and not executor.calls


def test_missing_condition_not_silently_dropped(tmp_path):
    pool = fixture_pool()
    pool[0]["artifacts"] = pool[0]["artifacts"][:2]
    with pytest.raises(ValueError, match="three-condition"):
        export_pool(pool, tmp_path)


def test_caller_cannot_resume_with_new_audit_or_model_settings(tmp_path):
    study(tmp_path)
    pool = fixture_pool()
    first = pool[0]
    first["audit"][first["artifacts"][0].content_hash]["input"] = "unknown"
    with pytest.raises(ValueError, match="Immutable artifact differs"):
        study(tmp_path, pool=pool)


def test_interrupted_proposal_is_not_silently_reissued(tmp_path):
    _, model, executor = study(tmp_path)
    # Emulate an attempt that has an immutable intent but no terminal receipt.
    (tmp_path / "proposals" / "adaptive_no_research.json").unlink()
    counts = len(model.calls), len(executor.calls)
    with pytest.raises(ValueError, match="Interrupted proposal without terminal receipt"):
        study(tmp_path, model=model, executor=executor)
    assert (len(model.calls), len(executor.calls)) == counts


def test_symlink_pool_or_output_is_not_followed(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        export_pool(fixture_pool(), alias)
    assert not list(actual.iterdir())


@pytest.mark.parametrize("child", ["protocol.json", "proposals", "frozen_pool/host_only"])
def test_nested_output_symlinks_cannot_redirect_writes(tmp_path, child):
    output = tmp_path / "run"
    outside = tmp_path / "outside"
    output.mkdir()
    outside.mkdir()
    link = output / child
    link.parent.mkdir(parents=True, exist_ok=True)
    if child.endswith(".json"):
        target = outside / "protected.json"
        target.write_text("protected bytes")
        link.symlink_to(target)
    else:
        link.symlink_to(outside, target_is_directory=True)
    protected = {p.name: p.read_bytes() for p in outside.iterdir()}
    model, executor = FixtureModel(), FixtureExecutor()
    with pytest.raises(ValueError, match="Symlink"):
        study(output, model=model, executor=executor)
    assert {p.name: p.read_bytes() for p in outside.iterdir()} == protected
    assert not model.calls


def test_in_place_obligation_not_relabelled_as_verified(tmp_path):
    study(tmp_path)
    saw_near_miss = False
    for path in (tmp_path / "comparisons").glob("*.json"):
        comparison = verify(json.loads(path.read_text()))
        for report in comparison["reports"]["adaptive_research"]:
            if "required_in_place" in report["obligations"]:
                saw_near_miss = True
                assert report["obligations"]["return"] == "pass"
                assert report["obligations"]["required_in_place"] == "unknown"
                state = [c for c in report["checks"] if c["check_id"] == "public-input-state"]
                assert len(state) == 1 and state[0]["status"] == "not_applicable"
                assert report["status"] == "unknown"
    assert saw_near_miss


def test_common_evidence_charged_as_shared_execution_not_three_free_runs(tmp_path):
    result, _, executor = study(tmp_path, common_evidence=True)
    assert result["learning_or_generalization_effect_established"] is False
    for path in (tmp_path / "comparisons").glob("*.json"):
        value = verify(json.loads(path.read_text()))
        assert value["shared_execution_cost"] == 6
        assert sum(c["execution_requests"] for c in value["costs"].values()) == 0
        assert value["mode"] == "common_evidence"
    assert len(executor.calls) == 18 + 6 * 6
    assert result["total_unique_execution_cost"]["executor_requests_including_development_and_shared_preparation"] == 54
