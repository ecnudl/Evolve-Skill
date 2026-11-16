"""v2.3 replay tests over authored records only: no data/, network, models, sandboxes or program execution."""
from __future__ import annotations

import functools
import json
import os
import socket
import tempfile
from pathlib import Path

import pytest

from scripts import execskill_v23_replay as replay
from skillopt.coevo5.calls import _request_hash
from skillopt.continual_eval.core import write_json
from skillopt.execskill import acceptance, stats_ext
from skillopt.execskill.cells import cell_id
from skillopt.execskill.package import save
from skillopt.execskill.protocol import PRACTICAL_RULE, record
from tests.test_execskill_acceptance import N, make_cells, packages, seal


@pytest.fixture
def root():
    # pytest's own temporary folder contains the prohibited substring "test"; the reader correctly refuses it.
    with tempfile.TemporaryDirectory(prefix="execskill-v23-replay-", dir=os.path.realpath(os.environ.get('TMPDIR') or '/tmp')) as folder:
        yield Path(folder)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("No networking in an offline replay")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(stats_ext, "signflip", functools.partial(stats_ext.signflip, n=200))
    monkeypatch.setattr(stats_ext, "bootstrap_ci", functools.partial(stats_ext.bootstrap_ci, resamples=100))


def trajectory(unit, arm, item, package, *, bench="officeqa", enabled=(), run=0, reply="answer", request="same",
               faults=()):
    return record("trajectory", "smoke", {"cell": cell_id(unit, arm, item, run), "unit": unit, "arm": arm,
        "bench": bench, "task_id": item, "run": run, "package_sha256": package,
        "calls": [{"purpose": "first", "system": "system", "user": request,
                   "request_sha256": _request_hash("system", request), "receipt": {"delivery": "delivered"}}],
        "replies": [reply], "route": {"enabled": list(enabled), "faults": []}, "shell": {"faults": list(faults)}})


def put_trajectory(attempt, value):
    path = attempt / "trajectories" / (value["cell"] + ".json")
    write_json(path, value)
    return path


def stored_round(root, rule, *, requests=None, kind="empty", dup=False):
    directory = root / "G" / "s2-officeqa" / "accept"
    sealed = seal(directory, kind, rule=rule, dup=dup)
    parent, candidate = packages(kind)
    save(root / "G", parent)
    save(root / "G", candidate)
    attempt = directory / "attempt-1"
    cells = []
    for synthetic in make_cells(sealed):
        inner = {"id": cell_id(sealed["unit"], synthetic["arm"], synthetic["task_id"], synthetic["run"]),
                 "unit": sealed["unit"], "unit_attempt": attempt.name, "benchmark": sealed["bench"],
                 "block": sealed["blocks"][synthetic["task_id"]],
                 **{k: synthetic[k] for k in ("arm", "task_id", "run", "set")}}
        cell = record("cell", "smoke", {**synthetic, "cell": inner})
        write_json(attempt / "cells" / (inner["id"] + ".json"), cell)
        cells.append(cell)
        changed = synthetic["arm"] in ("S'", "P_y", "P_i")
        put_trajectory(attempt, trajectory(sealed["unit"], synthetic["arm"], synthetic["task_id"],
                       candidate.sha256 if changed else parent.sha256, enabled=[N.id] if changed else [],
                       run=synthetic["run"], request=requests(synthetic, sealed) if requests else "same"))
    decision = acceptance.decide(cells, sealed)
    write_json(attempt / "decision" / "decision.json", decision)
    return sealed, decision


@pytest.mark.parametrize("rule", [None, PRACTICAL_RULE], ids=["v21", "v22"])
def test_stored_decision_reproduces_and_t1_substitutes_without_changing_input(root, rule):
    sealed, decision = stored_round(root, rule)
    before = {str(p): p.read_bytes() for p in root.rglob("*.json")}
    found = replay.replay(root)
    after = {str(p): p.read_bytes() for p in root.rglob("*.json")}
    assert before == after
    result = found["acceptance"][0]["attempts"][0]
    assert result["reproduced"] and result["reproduced_sha256"] == decision["record_sha256"]
    assert result["dispatch"] == {"actual": 900, "under_t1": 240,
        "by_arm": {arm: {"actual": 180, "under_t1": 120 if arm in ("S", "C") else 0,
                         "avoided": 60 if arm in ("S", "C") else 180}
                   for arm in ("S", "S'", "C", "P_y", "P_i")}}
    assert result["t1_cells_not_dispatched"] == 660
    assert result["identical_all"]["real_astar_items"] == result["identical_all"]["items"] == 15
    assert result["what_if_decision"]["contrasts"]["S'-S"]["whole_batch"] == 0
    assert result["what_if_decision"]["contrasts"]["S'-S"]["n"] == len(sealed["plan"]["astar"])
    assert len(result["reuse_plan"]["card_sample"]["items"]) == 30
    assert found["model_calls"] == found["program_executions"] == 0


def test_replay_full_classes_share_nonparent_arms_and_report_dispatch_per_arm(root):
    def requests(cell, sealed):
        return {"S": "parent", "S'": "candidate", "C": "card", "P_y": "card", "P_i": "card"}[cell["arm"]]
    stored_round(root, PRACTICAL_RULE, requests=requests, kind="new")
    result = replay.replay(root)["acceptance"][0]["attempts"][0]
    assert result["reproduced"]
    assert result["dispatch"]["actual"] == 900 and result["dispatch"]["under_t1"] == 540
    assert result["dispatch"]["by_arm"]["P_y"]["under_t1"] == 0
    assert result["dispatch"]["by_arm"]["P_i"]["under_t1"] == 0
    assert result["dispatch"]["by_arm"]["C"]["under_t1"] == 180
    assert result["identical_all"]["items"] == 0
    assert all(arms["P_y"] == arms["P_i"] == "C" for arms in result["reuse_plan"]["reused"]["real"].values())
    assert result["what_if_decision"]["contrasts"]["S'-S"]["n"] == 45


def test_replay_all_identical_without_instrument_dispatches_nothing(root):
    stored_round(root, PRACTICAL_RULE, kind="new")
    result = replay.replay(root)["acceptance"][0]["attempts"][0]
    assert result["reproduced"] and result["reuse_plan"]["card_sample"] is None
    assert result["dispatch"]["actual"] == 900 and result["dispatch"]["under_t1"] == 0
    assert all(row["under_t1"] == 0 for row in result["dispatch"]["by_arm"].values())
    assert result["identical_all"]["real_astar_items"] == 45
    decision = result["what_if_decision"]
    assert decision["analysed"] == 45 and decision["shared_unanswered"] == []
    assert decision["contrasts"]["S'-S"]["whole_batch"] == 0


def test_replay_instrument_sample_prefers_items_already_dispatched(root):
    def requests(cell, sealed):
        return "different" if cell["arm"] == "S'" and cell["task_id"] in sealed["plan"]["astar"][:31] else "same"
    sealed, _ = stored_round(root, PRACTICAL_RULE, requests=requests)
    result = replay.replay(root)["acceptance"][0]["attempts"][0]
    sample = result["reuse_plan"]["card_sample"]
    assert set(sample["items"]) <= set(sealed["plan"]["astar"][:31])
    assert not sample["supplemental_items"]
    assert result["dispatch"]["under_t1"] == (31 + 31 + 30) * sealed["runs"]
    assert result["identical_all"]["real_astar_items"] == 14


def test_replay_registered_duplicate_keeps_independent_cells(root):
    sealed, _ = stored_round(root, PRACTICAL_RULE, dup=True)
    result = replay.replay(root)["acceptance"][0]["attempts"][0]
    assert result["dispatch"]["actual"] == 1080
    assert result["dispatch"]["under_t1"] == (45 + 45 + 30) * sealed["runs"]
    assert result["dispatch"]["by_arm"]["S_dup"]["under_t1"] == 180
    assert result["dispatch"]["by_arm"]["S"]["under_t1"] == 180
    assert result["identical_all"]["items"] == 0


def test_replay_never_opens_forbidden_splits_caches_or_symlinks(root, monkeypatch):
    for name in ("test", "final", "holdout", "held_out", "verifier_calibration", "reserve", "selftest", "cache"):
        path = root / name / "trajectories" / ("1" * 32 + ".json")
        path.parent.mkdir(parents=True)
        path.write_text("this must never be opened")
    (root / "linked").symlink_to(root / "test", target_is_directory=True)
    original = Path.open
    def guarded(path, *args, **kwargs):
        assert not any(name in path.parts for name in ("test", "final", "holdout", "held_out", "reserve", "selftest", "cache"))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded)
    report = replay.replay(root)
    assert report["input_artifacts_read"] == 0 and len(report["excluded_paths"]) == 9
    for name in ("test", "final", "holdout", "held_out", "verifier_calibration", "reserve", "selftest"):
        with pytest.raises(ValueError, match="forbidden split"):
            replay.Inputs(root / name)
    with pytest.raises(ValueError, match="symlink"):
        replay.Inputs(root / "linked")
    with pytest.raises(ValueError, match="Repository data"):
        replay.Inputs(replay.REPOSITORY_DATA)


def test_training_t2_counts_only_enabled_difference_and_exact_fault_free_request(root):
    parent, candidate = packages("empty")
    save(root / "G", parent)
    save(root / "G", candidate)
    attempt = root / "G" / "s2-officeqa" / "train-r1" / "attempt-1"
    unit = "G/s2-officeqa/train-r1"
    for item in ("identical", "changed", "fault", "missing", "same-enabled"):
        for arm in ("S", "S'"):
            if item == "missing" and arm == "S'":
                continue
            active = arm == "S'" and item != "same-enabled"
            put_trajectory(attempt, trajectory(unit, arm, item, candidate.sha256 if active else parent.sha256,
                enabled=[N.id] if active else [], request="different" if item == "changed" and active else "same",
                faults=[{"kind": "fault"}] if item == "fault" and active else []))
    write_json(attempt.parent / "unit.json", record("unit", "smoke", {
        "attempt": attempt.name, "result": {"differs": 6}, "status": "complete"}))
    found = replay.replay(root)["training"][0]
    assert found["t2_items_skipped"] == 1 and found["identical"] == ["identical"]
    assert found["t2_cells_not_dispatched"] == 2 and found["unobserved_items"] == 1
    assert found["unproven_items"] == ["fault", "missing"]


def test_stored_post_hooks_faults_missing_definitions_and_alfworld_refuse_identity():
    base = trajectory("u", "S", "i", "p", bench="spreadsheetbench", enabled=["procedure"])
    package = {"order": ["procedure"], "procedures": ["v1"]}
    definition = {"id": "procedure", "hooks": ["applies", "sheet_feedback"], "requests_second_call": True,
                  "record_sha256": "v1"}
    first = replay.stored_signature(base, {"p": package}, {"v1": definition})
    other = replay.stored_signature({**base, "package_sha256": "q"},
        {"q": {**package, "procedures": ["v2"]}}, {"v2": {**definition, "record_sha256": "v2"}})
    assert first["request_sha256"] == other["request_sha256"] and first["post_call"] != other["post_call"]
    assert replay.stored_signature(base, {}, {})["faults"]
    assert replay.stored_signature({**base, "bench": "alfworld"}, {}, {})["faults"]
    faulty = {**base, "shell": {"faults": [{"kind": "crash"}]}}
    assert replay.stored_signature(faulty, {"p": package}, {"v1": definition})["faults"]
    changed = {**first, "request_sha256": "different"}
    assert replay._same([first, changed], "spreadsheetbench")["faults"]


def test_extraction_counts_each_variant_and_lists_cells_without_executing(root):
    attempt = root / "G" / "s4-spreadsheetbench" / "run" / "attempt-1"
    replies = ["Prose.```python\nprint(1)\n```", "```python\nprint(2)\n```\n```\n",
               "```python\nprint(3)\n```\n```py\nprint(4)\n```", "```python\nprint(5)\n```\n```\n```\n"]
    for index, reply in enumerate(replies):
        put_trajectory(attempt, trajectory("G/s4/run", "S'", str(index), "p", bench="spreadsheetbench", reply=reply))
    found = replay.replay(root)["extraction"]
    assert found["refuse"]["by_arm"]["S'"]["replies"] == 4
    assert found["refuse"]["changed_cells"] == 2
    assert found["last"]["changed_cells"] == 3
    counts = found["refuse"]["by_arm"]["S'"]
    assert counts["v2_kind:prose_prefixed_opening_fence"] == 1
    assert counts["v2_kind:trailing_fence_only_lines"] == 1
    assert counts["changed_reason_or_kind"] == 2
    assert all("code" not in row["v2"] for row in found["last"]["needs_rescoring"])


def test_malformed_sheet_trajectory_refuses_with_artifact_path(root):
    value = trajectory("G/s4/run", "S'", "i", "p", bench="spreadsheetbench")
    fields = {k: v for k, v in value.items() if k not in ("version", "evidence", "record_sha256")}
    fields["replies"] = ["one", "two"]
    put_trajectory(root / "G" / "run" / "attempt-1", record("trajectory", "smoke", fields))
    with pytest.raises(ValueError, match="requires one call per reply: G/run/attempt-1/trajectories/"):
        replay.replay(root)


def test_cli_outputs_two_new_files_outside_read_only_root(root):
    source = root / "source"
    source.mkdir()
    report = root / "report.json"
    assert replay.main([str(source), "--output", str(report)]) == 0
    assert json.loads(report.read_text())["model_calls"] == 0
    assert "Zero model calls" in report.with_suffix(".txt").read_text()
    assert list(source.iterdir()) == []
    with pytest.raises(ValueError, match="new files"):
        replay.main([str(source), "--output", str(report)])
    with pytest.raises(ValueError, match="read-only"):
        replay.main([str(source), "--output", str(source / "report.json")])
