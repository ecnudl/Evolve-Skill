"""Batch B1 integration (implementation plan §5, §8.1 T-ID-1/T-ID-2, §9 "Integration gates"; registration §2.2-§2.4,
§3.4, §4.1, §4.4, §9.3): the foundation modules wired together the way later batches wire them -- the route-B slot
pools under the frozen Endpoint and ledger with both chains' solver clients and the method roles, the smoke's and the
probe's own ledgers, the one exception set raised by the module that owns each stop, the one record stamp of every
B1 writer, the hand-off of checked bindings from the notes to the exact calculator, and the one lexicon hash.
Offline and deterministic: scripted gateways behind the real clients (tests/execskill_fakes.py), fixture items."""
from __future__ import annotations

import ast
import importlib
import json
import pkgutil
from pathlib import Path
from types import SimpleNamespace

import pytest

import skillopt.execskill as execskill
from skillopt.coevo5 import ledger, outcomes
from skillopt.coevo5.budget import Budget
from skillopt.execskill import budgets, compute, errors, notes, package, protocol, slots, supply
from skillopt.execskill.client import solver_client
from skillopt.execskill.errors import (
    STOP_KINDS,
    AssumptionBroken,
    BudgetStop,
    ConfigurationError,
    ConsumptionConflict,
    PackageInvalid,
    SandboxUnavailable,
    stop_kind,
)
from skillopt.execskill.registry import Registry
from skillopt.execskill.slots import CALL, EPISODE, LIVE, NATIVE
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes import FakeGLM, FakeSolver, over_nominal
from tests.fixtures.execskill import items as fx

DEEPSEEK, GLM = protocol.CHAINS["D"], protocol.CHAINS["G"]
SYSTEM, USER = "Act in the text environment.", json.dumps({"observation": "You are in the middle of a room."})
FROZEN_STOPS = ("AssumptionBroken", "BudgetStop", "CleanupUnconfirmed", "ConfigurationError", "LedgerFailure")
ROUTE_B_STOPS = ("ConsumptionConflict", "PackageInvalid", "SandboxUnavailable")
ONE_SET = ("skillopt.coevo5.outcomes", "skillopt.execskill.errors")
REPO = Path(__file__).resolve().parents[1]
ERRORS = REPO / "skillopt" / "execskill" / "errors.py"
SOURCE = ('"""Lists the numbers of a question."""\nimport re\n\n\ndef applies(view):\n    return True\n\n\n'
          'def before_call(view, state):\n    return {"facts": re.findall(r"[0-9]+", view["question"])[:3]}\n')
REPLY = "<calc>r1991 - r1990</calc> <calc>(r1991 - r1990) / r1990 * 100</calc> <calc>r1992</calc>"


class Clock:
    """A simulated monotonic clock whose ``sleep`` only advances it (one thread)."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def _ledger(tmp_path, name, caps):
    budget = Budget(tmp_path / name, sleep=lambda _: None)
    budget.declare(caps)
    return budget


def _reserves(budget):
    events = (json.loads(line) for line in (budget.root / "events.jsonl").read_text().splitlines())
    return [event for event in events if event["event"] == "reserve"]


def _holding(pools, seen, reply):
    """A scripted answer that records the pools the calling thread holds while the request is in flight."""
    def answer(system, user):
        seen.append(pools[EPISODE].holdings.held())
        return reply
    return answer


def _procedure(procedure_id):
    return package.Procedure(id=procedure_id, origin="officeqa", description="Lists the numbers of the question.",
                             hooks=("applies", "before_call"), source=SOURCE, evidence="smoke", max_note_chars=500)


# ------------------------------------------------------------------------------------------------------- T-ID-1
def _route_b_sources():
    return (sorted((REPO / "skillopt" / "execskill").rglob("*.py")) + sorted((REPO / "tests").glob("*execskill*.py"))
            + sorted((REPO / "tests" / "fixtures" / "execskill").rglob("*.py")))


def _imported_from(path, node):
    """The absolute module an ``ImportFrom`` node of ``path`` names."""
    if not node.level:
        return node.module
    parts = path.relative_to(REPO).parent.parts
    return ".".join(parts[:len(parts) - node.level + 1] + ((node.module,) if node.module else ()))


def test_t_id_1_one_exception_set_across_the_route_b_tree():
    stops = set(FROZEN_STOPS + ROUTE_B_STOPS)
    for path in _route_b_sources():
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                assert node.name not in stops or (path == ERRORS and node.name in ROUTE_B_STOPS), (path, node.name)
            elif isinstance(node, ast.ImportFrom) and stops & {alias.name for alias in node.names}:
                assert _imported_from(path, node) in ONE_SET, (path, node.module)
    for info in pkgutil.walk_packages(execskill.__path__, execskill.__name__ + "."):
        module = importlib.import_module(info.name)
        for name in sorted(stops):
            assert getattr(module, name, getattr(errors, name)) is getattr(errors, name), (info.name, name)
    assert all(getattr(errors, name) is getattr(outcomes, name) for name in FROZEN_STOPS)


def test_t_id_1_each_owner_raises_a_stop_of_its_kind(tmp_path):
    raised = {}
    registry = Registry(tmp_path / "history", evidence="engineering_fixture")
    item = fx.searchqa_items(1)
    registry.register("D", "searchqa", item, unit="D:run", purpose="run", run_root="/r")
    with pytest.raises(ConsumptionConflict) as caught:  # another unit of the same chain
        registry.register("D", "searchqa", item, unit="D:accept", purpose="accept", run_root="/r")
    raised["consumption"] = caught.value
    with pytest.raises(PackageInvalid) as caught:
        _procedure("not-a-procedure")
    raised["package"] = caught.value
    clock = Clock()
    pools = slots.pools(tmp_path / "slots", sizes={CALL: 1}, poll=10, sleep=clock.sleep, clock=clock,
                        log=lambda line: None)
    busy = pools[CALL]._take(0)  # another process's short hold that never ends
    try:
        with pytest.raises(SandboxUnavailable) as caught:
            with pools[CALL].hold_short():
                pass
    finally:
        pools[CALL]._release(busy)
    assert clock.now >= 2 * protocol.SHORT_HOLD_SECONDS
    raised["sandbox"] = caught.value
    with pytest.raises(ConfigurationError) as caught:
        solver_client("deepseek-v4-flash", config={})
    raised["configuration"] = caught.value
    fake = FakeSolver(tmp_path, [(None, "<answer>4</answer>")])
    bound = protocol.ledger_bound(DEEPSEEK, "officeqa", branch="E")
    scopes = budgets.solver_scopes("D", "officeqa", 2, "run")
    caps = {scope: 10 ** 9 for scope in scopes[:-1]} | {scopes[-1]: 1_000}  # the step scope fits no call
    tight = SimpleNamespace(budget=_ledger(tmp_path, "tight", caps), slots=pools, cooldown=0)
    recorder = budgets.endpoint(tight, scopes, client=fake.client, max_tokens_bound=bound).recorder(label="tight")
    with pytest.raises(BudgetStop) as caught:  # the frozen ledger's refusal, before anything is sent
        recorder(SYSTEM, USER)
    assert recorder.refused and fake.requests == []
    raised["budget"] = caught.value
    breach = FakeSolver(tmp_path, [(None, over_nominal("<answer>4</answer>", bound + 1))])
    setting = SimpleNamespace(budget=_ledger(tmp_path, "ledger", budgets.caps()), slots=pools, cooldown=0)
    endpoint = budgets.endpoint(setting, scopes, client=breach.client, max_tokens_bound=bound)
    with pytest.raises(AssumptionBroken) as caught:  # a completion above B halts the ledger
        endpoint.recorder(label="breach")(SYSTEM, USER)
    raised["assumption"] = caught.value
    for kind, error in raised.items():  # the frozen exact-type lookup (cells.py:215-216) and the MRO lookup agree
        assert STOP_KINDS[type(error)] == kind == stop_kind(error)


# ------------------------------------------------------------------------------------------------------- T-ID-2
def test_t_id_2_every_b1_writer_stamps_the_one_protocol(tmp_path):
    procedure = _procedure("p-officeqa-1-1")
    candidate = package.with_(package.empty(step="s0", evidence="smoke"), step="s1", add=[procedure])
    registry = Registry(tmp_path / "history", evidence="smoke")
    registry.register("smoke", "searchqa", fx.searchqa_items(1), unit="S2", purpose="smoke",
                      run_root=protocol.SMOKE_ROOT)
    line = json.loads(registry.path("smoke", "searchqa").read_text(encoding="utf-8").splitlines()[0])
    tail = supply.supply_record("searchqa-tail", "searchqa",
                                [{"task_id": "fresh-1", "position": protocol.SEARCHQA_TAIL_START}],
                                sources={"manifest": "fixture"}, evidence="engineering_fixture")
    for value, kind in ((procedure.to_json(), "procedure"), (candidate.to_json(), "package"),
                        (line, "consumption"), (tail, "supply")):
        assert protocol.verified(value, kind) == value
        assert value["version"] == protocol.kind(kind) and value["evidence"] in protocol.EVIDENCE
        assert value[protocol.RECORD_HASH] == digest({k: v for k, v in value.items() if k != protocol.RECORD_HASH})


def test_registered_names_agree_across_the_b1_modules():
    assert set(package.HOOK_PARAMETERS) == set(protocol.HOOKS)  # Procedure validation indexes it by every hook
    assert set(package.SECOND_CALL_HOOKS) <= set(package.NOTE_HOOKS) <= set(protocol.HOOKS)
    assert set(notes.FIELD_TYPES) == set(notes.FIELD_ORDER) == set(protocol.NOTE_HEADERS)  # render indexes headers
    assert set(protocol.NAMESPACES) == set(protocol.CHAINS) | {budgets.SMOKE} | set(protocol.V2_NAMESPACES.values()) | set(
        protocol.V21_NAMESPACES.values()) | set(protocol.V22_NAMESPACES.values()) | set(protocol.V23_NAMESPACES.values())
    assert set(protocol.V2_NAMESPACES) == set(protocol.V21_NAMESPACES) == set(protocol.V22_NAMESPACES) == set(protocol.V23_NAMESPACES) == set(
        protocol.CHAINS)  # v2, v2.1, v2.2: their own
    assert set(protocol.SOLVERS) <= set(slots.POOL_SIZES) and protocol.ROLE_MODEL in slots.POOL_SIZES


# ------------------------------------------------------------------------- pools, clients, roles and the ledger
def test_both_chains_and_a_role_run_through_the_route_b_pools_and_one_ledger(tmp_path):
    budget = _ledger(tmp_path, "ledger", budgets.caps("recommended"))  # SB -> ALF: both pilots run unedited
    pools = slots.pools(tmp_path / "slots", poll=0.01)
    setting = SimpleNamespace(budget=budget, slots=pools, cooldown=0)
    seen = []
    deepseek = FakeSolver(tmp_path, [(None, _holding(pools, seen, "<action>look</action>"))],
                          max_tokens=protocol.solver_tokens(DEEPSEEK, "alfworld"),
                          read_timeout=protocol.read_timeout(DEEPSEEK, "alfworld"))
    glm = FakeSolver(tmp_path, [(None, _holding(pools, seen, "<answer>4</answer>"))], model=GLM)
    roles = FakeGLM(tmp_path, _holding(pools, seen, "{}"))
    calls = [(deepseek.client, budgets.solver_scopes("D", "alfworld", 2, "run"),
              protocol.ledger_bound(DEEPSEEK, "alfworld", branch="E")),
             (glm.client, budgets.solver_scopes("G", "spreadsheetbench", 1, "run"),
              protocol.ledger_bound(GLM, "spreadsheetbench")),
             (roles.client, budgets.glm_scopes("D", "engineer", "alfworld", 2), protocol.ROLE_MAX_TOKENS)]
    recorders = [budgets.endpoint(setting, scopes, client=client, max_tokens_bound=bound).recorder(label=scopes[-1])
                 for client, scopes, bound in calls]
    with pools[EPISODE].hold(), pools[LIVE].hold():  # an ALFWorld episode's slots, then its solver call
        assert recorders[0](SYSTEM, USER)["ok"]
    assert recorders[1](SYSTEM, USER)["ok"] and recorders[2](SYSTEM, USER)["ok"]
    # the frozen Endpoint holds each model's ordered pool while its request is in flight; chain G's solver and the
    # role share the glm-5.3 pool
    assert seen == [(EPISODE, LIVE, DEEPSEEK), (GLM,), (GLM,)] and pools[EPISODE].holdings.held() == ()
    named = [deepseek.requests[0]["max_tokens"], glm.requests[0]["max_tokens"], roles.provider.requests[0]["max_tokens"]]
    assert named == [1_024, 65_536, 16_384]  # each request names its M; the ledger reserves with B
    size = ledger.request_bytes(SYSTEM, USER)
    assert [r.sends[0]["reserved"] for r in recorders] == [ledger.reservation(size, b) for _, _, b in calls]
    assert [tuple(event["scopes"]) for event in _reserves(budget)] == [tuple(sorted(s)) for _, s, _ in calls]
    snapshot = budget.snapshot()
    assert [snapshot[scope]["settled"] for scope in ("D:solver", "G:solver", "D:glm", "G:glm", "overall")] == [
        15, 15, 15, 0, 45]
    assert "halted" not in snapshot


def test_a_model_call_while_holding_a_native_slot_is_refused_before_anything_is_sent(tmp_path):
    budget = _ledger(tmp_path, "ledger", budgets.caps())
    pools = slots.pools(tmp_path / "slots", poll=0.01)
    setting = SimpleNamespace(budget=budget, slots=pools, cooldown=0)
    fake = FakeSolver(tmp_path, [(None, "<answer>4</answer>")],
                      max_tokens=protocol.solver_tokens(DEEPSEEK, "spreadsheetbench"),
                      read_timeout=protocol.read_timeout(DEEPSEEK, "spreadsheetbench"))
    endpoint = budgets.endpoint(setting, budgets.solver_scopes("D", "spreadsheetbench", 1, "run"), client=fake.client,
                                max_tokens_bound=protocol.ledger_bound(DEEPSEEK, "spreadsheetbench", branch="E"))
    recorder = endpoint.recorder(label="D/spreadsheetbench/1/run")
    with pools[NATIVE].hold():
        with pytest.raises(ConfigurationError, match="slot_lock_order") as caught:
            recorder(SYSTEM, USER)
    assert stop_kind(caught.value) == "configuration"
    assert fake.requests == [] and recorder.sends == [] and _reserves(budget) == []
    assert recorder(SYSTEM, USER)["ok"] and len(fake.requests) == 1  # released: the same endpoint sends


def test_the_smoke_and_the_probe_keep_their_own_ledgers(tmp_path):
    pools = slots.pools(tmp_path / "slots", poll=0.01)
    smoke = SimpleNamespace(budget=_ledger(tmp_path, "smoke", budgets.smoke_caps()), slots=pools, cooldown=0)
    probe = SimpleNamespace(budget=_ledger(tmp_path, "probe", budgets.probe_caps()), slots=pools, cooldown=0)
    solver = FakeSolver(tmp_path, [(None, "<answer>4</answer>")])  # the smoke's solver (chain D's model)
    roles = FakeGLM(tmp_path, lambda system, payload: "{}")
    bound = protocol.ledger_bound(protocol.SMOKE_SOLVER, "searchqa", branch="E")
    for scopes, client, b in ((budgets.solver_scopes("smoke", None, None, "smoke"), solver.client, bound),
                              (budgets.glm_scopes("smoke", "examiner", None, None), roles.client,
                               protocol.ROLE_MAX_TOKENS)):
        recorder = budgets.endpoint(smoke, scopes, client=client, max_tokens_bound=b).recorder(label=scopes[-1])
        assert recorder(SYSTEM, USER)["ok"]
    s1c = FakeSolver(tmp_path, [(None, "<answer>4</answer>")], max_tokens=protocol.S1C_TOKENS)
    recorder = budgets.endpoint(probe, budgets.solver_scopes("smoke", None, None, "probe"), client=s1c.client,
                                max_tokens_bound=protocol.B_PROBE).recorder(label="S1-c")
    assert recorder(SYSTEM, USER)["ok"] and s1c.requests[0]["max_tokens"] == protocol.S1C_TOKENS
    reserved = ledger.reservation(ledger.request_bytes(SYSTEM, USER), protocol.B_PROBE)
    assert recorder.sends[0]["reserved"] == reserved <= protocol.PROBE_CAP
    settled = {**smoke.budget.snapshot(), **probe.budget.snapshot()}
    assert [settled[scope]["settled"] for scope in ("smoke:solver", "smoke:glm", "smoke:probe")] == [15, 15, 15]
    for setting in (smoke, probe):  # a pilot scope set is refused there before the ledger could quarantine itself
        with pytest.raises(ConfigurationError):
            budgets.endpoint(setting, budgets.solver_scopes("D", "officeqa", 2, "run"), client=solver.client,
                             max_tokens_bound=bound)
        assert "halted" not in setting.budget.snapshot()


# ------------------------------------------------------------------------------- notes -> calculator, one lexicon
def test_checked_bindings_feed_the_exact_calculator_and_the_note():
    public = "Receipts were 1,031.3 million in 1990 and 1,100 million in 1991."
    fields = {"bindings": [{"name": "r1990", "value": "1,031.3", "quote": "Receipts were 1,031.3 million in 1990"},
                           {"name": "r1991", "value": "1,100", "quote": "1,100 million in 1991"},
                           {"name": "r1992", "value": "1,200", "quote": "1,200 million in 1992"}]}
    kept, dropped = notes.screen(fields, bench="officeqa")
    assert dropped == [] and kept == fields
    checked, faults = notes.check_bindings(kept["bindings"], public)
    assert [b["name"] for b in checked] == ["r1990", "r1991"]
    assert faults == [{"field": "bindings", "reason": "not_verbatim", "detail": "r1992"}]
    tags = compute.parse_tags(REPLY)
    results = compute.evaluate_tags(tags, checked)  # the kept records, passed as they are
    assert results[0] == {"expr": "r1991 - r1990", "value": "68.7"}
    assert results[1]["value"] == compute.evaluate("(1100 - 1031.3) / 1031.3 * 100")["value"]
    assert results[2] == {"expr": "r1992", "value": protocol.NOT_EVALUATED, "error": "computation_failed:name"}
    assert compute.evaluate_tags(tags, {b["name"]: b["value"] for b in checked}) == results
    with pytest.raises(ValueError, match="each name once"):  # a wiring error is loud, never "not evaluated"
        compute.evaluate_tags(tags, checked + checked[:1])
    note = notes.render({"bindings": checked}, bench="officeqa", header="")
    assert note.splitlines() == [protocol.NOTE_HEADERS["bindings"],
                                 '- r1990 = 1,031.3 (quoted: "Receipts were 1,031.3 million in 1990")',
                                 '- r1991 = 1,100 (quoted: "1,100 million in 1991")']
    assert notes.assemble([("p-officeqa-1-1", note, 500)], bench="officeqa") == (note, [])


def test_the_lexicon_has_one_hash_covering_the_registered_values():
    record = notes.lexicon_record()
    assert record["terms"] == {bench: list(protocol.LEXICON[bench]) for bench in protocol.BENCHES}
    assert (record["match"], record["headers"], record["caps"], record["max_header_chars"]) == (
        protocol.LEXICON_MATCH, protocol.NOTE_HEADERS, protocol.MAX_NOTE_CHARS, protocol.MAX_HEADER_CHARS)
    assert record["version"] == protocol.kind("lexicon") and notes.lexicon_sha256() == digest(record)
    assert not [name for name in vars(protocol) if "LEXICON" in name and name.endswith("SHA256")]
