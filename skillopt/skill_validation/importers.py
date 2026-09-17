"""Thin normalization of checked historical evidence; never promote old data."""
from __future__ import annotations

from .legacy import LegacyImport
from .models import ArtifactRecord, EvidenceRecord, Obligation, Observation, SourceFile, TaskContract, require, text


def normalize_v15(imported: LegacyImport):
    """Convert the host-only legacy bundle to strictly typed visible records.

Raw public dictionaries/logs, API prompts and the private projection are NOT
forwarded. The older solver's explicit nonmutation instruction is retained as
an obligation of THESE historical runs only, never a universal Coding rule.
    """
    require(type(imported) is LegacyImport, "Expected checked V15 import")
    imported.verify_integrity()
    identity, public = imported.identity, imported.public_task
    prompt = public.get("prompt")
    text(prompt)
    quote = prompt[:1000]
    obligations = [Obligation("requested", "requested_behavior",
                              "Implement the behavior stated by the public task contract.", quote)]
    # This exact instruction was actually supplied to the legacy solver.
    system = imported.host_only["api_receipts"][0]["request"]["system"]
    preservation_quote = "Do not mutate input data."
    if preservation_quote in system:
        prompt += "\nLegacy public runtime contract: " + preservation_quote
        obligations.append(Obligation("preserve_input", "input_preservation", preservation_quote, preservation_quote))
    public_files = public.get("files", {})
    require(type(public_files) is dict, "Legacy public files must be a source mapping")
    task = TaskContract(
        task_id=identity["task_id"], original_task_id=identity["task_id"], family_id=identity["family_id"],
        project_id=identity["project_id"], partition="development", domain="coding",
        mechanism="constraint_preservation", prompt=prompt, obligations=tuple(obligations),
        public_files=tuple(SourceFile(k, v) for k, v in sorted(public_files.items())),
    )
    solve = imported.host_only["solve"]
    stage = imported.host_only["stages"][0 if solve["chosen_stage"] == "generation" else 1]
    if imported.artifact is not None:
        require(type(imported.artifact) is dict, "Legacy Coding artifact must be an actual source mapping")
        availability = "available"
    else:
        availability = "parse_failure" if stage["receipt"]["ok"] else "api_failure"
    artifact = ArtifactRecord(
        task_hash=task.content_hash, repeat=identity["repeat"], condition=identity["condition"],
        skill_version="legacy-" + identity["skill_hash"], skill_hash=identity["skill_hash"],
        files=tuple(SourceFile(k, v) for k, v in sorted((imported.artifact or {}).items())),
        availability=availability, provenance_kind=imported.source_kind,
        provenance_complete=imported.provenance["source_closure_complete"], historical_only=True,
        source_ref="legacy-v15-solve:" + identity["solve_hash"], source_hash=identity["solve_hash"],
    )
    require(artifact.artifact_hash == identity["artifact_hash"], "Normalized artifact differs from actual chosen bytes")
    evaluation = stage["public_evaluation"]
    if availability != "available":
        execution_status = availability
    elif evaluation.get("execution_ok") is True:
        execution_status = "observed"
    elif evaluation.get("environment_error") or evaluation.get("unsupported"):
        execution_status = "unsupported"
    else:
        execution_status = "execution_error"
    observations = []
    if execution_status == "observed":
        by_case = {row["case_id"]: row for row in imported.public_observations}
        # A missing public case is retained as unknown, never silently dropped.
        for case in public["public_cases"]:
            case_id = case["case_id"]
            row = by_case.get(case_id, {})
            # Legacy `passed` combines return correctness AND input preservation.
            # Only the separately bound behavior outcome supports this obligation.
            observations.append(Observation(case_id + "_return", "requested", "public_test",
                                            passed=row.get("behavior_passed")))
            if len(obligations) > 1:
                before, after = row.get("input_before_fingerprint"), row.get("input_after_fingerprint")
                if before is not None and after is not None and row.get("input_unchanged") is not None:
                    require(row["input_unchanged"] == (before == after), "Recorded input state observations disagree")
                observations.append(Observation(case_id + "_state", "preserve_input", "input_state",
                                                before_hash=before, after_hash=after))
    evidence = EvidenceRecord(
        task_hash=task.content_hash, artifact_hash=artifact.artifact_hash, artifact_record_hash=artifact.content_hash,
        repeat=artifact.repeat, visibility="public", execution_status=execution_status,
        observations=tuple(observations), source_ref="legacy-public-execution:" + stage["execution_id"],
        source_hash=stage["execution_receipt_hash"], provenance_kind=artifact.provenance_kind,
    )
    # This is a separate HOST artifact. No validator/model view takes this arg.
    audit = {
        "purpose": "host_only_historical_audit_not_model_input",
        "task_hash": task.content_hash, "artifact_record_hash": artifact.content_hash,
        "source_identity": identity, "provenance": imported.provenance,
        "historical_private_evaluation": solve["private_evaluation"],
        "historical_private_score": solve["score"],
        "limitations": ["Historical native oracle is not assumed infallible.",
                        "This legacy audit was exposed in prior development; not fresh calibration/final data.",
                        "Public historical pass flags may use the legacy reference executor; no new weak-oracle claim."],
    }
    return task, artifact, (evidence,), audit
