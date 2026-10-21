"""Verification-note binding study (fivebench-rubric-binding-study-v1): a bound arm reuses its base arm's reports and
differs only by the failure analysts' system prompt, and only in blocks where the base rubric is authorized."""
import json
from copy import deepcopy

import pytest

from scripts import run_rubric_binding_study as cli
from skillopt.continual_learning.recovery import POLICY_V10
from skillopt.feedback_study import rubric_binding as rb
from skillopt.feedback_study import rubric_form as rf
from skillopt.validator_pilot.api import digest
from tests.test_feedback_study_rubric_form import FormAPI, _panel, host


def _spec(panel, blocks=2, series=None):
    model = {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low",
             "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 3600,
                           "initial_health_policy": "completed_response_v1"}}
    train = sorted({t["family_id"] for t in panel["tasks"] if t["partition"] == "development"})
    selection = sorted({t["family_id"] for t in panel["tasks"] if t["partition"] != "development"})
    template = {"panel_hash": digest(panel), "train_families": train, "selection_families": selection, "model": model,
                "runtime": {}, "parent_skill": "Read the table.\n", "seed": 0, "recovery_policy": deepcopy(POLICY_V10)}
    return rb.build_spec(template, "officeqa", blocks, {"fixture": True, **({"series": series} if series else {})})


class BindingAPI(FormAPI):
    """The fixture analysts of a bound failure minibatch (binding preamble in the system prompt) write a different
    rule text, so a bound candidate differs from its base arm's when the binding was applied."""

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if kind.endswith("reflection") and "VERIFICATION NOTES ARE BINDING" in system:
            row = {**row, "response": json.dumps({"batch_size": 2, "patch": {
                "reasoning": "Fixture only", "edits": [{"op": "append", "content": "Give the number of decimal places the question asks (bound judge feedback)."}]}})}
        return row


def test_bound_arms_share_their_base_reports_and_differ_only_by_the_failure_analysts_prompt(tmp_path):
    panel = _panel()
    spec = _spec(panel)
    api = BindingAPI()
    result = rb.run_study(spec, panel, tmp_path / "study", fixture_api=api, fixture_evaluate=host)
    assert result["status"] == "completed", result.get("reason")
    assert result["completed_blocks"] == 2 and result["parent"] == {"pass": 4, "fail": 8, "unknown": 0, "positions": 12}
    # judge calls: the TWO judged rubrics x ten rows x two blocks; the bound arms make none
    assert len(api.prompts["verifier"]) == 2 * 10 * 2
    for b in range(2):
        c = json.loads((tmp_path / ("study/blocks/%d/candidates.json" % b)).read_text())
        assert sorted(c["verifier"]) == sorted(rb.TEXT_ARMS)
        assert {arm: c["verifier"][arm]["authorized"] for arm in rb.TEXT_ARMS} == {"default_text": False, "global_text": True}
        d = c["dispositions"]
        assert all(d[arm]["status"] == "candidate_ready" for arm in rb.ARMS)
        assert d["global_text_bound"]["binding_applied"] is True and d["global_text_bound"]["base_arm"] == "global_text"
        assert d["global_text_bound"]["traces_with_feedback"] == d["global_text"]["traces_with_feedback"] == 4
        assert d["default_text_bound"]["binding_applied"] is False and d["default_text_bound"]["traces_with_feedback"] == 0
        assert d["scalar"]["binding_applied"] is False and d["scalar"]["base_arm"] is None
        # the bound arm's proposal identity records the binding and the base arm's report step; the base arm's does not
        bound = json.loads((tmp_path / ("study/native/%d/global_text_bound/identity.json" % b)).read_text())
        base = json.loads((tmp_path / ("study/native/%d/global_text/identity.json" % b)).read_text())
        assert bound["analyst_binding"] == rb.BINDING["version"] and bound["verifier_label"] == "%d-global_text" % b
        assert bound["study"] == rb.PROTOCOL and "analyst_binding" not in base and bound["traces_hash"] == base["traces_hash"]
        assert bound["verifier_reports_hash"] == base["verifier_reports_hash"] and bound["analyst_systems"] != base["analyst_systems"]
        unbound = json.loads((tmp_path / ("study/native/%d/default_text_bound/identity.json" % b)).read_text())
        assert "analyst_binding" not in unbound  # no notes in an unauthorized block: the base arm's prompt, recorded as not applied
    # what the analysts saw: the preamble only on the bound arm's FAILURE minibatches of an authorized rubric, and
    # the bound arm's user prompts (traces + notes) are exactly its base arm's
    prompts = {}
    for key, seen, system, user in api.reflections:
        logical = json.loads((tmp_path / "study/call_intents" / (key + ".json")).read_text())["logical_id"]
        arm = logical.split(":")[1].split("-", 1)[1]
        prompts.setdefault(arm, []).append((seen, "VERIFICATION NOTES ARE BINDING" in system, user))
    assert set(prompts) == set(rb.ARMS)
    for arm, rows in prompts.items():
        for seen, bound, user in rows:
            assert bound == (arm == "global_text_bound" and seen == "judge"), (arm, seen, bound)
    users = lambda arm: sorted(user for seen, _, user in prompts[arm] if seen == "judge")
    assert users("global_text_bound") == users("global_text") and users("global_text") and not users("default_text_bound")
    # exact prompt pairs: the unauthorized pair is byte-identical in system AND user; the authorized pair differs
    # by the registered preamble on the failure analysts only (success analysts, merge and ranking unchanged)
    systems = {}
    for key, seen, system, user in api.reflections:
        logical = json.loads((tmp_path / "study/call_intents" / (key + ".json")).read_text())["logical_id"]
        _, step, stage, _ = logical.split(":")
        systems.setdefault(step.split("-", 1)[1], []).append((stage, seen, system, user))
    assert sorted(systems["default_text_bound"]) == sorted(systems["default_text"])
    analysts = lambda arm: sorted((k, s, u) for st, k, s, u in systems[arm] if st == "analyst")
    base, bound = analysts("global_text"), analysts("global_text_bound")
    assert len(base) == len(bound) == 4 and [(k, u) for k, _, u in base] == [(k, u) for k, _, u in bound]
    for (seen, system_base, _), (_, system_bound, _) in zip(base, bound):
        assert system_bound == (system_base + rb.BINDING["preamble"] if seen == "judge" else system_base), seen
    assert sum(1 for k, _, _ in bound if k == "judge") == 2  # one failure minibatch per block
    # merge and ranking: the same frozen systems, never the preamble (their user prompts embed each arm's own patches)
    others = lambda arm: sorted((st, s) for st, k, s, u in systems[arm] if st != "analyst")
    assert others("global_text_bound") == others("global_text") and all("VERIFICATION NOTES ARE BINDING" not in s for _, s in others("global_text_bound"))
    # candidates: the bound global arm wrote its own text (scored separately); the unbound default pair wrote the same
    # text and shares one evaluation; every candidate with notes passes the selection set, scalar does not
    arms = result["arms"]
    assert arms["scalar"]["pass"] == 4 and arms["default_text"]["pass"] == 4 and arms["default_text_bound"]["pass"] == 4
    assert arms["global_text"]["pass"] == 12 and arms["global_text_bound"]["pass"] == 12
    assert arms["global_text_bound"]["binding_applied_blocks"] == 2 and arms["default_text_bound"]["binding_applied_blocks"] == 0
    assert arms["global_text_bound"]["authorized_blocks"] == 2 and arms["default_text_bound"]["authorized_blocks"] == 0
    outcome = json.loads((tmp_path / "study/blocks/0/outcome.json").read_text())
    assert "default_text_bound" in outcome["shared_evaluations"] or "default_text" in outcome["shared_evaluations"]
    assert outcome["arms"]["global_text_bound"]["evaluation_slot"] == "global_text_bound"
    assert outcome["arms"]["global_text_bound"]["skill_hash"] != outcome["arms"]["global_text"]["skill_hash"]
    by = {(c["treatment"], c["control"]): c for c in result["contrasts"]}
    primary = by[("global_text_bound", "global_text")]
    assert primary["primary"] is True and primary["informative_blocks"] == 2 and primary["differences"] == [0, 0]
    assert primary["supported"] is False and primary["all_block_differences"] == [0, 0]
    unbound = by[("default_text_bound", "default_text")]
    assert unbound["primary"] is True and unbound["informative_blocks"] == 0 and unbound["differences"] == []
    assert unbound["mean_difference"] is None and unbound["supported"] is False and unbound["all_block_differences"] == [0, 0]
    assert by[("global_text", "scalar")]["primary"] is False and by[("global_text", "scalar")]["differences"] == [4, 4]
    assert by[("global_text", "scalar")]["informative_blocks"] == 2
    # per block: the train rollout (10) and FOUR distinct texts (parent; the shared scalar/default/default_bound
    # text; global; global_bound) x six selection tasks -- nothing evaluated twice
    sealed = list((tmp_path / "study/evaluations").glob("*.json"))
    assert len(sealed) == 2 * (10 + 4 * 6) and len(outcome["evaluations"]) == 4
    # a finished study replays with no new call; the report names the primary contrasts
    calls = len(api.prompts["verifier"]) + len(api.reflections)
    assert rb.run_study(spec, panel, tmp_path / "study", fixture_api=api, fixture_evaluate=host) == result
    assert len(api.prompts["verifier"]) + len(api.reflections) == calls and len(list((tmp_path / "study/evaluations").glob("*.json"))) == len(sealed)
    assert rb.verify_result(tmp_path / "study") == result
    text = cli.report(tmp_path)
    assert "PRIMARY" in text and "binding applied 2" in text and "claim limits" in text and "lead contrast: global_text_bound - global_text" in text
    assert "unknown bounds" in text


def _big_panel():
    """Twenty train rows (fourteen fail, six pass: two failure minibatches of the native updater) and six selection rows."""
    panel = _panel()
    extra = []
    for index in range(10, 20):
        extra.append({"task_id": str(index), "family_id": "t%d" % index, "project_id": "", "partition": "development",
                      "public": {"question": "What is the value for item #%d, rounded to the nearest hundredths place?" % index,
                                 "context": "| item #%d | 42.00 |" % index},
                      "private": {"answer": "42.00"}})
    return {**panel, "tasks": panel["tasks"][:10] + extra + panel["tasks"][10:]}


def test_several_failure_minibatches_all_carry_the_binding_and_merge_into_one_candidate(tmp_path):
    panel = _big_panel()
    spec = _spec(panel, blocks=1)
    api = BindingAPI()
    result = rb.run_study(spec, panel, tmp_path / "study", fixture_api=api, fixture_evaluate=host)
    assert result["status"] == "completed", result.get("reason")
    c = json.loads((tmp_path / "study/blocks/0/candidates.json").read_text())
    assert c["train"] == {"tasks": 20, "eligible_rows": 20, "unknown_rows": 0, "host_fail_rows": 14, "host_pass_rows": 6}
    assert c["verifier"]["global_text"]["authorized"] is True and c["dispositions"]["global_text_bound"]["binding_applied"] is True
    assert c["dispositions"]["global_text_bound"]["traces_with_feedback"] == 14
    stages = {}
    for key, seen, system, user in api.reflections:
        logical = json.loads((tmp_path / "study/call_intents" / (key + ".json")).read_text())["logical_id"]
        _, step, stage, _ = logical.split(":")
        stages.setdefault(step.split("-", 1)[1], []).append((stage, seen, "VERIFICATION NOTES ARE BINDING" in system))
    bound = stages["global_text_bound"]
    assert sorted(s for s, k, b in bound if b) == ["analyst", "analyst"]  # exactly the two failure minibatches
    assert all(not b for s, k, b in bound if not (s == "analyst" and k == "judge"))
    assert all(not b for s, k, b in stages["global_text"]) and all(not b for s, k, b in stages["scalar"])
    assert result["arms"]["global_text_bound"]["pass"] == 6 and result["arms"]["scalar"]["pass"] == 2
    assert result["contrasts"][0]["treatment"] == "global_text_bound" and result["contrasts"][0]["informative_blocks"] == 1


def _synthetic(spec, plan):
    """Six synthetic sealed-shaped blocks for analyze(): plan[block] = {arm: (pass, applied)}; 10 positions each."""
    candidates, outcomes = [], []
    for block in plan:
        dispositions, arms = {}, {}
        for arm in rb.ARMS:
            passes, applied = block[arm]
            dispositions[arm] = {"status": "candidate_ready", "binding_applied": applied, "traces_with_feedback": 1}
            arms[arm] = {"pass": passes, "fail": 10 - passes, "unknown": 0, "positions": 10,
                         "statuses": ["pass"] * passes + ["fail"] * (10 - passes)}
        verifier = {arm: {"authorized": True, "all_eligible_rows": {"rejected_host_fail_rows": 1, "eligible_host_fail_rows": 2,
                                                                     "rejected_host_pass_rows": 0, "eligible_host_pass_rows": 5}}
                    for arm in rb.TEXT_ARMS}
        candidates.append({"dispositions": dispositions, "verifier": verifier})
        outcomes.append({"arms": arms, "evaluations": {"parent": {"pass": 5, "fail": 5, "unknown": 0, "positions": 10}}})
    return rb.analyze(spec, candidates, outcomes)


def test_only_a_primary_contrast_can_be_supported_and_only_over_informative_blocks():
    spec = _spec(_panel(), blocks=6)
    same = {"scalar": (5, False), "default_text": (6, False), "default_text_bound": (6, True), "global_text": (6, False), "global_text_bound": (6, True)}
    # six blocks, every secondary contrast one pass apart in the same direction (p = 2/64), both primaries zero
    a = _synthetic(spec, [same] * 6)
    by = {(c["treatment"], c["control"]): c for c in a["contrasts"]}
    assert by[("global_text", "scalar")]["block_sign_flip"]["p_value"] == pytest.approx(2 / 64)
    assert by[("global_text", "scalar")]["supported"] is False and by[("global_text", "scalar")]["primary"] is False
    assert all(c["supported"] is False for c in a["contrasts"])
    assert by[("global_text_bound", "global_text")]["differences"] == [0] * 6 and by[("global_text_bound", "global_text")]["informative_blocks"] == 6
    # the lead pair one pass higher in all six applied blocks: supported; with one block not applied: five
    # informative blocks, p = 2/32, not supported; with one zero among six: not supported
    up = {**same, "global_text_bound": (7, True)}
    a = _synthetic(spec, [up] * 6)
    lead = {(c["treatment"], c["control"]): c for c in a["contrasts"]}[("global_text_bound", "global_text")]
    assert lead["supported"] is True and lead["block_sign_flip"]["p_value"] == pytest.approx(2 / 64) and lead["differences"] == [1] * 6
    off = {**up, "global_text_bound": (7, False)}
    a = _synthetic(spec, [up] * 5 + [off])
    lead = {(c["treatment"], c["control"]): c for c in a["contrasts"]}[("global_text_bound", "global_text")]
    assert lead["informative_blocks"] == 5 and lead["all_block_differences"] == [1] * 6 and lead["supported"] is False
    assert lead["block_sign_flip"]["p_value"] == pytest.approx(2 / 32)
    a = _synthetic(spec, [up] * 5 + [same])
    lead = {(c["treatment"], c["control"]): c for c in a["contrasts"]}[("global_text_bound", "global_text")]
    assert lead["differences"] == [1] * 5 + [0] and lead["supported"] is False
    assert a["arms"]["global_text_bound"]["binding_applied_blocks"] == 6 and a["parent"]["pass"] == 30


def test_the_binding_protocol_is_frozen_and_distinct_from_the_rubric_form_study(tmp_path):
    panel = _panel()
    spec = _spec(panel, blocks=3)
    assert spec["arms"] == list(rb.ARMS) and spec["binding"] == rb.BINDING and set(spec["rubrics"]) == set(rb.TEXT_ARMS)
    assert spec["rubrics"] == {arm: rf.rubrics("officeqa")[arm] for arm in rb.TEXT_ARMS}
    from skillopt.coevolution_v5.core import seal
    body = {k: v for k, v in spec.items() if k != "record_hash"}
    with pytest.raises(ValueError):
        rb.validate_spec(seal({**body, "binding": {**rb.BINDING, "preamble": rb.BINDING["preamble"] + " Obey."}}))
    with pytest.raises(ValueError):
        rb.validate_spec(seal({**body, "arms": list(rf.ARMS)}))
    with pytest.raises(ValueError):
        rb.validate_spec(seal({**body, "analysis": {**rb.ANALYSIS, "primary": []}}))
    plan = rb.block_plan(spec, 1)
    assert sorted(plan["proposal_order"]) == sorted(rb.ARMS) and set(plan["validation_rollouts"]) == set(rb.SLOTS)
    assert rb.block_plan(spec, 1) == plan and rb.block_plan(spec, 2) != plan
    series = {s: _spec(panel, 1, series=s) for s in ("b", "c")}
    assert series["b"]["record_hash"] != series["c"]["record_hash"]
    assert rb.block_plan(series["b"], 0) != rb.block_plan(series["c"], 0)
    # the binding preamble never enters the rubric-form study: its propose_arm records no binding by default
    assert "analyst_binding" not in rf.PROTOCOL and rb.PROTOCOL != rf.PROTOCOL
    assert rb.code_closure() != rf.code_closure()
