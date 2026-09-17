from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v15 import learning
from skillopt.validator_pilot.api import digest


def fixture():
    parent = learning.empty_state()
    public = [{"id": "dev-1", "obligations": ["preserve input"]}]
    observations = [{"role": role, "artifact": {"formulas": {"B1": "=A1"}},
                     "feedback": seal({"phase": "development", "task_id": "dev-1",
                         "provenance": {"skill_hash": learning.text_hash("")}})}
                    for role in ("no_skill", "current")]
    probes = [seal({"phase": "development", "source_task_id": "dev-1",
                    "artifact_hash": digest(observations[0]["artifact"]), "score": {"oracle_available": False}})]
    return parent, public, observations, probes


def test_same_shared_prompt_and_strict_contract():
    inputs = fixture()
    system, user, identity = learning.messages(*inputs)
    assert "SAME updater" in system
    assert "no_skill" in user
    assert len(identity) == 64
    assert learning.messages(*deepcopy(inputs)) == (system, user, identity)


@pytest.mark.parametrize("phase", ["calibration", "final", "selection"])
def test_refuse_non_development_feedback(phase):
    parent, public, observations, probes = fixture()
    view = dict(observations[0]["feedback"])
    view.pop("record_hash")
    view["phase"] = phase
    observations[0]["feedback"] = seal(view)
    with pytest.raises(ValueError):
        learning.messages(parent, public, observations, probes)


def test_refuse_probe_artifact_substitution():
    parent, public, observations, _ = fixture()
    probes = [seal({"phase": "development", "source_task_id": "dev-1", "artifact_hash": digest(None)})]
    with pytest.raises(ValueError):
        learning.messages(parent, public, observations, probes)


def test_refuse_unpaired_roles_and_wrong_parent():
    parent, public, observations, probes = fixture()
    with pytest.raises(ValueError):
        learning.messages(parent, public, observations[:1], probes)
    parent["skill"] = "changed"
    with pytest.raises(ValueError):
        learning.messages(parent, public, observations, probes)


def test_unknown_and_invalid_update_retain_parent():
    parent = {"skill": "previous", "rules": []}
    for receipt in ({"ok": False}, {"ok": True, "response": "{\"skill\":\"invalid\"}"}):
        result = learning.parse_update(receipt, parent)
        assert result["state"] == parent
        assert not result["valid"]


def test_successful_whole_text_common_update():
    value = "## When\nExplicit constraints apply.\n## Procedure\nCheck dependent outputs.\n## Avoid\nAssuming an unstated scope."
    result = learning.parse_update({"ok": True, "response": value}, learning.empty_state())
    assert result["valid"] and result["skill"] == value
