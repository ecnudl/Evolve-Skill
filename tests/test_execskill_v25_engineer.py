"""v2.5 rendered feedback, disclosure and source limits on authored, offline synthetic fixtures."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from skillopt.execskill import engineer, notes, profiles as p, replay
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import EMPTY, GOOD, PUBLIC, change, claim, context, detail
from tests.test_execskill_v24_feedback_isolation import WireRoles, add_generated, GENERATED
from tests.test_execskill_zpc_pipeline import offline

V25 = p.ZEBRA_PC_V3
TABLE = GOOD.replace('    return {"table":',
                     '    rows = [[row[0].replace("House ", "")] + row[1:] for row in rows]\n    return {"table":')


def shown_context(*, configuration=V25, mode="train", views=None):
    ctx, workers = context(configuration=configuration, mode=mode, views=views)
    if mode == "train":
        ctx = replace(ctx, current=ctx.trajectories)
    return ctx, workers


def matches(ctx, *, good=False, claims=True):
    test = claim(ctx, claims=claims)
    test["property"] = {"kind": "note_matches", "value": ["| 1 |" if good else "House 1", "Mara", "blue"]}
    return test


def replies(ctx, *changes):
    prefix = [engineer_reply({"findings": []}, [])] if ctx.mode == "train" else []
    return prefix + [engineer_reply({"changes": [item.entry]}, [item.source]) for item in changes]


@pytest.mark.parametrize("configuration", [V25, p.ZEBRA_PC_V2])
@pytest.mark.parametrize("mode", ["train", "single"])
def test_real_claim_fix_sees_the_rendered_table_and_corrected_fragments_pass(configuration, mode):
    ctx, _ = shown_context(configuration=configuration, mode=mode)
    incorrect = change(ctx, TABLE, tests=[matches(ctx)])
    corrected = change(ctx, TABLE, tests=[matches(ctx, good=True)])
    ctx.roles = WireRoles(replies(ctx, incorrect, corrected))
    package, record = engineer.run_train(ctx) if mode == "train" else engineer.run(ctx)
    assert package is not None
    attempts = record["changes"][0]["attempts"]
    assert [attempt["failed"] for attempt in attempts] == ["C5b", None]
    failed = detail(attempts[0], "C5b")["failed"][0]
    assert failed["actual"]["status"] == "returned" and '"1","Mara","blue"' in failed["actual"]["value"]
    fix_system, fix, _ = next(row for row in ctx.roles.seen if row[1].get("request") == "fix")
    assert fix["failed"]["detail"]["failed"][0] == failed
    if configuration == V25:
        expected = notes.render({"table": [["House", "Name", "Color"], ["1", "Mara", "blue"],
            ["2", "Neri", "red"], ["3", "Oren", "green"], ["4", "Pari", "white"],
            ["5", "Quin", "yellow"]]}, bench="zebralogic", header="")
        assert failed["rendered_note"] == expected
        assert "House 1" not in failed["rendered_note"] and "| 1 | Mara | blue |" in expected
        assert engineer.RENDER_SAMPLE_V25 in fix_system
        assert record["version"] == p.kind("engineer-v2-5")
    else:
        assert "rendered_note" not in failed and engineer.RENDER_SAMPLE_V25 not in fix_system


@pytest.mark.parametrize("source", [EMPTY, EMPTY.replace("return {}", 'return {"facts": ["answer"]}')])
def test_screened_empty_claim_feedback_explains_absence(source):
    ctx, _ = shown_context()
    first, fixed = change(ctx, source, tests=[claim(ctx)]), change(ctx, GOOD, tests=[claim(ctx)])
    ctx.roles = WireRoles(replies(ctx, first, fixed))
    package, record = engineer.run_train(ctx)
    assert package is not None
    failed = detail(record["changes"][0]["attempts"][0], "C5b")["failed"][0]
    assert failed["rendered_note"] == replay.NO_RENDERED_NOTE


@pytest.mark.parametrize("configuration", [V25, p.ZEBRA_PC_V2])
def test_lint_persists_rendered_note_into_the_next_actual_proposal(configuration):
    ctx, _ = shown_context(configuration=configuration)
    advisory = change(ctx, TABLE, tests=[matches(ctx, claims=False)])
    ctx.roles = WireRoles(replies(ctx, advisory))
    package, record = engineer.run_train(ctx)
    assert package is not None
    # JSON round trip mirrors the persisted engineer unit carried into a resumed next round.
    saved = json.loads(json.dumps(record["lint"]))
    problems = saved[0]["problems"]
    problem = next(row for row in problems if row["reason"] == "test_failed")
    assert ("rendered_note" in problem) is (configuration == V25)
    next_ctx = replace(ctx, round=2, label="D/s1-zebralogic/engineer-r2", lint=saved,
                       roles=WireRoles())
    engineer.run_train(next_ctx)
    user = next(row[1] for row in next_ctx.roles.seen if row[1].get("request") == "propose")
    assert user["lint"] == saved
    if configuration == V25:
        assert "| 1 | Mara | blue |" in problem["rendered_note"]


@pytest.mark.parametrize("injected", [None, 7, {"private": "text"}, ["text"], "x" * 1501])
def test_next_round_rejects_malformed_rendered_note(injected):
    ctx, _ = shown_context()
    entry = {"id": "fixture", "tests": [], "problems": [
        {"reason": "test_failed", "test": 1, "rendered_note": injected}]}
    with pytest.raises(ValueError, match="Lint entries"):
        replace(ctx, round=2, lint=[entry])


def test_unshown_replayed_cell_and_generated_questions_never_enter_new_feedback():
    sentinel = "UNSHOWNRUNOUTPUTZSENTINEL"
    hidden_view = {**PUBLIC, "question": PUBLIC["question"] + "\n" + sentinel}
    ctx, workers = shown_context(views=[PUBLIC, hidden_view])
    # The complete second run cell is deliberately absent from the current/proposal pool; C6 still replays it.
    ctx = replace(ctx, current=[ctx.trajectories[0]])
    add_generated(ctx)
    source = EMPTY.replace("return {}", 'return {"table": [[view["question"].splitlines()[-1]]]}')
    tests = [claim(ctx, holds="definitely absent")]
    tests.append({**tests[0], "id": "unshown", "trajectory": ctx.trajectories[1]["cell"]})
    first, fixed = change(ctx, source, tests=tests), change(ctx, GOOD, tests=[claim(ctx)])
    ctx.roles = WireRoles(replies(ctx, first, fixed))
    package, record = engineer.run_train(ctx)
    assert package is not None
    failures = detail(record["changes"][0]["attempts"][0], "C5b")["failed"]
    assert "rendered_note" in failures[0]
    assert failures[1]["actual"] == {"status": "withheld", "reason": "trajectory_not_shown"}
    assert "rendered_note" not in failures[1]
    wire = json.dumps({"requests": ctx.roles.wire, "record": record, "payload": engineer.payload(ctx)})
    assert sentinel not in wire and GENERATED not in wire
    assert any(sentinel in args[0].get("question", "") for _, _, args in workers.calls)


def test_fitted_out_trajectory_does_not_authorize_rendered_note(monkeypatch):
    ctx, _ = shown_context(views=[PUBLIC, {**PUBLIC, "question": PUBLIC["question"] + "\nExtra clue."}])
    original_fit = engineer._fit_train
    def leave_one(user):
        user = original_fit(user)
        user["trajectories"] = user["trajectories"][:1]
        return user
    monkeypatch.setattr(engineer, "_fit_train", leave_one)
    payload = engineer.payload(ctx)
    retained = payload["trajectories"][0]["cell"]
    omitted = next(value["cell"] for value in ctx.trajectories if value["cell"] != retained)
    test = {**claim(ctx, holds="missing"), "trajectory": omitted}
    first, fixed = change(ctx, TABLE, tests=[test]), change(ctx, TABLE)
    ctx.roles = WireRoles(replies(ctx, first, fixed))
    _, record = engineer.run_train(ctx)
    failure = detail(record["changes"][0]["attempts"][0], "C5b")["failed"][0]
    assert engineer._feedback_cells(ctx) == {retained}
    assert failure["actual"]["status"] == "withheld" and "rendered_note" not in failure


@pytest.mark.parametrize("action", ['raise ValueError(view["question"])', 'return view["question"]',
                                   'return {"facts": view["question"]}'])
def test_generated_return_or_exception_is_absent_from_every_actual_fix_and_proposal(action):
    ctx, workers = shown_context()
    add_generated(ctx)
    source = ('def applies(view):\n    return True\ndef before_call(view, state):\n'
              '    if "House 1 |" in view["question"]:\n        return {}\n    ' + action + '\n')
    first = change(ctx, source, tests=[claim(ctx)])
    without_claim, fixed = change(ctx, source), change(ctx, GOOD, tests=[claim(ctx)])
    ctx.roles = WireRoles(replies(ctx, first, without_claim, fixed))
    package, record = engineer.run_train(ctx)
    assert package is not None
    attempts = record["changes"][0]["attempts"]
    assert [attempt["failed"] for attempt in attempts] == ["C5b", "C6c", None]
    assert detail(attempts[0], "C5b")["failed"][0]["rendered_note"] == replay.NO_RENDERED_NOTE
    assert detail(attempts[1], "C6c")["first_exception"] is None
    serialized = json.dumps({"requests": ctx.roles.wire, "record": record, "next": engineer.payload(ctx)})
    assert GENERATED not in serialized
    assert any(GENERATED in args[0].get("question", "") for _, _, args in workers.calls)


def test_unshown_lint_and_direct_checks_carry_no_rendered_text():
    ctx, _ = shown_context()
    direct = engineer.check(change(ctx, TABLE, tests=[matches(ctx)]), ctx)
    assert detail(direct, "C5b")["failed"][0]["actual"]["status"] == "withheld"
    assert "rendered_note" not in detail(direct, "C5b")["failed"][0]
    advisory = engineer.check(change(ctx, TABLE, tests=[matches(ctx, claims=False)]), ctx)
    assert advisory["passed"]
    assert all("rendered_note" not in problem for problem in advisory["lint"]["problems"])


def test_shown_allowlist_rechecks_the_stored_record_identity():
    ctx, _ = shown_context()
    engineer._ask(ctx, engineer.payload(ctx), "propose")
    assert engineer._feedback_cells(ctx) == {ctx.trajectories[0]["cell"]}
    ctx.trajectories[0]["task_id"] = "tampered-run-member"
    with pytest.raises(ValueError):
        engineer._feedback_cells(ctx)


def test_exact_cell_identity_does_not_expand_to_other_cells_of_the_same_item():
    ctx, _ = shown_context()
    clone = deepcopy(ctx.trajectories[0])
    clone["cell"] = "same-item-unshown-cell"
    clone = p.record("trajectory", clone["evidence"], {
        key: value for key, value in clone.items() if key not in (p.RECORD_HASH, "version", "evidence")})
    ctx = replace(ctx, trajectories=[*ctx.trajectories, clone])
    first = change(ctx, TABLE, tests=[{**matches(ctx), "trajectory": clone["cell"]}])
    ctx.roles = WireRoles(replies(ctx, first, change(ctx, TABLE)))
    _, record = engineer.run_train(ctx)
    failure = detail(record["changes"][0]["attempts"][0], "C5b")["failed"][0]
    assert failure["actual"]["status"] == "withheld" and "rendered_note" not in failure


def test_rendered_feedback_is_capped_without_changing_raw_actual():
    ctx, _ = shown_context()
    source = EMPTY.replace("return {}", 'return {"table": [["v" * 40, "w" * 40] for _ in range(20)]}')
    first = change(ctx, source, tests=[claim(ctx, holds="missing")])
    ctx.roles = WireRoles(replies(ctx, first, change(ctx, GOOD)))
    _, record = engineer.run_train(ctx)
    failure = detail(record["changes"][0]["attempts"][0], "C5b")["failed"][0]
    assert len(failure["rendered_note"]) == 1500
    assert len(failure["actual"]["value"]) == 1500


def test_import_time_prompt_sample_is_the_real_renderer_output():
    expected = notes.render(engineer.RENDER_SAMPLE_FIELDS_V25, bench="zebralogic",
                            header=engineer.RENDER_SAMPLE_HEADER_V25)
    assert expected == engineer.RENDER_SAMPLE_V25
    assert len(engineer.RENDER_SAMPLE_FIELDS_V25["facts"]) == 2
    assert [len(row) for row in engineer.RENDER_SAMPLE_FIELDS_V25["table"]] == [2, 2, 2]
    assert len(engineer.RENDER_SAMPLE_FIELDS_V25["warnings"]) == 1
    for system in (engineer.ENGINEER_SYSTEM_V25, engineer.ENGINEER_SYSTEM_SINGLE_V25,
                   engineer.ENGINEER_SYSTEM_ZPC_V25, engineer.ENGINEER_SYSTEM_SINGLE_ZPC_V25):
        assert expected in system and "at most 16000 bytes" in system
        assert "other benches render the same way" in system and "notes_coverage" in system
        assert "at most 10000 bytes" not in system


def sized_source(size):
    return GOOD + "#" + "x" * (size - len(GOOD.encode("utf-8")) - 1)


@pytest.mark.parametrize("configuration,size,passed", [(V25, 15999, True), (V25, 16001, False),
                                                       (p.ZEBRA_PC_V2, 15999, False)])
def test_new_source_cap_is_configuration_specific(configuration, size, passed):
    ctx, _ = shown_context(configuration=configuration)
    report = engineer.check(change(ctx, sized_source(size)), ctx)
    assert report["passed"] is passed
    if not passed:
        assert report["failed"] == "C3"
        measured = detail(report, "C3")
        assert measured["measured"]["source_bytes"] == size
        assert ("bytes_to_remove" in measured) is (configuration == V25)


@pytest.mark.parametrize("mode", ["train", "single"])
def test_actual_size_fix_feedback_states_removal_and_ninety_percent_target(mode):
    ctx, _ = shown_context(mode=mode)
    first, fixed = change(ctx, sized_source(16001)), change(ctx)
    ctx.roles = WireRoles(replies(ctx, first, fixed))
    _, record = engineer.run_train(ctx) if mode == "train" else engineer.run(ctx)
    fix = next(row[1] for row in ctx.roles.seen if row[1].get("request") == "fix")
    found = fix["failed"]["detail"]
    assert found["bytes_to_remove"] == 1 and found["recommended_source_bytes"] == 14400
    assert "at least 1 source bytes" in found["fix_hint"] and "90%" in found["fix_hint"]
    assert found["caps"]["source_bytes"] == 16000 and found["caps"]["package_source_bytes"] == 64000


@pytest.mark.parametrize("update", [{"items": True}, {"with_notes": 4}, {"faults": -1},
    {"fields": {"facts": 0}}, {"fields": {"facts": 4, "table": 0, "candidates": 0, "warnings": 0, "bindings": 0}},
    {"text": "not counts"}])
def test_coverage_validation_rejects_text_shape_and_impossible_counts(update):
    valid = {"items": 3, "with_notes": 2, "fields": {"facts": 1, "table": 1, "candidates": 0,
             "warnings": 0, "bindings": 0}, "faults": 1}
    assert engineer._coverage_ok(valid, 3)
    assert not engineer._coverage_ok({**valid, **update}, 3)
