"""v2.6 diagnostics from the two existing deterministic-replay passes; authored offline workers only."""
from contextlib import contextmanager
from dataclasses import replace
import json

import pytest

from skillopt.execskill import engineer, profiles as p, replay
from tests.execskill_fakes_env import FakeSandbox
from tests.test_execskill_v24_engineer import GOOD, PUBLIC, change, context, detail
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v25_engineer import shown_context
from tests.test_execskill_zpc_pipeline import offline


class SeedWorkers:
    """Each fresh fake worker's authored hooks depend on its requested hashseed, without launching a process."""
    def __init__(self, *, stable=False, predicate=False, large=False, raises=False):
        self.stable, self.predicate, self.large, self.raises = stable, predicate, large, raises
        self.opened = []

    @contextmanager
    def __call__(self, package, *, kind="cell", hashseed=0, inputs_dir=None):
        seed = 0 if self.stable else hashseed
        def applies(view):
            return seed == 0 if self.predicate else True
        def before(view, state):
            if self.raises and seed == 1:
                raise LookupError("x" * 500)
            if self.large:
                return {"facts": ["x" * 1800 + str(seed)]}
            return {"table": [[view["question"].splitlines()[-1], str(seed)]]}
        hooks = {procedure.id: {"applies": applies, "before_call": before} for procedure in package.procedures}
        worker = FakeSandbox(hooks).start(package, kind=kind, inputs_dir=inputs_dir)
        worker.rejected = {}
        self.opened.append({"kind": kind, "seed": hashseed, "inputs_dir": inputs_dir, "worker": worker})
        try:
            yield worker
        finally:
            worker.close()


def fixture(count=3):
    views = [{**PUBLIC, "question": PUBLIC["question"] + "\nAuthored public marker %02d" % index}
             for index in range(count)]
    ctx, _ = context(configuration=p.ZEBRA_PC_V3, views=views)
    proposal = change(ctx, GOOD)
    engineer._build(proposal, ctx)
    entries = [replay.inputs_of(value) for value in ctx.trajectories]
    return proposal.procedure, entries


def calls(workers):
    return [[(hook, args[0]["question"]) for _, hook, args in row["worker"].calls] for row in workers.opened]


def legacy_report(entries):
    return {"check": "C6", "passed": False, "trajectories": len(entries), "fault_count": 0, "faults": [],
            "mismatched": [entry["cell"] for entry in entries][:10], "applied": len(entries)}


def test_default_c6_report_and_first_capture_remain_byte_identical():
    procedure, entries = fixture()
    workers, actual = SeedWorkers(), {}
    report, _ = replay.zero_crash(procedure, entries, workers, actual=actual)
    assert json.dumps(report, sort_keys=True) == json.dumps(legacy_report(entries), sort_keys=True)
    assert len(workers.opened) == 2
    assert all(len(actual[entry["cell"]]) == 2 for entry in entries)
    assert all(json.loads(actual[entry["cell"]][1]["value"])["table"][0][-1] == "0" for entry in entries)


@pytest.mark.parametrize("shown", [frozenset(), frozenset({"unregistered-foreign-cell"}), frozenset({"cell-1"})])
def test_explanation_and_task_ids_are_added_but_return_values_require_a_shown_scope_cell(shown):
    procedure, entries = fixture()
    report, _ = replay.zero_crash(procedure, entries, SeedWorkers(), diagnostic_cells=shown)
    assert not report["passed"] and report["fault_count"] == 0
    assert report["mismatch_explanation"] == replay.MISMATCH_EXPLANATION
    assert "PYTHONHASHSEED=0" in report["mismatch_explanation"] and "reverse order" in report["mismatch_explanation"]
    assert "5 s" in report["mismatch_explanation"]
    assert report["mismatched_task_ids"] == sorted({entry["item"] for entry in entries})
    assert report["mismatched_total"] == len(entries)
    if "cell-1" in shown:
        example = report["mismatch_example"]
        assert example == {"cell": "cell-1", "task_id": entries[1]["item"], "hook": "before_call", "step": None,
            "first": {"status": "returned", "value": '{"table":[["Authored public marker 01","0"]]}'},
            "second": {"status": "returned", "value": '{"table":[["Authored public marker 01","1"]]}'}}
    else:
        assert "mismatch_example" not in report
    serialized = json.dumps(report)
    assert "Authored public marker 00" not in serialized and "Authored public marker 02" not in serialized


def test_one_deterministically_selected_cell_uses_first_differing_hook():
    procedure, entries = fixture()
    entries[0]["item"], entries[1]["item"] = "zebralogic/z", "zebralogic/a"
    shown = {entry["cell"] for entry in entries}
    report, _ = replay.zero_crash(procedure, entries, SeedWorkers(), diagnostic_cells=shown)
    reordered, _ = replay.zero_crash(procedure, entries[::-1], SeedWorkers(), diagnostic_cells=shown)
    assert report["mismatch_example"]["cell"] == "cell-1"
    assert report["mismatch_example"]["hook"] == "before_call"  # applies returns True identically
    assert report["mismatch_example"] == reordered["mismatch_example"]
    assert list(report["mismatched_task_ids"]) == list(reordered["mismatched_task_ids"])
    assert "Authored public marker 00" not in json.dumps(report)


def test_first_differing_predicate_is_reported_before_missing_later_hooks():
    procedure, entries = fixture(1)
    workers = SeedWorkers(predicate=True)
    report, _ = replay.zero_crash(procedure, entries, workers, diagnostic_cells={"cell-0"})
    example = report["mismatch_example"]
    assert example["hook"] == "applies" and example["step"] is None
    assert example["first"] == {"status": "returned", "value": "true"}
    assert example["second"] == {"status": "returned", "value": "false"}
    assert [len(row["worker"].calls) for row in workers.opened] == [2, 1]


def test_both_values_are_bounded_even_if_the_difference_is_beyond_the_excerpt():
    procedure, entries = fixture(1)
    report, _ = replay.zero_crash(procedure, entries, SeedWorkers(large=True), diagnostic_cells={"cell-0"})
    assert report["mismatched"] == ["cell-0"]
    example = report["mismatch_example"]
    assert len(example["first"]["value"]) == len(example["second"]["value"]) == 1500
    assert example["first"] == example["second"]  # full return hashes still detect the unseen tail difference
    assert example["hook"] == "before_call"


@pytest.mark.parametrize("capture_first", [False, True])
def test_diagnostics_reuse_exactly_two_workers_and_reverse_the_existing_item_order(capture_first):
    procedure, entries = fixture()
    baseline_workers, workers = SeedWorkers(), SeedWorkers()
    baseline, first = replay.zero_crash(procedure, entries, baseline_workers)
    actual = {} if capture_first else None
    report, second = replay.zero_crash(procedure, entries, workers, actual=actual, diagnostic_cells={"cell-1"})
    assert len(workers.opened) == len(baseline_workers.opened) == 2
    assert [(row["kind"], row["seed"], row["inputs_dir"]) for row in workers.opened] == [
        ("cell", 0, None), ("cell", 1, None)]
    assert calls(workers) == calls(baseline_workers)
    expected = [entry["request_view"]["question"] for entry in entries]
    assert [question for hook, question in calls(workers)[0] if hook == "applies"] == expected
    assert [question for hook, question in calls(workers)[1] if hook == "applies"] == expected[::-1]
    assert {key: value for key, value in report.items() if key in baseline} == baseline
    assert {cell: outcome.summary() for cell, outcome in first.items()} == {
        cell: outcome.summary() for cell, outcome in second.items()}
    if actual is not None:
        assert all(len(actual[entry["cell"]]) == 2 for entry in entries)  # second pass never appends to caller's capture
        assert all(json.loads(actual[entry["cell"]][1]["value"])["table"][0][-1] == "0" for entry in entries)


def test_stable_replay_gets_no_new_report_fields():
    procedure, entries = fixture()
    plain, first = replay.zero_crash(procedure, entries, SeedWorkers(stable=True))
    diagnosed, second = replay.zero_crash(procedure, entries, SeedWorkers(stable=True), diagnostic_cells={"cell-1"})
    assert plain == diagnosed and diagnosed["passed"]
    assert {cell: outcome.summary() for cell, outcome in first.items()} == {
        cell: outcome.summary() for cell, outcome in second.items()}


def test_task_list_covers_all_mismatches_and_shown_sample_can_follow_the_ten_cell_display_cap():
    procedure, entries = fixture(12)
    report, _ = replay.zero_crash(procedure, entries, SeedWorkers(), diagnostic_cells={"cell-11"})
    assert len(report["mismatched"]) == 10 and len(report["mismatched_task_ids"]) == 12
    assert report["mismatched_task_ids"] == sorted({entry["item"] for entry in entries})
    assert report["mismatched_total"] == 12
    assert report["mismatch_example"]["cell"] == "cell-11"
    assert entries[11]["item"] in report["mismatched_task_ids"]


@pytest.mark.parametrize("count", [12, 48])
def test_unshown_mismatches_keep_cell_cap_and_only_add_sorted_distinct_bounded_task_ids(count):
    procedure, entries = fixture(count)
    # Deliberately repeated, descending task IDs: cell totals must not count distinct tasks.
    for index, entry in enumerate(entries):
        entry["item"] = "zebralogic/task-%02d" % ((count - index) // 2)
    report, _ = replay.zero_crash(procedure, entries, SeedWorkers(), diagnostic_cells=set())
    expected = legacy_report(entries)
    assert {key: report[key] for key in expected} == expected
    assert set(report) == set(expected) | {"mismatch_explanation", "mismatched_task_ids", "mismatched_total"}
    tasks = sorted({entry["item"] for entry in entries})
    assert report["mismatched_task_ids"] == tasks[:20]
    assert len(report["mismatched_task_ids"]) == min(20, len(tasks))
    assert report["mismatched_total"] == count > len(tasks)
    serialized = json.dumps(report)
    assert all(json.dumps(entry["cell"]) not in serialized for entry in entries[10:])


def test_mismatch_with_a_raised_hook_uses_existing_bounded_results_without_new_crash_fields():
    procedure, entries = fixture(1)
    report, _ = replay.zero_crash(procedure, entries, SeedWorkers(raises=True), diagnostic_cells={"cell-0"})
    assert report["fault_count"] == 1 and report["mismatched"] == ["cell-0"]
    assert report["faults"] == [{"cell": "cell-0", "hook": "before_call", "step": None,
                                "kind": "crash:exception", "detail": "x" * 200}]
    assert report["mismatch_example"]["second"] == {"status": "raised", "exc_type": "LookupError",
                                                   "message": "x" * 300}


@pytest.mark.parametrize("configuration", [p.ZEBRA_PC_V3, p.ZEBRA_PC_V4])
def test_actual_engineer_c6_fix_payload_enables_diagnostics_only_for_v26(configuration):
    ctx, _ = shown_context(configuration=configuration)
    workers = SeedWorkers()
    ctx = replace(ctx, workers=workers, roles=WireRoles())
    engineer._ask(ctx, engineer.payload(ctx), "propose")
    proposal = change(ctx, GOOD)
    report = engineer.check(proposal, ctx)
    assert report["failed"] == "C6"
    found = detail(report, "C6")
    engineer._fix(ctx, proposal, report, attempt=1)
    fix = next(json.loads(row["user"]) for row in ctx.roles.wire if json.loads(row["user"])["request"] == "fix")
    assert fix["failed"]["detail"] == found
    if configuration == p.ZEBRA_PC_V4:
        assert found["mismatch_explanation"] == replay.MISMATCH_EXPLANATION
        assert found["mismatch_example"]["cell"] in engineer._feedback_cells(ctx)
    else:
        entries = [replay.inputs_of(value) for value in ctx.trajectories]
        assert found == legacy_report(entries)
        assert "mismatch_explanation" not in json.dumps(ctx.roles.wire)
    # C5's load worker plus exactly the two original C6 workers; the failure never enters routing.
    assert len(workers.opened) == 3 and [len(row["worker"].calls) for row in workers.opened] == [0, 2, 2]
