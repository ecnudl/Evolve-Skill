"""Fabricated receipt control-flow tests; no real model or code execution."""
import hashlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation.checks import ExecutionCache, pipeline_hash, validate_callable
from skillopt.skill_validation.development_feedback import build_development_feedback
from skillopt.skill_validation.models import SourceFile
from skillopt.skill_validation.public_repair_feedback import (
    ARMS,
    PromptBudgetExceeded,
    UnsupportedRepairEvidence,
    _ReplayExecutor,
    _require_supported_execution,
    _select,
    build_details,
    build_request,
    propose,
)
from skillopt.skill_validation.research import fixed_rubric
from skillopt.skill_validation.rule_skill import RuleSkill
from skillopt.skill_validation.rule_solver import solve_rule_condition
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_public_revision import (
    CODE,
    REVISED,
    SECRET,
    FixtureCalls,
    FixtureExecutor,
    fixture_row,
    reseal,
)
from tests.test_skill_validation_rule_learning import response


class Calls(FixtureCalls):
    def __init__(self, transition):
        super().__init__()
        self.transition = transition

    def call(self, system, user, kind, *, repeat, max_tokens):
        self.ok = not (kind == "public-initial" and self.transition == "unknown")
        self.response = (json.dumps({"solution.py": CODE}) if kind == "public-initial" else
                         "KEEP" if self.transition == "stable" else
                         "not JSON" if self.transition == "parse_fallback" else
                         json.dumps({"solution.py": REVISED}))
        if kind == "public-revision" and self.transition == "api_fallback":
            self.ok = False
        return super().call(system, user, kind, repeat=repeat, max_tokens=max_tokens)


def fixture_source(tmp_path, transitions=("repaired", "deteriorated", "unresolved", "stable", "unknown"), repeats=1):
    from skillopt.skill_validation import public_revision
    from skillopt.skill_validation.natural_study import _write
    _write(tmp_path / "protocol.json", seal({"source_hashes": {
        "public_revision.py": hashlib.sha256(Path(public_revision.__file__).read_bytes()).hexdigest()}}))
    parent, sources, entries, public_rows = RuleSkill("fixture-history", ()), [], [], []
    final_executor = FixtureExecutor()
    cache = ExecutionCache(final_executor)
    for index, transition in enumerate(transitions):
        original = fixture_row()
        contract = replace(original["task"].contract, task_id=f"{SECRET}-{index}",
            original_task_id=f"{SECRET}-{index}", family_id=f"{SECRET}-family-{index}",
            prompt=original["task"].contract.prompt + f"\nPublic fixture context {index}.")
        row = {"task": replace(original["task"], contract=contract),
               "public_task": replace(original["public_task"], contract=contract),
               "public_wrapper": {"path": "public_runner.py", "content": "# registered public fixture"}}
        public_rows.append(row)
        before = transition in {"deteriorated", "stable"}
        after = transition in {"repaired", "stable"}
        for repeat in range(repeats):
            artifacts, reports = [], []
            for role in ("no_skill", "current"):
                pos = tmp_path / "histories" / "h0" / "development" / digest([row["task"].content_hash, repeat, role])
                calls = Calls(transition)
                executor = FixtureExecutor({"actual": before}, {"actual": after})
                solved = solve_rule_condition(row, parent, role, repeat, calls, executor, pos, exposure="raw")
                draft, final = solved["initial_artifact"], solved["artifact"]
                initial = json.loads((pos / "public_initial" / (draft.content_hash + ".json")).read_text())
                sources.append({"public_row": {"task": row["task"].to_dict(),
                    "public_task": row["public_task"].to_dict(), "public_wrapper": row["public_wrapper"]},
                    "exposure": solved["exposure"], "result": solved["record"], "draft": draft.sealed(),
                    "initial": initial, "revision": solved["revision"]["record"]})
                if final.availability == "available":
                    final_executor.outcomes.append({"actual": after if transition not in {"parse_fallback", "api_fallback"}
                                                  else before})
                artifacts.append(final)
                reports.append(validate_callable(row["public_task"], final, fixed_rubric(), cache))
            entries.append({"task": row["public_task"], "artifacts": tuple(artifacts), "reports": tuple(reports)})
    bundle = build_development_feedback(entries, parent_skill="", rubric=fixed_rubric(),
        pipeline_hash=pipeline_hash(fixed_rubric(), cache), execution_identity=cache.identity,
        execution_records=tuple(cache.records.values()), detail_limit=2)
    return parent, bundle, sources, public_rows


def test_all_positions_and_aliases_counted_without_causal_skill_claim(tmp_path):
    parent, bundle, sources, _ = fixture_source(tmp_path, repeats=2)
    record = build_details(parent, bundle, sources, detail_limit=6)
    verify(record)
    coverage = record["coverage"]
    assert coverage["task_count"] == coverage["structural_family_count"] == 5
    assert coverage["pair_count"] == coverage["distinct_request_trajectories"] == 10
    assert coverage["position_count"] == 20
    assert coverage["unique_initial_requests"] == 10 and coverage["unique_revision_requests"] == 8
    assert coverage["deduplicated_transition_counts"] == {
        "repaired": 2, "deteriorated": 2, "unresolved": 2, "stable": 2, "unknown": 2}
    assert len(coverage["selected_pairs"]) == 6
    assert len({r["task_slot"] for r in coverage["selected_pairs"][:5]}) == 5
    assert not record["research_increment"] and not record["hidden_audit_used"]
    assert not record["learning_authorized"] and not record["deployment_authorized"]


def test_only_trajectory_annex_differs_both_catalogs_include_selected_final_pairs(tmp_path):
    parent, bundle, sources, _ = fixture_source(tmp_path)
    details = build_details(parent, bundle, sources)
    left, right = [build_request(parent, bundle, details, arm=a) for a in ARMS]
    assert left["system"] == right["system"]
    assert left["evidence_catalog"] == right["evidence_catalog"]
    assert left["parser_request_hash"] == right["parser_request_hash"]
    assert left["max_tokens"] == right["max_tokens"] == 2048
    luser, ruser = json.loads(left["user"]), json.loads(right["user"])
    assert luser.pop("public_repair_annex") == []
    annex = ruser.pop("public_repair_annex")
    assert luser == ruser
    assert {a["evidence_id"] for a in annex} == {e["id"] for e in right["evidence_catalog"]}
    assert all(r["prompt_bytes"] == len((r["system"] + r["user"]).encode()) for r in (left, right))
    assert all(r["prompt_hash"] == digest({"system": r["system"], "user": r["user"]}) for r in (left, right))


def test_private_identifiers_hidden_labels_and_api_diagnostics_never_project(tmp_path):
    parent, bundle, sources, _ = fixture_source(tmp_path)
    assert SECRET in json.dumps(sources)  # Host provenance and execution metadata.
    details = build_details(parent, bundle, sources)
    for arm in ARMS:
        request = build_request(parent, bundle, details, arm=arm)
        text = request["system"] + request["user"]
        assert SECRET not in text
        for key in ("host_audit", "source_ref", "api_receipt", "source_hash", "family_id", "stdout"):
            assert json.dumps(key) + ":" not in text
    assert _ReplayExecutor({}).identity == {}
    with pytest.raises(AssertionError, match="never execute"):
        _ReplayExecutor({}).run()


def test_joint_wrapper_failure_does_not_become_state_or_return_failure(tmp_path):
    parent, bundle, sources, _ = fixture_source(tmp_path, ("repaired",))
    details = build_details(parent, bundle, sources)
    item = json.loads(build_request(parent, bundle, details, arm="trajectory")["user"])["public_repair_annex"][0]
    trajectory = item["shared_trajectory"]
    assert trajectory["draft"]["public_check"]["status"] == "fail"
    assert trajectory["draft"]["public_check"]["component_attribution"] == "unknown"
    assert trajectory["draft"]["public_check"]["observations"][0]["input"]["args"] == []
    assert trajectory["selected_public_check"]["status"] == "pass"
    assert not any("preservation" in k for k in trajectory["draft"]["public_check"])
    assert set(item["roles"]) == {"no_skill", "current"}


def timeout_source(tmp_path, monkeypatch, *, enabled=True, transition="repaired", final_timeout=False,
                   timeout_changes=None):
    """Build fabricated, fully bound sources; no API or candidate execution."""
    from skillopt.skill_validation import public_revision
    from tests.test_skill_validation_clean_timeout_revision import IsolatedFixture, timeout

    class TimeoutFixture(IsolatedFixture):
        def __init__(self, *outcomes, **kwargs):
            if outcomes:
                outcomes = (timeout(**(timeout_changes or {})),
                            *(timeout() if final_timeout else item for item in outcomes[1:]))
            super().__init__(*outcomes, **kwargs)

    original = public_revision.revise_public

    def revise(*args, **kwargs):
        return original(*args, **kwargs, allow_clean_timeout_revision=enabled)

    monkeypatch.setattr(public_revision, "revise_public", revise)
    monkeypatch.setattr(__import__(__name__, fromlist=["FixtureExecutor"]), "FixtureExecutor", TimeoutFixture)
    return fixture_source(tmp_path, (transition,))


def test_clean_timeout_to_pass_keeps_unknown_transition_and_marks_no_return(tmp_path, monkeypatch):
    parent, bundle, sources, _ = timeout_source(tmp_path, monkeypatch)
    details = build_details(parent, bundle, sources)
    assert details["coverage"]["deduplicated_transition_counts"] == {"unknown": 1}
    role = details["coverage"]["positions"][0]["roles"]["no_skill"]
    assert role["draft_status"] == "unknown" and role["selected_status"] == "pass"
    assert role["transition"] == "unknown" and role["revision_decision"] == "revised"
    request = build_request(parent, bundle, details, arm="trajectory")
    trajectory = json.loads(request["user"])["public_repair_annex"][0]["shared_trajectory"]
    observation = trajectory["draft"]["public_check"]["observations"][0]
    assert observation["observation_status"] == "execution_budget_exceeded"
    assert observation["execution_budget_seconds"] == 10 and observation["semantic_outcome"] == "unknown"
    assert observation["observed"] is None and observation["exception"] is None
    selected = trajectory["selected_public_check"]["observations"][0]
    assert selected["observed"] is True and "observation_status" not in selected
    assert SECRET not in request["system"] + request["user"]
    assert build_details(parent, bundle, sources) == details  # Receipt-only replay.


@pytest.mark.parametrize("transition,final_timeout", [("stable", False), ("repaired", True)])
def test_selected_clean_timeout_keeps_explicit_unknown(tmp_path, monkeypatch, transition, final_timeout):
    parent, bundle, sources, _ = timeout_source(tmp_path, monkeypatch,
        transition=transition, final_timeout=final_timeout)
    details = build_details(parent, bundle, sources)
    trajectory = details["annex"][0]["shared_trajectory"]
    selected = trajectory["selected_public_check"]
    assert selected["status"] == "unknown"
    assert selected["observations"][0]["observation_status"] == "execution_budget_exceeded"
    assert selected["observations"][0]["semantic_outcome"] == "unknown"
    assert details["coverage"]["deduplicated_transition_counts"] == {"unknown": 1}


@pytest.mark.parametrize("enabled,changes", [(False, {}), (True, {"reason": "container_execution_failed"}),
                                            (True, {"cleanup_confirmed": False})])
def test_other_unknowns_do_not_acquire_clean_timeout_projection(tmp_path, monkeypatch, enabled, changes):
    parent, bundle, sources, _ = timeout_source(tmp_path, monkeypatch,
        enabled=enabled, timeout_changes=changes)
    details = build_details(parent, bundle, sources)
    trajectory = details["annex"][0]["shared_trajectory"]
    assert trajectory["revision_decision"] == "skipped"
    assert trajectory["draft"]["public_check"]["status"] == "unknown"
    assert "observation_status" not in trajectory["draft"]["public_check"]["observations"][0]
    assert details["coverage"]["deduplicated_transition_counts"] == {"unknown": 1}


@pytest.mark.parametrize("policy", [None, "different-policy", True, [], {}])
def test_unrecognized_explicit_timeout_policy_is_rejected(tmp_path, monkeypatch, policy):
    parent, bundle, sources, _ = timeout_source(tmp_path, monkeypatch)
    bad = deepcopy(sources)
    bad[0]["revision"]["request"]["clean_timeout_revision_policy"] = policy
    bad[0]["revision"] = reseal(bad[0]["revision"])
    bad[0]["result"]["revision_hash"] = bad[0]["revision"]["record_hash"]
    bad[0]["result"] = reseal(bad[0]["result"])
    with pytest.raises(ValueError, match="Unsupported public timeout"):
        build_details(parent, bundle, bad)


def test_clean_timeout_keep_cannot_be_resealed_as_ineligible_skip(tmp_path, monkeypatch):
    parent, bundle, sources, _ = timeout_source(tmp_path, monkeypatch, transition="stable")
    bad = deepcopy(sources)
    record = bad[0]["revision"]
    record.update(status="skipped", reason="public_execution_unknown_or_unsupported",
                  api_receipt=None, revision_opportunity_completed=False)
    bad[0]["revision"] = reseal(record)
    bad[0]["result"]["revision_hash"] = bad[0]["revision"]["record_hash"]
    bad[0]["result"] = reseal(bad[0]["result"])
    with pytest.raises(ValueError, match="cannot be mislabeled unsupported"):
        build_details(parent, bundle, bad)


def test_legacy_stage_projection_is_byte_identical(tmp_path):
    from skillopt.skill_validation import public_revision
    from skillopt.skill_validation.public_repair_feedback import _stage_view
    parent, bundle, sources, rows = fixture_source(tmp_path, ("repaired",))
    source = sources[0]
    stage = source["revision"]["draft_stage"]
    draft = source["draft"]
    artifact = public_revision.ArtifactRecord.from_dict({k: v for k, v in draft.items() if k != "record_hash"})
    row = rows[0]
    _, user = public_revision._messages(row["task"], row["public_task"], artifact, "", stage)
    execution = json.loads(user)["public_execution"]
    legacy = {"status": stage["report"]["status"], "observations": execution["observations"],
              "checker": execution["callable"], "scope": "registered_public_check_only_not_component_attribution",
              "component_attribution": "unknown"}
    current = _stage_view(stage, row["task"], row["public_task"], artifact, "")
    assert json.dumps(current, sort_keys=True) == json.dumps(legacy, sort_keys=True)
    details = build_details(parent, bundle, sources)
    assert "observation_status" not in json.dumps(build_request(parent, bundle, details, arm="trajectory"))


def output_options_source(tmp_path, monkeypatch, *, initial_tokens=4096, revision_tokens=4096,
                          format_policy="compact_json_v1", transition="repaired",
                          draft_timeout=False, attempted_timeout=False):
    """Recorded nonlegacy output controls, still nonexecuting fixtures only."""
    from skillopt.skill_validation import public_revision
    from tests.test_skill_validation_clean_timeout_revision import IsolatedFixture, timeout

    class OutputFixture(IsolatedFixture):
        def __init__(self, *outcomes, **kwargs):
            self.final_recheck = not outcomes
            if outcomes:
                outcomes = (timeout() if draft_timeout else outcomes[0],
                            *(timeout() if attempted_timeout else item for item in outcomes[1:]))
            super().__init__(*outcomes, **kwargs)

        def run(self, *args, **kwargs):
            if self.final_recheck:
                # Every profile control below ends at a known public-passing
                # selected artifact; attempted failure/unknown remains stored.
                self.outcomes = [{"actual": True}]
            return super().run(*args, **kwargs)

    original_initial = public_revision.solve_public_initial
    original_revision = public_revision.revise_public

    def initial(*args, **kwargs):
        return original_initial(*args, **{**kwargs, "max_tokens": initial_tokens, "format_policy": format_policy})

    def revise(*args, **kwargs):
        return original_revision(*args, **{**kwargs, "max_tokens": revision_tokens, "format_policy": format_policy,
            "allow_clean_timeout_revision": True, "public_selection_policy": public_revision.PUBLIC_NONREGRESSION_POLICY})

    monkeypatch.setattr(public_revision, "solve_public_initial", initial)
    monkeypatch.setattr(public_revision, "revise_public", revise)
    monkeypatch.setattr(__import__(__name__, fromlist=["FixtureExecutor"]), "FixtureExecutor", OutputFixture)
    return fixture_source(tmp_path, (transition,))


@pytest.mark.parametrize("initial_tokens,revision_tokens,format_policy", [
    (4096, 4096, "compact_json_v1"), (4096, 2048, "compact_json_v1"),
    (2048, 4096, "compact_json_v1"), (2048, 2048, "compact_json_v1"), (4096, 4096, None),
])
def test_declared_output_controls_replay_without_changing_learning_budget(
        tmp_path, monkeypatch, initial_tokens, revision_tokens, format_policy):
    parent, bundle, sources, _ = output_options_source(tmp_path, monkeypatch,
        initial_tokens=initial_tokens, revision_tokens=revision_tokens, format_policy=format_policy)
    for source in sources:
        initial, request = source["initial"], source["revision"]["request"]
        assert initial.get("max_tokens", 2048) == initial_tokens
        assert initial["api_receipt"]["request"]["max_tokens"] == initial_tokens
        assert request.get("max_tokens", 2048) == revision_tokens
        assert source["revision"]["api_receipt"]["request"]["max_tokens"] == revision_tokens
        assert initial.get("format_policy") == request.get("format_policy") == format_policy
        assert ("max_tokens" in initial) == (initial_tokens != 2048)
        assert ("max_tokens" in request) == (revision_tokens != 2048)
    details = build_details(parent, bundle, sources)
    assert details["coverage"]["deduplicated_transition_counts"] == {"repaired": 1}
    assert build_details(parent, bundle, sources) == details
    left, right = [build_request(parent, bundle, details, arm=arm) for arm in ARMS]
    assert left["max_tokens"] == right["max_tokens"] == 2048  # Updater remains separate.
    assert left["system"] == right["system"] and left["evidence_catalog"] == right["evidence_catalog"]
    luser, ruser = json.loads(left["user"]), json.loads(right["user"])
    assert luser.pop("public_repair_annex") == []
    ruser.pop("public_repair_annex")
    assert luser == ruser and SECRET not in right["system"] + right["user"]


@pytest.mark.parametrize("transition,draft_timeout,attempted_timeout,attempt_transition,decision", [
    ("repaired", True, False, "unknown", "revised"),
    ("deteriorated", False, False, "deteriorated", "retained"),
    ("deteriorated", False, True, "unknown", "retained"),
])
def test_4096_compact_feedback_preserves_timeout_and_rejected_attempts(
        tmp_path, monkeypatch, transition, draft_timeout, attempted_timeout, attempt_transition, decision):
    parent, bundle, sources, _ = output_options_source(tmp_path, monkeypatch, transition=transition,
        draft_timeout=draft_timeout, attempted_timeout=attempted_timeout)
    details = build_details(parent, bundle, sources)
    item = details["annex"][0]["shared_trajectory"]
    assert item["revision_decision"] == decision and item["attempt_transition"] == attempt_transition
    assert item["selected_public_check"]["status"] == "pass"
    attempt = item["attempted_revision"]
    assert attempt["solution.py"] == REVISED and attempt["selected"] == (decision == "revised")
    assert details["coverage"]["deduplicated_attempt_transition_counts"] == {attempt_transition: 1}
    assert details["coverage"]["deduplicated_transition_counts"] == {"unknown" if draft_timeout else "stable": 1}
    timeout_check = item["draft"]["public_check"] if draft_timeout else attempt["public_check"]
    if draft_timeout or attempted_timeout:
        observation = timeout_check["observations"][0]
        assert observation["observed"] is None and observation["semantic_outcome"] == "unknown"
        assert observation["observation_status"] == "execution_budget_exceeded"
        assert observation["execution_budget_seconds"] == 10
    assert all(source["revision"]["revision_opportunity_completed"] for source in sources)


@pytest.mark.parametrize("change", ["missing_cap", "missing_format", "cap_mismatch", "canonical_cap",
                                   "canonical_format", "bool_cap", "foreign_format", "system", "receipt_cap"])
def test_initial_output_declaration_and_prompt_cannot_be_resealed_inconsistently(tmp_path, monkeypatch, change):
    from skillopt.skill_validation.public_repair_feedback import _artifact, _initial
    _, _, sources, rows = output_options_source(tmp_path, monkeypatch)
    initial = deepcopy(sources[0]["initial"])
    if change in {"missing_cap", "missing_format"}:
        initial.pop("max_tokens" if change == "missing_cap" else "format_policy")
    elif change in {"cap_mismatch", "canonical_cap", "bool_cap"}:
        initial["max_tokens"] = {"cap_mismatch": 8192, "canonical_cap": 2048, "bool_cap": True}[change]
    elif change in {"canonical_format", "foreign_format"}:
        initial["format_policy"] = None if change == "canonical_format" else "other-format"
    else:
        request = initial["api_receipt"]["request"]
        request["system" if change == "system" else "max_tokens"] = "different instructions" if change == "system" else 8192
        initial["api_receipt"]["request_hash"] = digest(request)
    with pytest.raises(ValueError):
        _initial(reseal(initial), _artifact(sources[0]["draft"]), rows[0]["task"],
                 SourceFile.from_dict(rows[0]["public_wrapper"]), "")


@pytest.mark.parametrize("change", ["missing_cap", "missing_format", "cap_mismatch", "canonical_cap",
                                   "canonical_format", "bool_cap", "foreign_format"])
def test_revision_output_declaration_cannot_be_removed_or_changed(tmp_path, monkeypatch, change):
    parent, bundle, sources, _ = output_options_source(tmp_path, monkeypatch)
    bad = deepcopy(sources)
    request = bad[0]["revision"]["request"]
    if change in {"missing_cap", "missing_format"}:
        request.pop("max_tokens" if change == "missing_cap" else "format_policy")
    elif change in {"cap_mismatch", "canonical_cap", "bool_cap"}:
        request["max_tokens"] = {"cap_mismatch": 8192, "canonical_cap": 2048, "bool_cap": True}[change]
    else:
        request["format_policy"] = None if change == "canonical_format" else "other-format"
    bad[0]["revision"] = reseal(bad[0]["revision"])
    bad[0]["result"]["revision_hash"] = bad[0]["revision"]["record_hash"]
    bad[0]["result"] = reseal(bad[0]["result"])
    with pytest.raises(ValueError):
        build_details(parent, bundle, bad)


def profiled_source(tmp_path, monkeypatch, *, max_tokens=4096, health_policy="completed_response_v1"):
    """Actual rule-solver options with fabricated model/execution receipts."""
    from skillopt.skill_validation.solver_profile import SolverProfile

    original_solve, original_calls = solve_rule_condition, Calls
    profile = SolverProfile.named("reliable_v1", max_tokens)

    def solve(*args, **kwargs):
        return original_solve(*args, **kwargs, solver_profile=profile)

    class ProfileCalls(original_calls):
        def __init__(self, transition):
            super().__init__(transition)
            self.output_token_limits = profile.output_token_limits()
            if health_policy is not None:
                self.api.service["initial_health_policy"] = health_policy

    module = __import__(__name__, fromlist=["solve_rule_condition", "Calls"])
    monkeypatch.setattr(module, "solve_rule_condition", solve)
    monkeypatch.setattr(module, "Calls", ProfileCalls)
    return fixture_source(tmp_path, ("repaired",))


@pytest.mark.parametrize("max_tokens", [2048, 4096])
def test_registered_solver_profile_matches_both_generation_stages(tmp_path, monkeypatch, max_tokens):
    from skillopt.skill_validation.solver_profile import SolverProfile
    parent, bundle, sources, _ = profiled_source(tmp_path, monkeypatch, max_tokens=max_tokens)
    assert all(source["exposure"]["solver_profile"] == SolverProfile.named("reliable_v1", max_tokens).to_dict()
               for source in sources)
    details = build_details(parent, bundle, sources)
    assert details["coverage"]["deduplicated_transition_counts"] == {"repaired": 1}
    request = build_request(parent, bundle, details, arm="trajectory")
    assert request["max_tokens"] == 2048
    assert "solver_profile" not in request["user"] and SECRET not in request["user"]


@pytest.mark.parametrize("change", ["missing", "extra", "revision_cap", "format", "clean_timeout",
                                   "cap", "health", "legacy"])
def test_resealed_profile_cannot_override_actual_generation_controls(tmp_path, monkeypatch, change):
    from skillopt.skill_validation.solver_profile import SolverProfile
    parent, bundle, sources, _ = profiled_source(tmp_path, monkeypatch)
    bad = deepcopy(sources)
    exposure = bad[0]["exposure"]
    profile = exposure["solver_profile"]
    if change == "missing":
        profile.pop("initial_max_tokens")
    elif change == "extra":
        profile["unregistered_option"] = True
    elif change == "cap":
        exposure["solver_profile"] = SolverProfile.named("reliable_v1", 8192).to_dict()
    elif change == "legacy":
        exposure["solver_profile"] = SolverProfile.named().to_dict()
    else:
        field, value = {"revision_cap": ("revision_max_tokens", 8192),
                        "format": ("format_policy", None),
                        "clean_timeout": ("allow_clean_timeout_revision", False),
                        "health": ("initial_health_policy", "legacy_success_only")}[change]
        profile[field] = value
    bad[0]["exposure"] = reseal(exposure)
    bad[0]["result"]["exposure_hash"] = bad[0]["exposure"]["record_hash"]
    bad[0]["result"] = reseal(bad[0]["result"])
    with pytest.raises(ValueError, match="solver profile"):
        build_details(parent, bundle, bad)


@pytest.mark.parametrize("health_policy", [None, "legacy_success_only"])
def test_profile_requires_declared_api_health_policy_not_only_solver_tokens(tmp_path, monkeypatch, health_policy):
    with pytest.raises(ValueError, match="solver profile"):
        parent, bundle, sources, _ = profiled_source(tmp_path, monkeypatch, health_policy=health_policy)
        build_details(parent, bundle, sources)
    assert not list(tmp_path.rglob("rule_exposure.json"))


@pytest.mark.parametrize("health_policy", [None, "legacy_success_only"])
def test_frozen_profile_service_tamper_is_rejected_by_feedback_replay(tmp_path, monkeypatch, health_policy):
    parent, bundle, sources, _ = profiled_source(tmp_path, monkeypatch)
    bad = deepcopy(sources)
    exposure = bad[0]["exposure"]
    service = dict(exposure["service"])
    if health_policy is None:
        service.pop("initial_health_policy")
    else:
        service["initial_health_policy"] = health_policy
    exposure["service"] = service
    bad[0]["exposure"] = reseal(exposure)
    bad[0]["result"]["exposure_hash"] = bad[0]["exposure"]["record_hash"]
    bad[0]["result"] = reseal(bad[0]["result"])
    with pytest.raises(ValueError, match="Draft exposure binding changed"):
        build_details(parent, bundle, bad)


@pytest.mark.parametrize("kind", ["api_fallback", "parse_fallback"])
def test_revision_delivery_failure_retains_confirmed_draft_outcome(tmp_path, kind):
    parent, bundle, sources, _ = fixture_source(tmp_path, (kind,))
    coverage = build_details(parent, bundle, sources)["coverage"]
    assert coverage["deduplicated_transition_counts"] == {"unresolved": 1}
    for r in coverage["positions"][0]["roles"].values():
        assert r["revision_decision"] == "fallback"
        assert r["revision_reason"] == ("api_failure_no_retry" if kind == "api_fallback" else "parse_failure_no_retry")
        assert r["draft_status"] == r["selected_status"] == "fail"
        assert not r["source_changed"]


def test_no_successful_repairs_is_normal_and_unknown_is_kept(tmp_path):
    parent, bundle, sources, _ = fixture_source(tmp_path, ("stable", "unknown"))
    details = build_details(parent, bundle, sources)
    assert details["coverage"]["deduplicated_transition_counts"] == {"stable": 1, "unknown": 1}
    result = propose(FixtureCalls("NO_UPDATE"), parent, bundle, details, arm="trajectory")
    assert result["status"] == "no_update" and result["fixture_only"]
    assert not result["semantic_support_verified"]


def test_strict_existing_parser_can_cite_new_shared_selected_catalog(tmp_path):
    parent, bundle, sources, _ = fixture_source(tmp_path)
    details = build_details(parent, bundle, sources)
    request = build_request(parent, bundle, details, arm="trajectory")
    raw = response(parent, details["selected_final_bundle"])
    result = propose(FixtureCalls(raw), parent, bundle, details, arm="trajectory")
    assert result["status"] == "candidate"
    assert result["update"]["request_hash"] == request["parser_request_hash"]
    assert not result["semantic_support_verified"] and not result["deployment_authorized"]


@pytest.mark.parametrize("change", ["missing", "duplicate", "different_role", "different_repeat", "wrong_parent",
                                     "wrong_task", "wrong_final", "wrong_source_hash", "wrong_report"])
def test_reject_source_binding_changes_before_any_proposal(tmp_path, change):
    parent, bundle, sources, _ = fixture_source(tmp_path)
    bad = deepcopy(sources)
    if change == "missing":
        bad.pop()
    elif change == "duplicate":
        bad.append(bad[0])
    elif change == "wrong_parent":
        parent = RuleSkill("other-history", ())
    elif change in {"different_role", "different_repeat", "wrong_task"}:
        field, value = {"different_role": ("condition", "candidate"), "different_repeat": ("repeat", 10),
                        "wrong_task": ("task_hash", digest("other"))}[change]
        bad[0]["draft"] = reseal({**bad[0]["draft"], field: value})
    elif change == "wrong_final":
        bad[0]["result"] = reseal({**bad[0]["result"], "artifact_hash": digest("other")})
    elif change == "wrong_source_hash":
        bad[0]["draft"] = reseal({**bad[0]["draft"], "source_hash": digest("other")})
    else:
        bad[0]["revision"]["draft_stage"]["report"]["status"] = "pass"
        bad[0]["revision"] = reseal(bad[0]["revision"])
    with pytest.raises(ValueError):
        build_details(parent, bundle, bad)


@pytest.mark.parametrize("change", ["counts", "selection", "annex", "foreign_field"])
def test_resealed_derived_tamper_is_rejected_by_full_replay(tmp_path, change):
    parent, bundle, sources, _ = fixture_source(tmp_path)
    details = build_details(parent, bundle, sources)
    if change == "counts":
        details["coverage"]["task_count"] += 1
    elif change == "selection":
        details["coverage"]["selected_pairs"] = []
    elif change == "annex":
        details["annex"][0]["shared_trajectory"]["draft"]["solution.py"] = "different"
    else:
        details["host_audit"] = SECRET
    with pytest.raises(ValueError, match="source replay"):
        build_request(parent, bundle, reseal(details), arm="trajectory")


def test_replay_order_independent_and_original_sources_unchanged(tmp_path):
    parent, bundle, sources, _ = fixture_source(tmp_path, repeats=2)
    before = deepcopy(sources)
    first = build_details(parent, bundle, sources)
    assert build_details(parent, bundle, tuple(reversed(sources))) == first
    assert sources == before
    assert build_request(parent, bundle, first, arm="trajectory") == build_request(parent, bundle, first, arm="trajectory")


def test_select_covers_strata_and_new_tasks_before_repeated_family(tmp_path):
    parent, bundle, sources, _ = fixture_source(tmp_path, repeats=2)
    details = build_details(parent, bundle, sources, detail_limit=5)
    assert len({r["task_slot"] for r in details["coverage"]["selected_pairs"]}) == 5
    assert len(details["annex"]) == 5
    with pytest.raises(ValueError):
        _select({}, {}, 0)


def test_selection_reserves_one_real_same_task_alternative_not_a_nearby_family():
    pairs = {("a", 0): {"no_skill": {"transition": "unresolved"}, "current": {"transition": "unresolved"}},
             ("a", 1): {"no_skill": {"transition": "stable"}, "current": {"transition": "stable"}},
             ("b", 0): {"no_skill": {"transition": "stable"}, "current": {"transition": "stable"}},
             ("c", 0): {"no_skill": {"transition": "unknown"}, "current": {"transition": "unknown"}},
             ("d", 0): {"no_skill": {"transition": "stable"}, "current": {"transition": "stable"}}}
    families = {k: k[0] for k in pairs}
    for pair in pairs.values():
        for row in pair.values():
            row.update(final_feedback_status="pass" if row["transition"] == "stable" else "unknown",
                       public_recheck_disagreement=False)
    selected = _select(pairs, families, 4)
    assert ("a", 0) in selected and ("a", 1) in selected
    assert selected.index(("a", 1)) > selected.index(("c", 0))
    for row in pairs["a", 1].values():
        row.update(final_feedback_status="unknown", public_recheck_disagreement=True)
    assert ("a", 1) not in _select(pairs, families, 4)


@pytest.mark.parametrize("output,ok,status", [("not JSON", True, "invalid"), ("NO_UPDATE", True, "no_update"),
                                             (None, False, "api_failure")])
def test_proposal_failures_and_no_update_are_terminal_without_retry(tmp_path, output, ok, status):
    parent, bundle, sources, _ = fixture_source(tmp_path, ("stable",))
    details = build_details(parent, bundle, sources)
    calls = FixtureCalls(output, ok=ok)
    result = propose(calls, parent, bundle, details, arm="trajectory")
    assert result["status"] == status and len(calls.calls) == 1
    assert not result["retry_authorized"] and not result["deployment_authorized"]


def test_public_registration_rejects_extra_hidden_payload(tmp_path):
    parent, bundle, sources, _ = fixture_source(tmp_path, ("stable",))
    sources[0]["public_row"]["host_audit"] = SECRET
    with pytest.raises(ValueError, match="whitelisted"):
        build_details(parent, bundle, sources)


@pytest.mark.parametrize("change", ["MemoryError", "TimeoutError", "cleanup_false", "cleanup_missing"])
def test_legacy_unhealthy_revision_receipt_stops_replay_without_mutation_or_api(tmp_path, change):
    parent, bundle, sources, _ = fixture_source(tmp_path, ("repaired",))
    bad = deepcopy(sources)
    stage = bad[0]["revision"]["draft_stage"]
    receipt = stage["execution_records_host_only"][0]
    observed = receipt["execution"]
    if change in {"MemoryError", "TimeoutError"}:
        observed["exception"] = change
    elif change == "cleanup_false":
        observed["cleanup_confirmed"] = False
    else:
        observed.pop("cleanup_confirmed")
    receipt["execution"] = reseal(observed)
    stage["execution_records_host_only"][0] = reseal(receipt)
    # Preserve the old fail label: the guard must stop before semantic use,
    # even if a subsequent integrity check would reject this modified fixture.
    bad[0]["revision"]["draft_stage"] = reseal(stage)
    bad[0]["revision"] = reseal(bad[0]["revision"])
    before = deepcopy(bad)
    calls = FixtureCalls("NO_UPDATE")
    with pytest.raises(UnsupportedRepairEvidence, match="Unsupported"):
        details = build_details(parent, bundle, bad)
        propose(calls, parent, bundle, details, arm="trajectory")
    assert bad == before and not calls.calls
    assert bad[0]["revision"]["draft_stage"]["report"]["status"] == "fail"


def test_resource_guard_keeps_unobserved_placeholders_and_ordinary_exceptions():
    _require_supported_execution([seal({"execution": seal({"status": "unsupported", "reason": "not_executed"})})])
    _require_supported_execution([seal({"execution": seal({"status": "execution_error", "reason": "transport"})})])
    # Not every exception is an infrastructure failure; normal public
    # exception expectations remain the existing checker's responsibility.
    _require_supported_execution([seal({"execution": seal({"status": "observed", "exception": "ValueError",
                                                           "cleanup_confirmed": True})})])


def test_resource_guard_also_checks_complete_final_feedback(tmp_path, monkeypatch):
    from skillopt.skill_validation import public_repair_feedback as module
    parent, bundle, sources, _ = fixture_source(tmp_path, ("repaired",))
    bad = deepcopy(bundle)
    receipt = bad["execution_records"][0]
    receipt["execution"] = reseal({**receipt["execution"], "exception": "MemoryError"})
    bad["execution_records"][0] = reseal(receipt)
    # Isolate the added guard, not manufacture a second verifier report.
    monkeypatch.setattr(module, "build_update_request", lambda *a, **k: None)
    with pytest.raises(UnsupportedRepairEvidence, match="resource"):
        module.build_details(parent, bad, sources)


def test_budget_failure_is_not_silent_detail_truncation(tmp_path, monkeypatch):
    parent, bundle, sources, _ = fixture_source(tmp_path)
    details = build_details(parent, bundle, sources)
    monkeypatch.setattr("skillopt.skill_validation.public_repair_feedback.MAX_PROMPT_BYTES", 10)
    with pytest.raises(PromptBudgetExceeded) as error:
        build_request(parent, bundle, details, arm="trajectory")
    assert error.value.actual_bytes > error.value.limit_bytes
    assert len(details["annex"]) == 5


def test_script_preflight_never_constructs_api_and_preserves_replay_outputs(tmp_path, monkeypatch):
    from scripts import run_public_repair_feedback as script
    source, output = tmp_path / "source", tmp_path / "output"
    parent, bundle, _, rows = fixture_source(source)
    monkeypatch.setattr(script, "load_source", lambda _: (rows, {"h0": (parent, bundle)},
                        {"fixture": True, "source_service": {"fixture": True}}))
    monkeypatch.setattr(script, "CachedAPI", lambda *a, **k: (_ for _ in ()).throw(AssertionError("API forbidden")))
    first = script.run(tmp_path, source, output)
    assert first["status"] == "preflight_complete" and first["model_calls"] == 0
    assert first["proposed_call_limit"] == 4
    assert not (output / "api").exists()
    saved = (output / "histories/h0/details.json").read_bytes()
    assert script.run(tmp_path, source, output) == first
    assert (output / "histories/h0/details.json").read_bytes() == saved
    with pytest.raises(ValueError, match="Immutable"):
        script.run(tmp_path, source, output, detail_limit=5)


def test_script_loader_never_accesses_confirmation_paths(tmp_path, monkeypatch):
    from scripts import run_public_repair_feedback as script
    parent, bundle, sources, rows = fixture_source(tmp_path)
    original = script._read
    read_paths = []
    def read(path):
        assert "/confirmation" not in str(path) and "/host_only" not in str(path)
        read_paths.append(path)
        return original(path)
    monkeypatch.setattr(script, "_read", read)
    loaded = script.load_sources(tmp_path, "h0", rows, bundle)
    assert len(loaded) == len(sources) and len(read_paths) == 5 * len(sources) + 1
    assert build_details(parent, bundle, loaded) == build_details(parent, bundle, sources)


@pytest.mark.parametrize("change", ["model", "provider", "proxy", "temperature", "missing_health", None])
def test_script_requires_exact_source_service_plus_opt_in_policy_before_calls(tmp_path, monkeypatch, change):
    from scripts import run_public_repair_feedback as script
    source, output = tmp_path / "source", tmp_path / "output"
    parent, bundle, _, rows = fixture_source(source, ("stable",))
    service = {"fixture": True, "model": "fixture-no-model", "provider": "FIXTURE",
               "temperature": 0, "proxy": None}
    monkeypatch.setattr(script, "load_source", lambda _: (rows, {"h0": (parent, bundle)},
                        {"fixture": True, "source_service": service}))
    class API:
        def __init__(self, *args, **kwargs):
            assert kwargs["initial_health_policy"] == "completed_response_v1"
            self.service = {**service, "initial_health_policy": "completed_response_v1"}
            if change == "missing_health":
                self.service.pop("initial_health_policy")
            elif change is not None:
                self.service[change] = "different"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False
    def no_call(*args, **kwargs):
        raise AssertionError("matching_service_reached_budget_without_network")
    monkeypatch.setattr(script, "CachedAPI", API)
    monkeypatch.setattr(script, "BoundedCalls", no_call)
    if change is None:
        with pytest.raises(AssertionError, match="matching_service"):
            script.run(tmp_path, source, output, run_proposals=True)
    else:
        with pytest.raises(ValueError, match="source service"):
            script.run(tmp_path, source, output, run_proposals=True)
        assert not (output / "budget").exists()
