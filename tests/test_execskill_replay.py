"""Replay of procedures on stored trajectories (implementation plan §8 T-REPLAY-1..4; registration §5.4 C6-C9, FA-F6,
FA-F17). Every hook runs in the real sandbox worker through FakeDocker (local subprocesses, no docker), on synthetic
sealed trajectories; every procedure is an engineering fixture. Helpers here are shared with the engineer tests."""
from __future__ import annotations

import json
import textwrap
from contextlib import contextmanager
from fractions import Fraction

import pytest

from skillopt.execskill import replay
from skillopt.execskill.errors import CleanupUnconfirmed
from skillopt.execskill.package import FIXTURE, NOTE_HOOKS, Procedure
from skillopt.execskill.protocol import NOT_RECOMMENDED_PREFIX, record
from skillopt.execskill.sandbox import client
from skillopt.execskill.sandbox.client import Limits, Worker
from tests.execskill_fakes_docker import FakeDocker

TEST_LIMITS = {kind: Limits(pids=64, memory_mb=768, cpus=0.5, address_space_mb=512, frame_bytes=1 << 20)
               for kind in client.KINDS}
SHA = "0" * 64

# ------------------------------------------------------------------------------------------------ synthetic data
QA = {
    "q1": ({"question": "Which orchard ships 17 baskets each week?",
            "context": ["The Gravenstein Orchard ships 17 baskets each week.", "Other farms ship fewer."]},
           ["Gravenstein Orchard"], "fail"),
    "q2": ({"question": "Which river floods each spring?", "context": ["The Okavango River floods each spring."]},
           ["Okavango River"], "pass"),
    "q3": ({"question": "Who wrote the Moonlight sonata?", "context": ["The sonata was published in Vienna."]},
           ["Ludwig Beethoven"], "fail"),
}
INITIAL = ("-= Welcome to TextWorld, ALFRED! =-\n\nYou are in the middle of a room. Looking quickly around you, you "
           "see a cabinet 1, a drawer 1, a drawer 2, and a countertop 1.\n\nYour task is to: put some apple on "
           "countertop.")
ADMISSIBLE = ["go to cabinet 1", "go to drawer 1", "go to drawer 2", "go to countertop 1", "open drawer 1",
              "close cabinet 1", "take apple 1 from drawer 1", "move apple 1 to countertop 1"]
EPISODE = [  # (observation seen, action, observation after)
    (INITIAL, "go to drawer 1", "You arrive at drawer 1. The drawer 1 is closed."),
    ("You arrive at drawer 1. The drawer 1 is closed.", "open drawer 1",
     "You open the drawer 1. The drawer 1 is open. In it, you see a apple 1."),
    ("You open the drawer 1. The drawer 1 is open. In it, you see a apple 1.", "close cabinet 1", "Nothing happens."),
    ("Nothing happens.", "take apple 1 from drawer 1", "You pick up the apple 1 from the drawer 1."),
    ("You pick up the apple 1 from the drawer 1.", "go to countertop 1",
     "You arrive at countertop 1. On the countertop 1, you see nothing."),
    ("You arrive at countertop 1. On the countertop 1, you see nothing.", "move apple 1 to countertop 1",
     "You move the apple 1 to the countertop 1."),
]
SHEET_VIEW = {"instruction": "Fill the Total column with the sum of Q1 and Q2.", "workbook_preview": "A1: Q1 | B1: Q2",
              "input_path": "input.xlsx", "required_output_path": "output.xlsx", "required_answer_position": "C2:C9"}


def precheck(status, exc_type=None, message=""):
    return {"version": "fivebench-execskill-v1-precheck", "evidence": FIXTURE, "status": status, "exc_type": exc_type,
            "message": message, "answer_cells": None, "reason": status}


def trajectory(cell, bench, item, token, users, *, steps=None, report=None):
    """A sealed trajectory record with the whitelisted keys (trajectories.TOP)."""
    purpose = "step" if bench == "alfworld" else "first"
    calls = [{"purpose": purpose, "system": "frozen system prompt", "user": json.dumps(user), "request_sha256": SHA,
              "receipt": {"delivery": "delivered"}} for user in users]
    return record("trajectory", FIXTURE, {
        "cell": cell, "unit": "D/s1-%s/run" % bench, "arm": "S", "arm_kind": "parent", "bench": bench, "task_id": item,
        "run": 1, "package_sha256": SHA, "route": None, "calls": calls, "replies": [None] * len(calls),
        "deciding_receipt": None, "worst_delivery": None, "logical_calls": len(calls),
        "shell": {"notes": [], "compute": None, "precheck": report, "procedure_calls": [], "faults": [],
                  "fallback": None},
        "alfworld_steps": steps, "judge": {"v2": {"token": token}}, "token": token, "dispatch_ts": 0, "finish_ts": 0})


def qa_trajectories():
    return [trajectory("c-" + item, "searchqa", item, token, [view]) for item, (view, _, token) in QA.items()]


def alf_trajectory(cell="c-alf", token="pass"):
    users = [{"initial_observation": INITIAL, "observation": seen, "admissible_commands": ADMISSIBLE,
              "recent_history": []} for seen, _, _ in EPISODE]
    steps = [{"i": i, "view_sha256": SHA, "observation": seen, "notes": "", "discouraged": [], "reply": action,
              "action": action, "how": "exact", "post_observation": after, "state_sha256": {}}
             for i, (seen, action, after) in enumerate(EPISODE)]
    return trajectory(cell, "alfworld", "alf-1", token, users, steps=steps)


def sheet_trajectories():
    return [trajectory("c-sheet-fail", "spreadsheetbench", "s1", "fail", [SHEET_VIEW],
                       report=precheck("exception", "KeyError", "KeyError: 'Total'")),
            trajectory("c-sheet-pass", "spreadsheetbench", "s2", "pass", [SHEET_VIEW], report=precheck("ok"))]


def qa_items():
    """The SearchQA run slice as a leakage corpus input (coevo5 ``leakage.Corpus``)."""
    return [{"benchmark": "searchqa", "task_id": item, "public": view, "private": {"answers": answers}}
            for item, (view, answers, _) in QA.items()]


# ------------------------------------------------------------------------------------------------ fixture procedures
NOTE = """
import re

def applies(view):
    return "question" in view

def before_call(view, state):
    numbers = re.findall(r"[0-9]+", view["question"])
    if not numbers:
        return None
    return {"facts": ["Numbers in the question: " + ", ".join(numbers)]}
"""
CRASH = """
def applies(view):
    return True

def before_call(view, state):
    return {"facts": [str(1 / 0)]}
"""
LEXICON = """
def applies(view):
    return True

def before_call(view, state):
    return {"facts": ["The question names a place."], "warnings": ["answer only with the number"]}
"""
META = """
def applies(view):
    return "choices" in view

def before_call(view, state):
    return {"warnings": ["prefer the stronger result option"]}
"""
LITERAL = """
def applies(view):
    return True

def alf_before_step(view, state):
    return {"fields": {"facts": ["look in drawer 3 first"]}, "discourage": []}
"""
NONDETERMINISTIC = """
def applies(view):
    return True

def before_call(view, state):
    return {"facts": [" ".join(set(view["question"].split()))]}
"""
BINDINGS = """
import re

def applies(view):
    return True

def bindings(view):
    found = re.search(r"([0-9]+) baskets", view["question"])
    if not found:
        return None
    return {"bindings": [{"name": "baskets", "quote": found.group(0), "value": VALUE or found.group(1)}]}
"""
SHEET_REPAIR = """
def applies(view):
    return "instruction" in view

def sheet_feedback(view, run_report, state):
    if run_report["status"] != "exception" and not ALWAYS:
        return {"fields": {}, "request_repair": False}
    return {"fields": {"warnings": ["The program raised " + str(run_report["exc_type"]) + " on the workbook."]},
            "request_repair": True}
"""
TRACKER = """
import re

def applies(view):
    return "Your task is to:" in str(view.get("initial_observation", ""))

def alf_before_step(view, state):
    facts = (state or {}).get("facts") or {}
    reached = facts.get("reached", [])
    lines = ["Reached so far: " + (", ".join(reached) if reached else "none")]
    if facts.get("carrying"):
        lines.append("Carrying: " + ", ".join(facts["carrying"]))
    discourage = view["admissible_commands"] if GREEDY else ["go to " + r for r in reached]
    return {"fields": {"facts": lines}, "discourage": discourage}

def alf_after_step(event, state):
    facts = (state or {}).get("facts") or {"reached": [], "carrying": [], "nothing_happens": 0}
    reached, carrying, count = list(facts["reached"]), list(facts["carrying"]), facts["nothing_happens"]
    action, seen = event["action"].strip(), (event["observation"] or "").strip()
    arrive = re.match(r"go to (.+)$", action)
    opened = re.match(r"open (.+)$", action)
    take = re.match(r"take (.+?) from (.+)$", action)
    move = re.match(r"move (.+?) to (.+)$", action) or re.match(r"put (.+?) (?:in/on|in|on) (.+)$", action)
    if seen.startswith("Nothing happens"):
        count += 0 if FORGETFUL else 1
    elif arrive and seen.startswith("You arrive at"):
        reached.append(arrive.group(1).strip())
    elif opened and seen.startswith("You open"):
        reached.append(opened.group(1).strip())
    elif take and seen.startswith("You pick up"):
        carrying.append(take.group(1).strip())
    elif move and seen.startswith(("You move", "You put")):
        carrying = [c for c in carrying if c != move.group(1).strip()]
        reached.append(move.group(2).strip())
    return {"facts": {"reached": sorted(set(reached)), "carrying": sorted(carrying), "nothing_happens": count}}
"""


def source(text, **constants):
    """A fixture module, with its module-level constants written first."""
    head = "".join("%s = %r\n" % item for item in sorted(constants.items()))
    return head + textwrap.dedent(text)


def test_case(cell, hook, prop, *, claims_fix=True, mutation=None, test_id="rt-1"):
    return {"id": test_id, "trajectory": cell, "hook": hook, "property": prop, "claims_fix": claims_fix,
            "nonvacuity": {"withheld_expect": False, "mutation": mutation}}


test_case.__test__ = False  # a builder, not a test


def fixture(pid, text, hooks, *, tests=(), origin="searchqa", **fields):
    notes = any(h in NOTE_HOOKS for h in hooks)
    fields = {"max_note_chars": 1000 if notes else 0, **fields}
    return Procedure(id=pid, origin=origin, description="Fixture %s." % pid, hooks=tuple(hooks), source=text,
                     evidence=FIXTURE, replay_tests=tuple(tests), **fields)


def tracker(*, greedy=False, forgetful=False, tests=()):
    return fixture("fx-alf-tracker", source(TRACKER, GREEDY=greedy, FORGETFUL=forgetful),
                   ("applies", "alf_before_step", "alf_after_step"), tests=tests, origin="alfworld",
                   state_bytes=4096)


@pytest.fixture
def fake(tmp_path):
    docker = FakeDocker(tmp_path / "containers")
    yield docker
    docker.close()


@pytest.fixture
def workers(fake, tmp_path):
    """``replay_many``'s factory: a FakeDocker-backed worker per block, closed afterwards."""
    opened = []

    @contextmanager
    def factory(package, *, kind, hashseed=0, inputs_dir=None, tag=None):
        worker = Worker(docker=fake, limits=TEST_LIMITS, scratch=tmp_path, hashseed=hashseed, tag=tag)
        opened.append(worker.start(package, kind=kind, inputs_dir=inputs_dir))
        try:
            yield worker
        finally:
            worker.close()

    yield factory
    for worker in opened:
        try:
            worker.close()
        except CleanupUnconfirmed:
            pass


def entries_of(trajectories):
    return {t["cell"]: replay.inputs_of(t) for t in trajectories}


# ---------------------------------------------------------------------------------------------------------- inputs
def test_inputs_rebuild_the_views_reports_and_events_the_shell_used():
    qa = replay.inputs_of(qa_trajectories()[0])
    assert qa["view"] == qa["request_view"] == QA["q1"][0] and qa["steps"] is None and qa["token"] == "fail"
    sheet = replay.inputs_of(sheet_trajectories()[0])
    assert sheet["view"] == SHEET_VIEW and sheet["report"]["status"] == "exception"
    alf = replay.inputs_of(alf_trajectory())
    assert alf["view"] == {"initial_observation": INITIAL, "admissible_commands_at_reset": ADMISSIBLE,
                           "task_text": "put some apple on countertop."}
    assert [s["event"]["observation"] for s in alf["steps"][:5]] == [after for _, _, after in EPISODE[:5]]
    assert alf["steps"][-1]["event"] is None and alf["steps"][-1]["action"] == "move apple 1 to countertop 1"
    unanswered = alf_trajectory()
    fields = {k: v for k, v in unanswered.items() if k not in ("version", "evidence", "record_sha256")}
    fields["alfworld_steps"] = fields["alfworld_steps"][:-1]  # the last request got no reply
    tolerant = replay.inputs_of(record("trajectory", FIXTURE, fields))
    assert tolerant["steps"][-1]["action"] is None and tolerant["steps"][-2]["event"] is not None


def test_mutations_perturb_only_their_bench_inputs():
    qa = replay.inputs_of(qa_trajectories()[0])
    assert "17" not in json.dumps(replay.mutate(qa, "strip_digits")) and "17" in qa["view"]["question"]
    sheet = replay.inputs_of(sheet_trajectories()[0])
    assert replay.mutate(sheet, "program_ok")["report"]["status"] == "ok"
    assert replay.mutate(sheet, "drop_exception_message")["report"]["message"] == ""
    alf = replay.mutate(replay.inputs_of(alf_trajectory()), "nothing_happens")
    assert {s["event"]["observation"] for s in alf["steps"] if s["event"]} == {"Nothing happens."}
    with pytest.raises(ValueError):
        replay.mutate(qa, "nothing_happens")


# ------------------------------------------------------------------------------------------------- C6 zero crash
def test_zero_crash_passes_a_deterministic_procedure_and_returns_its_outcomes(workers):
    procedure = fixture("fx-note", source(NOTE), ("applies", "before_call"))
    entries = list(entries_of(qa_trajectories()).values())
    report, outcomes = replay.zero_crash(procedure, entries, workers)
    assert report["passed"] and report["trajectories"] == 3 and report["applied"] == 3
    assert outcomes["c-q1"].note("before_call").endswith("Numbers in the question: 17")
    assert outcomes["c-q2"].notes == [] and outcomes["c-q1"].values[0][0] == "applies"


def test_zero_crash_fails_on_a_crash_and_on_hash_seed_dependence(workers):
    entries = list(entries_of(qa_trajectories()).values())
    crash, _ = replay.zero_crash(fixture("fx-crash", source(CRASH), ("applies", "before_call")), entries, workers)
    assert not crash["passed"] and crash["faults"][0]["kind"] == "crash:exception"
    unstable, _ = replay.zero_crash(fixture("fx-nondeterministic", source(NONDETERMINISTIC),
                                            ("applies", "before_call")), entries, workers)
    assert not unstable["passed"] and unstable["fault_count"] == 0 and unstable["mismatched"]
    empty, _ = replay.zero_crash(fixture("fx-note", source(NOTE), ("applies", "before_call")), [], workers)
    assert not empty["passed"]


# ------------------------------------------------------------------------------------------ T-REPLAY-1: fixed kinds
def test_replay_tests_take_only_the_fixed_property_kinds_and_shapes():
    procedure = fixture("fx-note", source(NOTE), ("applies", "before_call"))
    entries = entries_of(qa_trajectories() + [alf_trajectory()])
    good = test_case("c-q1", "before_call", {"kind": "note_contains", "value": "17"})
    assert replay.validate_test(good, procedure, entries) is None
    cases = {
        "hook_or_kind": test_case("c-q1", "before_call", {"kind": "python", "value": "lambda n: True"}),
        "property_shape": test_case("c-q1", "before_call", {"kind": "note_contains", "value": "17", "code": "x"}),
        "trajectory_not_in_scope": test_case("c-unknown", "before_call", {"kind": "note_contains", "value": "17"}),
        "predicate_needs_mutation": test_case("c-q1", "applies", {"kind": "applies_true"}),
        "mutation": test_case("c-q1", "before_call", {"kind": "note_contains", "value": "17"},
                              mutation="nothing_happens"),
        "keys": {**good, "judge": "return True"},
        "nonvacuity": {**good, "nonvacuity": {"withheld_expect": True, "mutation": None}},
    }
    for reason, case in cases.items():
        assert replay.validate_test(case, procedure, entries) == reason
    stepped = tracker()
    no_step = test_case("c-alf", "alf_before_step", {"kind": "discourage_contains", "value": "go to drawer 1"})
    assert replay.validate_test(no_step, stepped, entries) == "property_shape"
    no_step["property"]["step"] = 1
    assert replay.validate_test(no_step, stepped, entries) is None


# ------------------------------------------------------------------- T-REPLAY-2: non-vacuity (withheld, mutation)
def test_a_property_true_without_the_procedure_is_vacuous(workers):
    trajectories = qa_trajectories() + [alf_trajectory()]
    entries = entries_of(trajectories)
    tests = [test_case("c-alf", "alf_before_step", {"kind": "discourage_excludes", "value": "go to cabinet 1",
                                                    "step": 2}, test_id="rt-vacuous"),
             test_case("c-alf", "alf_before_step", {"kind": "discourage_contains", "value": "go to drawer 1",
                                                    "step": 2}, claims_fix=False, test_id="rt-real")]
    procedure = tracker(tests=tests)
    _, outcomes = replay.zero_crash(procedure, list(entries.values()), workers)
    report = replay.run_tests(procedure, entries, outcomes, workers)
    results = {r["id"]: r for r in report["tests"]}
    assert results["rt-vacuous"] == {"id": "rt-vacuous", "holds": True, "withheld": True, "mutated": None,
                                     "nonvacuous": False}
    assert results["rt-real"]["holds"] and results["rt-real"]["nonvacuous"]
    assert {"reason": "vacuous_test", "test": "rt-vacuous"} in report["problems"]
    assert {"reason": "no_fix_claim"} in report["problems"] and not report["passed"]


def test_a_predicate_test_is_judged_by_its_mutation_only(workers):
    entries = entries_of(qa_trajectories())
    always = """
def applies(view):
    return True

def before_call(view, state):
    return {"facts": ["A fixture note."]}
"""
    digits = """
import re

def applies(view):
    return re.search(r"[0-9]", view["question"]) is not None

def before_call(view, state):
    return {"facts": ["A fixture note."]}
"""
    case = test_case("c-q1", "applies", {"kind": "applies_true"}, mutation="strip_digits")
    note = test_case("c-q1", "before_call", {"kind": "note_contains", "value": "fixture note"}, test_id="rt-2")
    for text, nonvacuous in ((always, False), (digits, True)):
        procedure = fixture("fx-predicate", source(text), ("applies", "before_call"), tests=[case, note])
        _, outcomes = replay.zero_crash(procedure, list(entries.values()), workers)
        report = replay.run_tests(procedure, entries, outcomes, workers)
        first = report["tests"][0]
        assert first["holds"] and not first["withheld"] and first["nonvacuous"] is nonvacuous
        assert report["passed"] is nonvacuous


def test_note_and_binding_properties_hold_with_the_procedure_and_fail_without(workers):
    entries = entries_of(qa_trajectories())
    tests = [test_case("c-q1", "bindings", {"kind": "binding_equals", "name": "baskets", "value": "17"},
                       mutation="strip_digits"),
             test_case("c-q1", "bindings", {"kind": "note_matches", "value": ["baskets", "17", "17 baskets"]},
                       claims_fix=False, test_id="rt-2")]
    procedure = fixture("fx-bindings", source(BINDINGS, VALUE=None), ("applies", "bindings"), tests=tests)
    _, outcomes = replay.zero_crash(procedure, list(entries.values()), workers)
    report = replay.run_tests(procedure, entries, outcomes, workers)
    assert report["passed"], report
    assert report["tests"][0] == {"id": "rt-1", "holds": True, "withheld": False, "mutated": False,
                                  "nonvacuous": True}
    forged = fixture("fx-bindings", source(BINDINGS, VALUE="18"), ("applies", "bindings"), tests=tests)
    _, outcomes = replay.zero_crash(forged, list(entries.values()), workers)
    report = replay.run_tests(forged, entries, outcomes, workers)
    assert not report["passed"]
    assert any(p["reason"] == "bindings_not_verbatim" and p["kind"] == "note_not_verbatim" for p in report["problems"])


# ----------------------------------------------------------------------------------------- T-REPLAY-3: negative
def test_negative_tests_refuse_a_discouraged_winning_action_and_a_repair_on_a_passed_sheet(workers):
    alf = entries_of([alf_trajectory()])
    claim = test_case("c-alf", "alf_before_step", {"kind": "discourage_contains", "value": "go to drawer 1",
                                                   "step": 2}, claims_fix=False)
    for greedy in (False, True):
        procedure = tracker(greedy=greedy, tests=[claim])
        _, outcomes = replay.zero_crash(procedure, list(alf.values()), workers)
        found = replay.negative_tests(alf, outcomes)
        assert found == ([{"cell": "c-alf", "test": "winning_action_discouraged"}] if greedy else [])
        assert outcomes["c-alf"].steps[2]["note"].endswith(NOT_RECOMMENDED_PREFIX + (
            ", ".join(ADMISSIBLE) if greedy else "go to drawer 1"))
    sheets = entries_of(sheet_trajectories())
    tests = [test_case("c-sheet-fail", "sheet_feedback", {"kind": "repair_requested", "value": True},
                       mutation="program_ok")]
    for always in (False, True):
        procedure = fixture("fx-sheet-repair", source(SHEET_REPAIR, ALWAYS=always), ("applies", "sheet_feedback"),
                            tests=tests, origin="spreadsheetbench", requests_second_call=True)
        _, outcomes = replay.zero_crash(procedure, list(sheets.values()), workers)
        report = replay.run_tests(procedure, sheets, outcomes, workers)
        assert report["tests"][0]["holds"] and report["tests"][0]["nonvacuous"]
        assert report["tests"][0]["mutated"] is always and report["passed"] is not always
        assert ({"reason": "negative_test", "cell": "c-sheet-pass", "test": "repair_on_passed_item"}
                in report["problems"]) is always


def test_an_undeclared_repair_request_is_a_crash_fault(workers):
    sheets = list(entries_of(sheet_trajectories()).values())
    procedure = fixture("fx-sheet-repair", source(SHEET_REPAIR, ALWAYS=False), ("applies", "sheet_feedback"),
                        origin="spreadsheetbench")
    report, _ = replay.zero_crash(procedure, sheets, workers)
    assert not report["passed"] and report["faults"][0]["kind"] == "undeclared_second_call"


# ------------------------------------------------------------------------------- T-REPLAY-4: reference tracker
def test_reference_tracker_port_matches_the_d3_comparison():
    reference = replay.ReferenceTracker(INITIAL)
    assert reference.receptacles == ["cabinet 1", "drawer 1", "drawer 2", "countertop 1"]
    for _, action, after in EPISODE:
        reference.update(action, after)
    assert reference.facts() == {"reached": ["countertop 1", "drawer 1"], "carrying": [], "nothing_happens": 1}
    assert reference.visited == {"drawer 1": "nothing", "countertop 1": "apple 1"}
    facts = {"reached": ["drawer 1", "countertop 1", "drawer 1"], "carrying": [], "nothing_happens": 1}
    assert replay.facts_agree({"facts": facts}, reference.facts())
    assert not replay.facts_agree({"facts": {}}, reference.facts())
    assert not replay.facts_agree({"facts": {"seen": []}}, reference.facts())
    assert not replay.facts_agree({"facts": {**facts, "nothing_happens": 0}}, reference.facts())


def test_reference_tracker_agreement_is_computed_and_gates_state_procedures(workers):
    entries = entries_of([alf_trajectory(token="fail")])
    tests = [test_case("c-alf", "alf_after_step", {"kind": "state_equals", "step": 3, "key": "facts",
                                                   "value": {"reached": ["drawer 1"], "carrying": ["apple 1"],
                                                             "nothing_happens": 1}}, mutation="nothing_happens")]
    procedure = tracker(tests=tests)
    _, outcomes = replay.zero_crash(procedure, list(entries.values()), workers)
    assert replay.reference_tracker_agreement(entries, outcomes) == (5, 5)
    report = replay.run_tests(procedure, entries, outcomes, workers)
    assert report["passed"], report
    assert report["tracker_agreement"] == [5, 5] and report["tests"][0]["mutated"] is False
    forgetful = tracker(forgetful=True, tests=tests)
    _, outcomes = replay.zero_crash(forgetful, list(entries.values()), workers)
    agree, total = replay.reference_tracker_agreement(entries, outcomes)
    assert (agree, total) == (2, 5) and Fraction(agree, total) < replay.TRACKER_AGREEMENT
    report = replay.run_tests(forgetful, entries, outcomes, workers)
    assert {"reason": "reference_tracker", "detail": [2, 5]} in report["problems"]


# ------------------------------------------------------------------------------------------- C8 and C9 outputs
def test_format_guard_and_output_screen_report_their_faults(workers):
    entries = list(entries_of(qa_trajectories()).values())
    calc = """
def applies(view):
    return True

def before_call(view, state):
    return {"facts": ["You may compute <calc>17*2</calc> here."]}
"""
    _, outcomes = replay.zero_crash(fixture("fx-calc", source(calc), ("applies", "before_call")), entries, workers)
    assert replay.format_guard(outcomes)[0]["marker"] == "<calc" and replay.output_faults(outcomes) == []
    _, outcomes = replay.zero_crash(fixture("fx-lexicon", source(LEXICON), ("applies", "before_call")), entries,
                                    workers)
    faults = replay.output_faults(outcomes)
    assert faults and {f["kind"] for f in faults} == {"note_lexicon"} and replay.format_guard(outcomes) == []
    assert outcomes["c-q1"].note("before_call").endswith("The question names a place.")
    capped = fixture("fx-note", source(NOTE), ("applies", "before_call"), max_note_chars=20)
    _, outcomes = replay.zero_crash(capped, entries, workers)
    assert {f["kind"] for f in replay.output_faults(outcomes)} == {"note_over_declared_cap"}
