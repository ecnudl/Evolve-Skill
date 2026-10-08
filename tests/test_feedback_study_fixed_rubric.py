"""L1 fixed-rubric study controls (engineering fixtures; no method-effect claim): frozen rubrics are never
re-proposed, every rubric x output cell is judged exactly once on the same fresh rollout in the registered order,
the judge never sees a label, terminal deliveries are abstentions, failures are pending and never resumed, and
the registered analysis is computed exactly."""
import itertools
import json
import random
import threading
from copy import deepcopy

import pytest

from skillopt.continual_learning import verifier as vf
from skillopt.continual_learning.contracts import VERIFIER_METHOD
from skillopt.continual_learning.ledger import Ledger
from skillopt.continual_learning.recovery import POLICY_V10
from skillopt.feedback_study import fixed_rubric as fr
from skillopt.feedback_study.common import FixedRubricVerifier, study_sources
from skillopt.validator_pilot.api import digest
from tests.test_continual_learning_domains import PRIVATE_CANARY, setup
from tests.test_continual_learning_generalization_v8 import LABEL
from tests.test_continual_learning_verifier_v10 import API, _closed

TRAIN_FAMILIES, PER_FAMILY = 4, 3
PASS_IDS = {"0", "3", "4", "6", "9", "10"}  # host-passed train rows (the others fail)


def _panel():
    _, base, _ = setup("korbench")
    task = base["tasks"][0]
    tasks = []
    for index in range(TRAIN_FAMILIES * PER_FAMILY + 4):
        row = deepcopy(task)
        family = index // PER_FAMILY if index < TRAIN_FAMILIES * PER_FAMILY else 100 + index
        row.update(task_id=str(index), family_id=f"f{family}",
                   partition="development" if index < TRAIN_FAMILIES * PER_FAMILY else "skill_confirmation")
        row["public"]["question"] = f"What is the reply? #{index}"
        row["private"]["answer"] = LABEL
        tasks.append(row)
    return {**base, "tasks": tasks}


def _policy(name):
    return {**vf.DEFAULT_POLICIES["korbench"], "mechanism": f"ARM:{name} Apply the stated rule exactly."}


def _rubrics(chain_break=False):
    default = vf.default_policy_record("korbench")
    rubrics, parent = {"default": default}, default["policy_hash"]
    for arm in ("h0", "h1", "h2"):
        policy = _policy(arm)
        rubrics[arm] = {"verifier_version": vf.VERSION, "benchmark": "korbench", "policy": policy,
                        "policy_hash": digest(policy), "status": "update", "citations": [], "sources": [],
                        "parent_policy_hash": "0" * 64 if chain_break and arm == "h1" else parent}
        parent = rubrics[arm]["policy_hash"]
    return rubrics


def _spec(panel, **kwargs):
    model = {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low",
             "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 3600,
                           "initial_health_policy": "completed_response_v1"}}
    train = sorted({t["family_id"] for t in panel["tasks"] if t["partition"] == "development"})
    selection = sorted({t["family_id"] for t in panel["tasks"] if t["partition"] != "development"})
    template = {"panel_hash": digest(panel), "train_families": train, "selection_families": selection, "model": model,
                "runtime": {}, "parent_skill": "", "seed": 0, "recovery_policy": deepcopy(POLICY_V10)}
    return fr.build_spec(template, _rubrics(**kwargs), {"fixture": True})


def host(task, skill):
    ok = task["task_id"] in PASS_IDS
    assert task["partition"] == "development", "the study never evaluates selection tasks"
    return ({"status": "available", "output": f"one #{task['task_id']}" if ok else f"zero #{task['task_id']}",
             "reason": "fixture"},
            {"status": "pass" if ok else "fail", "score": float(ok), "reason": "fixture", "metrics": {}})


class RubricAPI(API):
    """Judge verdicts depend on the rubric (arm) and the row: default abstains on wrong answers, h0 detects
    families f0/f1 only, h1 detects every wrong answer, h2 detects every wrong answer and falsely rejects row 9."""

    def __init__(self, rules=None):
        super().__init__()
        self.judged, self.keys, self.rules = [], [], rules or {}

    def _verifier(self, payload):
        assert "experiment_arm" not in payload and "reflection" not in payload, "no policy proposal"
        assert "fact_questions" not in payload and "probes" not in payload, "no Research or probes"
        mechanism = payload["rubric"]["mechanism"]
        arm = mechanism.split()[0][4:] if mechanism.startswith("ARM:") else "default"
        response = payload["anonymous_response"]
        index = int(payload["task"]["question"].rsplit("#", 1)[1])
        with self.lock:
            self.judged.append((arm, index))
        wrong = response.startswith("zero")
        verdict = {"default": "unknown" if wrong else "pass",
                   "h0": "fail" if wrong and index < 2 * PER_FAMILY else "pass",
                   "h1": "fail" if wrong else "pass",
                   "h2": "fail" if wrong or index == 9 else "pass"}[arm]
        return {"checks": [{"obligation": "answer form", "contract_quote": payload["task"]["question"],
                            "verdict": verdict, "evidence": response[:50]}]}

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if kind.endswith("verifier"):
            with self.lock:
                self.keys.append(key)
            payload = json.loads(user)
            for marker, rule in self.rules.items():
                if marker(payload):
                    return rule(row, max_tokens)
        return row


def _verifier_intents(root):
    return [json.loads(p.read_text()) for p in (root / "call_intents").glob("*.json")
            if json.loads(p.read_text())["role"] == "verifier"]


def test_fixed_rubric_study_judges_every_cell_once_on_one_fresh_rollout(tmp_path):
    panel = _panel()
    spec = _spec(panel)
    api = RubricAPI()
    result = fr.run_study(spec, panel, tmp_path / "study", fixture_api=api, fixture_evaluate=host)
    root = tmp_path / "study"
    assert result["status"] == "completed" and result["eligible_rows"] == TRAIN_FAMILIES * PER_FAMILY
    assert result["eligible_host_fail_rows"] == 6 and result["eligible_host_pass_rows"] == 6
    # one judgment per rubric x output cell, own logical ids per arm, no proposal / research / analyst call
    intents = _verifier_intents(root)
    schedule = json.loads((root / "schedule.json").read_text())
    tokens = schedule["eligible_tokens"]
    assert sorted(i["logical_id"] for i in intents) == sorted(
        f"verifier:0-{arm}:judge:{t[:16]}" for arm in fr.ARMS for t in tokens)
    assert not any(json.loads(p.read_text())["role"] == "reflection" for p in (root / "call_intents").glob("*.json"))
    assert sorted(api.judged) == sorted((arm, i) for arm in fr.ARMS for i in range(TRAIN_FAMILIES * PER_FAMILY))
    # the registered schedule: all cells, seeded order, and its first cell ran alone first (health barrier)
    assert schedule == fr.make_schedule(spec, tokens)
    first = json.loads((root / "call_intents" / (api.keys[0] + ".json")).read_text())
    arm, token = schedule["cells"][0]
    assert first["logical_id"] == f"verifier:0-{arm}:judge:{token[:16]}"
    # every arm's rows are bound to its frozen rubric; the source rubric records were never changed
    for arm in fr.ARMS:
        rows = [json.loads(p.read_text()) for p in (root / "verifier" / f"0-{arm}" / "rows").glob("*.json")]
        assert len(rows) == 12 and {r["policy_hash"] for r in rows} == {spec["rubrics"][arm]["policy_hash"]}
        assert (root / "host_only" / "verifier" / f"0-{arm}" / "calibration.json").is_file()
    # registered endpoints over ALL eligible rows (abstentions are no rejection, never dropped)
    arms = result["arms"]
    assert arms["default"]["detection_rate"] == 0 and arms["default"]["abstained_host_fail_rows"] == 6
    assert arms["h0"]["rejected_host_fail_rows"] == 3 and arms["h1"]["detection_rate"] == 1
    assert arms["h2"]["detection_rate"] == 1 and arms["h2"]["rejected_host_pass_rows"] == 1
    primary = result["primary"]
    assert primary["difference"] == 1 and primary["informative_families"] == 4
    assert primary["p_value"] == pytest.approx(2 / 16) and primary["supported"] is False  # 4 families cannot reach 0.05
    assert result["safety"]["difference"] == pytest.approx(1 / 6)
    assert result["safety"]["noninferior"] is False and result["registered_wording"] == "no_supported_detection_difference"
    assert result["secondary_mcnemar"]["detection"] == {"treatment_only": 6, "control_only": 0,
                                                       "mcnemar_exact_p": pytest.approx(2 / 64)}
    # blinded audit: every h2/default disagreement, no rubric identity or host label in the packet
    packet = json.loads((root / "audit" / "packet.json").read_text())
    key = json.loads((root / "host_only" / "audit_key.json").read_text())["key"]
    assert len(packet["items"]) == 7 and set(key) == {i["item"] for i in packet["items"]}
    text = json.dumps(packet)
    assert "h2" not in text.replace(packet["record_hash"], "") and "host_status" not in text and "ARM:" not in text
    assert sum(v["rejecting_rubric"] == "h2" for v in key.values()) == 7
    # a finished study replays from its sealed evidence with no new call
    calls = len(api.judged)
    assert fr.run_study(spec, panel, root, fixture_api=api, fixture_evaluate=host) == result
    assert len(api.judged) == calls
    assert result["artifacts"] == fr._artifacts(root, Ledger(root, json.loads((root / "study.json").read_text()), None))


def test_fixed_rubric_verifier_never_proposes_or_researches(tmp_path):
    panel = _panel()
    spec = _spec(panel)
    value = fr._manifest(spec, panel)
    assert value["method"] == VERIFIER_METHOD and value["study"]["protocol_hash"] == spec["record_hash"]
    assert value["study"]["study_sources"] == study_sources(fr.MODULES)
    assert set(study_sources(fr.MODULES)) == {"feedback_study/__init__.py", "feedback_study/common.py",
                                              "feedback_study/fixed_rubric.py"}  # a later study's module never enters
    ledger = Ledger(tmp_path, value, API())
    verifier = FixedRubricVerifier(value, ledger, tmp_path, 0, "h2", spec["rubrics"]["h2"])
    for method in (verifier.run, verifier.propose_policy, verifier._research):
        with pytest.raises(AssertionError):
            method()
    assert verifier.arm == "adaptive_no_research" and verifier.rubric_arm == "h2"
    with pytest.raises(ValueError):
        FixedRubricVerifier(value, ledger, tmp_path, 0, "H2/../x", spec["rubrics"]["h2"])
    with pytest.raises(ValueError):
        FixedRubricVerifier(value, ledger, tmp_path, 0, "h2", {**spec["rubrics"]["h2"], "policy_hash": "0" * 64})


def test_the_protocol_is_frozen_before_any_call(tmp_path):
    panel = _panel()
    with pytest.raises(ValueError):
        _spec(panel, chain_break=True)  # the evolved rubrics must be one recorded chain from the default
    spec = _spec(panel)
    with pytest.raises(ValueError):
        fr.validate_spec({**spec, "arms": ["default", "h2"]})  # seal broken / not the registered arms
    with pytest.raises(ValueError):
        fr.run_study(spec, {**panel, "tasks": panel["tasks"][1:]}, tmp_path / "x", fixture_api=RubricAPI(),
                     fixture_evaluate=host)  # not the registered panel
    with pytest.raises(ValueError):
        fr.run_study(spec, panel, tmp_path / "y", fixture_api=RubricAPI(), fixture_evaluate=None)  # half a fixture


def test_an_interrupted_study_is_never_resumed(tmp_path):
    panel = _panel()
    spec = _spec(panel)
    root = tmp_path / "study"
    api = RubricAPI()
    fr.run_study(spec, panel, root, fixture_api=api, fixture_evaluate=host)
    (root / "result.json").unlink()  # as if the process had died before the result
    assert fr.run_study(spec, panel, root, fixture_api=api, fixture_evaluate=host)["reason"] == \
        "interrupted_study_no_automatic_resume"
    assert not (root / "result.json").exists()


def test_a_terminal_delivery_is_an_abstention_and_a_transport_failure_is_pending(tmp_path):
    panel = _panel()
    spec = _spec(panel)

    def h2_on_row(index):
        return lambda payload: (payload.get("rubric", {}).get("mechanism", "").startswith("ARM:h2")
                                and payload["task"]["question"].endswith(f"#{index}"))

    def length(row, cap):
        return _closed(row, "length", "truncated_content", tokens=min(cap, 100))

    api = RubricAPI({h2_on_row(1): length})  # row 1 (host fail) runs out of tokens twice under h2
    result = fr.run_study(spec, panel, tmp_path / "a", fixture_api=api, fixture_evaluate=host)
    assert result["status"] == "completed"
    h2 = result["arms"]["h2"]
    assert h2["terminal_delivery_rows"] == 1 and h2["rejected_host_fail_rows"] == 5 and h2["abstained_host_fail_rows"] == 1
    assert h2["eligible_host_fail_rows"] == 6  # the denominator never shrinks
    recoveries = [i for i in _verifier_intents(tmp_path / "a") if i["logical_id"].endswith(":length-recovery:1")]
    assert len(recoveries) == 1 and recoveries[0]["logical_id"].startswith("verifier:0-h2:judge:")

    def broken(row, cap):
        return {**row, "ok": False, "finish_reason": None, "status": 502, "stream_complete": False,
                "error_type": "http_error", "response": None}

    api = RubricAPI({h2_on_row(4): broken})
    result = fr.run_study(spec, panel, tmp_path / "b", fixture_api=api, fixture_evaluate=host)
    assert result["status"] == "pending" and result["reason"] == "verifier_call_failed"
    assert "primary" not in result and not (tmp_path / "b" / "audit").exists()


def _brute_force_sign_flip(differences):
    informative = [d for d in differences if d]
    observed = abs(sum(informative))
    hits = sum(abs(sum(s * d for s, d in zip(signs, informative))) >= observed
               for signs in itertools.product((1, -1), repeat=len(informative)))
    return hits / 2 ** len(informative)


def test_registered_statistics_are_exact():
    assert fr.sign_flip_two_sided([1, 1, 1])["p_value"] == pytest.approx(0.25)
    assert fr.sign_flip_two_sided([0, 0])["p_value"] == 1 and fr.sign_flip_two_sided([])["informative_families"] == 0
    rng = random.Random(7)
    for _ in range(50):
        differences = [rng.randint(-3, 3) for _ in range(rng.randint(1, 9))]
        assert fr.sign_flip_two_sided(differences)["p_value"] == pytest.approx(_brute_force_sign_flip(differences))
    assert fr.mcnemar_exact(5, 0) == pytest.approx(2 / 32) and fr.mcnemar_exact(0, 0) == 1 and fr.mcnemar_exact(3, 3) == 1
    families = [(1, 3), (0, 2), (-1, 4), (2, 5)]
    upper = fr.cluster_bootstrap_upper(families, seed=1, resamples=2000)
    assert upper == fr.cluster_bootstrap_upper(families, seed=1, resamples=2000)  # registered seed: deterministic
    assert 2 / 14 <= upper <= 1


def test_no_private_label_reaches_the_judge(tmp_path):
    panel = _panel()
    spec = _spec(panel)
    api = RubricAPI()  # the base fixture API asserts the private canary/label never appears in a prompt
    fr.run_study(spec, panel, tmp_path / "study", fixture_api=api, fixture_evaluate=host)
    assert api.prompts["verifier"] and all(PRIVATE_CANARY not in p and LABEL not in p for p in api.prompts["verifier"])
    assert all("host_audit" not in p and '"status": "fail"' not in p for p in api.prompts["verifier"])


# ----------------------------------------------------------------------------- review round 1 regressions
class _FakeVerifier:
    def __init__(self, arm, behaviour):
        self.rubric = {"policy_hash": arm}
        self.pending_reason = None
        self.behaviour = behaviour

    def judge_row(self, item, row):
        return self.behaviour(self, item, row)


def test_run_cells_starts_no_queued_cell_after_a_failure():
    """Codex L1 review P1: a failing worker publishes the abort itself, before any freed worker can take a queued
    cell; work already running finishes, nothing queued starts afterwards."""
    from skillopt.continual_learning.ledger import LearningPending
    from skillopt.feedback_study.common import run_cells

    started, gate = [], threading.Event()

    def behaviour(verifier, item, row):
        token = item
        started.append(token)
        if verifier.pending_reason:  # the frozen per-call abort check
            raise LearningPending(verifier.pending_reason)
        if token == "t1":
            raise LearningPending("verifier_call_failed")
        if token == "t2":  # running beside the failure: waits until the abort is published, then completes
            assert gate.wait(5) or verifier.pending_reason
            for _ in range(500):
                if verifier.pending_reason:
                    break
                threading.Event().wait(0.01)
        return {"evidence_hash": token, "policy_hash": verifier.rubric["policy_hash"]}

    verifiers = {"a": _FakeVerifier("a", behaviour)}
    pairs = {f"t{i}": (f"t{i}", None) for i in range(12)}
    cells = [("a", f"t{i}") for i in range(12)]
    gate.set()
    with pytest.raises(LearningPending, match="verifier_call_failed"):
        run_cells(cells, verifiers, pairs, workers=2)
    assert started[0] == "t0" and set(started) <= {"t0", "t1", "t2"}, started
    assert verifiers["a"].pending_reason == "verifier_call_failed"


def test_usage_gaps_follow_the_registered_frozen_completion_rule(tmp_path):
    """A failed attempt whose usage was never reported, then a successful retry: a cost-accounting gap, reported
    and not blocking (the rule every learning stage completes under). A delivered reply without usage blocks."""
    panel = _panel()
    spec = _spec(panel)
    assert spec["analysis"]["completion"].startswith("frozen_v10_ledger_blocking_usage_gap_rule")

    def first_cell(payload):
        return payload["task"]["question"].endswith("#2") and "ARM:h1" in payload["rubric"]["mechanism"]

    def retried_without_first_usage(row, cap):
        return {**row, "http_attempt_count": 2, "attempts": [{"usage": {}}, row["attempts"][0]]}

    result = fr.run_study(spec, panel, tmp_path / "a", fixture_api=RubricAPI({first_cell: retried_without_first_usage}),
                          fixture_evaluate=host)
    assert result["status"] == "completed" and result["usage_complete"] is False and result["unknown_cost_attempts"] == 1

    def delivered_without_usage(row, cap):
        return {**row, "usage": {}, "attempts": [{"usage": {}}]}

    result = fr.run_study(spec, panel, tmp_path / "b", fixture_api=RubricAPI({first_cell: delivered_without_usage}),
                          fixture_evaluate=host)
    assert result["status"] == "pending" and "primary" not in result


def test_source_shaped_rubric_traces_never_enter_the_study_delivery_counts(tmp_path):
    """Codex L1 review P2: the sealed source policy records carry their proposal calls in `trace`; the study's
    per-arm delivery accounting counts only the study's own judge calls (the protocol keeps the full records)."""
    panel = _panel()
    rubrics = _rubrics()
    historical = [{"stage": "policy", "request_hash": "a" * 64, "ok": True, "finish_reason": "stop", "http_attempts": 1,
                   "status": "parsed"},
                  {"stage": "policy", "request_hash": "b" * 64, "ok": True, "finish_reason": "stop", "http_attempts": 2,
                   "status": "parsed", "length_recovery_of": "c" * 64}]
    for arm in ("h0", "h1", "h2"):
        rubrics[arm] = {**rubrics[arm], "trace": historical, "record_hash": "d" * 64}
    template = dict(_spec(panel)["template"])
    spec = fr.build_spec(template, rubrics, {"fixture": True})
    assert spec["rubrics"]["h2"]["trace"] == historical  # the protocol preserves the full source record
    result = fr.run_study(spec, panel, tmp_path / "s", fixture_api=RubricAPI(), fixture_evaluate=host)
    for arm in fr.ARMS:
        delivery = result["arms"][arm]["v7_conditional"]["delivery"]
        assert delivery["calls"] == 12 and delivery["length_recoveries"] == 0 and delivery["requests"] == 12, arm


def test_status_verifies_the_finished_evidence_not_just_the_seal(tmp_path):
    """Codex L1 review P2: a changed, missing or extra governed artifact fails the zero-call status check."""
    import shutil

    from scripts import run_fivebench_fixed_rubric_study as cli

    panel = _panel()
    spec = _spec(panel)
    study = tmp_path / "out" / "study"
    fr.run_study(spec, panel, study, fixture_api=RubricAPI(), fixture_evaluate=host)
    assert cli.main(["status", "--output", str(tmp_path / "out")]) == 0
    for damage in ("change", "delete", "extra"):
        copy = tmp_path / damage
        shutil.copytree(tmp_path / "out", copy)
        target = sorted((copy / "study" / "verifier" / "0-h2" / "rows").glob("*.json"))[0]
        if damage == "change":
            target.write_text(target.read_text() + "\n")  # any byte change of a governed record
        elif damage == "delete":
            (copy / "study" / "schedule.json").unlink()
        else:
            (copy / "study" / "evaluations" / ("0" * 64 + ".json")).write_text("{}")
        with pytest.raises(ValueError):
            cli.main(["status", "--output", str(copy)])
        with pytest.raises(ValueError):
            fr.verify_result(copy / "study")


def test_the_solver_rollout_starts_with_one_row_alone(tmp_path):
    """The first real solver reply is the health barrier: no other train row starts before the first finished
    (the solver delivery/recovery path itself is the frozen Adapter every natural stage runs)."""
    panel = _panel()
    spec = _spec(panel)
    events, lock = [], threading.Lock()

    def tracked(task, skill):
        with lock:
            events.append(("start", task["task_id"]))
        out = host(task, skill)
        with lock:
            events.append(("end", task["task_id"]))
        return out

    fr.run_study(spec, panel, tmp_path / "study", fixture_api=RubricAPI(), fixture_evaluate=tracked)
    assert events[0] == ("start", "0") and events[1] == ("end", "0")
    assert sorted(t for kind, t in events if kind == "start") == sorted(str(i) for i in range(12))
