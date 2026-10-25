"""v2.4 executable feedback over authored synthetic procedures; no model, network, Docker or docs reads."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from skillopt.execskill import engineer, engineer_payload, profiles as p, replay, zebralogic
from skillopt.execskill.package import FIXTURE, Procedure, empty
from tests.execskill_fakes import engineer_reply
from tests.execskill_fakes_env import FakeSandbox
from tests.test_execskill_replay import alf_trajectory, sheet_trajectories, trajectory
from tests.test_execskill_zpc_pipeline import offline

V24 = p.ZEBRA_PC_V2
PUBLIC = {"question": "There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street.\nHouse 1 | Mara | blue\nHouse 2 | Neri | red\n"
          "House 3 | Oren | green\nHouse 4 | Pari | white\nHouse 5 | Quin | yellow", "columns": ["Name", "Color"]}
GOOD = '''def applies(view):
    return "question" in view
def before_call(view, state):
    rows = [line.split(" | ") for line in view["question"].splitlines() if line.startswith("House ")]
    return {"table": [["House"] + view["columns"]] + rows}
'''
EMPTY = '''def applies(view):
    return True
def before_call(view, state):
    return {}
'''
DEFECT = '''def applies(view):
    return "question" in view
def before_call(view, state):
    try:
        raw = view["question"].split("Puzzle to Solve", 1)[1]
        return {"facts": [raw]}
    except Exception:
        return {}
'''


class Workers:
    def __init__(self):
        self.opened, self.calls = [], []

    @contextmanager
    def __call__(self, package, *, kind="cell", hashseed=0, inputs_dir=None):
        hooks = {}
        for procedure in package.procedures:
            namespace = {}
            exec(compile(procedure.source, "<authored-v24-fixture>", "exec"), namespace)
            hooks[procedure.id] = {hook: namespace[hook] for hook in procedure.hooks}
        worker = FakeSandbox(hooks).start(package, kind=kind, inputs_dir=inputs_dir)
        worker.rejected = {}
        self.opened.append((kind, inputs_dir, worker))
        try:
            yield worker
        finally:
            self.calls.extend(worker.calls)
            worker.close()

    def routing(self, package, item):
        return self(package)


class Roles:
    def __init__(self, replies=()):
        self.replies, self.calls, self.seen = list(replies), [], []

    def count(self, prefix):
        return sum(call["label"].startswith(prefix) for call in self.calls)

    def plain(self, role, system, user, *, label, **options):
        self.seen.append((system, json.loads(user), options))
        self.calls.append({"label": label, "request_sha256": "a" * 64})
        return self.replies.pop(0) if self.replies else engineer_reply({"changes": []}, [])


def stored(view=PUBLIC, *, key="zebralogic/run-a", cell="cell-a"):
    value = trajectory(cell, "zebralogic", key, "fail", [view])
    value["calls"][0]["user"] = zebralogic.render_user(view)
    return p.record("trajectory", FIXTURE, {k: v for k, v in value.items() if k not in (p.RECORD_HASH, "version", "evidence")})


def context(*, configuration=V24, bench="zebralogic", mode="train", views=None):
    workers, parent = Workers(), empty(step="D/s0", evidence=FIXTURE)
    values = [stored(view, key="zebralogic/run-%d" % n, cell="cell-%d" % n)
              for n, view in enumerate(views or [PUBLIC])]
    if bench == "alfworld":
        values = [alf_trajectory(token="fail")]
    routing = [(value["task_id"], replay.inputs_of(value)["view"]) for value in values]
    ctx = engineer.Context(bench=bench, k=1, step="D/s1-" + bench, evidence=FIXTURE, parent=parent,
        trajectories=values, current=[], corpora={}, workers=workers, roles=Roles(), label="D/s1-%s/engineer-r1" % bench,
        configuration=configuration, mode=mode, round=1 if mode == "train" else 0,
        base=parent if mode == "train" else None, routing_items=routing, routing_workers=workers.routing,
        routing_shared_worker=True)
    return ctx, workers


def claim(ctx, *, holds="Mara", claims=True):
    return {"id": "claimed-grid", "trajectory": ctx.trajectories[0]["cell"], "hook": "before_call",
            "property": {"kind": "note_contains", "value": holds}, "claims_fix": claims,
            "nonvacuity": {"withheld_expect": False, "mutation": None}}


def change(ctx, source=GOOD, *, tests=()):
    return engineer.Change(1, "new", {"kind": "new", "description": "Tabulates explicit public clues.",
        "hooks": ["applies", "before_call"], "max_note_chars": 4000, "excluded_benches": list(p.BENCHES),
        "replay_tests": list(tests)}, source, "a" * 64)


def detail(report, name):
    return next(check["detail"] for check in report["checks"] if check["check"] == name)


def test_claimed_empty_result_fails_c5b_with_actual_return_and_enters_fix_loop():
    ctx, workers = context()
    original = change(ctx, EMPTY, tests=[claim(ctx)])
    fixed = change(ctx, GOOD, tests=[claim(ctx)])
    ctx.roles = Roles([engineer_reply({"changes": [original.entry]}, [original.source]),
                       engineer_reply({"changes": [fixed.entry]}, [fixed.source])])
    package, record = engineer.run_train(ctx)
    assert package is not None
    attempts = record["changes"][0]["attempts"]
    assert attempts[0]["failed"] == "C5b" and attempts[1]["passed"]
    failure = detail(attempts[0], "C5b")["failed"][0]
    assert failure["id"] == "claimed-grid" and failure["hook"] == "before_call"
    assert failure["property"] == {"kind": "note_contains", "value": "Mara"}
    assert failure["actual"] == {"status": "returned", "value": "returned nothing ({})"}
    fix = ctx.roles.seen[1][1]
    assert fix["failed"]["check"] == "C5b" and fix["hook_views"]["hook_view"] == PUBLIC
    assert record["prompt_sha256"] == engineer.ENGINEER_PROMPT_ZPC_V24_SHA256
    assert record["version"] == p.kind("engineer-v2-4")


def test_swallowed_heading_defect_fails_c6c_then_repair_passes_both_gates():
    ctx, workers = context(views=[PUBLIC, {**PUBLIC, "question": PUBLIC["question"] + "\nAnother public clue."}])
    failed = engineer.check(change(ctx, DEFECT), ctx)
    assert failed["failed"] == "C6c"
    assert detail(failed, "C5b") == {"claimed": 0, "failed": []}
    output = detail(failed, "C6c")
    assert output["fired"] == output["empty"] == 2 and output["nonempty"] == output["exceptions"] == 0
    assert output["view_keys"] == ["columns", "question"] and output["sample"] == PUBLIC
    assert all("Puzzle to Solve" not in args[0].get("question", "") for _, _, args in workers.calls)
    assert len(workers.opened) == 4  # C5, two C6 hash seeds, one shared C6b+C6c worker
    last = workers.opened[-1][2].calls
    assert [fn for _, fn, _ in last] == ["applies", "before_call", "applies", "before_call"]
    fixed = engineer.check(change(ctx, GOOD, tests=[claim(ctx)]), ctx)
    assert fixed["passed"] and detail(fixed, "C5b")["claimed"] == 1 and detail(fixed, "C6c")["nonempty"] == 2


@pytest.mark.parametrize("mode", ["train", "single"])
def test_nonclaim_tests_remain_lint_only_and_old_zebra_has_neither_gate(mode):
    ctx, _ = context(mode=mode)
    result = engineer.check(change(ctx, tests=[claim(ctx, holds="absent content", claims=False)]), ctx)
    assert result["passed"] and result["lint"]["tests"][0]["holds"] is False
    old, _ = context(configuration=p.ZEBRA_PC_V1, mode="train")
    result = engineer.check(change(old, EMPTY, tests=[claim(old)]), old)
    assert result["passed"] and result["lint"]["tests"][0]["holds"] is False
    assert not {"C5b", "C6c"} & {check["check"] for check in result["checks"]}


def test_claim_feedback_captures_exception_and_bounds_actual_objects():
    ctx, _ = context()
    throwing = EMPTY.replace("return {}", "raise ValueError(" + repr("e" * 500) + ")")
    found = engineer.check(change(ctx, throwing, tests=[claim(ctx)]), ctx)
    assert found["failed"] == "C5b"
    actual = detail(found, "C5b")["failed"][0]["actual"]
    assert actual == {"status": "raised", "exc_type": "ValueError", "message": "e" * 300}
    large = EMPTY.replace("return {}", 'return {"facts": ["public " * 500]}')
    found = engineer.check(change(ctx, large, tests=[claim(ctx)]), ctx)
    actual = detail(found, "C5b")["failed"][0]["actual"]
    assert actual["status"] == "returned" and len(actual["value"]) == 1500 and actual["value"].startswith('{"facts":[')


def test_invalid_claim_fails_closed_and_never_looks_up_an_unshown_trajectory():
    ctx, _ = context()
    invalid = claim(ctx)
    invalid["trajectory"] = "sealed-private-trajectory"
    found = engineer.check(change(ctx, tests=[invalid]), ctx)
    assert found["failed"] == "C5b"
    failure = detail(found, "C5b")["failed"][0]
    assert failure["reason"] == "trajectory_not_in_scope"
    assert failure["actual"] == {"status": "not_called", "reason": "hook_not_reached"}


def test_c6c_exceptions_sample_caps_generated_items_and_no_hook_skip():
    ctx, workers = context(views=[{**PUBLIC, "question": PUBLIC["question"] + "x" * 1800}])
    ctx.routing_items.insert(0, ("gen:only", {"question": "GENERATED_ONLY_SENTINEL", "columns": ["Name"]}))
    candidate = change(ctx, EMPTY.replace("return {}", 'raise ValueError("x" * 500)'))
    engineer._build(candidate, ctx)
    found = engineer._routing_checks(candidate.procedure, ctx)
    output = found["C6c"][1]
    assert not found["C6c"][0] and output["exceptions"] == 2 and output["empty"] == 0
    assert output["first_exception"]["exc_type"] == "ValueError" and len(output["first_exception"]["message"]) == 300
    assert len(output["sample"]["question"]) == 300 and "GENERATED_ONLY_SENTINEL" not in json.dumps(output["sample"])
    assert len(workers.opened) == 1
    without = Procedure(id="fx-bindings-only", origin="searchqa",
                        source='def applies(view):\n    return True\ndef bindings(view):\n    return {}\n',
                        description="Selects public numbers.", hooks=("applies", "bindings"), max_note_chars=4000,
                        excluded_benches=("spreadsheetbench", "alfworld"), evidence=FIXTURE)
    passed, output = engineer._routing_checks(without, replace(ctx, bench="searchqa"))["C6c"]
    assert passed and output["status"] == "not_applicable"


def test_alfworld_output_check_uses_existing_stateful_replay_and_same_worker():
    ctx, workers = context(bench="alfworld")
    source = 'def applies(view):\n    return "task_text" in view\ndef alf_before_step(view, state):\n    return {"fields": {"facts": [view["observation"][:40]]}, "discourage": []}\n'
    proc = Procedure(id="fx-alf-output", origin="alfworld", source=source, description="Records observations.",
                     hooks=("applies", "alf_before_step"), max_note_chars=4000, evidence=FIXTURE)
    entries = [replay.inputs_of(value) for value in ctx.trajectories]
    crash, outcomes = replay.zero_crash(proc, entries, workers)
    assert crash["passed"]
    before = len(workers.calls)
    found = engineer._routing_checks(proc, ctx, outcomes=outcomes)
    assert found["C6b"][0] and found["C6c"][0] and found["C6c"][1]["nonempty"] == 1
    assert len(workers.opened) == 3
    assert [fn for _, fn, _ in workers.calls[before:]] == ["applies"]
    predicate, hook = workers.calls[:2]
    assert "task_text" in predicate[2][0] and "task_text" not in hook[2][0]
    assert hook[2][0] == replay.inputs_of(ctx.trajectories[0])["steps"][0]["view"] and hook[2][1] is None
    sample = engineer.hook_views(ctx)
    assert sample["routing_view"] == predicate[2][0] and sample["hook_view"] == hook[2][0]


@pytest.mark.parametrize("mode", ["train", "single"])
def test_prompt_samples_are_deterministic_bounded_public_and_cap_is_ten_thousand(mode):
    public = {"question": PUBLIC["question"] + "x" * 2000, "columns": ["Column%d" % n for n in range(25)]}
    ctx, _ = context(mode=mode, views=[public, PUBLIC])
    sample = engineer.payload(ctx)["hook_views"]
    assert len(sample["hook_view"]["question"]) == 1500 and len(sample["hook_view"]["columns"]) == 20
    assert sample == engineer.hook_views(replace(ctx, trajectories=list(reversed(ctx.trajectories))))
    assert set(sample["hook_view"]) == {"question", "columns"}
    engineer._ask(ctx, engineer.payload(ctx), "propose")
    system = ctx.roles.seen[-1][0]
    assert "at most 10000 bytes" in system and "at most 6000 bytes" not in system
    assert "What your hooks receive" in system and "# Puzzle to Solve" in system and "never block a change" not in system
    assert "private" not in json.dumps(sample) and "solution" not in json.dumps(sample)
    caps = engineer._size_detail(change(ctx), ValueError("too large"), configuration=V24)["caps"]
    assert caps["source_bytes"] == 10000 and caps["package_source_bytes"] == 64000
    old, _ = context(configuration=p.ZEBRA_PC_V1)
    assert "hook_views" not in engineer.payload(old)


def test_view_and_reference_excerpts_do_not_mutate_their_inputs():
    value = {"question": "q" * 1700, "context": ["v" * 1600] * 30, "count": 3}
    original = deepcopy(value)
    result = engineer_payload.view_excerpt(value)
    assert value == original and len(result["question"]) == 1500 and len(result["context"]) == 20
    assert len(result["context"][0]) == 1500 and result["count"] == 3
    assert engineer_payload.reference_excerpt({"z": "v" * 1500}) == json.dumps({"z": "v" * 1500}, separators=(",", ":"))[:1000]


def test_output_reference_tracking_reaches_c4_and_later_rounds_after_fitting(monkeypatch):
    ctx, _ = context()
    stored_sheet = sheet_trajectories()[0]
    reference = {"Sheet!C2": "PRIVATECONSUMEDRUNREFERENCE"}
    ctx = replace(ctx, bench="spreadsheetbench", trajectories=[stored_sheet], routing_items=[],
                  routing_shared_worker=False, references={stored_sheet["task_id"]: reference})
    user = {"trajectories": [], "training": {"unfixed_examples": [{"task_id": stored_sheet["task_id"],
        "cell": stored_sheet["cell"], "reference": engineer_payload.reference_excerpt(reference)}]}}
    monkeypatch.setattr(engineer, "payload", lambda _: user)
    assert list(engineer.disclosed(ctx).values()) == ["PRIVATECONSUMEDRUNREFERENCE"]
    assert engineer._disclosed_items(ctx) == [stored_sheet["task_id"]]
    assert engineer._output_references(replace(ctx, configuration=p.ZEBRA_PC_V1), user) == []
