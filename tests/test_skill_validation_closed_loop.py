"""Gated-round engineering controls; no network or execution of model code."""
import json

import pytest

from skillopt.skill_validation.calibration import GateConfig
from skillopt.skill_validation.closed_loop import run_round
from skillopt.skill_validation.closed_loop_fixtures import (
    PARENT_SKILL,
    audit_labels,
    fixture_solver,
    fixture_tasks,
    scripted_updater,
)
from skillopt.skill_validation.probe_recipes import HostInputCapability, InputStateProbeRecipe
from skillopt.skill_validation.research import BoundedResearch, ModelReply
from skillopt.skill_validation.stage2_fixtures import scripted_fetcher, scripted_model
from tests.test_skill_validation_closed_loop_fixtures import FixtureExecutor


def prepared(tmp_path, *, scenario="beneficial", engineering=True, recipe=None, missing_cal=False,
             proposer=scripted_model, update=scripted_updater):
    rows = fixture_tasks()
    index = {r["task"].contract.content_hash: r for r in rows}
    calls = {"solver": 0, "updater": 0, "auditor": 0, "proposer": 0}
    executor = FixtureExecutor()

    def solve(task, skill, condition, repeat):
        calls["solver"] += 1
        # No newly generated verification probes may leak into solver context.
        assert len(task.public_cases) == 1
        return fixture_solver(index[task.contract.content_hash], condition=condition, skill_text=skill,
                              repeat=repeat, scenario=scenario)

    def audit(task, artifact):
        calls["auditor"] += 1
        return audit_labels(index[task.contract.content_hash], artifact)

    def updater(system, user, cap):
        calls["updater"] += 1
        view = json.loads(user)
        assert set(view) == {"parent_skill", "feedback"}
        text = json.dumps(view)
        assert "host_fixture" not in text and "audit_labels" not in text
        return update(system, user, cap)

    def model(*args):
        calls["proposer"] += 1
        return proposer(*args)

    kwargs = dict(tasks=tuple((r["task"], r["region"]) for r in rows), parent_skill=PARENT_SKILL,
        solver=solve, auditor=audit, updater=updater,
        research=BoundedResearch(model=model, fetcher=scripted_fetcher, cache_root=tmp_path / "research_docs"),
        executor=executor, capabilities={k: HostInputCapability(k, 0) for k in index}, output=tmp_path,
        transport_identity={"fixture": True, "scenario": scenario}, engineering_simulation=engineering,
        gate_config=GateConfig(99 if missing_cal else 2, 2, 2, 2, .75, 0., 0., 1), recipe=recipe)
    return kwargs, calls, executor


def test_complete_gated_round_restricts_before_final_and_replays(tmp_path):
    kwargs, calls, executor = prepared(tmp_path)
    result = run_round(**kwargs)
    assert result["phase"] == "completed"
    assert result["verifier_gate"] == "pending"  # Fixtures NEVER acquire real authority.
    assert result["verifier_authority"] == "engineering_accepted"
    assert result["skill_gate"] == "Restrict"
    assert result["final"]["deployed_policy"] == {"pass": 3}
    assert result["final"]["candidate"] == {"pass": 2, "fail": 1}
    assert result["fallback_fraction"] == pytest.approx(1 / 3)
    assert not result["deployment_authorized"] and not result["real_deployment_performed"]
    assert calls["updater"] == 1
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    call_counts, executions = dict(calls), len(executor.calls)
    assert run_round(**kwargs) == result
    assert calls == call_counts and len(executor.calls) == executions
    assert {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")} == before
    final = json.loads((tmp_path / "host_only/final.json").read_text())
    assert final["not_used_for_learning_or_admission"]
    assert all(row["outcomes"][c] == row["public_verifier_outcomes"][c]
               for row in final["rows"] for c in ("no_skill", "current", "candidate"))


def test_harmful_candidate_rejected_and_all_deployment_is_base(tmp_path):
    kwargs, calls, _ = prepared(tmp_path, scenario="harmful")
    result = run_round(**kwargs)
    assert result["skill_gate"] == "Reject" and result["fallback_fraction"] == 1
    assert result["final"]["deployed_policy"] == result["final"]["no_skill"]
    assert result["final"]["candidate"] == {"fail": 3}
    assert calls["updater"] == 1


def test_unknown_candidate_is_pending_not_semantic_failure(tmp_path):
    kwargs, _, _ = prepared(tmp_path, scenario="insufficient")
    result = run_round(**kwargs)
    assert result["skill_gate"] == "Pending"
    assert result["final"]["candidate"] == {"unknown": 3}
    assert result["fallback_fraction"] == 1


def test_verifier_sample_shortage_blocks_updater_and_confirmation(tmp_path):
    kwargs, calls, _ = prepared(tmp_path, missing_cal=True)
    result = run_round(**kwargs)
    assert result["phase"] == "blocked_verifier_gate"
    assert result["verifier_authority"] == "engineering_pending"
    assert calls["updater"] == 0 and calls["solver"] == 10
    assert not (tmp_path / "candidate.json").exists()
    assert not (tmp_path / "frozen_final_routing.json").exists()


def test_no_new_executed_detection_blocks_update_even_with_a_valid_rubric(tmp_path):
    kwargs, calls, _ = prepared(tmp_path, recipe=InputStateProbeRecipe("none"))
    result = run_round(**kwargs)
    assert result["verifier_authority"] == "engineering_rejected"
    assert calls["updater"] == 0


def test_engineering_data_cannot_enter_real_admission(tmp_path):
    kwargs, calls, _ = prepared(tmp_path, engineering=False)
    result = run_round(**kwargs)
    assert result["verifier_authority"] == "pending"
    assert calls["updater"] == 0 and result["skill_gate"] == "Pending"


def test_research_no_update_has_no_calibration_or_skill_update(tmp_path):
    def no_update(*args):
        return ModelReply({"status": "no_update", "questions": [], "urls": []}, 0, 0)
    kwargs, calls, _ = prepared(tmp_path, proposer=no_update)
    result = run_round(**kwargs)
    assert result["phase"] == "blocked_verifier_proposal" and calls["solver"] == 2
    assert calls["updater"] == 0


def test_updater_may_abstain_without_producing_candidate(tmp_path):
    kwargs, calls, _ = prepared(tmp_path, update=lambda *args: "NO_UPDATE")
    result = run_round(**kwargs)
    assert result["phase"] == "no_skill_update" and result["update_status"] == "no_update"
    assert calls["updater"] == 1 and not (tmp_path / "frozen_candidate_and_scope.json").exists()


def test_final_task_cannot_be_reused_as_confirmation(tmp_path):
    kwargs, calls, _ = prepared(tmp_path)
    from dataclasses import replace
    tasks = list(kwargs["tasks"])
    final = next(t for t, _ in tasks if t.contract.partition == "final")
    tasks.append((replace(final, contract=replace(final.contract, partition="skill_confirmation")), "target"))
    kwargs["tasks"] = tuple(tasks)
    with pytest.raises(ValueError, match="cross"):
        run_round(**kwargs)
    assert not any(calls.values())


def test_scope_protocol_change_cannot_rewrite_frozen_run(tmp_path):
    kwargs, _, _ = prepared(tmp_path)
    run_round(**kwargs)
    kwargs["recipe"] = InputStateProbeRecipe("none")
    with pytest.raises(ValueError, match="Immutable"):
        run_round(**kwargs)


def test_interrupted_updater_intent_is_never_silently_retried(tmp_path):
    def crash(*args):
        raise RuntimeError("fixture interrupted callback")
    kwargs, calls, _ = prepared(tmp_path, update=crash)
    with pytest.raises(RuntimeError, match="interrupted"):
        run_round(**kwargs)
    assert calls["updater"] == 1
    with pytest.raises(ValueError, match="Interrupted"):
        run_round(**kwargs)
    assert calls["updater"] == 1


def test_runtime_unavailable_never_executes_on_host(tmp_path):
    from skillopt.coevolution_v5.core import seal
    kwargs, calls, executor = prepared(tmp_path)
    original = executor.run
    def unsupported(*args, **kw):
        record = original(*args, **kw)
        record.pop("record_hash")
        return seal({**record, "status": "unsupported"})
    executor.run = unsupported
    with pytest.raises(ValueError, match="infrastructure"):
        run_round(**kwargs)
    assert calls["updater"] == calls["proposer"] == 0
    assert not (tmp_path / "candidate.json").exists()
