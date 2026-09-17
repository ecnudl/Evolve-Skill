"""Sealed fixture tests: reporting never runs Study, artifacts, or network calls."""

import hashlib
import json
import socket
import subprocess
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v15 import analysis, reporting
from tests.test_coevolution_v15_study import setup as study_setup  # noqa: F401


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def save(root, name, value):
    value = seal({k: v for k, v in value.items() if k != "record_hash"})
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return value


def load(root, name):
    return json.loads((root / name).read_text(encoding="utf-8"))


def task(name, domain):
    return {"id": name, "cluster_id": name + "-family", "domain": domain,
            "public_cases": [{}, {}],
            "private_cases" if domain == "coding" else "hidden_cases": [{} for _ in range(6)],
            "reference": "DO_NOT_RENDER_PRIVATE_REFERENCE"}


def calibration(tasks, old, new, key, *, corrupt=None):
    names = {"reference": "good", "equivalent": "good", "semantic_mutant": "bad",
             "preservation_mutant": "bad"}
    roles, natural, canonical = {"old": [], "new": []}, {"old": [], "new": []}, []
    source_hashes = {t["id"]: sha(t["id"] + "-actual-natural-artifact") for t in tasks}
    for t in tasks:
        for name, truth in names.items():
            for offset in (0, 4):
                # Bad controls fail only in the second chunk: first-chunk survival
                # must not invalidate an independently checked ordinary mutant.
                outcome = "detected" if truth == "bad" and offset == 4 else "not_detected"
                canonical.append({"task_id": t["id"], "domain": t["domain"], "artifact": name,
                    "truth": truth, "input_offset": offset, "assessment": seal({"outcome": outcome})})
            for role in roles:
                outcome = "detected" if truth == "bad" and (role == "new" or name == "preservation_mutant") else "not_detected"
                roles[role].append({"task_id": t["id"], "domain": t["domain"], "artifact": name,
                    "truth": truth, "assessment": seal({"outcome": outcome})})
        for role in natural:
            natural[role].append({"task_id": t["id"], "domain": t["domain"],
                "source_solve_hash": source_hashes[t["id"]], "ordinary_score": 0.5,
                "assessment": seal({"outcome": "detected" if role == "new" else "not_detected"}),
                "used_for_gate": False})
    metrics = {role: {"true_detections": len(tasks) * (1 if role == "old" else 2),
        "false_rejections": 0, "unknown": 0, "good_unknown": 0,
        "bad_total": 2 * len(tasks), "good_total": 2 * len(tasks)} for role in roles}
    value = {"identity": {"key": key, "repeat": 0, "old_hash": old["record_hash"],
        "new_hash": new["record_hash"], "natural_hashes": source_hashes},
        "phase": "calibration", "rows": roles, "natural_rows": natural,
        "canonical_controls": canonical, "canonical_valid": True, "metrics": metrics,
        "paired_true_detection_gains": len(tasks), "paired_true_detection_losses": 0,
        "natural_detection_gains": len(tasks), "natural_detection_losses": 0,
        "accepted": True, "policy_changed": True, "accepted_state": new,
        "activation": "next_round_only", "natural_labels_used_for_gate": False}
    if corrupt == "metrics":
        value["metrics"]["new"]["true_detections"] += 1
    elif corrupt == "missing_chunk":
        value["canonical_controls"].pop()
    elif corrupt == "natural_gate":
        value["natural_rows"]["new"][0]["used_for_gate"] = True
    elif corrupt == "natural_source":
        value["natural_rows"]["new"][0]["source_solve_hash"] = sha("other artifact")
    elif corrupt == "unchanged_policy":
        value["policy_changed"] = False
    return value


def completed(root, *, accepted=False, corrupt=None, design="smoke"):
    """Small, complete actual-schema run with independent families and no APIs."""
    root.mkdir(exist_ok=True)
    groups = {"train": [[task(f"train-r{r}-{d}", d) for d in ("coding", "spreadsheet")] for r in range(2)],
              "calibration": [[task("cal-" + d, d) for d in ("coding", "spreadsheet")]],
              "final": [task(f"final-{d}-{i}", d) for d in ("coding", "spreadsheet", "rule_reasoning") for i in range(2)]}
    if corrupt == "family_overlap":
        groups["final"][0]["cluster_id"] = groups["train"][0][0]["cluster_id"]
    panel = save(root, "private_panel.json", {"groups": groups})
    files = {"skillopt/coevolution_v15/analysis.py": Path(analysis.__file__).read_text(),
             "skillopt/coevolution_v15/reporting.py": Path(reporting.__file__).read_text()}
    if corrupt == "source_drift":
        files["skillopt/coevolution_v15/reporting.py"] += "\n# drift\n"
    snapshot = save(root, "source_snapshot.json", {"files": files})
    protocol = save(root, "protocol.json", {"design": design, "histories": 1, "rounds": 2,
        "policies": list(analysis.POLICIES), "panel_hash": panel["record_hash"],
        "source_snapshot_hash": snapshot["record_hash"], "source_hashes": {k: sha(v) for k, v in files.items()},
        "task_preflight_hash": None, "final_validator_online_assistance": False,
        "all_checkpoints_frozen_before_any_final": True, "scope_promotion": False, "skill_selection_or_routing": False,
        "split_counts": {"train": 4, "calibration": 2, "final": 6}})
    old = seal({"revision": 0, "search_policy": "initial search", "when": "legal cases", "parent_hash": None})
    new = seal({"revision": 1, "search_policy": "target boundary transitions", "when": "legal cases",
                "parent_hash": old["record_hash"]})
    proposals, calibrations = [], []
    for arm in reporting.ARMS[1:]:
        valid = accepted and arm == "adaptive"
        candidate = new if valid else old
        key = "h0-r0-" + arm
        proposals.append(save(root, "validator/proposals/" + arm + ".json", {
            "identity": {"key": key, "repeat": 0, "parent_hash": old["record_hash"]},
            "arm": arm, "valid": valid, "parent_state_hash": old["record_hash"], "candidate_state": candidate}))
        if valid:
            calibrations.append(save(root, "validator/calibrations/" + arm + ".json",
                calibration(groups["calibration"][0], old, new, key, corrupt=corrupt)))
    validators = {arm: new if accepted and arm == "adaptive" else old for arm in reporting.ARMS}
    states, checkpoints, updates = [], [], []
    for r in range(2):
        current = {}
        for arm in reporting.ARMS:
            text = "DO_NOT_RENDER_SKILL-r0" if r == 0 else "DO_NOT_RENDER_SKILL-r1-" + arm
            current[arm] = {"skill": text, "rules": []}
            parent = "" if r == 0 else states[r - 1][arm]["skill"]
            update = {"history": 0, "round": r, "arm": arm, "state": current[arm], "skill": text,
                "skill_hash": sha(text), "parent_hash": sha(parent), "valid": True, "changed": parent != text,
                "feedback_hash": sha("same-feedback" if r == 0 else arm),
                "request_hash": sha("same-request" if r == 0 else arm),
                "calibration_or_final_feedback_used": False}
            if corrupt == "parent" and r == 1 and arm == "adaptive":
                update["parent_hash"] = sha("wrong parent")
            updates.append(save(root, f"learning/h0-r{r}-{arm}.json", update))
        states.append(current)
        checkpoints.append(save(root, f"checkpoints/round_{r}.json", {"round": r, "skills": [current],
            "validators_for_next_round": [validators], "completed_updates": [u["record_hash"] for u in updates]}))
    frozen = save(root, "final_frozen.json", {"protocol_hash": protocol["record_hash"], "skills": [states[-1]],
        "validators": [validators], "checkpoint_hashes": [c["record_hash"] for c in checkpoints],
        "skill_update_hashes": [u["record_hash"] for u in updates],
        "validator_proposal_hashes": [p["record_hash"] for p in proposals],
        "calibration_hashes": [c["record_hash"] for c in calibrations]})
    def rows(r):
        result = []
        for i, t in enumerate(groups["final"]):
            for policy in analysis.POLICIES:
                text = "" if policy == "no_skill" else states[r][policy]["skill"]
                unknown = policy == "no_skill" and i == 1
                result.append({"task_id": t["id"], "domain": t["domain"], "cluster_id": t["cluster_id"],
                    "history": 0, "policy": policy, "round": r, "phase": "final",
                    "passed": not unknown and (i % 2 == 0 or policy != "no_skill"),
                    "oracle_available": not unknown, "artifact_valid": not unknown,
                    "skill_hash": sha(text), "skill_nonempty": bool(text), "solver_record_hash": sha(t["id"] + policy)})
        return result
    final = rows(1)
    if corrupt == "whole_task_missing":
        final = [r for r in final if r["task_id"] != groups["final"][-1]["id"]]
    elif corrupt == "frozen_skill":
        final[1]["skill_hash"] = sha("not the frozen skill")
    grid = save(root, "final_rows.json", {"frozen_hash": frozen["record_hash"], "rows": final})
    checkpoint_rows = [r for r in rows(0) + final if r["domain"] != "rule_reasoning"]
    if corrupt == "checkpoint_skill":
        checkpoint_rows[1]["skill_hash"] = sha("wrong checkpoint")
    checkpoints_grid = save(root, "checkpoint_rows.json", {"frozen_hash": frozen["record_hash"],
        "rows": checkpoint_rows, "diagnostic_subset_only": True, "feedback_allowed": False})
    summary = analysis.summarize(final, expected_tasks={r["task_id"]: {
        "domain": r["domain"], "cluster_id": r["cluster_id"]} for r in final}, expected_histories=[0])
    if corrupt == "summary":
        summary["policy_summary"]["fixed"]["macro_all_attempt_success"] = 0.1
        summary = seal({k: v for k, v in summary.items() if k != "record_hash"})
    save(root, "results.json", {"complete": True, "design": design, "protocol_hash": protocol["record_hash"],
        "frozen_hash": frozen["record_hash"], "final_grid_hash": grid["record_hash"],
        "checkpoint_grid_hash": checkpoints_grid["record_hash"], "summary": summary,
        "learning": {"update_positions": 6, "valid": 6, "changed": 6, "unique_update_calls": 4},
        "validator_evolution": {"proposals": 2, "valid_proposals": int(accepted),
            "calibrations": int(accepted), "accepted": int(accepted)},
        "ledger": {"cached_logical_calls": 9, "http_attempts_from_cached_records": 10, "terminal_errors": 1,
            "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150, "missing_usage_calls": 1}})
    return root


def tree(root):
    return {str(p.relative_to(root)): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


def test_report_is_immutable_no_network_execution_or_private_content(tmp_path, monkeypatch, capsys):
    root = completed(tmp_path)
    before = tree(root)
    def forbidden(*args, **kwargs):
        raise AssertionError("Reporting must not execute or access network")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    report = reporting.render(root)
    assert tree(root) == before
    assert capsys.readouterr().out == ""
    assert "Smoke 仅检查链路" in report
    assert "没有验证器被激活" in report
    assert "人工控制校准与自然产物诊断分开" in report
    assert "1/6" in report  # Unknown retained, not discarded.
    assert "独立请求身份" in report and "不等于独立训练样本" in report
    assert "自然校准复用 0" in report
    assert "| 0 | 是 | 3 | 3 |" in report
    assert "DO_NOT_RENDER" not in report
    assert reporting.render(root) == report


def test_accepted_multichunk_calibration_and_natural_diagnostics(tmp_path):
    root = completed(tmp_path, accepted=True)
    report = reporting.render(root)
    assert "1 次校准，1 次接受" in report
    assert "| 反馈进化验证器 | 2→4 | 0→0 | 0→0 | 2 / 0 |" in report
    assert "自然校准复用 2" in report
    assert "没有验证器被激活" not in report
    assert "未发现反例不等于正确" in report
    assert "自然结果不参与接收门" in report


@pytest.mark.parametrize(("corrupt", "message"), [
    ("whole_task_missing", "frozen panel"), ("frozen_skill", "frozen Skill"),
    ("parent", "Skill lineage"), ("family_overlap", "Family leakage"),
    ("source_drift", "source drift"), ("summary", "Stored final summary"),
    ("checkpoint_skill", "Checkpoint row Skill"),
])
def test_resealed_inconsistencies_rejected(tmp_path, corrupt, message):
    root = completed(tmp_path, corrupt=corrupt)
    with pytest.raises(ValueError, match=message):
        reporting.render(root)


@pytest.mark.parametrize(("corrupt", "message"), [
    ("metrics", "Stored calibration metrics"), ("missing_chunk", "canonical control grid"),
    ("natural_gate", "used for gate"), ("natural_source", "Natural artifact source"),
    ("unchanged_policy", "text-change flag"),
])
def test_calibration_corruption_rejected(tmp_path, corrupt, message):
    root = completed(tmp_path, accepted=True, corrupt=corrupt)
    with pytest.raises(ValueError, match=message):
        reporting.render(root)


def test_active_run_refused_without_mutation(tmp_path):
    root = completed(tmp_path)
    result = load(root, "results.json")
    result["complete"] = False
    save(root, "results.json", result)
    before = tree(root)
    with pytest.raises(ValueError, match="Only completed"):
        reporting.render(root)
    assert tree(root) == before


def test_unsealed_tampering_refused(tmp_path):
    root = completed(tmp_path)
    result = load(root, "results.json")
    result["learning"]["changed"] = 0
    (root / "results.json").write_text(json.dumps(result))
    with pytest.raises(ValueError):
        reporting.render(root)


def test_missing_or_symlink_evidence_refused(tmp_path):
    root = completed(tmp_path / "run")
    target = root / "source_snapshot.json"
    original = target.read_bytes()
    target.unlink()
    with pytest.raises(ValueError, match="Missing completed"):
        reporting.render(root)
    other = tmp_path / "original.json"
    other.write_bytes(original)
    target.symlink_to(other)
    with pytest.raises(ValueError, match="Symlink"):
        reporting.render(root)


def test_pilot_is_exploratory_not_public_or_significance_proof(tmp_path):
    report = reporting.render(completed(tmp_path, design="pilot"))
    assert "pilot（探索性实验）" in report
    assert "Smoke 仅检查链路" not in report
    assert "不是路由、scope 扩张、原版 SkillOpt 对照或公开 benchmark" in report
    assert "区间未作多重比较控制" in report
    assert "不证明显著优越、等效或安全" in report


def test_nested_assessment_seal_is_verified(tmp_path):
    tasks = [task("cal", "coding")]
    old = seal({"search_policy": "old", "when": "legal"})
    new = seal({"search_policy": "new", "when": "legal"})
    record = calibration(tasks, old, new, "h0-r0-adaptive")
    record = deepcopy(record)
    record["rows"]["new"][0]["assessment"]["outcome"] = "unknown"
    with pytest.raises(ValueError):
        reporting._calibration_counts(record, reporting._metadata(tasks), old, new, {"cal": 8})


@pytest.mark.parametrize("design", ["smoke", "pilot"])
def test_real_study_fixture_records_render_without_api_or_native_replay(request, tmp_path, monkeypatch, design):
    from skillopt.coevolution_v15 import research, runtime, study
    root, state, build = request.getfixturevalue("study_setup")
    sources = {}
    for module in (analysis, reporting):
        relative = "skillopt/coevolution_v15/" + Path(module.__file__).name
        text = Path(module.__file__).read_text()
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        sources[relative] = sha(text)
    monkeypatch.setattr(study, "source_hashes", lambda repo: sources)
    build(design).run()
    before, calls = tree(root), state["calls"]
    def forbidden(*args, **kwargs):
        raise AssertionError("Completed reporting cannot call or execute")
    monkeypatch.setattr(runtime.legacy, "evaluate", forbidden)
    monkeypatch.setattr(research, "fetch_sources", forbidden)
    monkeypatch.setattr(study.Study, "run", forbidden)
    report = reporting.render(root)
    assert "状态：已完成" in report
    assert ("Smoke 仅检查链路" in report) == (design == "smoke")
    assert tree(root) == before and state["calls"] == calls
