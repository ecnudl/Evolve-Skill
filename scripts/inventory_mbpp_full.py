"""Static MBPP-full inventory only: no model, code execution, or data reservation.

Raw official data remain gitignored. Public output contains IDs, counts, hashes
and exclusion reasons, never task text, reference code, assertions or answers.
The optional download reads fixed public HTTPS assets without credentials.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from skillopt.coevolution_v5.core import seal, verify
from skillopt.coevolution_v11 import data as legacy
from skillopt.scope_evolution_v2.source_data import write_immutable_text
from skillopt.validator_pilot.api import digest, write_immutable_json

VERSION = "mbpp-full-static-readiness-inventory-v1"
REVISION = legacy.REVISION
URL = f"https://raw.githubusercontent.com/google-research/google-research/{REVISION}/mbpp/mbpp.jsonl"
DIRECTORY = Path("data/skill_validation/mbpp_full") / REVISION
MAX_BYTES = 16 * 1024 * 1024
MAX_HISTORY_BYTES = 64 * 1024 * 1024
DEFAULT_OUTPUT = Path("outputs/skill_validation/mbpp_full_inventory_20260923_a")


def _require(value, message):
    if not value:
        raise ValueError(message)


def _safe(path):
    path = Path(path).absolute()
    _require(".." not in path.parts and not any(p.is_symlink() for p in (path, *path.parents)), "Unsafe inventory path")
    return path


def parse_full(body, *, expected_count=None):
    """Strict JSONL parsing; no eval, import or execution of downloaded strings."""
    _require(type(body) is bytes and len(body) <= MAX_BYTES, "Bounded source bytes required")
    rows, seen = [], set()
    for number, line in enumerate(body.splitlines(keepends=True), 1):
        _require(bool(line.strip()) and len(line) <= 262144, "Blank or oversized source line")
        row = legacy._json(line.decode("utf-8"))
        _require(type(row) is dict, "Source row must be an object")
        identifier = row.get("task_id")
        legacy.source_split(identifier)
        _require(identifier not in seen, "Duplicate full-source task ID")
        seen.add(identifier)
        for field in ("text", "code"):
            _require(type(row.get(field)) is str and bool(row[field].strip()), "Missing source text/code")
        _require(type(row.get("test_setup_code")) is str, "Missing explicit setup field")
        _require(type(row.get("test_list")) is list and bool(row["test_list"]), "Missing standard native tests")
        for field in ("test_list", "challenge_test_list"):
            values = row.get(field, [])
            _require(type(values) is list and all(type(t) is str and bool(t.strip()) for t in values), "Invalid native test list")
        rows.append({"raw": row, "line_number": number, "line_sha256": hashlib.sha256(line).hexdigest(),
                     "source_row_hash": digest(row)})
    _require(bool(rows), "Empty full source")
    if expected_count is not None:
        _require(type(expected_count) is int and len(rows) == expected_count
                 and seen == set(range(1, expected_count + 1)), "Pinned source cardinality/ID range changed")
    return rows


def _fetch(url):
    _require(url == URL and url.startswith("https://"), "Only the pinned official full-source URL is allowed")
    import httpx
    with httpx.Client(trust_env=False, timeout=45, follow_redirects=False) as client:
        with client.stream("GET", url) as response:
            _require(response.status_code == 200, f"Official full source returned HTTP {response.status_code}")
            pieces, size = [], 0
            for piece in response.iter_bytes():
                size += len(piece)
                _require(size <= MAX_BYTES, "Official full source exceeds byte budget")
                pieces.append(piece)
            return b"".join(pieces)


def snapshot(repo, *, download=False, fetch=_fetch):
    """Verify cached sources; networking is impossible without explicit download."""
    repo = _safe(repo)
    sanitized = legacy.download_snapshot(repo) if download else legacy.load_snapshot(repo)
    root = _safe(repo / DIRECTORY)
    path = _safe(root / "mbpp.jsonl")
    receipt_path = _safe(root / "source_snapshot.json")
    if receipt_path.exists():
        receipt = verify(legacy._json(receipt_path.read_text()))
        _require(receipt["version"] == VERSION and receipt["revision"] == REVISION and receipt["url"] == URL
                 and receipt["sanitized_snapshot_hash"] == sanitized["record_hash"], "Source snapshot identity changed")
        _require(path.is_file() and path.stat().st_size <= MAX_BYTES, "Missing/oversized full source")
        body = path.read_bytes()
        _require(hashlib.sha256(body).hexdigest() == receipt["sha256"] and len(body) == receipt["bytes"], "Full-source bytes changed")
    else:
        _require(download, "Full source absent: use explicit --download to fetch the pinned official asset")
        body = fetch(URL)
        parse_full(body, expected_count=974)
        write_immutable_text(path, body.decode("utf-8"))
        receipt = seal({"version": VERSION, "revision": REVISION, "url": URL,
            "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "rows": 974,
            "sanitized_snapshot_hash": sanitized["record_hash"], "license": "CC-BY-4.0",
            "license_source": sanitized["files"]["dataset_card"],
            "upstream_readme": sanitized["files"]["upstream_readme"],
            "dataset_card_revision": legacy.CARD_REVISION})
        write_immutable_json(receipt_path, receipt)
    rows = parse_full(body, expected_count=974)
    sanitized_rows = legacy._source_rows(repo, sanitized)
    _require(len(sanitized_rows) == 427, "All 427 sanitized IDs must be known before inventory")
    return receipt, rows, sanitized_rows


def historical_inventories(repo):
    """Reuse explicit old MBPP inventories, not a claim of exhaustive exposure."""
    repo = _safe(repo)
    ids, sources = set(), []
    for path in sorted(_safe(repo / "outputs").rglob("exposure_inventory.json")):
        path = _safe(path)
        _require(path.stat().st_size <= MAX_HISTORY_BYTES, "Oversized historical inventory")
        raw = path.read_bytes()
        record = legacy._json(raw.decode("utf-8"))
        if record.get("dataset") != legacy.DATASET:
            continue
        verify(record)
        _require(record.get("version") in {"v10-mbpp-sanitized-data-v1-exposure", "v11-mbpp-sanitized-data-v1-exposure"},
                 "Unknown MBPP historical exposure schema")
        values = record.get("excluded_ids")
        _require(type(values) is list, "Missing historical exclusions")
        for value in values:
            legacy.source_split(value)
        ids.update(values)
        sources.append({"path": str(path.relative_to(repo)), "sha256": hashlib.sha256(raw).hexdigest(),
                        "record_hash": record["record_hash"], "excluded_ids": len(set(values))})
    return ids, sources


def lexical_families(full_rows, sanitized_rows):
    """Connected closure includes both original and sanitized wording per ID."""
    entries = [(row["task_id"], row["text"]) for row in full_rows]
    entries += [(row["task_id"], row["prompt"]) for row in sanitized_rows]
    entries = sorted(set((i, " ".join(re.findall(r"\w+", p.casefold()))) for i, p in entries))
    parents = {i: i for i, _ in entries}
    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    for index, (left, a) in enumerate(entries):
        for right, b in entries[index + 1:]:
            if left == right or 2 * min(len(a), len(b)) / max(1, len(a) + len(b)) < .90:
                continue
            if SequenceMatcher(None, a, b, autojunk=False).ratio() >= .90:
                first, second = root(left), root(right)
                parents[max(first, second)] = min(first, second)
    return {identifier: "mbpp-full-lexical-" + str(root(identifier)) for identifier in sorted(parents)}


def compatibility(row):
    """Thin V11 static adapter. Executable setup is explicitly unsupported."""
    try:
        setup = ast.parse(row["test_setup_code"])
    except (ValueError, SyntaxError, RecursionError):
        return {"eligible": False, "reason": "invalid_setup_syntax"}
    if setup.body:
        return {"eligible": False, "reason": "unsupported_nonempty_setup"}
    standard, challenge = row["test_list"], row.get("challenge_test_list", [])
    try:
        value = legacy._compatibility({"task_id": row["task_id"], "prompt": row["text"], "code": row["code"],
            "test_imports": [row["test_setup_code"]], "test_list": standard + challenge})
        return {"eligible": value["eligible"], "reason": value["reason"]}
    except (ValueError, SyntaxError, TypeError, RecursionError):
        return {"eligible": False, "reason": "unsupported_static_adapter"}


def inventory(parsed, sanitized_rows, *, history_ids=(), source=None, history_sources=()):
    """Return metadata only; fixture callers must not label it formal data."""
    raw_rows = [r["raw"] for r in parsed]
    full_ids, sanitized_ids = {r["task_id"] for r in raw_rows}, {r["task_id"] for r in sanitized_rows}
    _require(len(full_ids) == len(raw_rows) and len(sanitized_ids) == len(sanitized_rows)
             and sanitized_ids <= full_ids, "Unique full IDs must contain all provided sanitized IDs")
    exposed_functions = set()
    for row in raw_rows:
        try:
            if any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in legacy.EXPOSED_FUNCTIONS
                   for n in ast.walk(ast.parse(row["code"]))):
                exposed_functions.add(row["task_id"])
        except (ValueError, SyntaxError, RecursionError):
            pass  # Static compatibility will reject invalid reference syntax.
    known = set(history_ids) | set(legacy.EXPOSED_IDS) | set(range(1, 11)) | sanitized_ids | exposed_functions
    families = lexical_families(raw_rows, sanitized_rows)
    excluded_families = {families[i] for i in known if i in families}
    records = []
    for source_row in parsed:
        row = source_row["raw"]
        identifier, reasons = row["task_id"], []
        static = compatibility(row)
        if identifier in sanitized_ids: reasons.append("sanitized_pool_excluded")
        if legacy.source_split(identifier) == "prompt": reasons.append("official_prompt_few_shot")
        if identifier in legacy.EXPOSED_IDS: reasons.append("known_readiness_exposure")
        if identifier in exposed_functions: reasons.append("known_readiness_function_exposure")
        if identifier in history_ids: reasons.append("historical_inventory_exposure")
        if families[identifier] in excluded_families and not reasons: reasons.append("lexical_family_exposure_closure")
        if not static["eligible"]: reasons.append(static["reason"])
        records.append({"task_id": identifier, "source_line": source_row["line_number"],
            "source_line_sha256": source_row["line_sha256"], "source_row_hash": source_row["source_row_hash"],
            "source_split": legacy.source_split(identifier), "family_id": families[identifier],
            "static_compatible": static["eligible"], "eligible_candidate": not reasons, "reasons": reasons,
            "standard_test_count": len(row["test_list"]), "challenge_test_count": len(row.get("challenge_test_list", []))})
    eligible = [r for r in records if r["eligible_candidate"]]
    return seal({"version": VERSION, "dataset": "google-research/mbpp-full", "revision": REVISION,
        "source": source, "source_provenance": "pinned_official_snapshot" if source else "fixture_or_unverified_input",
        "history_sources": list(history_sources), "counts": {"source_tasks": len(records),
            "sanitized_ids_excluded": len(sanitized_ids), "history_ids_observed": len(set(history_ids)),
            "history_ids_outside_sanitized": len(set(history_ids) - sanitized_ids),
            "static_compatible_before_exclusions": sum(r["static_compatible"] for r in records),
            "candidate_tasks": len(eligible), "candidate_lexical_families": len({r["family_id"] for r in eligible})},
        "reason_counts_nonexclusive": dict(sorted(Counter(reason for r in records for reason in r["reasons"]).items())),
        "candidate_source_splits": dict(sorted(Counter(r["source_split"] for r in eligible).items())), "records": records,
        "family_rule": "casefold-word-normalized SequenceMatcher>=0.90 connected components over full and sanitized wording",
        "setup_policy": "No executable setup, including imports; not dropped or executed; comments/whitespace allowed",
        "test_scope": "Compile all standard and challenge assertions, no assertion execution",
        "formal_partition_created": False, "execution_calls": 0, "model_calls": 0,
        "limitations": ["Static candidates are not calibrated tasks, semantic-independent families, or adequate sample size.",
            "All sanitized IDs are excluded regardless of which prior runs consumed them.",
            "Old inventories predominantly cover sanitized MBPP; this is not a complete historical exposure closure.",
            "Lexical closure does not establish semantic non-overlap with HumanEval or other benchmarks.",
            "Source ID splits are reported, not reserved as new study partitions.",
            "Sparse native assertions are not a strong or independently validated audit H.",
            "No reference correctness, solution execution, or method effectiveness has been evaluated."]})


def run(repo=REPO, *, output=None, download=False):
    repo = _safe(repo)
    output = _safe(output or repo / DEFAULT_OUTPUT)
    _require(output.is_relative_to(repo / "outputs/skill_validation") and output != repo / "outputs/skill_validation",
             "Inventory output must be a dedicated child of outputs/skill_validation")
    source, parsed, sanitized = snapshot(repo, download=download)
    history_ids, sources = historical_inventories(repo)
    result = inventory(parsed, sanitized, history_ids=history_ids, source=source, history_sources=sources)
    result.pop("record_hash")
    paths = [Path(__file__), Path(legacy.__file__), Path(legacy.__file__).with_name("assertions.py"),
             Path(legacy.__file__).with_name("executor.py"), REPO / "skillopt/coevolution_v10/assertions.py"]
    result["implementation_hashes"] = {str(p.relative_to(REPO)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    result = seal(result)
    write_immutable_json(output / "inventory.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--download", action="store_true", help="Explicitly allow fixed public HTTPS downloads")
    args = parser.parse_args(argv)
    result = run(args.repo, output=args.output, download=args.download)
    print(json.dumps({"version": VERSION, "counts": result["counts"], "reasons": result["reason_counts_nonexclusive"],
                      "record_hash": result["record_hash"], "formal_partition_created": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
