"""KOR probe-stage pilot: fixture controls with no model calls, containers or KOR data."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import continue_fivebench_baselines as sequence
from scripts import run_kor_probe_pilot as pilot
from skillopt.applicability import kor, kor_probes
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import output_lock, read_json, write_json
from skillopt.validator_pilot.api import digest
from tests.test_feedback_ablation_pilot import FILES, source_tree
from tests.test_kor_probes import panel as probe_panel

PARENT = "Always restate the deliverable and test edge cases before answering."
SERVICE = {"name": "learning-service"}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def f_study(tmp_path, monkeypatch):
    tasks = probe_panel(monkeypatch)  # synthetic registered rules
    source_tree(tmp_path / "src", 6000)
    source_tree(tmp_path / "derived", 32000)
    plan = seal({"source_identity": {name: sha(text) for name, text in FILES.items()}, "repeats": 2, "tasks": [],
                 "config": {"panels": {"korbench": str(tmp_path / "kor.json"), "bigcodebench": None},
                            "methods": ["no_skill"], "model": {"name": "solver"}, "repeats": 2}})
    write_json(tmp_path / "noskill/plan.json", plan)
    reference = {"root": str(tmp_path / "noskill"), "source": str(tmp_path / "src"),
                 "evaluation_source": str(tmp_path / "derived"), "python": "python", "plan_hash": plan["record_hash"],
                 "model_service": seal({"name": "solver-service"})}
    model = {"provider": "bigmodel", "name": "glm-5.3", "reasoning_effort": "low", "transport": {}}
    protocol = seal({"version": sequence.BUDGET_SEQUENCE, "methods": ["skillopt", "gepa"],
                     "references": {"korbench": reference}, "learning_model_service": seal(SERVICE),
                     "learning_client_options": {}, "model": model, "config": {"workers": 2}})
    write_json(tmp_path / "f/protocol.json", protocol)
    for method in ("skillopt", "gepa"):  # F finished both methods (the paid stage's precondition)
        write_json(tmp_path / f"f/{method}/final.json", seal({"protocol_hash": protocol["record_hash"],
                                                              "method": method, "attempted_stages": 5}))
    monkeypatch.setattr(pilot, "_parent", lambda root, value: {"skill": PARENT, "stage_hash": "s" * 64,
                                                               "budget": 32000, "max_tokens": 4000})
    probes = kor_probes.generate(tasks, per_rule=2, seed=3)
    write_json(tmp_path / "probes.json", seal({"version": kor_probes.VERSION, "verifier": kor.VERSION,
                                               "protocol_hash": protocol["record_hash"],
                                               "panel_plan_hash": plan["record_hash"], "probes": probes}))
    return tmp_path / "f", tmp_path / "probes.json", {p["task_id"]: p for p in probes}


def answer(probes, method, task_id):
    probe = probes[task_id]
    wrong = method == "a2" or (method == "a0" and probe["private"]["category"] == "operation")
    return probe["private"]["mutated" if wrong else "reference"]


class FakeAPI:
    model = "glm-5.3"

    def __init__(self, responses):
        self.responses, self.calls, self.service, self.failure, self.forge = responses, [], SERVICE, None, False
        self.wrong_model = None

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        if self.failure is not None:
            raise self.failure
        self.calls.append(user)
        request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                   "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        if self.forge:
            request = {**request, "user": "another prompt"}
        receipt = {"request": request, "request_hash": digest(request), "ok": True, "finish_reason": "stop",
                   "usage": {"total_tokens": 10}, "response": self.responses("Evidence from" in user)}
        return {**receipt, **(self.wrong_model or {})}

    def close(self):
        pass


def fake_run(run, config, policies, probes, solved):
    """What the frozen worker leaves behind: plan, checkpoints and sealed predictions."""
    panel = json.loads(Path(config["panels"]["korbench"]).read_text())
    if not (run / "plan.json").exists():
        write_json(run / "plan.json", seal({"config": config, "repeats": 2, "tasks": [
            {"benchmark": "korbench", "task_id": t["task_id"], "task_hash": digest(t)} for t in panel["tasks"]]}))
    plan = read_json(run / "plan.json", sealed=True)
    for method, skill in policies.items():
        stage = 1 if skill else 0
        path = run / f"checkpoints/{method}/h0/s{stage}.json"
        if not path.exists():
            write_json(path, seal({"plan_hash": plan["record_hash"], "method": method, "history": "h0",
                                   "stage": stage, "skill_text": skill, "skill_hash": sha(skill)}))
        checkpoint = read_json(path, sealed=True)
        for task in panel["tasks"]:
            for repeat in (0, 1):
                target = run / f"predictions/{method}-{task['task_id'].replace(':', '-')}-{repeat}/prediction.json"
                if not target.exists():
                    solved.append((method, task["task_id"]))
                    write_json(target, seal({
                        "request": {"benchmark": "korbench", "plan_hash": plan["record_hash"], "repeat": repeat,
                                    "checkpoint_hash": checkpoint["record_hash"], "task_hash": digest(task)},
                        "prediction": {"status": "available", "output": answer(probes, method, task["task_id"])}}))
    return plan


@pytest.fixture
def pilot_run(tmp_path, monkeypatch):
    f_root, probes_path, probes = f_study(tmp_path, monkeypatch)
    solved = []

    def invoke(protocol, request_path, output, log):
        request = read_json(request_path, sealed=True)
        plan = fake_run(Path(request["run"]), request["config"], request["policies"], probes, solved)
        value = seal({"run": request["run"], "plan_hash": plan["record_hash"], "policies": request["policies"]})
        write_json(output, value)
        return value

    api = FakeAPI(lambda evidence: "<skill>" + ("Mechanism rules with scope." if evidence else "Generic scope.")
                  + "</skill>")
    monkeypatch.setattr(pilot, "_invoke", invoke)
    monkeypatch.setattr(pilot, "_client", lambda repo, rewrite, cache: api)
    pilot.prepare(f_root, probes_path, tmp_path / "pilot")
    return tmp_path / "pilot", api, solved, probes


def test_evidence_rewrites_and_held_out_comparisons(pilot_run, tmp_path):
    root, api, solved, probes = pilot_run
    result = pilot.run(root, tmp_path / "repo")
    assert result["pending_arms"] == [] and len(api.calls) == 2
    evidence = read_json(root / "evidence.json", sealed=True)
    assert evidence["counts"] == {"cipher": {"tie": 18}, "operation": {"loss": 20},
                                  "puzzle": {"tie": 8}}  # even-index probes only
    assert len(evidence["examples"]) == 8 and len({e["handler"] for e in evidence["examples"]}) == 8
    with_evidence, without = api.calls
    assert "Public check failed" in with_evidence and "Evidence from" not in without
    assert all(e["question"] in with_evidence for e in evidence["examples"])
    held = {t for t in probes if int(t.rsplit(":", 1)[1]) % 2}
    assert not any(t in with_evidence for t in held if probes[t]["public"]["question"] in with_evidence)
    assert {t for m, t in solved if m in {"a1", "a2"}} == held  # rewrites never meet their evidence probes
    report = pilot.report(root)
    c = report["comparisons_on_held_out"]
    assert c["a0_vs_no_skill"] == {"all": {"loss": 20, "tie": 26}, "cipher": {"tie": 18},
                                   "operation": {"loss": 20}, "puzzle": {"tie": 8}}
    assert c["a1_vs_a0"]["operation"] == {"win": 20} and c["a2_vs_a0"]["puzzle"] == {"loss": 8}
    assert c["a2_vs_a1"]["all"] == {"loss": 46}
    assert report["rewrites"]["a1"]["with_evidence"] and not report["rewrites"]["a2"]["with_evidence"]
    assert pilot.run(root, tmp_path / "repo") == result and len(api.calls) == 2  # replay: no new calls or solves


@pytest.mark.parametrize("response,reason", [("no block", "no_skill_block"),
                                             ("<skill>" + "x" * 32001 + "</skill>", "over_budget"),
                                             ("<skill>" + PARENT + "</skill>", "unchanged")])
def test_a_closed_failed_rewrite_leaves_its_arm_pending(pilot_run, tmp_path, response, reason):
    root, api, solved, _ = pilot_run
    api.responses = lambda evidence: response if evidence else "<skill>Generic scope.</skill>"
    result = pilot.run(root, tmp_path / "repo")
    assert result["pending_arms"] == ["a1"] and read_json(root / "rewrites/a1.json", sealed=True)["reason"] == reason
    assert not {m for m, _ in solved} & {"a1"} and "a2" in {m for m, _ in solved}
    assert pilot.report(root)["rewrites"]["a1"]["status"] == "pending"


@pytest.mark.parametrize("failure", [KeyboardInterrupt(), RuntimeError("network"), "forge"])
def test_an_open_rewrite_request_stops_the_pilot_and_is_never_resampled(pilot_run, tmp_path, failure):
    root, api, _, _ = pilot_run
    if failure == "forge":
        api.forge = True  # a receipt for another request is rejected after the intent was written
    else:
        api.failure = failure
    with pytest.raises((KeyboardInterrupt, RuntimeError, ValueError)):
        pilot.run(root, tmp_path / "repo")
    assert not (root / "rewrites/a1.json").exists() and not (root / "result.json").exists()
    api.failure, api.forge, calls = None, False, len(api.calls)
    with pytest.raises(ValueError, match="Interrupted rewrite request"):
        pilot.run(root, tmp_path / "repo")
    assert len(api.calls) == calls


def test_a_concurrent_orchestrator_is_refused(pilot_run, tmp_path):
    root, api, _, _ = pilot_run
    with output_lock(root):
        with pytest.raises(ValueError, match="Another process owns"):
            pilot.run(root, tmp_path / "repo")
    assert api.calls == []


def test_frozen_host_sources_prompt_and_artifacts(pilot_run, tmp_path, monkeypatch):
    root, _, _, _ = pilot_run
    pilot.run(root, tmp_path / "repo")
    with monkeypatch.context() as m:
        m.setattr(pilot, "SYSTEM", pilot.SYSTEM + " Be brief.")
        with pytest.raises(ValueError, match="Rewrite prompt changed"):
            pilot.run(root, tmp_path / "repo")
    with monkeypatch.context() as m:
        m.setattr(pilot, "_host_sources", lambda: {name: "0" * 64 for name in pilot.HOST_SOURCES})
        with pytest.raises(ValueError, match="Host prompt, client or scoring sources changed"):
            pilot.report(root)
    record = json.loads((root / "rewrites/a1.json").read_text())
    record["skill"] = "Something else."
    (root / "rewrites/a1.json").write_text(json.dumps(seal({k: v for k, v in record.items() if k != "record_hash"})))
    with pytest.raises(ValueError, match="does not reproduce"):
        pilot.report(root)


def reseal(path, change):
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(seal({k: v for k, v in value.items() if k != "record_hash"})))


@pytest.mark.parametrize("tamper,message", [
    (lambda root: reseal(root / "runs/a/plan.json",
                         lambda v: v["tasks"][0].update(task_hash="0" * 64)), "do not bind"),  # plan no longer the phase's
    (lambda root: write_json(root / "runs/a/predictions/extra/prediction.json", read_json(
        next((root / "runs/a/predictions").glob("*/prediction.json")))), "Duplicate probe attempt"),
    (lambda root: reseal(root / "evidence.json", lambda v: v["counts"].update(puzzle={"tie": 7})),
     "Recorded evidence differs"),
    (lambda root: reseal(root / "phase-a.json", lambda v: v.update(run="/elsewhere")), "do not bind"),
])
def test_report_replays_the_whole_chain(pilot_run, tmp_path, tamper, message):
    root, _, _, _ = pilot_run
    pilot.run(root, tmp_path / "repo")
    tamper(root)
    with pytest.raises(ValueError, match=message):
        pilot.report(root)


def test_predictions_bind_task_contents_not_just_ids(pilot_run, tmp_path):
    root, _, _, _ = pilot_run
    pilot.run(root, tmp_path / "repo")
    _, protocol, _, panels = pilot._load(root)
    tasks = [dict(t, public={**t["public"], "question": t["public"]["question"] + " edited"}) if i == 0 else t
             for i, t in enumerate(panels["all"])]
    with pytest.raises(ValueError, match="differ from the frozen probe panel"):
        pilot._predictions(root / "runs/a", protocol["configs"]["a"], {"no_skill": ""}, tasks)


@pytest.mark.parametrize("bad", [RuntimeError("network"),
                                 {"ok": False, "error_type": "unexpected_response_model", "returned_model": "other"},
                                 {"ok": True, "returned_model": "other"},
                                 {"ok": False, "error_type": "inconsistent_stream_model", "returned_model": "glm-5.3"},
                                 {"ok": False, "error_type": "inconsistent_stream_model"},
                                 {"ok": False, "error_type": "provider_content_filter", "returned_model": "glm-5.3"},
                                 {"ok": False, "finish_reason": "content_filter"}])
def test_the_solver_abort_gate_blocks_later_submissions(bad):
    made = []

    class Base:
        api = SimpleNamespace(model="glm-5.3")

        def __call__(self, system, user):
            made.append(user)
            if user == "second":
                if isinstance(bad, Exception):
                    raise bad
                return bad  # a sealed, closed receipt from the wrong model
            return {"ok": True, "returned_model": "glm-5.3"}

    gated = pilot._gated(Base)
    assert gated()("s", "first") == {"ok": True, "returned_model": "glm-5.3"}
    for user in ("second", "third"):
        with pytest.raises(pilot._SolverAbort):
            try:
                gated()("s", user)
            except Exception:  # what backends._response catches: the gate is not an Exception
                pytest.fail("the abort must not be swallowed")
    assert made == ["first", "second"]  # "third" was never submitted


def test_prepare_refuses_foreign_probes_and_load_refuses_tampering(tmp_path, monkeypatch):
    f_root, probes_path, _ = f_study(tmp_path, monkeypatch)
    value = read_json(probes_path, sealed=True)
    write_json(tmp_path / "other.json", seal({**{k: v for k, v in value.items() if k != "record_hash"},
                                               "protocol_hash": "0" * 64}))
    with pytest.raises(ValueError, match="do not belong"):
        pilot.prepare(f_root, tmp_path / "other.json", tmp_path / "pilot-a")
    pilot.prepare(f_root, probes_path, tmp_path / "pilot")
    held = tmp_path / "pilot/panels/held_out.json"
    held.write_text(held.read_text().replace("synthetic", "edited"))
    with pytest.raises(ValueError, match="changed"):
        pilot.run(tmp_path / "pilot", tmp_path / "repo")


def test_prepare_binds_the_derived_evaluation_source(tmp_path, monkeypatch):
    f_root, probes_path, _ = f_study(tmp_path, monkeypatch)
    (tmp_path / "derived/skillopt/continual_eval/runner.py").write_text("x = 2\n")
    with pytest.raises(ValueError, match="outside the Skill budget"):
        pilot.prepare(f_root, probes_path, tmp_path / "pilot")


# --------------------------------------------------------------- worker control
@pytest.fixture
def worker_env(tmp_path, monkeypatch):
    calls = {"service": 0, "generate": [], "fail_service": False}
    source = tmp_path / "derived"

    def freeze_plan(config, run):
        write_json(run / "plan.json", seal({"config": config, "repeats": 1, "tasks": []}))
        for method in config["methods"]:
            write_json(run / f"checkpoints/{method}/h0/s0.json", seal({"skill_text": ""}))

    def check(repo, model, cache, service):
        calls["service"] += 1
        if calls["fail_service"]:
            raise ValueError("Current client differs from frozen model service")

    def generate(run, *, method, **kwargs):
        assert tools.runner.PositionCalls.__name__ == "GatedCalls"  # installed before any submission
        calls["generate"].append(method)

    def register(run, method, history, stage, skill, provenance):
        read_json(run / f"checkpoints/{method}/{history}/s{stage - 1}.json", sealed=True)  # parent, as the real one
        write_json(run / f"checkpoints/{method}/{history}/s{stage}.json", seal({"skill_text": skill}))

    tools = SimpleNamespace(
        source_root=source, freeze_plan=freeze_plan, load_plan=lambda run: read_json(run / "plan.json", sealed=True),
        checkpoint_path=lambda run, method, history, stage: run / f"checkpoints/{method}/{history}/s{stage}.json",
        register_checkpoint=register,
        load_checkpoint=lambda run, method, history, stage, plan: read_json(
            run / f"checkpoints/{method}/{history}/s{stage}.json", sealed=True),
        generate=generate, runner=SimpleNamespace(PositionCalls=type("PositionCalls", (), {})), sequence=SimpleNamespace(
            verify_service=lambda root, expected=None: {"service": 1}, check_client_service=check,
            require_eval_handoff=lambda run: None))
    monkeypatch.setattr(pilot, "_worker_tools", lambda: tools)
    request = seal({"run": str(tmp_path / "run"), "config": {"methods": ["no_skill", "a0"], "model": {"name": "m"}},
                    "policies": {"no_skill": "", "a0": PARENT}, "provenance": "p", "repo": "r", "workers": 1,
                    "evaluation_source": str(source), "reference_root": str(tmp_path / "ref"), "service": {"service": 1}})
    write_json(tmp_path / "request.json", request)
    return tmp_path, calls


def test_worker_checks_the_service_on_every_entry_before_paying(worker_env):
    root, calls = worker_env
    pilot.worker(root / "request.json", root / "out-1.json")
    assert calls["service"] == 1 and calls["generate"] == ["no_skill", "a0"]
    calls["fail_service"] = True
    with pytest.raises(ValueError, match="frozen model service"):
        pilot.worker(root / "request.json", root / "out-2.json")
    assert calls["generate"] == ["no_skill", "a0"]


def test_worker_validates_every_checkpoint_before_the_first_paid_call(worker_env):
    root, calls = worker_env
    pilot.worker(root / "request.json", root / "out-1.json")
    (root / "run/checkpoints/no_skill/h0/s0.json").unlink()  # an interrupted freeze_plan
    with pytest.raises(FileNotFoundError):
        pilot.worker(root / "request.json", root / "out-2.json")
    assert calls["generate"] == ["no_skill", "a0"]


def test_worker_stops_on_an_unclosed_solver_call(worker_env):
    root, calls = worker_env
    pilot.worker(root / "request.json", root / "out-1.json")
    write_json(root / "run/predictions/x/call_intents/k.json", seal({"request": 1}))
    with pytest.raises(ValueError, match="Unclosed solver calls"):
        pilot.worker(root / "request.json", root / "out-2.json")
    assert calls["generate"] == ["no_skill", "a0"]


def test_a_call_is_closed_only_by_a_valid_sealed_terminal(tmp_path):
    request = {"position": 1, "system": "s", "user": "u"}
    key = digest(request)
    write_json(tmp_path / f"p/call_intents/{key}.json", seal(request))
    assert pilot._open_calls(tmp_path) == [str(tmp_path / f"p/call_intents/{key}.json")]  # no terminal
    (tmp_path / "p/calls").mkdir()
    (tmp_path / f"p/calls/{key}.json").write_text(json.dumps({"request": request, "receipt": {}}))  # unsealed
    assert pilot._open_calls(tmp_path)
    (tmp_path / f"p/calls/{key}.json").unlink()
    write_json(tmp_path / f"p/calls/{key}.json", seal({"request": {**request, "user": "v"}, "receipt": {}}))
    assert pilot._open_calls(tmp_path)  # a terminal for another request
    (tmp_path / f"p/calls/{key}.json").unlink()
    write_json(tmp_path / f"p/calls/{key}.json", seal({"request": request, "receipt": {}}))
    assert pilot._open_calls(tmp_path) == []
    write_json(tmp_path / "p/calls/orphan.json", seal({"request": request, "receipt": {}}))
    assert pilot._open_calls(tmp_path) == [str(tmp_path / "p/calls/orphan.json")]  # a terminal without intent
    write_json(tmp_path / "p/api/calls/cache.json", {"client": "cache"})  # client caches are not audited calls
    assert pilot._open_calls(tmp_path) == [str(tmp_path / "p/calls/orphan.json")]
    (tmp_path / "p/calls/orphan.json").unlink()
    for intent in (tmp_path / "p/call_intents").glob("*.json"):
        intent.unlink()
    (tmp_path / "p/call_intents").rmdir()  # a terminal whose whole intent directory is missing
    assert pilot._open_calls(tmp_path) == [str(tmp_path / f"p/calls/{key}.json")]


def test_a_forged_cached_rewrite_receipt_is_refused(pilot_run, tmp_path):
    root, _, _, _ = pilot_run
    pilot.run(root, tmp_path / "repo")
    terminal = next((root / "rewrites/a1/calls").glob("*.json"))

    def forge(value):
        request = {**value["receipt"]["request"], "user": "another prompt", "service": {"name": "other"}}
        value["receipt"] = {**value["receipt"], "request": request, "request_hash": digest(request)}
    reseal(terminal, forge)
    with pytest.raises(ValueError, match="Rewrite receipt does not match"):
        pilot.report(root)
    with pytest.raises(ValueError, match="Rewrite receipt does not match"):
        pilot.run(root, tmp_path / "repo")


@pytest.mark.parametrize("wrong", [{"ok": False, "error_type": "unexpected_response_model", "returned_model": "other"},
                                   {"returned_model": "other"},
                                   {"ok": False, "error_type": "inconsistent_stream_model", "returned_model": "glm-5.3"},
                                   {"ok": False, "error_type": "inconsistent_stream_model"}])
def test_a_wrong_model_rewrite_stops_the_pilot_and_keeps_its_receipt(pilot_run, tmp_path, wrong):
    root, api, solved, _ = pilot_run
    api.wrong_model = wrong
    with pytest.raises(ValueError, match="another model"):
        pilot.run(root, tmp_path / "repo")
    assert len(list((root / "rewrites/a1/calls").glob("*.json"))) == 1  # sealed and kept
    assert len(api.calls) == 1 and not (root / "rewrites/a2").exists() and not (root / "runs/b").exists()
    api.wrong_model = None
    with pytest.raises(ValueError, match="another model"):  # resume refuses the cached receipt too
        pilot.run(root, tmp_path / "repo")
    assert len(api.calls) == 1 and not {m for m, _ in solved} & {"a1", "a2"}


def test_the_paid_stage_waits_for_f_to_finish_both_methods(pilot_run, tmp_path):
    root, api, solved, _ = pilot_run
    (tmp_path / "f/gepa/final.json").unlink()
    with pytest.raises(ValueError, match="F has not finished gepa"):
        pilot.run(root, tmp_path / "repo")
    assert api.calls == [] and solved == [] and not (root / "requests").exists()


def test_a_filtered_receipt_passes_only_with_a_proven_model_over_a_complete_stream():
    proven = {"ok": False, "finish_reason": "content_filter", "returned_model": "glm-5.3", "stream_complete": True}
    assert not pilot._wrong_model(proven, "glm-5.3")
    assert pilot._wrong_model({**proven, "stream_complete": False}, "glm-5.3")
    assert pilot._wrong_model({**proven, "returned_model": None}, "glm-5.3")
    assert not pilot._wrong_model({"ok": False, "error_type": "network_error"}, "glm-5.3")  # ordinary delivery


def test_evidence_examples_take_turns_across_categories(monkeypatch):
    # Rules sort alphabetically, so a per-rule pass alone would let one category fill every example.
    monkeypatch.setattr(pilot, "_verdict", lambda probe, prediction: {"status": prediction["hint"], "reason": "broken"})
    probes, predictions = [], {}
    for category, rules in (("cipher", 6), ("operation", 6), ("puzzle", 1)):
        for rule in range(rules):
            probe = {"task_id": f"probe:{category}:r{rule}:0", "handler": f"{category}:r{rule}",
                     "public": {"question": f"Q {category} {rule}"}, "private": {"category": category}}
            probes.append(probe)
            predictions[("no_skill", probe["task_id"], 0)] = {"hint": "pass", "output": "[[1]]"}
            predictions[("a0", probe["task_id"], 0)] = {"hint": "fail", "output": "[[2]]"}
    evidence = pilot._evidence(probes, predictions, 1)
    assert [e["category"] for e in evidence["examples"]] == [
        "cipher", "operation", "puzzle", "cipher", "operation", "cipher", "operation", "cipher"]
    assert evidence["losses"] == 13 and evidence["counts"]["cipher"] == {"loss": 6}
