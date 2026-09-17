"""Correct the frozen V5 integration driver's nested-packet review export.

No API, model execution, scoring, or frozen-run mutation. Read sealed retained
development feedback, flatten only review evidence, and publish a NEW queue.
This creates a review assignment, never completed human-review evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v5 import core, governance  # noqa: E402
from skillopt.validator_pilot.api import digest, write_immutable_json  # noqa: E402

VERSION = "v5-postrun-human-queue-correction-v1"
SEED = 20260910


def _read(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    core.verify(value)
    return value


def _payload(value):
    return {key: item for key, item in value.items() if key != "record_hash"}


def _safe_relative(repo, relative):
    path = (repo / relative).resolve()
    if not path.is_relative_to(repo) or not path.is_file():
        raise ValueError("Frozen source path is unavailable or outside the repository")
    return path


def _verify_packet(packet, development):
    core.verify(packet)
    core.development_only(packet)
    if packet.get("phase") != "development":
        raise ValueError("Only actual development feedback may enter the review queue")
    task = development.get(packet.get("task_id"))
    if task != (packet.get("cluster_id"), packet.get("domain")):
        raise ValueError("Review feedback task does not match the frozen development panel")
    if packet.get("artifact_hash") != digest(packet.get("artifact")):
        raise ValueError("Feedback artifact content differs from its recorded hash")
    observations = packet.get("observations")
    if not isinstance(observations, list) or not observations:
        raise ValueError("Review feedback requires actual sealed observations")
    checked = {}
    for row in observations:
        core.verify(row, "receipt_hash")
        if any(row.get(key) != packet.get(key) for key in ("task_id", "domain", "phase", "artifact_hash", "rubric_hash")):
            raise ValueError("Feedback observation identity differs from its source packet")
        if row["receipt_hash"] in checked:
            raise ValueError("Duplicate feedback observation")
        checked[row["receipt_hash"]] = row
    for fact in packet.get("facts", []):
        row = checked.get(fact.get("receipt_hash"))
        if row is None or not row.get("verified") or any(
            fact.get(key) != row.get(key) for key in ("check_id", "status", "evidence_kind", "details")
        ):
            raise ValueError("Review fact is not supported by its sealed source observation")


def inspect_run(run: Path, *, repo: Path = REPO, require_complete: bool = False) -> dict:
    """Read-only validation also works while a run is incomplete; never exports."""
    run, repo = Path(run).resolve(), Path(repo).resolve()
    if not run.is_dir():
        raise ValueError("An existing V5 run directory is required")
    protocol, panel = _read(run / "protocol.json"), _read(run / "panel.json")
    if protocol.get("version") != "coevolution-v5-integration-study-v1":
        raise ValueError("Unsupported run protocol")
    if protocol["panel_hash"] != digest(_payload(panel)):
        raise ValueError("Frozen panel hash mismatch")
    if not isinstance(protocol.get("source_hashes"), dict) or not protocol["source_hashes"]:
        raise ValueError("Frozen source manifest is missing")
    for relative, expected in protocol["source_hashes"].items():
        if hashlib.sha256(_safe_relative(repo, relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen run source changed; correction cannot silently upgrade it")
    development = {}
    for group in ("source", "scope"):
        for batch in panel[group]:
            for item in batch:
                task, domain = item["task"], item["domain"]
                identity = (task["cluster_id"], domain)
                if development.setdefault(task["id"], identity) != identity:
                    raise ValueError("Frozen development task identity is inconsistent")
    rounds = protocol["rounds"]
    if type(rounds) is not int or rounds < 1:
        raise ValueError("Invalid frozen round count")
    packets, origins, state_files, last_state = {}, {}, {}, None
    for index in range(rounds):
        path = run / "states" / f"r{index}.json"
        if not path.exists():
            continue
        state = _read(path)
        state_files[f"states/r{index}.json"] = state["record_hash"]
        last_state = state
        for branch, value in _payload(state).items():
            core.verify(value["skill"], "state_hash")
            core.validate_rubric(value["rubric"])
            for packet in value["feedback"]:
                _verify_packet(packet, development)
                identifier = packet["record_hash"]
                if identifier in packets and packets[identifier] != packet:
                    raise ValueError("Feedback hash collision or inconsistent duplicate")
                packets[identifier] = packet
                origins.setdefault(identifier, []).append({"file": f"states/r{index}.json", "branch": branch})
    results_path = run / "results.json"
    complete = False
    result_hash, freeze_hash = None, None
    if results_path.exists():
        results = _read(results_path)
        complete = results.get("status") == "complete"
        if complete:
            if results.get("protocol_hash") != protocol["record_hash"]:
                raise ValueError("Completed result is not bound to this frozen protocol")
            if len(state_files) != rounds:
                raise ValueError("Completed run is missing a sealed round state")
            freeze = _read(run / "final_frozen.json")
            if freeze.get("protocol_hash") != protocol["record_hash"] or freeze.get("states") != _payload(last_state):
                raise ValueError("Final freeze and final round states differ")
            if freeze.get("decisions_hash") != digest(results.get("decisions")):
                raise ValueError("Final Skill decisions differ from their pre-evaluation freeze")
            if results.get("final_feedback_used") is not False or results.get("ledger", {}).get("unresolved_reservations"):
                raise ValueError("Unresolved run or forbidden final feedback cannot be exported")
            result_hash, freeze_hash = results["record_hash"], freeze["record_hash"]
    if require_complete and not complete:
        raise ValueError("Review correction requires a completed, frozen run")
    identity = {"protocol_hash": protocol["record_hash"], "panel_hash": panel["record_hash"],
                "results_hash": result_hash, "final_freeze_hash": freeze_hash,
                "round_state_hashes": state_files, "feedback_hashes": sorted(packets)}
    return {"complete": complete, "identity": identity, "source_run_hash": digest(identity),
            "packets": packets, "origins": origins, "verified_source_files": len(protocol["source_hashes"])}


def export_corrected_queue(run: Path, *, repo: Path = REPO) -> dict:
    verified = inspect_run(run, repo=repo, require_complete=True)
    if not verified["packets"]:
        raise ValueError("No retained development feedback exists; do not fabricate a review queue")
    rows = []
    for identifier, packet in sorted(verified["packets"].items()):
        row = {"feedback_id": identifier, "domain": packet["domain"],
               "source_run_hash": verified["source_run_hash"],
               "disputed": any(observation["status"] == "unknown" for observation in packet["observations"])}
        row.update({key: packet[key] for key in ("artifact", "contract", "facts", "repair_guidance", "hypotheses")
                    if key in packet})
        rows.append(row)
    directory = Path(run).resolve() / "human_review_corrected"
    # The original frozen human_review/ path is intentionally never touched.
    manifest = core.seal({"version": VERSION, "source_run_hash": verified["source_run_hash"],
                          "identity": verified["identity"], "origins": verified["origins"],
                          "exporter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                          "population_hash": digest(rows), "seed": SEED,
                          "selection": "two_random_and_two_remaining_disputed_per_domain",
                          "original_export_bug": "driver_nested_packet_did_not_match_top_level_whitelist",
                          "scores_and_decisions_changed": False, "human_review_performed": False})
    write_immutable_json(directory / "source_manifest.private.json", manifest)
    queue = governance.export_review_queue(directory / "queue.json", rows, seed=SEED)
    if any(not entry["evidence"] for entry in queue["entries"]):
        raise ValueError("Corrected queue must contain actual review evidence")
    return {"version": VERSION, "queue_path": str(directory / "queue.json"), "queue_hash": queue["queue_hash"],
            "source_run_hash": verified["source_run_hash"], "retained_unique_feedback": len(rows),
            "queued": len(queue["entries"]), "status": "awaiting_external_human_review",
            "original_queue_preserved": True, "experiment_results_unchanged": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        data = inspect_run(args.run)
        result = {"complete": data["complete"], "source_run_hash": data["source_run_hash"],
                  "retained_unique_feedback": len(data["packets"]),
                  "verified_source_files": data["verified_source_files"], "wrote_files": False}
    else:
        result = export_corrected_queue(args.run)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
