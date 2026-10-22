"""The route-B sandbox through FakeDocker (implementation plan §8: T-SBX-1..13; registration §2.6, §4.4 P1/P4;
plan §4; safety review findings 3-5 as the registrar decided them on 2026-10-22). Every test runs the real worker.py in
local subprocesses through the real client: no docker, no network, only engineering-fixture procedures; the process
group and prctl tests run ``worker.run_call`` in a fork of the test process on test-written code. The pinned container
itself is exercised in the S0 smoke on dl."""
from __future__ import annotations

import ast
import ctypes  # noqa: F401 -- loaded before a forked test process drops to uid 65534 (no venv access then)
import json
import os
import signal
import sys
import textwrap
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import openpyxl
import pytest

from skillopt.execskill import package as pkg
from skillopt.execskill import policy, slots
from skillopt.execskill.errors import CleanupUnconfirmed, ConfigurationError, SandboxUnavailable
from skillopt.execskill.sandbox import client, worker
from skillopt.execskill.sandbox.client import Limits, Worker, cleanup, docker_command, drain_check, with_worker
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_docker import FakeDocker

TEST_LIMITS = {kind: Limits(pids=64, memory_mb=768, cpus=0.5, address_space_mb=512, frame_bytes=1 << 20)
               for kind in client.KINDS}
VIEW = {"text": "a table\nwith two rows"}
NOTE = """
def applies(view):
    return "table" in view["text"]

def before_call(view, state):
    return {"facts": ["lines: %d" % len(view["text"].splitlines())]}
"""
CRASH = """
def applies(view):
    return True

def before_call(view, state):
    return {"facts": [str(1 / 0)]}
"""
LOOP = """
def before_call(view, state):
    total = 0
    while True:
        total += 1
"""
OOM = """
def before_call(view, state):
    block = bytearray(view["bytes"])
    return {"facts": [str(len(block))]}
"""
OUTPUTS = """
def nan(view, state):
    return {"x": float("nan")}

def a_set(view, state):
    return {"facts": {"a"}}

def int_key(view, state):
    return {1: "a"}

def surrogate(view, state):
    return "\\ud800"

def big(view, state):
    return {"facts": ["x" * view["n"]]}

def nested(view, state):
    value = []
    for _ in range(40):
        value = [value]
    return value

def deep_ok(view, state):
    value = []
    for _ in range(31):
        value = [value]
    return value
"""
PRINTS = """
import calendar

def before_call(view, state):
    calendar.prmonth(2026, 10)
    return {"facts": ["printed"]}
"""
MODULE_LOOP = """
def helper(count=sum(1 for _ in iter(int, 1))):
    return count

def applies(view):
    return True
"""
STATE = """
import json

SEEN = []

def before_call(view, state):
    SEEN.append(len(SEEN))
    try:
        marker = json.marker
    except AttributeError:
        marker = 0
    json.marker = marker + 1
    return {"facts": [str(len(SEEN)), str(marker)], "state": state}
"""
ORDER = """
WORDS = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]

def deterministic(view, state):
    return {"facts": sorted(set(WORDS))}

def nondeterministic(view, state):
    return {"facts": list(set(WORDS))}
"""
WORKBOOK = """
def before_call(view, state):
    sheet = public_workbook()["sheets"][0]
    cells = sheet["cells"]
    return {"facts": [sheet["name"], str(cells["A1"]["value"]), str(cells["B1"]["formula"]), str(cells["B1"]["value"])]}
"""
BANNED = """
import os

def applies(view):
    return True
"""
FIXTURES = {"fx-note": (NOTE, ("applies", "before_call")), "fx-crash": (CRASH, ("applies", "before_call")),
            "fx-loop": (LOOP, ("before_call",)), "fx-oom": (OOM, ("before_call",)),
            "fx-outputs": (OUTPUTS, ("nan", "a_set", "int_key", "surrogate", "big", "nested", "deep_ok")),
            "fx-print": (PRINTS, ("before_call",)), "fx-module-loop": (MODULE_LOOP, ("applies",)),
            "fx-state": (STATE, ("before_call",)), "fx-order": (ORDER, ("deterministic", "nondeterministic")),
            "fx-workbook": (WORKBOOK, ("before_call",)), "fx-banned": (BANNED, ("applies",))}


def source(text):
    return textwrap.dedent(text).lstrip()


def bundle(*ids):
    """A detector/generator-style bundle (``sha256`` + ``procedures`` with id, source, hooks) of fixtures."""
    procedures = tuple(SimpleNamespace(id=i, source=source(FIXTURES[i][0]), hooks=FIXTURES[i][1]) for i in ids)
    return SimpleNamespace(sha256=digest([[p.id, p.source, list(p.hooks)] for p in procedures]), procedures=procedures)


def in_thread(function):
    out = {}
    thread = threading.Thread(target=lambda: out.update(result=function()))
    thread.start()
    return thread, out


@pytest.fixture
def fake(tmp_path):
    docker = FakeDocker(tmp_path / "containers")
    yield docker
    docker.close()


@pytest.fixture
def make(fake, tmp_path):
    workers = []

    def factory(package, *, kind="cell", inputs_dir=None, **options):
        options = {"docker": fake, "limits": TEST_LIMITS, "scratch": tmp_path, **options}
        workers.append(Worker(**options).start(package, kind=kind, inputs_dir=inputs_dir))
        return workers[-1]

    yield factory
    for item in workers:
        try:
            item.close()
        except CleanupUnconfirmed:
            pass  # asserted by the test that made it unconfirmable


def test_fixture_sources_pass_the_host_policy_except_the_banned_one():
    assert {i for i, (text, _) in FIXTURES.items() if policy.check(source(text))} == {"fx-banned"}


def test_sbx01_load_call_ping_with_lazy_start(fake, make):
    procedure = pkg.Procedure(id="fx-note", origin="officeqa", description="Counts the lines of a table view.",
                              hooks=("applies", "before_call"), source=source(NOTE), evidence="engineering_fixture",
                              max_note_chars=200)
    real = make(pkg.Package((procedure,), "fixture", "engineering_fixture"))
    assert fake.argvs == [] and real.names == []  # lazy: nothing runs before the first call
    result = real.call("fx-note", "before_call", [VIEW, {}], timeout_s=5)
    value = {"facts": ["lines: 2"]}
    assert result == {"ok": True, "value": value, "value_sha256": digest(value), "cpu_ms": result["cpu_ms"],
                      "rss_kib": result["rss_kib"]}
    assert type(result["cpu_ms"]) is int and result["rss_kib"] > 0
    assert real.call("fx-note", "applies", [VIEW], timeout_s=2)["value"] is True
    assert len(fake.argvs) == 1 and real.names == [fake.argvs[0][fake.argvs[0].index("--name") + 1]]
    ping = real.ping()
    assert ping["worker"] == worker.WORKER_PROTOCOL and ping["worker_sha256"] == client.worker_sha256()
    assert ping["hashseed"] == "0" and ping["python"] == "%d.%d.%d" % sys.version_info[:3]
    assert ping["policy_sha256"] == policy.policy_sha256() and set(worker.LIBRARIES) <= set(ping)
    assert ping["openpyxl"] == openpyxl.__version__ and ping["vsz_kib"] > 0
    assert real.call("fx-note", "after_step", [VIEW], timeout_s=2)["fault"] == "undeclared"
    assert real.call("fx-other", "applies", [VIEW], timeout_s=2)["fault"] == "not_loaded"

    checked = make(bundle("fx-note", "fx-banned"))
    assert checked.call("fx-banned", "applies", [VIEW], timeout_s=2) == {
        "ok": False, "fault": "not_loaded", "exc_type": None, "line": None,
        "message": "rejected inside the sandbox: policy:import"}
    assert checked.rejected == {"fx-banned": "policy:import"}

    name = real.names[0]
    real.close()
    real.close()  # idempotent
    assert name not in fake.containers and fake.commands[-1] == ["ps", "-a", "--filter", "name=^/%s$" % name,
                                                                 "--format", "{{.Names}}"]
    with pytest.raises(ValueError):
        real.call("fx-note", "applies", [VIEW], timeout_s=2)


def test_sbx01_docker_argv_copies_the_frozen_hardening_and_runs_with_path_only(tmp_path, monkeypatch):
    argv = docker_command("cell", None, {"runner": "/r", "input": "/i"}, name="execskill-sbx-" + "0" * 32)
    frozen = ("--pull=never", "--network=none", "--read-only", "--user=65534:65534", "--cap-drop=ALL",
              "--security-opt=no-new-privileges=true", "--memory=768m", "--memory-swap=768m", "--ipc=private",
              "--no-healthcheck", "--log-driver=none", "--ulimit=core=0:0", "--workdir=/tmp", "--entrypoint=python")
    assert set(frozen) <= set(argv) and argv[:3] == ["docker", "run", "-i"]  # backends.py:169-178, plan §4
    assert argv[-5:] == [client.IMAGE, "-s", "-B", "-P", "/runner/worker.py"]
    assert {"--pids-limit=64", "--cpus=0.5", "--shm-size=16m", "--ulimit=nofile=64:64",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m"} <= set(argv)
    assert argv[argv.index("type=bind,source=/i,target=/input,readonly") - 1] == "--mount"
    assert argv[argv.index("type=bind,source=/r,target=/runner,readonly") - 1] == "--mount"
    assert "--memory=1024m" in docker_command("generator", None, {"runner": "/r"}, name="n")
    assert "<0|1>" in " ".join(client.argv_template("cell"))
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key-not-a-secret")
    binary = tmp_path / "bin" / "docker"
    binary.parent.mkdir()
    binary.write_text("#!%s\nimport json, os\nprint(json.dumps(sorted(os.environ)))\n" % sys.executable)
    binary.chmod(0o755)
    docker = client.Docker(path=str(binary.parent))
    keys = json.loads(docker.run([docker.binary], 10).stdout)
    assert "PATH" in keys and set(keys) <= {"PATH", "LC_CTYPE"}  # LC_CTYPE: python's own C-locale coercion
    spawned = docker.spawn([docker.binary])
    assert set(json.loads(spawned.communicate(timeout=10)[0])) == set(keys)
    assert client.Docker(path=str(tmp_path)).binary is None


def test_sbx02_timeout_and_exception_are_procedure_faults(make):
    sandbox = make(bundle("fx-loop", "fx-crash", "fx-note"))
    started = time.monotonic()
    assert sandbox.call("fx-loop", "before_call", [VIEW, {}], timeout_s=1)["fault"] == "timeout"
    assert time.monotonic() - started < 8
    assert sandbox.call("fx-crash", "before_call", [VIEW, {}], timeout_s=5) == {
        "ok": False, "fault": "exception", "exc_type": "ZeroDivisionError", "message": "division by zero",
        "line": 5}
    assert sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)["value"] is True
    assert len(sandbox.names) == 1 and sandbox.dropped == []  # P1: the same container keeps serving


def test_sbx03_memory_limit_is_a_procedure_fault(make):
    sandbox = make(bundle("fx-oom"))
    result = sandbox.call("fx-oom", "before_call", [{"bytes": 1 << 30}, {}], timeout_s=5)  # over RLIMIT_AS 512 MiB
    assert (result["fault"], result["exc_type"], result["line"]) == ("memory", "MemoryError", 2)
    assert sandbox.call("fx-oom", "before_call", [{"bytes": 1 << 20}, {}], timeout_s=5)["value"] == {
        "facts": [str(1 << 20)]}


def test_sbx04_values_that_are_not_canonical_json_are_output_faults(make):
    sandbox = make(bundle("fx-outputs"))
    for fn in ("nan", "a_set", "int_key", "surrogate"):
        assert sandbox.call("fx-outputs", fn, [VIEW, {}], timeout_s=5)["fault"] == "output", fn
    assert len(sandbox.names) == 1


def test_sbx05_size_and_nesting_caps(fake, make):
    sandbox = make(bundle("fx-outputs"))
    assert sandbox.call("fx-outputs", "big", [{"n": 2 << 20}, {}], timeout_s=10)["fault"] == "over_cap"
    assert sandbox.call("fx-outputs", "nested", [VIEW, {}], timeout_s=5)["fault"] == "over_cap"
    assert sandbox.call("fx-outputs", "deep_ok", [VIEW, {}], timeout_s=5)["ok"] is True
    assert sandbox.call("fx-outputs", "big", [{"n": 1000}, {}], timeout_s=5)["ok"] is True
    fresh = make(bundle("fx-outputs"))
    assert fresh.call("fx-outputs", "big", [{"n": 1, "pad": "x" * (2 << 20)}, {}], timeout_s=5)["fault"] == "over_cap"
    assert fresh.names == []  # refused on the host: the frame never left
    with pytest.raises(ConfigurationError):
        fresh.call("fx-outputs", "big", [{"n": float("nan")}, {}], timeout_s=5)


def test_sbx06_printing_never_reaches_the_frame_stream_or_stderr(fake, make):
    sandbox = make(bundle("fx-print", "fx-note"))
    assert sandbox.call("fx-print", "before_call", [VIEW, {}], timeout_s=5)["value"] == {"facts": ["printed"]}
    assert sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)["value"] is True  # frames still aligned
    container = fake.containers[sandbox.names[0]]
    sandbox.close()
    assert b"October 2026" not in container.stderr  # the child's fds 0/1/2 were /dev/null


def test_sbx07_module_level_loop_times_out_per_call_and_load_executes_nothing(make):
    sandbox = make(bundle("fx-module-loop", "fx-note"))
    assert sandbox.call("fx-module-loop", "applies", [VIEW], timeout_s=1)["fault"] == "timeout"
    assert sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)["value"] is True
    assert sandbox.call("fx-module-loop", "applies", [VIEW], timeout_s=1)["fault"] == "timeout"
    assert len(sandbox.names) == 1


def test_sbx08_killed_child_and_killed_worker_are_procedure_faults(fake, make):
    sandbox = make(bundle("fx-loop", "fx-note"))
    assert sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)["ok"]
    first = sandbox.names[0]
    thread, out = in_thread(lambda: sandbox.call("fx-loop", "before_call", [VIEW, {}], timeout_s=60))
    fake.kill_child(first)
    thread.join(30)
    assert out["result"]["fault"] == "killed" and "signal 9" in out["result"]["message"]
    assert sandbox.names == [first] and sandbox.dropped == []  # the container survives a killed child

    thread, out = in_thread(lambda: sandbox.call("fx-loop", "before_call", [VIEW, {}], timeout_s=60))
    fake.children(first)
    fake.kill_worker(first)
    thread.join(30)
    assert out["result"]["fault"] == "worker" and "end of file" in out["result"]["message"]
    assert sandbox.dropped == ["fx-loop"] and first not in fake.containers  # removed, by its exact name
    assert sandbox.call("fx-note", "before_call", [VIEW, {}], timeout_s=5)["ok"] is True  # restarted once
    assert len(sandbox.names) == 2 and sandbox.names[1] in fake.containers
    assert sandbox.call("fx-loop", "before_call", [VIEW, {}], timeout_s=5)["fault"] == "not_loaded"


def test_sbx09_corrupt_frames_restart_without_the_faulting_procedure(fake, make):
    fake.corrupt = (2, "garbage")  # reply frames: 0 ping, 1 load, 2 the first call
    sandbox = make(bundle("fx-crash", "fx-note"))
    result = sandbox.call("fx-crash", "before_call", [VIEW, {}], timeout_s=5)
    assert result["fault"] == "worker" and "invalid JSON" in result["message"]
    assert sandbox.dropped == ["fx-crash"] and sandbox.names[0] not in fake.containers
    fake.corrupt = (3, "seq")
    assert sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)["value"] is True
    result = sandbox.call("fx-note", "before_call", [VIEW, {}], timeout_s=5)
    assert result["fault"] == "worker" and "seq mismatch" in result["message"]
    assert sandbox.dropped == ["fx-crash", "fx-note"] and len(sandbox.names) == 2


def test_sbx09_a_failed_restart_is_sandbox_unavailable(fake, make, tmp_path):
    pools = slots.pools(tmp_path / "slots")
    fake.corrupt = (2, "garbage")
    sandbox = make(bundle("fx-crash", "fx-note"), live=pools[slots.LIVE])
    assert sandbox.call("fx-crash", "before_call", [VIEW, {}], timeout_s=5)["fault"] == "worker"
    fake.fail_starts = 2  # the start and its one retry (safety review 5)
    with pytest.raises(SandboxUnavailable, match="sandbox_start_failed"):
        sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)
    assert pools[slots.LIVE].holdings.held() == ()  # the failed containers' live slots were released
    assert [r["cause"] for r in sandbox.restarts] == ["start_failed"] and len(sandbox.names) == 3


def test_sbx10_missing_image_or_docker_is_sandbox_unavailable(fake, make, tmp_path):
    fake.image_missing = True
    sandbox = make(bundle("fx-note"))
    with pytest.raises(SandboxUnavailable, match="sandbox_image_missing"):
        sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)
    assert fake.containers == {} and ["image", "inspect", client.IMAGE] in fake.commands
    no_docker = make(bundle("fx-note"), docker=client.Docker(path=str(tmp_path)))
    with pytest.raises(SandboxUnavailable, match="docker not found"):
        no_docker.call("fx-note", "applies", [VIEW], timeout_s=2)


def test_sbx11_unconfirmed_removal_of_the_exact_name_keeps_the_live_slot(fake, make, tmp_path):
    pools = slots.pools(tmp_path / "slots")
    sandbox = make(bundle("fx-note"), live=pools[slots.LIVE], per_call=pools[slots.CALL])
    assert sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)["ok"]
    assert pools[slots.LIVE].holdings.held() == (slots.LIVE,)  # held for the container's lifetime
    name = sandbox.names[0]
    fake.sticky.add(name)
    with pytest.raises(CleanupUnconfirmed, match=name):
        sandbox.close()
    assert fake.commands[-1] == ["ps", "-a", "--filter", "name=^/%s$" % name, "--format", "{{.Names}}"]
    assert pools[slots.LIVE].holdings.held() == (slots.LIVE,)  # released only after a confirmed removal
    assert [c.name for c in sandbox.unconfirmed] == [name]
    with pytest.raises(ValueError):
        cleanup("not-a-sandbox-name", docker=fake)


def test_sbx11_slots_are_released_after_a_confirmed_removal(fake, make, tmp_path):
    pools = slots.pools(tmp_path / "slots")
    with with_worker(bundle("fx-note"), kind="episode", docker=fake, limits=TEST_LIMITS, scratch=tmp_path,
                     live=pools[slots.LIVE], per_call=pools[slots.CALL]) as sandbox:
        assert sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)["ok"]
        assert pools[slots.LIVE].holdings.held() == (slots.LIVE,)
    assert pools[slots.LIVE].holdings.held() == () and fake.containers == {}


def test_sbx12_fresh_namespace_per_call_and_two_hash_seeds(make):
    seed0, seed1 = make(bundle("fx-state", "fx-order")), make(bundle("fx-state", "fx-order"), hashseed=1)
    calls = [seed0.call("fx-state", "before_call", [VIEW, {"n": 1}], timeout_s=5)["value"] for _ in range(3)]
    assert calls == [{"facts": ["1", "0"], "state": {"n": 1}}] * 3  # module and library state never survive a call
    same = [w.call("fx-order", "deterministic", [VIEW, {}], timeout_s=5)["value_sha256"] for w in (seed0, seed1)]
    differ = [w.call("fx-order", "nondeterministic", [VIEW, {}], timeout_s=5)["value_sha256"] for w in (seed0, seed1)]
    assert same[0] == same[1] and differ[0] != differ[1]
    assert seed0.call("fx-order", "nondeterministic", [VIEW, {}], timeout_s=5)["value_sha256"] == differ[0]
    assert (seed0.ping()["hashseed"], seed1.ping()["hashseed"]) == ("0", "1")


def test_sbx13_two_live_workers_close_by_exact_name_and_drain_by_prefix(fake, make):
    first, second = make(bundle("fx-note")), make(bundle("fx-note"))
    for sandbox in (first, second):
        assert sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)["ok"]
    first.close()  # succeeds while the second container lives (Codex F14)
    assert list(fake.containers) == second.names
    assert [c for c in fake.commands if c[0] == "ps"] == [
        ["ps", "-a", "--filter", "name=^/%s$" % first.names[0], "--format", "{{.Names}}"]]
    with pytest.raises(CleanupUnconfirmed, match=second.names[0]):
        drain_check(docker=fake)
    second.close()
    drain_check(docker=fake)
    assert fake.commands[-1] == ["ps", "-a", "--filter", "name=^/execskill-sbx-", "--format", "{{.Names}}"]
    leftover = make(bundle("fx-note"))
    assert leftover.call("fx-note", "applies", [VIEW], timeout_s=2)["ok"]
    fake.sticky.add(leftover.names[0])
    with pytest.raises(CleanupUnconfirmed):
        leftover.close()
    with pytest.raises(CleanupUnconfirmed, match=leftover.names[0]):
        drain_check(docker=fake)


def test_public_workbook_reads_the_read_only_input_mount(fake, make, tmp_path):
    inputs = tmp_path / "input"
    inputs.mkdir()
    book = openpyxl.Workbook()
    book.active.title = "Data"
    book.active["A1"], book.active["B1"] = 3, "=A1*2"
    book.save(inputs / "input.xlsx")
    sandbox = make(bundle("fx-workbook"), inputs_dir=inputs)
    assert sandbox.call("fx-workbook", "before_call", [VIEW, {}], timeout_s=10)["value"] == {
        "facts": ["Data", "3", "=A1*2", "None"]}  # no cached value: openpyxl never computes formulas
    assert "type=bind,source=%s,target=/input,readonly" % inputs in fake.argvs[0]
    without = make(bundle("fx-workbook"))
    result = without.call("fx-workbook", "before_call", [VIEW, {}], timeout_s=10)
    assert (result["fault"], result["exc_type"]) == ("exception", "FileNotFoundError")


class Sym:
    """A stand-in for sympy objects: records how ``safe_sympify`` built the expression."""

    def __init__(self, text, integer=None):
        self.text, self.integer = text, integer

    @property
    def is_Integer(self):
        return self.integer is not None

    def __int__(self):
        return self.integer

    def __add__(self, other):
        return Sym("(%s+%s)" % (self.text, other.text))

    def __sub__(self, other):
        return Sym("(%s-%s)" % (self.text, other.text))

    def __mul__(self, other):
        return Sym("(%s*%s)" % (self.text, other.text))

    def __truediv__(self, other):
        return Sym("(%s/%s)" % (self.text, other.text))

    def __pow__(self, other):
        return Sym("(%s**%s)" % (self.text, other.text))

    def __neg__(self):
        return Sym("(-%s)" % self.text)


FAKE_SYMPY = SimpleNamespace(
    Rational=lambda p, q: Sym(str(p) if q == 1 else "%d/%d" % (p, q), p if q == 1 else None),
    Symbol=Sym, pi=Sym("pi"), E=Sym("E"), I=Sym("I"), sqrt=lambda x: Sym("sqrt(%s)" % x.text),
    sin=lambda x: Sym("sin(%s)" % x.text))


def test_safe_sympify_whitelists_tokens_and_builds_with_constructors(monkeypatch):
    assert worker.parse_expression("-x^2") == ("neg", ("pow", ("name", "x"), ("num", "2")))
    for bad in ("__import__('os')", "x.y", "lambda: 1", "sympify(x)", "1 +", "2 3", "(" * 41 + "x" + ")" * 41):
        with pytest.raises(ValueError):
            worker.parse_expression(bad)
    monkeypatch.setitem(sys.modules, "sympy", None)
    with pytest.raises(RuntimeError, match="sympy is not available"):
        worker.safe_sympify("x + 1")
    monkeypatch.setitem(sys.modules, "sympy", FAKE_SYMPY)
    assert worker.safe_sympify("2*x^2 - sqrt(y)/0.5 + sin(pi)").text == "(((2*(x**2))-(sqrt(y)/1/2))+sin(pi))"
    with pytest.raises(ValueError, match="exponent"):
        worker.safe_sympify("2**2000")


def test_worker_imports_only_the_standard_library_at_module_level():
    tree = ast.parse(client.WORKER_FILE.read_text())
    modules = {alias.name.split(".")[0] for node in tree.body if isinstance(node, ast.Import) for alias in node.names}
    modules |= {node.module.split(".")[0] for node in tree.body if isinstance(node, ast.ImportFrom)}
    assert modules.isdisjoint({"sympy", "numpy", "pandas", "openpyxl", "skillopt"})
    assert modules <= set(sys.stdlib_module_names) | {"__future__"}


# ------------------------------------------------------------------------- fixer regressions (reviews 2026-10-22)
def test_isolation_9_the_input_mount_holds_exactly_input_xlsx(tmp_path):
    from skillopt.execskill.sandbox.client import Worker

    folder = tmp_path / "item"
    folder.mkdir()
    (folder / "1_1_input.xlsx").write_bytes(b"PK")
    (folder / "1_1_answer.xlsx").write_bytes(b"PK")  # the frozen SpreadsheetBench layout keeps the answer beside it
    with pytest.raises(ValueError, match="input.xlsx"):
        Worker().start(bundle("fx-workbook"), kind="cell", inputs_dir=folder)
    clean = tmp_path / "clean"
    clean.mkdir()
    (clean / "input.xlsx").write_bytes(b"PK")
    assert Worker().start(bundle("fx-workbook"), kind="cell", inputs_dir=clean).inputs_dir == clean
    (clean / "notes.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="input.xlsx"):
        Worker().start(bundle("fx-workbook"), kind="cell", inputs_dir=clean)


# ------------------------------------------------- safety review findings 3-5 (registrar decisions, 2026-10-22)
def test_safety_3_names_carry_chain_and_unit_and_a_unit_drains_alone(fake, make):
    g_unit, d_unit = "G/s2-officeqa/accept", "D/s2-officeqa/accept"
    tag = client.unit_tag("G", g_unit)
    assert client.TAG.fullmatch(tag) and tag.startswith("g-") and tag == client.unit_tag("g", g_unit)
    assert client.unit_tag("D", d_unit).startswith("d-") and client.unit_tag("G", d_unit) != tag
    for chain in ("G/1", "", "toolongchain"):
        with pytest.raises(ValueError):
            client.unit_tag(chain, g_unit)
    with pytest.raises(ValueError):
        Worker(tag="G-1234")
    g, d = make(bundle("fx-note"), tag=tag), make(bundle("fx-note"), tag=client.unit_tag("D", d_unit))
    for sandbox in (g, d):
        assert sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)["ok"]
    assert g.names[0].startswith(client.PREFIX + tag + "-") and client.NAME.fullmatch(g.names[0])
    with pytest.raises(CleanupUnconfirmed, match=g.names[0]):
        client.drain_unit("G", g_unit, docker=fake)  # the unit's own container still lives
    g.close()
    client.drain_unit("G", g_unit, docker=fake)  # while the other chain's container lives (ticket A5-2)
    assert fake.commands[-1] == ["ps", "-a", "--filter", "name=^/%s%s-" % (client.PREFIX, tag), "--format",
                                 "{{.Names}}"]
    with pytest.raises(CleanupUnconfirmed, match=d.names[0]):
        drain_check(docker=fake)  # the machine-wide check still sees every route-B container
    d.close()
    client.drain_unit("D", d_unit, docker=fake)
    assert "execskill-sbx-<chain>-<unit12>-<uuid4>" in client.argv_template("cell")


def test_safety_3_removal_is_tried_three_times_before_cleanup_unconfirmed(fake, make, monkeypatch):
    monkeypatch.setattr(client, "CLEANUP_PAUSE_SECONDS", 0)
    slow = make(bundle("fx-note"))
    assert slow.call("fx-note", "applies", [VIEW], timeout_s=2)["ok"]
    name = slow.names[0]
    fake.transient[name] = 2  # the first two removals leave it listed
    before = len(fake.commands)
    slow.close()
    assert [c[0] for c in fake.commands[before:]] == ["rm", "ps"] * 3 and name not in fake.containers
    assert [c["container"] for c in slow.cleanups] == [name] and slow.cleanups[0]["seconds"] >= 0
    stuck = make(bundle("fx-note"))
    assert stuck.call("fx-note", "applies", [VIEW], timeout_s=2)["ok"]
    fake.sticky.add(stuck.names[0])
    before = len(fake.commands)
    with pytest.raises(CleanupUnconfirmed, match="still listed after 3 tries"):
        stuck.close()
    assert [c[0] for c in fake.commands[before:]] == ["rm", "ps"] * 3
    fake.daemon_down = True
    with pytest.raises(CleanupUnconfirmed, match="docker ps failed after 3 tries"):
        drain_check(docker=fake)
    fake.daemon_down = False


def test_safety_4_the_worker_parent_is_non_dumpable_and_ignores_sigint(fake, make):
    sandbox = make(bundle("fx-note"))
    assert sandbox.ping()["dumpable"] == (0 if sys.platform == "linux" else None)
    os.kill(fake.containers[sandbox.names[0]].process.pid, signal.SIGINT)
    time.sleep(0.2)
    assert sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)["value"] is True
    assert len(sandbox.names) == 1 and sandbox.dropped == []


def test_safety_4_a_refused_call_is_a_lost_worker_and_a_refused_ping_or_load_a_configuration_error(fake, make):
    fake.corrupt = (2, "refuse")  # reply frames: 0 ping, 1 load, 2 the first call
    sandbox = make(bundle("fx-crash", "fx-note"))
    result = sandbox.call("fx-crash", "before_call", [VIEW, {}], timeout_s=5)
    assert result["fault"] == "worker" and "refused the call: forged refusal" in result["message"]
    assert sandbox.dropped == ["fx-crash"] and sandbox.restarts == [] and sandbox.names[0] not in fake.containers
    assert sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)["value"] is True  # restarted without fx-crash
    for index in (0, 1):  # the ready ping, the load
        fake.corrupt = (index, "refuse")
        refused = make(bundle("fx-note"))
        with pytest.raises(ConfigurationError, match="forged refusal"):
            refused.call("fx-note", "applies", [VIEW], timeout_s=2)
        assert refused.names[0] not in fake.containers


IN_PROCESS = {"address_space_mb": 65_536, "frame_bytes": 1 << 20}  # the test process's own address space is large
GRANDCHILD = """
import os
import time

def spawn(report, closed):
    pid = os.fork()
    if pid == 0:
        if closed:
            os.closerange(3, 1 << 16)
        time.sleep(60)
        os._exit(0)
    os.write(report, b"%d\\n" % pid)
    if not closed:
        time.sleep(60)
    return pid
"""
PROBE = """
import ctypes

def probe():
    with open("/proc/self/oom_score_adj") as handle:
        adjust = handle.read().strip()
    return [adjust, ctypes.CDLL(None).prctl(3, 0, 0, 0, 0)]
"""


def call_here(text, fn, args, timeout_s):
    """``worker.run_call`` from this process on test-written code (its child is a fork of this process)."""
    channel = os.open(os.devnull, os.O_RDONLY)  # stands in for the frame channel, which the child closes
    try:
        return worker.run_call(compile(source(text), "procedure", "exec"), fn, args, timeout_s, IN_PROCESS, channel)
    finally:
        os.close(channel)


def exited(pid, wait_s=10):
    """True once ``pid`` has exited: no /proc entry, or a zombie."""
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline:
        try:
            state = Path("/proc/%d/stat" % pid).read_text().rpartition(")")[2].split()[0]
        except (OSError, IndexError):
            return True
        if state in ("Z", "X"):
            return True
        time.sleep(0.01)
    return False


@pytest.mark.skipif(sys.platform != "linux", reason="process groups and /proc: Linux")
@pytest.mark.parametrize("closed,timeout_s", [(False, 1), (True, 10)])
def test_safety_4_a_calls_descendants_die_with_its_process_group(closed, timeout_s):
    report, sink = os.pipe()
    try:
        outcome = call_here(GRANDCHILD, "spawn", [sink, closed], timeout_s)
        grandchild = int(os.read(report, 64))
    finally:
        os.close(report)
        os.close(sink)
    if closed:  # the call returned; its grandchild had let go of every descriptor
        assert outcome["ok"] is True and outcome["value"] == grandchild
    else:
        assert outcome["fault"] == "timeout"
    assert exited(grandchild)


@pytest.mark.skipif(sys.platform != "linux", reason="prctl and /proc: Linux")
def test_safety_4_a_call_child_is_non_dumpable_yet_gets_oom_score_adj_1000():
    """As in the container: uid 65534 (when the test runs as root) under a non-dumpable worker parent, whose /proc
    files therefore belong to root; the child takes them back just for its oom_score_adj write."""
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        status = 1
        try:
            os.dup2(write_fd, 3)
            os.closerange(4, 1 << 16)
            if os.getuid() == 0:
                os.setgroups([])
                os.setgid(65534)
                os.setuid(65534)
            parent = worker.set_dumpable(0)
            os.write(3, json.dumps([parent, call_here(PROBE, "probe", [], 10)]).encode())
            status = 0
        finally:
            os._exit(status)
    os.close(write_fd)
    with os.fdopen(read_fd, "rb") as handle:
        found = handle.read()
    os.waitpid(pid, 0)
    parent, outcome = json.loads(found)
    assert parent == 0 and outcome["ok"] is True, outcome
    assert outcome["value"] == ["1000", 0]


def test_safety_5_an_oom_killed_container_is_replaced_and_the_call_retried_once(fake, make):
    fake.corrupt = (2, "oom")
    sandbox = make(bundle("fx-note"))
    result = sandbox.call("fx-note", "before_call", [VIEW, {}], timeout_s=5)
    first = sandbox.names[0]
    assert result["ok"] is True and result["value"] == {"facts": ["lines: 2"]}
    assert sandbox.restarts == [{"cause": "oom", "container": first, "procedure": "fx-note"}]
    assert sandbox.dropped == [] and len(sandbox.names) == 2 and first not in fake.containers
    assert ["inspect", "--format", "{{json .State}}", first] in fake.commands
    fake.corrupt = [(2, "oom"), (2, "oom")]  # killed again in the replacement: then P1
    again = make(bundle("fx-note"))
    result = again.call("fx-note", "before_call", [VIEW, {}], timeout_s=5)
    assert result["fault"] == "worker" and "docker: oom" in result["message"]
    assert again.dropped == ["fx-note"] and [r["cause"] for r in again.restarts] == ["oom"]
    assert again.call("fx-note", "applies", [VIEW], timeout_s=2)["fault"] == "not_loaded"


def test_safety_5_a_vanished_container_is_replaced_and_a_crashed_worker_stays_p1(fake, make):
    fake.corrupt = (2, "gone")
    sandbox = make(bundle("fx-note", "fx-loop"))
    assert sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)["value"] is True
    assert [r["cause"] for r in sandbox.restarts] == ["gone"] and sandbox.dropped == []
    second = sandbox.names[1]
    thread, out = in_thread(lambda: sandbox.call("fx-loop", "before_call", [VIEW, {}], timeout_s=60))
    fake.children(second)
    fake.kill_worker(second)  # the container is still there and was not OOM-killed: the worker itself died
    thread.join(30)
    assert out["result"]["fault"] == "worker" and "docker: worker" in out["result"]["message"]
    assert sandbox.dropped == ["fx-loop"] and len(sandbox.restarts) == 1


def test_safety_5_docker_down_during_a_call_is_sandbox_unavailable_not_a_procedure_fault(fake, make, monkeypatch):
    monkeypatch.setattr(client, "CLEANUP_PAUSE_SECONDS", 0)
    fake.corrupt = (2, "daemon")
    sandbox = make(bundle("fx-note"))
    with pytest.raises(SandboxUnavailable, match="sandbox_daemon_unreachable") as caught:
        sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)
    first = sandbox.names[0]
    assert "removal unconfirmed" in str(caught.value) and [c.name for c in sandbox.unconfirmed] == [first]
    assert sandbox.dropped == [] and sandbox.restarts == []
    fake.daemon_down = False
    cleanup(first, docker=fake)
    assert fake.containers == {}


def test_safety_5_one_start_retry_but_none_while_docker_does_not_answer(fake, make, monkeypatch):
    monkeypatch.setattr(client, "CLEANUP_PAUSE_SECONDS", 0)
    fake.fail_starts = 1
    sandbox = make(bundle("fx-note"))
    assert sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)["value"] is True
    assert sandbox.restarts == [{"cause": "start_failed", "container": sandbox.names[0], "procedure": None}]
    assert len(sandbox.names) == 2 and sandbox.names[0] not in fake.containers
    fake.daemon_down = True
    down = make(bundle("fx-note"))
    with pytest.raises(SandboxUnavailable, match="sandbox_daemon_unreachable"):
        down.call("fx-note", "applies", [VIEW], timeout_s=2)
    assert len(down.names) == 1 and down.restarts == []
    fake.daemon_down = False


def test_safety_minor_13_a_live_slot_is_released_whatever_the_start_raises(fake, make, tmp_path, monkeypatch):
    pools = slots.pools(tmp_path / "slots")

    def explode(argv):
        raise RuntimeError("spawn exploded")

    monkeypatch.setattr(fake, "spawn", explode)
    sandbox = make(bundle("fx-note"), live=pools[slots.LIVE])
    with pytest.raises(RuntimeError, match="spawn exploded"):
        sandbox.call("fx-note", "applies", [VIEW], timeout_s=2)
    sandbox.close()
    assert pools[slots.LIVE].holdings.held() == ()


# ------------------------------------------- per-call writable state (§2.6; Codex 2026-10-22 review finding 6)
# RLIMIT_FSIZE 0 stops a call child writing file CONTENT but not ``os.mkdir`` of an empty directory, so a child that
# reached ``os`` (a reflection route the hygiene layer missed) could leave a marker in the shared /tmp that the next
# call's child would see -- hidden state across requests. The real boundary is the container, so the worker gives each
# call its own writable directory and removes it when the call ends. These tests drive ``worker.run_call`` on
# test-written code (bypassing the policy, as the escape probe does) with the writable base redirected to ``tmp_path``
# (host mode, not PID 1: only the private directory is swept, never the shared /tmp). The container's extra /tmp sweep
# is exercised in the S0 smoke on dl.
WRITABLE = """
import os

def make(view, state):
    base = os.environ["TMPDIR"]
    os.mkdir(os.path.join(base, "left-behind"))
    return {"cwd": os.getcwd(), "tmpdir": base, "listing": sorted(os.listdir(base))}

def look(view, state):
    base = os.environ["TMPDIR"]
    return {"cwd": os.getcwd(), "tmpdir": base, "listing": sorted(os.listdir(base))}
"""


def _run_raw(code, fn):
    """``worker.run_call`` on raw module source (its child is a fork of this process)."""
    channel = os.open(os.devnull, os.O_RDONLY)
    try:
        return worker.run_call(compile(source(code), "procedure", "exec"), fn, [VIEW, None], 5, IN_PROCESS, channel)
    finally:
        os.close(channel)


@pytest.mark.skipif(sys.platform != "linux", reason="os.fork and /proc: Linux")
def test_a_call_runs_in_a_private_writable_directory_removed_afterwards(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    first = _run_raw(WRITABLE, "make")["value"]
    second = _run_raw(WRITABLE, "look")["value"]
    assert first["listing"] == ["left-behind"]  # the call sees the marker it just wrote
    assert second["listing"] == []  # the next call's directory is fresh: the marker did not survive the request
    assert first["tmpdir"] != second["tmpdir"] and first["tmpdir"].startswith(str(tmp_path))
    assert not Path(first["tmpdir"]).exists() and not Path(second["tmpdir"]).exists()  # removed when the call ended
    assert list(tmp_path.iterdir()) == []  # no call directory is left behind in the writable base


@pytest.mark.skipif(sys.platform != "linux", reason="os.fork and /proc: Linux")
def test_each_call_child_runs_in_its_own_private_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    value = _run_raw(WRITABLE, "make")["value"]
    assert value["cwd"] == value["tmpdir"]  # the child changed into its private directory before any procedure code
    assert value["tmpdir"].startswith(str(tmp_path))
