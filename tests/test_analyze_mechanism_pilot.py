"""Fabricated completed-run records only; never reads the active real pilot."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import analyze_mechanism_pilot as analysis
from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation.admission import ScopeRule
from skillopt.skill_validation.mechanism_metrics import CONDITIONS, EXPOSURES, summarize
from skillopt.skill_validation.rule_skill import Rule, RuleSkill
from skillopt.validator_pilot.api import digest


def _save(path, record):
    path.write_text(json.dumps(record), encoding="utf-8")


def _reseal(value):
    return seal({k: v for k, v in value.items() if k != "record_hash"})


@pytest.fixture
def completed(tmp_path):
    root = tmp_path / "fixture-completed"
    root.mkdir()
    protocol = seal({"conditions": list(CONDITIONS), "exposures": list(EXPOSURES),
        "histories": 2, "repeats": 1, "deployment_authorized": False,
        "service": {"provider": "FIXTURE", "model": "fixture-no-model", "reasoning_effort": "low"}})
    rules = (Rule("fixture", "Fixture mechanism", ("Check the stated constraint.",), "Explicit contract only.", (),
                  ScopeRule(("requested_behavior",)), ("fixture-evidence",)),)
    histories, frozen = {}, {}
    for history in ("h0", "h1"):
        parent, local = RuleSkill(history, ()), RuleSkill(history, rules)
        histories[history] = {"no_skill": parent, "current": parent, "local": local, "mechanism": parent}
        frozen[history] = seal({"history": history, "protocol_hash": protocol["record_hash"],
            "feedback_hash": digest(["fixture-development", history]),
            "update_statuses": {"local": "candidate", "mechanism": "no_update"},
            "skills": {k: v.to_dict() for k, v in histories[history].items()}})
    freeze = seal({"protocol_hash": protocol["record_hash"], "histories": frozen, "before_any_confirmation": True})
    roster, rows = [], []
    regions = ["target_related"] * 24 + ["near_miss"] * 24 + ["boundary_control"] * 24 + ["unrelated"] * 6
    for index, region in enumerate(regions):
        task = f"fixture-task-{index:03d}"
        family = f"pipeline-{index % 24:02d}" if index < 72 else f"unrelated-{index}"
        for history in histories:
            for condition in CONDITIONS:
                for exposure in EXPOSURES:
                    pos = {"history": history, "task_id": task, "family_id": family, "domain": "coding",
                           "region": region, "repeat": 0, "condition": condition, "exposure": exposure}
                    roster.append(pos)
                    status = "pass"
                    if history == "h0" and condition == "local":
                        if (index in {0, 4} and exposure == "raw") or (index == 5 and exposure == "conditional"):
                            status = "fail"
                        elif index == 6 and exposure == "conditional":
                            status = "unknown"
                    alias = [history, task, "base"] if condition != "local" else [history, task, condition, exposure]
                    rows.append(seal({**pos, "status": status, "skill_applied": condition == "local",
                        "rule_skill_hash": histories[history][condition].content_hash,
                        "request_hash": digest(["initial", alias]), "receipt_hash": digest(["selected", alias]),
                        "trajectory_hash": digest(["trajectory", alias]), "deployment_authorized": False}))
    metrics = summarize(rows, roster, bootstrap_seed=1, bootstrap_samples=3)
    summary = seal({"status": "completed_shadow_pilot", "protocol_hash": protocol["record_hash"],
        "freeze_hash": freeze["record_hash"], "update_statuses": {h: r["update_statuses"] for h, r in frozen.items()},
        "metrics": metrics, "provenance": "engineering_fixture", "deployment_authorized": False,
        "accounting": {"reserved_logical_requests": 580, "terminal_logical_requests": 580,
            "http_attempts": 581, "terminal_failures": 1, "terminal_reported_tokens": 1234,
            "retry_inclusive_token_usage_known": False,
            "by_kind": {"public-initial": 476, "public-revision": 100, "same-feedback-rule-update": 4},
            "request_limit": 1000, "temperature": 0, "generation_seed_sent": False,
            "failed_attempt_token_usage_may_be_missing": True}})
    records = {"summary.json": summary, "protocol.json": protocol,
               "expected_positions.json": seal({"positions": roster}),
               "confirmation_rows.json": seal({"rows": rows}), "frozen_candidates.json": freeze}
    for filename, value in records.items():
        _save(root / filename, value)
    plan = {"kind": "analysis_plan_not_experimental_result", "study": root.name,
        "original_protocol_unchanged": True, "primary_confirmation_tasks": 78,
        "sensitivity_confirmation_tasks": 74, "deployment_authorized": False,
        "additional_sensitivity_excluded_task_ids": [f"fixture-task-{i:03d}" for i in (0, 1, 48, 49)]}
    plan_path = tmp_path / "fixture-predeclared-plan.json"
    _save(plan_path, plan)
    return root, plan_path, records


def test_primary_and_predeclared_sensitivity_keep_denominators_and_unknowns(completed):
    root, plan, _ = completed
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    result = analysis.analyze(root, plan)
    verify(result)
    original, sensitivity = (result["panels"][name] for name in ("primary_78", "sensitivity_74"))
    assert original["tasks"] == 78 and sensitivity["tasks"] == 74
    assert original["descriptive_metrics"]["expected_positions"] == 78 * 2 * 4 * 2
    assert sensitivity["descriptive_metrics"]["expected_positions"] == 74 * 2 * 4 * 2
    original_pairs = original["raw_vs_conditional"]["local"]
    sensitivity_pairs = sensitivity["raw_vs_conditional"]["local"]
    assert {k: original_pairs[k] for k in ("positions", "win", "loss", "tie", "unknown")} == {
        "positions": 156, "win": 2, "loss": 1, "tie": 152, "unknown": 1}
    assert {k: sensitivity_pairs[k] for k in ("positions", "win", "loss", "tie", "unknown")} == {
        "positions": 148, "win": 1, "loss": 1, "tie": 145, "unknown": 1}
    assert original_pairs["raw_pass_to_conditional_unknown"] == 1
    assert original_pairs["by_history"]["h0"]["unknown"] == 1
    assert original_pairs["by_region"]["target_related"]["win"] == 2
    assert sensitivity_pairs["by_region"]["target_related"]["win"] == 1
    assert original_pairs["by_history"]["h1"]["tie"] == 78
    assert result["original_results_unchanged"] and not result["deployment_authorized"]
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


def test_aliases_request_counts_and_fallback_never_become_independent_learning(completed):
    root, plan, _ = completed
    result = analysis.analyze(root, plan)
    primary = result["panels"]["primary_78"]
    assert primary["confirmation_reference_denominators"]["request_hash"] == {
        "referenced_positions": 1248, "unique_references": 468, "aliased_positions": 780}
    assert result["original_all_phase_accounting"]["terminal_logical_requests"] == 580
    assert result["original_all_phase_accounting"]["http_attempts"] == 581
    assert not result["original_all_phase_accounting"]["retry_inclusive_token_usage_known"]
    assert not primary["subset_token_cost_reconstructed"]
    assert primary["raw_vs_conditional"]["mechanism"]["reference_aliases"]["request_hash"]["same_reference_pairs"] == 156
    for history in ("h0", "h1"):
        candidates = result["candidate_content_and_source"][history]["conditions"]
        assert candidates["mechanism"]["rule_count"] == 0
        assert candidates["mechanism"]["update_status"] == "no_update"
        assert "not_new_learning" in candidates["mechanism"]["content_origin"]
        assert candidates["local"]["rule_count"] == 1
        assert candidates["local"]["content_origin"] == "handwritten_fixture_proposal_not_real_learning"
        assert not candidates["local"]["semantic_support_verified"]


def test_reads_only_approved_completed_inputs_not_api_updates_or_host_audits(completed, monkeypatch):
    root, plan, _ = completed
    original_read = Path.read_text
    allowed = {root / filename for filename in (
        "summary.json", "protocol.json", "expected_positions.json", "confirmation_rows.json", "frozen_candidates.json")}
    allowed.add(plan)
    seen = []
    def bounded_read(path, *args, **kwargs):
        assert path in allowed, "Unauthorized analysis input: " + str(path)
        seen.append(path)
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", bounded_read)
    analysis.analyze(root, plan)
    assert set(seen) == allowed


def test_incomplete_run_rejected_before_any_confirmation_read(completed, monkeypatch):
    root, plan, records = completed
    summary = {**records["summary.json"], "status": "learned_shadow_candidates"}
    _save(root / "summary.json", _reseal(summary))
    original_read = Path.read_text
    def only_summary(path, *args, **kwargs):
        assert path == root / "summary.json"
        return original_read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", only_summary)
    with pytest.raises(ValueError, match="Only a completed"):
        analysis.analyze(root, plan)


@pytest.mark.parametrize("tamper", ["row_unsealed", "changed_status_resealed", "changed_skill_hash", "protocol",
    "freeze", "roster_duplicate", "roster_metadata", "accounting"])
def test_tampered_inputs_do_not_silently_change_the_original_results(completed, tamper):
    root, plan, records = completed
    rows = deepcopy(records["confirmation_rows.json"])
    if tamper in {"row_unsealed", "changed_status_resealed", "changed_skill_hash"}:
        row = rows["rows"][0]
        if tamper == "changed_skill_hash":
            row["rule_skill_hash"] = "0" * 64
        else:
            row["status"] = "fail"
        if tamper != "row_unsealed":
            rows["rows"][0] = _reseal(row)
        _save(root / "confirmation_rows.json", _reseal(rows))
    elif tamper in {"roster_duplicate", "roster_metadata"}:
        roster = deepcopy(records["expected_positions.json"])
        if tamper == "roster_duplicate":
            roster["positions"].append(deepcopy(roster["positions"][0]))
        else:
            roster["positions"][0]["family_id"] = "wrong-family"
        _save(root / "expected_positions.json", _reseal(roster))
    elif tamper == "protocol":
        _save(root / "protocol.json", _reseal({**records["protocol.json"], "repeats": 2}))
    elif tamper == "freeze":
        _save(root / "frozen_candidates.json", _reseal({**records["frozen_candidates.json"], "before_any_confirmation": False}))
    else:
        summary = deepcopy(records["summary.json"])
        summary["accounting"]["terminal_logical_requests"] += 1
        _save(root / "summary.json", _reseal(summary))
    with pytest.raises(ValueError):
        analysis.analyze(root, plan)


@pytest.mark.parametrize("change", ["unknown_task", "duplicate", "wrong_primary_count", "wrong_sensitivity_count"])
def test_sensitivity_is_exactly_the_registered_four_task_exclusion(completed, change):
    root, plan_path, _ = completed
    plan = json.loads(plan_path.read_text())
    if change == "unknown_task":
        plan["additional_sensitivity_excluded_task_ids"][0] = "not-a-frozen-task"
    elif change == "duplicate":
        plan["additional_sensitivity_excluded_task_ids"][0] = plan["additional_sensitivity_excluded_task_ids"][1]
    elif change == "wrong_primary_count":
        plan["primary_confirmation_tasks"] = 77
    else:
        plan["sensitivity_confirmation_tasks"] = 75
    _save(plan_path, plan)
    with pytest.raises(ValueError):
        analysis.analyze(root, plan_path)


def test_unknown_is_retained_and_not_reclassified_as_a_confirmed_regression(completed):
    root, plan, _ = completed
    pair = analysis.analyze(root, plan)["panels"]["primary_78"]["raw_vs_conditional"]["local"]
    assert pair["raw"]["counts"] == {"pass": 154, "fail": 2, "unknown": 0}
    assert pair["conditional"]["counts"] == {"pass": 154, "fail": 1, "unknown": 1}
    assert pair["all_attempt_delta"] == 0  # A zero net change does not erase the confirmed regression.
    assert pair["loss"] == 1 and pair["unknown"] == 1


def test_explicitly_missing_position_remains_in_frozen_denominator_as_unknown(completed):
    root, plan, records = completed
    rows = [row for row in records["confirmation_rows.json"]["rows"] if not (
        row["task_id"] == "fixture-task-007" and row["history"] == "h0"
        and row["condition"] == "local" and row["exposure"] == "conditional")]
    summary = deepcopy(records["summary.json"])
    summary["metrics"] = summarize(rows, records["expected_positions.json"]["positions"],
                                    bootstrap_seed=1, bootstrap_samples=3)
    _save(root / "summary.json", _reseal(summary))
    _save(root / "confirmation_rows.json", seal({"rows": rows}))
    primary = analysis.analyze(root, plan)["panels"]["primary_78"]
    assert primary["descriptive_metrics"]["expected_positions"] == 1248
    assert primary["descriptive_metrics"]["observed_positions"] == 1247
    assert primary["descriptive_metrics"]["missing_positions"] == 1
    pair = primary["raw_vs_conditional"]["local"]
    assert pair["positions"] == 156 and pair["conditional"]["missing"] == 1
    assert pair["unknown"] == 2 and pair["loss"] == 1


def test_cli_is_stdout_only_and_outputs_no_complete_api_receipts(completed, capsys):
    root, plan, _ = completed
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    analysis.main(["--run", str(root), "--sensitivity-plan", str(plan)])
    raw = capsys.readouterr().out
    result = json.loads(raw)
    verify(result)
    assert '"api_receipt"' not in raw and '"system"' not in raw and '"user"' not in raw
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


def test_optional_export_preserves_stdout_and_identical_replay(completed, tmp_path, capsys):
    root, plan, _ = completed
    original = {p.name: p.read_bytes() for p in root.iterdir()}
    output = tmp_path / "archive" / "analysis.json"
    argv = ["--run", str(root), "--sensitivity-plan", str(plan), "--output", str(output)]
    analysis.main(argv)
    stdout = json.loads(capsys.readouterr().out)
    assert verify(json.loads(output.read_text())) == stdout == analysis.analyze(root, plan)
    before, timestamp = output.read_bytes(), output.stat().st_mtime_ns
    analysis.main(argv)
    assert json.loads(capsys.readouterr().out) == stdout
    assert output.read_bytes() == before and output.stat().st_mtime_ns == timestamp
    assert original == {p.name: p.read_bytes() for p in root.iterdir()}


def test_export_different_result_cannot_replace_existing_report(completed, tmp_path, capsys, monkeypatch):
    root, plan, _ = completed
    output = tmp_path / "analysis.json"
    argv = ["--run", str(root), "--sensitivity-plan", str(plan), "--output", str(output)]
    analysis.main(argv)
    capsys.readouterr()
    before = output.read_bytes()
    monkeypatch.setattr(analysis, "analyze", lambda *args: seal({"different_fixture_report": True}))
    with pytest.raises(ValueError, match="Immutable artifact differs"):
        analysis.main(argv)
    assert output.read_bytes() == before


@pytest.mark.parametrize("destination", ["run", "inside", "ancestor", "original", "plan", "symlink"])
def test_export_rejects_source_overlap_before_analyzing(completed, tmp_path, monkeypatch, destination):
    root, plan, _ = completed
    alias = tmp_path / "source-alias"
    if destination == "symlink":
        alias.symlink_to(root, target_is_directory=True)
    output = {"run": root, "inside": root / "reports" / "analysis.json", "ancestor": root.parent,
              "original": root / "summary.json", "plan": plan, "symlink": alias / "analysis.json"}[destination]
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    def forbidden(*args):
        raise AssertionError("Invalid export must be rejected before outcome reads")
    monkeypatch.setattr(analysis, "analyze", forbidden)
    with pytest.raises(ValueError):
        analysis.main(["--run", str(root), "--sensitivity-plan", str(plan), "--output", str(output)])
    assert before == {p.name: p.read_bytes() for p in root.iterdir()}


def test_documented_metrics_metadata_upgrade_preserves_original_table(completed):
    root, plan, records = completed
    summary = deepcopy(records["summary.json"])
    summary["metrics"] = _reseal({**summary["metrics"], "version": "mechanism-pilot-descriptive-metrics-v1"})
    _save(root / "summary.json", _reseal(summary))
    result = analysis.analyze(root, plan)
    assert result["panels"]["primary_78"]["descriptive_metrics"] == summary["metrics"]
    assert result["source"]["original_metrics_version"] == "mechanism-pilot-descriptive-metrics-v1"


def test_arbitrary_metrics_version_is_not_silently_accepted(completed):
    root, plan, records = completed
    summary = deepcopy(records["summary.json"])
    summary["metrics"] = _reseal({**summary["metrics"], "version": "unknown_future_metrics"})
    _save(root / "summary.json", _reseal(summary))
    with pytest.raises(ValueError, match="Unsupported historical"):
        analysis.analyze(root, plan)


@pytest.fixture
def completed_case(completed):
    """Synthetic C-shaped completed records, not an actual C model run."""
    root, plan_path, old = completed
    plan = json.loads(plan_path.read_text())
    frozen_plan = seal({"plan": plan, "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "additional_sensitivity_excluded_task_ids": plan["additional_sensitivity_excluded_task_ids"],
        "main_panel_filtered": False})
    rename = {"no_skill": "no_skill", "current": "current", "local": "boolean", "mechanism": "case_details"}
    roster = [{**row, "condition": rename[row["condition"]]} for row in old["expected_positions.json"]["positions"]]
    protocol = seal({**{k: v for k, v in old["protocol.json"].items() if k != "record_hash"},
        "version": analysis.CASE_VERSION, "conditions": list(rename.values()),
        "selection": "repeat_0_only_no_best_of_n_selection", "no_A_solver_cache_reuse": True,
        "all_candidates_frozen_before_any_confirmation": True,
        "shared_holdout_exploratory_extension": True, "independent_replication": False,
        "expected_positions_hash": digest(roster), "sensitivity_hash": frozen_plan["record_hash"]})
    skills, statuses, changed, proposals = {}, {}, {}, {}
    for history, frozen in old["frozen_candidates.json"]["histories"].items():
        skills[history] = {rename[c]: value for c, value in frozen["skills"].items()}
        statuses[history] = {"boolean": "candidate", "case_details": "no_update"}
        changed[history] = {"boolean": True, "case_details": False}
        parent = RuleSkill.from_dict(skills[history]["no_skill"])
        proposals[history] = {}
        for arm in analysis.CASE_CANDIDATES:
            update = seal({"status": statuses[history][arm], "parent_hash": parent.content_hash,
                "candidate": skills[history][arm] if changed[history][arm] else None})
            proposals[history][arm] = seal({"status": statuses[history][arm], "arm": arm,
                "strategy": "mechanism", "update": update, "deployment_authorized": False,
                "semantic_support_verified": False, "fixture_only": True})
    freeze = seal({"protocol_hash": protocol["record_hash"], "before_any_confirmation": True,
        "selected_proposal_repeat": 0, "noncandidate_retains_parent": True,
        "deployment_authorized": False, "skills": skills, "update_statuses": statuses,
        "behavior_changed": changed, "proposal_records": proposals})
    rows = [_reseal({**row, "condition": rename[row["condition"]],
        "update_status": statuses[row["history"]].get(rename[row["condition"]]),
        "predeclared_near_duplicate": row["task_id"] in plan["additional_sensitivity_excluded_task_ids"]})
        for row in old["confirmation_rows.json"]["rows"]]
    metrics = summarize(rows, roster, bootstrap_seed=1, bootstrap_samples=3,
                        candidate_conditions=analysis.CASE_CANDIDATES)
    accounting = deepcopy(old["summary.json"]["accounting"])
    accounting.update(reserved_logical_requests=576, terminal_logical_requests=576, http_attempts=577,
                      by_kind={"public-initial": 476, "public-revision": 100})
    summary = seal({"version": analysis.CASE_VERSION, "status": "completed_shadow_confirmation",
        "protocol_hash": protocol["record_hash"], "freeze_hash": freeze["record_hash"],
        "update_statuses": statuses, "behavior_changed": changed, "metrics": metrics,
        "provenance": "engineering_fixture", "deployment_authorized": False, "accounting": accounting,
        "shared_holdout_exploratory_extension": True, "independent_replication": False})
    records = {"protocol.json": protocol, "summary.json": summary, "frozen_candidates.json": freeze,
        "expected_positions.json": seal({"positions": roster}), "confirmation_rows.json": seal({"rows": rows}),
        "sensitivity_plan.json": frozen_plan}
    for filename, value in records.items():
        _save(root / filename, value)
    return root, plan_path, records


def test_C_names_fresh_baseline_cost_scope_and_shared_holdout_are_explicit(completed_case):
    root, plan, records = completed_case
    result = analysis.analyze(root, plan)
    verify(result)
    context = result["experiment_context"]
    assert context["candidate_conditions"] == ["boolean", "case_details"]
    assert context["baseline_origin"] == "fresh_C_solver_calls_not_A_results"
    assert context["shared_holdout_exploratory_extension"] and not context["independent_replication"]
    assert not context["cross_run_scores_pooled"]
    assert context["accounting_scope"] == "C_confirmation_only_excludes_A_B_and_aborted_runs"
    for name, tasks in (("primary_78", 78), ("sensitivity_74", 74)):
        panel = result["panels"][name]
        assert panel["tasks"] == tasks and panel["comparison_context"] == context
        assert set(panel["raw_vs_conditional"]) == {"no_skill", "current", "boolean", "case_details"}
        assert "raw/case_details_vs_boolean" in panel["descriptive_metrics"]["comparisons"]
        assert not any("local" in key or "mechanism" in key for key in panel["descriptive_metrics"]["arms"])
    assert result["panels"]["primary_78"]["descriptive_metrics"] == records["summary.json"]["metrics"]
    assert result["original_all_phase_accounting"]["terminal_logical_requests"] == 576
    pairs = result["panels"]["primary_78"]["raw_vs_conditional"]["boolean"]
    assert {k: pairs[k] for k in ("positions", "win", "loss", "unknown")} == {
        "positions": 156, "win": 2, "loss": 1, "unknown": 1}
    cold = result["candidate_content_and_source"]["h0"]["conditions"]["case_details"]
    assert cold["rule_count"] == 0 and "not_new_learning" in cold["content_origin"]


def test_C_reader_is_whitelisted_and_emits_no_API_or_prompt_contents(completed_case, monkeypatch, capsys):
    root, plan, records = completed_case
    before = {p: p.read_bytes() for p in root.iterdir()}
    allowed = {root / name for name in records} | {plan}
    read_text, read_bytes = Path.read_text, Path.read_bytes
    seen = set()
    def guarded_text(path, *args, **kwargs):
        assert path in allowed
        seen.add(path)
        return read_text(path, *args, **kwargs)
    def guarded_bytes(path):
        assert path == plan
        return read_bytes(path)
    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", guarded_text)
        patch.setattr(Path, "read_bytes", guarded_bytes)
        analysis.main(["--run", str(root), "--sensitivity-plan", str(plan)])
    raw = capsys.readouterr().out
    assert '"api_receipt"' not in raw and '"system"' not in raw and '"user"' not in raw
    assert seen == allowed
    assert before == {p: p.read_bytes() for p in root.iterdir()}


def _case_rebind(root, records, *, protocol=None, freeze=None, summary=None):
    """Reseal modified metadata to exercise deeper consistency, not only hashes."""
    protocol = _reseal(protocol or records["protocol.json"])
    freeze = _reseal({**(freeze or records["frozen_candidates.json"]), "protocol_hash": protocol["record_hash"]})
    summary = _reseal({**(summary or records["summary.json"]), "protocol_hash": protocol["record_hash"],
                       "freeze_hash": freeze["record_hash"]})
    for filename, value in (("protocol.json", protocol), ("frozen_candidates.json", freeze), ("summary.json", summary)):
        _save(root / filename, value)


@pytest.mark.parametrize("change", ["version", "cache_reuse", "selection", "replication", "arm_order", "roster_hash"])
def test_C_protocol_cannot_silently_be_reinterpreted(completed_case, change):
    root, plan, records = completed_case
    protocol = deepcopy(records["protocol.json"])
    field, value = {"version": ("version", "unreviewed-v3"), "cache_reuse": ("no_A_solver_cache_reuse", False),
        "selection": ("selection", "best_of_repeats"), "replication": ("independent_replication", True),
        "arm_order": ("conditions", ["no_skill", "current", "case_details", "boolean"]),
        "roster_hash": ("expected_positions_hash", digest("different"))}[change]
    protocol[field] = value
    _case_rebind(root, records, protocol=protocol)
    with pytest.raises(ValueError):
        analysis.analyze(root, plan)


@pytest.mark.parametrize("change", ["repeat", "status", "candidate", "parent", "changed_flag", "warm_base"])
def test_C_primary_freeze_cannot_change_selected_candidate_or_cold_parent(completed_case, change):
    root, plan, records = completed_case
    freeze = deepcopy(records["frozen_candidates.json"])
    if change == "repeat":
        freeze["selected_proposal_repeat"] = 1
    elif change == "changed_flag":
        freeze["behavior_changed"]["h0"]["boolean"] = False
    elif change == "warm_base":
        freeze["skills"]["h0"]["no_skill"] = freeze["skills"]["h0"]["boolean"]
    else:
        proposal = freeze["proposal_records"]["h0"]["boolean"]
        if change == "status":
            proposal["status"] = "no_update"
        elif change == "parent":
            proposal["update"]["parent_hash"] = digest("different-parent")
        else:
            proposal["update"]["candidate"] = freeze["skills"]["h0"]["current"]
        proposal["update"] = _reseal(proposal["update"])
        freeze["proposal_records"]["h0"]["boolean"] = _reseal(proposal)
    summary = deepcopy(records["summary.json"])
    summary["behavior_changed"] = deepcopy(freeze["behavior_changed"])
    _case_rebind(root, records, freeze=freeze, summary=summary)
    with pytest.raises(ValueError):
        analysis.analyze(root, plan)


@pytest.mark.parametrize("change", ["annotation", "update_status", "original_metrics", "frozen_plan"])
def test_C_row_metrics_and_plan_consistency(completed_case, change):
    root, plan, records = completed_case
    if change in {"annotation", "update_status"}:
        rows = deepcopy(records["confirmation_rows.json"])
        row = rows["rows"][0]
        row["predeclared_near_duplicate" if change == "annotation" else "update_status"] = (
            not row["predeclared_near_duplicate"] if change == "annotation" else "candidate")
        rows["rows"][0] = _reseal(row)
        _save(root / "confirmation_rows.json", _reseal(rows))
    elif change == "original_metrics":
        summary = deepcopy(records["summary.json"])
        summary["metrics"] = _reseal({**summary["metrics"], "version": "mechanism-pilot-descriptive-metrics-v1"})
        _save(root / "summary.json", _reseal(summary))
    else:
        frozen_plan = deepcopy(records["sensitivity_plan.json"])
        frozen_plan["main_panel_filtered"] = True
        _save(root / "sensitivity_plan.json", _reseal(frozen_plan))
    with pytest.raises(ValueError):
        analysis.analyze(root, plan)


def test_C_no_changed_candidates_not_counted_as_completed_learning(completed_case, monkeypatch):
    root, plan, records = completed_case
    summary = _reseal({**records["summary.json"], "status": "no_changed_primary_candidates"})
    _save(root / "summary.json", summary)
    read_text = Path.read_text
    def summary_only(path, *args, **kwargs):
        assert path == root / "summary.json"
        return read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", summary_only)
    with pytest.raises(ValueError, match="Only a completed"):
        analysis.analyze(root, plan)
