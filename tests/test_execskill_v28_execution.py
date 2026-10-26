"""v2.8 environment guarantees and note screening, using authored offline fixtures only."""
from contextlib import contextmanager
from dataclasses import replace
import json
import os
import subprocess
import sys

import pytest

from skillopt.execskill import donors, notes, placebo, policy, replay, reuse, solver
from skillopt.execskill.package import FIXTURE, Package, Procedure
from skillopt.execskill.sandbox.client import Worker, docker_command
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import FakeSandbox, Script
from tests.test_execskill_replay import alf_trajectory, qa_trajectories, sheet_trajectories
from tests.test_execskill_v24_engineer import Workers


SOURCE = '''COUNTER = [0]
def applies(view):
    return True
def before_call(view, state):
    COUNTER[0] += 1
    return {"facts": [str(COUNTER[0]) + " " + " ".join({"alpha", "beta", "gamma"})]}
'''


def procedure(source=SOURCE, *, modern=True, origin="searchqa", hooks=("applies", "before_call"), **extra):
    return Procedure("fx-v28-execution", origin, "Authored execution fixture", hooks, source, FIXTURE,
                     max_note_chars=1500, policy_version=policy.POLICY_VERSION_V28 if modern else policy.POLICY_VERSION_V25,
                     **extra)


def entries():
    return [replay.inputs_of(value) for value in qa_trajectories()]


class SeedWorkers(Workers):
    def __init__(self):
        super().__init__()
        self.seeds = []

    @contextmanager
    def __call__(self, package, **options):
        self.seeds.append(options.get("hashseed", 0))
        with super().__call__(package, **options) as worker:
            # The production worker recreates this namespace for every hook, even when a container is reused.
            from skillopt.execskill.sandbox.worker import execute
            codes = {proc.id: compile(proc.source, "<v28-pass-fixture>", "exec") for proc in package.procedures}
            def call(pid, hook, args, **kwargs):
                worker.calls.append((pid, hook, args))
                result = execute(codes[pid], hook, args, 65536)
                if result.get("ok"):
                    result["value_sha256"] = digest(result["value"])
                return result
            worker.call = call
            yield worker


def test_v28_replay_reuses_pass_workers_with_fixed_seed_and_fresh_hook_namespaces():
    proc, values, workers = procedure(), entries(), SeedWorkers()
    report, first = replay.zero_crash(proc, values, workers)
    assert report["passed"] and report["informational"] and report["hashseed"] == 0
    assert workers.seeds == [0, 0]
    assert len(workers.opened) == 2 and report["replay_workers"] == "per_pass"
    assert all(outcome.note("before_call").splitlines()[-1].startswith("- 1 ") for outcome in first.values())
    expected = [value["request_view"]["question"] for value in values]
    seen = [call[2][0]["question"] for call in workers.calls if call[1] == "applies"]
    assert seen == expected + expected[::-1]


def test_v28_worker_seed_is_enforced_at_start_for_all_callers():
    proc = procedure()
    for modern, expected in ((True, 0), (False, 1)):
        worker = Worker(hashseed=1).start(replay.solo(proc if modern else procedure(modern=False)), kind="cell")
        assert worker.hashseed == expected
        argv = docker_command("cell", None, {"runner": "/runner", "input": None},
                              name="execskill-sbx-fixture", hashseed=worker.hashseed)
        assert "PYTHONHASHSEED=%d" % expected in argv
        worker.close()


def test_real_execute_fresh_namespace_and_seed_make_set_counter_repeatable():
    # Use the production execute function in separate Python processes; no Docker/network/model is involved.
    program = ("import json; from skillopt.execskill.sandbox.worker import execute; "
               "source = " + repr(SOURCE) + "; code = compile(source, '<fixture>', 'exec'); "
               "print(json.dumps([execute(code, 'before_call', [{}, None], 4096) for _ in range(3)]))")
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1")
    first = subprocess.check_output([sys.executable, "-c", program], env=env, text=True)
    second = subprocess.check_output([sys.executable, "-c", program], env=env, text=True)
    assert first == second
    values = json.loads(first)
    assert len(values) == 3 and all(value == values[0] for value in values)
    assert values[0]["value"]["facts"][0].startswith("1 ")


def test_v28_reports_mismatch_without_losing_first_pass_outputs():
    class ChangingWorkers(SeedWorkers):
        @contextmanager
        def __call__(self, package, **options):
            with super().__call__(package, **options) as worker:
                old = worker.call
                iteration = len(self.opened)

                def call(pid, hook, args, **kwargs):
                    result = old(pid, hook, args, **kwargs)
                    if hook == "before_call":
                        result["value_sha256"] = str(iteration)
                    return result

                worker.call = call
                yield worker

    values = entries()[:1]
    report, first = replay.zero_crash(procedure(), values, ChangingWorkers(), diagnostic_cells={values[0]["cell"]})
    assert not report["passed"] and report["informational"]
    assert report["mismatched"] == [values[0]["cell"]]
    assert first[values[0]["cell"]].values[-1][-1] == "1"
    assert "same seed" in report["mismatch_explanation"]


def test_crashing_item_has_no_note_and_next_item_still_runs():
    source = SOURCE.replace('COUNTER[0] += 1', 'if "17" in view["question"]:\n        raise RuntimeError("fixture")\n    COUNTER[0] += 1')
    report, first = replay.zero_crash(procedure(source), entries(), SeedWorkers())
    assert report["informational"] and report["fault_count"] == 2
    assert first["c-q1"].notes == []
    assert first["c-q2"].notes and first["c-q3"].notes
    recorded = {row["cell"]: row for row in report["items"]}
    assert set(recorded) == set(first)
    assert recorded["c-q1"]["first"]["faults"] and recorded["c-q1"]["second"]["faults"]
    assert recorded["c-q2"]["first"]["faults"] == []


@pytest.mark.parametrize("imperative", ["Answer with a number.", "Respond with JSON.", "Output only a label.",
    "Format your answer as JSON.", "Round to two places.", "Give the answer as text.", "Only the number.",
    "Just the answer."])
def test_c9_drops_only_instruction_item_keeps_factual_words(imperative):
    fact = "The units return to round output bins; the answer appears in the ledger."
    kept, dropped = notes.screen({"facts": [fact, imperative, "The count is 3."]}, bench="zebralogic",
                                 outcome_judged=True)
    assert kept == {"facts": [fact, "The count is 3."]}
    assert len(dropped) == 1 and dropped[0]["reason"] == "form_instruction" and dropped[0]["item"] == 1
    assert fact in notes.render(kept, bench="zebralogic", header="Units in the ledger")
    old, old_drops = notes.screen({"facts": [fact]}, bench="zebralogic")
    assert not old and old_drops[0]["reason"] == "lexicon"


def test_c9_can_remove_one_sentence_and_records_without_killing_procedure():
    source = SOURCE.replace('str(COUNTER[0]) + " " + " ".join({"alpha", "beta", "gamma"})',
                            '"The count is 3. Answer with a number. Units are boxes."')
    proc, values = procedure(source), entries()[:1]
    result = replay.replay_many(proc, values, SeedWorkers())[values[0]["cell"]]
    assert "The count is 3. Units are boxes." in result.note("before_call")
    assert result.faults == [{"hook": "before_call", "step": None, "kind": "note_form_instruction",
                             "detail": "Answer with", "field": "facts", "item": 0, "informational": True}]


def test_c9_factual_mentions_of_phrases_are_kept():
    facts = ["The sensor can output only integers.", "The answer with units appears in the ledger.",
             "Only the red house has 3 units.", "Just the blue bin is round."]
    kept, dropped = notes.screen({"facts": facts}, bench="zebralogic", outcome_judged=True)
    assert kept == {"facts": facts} and dropped == []
    assert notes.instruction_hits("Please answer with JSON.") == ["answer with"]
    assert notes.instruction_hits("Use the clues and output only JSON.") == ["output only"]


def test_c8_audits_raw_markers_even_when_instruction_item_is_dropped():
    source = SOURCE.replace('str(COUNTER[0]) + " " + " ".join({"alpha", "beta", "gamma"})',
                            '"Answer with <answer>3</answer>."')
    values = entries()[:1]
    found = replay.replay_many(procedure(source), values, SeedWorkers())
    assert not found[values[0]["cell"]].notes
    assert {hit["marker"] for hit in replay.format_guard(found)} == {"<answer", "</answer"}


def test_registrar_tracker_and_negative_quality_checks_are_informational_only_v28():
    source = '''def applies(view):
    return True
def alf_before_step(view, state):
    return {"fields": {"facts": ["Public room facts"]}, "discourage": []}
def alf_after_step(event, state):
    return {"facts": {"nothing_happens": 999}}
'''
    values = [replay.inputs_of(alf_trajectory())]
    proc = procedure(source, origin="alfworld", hooks=("applies", "alf_before_step", "alf_after_step"), state_bytes=4096)
    found = replay.replay_many(proc, values, SeedWorkers())
    by_cell = {value["cell"]: value for value in values}
    result = replay.registrar_checks(proc, by_cell, found)
    assert result["passed"] and not result["measured_passed"]
    assert result["informational_problems"][0]["reason"] == "reference_tracker"
    old = replace(proc, policy_version=policy.POLICY_VERSION_V25)
    assert not replay.registrar_checks(old, by_cell, found)["passed"]
    outcome = found[values[0]["cell"]]
    outcome.faults.append({"hook": "bindings", "step": None, "kind": "note_not_verbatim", "detail": "x"})
    assert not replay.registrar_checks(proc, by_cell, found)["passed"]


def test_alf_state_is_explicit_and_resets_for_each_episode():
    source = '''COUNTER = [0]
def applies(view):
    return True
def alf_before_step(view, state):
    return {"fields": {"facts": [str((state or {}).get("count", 0))]}, "discourage": []}
def alf_after_step(event, state):
    return {"count": (state or {}).get("count", 0) + 1}
'''
    proc = procedure(source, origin="alfworld", hooks=("applies", "alf_before_step", "alf_after_step"), state_bytes=4096)
    values = [replay.inputs_of(alf_trajectory(cell="a")), replay.inputs_of(alf_trajectory(cell="b"))]
    workers = SeedWorkers()
    found = replay.replay_many(proc, values, workers)
    assert workers.seeds == [0] and all(kind == "episode" for kind, _, _ in workers.opened)
    assert found["a"].steps == found["b"].steps
    assert found["a"].note("alf_before_step", 0).endswith("- 0")
    assert found["a"].note("alf_before_step", 1).endswith("- 1")


def test_registrar_winning_action_negative_is_quality():
    source = '''def applies(view):
    return True
def alf_before_step(view, state):
    return {"fields": {}, "discourage": view["admissible_commands"]}
'''
    proc = procedure(source, origin="alfworld", hooks=("applies", "alf_before_step"))
    values = [replay.inputs_of(alf_trajectory())]
    found = replay.replay_many(proc, values, SeedWorkers())
    report = replay.registrar_checks(proc, {value["cell"]: value for value in values}, found)
    assert report["passed"] and not report["measured_passed"]
    assert report["informational_problems"] == [{"reason": "negative_test", "cell": values[0]["cell"],
                                               "test": "winning_action_discouraged"}]


@pytest.mark.parametrize("kind", ["note_name", "note_duplicate_name", "note_value", "note_not_verbatim"])
def test_registrar_binding_quality_is_information_but_nonverbatim_is_leakage(kind):
    proc = procedure()
    value = entries()[0]
    outcome = replay.Outcome(value["cell"], value["bench"], applies=True)
    outcome.faults.append({"hook": "bindings", "step": None, "kind": kind, "detail": "fixture"})
    report = replay.registrar_checks(proc, {value["cell"]: value}, {value["cell"]: outcome})
    fatal = kind == "note_not_verbatim"
    assert report["passed"] is not fatal and not report["measured_passed"]
    assert bool(report["informational_problems"]) is not fatal
    assert report["classifications"][kind] == ("leakage" if fatal else "quality")
    old = replace(proc, policy_version=policy.POLICY_VERSION_V25)
    assert not replay.registrar_checks(old, {value["cell"]: value}, {value["cell"]: outcome})["passed"]


def test_shell_instruction_drops_are_recorded_without_faulting_and_crash_is_no_note():
    proc = procedure()
    package = Package((proc,), "fixture", FIXTURE)
    public = {"question": "Who?", "context": ["The count is 3 units."]}
    worker = FakeSandbox({proc.id: {"before_call": lambda view, state:
        {"facts": ["There are 3 units.", "Answer with a number."]}}})
    call = Script(["<answer>3</answer>"])
    prediction = solver.solve("searchqa", public, "Read facts", package, call, worker=worker)
    assert "There are 3 units." in call.requests[0][1] and "Answer with a number" not in call.requests[0][1]
    assert not prediction["shell"]["faults"]
    assert prediction["shell"]["notes"][0]["dropped"][0]["reason"] == "form_instruction"
    crashed = FakeSandbox(faults={(proc.id, "before_call"): "timeout"})
    no_note = Script(["<answer>3</answer>"])
    prediction = solver.solve("searchqa", public, "Read facts", package, no_note, worker=crashed)
    assert prediction["shell"]["faults"][0]["kind"] == "timeout"
    assert "There are 3 units." not in no_note.requests[0][1]


def test_donor_and_placebo_lengths_apply_the_same_v28_screen_after_serialization():
    proc = procedure()
    worker = FakeSandbox({proc.id: {"before_call": lambda view, state:
        {"facts": ["There are 3 units.", "Answer with a number."]}}})
    worker.start(replay.solo(proc), kind="cell")
    faults = []
    found = donors.procedure_outputs(worker, proc, {"id": "donor", "item": "item", "view": {},
        "report": None, "steps": None}, bench="searchqa", faults=faults)
    fields = json.loads(json.dumps(found["before_call"]))
    assert fields == {"facts": ["There are 3 units."]}
    assert faults[0]["reason"] == "form_instruction" and faults[0]["informational"]
    length = placebo.rendered(fields, bench="searchqa", header="", outcome_judged=True)
    sham, band = placebo.sham_fields([fields], length, bench="searchqa", header="", cap=1500,
                                     outcome_judged=True)
    assert sham == fields and band["chars"] == length and band["within"]


def test_alf_post_action_fault_keeps_emitted_note_but_suppresses_future_notes():
    source = '''def applies(view):
    return True
def alf_before_step(view, state):
    return {"fields": {"facts": ["The count is 3."]}, "discourage": []}
def alf_after_step(event, state):
    raise RuntimeError("late fault")
'''
    proc = procedure(source, origin="alfworld", hooks=("applies", "alf_before_step", "alf_after_step"), state_bytes=4096)
    value = replay.inputs_of(alf_trajectory())
    found = replay.replay_many(proc, [value], SeedWorkers())[value["cell"]]
    assert "The count is 3." in found.note("alf_before_step", 0)
    assert found.steps[0]["note"] == found.note("alf_before_step", 0)
    assert found.note("alf_before_step", 1) == "" and len(found.steps) == 1
    assert found.faults[0]["hook"] == "alf_after_step"
    # Match the actual shell: after_step runs only after the note-bearing request and action.
    package = replay.solo(proc)
    namespace = {}
    exec(source, namespace)
    worker = FakeSandbox({proc.id: {hook: namespace[hook] for hook in proc.hooks}})
    shell = solver._Shell("alfworld", package, None, worker, withhold=(), restore=(), placebo=None,
                          text=None, native=None, nominal=None)
    shell.start("episode")
    shell.route_on(value["view"])
    emitted, _ = shell.before_step(value["steps"][0]["view"], {}, 0)
    shell.after_step(value["steps"][0]["event"], {})
    following, _ = shell.before_step(value["steps"][1]["view"], {}, 1)
    shell.close()
    assert emitted == found.note("alf_before_step", 0) and following == ""
    assert shell.faults[0]["hook"] == "alf_after_step"


def test_sheet_feedback_fault_keeps_previously_emitted_first_request_note():
    source = '''def applies(view):
    return True
def before_call(view, state):
    return {"facts": ["The count is 3."]}
def sheet_feedback(view, report, state):
    raise RuntimeError("late feedback fault")
'''
    proc = procedure(source, origin="spreadsheetbench", hooks=("applies", "before_call", "sheet_feedback"))
    value = replay.inputs_of(sheet_trajectories()[0])
    found = replay.replay_many(proc, [value], SeedWorkers())[value["cell"]]
    assert "The count is 3." in found.note("before_call")
    assert found.note("sheet_feedback") == "" and found.faults[0]["hook"] == "sheet_feedback"
    package, namespace = replay.solo(proc), {}
    exec(source, namespace)
    worker = FakeSandbox({proc.id: {hook: namespace[hook] for hook in proc.hooks}}).start(package, kind="cell")
    donor = donors.procedure_outputs(worker, proc, {"id": "donor", "item": "item", "view": value["request_view"],
        "report": value["report"], "steps": None}, bench="spreadsheetbench", faults=[])
    assert donor["before_call"] == {"facts": ["The count is 3."]} and donor["sheet_feedback"] == {}


def test_instruction_only_zero_call_signature_reuses_empty_request_but_real_fault_does_not():
    proc = procedure()
    package = replay.solo(proc)
    parent = Package((), "fixture", FIXTURE)
    view = entries()[0]["request_view"]
    worker = FakeSandbox({proc.id: {"before_call": lambda view, state:
        {"facts": ["Answer with a number."]}}}).start(package, kind="cell")
    candidate = reuse.signature("searchqa", package, view, worker)
    baseline = reuse.signature("searchqa", parent, view, None)
    assert candidate["faults"] == [] and reuse.interchangeable(candidate, baseline, bench="searchqa")
    crashed = FakeSandbox(faults={(proc.id, "before_call"): "timeout"}).start(package, kind="cell")
    faulting = reuse.signature("searchqa", package, view, crashed)
    assert faulting["request_sha256"] == baseline["request_sha256"]  # no note on the pending request
    assert faulting["faults"][0]["kind"] == "timeout"
    assert not reuse.interchangeable(faulting, baseline, bench="searchqa")  # conservative fault retry
