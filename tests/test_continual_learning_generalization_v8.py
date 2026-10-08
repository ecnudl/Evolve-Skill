"""Learning v8 controls (val selection, margin gate, labeled failure feedback, concurrency); not method effects."""
import json
import threading
import time
from copy import deepcopy

import pytest

from skillopt.continual_learning.contracts import (
    GENERALIZATION_VERSION,
    HARDENED_VERSIONS,
    manifest,
    role_partition,
    validate_manifest,
)
from skillopt.continual_learning.feedback import LABELED_PROFILE, PROFILE, expected_text, project
from skillopt.continual_learning.gepa import Adapter
from skillopt.continual_learning.ledger import LearningPending, Ledger
from skillopt.continual_learning.recovery import POLICY_V7, POLICY_V8, validate_policy
from skillopt.continual_learning.skillopt import (
    TRANSFER_PREAMBLE,
    _label_leak,
    _margin_selection,
    _train_labels,
    run_stage,
)
from skillopt.validator_pilot.api import digest
from tests.test_continual_learning_budget_v7 import API as V7API
from tests.test_continual_learning_domains import PRIVATE_CANARY, evaluate, setup

LABEL = "THE-LONG-EXPECTED-ANSWER-TEXT"


def auth(*, selection=4, iterations=1, benchmark="korbench", selection_partition="skill_confirmation",
         profile=LABELED_PROFILE, policy=POLICY_V8, version=GENERALIZATION_VERSION):
    _, base, args = setup(benchmark)
    task = base["tasks"][0]
    tasks = [{**deepcopy(task), "task_id": str(i), "family_id": str(i)} for i in range(2 + selection)]
    for row in tasks[2:]:
        row["partition"] = selection_partition
    for row in tasks:
        row["private"]["answer" if benchmark == "korbench" else "answers"] = (
            LABEL if benchmark == "korbench" else [LABEL, "alt"])
    panel = {**base, "tasks": tasks}
    args.update(version=version, recovery_policy=deepcopy(policy), train_families=["0", "1"],
                selection_families=[str(i) for i in range(2, 2 + selection)], feedback_profile=profile)
    args["model"]["transport"]["stream_wall_seconds"] = 3600
    args["budget"].update(max_iterations=iterations, max_metric_calls=200, max_api_calls=400,
                          max_reflection_calls=40)
    return manifest(panel, **args), panel


class API(V7API):
    """Fixture provider: the solver must never see a label; reflection may (v8 failed train rows)."""

    def __init__(self, content="Use the requested constant result.", *, fail_reflection_at=None, leak=False):
        super().__init__(content)
        self.fail_reflection_at, self.leak = fail_reflection_at, leak
        self.reflection_calls, self.solver_prompts, self.reflection_prompts = 0, [], []
        self.lock = threading.Lock()

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        with self.lock:
            if kind.endswith("solver"):
                assert LABEL not in system + user and PRIVATE_CANARY not in system + user
                self.solver_prompts.append(user)
            else:
                self.reflection_prompts.append(system + "\n" + user)
                self.reflection_calls += 1
                index = self.reflection_calls
        request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                   "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        if kind.endswith("solver"):
            response = "<answer>one</answer>" if "requested constant" in system else "<answer>zero</answer>"
        else:
            if self.fail_reflection_at is not None and index >= self.fail_reflection_at:
                return {"request": request, "request_hash": digest(request), "response": None, "ok": False,
                        "finish_reason": None, "usage": {"prompt_tokens": 5, "completion_tokens": 0},
                        "http_attempt_count": 1, "attempts": [{"usage": {"prompt_tokens": 5, "completion_tokens": 0}}]}
            content = self.content + (" " + LABEL if self.leak else "")
            response = json.dumps({"batch_size": 2, "patch": {"reasoning": "Fixture only", "edits": [
                {"op": "append", "content": content}]}})
        return {"request": request, "request_hash": digest(request), "response": response, "ok": True,
                "finish_reason": "stop", "usage": {"prompt_tokens": 20, "completion_tokens": 20},
                "http_attempt_count": 1, "attempts": [{"usage": {"prompt_tokens": 20, "completion_tokens": 20}}]}


def _rows(scores):
    return [{"score": s} for s in scores]


def _items(n):
    return [{"role": "selection", "task": {"family_id": str(i)}} for i in range(n)]


# ----------------------------------------------------------------------------- contracts
def test_v8_policy_is_explicit_and_selection_role_is_val():
    assert POLICY_V8["skill_budget_bytes"] == POLICY_V7["skill_budget_bytes"] == 32000
    assert POLICY_V8["selection_partition"] == "skill_confirmation" and POLICY_V8["solver_workers"] == 8
    assert role_partition(GENERALIZATION_VERSION, "selection") == "skill_confirmation"
    assert role_partition(GENERALIZATION_VERSION, "train") == "development"
    assert role_partition("continual-learning-v7", "selection") == "development"
    assert GENERALIZATION_VERSION in HARDENED_VERSIONS
    model = {"provider": "fixture", "transport": {"stream_wall_seconds": 3600}}
    validate_policy(POLICY_V8, model, GENERALIZATION_VERSION)
    with pytest.raises(ValueError):
        validate_policy(POLICY_V7, model, GENERALIZATION_VERSION)


def test_v8_manifest_requires_val_selection_development_train_and_labeled_profile():
    value, panel = auth()
    assert validate_manifest(value, panel) == value
    assert value["solver_workers"] == 8 and value["selection_partition"] == "skill_confirmation"
    assert value["feedback_profile"] == LABELED_PROFILE
    with pytest.raises(ValueError, match="development"):
        auth(selection_partition="development")
    with pytest.raises(ValueError, match="development"):
        auth(selection_partition="final")
    with pytest.raises(ValueError, match="labeled"):
        auth(profile=PROFILE)
    with pytest.raises(ValueError, match="v8/v9 only"):
        auth(version="continual-learning-v7", policy=POLICY_V7, selection_partition="development")
    v7, _ = auth(version="continual-learning-v7", policy=POLICY_V7, profile=PROFILE,
                 selection_partition="development")
    assert v7["solver_workers"] == 1 and "selection_partition" not in v7


# ----------------------------------------------------------------------------- gate
def test_margin_gate_charges_new_unknowns_and_never_compensates():
    policy = POLICY_V8
    # Codex counterexample 1: two passes become unknown, one failure becomes a pass -> v7 accepted.
    parent = _rows([1] * 10 + [0] * 10)
    candidate = _rows([None, None] + [1] * 8 + [1] + [0] * 9)
    record = _margin_selection(parent, candidate, _items(20), policy)
    assert record["wins"] == 1 and record["losses"] == 2 and record["candidate_new_unknown"] == 2
    assert record["net_wins"] == -1 and not record["accepted"]
    # Counterexample 2: resolved unknowns do not offset lost passes.
    parent = _rows([1] * 10 + [0] * 5 + [None] * 5)
    candidate = _rows([None] * 5 + [1] * 5 + [1] + [0] * 4 + [0] * 5)
    record = _margin_selection(parent, candidate, _items(20), policy)
    assert record["parent_unknown"] == 5 and record["net_wins"] == 1 - 5 and not record["accepted"]
    # One lucky position is not an update.
    parent = _rows([0] * 50 + [1] * 50)
    candidate = _rows([1] + [0] * 49 + [1] * 50)
    record = _margin_selection(parent, candidate, _items(100), policy)
    assert record["net_wins"] == 1 and record["required_net_wins"] == 3 and not record["accepted"]
    # A real margin across distinct families is accepted; the fraction scales the margin.
    candidate = _rows([1] * 4 + [0] * 46 + [1] * 50)
    record = _margin_selection(parent, candidate, _items(100), policy)
    assert record["accepted"] and record["families_improving"] == 4 and record["families_regressing"] == 0
    big = _margin_selection(_rows([0] * 300), _rows([1] * 5 + [0] * 295), _items(300), policy)
    assert big["required_net_wins"] == 6 and not big["accepted"]


def test_margin_gate_requires_candidate_coverage_too():
    # Codex case: parent 50 fail + 50 unknown; candidate passes 27 of the failures, everything else unknown.
    parent = _rows([0] * 50 + [None] * 50)
    candidate = _rows([1] * 27 + [None] * 73)
    record = _margin_selection(parent, candidate, _items(100), POLICY_V8)
    assert record["wins"] == 27 and record["losses"] == 23 and record["candidate_known"] == 27
    assert not record["coverage_admissible"] and not record["accepted"]


def test_margin_gate_needs_more_families_improving_than_regressing():
    items = [{"role": "selection", "task": {"family_id": "A"}}] * 6 + [{"role": "selection", "task": {"family_id": str(i)}}
                                                                          for i in range(3)]
    parent = _rows([0] * 6 + [1] * 3)
    candidate = _rows([1] * 6 + [0] * 3)  # +6 on one rule, -1 on each of three other rules
    record = _margin_selection(parent, candidate, items, POLICY_V8)
    assert record["net_wins"] == 3 and record["families_improving"] == 1 and record["families_regressing"] == 3
    assert not record["accepted"]


def test_label_leak_detects_only_new_long_labels_per_individual_answer():
    items = [{"task": {"private": {"answers": [LABEL, "alias-of-the-answer"]}}},
             {"task": {"private": {"answers": ["short"]}}},
             {"task": {"private": {"answers": ["PASSED-ROW-LABEL-NOT-CHECKED"]}}},
             {"task": {"private": {"answers": ["UNKNOWN-ROW-LABEL-NOT-CHECKED"]}}}]
    rows = [{"score": 0, "output": {"evidence_hash": "a" * 64}}, {"score": 0, "output": {"evidence_hash": "b" * 64}},
            {"score": 1, "output": {"evidence_hash": "c" * 64}}, {"score": None, "output": {"evidence_hash": "d" * 64}}]
    labels = _train_labels("searchqa", items, rows)
    assert labels == [("a" * 64, LABEL), ("a" * 64, "alias-of-the-answer"), ("b" * 64, "short")]
    # Each authorized answer is checked on its own, not the joined display text.
    assert _label_leak("rule: always answer " + LABEL, "", labels, POLICY_V8) == ["a" * 64]
    assert _label_leak("rule: alias-of-the-answer is typical", "", labels, POLICY_V8) == ["a" * 64]
    assert _label_leak("rule: say short", "", labels, POLICY_V8) == []
    assert _label_leak("rule: " + LABEL, "parent already had " + LABEL, labels, POLICY_V8) == []
    assert _label_leak("PASSED-ROW-LABEL-NOT-CHECKED", "", labels, POLICY_V8) == []
    kor = _train_labels("korbench", [{"task": {"private": {"answer": "[[ANSWER]]"}}}], [rows[0]])
    assert kor == [("a" * 64, "[[ANSWER]]")]


# ----------------------------------------------------------------------------- feedback
def test_labeled_projection_only_on_failed_train_rows():
    value, panel = auth()
    task = panel["tasks"][0]
    prediction = {"status": "available", "output": "zero"}
    fail = {"status": "fail", "score": 0, "metrics": {}}
    train = project(value, task["public"], prediction, fail, private=task["private"], role="train")
    assert train["Feedback"] == {"status": "fail", "score": 0, "expected": LABEL}
    selection = project(value, task["public"], prediction, fail, private=task["private"], role="selection")
    assert selection["Feedback"] == {"status": "fail", "score": 0}
    ok = project(value, task["public"], prediction, {"status": "pass", "score": 1}, private=task["private"], role="train")
    assert ok["Feedback"] == {"status": "pass", "score": 1}
    with pytest.raises(ValueError, match="private"):
        project(value, task["public"], prediction, fail, role="train")
    assert expected_text("searchqa", {"answers": ["a", "b"]}) == "a | b"
    assert expected_text("spreadsheetbench", {"test_files": []}) is None
    assert expected_text("korbench", {"answer": "x" * 5000}).endswith("…[truncated]")
    # A v7 manifest never gains labels, whatever the caller passes.
    v7, panel7 = auth(version="continual-learning-v7", policy=POLICY_V7, profile=PROFILE,
                      selection_partition="development")
    legacy = project(v7, task["public"], prediction, fail, private=task["private"], role="train")
    assert legacy["Feedback"] == {"status": "fail", "score": 0}


# ----------------------------------------------------------------------------- learner
def test_v8_stage_accepts_only_with_margin_and_labels_reach_reflection_not_solver(tmp_path):
    value, panel = auth(selection=4)
    api = API()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=api,
                       fixture_evaluate=evaluate("korbench"))
    assert result["status"] == "completed" and result["accepted_steps"] == 1
    assert "requested constant" in result["candidate_skill"]
    step = result["steps"][0]
    assert step["gate_action"] == "accept_margin" and step["wins"] == 4 and step["losses"] == 0
    assert step["required_net_wins"] == 3 and step["families_improving"] == 4
    assert any(LABEL in p for p in api.reflection_prompts), "failed train rows show the expected answer"
    assert all(LABEL not in p for p in api.solver_prompts)
    assert any(TRANSFER_PREAMBLE.strip()[:40] in p for p in api.reflection_prompts)
    # Completed replay re-verifies evidence without new calls.
    calls = len(api.solver_prompts) + api.reflection_calls
    replay = run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=evaluate("korbench"))
    assert replay == result and len(api.solver_prompts) + api.reflection_calls == calls


def test_v8_stage_rejects_a_one_position_change(tmp_path):
    value, panel = auth(selection=4)

    def flaky(task, skill):
        prediction, score = evaluate("korbench")(task, skill)
        if task["task_id"] != "2":  # only one selection task improves under the candidate
            score = {**score, "status": "fail", "score": 0.0}
        return prediction, score

    result = run_stage(value, panel, tmp_path / "stage", fixture_api=API(), fixture_evaluate=flaky)
    assert result["status"] == "completed" and result["accepted_steps"] == 0
    assert result["candidate_skill"] == "" and result["steps"][0]["gate_action"] == "reject_margin"
    assert result["steps"][0]["net_wins"] == 1


def test_v8_stage_rejects_a_candidate_that_copies_a_train_label(tmp_path):
    value, panel = auth(selection=4)
    api = API(leak=True)
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=evaluate("korbench"))
    assert result["status"] == "completed" and result["candidate_skill"] == ""
    assert result["steps"][0]["gate_action"] == "reject_label_leakage" and result["steps"][0]["leaked_evidence"]
    # The leaking candidate was never evaluated on the selection rows.
    assert all("requested constant" not in p for p in api.solver_prompts)


def test_v8_keeps_an_accepted_prefix_when_a_later_iteration_stops(tmp_path):
    value, panel = auth(selection=4, iterations=2)
    api = API(fail_reflection_at=2)  # the second iteration's first analyst call is unavailable
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=evaluate("korbench"))
    assert result["status"] == "completed" and result["accepted_steps"] == 1
    assert result["iterations_completed"] is False
    assert result["reason"].startswith("accepted_prefix_kept_after_stop:native_reflection_incomplete")
    assert "requested constant" in result["candidate_skill"]
    # Without an accepted step the same stop stays Pending with the parent.
    value2, panel2 = auth(selection=4, iterations=1)
    pending = run_stage(value2, panel2, tmp_path / "stage2", fixture_api=API(fail_reflection_at=1),
                        fixture_evaluate=evaluate("korbench"))
    assert pending["status"] == "pending" and pending["candidate_skill"] == ""


# ----------------------------------------------------------------------------- concurrency
def test_v8_ledger_serves_concurrent_callers_and_counts_every_call(tmp_path):
    value, _ = auth()
    api = API()
    root = tmp_path / "ledger"
    ledger = Ledger(root, value, api)
    errors = []

    def work(i):
        try:
            receipt = ledger.call("solver", f"row:{i}", "system", f"user {i}", 50)
            assert receipt["ok"]
        except Exception as exc:  # noqa: BLE001 - collected for the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    costs = ledger.snapshot()
    assert costs["logical_calls"] == costs["terminal_calls"] == 12 and costs["unclosed_calls"] == 0
    assert costs["usage_complete"] and not ledger.usage_blocks_completion(costs)
    # Replay of a recorded call is served from the receipt, with no provider call.
    before = len(api.solver_prompts)
    ledger.call("solver", "row:0", "system", "user 0", 50)
    assert len(api.solver_prompts) == before
    # A v7 ledger never reports in-flight calls.
    v7, _ = auth(version="continual-learning-v7", policy=POLICY_V7, profile=PROFILE, selection_partition="development")
    with pytest.raises(ValueError, match="v8"):
        Ledger(tmp_path / "v7", v7, api)._snapshot(inflight=1)


def test_v8_adapter_keeps_batch_order_and_stops_after_a_failure(tmp_path):
    value, panel = auth(selection=8)
    root = tmp_path / "adapter"
    ledger = Ledger(root, value, API())
    order = []

    def slow(task, skill):
        order.append(task["task_id"])
        return evaluate("korbench")(task, skill)

    adapter = Adapter(value, root, ledger, fixture_evaluate=slow)
    batch = [{"role": "selection", "task": t} for t in panel["tasks"][2:]]
    rows = adapter.evaluate_rows(batch, {"skill": ""})
    assert [r["trajectory"]["Inputs"] for r in rows] == [t["public"] for t in panel["tasks"][2:]]
    assert sorted(order) == [str(i) for i in range(2, 10)] and adapter.calls == 8

    started = []

    def broken(task, skill):
        started.append(task["task_id"])
        if task["task_id"] == "3":
            return {"status": "available", "output": "zero", "reason": "fixture"}, {
                "status": "unknown", "score": None, "reason": "native_cleanup_unconfirmed", "metrics": {}}
        time.sleep(0.05)
        return evaluate("korbench")(task, skill)

    big_value, big_panel = auth(selection=40)
    adapter2 = Adapter(big_value, tmp_path / "adapter2", Ledger(tmp_path / "adapter2", big_value, API()),
                       fixture_evaluate=broken)
    big_batch = [{"role": "selection", "task": t} for t in big_panel["tasks"][2:]]
    with pytest.raises(LearningPending, match="cleanup"):
        adapter2.evaluate_rows(big_batch, {"skill": ""})
    assert adapter2.pending_reason == "native_cleanup_unconfirmed"
    # The failure in row "3" stops admission: far fewer than the 40 rows start (at most the running wave).
    assert len(started) < 24, started


def test_v8_propose_native_identity_binds_the_transfer_preamble(tmp_path):
    value, panel = auth(selection=4)
    api = API()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=evaluate("korbench"))
    identity = json.loads((tmp_path / "stage/native/0/identity.json").read_text())
    assert identity["analyst_preamble"] == "transfer-requirement-v1" and identity["native_generic_prompts"] is False
    assert result["steps"][0]["gate_action"] == "accept_margin"
    # A v7 proposal keeps the repository's generic analyst prompts (identity unchanged).
    v7, panel7 = auth(selection=4, version="continual-learning-v7", policy=POLICY_V7, profile=PROFILE,
                      selection_partition="development")
    legacy = run_stage(v7, panel7, tmp_path / "v7", fixture_api=API(), fixture_evaluate=evaluate("korbench"))
    identity7 = json.loads((tmp_path / "v7/native/0/identity.json").read_text())
    assert identity7["native_generic_prompts"] is True and "analyst_preamble" not in identity7
    assert legacy["status"] == "completed"


def test_v8_gepa_guard_applies_margin_and_leak_rules_on_the_full_panel():
    from skillopt.continual_learning.gepa import _guard_official_best

    value, _ = auth(selection=4)
    full_items = _items(100)
    full_parent = _rows([0] * 50 + [1] * 40 + [None] * 10)
    # the optimizer saw only the parent-known positions (90); the final gate must use all 100
    known_items = full_items[:90]
    known_parent = full_parent[:90]

    class Fake:
        imputed = {}
        leaked_candidates = {}

        def __init__(self, rows, labels=()):
            self.rows, self.train_labels = rows, list(labels)
            self.seen = []

        def evaluate_rows(self, batch, candidate):
            self.seen.append(len(batch))
            return self.rows[:len(batch)]

    plus_one = Fake(_rows([1] + [0] * 49 + [1] * 40 + [None] * 10))
    skill, record = _guard_official_best(plus_one, value, "better?", known_items, known_parent, (full_items, full_parent))
    assert skill == value["parent_skill"] and record["official_best_rejected"] == "margin_or_coverage"
    assert plus_one.seen == [100] and record["final_margin"]["selection_positions"] == 100
    good = Fake(_rows([1] * 5 + [0] * 45 + [1] * 40 + [None] * 10))
    skill, record = _guard_official_best(good, value, "better", known_items, known_parent, (full_items, full_parent))
    assert skill == "better" and record["final_margin"]["accepted"]
    leaked = Fake(_rows([1] * 5 + [0] * 45 + [1] * 40 + [None] * 10), labels=[("e" * 64, LABEL)])
    skill, record = _guard_official_best(leaked, value, "copy " + LABEL, known_items, known_parent, (full_items, full_parent))
    assert skill == value["parent_skill"] and record["official_best_rejected"] == "label_leakage" and leaked.seen == []
    with pytest.raises(ValueError, match="unfiltered"):
        _guard_official_best(good, value, "better", known_items, known_parent)


def test_v8_adapter_refuses_a_leaking_candidate_before_any_execution_and_tracks_labels(tmp_path):
    value, panel = auth(selection=4)
    root = tmp_path / "adapter"
    executed = []

    def evaluate_fixture(task, skill):
        executed.append((task["task_id"], skill))
        return evaluate("korbench")(task, skill)

    adapter = Adapter(value, root, Ledger(root, value, API()), fixture_evaluate=evaluate_fixture)
    adapter.refuse_leaks = True  # as the GEPA stage sets it; native SkillOpt checks candidates itself
    train = [{"role": "train", "task": t} for t in panel["tasks"][:2]]
    rows = adapter.evaluate_rows(train, {"skill": ""})  # parent fails both train rows -> labels exposed
    assert all(r["score"] == 0.0 for r in rows) and [l for _, l in adapter.train_labels] == [LABEL, LABEL]
    before = len(executed)
    leaking = {"skill": "Always answer " + LABEL}
    refused = adapter.evaluate_rows(train, leaking)
    assert len(executed) == before, "a leaking candidate must never reach the solver"
    assert all(r["score"] == 0.0 and r["trajectory"] is None for r in refused)
    assert list(adapter.leaked_candidates.values()) == [sorted({r["output"]["evidence_hash"] for r in rows})]
    assert not (root / "evaluations").exists() or len(list((root / "evaluations").glob("*.json"))) == 2
    # A clean candidate is executed normally.
    adapter.evaluate_rows(train, {"skill": "Use the requested constant result."})
    assert len(executed) == before + 2


def test_v8_completion_after_a_stop_requires_closed_evaluations(tmp_path):
    from skillopt.continual_learning.skillopt import _evaluations_closed

    root = tmp_path / "stage"
    (root / "evaluation_intents").mkdir(parents=True)
    (root / "evaluations").mkdir()
    write = lambda path, value: path.write_text(json.dumps(value))  # noqa: E731
    from skillopt.coevolution_v5.core import seal as _seal
    write(root / "evaluation_intents/a.json", _seal({"x": 1}))
    write(root / "evaluations/a.json", _seal({"request": {}, "prediction": {"status": "available"}, "score": {"status": "pass"}}))
    assert _evaluations_closed(root)
    write(root / "evaluation_intents/b.json", _seal({"x": 2}))  # open intent
    assert not _evaluations_closed(root)
    write(root / "evaluations/b.json", _seal({"request": {}, "prediction": {"status": "available", "cleanup_confirmed": False},
                                              "score": {"status": "unknown"}}))
    assert not _evaluations_closed(root)  # unconfirmed cleanup


def test_native_learner_never_asks_the_adapter_to_refuse_its_own_parent(tmp_path):
    """The accepted parent may contain a label exposed only later; native SkillOpt keeps evaluating it."""
    value, panel = auth(selection=4, iterations=2)
    api = API()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=evaluate("korbench"))
    assert result["status"] == "completed" and result["accepted_steps"] == 1
    # second iteration evaluated the accepted parent on train rows and proposed from them (no refusal rows)
    assert len(result["steps"]) == 2 and result["steps"][1]["gate_action"] in {"no_update_proposed", "reject_margin",
                                                                                "accept_margin"}
    assert result["leaked_candidates_refused"] == 0


# ----------------------------------------------------------------------------- v9: two-pass sign-test gate
def auth9(**kwargs):
    from skillopt.continual_learning.recovery import POLICY_V9

    return auth(version="continual-learning-v9", policy=POLICY_V9, **kwargs)


def test_sign_test_p_is_the_exact_one_sided_binomial_tail():
    from skillopt.continual_learning.skillopt import sign_test_p

    assert sign_test_p(0, 0) == 1.0 and sign_test_p(1, 0) == 0.5 and sign_test_p(0, 5) == 1.0
    assert abs(sign_test_p(29, 15) - 0.0244) < 5e-4      # the 10/6 KOR candidate v8 accepted (not < 0.05/3)
    assert abs(sign_test_p(11, 4) - 0.0592) < 5e-4       # the 10/6 SearchQA third step
    assert sign_test_p(34, 5) < 1e-5 and sign_test_p(9, 7) > 0.4
    with pytest.raises(ValueError):
        sign_test_p(-1, 2)


class _Replay:
    """Adapter stand-in: returns scripted rows per (skill, rollout) and records every evaluation."""

    def __init__(self, script):
        self.script, self.seen = script, []

    def evaluate_rows(self, batch, candidate, *, rollout=None):
        self.seen.append((candidate["skill"], rollout, len(batch)))
        return self.script[(candidate["skill"], rollout)]


def _family_items(n, per_family):
    return [{"role": "selection", "task": {"family_id": f"rule{i // per_family}"}} for i in range(n)]


def test_v9_gate_screens_on_pass_one_and_decides_on_the_fresh_pass_alone():
    from skillopt.continual_learning.recovery import POLICY_V9
    from skillopt.continual_learning.skillopt import confirm_selection

    items = _items(100)                       # one family per task
    parent1 = _rows([0] * 50 + [1] * 50)
    # (a) not positive enough at the screen: no confirmation calls at all
    weak = _rows([1] * 3 + [0] * 47 + [1] * 49 + [0])            # 3 families up / 1 down, p = 0.3125
    adapter = _Replay({})
    record = confirm_selection(adapter, items, "P", "C", parent1, weak, POLICY_V9, tries=3, rollout=1)
    assert record["gate_action"] == "reject_screen" and not record["accepted"] and adapter.seen == []
    # (b) lucky first pass (10 up / 2 down, p = 0.019) that does not replicate: rejected on the fresh pass
    lucky = _rows([1] * 10 + [0] * 40 + [1] * 48 + [0] * 2)
    adapter = _Replay({("P", 1): _rows([0] * 50 + [1] * 50), ("C", 1): _rows([1] * 3 + [0] * 47 + [1] * 47 + [0] * 3)})
    record = confirm_selection(adapter, items, "P", "C", parent1, lucky, POLICY_V9, tries=3, rollout=1)
    assert adapter.seen == [("P", 1, 100), ("C", 1, 100)]
    assert record["gate_action"] == "reject_confirmation" and record["confirmation_pass"]["net_wins"] == 0
    # (c) an effect that replicates: the confirmation pass alone is significant (18 up / 3 down, p = 0.0007)
    real = _rows([1] * 20 + [0] * 30 + [1] * 48 + [0] * 2)
    adapter = _Replay({("P", 2): _rows([0] * 50 + [1] * 50), ("C", 2): _rows([1] * 18 + [0] * 32 + [1] * 47 + [0] * 3)})
    record = confirm_selection(adapter, items, "P", "C", parent1, real, POLICY_V9, tries=3, rollout=2)
    assert record["gate_action"] == "accept_confirmed" and record["accepted"]
    assert record["wins"] == 18 and record["losses"] == 3 and record["confirmation_p_value"] < 0.05 / 3
    assert record["accept_alpha_effective"] == 0.05 / 3 and record["confirmation_rollout"] == 2
    # (d) Codex case: a huge first pass (30/0) whose fresh pass shows 1/0 is NOT confirmed -- the first pass
    #     (shared, possibly unlucky parent draw) never enters the accepted p-value
    huge = _rows([1] * 30 + [0] * 20 + [1] * 50)
    adapter = _Replay({("P", 1): _rows([0] * 50 + [1] * 50), ("C", 1): _rows([1] + [0] * 49 + [1] * 50)})
    record = confirm_selection(adapter, items, "P", "C", parent1, huge, POLICY_V9, tries=3, rollout=1)
    assert record["first_pass"]["family_p_value"] < 1e-8 and record["confirmation_pass"]["wins"] == 1
    assert record["confirmation_p_value"] == 0.5 and not record["accepted"]
    # (e) Codex case: the SAME four tasks winning twice is four families, not eight trials (p = 0.0625 > 0.0167)
    four = _rows([1] * 4 + [0] * 46 + [1] * 50)
    adapter = _Replay({("P", 1): parent1, ("C", 1): four})
    record = confirm_selection(adapter, items, "P", "C", parent1, four, POLICY_V9, tries=3, rollout=1)
    assert record["confirmation_pass"]["family_p_value"] == 0.0625 and not record["accepted"]
    # (f) a new unknown in the fresh pass is a loss, and JOINTLY known coverage must reach the floor
    adapter = _Replay({("P", 1): _rows([0] * 50 + [1] * 50), ("C", 1): _rows([None] * 60 + [1] * 40)})
    record = confirm_selection(adapter, items, "P", "C", parent1, real, POLICY_V9, tries=3, rollout=1)
    assert not record["accepted"] and record["confirmation_pass"]["candidate_new_unknown"] == 60
    assert record["confirmation_pass"]["jointly_known"] == 40
    half_parent = _rows([None] * 50 + [0] * 25 + [1] * 25)       # 50% marginal each, 40% jointly known
    half_cand = _rows([1] * 10 + [None] * 40 + [1] * 40 + [None] * 10)
    adapter = _Replay({("P", 1): half_parent, ("C", 1): half_cand})
    record = confirm_selection(adapter, items, "P", "C", parent1, real, POLICY_V9, tries=3, rollout=1)
    assert record["confirmation_pass"]["jointly_known"] == 40 and not record["accepted"]


def test_v9_gate_counts_one_sign_per_rule_not_per_task():
    """Codex case: 14 rules up and 11 down, ten tasks each -- position-level p looks tiny, rule-level p = 0.345."""
    from skillopt.continual_learning.recovery import POLICY_V9
    from skillopt.continual_learning.skillopt import _paired_counts, confirm_selection, sign_test_p

    items = _family_items(250, 10)
    parent = _rows([0] * 140 + [1] * 110)
    candidate = _rows([1] * 140 + [0] * 110)        # 140 wins / 110 losses, but only 14 vs 11 rules
    counts = _paired_counts(parent, candidate, items)
    assert counts["wins"] == 140 and counts["losses"] == 110 and counts["families"] == 25
    assert counts["families_improving"] == 14 and counts["families_regressing"] == 11
    assert abs(counts["family_p_value"] - 0.345) < 1e-3 and sign_test_p(140, 110) < 0.04
    record = confirm_selection(_Replay({}), items, "P", "C", parent, candidate, POLICY_V9, tries=3, rollout=1)
    assert record["gate_action"] == "reject_screen"
    # a broad rule-level effect (20 of 25 rules up, none down) passes screen and confirmation
    broad = _rows([1] * 200 + [0] * 50)
    parent_b = _rows([0] * 200 + [0] * 50)
    adapter = _Replay({("P", 1): parent_b, ("C", 1): broad})
    record = confirm_selection(adapter, items, "P", "C", parent_b, broad, POLICY_V9, tries=3, rollout=1)
    assert record["accepted"] and record["confirmation_pass"]["families_improving"] == 20


def test_v9_adapter_draws_fresh_selection_samples_only_for_confirmation_passes(tmp_path):
    value, panel = auth9(selection=4)
    assert value["version"] == "continual-learning-v9" and value["solver_workers"] == 8
    calls = []

    def counted(task, skill):
        calls.append(task["task_id"])
        return evaluate("korbench")(task, skill)

    root = tmp_path / "adapter"
    adapter = Adapter(value, root, Ledger(root, value, API()), fixture_evaluate=counted)
    batch = [{"role": "selection", "task": t} for t in panel["tasks"][2:]]
    adapter.evaluate_rows(batch, {"skill": ""})
    adapter.evaluate_rows(batch, {"skill": ""})               # cached: the first pass is one sample
    assert len(calls) == 4
    adapter.evaluate_rows(batch, {"skill": ""}, rollout=1)    # confirmation pass: fresh samples
    assert len(calls) == 8
    with pytest.raises(ValueError, match="Rollout"):
        adapter.evaluate_rows(batch, {"skill": ""}, rollout=0)
    # v8 never re-samples selection rows
    value8, panel8 = auth(selection=4)
    adapter8 = Adapter(value8, tmp_path / "a8", Ledger(tmp_path / "a8", value8, API()), fixture_evaluate=counted)
    with pytest.raises(ValueError, match="Rollout"):
        adapter8.evaluate_rows([{"role": "selection", "task": t} for t in panel8["tasks"][2:]], {"skill": ""}, rollout=1)


def test_v9_stage_accepts_a_replicating_candidate_and_rejects_a_one_position_change(tmp_path):
    value, panel = auth9(selection=8)
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=API(), fixture_evaluate=evaluate("korbench"))
    step = result["steps"][0]
    assert result["status"] == "completed" and result["accepted_steps"] == 1
    assert step["gate_action"] == "accept_confirmed" and step["first_pass"]["wins"] == 8
    assert step["confirmation_pass"]["wins"] == 8 and step["wins"] == 8 and step["losses"] == 0
    assert step["confirmation_p_value"] == 0.5 ** 8 and step["confirmation_pass"]["families_improving"] == 8
    identity = json.loads((tmp_path / "stage/identity.json").read_text())
    assert identity["gate"] == "v9_family_sign_test_screen_then_fresh_confirmation_on_val"

    def one_position(task, skill):
        prediction, score = evaluate("korbench")(task, skill)
        if task["task_id"] != "2":
            score = {**score, "status": "fail", "score": 0.0}
        return prediction, score

    value2, panel2 = auth9(selection=8)
    rejected = run_stage(value2, panel2, tmp_path / "stage2", fixture_api=API(), fixture_evaluate=one_position)
    assert rejected["accepted_steps"] == 0 and rejected["candidate_skill"] == ""
    assert rejected["steps"][0]["gate_action"] == "reject_screen"      # 1 win / 0 losses: p = 0.5


def test_v9_parser_policy_escapes_raw_control_characters_inside_strings_only():
    from skillopt.continual_learning.recovery import POLICY_V8, POLICY_V9
    from skillopt.continual_learning.reflection_json import CONTROL_POLICY, NativeJSONError, prepare_native_json

    assert POLICY_V9["reflection_parser"] == CONTROL_POLICY and POLICY_V8["reflection_parser"] == "strict-json-invalid-escape-v1"
    raw = '{"patch": {"edits": [{"op": "append", "content": "```python\nx = 1\n```\nApply it."}]}}'
    with pytest.raises(NativeJSONError, match="invalid_json_document"):
        prepare_native_json(raw)                         # v1: a raw newline inside a string is invalid JSON
    text, audit = prepare_native_json(raw, CONTROL_POLICY)
    assert json.loads(text)["patch"]["edits"][0]["content"] == "```python\nx = 1\n```\nApply it."
    assert audit["status"] == "repaired" and audit["repair_count"] == 3
    assert len(audit["escape_control_character_at_response_byte_offsets"]) == 3
    # outside strings nothing is touched; invalid documents are still rejected
    with pytest.raises(NativeJSONError, match="invalid_json_document"):
        prepare_native_json('{"a": 1,\n "b": }', CONTROL_POLICY)
    assert prepare_native_json('{\n  "a": "b"\n}', CONTROL_POLICY)[1]["status"] == "strict"
    with pytest.raises(NativeJSONError, match="unsupported_parser_policy"):
        prepare_native_json("{}", "no-such-policy")
    # Codex case: a backslash immediately followed by a raw newline -> doubled backslash + escaped newline
    tricky = '{"a": "x\\\ny"}'
    text, audit = prepare_native_json(tricky, CONTROL_POLICY)
    assert json.loads(text)["a"] == "x\\\ny" and audit["repair_count"] == 2
    assert len(audit["insert_backslash_before_response_byte_offsets"]) == 1
    assert len(audit["escape_control_character_at_response_byte_offsets"]) == 1


def test_v9_stage_recovers_an_analyst_reply_with_a_raw_newline(tmp_path):
    class NewlineAPI(API):
        def call(self, system, user, kind, key, *, max_tokens, repeat):
            row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
            if not kind.endswith("solver") and row.get("response"):
                row["response"] = row["response"].replace("Use the requested constant result.",
                                                          "Use the requested constant result.\nAlways.")
            return row

    value, panel = auth9(selection=8)
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=NewlineAPI(), fixture_evaluate=evaluate("korbench"))
    assert result["status"] == "completed" and result["accepted_steps"] == 1
    assert "requested constant result.\nAlways." in result["candidate_skill"]
    audit = json.loads((tmp_path / "stage/native/0/parser_audits/0.json").read_text())
    assert audit["version"] == "strict-json-invalid-escape-control-v2" and audit["status"] == "repaired"
    # the same reply under v8 stays pending (its parser policy is frozen at v1)
    value8, panel8 = auth(selection=8)
    pending = run_stage(value8, panel8, tmp_path / "v8", fixture_api=NewlineAPI(), fixture_evaluate=evaluate("korbench"))
    assert pending["status"] == "pending" and pending["reason"] == "native_reflection_incomplete"


def test_v9_bridge_retries_a_malformed_analyst_document_once(tmp_path):
    class MalformedAPI(API):
        """Every analyst reply is malformed the first time (missing comma) and valid on the retry."""

        def __init__(self, *, always_bad=False):
            super().__init__()
            self.always_bad, self.analyst_calls, self.retry_prompts = always_bad, 0, []

        def call(self, system, user, kind, key, *, max_tokens, repeat):
            row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
            if not kind.endswith("solver") and row.get("response"):
                is_retry = "could not be parsed" in user
                if is_retry:
                    self.retry_prompts.append(user)
                if self.always_bad or not is_retry:
                    row["response"] = row["response"].replace('"patch": {', '"patch" {', 1)   # drop one colon
            return row

    value, panel = auth9(selection=8)
    api = MalformedAPI()
    result = run_stage(value, panel, tmp_path / "stage", fixture_api=api, fixture_evaluate=evaluate("korbench"))
    assert result["status"] == "completed" and result["accepted_steps"] == 1 and api.retry_prompts
    audits = sorted(p.name for p in (tmp_path / "stage/native/0/parser_audits").glob("*.json"))
    assert any(name.endswith("-retry1.json") for name in audits)
    first = json.loads((tmp_path / "stage/native/0/parser_audits/0.json").read_text())
    retry = json.loads((tmp_path / "stage/native/0/parser_audits/0-retry1.json").read_text())
    assert first["status"] == "rejected" and retry["status"] in {"strict", "repaired"} and retry["json_retry"] == 1
    # a second malformed reply leaves the stage pending, with the reason naming the retry
    pending = run_stage(value, panel, tmp_path / "bad", fixture_api=MalformedAPI(always_bad=True),
                        fixture_evaluate=evaluate("korbench"))
    assert pending["status"] == "pending" and pending["reason"] == "native_reflection_incomplete"
    bad_audits = sorted(p.name for p in (tmp_path / "bad/native/0/parser_audits").glob("*.json"))
    assert "0.json" in bad_audits and "0-retry1.json" in bad_audits
    # v8 keeps its frozen behavior: no retry, pending at the first malformed reply
    value8, panel8 = auth(selection=8)
    legacy = run_stage(value8, panel8, tmp_path / "v8", fixture_api=MalformedAPI(), fixture_evaluate=evaluate("korbench"))
    assert legacy["status"] == "pending" and not (tmp_path / "v8/native/0/parser_audits/0-retry1.json").exists()
