"""Aggregate-only progress reporting; authored records, no API/native execution."""
import json
from copy import deepcopy

import pytest

from scripts.report_fivebench_generalization import (
    aggregate,
    build_report,
    comparison,
    markdown,
    paired,
    row_index,
    watch,
)
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import BENCHMARKS, read_json, write_json

SECRET = "PRIVATE_PROMPT_OR_SKILL_CANARY"


def rows(statuses):
    return [dict(task_id=f"t{i // 2}", family_id=f"f{i // 2}", repeat=i % 2, status=status,
                 record_hash=str(i) * 64) for i, status in enumerate(statuses)]


BASE = rows(["pass", "pass", "fail", "fail", "unknown", "fail"])
CANDIDATE = rows(["fail", "pass", "pass", "pass", "pass", "fail"])


def reference(benchmark, value=BASE):
    return seal({"benchmark": benchmark, "positions": len(value), "rows": value,
                 "counts": {s: sum(r["status"] == s for r in value) for s in ("pass", "fail", "unknown")},
                 "costs": {"logical_calls": 6, "reported_tokens_known_subtotal": 600, "private": SECRET},
                 "model_service": {"name": "fixture"}})


@pytest.fixture
def study(tmp_path):
    root = tmp_path / "study"
    protocol = seal({"version": "fivebench-sequential-attempts-v1", "order": list(BENCHMARKS),
                     "methods": ["skillopt", "gepa"], "references": {b: reference(b) for b in BENCHMARKS},
                     "roles": {b: {"train": ["f0"], "selection": ["f1"]} for b in BENCHMARKS},
                     "model": {"provider": "fixture", "name": "fixture", "max_tokens": 100,
                               "reasoning_effort": "low", "api_key": SECRET}})
    write_json(root / "protocol.json", protocol)
    result = seal({"status": "pending", "candidate_skill": "", "costs": {"logical_calls": 10,
                    "reported_tokens_known_subtotal": 1000, "prompt": SECRET}, "prompt": SECRET})
    directory = root / "skillopt/s1-bigcodebench"
    write_json(directory / "learning/result.json", result)
    stage = seal({"protocol_hash": protocol["record_hash"], "method": "skillopt", "stage": 1,
                  "benchmark": "bigcodebench", "learning_result_hash": result["record_hash"],
                  "action": "pending_carry_parent", "skill": "", "learning_completed": False,
                  "cells": {b: {"result": protocol["references"][b], "reused": True,
                                 "independent_new_observation": False} for b in BENCHMARKS}, "private": SECRET})
    write_json(directory / "stage.json", stage)
    return root, protocol


def test_repeats_are_not_independent_families_and_unknown_not_a_loss():
    result = paired(CANDIDATE, row_index(BASE))
    assert result["positions"] == {"win": 2, "loss": 1, "tie": 2, "unknown": 1, "unscored": 0}
    assert result["tasks_with_win"] == result["families_with_win"] == 1
    assert result["tasks_with_loss"] == result["families_with_loss"] == 1
    assert result["family_net_direction"] == {"win": 1, "loss": 1, "tie": 0, "uncertain": 1}


def test_full_denominator_and_unscored_remain_explicit():
    result = aggregate(CANDIDATE[:2], row_index(BASE))
    assert result["scored"] == 2 and result["unscored"] == 4
    assert result["confirmed_pass_rate"] == 1 / 6
    assert result["known_coverage"] == 2 / 6 and result["counts"]["unknown"] == 0
    assert result["success_bounds"] == [1 / 6, 5 / 6]


def test_excluded_subset_and_zero_holdout_not_claimed():
    result = comparison(CANDIDATE, reference("bigcodebench"), {"train": ["f0"], "selection": ["f1"]})
    held = result["learning_family_excluded"]
    assert held["available"] and held["current"]["tasks"] == 1 and held["current"]["positions"] == 2
    assert held["no_skill"]["counts"]["unknown"] == 1
    empty = comparison(CANDIDATE, reference("alfworld"), {"train": ["f0"], "selection": ["f1", "f2"]})
    assert not empty["learning_family_excluded"]["available"]
    assert empty["learning_family_excluded"]["current"]["confirmed_pass_rate"] is None


def test_report_does_not_export_skills_prompts_private_or_count_reuse_as_new(study):
    root, _ = study
    result = build_report(root)
    assert result["completed_learning_stages"] == 0 and result["closed_all_domain_stages"] == 1
    assert result["evaluation_cost_records_deduplicated"] == []
    stage = result["stages"][0]
    assert stage["learning_costs"] == {"logical_calls": 10, "reported_tokens_known_subtotal": 1000}
    assert stage["empty_skill"] and stage["action"] == "pending_carry_parent"
    for cell in stage["cells"].values():
        assert cell["reused"] and not cell["independent_new_observation"]
        assert cell["new_costs"] == {"logical_calls": 0}
        assert cell["confirmed_pass_delta"] == 0
    text = markdown(result)
    assert SECRET not in json.dumps(result) + text
    assert "复用" in text and "0/5" in text
    assert "未评测（0/6已评分）" in text
    assert not result["causal_generalization_claimed"] and not result["deployment_authorized"]


def test_partial_stage_does_not_claim_liveness_and_counts_saved_scores(study):
    root, _ = study
    directory = root / "skillopt/s2-spreadsheetbench"
    write_json(directory / "evaluations/bigcodebench/host_only/scores/one.json",
               seal({k: v for k, v in CANDIDATE[0].items() if k != "record_hash"}))
    report = build_report(root)
    stage = report["stages"][1]
    assert stage["state"] == "started_or_interrupted"
    cell = stage["cells"]["bigcodebench"]
    assert not cell["terminal"] and cell["current"]["unscored"] == 5
    assert cell["confirmed_pass_delta"] is None and cell["new_costs"] is None
    assert cell["paired"]["positions"]["loss"] == 1


def test_learning_completed_but_evaluations_pending_are_separate(study):
    root, protocol = study
    directory = root / "skillopt/s2-spreadsheetbench"
    result = seal({"status": "completed", "candidate_skill": SECRET, "costs": {"logical_calls": 4}})
    write_json(directory / "learning/result.json", result)
    write_json(directory / "decision.json", seal({"protocol_hash": protocol["record_hash"], "method": "skillopt",
               "stage": 2, "benchmark": "spreadsheetbench", "learning_result_hash": result["record_hash"],
               "action": "selected_update", "skill": SECRET}))
    write_json(directory / "evaluation-bigcodebench.json", reference("bigcodebench", CANDIDATE))
    report = build_report(root)
    assert report["completed_learning_stages"] == 1 and report["closed_all_domain_stages"] == 1
    assert len(report["evaluation_cost_records_deduplicated"]) == 1
    stage = report["stages"][1]
    assert stage["state"] == "evaluation_incomplete" and not stage["empty_skill"]
    assert stage["cells"]["bigcodebench"]["terminal"]
    assert SECRET not in json.dumps(report)


@pytest.mark.parametrize("mutation", ["duplicate", "boolean_repeat", "wrong_family", "wrong_task"])
def test_bad_score_identities_rejected(mutation):
    value = deepcopy(CANDIDATE)
    if mutation == "duplicate":
        value.append(value[0])
    elif mutation == "boolean_repeat":
        value[0]["repeat"] = False
    elif mutation == "wrong_family":
        value[0]["family_id"] = "other"
    else:
        value[0]["task_id"] = "other"
    with pytest.raises(ValueError):
        paired(value, row_index(BASE))


def test_wrong_reference_count_rejected():
    value = reference("bigcodebench")
    value["counts"]["pass"] = 3
    with pytest.raises(ValueError, match="count mismatch"):
        comparison(CANDIDATE, value, {"train": [], "selection": []})


def test_report_does_not_write_to_study(study):
    root, _ = study
    before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    build_report(root)
    after = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert before == after


class Clock:
    def __init__(self, on_sleep=None):
        self.now, self.sleeps, self.on_sleep = 0.0, [], on_sleep

    def time(self):
        return self.now

    def sleep(self, seconds):
        assert 0 < seconds <= 60
        self.sleeps.append(seconds)
        self.now += seconds
        if self.on_sleep:
            self.on_sleep(len(self.sleeps))


def install_final(root, protocol):
    template = read_json(root / "skillopt/s1-bigcodebench/stage.json", sealed=True)
    result = read_json(root / "skillopt/s1-bigcodebench/learning/result.json", sealed=True)
    hashes = [template["record_hash"]]
    for i, benchmark in enumerate(BENCHMARKS[1:], 2):
        stage = seal({**{k: v for k, v in template.items() if k != "record_hash"},
                      "stage": i, "benchmark": benchmark})
        write_json(root / f"skillopt/s{i}-{benchmark}/learning/result.json", result)
        write_json(root / f"skillopt/s{i}-{benchmark}/stage.json", stage)
        hashes.append(stage["record_hash"])
    write_json(root / "skillopt/final.json", seal({"protocol_hash": protocol["record_hash"],
               "method": "skillopt", "attempted_stages": 5, "completed_learning_stages": 0,
               "stage_hashes": hashes, "status": "attempts_finished_with_pending"}))


def test_watch_deadline_has_initial_and_final_snapshot_without_touching_study(study, tmp_path):
    root, _ = study
    before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    clock = Clock()
    result = watch(root, "skillopt", tmp_path / "exports", interval=60, hours=0.05,
                   _clock=clock.time, _sleep=clock.sleep)
    assert result["status"] == "watch_deadline_reached" and result["snapshots"] == 2
    assert clock.sleeps == [60, 60, 60]
    assert (tmp_path / "exports/snapshot-0000/report.md").is_file()
    assert (tmp_path / "exports/snapshot-0001/report.json").is_file()
    latest = read_json(tmp_path / "exports/latest.json", sealed=True)
    assert latest["snapshot"] == "snapshot-0001" and latest["snapshots"] == 2
    assert latest["report_hash"] == result["latest_report_hash"]
    assert not result["study_modified"] and result["model_calls"] == 0
    assert before == {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_watch_final_appearance_exports_last_comparison_and_stops(study, tmp_path):
    root, protocol = study
    clock = Clock(lambda call: install_final(root, protocol) if call == 1 else None)
    result = watch(root, "skillopt", tmp_path / "exports", interval=60, hours=12,
                   _clock=clock.time, _sleep=clock.sleep)
    assert clock.sleeps == [60] and result["snapshots"] == 2
    assert result["status"] == "final_observed"
    last = read_json(tmp_path / "exports/snapshot-0001/report.json", sealed=True)
    assert last["closed_all_domain_stages"] == 5 and last["completed_learning_stages"] == 0
    assert SECRET not in json.dumps(result) + json.dumps(last)


def test_watch_existing_final_exits_without_sleep(study, tmp_path):
    root, protocol = study
    install_final(root, protocol)
    clock = Clock()
    result = watch(root, "skillopt", tmp_path / "exports", _clock=clock.time, _sleep=clock.sleep)
    assert result["status"] == "final_observed" and result["snapshots"] == 1 and not clock.sleeps


def test_watch_heartbeat_for_nonterminal_long_generation(study, tmp_path):
    root, _ = study
    clock = Clock()
    result = watch(root, "skillopt", tmp_path / "exports", interval=60, hours=960 / 3600,
                   _clock=clock.time, _sleep=clock.sleep)
    assert result["snapshots"] == 3  # Initial, 15 minute progress, deadline.
    assert sum(clock.sleeps) == 960


def test_watch_terminal_learning_change_exports_before_deadline(study, tmp_path):
    root, _ = study
    def change(call):
        if call == 1:
            write_json(root / "skillopt/s2-spreadsheetbench/learning/result.json",
                       seal({"status": "pending", "candidate_skill": "", "costs": {"logical_calls": 1}}))
    clock = Clock(change)
    result = watch(root, "skillopt", tmp_path / "exports", interval=60, hours=120 / 3600,
                   _clock=clock.time, _sleep=clock.sleep)
    assert result["snapshots"] == 3
    middle = read_json(tmp_path / "exports/snapshot-0001/report.json", sealed=True)
    assert middle["stages"][1]["state"] == "learning_terminal"


@pytest.mark.parametrize("interval,hours", [(0, 1), (61, 1), (True, 1), (60, 0), (60, 25),
                                           (60, True), (60, float("nan")), (60, float("inf"))])
def test_watch_invalid_bounds_never_wait_or_write(study, tmp_path, interval, hours):
    root, _ = study
    with pytest.raises(ValueError):
        watch(root, "skillopt", tmp_path / "exports", interval=interval, hours=hours,
              _sleep=lambda _: pytest.fail("Invalid watch must not sleep"))
    assert not (tmp_path / "exports").exists()


def test_watch_refuses_input_output_overlap_and_existing_destination(study, tmp_path):
    root, _ = study
    with pytest.raises(ValueError, match="outside"):
        watch(root, "skillopt", root / "forbidden")
    target = tmp_path / "existing"
    target.mkdir()
    (target / "marker").write_text("preserve")
    with pytest.raises(ValueError, match="new report"):
        watch(root, "skillopt", target)
    assert (target / "marker").read_text() == "preserve"
