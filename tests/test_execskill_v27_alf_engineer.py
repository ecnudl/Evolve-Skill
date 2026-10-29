"""ALF v2 prompt and disclosed-only tracker feedback through real engineer requests."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from skillopt.execskill import engineer as e, manifest, profiles as p, replay
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_alf_v1_engineer import assert_alf_evidence_contract
from tests.test_execskill_replay import alf_trajectory
from tests.test_execskill_v24_engineer import context, detail
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v24_routing_review import tracker_change
from tests.test_execskill_zpc_pipeline import offline


@pytest.mark.parametrize("mode", ["train", "single"])
def test_alf_v2_prompts_extend_alf_evidence_and_use_registered_hashes(mode):
    ctx, _ = context(configuration=p.ALFWORLD_V2, bench="alfworld", mode=mode)
    prompt = e.ENGINEER_SYSTEM_ALF_V2 if mode == "train" else e.ENGINEER_SYSTEM_SINGLE_ALF_V2
    base = e.ENGINEER_SYSTEM_ALF_V1 if mode == "train" else e.ENGINEER_SYSTEM_SINGLE_ALF_V1
    assert prompt == (base.replace("configuration alfworld-v1", "configuration alfworld-v2")
                      + e.ENGINEER_FACTS_V27 + "\n" + replay.tracker_format_rules() + "\n")
    assert_alf_evidence_contract(prompt, training=mode == "train")
    assert "ZebraLogic grid-mode addition" not in prompt
    assert "Reference tracker (alfworld-v2)" in prompt and "INSIDE property" in prompt
    for purpose in ("propose", "repropose", "fix/1"):
        ctx.roles = WireRoles()
        e._ask(ctx, e.payload(ctx), purpose)
        assert ctx.roles.wire[0]["system"] == prompt
    pinned = manifest.prompt_sha(p.ALFWORLD_V2)
    assert pinned["engineer"] == e.ENGINEER_PROMPT_SINGLE_ALF_V2_SHA256
    assert pinned["v2"]["engineer"] == e.ENGINEER_PROMPT_ALF_V2_SHA256


def tagged(cell, task, sentinel):
    value = deepcopy(alf_trajectory(cell=cell, token="fail"))
    value["task_id"] = task
    view = json.loads(value["calls"][1]["user"])
    view["observation"] += " " + sentinel
    value["calls"][1]["user"] = json.dumps(view)
    value["alfworld_steps"][1]["observation"] = view["observation"]
    value["alfworld_steps"][0]["post_observation"] = view["observation"]
    return p.record("trajectory", value["evidence"], {key: child for key, child in value.items()
                    if key not in (p.RECORD_HASH, "version", "evidence")})


@pytest.mark.parametrize("configuration", [p.ALFWORLD_V1, p.ALFWORLD_V2])
def test_c7_tracker_failure_reaches_fix_with_only_shown_observations_and_unchanged_verdict(configuration):
    ctx, _ = context(configuration=configuration, bench="alfworld")
    shown = tagged("a-shown", "alf-0", "SHOWN_TRACKER_OBSERVATION")
    hidden = tagged("z-unshown", "alf-1", "UNSHOWN_TRACKER_OBSERVATION")
    ctx = replace(ctx, trajectories=[shown, hidden], current=[shown],
                  routing_items=[(t["task_id"], replay.inputs_of(t)["view"]) for t in (shown, hidden)])
    bad, fixed = tracker_change(ctx, claims=False), tracker_change(ctx, claims=False)
    bad.source = bad.source.replace('count += int(', 'count += 1 + int(')
    ctx.roles = WireRoles([engineer_reply({"findings": []}, [])] + [
        engineer_reply({"changes": [change.entry]}, [change.source]) for change in (bad, fixed)])
    candidate, record = e.run_train(ctx)
    assert candidate is not None
    assert record["version"] == p.kind("engineer-alf-v2" if configuration == p.ALFWORLD_V2 else "engineer-alf-v1")
    attempts = record["changes"][0]["attempts"]
    assert [row["failed"] for row in attempts] == ["C7", None]
    failed = detail(attempts[0], "C7")
    assert failed["problems"] == [{"reason": "reference_tracker", "detail": [0, 10]}]
    assert failed["tracker_agreement"] == [0, 10]
    assert detail(attempts[1], "C7")["tracker_agreement"] == [10, 10]
    fix = next(json.loads(row["user"]) for row in ctx.roles.wire if json.loads(row["user"]).get("request") == "fix")
    assert fix["failed"]["detail"] == failed
    assert "UNSHOWN_TRACKER_OBSERVATION" not in json.dumps(ctx.roles.wire)
    if configuration == p.ALFWORLD_V2:
        assert failed["tracker_disagreement_counts"] == {"reached": 0, "carrying": 0,
                                                        "nothing_happens": 10, "facts_shape": 0}
        examples = failed["tracker_disagreements"]
        assert len(examples) == 3 and [row["step"] for row in examples] == [0, 1, 2]
        assert {row["trajectory"] for row in examples} == {shown["cell"]}
        assert "SHOWN_TRACKER_OBSERVATION" in examples[0]["observation"]
        assert all(len(row["observation"]) <= 200 and len(row["action"]) <= 200 for row in examples)
        assert all(len(row["procedure_facts"]) <= 1000 and len(row["reference_facts"]) <= 1000 for row in examples)
        assert fix["replay_test_instruction"] == e.FIX_TESTS_V27
        assert "tracker_disagreement_counts" not in detail(attempts[1], "C7")
    else:
        assert set(failed) == {"check", "passed", "problems", "tracker_agreement"}
        assert "replay_test_instruction" not in fix


def test_alf_v2_c7_without_any_shown_cell_reports_counts_only():
    ctx, _ = context(configuration=p.ALFWORLD_V2, bench="alfworld")
    assert not e._feedback_cells(ctx)
    bad = tracker_change(ctx, claims=False)
    bad.source = bad.source.replace('count += int(', 'count += 1 + int(')
    result = e.check(bad, ctx)
    assert result["failed"] == "C7"
    failed = detail(result, "C7")
    assert failed["tracker_disagreement_counts"]["nothing_happens"] == 5
    assert failed["tracker_disagreements"] == []


def test_tracker_prompt_is_alf_v2_only_even_though_fix_help_is_shared():
    for configuration in (name for name in p.CONFIGURATIONS if not p.is_v28(name) and not p.is_v210(name)):
        ctx, _ = context(configuration=configuration, bench="alfworld")
        ctx.roles = WireRoles()
        e._ask(ctx, e.payload(ctx), "propose")
        system = ctx.roles.wire[0]["system"]
        assert (e.REFERENCE_TRACKER_ALF_V2 in system) is p.is_alfworld_v2(configuration)
        assert (e.FIX_TESTS_V27 in system) is p.is_v27(configuration)
