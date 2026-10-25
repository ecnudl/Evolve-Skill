"""v2.5 coverage uses actual shell delivery and run-item counts; synthetic offline fixtures only."""
import copy
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.coevo5.calls import _request_hash
from skillopt.execskill import notes, policy, profiles as p, reuse, rounds, solver, step, zebralogic as z
from skillopt.execskill.package import FIXTURE, Package, Procedure, empty, save, with_
from tests import test_execskill_zpc_pipeline as fixture
from tests.test_execskill_zpc_pipeline import offline


PUBLIC = {"question": "There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street. "
                     "A public clue mentions format.", "columns": ["Color"]}


def procedure(ident, *, fields=None, source=None, cap=4000, lineage=None):
    source = source or ("def applies(view):\n    return True\ndef before_call(view, state):\n    return "
                        + repr(fields or {}) + "\n")
    return Procedure(id=ident.replace("p-", "fx-", 1), origin=z.BENCH, description="Checks public clues.",
        hooks=("applies", "before_call"), source=source, evidence=FIXTURE, max_note_chars=cap,
        excluded_benches=p.BENCHES, policy_version=policy.POLICY_VERSION_V25,
        **({"lineage": lineage} if lineage is not None else {}))


def package(*procedures):
    return Package(procedures, "D/s1-zebralogic", FIXTURE)


def trace(pack, *, key="zebralogic/run-a", cell="cell-a", view=PUBLIC, run=0):
    """Run only authored hooks through the real note screen/renderer/assembler, never a model endpoint."""
    worker = fixture.SourceWorker().start(pack, kind="cell")
    def forbidden(*args, **kwargs):
        pytest.fail("Coverage fixtures do not call a model")
    shell = solver._Shell(z.BENCH, pack, forbidden, worker, withhold=(), restore=(), placebo=None,
                          text=None, native=None, nominal=None)
    shell.started = True
    try:
        shell.route_on(view)
        text, _ = shell.before(view, solver._public_text(view))
        system, user = solver._system(z.BENCH, z.CARD_TEXT, {}), solver._user(z.BENCH, view, text)
        return {"cell": cell, "task_id": key, "bench": z.BENCH, "arm": "S'", "arm_kind": "candidate",
                "run": run, "token": "fail", "calls": [{"user": user, "system": system,
                    "request_sha256": _request_hash(system, user), "receipt": {"delivery": "delivered"}}],
                "replies": ["An authored final response."],
                "shell": {"notes": copy.deepcopy(shell.notes), "faults": copy.deepcopy(shell.faults)}}
    finally:
        worker.close()


def coverage(pid, pack, rows, *, enabled=None, identical=(), current=(), captured=None):
    made = {row["cell"]: row for row in rows}
    cells = {}
    for row in rows:
        cells.setdefault(("S'", row["task_id"]), []).append({"cell": {"id": row["cell"]},
            "faults": copy.deepcopy(row["shell"]["faults"])})
    keys = sorted(set(row["task_id"] for row in rows)) if enabled is None else enabled
    return step._notes_coverage(SimpleNamespace(bench=z.BENCH), pid, keys, pack, cells, made,
                                current, set(identical), captured or {})


def counts(items, with_notes=0, faults=0, **fields):
    return {"items": items, "with_notes": with_notes,
            "fields": {name: fields.get(name, 0) for name in notes.FIELD_ORDER}, "faults": faults}


def test_coverage_counts_distinct_items_and_fields_after_screening_and_binding_validation():
    fields = {"facts": ["Check the public clues."], "table": [["format"]],
              "candidates": ["Consider adjacent houses."], "warnings": ["Check uniqueness."],
              "bindings": [{"name": "houses", "value": "5", "quote": "There are 5 houses"}]}
    proc = procedure("p-coverage", fields=fields)
    pack = package(proc)
    rows = [trace(pack, cell="first"), trace(pack, cell="repeat", run=1)]
    assert coverage(proc.id, pack, rows) == counts(1, 1, **{name: 1 for name in notes.FIELD_ORDER})
    assert coverage(proc.id, pack, rows + rows) == coverage(proc.id, pack, rows)


def test_coverage_counts_fault_item_once_and_keeps_the_valid_delivered_field():
    proc = procedure("p-mixed", fields={"facts": "not a list", "table": "not rows",
                                      "warnings": ["Check the public clues."]})
    pack = package(proc)
    rows = [trace(pack, cell="first"), trace(pack, cell="again", run=1)]
    assert len(rows[0]["shell"]["faults"]) == 2
    assert coverage(proc.id, pack, rows) == counts(1, 1, 1, warnings=1)


def test_coverage_omits_total_cap_and_declared_cap_notes_even_when_text_matches_another_procedure():
    fields = {"facts": ["Clues relate the houses. " * 6] * 20}
    first, total_skipped, own_skipped = (procedure("p-first", fields=fields),
        procedure("p-total", fields=fields), procedure("p-declared", fields=fields, cap=8))
    pack = package(first, total_skipped, own_skipped)
    row = trace(pack)
    assert all(note["rendered_chars"] > 2000 for note in row["shell"]["notes"])
    assert coverage(first.id, pack, [row]) == counts(1, 1, facts=1)
    assert coverage(total_skipped.id, pack, [row]) == counts(1)
    assert coverage(own_skipped.id, pack, [row]) == counts(1, faults=1)


@pytest.mark.parametrize("delivery,expected", [("delivered", 1), ("truncated", 1),
    ("undelivered:transport", 0), ("noncompletion:content_filter", 0)])
def test_coverage_requires_a_delivered_request_and_does_not_change_the_item_denominator(delivery, expected):
    proc = procedure("p-note", fields={"facts": ["Check all public clues."]})
    pack = package(proc)
    row = trace(pack)
    row["calls"][0]["receipt"]["delivery"] = delivery
    assert coverage(proc.id, pack, [row]) == counts(1, expected, facts=expected)


def test_coverage_refuses_stored_fields_that_do_not_match_the_actual_request():
    proc = procedure("p-note", fields={"facts": ["Check all public clues."]})
    pack = package(proc)
    row = trace(pack)
    row["calls"][0]["user"] = z.render_user(PUBLIC)
    with pytest.raises(ValueError, match="actual solver request"):
        coverage(proc.id, pack, [row])


def test_signature_observation_is_transient_and_does_not_repeat_hooks_or_change_identity():
    proc = procedure("p-note", fields={"facts": ["Check all public clues."]})
    pack = package(proc)
    found = []
    def observe(shell, text):
        found.append(step._shown_note_fields(z.BENCH, pack, shell.notes, PUBLIC, text))
    with fixture.workers(pack) as first, fixture.workers(pack) as second:
        baseline = reuse.signature(z.BENCH, pack, PUBLIC, first, card_text=z.CARD_TEXT)
        observed = reuse.signature(z.BENCH, pack, PUBLIC, second, card_text=z.CARD_TEXT, note_observer=observe)
        assert observed == baseline
        assert first.calls == second.calls
    assert found == [{proc.id: {"facts"}}]
    assert "notes_coverage" not in observed and "fields" not in observed


def test_identical_request_uses_candidate_attribution_and_requires_the_incumbents_delivered_request():
    # An empty added procedure must not inherit the old note; a new replacement with another id must get credit.
    old = procedure("p-old", fields={"facts": ["Check all public clues."]})
    new = procedure("p-new", fields={"facts": ["Check all public clues."]})
    idle = procedure("p-empty")
    source, candidate = package(old), package(new, idle)
    row = trace(source)
    capture = {}
    with fixture.workers(candidate) as worker:
        signature = reuse.signature(z.BENCH, candidate, PUBLIC, worker, card_text=z.CARD_TEXT,
            note_observer=lambda shell, text: capture.update(step._shown_note_fields(
                z.BENCH, candidate, shell.notes, PUBLIC, text)))
    assert row["calls"][0]["request_sha256"] == signature["request_sha256"]
    key = row["task_id"]
    captured = {key: {"request_sha256": signature["request_sha256"], "fields": capture}}
    given = {"enabled": [key], "identical": [key], "current": [row], "captured": captured}
    assert coverage(new.id, candidate, [], **given) == counts(1, 1, facts=1)
    assert coverage(idle.id, candidate, [], **given) == counts(1)
    row["calls"][0]["request_sha256"] = "0" * 64
    assert coverage(new.id, candidate, [], **given) == counts(1)


def test_real_training_coverage_has_run_enabled_denominator_reused_row_and_fault_cell(tmp_path, monkeypatch):
    from skillopt.execskill import engineer
    from tests.execskill_fakes import engineer_reply

    setting, services, fake_solver, glm = fixture.build(tmp_path, monkeypatch, effect="no_gain")
    setting = replace(setting, extra={**setting.extra, "configuration": p.ZEBRA_PC_V3})
    cut = z.slices(setting.pools[z.BENCH])
    cut["run"] = cut["run"][:6]
    labels = ("same", "table", "fault", "empty", "disabled", "empty-again")
    for item, label in zip(cut["run"], labels):
        item["public"]["question"] += "\nCoverage case: " + label
    old_source = '''def applies(view):
    return "Coverage case: disabled" not in view["question"]
def before_call(view, state):
    if "Coverage case: same" in view["question"]:
        return {"facts": ["Check all public clues."]}
    return {}
'''
    new_source = old_source.replace("    return {}", '''    if "Coverage case: table" in view["question"]:
        rows = [line.split(" | ") for line in view["question"].splitlines() if line.startswith("House ")]
        return {"table": [["House"] + view["columns"]] + rows}
    if "Coverage case: fault" in view["question"]:
        return {"facts": "not a list", "warnings": ["Check the public clues."]}
    return {}''')
    old = procedure("p-old", source=old_source)
    parent = with_(empty(step="D/s0", evidence=FIXTURE), step="D/s0", add=[old])
    new = procedure("p-new", source=new_source,
                    lineage={"parent": old.sha256, "revises": old.id, "engineer_call": None})
    candidate = with_(parent, step="D/s1-zebralogic", revise=[new])
    save(setting.root / "D", parent)
    save(setting.root / "D", candidate)
    st = step._Step(setting, services, "D", z.BENCH, 1, parent, setting.root / "D")
    step._run(st, cut)
    current = step._run_trajectories(st, parent_only=True)
    foreign = copy.deepcopy(cut["run"][1])
    foreign["public"]["question"] += "\nGENERATED-COVERAGE-SENTINEL"
    generated = {"generator": {"status": "admitted"}, "g_self": [p.record("generated-item", FIXTURE,
        {"id": "generated-only", "benchmark": z.BENCH, "public": foreign["public"], "private": foreign["private"]})]}
    result = step._train_eval(st, cut, 1, parent, candidate, generated, current=current)
    feedback = result["feedback"]
    rows = {row["id"]: row for row in feedback["procedures"]}
    assert rows[new.id]["enabled_items"] == 5
    assert rows[new.id]["notes_coverage"] == counts(5, 3, 1, facts=1, table=1, warnings=1)
    assert rows[old.id]["notes_coverage"] == counts(0)
    assert result["cells"] == 6  # two real run pairs plus one generated pair; three T2 rows have no cells
    assert result["verdict"]["generated"] == 1
    assert set(result["identical"]) == {rounds.key(z.BENCH, cut["run"][i]["task_id"]) for i in (0, 3, 5)}
    assert any(row["source"] == "identical_current" for row in feedback["unfixed_examples"])
    assert "GENERATED-COVERAGE-SENTINEL" not in json.dumps(feedback)
    assert "fields" not in next(iter(result["request_signatures"].values()))["S'"]
    assert glm.seen == []
    calls = len(fake_solver.requests)
    assert step._train_eval(st, cut, 1, parent, candidate, generated, current=current) == result
    assert len(fake_solver.requests) == calls
    other_roles = glm.replies
    glm.replies = lambda system, payload: (engineer_reply({"changes": []}, [])
        if system == engineer.ENGINEER_SYSTEM_ZPC_V25 else other_roles(system, payload))
    step._engineer_train(st, cut, 2, parent, done=[("train-r1", False)], fed="train-r1", history=[],
        training=feedback, lint=[], reserved=frozenset(), analysed=frozenset(), disclosed=frozenset(),
        generated=generated)
    proposals = [payload for system, payload in glm.seen if system == engineer.ENGINEER_SYSTEM_ZPC_V25]
    assert len(proposals) == 1
    assert proposals[0]["training"]["procedures"] == feedback["procedures"]
    assert "GENERATED-COVERAGE-SENTINEL" not in json.dumps(glm.seen)
    assert len(fake_solver.requests) == calls


@pytest.mark.parametrize("configuration", [p.MAIN_V2_3, p.ZEBRA_PC_V1, p.ZEBRA_PC_V2])
def test_older_feedback_procedures_never_gain_coverage(configuration, tmp_path):
    from tests.test_execskill_v24_training import add_cell, feedback_fixture, trajectory
    st, cut, _ = feedback_fixture(tmp_path, configuration=configuration, count=1)
    proc = procedure("p-added", fields={"facts": ["Check the clues."]})
    parent, candidate = empty(step="D/s0", evidence=FIXTURE), package(proc)
    cells, made = {}, {}
    for arm in ("S", "S'"):
        add_cell(cells, made, trajectory(cut["run"][0], arm, "fail"))
    key = rounds.key(z.BENCH, cut["run"][0]["task_id"])
    verdict = step.train_verdict(cells, [key], [], {proc.id}, predicate_faults=0, routed=1, sign=False)
    result = step._feedback(st, cut, "train-r1", verdict,
                            {key: {"incumbent": [], "candidate": [proc.id]}}, parent, candidate, cells, made)
    assert "notes_coverage" not in result["procedures"][0]
