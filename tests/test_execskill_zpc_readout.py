"""Synthetic single-panel unseal, root scan and report; no real panel or executable worker."""
import pytest

from tests.execskill_zpc_fakes import tmp_path

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import evaluation, package, profiles as p, readout
from skillopt.execskill.cells import Pause

BENCH = "zebralogic"
EVIDENCE = "engineering_fixture"
RUN = "synthetic-single-panel-read"
PROC = "fx-zebra-readout"
CANARY = "Only this authored synthetic panel contains the cerulean canary sentence."


def completed(root, chain):
    """Persist only synthetic sealed outcome records, with no puzzle or gold grid."""
    chain_root = root / chain
    procedure = package.Procedure(PROC, BENCH, "Authored fixture note", ("applies", "before_call"),
        "def applies(view):\n    return True\ndef before_call(view, state):\n    return {}\n", EVIDENCE,
        max_note_chars=100)
    final = package.Package((procedure,), step=chain + "/s1-zebralogic", evidence=EVIDENCE)
    package.save(chain_root, final)
    unit = chain_root / "test" / BENCH
    names = []
    for index in range(4):
        for arm in ("C", "F", "T_F", "P_F", "withhold:" + PROC):
            name = "%s-%02d" % (arm.replace(":", "-"), index)
            names.append(name)
            token = "pass" if arm == "F" else "fail"
            value = {
                "cell": {"id": name, "arm": arm, "task_id": "fixture-%02d" % index, "run": 0, "block": "b1"},
                "final": {"token": token, "kind": None},
                "judge": {"v2": token, "official": token, "final": token, "lenient": token == "pass",
                          "format": {"grid": True, "violation": False}, "flags": [], "carrier": "text"},
                "enabled": [PROC] if arm == "F" else [], "shared_with": None, "answered": True,
                "fault_kinds": {}, "worst_delivery": "delivered", "dispatch_ts": index,
                "finish_ts": index + 0.1, "calls": [{"completion_tokens": 20}], "solver_route": None}
            write_json(unit / "attempt-1" / "cells" / (name + ".json"), p.record("evaluation-cell", EVIDENCE, value))
    write_json(unit / "unit.json", p.record("evaluation", EVIDENCE, {
        "chain": chain, "run": RUN, "bench": BENCH, "attempt": "attempt-1", "cells": names}))
    write_json(chain_root / "test-read.json", p.record("test-read", EVIDENCE,
        {"status": "read", "package_sha256": final.sha256}))
    write_json(chain_root / "chain-complete.json", p.record("chain-complete", EVIDENCE, {"chain": chain}))
    write_json(root / "shared" / "owner-continuation.json", {
        "by": "owner", "date": "2026-10-25", "decision": "stop", "note": "Authored fixture read only."})
    write_json(root / evaluation.READ_CANARIES, p.record("test-read-canaries", EVIDENCE, {
        "configuration": p.ZEBRA_PC_V1, "extends": None, "counts": {BENCH: 1},
        "canaries": [evaluation.canary(CANARY)]}))
    return {"root": str(root), p.RECORD_HASH: RUN, "evidence": EVIDENCE,
            "configuration": p.ZEBRA_PC_V1, "data": {"launchable_chains": [chain]}}


@pytest.mark.parametrize("chain", ("G", "D"))
def test_single_panel_report_reaches_real_root_scan_and_readout(tmp_path, chain):
    root = tmp_path / "run"
    manifest = completed(root, chain)
    out = tmp_path / "readout"
    found = readout.report(manifest, out=out)
    value = p.verified(read_json(out / ("readout-%s.json" % chain)), "readout")
    assert found == {chain: value[p.RECORD_HASH]}
    assert value["evidence_kind"] == "pipeline_control"
    assert set(value["arms"]) == set(value["q1_home"]) == {BENCH}
    assert value["q1_home"][BENCH]["n"] == 4 and value["q1_home"][BENCH]["mean"] == 1
    assert value["q2_similar"] == {} and value["q3_noninferiority"] is None
    scan = p.verified(read_json(root / chain / "root-scan" / "attempt-1" / "scan.json"), "root-canary-scan")
    assert scan["canaries"] == 1 and scan["hits"] == 0
    assert not (root / ("D" if chain == "G" else "G")).exists()
    assert not (root / p.CANARIES).exists()
    # Repeated publication reuses the verified marker and scan without another panel or scan attempt.
    assert readout.report(manifest, out=tmp_path / "readout-again") == found
    assert not (root / chain / "root-scan" / "attempt-2").exists()


def test_single_panel_canary_hit_blocks_real_report_before_scores(tmp_path):
    root = tmp_path / "run"
    manifest = completed(root, "D")
    write_json(root / "D" / "training-leak.json", {"question": CANARY})
    out = tmp_path / "readout"
    with pytest.raises(Pause, match="canary_hit"):
        readout.report(manifest, out=out)
    scan = p.verified(read_json(root / "D" / "root-scan" / "attempt-1" / "scan.json"), "root-canary-scan")
    assert scan["hits"] == 1 and scan["by_bench"] == {BENCH: 1}
    assert not out.exists() and not (root / "D" / evaluation.UNSEALED).exists()
