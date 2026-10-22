"""T-PLACEBO-1..6 (implementation plan §8; registration §6.1 placebo rows and "替身的细则", Codex F4/F5; ticket A6-1):
the frozen donor corpus and the P_y / P_i content, built with the in-process FakeSandbox and shown through the route-B
shell with the fakes of tests/execskill_fakes_env.py. Offline and deterministic; no model call anywhere."""
from __future__ import annotations

import json
import re
import socket
from contextlib import contextmanager

import pytest

from skillopt.continual_eval import backends
from skillopt.continual_eval.code_delivery import extract_python
from skillopt.execskill import donors, notes, placebo, router, solver
from skillopt.execskill.errors import ConfigurationError
from skillopt.execskill.package import empty, with_
from skillopt.execskill.protocol import COMPUTE_INVITE, NOT_EVALUATED, NOTES_KEY, PLACEBO_CORPUS, discourage_tag
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import FakeNative, FakeSandbox, Script, procedure
from tests.fixtures.execskill.items import officeqa_items, spreadsheetbench_items

EVIDENCE = "smoke"
UNIT = "pilot/s2-officeqa/accept"
CARD = "Read the table rows before computing."
PARENT = empty(step="s1", evidence=EVIDENCE)
NOTE = procedure("p-officeqa-2-1", ("applies", "before_call"), header="Row helper notes.")
BIND = procedure("p-officeqa-2-2", ("applies", "bindings"), requests_second_call=True)
SHEET = procedure("p-spreadsheetbench-2-1", ("applies", "sheet_feedback"), requests_second_call=True)
STEPS = procedure("p-alfworld-2-1", ("applies", "alf_before_step", "alf_after_step"))
QA_CANDIDATE = with_(PARENT, step="s2", add=[NOTE, BIND])
SHEET_CANDIDATE = with_(PARENT, step="s2", add=[SHEET])
ALF_CANDIDATE = with_(PARENT, step="s2", add=[STEPS])
ITEMS = officeqa_items(10)
ACCEPT, RUN = ITEMS[:6], ITEMS[6:]  # the run slice never overlaps the acceptance slice
VIEWS = {item["task_id"]: solver.routing_view("officeqa", item["public"]) for item in ACCEPT}
# the frozen sheet solver's runtime and a program whose pre-check fails (tests/test_execskill_solver.py)
SHEET_RUNTIME = {"prompt_layout": "contract-first-v2", "code_extraction_version": "explicit-python-fences-v1",
                 "spreadsheet_preview_version": "public-formula-preview-v1", "_stop_on_cleanup_failure": True,
                 "image": "sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd",
                 "timeout_seconds": 300, "memory_mb": 4096, "cpus": 1}
PROGRAM = ("```python\nimport openpyxl\nbook = openpyxl.load_workbook('input.xlsx')\n"
           "book.active['B1'] = '=SUM(A1:A5)'\nbook.save('output.xlsx')\n```")
REPAIRED = PROGRAM.replace("A1:A5", "A1:A6")
ERROR_REPORT = {"status": "exception", "exc_type": "KeyError", "message": "KeyError: 'Sheet2'"}


def first_row(view):
    return re.search(r"2019 \| (\d+)", view["context"])


def row_note(view, state):
    return {"facts": ["The first data row reads: %s." % first_row(view).group(0), "The page has a receipts table."]}


def customs(view):
    found = first_row(view)
    return {"bindings": [{"name": "customs_2019", "quote": found.group(0), "value": found.group(1)}]}


def advice(view, report, state):
    return {"fields": {"warnings": ["Check the sheet named in the program: %s" % report["message"]]},
            "request_repair": report["status"] == "exception"}


def before_step(view, state):
    return {"fields": {"facts": ["Steps taken so far: %d." % (state or 0)]}, "discourage": ["inventory", "jump"]}


QA_HOOKS = {NOTE.id: {"before_call": row_note}, BIND.id: {"bindings": customs}}
SHEET_HOOKS = {SHEET.id: {"sheet_feedback": advice}}
ALF_HOOKS = {STEPS.id: {"alf_before_step": before_step, "alf_after_step": lambda event, state: (state or 0) + 1}}


def workers(table, seen=None):
    @contextmanager
    def worker(package, item):
        sandbox = FakeSandbox(table).start(package, kind="cell")
        try:
            yield sandbox
        finally:
            sandbox.close()
            if seen is not None:
                seen.extend(sandbox.calls)
    return worker


def qa_trajectory(item):
    view = solver.routing_view("officeqa", item["public"])
    return {"cell": "pilot/s2-officeqa/run/S/%s/0" % item["task_id"], "task_id": item["task_id"], "bench": "officeqa",
            "arm_kind": "parent", "calls": [{"purpose": "first", "user": json.dumps(view)}], "shell": {"precheck": None}}


def sheet_trajectory(k):
    report = {"status": "exception", "exc_type": "KeyError", "message": "KeyError: 'Donor%d'" % k}
    return {"cell": "pilot/s2-spreadsheetbench/run/S/run-%02d/0" % k, "task_id": "run-%02d" % k,
            "bench": "spreadsheetbench", "calls": [{"purpose": "first", "user": json.dumps({"instruction": "Fill B%d"
                                                                                          % k})}],
            "arm_kind": "parent", "shell": {"precheck": report}}


def alf_trajectory(k, steps):
    views = [{"initial_observation": "You are in room %d." % k, "observation": "You see %d shelves." % s,
              "admissible_commands": ["look", "go to shelf %d" % s, "inventory"]} for s in range(steps)]
    return {"cell": "pilot/s2-alfworld/run/S/run-%02d/0" % k, "task_id": "run-%02d" % k, "bench": "alfworld",
            "arm_kind": "parent", "calls": [{"purpose": "step", "user": json.dumps(view)} for view in views],
            "alfworld_steps": [{"action": "go to shelf %d" % s} for s in range(steps)], "shell": {"precheck": None}}


QA_TRAJECTORIES = [qa_trajectory(item) for item in RUN]


def qa_round(seen=None):
    corpus = donors.donor_corpus(QA_CANDIDATE, PARENT, QA_TRAJECTORIES, workers(QA_HOOKS, seen))
    changed = donors.changed(PARENT, QA_CANDIDATE)
    pairs = donors.pair(list(VIEWS), corpus, UNIT)["pairs"]
    lengths = placebo.real_lengths(changed, VIEWS, workers(QA_HOOKS, seen), bench="officeqa",
                                   packages={"candidate": QA_CANDIDATE, "parent": PARENT})
    return {"corpus": corpus, "changed": changed, "pairs": pairs, "lengths": lengths,
            "content": placebo.build_y(corpus, pairs, lengths, changed=changed)}


@pytest.fixture(scope="module")
def qa():
    return qa_round()


@pytest.fixture(scope="module")
def alf():
    trajectories = [alf_trajectory(0, 3), alf_trajectory(1, 1)]
    corpus = donors.donor_corpus(ALF_CANDIDATE, PARENT, trajectories, workers(ALF_HOOKS))
    pairs = donors.pair(["game-%02d" % k for k in range(4)], corpus, "pilot/s2-alfworld/accept")["pairs"]
    return {"corpus": corpus, "pairs": pairs,
            "content": placebo.build_y(corpus, pairs, {}, changed=donors.changed(PARENT, ALF_CANDIDATE))}


# ------------------------------------------------------------------- T-PLACEBO-1 donor pairing and steps
def test_t_placebo_1_one_donor_per_item_by_seed_and_the_last_step_beyond_the_end(qa, alf):
    corpus = qa["corpus"]
    pairs = donors.pair(list(VIEWS), corpus, UNIT)
    assert pairs == router.yoke(list(VIEWS), corpus["donors"], UNIT) == donors.pair(list(reversed(VIEWS)), corpus,
                                                                                     UNIT)
    assert set(pairs["pairs"]) == set(VIEWS) and set(pairs["pairs"].values()) <= set(corpus["donors"])
    assert sum(pairs["reuse"].values()) == 6 and max(pairs["reuse"].values()) == 2  # 6 items, 4 donors, reuse counted
    assert {item: entry["donor"] for item, entry in qa["content"].items()} == pairs["pairs"]
    # ALFWorld: the stored episode replayed step by step, the state carried; beyond the donor's end, its last step
    steps = alf["corpus"]["outputs"][STEPS.id]
    three, one = alf["corpus"]["donors"]
    assert [e["fields"]["facts"] for e in steps[three][donors.STEP_HOOK]] == [
        ["Steps taken so far: %d." % s] for s in range(3)]
    assert [e["discourage"] for e in steps[three][donors.STEP_HOOK]] == [1, 1, 1]  # admissible commands only
    assert donors.output(alf["corpus"], STEPS.id, three, donors.STEP_HOOK, step=9) == steps[three][donors.STEP_HOOK][2]
    assert donors.output(alf["corpus"], STEPS.id, one, donors.STEP_HOOK, step=4) == steps[one][donors.STEP_HOOK][0]
    for item, donor in alf["pairs"].items():
        assert alf["content"][item]["procedures"][STEPS.id][donors.STEP_HOOK] == steps[donor][donors.STEP_HOOK]


# ------------------------------------------------------------------------------- T-PLACEBO-2 length band
def test_t_placebo_2_the_length_band(qa):
    keep = {"bench": "officeqa", "header": NOTE.header, "cap": NOTE.max_note_chars}
    assert placebo.band(100, 600) == (80, 120) and placebo.band(1000, 600) == (600, 600)
    one = {"facts": ["a" * 60]}
    size = placebo.rendered(one, bench="officeqa", header=NOTE.header)
    assert placebo.sham_fields([one], size, **keep) == (one, {"target": size, "chars": size, "within": True,
                                                              "action": "kept"})
    fields, record = placebo.sham_fields([{"facts": ["word " * 39 + "word", "a second entry"]}], size, **keep)
    assert record["action"] == "clipped" and record["within"] and len(fields["facts"]) == 1
    assert fields["facts"][0].startswith("word word") and record["chars"] <= size * 1.2
    short, more = {"facts": ["a" * 20]}, {"facts": ["b" * 30, "c" * 30]}
    target = placebo.rendered({"facts": ["a" * 20, "b" * 30, "c" * 30]}, bench="officeqa", header=NOTE.header)
    fields, record = placebo.sham_fields([short, more], target, **keep)
    assert record["action"] == "extended" and record["within"] and fields == {"facts": ["a" * 20, "b" * 30, "c" * 30]}
    fields, record = placebo.sham_fields([short], 500, **keep)
    assert record["action"] == "short" and not record["within"] and fields == short
    assert placebo.sham_fields([one], 0, **keep) == ({}, {"target": 0, "chars": 0, "within": True,
                                                          "action": "nothing"})
    _, record = placebo.sham_fields([{"facts": ["x" * 200] * 5}], 2000, **keep)
    assert record["chars"] == NOTE.max_note_chars  # never beyond the procedure's note cap
    # the target is the real note's length on the acceptance item, computed with zero model calls
    for item, entry in qa["content"].items():
        for label, band in entry["bands"].items():
            procedure_id, hook = label.split("/")
            assert band["target"] == qa["lengths"][procedure_id][item][hook] > 0 and band["within"]


# ------------------------------------------------------------------------------ T-PLACEBO-3 header kept
def test_t_placebo_3_the_shell_keeps_the_header_and_shows_the_donor_content(qa):
    item = ACCEPT[0]
    donor = qa["content"][item["task_id"]]["donor"]
    donor_view = json.loads(next(t for t in QA_TRAJECTORIES if t["cell"] == donor)["calls"][0]["user"])
    sandbox, call = FakeSandbox(QA_HOOKS), Script(["<answer>1</answer>"])
    routed = solver.solve("officeqa", item["public"], CARD, QA_CANDIDATE, call, worker=sandbox,
                          placebo=placebo.arm(qa["content"], item["task_id"], seed=discourage_tag(UNIT, "cell-1")))
    shown = json.loads(call.requests[0][1])[NOTES_KEY]
    assert shown.startswith(NOTE.header + "\n")
    assert first_row(donor_view).group(0) in shown and first_row(VIEWS[item["task_id"]]).group(0) not in shown
    assert sandbox.called("before_call") == [] and sandbox.called("bindings") == []
    assert len(sandbox.called("applies")) == 2  # the predicates run as in S'
    assert routed["shell"]["arm"]["placebo"] == sorted([NOTE.id, BIND.id])


# ------------------------------------------------------------------------------ T-PLACEBO-4 compute sham
def test_t_placebo_4_compute_sham_answers_not_evaluated_and_echoes_the_expression(qa):
    item = ACCEPT[1]
    replies = ["<calc>customs_2019 * 2</calc>", "<answer>1</answer>"]
    call = Script(replies)
    solver.solve("officeqa", item["public"], CARD, QA_CANDIDATE, call, worker=FakeSandbox(QA_HOOKS),
                 placebo=placebo.arm(qa["content"], item["task_id"], seed=discourage_tag(UNIT, "cell-2")))
    first, second = (json.loads(user) for _, user in call.requests)
    assert first[NOTES_KEY].endswith("\n\n" + COMPUTE_INVITE)
    assert second["computed"] == [{"expr": "customs_2019 * 2", "value": NOT_EVALUATED}]
    real = Script(replies)  # S' evaluates the same expression with the item's own binding
    solver.solve("officeqa", item["public"], CARD, QA_CANDIDATE, real, worker=FakeSandbox(QA_HOOKS))
    value = int(first_row(VIEWS[item["task_id"]]).group(1))
    assert json.loads(real.requests[1][1])["computed"] == [{"expr": "customs_2019 * 2", "value": str(2 * value)}]


# ------------------------------------------------------------------------- T-PLACEBO-5 repair sham, shadow
def test_t_placebo_5_repair_sham_keeps_program_and_error_and_triggers_like_the_real_hook(tmp_path, monkeypatch):
    native = FakeNative(report=ERROR_REPORT).install(monkeypatch)
    item = spreadsheetbench_items(tmp_path, 1)[0]
    corpus = donors.donor_corpus(SHEET_CANDIDATE, PARENT, [sheet_trajectory(k) for k in range(3)],
                                 workers(SHEET_HOOKS))
    content = placebo.build_y(corpus, {item["task_id"]: corpus["donors"][1]}, {},
                              changed=donors.changed(PARENT, SHEET_CANDIDATE))
    assert content[item["task_id"]]["procedures"][SHEET.id] == {
        "sheet_feedback": {"warnings": ["Check the sheet named in the program: KeyError: 'Donor1'"]}}
    sham = placebo.arm(content, item["task_id"], seed=discourage_tag(UNIT, "cell-3"))

    def run(arm):
        call = Script([PROGRAM, REPAIRED])
        routed = solver.solve("spreadsheetbench", item["public"], CARD, SHEET_CANDIDATE, call, runtime=SHEET_RUNTIME,
                              worker=FakeSandbox(SHEET_HOOKS), placebo=arm)
        return call, [c["purpose"] for c in routed["shell"]["calls"]]

    (real_call, real), (sham_call, shammed) = run(None), run(sham)
    repair = json.loads(sham_call.requests[1][1])
    assert repair["previous_program"] == extract_python(PROGRAM)["code"] and repair["run_report"] == ERROR_REPORT
    assert "Donor1" in repair["repair_notes"] and "Sheet2" not in repair["repair_notes"]
    assert "Sheet2" in json.loads(real_call.requests[1][1])["repair_notes"]
    assert shammed == real == ["first", "repair"]  # the shadow of the real hook triggers the repair
    native.report = {"status": "ok", "answer_cells": {"Sheet!B1": "=SUM(A1:A5)"}}
    assert run(sham)[1] == run(None)[1] == ["first"]


# ------------------------------------------------------- T-PLACEBO-6 zero calls, sealing, no acceptance text
def test_t_placebo_6_donors_are_zero_call_sealed_and_free_of_acceptance_text(monkeypatch, alf):
    def no_model_call(*args, **kwargs):
        raise AssertionError("a model call or a network connection")

    for target, name in ((solver, "solve"), (backends, "solve"), (socket.socket, "connect")):
        monkeypatch.setattr(target, name, no_model_call)
    seen = []
    built = qa_round(seen)
    corpus = built["corpus"]
    assert seen and {fn for _, fn, _ in seen} == {"before_call", "bindings"}  # the sandbox ran, nothing else
    assert corpus["version"] == "fivebench-execskill-v1-donor-corpus" and corpus["evidence"] == EVIDENCE
    assert corpus["candidate_sha256"] == QA_CANDIDATE.sha256 and corpus["parent_sha256"] == PARENT.sha256
    assert corpus["sources"] == {t["cell"]: digest(t) for t in QA_TRAJECTORIES} and corpus["faults"] == []
    assert all(corpus["hashes"][p][d] == digest(out) for p, per in corpus["outputs"].items() for d, out in per.items())
    assert donors.seal(corpus) == corpus["record_sha256"]
    tampered = json.loads(json.dumps(corpus))
    tampered["outputs"][NOTE.id][corpus["donors"][0]]["before_call"] = {"facts": ["other"]}
    with pytest.raises(ValueError):
        donors.seal(tampered)
    moved = json.loads(json.dumps(QA_TRAJECTORIES))
    moved[2]["shell"]["precheck"] = {"status": "ok"}
    with pytest.raises(ConfigurationError, match="sealed_input_changed"):
        donors.verify(corpus, moved)
    sealed_text = json.dumps([corpus, built["content"]])
    assert not [v for v in VIEWS.values() if first_row(v).group(0) in sealed_text]  # no acceptance-item text
    assert all(first_row(json.loads(t["calls"][0]["user"])).group(0) in sealed_text for t in QA_TRAJECTORIES)
    # ALFWorld keeps the NUMBER of discouraged commands; the commands are drawn at dispatch with the cell's seed
    for entry in alf["content"].values():
        assert all(type(step["discourage"]) is int for step in entry["procedures"][STEPS.id][donors.STEP_HOOK])
    assert "inventory" not in json.dumps(alf["content"])
    item = sorted(alf["content"])[0]
    arm = placebo.arm(alf["content"], item, seed=discourage_tag("pilot/s2-alfworld/accept", "cell-9"))
    assert arm["seed"] == "execskill-v1:discourage:pilot/s2-alfworld/accept:cell-9"
    assert placebo.sham_discourage is solver.sham_discouraged
    admissible = ["look", "go to shelf 0", "inventory"]
    drawn = placebo.sham_discourage(admissible, 1, arm["seed"], 0)
    assert len(drawn) == 1 and set(drawn) <= set(admissible)
    assert drawn == placebo.sham_discourage(admissible, 1, arm["seed"], 0)


# --------------------------------------------------------------------------------- P_i (descriptive)
def test_p_i_shows_the_registered_irrelevant_text_at_the_sham_length(qa):
    procedures = {p.id: p for _, p, _ in qa["changed"]}
    content = placebo.build_i(qa["content"], procedures, bench="officeqa", unit=UNIT)
    assert placebo.build_i(qa["content"], procedures, bench="alfworld", unit=UNIT) is None
    assert placebo.build_i(qa["content"], procedures, bench="searchqa", unit=UNIT) is None
    assert set(content) == set(qa["content"])
    for item, entry in content.items():
        text = placebo.irrelevant_text(item, UNIT)
        assert text in PLACEBO_CORPUS and text == placebo.irrelevant_text(item, UNIT)
        for procedure_id, hooks in entry["procedures"].items():
            procedure = procedures[procedure_id]
            for hook, fields in hooks.items():
                assert set(fields) == {"facts"} and notes.screen(fields, bench="officeqa") == (fields, [])
                assert " ".join(text.split() * 20).startswith(" ".join(fields["facts"]))  # cut at spaces or clipped
                sham = qa["content"][item]["procedures"][procedure_id][hook]
                lower, upper = placebo.band(placebo.rendered(sham, bench="officeqa", header=procedure.header),
                                            procedure.max_note_chars)
                assert lower <= placebo.rendered(fields, bench="officeqa", header=procedure.header) <= upper
    parts = placebo.chunks("alpha beta gamma", 3)
    assert len(parts) == 3 and all(len(p) <= placebo.FACT_CHARS for p in parts)
    assert all(set(p.split()) <= {"alpha", "beta", "gamma"} for p in parts)
    with pytest.raises(ValueError):
        placebo.chunks("", 1)
