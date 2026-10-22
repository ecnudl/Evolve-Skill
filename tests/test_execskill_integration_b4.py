"""Integration B4 (method roles + examiner): rows A10 (engineer, replay, describer) and A11 (research, generators) with
the integrator's ``detectors``, on REAL stored run-slice trajectories (implementation plan §9 B4 gate; registration
§5.2, §5.4, §5.7, §7.1, §8.1). Offline and deterministic: the run slice is the B3 gate's (real ``cells.run_cell``
cells of a fake solver behind the frozen Endpoint, stored by ``TrainingStore``); the engineer, the leakage adjudicator
and the describer are FakeGLM behind the real ``Roles``; every model-written procedure and detector runs in the real
sandbox worker through FakeDocker. Everything is an engineering fixture.

1. The examiner's diagnosis and a detector validation run on the masked views of the stored trajectories.
2. The engineer step on the same trajectories: one valid change survives C1-C9; a crashing change and a leaking change
   (a run-slice reference answer, vetoed by the adjudicator) are dropped after their one fix.
3. The surviving procedure runs in the real shell for the F arm; the describer's frozen text replaces its note in the
   T_F arm; a procedure without a usable description is withheld in T_F and shows nothing (ticket A10-3).
"""
from __future__ import annotations

import itertools
import json

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.leakage import Corpus
from skillopt.coevo5.protocol import RUNTIME
from skillopt.execskill import describer, detectors, donors, engineer, replay, rounds, solver, trajectories
from skillopt.execskill.detectors import Detector
from skillopt.execskill.package import FIXTURE, Package, edits, with_describer
from skillopt.execskill.protocol import NOTES_KEY, verified
from skillopt.execskill.sandbox.client import Worker
from tests.execskill_fakes import engineer_reply, glm_roles
from tests.execskill_fakes_env import Script
from tests.test_execskill_integration_b3 import (ACCEPT, BENCH, CARD, GENERATED, ITEMS, PARENT, RUN_SLICE, Solver,
                                                 run_slice)
from tests.test_execskill_replay import (ADMISSIBLE, EPISODE, INITIAL, TEST_LIMITS, fake, source,  # noqa: F401
                                         test_case, workers)
from tests.test_execskill_replay import trajectory as replay_trajectory

YEARS = """
import re

def applies(view):
    return "Year |" in view["context"]

def before_call(view, state):
    rows = re.findall(r"^([0-9]+) [|] ([0-9]+) [|]", view["context"], re.M)
    if not rows:
        return None
    return {"facts": ["Customs receipts by year: " + "; ".join(year + " = " + customs for year, customs in rows)]}
"""
CRASH = """
def applies(view):
    return True

def before_call(view, state):
    return {"facts": ["%d rows" % (len(view["context"]) // 0)]}
"""
LEAK = """
def applies(view):
    return "Year |" in view["context"]

def before_call(view, state):
    return {"candidates": [LEAKED]}
"""
DESCRIPTION = "Before the question is solved, the solver sees each year's customs receipts read from the table."


def new(description, test):
    return {"kind": "new", "description": description, "hooks": ["applies", "before_call"], "max_note_chars": 1000,
            "replay_tests": [test]}


def glm(proposal):
    """The scripted GLM-5.3 roles: the engineer proposes ``proposal`` and resends a change unchanged when asked to
    fix it; the leakage adjudicator vetoes; the describer answers ``DESCRIPTION``."""
    def answer(system, payload):
        if isinstance(payload, dict) and "rule" in payload:
            return {"verdict": "yes", "reason": "It names a run-slice reference answer."}
        if isinstance(payload, dict) and "target_chars" in payload:
            return DESCRIPTION
        if payload["request"] == "fix":
            change = dict(payload["change"])
            code = change.pop("source")
            return engineer_reply({"changes": [change]}, [code])
        return proposal

    return answer


def sent(call, k=-1):
    return json.loads(call.requests[k][1])


def test_b4_examiner_engineer_and_describer_on_real_run_slice_trajectories(tmp_path, monkeypatch, fake, workers):
    endpoint = Endpoint(Solver(ITEMS + GENERATED), model="glm-5.3", max_tokens=100,
                        slots=Slots(tmp_path / "slots", "glm-5.3", 1), sleep=lambda _: None)
    ticks = itertools.count()
    _, stored = run_slice(tmp_path, monkeypatch, endpoint, lambda: float(next(ticks)))
    assert len(stored) == 24 and {t["arm_kind"] for t in stored} == {"parent"}
    failing = sorted(t["cell"] for t in stored if t["token"] == "fail")
    assert failing and all(t["task_id"].startswith(BENCH + "/") for t in stored)  # rounds.key items

    # 1. the examiner: diagnosis, a sealed candidate, its validation on the masked hold half
    shown = detectors.diagnosis(stored, bench=BENCH)
    assert shown["cells"] == 24 and set(shown["failing"]) == set(failing)
    assert all(not names for names in shown["failing"].values())  # every reply carries one closed answer tag
    view = trajectories.masked_view(stored[0], bench=BENCH, purpose="detector")
    assert "[masked]" in view["replies"][0] and NOTES_KEY not in view["task"]
    halves = detectors.split(stored, bench=BENCH, unit="G/s2-officeqa/diagnose")
    assert halves["hold_items"] == halves["write_items"] == 6 and len(halves["hold"]) == 12
    examiner_shown = detectors.examiner_diagnosis(halves, bench=BENCH)  # isolation review 6: the write half only
    assert examiner_shown["cells"] == 12 and set(examiner_shown["failing"]) <= {t["cell"] for t in halves["write"]}
    candidate = Detector(id="fx-ratio-question", bench=BENCH, description="Fires on ratio questions.",
                         source='def detect(view):\n    return "ratio" in view["task"]["question"]\n')
    sealed = detectors.seal_candidates(tmp_path / "diagnose", [candidate], unit="G/s2-officeqa/diagnose",
                                       written_from="G/s2-officeqa/diagnose/write-half", evidence=FIXTURE)
    validation = detectors.validate(sealed, [candidate], halves, bench=BENCH, library=[], workers=workers,
                                    evidence=FIXTURE)
    row = validation["candidates"][0]
    ratio = sum("ratio" in json.loads(t["calls"][0]["user"])["question"] for t in halves["hold"])
    assert validation["status"] == "ok" and validation["included"] == 12 and validation["residual_cells"] == 12
    assert row["faults"] == 0 and row["deterministic"] and row["n_fired"] == ratio < 10 and not row["accepted"]
    assert verified(detectors.detector_records(validation, [candidate], written_from="w", evidence=FIXTURE)[0],
                    "detector")["validation"]["reason"] == "too_few_alarms"

    # 2. the engineer step on the same stored trajectories
    leaked = next(item["private"]["answer"] for item in RUN_SLICE
                  if item["private"]["answer"].isdigit() and len(item["private"]["answer"]) >= 4)
    assert not any(leaked in json.dumps(item["public"]) for item in RUN_SLICE)
    years_test = test_case(failing[0], "before_call", {"kind": "note_contains", "value": "Customs receipts by year"},
                           mutation="strip_digits")
    proposal = engineer_reply({"changes": [
        new("Lists the customs receipts of each year in the table.", years_test),
        new("Counts the table rows.", test_case(failing[0], "before_call", {"kind": "note_contains", "value": "rows"})),
        new("Suggests a candidate number.", test_case(failing[0], "before_call",
                                                      {"kind": "note_contains", "value": leaked}))]},
        [source(YEARS), source(CRASH), source(LEAK, LEAKED=leaked)])
    roles, scripted = glm_roles(tmp_path / "glm", glm(proposal))
    failed = {t["task_id"] for t in stored if t["token"] == "fail"}  # §4.2: references of the failures only
    references = {rounds.key(BENCH, item["task_id"]): item["private"]["answer"] for item in RUN_SLICE
                  if rounds.key(BENCH, item["task_id"]) in failed}
    ctx = engineer.Context(bench=BENCH, k=2, step="s2", evidence=FIXTURE, parent=PARENT, trajectories=stored,
                           corpora={BENCH: Corpus(BENCH, RUN_SLICE)}, workers=workers, roles=roles,
                           label="G/s2-officeqa/engineer", card=CARD, references=references,
                           detectors=detectors.counts(shown))
    package, record = engineer.run(ctx)
    record = verified(record, "engineer")
    years, crash, leak = record["changes"]
    assert years["survived"] and len(years["attempts"]) == 1
    assert [a["failed"] for a in crash["attempts"]] == ["C6", "C6"] and not crash["survived"]
    assert [a["failed"] for a in leak["attempts"]] == ["C4", "C4"] and not leak["survived"]
    assert all(a["checks"][-1]["detail"]["adjudicated"] for a in leak["attempts"])
    assert [c["role"] for c in roles.calls] == ["engineer", "engineer", "leak_adjudicate", "engineer",
                                               "leak_adjudicate"]
    new_id = "fx-officeqa-2-1"
    assert package.order == PARENT.order + (new_id,) and [e.kind for e in edits(PARENT, package)] == ["new"]
    payload, task_of = scripted.seen[0][1], {t["cell"]: t["task_id"] for t in stored}
    assert payload["detectors"] == detectors.counts(shown) and "failing" not in payload["detectors"]
    with_reference = [t for t in payload["trajectories"] if "reference" in t]
    assert with_reference and {t["cell"] for t in with_reference} <= set(failing)
    assert all(t["reference"] == references[task_of[t["cell"]]] for t in with_reference)

    # 3. F, T_F and a T_F procedure without a description, through the real shell and worker
    procedure = package.get(new_id)
    entries = [replay.inputs_of(t) for t in stored]
    outcomes = replay.replay_many(procedure, entries, workers)
    lengths = [len(note["text"]) for outcome in outcomes.values() for note in outcome.notes]
    description = verified(describer.describe(roles, procedure, lengths=lengths, label="G/s2-officeqa/freeze",
                                              evidence=FIXTURE), "description")
    assert description["text"] and description["band"] in ("within", "clipped", "short")
    frozen = with_describer(package, describer.entries([description]))
    assert frozen.describer[new_id]["text_sha256"] == description["text_sha256"]
    alone, item = Package((procedure,), "s2", FIXTURE), ACCEPT[0]

    def shell(**arm):
        call = Script(["<answer>1</answer>"])
        solver.solve(BENCH, item["public"], CARD, alone, call, runtime=RUNTIME[BENCH],
                     worker=Worker(docker=fake, limits=TEST_LIMITS, scratch=tmp_path), **arm)
        return sent(call)

    assert "Customs receipts by year" in shell()[NOTES_KEY]
    shown_text = shell(text=describer.texts([description]))[NOTES_KEY]
    assert description["text"] in shown_text and "Customs receipts" not in shown_text
    assert NOTES_KEY not in shell(text={}, withhold=frozenset({new_id}))


def test_a10_2_an_episode_whose_last_request_got_no_reply_feeds_donors_and_replay_alike():
    """Ticket A10-2: the shell logs an ALFWorld step only after a usable reply, so a stored episode may hold one more
    step request than steps. The donor corpus and the engineer's replay read it the same way: the unanswered request
    keeps its view (``alf_before_step`` ran on it) and has no action and no event."""
    users = [{"initial_observation": INITIAL, "observation": seen, "admissible_commands": ADMISSIBLE,
              "recent_history": []} for seen, _, _ in EPISODE]
    steps = [{"i": i, "view_sha256": "0" * 64, "observation": seen, "notes": "", "discouraged": [], "reply": action,
              "action": action, "how": "tag_exact", "post_observation": after, "state_sha256": {}}
             for i, (seen, action, after) in enumerate(EPISODE[:-1])]
    episode = replay_trajectory("c-cut", "alfworld", "alf-cut", "fail", users, steps=steps)
    donor = donors.donor_inputs(episode, bench="alfworld")
    replayed = replay.inputs_of(episode)
    assert len(donor["steps"]) == len(replayed["steps"]) == len(EPISODE)
    assert donor["steps"][-1]["event"] is None and replayed["steps"][-1]["action"] is None
    assert donor["steps"][-2]["event"]["observation"] == EPISODE[-1][0]
    assert [s["event"] for s in donor["steps"]] == [s["event"] for s in replayed["steps"]]
    assert [s["view"] for s in donor["steps"]] == [s["view"] for s in replayed["steps"]]
