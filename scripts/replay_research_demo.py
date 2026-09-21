"""Read and verify published evidence; never execute code or contact a service.

This is a recorded-result replay, not a rerun of model generation or benchmark
tests. File hashes provide consistency, not independent execution authenticity.
Only the Python standard library is required.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from collections import Counter
from pathlib import Path, PurePosixPath

DEFAULT_ROOT = Path(__file__).resolve().parents[1] / "examples/research_evidence"
CASE_NAMES = ("power_boundary", "word_boundary", "public_check_blindspot", "audit_disagreement")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def read_bytes(root, relative):
    require(isinstance(relative, str) and bool(relative), "Expected relative file path")
    parts = PurePosixPath(relative).parts
    require(not relative.startswith("/") and "\\" not in relative
            and all(p not in {".", ".."} for p in parts), "Unsafe package path")
    path = root
    for part in parts:
        path = path / part
        require(not path.is_symlink(), "Package symlinks are not allowed")
    require(path.is_file() and path.stat().st_size <= 2_000_000, "Missing or oversized package file")
    return path.read_bytes()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError("Nonfinite JSON number")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def inspect_package(root=DEFAULT_ROOT):
    root = Path(root).resolve()
    manifest = parse(read_bytes(root, "manifest.json"))
    require(manifest["schema"] == "public_research_evidence_v1", "Unsupported evidence package")
    contents = {}
    require(1 <= len(manifest["files"]) <= 50, "Invalid file inventory")
    for name, identity in manifest["files"].items():
        raw = read_bytes(root, name)
        require(len(raw) == identity["bytes"] and hashlib.sha256(raw).hexdigest() == identity["sha256"],
                "Package checksum mismatch: " + name)
        contents[name] = raw

    def load(name):
        require(name in contents, "Required file absent from manifest: " + name)
        return parse(contents[name])

    update = load("skill_update/update.json")
    for role in ("parent", "candidate"):
        name = update[role + "_file"]
        require(name in contents, "Skill text absent from manifest")
        raw = contents[name]
        if not update["original_text_had_trailing_newline"][role]:
            require(raw.endswith(b"\n"), "Missing documented display newline")
            raw = raw[:-1]
        require(hashlib.sha256(raw).hexdigest() == update[role + "_original_text_sha256"],
                "Skill text differs from recorded original")

    evidence = load("single_round_final_outcomes.json")
    rows = evidence["rows"]
    require(evidence["partition"] == "final" and evidence["not_training_or_validation_input"] is True,
            "Final evidence cannot be relabeled as training")
    require(len(rows) == evidence["exported_unique_condition_rows"], "Final row count mismatch")
    conditions = {"no_skill", "parent", "candidate"}
    keys = {(r["task_id"], r["repeat"], r["condition"]) for r in rows}
    tasks = {r["task_id"] for r in rows}
    require(len(keys) == len(rows), "Duplicate final position")
    require(len(tasks) == evidence["independent_task_ids"], "Task count mismatch")
    expected = {(task, repeat, condition) for task in tasks
                for repeat in range(evidence["repeats"]) for condition in conditions}
    require(keys == expected, "Incomplete or extra final positions")
    require(all(r["status"] in {"pass", "fail", "unknown"} for r in rows), "Invalid final status")
    rates = {}
    for condition in sorted(conditions):
        selected = [r for r in rows if r["condition"] == condition]
        counts = Counter(r["status"] for r in selected)
        rates[condition] = {s: counts[s] for s in ("pass", "fail", "unknown")}
        rates[condition].update(positions=len(selected), all_attempt_success=counts["pass"] / len(selected))
    lookup = {(r["task_id"], r["repeat"], r["condition"]): r["status"] for r in rows}
    paired = {}
    for baseline in ("no_skill", "parent"):
        count = Counter()
        for task in sorted(tasks):
            for repeat in range(evidence["repeats"]):
                before, after = (lookup[task, repeat, condition] for condition in (baseline, "candidate"))
                result = ("unknown" if "unknown" in (before, after) else
                          "tie" if before == after else "win" if after == "pass" else "loss")
                count[result] += 1
        paired["candidate_vs_" + baseline] = {s: count[s] for s in ("win", "loss", "tie", "unknown")}

    cases = []
    for name in CASE_NAMES:
        case = load("cases/" + name + ".json")
        require(case["partition"] == "development" and case["research_credit"] is False,
                "Illustrative diagnostics must remain development evidence without Research credit")
        artifacts = {a["condition"]: a for a in case["artifacts"]}
        require(len(artifacts) == len(case["artifacts"]) and set(artifacts) == {"no_skill", "current"},
                "Expected one artifact per paired condition")
        for artifact in artifacts.values():
            require(hashlib.sha256(artifact["solution_py"].encode()).hexdigest() == artifact["solution_sha256"],
                    "Code payload checksum mismatch")
        observations = []
        for item in case["diagnostics"]:
            e = item["execution"]
            require(item["used_by_updater"] is False and item["included_in_original_score"] is False,
                    "Post-hoc diagnostics cannot be relabeled as original feedback")
            require(e["status"] == "observed" and e["cleanup_confirmed"] is True,
                    "Demo requires observed, cleaned-up execution")
            if item["condition"] in artifacts:
                a = artifacts[item["condition"]]
                require(item["artifact_record_hash"] == a["source"]["original_record_hash"],
                        "Diagnostic artifact mismatch")
                source = {"solution.py": a["solution_py"]}
                call = {"module": "solution", "function": case["function"],
                        "args": e["before_args"], "kwargs": e["before_kwargs"]}
                require(e["source_hash"] == digest(source) and e["call_hash"] == digest(call)
                        and e["input_hash"] == digest({"files": source, **call}),
                        "Diagnostic code/call binding mismatch")
            # Strict JSON comparison, so False and 0 cannot silently compare equal.
            require(item["matches_public_contract_case"] == (digest(e["actual"]) == digest(item["public_expected"])),
                    "Recorded diagnostic comparison mismatch")
            observations.append({"condition": item["condition"], "args": e["before_args"],
                                 "actual": e["actual"], "public_expected": item["public_expected"],
                                 "posthoc": True})
        cases.append({"id": name, "task_id": case["task_id"],
                      "public_status": {k: v["public_status"] for k, v in artifacts.items()},
                      "recorded_diagnostics": observations,
                      "new_probe_execution_claimed": False})
    return {"kind": "recorded_evidence_replay_not_new_execution", "verified_files": len(contents),
            "model_calls": 0, "executed_artifact_code": False, "method_effect_established": False,
            "final_tasks": len(tasks), "final_positions": len(rows), "rates": rates,
            "paired": paired, "cases": cases, "raw_source_authenticity_verified": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", help="Print machine-readable replay summary")
    output.add_argument("--show-skill-diff", action="store_true", help="Print stored parent/candidate text diff")
    args = parser.parse_args(argv)
    try:
        result = inspect_package(args.root)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, "Evidence replay refused: " + str(exc) + "\n")
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("Recorded evidence replay only: no API, no generated-code execution, no new accuracy estimate.")
        print(f"Verified {result['verified_files']} files; {result['final_tasks']} tasks, {result['final_positions']} final positions.")
        for condition, row in result["rates"].items():
            print(f"{condition}: {row['pass']}/{row['positions']} pass; {row['fail']} fail; {row['unknown']} unknown")
        for case in result["cases"]:
            print(f"\n{case['task_id']} / {case['id']}: public={case['public_status']}")
            for observation in case["recorded_diagnostics"]:
                print("  " + json.dumps(observation, ensure_ascii=False))
    if args.show_skill_diff:
        root = args.root.resolve()
        before = read_bytes(root, "skill_update/parent.md").decode().splitlines(keepends=True)
        after = read_bytes(root, "skill_update/candidate.md").decode().splitlines(keepends=True)
        print("".join(difflib.unified_diff(before, after, fromfile="parent", tofile="candidate")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
