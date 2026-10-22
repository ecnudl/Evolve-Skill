"""The examiner's failure detectors (implementation plan §8 T-DET-1..6; registration §5.2, §7.1 after Codex F10, F11
and consistency check C2). Every detector runs in the real sandbox worker through FakeDocker (local subprocesses, no
docker); every trajectory is a synthetic sealed engineering fixture; the bootstrap uses the registered draw count."""
from __future__ import annotations

import json

import pytest

from skillopt.execskill import detectors
from skillopt.execskill.detectors import Detector
from skillopt.execskill.package import FIXTURE
from skillopt.execskill.protocol import DETECTOR_LIFT, HOLM_FAMILY, record, verified
from skillopt.execskill.stats_ext import holm
from skillopt.execskill.trajectories import masked_view
from tests.test_execskill_replay import fake, workers  # noqa: F401  (the FakeDocker worker factory)

SHA = "0" * 64
RECEIPT = {"delivery": "delivered", "finish_reason": "stop"}


def trajectory(cell, bench, item, token, users, replies, *, steps=None, report=None, receipts=None, deciding=0):
    """A sealed trajectory record with the whitelisted keys (``trajectories.TOP``)."""
    purpose = "step" if bench == "alfworld" else "first"
    calls = [{"purpose": purpose, "system": "frozen system prompt", "user": json.dumps(user), "request_sha256": SHA,
              "receipt": (receipts or [RECEIPT] * len(users))[n]} for n, user in enumerate(users)]
    return record("trajectory", FIXTURE, {
        "cell": cell, "unit": "fixture-unit", "arm": "S", "arm_kind": "parent", "bench": bench, "task_id": item,
        "run": 1, "package_sha256": SHA, "route": None, "calls": calls, "replies": replies,
        "deciding_receipt": deciding, "worst_delivery": "delivered", "logical_calls": [],
        "shell": {"notes": [], "compute": None, "precheck": report, "procedure_calls": [], "faults": [],
                  "fallback": None},
        "alfworld_steps": steps, "judge": {"v2": {"token": token}}, "token": token, "dispatch_ts": 0, "finish_ts": 0})


def qa(cell, token, reply, *, bench="searchqa", receipts=None):
    view = {"question": "Which city hosts the fixture event %s?" % cell, "context": ["Public context for %s." % cell]}
    return trajectory(cell, bench, "item-" + cell, token, [view], [reply], receipts=receipts)


# ---------------------------------------------------------------------------------------------- ALFWorld episodes
START = ("-= Welcome to TextWorld, ALFRED! =-\n\nYou are in the middle of a room. Looking quickly around you, you see "
         "a cabinet 1, a drawer 1, a shelf 1, and a countertop 1.\n\nYour task is to: put some apple on countertop.")
PLACES = ("cabinet 1", "drawer 1", "drawer 2", "countertop 1", "shelf 1", "sinkbasin 1", "fridge 1", "microwave 1",
          "toaster 1", "stoveburner 1", "garbagecan 1", "desk 1")


def arrive(place):
    return "You arrive at %s. On the %s, you see a mug 1." % (place, place)


def walk(actions, length, *, tail="look", tail_after="Nothing happens.", last_after=None):
    """(observation seen, action, observation after) of an episode: ``actions`` first ("go to X" arrives at X,
    "inventory" and "look" report), then ``tail`` until ``length`` steps; ``last_after`` replaces the observation
    after the last step (a terminal observation)."""
    out, seen = [], START
    for n in range(length):
        action = actions[n] if n < len(actions) else tail
        if action.startswith("go to "):
            after = arrive(action[len("go to "):])
        elif action == "inventory":
            after = "You are not carrying anything."
        elif n < len(actions):
            after = "You see a room with a few receptacles."
        else:
            after = tail_after
        out.append((seen, action, after))
        seen = after
    if last_after is not None:
        out[-1] = out[-1][:2] + (last_after,)
    return out


def episode(cell, item, token, transitions):
    users = [{"observation": seen, "admissible_commands": ["look", "inventory"]} for seen, _, _ in transitions]
    steps = [{"i": i, "observation": seen, "notes": "", "discouraged": [], "reply": "<action>%s</action>" % action,
              "action": action, "how": "tag_exact", "post_observation": after}
             for i, (seen, action, after) in enumerate(transitions)]
    return trajectory(cell, "alfworld", item, token, users, [s["reply"] for s in steps], steps=steps, deciding=None)


TOUR = ["go to " + place for place in PLACES]
MARKED = ["inventory"] + TOUR[:9]  # the failures' landmark: they start by checking the inventory
LOOPING = ["inventory", "look", "look", "look"] + TOUR[:6]  # a loop inside the landmark view
WINNING = TOUR[3:] + TOUR[:3]


def alfworld_set(rooms):
    """Six games per room: two failures with the landmark (all 50 steps, looping after step 10), one failure looping
    inside the first 10 steps (50 steps), two long successes (20 steps) and one short success (6 steps)."""
    out, room_of = [], {}
    for r in range(rooms):
        room = "room-%02d" % r
        games = [("fail", walk(MARKED, 50)), ("fail", walk(MARKED, 50)), ("fail", walk(LOOPING, 50)),
                 ("pass", walk(WINNING, 20, tail="go to countertop 1", last_after="You won!")),
                 ("pass", walk(WINNING[1:], 20, tail="go to desk 1", last_after="You won!")),
                 ("pass", walk(WINNING, 6, last_after="You won!"))]
        for g, (token, transitions) in enumerate(games):
            item = "alf-%s-%d" % (room, g)
            room_of[item] = room
            out.append(episode("c-" + item, item, token, transitions))
    return out, room_of


# --------------------------------------------------------------------------------------------- detector fixtures
def detector(pid, body, bench="searchqa", description=None):
    return Detector(id=pid, bench=bench, source="def detect(view):\n    " + body + "\n",
                    description=description or "Fixture detector %s." % pid)


LANDMARK = detector("fx-inventory-first", 'return view["steps"][0]["action"] == "inventory"', "alfworld")
FIFTY = detector("fx-fifty-steps", 'return len(view["steps"]) == 50', "alfworld")
WON = detector("fx-you-won", 'return any("You won" in step["observation"] for step in view["steps"])', "alfworld")
LONGER = detector("fx-longer", 'return len(view["steps"]) > 10', "alfworld")
LIBRARY = detector("fx-zzz", 'return any("ZZZ" in (reply or "") for reply in view["replies"])')
HEDGE = detector("fx-hedge", 'return any("maybe" in (reply or "").lower() for reply in view["replies"])')
DUPLICATE = detector("fx-duplicate", 'return any(("ZZZ" in (reply or "")) or ("maybe" in (reply or "")) '
                                     'for reply in view["replies"])')
CRASH = detector("fx-crash", "return 1 / 0 > 0")
SET_ORDER = detector("fx-set-order", 'return next(iter(set(view["task"]["question"].split()))) < "m"')


def qa_hold():
    """Six untagged failures (masked ``no_answer_tag``), sixty failures the accepted detector flags, and the 24
    residual cells: 12 failures (11 hedged) and 12 successes (1 hedged)."""
    cells = [qa("t%02d" % n, "fail", "Maybe it is Paris, I think.") for n in range(6)]
    cells += [qa("l%02d" % n, "fail", "<answer>Lisbon</answer> (unsure: ZZZ)") for n in range(60)]
    cells += [qa("rf%02d" % n, "fail", "<answer>Rome</answer>" + (" maybe" if n < 11 else "")) for n in range(12)]
    cells += [qa("rp%02d" % n, "pass", "<answer>Oslo</answer>" + (" maybe" if n == 0 else "")) for n in range(12)]
    return cells


def halves_of(hold, unit="item"):
    return {"unit": unit, "tag": "fixture", "status": "ok", "write": [], "hold": hold}


def sealed(tmp_path, candidates, unit="fixture-unit/diagnose"):
    return detectors.seal_candidates(tmp_path / "sealed", candidates, unit=unit, written_from=unit + "/write-half",
                                     evidence=FIXTURE)


def rows_of(validation):
    return {row["id"]: row for row in validation["candidates"]}


# ---------------------------------------------------------------------------------------------------------- tests
def test_det1_masked_views_hide_answers_run_status_and_step_count(workers):
    secret = qa("s1", "pass", "<answer>Okavango</answer>")
    leaky = detector("fx-answer-text", 'return any("Okavango" in (reply or "") for reply in view["replies"])')
    sheet = trajectory("c-sheet", "spreadsheetbench", "s-1", "fail",
                       [{"instruction": "Fill the Total column.", "workbook_preview": "A1: Q1"},
                        {"instruction": "Fill the Total column.", "run_report": "KeyError: 'Total'"}],
                       ["```python\nprint(1)\n```", "```python\nprint(2)\n```"],
                       report={"status": "exception", "exc_type": "KeyError", "message": "KeyError: 'Total'"})
    run_status = detector("fx-run-status", 'return "KeyError" in str(view) or "exception" in str(view)',
                          "spreadsheetbench")
    episodes, _ = alfworld_set(1)
    views = {t["cell"]: masked_view(t, bench="alfworld", purpose="detector") for t in episodes[:5]}
    assert "passed" not in masked_view(secret, bench="searchqa", purpose="detector")
    found = detectors.evaluate([leaky], {"s1": masked_view(secret, bench="searchqa", purpose="detector")}, workers)
    assert found["fx-answer-text"] == {"fired": [], "faults": {}}
    sheet_view = masked_view(sheet, bench="spreadsheetbench", purpose="detector")
    assert sheet_view["replies"] == ["```python\nprint(1)\n```"]
    assert detectors.evaluate([run_status], {"c-sheet": sheet_view}, workers)["fx-run-status"]["fired"] == []
    assert "program_exception_on_public_input" in detectors.mechanical(sheet, bench="spreadsheetbench")
    assert "program_exception_on_public_input" not in detectors.MECHANICAL_MASKED["spreadsheetbench"]
    assert {len(view["steps"]) for view in views.values()} == {10}  # 50-step failures and 20-step wins alike
    assert set(detectors.MECHANICAL_MASKED["alfworld"]) == {
        "revisit_empty_receptacle>=3", "repeated_action_loop", "nothing_happens_share>0.2"}


def test_det1_mechanical_categories_on_replies_and_episodes():
    tagless = qa("a", "fail", 'Final: {"answer": "Paris"}')
    many = qa("b", "fail", "<answer>Paris</answer> or <answer>Lyon</answer>")
    cut = qa("c", "fail", "<answer>Pa", receipts=[{"delivery": "truncated", "finish_reason": "length"}])
    empty = qa("d", "fail", "  ")
    assert detectors.mechanical(tagless, bench="searchqa") == ["json_answer_untagged", "no_answer_tag"]
    assert detectors.mechanical(many, bench="searchqa") == ["multiple_answers"]
    assert detectors.mechanical(cut, bench="searchqa") == ["no_answer_tag", "truncated_or_suspected"]
    assert detectors.mechanical(empty, bench="searchqa") == ["empty_reply"]
    masked = masked_view(tagless, bench="searchqa", purpose="detector")
    assert detectors.mechanical_masked(masked, bench="searchqa") == ["json_answer_untagged", "no_answer_tag"]
    formula = trajectory("c-f", "spreadsheetbench", "s-2", "fail", [{"instruction": "x"}], ["=SUM(A1:A3)"])
    glued = trajectory("c-g", "spreadsheetbench", "s-3", "fail", [{"instruction": "x"}],
                       ["Here it is:```python\nprint(1)\n```"])
    assert detectors.mechanical(formula, bench="spreadsheetbench") == ["excel_formula_only"]
    assert "fence_glued" in detectors.mechanical(glued, bench="spreadsheetbench")
    visits = ["go to drawer 1", "go to shelf 1", "go to drawer 1", "go to cabinet 1", "go to drawer 1",
              "go to desk 1", "go to drawer 1"]
    empty_drawer = "You arrive at drawer 1. On the drawer 1, you see nothing."
    transitions = [(seen, action, empty_drawer if action == "go to drawer 1" else after)
                   for seen, action, after in walk(visits, 12)]
    revisits = episode("c-r", "alf-r", "fail", transitions)
    assert detectors.empty_revisits([(action, after) for _, action, after in transitions]) == 3
    assert "revisit_empty_receptacle>=3" in detectors.mechanical(revisits, bench="alfworld")
    assert detectors.repeated_action_loop([("a", None), ("b", None), ("a", None), ("b", None), ("a", None),
                                           ("b", None)])
    assert not detectors.repeated_action_loop([("a", None), ("a", None), ("b", None), ("a", None)])


def test_det2_det3_residual_metrics_and_jaccard_on_the_full_hold_half(tmp_path, workers):
    candidates = [HEDGE, DUPLICATE]
    validation = detectors.validate(sealed(tmp_path, candidates), candidates, halves_of(qa_hold()),
                                    bench="searchqa", library=[LIBRARY], workers=workers, evidence=FIXTURE)
    validation = verified(validation, "detector-validation")
    rows = rows_of(validation)
    assert validation["status"] == "ok" and validation["included"] == 90
    assert validation["masked_categories"] == {"no_answer_tag": 6}
    assert validation["library"] == {"fx-zzz": {"fired": 60, "faults": 0}}
    assert validation["residual_cells"] == 24 and validation["residual_failed"] == 12 and validation["base"] == 0.5
    hedge, duplicate = rows["fx-hedge"], rows["fx-duplicate"]
    # T-DET-2: precision, base and recall on the residual cells only
    assert hedge["n_fired"] == 12 and hedge["n_items"] == 12 and hedge["precision"] == pytest.approx(11 / 12)
    assert hedge["recall_residual"] == pytest.approx(11 / 12) and hedge["lift"] == pytest.approx(11 / 12 - 0.5)
    assert hedge["recall_counts"] == [11, 12]  # the exact counts §7.1 is judged on (Codex review 2026-10-22 #11)
    assert hedge["p_boot_lift_le_0.10"] < 0.01 and hedge["accepted"] and hedge["reason"] == "accepted"
    assert [row["p_holm"] for row in validation["candidates"]] == holm(
        [row["p_boot_lift_le_0.10"] for row in validation["candidates"]])
    # T-DET-3: Jaccard with the accepted detector on the WHOLE hold half (60 / 72), not on the residual (0)
    assert hedge["jaccard_max_full_hold"] == 0.0
    assert duplicate["n_fired"] == 12 and duplicate["precision"] == pytest.approx(11 / 12)
    assert duplicate["jaccard_max_full_hold"] == pytest.approx(60 / 72) and duplicate["jaccard_max_counts"] == [60, 72]
    assert not duplicate["accepted"] and duplicate["reason"] == "duplicate_of_accepted"
    written = detectors.detector_records(validation, candidates, written_from="fixture-unit/write-half",
                                         evidence=FIXTURE)
    assert [verified(r, "detector")["validation"]["accepted"] for r in written] == [True, False]
    assert written[0]["view"] == "qa_masked" and written[0]["candidates_sha256"] == validation["candidates_sha256"]


def test_det4_all_failures_run_50_steps_yet_a_landmark_detector_can_be_accepted(tmp_path, workers):
    episodes, rooms = alfworld_set(16)
    halves = detectors.split(episodes, bench="alfworld", unit="G/s1-alfworld/run", rooms=rooms)
    assert halves["status"] == "ok" and halves["hold_rooms"] == 8 and halves["write_rooms"] == 8
    failures = [t for t in halves["hold"] if t["token"] == "fail"]
    # the whole-episode categories mark every failure (50 steps): residual cells defined on them hold no failure
    assert all("step_budget_exhausted" in detectors.mechanical(t, bench="alfworld") for t in failures)
    candidates = [LANDMARK, FIFTY]
    validation = detectors.validate(sealed(tmp_path, candidates), candidates, halves, bench="alfworld", library=[],
                                    workers=workers, rooms=rooms, evidence=FIXTURE)
    rows = rows_of(validation)
    assert validation["excluded"] == {"ended_by_step_10:won": 8}
    assert validation["masked_categories"] == {"repeated_action_loop": 8}
    assert validation["residual_cells"] == 32 and validation["residual_failed"] == 16
    landmark = rows["fx-inventory-first"]
    assert landmark["n_fired"] == 16 and landmark["n_rooms"] == 8 and landmark["precision"] == 1.0
    assert landmark["recall_residual"] == 1.0 and landmark["accepted"]
    assert rows["fx-fifty-steps"]["n_fired"] == 0 and rows["fx-fifty-steps"]["reason"] == "too_few_alarms"


def test_det5_landmark_task_excludes_early_ends_and_hides_terminal_text(workers):
    hold = [episode("c-win11", "alf-1", "pass", walk(WINNING, 11, last_after="You won!")),
            episode("c-fail30", "alf-2", "fail", walk(MARKED, 30)),
            episode("c-short-win", "alf-3", "pass", walk(WINNING, 6, last_after="You won!")),
            episode("c-early-done", "alf-4", "fail", walk(MARKED, 8)),
            episode("c-infra-short", "alf-5", "unknown_fault", walk(MARKED, 4)),
            episode("c-infra-long", "alf-6", "unknown", walk(MARKED, 30))]
    included, excluded = detectors.hold_cells(hold, bench="alfworld")
    assert sorted(included) == ["c-fail30", "c-win11"]
    assert excluded == {"censored:infrastructure": 1, "ended_by_step_10:done": 1,
                        "ended_by_step_10:infrastructure": 1, "ended_by_step_10:won": 1}
    views = {cell: entry["view"] for cell, entry in included.items()}
    found = detectors.evaluate([WON, LONGER], views, workers)
    assert found["fx-you-won"] == {"fired": [], "faults": {}} and found["fx-longer"] == {"fired": [], "faults": {}}


def test_det6_room_split_sealing_holm_faults_and_determinism(tmp_path, workers):
    episodes, rooms = alfworld_set(14)
    halves = detectors.split(episodes, bench="alfworld", unit="G/s1-alfworld/run", rooms=rooms)
    assert halves["status"] == "cannot_decide" and halves["hold_rooms"] == 7
    assert not {rooms[t["task_id"]] for t in halves["write"]} & {rooms[t["task_id"]] for t in halves["hold"]}

    def no_sandbox(*args, **kwargs):
        raise AssertionError("an undecidable hold half runs no detector")

    small = detectors.validate(sealed(tmp_path / "a", [LANDMARK]), [LANDMARK], halves, bench="alfworld", library=[],
                               workers=no_sandbox, rooms=rooms, evidence=FIXTURE)
    assert small["status"] == "cannot_decide" and rows_of(small)["fx-inventory-first"]["accepted"] is False
    # candidates are sealed before the hold half is read; a changed candidate is refused
    seal = sealed(tmp_path / "b", [HEDGE])
    changed = Detector(id=HEDGE.id, bench="searchqa", source=HEDGE.source.replace("maybe", "perhaps"),
                       description=HEDGE.description)
    with pytest.raises(ValueError, match="candidates_changed_after_sealing"):
        detectors.validate(seal, [changed], halves_of(qa_hold()), bench="searchqa", library=[], workers=workers,
                           evidence=FIXTURE)
    with pytest.raises(ValueError):
        sealed(tmp_path / "b", [changed])  # the sealed file is written once
    # Holm over the step's candidates at family level 10 %: 0.04 passes alone, not beside 0.06 and 0.08
    row = {"faults": 0, "deterministic": True, "n_fired": 12, "n_items": 12, "n_rooms": None,
           "recall_residual": 0.5, "recall_counts": [6, 12], "jaccard_max_full_hold": 0.0, "jaccard_max_counts": [0, 0]}
    assert detectors._verdict({**row, "p_holm": holm([0.04])[0]}, "searchqa") == "accepted"
    adjusted = holm([0.04, 0.06, 0.08])
    assert adjusted == pytest.approx([0.12, 0.12, 0.12]) and min(adjusted) > HOLM_FAMILY
    assert {detectors._verdict({**row, "p_holm": p}, "searchqa") for p in adjusted} == {"lift_not_established"}
    # a fault or a hash-seed dependence blocks acceptance whatever the lift
    candidates = [CRASH, SET_ORDER, HEDGE]
    validation = detectors.validate(sealed(tmp_path / "c", candidates), candidates, halves_of(qa_hold()),
                                    bench="searchqa", library=[LIBRARY], workers=workers, evidence=FIXTURE)
    rows = rows_of(validation)
    assert rows["fx-crash"]["faults"] == 2 * 90 and rows["fx-crash"]["reason"] == "faults_or_nondeterministic"
    assert rows["fx-set-order"]["deterministic"] is False
    assert rows["fx-set-order"]["reason"] == "faults_or_nondeterministic"
    assert rows["fx-hedge"]["accepted"] and rows["fx-hedge"]["p_holm"] <= HOLM_FAMILY


def test_detector_candidates_obey_the_policy_and_define_detect():
    with pytest.raises(ValueError, match="detector_policy"):
        detector("fx-opens", 'return open("/etc/passwd") is None')
    with pytest.raises(ValueError, match="detect"):
        Detector(id="fx-nameless", bench="searchqa", source="def judge(view):\n    return True\n",
                 description="No entry point.")
    with pytest.raises(ValueError, match="detector_policy"):
        detector("fx-drawer", 'return "drawer 3" in str(view)', "alfworld")  # an ALFWorld receptacle literal
    assert DETECTOR_LIFT == pytest.approx(0.10)


# ------------------------------------------------------------------------- fixer regressions (reviews 2026-10-22)
def test_isolation_6_the_examiner_diagnosis_reads_the_write_half_on_masked_views():
    cells = [qa("w%02d" % n, "fail", "Maybe it is Paris, I think.") for n in range(8)]
    cells += [qa("p%02d" % n, "pass", "<answer>Oslo</answer>") for n in range(8)]
    halves = detectors.split(cells, bench="searchqa", unit="G/s1-searchqa/diagnose")
    found = detectors.examiner_diagnosis(halves, bench="searchqa")
    hold = {t["cell"] for t in halves["hold"]}
    assert found["half"] == "write" and found["cells"] == len(halves["write"]) and not hold & set(found["failing"])
    assert set(found["categories"]) == set(detectors.MECHANICAL_MASKED["searchqa"])
    assert all(names == ["no_answer_tag"] or "no_answer_tag" in names for names in found["failing"].values())
    with pytest.raises(ValueError, match="hold-half"):
        detectors.examiner_diagnosis({**halves, "write": halves["write"] + halves["hold"][:1]}, bench="searchqa")
    with pytest.raises(ValueError, match="split"):
        detectors.examiner_diagnosis(cells, bench="searchqa")
    counted = detectors.counts(detectors.diagnosis(cells, bench="searchqa"))
    assert set(counted) == {"cells", "failed", "categories"} and "w00" not in json.dumps(counted)


# ---------------------------------------------------------------------- M round (Codex review 2026-10-22, #11)
def test_codex_11_recall_exactly_at_the_registered_minimum_is_accepted():
    """§7.1: recall among the residual failures >= 0.15. The exact 3/20 meets it (a float round trip of 0.15 lies
    below 3/20); 299/2000, 2/20 and no residual failure do not. Jaccard is judged exactly too: 4/5 is a duplicate,
    799/1000 is not."""
    from fractions import Fraction

    from skillopt.execskill.protocol import DETECTOR_MAX_JACCARD, DETECTOR_MIN_RECALL

    assert DETECTOR_MIN_RECALL == Fraction(3, 20) and Fraction(float(Fraction(3, 20))) < DETECTOR_MIN_RECALL
    row = {"faults": 0, "deterministic": True, "n_fired": 12, "n_items": 12, "n_rooms": None, "p_holm": 0.01,
           "recall_residual": 0.15, "recall_counts": [3, 20], "jaccard_max_full_hold": 0.0,
           "jaccard_max_counts": [0, 0]}
    assert detectors._verdict(row, "searchqa") == "accepted"
    for counts in ([299, 2000], [2, 20], [0, 0]):
        assert detectors._verdict({**row, "recall_counts": counts}, "searchqa") == "recall_below_minimum"
    assert DETECTOR_MAX_JACCARD == Fraction(4, 5)
    assert detectors._verdict({**row, "jaccard_max_counts": [4, 5]}, "searchqa") == "duplicate_of_accepted"
    assert detectors._verdict({**row, "jaccard_max_counts": [799, 1000]}, "searchqa") == "accepted"
    assert detectors._ratio([3, 20]) == Fraction(3, 20) and detectors._ratio([0, 0]) == 0
    assert detectors._jaccard_counts(["a", "b", "c"], ["b", "c", "d"]) == [2, 4]
