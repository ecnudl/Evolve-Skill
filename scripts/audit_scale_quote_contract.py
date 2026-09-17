"""Data-dependent posthoc quote-contract audit; never rewrites original scores.

Candidate support is exactly all 364 strings of length 0..5 over a/comma/quote.
Additional explicit contract examples cross-check ONLY the frozen reference.
This is not an independent benchmark or a replacement for the frozen oracle.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

VERSION = "quote-contract-finite-language-posthoc-v1"
TASK_ID = "authored-v1-stateful_parsing-quoted_record"
ALPHABET = ("a", ",", '"')
MAX_LENGTH = 5
ARMS = ("noskill", "generic_control", "mechanism_skill")
REFERENCE_EXAMPLES = (
    ("", [""], None),
    ("a,", ["a", ""], None),
    ('"a,b",c', ["a,b", "c"], None),
    ('""', [""], None),
    ('""""', ['"'], None),
    ('"a""b"', ['a"b'], None),
    ('a"b"', None, "ValueError"),
    ('"a', None, "ValueError"),
    ('"', None, "ValueError"),
    ('"a"b', None, "ValueError"),
    (" a , b ", [" a ", " b "], None),
    ('" a "', [" a "], None),
)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def words() -> list[str]:
    return ["".join(chars) for length in range(MAX_LENGTH + 1) for chars in itertools.product(ALPHABET, repeat=length)]


def validate_output(source: Path, output: Path) -> None:
    if output == source or source in output.parents:
        raise ValueError("audit output must be outside the original run")
    if output.suffix != ".json":
        raise ValueError("audit output must be a new JSON file")
    if output.exists():
        raise FileExistsError("audit output already exists; refusing overwrite")


def verify_source(source: Path) -> tuple[dict, dict]:
    """Require completed source and unchanged borrowed task/execution code."""
    if not (source / "results.json").is_file():
        raise RuntimeError("source results must be complete before posthoc audit")
    result = read(source / "results.json")
    if result.get("status") != "complete":
        raise RuntimeError("source results must be complete before posthoc audit")
    protocol = read(source / "protocol.json")
    if result.get("protocol_hash") != digest(protocol):
        raise ValueError("source result/protocol identity mismatch")
    snapshot = read(source / "source_snapshot.json")
    for name in ("skillopt/validator_pilot/tasks.py", "skillopt/validator_scale_tasks.py"):
        expected = protocol["source_hashes"][name]
        if digest(snapshot[name]) != expected or digest((REPO / name).read_text()) != expected:
            raise ValueError("frozen task or sandbox implementation changed")
    return protocol, result


def sandbox_observations(code: str, texts: list[str]) -> list[dict]:
    """Reuse the fail-closed sandbox; expected answers are never in its payload."""
    from skillopt.validator_pilot import tasks as oracle

    oracle.validate_code(code)
    payload = {
        "code": code,
        "cases": [{"setup": "data=" + repr({"text": text}), "expr": "solve(data)"} for text in texts],
    }
    returncode, stdout, _ = oracle._run_payload(payload)
    if returncode != 0:
        raise RuntimeError("sandbox/reference execution failed")
    rows = json.loads(stdout)["rows"]
    if len(rows) != len(texts) or any(
        not {"actual", "exception"}.issubset(row) or set(row) - {"actual", "exception", "message"} for row in rows
    ):
        raise ValueError("sandbox result cardinality or schema mismatch")
    return rows


def build_expected_cases(reference: str) -> tuple[list[dict], list[dict]]:
    """Reference-derived oracle with separately stated contract sanity examples."""
    observed = sandbox_observations(reference, [example[0] for example in REFERENCE_EXAMPLES])
    checks = []
    for (text, expected, exception), row in zip(REFERENCE_EXAMPLES, observed):
        matches = row["exception"] == exception and (exception is not None or row["actual"] == expected)
        checks.append(
            {
                "text": text,
                "expected": expected,
                "expected_exception": exception,
                "actual": row["actual"],
                "exception": row["exception"],
                "passed": matches,
                "reference_only": True,
            }
        )
    if not all(check["passed"] for check in checks):
        raise ValueError("frozen reference contradicts an explicit contract example")
    language = words()
    outcomes = sandbox_observations(reference, language)
    cases = []
    for index, (text, row) in enumerate(zip(language, outcomes)):
        if row["exception"] not in (None, "ValueError"):
            raise ValueError("reference has an unexpected finite-language exception")
        if row["exception"] is None and not isinstance(row["actual"], list):
            raise ValueError("reference output violates list interface")
        cases.append(
            {
                "label": f"finite-case-{index:03}",
                "setup": "data=" + repr({"text": text}),
                "expr": "solve(data)",
                "expected": row["actual"],
                "exception": row["exception"],
                "dimension": "requested_behavior",
                "public": False,
            }
        )
    return cases, checks


def audit_artifact(task, artifact: dict, cases: list[dict]) -> dict:
    from skillopt.validator_pilot import tasks as oracle

    original_hard = artifact["original_hard"]
    code = artifact["code"]
    if code is None:
        return {
            **artifact,
            "code": None,
            "finite_language_pass": None,
            "status": "no_frozen_extracted_code",
            "counterexamples": [],
        }
    finite_task = oracle.Task.from_dict({**task.to_dict(), "public_cases": [], "private_cases": cases})
    result = oracle.evaluate(finite_task, {"code": code})
    hard = result["hard"] if result["execution_ok"] else None
    inputs = {case["label"]: text for case, text in zip(cases, words())}
    failures = [
        {
            "label": item["label"],
            "text": inputs[item["label"]],
            "expected": item["expected"],
            "expected_exception": item["expected_exception"],
            "actual": item["actual"],
            "exception": item["exception"],
        }
        for item in result.get("private_diagnostics", [])
    ]
    return {
        **{key: value for key, value in artifact.items() if key != "code"},
        "code_sha256": sha256(code),
        "finite_language_pass": hard,
        "status": "completed" if result["execution_ok"] else "infrastructure_or_resource_unavailable",
        "error_category": result.get("error_category"),
        "finite_cases_passed": result.get("passed_tests", 0),
        "finite_cases_total": len(cases),
        "original_pass_but_posthoc_failure": original_hard is True and hard is False,
        "counterexamples": failures,
    }


def load_artifacts(source: Path, task) -> list[dict]:
    from skillopt.validator_scale_tasks import controlled_fixtures

    artifacts = []
    for arm in ARMS:
        for repeat in range(4):
            path = source / "targets" / f"{TASK_ID}__{arm}__{repeat}.json"
            record = read(path)
            checksum = record.pop("record_sha256", None)
            if checksum != digest(record):
                raise ValueError("frozen target record integrity mismatch")
            if (
                record["id"] != TASK_ID
                or record["arm"] != arm
                or record["repeat"] != repeat
                or record["split"] != "holdout"
                or record["origin"] != "natural"
            ):
                raise ValueError("unexpected frozen quote artifact identity")
            artifacts.append(
                {
                    "origin": "natural",
                    "arm": arm,
                    "repeat": repeat,
                    "original_hard": record["hard"],
                    "code": record.get("code"),
                    "source_path": str(path.relative_to(source)),
                    "source_record_hash": checksum,
                    "request_hash": record["request_hash"],
                    "response_sha256": sha256(record["response"]),
                }
            )
    checks = {row["kind"]: row for row in read(source / "oracle_selftest.json") if row["id"] == TASK_ID}
    for fixture in controlled_fixtures(task):
        kind = fixture["kind"]
        if kind not in checks:
            raise ValueError("frozen controlled selfcheck missing")
        artifacts.append(
            {
                "origin": "controlled",
                "arm": kind,
                "repeat": None,
                "original_hard": checks[kind]["hard"],
                "code": json.loads(fixture["response"])["code"],
                "source_record_hash": digest(fixture),
                "response_sha256": sha256(fixture["response"]),
                "source_path": "frozen task source + oracle_selftest.json",
            }
        )
    return artifacts


def summarize(rows: list[dict]) -> dict:
    by_arm = {}
    for arm in ARMS:
        selected = [row for row in rows if row["origin"] == "natural" and row["arm"] == arm]
        by_arm[arm] = {
            "artifacts": len(selected),
            "original_hard_pass": sum(row["original_hard"] is True for row in selected),
            "finite_language_pass": sum(row["finite_language_pass"] is True for row in selected),
            "finite_language_fail": sum(row["finite_language_pass"] is False for row in selected),
            "unavailable": sum(row["finite_language_pass"] is None for row in selected),
            "original_pass_but_posthoc_failure": sum(
                row["original_hard"] is True and row["finite_language_pass"] is False for row in selected
            ),
        }
    return by_arm


def run(source: Path, output: Path) -> dict:
    source, output = source.resolve(), output.resolve()
    validate_output(source, output)
    protocol, source_result = verify_source(source)
    manifest = read(source / "tasks_private.json")
    if digest(manifest) != protocol["task_manifest_hash"]:
        raise ValueError("frozen task manifest identity mismatch")
    from skillopt.validator_pilot import tasks as oracle
    from skillopt.validator_pilot.api import write_immutable_json

    task = oracle.Task.from_dict(manifest[TASK_ID])
    if not oracle.sandbox_probe().get("ok"):
        raise RuntimeError("sandbox unavailable; refusing candidate execution")
    cases, reference_checks = build_expected_cases(task.reference_code)
    artifacts = load_artifacts(source, task)
    if len(artifacts) != 15:
        raise ValueError("audit must contain twelve natural and three controlled artifacts")
    audited = [audit_artifact(task, artifact, cases) for artifact in artifacts]
    report = {
        "version": VERSION,
        "status": "complete",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "source_protocol_hash": digest(protocol),
        "source_results_hash": digest(source_result),
        "source_task_hash": digest(manifest[TASK_ID]),
        "script_sha256": sha256(Path(__file__).read_text()),
        "source_labels_unchanged": True,
        "task_id": TASK_ID,
        "alphabet": list(ALPHABET),
        "max_length": MAX_LENGTH,
        "candidate_language_size": len(cases),
        "input_hash": digest(words()),
        "reference_sha256": sha256(task.reference_code),
        "expected_cases_hash": digest(cases),
        "reference_only_contract_crosschecks": reference_checks,
        "finite_language_oracle": "expected outputs/exceptions from frozen reference in existing sandbox",
        "finite_expected_outcome_counts": dict(Counter(case["exception"] or "success" for case in cases)),
        "finite_language_inputs": words(),
        "summary_by_arm": summarize(audited),
        "artifacts": audited,
        "model_calls": 0,
        "new_target_generations": 0,
        "candidate_execution_mode": "existing fail-closed macOS sandbox; no expected labels in child payload",
        "limitations": [
            "Posthoc, data-dependent oracle-gap discovery; NOT an independent benchmark or confirmation.",
            "Original frozen labels, aggregate scores and all source-run files remain unchanged.",
            "Exactly length<=5 over a/comma/quote for candidates; no spaces, b, or longer-string coverage.",
            "The strip-spaces preservation mutant can pass this finite language despite failing the original oracle.",
            "Additional contract crosschecks test only the frozen reference, never expand candidate input support.",
            "Reference-derived agreement is not a proof of full contract correctness or independent oracle validity.",
            "Only quoted_record audited; other task families and possible oracle gaps remain unexamined.",
        ],
    }
    write_immutable_json(output, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source, args.output)
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "candidate_language_size": report["candidate_language_size"],
                "summary_by_arm": report["summary_by_arm"],
                "posthoc_not_independent": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
