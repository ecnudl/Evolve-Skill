"""Offline two-round integration with real sandbox and immutable fake receipts.

Fake responses intentionally know a toy solution to exercise wiring. Scores in
these tests are deterministic control outcomes, never experimental efficacy.
"""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from skillopt.coevolution.budget import BudgetedAPI
from skillopt.coevolution_v3.executor import RepoTask
from skillopt.coevolution_v5 import core, evaluation
from skillopt.coevolution_v5 import experiment as e
from skillopt.coevolution_v5.adapters import CodingAdapter, QAAdapter
from skillopt.validator_pilot.api import digest, write_immutable_json


def coding(index, split):
    def source(body):
        return f"# project {index}\ndef double(data):\n" + body

    files = {"api.py": "import calculation\ndef solve(data):\n    return calculation.double(data)\n",
             "calculation.py": source("    return data['x']\n"), "support.py": f"PROJECT = {index}\n"}
    reference = {**files, "calculation.py": source("    return data['x'] * 2\n")}
    equivalent = {**files, "calculation.py": source("    value = data['x']\n    return value + value\n")}
    bad_preservation = {**files, "calculation.py": source("    data['touched'] = True\n    return data['x'] * 2\n")}
    return CodingAdapter(RepoTask(
        id=f"integration-coding-{index}", split=split, family="doubling", cluster_id=f"independent-project-{index}",
        prompt="Return twice x without changing the input object; no filesystem or external effects.",
        files=files, reference_files=reference, editable_paths=["calculation.py"],
        input_domain={"type": "object", "properties": {"x": {"type": "integer"}},
                      "required": ["x"], "additionalProperties": False},
        public_cases=[{"label": "public", "input": {"x": 2}, "expected": 4, "exception": None,
                       "public": True, "dimension": "requested_behavior"}],
        private_cases=[{"label": f"private-{index}", "input": {"x": 617}, "expected": 1234, "exception": None,
                        "public": False, "dimension": "preserved_behavior"}],
        metadata={"controls": {"equivalent": equivalent, "semantic_mutant": files,
                               "preservation_mutant": bad_preservation}},
    ))


def qa(index, split):
    return QAAdapter({"id": f"integration-qa-{index}", "cluster_id": f"qa-project-{index}",
                      "question": f"What is the marked token for item {index}?",
                      "contexts": [f"The marked token for item {index} is TOKEN{index}."],
                      "answers": [f"TOKEN{index}"], "split": split})


def panel():
    first, second = [coding(i, "learn0") for i in (0, 1)], [coding(i, "learn1") for i in (2, 3)]
    scope = [qa(i, "development") for i in (0, 1)]
    return {"source": [first, second], "scope": [scope[:1], scope],
            "promotion": [coding(i, "promotion") for i in (4, 5)],
            "final": [coding(6, "final"), qa(7, "final")]}


class FakeTransport:
    model = "glm-5.3"
    service = {"max_retries": 2, "fake_transport": "offline-integration"}
    response_hook = None

    def __init__(self, root, calls, tasks):
        self.root, self.calls, self.tasks = Path(root), calls, tasks

    def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
        request = {"model": self.model, "service": self.service, "system": system, "user": user,
                   "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
        identifier = digest(request)
        path = self.root / "calls" / f"{identifier}.json"
        if path.exists():
            return json.loads(path.read_text())
        payload = json.loads(user)
        if kind == "v5_coding_generate":
            task = self.tasks[payload["task"]["id"]].task
            files = task.reference_files if payload["skill"] else task.files
            response = "<<<FILE calculation.py>>>\n" + files["calculation.py"]
        elif kind in {"v5_coding_revision", "v5_qa_revision"}:
            response = "KEEP"
        elif kind == "v5_qa_generate":
            task = self.tasks[payload["task"]["id"]].task
            response = json.dumps({"answer": task["answers"][0], "citations": [
                {"context_id": 0, "quote": task["contexts"][0]}]})
        elif kind == "v5_skill":
            response = ("Preserve task constraints before editing. Check changed dependency paths, explicit input "
                        "preservation obligations, and old behavior. Use the task contract as authority, verify "
                        "outputs with concrete checks, and abstain when this procedural guidance does not apply.")
        elif kind == "v5_validator_probe":
            response = json.dumps({"inputs": [{"x": 3}]})
        elif kind == "v5_rubric_plan":
            external = "urls must be []" not in system
            response = json.dumps({"explanations": [
                {"hypothesis": "Boundary coverage may be missing.", "check": "Check an independent input."},
                {"hypothesis": "The existing contract may already cover the case.", "check": "Compare its scope."}],
                "questions": [{"topic": "mapping semantics", "question": "How does shared state preserve constraints?"}],
                "urls": ["https://docs.python.org/3/library/stdtypes.html"] if external else []})
        elif kind == "v5_rubric_synthesis":
            response = json.dumps({"findings": [], "limits": ["Offline control; no external evidence was obtained."]})
        elif kind == "v5_rubric_patch":
            response = json.dumps({"changes": [{"check_id": "coding_probe", "search": "Check one independent nonzero input and input mutation.",
                                                 "when": "Apply only under the stated input preservation contract.",
                                                 "limits": "A finite input check is not a general safety proof."}],
                                   "rationale": "Exercise operational checking without changing obligations.", "source_refs": []})
        elif kind == "v5_feedback_repair":
            task = self.tasks[payload["task"]["id"]].task
            response = "<<<FILE calculation.py>>>\n" + task.reference_files["calculation.py"]
        else:
            raise AssertionError(f"Unexpected model call {kind}")
        hook = type(self).response_hook
        if hook is not None:
            response = hook(request, response)
        receipt = {"request": request, "request_hash": identifier, "ok": response is not None, "response": response or "",
                   "http_attempt_count": 1, "usage": {"prompt_tokens": 9, "completion_tokens": 8, "total_tokens": 17},
                   "finish_reason": "stop", "returned_model": "glm-5.3"}
        write_immutable_json(path, receipt)
        self.calls.append(receipt)
        return receipt

    def close(self):
        return None

    def parallel(self, jobs, fn, label):
        return [fn(job) for job in jobs]


def setup_study(tmp_path, monkeypatch):
    tasks = panel()
    all_adapters = [a for groups in (tasks["source"], tasks["scope"]) for group in groups for a in group]
    all_adapters += tasks["promotion"] + tasks["final"]
    indexed = {e.task_id(a): a for a in all_adapters}
    source = {"hash": digest("frozen-test-source")}
    monkeypatch.setattr(e.Study, "_sources", lambda self: {"test_source": source["hash"]})

    def no_network(*args, **kwargs):
        raise OSError("offline test: documentation transport is unavailable")

    monkeypatch.setattr(e.research, "fetch_sources", no_network)
    calls = []

    def factory(repo, root, *, max_calls, workers):
        return BudgetedAPI(repo, root, max_calls, workers, api=FakeTransport(root, calls, indexed))

    study = e.Study(tmp_path, tmp_path / "outputs/coevolution_v5/unit", panel=tasks)
    return study, factory, calls, source


@pytest.fixture(scope="module")
def completed(tmp_path_factory):
    with pytest.MonkeyPatch.context() as monkeypatch:
        study, factory, calls, source = setup_study(tmp_path_factory.mktemp("v5-integration"), monkeypatch)
        result = study.run(api_factory=factory)
        yield study, factory, calls, source, result


def test_full_two_round_flow_seals_final_and_calibration(completed):
    study, _, calls, _, result = completed
    assert result["status"] == "complete" and result["engineering_only"]
    assert result["cross_domain_efficacy_established"] is False and result["final_feedback_used"] is False
    assert len(result["decisions"]) == 6
    assert {d["round"] for d in result["decisions"]} == {0, 1}
    assert result["ledger"]["unresolved_reservations"] == []
    assert result["ledger"]["cached_logical_calls"] == len(calls)
    assert (study.root / "final_frozen.json").exists()
    assert (study.root / "states/r0.json").exists() and (study.root / "states/r1.json").exists()
    assert len(list((study.root / "calibration").glob("*/r0/consumed.json"))) == 2
    for path in (study.root / "calibration").glob("*/r0/consumed.json"):
        value = json.loads(path.read_text())
        assert value["raw_labels_returned"] is False
        assert value["active_from_round"] is None  # Identical probe quality, no strict improvement.
    for path in (study.root / "calibration").glob("*/r0/private_manifest.json"):
        assert json.loads(path.read_text())["current_rubric_hash"] == core.initial_rubric()["rubric_hash"]
    preflight = e.read(study.root / "private_control_preflight.json")
    assert len(preflight["records"]) == 8 and preflight["never_model_feedback"] is True
    assert all(row["assessment"]["phase"] == "promotion" for row in preflight["records"])


def test_final_never_enters_optimizer_or_research_feedback(completed):
    study, _, calls, _, _ = completed
    forbidden_ids = [e.task_id(a) for a in study.panel["final"]]
    for call in calls:
        request = call["request"]
        if request["kind"] == "v5_skill" or request["kind"].startswith("v5_rubric_"):
            assert all(identifier not in request["user"] for identifier in forbidden_ids)
            assert "TOKEN7" not in request["user"]
            assert '"truth"' not in request["user"]
            assert '"promotion_result"' not in request["user"]
        if request["kind"].startswith("v5_rubric_"):
            assert "TOKEN0" not in request["user"] and "TOKEN1" not in request["user"]
    frozen = e.read(study.root / "final_frozen.json")
    for branch in frozen["states"].values():
        assert all(p["phase"] == "development" for p in branch["feedback"])
        assert all(p["task_id"] not in forbidden_ids for p in branch["feedback"])


def test_final_no_skill_and_fallback_policies_share_identical_requests(completed):
    study, _, _, _, _ = completed
    rows = e.read(study.root / "final_rows.json")["rows"]
    for adapter in study.panel["final"]:
        group = [row for row in rows if row["task_id"] == e.task_id(adapter)]
        assert len(group) == 7
        baseline = next(row for row in group if row["policy"] == "no_skill")
        for name in ("fixed", "feedback", "research"):
            policy = next(row for row in group if row["policy"] == name)
            assert policy["fallback"] is True
            assert policy["request_hashes"] == baseline["request_hashes"]
            assert policy["score"] == baseline["score"]


def test_human_queue_generated_but_reviews_not_invented(completed):
    study, _, _, _, result = completed
    queue = json.loads((study.root / "human_review/queue.json").read_text())
    assert queue["entries"] and queue["review_performed"] is False
    assert result["human_review"] == "queue_exported_not_yet_performed"
    assert (study.root / "human_review/queue.json.private.json").exists()
    assert not (study.root / "human_review/reviews.json").exists()


def test_completed_resume_uses_no_api_factory(completed):
    study, _, calls, _, expected = completed

    def forbidden(*args, **kwargs):
        pytest.fail("Completed resume tried to open API")

    resumed = e.Study(study.repo, study.root, panel=study.panel)
    before = len(calls)
    assert resumed.run(api_factory=forbidden) == expected
    assert len(calls) == before


def test_frozen_source_mutation_rejected_before_api(tmp_path, monkeypatch):
    study, _, calls, source = setup_study(tmp_path, monkeypatch)
    study.prepare()
    source["hash"] = digest("changed-test-source")
    with pytest.raises(ValueError, match="Frozen"):
        study.verify()
    assert calls == []


def test_frozen_task_mutation_rejected_before_api(tmp_path, monkeypatch):
    study, _, calls, _ = setup_study(tmp_path, monkeypatch)
    study.prepare()
    task = study.panel["source"][0][0].task
    study.panel["source"][0][0] = CodingAdapter(replace(task, prompt="Modified task contract."))
    with pytest.raises(ValueError, match="Frozen"):
        study.verify()
    assert calls == []


def test_panel_overlap_and_duplicate_controls_rejected_without_api(tmp_path, monkeypatch):
    study, _, calls, _ = setup_study(tmp_path, monkeypatch)
    task = study.panel["final"][0].task
    study.panel["final"][0] = CodingAdapter(replace(task, cluster_id=e.cluster(study.panel["source"][0][0])))
    with pytest.raises(ValueError, match="overlap"):
        study.prepare()
    assert calls == []
    study.panel = panel()
    task = study.panel["promotion"][0].task
    metadata = deepcopy(task.metadata)
    metadata["controls"]["equivalent"] = task.reference_files
    study.panel["promotion"][0] = CodingAdapter(replace(task, metadata=metadata))
    with pytest.raises(ValueError, match="Duplicate"):
        study.prepare()


def test_safe_checkpoint_resume_reuses_persisted_solver_calls(tmp_path, monkeypatch):
    study, factory, calls, _ = setup_study(tmp_path, monkeypatch)
    original = study._solve
    counter = {"calls": 0}

    def checkpoint(*args, **kwargs):
        row = original(*args, **kwargs)
        counter["calls"] += 1
        if counter["calls"] == 2:
            raise InterruptedError("test pause after outer result and API receipts persisted")
        return row

    monkeypatch.setattr(study, "_solve", checkpoint)
    with pytest.raises(InterruptedError):
        study.run(api_factory=factory)
    before = {row["request_hash"] for row in calls}
    assert before and not (study.root / "results.json").exists()
    resumed = e.Study(study.repo, study.root, panel=study.panel)
    result = resumed.run(api_factory=factory)
    assert result["status"] == "complete"
    hashes = [row["request_hash"] for row in calls]
    assert len(hashes) == len(set(hashes)) and before <= set(hashes)
    assert result["ledger"]["unresolved_reservations"] == []


def test_scope_skill_receipts_are_bound_to_actual_intervention(completed):
    study, _, _, _, _ = completed
    for path in (study.root / "decisions").glob("*.json"):
        decision = e.read(path)
        candidate_hash = digest(e.text(decision["candidate"]))
        for group in decision["pairs"].values():
            for pair in group:
                assert pair["skill_hashes"]["candidate"] == candidate_hash
                for arm in ("baseline", "current", "candidate"):
                    for row in pair[arm]:
                        core.verify(row, "receipt_hash")
                        assert row["details"]["solver_skill_hash"] == pair["skill_hashes"][arm]


def test_candidate_feedback_has_paired_interventions_not_just_a_score(completed):
    study, _, _, _, _ = completed
    frozen = e.read(study.root / "final_frozen.json")
    for branch in frozen["states"].values():
        assert branch["feedback"]
        for packet in branch["feedback"]:
            assert packet["comparisons"]
            for comparison in packet["comparisons"]:
                assert set(comparison["arms"]) == {"baseline", "current", "candidate"}
                assert comparison["interpretation"] == "paired_observation_not_proven_causation"
                for arm in comparison["arms"].values():
                    assert len(arm["artifact_hash"]) == len(arm["receipt_hash"]) == len(arm["skill_hash"]) == 64


def test_mislabelled_unique_control_rejected_before_api_opens(tmp_path, monkeypatch):
    study, _, calls, _ = setup_study(tmp_path, monkeypatch)
    adapter = study.panel["promotion"][0]
    metadata = deepcopy(adapter.task.metadata)
    # Valid but misleading label, not merely a duplicate hash: this "bad" file
    # computes the correct behavior and preserves the input.
    metadata["controls"]["semantic_mutant"] = {
        **adapter.task.reference_files,
        "calculation.py": adapter.task.reference_files["calculation.py"] + "\n# distinct but still correct\n",
    }
    study.panel["promotion"][0] = CodingAdapter(replace(adapter.task, metadata=metadata))

    def forbidden(*args, **kwargs):
        pytest.fail("API opened before calibration truth preflight")

    with pytest.raises(ValueError, match="control truth"):
        study.run(api_factory=forbidden)
    assert calls == []


def test_all_invalid_skill_proposals_keep_accurate_review_queue_state(tmp_path, monkeypatch):
    study, factory, _, _ = setup_study(tmp_path, monkeypatch)
    monkeypatch.setattr(FakeTransport, "response_hook", lambda request, response:
                        "" if request["kind"] == "v5_skill" else response)
    result = study.run(api_factory=factory)
    assert all(row["action"] == "Restrict" for row in result["decisions"])
    path = study.root / "human_review/queue.json"
    if path.exists():
        assert result["human_review"] == "queue_exported_not_yet_performed"
        assert json.loads(path.read_text())["review_performed"] is False
    else:
        assert result["human_review"] == "no_feedback_to_review"
    frozen = e.read(study.root / "final_frozen.json")
    assert all(branch["skill"]["approved"] == "" for branch in frozen["states"].values())


def test_existing_approved_scope_is_revoked_from_its_own_replayed_harm(tmp_path, monkeypatch):
    study, factory, _, _ = setup_study(tmp_path, monkeypatch)
    scope_calls = {"with_skill": 0}

    def regress_scope(request, response):
        payload = json.loads(request["user"])
        if (request["kind"] == "v5_qa_generate" and payload["task"]["id"] == "integration-qa-0"
                and payload["skill"]):
            scope_calls["with_skill"] += 1
            if scope_calls["with_skill"] >= 2:
                return json.dumps({"answer": "WRONG", "citations": []})
        return response

    monkeypatch.setattr(FakeTransport, "response_hook", regress_scope)
    study.run(api_factory=factory)
    for name in e.POLICIES:
        row = e.read(study.root / f"decisions/h0-{name}-r1.json")
        prior, revalidated = row["before"], row["after_scope_revalidation"]
        assert prior["approved"] and not prior["revoked_scopes"]
        revoked = revalidated["revoked_scopes"]
        assert revoked and revoked[-1]["domain"] == "qa"
        assert revoked[-1]["approved_hash"] == digest(e.text(prior["approved"]))
        assert e.governance.eligible_skill(row["after"], "qa", cluster_id="qa-project-0")["fallback"] is True


def test_final_unavailable_execution_separates_coverage_from_native_score(tmp_path, monkeypatch):
    study, factory, _, _ = setup_study(tmp_path, monkeypatch)

    def unavailable_final_revision(request, response):
        payload = json.loads(request["user"])
        if request["kind"] == "v5_coding_revision" and payload["task"]["id"] == "integration-coding-6":
            return None
        return response

    monkeypatch.setattr(FakeTransport, "response_hook", unavailable_final_revision)
    result = study.run(api_factory=factory)
    native = result["final"]["by_policy"]["no_skill"]["coding"]
    assert native["available_score_mean"] is None
    assert native["all_attempt_yield_mean"] == 0
    assert native["unknown"] == 1 and native["available_coverage"] == 0
    assert "transport_unavailable" in native["errors"]
    macro = result["final"]["macro"]["no_skill"]
    assert macro["domains_available"] == 1 and macro["domains_total"] == 2
    assert macro["available_score_mean"] == 1 and macro["all_attempt_yield_mean"] == 0.5


def test_repair_diagnostic_uses_the_same_promoted_rubric_as_its_feedback(tmp_path, monkeypatch):
    study, factory, _, _ = setup_study(tmp_path, monkeypatch)
    # Private-only controlled defects make a changed probe objectively improve
    # calibration. This is deliberately deterministic test wiring, not a model
    # learning or benchmark claim.
    for index, adapter in enumerate(study.panel["promotion"]):
        task = adapter.task
        metadata = deepcopy(task.metadata)
        prefix = f"# private-only controlled project {index}\ndef double(data):\n"
        metadata["controls"]["semantic_mutant"] = {
            **task.files, "calculation.py": prefix + "    return data['x'] if data['x'] == 617 else data['x'] * 2\n"}
        metadata["controls"]["preservation_mutant"] = {
            **task.files, "calculation.py": prefix + "    if data['x'] == 617:\n        data['changed'] = True\n    return data['x'] * 2\n"}
        study.panel["promotion"][index] = CodingAdapter(replace(task, metadata=metadata))
    initial_hash = core.initial_rubric()["rubric_hash"]

    def specific_control_response(request, response):
        payload = json.loads(request["user"])
        if request["kind"] == "v5_validator_probe" and payload["rubric"]["revision"] > 0:
            return json.dumps({"inputs": [{"x": 617}]})
        if request["kind"] == "v5_skill" and any(
            p["rubric_hash"] != initial_hash for p in payload["development_evidence"]
        ):
            return response + " REVISED_VALIDATOR_BRANCH"
        if request["kind"] == "v5_coding_generate" and "REVISED_VALIDATOR_BRANCH" in payload["skill"]:
            return "<<<FILE calculation.py>>>\ndef double(data):\n    return data['x']\n"
        return response

    monkeypatch.setattr(FakeTransport, "response_hook", specific_control_response)
    original = evaluation.repair_feedback_comparison
    inspected = []

    def checked(api, adapter, artifact, packet, rubric, root, *, key):
        assert rubric["rubric_hash"] == packet["rubric_hash"]
        inspected.append(rubric["revision"])
        return original(api, adapter, artifact, packet, rubric, root, key=key)

    monkeypatch.setattr(evaluation, "repair_feedback_comparison", checked)
    result = study.run(api_factory=factory)
    assert inspected == [1]
    assert len(result["feedback_utility"]) == 1
    states = e.read(study.root / "states/r1.json")
    assert states["h0-feedback"]["rubric"]["revision"] == states["h0-research"]["rubric"]["revision"] == 1
    assert states["h0-fixed"]["rubric"]["revision"] == 0
