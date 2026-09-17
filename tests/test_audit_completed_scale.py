"""Synthetic-only audit tests; completion barrier is tested without real artifacts."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from skillopt.validator_scale_analysis import ARMS, analyze

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_completed_scale.py"
SPEC = importlib.util.spec_from_file_location("completed_scale_audit", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def target(repeat, hard, code="def f(): return 1", **updates):
    return {"id": "T", "family": "F", "split": "holdout", "arm": "noskill", "repeat": repeat,
            "hard": hard, "code": code, "response": code, "target_ok": True, "execution_ok": True, **updates}


def judge(repeat, hard, decision, **updates):
    parsed = {"decision": decision, "schema_valid": decision != "malformed"}
    return {"id": "T", "family": "F", "origin": "natural", "skill_version": "noskill",
            "target_repeat": 0, "repeat": repeat, "hard": hard, "target_ok": True,
            "execution_ok": True, "judge_ok": True, "guard_forced": False,
            "judgment": parsed, "guarded_judgment": parsed, **updates}


def test_missing_completion_reads_only_result_filename(monkeypatch):
    reads = []

    def fake_read(path):
        reads.append(path.name)
        raise FileNotFoundError("synthetic missing completion")

    monkeypatch.setattr(Path, "read_bytes", fake_read)
    with pytest.raises(FileNotFoundError):
        MODULE.audit_completed(Path("/synthetic-run"))
    assert reads == ["results.json"]


def test_noncomplete_status_reads_no_protocol_or_target(monkeypatch):
    reads = []

    def fake_read(path):
        reads.append(path.name)
        return b'{"status":"running"}'

    monkeypatch.setattr(Path, "read_bytes", fake_read)
    with pytest.raises(ValueError, match="Completion barrier"):
        MODULE.audit_completed(Path("/synthetic-run"))
    assert reads == ["results.json"]


def test_protocol_mismatch_stops_before_target_read(monkeypatch):
    reads = []

    def fake_read(path):
        reads.append(path.name)
        return json.dumps({"status": "complete", "protocol_hash": "wrong"}
                          if path.name == "results.json" else {}).encode()

    monkeypatch.setattr(Path, "read_bytes", fake_read)
    with pytest.raises(ValueError, match="protocol disagree"):
        MODULE.audit_completed(Path("/synthetic-run"))
    assert reads == ["results.json", "protocol.json"]


def test_identical_code_hard_flip_is_flagged_without_claiming_code_change():
    rows = [target(0, True), target(1, False), target(2, True, code="def f(): return 2"),
            target(3, False, code=None)]
    result = MODULE.solver_details(rows)["holdout"]["noskill"]
    assert result["hard_failures"]["response_draws"] == 2
    assert result["hard_failures"]["distinct_tasks"] == 1
    assert result["hard_failures"]["distinct_families"] == 1
    assert result["tasks_with_hard_flips"] == 1
    pairs = result["task_repeat_pairs"]
    assert pairs["observed_repeat_pairs"] == 6
    assert pairs["hard_flip_pairs"] == 4
    assert pairs["code_comparable_pairs"] == 3
    assert pairs["identical_code_pairs"] == 1
    assert pairs["different_code_pairs"] == 2
    assert pairs["identical_code_hard_flip_pairs"] == 1
    assert pairs["different_code_hard_flip_pairs"] == 1
    assert pairs["unavailable_code_hard_flip_pairs"] == 2
    assert result["tasks"][0]["identical_code_conflicting_hard_repeats"] == [[0, 1]]


def test_four_same_codes_and_successes_are_ceiling_not_independent_evidence():
    rows = [target(repeat, True) for repeat in range(4)]
    result = MODULE.solver_details(rows)["holdout"]["noskill"]
    assert result["all_expected_observed_and_pass"]
    assert result["tasks_with_four_successes"] == 1
    assert result["task_repeat_pairs"]["identical_code_pairs"] == 6
    assert result["not_independent_repeat_pairs"]
    assert result["tasks"][0]["all_available_code_identical"]


def test_missing_or_failed_calls_do_not_establish_a_complete_ceiling():
    rows = [target(repeat, True) for repeat in range(3)]
    result = MODULE.solver_details(rows)["holdout"]["noskill"]
    assert result["zero_observed_failures"]
    assert not result["all_expected_observed_and_pass"]
    rows.append(target(3, None, target_ok=False))
    result = MODULE.solver_details(rows)["holdout"]["noskill"]
    assert result["unavailable"]["response_draws"] == 1
    assert result["observed"] == 3
    assert not result["all_expected_observed_and_pass"]


def test_judge_false_pass_draws_are_distinct_from_artifacts_tasks_and_families():
    rows = [judge(0, False, "pass"), judge(1, False, "pass"),
            judge(0, False, "pass", skill_version="mechanism_skill"),
            judge(1, False, "fail", skill_version="mechanism_skill")]
    result = MODULE.judge_details({"static_v0": rows})["static_v0"]["raw"]["natural"]
    assert result["judge_draws"] == 4
    assert result["distinct_artifacts"] == 2
    assert result["distinct_tasks"] == 1
    assert result["distinct_families"] == 1
    errors = result["error_counts"]["false_pass"]
    assert errors["response_draws"] == 3
    assert errors["distinct_artifacts"] == 2
    assert errors["distinct_tasks"] == 1
    assert result["artifacts_with_strict_pass_fail_flips"] == 1


def test_guard_effect_does_not_hide_raw_api_unknown():
    row = judge(0, False, "pass", judge_ok=False, guard_forced=True,
                guarded_judgment={"decision": "fail", "schema_valid": True})
    result = MODULE.judge_details({"v0": [row]})["v0"]
    assert result["raw"]["natural"]["error_counts"]["unknown"]["response_draws"] == 1
    assert result["raw"]["natural"]["error_counts"]["false_pass"]["response_draws"] == 0
    assert result["guarded"]["natural"]["error_counts"]["unknown"]["response_draws"] == 0


def test_natural_and_controlled_false_rejections_are_not_pooled():
    rows = [judge(0, True, "fail"), judge(0, True, "fail", origin="controlled", skill_version="reference")]
    result = MODULE.judge_details({"v0": rows})["v0"]["raw"]
    assert result["natural"]["error_counts"]["false_reject"]["response_draws"] == 1
    assert result["controlled"]["error_counts"]["false_reject"]["response_draws"] == 1
    json.dumps(result, allow_nan=False)


def test_schema_unknown_and_execution_unavailable_are_not_false_rejections():
    rows = [judge(0, True, "malformed"), judge(1, True, "fail", execution_ok=False)]
    result = MODULE.judge_details({"v0": rows})["v0"]["raw"]["natural"]
    assert result["error_counts"]["unknown"]["response_draws"] == 1
    assert result["error_counts"]["unavailable"]["response_draws"] == 1
    assert result["error_counts"]["false_reject"]["response_draws"] == 0


def test_full_completion_read_is_provenanced_and_ceilings_are_flagged(monkeypatch):
    rows = [target(repeat, True, arm=arm, cluster_id="F", format_ok=True, public_ok=True,
                   request_hash=f"{arm}-{repeat}") for arm in ARMS for repeat in range(4)]
    analysis = analyze(rows, bootstrap_draws=5, subsample_draws=5, subsample_sizes=(1,))
    protocol = {"version": "synthetic"}
    results = {"status": "complete", "protocol_hash": MODULE._digest(protocol), "skill_analysis": analysis}
    payloads = {name: json.dumps(value).encode() for name, value in {
        "results.json": results, "protocol.json": protocol, "dev_targets_frozen_private.json": [],
        "holdout_targets_frozen_private.json": rows, "holdout_judgments.json": {},
        "dev_judgments.json": {}}.items()}
    payloads[SCRIPT.name] = b"synthetic audit source"
    read_order = []

    def fake_read(path):
        read_order.append(path.name)
        return payloads[path.name]

    monkeypatch.setattr(Path, "read_bytes", fake_read)
    result = MODULE.audit_completed(Path("/synthetic-run"))
    assert read_order[:2] == ["results.json", "protocol.json"]
    assert result["completion_barrier_checked"]
    assert len(result["input_file_sha256"]) == 6
    assert result["audit_code_sha256"]
    for contrast in result["tables"]["holdout"].values():
        assert contrast["both_arms_observed_ceiling"]
        assert not contrast["equivalence_established"]
        assert "Ceiling-limited" in contrast["diagnostic_warning"]
    json.dumps(result, allow_nan=False)


def repeated_rows(count=8, outcome=None):
    if outcome is None:
        def outcome(arm, repeat, identity):
            return repeat % 2 == (0 if arm == "mechanism_skill" else 1)
    return [target(repeat, outcome(arm, repeat, identity), arm=arm, id=f"T{identity:02d}",
                   family=f"F{identity // 2}")
            for identity in range(count) for arm in ARMS for repeat in range(4)]


def shot(result, size, reference="noskill", split="holdout"):
    return result["scopes"][split]["contrasts"][f"mechanism_skill_vs_{reference}"]["sizes"][str(size)]


def test_single_shot_full_batch_preserves_one_shared_global_wave():
    result = MODULE.single_shot_batch_sensitivity(repeated_rows(), draws=400, seed=42, sizes=(8,))
    data = shot(result, 8)
    # Every selected wave is uniformly +1 or -1. Per-task repeat sampling would
    # create spurious intermediate values and cancel the observed wave effect.
    counts = data["global_repeat_draw_counts"]
    assert sum(counts.values()) == 400
    assert data["macro_family_delta"]["positive_fraction"] == (counts["0"] + counts["2"]) / 400
    assert data["macro_family_delta"]["negative_fraction"] == (counts["1"] + counts["3"]) / 400
    assert data["macro_family_delta"]["zero_fraction"] == 0
    assert data["matched_tasks_per_draw_min_max"] == [8, 8]
    assert data["observed_families_per_draw_min_max"] == [4, 4]
    assert data["missing_pairs_total"] == 0
    assert data["draws_without_observable_pairs"] == 0
    assert data["selected_pairs_total"] == 3200
    assert data["one_global_repeat_shared_by_all_selected_tasks"]
    assert data["without_replacement_within_draw"]
    assert result["not_new_evidence"]
    assert result["separate_from_frozen_four_repeat_average_subsampling"]
    assert result["does_not_reweight_frozen_main_analysis"]


def test_single_shot_missing_pairs_omitted_not_zeroed_or_removed_from_sampling_pool():
    rows = repeated_rows(4, lambda arm, repeat, identity: arm == "mechanism_skill")
    for row in rows:
        if row["id"] == "T00" and row["arm"] == "noskill":
            row["execution_ok"] = False
    result = MODULE.single_shot_batch_sensitivity(rows, draws=30, sizes=(1, 4))
    assert result["scopes"]["holdout"]["task_pool_size"] == 4
    full = shot(result, 4)
    assert full["macro_family_delta"]["positive_fraction"] == 1
    assert set(full["macro_family_delta"]["percentiles"].values()) == {1.}
    assert full["matched_pairs_total"] == 90
    assert full["missing_pairs_total"] == 30
    assert full["draws_with_missing_pairs"] == 30
    assert full["matched_tasks_per_draw_min_max"] == [3, 3]
    assert full["selected_missing_pair_count_by_task"] == {"T00": 30}
    tiny = shot(result, 1)
    assert tiny["draws_without_observable_pairs"] > 0
    assert tiny["macro_family_delta"]["positive_fraction"] == 1
    assert tiny["macro_family_delta"]["n_evaluable_draws"] == 30 - tiny["draws_without_observable_pairs"]


def test_single_shot_fully_unavailable_draws_have_no_zero_delta_or_sign_estimate():
    rows = repeated_rows(1)
    for row in rows:
        if row["arm"] == "generic_control":
            row["target_ok"] = False
    result = MODULE.single_shot_batch_sensitivity(rows, draws=10, sizes=(1,))
    data = shot(result, 1, reference="generic_control")
    assert data["draws_without_observable_pairs"] == 10
    assert data["missing_pairs_total"] == 10
    assert data["macro_family_delta"]["n_evaluable_draws"] == 0
    assert data["macro_family_delta"]["zero_fraction"] is None
    assert data["macro_family_delta"]["positive_fraction"] is None
    assert set(data["macro_family_delta"]["percentiles"].values()) == {None}
    assert shot(result, 1)["draws_without_observable_pairs"] == 0
    json.dumps(result, allow_nan=False)


def test_single_shot_family_macro_and_task_micro_are_distinct():
    rows = repeated_rows(4, lambda arm, repeat, identity: (identity == 0) if arm == "mechanism_skill" else identity != 0)
    for row in rows:
        row["family"] = "one" if row["id"] == "T00" else "three"
    data = shot(MODULE.single_shot_batch_sensitivity(rows, draws=20, sizes=(4,)), 4)
    assert set(data["macro_family_delta"]["percentiles"].values()) == {0.}
    assert set(data["micro_task_delta"]["percentiles"].values()) == {-.5}
    assert data["macro_family_delta"]["zero_fraction"] == 1


def test_single_shot_reproducible_with_shared_choices_and_input_order_invariance():
    rows = repeated_rows()
    first = MODULE.single_shot_batch_sensitivity(rows, draws=100, seed=3, sizes=(5,))
    second = MODULE.single_shot_batch_sensitivity(list(reversed(rows)), draws=100, seed=3, sizes=(5,))
    assert first == second
    left, right = shot(first, 5), shot(first, 5, reference="generic_control")
    assert left["sampled_repeat_task_choices_sha256"] == right["sampled_repeat_task_choices_sha256"]
    assert left["global_repeat_draw_counts"] == right["global_repeat_draw_counts"]


def test_single_shot_default_batch_sizes_skip_sizes_larger_than_split():
    rows = repeated_rows(32)
    for row in rows:
        row["split"] = "dev" if row["id"] < "T16" else "holdout"
    result = MODULE.single_shot_batch_sensitivity(rows)
    assert result["draws_per_size"] == 2000
    assert result["base_seed"] == 20260910
    assert result["sizes"] == [5, 10, 20, 32]
    assert result["scopes"]["holdout"]["task_pool_size"] == 16
    assert shot(result, 20)["status"] == "insufficient_tasks"
    assert shot(result, 32)["draws_executed"] == 0
    assert shot(result, 32, split="all")["draws_executed"] == 2000
    assert shot(result, 32, split="all")["matched_tasks_per_draw_min_max"] == [32, 32]


@pytest.mark.parametrize("options", [{"draws": 0}, {"draws": True}, {"seed": -1},
                                     {"sizes": (0,)}, {"sizes": (5, 5)}])
def test_single_shot_invalid_parameters_rejected(options):
    with pytest.raises(ValueError):
        MODULE.single_shot_batch_sensitivity([], **options)


def test_single_shot_duplicate_rows_rejected():
    row = target(0, True)
    with pytest.raises(ValueError, match="Duplicate"):
        MODULE.single_shot_batch_sensitivity([row, row], draws=5, sizes=(1,))


def test_external_archive_is_immutable_and_identical_rerun_allowed(tmp_path):
    original = tmp_path / "run"
    original.mkdir()
    output = tmp_path / "posthoc" / "audit.json"
    report = {"diagnostic": True, "value": 1}
    first = MODULE.archive_audit(report, output, original)
    assert json.loads(output.read_text()) == report
    assert first["immutable"]
    second = MODULE.archive_audit(report, output, original)
    assert first == second
    with pytest.raises(ValueError, match="Immutable"):
        MODULE.archive_audit({"value": 2}, output, original)
    assert json.loads(output.read_text()) == report
    assert list(original.iterdir()) == []
    assert not list(output.parent.glob(".scale-audit-*"))


@pytest.mark.parametrize("nested", ["audit.json", "subdir/audit.json", "."])
def test_archive_rejects_original_run_or_its_descendants_before_writing(tmp_path, nested):
    original = tmp_path / "run"
    original.mkdir()
    with pytest.raises(ValueError, match="outside"):
        MODULE.archive_audit({}, original / nested, original)
    assert list(original.iterdir()) == []


def test_archive_rejects_outside_symlink_pointing_inside_run(tmp_path):
    original = tmp_path / "run"
    original.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(original, target_is_directory=True)
    with pytest.raises(ValueError, match="outside"):
        MODULE.archive_audit({}, alias / "audit.json", original)
    assert list(original.iterdir()) == []


def test_archive_rejects_inside_run_symlink_pointing_outside_run(tmp_path):
    original, external = tmp_path / "run", tmp_path / "external"
    original.mkdir()
    external.mkdir()
    alias = original / "alias"
    alias.symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="outside"):
        MODULE.archive_audit({}, alias / "audit.json", original)
    assert list(external.iterdir()) == []


def test_cli_optional_archive_and_default_stdout(monkeypatch, tmp_path, capsys):
    report = {"synthetic": True}
    original = tmp_path / "run"
    original.mkdir()
    monkeypatch.setattr(MODULE, "audit_completed", lambda root: report)
    monkeypatch.setattr("sys.argv", ["audit_completed_scale.py", "--run", str(original)])
    assert MODULE.main() == 0
    assert json.loads(capsys.readouterr().out) == report
    output = tmp_path / "supplement.json"
    monkeypatch.setattr("sys.argv", ["audit_completed_scale.py", "--run", str(original), "--output", str(output)])
    assert MODULE.main() == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["ok"] and stdout["no_api_calls"]
    assert stdout["archive"]["path"] == str(output)
    assert json.loads(output.read_text()) == report
