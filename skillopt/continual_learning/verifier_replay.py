"""Frozen-train verifier replay (registered 10/8; Codex design rounds 1-2): the CURRENT verifier re-run on one
completed v10 BigCodeBench stage's sealed train rollout, verifier-only.

A mechanism screen, not a learning stage: no solver call, no analyst, no gate, no test evaluation. The source
stage is read-only and verified first (its sealed identity, result and artifact inventory); the complete eligible
rollout of the registered step is reconstructed from the source's sealed evaluation records (every train task
exactly once; source-unknown rows counted, never silently dropped) and must equal the rows the source verifier
saw. The replay runs under its own manifest -- the source's model, runtime and budget with the current
POLICY_V10, the current code identity and a ``replay_of`` binding -- with its own ledger in a new directory.
Only step 0 of a stage that started from the default rubric is supported: the replay starts from the CURRENT
default rubric and records that transition (an evolved historical rubric is never migrated).
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import CachedAPI, digest

from .contracts import MULTIDOMAIN_VERSIONS, VERIFIER_METHOD
from .feedback import project
from .ledger import LearningPending, Ledger
from .recovery import POLICY_V10, client_options
from .verifier import VERSION, Verifier, default_policy_record, native_probe_executor

# v2 (10/8 amendment, Codex design v7-1): the registered replay runs verifier v7 (one length recovery; terminal
# unit delivery results; coverage/delivery accounting). Source rollout, eligibility and criteria are v1's.
REPLAY_PROTOCOL = "fivebench-verifier-replay-v2"


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class _ReplayVerifier(Verifier):
    """The current verifier bound to rows already verified against the SOURCE stage's sealed evidence."""

    def __init__(self, manifest, ledger, root, step, pairs, **kwargs):
        super().__init__(manifest, ledger, root, step, **kwargs)
        self._pairs = pairs

    def _bound_pairs(self, items, rows, skill):
        require(len(items) == len(rows) == len(self._pairs)
                and all(i is p[0] and r is p[1] for i, r, p in zip(items, rows, self._pairs)),
                "Replay rows must be the verified source rows")
        return list(self._pairs)


def source_rollout(source, step):
    """Verify a completed v10 BigCodeBench learning directory and reconstruct step ``step``'s complete train rollout.

    Returns (identity, result, manifest, pairs, accounting). Every train task authorized by the source manifest must
    have exactly one sealed evaluation (with its intent) for this rollout of the parent Skill; unknown scores are
    counted and excluded exactly as the learner excluded them; the remaining evidence set must equal the rows the
    source verifier recorded for this step.
    """
    from .skillopt import _stage_artifacts

    source = safe_path(source)
    identity = read_json(source / "identity.json", sealed=True)
    result = read_json(source / "result.json", sealed=True)
    manifest = identity["manifest"]
    require(result["identity_hash"] == identity["record_hash"], "Source result does not bind its identity")
    require(result["artifacts"] == _stage_artifacts(source, Ledger(source, manifest, None)),
            "Source learning evidence changed or is incomplete")
    require(manifest.get("method") == VERIFIER_METHOD and manifest["benchmark"] == "bigcodebench"
            and result["status"] == "completed", "A replay needs a completed v10 BigCodeBench stage")
    require(step == 0, "Only step 0 (the parent Skill under the default rubric) is a registered replay")
    require((manifest.get("parent_verifier_policy") or {}).get("bigcodebench") is None,
            "An evolved historical rubric is never migrated")
    panel = read_json(source / "panel.json")
    skill = manifest["parent_skill"]
    train = [t for t in panel["tasks"] if t["family_id"] in manifest["train_families"]]
    authorized = sorted(h for h, role in manifest["authorized_tasks"].items() if role == "train")
    require(sorted(digest(t) for t in train) == authorized and len(set(authorized)) == len(train),
            "The source panel's train tasks differ from the manifest's train authorization")
    pairs, unknown = [], 0
    for task in train:
        require(task.get("partition") == "development", "A train task outside the development partition")
        request = {"manifest_hash": manifest["record_hash"], "candidate_hash": digest({"skill": skill}),
                   "task_hash": digest(task), "role": "train", "repeat": 0}
        if manifest["version"] in MULTIDOMAIN_VERSIONS:
            request["benchmark"] = manifest["benchmark"]
        request["rollout"] = step
        key = digest(request)
        saved = read_json(source / "evaluations" / (key + ".json"), sealed=True)
        require(saved["request"] == request
                and read_json(source / "evaluation_intents" / (key + ".json"), sealed=True) == seal(request),
                "A train row of the registered rollout is missing or differs from its intent")
        if saved["score"]["status"] == "unknown":
            unknown += 1  # the learner excluded it from feedback and from the verifier, so does the replay
            continue
        trace = project(manifest, task["public"], saved["prediction"], saved["score"], private=task["private"],
                        role="train")
        pairs.append(({"role": "train", "task": task},
                      {"output": {"output": trace["Generated Outputs"], "evidence_hash": saved["record_hash"]},
                       "score": saved["score"]["score"], "trajectory": trace}))
    tokens = sorted(r["output"]["evidence_hash"] for _, r in pairs)
    source_summary = read_json(source / "verifier" / str(step) / "summary.json", sealed=True)
    seen = sorted(read_json(p, sealed=True)["evidence_hash"]
                  for p in (source / "verifier" / str(step) / "rows").glob("*.json"))
    require(tokens == seen and len(source_summary["row_record_hashes"]) == len(tokens),
            "The reconstructed rollout is not the row set the source verifier saw")
    source_policy = read_json(source / "verifier" / str(step) / "policy.json", sealed=True)
    accounting = {"train_tasks": len(train), "eligible_rows": len(pairs), "source_unknown_rows": unknown,
                  "row_evidence_digest": digest(tokens), "source_verifier_summary_hash": source_summary["record_hash"],
                  "source_policy_record_hash": source_policy["record_hash"],
                  "source_start_policy_hash": source_policy["parent_policy_hash"]}
    return identity, result, manifest, pairs, accounting


def overlaps(a, b):
    """True when one path contains the other (the archived source must never receive a replay write)."""
    a, b = Path(a).resolve(), Path(b).resolve()
    return a == b or a.is_relative_to(b) or b.is_relative_to(a)


def _replay_manifest(identity, result, manifest, accounting, step):
    """The replay's execution identity: the source's model/runtime/budget (the ledger keeps v10 semantics), the
    CURRENT POLICY_V10 and code (every continual_learning source, the retrieval extractor and the frozen
    dependency identity), and the binding to the source evidence."""
    from .contracts import sources

    start = default_policy_record("bigcodebench")
    return seal({
        "version": manifest["version"], "replay_protocol": REPLAY_PROTOCOL, "method": manifest["method"],
        "benchmark": manifest["benchmark"], "seed": manifest["seed"], "model": manifest["model"],
        "runtime": manifest["runtime"], "budget": dict(manifest["budget"]), "recovery_policy": dict(POLICY_V10),
        "execution_identity": {"verifier_version": VERSION, "sources": sources()},
        "replay_of": {"source_manifest_hash": manifest["record_hash"], "source_identity_hash": identity["record_hash"],
                      "source_result_hash": result["record_hash"], "step": step,
                      "parent_skill_sha256": hashlib.sha256(manifest["parent_skill"].encode()).hexdigest(),
                      "start_policy_hash": start["policy_hash"],
                      "policy_transition": "source_default_to_current_default", **accounting}})


def _replay_artifacts(root, ledger):
    """Every governed replay file by content hash: ledger receipts/intents, verifier records and host-only
    calibration (feedback.artifacts for a v10 ledger) plus the replay's own manifest, start marker and service."""
    from .feedback import artifacts

    return {**artifacts(ledger), **{name: _sha(root / name) for name in ("replay.json", "started.json",
                                                                          "model_service.json")
                                    if (root / name).exists()}}  # a client failure can precede the service file


def replay_step(source, step, output, *, repo=None, fixture_api=None, fixture_probe_executor=None,
                fixture_fetcher=None):
    """Run the current verifier once on the source step's frozen rollout; returns the sealed replay result.

    A finished result is returned only after its binding (same source, step and current code) and its complete
    artifact inventory are re-verified. A replay is never resumed: a started marker without a result is an
    interrupted (inconclusive) replay. Transport, budget, cleanup or usage gaps are recorded as ``pending``
    (inconclusive), never as a negative mechanism result.
    """
    source, root = safe_path(source), safe_path(output)
    require(not overlaps(source, root), "The replay output must not overlap the archived source")
    identity, result, manifest, pairs, accounting = source_rollout(source, step)
    fixture = manifest["model"]["provider"] == "fixture"
    require(fixture == (fixture_api is not None and fixture_probe_executor is not None)
            and (fixture or fixture_fetcher is None), "Fixture hooks belong to a fixture source only")
    replay = _replay_manifest(identity, result, manifest, accounting, step)
    final = root / "replay-result.json"
    if final.exists():
        saved = read_json(final, sealed=True)
        require(read_json(root / "replay.json", sealed=True) == replay and saved["replay_hash"] == replay["record_hash"],
                "The finished replay belongs to another source, step or code identity")
        require(saved["artifacts"] == _replay_artifacts(root, Ledger(root, replay, None)),
                "Finished replay evidence changed or is incomplete")
        return saved
    require(not (root / "started.json").exists(), "Interrupted replay retained; no automatic resume")
    write_json(root / "replay.json", replay)
    if not fixture:
        require(repo is not None, "A natural replay needs the credential repository")
        require(backends.readiness("bigcodebench", replay["runtime"])["status"] == "ready",
                "BigCodeBench native runtime is not ready")
    write_json(root / "started.json", seal({"replay_hash": replay["record_hash"]}))
    api, pending, summary = fixture_api, None, None
    try:
        if not fixture:
            model = replay["model"]
            api = CachedAPI(Path(repo), root / "api", provider=model["provider"], model=model["name"], workers=1,
                            reasoning_effort=model["reasoning_effort"],
                            **model.get("transport", {"initial_health_policy": "completed_response_v1"}),
                            **({"proxy": model["proxy"]} if "proxy" in model else {}), **client_options(replay))
        write_json(root / "model_service.json", seal(api.service))
        ledger = Ledger(root, replay, api)
        executor = fixture_probe_executor if fixture else native_probe_executor(replay["runtime"])
        runner = _ReplayVerifier(replay, ledger, root, step, pairs, executor=executor, fetcher=fixture_fetcher)
        summary, _ = runner.run([i for i, _ in pairs], [r for _, r in pairs], default_policy_record("bigcodebench"),
                                None, skill=manifest["parent_skill"])
    except LearningPending as exc:
        pending = str(exc)
    finally:
        if api is not None and not fixture:
            api.close()
    # The learner's final guard: an unknown usage or receipt never completes (run_stage: incomplete_usage).
    ledger = Ledger(root, replay, api)
    costs = ledger.snapshot()
    if pending is None and ledger.usage_blocks_completion(costs):
        pending = "incomplete_usage"
    outcome = {"version": REPLAY_PROTOCOL, "replay_hash": replay["record_hash"], **accounting, "costs": costs}
    if pending is not None:
        outcome.update(status="pending", reason=pending, artifacts=_replay_artifacts(root, ledger))
        frozen = seal(outcome)
        write_json(final, frozen)
        return frozen
    calibration = read_json(root / "host_only" / "verifier" / str(step) / "calibration.json", sealed=True)
    # Structural detections await the independent public-contract audit (launch criterion ii); the queue binds
    # each to its exact probe, its row record and its sealed execution receipt (the complete projection).
    queue = []
    for path in sorted((root / "verifier" / str(step) / "rows").glob("*.json")):
        row = read_json(path, sealed=True)
        for probe in row["probes"]:
            if row["host_status"] == "fail" and probe["kind"] == "structure" and probe["outcome"] == "fail":
                queue.append({"evidence_hash": row["evidence_hash"], "row_record_hash": row["record_hash"],
                              "probe_index": probe["index"], "execution_receipt": f"verifier/{step}/executions/"
                              f"{row['evidence_hash']}.json", "admitted": summary["structure_admitted"]})
    outcome.update(status="completed", summary_hash=summary["record_hash"], calibration_hash=calibration["record_hash"],
                   authorized=summary["authorized"], structure_admission=calibration["structure_admission"],
                   by_kind=calibration["by_kind"], coverage=calibration["coverage"], delivery=calibration["delivery"],
                   detections=summary["detections"],
                   false_rejections=summary["false_rejections"], host_pass_rows=summary["host_pass_rows"],
                   host_fail_rows=summary["host_fail_rows"], policy_status=summary["policy_status"],
                   reports_with_feedback=summary["reports_with_feedback"], structural_detections_for_audit=queue,
                   criteria={"i_structure_admitted": calibration["structure_admission"]["admitted"],
                             "ii_audited_structural_detection": None,  # set only by the independent audit record
                             "iii_step_authorized": summary["authorized"]},
                   artifacts=_replay_artifacts(root, ledger))
    frozen = seal(outcome)
    write_json(final, frozen)
    return frozen
