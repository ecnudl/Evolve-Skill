"""Scope-routed deployment diagnostic: zero-call engineering controls, not method effects."""
import os
import sys

import pytest

from scripts import report_scope_routed_deployment as routing
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import BENCHMARKS, read_json, write_json

PUBLIC = {
    "bigcodebench": {"prompt": "Return one.", "entry_point": "f"},
    "searchqa": {"question": "What is the capital?", "context": ["The capital is Paris."]},
    "korbench": {"rule": "Reply ONE.", "question": "What is the reply?"},
    "spreadsheetbench": {"instruction": "Set A1 to one.", "input_files": ["public.xlsx"], "answer_position": "Sheet1!A1"},
    "alfworld": {"game_file": "public-game.tw-pddl"},
}
NO_SKILL = ["pass", "fail", "fail", "pass", "pass", "pass"]
BETTER = ["pass", "pass", "pass", "pass", "pass", "pass"]   # +2 against No-Skill (families f0, f1)
WORSE = ["fail", "fail", "fail", "pass", "pass", "fail"]    # -2 against No-Skill (families f0, f2)


def rows(statuses):
    return [{"task_id": f"t{i // 2}", "family_id": f"f{i // 2}", "repeat": i % 2, "status": s,
             "record_hash": f"{i:064d}"} for i, s in enumerate(statuses)]


SERVICE = {"name": "fixture-service"}


def write_study(root, stages, *, method="skillopt", public=None, cell=None):
    """``stages``: (action, skill, {benchmark: statuses}) for s1..sk; ``cell`` may edit one result."""
    references, roles = {}, {}
    for benchmark in BENCHMARKS:
        value = rows(NO_SKILL)
        references[benchmark] = {"benchmark": benchmark, "positions": len(value), "rows": value,
                                 "counts": {s: NO_SKILL.count(s) for s in ("pass", "fail", "unknown")},
                                 "model_service": SERVICE}
        panel = root / f"panels/{benchmark}.json"
        write_json(panel, {"benchmark": benchmark, "tasks": [
            {"task_id": "t0", "family_id": "f0", "public": (public or PUBLIC)[benchmark]}]})
        roles[benchmark] = {"path": str(panel), "train": ["f0"], "selection": ["f1"]}
    protocol = seal({"version": "fivebench-sequential-attempts-v4", "order": list(BENCHMARKS),
                     "methods": ["skillopt", "gepa"], "references": references, "roles": roles})
    write_json(root / "protocol.json", protocol)
    previous, parent = "", None
    for number, (action, skill, statuses) in enumerate(stages, 1):
        benchmark = BENCHMARKS[number - 1]
        cells = {t: {"result": {"benchmark": t, "model_service": SERVICE, "rows": rows(statuses.get(t, NO_SKILL))}}
                 for t in BENCHMARKS}
        if cell:
            cell(number, cells)
        record = seal({"protocol_hash": protocol["record_hash"], "method": method, "stage": number,
                       "benchmark": benchmark, "parent_skill": previous, "parent_stage_hash": parent,
                       "action": action, "skill": skill, "cells": cells})
        write_json(root / f"{method}/s{number}-{benchmark}/stage.json", record)
        previous, parent = skill, record["record_hash"]
    return root


FORCED = {"bigcodebench": BETTER, "korbench": WORSE, "searchqa": BETTER}


def test_out_of_scope_harm_is_avoided_and_in_scope_gain_kept(tmp_path):
    report = routing.build(write_study(tmp_path / "study", [("selected_update", "coding checklist", FORCED)]))
    stage = report["stages"][0]
    assert stage["authorized_deliverable_types"] == ["python_function"]
    cells = stage["cells"]
    assert cells["bigcodebench"]["in_scope"] and cells["bigcodebench"]["routed_source"] == "forced_skill_observation"
    assert cells["bigcodebench"]["routed"]["paired"]["positions"]["win"] == 2
    assert not cells["korbench"]["in_scope"] and cells["korbench"]["routed_source"] == "reused_no_skill_reference"
    assert cells["korbench"]["routed"]["paired"]["positions"] == {"win": 0, "loss": 0, "tie": 6, "unknown": 0,
                                                                  "unscored": 0}
    assert stage["summary"] == {"forced_net_positions": 2, "routed_net_positions": 2,
                                "forced_losses_avoided": 2, "forced_wins_forgone": 2}
    # Family f2 is the only one outside the planned train/selection families.
    held = cells["korbench"]["learning_family_excluded"]
    assert held["forced"]["positions"]["loss"] == 1 and held["routed"]["positions"]["tie"] == 2
    assert report["model_api_calls"] == 0 and report["new_observations"] == 0
    assert report["post_hoc_diagnostic"] and not report["deployment_authorized"]


def test_routing_never_depends_on_outcomes(tmp_path):
    flipped = {t: [("fail" if s == "pass" else "pass") for s in NO_SKILL] for t in BENCHMARKS}
    first = routing.build(write_study(tmp_path / "a", [("selected_update", "coding checklist", FORCED)]))
    second = routing.build(write_study(tmp_path / "b", [("selected_update", "coding checklist", flipped)]))
    scope = [{t: c["in_scope"] for t, c in r["stages"][0]["cells"].items()} for r in (first, second)]
    assert scope[0] == scope[1] == {t: t == "bigcodebench" for t in BENCHMARKS}


def test_private_or_unexpected_public_fields_are_refused(tmp_path):
    leaked = {**PUBLIC, "korbench": {**PUBLIC["korbench"], "answer": "HIDDEN"}}
    with pytest.raises(ValueError, match="public contract schema"):
        routing.build(write_study(tmp_path / "study", [("selected_update", "x", {})], public=leaked))


def test_scope_widens_only_with_an_accepted_update_and_pending_keeps_the_parent(tmp_path):
    study = write_study(tmp_path / "study", [
        ("selected_update", "coding checklist", FORCED),
        ("completed_no_update", "coding checklist", FORCED),
        ("selected_update", "coding checklist plus evidence", {}),
        ("pending_carry_parent", "coding checklist plus evidence", {})])
    scopes = [s["authorized_deliverable_types"] for s in routing.build(study)["stages"]]
    assert scopes == [["python_function"], ["python_function"], ["python_function", "short_answer"],
                      ["python_function", "short_answer"]]


@pytest.mark.parametrize("stages,message", [
    ([("selected_update", "a", {}), ("pending_carry_parent", "b", {})], "Only an accepted update"),
    ([("selected_update", "", {})], "Only an accepted update"),
    ([("completed_no_update", "", {"bigcodebench": BETTER})], "recurring Skill changed"),
    ([("selected_update", "a", FORCED), ("completed_no_update", "a", {})], "recurring Skill changed"),
    ([("selected_update", "a", FORCED), ("selected_update", "b", {}), ("selected_update", "a", {})],
     "recurring Skill changed"),
    ([("rolled_back", "a", {})], "Only an accepted update"),
])
def test_inconsistent_stage_records_are_refused(tmp_path, stages, message):
    with pytest.raises(ValueError, match=message):
        routing.build(write_study(tmp_path / "study", stages))


def _rehash(number, cells):
    if number == 1:
        cells["korbench"]["result"]["rows"][0]["record_hash"] = "f" * 64


def _foreign_service(number, cells):
    cells["searchqa"]["result"]["model_service"] = {"name": "other-service"}


@pytest.mark.parametrize("edit,message", [(_rehash, "recurring Skill changed"),
                                          (_foreign_service, "another domain or model service")])
def test_reuse_requires_the_same_evidence_and_service(tmp_path, edit, message):
    # Same statuses but a different evidence hash cannot pass as the No-Skill observation.
    with pytest.raises(ValueError, match=message):
        routing.build(write_study(tmp_path / "study", [("completed_no_update", "", {})], cell=edit))


def test_method_identity_and_complete_cells_are_required(tmp_path):
    copied = write_study(tmp_path / "a", [("selected_update", "x", {})], method="skillopt")
    target = copied / "gepa/s1-bigcodebench/stage.json"
    target.parent.mkdir(parents=True)
    target.write_bytes((copied / "skillopt/s1-bigcodebench/stage.json").read_bytes())
    with pytest.raises(ValueError, match="Stage chain binding mismatch"):
        routing.build(copied, "gepa")
    gepa = routing.build(write_study(tmp_path / "b", [("selected_update", "x", {})], method="gepa"), "gepa")
    assert gepa["method"] == "gepa" and gepa["stages"][0]["authorized_deliverable_types"] == ["python_function"]
    short = write_study(tmp_path / "c", [("selected_update", "x", {"searchqa": NO_SKILL[:4]})])
    with pytest.raises(ValueError, match="Incomplete or foreign"):
        routing.build(short)


def test_export_must_be_new_and_outside_the_study_including_aliases(tmp_path, monkeypatch):
    study = write_study(tmp_path / "study", [("selected_update", "coding checklist", {})])
    alias = tmp_path / "alias"
    os.symlink(study, alias)
    for inside in (study / "inside", alias / "inside"):
        monkeypatch.setattr(sys, "argv", ["x", "--study", str(study), "--output", str(inside)])
        with pytest.raises(ValueError, match="outside the frozen study|Symlink paths are not supported"):
            routing.main()
    out = tmp_path / "export"
    monkeypatch.setattr(sys, "argv", ["x", "--study", str(study), "--output", str(out)])
    routing.main()
    assert read_json(out / "report.json", sealed=True)["stages"][0]["stage"] == 1
    assert "按适用范围部署诊断" in (out / "report.md").read_text()
