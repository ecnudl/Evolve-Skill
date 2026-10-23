"""The chain-G smoke (registrar addendum 2026-10-23 02:3x, "smoke solver chain"): ``smoke.make(...,
solver_chain="G")`` pins GLM-5.3 through its frozen client as the smoke solver -- chain G's registered settings (M =
B = 65,536 on every bench, read timeout 2,400 s, echo glm-5.3), no S1, no probe root, no control cells -- while a
chain D specification stays as registered. Checked: the specification and its refusals, ``probe`` and the S1 record
refused, the S2 receipt criterion without S1-e, the frozen GLM receipts as the smoke classes them, the confirmation's
echo set, the smoke manifest's solver block with its Setting, endpoint, pools and mini-step solver, the real-mode
credential check, ``smoke-make --solver-chain``, and the zero-network CLI rehearsal end to end on a chain-G spec: S0 by
hand, no S1, chain D's block on the conservative unprobed bound (branch N, longest ``routes.S1B_CEILING``) with its
route-B pin, S2 and S3 as two ``smoke-run --fake`` processes, S-E6, ``smoke-summary`` and ``test-read-estimate``,
then the main manifest from the same pins with both chains' Settings built at zero calls. Engineering fixtures only;
no network, no container, no test-pool file."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from dataclasses import asdict, replace
from fractions import Fraction
from types import SimpleNamespace

import pytest

from scripts import run_execskill as cli
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (budgets, client, fixtures, manifest, prelaunch, protocol, research, routes, smoke, step,
                                units)
from skillopt.execskill.chain import FIRST_CALL_ECHO
from skillopt.execskill.package import empty
from skillopt.execskill.sandbox import client as sandbox
from tests import execskill_fakes_research as fake_research
from tests.execskill_fakes import FakeProvider, Reply, fake_config
from tests.fixtures.execskill.items import searchqa_items
from tests.test_execskill_cli import CONSENT, REPO, test_side  # noqa: F401 -- test_side: the synthetic test side
from tests.test_execskill_evaluation import consent_value
from tests.test_execskill_manifest import (MEASURED, NO_CALLS, FakeDockerCLI, _items, _pinned, fake_environment,
                                           given, run_given)
from tests.test_execskill_routes import northgate_env
from tests.test_execskill_smoke import ENVIRONMENT, S1E, items, production, selftest
from tests.test_execskill_smoke_rehearsal import _alfworld, _write

GLM, ELUCID = protocol.CHAINS["G"], protocol.CHAINS["D"]
GLM_M = dict.fromkeys(protocol.BENCHES, 65_536)
NO_S1 = "a chain-G smoke has no S1"
PLACEHOLDER = "chain D priced at the glm-5.3 per-cell tokens: a placeholder (§4.1, §9.3)"


def quick(tmp_path, **options):
    """A smoke specification on ``tmp_path / "smoke"`` over synthetic item files (no manifest)."""
    return smoke.make(tmp_path / "smoke", items=items(tmp_path), selftest=selftest(tmp_path),
                      environment_found=ENVIRONMENT, **options)


def g_spec(tmp_path, root):
    """A chain-G smoke specification on ``root`` over pool-shaped item files and a passing S0 self-test whose
    measurements are ``MEASURED``'s (as ``test_execskill_manifest.smoke_spec``, on chain G)."""
    sets = {b: _pinned(tmp_path / "smoke-items" / (b + ".json"), _items(tmp_path, b, 3))["path"]
            for b in smoke.ITEM_SETS}
    tested = tmp_path / "s0" / smoke.SELFTEST
    write_json(tested, protocol.record("sandbox-selftest", "smoke", {
        "escape_rows": {row: True for row in smoke.ESCAPE_ROWS}, "escape_probe_sha256": "0" * 64,
        "worker_sha256": "1" * 64, "image": sandbox.IMAGE,
        "limits": {k: asdict(v) for k, v in sorted(sandbox.LIMITS.items())},
        "measured": {**{k: MEASURED[k] for k in ("vsz_kib", "rss_kib", "view_bytes_p99")}, "start_seconds": 2.6,
                     "views": 15}, "passed": True}))
    return smoke.make(root, items=sets, selftest=str(tested), environment_found=fake_environment(), solver_chain="G")


def conservative_d(env_path):
    """Chain D's solver block on the unprobed conservative bound (branch N, longest ``routes.S1B_CEILING``): what the
    manifest format needs of chain D in a chain-G smoke, which has no S1 (registrar addendum 2026-10-23 02:3x)."""
    return manifest.solver_block("D", env_path=env_path, branch="N", longest=routes.S1B_CEILING)


@pytest.fixture
def g_manifest(tmp_path, monkeypatch):
    """A chain-G smoke specification and its smoke manifest (``conservative_d``, chain G's credential repository)."""
    root = tmp_path / "smoke"
    values = run_given(tmp_path, monkeypatch, root=root)
    elucid, glm = fake_config(tmp_path, ELUCID), fake_config(tmp_path, GLM)
    values["clients"] = {"solver": {"D": conservative_d(elucid["env_path"]),
                                    "G": manifest.solver_block("G", env_path=glm["repo"])},
                         "roles": dict(manifest.ROLES)}
    values["data"] = {"research": values["data"]["research"]}
    spec = g_spec(tmp_path, root)
    path = tmp_path / "smoke-manifest.json"
    m = manifest.make(path, evidence=manifest.SMOKE_EVIDENCE, environment_found=fake_environment(), measured=MEASURED,
                      **values)
    return SimpleNamespace(spec=spec, m=m, path=path, root=root, elucid=elucid["env_path"], glm=glm["repo"])


# ------------------------------------------------------------------------------------------ the specification
def test_a_chain_g_spec_pins_glm_through_its_frozen_settings_and_lists_no_s1(tmp_path):
    spec = quick(tmp_path, solver_chain="G")
    assert smoke.load(tmp_path / "smoke" / smoke.SPEC) == spec
    assert spec["solver"] == {"chain": "G", "model": GLM, "M": GLM_M,
                              "read_timeout": dict.fromkeys(protocol.BENCHES, 2_400), "proxy": protocol.GATEWAY,
                              "reasoning_effort": None, "b_probe": None, "s1d_tokens": None,
                              "response_model_ids": [GLM]}
    assert spec["stages"] == list(smoke.G_SMOKE_STAGES) == ["S0", "S2", "S3", "SE6"]
    assert spec["probe_root"] is None and spec["control_cells"] == [] and spec["noise_anchor"] is None
    found = smoke.solver_of(spec)
    assert (found.chain, found.model, found.echo) == ("G", GLM, frozenset({GLM})) == (
        "G", GLM, FIRST_CALL_ECHO["G"])
    summary = smoke.summary(spec)  # nothing recorded yet: reported, not sealed
    assert summary["required"] == list(smoke.G_SMOKE_STAGES) and summary["stages"]["S1"] == "not_required"
    wider = smoke.make(tmp_path / "wider", items=items(tmp_path), selftest=selftest(tmp_path), write=False,
                       environment_found=ENVIRONMENT, solver_chain="G", stages=smoke.G_SMOKE_STAGES + ("SN1", "S4"),
                       noise_anchor={"searchqa": 0.3, "alfworld": 0.45})
    assert wider["stages"] == ["S0", "S2", "S3", "SE6", "SN1", "S4"]  # S-N1 and S4 stay optional


def test_a_chain_g_spec_refuses_s1_a_probe_root_and_control_cells(tmp_path):
    def make(**options):
        return quick(tmp_path, solver_chain="G", write=False, **options)

    for stages in (smoke.SMOKE_STAGES, smoke.G_SMOKE_STAGES + ("S1",), ("S0", "S2", "SE6")):
        with pytest.raises(ValueError, match=NO_S1):
            make(stages=stages)
    with pytest.raises(ValueError, match="names no probe root"):
        make(probe_root=tmp_path / "probe")
    with pytest.raises(ValueError, match="no control cells"):
        make(control_cells=["S2/searchqa/X/fx-crash/q1/1"])
    with pytest.raises(ValueError, match="D or G"):
        quick(tmp_path, solver_chain="E", write=False)
    assert not (tmp_path / "smoke").exists()


def test_a_chain_d_spec_is_the_registered_one(tmp_path):
    default = quick(tmp_path, write=False, probe_root=tmp_path / "probe")
    assert quick(tmp_path, write=False, probe_root=tmp_path / "probe", solver_chain="D") == default
    assert default["solver"] == {  # no ``chain`` field: a chain D spec is byte for byte the registered one
        "model": ELUCID, "M": {"searchqa": 8_192, "officeqa": 8_192, "livemath": 8_192, "spreadsheetbench": 16_384,
                               "alfworld": 1_024},
        "read_timeout": {"searchqa": 600, "officeqa": 600, "livemath": 600, "spreadsheetbench": 900, "alfworld": 180},
        "proxy": protocol.GATEWAY, "reasoning_effort": "none", "b_probe": 32_768, "s1d_tokens": 64,
        "response_model_ids": sorted(client.ELUCID_RESPONSE_MODEL_IDS)}  # owner 2026-10-23 19:1x: with the alias
    assert default["stages"] == list(smoke.SMOKE_STAGES) and default["probe_root"] == str(tmp_path / "probe")
    assert quick(tmp_path, write=False)["probe_root"] == protocol.PROBE_ROOT  # the registered default
    found = smoke.solver_of(default)
    assert (found.chain, found.model, found.echo) == ("D", ELUCID, client.ELUCID_RESPONSE_MODEL_IDS)
    with pytest.raises(ValueError, match="S0, S1, S2, S3 and S-E6"):  # chain D keeps S1
        quick(tmp_path, write=False, stages=smoke.G_SMOKE_STAGES)


def test_solver_of_refuses_a_block_that_is_not_its_chains(tmp_path):
    g, d = quick(tmp_path, solver_chain="G", write=False), quick(tmp_path, write=False)
    for broken in ({**g, "stages": list(smoke.SMOKE_STAGES)}, {**g, "solver": {**g["solver"], "model": ELUCID}},
                   {**g, "solver": {**g["solver"], "response_model_ids": [ELUCID]}},
                   {**d, "solver": {**d["solver"], "chain": "G"}}, {**d, "solver": {**d["solver"], "chain": "X"}}):
        with pytest.raises(ValueError, match="chain D's or chain G's"):
            smoke.solver_of(broken)


# ----------------------------------------------------------------------------------------------- no S1
def test_probe_and_the_s1_record_refuse_a_chain_g_spec(tmp_path):
    spec = quick(tmp_path, solver_chain="G")
    path, elucid = str(tmp_path / "smoke" / smoke.SPEC), fake_config(tmp_path, ELUCID)["env_path"]
    with pytest.raises(ValueError, match=NO_S1):
        smoke.run_probe(spec, env_path=elucid, slot_root=tmp_path / "slots", transport=NO_CALLS)
    for argv in (["probe", "--spec", path, "--env-path", elucid], ["probe", "--spec", path, "--fake"]):
        with pytest.raises(ValueError, match=NO_S1):
            cli.main(argv)
    with pytest.raises(ValueError, match=NO_S1):
        smoke.record(spec, "S1", {"rows": {row: True for row in smoke.S1_ROWS}, "passed": True})
    assert smoke._probe_entries(spec) == []
    assert not (tmp_path / "slots").exists() and not (tmp_path / "smoke" / smoke.STAGES_DIR).exists()


def test_the_s2_receipt_criterion_asks_s1e_only_of_a_smoke_with_s1(tmp_path):
    g, d = quick(tmp_path, solver_chain="G", write=False), quick(tmp_path, write=False)
    bound_g = dict(GLM_M)
    glm = [{**entry, "M": 65_536, "B": 65_536} for entry in production(protocol.MIN_PRODUCTION_RECEIPTS)]
    judged = smoke.receipt_classes(glm, g, ledger_bound=bound_g)
    assert judged["passed"] is True and judged["s1e_mismatch"] == [] and judged["counts"] == {
        "control": 0, "probe": 0, "production": 300, "resend": 0, "unregistered": 0}
    assert smoke.receipt_classes(glm[1:], g, ledger_bound=bound_g)["passed"] is False  # still 300 production receipts
    leaked = glm[:-1] + [{**glm[-1], "receipt": {"ok": False, "subtype": client.REASONING_MISMATCH}}]
    assert smoke.receipt_classes(leaked, g, ledger_bound=bound_g)["passed"] is False  # leak counting unchanged
    assert smoke.receipt_classes(glm + [S1E], g, ledger_bound=bound_g)["passed"] is False  # no S1-e in a G smoke
    elucid = production(protocol.MIN_PRODUCTION_RECEIPTS)  # chain D's registered M and B (branch E)
    assert smoke.receipt_classes(elucid, g, ledger_bound=bound_g)["counts"]["unregistered"] == 300
    bound_d = {b: protocol.ledger_bound(ELUCID, b, branch="E") for b in protocol.BENCHES}
    assert smoke.receipt_classes(elucid, d, ledger_bound=bound_d)["passed"] is False  # unchanged: chain D needs S1-e
    assert smoke.receipt_classes(elucid + [S1E], d, ledger_bound=bound_d)["passed"] is True


def test_the_frozen_glm_receipts_carry_no_leak_as_the_smoke_classes_them(tmp_path):
    """The frozen GLM client keeps thinking enabled, so it never reports ``thinking_mismatch``, and its receipts carry
    no subtype: a reply with reasoning text is an ok production receipt without a leak; an echo other than glm-5.3 is
    a model mismatch (still a production receipt by class) that never confirms a first call; a reply without text is
    not ok either."""
    g = quick(tmp_path, solver_chain="G", write=False)
    replies = iter([Reply(text="<answer>1</answer>", reasoning="thinking first"),
                    Reply(text="<answer>1</answer>", model="glm-5.3-flash"), Reply(text=None, reasoning="only")])
    provider = FakeProvider(GLM, lambda system, user: next(replies))
    solver = client.solver_client(GLM, config=fake_config(tmp_path, GLM), transport=provider.transport)
    assert (solver.max_tokens, solver.http.timeout.read) == (65_536, 2_400)
    thinking, other, blank = (solver.call("system", "user") for _ in range(3))
    assert thinking["ok"] is True and thinking["reasoning_chars"] > 0 and "subtype" not in thinking
    assert other["ok"] is False and other["error_type"] == "model_mismatch" and "subtype" not in other
    assert blank["ok"] is False and blank["error_type"] == "content_missing" and "subtype" not in blank
    assert all(body["thinking"] == {"type": "enabled"} and body["max_tokens"] == 65_536 for body in provider.requests)
    sends = [{"request_sha256": str(n), "max_tokens": 65_536, "request_bytes": 10, "receipt": receipt}
             for n, receipt in enumerate((thinking, other, blank))]
    entries = smoke.classed_sends(g, sends, stage="S2", cell="S2/searchqa/C/q1/1", bench="searchqa",
                                  body=smoke.REGISTERED_BODY, nominal=65_536, ledger_bound={"searchqa": 65_536})
    assert [entry["class"] for entry in entries] == [smoke.PRODUCTION] * 3
    assert [entry["receipt"]["subtype"] for entry in entries] == [None] * 3
    echo = smoke.solver_of(g).echo
    assert smoke._confirmed({"sends": sends[:1]}, echo) and not smoke._confirmed({"sends": sends[1:]}, echo)


def test_the_confirmation_reads_the_echo_set_of_the_specs_chain(tmp_path):
    g = smoke.solver_of(quick(tmp_path, solver_chain="G", write=False))
    d = smoke.solver_of(quick(tmp_path, write=False))

    def first(model, ok=True):
        return {"sends": [{"receipt": {"ok": ok, "returned_model": model}}]}

    assert smoke._confirmed(first(GLM), g.echo) and not smoke._confirmed(first(ELUCID), g.echo)
    assert smoke._confirmed(first(ELUCID), d.echo) and not smoke._confirmed(first(GLM), d.echo)
    assert not smoke._confirmed(first(GLM, ok=False), g.echo) and not smoke._confirmed({"sends": []}, g.echo)


# ------------------------------------------------------------------------ the smoke manifest of a chain-G spec
def test_the_smoke_setting_endpoint_and_mini_step_of_a_chain_g_spec_are_glm(g_manifest):
    spec, m, root = g_manifest.spec, g_manifest.m, g_manifest.root
    assert manifest._solver_chain(budgets.SMOKE, root) == "G" and manifest._solver_chain("D", root) == "D"
    setting = manifest.setting_of(m, budgets.SMOKE, docker=FakeDockerCLI(), transport=NO_CALLS)
    assert (setting.branch, setting.longest) == (None, None) and list(setting.pools) == sorted(smoke.ITEM_SETS)
    assert {scope: value["cap"] for scope, value in setting.budget.snapshot().items()} == budgets.smoke_caps()
    solver = setting.clients(GLM, "searchqa")
    assert (solver.model, solver.max_tokens, solver.http.timeout.read) == (GLM, 65_536, 2_400)
    with pytest.raises(ValueError):  # the chain-G smoke has no elucid client
        setting.clients(ELUCID, "searchqa")
    for bench in protocol.BENCHES:
        local = units.for_unit(setting, budgets.SMOKE, bench, "smoke/S2/" + bench)
        endpoint, watched = smoke._endpoint(spec, local, bench)
        assert (endpoint.model, endpoint.max_tokens, watched.max_tokens) == (GLM, 65_536, 65_536)
    parent = empty(step="smoke/s0", evidence=setting.evidence)
    mini = step.SmokeStep(items=(), candidate=replace(fixtures.fixture_package(), parent_sha256=parent.sha256),
                          model=smoke.solver_of(spec).model)
    endpoint = step._Step(setting, None, budgets.SMOKE, step.SMOKE_BENCH, 1, parent, root / "S4", mini).solver("run", 1)
    assert (endpoint.model, endpoint.max_tokens) == (GLM, 65_536)
    with pytest.raises(ValueError):  # a mini-step on chain D's default model is refused by the Setting, never sent
        step._Step(setting, None, budgets.SMOKE, step.SMOKE_BENCH, 1, parent, root / "S4",
                   replace(mini, model=ELUCID)).solver("run", 1)


def test_a_real_chain_g_stage_names_chain_gs_repository_as_both_credentials(g_manifest, monkeypatch):
    spec, m, path = g_manifest.spec, g_manifest.m, g_manifest.path
    with pytest.raises(ValueError, match="names chain G's credential repository as the env path"):
        smoke.run_stage(spec, path, "S2")  # refused before anything is built
    verified = []
    monkeypatch.setattr(smoke.sandbox, "Docker", FakeDockerCLI)  # nothing below reaches a docker daemon or a model
    monkeypatch.setattr(manifest, "verify_unit", lambda m, docker: verified.append(m[protocol.RECORD_HASH]))
    for env_path in (g_manifest.elucid, protocol.ELUCID_ENV):  # the elucid file, or the CLI's default when omitted
        with pytest.raises(ValueError, match="not the smoke manifest's"):
            with smoke._backends(spec, m, path, fake=False, env_path=env_path, roles_repo=g_manifest.glm):
                pass
    assert verified == []
    with smoke._backends(spec, m, path, fake=False, env_path=g_manifest.glm,
                         roles_repo=g_manifest.glm) as (setting, docker):
        assert isinstance(docker, FakeDockerCLI) and setting.clients(GLM, "officeqa").max_tokens == 65_536
    assert verified == [m[protocol.RECORD_HASH]]
    assert not (g_manifest.root / smoke.UNITS_DIR).exists() and not (g_manifest.root / smoke.STAGES_DIR).exists()


def test_smoke_make_takes_the_solver_chain(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(manifest, "environment", lambda **_: dict(ENVIRONMENT))
    args = [arg for name, path in sorted(items(tmp_path).items()) for arg in ("--items", "%s=%s" % (name, path))]
    args += ["--selftest", selftest(tmp_path)]
    for chain, options, stages in (("G", ["--solver-chain", "G"], smoke.G_SMOKE_STAGES),
                                   ("D", ["--probe-root", str(tmp_path / "probe")], smoke.SMOKE_STAGES)):
        assert cli.main(["smoke-make", "--root", str(tmp_path / chain), *options, *args]) == 0
        shown = json.loads(capsys.readouterr().out)
        assert (shown["solver_chain"], shown["stages"]) == (chain, list(stages))
    assert read_json(tmp_path / "G" / smoke.SPEC)["solver"]["chain"] == "G"
    assert "chain" not in read_json(tmp_path / "D" / smoke.SPEC)["solver"]
    control = tmp_path / "control.json"
    write_json(control, ["S2/searchqa/X/fx-crash/q1/1"])
    for refused, match in ((["--probe-root", str(tmp_path / "probe")], "names no probe root"),
                           (["--control-cells", str(control)], "no control cells")):
        with pytest.raises(ValueError, match=match):
            cli.main(["smoke-make", "--root", str(tmp_path / "x"), "--solver-chain", "G", *refused, *args])
    with pytest.raises(SystemExit):
        cli.main(["smoke-make", "--root", str(tmp_path / "x"), "--solver-chain", "E", *args])
    assert not (tmp_path / "x").exists()


# --------------------------------------------------------------------------------------- the CLI rehearsal
def test_cli_rehearsal_runs_the_chain_g_smoke_end_to_end_as_an_engineering_fixture(tmp_path, monkeypatch, test_side,
                                                                                    capsys):
    """Registrar addendum 2026-10-23 02:3x on the plan-§7 fakes with zero network (as ``test_execskill_cli``'s chain D
    rehearsal of configuration ``main``): S0 by hand on the persisted synthetic exclusion unit; no S1 -- ``probe``
    refuses the spec and nothing is written under a probe root; the smoke manifest's chain D block on the conservative
    unprobed bound (``conservative_d``: B = max(4M, 384)) with chain D's route-B pin from it, no S1 record anywhere; S2
    and S3 as two ``smoke-run --fake`` processes on the scripted glm-5.3 gateway (a request for another model fails
    the fake); S-E6 with chain D priced at the glm-5.3 per-cell tokens; ``smoke-summary`` passing on S0, S2, S3 and
    S-E6 with S1 not required; ``test-read-estimate``; then main-runbook §3.2/§4 on a throwaway main root: the main
    manifest from the same pins and both chains' Settings built with zero calls."""
    environment = fake_environment()
    monkeypatch.setattr(manifest, "environment", lambda **_: dict(environment))
    monkeypatch.setattr(protocol, "SLOT_ROOT", str(tmp_path / "slots"))  # the smoke manifest records both roots,
    monkeypatch.setattr(protocol, "HISTORY_ROOT", str(tmp_path / "history"))  # which the smoke-run processes use
    root = test_side.root
    write_json(root / protocol.EXCLUSION_CONSENT, CONSENT)
    assert cli.main(test_side.argv) == 0  # the persisted exclusion unit that S0's supply row reads (synthetic panels)
    capsys.readouterr()
    fixtures.make_fixtures(tmp_path / "fixtures")
    sets = {bench: str(tmp_path / "fixtures" / (bench + ".json")) for bench in ("officeqa", "livemath",
                                                                               "spreadsheetbench")}
    sets["searchqa"] = _write(tmp_path / "items" / "searchqa.json", searchqa_items(280))
    sets["alfworld"] = _write(tmp_path / "items" / "alfworld.json", _alfworld(tmp_path / "games"))
    tested = tmp_path / "s0" / smoke.SELFTEST
    write_json(tested, protocol.record("sandbox-selftest", "smoke", {
        "escape_rows": {row: True for row in smoke.ESCAPE_ROWS}, "escape_probe_sha256": "0" * 64,
        "worker_sha256": "1" * 64, "image": sandbox.IMAGE,
        "limits": {k: asdict(v) for k, v in sorted(sandbox.LIMITS.items())},
        "measured": {**{k: MEASURED[k] for k in ("vsz_kib", "rss_kib", "view_bytes_p99")}, "start_seconds": 2.6,
                     "views": 15}, "passed": True}))
    item_args = [arg for name in smoke.ITEM_SETS for arg in ("--items", "%s=%s" % (name, sets[name]))]
    assert cli.main(["smoke-make", "--root", str(root), "--solver-chain", "G", "--selftest", str(tested),
                     *item_args]) == 0
    assert json.loads(capsys.readouterr().out)["solver_chain"] == "G"
    spec = str(root / smoke.SPEC)
    checks = tmp_path / "s0-checks.json"
    write_json(checks, {"checks": {row: True for row in smoke.S0_ROWS}})
    assert cli.main(["smoke", "--spec", spec, "--stage", "S0", "--input", str(checks)]) == 0
    with pytest.raises(ValueError, match=NO_S1):
        cli.main(["probe", "--spec", spec, "--fake"])
    capsys.readouterr()
    elucid, glm = fake_config(tmp_path, ELUCID), fake_config(tmp_path, GLM)
    archive = fake_research.archive_fixture(tmp_path / "archive")
    block = conservative_d(elucid["env_path"])  # smoke-runbook, chain-G section: no S1, so no S1.json is read
    assert (block["branch"], block["longest"]) == ("N", 256) and block["B"] == {
        b: max(4 * protocol.solver_tokens(ELUCID, b), 384) for b in protocol.BENCHES}
    clients = {"solver": {"D": block, "G": manifest.solver_block("G", env_path=glm["repo"])},
               "roles": dict(manifest.ROLES),
               "routes": {"D": {"B": routes.pin("D", "B", env_path=northgate_env(tmp_path), solver_block=block)}}}
    path = tmp_path / "smoke-manifest.json"
    smoke_m = manifest.make(path, evidence=manifest.SMOKE_EVIDENCE, environment_found=environment, measured=MEASURED,
                            configuration="main",
                            **{**given(tmp_path), "root": str(root), "clients": clients,
                               "data": {"research": {"archive": str(archive),
                                                     "index_sha256": research.Archive(archive).index_sha256}}})
    run = [sys.executable, "-B", str(REPO / "scripts" / "run_execskill.py"), "smoke-run", "--spec", spec,
           "--manifest", str(path), "--fake", "--stage"]
    children = {stage: subprocess.Popen(run + [stage], cwd=REPO, env=prelaunch.launch_env(), stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE) for stage in ("S2", "S3")}  # side by side
    shown = {stage: child.communicate(timeout=1500) for stage, child in children.items()}
    assert [children[s].returncode for s in ("S2", "S3")] == [0, 0], {
        s: (out.decode("utf-8", "replace")[-2000:], err.decode("utf-8", "replace")[-3000:])
        for s, (out, err) in shown.items()}
    assert [json.loads(shown[s][0]) for s in ("S2", "S3")] == [{"stage": s, "passed": True} for s in ("S2", "S3")]
    assert cli.main(["smoke-run", "--spec", spec, "--manifest", str(path), "--stage", "SE6", "--fake"]) == 0
    assert cli.main(["smoke-summary", "--spec", spec]) == 0
    capsys.readouterr()
    stages = {stage: protocol.verified(read_json(root / smoke.STAGES_DIR / (stage + ".json")), "smoke-stage")
              for stage in smoke.G_SMOKE_STAGES}
    assert {stage: value["evidence"] for stage, value in stages.items()} == {
        "S0": "smoke", **{stage: smoke.REHEARSAL_EVIDENCE for stage in ("S2", "S3", "SE6")}}
    assert all(value["result"]["passed"] is True for value in stages.values())
    assert not (root / smoke.STAGES_DIR / "S1.json").exists() and not (tmp_path / "pre" / "probe").exists()
    result = protocol.verified(read_json(root / smoke.RESULT), "smoke-result")
    assert result["passed"] is True and result["evidence"] == smoke.REHEARSAL_EVIDENCE
    assert result["required"] == list(smoke.G_SMOKE_STAGES) and result["stages"]["S1"] == "not_required"
    assert set(result["rows"]) == set(smoke.G_SMOKE_STAGES) and all(
        verdict == "pass" for rows in result["rows"].values() for verdict in rows.values())
    receipts = stages["S2"]["result"]["receipts"]
    assert receipts["s1e_mismatch"] == [] and receipts["counts"]["production"] >= protocol.MIN_PRODUCTION_RECEIPTS
    assert {kind: receipts["counts"][kind] for kind in ("control", "probe", "resend", "unregistered")} == dict.fromkeys(
        ("control", "probe", "resend", "unregistered"), 0) and not any(receipts["leaks"].values())
    for name in smoke.ITEM_SETS:  # every S2 send went to glm-5.3 with M = B = 65,536
        unit = read_json(root / smoke.UNITS_DIR / "S2" / name / "unit.json")
        entries = [entry for cell in unit["result"]["cells"] for entry in cell["entries"]]
        assert entries and {(entry["M"], entry["B"]) for entry in entries} == {(65_536, 65_536)}
    se6 = stages["SE6"]["result"]
    assert se6["chain_d"] == PLACEHOLDER and "chain_g" not in se6 and se6["configuration"] == "main"
    assert se6["bounds"] == {"D": block["B"], "G": GLM_M}
    out = tmp_path / "test-read-estimate.json"
    assert cli.main(["test-read-estimate", "--smoke", str(root), "--configuration", "main", "--out", str(out)]) == 0
    capsys.readouterr()
    estimate = protocol.verified(read_json(out), "test-read-estimate")
    value = estimate["value"]
    assert estimate["evidence"] == smoke.REHEARSAL_EVIDENCE and estimate["test_read_estimate"] == {"D": value,
                                                                                                    "G": value}
    assert math.ceil(sum(Fraction(term) for term in estimate["terms"].values())) == value and value > 0
    # main-runbook §3.2 and §4 on a throwaway main root: the main manifest from the same pins (no S1 record read)
    main_root, mm = tmp_path / "main-root", tmp_path / "main-manifest.json"
    monkeypatch.setitem(protocol.RUN_ROOTS, "main", str(main_root))
    write_json(main_root / "shared" / "consent.json", consent_value())  # stands in for the owner's file
    tail = tmp_path / "history" / "searchqa-tail.json"
    pins = {"root": str(main_root), "evidence": "main_real_run", "configuration": "main",
            "data": {**smoke_m["data"],
                     "pools": {b: _pinned(tmp_path / "pools" / (b + ".json"), _items(tmp_path, b, 4))
                               for b in protocol.BENCHES},
                     "searchqa_tail": {"path": str(tail), "sha256": hashlib.sha256(tail.read_bytes()).hexdigest()},
                     "test_read_estimate": {"G": value, "D": value},
                     "test_read_terms": {"G": estimate["terms"], "D": estimate["terms"]}},
            **{key: smoke_m[key] for key in ("runtime", "cards", "clients", "sheet_qualification", "contracts",
                                             "fixtures", "provenance")}}
    write_json(tmp_path / "main-pins.json", pins)
    write_json(tmp_path / "s0-pins.json", {"limits": {k: asdict(v) for k, v in sorted(sandbox.LIMITS.items())},
                                           "measured": dict(MEASURED)})
    assert cli.main(["make-manifest", "--out", str(mm), "--pins", str(tmp_path / "main-pins.json"),
                     "--exclusion-root", str(root), "--s0-pins", str(tmp_path / "s0-pins.json")]) == 0
    capsys.readouterr()
    found = manifest.load(mm, verify=False)
    assert found["clients"] == smoke_m["clients"] and found["clients"]["solver"]["D"]["branch"] == "N"
    for name in protocol.CHAINS:  # zero calls: what `run --manifest $MM --chain C` builds first
        built = manifest.setting_of(found, name, path=mm, docker=FakeDockerCLI(), transport=NO_CALLS)
        assert (protocol.configuration_of(built), set(built.pools)) == ("main", set(protocol.BENCHES))
        assert built.extra[step.TAIL]["exclusion"] == found["data"]["exclusion"]["searchqa_test_exclusion"]
        assert (built.branch, built.longest, built.extra.get("route")) == (
            ("N", 256, "A") if name == "D" else (None, None, None))
    assert cli.main(["consent", "--root", str(main_root)]) == 0
    assert json.loads(capsys.readouterr().out) == {"test_read": "valid"}
