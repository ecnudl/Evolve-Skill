"""coevo5 examiner (registration §6) and analyst (§4 step 5): rubric validation, judging (host checks first, never a
reference), the revision's selection rule, diagnosis codes, and the analyst's proposal contract."""
from fractions import Fraction

import pytest

from skillopt.coevo5 import analyst, examiner
from skillopt.coevo5.protocol import RUBRIC_PANEL_PER_CLASS
from tests.coevo5_fakes import Script, roles

TAG = {"name": "answer_tag_present", "params": {}}
RUBRIC = {"bench": "searchqa", "items": [
    {"id": "R1", "text": "The answer is inside an answer tag.", "check": TAG, "basis": "card"},
    {"id": "R2", "text": "The answer is a short span, not a sentence.", "check": None, "basis": "card"}]}
GENERAL = {"bench": "general", "items": [
    {"id": "G1", "text": "The answer addresses the question asked.", "check": None, "basis": "cards"}]}


def _answer(n, *, official="fail", half="proposal", output="<answer>x</answer>", kind="scored", run=0):
    return {"key": "c%03d-%d" % (n, run), "item": "searchqa/%03d" % n, "benchmark": "searchqa", "run": run,
            "half": half, "official": official, "kind": kind, "output": output,
            "public": {"question": "Q%d" % n, "context": ["snippet"]}, "private": {"answers": ["a%d" % n]},
            "trace": None, "cases": None}


# --------------------------------------------------------------------------------------------------- rubrics
def test_rubrics_are_validated():
    assert examiner.validate_rubric(RUBRIC, "searchqa")["items"][0]["check"] == TAG
    assert examiner.validate_rubric(GENERAL, "general")["bench"] == "general"


@pytest.mark.parametrize("change", [
    lambda r: r["items"][0].update(id="G1"),  # a bench rubric's ids are R<n>
    lambda r: r["items"].append(dict(r["items"][0])),  # duplicate id
    lambda r: r["items"][0].update(check={"name": "run_code", "params": {}}),  # not in the library
    lambda r: r["items"][1].update(text="x" * 451),  # v2 §6: 450 characters
    lambda r: r.update(items=[]),
    lambda r: r["items"][1].pop("basis"),
])
def test_invalid_rubrics_are_refused(change):
    import copy

    rubric = copy.deepcopy(RUBRIC)
    change(rubric)
    with pytest.raises(ValueError):
        examiner.validate_rubric(rubric, "searchqa")


def test_diagnosis_codes_are_the_taxonomy_the_rubric_text_items_and_other(tmp_path):
    meanings = examiner.code_meanings("searchqa", RUBRIC, GENERAL)
    assert {"D1", "D2", "D3", "D4", "D5", "R1", "R2", "G1", "other"} <= set(meanings)  # v2 §3: frozen D codes
    role, script = roles(tmp_path, [{"code": "D2"}, {"code": "R1"}, {"code": "D9"}])
    first = examiner.diagnose_one(role, "searchqa", RUBRIC, GENERAL, _answer(1), label="d1")
    assert first == {"code": "D2", "by": "model"}
    codes = [c["id"] for c in script.seen[0][1]["codes"]]
    assert codes == ["D1", "D2", "D3", "D4", "D5", "R2", "G1", "other"]  # a host-check item is not a model code
    assert examiner.diagnose_one(role, "searchqa", RUBRIC, GENERAL, _answer(2), label="d2") == {
        "code": "other", "by": "invalid"}  # R1 then D9: never a listed code
    assert [c["id"] for c in examiner.taxonomy("alfworld")] == ["D1", "D2", "D3", "D4"]


# --------------------------------------------------------------------------------------------------- judging
def test_a_violated_host_check_fails_the_answer_without_a_call(tmp_path):
    role, script = roles(tmp_path, [])
    verdict = examiner.judge(role, "searchqa", RUBRIC, GENERAL, _answer(1, output="no tag"), label="j")
    assert verdict == {"verdict": "fail", "item": "R1", "by": "check"} and script.seen == []


def test_the_model_judges_the_text_items_without_the_reference(tmp_path):
    role, script = roles(tmp_path, [{"verdict": "fail", "violated": ["R2"]}, {"verdict": "pass", "violated": ["G1"]}])
    first = examiner.judge(role, "searchqa", RUBRIC, GENERAL, _answer(1), label="j1")
    assert first == {"verdict": "fail", "item": "R2", "by": "model"}
    system, payload = script.seen[0]
    assert system == examiner.JUDGE_SYSTEM and "a1" not in str(payload) and "reference" not in payload
    assert [i["id"] for i in payload["items"]] == ["R2", "G1"]  # text items only
    second = examiner.judge(role, "searchqa", RUBRIC, GENERAL, _answer(2), label="j2")
    assert second["verdict"] == "invalid"  # a pass naming violated items is not a valid verdict


def test_role_inputs_stay_within_their_bounds_with_the_truncation_mark():
    view = examiner.task_view("searchqa", {"question": "q" * 5000, "context": ["c" * 9000]})
    assert len(view["question"]) == examiner.VIEW_CHARS["question"] and view["question"].endswith(" [...]")
    assert len(view["context"]) == examiner.VIEW_CHARS["context"]
    steps = [{"action": "go to desk 1" if n % 2 else "x" * 1000, "post_observation": "o" * 1000} for n in range(40)]
    found = examiner.reference("alfworld", {"private": {}, "trace": steps})["trajectory"]
    assert len(found) == examiner.TRACE_STEPS
    assert all(len(s["action"]) + len(s["observation"]) <= examiner.TRACE_CHARS for s in found)
    assert found[-1] == {"action": "go to desk 1", "observation": "o" * 282 + " [...]"}
    assert found[-2] == {"action": "x" * 294 + " [...]", "observation": ""}


# -------------------------------------------------------------------------------------------------- revision
def _pool(per_class=12, check_items=24):
    """Proposal-half disagreements and a check half with both classes."""
    out = [_answer(n, official="fail" if n % 2 else "pass") for n in range(1, 13)]
    out += [_answer(100 + n, half="check", official="pass" if n < per_class else "fail") for n in range(check_items)]
    return out


def test_the_selection_panel_is_one_answer_per_check_item_and_at_most_20_per_class():
    answers = [_answer(100 + n, half="check", official="pass" if n < 30 else "fail", run=r)
               for n in range(60) for r in range(2)]
    panel = examiner.selection_panel(answers, seed=1, tag="t")
    assert len(panel) == 2 * RUBRIC_PANEL_PER_CLASS
    assert len({k.split("-")[0] for k in panel}) == len(panel)  # one run per item
    assert examiner.selection_panel(answers, seed=1, tag="t") == panel
    few = [a for a in answers if a["official"] == "pass" or int(a["item"][-3:]) < 137]
    assert examiner.selection_panel(few, seed=1, tag="t") is None  # 7 failed items < 8


def test_balanced_accuracy_counts_an_invalid_verdict_as_wrong():
    answers = [_answer(1, official="pass"), _answer(2, official="fail"), _answer(3, official="fail")]
    judgments = {"c001-0": {"verdict": "pass"}, "c002-0": {"verdict": "invalid"}, "c003-0": {"verdict": "fail"}}
    assert examiner.balanced_accuracy(["c001-0", "c002-0", "c003-0"], answers, judgments) == (Fraction(3, 4), 2)


def _reviser(edits, *, improves):
    """Judge: the current rubric passes everything (wrong on failed answers); the revised one (with R3) fails the
    officially failed answers when ``improves``."""
    def answer(system, payload):
        if system == examiner.REVISE_SYSTEM:
            return {"edits": edits}
        ids = [i["id"] for i in payload["items"]]
        question = payload["task"]["question"]
        if "R3" in ids and improves and int(question[1:]) >= 112:
            return {"verdict": "fail", "violated": ["R3"]}
        return {"verdict": "pass", "violated": []}
    return answer


EDIT = {"op": "add", "text": "The answer names one entity.", "check": None, "basis": "disagreements",
        "evidence": ["searchqa/001"]}


def test_a_revision_is_accepted_only_by_the_selection_rule(tmp_path):
    role, _ = roles(tmp_path, _reviser([EDIT], improves=True))
    record = examiner.revise(role, "searchqa", RUBRIC, GENERAL, _pool(), seed=3, tag="t", label="x", workers=4)
    assert record["status"] == "accepted" and [i["id"] for i in record["rubric"]["items"]] == ["R1", "R2", "R3"]
    gain = Fraction(record["balanced_accuracy"]["new"]) - Fraction(record["balanced_accuracy"]["old"])
    assert gain >= Fraction(1, 20)
    role, _ = roles(tmp_path / "b", _reviser([EDIT], improves=False))
    record = examiner.revise(role, "searchqa", RUBRIC, GENERAL, _pool(), seed=3, tag="t", label="x", workers=4)
    assert record["status"] == "rejected" and record["rubric"] == RUBRIC


def test_edits_without_proposal_half_evidence_are_dropped(tmp_path):
    unbacked = {**EDIT, "evidence": ["searchqa/105"]}  # a check-half task: not shown, not evidence
    role, _ = roles(tmp_path, _reviser([unbacked], improves=True))
    record = examiner.revise(role, "searchqa", RUBRIC, GENERAL, _pool(), seed=3, tag="t", label="x", workers=4)
    assert record["status"] == "no_valid_edits" and record["rubric"] == RUBRIC


def test_a_key_of_another_op_is_dropped_and_an_invalid_edit_is_left_out():
    dropped = []
    check = examiner._edits(RUBRIC, {"searchqa/001"}, dropped)
    remove = {"op": "remove", "id": "R2", "basis": "b", "evidence": ["searchqa/001"]}
    edits = check({"edits": [{**EDIT, "id": "R9"}, {**remove, "text": None, "check": None}]})  # the smoke's form
    assert edits == [EDIT, remove] and dropped == []
    assert [i["id"] for i in examiner.apply_edits(RUBRIC, edits)[1]["items"]] == ["R1", "R3"]
    # v2 §6: an invalid edit (an unknown key, a missing field, an overlong text, an unknown id) is left out and
    # logged; its valid siblings stand; a reply with no valid edit or a malformed envelope is invalid
    bad = [{**EDIT, "reason": "x"}, {key: value for key, value in EDIT.items() if key != "check"},
           {**EDIT, "text": "x" * 451}, {**remove, "id": "R9"}]
    assert check({"edits": bad[:2] + [EDIT]}) == [EDIT] and [d["index"] for d in dropped] == [0, 1]
    assert check({"edits": [bad[2], EDIT, bad[3]]}) == [EDIT] and [d["index"] for d in dropped] == [0, 2]
    # a value of the wrong type (a list as the id, a list as a check's name) is the edit's own fault too
    typed = [{**remove, "id": []}, {**EDIT, "check": {"name": [], "params": {}}}]
    assert check({"edits": typed + [EDIT]}) == [EDIT] and [d["index"] for d in dropped] == [0, 1]
    with pytest.raises(examiner.Invalid, match="no valid edit"):
        check({"edits": bad[1:]})
    with pytest.raises(examiner.Invalid, match="fields"):
        check({"edits": [EDIT], "note": "x"})


def test_an_edit_of_an_item_removed_earlier_is_skipped_and_logged(tmp_path):
    remove = {"op": "remove", "id": "R2", "basis": "b", "evidence": ["searchqa/001"]}
    change = {"op": "edit", "id": "R2", "text": "Shorter.", "check": None, "basis": "b", "evidence": ["searchqa/001"]}
    used, revised = examiner.apply_edits(RUBRIC, [remove, change, EDIT])
    assert used == [remove, EDIT] and [i["id"] for i in revised["items"]] == ["R1", "R3"]
    role, _ = roles(tmp_path, _reviser([remove, change, EDIT], improves=True))
    record = examiner.revise(role, "searchqa", RUBRIC, GENERAL, _pool(), seed=3, tag="t", label="x", workers=4)
    assert record["skipped_edits"] == [1] and record["dropped_edits"] == []
    # the whole rubric invalid after the edits (no item left): no revision at all
    role, _ = roles(tmp_path / "b", _reviser([remove, {**remove, "id": "R1"}], improves=True))
    record = examiner.revise(role, "searchqa", RUBRIC, GENERAL, _pool(), seed=3, tag="t", label="x", workers=4)
    assert record["status"] == "no_valid_edits" and record["rubric"] == RUBRIC


def test_an_invalid_revision_reply_or_alfworld_leaves_the_rubric(tmp_path):
    role, _ = roles(tmp_path, lambda system, payload: (
        "not json" if system == examiner.REVISE_SYSTEM else {"verdict": "pass", "violated": []}))
    record = examiner.revise(role, "searchqa", RUBRIC, GENERAL, _pool(), seed=3, tag="t", label="x", workers=4)
    assert record["status"] == "invalid_reply" and record["rubric"] == RUBRIC
    alf = {"bench": "alfworld", "items": [{"id": "R1", "text": "Act.", "check": None, "basis": "card"}]}
    assert examiner.revise(role, "alfworld", alf, GENERAL, [], seed=3, tag="t", label="x", workers=1) == {
        "status": "not_revised", "rubric": alf}


def test_too_few_check_half_failures_means_no_revision(tmp_path):
    role, script = roles(tmp_path, lambda s, p: {"verdict": "pass", "violated": []})
    record = examiner.revise(role, "searchqa", RUBRIC, GENERAL, _pool(per_class=20, check_items=24), seed=3,
                             tag="t", label="x", workers=4)
    assert record["status"] == "insufficient_panel"
    assert all(system == examiner.JUDGE_SYSTEM for system, _ in script.seen)


# ------------------------------------------------------------------------------------------------- diagnosis
def test_diagnosis_codes_in_the_registered_order(tmp_path):
    role, script = roles(tmp_path, [{"code": "R2"}, {"code": "R9"}])
    cases = [_answer(1, kind="noncompletion", output=None), _answer(2, output="no tag"), _answer(3), _answer(4)]
    found = examiner.diagnose(role, "searchqa", RUBRIC, GENERAL, cases, label="d", workers=1)
    assert [found[a["key"]] for a in cases] == [
        {"code": "noncompletion", "by": "table"}, {"code": "answer_tag_present", "by": "format"},
        {"code": "R2", "by": "model"}, {"code": "other", "by": "invalid"}]
    assert script.seen[0][1]["reference"] == {"answers": ["a3"]}


def test_a_rubric_check_no_longer_codes_before_the_model(tmp_path):
    rubric = {"bench": "officeqa", "items": [
        {"id": "R1", "text": "Number only.", "check": {"name": "answer_no_letters", "params": {}}, "basis": "card"}]}
    role, script = roles(tmp_path, [{"code": "D4"}])
    answer = {**_answer(1, output="<answer>12 million</answer>"), "benchmark": "officeqa",
              "public": {"question": "Q", "context": "page " * 3000}, "private": {"answer": "12"}}
    assert examiner.diagnose_one(role, "officeqa", rubric, GENERAL, answer, label="d") == {"code": "D4",
                                                                                          "by": "model"}
    payload = script.seen[0][1]  # v2 §3: the type the model picks; the OfficeQA pages up to 30,000 characters
    assert len(payload["task"]["context"]) == len("page " * 3000) == 15000
    assert [c["id"] for c in payload["codes"]] == ["D1", "D2", "D3", "D4", "D5", "G1", "other"]  # R1: a host check
    assert len(examiner.task_view("officeqa", answer["public"])["context"]) == examiner.VIEW_CHARS["context"]


def _livemath_answer(letter, reference, meta="C"):
    options = {k: "Statement %s." % k for k in "ABCDE"}
    if meta:
        options[meta] = "One of the remaining options is correct, but a stronger result can be proven."
    public = {"question": "Which holds?", "choices": "\n\n".join("%s. %s" % kv for kv in sorted(options.items()))}
    return {**_answer(1, output="<answer>%s</answer>" % letter), "benchmark": "livemath", "public": public,
            "private": {"answer": reference}}


@pytest.mark.parametrize("letter, reference, meta, code", [
    ("A", "C", "C", "D1"),  # the meta-option was right, a listed statement was picked
    ("C", "A", "C", "D2"),  # the meta-option was picked, a listed statement was right
    ("A", "B", "C", None),  # neither: the model decides among D3-D5
    ("A", "B", None, None),  # no meta-option in the item
])
def test_livemath_meta_option_failures_are_coded_by_table(tmp_path, letter, reference, meta, code):
    answer = _livemath_answer(letter, reference, meta)
    assert examiner.stronger_option_code(answer) == code
    role, script = roles(tmp_path, [{"code": "D5"}])
    found = examiner.diagnose_one(role, "livemath", {"bench": "livemath", "items": [
        {"id": "R1", "text": "Pick one letter.", "check": None, "basis": "card"}]}, GENERAL, answer, label="d")
    if code is not None:
        assert found == {"code": code, "by": "table"} and script.seen == []
    else:
        assert found == {"code": "D5", "by": "model"}
        assert [c["id"] for c in script.seen[0][1]["codes"]] == ["D3", "D4", "D5", "R1", "G1", "other"]
    meanings = examiner.code_meanings("livemath", {"bench": "livemath", "items": []}, GENERAL)
    assert {"D1", "D2", "D3", "D4", "D5"} <= set(meanings)  # the analyst reads every type's meaning


def test_a_livemath_answer_without_one_letter_keeps_its_format_code(tmp_path):
    answer = _livemath_answer("A or C", "C")
    role, script = roles(tmp_path, [])
    assert examiner.stronger_option_code(answer) is None
    assert examiner.diagnose_one(role, "livemath", {"bench": "livemath", "items": []}, GENERAL, answer,
                                 label="d") == {"code": "answer_single_letter", "by": "format"}


# --------------------------------------------------------------------------------------------------- analyst
def _failures(n=50):
    return [_answer(k) for k in range(n)]


def test_the_analyst_sees_at_most_40_examples_round_robin_over_codes_and_the_similar_kinds():
    failures = _failures()
    diagnoses = {a["key"]: {"code": "R2" if k < 45 else "other"} for k, a in enumerate(failures)}
    cards = {b: "card of " + b for b in ("searchqa", "officeqa", "livemath", "spreadsheetbench", "alfworld")}
    value = analyst.payload("searchqa", parent_text="", failures=failures, diagnoses=diagnoses,
                            meanings={"R2": "short", "other": "none"}, cards=cards, seed=1, tag="t")
    assert len(value["examples"]) == analyst.MAX_EXAMPLES and value["failures"]["by_code"] == {"R2": 45, "other": 5}
    assert [e["code"] for e in value["examples"][:4]] == ["R2", "other", "R2", "other"]
    assert value["similar"] == {"kinds": [{"section": "OfficeQA", "task_card": "card of officeqa"}],
                                "checkable": ["OfficeQA"]}
    assert value["limits"]["similar_rules"] == 2 and value["limits"]["evidence"] == [2, 8]
    assert value["correct_examples"] == []
    passed = [_answer(200 + n, official="pass", run=r) for n in range(6) for r in range(2)]
    shown = analyst.payload("searchqa", parent_text="", failures=failures, diagnoses=diagnoses,
                            meanings={"R2": "short", "other": "none"}, cards=cards, seed=1, tag="t", passed=passed)
    contrast = shown["correct_examples"]  # v2 §4: at most four, one per item, never citable as evidence
    assert len(contrast) == 4 and len({e["task"]["question"] for e in contrast}) == 4
    assert all(set(e) == {"task", "answer", "reference"} for e in contrast)
    alf = analyst.payload("alfworld", parent_text="", failures=[], diagnoses={}, meanings={}, cards=cards, seed=1,
                          tag="t")
    assert alf["similar"] == {"kinds": [], "checkable": []} and alf["limits"]["similar_rules"] == 0


# the shown proposal-half failures a rule's evidence is checked against (v2 §4)
SHOWN = {"examples": [{"task_id": "searchqa/%03d" % n, "code": "R2" if n < 4 else "other"} for n in range(1, 6)]}
RULE = {"text": "Answer with the shortest span.", "placement": "local", "codes": ["R2"],
        "evidence": ["searchqa/001", "searchqa/002"], "covered": "none", "adds": "the shortest span",
        "rationale": "why", "questions": []}
NONE = {"none": "no shown failure is shared"}


def test_proposals_get_stage_ids_and_two_invalid_replies_are_a_method_failure(tmp_path):
    role, _ = roles(tmp_path, [{"rules": [RULE, {**RULE, "text": "Prefer names.", "placement": "similar"}],
                                "transfer": {"rule": 2}}])
    found = analyst.propose(role, "searchqa", SHOWN, stage=1, codes={"R2", "other"}, label="a")
    assert found["status"] == "proposed" and [p["id"] for p in found["proposals"]] == ["s1-r1", "s1-r2"]
    assert found["transfer"] == {"rule": 2, "status": "named"}
    assert [p["evidence_status"] for p in found["proposals"]] == ["ok", "ok"]
    role, script = roles(tmp_path / "b", ["nope", {"rules": [{**RULE, "codes": ["R7"]}], "transfer": NONE}])
    assert analyst.propose(role, "searchqa", SHOWN, stage=1, codes={"R2"}, label="a") == {
        "status": "method_failure", "attempts": 2, "proposals": [], "transfer": None}
    assert len(script.seen) == 2


@pytest.mark.parametrize("benchmark, reply", [
    ("alfworld", {"rules": [{**RULE, "placement": "similar"}]}),  # no checkable similar target
    ("searchqa", {"rules": [{**RULE, "placement": "similar", "text": "a%d" % k} for k in range(3)],
                  "transfer": NONE}),  # more than two
    ("searchqa", {"rules": [{**RULE, "text": "x" * 601}], "transfer": NONE}),
    ("searchqa", {"rules": [{**RULE, "text": "# heading"}], "transfer": NONE}),
    ("searchqa", {"rules": [{**RULE, "questions": ["q1", "q2", "q3"]}], "transfer": NONE}),
    ("searchqa", {"rules": [RULE] * 6, "transfer": NONE}),
    # v2 §4: the transfer slot where a similar target is checkable; the covered and adds statements, bounded
    ("searchqa", {"rules": [RULE]}),
    ("searchqa", {"rules": [RULE], "transfer": {"rule": 1, "none": "x"}}),
    ("searchqa", {"rules": [RULE], "transfer": {"none": "x" * 301}}),
    ("searchqa", {"rules": [RULE], "transfer": {"none": " "}}),  # "none" needs its reason
    ("searchqa", {"rules": [{k: v for k, v in RULE.items() if k != "covered"}], "transfer": NONE}),
    ("searchqa", {"rules": [{**RULE, "covered": "x" * 201}], "transfer": NONE}),
    ("searchqa", {"rules": [{**RULE, "adds": "x" * 301}], "transfer": NONE}),
])
def test_invalid_proposals(tmp_path, benchmark, reply):
    role, _ = roles(tmp_path, [reply] * 2)
    assert analyst.propose(role, benchmark, SHOWN, stage=1, codes={"R2"}, label="a")["status"] == "method_failure"


@pytest.mark.parametrize("evidence, codes, problem", [
    (["searchqa/001"], ["R2"], "evidence_count"),  # fewer than two
    (["searchqa/%03d" % n for n in range(1, 10)], ["R2"], "evidence_count"),  # more than eight
    ("searchqa/001", ["R2"], "evidence_count"),
    (["searchqa/001", "searchqa/001"], ["R2"], "evidence_ids"),
    (["searchqa/001", "searchqa/099"], ["R2"], "evidence_not_shown"),  # a task not shown (the check half)
    (["searchqa/001", "searchqa/004"], ["R2"], "evidence_other_code"),  # 004 was shown with another code
    (["searchqa/001", "searchqa/002"], ["R2", "other"], "code_without_evidence"),
    (["searchqa/001", "searchqa/004"], ["R2", "other"], None),
])
def test_a_rule_whose_evidence_fails_is_kept_untested_and_its_siblings_stand(tmp_path, evidence, codes, problem):
    reply = {"rules": [{**RULE, "evidence": evidence, "codes": codes}, RULE], "transfer": {"rule": 1}}
    role, script = roles(tmp_path, [reply])
    found = analyst.propose(role, "searchqa", SHOWN, stage=1, codes={"R2", "other"}, label="a")
    assert found["status"] == "proposed" and len(script.seen) == 1  # no second attempt
    assert [p["evidence_status"] for p in found["proposals"]] == [problem or "ok", "ok"]
    assert found["transfer"] == {"rule": 1, "status": "not_a_similar_rule"}  # recorded, invalidating nothing


def test_the_transfer_slot_is_ignored_where_no_similar_target_is_checkable(tmp_path):
    role, _ = roles(tmp_path, [{"rules": [RULE], "transfer": {"rule": 1}}])
    found = analyst.propose(role, "alfworld", SHOWN, stage=5, codes={"R2"}, label="a")
    assert found["status"] == "proposed" and found["transfer"] is None


def test_duplicates_of_the_parent_or_a_lower_numbered_proposal_are_dropped():
    proposals = [{"id": "s2-r1", "text": "Keep  units."}, {"id": "s2-r2", "text": "keep units."},
                 {"id": "s2-r3", "text": "Answer briefly."}, {"id": "s2-r4", "text": "New."}]
    kept, dropped = analyst.deduplicated(proposals, ["ANSWER briefly."])
    assert [p["id"] for p in kept] == ["s2-r1", "s2-r4"] and dropped == ["s2-r2", "s2-r3"]


def test_script_fake_is_used_as_documented():
    assert Script([]).replies == []
