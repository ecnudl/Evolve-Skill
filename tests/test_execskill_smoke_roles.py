"""The smoke's S3, the method roles (registration §10 S3 row, §7.2, §21 owner rule (b); implementation plan §10 step
7; ``smoke_roles``, notes/C7d.md; registrar addendum 2026-10-22 14:3x), on a temporary smoke root with zero network:
S3's own run unit (the S4 mini-step's run sub-step only, ``smoke_roles.own_run``) runs on the plan-§7 fakes
(``smoke.run_stage``'s rehearsal backends) -- no S2 or S4 unit exists -- then the roles run on ``S3Rehearsal``
(tests/execskill_fakes_s3.py) -- the scripted GLM-5.3 gateway behind the real frozen client, FakeWikipedia,
SympyDocker running the real sandbox worker with a stand-in sympy so the registrar's LiveMath checker source runs
unchanged. Engineering fixtures only."""
from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import asdict

import pytest

from skillopt.coevo5 import leakage
from skillopt.coevo5.budget import Budget
from skillopt.coevo5.ledger import attempt_bound, request_bytes
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import budgets, fixtures, manifest, protocol, research, smoke, smoke_roles, trajectories
from skillopt.execskill.generators import families, livemath
from skillopt.execskill.registry import Registry
from skillopt.execskill.sandbox import client as sandbox
from skillopt.execskill.sandbox.client import Worker
from skillopt.execskill.supply import routing_view as alf_routing_view
from skillopt.validator_pilot.api import digest
from tests import execskill_fakes_research as fake_research
from tests.execskill_fakes import fake_config, undelivered
from tests.execskill_fakes_docker import FakeDocker
from tests.execskill_fakes_env import FakeAlfEnv
from tests.execskill_fakes_s3 import PARAMS, TRUTHS, S3Rehearsal, S3Script, SympyDocker, wrong_model_first
from tests.fixtures.execskill.items import alfworld_games, alfworld_items, searchqa_items
from tests.test_execskill_manifest import MEASURED, fake_environment, given
from tests.test_execskill_replay import TEST_LIMITS



def _alfworld(root):
    out = []
    for game, item in zip(alfworld_games(), alfworld_items(root)):
        observations, _, infos = FakeAlfEnv(game).reset()
        view = alf_routing_view(observations[0], infos[0]["admissible_commands"])
        out.append({**item, "room": game["room"],
                    "public": {**item["public"], "routing_view": view, "routing_view_sha256": digest(view)}})
    return out


def _write(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, items)
    return str(path)


@pytest.fixture(scope="module")
def smoked(tmp_path_factory):
    """A smoke root whose S3 run unit is complete (``own_run``, fake mode) and nothing else ran; ``tags``: the unit
    tag of the worker factory every LiveMath checker was made from meanwhile (ticket C7d-2)."""
    tmp = tmp_path_factory.mktemp("s3")
    patch = pytest.MonkeyPatch()
    tags, made = [], livemath.WorkerChecker.__init__

    def recorded(self, workers):
        tags.append(getattr(workers, "keywords", {}).get("tag"))
        made(self, workers)

    patch.setattr(livemath.WorkerChecker, "__init__", recorded)
    patch.setattr(protocol, "SLOT_ROOT", str(tmp / "slots"))
    patch.setattr(protocol, "HISTORY_ROOT", str(tmp / "history"))
    root = tmp / "smoke"
    fixtures.make_fixtures(tmp / "fixtures")
    sets = {bench: str(tmp / "fixtures" / (bench + ".json")) for bench in ("officeqa", "livemath",
                                                                           "spreadsheetbench")}
    sets["searchqa"] = _write(tmp / "items" / "searchqa.json", searchqa_items(280))
    sets["alfworld"] = _write(tmp / "items" / "alfworld.json", _alfworld(tmp / "games"))
    tested = tmp / "s0" / smoke.SELFTEST
    write_json(tested, protocol.record("sandbox-selftest", "smoke", {
        "escape_rows": {row: True for row in smoke.ESCAPE_ROWS}, "escape_probe_sha256": "0" * 64,
        "worker_sha256": "1" * 64, "image": sandbox.IMAGE,
        "limits": {k: asdict(v) for k, v in sorted(sandbox.LIMITS.items())},
        "measured": {**{k: MEASURED[k] for k in ("vsz_kib", "rss_kib", "view_bytes_p99")}, "start_seconds": 2.6,
                     "views": 15}, "passed": True}))
    spec = smoke.make(root, items=sets, control_cells=["fx-drill-1"], noise_anchor={"searchqa": 0.21, "alfworld": 0.3},
                      selftest=str(tested), environment_found=fake_environment())
    elucid, glm = fake_config(tmp, protocol.CHAINS["D"]), fake_config(tmp, protocol.CHAINS["G"])
    archive = fake_research.archive_fixture(tmp / "archive")
    values = {**given(tmp), "root": str(root),
              "clients": {"solver": {"D": manifest.solver_block("D", env_path=elucid["env_path"], branch="E"),
                                     "G": manifest.solver_block("G", env_path=glm["repo"])},
                          "roles": dict(manifest.ROLES)},
              "data": {"research": {"archive": str(archive), "index_sha256": research.Archive(archive).index_sha256}}}
    path = tmp / "smoke-manifest.json"
    manifest.make(path, evidence=manifest.SMOKE_EVIDENCE, environment_found=fake_environment(), measured=MEASURED,
                  **values)
    m = manifest.load(path, verify=False)
    first = smoke_roles.own_run(spec, m, path, fake=True)
    assert first["identity"]["unit"] == "smoke/s1-searchqa/run" and (smoke_roles.run_root(spec) / "unit.json").exists()
    yield {"spec": spec, "m": m, "root": root, "path": path, "tmp": tmp, "elucid": elucid["env_path"],
           "glm": glm["repo"], "run": first, "tags": tags}
    patch.undo()


def ledger(smoked):
    return Budget(budgets.ledger_root(smoked["root"], budgets.SMOKE))


def spent(smoked):
    snapshot = ledger(smoked).snapshot()
    return snapshot[smoke_roles.METER_SCOPE]["settled"] if smoke_roles.METER_SCOPE in snapshot else 0


def s3_unit(smoked, name, **options):
    return smoke_roles.unit(smoked["spec"], smoked["m"], smoked["path"], fake=True, name=name, **options)


def attempt_dir(smoked, name, n=1):
    return smoke_roles.unit_root(smoked["spec"], name) / ("attempt-%d" % n)


# ------------------------------------------------------------------------------------------- the stage record
def test_run_stage_s3_runs_every_role_and_records_the_stage_once(smoked):
    before = spent(smoked)
    value = smoke.run_stage(smoked["root"] / smoke.SPEC, smoked["path"], "S3", fake=True)
    result = value["result"]
    assert value["stage"] == "S3" and result["rows"] == {row: True for row in smoke.S3_ROWS}
    assert result["passed"] is True and result["unit"] == "smoke/S3/roles"
    glm = result["glm"]
    assert glm["first"]["confirmed"] and glm["first"]["label"] == "leak/smoke/S3/roles/fx-note"
    assert glm["before"] == before and glm["total"] == before + glm["spent"] <= smoke_roles.S3_GLM_CAP
    assert glm["spent"] == spent(smoked) - before > 0 and glm["refused"] is None
    assert set(glm["by_role"]) == {"leakage", "engineer", "examiner", "examiner_research", "describer"}
    unit = read_json(smoke_roles.unit_root(smoked["spec"]) / "unit.json")
    assert unit[protocol.RECORD_HASH] == result["unit_sha256"]
    calls = unit["result"]["calls"]
    assert sum(c["charged"] for c in calls) == glm["spent"] and all(c["sends"] == 1 for c in calls)
    stored = read_json(smoked["root"] / smoke.STAGES_DIR / "S3.json")
    assert stored[protocol.RECORD_HASH] == value[protocol.RECORD_HASH]
    assert smoke.summary(smoked["spec"])["stages"]["S3"] == "pass"
    with pytest.raises(ValueError, match="Stage S3 is recorded"):  # write-once: run_stage refuses a second run
        smoke.run_stage(smoked["root"] / smoke.SPEC, smoked["path"], "S3", fake=True)
    with pytest.raises(ValueError, match="Immutable artifact differs"):
        smoke.record(smoked["spec"], "S3", {**result, "passed": False})
    again = smoke_roles.unit(smoked["spec"], smoked["m"], smoked["path"], fake=True)  # read back, nothing sent
    assert again[protocol.RECORD_HASH] == unit[protocol.RECORD_HASH] and spent(smoked) == before + glm["spent"]


def test_the_six_pieces_run_in_order_through_the_sandbox(smoked):
    rehearsal = S3Rehearsal(smoked["tmp"] / "r-order")
    value = s3_unit(smoked, "t-order", rehearsal=rehearsal)
    result, roles = value["result"], rehearsal.script.roles()
    assert roles[0] == "leakage" and roles[-1] == "describer"
    assert roles.index("engineer") < roles.index("detector") < roles.index("query") < roles.index("pick") \
        < roles.index("conclude") < roles.index("generator")
    assert {body["model"] for body in rehearsal.glm.requests} == {protocol.ROLE_MODEL}
    pieces = result["pieces"]
    # 2: the engineer's change ran through the fixed checks C1-C9 on S3's own run unit's trajectories
    engineer_record = pieces["engineer"]["record"]
    checks = [c["check"] for c in engineer_record["changes"][0]["attempts"][0]["checks"]]
    assert checks[:2] == ["C1", "C2"] and checks[-1] == "C9" and pieces["engineer"]["ran"]
    assert engineer_record["label"] == "smoke/S3/t-order" and engineer_record["calls"] == 1
    # 3: one detector written, sealed before the hold half, validated in the sandbox on the hold half
    detector = pieces["detector"]
    assert detector["split"]["status"] == "ok" and detector["validation"]["status"] == "ok"
    assert detector["validation"]["candidates"][0]["deterministic"] is True
    assert read_json(attempt_dir(smoked, "t-order") / "detectors" / "candidates.json")["candidates_sha256"] \
        == detector["validation"]["candidates_sha256"]
    # 4: research first (archived write-once, verbatim, <= 8 calls, the gateway), then generation and the checker
    searched, generated = pieces["research"], pieces["generator"]
    found = searched["request"]
    assert found["status"] == "found" and found["calls"] == 3 <= protocol.RESEARCH_MAX_CALLS
    assert searched["provenance"]["archived"] and searched["provenance"]["verbatim"]
    assert searched["gateway"] == protocol.GATEWAY and searched["trust_env"] is False
    store = attempt_dir(smoked, "t-order") / "research" / "sources"
    page = read_json(store / (found["archive"] + ".json"))
    assert digest(page) == found["archive"] and page["title"] == "Derivative"
    assert [r[2].get("action") for r in rehearsal.wikipedia.requests] == ["query", "parse"]
    assert generated["ran"] and len(generated["kept"]) == len(PARAMS) >= smoke_roles.MIN_CHECKED
    assert [entry["exact"] for entry in generated["checker"]] == TRUTHS and generated["solved"] == len(PARAMS)
    items = read_json(attempt_dir(smoked, "t-order") / "generated-G_self.json")
    assert [item["private"]["truth"]["exact"] for item in items] == TRUTHS
    assert all(item["public"]["question"].startswith('Background (quoted from English Wikipedia, "Derivative")')
               for item in items)
    # 5: the describer on the engineer's surviving procedure (one call), its note lengths replayed
    assert pieces["describer"]["origin"] == "engineer" and pieces["describer"]["record"]["text"]
    assert result["ran"] == {row: True for row in smoke.S3_ROWS}
    assert not rehearsal.docker.containers  # every container removed, the unit drained


def test_s3_runs_its_own_run_unit_first_and_needs_no_other_stage(smoked, monkeypatch):
    """Registrar addendum 14:3x: S3's own run unit -- the S4 mini-step's run sub-step only, under <root>/units/S3,
    after one confirmation cell, charged to smoke:solver, consuming in its own smoke-namespace registry -- whose run
    trajectories the engineer admits; no S2 or S4 unit exists. A completed run unit is read back with nothing sent;
    the roles refuse before anything is sent while it is missing."""
    spec, root = smoked["spec"], smoked["root"]
    base = root / smoke.UNITS_DIR
    assert not (base / "S2").exists() and not (base / smoke.S4_DIR).exists()
    value = smoked["run"]
    assert value["identity"] == {"unit": "smoke/s1-searchqa/run", "chain": budgets.SMOKE, "k": 1, "bench": "searchqa",
                                 "parent": value["identity"]["parent"]}
    assert value["result"]["items"] == protocol.S4_SLICES["run"] and value["result"]["cells"] == protocol.S4_SLICES[
        "run"] * protocol.SLICES["searchqa"]["run"][1]
    assert sorted(p.name for p in (base / "S3").glob("confirm-*")) == ["confirm-1"]  # one confirmation cell first
    entries = Registry(base / "S3" / smoke.DRILL_HISTORY, evidence="smoke").entries(budgets.SMOKE, "searchqa")
    assert len(entries) == protocol.S4_SLICES["run"] and {e["state"] for e in entries.values()} == {"decided"}
    assert {e["purpose"] for e in entries.values()} == {"smoke"}
    stored = trajectories.load_run(smoke_roles.run_root(spec))
    assert {t["unit"] for t in stored} == {"smoke/s1-searchqa/run"} and {t["arm_kind"] for t in stored} == {"parent"}
    snapshot = ledger(smoked).snapshot()
    assert snapshot[budgets.SMOKE + ":solver"]["settled"] > 0 and snapshot[budgets.SMOKE + ":solver"]["open"] == 0
    # ticket C7d-2: services_of's LiveMath checker followed the run unit's tag-bound workers
    assert sandbox.unit_tag(budgets.SMOKE, "smoke/s1-searchqa/run") in smoked["tags"]
    settled = snapshot[budgets.SMOKE + ":solver"]["settled"]
    again = smoke_roles.own_run(spec, smoked["m"], smoked["path"], fake=True)  # read back: nothing sent
    assert again[protocol.RECORD_HASH] == value[protocol.RECORD_HASH]
    assert ledger(smoked).snapshot()[budgets.SMOKE + ":solver"]["settled"] == settled
    assert sorted(p.name for p in (base / "S3").glob("confirm-*")) == ["confirm-1"]
    monkeypatch.setattr(smoke_roles, "run_root", lambda spec: root / "missing")
    with pytest.raises(ValueError, match="run it first"):
        s3_unit(smoked, "t-missing")
    assert not smoke_roles.unit_root(spec, "t-missing").exists()


# ------------------------------------------------------------------------------------------------ the guards
def test_the_first_reply_is_confirmed_before_any_further_call(smoked):
    for name, first in (("t-model", wrong_model_first()), ("t-undelivered", undelivered("http_400"))):
        rehearsal = S3Rehearsal(smoked["tmp"] / ("r-" + name), script=S3Script(first=first))
        before = spent(smoked)
        value = s3_unit(smoked, name, rehearsal=rehearsal)
        assert value["complete"] is False and value["stopped"] == "first_call_not_confirmed"
        assert rehearsal.script.roles() == ["leakage"] and len(rehearsal.glm.requests) == 1  # no resend, nothing else
        state = read_json(attempt_dir(smoked, name) / "glm.json")
        assert state["first"]["confirmed"] is False and state["sends"] == 1
        assert spent(smoked) - before == state["spent"]
        status = read_json(attempt_dir(smoked, name) / "status.json")
        assert status["status"] == "paused" and status["kind"] == "first_call_not_confirmed"


def test_the_glm_cap_refuses_a_call_before_anything_is_reserved(smoked):
    rule = smoke_roles.rule_text()
    confirm = attempt_bound(request_bytes(leakage.ADJUDICATE_SYSTEM, json.dumps({"rule": rule}, ensure_ascii=False,
                                                                                sort_keys=True)),
                            protocol.ROLE_MAX_TOKENS)
    before = spent(smoked)
    rehearsal = S3Rehearsal(smoked["tmp"] / "r-cap")
    value = s3_unit(smoked, "t-cap", rehearsal=rehearsal, cap=before + confirm + 1_000)
    assert value["complete"] is False and value["stopped"] == "budget"
    assert rehearsal.script.roles() == ["leakage"]  # the engineer's request was never sent
    state = read_json(attempt_dir(smoked, "t-cap") / "glm.json")
    assert state["refused"]["label"] == "engineer/smoke/S3/t-cap/propose"
    assert state["refused"]["total"] + state["refused"]["attempt_bound"] > state["cap"] >= state["total"]
    snapshot = ledger(smoked).snapshot()
    assert snapshot[smoke_roles.METER_SCOPE]["open"] == 0 and snapshot[budgets.SMOKE + ":glm"]["open"] == 0
    assert spent(smoked) == before + state["spent"] and "halted" not in snapshot


def test_credentials_and_the_money_guard(smoked):
    spec, m, path = smoked["spec"], smoked["m"], smoked["path"]
    with pytest.raises(ValueError, match="names the elucid env path"):
        smoke.run_stage(smoked["root"] / smoke.SPEC, path, "S3")
    with pytest.raises(ValueError, match="A rehearsal names no credential"):
        smoke_roles.unit(spec, m, path, fake=True, roles_repo=smoked["glm"], name="t-cred")
    with pytest.raises(ValueError, match="A rehearsal names no credential"):
        smoke_roles.unit(spec, m, path, fake=True, env_path=smoked["elucid"], name="t-cred")
    with pytest.raises(ValueError, match="A rehearsal names no credential"):  # the run unit too (smoke._backends)
        smoke_roles.own_run(spec, m, path, fake=True, env_path=smoked["elucid"])
    with pytest.raises(ValueError, match="not the smoke manifest's"):  # roles_repo must be the G solver block's
        smoke_roles.unit(spec, m, path, env_path=smoked["elucid"], roles_repo=str(smoked["tmp"]), name="t-cred")
    with pytest.raises(ValueError, match="A real S3 runs on no fake"):
        smoke_roles.unit(spec, m, path, env_path=smoked["elucid"], roles_repo=smoked["glm"], name="t-cred",
                         rehearsal=S3Rehearsal(smoked["tmp"] / "r-cred"))
    assert not smoke_roles.unit_root(spec, "t-cred").exists()


# --------------------------------------------------------------------------------------------- the judge
def test_a_piece_that_does_not_run_through_fails_its_row(smoked):
    rehearsal = S3Rehearsal(smoked["tmp"] / "r-nodet", script=S3Script(detectors=False))
    judged = smoke_roles.judged(s3_unit(smoked, "t-nodet", rehearsal=rehearsal))
    assert judged["passed"] is False and judged["rows"] == {row: row != "detector" for row in smoke.S3_ROWS}
    rehearsal = S3Rehearsal(smoked["tmp"] / "r-none", script=S3Script(found=False))
    value = s3_unit(smoked, "t-none", rehearsal=rehearsal)
    judged = smoke_roles.judged(value)
    assert judged["rows"] == {row: row != "generator_research" for row in smoke.S3_ROWS}
    assert "generator" not in rehearsal.script.roles()  # nothing found: no generation, no fallback
    assert value["result"]["pieces"]["generator"]["reason"] == "no_research_finding"
    assert smoke.s3_roles({row: True for row in smoke.S3_ROWS})["passed"]
    assert not smoke.s3_roles({row: row != "glm_cap" for row in smoke.S3_ROWS})["passed"]


def test_mutation_skipping_the_research_request_fails_loudly(smoked, monkeypatch):
    """§21 (b): a generation whose material did not come from this attempt's dispatched research request pauses the
    unit (ConfigurationError) before the generator call -- whether the request is skipped or its finding forged."""
    material = {"purpose": "definition", "question": "q", "rule": None, "subject": None, "status": "found",
                "reason": None, "conclusion": None, "quotes": [], "calls": 3, "rounds": 1, "log": [], "pages": [],
                "quote": fake_research.DEFINITION, "page": "P1", "archive": "0" * 64,
                "source": {"title": "Derivative", "revid": 1003}}

    def skipped(self, *, concept, topic=None):  # the request is never sent: a finding appears in the log
        found = {"kind": "family_material", **material}
        self.log.append(found)
        return found

    for name, target, attribute, replacement in (
            ("t-skip", research.Researcher, "family_material", skipped),
            ("t-forged", research, "request", lambda *args, **kwargs: dict(material))):
        with monkeypatch.context() as patch:
            patch.setattr(target, attribute, replacement)
            rehearsal = S3Rehearsal(smoked["tmp"] / ("r-" + name))
            value = s3_unit(smoked, name, rehearsal=rehearsal)
        assert value["complete"] is False and value["stopped"] == "configuration"
        assert "generator" not in rehearsal.script.roles() and not rehearsal.wikipedia.requests
        log = (attempt_dir(smoked, name) / "diagnostics.log").read_text()
        assert "generation_without_research" in log
        assert not (attempt_dir(smoked, name) / "generated-G_self.json").exists()


# ----------------------------------------------------------------------------------- the checker adapter
@contextmanager
def _factory(docker, tmp_path):
    opened = []

    @contextmanager
    def workers(package, *, kind, hashseed=0, inputs_dir=None):
        worker = Worker(docker=docker, limits=TEST_LIMITS, scratch=tmp_path, hashseed=hashseed)
        opened.append(worker.start(package, kind=kind, inputs_dir=inputs_dir))
        try:
            yield worker
        finally:
            worker.close()

    yield workers, opened


def test_worker_checker_runs_the_registered_checker_in_a_generator_sandbox(tmp_path):
    family = livemath.FAMILIES["livemath.derivative"]
    specs = [livemath.instance(family, families.check(family, p))[1] for p in PARAMS]
    docker = SympyDocker(tmp_path / "docker")
    try:
        with _factory(docker, tmp_path) as (workers, opened):
            checker = livemath.WorkerChecker(workers)
            with checker.session():
                results = [checker.solve(spec) for spec in specs]
            assert len(opened) == 1 and opened[0].kind == "generator"  # one worker for the session
            assert [str(livemath.solved(r)) for r in results] == TRUTHS
            alone = checker.solve({"op": "binomial", "n": "10", "k": "3"})  # outside a session: a worker of its own
            assert len(opened) == 2 and livemath.solved(alone) == 120
            fault = checker.solve({"op": "unknown"})
            assert fault["ok"] is False and checker.solved[-1] == {"op": "unknown", "ok": False, "exact": None,
                                                                   "digits": None, "fault": fault["fault"]}
            assert [entry["exact"] for entry in checker.solved[:6]] == TRUTHS
        assert not docker.containers
    finally:
        docker.close()
    plain = FakeDocker(tmp_path / "plain")  # the host interpreter has no sympy: the checker faults, the set drops
    try:
        with _factory(plain, tmp_path) as (workers, _):
            result = livemath.WorkerChecker(workers).solve(specs[0])
        assert result["ok"] is False
        with pytest.raises(families.Drop, match="reference_fn_failed"):
            livemath.solved(result)
    finally:
        plain.close()
