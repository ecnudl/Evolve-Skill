"""v2.7 replay-format help: authored tests only, with frozen default diagnostics and no worker/model calls."""
from copy import deepcopy
import json
import re
from types import SimpleNamespace

import pytest

from skillopt.execskill import replay
from tests.test_execskill_zpc_pipeline import offline


def case(*, hook="before_call", prop=None, cell="cell-own", **changes):
    return {"id": "own-test", "trajectory": cell, "hook": hook,
            "property": prop or {"kind": "note_matches", "value": ["House 1", "House 2"]},
            "claims_fix": True, "nonvacuity": {"withheld_expect": False, "mutation": None}, **changes}


def context(test, *, bench="zebralogic"):
    procedure = SimpleNamespace(hooks=("applies", "before_call", "bindings", "sheet_feedback",
                                        "alf_before_step", "alf_after_step"), replay_tests=(test,))
    entries = {"cell-own": {"cell": "cell-own", "bench": bench, "item": "PRIVATE_ITEM_SENTINEL",
                            "view": {"question": "PRIVATE_QUESTION_SENTINEL"}, "token": "fail"}}
    return procedure, entries


def explain(test, reason, *, bench="zebralogic"):
    procedure, entries = context(test, bench=bench)
    assert replay.validate_test(test, procedure, entries) == reason
    found = replay.test_validation_feedback(test, reason, procedure=procedure, entry=entries["cell-own"])
    assert set(found) == {"evaluated", "validation_explanation"} and found["evaluated"] is False
    assert "not evaluated" in found["validation_explanation"] and "malformed" in found["validation_explanation"]
    assert len(found["validation_explanation"]) <= replay.VALIDATION_EXPLANATION_CHARS
    assert "PRIVATE_" not in json.dumps(found)
    assert found == replay.test_validation_feedback(deepcopy(test), reason, procedure=procedure,
                                                     entry=entries["cell-own"])
    return found["validation_explanation"]


@pytest.mark.parametrize("count", [6, 10])
def test_real_v4_fragment_counts_are_format_errors_despite_correct_recorded_output(count, monkeypatch):
    fragments = ["House %d: value%d" % (index, index) for index in range(1, count + 1)]
    test = case(prop={"kind": "note_matches", "value": fragments})
    procedure, entries = context(test)
    note = " | ".join(fragments)
    outcomes = {"cell-own": replay.Outcome("cell-own", "zebralogic", applies=True,
        notes=[{"hook": "before_call", "step": None, "text": note}])}
    actual = {"cell-own": [{"hook": "before_call", "step": None, "status": "returned", "value": note}]}
    assert replay.holds(test["property"], test["hook"], outcomes["cell-own"])
    def no_evaluation(*args):
        pytest.fail("A malformed replay test must not evaluate its property")
    monkeypatch.setattr(replay, "holds", no_evaluation)
    before = deepcopy((test, entries, outcomes, actual))
    legacy = replay.claimed_tests(procedure, entries, outcomes, actual, shown_cells={"cell-own"})
    explicit = replay.claimed_tests(procedure, entries, outcomes, actual, shown_cells={"cell-own"},
                                    validation_feedback=False)
    enhanced = replay.claimed_tests(procedure, entries, outcomes, actual, shown_cells={"cell-own"},
                                    validation_feedback=True)
    assert legacy == explicit == (False, {"claimed": 1, "failed": [{"id": "own-test", "hook": "before_call",
        "property": test["property"], "reason": "value", "actual": {"status": "returned", "value": note}}]})
    failure = enhanced[1]["failed"][0]
    assert failure["evaluated"] is False and failure["actual"] == legacy[1]["failed"][0]["actual"]
    assert "%d fragments; 1-5 allowed, each 1-200 characters" % count in failure["validation_explanation"]
    assert {key: value for key, value in failure.items() if key not in
            ("evaluated", "validation_explanation")} == legacy[1]["failed"][0]
    assert (test, entries, outcomes, actual) == before


@pytest.mark.parametrize("test,reason,part,bench", [
    (case(extra="own"), "keys", "exactly {claims_fix,hook,id,nonvacuity,property,trajectory}", "zebralogic"),
    ([], "keys", "observed []", "zebralogic"),
    (case(id="z 1"), "id", "id 'z 1' does not match [A-Za-z0-9][A-Za-z0-9_.-]{0,39}", "zebralogic"),
    (case(cell="own-unregistered-cell"), "trajectory_not_in_scope", "'own-unregistered-cell'", "zebralogic"),
    (case(hook="invented"), "hook_or_kind", "hook 'invented'", "zebralogic"),
    (case(prop={"kind": "python", "value": "own expression"}), "hook_or_kind", "python", "zebralogic"),
    (case(prop={"kind": "note_contains", "value": "own", "step": 0}), "property_shape", "forbidden", "zebralogic"),
    (case(hook="applies", prop={"kind": "note_contains", "value": "own"}), "property_shape", "allows hooks", "zebralogic"),
    (case(hook="alf_before_step", prop={"kind": "note_contains", "value": "own"}),
     "property_shape", '"step"', "alfworld"),
    (case(hook="alf_before_step", prop={"kind": "note_contains", "value": "own", "step": -1}),
     "step", "observed step -1", "alfworld"),
    (case(hook="alf_before_step", prop={"kind": "note_contains", "value": "own", "step": True}),
     "step", "not bool", "alfworld"),
    (case(hook="alf_before_step", prop={"kind": "note_contains", "value": "own", "step": 0}),
     "step", "benchmark 'zebralogic'", "zebralogic"),
    (case(claims_fix="yes"), "nonvacuity", "claims_fix 'yes' (str)", "zebralogic"),
    (case(nonvacuity={"withheld_expect": True, "mutation": None}), "nonvacuity", "withheld_expect=false", "zebralogic"),
    (case(nonvacuity={"withheld_expect": False, "mutation": None, "extra": 1}), "nonvacuity", "exactly", "zebralogic"),
    (case(nonvacuity={"withheld_expect": False, "mutation": {"own": 1}}), "mutation", '"own": 1', "zebralogic"),
    (case(nonvacuity={"withheld_expect": False, "mutation": "nothing_happens"}),
     "mutation", "'nothing_happens'", "zebralogic"),
    (case(hook="applies", prop={"kind": "applies_true"}), "predicate_needs_mutation", "non-null", "zebralogic"),
])
def test_every_validation_reason_identifies_rule_and_observed_authored_value(test, reason, part, bench):
    assert part in explain(test, reason, bench=bench)


@pytest.mark.parametrize("hook,prop,part,bench", [
    ("before_call", {"kind": "note_matches", "value": []}, "0 fragments", "zebralogic"),
    ("before_call", {"kind": "note_matches", "value": "own"}, "non-list str", "zebralogic"),
    ("before_call", {"kind": "note_matches", "value": [""]}, "[0]", "zebralogic"),
    ("before_call", {"kind": "note_matches", "value": ["x" * 201]}, "[201]", "zebralogic"),
    ("before_call", {"kind": "note_matches", "value": [7]}, '["int"]', "zebralogic"),
    ("before_call", {"kind": "note_contains", "value": "x" * 201}, "201 characters", "zebralogic"),
    ("before_call", {"kind": "note_contains", "value": None}, "NoneType null", "zebralogic"),
    ("alf_before_step", {"kind": "discourage_contains", "step": 0, "value": ""}, "0 characters", "alfworld"),
    ("alf_before_step", {"kind": "discourage_excludes", "step": 0, "value": 1}, "int 1", "alfworld"),
    ("bindings", {"kind": "binding_equals", "name": "", "value": "own"}, "name 0 characters", "searchqa"),
    ("bindings", {"kind": "binding_equals", "name": "own", "value": 3}, "value int 3", "searchqa"),
    ("sheet_feedback", {"kind": "repair_requested", "value": 1}, "boolean", "spreadsheetbench"),
    ("alf_after_step", {"kind": "state_equals", "key": "", "value": 1, "step": 0}, "observed key 0", "alfworld"),
    ("alf_after_step", {"kind": "state_equals", "key": "own", "value": "é" * 34, "step": 0},
     "serialized value length 206", "alfworld"),
])
def test_all_property_value_branches_report_lengths_types_and_actual_json_character_units(hook, prop, part, bench):
    assert part in explain(case(hook=hook, prop=prop), "value", bench=bench)


@pytest.mark.parametrize("count", [0, 9])
def test_test_count_feedback_matches_actual_evaluator_without_running_workers(count):
    tests = [case(id="own-%d" % number) for number in range(count)]
    procedure, entries = context(None)
    procedure.replay_tests = tests
    advice = replay.run_tests(procedure, entries, {}, lambda *args: pytest.fail("No workers for a count error"))
    assert advice == {"check": "C7", "passed": False,
                      "problems": [{"reason": "test_count", "detail": count}], "tests": []}
    found = replay.test_validation_feedback(tests, "test_count")
    assert found["evaluated"] is False and "observed %d" % count in found["validation_explanation"]
    assert "1-8 tests" in found["validation_explanation"] and "not a procedure-output verdict" in found["validation_explanation"]


@pytest.mark.parametrize("tests,part", [
    (None, "NoneType null"), ({"own": 1}, "must be a list"),
    ([case(), "own"], '[2, "str"]'),
    ([case(id="")], '[1, ""]'), ([case(id=3)], "[1, 3]"),
    ([case(), case()], "duplicated IDs"),
    ([case(hook="unknown-hook")], "unknown-hook"),
])
def test_package_list_failures_explain_the_first_admission_rule(tests, part):
    found = replay.test_list_feedback(tests, hooks=("applies", "before_call"))
    assert found["evaluated"] is False and part in found["validation_explanation"]
    assert "not evaluated" in found["validation_explanation"]


@pytest.mark.parametrize("tests", [[], (), [case()], [case(id="z 1")],
                                    [case(id="own-%d" % n) for n in range(9)]])
def test_package_list_help_does_not_invent_earlier_pattern_or_count_gates(tests):
    assert replay.test_list_feedback(tests, hooks=("applies", "before_call")) is None


def test_limits_paragraph_contains_every_enforced_table_bound_and_caller_distinction():
    paragraph = replay.test_format_limits()
    assert paragraph.startswith("Replay-test format limits (v2.7):") and 1500 < len(paragraph) < 2700
    assert "exactly {%s}" % ",".join(replay.TEST_KEYS) in paragraph
    assert replay.TEST_ID.pattern in paragraph
    assert "1-%d tests" % replay.MAX_TESTS in paragraph
    assert "1-%d literal fragments" % replay.MAX_FRAGMENTS in paragraph
    assert "1-%d characters" % replay.MAX_PROPERTY_TEXT in paragraph
    assert "at most %d characters, not bytes" % replay.MAX_PROPERTY_TEXT in paragraph
    assert "count errors are advisory" in paragraph and "empty list is allowed" in paragraph
    for kind, (hooks, keys) in replay.PROPERTY_KINDS.items():
        assert "%s: %s, keys {%s}" % (kind, "/".join(hooks), ",".join(("kind", *keys))) in paragraph
    for mutation, benches in replay.SUPPORTED_MUTATIONS.items():
        assert "%s (%s)" % (mutation, "/".join(benches)) in paragraph


@pytest.mark.parametrize("name,value,expected", [
    ("MAX_TESTS", 3, "1-3 tests"), ("MAX_FRAGMENTS", 6, "1-6 literal fragments"),
    ("MAX_PROPERTY_TEXT", 17, "1-17 characters"),
    ("TEST_ID", re.compile(r"changed-[0-9]{2}"), "changed-[0-9]{2}"),
    ("TEST_KEYS", ("changed",), "exactly {changed}"),
    ("PROPERTY_KINDS", {"changed_property": (("before_call",), ("changed_key",))},
     "changed_property: before_call, keys {kind,changed_key}"),
    ("SUPPORTED_MUTATIONS", {"changed_mutation": ("zebralogic",)}, "changed_mutation (zebralogic)"),
    ("STEP_HOOKS", ("changed_hook",), "required step key only for changed_hook"),
])
def test_mutating_enforced_constants_changes_generated_paragraph(name, value, expected, monkeypatch):
    before = replay.test_format_limits()
    monkeypatch.setattr(replay, name, value)
    assert replay.test_format_limits() != before and expected in replay.test_format_limits()


def test_mutated_fragment_cap_updates_validator_and_explanation_together(monkeypatch):
    test = case(prop={"kind": "note_matches", "value": ["own"] * 6})
    procedure, entries = context(test)
    assert replay.validate_test(test, procedure, entries) == "value"
    monkeypatch.setattr(replay, "MAX_FRAGMENTS", 6)
    assert replay.validate_test(test, procedure, entries) is None
    test["property"]["value"].append("own")
    assert replay.validate_test(test, procedure, entries) == "value"
    assert "7 fragments; 1-6 allowed" in replay.test_validation_feedback(test, "value")["validation_explanation"]


def test_valid_failure_keeps_existing_rendered_notes_and_reference_help_unchanged():
    test = case(prop={"kind": "note_contains", "value": "absent-own"})
    procedure, entries = context(test)
    outcomes = {"cell-own": replay.Outcome("cell-own", "zebralogic", applies=True,
        notes=[{"hook": "before_call", "step": None, "text": "shown-rendered-note"}])}
    arguments = dict(shown_cells={"cell-own"}, reference_feedback=True)
    before = replay.claimed_tests(procedure, entries, outcomes, {}, **arguments)
    after = replay.claimed_tests(procedure, entries, outcomes, {}, validation_feedback=True, **arguments)
    assert after == before and after[1]["failed"][0]["rendered_note"] == "shown-rendered-note"
    assert "evaluated" not in after[1]["failed"][0]
    test["trajectory"] = "own-missing-cell"
    before = replay.claimed_tests(procedure, entries, outcomes, {}, **arguments)
    after = replay.claimed_tests(procedure, entries, outcomes, {}, validation_feedback=True, **arguments)
    assert after[1]["failed"][0]["valid_trajectories"] == before[1]["failed"][0]["valid_trajectories"]
    assert after[1]["failed"][0]["actual"] == {"status": "withheld", "reason": "trajectory_not_shown"}
    assert "PRIVATE_QUESTION_SENTINEL" not in json.dumps(after)


def test_feedback_is_bounded_for_large_authored_values_without_reading_entry_content():
    test = case(prop={"kind": "note_contains", "value": "own" * 10000})
    description = explain(test, "value")
    assert "30000 characters" in description and len(description) <= replay.VALIDATION_EXPLANATION_CHARS
    class BenchOnly(dict):
        def get(self, key, default=None):
            assert key == "bench"
            return "zebralogic"
    result = replay.test_validation_feedback(case(nonvacuity={"withheld_expect": False, "mutation": "wrong"}),
                                               "mutation", entry=BenchOnly())
    assert "'wrong'" in result["validation_explanation"]
