"""Authored v2.8 format shapes, including schema extension without reader patches."""
import json
from dataclasses import replace

import pytest

from skillopt.execskill import engineer as e, engineer_reader as reader, profiles as p
from skillopt.execskill.package import with_
from tests.execskill_fakes import engineer_reply
from tests.test_execskill_v24_engineer import GOOD, change, context, claim


def setup(configuration=p.ZEBRA_PC_V6):
    ctx, _ = context(configuration=configuration)
    return ctx, change(ctx)


def parsed(ctx, proposed, entry=None, sources=None):
    result = reader.read(engineer_reply({"changes": [proposed.entry if entry is None else entry]},
                                       [proposed.source] if sources is None else sources), ctx)
    assert result[0]["error"] is None
    return result[0]


@pytest.mark.parametrize("missing", ["kind", "description", "hooks", "max_note_chars", "excluded_benches"])
def test_missing_fields_derive_or_default_and_record_repairs(missing):
    ctx, c = setup()
    entry = {key: value for key, value in c.entry.items() if key != missing}
    result = parsed(ctx, c, entry)
    assert result["entry"][missing] is not None
    assert any(row["path"] == "$." + missing for row in result["repairs"])
    if missing == "hooks":
        assert result["entry"]["hooks"] == ["applies", "before_call"]


def test_unseen_required_field_uses_same_schema_walker(monkeypatch):
    ctx, c = setup()
    monkeypatch.setitem(e.PROCEDURE_KEYS, "future_required_field", str)
    original = e._keys
    monkeypatch.setattr(e, "_keys", lambda kind, train=False: (
        original(kind, train)[0] | {"future_required_field"}, original(kind, train)[1] | {"future_required_field"}))
    result = parsed(ctx, c)
    assert result["entry"]["future_required_field"] == ""
    document = reader.schema_document()
    assert document["kinds"]["new"]["future_required_field"] == {"type": "str", "required": True, "default": ""}


def test_unknown_keys_ignored_at_every_level_with_provenance():
    ctx, c = setup()
    c.entry.update(claims_fix_note="Authored explanation", future_extra=17)
    test = dict(claim(ctx), unseen_test_key=1)
    test["property"]["unknown_property"] = 2
    c.entry["replay_tests"] = [test]
    result = parsed(ctx, c)
    assert "claims_fix_note" not in result["entry"]
    paths = [row["path"] for row in result["repairs"] if row["rule"] == "unknown_key_ignored"]
    assert "$.claims_fix_note" in paths and "$.replay_tests[0].property.unknown_property" in paths


def test_misplaced_keys_move_to_unique_schema_place():
    fields = reader.test_schema({"hook": "alf_before_step", "property": {"kind": "note_contains"}})
    repairs = []
    result = reader.normalize({"id": "test", "hook": "alf_before_step", "step": 3,
        "property": {"kind": "note_contains", "value": "x"}, "mutation": "nothing_happens"}, fields, repairs=repairs)
    assert result["property"]["step"] == 3 and "step" not in result
    assert result["nonvacuity"]["mutation"] == "nothing_happens"
    assert len([row for row in repairs if row["rule"] == "relocated"]) == 2


@pytest.mark.parametrize("language", ["", "py", "python", "text"])
def test_source_taken_from_any_fenced_language(language):
    ctx, c = setup()
    reply = "```json\n" + json.dumps({"changes": [c.entry]}) + "\n```\n```" + language + "\n" + GOOD + "```"
    result = reader.read(reply, ctx)[0]
    assert result["error"] is None and result["source"] == GOOD


def test_several_blocks_choose_declared_or_derived_hooks():
    ctx, c = setup()
    result = parsed(ctx, c, sources=["def unrelated():\n    return None", GOOD, "An explanation."])
    assert result["source"].strip() == GOOD.strip()
    entry = {key: value for key, value in c.entry.items() if key != "hooks"}
    assert parsed(ctx, c, entry, ["def unrelated():\n    return None", GOOD])["entry"]["hooks"] == ["applies", "before_call"]


@pytest.mark.parametrize("text", [
    '{"value": [1, 2,],}',
    "{'value': [1, 2], // comment\n}",
    '{/* comment */ "value": [1, 2]}',
])
def test_vetted_literal_json_extensions(text):
    value, repairs = reader.tolerant_json(text)
    assert value == {"value": [1, 2]} and repairs[0]["rule"] == "tolerant_json"


def test_literals_inside_strings_are_not_rewritten():
    value, _ = reader.tolerant_json("{'url': 'https://host/x', 'text': 'true null /* literal */', 'flag': true,}")
    assert value == {"url": "https://host/x", "text": "true null /* literal */", "flag": True}


@pytest.mark.parametrize("text", ['{"a":1,"a":2}', '{"a":NaN}', '{"a": __import__("os")}', '{"a": [1,2}', '{"a": {1,2}}'])
def test_ambiguous_non_json_or_truncated_data_are_not_evaluated(text):
    with pytest.raises(reader.Unusable):
        reader.tolerant_json(text)


def test_fix_then_incumbent_then_schema_default_inheritance():
    ctx, c = setup()
    e._build(c, ctx)
    old = replace(c.procedure, id="fx-reader-parent", header="Parent header")
    parent = with_(ctx.parent, step="D/s0-parent", add=(old,))
    ctx = replace(ctx, parent=parent, base=parent)
    revision = e.Change(1, "revision", {"kind": "revision", "revises": old.id, "description": "Fixed description"}, GOOD, "a" * 64)
    reply = engineer_reply({"changes": [{}]}, [])
    result = reader.read(reply, ctx, fix_change=revision)[0]
    assert result["error"] is None
    assert result["entry"]["description"] == "Fixed description"
    assert result["entry"]["header"] == "Parent header"
    assert result["entry"]["kind"] == "revision" and result["source"] == GOOD
    rules = {row["rule"] for row in result["repairs"]}
    assert {"inherited_change", "inherited_parent", "inherited_source"} <= rules


def test_proposal_missing_kind_derives_revision_from_incumbent_id():
    ctx, c = setup()
    e._build(c, ctx)
    ctx = replace(ctx, parent=with_(ctx.parent, step="D/s0-parent", add=(c.procedure,)))
    result = parsed(ctx, c, {"revises": c.procedure.id})
    assert result["entry"]["kind"] == "revision"


def test_generated_schema_example_can_be_read():
    ctx, _ = setup()
    document = reader.schema_document()
    assert reader.read(document["example"], ctx)[0]["error"] is None
    assert all({"type", "required", "default"} <= set(spec)
               for fields in document["kinds"].values() for spec in fields.values())


def test_malformed_test_list_never_makes_the_program_unparseable():
    ctx, c = setup()
    for malformed in (None, 7, "bad test", {"bogus": True}):
        result = parsed(ctx, c, dict(c.entry, replay_tests=malformed))
        built = e.Change(1, "new", result["entry"], result["source"], "a" * 64)
        report = e.check(built, ctx)
        assert report["passed"] and built.procedure.replay_tests == () and report["dropped_tests"]


@pytest.mark.parametrize("malformed", [None, 7, True])
def test_wrong_declared_hook_type_returns_parse_problem_instead_of_raising(malformed):
    ctx, c = setup()
    results = reader.read(engineer_reply({"changes": [dict(c.entry, hooks=malformed)]}, [c.source]), ctx)
    assert "hooks" in results[0]["error"]


def test_unusable_earlier_change_does_not_shift_a_usable_siblings_source():
    ctx, c = setup()
    first = GOOD.replace('return "question" in view', 'return False')
    reply = engineer_reply({"changes": [dict(c.entry, kind="unknown"), c.entry]}, [first, GOOD])
    result = reader.read(reply, ctx)
    assert result[0]["error"]
    assert result[1]["error"] is None and result[1]["source"].strip() == GOOD.strip()


@pytest.mark.parametrize("text", ['{"text":"\\ud800"}', '\ud800'])
def test_non_utf8_unicode_is_an_unusable_reply_not_a_host_crash(text):
    with pytest.raises(reader.Unusable):
        reader.tolerant_json(text)


def test_generic_relocation_handles_sibling_objects_and_unknown_wrappers():
    fields = reader.test_schema({"hook": "alf_before_step", "property": {"kind": "note_contains"}})
    log = []
    result = reader.normalize({"hook": "alf_before_step", "property": {"kind": "note_contains", "value": "x"},
                              "nonvacuity": {"step": 4}, "metadata": {"id": "authored"}}, fields, repairs=log)
    assert result["property"]["step"] == 4 and result["id"] == "authored"
    assert "step" not in result["nonvacuity"]
    assert any(row["path"] == "$.nonvacuity.step" and row["to"] == "$.property.step" for row in log)


def test_generic_relocation_never_reinterprets_opaque_state_data():
    test = {"hook": "alf_after_step", "property": {"kind": "state_equals", "key": "facts",
            "value": {"step": 42, "id": "application-data", "kind": "state-data"}, "step": 1}}
    result = reader.normalize(test, reader.test_schema(test))
    assert result["property"]["value"] == test["property"]["value"]
    assert result["id"] == "" and result["property"]["step"] == 1
