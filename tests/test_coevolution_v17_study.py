"""Offline V17 integration: authentic receipts, mocked Coding execution only."""

import hashlib
import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v15 import runtime, tasks
from skillopt.coevolution_v17 import core, study
from skillopt.validator_pilot.api import digest
from tests.test_coevolution_v12_study import forbidden, put, tree
from tests.test_coevolution_v15_study import FakeAPI as LegacyFakeAPI
from tests.test_coevolution_v15_study import setup as legacy_setup  # noqa: F401


class FakeAPI(LegacyFakeAPI):
    """Keep V17 request bytes unchanged and publish its actual cache receipts."""

    def call(self, **arguments):
        if arguments["kind"] != "v17_skill_update":
            return super().call(**arguments)
        with self.state["lock"]:
            request = {**arguments, "model": self.model, "service": self.service}
            identifier = digest(request)
            path = self.root / "calls" / (identifier + ".json")
            if path.exists():
                return json.loads(path.read_text())
            value = json.loads(arguments["user"])
            mode = value["development_feedback"]["mode"]
            response = ("## When\nWhen the declared task constraints apply.\n"
                        "## Procedure\nVerify affected outputs. Evidence arrangement: " + mode + ".\n"
                        "## Avoid\nInventing or preserving superseded constraints.")
            if self.state.get("invalid_skill"):
                response = "Invalid Skill output"
            receipt = {"request": request, "request_hash": identifier, "ok": True,
                       "response": response, "http_attempt_count": 1, "finish_reason": "stop",
                       "usage": {"total_tokens": 2}}
            put(self.root / "budget_reservations" / (identifier + ".json"),
                {"request_hash": identifier, "kind": arguments["kind"]})
            put(path, receipt)
            self.state["calls"] += 1
            self.state["receipts"].append(receipt)
            if (self.state.get("pause_at") == self.state["calls"]
                    or self.state.pop("pause_on_update", False)):
                (self.root.parent / "PAUSE").touch()
            return receipt


def fixture_panel():
    """Only existing local authored structures; no production V17/final access."""
    panel = {
        "source": [tasks._coding(tasks.CODING_DEV[0], "development")],
        "source_extra": [tasks._coding(tasks.CODING_DEV[1], "development")],
        "transfer": [tasks._sheet(tasks.SHEET_DEV[0], "development")],
        "confirmation": [tasks._coding(f, "calibration") for f in tasks.CODING_CAL[:2]]
            + [tasks._sheet(f, "calibration") for f in tasks.SHEET_CAL[:2]],
        "final": [tasks._coding(tasks.SMOKE_CODING[2], "final"),
                  tasks._sheet(tasks.SMOKE_SHEET[2], "final"), tasks._rule(tasks.SMOKE_RULE)],
    }
    for partition, adapters in panel.items():
        for i, adapter in enumerate(adapters):
            task = adapter.task.metadata if isinstance(adapter, CodingAdapter) else adapter.task["metadata"]
            task["mechanism_cell"] = "near_miss" if partition == "confirmation" and i % 2 else "same_mechanism"
    return panel


@pytest.fixture
def setup(request, monkeypatch):
    old_root, state, _ = request.getfixturevalue("legacy_setup")
    repo = old_root.parents[2]
    source = repo / "fixture.txt"
    monkeypatch.setattr(study, "source_hashes", lambda root:
        {"fixture.txt": hashlib.sha256(source.read_bytes()).hexdigest()})
    monkeypatch.setattr(study.tasks, "build_panel", forbidden)
    monkeypatch.setattr(study.tasks, "self_check", forbidden)
    root = repo / "outputs/coevolution_v17/test"
    panel = fixture_panel()
    state["tasks"].update({tasks.payload(a)["id"]: a for group in panel.values() for a in group})

    def build(design="smoke"):
        return study.Study(repo, root, design=design, panel=deepcopy(panel),
            api_factory=lambda repo, api_root, max_calls, workers: FakeAPI(api_root, max_calls, state))

    return root, state, build


def test_smoke_completes_with_closed_receipts_and_frozen_final(setup):
    root, state, build = setup
    result = build().run()
    assert result["complete"] is True and result["status"] == "completed"
    assert result["learning"] == {"positions": 4, "valid": 4}
    assert result["evidence_closure"]["all_api_receipts_accounted"] is True
    assert result["ledger"]["cached_logical_calls"] == state["calls"] <= 128
    assert len(study.read(root / "final_rows.json")["rows"]) == 3 * len(study.POLICIES)
    assert study.read(root / "final_frozen.json")["no_more_learning"] is True
    assert len(result["gates"]) == 3
    assert all(item["verdict"]["deployment_mapping"]["rule_reasoning"] == "no_skill"
               for item in result["gates"])


def test_completed_replay_has_no_calls_execution_or_byte_changes(setup, monkeypatch):
    root, state, build = setup
    expected = build().run()
    before, calls, executions = tree(root), state["calls"], state["executions"]
    monkeypatch.setattr(runtime.legacy, "evaluate", forbidden)
    monkeypatch.setattr(study.OfflineAPI, "call", forbidden)
    runner = build()
    runner.api_factory = forbidden
    assert runner.run() == expected
    assert tree(root) == before
    assert state["calls"] == calls and state["executions"] == executions


def test_pause_resume_preserves_completed_requests(setup):
    root, state, build = setup
    state["pause_at"] = 1
    with pytest.raises(study.PauseRequested):
        build().run()
    before = {p.name: p.read_bytes() for p in (root / "api/calls").glob("*.json")}
    assert before and not (root / "results.json").exists()
    (root / "PAUSE").unlink()
    assert build().run()["complete"] is True
    assert all((root / "api/calls" / name).read_bytes() == value for name, value in before.items())
    assert state["calls"] == len(list((root / "api/calls").glob("*.json")))


def test_pause_during_parent_update_reuses_durable_learning_request(setup):
    root, state, build = setup
    state["pause_on_update"] = True
    with pytest.raises(study.PauseRequested):
        build().run()
    updates = [r for r in state["receipts"] if r["request"]["kind"] == "v17_skill_update"]
    assert len(updates) == 1
    parent = study.read(root / "learning/h0-parent.json")
    before = (root / "api/calls" / (parent["request_hash"] + ".json")).read_bytes()
    (root / "PAUSE").unlink()
    assert build().run()["complete"] is True
    assert (root / "api/calls" / (parent["request_hash"] + ".json")).read_bytes() == before
    assert sum(r["request_hash"] == parent["request_hash"] for r in state["receipts"]) == 1


def test_failed_headroom_stops_before_learning_confirmation_or_final(setup, monkeypatch):
    root, state, build = setup
    screen = study.screen_summary

    def stop(rows, *, smoke=False):
        return {**screen(rows, smoke=smoke), "continue": False,
                "scientific_threshold_met": False, "reason": "fixture_insufficient_headroom"}

    monkeypatch.setattr(study, "screen_summary", stop)
    runner = build()
    expected_ids = {tasks.payload(a)["id"] for key in ("source", "transfer") for a in runner.panel[key]}
    result = runner.run()
    assert result["status"] == "screen_stopped" and result["complete"] is True
    assert result["learning"] == {"positions": 0, "valid": 0}
    assert not (root / "final_rows.json").exists() and not (root / "final_frozen.json").exists()
    assert not (root / "confirmation_rows.json").exists()
    assert all(r["request"]["kind"] != "v17_skill_update" for r in state["receipts"])
    assert {json.loads(r["request"]["user"])["task"]["id"] for r in state["receipts"]} == expected_ids
    before, count = tree(root), state["calls"]
    monkeypatch.setattr(runtime.legacy, "evaluate", forbidden)
    replay = build()
    replay.api_factory = forbidden
    assert replay.run() == result and tree(root) == before and state["calls"] == count


def test_three_candidates_share_parent_and_cross_views_have_identical_facts(setup):
    root, state, build = setup
    build().run()
    updates = {arm: study.read(root / "learning" / f"h0-{arm}.json") for arm in study.ARMS}
    parent = study.read(root / "learning/h0-parent.json")
    assert {row["parent_hash"] for row in updates.values()} == {parent["skill_hash"]}
    raw, structured = updates["cross_raw_feedback"], updates["cross_structured_feedback"]
    assert raw["factual_evidence_hash"] == structured["factual_evidence_hash"]
    assert raw["feedback_hash"] != structured["feedback_hash"]
    assert raw["request_hash"] != structured["request_hash"]
    requests = {r["request_hash"]: json.loads(r["request"]["user"]) for r in state["receipts"]
                if r["request"]["kind"] == "v17_skill_update"}
    raw_facts = core.flatten_feedback(requests[raw["request_hash"]]["development_feedback"])
    structured_facts = core.flatten_feedback(requests[structured["request_hash"]]["development_feedback"])
    local_facts = core.flatten_feedback(requests[updates["local_feedback"]["request_hash"]]["development_feedback"])
    assert raw_facts == structured_facts and raw_facts != local_facts
    assert len(raw_facts) == len(local_facts)
    assert {fact["role"] for fact in raw_facts} == {"no_skill", "current"}
    assert requests[raw["request_hash"]]["parent_skill"] == requests[structured["request_hash"]]["parent_skill"]


def test_final_never_reaches_learning_and_host_gold_never_reaches_model(setup):
    root, state, build = setup
    build().run()
    groups = study.read(root / "private_panel.json")["groups"]
    final_ids = {task["id"] for task in groups["final"]}
    confirmation_ids = {task["id"] for task in groups["confirmation"]}
    first_final = next(i for i, r in enumerate(state["receipts"])
        if json.loads(r["request"]["user"]).get("task", {}).get("id") in final_ids)
    assert all(r["request"]["kind"] != "v17_skill_update" for r in state["receipts"][first_final:])
    forbidden_fields = ('"reference_files":', '"reference_artifact":', '"private_cases":',
                        '"hidden_cases":', '"mechanism_cell":', '"structural_family":')
    for receipt in state["receipts"]:
        request = receipt["request"]
        assert all(field not in request["user"] for field in forbidden_fields)
        if request["kind"] == "v17_skill_update":
            assert all(identifier not in request["user"] for identifier in final_ids | confirmation_ids)
            facts = core.flatten_feedback(json.loads(request["user"])["development_feedback"])
            assert all(fact["phase"] == "development" for fact in facts)


def test_partition_identity_and_cluster_overlap_rejected(setup):
    _, _, build = setup
    runner = build()
    runner.panel["source_extra"] = deepcopy(runner.panel["source"])
    with pytest.raises(ValueError, match="overlap"):
        runner.prepare()


def test_unequal_local_and_cross_feedback_budget_rejected(setup):
    _, _, build = setup
    runner = build()
    extra = tasks._coding(tasks.CODING_DEV[2], "development")
    extra.task.metadata["mechanism_cell"] = "same_mechanism"
    runner.panel["source_extra"].append(extra)
    with pytest.raises(ValueError, match="equal task counts"):
        runner.prepare()


@pytest.mark.parametrize("families,valid,available,qualified", [
    (["a", "b"], True, True, True),
    (["a", "a"], True, True, False),
    (["a", "b"], False, True, False),
    (["a", "b"], True, False, False),
])
def test_headroom_requires_semantic_failures_in_distinct_families(families, valid, available, qualified):
    rows = [{"phase": "development", "arm": "no_skill", "oracle_available": available,
             "artifact_valid": valid, "passed": False, "structural_family": family}
            for family in families]
    assert study.screen_summary(rows)["continue"] is qualified
