"""Synthetic immutable fixtures; auditor tests perform no model calls/execution."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import audit_coevolution_v4 as a


def put(root, relative, value, wrapped=True):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if wrapped:
        value = {"record": value, "record_hash": a.digest(value)}
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def add_call(root, key, kind="v4_repo_generate", ok=True):
    request = {"model": "glm-5.3", "kind": kind, "key": key, "system": "offline fixture", "user": "offline fixture"}
    identifier = a.digest(request)
    row = {"request": request, "request_hash": identifier, "ok": ok,
           "response": "synthetic content", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
           "http_attempt_count": 1, "attempts": [{"status": 200, "ok": ok}],
           "wall_seconds": .1, "finish_reason": "stop", "returned_model": "glm-5.3", "error_type": None}
    put(root, f"api/calls/{identifier}.json", row, False)
    put(root, f"api/budget_reservations/{identifier}.json", {"request_hash": identifier, "kind": kind}, False)
    return identifier, row


@pytest.fixture
def run(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    put(root, "protocol.json", {"version": "coevolution-v4-engineering-v1", "not_unseen_or_canonical_benchmark": True,
                               "cross_domain_validated": False})
    put(root, "api/budget_protocol.json", {"max_logical_calls": 1600}, False)
    return root


def add_target(root, stage="r0", skill="", repeat=0, initial_valid=False, final_valid=True,
               hard=True, transport_ok=True):
    job = {"id": "synthetic-pipeline", "skill": skill, "stream": 0, "stage": stage, "repeat": repeat}
    identifier = a.digest(job)
    first, _ = add_call(root, identifier + "first")
    second, _ = add_call(root, identifier + "second", "v4_repo_revision", transport_ok)
    files = {"api.py": "synthetic module"} if final_valid else None
    row = {**job, "job_hash": identifier, "artifact_hash": a.digest(files), "skill_hash": a.digest(skill),
           "files": files, "format_ok": final_valid, "target_ok": transport_ok,
           "initial_request_hash": first, "request_hash": second, "request_hashes": [first, second],
           "initial_evaluation": {"files": {"api.py": "first"} if initial_valid else None,
                                  "execution_ok": True, "hard": initial_valid, "public_pass": initial_valid},
           "evaluation": {"execution_ok": True if transport_ok else False,
                          "hard": hard if transport_ok else None, "public_pass": hard if transport_ok else None}}
    put(root, f"targets/{identifier}.json", row)
    return identifier, row


def evidence(passes):
    cases = {f"case{i}": passed for i, passed in enumerate(passes)}
    return {"available": True, "hard": all(passes), "case_results": cases,
            "preserved": {"case0": passes[0]}, "case_total": len(passes), "case_passes": sum(passes)}


def pair():
    base, candidate = evidence([True, False]), evidence([True, True])
    return {"id": "task", "repeat": 0, "base": base, "working": deepcopy(base), "approved": deepcopy(base),
            "candidate": candidate, "probe_results": {"base": {"probe": True}, "working": {"probe": True},
                                                        "approved": {"probe": True}, "candidate": {"probe": False}}}


def add_decision(root):
    proposal_call, _ = add_call(root, "skill-proposal", "v4_skill")
    candidate = {"valid": True, "content": "synthetic skill", "request_hash": proposal_call}
    decision = {"stream": 0, "policy": "fixed", "round": 0, "candidate": candidate,
                "pairs": {"source": [pair()], "replay": [], "scope": [pair()]},
                "local": {"candidate_hash": a.digest(candidate), "passed": False, "action": "Reject", "reasons": ["probe"]},
                "scope": {"candidate_hash": a.digest(candidate), "passed": False, "action": "Restrict", "reasons": ["local"]}}
    put(root, "decisions/r0.json", {"s0_fixed": decision})
    return decision


def cal_rows():
    rows = []
    for truth in ("good", "bad"):
        for artifact in range(2):
            for repeat in range(2):
                rows.append({"artifact_id": f"{truth}{artifact}r{repeat}", "artifact_hash": a.digest([truth, artifact]),
                             "truth": truth, "outcome": "not_detected" if truth == "good" else "unknown",
                             "case_kind": "equivalent" if truth == "good" else "semantic_mutant", "repeat": repeat,
                             "project": "dev-calibration", "claim_key": a.digest([truth, artifact, repeat])})
    return rows


def calibration(promote=True, unproven=False):
    old, new = cal_rows(), cal_rows()
    if promote:
        new[4]["outcome"] = "detected"
    if unproven:
        natural = {"artifact_id": "natural", "artifact_hash": a.digest("natural"), "truth": "oracle_pass_unproven",
                   "outcome": "not_detected", "case_kind": "natural", "repeat": 0, "project": "dev-calibration"}
        old.append(natural)
        new.append({**natural, "outcome": "unknown"})
    selected = {name: [r for r in rows if r["truth"] != "oracle_pass_unproven"] for name, rows in (("old", old), ("new", new))}
    return {"old": old, "new": new, "selection_rows": selected,
            "diagnostic_only": {name: [r for r in rows if r["truth"] == "oracle_pass_unproven"]
                                for name, rows in (("old", old), ("new", new))},
            "decision": {"promote": promote, "reasons": [] if promote else ["no_improvement"],
                         "criteria": {"min_good": 4, "min_bad": 4, "min_unique_good": 2, "min_unique_bad": 2}}}


def add_update(root, use_research=True):
    key = "s0_research_r0" if use_research else "s0_feedback_r0"
    identity = {"key": key}
    directory = Path("research") / key / "validator_evolution" / a.digest(identity)
    stages = []
    for stage in ("plan", "synthesis", "revision"):
        request, _ = add_call(root, key + stage, "v4_validator_revision_" + stage)
        stages.append({"stage": stage, "request_hash": request, "transport_ok": True, "schema_valid": True,
                       "error": None, "max_tokens": 6000})
    research = {"requested": use_research, "executed": use_research, "trigger": {"triggered": True},
                "method": "bounded_official_document_investigation" if use_research else "feedback_only",
                "fetch_status": "complete" if use_research else "not_requested", "sources_requested": int(use_research),
                "sources_available": int(use_research), "source_snapshots": [], "findings": {"findings": []}}
    if use_research:
        text = "The bool class is a subclass of int. This quote is synthetic official-doc fixture data."
        html = ("<p>" + text + "</p>").encode()
        sid = a.digest("source")
        source = {"requested_url": "https://docs.python.org/3/library/stdtypes.html", "snapshot_id": sid,
                  "text": text, "ok": True, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                  "raw_html_sha256": hashlib.sha256(html).hexdigest()}
        put(root, directory / "research_sources/sources.json", [source], False)
        source_dir = directory / "research_sources/documents" / sid
        put(root, source_dir / "source.json", source, False)
        (root / source_dir / "excerpt.txt").write_text(text)
        (root / source_dir / "source.html").write_bytes(html)
        research["source_snapshots"] = [{k: value for k, value in source.items() if k != "text"}]
        research["findings"] = {"findings": [{"evidenceurls": [source["requested_url"]],
                                             "evidencequotes": [{"url": source["requested_url"],
                                                                  "quote": "The bool class is a subclass of int."}]}]}
    proposal = {"identity": identity, "status": "proposal_ready", "stages": stages, "calls_used": 3, "research": research}
    proposal["record_hash"] = a.digest(proposal)
    put(root, directory / "proposal.json", proposal, False)
    update = {"proposal": proposal, "calibration": calibration(unproven=True), "promoted": True, "effective_from_round": 1}
    put(root, f"validator_updates/{key}.json", update)
    return proposal, directory


def test_empty_live_run_is_readonly_progress(run):
    before = sorted(str(p.relative_to(run)) for p in run.rglob("*"))
    report = a.audit(run)
    assert report["status"] == "in_progress_snapshot" and report["api_ledger"]["cached_logical_calls"] == 0
    assert report["api_calls_made_by_audit"] == report["candidate_executions_by_audit"] == 0
    assert report["final"]["status"] == "not_started"
    assert sorted(str(p.relative_to(run)) for p in run.rglob("*")) == before


def test_actual_api_cost_counts_calls_not_policy_aliases(run):
    identifier, _ = add_target(run, stage="final")
    put(run, "final_alias_plan.json", [{"arm": arm, "job_hash": identifier} for arm in ("noskill", "fixed", "research")])
    report = a.audit(run)
    assert report["api_ledger"]["cached_logical_calls"] == 2
    assert report["api_ledger"]["total_tokens"] == 30
    assert report["final"]["logical_alias_rows"] == 3
    assert report["final"]["unique_target_jobs_planned"] == 1
    assert report["targets"]["all"]["delivery_rescued_by_public_revision"] == 1


def test_initial_public_final_full_not_misrepresented_as_same_test(run):
    add_target(run, initial_valid=True, hard=False)
    report = a.audit(run)["targets"]["all"]
    assert report["initial_public_only_categories"]["hard_pass"] == 1
    assert report["final_categories"]["behavior_failure"] == 1
    assert report["initial_and_final_evaluations_have_different_test_visibility"]


@pytest.mark.parametrize("final_valid,hard,ok,category", [(False, False, True, "delivery_failure"),
                                                       (True, False, True, "behavior_failure"),
                                                       (True, True, True, "hard_pass"),
                                                       (False, None, False, "transport_unavailable")])
def test_target_layers(run, final_valid, hard, ok, category):
    add_target(run, final_valid=final_valid, hard=hard, transport_ok=ok)
    assert a.audit(run)["targets"]["all"]["final_categories"][category] == 1


def test_decision_gains_and_probe_losses_recomputed(run):
    add_decision(run)
    report = a.audit(run)["development"]
    assert report["unique_proposal_calls"] == 1 and report["local_commits"] == 0
    evidence = report["rows"][0]["pairs"]["source"]["vs_base"]
    assert evidence["case_pass_gain"] == evidence["hard_gain"] == 1
    assert evidence["mean_case_fraction_gain"] == .5
    assert len(evidence["known_shared_probe_losses"]) == 1


def test_duplicate_pair_refused():
    with pytest.raises(ValueError, match="Duplicate"):
        a._pair_stats([pair(), pair()], "base")


def test_pair_unknown_not_zero_or_pass():
    row = pair()
    row["candidate"]["available"] = False
    result = a._pair_stats([row], "base")
    assert result["unknown_pairs"] == 1 and result["mean_case_fraction_gain"] is None
    assert len(result["known_shared_probe_losses"]) == 1


def test_unproven_natural_diagnostics_excluded_from_promotion():
    result = a.calibration(calibration(unproven=True))
    assert result["independently_recomputed_promote"]
    assert result["new"]["all"]["rows"] == 9
    assert result["new"]["selection"]["rows"] == 8
    assert result["new"]["diagnostic_unproven"]["unknown"] == 1
    assert result["new_paired_unknowns"] == []


@pytest.mark.parametrize("change", ["false_positive", "new_unknown", "lost_detection", "coverage", "same", "unpaired"])
def test_falsely_reported_promotion_refused(change):
    record = calibration()
    if change == "false_positive":
        record["new"][0]["outcome"] = "detected"
    elif change == "new_unknown":
        record["new"][0]["outcome"] = "unknown"
    elif change == "lost_detection":
        record["old"][5]["outcome"] = "detected"
        record["new"][5]["outcome"] = "not_detected"
    elif change == "coverage":
        record["decision"]["criteria"]["min_good"] = 5
    elif change == "same":
        record["new"][4]["outcome"] = "unknown"
    elif change == "unpaired":
        record["new"][0]["artifact_hash"] = "a" * 64
    with pytest.raises(ValueError):
        a.calibration(record)


def test_selection_rows_cannot_omit_bad_cases():
    record = calibration()
    record["selection_rows"]["old"] = record["selection_rows"]["old"][:-1]
    with pytest.raises(ValueError, match="selection rows"):
        a.calibration(record)


@pytest.mark.parametrize("use_research", [False, True])
def test_complete_update_independently_audited(run, use_research):
    add_update(run, use_research)
    report = a.audit(run)["validator_evolution"]
    assert report["promotions"] == 1 and report["completed_updates"] == 1
    row = report["rows"][0]
    assert row["calls_used"] == 3 and row["calibration"]["independently_recomputed_promote"]
    assert row["research"]["verified_exact_quotes"] == int(use_research)
    assert row["research"]["sources_available"] == int(use_research)
    assert row["effective_from_round"] == 1


def test_proposal_pending_calibration_reported(run):
    _, directory = add_update(run)
    (run / "validator_updates/s0_research_r0.json").unlink()
    report = a.audit(run)["validator_evolution"]
    assert (run / directory / "proposal.json").exists()
    assert report["proposal_attempts"] == 1 and report["completed_updates"] == 0
    assert report["rows"][0]["promoted"] is None


@pytest.mark.parametrize("file", ["source.html", "excerpt.txt"])
def test_source_snapshot_tampering_refused(run, file):
    _, directory = add_update(run)
    target = next((run / directory / "research_sources/documents").glob("*/" + file))
    target.write_text("tampered")
    with pytest.raises(ValueError, match="provenance"):
        a.audit(run)


def test_fabricated_quote_refused_despite_resealed_proposal(run):
    proposal, directory = add_update(run)
    proposal["research"]["findings"]["findings"][0]["evidencequotes"][0]["quote"] = "Fabricated quote longer than twenty characters."
    proposal.pop("record_hash")
    proposal["record_hash"] = a.digest(proposal)
    put(run, directory / "proposal.json", proposal, False)
    (run / "validator_updates/s0_research_r0.json").unlink()
    with pytest.raises(ValueError, match="exact bounded"):
        a.audit(run)


def test_representation_risk_flag_does_not_change_verdict(run):
    request, _ = add_call(run, "probe", "v4_probe")
    receipt = {"matched": False, "reference": {"ok": True, "exception": "ValueError",
                "message": "Out of range float values are not JSON compliant"}, "actual": {"ok": True, "value": 1}}
    receipt["receipt_hash"] = a.digest(receipt)
    identifier = a.digest("claim")
    put(run, f"claims/{identifier}.json", {"key": identifier, "request_hash": request,
        "parsed": {"schema_valid": True, "claims": [{"input": {"raw": "1e1000"}}]}, "receipts": [receipt]})
    report = a.audit(run)["claims"]
    assert report["verified_mismatches"] == 1 and len(report["oracle_representation_risks"]) == 1
    assert report["oracle_representation_risks"][0]["recorded_matched"] is False
    assert report["oracle_representation_risks"][0]["automatic_bug_verdict"] is False


def test_tampered_wrapper_refused(run):
    path = run / "protocol.json"
    value = json.loads(path.read_text())
    value["record"]["cross_domain_validated"] = True
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="integrity"):
        a.audit(run)


@pytest.mark.parametrize("field,value", [("http_attempt_count", 4), ("ok", "yes"), ("request_hash", "wrong")])
def test_invalid_raw_api_cache_refused(run, field, value):
    identifier, row = add_call(run, "raw")
    row[field] = value
    put(run, f"api/calls/{identifier}.json", row, False)
    with pytest.raises(ValueError):
        a.audit(run)


@pytest.mark.parametrize("value", [-1, True, 1.5, "10"])
def test_invalid_usage_refused(run, value):
    identifier, row = add_call(run, "usage")
    row["usage"]["total_tokens"] = value
    put(run, f"api/calls/{identifier}.json", row, False)
    with pytest.raises(ValueError):
        a.audit(run)


def test_active_reservation_not_silent_zero(run):
    identifier = a.digest("active")
    put(run, f"api/budget_reservations/{identifier}.json", {"request_hash": identifier, "kind": "v4_probe"}, False)
    report = a.audit(run)["api_ledger"]
    assert report["logical_requests_reserved"] == 1 and report["cached_logical_calls"] == 0
    assert report["unresolved_reservations"] == [identifier]


def test_missing_target_call_refused(run):
    _, row = add_target(run)
    (run / "api/calls" / (row["request_hash"] + ".json")).unlink()
    with pytest.raises(ValueError, match="two actual"):
        a.audit(run)


@pytest.mark.parametrize("relative", ["../outside.json", ".env", "tasks.json", "/tmp/external.json"])
def test_reader_cannot_read_secrets_or_outside_paths(run, relative):
    with pytest.raises(ValueError):
        a.Reader(run).read(relative)


def test_symlinked_input_refused(run, tmp_path):
    (run / "protocol.json").unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    (run / "protocol.json").symlink_to(outside)
    with pytest.raises(ValueError, match="Symlinked"):
        a.audit(run)


def test_mutated_input_detected_after_read(run):
    reader = a.Reader(run)
    reader.read("protocol.json")
    (run / "protocol.json").write_text("{}")
    with pytest.raises(ValueError, match="changed"):
        reader.verify_unchanged()


def test_capture_does_not_absorb_later_target(run):
    reader = a.Reader(run)
    reader.capture_progress_listing()
    add_target(run)
    assert reader.find("targets/*.json") == []
    assert reader.find("api/calls/*.json") == []


def test_output_is_immutable_and_outside_frozen_run(run, tmp_path):
    report = a.audit(run)
    with pytest.raises(ValueError, match="outside"):
        a.write_report(report, run / "audit.json", run)
    output = tmp_path / "audit.json"
    assert a.write_report(report, output, run) == output
    assert a.write_report(report, output, run) == output
    with pytest.raises(ValueError, match="different"):
        a.write_report({**report, "status": "tampered"}, output, run)


def test_finished_run_rechecks_actual_ledger_and_final_labels(run):
    identifier, row = add_target(run, stage="final")
    alias = {"arm": "noskill", "job_hash": identifier}
    put(run, "final_alias_plan.json", [alias])
    derived = {**alias, **{key: row[key] for key in ("id", "stream", "repeat", "artifact_hash", "skill_hash", "format_ok", "target_ok")},
               "hard": row["evaluation"]["hard"]}
    put(run, "final_rows.json", [derived])
    protocol = a.Reader(run).read("protocol.json")
    put(run, "final_frozen.json", {"protocol_hash": a.digest(protocol), "freeze_before_final": True})
    ledger = a.audit(run)["api_ledger"]
    result = {"status": "complete", "ledger": ledger, "local_commits": 0, "scope_commits": 0, "validator_promotions": 0}
    put(run, "results.json", result)
    assert a.audit(run)["status"] == "complete"
    result["ledger"]["total_tokens"] = 999
    put(run, "results.json", result)
    with pytest.raises(ValueError, match="completion ledger"):
        a.audit(run)


def test_cli_stdout_and_external_output(run, tmp_path, capsys):
    a.main([str(run), "--output", str(tmp_path / "cli.json")])
    summary = json.loads(capsys.readouterr().out)
    assert summary["actual_api_calls"] == 0 and summary["status"] == "in_progress_snapshot"
