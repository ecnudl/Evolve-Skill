"""D-only ALF postread report through the real unseal and root-canary scan; authored sealed outcomes only."""
import pytest

from tests.execskill_zpc_fakes import tmp_path
from tests.test_execskill_zpc_pipeline import offline

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import evaluation, package, profiles as p, readout
from skillopt.execskill.cells import Pause

BENCH = "alfworld"
EVIDENCE = "engineering_fixture"
RUN = "authored-alf-single-panel-read"
PROC = "fx-alf-readout"
CANARY = "valid_unseen/pick_and_place_simple-Mug-None-Cabinet-441/trial_AUTHORED_CANARY/game.tw-pddl"


def completed(root, *, canary_configuration=None):
    procedure = package.Procedure(PROC, BENCH, "Authored public task tracker", ("applies", "alf_before_step"),
        'def applies(view):\n    return "task_text" in view\n'
        'def alf_before_step(view, state):\n    return {"fields": {}, "discourage": []}\n',
        EVIDENCE, max_note_chars=100, policy_version=p.POLICY_VERSIONS[p.ALFWORLD_V1])
    final = package.Package((procedure,), step="D/s1-alfworld", evidence=EVIDENCE)
    package.save(root / "D", final)
    unit, names = root / "D" / "test" / BENCH, []
    for index in range(12):
        for arm in ("C", "F", "T_F", "P_F", "withhold:" + PROC):
            name = "%s-%02d" % (arm.replace(":", "-"), index)
            names.append(name)
            token = "pass" if arm == "F" else "fail"
            value = {
                "cell": {"id": name, "arm": arm, "task_id": "authored-game-%02d" % index, "run": 0,
                         "block": "b1", "room": "authored-room-%d" % (index // 2)},
                "final": {"token": token, "kind": None},
                "judge": {"v2": token, "official": token, "final": token, "lenient": token == "pass",
                          "format": {"action_valid": True, "violation": False}, "flags": [], "carrier": "native"},
                "enabled": [PROC] if arm == "F" else [], "shared_with": None, "answered": True,
                "fault_kinds": {}, "worst_delivery": "delivered", "dispatch_ts": index,
                "finish_ts": index + 0.1, "calls": [{"completion_tokens": 20}, {"completion_tokens": 30}],
                "solver_route": None}
            write_json(unit / "attempt-1" / "cells" / (name + ".json"), p.record("evaluation-cell", EVIDENCE, value))
    write_json(unit / "unit.json", p.record("evaluation", EVIDENCE, {
        "chain": "D", "run": RUN, "bench": BENCH, "attempt": "attempt-1", "cells": names}))
    write_json(root / "D" / "test-read.json", p.record("test-read", EVIDENCE,
        {"status": "read", "package_sha256": final.sha256}))
    write_json(root / "D" / "chain-complete.json", p.record("chain-complete", EVIDENCE, {"chain": "D"}))
    write_json(root / "shared" / "owner-continuation.json", {
        "by": "owner", "date": "2026-10-26", "decision": "stop", "note": "Authored fixture read only."})
    write_json(root / evaluation.READ_CANARIES, p.record("test-read-canaries", EVIDENCE, {
        "configuration": canary_configuration or p.ALFWORLD_V1, "extends": None, "counts": {BENCH: 1},
        "canaries": [evaluation.canary(CANARY)]}))
    return {"root": str(root), p.RECORD_HASH: RUN, "evidence": EVIDENCE,
            "configuration": p.ALFWORLD_V1, "data": {"launchable_chains": ["D"]}}


def test_alf_only_report_unseals_and_scans_without_a_chain_g(tmp_path):
    root, out = tmp_path / "run", tmp_path / "readout"
    manifest = completed(root)
    found = readout.report(manifest, out=out)
    value = p.verified(read_json(out / "readout-D.json"), "readout")
    assert found == {"D": value[p.RECORD_HASH]}
    assert value["learned"] == [BENCH] and set(value["arms"]) == set(value["q1_home"]) == {BENCH}
    home = value["q1_home"][BENCH]
    assert home["n"] == 12 and home["rooms"] == 6 and home["df"] == 5 and home["mean"] == 1
    assert value["q2_similar"] == {} and value["q3_noninferiority"] is None and "stages" not in value
    assert all(row["answer_tag_share"] is None for row in value["arms"][BENCH]["F"]["windows"])
    scan = p.verified(read_json(root / "D" / "root-scan" / "attempt-1" / "scan.json"), "root-canary-scan")
    assert scan["canaries"] == 1 and scan["hits"] == 0
    assert (root / "D" / evaluation.UNSEALED).is_file()
    assert not (root / "G").exists() and not (out / "readout-G.json").exists()
    assert not (root / p.CANARIES).exists()  # The isolated ALF record is sufficient.
    assert readout.report(manifest, out=tmp_path / "readout-again") == found
    assert not (root / "D" / "root-scan" / "attempt-2").exists()


def test_alf_not_read_report_needs_only_d_and_opens_no_read_or_scan(tmp_path):
    root = tmp_path / "run"
    write_json(root / "D" / "test-read.json", p.record("test-read", EVIDENCE, {"status": "not_read"}))
    manifest = {"root": str(root), p.RECORD_HASH: RUN, "evidence": EVIDENCE,
                "configuration": p.ALFWORLD_V1, "data": {"launchable_chains": ["D"]}}
    out = tmp_path / "readout"
    assert readout.report(manifest, out=out) == {"D": "not_read"}
    assert list(out.iterdir()) == [] and list(root.iterdir()) == [root / "D"]
    assert not (root / "D" / "root-scan").exists() and not (root / "D" / evaluation.UNSEALED).exists()


def test_alf_canary_identity_is_passed_to_real_unseal_and_rejects_another_profile(tmp_path):
    root = tmp_path / "run"
    manifest = completed(root, canary_configuration=p.ZEBRA_PC_V4)
    out = tmp_path / "readout"
    with pytest.raises(ValueError, match="ALFWorld canaries"):
        readout.report(manifest, out=out)
    assert not out.exists() and not (root / "D" / evaluation.UNSEALED).exists()


def test_alf_canary_hit_blocks_real_report_before_any_score_is_published(tmp_path):
    root = tmp_path / "run"
    manifest = completed(root)
    write_json(root / "D" / "authored-leak.json", {"game_file": CANARY})
    out = tmp_path / "readout"
    with pytest.raises(Pause, match="canary_hit"):
        readout.report(manifest, out=out)
    scan = p.verified(read_json(root / "D" / "root-scan" / "attempt-1" / "scan.json"), "root-canary-scan")
    assert scan["hits"] == 1 and scan["by_bench"] == {BENCH: 1}
    assert not out.exists() and not (root / "D" / evaluation.UNSEALED).exists()
