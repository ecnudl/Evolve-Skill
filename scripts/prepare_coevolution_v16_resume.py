"""Offline, score-blind recovery of the 2026-09-16 V16 checkpoint batch.

Never modifies the source run or frozen scientific code. Copies a clean prefix
to a new fork, preserving main final and previously cached control aliases.
The whole newly admitted batch is excluded, including successful calls.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import shutil
import sys
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.coevolution_v9.study import closed_ledger  # noqa: E402
from skillopt.coevolution_v16 import study  # noqa: E402
from skillopt.validator_pilot.api import digest, write_immutable_json  # noqa: E402

VERSION = "v16-sleep-whole-new-checkpoint-batch-fork-v1"
SLEEP = "2026-09-16T12:05:15+08:00"
BOUNDARY = "2026-09-16T04:04:44.580350+00:00"
LAST_EVENT = 426


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(root):
    result = {}
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "Symlink evidence is forbidden")
        if path.is_file():
            require(not path.name.startswith((".env", ".pending")), "Unexpected secret or unfinished write")
            result[str(path.relative_to(root))] = sha(path)
        else:
            require(path.is_dir(), "Only regular files and directories are allowed")
    return result


def choose_tail(calls, admissions, attempts, *, boundary_wall, sleep_wall):
    """Choose an entire admitted batch by clocks, never by response or score."""
    require(math.isfinite(boundary_wall) and math.isfinite(sleep_wall)
            and boundary_wall < sleep_wall, "Invalid external time boundaries")
    sequence = set(admissions)
    require(sequence and sequence == set(attempts) == set(range(1, len(sequence) + 1)),
            "HTTP admissions and outcomes must be a complete continuous sequence")
    references, retained, excluded, affected = set(), set(), set(), set()
    for h, call in calls.items():
        refs = [r["sequence"] for r in call["pacing"]["attempts"]]
        require(call["request_hash"] == h and len(refs) == call["http_attempt_count"]
                and refs and len(refs) == len(set(refs)), "Invalid logical receipt binding")
        require(not references.intersection(refs) and set(refs) <= sequence,
                "Unknown or duplicate HTTP attempt reference")
        references.update(refs)
        times = []
        for n in refs:
            a, o = admissions[n], attempts[n]
            require(a["sequence"] == o["sequence"] == n
                    and a["request_hash"] == o["request_hash"] == h, "HTTP request identity differs")
            start, end = a["admitted_wall"], o["finished_wall"]
            require(all(type(v) in (float, int) and math.isfinite(v) for v in (start, end))
                    and start <= end, "Invalid HTTP clock")
            times.append((start, end))
        if all(start < boundary_wall for start, _ in times):
            require(all(end < boundary_wall and end < sleep_wall for _, end in times),
                    "Retained request crosses the clean batch boundary")
            retained.add(h)
        else:
            require(all(start >= boundary_wall for start, _ in times), "Request retries cross batch boundary")
            excluded.add(h)
            if any(end >= sleep_wall for _, end in times):
                affected.add(h)
    require(references == sequence and retained and excluded and affected,
            "Closed ledger and an actually affected batch are required")
    prefix = {n for n, a in admissions.items() if a["request_hash"] in retained}
    require(prefix == set(range(1, len(prefix) + 1)), "Retained HTTP attempts are not a prefix")
    return {"retained_calls": sorted(retained), "excluded_calls": sorted(excluded),
            "retained_sequences": sorted(prefix), "excluded_sequences": sorted(sequence - prefix),
            "overlap_calls": sorted(affected)}


def partition(source, manifest, *, sleep_wall, boundary_wall):
    def plain(directory):
        return {p.stem: json.loads(p.read_text()) for p in (source / directory).glob("*.json")}

    calls = plain("api/calls")
    admissions = {int(n): study.read(source / "api/pacing/admissions" / (n + ".json"))
                  for n in plain("api/pacing/admissions")}
    attempts = {int(n): study.read(source / "api/pacing/attempts" / (n + ".json"))
                for n in plain("api/pacing/attempts")}
    selected = choose_tail(calls, admissions, attempts, boundary_wall=boundary_wall, sleep_wall=sleep_wall)
    tail = set(selected["excluded_calls"])
    solves = {p.stem: study.read(p) for p in (source / "runtime/solves").glob("*.json")}
    dropped = {k: r for k, r in solves.items() if tail.intersection(r["request_hashes"])}
    require(len(calls) == 615 and len(tail) == 8 and len(dropped) == 4
            and selected["retained_sequences"] == list(range(1, 620))
            and selected["excluded_sequences"] == list(range(620, 638)),
            "This recovery is restricted to the audited 615-call paused pilot")
    require(all(set(r["request_hashes"]) <= tail and r["phase"] == "final"
                and r["identity"]["repeat"] == 1 for r in dropped.values()),
            "Tail is not a complete final-phase history-1 solver batch")
    require({h for r in dropped.values() for h in r["request_hashes"]} == tail,
            "Excluded calls have unexplained dependencies")
    # Check group membership using task/Skill identity only, never any score.
    panel = study.read(source / "private_panel.json")["groups"]["final"]
    checkpoint = study.read(source / "checkpoints/round_1.json")
    tasks = [t for domain in ("coding", "spreadsheet")
             for t in [t for t in panel if t.get("domain", "coding") == domain][:2]]
    texts = ["", *(s["skill"] for s in checkpoint["skills"][1].values())]
    group = {digest({"task_hash": digest(t), "skill": study.learning.text_hash(s),
                     "phase": "final", "history": 1}) for t in tasks for s in texts}
    retained_keys = {r["identity"]["key"] for k, r in solves.items() if k not in dropped}
    require({r["identity"]["key"] for r in dropped.values()} == group - retained_keys,
            "Tail differs from all newly admitted keys in checkpoint r1/h1")
    final = study.read(source / "final_rows.json")
    protected_calls = {h for r in final["rows"] for h in r["request_hashes"]}
    require(len(final["rows"]) == 216 and not tail.intersection(protected_calls),
            "Recovery must not alter any main final trajectory")
    execution_ids = {i for r in dropped.values() for i in r["execution_ids"]}
    require(not execution_ids.intersection(i for k, r in solves.items() if k not in dropped
                                         for i in r["execution_ids"]), "Shared execution cannot be excluded")
    for intent in (source / "runtime").rglob("execution_intents/*.json"):
        receipt = intent.parent.parent / "executions" / intent.name
        require(receipt.is_file(), "Unresolved native execution")
        require(study.read(receipt)["intent_hash"] == study.read(intent)["record_hash"],
                "Native execution provenance mismatch")
    for directory in ("results.json", "checkpoint_rows.json"):
        require(not (source / directory).exists(), "Only the paused unfinished diagnostic is supported")
    roots = {"protocol.json", "private_panel.json", "task_preflight.json", "source_snapshot.json",
             "final_frozen.json", "final_rows.json"}
    dirs = {"api", "runtime", "learning", "learning_intents", "validator", "checkpoints"}
    keep = set()
    for name in manifest:
        parts = Path(name).parts
        if parts[0] in dirs or name in roots:
            keep.add(name)
        elif parts[0] == "events" and int(Path(name).stem) <= LAST_EVENT:
            keep.add(name)
        else:
            require(parts[0] == "events" or name == "PAUSE" or name.endswith((".log", ".lock")),
                    f"Unreviewed source path: {name}")
        if (len(parts) == 3 and parts[:2] in {
                ("api", "calls"), ("api", "budget_reservations"),
                ("runtime", "request_intents"), ("runtime", "stages")}
                and Path(name).stem in tail):
            keep.discard(name)
        if (len(parts) == 3 and parts[:2] in {("runtime", "executions"), ("runtime", "execution_intents")}
                and Path(name).stem in execution_ids):
            keep.discard(name)
        if parts[:2] == ("runtime", "solves") and Path(name).stem in dropped:
            keep.discard(name)
        if len(parts) == 4 and parts[:2] == ("api", "pacing") and parts[2] in {"admissions", "attempts", "cooldowns"}:
            if int(Path(name).stem) in selected["excluded_sequences"]:
                keep.discard(name)
    return {**selected, "excluded_solver_ids": sorted(dropped),
            "excluded_solver_keys": sorted(r["identity"]["key"] for r in dropped.values()),
            "excluded_execution_ids": sorted(execution_ids),
            "retained_files": sorted(keep), "excluded_files": sorted(set(manifest) - keep),
            "original_terminal_errors": sum(not c["ok"] for c in calls.values()),
            "inherited_terminal_errors": sum(not calls[h]["ok"] for h in selected["retained_calls"])}


def verify_frontier(root, excluded_keys):
    """Replay clean evidence with network and native execution disabled."""
    from skillopt.coevolution_v15 import runtime
    from skillopt.coevolution_v16 import research

    class ReachedFrontier(Exception):
        pass

    def forbidden(*args, **kwargs):
        raise AssertionError("Recovery audit must not execute artifacts or call a model/network")

    original = runtime.solve

    def solve(*args, **kwargs):
        if kwargs["key"] in excluded_keys:
            raise ReachedFrontier()
        return original(*args, **kwargs)

    before = inventory(root)
    runner = study.Study(REPO, root, design="pilot", api_factory=forbidden)
    runner.complete = True  # Read-only mode; every clean receipt must already exist.
    with patch.object(runtime, "solve", solve), patch.object(runtime.legacy, "evaluate", forbidden), \
            patch.object(research, "fetch_sources", forbidden), patch.object(study.OfflineAPI, "call", forbidden):
        try:
            runner.run()
        except ReachedFrontier:
            pass
        else:
            raise ValueError("Clean replay did not reach the expected checkpoint frontier")
    require(inventory(root) == before, "Read-only frontier replay changed evidence")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Copy only; never launch API work")
    args = parser.parse_args(argv)
    source, target = (study.safe_root(REPO, p) for p in (args.source, args.output))
    parent = REPO / "outputs/coevolution_v16"
    require(source.parent == target.parent == parent and source != target and not target.exists(),
            "Require existing source and a fresh sibling output, without merging")
    require(source.name == "pilot_20260915_a" and (source / "PAUSE").exists(), "Exact paused pilot required")
    with ExitStack() as stack:
        for name in ("supervisor.lock", ".run.lock", ".audit.lock"):
            handle = stack.enter_context((source / name).open("rb"))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = inventory(source)
        protocol = study.read(source / "protocol.json")
        require(study.source_hashes(REPO) == protocol["source_hashes"], "Frozen source drift")
        event = study.read(source / "events" / f"{LAST_EVENT:06d}.json")
        require(event["time_utc"] == BOUNDARY and event["stage"] == "frozen_checkpoint_r1_h0"
                and event["closed_trajectories"] == event["admitted_total"] == 4,
                "Clean previous checkpoint batch is not complete")
        ledger = closed_ledger(source, protocol["max_calls"])
        selection = partition(source, manifest, sleep_wall=datetime.fromisoformat(SLEEP).timestamp(),
                              boundary_wall=datetime.fromisoformat(BOUNDARY).timestamp())
        # Even replacing every checkpoint position stays under the original gross cap.
        future_upper = (protocol["rounds"] - 1) * protocol["histories"] * 4 * len(protocol["policies"]) * 2
        require(ledger["cached_logical_calls"] + future_upper <= protocol["max_calls"],
                "Recovery could exceed the original total gross call cap")
        plan = seal({"version": VERSION, "source": str(source), "target": str(target),
            "sleep_start": SLEEP, "clean_batch_end": BOUNDARY, "batch": "checkpoint_r1_h1",
            "policy": "exclude_all_new_keys_in_batch_retain_clean_shared_aliases",
            "source_manifest": manifest, "source_manifest_hash": digest(manifest),
            "source_protocol_hash": protocol["record_hash"], "recovery_script_hash": sha(__file__),
            "old_request_epoch": digest({"root": str(source), "manifest": digest(manifest)}),
            "new_request_epoch": digest({"root": str(target), "source": digest(manifest), "version": VERSION}),
            "source_run_untouched": True, "score_blind_selection": True,
            "user_authorized_posthoc_infrastructure_exclusion": True,
            "inherited_evidence_not_independent_replication": True,
            "cost_not_refunded": True, "gross_cost_formula": "source_615_plus_new_fork_requests",
            "gross_call_upper_bound": ledger["cached_logical_calls"] + future_upper,
            "original_ledger": ledger, **selection})
        require(inventory(source) == manifest, "Source changed during planning")
        if args.apply:
            target.mkdir(exist_ok=False)
            for relative in selection["retained_files"]:
                dst = target / relative
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative, dst, follow_symlinks=False)
                require(sha(dst) == manifest[relative], "Copy bytes differ")
            require(inventory(target) == {p: manifest[p] for p in selection["retained_files"]},
                    "Copied inventory differs")
            inherited = closed_ledger(target, protocol["max_calls"])
            require(inherited["cached_logical_calls"] == 607, "Inherited request count differs")
            write_immutable_json(target / "recovery_manifest.json", plan)
            verify_frontier(target, set(selection["excluded_solver_keys"]))
            write_immutable_json(target / "recovery_verification.json", seal({"version": VERSION,
                "manifest_hash": plan["record_hash"], "zero_api_zero_execution_frontier_replay": True,
                "inherited_calls": 607, "inherited_http_attempts": 619,
                "main_final_byte_identical": sha(target / "final_rows.json") == manifest["final_rows.json"]}))
            (target / "PAUSE").touch(exist_ok=False)
            require(inventory(source) == manifest, "Source evidence changed during recovery")
        print(json.dumps({"applied": args.apply, "target": str(target), "inherited_calls": 607,
            "excluded_calls": len(selection["excluded_calls"]), "excluded_trajectories": 4,
            "affected_calls": len(selection["overlap_calls"]), "main_final_preserved": True,
            "original_errors": selection["original_terminal_errors"],
            "inherited_errors": selection["inherited_terminal_errors"],
            "model_api_calls": 0, "native_executions": 0, "plan_hash": plan["record_hash"]}, indent=2))


if __name__ == "__main__":
    main()
