"""Interrupted ALF responses through real solver, persisted trajectory and replay; synthetic local transports."""
import json

from tests.execskill_zpc_fakes import tmp_path
from tests.execskill_fakes_env import alf_sessions
from tests.fixtures.execskill.items import alfworld_items
from tests.test_execskill_replay import fixture
from tests.test_execskill_trajectories import _Client, _run, stall
from tests.test_execskill_v24_engineer import Workers
from tests.test_execskill_zpc_pipeline import offline
from skillopt.coevo5.protocol import RUNTIME
from skillopt.execskill import replay


TRACKER = '''def applies(view):
    return True
def alf_before_step(view, state):
    return {"fields": {}, "discourage": []}
def alf_after_step(event, state):
    count = state["facts"]["nothing_happens"] if state else 0
    count += int(event["observation"].startswith("Nothing happens"))
    return {"facts": {"reached": [], "carrying": [], "nothing_happens": count}}
'''


def tracked(trajectory):
    procedure = fixture("fx-v27-tracker-review", TRACKER, ("applies", "alf_before_step", "alf_after_step"),
                        origin="alfworld", state_bytes=1000)
    entry = replay.inputs_of(trajectory)
    workers, actual = Workers(), {}
    outcomes = replay.replay_many(procedure, [entry], workers, actual=actual)
    return entry, outcomes, actual


def test_unavailable_following_response_still_supplies_prior_action_event_and_tracker_denominator(tmp_path, monkeypatch):
    sessions = alf_sessions(monkeypatch)
    item = alfworld_items(tmp_path / "authored-games")[0]
    result, trajectory = _run(tmp_path / "interrupted", item, _Client(stall, censor_after=1))
    assert result["final"]["token"] == "unknown"
    requests = [call for call in trajectory["calls"] if call["purpose"] == "step"]
    assert len(requests) == 2
    assert [step["i"] for step in trajectory["alfworld_steps"]] == [0]
    assert [step["action"] for step in trajectory["alfworld_steps"]] == ["look"]
    assert requests[0]["receipt"]["delivery"] != requests[1]["receipt"]["delivery"]
    entry, outcomes, actual = tracked(trajectory)
    assert len(entry["steps"]) == 2
    assert entry["steps"][0]["event"] == {
        "step": 0, "action": "look", "observation": json.loads(requests[1]["user"])["observation"],
        "admissible_commands": json.loads(requests[1]["user"])["admissible_commands"]}
    assert entry["steps"][1]["action"] is None and entry["steps"][1]["event"] is None
    assert [call["step"] for call in actual[entry["cell"]] if call["hook"] == "alf_after_step"] == [0]
    agreement = replay.reference_tracker_agreement({entry["cell"]: entry}, outcomes)
    assert list(agreement) == [1, 1]
    text = replay.tracker_format_rules()
    assert "exactly when a following step request/view exists" in text
    assert "even if its response was unavailable" in text
    assert "actions without a following view have no event and are excluded" in text
    assert "final stored step has no replay event" not in text
    limits = replay.test_format_limits()
    assert "0-based index of the stored step request/view" in limits
    assert "for every stored action it equals alfworld_steps[].i" in limits
    assert all(session.closed for session in sessions)


def test_action_without_following_request_is_excluded_by_same_mechanism(tmp_path, monkeypatch):
    alf_sessions(monkeypatch)
    item = alfworld_items(tmp_path / "authored-games")[0]
    runtime = {**RUNTIME, "alfworld": {**RUNTIME["alfworld"], "max_steps": 1}}
    result, trajectory = _run(tmp_path / "stopped", item, _Client(stall), runtime=runtime)
    assert result["final"]["token"] == "fail"
    assert len([call for call in trajectory["calls"] if call["purpose"] == "step"]) == 1
    assert [step["i"] for step in trajectory["alfworld_steps"]] == [0]
    entry, outcomes, actual = tracked(trajectory)
    assert entry["steps"][0]["action"] == "look" and entry["steps"][0]["event"] is None
    assert [call for call in actual[entry["cell"]] if call["hook"] == "alf_after_step"] == []
    assert replay.reference_tracker_agreement({entry["cell"]: entry}, outcomes) == (0, 0)
