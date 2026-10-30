"""v2.6 replay references: authored data, real build/check/fix paths, no model or sandbox process."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from skillopt.execskill import engineer as e, profiles as p, replay
from skillopt.execskill.package import Procedure, load, save, with_
from tests.execskill_fakes import engineer_reply
from tests.execskill_zpc_fakes import tmp_path
from tests.test_execskill_v24_engineer import GOOD, PUBLIC, change, claim, context, stored
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_zpc_pipeline import offline

V4 = p.ZEBRA_PC_V4
CELL = "5c52438abafc51f1cbbcf4707d5ca519"
TYPO = "5c52438abafc51f1cbbcf4707d6ca519"
OTHER = "a" * 32
TASK = "zebralogic/lgp-test-5x2-23"


def reseal(value, **fields):
    return p.record("trajectory", value["evidence"], {**{key: deepcopy(child) for key, child in value.items()
        if key not in (p.RECORD_HASH, "version", "evidence")}, **fields})


def fixture(*, configuration=V4, cells=(CELL,), tasks=None, shown=(CELL,), mode="train", current=None):
    ctx, workers = context(configuration=configuration, mode=mode)
    tasks = tasks or [TASK if n == 0 else "zebralogic/item-%d" % n for n in range(len(cells))]
    trajectories = [stored(PUBLIC, key=task, cell=cell) for cell, task in zip(cells, tasks)]
    routing = dict((row["task_id"], replay.inputs_of(row)["view"]) for row in trajectories)
    if mode == "train":
        ctx = replace(ctx, trajectories=trajectories,
                      current=current if current is not None else [t for t in trajectories if t["cell"] in shown],
                      round=2 if current is not None else 1, routing_items=list(routing.items()))
    else:
        ctx = replace(ctx, trajectories=trajectories, routing_items=list(routing.items()))
    return ctx, workers


def reference(ctx, given, *, claims=True):
    return {**claim(ctx, claims=claims), "trajectory": given}


def show(ctx):
    e._ask(ctx, e.payload(ctx), "propose")


def entries(*cells):
    return {cell: {"item": TASK if n == 0 else "zebralogic/other-%d" % n} for n, cell in enumerate(cells)}


@pytest.mark.parametrize("given,scope,shown,tasks,expected,rule", [
    (CELL, entries(CELL, OTHER), (), {TASK}, CELL, "exact"),
    (TASK, entries(CELL), (), {TASK}, CELL, "task_id"),
    ("lgp-test-5x2-23", entries(CELL), (), {TASK}, CELL, "task_id"),
    ("lgp-test-5x2-23", entries(CELL), (), {TASK, "different/lgp-test-5x2-23"}, "lgp-test-5x2-23", "unresolved"),
    (TYPO, entries(CELL, OTHER), (), {TASK}, CELL, "near_cell"),
    ("0" + TYPO[1:], entries(CELL, OTHER), (), {TASK}, CELL, "near_cell"),
    ("00" + TYPO[2:], entries(CELL, OTHER), (), {TASK}, "00" + TYPO[2:], "unresolved"),
    (TYPO.upper(), entries(CELL), (), {TASK}, TYPO.upper(), "unresolved"),
    ("g" + CELL[1:], entries(CELL), (), {TASK}, "g" + CELL[1:], "unresolved"),
    (TYPO, entries(CELL, "0" + CELL[1:]), (), {TASK}, TYPO, "unresolved"),
    (TYPO, entries(CELL, "00000" + CELL[5:]), (), {TASK}, TYPO, "unresolved"),
    (TYPO, entries(), (), set(), TYPO, "unresolved"),
])
def test_reference_rules_and_separation_margin(given, scope, shown, tasks, expected, rule):
    assert e._resolve_reference(given, scope, set(shown), tasks) == (expected, rule)


@pytest.mark.parametrize("given", [TASK, TASK.rsplit("/", 1)[-1]])
@pytest.mark.parametrize("visible", [(CELL,), (OTHER,), (), (CELL, OTHER)])
def test_task_id_uses_exactly_one_shown_cell_otherwise_refuses_multiple_cells(given, visible):
    scope = {cell: {"item": TASK} for cell in (CELL, OTHER)}
    found, rule = e._resolve_reference(given, scope, set(visible), {TASK})
    assert found == (visible[0] if len(visible) == 1 else given)
    assert rule == "task_id"


def test_exact_cell_precedes_a_task_alias_with_the_same_string():
    scope = {CELL: {"item": TASK}, OTHER: {"item": CELL}}
    assert e._resolve_reference(CELL, scope, {OTHER}, {TASK, CELL}) == (CELL, "exact")


@pytest.mark.parametrize("mode", ["train", "single"])
@pytest.mark.parametrize("given", [CELL, TASK, TASK.rsplit("/", 1)[-1], TYPO])
def test_real_proposal_build_hash_claim_and_lint_all_use_resolved_ids(mode, given, tmp_path):
    ctx, _ = fixture(mode=mode)
    original = change(ctx, tests=[reference(ctx, given)])
    advisory = {**reference(ctx, given, claims=False), "id": "advisory"}
    original.entry["replay_tests"].append(advisory)
    prefix = [engineer_reply({"findings": []}, [])] if mode == "train" else []
    ctx.roles = WireRoles(prefix + [engineer_reply({"changes": [original.entry]}, [original.source])])
    package, record = e.run_train(ctx) if mode == "train" else e.run(ctx)
    assert package is not None
    procedure = package.procedures[0]
    assert [t["trajectory"] for t in procedure.replay_tests] == [CELL, CELL]
    assert all(row["holds"] for row in record["changes"][0]["attempts"][0]["lint"]["tests"])
    assert next(check for check in record["changes"][0]["attempts"][0]["checks"] if check["check"] == "C5b")["passed"]
    assert record["changes"][0]["procedure_sha256"] == procedure.sha256
    assert record["procedures"][0] == procedure.to_json()
    assert Procedure.from_json(record["procedures"][0]).sha256 == procedure.sha256
    save(tmp_path, package)
    assert load(tmp_path / "packages" / (package.sha256 + ".json")).procedures[0].sha256 == procedure.sha256
    mapping = record["changes"][0]["trajectory_resolution"]
    assert len(mapping) == (0 if given == CELL else 2)
    if mapping:
        assert all(row["given"] == given and row["resolved"] == CELL for row in mapping)
        assert all(row["rule"] == ("near_cell" if given == TYPO else "task_id") for row in mapping)
        wrong = replace(procedure, replay_tests=tuple(original.entry["replay_tests"]))
        assert wrong.sha256 != procedure.sha256


def test_current_training_cell_selected_when_original_run_cell_is_not_shown():
    original = stored(PUBLIC, key=TASK, cell=CELL)
    current = reseal(original, cell=OTHER, unit="D/s1-zebralogic/train-r1", arm_kind="candidate")
    ctx, _ = fixture(current=[current])
    show(ctx)
    proposed = change(ctx, tests=[reference(ctx, TASK)])
    report = e.check(proposed, ctx)
    assert report["passed"] and proposed.procedure.replay_tests[0]["trajectory"] == OTHER
    assert e._feedback_cells(ctx) == {OTHER}
    assert set(e._scope(ctx, e.candidate(ctx.parent, [proposed], step=ctx.step), proposed.procedure)) == {CELL, OTHER}


@pytest.mark.parametrize("kind", ["accept", "generated", "smoke", "reserve", "sealed"])
def test_foreign_ids_and_routing_only_items_are_never_resolution_candidates(kind):
    ctx, _ = fixture()
    show(ctx)
    foreign = "f" * 32
    ctx.routing_items.append(("%s/%s" % (kind, foreign), PUBLIC))
    proposed = change(ctx, tests=[reference(ctx, foreign)])
    report = e.check(proposed, ctx)
    assert report["failed"] == "C5b"
    assert proposed.procedure.replay_tests[0]["trajectory"] == foreign
    detail = next(c["detail"] for c in report["checks"] if c["check"] == "C5b")["failed"][0]
    assert detail["reason"] == "trajectory_not_in_scope"
    assert detail["valid_trajectories"] == [{"trajectory": CELL, "task_id": TASK}]
    assert foreign not in json.dumps(detail["valid_trajectories"])


def test_exclusions_and_suffix_uniqueness_use_scope_and_all_step_tasks():
    ctx, _ = fixture(cells=(CELL, OTHER), tasks=(TASK, "different/lgp-test-5x2-23"))
    show(ctx)
    ambiguous = change(ctx, tests=[reference(ctx, "lgp-test-5x2-23")])
    e._build(ambiguous, ctx)
    assert ambiguous.procedure.replay_tests[0]["trajectory"] == "lgp-test-5x2-23"
    excluded = change(ctx, tests=[reference(ctx, TYPO)])
    excluded.entry["excluded_benches"] = ["zebralogic"]
    single = e._build(excluded, ctx)
    assert e._scope(ctx, single, excluded.procedure) == {}
    assert excluded.procedure.replay_tests[0]["trajectory"] == TYPO


def test_revision_resolves_before_its_hash_and_does_not_inherit_retired_narrowing():
    ctx, _ = fixture()
    old = change(ctx)
    old.entry["excluded_benches"] = []
    parent = e._build(old, ctx)
    parent = with_(parent, step=ctx.step, narrow={old.procedure.id: ["zebralogic"]})
    # Revision context uses this package as S; no training-round rebase is involved.
    ctx = replace(ctx, parent=parent, base=parent)
    show(ctx)
    revised = change(ctx, tests=[reference(ctx, TASK)])
    revised.kind = revised.entry["kind"] = "revision"
    revised.entry["revises"] = old.procedure.id
    single = e._build(revised, ctx)
    assert revised.procedure.replay_tests[0]["trajectory"] == CELL
    assert revised.procedure.lineage["parent"] == old.procedure.sha256
    assert CELL in e._scope(ctx, single, revised.procedure)


@pytest.mark.parametrize("configuration", [V4, p.ZEBRA_PC_V3])
def test_real_fix_resolves_new_reference_and_records_the_attempt_history(configuration):
    ctx, _ = fixture(configuration=configuration)
    first = change(ctx, tests=[reference(ctx, "unresolvable-id")])
    second = change(ctx, tests=[reference(ctx, TASK)])
    third = change(ctx, tests=[reference(ctx, CELL)])
    ctx.roles = WireRoles([engineer_reply({"findings": []}, [])] + [
        engineer_reply({"changes": [item.entry]}, [item.source]) for item in (first, second, third)])
    package, record = e.run_train(ctx)
    assert package is not None
    attempts = record["changes"][0]["attempts"]
    assert [a["failed"] for a in attempts] == (["C5b", None] if configuration == V4 else ["C5b", "C5b", None])
    fixes = [payload for _, payload, _ in ctx.roles.seen if payload.get("request") == "fix"]
    failure = fixes[0]["failed"]["detail"]["failed"][0]
    assert ("valid_trajectories" in failure) is (configuration == V4)
    if configuration == V4:
        assert failure["valid_trajectories"] == [{"trajectory": CELL, "task_id": TASK}]
        assert failure["valid_trajectories_total"] == 1
        assert fixes[0]["trajectory_resolution"][0]["rule"] == "unresolved"
        assert [row["rule"] for row in record["changes"][0]["trajectory_resolution"]] == ["unresolved", "task_id"]
    else:
        assert "trajectory_resolution" not in record["changes"][0] and "trajectory_resolution" not in fixes[0]


@pytest.mark.parametrize("configuration", [V4, p.ZEBRA_PC_V3])
def test_invalid_advisory_reference_help_survives_persistence_and_next_round(configuration):
    ctx, _ = fixture(configuration=configuration)
    proposed = change(ctx, tests=[reference(ctx, "unresolved-advisory", claims=False)])
    ctx.roles = WireRoles([engineer_reply({"findings": []}, []),
                          engineer_reply({"changes": [proposed.entry]}, [proposed.source])])
    package, record = e.run_train(ctx)
    assert package is not None
    lint = json.loads(json.dumps(record["lint"]))
    problem = lint[0]["problems"][0]
    assert problem["detail"] == "trajectory_not_in_scope"
    assert ("valid_trajectories" in problem) is (configuration == V4)
    if configuration == V4:
        assert problem["valid_trajectories_total"] == 1
        assert problem["valid_trajectories"] == [{"trajectory": CELL, "task_id": TASK}]
    next_ctx = replace(ctx, round=2, lint=lint, roles=WireRoles())
    e.run_train(next_ctx)
    assert next(payload for _, payload, _ in next_ctx.roles.seen if payload.get("request") == "propose")["lint"] == lint


def test_valid_reference_help_is_sorted_bounded_and_only_shown_in_scope():
    scope = {"cell-%02d" % n: {"item": "task-%02d" % (n // 2)} for n in reversed(range(50))}
    shown = {"cell-%02d" % n for n in range(45)} | {"not-in-scope"}
    help_ = replay.valid_trajectories(scope, shown)
    assert help_["valid_trajectories_total"] == 45 and len(help_["valid_trajectories"]) == 20
    assert help_["valid_trajectories"] == [{"trajectory": "cell-%02d" % n, "task_id": "task-%02d" % (n // 2)}
                                          for n in range(20)]
    assert replay.valid_trajectories_shape(help_)
    assert replay.valid_trajectories(scope, ()) == {"valid_trajectories": [], "valid_trajectories_total": 0}


def test_resolution_logs_are_bounded_and_resolution_does_not_relax_test_truth():
    ctx, _ = fixture()
    show(ctx)
    proposed = change(ctx, tests=[{**reference(ctx, "x" * 2000), "id": "y" * 2000} for _ in range(20)])
    e._resolve_change(proposed, ctx)
    assert len(proposed.trajectory_resolution) == e.MAX_TESTS
    assert all(len(row[key]) <= 256 for row in proposed.trajectory_resolution for key in ("test", "given", "resolved"))
    false = reference(ctx, TYPO)
    false["property"]["value"] = "Not actually returned."
    proposed = change(ctx, tests=[false])
    report = e.check(proposed, ctx)
    assert proposed.procedure.replay_tests[0]["trajectory"] == CELL
    assert report["failed"] == "C5b"
    assert next(c["detail"] for c in report["checks"] if c["check"] == "C5b")["failed"][0]["reason"] == "test_failed"


@pytest.mark.parametrize("mode", ["train", "single"])
def test_reference_and_determinism_instructions_reach_only_v4_engineer_requests(mode):
    for configuration in (name for name in p.CONFIGURATIONS if not p.is_v210(name) and not p.is_v213(name)):
        for purpose in ("propose", "repropose", "fix/1"):
            ctx, _ = fixture(configuration=configuration, mode=mode)
            ctx.roles = WireRoles()
            e._ask(ctx, {"request": purpose, "trajectories": []}, purpose)
            system = ctx.roles.wire[0]["system"]
            assert (e.ENGINEER_FACTS_V26 in system) is (configuration == V4)
            if configuration == V4:
                expected = e.ENGINEER_SYSTEM_ZPC_V26 if mode == "train" else e.ENGINEER_SYSTEM_SINGLE_ZPC_V26
                assert system == expected
                for fact in ("shown trajectory's cell", "only when unambiguous", "trajectory_resolution",
                             "PYTHONHASHSEED=0", "PYTHONHASHSEED=1", "reverse order", "(5 s)",
                             "set/frozenset", "wall-clock", "state carried across items", "id()/hash()",
                             "Sort before iterating", "deterministic counters"):
                    assert fact in system
