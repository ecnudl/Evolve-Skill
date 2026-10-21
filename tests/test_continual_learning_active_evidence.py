"""Learning v11 ``active_evidence`` controls: a round without any validation data, the frozen post-update decision,
the diagnosis arm (triage -> hypotheses -> graded checks -> authenticated reports), information boundaries and
replay guarantees (engineering fixtures; no method-effect claim)."""
import json
from copy import deepcopy

import pytest

from skillopt.active_evidence import METHOD, PROTOCOL
from skillopt.active_evidence import protocol as ae
from skillopt.active_evidence import updater
from skillopt.active_evidence.checks import parse_check_probes, state_test_source
from skillopt.active_evidence.stage import run_stage
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from skillopt.continual_learning.ledger import Ledger
from skillopt.validator_pilot.api import digest
from tests.test_continual_learning_domains import PRIVATE_CANARY, setup
from tests.test_continual_learning_verifier_v10 import API, TRAIN_PASS, executor

CHALLENGE_CANARY = "CHALLENGE_POOL_TASK_TEXT_NEVER_IN_A_DIAGNOSIS_OR_REFLECTION_PROMPT"
STEP = [str(i) for i in range(8)]
POOL = [f"c{i}" for i in range(12)]
# decision rule v2 on the 8-position fixture panel: 5 non-tied families all one way give p = 0.031 <= alpha
LIMITS = {**ae.DEFAULT_LIMITS, "fresh_tasks": 8, "replay_rows": 5, "local_fix_rows": 2, "min_paired_known": 8}
PRESERVE_PROMPT = "Return one. The input list is not modified."
INPLACE_PROMPT = "Return one. Sort the given list in place."
KEY = {"bigcodebench": "prompt", "searchqa": "question", "korbench": "rule", "spreadsheetbench": "instruction",
       "alfworld": "game_file"}


def _panel(benchmark="bigcodebench", *, pool=POOL, partition="development", prompt=None):
    _, base, _ = setup(benchmark)
    task = base["tasks"][0]
    if prompt is not None:
        task["public"]["prompt"] = prompt
    tasks = [{**deepcopy(task), "task_id": i, "family_id": i} for i in STEP]
    for i in pool:
        row = {**deepcopy(task), "task_id": i, "family_id": i, "partition": partition}
        row["public"] = {**row["public"], KEY[benchmark]: row["public"][KEY[benchmark]] + " " + CHALLENGE_CANARY}
        tasks.append(row)
    return {**base, "tasks": tasks}


def _args(*, arms, limits=None, budget=None):
    _, _, base = setup("bigcodebench")
    model = base["model"]
    model["transport"]["stream_wall_seconds"] = 3600
    full = {**base["budget"], "max_metric_calls": 400, "max_api_calls": 600, "max_reflection_calls": 40,
            "max_reported_tokens": 1_000_000, "max_verifier_calls": 100, "verifier_max_tokens": 100, **(budget or {})}
    return dict(step_families=list(STEP), challenge_families=list(POOL), model=model, budget=full, runtime={},
                parent_skill="", seed=7, arms=arms, limits={**LIMITS, **(limits or {})})


def evaluate(mode):
    """Step rows: fixed host outcomes whatever the Skill (controls); challenge rows: decided by the Skill under the
    named scenario. ``regress``: the candidate breaks step rows the parent passed."""
    def execute(task, skill):
        has = "requested constant" in skill
        if task["task_id"] in STEP:
            ok = task["task_id"] in TRAIN_PASS and not (mode == "regress" and has)
        else:
            ok = {"candidate_wins": has, "parent_wins": not has, "equal": True, "regress": has}[mode]
        return ({"status": "available", "output": "one" if ok else "zero", "reason": "fixture"},
                {"status": "pass" if ok else "fail", "score": float(ok), "reason": "fixture", "metrics": {}})
    return execute


CHALLENGE = {"feedback": "scalar", "post_update": "challenge_replay"}
PLAIN = {"feedback": "scalar", "post_update": "none"}
DIAGNOSIS = {"feedback": "diagnosis", "post_update": "none"}
DIAGNOSIS_CHALLENGE = {"feedback": "diagnosis", "post_update": "challenge_replay"}
STATE_PROBE = {"kind": "state", "calls": [{"args": [[3, 1, 2]], "kwargs": {}}],
               "expected": {"argument": 0, "relation": "unchanged"}, "obligation_id": "requested_behavior",
               "contract_quote": "The input list is not modified.", "rationale": "The contract preserves the input."}


class DiagnosisAPI(API):
    """Routes the mode's diagnoser and hypothesis-bound check payloads; review/judge fall back to the v10 fixture."""

    def __init__(self, *, probe=None, hypotheses=None, revised_keep=True, **kwargs):
        super().__init__(**kwargs)
        self.probe, self.hypotheses, self.revised_keep = probe, hypotheses, revised_keep

    def _verifier(self, payload):
        if "revision" in payload and "probes" in payload:  # the second review of a revised expectation
            return {"reviews": [{"index": i, "keep": self.revised_keep, "reason": "revised expectation reviewed",
                                 "fact_question": None} for i in range(len(payload["probes"]))]}
        if "batch_summary" in payload:
            cases = payload["cases"]
            fails = [c["case_id"] for c in cases if c["host_audit"]["status"] == "fail"]
            passes = [c["case_id"] for c in cases if c["host_audit"]["status"] == "pass"]
            if self.hypotheses is not None:
                return self.hypotheses(cases)
            return {"hypotheses": [{"id": "h1", "kind": "task_error_candidate",
                                    "statement": "The documented boundary return value is produced wrongly.",
                                    "mechanism": "Check the documented return value on a legal boundary input.",
                                    "applies_to": fails or [c["case_id"] for c in cases[:1]],
                                    "discriminating_observation": {"supports": "the boundary call returns another value",
                                                                   "excludes": "the boundary call returns the documented value"},
                                    "needs_fact": None, "preserve": passes}]}
        if "diagnostic_focus" in payload and "anonymous_implementation" in payload:
            probe = self.probe or {"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": self.probe_expected,
                                   "obligation_id": "requested_behavior", "contract_quote": "Return one.",
                                   "rationale": "The contract fixes the return value."}
            return {"probes": [{**probe, "hypothesis_id": "h1"}]}
        if "diagnostic_focus" in payload and "anonymous_response" in payload:
            verdict = "fail" if payload["anonymous_response"] == self.judge_fail_on else "pass"
            quote = payload["task"].get("question") or payload["task"]["rule"]
            return {"checks": [{"obligation": "[h1] answer form", "contract_quote": quote, "verdict": verdict,
                                "evidence": payload["anonymous_response"][:50]}]}
        return super()._verifier(payload)


def _run(tmp_path, *, mode="candidate_wins", arms=CHALLENGE, api=None, panel=None, probe_executor=None, evaluator=None,
         **kwargs):
    panel = panel or _panel()
    value = ae.manifest(panel, **_args(arms=arms, **kwargs))
    api = api or API()
    result = run_stage(value, panel, tmp_path / "learning", fixture_api=api, fixture_evaluate=evaluator or evaluate(mode),
                       fixture_probe_executor=probe_executor)
    return value, panel, api, result


# ----------------------------------------------------------------------------- protocol
def test_manifest_has_no_selection_role_and_round_trips():
    panel = _panel()
    value = ae.manifest(panel, **_args(arms=CHALLENGE))
    assert value["selection_families"] == [] and value["method"] == "rubric_research"  # compatibility record
    assert value["active_evidence"]["protocol"] == PROTOCOL and value["active_evidence"]["method"] == METHOD
    assert set(value["authorized_tasks"].values()) == {"train"}
    assert value["active_evidence"]["step_families"] == sorted(STEP)
    assert value["active_evidence"]["challenge_families"] == sorted(POOL)
    assert ae.validate_manifest(value, panel) == value
    tampered = {**value, "active_evidence": {**value["active_evidence"], "limits": {**LIMITS, "decision_alpha_permille": 100}}}
    with pytest.raises(ValueError):
        ae.validate_manifest(tampered, panel)


def test_manifest_refuses_non_development_partitions_and_unsupported_domains():
    for partition in ("skill_confirmation", "final", "verifier_calibration"):
        with pytest.raises(ValueError, match="development"):
            ae.manifest(_panel(partition=partition), **_args(arms=CHALLENGE))
    with pytest.raises(ValueError, match="unsupported"):
        ae.manifest(_panel("spreadsheetbench"), **_args(arms=CHALLENGE))
    with pytest.raises(ValueError, match="nonempty challenge pool"):
        ae.manifest(_panel(pool=[]), **{**_args(arms=CHALLENGE), "challenge_families": []})
    with pytest.raises(ValueError, match="overlap"):
        ae.manifest(_panel(), **{**_args(arms=CHALLENGE), "challenge_families": [*POOL, STEP[0]]})
    with pytest.raises(ValueError, match="collide"):
        ae.manifest(_panel(), **_args(arms=CHALLENGE, budget={"max_iterations": 1000}))


# ----------------------------------------------------------------------------- scalar arm + challenge
def test_round_without_validation_data_keeps_a_winning_candidate(tmp_path):
    value, panel, api, result = _run(tmp_path)
    assert result["status"] == "completed", result["reason"]
    assert result["decisions"] == ["keep"] and "requested constant" in result["candidate_skill"]
    assert result["method"] == METHOD and result["protocol"] == PROTOCOL and result["accepted_steps"] == 1
    root = tmp_path / "learning"
    draw = read_json(root / "challenge/0/draw.json", sealed=True)
    outcome = read_json(root / "challenge/0/outcome.json", sealed=True)
    assert draw["frozen_before_candidate_evaluation"] and draw["candidate_hash"] == digest(result["candidate_skill"])
    assert len(draw["fresh"]) == 8 and len(draw["replay"]) == 5 and len(draw["local_fix"]) == 2
    step_hashes = {digest(t) for t in panel["tasks"] if t["task_id"] in STEP}
    assert not step_hashes & {e["task_hash"] for e in draw["fresh"]}
    fresh = outcome["summary"]["fresh"]
    assert (fresh["wins"], fresh["losses"], fresh["jointly_known"], fresh["net_wins"]) == (8, 0, 8, 8)
    assert fresh["strata"]["unseen_family"]["positions"] == 8 and fresh["strata"]["seen_family"]["positions"] == 0
    assert outcome["summary"]["replay"]["regressions"] == 0 and outcome["summary"]["local_fix"]["fixed"] == 0
    # both Skills re-solved every position under fresh rollout keys: new receipts bound to the candidate
    rows = [read_json(p, sealed=True) for p in (root / "evaluations").glob("*.json")]
    assert all(r["request"]["role"] == "train" for r in rows)
    candidate_rows = [r for r in rows if r["request"]["candidate_hash"] == digest({"skill": result["candidate_skill"]})]
    assert len(candidate_rows) == 15 and {r["request"]["rollout"] for r in candidate_rows} == {1001}
    current_rows = [r for r in rows if r["request"]["rollout"] == 1000]
    assert len(current_rows) == 15 and {r["request"]["candidate_hash"] for r in current_rows} == {digest({"skill": ""})}
    # decision rule v2: a balanced execution order per set (half parent-first, half candidate-first) is sealed, and
    # the family-level one-sided sign test on the fresh panel decides (8 improving families of 8: p = 1/256)
    order = outcome["execution_order"]
    assert order["version"] == "balanced_abba_v1"
    assert {k: (len(v["parent_first"]), len(v["candidate_first"])) for k, v in order["halves"].items()} == {
        "fresh": (4, 4), "replay": (3, 2), "local_fix": (1, 1)}
    assert sorted(order["halves"]["fresh"]["parent_first"] + order["halves"]["fresh"]["candidate_first"]) == list(range(8))
    decision = read_json(root / "challenge/0/decision.json", sealed=True)
    assert decision["rule_version"] == "active-evidence-decision-v2" and decision["limits"] == {"min_paired_known": 8, "alpha": 0.05}
    assert decision["reason"] == "fresh_gain_significant_with_aggregate_guard_and_adverse_completion"
    assert decision["inputs"]["fresh"]["families_improving"] == 8 and decision["inputs"]["fresh"]["family_p_value"] == 1 / 256
    assert decision["inputs"]["flags"] == {"replay_harm": False, "fresh_admissible": True, "fresh_harm": False,
                                           "fresh_gain": True, "aggregate_guard": True, "adverse_completion": True}
    assert decision["inputs"]["local_fix"]["decision_input"] is False
    assert {p["candidate"]["evidence_hash"] for p in outcome["positions"]}.isdisjoint(
        {p["current"]["evidence_hash"] for p in outcome["positions"]})
    # the balanced order assigns every row back to its own position: each side's evidence is that task's evaluation
    # under that Skill's rollout key
    by_hash = {r["record_hash"]: r["request"] for r in rows}
    for position in outcome["positions"]:
        for side, rollout in (("current", 1000), ("candidate", 1001)):
            request = by_hash[position[side]["evidence_hash"]]
            assert request["task_hash"] == position["task_hash"] and request["rollout"] == rollout
    # the challenge pool never reaches a diagnosis/reflection prompt (the solver necessarily sees what it solves)
    assert api.prompts["reflection"] and all(CHALLENGE_CANARY not in p for p in api.prompts["reflection"])
    assert not api.prompts["verifier"] and not api.prompts["solver"]
    chain = read_json(root / "chain/0.json", sealed=True)
    assert chain["intervened"] == {"research_consulted": False, "label_feedback": False, "research_new_information": False,
                                   "feedback_differs_from_scalar": False, "skill_changed": True, "challenge_delta": True,
                                   "decision": "keep", "screen_changed_selection": False}
    assert set(chain["never_shown_to_diagnosis_or_reflection"]["challenge_task_hashes"]) == {
        digest(t) for t in panel["tasks"] if t["task_id"] in POOL}
    assert 1 <= chain["edits"]["edit_count"] <= LIMITS["edit_budget"] and chain["reserve"]["positions"] == 15
    assert "started.json" in result["artifacts"] and "identity.json" in result["artifacts"]
    # replay: the identical sealed record with zero new calls
    calls = len(api.prompts["reflection"])
    again = run_stage(value, panel, root, fixture_api=api, fixture_evaluate=evaluate("candidate_wins"))
    assert again == result and len(api.prompts["reflection"]) == calls


def test_regressions_revert_and_inconclusive_parks(tmp_path):
    _, _, _, reverted = _run(tmp_path / "a", mode="regress")
    assert reverted["status"] == "completed" and reverted["decisions"] == ["revert"]
    assert reverted["candidate_skill"] == "" and reverted["accepted_steps"] == 0
    decision = read_json(tmp_path / "a/learning/challenge/0/decision.json", sealed=True)
    # five replay rows the parent passed, all lost by the candidate: one-sided harm p = 1/32 <= alpha
    assert decision["reason"] == "replay_harm_significant" and decision["inputs"]["replay_regressions"] == 5
    assert decision["inputs"]["replay"]["family_harm_p_value"] == 1 / 32 and decision["inputs"]["flags"]["fresh_gain"] is True
    _, _, _, parked = _run(tmp_path / "b", mode="equal")
    assert parked["status"] == "completed" and parked["decisions"] == ["park"] and parked["candidate_skill"] == ""
    decision = read_json(tmp_path / "b/learning/challenge/0/decision.json", sealed=True)
    assert decision["reason"] == "fresh_gain_not_significant" and decision["inputs"]["fresh"]["net_wins"] == 0
    assert decision["inputs"]["fresh"]["families_non_tied"] == 0 and decision["inputs"]["fresh"]["family_p_value"] == 1.0
    _, _, _, lost = _run(tmp_path / "c", mode="parent_wins")
    assert lost["decisions"] == ["revert"]
    assert read_json(tmp_path / "c/learning/challenge/0/decision.json", sealed=True)["reason"] == "fresh_harm_significant"


def test_accept_without_challenge_arm_runs_no_challenge(tmp_path):
    value, _, api, result = _run(tmp_path, arms=PLAIN)
    assert result["status"] == "completed" and result["decisions"] == ["accepted_without_challenge"]
    assert "requested constant" in result["candidate_skill"]
    assert not (tmp_path / "learning/challenge/0/draw.json").exists()
    rows = [read_json(p, sealed=True) for p in (tmp_path / "learning/evaluations").glob("*.json")]
    assert len(rows) == len(STEP) and {r["request"]["rollout"] for r in rows} == {0}


def test_missing_challenge_reserve_stops_pending_before_any_update(tmp_path):
    # 8 step rows + 28 challenge positions exceed the metric budget: the stage stops pending before the updater runs
    _, _, api, result = _run(tmp_path, budget={"max_metric_calls": 20})
    assert result["status"] == "pending" and result["reason"] == "challenge_budget_reserve_unavailable"
    assert result["candidate_skill"] == "" and result["decisions"] == [] and not api.prompts["reflection"]
    assert "record_hash" in result and result["costs"]["logical_calls"] == 0


def test_interrupted_stage_returns_a_complete_sealed_pending_record(tmp_path):
    panel = _panel()
    value = ae.manifest(panel, **_args(arms=CHALLENGE))
    root = tmp_path / "learning"
    write_json(root / "started.json", seal({"identity_hash": "x"}))
    result = run_stage(value, panel, root, fixture_api=API(), fixture_evaluate=evaluate("candidate_wins"))
    assert result["status"] == "pending" and result["reason"] == "interrupted_stage_no_automatic_resume"
    assert result["candidate_skill"] == "" and result["costs"]["logical_calls"] == 0 and "record_hash" in result
    assert result["artifacts"] and read_json(root / "result.json", sealed=True) == result  # durable, never resumed
    assert run_stage(value, panel, root, fixture_api=API(), fixture_evaluate=evaluate("candidate_wins")) == result


def test_no_update_proposal_is_recorded_without_a_challenge(tmp_path):
    class NoUpdate(API):
        def call(self, system, user, kind, key, *, max_tokens, repeat):
            receipt = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
            if kind.endswith("reflection"):
                receipt = {**receipt, "response": json.dumps({"batch_size": 2, "patch": {"reasoning": "none", "edits": []}})}
            return receipt
    _, _, _, result = _run(tmp_path, api=NoUpdate())
    assert result["status"] == "completed" and result["decisions"] == ["no_update"] and result["candidate_skill"] == ""
    assert not (tmp_path / "learning/challenge/0/draw.json").exists()
    assert read_json(tmp_path / "learning/chain/0.json", sealed=True)["intervened"]["skill_changed"] is False


def test_tampered_evidence_is_refused_on_replay(tmp_path):
    value, panel, api, result = _run(tmp_path)
    path = next((tmp_path / "learning/challenge/0").glob("outcome.json"))
    record = json.loads(path.read_text())
    record["summary"]["fresh"]["wins"] = 0
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        run_stage(value, panel, tmp_path / "learning", fixture_api=api, fixture_evaluate=evaluate("candidate_wins"))


def test_private_canary_never_reaches_a_prompt(tmp_path):
    _, panel, api, _ = _run(tmp_path)
    assert all(PRIVATE_CANARY in json.dumps(t["private"]) for t in panel["tasks"])
    assert all(PRIVATE_CANARY not in p for role in api.prompts.values() for p in role)


# ----------------------------------------------------------------------------- diagnosis arm
def test_diagnosis_arm_confirms_violations_and_preservation_with_authenticated_reports(tmp_path):
    api = DiagnosisAPI()
    value, panel, api, result = _run(tmp_path, arms=DIAGNOSIS, api=api, probe_executor=executor())
    assert result["status"] == "completed", result["reason"]
    assert result["decisions"] == ["accepted_without_challenge"] and result["steps"][0]["rows_with_evidence"] == 8
    root = tmp_path / "learning"
    summary = read_json(root / "diagnosis/0/summary.json", sealed=True)
    assert summary["status"] == "completed" and summary["grades"] == {"confirmed_preserved": 5, "confirmed_violation": 3}
    assert [o["verdict"] for o in summary["observations"]] == ["consistent"]  # tentative, never "confirmed cause"
    triage = read_json(root / "diagnosis/0/triage.json", sealed=True)
    assert triage["summary"]["counts"] == {"environment": 0, "delivery": 0, "host_fail": 3, "host_pass": 5}
    assert len(triage["cases"]) == 8 and {c["why"] for c in triage["cases"]} == {"failure", "success"}
    # the evidence reaches the analysts as graded items, on passed rows too; the summary is in the system prompt
    conversations = [read_json(p) for p in (root / "native/0/predictions").rglob("conversation.json")]
    notes = [c[2]["content"] for c in conversations]
    assert sum("CONFIRMED VIOLATION [h1]" in n for n in notes) == 3 and sum("CONFIRMED PRESERVED [h1]" in n for n in notes) == 5
    analyst = [p for p in api.prompts["reflection"] if "EVIDENCE REPORTS" in p]  # (merge/ranking calls differ)
    assert analyst and all("Diagnosis summary (this step)" in p and "Confirmed violations (executed checks): 3" in p
                           and "consistent with them: h1" in p and "consistency, not proof of cause" in p for p in analyst)
    assert all("Current rubric -- mechanism" not in p for p in analyst)  # the rubric is never a system rule
    # the reviewer never saw the output, the host status, the rationale or the hypothesis verdict
    reviews = [p for p in api.prompts["verifier"] if "Review verifier probes BEFORE execution" in p]
    assert reviews and all("zero" not in p.split("\n", 1)[1] and "host_audit" not in p and "withheld for blind review" in p
                           and "hypothesis_id" not in p.split("\n", 1)[1] for p in reviews)
    chain = read_json(root / "chain/0.json", sealed=True)
    assert chain["intervened"]["feedback_differs_from_scalar"] is True and chain["diagnosis_status"] == "completed"
    assert all(CHALLENGE_CANARY not in p and PRIVATE_CANARY not in p for role in api.prompts.values() for p in role)
    assert (root / "host_only/triage/0.json").exists()


def test_state_check_holds_only_where_the_contract_states_it(tmp_path):
    # explicit preservation contract: the state probe is admissible and its failure is a confirmed violation
    api = DiagnosisAPI(probe=STATE_PROBE)
    _, _, _, result = _run(tmp_path / "a", arms=DIAGNOSIS, api=api, panel=_panel(prompt=PRESERVE_PROMPT),
                           probe_executor=executor())
    assert result["status"] == "completed", result["reason"]
    summary = read_json(tmp_path / "a/learning/diagnosis/0/summary.json", sealed=True)
    assert summary["grades"] == {"confirmed_preserved": 5, "confirmed_violation": 3}
    checks = read_json(next((tmp_path / "a/learning/diagnosis/0/checks").glob("*.json")), sealed=True)["checks"]
    assert checks[0]["kind"] == "state" and checks[0]["executed"] is True
    # explicit in-place contract: the same constraint is NOT APPLICABLE, never executed, never hard feedback
    api = DiagnosisAPI(probe={**STATE_PROBE, "contract_quote": "Sort the given list in place."})
    _, _, _, result = _run(tmp_path / "b", arms=DIAGNOSIS, api=api, panel=_panel(prompt=INPLACE_PROMPT),
                           probe_executor=executor())
    summary = read_json(tmp_path / "b/learning/diagnosis/0/summary.json", sealed=True)
    assert summary["grades"] == {"not_applicable": 8} and summary["observations"][0]["verdict"] == "undecided"
    notes = [read_json(p)[2]["content"] for p in (tmp_path / "b/learning/native/0/predictions").rglob("conversation.json")]
    assert all("NOT APPLICABLE" in n and "CONFIRMED" not in n for n in notes)
    assert not (tmp_path / "b/learning/diagnosis/0/executions").exists()
    # an unstated contract: the probe is rejected the same way
    api = DiagnosisAPI(probe={**STATE_PROBE, "contract_quote": "Return one."})
    _, _, _, result = _run(tmp_path / "c", arms=DIAGNOSIS, api=api, probe_executor=executor())
    assert read_json(tmp_path / "c/learning/diagnosis/0/summary.json", sealed=True)["grades"] == {"not_applicable": 8}
    # 10/11 review: the NOT APPLICABLE record is built from the probe AS THE PARSER READ IT (a quote relocated to its
    # verbatim task line), so a surface variant of the quote no longer makes the record disappear
    api = DiagnosisAPI(probe={**STATE_PROBE, "contract_quote": "sort the given list in place"})
    _, _, _, result = _run(tmp_path / "d", arms=DIAGNOSIS, api=api, probe_executor=executor(),
                           panel=_panel(prompt="Return one.\nSort the given list in place."))
    assert read_json(tmp_path / "d/learning/diagnosis/0/summary.json", sealed=True)["grades"] == {"not_applicable": 8}
    record = read_json(next((tmp_path / "d/learning/diagnosis/0/checks").glob("*.json")), sealed=True)
    assert record["checks"][0]["contract_quote"] == "Sort the given list in place." and record["checks"][0]["hypothesis_id"] == "h1"


def test_state_harness_observes_argument_mutation():
    probes = [{**STATE_PROBE, "hypothesis_id": "h1"}]
    source = state_test_source("f", probes)
    assert "_vf_before = _vf_norm(_vf_args[0])" in source and "was modified" in source and "TestCases" in source
    scope = {}
    exec(source + "\ndef f(values):\n    values.sort()\n    return 1\n", scope)  # noqa: S102 - the harness under test
    import unittest
    result = unittest.TextTestRunner(stream=open("/dev/null", "w")).run(unittest.defaultTestLoader.loadTestsFromTestCase(scope["TestCases"]))
    assert len(result.failures) == 1 and "argument 0 was modified" in result.failures[0][1]


def test_unjustified_checks_never_become_hard_feedback(tmp_path):
    # dropped by the limited-blinding review -> pending, not executed
    api = DiagnosisAPI(review_keep=False)
    _, _, _, result = _run(tmp_path / "a", arms=DIAGNOSIS, api=api, probe_executor=executor())
    summary = read_json(tmp_path / "a/learning/diagnosis/0/summary.json", sealed=True)
    assert summary["grades"] == {"pending_explanation": 8} and not (tmp_path / "a/learning/diagnosis/0/executions").exists()
    # an unresolved fact question (no Research arm) -> unknown, not executed
    api = DiagnosisAPI(fact_question="Is the boundary return documented?")
    _, _, _, result = _run(tmp_path / "b", arms=DIAGNOSIS, api=api, probe_executor=executor())
    summary = read_json(tmp_path / "b/learning/diagnosis/0/summary.json", sealed=True)
    assert summary["grades"] == {"unknown": 8}
    # a fabricated quote or a non-requested obligation is rejected at parse time: no check, no evidence row
    for bad in ({"contract_quote": "Return two."}, {"obligation_id": "determinism"}):
        api = DiagnosisAPI(probe={"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": 1,
                                  "obligation_id": "requested_behavior", "contract_quote": "Return one.",
                                  "rationale": "x", **bad})
        _, _, _, result = _run(tmp_path / ("c" + bad.get("obligation_id", "q")), arms=DIAGNOSIS, api=api,
                               probe_executor=executor())
        assert result["status"] == "completed" and result["steps"][0]["rows_with_evidence"] == 0
    # a raised call is an error, never a violation
    api = DiagnosisAPI()
    _, _, _, result = _run(tmp_path / "e", arms=DIAGNOSIS, api=api, probe_executor=executor(fail_on=()))
    summary = read_json(tmp_path / "e/learning/diagnosis/0/summary.json", sealed=True)
    assert set(summary["grades"]) == {"confirmed_preserved"}  # the fixture executor passes everything here
    probes, rejected = parse_check_probes({"probes": [{**STATE_PROBE, "hypothesis_id": "h9"}]}, PRESERVE_PROMPT, {"h1"}, 2)
    assert not probes and "hypothesis_id" in rejected["0"]


def test_rejected_probe_reply_gets_one_repair_and_surface_variants_are_normalized(tmp_path):
    class RepairAPI(DiagnosisAPI):
        def _verifier(self, payload):
            if "diagnostic_focus" in payload and "anonymous_implementation" in payload:
                good = {"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": 1,
                        "obligation_id": "requested_behavior", "contract_quote": "Return one.", "rationale": "x",
                        "hypothesis_id": "H1", "select": None, "index": 0}  # surface variants: normalized
                if "repair" in payload:
                    assert "rejected" in payload["repair"] and "previous_reply" in payload["repair"]
                    return {"probes": [good]}
                return {"probes": [{**good, "contract_quote": "Return two."}]}  # rejected: quote not in the task
            return super()._verifier(payload)
    api = RepairAPI()
    _, _, _, result = _run(tmp_path, arms=DIAGNOSIS, api=api, probe_executor=executor())
    assert result["status"] == "completed", result["reason"]
    record = read_json(next((tmp_path / "learning/diagnosis/0/checks").glob("*.json")), sealed=True)
    assert record["rejected"]["parse"] and record["rejected"]["repair"] == {} and len(record["checks"]) == 1
    assert record["checks"][0]["hypothesis_id"] == "h1" and record["checks"][0]["executed"] is True
    assert sum("repair" in p for p in api.prompts["verifier"]) == 8  # one repair per case, never a second
    summary = read_json(tmp_path / "learning/diagnosis/0/summary.json", sealed=True)
    assert [o["verdict"] for o in summary["observations"]] == ["consistent"]


def test_unrouted_fact_needs_are_recorded_and_reported_as_unresolved(tmp_path):
    def hypotheses(cases):
        fails = [c["case_id"] for c in cases if c["host_audit"]["status"] == "fail"]
        passes = [c["case_id"] for c in cases if c["host_audit"]["status"] == "pass"]
        return {"hypotheses": [{"id": "h1", "kind": "task_error_candidate", "statement": "A keyword is rejected.",
                                "mechanism": "The call uses an undocumented keyword.", "applies_to": fails,
                                "discriminating_observation": {"supports": "raises", "excludes": "returns"},
                                "needs_fact": "Does the documented call accept this keyword?", "preserve": passes}]}
    # (a) an arm without Research: the need is recorded as never consulted and the analysts read it as unresolved
    api = DiagnosisAPI(hypotheses=hypotheses)
    _, _, _, result = _run(tmp_path / "a", arms=DIAGNOSIS, api=api, probe_executor=executor())
    assert result["status"] == "completed", result["reason"]
    summary = read_json(tmp_path / "a/learning/diagnosis/0/summary.json", sealed=True)
    need, = summary["fact_needs"]
    assert need["hypothesis_id"] == "h1" and need["status"] == "not_consulted:arm_without_research"
    assert need["resolved"] is False and need["checks"] == 8 and need["research_hashes"] == []
    assert summary["research_consulted"] is False and "Research did not resolve" in summary["summary_text"]
    chain = read_json(tmp_path / "a/learning/chain/0.json", sealed=True)
    assert chain["fact_needs"] == summary["fact_needs"] and chain["intervened"]["research_consulted"] is False
    analyst = [p for p in api.prompts["reflection"] if "EVIDENCE REPORTS" in p]
    assert analyst and all("do not encode them as rules" in p and "Does the documented call accept" in p for p in analyst)

    # (b) the Research arm, but no admissible check ever reaches a review: Research is never consulted, and the step
    # still tells the analysts so instead of staying silent (no reports, summary only)
    class NoProbeAPI(ResearchAPI):
        def _verifier(self, payload):
            if "diagnostic_focus" in payload and "anonymous_implementation" in payload:
                return {"probes": []}
            return super()._verifier(payload)
    api, fetch = NoProbeAPI(hypotheses=hypotheses), fetcher()
    _, _, _, result = _run_research(tmp_path / "b", api, fetch)
    assert result["status"] == "completed", result["reason"]
    summary = read_json(tmp_path / "b/learning/diagnosis/0/summary.json", sealed=True)
    assert summary["checks"] == [] and summary["research"] == [] and summary["research_consulted"] is False
    assert summary["fact_needs"][0]["status"] == "not_consulted:no_admissible_check" and fetch.calls == []
    assert summary["report_hashes"] == {} and "no_admissible_check" in summary["summary_text"]
    chain = read_json(tmp_path / "b/learning/chain/0.json", sealed=True)
    assert chain["intervened"]["feedback_differs_from_scalar"] is True and chain["reports"]["rows_with_evidence"] == 0


def test_fact_need_resolution_binds_to_the_hypothesis_own_checks(tmp_path):
    """Two hypotheses with fact needs share the failing cases; only h1's check raises a fact question and receives a
    documented resolution. h2 stays unresolved: a case's Research never resolves another hypothesis on that case."""
    def hypotheses(cases):
        fails = [c["case_id"] for c in cases if c["host_audit"]["status"] == "fail"]
        passes = [c["case_id"] for c in cases if c["host_audit"]["status"] == "pass"]
        base = {"kind": "task_error_candidate", "statement": "s", "mechanism": "m", "applies_to": fails,
                "discriminating_observation": {"supports": "a", "excludes": "b"}}
        return {"hypotheses": [{**base, "id": "h1", "needs_fact": "Is the empty call documented?", "preserve": []},
                               {**base, "id": "h2", "needs_fact": "Is the call with one argument documented?",
                                "preserve": passes}]}
    probe = {"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": 1, "obligation_id": "requested_behavior",
             "contract_quote": "Return one.", "rationale": "The contract fixes the return value."}

    class SharedCaseAPI(ResearchAPI):
        def _verifier(self, payload):
            if "diagnostic_focus" in payload and "anonymous_implementation" in payload:
                return {"probes": [{**probe, "hypothesis_id": "h1"},
                                   {**probe, "calls": [{"args": [1], "kwargs": {}}], "hypothesis_id": "h2"}]}
            if "probes" in payload and "reviews" not in payload and "revision" not in payload:  # limited-blinding review
                return {"reviews": [{"index": i, "keep": True, "reason": "legal input",
                                     "fact_question": QUESTION if p["calls"][0]["args"] == [] else None}
                                    for i, p in enumerate(payload["probes"])]}
            return super()._verifier(payload)
    api, fetch = SharedCaseAPI(hypotheses=hypotheses), fetcher()
    _, _, _, result = _run_research(tmp_path, api, fetch)
    assert result["status"] == "completed", result["reason"]
    summary = read_json(tmp_path / "learning/diagnosis/0/summary.json", sealed=True)
    # 10/11: the five passed cases are CONTROLS for the error hypothesis h1 (it claims the failed cases only), so h1's
    # check -- and its fact question -- is also raised on them: eight Research records instead of three
    assert summary["grades"]["confirmed_violation"] == 3 and len(summary["research"]) == 8
    assert len(summary["controls"]["assignment"]) == 5 and all(v == ["h1"] for v in summary["controls"]["assignment"].values())
    h1 = next(o for o in summary["observations"] if o["hypothesis_id"] == "h1")
    assert (h1["control_cases_assigned"], h1["control_cases_checked"], h1["control_cases_violated"], h1["verdict"]) == (5, 5, 0, "consistent")
    needs = {f["hypothesis_id"]: f for f in summary["fact_needs"]}
    assert needs["h1"]["status"] == "consulted:resolved" and needs["h1"]["resolved"] is True
    assert len(needs["h1"]["consulted_checks"]) == 8 and len(needs["h1"]["research_hashes"]) == 8
    assert needs["h2"]["status"] == "not_consulted:review_raised_no_fact_question" and needs["h2"]["resolved"] is False
    assert needs["h2"]["consulted_checks"] == [] and needs["h2"]["checks"] == 8 and needs["h2"]["research_hashes"] == []
    text = summary["summary_text"]
    assert "h2 [not_consulted:review_raised_no_fact_question]: Is the call with one argument" in text and "h1 [" not in text


def test_fact_need_routing_reasons_distinguish_rejected_and_dropped_checks(tmp_path):
    def hypotheses(cases):
        fails = [c["case_id"] for c in cases if c["host_audit"]["status"] == "fail"]
        return {"hypotheses": [{"id": "h1", "kind": "task_error_candidate", "statement": "s", "mechanism": "m",
                                "applies_to": fails, "discriminating_observation": {"supports": "a", "excludes": "b"},
                                "needs_fact": "Is the keyword documented?", "preserve": []}]}
    # (i) the only probe is a state cue the contract does not impose: recorded NOT APPLICABLE, never admitted
    api = ResearchAPI(hypotheses=hypotheses, probe={**STATE_PROBE, "contract_quote": "Return one."})
    _, _, _, result = _run_research(tmp_path / "a", api, fetcher())
    assert result["status"] == "completed", result["reason"]
    summary = read_json(tmp_path / "a/learning/diagnosis/0/summary.json", sealed=True)
    assert summary["grades"] == {"not_applicable": 8} and summary["research"] == []  # 3 failed + 5 control cases
    assert summary["fact_needs"][0]["status"] == "not_consulted:no_admissible_check"
    # (ii) the review drops the check while asking a fact question: the researcher takes kept questions only
    api = ResearchAPI(hypotheses=hypotheses, review_keep=False)
    _, _, _, result = _run_research(tmp_path / "b", api, fetcher())
    assert result["status"] == "completed", result["reason"]
    summary = read_json(tmp_path / "b/learning/diagnosis/0/summary.json", sealed=True)
    assert summary["research"] == [] and not (tmp_path / "b/learning/diagnosis/0/executions").exists()
    assert summary["fact_needs"][0]["status"] == "not_consulted:fact_question_only_on_dropped_checks"
    assert "fact_question_only_on_dropped_checks" in summary["summary_text"]


def test_summary_bound_keeps_the_unresolved_fact_caveats():
    from skillopt.active_evidence.reports import fact_needs, observations, render_summary
    cases = [{"case_id": f"case-{i}", "host_status": "fail" if i < 4 else "pass"} for i in range(8)]
    hyps = [{"id": f"h{i}", "kind": "task_error_candidate", "statement": "S" * 220, "mechanism": "M" * 200,
             "applies_to": [f"case-{i - 1}"], "preserve": [], "needs_fact": f"Question {i}? " + "q" * 150}
            for i in range(1, 5)]

    def check(i, grade, status, case):
        return {"check_id": f"c{i}-{case}", "hypothesis_id": f"h{i}" if i else None, "case_id": case, "evidence_hash": case,
                "host_status": status, "grade": grade, "assertion": "A" * 120, "contract_quote": "Q" * 80,
                "input_legality": {"reviewed": True, "keep": True, "fact_question": None}, "expected_basis": "contract",
                "research": None}
    checks = [check(1, "confirmed_violation", "fail", "case-0"), check(2, "confirmed_violation", "fail", "case-1"),
              check(3, "confirmed_preserved", "fail", "case-2"), check(4, "confirmed_preserved", "fail", "case-3")]
    checks += [check(0, "confirmed_preserved", "pass", f"case-{4 + i % 4}") for i in range(6)]
    needs = fact_needs(hyps, checks, [], arm="diagnosis")
    assert [n["status"] for n in needs] == ["not_consulted:arm_without_research"] * 4
    verdicts = observations(hyps, checks, cases)
    assert [v["verdict"] for v in verdicts] == ["consistent", "consistent", "not_observed", "not_observed"]
    limit = ae.DEFAULT_LIMITS["summary_chars"]
    full = render_summary(hyps, verdicts, checks, {"exceptions": "none"}, 10 ** 6, fact_needs=needs)
    assert len(full) > limit  # the statements alone exceed the default bound
    text = render_summary(hyps, verdicts, checks, {"exceptions": "none"}, limit, fact_needs=needs)
    assert len(text) <= limit + len(updater.TRUNCATION) and updater.TRUNCATION in text  # the updater's maximum
    assert "Research did not resolve" in text and "h1 [not_consulted:arm_without_research]: Question 1?" in text
    assert text.index("Unproven:") > text.index("Confirmed violations")
    for small in (200, 213, 214, 300, 700, 1200):  # every admissible bound stays within limit + one marker
        bounded = render_summary(hyps, verdicts, checks, {"exceptions": "none"}, small, fact_needs=needs)
        assert 0 < len(bounded) <= small + len(updater.TRUNCATION), (small, len(bounded))
        assert "Unproven:" in bounded
    # consulted checks that met different Research outcomes are aggregated, never reported by whichever comes first
    def consulted(case, basis):
        return {**check(1, "confirmed_preserved", "fail", case), "expected_basis": basis,
                "input_legality": {"reviewed": True, "keep": True, "fact_question": "q"}}
    records = [{"evidence_hash": "case-0", "status": "retrieval_failed", "record_hash": "ra", "new_information": False},
               {"evidence_hash": "case-1", "status": "resolved", "record_hash": "rb", "new_information": True}]
    for order in ([consulted("case-0", "contract"), consulted("case-1", "documentation")],
                  [consulted("case-1", "documentation"), consulted("case-0", "contract")]):
        need, = fact_needs(hyps[:1], order, records, arm="diagnosis_research")
        assert need["status"] == "consulted:mixed" and need["research_statuses"] == ["resolved", "retrieval_failed"]
        assert need["resolved"] is True and need["research_hashes"] == ["ra", "rb"]


def test_judged_domain_grades_at_most_pending(tmp_path):
    api = DiagnosisAPI()
    _, _, _, result = _run(tmp_path, arms=DIAGNOSIS, api=api, panel=_panel("korbench"), probe_executor=executor())
    assert result["status"] == "completed", result["reason"]
    summary = read_json(tmp_path / "learning/diagnosis/0/summary.json", sealed=True)
    assert summary["grades"] == {"pending_explanation": 8} and summary["observations"][0]["verdict"] == "undecided"
    notes = [read_json(p)[2]["content"] for p in (tmp_path / "learning/native/0/predictions").rglob("conversation.json")]
    # R1 (10/11): a judged check shows its verdict; its grade stays pending and nothing is "confirmed"
    assert all(("JUDGED PASS [h1] judged:" in n or "JUDGED FAIL [h1] judged:" in n) and "CONFIRMED" not in n for n in notes)
    assert sum("JUDGED FAIL [h1]" in n for n in notes) == 3 and sum("JUDGED PASS [h1]" in n for n in notes) == 5
    # the default fixture hypothesis CLAIMS the five passed cases (preserve), so they are claimed passes, not controls
    assert summary["judged_leads"] == [{"hypothesis_id": "h1", "judged_checks": 8, "judged_unknown_checks": 0, "fail_cases": 3,
                                        "fail_cases_with_judged_fail": 3, "control_cases_assigned": 0, "control_cases_judged": 0,
                                        "control_cases_with_judged_fail": 0, "control_cases_with_judged_unknown": 0,
                                        "claimed_pass_cases": 5, "claimed_pass_cases_with_judged_fail": 0}]
    text = summary["summary_text"]
    assert ("Judged leads (model judgments, nothing executed -- leads, not confirmed facts): h1: a judged check failed on 3 of 3 "
            "failed cases and on 0 of 0 judged passing controls (0 assigned); on 0 of 5 passed cases it claims") in text
    assert "no check could be executed here, so the absence of confirmed violations is NOT evidence" in text
    assert "prefer no change" not in text and "Reports cover 8 of 8 step rows; executed checks cover 0." in text
    # the rubric guides the checker only: its "exceptions" sentence (when the CHECKER abstains) is not quoted to the
    # analysts -- it used to come back as a solver rule "abstain rather than guess" in every SearchQA Skill
    assert "rubric says" not in text and "Abstain" not in text and "Exceptions" not in text
    assert all("rubric says" not in p and "Abstain when" not in p for p in api.prompts["reflection"])
    assert all("JUDGED FAIL / JUDGED PASS / JUDGED UNKNOWN" in p and "never evidence that an output was right" in p
               for p in api.prompts["reflection"] if "EVIDENCE REPORTS" in p)


def test_forged_reports_and_summaries_are_refused(tmp_path):
    api = DiagnosisAPI()
    value, panel, api, result = _run(tmp_path, arms=DIAGNOSIS, api=api, probe_executor=executor())
    root = tmp_path / "learning"
    ledger = Ledger(root, value, None)
    token = next(iter(read_json(root / "diagnosis/0/summary.json", sealed=True)["report_hashes"]))
    row = next(r for r in (read_json(p, sealed=True) for p in (root / "evaluations").glob("*.json")) if r["record_hash"] == token)
    task = next(t for t in panel["tasks"] if digest(t) == row["request"]["task_hash"])
    trace = {"Inputs": task["public"], "Generated Outputs": row["prediction"]["output"],
             "Feedback": {"status": row["score"]["status"], "score": row["score"]["score"], "evidence": "forged evidence"},
             "evidence_hash": token}
    forged = seal({"protocol": PROTOCOL, "manifest_hash": value["record_hash"], "step": 0, "evidence_hash": token,
                   "feedback": "forged evidence"})
    with pytest.raises(ValueError, match="differs from the sealed report"):
        updater.propose_with_evidence("", [trace], root / "forged", ledger, step=0, seed=1, minibatch_size=2,
                                      edit_budget=4, reports={token: forged})
    with pytest.raises(ValueError, match="sealed record"):
        updater.propose_with_evidence("", [{**trace, "Feedback": {"status": trace["Feedback"]["status"],
                                                                 "score": trace["Feedback"]["score"]}}],
                                      root / "forged2", ledger, step=0, seed=1, minibatch_size=2, edit_budget=4,
                                      summary="a forged summary")


# ----------------------------------------------------------------------------- research arm
RESEARCH = {"feedback": "diagnosis_research", "post_update": "none"}
DOC_URL = "https://docs.python.org/3.11/library/functions.html"
DOC_TEXT = ("Lorem ipsum dolor sit amet consectetur adipiscing elit. The builtin returns the documented constant one "
            "for an empty boundary call; this behavior is documented here for every version.")
QUESTION = "Is the boundary return documented?"
GOOD_QUOTE = "returns the documented constant one for an empty boundary call"
IRRELEVANT_QUOTE = "Lorem ipsum dolor sit amet consectetur adipiscing elit"


def fetcher(status="available"):
    calls = []

    def fetch(urls, root):
        calls.append(list(urls))
        if status != "available":
            return [{"source_id": digest(u)[:16], "url": u, "status": "retrieval_failed", "error_type": "Fixture"} for u in urls]
        return [{"source_id": digest([u, "fixture"])[:16], "url": u, "status": "available", "text": DOC_TEXT,
                 "text_sha256": digest(DOC_TEXT), "retrieved_text_sha256": digest(DOC_TEXT), "retrieved_utc": "fixture",
                 "source_version": "Python 3.11", "information_origin": "research_document"} for u in urls]
    fetch.calls = calls
    return fetch


class ResearchAPI(DiagnosisAPI):
    def __init__(self, *, urls=(DOC_URL,), resolution=None, **kwargs):
        super().__init__(fact_question=QUESTION, **kwargs)
        self.urls, self.resolution = list(urls), resolution or {}

    def _verifier(self, payload):
        if "fact_questions" in payload:
            return {"urls": self.urls}
        if "reviews" in payload and "sources" in payload:
            source = payload["sources"][0]["source_id"]
            row = {"index": 0, "keep": True, "revised_expected": None,
                   "citation": {"source_id": source, "quote": GOOD_QUOTE}, "reason": "documented", **self.resolution}
            if row.get("citation") is not None and "quote" in row["citation"]:
                row["citation"] = {"source_id": source, "quote": row["citation"]["quote"]}
            return {"resolutions": [row]}
        return super()._verifier(payload)


def test_research_resolves_a_fact_with_a_relevant_citation(tmp_path):
    api, fetch = ResearchAPI(), fetcher()
    _, _, _, result = _run_research(tmp_path, api, fetch)
    assert result["status"] == "completed", result["reason"]
    root = tmp_path / "learning"
    summary = read_json(root / "diagnosis/0/summary.json", sealed=True)
    assert summary["grades"] == {"confirmed_preserved": 5, "confirmed_violation": 3}
    assert summary["research_new_information"] is True and len(summary["research"]) == 8
    research = read_json(next((root / "diagnosis/0/research").glob("*.json")), sealed=True)
    assert research["status"] == "resolved" and research["documented"] == [0] and research["missing_facts"] == [QUESTION]
    assert research["resolutions"]["0"]["citation"]["quote"] == GOOD_QUOTE
    checks = read_json(next((root / "diagnosis/0/checks").glob("*.json")), sealed=True)["checks"]
    assert checks[0]["expected_basis"] == "documentation" and checks[0]["research"]["keep"] is True
    assert read_json(root / "chain/0.json", sealed=True)["intervened"]["research_new_information"] is True
    assert fetch.calls == [[DOC_URL]]  # fetched once per step, cached across the eight cases


def _run_research(tmp_path, api, fetch, panel=None):
    panel = panel or _panel()
    value = ae.manifest(panel, **_args(arms=RESEARCH))
    result = run_stage(value, panel, tmp_path / "learning", fixture_api=api, fixture_evaluate=evaluate("candidate_wins"),
                       fixture_probe_executor=executor(), fixture_fetcher=fetch)
    return value, panel, api, result


@pytest.mark.parametrize("name, api, fetch, status", [
    ("no_sources", lambda: ResearchAPI(urls=[]), fetcher, "no_sources_selected:ok"),
    ("retrieval_failed", lambda: ResearchAPI(), lambda: fetcher("failed"), "retrieval_failed"),
    ("irrelevant_citation", lambda: ResearchAPI(resolution={"citation": {"quote": IRRELEVANT_QUOTE}}), fetcher, "invalid_resolutions"),
    ("revised_without_citation", lambda: ResearchAPI(resolution={"revised_expected": 2, "citation": None}), fetcher, "invalid_resolutions"),
    ("kept_without_citation", lambda: ResearchAPI(resolution={"citation": None}), fetcher, "resolved"),
    ("fabricated_quote", lambda: ResearchAPI(resolution={"citation": {"quote": "this sentence is not in the page at all"}}), fetcher, "invalid_resolutions"),
])
def test_research_without_new_information_never_confirms(tmp_path, name, api, fetch, status):
    _, _, _, result = _run_research(tmp_path, api(), fetch())
    assert result["status"] == "completed", result["reason"]
    root = tmp_path / "learning"
    summary = read_json(root / "diagnosis/0/summary.json", sealed=True)
    assert summary["grades"] == {"unknown": 8} and summary["research_new_information"] is False
    research = read_json(next((root / "diagnosis/0/research").glob("*.json")), sealed=True)
    assert research["status"].startswith(status) and research["documented"] == []
    assert not (root / "diagnosis/0/executions").exists()


def test_research_revised_expectation_needs_re_admission_and_a_second_review(tmp_path):
    api = ResearchAPI(resolution={"revised_expected": 7})
    _, _, _, result = _run_research(tmp_path, api, fetcher())
    research = read_json(next((tmp_path / "learning/diagnosis/0/research").glob("*.json")), sealed=True)
    assert research["status"] == "resolved" and research["resolutions"]["0"]["revised"] is True and research["revised"] == [0]
    checks = read_json(next((tmp_path / "learning/diagnosis/0/checks").glob("*.json")), sealed=True)["checks"]
    assert "returns 7" in checks[0]["assertion"] and checks[0]["executed"] is True
    assert checks[0]["input_legality"]["revision_review"] == "revised expectation reviewed"  # the second review decided
    assert any("revision" in p for p in api.prompts["verifier"])
    # the second review drops the revised assertion: pending, never executed
    api = ResearchAPI(resolution={"revised_expected": 7}, revised_keep=False)
    _, _, _, result = _run_research(tmp_path / "d", api, fetcher())
    summary = read_json(tmp_path / "d/learning/diagnosis/0/summary.json", sealed=True)
    assert summary["grades"] == {"pending_explanation": 8} and not (tmp_path / "d/learning/diagnosis/0/executions").exists()
    api = ResearchAPI(resolution={"revised_expected": "ValueError"})  # an exception encoded as a value is refused
    _, _, _, result = _run_research(tmp_path / "x", api, fetcher())
    research = read_json(next((tmp_path / "x/learning/diagnosis/0/research").glob("*.json")), sealed=True)
    assert research["status"].startswith("invalid_resolutions")


def test_state_admission_is_negation_aware_and_in_place_failures_stay_pending(tmp_path):
    from skillopt.active_evidence.checks import NOT_APPLICABLE, _parse_state_probe

    def admitted(quote, relation):
        probe = {**STATE_PROBE, "contract_quote": quote, "expected": {"argument": 0, "relation": relation}}
        try:
            _parse_state_probe(probe, "Return one. " + quote)
            return True
        except ValueError as exc:
            assert str(exc).startswith(NOT_APPLICABLE)
            return False
    assert admitted("The input list is not modified.", "unchanged") and not admitted("The input list is not modified.", "changed")
    assert admitted("Sort the given list in place.", "changed") and not admitted("Sort the given list in place.", "unchanged")
    assert not admitted("Does not modify the input list in place.", "changed")  # negation: both cues -> ambiguous
    assert not admitted("The original list is sorted in place.", "unchanged")
    assert admitted("Leaves the provided list untouched.", "unchanged")
    assert not admitted("The original list is modified.", "unchanged") and not admitted("The original list is changed.", "unchanged")
    assert admitted("The original list is not modified.", "unchanged") and admitted("The original list remains unchanged.", "unchanged")
    # hypothesis inference: an explained case without any admissible check keeps the inference undecided
    from skillopt.active_evidence.reports import observations
    hyps = [{"id": "h1", "kind": "task_error_candidate", "applies_to": ["a", "b"], "preserve": []},
            {"id": "h2", "kind": "unexplained", "applies_to": ["a"], "preserve": []}]
    cases = [{"case_id": "a", "host_status": "pass"}, {"case_id": "b", "host_status": "fail"}]
    check = {"check_id": "a/0", "hypothesis_id": "h1", "case_id": "a", "host_status": "pass", "grade": "confirmed_preserved"}
    verdicts = observations(hyps, [check, {**check, "hypothesis_id": "h2"}], cases)
    assert verdicts[0]["verdict"] == "undecided" and verdicts[0]["uncovered_cases"] == 1 and verdicts[0]["from_checks"] == []
    assert verdicts[1]["verdict"] == "preserved" and verdicts[1]["from_checks"] == ["a/0"]
    both = observations(hyps[:1], [check, {**check, "check_id": "b/0", "case_id": "b", "host_status": "fail"}], cases)
    assert both[0]["verdict"] == "not_observed" and both[0]["from_checks"] == ["a/0", "b/0"]
    # exact snapshot comparison: a 1e-7 float change is a modification
    source = state_test_source("f", [{**STATE_PROBE, "calls": [{"args": [[1.0]], "kwargs": {}}], "hypothesis_id": "h1"}])
    scope = {}
    exec(source + "\ndef f(values):\n    values[0] += 1e-7\n    return 1\n", scope)  # noqa: S102
    import unittest
    result = unittest.TextTestRunner(stream=open("/dev/null", "w")).run(unittest.defaultTestLoader.loadTestsFromTestCase(scope["TestCases"]))
    assert len(result.failures) == 1
    # an in-place obligation whose argument stayed unchanged is ambiguous (already in its final state): pending
    from skillopt.active_evidence.checks import grade
    changed = {**STATE_PROBE, "expected": {"argument": 0, "relation": "changed"}}
    review = {"keep": True, "reason": "x", "fact_question": None}
    assert grade(executed=True, outcome="fail", review=review, basis="contract", probe=changed) == "pending_explanation"
    assert grade(executed=True, outcome="fail", review=review, basis="contract", probe=STATE_PROBE) == "confirmed_violation"


def test_diagnosis_with_challenge_decides_on_fresh_tasks(tmp_path):
    api = DiagnosisAPI()
    _, _, _, result = _run(tmp_path, arms=DIAGNOSIS_CHALLENGE, api=api, probe_executor=executor())
    assert result["status"] == "completed", result["reason"]
    assert result["decisions"] == ["keep"] and result["steps"][0]["rows_with_evidence"] == 8
    chain = read_json(tmp_path / "learning/chain/0.json", sealed=True)
    assert chain["intervened"] == {"research_consulted": False, "label_feedback": False, "research_new_information": False,
                                   "feedback_differs_from_scalar": True, "skill_changed": True, "challenge_delta": True,
                                   "decision": "keep", "screen_changed_selection": False}
    assert all(CHALLENGE_CANARY not in p for role in ("verifier", "reflection") for p in api.prompts[role])


# ----------------------------------------------------------------------------- failure-message study (label feedback)
HIDDEN = {"feedback": "hidden_failure", "post_update": "matched_scalar_branch"}
STUDY_LIMITS = {"fresh_tasks": 8, "replay_rows": 0, "local_fix_rows": 0, "min_paired_known": 8}
FAKE_TRACEBACKS = {
    "test_case_3": ('Traceback (most recent call last):\n  File "/tmp/secret/__test__.py", line 31, in test_case_3\n'
                    '    pd.testing.assert_frame_equal(result, expected)\n'
                    '  File "/usr/local/lib/python3.10/site-packages/pandas/_testing/asserters.py", line 599, in raise_assert_detail\n'
                    '    raise AssertionError(msg)\nAssertionError: DataFrame.iloc[:, 0] (column name="0") are different\n\n'
                    '[left]:  [nan]\n[right]: [0.0]\nAt positional index 0, first diff: nan != 0.0\n'),
    "test_invalid_directory": ('Traceback (most recent call last):\n  File "/tmp/secret/__test__.py", line 40, in test_invalid_directory\n'
                               '    with self.assertRaises(FileNotFoundError):\nAssertionError: FileNotFoundError not raised\n'),
    "test_no_exception_line": "the scorer wrote something that is not a traceback\n",
}


def evaluate_with_hidden_details(mode):
    """The fixture host scorer with the native per-test tracebacks a BigCodeBench failure carries."""
    base = evaluate(mode)

    def execute(task, skill):
        prediction, score = base(task, skill)
        if score["status"] == "fail":
            score = {**score, "metrics": {"details": dict(FAKE_TRACEBACKS), "native_result": "fixture"}}
        return prediction, score
    return execute


class LabelAPI(API):
    """The message branch's analysts (label preamble in the system prompt) propose a different edit than the scalar
    branch; merge/rank calls follow the branch whose analysts were seen last (the stage runs M before S)."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.mode = "scalar"

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        role = kind.rsplit("-", 1)[-1]
        if role == "reflection":
            if "FAILURE-MESSAGE FEEDBACK" in system:
                self.mode = "label"
            elif "EVIDENCE REPORTS" in system:
                self.mode = "scalar"
        result = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if role == "reflection" and self.mode == "label":
            patch = {"reasoning": "The hidden tests complained that FileNotFoundError was not raised (test_invalid_directory).",
                     "edits": [{"op": "append", "content": "Raise the documented exception on invalid input instead of a sentinel."}]}
            result = {**result, "response": json.dumps({"batch_size": 2, "patch": patch})}
        return result


def test_failure_message_study_releases_bounded_messages_and_compares_matched_branches(tmp_path):
    from skillopt.active_evidence import label_feedback, matched

    panel = _panel()
    value = ae.manifest(panel, **_args(arms=HIDDEN, limits=STUDY_LIMITS))
    boundaries = value["active_evidence"]["information_boundaries"]
    assert boundaries["private_scoring_data"].startswith("label-feedback study arm") and boundaries["release_profile"] == ae.RELEASE_PROFILE
    assert value["active_evidence"]["limits"]["replay_rows"] == 0 and ae.default_limits(HIDDEN)["fresh_tasks"] == 242
    api = LabelAPI()
    root = tmp_path / "learning"
    result = run_stage(value, panel, root, fixture_api=api, fixture_evaluate=evaluate_with_hidden_details("candidate_wins"))
    assert result["status"] == "completed", result["reason"]
    # a study deploys nothing: the parent is carried whatever the decision says
    assert result["candidate_skill"] == "" and result["accepted_steps"] == 0 and len(result["decisions"]) == 1
    # release: the three failed step rows, two usable messages each (the third traceback has no exception line)
    audit = read_json(root / "diagnosis/0/release_audit.json", sealed=True)
    assert audit["delivered"] is True and audit["release_profile"] == label_feedback.RELEASE_PROFILE
    assert audit["denominators"] == {"step_rows": 8, "host_fail_rows": 3, "rows_with_details": 3, "rows_without_detail": 0,
                                     "rows_released": 3, "rows_withheld": 0, "tests_total": 9, "tests_omitted_by_cap": 0,
                                     "tests_withheld": 3, "tests_extracted": 6, "tests_shown": 6, "tests_cut_by_row_cap": 0,
                                     "tests_truncated": 0, "rows_truncated": 0, "rows_with_partial_last_entry": 0}
    assert audit["message_classes"]["value_diff"] == 3 and audit["message_classes"]["not_raised"] == 3
    assert audit["released_message_classes"] == audit["message_classes"]
    assert all(r["source_details_hash"] and r["released_payload_hash"] and r["tests_withheld"] == 1 and r["released"]
               for r in audit["rows"].values())
    summary = read_json(root / "diagnosis/0/summary.json", sealed=True)
    assert summary["status"] == "completed" and summary["information_release"] == label_feedback.INFORMATION_RELEASE
    assert summary["release_audit_hash"] == audit["record_hash"] and summary["hypotheses"] == [] and summary["research_consulted"] is False
    chain = read_json(root / "chain/0.json", sealed=True)
    assert set(summary["report_hashes"]) == set(chain["problem"]["host_fail"]) == set(summary["released_rows"])
    # the failed rows' native system turn (message branch) quotes the messages, never frames, paths or source lines
    notes = [c[2]["content"] for c in (read_json(p) for p in (root / "native/0/predictions").rglob("conversation.json"))]
    released = [n for n in notes if "HIDDEN TEST FAILURES" in n]
    assert len(released) == 3 and all("AssertionError: FileNotFoundError not raised" in n and "first diff: nan != 0.0" in n
                                      and "1 withheld" in n and 'File "' not in n and "/tmp" not in n
                                      and "site-packages" not in n and "assert_frame_equal" not in n for n in released)
    assert all("label feedback) follow" in n and "are not provided" not in n for n in released)
    assert sum("Hidden tests and expected answers are not provided" in n for n in notes) == 5  # passed rows
    # the matched scalar branch saw the same traces without any evidence and the scalar arm's exact package
    plain = [c[2]["content"] for c in (read_json(p) for p in (root / "native_matched/0/predictions").rglob("conversation.json"))]
    assert len(plain) == 8 and all("HIDDEN TEST" not in n and "are not provided" in n for n in plain)
    label_prompts = [p for p in api.prompts["reflection"] if "FAILURE-MESSAGE FEEDBACK" in p]
    scalar_prompts = [p for p in api.prompts["reflection"] if "EVIDENCE REPORTS" in p]
    assert label_prompts and scalar_prompts and all("HIDDEN TEST FAILURES" not in p for p in scalar_prompts)
    assert all("Diagnosis summary (this step)" in p and "Bounded development failure-message feedback" in p for p in label_prompts)
    identity = read_json(root / "native/0/identity.json", sealed=True)
    comparator_identity = read_json(root / "native_matched/0/identity.json", sealed=True)
    assert identity["label_feedback"] is True and identity["evidence_preamble"] == updater.LABEL_PREAMBLE_VERSION
    assert comparator_identity["label_feedback"] is False and comparator_identity["evidence_preamble"] == updater.EVIDENCE_PREAMBLE_VERSION
    assert comparator_identity["evidence_rows"] == 0 and identity["evidence_rows"] == 3
    # the study record: distinct candidates, both solved on the same drawn holdout, prespecified outcome class
    study = chain["matched"]
    assert study["candidates_identical"] is False and study["diff_lines"] > 0 and study["comparator"]["is_parent"] is False
    assert "requested constant" in read_json(root / "native_matched/0/result.json", sealed=True)["candidate_skill"]
    assert study["holdout"]["positions"] == 8 and study["holdout"]["jointly_known"] == 8
    outcome = study["outcome"]
    assert outcome["outcome"] == "harmful_change" and outcome["wins"] == 0 and outcome["losses"] == 8
    assert outcome["difference"]["interval"] == matched.INTERVAL and outcome["difference"]["ci95"][1] < 0
    assert outcome["sign_test_two_sided_p"] == pytest.approx(2 / 256, abs=1e-6) and outcome["unknown_positions"] == 0
    assert chain["intervened"]["label_feedback"] is True and chain["intervened"]["feedback_differs_from_scalar"] is True
    assert chain["information_release"] == label_feedback.INFORMATION_RELEASE and chain["release_audit_hash"] == audit["record_hash"]
    assert result["steps"][0]["matched_outcome"] == "harmful_change"
    outcome_record = read_json(root / "challenge/0/outcome.json", sealed=True)
    rows = [read_json(p, sealed=True) for p in (root / "evaluations").glob("*.json")]
    # study v2: the parent also solves the drawn holdout (reference key 1003) after both branches
    assert {r["request"]["rollout"] for r in rows} == {0, 1000, 1001, 1003}
    references = read_json(root / "challenge/0/references.json", sealed=True)
    assert references["status"] == "completed" and [r["name"] for r in references["references"]] == ["parent"]
    assert references["references"][0]["skill_hash"] == digest("") and references["outcome_hash"] == outcome_record["record_hash"]
    assert {r["request"]["candidate_hash"] for r in rows if r["request"]["rollout"] == 1003} == {digest({"skill": ""})}
    # fixture: the scalar branch's Skill passes every holdout task, the parent and the message branch none
    parent = study["references"]["by_reference"]["parent"]
    assert study["references"]["parent_bound"] is True and study["references"]["references_hash"] == references["record_hash"]
    assert parent["is_parent"] is True and (parent["pass"], parent["fail"], parent["unknown"]) == (0, 8, 0)
    assert parent["comparator_minus_reference"]["outcome"] == "useful_gain" and parent["comparator_minus_reference"]["wins"] == 8
    assert parent["treatment_minus_reference"]["outcome"] == "inconclusive" and parent["treatment_minus_reference"]["ties"] == 8
    # eight concordant pairs cannot show non-inferiority at a 0.05 margin (interval about +-0.32); 242 can
    assert parent["treatment_minus_reference"]["non_inferiority"] == {
        "margin": 0.05, "holds": False, "holds_with_unknowns_as_losses": False, "scope": "jointly known positions of this contrast"}
    # Codex round 1: 218 ties with 24 unknowns is non-inferior on the jointly known pairs only, not on the whole draw
    partial = matched.paired_class(0, 0, 218, 242, 218, estimand="x")
    assert partial["non_inferiority"]["holds"] is True and partial["non_inferiority"]["holds_with_unknowns_as_losses"] is False
    assert partial["difference"]["ci95"] == pytest.approx([-0.0173, 0.0173], abs=2e-4)
    assert partial["worst_case_unknowns_as_treatment_losses"]["ci95"] == pytest.approx([-0.1433, -0.0676], abs=2e-4)
    assert matched.paired_class(0, 0, 242, 242, 218, estimand="x")["non_inferiority"]["holds"] is True
    assert matched.paired_class(3, 12, 227, 242, 218, estimand="x")["non_inferiority"]["holds"] is False
    assert outcome["non_inferiority"]["holds"] is False and study["references"]["branch_pass"] == {"comparator": 8, "treatment": 0}
    assert {r["request"]["candidate_hash"] for r in rows if r["request"]["rollout"] == 1000} == {study["comparator"]["request_candidate_hash"]}
    assert {r["request"]["candidate_hash"] for r in rows if r["request"]["rollout"] == 1001} == {study["treatment"]["request_candidate_hash"]}
    assert study["treatment"]["skill_hash"] == chain["edits"]["candidate_hash"]
    assert outcome_record["summary"]["replay"]["positions"] == 0 and outcome_record["summary"]["local_fix"]["positions"] == 0
    assert all(CHALLENGE_CANARY not in p and PRIVATE_CANARY not in p for role in api.prompts.values() for p in role)
    assert not api.prompts["verifier"]  # zero diagnosis calls
    # replay: identical sealed records, zero new calls
    calls = len(api.prompts["reflection"])
    again = run_stage(value, panel, root, fixture_api=api, fixture_evaluate=evaluate_with_hidden_details("candidate_wins"))
    assert again == result and len(api.prompts["reflection"]) == calls


def test_failure_message_study_never_leaks_into_other_arms_and_stops_on_failed_delivery(tmp_path):
    from skillopt.active_evidence import label_feedback, matched

    # other arms: byte-identical analyst guidance, no hidden messages even when the scorer carries details
    value, panel, api, result = _run(tmp_path / "plain", arms=PLAIN, evaluator=evaluate_with_hidden_details("candidate_wins"))
    assert result["status"] == "completed" and all("HIDDEN TEST" not in p and "FAILURE-MESSAGE" not in p
                                                   for role in api.prompts.values() for p in role)
    assert value["active_evidence"]["information_boundaries"] == ae.INFORMATION_BOUNDARIES
    # the failure-message arm exists only as the study; the study needs a non-scalar treatment branch
    for arms in ({"feedback": "hidden_failure", "post_update": "none"}, {"feedback": "scalar", "post_update": "matched_scalar_branch"}):
        with pytest.raises(ValueError, match="matched-branch study"):
            ae.manifest(panel, **_args(arms=arms, limits=STUDY_LIMITS))
    # the method's own diagnosis package can be the treatment branch of the same matched design (nothing deployed)
    value, panel, api, result = _run(tmp_path / "diag-matched", arms={"feedback": "diagnosis", "post_update": "matched_scalar_branch"},
                                     api=DiagnosisAPI(), probe_executor=executor(), limits=STUDY_LIMITS)
    assert result["status"] == "completed", result["reason"]
    assert result["candidate_skill"] == "" and result["accepted_steps"] == 0
    study = read_json(tmp_path / "diag-matched/learning/chain/0.json", sealed=True)["matched"]
    assert study["outcome"]["outcome"] in ("failed_delivery", "useful_gain", "harmful_change", "inconclusive")
    assert study["delivery"]["status"] == "completed" and study["delivery"]["release_profile"] is None
    comparator_notes = [c[2]["content"] for c in (read_json(p) for p in (tmp_path / "diag-matched/learning/native_matched/0/predictions").rglob("conversation.json"))]
    treatment_notes = [c[2]["content"] for c in (read_json(p) for p in (tmp_path / "diag-matched/learning/native/0/predictions").rglob("conversation.json"))]
    assert len(comparator_notes) == 8 and all("CONFIRMED" not in n for n in comparator_notes)
    assert sum("CONFIRMED" in n for n in treatment_notes) == 8
    assert read_json(tmp_path / "diag-matched/learning/native/0/identity.json", sealed=True)["label_feedback"] is False
    with pytest.raises(ValueError, match="no replay or local-fix set"):  # the comparator never solved the step rows
        ae.manifest(panel, **_args(arms=HIDDEN, limits={**STUDY_LIMITS, "replay_rows": 4}))
    # a scorer without per-test detail: nothing can be released -> failed delivery BEFORE any updater call
    value, panel, api, result = _run(tmp_path / "bare", arms=HIDDEN, limits=STUDY_LIMITS)
    assert result["status"] == "pending" and result["reason"] == "label_feedback_failed_delivery"
    assert not api.prompts["reflection"] and result["candidate_skill"] == ""
    audit = read_json(tmp_path / "bare/learning/diagnosis/0/release_audit.json", sealed=True)
    assert audit["delivered"] is False and audit["denominators"]["rows_released"] == 0 and audit["denominators"]["host_fail_rows"] == 3
    summary = read_json(tmp_path / "bare/learning/diagnosis/0/summary.json", sealed=True)
    assert summary["status"] == "failed_delivery" and summary["summary_text"] is None and summary["released_rows"] == []
    # extraction policy: bounded, frame-free, path-free, multi-line messages kept; ambiguous or forbidden -> None
    text = label_feedback.failure_message(FAKE_TRACEBACKS["test_case_3"])
    assert text.startswith("AssertionError: DataFrame.iloc") and "[right]: [0.0]" in text and 'File "' not in text and "/usr" not in text
    assert label_feedback.failure_message(FAKE_TRACEBACKS["test_no_exception_line"]) is None
    assert label_feedback.failure_message("ValueError: bad\n    x = compute()\n") is None  # indented source line survives -> withheld
    assert label_feedback.failure_message("ValueError: see /etc/passwd now\n") == "ValueError: see <path> now"
    assert label_feedback.failure_message("ValueError: /[private] missing\n") == "ValueError: <path> missing"
    assert label_feedback.failure_message("ValueError: /<private> and /|private and '/q x'\n") == "ValueError: <path> and <path> and '<path> x'"
    assert label_feedback.forbidden_content("see /<private>") == "path" and label_feedback.forbidden_content("see <path>") is None
    assert label_feedback.failure_message("ZeroDivisionError: 1/2 and a/b stay, 100 / 2 stays\n") == "ZeroDivisionError: 1/2 and a/b stay, 100 / 2 stays"
    assert label_feedback.failure_message("ValueError: C:\\Users\\secret\\t.py missing\n") == "ValueError: <path> missing"
    assert label_feedback.failure_message("OSError: \\\\server\\share\\f.txt and ~/data/x.csv\n") == "OSError: <path> and <path>"
    long = {f"test_{i}": "x\n" * 5 + "ValueError: " + "v" * 1000 for i in range(9)}
    release = label_feedback.row_release(long, 1800)
    assert release["text"].startswith("HIDDEN TEST FAILURES") and "first 4 shown" in release["text"]
    assert len(release["text"]) <= 1800 + len(updater.TRUNCATION) and release["tests_truncated"] == 4 and not release["row_truncated"]
    assert (release["tests_total"], release["tests_omitted_by_cap"], release["tests_extracted"], release["tests_shown"]) == (9, 5, 4, 4)
    narrow = label_feedback.row_release(long, 600)  # the row cap cuts entries: only emitted entries count as shown
    assert len(narrow["text"]) == 600 + len(updater.TRUNCATION) and narrow["row_truncated"]
    assert narrow["tests_extracted"] == 4 and narrow["tests_shown"] == narrow["text"].count("\n- test_") == 2
    assert narrow["tests_cut_by_row_cap"] == 2 and narrow["last_entry_partial"] is True
    assert narrow["classes"]["typed_error"] == 2 and narrow["classes_extracted"]["typed_error"] == 4
    assert release["tests_cut_by_row_cap"] == 0 and release["last_entry_partial"] is False
    assert label_feedback.row_release({}, 1800) is None and label_feedback.row_release(None, 1800) is None
    nothing = label_feedback.row_release({"t": "no exception here"}, 1800)  # detail present, nothing releasable: counted
    assert nothing["text"] is None and nothing["withheld_reason"] == "no_releasable_message" and nothing["tests_withheld"] == 1
    bad_name = label_feedback.row_release({'File "/tmp/t.py"': "ValueError: y\n"}, 1800)  # a test NAME carrying a frame
    assert bad_name["text"] is None and bad_name["withheld_reason"].startswith("forbidden_content_in_row:") \
        and bad_name["tests_extracted"] == 1 and bad_name["tests_shown"] == 0
    # the prespecified statistics: McNemar at zero, the reviewer's sparse case, useful gain, inconclusive
    assert matched.tango_score(44, 26, 482, 0.0) == pytest.approx((44 - 26) / 70 ** 0.5)
    sparse = matched.paired_difference(6, 0, 218)
    assert sparse["ci95"][0] > 0 and sparse["ci95"][1] > 0.05  # a Wald interval would have excluded 0.05 here
    assert matched.paired_difference(0, 0, 218)["ci95"] == pytest.approx([-0.017316, 0.017316], abs=1e-5)
    gain = matched.outcome_class({"wins": 40, "losses": 20, "ties": 180, "jointly_known": 240, "positions": 242},
                                 delivered=True, candidates_identical=False, treatment_ready=True, min_paired_known=218)
    assert gain["outcome"] == "useful_gain" and gain["robust_to_unknowns"] is True and gain["unknown_positions"] == 2
    flat = matched.outcome_class({"wins": 12, "losses": 12, "ties": 216, "jointly_known": 240, "positions": 242},
                                 delivered=True, candidates_identical=False, treatment_ready=True, min_paired_known=218)
    assert flat["outcome"] == "inconclusive" and flat["reason"] == "worthwhile_gain_excluded"  # upper bound ~0.040 < 0.05
    wide = matched.outcome_class({"wins": 20, "losses": 15, "ties": 205, "jointly_known": 240, "positions": 242},
                                 delivered=True, candidates_identical=False, treatment_ready=True, min_paired_known=218)
    assert wide["outcome"] == "inconclusive" and wide["reason"] == "interval_includes_both" and wide["difference"]["ci95"][1] > 0.05
    thin = matched.outcome_class({"wins": 30, "losses": 0, "ties": 180, "jointly_known": 210, "positions": 242},
                                 delivered=True, candidates_identical=False, treatment_ready=True, min_paired_known=218)
    assert thin["outcome"] == "failed_delivery" and thin["reason"] == "insufficient_jointly_known_holdout_pairs"
    assert matched.outcome_class(None, delivered=True, candidates_identical=True, treatment_ready=True,
                                 min_paired_known=4)["reason"] == "identical_candidates"


def test_failure_message_study_records_identical_candidates_and_unknown_holdout_positions(tmp_path):
    from skillopt.active_evidence import matched

    # identical candidates (the base fixture analysts ignore the messages): a failed delivery of the contrast, the
    # holdout is still solved and recorded, nothing is deployed
    value, panel, api, result = _run(tmp_path / "same", arms=HIDDEN, limits=STUDY_LIMITS,
                                     evaluator=evaluate_with_hidden_details("candidate_wins"))
    assert result["status"] == "completed" and result["candidate_skill"] == "" and result["accepted_steps"] == 0
    chain = read_json(tmp_path / "same/learning/chain/0.json", sealed=True)
    study = chain["matched"]
    assert study["candidates_identical"] is True and study["diff_lines"] == 0
    assert study["outcome"] == {"outcome": "failed_delivery", "reason": "identical_candidates"}
    assert study["holdout"]["positions"] == 8 and chain["decision"]["action"] == "no_update"
    assert study["comparator"]["request_candidate_hash"] == study["treatment"]["request_candidate_hash"]
    assert result["steps"][0]["matched_outcome"] == "failed_delivery"
    # the inventory governs the comparator branch too: a stray file under native_matched breaks the replay
    (tmp_path / "same/learning/native_matched/0/stray.txt").write_text("x")
    with pytest.raises(ValueError, match="Learning evidence changed"):
        run_stage(value, panel, tmp_path / "same/learning", fixture_api=api,
                  fixture_evaluate=evaluate_with_hidden_details("candidate_wins"))
    # unknown holdout positions (the adapter's own unknown path is exercised by the v10 fixtures): above 10% of the
    # drawn positions the evaluation is a failed delivery, with the descriptive statistics and the worst-case
    # sensitivity still reported; the estimand stays the jointly known positions
    thin = matched.outcome_class({"wins": 30, "losses": 0, "ties": 180, "jointly_known": 210, "positions": 242},
                                 delivered=True, candidates_identical=False, treatment_ready=True, min_paired_known=218)
    assert thin["outcome"] == "failed_delivery" and thin["reason"] == "insufficient_jointly_known_holdout_pairs"
    assert thin["unknown_positions"] == 32 and thin["difference"]["estimate"] == pytest.approx(30 / 210)
    assert thin["difference"]["ci95"][0] > 0 and thin["worst_case_unknowns_as_treatment_losses"]["estimate"] == pytest.approx(-2 / 242, abs=1e-6)
    assert thin["sign_test_two_sided_p"] <= 1e-6 and "independence" in thin["independence_assumption"]


def test_failure_message_study_report_audits_and_budget_reserve(tmp_path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("report_ae", "scripts/report_active_evidence_stage.py")
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    # the zero-call study audits run on a finished study (attribution on reasoning fields, label echo, reuse overlap)
    value, panel, api, result = _run(tmp_path / "study", arms=HIDDEN, api=LabelAPI(), limits=STUDY_LIMITS,
                                     evaluator=evaluate_with_hidden_details("candidate_wins"))
    assert result["status"] == "completed", result["reason"]
    audits = report._study_audits(tmp_path / "study/learning", 0)
    assert audits["released_rows"] == 3 and audits["released_test_names"] == 2 and audits["released_exception_classes"] == ["AssertionError"]
    attribution = audits["attribution"]
    assert attribution["minibatch_proposal_reasoning"]["cites_test_names"] == 1 and attribution["minibatch_proposal_reasoning"]["mentions_failure_messages"]
    assert attribution["reasoning_texts"]["minibatch_files"] > 0
    assert attribution["mechanism"] in {"cited_in_selected_edits", "cited_in_minibatch_proposals_only"}
    assert audits["label_echo"] == {"literals_in_treatment_skill": 0, "test_names_in_treatment_skill": 0}
    assert report._study_audits(tmp_path / "study/learning", 1) is None  # no such step
    value2, panel2, api2, result2 = _run(tmp_path / "plain", arms=PLAIN, evaluator=evaluate_with_hidden_details("candidate_wins"))
    assert report._study_audits(tmp_path / "plain/learning", 0) is None  # no released report in another arm
    overlap = report.holdout_overlap(tmp_path / "study", [tmp_path / "study", tmp_path / "plain"])
    assert overlap["holdout_positions"] == 8 and overlap["overlap_by_prior_stage"]["study"] == 8
    assert 0 <= overlap["overlap_by_prior_stage"]["plain"] <= 8 and overlap["holdout_tasks_used_by_any_prior_stage"] == 8
    # the two-branch updater reserve: every analyst, every merge level and the ranking, each with one retry; it is
    # checked against the reflection cap and the API cap before the first updater call
    from skillopt.active_evidence.stage import _merge_calls
    assert [_merge_calls(n) for n in (0, 1, 2, 8, 9, 10, 65)] == [0, 0, 1, 1, 3, 3, 12]  # 65 -> 9 -> 2 -> 1
    for name, budget, reason in (("reflection", {"max_reflection_calls": 30}, "challenge_budget_reserve_unavailable"),
                                 ("api", {"max_api_calls": 60}, "challenge_budget_reserve_unavailable")):
        value3, panel3, api3, result3 = _run(tmp_path / ("tight-" + name), arms=HIDDEN, api=LabelAPI(),
                                             limits=STUDY_LIMITS, budget=budget,
                                             evaluator=evaluate_with_hidden_details("candidate_wins"))
        assert result3["status"] == "pending" and result3["reason"] == reason and not api3.prompts["reflection"]


def test_matched_study_solves_named_reference_skills_on_the_same_holdout(tmp_path):
    """Study v2: sealed evaluation-only reference Skills (e.g. a validation-gated baseline's Skill) solve the drawn
    holdout after both branches under their own rollout keys; they never reach an updater, diagnoser or deployment."""
    from skillopt.active_evidence import challenge, matched

    panel = _panel()
    good = {"name": "gated_baseline", "skill": "Baseline guidance: return the requested constant.",
            "source": {"stage": "/sealed/baseline", "skill_sha256": "0" * 64}}
    weak = {"name": "other_domain", "skill": "Guidance learned elsewhere.", "source": {"stage": "/sealed/other"}}
    # protocol: references belong to the study, are uniquely and safely named, bounded in number, and carry provenance
    for bad, message in (([{**good, "name": "parent"}], "unique lower-case name"), ([{**good, "name": "Bad Name"}], "unique"),
                         ([good, good], "unique"), ([{**good, "source": {}}], "provenance"),
                         ([{"name": "x", "skill": "y"}], "provenance"),
                         ([{**good, "name": f"r{i}"} for i in range(5)], "At most 4")):
        with pytest.raises(ValueError, match=message):
            ae.manifest(panel, **_args(arms=HIDDEN, limits=STUDY_LIMITS), reference_skills=bad)
    with pytest.raises(ValueError, match="belong to the matched-branch study"):
        ae.manifest(panel, **_args(arms=CHALLENGE), reference_skills=[good])
    value = ae.manifest(panel, **_args(arms=HIDDEN, limits=STUDY_LIMITS), reference_skills=[good, weak])
    assert ae.validate_manifest(value, panel) == value
    assert [r["name"] for r in value["active_evidence"]["reference_skills"]] == ["gated_baseline", "other_domain"]
    assert "holdout_references" in value["active_evidence"]["information_boundaries"]
    assert "holdout_references" not in ae.manifest(panel, **_args(arms=CHALLENGE))["active_evidence"]["information_boundaries"]
    api = LabelAPI()
    root = tmp_path / "learning"
    result = run_stage(value, panel, root, fixture_api=api, fixture_evaluate=evaluate_with_hidden_details("candidate_wins"))
    assert result["status"] == "completed" and result["candidate_skill"] == "" and result["accepted_steps"] == 0
    chain = read_json(root / "chain/0.json", sealed=True)
    assert chain["chain_version"] == "active-evidence-chain-v5" and chain["matched"]["study"] == matched.STUDY_VERSION
    record = read_json(root / "challenge/0/references.json", sealed=True)
    assert [(r["name"], r["rollout"]) for r in record["references"]] == [("parent", 1003), ("gated_baseline", 1004),
                                                                           ("other_domain", 1005)]
    assert record["evaluation_only"] is True and record["draw_hash"] == chain["challenge"]["draw_hash"]
    rows = [read_json(p, sealed=True) for p in (root / "evaluations").glob("*.json")]
    assert {r["request"]["rollout"] for r in rows} == {0, 1000, 1001, 1003, 1004, 1005}
    for name, rollout, skill in (("gated_baseline", 1004, good["skill"]), ("other_domain", 1005, weak["skill"])):
        hashes = {r["request"]["candidate_hash"] for r in rows if r["request"]["rollout"] == rollout}
        assert hashes == {digest({"skill": skill})} and sum(r["request"]["rollout"] == rollout for r in rows) == 8
    # every reference position is a drawn holdout task; none is a step row
    draw = read_json(root / "challenge/0/draw.json", sealed=True)
    assert [p["task_hash"] for p in record["positions"]] == [e["task_hash"] for e in draw["fresh"]]
    assert all(set(p["reference"]) == {"parent", "gated_baseline", "other_domain"} for p in record["positions"])
    by = chain["matched"]["references"]["by_reference"]
    # fixture: a Skill containing "requested constant" passes every holdout task (scalar branch and the gated
    # baseline), the others none -> the scalar branch ties the baseline and beats the parent and the other-domain Skill
    assert (by["gated_baseline"]["pass"], by["other_domain"]["pass"], by["parent"]["pass"]) == (8, 0, 0)
    assert by["gated_baseline"]["comparator_minus_reference"]["ties"] == 8
    assert by["gated_baseline"]["treatment_minus_reference"]["outcome"] == "harmful_change"
    assert by["other_domain"]["comparator_minus_reference"]["outcome"] == "useful_gain"
    assert by["gated_baseline"]["is_parent"] is False and by["parent"]["is_parent"] is True
    # instrument check: the gated baseline's (fixture) effect over the parent is visible on the same holdout
    assert by["gated_baseline"]["reference_minus_parent"]["outcome"] == "useful_gain"
    assert by["gated_baseline"]["reference_minus_parent"]["wins"] == 8 and "reference_minus_parent" not in by["parent"]
    assert by["other_domain"]["reference_minus_parent"]["ties"] == 8
    assert "gated_baseline" in by["gated_baseline"]["treatment_minus_reference"]["estimand"]
    # references never reach a model prompt as text to learn from: no reflection/verifier prompt quotes them
    assert all(good["skill"] not in p and weak["skill"] not in p for role in ("reflection", "verifier") for p in api.prompts[role])
    # the reserve counts the reference evaluations before any update expenditure
    assert chain["reserve"]["reference_evaluations"] == 3 * 8 and chain["reserve"]["metric_calls"] == 2 * 8 + 3 * 8
    # replay: identical records, zero new calls; a changed reference list is refused
    calls = sum(len(v) for v in api.prompts.values())
    again = run_stage(value, panel, root, fixture_api=api, fixture_evaluate=evaluate_with_hidden_details("candidate_wins"))
    assert again == result and sum(len(v) for v in api.prompts.values()) == calls
    with pytest.raises(ValueError, match="Too many reference Skills"):
        challenge.reference_rollout(0, 7)
    # a budget that cannot hold the reference evaluations stops the stage pending before any updater call
    tight = ae.manifest(panel, **_args(arms=HIDDEN, limits=STUDY_LIMITS, budget={"max_metric_calls": 8 + 2 * 8 + 2 * 8}),
                        reference_skills=[good, weak])
    api2 = LabelAPI()
    pending = run_stage(tight, panel, tmp_path / "tight", fixture_api=api2,
                        fixture_evaluate=evaluate_with_hidden_details("candidate_wins"))
    assert pending["status"] == "pending" and pending["reason"] == "challenge_budget_reserve_unavailable"
    assert not api2.prompts["reflection"]


DIAG_STUDY = {"feedback": "diagnosis", "post_update": "matched_scalar_branch"}
REFERENCE_CANARY = "REFERENCE_SKILL_TEXT_NEVER_IN_A_LEARNING_PROMPT"


class BrokenJudgeAPI(DiagnosisAPI):
    """The judge's check reply fails schema validation for the first ``broken`` cases (None: for every case)."""

    def __init__(self, broken=None, **kwargs):
        super().__init__(**kwargs)
        self.broken, self.judged = broken, 0

    def _verifier(self, payload):
        if "diagnostic_focus" in payload and "anonymous_response" in payload:
            self.judged += 1
            if self.broken is None or self.judged <= self.broken:
                return {"checks": "not a list"}
        return super()._verifier(payload)


def test_diagnosis_matched_study_on_a_judged_domain_with_references(tmp_path):
    """The method's own package as the treatment on a judged domain (no execution, no review, no Research): judge
    checks reach the analysts as pending items, the delivery is accounted, and a named reference Skill is solved on
    the holdout without ever entering a diagnoser, judge or analyst prompt."""
    from skillopt.active_evidence import challenge, matched

    panel = _panel("searchqa")
    ref = {"name": "gated_baseline", "skill": REFERENCE_CANARY + " Answer with the shortest exact entity.",
           "source": {"stage": "/sealed/gated"}}
    value = ae.manifest(panel, **_args(arms=DIAG_STUDY, limits=STUDY_LIMITS), reference_skills=[ref])
    api = DiagnosisAPI()
    root = tmp_path / "learning"
    result = run_stage(value, panel, root, fixture_api=api, fixture_evaluate=evaluate("candidate_wins"),
                       fixture_probe_executor=executor())
    assert result["status"] == "completed", result["reason"]
    assert result["candidate_skill"] == "" and result["accepted_steps"] == 0
    chain = read_json(root / "chain/0.json", sealed=True)
    delivery = chain["diagnosis_delivery"]
    assert delivery == {"cases": 8, "cases_attempted": 8, "cases_with_checks": 8, "cases_format_failed": 0,
                        "cases_without_checks": 0, "cases_skipped_for_reserve": 0, "cases_unassigned": 0,
                        "rows_with_reports": 8, "summary_present": True}
    study = chain["matched"]
    assert study["delivery"]["problem"] is None and study["delivery"]["diagnosis"] == delivery
    assert all(read_json(p, sealed=True)["delivery"] == "checks" for p in (root / "diagnosis/0/checks").glob("*.json"))
    summary = read_json(root / "diagnosis/0/summary.json", sealed=True)
    assert set(summary["grades"]) == {"pending_explanation"} and summary["research_consulted"] is False
    # the reference is solved on the drawn holdout; its text is in solver prompts only
    record = read_json(root / "challenge/0/references.json", sealed=True)
    assert [(r["name"], r["rollout"]) for r in record["references"]] == [("parent", 1003), ("gated_baseline", 1004)]
    assert api.prompts["verifier"] and api.prompts["reflection"]
    assert all(REFERENCE_CANARY not in p and CHALLENGE_CANARY not in p
               for role in ("verifier", "reflection") for p in api.prompts[role])
    rows = [read_json(p, sealed=True) for p in (root / "evaluations").glob("*.json")]
    assert [r["request"]["candidate_hash"] for r in rows if r["request"]["rollout"] == 1004] == [digest({"skill": ref["skill"]})] * 8
    assert study["references"]["by_reference"]["gated_baseline"]["pass"] == 0
    # a different reference list can never replay this step's sealed reference evaluation; a tampered file breaks
    # the stage inventory
    draw = read_json(root / "challenge/0/draw.json", sealed=True)
    outcome = read_json(root / "challenge/0/outcome.json", sealed=True)
    with pytest.raises(ValueError, match="Reference evaluation replay changed"):
        challenge.run_references(None, None, value, panel, 0, draw, outcome, [("parent", ""), ("gated_baseline", "other")], root)
    tampered = read_json(root / "challenge/0/references.json")
    tampered["summary"]["parent"]["pass"] += 1
    (root / "challenge/0/references.json").write_text(json.dumps(tampered))
    with pytest.raises(ValueError):
        run_stage(value, panel, root, fixture_api=api, fixture_evaluate=evaluate("candidate_wins"),
                  fixture_probe_executor=executor())
    # unknown reference positions are excluded from the jointly known pairs and reported, never imputed
    assert challenge._reference_pair("unknown", "pass") == "unknown" and challenge._reference_pair("fail", "unknown") == "unknown"
    assert challenge._reference_pair("fail", "pass") == "win" and challenge._reference_pair("pass", "fail") == "loss"
    counts = challenge._reference_counts(["win"] * 20 + ["loss"] * 5 + ["tie"] * 187 + ["unknown"] * 30)
    assert counts == {"positions": 242, "wins": 20, "losses": 5, "ties": 187, "unknown": 30, "jointly_known": 212}
    synthetic = {"status": "completed", "record_hash": "h", "branch_pass": {"comparator": 1, "treatment": 2},
                 "references": [{"name": "parent", "skill_hash": digest(""), "rollout": 1003}],
                 "summary": {"parent": {"pass": 100, "fail": 112, "unknown": 30, "comparator_minus_reference": counts,
                                        "treatment_minus_reference": {**counts, "unknown": 0, "ties": 217, "jointly_known": 242}}}}
    updated = {"comparator": {"skill_hash": digest("s"), "updated": True}, "treatment": {"skill_hash": digest("m"), "updated": True}}
    compared = matched.reference_comparisons(synthetic, "", 218, branches=updated)["by_reference"]["parent"]
    assert compared["comparator_minus_reference"]["outcome"] == "failed_delivery"
    assert compared["comparator_minus_reference"]["reason"] == "insufficient_jointly_known_holdout_pairs"
    assert compared["comparator_minus_reference"]["non_inferiority"]["holds"] is False
    assert compared["comparator_minus_reference"]["unknown_positions"] == 30
    assert compared["treatment_minus_reference"]["outcome"] == "useful_gain"
    assert compared["treatment_minus_reference"]["non_inferiority"]["holds"] is True
    assert matched.reference_comparisons({"status": "not_run"}, "", 218, branches=updated) is None
    # Codex round 2: a contrast that was not measured carries neither non-inferiority flag (100 wins, 25 unknown
    # positions: the worst-case interval alone would have held)
    thin = matched.paired_class(100, 0, 117, 242, 218, estimand="x")
    assert thin["outcome"] == "failed_delivery" and thin["worst_case_unknowns_as_treatment_losses"]["ci95"][0] > -0.05
    assert thin["non_inferiority"]["holds"] is False and thin["non_inferiority"]["holds_with_unknowns_as_losses"] is False
    # Codex round 2: an unchanged branch (no candidate: the parent itself was solved twice) is a noise replicate, never
    # an "update gain", whatever its counts; likewise a branch identical to its reference and a reference identical to
    # the parent
    full = {**counts, "unknown": 0, "ties": 217, "jointly_known": 242}
    synthetic2 = {"status": "completed", "record_hash": "h", "branch_pass": {"comparator": 1, "treatment": 2},
                  "references": [{"name": "parent", "skill_hash": digest(""), "rollout": 1003},
                                 {"name": "same_as_m", "skill_hash": digest("m"), "rollout": 1004},
                                 {"name": "empty_ref", "skill_hash": digest(""), "rollout": 1005}],
                  "summary": {name: {"pass": 100, "fail": 142, "unknown": 0, "comparator_minus_reference": full,
                                     "treatment_minus_reference": full, **({} if name == "parent" else {"reference_minus_parent": full})}
                              for name in ("parent", "same_as_m", "empty_ref")}}
    stale = {"comparator": {"skill_hash": digest(""), "updated": False}, "treatment": {"skill_hash": digest("m"), "updated": True}}
    by = matched.reference_comparisons(synthetic2, "", 218, branches=stale)["by_reference"]
    unchanged = by["parent"]["comparator_minus_reference"]
    assert unchanged["outcome"] == "failed_delivery" and unchanged["reason"] == "branch_skill_unchanged_from_parent"
    assert unchanged["wins"] == 20 and unchanged["non_inferiority"]["holds"] is False and "robust_to_unknowns" not in unchanged
    assert by["parent"]["treatment_minus_reference"]["outcome"] == "useful_gain"
    assert by["same_as_m"]["treatment_minus_reference"]["reason"] == "branch_skill_identical_to_reference"
    assert by["same_as_m"]["comparator_minus_reference"]["reason"] == "branch_skill_unchanged_from_parent"
    assert by["same_as_m"]["reference_minus_parent"]["outcome"] == "useful_gain"
    assert by["empty_ref"]["reference_minus_parent"]["reason"] == "reference_identical_to_parent"
    assert by["same_as_m"]["q3_interpretable"] == {"holds": True, "reason": "instrument_check_useful_gain"}
    assert by["empty_ref"]["q3_interpretable"] == {"holds": False, "reason": "instrument_check_failed_delivery:reference_identical_to_parent"}
    assert "q3_interpretable" not in by["parent"]


def test_matched_scalar_study_from_a_non_empty_parent_with_the_empty_skill_as_reference(tmp_path):
    """The study of active-evidence-from-generic-design-20261011.md: both updater branches start from a non-empty
    (fixed) parent text, the parent reference solves the holdout with that text, the EMPTY Skill is a named
    evaluation-only reference, and the study deploys nothing (the stage's Skill stays the parent)."""
    panel = _panel("searchqa")
    parent = "- Think the task through step by step.\n- Give the answer in the form the task asks for.\n"
    empty = {"name": "empty", "skill": "", "source": {"action": "empty_skill", "skill_bytes": 0}}
    value = ae.manifest(panel, **{**_args(arms=DIAG_STUDY, limits=STUDY_LIMITS), "parent_skill": parent},
                        reference_skills=[empty])
    assert ae.validate_manifest(value, panel) == value
    api = DiagnosisAPI()
    root = tmp_path / "learning"
    result = run_stage(value, panel, root, fixture_api=api, fixture_evaluate=evaluate("candidate_wins"),
                       fixture_probe_executor=executor())
    assert result["status"] == "completed", result["reason"]
    assert result["candidate_skill"] == parent and result["accepted_steps"] == 0  # a study deploys nothing
    chain = read_json(root / "chain/0.json", sealed=True)
    study = chain["matched"]
    # both branches are updates OF THE PARENT TEXT (the fixture analyst appends to the Skill it was given)
    for folder in ("native_matched", "native"):
        proposal = read_json(root / folder / "0/result.json", sealed=True)
        assert proposal["status"] == "candidate_ready" and proposal["candidate_skill"] != parent
        assert proposal["candidate_skill"].startswith(parent.rstrip("\n"))
    assert all(study["references"]["branches"][b]["updated"] is True for b in ("comparator", "treatment"))
    # the step rollout and the parent reference solve with the parent text, the named reference with no text
    record = read_json(root / "challenge/0/references.json", sealed=True)
    assert [(r["name"], r["rollout"]) for r in record["references"]] == [("parent", 1003), ("empty", 1004)]
    rows = [read_json(p, sealed=True) for p in (root / "evaluations").glob("*.json")]
    by_rollout = {k: {r["request"]["candidate_hash"] for r in rows if r["request"]["rollout"] == k} for k in (0, 1003, 1004)}
    assert by_rollout == {0: {digest({"skill": parent})}, 1003: {digest({"skill": parent})}, 1004: {digest({"skill": ""})}}
    by = study["references"]["by_reference"]
    assert by["parent"]["is_parent"] is True and by["empty"]["is_parent"] is False
    # fixture: only a Skill containing "requested constant" passes a holdout task -> both branches beat the parent
    # text and the empty Skill, and the empty Skill ties the parent text as a MEASURED contrast (different texts)
    assert (by["parent"]["pass"], by["empty"]["pass"]) == (0, 0)
    assert by["parent"]["comparator_minus_reference"]["outcome"] == "useful_gain"
    assert by["empty"]["comparator_minus_reference"]["outcome"] == "useful_gain"
    assert by["empty"]["reference_minus_parent"]["ties"] == 8
    assert by["empty"]["reference_minus_parent"].get("reason") != "reference_identical_to_parent"
    # no learning prompt saw a pool task
    assert all(CHALLENGE_CANARY not in p for role in ("verifier", "reflection") for p in api.prompts[role])


def test_an_analyst_prompt_profile_only_appends_its_addendum_and_is_sealed(tmp_path):
    """The prompt-chain experiment of 2026-10-13: a named profile appends one addendum to the analysts' system
    prompt; the default package is unchanged (no new manifest field), and the profile is limited to pass/fail
    feedback with the native update."""
    panel = _panel("searchqa")
    default = ae.manifest(panel, **_args(arms=PLAIN))
    assert "analyst_profile" not in default["active_evidence"]
    value = ae.manifest(panel, **_args(arms=PLAIN), analyst_profile="generalize_v1")
    assert value["active_evidence"]["analyst_profile"] == "generalize_v1" and ae.validate_manifest(value, panel) == value
    assert value["record_hash"] != default["record_hash"]
    with pytest.raises(ValueError, match="Unknown analyst prompt profile"):
        ae.manifest(panel, **_args(arms=PLAIN), analyst_profile="other")
    with pytest.raises(ValueError, match="pass/fail feedback and the native update only"):
        ae.manifest(panel, **_args(arms=DIAGNOSIS), analyst_profile="generalize_v1")
    systems = updater.analyst_systems(profile="generalize_v1")
    plain = updater.analyst_systems()
    assert all(systems[k].startswith(plain[k]) and "## Generalization requirement" in systems[k] for k in systems)
    assert all("## Generalization requirement" not in plain[k] for k in plain)
    api_default, api_profile = API(), API()
    run_stage(default, panel, tmp_path / "default", fixture_api=api_default, fixture_evaluate=evaluate("candidate_wins"))
    result = run_stage(value, panel, tmp_path / "profile", fixture_api=api_profile,
                       fixture_evaluate=evaluate("candidate_wins"))
    assert result["status"] == "completed" and result["decisions"] == ["accepted_without_challenge"]
    assert api_profile.prompts["reflection"] and all("## Generalization requirement" in p
                                                     for p in api_profile.prompts["reflection"] if "Transfer requirement" in p)
    assert all("## Generalization requirement" not in p for p in api_default.prompts["reflection"])
    identity = read_json(tmp_path / "profile/native/0/identity.json", sealed=True)
    assert identity["analyst_profile"] == "generalize_v1"
    assert "analyst_profile" not in read_json(tmp_path / "default/native/0/identity.json", sealed=True)
    # the solver never sees the addendum
    assert all("Generalization requirement" not in p for p in api_profile.prompts["solver"])


def test_matched_study_stops_pending_before_any_update_when_the_treatment_package_is_not_delivered(tmp_path):
    """A diagnosis whose check replies fail validation (or that yields no hypotheses) is a delivery failure of the
    treatment, never a delivered package: the study stops pending before any updater call or holdout evaluation.
    The method's own arms keep their behavior (the update proceeds on scalar feedback) and record the accounting."""
    panel = _panel("searchqa")

    def study(folder, api):
        value = ae.manifest(panel, **_args(arms=DIAG_STUDY, limits=STUDY_LIMITS))
        result = run_stage(value, panel, tmp_path / folder, fixture_api=api, fixture_evaluate=evaluate("candidate_wins"),
                           fixture_probe_executor=executor())
        rollouts = {read_json(p, sealed=True)["request"]["rollout"] for p in (tmp_path / folder / "evaluations").glob("*.json")}
        return result, rollouts

    api = BrokenJudgeAPI()
    result, rollouts = study("all", api)
    assert result["status"] == "pending" and result["reason"] == "treatment_package_not_delivered:no_row_report"
    assert not api.prompts["reflection"] and rollouts == {0} and result["candidate_skill"] == ""
    summary = read_json(tmp_path / "all/diagnosis/0/summary.json", sealed=True)
    assert summary["status"] == "completed" and summary["delivery"]["cases_format_failed"] == 8
    assert summary["delivery"]["rows_with_reports"] == 0 and summary["delivery"]["summary_present"] is False
    assert all(read_json(p, sealed=True)["delivery"] == "format_failure" for p in (tmp_path / "all/diagnosis/0/checks").glob("*.json"))
    api = BrokenJudgeAPI(broken=5)  # five of eight attempted cases lost: above one half
    result, rollouts = study("most", api)
    assert result["reason"] == "treatment_package_not_delivered:format_failures_exceed_half_of_attempted_cases"
    assert not api.prompts["reflection"] and rollouts == {0}
    api = BrokenJudgeAPI(broken=3)  # three of eight lost: the package is delivered and the loss is recorded
    result, rollouts = study("some", api)
    assert result["status"] == "completed" and rollouts == {0, 1000, 1001, 1003}
    chain = read_json(tmp_path / "some/chain/0.json", sealed=True)
    assert chain["diagnosis_delivery"]["cases_format_failed"] == 3 and chain["diagnosis_delivery"]["rows_with_reports"] == 5
    assert chain["matched"]["delivery"]["problem"] is None
    api = DiagnosisAPI(hypotheses=lambda cases: {"hypotheses": "not a list"})
    result, rollouts = study("nohyp", api)
    assert result["status"] == "pending" and result["reason"] == "treatment_package_not_delivered:diagnosis_no_hypotheses"
    assert not api.prompts["reflection"] and rollouts == {0}
    # the method's own diagnosis arm is unchanged: it completes on scalar feedback and records the lost delivery
    value = ae.manifest(panel, **_args(arms=DIAGNOSIS))
    api = BrokenJudgeAPI()
    result = run_stage(value, panel, tmp_path / "method", fixture_api=api, fixture_evaluate=evaluate("candidate_wins"),
                       fixture_probe_executor=executor())
    assert result["status"] == "completed" and api.prompts["reflection"]
    chain = read_json(tmp_path / "method/chain/0.json", sealed=True)
    assert chain["diagnosis_delivery"]["cases_format_failed"] == 8 and chain["reports"]["rows_with_evidence"] == 0
    assert chain["intervened"]["feedback_differs_from_scalar"] is False


def test_case_delivery_follows_the_effective_repaired_response(tmp_path):
    """Codex round 2: the delivery class and the not-applicable records come from the response the records are built
    from -- a repair that validly proposes nothing is an abstention (``no_checks``), not a format failure, and a
    repaired not-applicable item is recorded; five repaired abstentions plus three checked cases do not stop the study."""
    from skillopt.active_evidence import diagnosis as dg

    bad = {"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": 1, "obligation_id": "requested_behavior",
           "contract_quote": "Return two.", "rationale": "x", "hypothesis_id": "h1"}  # rejected: quote not in the task

    class AbstainAfterRepairAPI(DiagnosisAPI):
        """The first ``abstain`` cases: an invalid first reply, then a repair that proposes nothing (or, with
        ``inapplicable``, only a state check the contract does not impose); later cases: a valid check at once."""

        def __init__(self, abstain, inapplicable=False, **kwargs):
            super().__init__(**kwargs)
            self.abstain, self.inapplicable, self.cases = abstain, inapplicable, 0

        def _verifier(self, payload):
            if "diagnostic_focus" in payload and "anonymous_implementation" in payload:
                if "repair" in payload:
                    return {"probes": [{**STATE_PROBE, "contract_quote": "Return one.", "hypothesis_id": "h1"}] if self.inapplicable else []}
                self.cases += 1
                if self.cases <= self.abstain:
                    return {"probes": [bad]}
            return super()._verifier(payload)

    panel = _panel()
    value = ae.manifest(panel, **_args(arms=DIAG_STUDY, limits=STUDY_LIMITS))
    api = AbstainAfterRepairAPI(5)
    root = tmp_path / "abstain"
    result = run_stage(value, panel, root, fixture_api=api, fixture_evaluate=evaluate("candidate_wins"),
                       fixture_probe_executor=executor())
    assert result["status"] == "completed", result["reason"]
    records = [read_json(p, sealed=True) for p in (root / "diagnosis/0/checks").glob("*.json")]
    assert sorted(r["delivery"] for r in records) == ["checks"] * 3 + ["no_checks"] * 5
    assert all(r["rejected"]["parse"] and r["rejected"]["repair"] == {} for r in records if r["delivery"] == "no_checks")
    delivery = read_json(root / "diagnosis/0/summary.json", sealed=True)["delivery"]
    assert (delivery["cases_format_failed"], delivery["cases_without_checks"], delivery["rows_with_reports"]) == (0, 5, 3)
    # a repaired not-applicable item is recorded from the repaired reply (not looked up in the first reply's rejections)
    api = AbstainAfterRepairAPI(8, inapplicable=True)
    value = ae.manifest(panel, **_args(arms=DIAGNOSIS))
    result = run_stage(value, panel, tmp_path / "inapplicable", fixture_api=api, fixture_evaluate=evaluate("candidate_wins"),
                       fixture_probe_executor=executor())
    assert result["status"] == "completed", result["reason"]
    records = [read_json(p, sealed=True) for p in (tmp_path / "inapplicable/diagnosis/0/checks").glob("*.json")]
    assert all(r["delivery"] == "checks" and [c["grade"] for c in r["checks"]] == ["not_applicable"] for r in records)
    # the classifier itself: undelivered or invalid -> format failure; nothing proposed / only inapplicable -> no checks
    assert dg.case_delivery([], None, {}) == "format_failure" and dg.case_delivery([], {"probes": []}, {}) == "no_checks"
    assert dg.case_delivery([], {"probes": [bad]}, {"0": "contract_quote is not in the task"}) == "format_failure"
    assert dg.case_delivery([], {"probes": []}, {"0": dg.NOT_APPLICABLE + " no cue"}) == "no_checks"
    assert dg.case_delivery([{"check_id": "x"}], None, {"0": "bad"}) == "checks"


def _positions(spec, pair_families=None):
    """Synthetic sealed-outcome positions: ``spec`` is a list of (family_id, pair) with pair in win/loss/tie or an
    unknown kind."""
    return [{"set": "x", "family_id": family, "family_seen_in_step": False, "pair": pair} for family, pair in spec]


def _outcome(fresh, replay=(), local=()):
    from skillopt.active_evidence import challenge

    return {"status": "completed", "record_hash": "o" * 64,
            "summary": {"fresh": challenge._summary(_positions(fresh)), "replay": challenge._summary(_positions(replay)),
                        "local_fix": challenge._summary(_positions(local))}}


def test_decision_v2_table_family_sign_test_guard_and_adverse_completion():
    """Every branch of the frozen v2 table on synthetic sealed summaries (design memo of 2026-10-10)."""
    from skillopt.active_evidence import challenge
    from skillopt.active_evidence.decision import decide

    limits = {**ae.DEFAULT_LIMITS}  # fresh 96, min_paired_known 87, alpha 0.05

    def act(outcome, candidate="new", **changes):
        record = decide(outcome, {**limits, **changes}, parent="", candidate=candidate, step=0)
        return record["action"], record["reason"], record

    def single(wins, losses, ties, unknown=0, kind="candidate_unknown"):
        cells = ["win"] * wins + ["loss"] * losses + ["tie"] * ties + [kind] * unknown
        return [(f"f{i}", pair) for i, pair in enumerate(cells)]

    # 1-3: no candidate / no challenge arm / challenge not completed
    assert act(None, candidate=None)[:2] == ("no_update", "no_candidate_or_identical_to_parent")
    assert act(None, candidate="")[0] == "no_update" and act(None)[0] == "accepted_without_challenge"
    assert act({"status": "not_run", "reason": "no_positions_drawn", "record_hash": "n" * 64})[:2] == (
        "park", "challenge_not_completed:no_positions_drawn")
    # 7: a clear gain on single-task families (12 improving vs 1 regressing of 96: p = 0.0017)
    action, reason, record = act(_outcome(single(12, 1, 83)))
    assert action == "keep" and record["inputs"]["fresh"]["family_p_value"] == pytest.approx(14 / 8192)
    assert record["inputs"]["fresh"]["families_non_tied"] == 13 and record["next_skill"] == "candidate"
    # 8: the SearchQA M-minus-S shape (6 vs 4) and the BCB shapes are parked; 9 vs 3 of 96 is p = 0.073 -> park
    assert act(_outcome(single(6, 4, 86)))[:2] == ("park", "fresh_gain_not_significant")
    assert act(_outcome(single(9, 3, 84)))[:2] == ("park", "fresh_gain_not_significant")
    assert act(_outcome(single(10, 2, 84)))[0] == "keep"  # p = 0.019
    # 6: significant harm on the fresh panel
    assert act(_outcome(single(1, 9, 86)))[:2] == ("revert", "fresh_harm_significant")
    # 5: too few jointly known fresh positions -> the fresh decision is inadmissible, whatever the wins
    action, reason, record = act(_outcome(single(30, 0, 50, unknown=16)))
    assert (action, reason) == ("park", "fresh_decision_inadmissible") and record["inputs"]["flags"]["fresh_gain"] is True
    # 4 before 5: significant replay harm reverts even when the fresh panel is inadmissible; replay is harm-only
    harmful_replay = [(f"r{i}", "loss") for i in range(6)] + [(f"t{i}", "tie") for i in range(26)]
    assert act(_outcome(single(30, 0, 50, unknown=16), replay=harmful_replay))[:2] == ("revert", "replay_harm_significant")
    assert act(_outcome(single(12, 1, 83), replay=harmful_replay))[:2] == ("revert", "replay_harm_significant")
    winning_replay = [(f"r{i}", "win") for i in range(20)]
    assert act(_outcome(single(6, 4, 86), replay=winning_replay))[:2] == ("park", "fresh_gain_not_significant")
    # four replay losses of 32 are not significant (p = 1/16): no revert, the fresh gain keeps
    assert act(_outcome(single(12, 1, 83), replay=[(f"r{i}", "loss") for i in range(4)] + [(f"t{i}", "tie") for i in range(28)]))[0] == "keep"
    # adverse completion (Codex design round 1): 5 wins, 0 losses, 82 ties, 9 unknown -> p = 0.031 on the jointly
    # known positions, but the nine unknown positions could reverse it -> not kept
    action, reason, record = act(_outcome(single(5, 0, 82, unknown=9)))
    assert (action, reason) == ("park", "gain_not_robust_to_unknown_positions")
    assert record["inputs"]["fresh"]["family_p_value"] == 1 / 32 and record["inputs"]["fresh_adverse"]["net_wins"] == -4
    assert record["inputs"]["fresh_adverse"]["families_regressing"] == 9 and record["inputs"]["flags"]["fresh_admissible"] is True
    for kind in ("current_unknown", "both_unknown"):
        assert act(_outcome(single(5, 0, 82, unknown=9, kind=kind)))[1] == "gain_not_robust_to_unknown_positions"
    assert act(_outcome(single(14, 0, 80, unknown=2)))[0] == "keep"  # 14 vs 2 adverse: p = 0.002, net +12
    # multi-task families (KOR rules): the sign test is on RULE directions; 15 rules gaining one task and 5 rules
    # losing four each have p = 0.021 but a task-level net of -5 -> the aggregate guard refuses to keep
    rules = [(f"g{r}", "win") for r in range(15)] + [(f"g{r}", "tie") for r in range(15) for _ in range(3)]
    rules += [(f"b{r}", "loss") for r in range(5) for _ in range(4)]
    action, reason, record = act(_outcome(rules), min_paired_known=72)
    assert (action, reason) == ("park", "aggregate_guard_not_met")
    assert record["inputs"]["fresh"]["family_p_value"] == pytest.approx(0.0207, abs=1e-4) and record["inputs"]["fresh"]["net_wins"] == -5
    assert record["inputs"]["fresh"]["families"] == 20 and record["inputs"]["fresh"]["families_tied"] == 0
    # correlated tasks of one rule count once: one rule winning all ten of its tasks is a single improving family
    one_rule = [("g0", "win")] * 10 + [(f"t{r}", "tie") for r in range(19) for _ in range(5)]
    action, reason, record = act(_outcome(one_rule), min_paired_known=90)
    assert (action, reason) == ("park", "fresh_gain_not_significant") and record["inputs"]["fresh"]["families_improving"] == 1
    assert record["inputs"]["fresh"]["net_wins"] == 10 and record["inputs"]["fresh"]["family_p_value"] == 0.5
    # an empty replay set is recorded as unavailable, never as "no harm shown by a test"
    assert act(_outcome(single(12, 1, 83)))[2]["inputs"]["replay"]["unavailable"] == "no_positions_in_this_set"
    assert act(_outcome(single(12, 1, 83)))[2]["inputs"]["replay"]["family_harm_p_value"] is None
    # alpha comes from the sealed limits
    assert act(_outcome(single(9, 3, 84)), decision_alpha_permille=100)[0] == "keep"
    # the summary itself: family nets, harm p, adverse counts
    summary = challenge._summary(_positions([("a", "win"), ("a", "loss"), ("a", "win"), ("b", "loss"), ("c", "tie"),
                                             ("d", "candidate_unknown"), ("d", "win")]))
    assert (summary["families"], summary["families_improving"], summary["families_regressing"], summary["families_tied"]) == (4, 2, 1, 1)
    assert summary["net_wins"] == 1 and summary["jointly_known"] == 6 and summary["family_harm_p_value"] == 7 / 8
    assert summary["adverse"]["net_wins"] == 0 and summary["adverse"]["families_improving"] == 1  # family d: +1 - 1 = 0


def test_decision_v2_limits_caps_and_balanced_order():
    """The limits are fixed before any challenge outcome: the fresh panel is capped by the eligible pool and needs 90%
    coverage; alpha is never relaxed; the execution order is a seeded balanced split."""
    from skillopt.active_evidence import challenge

    assert (ae.DEFAULT_LIMITS["fresh_tasks"], ae.DEFAULT_LIMITS["replay_rows"], ae.DEFAULT_LIMITS["local_fix_rows"],
            ae.DEFAULT_LIMITS["min_paired_known"], ae.DEFAULT_LIMITS["decision_alpha_permille"]) == (96, 32, 8, 87, 50)
    assert "min_net_wins" not in ae.DEFAULT_LIMITS and "max_regressions" not in ae.DEFAULT_LIMITS
    assert [ae.min_known(n) for n in (96, 200, 242, 8, 1)] == [87, 180, 218, 8, 1]
    method = ae.effective_limits(CHALLENGE, 272)
    assert (method["fresh_tasks"], method["min_paired_known"]) == (96, 87)
    small = ae.effective_limits(CHALLENGE, 40)  # a small pool lowers the panel, never alpha
    assert (small["fresh_tasks"], small["min_paired_known"], small["decision_alpha_permille"], small["replay_rows"]) == (40, 36, 50, 32)
    study = ae.effective_limits(HIDDEN, 200)  # the matched study on a 200-task pool: 200 / 180 instead of 242 / 218
    assert (study["fresh_tasks"], study["min_paired_known"], study["replay_rows"]) == (200, 180, 0)
    assert ae.effective_limits(HIDDEN, 272)["min_paired_known"] == 218 and ae.effective_limits(PLAIN, 0) == ae.DEFAULT_LIMITS
    with pytest.raises(ValueError, match="eligible fresh task"):
        ae.effective_limits(CHALLENGE, 0)
    panel = _panel()
    for bad in ({"min_paired_known": 7}, {"fresh_tasks": 12, "min_paired_known": 10}, {"min_paired_known": 9},
                {"decision_alpha_permille": 0}, {"decision_alpha_permille": 500}):
        with pytest.raises(ValueError):
            ae.manifest(panel, **_args(arms=CHALLENGE, limits=bad))
    with pytest.raises(ValueError, match="Explicit complete limits"):
        ae.manifest(panel, **{**_args(arms=CHALLENGE), "limits": {**LIMITS, "min_net_wins": 2}})
    value = ae.manifest(panel, **_args(arms=CHALLENGE))
    for count in (0, 1, 2, 7, 8, 96):
        first, second = challenge.balanced_halves(value, 0, "fresh", count)
        assert sorted(first + second) == list(range(count)) and len(first) == (count + 1) // 2
        assert (first, second) == challenge.balanced_halves(value, 0, "fresh", count)
    assert challenge.balanced_halves(value, 0, "fresh", 96) != challenge.balanced_halves(value, 0, "replay", 96)
    assert challenge.balanced_halves(value, 0, "fresh", 96) != challenge.balanced_halves(value, 1, "fresh", 96)


def test_in_sample_train_panel_is_blind_solved_once_and_never_a_decision_input(tmp_path):
    """The optional train panel: an outcome-blind sample of the whole step roster next to the UNCHANGED replay and
    local-fix sets; a panel position that is also a replay / local-fix position reuses its evaluations; the shadow
    record never reaches the acting decision (design memo of 2026-10-11, in-sample shadow)."""
    from types import SimpleNamespace

    from skillopt.active_evidence import challenge

    # without the optional limit nothing changes: no key in the limits, the draw, the outcome or the decision
    plain_value, _, _, _ = _run(tmp_path / "plain")
    assert "train_panel_rows" not in plain_value["active_evidence"]["limits"]
    plain_draw = read_json(tmp_path / "plain/learning/challenge/0/draw.json", sealed=True)
    assert "train_panel" not in plain_draw and "train_panel_rule" not in plain_draw
    assert set(read_json(tmp_path / "plain/learning/challenge/0/outcome.json", sealed=True)["summary"]) == {
        "fresh", "replay", "local_fix"}
    assert "in_sample_shadow" not in read_json(tmp_path / "plain/learning/challenge/0/decision.json", sealed=True)

    limits = {"train_panel_rows": 8, "replay_rows": 2, "local_fix_rows": 1}
    value, panel, api, result = _run(tmp_path / "a", limits=limits)
    root = tmp_path / "a/learning"
    assert result["status"] == "completed" and result["decisions"] == ["keep"]
    draw = read_json(root / "challenge/0/draw.json", sealed=True)
    assert draw["train_panel_rule"] == challenge.TRAIN_PANEL_RULE
    # the whole roster of 8 step rows, each with the status of its own step evaluation; replay / local-fix as asked
    assert sorted(e["task_id"] for e in draw["train_panel"]) == STEP
    assert all(e["step_status"] == ("pass" if e["task_id"] in TRAIN_PASS else "fail") for e in draw["train_panel"])
    assert len(draw["replay"]) == 2 and len(draw["local_fix"]) == 1 and len(draw["fresh"]) == 8
    assert challenge.required_metric_calls(draw) == 2 * (8 + 2 + 1 + 5) and len(challenge.panel_extra(draw)) == 5
    outcome = read_json(root / "challenge/0/outcome.json", sealed=True)
    by_set = {}
    for position in outcome["positions"]:
        by_set.setdefault(position["set"], []).append(position)
    assert {k: len(v) for k, v in by_set.items()} == {"fresh": 8, "replay": 2, "local_fix": 1, "train_panel": 8}
    acting = {p["task_hash"]: p for p in by_set["replay"] + by_set["local_fix"]}
    shared = [p for p in by_set["train_panel"] if p["shared_with"] is not None]
    assert len(shared) == 3 and all(
        p["shared_with"] == acting[p["task_hash"]]["set"] and p["current"] == acting[p["task_hash"]]["current"]
        and p["candidate"] == acting[p["task_hash"]]["candidate"] for p in shared)
    # every task is solved exactly once per Skill: 8 fresh + 8 step tasks under each challenge rollout key
    rows = [read_json(f, sealed=True) for f in (root / "evaluations").glob("*.json")]
    for rollout in (1000, 1001):
        solved = [r["request"]["task_hash"] for r in rows if r["request"]["rollout"] == rollout]
        assert len(solved) == 16 and len(set(solved)) == 16
    order = outcome["execution_order"]["halves"]["train_panel"]
    extra = challenge.panel_extra(draw)
    assert sorted(order["parent_first"] + order["candidate_first"]) == extra and order["reused_positions"] == 3
    assert len(order["parent_first"]) == 3 and len(order["candidate_first"]) == 2
    panel_summary = outcome["summary"]["train_panel"]
    # the fixture's step rows do not depend on the Skill: the in-sample panel ties everywhere
    assert (panel_summary["positions"], panel_summary["ties"], panel_summary["net_wins"]) == (8, 8, 0)
    assert panel_summary["in_sample"] is True and panel_summary["decision_input"] is False
    assert panel_summary["by_step_status"] == {
        "step_pass": {"positions": 5, "wins": 0, "losses": 0, "ties": 5},
        "step_fail": {"positions": 3, "wins": 0, "losses": 0, "ties": 3},
        "step_unknown": {"positions": 0, "wins": 0, "losses": 0, "ties": 0}}
    assert outcome["summary"]["fresh_size_matched"]["positions"] == 8 and outcome["summary"]["fresh_size_matched"]["sensitivity_only"]
    decision = read_json(root / "challenge/0/decision.json", sealed=True)
    # the acting decision is rule v2 on the fresh panel, with exactly its usual inputs
    assert decision["action"] == "keep" and decision["rule_version"] == "active-evidence-decision-v2"
    assert set(decision["inputs"]) == {"candidate_changed", "challenge_status", "fresh", "replay", "flags", "fresh_adverse",
                                       "fresh_candidate_unknown", "replay_regressions", "local_fix"}
    shadow = decision["in_sample_shadow"]
    assert (shadow["version"], shadow["action"], shadow["reason"]) == ("in-sample-shadow-v1", "park", "panel_gain_not_significant")
    assert shadow["decision_input"] is False and shadow["min_paired_known"] == 8 and shadow["reused_positions"] == 3
    assert shadow["size_matched_fresh"]["action"] == "keep" and shadow["evidence"]["net_wins"] == 0
    chain = read_json(root / "chain/0.json", sealed=True)
    assert chain["reserve"]["positions"] == 8 + 2 + 1 + 8  # an upper bound: shared positions are solved once
    calls = len(api.prompts["reflection"])
    again = run_stage(value, panel, root, fixture_api=api, fixture_evaluate=evaluate("candidate_wins"))
    assert again == result and len(api.prompts["reflection"]) == calls
    # a forged draw is refused: a panel entry that is not a step task, a wrong step status, a duplicate
    ledger = SimpleNamespace(root=root)

    def refused(change, match):
        forged = {k: deepcopy(v) for k, v in draw.items() if k != "record_hash"}
        change(forged)
        with pytest.raises(ValueError, match=match):
            challenge._validate_draw(value, panel, 0, seal(forged), "", result["candidate_skill"], ledger)

    challenge._validate_draw(value, panel, 0, draw, "", result["candidate_skill"], ledger)
    blind = "deterministic outcome-blind draw"
    refused(lambda d: d["train_panel"].__setitem__(0, {**d["fresh"][0], "step_evidence_hash": None, "step_status": "unknown"}), blind)
    refused(lambda d: d["train_panel"][0].__setitem__("step_status", "fail" if d["train_panel"][0]["step_status"] == "pass" else "pass"), blind)
    refused(lambda d: d["train_panel"].append(d["train_panel"][0]), blind)
    refused(lambda d: d["train_panel"].__setitem__(1, d["train_panel"][0]), blind)
    refused(lambda d: d["train_panel"].pop(), blind)  # a truncated panel
    refused(lambda d: d["train_panel"].clear(), blind)  # an emptied panel
    refused(lambda d: d["train_panel"].reverse(), blind)  # the draw order is part of the record
    refused(lambda d: d.__setitem__("train_panel_rule", "hand_picked"), blind)
    refused(lambda d: d.pop("train_panel"), blind)
    # a hand-picked panel of valid step tasks with their true statuses is still not the seeded draw
    small_value, small_panel, _, small = _run(tmp_path / "small", limits={"train_panel_rows": 4})
    small_root = tmp_path / "small/learning"
    small_draw = read_json(small_root / "challenge/0/draw.json", sealed=True)
    assert len(small_draw["train_panel"]) == 4 and len({e["family_id"] for e in small_draw["train_panel"]}) == 4
    chosen = {e["task_id"] for e in small_draw["train_panel"]}
    swap = next(e for e in draw["train_panel"] if e["task_id"] not in chosen)  # a real step task outside the draw
    forged = {k: deepcopy(v) for k, v in small_draw.items() if k != "record_hash"}
    forged["train_panel"][0] = {**swap, "step_evidence_hash": None, "step_status": "unknown"}
    with pytest.raises(ValueError, match=blind):
        challenge._validate_draw(small_value, small_panel, 0, seal(forged), "", small["candidate_skill"],
                                 SimpleNamespace(root=small_root))
    # and a default stage refuses a draw that carries a panel
    plain_ledger = SimpleNamespace(root=tmp_path / "plain/learning")
    with_panel = {**{k: deepcopy(v) for k, v in plain_draw.items() if k != "record_hash"}, "train_panel": [],
                  "train_panel_rule": challenge.TRAIN_PANEL_RULE}
    with pytest.raises(ValueError, match="do not ask for one"):
        challenge._validate_draw(plain_value, panel, 0, seal(with_panel), "", result["candidate_skill"], plain_ledger)
    # the optional limit never changes the acting draw: the same fresh tasks in the same order, the same balanced
    # halves, the same sampling identity as the manifest without it (replay / local-fix are seeded samples over
    # rows ordered by their evaluation-record hash, which belongs to each stage's own manifest)
    assert ae.sampling_identity(plain_value) == plain_value["record_hash"] != value["record_hash"]
    assert ae.sampling_identity(small_value) == plain_value["record_hash"] != small_value["record_hash"]
    assert ae.sampling_identity(value) == ae.manifest(panel, **_args(
        arms=CHALLENGE, limits={"replay_rows": 2, "local_fix_rows": 1}))["record_hash"]
    assert [e["task_id"] for e in small_draw["fresh"]] == [e["task_id"] for e in plain_draw["fresh"]]
    plain_outcome = read_json(tmp_path / "plain/learning/challenge/0/outcome.json", sealed=True)
    small_outcome = read_json(small_root / "challenge/0/outcome.json", sealed=True)
    assert {k: small_outcome["execution_order"]["halves"][k] for k in ("fresh", "replay", "local_fix")} == \
        plain_outcome["execution_order"]["halves"]
    assert small_outcome["summary"]["fresh_size_matched"]["positions"] == 4

    # the acting decision never reads the panel: the candidate breaks the step rows the parent passed, the fresh
    # panel still gains -> keep; the shadow reports the in-sample harm (5 regressing families: p = 1/32)
    _, _, _, kept = _run(tmp_path / "b", mode="regress", limits={"train_panel_rows": 8, "replay_rows": 0, "local_fix_rows": 0})
    decision = read_json(tmp_path / "b/learning/challenge/0/decision.json", sealed=True)
    assert kept["decisions"] == ["keep"] and decision["inputs"]["flags"]["replay_harm"] is False
    shadow = decision["in_sample_shadow"]
    assert (shadow["action"], shadow["reason"]) == ("revert", "panel_harm_significant")
    assert shadow["evidence"]["families_regressing"] == 5 and shadow["evidence"]["family_harm_p_value"] == 1 / 32
    assert shadow["by_step_status"]["step_pass"] == {"positions": 5, "wins": 0, "losses": 5, "ties": 0}
    assert shadow["reused_positions"] == 0 and shadow["size_matched_fresh"]["action"] == "keep"
    # the same replay precedence as the acting table: significant replay harm reverts both readings
    _, _, _, reverted = _run(tmp_path / "c", mode="regress", limits={"train_panel_rows": 4})
    decision = read_json(tmp_path / "c/learning/challenge/0/decision.json", sealed=True)
    assert reverted["decisions"] == ["revert"] and decision["reason"] == "replay_harm_significant"
    assert decision["in_sample_shadow"]["reason"] == "replay_harm_significant"
    assert decision["in_sample_shadow"]["size_matched_fresh"]["reason"] == "replay_harm_significant"
    assert len(read_json(tmp_path / "c/learning/challenge/0/draw.json", sealed=True)["replay"]) == 5

    # no equal-size fresh reading when the fresh panel is smaller than the train panel: unavailable, never a smaller one
    _, _, _, thin = _run(tmp_path / "thin", limits={"train_panel_rows": 8, "fresh_tasks": 6, "min_paired_known": 6})
    assert thin["status"] == "completed", thin["reason"]
    matched = read_json(tmp_path / "thin/learning/challenge/0/outcome.json", sealed=True)["summary"]["fresh_size_matched"]
    assert matched == {"positions": 6, "wanted_positions": 8, "sensitivity_only": True, "decision_input": False,
                       "unavailable": "fewer_fresh_positions_than_train_panel_positions", "rule": matched["rule"]}
    shadow = read_json(tmp_path / "thin/learning/challenge/0/decision.json", sealed=True)["in_sample_shadow"]
    assert shadow["size_matched_fresh"] == {"action": None, "positions": 6, "wanted_positions": 8,
                                            "reason": "fewer_fresh_positions_than_train_panel_positions"}

    # a step row whose step evaluation was unknown stays in the roster (outcome-blind) and is solved again
    def with_unknown(task, skill):
        prediction, score = evaluate("candidate_wins")(task, skill)
        if task["task_id"] == "7":
            return prediction, {**score, "status": "unknown", "score": None}
        return prediction, score

    _, _, _, result = _run(tmp_path / "d", limits={"train_panel_rows": 8}, evaluator=with_unknown)
    assert result["status"] == "completed", result["reason"]
    draw = read_json(tmp_path / "d/learning/challenge/0/draw.json", sealed=True)
    entry = next(e for e in draw["train_panel"] if e["task_id"] == "7")
    assert entry["step_status"] == "unknown" and entry["step_evidence_hash"] is None
    outcome = read_json(tmp_path / "d/learning/challenge/0/outcome.json", sealed=True)
    position = next(p for p in outcome["positions"] if p["set"] == "train_panel" and p["task_id"] == "7")
    assert position["pair"] == "both_unknown" and position["shared_with"] is None
    summary = outcome["summary"]["train_panel"]
    assert summary["by_step_status"]["step_unknown"]["positions"] == 1 and summary["both_unknown"] == 1
    shadow = read_json(tmp_path / "d/learning/challenge/0/decision.json", sealed=True)["in_sample_shadow"]
    # 7 of 8 jointly known, 8 needed (ceil 90%): the in-sample reading is inadmissible, never a pass
    assert (shadow["action"], shadow["reason"], shadow["min_paired_known"]) == ("park", "panel_decision_inadmissible", 8)

    # the panel belongs to the method's challenge only, and its size is at least one
    for arms in (PLAIN, HIDDEN, DIAGNOSIS):
        with pytest.raises(ValueError):
            ae.manifest(panel, **_args(arms=arms, limits={"train_panel_rows": 4} if arms is not HIDDEN else
                                       {**STUDY_LIMITS, "train_panel_rows": 4}))
    for bad in (0, 501, "4"):
        with pytest.raises(ValueError):
            ae.manifest(panel, **_args(arms=CHALLENGE, limits={"train_panel_rows": bad}))


def test_in_sample_shadow_table_on_synthetic_panels():
    from skillopt.active_evidence import challenge
    from skillopt.active_evidence.decision import panel_action

    def act(spec, replay_harm=False):
        record = panel_action(challenge._summary(_positions(spec)), replay_harm, 0.05)
        return record["action"], record["reason"]

    wins = [(f"w{i}", "win") for i in range(6)]
    ties = [(f"t{i}", "tie") for i in range(58)]
    assert act(wins + ties) == ("keep", "panel_gain_significant_with_aggregate_guard_and_adverse_completion")
    assert act(wins + ties, replay_harm=True) == ("revert", "replay_harm_significant")
    assert act(wins[:4] + ties) == ("park", "panel_gain_not_significant")  # 4 of 4: p = 1/16
    assert act([(f"l{i}", "loss") for i in range(5)] + ties) == ("revert", "panel_harm_significant")
    # coverage: ceil(90%) of the positions jointly known, else inadmissible whatever the known rows say
    unknown = [(f"u{i}", "candidate_unknown") for i in range(7)]
    assert act(wins + ties[:51] + unknown) == ("park", "panel_decision_inadmissible")  # 57 of 64, 58 needed
    # the adverse completion: every unknown side charged as a loss must leave the gain standing
    assert act(wins + ties[:52] + unknown[:6]) == ("park", "gain_not_robust_to_unknown_positions")
    # multi-task families: five improving families, yet the task-level net is not positive
    spec = [(f"f{i}", "win") for i in range(5)] + [("g", "loss")] * 5
    assert act(spec + ties) == ("park", "panel_gain_not_significant")
    assert act([(f"f{i}", "win") for i in range(6)] + [("g", "loss")] * 6 + ties)[1] == "panel_gain_not_significant"
    assert act([]) == ("park", "panel_decision_inadmissible")


def test_exhausted_fresh_pool_parks_without_running_replay(tmp_path):
    """Codex code review: when an earlier step drew the whole pool, the next step has no eligible fresh task -- the
    challenge is not run at all (replay rows alone never decide, even when they would show significant harm), the
    candidate is parked, and the reserve holds nothing for comparisons that will not run."""
    panel = _panel()
    args = _args(arms=CHALLENGE, limits={"fresh_tasks": 12, "min_paired_known": 11}, budget={"max_iterations": 2})
    value = ae.manifest(panel, **args)
    api = API()
    root = tmp_path / "learning"
    result = run_stage(value, panel, root, fixture_api=api, fixture_evaluate=evaluate("regress"))
    assert result["status"] == "completed", result["reason"]
    # step 0: the candidate regresses every replay row -> revert; step 1: the pool is exhausted
    assert result["decisions"] == ["revert", "park"] and result["candidate_skill"] == ""
    first = read_json(root / "challenge/0/decision.json", sealed=True)
    assert first["reason"] == "replay_harm_significant" and len(read_json(root / "challenge/0/draw.json", sealed=True)["fresh"]) == 12
    draw = read_json(root / "challenge/1/draw.json", sealed=True)
    assert draw["fresh"] == [] and len(draw["replay"]) == 5 and draw["excluded_earlier_draws"] == 12
    outcome = read_json(root / "challenge/1/outcome.json", sealed=True)
    assert outcome["status"] == "not_run" and outcome["reason"] == "no_eligible_fresh_tasks"
    assert outcome["drawn"] == {"fresh": 0, "replay": 5, "local_fix": 2} and "positions" not in outcome
    second = read_json(root / "challenge/1/decision.json", sealed=True)
    assert (second["action"], second["reason"]) == ("park", "challenge_not_completed:no_eligible_fresh_tasks")
    rollouts = {read_json(p, sealed=True)["request"]["rollout"] for p in (root / "evaluations").glob("*.json")}
    assert rollouts == {0, 1, 1000, 1001}  # nothing was evaluated under the second step's challenge keys (1010, 1011)
    chain = read_json(root / "chain/1.json", sealed=True)
    assert chain["reserve"]["positions"] == 0 and chain["reserve"]["metric_calls"] == 0
    assert chain["challenge"]["status"] == "not_run" and chain["intervened"]["challenge_delta"] is False


def test_revised_expectation_executes_only_with_research_approval_second_review_and_no_open_question(tmp_path):
    """Codex code review (10/10): a revised expectation is a new assertion. It may execute only when Research approved
    it with documentary provenance AND its second review kept it AND that review raised no fact question. A second
    review can never re-admit a revision Research rejected; a question it raises leaves the check unresolved, and the
    hypothesis's fact need stays unresolved although Research documented the first question."""
    def hypotheses(cases):
        fails = [c["case_id"] for c in cases if c["host_audit"]["status"] == "fail"]
        passes = [c["case_id"] for c in cases if c["host_audit"]["status"] == "pass"]
        return {"hypotheses": [{"id": "h1", "kind": "task_error_candidate", "statement": "s", "mechanism": "m",
                                "applies_to": fails or [c["case_id"] for c in cases[:1]],
                                "discriminating_observation": {"supports": "a", "excludes": "b"},
                                "needs_fact": "Is the boundary return documented?", "preserve": passes}]}

    # (a) Research rejects the check but supplies a cited revised value; the second review would keep it
    api = ResearchAPI(resolution={"revised_expected": 7, "keep": False}, hypotheses=hypotheses)
    _, _, _, result = _run_research(tmp_path / "rejected", api, fetcher())
    assert result["status"] == "completed", result["reason"]
    root = tmp_path / "rejected/learning"
    assert not (root / "diagnosis/0/executions").exists()  # nothing executed
    summary = read_json(root / "diagnosis/0/summary.json", sealed=True)
    assert "confirmed_violation" not in summary["grades"] and "confirmed_preserved" not in summary["grades"]
    record = read_json(next((root / "diagnosis/0/checks").glob("*.json")), sealed=True)["checks"][0]
    legality = record["input_legality"]
    assert record["executed"] is False and legality["keep"] is False and legality["revision_admitted"] is False
    assert legality["reason"].startswith("revised expectation rejected by Research") and record["expected_basis"] == "contract"
    assert legality["revision_review"] == "revised expectation reviewed"  # the second review's keep is on record
    assert summary["fact_needs"][0]["resolved"] is False
    assert any("revision" in p for p in api.prompts["verifier"])

    # (b) Research approves the revision with a citation, the second review keeps it but asks a new fact question
    class QuestioningSecondReviewAPI(ResearchAPI):
        def _verifier(self, payload):
            if "revision" in payload and "probes" in payload:
                return {"reviews": [{"index": i, "keep": True, "reason": "plausible, but one fact is open",
                                     "fact_question": "Is seven the documented value on every platform?"}
                                    for i in range(len(payload["probes"]))]}
            return super()._verifier(payload)

    api = QuestioningSecondReviewAPI(resolution={"revised_expected": 7}, hypotheses=hypotheses)
    _, _, _, result = _run_research(tmp_path / "questioned", api, fetcher())
    assert result["status"] == "completed", result["reason"]
    root = tmp_path / "questioned/learning"
    assert not (root / "diagnosis/0/executions").exists()
    summary = read_json(root / "diagnosis/0/summary.json", sealed=True)
    assert set(summary["grades"]) == {"unknown"}
    record = read_json(next((root / "diagnosis/0/checks").glob("*.json")), sealed=True)["checks"][0]
    legality = record["input_legality"]
    assert record["executed"] is False and legality["keep"] is True and legality["revision_admitted"] is False
    assert legality["fact_question"] == legality["revision_fact_question"] == "Is seven the documented value on every platform?"
    assert record["expected_basis"] == "contract" and record["note"] == "unresolved fact question: not executed"
    need = summary["fact_needs"][0]
    assert need["status"] == "consulted:resolved" and need["resolved"] is False  # Research answered; the revision is still open
    assert "h1 [consulted:resolved]" in summary["summary_text"]
    # (c) the admitted path is unchanged: Research approval + second-review keep + no question -> executed
    api = ResearchAPI(resolution={"revised_expected": 7}, hypotheses=hypotheses)
    _, _, _, result = _run_research(tmp_path / "admitted", api, fetcher())
    record = read_json(next((tmp_path / "admitted/learning/diagnosis/0/checks").glob("*.json")), sealed=True)["checks"][0]
    assert record["executed"] is True and record["input_legality"]["revision_admitted"] is True
    assert record["expected_basis"] == "documentation"
    assert read_json(tmp_path / "admitted/learning/diagnosis/0/summary.json", sealed=True)["fact_needs"][0]["resolved"] is True


def test_evidence_delivery_repairs_whole_contracts_and_unassigned_cases(tmp_path):
    """R2 / R3 (10/11 audit): the diagnoser sees whole public contracts within a deterministic text budget (lengths and
    truncated fields on record), and a representative case that no hypothesis references gets a generic check attempt
    under the pseudo-hypothesis u0 instead of being skipped silently."""
    from skillopt.active_evidence import diagnoser

    # R2: bounds and the shared budget
    assert diagnoser.text_cap([100, 5000, 9000]) == 9000  # everything fits: nothing is clipped
    lengths = [30000] * 2 + [3000] * 14
    cap = diagnoser.text_cap(lengths)
    assert sum(min(n, cap) for n in lengths) <= diagnoser.VIEW_TEXT_BUDGET < sum(min(n, cap + 1) for n in lengths)
    assert diagnoser.text_cap([10**6] * 100) == diagnoser.VIEW_FLOOR_CHARS  # never below the floor
    _, base, _ = setup("korbench")
    task = base["tasks"][0]
    long_rule = "Rule clause. " * 900  # 11,700 characters: beyond the frozen 4,000-character development view
    pairs, cases = {}, []
    for i in range(3):
        public = {**task["public"], "rule": long_rule if i == 0 else task["public"]["rule"]}
        pairs[f"t{i}"] = {"item": {"task": {**task, "public": public}}, "row": {"output": {"output": "x" * 5000}}}
        cases.append({"token": f"t{i}", "case_id": f"case-{i}", "family_id": "f", "why": "fixture", "host_status": "fail",
                      "category": "host_fail"})
    views = diagnoser.case_views("korbench", pairs, cases, ae.DEFAULT_LIMITS)
    assert views[0]["task"]["rule"] == long_rule and views[0]["task_text_truncated"] == []
    assert views[0]["task_text_chars"]["rule"] == len(long_rule) and views[0]["task"]["domain"] == "rule_following"
    assert views[0]["generated_output_truncated"] is True and len(views[0]["generated_output"]) == ae.DEFAULT_LIMITS["view_output_chars"]
    huge = {"t0": {"item": {"task": {**task, "public": {**task["public"], "rule": "R" * 500000}}}, "row": {"output": {"output": ""}}}}
    clipped = diagnoser.case_views("korbench", huge, cases[:1], ae.DEFAULT_LIMITS)[0]
    assert clipped["task_text_truncated"] == ["rule"] and clipped["task"]["rule"].endswith("…[truncated]")
    assert clipped["task_text_chars"]["rule"] == 500000 and len(clipped["task"]["rule"]) <= diagnoser.TASK_TEXT_CHARS + 20

    # R3: the hypotheses reference two cases only; the six other representative cases are checked under u0
    def hypotheses(cases):
        failed = [c["case_id"] for c in cases if c["host_audit"]["status"] == "fail"]
        passed = [c["case_id"] for c in cases if c["host_audit"]["status"] == "pass"]
        return {"hypotheses": [{"id": "h1", "kind": "task_error_candidate", "statement": "s", "mechanism": "m",
                                "applies_to": failed[:1], "preserve": passed[:1],
                                "discriminating_observation": {"supports": "a", "excludes": "b"}, "needs_fact": None}]}

    class UnassignedAPI(DiagnosisAPI):
        def _verifier(self, payload):
            if "diagnostic_focus" in payload and "anonymous_response" in payload:
                ids = [f["hypothesis_id"] for f in payload["diagnostic_focus"]]
                verdict = "fail" if payload["anonymous_response"] == self.judge_fail_on else "pass"
                quote = payload["task"].get("question") or payload["task"]["rule"]
                return {"checks": [{"obligation": f"[{ids[0]}] answer form", "contract_quote": quote, "verdict": verdict,
                                    "evidence": payload["anonymous_response"][:50]}]}
            return super()._verifier(payload)

    api = UnassignedAPI(hypotheses=hypotheses)
    _, _, _, result = _run(tmp_path, arms=DIAGNOSIS, api=api, panel=_panel("korbench"), probe_executor=executor())
    assert result["status"] == "completed", result["reason"]
    root = tmp_path / "learning"
    summary = read_json(root / "diagnosis/0/summary.json", sealed=True)
    # h1 explains one failed case and preserves one passed case; the two other FAILED cases are unassigned (u0); the
    # four other PASSED cases serve as controls for h1 (an error hypothesis) -- every case has a disposition
    assert len(summary["unassigned_cases"]) == 2 and summary["delivery"]["cases_unassigned"] == 2
    assert summary["delivery"]["cases_attempted"] == 8 and summary["delivery"]["rows_with_reports"] == 8
    records = [read_json(p, sealed=True) for p in (root / "diagnosis/0/checks").glob("*.json")]
    tags = sorted(c["hypothesis_id"] for r in records for c in r["checks"])
    assert tags == ["h1"] * 6 + ["u0"] * 2
    unassigned = [r for r in records if r["focus"][0]["hypothesis_id"] == "u0"]
    assert len(unassigned) == 2 and all(r["focus"][0]["kind"] == "unexplained" and r["delivery"] == "checks" for r in unassigned)
    controls = [r for r in records if r["controls"]]
    assert len(controls) == 4 and all(r["host_status"] == "pass" for r in controls)
    assert summary["controls"]["version"] == "passed-case-controls-v1" and len(summary["controls"]["assignment"]) == 4
    lead = next(l for l in summary["judged_leads"] if l["hypothesis_id"] == "h1")
    assert (lead["fail_cases"], lead["control_cases_assigned"], lead["control_cases_judged"], lead["control_cases_with_judged_fail"],
            lead["claimed_pass_cases"]) == (1, 4, 4, 0, 1)
    # the control status stays host-side: the per-case judge prompt carries the neutral role "probe", never the words
    # control / passed the host audit
    judge_prompts = [p for p in api.prompts["verifier"] if "anonymous_response" in p]
    assert any('"role": "probe"' in p for p in judge_prompts) and all('"role": "control"' not in p for p in judge_prompts)
    assert all("passed the host audit" not in p for p in judge_prompts) and any("a hypothesis stated for OTHER responses" in p for p in judge_prompts)
    assert all(r["focus"][0]["role"] == "probe" for r in controls)
    assert any(lead["hypothesis_id"] == "u0" for lead in summary["judged_leads"])
    hyp = read_json(root / "diagnosis/0/hypotheses.json", sealed=True)
    assert set(hyp["case_task_text"]) == set(hyp["cases"]) and all(v["truncated"] == [] for v in hyp["case_task_text"].values())
    assert any("assign EVERY case id" in p for p in api.prompts["verifier"])


def test_probe_surface_repairs_bind_single_focus_ids_and_relocate_altered_quotes():
    """10/11 audit: the two most frequent probe rejections were surface problems -- a quote altered in case / quote
    characters / edge punctuation, and a wrong hypothesis id although the case had one focus hypothesis. The repairs
    are deterministic and never admit a paraphrase."""
    from skillopt.active_evidence import checks

    text = "def task_func(values):\n    \"\"\"Return the `sorted` list.\n    The input list is not modified.\n    \"\"\"\n"
    assert checks.relocate_quote("the input list is not modified", text) == "The input list is not modified."
    assert checks.relocate_quote("Return the 'sorted' list...", text) == '"""Return the `sorted` list.'
    assert checks.relocate_quote("The input list is not modified.", text) is None  # already a verbatim passage
    assert checks.relocate_quote("the list stays unchanged", text) is None  # a paraphrase is never relocated
    assert checks.relocate_quote("list", text) is None  # too short / ambiguous
    assert checks.relocate_quote("the", "the cat\nthe dog") is None
    probe = {"kind": "expected", "calls": [{"args": [[2, 1]], "kwargs": {}}], "expected": [1, 2],
             "obligation_id": "requested_behavior", "contract_quote": "return the 'sorted' list", "rationale": "x"}
    probes, rejected = checks.parse_check_probes({"probes": [dict(probe)]}, text, {"h2"}, 2)  # no id, one focus
    assert rejected == {} and probes[0]["hypothesis_id"] == "h2" and probes[0]["contract_quote"] == '"""Return the `sorted` list.'
    # a probe that NAMES another hypothesis stays rejected, as does a missing id with two focus hypotheses and a
    # paraphrased quote
    probes, rejected = checks.parse_check_probes({"probes": [{**probe, "hypothesis_id": "h9"}]}, text, {"h2"}, 2)
    assert probes == [] and "hypothesis_id" in rejected["0"]
    probes, rejected = checks.parse_check_probes({"probes": [dict(probe)]}, text, {"h1", "h2"}, 2)
    assert probes == [] and "hypothesis_id" in rejected["0"]
    probes, rejected = checks.parse_check_probes(
        {"probes": [{**probe, "hypothesis_id": "h1", "contract_quote": "the list must come back ordered"}]}, text, {"h1"}, 2)
    assert probes == [] and rejected
    # 10/11 (bsel1 log): a probe WITHOUT obligation_id gets the only admissible value; another obligation stays
    # rejected; a reply with more probes than allowed keeps the first ones in order instead of being rejected whole
    bare = {k: v for k, v in probe.items() if k != "obligation_id"}
    probes, rejected = checks.parse_check_probes({"probes": [{**bare, "hypothesis_id": "h2"}]}, text, {"h2"}, 2)
    assert rejected == {} and probes[0]["obligation_id"] == "requested_behavior"
    probes, rejected = checks.parse_check_probes({"probes": [{**probe, "obligation_id": "determinism"}]}, text, {"h2"}, 2)
    assert probes == [] and "requested behavior" in rejected["0"]
    three = [{**probe, "expected": [1, 2]}, {**probe, "expected": [2, 1], "contract_quote": "the list must come back ordered"},
             {**probe, "expected": [9]}]
    probes, rejected = checks.parse_check_probes({"probes": three}, text, {"h2"}, 2)
    assert [p["expected"] for p in probes] == [[1, 2]] and set(rejected) == {"1", checks.OVER_LIMIT}
    assert rejected[checks.OVER_LIMIT].startswith("3 probes returned")
    probes, rejected = checks.parse_check_probes({"probes": three[:2]}, text, {"h2"}, 2)
    assert checks.OVER_LIMIT not in rejected
    with pytest.raises(ValueError):
        checks.parse_check_probes({"probes": three, "note": "x"}, text, {"h2"}, 2)  # the envelope itself stays exact
    judged, _ = checks.parse_judged_checks({"checks": [{"obligation": "answer form", "contract_quote": "Return the `sorted` list.",
                                                         "verdict": "pass", "evidence": "x"}]}, text, {"u0"})
    assert judged[0]["hypothesis_id"] == "u0"
    judged, _ = checks.parse_judged_checks({"checks": [{"obligation": "[u0] answer form", "contract_quote": "Return the `sorted` list.",
                                                         "verdict": "pass", "evidence": "x"}]}, text, {"h1", "u0"})
    assert judged[0]["hypothesis_id"] == "u0"


# ----------------------------------------------------------------------------- the composition-aware screen (10/11)
SELECTION = {"feedback": "scalar", "post_update": "matched_selection_branch"}
GOOD_EDIT = "Use the requested constant result."
BAD_EDIT = "HARMFUL RULE: ignore the request."


ONE_MINIBATCH = {"minibatch_size": 8}  # one failure and one success minibatch: one patch from each side


class TwoEditAPI(API):
    """The failure analysts propose a useful section, the success analysts a harmful one (``success=None``: nothing);
    the merge and ranking calls keep whatever sections they are shown -- so the native candidate carries both."""

    def __init__(self, success=BAD_EDIT, **kwargs):
        super().__init__(**kwargs)
        self.success = success

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        result = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if kind.rsplit("-", 1)[-1] == "reflection":
            if "failure-analysis agent" in system:
                texts = [GOOD_EDIT]
            elif "success-pattern analyst" in system:
                texts = [self.success] if self.success else []
            else:
                texts = [text for text in (GOOD_EDIT, BAD_EDIT) if text in user] or [GOOD_EDIT]
            patch = {"reasoning": "Fixture only", "edits": [{"op": "append", "content": text} for text in texts]}
            result = {**result, "response": json.dumps({"batch_size": 2, "patch": patch})}
        return result


def skill_sensitive(task, skill):
    """Every row answers to the Skill text: the useful section repairs a failing row, the harmful one breaks any row."""
    good, bad = "requested constant" in skill, "HARMFUL" in skill
    base = task["task_id"] in TRAIN_PASS if task["task_id"] in STEP else False
    ok = (base or good) and not bad
    return ({"status": "available", "output": "one" if ok else "zero", "reason": "fixture"},
            {"status": "pass" if ok else "fail", "score": float(ok), "reason": "fixture", "metrics": {}})


def test_screen_builds_exact_variants_and_selects_by_the_frozen_rule():
    from skillopt.active_evidence import screen
    from skillopt.continual_learning.ledger import LearningPending

    def proposal(parent, edits):
        from skillopt.optimizer.skill import apply_patch_with_report
        text, report = apply_patch_with_report(parent, {"edits": edits})
        return {"status": "candidate_ready", "selected": {"edits": edits}, "application": report, "candidate_skill": text,
                "record_hash": "p" * 64}

    a, b, c = ({"op": "append", "content": text} for text in ("Section A.", "Section B.", "Section C."))
    arms = screen.build_arms("", proposal("", [a, b, c]), 32000)
    assert [(x["id"], x["kind"], x["disposition"]) for x in arms] == [
        ("parent_a", "parent", "scored"), ("parent_b", "parent", "scored"), ("candidate", "candidate", "scored"),
        ("drop_0", "leave_one_out", "scored"), ("drop_1", "leave_one_out", "scored"), ("drop_2", "leave_one_out", "scored"),
        # screen v2: with three or more applied edits, each edit ALONE on the parent is an arm too
        ("only_0", "single_edit", "scored"), ("only_1", "single_edit", "scored"), ("only_2", "single_edit", "scored")]
    assert arms[3]["skill"].split() == "Section B. Section C.".split() and arms[3]["dropped_edit"] == 0
    assert arms[6]["skill"].split() == "Section A.".split() and arms[6]["retained_edits"] == [0] and arms[6]["dropped_edit"] is None
    assert [x["arm"] for x in arms] == list(range(9)) and arms[2]["skill"] == proposal("", [a, b, c])["candidate_skill"]
    # two applied edits: a single-edit text IS the other leave-one-out variant, so no extra arm
    assert [x["id"] for x in screen.build_arms("", proposal("", [a, b]), 32000)] == ["parent_a", "parent_b", "candidate", "drop_0", "drop_1"]
    chained = screen.build_arms("", proposal("", [a, {"op": "insert_after", "target": "Section A.", "content": "After A."}, c]), 32000)
    assert {x["id"]: x["disposition"] for x in chained}["only_1"] == "application_dependency_failed"
    # one applied edit: nothing to leave out; identical texts alias; a leave-one-out that changes how another edit
    # applies is a dependency (not a clean variant); a no-op and an over-budget text are never scored
    assert [x["id"] for x in screen.build_arms("", proposal("", [a]), 32000)] == ["parent_a", "parent_b", "candidate"]
    twins = screen.build_arms("", proposal("", [a, a, b]), 32000)
    assert (twins[3]["disposition"], twins[4]["disposition"], twins[4]["alias_of"]) == ("scored", "duplicate_text", "drop_0")
    dependent = screen.build_arms("", proposal("", [a, {"op": "insert_after", "target": "Section A.", "content": "After A."}]), 32000)
    assert {x["id"]: x["disposition"] for x in dependent}["drop_0"] == "application_dependency_failed"
    removal = screen.build_arms("Keep.\n", proposal("Keep.\n", [a, {"op": "delete", "target": "Section A."}]), 32000)
    assert {x["id"]: x["disposition"] for x in removal}["drop_0"] == "application_dependency_failed"
    tight = screen.build_arms("", proposal("", [a, b]), len(proposal("", [a, b])["candidate_skill"].encode()) - 12)
    assert all(x["disposition"] == "scored" for x in tight)  # each single section still fits
    with pytest.raises(ValueError, match="recorded selection applied"):
        screen.build_arms("", {**proposal("", [a, b]), "candidate_skill": "something else"}, 32000)
    assert screen.screen_rollout(0, 0) == 2000 and screen.screen_rollout(3, 7) == 2307
    assert screen.max_positions(128, 4) == 11 * 128
    for bad in ((100, 0), (0, 100), (-1, 0)):
        with pytest.raises(ValueError):
            screen.screen_rollout(*bad)
    value = ae.manifest(_panel(), **_args(arms=CHALLENGE), update_mode="screened")
    blocks = screen._schedule(value, 0, 40, ["parent_a", "parent_b", "candidate"])
    assert sorted(i for block in blocks for i in block["rows"]) == list(range(40)) and [len(b["rows"]) for b in blocks] == [16, 16, 8]
    assert all(sorted(block["arms"]) == ["candidate", "parent_a", "parent_b"] for block in blocks)
    # arm order varies between blocks: the order is drawn from the manifest's hash, so one draw of three blocks can
    # coincide (1 in 36) -- which a change of the hashed sources can hit; several steps cannot all coincide
    orders = {tuple(block["arms"]) for step in range(6)
              for block in screen._schedule(value, step, 40, ["parent_a", "parent_b", "candidate"])}
    assert len(orders) > 1
    # the selection rule on synthetic statuses (20 single-task families)
    rows = [{"family_id": f"f{i}", "historical": "fail" if i < 10 else "pass"} for i in range(20)]
    arms = screen.build_arms("", proposal("", [a, b]), 32000)

    def chosen(statuses, alpha=0.10):
        selection, summaries, replicate = screen.select(arms, statuses, rows, alpha)
        return selection["id"], {v["id"]: v for v in summaries}, replicate

    base = ["fail"] * 10 + ["pass"] * 10
    fixed5 = ["pass"] * 5 + ["fail"] * 5 + ["pass"] * 10
    fixed4 = ["pass"] * 4 + ["fail"] * 6 + ["pass"] * 10
    noisy = ["pass"] * 5 + ["fail"] * 5 + ["pass"] * 10  # a control that happens to pass five of the failed rows
    picked, by, replicate = chosen({"parent_a": base, "parent_b": base, "candidate": fixed5, "drop_0": fixed4, "drop_1": base})
    assert picked == "candidate" and by["candidate"]["eligible"] and by["drop_0"]["eligible"] and not by["drop_1"]["eligible"]
    assert by["candidate"]["score"] == 10 and by["drop_0"]["against"]["parent_a"]["family_p_value"] == 1 / 16
    assert by["candidate"]["against"]["parent_a"]["by_historical_status"]["fail"]["wins"] == 5 and replicate["net_wins"] == 0
    # both controls must agree: against an unusually good replicate the same variant is not eligible -> abstain
    picked, by, replicate = chosen({"parent_a": base, "parent_b": noisy, "candidate": fixed5, "drop_0": base, "drop_1": base})
    assert picked == "parent" and not by["candidate"]["eligible"] and replicate["net_wins"] == 5
    # equal scores: the shorter text wins (a leave-one-out variant over the full candidate)
    picked, by, _ = chosen({"parent_a": base, "parent_b": base, "candidate": fixed5, "drop_0": fixed5, "drop_1": base})
    assert picked == "drop_0"
    # three repaired rows of twenty give p = 0.125 > 0.10 -> abstain; the threshold comes from the sealed limits
    fixed3 = ["pass"] * 3 + ["fail"] * 7 + ["pass"] * 10
    assert chosen({"parent_a": base, "parent_b": base, "candidate": fixed3, "drop_0": base, "drop_1": base})[0] == "parent"
    assert chosen({"parent_a": base, "parent_b": base, "candidate": fixed3, "drop_0": base, "drop_1": base}, alpha=0.2)[0] == "candidate"
    # coverage: a variant with too many unknown rows is ineligible; a control below coverage stops the stage pending
    holes = ["unknown"] * 3 + fixed5[3:]
    assert chosen({"parent_a": base, "parent_b": base, "candidate": holes, "drop_0": base, "drop_1": base})[1]["candidate"]["covered"] is False
    # screen v2: coverage is JOINT -- a variant and a control with 18 known rows each (the minimum) but different holes
    # share only 16, so the variant is not covered although each arm alone would be
    hole_a = ["unknown"] * 2 + base[2:]
    hole_v = fixed5[:18] + ["unknown"] * 2
    picked, by, _ = chosen({"parent_a": hole_a, "parent_b": base, "candidate": hole_v, "drop_0": base, "drop_1": base})
    assert by["candidate"]["against"]["parent_a"]["jointly_known"] == 16 and by["candidate"]["covered"] is False and picked == "parent"
    # ... and two controls that are each covered but share too few rows stop the stage pending
    with pytest.raises(LearningPending, match="screen_control_coverage"):
        chosen({"parent_a": hole_a, "parent_b": base[:18] + ["unknown"] * 2, "candidate": fixed5, "drop_0": base, "drop_1": base})
    # the outcome-blind text audit counts step-row outputs quoted by the added text; it decides nothing
    quoting = proposal("", [{"op": "append", "content": "Answer Daniel Boone when asked about the frontiersman."}, b])
    audit = screen.text_audit("", quoting, [{"row": {"output": {"output": "<answer>Daniel Boone</answer>"}}},
                                           {"row": {"output": {"output": "<answer>one</answer>"}}}])
    assert audit["step_outputs_quoted_in_added_text"] == 1 and audit["step_outputs_checked"] == 2 and audit["decides_nothing"] is True
    with pytest.raises(LearningPending, match="screen_control_coverage"):
        chosen({"parent_a": ["unknown"] * 3 + base[3:], "parent_b": base, "candidate": fixed5, "drop_0": base, "drop_1": base})


def test_screened_update_prunes_a_harmful_edit_and_the_selection_study_compares_it_with_the_native_candidate(tmp_path):
    """End to end: the native candidate carries a useful and a harmful section; on the step rows the screen measures
    the candidate, both leave-one-out variants and two parent controls (interleaved), selects the variant without the
    harmful section, and (method mode) the outer decision keeps it; (study mode) it beats the native candidate on the
    holdout while the parent and the native candidate are evaluated as references / comparator."""
    from skillopt.active_evidence import screen as screen_module

    panel = _panel()
    limits = {"screen_alpha_permille": 200}  # three repaired rows of eight: p = 0.125
    value = ae.manifest(panel, **_args(arms=CHALLENGE, limits=limits, budget=ONE_MINIBATCH), update_mode="screened")
    assert value["active_evidence"]["update_mode"] == "screened" and ae.validate_manifest(value, panel) == value
    api = TwoEditAPI()
    root = tmp_path / "method"
    result = run_stage(value, panel, root, fixture_api=api, fixture_evaluate=skill_sensitive)
    assert result["status"] == "completed", result["reason"]
    assert result["decisions"] == ["keep"] and GOOD_EDIT in result["candidate_skill"] and BAD_EDIT not in result["candidate_skill"]
    native = read_json(root / "native/0/result.json", sealed=True)
    assert GOOD_EDIT in native["candidate_skill"] and BAD_EDIT in native["candidate_skill"]  # the native candidate had both
    inventory = read_json(root / "screen/0/inventory.json", sealed=True)
    outcome = read_json(root / "screen/0/outcome.json", sealed=True)
    assert [a["id"] for a in inventory["arms"]] == ["parent_a", "parent_b", "candidate", "drop_0", "drop_1"]
    assert [a["rollout"] for a in inventory["arms"]] == [2000, 2001, 2002, 2003, 2004] and inventory["schedule"]["interleaved"] is True
    assert outcome["inventory_hash"] == inventory["record_hash"] and inventory["expected_metric_positions"] == 5 * 8
    assert outcome["selection"] == {"id": "drop_1", "abstained": False, "reason": "largest_net_against_both_controls_among_eligible",
                                    "rule": screen_module.SELECTION_RULE, "alpha": 0.2}
    by = {v["id"]: v for v in outcome["variants"]}
    assert (by["candidate"]["pass"], by["drop_0"]["pass"], by["drop_1"]["pass"]) == (0, 0, 8)
    assert by["drop_1"]["against"]["parent_a"]["wins"] == 3 and by["drop_1"]["eligible"] and not by["candidate"]["eligible"]
    assert by["candidate"]["against"]["parent_b"]["losses"] == 5 and outcome["parent_b_minus_parent_a"]["net_wins"] == 0
    assert outcome["controls"] == {"parent_a": {"pass": 5, "fail": 3, "unknown": 0}, "parent_b": {"pass": 5, "fail": 3, "unknown": 0}}
    rows = [read_json(p, sealed=True) for p in (root / "evaluations").glob("*.json")]
    assert {r["request"]["rollout"] for r in rows} == {0, 1000, 1001, 2000, 2001, 2002, 2003, 2004}
    assert all(sum(r["request"]["rollout"] == key for r in rows) == 8 for key in (2000, 2001, 2002, 2003, 2004))
    # every screen row is a step row; no challenge task is ever screened
    step_hashes = {digest(t) for t in panel["tasks"] if t["task_id"] in STEP}
    assert {r["request"]["task_hash"] for r in rows if r["request"]["rollout"] >= 2000} == step_hashes
    chain = read_json(root / "chain/0.json", sealed=True)
    assert chain["update_mode"] == "screened" and chain["screen"]["selection"]["id"] == "drop_1"
    assert chain["intervened"]["screen_changed_selection"] is True and chain["native_candidate_hash"] == digest(native["candidate_skill"])
    assert chain["edits"]["candidate_hash"] == digest(result["candidate_skill"]) != chain["native_candidate_hash"]
    assert chain["reserve"]["screen_positions"] == 11 * 8 and "screen/0/outcome.json" in result["artifacts"]
    assert inventory["text_audit"]["decides_nothing"] is True and inventory["text_audit"]["step_outputs_quoted_in_added_text"] == 0
    # the analysts were told their edits are measured individually (screened mode only)
    assert all("MEASURED EDITS." in p for p in api.prompts["reflection"] if "failure-analysis agent" in p or "success-pattern analyst" in p)
    assert all(CHALLENGE_CANARY not in p for p in api.prompts["reflection"])
    # replay: identical records, zero new calls
    calls = len(api.prompts["reflection"])
    again = run_stage(value, panel, root, fixture_api=api, fixture_evaluate=skill_sensitive)
    assert again == result and len(api.prompts["reflection"]) == calls

    # the selection study: comparator = native candidate (both sections), treatment = the screen's selection
    study = ae.manifest(panel, **_args(arms=SELECTION, limits={**STUDY_LIMITS, **limits}, budget=ONE_MINIBATCH),
                        update_mode="screened")
    api = TwoEditAPI()
    root = tmp_path / "study"
    result = run_stage(study, panel, root, fixture_api=api, fixture_evaluate=skill_sensitive)
    assert result["status"] == "completed", result["reason"]
    assert result["candidate_skill"] == "" and result["accepted_steps"] == 0  # a study deploys nothing
    record = read_json(root / "chain/0.json", sealed=True)["matched"]
    assert record["study"] == "matched-selection-branch-study-v3" and record["treatment"]["selection"]["id"] == "drop_1"
    assert record["candidates_identical"] is False and record["treatment"]["is_parent"] is False
    assert record["outcome"]["outcome"] == "useful_gain" and record["outcome"]["wins"] == 8
    assert "screen selection minus native candidate" in record["outcome"]["estimand"]
    parent = record["references"]["by_reference"]["parent"]
    assert parent["treatment_minus_reference"]["outcome"] == "useful_gain" and parent["comparator_minus_reference"]["ties"] == 8
    assert record["references"]["branches"] == {"comparator": {"skill_hash": record["comparator"]["skill_hash"], "updated": True},
                                                "treatment": {"skill_hash": record["treatment"]["skill_hash"], "updated": True,
                                                              "delivered_selection": True}}
    assert result["steps"][0]["matched_outcome"] == "useful_gain"


def test_screen_abstention_and_policy_agreement_are_recorded_not_dropped(tmp_path):
    """Abstention is a result: in method mode the step has no candidate and spends no fresh panel; in the study the
    parent is the treatment and is compared with the native candidate. When the screen selects the native candidate
    itself the study records policy agreement (a same-Skill replicate, not a measured contrast)."""
    panel = _panel()
    # the fixture's step rows do not answer to the Skill: no variant beats the controls -> abstain
    value = ae.manifest(panel, **_args(arms=CHALLENGE), update_mode="screened")
    api = API()
    result = run_stage(value, panel, tmp_path / "method", fixture_api=api, fixture_evaluate=evaluate("candidate_wins"))
    assert result["status"] == "completed" and result["decisions"] == ["no_update"] and result["candidate_skill"] == ""
    outcome = read_json(tmp_path / "method/screen/0/outcome.json", sealed=True)
    assert outcome["selection"]["abstained"] is True and outcome["selection"]["reason"] == "no_eligible_variant"
    assert not (tmp_path / "method/challenge/0/draw.json").exists()
    rollouts = {read_json(p, sealed=True)["request"]["rollout"] for p in (tmp_path / "method/evaluations").glob("*.json")}
    assert {0, 2000, 2001, 2002} <= rollouts and not any(1000 <= key < 2000 for key in rollouts)  # no challenge key
    chain = read_json(tmp_path / "method/chain/0.json", sealed=True)
    assert chain["intervened"]["skill_changed"] is False and chain["intervened"]["screen_changed_selection"] is True
    assert chain["native_candidate_hash"] is not None and chain["edits"]["candidate_hash"] is None
    # study: abstention is a measured contrast (here the native candidate wins every holdout task, so abstaining is worse)
    study = ae.manifest(panel, **_args(arms=SELECTION, limits=STUDY_LIMITS), update_mode="screened")
    result = run_stage(study, panel, tmp_path / "study", fixture_api=API(), fixture_evaluate=evaluate("candidate_wins"))
    assert result["status"] == "completed", result["reason"]
    record = read_json(tmp_path / "study/chain/0.json", sealed=True)["matched"]
    assert record["treatment"]["is_parent"] is True and record["treatment"]["selection"]["abstained"] is True
    assert record["outcome"]["outcome"] == "harmful_change" and record["outcome"]["losses"] == 8
    by = record["references"]["by_reference"]["parent"]
    # abstention against the parent reference is a same-text replicate; against a DISTINCT reference it is measured
    assert by["treatment_minus_reference"]["reason"] == "branch_skill_identical_to_reference"
    assert by["comparator_minus_reference"]["outcome"] == "useful_gain"
    assert record["references"]["branches"]["treatment"] == {"skill_hash": digest(""), "updated": False, "delivered_selection": True}
    assert record["delivery"]["diagnosis_status"] == "scalar_arm_no_diagnosis" and record["delivery"]["diagnosis_problem"] is None
    # policy agreement: the screen selects the native candidate itself
    agree = ae.manifest(panel, **_args(arms=SELECTION, limits={**STUDY_LIMITS, "screen_alpha_permille": 200},
                                       budget=ONE_MINIBATCH), update_mode="screened")
    result = run_stage(agree, panel, tmp_path / "agree", fixture_api=TwoEditAPI(success=None), fixture_evaluate=skill_sensitive)
    assert result["status"] == "completed", result["reason"]
    record = read_json(tmp_path / "agree/chain/0.json", sealed=True)["matched"]
    assert record["treatment"]["selection"]["id"] == "candidate" and record["candidates_identical"] is True
    assert record["outcome"]["outcome"] == "failed_delivery" and record["outcome"]["reason"] == "policy_agreement_same_skill_replicate"
    assert record["references"]["by_reference"]["parent"]["comparator_minus_reference"]["outcome"] == "useful_gain"
    # the protocol: the selection study needs the screened update mode; the failure-message arm is never screened
    with pytest.raises(ValueError, match="needs update_mode screened"):
        ae.manifest(panel, **_args(arms=SELECTION, limits=STUDY_LIMITS))
    with pytest.raises(ValueError, match="not screened"):
        ae.manifest(panel, **_args(arms=HIDDEN, limits=STUDY_LIMITS), update_mode="screened")
    with pytest.raises(ValueError, match="native or screened"):
        ae.manifest(panel, **_args(arms=CHALLENGE), update_mode="other")


def test_review_fixes_of_the_screen_and_the_delivery_repairs(tmp_path):
    """Codex code review (10/11), one regression per item."""
    from skillopt.active_evidence import checks, diagnoser, matched, reports, screen
    from skillopt.optimizer.skill import apply_patch_with_report

    # 1. leave-one-out re-applies only the edits the native application APPLIED: dropping the deletion must give
    #    "X + B", never bring the originally failed replacement to life
    edits = [{"op": "delete", "target": "X"}, {"op": "replace", "target": "X", "content": "Y"}, {"op": "append", "content": "B"}]
    text, report = apply_patch_with_report("X\n", {"edits": edits})
    assert [r["status"] for r in report] == ["applied_delete", "skipped_replace_target_not_found", "applied_append"]
    arms = {a["id"]: a for a in screen.build_arms("X\n", {"status": "candidate_ready", "selected": {"edits": edits},
                                                           "application": report, "candidate_skill": text, "record_hash": "p"}, 32000)}
    assert set(arms) == {"parent_a", "parent_b", "candidate", "drop_0", "drop_2"}  # the skipped edit is not a unit
    assert arms["drop_0"]["disposition"] == "scored" and "X" in arms["drop_0"]["skill"] and "Y" not in arms["drop_0"]["skill"]
    assert arms["drop_0"]["retained_edits"] == [2] and arms["drop_2"]["retained_edits"] == [0] and arms["candidate"]["retained_edits"] == [0, 2]
    assert all(r["status"].startswith("applied") for a in arms.values() if a["application"] for r in a["application"]
               if a["kind"] == "leave_one_out")
    # 2. the diagnoser prompt is fitted in BYTES: sixteen cases of 8,000 CJK context characters and 3,000-character
    #    outputs exceed 200,000 bytes at full size; the fitted views stay under the target and record the fit
    _, base, _ = setup("searchqa")
    task = base["tasks"][0]
    pairs, cases = {}, []
    for i in range(16):
        public = {**task["public"], "context": "\u8bed" * 8000}
        pairs[f"t{i}"] = {"item": {"task": {**task, "public": public}}, "row": {"output": {"output": "o" * 3000}}}
        cases.append({"token": f"t{i}", "case_id": f"case-{i}", "family_id": "f", "why": "fixture", "host_status": "fail",
                      "category": "host_fail"})

    def size(views):
        return len(json.dumps(views, ensure_ascii=False).encode())
    assert size(diagnoser.case_views("searchqa", pairs, cases, ae.DEFAULT_LIMITS)) > 200000
    views, fit = diagnoser.fitted_case_views("searchqa", pairs, cases, ae.DEFAULT_LIMITS, size)
    assert fit["fits"] is True and fit["prompt_bytes"] <= diagnoser.PROMPT_BYTES_TARGET and fit["scale"] < 1
    assert all(v["task_text_truncated"] == ["context"] and v["task_text_chars"]["context"] == 8000 for v in views)
    small, fit = diagnoser.fitted_case_views("searchqa", pairs, cases[:2], ae.DEFAULT_LIMITS, size)
    assert fit["scale"] == 1.0 and small[0]["task_text_truncated"] == []
    assert diagnoser.fitted_case_views("searchqa", pairs, cases, ae.DEFAULT_LIMITS, lambda v: 10**9)[1]["fits"] is False
    # 3. a quote is never relocated to a prefix of an overlong line (the matched clause and its qualifications stay)
    long_line = "The input list is preserved during validation " + "and " * 200 + "is then sorted in place before returning."
    assert len(long_line) > 600 and checks.relocate_quote("is then sorted in place before returning", long_line) is None
    assert checks.relocate_quote("the input list is preserved during validation", long_line) is None
    # 4. a judged check that explicitly names a hypothesis outside the focus stays unbound; only a MISSING tag binds
    def judged(obligation, ids):
        rows, _ = checks.parse_judged_checks({"checks": [{"obligation": obligation, "contract_quote": "Return one.",
                                                          "verdict": "fail", "evidence": "x"}]}, "Return one.", ids)
        return rows[0]["hypothesis_id"]
    assert judged("[h9] answer form", {"h1"}) is None and judged("answer form", {"h1"}) == "h1"
    assert judged("[h1] answer form", {"h1", "h2"}) == "h1" and judged("answer form", {"h1", "h2"}) is None
    # 5. a confirmed violation without a supported hypothesis is not summarized as "no violation"
    def check(i, grade, executed, hypothesis="u0", kind="expected", outcome=None, case="case-a"):
        return {"check_id": f"c/{i}", "hypothesis_id": hypothesis, "case_id": case, "evidence_hash": f"e{i}", "kind": kind,
                "host_status": "fail", "grade": grade, "executed": executed, "outcome": outcome, "assertion": "returns 1",
                "contract_quote": "Return one.", "observation": "returned 0", "note": None}
    hypothesis = {"id": "h1", "kind": "task_error_candidate", "statement": "s", "mechanism": "m", "applies_to": ["case-b"],
                  "preserve": [], "needs_fact": None}
    undecided = [{"hypothesis_id": "h1", "verdict": "undecided", "uncovered_cases": 1, "explained_cases": 1}]
    text = reports.render_summary([hypothesis], undecided, [check(0, "confirmed_violation", True)], {"exceptions": "none"},
                                  2500, rows=(1, 1, 128))
    assert "Confirmed violations (executed checks): 1" in text and "confirmed no violation" not in text
    assert "1 executed assertion(s) failed without a hypothesis that explains them" in text and "executed checks cover 1." in text
    assert "the correctness of its expectation and its cause are not" in text
    def scope(*grades):
        text = reports.render_summary([hypothesis], undecided, [check(i, g, True) for i, g in enumerate(grades)],
                                      {"exceptions": "none"}, 2500, rows=(1, 1, 128))
        assert "confirmed no violation" not in text  # executed is not the same as held (Codex round 2)
        return text
    assert "no violation was confirmed: 1 executed check(s) held and 0 executed check(s) are unresolved" in scope("confirmed_preserved")
    for grade in ("format_or_env_error", "unknown", "pending_explanation"):
        assert "no violation was confirmed: 0 executed check(s) held and 1 executed check(s) are unresolved" in scope(grade)
    assert "2 executed check(s) held and 3 executed check(s) are unresolved" in scope(
        "confirmed_preserved", "unknown", "format_or_env_error", "confirmed_preserved", "pending_explanation")
    # 6. an abstaining selection is measured against a DISTINCT reference (20 wins, 0 losses), never 'unchanged'
    counts = {"positions": 242, "wins": 20, "losses": 0, "ties": 222, "unknown": 0, "jointly_known": 242}
    references = {"status": "completed", "record_hash": "h", "branch_pass": {"comparator": 1, "treatment": 2},
                  "references": [{"name": "parent", "skill_hash": digest(""), "rollout": 1003},
                                 {"name": "gated", "skill_hash": digest("g"), "rollout": 1004}],
                  "summary": {"parent": {"pass": 1, "fail": 1, "unknown": 0, "comparator_minus_reference": counts,
                                         "treatment_minus_reference": counts},
                              "gated": {"pass": 1, "fail": 1, "unknown": 0, "comparator_minus_reference": counts,
                                        "treatment_minus_reference": counts, "reference_minus_parent": counts}}}
    abstain = {"comparator": {"skill_hash": digest("c"), "updated": True},
               "treatment": {"skill_hash": digest(""), "updated": False, "delivered_selection": True}}
    by = matched.reference_comparisons(references, "", 218, branches=abstain)["by_reference"]
    assert by["gated"]["treatment_minus_reference"]["outcome"] == "useful_gain"
    assert by["parent"]["treatment_minus_reference"]["reason"] == "branch_skill_identical_to_reference"
    plain = {**abstain, "treatment": {"skill_hash": digest(""), "updated": False}}  # study v2 semantics are unchanged
    assert matched.reference_comparisons(references, "", 218, branches=plain)["by_reference"]["gated"][
        "treatment_minus_reference"]["reason"] == "branch_skill_unchanged_from_parent"
    # 7. a genuine judged unknown is shown as JUDGED UNKNOWN (grade unknown) and counted among the judged checks
    mixed = [check(0, "pending_explanation", False, "h1", "judged_obligation", "fail", "case-b"),
             check(1, "pending_explanation", False, "h1", "judged_obligation", "pass", "case-b"),
             check(2, "unknown", False, "h1", "judged_obligation", "unknown", "case-b"),
             check(3, "unknown", False, "h1", "expected", None, "case-b")]
    assert [reports.judged_verdict(c) for c in mixed] == ["fail", "pass", "unknown", None]
    rendered = reports.render_report(mixed, 1800)
    assert rendered.index("JUDGED FAIL") < rendered.index("JUDGED PASS") < rendered.index("JUDGED UNKNOWN")
    assert rendered.count("- UNKNOWN") == 1
    leads = reports.judged_leads([hypothesis], mixed, [{"case_id": "case-b", "host_status": "fail"}])
    assert leads == [{"hypothesis_id": "h1", "judged_checks": 3, "judged_unknown_checks": 1, "fail_cases": 1,
                      "fail_cases_with_judged_fail": 1, "control_cases_assigned": 0, "control_cases_judged": 0,
                      "control_cases_with_judged_fail": 0, "control_cases_with_judged_unknown": 0, "claimed_pass_cases": 0,
                      "claimed_pass_cases_with_judged_fail": 0}]


def test_overlong_hypothesis_texts_are_clipped_not_fatal(tmp_path):
    """10/11 (BigCodeBench m2): 'Bounded text required' on the diagnoser's reply and again on its repair lost the whole
    diagnosis. An over-long text field is now clipped to its bound and recorded; ids, kinds and case lists stay strict."""
    from skillopt.active_evidence import diagnoser

    def hypotheses(cases):
        fails = [c["case_id"] for c in cases if c["host_audit"]["status"] == "fail"]
        passes = [c["case_id"] for c in cases if c["host_audit"]["status"] == "pass"]
        return {"hypotheses": [{"id": "h1", "kind": "task_error_candidate", "statement": "S" * 620, "mechanism": "M" * 340,
                                "applies_to": fails, "preserve": passes, "needs_fact": "Q" * 450,
                                "discriminating_observation": {"supports": "a" * 330, "excludes": "b"}}]}

    api = DiagnosisAPI(hypotheses=hypotheses)
    _, _, _, result = _run(tmp_path, arms=DIAGNOSIS, api=api, probe_executor=executor())
    assert result["status"] == "completed", result["reason"]
    record = read_json(tmp_path / "learning/diagnosis/0/hypotheses.json", sealed=True)
    assert record["status"] == "ok" and len(api.prompts["verifier"]) and not any("repair" in p and "batch_summary" in p for p in api.prompts["verifier"])
    parsed = record["hypotheses"][0]
    assert len(parsed["statement"]) == 500 and parsed["statement"].endswith(diagnoser.CLIP) and len(parsed["mechanism"]) == 300
    assert len(parsed["needs_fact"]) == 400 and len(parsed["discriminating_observation"]["supports"]) == 300
    assert parsed["discriminating_observation"]["excludes"] == "b"
    assert record["clipped_text_fields"] == ["0.statement", "0.mechanism", "0.needs_fact", "0.discriminating_observation.supports"]
    # structural strictness is unchanged
    for bad in ({"id": "h2"}, {"kind": "other"}, {"applies_to": ["unknown-case"]}):
        with pytest.raises(ValueError):
            diagnoser.parse_hypotheses({"hypotheses": [{**hypotheses([])["hypotheses"][0], "applies_to": [], "preserve": ["c"],
                                                        **bad}]}, ["c"], ae.DEFAULT_LIMITS)
    value, clipped = diagnoser.clip_hypothesis_texts({"hypotheses": "not a list"})
    assert value == {"hypotheses": "not a list"} and clipped == []
    # over-long whitespace is never turned into content by the marker: it stays as it is and fails validation
    blank = {"hypotheses": [{**hypotheses([])["hypotheses"][0], "applies_to": [], "preserve": ["c"], "statement": " " * 700,
                             "mechanism": "m", "needs_fact": None,
                             "discriminating_observation": {"supports": "a", "excludes": "e" * 320}}]}
    value, clipped = diagnoser.clip_hypothesis_texts(blank)
    assert value["hypotheses"][0]["statement"] == " " * 700 and clipped == ["0.discriminating_observation.excludes"]
    with pytest.raises(ValueError, match="Bounded text required"):
        diagnoser.parse_hypotheses(blank, ["c"], ae.DEFAULT_LIMITS)


def test_passed_cases_are_controls_for_error_hypotheses():
    """10/11: an error hypothesis predicts its violation is absent from passing outputs; passed representative cases
    that it does not already reference are assigned to it as controls (round-robin, deterministic), and the
    observation records how many control cases showed the violation too."""
    from skillopt.active_evidence import diagnosis as dg
    from skillopt.active_evidence import reports

    def hyp(i, kind, applies=(), preserve=()):
        return {"id": f"h{i}", "kind": kind, "statement": "s", "mechanism": "m", "applies_to": list(applies),
                "preserve": list(preserve), "needs_fact": None, "discriminating_observation": {"supports": "a", "excludes": "b"}}

    cases = [{"case_id": f"f{i}", "host_status": "fail"} for i in range(3)] + [{"case_id": f"p{i}", "host_status": "pass"} for i in range(4)]
    hypotheses = [hyp(1, "task_error_candidate", ["f0", "f1"]), hyp(2, "coverage_gap", ["f2"]),
                  hyp(3, "unexplained", [], ["p0", "p1", "p2", "p3"])]
    assignment = dg.control_assignment(hypotheses, cases, 2)
    assert assignment == {"p0": ["h1", "h2"], "p1": ["h1", "h2"], "p2": ["h1", "h2"], "p3": ["h1", "h2"]}
    assert dg.control_assignment(hypotheses, cases, 1) == {"p0": ["h1"], "p1": ["h2"], "p2": ["h1"], "p3": ["h2"]}  # round-robin
    # a hypothesis never controls a case it already references; success-only hypotheses create no controls
    own = [hyp(1, "task_error_candidate", ["f0"], ["p0"]), hyp(2, "unexplained", [], ["p1"])]
    assert dg.control_assignment(own, cases, 2) == {"p1": ["h1"], "p2": ["h1"], "p3": ["h1"]}
    assert dg.control_assignment([hyp(1, "unexplained", ["f0"], ["p0"])], cases, 2) == {}
    assert dg.control_assignment(hypotheses, cases[:3], 2) == {}  # no passed case

    def check(i, hypothesis, case, grade, outcome=None, kind="judged_obligation"):
        return {"check_id": f"c/{i}", "hypothesis_id": hypothesis, "case_id": case, "evidence_hash": f"e{i}", "kind": kind,
                "grade": grade, "outcome": outcome, "executed": kind != "judged_obligation"}

    checks = [check(0, "h1", "f0", "pending_explanation", "fail"), check(1, "h1", "f1", "pending_explanation", "fail"),
              check(2, "h1", "p0", "pending_explanation", "pass"), check(3, "h1", "p1", "pending_explanation", "fail"),
              check(4, "h2", "p2", "confirmed_violation", "fail", "expected")]
    by = {o["hypothesis_id"]: o for o in reports.observations(hypotheses, checks, cases, controls=assignment)}
    assert (by["h1"]["control_cases_assigned"], by["h1"]["control_cases_checked"], by["h1"]["control_cases_violated"]) == (4, 2, 0)
    assert (by["h2"]["control_cases_checked"], by["h2"]["control_cases_violated"]) == (1, 1) and by["h3"]["control_cases_assigned"] == 0
    lead = reports.judged_leads(hypotheses, checks, cases, controls=assignment)[0]
    assert (lead["fail_cases_with_judged_fail"], lead["fail_cases"], lead["control_cases_assigned"], lead["control_cases_judged"],
            lead["control_cases_with_judged_fail"], lead["claimed_pass_cases"]) == (2, 2, 4, 2, 1, 0)
    # without the sealed assignment nothing is called a control (a preserved or claimed passed case is not one)
    plain = reports.judged_leads(hypotheses, checks, cases)[0]
    assert plain["control_cases_assigned"] == 0 and plain["claimed_pass_cases"] == 2
    # an EXECUTED violation that is also confirmed on a passing (control) output does not explain the failures
    executed = [check(0, "h2", "f2", "confirmed_violation", "fail", "expected"), check(1, "h2", "p0", "confirmed_violation", "fail", "expected"),
                check(2, "h1", "f0", "confirmed_violation", "fail", "expected"), check(3, "h1", "f1", "confirmed_violation", "fail", "expected"),
                check(4, "h1", "p1", "confirmed_preserved", "pass", "expected")]
    for c in executed:
        c.update(host_status="fail" if c["case_id"].startswith("f") else "pass", assertion="returns 1", contract_quote="q",
                 observation=None, note=None)
    by = {o["hypothesis_id"]: o for o in reports.observations(hypotheses, executed, cases, controls=assignment)}
    assert by["h2"]["verdict"] == "also_on_controls" and by["h1"]["verdict"] == "consistent"
    text = reports.render_summary(hypotheses, list(by.values()), executed, {"exceptions": "x"}, 2500, rows=(5, 5, 128))
    assert ("Also observed on passing control outputs (specificity and cause unresolved -- the probe's expectation, the "
            "contract reading or the hidden tests' coverage may be at fault): h2 (1 of 1 checked control cases)") in text
    assert "do not explain the failures" not in text
    assert "hypotheses consistent with them: h1 " in text and "h2 (coverage_gap)" not in text.split("Also observed on passing")[0]
    # the wording needs failed-case evidence: a hypothesis whose only confirmed violation is on a PASSING case it claims
    # is never said to be 'also observed on controls'
    claim = [hyp(1, "task_error_candidate", ["p0"]), hyp(2, "unexplained", [], ["p1"])]
    only_pass = [dict(executed[1], hypothesis_id="h1", case_id="p0"), dict(executed[1], hypothesis_id="h1", case_id="p2", check_id="c/9")]
    verdict = reports.observations(claim, only_pass, cases, controls={"p2": ["h1"]})[0]
    assert verdict["verdict"] == "consistent" and verdict["control_cases_violated"] == 1
    # Codex round 1: heterogeneous exclusions must not starve a hypothesis of controls
    four = [hyp(1, "task_error_candidate", ["f0"], ["p0"]), hyp(2, "task_error_candidate", ["f1"]),
            hyp(3, "coverage_gap", ["f2"], ["p2"]), hyp(4, "delivery", ["f0"])]
    spread = dg.control_assignment(four, cases, 2)
    counts = {h: sum(h in ids for ids in spread.values()) for h in ("h1", "h2", "h3", "h4")}
    assert spread == {"p0": ["h2", "h3"], "p1": ["h4", "h1"], "p2": ["h2", "h4"], "p3": ["h1", "h2"]} and min(counts.values()) >= 1
    assert all("h1" not in spread["p0"] and "h3" not in spread["p2"] for _ in [0])
