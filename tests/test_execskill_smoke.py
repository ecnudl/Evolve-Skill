"""T-SMOKE-1 and the smoke's stage judgements and dispatch (registration §10, §9.3, §2.6; implementation plan §8.1,
§10; Codex F19; registrar addenda 2026-10-22 13:0x, 13:4x, 14:3x): the sealed specification (the trimmed stage list,
no noise anchor or control cells required), the receipt classes (also stamped at dispatch), the format floor and
margin, the S0 sandbox self-test with the escape probe, the S1 probe on its own ledger (fake transport), S-N1, S-E6
(the solver scopes and the GLM projection), S2's ledger and leftover rows beside a running S3, the S4 fault switch
and smoke-result.json. Offline: synthetic item files, receipts and probe reports, a fake docker, a fake environment
and an ``httpx`` mock transport -- no network, no container, no credential."""
from __future__ import annotations

import argparse
import json
import threading
from types import SimpleNamespace

import httpx
import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.coevo5.evaluation import recovered
from skillopt.execskill import budgets, protocol, smoke
from skillopt.execskill import engineer as engineer_module
from skillopt.execskill.client import ELUCID_MODEL, REASONING_MISMATCH
from skillopt.execskill.errors import SandboxUnavailable
from skillopt.execskill.sandbox import client as sandbox
from tests.execskill_fakes import FAKE_KEYS, fake_config

ENVIRONMENT = {"python": "3.11.16", "openpyxl": "3.1.5", "docker": "27.3.1", "image_digests": {},
               "in_image_libs": {}, "in_image_pip_freeze_sha256": "0" * 64}
DRILL = "S2/searchqa/X/fx-crash/q1/1"
ANCHOR = {"searchqa": 0.3, "alfworld": 0.45}
BOUND = {b: protocol.ledger_bound(protocol.SMOKE_SOLVER, b, branch="E") for b in protocol.BENCHES}


def items(tmp_path):
    out = {}
    for name in smoke.ITEM_SETS:
        path = tmp_path / "items" / (name + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([{"task_id": "%s-%d" % (name, i), "public": {}} for i in range(3)]))
        out[name] = str(path)
    return out


def selftest(tmp_path, passed=True):
    """A sealed S0 sandbox self-test record (what ``smoke.sandbox_selftest`` writes)."""
    path = tmp_path / "s0" / smoke.SELFTEST
    value = protocol.record("sandbox-selftest", "smoke", {
        "escape_rows": {row: passed for row in smoke.ESCAPE_ROWS}, "escape_probe_sha256": "0" * 64,
        "worker_sha256": "1" * 64, "image": sandbox.IMAGE, "limits": {"cell": {"pids": 64}},
        "measured": {"vsz_kib": 173_792, "rss_kib": 111_932, "view_bytes_p99": 4_096, "start_seconds": 2.6,
                     "views": 3}, "passed": passed})
    write_json(path, value)
    return str(path)


@pytest.fixture
def spec(tmp_path):
    return smoke.make(tmp_path / "smoke", items=items(tmp_path), control_cells=[DRILL], noise_anchor=ANCHOR,
                      selftest=selftest(tmp_path), environment_found=ENVIRONMENT, probe_root=tmp_path / "probe")


def receipt(leak=False):
    return {"ok": not leak, "subtype": REASONING_MISMATCH if leak else None}


def production(n, bench="searchqa", stage="S2"):
    return [{"stage": stage, "probe": None, "cell": "%s/%s/C/q%d/1" % (stage, bench, i), "bench": bench,
             "body": smoke.REGISTERED_BODY, "M": protocol.solver_tokens(protocol.SMOKE_SOLVER, bench),
             "B": BOUND[bench], "resend": False, "receipt": receipt()} for i in range(n)]


def probes(leak=False):
    return [{"stage": "S1", "probe": row, "cell": "S1/" + row, "bench": "searchqa", "body": smoke.REGISTERED_BODY,
             "M": 64, "B": protocol.B_PROBE, "resend": False, "receipt": receipt(leak and row == "a")}
            for row in ("a", "b", "c", "d", "f")]


S1E = {"stage": "S1", "probe": "e", "cell": "S1/e", "bench": "searchqa", "body": "no_reasoning_effort",
       "M": 64, "B": protocol.B_PROBE, "resend": False, "receipt": receipt(True)}
CONTROL = {"stage": "S2", "probe": None, "cell": DRILL, "bench": "searchqa", "body": smoke.REGISTERED_BODY,
           "M": 8_192, "B": BOUND["searchqa"], "resend": False, "receipt": receipt(True)}
RESENT = {"stage": "S2", "probe": None, "cell": "S2/searchqa/C/q0/1", "bench": "searchqa",
          "body": smoke.REGISTERED_BODY, "M": 8_192, "B": BOUND["searchqa"], "resend": True, "receipt": receipt()}


# --------------------------------------------------------------------------------------------- the specification
def test_make_seals_the_specification_once_and_a_dry_run_writes_nothing(tmp_path, spec):
    assert spec["version"] == "fivebench-execskill-v1-smoke-spec" and spec["evidence"] == "smoke"
    assert read_json(tmp_path / "smoke" / smoke.SPEC) == spec and smoke.load(tmp_path / "smoke" / smoke.SPEC) == spec
    assert spec["solver"]["model"] == "deepseek-v4.1-flash-1017"  # owner rule 22:3x (c): elucid only
    assert spec["format"] == {"floor": "9/10", "margin": "1/20"} and spec["min_production_receipts"] == 300
    assert spec["caps"]["smoke"]["smoke:solver"] == 14_000_000 and spec["items"]["searchqa"]["count"] == 3
    with pytest.raises(ValueError):
        smoke.make(tmp_path / "smoke", items=items(tmp_path), control_cells=[DRILL], noise_anchor=ANCHOR,
                   selftest=selftest(tmp_path), environment_found=ENVIRONMENT)
    dry = smoke.make(tmp_path / "dry", items=items(tmp_path), control_cells=[DRILL], noise_anchor=ANCHOR,
                     selftest=selftest(tmp_path), environment_found=ENVIRONMENT, write=False)
    assert dry["items"] == spec["items"] and not (tmp_path / "dry").exists()
    with pytest.raises(ValueError, match="enumerated"):
        smoke.make(tmp_path / "x", items=items(tmp_path), control_cells=[DRILL, DRILL], noise_anchor=ANCHOR,
                   selftest=selftest(tmp_path), environment_found=ENVIRONMENT, write=False)
    # the S0 limits and measurements are in the spec before S1 (plan §10 step 3); a failing self-test means no smoke
    assert spec["sandbox"]["measured"]["rss_kib"] == 111_932 and spec["sandbox"]["limits"] == {"cell": {"pids": 64}}
    failing = tmp_path / "failing"
    with pytest.raises(ValueError, match="self-test"):
        smoke.make(tmp_path / "y", items=items(tmp_path), control_cells=[DRILL], noise_anchor=ANCHOR,
                   selftest=selftest(failing, passed=False), environment_found=ENVIRONMENT, write=False)


# ---------------------------------------------------------------------------------------------------- T-SMOKE-1
def test_t_smoke_1_receipt_classes(spec):
    entries = production(300) + probes() + [S1E, CONTROL, RESENT]
    found = smoke.receipt_classes(entries, spec, ledger_bound=BOUND)
    assert found["passed"], found
    assert found["counts"] == {"control": 2, "probe": 5, "production": 300, "resend": 1, "unregistered": 0}
    assert found["control_cells"] == sorted([DRILL, "S1/e"]) and found["s1e_mismatch"] == [True]
    assert found["leaks"]["control"] == 2  # enumerated, listed and excluded: never a production leak
    # S1-e is a control receipt, never a production one: 299 production receipts stay short of 300
    short = smoke.receipt_classes(production(299) + probes() + [S1E], spec, ledger_bound=BOUND)
    assert short["counts"]["production"] == 299 and not short["passed"]
    failing = {
        "s1e_not_mismatch": production(300) + probes() + [{**S1E, "receipt": receipt()}],
        "s1e_missing": production(300) + probes(),
        "probe_leak": production(300) + probes(leak=True) + [S1E],
        "resend_leak": production(300) + probes() + [S1E, {**RESENT, "receipt": receipt(True)}],
        "production_leak": production(299) + [{**production(1)[0], "cell": "S2/x/1", "receipt": receipt(True)}]
        + probes() + [S1E],
        "unregistered_m": production(300) + probes() + [S1E, {**production(1)[0], "cell": "S2/m", "M": 4_096}],
        "unregistered_body": production(300) + probes() + [S1E, {**production(1)[0], "cell": "S2/b",
                                                                 "body": "no_reasoning_effort"}],
        "probe_outside_production": production(300, stage="S3") + probes() + [S1E],
    }
    for name, value in failing.items():
        assert not smoke.receipt_classes(value, spec, ledger_bound=BOUND)["passed"], name


def test_production_receipts_need_the_registered_m_and_b(spec):
    entry = production(1, bench="spreadsheetbench", stage="S4")[0]
    assert smoke.receipt_class(entry, spec, ledger_bound=BOUND) == smoke.PRODUCTION
    assert smoke.receipt_class({**entry, "B": entry["B"] + 1}, spec, ledger_bound=BOUND) == smoke.UNREGISTERED
    assert smoke.receipt_class({**entry, "stage": "S1"}, spec, ledger_bound=BOUND) == smoke.PROBE


# ------------------------------------------------------------------------------------------------- format check
def test_format_floor_nine_tenths_and_margin_one_twentieth():
    def cells(n_ok, n=20):
        return [True] * n_ok + [False] * (n - n_ok)

    ok = smoke.format_check({"officeqa": {"C": cells(20), "X": cells(19), "P": cells(19), "twins": cells(18)}})
    assert ok["passed"] and ok["shares"]["officeqa"]["X"] == "19/20"
    low = smoke.format_check({"officeqa": {"C": cells(18), "X": cells(17), "P": cells(18)}})
    assert [(f["arm"], f["criterion"]) for f in low["failing"]] == [("X", "floor")]
    assert smoke.format_check({"livemath": {"C": cells(20), "X": cells(19), "P": cells(20)}})["passed"]  # C - 1/20
    # 37/40 is above the floor but more than 1/20 below the card arm
    below = smoke.format_check({"livemath": {"C": cells(40, 40), "X": cells(37, 40), "P": cells(40, 40)}})
    assert [(f["arm"], f["criterion"]) for f in below["failing"]] == [("X", "below_card")]
    with pytest.raises(ValueError):
        smoke.format_check({"officeqa": {"C": cells(20), "X": cells(20)}})


# --------------------------------------------------------------------------------------------------- S1 probes
def probe_receipt(prompt=1_000, completion=10, request_bytes=900, ok=True, seconds=5.0, model=None):
    return {"ok": ok, "model": model or protocol.SMOKE_SOLVER, "seconds": seconds, "subtype": None,
            "request_bytes": request_bytes, "usage": {"prompt_tokens": prompt, "completion_tokens": completion}}


def s1(**changes):
    found = {"a": probe_receipt(), "b": {m: [probe_receipt(completion=m) for _ in range(10)] for m in (16, 64, 256)},
             "c": probe_receipt(completion=16_384, seconds=400.0), "d": [probe_receipt() for _ in range(8)],
             "e": {"ok": False, "subtype": REASONING_MISMATCH},
             "f": {"gateway": protocol.GATEWAY, "trust_env": False, "first_confirmed": True}}
    return {**found, **changes}


def test_s1_rows_and_branch():
    found = smoke.s1_probe(s1())
    assert found["passed"] and found["branch"] == "E" and found["longest"] is None
    longer = smoke.s1_probe(s1(b={m: [probe_receipt(completion=m + (i == 3) * 500) for i in range(10)]
                                  for m in (16, 64, 256)}))
    assert longer["branch"] == "N" and longer["longest"] == 756 and longer["passed"]
    assert not smoke.s1_probe(s1(e={"ok": True, "subtype": None}))["passed"]
    assert not smoke.s1_probe(s1(a=probe_receipt(model="deepseek-other")))["passed"]
    assert not smoke.s1_probe(s1(d=[probe_receipt() for _ in range(7)]))["passed"]
    assert not smoke.s1_probe(s1(f={"gateway": protocol.GATEWAY, "trust_env": True, "first_confirmed": True}))["passed"]
    assert not smoke.s1_probe(s1(a=probe_receipt(prompt=1_500, request_bytes=900)))["passed"]  # overhead > 512
    leaking = s1(d=[probe_receipt() for _ in range(7)] + [{**probe_receipt(), "subtype": REASONING_MISMATCH}])
    assert smoke.s1_probe(leaking)["probe_leaks"] == 1


# ------------------------------------------------------------------------------------- S2, S-N1, S-E6, summary
def test_s2_combines_format_receipts_hooks_ledger_and_leftovers(spec):
    compliant = {"searchqa": {"C": [True] * 20, "X": [True] * 20, "P": [True] * 20}}
    kwargs = {"compliant": compliant, "entries": production(300) + probes() + [S1E], "ledger_bound": BOUND,
              "hooks_fired": {hook: 1 for hook in protocol.HOOKS}, "ledger": {"reserved": 10, "settled": 10},
              "leftover": "cannot_judge"}
    assert smoke.s2_solver(spec, **kwargs)["passed"]
    for change in ({"hooks_fired": {hook: 1 for hook in protocol.HOOKS[:-1]}},
                   {"ledger": {"reserved": 11, "settled": 10}}, {"leftover": "leftovers"}):
        assert not smoke.s2_solver(spec, **{**kwargs, **change})["passed"]


def test_sn1_noise_and_se6_cost(spec):
    pairs = {"searchqa": [(1, 1)] * 160 + [(1, 0)] * 20 + [(0, 1)] * 20}
    found = smoke.sn1_noise(spec, pairs)["benches"]["searchqa"]
    assert found["discordant"] == 40 and found["ratio"] == pytest.approx(found["sd"] / 0.3)
    assert found["reregister"] is (found["ratio"] > 1.25)
    fits = smoke.se6_cost({"D:xs:officeqa:2:accept": {"per_cell": 7_000, "cells": 2_000, "reservation": 389_120,
                                                      "cap": 29_500_000}}, ratio=1.5)
    assert fits["passed"] and fits["rows"]["D:xs:officeqa:2:accept"]["needed"] == 21_389_120
    assert not smoke.se6_cost({"s": {"per_cell": 7_000, "cells": 2_000, "reservation": 0, "cap": 1}}, ratio=1.0)["passed"]
    assert not smoke.se6_cost({}, ratio=1.6)["passed"]


def test_the_trimmed_smoke_needs_no_noise_anchor_or_control_cells_and_lists_its_stages(tmp_path):
    """Registrar addenda 13:0x and 13:4x: the default stages are S0, S1, S2, S3 and S-E6; without S-N1 no noise anchor
    is registered (null, with the reason) and the control cells default to none; S-N1 or S4 may be listed, and a
    listed S-N1 needs its anchor."""
    found = smoke.make(tmp_path / "a", items=items(tmp_path), selftest=selftest(tmp_path),
                       environment_found=ENVIRONMENT, write=False)
    assert found["stages"] == list(smoke.SMOKE_STAGES) == ["S0", "S1", "S2", "S3", "SE6"]
    assert found["noise_anchor"] is None and found["noise_anchor_reason"] == smoke.TRIMMED
    assert found["control_cells"] == [] and not (tmp_path / "a").exists()
    listed = smoke.make(tmp_path / "b", items=items(tmp_path), selftest=selftest(tmp_path), noise_anchor=ANCHOR,
                        stages=smoke.SMOKE_STAGES + ("SN1", "S4"), environment_found=ENVIRONMENT, write=False)
    assert listed["stages"][-2:] == ["SN1", "S4"] and listed["noise_anchor"] == ANCHOR
    assert "noise_anchor_reason" not in listed
    for stages, anchor, message in ((smoke.SMOKE_STAGES + ("SN1",), None, "noise anchor"),
                                    (("S0", "S1", "S2", "SE6"), None, "S0, S1, S2, S3 and S-E6"),
                                    (smoke.SMOKE_STAGES + ("S9",), None, "S0, S1, S2, S3 and S-E6"),
                                    (smoke.SMOKE_STAGES + ("S3",), None, "S0, S1, S2, S3 and S-E6")):
        with pytest.raises(ValueError, match=message):
            smoke.make(tmp_path / "c", items=items(tmp_path), selftest=selftest(tmp_path), noise_anchor=anchor,
                       stages=stages, environment_found=ENVIRONMENT, write=False)
    with pytest.raises(ValueError, match="enumerated by id"):
        smoke.make(tmp_path / "c", items=items(tmp_path), selftest=selftest(tmp_path), control_cells=["a", "a"],
                   environment_found=ENVIRONMENT, write=False)
    unanchored = smoke.sn1_noise(found, {"searchqa": [(1, 1), (1, 0), (0, 0)]})  # S-N1 run anyway: measured only
    assert unanchored["anchored"] is False and unanchored["reregister"] is False
    assert unanchored["benches"]["searchqa"]["ratio"] is None and unanchored["benches"]["searchqa"]["discordant"] == 1


def test_the_summary_passes_on_the_specs_stages_and_is_sealed_once(tmp_path):
    spec = smoke.make(tmp_path / "smoke", items=items(tmp_path), selftest=selftest(tmp_path),
                      environment_found=ENVIRONMENT)
    for stage in smoke.SMOKE_STAGES[:-1]:
        smoke.record(spec, stage, {"rows": {}, "passed": True})
    running = smoke.summary(spec)
    assert running["stages"]["SE6"] == "missing" and running["stages"]["SN1"] == "not_required"
    assert running["passed"] is False and not (tmp_path / "smoke" / smoke.RESULT).exists()
    smoke.record(spec, "SE6", {"rows": {}, "passed": True})
    result = smoke.summary(spec)
    assert result["passed"] is True and result["required"] == list(smoke.SMOKE_STAGES)
    assert result["stages"]["SN1"] == result["stages"]["S4"] == "not_required"
    assert read_json(tmp_path / "smoke" / smoke.RESULT) == result
    smoke.record(spec, "S4", {"rows": {}, "passed": False})  # a stage outside the list never gates; sealed already
    assert smoke.summary(spec) == result


def test_summary_is_written_once_every_stage_is_recorded(tmp_path, spec):
    smoke.record(spec, "S0", smoke.s0({row: True for row in smoke.S0_ROWS}))
    partial = smoke.summary(spec)
    assert partial["stages"]["S0"] == "pass" and partial["stages"]["S1"] == "missing" and not partial["passed"]
    assert not (tmp_path / "smoke" / smoke.RESULT).exists()
    for stage in smoke.STAGES[1:]:
        smoke.record(spec, stage, {"rows": {}, "passed": stage != "S3"})
    result = smoke.summary(spec)
    assert result["stages"]["S3"] == "fail" and not result["passed"]
    assert read_json(tmp_path / "smoke" / smoke.RESULT) == result
    assert result["version"] == "fivebench-execskill-v1-smoke-result"
    assert result["rows"]["S0"] == {row: "pass" for row in smoke.S0_ROWS} and result["rows"]["S3"] == {}
    with pytest.raises(ValueError):  # a stage is judged once
        smoke.record(spec, "S3", {"rows": {}, "passed": True})
    with pytest.raises(ValueError):
        smoke.s0({row: True for row in smoke.S0_ROWS[:-1]})
    assert not smoke.s3_roles({row: row != "leakage" for row in smoke.S3_ROWS})["passed"]
    assert smoke.s4_ministep({row: True for row in smoke.S4_ROWS})["passed"]


# ------------------------------------------------- S2 beside S3 (registrar addendum 14:3x): the ledger and leftovers
def test_s2s_ledger_row_judges_this_processs_reservations_and_lists_anothers(tmp_path):
    from skillopt.coevo5.budget import Budget

    root = tmp_path / "ledger"
    mine, other = Budget(root), Budget(root)
    mine.declare(budgets.smoke_caps())
    other.owner = {"pid": 1, "host": "s3-elsewhere", "start": None}  # S3's process
    scopes = budgets.solver_scopes(budgets.SMOKE, None, None, "smoke")
    settled = mine.reserve(scopes, 1_000, label="S2/c1", generation=mine.generation())
    mine.settle(settled, 400, detail={})
    other.reserve(scopes, 2_000, label="smoke/s1-searchqa/run/c1", generation=other.generation())
    rows = smoke._ledger_rows(SimpleNamespace(budget=mine))
    assert rows == {"reserved": 400, "settled": 400, "others_open": 2_000}  # S2's row: reserved == settled
    mine.reserve(scopes, 300, label="S2/c2", generation=mine.generation())  # one of S2's own still open
    assert smoke._ledger_rows(SimpleNamespace(budget=mine))["reserved"] == 700


class PsDocker:
    binary = "docker"

    def __init__(self, names, code=0):
        self.names, self.code = names, code

    def run(self, argv, timeout):
        assert argv[1] == "ps"
        return sandbox.Completed(self.code, "\n".join(self.names).encode())


def test_s2s_leftover_row_lists_the_running_s3_apart(tmp_path, monkeypatch):
    root = tmp_path / "smoke"
    (root / smoke.UNITS_DIR / "S3" / "confirm-1").mkdir(parents=True)
    tags = smoke._s3_tags(root)
    assert sandbox.unit_tag("smoke", "smoke/S3/confirm-2") in tags and len(tags) == 4  # roles, run, confirm-1, -2
    run = sandbox.PREFIX + sandbox.unit_tag("smoke", "smoke/s1-searchqa/run") + "-" + "a" * 32
    roles = sandbox.PREFIX + sandbox.unit_tag("smoke", "smoke/S3/roles") + "-" + "b" * 32
    s2 = sandbox.PREFIX + sandbox.unit_tag("smoke", "smoke/S2/searchqa") + "-" + "c" * 32
    s3 = [(40, "/env/bin/python -B scripts/run_execskill.py smoke-run --spec /s/smoke.json --manifest /s/m.json "
               "--stage S3 --env-path /e --roles-repo /r"),
          (41, "docker exec -i %s python /runner/worker.py" % roles),
          (42, "python scripts/run_execskill.py smoke-run --spec s --manifest m --stage=S3")]
    found = list(s3)
    monkeypatch.setattr(smoke.prelaunch, "processes", lambda: list(found))
    verdict, concurrent = smoke._leftover(PsDocker([run, roles]), fake=False, root=root)
    assert verdict == "clean" and concurrent["containers"] == sorted([run, roles])
    assert [p["pid"] for p in concurrent["processes"]] == [40, 41, 42]
    assert smoke._leftover(PsDocker([run, s2]), fake=False, root=root)[0] == "leftovers"  # an S2 container remains
    assert smoke._leftover(PsDocker([], code=1), fake=False, root=root)[0] == "leftovers"  # unreadable list
    found.append((50, "python scripts/run_execskill.py smoke-run --spec s --manifest m --stage SN1"))
    assert smoke._leftover(PsDocker([]), fake=False, root=root)[0] == "leftovers"  # another route-B process
    found[-1] = (50, "python scripts/run_execskill.py smoke-run --spec s --manifest m --stage S3x")
    assert smoke._leftover(PsDocker([]), fake=False, root=root)[0] == "leftovers"


def test_glm_projection_prices_every_glm_scope_at_the_registered_maximum_role_calls():
    measured = {role: {"calls": 2, "tokens": 20_000, "per_call": 10_000.0, "request_bytes": 50_000}
                for role in budgets.ROLES}
    found = smoke.glm_projection(measured)
    caps = {**budgets.chain_caps("G"), **budgets.chain_caps("D")}
    assert set(found) == {name for name in caps if name.endswith(":glm") or ":role:" in name}
    engineer = found["G:xs:spreadsheetbench:1:role:engineer"]
    # R7 decision 2026-10-22 16:1x, R7c: the per-step maxima the code allows -- 6 engineer calls shared by both
    # engineer units (R7a), 2 x 3 first checks + 4 checks after fixes = 10 leakage judge calls, 3 describer calls
    assert (protocol.ENGINEER_CALLS, smoke.LEAKAGE_CALLS, smoke.DESCRIBER_CALLS) == (6, 10, 3)
    assert engineer["settled"] == 10_000 * (protocol.ENGINEER_CALLS + smoke.LEAKAGE_CALLS + smoke.DESCRIBER_CALLS)
    # registrar addendum 14:4x: the next reservation is never below a full role input (roles.fit's limit), whatever
    # the smaller request S3 measured: 4 x (220,000 + 512 + 16,384) = 947,584; the engineer's with its system prompt
    # (R7c): 4 x (220,000 + 5,170 + 512 + 16,384) = 968,264
    full = 4 * (protocol.ROLE_INPUT_BYTES + 512 + protocol.ROLE_MAX_TOKENS)
    assert full == 947_584 and found["G:xs:spreadsheetbench:1:role:examiner"]["reservation"] == full
    system = len(engineer_module.ENGINEER_SYSTEM.encode())
    assert smoke.ENGINEER_REQUEST_FLOOR == protocol.ROLE_INPUT_BYTES + system == 225_170
    assert engineer["reservation"] == 968_264 and engineer["fits"] is True and engineer["cap"] == 2_500_000
    wide = smoke.glm_projection({**measured, "leakage": {**measured["leakage"], "request_bytes": 230_000}})
    wider = 4 * (230_000 + 512 + protocol.ROLE_MAX_TOKENS)  # a measured request above the limit is kept
    assert wide["G:xs:spreadsheetbench:1:role:engineer"]["reservation"] == wider
    assert wide["G:xs:spreadsheetbench:1:role:examiner"]["reservation"] == full
    research_ = found["D:xs:officeqa:2:role:examiner:research"]
    assert research_["settled"] == 10_000 * smoke.MAX_ROLE_CALLS["examiner_research"] == 1_920_000
    per_step = sum(10_000 * n for n in smoke.MAX_ROLE_CALLS.values())
    assert found["D:glm"]["settled"] == 2 * per_step and found["D:glm"]["cap"] == protocol.GLM_CAP
    dear = {**measured, "examiner_research": {**measured["examiner_research"], "per_call": 30_000.0}}
    over = smoke.glm_projection(dear)  # 192 x 30k + R > 4.6M: a v1.1 re-registration before the pilot
    assert over["G:xs:officeqa:2:role:examiner:research"]["fits"] is False
    assert over["G:xs:officeqa:2:role:examiner"]["fits"] is True
    partial = smoke.glm_projection({role: entry for role, entry in dear.items() if role != "describer"})
    assert partial["G:xs:spreadsheetbench:1:role:engineer"]["assumed"] == ["describer"]
    assert partial["G:xs:spreadsheetbench:1:role:engineer"]["settled"] == 10_000 * (
        protocol.ENGINEER_CALLS + smoke.LEAKAGE_CALLS) + 30_000 * protocol.MAX_CHANGES
    with pytest.raises(ValueError, match="measured role calls"):
        smoke.glm_projection({})
    calls = [{"role": "engineer", "charged": 70_000, "request_bytes": 200_000},
             {"role": "engineer", "charged": 30_000, "request_bytes": None}, {"role": "leakage", "charged": 900}]
    assert smoke.role_calls_measured(calls) == {
        "engineer": {"calls": 2, "tokens": 100_000, "request_bytes": 200_000, "per_call": 50_000.0},
        "leakage": {"calls": 1, "tokens": 900, "request_bytes": 0, "per_call": 900.0}}


# ------------------------------------------------------------------------------------- S0: the sandbox self-test
def escape_report(**changes):
    """A passing escape-probe report shaped like the B2 real-container run (integration note B2)."""
    report = {
        "identity": {"uid": 65534, "gid": 65534, "groups": [65534], "pid": 1},
        "python": {"version": "3.11.16", "safe_path": True, "no_user_site": 1, "dont_write_bytecode": 1,
                   "isolated": 0},
        "env_keys": list(smoke.REGISTERED_ENV_KEYS), "env": dict(smoke.REGISTERED_ENV),
        "network": {"tcp_1.1.1.1_53": "ENETUNREACH", "tcp_8.8.8.8_443": "ENETUNREACH",
                    "udp_1.1.1.1_53": "ENETUNREACH", "dns_example.com": "gaierror", "interfaces": ["lo"]},
        "writes": {"/": "EROFS", "/runner": "EROFS", "/input": "EROFS", "/etc": "EROFS", "/usr": "EROFS",
                   "/tmp": "writable"},
        "tmp": {"mode": "0o1777", "exec": "refused_EACCES"}, "mounts": [],
        "status": {"CapInh": "0000000000000000", "CapPrm": "0000000000000000", "CapEff": "0000000000000000",
                   "CapBnd": "0000000000000000", "CapAmb": "0000000000000000", "NoNewPrivs": "1", "Seccomp": "2"},
        "host_paths": {"/data": False, "/var/run/docker.sock": False, "/run/docker.sock": False,
                       "/root/.config/weak-solver/elucid.env": False, "/data/skillopt-work/.env": False},
        "root_listable": "EACCES", "secret_names": ["/usr/lib/python3/dist-packages/keyring", "/etc/ssl/key.pem"],
        "pids": {"forked": 63, "stopped_by": "EAGAIN"}, "memory": "killed_by_signal_9",
        "worker_child": {"write_file": {"ok": False, "fault": "exception"}, "oom_score_adj": {"ok": True, "value": "1000"},
                         "limits": {"ok": True, "value": {"RLIMIT_FSIZE": [0, 0], "RLIMIT_CPU": [6, 7]}},
                         "standard_streams": {"ok": True, "value": ["/dev/null"] * 3},
                         "connect": {"ok": False, "fault": "exception"}, "allocate": {"ok": False, "fault": "memory"}}}
    return {**report, **changes}


class EscapeDocker:
    """The docker CLI of the self-test: ``run`` returns the probe's report and confirms the forced removal."""

    binary = "docker"

    def __init__(self, report):
        self.report, self.argvs = report, []

    def run(self, argv, timeout):
        self.argvs.append(argv)
        if argv[1] == "run":
            return sandbox.Completed(0, json.dumps(self.report).encode())
        return sandbox.Completed(0, b"")  # rm --force, then ps -a by exact name: nothing left


class PingWorker:
    def start(self, package, *, kind):
        assert kind == "cell" and package.procedures == ()
        return self

    def ping(self):
        return {"vsz_kib": 173_792, "rss_kib": 111_932}

    def close(self):
        self.closed = True


def test_escape_argv_is_the_registered_argv_with_the_probe_in_place_of_the_worker(tmp_path):
    argv = smoke.escape_argv(tmp_path, name=sandbox.PREFIX + "0" * 32)
    registered = sandbox.docker_command("cell", None, {"runner": str(tmp_path), "input": None},
                                        name=sandbox.PREFIX + "0" * 32)
    assert argv[:-1] == registered[:-1] and argv[-1] == "/runner/escape_probe.py"
    assert "--network=none" in argv and "--read-only" in argv and "--user=65534:65534" in argv


def test_sandbox_selftest_judges_the_escape_probe_and_seals_the_measurements(tmp_path):
    item_file = tmp_path / "views.json"
    item_file.write_text(json.dumps([{"public": {"question": "q" * n}} for n in (10, 20, 300)]))
    docker = EscapeDocker(escape_report())
    value = smoke.sandbox_selftest(tmp_path / "s0", item_files=[str(item_file)], docker=docker, worker=PingWorker,
                                   scratch=str(tmp_path))
    assert value["passed"] and value["escape_rows"] == {row: True for row in smoke.ESCAPE_ROWS}
    assert value["measured"]["rss_kib"] == 111_932 and value["measured"]["views"] == 3
    assert value["version"] == "fivebench-execskill-v1-sandbox-selftest" and value["evidence"] == "smoke"
    assert read_json(tmp_path / "s0" / smoke.SELFTEST) == value
    run, removed, listed = docker.argvs
    assert run[-1] == "/runner/escape_probe.py" and removed[1:3] == ["rm", "--force"] and listed[1:3] == ["ps", "-a"]
    assert not list(tmp_path.glob("execskill-escape-*"))  # the runner directory is gone
    with pytest.raises(ValueError):  # written once
        smoke.sandbox_selftest(tmp_path / "s0", item_files=[str(item_file)], docker=docker, worker=PingWorker,
                               scratch=str(tmp_path))
    # each registered check fails its own row
    failing = {
        "env_keys": {"env_keys": sorted([*smoke.REGISTERED_ENV_KEYS, "OPENAI_API_KEY"])},
        "network": {"network": {**escape_report()["network"], "tcp_1.1.1.1_53": "connected"}},
        "no_secrets": {"secret_names": ["/runner/elucid.env"]},
        "read_only": {"writes": {**escape_report()["writes"], "/runner": "writable"}},
        "identity": {"identity": {"uid": 0, "gid": 0, "groups": [0], "pid": 1}},
        "limits": {"memory": "exited_0"},
        "python_flags": {"python": {**escape_report()["python"], "no_user_site": 0}},
        "worker_child": {"worker_child": {**escape_report()["worker_child"],
                                          "write_file": {"ok": True, "value": "written"}}},
    }
    for row, change in failing.items():
        rows = smoke.escape_rows(escape_report(**change))
        assert not rows[row] and sum(rows.values()) == len(smoke.ESCAPE_ROWS) - 1, row

    class NoDocker:
        binary = None

    with pytest.raises(SandboxUnavailable, match="docker not found"):  # no container could be started at all
        smoke.sandbox_selftest(tmp_path / "s0-none", item_files=[str(item_file)], docker=NoDocker(),
                               worker=PingWorker, scratch=str(tmp_path))
    assert not (tmp_path / "s0-none").exists()


# ------------------------------------------------------------------------------------------- S1: the probe
class Gateway:
    """A fake elucid gateway behind ``httpx.MockTransport``: the registered body gets a clean reply whose completion
    stays within max_tokens (branch E); a body without ``reasoning_effort`` gets reasoning text (S1-e)."""

    def __init__(self, *, echo=ELUCID_MODEL, over=None):
        self.echo, self.over, self.bodies, self.lock = echo, over, [], threading.Lock()

    def __call__(self, request):
        body = json.loads(request.content)
        assert request.headers["authorization"] == "Bearer " + FAKE_KEYS[ELUCID_MODEL]
        with self.lock:
            self.bodies.append(body)
        completion = min(body["max_tokens"], 40) if self.over is None else self.over(body)
        message = {"role": "assistant", "content": "SECRET-REPLY-TEXT ready"}
        if "reasoning_effort" not in body:
            message["reasoning_content"] = "thinking first"
        return httpx.Response(200, json={
            "model": self.echo, "choices": [{"message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 30, "completion_tokens": completion, "total_tokens": 30 + completion}})


def probe(tmp_path, spec, gateway):
    env = fake_config(tmp_path, ELUCID_MODEL)["env_path"]
    return smoke.run_probe(spec, env_path=env, probe_root=tmp_path / "probe", slot_root=tmp_path / "slots",
                           transport=httpx.MockTransport(gateway))


def test_s1_probe_on_its_own_ledger_judges_rows_a_to_f_and_keeps_no_reply_text(tmp_path, spec):
    gateway = Gateway()
    value = probe(tmp_path, spec, gateway)
    assert value["complete"] and value["stopped"] is None and len(value["sent"]) == smoke.PROBE_CALLS == 41
    result = value["result"]
    assert result["passed"] and result["branch"] == "E" and result["longest"] is None
    assert result["rows"] == {row: True for row in smoke.S1_ROWS}
    stage = read_json(tmp_path / "smoke" / smoke.STAGES_DIR / "S1.json")
    assert stage["result"] == result
    # S1-e is the control client: the registered body without reasoning_effort, judged reasoning_mismatch
    controls = [b for b in gateway.bodies if "reasoning_effort" not in b]
    assert len(controls) == 1 and all(b["reasoning_effort"] == "none" for b in gateway.bodies if b not in controls)
    assert sorted({b["max_tokens"] for b in gateway.bodies}) == [16, 64, 256, 16_384]
    classes = [smoke.receipt_class(e, spec, ledger_bound={}) for e in smoke.entries_of(value)]
    assert classes.count(smoke.CONTROL) == 1 and classes.count(smoke.PROBE) == 40
    # the probe's own ledger root, apart from the smoke's; only counts and classes are kept
    assert (tmp_path / "probe" / "ledger").is_dir() and not (tmp_path / "smoke" / "shared").exists()
    kept = (tmp_path / "probe" / "attempts" / "attempt-1.json").read_text()
    assert "SECRET-REPLY-TEXT" not in kept and FAKE_KEYS[ELUCID_MODEL] not in kept
    with pytest.raises(ValueError, match="already"):
        probe(tmp_path, spec, Gateway())
    with pytest.raises(ValueError, match="own ledger"):
        smoke.run_probe(spec, env_path="unused", probe_root=tmp_path / "smoke" / "probe")
    with pytest.raises(ValueError, match="spec's probe root"):  # S2 reads the receipts at the spec's probe root
        smoke.run_probe(spec, env_path="unused", probe_root=tmp_path / "elsewhere")
    with pytest.raises(ValueError, match="own ledger"):  # the spec names a probe root apart from the smoke root
        smoke.make(tmp_path / "inside", items=items(tmp_path), selftest=selftest(tmp_path),
                   environment_found=ENVIRONMENT, probe_root=tmp_path / "inside" / "probe")
    assert stage["evidence"] == "smoke" and read_json(tmp_path / "probe" / "attempts" / "attempt-1.json")[
        "evidence"] == "smoke"


def test_s1_first_call_must_be_confirmed_before_any_other_call(tmp_path, spec):
    gateway = Gateway(echo="deepseek-other")
    value = probe(tmp_path, spec, gateway)
    assert not value["complete"] and value["stopped"] == "first_call_not_confirmed"
    assert len(gateway.bodies) == 1 and len(value["sent"]) == 1 and value["result"] is None
    assert not (tmp_path / "smoke" / smoke.STAGES_DIR / "S1.json").exists()  # S1 is not judged on a stopped attempt
    again = probe(tmp_path, spec, Gateway())  # the next attempt counts the earlier send towards the 60
    assert again["attempt"] == 2 and again["calls_before"] == 1 and again["complete"]


def test_s1_a_completion_beyond_the_probe_bound_halts_only_the_probe_ledger(tmp_path, spec):
    gateway = Gateway(over=lambda body: 100 if body["max_tokens"] == protocol.S1D_TOKENS
                      and len(body["messages"][1]["content"]) < 40 and body.get("reasoning_effort") else 10)
    value = probe(tmp_path, spec, gateway)
    # row a is sent with B_probe (100 <= 32,768); the concurrent d calls have B = 64, so a 100-token reply breaks it
    assert value["stopped"] == "ledger_stop:AssumptionBroken" and not value["complete"]
    assert not (tmp_path / "smoke" / smoke.STAGES_DIR / "S1.json").exists()
    assert (tmp_path / "probe" / "attempts" / "attempt-1.json").exists()


# ------------------------------------------------------------------------------- dispatch-time receipt classes
def test_classed_sends_stamp_the_class_at_dispatch_and_mark_frozen_resends(spec):
    m = protocol.solver_tokens(protocol.SMOKE_SOLVER, "searchqa")
    mismatch = {"ok": False, "error_type": "thinking_mismatch", "subtype": REASONING_MISMATCH, "response": "x"}
    clean = {"ok": True, "error_type": None, "response": "<answer>a</answer>"}
    sends = [{"request_sha256": "r1", "max_tokens": BOUND["searchqa"], "receipt": mismatch},
             {"request_sha256": "r1", "max_tokens": BOUND["searchqa"], "receipt": clean},
             {"request_sha256": "r2", "max_tokens": BOUND["searchqa"], "receipt": clean}]
    found = smoke.classed_sends(spec, sends, stage="S2", cell="S2/searchqa/C/q1/1", bench="searchqa",
                                body=smoke.REGISTERED_BODY, nominal=m, ledger_bound=BOUND)
    assert [e["class"] for e in found] == [smoke.PRODUCTION, smoke.RESEND, smoke.PRODUCTION]
    assert all("response" not in e["receipt"] for e in found)
    drill = smoke.classed_sends(spec, sends[2:], stage="S2", cell=DRILL, bench="searchqa", body=smoke.REGISTERED_BODY,
                                nominal=m, ledger_bound=BOUND)
    assert drill[0]["class"] == smoke.CONTROL
    # a stamp that differs from the judge's verdict is unregistered and fails the receipt criterion
    forged = [{**found[0], "class": smoke.CONTROL}]
    counted = smoke.receipt_classes(production(300) + probes() + [S1E] + forged, spec, ledger_bound=BOUND)
    assert counted["counts"]["unregistered"] == 1 and not counted["passed"]
    with pytest.raises(ValueError):
        smoke.classed_sends(spec, sends, stage="S1", cell="S1/a", bench="searchqa", body=smoke.REGISTERED_BODY,
                            nominal=m, ledger_bound=BOUND)


# ------------------------------------------------------------------------------------------ S4: the drill
def test_the_s4_fault_switch_exists_only_under_the_smoke_root(tmp_path, spec):
    with pytest.raises(ValueError, match="smoke root"):
        smoke.FaultSwitch(spec, tmp_path / "pilot" / "unit", fail_at=1)
    switch = smoke.FaultSwitch(spec, tmp_path / "smoke" / "S4" / "accept-b1", fail_at=2)
    switch.tick()
    with pytest.raises(SandboxUnavailable, match="registered S4 drill"):
        switch.tick()
    assert switch.fired and switch.calls == 2

    class NoDocker:
        binary = None

    drilled = smoke.FaultSwitch(spec, tmp_path / "smoke" / "S4" / "accept-b2", fail_at=1)
    worker = drilled.worker(docker=NoDocker())
    assert isinstance(worker, sandbox.Worker)
    worker.start(type("P", (), {"sha256": "0" * 64, "procedures": ()})(), kind="cell")
    with pytest.raises(SandboxUnavailable, match="registered S4 drill"):
        worker.call("fx-note", "applies", [{}], timeout_s=2)


# ------------------------------------------------------------------------------------- the stage runs (§10)
def test_stage_slices_are_the_registered_disjoint_cuts():
    searchqa = [{"task_id": "q%03d" % n} for n in range(280)]
    cuts = {stage: [i["task_id"] for i in smoke._slice(stage, "searchqa", searchqa)] for stage in ("S2", "SN1", "S4")}
    assert [len(cuts[s]) for s in ("S2", "SN1", "S4")] == [20, 200, 60]
    assert len(set(cuts["S2"]) | set(cuts["SN1"]) | set(cuts["S4"])) == 280
    games = [{"task_id": "g%02d" % n} for n in range(12)]
    assert {i["task_id"] for i in smoke._slice("S2", "alfworld", games)}.isdisjoint(
        i["task_id"] for i in smoke._slice("SN1", "alfworld", games))
    with pytest.raises(ValueError, match="slice"):
        smoke._slice("SN1", "searchqa", searchqa[:100])
    with pytest.raises(ValueError, match="20 fixtures"):
        smoke._slice("SN1", "officeqa", [{"task_id": "f%02d" % n} for n in range(20)])


def test_the_rehearsal_reply_uses_each_benchs_registered_carrier():
    alf = json.dumps({"admissible_commands": ["look", "go to fridge 1"]})
    assert smoke._rehearsal_reply(smoke.solver.ALF_SYSTEM, alf) == "<action>go to fridge 1</action>"
    assert smoke._rehearsal_reply("system", json.dumps({"question": "q", "options": {"A": "1"}})) == "<answer>A</answer>"
    assert smoke._rehearsal_reply("system", json.dumps({"question": "q"})) == "<answer>1</answer>"


# ------------------------------------------------------------- S-E6 and the S4 drill's operator step (§9.3, §10)
def _cell(bench, *, tokens, enabled=None, final=True, request_bytes=100):
    """A stored cell record as S-E6 reads it: its bench and arm, the enabled procedures, the verdict, the sends."""
    return {"cell": {"benchmark": bench, "arm": "S" if enabled else "C"}, "enabled": enabled,
            "final": {"correct": True} if final else None,
            "sends": [{"receipt": {"usage": {"prompt_tokens": tokens - 1, "completion_tokens": 1}},
                       "request_bytes": request_bytes}]}


def test_se6_measures_card_and_procedure_cells_and_charges_a_stopped_cell():
    found = smoke.measured_cells([_cell("searchqa", tokens=10), _cell("searchqa", tokens=30, enabled=["fx-print"]),
                                  _cell("searchqa", tokens=50, final=False, request_bytes=900)])
    assert found["per_class"]["searchqa"] == {"card": {"cells": 1, "tokens": 10},
                                              "procedure": {"cells": 1, "tokens": 30}}
    assert found["per_arm"]["searchqa"] == {"C": {"cells": 1, "tokens": 10}, "S": {"cells": 1, "tokens": 30}}
    assert found["actual"] == 90 and found["request_bytes"] == {"searchqa": 900}
    per_cell = smoke._per_cell({b: {"card": {"cells": 2, "tokens": 20}} for b in protocol.BENCHES})
    assert per_cell["officeqa"] == {"card": 10.0, "procedure": 10.0 * float(protocol.PROCEDURE_ARM_FACTOR[1]),
                                    "procedure_assumed": True}
    with pytest.raises(ValueError, match="no card cell"):
        smoke._per_cell({})


def test_se6_projects_every_solver_scope_and_prices_a_redo_as_one_acceptance_block():
    plan = protocol.PILOTS[protocol.PILOT]
    for chain in protocol.CHAINS:
        caps, cells = budgets.chain_caps(chain), smoke._scope_cells(chain)
        assert set(cells) <= set(caps)
        assert all(n == budgets.ROOT or n.endswith(":glm") or ":role:" in n for n in set(caps) - set(cells))
        assert cells[chain + ":test"] == [protocol.TEST_READ_CELLS[protocol.PILOT]]
        assert len(cells[chain + ":redo"]) == len(cells[chain + ":solver"]) == len(plan["order"])
        for k, bench in enumerate(plan["order"], 1):
            whole = protocol.MAX_SCHEDULE_CELLS[bench]["accept"][bench]
            share = protocol.SLICES[bench]["blocks"]
            for attempt in (2, 3):  # §9.3: a pause redoes one acceptance block in its own sub-scope
                redo = cells[budgets.solver_scopes(chain, bench, k, "accept", attempt)[-1]]
                assert redo == [{bench: (whole[0] / share, whole[1] / share)}]
            run = budgets.solver_scopes(chain, bench, k, "run", 2)[-1]
            assert cells[run] == [protocol.MAX_SCHEDULE_CELLS[bench]["run"]]


def test_m1_se6_scope_cells_and_glm_scopes_of_main_are_its_five_steps_at_its_caps():
    """Registrar 17:0x: S-E6 of the main experiment's smoke projects ``main`` -- main's schedule
    (``MAIN_SCHEDULE_CELLS``) on main's caps, its test read, a redo as one acceptance block, and its GLM scopes at the
    owner's role caps (engineer 5M, examiner 5M, research 9.2M per step)."""
    for chain in protocol.CHAINS:
        caps, cells = budgets.chain_caps(chain, "main"), smoke._scope_cells(chain, "main")
        assert set(cells) == {n for n in caps if n != budgets.ROOT and not n.endswith(":glm") and ":role:" not in n}
        assert cells[chain + ":test"] == [protocol.TEST_READ_CELLS["main"]]
        assert len(cells[chain + ":redo"]) == len(cells[chain + ":solver"]) == len(protocol.BENCHES) == 5
        for k, bench in enumerate(protocol.BENCHES, 1):
            whole = protocol.MAIN_SCHEDULE_CELLS[bench]["accept"][bench]
            share = protocol.SLICES[bench]["blocks"]
            assert cells[budgets.solver_scopes(chain, bench, k, "accept", 2)[-1]] == [
                {bench: (whole[0] / share, whole[1] / share)}]
            assert cells[budgets.solver_scopes(chain, bench, k, "selftest")[-1]] == [
                protocol.MAIN_SCHEDULE_CELLS[bench]["selftest"]]
    measured = {role: {"calls": 2, "tokens": 20_000, "per_call": 10_000.0, "request_bytes": 50_000}
                for role in budgets.ROLES}
    found = smoke.glm_projection(measured, "main")
    caps = {**budgets.chain_caps("G", "main"), **budgets.chain_caps("D", "main")}
    assert set(found) == {name for name in caps if name.endswith(":glm") or ":role:" in name}
    assert found["G:xs:searchqa:1:role:engineer"]["cap"] == found["D:xs:alfworld:5:role:examiner"]["cap"] == 5_000_000
    assert found["G:xs:livemath:3:role:examiner:research"]["cap"] == 9_200_000
    per_step = sum(10_000 * n for n in smoke.MAX_ROLE_CALLS.values())
    assert found["D:glm"]["settled"] == 5 * per_step and found["D:glm"]["cap"] == protocol.MAIN_GLM_CAP
    assert all(entry["fits"] for entry in found.values())


def test_smoke_recovery_writes_the_owner_format_only_into_a_paused_s4_attempt(tmp_path, spec, capsys):
    parser = argparse.ArgumentParser()
    smoke.add_arguments(parser.add_subparsers(dest="command", required=True))
    root = tmp_path / "smoke" / smoke.UNITS_DIR
    paused = root / smoke.S4_DIR / "s1-searchqa" / "accept" / "attempt-1"
    other = root / "S2" / "searchqa" / "attempt-1"
    confirm = root / smoke.S4_DIR / "confirm-1" / "attempt-1"  # the next process run confirms in a new unit
    for attempt in (paused, other, confirm):
        attempt.mkdir(parents=True)
        write_json(attempt / "status.json", protocol.record("unit-status", "smoke", {
            "status": "paused", "kind": "sandbox", "reason": "drill", "cell": "c1"}))
    command = ["smoke-recovery", "--spec", str(tmp_path / "smoke" / smoke.SPEC), "--decision", "redo the round",
               "--attempt"]
    for refused in (other, confirm):
        with pytest.raises(ValueError, match="paused attempt of an S4 unit"):
            smoke.recovery_cli(parser.parse_args(command + [str(refused)]))
    assert smoke.recovery_cli(parser.parse_args(command + [str(paused)])) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["recovery"] == str(paused / "recovery.json") and printed["by"] == "owner"
    assert read_json(paused / "recovery.json")["decision"] == smoke.SMOKE_LABEL + ": redo the round"
    assert recovered(paused) and not (other / "recovery.json").exists()
    with pytest.raises(ValueError, match="decision"):
        smoke.write_recovery(spec, paused, decision=" ")
