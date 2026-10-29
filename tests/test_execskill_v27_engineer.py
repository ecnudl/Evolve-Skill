"""v2.7 test-format diagnostics through real engineer checks and fake role requests."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from skillopt.execskill import engineer as e, profiles as p, replay
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import change, detail
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v26_references import CELL, fixture, reference


def fragments(ctx, count=10, *, claims=True):
    test = reference(ctx, CELL, claims=claims)
    test["property"] = {"kind": "note_matches", "value": ["Mara"] * count}
    return test


def reply(proposed):
    return engineer_reply({"changes": [proposed.entry]}, [proposed.source])


def run(ctx, proposed, *fixed):
    prefix = [engineer_reply({"findings": []}, [])] if ctx.mode == "train" else []
    ctx.roles = WireRoles(prefix + [reply(item) for item in (proposed, *fixed)])
    return e.run_train(ctx) if ctx.mode == "train" else e.run(ctx)


@pytest.mark.parametrize("mode", ["train", "single"])
@pytest.mark.parametrize("count", [6, 10])
def test_real_fragment_failure_is_not_a_verdict_on_correct_output_and_can_fix_only_test(mode, count):
    ctx, _ = fixture(configuration=p.ZEBRA_PC_V5, mode=mode)
    original = change(ctx, tests=[fragments(ctx, count)])
    corrected = change(ctx, tests=[reference(ctx, CELL)])
    package, record = run(ctx, original, corrected)
    assert package is not None and package.procedures[0].source == original.source
    assert record["version"] == p.kind("engineer-v2-7")
    attempts = record["changes"][0]["attempts"]
    assert attempts[0]["failed"] == "C5b" and attempts[1]["passed"]
    failed = detail(attempts[0], "C5b")["failed"][0]
    assert failed["reason"] == "value" and failed["evaluated"] is False
    assert "note_matches has %d fragments" % count in failed["validation_explanation"]
    assert "1-5" in failed["validation_explanation"] and "1-200" in failed["validation_explanation"]
    assert "not evaluated" in failed["validation_explanation"].lower()
    assert failed["actual"]["status"] == "returned" and "Mara" in failed["actual"]["value"]
    assert "rendered_note" not in failed  # malformed properties were not matched against rendered text
    fix = next(payload for _, payload, _ in ctx.roles.seen if payload.get("request") == "fix")
    assert fix["replay_test_instruction"] == e.FIX_TESTS_V27
    assert fix["failed"]["detail"]["failed"][0] == failed
    assert detail(attempts[1], "C5b") == {"claimed": 1, "failed": []}
    expected = e.ENGINEER_PROMPT_ZPC_V27_SHA256 if mode == "train" else e.ENGINEER_PROMPT_SINGLE_ZPC_V27_SHA256
    assert record["prompt_sha256"] == expected


@pytest.mark.parametrize("repair", ["remove", "advisory"])
def test_fix_may_remove_or_demote_unsatisfied_claim_without_relaxing_remaining_claims(repair):
    ctx, _ = fixture(configuration=p.ZEBRA_PC_V5)
    false = reference(ctx, CELL)
    false["property"]["value"] = "A nonexistent clue."
    corrected_tests = [reference(ctx, CELL)]
    if repair == "advisory":
        corrected_tests.append({**false, "id": "advisory", "claims_fix": False})
    package, record = run(ctx, change(ctx, tests=[false]), change(ctx, tests=corrected_tests))
    assert package is not None
    attempts = record["changes"][0]["attempts"]
    failed = detail(attempts[0], "C5b")["failed"][0]
    assert failed["reason"] == "test_failed" and "evaluated" not in failed
    assert "validation_explanation" not in failed and "rendered_note" in failed
    assert detail(attempts[1], "C5b")["claimed"] == 1
    if repair == "advisory":
        assert attempts[1]["lint"]["tests"][1]["holds"] is False


@pytest.mark.parametrize("bad", ["id", "keys", "step", "fragments", "trajectory"])
def test_invalid_lint_explanation_survives_record_and_next_proposal_without_new_item_text(bad):
    ctx, _ = fixture(configuration=p.ZEBRA_PC_V5)
    test = reference(ctx, CELL, claims=False)
    if bad == "id":
        test["id"] = "z 1"
    elif bad == "keys":
        test["extra"] = "engineer's own extra field"
    elif bad == "step":
        test["property"]["step"] = 0
    elif bad == "fragments":
        test = fragments(ctx, claims=False)
    else:
        test["trajectory"] = "not-in-scope"
    package, record = run(ctx, change(ctx, tests=[test]))
    assert package is not None
    lint = json.loads(json.dumps(record["lint"]))
    problem = lint[0]["problems"][0]
    assert problem["reason"] == "invalid_test" and problem["evaluated"] is False
    assert problem["validation_explanation"]
    assert e._lint_entry(lint[0], v25=True, v26=True, v27=True)
    assert not e._lint_entry(lint[0], v25=True, v26=True)
    if bad == "trajectory":
        assert problem["valid_trajectories"] == [{"trajectory": CELL, "task_id": ctx.trajectories[0]["task_id"]}]
    next_ctx = replace(ctx, round=2, lint=lint, roles=WireRoles())
    e.run_train(next_ctx)
    proposal = next(payload for _, payload, _ in next_ctx.roles.seen if payload.get("request") == "propose")
    assert proposal["lint"] == lint


def test_excess_count_is_advisory_and_explained_without_changing_admission():
    ctx, _ = fixture(configuration=p.ZEBRA_PC_V5)
    tests = [{**reference(ctx, CELL, claims=False), "id": "test-%d" % n} for n in range(9)]
    package, record = run(ctx, change(ctx, tests=tests))
    assert package is not None
    problem = record["lint"][0]["problems"][0]
    assert problem["reason"] == "test_count" and problem["detail"] == 9 and problem["evaluated"] is False
    assert "9" in problem["validation_explanation"]
    assert e._lint_entry(record["lint"][0], v25=True, v26=True, v27=True)


@pytest.mark.parametrize("bad,check", [(None, "C1"), (["not a test"], "C3"), ("duplicate", "C3"), ("hook", "C3")])
def test_pre_replay_test_admission_failures_also_explain_own_malformed_tests(bad, check):
    ctx, _ = fixture(configuration=p.ZEBRA_PC_V5)
    if bad == "duplicate":
        bad = [reference(ctx, CELL), reference(ctx, CELL)]
    elif bad == "hook":
        bad = [{**reference(ctx, CELL), "hook": "bindings"}]
    proposed = change(ctx)
    proposed.entry["replay_tests"] = bad
    report = e.check(proposed, ctx)
    assert report["failed"] == check
    found = detail(report, check)["replay_test_validation"]
    assert found["evaluated"] is False and found["validation_explanation"]


def test_single_mode_missing_test_list_reports_its_actual_required_keys():
    ctx, _ = fixture(configuration=p.ZEBRA_PC_V5, mode="single")
    proposed = change(ctx)
    del proposed.entry["replay_tests"]
    report = e.check(proposed, ctx)
    assert report["failed"] == "C1"
    assert "replay_tests" in detail(report, "C1")["required"]
    assert "replay_tests" not in detail(report, "C1")["given"]


@pytest.mark.parametrize("mode", ["train", "single"])
def test_v27_instructions_reach_every_engineer_proposal_and_fix_channel_only_v27(mode):
    for configuration in (name for name in p.CONFIGURATIONS if not p.is_v28(name) and not p.is_v210(name)):
        for purpose in ("propose", "repropose", "fix/1"):
            ctx, _ = fixture(configuration=configuration, mode=mode)
            ctx.roles = WireRoles()
            e._ask(ctx, {"request": purpose}, purpose)
            system = ctx.roles.wire[0]["system"]
            assert (e.REPLAY_TEST_LIMITS_V27 in system) is p.is_v27(configuration)
            assert (e.FIX_TESTS_V27 in system) is p.is_v27(configuration)
            if p.is_v27(configuration):
                assert e.REPLAY_TEST_LIMITS_V27 == replay.test_format_limits()
                assert "PYTHONHASHSEED=0" in system and "PYTHONHASHSEED=1" in system
                assert "only when unambiguous" in system and "16000" in system


def test_same_v4_invalid_claim_and_lint_details_are_unchanged_after_v27():
    records = {}
    for configuration in (p.ZEBRA_PC_V4, p.ZEBRA_PC_V5):
        ctx, _ = fixture(configuration=configuration)
        original = change(ctx, tests=[fragments(ctx)])
        corrected = change(ctx, tests=[fragments(ctx, claims=False)])
        _, record = run(ctx, original, corrected)
        fail = detail(record["changes"][0]["attempts"][0], "C5b")["failed"][0]
        lint = record["lint"][0]["problems"][0]
        records[configuration] = deepcopy((fail, lint))
    v4, v5 = records[p.ZEBRA_PC_V4], records[p.ZEBRA_PC_V5]
    for old, new in zip(v4, v5):
        assert "validation_explanation" not in old and "evaluated" not in old
        assert {k: value for k, value in new.items() if k not in ("validation_explanation", "evaluated")} == old


def test_lint_feedback_shape_rejects_forged_evaluation_flags_and_unbounded_text():
    entry = {"id": "p-fixture", "tests": [], "problems": [
        {"reason": "invalid_test", "test": 1, "detail": "value", "evaluated": False,
         "validation_explanation": "The own test is malformed; not evaluated."}]}
    assert e._lint_entry(entry, v25=True, v26=True, v27=True)
    for patch in ({"evaluated": True}, {"validation_explanation": "x" * (replay.VALIDATION_EXPLANATION_CHARS + 1)},
                  {"reason": "test_failed"}):
        bad = deepcopy(entry)
        bad["problems"][0].update(patch)
        assert not e._lint_entry(bad, v25=True, v26=True, v27=True)
