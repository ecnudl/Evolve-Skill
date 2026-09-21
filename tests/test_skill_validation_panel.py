"""Panel-planning tests; all code/labels are synthetic, with no actual runs."""
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.skill_validation.panel import PilotRequirements, inspect_pool, main
from skillopt.skill_validation.stage2 import export_pool
from skillopt.skill_validation.stage2_fixtures import fixture_pool


def simulated_complete_pool():
    # Only exercises eligibility-flag handling; NOT real model-run evidence.
    pool = fixture_pool()
    for row in pool:
        old = row["artifacts"]
        row["artifacts"] = tuple(replace(a, provenance_kind="model") for a in old)
        row["audit"] = {new.content_hash: row["audit"][previous.content_hash]
                        for previous, new in zip(old, row["artifacts"])}
    return pool


def test_fixtures_cannot_become_natural_panel_or_authority():
    report = inspect_pool(fixture_pool())
    assert report["readiness"]["status"] == "pending"
    assert report["readiness"]["skill_or_verifier_admission_authority"] is False
    assert report["development"]["natural_complete_triplets"]["artifact_positions"] == 0
    diagnostic = report["development"]["diagnostic_only_triplets"]
    assert diagnostic["artifact_positions"] == 9
    assert diagnostic["original_tasks"] == 2
    assert diagnostic["declared_families"] == 1
    assert diagnostic["same_delivered_content_triplets"] == 1
    assert report["requirements_are_power_guarantee"] is False


def test_repeats_are_not_independent_and_unknown_is_not_removed():
    report = inspect_pool(simulated_complete_pool())
    dev = report["development"]["natural_complete_triplets"]
    assert dev["task_repeat_triplets"] == 3 and dev["original_tasks"] == 2
    assert dev["declared_families"] == 1
    assert dev["conditions"]["no_skill"]["audit_outcomes"] == {"pass": 1, "fail": 1, "unknown": 1}
    assert dev["conditions"]["no_skill"]["all_attempt_success"] == {
        "numerator": 1, "denominator": 3, "value": 1 / 3}
    assert dev["paired_task_repeat_outcomes"]["candidate_vs_no_skill"] == {
        "win": 1, "loss": 1, "tie": 0, "unknown": 1}
    assert dev["audited_error_families"] == dev["discordant_families"] == 1
    assert report["readiness"]["status"] == "pending"


def test_heldout_outcomes_do_not_change_development_readiness():
    pool = fixture_pool()
    before = inspect_pool(pool)
    for row in pool:
        if row["task"].contract.partition != "development":
            row["near_miss"] = not row["near_miss"]
            for labels in row["audit"].values():
                for key in labels:
                    labels[key] = "fail" if labels[key] == "pass" else "pass"
    assert inspect_pool(pool) == before


def test_order_does_not_change_replay_and_no_prompt_or_hidden_checks_exported():
    pool = fixture_pool()
    report = inspect_pool(pool)
    assert inspect_pool(list(reversed(pool))) == report
    import json
    text = json.dumps(report)
    for forbidden in ("expected_json", "arguments_json", "def solve", "host_only/audit", "Public example"):
        assert forbidden not in text


def test_missing_artifact_remains_unknown_even_if_host_claims_pass():
    pool = simulated_complete_pool()
    row = pool[0]
    old = row["artifacts"][2]
    new = replace(old, files=(), availability="api_failure")
    row["artifacts"] = (*row["artifacts"][:2], new)
    row["audit"][new.content_hash] = {key: "pass" for key in row["audit"].pop(old.content_hash)}
    report = inspect_pool(pool)
    dev = report["development"]["natural_complete_triplets"]
    assert dev["conditions"]["candidate"]["audit_outcomes"] == {"pass": 1, "fail": 0, "unknown": 2}
    assert dev["conditions"]["candidate"]["all_attempt_success"]["denominator"] == 3


def test_mixed_origin_triplet_is_not_partially_counted_as_natural():
    pool = simulated_complete_pool()
    row = pool[0]
    old = row["artifacts"][2]
    new = replace(old, provenance_complete=False)
    row["artifacts"] = (*row["artifacts"][:2], new)
    row["audit"][new.content_hash] = row["audit"].pop(old.content_hash)
    report = inspect_pool(pool)
    assert report["development"]["natural_complete_triplets"]["task_repeat_triplets"] == 2
    assert report["development"]["diagnostic_only_triplets"]["task_repeat_triplets"] == 1


def test_skill_changed_per_task_requires_collection_review():
    pool = simulated_complete_pool()
    row = pool[2]  # same repeat, a different task in development
    old = row["artifacts"][2]
    new = replace(old, skill_hash="a" * 64)
    row["artifacts"] = (*row["artifacts"][:2], new)
    row["audit"][new.content_hash] = row["audit"].pop(old.content_hash)
    report = inspect_pool(pool)
    assert "skill_changes_across_tasks_within_repeat_condition_review_collection_protocol" in report["readiness"]["reasons"]


def test_empty_pool_and_duplicate_triplets_are_refused():
    with pytest.raises(ValueError):
        inspect_pool([])
    pool = fixture_pool()
    with pytest.raises(ValueError, match="Duplicate"):
        inspect_pool(pool + [deepcopy(pool[0])])


@pytest.mark.parametrize("kwargs", [{"min_tasks": 0}, {"min_tasks": True},
                                    {"min_audit_coverage": float("nan")}, {"min_audit_coverage": True}])
def test_bad_requirements(kwargs):
    with pytest.raises(ValueError):
        PilotRequirements(**kwargs)


def test_cli_host_only_exact_replay(tmp_path):
    source, output = tmp_path / "source", tmp_path / "output"
    export_pool(fixture_pool(), source)
    args = ["--pool", str(source), "--output", str(output)]
    assert main(args) == 0
    path = output / "host_only/panel.json"
    original = path.read_bytes()
    assert main(args) == 0 and path.read_bytes() == original
    assert not (output / "development_views.json").exists()


def test_output_child_symlink_is_refused(tmp_path):
    source, output, outside = tmp_path / "source", tmp_path / "output", tmp_path / "outside"
    export_pool(fixture_pool(), source)
    output.mkdir()
    outside.mkdir()
    (output / "host_only").symlink_to(outside, target_is_directory=True)
    with pytest.raises(SystemExit) as exc:
        main(["--pool", str(source), "--output", str(output)])
    assert exc.value.code == 2 and not (outside / "panel.json").exists()
