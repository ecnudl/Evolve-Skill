"""Independent reader review regressions; inherited metadata/source are never rewritten."""
import json
from types import SimpleNamespace

import pytest

from skillopt.execskill import engineer, engineer_reader as reader
from skillopt.execskill.package import FIXTURE, Package
from tests.test_execskill_v28_execution import procedure


def fixture():
    incumbent = procedure()
    return incumbent, SimpleNamespace(mode="train", parent=Package((incumbent,), "fixture", FIXTURE))


def test_incumbent_id_derives_revision_target_and_inherits_source_byte_for_byte():
    incumbent, ctx = fixture()
    results = reader.read(json.dumps({"changes": [{"id": incumbent.id}]}), ctx)
    assert len(results) == 1 and results[0]["error"] is None
    result = results[0]
    assert result["source"] == incumbent.source
    assert result["entry"]["kind"] == "revision" and result["entry"]["revises"] == incumbent.id
    assert result["entry"]["description"] == incumbent.description
    assert {row["rule"] for row in result["repairs"]} >= {"derived", "inherited_source", "inherited_parent"}


def test_missing_source_prefers_fixed_change_over_incumbent():
    incumbent, ctx = fixture()
    source = incumbent.source + "\n# new source bytes deliberately preserved\n"
    fixed = engineer.Change(1, "revision", {"kind": "revision", "revises": incumbent.id,
                                           "description": "Changed description"}, source, "a" * 64)
    result = reader.read('{"changes":[{}]}', ctx, fix_change=fixed)[0]
    assert result["error"] is None
    assert result["source"] == source
    assert result["entry"]["description"] == "Changed description"
    assert result["entry"]["hooks"] == list(incumbent.hooks)
    assert result["entry"]["revises"] == incumbent.id


@pytest.mark.parametrize("text", ['{"x": NaN}', '{"x": Infinity}', '{"x": -Infinity}',
    '{"x": 1e999}', '{"x": -1e999}', '{"x": 1, "x": 2}', "{'x': 1, 'x': 2,}"])
def test_nonfinite_and_ambiguous_json_never_enters_schema(text):
    with pytest.raises(reader.Unusable):
        reader.tolerant_json(text)


def test_misplaced_property_kind_and_value_share_the_generic_schema_relocation():
    test = {"id": "t", "trajectory": "trajectory", "hook": "before_call", "kind": "note_contains",
            "value": "Public clue", "claims_fix": False, "nonvacuity": {"mutation": None, "withheld_expect": False}}
    repairs = []
    normalized = reader.normalize(test, reader.test_schema(test), repairs=repairs)
    assert normalized["property"] == {"kind": "note_contains", "value": "Public clue"}
    assert {row["path"] for row in repairs if row["rule"] == "relocated"} == {"$.kind", "$.value"}


def test_extreme_json_nesting_is_an_unusable_reply_not_host_exception():
    with pytest.raises(reader.Unusable):
        reader.tolerant_json("[" * 20_000 + "0" + "]" * 20_000)
