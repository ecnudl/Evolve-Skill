"""Opt-in literal public-example coverage correction, not a hidden oracle.

The frozen natural_data extractor misses earlier adjacent doctest comparisons:
its expected-literal suffix also contains the next >>> operator. Do not change
historical task hashes or silently apply this adapter to an existing protocol.
"""
import ast
import re

from skillopt.validator_pilot.api import digest

from . import natural_data as legacy
from .checks import PublicCase

VERSION = "adjacent-public-comparison-examples-v2"


def public_examples(row):
    """Keep the legacy cases; add only whole-line explicit literal comparisons.

    No exec/eval, reference, hidden test or expected-value generation is used.
    Python AST parsing of text does not execute the submitted task program.
    """
    original = legacy.public_examples(row)
    prompt, entry = row["prompt"], row["entry_point"]
    function = next(n for n in ast.parse(prompt).body if isinstance(n, ast.FunctionDef) and n.name == entry)
    doc = ast.get_docstring(function, clean=False) or ""
    found = list(original)
    seen = {digest([case.arguments_json, case.expected_json]) for case in found}
    for line in doc.splitlines():
        match = re.fullmatch(r"\s*>>>\s+(.+)", line)
        if not match:
            continue
        try:
            node = ast.parse(match[1], mode="eval").body
            if not (isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq)):
                continue
            arguments = legacy._call(ast.unparse(node.left), entry)
            expected = legacy._literal(node.comparators[0])
            arguments_json, expected_json = legacy._json(arguments), legacy._json(expected)
            identity = digest([arguments_json, expected_json])
            if identity in seen:
                continue
            case = PublicCase("public-comparison-" + str(len(found)), arguments_json, prompt,
                              ("requested_behavior",), expected_json=expected_json)
            # Apply the same bounded JSON validation as the legacy extractor.
            legacy.json_value(arguments_json)
            legacy.json_value(expected_json)
            found.append(case)
            seen.add(identity)
        except (ValueError, SyntaxError, TypeError):
            continue
    return tuple(found[:16])


def missing_examples(row):
    existing = {digest([c.arguments_json, c.expected_json]) for c in legacy.public_examples(row)}
    return tuple(c for c in public_examples(row) if digest([c.arguments_json, c.expected_json]) not in existing)


def main():
    """Recheck only newly recovered DEVELOPMENT examples, without any model call."""
    import argparse
    import hashlib
    import json
    from collections import Counter
    from pathlib import Path

    from skillopt.coevolution_v5.core import seal
    from .natural_study import ExecutorPool, _write
    from .natural_verifier_replay import load_frozen
    from .task_probes import execute_probes, parse_probes

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--remote-repo", required=True)
    args = parser.parse_args()
    manifest, protocol, _, pool, _ = load_frozen(args.repo, args.source)
    source_rows, _ = legacy.download(args.repo)
    public_rows = {r["task_id"]: {k: r[k] for k in ("prompt", "entry_point")} for r in source_rows}
    executor = ExecutorPool(args.remote_repo, 1)
    try:
        declaration = seal({"version": VERSION, "source_protocol_hash": protocol["record_hash"],
                            "manifest_hash": manifest["record_hash"], "partition": "development",
                            "executor": executor.identity, "transport": executor.transport_identity,
                            "source_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                            "effect_claim": "posthoc_public_extractor_bug_diagnostic_not_method_efficacy",
                            "old_scores_unchanged": True, "new_model_calls": 0})
        _write(args.output / "protocol.json", declaration)
        results, inventory = [], {}
        for group in pool["development"].values():
            task = group[0]["task"]
            cases = missing_examples(public_rows[task.contract.original_task_id])
            if not cases:
                continue
            inventory[task.contract.original_task_id] = len(cases)
            for position in group:
                artifact = position["artifact"]
                if artifact is None:
                    continue
                reports = []
                for start in range(0, len(cases), 2):
                    probes = [{"kind": "expected", "calls": [json.loads(c.arguments_json)],
                        "expected": json.loads(c.expected_json), "obligation_id": "requested_behavior",
                        "contract_quote": c.contract_quote,
                        "rationale": "Literal published example recovered by the deterministic parser; not Research."}
                        for c in cases[start:start + 2]]
                    reports.append(execute_probes(task, artifact, parse_probes({"probes": probes}, task),
                                                  executor, args.output / "execution"))
                results.append({"task_id": task.contract.original_task_id, "repeat": artifact.repeat,
                    "condition": artifact.condition, "artifact_hash": artifact.content_hash,
                    "old_public_status": position["host"]["public_status"],
                    "old_audit_status": position["host"]["status"],
                    "status": "mismatch" if any(r["status"] == "mismatch" for r in reports) else
                              "unknown" if any(r["status"] == "unknown" for r in reports) else "consistent",
                    "report_hashes": [r["record_hash"] for r in reports]})
            print(json.dumps({"task": task.contract.original_task_id, "added_examples": len(cases)}), flush=True)
        result = seal({"protocol_hash": declaration["record_hash"], "inventory": inventory, "rows": results,
                       "counts": dict(Counter(r["status"] for r in results)),
                       "new_public_failures": sum(r["old_public_status"] == "pass" and r["status"] == "mismatch" for r in results),
                       "new_model_calls": 0, "scores_rewritten": False, "deployment_authorized": False})
        _write(args.output / "results.json", result)
        print(json.dumps({k: result[k] for k in ("inventory", "counts", "new_public_failures")}), flush=True)
    finally:
        executor.close()


if __name__ == "__main__":
    main()
