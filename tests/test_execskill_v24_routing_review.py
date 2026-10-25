"""Review fixes: shell-visible C6c notes and existing stateful replays, using synthetic offline fixtures only."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.execskill import engineer, notes, profiles as p, replay
from skillopt.execskill.package import FIXTURE
from tests.test_execskill_v24_engineer import PUBLIC, change, context, detail, offline


def generated_source(fields):
    return '''def applies(view):
    return True
def before_call(view, state):
    if "generated-only" in view["question"]:
        return %r
    return {}
''' % fields


@pytest.mark.parametrize("fields", [
    {"facts": "not a list"},
    {"facts": ["Return the answer as JSON."]},
    {"facts": ["x" * 201]},
    {"bindings": [{"name": "quantity", "quote": "not in the public question 27", "value": "27"}]},
    {"bindings": [{"name": "quantity", "quote": "generated-only 27", "value": "not numeric"}]},
    {"table": [[1, 2]]},
    {},
])
def test_generated_output_removed_by_shell_cannot_pass_c6c(fields):
    ctx, workers = context()
    ctx.routing_items.append(("gen:one", {"question": "generated-only 27", "columns": ["Name"]}))
    report = engineer.check(change(ctx, generated_source(fields)), ctx)
    assert report["failed"] == "C6c"
    output = detail(report, "C6c")
    assert output["fired"] == output["empty"] == 2 and output["nonempty"] == output["exceptions"] == 0
    assert len(workers.opened) == 4  # C5, two C6 passes, and one C6b/C6c worker
    assert [fn for _, fn, _ in workers.opened[-1][2].calls] == ["applies", "before_call"] * 2


def test_generated_valid_output_and_verbatim_table_exception_still_pass():
    ctx, workers = context()
    ctx.routing_items.append(("gen:one", {"question": "generated-only answer", "columns": ["Name"]}))
    report = engineer.check(change(ctx, generated_source({"table": [["answer"]]})), ctx)
    assert report["passed"] and detail(report, "C6c")["nonempty"] == 1
    assert detail(report, "C6c")["empty"] == 1
    assert len(workers.opened) == 4


def test_screened_generated_note_over_declared_cap_counts_empty():
    ctx, _ = context()
    ctx.routing_items.append(("gen:one", {"question": "generated-only 27", "columns": ["Name"]}))
    proposal = change(ctx, generated_source({"facts": ["Useful public clue."]}))
    proposal.entry["max_note_chars"] = 3
    report = engineer.check(proposal, ctx)
    assert report["failed"] == "C6c" and detail(report, "C6c")["empty"] == 2


def test_existing_response_is_rendered_through_binding_validation_and_benchmark_cap():
    # This helper-only object separates the benchmark cap from the usual <=4000 declared package cap.
    procedure = SimpleNamespace(id="fx-screened", header="", max_note_chars=9000)
    response = {"ok": True, "value": {"facts": ["useful " * 28] * 22}}
    assert replay.screened_note(procedure, "zebralogic", PUBLIC, response) == ""
    value = {"bindings": [{"name": "quantity", "quote": "five houses", "value": "5"}]}
    assert replay.screened_note(procedure, "zebralogic", PUBLIC, {"ok": True, "value": value}) == ""
    value = {"bindings": [{"name": "quantity", "quote": "5 houses", "value": "5"}]}
    rendered = replay.screened_note(procedure, "zebralogic", PUBLIC, {"ok": True, "value": value})
    assert rendered and "quantity" in rendered
    visible, skipped = notes.assemble([(procedure.id, rendered, 3)], bench="zebralogic")
    assert visible == "" and skipped[0]["reason"] == "over_declared_cap"


def test_legacy_c6b_does_not_gain_the_new_screened_output_gate():
    ctx, workers = context(configuration=p.ZEBRA_PC_V1)
    ctx.routing_items.append(("gen:one", {"question": "generated-only 27", "columns": ["Name"]}))
    report = engineer.check(change(ctx, generated_source({"facts": "not a list"})), ctx)
    assert report["passed"] and "C6c" not in [entry["check"] for entry in report["checks"]]
    assert [fn for _, fn, _ in workers.opened[-1][2].calls] == ["applies", "applies"]


TRACKER = '''def applies(view):
    return "task_text" in view
def alf_before_step(view, state):
    if state is None:
        return {"fields": {}, "discourage": []}
    return {"fields": {"facts": ["Earlier public observations are retained."]}, "discourage": []}
def alf_after_step(event, state):
    count = state["facts"]["nothing_happens"] if state else 0
    count += int(event["observation"].startswith("Nothing happens"))
    return {"facts": {"nothing_happens": count}}
'''


def tracker_change(ctx, *, emits=True, claims=True):
    source = TRACKER if emits else TRACKER.replace(
        '{"facts": ["Earlier public observations are retained."]}', '{}')
    test = {"id": "later-note", "trajectory": ctx.trajectories[-1]["cell"], "hook": "alf_before_step",
            "property": {"kind": "note_contains", "value": "Earlier public observations", "step": 1},
            "claims_fix": True, "nonvacuity": {"withheld_expect": False, "mutation": None}}
    return engineer.Change(1, "new", {"kind": "new", "description": "Tracks public observations.",
        "hooks": ["applies", "alf_before_step", "alf_after_step"], "max_note_chars": 4000, "state_bytes": 1024,
        "excluded_benches": [bench for bench in p.BENCHES if bench != "alfworld"],
        "replay_tests": [test] if claims else []}, source, "a" * 64)


def _record_trajectory(value):
    return p.record("trajectory", FIXTURE,
                    {k: v for k, v in value.items() if k not in (p.RECORD_HASH, "version", "evidence")})


def test_stateful_alfworld_later_screened_note_passes_without_replaying_step_hooks():
    ctx, workers = context(bench="alfworld")
    report = engineer.check(tracker_change(ctx), ctx)
    assert report["passed"] and detail(report, "C5b")["claimed"] == 1
    assert detail(report, "C6c")["nonempty"] == 1 and detail(report, "C6c")["empty"] == 0
    assert len(workers.opened) == 4
    assert [fn for _, fn, _ in workers.opened[-1][2].calls] == ["applies"]
    first_pass = workers.opened[1][2].calls
    before = [args for _, fn, args in first_pass if fn == "alf_before_step"]
    assert before[0][1] is None and before[1][1] == {"facts": {"nothing_happens": 0}}
    assert len(before) == len(replay.inputs_of(ctx.trajectories[0])["steps"])


def test_stateful_alfworld_never_emitting_still_fails_c6c():
    ctx, workers = context(bench="alfworld")
    report = engineer.check(tracker_change(ctx, emits=False, claims=False), ctx)
    assert report["failed"] == "C6c"
    assert detail(report, "C6c")["fired"] == detail(report, "C6c")["empty"] == 1
    assert detail(report, "C6c")["nonempty"] == 0
    assert len(workers.opened) == 4 and [fn for _, fn, _ in workers.opened[-1][2].calls] == ["applies"]


def test_all_verified_run_cells_of_a_routed_item_are_considered():
    ctx, workers = context(bench="alfworld")
    first = deepcopy(ctx.trajectories[0])
    first.update(cell="a-empty-first", calls=first["calls"][:1], replies=first["replies"][:1],
                 alfworld_steps=first["alfworld_steps"][:1], logical_calls=1)
    ctx = replace(ctx, trajectories=[_record_trajectory(first), ctx.trajectories[0]])
    report = engineer.check(tracker_change(ctx), ctx)
    assert report["passed"] and detail(report, "C6c")["nonempty"] == 1
    assert len(workers.opened) == 4  # both trajectories share each existing C6 worker
    assert [fn for _, fn, _ in workers.opened[-1][2].calls] == ["applies"]


def test_alfworld_cannot_use_non_run_outcomes_or_create_a_fresh_step_replay():
    ctx, workers = context(bench="alfworld")
    proposal = tracker_change(ctx, emits=False, claims=False)
    engineer._build(proposal, ctx)
    foreign = replay.Outcome("generated-cell", "alfworld", applies=True,
        notes=[{"hook": "alf_before_step", "step": 1, "text": "NONRUN_OUTPUT_SENTINEL", "public": ""}])
    found = engineer._routing_checks(proposal.procedure, ctx, outcomes={foreign.cell: foreign})
    assert not found["C6c"][0] and found["C6c"][1]["missing_replays"] == 1
    assert found["C6c"][1]["nonempty"] == 0 and len(workers.opened) == 1
    assert [fn for _, fn, _ in workers.calls] == ["applies"]


def test_alfworld_current_run_item_trajectory_can_supply_later_stateful_output():
    ctx, workers = context(bench="alfworld")
    short, current = deepcopy(ctx.trajectories[0]), deepcopy(ctx.trajectories[0])
    short.update(calls=short["calls"][:1], replies=short["replies"][:1],
                 alfworld_steps=short["alfworld_steps"][:1], logical_calls=1)
    current.update(cell="current-training-cell", unit="D/s1-alfworld/train-r1", arm="S'", arm_kind="candidate")
    short, current = _record_trajectory(short), _record_trajectory(current)
    ctx = replace(ctx, round=2, trajectories=[short], current=[current])
    proposal = tracker_change(ctx)
    proposal.entry["replay_tests"][0]["trajectory"] = current["cell"]
    report = engineer.check(proposal, ctx)
    assert report["passed"] and detail(report, "C5b")["claimed"] == 1
    assert detail(report, "C6c")["nonempty"] == 1 and detail(report, "C6c")["empty"] == 0
    assert len(workers.opened) == 4 and [fn for _, fn, _ in workers.opened[-1][2].calls] == ["applies"]
    # Current output qualifies; the public sample still comes from the original run record.
    assert detail(report, "C6c")["sample"] == engineer.engineer_payload.view_excerpt(
        replay.inputs_of(short)["steps"][0]["view"], chars=300)


def test_alfworld_evaluated_cells_do_not_expand_c6c_replay_scope():
    ctx, workers = context(bench="alfworld")
    short, evaluated = deepcopy(ctx.trajectories[0]), deepcopy(ctx.trajectories[0])
    short.update(calls=short["calls"][:1], replies=short["replies"][:1],
                 alfworld_steps=short["alfworld_steps"][:1], logical_calls=1)
    evaluated.update(cell="evaluated-only-cell", unit="D/s1-alfworld/train-r1", arm="S'", arm_kind="candidate")
    short, evaluated = _record_trajectory(short), _record_trajectory(evaluated)
    ctx = replace(ctx, round=2, trajectories=[short], evaluated=[evaluated])
    proposal = tracker_change(ctx, claims=False)
    engineer._build(proposal, ctx)
    # Even a supplied output from an evaluated-only cell cannot count as an existing in-scope C6 replay.
    foreign = replay.Outcome(evaluated["cell"], "alfworld", applies=True,
        notes=[{"hook": "alf_before_step", "step": 1, "text": "A later public note.", "public": ""}])
    empty = replay.Outcome(short["cell"], "alfworld", applies=True)
    found = engineer._routing_checks(proposal.procedure, ctx, outcomes={empty.cell: empty, foreign.cell: foreign})
    assert not found["C6c"][0] and found["C6c"][1]["nonempty"] == 0
    assert len(workers.opened) == 1 and [fn for _, fn, _ in workers.calls] == ["applies"]


def test_current_stateful_replay_can_follow_an_original_run_without_a_request():
    ctx, workers = context(bench="alfworld")
    missing, current = deepcopy(ctx.trajectories[0]), deepcopy(ctx.trajectories[0])
    missing.update(calls=[], replies=[], alfworld_steps=[], logical_calls=0, token="unknown")
    current.update(cell="current-after-missing-run", unit="D/s1-alfworld/train-r1", arm="S'", arm_kind="candidate")
    missing, current = _record_trajectory(missing), _record_trajectory(current)
    ctx = replace(ctx, round=2, trajectories=[missing], current=[current])
    proposal = tracker_change(ctx)
    proposal.entry["replay_tests"][0]["trajectory"] = current["cell"]
    report = engineer.check(proposal, ctx)
    assert report["passed"] and detail(report, "C6c")["nonempty"] == 1
    assert detail(report, "C6c")["sample"] is None
    assert detail(report, "C6c")["view_keys"] == sorted(replay.inputs_of(current)["steps"][0]["view"])
    assert engineer.hook_views(ctx)["status"] == "unavailable"
    assert len(workers.opened) == 4 and [fn for _, fn, _ in workers.opened[-1][2].calls] == ["applies"]
    # A current-only exception remains counts-only, just like the absent original public-view sample.
    failed = replay.Outcome(current["cell"], "alfworld", applies=True,
        faults=[{"hook": "alf_before_step", "step": 1, "kind": "crash:exception", "detail": "CURRENT_ONLY_SENTINEL"}])
    captured = {current["cell"]: [{"hook": "alf_before_step", "step": 1, "status": "raised",
                                  "exc_type": "ValueError", "message": "CURRENT_ONLY_SENTINEL"}]}
    found = engineer._routing_checks(proposal.procedure, ctx, outcomes={failed.cell: failed}, actual=captured)
    assert not found["C6c"][0] and found["C6c"][1]["exceptions"] == 1
    assert found["C6c"][1]["first_exception"] is None and found["C6c"][1]["sample"] is None
    assert len(workers.opened) == 5 and [fn for _, fn, _ in workers.opened[-1][2].calls] == ["applies"]
