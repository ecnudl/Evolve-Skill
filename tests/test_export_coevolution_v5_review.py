"""Synthetic offline export fixtures; no actual human reviews are claimed."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.export_coevolution_v5_review import export_corrected_queue, inspect_run
from skillopt.coevolution_v5 import core, governance
from skillopt.validator_pilot.api import digest


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def get(path):
    return json.loads(path.read_text())


def reseal(value):
    return core.seal({key: item for key, item in value.items() if key != "record_hash"})


def fixture_run(tmp_path, *, complete=True):
    repo, run = tmp_path / "repo", tmp_path / "repo/outputs/run"
    repo.mkdir()
    source = repo / "source.py"
    source.write_text("# synthetic frozen source\n")
    artifact = {"main.py": "def run(): return 1"}
    rubric = core.initial_rubric()
    observation = core.make_assessment(
        check_id="coding_contract", task_id="dev", domain="coding", phase="development",
        artifact_hash=digest(artifact), rubric_hash=rubric["rubric_hash"], status="pass",
        evidence_kind="execution", verified=True, gate_eligible=True, details={"task_split": "development"})
    packet = core.feedback_packet(task_id="dev", cluster_id="dev-project", domain="coding",
                                  assessments=[observation], artifact=artifact, contract="Return one.")
    panel = core.seal({"source": [[{"domain": "coding", "task": {"id": "dev", "cluster_id": "dev-project"}}]],
                       "scope": [[]], "promotion": [], "final": []})
    protocol = core.seal({"version": "coevolution-v5-integration-study-v1", "rounds": 2,
                          "panel_hash": panel["record_hash"],
                          "source_hashes": {"source.py": hashlib.sha256(source.read_bytes()).hexdigest()}})
    put(run / "protocol.json", protocol)
    put(run / "panel.json", panel)
    branches = {"h0-fixed": {"skill": governance.initial_skill_state(), "rubric": rubric, "feedback": [packet]},
                "h0-feedback": {"skill": governance.initial_skill_state(), "rubric": rubric, "feedback": [packet]}}
    state = core.seal(branches)
    put(run / "states/r0.json", state)
    if complete:
        put(run / "states/r1.json", state)
        put(run / "final_frozen.json", core.seal({"protocol_hash": protocol["record_hash"], "states": branches,
                                                  "decisions_hash": digest([])}))
        put(run / "results.json", core.seal({"status": "complete", "protocol_hash": protocol["record_hash"],
                                             "decisions": [], "final_feedback_used": False,
                                             "ledger": {"unresolved_reservations": []}}))
    put(run / "human_review/queue.json", {"intentionally": "original frozen empty queue placeholder"})
    return repo, run


def snapshot(run):
    return {str(path.relative_to(run)): path.read_bytes() for path in run.rglob("*") if path.is_file()}


def test_read_only_validation_of_incomplete_run(tmp_path):
    repo, run = fixture_run(tmp_path, complete=False)
    before = snapshot(run)
    result = inspect_run(run, repo=repo)
    assert not result["complete"]
    assert len(result["packets"]) == 1
    assert snapshot(run) == before
    with pytest.raises(ValueError, match="completed, frozen run"):
        export_corrected_queue(run, repo=repo)
    assert snapshot(run) == before


def test_export_preserves_original_and_contains_actual_evidence(tmp_path):
    repo, run = fixture_run(tmp_path)
    original = snapshot(run)
    result = export_corrected_queue(run, repo=repo)
    assert result["retained_unique_feedback"] == 1
    assert result["queued"] == 1
    assert result["status"] == "awaiting_external_human_review"
    assert all((run / name).read_bytes() == contents for name, contents in original.items())
    queue = get(Path(result["queue_path"]))
    evidence = queue["entries"][0]["evidence"]
    assert evidence["artifact"] == {"main.py": "def run(): return 1"}
    assert evidence["contract"] == "Return one."
    assert evidence["facts"]
    assert queue["review_performed"] is False
    manifest = get(run / "human_review_corrected/source_manifest.private.json")
    assert manifest["scores_and_decisions_changed"] is False
    assert manifest["human_review_performed"] is False
    assert len(next(iter(manifest["origins"].values()))) == 4
    assert export_corrected_queue(run, repo=repo) == result


def test_frozen_source_change_blocks_export(tmp_path):
    repo, run = fixture_run(tmp_path)
    (repo / "source.py").write_text("# changed\n")
    with pytest.raises(ValueError, match="source changed"):
        export_corrected_queue(run, repo=repo)
    assert not (run / "human_review_corrected").exists()


def test_packet_tampering_not_hidden_by_resealed_outer_state(tmp_path):
    repo, run = fixture_run(tmp_path)
    state = get(run / "states/r0.json")
    state["h0-fixed"]["feedback"][0]["contract"] = "Invented modified contract"
    put(run / "states/r0.json", reseal(state))
    with pytest.raises(ValueError, match="checksum mismatch"):
        export_corrected_queue(run, repo=repo)


def test_relabelled_final_feedback_cannot_enter_human_queue(tmp_path):
    repo, run = fixture_run(tmp_path, complete=False)
    state = get(run / "states/r0.json")
    packet = state["h0-fixed"]["feedback"][0]
    packet["research_context"] = {"source_phase": "final"}
    state["h0-fixed"]["feedback"][0] = reseal(packet)
    put(run / "states/r0.json", reseal(state))
    with pytest.raises(ValueError, match="cannot become development"):
        inspect_run(run, repo=repo)


def test_packet_task_identity_bound_to_panel(tmp_path):
    repo, run = fixture_run(tmp_path, complete=False)
    state = get(run / "states/r0.json")
    packet = state["h0-fixed"]["feedback"][0]
    packet["cluster_id"] = "unobserved cluster"
    state["h0-fixed"]["feedback"][0] = reseal(packet)
    put(run / "states/r0.json", reseal(state))
    with pytest.raises(ValueError, match="frozen development panel"):
        inspect_run(run, repo=repo)


def test_feedback_artifact_hash_bound(tmp_path):
    repo, run = fixture_run(tmp_path, complete=False)
    state = get(run / "states/r0.json")
    packet = state["h0-fixed"]["feedback"][0]
    packet["artifact"]["main.py"] = "def run(): return 2"
    state["h0-fixed"]["feedback"][0] = reseal(packet)
    put(run / "states/r0.json", reseal(state))
    with pytest.raises(ValueError, match="artifact content"):
        inspect_run(run, repo=repo)


def test_fake_facts_cannot_override_verified_observation(tmp_path):
    repo, run = fixture_run(tmp_path, complete=False)
    state = get(run / "states/r0.json")
    packet = state["h0-fixed"]["feedback"][0]
    packet["facts"][0]["status"] = "fail"
    state["h0-fixed"]["feedback"][0] = reseal(packet)
    put(run / "states/r0.json", reseal(state))
    with pytest.raises(ValueError, match="not supported"):
        inspect_run(run, repo=repo)


@pytest.mark.parametrize("change", [{"protocol_hash": digest("wrong protocol")},
                                     {"final_feedback_used": True},
                                     {"ledger": {"unresolved_reservations": ["pending"]}}])
def test_wrong_or_unresolved_complete_run_rejected(tmp_path, change):
    repo, run = fixture_run(tmp_path)
    result = get(run / "results.json")
    result.update(deepcopy(change))
    put(run / "results.json", reseal(result))
    with pytest.raises(ValueError):
        export_corrected_queue(run, repo=repo)


def test_final_freeze_must_match_retained_final_branch_states(tmp_path):
    repo, run = fixture_run(tmp_path)
    freeze = get(run / "final_frozen.json")
    freeze["states"]["h0-fixed"]["feedback"] = []
    put(run / "final_frozen.json", reseal(freeze))
    with pytest.raises(ValueError, match="Final freeze"):
        export_corrected_queue(run, repo=repo)


def test_completed_run_requires_all_round_states(tmp_path):
    repo, run = fixture_run(tmp_path)
    (run / "states/r0.json").unlink()
    with pytest.raises(ValueError, match="missing a sealed round state"):
        export_corrected_queue(run, repo=repo)


def test_export_never_overwrites_different_corrected_queue(tmp_path):
    repo, run = fixture_run(tmp_path)
    path = run / "human_review_corrected/queue.json"
    put(path, {"preexisting": "belongs to user"})
    with pytest.raises(ValueError, match="Immutable artifact differs"):
        export_corrected_queue(run, repo=repo)
    assert get(path) == {"preexisting": "belongs to user"}
