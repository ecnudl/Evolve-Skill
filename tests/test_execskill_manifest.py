"""T-MAN-1..2 and the pre-launch checks (implementation plan §2.9, §8.1, §10 steps 1-3; registration §1, §10 S0, §14
#3): the route-B manifest's code check, environment, registered fields and clients; the snapshot list, the S0 pytest
row and the leftover check. Offline: a fake docker CLI and a fake sandbox ping, synthetic trees in tmp_path."""
from __future__ import annotations

import functools
import hashlib
import json
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import asdict, replace
from types import SimpleNamespace

import httpx
import pytest

from skillopt.continual_eval.core import read_json, safe_path, write_json
from skillopt.execskill import (budgets, describer, engineer, examiner, manifest, prelaunch, protocol, qualify,
                                research, slots, smoke, step, supply)
from skillopt.execskill.generators import livemath, sheet
from skillopt.execskill.errors import ConfigurationError
from skillopt.execskill.sandbox import client as sandbox
from tests import execskill_fakes_research as fake_research
from tests.execskill_fakes import fake_config
from tests.fixtures.execskill.items import (alfworld_items, livemath_items, officeqa_items, searchqa_items,
                                            spreadsheetbench_items)

PING = {"python": "3.11.13", "numpy": "1.26.4", "openpyxl": "3.1.5", "pandas": "2.2.3", "sympy": "1.13.3",
        "worker_sha256": "0" * 64}
HEAD = "010d453" + "0" * 33


class FakeDockerCLI:
    """The ``sandbox.client.Docker`` surface: scripted stdout per docker subcommand, every argv recorded."""

    def __init__(self, image=sandbox.IMAGE, containers=b"", binary="docker"):
        self.binary, self.image, self.containers, self.argvs = binary, image, containers, []

    def run(self, argv, timeout):
        self.argvs.append(argv)
        out = {"image": self.image.encode() if self.image else b"", "version": b"27.3.1", "ps": self.containers}
        found = out[argv[1]]
        return sandbox.Completed(0 if found or argv[1] == "ps" else 1, found)


def fake_environment():
    return manifest.environment(docker=FakeDockerCLI(), ping=lambda: dict(PING))


CARDS = {b: "Card (%s): read the task, then answer in the registered format." % b for b in protocol.BENCHES}
CONTRACTS = {"searchqa": "\nReturn the concise final answer inside <answer>...</answer>.",
             "officeqa": "\nReturn the concise final answer inside <answer>...</answer>.",
             "livemath": "\nChoose exactly one of the listed options and return only its letter inside "
                         "<answer>...</answer>.",
             "spreadsheetbench": "\nReturn one complete Python program in a ```python code block.",
             "alfworld": "Act in the text environment. Return a single action inside <action>...</action>."}


def given(tmp_path):
    credentials = tmp_path / "elucid.env"
    credentials.write_text("synthetic, never read\n")
    repo = tmp_path / "bigmodel-repo"
    repo.mkdir(exist_ok=True)
    return {"root": str(tmp_path / "run"), "data": {"items": {"searchqa": {"sha256": "1" * 64}}},
            # the shapes of pilot-runbook §3.1 (registrar addendum 14:10 row 12): the cards are texts, the contracts
            # {text, sha256(text)}, the sheet qualification {path, record_hash}, the fixtures {sha256}
            "sheet_qualification": {"path": str(tmp_path / "sheet" / "qualification.json"), "record_hash": "2" * 64},
            "cards": dict(CARDS),
            "contracts": {b: {"text": text, "sha": hashlib.sha256(text.encode()).hexdigest()}
                          for b, text in CONTRACTS.items()},
            "runtime": {b: {} for b in protocol.BENCHES},
            "clients": {"solver": {"D": manifest.solver_block("D", env_path=credentials, branch="E"),
                                   "G": manifest.solver_block("G", env_path=repo)},
                        "roles": dict(manifest.ROLES)},
            "fixtures": {"sha256": "6" * 64},
            "provenance": {"build_tree": protocol.BUILD_TREE, "git_head": HEAD,
                           "snapshot_root": protocol.SNAPSHOT_ROOT, "sha256_list_sha256": "7" * 64,
                           "env_files_absent": True}}


MEASURED = {"vsz_kib": 173_936, "rss_kib": 112_052, "view_bytes_p99": 40_000, "native_peak_rss_kib": 900_000}


def tree(root):
    for name, text in {"skillopt/execskill/__init__.py": "VERSION = 1\n", "skillopt/execskill/a.py": "A = 1\n",
                       "scripts/run_execskill.py": "print(1)\n", "skillopt/other/b.txt": "data\n"}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


# ------------------------------------------------------------------------------------------------------ T-MAN-1
def test_t_man_1_verify_code_refuses_a_changed_unpinned_or_foreign_tree(tmp_path):
    repo = tree(tmp_path / "repo")
    pinned = {"code": manifest.pin_code(repo), "environment": fake_environment()}
    assert set(pinned["code"]) == {"skillopt/execskill/__init__.py", "skillopt/execskill/a.py",
                                   "scripts/run_execskill.py", "skillopt/other/b.txt"}
    manifest.verify_code(pinned, repo)
    (repo / "skillopt/execskill/a.py").write_text("A = 2\n")
    with pytest.raises(ValueError, match="Files differ"):
        manifest.verify_code(pinned, repo)
    (repo / "skillopt/execskill/a.py").write_text("A = 1\n")
    (repo / "skillopt/execskill/new.py").write_text("")
    with pytest.raises(ValueError, match="Files missing"):
        manifest.verify_code(pinned, repo)
    (repo / "skillopt/execskill/new.py").unlink()
    other = {**pinned, "environment": {**pinned["environment"], "openpyxl": "0.0"}}
    with pytest.raises(ValueError, match="openpyxl"):
        manifest.verify_code(other, repo)
    with pytest.raises(ConfigurationError, match="Files differ"):  # before a unit: a stop, not a value error
        (repo / "scripts/run_execskill.py").write_text("print(2)\n")
        manifest.verify_unit(pinned | {"sandbox": {"image_id": sandbox.IMAGE}}, docker=FakeDockerCLI(), repo=repo)


def test_the_real_tree_pins_every_loaded_module():
    loaded = manifest.loaded_code()
    assert manifest.COMMAND in loaded and "skillopt/execskill/manifest.py" in loaded
    assert "skillopt/execskill/sandbox/worker.py" in loaded and not loaded - set(manifest.pin_code())


# ------------------------------------------------------------------------------------------------------ T-MAN-2
def test_t_man_2_environment_fields_image_and_in_image_libraries():
    docker = FakeDockerCLI()
    found = manifest.environment(docker=docker, ping=lambda: dict(PING))
    assert set(found) == manifest.ENVIRONMENT_FIELDS
    assert found["image_digests"] == {"sandbox": sandbox.IMAGE} and found["docker"] == "27.3.1"
    assert found["in_image_libs"] == {k: PING[k] for k in manifest.IN_IMAGE_LIBS}
    assert found["python"] == sys.version.split()[0]
    assert ["docker", "image", "inspect", "--format", "{{.Id}}", sandbox.IMAGE] in docker.argvs
    for broken in (FakeDockerCLI(image="sha256:" + "f" * 64), FakeDockerCLI(image=""), FakeDockerCLI(binary=None)):
        with pytest.raises(ConfigurationError):
            manifest.environment(docker=broken, ping=lambda: dict(PING))
    with pytest.raises(ValueError, match="libraries"):
        manifest.environment(docker=FakeDockerCLI(), ping=lambda: {**PING, "sympy": None})


def test_make_seals_the_registered_fields_once_and_load_checks_them(tmp_path):
    out = tmp_path / "manifest.json"
    record = manifest.make(out, evidence="engineering_fixture", environment_found=fake_environment(),
                           measured=MEASURED, **given(tmp_path))
    assert set(record) == manifest.FIELDS and record["version"] == "fivebench-execskill-v1-manifest"
    assert record["evidence"] == "engineering_fixture" and read_json(out) == record
    assert record["sandbox"]["worker_sha256"] == sandbox.worker_sha256()
    assert record["templates"] == protocol.TEMPLATES_SHA256 and record["caps"]["G:solver"] > 0
    assert set(record["sandbox"]["limits"]) == set(sandbox.KINDS)
    assert manifest.load(out, verify=False) == record
    assert manifest.limits_of(record) == sandbox.LIMITS
    assert manifest.solver_config(record, "D", "officeqa") == {
        "env_path": str(tmp_path / "elucid.env"), "proxy": protocol.GATEWAY, "max_tokens": 8_192, "read_timeout": 600}
    assert manifest.solver_config(record, "G", "officeqa") == {"repo": str(tmp_path / "bigmodel-repo"),
                                                               "proxy": protocol.GATEWAY}
    with pytest.raises(ValueError):  # write-once
        manifest.make(out, evidence="engineering_fixture", environment_found=fake_environment(),
                      measured=MEASURED, **given(tmp_path))
    tampered = {**record, "root": "/elsewhere"}
    with pytest.raises(ValueError):
        manifest.check(tampered)
    with pytest.raises(ValueError, match="given fields"):
        manifest.make(tmp_path / "m2.json", evidence="smoke", environment_found=fake_environment(),
                      measured=MEASURED, **{k: v for k, v in given(tmp_path).items() if k != "fixtures"})
    limits = {**sandbox.LIMITS, "cell": replace(sandbox.CELL_LIMITS, pids=96)}
    second = manifest.make(tmp_path / "m3.json", evidence="smoke", environment_found=fake_environment(),
                           measured=MEASURED, limits=limits, **given(tmp_path))
    assert second["sandbox"]["docker_argv_template_sha"] != record["sandbox"]["docker_argv_template_sha"]


def test_clients_are_the_registered_ones(tmp_path):
    clients = given(tmp_path)["clients"]
    manifest.check_clients(clients)
    assert clients["solver"]["G"]["B"] == {b: 65_536 for b in protocol.BENCHES}
    assert clients["solver"]["D"]["B"]["searchqa"] == 2 * 8_192 and clients["solver"]["D"]["branch"] == "E"
    bad = [{**clients, "roles": {**manifest.ROLES, "max_tokens": 8_192}},
           {**clients, "solver": {"X": clients["solver"]["D"]}},
           {**clients, "solver": {"D": {**clients["solver"]["D"], "proxy": "http://other:3128"}}},
           {**clients, "solver": {"D": {**clients["solver"]["D"], "reasoning_effort": "low"}}},
           {**clients, "solver": {"G": {**clients["solver"]["G"], "branch": "E"}}},
           {**clients, "solver": {"D": {**clients["solver"]["D"], "B": {b: 16 for b in protocol.BENCHES}}}},
           {**clients, "solver": {"D": {**clients["solver"]["D"], "client_source_sha": "0" * 64}}}]
    for value in bad:
        with pytest.raises(ValueError):
            manifest.check_clients(value)
    longer = manifest.solver_block("D", env_path=tmp_path / "elucid.env", branch="N", longest=40_000)
    assert longer["B"]["searchqa"] == 60_000 and longer["B"]["spreadsheetbench"] == 65_536
    manifest.check_clients({**clients, "solver": {"D": longer}})
    assert longer["longest"] == 40_000 and clients["solver"]["D"]["longest"] is None


def test_safety_2_the_ledger_bound_equals_the_registered_derivation(tmp_path):
    """Safety review finding 2: B is re-derived from the block's branch and longest probe completion; a B that is
    only at least M, a branch-N block without its longest completion, or a block without the field is refused."""
    clients = given(tmp_path)["clients"]
    wide = clients["solver"]["D"]
    longer = manifest.solver_block("D", env_path=tmp_path / "elucid.env", branch="N", longest=40_000)
    bad = [{**wide, "B": dict(wide["M"])},
           {**wide, "B": {**wide["B"], "searchqa": wide["B"]["searchqa"] + 1}},
           {**wide, "longest": 40_000},
           {**longer, "longest": None},
           {**longer, "longest": 30_000},
           {key: value for key, value in wide.items() if key != "longest"}]
    for block in bad:
        with pytest.raises(ValueError):
            manifest.check_clients({**clients, "solver": {"D": block}})
    with pytest.raises(ValueError):
        manifest.check_clients({**clients, "solver": {"G": {**clients["solver"]["G"], "longest": 1}}})
    manifest.check_clients({**clients, "solver": {"D": longer, "G": clients["solver"]["G"]}})


# ------------------------------------------------------------------------------------------- pre-launch checks
def test_launch_env_unsets_the_openai_keys_and_disables_bytecode():
    env = prelaunch.launch_env({"OPENAI_API_KEY": "k", "OPENAI_BASE_URL": "u", "PATH": "/usr/bin"})
    assert env == {"PATH": "/usr/bin", "PYTHONDONTWRITEBYTECODE": "1"}


def test_verify_snapshot_compares_the_list_and_refuses_env_files(tmp_path):
    build, snapshot = tree(tmp_path / "build"), tree(tmp_path / "snapshot")
    (build / "tests").mkdir()
    (build / "tests/test_x.py").write_text("def test(): pass\n")
    (snapshot / "tests").mkdir()
    (snapshot / "tests/test_x.py").write_text("def test(): pass\n")
    (build / "skillopt/execskill/__pycache__").mkdir()
    (build / "skillopt/execskill/__pycache__/a.cpython-311.pyc").write_bytes(b"cache")
    listed = tmp_path / "sha256.list"
    listed.write_text(prelaunch.sha256_list(build))
    assert "__pycache__" not in listed.read_text() and "  tests/test_x.py\n" in listed.read_text()
    found = prelaunch.verify_snapshot(listed, root=snapshot, git_head=HEAD)
    assert set(found) == manifest.PROVENANCE_FIELDS and found["env_files_absent"] is True
    (snapshot / "scripts/run_execskill.py").write_text("print(3)\n")
    with pytest.raises(ValueError, match="differs from its sha256 list"):
        prelaunch.verify_snapshot(listed, root=snapshot, git_head=HEAD)
    (snapshot / "scripts/run_execskill.py").write_text("print(1)\n")
    (snapshot / "skillopt/.env.local").write_text("secret")
    listed.write_text(prelaunch.sha256_list(snapshot))
    with pytest.raises(ValueError, match=".env"):
        prelaunch.verify_snapshot(listed, root=snapshot, git_head=HEAD)


def test_zero_call_checks_run_the_registered_pytest_row(tmp_path, monkeypatch):
    root = tmp_path / "snapshot"
    (root / "tests").mkdir(parents=True)
    for name in ("test_execskill_a.py", "test_weak_solver_probe.py", "test_other.py"):
        (root / "tests" / name).write_text("")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic")
    seen = {}

    def run(command, **options):
        seen.update(command=command, env=options["env"], cwd=options["cwd"])
        return subprocess.CompletedProcess(command, 0, b"....\n12 passed in 0.50s\n")

    found = prelaunch.zero_call_checks(root, python="/py", run=run)
    assert found["passed"] and found["summary"] == "12 passed in 0.50s"
    assert seen["command"] == ["/py", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                               "tests/test_execskill_a.py", "tests/test_weak_solver_probe.py"]
    assert "OPENAI_API_KEY" not in seen["env"] and seen["env"]["PYTHONDONTWRITEBYTECODE"] == "1"
    failed = prelaunch.zero_call_checks(root, python="/py", run=lambda c, **o: subprocess.CompletedProcess(
        c, 1, b"1 failed, 11 passed in 0.60s\n"))
    assert not failed["passed"]


def test_leftovers_exclude_d3_d14_workers_by_command_line():
    d3 = (11, "python /data/feasibility/D3/r3/run.py --games 5")
    d14 = (12, "python -u /data/feasibility/D14/analyse.py")
    mine = (13, "python -B scripts/run_execskill.py run --manifest m --chain G")
    alf = (14, "python -m alfworld.agents.environment worker")
    other = (15, "/usr/sbin/sshd -D")
    clean = prelaunch.leftovers(found=[other], docker=FakeDockerCLI(), own=())
    assert clean["verdict"] == "clean" and clean["containers"] == []
    judged = prelaunch.leftovers(found=[d3, d14, other], docker=FakeDockerCLI(), own=())
    assert judged["verdict"] == "cannot_judge" and [e["pid"] for e in judged["excluded"]] == [11, 12]
    assert all(e["verdict"] == "cannot_judge" for e in judged["excluded"])
    for found in ([d3, mine], [d3, alf]):
        assert prelaunch.leftovers(found=found, docker=FakeDockerCLI(), own=())["verdict"] == "leftovers"
    assert prelaunch.leftovers(found=[mine], docker=FakeDockerCLI(), own=(13,))["verdict"] == "clean"
    boxed = prelaunch.leftovers(found=[], docker=FakeDockerCLI(containers=b"execskill-sbx-" + b"a" * 32), own=())
    assert boxed["verdict"] == "leftovers" and boxed["containers"] == ["execskill-sbx-" + "a" * 32]
    assert prelaunch.leftovers(found=[], docker=FakeDockerCLI(binary=None), own=())["verdict"] == "leftovers"


# ---------------------------------------------------------------------- the run adapters (A13-1, C2-1 §1, fixer-6)
def _refuse(request):
    raise AssertionError("no model call in an adapter test")


NO_CALLS = httpx.MockTransport(_refuse)


def _pinned(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items), encoding="utf-8")
    return {"path": str(path), "sha256": manifest._sha(path)}


def _items(tmp_path, bench, count):
    """Pool-shaped fixture items of ``bench`` (ALFWorld games carry their room, as the exported supply does)."""
    if bench == "spreadsheetbench":
        return spreadsheetbench_items(tmp_path / "sheets", count)
    if bench == "alfworld":
        games = alfworld_items(tmp_path / "games")
        return [{**item, "room": str(301 + n // 2)} for n, item in enumerate(games)][:count]
    return {"searchqa": searchqa_items, "officeqa": officeqa_items, "livemath": livemath_items}[bench](count)


def run_given(tmp_path, monkeypatch, *, root):
    """``given`` of a run on ``root`` with fake credentials, the pilot's pools, the research archive and the test-read
    estimate pinned; the slot and history roots under tmp_path."""
    monkeypatch.setattr(protocol, "SLOT_ROOT", str(tmp_path / "slots"))
    monkeypatch.setattr(protocol, "HISTORY_ROOT", str(tmp_path / "history"))
    elucid, glm = fake_config(tmp_path, protocol.CHAINS["D"]), fake_config(tmp_path, protocol.CHAINS["G"])
    archive = fake_research.archive_fixture(tmp_path / "archive")
    return {**given(tmp_path), "root": str(root),
            "clients": {"solver": {"D": manifest.solver_block("D", env_path=elucid["env_path"], branch="E"),
                                   "G": manifest.solver_block("G", env_path=glm["repo"])},
                        "roles": dict(manifest.ROLES)},
            "data": {"pools": {b: _pinned(tmp_path / "pools" / (b + ".json"), _items(tmp_path, b, 4))
                               for b in protocol.ORDER},
                     "research": {"archive": str(archive), "index_sha256": research.Archive(archive).index_sha256},
                     "test_read_estimate": {"G": 4_000_000, "D": 3_000_000},
                     "test_read_terms": {"G": read_terms(4_000_000), "D": read_terms(3_000_000)}}}


def read_terms(total):
    """Per-bench terms (``test-read-estimate``'s ``terms``, "p/q") whose sum is ``total`` (ticket P2C-2)."""
    return {bench: "%d/5" % total for bench in protocol.BENCHES}


def pilot(tmp_path, monkeypatch):
    return manifest.make(tmp_path / "manifest.json", evidence="engineering_fixture",
                         environment_found=fake_environment(), measured=MEASURED,
                         **run_given(tmp_path, monkeypatch, root=tmp_path / "run"))


def test_a10_1_the_manifest_binds_the_engineers_and_describers_prompt_hashes(tmp_path):
    record = manifest.make(tmp_path / "manifest.json", evidence="engineering_fixture",
                           environment_found=fake_environment(), measured=MEASURED, **given(tmp_path))
    assert record["prompt_sha"] == {"describer": describer.DESCRIBER_PROMPT_SHA256,
                                    "engineer": engineer.ENGINEER_PROMPT_SHA256,
                                    "examiner": examiner.PROMPT_SHA256} == manifest.prompt_sha()
    assert set(examiner.PROMPT_SHA256) == {"policy", "detectors", "generators"}
    unbound = protocol.record(manifest.KIND, "engineering_fixture", {
        **{k: v for k, v in record.items() if k not in ("version", "evidence", protocol.RECORD_HASH)},
        "prompt_sha": {"engineer": engineer.ENGINEER_PROMPT_SHA256}})
    with pytest.raises(ValueError, match="prompt"):
        manifest.check(unbound)


def test_row_12_the_manifest_refuses_card_hashes_in_place_of_the_card_texts(tmp_path):
    """Registrar addendum 14:10 row 12: ``cells.py`` hands ``cards[bench]`` to the solver as the card, so a manifest
    whose cards are hashes, miss a bench or are blank is refused before anything is written."""
    values = given(tmp_path)
    for cards in ({b: "4" * 64 for b in protocol.BENCHES}, {b: CARDS[b] for b in list(CARDS)[1:]},
                  {**CARDS, "searchqa": "  "}):
        with pytest.raises(ValueError, match="card texts"):
            manifest.make(tmp_path / "m.json", evidence="engineering_fixture", environment_found=fake_environment(),
                          measured=MEASURED, **{**values, "cards": cards})
        assert not (tmp_path / "m.json").exists()
    made = manifest.make(tmp_path / "m.json", evidence="engineering_fixture", environment_found=fake_environment(),
                         measured=MEASURED, **values)
    assert made["cards"] == CARDS and all(c["sha"] == hashlib.sha256(c["text"].encode()).hexdigest()
                                          for c in made["contracts"].values())


def test_a13_1_setting_of_builds_each_chains_setting_from_the_verified_manifest(tmp_path, monkeypatch):
    m, docker, path = pilot(tmp_path, monkeypatch), FakeDockerCLI(), tmp_path / "manifest.json"
    root = safe_path(m["root"])
    for chain in ("G", "D"):
        setting = manifest.setting_of(m, chain, path=path, docker=docker, transport=NO_CALLS)
        assert setting.run == m[protocol.RECORD_HASH] and setting.root == root and setting.evidence == m["evidence"]
        assert setting.budget.root == budgets.ledger_root(root, chain) and setting.budget.snapshot() == {}
        assert list(setting.pools) == list(protocol.ORDER)
        assert [i["task_id"] for i in setting.pools["officeqa"]] == [
            i["task_id"] for i in supply.order("officeqa", officeqa_items(4))]
        assert setting.sandbox == {"docker": docker, "limits": manifest.limits_of(m), "image": sandbox.IMAGE}
        assert set(setting.extra) == {"verify", "drain", "slot_root", "manifest", "test_read_estimate",
                                      "test_read_terms", "configuration"} | ({"route"} if chain == "D" else set())
        assert setting.extra["configuration"] == m["configuration"] == protocol.PILOT  # registrar 17:0x (M1)
        assert setting.extra["manifest"] == str(safe_path(path)) and setting.extra["slot_root"] == m["slot_root"]
        assert setting.extra["test_read_estimate"] == {chain: m["data"]["test_read_estimate"][chain]}
        assert setting.extra["test_read_terms"] == {chain: m["data"]["test_read_terms"][chain]}
        assert setting.extra["drain"].func is sandbox.drain_unit
        assert setting.extra["drain"].keywords == {"docker": docker}
        assert set(setting.slots) == set(slots.POOL_SIZES) and setting.slots[slots.NATIVE].count == 3
        block = m["clients"]["solver"][chain]
        assert (setting.branch, setting.longest) == (block["branch"], block["longest"])
        manifest._safety(setting, block)
    d = manifest.setting_of(m, "D", docker=docker, transport=NO_CALLS)
    solver = d.clients(protocol.CHAINS["D"], "officeqa")
    assert solver.model == protocol.CHAINS["D"] and solver.max_tokens == 8_192
    assert d.clients(protocol.CHAINS["D"], "officeqa") is solver and "manifest" not in d.extra
    role = d.clients(protocol.ROLE_MODEL, None)
    assert role.model == "glm-5.3" and role.max_tokens == protocol.ROLE_MAX_TOKENS == 16_384
    assert role.http.timeout.read == protocol.ROLE_READ_TIMEOUT
    with pytest.raises(ValueError):
        d.clients(protocol.CHAINS["G"], "officeqa")  # not chain D's solver


def main_given(tmp_path, monkeypatch):
    """``given`` of a ``main`` run (registrar "Owner instructions 2026-10-22 17:0x and 17:3x"): the pools of all five
    benches, the SearchQA tail pin with the bound SearchQA exclusion record, chain D's route-B pin."""
    from skillopt.execskill import routes

    values = run_given(tmp_path, monkeypatch, root=tmp_path / "main-run")
    tail = _pinned(tmp_path / "history" / "supply" / "searchqa-tail.json", searchqa_items(3))
    _, searchqa_run = protocol.EXCLUSION_RUNS
    bound = {searchqa_run: {"path": str(tmp_path / "exclusion.json"), "record_sha256": "8" * 64}}
    clients = values["clients"]
    route_env = tmp_path / "route-b.env"
    route_env.write_text("synthetic, never read\n")
    clients = {**clients, "routes": {"D": {"B": routes.pin("D", "B", env_path=route_env,
                                                           solver_block=clients["solver"]["D"])}}}
    data = {**values["data"], "pools": {b: _pinned(tmp_path / "pools" / (b + ".json"), _items(tmp_path, b, 4))
                                        for b in protocol.BENCHES},
            "searchqa_tail": tail, "exclusion": bound}
    return {**values, "data": data, "clients": clients}


def test_m1_a_main_manifest_carries_its_configuration_to_every_consumer(tmp_path, monkeypatch):
    """Registrar 17:0x: ``configuration`` is a manifest field stamped with its caps; the Setting carries it
    (``protocol.configuration_of`` / ``order_of``), the pools follow main's five-bench order, chains G and D get the
    SearchQA tail pin with the bound exclusion record, and a real run's evidence label must be its configuration's."""
    values, docker = main_given(tmp_path, monkeypatch), FakeDockerCLI()
    options = {"environment_found": fake_environment(), "measured": MEASURED}
    m = manifest.make(tmp_path / "main.json", evidence="engineering_fixture", configuration=protocol.MAIN,
                      **options, **values)
    assert m["configuration"] == "main" and m["caps"] == budgets.caps("main") != budgets.caps()
    assert m["caps"]["G:solver"] == protocol.PILOTS["main"]["solver_cap"] == 1_520_000_000
    for chain in ("G", "D"):
        setting = manifest.setting_of(m, chain, docker=docker, transport=NO_CALLS)
        assert protocol.configuration_of(setting) == "main" and protocol.order_of(setting) == protocol.BENCHES
        assert list(setting.pools) == list(protocol.BENCHES)
        assert setting.extra["searchqa_tail"] == {**values["data"]["searchqa_tail"],
                                                  "exclusion": values["data"]["exclusion"]["searchqa_test_exclusion"]}
    untailed = {**m, "data": {k: v for k, v in m["data"].items() if k != "searchqa_tail"}}
    with pytest.raises(ValueError, match="SearchQA tail"):
        manifest.setting_of(untailed, "G", docker=docker, transport=NO_CALLS)
    short = {**m, "data": {**m["data"], "pools": {b: m["data"]["pools"][b] for b in protocol.ORDER}}}
    with pytest.raises(ValueError, match="configuration's order"):  # main's pools: all five benches
        manifest.setting_of(short, "G", docker=docker, transport=NO_CALLS)
    # a fixture Setting without the field is the default configuration
    assert protocol.configuration_of(SimpleNamespace(extra={})) == protocol.PILOT == "default"
    with pytest.raises(ValueError, match="Unknown run configuration"):
        protocol.configuration_of(SimpleNamespace(extra={"configuration": "pilot"}))
    # refusals, before anything is written
    for evidence, configuration in (("main_real_run", "default"), ("pilot_real_run", "main")):
        with pytest.raises(ValueError, match="evidence label"):
            manifest.make(tmp_path / "refused.json", evidence=evidence, configuration=configuration, **options,
                          **(values if configuration == "main" else run_given(tmp_path, monkeypatch,
                                                                              root=tmp_path / "run")))
    with pytest.raises(ValueError, match="Unknown run configuration"):
        manifest.make(tmp_path / "refused.json", evidence="engineering_fixture", configuration="pilot", **options,
                      **values)
    assert not (tmp_path / "refused.json").exists()
    fields = {k: v for k, v in m.items() if k not in ("version", "evidence", protocol.RECORD_HASH)}
    with pytest.raises(ValueError, match="carries its caps"):  # main's name with the pilot's caps
        manifest.check(protocol.record(manifest.KIND, "engineering_fixture", {**fields, "caps": budgets.caps()}))
    real = manifest.make(tmp_path / "main-real.json", evidence="main_real_run", configuration="main", **options,
                         **values)
    assert real["evidence"] == "main_real_run" and manifest.check(real) == real


def test_fixer_6_setting_of_refuses_a_broken_invariant_or_a_changed_pin(tmp_path, monkeypatch):
    m, docker = pilot(tmp_path, monkeypatch), FakeDockerCLI()
    setting, block = manifest.setting_of(m, "D", docker=docker), m["clients"]["solver"]["D"]
    foreign = slots.pools(tmp_path / "other-slots")
    for broken in (replace(setting, branch="N", longest=40_000), replace(setting, longest=1),
                   replace(setting, slots={**setting.slots, slots.CALL: foreign[slots.CALL]}),
                   replace(setting, slots={k: v for k, v in setting.slots.items() if k != slots.NATIVE})):
        with pytest.raises(ValueError):
            manifest._safety(broken, block)
    with pytest.raises(ValueError, match="smoke"):
        manifest.setting_of(m, budgets.SMOKE, docker=docker)  # a pilot manifest never runs the smoke
    with pytest.raises(ValueError, match="Chain G, chain D or the smoke"):
        manifest.setting_of(m, "X", docker=docker)
    unpinned = {**m, "data": {k: v for k, v in m["data"].items() if k != "test_read_estimate"}}
    with pytest.raises(ValueError, match="test-read estimate"):
        manifest.setting_of(unpinned, "G", docker=docker)
    with pytest.raises(ValueError, match="prompt"):
        manifest.setting_of({**m, "prompt_sha": {**m["prompt_sha"], "engineer": "0" * 64}}, "G", docker=docker)
    with open(m["data"]["pools"]["officeqa"]["path"], "a", encoding="utf-8") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="differs from its pin"):
        manifest.setting_of(m, "G", docker=docker)



def test_p2c_2_setting_of_needs_each_chains_per_bench_terms_of_its_estimate(tmp_path, monkeypatch):
    """Registrar addendum 2026-10-22 15:3x, ticket P2C-2: a chain's Setting carries the exact per-bench terms of its
    test-read estimate (``data.test_read_terms[chain]``, as ``test-read-estimate`` records them), refused when
    missing, of another estimate, incomplete or not positive."""
    m, docker = pilot(tmp_path, monkeypatch), FakeDockerCLI()
    assert manifest.setting_of(m, "G", docker=docker).extra["test_read_terms"] == {"G": read_terms(4_000_000)}
    near = {**read_terms(4_000_000), "alfworld": "3999999/5"}  # the sum still rounds up to the estimate
    for terms, ok in ((read_terms(4_000_000), True), (near, True), (None, False), (read_terms(3_000_000), False),
                      ({**read_terms(4_000_000), "alfworld": "0/1"}, False),
                      ({b: t for b, t in read_terms(4_000_000).items() if b != "alfworld"}, False),
                      ({**read_terms(4_000_000), "alfworld": 800_000}, False),
                      ({**read_terms(4_000_000), "alfworld": "x/0"}, False)):
        changed = {**m, "data": {**m["data"], "test_read_terms": {**m["data"]["test_read_terms"], "G": terms}}}
        if ok:
            assert manifest.setting_of(changed, "G", docker=docker).extra["test_read_terms"] == {"G": terms}
        else:
            with pytest.raises(ValueError, match="per-bench terms"):
                manifest.setting_of(changed, "G", docker=docker)
    unpinned = {**m, "data": {k: v for k, v in m["data"].items() if k != "test_read_terms"}}
    with pytest.raises(ValueError, match="per-bench terms"):
        manifest.setting_of(unpinned, "D", docker=docker)


def test_a13_1_native_slots_drop_to_two_above_two_gib_native_peak(tmp_path, monkeypatch):
    high = manifest.make(tmp_path / "manifest.json", evidence="engineering_fixture",
                         environment_found=fake_environment(), measured={**MEASURED, "native_peak_rss_kib": 3 << 20},
                         **run_given(tmp_path, monkeypatch, root=tmp_path / "run"))
    found = manifest.setting_of(high, "G", docker=FakeDockerCLI())
    assert found.slots[slots.NATIVE].count == protocol.NATIVE_SLOTS_LOW_MEMORY == 2


def test_a13_1_services_of_binds_the_registry_research_and_the_settings_workers(tmp_path, monkeypatch):
    m, docker = pilot(tmp_path, monkeypatch), FakeDockerCLI()
    setting = manifest.setting_of(m, "G", docker=docker)
    services = manifest.services_of(m, "G", setting=setting, transport=NO_CALLS)
    engine = services.engine  # tickets C6-1, PR-C61-1: the production SpreadsheetBench engines, building nothing
    assert isinstance(services, step.Services) and isinstance(engine, sheet.Engine)
    # tickets C6-1, C7d-2: LiveMath's checker over the Services' own worker factory; making it started nothing
    assert isinstance(services.checker, livemath.WorkerChecker) and services.checker.workers is services.workers
    assert {argv[1] for argv in docker.argvs} <= {"image", "version", "ps"}
    assert engine.native is setting.slots[slots.NATIVE] and engine.runtime == m["runtime"]["spreadsheetbench"]
    assert engine.qualify.func is qualify.qualify and engine.qualify.keywords == {"evidence": m["evidence"]}
    assert services.registry.root == safe_path(tmp_path / "history") and services.registry.evidence == m["evidence"]
    assert services.sources.store == safe_path(m["root"]) / "shared" / "research" / "G" / "sources"
    assert services.sources.archive.index_sha256 == m["data"]["research"]["index_sha256"]
    assert services.workers.func is sandbox.with_worker
    assert services.workers.keywords == {**setting.sandbox, "live": setting.slots[slots.LIVE],
                                         "per_call": setting.slots[slots.CALL]}
    moved = {**m, "data": {**m["data"], "research": {**m["data"]["research"], "index_sha256": "0" * 64}}}
    with pytest.raises(ValueError, match="research archive"):
        manifest.services_of(moved, "G", setting=setting)


def test_c7d_2_the_livemath_checker_follows_the_units_tag_bound_workers(tmp_path, monkeypatch):
    """Ticket C7d-2 (C5-1): ``step._Step.unit`` re-binds ``Services.workers`` to the running unit's tag with
    ``dataclasses.replace``; the checker of the new instance is made from those tag-bound workers, so its containers
    carry the unit's tag. A fake checker given explicitly is kept."""
    m, docker = pilot(tmp_path, monkeypatch), FakeDockerCLI()
    setting = manifest.setting_of(m, "G", docker=docker)
    services = manifest.services_of(m, "G", setting=setting, transport=NO_CALLS)
    tag = sandbox.unit_tag("G", "G/s1-livemath/generate")
    bound = replace(services, workers=functools.partial(services.workers, tag=tag))  # as step._Step.unit does
    assert isinstance(bound, manifest.Services) and bound.checker is not services.checker
    assert bound.checker.workers is bound.workers and bound.checker.workers.keywords["tag"] == tag
    assert services.checker.workers is services.workers  # the step restores the Services it was given
    fake = object()
    assert replace(services, checker=fake).checker is fake
    assert replace(replace(services, checker=fake), workers=bound.workers).checker is fake

    with pytest.raises(ValueError, match="Setting of this manifest"):
        manifest.services_of(m, "G", setting=replace(setting, run="another-run"))


class _CountingWorker:
    """A started generator worker that answers every checker call (zero containers)."""

    def __init__(self, kind, tag):
        self.kind, self.tag, self.calls = kind, tag, []

    def call(self, entry, method, args, *, timeout_s):
        self.calls.append((entry, method, args[0]["op"]))
        return {"ok": True, "value": {"exact": "1", "digits": "1"}}


def test_i1_2_a_livemath_build_holds_one_checker_session_on_the_units_workers(tmp_path, monkeypatch):
    """Ticket I1-2 (registrar addenda 14:3x row C7d-2, 14:4x): ``step._build`` holds ONE checker session around
    ``examiner.build`` on LiveMath, so every solve of the build shares one generator worker opened from the unit's
    tag-bound workers, closed after the build; another bench, or a checker without sessions, opens none."""
    opened = []

    @contextmanager
    def workers(package, *, kind, hashseed=0, inputs_dir=None, tag=None):
        worker = _CountingWorker(kind, tag)
        opened.append(worker)
        yield worker

    checker = livemath.WorkerChecker(functools.partial(workers, tag="unit-tag"))  # as _Step.unit binds them
    during = []

    def build(specs, materials, **given):
        during.append((given["checker"] is checker, checker._worker is not None))
        return [given["checker"].solve(spec) for spec in specs]

    monkeypatch.setattr(examiner, "build", build)
    st = SimpleNamespace(bench="livemath", k=1, name="G/s1-livemath", evidence="engineering_fixture",
                         services=SimpleNamespace(checker=checker, engine=None))
    specs = [{"op": "derivative"}, {"op": "integral"}, {"op": "binomial"}]
    assert len(step._build(st, specs, [], "G_self", None, tmp_path, 0)) == 3
    assert during == [(True, True)] and checker._worker is None  # the session spans the build and is closed after
    assert [(w.kind, w.tag, len(w.calls)) for w in opened] == [("generator", "unit-tag", 3)]
    assert [entry["op"] for entry in checker.solved] == ["derivative", "integral", "binomial"]
    opened.clear()
    step._build(SimpleNamespace(**{**vars(st), "bench": "officeqa"}), [], [], "G_self", None, tmp_path, 0)
    assert opened == [] and during[-1] == (True, False)  # another bench: no session
    fake = SimpleNamespace(solve=lambda spec: {"ok": True})  # a checker without sessions (a test fake): no session
    st.services = SimpleNamespace(checker=fake, engine=None)
    monkeypatch.setattr(examiner, "build", lambda specs, materials, **given: [given["checker"].solve(s) for s in specs])
    assert step._build(st, specs, [], "G_self", None, tmp_path, 0) == [{"ok": True}] * 3 and opened == []


def smoke_spec(tmp_path, root, *, limits=None):
    """The smoke's sealed specification on ``root`` over pool-shaped item files and a passing S0 self-test whose
    measurements are ``MEASURED``'s (plus the start latency and view count the manifest does not carry)."""
    sets = {b: _pinned(tmp_path / "smoke-items" / (b + ".json"), _items(tmp_path, b, 3))["path"]
            for b in smoke.ITEM_SETS}
    tested = tmp_path / "s0" / smoke.SELFTEST
    write_json(tested, protocol.record("sandbox-selftest", "smoke", {
        "escape_rows": {row: True for row in smoke.ESCAPE_ROWS}, "escape_probe_sha256": "0" * 64,
        "worker_sha256": "1" * 64, "image": sandbox.IMAGE,
        "limits": {k: asdict(v) for k, v in sorted((limits or sandbox.LIMITS).items())},
        "measured": {**{k: MEASURED[k] for k in ("vsz_kib", "rss_kib", "view_bytes_p99")}, "start_seconds": 2.6,
                     "views": 15}, "passed": True}))
    return smoke.make(root, items=sets, control_cells=["fx-drill-1"], noise_anchor={"searchqa": 0.21, "alfworld": 0.3},
                      selftest=str(tested), environment_found=fake_environment())


def test_a13_1_a_smoke_manifest_runs_the_smoke_on_its_ledger_with_chain_ds_solver(tmp_path, monkeypatch):
    root = tmp_path / "smoke"
    values = run_given(tmp_path, monkeypatch, root=root)
    values["data"] = {"research": values["data"]["research"]}
    smoke_spec(tmp_path, root)
    m = manifest.make(tmp_path / "smoke-manifest.json", evidence=manifest.SMOKE_EVIDENCE,
                      environment_found=fake_environment(), measured=MEASURED, **values)
    setting = manifest.setting_of(m, budgets.SMOKE, docker=FakeDockerCLI(), transport=NO_CALLS)
    assert setting.evidence == "smoke" and list(setting.pools) == sorted(smoke.ITEM_SETS)
    assert setting.budget.root == safe_path(root) / "shared" / "ledger"
    assert {scope: value["cap"] for scope, value in setting.budget.snapshot().items()} == budgets.smoke_caps()
    assert (setting.branch, setting.longest) == ("E", None) and "test_read_estimate" not in setting.extra
    assert setting.clients(protocol.SMOKE_SOLVER, "searchqa").max_tokens == protocol.solver_tokens(
        protocol.SMOKE_SOLVER, "searchqa")
    assert setting.clients(protocol.ROLE_MODEL, None).max_tokens == protocol.ROLE_MAX_TOKENS
    services = manifest.services_of(m, budgets.SMOKE, setting=setting, transport=NO_CALLS)
    assert services.registry.evidence == "smoke" and services.sources.store.parent.name == budgets.SMOKE
    for chain in ("G", "D"):
        with pytest.raises(ValueError, match="smoke"):
            manifest.setting_of(m, chain, docker=FakeDockerCLI())
    limits = {**sandbox.LIMITS, "cell": replace(sandbox.CELL_LIMITS, pids=96)}
    wider = manifest.make(tmp_path / "wider.json", evidence=manifest.SMOKE_EVIDENCE, limits=limits,
                          environment_found=fake_environment(), measured=MEASURED, **values)
    with pytest.raises(ValueError, match="S0 limits"):
        manifest.setting_of(wider, budgets.SMOKE, docker=FakeDockerCLI())
    other = manifest.make(tmp_path / "other.json", evidence=manifest.SMOKE_EVIDENCE,
                          environment_found=fake_environment(),
                          measured={**MEASURED, "rss_kib": MEASURED["rss_kib"] + 1}, **values)
    with pytest.raises(ValueError, match="S0 limits"):
        manifest.setting_of(other, budgets.SMOKE, docker=FakeDockerCLI())
