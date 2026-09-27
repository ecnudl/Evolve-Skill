"""Opt-in literal public-example coverage correction, not a hidden oracle.

The frozen natural_data extractor misses earlier adjacent doctest comparisons:
its expected-literal suffix also contains the next >>> operator. Do not change
historical task hashes or silently apply this adapter to an existing protocol.
"""
import ast
import doctest
import re

from skillopt.validator_pilot.api import digest

from . import natural_data as legacy
from .checks import PublicCase

VERSION = "adjacent-public-comparison-examples-v2"
INVENTORY_VERSION = "public-doctest-coverage-inventory-v1"


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


def coverage_inventory(row):
    """Inventory explicit doctest blocks without executing code or consulting H.

    This opt-in report does not change ``public_examples`` or its 16-case cap.
    Counts cover explicit ``>>>`` blocks only, not every possible prose/inline
    example understood by the legacy extractor. One block is one candidate;
    duplicate literal cases remain visible. A different literal expected value
    for the same call is a public disagreement flag, not a claim about which
    answer is correct or a complete semantic-conflict detector.
    """
    prompt, entry = row["prompt"], row["entry_point"]
    function = next(n for n in ast.parse(prompt).body if isinstance(n, ast.FunctionDef) and n.name == entry)
    doc = ast.get_docstring(function, clean=False) or ""
    prompt_hash = digest(prompt)
    selected_cases = public_examples({"prompt": prompt, "entry_point": entry})
    selected = {digest([c.arguments_json, c.expected_json]) for c in selected_cases}
    matches = list(re.finditer(r"(?m)^[ \t]*>>>[^\n]*$", doc))
    doc_lines, prompt_lines = doc.splitlines(), prompt.splitlines()
    doc_node = function.body[0].value if doc else None
    records, seen, by_call = [], {}, {}
    for index, match in enumerate(matches):
        line = doc[:match.start()].count("\n") + 1
        quote = doc_lines[line - 1]
        proposed_prompt_line = doc_node.lineno + line - 1
        # Escape sequences inside the literal may add logical docstring lines.
        # Do not invent a physical source location if it cannot be matched.
        prompt_line = proposed_prompt_line if (
            1 <= proposed_prompt_line <= len(prompt_lines)
            and prompt_lines[proposed_prompt_line - 1].strip() == quote.strip()
        ) else None
        end = matches[index + 1].start() if index + 1 < len(matches) else len(doc)
        block = doc[match.start():end]
        record = {
            "candidate_id": "public-example-" + digest([INVENTORY_VERSION, prompt_hash, entry, line, quote]),
            "docstring_line_1based": line, "prompt_line_1based": prompt_line,
            "source_quote": quote, "source_block": block,
            "status": "unsupported", "reason": None,
            "arguments_json": None, "expected_json": None, "case_hash": None,
            "duplicate_of": None, "selected_by_public_extractor": False,
        }
        try:
            examples = doctest.DocTestParser().get_examples(block)
            if len(examples) != 1:
                raise ValueError("unsupported_doctest_structure")
            example = examples[0]
            node = ast.parse(example.source.strip(), mode="eval").body
            if isinstance(node, ast.Compare):
                if not (len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq)):
                    raise ValueError("unsupported_comparison_relation")
                if example.want.strip() not in ("", "True"):
                    raise ValueError("comparison_has_non_true_output")
                # The correction currently recognizes only whole-line comparisons.
                if len(example.source.strip().splitlines()) != 1:
                    raise ValueError("unsupported_multiline_comparison")
                arguments = legacy._call(ast.unparse(node.left), entry)
                expected = legacy._literal(node.comparators[0])
                representation = "literal_equality"
            else:
                arguments = legacy._call(example.source, entry)
                expected = legacy._literal(ast.parse(example.want.strip(), mode="eval").body)
                representation = "literal_doctest_output"
            arguments_json, expected_json = legacy._json(arguments), legacy._json(expected)
            legacy.json_value(arguments_json)
            legacy.json_value(expected_json)
            case_hash = digest([arguments_json, expected_json])
            record.update(status="parsed", representation=representation,
                          arguments_json=arguments_json, expected_json=expected_json, case_hash=case_hash,
                          duplicate_of=seen.get(case_hash), selected_by_public_extractor=case_hash in selected)
            seen.setdefault(case_hash, record["candidate_id"])
            by_call.setdefault(arguments_json, {}).setdefault(expected_json, []).append(record["candidate_id"])
        except (ValueError, SyntaxError, TypeError) as error:
            record["reason"] = type(error).__name__ + ": " + str(error)
        records.append(record)
    conflicts = [{
        "kind": "same_call_different_literal_expected",
        "arguments_json": arguments_json,
        "alternatives": [{"expected_json": expected_json, "candidate_ids": identifiers}
                         for expected_json, identifiers in sorted(alternatives.items())],
    } for arguments_json, alternatives in sorted(by_call.items()) if len(alternatives) > 1]
    parsed = [r for r in records if r["status"] == "parsed"]
    parsed_hashes = {r["case_hash"] for r in parsed}
    return {
        "version": INVENTORY_VERSION, "prompt_hash": prompt_hash, "entry_point": entry,
        "scope": "explicit_doctest_blocks_only",
        "limitations": [
            "Inline prose equations and other example formats are outside this inventory's denominator.",
            "Same-call literal disagreements are flags; no hidden/reference truth or semantic adjudication is used.",
            "A supported example absent from the extractor may be omitted by parsing or the cap; causes are not inferred.",
            "Counts describe extraction coverage, not executed checks or task correctness.",
        ],
        "candidate_count": len(records), "parsed_supported_count": len(parsed),
        "unique_supported_count": len(parsed_hashes),
        "duplicate_count": sum(r["duplicate_of"] is not None for r in parsed),
        "unsupported_count": len(records) - len(parsed),
        "selected_supported_count": len(parsed_hashes & selected),
        "unselected_supported_count": len(parsed_hashes - selected),
        "selected_public_case_count": len(selected_cases),
        "selected_outside_inventory_count": len(selected - parsed_hashes),
        "public_case_limit": 16, "extractor_at_limit": len(selected_cases) == 16,
        "cap_truncation_minimum_count": max(0, len(parsed_hashes) - 16),
        "conflict_call_count": len(conflicts), "conflicts": conflicts,
        "candidates": records, "hidden_or_reference_accessed": False,
        "benchmark_code_executed": False, "historical_cases_changed": False,
    }


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
