"""Offline native-shape fixtures; no downloaded code or model is executed."""

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v10.codec import encode_value
from skillopt.coevolution_v11 import assertions, data, executor
from skillopt.coevolution_v18 import runtime as r
from skillopt.validator_pilot.api import digest

GOOD = "def solve(x):\n    return x + 1\n"
BAD = "def solve(x):\n    return x - 1\n"
REFERENCE = GOOD + "# PRIVATE_REFERENCE_NEVER_PROJECT\n"
PROTO = "a" * 64


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def reseal(value):
    return seal({key: item for key, item in value.items() if key != "record_hash"})


def tree(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def forbid(*args, **kwargs):
    pytest.fail("Attempted API/execution/write on offline replay")


@pytest.fixture
def fx(tmp_path, monkeypatch):
    prompt = "Return one more than the input."
    compiled = assertions.compile_tests(["assert solve(9) == 10", "assert solve(-2) == -1"])
    coding = {"domain": "coding", "id": "601", "task_id": 601, "source_split": "train",
        "phase": "development", "split": "development", "prompt": prompt, "reference_code": REFERENCE,
        "compiled": compiled, "entry_point": compiled["entry_point"], "public_interface": compiled["public_interface"],
        "source_row_hash": "b" * 64, "question_sha256": data.question_fingerprint(prompt),
        "cluster_id": data.question_fingerprint(prompt)}
    qa_prompt = "What entity is requested?"
    qa_task = {"domain": "searchqa", "id": "qa-one", "phase": "development", "source_split": "train",
               "cluster_id": data.question_fingerprint(qa_prompt),
               "item": {"key": "qa-one", "question": qa_prompt, "context": "Public evidence only.",
                        "answers": ["PRIVATE_GOLD"]}}
    state = {"api_calls": 0, "child_calls": 0, "api_ok": True, "candidate": GOOD,
             "qa_response": "<answer>PRIVATE_GOLD</answer>", "raw_code": None,
             "reference_wrong": False, "candidate_status": "completed", "requests": []}

    def child(source, entry, cases):
        state["child_calls"] += 1
        reference = source == REFERENCE
        result = {"version": executor.VERSION, "runner_sha256": executor.RUNNER_SHA256,
                  "code_hash": r.text_hash(source), "status": "completed" if reference else state["candidate_status"],
                  "observations": [], "error_category": None}
        try:
            executor.validate_code(source)
            payload = executor._payload(source, entry, cases)
        except (ValueError, SyntaxError):
            result["status"] = "candidate_rejected"
            return result
        result["payload_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        if result["status"] == "completed":
            correct = source in (REFERENCE, GOOD) and not (reference and state["reference_wrong"])
            result["observations"] = [{"value": encode_value(x), "exception": None, "typed": True,
                                       "truthiness": bool(x)} for x in ([10, -1] if correct else [8, -3])]
        return result

    class API:
        model = "glm-5.3"
        service = {"fixture": True, "temperature": 0}
        root = tmp_path / "api"

        def call(self, system, user, kind, key, *, max_tokens, repeat):
            state["api_calls"] += 1
            request = {"model": self.model, "service": self.service, "system": system, "user": user,
                       "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
            state["requests"].append(request)
            response = (state["qa_response"] if "searchqa" in kind else
                        state["raw_code"] if state["raw_code"] is not None else "```python\n" + state["candidate"] + "```")
            receipt = {"request": request, "request_hash": digest(request), "ok": state["api_ok"],
                       "response": response if state["api_ok"] else "", "http_attempt_count": 1,
                       "finish_reason": "stop" if state["api_ok"] else None}
            put(self.root / "calls" / (digest(request) + ".json"), receipt)
            return receipt

    monkeypatch.setattr(executor, "run_cases", child)
    return SimpleNamespace(root=tmp_path, coding=coding, qa=qa_task, state=state, api=API())


def solve(fx, task=None, *, skill="", history=1, completed=False):
    return r.solve(fx.api, task or fx.coding, skill, history, fx.root, PROTO, completed=completed)


@pytest.mark.parametrize("domain", ["coding", "searchqa"])
def test_one_shot_native_score_and_public_only_messages(fx, domain):
    row = solve(fx, getattr(fx, "qa" if domain == "searchqa" else "coding"))
    assert row["hard"] == row["soft"] == 1 and row["category"] == "passed"
    assert row["history"] == row["request_repeat"] == 1
    assert row["phase"] == "development"
    assert fx.state["api_calls"] == 1
    assert fx.state["child_calls"] == (2 if domain == "coding" else 0)
    request = fx.state["requests"][0]
    assert request["repeat"] == 1 and request["max_tokens"] == 4096
    assert "PRIVATE_REFERENCE" not in request["system"] + request["user"]
    assert "PRIVATE_GOLD" not in request["system"] + request["user"]
    assert "assert solve" not in request["system"] + request["user"]


@pytest.mark.parametrize("domain", ["coding", "searchqa"])
def test_exact_alias_only_within_history(fx, domain):
    task = fx.coding if domain == "coding" else fx.qa
    first = solve(fx, task, skill="Same bytes", history=1)
    assert solve(fx, task, skill="Same bytes", history=1) == first
    second = solve(fx, task, skill="Same bytes", history=2)
    assert first["request_hash"] != second["request_hash"]
    assert fx.state["api_calls"] == 2
    assert [x["repeat"] for x in fx.state["requests"]] == [1, 2]
    assert fx.state["child_calls"] == (3 if domain == "coding" else 0)


@pytest.mark.parametrize("domain", ["coding", "searchqa"])
def test_completed_replay_is_exact_without_io_side_effect(fx, monkeypatch, domain):
    task = fx.coding if domain == "coding" else fx.qa
    row = solve(fx, task)
    before = tree(fx.root)
    monkeypatch.setattr(fx.api, "call", forbid)
    monkeypatch.setattr(executor, "run_cases", forbid)
    monkeypatch.setattr(r, "write_immutable_json", forbid)
    assert solve(fx, task, completed=True) == row
    assert solve(fx, task) == row
    assert tree(fx.root) == before


def test_closed_receipts_reconstruct_missing_solve_without_resampling(fx, monkeypatch):
    row = solve(fx)
    next((fx.root / "runtime/solves").glob("*.json")).unlink()
    monkeypatch.setattr(fx.api, "call", forbid)
    monkeypatch.setattr(executor, "run_cases", forbid)
    assert solve(fx) == row


def test_unclosed_api_intent_is_never_resent(fx, monkeypatch):
    def interrupted(*args, **kwargs):
        assert len(list((fx.root / "runtime/api_intents").glob("*.json"))) == 1
        raise OSError("synthetic interrupted request")
    monkeypatch.setattr(fx.api, "call", interrupted)
    with pytest.raises(OSError):
        solve(fx, fx.qa)
    monkeypatch.setattr(fx.api, "call", forbid)
    with pytest.raises(ValueError, match="unresolved"):
        solve(fx, fx.qa)


@pytest.mark.parametrize("part", ["runtime/references", "runtime/solves", "runtime/api_intents", "api/calls", "runtime/executions", "runtime/execution_intents"])
def test_missing_completed_dependency_never_repaired(fx, monkeypatch, part):
    solve(fx)
    next((fx.root / part).glob("*.json")).unlink()
    before = tree(fx.root)
    monkeypatch.setattr(fx.api, "call", forbid)
    monkeypatch.setattr(executor, "run_cases", forbid)
    with pytest.raises(ValueError):
        solve(fx, completed=True)
    assert tree(fx.root) == before


@pytest.mark.parametrize("domain", ["coding", "searchqa"])
def test_api_unknown_is_retained_not_semantic_failure(fx, domain):
    fx.state["api_ok"] = False
    row = solve(fx, fx.coding if domain == "coding" else fx.qa)
    assert row["hard"] is row["soft"] is None
    assert row["category"] == "api_unknown" and row["oracle_available"] is False
    assert r.development_feedback(fx.coding if domain == "coding" else fx.qa, row, fx.root)["hard"] is None


def test_unavailable_reference_retains_unknown_and_does_not_replace_task(fx):
    fx.state["reference_wrong"] = True
    row = solve(fx)
    assert row["category"] == "reference_unavailable" and row["hard"] is None
    assert fx.state["api_calls"] == 1 and fx.state["child_calls"] == 1
    assert row["task_id"] == fx.coding["id"]
    assert r.development_feedback(fx.coding, row, fx.root)["category"] == "reference_unavailable"


def test_semantic_vs_delivery_vs_execution_failures(fx):
    fx.state["candidate"] = BAD
    row = solve(fx, skill="semantic")
    assert row["category"] == "assertion_failure" and row["hard"] == 0
    feedback = r.development_feedback(fx.coding, row, fx.root)
    assert len(feedback["executed_native_checks"]) == 2
    assert "PRIVATE_REFERENCE" not in json.dumps(feedback)
    fx.state["raw_code"] = "def solve(:"
    row = solve(fx, skill="delivery")
    assert row["category"] == "artifact_contract_violation" and row["hard"] == 0
    assert "executed_native_checks" not in r.development_feedback(fx.coding, row, fx.root)
    fx.state.update(raw_code=None, candidate=GOOD, candidate_status="infrastructure_unknown")
    row = solve(fx, skill="execution")
    assert row["category"] == "infrastructure_unknown" and row["hard"] is None


def test_qa_feedback_gold_only_in_development(fx):
    feedback = r.development_feedback(fx.qa, solve(fx, fx.qa), fx.root)
    assert feedback["development_answers"] == ["PRIVATE_GOLD"]
    final = {**fx.qa, "phase": "final", "source_split": "validation"}
    row = solve(fx, final)
    assert row["optimizer_feedback_allowed"] is False
    with pytest.raises(ValueError, match="genuine development"):
        r.development_feedback(final, row, fx.root)
    with pytest.raises(ValueError):
        r.development_feedback(fx.qa, row, fx.root)


def test_confirmation_and_final_stay_actual_phase(fx):
    for phase in ("confirmation", "final"):
        task = {**fx.coding, "phase": phase, "split": phase}
        if phase == "final":
            task.update(task_id=101, id="101", source_split="test")
        row = solve(fx, task)
        assert row["identity"]["phase"] == phase
        assert row["reference_record"]["identity"]["phase"] == phase
        with pytest.raises(ValueError):
            r.development_feedback(task, row, fx.root)


@pytest.mark.parametrize("domain", ["coding", "searchqa"])
def test_feedback_rescores_instead_of_trusting_resealed_score(fx, domain):
    task = fx.coding if domain == "coding" else fx.qa
    row = solve(fx, task)
    changed = deepcopy(row)
    changed["hard"] = 0
    with pytest.raises(ValueError, match="on-disk"):
        r.development_feedback(task, reseal(changed), fx.root)


def test_row_and_reference_tampering_fail_replay(fx):
    row = solve(fx)
    changed = {**row, "hard": 0}
    put(fx.root / "runtime/solves" / (row["request_hash"] + ".json"), reseal(changed))
    with pytest.raises(ValueError, match="recomputed"):
        solve(fx, completed=True)


def test_phase_source_and_request_schema_fail_closed(fx):
    with pytest.raises(ValueError):
        solve(fx, {**fx.qa, "phase": "final"})
    with pytest.raises(ValueError):
        solve(fx, {**fx.coding, "phase": "calibration"})
    with pytest.raises(ValueError):
        solve(fx, history=True)
    with pytest.raises(ValueError):
        solve(fx, {**fx.coding, "cluster_id": "d" * 64})


def test_api_receipt_requires_complete_finish(fx):
    row = solve(fx, fx.qa)
    path = fx.root / "api/calls" / (row["request_hash"] + ".json")
    receipt = json.loads(path.read_text())
    receipt["finish_reason"] = "length"
    put(path, receipt)
    with pytest.raises(ValueError, match="complete request"):
        solve(fx, fx.qa, completed=True)


def test_development_feedback_exposes_only_actual_truncated_qa_context(fx):
    task = deepcopy(fx.qa)
    task["item"]["context"] = "x" * 6500 + "UNSEEN_SUFFIX"
    row = solve(fx, task)
    feedback = r.development_feedback(task, row, fx.root)
    public = feedback["public_task"]
    assert public["context_truncated_at_source"] is True
    assert public["native_user_message"] == fx.state["requests"][-1]["user"]
    assert "UNSEEN_SUFFIX" not in json.dumps(feedback)


def test_development_feedback_checks_disk_and_rescores_resealed_disk_score(fx):
    row = solve(fx)
    changed = reseal({**row, "hard": 0})
    put(fx.root / "runtime/solves" / (row["request_hash"] + ".json"), changed)
    with pytest.raises(ValueError, match="score differs"):
        r.development_feedback(fx.coding, changed, fx.root)


@pytest.mark.parametrize("part", ["runtime/api_intents", "api/calls", "runtime/executions"])
def test_feedback_requires_closed_disk_dependencies_without_reexecution(fx, monkeypatch, part):
    row = solve(fx)
    next((fx.root / part).glob("*.json")).unlink()
    monkeypatch.setattr(fx.api, "call", forbid)
    monkeypatch.setattr(executor, "run_cases", forbid)
    with pytest.raises(ValueError):
        r.development_feedback(fx.coding, row, fx.root)


def test_parallel_histories_share_reference_but_not_solver_draws(fx):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(lambda h: solve(fx, history=h), [1, 2]))
    assert len({row["request_hash"] for row in records}) == 2
    assert fx.state["api_calls"] == 2 and fx.state["child_calls"] == 3
