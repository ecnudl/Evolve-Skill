"""The rubric-form study (``fivebench-rubric-form-study-v1``): engineering fixtures only -- shared rollouts, one
candidate per feedback arm, host-executed checks beside model-judged rubrics, the labelled arm, failure tolerance,
sealed results. No method-effect claim."""
import json
from copy import deepcopy

import pytest

from scripts import run_rubric_form_study as cli
from skillopt.continual_learning.recovery import POLICY_V10
from skillopt.feedback_study import rubric_form as rf
from skillopt.validator_pilot.api import digest
from tests.test_continual_learning_domains import setup
from tests.test_continual_learning_verifier_v10 import API

PASS_IDS = {"0", "2", "4", "6", "8", "9"}  # six host-passed train rows (five controls are needed), four failed
SELECTION_PASS = {"s0", "s1"}  # what the parent passes on the selection set; a candidate with the rule passes all


def _panel():
    _, base, _ = setup("searchqa")
    tasks = []
    for index in range(10):
        tasks.append({"task_id": str(index), "family_id": "t%d" % index, "project_id": "", "partition": "development",
                      "public": {"question": "What is the value for item #%d, rounded to the nearest hundredths place?" % index,
                                 "context": "| item #%d | 42.00 |" % index},
                      "private": {"answer": "42.00"}})
    for index in range(6):
        tasks.append({"task_id": "s%d" % index, "family_id": "s%d" % index, "project_id": "", "partition": "skill_confirmation",
                      "public": {"question": "What is the selection value #%d, rounded to the nearest hundredths place?" % index,
                                 "context": "| selection #%d | 7.00 |" % index},
                      "private": {"answer": "7.00"}})
    return {**base, "benchmark": "officeqa", "tasks": tasks}


def _spec(panel, blocks=2):
    model = {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low",
             "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 3600,
                           "initial_health_policy": "completed_response_v1"}}
    train = sorted({t["family_id"] for t in panel["tasks"] if t["partition"] == "development"})
    selection = sorted({t["family_id"] for t in panel["tasks"] if t["partition"] != "development"})
    template = {"panel_hash": digest(panel), "train_families": train, "selection_families": selection, "model": model,
                "runtime": {}, "parent_skill": "Read the table.\n", "seed": 0, "recovery_policy": deepcopy(POLICY_V10)}
    return rf.build_spec(template, "officeqa", blocks, {"fixture": True})


def host(task, skill):
    """Train rows: fixed host outcomes; a failed row answers a wrong value without the requested decimals (odd ids
    (ids 1 and 5 also with a unit word). Selection rows: the parent passes two; a candidate that carries the decimals rule passes all."""
    if task["partition"] == "development":
        ok = task["task_id"] in PASS_IDS
        wrong = "<answer>41 million</answer>" if int(task["task_id"]) % 4 == 1 and not ok else "<answer>41</answer>"
        output = "<answer>42.00</answer>" if ok else wrong
    else:
        ok = task["task_id"] in SELECTION_PASS or "decimal places" in skill
        output = "<answer>7.00</answer>" if ok else "<answer>7</answer>"
    return ({"status": "available", "output": output, "reason": "fixture"},
            {"status": "pass" if ok else "fail", "score": float(ok), "reason": "fixture", "metrics": {}})


class FormAPI(API):
    """Judges: the default rubric abstains (unauthorized); the study rubrics reject answers without a decimal point.
    Analysts: the edit names the kind of feedback they saw, so candidates differ by arm; ``broken`` makes the
    analysts of one feedback kind return no JSON."""

    def __init__(self, *, broken=None):
        super().__init__()
        self.broken, self.reflections = broken, []

    def _verifier(self, payload):
        assert "anonymous_response" in payload and "rubric" in payload, "judge calls only"
        from skillopt.continual_learning.verifier import DEFAULT_POLICIES

        default = payload["rubric"] == DEFAULT_POLICIES["officeqa"]  # the judge sees the policy's seven fields only
        response = payload["anonymous_response"]
        verdict = "unknown" if default else ("fail" if "." not in response else "pass")
        return {"checks": [{"obligation": "answer form", "contract_quote": payload["task"]["question"],
                            "verdict": verdict, "evidence": response[:50]}]}

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if kind.endswith("reflection"):
            seen = ("host" if "host-executed checks" in user else "label" if "The checker expected exactly this answer" in user
                    else "judge" if "Verifier (reusable rubric" in user else "none")
            with self.lock:
                self.reflections.append((key, seen, system, user))
            if seen == self.broken:
                return {**row, "response": "not json at all"}
            content = ("Read the table carefully." if seen == "none"
                       else "Give the number of decimal places the question asks (%s feedback)." % seen)
            row = {**row, "response": json.dumps({"batch_size": 2, "patch": {"reasoning": "Fixture only",
                                                                            "edits": [{"op": "append", "content": content}]}})}
        return row


def test_host_checks_read_the_question_and_the_output_only():
    public = {"question": "What was the total in FY 1934, rounded to the nearest hundredths place?", "context": "| 1934 | 4,908 |"}
    names = lambda checks: [(c["name"], c["outcome"]) for c in checks]
    assert names(rf.format_checks(public, "<answer>4908.00</answer>")) == [("answer_tag", "pass"), ("one_value", "pass"), ("decimals_as_requested", "pass")]
    assert names(rf.format_checks(public, "work <answer>4908</answer>"))[-1] == ("decimals_as_requested", "fail")
    assert names(rf.format_checks(public, "no tag")) == [("answer_tag", "fail")]
    assert names(rf.format_checks(public, "<answer>The total is 4908.00 because</answer>"))[1] == ("one_value", "fail")
    assert names(rf.format_checks({"question": "Return as comma-separated values in enclosed brackets.", "context": ""}, "<answer>[1, 2]</answer>"))[-1] == ("bracketed_list", "pass")
    assert names(rf.format_checks({"question": "Report your answer in the U.S. long date format.", "context": ""}, "<answer>March 3, 1977</answer>"))[-1] == ("long_date_format", "pass")
    assert names(rf.format_checks({"question": "What is the absolute difference?", "context": ""}, "<answer>-3</answer>"))[-1] == ("absolute_nonnegative", "fail")
    # one value: not an empty tag, not several values; a date with its comma and a thousands separator are one value
    one = lambda q, out: names(rf.format_checks({"question": q, "context": ""}, out))[1]
    assert one("Return one number.", "<answer></answer>") == ("one_value", "fail") and one("Return one number.", "<answer>1, 2</answer>") == ("one_value", "fail")
    assert one("Return one number.", "<answer>1 and 2</answer>") == ("one_value", "fail") and one("Return one number.", "<answer>1,234</answer>") == ("one_value", "pass")
    assert one("Which date?", "<answer>March 3, 1977</answer>") == ("one_value", "pass")
    # any whitespace in the question's rounding instruction; outputs of any length
    assert names(rf.format_checks({"question": "Round to nearest\thundredth.", "context": ""}, "<answer>1.23</answer>"))[-1] == ("decimals_as_requested", "pass")
    assert names(rf.format_checks(public, "<answer>" * 50000))[0] == ("answer_tag", "fail")
    # which proposal failures are the analyst's (tolerated) and which stop the study
    from skillopt.continual_learning.ledger import BudgetExhausted, LearningPending

    def chained(inner, outer="native_reflection_incomplete"):
        try:
            raise LearningPending(outer) from inner
        except LearningPending as exc:
            return rf.tolerated_proposal_failure(exc)
    assert chained(LearningPending("native_optimizer_json_rejected_after_retry:x")) == "native_reflection_incomplete:native_optimizer_json_rejected_after_retry"
    assert chained(BudgetExhausted("max_reflection_calls")) is None and chained(LearningPending("native_optimizer_response_unknown")) is None
    assert chained(RuntimeError("transport")) is None and rf.tolerated_proposal_failure(BudgetExhausted("max_api_calls")) is None
    assert rf.tolerated_proposal_failure(LearningPending("native_reflection_parse_incomplete")) == "native_reflection_parse_incomplete"
    # a disqualifying cause ANYWHERE in the chain wins over a tolerated wrapper
    assert chained(BudgetExhausted("max_reflection_calls"), "native_reflection_parse_incomplete") is None
    assert chained(BudgetExhausted("max_reflection_calls"), "native_candidate_exceeds_skill_budget") is None

    def deep():
        try:
            try:
                raise BudgetExhausted("max_reflection_calls")
            except BudgetExhausted as inner:
                raise LearningPending("native_optimizer_json_rejected_after_retry:x") from inner
        except LearningPending as middle:
            try:
                raise LearningPending("native_reflection_incomplete") from middle
            except LearningPending as outer:
                return rf.tolerated_proposal_failure(outer)
    assert deep() is None
    assert one("Which year and value?", "<answer>1, 2024</answer>") == ("one_value", "fail")
    assert names(rf.compliance_checks(public, "<answer>4,908.00 million dollars</answer>"))[1:3] == [("bare_value", "fail"), ("no_thousands_separator", "fail")]
    assert names(rf.compliance_checks({"question": "What is the mean of the series?", "context": ""}, "<answer>5</answer>"))[-1] == ("show_work_when_computing", "fail")
    assert rf.requested_decimals("Report in millions rounded to the nearest thousandth.") == 3
    assert rf.requested_decimals("rounded to 4 decimal places") == 4 and rf.requested_decimals("Round to the nearest whole number") == 0
    assert rf.requested_decimals("In which year?") is None
    text = rf.render_host_feedback(rf.rubrics("officeqa")["format_code"], [{"kind": "host_check", **c} for c in rf.format_checks(public, "<answer>4908</answer>")])
    assert text.startswith("Verifier (host-executed checks") and "FAIL the answer has exactly the number of decimal places" in text
    assert "4908" not in text.split("\n")[0] and "42" not in text  # no reference enters a report


def test_every_arm_proposes_from_the_shared_rollout_and_is_scored_on_the_same_selection(tmp_path):
    panel = _panel()
    spec = _spec(panel)
    api = FormAPI()
    result = rf.run_study(spec, panel, tmp_path / "study", fixture_api=api, fixture_evaluate=host)
    assert result["status"] == "completed", result.get("reason")
    assert result["completed_blocks"] == 2 and result["parent"] == {"pass": 4, "fail": 8, "unknown": 0, "positions": 12}
    # judge calls: the four text arms x ten rows x two blocks; code arms make none
    assert len(api.prompts["verifier"]) == 4 * 10 * 2 and not any("host-executed" in p for p in api.prompts["verifier"])
    blocks = [json.loads((tmp_path / ("study/blocks/%d/candidates.json" % b)).read_text()) for b in range(2)]
    for c in blocks:
        assert c["train"] == {"tasks": 10, "eligible_rows": 10, "unknown_rows": 0, "host_fail_rows": 4, "host_pass_rows": 6}
        auth = {arm: c["verifier"][arm]["authorized"] for arm in rf.RUBRIC_ARMS}
        assert auth == {"default_text": False, "global_text": True, "cluster_text": True, "format_text": True,
                        "format_code": True, "compliance_code": True}
        assert c["verifier"]["format_code"]["all_eligible_rows"]["detection_rate"] == 1.0  # every failed row lacks decimals
        assert c["verifier"]["compliance_code"]["all_eligible_rows"]["rejected_host_fail_rows"] == 2  # the unit-word rows
        assert c["verifier"]["format_code"]["delivery"] == {"calls": 0, "host_executed": True}
        assert all(c["dispositions"][arm]["status"] == "candidate_ready" for arm in rf.ARMS)
        assert c["dispositions"]["labelled"]["traces_with_feedback"] == 4 and c["dispositions"]["scalar"]["traces_with_feedback"] == 0
        assert c["dispositions"]["default_text"]["traces_with_feedback"] == 0  # unauthorized: scalar feedback
    # what each arm's analysts saw: the label on the labelled arm only, host checks on the code arms only
    seen = {}
    for key, kind, system, user in api.reflections:  # the call key is a hash; its intent names the arm's logical id
        logical = json.loads((tmp_path / "study/call_intents" / (key + ".json")).read_text())["logical_id"]
        arm = logical.split(":")[1].split("-", 1)[1]
        seen.setdefault(arm, set()).add(kind)
    # (the analysts of the success minibatches see no feedback text on any arm: "none" appears everywhere)
    assert "label" in seen["labelled"] and seen["scalar"] == {"none"} and seen["default_text"] == {"none"}
    assert all("host" in seen[arm] for arm in rf.CODE_ARMS) and all("judge" in seen[arm] for arm in ("global_text", "cluster_text", "format_text"))
    assert all("label" not in seen[arm] for arm in rf.ARMS if arm != "labelled")
    assert all("host" not in seen[arm] for arm in rf.ARMS if arm not in rf.CODE_ARMS)
    assert all("judge" not in seen[arm] for arm in rf.ARMS if arm not in rf.TEXT_ARMS)
    assert all("expected exactly this answer" not in user for key, kind, system, user in api.reflections if kind != "label")
    assert any("expected exactly this answer (do not copy it into the skill; explain the procedural mistake that led away from it): 42.00" in user
               for key, kind, system, user in api.reflections if kind == "label")
    # the candidates with any feedback carry the decimals rule and pass the whole selection set; scalar and the
    # unauthorized default do not
    arms = result["arms"]
    assert arms["scalar"]["pass"] == 4 and arms["default_text"]["pass"] == 4
    assert all(arms[a]["pass"] == 12 for a in ("labelled", "global_text", "cluster_text", "format_text", "format_code", "compliance_code"))
    assert arms["default_text"]["authorized_blocks"] == 0 and arms["format_code"]["authorized_blocks"] == 2
    by = {(c["treatment"], c["control"]): c for c in result["contrasts"]}
    assert by[("format_code", "format_text")]["differences"] == [0, 0] and by[("format_code", "format_text")]["supported"] is False
    assert by[("format_code", "scalar")]["differences"] == [4, 4] and by[("format_code", "scalar")]["paired_positions"] == {"wins": 8, "losses": 0, "net": 8, "positions": 12}
    assert by[("format_code", "scalar")]["block_sign_flip"]["p_value"] == pytest.approx(0.5)  # two blocks cannot reach alpha
    assert result["verifier_component"]["format_code"]["detection_rate"] == 1.0
    # every distinct candidate and the parent evaluated once per block; a finished study replays with no new call
    outcome = json.loads((tmp_path / "study/blocks/0/outcome.json").read_text())
    # the fixture analysts write one of three texts per feedback kind (host / judge / label) plus the plain edit of
    # scalar and default: identical candidates share ONE evaluation per block
    assert len(outcome["evaluations"]) == 5 and len(outcome["evaluations"]["parent"]["statuses"]) == 6
    assert sorted(outcome["shared_evaluations"]) == sorted(a for a in rf.ARMS if a not in {o for o in outcome["evaluations"]})
    assert all(outcome["arms"][a]["evaluation_slot"] in outcome["evaluations"] for a in rf.ARMS)
    sealed = list((tmp_path / "study/evaluations").glob("*.json"))
    assert len(sealed) == 2 * (10 + 5 * 6)  # per block: the train rollout and five distinct texts x six selection tasks
    calls = len(api.prompts["verifier"]) + len(api.reflections)
    assert rf.run_study(spec, panel, tmp_path / "study", fixture_api=api, fixture_evaluate=host) == result
    assert len(api.prompts["verifier"]) + len(api.reflections) == calls and len(list((tmp_path / "study/evaluations").glob("*.json"))) == len(sealed)
    assert rf.verify_result(tmp_path / "study") == result
    text = cli.report(tmp_path)
    assert "contrast format_code" in text and "claim limits" in text
    # the proposal identity of this study is the frozen v1 shape: no binding fields (10/15 extension of propose_arm)
    identity = json.loads((tmp_path / "study/native/0/scalar/identity.json").read_text())
    assert identity["study"] == rf.PROTOCOL and identity["acceptance"] == "none_one_step_rubric_form_study"
    assert not ({"analyst_binding", "verifier_label"} & set(identity))


def test_a_failed_proposal_keeps_its_arm_on_the_parent_and_the_block_continues(tmp_path):
    panel = _panel()
    spec = _spec(panel, blocks=1)
    api = FormAPI(broken="host")  # the analysts of the two code arms return no JSON
    result = rf.run_study(spec, panel, tmp_path / "study", fixture_api=api, fixture_evaluate=host)
    assert result["status"] == "completed", result.get("reason")
    c = json.loads((tmp_path / "study/blocks/0/candidates.json").read_text())
    for arm in rf.CODE_ARMS:
        assert c["dispositions"][arm]["status"] == "proposal_failed" and c["dispositions"][arm]["evaluated"] == "parent_fallback"
        assert c["dispositions"][arm]["failure"].startswith("native_reflection_incomplete:native_optimizer_json_rejected")
    assert c["dispositions"]["format_text"]["status"] == "candidate_ready"
    assert c["dispositions"]["format_code"]["failure"] == "native_reflection_incomplete:native_optimizer_json_rejected_after_retry"
    assert result["arms"]["format_code"]["pass"] == 2 and result["arms"]["format_text"]["pass"] == 6
    assert result["arms"]["format_code"]["dispositions"] == {"proposal_failed": 1}
    # the same study with the reflection budget exhausted on the first analyst call stops pending (not tolerated)
    from skillopt.continual_learning.ledger import BudgetExhausted
    exhausted = _spec(panel, blocks=1)
    api2 = FormAPI()
    original = rf.propose_arm

    def failing(*args, **kwargs):
        try:
            raise BudgetExhausted("max_reflection_calls")
        except BudgetExhausted as exc:
            raise rf.LearningPending("native_reflection_incomplete") from exc
    rf.propose_arm = failing
    try:
        result2 = rf.run_study(exhausted, panel, tmp_path / "study2", fixture_api=api2, fixture_evaluate=host)
    finally:
        rf.propose_arm = original
    assert result2["status"] == "pending" and result2["reason"] == "native_reflection_incomplete"


def test_a_label_that_is_not_the_frozen_projection_is_refused(tmp_path):
    from skillopt.continual_learning.ledger import Ledger

    panel = _panel()
    spec = _spec(panel, blocks=1)
    api = FormAPI()
    rf.run_study(spec, panel, tmp_path / "study", fixture_api=api, fixture_evaluate=host)
    from skillopt.continual_eval.core import read_json
    value = read_json(tmp_path / "study/study.json", sealed=True)
    ledger = Ledger(tmp_path / "study", value, None)
    native = read_json(tmp_path / "study/native/0/labelled/identity.json", sealed=True)
    assert native["arm"] == "labelled" and native["study"] == rf.PROTOCOL
    # rebuild the labelled traces from the sealed evaluations and tamper with one label
    rows = [read_json(p, sealed=True) for p in (tmp_path / "study/evaluations").glob("*.json")]
    rows = [r for r in rows if r["request"]["role"] == "train" and r["request"].get("rollout") == 0]
    from skillopt.continual_learning.feedback import project
    tasks = {digest(t): t for t in panel["tasks"]}
    traces = []
    for r in rows:
        task = tasks[r["request"]["task_hash"]]
        feedback = project(value, task["public"], r["prediction"], r["score"], private=task["private"], role="train")
        trace = {**feedback, "evidence_hash": r["record_hash"]}
        if trace["Feedback"]["status"] == "fail":
            trace["Feedback"] = {**trace["Feedback"], "expected": "42.00"}
        traces.append(trace)
    rf._bind_form_traces(traces, ledger, value["parent_skill"], 0, "0-labelled", labelled=True)  # the true labels bind
    bad = deepcopy(traces)
    for t in bad:
        if "expected" in t["Feedback"]:
            t["Feedback"]["expected"] = "43.00"
    with pytest.raises(ValueError, match="not the frozen projection"):
        rf._bind_form_traces(bad, ledger, value["parent_skill"], 0, "0-labelled", labelled=True)
    with pytest.raises(ValueError, match="not the frozen projection"):  # a label outside the labelled arm
        rf._bind_form_traces(traces, ledger, value["parent_skill"], 0, "0-scalar", labelled=False)


def test_the_protocol_is_frozen(tmp_path):
    panel = _panel()
    spec = _spec(panel, blocks=3)
    assert spec["arms"] == list(rf.ARMS) and spec["blocks"] == 3 and spec["rubrics"]["default_text"]["status"] == "default"
    assert set(spec["rubric_policy_hashes"]) == set(rf.RUBRIC_ARMS)
    changed = {**{k: v for k, v in spec.items() if k != "record_hash"}, "blocks": 4}
    from skillopt.coevolution_v5.core import seal
    with pytest.raises(ValueError):
        rf.validate_spec(seal({**changed, "budget": {**spec["budget"], "max_metric_calls": 1}}))
    plan = rf.block_plan(spec, 1)
    assert sorted(plan["proposal_order"]) == sorted(rf.ARMS) and set(plan["validation_rollouts"]) == set(rf.SLOTS)
    assert rf.block_plan(spec, 1) == plan and rf.block_plan(spec, 2) != plan
    # one-block studies run in series: the series label gives each its own plan (and its own protocol hash)
    series = {s: rf.build_spec(spec["template"], "officeqa", 1, {"fixture": True, "series": s}) for s in ("b", "c")}
    assert series["b"]["record_hash"] != series["c"]["record_hash"]
    assert rf.block_plan(series["b"], 0)["proposal_order"] != rf.block_plan(series["c"], 0)["proposal_order"] or \
        rf.block_plan(series["b"], 0)["minibatch_seed"] != rf.block_plan(series["c"], 0)["minibatch_seed"]


def _searchqa_panel():
    _, base, _ = setup("searchqa")
    tasks = []
    for index in range(10):
        tasks.append({"task_id": str(index), "family_id": "t%d" % index, "project_id": "", "partition": "development",
                      "public": {"question": "How many moons does planet #%d have?" % index, "context": ["Planet #%d has 2 moons." % index]},
                      "private": {"answers": ["2"]}})
    for index in range(6):
        tasks.append({"task_id": "s%d" % index, "family_id": "s%d" % index, "project_id": "", "partition": "skill_confirmation",
                      "public": {"question": "How many rings does ring #%d have?" % index, "context": ["Ring #%d has 7 rings." % index]},
                      "private": {"answers": ["7"]}})
    return {**base, "benchmark": "searchqa", "tasks": tasks}


def searchqa_host(task, skill):
    """Failed train rows answer with a sentence (the format and compliance checks fire); selection as above."""
    if task["partition"] == "development":
        ok = task["task_id"] in PASS_IDS
        output = "<answer>2</answer>" if ok else "<answer>the planet has three moons in total</answer>"
    else:
        ok = task["task_id"] in SELECTION_PASS or "decimal places" in skill
        output = "<answer>7</answer>" if ok else "<answer>7 rings</answer>"
    return ({"status": "available", "output": output, "reason": "fixture"},
            {"status": "pass" if ok else "fail", "score": float(ok), "reason": "fixture", "metrics": {}})


def test_the_study_runs_on_searchqa_with_its_own_rubrics_and_checks(tmp_path):
    from skillopt.continual_learning.verifier import DEFAULT_POLICIES

    assert set(rf.rubrics("searchqa")) == set(rf.RUBRIC_ARMS) and rf.rubrics("searchqa")["default_text"]["policy"] == DEFAULT_POLICIES["searchqa"]
    assert rf.rubrics("searchqa")["cluster_text"]["policy"] != rf.rubrics("officeqa")["cluster_text"]["policy"]
    names = lambda checks: [(c["name"], c["outcome"]) for c in checks]
    q = {"question": "How many moons does Mars have?", "context": ["x"]}
    assert names(rf.searchqa_format_checks(q, "<answer>2</answer>")) == [("answer_tag", "pass"), ("not_empty", "pass"), ("one_short_value", "pass"), ("number_when_asked", "pass")]
    assert names(rf.searchqa_format_checks(q, "<answer></answer>")) == [("answer_tag", "pass"), ("not_empty", "fail")]
    assert names(rf.searchqa_format_checks(q, "<answer>Mars has two moons which are called Phobos and Deimos</answer>"))[2] == ("one_short_value", "fail")
    assert names(rf.searchqa_compliance_checks(q, "<answer>2</answer>")) == [("tag_last_concise", "pass"), ("minimal_entity_not_sentence", "pass"), ("number_when_how_many", "pass"), ("never_empty", "pass")]
    assert names(rf.searchqa_compliance_checks(q, "no tag")) == [("tag_last_concise", "fail"), ("never_empty", "fail")]
    assert names(rf.searchqa_format_checks({"question": "Name two rivers", "context": []}, "<answer>Nile and Congo</answer>"))[-1] == ("one_short_value", "pass")
    assert names(rf.searchqa_format_checks({"question": "Which city?", "context": []}, "<answer>It is Rome.</answer>"))[2] == ("one_short_value", "fail")
    # entity names with "and", "&", commas or abbreviations are ONE value; no check judges "several items"
    for name in ("Martin Luther King Jr.", "John F. Kennedy Jr.", "St. Louis", "Simon & Garfunkel", "Trinidad and Tobago",
                 "War and Peace", "Washington, D.C.", "Paris,London", "Nairobi, Mombasa and Kisumu"):
        checks = rf.searchqa_format_checks({"question": "Who or where?", "context": []}, "<answer>%s</answer>" % name)
        assert names(checks) == [("answer_tag", "pass"), ("not_empty", "pass"), ("one_short_value", "pass")], name
        assert names(rf.searchqa_compliance_checks({"question": "Who or where?", "context": []}, "<answer>%s</answer>" % name)) == [
            ("tag_last_concise", "pass"), ("minimal_entity_not_sentence", "pass"), ("never_empty", "pass")], name
    assert names(rf.searchqa_format_checks({"question": "Who?", "context": []}, "<answer>It was Rome.</answer>"))[2] == ("one_short_value", "fail")
    assert names(rf.searchqa_format_checks(q, "<answer>,,,</answer>"))[3] == ("number_when_asked", "fail")
    assert names(rf.searchqa_format_checks(q, "<answer>1,234</answer>"))[3] == ("number_when_asked", "pass")
    assert rf.BUDGETS["searchqa"]["max_verifier_calls"] >= 4 * 128 * 6 + 600 and rf.BUDGETS["officeqa"]["max_verifier_calls"] >= 4 * 48 * 6 + 600
    panel = _searchqa_panel()
    model = {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low",
             "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 3600,
                           "initial_health_policy": "completed_response_v1"}}
    template = {"panel_hash": digest(panel), "train_families": sorted({t["family_id"] for t in panel["tasks"] if t["partition"] == "development"}),
                "selection_families": sorted({t["family_id"] for t in panel["tasks"] if t["partition"] != "development"}), "model": model,
                "runtime": {}, "parent_skill": "Read the snippets.\n", "seed": 0, "recovery_policy": deepcopy(POLICY_V10)}
    spec = rf.build_spec(template, "searchqa", 1, {"fixture": True})
    assert spec["compliance_rules"][0][0] == "tag_last_concise"

    class SearchAPI(FormAPI):
        def _verifier(self, payload):
            default = payload["rubric"] == DEFAULT_POLICIES["searchqa"]
            response = payload["anonymous_response"]
            verdict = "unknown" if default else ("fail" if len(response.split()) > 3 else "pass")
            return {"checks": [{"obligation": "answer form", "contract_quote": payload["task"]["question"], "verdict": verdict, "evidence": response[:50]}]}

    api = SearchAPI()
    result = rf.run_study(spec, panel, tmp_path / "study", fixture_api=api, fixture_evaluate=searchqa_host)
    assert result["status"] == "completed", result.get("reason")
    c = json.loads((tmp_path / "study/blocks/0/candidates.json").read_text())
    assert c["verifier"]["format_code"]["authorized"] is True and c["verifier"]["compliance_code"]["authorized"] is True
    assert c["verifier"]["format_code"]["all_eligible_rows"]["detection_rate"] == 1.0  # every failed row answered a sentence
    assert c["verifier"]["default_text"]["authorized"] is False and c["verifier"]["format_text"]["authorized"] is True
    labels = [user for key, kind, system, user in api.reflections if kind == "label"]
    assert labels and all("expected exactly this answer (do not copy it into the skill; explain the procedural mistake that led away from it): 2" in user for user in labels)
    assert all("expected exactly this answer" not in user for key, kind, system, user in api.reflections if kind != "label")
    assert result["arms"]["format_code"]["pass"] == 6 and result["arms"]["scalar"]["pass"] == 2
