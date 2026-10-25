"""Codex review #4: single-mode smoke has its own pinned v2.3 contract. Synthetic role replies only."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.execskill import engineer, manifest, protocol, smoke, smoke_roles
from skillopt.execskill.package import FIXTURE
from skillopt.validator_pilot.api import digest
from tests.test_execskill_v23_engineer import ScriptedRoles, context


def single(configuration=protocol.MAIN_V2_3):
    return replace(context(configuration), mode="single", round=0, base=None,
                   label="D/s1-searchqa/engineer")


def test_v23_single_prompt_requires_replay_tests_and_its_record_pins_that_prompt():
    ctx = single()
    engineer._ask(ctx, {"request": "propose"}, "propose")
    engineer._ask(ctx, {"request": "fix"}, "fix/1")
    assert engineer.ENGINEER_SYSTEM_SINGLE_V23 == engineer.ENGINEER_SYSTEM + engineer.ENGINEER_FACTS_V23
    assert engineer.ENGINEER_PROMPT_SINGLE_V23_SHA256 == digest(engineer.ENGINEER_SYSTEM_SINGLE_V23)
    assert all(entry[1] == engineer.ENGINEER_SYSTEM_SINGLE_V23 and entry[-1] == {} for entry in ctx.roles.seen)
    assert "Replay tests (1 to 8" in ctx.roles.seen[0][1]
    assert "Replay tests (0 to 8" not in ctx.roles.seen[0][1]
    change = engineer.Change(1, "new", {"kind": "new", "description": "Checks public facts.",
                                        "hooks": ["applies"]}, "def applies(view):\n    return True\n", "call")
    assert engineer._structure(change, ctx.parent, ()) == "keys"
    change.entry["replay_tests"] = [{"id": "local-evidence"}]
    assert engineer._structure(change, ctx.parent, ()) is None
    _, sealed = engineer.run(single())
    assert sealed["prompt_sha256"] == engineer.ENGINEER_PROMPT_SINGLE_V23_SHA256
    _, trained = engineer.run_train(context())
    assert trained["prompt_sha256"] == engineer.ENGINEER_PROMPT_V23_SHA256


def test_v23_smoke_uses_the_single_mode_prompt_and_manifest_pins_both_modes():
    roles = ScriptedRoles()
    setting = SimpleNamespace(extra={"configuration": protocol.MAIN_V2_3}, pools={"searchqa": []}, cards={})
    result, _ = smoke_roles._engineer(roles, setting, None, "D/s1-searchqa/engineer", [], FIXTURE)
    assert roles.seen[0][1] == engineer.ENGINEER_SYSTEM_SINGLE_V23
    assert roles.seen[0][-1] == {}
    assert result["record"]["prompt_sha256"] == engineer.ENGINEER_PROMPT_SINGLE_V23_SHA256
    pins = manifest.prompt_sha(protocol.MAIN_V2_3)
    assert pins["engineer"] == engineer.ENGINEER_PROMPT_SINGLE_V23_SHA256
    assert pins["v2"]["engineer"] == engineer.ENGINEER_PROMPT_V23_SHA256
    assert smoke.engineer_request_floor(protocol.MAIN_V2_3) == protocol.ROLE_INPUT_BYTES + max(
        len(prompt.encode()) for prompt in (engineer.ENGINEER_SYSTEM_SINGLE_V23,
                                           engineer.ENGINEER_SYSTEM_V23, engineer.ANALYST_SYSTEM))


@pytest.mark.parametrize("configuration", [c for c in protocol.CONFIGURATIONS if c != protocol.MAIN_V2_3])
def test_older_single_prompts_records_and_manifest_pins_remain_unchanged(configuration):
    ctx = single(configuration)
    _, sealed = engineer.run(ctx)
    assert ctx.roles.seen[0][1] == engineer.ENGINEER_SYSTEM
    assert sealed["prompt_sha256"] == engineer.ENGINEER_PROMPT_SHA256
    assert manifest.prompt_sha(configuration)["engineer"] == engineer.ENGINEER_PROMPT_SHA256
