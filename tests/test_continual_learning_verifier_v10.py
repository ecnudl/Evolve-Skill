"""Learning v10 controls: the Rubric -> probe -> Research verifier's feedback path, calibration and
replay guarantees (engineering fixtures; no method-effect claim)."""
import json
import threading
from copy import deepcopy

import pytest

from skillopt.continual_learning.contracts import VERIFIER_METHOD, VERIFIER_VERSION, manifest, validate_manifest
from skillopt.continual_learning.feedback import LABELED_PROFILE, VERIFIER_PROFILE, project
from skillopt.continual_learning.ledger import BudgetExhausted, Ledger
from skillopt.continual_learning.recovery import POLICY_V9, POLICY_V10
from skillopt.continual_learning.skillopt import VERIFIER_PREAMBLE, run_stage
from skillopt.continual_learning import verifier as vf
from skillopt.validator_pilot.api import digest
from tests.test_continual_learning_domains import PRIVATE_CANARY, evaluate, setup
from tests.test_continual_learning_generalization_v8 import LABEL, auth

POLICY = {**vf.DEFAULT_POLICIES["bigcodebench"], "mechanism": "Check the documented return value on a legal boundary input."}


TRAIN_PASS = {"0", "1", "2", "3", "4"}  # fixture train rows the host passes (controls for calibration)


def _args10(*, benchmark="bigcodebench", train=8, selection=8, iterations=1, parent_policy=None):
    _, base, args = setup(benchmark)
    task = base["tasks"][0]
    tasks = [{**deepcopy(task), "task_id": str(i), "family_id": str(i)} for i in range(train + selection)]
    for row in tasks[train:]:
        row["partition"] = "skill_confirmation"
    for row in tasks:
        row["private"]["answer" if benchmark == "korbench" else "answers" if benchmark == "searchqa" else "test"] = (
            [LABEL, "alt"] if benchmark == "searchqa" else LABEL if benchmark == "korbench" else PRIVATE_CANARY)
    panel = {**base, "tasks": tasks}
    args.update(version=VERIFIER_VERSION, recovery_policy=deepcopy(POLICY_V10),
                train_families=[str(i) for i in range(train)],
                selection_families=[str(i) for i in range(train, train + selection)], feedback_profile=VERIFIER_PROFILE,
                method=VERIFIER_METHOD, parent_verifier_policy=parent_policy)
    args["model"]["transport"]["stream_wall_seconds"] = 3600
    args["budget"].update(max_iterations=iterations, max_metric_calls=200, max_api_calls=600,
                          max_reflection_calls=40, max_verifier_calls=100, verifier_max_tokens=100)
    return panel, args


def _auth10(**kwargs):
    panel, args = _args10(**kwargs)
    return manifest(panel, **args), panel


def host_evaluate(benchmark, pass_ids=TRAIN_PASS):
    """Train rows: fixed host outcomes regardless of the Skill (passing rows output 'one', failing rows
    'zero'); selection rows: the ordinary fixture, so the candidate Skill wins there."""
    base = evaluate(benchmark)

    def execute(task, skill):
        if task["partition"] != "development":
            return base(task, skill)
        ok = task["task_id"] in pass_ids
        return ({"status": "available", "output": "one" if ok else "zero", "reason": "fixture"},
                {"status": "pass" if ok else "fail", "score": float(ok), "reason": "fixture", "metrics": {}})
    return execute


class API:
    """Fixture provider for solver, analyst and verifier calls; records what each role was shown."""

    service = {"fixture": "offline-domain-controls", "delivery_retry_policy": "closed_delivery_error_v3", "max_retries": 2}
    model = "fixture"

    def __init__(self, *, judge_fail_on="zero", probe_expected=1, plan_status="investigate",
                 synthesis_status="update", review_keep=True, fact_question=None):
        self.prompts = {"solver": [], "reflection": [], "verifier": []}
        self.judge_fail_on, self.probe_expected = judge_fail_on, probe_expected
        self.plan_status, self.synthesis_status = plan_status, synthesis_status
        self.review_keep, self.fact_question = review_keep, fact_question
        self.lock = threading.Lock()

    def close(self):
        pass

    def _verifier(self, payload):
        if "experiment_arm" in payload:  # plan
            return {"status": self.plan_status, "questions": ["Is the boundary return documented?"], "urls": []}
        if "reflection" in payload:  # synthesis
            if self.synthesis_status != "update":
                return {"status": self.synthesis_status, "policy": None, "citations": [], "reason": "abstain"}
            return {"status": "update", "policy": POLICY, "citations": [], "reason": "Boundary returns were unchecked."}
        if "anonymous_implementation" in payload:  # probes
            return {"probes": [{"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": self.probe_expected,
                                "obligation_id": "requested_behavior", "contract_quote": "Return one.",
                                "rationale": "The contract fixes the return value."}]}
        if "fact_questions" in payload:  # research plan
            return {"urls": []}
        if "reviews" in payload:  # research resolution (never reached without sources)
            return {"resolutions": []}
        if "probes" in payload:  # review
            return {"reviews": [{"index": 0, "keep": self.review_keep, "reason": "legal input", "fact_question": self.fact_question}]}
        if "anonymous_response" in payload:  # judge
            verdict = "fail" if payload["anonymous_response"] == self.judge_fail_on else "pass"
            quote = payload["task"].get("question") or payload["task"]["rule"]
            return {"checks": [{"obligation": "answer form", "contract_quote": quote, "verdict": verdict,
                                "evidence": payload["anonymous_response"][:50]}]}
        raise AssertionError("unknown verifier payload")

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        role = kind.rsplit("-", 1)[-1]
        with self.lock:
            self.prompts[role].append(system + "\n" + user)
        assert PRIVATE_CANARY not in system + user and LABEL not in system + user, role
        request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                   "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        if role == "solver":
            response = "<answer>one</answer>" if "requested constant" in system else "<answer>zero</answer>"
        elif role == "verifier":
            response = json.dumps(self._verifier(json.loads(user)))
        else:
            response = json.dumps({"batch_size": 2, "patch": {"reasoning": "Fixture only", "edits": [
                {"op": "append", "content": "Use the requested constant result."}]}})
        return {"request": request, "request_hash": digest(request), "response": response, "ok": True,
                "finish_reason": "stop", "usage": {"prompt_tokens": 20, "completion_tokens": 20},
                "http_attempt_count": 1, "attempts": [{"usage": {"prompt_tokens": 20, "completion_tokens": 20}}]}


def executor(*, fail_on=("zero",), cleanup=True):
    """Fixture container: probe 0 fails on the named outputs (the fixture solver's wrong answer is 'zero')."""
    calls = []

    def execute(public, output, probes):
        calls.append((public["entry_point"], output, deepcopy(probes)))
        details = {}
        if output in fail_on:
            details["test_probe_0"] = ("Traceback (most recent call last):\n  File \"__test__.py\", line 9\n"
                                       f"AssertionError: {vf.probe_mark(probes)} got 0 expected 1")
        return {"status": "fail" if details else "pass", "score": 0.0 if details else 1.0,
                "reason": "official_bigcodebench_untrusted_check", "metrics": {"native_result": "fail" if details else "pass",
                                                                              "details": details},
                "cleanup_confirmed": cleanup, "execution_costs": {"container_calls": 1}}
    execute.calls = calls
    return execute


# ----------------------------------------------------------------------------- contracts and ledger
def test_v10_manifest_couples_method_version_profile_and_budget():
    value, panel = _auth10()
    assert validate_manifest(value, panel) == value
    assert value["method"] == VERIFIER_METHOD and value["feedback_profile"] == VERIFIER_PROFILE
    assert value["parent_verifier_policy"] is None and value["budget"]["max_verifier_calls"] == 100
    assert value["feedback_fields"][-1] == "verifier_probe_reports_on_failed_train_rows"
    base, args = _args10()
    v9_budget = {k: v for k, v in args["budget"].items() if k not in {"max_verifier_calls", "verifier_max_tokens"}}
    with pytest.raises(ValueError, match="rubric_research method requires learning v10"):
        manifest(base, **{**args, "version": "continual-learning-v9", "recovery_policy": deepcopy(POLICY_V9),
                          "budget": v9_budget, "feedback_profile": LABELED_PROFILE})
    with pytest.raises(ValueError, match="rubric_research method requires learning v10"):
        manifest(base, **{**args, "method": "skillopt"})
    with pytest.raises(ValueError, match="verifier feedback is v10 only"):
        manifest(base, **{**args, "feedback_profile": LABELED_PROFILE})
    with pytest.raises(ValueError, match="complete learning budget"):
        manifest(base, **{**args, "budget": v9_budget})
    # a parent policy mapping must hold valid per-domain records
    record = vf.default_policy_record("bigcodebench")
    value2, _ = _auth10(parent_policy={"bigcodebench": record})
    assert value2["parent_verifier_policy"]["bigcodebench"]["policy_hash"] == digest(record["policy"])
    with pytest.raises(ValueError, match="another verifier or domain"):
        _auth10(parent_policy={"searchqa": record})
    with pytest.raises(ValueError, match="hash differs"):
        _auth10(parent_policy={"bigcodebench": {**record, "policy_hash": "0" * 64}})


def test_v10_projection_stays_scalar_and_label_free():
    value, panel = _auth10(benchmark="korbench")
    task = panel["tasks"][0]
    trace = project(value, task["public"], {"status": "available", "output": "zero"},
                    {"status": "fail", "score": 0.0}, private=task["private"], role="train")
    assert trace["Feedback"] == {"status": "fail", "score": 0.0}
    assert LABEL not in json.dumps(trace)


def test_v10_ledger_has_a_verifier_role_with_its_own_budget(tmp_path):
    value, panel = _auth10()
    root = tmp_path / "ledger"
    root.mkdir()
    ledger = Ledger(root, value, API())
    for i in range(3):
        receipt = ledger.call("verifier", f"verifier:0:probes:{i}", "s", json.dumps({"anonymous_response": "x", "task": {"question": "q"}}), 50)
        assert receipt["ok"]
    costs = ledger.snapshot()
    assert costs["verifier_calls"] == 3 and costs["reflection_calls"] == 0
    with pytest.raises(ValueError, match="frozen output cap"):
        ledger.call("verifier", "verifier:0:probes:big", "s", "{}", 101)
    value9, _ = auth(version="continual-learning-v9", policy=POLICY_V9)
    with pytest.raises(ValueError, match="Unsupported learning call role"):
        Ledger(tmp_path / "v9", value9, API()).call("verifier", "x", "s", "u", 50)
    # the verifier call budget is a stop of its own
    base, args = _args10()
    args["budget"]["max_verifier_calls"] = 1
    tiny = manifest(base, **args)
    ledger = Ledger(tmp_path / "tiny", tiny, API())
    ledger.call("verifier", "verifier:0:judge:a", "s", json.dumps({"anonymous_response": "x", "task": {"question": "q"}}), 50)
    with pytest.raises(BudgetExhausted, match="max_verifier_calls"):
        ledger.call("verifier", "verifier:0:judge:b", "s", json.dumps({"anonymous_response": "y", "task": {"question": "q"}}), 50)


# ----------------------------------------------------------------------------- probes and harness
def test_probe_parsing_is_strict_and_the_harness_is_valid_python():
    task = "Return one. Example: f() -> 1"
    probes, rejected = vf.parse_probes({"probes": [
        {"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": 1, "obligation_id": "requested_behavior",
         "contract_quote": "Return one.", "rationale": "fixed"},
        {"kind": "equal_relation", "calls": [{"args": [1], "kwargs": {}}, {"args": [1.0], "kwargs": {}}], "expected": None,
         "obligation_id": "requested_behavior", "contract_quote": "f() -> 1", "rationale": "same"}]}, task)
    assert rejected == {} and len(probes) == 2
    source = vf.probe_test_source("f", probes)
    compile(source, "<harness>", "exec")
    assert "def test_probe_0" in source and "def test_probe_1" in source and "class TestCases" in source
    # one malformed probe drops only itself (per-probe validation); the envelope stays strict
    kept, rejected = vf.parse_probes({"probes": [
        {"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": 1, "obligation_id": "requested_behavior",
         "contract_quote": "Return two.", "rationale": "x"},
        {"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": 1, "obligation_id": "requested_behavior",
         "contract_quote": "Return one.", "rationale": "ok"}]}, task)
    assert len(kept) == 1 and kept[0]["rationale"] == "ok" and set(rejected) == {"0"} and "substring" in rejected["0"]
    checks, rejected = vf.parse_checks({"checks": [
        {"obligation": "form", "contract_quote": "Return one.", "verdict": "fail", "evidence": "e"},
        {"obligation": "form", "contract_quote": "nope", "verdict": "pass", "evidence": ""}]}, task)
    assert len(checks) == 1 and set(rejected) == {"1"}
    for bad in (
        {"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": 1, "obligation_id": "requested_behavior",
         "contract_quote": "Return two.", "rationale": "x"},                    # quote not in task
        {"kind": "expected", "calls": [{"args": [], "kwargs": {}}, {"args": [], "kwargs": {}}], "expected": 1,
         "obligation_id": "requested_behavior", "contract_quote": "Return one.", "rationale": "x"},  # two calls
        {"kind": "equal_relation", "calls": [{"args": [], "kwargs": {}}, {"args": [], "kwargs": {}}], "expected": 1,
         "obligation_id": "requested_behavior", "contract_quote": "Return one.", "rationale": "x"},  # expected on relation
        {"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": 1, "obligation_id": "input_preservation",
         "contract_quote": "Return one.", "rationale": "x"},                    # invented obligation
    ):
        assert vf.parse_probes({"probes": [bad]}, task) == ([], {"0": vf.parse_probes({"probes": [bad]}, task)[1]["0"]})
    with pytest.raises((ValueError, TypeError, KeyError)):
        vf.parse_probes({"probes": [{}, {}, {}]}, task)  # too many: the envelope is strict
    with pytest.raises(ValueError, match="Invalid entry point"):
        vf.probe_test_source("task_func; import os", probes)


def test_probe_outcomes_follow_the_official_harness_details():
    probes = [{"kind": "expected"}, {"kind": "expected"}]
    run = {"status": "fail", "metrics": {"details": {"test_probe_1": f"Traceback\nAssertionError: {vf.probe_mark(probes)} got 2 expected 1"}},
           "cleanup_confirmed": True}
    outcomes = vf.probe_outcomes(run, probes)
    assert outcomes[0] == {"outcome": "pass", "evidence": ""}
    assert outcomes[1] == {"outcome": "fail", "evidence": "AssertionError: verifier probe: got 2 expected 1"}
    # the un-nonced marker (or another probe set's nonce) is candidate-forgeable text: a raised call
    forged = vf.probe_outcomes({"status": "fail", "metrics": {"details": {"test_probe_1": "Traceback\nAssertionError: verifier probe: got 2 expected 1"}},
                                "cleanup_confirmed": True}, probes)
    assert forged[1]["outcome"] == "error"
    crashed = vf.probe_outcomes({"status": "fail", "metrics": {"details": {"ALL": "SyntaxError: bad"}}, "cleanup_confirmed": True}, probes)
    assert [o["outcome"] for o in crashed] == ["error", "error"]
    errored = vf.probe_outcomes({"status": "fail", "metrics": {"details": {"test_probe_0": "Traceback\nTypeError: x"}}, "cleanup_confirmed": True}, probes)
    assert errored[0]["outcome"] == "error" and errored[1]["outcome"] == "pass"
    # an AssertionError raised INSIDE the candidate function (e.g. `assert xs`) is a raised call, not a
    # verifier comparison failure: only the harness's own messages carry the marker
    inner = vf.probe_outcomes({"status": "fail", "metrics": {"details": {"test_probe_0": "Traceback\n  File \"__test__.py\", line 3, in task_func\n    assert xs\nAssertionError"}},
                               "cleanup_confirmed": True}, probes)
    assert inner[0]["outcome"] == "error"
    inner2 = vf.probe_outcomes({"status": "fail", "metrics": {"details": {"test_probe_1": "Traceback\nAssertionError: input must be non-empty"}},
                                "cleanup_confirmed": True}, probes)
    assert inner2[1]["outcome"] == "error"
    one = [{"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": 1,
            "obligation_id": "requested_behavior", "contract_quote": "x", "rationale": "x"}]
    assert vf.probe_mark(one) in vf.probe_test_source("f", one) and vf.harness_nonce(one) != vf.harness_nonce(one * 2)
    unknown = vf.probe_outcomes({"status": "unknown", "reason": "native_timeout", "cleanup_confirmed": True}, probes)
    assert all(o["outcome"] == "unknown" for o in unknown)
    with pytest.raises(Exception, match="native_cleanup_unconfirmed"):
        vf.probe_outcomes({"status": "unknown", "reason": "container_cleanup_unconfirmed", "cleanup_confirmed": False}, probes)


def test_research_urls_are_frozen_official_pages_only():
    vf.approved_url("https://docs.python.org/3.11/library/stdtypes.html#str.split")
    for url in ("https://docs.python.org/3.12/library/stdtypes.html", "https://example.com/3.11/library/stdtypes.html",
                "http://docs.python.org/3.11/library/stdtypes.html", "https://docs.python.org/3.11/library/stdtypes.html?q=1",
                "https://user:pw@docs.python.org/3.11/library/stdtypes.html"):
        with pytest.raises(ValueError):
            vf.approved_url(url)
    with pytest.raises(ValueError, match="credential-free"):
        vf.approved_proxy("http://user:pw@proxy:3128")
    assert vf.approved_proxy("http://httpproxy-headless.kubebrain.svc.pjlab.local:3128")


# ----------------------------------------------------------------------------- stage
def test_v10_stage_feeds_authorized_verifier_reports_to_analysts_only(tmp_path):
    value, panel = _auth10()
    api, execute = API(), executor()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=host_evaluate("bigcodebench"),
                       fixture_probe_executor=execute)
    assert result["status"] == "completed" and result["accepted_steps"] == 1
    step = result["verifier_steps"][0]
    assert step["policy_status"] == "update" and step["policy_changed"] and step["authorized"]
    assert step["rows"] == 8 and step["probes_executed"] == 8 and step["probes_failed"] == 3  # 3 host-failed train rows
    assert step["host_pass_rows"] == 5 and step["false_rejection_rate"] == 0.0
    assert step["detections"] == 3 and step["false_rejections"] == 0 and step["reports_with_feedback"] == 3
    # the analysts saw the report text and the rubric guidance; solver and verifier never saw analyst/label text
    analyst = "\n".join(api.prompts["reflection"])
    assert "Verifier (reusable rubric" in analyst and "got 0 expected 1" in analyst and "Return one." in analyst
    assert VERIFIER_PREAMBLE.split("{")[0].strip() in analyst and POLICY["mechanism"] in analyst
    assert all("Verifier (reusable rubric" not in p for p in api.prompts["solver"] + api.prompts["verifier"])
    # the probe executor ran on the parent's actual outputs with the reviewed probes, once per row, durably
    assert sorted(c[1] for c in execute.calls) == ["one"] * 5 + ["zero"] * 3 and all(c[2][0]["expected"] == 1 for c in execute.calls)
    assert len(list((tmp_path / "stage/verifier/0/executions").glob("*.intent.json"))) == 8
    assert len(list((tmp_path / "stage/verifier/0/executions").glob("*.json"))) == 16
    # the rubric this stage ends with is handed on, bound by hash
    handed = result["verifier_policy"]["bigcodebench"]
    assert handed["policy"] == POLICY and handed["policy_hash"] == digest(POLICY) and handed["status"] == "update"
    # sealed verifier records are governed artifacts of the stage
    assert any(k.startswith("verifier/0/reports/") for k in result["artifacts"])
    assert "verifier/0/policy.json" in result["artifacts"] and "host_only/verifier/0/calibration.json" in result["artifacts"]
    assert any(k.startswith("verifier/0/executions/") for k in result["artifacts"])
    identity = json.loads((tmp_path / "stage/identity.json").read_text())
    assert identity["verifier"] == vf.VERSION and identity["gate"] == "v9_family_sign_test_screen_then_fresh_confirmation_on_val"
    proposal_identity = json.loads((tmp_path / "stage/native/0/identity.json").read_text())
    assert proposal_identity["verifier_policy_hash"] == digest(POLICY) and proposal_identity["verifier_authorized"]
    assert "verifier_reports_hash" in proposal_identity
    # complete replay returns the identical sealed record without new calls or executions
    before = len(api.prompts["verifier"]), len(execute.calls)
    replay = run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=host_evaluate("bigcodebench"),
                       fixture_probe_executor=execute)
    assert replay == result and (len(api.prompts["verifier"]), len(execute.calls)) == before


def test_v10_calibration_withholds_an_unreliable_verifier_and_an_undefined_rate(tmp_path):
    # every probe fails, including on the five outputs the host passed: false-rejection rate 1.0 > 0.25
    value, panel = _auth10()
    api = API()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=host_evaluate("bigcodebench"),
                       fixture_probe_executor=executor(fail_on=("zero", "one")))
    step = result["verifier_steps"][0]
    assert step["false_rejections"] == 5 and step["false_rejection_rate"] == 1.0 and not step["authorized"]
    assert step["reports_with_feedback"] == 0
    # neither the reports nor the rejected rubric text reach the analysts; the stage still completes
    assert all("Verifier (reusable rubric" not in p and "VERIFIER REPORTS" not in p for p in api.prompts["reflection"])
    assert result["status"] == "completed"
    proposal_identity = json.loads((tmp_path / "stage/native/0/identity.json").read_text())
    assert proposal_identity["verifier_authorized"] is False and proposal_identity["verifier_policy_hash"] is None
    calibration = json.loads((tmp_path / "stage/host_only/verifier/0/calibration.json").read_text())
    assert calibration["authorized"] is False and len(calibration["dropped"]) == 5
    # the unauthorized rubric is not handed on: the next stage starts from the default again
    assert result["verifier_policy"]["bigcodebench"]["policy"] == vf.DEFAULT_POLICIES["bigcodebench"]
    # too few host-passed controls: the rate is undefined and nothing is authorized, even with detections
    value2, panel2 = _auth10(train=3)
    api2 = API()
    result2 = run_stage(value2, panel2, tmp_path / "stage2", fixture_api=api2,
                        fixture_evaluate=host_evaluate("bigcodebench", pass_ids={"0"}), fixture_probe_executor=executor())
    step2 = result2["verifier_steps"][0]
    assert step2["detections"] == 2 and step2["host_pass_rows"] == 1 and step2["false_rejection_rate"] is None
    assert not step2["authorized"] and step2["reports_with_feedback"] == 0


def test_v10_unreviewed_or_dropped_probes_are_never_executed_and_abstention_keeps_the_policy(tmp_path):
    value, panel = _auth10()
    api, execute = API(review_keep=False, synthesis_status="no_update"), executor()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=host_evaluate("bigcodebench"),
                       fixture_probe_executor=execute)
    step = result["verifier_steps"][0]
    assert execute.calls == [] and step["probes_executed"] == 0 and not step["authorized"]
    assert step["policy_status"] == "no_update" and not step["policy_changed"]
    assert result["verifier_policy"]["bigcodebench"]["policy"] == vf.DEFAULT_POLICIES["bigcodebench"]
    assert result["status"] == "completed"  # the Skill loop continues on the common scalar evidence


def test_v10_judge_path_for_text_domains_and_chained_policy(tmp_path):
    value, panel = _auth10(benchmark="searchqa")
    api = API()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=host_evaluate("searchqa"),
                       fixture_probe_executor=lambda *a: pytest.fail("no container for text domains"))
    step = result["verifier_steps"][0]
    assert step["authorized"] and step["detections"] == 3 and step["reports_with_feedback"] == 3
    assert step["arm"] == "adaptive_no_research" and step["configured_arm"] == "adaptive_research"
    analyst = "\n".join(api.prompts["reflection"])
    assert "FAIL answer form" in analyst and LABEL not in analyst
    # the judge never sees labels or analyst text; it sees the response and the rubric; the planner is
    # prompted as the no-research arm (no documentation URLs offered outside the coding domain)
    judge = [p for p in api.prompts["verifier"] if "anonymous_response" in p]
    assert len(judge) == 8 and sum("zero" in p for p in judge) == 3
    plan = [p for p in api.prompts["verifier"] if "experiment_arm" in p][0]
    assert "NO-RESEARCH arm" in plan and "docs.python.org" not in plan
    # a chained stage starts from the handed-on policy of its own domain only
    handed = result["verifier_policy"]
    value2, panel2 = _auth10(benchmark="searchqa", parent_policy=handed)
    api2 = API(plan_status="no_update")
    result2 = run_stage(value2, panel2, tmp_path / "stage2", fixture_api=api2, fixture_evaluate=host_evaluate("searchqa"),
                        fixture_probe_executor=lambda *a: pytest.fail("no container"))
    step2 = result2["verifier_steps"][0]
    assert step2["policy_status"] == "no_update" and step2["policy_hash"] == handed["searchqa"]["policy_hash"]
    policy_record = json.loads((tmp_path / "stage2/verifier/0/policy.json").read_text())
    assert policy_record["parent_policy_hash"] == handed["searchqa"]["policy_hash"]
    assert result2["verifier_policy"]["searchqa"]["policy"] == POLICY


def test_v10_rejects_fixture_hooks_outside_a_v10_fixture_run(tmp_path):
    value9, panel9 = auth(version="continual-learning-v9", policy=POLICY_V9)
    with pytest.raises(ValueError, match="Verifier fixtures belong to a v10 fixture run"):
        run_stage(value9, panel9, tmp_path / "s", fixture_api=API(), fixture_evaluate=evaluate("korbench"),
                  fixture_probe_executor=executor())
    value, panel = _auth10()
    with pytest.raises(ValueError, match="needs a probe executor"):
        run_stage(value, panel, tmp_path / "t", fixture_api=API(), fixture_evaluate=evaluate("bigcodebench"))


def test_v10_cleanup_failure_leaves_an_open_execution_intent_and_never_a_completed_handoff(tmp_path):
    """A probe container whose cleanup is unconfirmed stops the step; the intent stays open, so the
    accepted-prefix rule cannot turn the stage into a completed handoff."""
    from skillopt.continual_learning.skillopt import _evaluations_closed

    value, panel = _auth10(iterations=2)
    calls = {"n": 0}
    good = executor()

    def flaky(public, output, probes):
        calls["n"] += 1
        if calls["n"] > 8:  # second iteration: the first container of the step fails to clean up
            return {"status": "unknown", "score": None, "reason": "container_cleanup_unconfirmed", "metrics": {},
                    "cleanup_confirmed": False, "execution_costs": {"container_calls": 1}}
        return good(public, output, probes)

    result = run_stage(value, panel, tmp_path / "stage", fixture_api=API(), fixture_evaluate=host_evaluate("bigcodebench"),
                       fixture_probe_executor=flaky)
    assert result["status"] == "pending" and "native_cleanup_unconfirmed" in result["reason"]
    assert result["candidate_skill"] == ""  # the first iteration's acceptance is NOT kept
    intents = list((tmp_path / "stage/verifier/1/executions").glob("*.intent.json"))
    receipts = [p for p in (tmp_path / "stage/verifier/1/executions").glob("*.json") if not p.name.endswith(".intent.json")]
    assert len(intents) >= 1 and len(receipts) < len(intents)
    assert _evaluations_closed(tmp_path / "stage") is False


def test_v10_research_revisions_apply_only_when_the_whole_response_is_valid():
    probes = [{"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": 1, "obligation_id": "requested_behavior",
               "contract_quote": "Return one.", "rationale": "x"},
              {"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": 2, "obligation_id": "requested_behavior",
               "contract_quote": "Return one.", "rationale": "y"}]
    reviews = [{"index": 0, "keep": True, "reason": "r", "fact_question": "q0"},
               {"index": 1, "keep": True, "reason": "r", "fact_question": "q1"}]
    source = {"source_id": "s1", "url": "https://docs.python.org/3.11/library/functions.html", "status": "available",
              "text": "The documentation says that round() returns an integer when called with one argument."}
    responses = iter([
        {"urls": [source["url"]]},
        {"resolutions": [{"index": 0, "keep": True, "revised_expected": 99, "reason": "doc",
                          "citation": {"source_id": "s1", "quote": "round() returns an integer when called"}},
                         {"index": 1, "keep": False, "revised_expected": None, "citation": None}]},  # missing 'reason'
    ])

    class Runner(vf.Verifier):
        def __init__(self):
            self.step, self.arm, self.benchmark = 0, "adaptive_research", "bigcodebench"
            self.fetcher = lambda urls, root: [source]
            self.pending_reason = None
            self.root = __import__("pathlib").Path("/nonexistent")

        def call(self, stage, logical, system, user):
            return next(responses), {"stage": stage, "status": "parsed"}

        def _fetch(self, urls, namespace):
            return [source]

    record = {"trace": []}
    out = Runner()._research({"prompt": "Return one.", "entry_point": "f"}, probes, reviews, "t" * 64, record)
    assert out == reviews and probes[0]["expected"] == 1 and probes[1]["expected"] == 2
    assert record["trace"][-1]["status"] == "invalid_resolutions"


def test_probe_literals_round_trip_supplementary_plane_characters():
    value = {"s": "smile 😀 ok", "n": [1, 2.5, None, True]}
    namespace = {}
    exec("v = __import__('json').loads(" + vf._literal(value) + ")", namespace)
    assert namespace["v"] == value
    harness = vf.probe_test_source("f", [{"kind": "expected", "calls": [{"args": ["😀"], "kwargs": {}}], "expected": "😀",
                                          "obligation_id": "requested_behavior", "contract_quote": "x", "rationale": "x"}])
    compile(harness, "<h>", "exec")
    assert "😀" in harness


def test_v10_verifier_budget_is_reserved_against_submitted_intents(tmp_path):
    base, args = _args10()
    args["budget"]["max_verifier_calls"] = 3
    value = manifest(base, **args)
    gate = threading.Barrier(4, timeout=5)

    class SlowAPI(API):
        def call(self, system, user, kind, key, *, max_tokens, repeat):
            gate.wait()  # all four calls are in flight before any receipt is written
            return super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)

    ledger = Ledger(tmp_path / "ledger", value, SlowAPI())
    outcomes = {}

    def go(i):
        try:
            ledger.call("verifier", f"verifier:0:judge:{i}", "s", json.dumps({"anonymous_response": str(i), "task": {"question": "q"}}), 50)
            outcomes[i] = "ok"
        except BudgetExhausted:
            outcomes[i] = "budget"
            gate.abort()
        except threading.BrokenBarrierError:
            outcomes[i] = "broken"

    threads = [threading.Thread(target=go, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes.values()).count("budget") == 1  # the fourth submission is refused before any receipt
    assert len(list((tmp_path / "ledger/call_intents").glob("*.json"))) == 3


def test_v10_transport_failure_stops_the_stage_but_truncation_is_a_unit_result(tmp_path):
    class FailingAPI(API):
        def call(self, system, user, kind, key, *, max_tokens, repeat):
            row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
            if kind.endswith("verifier") and "anonymous_implementation" in user:
                return {**row, "ok": False, "response": None, "finish_reason": None}
            return row

    value, panel = _auth10()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=FailingAPI(),
                       fixture_evaluate=host_evaluate("bigcodebench"), fixture_probe_executor=executor())
    assert result["status"] == "pending" and result["reason"] == "verifier_call_failed"

    class TruncatingAPI(API):
        def call(self, system, user, kind, key, *, max_tokens, repeat):
            row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
            if kind.endswith("verifier") and "anonymous_implementation" in user:
                return {**row, "finish_reason": "length"}
            return row

    value2, panel2 = _auth10()
    result2 = run_stage(value2, panel2, tmp_path / "stage2", fixture_api=TruncatingAPI(),
                        fixture_evaluate=host_evaluate("bigcodebench"), fixture_probe_executor=executor())
    assert result2["status"] == "completed" and result2["verifier_steps"][0]["probes_executed"] == 0
    row = json.loads(next((tmp_path / "stage2/verifier/0/rows").glob("*.json")).read_text())
    assert row["trace"][0]["status"] == "truncated_or_empty"


def test_v10_bind_traces_rejects_a_report_that_is_not_the_sealed_file(tmp_path):
    from skillopt.continual_learning.skillopt import _bind_traces

    value, panel = _auth10()
    api, execute = API(), executor()
    run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=host_evaluate("bigcodebench"),
              fixture_probe_executor=execute)
    ledger = Ledger(tmp_path / "stage", value, None)
    policy = json.loads((tmp_path / "stage/verifier/0/policy.json").read_text())
    reports = {p.stem: json.loads(p.read_text()) for p in (tmp_path / "stage/verifier/0/reports").glob("*.json")}
    token, report = next((k, v) for k, v in reports.items() if v["feedback"])
    evaluation = next(json.loads(p.read_text()) for p in (tmp_path / "stage/evaluations").glob("*.json")
                      if json.loads(p.read_text())["record_hash"] == token)
    task = next(t for t in panel["tasks"] if digest(t) == evaluation["request"]["task_hash"])
    trace = {"Inputs": task["public"], "Generated Outputs": evaluation["prediction"]["output"],
             "Feedback": {"status": "fail", "score": 0.0, "verifier": report["feedback"]}, "evidence_hash": token}
    _bind_traces([trace], ledger, "", reports, 0, policy)  # the genuine sealed report binds
    forged = {**report, "feedback": report["feedback"] + " (edited)"}
    with pytest.raises(ValueError, match="differs from the sealed report"):
        _bind_traces([{**trace, "Feedback": {**trace["Feedback"], "verifier": forged["feedback"]}}], ledger, "",
                     {**reports, token: forged}, 0, policy)
    with pytest.raises(ValueError, match="fresh train rollout"):
        _bind_traces([trace], ledger, "", reports, 1, policy)  # another step: rollout-0 evidence is stale
    with pytest.raises(ValueError, match="differs from the sealed report"):
        _bind_traces([trace], ledger, "", reports, 0, {**policy, "policy_hash": "0" * 64})
    # the proposal boundary authenticates the policy itself against the step's sealed policy + summary
    from skillopt.continual_learning.skillopt import _authenticate_policy
    assert _authenticate_policy(ledger, 0, policy) == policy
    with pytest.raises(ValueError, match="not the step's authorized sealed policy"):
        _authenticate_policy(ledger, 0, {**policy, "policy": {**policy["policy"], "mechanism": "changed"}})
    with pytest.raises(ValueError, match="sealed policy and summary"):
        _authenticate_policy(ledger, 1, policy)
    # verifier inputs must be this step's rows of the current Skill: a stale rollout or another Skill is refused
    runner = vf.Verifier(value, ledger, tmp_path / "stage", 0, executor=execute)
    items = [{"role": "train", "task": task}]
    rows = [{"output": {"output": evaluation["prediction"]["output"], "evidence_hash": token}, "score": 0.0, "trajectory": {}}]
    assert len(runner._bound_pairs(items, rows, "")) == 1
    with pytest.raises(ValueError, match="this step's saved evidence"):
        runner._bound_pairs(items, rows, "another skill")
    with pytest.raises(ValueError, match="this step's saved evidence"):
        vf.Verifier(value, ledger, tmp_path / "stage", 1, executor=execute)._bound_pairs(items, rows, "")


def test_v10_long_texts_are_bounded_in_verifier_prompts_and_oversized_prompts_are_unit_results(tmp_path):
    long_response = "step " * 40000  # ~200k chars, like a long KOR-Bench reasoning response
    system, user = vf.judge_messages("korbench", {"rule": "Reply ONE.", "question": "What is the reply?"},
                                     long_response, POLICY)
    payload = json.loads(user)
    assert payload["response_truncated"] and "…[middle truncated]…" in payload["anonymous_response"]
    assert len(payload["anonymous_response"]) < vf.JUDGE_OUTPUT_HEAD + vf.JUDGE_OUTPUT_TAIL + 40
    assert len((system + user).encode()) <= vf.MAX_PROMPT_BYTES
    system, user = vf.probe_messages({"prompt": "Return one.", "entry_point": "f"}, "x" * 50000, POLICY, [])
    assert json.loads(user)["implementation_truncated"] and len(json.loads(user)["anonymous_implementation"]) == vf.PROBE_OUTPUT_CHARS
    # the development view clips long public texts; the judge keeps the full text for exact quotes
    view = vf._public_view("korbench", {"rule": "r" * 10000, "question": "q"})
    assert view["rule"].endswith("…[truncated]") and len(view["rule"]) < 4100
    assert vf._public_view("korbench", {"rule": "r" * 10000, "question": "q"}, full=True)["rule"] == "r" * 10000
    # an oversized prompt is recorded as a unit result, not raised
    value, panel = _auth10(benchmark="korbench")
    runner = vf.Verifier(value, Ledger(tmp_path / "ledger", value, API()), tmp_path / "stage", 0,
                         executor=lambda *a: pytest.fail("no container"))
    parsed, record = runner.call("judge", "x", "s", "u" * (vf.MAX_PROMPT_BYTES + 1))
    assert parsed is None and record["status"] == "prompt_too_large"


def test_v10_plan_urls_are_filtered_not_fatal_and_quotes_tolerate_rewrapped_whitespace(tmp_path):
    # the planner asks for an unapproved page next to an approved one: the approved page is fetched,
    # the other is recorded as rejected, and the proposal still proceeds to synthesis
    seen = {}

    class PlanAPI(API):
        def _verifier(self, payload):
            if "experiment_arm" in payload:
                return {"status": "investigate", "questions": ["q"],
                        "urls": ["https://docs.python.org/3.11/library/io.html", "https://docs.python.org/3.11/library/csv.html"]}
            return super()._verifier(payload)

    def fetcher(urls, root):
        seen["urls"] = list(urls)
        return [{"source_id": "s1", "url": u, "status": "available", "text": "csv documentation text " * 5} for u in urls]

    value, panel = _auth10()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=PlanAPI(), fixture_evaluate=host_evaluate("bigcodebench"),
                       fixture_probe_executor=executor(), fixture_fetcher=fetcher)
    policy = json.loads((tmp_path / "stage/verifier/0/policy.json").read_text())
    assert policy["status"] == "update" and seen["urls"] == ["https://docs.python.org/3.11/library/csv.html"]
    plan = next(t for t in policy["trace"] if t.get("stage") == "plan")
    assert plan["rejected_urls"] == ["https://docs.python.org/3.11/library/io.html"]
    assert result["verifier_steps"][0]["authorized"]
    # the no-research arm (text domains) drops every requested URL instead of failing the plan
    value2, panel2 = _auth10(benchmark="searchqa")
    run_stage(value2, panel2, tmp_path / "stage2", fixture_api=PlanAPI(), fixture_evaluate=host_evaluate("searchqa"),
              fixture_probe_executor=lambda *a: pytest.fail("no container"), fixture_fetcher=lambda *a: pytest.fail("no fetch"))
    policy2 = json.loads((tmp_path / "stage2/verifier/0/policy.json").read_text())
    assert policy2["status"] == "update" and policy2["sources"] == []
    assert len(next(t for t in policy2["trace"] if t.get("stage") == "plan")["rejected_urls"]) == 2
    # quotes: re-wrapped whitespace is tolerated, paraphrase is not
    task = "Return the sum of\n    the two numbers,\n    rounded to two decimals."
    assert vf.quote_in("the sum of the two numbers, rounded", task)
    assert not vf.quote_in("sum of both numbers", task) and not vf.quote_in("   ", task)


def test_v10_raised_probe_calls_are_diagnostic_only(tmp_path):
    """A raised call never authorizes a step (it may be an illegal probe input); in an authorized step it is
    reported with its caveat, and on host-passed outputs it is dropped without counting as a false rejection."""
    def raising(fail_on_assert=()):
        def execute(public, output, probes):
            details = {}
            if output == "zero":
                details["test_probe_0"] = "Traceback\nTypeError: mode() got an unexpected keyword argument 'keepdims'"
            if output in fail_on_assert:
                details["test_probe_0"] = f"Traceback\nAssertionError: {vf.probe_mark(probes)} got 0 expected 1"
            return {"status": "fail" if details else "pass", "score": 0.0 if details else 1.0,
                    "reason": "official_bigcodebench_untrusted_check",
                    "metrics": {"native_result": "fail" if details else "pass", "details": details},
                    "cleanup_confirmed": True, "execution_costs": {"container_calls": 1}}
        return execute

    # only raised calls on the failed rows: zero detections, unauthorized, nothing reaches the analysts
    value, panel = _auth10()
    api = API()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=host_evaluate("bigcodebench"),
                       fixture_probe_executor=raising())
    step = result["verifier_steps"][0]
    assert step["probes_error"] == 3 and step["probes_failed"] == 0 and step["detections"] == 0 and not step["authorized"]
    assert all("ERROR (the call raised" not in p for p in api.prompts["reflection"])
    calibration = json.loads((tmp_path / "stage/host_only/verifier/0/calibration.json").read_text())
    assert calibration["raised_on_host_failed_rows"] == 3 and calibration["raised_on_host_passed_rows"] == 0

    # raised calls on host-PASSED outputs are not false rejections either, but are dropped from those rows
    def raising_on_pass(public, output, probes):
        details = {"test_probe_0": "Traceback\nTypeError: Input is not a Pandas DataFrame."} if output == "one" else {
            "test_probe_0": f"Traceback\nAssertionError: {vf.probe_mark(probes)} got 0 expected 1"}
        return {"status": "fail", "score": 0.0, "reason": "official_bigcodebench_untrusted_check",
                "metrics": {"native_result": "fail", "details": details}, "cleanup_confirmed": True,
                "execution_costs": {"container_calls": 1}}

    value2, panel2 = _auth10()
    api2 = API()
    result2 = run_stage(value2, panel2, tmp_path / "stage2", fixture_api=api2, fixture_evaluate=host_evaluate("bigcodebench"),
                        fixture_probe_executor=raising_on_pass)
    step2 = result2["verifier_steps"][0]
    # v6: an error-only host-passed row is no control (v4 counted it, which deflated pooled rates): with zero decided
    # controls the false-rejection rate is undefined and the step is unauthorized despite three detections
    assert step2["detections"] == 3 and step2["false_rejections"] == 0 and step2["host_pass_rows"] == 0
    assert step2["false_rejection_rate"] is None and not step2["authorized"]
    calibration2 = json.loads((tmp_path / "stage2/host_only/verifier/0/calibration.json").read_text())
    assert calibration2["raised_on_host_passed_rows"] == 5 and len(calibration2["dropped"]) == 5
    pass_reports = [json.loads(p.read_text()) for p in (tmp_path / "stage2/verifier/0/reports").glob("*.json")]
    dropped = set(calibration2["dropped"])  # the host-passed rows: their raised calls are removed from the reports
    assert sum(r["evidence_hash"] in dropped for r in pass_reports) == 5
    assert all(all(pr["outcome"] == "pass" for pr in r["probes"]) for r in pass_reports if r["evidence_hash"] in dropped)

    # in an authorized step (assertion detections present), a raised call on a failed row is shown with its caveat
    value3, panel3 = _auth10()
    api3 = API()
    run_stage(value3, panel3, tmp_path / "stage3", fixture_api=api3, fixture_evaluate=host_evaluate("bigcodebench", pass_ids={"0", "1", "2", "3", "4"}),
              fixture_probe_executor=raising(fail_on_assert=("zero",)))
    # here every failed row has an assertion failure (the last writer wins in the fixture), so make one row raise instead
    def mixed(public, output, probes):
        if output == "zero" and public is not None and probes and probes[0].get("rationale") == "The contract fixes the return value." and mixed.count == 0:
            mixed.count += 1
            return raising()(public, output, probes)
        return raising(fail_on_assert=("zero",))(public, output, probes)
    mixed.count = 0
    value4, panel4 = _auth10()
    api4 = API()
    result4 = run_stage(value4, panel4, tmp_path / "stage4", fixture_api=api4, fixture_evaluate=host_evaluate("bigcodebench"),
                        fixture_probe_executor=mixed)
    step4 = result4["verifier_steps"][0]
    assert step4["authorized"] and step4["detections"] == 2 and step4["probes_error"] == 1
    analyst = "\n".join(api4.prompts["reflection"])
    assert "ERROR (the call raised" in analyst and "keepdims" in analyst and "FAIL call" in analyst
    assert "not a verified contract violation" in analyst


DOC_TEXT = ("math.sqrt(x)\nReturn the square root of x.\nThe current implementation will raise\nValueError for invalid "
            "operations like sqrt(-1.0) or log(0.0)\n(where C99 Annex F recommends signaling invalid operation).")
REWRAPPED = "The current implementation will raise ValueError for invalid operations like sqrt(-1.0) or log(0.0)"


def test_v10_citations_tolerate_page_line_breaks_and_a_rejected_synthesis_gets_one_repair(tmp_path):
    """Chain d, BCB step 0 (10/7): three genuine documentation sentences were rejected because the extracted
    page keeps hard line breaks the model rewrote as spaces, and the rubric update was lost without a repair.
    Citations now match with whitespace collapsed (wording still literal), and a strictly invalid synthesis is
    sent back exactly once with its validation error."""
    class CiteAPI(API):
        def __init__(self, first, second):
            super().__init__()
            self.first, self.second, self.synthesis_calls = first, second, []

        def _verifier(self, payload):
            if "experiment_arm" in payload:
                return {"status": "investigate", "questions": ["q"], "urls": ["https://docs.python.org/3.11/library/math.html"]}
            if "reflection" in payload:
                self.synthesis_calls.append(payload.get("repair"))
                quote = self.second if "repair" in payload else self.first
                return {"status": "update", "policy": POLICY, "reason": "grounded",
                        "citations": [{"source_id": "s1", "quote": quote}]}
            return super()._verifier(payload)

    def fetcher(urls, root):
        return [{"source_id": "s1", "url": u, "status": "available", "text": DOC_TEXT} for u in urls]

    # a paraphrase is rejected, the repair carries the exact error, and the re-wrapped literal quote is accepted
    api = CiteAPI("the implementation raises ValueError on negative inputs such as sqrt(-1)", REWRAPPED)
    value, panel = _auth10()
    run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=host_evaluate("bigcodebench"),
              fixture_probe_executor=executor(), fixture_fetcher=fetcher)
    policy = json.loads((tmp_path / "stage/verifier/0/policy.json").read_text())
    assert policy["status"] == "update" and policy["citations"] == [{"source_id": "s1", "quote": REWRAPPED}]
    assert policy["verifier_version"] == vf.VERSION == "rubric-probe-research-verifier-v7"
    assert api.synthesis_calls[0] is None and "Citation is not an exact available source excerpt" in api.synthesis_calls[1]["validation_error"]
    assert "previous_proposal" in api.synthesis_calls[1] and len(api.synthesis_calls) == 2
    repairs = [t for t in policy["trace"] if t.get("repair_of")]
    assert len(repairs) == 1 and repairs[0]["stage"] == "policy" and repairs[0]["status"] == "parsed"
    intents = [json.loads(p.read_text()) for p in (tmp_path / "stage/call_intents").glob("*.json")]
    ledger_logicals = sorted(i["logical_id"] for i in intents if i["role"] == "verifier" and ":policy:" in i["logical_id"])
    assert ledger_logicals == ["verifier:0:policy:plan", "verifier:0:policy:synthesis", "verifier:0:policy:synthesis_repair"]

    # a second rejection leaves the policy invalid (parent policy kept) with the error recorded; no third call
    api2 = CiteAPI("a fabricated sentence that the page never contains", "another fabricated sentence here")
    value2, panel2 = _auth10()
    run_stage(value2, panel2, tmp_path / "stage2", fixture_api=api2, fixture_evaluate=host_evaluate("bigcodebench"),
              fixture_probe_executor=executor(), fixture_fetcher=fetcher)
    policy2 = json.loads((tmp_path / "stage2/verifier/0/policy.json").read_text())
    assert policy2["status"] == "invalid" and policy2["policy"] == vf.default_policy_record("bigcodebench")["policy"]
    assert policy2["failure_detail"] == "Citation is not an exact available source excerpt" and "one repair call" in policy2["reason"]
    assert len(api2.synthesis_calls) == 2 and sum(1 for t in policy2["trace"] if t.get("stage") == "policy") == 3

    # the same literal rule applies to research citations (whitespace collapsed, wording literal)
    available = {"s1": {"source_id": "s1", "status": "available", "text": DOC_TEXT}}
    assert vf._citation({"source_id": "s1", "quote": REWRAPPED}, available)["quote"] == REWRAPPED
    with pytest.raises(ValueError, match="exact available source excerpt"):
        vf._citation({"source_id": "s1", "quote": "raise ValueError for invalid operations like sqrt(-2.0)"}, available)


def _run_harness(code, probes):
    """The generated harness run in-process the way the official untrusted check reports it."""
    import types
    import unittest

    module = types.ModuleType("__test__")
    exec(compile(code + "\n" + vf.probe_test_source("task_func", probes), "__test__.py", "exec"), module.__dict__)
    result = unittest.TestResult()
    unittest.defaultTestLoader.loadTestsFromTestCase(module.TestCases).run(result)
    details = {test._testMethodName: trace for test, trace in result.failures + result.errors}
    return {"status": "fail" if details else "pass", "score": float(not details), "metrics": {"details": details},
            "cleanup_confirmed": True}


RAISES_TASK = ("Return the square root of n. The function should raise the exception for: ValueError: If n is "
               "negative. This function will raise Value Error if n is not a number.")


def _raises(name="ValueError", args=(-1,), quote="ValueError: If n is negative."):
    return {"kind": "raises", "calls": [{"args": list(args), "kwargs": {}}], "expected": name,
            "obligation_id": "requested_behavior", "contract_quote": quote, "rationale": "documented error"}


def test_v10_raises_probes_port_the_pilot_expected_exception():
    """Chain e (10/7): 58 of 70 raised probe calls were the evolved rubric deliberately checking documented
    exceptions, encoded as expected values ("ValueError", {"exception_type": "ValueError"}); a correct raise was
    then reported to the analyst as an ERROR. v4 ports the pilot's expected_exception as kind `raises`."""
    ok, rejected = vf.parse_probes({"probes": [_raises(), _raises(args=["x"], quote="This function will raise Value Error if n is not a number.")]},
                                   RAISES_TASK)
    assert rejected == {} and [p["kind"] for p in ok] == ["raises", "raises"]
    for bad, reason in (
        (_raises(name="requests.HTTPError"), "builtin exception"),
        (_raises(name="SystemExit"), "builtin exception"),
        (_raises(name="AssertionError"), "builtin exception"),
        (_raises(name="TypeError"), "must state the expected exception"),
        ({**_raises(), "calls": [{"args": [-1], "kwargs": {}}, {"args": [-2], "kwargs": {}}]}, "Call count"),
        ({**_raises(), "kind": "expected", "expected": "ValueError"}, "needs kind raises"),
        ({**_raises(), "kind": "expected", "expected": {"exception_type": "ValueError"}}, "needs kind raises"),
    ):
        kept, why = vf.parse_probes({"probes": [bad]}, RAISES_TASK)
        assert kept == [] and reason in why["0"], (bad, why)
    assert vf.parse_probes({"probes": [{**_raises(), "kind": "expected", "expected": {"root": 1.0}}]}, RAISES_TASK)[1] == {}

    correct = "def task_func(n):\n    if not isinstance(n, (int, float)) or n < 0:\n        raise ValueError('bad n')\n    return n ** 0.5"
    subclass = "class NegativeError(ValueError):\n    pass\n\ndef task_func(n):\n    raise NegativeError('negative')"
    silent = "def task_func(n):\n    return 0"
    other = "def task_func(n):\n    raise TypeError('unsupported operand')"
    inner_assert = "def task_func(n):\n    assert n >= 0\n    return n"
    outcomes = {name: vf.probe_outcomes(_run_harness(code, [_raises()]), [_raises()])[0]
                for name, code in (("correct", correct), ("subclass", subclass), ("silent", silent), ("other", other),
                                   ("inner_assert", inner_assert))}
    assert outcomes["correct"] == {"outcome": "pass", "evidence": ""} and outcomes["subclass"]["outcome"] == "pass"
    assert outcomes["silent"]["outcome"] == "fail" and "expected ValueError to be raised; the call returned 0" in outcomes["silent"]["evidence"]
    assert outcomes["other"]["outcome"] == "error" and "TypeError" in outcomes["other"]["evidence"]
    assert outcomes["inner_assert"]["outcome"] == "error"  # the candidate's own assert is not the harness's

    # results the harness cannot compare are undecided (unknown), never a contract violation
    expected = {"kind": "expected", "calls": [{"args": [4], "kwargs": {}}], "expected": {"root": 2.0},
                "obligation_id": "requested_behavior", "contract_quote": "Return the square root of n.", "rationale": "r"}
    relation = {**expected, "kind": "equal_relation", "expected": None, "calls": [{"args": [4], "kwargs": {}}] * 2}
    plot = "class Axes:\n    pass\n\ndef task_func(n):\n    return {'root': n ** 0.5}, Axes()"
    run = _run_harness(plot, [expected, relation])
    assert [o["outcome"] for o in vf.probe_outcomes(run, [expected, relation])] == ["unknown", "unknown"]
    assert vf.UNREPRESENTABLE_MARK in vf._HARNESS
    numpy_like = "class Arr:\n    def tolist(self):\n        return [1, 2]\n\ndef task_func(n):\n    return {'root': Arr()}"
    assert vf.probe_outcomes(_run_harness(numpy_like, [{**expected, "expected": {"root": [1, 2]}}]), [expected])[0]["outcome"] == "pass"

    # the analyst-facing text describes the documented exception, not a product fault
    policy = vf.default_policy_record("bigcodebench")
    text = vf.render_feedback("bigcodebench", policy, [
        {**_raises(), "outcome": "fail", "evidence": outcomes["silent"]["evidence"]},
        {**_raises(), "outcome": "error", "evidence": "TypeError: unsupported operand"}])
    assert "FAIL call args=[-1]; the task documents that this call raises ValueError" in text
    assert "raised a different exception than documented" in text


def test_v10_unknown_probe_outcomes_are_recorded_but_not_shown_to_the_analyst(tmp_path):
    def undecided(public, output, probes):
        details = {"test_probe_0": "Traceback\nTypeError: " + vf.unrepresentable_mark(probes) + ": Axes"} if output == "zero" else {}
        return {"status": "fail" if details else "pass", "score": 0.0 if details else 1.0,
                "reason": "official_bigcodebench_untrusted_check",
                "metrics": {"native_result": "fail" if details else "pass", "details": details},
                "cleanup_confirmed": True, "execution_costs": {"container_calls": 1}}

    value, panel = _auth10()
    api = API()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=host_evaluate("bigcodebench"),
                       fixture_probe_executor=undecided)
    step = result["verifier_steps"][0]
    assert step["probes_unknown"] == 3 and step["detections"] == 0 and not step["authorized"]
    summary = json.loads((tmp_path / "stage/verifier/0/summary.json").read_text())
    assert summary["probes_by_kind"] == {"expected": {"pass": 5, "unknown": 3}}
    reports = [json.loads(p.read_text()) for p in (tmp_path / "stage/verifier/0/reports").glob("*.json")]
    assert all(r["feedback"] is None for r in reports)
    assert sum(p["outcome"] == "unknown" for r in reports for p in r["probes"]) == 3


def test_v10_candidate_text_never_decides_a_probe_outcome():
    """Codex round 10: outcome classification must not trust candidate-controlled exception messages or
    return values; only the harness's nonce-marked lines decide fail/unknown."""
    root = {"kind": "expected", "calls": [{"args": [4], "kwargs": {}}], "expected": {"root": 2.0},
            "obligation_id": "requested_behavior", "contract_quote": "Return the square root of n.", "rationale": "r"}
    cases = {
        # forged harness text in an exception the candidate raises: a raised call, never a detection
        "forged_assert": ("def task_func(n):\n    raise AssertionError('verifier probe: got 1 expected 2')", [root], "error"),
        "forged_in_message": ("def task_func(n):\n    raise ValueError('x\\nAssertionError: verifier probe: got 1')", [root], "error"),
        # forged 'unrepresentable' text in a RETURNED value is still a comparison failure, never undecided
        "forged_unknown_return": ("def task_func(n):\n    return 'TypeError: verifier harness: result is not JSON-expressible: X'",
                                  [root], "fail"),
        "forged_unknown_raises": ("def task_func(n):\n    return 'verifier harness: result is not JSON-expressible'",
                                  [_raises()], "fail"),
        # a line separator inside a returned string must not split the harness's own message
        "line_separator": ("def task_func(n):\n    return {'root': 'a\\u2028b'}", [root], "fail"),
        "raises_other_with_forged_text": ("def task_func(n):\n    raise KeyError('AssertionError: verifier probe: x')",
                                          [_raises()], "error"),
    }
    for name, (code, probes, expected) in cases.items():
        outcome = vf.probe_outcomes(_run_harness(code, probes), probes)[0]
        assert outcome["outcome"] == expected, (name, outcome)
        if expected == "fail":
            assert outcome["evidence"].startswith("AssertionError: verifier probe: ") and vf.harness_nonce(probes) not in outcome["evidence"]

    # research cannot revise an expected value into an exception encoding (the guard of the parser)
    probes = [{"kind": "expected", "calls": [{"args": [], "kwargs": {}}], "expected": 1, "obligation_id": "requested_behavior",
               "contract_quote": "Return one.", "rationale": "x"}]
    reviews = [{"index": 0, "keep": True, "reason": "r", "fact_question": "q0"}]
    source = {"source_id": "s1", "url": "https://docs.python.org/3.11/library/functions.html", "status": "available",
              "text": "The documentation says that round() returns an integer when called with one argument."}
    responses = iter([{"urls": [source["url"]]},
                      {"resolutions": [{"index": 0, "keep": True, "revised_expected": {"exception_type": "ValueError"}, "reason": "doc",
                                        "citation": {"source_id": "s1", "quote": "round() returns an integer when called"}}]}])

    class Runner(vf.Verifier):
        def __init__(self):
            self.step, self.arm, self.benchmark = 0, "adaptive_research", "bigcodebench"
            self.pending_reason = None
            self.root = __import__("pathlib").Path("/nonexistent")

        def call(self, stage, logical, system, user):
            return next(responses), {"stage": stage, "status": "parsed"}

        def _fetch(self, urls, namespace):
            return [source]

    record = {"trace": []}
    assert Runner()._research({"prompt": "Return one.", "entry_point": "f"}, probes, reviews, "t" * 64, record) == reviews
    assert probes[0]["expected"] == 1 and record["trace"][-1]["status"] == "invalid_resolutions"
    # dict encodings count only with exception-like keys
    assert vf._encodes_exception({"exception_type": "ValueError"}) and not vf._encodes_exception({"label": "ValueError"})


MALFORMED_PLAN = '{"status": "investigate", "questions": ["rows like item-1 ("<answer>x</answer>") still fail"], "urls": []}'


class FlakyAPI(API):
    """Replaces the verifier reply of the named payload kinds by a malformed text: on the first attempt only,
    or on the format retry too (``twice``); records every verifier system prompt."""

    def __init__(self, broken, *, twice=False):
        super().__init__()
        self.broken, self.twice, self.systems = broken, twice, []

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if kind.endswith("verifier"):
            with self.lock:
                self.systems.append(system)
            payload = json.loads(user)
            for marker, bad in self.broken.items():
                if marker in payload and ("FORMAT RETRY" not in system or self.twice):
                    return {**row, "response": bad}
        return row


def _verifier_logicals(stage_root):
    intents = [json.loads(p.read_text()) for p in (stage_root / "call_intents").glob("*.json")]
    return sorted(i["logical_id"] for i in intents if i["role"] == "verifier")


def test_v10_unparseable_verifier_replies_get_exactly_one_format_retry(tmp_path):
    """Chain e, SearchQA step 0 (10/7): the plan reply quoted ("<answer>Strawberry</answer>") without escaping
    the inner quotes, so the plan was lost and the step ran on its parent policy (8 of 1,505 real verifier
    replies were unparseable). Every verifier JSON call now gets exactly one format retry -- a fresh sample of
    the same request with the reason in the system prompt; a second failure is the old unit result, and a
    truncated reply is never retried."""
    # a malformed plan is retried once and the proposal proceeds; the trace references the first reply
    api = FlakyAPI({"experiment_arm": MALFORMED_PLAN})
    value, panel = _auth10()
    run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=host_evaluate("bigcodebench"),
              fixture_probe_executor=executor())
    policy = json.loads((tmp_path / "stage/verifier/0/policy.json").read_text())
    assert policy["status"] == "update" and policy["verifier_version"] == "rubric-probe-research-verifier-v7"
    plan = policy["trace"][0]
    assert plan["status"] == "parsed" and plan["json_retry_of"]["error"] == "NativeJSONError"
    assert plan["json_retry_of"]["reason"].startswith("invalid_json_document: Expecting ',' delimiter at character ")
    assert plan["json_retry_of"]["request_hash"] != plan["request_hash"]
    logicals = _verifier_logicals(tmp_path / "stage")
    assert [x for x in logicals if ":policy:" in x] == [
        "verifier:0:policy:plan", "verifier:0:policy:plan:json-retry:1", "verifier:0:policy:synthesis"]
    retried = [s for s in api.systems if "FORMAT RETRY" in s]
    assert len(retried) == 1 and "Expecting ',' delimiter" in retried[0] and "x</answer>" not in retried[0]

    # a second malformed reply leaves the plan failed exactly as before -- and no third call
    api2 = FlakyAPI({"experiment_arm": MALFORMED_PLAN}, twice=True)
    value2, panel2 = _auth10()
    run_stage(value2, panel2, tmp_path / "stage2", fixture_api=api2, fixture_evaluate=host_evaluate("bigcodebench"),
              fixture_probe_executor=executor())
    policy2 = json.loads((tmp_path / "stage2/verifier/0/policy.json").read_text())
    assert policy2["status"] == "invalid" and policy2["failure_detail"] == "Plan call failed"
    assert policy2["policy"] == vf.default_policy_record("bigcodebench")["policy"] and "one format retry" in policy2["reason"]
    assert policy2["trace"] == [{**policy2["trace"][0], "status": "invalid_json"}] and "json_retry_of" in policy2["trace"][0]
    assert [x for x in _verifier_logicals(tmp_path / "stage2") if ":policy:" in x] == [
        "verifier:0:policy:plan", "verifier:0:policy:plan:json-retry:1"]

    # prose after a valid probe object: retried, and the retried probes are executed
    api3 = FlakyAPI({"anonymous_implementation": '{"probes": []}\n\nThe task generates a plot, so no probe.'})
    value3, panel3 = _auth10()
    result3 = run_stage(value3, panel3, tmp_path / "stage3", fixture_api=api3, fixture_evaluate=host_evaluate("bigcodebench"),
                        fixture_probe_executor=executor())
    step3 = result3["verifier_steps"][0]
    assert step3["probes_executed"] == 8 and step3["authorized"] and step3["detections"] == 3
    rows = [json.loads(p.read_text()) for p in (tmp_path / "stage3/verifier/0/rows").glob("*.json")]
    probe_records = [t for r in rows for t in r["trace"] if t.get("stage") == "probes"]
    assert len(probe_records) == 8 and all(t["status"] == "parsed" and "Extra data" in t["json_retry_of"]["reason"]
                                           for t in probe_records)

    # the text-domain judge: a garbled key on every first reply; the retried verdicts decide as before
    api4 = FlakyAPI({"anonymous_response": '{"checks": [{"obligation ":", "contract_quote": "x"}]}'})
    value4, panel4 = _auth10(benchmark="searchqa")
    result4 = run_stage(value4, panel4, tmp_path / "stage4", fixture_api=api4, fixture_evaluate=host_evaluate("searchqa"),
                        fixture_probe_executor=lambda *a: pytest.fail("no container for text domains"))
    step4 = result4["verifier_steps"][0]
    assert step4["authorized"] and step4["detections"] == 3 and step4["reports_with_feedback"] == 3
    assert sum(":judge:" in x and x.endswith(":json-retry:1") for x in _verifier_logicals(tmp_path / "stage4")) == 8

    # truncation is a budget outcome, never retried
    class TruncatingAPI(API):
        def call(self, system, user, kind, key, *, max_tokens, repeat):
            row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
            if kind.endswith("verifier") and "anonymous_implementation" in user:
                return {**row, "finish_reason": "length"}
            return row

    value5, panel5 = _auth10()
    run_stage(value5, panel5, tmp_path / "stage5", fixture_api=TruncatingAPI(), fixture_evaluate=host_evaluate("bigcodebench"),
              fixture_probe_executor=executor())
    assert not any("json-retry" in x for x in _verifier_logicals(tmp_path / "stage5"))

    # the reason is content-free: fixed parser texts and a position, never the reply's own words
    assert vf._json_reason(ValueError("JSON object required"), "[1]") == "JSON object required"
    assert vf._json_reason(vf.NativeJSONError("invalid_json_envelope"), "```json\n{]\n```") == "invalid_json_envelope"


def test_v10_format_retry_replays_after_an_interruption_and_a_retry_over_budget_is_a_stop(tmp_path, monkeypatch):
    """Codex round 13 (P3): the retry request is a pure function of the sealed first receipt, so an interruption
    between that receipt and the retry intent resumes without a second first call; a retry beyond the verifier
    budget is the ordinary budget stop; the synthesis path is bounded at four calls."""
    class Crash(Exception):
        pass

    value, panel = _auth10()
    user = json.dumps({"experiment_arm": "adaptive_research", "view": {}})
    root = tmp_path / "stage"
    root.mkdir()
    api = FlakyAPI({"experiment_arm": MALFORMED_PLAN})
    original = vf.Verifier._check_abort
    seen = {"n": 0}

    def crash_before_retry(self):
        seen["n"] += 1
        if seen["n"] == 2:  # the abort check between the first receipt and the retry intent
            raise Crash()
        return original(self)

    monkeypatch.setattr(vf.Verifier, "_check_abort", crash_before_retry)
    with pytest.raises(Crash):
        vf.Verifier(value, Ledger(root, value, api), root, 0).call("policy", "plan", "sys", user)
    monkeypatch.setattr(vf.Verifier, "_check_abort", original)
    assert len(api.systems) == 1 and _verifier_logicals(root) == ["verifier:0:policy:plan"]
    api2 = FlakyAPI({"experiment_arm": MALFORMED_PLAN})
    plan, record = vf.Verifier(value, Ledger(root, value, api2), root, 0).call("policy", "plan", "sys", user)
    assert plan["status"] == "investigate" and record["status"] == "parsed" and record["json_retry_of"]["error"] == "NativeJSONError"
    assert len(api2.systems) == 1 and "FORMAT RETRY" in api2.systems[0]  # the first reply came from its receipt
    assert _verifier_logicals(root) == ["verifier:0:policy:plan", "verifier:0:policy:plan:json-retry:1"]

    # a retry beyond max_verifier_calls is the ordinary verifier budget stop (a LearningPending)
    base, args = _args10()
    args["budget"]["max_verifier_calls"] = 1
    tiny = manifest(base, **args)
    root2 = tmp_path / "tiny"
    root2.mkdir()
    with pytest.raises(BudgetExhausted, match="max_verifier_calls"):
        vf.Verifier(tiny, Ledger(root2, tiny, FlakyAPI({"experiment_arm": MALFORMED_PLAN})), root2, 0).call(
            "policy", "plan", "sys", user)
    result = run_stage(tiny, panel, tmp_path / "stage3", fixture_api=FlakyAPI({"experiment_arm": MALFORMED_PLAN}),
                       fixture_evaluate=host_evaluate("bigcodebench"), fixture_probe_executor=executor())
    assert result["status"] == "pending" and "max_verifier_calls" in result["reason"]

    # synthesis: malformed -> retried proposal fails validation -> repair malformed -> retried repair accepted
    class SynthAPI(FlakyAPI):
        def _verifier(self, payload):
            if "experiment_arm" in payload:
                return {"status": "investigate", "questions": ["q"], "urls": ["https://docs.python.org/3.11/library/math.html"]}
            if "reflection" in payload:
                quote = REWRAPPED if "repair" in payload else "a paraphrase that the page never contains at all"
                return {"status": "update", "policy": POLICY, "reason": "grounded", "citations": [{"source_id": "s1", "quote": quote}]}
            return super()._verifier(payload)

    value4, panel4 = _auth10()
    run_stage(value4, panel4, tmp_path / "stage4", fixture_api=SynthAPI({"reflection": "not json at all"}),
              fixture_evaluate=host_evaluate("bigcodebench"), fixture_probe_executor=executor(),
              fixture_fetcher=lambda urls, root: [{"source_id": "s1", "url": u, "status": "available", "text": DOC_TEXT} for u in urls])
    policy = json.loads((tmp_path / "stage4/verifier/0/policy.json").read_text())
    assert policy["status"] == "update" and policy["citations"] == [{"source_id": "s1", "quote": REWRAPPED}]
    assert [x for x in _verifier_logicals(tmp_path / "stage4") if ":policy:" in x] == [
        "verifier:0:policy:plan", "verifier:0:policy:synthesis", "verifier:0:policy:synthesis:json-retry:1",
        "verifier:0:policy:synthesis_repair", "verifier:0:policy:synthesis_repair:json-retry:1"]
    synthesis = [t for t in policy["trace"] if t.get("stage") == "policy" and "json_retry_of" in t]
    assert len(synthesis) == 2 and "repair_of" in synthesis[1] and "repair_of" not in synthesis[0]


# ----------------------------------------------------------------------------- v6 (plan repair, structure, admission)
def test_v6_a_schema_invalid_plan_gets_one_field_specific_repair(tmp_path):
    """Chain f, BCB step 2 (10/7): a parseable plan without its `status` field dropped the step to the parent
    policy. v6 sends a parsed but schema-invalid plan back exactly once with a field-specific error."""
    import re

    class PlanAPI(API):
        def __init__(self, first, second=None):
            super().__init__()
            self.first, self.second, self.plans = first, second, []

        def _verifier(self, payload):
            if "experiment_arm" in payload:
                self.plans.append(payload.get("repair"))
                return self.second if "repair" in payload else self.first
            return super()._verifier(payload)

    good = {"status": "investigate", "questions": ["q"], "urls": []}
    api = PlanAPI({"questions": ["q"], "urls": []}, good)
    value, panel = _auth10()
    run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=host_evaluate("bigcodebench"),
              fixture_probe_executor=executor())
    policy = json.loads((tmp_path / "stage/verifier/0/policy.json").read_text())
    assert policy["status"] == "update" and api.plans[0] is None
    assert api.plans[1]["validation_error"] == "ValueError: missing required field(s): status"
    assert api.plans[1]["previous_plan"] == {"questions": ["q"], "urls": []}
    repairs = [t for t in policy["trace"] if t.get("repair_of")]
    assert len(repairs) == 1 and repairs[0]["status"] == "parsed" and "missing required field" in repairs[0]["repair_of"]
    assert [x for x in _verifier_logicals(tmp_path / "stage") if ":policy:" in x] == [
        "verifier:0:policy:plan", "verifier:0:policy:plan_repair", "verifier:0:policy:synthesis"]

    # a repair that is still invalid keeps the parent policy with the field-specific detail; no third plan request
    api2 = PlanAPI({"questions": ["q"], "urls": []}, {"status": "maybe", "questions": [], "urls": []})
    value2, panel2 = _auth10()
    run_stage(value2, panel2, tmp_path / "stage2", fixture_api=api2, fixture_evaluate=host_evaluate("bigcodebench"),
              fixture_probe_executor=executor())
    policy2 = json.loads((tmp_path / "stage2/verifier/0/policy.json").read_text())
    assert policy2["status"] == "invalid" and len(api2.plans) == 2
    assert policy2["failure_detail"] == "status must be one of investigate, no_update, insufficient_evidence"

    # a valid abstention is never repaired
    api3 = PlanAPI({"status": "no_update", "questions": [], "urls": []})
    value3, panel3 = _auth10()
    run_stage(value3, panel3, tmp_path / "stage3", fixture_api=api3, fixture_evaluate=host_evaluate("bigcodebench"),
              fixture_probe_executor=executor())
    assert json.loads((tmp_path / "stage3/verifier/0/policy.json").read_text())["status"] == "no_update" and len(api3.plans) == 1

    for bad, message in (({"status": "investigate", "questions": [], "urls": [], "why": 1}, "unexpected field(s): why"),
                         ({"status": "investigate", "questions": ["q"] * 4, "urls": []}, "questions must be a list"),
                         ({"status": "investigate", "questions": [], "urls": "x"}, "urls must be a list"),
                         ([], "the plan must be one JSON object")):
        with pytest.raises(ValueError, match=re.escape(message)):
            vf._validated_plan(bad)


STRUCT_TASK = ("Create a goal report. Returns: tuple: (pd.DataFrame, matplotlib.axes.Axes). The DataFrame has the "
               "columns 'Team', 'Goals' and the index 'A', 'B'. The plot has the title 'Goals per team', x-label 'Team' "
               "and y-label 'Goals'. The function also builds a numpy array of shape (2, 3).")


def _structure(expected, select=None, quote=STRUCT_TASK, args=(2,)):
    return {"kind": "structure", "calls": [{"args": list(args), "kwargs": {}}], "select": select, "expected": expected,
            "obligation_id": "requested_behavior", "contract_quote": quote, "rationale": "documented structure"}


def test_v6_structure_probes_are_parsed_strictly():
    accepted = [_structure({"type": "DataFrame", "columns": ["Team", "Goals"]}, select=0),
                _structure({"type": "DataFrame", "shape": [2, 2], "columns": ["Team", "Goals"], "index": ["A", "B"]}, select=0),
                _structure({"type": "Axes", "title": "Goals per team", "xlabel": "Team", "ylabel": "Goals"}, select=1),
                _structure({"type": "ndarray", "ndim": 2, "shape": [2, 3]}),
                _structure({"type": "Figure"}),
                _structure({"type": "Series", "length": 2, "name": None}),  # null/empty need the review's confirmation
                _structure({"type": "Axes", "title": ""})]
    for probe in accepted:
        kept, why = vf.parse_probes({"probes": [probe]}, STRUCT_TASK)
        assert why == {} and kept[0]["kind"] == "structure", (probe, why)
    for expected, select, reason in (
        ({"type": "DataFrame", "dtypes": {"Team": "object"}}, None, "Unsupported structural property"),
        ({"type": "Axes", "legend": ["Goals"]}, None, "Unsupported structural property"),
        ({"type": "Plot"}, None, "supported type"),
        ({"type": "Figure"}, True, "select is null or an element index"),
        ({"type": "Figure"}, 10, "select is null or an element index"),
        ({"type": "ndarray", "ndim": 3, "shape": [2, 3]}, None, "ndim must equal len(shape)"),
        ({"type": "DataFrame", "shape": [2, True]}, None, "nonnegative integer"),
        ({"type": "Series", "length": -1}, None, "nonnegative integer"),
        ({"type": "DataFrame", "shape": [3, 2], "index": ["A", "B"]}, None, "index must list exactly shape[0] labels"),
        ({"type": "DataFrame", "columns": ["Team", "Points"]}, None, "must state every expected label"),
        ({"type": "Axes", "title": "Goals by team"}, None, "must state every expected label"),
        ({"type": "DataFrame", "columns": [True]}, None, "string (<= 100 characters) or integer labels"),
    ):
        kept, why = vf.parse_probes({"probes": [_structure(expected, select=select)]}, STRUCT_TASK)
        assert kept == [] and reason in why["0"], (expected, why)
    no_select = {k: v for k, v in _structure({"type": "Figure"}).items() if k != "select"}
    assert "Exact probe fields required" in vf.parse_probes({"probes": [no_select]}, STRUCT_TASK)[1]["0"]
    assert "Exact probe fields required" in vf.parse_probes({"probes": [{**_raises(), "select": None}]}, RAISES_TASK)[1]["0"]
    # the selector and the expectation are part of the evidence identity
    probe = _structure({"type": "DataFrame", "columns": ["Team", "Goals"]}, select=0)
    assert vf.harness_nonce([probe]) != vf.harness_nonce([{**probe, "select": 1}])


def test_v6_structure_harness_decides_selection_type_and_properties_in_process():
    pytest.importorskip("pandas")
    pytest.importorskip("numpy")
    frame = ("import pandas as pd\n\ndef task_func(n):\n"
             "    return pd.DataFrame({'Team': ['A', 'B'][:n], 'Goals': [1, 2][:n]}, index=['A', 'B'][:n])")
    full = _structure({"type": "DataFrame", "shape": [2, 2], "columns": ["Team", "Goals"], "index": ["A", "B"]})

    def outcome(code, probe):
        return vf.probe_outcomes(_run_harness(code, [probe]), [probe])[0]

    assert outcome(frame, full) == {"outcome": "pass", "evidence": ""}
    renamed = frame.replace("'Team'", "'team'")
    wrong = outcome(renamed, full)
    assert wrong["outcome"] == "fail" and "DataFrame columns differ: observed" in wrong["evidence"]
    assert '"columns": ["team", "Goals"]' in wrong["evidence"] and '"columns": ["Team", "Goals"]' in wrong["evidence"]
    assert wrong["evidence"].startswith("AssertionError: verifier probe: ")
    none = outcome("def task_func(n):\n    return None", full)
    assert none["outcome"] == "fail" and 'expected a DataFrame; got "NoneType"' in none["evidence"]
    pair = frame.replace("    return pd.DataFrame", "    return pd.DataFrame") + "\n\ndef task_func(n, _f=task_func):\n    return (_f(n), None)"
    assert outcome(pair, {**full, "select": 0})["outcome"] == "pass"
    second = outcome(pair, {**full, "select": 1})
    assert second["outcome"] == "fail" and 'expected element 1 to be a DataFrame; got "NoneType"' in second["evidence"]
    single = outcome(frame, {**full, "select": 0})
    assert single["outcome"] == "fail" and 'expected a tuple/list return with element 0; got "DataFrame"' in single["evidence"]
    multi = ("import pandas as pd\n\ndef task_func(n):\n    return pd.DataFrame([[1, 2]], "
             "columns=pd.MultiIndex.from_tuples([('Team', 'x'), ('Goals', 'y')]))")
    assert outcome(multi, _structure({"type": "DataFrame", "columns": ["Team", "Goals"]}))["outcome"] == "unknown"
    assert outcome(multi, _structure({"type": "DataFrame", "shape": [1, 2]}))["outcome"] == "pass"  # labels not requested
    assert outcome("def task_func(n):\n    raise KeyError('x')", full)["outcome"] == "error"
    array = "import numpy as np\n\ndef task_func(n):\n    return np.zeros((2, 3))"
    assert outcome(array, _structure({"type": "ndarray", "ndim": 2, "shape": [2, 3]}))["outcome"] == "pass"
    assert outcome(array, _structure({"type": "ndarray", "shape": [3, 2]}))["outcome"] == "fail"
    series = "import pandas as pd\n\ndef task_func(n):\n    return pd.Series([1, 2], index=['A', 'B'], name='Goals')"
    assert outcome(series, _structure({"type": "Series", "length": 2, "name": "Goals", "index": ["A", "B"]}))["outcome"] == "pass"
    ints = "import pandas as pd\n\ndef task_func(n):\n    return pd.DataFrame([[1, 2]])"
    assert outcome(ints, _structure({"type": "DataFrame", "columns": [0, 1]}, quote="columns 0 and 1"))["outcome"] == "pass"


def test_v6_structure_axes_projection_in_process():
    pytest.importorskip("matplotlib")
    code = ("import matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt\n\ndef task_func(n):\n"
            "    fig, ax = plt.subplots()\n    ax.set_title('Goals per team')\n    ax.set_xlabel('Team')\n"
            "    ax.set_ylabel('Goals')\n    return ax")
    probe = _structure({"type": "Axes", "title": "Goals per team", "xlabel": "Team", "ylabel": "Goals"})
    assert vf.probe_outcomes(_run_harness(code, [probe]), [probe])[0]["outcome"] == "pass"
    left = code.replace("ax.set_title('Goals per team')", "ax.set_title('Goals per team', loc='left')")
    assert vf.probe_outcomes(_run_harness(left, [probe]), [probe])[0]["outcome"] == "fail"  # center title only


def _calibration_records(structure_controls, structure_false, structure_detections, raises_controls=20, raises_fail_rows=2):
    rows, n = [], 0

    def row(status, probes):
        nonlocal n
        n += 1
        return {"record_hash": f"{n:064x}", "evidence_hash": f"{n:064x}", "host_status": status, "probes": probes}
    raises = {**_raises(), "index": 0}
    structure = {**_structure({"type": "DataFrame", "columns": ["Team", "Goals"]}), "index": 0}
    rows += [row("pass", [{**raises, "outcome": "pass", "evidence": ""}]) for _ in range(raises_controls)]
    rows += [row("pass", [{**structure, "outcome": "fail" if i < structure_false else "pass", "evidence": "x"}])
             for i in range(structure_controls)]
    rows += [row("fail", [{**structure, "outcome": "fail", "evidence": "AssertionError: verifier probe: DataFrame columns differ"}])
             for _ in range(structure_detections)]
    rows += [row("fail", [{**raises, "outcome": "pass", "evidence": ""}]) for _ in range(raises_fail_rows)]
    return rows


def test_v6_structure_needs_its_own_calibration_before_it_counts(tmp_path):
    """Codex round 1 (design): pooled rates hide a new kind behind always-passing raises controls -- 20 clean raises
    controls plus 5 structure controls with 4 false rejections pool to 16% while structure alone is 80%."""
    value, panel = _auth10()
    policy = vf.default_policy_record("bigcodebench")
    for name, args, admitted, authorized in (("pooled", (5, 4, 3), False, False), ("own", (6, 1, 3), True, True)):
        root = tmp_path / name
        root.mkdir()
        runner = vf.Verifier(value, Ledger(root, value, API()), root, 0)
        summary, reports = runner._calibrate(_calibration_records(*args), policy)
        assert summary["structure_admitted"] is admitted and summary["authorized"] is authorized, (name, summary)
        calibration = json.loads((root / "host_only/verifier/0/calibration.json").read_text())
        assert calibration["calibration_rule"] == "train_host_audit_kind_admission_v6"
        assert calibration["structure_admission"]["decided_control_rows"] == args[0]
        assert calibration["by_kind"]["structure"]["detection_rows"] == 3 and calibration["by_kind"]["raises"]["decided_control_rows"] == 20
        failed = [r for r in reports.values() if r["probes"] and r["probes"][0]["kind"] == "structure"
                  and r["probes"][0].get("raw_outcome", r["probes"][0]["outcome"]) == "fail"]
        if admitted:
            assert summary["detections"] == 3 and summary["false_rejections"] == 1 and summary["host_pass_rows"] == 26
            # every host-failed row of an authorized step is reported: 3 structure FAILs and 2 raises PASS lines
            assert sum(r["feedback"] is not None for r in reports.values()) == 5
            assert sum("FAIL call" in (r["feedback"] or "") for r in reports.values()) == 3
        else:
            # unadmitted: raw outcomes kept, nothing counted or shown; only the 2 raises rows are decided host-fail rows
            assert summary["detections"] == 0 and summary["host_pass_rows"] == 20 and summary["host_fail_rows"] == 2
            assert calibration["by_kind"]["structure"]["unadmitted_probes"] == 8
            assert all(r["probes"][0]["outcome"] == "unadmitted" for r in failed) and len(failed) == 3
            assert all(r["feedback"] is None for r in reports.values())


def test_v6_capabilities_are_shared_by_the_coding_prompts_only_and_structure_renders():
    bcb = {"benchmark": "bigcodebench", "rows": []}
    qa = {"benchmark": "searchqa", "rows": []}
    public = {"prompt": STRUCT_TASK, "entry_point": "task_func"}
    policy = vf.DEFAULT_POLICIES["bigcodebench"]
    for system, _ in (vf.plan_messages(bcb, "adaptive_research"), vf.synthesis_messages(bcb, {}, [], policy),
                      vf.probe_messages(public, "def task_func(n): pass", policy, []),
                      vf.review_messages(public, [], policy)):
        assert vf.HARNESS_CAPABILITIES in system
    assert vf.HARNESS_CAPABILITIES not in vf.plan_messages(qa, "adaptive_no_research")[0]
    assert vf.HARNESS_CAPABILITIES not in vf.judge_messages("searchqa", {"question": "q", "context": "c"}, "a",
                                                            vf.DEFAULT_POLICIES["searchqa"])[0]
    probe = {**_structure({"type": "DataFrame", "columns": ["Team", "Goals"]}, select=0), "outcome": "fail",
             "evidence": "AssertionError: verifier probe: DataFrame columns differ: observed ..."}
    text = vf.render_feedback("bigcodebench", vf.default_policy_record("bigcodebench"), [probe])
    assert ('FAIL call args=[2]; the task documents that element 0 of the returned tuple/list is a DataFrame with '
            'columns=["Team", "Goals"]') in text


def test_v6_frozen_train_replay_reruns_only_the_verifier_on_the_sources_sealed_rollout(tmp_path):
    """The registered mechanism screen (Codex design round 2, item E): the current verifier on one completed stage's
    sealed step-0 train rollout -- verified source, complete row set, own manifest/ledger, no solver/analyst calls."""
    import shutil

    from skillopt.continual_learning import verifier_replay as vr

    value, panel = _auth10()
    run_stage(value, panel, tmp_path / "source", fixture_api=API(), fixture_evaluate=host_evaluate("bigcodebench"),
              fixture_probe_executor=executor())
    api = API()
    result = vr.replay_step(tmp_path / "source", 0, tmp_path / "replay", fixture_api=api, fixture_probe_executor=executor())
    assert result["status"] == "completed" and result["eligible_rows"] == 8 and result["source_unknown_rows"] == 0
    assert api.prompts["solver"] == [] and api.prompts["reflection"] == [] and api.prompts["verifier"]
    assert result["criteria"]["ii_audited_structural_detection"] is None and "iii_step_authorized" in result["criteria"]
    replay = json.loads((tmp_path / "replay/replay.json").read_text())
    assert replay["replay_of"]["source_manifest_hash"] == value["record_hash"]
    assert replay["recovery_policy"]["version"] == "verifier-feedback-v7"
    assert replay["replay_of"]["start_policy_hash"] == vf.default_policy_record("bigcodebench")["policy_hash"]
    assert replay["replay_of"]["policy_transition"] == "source_default_to_current_default"
    rows = [sorted(json.loads(p.read_text())["evidence_hash"] for p in (tmp_path / d / "verifier/0/rows").glob("*.json"))
            for d in ("source", "replay")]
    assert rows[0] == rows[1] and len(rows[0]) == 8
    intents = [json.loads(p.read_text()) for p in (tmp_path / "replay/call_intents").glob("*.json")]
    assert intents and all(i["role"] == "verifier" and i["manifest_hash"] == replay["record_hash"] for i in intents)
    # a finished replay returns its sealed result without new calls; an interrupted one is never resumed
    quiet = API()
    assert vr.replay_step(tmp_path / "source", 0, tmp_path / "replay", fixture_api=quiet,
                          fixture_probe_executor=executor()) == result and quiet.prompts["verifier"] == []
    (tmp_path / "interrupted").mkdir()
    (tmp_path / "interrupted/started.json").write_text("{}")
    with pytest.raises(ValueError, match="Interrupted replay retained"):
        vr.replay_step(tmp_path / "source", 0, tmp_path / "interrupted", fixture_api=API(), fixture_probe_executor=executor())
    with pytest.raises(ValueError, match="Only step 0"):
        vr.source_rollout(tmp_path / "source", 1)
    # changed source evidence is refused before anything runs
    shutil.copytree(tmp_path / "source", tmp_path / "tampered")
    evaluation = sorted((tmp_path / "tampered/evaluations").glob("*.json"))[0]
    evaluation.write_text(evaluation.read_text() + "\n")
    with pytest.raises(ValueError, match="Source learning evidence changed"):
        vr.source_rollout(tmp_path / "tampered", 0)


def test_v6_round14_harness_and_parser_regressions():
    """Codex round 14: escaped class names, complete or undecided projections, one-level MultiIndex, whitespace."""
    pytest.importorskip("pandas")
    full = _structure({"type": "DataFrame", "columns": ["Team", "Goals"]})

    def run(code, probe):
        execution = _run_harness(code, [probe])
        return vf.probe_outcomes(execution, [probe])[0], execution

    # a candidate class name with a line break cannot split the harness's own message (type failure stays counted)
    weird = "def task_func(n):\n    return type('Wrong\\nsecond line', (), {})()"
    assert run(weird, full)[0]["outcome"] == "fail"
    renamed = ("import pandas as pd\n\nclass Frame(pd.DataFrame):\n    pass\n\nFrame.__name__ = 'X\\nY'\n\n"
               "def task_func(n):\n    return Frame({'team': [1], 'Goals': [2]})")
    outcome, _ = run(renamed, full)
    assert outcome["outcome"] == "fail" and "columns differ" in outcome["evidence"]
    assert vf.probe_outcomes(_run_harness(weird, [_raises()]), [_raises()])[0]["outcome"] == "fail"  # v4 path too
    # the complete observed projection is retained in the raw execution evidence (no truncated failure)
    long_label = "Goals" + "x" * 900 + "END"
    code = f"import pandas as pd\n\ndef task_func(n):\n    return pd.DataFrame({{'Team': [1], {long_label!r}: [2]}})"
    outcome, execution = run(code, full)
    assert outcome["outcome"] == "fail" and long_label in execution["metrics"]["details"]["test_probe_0"]
    huge = "import pandas as pd\n\ndef task_func(n):\n    return pd.DataFrame({('c%d' % i): [1] for i in range(2000)})"
    assert run(huge, full)[0]["outcome"] == "unknown"  # too large to retain -> undecided, never a truncated fail
    one_level = ("import pandas as pd\n\ndef task_func(n):\n    return pd.DataFrame([[1, 2]], "
                 "columns=pd.MultiIndex.from_tuples([('Team',), ('Goals',)]))")
    assert run(one_level, full)[0]["outcome"] == "unknown"
    # whitespace-only expected strings are not empty: they need (and cannot get) a quote match
    for expected in ({"type": "Axes", "title": " \t "}, {"type": "DataFrame", "columns": [" "]}):
        kept, why = vf.parse_probes({"probes": [_structure(expected)]}, STRUCT_TASK)
        assert kept == [] and "must state every expected label" in why["0"]


def test_v6_round14_replay_guards(tmp_path, monkeypatch):
    """Codex round 14: usage gaps never complete, reuse is bound and inventoried, natural sources take no fixture
    hooks, the output never overlaps the source, and the CLI requires completion markers."""
    import shutil

    from scripts import replay_fivebench_verifier as cli
    from skillopt.continual_learning import verifier_replay as vr

    value, panel = _auth10()
    run_stage(value, panel, tmp_path / "source", fixture_api=API(), fixture_evaluate=host_evaluate("bigcodebench"),
              fixture_probe_executor=executor())

    class NoUsageAPI(API):
        def call(self, system, user, kind, key, *, max_tokens, repeat):
            row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
            if kind.endswith("verifier") and "reviews" not in user and '"probes"' in user and "anonymous_implementation" not in user:
                return {**row, "usage": {}, "attempts": [{}]}  # a delivered review whose usage is unknown
            return row

    gap = vr.replay_step(tmp_path / "source", 0, tmp_path / "gap", fixture_api=NoUsageAPI(), fixture_probe_executor=executor())
    # never completed: the ledger's pre-call check or the final guard (a gap on the very last call) stops it
    assert gap["status"] == "pending" and "authorized" not in gap
    assert gap["reason"] in {"incomplete_usage", "previous_call_usage_or_receipt_unknown"}

    done = vr.replay_step(tmp_path / "source", 0, tmp_path / "replay", fixture_api=API(), fixture_probe_executor=executor())
    assert done["status"] == "completed" and done["artifacts"]
    # a changed replay record is refused on reuse
    shutil.copytree(tmp_path / "replay", tmp_path / "replay2")
    row = sorted((tmp_path / "replay2/verifier/0/rows").glob("*.json"))[0]
    row.write_text(row.read_text() + "\n")
    with pytest.raises(ValueError, match="Finished replay evidence changed"):
        vr.replay_step(tmp_path / "source", 0, tmp_path / "replay2", fixture_api=API(), fixture_probe_executor=executor())
    # a finished replay of another source is not returned for this one
    value2, panel2 = _auth10(train=6)
    run_stage(value2, panel2, tmp_path / "other", fixture_api=API(), fixture_evaluate=host_evaluate("bigcodebench"),
              fixture_probe_executor=executor())
    with pytest.raises(ValueError, match="belongs to another source"):
        vr.replay_step(tmp_path / "other", 0, tmp_path / "replay", fixture_api=API(), fixture_probe_executor=executor())
    # the output never overlaps the archived source (refused before any write)
    with pytest.raises(ValueError, match="must not overlap"):
        vr.replay_step(tmp_path / "source", 0, tmp_path / "source/verifier/replay", fixture_api=API(),
                       fixture_probe_executor=executor())
    assert not (tmp_path / "source/verifier/replay").exists()
    # a natural source accepts no fixture hook, the fetcher included
    real = vr.source_rollout

    def natural(source, step):
        identity, result, manifest, pairs, accounting = real(source, step)
        return identity, result, {**manifest, "model": {**manifest["model"], "provider": "bigmodel"}}, pairs, accounting

    monkeypatch.setattr(vr, "source_rollout", natural)
    with pytest.raises(ValueError, match="Fixture hooks belong to a fixture source only"):
        vr.replay_step(tmp_path / "source", 0, tmp_path / "natural", fixture_fetcher=lambda urls, root: [])
    assert not (tmp_path / "natural").exists()
    # the CLI refuses to run without completion markers
    with pytest.raises(SystemExit):
        cli.main(["--source", str(tmp_path / "source"), "--output", str(tmp_path / "cli")])


def test_v6_round15_unrepresentable_class_names_and_stop_markers(tmp_path):
    """Codex round 15: the serialization path escapes candidate class names too (an unrepresentable result stays
    unknown, never a misleading raised call), and the replay CLI needs absent STOP markers before and after the lock."""
    from scripts import replay_fivebench_verifier as cli

    expected = {"kind": "expected", "calls": [{"args": [4], "kwargs": {}}], "expected": {"root": 2.0},
                "obligation_id": "requested_behavior", "contract_quote": "Return the square root of n.", "rationale": "r"}
    relation = {**expected, "kind": "equal_relation", "expected": None, "calls": [{"args": [4], "kwargs": {}}] * 2}
    weird = "def task_func(n):\n    return {'root': type('Wrong\\nsecond line', (), {})()}"
    outcomes = vf.probe_outcomes(_run_harness(weird, [expected, relation]), [expected, relation])
    assert [o["outcome"] for o in outcomes] == ["unknown", "unknown"]
    log = tmp_path / "main.log"
    log.write_text("chain complete\nMAIN-EXIT=0\n")
    cli._markers([f"{log}::MAIN-EXIT=0"], [f"{log}::STOP"])
    log.write_text("chain complete\nMAIN-EXIT=0\n2026 STOP: review\n")
    with pytest.raises(ValueError, match="Forbidden marker present"):
        cli._markers([f"{log}::MAIN-EXIT=0"], [f"{log}::STOP"])
    with pytest.raises(SystemExit):  # --forbid is mandatory
        cli.main(["--source", str(tmp_path / "s"), "--output", str(tmp_path / "o"), "--require", f"{log}::MAIN-EXIT=0"])


# ----------------------------------------------------------------------------- v7: verifier call delivery
def _closed(row, finish, error, response="", tokens=None):
    """A delivered but unusable reply exactly as the frozen client reports it (ok=false, HTTP 200, complete stream)."""
    usage = {"prompt_tokens": 20, "completion_tokens": row["request"]["max_tokens"] if tokens is None else tokens}
    return {**row, "ok": False, "finish_reason": finish, "error_type": error, "status": 200, "stream_complete": True,
            "returned_model": "glm-5.3", "response": response, "usage": usage, "attempts": [{"usage": usage}]}


def length(row, cap, system):  # chain e KOR (10/8): ran out of the verifier cap; reasoning only, empty content
    return _closed(row, "length", "truncated_content", tokens=min(cap, 100))  # (fixture usage under the token stop)


class DeliveryAPI(API):
    """Real-client-shaped delivery results for the verifier payloads named by a marker: ``rules[marker](row, cap,
    system)`` returns the receipt (the fixture's ordinary reply is ``row``)."""

    def __init__(self, rules, **kwargs):
        super().__init__(**kwargs)
        self.rules = rules

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if kind.endswith("verifier"):
            payload = json.loads(user)
            for marker, rule in self.rules.items():
                if marker in payload and (not callable(getattr(rule, "applies", None)) or rule.applies(payload)):
                    return rule(row, max_tokens, system)
        return row


def _intents(stage_root):
    return {json.loads(p.read_text())["logical_id"]: json.loads(p.read_text())
            for p in (stage_root / "call_intents").glob("*.json") if json.loads(p.read_text())["role"] == "verifier"}


def _text_stage(tmp_path, name, api, **kwargs):
    value, panel = _auth10(benchmark="searchqa", **kwargs)
    return run_stage(value, panel, tmp_path / name, fixture_api=api, fixture_evaluate=host_evaluate("searchqa"),
                     fixture_probe_executor=lambda *a: pytest.fail("no container for text domains"))


def test_v7_a_closed_length_verifier_reply_gets_one_recovery_then_is_a_unit_result(tmp_path):
    """KOR chain e (10/8): two judge replies ran out of the 4096-token verifier cap (ok=false, truncated_content,
    one with empty content) and stopped the whole stage. Now the solver's rule applies: one recovery of the same
    request at the frozen recovery cap, bound by the ledger to the closed receipt; if that too runs out, the row
    gets no verdict (its own result) and the stage goes on."""
    # recovered: every judge request at the base cap runs out, its recovery decides as before
    api = DeliveryAPI({"anonymous_response": lambda row, cap, system: length(row, cap, system) if cap == 100 else row})
    result = _text_stage(tmp_path, "stage", api)
    step = result["verifier_steps"][0]
    assert result["status"] == "completed" and step["authorized"] and step["detections"] == 3
    assert step["delivery"]["length_recoveries"] == 8 and step["delivery"]["terminal"] == {}
    assert step["delivery"]["requests"] == step["delivery"]["calls"] + 8
    intents = _intents(tmp_path / "stage")
    judges = sorted(k for k in intents if ":judge:" in k and not k.endswith(":length-recovery:1"))
    assert len(judges) == 8
    for logical in judges:
        recovery = intents[logical + ":length-recovery:1"]
        assert recovery["max_tokens"] == POLICY_V10["length_max_tokens"] == 131072
        assert recovery["recovery_of"] == intents[logical]["record_hash"] and intents[logical]["max_tokens"] == 100
    rows = [json.loads(p.read_text()) for p in (tmp_path / "stage/verifier/0/rows").glob("*.json")]
    assert all(r["trace"][0]["status"] == "parsed" and "length_recovery_of" in r["trace"][0] for r in rows)

    # exhausted on the three host-failed rows: no verdict there (coverage loss, by host status), no third request,
    # no format retry of the partial reply -- and the stage completes, unauthorized for lack of detections
    exhausted = lambda row, cap, system: length(row, cap, system)  # noqa: E731
    exhausted.applies = lambda payload: payload["anonymous_response"] == "zero"
    result2 = _text_stage(tmp_path, "stage2", DeliveryAPI({"anonymous_response": exhausted}))
    step2 = result2["verifier_steps"][0]
    assert result2["status"] == "completed" and not step2["authorized"] and step2["detections"] == 0
    assert step2["delivery"]["terminal"] == {"length_after_recovery": 3} and step2["delivery"]["length_recoveries"] == 3
    assert step2["coverage"]["rows_with_terminal_delivery"] == {"host_pass": 0, "host_fail": 3}
    assert step2["coverage"]["rows_without_probes"] == {"host_pass": 0, "host_fail": 3}
    assert step2["coverage"]["eligible_rows"] == {"host_pass": 5, "host_fail": 3}
    assert step2["coverage"]["decided_rows"] == {"host_pass": 5, "host_fail": 0}
    logicals = _verifier_logicals(tmp_path / "stage2")
    assert sum(x.endswith(":length-recovery:1") for x in logicals) == 3 and not any("json-retry" in x for x in logicals)
    calibration = json.loads((tmp_path / "stage2/host_only/verifier/0/calibration.json").read_text())
    assert calibration["coverage"] == step2["coverage"] and calibration["delivery"] == step2["delivery"]

    # a partial (nonempty) truncated reply is never parsed either: the recovery is the reply that counts
    partial = lambda row, cap, system: (_closed(row, "length", "truncated_content", response='{"checks": [')  # noqa: E731
                                        if cap == 100 else row)
    result3 = _text_stage(tmp_path, "stage3", DeliveryAPI({"anonymous_response": partial}))
    assert result3["verifier_steps"][0]["detections"] == 3
    assert not any("json-retry" in x for x in _verifier_logicals(tmp_path / "stage3"))

    # recoveries spend real tokens: the reported-usage stop threshold (checked before each submission, not a
    # reservation, so concurrent requests overshoot it) still ends the stage once exceeded -- in the verifier or,
    # when every verifier request was already in flight, at the analyst's next submission
    heavy = lambda row, cap, system: _closed(row, "length", "truncated_content")  # noqa: E731  (usage = full cap)
    heavy.applies = exhausted.applies
    result4 = _text_stage(tmp_path, "stage4", DeliveryAPI({"anonymous_response": heavy}))
    assert result4["status"] == "pending" and result4["reason"] in {"reported_token_stop_threshold",
                                                                     "native_reflection_incomplete"}
    assert result4["costs"]["reported_tokens_known_subtotal"] >= 100000


def test_v7_empty_and_filtered_replies_are_unit_results_never_retried_or_repaired(tmp_path):
    # a filtered synthesis is not repaired: the policy stays the parent's and the step goes on
    filtered = lambda row, cap, system: _closed(row, "sensitive", "provider_content_filter", tokens=0)  # noqa: E731
    value, panel = _auth10()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=DeliveryAPI({"reflection": filtered}),
                       fixture_evaluate=host_evaluate("bigcodebench"), fixture_probe_executor=executor())
    policy = json.loads((tmp_path / "stage/verifier/0/policy.json").read_text())
    assert result["status"] == "completed" and policy["status"] == "invalid"
    assert policy["failure_detail"] == "Synthesis reply unavailable: filtered"
    assert policy["policy"] == vf.default_policy_record("bigcodebench")["policy"]
    assert [x for x in _verifier_logicals(tmp_path / "stage") if ":policy:" in x] == [
        "verifier:0:policy:plan", "verifier:0:policy:synthesis"]
    assert result["verifier_steps"][0]["delivery"]["terminal"] == {"provider_content_filter": 1}
    # an empty delivered judge reply (closed stop/empty_content), and an ok reply of whitespace only: no verdict,
    # no format retry, no recovery
    empty = lambda row, cap, system: _closed(row, "stop", "empty_content", tokens=0)  # noqa: E731
    blank = lambda row, cap, system: {**row, "response": "  \n"}  # noqa: E731
    for name, rule in (("empty", empty), ("blank", blank)):
        step = _text_stage(tmp_path, name, DeliveryAPI({"anonymous_response": rule}))["verifier_steps"][0]
        assert step["delivery"]["terminal"] == {"empty_content": 8} and step["detections"] == 0
        assert step["coverage"]["rows_with_terminal_delivery"] == {"host_pass": 5, "host_fail": 3}
        logicals = _verifier_logicals(tmp_path / name)
        assert not any("json-retry" in x or "length-recovery" in x for x in logicals)
    filtered_judge = _text_stage(tmp_path, "filtered", DeliveryAPI({"anonymous_response": filtered}))
    assert filtered_judge["status"] == "completed"
    assert filtered_judge["verifier_steps"][0]["delivery"]["terminal"] == {"provider_content_filter": 8}


def test_v7_receipts_that_are_not_a_closed_delivery_still_stop_the_stage(tmp_path):
    shapes = {
        "broken_stream_length": lambda row, cap, s: {**length(row, cap, s), "stream_complete": False},
        "other_model_length": lambda row, cap, s: {**length(row, cap, s), "returned_model": "glm-4"},
        "filter_in_broken_stream": lambda row, cap, s: {**_closed(row, "sensitive", "provider_content_filter", tokens=0),
                                                        "stream_complete": False},
        "http_error": lambda row, cap, s: {**row, "ok": False, "status": 500, "error_type": "http_status",
                                           "finish_reason": None, "response": None},
        "unclassified": lambda row, cap, s: _closed(row, "tool_calls", "unexpected_finish_reason"),
    }
    for name, rule in shapes.items():
        result = _text_stage(tmp_path, name, DeliveryAPI({"anonymous_response": rule}))
        assert result["status"] == "pending" and result["reason"] == "verifier_call_failed", name
        assert not any("length-recovery" in x for x in _verifier_logicals(tmp_path / name)), name


def test_v7_one_call_makes_at_most_four_requests(tmp_path):
    """Length recovery, then an unparseable recovered reply, then the format retry runs out too, and ITS
    recovery decides: four ledger requests for one plan call; the linkage of every step is kept."""
    def plan(row, cap, system):
        retry = "FORMAT RETRY" in system
        if cap == 100:
            return length(row, cap, system)
        return row if retry else {**row, "response": MALFORMED_PLAN}

    value, panel = _auth10()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=DeliveryAPI({"experiment_arm": plan}),
                       fixture_evaluate=host_evaluate("bigcodebench"), fixture_probe_executor=executor())
    record = json.loads((tmp_path / "stage/verifier/0/policy.json").read_text())
    assert record["status"] == "update"
    first = record["trace"][0]
    assert first["status"] == "parsed" and "length_recovery_of" in first
    assert "length_recovery_of" in first["json_retry_of"] and first["json_retry_of"]["error"] == "NativeJSONError"
    assert [x for x in _verifier_logicals(tmp_path / "stage") if ":policy:plan" in x] == [
        "verifier:0:policy:plan", "verifier:0:policy:plan:json-retry:1", "verifier:0:policy:plan:json-retry:1:length-recovery:1",
        "verifier:0:policy:plan:length-recovery:1"]
    delivery = result["verifier_steps"][0]["delivery"]
    assert delivery["format_retries"] == 1 and delivery["length_recoveries"] == 2
    assert delivery["requests"] == delivery["calls"] + 3 and delivery["http_attempts"] == delivery["requests"]


def test_v7_ledger_binds_verifier_recovery_to_the_v7_rule_and_the_budget(tmp_path):
    value, _ = _auth10()
    question = json.dumps({"anonymous_response": "x", "task": {"question": "q"}})
    api = DeliveryAPI({"anonymous_response": lambda row, cap, s: length(row, cap, s) if cap == 100 else row})
    ledger = Ledger(tmp_path / "ledger", value, api)

    def original(logical, policy=value):
        return digest({"manifest_hash": policy["record_hash"], "role": "verifier", "logical_id": logical,
                       "system": "s", "user": question, "max_tokens": 100})

    assert not ledger.call("verifier", "verifier:0:judge:a", "s", question, 100)["ok"]
    with pytest.raises(ValueError, match="frozen cap"):
        ledger.call("verifier", "verifier:0:judge:a:length-recovery:1", "s", question, 4096,
                    recovery_of=original("verifier:0:judge:a"))
    recovered = ledger.call("verifier", "verifier:0:judge:a:length-recovery:1", "s", question, 131072,
                            recovery_of=original("verifier:0:judge:a"))
    assert recovered["ok"]
    with pytest.raises(ValueError, match="Invalid or repeated length recovery"):  # never a recovery of a recovery
        ledger.call("verifier", "verifier:0:judge:a:length-recovery:1:length-recovery:1", "s", question, 131072,
                    recovery_of=digest({"manifest_hash": value["record_hash"], "role": "verifier",
                                        "logical_id": "verifier:0:judge:a:length-recovery:1", "system": "s",
                                        "user": question, "max_tokens": 131072, "recovery_of": original("verifier:0:judge:a")}))
    ok_api = API()
    ok_ledger = Ledger(tmp_path / "ok", value, ok_api)
    assert ok_ledger.call("verifier", "verifier:0:judge:b", "s", question, 100)["ok"]
    with pytest.raises(ValueError, match="Invalid or repeated length recovery"):  # only a closed length receipt
        ok_ledger.call("verifier", "verifier:0:judge:b:length-recovery:1", "s", question, 131072,
                       recovery_of=original("verifier:0:judge:b"))
    # earlier v10 policies (no v7 delivery rule) keep refusing verifier recovery, and so does the verifier
    legacy = {**value, "recovery_policy": {k: v for k, v in value["recovery_policy"].items() if k != "verifier_delivery"}}
    old = Ledger(tmp_path / "legacy", legacy, api)
    old.call("verifier", "verifier:0:judge:c", "s", question, 100)
    with pytest.raises(ValueError, match="v7 delivery rule"):
        old.call("verifier", "verifier:0:judge:c:length-recovery:1", "s", question, 131072,
                 recovery_of=original("verifier:0:judge:c", legacy))
    verifier = vf.Verifier(legacy, old, tmp_path / "legacy-stage", 0)
    assert verifier.delivery is None
    with pytest.raises(vf.LearningPending, match="verifier_call_failed"):
        verifier.call("judge", "d", "s", question)
    # a recovery is a verifier request of its own: it counts against max_verifier_calls
    base, args = _args10()
    args["budget"]["max_verifier_calls"] = 1
    tiny = manifest(base, **args)
    small = Ledger(tmp_path / "tiny", tiny, api)
    small.call("verifier", "verifier:0:judge:e", "s", question, 100)
    with pytest.raises(BudgetExhausted, match="max_verifier_calls"):
        small.call("verifier", "verifier:0:judge:e:length-recovery:1", "s", question, 131072,
                   recovery_of=original("verifier:0:judge:e", tiny))


def test_v7_parent_mapping_carries_inactive_predecessor_records_verbatim(tmp_path):
    """The main method's S3 rerun chains from chain e's SearchQA stage, which hands on v3 rubrics for BigCodeBench
    and SearchQA. Only the stage's OWN domain record must be this verifier's; the inactive ones are carried as is."""
    def old(benchmark, version="rubric-probe-research-verifier-v3"):
        return {**vf.default_policy_record(benchmark), "verifier_version": version}

    assert vf.validate_policy_mapping({"bigcodebench": old("bigcodebench"), "searchqa": old("searchqa")}, "korbench")
    for mapping, benchmark in (({"searchqa": old("searchqa")}, "searchqa"),  # the active domain must be current
                               ({"searchqa": old("searchqa")}, None),  # strict without a benchmark
                               ({"bigcodebench": old("bigcodebench", "rubric-probe-research-verifier-v2")}, "searchqa"),
                               ({"bigcodebench": {**old("bigcodebench"), "policy_hash": "0" * 64}}, "searchqa"),
                               ({"sheet": {**old("bigcodebench"), "benchmark": "sheet"}}, "searchqa"),
                               ({"searchqa": old("bigcodebench")}, "korbench")):
        with pytest.raises(ValueError):
            vf.validate_policy_mapping(mapping, benchmark)
    with pytest.raises(ValueError):
        _auth10(benchmark="searchqa", parent_policy={"searchqa": old("searchqa")})
    carried = {"bigcodebench": old("bigcodebench")}
    result = _text_stage(tmp_path, "stage", API(), parent_policy=deepcopy(carried))
    assert result["status"] == "completed"
    assert result["verifier_policy"]["bigcodebench"] == carried["bigcodebench"]  # verbatim, original version
    assert result["verifier_policy"]["searchqa"]["verifier_version"] == vf.VERSION
    policy = json.loads((tmp_path / "stage/verifier/0/policy.json").read_text())
    assert policy["parent_policy_hash"] == vf.default_policy_record("searchqa")["policy_hash"]


def test_v7_round17_a_terminal_research_reply_withholds_the_rows_verdict(tmp_path):
    """Codex round 17: the bounded research is part of the row; when its plan or resolution reply is unavailable
    (filtered here), the reviewed probes must not run on the reviewer's keep alone -- the row has no verdict."""
    filtered = lambda row, cap, system: _closed(row, "sensitive", "provider_content_filter", tokens=0)  # noqa: E731
    doc = "https://docs.python.org/3.11/library/functions.html"
    with_urls = lambda row, cap, system: {**row, "response": json.dumps({"urls": [doc]})}  # noqa: E731

    def fetcher(urls, root):
        return [{"source_id": "s1", "url": u, "status": "available", "text": "int(x) returns an integer."} for u in urls]

    for name, rules in (("plan", {"fact_questions": filtered}),
                        ("resolution", {"fact_questions": with_urls, "reviews": filtered})):
        run = executor()
        value, panel = _auth10()
        result = run_stage(value, panel, tmp_path / name,
                           fixture_api=DeliveryAPI(rules, fact_question="Does int('3') return 3?"),
                           fixture_evaluate=host_evaluate("bigcodebench"), fixture_probe_executor=run,
                           fixture_fetcher=fetcher)
        step = result["verifier_steps"][0]
        assert result["status"] == "completed" and run.calls == [], name
        assert step["probes_executed"] == 0 and not step["authorized"] and step["detections"] == 0, name
        assert step["coverage"]["rows_with_terminal_delivery"] == {"host_pass": 5, "host_fail": 3}, name
        assert step["delivery"]["terminal"] == {"provider_content_filter": 8}, name
        rows = [json.loads(p.read_text()) for p in (tmp_path / name / "verifier/0/rows").glob("*.json")]
        assert all(r["probes"] == [] and r["trace"][-1]["status"] == "no_verdict_after_terminal_delivery"
                   and r["trace"][-1]["withheld"] == [0] for r in rows), name


def test_v7_round17_a_retry_refused_before_submission_keeps_its_first_request_counted():
    first = {"request_hash": "h" * 64, "error": "NativeJSONError", "reason": "r", "http_attempts": 2}
    policy = {"trace": [{"stage": "policy", "status": "prompt_too_large", "prompt_bytes": 200001, "json_retry_of": first},
                        {"stage": "plan", "information_origin": "model_proposal"}]}
    delivery = vf._delivery_accounting(policy, [])
    assert delivery == {"calls": 1, "format_retries": 1, "length_recoveries": 0, "requests": 1, "http_attempts": 2,
                        "terminal": {}}


def test_v7_round17_test_cell_verification_binds_every_artifact_and_writes_nothing(tmp_path):
    """Codex round 17: the S3 queue may declare success only for VERIFIED cells (its own, or the inherited S2
    cells): sealed request = the tool's request for the deployed Skill, result and checkpoint bound to it, summary =
    its recomputation (in a scratch directory). A file that merely exists is not enough."""
    import hashlib
    import types
    from pathlib import Path

    from scripts import verify_fivebench_g_cells as cells
    from skillopt.coevolution_v5.core import seal
    from skillopt.continual_eval.core import write_json

    out = tmp_path / "stage"
    out.mkdir()
    tool = tmp_path / "tool.py"
    tool.write_text("# tool\n")
    tool_sha = hashlib.sha256(tool.read_bytes()).hexdigest()
    skill = "Answer with the entity only."
    learned = {"skill": skill, "skill_sha256": hashlib.sha256(skill.encode()).hexdigest(), "action": "selected_update"}
    record = {"benchmark": "searchqa", "record_hash": "r" * 64}

    def request_for(text, benchmark):
        return seal({"operation": "test", "benchmark": benchmark, "skill": text, "method": "rubric_research",
                     "provenance": "fivebench_g_stage:" + record["record_hash"], "run": str(tmp_path / ("run-" + benchmark)),
                     "tool_sha256": tool_sha})

    def compare(where, record_, learned_, request, result):
        summary = seal({"benchmark": request["benchmark"], "skill_sha256": learned_["skill_sha256"],
                        "test_counts": result["counts"], "wins_vs_no_skill": result["wins"], "losses_vs_no_skill": 0,
                        "operated_by_tool_sha256": tool_sha})
        write_json(where / ("summary-" + request["benchmark"] + ".json"), summary)
        return summary

    stage = types.SimpleNamespace(__file__=str(tool), COMPATIBLE_TOOL_HASHES=frozenset(), compare=compare,
                                  _sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest(),
                                  _suffix=lambda r, b: "" if b == r["benchmark"] else "-" + b,
                                  _method=lambda r: "rubric_research",
                                  _test_request=lambda r, protocol, test_eval, o, text, b: request_for(text, b))
    for benchmark in ("searchqa", "korbench"):
        suffix = stage._suffix(record, benchmark)
        request = request_for(skill, benchmark)
        write_json(out / f"test-request{suffix}.json", request)
        checkpoint = seal({"skill_text": skill, "provenance": request["provenance"], "plan_hash": "p" * 64})
        write_json(Path(request["run"]) / "checkpoints/rubric_research/h0/s1.json", checkpoint)
        result = seal({"request_hash": request["record_hash"], "root": request["run"], "skill_sha256": learned["skill_sha256"],
                       "plan_hash": "p" * 64, "checkpoint_hash": checkpoint["record_hash"], "counts": {"pass": 3}, "wins": 2})
        write_json(out / f"test-result{suffix}.json", result)
        write_json(out / f"summary{suffix}.json", compare(tmp_path, record, learned, request, result))
    before = sorted(p.name for p in out.iterdir())
    cell = cells.verify_cell(stage, out, record, {}, learned, tmp_path, "korbench")
    assert cell["wins_vs_no_skill"] == 2 and sorted(p.name for p in out.iterdir()) == before  # nothing written
    # a re-sealed summary that disagrees with its evidence
    summary = json.loads((out / "summary-korbench.json").read_text())
    (out / "summary-korbench.json").unlink()  # (sealed artifacts are immutable; a tamperer replaces the file)
    write_json(out / "summary-korbench.json", seal({**{k: v for k, v in summary.items() if k != "record_hash"},
                                                    "wins_vs_no_skill": 9}))
    with pytest.raises(ValueError, match="Recorded summary differs"):
        cells.verify_cell(stage, out, record, {}, learned, tmp_path, "korbench")
    # another deployed Skill: the recorded request (and result) belong to a different Skill
    other = {**learned, "skill": "Other.", "skill_sha256": hashlib.sha256(b"Other.").hexdigest()}
    with pytest.raises(ValueError, match="not this stage's request"):
        cells.verify_cell(stage, out, record, {}, other, tmp_path, "searchqa")
    # a result bound to another request
    result = json.loads((out / "test-result.json").read_text())
    (out / "test-result.json").unlink()
    write_json(out / "test-result.json", seal({**{k: v for k, v in result.items() if k != "record_hash"},
                                               "request_hash": "x" * 64}))
    with pytest.raises(ValueError, match="does not belong to this request"):
        cells.verify_cell(stage, out, record, {}, learned, tmp_path, "searchqa")
    # an incomplete cell (no result) fails; nothing is submitted
    (out / "test-result.json").unlink()
    with pytest.raises((ValueError, FileNotFoundError, OSError)):
        cells.verify_cell(stage, out, record, {}, learned, tmp_path, "searchqa")
