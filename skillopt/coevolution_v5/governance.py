"""Finite-evidence Skill governance and one-use independent validator calibration.

Nothing here certifies general safety. Host-verified execution evidence can
authorize only the observed task/project coverage. Model opinions and citation
existence cannot authorize deployment. Human review imports are attestations,
not software-authenticated claims that a person actually performed a review.
"""

from __future__ import annotations

import json
import os
import random
import re
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from skillopt.validator_pilot.api import digest, write_immutable_json

VERSION = "coevolution-v5-governance-v1"
HARD_EVIDENCE = frozenset({"execution", "native_oracle", "differential_execution", "deterministic_contract"})
STATUSES = frozenset({"pass", "fail", "unknown", "not_applicable"})
INTERPRETATION = "finite_evidence_selection_not_statistical_safety_or_cross_domain_certificate"


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 1000


def _hash(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _seal(value: dict, key: str) -> dict:
    return {**value, key: digest(value)}


def _verify(value: Mapping, key: str) -> dict:
    copied = deepcopy(dict(value))
    if copied.pop(key, None) != digest(copied):
        raise ValueError(f"{key} integrity mismatch")
    return copied


def _assessment(record: Mapping, task_id: str, domain: str, skill_hash: str) -> dict:
    row = _verify(record, "receipt_hash")
    if (not _text(row.get("check_id")) or row.get("task_id") != task_id
            or row.get("domain") != domain or not _hash(row.get("artifact_hash"))
            or not _hash(row.get("rubric_hash")) or row.get("status") not in STATUSES
            or type(row.get("verified")) is not bool or type(row.get("gate_eligible")) is not bool
            or not _text(row.get("evidence_kind"))):
        raise ValueError("Invalid or mismatched assessment provenance")
    if row.get("phase") != "development":
        raise ValueError("Only development evidence may update a Skill")
    if type(row.get("repeat", 0)) is not int or row.get("repeat", 0) < 0:
        raise ValueError("Assessment repeat must be a nonnegative integer")
    details = row.get("details", {})
    if details.get("solver_skill_hash") != skill_hash or not isinstance(details.get("solver_request_hashes"), list):
        raise ValueError("Assessment must bind its host solver Skill and request receipts")
    if not details["solver_request_hashes"] or not all(_hash(value) for value in details["solver_request_hashes"]):
        raise ValueError("Assessment needs actual solver request hashes")
    from skillopt.coevolution_v5.core import development_only

    development_only(details)
    return row


def _hard(row: dict | None) -> bool:
    return bool(row and row["verified"] and row["gate_eligible"] and row["evidence_kind"] in HARD_EVIDENCE)


def _case_flags(row: dict | None) -> dict:
    if not _hard(row):
        return {}
    cases = row.get("details", {}).get("case_results", [])
    if not isinstance(cases, list):
        raise ValueError("Host case_results must be a list")
    result = {}
    for case in cases:
        if not isinstance(case, dict) or not _text(case.get("id")) or type(case.get("passed")) is not bool:
            raise ValueError("Case observations require stable IDs and boolean outcomes")
        if case["id"] in result:
            raise ValueError("Duplicate native case observation")
        result[case["id"]] = case["passed"]
    return result


def evaluate_pairs(pairs: Sequence[Mapping], require_gain: bool) -> dict:
    """Compare frozen checks in paired Base/Current/Candidate observations.

    Known pass -> fail harm takes precedence over incomplete evidence. Soft
    observations are diagnostic only. Required hard checks cannot disappear or
    change applicability/rubric between arms. Repeated positions are explicit;
    repeated observations never imply independent project coverage.
    """
    if type(require_gain) is not bool or not isinstance(pairs, (list, tuple)):
        raise ValueError("Expected pair sequence and boolean gain requirement")
    harms, unknown, ignored = [], [], []
    gains = {"baseline": 0, "current": 0}
    supplemental_gains = {"baseline": 0, "current": 0}
    comparable = {"baseline": 0, "current": 0}
    coverage = set()
    pair_keys = set()
    for incoming in pairs:
        pair = dict(incoming)
        task_id, cluster_id = pair.get("task_id"), pair.get("cluster_id")
        repeat = pair.get("repeat", 0)
        if not _text(task_id) or not _text(cluster_id) or type(repeat) is not int or repeat < 0:
            raise ValueError("Pair needs a task, project cluster, and nonnegative repeat")
        if (task_id, repeat) in pair_keys:
            raise ValueError("Duplicate paired task/repeat position")
        pair_keys.add((task_id, repeat))
        domains = {row.get("domain") for arm in ("baseline", "current", "candidate")
                   for row in pair.get(arm, [])}
        domain = pair.get("domain") or (next(iter(domains)) if len(domains) == 1 else None)
        if not _text(domain):
            raise ValueError("Pair needs one unambiguous domain")
        from skillopt.coevolution_v5.core import initial_rubric

        expected_checks = {check["id"] for check in initial_rubric()["checks"]}
        required_checks = pair.get("required_check_ids")
        expected_required = {"coding_contract"} if domain == "coding" else {"qa_answer"} if domain == "qa" else set()
        if (not isinstance(required_checks, list) or not expected_required
                or set(required_checks) != expected_required or len(required_checks) != len(set(required_checks))):
            raise ValueError("Host required checks must match the fixed domain contract")
        rubric_hash = pair.get("rubric_hash")
        skill_hashes = pair.get("skill_hashes")
        if not _hash(rubric_hash) or not isinstance(skill_hashes, dict) or set(skill_hashes) != {"baseline", "current", "candidate"}:
            raise ValueError("Pair must freeze its Rubric and all three solver Skill hashes")
        if not all(_hash(value) for value in skill_hashes.values()) or skill_hashes["baseline"] != digest(""):
            raise ValueError("Baseline must be No-Skill and all Skill identities must be content hashes")
        indexed = {}
        for arm in ("baseline", "current", "candidate"):
            if not isinstance(pair.get(arm), (list, tuple)):
                raise ValueError("Each arm must contain an assessment list")
            indexed[arm] = {}
            for record in pair[arm]:
                row = _assessment(record, task_id, domain, skill_hashes[arm])
                if row["rubric_hash"] != rubric_hash:
                    raise ValueError("Paired checks must use the same frozen Rubric")
                key = (row["check_id"], row.get("repeat", 0))
                if key in indexed[arm]:
                    raise ValueError("Duplicate check/repeat within one arm")
                indexed[arm][key] = row
            if {key[0] for key in indexed[arm]} != expected_checks:
                raise ValueError("Each arm must report every frozen check, including explicit non-applicability")
            if len({row["artifact_hash"] for row in indexed[arm].values()}) != 1:
                raise ValueError("One arm cannot combine assessments of different artifacts")
        keys = set().union(*(set(rows) for rows in indexed.values()))
        pair_comparable = 0
        for key in sorted(keys):
            values = {arm: rows.get(key) for arm, rows in indexed.items()}
            position = {"task_id": task_id, "cluster_id": cluster_id, "domain": domain,
                        "pair_repeat": repeat, "check_id": key[0], "check_repeat": key[1]}
            required = key[0] in required_checks
            hard_kind = any(row and row["evidence_kind"] in HARD_EVIDENCE for row in values.values())
            if all(row and row["status"] == "not_applicable" for row in values.values()) and not required:
                continue
            if not required and not hard_kind:
                ignored.append({**position, "reason": "non_gate_or_soft_evidence"})
                continue
            rubrics = {row["rubric_hash"] for row in values.values() if row}
            if len(rubrics) != 1:
                raise ValueError("Paired checks must use the same frozen Rubric")
            candidate = values["candidate"]
            for arm in ("baseline", "current"):
                reference = values[arm]
                if _hard(candidate) and _hard(reference):
                    left, right = reference["status"], candidate["status"]
                    if left == "pass" and right == "fail":
                        harms.append({**position, "reference": arm, "kind": "verified_paired_regression"})
                    before_cases, after_cases = _case_flags(reference), _case_flags(candidate)
                    for case_id in sorted(set(before_cases) & set(after_cases)):
                        if before_cases[case_id] and not after_cases[case_id]:
                            harms.append({**position, "reference": arm, "case_id": case_id,
                                          "kind": "verified_native_case_regression"})
                    if set(before_cases) != set(after_cases):
                        unknown.append({**position, "reference": arm, "blocking": required,
                                        "reason": "native_case_coverage_changed"})
                    if left in {"pass", "fail"} and right in {"pass", "fail"}:
                        if required:
                            comparable[arm] += 1
                            pair_comparable += 1
                            gains[arm] += int(right == "pass") - int(left == "pass")
                        else:
                            supplemental_gains[arm] += int(right == "pass") - int(left == "pass")
                    else:
                        unknown.append({**position, "reference": arm, "blocking": required,
                                        "reason": "unknown_or_changed_applicability"})
                else:
                    unknown.append({**position, "reference": arm, "blocking": required,
                                    "reason": "missing_verified_hard_evidence"})
        if pair_comparable:
            coverage.add((domain, cluster_id, task_id))
        else:
            unknown.append({"task_id": task_id, "blocking": True, "reason": "no_applicable_paired_hard_checks"})
    reasons = []
    if harms:
        reasons.append("verified_paired_regression")
    if not pairs or not all(comparable.values()) or any(row["blocking"] for row in unknown):
        reasons.append("incomplete_behavioral_evidence")
    if require_gain and any(value <= 0 for value in gains.values()):
        reasons.append("no_positive_gain_against_both_references")
    result = {
        "passed": not reasons, "action": "Reject" if harms else ("Restrict" if reasons else "Pass"),
        "reasons": reasons, "harms": harms, "unknown": unknown, "ignored": ignored,
        "gains": gains, "supplemental_gains": supplemental_gains, "comparable": comparable,
        "coverage": [{"domain": domain, "cluster_id": cluster, "task_id": task}
                     for domain, cluster, task in sorted(coverage)],
        "require_gain": require_gain, "pairs": deepcopy(list(pairs)),
        "interpretation": INTERPRETATION,
    }
    return _seal(result, "decision_hash")


def initial_skill_state() -> dict:
    return _seal({"version": VERSION, "working": "", "approved": "", "repair_parent": None,
                  "approved_scope": [], "revoked_scopes": [], "last_round": None,
                  "revision": 0, "history": []}, "state_hash")


def _state(state: Mapping) -> dict:
    value = _verify(state, "state_hash")
    if value.get("version") != VERSION:
        raise ValueError("Unknown Skill state version")
    return value


def _skill_content(skill: Any) -> str:
    return skill if isinstance(skill, str) else skill["content"]


def _bind_skills(pairs, candidate: Any, current: Any):
    for pair in pairs:
        if pair.get("skill_hashes") != {"baseline": digest(""), "current": digest(_skill_content(current)),
                                       "candidate": digest(_skill_content(candidate))}:
            raise ValueError("Paired solver Skill identities do not match the candidate and current state")


def transition_skill(state: Mapping, candidate: Any, local_evidence: Mapping,
                     scope_evidence: Sequence[Mapping], round_index: int) -> dict:
    """Local evidence is {'source': pairs, 'replay': pairs}; scope is pairs.

    A failed scope gate retains a locally improved Working Skill but cannot
    change Approved. Failed candidates remain optimizer-only repair parents.
    """
    current = _state(state)
    if type(round_index) is not int or round_index < 0 or (
        current["last_round"] is not None and round_index <= current["last_round"]
    ):
        raise ValueError("Skill rounds must advance monotonically")
    content = candidate if isinstance(candidate, str) else candidate.get("content") if isinstance(candidate, dict) else None
    if not isinstance(content, str) or not content.strip() or (
        isinstance(candidate, dict) and candidate.get("valid", True) is not True
    ):
        raise ValueError("Candidate must contain nonempty valid Skill text")
    if set(local_evidence) - {"source", "replay"} or "source" not in local_evidence:
        raise ValueError("Local evidence requires source and optional replay pairs")
    _bind_skills(local_evidence["source"], candidate, current["working"])
    _bind_skills(local_evidence.get("replay", []), candidate, current["working"])
    _bind_skills(scope_evidence, candidate, current["approved"])
    source = evaluate_pairs(local_evidence["source"], True)
    replay_pairs = local_evidence.get("replay", [])
    replay = evaluate_pairs(replay_pairs, False) if replay_pairs else None
    local_pass = source["passed"] and (replay is None or replay["passed"])
    scope = evaluate_pairs(scope_evidence, False)
    approved = local_pass and scope["passed"]
    if local_pass:
        current["working"] = deepcopy(candidate)
    if approved:
        current["approved"] = deepcopy(candidate)
        all_coverage = source["coverage"] + scope["coverage"] + (replay["coverage"] if replay else [])
        current["approved_scope"] = sorted({(r["domain"], r["cluster_id"], r["task_id"])
                                             for r in all_coverage})
        current["approved_scope"] = [{"domain": d, "cluster_id": c, "task_id": t}
                                     for d, c, t in current["approved_scope"]]
        current["repair_parent"] = None
    else:
        current["repair_parent"] = {"candidate": deepcopy(candidate), "round_index": round_index,
                                    "source": source, "replay": replay, "scope": scope,
                                    "eligible_for_execution": False, "usage": "optimizer_repair_only"}
    rejected = bool(source["harms"] or (replay and replay["harms"]))
    action = "ScopeCommit" if approved else "LocalCommit" if local_pass else "Reject" if rejected else "Restrict"
    transition = {"round_index": round_index, "candidate_hash": digest(candidate), "action": action,
                  "local_passed": local_pass, "scope_passed": approved,
                  "source_decision_hash": source["decision_hash"],
                  "replay_decision_hash": replay["decision_hash"] if replay else None,
                  "scope_decision_hash": scope["decision_hash"], "interpretation": INTERPRETATION}
    current["last_round"] = round_index
    current["revision"] += int(local_pass)
    current["history"].append(transition)
    current["last_transition"] = transition
    return _seal(current, "state_hash")


def revoke_scope(state: Mapping, domain: str, evidence: Mapping | Sequence[Mapping], reason: str) -> dict:
    """Revoke only the current Approved artifact's observed domain coverage.

    Recomputes hard paired harm from receipts; a caller-provided `harms` field,
    model criticism, or unsupported research citation cannot revoke a Skill.
    """
    current = _state(state)
    if not _text(domain) or not _text(reason):
        raise ValueError("Revocation requires an explicit domain and reason")
    if isinstance(evidence, Mapping):
        checked = _verify(evidence, "decision_hash")
        pairs = checked["pairs"]
    else:
        pairs = evidence
    decision = evaluate_pairs(pairs, False)
    if any(pair["skill_hashes"]["candidate"] != digest(_skill_content(current["approved"])) for pair in pairs):
        raise ValueError("Revocation evidence must evaluate the current Approved Skill")
    harms = [row for row in decision["harms"] if row["domain"] == domain]
    if not harms:
        raise ValueError("Revocation requires confirmed paired harm in the named domain")
    if not current["approved"] or domain not in {row["domain"] for row in current["approved_scope"]}:
        raise ValueError("No current Approved scope exists for this domain")
    record = {"domain": domain, "approved_hash": digest(_skill_content(current["approved"])), "reason": reason,
              "evidence_hash": decision["decision_hash"], "harms": harms}
    if record not in current["revoked_scopes"]:
        current["revoked_scopes"].append(record)
    return _seal(current, "state_hash")


def eligible_skill(state: Mapping, domain: str, *, task_id: str | None = None,
                   cluster_id: str | None = None) -> dict:
    """Abstain on unseen coverage or a revoked domain; never deploy Working."""
    current = _state(state)
    approved = current["approved"]
    revoked = any(r["domain"] == domain and r["approved_hash"] == digest(_skill_content(approved))
                  for r in current["revoked_scopes"])
    observed = any(row["domain"] == domain and (
        (task_id is not None and row["task_id"] == task_id)
        or (cluster_id is not None and row["cluster_id"] == cluster_id)
    ) for row in current["approved_scope"])
    eligible = bool(approved and observed and not revoked)
    return {"eligible": eligible, "skill": deepcopy(approved) if eligible else "",
            "fallback": not eligible, "reason": "observed_scope" if eligible else "revoked_scope" if revoked
            else "unobserved_or_empty_scope", "interpretation": INTERPRETATION}


def _artifacts(manifest: Mapping) -> list[dict]:
    if not isinstance(manifest, Mapping):
        raise ValueError("Calibration manifest must be an object")
    if manifest.get("phase", "promotion") != "promotion":
        raise ValueError("Calibration manifest must belong to the promotion split")
    artifacts = deepcopy(manifest.get("artifacts"))
    if not isinstance(artifacts, list) or not artifacts or len(artifacts) > 10000:
        raise ValueError("Calibration manifest requires bounded nonempty artifacts")
    ids, hashes = set(), set()
    for row in artifacts:
        if (not _text(row.get("artifact_id")) or not _hash(row.get("artifact_hash"))
                or not _text(row.get("cluster_id")) or row.get("truth") not in {"good", "bad", "unknown"}):
            raise ValueError("Invalid calibration artifact identity or oracle truth")
        if row["artifact_id"] in ids or row["artifact_hash"] in hashes:
            raise ValueError("Duplicate calibration artifact ID or content hash")
        ids.add(row["artifact_id"])
        hashes.add(row["artifact_hash"])
    for truth in ("good", "bad"):
        rows = [row for row in artifacts if row["truth"] == truth]
        if len(rows) < 2 or len({row["cluster_id"] for row in rows}) < 2:
            raise ValueError("Calibration requires two unique artifacts and project clusters per truth")
    return artifacts


def _repeats(manifest: Mapping) -> list[int]:
    repeats = manifest.get("repeats", [0, 1])
    if (not isinstance(repeats, (list, tuple)) or not repeats or len(repeats) > 100
            or any(type(repeat) is not int or repeat < 0 for repeat in repeats)
            or len(set(repeats)) != len(repeats)):
        raise ValueError("Calibration repeats must be predeclared unique nonnegative positions")
    return sorted(repeats)


def _calibration_rows(rows: Sequence[Mapping]) -> dict:
    if not isinstance(rows, (list, tuple)) or not rows or len(rows) > 10000:
        raise ValueError("Calibration rows must be bounded and nonempty")
    indexed, identities, hashes = {}, {}, {}
    for incoming in rows:
        row = dict(incoming)
        repeat = row.get("repeat", 0)
        if (not _text(row.get("artifact_id")) or not _hash(row.get("artifact_hash"))
                or not _text(row.get("cluster_id")) or row.get("truth") not in {"good", "bad", "unknown"}
                or row.get("outcome") not in {"detected", "not_detected", "unknown"}
                or type(repeat) is not int or repeat < 0):
            raise ValueError("Invalid calibration observation")
        identity = (row["artifact_hash"], row["cluster_id"], row["truth"])
        if identities.setdefault(row["artifact_id"], identity) != identity:
            raise ValueError("Artifact identity changes across repeats")
        if hashes.setdefault(row["artifact_hash"], row["artifact_id"]) != row["artifact_id"]:
            raise ValueError("One artifact content cannot masquerade as multiple artifacts")
        key = (row["artifact_id"], repeat)
        if key in indexed:
            raise ValueError("Duplicate calibration artifact/repeat position")
        indexed[key] = {**row, "repeat": repeat}
    return indexed


def _counts(rows: Mapping) -> dict:
    values = list(rows.values())
    counts = {"positions": len(values), "clusters": len({r["cluster_id"] for r in values}),
              "unknown_truth": sum(r["truth"] == "unknown" for r in values),
              "unknown_outcomes": sum(r["outcome"] == "unknown" and r["truth"] != "unknown" for r in values)}
    for truth in ("good", "bad"):
        selected = [r for r in values if r["truth"] == truth]
        counts[truth] = len(selected)
        counts[f"unique_{truth}"] = len({r["artifact_hash"] for r in selected})
        counts[f"{truth}_clusters"] = len({r["cluster_id"] for r in selected})
    counts["false_rejections"] = sum(r["truth"] == "good" and r["outcome"] == "detected" for r in values)
    counts["detected_bad"] = sum(r["truth"] == "bad" and r["outcome"] == "detected" for r in values)
    return counts


def promote(old_rows: Sequence[Mapping], new_rows: Sequence[Mapping], *, min_good: int = 4,
            min_bad: int = 4) -> dict:
    """Conservative paired selection; returns aggregate counts, no raw labels."""
    if any(type(value) is not int or value < 1 for value in (min_good, min_bad)):
        raise ValueError("Calibration minima must be positive integers")
    old, new = _calibration_rows(old_rows), _calibration_rows(new_rows)
    if set(old) != set(new):
        raise ValueError("Old and new validators require exactly matched positions")
    for key in old:
        if any(old[key].get(field) != new[key].get(field)
               for field in ("artifact_hash", "cluster_id", "truth", "task_id")):
            raise ValueError("Paired calibration provenance differs")
    before, after = _counts(old), _counts(new)
    regressions = {"new_false_rejections": 0, "new_unknowns": 0, "lost_detections": 0}
    for key, left in old.items():
        right = new[key]
        if left["truth"] == "unknown":
            continue  # An unresolved oracle dispute is not a good/bad label.
        regressions["new_false_rejections"] += int(left["truth"] == "good"
                                                  and left["outcome"] != "detected" and right["outcome"] == "detected")
        regressions["new_unknowns"] += int(left["outcome"] != "unknown" and right["outcome"] == "unknown")
        regressions["lost_detections"] += int(left["truth"] == "bad" and left["outcome"] == "detected"
                                              and right["outcome"] != "detected")
    reasons = []
    if before["good"] < min_good or before["bad"] < min_bad:
        reasons.append("insufficient_observation_positions")
    if before["unique_good"] < 2 or before["unique_bad"] < 2:
        reasons.append("insufficient_unique_artifacts")
    if before["good_clusters"] < 2 or before["bad_clusters"] < 2:
        reasons.append("insufficient_project_coverage")
    reasons.extend(name for name, count in regressions.items() if count)
    improved = after["detected_bad"] > before["detected_bad"] or (
        after["unknown_outcomes"] < before["unknown_outcomes"] and after["detected_bad"] >= before["detected_bad"]
    )
    if not improved:
        reasons.append("no_strict_detection_or_availability_improvement")
    return _seal({"promote": not reasons, "reasons": reasons, "old": before, "new": after,
                  "regressions": regressions, "paired_rows_hash": digest({"old": old_rows, "new": new_rows}),
                  "criteria": {"min_good": min_good, "min_bad": min_bad, "min_unique_per_truth": 2,
                               "min_clusters_per_truth": 2},
                  "activation": "next_round_only" if not reasons else "retain_previous_validator",
                  "interpretation": INTERPRETATION}, "promotion_hash")


def _promotion_assessments(row: Mapping, artifact: Mapping, rubric_hash: str) -> str:
    """Recompute an outcome from host-sealed, version-bound Coding evidence.

    Receipt hashes establish integrity/provenance within the local experiment,
    not cryptographic authentication of the host. The caller still must use
    the sandboxed adapter; model-written labels cannot substitute for receipts.
    """
    from skillopt.coevolution_v5.core import initial_rubric

    assessments = row.get("assessments")
    if not isinstance(assessments, (list, tuple)) or len(assessments) != 4:
        raise ValueError("Calibration outcomes require all four sealed host assessments")
    expected = {check["id"] for check in initial_rubric()["checks"]}
    indexed = {}

    def promotion_only(value):
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key.casefold() in {"phase", "split", "task_split", "source_phase", "source_split", "requested_phase"}:
                    if not isinstance(child, str) or child not in {"promotion", "calibration"}:
                        raise ValueError("Calibration receipt contains evidence from a non-promotion split")
                promotion_only(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                promotion_only(child)

    for incoming in assessments:
        if not isinstance(incoming, Mapping):
            raise ValueError("Calibration assessment must be a sealed object")
        assessment = _verify(incoming, "receipt_hash")
        identifier = assessment.get("check_id")
        if identifier not in expected or identifier in indexed:
            raise ValueError("Calibration checks must be complete and unique")
        if (assessment.get("artifact_hash") != artifact["artifact_hash"]
                or assessment.get("task_id") != artifact["task_id"]
                or assessment.get("rubric_hash") != rubric_hash or assessment.get("domain") != "coding"):
            raise ValueError("Calibration assessment artifact/task/Rubric identity mismatch")
        details = assessment.get("details")
        if (assessment.get("phase") != "promotion" or not isinstance(details, dict)
                or details.get("task_split") not in {"promotion", "calibration"}
                or details.get("requested_phase") != "promotion"):
            raise ValueError("Calibration assessments must bind requested promotion and original task split")
        promotion_only(details)
        if (assessment.get("status") not in STATUSES or type(assessment.get("verified")) is not bool
                or type(assessment.get("gate_eligible")) is not bool):
            raise ValueError("Invalid calibration assessment outcome or evidence flags")
        if identifier in {"coding_contract", "coding_probe"} and assessment.get("evidence_kind") != "execution":
            raise ValueError("Coding calibration requires execution evidence, not opinions or citations")
        if assessment["gate_eligible"] and (not assessment["verified"] or assessment["status"] not in {"pass", "fail"}):
            raise ValueError("Unknown or unverified calibration evidence cannot be gate eligible")
        indexed[identifier] = assessment
    relevant = [indexed[identifier] for identifier in ("coding_contract", "coding_probe")]
    if any(_hard(assessment) and assessment["status"] == "fail" for assessment in relevant):
        return "detected"
    if all(_hard(assessment) and assessment["status"] == "pass" for assessment in relevant):
        return "not_detected"
    return "unknown"


class CalibrationRegistry:
    """Immutable one-use shards, reserved before any candidate judgments.

    A shard is never reassigned after rejection. Identical resume is permitted;
    overlapping artifacts or project clusters cannot hide behind a new shard
    ID. Raw manifests and rows stay in local private calibration storage, and
    only aggregate decisions are returned to the caller.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    @contextmanager
    def _lock(self):
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / ".reservation.lock"
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ValueError("Calibration registry is busy; do not run concurrent owners") from None
        try:
            os.close(descriptor)
            yield
        finally:
            path.unlink()

    def _path(self, shard_id: str, name: str) -> Path:
        if not isinstance(shard_id, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,120}", shard_id) is None:
            raise ValueError("Shard ID must be a safe bounded identifier")
        return self.root / shard_id / name

    def reserve(self, shard_id: str, manifest: Mapping, development_clusters: Sequence[str],
                development_artifacts: Sequence[str], final_clusters: Sequence[str], proposal_hash: str,
                round_index: int, *, final_artifacts: Sequence[str] = ()) -> dict:
        artifacts = _artifacts(manifest)
        repeats = _repeats(manifest)
        if not _hash(manifest.get("current_rubric_hash")):
            raise ValueError("Calibration manifest must predeclare current_rubric_hash")
        if any(not _text(artifact.get("task_id")) for artifact in artifacts):
            raise ValueError("Reserved calibration artifacts require their original task_id")
        if not _hash(proposal_hash) or type(round_index) is not int or round_index < 0:
            raise ValueError("Reservation needs a proposal hash and nonnegative round")
        clusters, hashes = {r["cluster_id"] for r in artifacts}, {r["artifact_hash"] for r in artifacts}
        if clusters & (set(development_clusters) | set(final_clusters)):
            raise ValueError("Calibration project clusters overlap development or final audit")
        if hashes & (set(development_artifacts) | set(final_artifacts)):
            raise ValueError("Calibration artifact hashes overlap development or final audit")
        reservation = _seal({"version": VERSION, "shard_id": shard_id, "manifest_hash": digest(manifest),
                             "proposal_hash": proposal_hash, "round_index": round_index,
                             "current_rubric_hash": manifest["current_rubric_hash"],
                             "repeats": repeats,
                             "clusters": sorted(clusters), "artifact_hashes": sorted(hashes),
                             "excluded_development_clusters": sorted(set(development_clusters)),
                             "excluded_development_artifacts": sorted(set(development_artifacts)),
                             "excluded_final_clusters": sorted(set(final_clusters)),
                             "excluded_final_artifacts": sorted(set(final_artifacts)),
                             "activation_earliest_round": round_index + 1,
                             "labels_are_optimizer_inaccessible": True}, "reservation_hash")
        target = self._path(shard_id, "reservation.json")
        with self._lock():
            for previous in self.root.glob("*/reservation.json"):
                if previous == target:
                    continue
                row = _verify(json.loads(previous.read_text()), "reservation_hash")
                if clusters & set(row["clusters"]) or hashes & set(row["artifact_hashes"]):
                    raise ValueError("A calibration project/artifact shard was already reserved")
            write_immutable_json(target, reservation)
            write_immutable_json(self._path(shard_id, "private_manifest.json"), manifest)
        return reservation

    def consume(self, shard_id: str, old_rows: Sequence[Mapping], new_rows: Sequence[Mapping], *,
                proposal_hash: str, round_index: int) -> dict:
        path = self._path(shard_id, "reservation.json")
        if not path.exists():
            raise ValueError("Calibration shard must be reserved BEFORE judgments")
        reservation = _verify(json.loads(path.read_text()), "reservation_hash")
        if reservation["proposal_hash"] != proposal_hash or reservation["round_index"] != round_index:
            raise ValueError("Calibration proposal/round differs from pre-judgment reservation")
        manifest = json.loads(self._path(shard_id, "private_manifest.json").read_text())
        if digest(manifest) != reservation["manifest_hash"]:
            raise ValueError("Calibration manifest integrity mismatch")
        artifacts = {r["artifact_id"]: r for r in _artifacts(manifest)}
        expected_positions = {(identifier, repeat) for identifier in artifacts for repeat in reservation["repeats"]}
        for rows, rubric_hash in ((old_rows, reservation["current_rubric_hash"]), (new_rows, proposal_hash)):
            indexed = _calibration_rows(rows)
            if {r["artifact_id"] for r in indexed.values()} != set(artifacts):
                raise ValueError("Calibration may not drop reserved artifacts after judging")
            if set(indexed) != expected_positions:
                raise ValueError("Calibration observations must match all predeclared repeat positions")
            for row in indexed.values():
                if any(row.get(field) != artifacts[row["artifact_id"]][field]
                       for field in ("artifact_hash", "cluster_id", "truth", "task_id")):
                    raise ValueError("Judged artifact differs from reserved identity/oracle truth")
                derived = _promotion_assessments(row, artifacts[row["artifact_id"]], rubric_hash)
                if row["outcome"] != derived:
                    raise ValueError("Calibration outcome disagrees with its sealed execution assessments")
        decision = promote(old_rows, new_rows)
        result = _seal({"reservation_hash": digest(reservation), "proposal_hash": proposal_hash,
                        "shard_id": shard_id, "round_index": round_index, "decision": decision,
                        "active_from_round": round_index + 1 if decision["promote"] else None,
                        "raw_labels_returned": False,
                        "outcomes_recomputed_from_sealed_assessments": True}, "consumption_hash")
        with self._lock():
            write_immutable_json(self._path(shard_id, "private_judgments.json"),
                                 {"old": old_rows, "new": new_rows})
            write_immutable_json(self._path(shard_id, "consumed.json"), result)
        return result


def sample_reviews(rows: Sequence[Mapping], *, seed: int = 0, random_per_domain: int = 2,
                   disputed_per_domain: int = 2) -> dict:
    """Deterministic, domain-balanced blind-review strata; not equal estimands."""
    if any(type(v) is not int or v < 0 for v in (seed, random_per_domain, disputed_per_domain)):
        raise ValueError("Review seed and sample sizes must be nonnegative integers")
    indexed = {}
    for incoming in rows:
        row = deepcopy(dict(incoming))
        if not _text(row.get("feedback_id")) or not _text(row.get("domain")):
            raise ValueError("Review sources require feedback_id and domain")
        if row["feedback_id"] in indexed:
            raise ValueError("Duplicate review feedback ID")
        indexed[row["feedback_id"]] = row
    rng = random.Random(seed)
    random_rows, disputed_rows = [], []
    for domain in sorted({r["domain"] for r in indexed.values()}):
        group = sorted((r for r in indexed.values() if r["domain"] == domain), key=lambda r: r["feedback_id"])
        chosen = rng.sample(group, min(random_per_domain, len(group)))
        random_rows.extend(chosen)
        chosen_ids = {r["feedback_id"] for r in chosen}
        disputed = [r for r in group if r["feedback_id"] not in chosen_ids
                    and (r.get("disputed") is True or bool(r.get("disputes")))]
        disputed_rows.extend(rng.sample(disputed, min(disputed_per_domain, len(disputed))))
    return _seal({"random": random_rows, "disputed": disputed_rows, "seed": seed,
                  "random_per_domain": random_per_domain, "disputed_per_domain": disputed_per_domain,
                  "population_hash": digest(sorted(indexed.values(), key=lambda r: r["feedback_id"])),
                  "interpretation": "report_random_and_disputed_strata_separately"}, "sampling_hash")


_BLIND_FIELDS = frozenset({"strategy", "policy", "arm", "candidate", "candidate_id", "candidate_hash", "model",
                           "model_id", "returned_model", "validator_name", "skill", "skill_hash", "feedback_id",
                           "strategy_id", "strategy_name", "policy_id", "policy_name", "arm_id", "arm_name",
                           "condition", "condition_id", "condition_name", "baseline", "current",
                           "comparisons", "disputed", "disputes"})


def _blind(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _blind(item) for key, item in value.items() if key.casefold() not in _BLIND_FIELDS
                and not (key.casefold() == "reference" and isinstance(item, str)
                         and item.casefold() in {"baseline", "current", "candidate", "no-skill", "no_skill"})}
    if isinstance(value, (list, tuple)):
        return [_blind(item) for item in value]
    return value


def export_review_queue(path: Path, rows: Sequence[Mapping], *, seed: int = 0, random_per_domain: int = 2,
                        disputed_per_domain: int = 2) -> dict:
    sample = sample_reviews(rows, seed=seed, random_per_domain=random_per_domain,
                            disputed_per_domain=disputed_per_domain)
    selected = [(stratum, row) for stratum in ("random", "disputed") for row in sample[stratum]]
    random.Random(seed + 1).shuffle(selected)
    entries, private = [], []
    for index, (stratum, row) in enumerate(selected):
        review_id = f"review-{index + 1:04d}"
        allowed = {key: row[key] for key in ("artifact", "contract", "facts", "repair_guidance", "hypotheses") if key in row}
        entries.append({"review_id": review_id, "domain": row["domain"], "evidence": _blind(allowed)})
        private.append({"review_id": review_id, "feedback_id": row["feedback_id"], "stratum": stratum,
                        "source_hash": digest(row)})
    queue = _seal({"version": VERSION, "sampling_hash": sample["sampling_hash"], "entries": entries,
                   "review_performed": False, "blinding": "structured_labels_removed_free_text_requires_audit"}, "queue_hash")
    path = Path(path)
    write_immutable_json(path.with_suffix(path.suffix + ".private.json"),
                         {"queue_hash": queue["queue_hash"], "sources": private})
    write_immutable_json(path, queue)
    return queue


def import_reviews(path: Path, queue: Mapping, reviews: Sequence[Mapping], *, reviewer_id: str) -> dict:
    """Validate externally supplied human attestations; do not invent reviews."""
    data = _verify(queue, "queue_hash")
    if not _text(reviewer_id) or not isinstance(reviews, (list, tuple)) or not reviews:
        raise ValueError("A named reviewer and nonempty externally supplied reviews are required")
    ids = {entry["review_id"] for entry in data["entries"]}
    seen, accepted = set(), []
    for incoming in reviews:
        row = deepcopy(dict(incoming))
        if row.get("queue_hash") != queue["queue_hash"]:
            raise ValueError("Human review must explicitly bind the exact exported queue_hash")
        if row.get("review_id") not in ids or row["review_id"] in seen:
            raise ValueError("Human review ID is unknown or duplicated")
        if any(type(row.get(name)) is not bool for name in ("factually_supported", "applicable", "actionable")):
            raise ValueError("Human review requires explicit factual/applicability/actionability judgments")
        if row.get("citation_supported") is not None and type(row["citation_supported"]) is not bool:
            raise ValueError("Citation support must be boolean or unresolved null")
        if row.get("verdict") not in {"accept", "dispute", "insufficient_evidence"} or not _text(row.get("rationale")):
            raise ValueError("Human review requires verdict and rationale")
        seen.add(row["review_id"])
        accepted.append(row)
    result = _seal({"queue_hash": queue["queue_hash"], "reviewer_id": reviewer_id, "reviews": accepted,
                    "trust": "external_human_attestation_unverified_by_software", "gate_eligible": False,
                    "unreviewed_count": len(ids - seen)}, "human_receipt_hash")
    write_immutable_json(Path(path), result)
    return result
