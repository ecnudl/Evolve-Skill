"""Controls for the frozen-Skill panel evaluation tool (learning v11 call path; engineering fixtures, no
method-effect claim): an external panel is refused when it touches the canonical split, Skill texts are bound by
hash, the arms are interleaved, every (task, Skill) position is solved once and the zero-call report reads the
paired contrasts."""
import hashlib
import json
from copy import deepcopy

import pytest

from scripts import run_active_evidence_panel_eval as panel_eval
from scripts import run_fivebench_g_stage as tool
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from skillopt.validator_pilot.api import digest
from tests.test_continual_learning_active_evidence import API, evaluate
from tests.test_continual_learning_domains import setup

GOOD = "Always return the requested constant."  # the fixture scorer passes a Skill that contains this phrase


def _study(tmp_path, monkeypatch, *, tasks=12):
    _, base, args = setup("searchqa")
    task = base["tasks"][0]
    fresh = {**base, "tasks": [{**deepcopy(task), "task_id": f"x{i}", "family_id": f"x{i}", "partition": "development"}
                               for i in range(tasks)]}
    model = args["model"]
    model["transport"]["stream_wall_seconds"] = 3600
    model["max_tokens"] = tool.BUDGET_V11["solver_max_tokens"]
    protocol = {"record_hash": "p" * 64, "root": str(tmp_path / "study"), "references": {}, "files": {},
                "model": model, "roles": {"searchqa": {"runtime": {}}},
                "learning_model_service": {"fixture": True}, "config": {"native_lock": str(tmp_path / "lock")}}
    split = seal({"version": tool.SPLIT_VERSION, "f_study_usage": {"searchqa": {"protocol_hash": "p" * 64}},
                  "splits": {"searchqa": {"train": [{"task_id": "t1", "family_id": "t1"}],
                                          "val": [{"task_id": "v1", "family_id": "v1"}], "test": [], "reserve": []}}})
    write_json(tmp_path / "split.json", split)
    (tmp_path / "items.json").write_text("[]", encoding="utf-8")
    monkeypatch.setattr(tool, "_study", lambda study: (tmp_path / "study", protocol))
    monkeypatch.setattr(tool, "_outside", lambda out, root, protocol, extra=(): None)
    monkeypatch.setattr(panel_eval, "_import_panel", lambda benchmark, items, revision: deepcopy(fresh))

    # the summary-only stage fixtures below have no learning directory: the evidence verification of a stage is
    # exercised on a really finished fixture stage in test_a_stage_skill_is_read_only_with_its_evidence_intact
    monkeypatch.setattr(panel_eval, "verified_stage", tool._completed_stage)
    return fresh, split


def _prepare(tmp_path, name, *skills, **extra):
    return panel_eval.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / name), str(tmp_path),
                              benchmark="searchqa", items=str(tmp_path / "items.json"), revision="r1", skills=skills,
                              **{"seed": 5, "chunk": 4, **extra})


def _stage(tmp_path, name, split, *, skill, families=("t1",), action="selected_update", seed=9):
    root = tmp_path / name
    stage = seal({"version": tool.VERSION, "protocol_hash": "p" * 64, "study": str(tmp_path / "study"),
                  "split_hash": split["record_hash"], "benchmark": "searchqa", "method": tool.ACTIVE_EVIDENCE,
                  "learning_version": "x", "train_families": list(families), "parent": "none", "seed": seed,
                  "arms": {"feedback": "scalar", "post_update": "none"}, "train_tasks": 1, "selection_tasks": 0})
    write_json(root / "stage.json", stage)
    write_json(root / "learned.json", seal({"stage_hash": stage["record_hash"], "status": "completed", "action": action,
                                            "skill": skill, "skill_sha256": hashlib.sha256(skill.encode()).hexdigest()}))
    return root


def test_prepare_binds_an_external_panel_and_the_skill_texts(tmp_path, monkeypatch):
    fresh, split = _study(tmp_path, monkeypatch)
    fixed = tmp_path / "generic.md"
    fixed.write_text("- Answer in the form the task asks for.\n", encoding="utf-8")
    learned = _stage(tmp_path, "learned", split, skill=GOOD)
    record = _prepare(tmp_path, "e1", "empty=none", f"generic=f:{fixed}", f"l1=g:{learned}")
    assert record["version"] == panel_eval.VERSION and record["tasks"] == 12 and record["deployment_authorized"] is False
    assert [(s["name"], s["rollout"], s["action"]) for s in record["skills"]] == [
        ("empty", 3000, "empty_skill"), ("generic", 3001, "fixed_text"), ("l1", 3002, "stage:selected_update")]
    assert record["skills"][1]["skill_sha256"] == hashlib.sha256(fixed.read_bytes()).hexdigest()
    assert record["skills"][2]["stage"] == "learned" and record["skills"][2]["seed"] == 9
    value = read_json(tmp_path / "e1/manifest.json", sealed=True)
    assert value["parent_skill"] == "" and value["active_evidence"]["challenge_families"] == []
    assert value["active_evidence"]["arms"] == panel_eval.ARMS and value["budget"]["max_metric_calls"] == 12 * 3 + 64
    out, loaded, _, panel, skills = panel_eval._load(str(tmp_path / "e1"))
    assert loaded == record and [name for name, _ in skills] == ["empty", "generic", "l1"] and skills[2][1] == GOOD
    # refusals: a panel that touches the canonical split, a Skill learned on a panel family, bad names and paths
    with pytest.raises(ValueError, match="unique"):
        _prepare(tmp_path, "r1", "a=none", "a=none")
    with pytest.raises(ValueError, match="absolute path"):
        _prepare(tmp_path, "r2", "g=f:generic.md")
    with pytest.raises(ValueError, match="trained on a family of this panel"):
        _prepare(tmp_path, "r3", f"l=g:{_stage(tmp_path, 'leaky', split, skill=GOOD, families=('x3',))}")
    with pytest.raises(ValueError, match="A Skill is given as"):
        _prepare(tmp_path, "r4", "Bad Name=none")
    touching = {**fresh, "tasks": [{**deepcopy(fresh["tasks"][0]), "task_id": "v1", "family_id": "v1"}]}
    monkeypatch.setattr(panel_eval, "_import_panel", lambda benchmark, items, revision: deepcopy(touching))
    with pytest.raises(ValueError, match="not an external sample"):
        _prepare(tmp_path, "r5", "empty=none")
    # a changed Skill record no longer loads
    texts = read_json(tmp_path / "e1/skills.json")
    texts["skills"][1]["skill"] += "x"
    (tmp_path / "e1/skills.json").write_text(json.dumps(texts), encoding="utf-8")
    with pytest.raises(ValueError):
        panel_eval._load(str(tmp_path / "e1"))


def test_the_schedule_interleaves_the_arms():
    hashes = [f"{i:02d}" for i in range(12)]
    plan = panel_eval.schedule(hashes, 3, seed=5, chunk=4)
    assert len(plan) == 9 and sorted(h for arm, tasks in plan if arm == 0 for h in tasks) == hashes
    # inside each chunk every arm runs once, and the arm that goes first rotates with the chunk number
    assert [arm for arm, _ in plan] == [0, 1, 2, 1, 2, 0, 2, 0, 1]
    assert all(plan[i][1] == plan[i + 1][1] == plan[i + 2][1] for i in (0, 3, 6))
    assert panel_eval.schedule(hashes, 3, seed=5, chunk=4) == plan != panel_eval.schedule(hashes, 3, seed=6, chunk=4)


def _three_histories(tmp_path, split, name="e1"):
    histories = [_stage(tmp_path, f"{name}h{i}", split, skill=text)
                 for i, text in enumerate((GOOD, GOOD + " Keep it short.", "Guidance without the phrase."))]
    return _prepare(tmp_path, name, "empty=none", *(f"l{i}=g:{h}" for i, h in enumerate(histories)))


def test_every_position_is_solved_once_and_the_report_reads_paired_contrasts(tmp_path, monkeypatch):
    _, split = _study(tmp_path, monkeypatch)
    record = _three_histories(tmp_path, split)
    out = tmp_path / "e1"
    with pytest.raises(ValueError, match="Invalid fixture callbacks"):
        panel_eval.run(str(out))
    api = API()
    result = panel_eval.run(str(out), fixture_api=api, fixture_evaluate=evaluate("candidate_wins"))
    assert result["status"] == "completed" and result["reason"] is None and result["evaluations_closed"] is True
    assert result["eval_hash"] == record["record_hash"] and result["usage_blocks_completion"] is False
    assert result["summary"]["empty"] == {"pass": 0, "fail": 12, "unknown": 0, "not_run": 0}
    assert result["summary"]["l0"]["pass"] == 12 and result["summary"]["l2"]["pass"] == 0
    rows = [read_json(p, sealed=True) for p in (out / "learning/evaluations").glob("*.json")]
    assert len(rows) == 12 * 4 and {r["request"]["rollout"] for r in rows} == {3000, 3001, 3002, 3003}
    assert {r["request"]["candidate_hash"] for r in rows if r["request"]["rollout"] == 3001} == {digest({"skill": GOOD})}
    assert not api.prompts["reflection"] and not api.prompts["verifier"]  # evaluation only: no learning call
    # a competing or later invocation returns the published result: nothing is solved again
    calls = sum(len(v) for v in api.prompts.values())
    assert panel_eval.run(str(out), fixture_api=api, fixture_evaluate=evaluate("candidate_wins")) == result
    assert sum(len(v) for v in api.prompts.values()) == calls
    value = panel_eval.report([str(out)], ["l0-empty", "learned-empty", "l2-empty"], ["learned=l0,l1,l2"])
    assert value["complete"] is True and value["arms"]["l1"] == {"pass": 12, "fail": 0, "unknown": 0, "not_run": 0}
    single = value["contrasts"]["l0-empty"]
    assert (single["known"], single["wins"], single["losses"], single["estimate"]) == (12, 12, 0, 1.0)
    group = value["contrasts"]["learned-empty"]
    assert abs(group["estimate"] - 2 / 3) < 1e-9 and group["per_history"] == [1.0, 1.0, 0.0]
    assert group["crossed_ci95"][0] <= group["history_ci95"][0] < 2 / 3 < group["history_ci95"][1] and "wins" not in group
    assert value["contrasts"]["l2-empty"]["estimate"] == 0.0
    with pytest.raises(ValueError, match="A contrast is a-b"):
        panel_eval.report([str(out)], ["l0-nobody"])
    with pytest.raises(ValueError, match="distinct evaluated arms"):
        panel_eval.report([str(out)], [], ["g=l0,l0"])
    # the retained evidence is bound to the result: a changed sealed evaluation is noticed by the report
    victim = sorted((out / "learning/evaluations").glob("*.json"))[0]
    victim.write_text(victim.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError):
        panel_eval.report([str(out)], ["l0-empty"])


def test_a_stopped_or_interrupted_run_leaves_a_reportable_pending_result(tmp_path, monkeypatch):
    from skillopt.continual_learning.ledger import LearningPending, Ledger

    _, split = _study(tmp_path, monkeypatch)

    def failing(kind, after):
        inner, seen = evaluate("candidate_wins"), []

        def execute(task, skill):
            seen.append(1)
            if len(seen) > after:
                raise kind("provider said something that must not be copied")
            return inner(task, skill)
        return execute

    # a ledger stop in the middle of a batch: what was solved (the health-barrier row included) stays reportable
    _three_histories(tmp_path, split, "p1")
    stopped = panel_eval.run(str(tmp_path / "p1"), fixture_api=API(), fixture_evaluate=failing(LearningPending, 5))
    assert stopped["status"] == "pending" and stopped["reason"].startswith("LearningPending")
    solved = sum(len(p["status"]) for p in stopped["positions"])
    assert 1 <= solved < 48 and sum(v["not_run"] for v in stopped["summary"].values()) == 48 - solved
    assert stopped["costs"]["solver_calls"] >= 0 and stopped["artifacts"] is not None
    value = panel_eval.report([str(tmp_path / "p1")], ["l0-empty"])
    assert value["complete"] is False and value["contrasts"]["l0-empty"]["reason"] == "insufficient_jointly_known_positions"
    # an ordinary exception: durable pending record, the exception type only
    _three_histories(tmp_path, split, "p2")
    crashed = panel_eval.run(str(tmp_path / "p2"), fixture_api=API(), fixture_evaluate=failing(RuntimeError, 0))
    assert crashed["status"] == "pending" and crashed["reason"] == "error:RuntimeError"
    assert "must not be copied" not in json.dumps(crashed)
    assert panel_eval.run(str(tmp_path / "p2"), fixture_api=API(), fixture_evaluate=evaluate("candidate_wins")) == crashed
    # an earlier attempt that never published a result: a terminal interrupted record, nothing is resumed
    record = _three_histories(tmp_path, split, "p3")
    write_json(tmp_path / "p3/learning/started.json", seal({"eval_hash": record["record_hash"]}))
    api = API()
    interrupted = panel_eval.run(str(tmp_path / "p3"), fixture_api=api, fixture_evaluate=evaluate("candidate_wins"))
    assert interrupted["status"] == "pending" and interrupted["reason"] == "interrupted_evaluation_no_automatic_resume"
    assert interrupted["eval_hash"] == record["record_hash"] and interrupted["costs"] is None
    assert not api.prompts["solver"] and interrupted["summary"]["empty"]["not_run"] == 12
    assert panel_eval.report([str(tmp_path / "p3")])["complete"] is False
    # incomplete usage accounting blocks completion, as in a learning stage
    _three_histories(tmp_path, split, "p4")
    monkeypatch.setattr(Ledger, "usage_blocks_completion", lambda self, costs: True)
    blocked = panel_eval.run(str(tmp_path / "p4"), fixture_api=API(), fixture_evaluate=evaluate("candidate_wins"))
    assert blocked["status"] == "pending" and blocked["reason"] == "usage_or_receipt_accounting_incomplete"
    assert blocked["summary"]["l0"]["pass"] == 12  # the positions themselves are all there


def test_paired_statistics_use_one_common_task_set_and_refuse_thin_data():
    def position(i, **status):
        return {"task_hash": f"t{i}", "family_id": f"f{i}", "status": status}

    rows = []
    for i in range(40):
        rows.append(position(i, b="pass" if i < 20 else "fail", l1="pass" if i < 30 else "fail",
                             l2="pass" if i < 26 else "fail", l3="pass" if i < 22 else "fail",
                             m1="pass" if i < 24 else "fail", m2="pass" if i < 24 else "fail",
                             m3="pass" if i < 24 else "fail"))
    rows[39]["status"]["l2"] = "unknown"  # leaves the common set of every contrast that involves l2
    group = panel_eval.paired(rows, ["l1", "l2", "l3"], "b")
    assert group["known"] == 39 and group["positions"] == 40
    assert abs(sum(group["per_history"]) / 3 - group["estimate"]) < 1e-12  # one common task set for all of them
    assert group["per_history"] == [10 / 39, 6 / 39, 2 / 39]
    low, high = group["crossed_ci95"]
    assert low < group["history_ci95"][0] and high > group["history_ci95"][1]
    assert low < group["task_ci95"][0] and high > group["task_ci95"][1]
    # two groups paired member by member (same seeds in the same order)
    both = panel_eval.paired(rows, ["l1", "l2", "l3"], ["m1", "m2", "m3"])
    assert both["per_history"] == [6 / 39, 2 / 39, -2 / 39] and "crossed_ci95" in both
    # groups of different size are not paired here (the report pairs groups by recorded seed first); two histories
    # give no history-level interval
    assert "per_history" not in panel_eval.paired(rows, ["l1", "l2", "l3"], ["m1", "m2"])
    # coverage is judged against the PLANNED positions, and the missing outcomes bound what the estimate could be
    assert panel_eval.paired(rows, "l1", "b", planned=80)["reason"] == "insufficient_jointly_known_positions"
    assert panel_eval.paired(rows, "l1", "b", planned=80)["missing_outcome_bounds"] == [(10 - 40) / 80, (10 + 40) / 80]
    bounds = group["missing_outcome_bounds"]  # one unknown solve of one of three histories: +- (1/3) / 40 at most
    assert bounds[0] <= group["estimate"] <= bounds[1] and bounds[1] - bounds[0] == pytest.approx(1 / 3 / 40)
    assert "crossed_ci95" not in panel_eval.paired(rows, ["l1", "l3"], "b")
    single = panel_eval.paired(rows, "l1", "b")
    assert (single["wins"], single["losses"], single["known"]) == (10, 0, 40) and "per_history" not in single
    # an entirely unknown history, or coverage below 90%, is reported as insufficient -- never a crash or a number
    for row in rows:
        row["status"]["l3"] = "unknown"
    thin = panel_eval.paired(rows, ["l1", "l2", "l3"], "b")
    assert thin["estimate"] is None and thin["reason"] == "insufficient_jointly_known_positions" and thin["known"] == 0


def test_the_connectivity_gate_only_delays_a_batch(tmp_path, monkeypatch):
    """The gate added after the connect-timeout outages of 2026-10-12: before each batch it waits for the network to
    be reachable again (a few consecutive successful probes) and gives up after its patience; it submits nothing and
    changes no call."""
    def gate_for(outcomes, **options):
        clock, slept = [0.0], []

        def sleep(seconds):
            slept.append(seconds)
            clock[0] += seconds

        probes = iter(outcomes)
        return panel_eval.network_gate(lambda: next(probes), sleep=sleep, clock=lambda: clock[0], **options), slept

    gate, slept = gate_for([True])
    gate()
    assert slept == [] and gate.state == {"waits": 0, "waited_seconds": 0.0, "failed_probes": 0}
    # down, then up-down-up-up-up: three consecutive successes are needed after a failure
    gate, slept = gate_for([False, True, False, True, True, True], quiet=3, interval=10.0)
    gate()
    assert len(slept) == 5 and gate.state == {"waits": 1, "waited_seconds": 50.0, "failed_probes": 1}
    gate, _ = gate_for([False] * 100, interval=10.0, patience=60.0)
    with pytest.raises(panel_eval.NetworkUnavailable):
        gate()
    assert gate.state["waits"] == 1 and gate.state["failed_probes"] >= 6
    # connectivity that comes back only AFTER the deadline does not release the batch
    gate, slept = gate_for([False] * 7 + [True] * 10, quiet=1, interval=10.0, patience=60.0)
    with pytest.raises(panel_eval.NetworkUnavailable):
        gate()
    assert sum(slept) == 70.0 and gate.state["waited_seconds"] == 70.0
    # the CONNECT reply: a COMPLETE header block whose status token is exactly 200
    def block(*pieces):
        data = bytearray(b"".join(pieces))
        sizes = []

        def receive(size):
            sizes.append(size)
            piece = bytes(data[:size])
            del data[:size]
            return piece

        return panel_eval.read_header_block(receive), sizes, bytes(data)

    reply, sizes, rest = block(b"HTTP/1.1 200 Connection established\r\n", b"Via: x\r\n\r\n", b"TLS-BYTES")
    assert panel_eval.status_line(reply) == b"HTTP/1.1 200 Connection established"
    assert set(sizes) == {1} and rest == b"TLS-BYTES"                 # nothing after the header block is consumed
    assert block(b"HTTP/1.1 200 OK\r\n")[0] is None                   # truncated: closed before the blank line
    assert panel_eval.read_header_block(lambda size: b"x" * size, limit=1024) is None  # oversized, never terminated
    assert panel_eval.status_line(None) is None
    established = panel_eval.connect_established
    assert established(b"HTTP/1.1 200 Connection established") and established(b"HTTP/1.0 200")
    for line in (None, b"HTTP/1.1 503 upstream said 200 once", b"HTTP/1.1 0200 odd", b"HTTP/1.1 2000 odd",
                 b"HTTP/2 200", b"garbage 200", b"200"):
        assert not established(line)
    # a gateway that answers 200 is not enough: the TLS handshake through the tunnel must complete
    import socket
    import threading

    def gateway(reply):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)

        def serve():
            connection, _ = server.accept()
            connection.recv(4096)
            connection.sendall(reply)
            connection.close()
            server.close()

        threading.Thread(target=serve, daemon=True).start()
        return "http://127.0.0.1:%d" % server.getsockname()[1]

    assert panel_eval.tunnel_probe(gateway(b"HTTP/1.1 200 Connection established\r\n\r\n"), "example.invalid", timeout=3) is False
    assert panel_eval.tunnel_probe(gateway(b"HTTP/1.1 503 Service Unavailable\r\n\r\n"), "example.invalid", timeout=3) is False

    class Handshake:
        def wrap_socket(self, connection, server_hostname=None):
            assert server_hostname == "example.invalid"
            import contextlib
            return contextlib.nullcontext()

    assert panel_eval.tunnel_probe(gateway(b"HTTP/1.1 200 Connection established\r\n\r\n"), "example.invalid", timeout=3,
                                   context=Handshake()) is True
    assert panel_eval.bounded(lambda: True, 1.0) is True and panel_eval.bounded(lambda: False, 1.0) is False
    import time as _time
    assert panel_eval.bounded(lambda: _time.sleep(2) or True, 0.1) is False  # a probe that hangs counts as down
    assert panel_eval.tunnel_probe("http://127.0.0.1:1", "example.invalid", timeout=1) is False
    with pytest.raises(ValueError, match="credential-free"):
        panel_eval.tunnel_probe("http://user:secret@127.0.0.1:1", "example.invalid", timeout=1)
    # in a run the gate is consulted once per submitted batch and an exhausted gate leaves a durable pending result
    _, split = _study(tmp_path, monkeypatch)
    record = _three_histories(tmp_path, split, "g1")
    out, _, value, panel, skills = panel_eval._load(str(tmp_path / "g1"))
    calls = []
    panel_eval.evaluate(value, panel, skills, out / "learning", seed=record["seed"], chunk=record["chunk"], api=API(),
                        fixture_evaluate=evaluate("candidate_wins"), gate=lambda: calls.append(1))
    assert len(calls) == 3 * 4 + 1  # 3 chunks x 4 arms, the first batch split by the health barrier
    done = panel_eval.collect(value, panel, skills, out / "learning", reason=None, network_gate_state={"waits": 0})
    assert done["status"] == "completed" and done["network_gate"] == {"waits": 0}

    def down():
        raise panel_eval.NetworkUnavailable("no connectivity")

    _three_histories(tmp_path, split, "g2")
    out2, record2, value2, panel2, skills2 = panel_eval._load(str(tmp_path / "g2"))
    with pytest.raises(panel_eval.NetworkUnavailable):
        panel_eval.evaluate(value2, panel2, skills2, out2 / "learning", seed=5, chunk=4, api=API(),
                            fixture_evaluate=evaluate("candidate_wins"), gate=down)
    assert not list((out2 / "learning/evaluations").glob("*.json"))  # nothing was submitted
    # through run(): a gate that gives up after some batches leaves a durable, correctly bound PENDING result with
    # the positions solved so far -- the only state after which the queue may repeat a block in a new directory
    record3 = _three_histories(tmp_path, split, "g3")
    seen = []

    def gives_up():
        seen.append(1)
        if len(seen) > 4:
            raise panel_eval.NetworkUnavailable("no connectivity")

    gives_up.state = {"waits": 1}
    pending = panel_eval.run(str(tmp_path / "g3"), fixture_api=API(), fixture_evaluate=evaluate("candidate_wins"),
                             fixture_gate=gives_up)
    assert pending["status"] == "pending" and pending["reason"] == "error:NetworkUnavailable"
    assert pending["eval_hash"] == record3["record_hash"] and pending["network_gate"] == {"waits": 1}
    assert 1 <= sum(len(p["status"]) for p in pending["positions"]) < 48
    assert panel_eval.status(str(tmp_path / "g3")) == (3, {"status": "pending", "reason": "error:NetworkUnavailable"})
    assert panel_eval.status(str(tmp_path / "g2"))[0] == 2  # started by hand above, no result: not repeatable
    done_run = _three_histories(tmp_path, split, "g4")
    assert panel_eval.run(str(tmp_path / "g4"), fixture_api=API(),
                          fixture_evaluate=evaluate("candidate_wins"))["eval_hash"] == done_run["record_hash"]
    assert panel_eval.status(str(tmp_path / "g4")) == (0, {"status": "completed", "reason": None})
    # a result that belongs to another evaluation is invalid, whatever it says
    (tmp_path / "g4/result.json").write_text((tmp_path / "g3/result.json").read_text(encoding="utf-8"), encoding="utf-8")
    assert panel_eval.status(str(tmp_path / "g4"))[0] == 2


def test_the_probe_log_is_quiet_only_when_fresh_ok_and_advancing():
    from scripts import connectivity_probe as probe

    now = 1_000_000.0
    good = ["%d ok 0.01" % (now - 10 * k) for k in range(12, 0, -1)]
    assert probe.quiet(good, 12, now) and probe.quiet(["0 fail 20.0"] + good, 12, now)
    assert not probe.quiet(good, 13, now)                                   # too few entries
    assert not probe.quiet(good[:5] + ["%d fail 20.00" % (now - 65)] + good[6:], 12, now)  # a failure in the window
    assert not probe.quiet(good, 12, now + 300)                             # a dead probe: old successes
    assert not probe.quiet(good[:-1] + [good[-2]], 12, now)                 # duplicated timestamp
    assert not probe.quiet(["%d ok 0.01" % (now - 5000 - k) for k in range(11, 0, -1)] + good[-1:], 12, now)  # old + 1 fresh
    assert not probe.quiet(["garbage"] + good[1:], 12, now) and not probe.quiet([], 1, now)
    assert not probe.quiet(["%d ok 0.01" % (now + 50)], 1, now)             # a timestamp from the future


def test_fixture_hooks_never_enter_a_natural_run():
    assert panel_eval.fixture_guard("fixture", API(), evaluate("equal")) is True
    assert panel_eval.fixture_guard("bigmodel", None, None) is False
    for hooks in ((API(), None), (None, evaluate("equal")), (API(), evaluate("equal"))):
        with pytest.raises(ValueError, match="Natural run cannot inject fixtures"):
            panel_eval.fixture_guard("bigmodel", *hooks)
    with pytest.raises(ValueError, match="Invalid fixture callbacks"):
        panel_eval.fixture_guard("fixture", API(), None)


def test_groups_are_paired_by_recorded_seed_and_coverage_counts_the_planned_tasks(tmp_path, monkeypatch):
    _, split = _study(tmp_path, monkeypatch)
    learned = [_stage(tmp_path, f"l{n}", split, skill=GOOD + f" v{n}", seed=n) for n in (1, 2, 3, 4)]
    other = [_stage(tmp_path, f"m{n}", split, skill=f"Plain guidance {n}.", seed=n) for n in (2, 3, 4, 5)]
    _prepare(tmp_path, "s1", "empty=none", *(f"l{n}=g:{d}" for n, d in zip((1, 2, 3, 4), learned)),
             *(f"m{n}=g:{d}" for n, d in zip((2, 3, 4, 5), other)))
    out = tmp_path / "s1"
    assert panel_eval.run(str(out), fixture_api=API(), fixture_evaluate=evaluate("candidate_wins"))["status"] == "completed"
    value = panel_eval.report([str(out)], ["le-lm", "le-empty"], ["le=l1,l2,l3,l4", "lm=m2,m3,m4,m5"])
    paired = value["contrasts"]["le-lm"]
    # equal-sized groups that miss different seeds are aligned on the shared seeds, never by list position
    assert paired["paired_seeds"] == [2, 3, 4] and paired["dropped_unpaired_histories"] == ["l1", "m5"]
    assert paired["histories"] == [3, 3] and paired["per_history"] == [1.0, 1.0, 1.0] and paired["estimate"] == 1.0
    assert value["contrasts"]["le-empty"]["histories"] == [4, 1]
    # the planned denominator: one of two planned halves is not enough, whatever it shows
    half = panel_eval.report([str(out)], ["le-empty"], ["le=l1,l2,l3,l4"], planned_tasks=24)
    assert half["planned_tasks"] == 24 and half["contrasts"]["le-empty"]["reason"] == "insufficient_jointly_known_positions"
    assert half["contrasts"]["le-empty"]["missing_outcome_bounds"] == [0.0, 1.0]
    with pytest.raises(ValueError, match="planned number of tasks"):
        panel_eval.report([str(out)], [], [], planned_tasks=5)


def test_the_report_refuses_runs_that_share_a_family(tmp_path, monkeypatch):
    fresh, split = _study(tmp_path, monkeypatch)
    _prepare(tmp_path, "a1", "empty=none", "good=f:" + str(_text(tmp_path)))
    # the same question imported from another file has another task hash but the same family: counted once only
    other = {**fresh, "tasks": [{**deepcopy(t), "task_id": "y" + t["task_id"]} for t in fresh["tasks"]]}
    monkeypatch.setattr(panel_eval, "_import_panel", lambda benchmark, items, revision: deepcopy(other))
    _prepare(tmp_path, "a2", "empty=none", "good=f:" + str(_text(tmp_path)))
    for name in ("a1", "a2"):
        assert panel_eval.run(str(tmp_path / name), fixture_api=API(),
                              fixture_evaluate=evaluate("candidate_wins"))["status"] == "completed"
    assert panel_eval.report([str(tmp_path / "a1")], ["good-empty"])["contrasts"]["good-empty"]["wins"] == 12
    with pytest.raises(ValueError, match="share a task or a family"):
        panel_eval.report([str(tmp_path / "a1"), str(tmp_path / "a2")], ["good-empty"])
    # runs under another model service (or model, runtime, sources) are never pooled
    disjoint = {**fresh, "tasks": [{**deepcopy(t), "task_id": "z" + t["task_id"], "family_id": "z" + t["family_id"]}
                                   for t in fresh["tasks"]]}
    monkeypatch.setattr(panel_eval, "_import_panel", lambda benchmark, items, revision: deepcopy(disjoint))
    _prepare(tmp_path, "a3", "empty=none", "good=f:" + str(_text(tmp_path)))
    tool._study(None)[1]["learning_model_service"] = {"fixture": "another service"}
    _prepare(tmp_path, "a4", "empty=none", "good=f:" + str(_text(tmp_path)))
    for name in ("a3", "a4"):
        panel_eval.run(str(tmp_path / name), fixture_api=API(), fixture_evaluate=evaluate("candidate_wins"))
    assert panel_eval.report([str(tmp_path / "a1"), str(tmp_path / "a3")], ["good-empty"])["contrasts"]["good-empty"]["wins"] == 24
    with pytest.raises(ValueError, match="differ in benchmark, model, service"):
        panel_eval.report([str(tmp_path / "a1"), str(tmp_path / "a4")], ["good-empty"])


def _text(tmp_path):
    path = tmp_path / "good.md"
    path.write_text(GOOD + "\n", encoding="utf-8")
    return path


def _dev_study(tmp_path, monkeypatch, *, tasks=20):
    """A fixture F study with a SearchQA development panel (the stage tool's and the generator's inputs)."""
    _, base, args = setup("searchqa")
    task = base["tasks"][0]
    dev = {**base, "tasks": [{**deepcopy(task), "task_id": str(i), "family_id": str(i)} for i in range(tasks)]}
    dev_path = tmp_path / "study" / "dev_panel.json"
    write_json(dev_path, dev)
    plan = seal({"config": {"panels": {"searchqa": str(dev_path)}}})
    write_json(tmp_path / "study/ref/plan.json", plan)
    model = args["model"]
    model["transport"]["stream_wall_seconds"] = 3600
    model["max_tokens"] = tool.BUDGET_V11["solver_max_tokens"]
    protocol = {"record_hash": "p" * 64, "root": str(tmp_path / "study"),
                "references": {"searchqa": {"root": str(tmp_path / "study/ref"), "plan_hash": plan["record_hash"]}},
                "files": {str(dev_path): hashlib.sha256(dev_path.read_bytes()).hexdigest()},
                "model": model, "roles": {"searchqa": {"runtime": {}}},
                "learning_model_service": {"fixture": True}, "config": {"native_lock": str(tmp_path / "lock")}}
    split = seal({"version": tool.SPLIT_VERSION, "f_study_usage": {"searchqa": {"protocol_hash": "p" * 64}},
                  "splits": {"searchqa": {"train": [{"task_id": t["task_id"], "family_id": t["family_id"]}
                                                    for t in dev["tasks"]], "val": []}}})
    write_json(tmp_path / "split.json", split)
    monkeypatch.setattr(tool, "_study", lambda study: (tmp_path / "study", protocol))
    monkeypatch.setattr(tool, "_outside", lambda out, root, protocol, extra=(): None)
    return dev, task, protocol, split


def test_a_stage_skill_is_read_only_with_its_evidence_intact(tmp_path, monkeypatch):
    """``name=g:<stage>``: a really finished ``scalar / none`` fixture stage (one pass/fail step adopted without
    selection) passes the full verification; a changed sealed evaluation of that stage is refused."""
    from skillopt.active_evidence.stage import run_stage

    _, _, protocol, split = _dev_study(tmp_path, monkeypatch)
    monkeypatch.setattr(tool, "TRAIN", {**tool.TRAIN, "searchqa": {"families": 8}})
    out = tmp_path / "stage"
    record = tool.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(out), str(tmp_path),
                          benchmark="searchqa", parent="none", val_source=None, seed=3, method=tool.ACTIVE_EVIDENCE,
                          learning_version="v11", arms={"feedback": "scalar", "post_update": "none"})
    value, panel = read_json(out / "manifest.json", sealed=True), read_json(out / "panel.json")
    result = run_stage(value, panel, out / "learning", fixture_api=API(), fixture_evaluate=evaluate("candidate_wins"))
    assert result["status"] == "completed" and result["decisions"] == ["accepted_without_challenge"]
    skill = result["candidate_skill"]
    assert skill != ""
    write_json(out / "learned.json", seal({"stage_hash": record["record_hash"], "status": "completed",
                                           "action": "selected_update", "skill": skill,
                                           "skill_sha256": hashlib.sha256(skill.encode()).hexdigest(),
                                           "learning_result_hash": result["record_hash"]}))
    stage, learned = panel_eval.verified_stage(protocol, out, split["record_hash"])
    assert learned["skill"] == skill and stage["arms"] == {"feedback": "scalar", "post_update": "none"}
    name, text, source = panel_eval.skill_spec(protocol, f"l1=g:{out}", split["record_hash"], {"fresh"})
    assert (name, text, source["action"], source["seed"]) == ("l1", skill, "stage:selected_update", 3)
    assert source["stage_tool_sha256"] == record["tool_sha256"] and source["parent"] == "none"
    with pytest.raises(ValueError, match="trained on a family of this panel"):
        panel_eval.skill_spec(protocol, f"l1=g:{out}", split["record_hash"], {record["train_families"][0]})
    victim = sorted((out / "learning/evaluations").glob("*.json"))[0]
    victim.write_text(victim.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="missing or changed"):
        panel_eval.verified_stage(protocol, out, split["record_hash"])


def test_the_zero_shot_initial_skill_is_written_once_from_the_public_task_card_only(tmp_path, monkeypatch):
    from scripts import generate_zero_shot_skill as zero

    assert zero.skill_text("```markdown\n- Be brief.\n```") == "- Be brief.\n" and zero.skill_text(" - A\n- B ") == "- A\n- B\n"
    _, task, _, _ = _dev_study(tmp_path, monkeypatch, tasks=6)
    record = zero.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / "z"), str(tmp_path),
                          benchmark="searchqa")
    assert record["user"].startswith("Public task card:") and "exact match" in record["user"]
    assert "seen no example task" in record["system"] and record["selection"].startswith("generated once")
    api = API()
    with pytest.raises(ValueError, match="Invalid fixture callbacks"):
        zero.run(str(tmp_path / "z"))
    result = zero.run(str(tmp_path / "z"), fixture_api=api)
    text = (tmp_path / "z/skill.md").read_text(encoding="utf-8")
    assert result["status"] == "completed" and result["reason"] is None
    assert text.strip() and result["skill_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert result["costs"]["reflection_calls"] == 1 and result["costs"]["solver_calls"] == 0
    # generated once: a later invocation returns the published record without another call
    assert zero.run(str(tmp_path / "z"), fixture_api=api) == result and len(api.prompts["reflection"]) == 1
    # a failed call is a durable pending record without a Skill file; a started directory is never regenerated
    zero.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / "z2"), str(tmp_path),
                 benchmark="searchqa")

    class Broken(API):
        def call(self, *args, **kwargs):
            raise RuntimeError("provider text")

    failed = zero.run(str(tmp_path / "z2"), fixture_api=Broken())
    assert failed["status"] == "pending" and failed["reason"] == "error:RuntimeError"
    assert not (tmp_path / "z2/skill.md").exists() and zero.run(str(tmp_path / "z2"), fixture_api=API()) == failed
    started = zero.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / "z3"), str(tmp_path),
                           benchmark="searchqa")
    write_json(tmp_path / "z3/learning/started.json", seal({"generation_hash": started["record_hash"]}))
    assert zero.run(str(tmp_path / "z3"), fixture_api=API())["reason"] == "interrupted_generation_no_automatic_resume"
    # only a COMPLETED generation's Skill may be consumed; incomplete usage accounting is not a completed generation
    path, sha = zero.check(str(tmp_path / "z"))
    assert path == tmp_path / "z/skill.md" and sha == result["skill_sha256"]
    for name in ("z2", "z3"):
        with pytest.raises(ValueError, match="No completed generation"):
            zero.check(str(tmp_path / name))
    from skillopt.continual_learning.ledger import Ledger

    zero.prepare(str(tmp_path / "study"), str(tmp_path / "split.json"), str(tmp_path / "z4"), str(tmp_path),
                 benchmark="searchqa")
    # (blocking only once the call exists: before it, the ledger itself would refuse to submit)
    monkeypatch.setattr(Ledger, "usage_blocks_completion", lambda self, costs: costs["logical_calls"] >= 1)
    gated = zero.run(str(tmp_path / "z4"), fixture_api=API())
    assert gated["status"] == "pending" and gated["reason"] == "usage_or_receipt_accounting_incomplete"
    assert not (tmp_path / "z4/skill.md").exists()
    # the one prompt is the fixed public card: no development task text reaches the generator
    assert api.prompts["reflection"] == [record["system"] + "\n" + record["user"]]
    assert task["public"]["question"] not in api.prompts["reflection"][0]
