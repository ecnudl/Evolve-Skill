"""Completed V8 feedback integrity audit with optional offline native replay.

Reads only this development run; never creates an API client, resamples a
trajectory, writes the run, or returns hidden scores to an optimizer. Replaying
cached artifacts checks the existing oracle, not its external validity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import audit_coevolution_v6 as prior  # noqa: E402
from scripts.audit_coevolution_v7 import _pacing  # noqa: E402
from skillopt.coevolution_v5 import core  # noqa: E402
from skillopt.coevolution_v8 import feedback_study as e  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402

_require = prior._require


def tree_hashes(root):
    paths = list(Path(root).rglob("*"))
    _require(not any(p.is_symlink() for p in paths), "Symlink audit input rejected")
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths) if p.is_file()}


def _read(path):
    record = prior._json(path)
    core.verify(record)
    return record


def _cost(receipts):
    return {"logical_calls": len(receipts), "api_ok": sum(r["ok"] for r in receipts),
            "http_attempts": sum(r["http_attempt_count"] for r in receipts),
            **{k: sum(r.get("usage", {}).get(k, 0) or 0 for r in receipts)
               for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
            "missing_usage_calls": sum(not r.get("usage") for r in receipts),
            "returned_models": dict(Counter(prior._returned_model(r) for r in receipts))}


def _sensitivity(rows):
    positions = sorted({(r["task_id"], r["block"]) for r in rows})
    indexed = {(r["task_id"], r["block"], r["arm"]): r for r in rows}
    both_api = [p for p in positions if all(indexed[(*p, a)]["api_ok"] for a in e.ARMS)]
    initial_api = [p for p in both_api if all(indexed[(*p, a)]["initial_api_ok"] for a in e.ARMS)]
    both_oracles = [p for p in positions if all(indexed[(*p, a)]["score"]["oracle_available"] for a in e.ARMS)]

    def selected(values):
        return {"pairs": len(values), "successes": {arm: sum(indexed[(*p, arm)]["score"]["all_attempt_success"]
                for p in values) for arm in e.ARMS},
                "wins": sum(indexed[(*p, "structured")]["score"]["all_attempt_success"] >
                            indexed[(*p, "generic")]["score"]["all_attempt_success"] for p in values),
                "losses": sum(indexed[(*p, "structured")]["score"]["all_attempt_success"] <
                              indexed[(*p, "generic")]["score"]["all_attempt_success"] for p in values)}

    return {"both_revision_api_ok": selected(both_api), "initial_and_both_revision_api_ok": selected(initial_api),
            "both_oracles_available": selected(both_oracles),
            "post_treatment_diagnostic_not_causal_or_primary": True,
            "never_replace_preregistered_all_attempt_metric": True}


def audit(run, repo=REPO, *, reexecute=True, panel=None):
    """Validate a completed closed grid; replay only already cached artifacts.

    ``panel`` supports explicit offline fixture testing. CLI always rebuilds the
    frozen real task panel. ``reexecute=False`` is labeled provenance-only, not
    a completed independent native-score replay.
    """
    run, repo = Path(run).absolute(), Path(repo).resolve()
    _require(not any(p.is_symlink() for p in (run, *run.parents)), "Symlink run path rejected")
    before = tree_hashes(run)
    for name in ("results.json", "protocol.json", "panel.json", "preflight.json", "rows.json"):
        _require(name in before, "Completed audit requires " + name)
    result, protocol = _read(run / "results.json"), _read(run / "protocol.json")
    _require(result.get("complete") is True and protocol["version"] == e.VERSION, "Completed V8 feedback run required")
    study = e.FeedbackStudy(repo, run, blocks=protocol["blocks"], panel=panel)
    study.protocol = protocol  # No prepare(): audit never writes missing seals.
    _require(protocol["source_hashes"] == study.sources(), "Frozen source hashes changed")
    expected_panel = {"tasks": [{"domain": a.domain, "task": e.payload(a)} for a in study.panel]}
    _require(_read(run / "panel.json") == core.seal(expected_panel)
             and protocol["panel_hash"] == digest(expected_panel), "Frozen task panel changed")
    _require(protocol["max_calls"] == study.max_calls and protocol["arms"] == list(e.ARMS)
             and protocol["skill"] == "" and protocol["all_initials_included"] is True
             and protocol["semantic_retries"] == 0 and protocol["seed"] == e.SEED
             and protocol["hidden_scoring_after_both_revisions_never_feedback"] is True,
             "Frozen paired design or authority changed")
    calls, accounting = prior._receipts(run, protocol, True)
    _require(len(calls) == study.max_calls, "Complete run omitted planned actual API calls")
    pacing = _pacing(run, {"pacing_policy": protocol["pacing"]}, calls)
    _require(accounting["ledger"] == result["ledger"], "Final ledger differs from actual request receipts")
    expected_hashes = set(calls)
    for directory in ("stages", "private_scores", "intents", "api/budget_reservations"):
        _require({p.stem for p in (run / directory).glob("*.json")} == expected_hashes,
                 "Missing/extra completed evidence in " + directory)
    sample = next(iter(calls.values()))
    offline = SimpleNamespace(offline=True, model=sample["request"]["model"], service=sample["request"]["service"])
    positions = study._positions()
    stages, rows, grouped_calls = {}, [], {a: [] for a in ("initial", *e.ARMS)}
    replayed_public = replayed_private = 0
    if reexecute and any(a.domain == "coding" for a in study.panel):
        _require(e.executor.sandbox_probe()["ok"],
                 "OS execution sandbox unavailable; cannot claim native replay (use --no-reexecute for provenance only)")
    preflight = _read(run / "preflight.json")
    _require(preflight["never_model_feedback"] is True and len(preflight["rows"]) == len(study.panel)
             and {r["task_id"] for r in preflight["rows"]} == set(study.indexed), "Reference preflight grid changed")
    for row in preflight["rows"]:
        adapter = study.indexed[row["task_id"]]
        task = e.payload(adapter)
        reference = task["reference_files"] if adapter.domain == "coding" else task["reference_artifact"]
        _require(row["reference_hash"] == digest(reference), "Reference identity changed")
        e.verify_private_evaluation(adapter, reference, row["evaluation"])
        _require(e.score(adapter, reference, row["evaluation"])["all_attempt_success"] == 1, "Reference not correct")
        if reexecute:
            fresh = e.evaluate(adapter, reference, public_only=False)
            _require(fresh == row["evaluation"], "Reference replay changed for " + row["task_id"])
    for task_id, block in positions:
        adapter = study.indexed[task_id]
        first = study._stage(offline, task_id, block, "generation")
        pair = {"initial": first, **{arm: study._stage(offline, task_id, block, "revision", arm, first) for arm in e.ARMS}}
        private = {}
        for arm, stage in pair.items():
            h, artifact = stage["request_hash"], stage["delivery"]["artifact"]
            _require(h not in stages, "A real request was aliased across independent stages")
            stages[h] = stage
            grouped_calls[arm].append(calls[h])
            evidence = _read(run / "private_scores" / f"{h}.json")
            _require(evidence["stage_hash"] == stage["record_hash"] and evidence["request_hash"] == h
                     and evidence["never_model_feedback"] is True, "Private score not bound to original stage")
            e.verify_private_evaluation(adapter, artifact, evidence["evaluation"])
            _require(evidence["score"] == e.score(adapter, artifact, evidence["evaluation"]), "Cached score mismatch")
            if reexecute:
                fresh_public = e.public_observation(adapter, artifact, calls[h], stage["stage"])
                _require(all(stage[k] == v for k, v in fresh_public.items()), "Public feedback replay changed for " + h)
                fresh_private = e.evaluate(adapter, artifact, public_only=False)
                _require(fresh_private == evidence["evaluation"], "Private oracle replay changed for " + h)
                _require(e.score(adapter, artifact, fresh_private) == evidence["score"], "Replayed score differs")
                replayed_public += 1
                replayed_private += 1
            private[arm] = evidence
        for arm in e.ARMS:
            stage = pair[arm]
            rows.append({"task_id": task_id, "cluster_id": e.payload(adapter)["cluster_id"], "domain": adapter.domain,
                "block": block, "arm": arm, "initial_request_hash": first["request_hash"],
                "initial_response_hash": digest(first["response"]), "initial_score": private["initial"]["score"],
                "request_hash": stage["request_hash"], "stage_hash": stage["record_hash"],
                "api_ok": stage["api_ok"], "initial_api_ok": first["api_ok"], "score": private[arm]["score"],
                "delivery_diagnostics": stage["delivery"]["diagnostics"]})
    _require(set(stages) == expected_hashes, "Scheduled stage grid does not exactly cover closed API ledger")
    _require(_read(run / "rows.json") == core.seal({"rows": rows, "hidden_feedback_used": False}), "Derived final rows changed")
    summary = e.summary(rows, expected_positions=positions)
    _require(result == study._result(rows, summary, e.closed_ledger(run, study.max_calls)), "Completed summary/result differs")
    losses, indexed = [], {(r["task_id"], r["block"], r["arm"]): r for r in rows}
    for p in positions:
        left, right = (indexed[(*p, arm)] for arm in e.ARMS)
        if right["score"]["all_attempt_success"] < left["score"]["all_attempt_success"]:
            losses.append({"task_id": p[0], "block": p[1], "domain": right["domain"],
                "generic": left["score"], "structured": right["score"], "structured_api_ok": right["api_ok"],
                "structured_delivery_diagnostics": right["delivery_diagnostics"],
                "structured_request_hash": right["request_hash"]})
    _require(before == tree_hashes(run), "Audit observed run evidence mutate; cannot certify read-only snapshot")
    return core.seal({"version": "v8-feedback-independent-audit-v1", "run": str(run), "passed": True,
        "results_hash": result["record_hash"], "protocol_hash": protocol["record_hash"],
        "source_file_count": len(protocol["source_hashes"]), "unchanged_run_files": len(before),
        "source_evidence_manifest_hash": digest(before), "actual_stage_count": len(stages),
        "shared_initials": len(positions), "paired_revision_rows": len(rows),
        "native_reexecution_performed": reexecute, "native_public_replays": replayed_public,
        "native_private_replays": replayed_private, "reference_replays": len(study.panel) if reexecute else 0,
        "ledger": accounting["ledger"], "pacing": pacing, "costs_by_stage": {a: _cost(rs) for a, rs in grouped_calls.items()},
        "summary": summary, "sensitivities": _sensitivity(rows), "structured_losses": losses,
        "actual_tokens_not_equal_despite_equal_calls_and_output_cap": True,
        "usage_is_reported_successful_response_usage_not_provider_invoice": True,
        "skill_evolution_measured": False, "deployment_approval": False, "model_calls_by_auditor": 0,
        "read_only_run_snapshot": True, "independent_oracle_external_validity_established": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--no-reexecute", action="store_true", help="Only provenance/score arithmetic; no independent native replay")
    args = parser.parse_args()
    print(json.dumps(audit(args.run, repo=args.repo, reexecute=not args.no_reexecute), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
