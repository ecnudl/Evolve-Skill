"""ALF-only v2.6 engineer dispatch and stateful checks, with authored offline workers."""
from copy import deepcopy
from dataclasses import replace
import json

import pytest

from skillopt.execskill import engineer as e, manifest, profiles as p, replay, solver
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes import engineer_reply
from tests.execskill_zpc_fakes import tmp_path
from tests.test_execskill_v24_engineer import context, detail
from tests.test_execskill_v24_feedback_isolation import WireRoles
from tests.test_execskill_v24_routing_review import tracker_change
from tests.test_execskill_zpc_pipeline import offline


def assert_alf_evidence_contract(system, *, training):
    """Check the complete request instructions, including every inherited paragraph."""
    normalized = " ".join(system.split())
    for stale in ("each failure with its reference answer", "the reference answer)",
                  "already-visible run reference", "task's reference answer into code",
                  "actual notes, final answer", "receives step, action, and observation after"):
        assert stale not in normalized
    for fact in ("stored game trajectories", "observations, admissible commands", "actions, the notes the solver saw",
                 "outcome (won/lost, or unknown) and recorded steps", "no reference answer is supplied",
                 "No expert plan, hidden game state, reference answer, or solution trajectory is supplied",
                 "outcome summary (won/not won and steps)", "reference field says reference unavailable",
                 "receives exactly step, action, observation, and admissible_commands",
                 "observation and admissible_commands describe the environment AFTER that action"):
        assert fact in system
    c6c = system[system.index("C6c requires"):system.index("What your hooks receive.")]
    assert "facts, table, candidates, warnings or bindings" in c6c
    assert "non-empty discourage\nlist of admissible commands also counts as output" in c6c
    if training:
        assert "outcome summaries with the current package and with the candidate, and their pass shares" in system
        assert "Each outcome summary says won/not won and the number of steps" in system


@pytest.mark.parametrize("mode", ["train", "single"])
def test_alf_system_dispatch_uses_alf_views_and_v26_rules_without_zebra_instructions(mode):
    for purpose in ("propose", "repropose", "fix/1"):
        ctx, _ = context(configuration=p.ALFWORLD_V1, bench="alfworld", mode=mode)
        ctx.roles = WireRoles()
        e._ask(ctx, e.payload(ctx), purpose)
        system = ctx.roles.wire[0]["system"]
        assert system == (e.ENGINEER_SYSTEM_ALF_V1 if mode == "train" else e.ENGINEER_SYSTEM_SINGLE_ALF_V1)
        for fragment in ("16000", "rendered note text", "claims_fix: true", "C6c", "six rounds",
                         "alfworld-v1", "admissible_commands_at_reset", "task_text", "recent_history",
                         "trajectory_resolution", "PYTHONHASHSEED=0", "PYTHONHASHSEED=1", "(5 s)",
                         "State starts as None", "50 actions", "notes_coverage is not recorded"):
            assert fragment in system
        assert "training.procedures[].notes_coverage counts" not in system
        assert "ZebraLogic grid-mode addition" not in system and "view[\"question\"] is the raw puzzle" not in system
        assert_alf_evidence_contract(system, training=mode == "train")


@pytest.mark.parametrize("mode", ["train", "single"])
def test_real_alf_check_resolves_task_reference_before_hash_and_evaluates_later_stateful_note(mode):
    ctx, workers = context(configuration=p.ALFWORLD_V1, bench="alfworld", mode=mode)
    e._ask(ctx, e.payload(ctx), "propose")
    proposed = tracker_change(ctx)
    proposed.entry["replay_tests"][0]["trajectory"] = ctx.trajectories[0]["task_id"]
    advisory = deepcopy(proposed.entry["replay_tests"][0])
    advisory.update(id="advisory-later-note", claims_fix=False)
    proposed.entry["replay_tests"].append(advisory)
    report = e.check(proposed, ctx)
    assert report["passed"], report
    assert all(test["trajectory"] == ctx.trajectories[0]["cell"] for test in proposed.procedure.replay_tests)
    assert all(row["rule"] == "task_id" for row in proposed.trajectory_resolution)
    assert proposed.to_json()["procedure_sha256"] == proposed.procedure.sha256
    assert detail(report, "C5b") == {"claimed": 1, "failed": []}
    assert all(test["holds"] for test in report["lint"]["tests"])
    assert detail(report, "C6b")["fires_on"] > 0 and detail(report, "C6c")["nonempty"] > 0
    assert any(hook == "alf_after_step" for _, hook, _ in workers.calls)


@pytest.mark.parametrize("failure", ["C6b", "C6c"])
def test_alf_tracker_wrong_routing_view_or_no_notes_receives_executable_feedback(failure):
    ctx, _ = context(configuration=p.ALFWORLD_V1, bench="alfworld")
    ctx.roles = WireRoles()
    e._ask(ctx, e.payload(ctx), "propose")
    proposed = tracker_change(ctx, claims=False, emits=failure != "C6c")
    if failure == "C6b":
        proposed.source = proposed.source.replace('"task_text" in view', '"recent_history" in view')
    report = e.check(proposed, ctx)
    assert report["failed"] == failure
    e._fix(ctx, proposed, report, attempt=1)
    wire = next(json.loads(row["user"]) for row in ctx.roles.wire if json.loads(row["user"])["request"] == "fix")
    assert wire["failed"]["check"] == failure
    assert set(wire["hook_views"]["routing_view"]) == set(p.ALFWORLD_ROUTING_VIEW)
    assert set(wire["hook_views"]["hook_view"]) == set(e.ALFWORLD_STEP_VIEW_KEYS)
    if failure == "C6b":
        assert wire["failed"]["detail"]["fires_on"] == 0
    else:
        assert wire["failed"]["detail"]["nonempty"] == 0


def test_failed_alf_note_claim_shows_the_rendered_later_step_and_invalid_reference_help():
    ctx, _ = context(configuration=p.ALFWORLD_V1, bench="alfworld")
    ctx = replace(ctx, current=list(ctx.trajectories))
    e._ask(ctx, e.payload(ctx), "propose")
    proposed = tracker_change(ctx)
    proposed.entry["replay_tests"][0]["property"]["value"] = "Missing authored note fragment"
    report = e.check(proposed, ctx)
    assert report["failed"] == "C5b"
    failed = detail(report, "C5b")["failed"][0]
    assert "Earlier public observations are retained." in failed["rendered_note"]
    invalid = tracker_change(ctx)
    invalid.entry["replay_tests"][0]["trajectory"] = "outside-the-run"
    failed = detail(e.check(invalid, ctx), "C5b")["failed"][0]
    assert failed["reason"] == "trajectory_not_in_scope"
    assert failed["valid_trajectories"] == [{"trajectory": ctx.trajectories[0]["cell"],
                                            "task_id": ctx.trajectories[0]["task_id"]}]


@pytest.mark.parametrize("mode", ["train", "single"])
def test_actual_proposal_reproposal_and_fix_requests_consistently_describe_alf_evidence(mode):
    ctx, _ = context(configuration=p.ALFWORLD_V1, bench="alfworld", mode=mode)
    if mode == "train":
        ctx = replace(ctx, current=list(ctx.trajectories))
    failed, corrected = tracker_change(ctx), tracker_change(ctx)
    failed.entry["replay_tests"][0]["property"]["value"] = "Authored absent note fragment"
    ctx.roles = WireRoles(([engineer_reply({"findings": []}, [])] if mode == "train" else [])
        + ["An authored malformed proposal", *[
        engineer_reply({"changes": [change.entry]}, [change.source]) for change in (failed, corrected)]])
    candidate, record = (e.run_train if mode == "train" else e.run)(ctx)
    assert candidate is not None
    assert [row["parsed"] for row in record["proposals"]] == [False, True]
    assert [row["failed"] for row in record["changes"][0]["attempts"]] == ["C5b", None]
    wire = [row for row in ctx.roles.wire if row["label"].startswith("engineer/")]
    assert len(wire) == 3
    assert wire[0]["label"].endswith("/propose")
    assert wire[1]["label"].endswith("/repropose")
    assert "/fix/" in wire[2]["label"]
    prompt = e.ENGINEER_SYSTEM_ALF_V1 if mode == "train" else e.ENGINEER_SYSTEM_SINGLE_ALF_V1
    assert record["prompt_sha256"] == digest(prompt)
    for row in wire:
        assert row["system"] == prompt
        assert_alf_evidence_contract(row["system"], training=mode == "train")
    proposed = json.loads(wire[0]["user"])
    assert proposed["trajectories"] and all("reference" not in row for row in proposed["trajectories"])
    assert proposed["trajectories"][0]["token"] == "fail"
    assert proposed["trajectories"][0]["alfworld_steps"]
    fixed = json.loads(wire[-1]["user"])
    assert fixed["request"] == "fix" and fixed["failed"]["check"] == "C5b"
    assert "rendered_note" in fixed["failed"]["detail"]["failed"][0]


@pytest.mark.parametrize("commands,accepted", [
    ('view["admissible_commands"][:1]', True), ('["fly away"]', False), ('[]', False),
], ids=["admissible-discourage-only", "inadmissible", "empty"])
def test_c6c_discourage_only_contract_matches_real_screened_replay(commands, accepted):
    ctx, workers = context(configuration=p.ALFWORLD_V1, bench="alfworld")
    proposal = tracker_change(ctx, claims=False)
    proposal.source = (proposal.source[:proposal.source.index("def alf_before_step")]
        + 'def alf_before_step(view, state):\n    return {"fields": {}, "discourage": ' + commands + '}\n'
        + proposal.source[proposal.source.index("def alf_after_step"):])
    report = e.check(proposal, ctx)
    assert report["passed"] is accepted, report
    assert detail(report, "C6c")["nonempty"] == int(accepted)
    if not accepted:
        assert report["failed"] == "C6c"
    else:
        entry = replay.inputs_of(ctx.trajectories[0])
        with workers(replay.solo(proposal.procedure)) as worker:
            outcome = replay.replay(worker, proposal.procedure, entry)
        assert outcome.notes and all(note["text"].startswith(p.NOT_RECOMMENDED_PREFIX) for note in outcome.notes)


def test_after_step_event_has_post_action_observation_and_commands_in_live_and_replay(tmp_path, monkeypatch):
    from tests.execskill_fakes_env import FakeSandbox, Script, alf_sessions
    from tests.test_execskill_solver import ALF, ALF_RUNTIMES, alf_public, package, plan_replies
    sessions = alf_sessions(monkeypatch)
    public, game = alf_public(tmp_path)
    worker = FakeSandbox({"fx-alf": {"alf_before_step": lambda view, state: {"fields": {}, "discourage": []},
                                    "alf_after_step": lambda event, state: {"n": (state or {}).get("n", 0) + 1}}})
    calls = Script(plan_replies(game))
    solved = solver.solve("alfworld", public, "Authored card", package(ALF), calls,
                          runtime=ALF_RUNTIMES[1], worker=worker)
    assert solved["output"]["won"] is True
    events = [args[0] for _, args in worker.called("alf_after_step")]
    for index, event in enumerate(events):
        assert set(event) == {"step", "action", "observation", "admissible_commands"}
        assert event["step"] == index and event["action"] == sessions[0].actions[index]
        assert event["observation"] == solved["trace"][index]["post_observation"]
        if index + 1 < len(calls.requests):
            following = json.loads(calls.requests[index + 1][1])
            assert event["observation"] == following["observation"]
            assert event["admissible_commands"] == following["admissible_commands"]
    ctx, workers = context(configuration=p.ALFWORLD_V1, bench="alfworld")
    row = deepcopy(ctx.trajectories[0])
    following = json.loads(row["calls"][1]["user"])
    following["admissible_commands"] = ["look", "inventory"]
    row["calls"][1]["user"] = json.dumps(following)
    row = p.record("trajectory", row["evidence"], {key: value for key, value in row.items()
        if key not in ("version", "evidence", p.RECORD_HASH)})
    ctx = replace(ctx, trajectories=[row])
    assert e.check(tracker_change(ctx), ctx)["passed"]
    replay_events = [args[0] for _, hook, args in workers.calls if hook == "alf_after_step"]
    assert replay_events and replay_events[0] == {
        "step": 0, "action": row["alfworld_steps"][0]["action"], "observation": following["observation"],
        "admissible_commands": ["look", "inventory"]}
    assert replay_events[0]["observation"] != json.loads(row["calls"][0]["user"])["observation"]


def test_fixed_alf_prompt_hashes_are_bound_by_manifest():
    assert e.ENGINEER_PROMPT_ALF_V1_SHA256 == "4abdd3ef44c5d8505279e3a9ab5e14d4a31a0527219f41070a0a67160aa6b577"
    assert e.ENGINEER_PROMPT_SINGLE_ALF_V1_SHA256 == "964b8451bfe14bd416512c55205d0b538a1c8c01ca468615c1afc06d018310ef"
    assert manifest.prompt_sha(p.ALFWORLD_V1)["v2"]["engineer"] == digest(e.ENGINEER_SYSTEM_ALF_V1)
    assert manifest.prompt_sha(p.ALFWORLD_V1)["engineer"] == digest(e.ENGINEER_SYSTEM_SINGLE_ALF_V1)
