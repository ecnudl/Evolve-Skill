"""v2's example SX (owner decision 2026-10-23 13:3x: "最好真正的跑通了一个示例再开始正式实验") rehearsed end to end with
zero network, as the chain-G smoke rehearsal of ``test_execskill_glm_smoke`` on a ``--example`` specification and a
main-v2 smoke manifest: S0 by hand, S2 and S3 as two ``smoke-run --fake`` processes, S-E6, then SX (``smoke-run --stage
SX --fake``: the whole v2 step on its 260 SearchQA smoke items, the method roles scripted by
``tests/execskill_fakes_sx.py``, the smoke solver by ``smoke._rehearsal_reply``) and ``smoke-summary``. The scripted
engineer's note changes no reply, so no round adopts it and the last evaluated candidate takes the self-test and the
acceptance round (``exercise``). Engineering fixtures only; no network, no container, no test-pool file."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict

from scripts import run_execskill as cli
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import budgets, fixtures, manifest, prelaunch, protocol, research, routes, smoke, step
from skillopt.execskill.sandbox import client as sandbox
from tests import execskill_fakes_research as fake_research
from tests.execskill_fakes import fake_config
from tests.fixtures.execskill.items import searchqa_items
from tests.test_execskill_cli import CONSENT, REPO, test_side  # noqa: F401 -- test_side: the synthetic test side
from tests.test_execskill_glm_smoke import ELUCID, GLM, conservative_d
from tests.test_execskill_manifest import MEASURED, fake_environment, given
from tests.test_execskill_routes import northgate_env
from tests.test_execskill_smoke_rehearsal import _alfworld, _write


def test_cli_rehearsal_runs_the_v2_example_smoke_end_to_end_as_an_engineering_fixture(tmp_path, monkeypatch,
                                                                                      test_side, capsys):
    environment = fake_environment()
    monkeypatch.setattr(manifest, "environment", lambda **_: dict(environment))
    monkeypatch.setattr(protocol, "SLOT_ROOT", str(tmp_path / "slots"))
    monkeypatch.setattr(protocol, "HISTORY_ROOT", str(tmp_path / "history"))
    root = test_side.root
    write_json(root / protocol.EXCLUSION_CONSENT, CONSENT)
    assert cli.main(test_side.argv) == 0
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
    assert cli.main(["smoke-make", "--root", str(root), "--solver-chain", "G", "--example", "--selftest", str(tested),
                     *item_args]) == 0
    capsys.readouterr()
    spec = str(root / smoke.SPEC)
    made = smoke.load(spec)
    assert made["stages"] == list(smoke.G_SMOKE_STAGES) + ["SX"] and made["plan"]["SX"] == smoke.PLAN["SX"]
    assert made["caps"]["smoke"] == budgets.smoke_caps(example=True) != budgets.smoke_caps()
    checks = tmp_path / "s0-checks.json"
    write_json(checks, {"checks": {row: True for row in smoke.S0_ROWS}})
    assert cli.main(["smoke", "--spec", spec, "--stage", "S0", "--input", str(checks)]) == 0
    capsys.readouterr()
    elucid, glm = fake_config(tmp_path, ELUCID), fake_config(tmp_path, GLM)
    archive = fake_research.archive_fixture(tmp_path / "archive")
    block = conservative_d(elucid["env_path"])
    clients = {"solver": {"D": block, "G": manifest.solver_block("G", env_path=glm["repo"])},
               "roles": dict(manifest.ROLES),
               "routes": {"D": {"B": routes.pin("D", "B", env_path=northgate_env(tmp_path), solver_block=block)}}}
    path = tmp_path / "smoke-manifest.json"
    smoke_m = manifest.make(path, evidence=manifest.SMOKE_EVIDENCE, environment_found=environment, measured=MEASURED,
                            configuration="main-v2",
                            **{**given(tmp_path), "root": str(root), "clients": clients,
                               "data": {"research": {"archive": str(archive),
                                                     "index_sha256": research.Archive(archive).index_sha256}}})
    assert smoke_m["prompt_sha"] == manifest.prompt_sha("main-v2") and "v2" in smoke_m["prompt_sha"]
    run = [sys.executable, "-B", str(REPO / "scripts" / "run_execskill.py"), "smoke-run", "--spec", spec,
           "--manifest", str(path), "--fake", "--stage"]
    children = {stage: subprocess.Popen(run + [stage], cwd=REPO, env=prelaunch.launch_env(), stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE) for stage in ("S2", "S3")}
    shown = {stage: child.communicate(timeout=1500) for stage, child in children.items()}
    assert [children[s].returncode for s in ("S2", "S3")] == [0, 0], {
        s: (out.decode("utf-8", "replace")[-2000:], err.decode("utf-8", "replace")[-3000:])
        for s, (out, err) in shown.items()}
    assert cli.main(["smoke-run", "--spec", spec, "--manifest", str(path), "--stage", "SE6", "--fake"]) == 0
    capsys.readouterr()
    se6 = protocol.verified(read_json(root / smoke.STAGES_DIR / "SE6.json"), "smoke-stage")["result"]
    assert se6["configuration"] == "main-v2" and se6["passed"] is True
    # SX in its own process, as the operator runs it
    child = subprocess.run(run + ["SX"], cwd=REPO, env=prelaunch.launch_env(), capture_output=True, timeout=3000)
    assert child.returncode == 0, (child.stdout.decode("utf-8", "replace")[-2000:],
                                   child.stderr.decode("utf-8", "replace")[-4000:])
    assert json.loads(child.stdout) == {"stage": "SX", "passed": True}
    sx = protocol.verified(read_json(root / smoke.STAGES_DIR / "SX.json"), "smoke-stage")
    assert sx["evidence"] == smoke.REHEARSAL_EVIDENCE and sx["result"]["passed"] is True
    assert set(sx["result"]["rows"]) == set(smoke.SX_ROWS) and all(sx["result"]["rows"].values())
    extras = sx["result"]
    assert extras["exercise"] == step.EXERCISE and extras["adopted"] == 0 and len(extras["rounds"]) == 2
    assert extras["decision"] in ("accept", "reject") and extras["train_cells"] > 0
    step_root = root / smoke.UNITS_DIR / smoke.SX_DIR / ("s1-" + step.SMOKE_BENCH)
    sealed = read_json(step_root / "engineer-r2" / "unit.json")["result"]["engineer"]
    assert sealed["mode"] == "train" and sealed["round"] == 2 and sealed["disclosed"] == []
    assert cli.main(["smoke-summary", "--spec", spec]) == 0
    capsys.readouterr()
    result = protocol.verified(read_json(root / smoke.RESULT), "smoke-result")
    assert result["required"] == list(smoke.G_SMOKE_STAGES) + ["SX"] and result["stages"]["SX"] == "pass"
    assert result["passed"] is True and smoke.waiver_name(result) == protocol.SMOKE_WAIVER_V2
