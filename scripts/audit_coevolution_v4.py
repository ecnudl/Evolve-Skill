"""Independent, read-only audit of a frozen or still-running V4 experiment.

No experiment modules are imported, no candidate is executed, and no network or
API operation is performed. Existing scores are described, never recomputed or
fed back. Actual request files, not logical policy aliases, determine API cost.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

VERSION = "coevolution-v4-independent-readonly-audit-v1"
HASH = re.compile(r"[0-9a-f]{64}")
POLICIES = ("fixed", "feedback", "research")
CATEGORIES = ("transport_unavailable", "execution_unknown", "delivery_failure", "behavior_failure", "hard_pass")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _json(raw):
    def pairs(items):
        value = {}
        for key, child in items:
            if key in value:
                raise ValueError("Duplicate audit input JSON key")
            value[key] = child
        return value
    def nonfinite(_):
        raise ValueError("Nonfinite audit input JSON")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


class Reader:
    def __init__(self, root):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError("Experiment directory is missing")
        self.hashes = {}
        self.cache = {}
        self.listings = {}
        self.existence = {}

    def _path(self, relative):
        relative = str(relative)
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Audit path must stay inside the experiment")
        allowed = relative in {"protocol.json", "results.json", "final_frozen.json", "final_rows.json",
                               "final_alias_plan.json", "api/budget_protocol.json"}
        allowed |= bool(re.fullmatch(r"decisions/r[012]\.json", relative))
        allowed |= bool(re.fullmatch(r"targets/[0-9a-f]{64}\.json", relative))
        allowed |= bool(re.fullmatch(r"claims/[0-9a-f]{64}\.json", relative))
        allowed |= bool(re.fullmatch(r"api/(?:calls|budget_reservations)/[0-9a-f]{64}\.json", relative))
        allowed |= bool(re.fullmatch(r"validator_updates/s[01]_(?:feedback|research)_r[01]\.json", relative))
        allowed |= bool(re.fullmatch(
            r"research/s[01]_(?:feedback|research)_r[01]/validator_evolution/[0-9a-f]{64}/"
            r"(?:proposal\.json|research_sources/(?:sources\.json|documents/[0-9a-f]{64}/"
            r"(?:source\.json|source\.html|excerpt\.txt)))", relative))
        if not allowed:
            raise ValueError("Audit input path is not allowlisted")
        path = self.root / relative
        for parent in (path, *path.parents):
            if parent == self.root:
                break
            if parent.is_symlink():
                raise ValueError("Symlinked audit inputs are forbidden")
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Audit input escaped the experiment")
        return path

    def bytes(self, relative):
        key = str(relative)
        path = self._path(key)
        if key not in self.cache:
            raw = path.read_bytes()
            self.cache[key] = raw
            self.hashes[key] = hashlib.sha256(raw).hexdigest()
        return self.cache[key]

    def read(self, relative, *, wrapped=True):
        value = _json(self.bytes(relative))
        if wrapped:
            if (not isinstance(value, dict) or set(value) != {"record", "record_hash"}
                    or value["record_hash"] != digest(value["record"])):
                raise ValueError("Wrapped experiment record integrity mismatch")
            return value["record"]
        return value

    def exists(self, relative):
        if str(relative) in self.existence:
            return self.existence[str(relative)]
        return self._path(relative).is_file()

    def find(self, pattern):
        if pattern in self.listings:
            return list(self.listings[pattern])
        found = sorted(str(path.relative_to(self.root)) for path in self.root.glob(pattern) if path.is_file())
        for relative in found:
            self._path(relative)
        return found

    def capture_progress_listing(self):
        # Discover consumers before their already-persisted dependencies. This
        # prevents a newly published target from referring to a call omitted by
        # an earlier API listing. The snapshot is causal, not a DB transaction.
        for relative in ("results.json", "final_rows.json", "final_alias_plan.json", "final_frozen.json",
                         "api/budget_protocol.json"):
            self.existence[relative] = self._path(relative).is_file()
        for pattern in ("validator_updates/*.json", "decisions/r*.json",
                        "research/*/validator_evolution/*/proposal.json",
                        "research/*/validator_evolution/*/research_sources/sources.json",
                        "targets/*.json", "claims/*.json", "api/budget_reservations/*.json", "api/calls/*.json"):
            self.listings[pattern] = self.find(pattern)

    def verify_unchanged(self):
        for relative, expected in self.hashes.items():
            if hashlib.sha256(self._path(relative).read_bytes()).hexdigest() != expected:
                raise ValueError("Immutable input changed during read-only audit")


def _number(value, label, *, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Invalid nonnegative " + label)
    if integer and type(value) is not int:
        raise ValueError("Expected integer " + label)
    return value


def api_ledger(reader):
    calls = {}
    usage = Counter()
    kinds, status, errors, finishes, requested_models, returned_models = (Counter() for _ in range(6))
    attempts, missing_usage, duration = 0, 0, 0.0
    for relative in reader.find("api/calls/*.json"):
        row = reader.read(relative, wrapped=False)
        identifier = Path(relative).stem
        request = row.get("request")
        if (not isinstance(request, dict) or row.get("request_hash") != identifier
                or digest(request) != identifier or type(row.get("ok")) is not bool):
            raise ValueError("Raw API request identity or result schema mismatch")
        count = _number(row.get("http_attempt_count"), "HTTP attempt count", integer=True)
        if not 1 <= count <= 3 or len(row.get("attempts", [])) != count:
            raise ValueError("API attempt accounting mismatch")
        calls[identifier] = row
        attempts += count
        kinds[request.get("kind", "missing")] += 1
        requested_models[request.get("model", "missing")] += 1
        returned_models[row.get("returned_model") or "not_reported"] += 1
        finishes[str(row.get("finish_reason"))] += 1
        errors[str(row.get("error_type"))] += 1
        for attempt in row["attempts"]:
            status[str(attempt.get("status"))] += 1
        reported = row.get("usage") or {}
        if not isinstance(reported, dict):
            raise ValueError("Invalid API usage object")
        missing_usage += not bool(reported)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            usage[key] += _number(reported.get(key) or 0, key, integer=True)
        duration += _number(row.get("wall_seconds", 0), "logical request duration")
    reservations = set()
    for relative in reader.find("api/budget_reservations/*.json"):
        row = reader.read(relative, wrapped=False)
        if row.get("request_hash") != Path(relative).stem:
            raise ValueError("API reservation identity mismatch")
        reservations.add(row["request_hash"])
    budget = reader.read("api/budget_protocol.json", wrapped=False) if reader.exists("api/budget_protocol.json") else {}
    result = {"cached_logical_calls": len(calls), "successful_calls": sum(r["ok"] for r in calls.values()),
              "terminal_errors": sum(not r["ok"] for r in calls.values()),
              "logical_requests_reserved": len(reservations | calls.keys()),
              "unresolved_reservations": sorted(reservations - calls.keys()),
              "http_attempts_from_cached_records": attempts,
              "by_kind": dict(sorted(kinds.items())), "http_statuses_all_attempts": dict(sorted(status.items())),
              "terminal_error_categories": dict(sorted(errors.items())), "finish_reasons": dict(sorted(finishes.items())),
              "requested_models": dict(sorted(requested_models.items())), "returned_models": dict(sorted(returned_models.items())),
              **{key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
              "missing_usage_calls": missing_usage, "usage_not_invoice": True,
              "summed_request_wall_seconds_not_elapsed_wall_time": duration,
              "max_logical_calls": budget.get("max_logical_calls"),
              "actual_api_files_not_policy_aliases": True,
              "in_progress_file_listing_is_not_transactionally_atomic": True}
    if result["max_logical_calls"] is not None and result["logical_requests_reserved"] > result["max_logical_calls"]:
        raise ValueError("Observed API reservations exceed frozen budget")
    return result, calls


def _classification(evaluation, files_present, transport_ok):
    if not transport_ok:
        return "transport_unavailable"
    if evaluation.get("execution_ok") is not True:
        return "execution_unknown"
    if not files_present:
        return "delivery_failure"
    if evaluation.get("hard") is True:
        return "hard_pass"
    if evaluation.get("hard") is False:
        return "behavior_failure"
    return "execution_unknown"


def _target_counts(rows, calls):
    categories, initial, transitions = Counter(), Counter(), Counter()
    request_ids = set()
    repaired_format, regressed_format, public_repaired, public_regressed = 0, 0, 0, 0
    nonempty_skills, valid_semantic, valid_count = set(), 0, 0
    for row in rows:
        request_ids.update(row["request_hashes"])
        first_call = calls[row["initial_request_hash"]]
        last_call = calls[row["request_hash"]]
        before, after = row["initial_evaluation"], row["evaluation"]
        first_valid, final_valid = before.get("files") is not None, row.get("files") is not None
        first_category = _classification(before, first_valid, first_call["ok"])
        category = _classification(after, final_valid, last_call["ok"])
        initial[first_category] += 1
        categories[category] += 1
        transitions[first_category + "->" + category] += 1
        repaired_format += not first_valid and final_valid
        regressed_format += first_valid and not final_valid
        public_repaired += before.get("public_pass") is False and after.get("public_pass") is True
        public_regressed += before.get("public_pass") is True and after.get("public_pass") is False
        if row.get("skill"):
            nonempty_skills.add(row["skill_hash"])
        if final_valid and after.get("execution_ok") is True:
            valid_count += 1
            valid_semantic += after.get("hard") is True
    n = len(rows)
    return {"unique_solution_jobs": n, "unique_solver_api_calls": len(request_ids),
            "final_categories": {name: categories[name] for name in CATEGORIES},
            "initial_public_only_categories": {name: initial[name] for name in CATEGORIES},
            "initial_public_to_final_all_fixture_transitions_descriptive_only": dict(sorted(transitions.items())),
            "initial_and_final_evaluations_have_different_test_visibility": True,
            "delivery_rescued_by_public_revision": repaired_format, "delivery_regressed_on_revision": regressed_format,
            "public_pass_false_to_true": public_repaired, "public_pass_true_to_false": public_regressed,
            "final_delivery_rate": sum(r.get("files") is not None for r in rows) / n if n else None,
            "hard_pass_fraction_all_jobs": categories["hard_pass"] / n if n else None,
            "conditional_hard_pass_given_delivered_observable": valid_semantic / valid_count if valid_count else None,
            "conditional_rate_is_descriptive_not_a_causal_skill_estimate": True,
            "distinct_nonempty_skill_hashes": sorted(nonempty_skills)}


def targets(reader, calls):
    rows = {}
    for relative in reader.find("targets/*.json"):
        row = reader.read(relative)
        identifier = Path(relative).stem
        job = {key: row.get(key) for key in ("id", "skill", "stream", "stage", "repeat")}
        if row.get("job_hash") != identifier or digest(job) != identifier:
            raise ValueError("Target job identity mismatch")
        if row.get("artifact_hash") != digest(row.get("files")) or row.get("skill_hash") != digest(row.get("skill")):
            raise ValueError("Target artifact or skill hash mismatch")
        request_ids = row.get("request_hashes")
        if (not isinstance(request_ids, list) or len(request_ids) != 2
                or request_ids != [row.get("initial_request_hash"), row.get("request_hash")]
                or any(identifier not in calls for identifier in request_ids)):
            raise ValueError("Target lacks its two actual cached solver calls")
        if row.get("target_ok") is not calls[row["request_hash"]]["ok"]:
            raise ValueError("Target transport status disagrees with raw API cache")
        if row.get("format_ok") is not (row.get("files") is not None):
            raise ValueError("Target delivery status disagrees with artifact")
        rows[identifier] = row
    grouped = defaultdict(list)
    for row in rows.values():
        grouped[row["stage"]].append(row)
    return {"all": _target_counts(list(rows.values()), calls),
            "by_stage": {key: _target_counts(value, calls) for key, value in sorted(grouped.items())}}, rows


def claim_audit(reader, calls):
    """Flag representation-risk receipts without changing any frozen verdict."""
    counts = Counter()
    invalid = Counter()
    risks = []
    request_ids = set()
    for relative in reader.find("claims/*.json"):
        row = reader.read(relative)
        if row.get("key") != Path(relative).stem:
            raise ValueError("Claim record identity mismatch")
        request_hash = row.get("request_hash")
        if request_hash is not None:
            if request_hash not in calls:
                raise ValueError("Claim lacks actual cached API request")
            request_ids.add(request_hash)
        parsed = row.get("parsed", {})
        counts["claim_records"] += 1
        counts["schema_valid"] += parsed.get("schema_valid") is True
        counts["schema_invalid"] += parsed.get("schema_valid") is not True
        counts["no_usable_claims"] += not bool(parsed.get("claims"))
        for rejected in parsed.get("invalid_claims", []):
            invalid[rejected.get("reason", "missing_reason")] += 1
        for index, receipt in enumerate(row.get("receipts", [])):
            payload = {key: value for key, value in receipt.items() if key != "receipt_hash"}
            if receipt.get("receipt_hash") != digest(payload):
                raise ValueError("Probe receipt integrity mismatch")
            counts["receipts"] += 1
            counts["verified_mismatches"] += receipt.get("matched") is False
            counts["execution_unknown_receipts"] += receipt.get("matched") is None
            for arm in ("reference", "actual"):
                observation = receipt.get(arm, {})
                message = observation.get("message", "")
                if isinstance(message, str) and re.search(r"JSON compliant|nonfinite|serializ", message, re.I):
                    risks.append({"claim_key": row["key"], "receipt_index": index, "arm": arm,
                                  "receipt_hash": receipt["receipt_hash"], "exception": observation.get("exception"),
                                  "message": message[:250], "recorded_matched": receipt.get("matched"),
                                  "classification": "oracle_representation_risk_requires_human_review",
                                  "automatic_bug_verdict": False})
    return {**dict(counts), "unique_probe_api_calls": len(request_ids),
            "invalid_claim_reasons": dict(sorted(invalid.items())),
            "oracle_representation_risks": risks,
            "risk_flags_do_not_change_frozen_scores_or_gate_decisions": True}


def _pair_stats(pairs, reference_arm):
    complete, case_gain, hard_gain, wins, losses, ties = 0, 0, 0, 0, 0, 0
    reference_passes = candidate_passes = reference_hard = candidate_hard = 0
    deltas, preserved_losses, fixture_losses, probe_losses = [], [], [], []
    unknown_probe_pairs = 0
    seen = set()
    for pair in pairs:
        key = (pair["id"], pair["repeat"])
        if key in seen:
            raise ValueError("Duplicate decision task/repeat pair")
        seen.add(key)
        left, right = pair[reference_arm], pair["candidate"]
        identity = {"id": pair["id"], "repeat": pair["repeat"], "reference": reference_arm}
        for field, destination in (("case_results", fixture_losses), ("preserved", preserved_losses)):
            lm, rm = left.get(field, {}), right.get(field, {})
            for label in sorted(set(lm) & set(rm)):
                if lm[label] is True and rm[label] is False:
                    destination.append({**identity, "case": label})
        probes = pair.get("probe_results", {})
        lp, rp = probes.get(reference_arm, {}), probes.get("candidate", {})
        for label in sorted(set(lp) & set(rp)):
            if lp[label] is True and rp[label] is False:
                probe_losses.append({**identity, "probe": label})
        unknown_probe_pairs += bool(pair.get("search_unknown")) or any(
            value is None for value in list(lp.values()) + list(rp.values()))
        if not (left.get("available") is True and right.get("available") is True):
            continue
        for value in (left, right):
            case_map = value["case_results"]
            if (any(type(passed) is not bool for passed in case_map.values())
                    or value["case_total"] != len(case_map) or value["case_passes"] != sum(case_map.values())
                    or value["case_total"] <= 0 or type(value.get("hard")) is not bool):
                raise ValueError("Malformed observable decision case evidence")
        if set(left["case_results"]) != set(right["case_results"]):
            raise ValueError("Decision pair fixture identities differ")
        complete += 1
        reference_passes += left["case_passes"]
        candidate_passes += right["case_passes"]
        reference_hard += left["hard"]
        candidate_hard += right["hard"]
        delta = right["case_passes"] / right["case_total"] - left["case_passes"] / left["case_total"]
        deltas.append(delta)
        case_gain += right["case_passes"] - left["case_passes"]
        hard_gain += int(right["hard"]) - int(left["hard"])
        wins += right["hard"] and not left["hard"]
        losses += left["hard"] and not right["hard"]
        ties += left["hard"] == right["hard"]
    return {"pairs": len(pairs), "complete_pairs": complete, "unknown_pairs": len(pairs) - complete,
            "reference_case_passes": reference_passes, "candidate_case_passes": candidate_passes,
            "case_pass_gain": case_gain, "mean_case_fraction_gain": sum(deltas) / len(deltas) if deltas else None,
            "reference_hard_passes": reference_hard, "candidate_hard_passes": candidate_hard,
            "hard_gain": hard_gain, "hard_wins": wins, "hard_losses": losses, "hard_ties": ties,
            "known_fixture_losses": fixture_losses, "known_preserved_losses": preserved_losses,
            "known_shared_probe_losses": probe_losses, "unknown_probe_pairs": unknown_probe_pairs,
            "repeats_are_not_independent_task_families": True}


def decisions(reader):
    rows = []
    for relative in reader.find("decisions/r*.json"):
        record = reader.read(relative)
        for key, decision in sorted(record.items()):
            policy, stream, round_index = decision["policy"], decision["stream"], decision["round"]
            if key != f"s{stream}_{policy}" or Path(relative).stem != f"r{round_index}" or policy not in POLICIES:
                raise ValueError("Decision identity does not match its sealed path")
            candidate = decision["candidate"]
            if any(decision[gate].get("candidate_hash") != digest(candidate) for gate in ("local", "scope")):
                raise ValueError("Gate candidate provenance mismatch")
            groups = {}
            for group, reference in (("source", "working"), ("replay", "working"), ("scope", "approved")):
                pairs = decision["pairs"][group]
                groups[group] = {"vs_base": _pair_stats(pairs, "base"),
                                 "vs_" + reference: _pair_stats(pairs, reference)}
            rows.append({"stream": stream, "policy": policy, "round": round_index,
                         "candidate_valid": candidate.get("valid") is True,
                         "candidate_content_hash": digest(candidate.get("content", "")),
                         "proposal_request_hash": candidate.get("request_hash"),
                         "local": {key: decision["local"].get(key) for key in ("passed", "action", "reasons")},
                         "scope": {key: decision["scope"].get(key) for key in ("passed", "action", "reasons")},
                         "pairs": groups})
    return {"logical_decisions": len(rows), "unique_proposal_calls": len({r["proposal_request_hash"] for r in rows
                                                                          if r["proposal_request_hash"]}),
            "local_commits": sum(row["local"]["passed"] is True for row in rows),
            "scope_commits": sum(row["scope"]["passed"] is True for row in rows), "rows": rows}


def _calibration_counts(rows):
    result = {"rows": len(rows), "good": 0, "bad": 0, "detected_bad": 0,
              "false_rejections": 0, "unknown": 0, "usable_missed_bad": 0,
              "oracle_pass_unproven": 0, "detected_on_unproven_natural": 0}
    for row in rows:
        truth, outcome = row.get("truth"), row.get("outcome")
        if truth not in {"good", "bad", "oracle_pass_unproven"} or outcome not in {"detected", "not_detected", "unknown"}:
            raise ValueError("Malformed calibration truth or outcome")
        result[truth] += 1
        result["detected_bad"] += truth == "bad" and outcome == "detected"
        result["false_rejections"] += truth == "good" and outcome == "detected"
        result["unknown"] += outcome == "unknown"
        result["usable_missed_bad"] += truth == "bad" and outcome == "not_detected"
        result["detected_on_unproven_natural"] += truth == "oracle_pass_unproven" and outcome == "detected"
    result["unique_artifacts"] = len({row["artifact_hash"] for row in rows})
    result["unique_claim_keys"] = len({row["claim_key"] for row in rows if row.get("claim_key")})
    return result


def calibration(record):
    if record is None:
        return None
    old, new = record["old"], record["new"]
    selection = {name: [row for row in rows if row["truth"] != "oracle_pass_unproven"]
                 for name, rows in (("old", old), ("new", new))}
    diagnostic = {name: [row for row in rows if row["truth"] == "oracle_pass_unproven"]
                  for name, rows in (("old", old), ("new", new))}
    if "selection_rows" in record and record["selection_rows"] != selection:
        raise ValueError("Calibration selection rows differ from independently filtered oracle labels")
    if "diagnostic_only" in record and record["diagnostic_only"] != diagnostic:
        raise ValueError("Calibration diagnostic rows differ from independently filtered oracle labels")
    indexed = []
    for rows in (old, new):
        ids = [row["artifact_id"] for row in rows]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate calibration observation")
        indexed.append(dict(zip(ids, rows)))
    if indexed[0].keys() != indexed[1].keys():
        raise ValueError("Calibration arms do not use the same observations")
    transitions = Counter()
    new_false, new_unknown, lost = [], [], []
    for identity in indexed[0]:
        left, right = indexed[0][identity], indexed[1][identity]
        if any(left.get(key) != right.get(key) for key in ("artifact_hash", "truth", "case_kind", "repeat", "project")):
            raise ValueError("Paired calibration artifacts or labels differ")
        transitions[f"{left['truth']}:{left['outcome']}->{right['outcome']}"] += 1
        if left["truth"] == "oracle_pass_unproven":
            continue
        if right["truth"] == "good" and right["outcome"] == "detected" and left["outcome"] != "detected":
            new_false.append(identity)
        if right["outcome"] == "unknown" and left["outcome"] != "unknown":
            new_unknown.append(identity)
        if left["truth"] == "bad" and left["outcome"] == "detected" and right["outcome"] != "detected":
            lost.append(identity)
    derived = {}
    for name, rows in (("old", old), ("new", new)):
        derived[name] = {"all": _calibration_counts(rows),
                         "selection": _calibration_counts(selection[name]),
                         "diagnostic_unproven": _calibration_counts(diagnostic[name]),
                         "natural": _calibration_counts([r for r in rows if r["case_kind"] == "natural"]),
                         "controls": _calibration_counts([r for r in rows if r["case_kind"] != "natural"])}
        reported = record.get("decision", {}).get(name, {})
        for key in ("rows", "good", "bad", "detected_bad", "false_rejections", "unknown", "usable_missed_bad"):
            if key in reported and reported[key] != derived[name]["selection"][key]:
                raise ValueError("Reported calibration count disagrees with raw paired rows")
    before, after = derived["old"]["selection"], derived["new"]["selection"]
    criteria = record.get("decision", {}).get("criteria", {})
    def unique(rows, truth):
        return len({r["artifact_hash"] for r in rows if r["truth"] == truth})
    coverage = (before["good"] >= criteria.get("min_good", 4) and before["bad"] >= criteria.get("min_bad", 4)
                and unique(old, "good") >= criteria.get("min_unique_good", 2)
                and unique(old, "bad") >= criteria.get("min_unique_bad", 2))
    improved = (after["detected_bad"] > before["detected_bad"] or
                (after["unknown"] < before["unknown"] and after["detected_bad"] >= before["detected_bad"]))
    recomputed = coverage and improved and not (new_false or new_unknown or lost)
    if record.get("decision", {}).get("promote") is not bool(recomputed):
        raise ValueError("Reported promotion does not match independently recomputed criteria")
    return {**derived, "transitions": dict(sorted(transitions.items())),
            "new_paired_false_rejections": new_false, "new_paired_unknowns": new_unknown,
            "lost_paired_detections": lost, "coverage_satisfied": coverage,
            "independently_recomputed_promote": bool(recomputed),
            "reported_reasons": record.get("decision", {}).get("reasons", []),
            "natural_oracle_pass_does_not_establish_correctness_or_false_rejection_truth": True,
            "calibration_is_selection_not_independent_final_evidence": True}


def source_snapshots(reader):
    snapshots = {}
    for relative in reader.find("research/*/validator_evolution/*/research_sources/sources.json"):
        rows = reader.read(relative, wrapped=False)
        if not isinstance(rows, list):
            raise ValueError("Research sources must be a list")
        for row in rows:
            url, identifier = row.get("requested_url"), row.get("snapshot_id")
            if not isinstance(url, str) or not isinstance(identifier, str) or not HASH.fullmatch(identifier):
                raise ValueError("Research source identity is invalid")
            directory = Path(relative).parent / "documents" / identifier
            persisted = reader.read(directory / "source.json", wrapped=False)
            if persisted != row:
                raise ValueError("Research source list and individual snapshot differ")
            if row.get("ok") is True:
                excerpt = reader.bytes(directory / "excerpt.txt")
                html = reader.bytes(directory / "source.html")
                if (hashlib.sha256(excerpt).hexdigest() != row.get("text_sha256")
                        or hashlib.sha256(html).hexdigest() != row.get("raw_html_sha256")
                        or excerpt.decode("utf-8") != row.get("text")):
                    raise ValueError("Research source bytes failed provenance verification")
            snapshots[(url, row.get("text_sha256"), identifier)] = row
    return snapshots


def _research(proposal, snapshots):
    record = proposal.get("research", {})
    listed = record.get("source_snapshots", [])
    available = {}
    for source in listed:
        identity = source.get("requested_url"), source.get("text_sha256"), source.get("snapshot_id")
        if identity not in snapshots:
            raise ValueError("Evolution cites a missing research source snapshot")
        actual = snapshots[identity]
        if any(source.get(key) != actual.get(key) for key in ("ok", "raw_html_sha256", "text_sha256")):
            raise ValueError("Evolution source summary disagrees with actual bytes")
        if actual.get("ok") is True:
            available[actual["requested_url"]] = actual
    findings = (record.get("findings") or {}).get("findings", [])
    quotes, valid_quotes = 0, 0
    for finding in findings:
        if record.get("method") != "bounded_official_document_investigation":
            continue
        urls, cited = set(finding.get("evidenceurls", [])), set()
        if not urls or not urls <= available.keys():
            raise ValueError("Research finding cites an unavailable source")
        for evidence in finding.get("evidencequotes", []):
            quotes += 1
            url, quote = evidence.get("url"), evidence.get("quote")
            if (url not in urls or not isinstance(quote, str) or not 20 <= len(quote) <= 500
                    or quote not in available[url]["text"]):
                raise ValueError("Research quote is not an exact bounded source excerpt")
            valid_quotes += 1
            cited.add(url)
        if urls != cited:
            raise ValueError("Research finding lacks a quote for every cited source")
    if record.get("sources_available", 0) != len(available):
        raise ValueError("Research available-source accounting mismatch")
    return {key: record.get(key) for key in ("requested", "executed", "trigger", "method", "fetch_status",
                                            "sources_requested", "sources_available")} | {
        "findings_count": len(findings), "exact_quotes": quotes, "verified_exact_quotes": valid_quotes,
        "sources": [{"url": row["requested_url"], "ok": row.get("ok"), "text_sha256": row.get("text_sha256"),
                     "error_type": row.get("error_type")} for row in listed],
        "source_provenance_is_not_entailment_or_validator_effectiveness": True,
        "autonomous_open_web_deepresearch": False}


def validator_updates(reader, calls):
    snapshots = source_snapshots(reader)
    proposals = {}
    for relative in reader.find("research/*/validator_evolution/*/proposal.json"):
        row = reader.read(relative, wrapped=False)
        payload = {k: value for k, value in row.items() if k != "record_hash"}
        if row.get("record_hash") != digest(payload):
            raise ValueError("Evolution proposal checksum mismatch")
        identity = row.get("identity", {})
        if Path(relative).parent.name != digest(identity):
            raise ValueError("Evolution proposal identity path mismatch")
        proposals[identity["key"]] = row
    completed = {}
    for relative in reader.find("validator_updates/*.json"):
        completed[Path(relative).stem] = reader.read(relative)
    rows = []
    for key in sorted(proposals.keys() | completed.keys()):
        update = completed.get(key)
        proposal = proposals.get(key, (update or {}).get("proposal"))
        if proposal is None:
            raise ValueError("Validator update lacks a proposal")
        if update is not None and update["proposal"] != proposal:
            raise ValueError("Completed update differs from immutable evolution proposal")
        stages = []
        for stage in proposal["stages"]:
            request_hash = stage["request_hash"]
            if request_hash not in calls:
                raise ValueError("Validator stage lacks its actual API call")
            actual = calls[request_hash]
            if stage["transport_ok"] is not actual["ok"]:
                raise ValueError("Validator stage transport disagrees with API cache")
            stages.append({k: stage.get(k) for k in ("stage", "request_hash", "transport_ok", "schema_valid", "error", "max_tokens")})
        if proposal["calls_used"] != len(stages) or len(stages) > 3:
            raise ValueError("Validator proposal stage budget mismatch")
        independent = calibration(update.get("calibration")) if update else None
        if update and bool(update["promoted"]) != bool(independent and independent["independently_recomputed_promote"]):
            raise ValueError("Validator activation disagrees with calibration")
        rows.append({"identity": key, "status": proposal["status"], "update_complete": update is not None,
                     "stages": stages, "calls_used": len(stages), "research": _research(proposal, snapshots),
                     "promoted": update.get("promoted") if update else None,
                     "effective_from_round": update.get("effective_from_round") if update else None,
                     "calibration": independent})
    return {"proposal_attempts": len(rows), "completed_updates": sum(r["update_complete"] for r in rows),
            "promotions": sum(r["promoted"] is True for r in rows), "rows": rows,
            "verified_source_snapshots": len(snapshots),
            "successful_snapshot_count": sum(row.get("ok") is True for row in snapshots.values())}


def final_aliases(reader, targets_by_hash, calls):
    if not reader.exists("final_alias_plan.json"):
        return {"status": "not_started", "logical_alias_rows": 0, "arms": {}}
    aliases = reader.read("final_alias_plan.json")
    grouped = defaultdict(list)
    missing = []
    seen = set()
    for alias in aliases:
        identity = alias["arm"], alias["job_hash"]
        if identity in seen:
            raise ValueError("Duplicate final logical alias")
        seen.add(identity)
        if alias["job_hash"] not in targets_by_hash:
            missing.append(alias["job_hash"])
        else:
            row = targets_by_hash[alias["job_hash"]]
            if row["stage"] != "final":
                raise ValueError("Final alias references a nonfinal target")
            grouped[alias["arm"]].append(row)
    if reader.exists("final_rows.json"):
        derived = reader.read("final_rows.json")
        if {(r["arm"], r["job_hash"]) for r in derived} != seen or len(derived) != len(aliases):
            raise ValueError("Final derived rows do not match the frozen alias plan")
        for row in derived:
            actual = targets_by_hash.get(row["job_hash"])
            if actual is None:
                raise ValueError("Final derived row lacks actual target")
            for key in ("id", "stream", "repeat", "artifact_hash", "skill_hash", "format_ok", "target_ok"):
                if row[key] != actual[key]:
                    raise ValueError("Final alias differs from actual target")
            if row["hard"] is not actual["evaluation"]["hard"]:
                raise ValueError("Final derived hard score differs from actual target")
    return {"status": "complete" if not missing and reader.exists("final_rows.json") else "in_progress",
            "logical_alias_rows": len(aliases), "unique_target_jobs_planned": len({r["job_hash"] for r in aliases}),
            "missing_unique_target_jobs": len(set(missing)),
            "arms": {key: _target_counts(value, calls) for key, value in sorted(grouped.items())},
            "identical_empty_skills_share_actual_requests": True,
            "alias_equality_is_not_statistical_equivalence_or_safe_generalization": True}


def audit(run):
    reader = Reader(run)
    reader.capture_progress_listing()
    protocol = reader.read("protocol.json")
    if protocol.get("version") != "coevolution-v4-engineering-v1":
        raise ValueError("This auditor only supports the frozen V4 engineering schema")
    ledger, calls = api_ledger(reader)
    target_summary, target_rows = targets(reader, calls)
    claims = claim_audit(reader, calls)
    decision_summary = decisions(reader)
    updates = validator_updates(reader, calls)
    aliases = final_aliases(reader, target_rows, calls)
    completed = reader.read("results.json") if reader.exists("results.json") else None
    if reader.exists("final_frozen.json"):
        freeze = reader.read("final_frozen.json")
        if freeze.get("protocol_hash") != digest(protocol) or freeze.get("freeze_before_final") is not True:
            raise ValueError("Final freeze does not bind the frozen protocol")
    if completed:
        for key in ("cached_logical_calls", "successful_calls", "terminal_errors", "logical_requests_reserved",
                    "http_attempts_from_cached_records", "prompt_tokens", "completion_tokens", "total_tokens", "by_kind"):
            if completed["ledger"].get(key) != ledger[key]:
                raise ValueError("Published completion ledger differs from actual API cache")
        for name, actual in (("local_commits", decision_summary["local_commits"]),
                             ("scope_commits", decision_summary["scope_commits"]),
                             ("validator_promotions", updates["promotions"])):
            if completed.get(name) != actual:
                raise ValueError("Published completion count differs from independent audit")
        if aliases["status"] != "complete" or not reader.exists("final_frozen.json"):
            raise ValueError("Completion was published without a complete frozen final matrix")
    result = {"version": VERSION, "status": "complete" if completed else "in_progress_snapshot",
              "source_run": str(reader.root), "protocol_hash": digest(protocol), "read_only": True,
              "api_calls_made_by_audit": 0, "candidate_executions_by_audit": 0,
              "not_canonical_public_benchmark": protocol.get("not_unseen_or_canonical_benchmark"),
              "cross_domain_validated": protocol.get("cross_domain_validated"),
              "api_ledger": ledger, "targets": target_summary, "development": decision_summary,
              "claims": claims,
              "validator_evolution": updates, "final": aliases,
              "limitations": ["Describes finite development selection and frozen engineering fixtures, not unseen benchmark or multi-domain evidence.",
                              "Paired repeats are observations of shared tasks; no significance or safety certificate is inferred.",
                              "Initial public-only and final all-fixture scores have different denominators and are not a causal repair comparison.",
                              "Exact source quotations establish provenance, not entailment or validation effectiveness.",
                              "During a live run, immutable file listings form a nontransactional progress snapshot."]}
    reader.verify_unchanged()
    result["verified_input_hashes"] = dict(sorted(reader.hashes.items()))
    result["audit_hash"] = digest(result)
    return result


def write_report(report, output, source):
    destination, root = Path(output).resolve(), Path(source).resolve()
    if destination == root or destination.is_relative_to(root):
        raise ValueError("Audit output must be outside the frozen run")
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    if destination.exists():
        if destination.is_symlink() or destination.read_bytes() != data:
            raise ValueError("Immutable audit output already exists with different contents")
        return destination
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".v4-audit-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, help="Optional immutable JSON file outside the source run")
    args = parser.parse_args(argv)
    report = audit(args.run)
    if args.output:
        destination = write_report(report, args.output, args.run)
        print(json.dumps({"audit": str(destination), "status": report["status"],
                          "actual_api_calls": report["api_ledger"]["cached_logical_calls"]}, ensure_ascii=False))
    else:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
