"""coevo5 baselines (registration §11, §13.2-13.5): the frozen SkillOpt v9 learner run as one learning unit per stage
on the bench's historical train and val parts, the stage's worst case reserved and settled from the frozen ledger, the
learner's own stops carried as in study F, every other pending reason and every open intent or unconfirmed cleanup
pausing the unit, and the slots its own workers need held throughout."""
from copy import deepcopy

import pytest

from skillopt.coevo5 import baseline, chain
from skillopt.coevo5.budget import Budget, step_scope
from skillopt.coevo5.calls import Slots
from skillopt.coevo5.cells import Pause
from skillopt.coevo5.ledger import attempt_bound, request_bytes
from skillopt.coevo5.outcomes import AssumptionBroken
from skillopt.coevo5.protocol import BASELINE_INFLIGHT, BASELINE_LEARNING_CAP, ORDER, SLOTS
from skillopt.coevo5.units import Setting
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from skillopt.continual_learning import skillopt as frozen_skillopt
from tests.test_continual_learning_domains import evaluate
from tests.test_continual_learning_generalization_v8 import API

CHAIN = "SkillOpt-glm"
MODEL = {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low",
         "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 3600,
                       "initial_health_policy": "completed_response_v1"}}
RULE = "Use the requested constant result."


PUBLIC = {"searchqa": {"question": "What is the capital?", "context": ["The capital is Paris."]},
          "officeqa": {"question": "What was the total?", "context": "Table: the total was 5."},
          "livemath": {"question": "Which value?", "choices": "A. one\n\nB. two"},
          "spreadsheetbench": {"instruction": "Set A1 to one.", "input_files": ["public.xlsx"],
                               "answer_position": "Sheet1!A1"},
          "alfworld": {"game_file": "public-game.tw-pddl"}}
PRIVATE = {"searchqa": {"answers": ["Paris", "alt"]}, "officeqa": {"answer": "5"}, "livemath": {"answer": "A"},
           "spreadsheetbench": {"test_files": ["private.xlsx"], "answer_position": "Sheet1!A1"},
           "alfworld": {"game_metadata": {}}}


def _task(task_id, family, partition, bench):
    return {"task_id": task_id, "family_id": family, "project_id": "", "partition": partition,
            "public": deepcopy(PUBLIC[bench]), "private": deepcopy(PRIVATE[bench])}


def _panels(bench, train=2, val=8):
    parts = {"train": [_task("t%d" % n, "ft%d" % n, "development", bench) for n in range(train)],
             "val": [_task("v%d" % n, "fv%d" % n, "skill_confirmation", bench) for n in range(val)]}
    return {part: {"version": "continual-panel-v1", "benchmark": bench, "dataset_revision": "fixture-domain-v1",
                   "provenance": "fixture", "tasks": tasks} for part, tasks in parts.items()}


@pytest.fixture
def setting(tmp_path, monkeypatch):
    panels = {b: _panels(b) for b in ORDER}

    def load(pinned, bench, part):
        assert pinned == {"fixture": True}
        return deepcopy(panels[bench][part])
    monkeypatch.setattr(baseline.data, "_load", load)
    pools = {b: [{"task_id": t["task_id"]} for part in ("train", "val") for t in panels[b][part]["tasks"]]
             for b in ORDER}
    value = Setting(run="run-1", root=tmp_path, shared=tmp_path / "shared", pools=pools, regression={},
                    tolerance={}, cards={}, rubrics={}, instructions={}, runtime={b: {} for b in ORDER},
                    clients=None, budget=Budget(tmp_path / "ledger", poll=0),
                    slots={name: Slots(tmp_path / "slots", name, count, poll=0) for name, count in SLOTS.items()},
                    sources=None,
                    extra={"pinned": {"fixture": True}, "baseline": {"model": MODEL, "service": None, "repo": None,
                                                                     "gepa_source": None}})
    value.budget.declare(chain.caps(CHAIN))
    return value, panels


def _fixture_learner(calls):
    def frozen(setting, name, value, panel, out):
        calls.append(name)
        return frozen_skillopt.run_stage(value, panel, out, fixture_api=API(RULE), fixture_evaluate=evaluate("searchqa"))
    return frozen


def _scope(stage=1):
    return step_scope(CHAIN, stage, "learning")


def test_a_stage_runs_the_frozen_learner_and_settles_its_ledger(setting, tmp_path):
    value, _ = setting
    calls = []
    skill, record = baseline.learn(value, tmp_path / CHAIN, CHAIN, 1, "", frozen=_fixture_learner(calls))
    result = record["result"]
    assert RULE in skill and result["action"] == "selected_update" and result["accepted_steps"] >= 1
    assert (result["train_tasks"], result["selection_tasks"]) == (2, 8)
    learning = tmp_path / CHAIN / "s1" / "learning" / "attempt-1" / "learning"
    receipts = [read_json(p, sealed=True)["receipt"] for p in sorted((learning / "calls").glob("*.json"))]
    reported = sum(a["usage"]["prompt_tokens"] + a["usage"]["completion_tokens"] for r in receipts
                   for a in r["attempts"])
    assert receipts and result["charged"] == reported  # every attempt reported its usage
    assert value.budget.snapshot()[_scope()] == {"cap": BASELINE_LEARNING_CAP, "settled": reported, "open": 0}
    manifest = read_json(learning.parent / "manifest.json", sealed=True)
    assert manifest["seed"] == value.seed + 1 and manifest["method"] == "skillopt" and manifest["parent_skill"] == ""
    assert manifest["version"] == "continual-learning-v9" and manifest["budget"]["max_metric_calls"] == 8000
    assert baseline.learn(value, tmp_path / CHAIN, CHAIN, 1, "", frozen=_fixture_learner(calls)) == (skill, record)
    assert calls == [CHAIN]  # a complete unit is never run again


def test_the_learning_panel_keeps_the_pool_and_the_historical_roles(setting):
    value, _ = setting
    value.pools["spreadsheetbench"] = [{"task_id": "t1"}, {"task_id": "v3"}, {"task_id": "v5"}]  # the qualified part
    panel, train, selection = baseline.learning_panel(value, "spreadsheetbench")
    assert [t["task_id"] for t in panel["tasks"]] == ["t1", "v3", "v5"]
    assert (train, selection) == (["ft1"], ["fv3", "fv5"])
    value.pools["spreadsheetbench"] = [{"task_id": "t1"}]
    with pytest.raises(ValueError, match="historical train and val"):  # §2.1: not runnable as frozen
        baseline.learning_panel(value, "spreadsheetbench")


def _result(parent, reason, *, status="pending", skill=None, unclosed=0):
    return {"status": status, "candidate_skill": parent if skill is None else skill, "reason": reason,
            "costs": {"unclosed_calls": unclosed}, "record_hash": "r" * 64, "steps": []}


def _returning(result, write=None):
    def frozen(setting, name, value, panel, out):
        out.mkdir(parents=True, exist_ok=True)
        if write is not None:
            write(out)
        return result
    return frozen


@pytest.mark.parametrize("reason", ["max_metric_calls", "reported_token_stop_threshold",
                                    "native_optimizer_json_rejected_after_retry:invalid_json_document",
                                    "native_optimizer_incomplete", "native_candidate_exceeds_skill_budget"])
def test_the_learners_own_stops_carry_the_parent(setting, tmp_path, reason):
    value, _ = setting
    skill, record = baseline.learn(value, tmp_path / CHAIN, CHAIN, 1, "- parent rule\n",
                                   frozen=_returning(_result("- parent rule\n", reason)))
    assert skill == "- parent rule\n" and record["result"]["action"] == "pending_carry_parent"
    assert value.budget.snapshot()[_scope()] == {"cap": BASELINE_LEARNING_CAP, "settled": 0, "open": 0}


@pytest.mark.parametrize("reason, kind", [("unknown_cost_attempt_cap", "infrastructure_incomplete"),
                                          ("insufficient_known_selection", "infrastructure_incomplete"),
                                          ("incomplete_usage", "infrastructure_incomplete"),
                                          ("OSError", "infrastructure_incomplete"),
                                          ("native_cleanup_unconfirmed", "cleanup"),
                                          ("native_cleanup_evidence_unreadable", "cleanup")])
def test_other_pending_reasons_pause_the_unit(setting, tmp_path, reason, kind):
    value, _ = setting
    with pytest.raises(Pause) as stopped:
        baseline.learn(value, tmp_path / CHAIN, CHAIN, 1, "", frozen=_returning(_result("", reason)))
    assert stopped.value.kind == kind and stopped.value.cell == "%s/s1/learning" % CHAIN
    if kind != "cleanup":
        assert stopped.value.reason == "baseline_pending:" + reason
    status = read_json(tmp_path / CHAIN / "s1" / "learning" / "attempt-1" / "status.json", sealed=True)
    assert status["kind"] == kind and value.budget.snapshot()[_scope()]["open"] == 0


def _evaluation(name, row):
    def write(out):
        write_json(out / "evaluation_intents" / name, seal({"position": name}))
        if row is not None:
            write_json(out / "evaluations" / name, seal(row))
    return write


@pytest.mark.parametrize("write, unclosed, kind", [
    (_evaluation("a.json", None), 0, "infrastructure_incomplete"),  # an evaluation intent without its record
    (None, 1, "infrastructure_incomplete"),  # a model call intent without its receipt
    (_evaluation("a.json", {"prediction": {"cleanup_confirmed": False}}), 0, "cleanup")])
def test_open_intents_and_unconfirmed_cleanup_pause_a_completed_run(setting, tmp_path, write, unclosed, kind):
    value, _ = setting
    result = _result("", "native_skillopt_development_selection", status="completed", skill="- learned\n",
                     unclosed=unclosed)
    with pytest.raises(Pause) as stopped:
        baseline.learn(value, tmp_path / CHAIN, CHAIN, 1, "", frozen=_returning(result, write))
    assert stopped.value.kind == kind


def _call(out, name, *, usage=None, attempts=1, max_tokens=100):
    intent = seal({"role": "solver", "system": "S" * 40, "user": "U" * 60, "max_tokens": max_tokens})
    write_json(out / "call_intents" / name, intent)
    if usage is not None:
        write_json(out / "calls" / name, seal({"role": "solver", "intent_hash": intent["record_hash"], "receipt": {
            "attempts": [{"error": "ReadTimeout"}] * (attempts - 1) + [{"usage": usage}]}}))


def test_the_settlement_charges_unknown_attempts_at_their_bound_and_a_breach_halts(setting, tmp_path):
    value, _ = setting
    bound = attempt_bound(request_bytes("S" * 40, "U" * 60), 100)

    def calls(out):
        _call(out, "a.json", usage={"prompt_tokens": 30, "completion_tokens": 7}, attempts=2)  # one attempt unknown
        _call(out, "b.json")  # an intent without a receipt: every attempt of the client
    result = _result("", "native_skillopt_development_selection", status="completed", skill="- learned\n")
    skill, record = baseline.learn(value, tmp_path / CHAIN, CHAIN, 1, "", frozen=_returning(result, calls))
    assert skill == "- learned\n" and record["result"]["charged"] == 37 + bound + 3 * bound

    def beyond(out):
        _call(out, "a.json", usage={"prompt_tokens": 30, "completion_tokens": 101})  # more than max_tokens
    with pytest.raises(Pause) as stopped:
        baseline.learn(value, tmp_path / CHAIN, CHAIN, 2, skill, frozen=_returning(result, beyond))
    assert stopped.value.kind == "assumption"
    with pytest.raises(AssumptionBroken):  # the ledger halted: no unit attempt begins until the owner's decision
        value.budget.generation()


@pytest.mark.parametrize("resume", [False, True])
def test_a_halt_stops_the_learners_dispatches_and_pauses_the_unit(setting, tmp_path, monkeypatch, resume):
    """§13.4: a halt during the frozen learner's run (even one resumed at once) refuses its every later dispatch,
    whatever the learner does with the error, and the unit pauses after the stage is settled."""
    from skillopt.validator_pilot.api import CachedAPI

    value, _ = setting
    sent = []
    monkeypatch.setattr(CachedAPI, "_perform", lambda api, request, identifier: sent.append(identifier) or {})
    stub, refused = CachedAPI._perform, []

    def frozen(setting, name, manifest, panel, out):
        _call(out, "a.json", usage={"prompt_tokens": 30, "completion_tokens": 7})
        CachedAPI._perform(None, {}, "a")
        setting.budget.halt("breach elsewhere", label="E-glm/s1/train")  # another chain's breach
        if resume:
            setting.budget.resume(decision="the owner reconciled the ledger")
        for key in ("b", "c"):  # the learner swallows the error and tries again
            try:
                CachedAPI._perform(None, {}, key)
            except AssumptionBroken as error:
                refused.append(str(error))
        return _result("", "native_skillopt_development_selection", status="completed", skill="- learned\n")
    with pytest.raises(Pause) as stopped:
        baseline.learn(value, tmp_path / CHAIN, CHAIN, 1, "", frozen=frozen)
    assert stopped.value.kind == "assumption" and sent == ["a"] and len(refused) == 2
    assert value.budget.snapshot()[_scope()]["open"] == 0 and value.budget.snapshot()[_scope()]["settled"] == 37
    assert CachedAPI._perform is stub  # the guard is removed once the learner returns


@pytest.mark.parametrize("damage", ["fewer_intents", "unlistable"])
def test_a_ledger_that_cannot_account_for_the_dispatches_is_charged_in_full(setting, tmp_path, monkeypatch, damage):
    """§13.2: an intent missing for a dispatch, or a ledger folder that cannot be listed, settles the whole
    reservation and halts the ledger (never zero)."""
    from skillopt.validator_pilot.api import CachedAPI

    value, _ = setting
    monkeypatch.setattr(CachedAPI, "_perform", lambda api, request, identifier: {})

    def frozen(setting, name, manifest, panel, out):
        out.mkdir(parents=True, exist_ok=True)
        CachedAPI._perform(None, {}, "a")
        CachedAPI._perform(None, {}, "b")
        if damage == "fewer_intents":
            _call(out, "a.json", usage={"prompt_tokens": 30, "completion_tokens": 7})
        else:
            (out / "call_intents").write_text("not a folder", encoding="utf-8")
        return _result("", "native_skillopt_development_selection", status="completed", skill="- learned\n")
    with pytest.raises(Pause) as stopped:
        baseline.learn(value, tmp_path / CHAIN, CHAIN, 1, "", frozen=frozen)
    assert stopped.value.kind == "assumption"
    assert value.budget.snapshot()[_scope()]["settled"] == BASELINE_LEARNING_CAP
    with pytest.raises(AssumptionBroken):
        value.budget.generation()


def test_unreadable_cleanup_evidence_is_a_cleanup_stop(setting, tmp_path):
    value, _ = setting

    def write(out):
        (out / "host_only" / "scorer_artifacts" / "case").mkdir(parents=True)
        (out / "host_only" / "scorer_artifacts" / "case" / "cleanup.json").write_text("{torn", encoding="utf-8")
    result = _result("", "native_skillopt_development_selection", status="completed", skill="- learned\n")
    with pytest.raises(Pause) as stopped:
        baseline.learn(value, tmp_path / CHAIN, CHAIN, 1, "", frozen=_returning(result, write))
    assert stopped.value.kind == "cleanup"


def test_a_stage_holds_the_slots_of_the_learners_own_workers(setting, tmp_path):
    value, _ = setting
    free = {}

    def count(name):
        pool, found = value.slots[name], 0
        for index in range(pool.count):
            descriptor = pool._take(index)
            if descriptor is not None:
                pool._release(descriptor)
                found += 1
        return found

    def frozen(setting, name, manifest, panel, out):
        free.update({name: count(name) for name in SLOTS})
        return _result(manifest["parent_skill"], "max_metric_calls")
    baseline.learn(value, tmp_path / CHAIN, CHAIN, 4, "", frozen=frozen)  # SpreadsheetBench
    assert free == {"glm-5.3": SLOTS["glm-5.3"] - BASELINE_INFLIGHT, "deepseek-v4-flash": SLOTS["deepseek-v4-flash"],
                    "spreadsheet-native": 0, "alfworld-episode": SLOTS["alfworld-episode"]}
    assert all(count(name) == SLOTS[name] for name in SLOTS)  # released


def test_a_gepa_stage_builds_the_frozen_gepa_manifest(setting):
    value, _ = setting
    manifest, panel = baseline.frozen_manifest(value, "GEPA-glm", 2, "- parent\n")
    assert manifest["method"] == "gepa" and manifest["parent_skill"] == "- parent\n"
    assert manifest["seed"] == value.seed + 2 and panel["benchmark"] == "officeqa"
    assert manifest["recovery_policy"]["skill_budget_bytes"] == 32000 and manifest["solver_workers"] == 8
