"""Post-completion delivery/behavior accounting, never rescoring a V3 artifact.

Reads only sealed experiment metadata and already-scored derived target rows.
No API cache, credentials, model calls, candidate execution or new inference.
The original hard labels, denominators and arm statistics remain unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

VERSION = "coevolution-v3-delivery-layer-audit-v1"
PROTOCOL_VERSION = "multi-file-local-deployment-decoupling-v3"
POLICIES = ("coupled_evolving", "decoupled_fixed", "decoupled_evolving")
ARMS = ("noskill", *POLICIES, *("working_" + policy for policy in POLICIES))
CATEGORIES = (
    "transport_unavailable",
    "execution_infrastructure_unknown",
    "delivery_failure",
    "delivered_behavior_failure",
    "hard_pass",
)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class Reader:
    """Explicit path allowlist; a completion barrier precedes all other reads."""

    def __init__(self, run):
        self.root = Path(run).resolve()
        self.hashes = {}
        self.complete = False
        self.cache = {}

    def read(self, relative, *, record=False):
        allowed = relative in {
            "results.json",
            "protocol.json",
            "final_frozen.json",
            "final_rows.json",
            "final_alias_plan.json",
        }
        allowed = allowed or re.fullmatch(r"(?:histories|decisions)/r[01]\.json", relative)
        allowed = allowed or re.fullmatch(
            r"states/s[01]_(?:coupled_evolving|decoupled_fixed|decoupled_evolving)_r[01]\.json", relative
        )
        allowed = allowed or re.fullmatch(r"targets/[0-9a-f]{64}\.json", relative)
        if not allowed or (relative != "results.json" and not self.complete):
            raise ValueError("Forbidden read or unmet completion barrier")
        path = self.root / relative
        if any(p.is_symlink() for p in (path, *path.parents) if p != self.root and self.root in p.parents):
            raise ValueError("Symlinked experiment inputs are not permitted")
        if not path.resolve().is_relative_to(self.root):
            raise ValueError("Experiment input escaped source directory")
        if relative not in self.cache:
            payload = path.read_bytes()
            self.hashes[relative] = hashlib.sha256(payload).hexdigest()
            self.cache[relative] = json.loads(payload)
        # JSON roundtrip gives consumers an independent copy, including nested
        # records from the final matrix that will receive logical-role labels.
        value = json.loads(json.dumps(self.cache[relative]))
        if record:
            checksum = value.pop("record_sha256", None)
            if checksum != digest(value):
                raise ValueError("Derived target record hash mismatch")
        return value

    def verify_unchanged(self):
        for relative, expected in self.hashes.items():
            if hashlib.sha256((self.root / relative).read_bytes()).hexdigest() != expected:
                raise ValueError("Source artifacts changed during read-only audit")


def _sealed(component):
    if not isinstance(component, dict):
        raise ValueError("Invalid sealed state component")
    core = dict(component)
    checksum = core.pop("state_hash", None)
    if checksum != digest(core):
        raise ValueError("State component checksum mismatch")


def classify(row):
    """Five descriptive categories; no correction or interpretation of code."""
    for key in ("target_ok", "execution_ok", "format_ok", "skill_active"):
        if type(row.get(key)) is not bool:
            raise ValueError("Derived row has a malformed boolean field: " + key)
    hard = row.get("hard")
    if hard is not None and type(hard) is not bool:
        raise ValueError("Hard label must be true/false/null")
    if not isinstance(row.get("request_hash"), str) or not row["request_hash"]:
        raise ValueError("Missing actual logical request hash")
    if not row["target_ok"]:
        if hard is not None:
            raise ValueError("Transport-unavailable row has a populated hard label")
        return "transport_unavailable"
    if not row["execution_ok"]:
        if hard is not None:
            raise ValueError("Infrastructure-unknown row has a populated hard label")
        return "execution_infrastructure_unknown"
    if not row["format_ok"]:
        if hard is not False:
            raise ValueError("Delivery failure must retain the original hard=false label")
        return "delivery_failure"
    if hard is False:
        return "delivered_behavior_failure"
    if hard is True:
        return "hard_pass"
    raise ValueError("Delivered observable row is missing its original hard label")


def _request_groups(rows):
    groups = defaultdict(list)
    invariant = (
        "id",
        "stream",
        "stage",
        "repeat",
        "skill_hash",
        "skill_active",
        "target_ok",
        "execution_ok",
        "format_ok",
        "hard",
        "case_fraction",
        "response",
        "files",
        "evaluation",
    )
    for row in rows:
        groups[row["request_hash"]].append(row)
    for group in groups.values():
        if any(any(row.get(key) != group[0].get(key) for key in invariant) for row in group[1:]):
            raise ValueError("Shared request aliases disagree on an existing observation")
    return groups


def counts(rows):
    rows = list(rows)
    groups = _request_groups(rows)
    unique = [group[0] for group in groups.values()]
    logical = Counter(classify(row) for row in rows)
    actual = Counter(classify(row) for row in unique)
    observed = [row for row in rows if row["target_ok"] and row["execution_ok"]]
    return {
        "logical_rows": len(rows),
        "five_categories_logical_rows": {name: logical[name] for name in CATEGORIES},
        "actual_request_hash_count": len(groups),
        "five_categories_unique_request_hashes": {name: actual[name] for name in CATEGORIES},
        "shared_logical_alias_rows": len(rows) - len(groups),
        "original_hard_accounting": {
            "expected_rows": len(rows),
            "observable_denominator": len(observed),
            "hard_passes": sum(row["hard"] is True for row in observed),
            "hard_failures": sum(row["hard"] is False for row in observed),
            "unknown": len(rows) - len(observed),
            "delivery_failures_remain_in_original_denominator": True,
        },
        "nonempty_skill_rows": sum(row["skill_active"] for row in rows),
        "actual_requests_with_nonempty_skill": sum(row["skill_active"] for row in unique),
        "distinct_nonempty_skill_hashes": len({row["skill_hash"] for row in rows if row["skill_active"]}),
        "nonempty_skill_streams": sorted({row["stream"] for row in rows if row["skill_active"]}),
    }


def _job(identifier, skill, stream, stage, repeat):
    return {"id": identifier, "skill": skill, "stream": stream, "stage": stage, "repeat": repeat}


def _derived(reader, job):
    row = reader.read("targets/" + digest(job) + ".json", record=True)
    expected = {
        "id": job["id"],
        "stream": job["stream"],
        "stage": job["stage"],
        "repeat": job["repeat"],
        "skill_hash": digest(job["skill"]),
        "skill_active": bool(job["skill"]),
        "arm": "shared_content",
    }
    if any(row.get(key) != value for key, value in expected.items()):
        raise ValueError("Derived target does not match its sealed job identity")
    return row


def _lineage(reader, protocol, results):
    frozen = reader.read("final_frozen.json")
    histories = reader.read("histories/r1.json")
    expected = {
        (stream, policy, round_index)
        for stream in protocol["streams"]
        for policy in protocol["policies"]
        for round_index in protocol["rounds"]
    }
    if not isinstance(histories, list) or len(histories) != len(expected):
        raise ValueError("Incomplete frozen learning history")
    identities = {(h["stream"], h["policy"], h["round"]) for h in histories}
    if identities != expected:
        raise ValueError("Duplicate or unexpected learning history identity")
    state_keys = {f"s{s}_{p}" for s in protocol["streams"] for p in protocol["policies"]}
    if (
        frozen.get("freeze_before_holdout") is not True
        or frozen.get("protocol_hash") != digest(protocol)
        or frozen.get("histories_hash") != digest(histories)
        or set(frozen.get("states", {})) != state_keys
        or results.get("final_state_hash") != digest(frozen["states"])
    ):
        raise ValueError("Final protocol/state/history freeze mismatch")
    decisions = {r: reader.read(f"decisions/r{r}.json") for r in protocol["rounds"]}
    completed = {(h["stream"], h["policy"], h["round"]): h for h in results["decisions"]}
    if len(results["decisions"]) != len(expected) or set(completed) != expected:
        raise ValueError("Completed decision identities do not match histories")
    for h in histories:
        s, p, r = h["stream"], h["policy"], h["round"]
        key = f"s{s}_{p}"
        if set(decisions[r]) != state_keys:
            raise ValueError("Decision seal is incomplete")
        if any(h.get(field) != value for field, value in decisions[r][key].items()):
            raise ValueError("History differs from its pre-audit decision seal")
        if any(h.get(field) != value for field, value in completed[s, p, r].items()):
            raise ValueError("Completed decision summary differs from history")
        archived = reader.read(f"states/{key}_r{r}.json")
        for component in ("learning", "validator"):
            _sealed(archived[component])
            _sealed(h[component + "_before"])
            if archived[component] != h[component + "_after"]:
                raise ValueError("Archived state differs from its completed history")
            if r:
                previous = reader.read(f"states/{key}_r{r - 1}.json")
                if h[component + "_before"] != previous[component]:
                    raise ValueError("Learning history is not continuous between rounds")
        for name in ("working_local", "approved_deployed"):
            if not isinstance(archived["learning"].get(name), str):
                raise ValueError("Frozen Skill is not text")
        if r == protocol["rounds"][-1] and archived != frozen["states"][key]:
            raise ValueError("Final archived state differs from holdout freeze")
        if not isinstance(h["candidate"].get("content"), str) or h["candidate"].get("content_hash") != digest(
            h["candidate"]["content"]
        ):
            raise ValueError("Frozen proposal content hash mismatch")
    return frozen, histories


def _final(reader, protocol, results, frozen):
    rows = reader.read("final_rows.json")
    analysis = results["final_analysis"]
    expected_size = (
        protocol["phase_counts"]["holdout"] * len(ARMS) * len(protocol["streams"]) * len(protocol["final_repeats"])
    )
    if (
        len(rows) != expected_size
        or analysis.get("n_rows") != len(rows)
        or analysis.get("expected_rows") != len(rows)
        or analysis.get("all_rows_present") is not True
    ):
        raise ValueError("Final matrix row cardinality differs from frozen analysis")
    ids = {row["id"] for row in rows}
    expected = {
        (identifier, stream, arm, repeat)
        for identifier in ids
        for stream in protocol["streams"]
        for arm in ARMS
        for repeat in protocol["final_repeats"]
    }
    identities = {(row["id"], row["stream"], row["arm"], row["repeat"]) for row in rows}
    if (
        len(ids) != protocol["phase_counts"]["holdout"]
        or analysis.get("n_tasks") != len(ids)
        or len(identities) != len(rows)
        or identities != expected
    ):
        raise ValueError("Final task/stream/arm/repeat matrix has missing or duplicated identities")
    metadata = {}
    for row in rows:
        labels = tuple(row.get(key) for key in ("cluster_id", "family", "context", "mode"))
        if row["id"] in metadata and metadata[row["id"]] != labels:
            raise ValueError("Task metadata changes across final arms or repetitions")
        metadata[row["id"]] = labels
    if analysis.get("n_project_clusters") != len({labels[0] for labels in metadata.values()}):
        raise ValueError("Final project cluster count differs from frozen analysis")
    alias_plan = reader.read("final_alias_plan.json")
    if len(alias_plan) != len(rows):
        raise ValueError("Final alias plan cardinality differs")
    observed_plan = []
    for row in rows:
        if row.get("phase") != "holdout" or row.get("stage") != "final":
            raise ValueError("Final matrix contains non-final or non-holdout rows")
        arm = row["arm"]
        if arm == "noskill":
            skill = ""
        else:
            policy = arm.removeprefix("working_")
            component = "working_local" if arm.startswith("working_") else "approved_deployed"
            skill = frozen["states"][f"s{row['stream']}_{policy}"]["learning"][component]
        job = _job(row["id"], skill, row["stream"], "final", row["repeat"])
        if row.get("shared_draw_job_hash") != digest(job):
            raise ValueError("Final shared job differs from frozen Skill")
        derived = _derived(reader, job)
        expected_row = {
            **derived,
            "arm": arm,
            "shared_draw_job_hash": digest(job),
            "diagnostic_not_deployment": arm.startswith("working_"),
        }
        if row != expected_row:
            raise ValueError("Final row differs from its already-scored target artifact")
        observed_plan.append({"arm": arm, "job_hash": digest(job)})
    if Counter(digest(row) for row in alias_plan) != Counter(digest(row) for row in observed_plan):
        raise ValueError("Final logical rows differ from frozen alias plan")
    aggregate = counts(rows)
    if (
        analysis.get("unique_api_requests") != aggregate["actual_request_hash_count"]
        or analysis.get("shared_alias_rows") != aggregate["shared_logical_alias_rows"]
    ):
        raise ValueError("Request sharing differs from original final analysis")
    by_arm = {}
    for arm in ARMS:
        selected = [row for row in rows if row["arm"] == arm]
        summary = counts(selected)
        original = analysis["arms"][arm]
        accounting = summary["original_hard_accounting"]
        for key, expected_count in (
            ("n_expected_rows", len(selected)),
            ("n_rows", len(selected)),
            ("n_observable", accounting["observable_denominator"]),
            ("hard_passes", accounting["hard_passes"]),
            ("hard_failures", accounting["hard_failures"]),
            ("skill_active_rows", summary["nonempty_skill_rows"]),
        ):
            if original.get(key) != expected_count:
                raise ValueError("Stratified counts disagree with original arm statistics")
        by_arm[arm] = {
            **summary,
            "original_arm_statistics_copied_without_recomputation": original,
            "by_stream": {
                str(stream): counts([row for row in selected if row["stream"] == stream])
                for stream in protocol["streams"]
            },
            "by_repeat": {
                str(repeat): counts([row for row in selected if row["repeat"] == repeat])
                for repeat in protocol["final_repeats"]
            },
            "by_mode": {
                mode: counts([row for row in selected if row["mode"] == mode])
                for mode in sorted({row["mode"] for row in selected})
            },
        }
    return {"scope": "frozen_final_holdout", "all": aggregate, "by_arm": by_arm}


def _development(reader, histories):
    logical = []
    for h in histories:
        s, p, r = h["stream"], h["policy"], h["round"]
        conditions = {
            "base": "",
            "working": h["learning_before"]["working_local"],
            "candidate": h["candidate"]["content"],
        }
        for source, pairs in (("source", h["source_pairs"]), ("replay", h["replay_pairs"])):
            seen = set()
            for pair in pairs:
                identity = pair["id"], pair["repeat"]
                if identity in seen:
                    raise ValueError("Duplicate development task/repeat pair")
                seen.add(identity)
                for condition, skill in conditions.items():
                    row = _derived(reader, _job(pair["id"], skill, s, f"r{r}", pair["repeat"]))
                    expected_phase = "learn0" if source == "replay" else f"learn{r}"
                    if row["phase"] != expected_phase or row.get("evaluation_mode") != "finite_private_tests":
                        raise ValueError("Development audit tried to mix gate/public-only or holdout evaluations")
                    basis = pair[condition]
                    if basis["available"] != (row["target_ok"] and row["execution_ok"]) or basis.get("hard") != row[
                        "evaluation"
                    ].get("hard"):
                        raise ValueError("Development pair basis differs from its scored artifact")
                    logical.append(
                        {
                            **row,
                            "audit_policy": p,
                            "audit_round": r,
                            "audit_source": source,
                            "audit_condition": condition,
                        }
                    )
    groups, by_policy = defaultdict(list), defaultdict(list)
    for row in logical:
        key = f"r{row['audit_round']}/{row['audit_source']}/{row['audit_condition']}"
        groups[key].append(row)
        by_policy[row["audit_policy"] + "/" + key].append(row)
    return {
        "scope": "source_and_replay_only_no_gate_rescoring",
        "all": counts(logical),
        "by_round_source_condition": {key: counts(value) for key, value in sorted(groups.items())},
        "by_policy_round_source_condition": {key: counts(value) for key, value in sorted(by_policy.items())},
    }


def audit(run, *, include_development=False):
    reader = Reader(run)
    results = reader.read("results.json")
    if results.get("status") != "complete":
        raise ValueError("Completion barrier not met; no final or development artifact was read")
    reader.complete = True
    protocol = reader.read("protocol.json")
    if protocol.get("version") != PROTOCOL_VERSION or results.get("protocol_hash") != digest(protocol):
        raise ValueError("Completed results disagree with the supported V3 protocol")
    if (
        protocol.get("streams") != [0, 1]
        or protocol.get("rounds") != [0, 1]
        or protocol.get("policies") != list(POLICIES)
        or protocol.get("final_arms") != list(ARMS)
        or protocol.get("final_repeats") != [0, 1, 2]
        or protocol.get("shared_identical_content_draws_including_final") is not True
    ):
        raise ValueError("Unsupported frozen V3 experimental layout")
    frozen, histories = _lineage(reader, protocol, results)
    final = _final(reader, protocol, results, frozen)
    development = _development(reader, histories) if include_development else {"included": False}
    reader.verify_unchanged()
    return {
        "version": VERSION,
        "status": "completed_source_audited",
        "source_run": str(reader.root),
        "source_protocol_version": protocol["version"],
        "protocol_hash": digest(protocol),
        "completion_barrier_checked": True,
        "input_sha256": dict(reader.hashes),
        "audit_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "final": final,
        "development": development,
        "original_hard_labels_and_denominators_changed": False,
        "candidate_reexecution": False,
        "model_calls": 0,
        "api_caches_read": False,
        "new_significance_tests": False,
        "new_thresholds": False,
        "interpretation": [
            "Delivery failure means existing format_ok=False: it can include JSON, path, file-map, syntax or AST-contract rejection, not only JSON errors.",
            "A delivered behavior failure is an existing finite-test failure after artifact admission, not proof of causal semantic negative transfer.",
            "Delivery failures remain hard=False in the unchanged original observable denominator.",
            "Request-hash deduplication counts actual logical requests, not HTTP retry attempts or independent projects.",
            "Per-arm and per-condition request counts overlap when they alias one shared request; they must not be added as independent calls.",
            "Working-Skill arms are frozen sandbox diagnostics, not approved deployments.",
            "This posthoc descriptive audit neither repairs outputs nor creates a new confirmatory evaluation.",
        ],
    }


def write_report(report, output, source):
    output, source = Path(output).resolve(), Path(source).resolve()
    if output == source or output.is_relative_to(source):
        raise ValueError("Audit output must be a new directory outside the original run")
    if output.exists():
        raise ValueError("Audit output directory already exists; never overwrite an audit")
    output.mkdir(parents=True, exist_ok=False)
    destination = output / "delivery_audit.json"
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return str(destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New directory outside the completed source run")
    parser.add_argument(
        "--include-development", action="store_true", help="Also audit source/replay conditions, never gate rescoring"
    )
    args = parser.parse_args(argv)
    try:
        report = audit(args.run, include_development=args.include_development)
        destination = write_report(report, args.output, args.run)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "original_run_unchanged": True,
                    "model_calls": 0,
                }
            )
        )
        return 1
    print(json.dumps({"ok": True, "report": destination, "original_run_unchanged": True, "model_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
