"""coevo5 chain runner (registration §1, §2.1, §10, §13.3-13.4): the scopes a chain declares, the order of its units
(the SpreadsheetBench test-side qualification, then the chain's own stage 0 -- v2 shares none, §1), the NoSkill-glm
reference's stage 0 alone, evaluation children whose pause stops the chain, children that fail before their attempt,
one runner per chain, terminations of idle chains only, a manifest mismatch, and terminal markers bound to the run."""
import pytest

from skillopt.coevo5 import baseline, chain, step
from skillopt.coevo5.budget import OVERALL, Budget, chain_scope, deepseek_scope, step_scope
from skillopt.coevo5.cells import exclusive
from skillopt.coevo5.evaluation import _next_attempt
from skillopt.coevo5.protocol import (
    BASELINE_LEARNING_CAP,
    CHAIN_CAP,
    DEEPSEEK_CEILING,
    DEEPSEEK_CHAIN_CAP,
    EVALUATION_CAP,
    ORDER,
    OVERALL_CEILING,
    STAGE0_EVALUATION_CAP,
)
from skillopt.coevo5.skill import Rule, Skill
from skillopt.coevo5.units import Setting
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from skillopt.validator_pilot.api import digest


def test_the_scopes_of_each_chain():
    e = chain.caps("E-glm")
    assert e[OVERALL] == OVERALL_CEILING and e[chain_scope("E-glm")] == CHAIN_CAP["E-glm"]
    # v2 §1: no shared stage 0 -- E-glm evaluates its own (the scaffold), as every chain
    assert e[step_scope("E-glm", 0, "evaluation")] == STAGE0_EVALUATION_CAP["E"]
    assert step_scope("stage0-glm", 0, "evaluation") not in e and step_scope("E-glm", 5, "evaluation") in e
    assert CHAIN_CAP["E-glm"] == sum(v for k, v in e.items() if k.startswith("step:"))
    i = chain.caps("I-glm")
    assert i[step_scope("I-glm", 0, "evaluation")] == STAGE0_EVALUATION_CAP["I"]
    assert CHAIN_CAP["I-glm"] == sum(v for k, v in i.items() if k.startswith("step:"))
    assert chain.caps("NoSkill-glm") == {  # the reference: its stage 0 only
        OVERALL: OVERALL_CEILING, chain_scope("NoSkill-glm"): CHAIN_CAP["NoSkill-glm"],
        step_scope("NoSkill-glm", 0, "evaluation"): STAGE0_EVALUATION_CAP["N"]}
    b = chain.caps("SkillOpt-glm")  # defined; run by no v2 chain
    assert b[step_scope("SkillOpt-glm", 1, "learning")] == BASELINE_LEARNING_CAP
    assert b[step_scope("SkillOpt-glm", 2, "evaluation")] == EVALUATION_CAP["baseline"]
    assert b[step_scope("SkillOpt-glm", 0, "evaluation")] == STAGE0_EVALUATION_CAP["baseline"]
    assert chain_scope("E-glm") not in b
    assert CHAIN_CAP["SkillOpt-glm"] == sum(v for k, v in b.items() if k.startswith("step:"))
    ds = chain.caps("E-ds")  # GLM-5.3: the method roles' learning steps only
    assert not any(s.startswith("step:") and s.endswith(":evaluation") for s in ds)
    assert step_scope("E-ds", 1, "learning") in ds
    # v3 §9: the deepseek solver's own allowance -- in all, per chain, and counted per step (no extra cap)
    assert ds[deepseek_scope()] == DEEPSEEK_CEILING and ds[deepseek_scope("E-ds")] == DEEPSEEK_CHAIN_CAP["E-ds"]
    assert {s for s in ds if s.startswith("deepseek:E-ds:")} == {
        deepseek_scope("E-ds", k, t) for k in range(6) for t in ("learning", "evaluation") if (k, t) != (0, "learning")}
    assert chain.evaluation_scopes("E-ds", 3) == ("deepseek", "deepseek:E-ds", "deepseek:E-ds:3:evaluation")
    assert chain.deepseek_scopes("I-ds") == ("deepseek", "deepseek:I-ds")
    assert chain.caps("NoSkill-ds") == {  # v3 §1: deepseek's reference, stage 0 only, no GLM-5.3 call
        OVERALL: OVERALL_CEILING, chain_scope("NoSkill-ds"): CHAIN_CAP["NoSkill-ds"],
        deepseek_scope(): DEEPSEEK_CEILING, deepseek_scope("NoSkill-ds"): DEEPSEEK_CHAIN_CAP["NoSkill-ds"],
        deepseek_scope("NoSkill-ds", 0, "evaluation"): DEEPSEEK_CHAIN_CAP["NoSkill-ds"]}
    assert not chain.learns("NoSkill-ds") and chain.start(None, "NoSkill-ds") == Skill()
    assert chain.evaluation_scopes("stage0-glm", 0) == (OVERALL, chain_scope("E-glm"),
                                                        step_scope("stage0-glm", 0, "evaluation"))


@pytest.fixture
def setting(tmp_path, monkeypatch):
    learned = []

    def learn(value, root, name, stage, parent):
        learned.append(stage)
        child = parent.add(Rule("s%d-r1" % stage, "Rule of stage %d." % stage, ORDER[stage - 1]))
        return child, {"result": {"accepted": [{"id": "s%d-r1" % stage, "placement": "local"}]}}
    monkeypatch.setattr(step, "learn", learn)
    value = Setting(run="run-1", root=tmp_path, shared=tmp_path / "shared", pools={}, regression={}, tolerance={},
                    cards={}, rubrics={}, instructions={b: "Instruction for %s." % b for b in ORDER}, runtime={},
                    clients=None, budget=Budget(tmp_path / "ledger", poll=0), slots={}, sources=None)
    return value, learned


def _ok(value):
    return chain.EXIT_COMPLETE


def _launcher(launched, *, pause=None):
    """The child's protocol without its work: a unit whose last attempt awaits the owner's decision is not run; the
    ``pause`` unit pauses its first attempt; every other unit completes."""
    def launch(value, spec):
        launched.append((spec["chain"], spec["stage"], spec["benchmark"], spec["previous"] is not None))
        root = chain.unit_root(value, spec["chain"], spec["stage"], spec["benchmark"])
        attempt = _next_attempt(root)
        if attempt is None:
            return chain.EXIT_AWAITING
        attempt.mkdir(parents=True)
        if (spec["chain"], spec["stage"], spec["benchmark"]) == pause and attempt.name == "attempt-1":
            write_json(attempt / "status.json", seal({"status": "paused", "kind": "budget", "reason": "budget_stop",
                                                     "cell": "x"}))
            return chain.EXIT_PAUSED
        write_json(root / "unit.json", seal({"run": value.run, "chain": spec["chain"], "stage": spec["stage"],
                                             "benchmark": spec["benchmark"], "status": "complete",
                                             "skill_sha256": digest(spec["skill"])}))
        return chain.EXIT_COMPLETE
    return launch


def test_the_run_declares_what_remains_of_the_overall_cap(setting):
    value, _ = setting
    value.extra["overall"] = OVERALL_CEILING - 1234  # the manifest's: the GLM-5.3 tokens spent before the run
    assert chain.run(value, "E-ds", launch=_launcher([]), qualify=_ok) == {"status": "complete"}
    assert value.budget.snapshot()[OVERALL]["cap"] == OVERALL_CEILING - 1234
    assert chain.caps("E-glm", 99)[OVERALL] == 99


def test_e_glm_evaluates_its_scaffold_at_stage_zero_then_its_stages_in_order(setting, tmp_path):
    value, learned = setting
    launched = []
    assert chain.run(value, "E-glm", launch=_launcher(launched), qualify=_ok) == {"status": "complete"}
    assert learned == [1, 2, 3, 4, 5]
    assert [x[:2] for x in launched[:5]] == [("E-glm", 0)] * 5 and not any(x[3] for x in launched[:5])
    assert all(x[3] for x in launched[5:]) and not (tmp_path / "stage0-glm").exists()
    assert len(launched) == 5 * 6 and (tmp_path / "E-glm" / "chain-complete.json").exists()
    scaffold = chain.start(value, "E-glm")  # v2 §2: every section's heading and applicability line, no rule
    assert scaffold == Skill(scaffold=True) and scaffold.render().count("## ") == len(ORDER)
    unit = read_json(chain.unit_root(value, "E-glm", 0, "searchqa") / "unit.json", sealed=True)
    assert unit["skill_sha256"] == digest(scaffold.render())
    assert chain.run(value, "E-glm", launch=_launcher(launched), qualify=_ok) == {"status": "complete"}
    assert len(launched) == 30  # nothing runs again


def test_the_noskill_reference_evaluates_the_empty_skill_at_stage_zero_only(setting, tmp_path):
    value, learned = setting
    launched = []
    assert chain.run(value, "NoSkill-glm", launch=_launcher(launched), qualify=_ok) == {"status": "complete"}
    assert learned == [] and [x[:2] for x in launched] == [("NoSkill-glm", 0)] * 5 and not chain.learns("NoSkill-glm")
    marker = read_json(tmp_path / "NoSkill-glm" / "chain-complete.json", sealed=True)
    assert marker["skill_sha256"] == digest("") and chain.start(value, "NoSkill-glm") == Skill()


def test_a_baseline_chain_evaluates_its_own_stage_zero_and_its_learners_text(setting, tmp_path, monkeypatch):
    value, learned = setting
    texts = []

    def learn(v, root, name, stage, parent):
        texts.append(parent)
        return parent + "- baseline rule %d\n" % stage, {"result": {"action": "selected_update"}}
    monkeypatch.setattr(baseline, "learn", learn)
    launched = []
    assert chain.run(value, "E-glm", launch=_launcher(launched), qualify=_ok) == {"status": "complete"}
    first = len(launched)
    specs = []

    def launch(v, spec):
        specs.append(spec)
        return _launcher(launched)(v, spec)
    assert chain.run(value, "GEPA-glm", launch=launch, qualify=_ok) == {"status": "complete"}
    assert learned == [1, 2, 3, 4, 5] and texts == ["", *("".join("- baseline rule %d\n" % k for k in range(1, s))
                                                           for s in range(2, 6))]
    assert [x[:2] for x in launched[first:first + 5]] == [("GEPA-glm", 0)] * 5  # its own (v2 shares none)
    assert not any(x[3] for x in launched[first:first + 5])
    assert all(s["skill"] == "" for s in specs[:5]) and specs[-1]["skill"].count("- baseline rule") == 5
    marker = read_json(tmp_path / "GEPA-glm" / "chain-complete.json", sealed=True)
    assert marker["skill"] == specs[-1]["skill"] and marker["skill_sha256"] == digest(specs[-1]["skill"])


def test_chain_i_starts_from_the_instructions(setting):
    value, _ = setting
    launched = []
    chain.run(value, "I-glm", launch=_launcher(launched), qualify=_ok)
    assert launched[0][:2] == ("I-glm", 0) and not launched[0][3]
    assert chain.start(value, "I-glm").render().count("Instruction for") == 5


def test_a_paused_evaluation_pauses_the_chain_and_nothing_resumes_by_itself(setting, tmp_path):
    value, learned = setting
    launched = []
    found = chain.run(value, "E-ds", launch=_launcher(launched, pause=("E-ds", 2, "livemath")), qualify=_ok)
    assert found == {"status": "paused", "kind": "budget", "reason": "budget_stop",
                     "unit": "E-ds/s2/evaluation/livemath"}
    assert learned == [1, 2] and len(launched) == 15  # the other four units of stage 2 still completed
    assert not (tmp_path / "E-ds" / "chain-complete.json").exists()
    again = []
    assert chain.run(value, "E-ds", launch=_launcher(again, pause=("E-ds", 2, "livemath")), qualify=_ok) == {
        "status": "paused", "kind": "awaiting_owner_decision", "reason": "attempt-1",
        "unit": "E-ds/s2/evaluation/livemath"}
    # a restarted runner re-enters stages 1-2 (their learning units return their records) and relaunches one unit
    assert again == [("E-ds", 2, "livemath", True)] and learned == [1, 2, 1, 2]
    root = chain.unit_root(value, "E-ds", 2, "livemath")
    write_json(root / "attempt-1" / "recovery.json", {"by": "owner", "date": "2026-10-17", "decision": "redo"})
    assert chain.run(value, "E-ds", launch=_launcher(again, pause=("E-ds", 2, "livemath")),
                     qualify=_ok) == {"status": "complete"}
    assert (root / "attempt-2").is_dir() and learned == [1, 2, 1, 2, 1, 2, 3, 4, 5]


def test_termination_ends_the_chain(setting, tmp_path):
    value, _ = setting
    chain.terminate(value, "E-ds", decision="stop here")
    assert chain.run(value, "E-ds", launch=_launcher([]), qualify=_ok) == {"status": "terminated"}
    with pytest.raises(ValueError):
        chain.terminate(value, "E-ds", decision=" ")


def test_no_qualified_spreadsheet_test_item_stops_the_chain_before_any_stage_zero_call(setting):
    value, learned = setting
    launched, asked = [], []
    found = chain.run(value, "E-ds", launch=_launcher(launched), qualify=lambda v: chain.EXIT_NO_QUALIFIED)
    assert found["status"] == "paused" and found["kind"] == "no_qualified_test_items"
    assert launched == [] and learned == []

    def qualify(v):
        asked.append(1)
        return chain.EXIT_COMPLETE
    pause = ("E-ds", 1, "searchqa")
    assert chain.run(value, "E-ds", launch=_launcher(launched, pause=pause), qualify=qualify)["status"] == "paused"
    assert chain.run(value, "E-ds", launch=_launcher(launched, pause=pause), qualify=qualify)["status"] == "paused"
    assert asked == [1]  # stage 0 is complete: the qualification is not asked again


def test_a_child_that_fails_before_its_attempt_still_needs_the_owners_decision(setting, tmp_path):
    value, _ = setting
    failing = {"E-ds/0/searchqa"}

    def launch(v, spec):
        if "%s/%d/%s" % (spec["chain"], spec["stage"], spec["benchmark"]) in failing:
            return 1  # e.g. the manifest or the client could not be loaded
        return _launcher([])(v, spec)
    found = chain.run(value, "E-ds", launch=launch, qualify=_ok)
    assert (found["kind"], found["reason"]) == ("exception", "child_failed_before_its_attempt")
    root = chain.unit_root(value, "E-ds", 0, "searchqa")
    assert (root / "attempt-1" / "status.json").exists() and _next_attempt(root) is None
    failing.clear()
    assert chain.run(value, "E-ds", launch=launch, qualify=_ok)["kind"] == "awaiting_owner_decision"


def test_one_runner_per_chain_and_only_an_idle_chain_is_terminated(setting, tmp_path):
    value, _ = setting
    root = tmp_path / "E-ds"
    with exclusive(root / chain.RUNNER_LOCK):  # a runner is running
        with pytest.raises(ValueError):
            chain.run(value, "E-ds", launch=_launcher([]), qualify=_ok)
        with pytest.raises(ValueError):
            chain.terminate(value, "E-ds", decision="stop")
    with exclusive(chain.unit_root(value, "E-ds", 3, "alfworld") / ".lock"):  # an evaluation child is running
        with pytest.raises(ValueError, match="still running"):
            chain.terminate(value, "E-ds", decision="stop")
    assert not (root / "chain-terminated.json").exists()
    chain.terminate(value, "E-ds", decision="stop")
    with pytest.raises(ValueError):
        chain.terminate(value, "E-ds", decision="again")


def test_a_manifest_mismatch_refuses_a_new_chain_and_terminates_a_started_one(setting, tmp_path):
    value, learned = setting

    def changed():
        raise ValueError("Files differ from the launch manifest: ['skillopt/coevo5/step.py']")
    value.extra["verify"] = changed
    with pytest.raises(ValueError):
        chain.run(value, "E-ds", launch=_launcher([]), qualify=_ok)
    assert not (tmp_path / "E-ds" / "chain.json").exists()
    value.extra["verify"] = lambda: None
    chain.run(value, "E-ds", launch=_launcher([], pause=("E-ds", 1, "searchqa")), qualify=_ok)
    value.extra["verify"] = changed
    assert chain.run(value, "E-ds", launch=_launcher([]), qualify=_ok) == {"status": "terminated",
                                                                        "reason": "manifest_mismatch"}
    marker = tmp_path / "E-ds" / "chain-terminated.json"
    assert marker.exists() and "manifest_mismatch" in marker.read_text()
    value.extra["verify"] = lambda: None
    assert chain.run(value, "E-ds", launch=_launcher([]), qualify=_ok) == {"status": "terminated"}


def test_terminal_markers_name_their_run(setting, tmp_path):
    value, _ = setting
    chain.terminate(value, "E-ds", decision="stop")
    value.run = "run-2"
    with pytest.raises(ValueError, match="another run"):
        chain.run(value, "E-ds", launch=_launcher([]), qualify=_ok)
