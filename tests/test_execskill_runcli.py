"""The run subcommands of ``scripts/run_execskill.py`` (``skillopt.execskill.runcli``; implementation plan §6, tickets
A13-1, C2-1 §1, fixer-1): the parsed arguments and each handler on a fixture manifest -- terminate (§9.4), run on an
ended chain, one step in a child with its exit codes and only on a chain whose first call is confirmed (registrar
addendum 2026-10-22 15:3x, ticket P2C-1), a read unit's consent and exit codes, the report's refusal
before every chain has ended and its chains that read nothing, the report's run-root canary scan pause as exit 3 or 5
(ticket PR-C31-1), the owner's addendum sealed once. Offline: fake
credentials, a fake docker CLI, the manifest's code and image verification recorded instead of run (it has its own
tests), every model call refused."""
from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

import pytest

from skillopt.coevo5.budget import Budget
from skillopt.continual_eval.core import read_json, safe_path, write_json
from skillopt.execskill import budgets, chain, manifest, protocol, runcli, step
from skillopt.execskill.cells import Pause
from skillopt.execskill.package import empty
from skillopt.execskill.protocol import FORMAL_ADDENDUM, FORMAL_ADDENDUM_DOCUMENT, ORDER, TEST_ARMS, verified
from tests.test_execskill_manifest import pilot


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    """A sealed fixture manifest at ``<tmp>/manifest.json`` whose loads record their verification."""
    checked = []
    monkeypatch.setattr(manifest, "verify_unit", lambda value, *, docker=None: checked.append(value["root"]))
    value = pilot(tmp_path, monkeypatch)
    return SimpleNamespace(path=str(tmp_path / "manifest.json"), value=value, root=safe_path(value["root"]),
                           run=value[protocol.RECORD_HASH], checked=checked)


def parse(*argv):
    parser = argparse.ArgumentParser()
    runcli.add_arguments(parser.add_subparsers(dest="command", required=True))
    return parser.parse_args(argv)


def test_the_subcommands_take_the_command_lines_arguments():
    assert set(runcli.HANDLERS) == {"run", "terminate", "step-unit", "evaluate-unit", "report", "seal-addendum"}
    assert vars(parse("run", "--manifest", "m.json", "--chain", "G")) == {"command": "run", "manifest": "m.json",
                                                                          "chain": "G"}
    assert parse("terminate", "--manifest", "m", "--chain", "D", "--decision", "stop").decision == "stop"
    for name in ("step-unit", "evaluate-unit"):
        assert parse(name, "--manifest", "m", "--spec", "s.json").spec == "s.json"
    assert parse("report", "--manifest", "m", "--out", "o").out == "o"
    assert vars(parse("seal-addendum", "--manifest", "m")) == {"command": "seal-addendum", "manifest": "m"}
    for argv in (("run", "--manifest", "m", "--chain", "X"), ("run", "--manifest", "m"),
                 ("terminate", "--manifest", "m", "--chain", "G"), ("report", "--manifest", "m"),
                 ("step-unit", "--manifest", "m")):
        with pytest.raises(SystemExit):
            parse(*argv)


def test_terminate_run_and_report_on_chains_that_ended_before_their_read(fixture, tmp_path, capsys):
    with pytest.raises(ValueError, match="neither read nor ended"):
        runcli.report(SimpleNamespace(manifest=fixture.path, out=str(tmp_path / "early")))
    assert not (tmp_path / "early").exists()
    decision = SimpleNamespace(manifest=fixture.path, chain="G", decision="Stop chain G before its read.")
    assert runcli.terminate(decision) == chain.EXIT_COMPLETE
    assert json.loads(capsys.readouterr().out) == {"status": "terminated", "chain": "G", "run": fixture.run}
    ended = verified(read_json(fixture.root / "G" / "chain-terminated.json"), "chain-terminated")
    assert ended["identity"] == {"run": fixture.run, "chain": "G"} and ended["evidence"] == fixture.value["evidence"]
    with pytest.raises(ValueError, match="ended"):
        runcli.terminate(decision)  # once
    assert runcli.run(SimpleNamespace(manifest=fixture.path, chain="G")) == chain.EXIT_PAUSED
    assert json.loads(capsys.readouterr().out) == {"status": "terminated"}
    with pytest.raises(ValueError, match="neither read nor ended"):  # chain D still runs: nothing is written
        runcli.report(SimpleNamespace(manifest=fixture.path, out=str(tmp_path / "half")))
    assert not (tmp_path / "half").exists()
    runcli.terminate(SimpleNamespace(manifest=fixture.path, chain="D", decision="Stop chain D as well."))
    capsys.readouterr()
    assert runcli.report(SimpleNamespace(manifest=fixture.path, out=str(tmp_path / "readout"))) == chain.EXIT_COMPLETE
    assert json.loads(capsys.readouterr().out) == {"D": "not_read", "G": "not_read"}
    assert list((tmp_path / "readout").iterdir()) == []
    with pytest.raises(ValueError, match="new directory"):
        runcli.report(SimpleNamespace(manifest=fixture.path, out=str(tmp_path / "readout")))
    assert len(fixture.checked) == 8  # every handler verified the manifest before acting


def test_step_unit_runs_one_step_of_the_order_and_maps_its_pause_to_the_exit_code(fixture, tmp_path, monkeypatch):
    seen, outcomes = [], iter([None, Pause("awaiting_owner_decision", "attempt-1", "D/s1-x/run"),
                               Pause("solver_unavailable", "the endpoint is down", "cell-1")])

    def run_step(setting, chain_, bench, k, parent, *, services, chain_root):
        seen.append((chain_, bench, k, parent.sha256, chain_root, setting.run, isinstance(services, step.Services)))
        outcome = next(outcomes)
        if outcome is not None:
            raise outcome

    monkeypatch.setattr(step, "run_step", run_step)
    spec = tmp_path / "step-1.json"
    write_json(spec, {"chain": "D", "k": 1, "bench": ORDER[0]})
    args = SimpleNamespace(manifest=fixture.path, spec=str(spec))
    confirm = fixture.root / "D" / chain.CONFIRM
    with pytest.raises(ValueError, match="no confirmed first call"):  # ticket P2C-1: nothing starts, nothing written
        runcli.step_unit(args)
    assert not budgets.ledger_root(fixture.root, "D").exists() and not seen
    for identity, passed in (({"run": "another-run", "chain": "D"}, True), ({"run": fixture.run, "chain": "G"}, True),
                             ({"run": fixture.run, "chain": "D"}, False)):
        write_json(confirm, protocol.record("first-call", fixture.value["evidence"], {"identity": identity,
                                                                                    "passed": passed}))
        with pytest.raises(ValueError, match="another run"):
            runcli.step_unit(args)
        confirm.unlink()
    assert not seen
    write_json(confirm, protocol.record("first-call", fixture.value["evidence"], {
        "identity": {"run": fixture.run, "chain": "D"}, "passed": True}))  # as chain.first_call writes a pass
    assert [runcli.step_unit(args) for _ in range(3)] == [chain.EXIT_COMPLETE, chain.EXIT_AWAITING, chain.EXIT_PAUSED]
    start = empty(step="D/s0", evidence=fixture.value["evidence"])
    assert seen[0] == ("D", ORDER[0], 1, start.sha256, fixture.root / "D", fixture.run, True)
    ledger = Budget(budgets.ledger_root(fixture.root, "D")).snapshot()  # declared as chain.run declares it
    assert {scope: value["cap"] for scope, value in ledger.items()} == {**budgets.chain_caps("D"),
                                                                        **budgets.first_call_caps("D")}
    later = tmp_path / "step-2.json"
    write_json(later, {"chain": "D", "k": 2, "bench": ORDER[1]})
    with pytest.raises(ValueError, match="has not finished"):
        runcli.step_unit(SimpleNamespace(manifest=fixture.path, spec=str(later)))
    for n, bad in enumerate(({"chain": "D", "k": 1, "bench": ORDER[1]}, {"chain": "X", "k": 1, "bench": ORDER[0]},
                             {"chain": "D", "k": 1}, {"chain": "D", "k": len(ORDER) + 1, "bench": ORDER[0]})):
        write_json(tmp_path / ("bad-%d.json" % n), bad)
        with pytest.raises(ValueError):
            runcli.step_unit(SimpleNamespace(manifest=fixture.path, spec=str(tmp_path / ("bad-%d.json" % n))))
    assert len(seen) == 3


def test_evaluate_unit_needs_consent_and_its_registered_unit(fixture, tmp_path):
    unit_root = fixture.root / "D" / "test" / "officeqa"
    spec = tmp_path / "read.json"
    write_json(spec, {"chain": "D", "bench": "officeqa", "package_sha256": "0" * 64, "unit_root": str(unit_root)})
    args = SimpleNamespace(manifest=fixture.path, spec=str(spec))
    with pytest.raises(ValueError, match="consent"):
        runcli.evaluate_unit(args)
    write_json(fixture.root / "shared" / "consent.json", {
        "test_evaluation": True, "sheet_test_qualification": False, "multi_arm_arms": list(TEST_ARMS), "by": "owner",
        "date": "2026-10-22", "note": "Read the pilot's test sets once."})
    elsewhere = tmp_path / "elsewhere.json"
    write_json(elsewhere, {"chain": "D", "bench": "officeqa", "package_sha256": "0" * 64,
                           "unit_root": str(tmp_path / "another-unit")})
    with pytest.raises(ValueError, match="registered directory"):
        runcli.evaluate_unit(SimpleNamespace(manifest=fixture.path, spec=str(elsewhere)))
    write_json(unit_root / "attempt-1" / "status.json", {"status": "paused"})  # no owner decision recorded
    assert runcli.evaluate_unit(args) == chain.EXIT_AWAITING
    write_json(unit_root / "unit.json", {"status": "complete"})
    assert runcli.evaluate_unit(args) == chain.EXIT_COMPLETE


def test_a_paused_root_scan_is_the_reports_exit_code_not_a_traceback(fixture, tmp_path, monkeypatch, capsys):
    """Ticket PR-C31-1 item 2: ``readout.report`` unseals each chain, and the run-root canary scan before the first
    unseal (registrar decision C3-1 (b)) can pause; ``report`` prints the pause (kind, reason, where -- never text) and
    returns 3 for a hit, 5 while the hit awaits the owner's recorded decision."""
    from skillopt.execskill import readout

    raised = []

    def report(value, *, out):
        raise raised[-1]

    monkeypatch.setattr(readout, "report", report)
    args = SimpleNamespace(manifest=fixture.path, out=str(tmp_path / "report"))
    raised.append(Pause("canary_hit", "3 hits", "G/root-scan"))
    assert runcli.report(args) == chain.EXIT_PAUSED == 3
    assert json.loads(capsys.readouterr().out) == {"paused": "canary_hit", "reason": "3 hits", "at": "G/root-scan"}
    raised.append(Pause("awaiting_owner_decision", "attempt-1", "G/root-scan"))
    assert runcli.report(args) == chain.EXIT_AWAITING == 5
    assert json.loads(capsys.readouterr().out)["paused"] == "awaiting_owner_decision"
    assert not (tmp_path / "report").exists()


def test_seal_addendum_seals_the_owners_document_once(fixture, capsys):
    document = fixture.root / FORMAL_ADDENDUM_DOCUMENT
    document.parent.mkdir(parents=True, exist_ok=True)
    document.write_text("Formal chain: steps 3 to 5 follow the pilot's two steps.\n", encoding="utf-8")
    assert runcli.seal_addendum(SimpleNamespace(manifest=fixture.path)) == chain.EXIT_COMPLETE
    sealed = verified(read_json(fixture.root / FORMAL_ADDENDUM), "formal-addendum")
    assert json.loads(capsys.readouterr().out) == {"addendum": FORMAL_ADDENDUM_DOCUMENT, "sha256": sealed["sha256"],
                                                   "written_at": sealed["written_at"],
                                                   "record_sha256": sealed[protocol.RECORD_HASH]}
    assert sealed["evidence"] == fixture.value["evidence"]
    with pytest.raises(ValueError, match="sealed once"):
        runcli.seal_addendum(SimpleNamespace(manifest=fixture.path))
