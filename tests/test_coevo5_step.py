"""coevo5 stage orchestration (registration §4, §5, §13.4) end to end, offline: the real units, cells, frozen QA
backends, gate and ledger, with a scripted GLM-5.3 (solver and method roles) and canned research and forward panels.

Stage 1 (SearchQA) learns a rule that fixes the even items and is proposed for the similar placement: it reaches its
forward OfficeQA panel, passes both rounds there and is merged into the SearchQA and OfficeQA sections. Stage 2
(OfficeQA) learns a second similar rule, checked backward on SearchQA's regression panel and forward on LiveMath."""
import json
from fractions import Fraction

import pytest

from skillopt.coevo5 import analyst, chain, examiner, forward, leakage, research, step
from skillopt.coevo5 import data as data_module
from skillopt.coevo5.budget import Budget
from skillopt.coevo5.calls import Slots
from skillopt.coevo5.cells import Pause
from skillopt.coevo5.protocol import DATA_SEED, SLOTS, TOLERANCE_FOCAL
from skillopt.coevo5.skill import Skill
from skillopt.coevo5.units import Setting
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import write_json
from tests.coevo5_fakes import Script, roles, undelivered
from tests.test_coevo5_research import TEXT, _page, _wikipedia

SEARCH_RULE = "Copy the exact answer."
OFFICE_RULE = "Give the number only."
RUBRIC = {"bench": "searchqa", "items": [{"id": "R1", "text": "Short answer.", "check": None, "basis": "card"}]}
GENERAL = {"bench": "general", "items": [{"id": "G1", "text": "On topic.", "check": None, "basis": "cards"}]}


def _pool(bench, n):
    if bench == "searchqa":
        return [{"benchmark": bench, "task_id": "sq%02d" % k, "family_id": "f%d" % k, "part": "train",
                 "public": {"question": "SQ%d" % k, "context": ["snippet %d" % k]},
                 "private": {"answers": ["ans%d" % k]}} for k in range(n)]
    return [{"benchmark": bench, "task_id": "oq%02d" % k, "family_id": "g%d" % k, "part": "train",
             "public": {"question": "OQ%d" % k, "context": "page %d" % k}, "private": {"answer": "%d" % k}}
            for k in range(n)]


def _forward(rule_id, target, count=12):
    items = []
    for n in range(1, count + 1):
        if target == "officeqa":
            public, private = {"question": "FO%d" % n, "context": "table"}, {"answer": "%d" % n}
        else:
            public = {"question": "FL%d" % n, "choices": "A. 1\n\nB. 2\n\nC. 3\n\nD. 4\n\nE. 5"}
            private = {"answer": "A"}
        items.append({"id": "fwd:%s:%s:%d" % (rule_id, target, n), "benchmark": target, "public": public,
                      "private": private, "identity": "%s%d" % (target, n), "source": {}, "formula": "1",
                      "round": 1})
    return {"status": "ok" if count >= 8 else "short", "items": items, "counts": {}, "rounds": []}


def _solver(system, payload):
    question = payload.get("question", "")
    if question.startswith("SQ"):
        n = int(question[2:])
        return "<answer>%s</answer>" % ("ans%d" % n if SEARCH_RULE in system or n % 2 else "wrong")
    if question.startswith("OQ"):
        n = int(question[2:])
        return "<answer>%s</answer>" % (n if OFFICE_RULE in system or n % 2 else "no idea")
    if question.startswith("FO"):
        return "<answer>%s</answer>" % question[2:]
    return "<answer>A</answer>"


def _roles(state):
    def answer(system, payload):
        if system.startswith("Solve the supplied task"):
            return state.get("solver", _solver)(system, payload)
        if system == examiner.JUDGE_SYSTEM:
            return {"verdict": "pass", "violated": []}
        if system == examiner.REVISE_SYSTEM:
            return {"edits": []}
        if system == examiner.DIAGNOSE_SYSTEM:
            return {"code": "R1"}
        if system == analyst.ANALYST_SYSTEM:  # v2: evidence from the shown failures, the transfer slot
            evidence = list(dict.fromkeys(e["task_id"] for e in payload["examples"]))[:8]
            return {"rules": [{"text": state["rule"], "placement": "similar", "codes": ["R1"], "evidence": evidence,
                               "covered": "none", "adds": "an exact copy", "rationale": "fix",
                               "questions": ["What does exact match compare?"]}], "transfer": {"rule": 1}}
        if system == leakage.ADJUDICATE_SYSTEM:
            return {"verdict": "no", "reason": "general"}
        if system == research.REWRITE_SYSTEM:
            return {"text": payload["rule"] + " Keep it exact."}
        if system == step.SELFTEST_SYSTEM:  # v3 §7: the batch revision (by default every rule is dropped)
            state.setdefault("revised", []).append(payload)
            return {"rules": [{"id": r["id"], **state.get("revise", lambda rule: {"drop": True})(r)}
                              for r in payload["rules"]]}
        raise AssertionError("unexpected system prompt")
    return answer


@pytest.fixture
def setting(tmp_path, monkeypatch):
    monkeypatch.setattr(step.research, "request", lambda roles, sources, **kw: {
        "purpose": "verify", "question": kw["question"], "status": "found", "conclusion": "Exact strings.",
        "quotes": [{"page": "p", "text": "exact"}], "calls": 3})
    monkeypatch.setattr(step.forward, "build_panel", lambda roles, **kw: _forward(kw["rule_id"], kw["target"]))
    monkeypatch.setattr(data_module, "TRAIN_ROLLOUT", {"searchqa": (20, 2), "officeqa": (16, 2)})
    monkeypatch.setattr(step, "TRAIN_ROLLOUT", {"searchqa": (20, 2), "officeqa": (16, 2)})
    state = {"rule": SEARCH_RULE}
    script = Script(_roles(state))
    budget = Budget(tmp_path / "shared" / "ledger", poll=0)
    budget.declare(chain.caps("E-glm"))
    value = Setting(
        run="run-1", root=tmp_path, shared=tmp_path / "shared",
        pools={"searchqa": _pool("searchqa", 30), "officeqa": _pool("officeqa", 16)},
        regression={"searchqa": {"items": ["sq%02d" % k for k in range(10)], "tolerance": 5}},
        tolerance=dict(TOLERANCE_FOCAL), cards={b: "card" for b in ("searchqa", "officeqa", "livemath",
                                                                     "spreadsheetbench", "alfworld")},
        rubrics={"searchqa": RUBRIC, "officeqa": {**RUBRIC, "bench": "officeqa"}, "general": GENERAL},
        instructions={}, runtime={"searchqa": {}, "officeqa": {}, "livemath": {}},
        clients=lambda model, max_tokens, timeout: script, budget=budget,
        slots={name: Slots(tmp_path / "shared" / "slots", name, count) for name, count in SLOTS.items()},
        sources=lambda store: None, workers=8, cooldown=0)
    return value, state, script


def test_two_stages_learn_similar_rules_through_every_unit(setting, tmp_path):
    value, state, script = setting
    root = tmp_path / "E-glm"
    skill, merged = step.learn(value, root, "E-glm", 1, Skill())
    rewritten = SEARCH_RULE + " Keep it exact."
    assert merged["result"]["accepted"] == [{"id": "s1-r1", "placement": "similar"}]
    assert [(r.text, r.sections) for r in skill.rules] == [(rewritten, ("searchqa", "officeqa"))]
    prepared = json.loads((root / "s1" / "prepare" / "unit.json").read_text())["result"]
    assert prepared["rules"][0]["status"] == "supported" and prepared["rules"][0]["also"] == []  # v3: placed later
    planned = json.loads((root / "s1" / "selftest" / "unit.json").read_text())["result"]  # the gate's plan
    rule = planned["rules"][0]
    assert rule["status"] == "supported" and rule["also"] == ["officeqa"] and len(rule["trigger"]) >= 4
    assert planned["selftest"]["s1-r1"]["round1"]["passed"] is True and "_revision" not in planned["selftest"]
    screen = json.loads((root / "s1" / "screen" / "unit.json").read_text())["result"]
    assert screen["verdicts"]["s1-r1:similar"]["status"] == "pass"
    assert screen["verdicts"]["s1-r1:similar"]["criteria"]["C4'"]["officeqa"]["ok"] is True
    assert sorted(screen["verdicts"]) == ["s1-r1:local", "s1-r1:similar"]
    assert not (root / "s1" / "composite").exists()  # a single confirmed rule needs no composition round
    # the units' records are complete and bound to their inputs; a rerun passes every completed unit
    calls = len(script.seen)
    again, _ = step.learn(value, root, "E-glm", 1, Skill())
    assert again == skill and len(script.seen) == calls
    # stage 2: a backward (SearchQA regression) and a forward (LiveMath) similar target
    state["rule"] = OFFICE_RULE
    skill2, merged2 = step.learn(value, root, "E-glm", 2, skill)
    assert merged2["result"]["accepted"] == [{"id": "s2-r1", "placement": "similar"}]
    assert skill2.rules[-1].sections == ("officeqa", "searchqa", "livemath")
    screen2 = json.loads((root / "s2" / "screen" / "unit.json").read_text())["result"]
    c4 = screen2["verdicts"]["s2-r1:similar"]["criteria"]["C4'"]
    assert set(c4) == {"searchqa", "livemath"} and all(row["ok"] for row in c4.values())
    assert screen2["verdicts"]["s2-r1:similar"]["criteria"]["C3"]["searchqa"]["ok"] is True
    # v2 §5: C1's arms run every trigger item four times; on the regression panel the parent runs twice, a rule once
    runs = _runs(root / "s2" / "screen")
    trigger = json.loads((root / "s2" / "prepare" / "unit.json").read_text())["result"]["rules"][0]["trigger"]
    regression = ["searchqa/sq%02d" % k for k in range(10)]
    assert {runs[("parent", i)] for i in regression} == {2}
    assert {runs[(arm, i)] for arm in ("s2-r1:local", "s2-r1:similar") for i in regression} == {1}
    assert {runs[(arm, i)] for arm in ("parent", "s2-r1:local", "s2-r1:similar", "control:local:1",
                                       "control:similar:4") for i in trigger} == {4}
    rest = [i for (arm, i) in runs if arm == "parent" and i.startswith("officeqa/") and i not in trigger]
    assert rest and {runs[("parent", i)] for i in rest} == {2}
    rendered = skill2.render()
    assert rendered.index("## SearchQA") < rendered.index("## OfficeQA") < rendered.index("## LiveMath")
    assert value.budget.snapshot()["overall"]["settled"] > 0


def test_a_rule_naming_a_training_answer_word_is_adjudicated_with_the_colliding_items(setting, tmp_path):
    value, state, _ = setting
    state["rule"] = "Copy the exact answer, never ans12."  # "ans12": a SearchQA training answer (v2 §7)
    seen, original = [], _roles(state)

    def answer(system, payload):
        if system == leakage.ADJUDICATE_SYSTEM:
            seen.append(payload)
            return {"verdict": "yes" if payload.get("colliding_items") else "no", "reason": "gives it away"}
        return original(system, payload)
    value.clients = lambda model, max_tokens, timeout: Script(answer)
    skill, merged = step.learn(value, tmp_path / "E-glm", "E-glm", 1, Skill())
    unit = tmp_path / "E-glm" / "s1" / "prepare"
    record = json.loads((unit / "unit.json").read_text())
    assert record["result"]["rules"][0]["status"] == "leak_adjudicated_word" and merged["result"]["accepted"] == []
    researched = json.loads((unit / record["attempt"] / "research.json").read_text())
    assert researched[0]["research"] == "skipped_answer_word" and researched[0]["questions"] == []  # never sent
    assert seen == [{"rule": state["rule"], "colliding_items": [{"question": "SQ12", "answer": "ans12"}]}]


def _runs(unit_root):
    """{(arm, item): runs} of a unit's completed attempt."""
    record = json.loads((unit_root / "unit.json").read_text())
    counts = {}
    for path in (unit_root / record["attempt"] / "cells").glob("*.json"):
        cell = json.loads(path.read_text())["cell"]
        counts[(cell["arm"], cell["task_id"])] = counts.get((cell["arm"], cell["task_id"]), 0) + 1
    return counts


def test_a_short_forward_panel_tests_the_rule_at_its_own_placement_only(setting, tmp_path, monkeypatch):
    value, _, _ = setting
    monkeypatch.setattr(step.forward, "build_panel", lambda roles, **kw: _forward(kw["rule_id"], kw["target"], 7))
    skill, merged = step.learn(value, tmp_path / "E-glm", "E-glm", 1, Skill())
    planned = json.loads((tmp_path / "E-glm" / "s1" / "selftest" / "unit.json").read_text())["result"]
    assert planned["rules"][0]["similar_status"] == "forward_panel_short" and planned["rules"][0]["also"] == []
    assert merged["result"]["accepted"] == [{"id": "s1-r1", "placement": "local"}]
    assert skill.rules[0].sections == ("searchqa",)


def test_an_infrastructure_incomplete_training_execution_pauses_until_the_owner_decides(setting, tmp_path):
    value, state, _ = setting
    state["solver"] = lambda system, payload: undelivered()
    root = tmp_path / "E-glm"
    with pytest.raises(Pause) as paused:
        step.learn(value, root, "E-glm", 1, Skill())
    assert paused.value.kind == "infrastructure_incomplete"
    status = json.loads((root / "s1" / "train" / "attempt-1" / "status.json").read_text())
    assert status["kind"] == "infrastructure_incomplete"
    with pytest.raises(Pause) as waiting:  # nothing resumes by itself
        step.learn(value, root, "E-glm", 1, Skill())
    assert waiting.value.kind == "awaiting_owner_decision"
    write_json(root / "s1" / "train" / "attempt-1" / "recovery.json",
               {"by": "owner", "date": "2026-10-17", "decision": "redo the unit"})
    state.pop("solver")
    skill, _ = step.learn(value, root, "E-glm", 1, Skill())
    assert (root / "s1" / "train" / "attempt-2").is_dir() and skill.rules


def test_a_method_failure_leaves_the_skill_unchanged(setting, tmp_path):
    value, state, _ = setting
    original = _roles(state)

    def broken(system, payload):
        if system == analyst.ANALYST_SYSTEM:
            return "not json"
        return original(system, payload)
    value.clients = lambda model, max_tokens, timeout: Script(broken)
    skill, merged = step.learn(value, tmp_path / "E-glm", "E-glm", 1, Skill())
    assert skill == Skill() and merged["result"]["accepted"] == []
    prepared = json.loads((tmp_path / "E-glm" / "s1" / "prepare" / "unit.json").read_text())["result"]
    assert prepared["analyst"] == {"status": "method_failure", "attempts": 2, "transfer": None}


def test_a_rule_that_hurts_its_similar_target_falls_back_to_its_own_section(setting, tmp_path):
    value, state, _ = setting

    def solver(system, payload):
        if payload.get("question", "").startswith("FO") and SEARCH_RULE in system:
            return "<answer>wrong</answer>"  # the rule's similar copy hurts the forward OfficeQA items
        return _solver(system, payload)
    state["solver"] = solver
    skill, merged = step.learn(value, tmp_path / "E-glm", "E-glm", 1, Skill())
    screen = json.loads((tmp_path / "E-glm" / "s1" / "screen" / "unit.json").read_text())["result"]
    assert screen["verdicts"]["s1-r1:similar"]["criteria"]["C4'"]["officeqa"]["ok"] is False
    assert merged["result"]["accepted"] == [{"id": "s1-r1", "placement": "local"}]
    confirm = json.loads((tmp_path / "E-glm" / "s1" / "confirm" / "unit.json").read_text())["result"]
    assert sorted(confirm["verdicts"]) == ["s1-r1:local"]  # a tentatively local rule confirms its own arm only


def test_two_confirmed_rules_are_merged_after_the_composition_round(setting, tmp_path):
    value, state, _ = setting
    second = "Prefer the full name."
    original = _roles(state)

    def roles_answer(system, payload):
        if system == analyst.ANALYST_SYSTEM:  # each rule cites the shown failures it fixes (v3 §7: its self-test)
            shown = list(dict.fromkeys(e["task_id"] for e in payload["examples"]))

            def cited(rest):
                return [i for i in shown if int(i.rsplit("sq", 1)[1]) % 4 == rest][:3]
            rule = {"codes": ["R1"], "covered": "none", "adds": "x", "questions": []}
            return {"rules": [{**rule, "text": SEARCH_RULE, "placement": "local", "rationale": "a",
                               "evidence": cited(0)},
                              {**rule, "text": second, "placement": "local", "rationale": "b",
                               "evidence": cited(2)}],
                    "transfer": {"none": "both rules concern this kind only"}}
        if system.startswith("Solve the supplied task") and payload.get("question", "").startswith("SQ"):
            n = int(payload["question"][2:])
            right = n % 2 or (SEARCH_RULE in system and n % 4 == 0) or (second in system and n % 4 == 2)
            return "<answer>%s</answer>" % ("ans%d" % n if right else "wrong")
        return original(system, payload)
    value.clients = lambda model, max_tokens, timeout: Script(roles_answer)
    skill, merged = step.learn(value, tmp_path / "E-glm", "E-glm", 1, Skill())
    combined = json.loads((tmp_path / "E-glm" / "s1" / "composite" / "unit.json").read_text())["result"]
    assert combined["verdict"]["status"] == "pass" and sorted(combined["subset"]) == ["s1-r1", "s1-r2"]
    assert sorted(a["id"] for a in merged["result"]["accepted"]) == ["s1-r1", "s1-r2"]
    assert [r.id for r in skill.rules] == combined["subset"]  # merged in priority order, exactly as tested


def test_v3_a_rule_that_fails_its_self_test_enters_the_gate_only_with_its_revised_text(setting, tmp_path):
    value, state, _ = setting
    state.update(rule="Be careful.", revise=lambda rule: {"text": SEARCH_RULE})  # changes nothing, then fixes
    skill, merged = step.learn(value, tmp_path / "E-glm", "E-glm", 1, Skill())
    unit = tmp_path / "E-glm" / "s1" / "selftest"
    planned = json.loads((unit / "unit.json").read_text())["result"]
    entry = planned["selftest"]["s1-r1"]
    assert entry["round1"]["passed"] is False and entry["round1"]["rule_L"] == entry["round1"]["parent_H"] == "0"
    assert entry["revision"] == "revised" and entry["round2"]["passed"] is True
    assert planned["selftest"]["_revision"] == {"status": "valid", "dropped": [], "omitted_tasks": 0}
    rule = planned["rules"][0]
    assert (rule["status"], rule["text"], rule["before_selftest"]) == ("supported", SEARCH_RULE,
                                                                       "Be careful. Keep it exact.")
    assert rule["also"] == ["officeqa"]  # placed after the self-test, with the final text
    (payload,) = state["revised"]  # one batch call: the rule, its tasks with the rule arm's answers and references
    assert [r["id"] for r in payload["rules"]] == ["s1-r1"] and payload["current_skill"] == ""
    tasks = payload["rules"][0]["tasks"]
    assert 2 <= len(tasks) <= 3 and all(len(t["answers"]) == 2 and t["reference"] for t in tasks)
    assert {arm for arm, _ in _runs(unit)} == {"parent", "s1-r1", "s1-r1:revised"}
    assert merged["result"]["accepted"] and [r.text for r in skill.rules] == [SEARCH_RULE]
    assert step.selftest_counts(planned) == {"tested": 1, "round1_passed": 0, "reply": "valid",
                                             "revisions": {"revised": 1}, "round2_passed": 1}


@pytest.mark.parametrize("revise, status, rounds, calls", [
    (lambda rule: {"drop": True}, "selftest_dropped", {"parent", "s1-r1"}, 1),
    (lambda rule: {"text": "Be very careful."}, "selftest_failed", {"parent", "s1-r1", "s1-r1:revised"}, 1),
    (lambda rule: {"text": "x" * 601}, "selftest_failed", {"parent", "s1-r1"}, 2),  # invalid twice: not revised
])
def test_v3_a_rule_that_fails_its_self_test_and_is_not_fixed_never_enters_the_gate(setting, tmp_path, revise,
                                                                                    status, rounds, calls):
    value, state, _ = setting
    state.update(rule="Be careful.", revise=revise)
    skill, merged = step.learn(value, tmp_path / "E-glm", "E-glm", 1, Skill())
    unit = tmp_path / "E-glm" / "s1" / "selftest"
    planned = json.loads((unit / "unit.json").read_text())["result"]
    assert planned["rules"][0]["status"] == status and planned["supported"] == []
    assert {arm for arm, _ in _runs(unit)} == rounds and len(state["revised"]) == calls
    assert merged["result"]["accepted"] == [] and skill == Skill()
    assert not (tmp_path / "E-glm" / "s1" / "screen").exists()


def test_v3_a_revised_rule_without_replies_fails_its_second_round_without_pausing_the_chain(setting, tmp_path):
    value, state, _ = setting
    state.update(rule="Be careful.", revise=lambda rule: {"text": SEARCH_RULE},
                 solver=lambda system, payload: undelivered() if SEARCH_RULE in system else _solver(system, payload))
    skill, merged = step.learn(value, tmp_path / "E-glm", "E-glm", 1, Skill())
    planned = json.loads((tmp_path / "E-glm" / "s1" / "selftest" / "unit.json").read_text())["result"]
    entry = planned["selftest"]["s1-r1"]  # the second round has no parent arm: its unknowns decide the rule alone
    assert entry["revision"] == "revised" and entry["round2"]["passed"] is False
    assert entry["round2"]["unknown_share"] == "1" and planned["rules"][0]["status"] == "selftest_failed"
    assert merged["result"]["accepted"] == [] and skill == Skill()


def test_v3_the_revision_input_leaves_out_tasks_down_to_none_and_is_never_sent_over_its_bound(setting, tmp_path,
                                                                                             monkeypatch):
    value, state, _ = setting
    state.update(rule="Be careful.", revise=lambda rule: {"drop": True})
    step.learn(value, tmp_path / "A", "E-glm", 1, Skill())
    (payload,) = state.pop("revised")
    shown = len(payload["rules"][0]["tasks"])
    bare = {**payload, "rules": [{**r, "tasks": []} for r in payload["rules"]], "tasks_omitted": shown}
    monkeypatch.setattr(step, "ROLE_INPUT_BYTES", step.message_bytes(bare))  # room for no task at all
    step.learn(value, tmp_path / "B", "E-glm", 1, Skill())
    (payload,) = state.pop("revised")
    assert payload["rules"][0]["tasks"] == [] and payload["tasks_omitted"] == shown
    monkeypatch.setattr(step, "ROLE_INPUT_BYTES", step.message_bytes(bare) - 1)  # the fixed fields alone are over
    step.learn(value, tmp_path / "C", "E-glm", 1, Skill())
    planned = json.loads((tmp_path / "C" / "s1" / "selftest" / "unit.json").read_text())["result"]
    assert "revised" not in state and planned["selftest"]["_revision"]["status"] == "input_overflow"
    assert planned["selftest"]["s1-r1"]["revision"] == "input_overflow"
    assert planned["rules"][0]["status"] == "selftest_failed"


def test_v3_only_items_no_arm_got_any_reply_for_are_shared_unanswered():
    def record(token, *receipts):
        return {"final": {"token": token}, "sends": [{"receipt": r} for r in receipts]}
    filtered = {"ok": False, "response": None, "error_type": "http_400", "status": 400}
    delivered = {"ok": True, "response": "<answer>x</answer>", "finish_reason": "stop"}
    cells = {("parent", "a"): [record("unknown", filtered)], ("rule", "a"): [record("unknown", filtered, filtered)],
             # a delivered reply that failed later (e.g. its program crashed): not shared-unanswered
             ("parent", "b"): [record("unknown", filtered)], ("rule", "b"): [record("unknown", delivered)],
             ("parent", "c"): [record("pass", delivered)], ("rule", "c"): [record("unknown", filtered)],
             ("parent", "d"): [{"final": {"token": "unknown"}, "sends": [{"refused": "budget stop"}]}]}
    assert step.shared_unanswered(cells, ["a", "b", "c", "d", "e"]) == ["a", "d"]
    assert step.shared_unanswered(cells, ["b", "c"]) == []


def test_v3_an_item_no_arm_got_any_reply_for_leaves_every_criterion_of_the_round(setting, tmp_path):
    value, state, _ = setting
    drawn = data_module.training_items(value.pools["searchqa"], "searchqa", DATA_SEED)
    blocked = next(t for t in drawn if int(t["task_id"][2:]) % 2)  # one the parent passes: an item of C2's rest
    filtered = {"ok": False, "response": None, "finish_reason": None, "usage": {}, "status": 400,
                "error_type": "http_400", "error_code": "1301", "attempts": [{"status": 400}]}

    def solver(system, payload):  # e.g. a provider's content filter, for every arm
        return filtered if payload.get("question") == blocked["public"]["question"] else _solver(system, payload)
    state["solver"] = solver
    skill, merged = step.learn(value, tmp_path / "E-glm", "E-glm", 1, Skill())
    key = step.key("searchqa", blocked["task_id"])
    for name in ("screen", "confirm"):
        found = json.loads((tmp_path / "E-glm" / "s1" / name / "unit.json").read_text())["result"]
        assert found["excluded"] == [key]
        assert all(v["status"] == "pass" for v in found["verdicts"].values())
    assert merged["result"]["accepted"] == [{"id": "s1-r1", "placement": "similar"}]


def test_c3_counts_every_answer_without_its_mandatory_form(tmp_path):
    store = tmp_path / "store"
    predictions = {"tagged": {"status": "available", "output": "<answer>x</answer>"},
                   "untagged": {"status": "available", "output": "x"}, "truncated": {"status": "truncated"}}
    for name, prediction in predictions.items():
        write_json(store / "artifacts" / (name + ".json"), prediction)

    def cell(name, token="fail", kind="scored"):
        return [{"final": {"token": token, "kind": kind}, "attempts": [{"prediction": {"sha256": name}}]}]
    cells = {("arm", "a"): cell("tagged", "pass"), ("arm", "b"): cell("untagged"),
             ("arm", "c"): cell("truncated", kind="noncompletion"), ("arm", "d"): cell("tagged", "unknown"),
             ("arm", "e"): cell("tagged", kind="malformed")}
    assert step.violations(store, cells, "arm", "abcde", "searchqa", unknown_counts=1) == 4
    assert step.violations(store, cells, "arm", "abcde", "searchqa", unknown_counts=0) == 3
    assert step.violations(store, cells, "arm", "ac", "alfworld", unknown_counts=1) == 0  # no fixed format
    # v2 §5.2: an item run more than once counts its violating share of runs (the parent's two regression runs)
    cells[("arm", "a")] = cell("tagged", "pass") + cell("untagged")
    cells[("arm", "b")] = cell("untagged") + cell("truncated", kind="noncompletion")
    found = step.violations(store, cells, "arm", "ab", "searchqa", unknown_counts=1)
    assert found == Fraction(3, 2) and type(found) is Fraction


def test_an_arm_schedule_runs_triggers_more_often_and_each_item_once():
    plan = step.runs_plan(["a", "b", "c"], ["b"], "searchqa", regression=["r1"], regression_runs=2,
                          forward=["f1"])
    assert plan == [("a", 2), ("b", 4), ("c", 2), ("r1", 2), ("f1", 2)]
    assert step.runs_plan(["a", "b"], ["a"], "spreadsheetbench") == [("a", 2), ("b", 1)]
    with pytest.raises(ValueError):
        step.runs_plan(["a"], ["z"], "searchqa")  # a trigger outside the focal panel
    with pytest.raises(ValueError):
        step.runs_plan(["a"], [], "searchqa", regression=["a"])  # an item scheduled twice


def test_training_answers_keep_the_completion_token_and_the_official_result_apart(tmp_path):
    store = tmp_path / "store"
    write_json(store / "artifacts" / "p.json", {"status": "available", "output": {"code": "print(1)", "cases": []}})
    records = {"c1": ("fail", {"status": None, "reason": "not_scored:decided_before_scoring"}),  # no workbook
               "c2": ("pass", {"status": "pass", "reason": "r"}), "c3": ("fail", {"status": "fail", "reason": "r"})}
    for cid, (token, official) in records.items():
        write_json(store / "cells" / (cid + ".json"), seal({"final": {"token": token, "kind": "scored"},
                                                           "official": official,
                                                           "attempts": [{"prediction": {"sha256": "p"}}]}))
    tasks = {t: {"public": {}, "private": {}} for t in ("t1", "t2", "t3")}
    found = step.answers(store, {"cells": {"t1": ["c1"], "t2": ["c2"], "t3": ["c3"]}}, tasks, "spreadsheetbench",
                         {t: "check" for t in tasks})
    assert [(a["completion"], a["official"]) for a in found] == [("fail", "unknown"), ("pass", "pass"),
                                                                 ("fail", "fail")]
    assert [examiner.judgeable(a) for a in found] == [False, True, True]  # the revision reads official results only


def test_research_material_is_the_forward_builders_input(tmp_path):
    """step._forward unpatched: each round's material request (§7) feeds that round's generation (§8)."""
    numbers = iter(range(1, 100))

    def model(system, payload):
        if system == research.QUERY_SYSTEM:
            return {"queries": ["towns"], "source": "wikipedia"}
        if system == research.PICK_SYSTEM:
            return {"pages": ["R1"]}
        if system == research.CONCLUDE_SYSTEM["table"]:
            return {"status": "found", "page": "P1", "table": 0}
        if system == forward.GENERATE_SYSTEM["officeqa"]:
            return {"items": [{"question": "How much did Alpha grow (case %d)?" % next(numbers),
                               "formula": "1500 - 1200", "decimals": 0, "answer": "300"} for _ in range(3)]}
        assert system == forward.CHECK_SYSTEM["officeqa"] and payload["question"].startswith("How much")
        return {"formula": "1500 - 1200"}
    role, _ = roles(tmp_path, model)
    sources = research.Sources(_wikipedia({"towns": ["Towns"]}, {"Towns": _page("Towns")}), None, tmp_path / "unit")
    rule = {"id": "s1-r1", "text": "Compute changes from the exact table cells."}
    found = step._forward(role, sources, rule, "officeqa", "fwd/s1-r1/officeqa")
    assert found["status"] == "ok" and len(found["items"]) == 12 and len(found["material"]) == 4
    assert [r["status"] for r in found["material"]] == ["found"] * 4
    assert found["items"][0]["public"]["context"] == "Source: Wikipedia, Towns (revision 7)\n" + "\n".join(TEXT[1:5])
    assert found["items"][0]["private"] == {"answer": "300"} and found["items"][-1]["id"] == "fwd:s1-r1:officeqa:12"
    assert role.count("fwd/s1-r1/officeqa/r1/material") == 3 and role.count("fwd/s1-r1/officeqa/r4/check") == 3
