"""Independent v2.7 fix-reply regressions over authored procedures and real fake-role flows."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from skillopt.execskill import engineer as e, profiles as p
from skillopt.execskill.package import with_
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import change, context
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v24_routing_review import tracker_change
from tests.test_execskill_v26_references import CELL, fixture, reference
from tests.test_execskill_zpc_pipeline import offline


NEW = ("zebra-pc-v5", "alfworld-v2")
FAILED = {"checks": [{"check": "C1", "passed": False, "detail": "Authored failure."}]}


def authored(configuration, *, mode="train"):
    if configuration.startswith("alfworld-"):
        ctx, workers = context(configuration=configuration, bench="alfworld", mode=mode)
        if mode == "train":
            ctx = replace(ctx, current=list(ctx.trajectories))
        correct = tracker_change(ctx)
    else:
        ctx, workers = fixture(configuration=configuration, mode=mode)
        correct = change(ctx, tests=[reference(ctx, CELL)])
    incorrect = deepcopy(correct)
    incorrect.entry["replay_tests"][0]["property"]["value"] = "Authored absent note fragment."
    return ctx, workers, incorrect, correct


def encoded(proposed, *, entry=None, sources=None):
    return engineer_reply({"changes": [proposed.entry if entry is None else entry]},
                          [proposed.source] if sources is None else sources)


def run_fix(ctx, original, *fix_replies):
    prefix = [engineer_reply({"findings": []}, [])] if ctx.mode == "train" else []
    ctx.roles = WireRoles(prefix + [encoded(original), *fix_replies])
    return e.run_train(ctx) if ctx.mode == "train" else e.run(ctx)


def with_parent(ctx, correct):
    built = deepcopy(correct)
    e._build(built, ctx)
    first = replace(built.procedure, id="fx-authored-parent-a")
    second = replace(built.procedure, id="fx-authored-parent-b")
    parent = with_(ctx.parent, step="D/s0-parent", add=(first, second))
    return replace(ctx, parent=parent, **({"base": parent} if ctx.mode == "train" else {}))


@pytest.mark.parametrize("configuration", NEW)
@pytest.mark.parametrize("mode", ["train", "single"])
def test_real_missing_kind_fix_shape_is_inferred_before_python_count_and_recorded(configuration, mode):
    ctx, _, incorrect, correct = authored(configuration, mode=mode)
    reply_entry = deepcopy(correct.entry)
    del reply_entry["kind"]
    package, record = run_fix(ctx, incorrect, encoded(correct, entry=reply_entry))
    assert package is not None and package.procedures[0].source == correct.source
    result = record["changes"][0]
    assert [attempt["failed"] for attempt in result["attempts"]] == ["C5b", None]
    assert result["kind"] == "new" and result["survived"]
    assert any(row["rule"] == "fix_kind_inferred" for row in result["normalized"])
    assert package.procedures[0].lineage["revises"] is None
    fix = next(json.loads(wire["user"]) for wire in ctx.roles.wire if json.loads(wire["user"]).get("request") == "fix")
    assert fix["change"]["kind"] == "new"
    if mode == "train":
        assert result["fix_replies"] == [None]


@pytest.mark.parametrize("configuration", NEW)
@pytest.mark.parametrize("mode", ["train", "single"])
def test_real_unknown_revision_of_new_maps_to_new_with_explicit_provenance(configuration, mode):
    ctx, _, incorrect, correct = authored(configuration, mode=mode)
    reply_entry = dict(correct.entry, kind="revision", revises="fx-not-in-the-parent")
    package, record = run_fix(ctx, incorrect, encoded(correct, entry=reply_entry))
    assert package is not None and record["changes"][0]["survived"]
    result = record["changes"][0]
    assert result["kind"] == "new" and result["target"] is None
    assert any(row["rule"] == "fix_revision_of_new_mapped" for row in result["normalized"])
    assert "fx-not-in-the-parent" in json.dumps(result["normalized"])
    assert package.procedures[0].lineage["parent"] is package.procedures[0].lineage["revises"] is None


@pytest.mark.parametrize("configuration", NEW)
def test_fix_normalization_keeps_earlier_hook_normalization_in_the_final_record(configuration):
    ctx, _, incorrect, correct = authored(configuration)
    incorrect.entry["hooks"] = list(reversed(incorrect.entry["hooks"]))
    missing = {key: value for key, value in correct.entry.items() if key != "kind"}
    package, record = run_fix(ctx, incorrect, encoded(correct, entry=missing))
    assert package is not None
    normalizations = record["changes"][0]["normalized"]
    assert any(row.get("field") == "hooks" for row in normalizations)
    assert any(row.get("rule") == "fix_kind_inferred" for row in normalizations)


@pytest.mark.parametrize("configuration", NEW)
def test_inferred_kind_precedes_existing_lenient_inline_source_recovery(configuration):
    ctx, _, original, correct = authored(configuration)
    missing = {key: value for key, value in correct.entry.items() if key != "kind"}
    missing["source"] = correct.source
    ctx.roles = WireRoles([encoded(correct, entry=missing, sources=[])])
    fixed, reason = e._fix(ctx, original, FAILED, attempt=1)
    assert reason is None and fixed.kind == "new" and fixed.source == correct.source
    assert "source" not in fixed.entry
    assert any(row["rule"] == "fix_kind_inferred" for row in fixed.normalized)


@pytest.mark.parametrize("configuration", NEW)
@pytest.mark.parametrize("kind", ["revision", "deletion", "narrowing"])
def test_absent_kind_infers_absent_target_but_records_the_inferred_target(configuration, kind):
    ctx, _, _, correct = authored(configuration)
    ctx = with_parent(ctx, correct)
    target = ctx.parent.order[0]
    key = "revises" if kind == "revision" else "id"
    entry = (dict(correct.entry, kind=kind, revises=target) if kind == "revision" else
             {"kind": kind, "id": target, **({"benches": [ctx.bench]} if kind == "narrowing" else {})})
    original = e.Change(1, kind, entry, correct.source if kind == "revision" else None, "a" * 64)
    omitted = {name: value for name, value in entry.items() if name not in ("kind", key)}
    ctx.roles = WireRoles([engineer_reply({"changes": [omitted]}, [correct.source] if kind == "revision" else [])])
    fixed, why = e._fix(ctx, original, FAILED, attempt=1)
    assert why is None and fixed.kind == kind and fixed.entry[key] == target
    assert any(row["rule"] == "fix_kind_inferred" for row in fixed.normalized)
    assert target in json.dumps(fixed.normalized)
    assert fixed.source == original.source


@pytest.mark.parametrize("configuration", NEW)
def test_explicit_kind_with_absent_target_is_not_silently_filled(configuration):
    ctx, _, _, correct = authored(configuration)
    ctx = with_parent(ctx, correct)
    original = e.Change(1, "revision", dict(correct.entry, kind="revision", revises=ctx.parent.order[0]),
                        correct.source, "a" * 64)
    entry = {key: value for key, value in original.entry.items() if key != "revises"}
    ctx.roles = WireRoles([encoded(correct, entry=entry)])
    fixed, why = e._fix(ctx, original, FAILED, attempt=1)
    assert fixed is None and why == "another kind or target than the change to fix"


@pytest.mark.parametrize("configuration", NEW)
def test_real_revision_to_known_parent_stays_rejected_and_next_reply_receives_reason(configuration):
    ctx, _, incorrect, correct = authored(configuration)
    ctx = with_parent(ctx, correct)
    known = dict(correct.entry, kind="revision", revises=ctx.parent.order[0])
    package, record = run_fix(ctx, incorrect, encoded(correct, entry=known), encoded(correct))
    assert package is not None
    reason = "another kind or target than the change to fix"
    assert record["changes"][0]["fix_replies"] == [reason, None]
    fixes = [payload for _, payload, _ in ctx.roles.seen if payload.get("request") == "fix"]
    assert fixes[1]["previous_reply"] == reason
    assert not any(row.get("rule") == "fix_revision_of_new_mapped"
                   for row in record["changes"][0].get("normalized", []))


@pytest.mark.parametrize("configuration", NEW)
@pytest.mark.parametrize("absent_kind", [False, True])
def test_revision_cannot_change_to_a_different_known_parent_target(configuration, absent_kind):
    ctx, _, _, correct = authored(configuration)
    ctx = with_parent(ctx, correct)
    original = e.Change(1, "revision", dict(correct.entry, kind="revision", revises=ctx.parent.order[0]),
                        correct.source, "a" * 64)
    wrong = dict(original.entry, revises=ctx.parent.order[1])
    if absent_kind:
        wrong.pop("kind")
    ctx.roles = WireRoles([encoded(correct, entry=wrong)])
    fixed, why = e._fix(ctx, original, FAILED, attempt=1)
    assert fixed is None and why == "another kind or target than the change to fix"


@pytest.mark.parametrize("configuration", NEW)
@pytest.mark.parametrize("python_blocks", [0, 1])
def test_explicit_null_kind_is_never_inferred(configuration, python_blocks):
    ctx, workers, original, correct = authored(configuration)
    ctx.roles = WireRoles([encoded(correct, entry=dict(correct.entry, kind=None),
                                   sources=[correct.source] * python_blocks)])
    fixed, why = e._fix(ctx, original, FAILED, attempt=1)
    assert fixed is None and why
    assert why.startswith("unparseable: code_blocks:") if python_blocks else why == "another kind or target than the change to fix"
    assert not workers.calls


@pytest.mark.parametrize("configuration", NEW)
def test_multichange_fix_never_infers_kind_or_maps_revision(configuration):
    ctx, workers, original, correct = authored(configuration)
    entries = [{key: value for key, value in correct.entry.items() if key != "kind"},
               dict(correct.entry, kind="revision", revises="fx-unknown")]
    reply = engineer_reply({"changes": entries}, [correct.source])
    normalizations = []
    parsed, sources = e.parse(reply, lenient=True, fix_change=original, parent_ids=(),
                              normalizations=normalizations, diagnostics=True)
    assert "kind" not in parsed[0] and parsed[1]["kind"] == "revision" and not normalizations
    assert len(sources) == 1
    ctx.roles = WireRoles([reply])
    fixed, why = e._fix(ctx, original, FAILED, attempt=1)
    assert fixed is None and why == "changes: 2, expected exactly the one change"
    assert not workers.calls


@pytest.mark.parametrize("configuration", NEW)
@pytest.mark.parametrize("python_blocks", [0, 2])
def test_real_code_count_failure_is_bounded_and_reaches_next_fix_as_previous_reply(configuration, python_blocks):
    ctx, _, incorrect, correct = authored(configuration)
    missing = {key: value for key, value in correct.entry.items() if key != "kind"}
    wrong_count = encoded(correct, entry=missing, sources=[correct.source] * python_blocks)
    package, record = run_fix(ctx, incorrect, wrong_count, encoded(correct, entry=missing))
    assert package is not None
    reason, success = record["changes"][0]["fix_replies"]
    assert success is None and reason.startswith("unparseable: code_blocks:") and len(reason) <= 600
    assert "%d python block(s)" % python_blocks in reason and "1 coded change(s)" in reason
    assert "kind" in reason and "python" in reason
    fixes = [payload for _, payload, _ in ctx.roles.seen if payload.get("request") == "fix"]
    assert fixes[1]["previous_reply"] == reason
    assert any(row["rule"] == "fix_kind_inferred" for row in record["changes"][0]["normalized"])


@pytest.mark.parametrize("configuration", NEW)
@pytest.mark.parametrize("reply,legacy,fragment", [
    ("Authored prose only.", "manifest_blocks:0", "json"),
    ('```json\n{"changes": [}\n```', "manifest_json", "JSON"),
    ('```json\n{"changes": "authored"}\n```', "manifest_shape", "changes"),
])
def test_other_fix_parse_errors_are_specific_bounded_and_proposal_parser_stays_exact(configuration, reply, legacy, fragment):
    ctx, _, original, _ = authored(configuration)
    with pytest.raises(e.Unparseable) as caught:
        e.parse(reply)
    assert str(caught.value) == legacy
    ctx.roles = WireRoles([reply])
    fixed, reason = e._fix(ctx, original, FAILED, attempt=1)
    assert fixed is None and reason.startswith("unparseable: " + legacy)
    assert fragment.lower() in reason.lower() and len(reason) <= 600
    assert reason != "unparseable: " + legacy


@pytest.mark.parametrize("configuration", NEW)
def test_diagnostic_and_mapped_target_text_stay_bounded_for_large_authored_values(configuration):
    ctx, _, original, correct = authored(configuration)
    huge = "authored-own-value-" * 5000
    ctx.roles = WireRoles([encoded(correct, entry=dict(correct.entry, kind=huge))])
    fixed, reason = e._fix(ctx, original, FAILED, attempt=1)
    assert fixed is None and reason.startswith("unparseable: code_blocks:") and len(reason) <= 600
    ctx.roles = WireRoles([encoded(correct, entry=dict(correct.entry, kind="revision", revises=huge))])
    fixed, reason = e._fix(ctx, original, FAILED, attempt=1)
    assert reason is None and fixed.kind == "new" and "revises" not in fixed.entry
    row = next(row for row in fixed.normalized if row["rule"] == "fix_revision_of_new_mapped")
    assert all(len(value) <= 200 for value in row.values() if isinstance(value, str))
    assert huge not in json.dumps(fixed.to_json())


@pytest.mark.parametrize("configuration", NEW)
@pytest.mark.parametrize("mode", ["train", "single"])
def test_missing_kind_proposal_is_still_unparseable_and_only_the_fix_path_infers(configuration, mode):
    ctx, _, _, correct = authored(configuration, mode=mode)
    missing = {key: value for key, value in correct.entry.items() if key != "kind"}
    prefix = [engineer_reply({"findings": []}, [])] if mode == "train" else []
    ctx.roles = WireRoles(prefix + [encoded(correct, entry=missing), encoded(correct)])
    package, record = e.run_train(ctx) if mode == "train" else e.run(ctx)
    assert package is not None
    assert record["proposals"][0]["parsed"] is False and record["proposals"][0]["reason"] == "code_blocks"
    assert record["proposals"][1]["parsed"] is True
    assert not any(row.get("rule", "").startswith("fix_") for row in record["changes"][0].get("normalized", []))


@pytest.mark.parametrize("configuration", [name for name in p.CONFIGURATIONS if name not in NEW and not p.is_v28(name)])
def test_older_fix_reply_shapes_and_error_strings_stay_exact(configuration):
    ctx, _, original, correct = authored(configuration)
    missing = {key: value for key, value in correct.entry.items() if key != "kind"}
    ctx.roles = WireRoles([encoded(correct, entry=missing)])
    fixed, reason = e._fix(ctx, original, FAILED, attempt=1)
    assert fixed is None and reason == "unparseable: code_blocks"
    ctx.roles = WireRoles([encoded(correct, entry=dict(correct.entry, kind="revision", revises="fx-unknown"))])
    fixed, reason = e._fix(ctx, original, FAILED, attempt=1)
    assert fixed is None and reason == "another kind or target than the change to fix"
