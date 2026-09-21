"""Static HumanEval+ data bridge; benchmark programs execute only in a sandbox.

Public cases come exclusively from literal examples already present in the
published prompt. Extra EvalPlus inputs, its reference and its input contracts
remain host-only. This is a disclosed custom split, not a leaderboard score.
"""
from __future__ import annotations

import ast
import doctest
import gzip
import hashlib
import json
import math
import re
import subprocess
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest, write_immutable_json

from .checks import CallableTask, PublicCase, json_value
from .models import Obligation, TaskContract, require

VERSION = "natural-humanevalplus-contract-data-v1"
DATASET = "evalplus/HumanEvalPlus"
RELEASE = "v0.1.10"
URL = "https://github.com/evalplus/humanevalplus_release/releases/download/v0.1.10/HumanEvalPlus.jsonl.gz"
SHA256 = "272720b90ac375502c8ed23cd791c2a93dfb22a911641a494da74a426c09f101"
DIRECTORY = Path("data/skill_validation/humanevalplus_v0.1.10")
PARTITIONS = ("development", "verifier_calibration", "skill_confirmation", "final")
COUNTS = dict(zip(PARTITIONS, (64, 24, 24, 24)))
SEED = 20260920
SPECIAL_ORACLES = frozenset({"HumanEval/32"})
COMPARATOR_NOTE = ("Evaluation adapter: public examples use Python equality. Floating results may also satisfy "
                   "relative tolerance 1e-7 and the source task's absolute tolerance; when the source tolerance "
                   "is zero, scalar or homogeneous-list float results use absolute tolerance 1e-6. "
                   "This disclosed compatibility protocol is not a native leaderboard evaluation.")


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _plain(value):
    """Reject Python tuples/sets and numeric-key dictionaries, without coercion."""
    if type(value) in (str, int, bool, type(None)):
        return value
    if type(value) is float:
        require(math.isfinite(value), "Nonfinite value")
        return value
    if type(value) is list:
        return [_plain(x) for x in value]
    if type(value) is dict:
        require(all(type(k) is str for k in value), "Non-string JSON key")
        return {k: _plain(v) for k, v in value.items()}
    raise ValueError("Non-JSON native type")


def _literal(node):
    return _plain(ast.literal_eval(node))


def _call(source, entry_point):
    node = ast.parse(source.strip(), mode="eval").body
    require(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == entry_point, "Not a literal call to the task function")
    require(all(k.arg is not None for k in node.keywords), "Expanded keyword call")
    args = [_literal(a) for a in node.args]
    kwargs = {k.arg: _literal(k.value) for k in node.keywords}
    require(len(kwargs) == len(node.keywords), "Duplicate keyword")
    return {"args": args, "kwargs": kwargs}


def _literal_prefix(source):
    """Find a complete literal before trailing prose; never evaluate expressions."""
    source = source.lstrip()
    for end in range(min(len(source), 32768), 0, -1):
        text = source[:end].rstrip()
        if not text:
            continue
        # A shorter prefix must end at a syntax/prose boundary, not inside a number.
        if end < len(source) and source[end].isalnum():
            continue
        remainder = source[end:].lstrip()
        if remainder and remainder[0] in ".+-*/%@|&^=!<>()[{":
            continue
        try:
            return _literal(ast.parse(text, mode="eval").body)
        except (ValueError, SyntaxError, TypeError):
            continue
    raise ValueError("No literal expected result")


def _inline_example_text(doc):
    """Honor explicit Example(s) sections before recognizing inline equations.

    A function name may also denote a mathematical quantity in explanatory
    prose. A later standalone Examples heading makes that prose ineligible as
    a function-return example. Doctests remain independently explicit calls.
    """
    headings = list(re.finditer(r"(?m)^(?P<indent>[ \t]*)(?P<title>[A-Za-z][A-Za-z -]*):[ \t]*$", doc))
    examples = [heading for heading in headings if heading["title"].casefold() in {"example", "examples"}]
    if not examples:
        return doc
    sections = []
    for example in examples:
        end = next((heading.start() for heading in headings
                    if heading.start() > example.start() and len(heading["indent"]) <= len(example["indent"])), len(doc))
        sections.append(doc[example.end():end])
    return "\n\n".join(sections)


def public_examples(row):
    """Recognize doctests and explicit ``function(literals) ==/=> literal`` text.

    No base_input, plus_input, test, contract or reference is consulted here.
    The entire original prompt is retained as the public provenance quote.
    """
    prompt, entry = row["prompt"], row["entry_point"]
    tree = ast.parse(prompt)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == entry)
    doc = ast.get_docstring(function, clean=False) or ""
    found = []

    def append(arguments, expected):
        # PublicCase has a deliberately smaller bound than host-only audit inputs.
        json_value(_json(arguments))
        json_value(_json(expected))
        item = (arguments, expected)
        if digest(item) not in {digest(previous) for previous in found}:
            found.append(item)

    try:
        examples = doctest.DocTestParser().get_examples(doc)
    except ValueError:
        examples = []
    for example in examples:
        try:
            append(_call(example.source, entry), _literal(ast.parse(example.want.strip(), mode="eval").body))
        except (ValueError, SyntaxError, TypeError):
            pass
    inline = _inline_example_text(doc)
    for match in re.finditer(r"\b" + re.escape(entry) + r"\s*\(", inline):
        for close in re.finditer(r"\)", inline[match.start():]):
            end = match.start() + close.end()
            try:
                arguments = _call(inline[match.start():end], entry)
            except (ValueError, SyntaxError, TypeError):
                continue
            rest = inline[end:]
            marker = re.match(r"\s*(?:#\s*)?(?:==>|=>|->|==|=(?!=)|returns\b|should return\b)\s*:?[ \t]*", rest)
            if marker:
                try:
                    # Examples use one line, with possible balanced literal continuations.
                    suffix = rest[marker.end():].split("\n\n", 1)[0]
                    append(arguments, _literal_prefix(suffix))
                except (ValueError, SyntaxError, TypeError):
                    pass
            break
    return tuple(PublicCase("prompt-example-" + str(i), _json(arguments), prompt,
                            ("requested_behavior",), expected_json=_json(expected))
                 for i, (arguments, expected) in enumerate(found[:16]))


def public_projection(row):
    """If needed, disclose one original literal assert equally to solver and V."""
    cases = public_examples(row)
    if cases:
        return row["prompt"], cases, {"kind": "original_prompt_literal_examples", "original_assertion_index": None}
    for index, assertion in enumerate(n for n in ast.walk(ast.parse(row["test"])) if isinstance(n, ast.Assert)):
        expression = assertion.test
        if not (isinstance(expression, ast.Compare) and len(expression.ops) == 1
                and isinstance(expression.ops[0], ast.Eq) and isinstance(expression.left, ast.Call)
                and isinstance(expression.left.func, ast.Name) and expression.left.func.id == "candidate"):
            continue
        call = expression.left
        try:
            arguments = {"args": [_literal(a) for a in call.args],
                         "kwargs": {k.arg: _literal(k.value) for k in call.keywords}}
            require(all(k.arg is not None for k in call.keywords), "Expanded keyword call")
            expected = _literal(expression.comparators[0])
            json_value(_json(arguments))
            json_value(_json(expected))
        except (ValueError, SyntaxError, TypeError):
            continue
        # Preserve the original assertion's syntax except the named callable.
        call.func.id = row["entry_point"]
        shown = ast.unparse(assertion)
        quote = "Public original benchmark example (assertion " + str(index) + "): " + shown
        prompt = row["prompt"] + "\n\n" + quote
        case = PublicCase("disclosed-native-assertion-" + str(index), _json(arguments), quote,
                          ("requested_behavior",), expected_json=_json(expected))
        return prompt, (case,), {"kind": "disclosed_original_literal_assertion", "original_assertion_index": index}
    return row["prompt"], (), {"kind": "no_supported_public_example", "original_assertion_index": None}


def compatibility(row):
    """Source-only eligibility; successful reference execution is a later gate."""
    try:
        require(row["task_id"] not in SPECIAL_ORACLES, "special_oracle")
        tree = ast.parse(row["prompt"] + row["canonical_solution"])
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == row["entry_point"])
        annotation = ast.unparse(function.returns) if function.returns else ""
        require(not any(word in annotation for word in ("Tuple", "Set", "tuple", "set")), "native_non_json_return")
        require(not any(isinstance(n, ast.Return) and isinstance(n.value, (ast.Tuple, ast.Set))
                        for n in ast.walk(function)), "native_non_json_return")
        require(type(row["atol"]) in (int, float) and row["atol"] >= 0, "unsupported_atol")
        for name in ("base_input", "plus_input"):
            require(type(row[name]) is list and bool(row[name]), "empty_hidden_input_partition")
            for args in row[name]:
                require(type(args) is list, "non_json_call_arguments")
                _plain(args)
        prompt, cases, origin = public_projection(row)
        require(bool(cases), "no_supported_public_example")
        require(len(prompt.encode()) <= 12000, "oversized_public_contract")
    except (SyntaxError, TypeError, StopIteration, KeyError):
        return {"eligible": False, "reason": "unsupported_source_structure"}
    except ValueError as error:
        return {"eligible": False, "reason": str(error)}
    return {"eligible": True, "reason": None, "public_examples": len(cases), "public_origin": origin}


def lexical_families(rows):
    """Conservative lexical components; this does not certify semantic families."""
    values = {r["task_id"]: " ".join(re.findall(r"\w+", r["prompt"].casefold())) for r in rows}
    parents = {key: key for key in values}

    def root(key):
        while parents[key] != key:
            key = parents[key]
        return key

    keys = sorted(values)
    for position, left in enumerate(keys):
        for right in keys[position + 1:]:
            a, b = values[left], values[right]
            if 2 * min(len(a), len(b)) / max(1, len(a) + len(b)) >= .90 \
                    and SequenceMatcher(None, a, b, autojunk=False).ratio() >= .90:
                first, second = sorted((root(left), root(right)))
                parents[second] = first
    return {key: "humaneval-lexical-" + root(key).split("/")[-1] for key in keys}


def download(repo):
    """Fetch and hash-check the pinned public release; never import its programs."""
    import httpx
    directory = Path(repo).resolve() / DIRECTORY
    path = directory / "HumanEvalPlus.jsonl.gz"
    require(not any(p.is_symlink() for p in (directory, *directory.parents)), "Symlink data path")
    if path.exists():
        require(not path.is_symlink(), "Symlink data file")
        body = path.read_bytes()
    else:
        with httpx.Client(trust_env=False, timeout=45, follow_redirects=True) as client:
            response = client.get(URL)
            response.raise_for_status()
            body = response.content
        require(len(body) <= 64_000_000 and hashlib.sha256(body).hexdigest() == SHA256,
                "Pinned HumanEval+ compressed asset changed")
        directory.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as handle:
            handle.write(body)
    require(hashlib.sha256(body).hexdigest() == SHA256, "Pinned HumanEval+ asset changed")
    raw = gzip.decompress(body)
    rows = [json.loads(line) for line in raw.splitlines() if line]
    require(len(rows) == 164 and len({r["task_id"] for r in rows}) == 164, "Unexpected HumanEval+ source population")
    return rows, seal({"version": VERSION + "-source", "dataset": DATASET, "release": RELEASE,
                       "url": URL, "compressed_sha256": SHA256, "raw_sha256": hashlib.sha256(raw).hexdigest(),
                       "path": str(path.relative_to(Path(repo).resolve())), "rows": len(rows),
                       "benchmark_code_executed": False})


def _safe_path(path):
    path = Path(path).absolute()
    require(".." not in path.parts and not any(p.is_symlink() for p in (path, *path.parents)),
            "Symlink or parent traversal path")
    return path


def _history(repo, output, rows):
    """Scan identities and prompt hashes, without parsing stored solutions."""
    root = repo / "outputs"
    hashes = {digest(r["prompt"]): r["task_id"] for r in rows}
    identifiers, files = set(), []
    if root.exists():
        # rg performs the broad scan once; only matching text files are read into Python.
        pattern = r"HumanEval[/_: -][0-9]+|" + "|".join(hashes)
        process = subprocess.run(["rg", "-l", "--null", "--hidden", "--no-ignore", "-i",
                                  "-g", "!**/.env*", "-g", "!**/.git/**", "-g", "*.json",
                                  "-g", "*.jsonl", "-g", "*.md", "-g", "*.log", "-g", "*.txt",
                                  pattern, str(root)], capture_output=True, check=False)
        require(process.returncode in (0, 1), "Historical exposure search failed")
        for raw_path in process.stdout.split(b"\0"):
            if not raw_path:
                continue
            path = _safe_path(raw_path.decode())
            if path.is_relative_to(output):
                continue
            body = path.read_bytes()
            if path.name == "eligibility_manifest.json":
                catalog = verify(json.loads(body))
                if catalog.get("version") == VERSION + "-eligibility":
                    continue
            text = body.decode("utf-8")
            found = {"HumanEval/" + str(int(match)) for match in re.findall(r"(?i)HumanEval[/_: -]([0-9]+)", text)}
            found.update(identifier for fingerprint, identifier in hashes.items() if fingerprint in text)
            identifiers.update(found)
            files.append({"path": str(path.relative_to(repo)), "sha256": hashlib.sha256(body).hexdigest(),
                          "matched_ids": sorted(found)})
    return seal({"version": VERSION + "-exposure", "files": files,
                 "excluded_ids": sorted(identifiers), "scope": "all_outputs_source_ids_and_prompt_hashes"})


def select(rows, inventory, *, counts=None, seed=SEED):
    """Outcome-blind family-disjoint selection; never silently reduce counts."""
    require(type(seed) is int and seed >= 0, "Invalid selection seed")
    families = lexical_families(rows)
    exposed = set(inventory["excluded_ids"])
    exposed_families = {families[key] for key in exposed if key in families}
    eligible, diagnostics, records = [], Counter(), []
    for row in rows:
        checked = compatibility(row)
        reason = checked["reason"]
        if checked["eligible"] and families[row["task_id"]] in exposed_families:
            reason = "historical_exposure_or_near_duplicate"
        identity = {"task_id": row["task_id"], "original_task_id": row["task_id"],
                    "family_id": families[row["task_id"]], "source_row_hash": digest(row),
                    "question_sha256": digest(row["prompt"]), "source_split": "original_humaneval_test",
                    "eligible": reason is None, "reason": reason}
        records.append(identity)
        diagnostics[reason or "eligible"] += 1
        if reason is None:
            eligible.append(identity)
    ranked = sorted(eligible, key=lambda row: digest([VERSION, seed, row["task_id"]]))
    representatives, seen = [], set()
    for row in ranked:
        if row["family_id"] not in seen:
            representatives.append(row)
            seen.add(row["family_id"])
    actual_counts = dict(COUNTS if counts is None else counts)
    if counts is None:
        actual_counts["final"] = len(representatives) - sum(actual_counts[p] for p in PARTITIONS[:-1])
    require(set(actual_counts) == set(PARTITIONS)
            and all(type(n) is int and n > 0 for n in actual_counts.values()), "Positive counts for all four partitions required")
    require(counts is not None or actual_counts["final"] >= COUNTS["final"],
            "Fewer than 136 eligible unexposed unique families; explicitly revise protocol counts")
    require(sum(actual_counts.values()) <= len(representatives), "Insufficient unexposed unique families")
    splits, offset = {}, 0
    for partition in PARTITIONS:
        splits[partition] = [{**row, "partition": partition} for row in representatives[offset:offset + actual_counts[partition]]]
        offset += actual_counts[partition]
    return splits, {**dict(diagnostics), "unique_eligible_families": len(representatives)}, records


def prepare(repo, output, *, counts=None, seed=SEED):
    """Download static assets and freeze identities before any model requests."""
    repo, output = _safe_path(repo), _safe_path(output)
    require(output.is_relative_to(repo / "outputs/skill_validation") and output != repo / "outputs/skill_validation",
            "Dedicated skill_validation output directory required")
    rows, source = download(repo)
    settings = {"seed": seed, "requested_counts": counts, "source_snapshot_hash": source["record_hash"],
                "implementation_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    manifest_path = output / "data_manifest.json"
    if manifest_path.exists():
        previous = verify(json.loads(manifest_path.read_text()))
        require(previous.get("version") == VERSION and previous["settings"] == settings, "Frozen data settings changed")
        inventory = verify(json.loads((output / "exposure_inventory.json").read_text()))
        require(inventory["record_hash"] == previous["exposure_inventory_hash"], "Frozen inventory changed")
        for entry in inventory["files"]:
            path = _safe_path(repo / entry["path"])
            require(hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"], "Historical exposure file changed")
        return previous
    inventory = _history(repo, output, rows)
    splits, diagnostics, catalog = select(rows, inventory, counts=counts, seed=seed)
    manifest = seal({"version": VERSION, "dataset": DATASET, "run_path": str(output.relative_to(repo)),
                     "settings": settings, "splits": splits, "counts": {p: len(v) for p, v in splits.items()},
                     "pool_counts": diagnostics, "exposure_inventory_hash": inventory["record_hash"],
                     "source_snapshot": source, "canonical_benchmark": False,
                     "split_policy": "custom_four_way_family_disjoint_original_test_partition",
                     "lexical_grouping": "casefold words SequenceMatcher>=0.90 connected components",
                     "semantic_family_independence_certified": False, "project_disjoint": False,
                     "extra_nonmutation_or_repeat_obligations": False,
                     "public_examples_policy": "prompt_literals_or_one_disclosed_original_literal_assertion",
                     "hidden_audit_policy": "all_base_and_plus_inputs_reference_differential",
                     "special_oracle_excluded_ids": sorted(SPECIAL_ORACLES),
                     "float_policy": "EvalPlus_python_equality_then_rtol1e-7_atol_or_float_default1e-6"})
    write_immutable_json(output / "source_snapshot.json", source)
    write_immutable_json(output / "eligibility_manifest.json", seal({"version": VERSION + "-eligibility", "records": catalog}))
    write_immutable_json(output / "exposure_inventory.json", inventory)
    write_immutable_json(manifest_path, manifest)
    return manifest


def materialize_row(row, identity):
    require(digest(row) == identity["source_row_hash"], "Selected source row changed")
    require(compatibility(row)["eligible"], "Selected row became incompatible")
    prompt, cases, origin = public_projection(row)
    comparator = {"atol": row["atol"], "rtol": 1e-7, "float_default_atol": 1e-6}
    prompt += "\n\n" + COMPARATOR_NOTE + " Source absolute tolerance: " + str(row["atol"]) + "."
    contract = TaskContract(row["task_id"], row["task_id"], identity["family_id"], "humaneval-public-functions",
                            identity["partition"], "coding", "task_contract_conformance", prompt,
                            (Obligation("requested_behavior", "requested_behavior", row["prompt"], row["prompt"]),))
    task = CallableTask(contract, "solution", row["entry_point"], cases)
    public_case = PublicCase("all-disclosed-public-examples", '{"args":[],"kwargs":{}}',
                             COMPARATOR_NOTE, ("requested_behavior",), expected_json="true")
    public_task = CallableTask(contract, "public_runner", "check", (public_case,))
    visible_cases = [{"arguments": json.loads(case.arguments_json), "expected": json.loads(case.expected_json)}
                     for case in cases]
    public_wrapper = {"path": "public_runner.py", "content": (
        "ENTRY = " + repr(row["entry_point"]) + "\nATOL = " + repr(row["atol"])
        + "\nEXAMPLES = " + repr(visible_cases) + "\n" + _AUDIT_PROGRAM.split("def audit():", 1)[0]
        + "def check():\n    candidate = getattr(importlib.import_module('solution'), ENTRY)\n"
        + "    for case in EXAMPLES:\n        args = copy.deepcopy(case['arguments'])\n"
        + "        actual = candidate(*args['args'], **args['kwargs'])\n"
        + "        if not _plain(actual) or not _same(actual, case['expected']):\n            return False\n"
        + "    return True\n")}
    return {"identity": dict(identity), "task": task, "public_task": public_task,
            "public_wrapper": public_wrapper, "public_comparator": comparator, "public_example_origin": origin,
            "host_audit": {"reference_code": row["prompt"] + row["canonical_solution"],
                           "entry_point": row["entry_point"], "base_input": row["base_input"],
                           "plus_input": row["plus_input"], "atol": row["atol"],
                           "native_test": row["test"], "source_input_contract": row["contract"]}}


def load_tasks(repo, manifest, partition):
    verify(manifest)
    repo = _safe_path(repo)
    require(manifest.get("version") == VERSION and partition in PARTITIONS, "Unknown natural-data manifest/partition")
    root = _safe_path(repo / manifest["run_path"])
    require(root.is_relative_to(repo / "outputs/skill_validation")
            and verify(json.loads((root / "data_manifest.json").read_text())) == manifest, "Actual frozen manifest required")
    rows, source = download(repo)
    require(source["record_hash"] == manifest["settings"]["source_snapshot_hash"], "Frozen source changed")
    require(hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == manifest["settings"]["implementation_hash"],
            "Frozen data implementation changed")
    indexed = {row["task_id"]: row for row in rows}
    return [materialize_row(indexed[identity["task_id"]], identity) for identity in manifest["splits"][partition]]


_AUDIT_PROGRAM = '''import copy
import importlib
import math

def _plain(value):
    if type(value) in (str, int, bool, type(None)):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_plain(x) for x in value)
    if type(value) is dict:
        return all(type(k) is str and _plain(v) for k, v in value.items())
    return False

def _floats(value):
    return type(value) is float or (type(value) is list and bool(value) and all(type(x) is float for x in value))

def _close(actual, expected, tolerance):
    if type(expected) is list:
        return type(actual) is list and len(actual) == len(expected) and all(_close(a, e, tolerance) for a, e in zip(actual, expected))
    if type(actual) not in (int, float, bool) or type(expected) not in (int, float, bool):
        return False
    return abs(actual - expected) <= tolerance + 1e-7 * abs(expected)

def _same(actual, expected):
    if actual == expected:
        return True
    tolerance = ATOL or (1e-6 if _floats(expected) else 0)
    return bool(tolerance and type(actual) is type(expected) and _close(actual, expected, tolerance))

def audit():
    report = {"base_pass": None, "plus_pass": None, "base_count": len(BASE), "plus_count": len(PLUS),
              "base_observed": 0, "plus_observed": 0, "base_failed": 0, "plus_failed": 0,
              "base_unknown": 0, "plus_unknown": 0, "reference_errors": 0,
              "candidate_errors": 0, "unsupported_outputs": 0, "reference_unsupported_outputs": 0,
              "candidate_unsupported_outputs": 0, "status": "unknown"}
    try:
        reference = getattr(importlib.import_module("reference_solution"), ENTRY)
    except Exception:
        report["reference_errors"] = 1
        report["base_unknown"] = len(BASE)
        report["plus_unknown"] = len(PLUS)
        report["reason"] = "reference_module_or_entrypoint_unavailable"
        return report
    try:
        candidate = getattr(importlib.import_module("solution"), ENTRY)
    except Exception:
        report["candidate_errors"] = 1
        report["base_observed"] = report["base_failed"] = len(BASE)
        report["plus_observed"] = report["plus_failed"] = len(PLUS)
        report["base_pass"] = report["plus_pass"] = False
        report["status"] = "fail"
        report["reason"] = "candidate_module_or_entrypoint_unavailable"
        return report
    for name, inputs in (("base", BASE), ("plus", PLUS)):
        for arguments in inputs:
            try:
                expected = reference(*copy.deepcopy(arguments))
                if not _plain(expected):
                    report["unsupported_outputs"] += 1
                    report["reference_unsupported_outputs"] += 1
                    report[name + "_unknown"] += 1
                    continue
            except Exception:
                report["reference_errors"] += 1
                report[name + "_unknown"] += 1
                continue
            report[name + "_observed"] += 1
            try:
                actual = candidate(*copy.deepcopy(arguments))
                if not _plain(actual):
                    report["unsupported_outputs"] += 1
                    report["candidate_unsupported_outputs"] += 1
                    report[name + "_failed"] += 1
                    continue
                if not _same(actual, expected):
                    report[name + "_failed"] += 1
            except Exception:
                report["candidate_errors"] += 1
                report[name + "_failed"] += 1
                continue
        if report[name + "_failed"]:
            report[name + "_pass"] = False
        elif report[name + "_unknown"] == 0 and report[name + "_observed"] == len(inputs):
            report[name + "_pass"] = True
    report["status"] = ("fail" if report["base_pass"] is False or report["plus_pass"] is False else
                        "pass" if report["base_pass"] is True and report["plus_pass"] is True else "unknown")
    return report
'''


def build_audit_files(row, model_code=None, *, reference=False):
    """Build source text for one bounded Docker call to hidden_audit.audit()."""
    audit = row["host_audit"]
    if reference:
        model_code = audit["reference_code"]
    require(type(model_code) is str and bool(model_code.strip()), "Nonempty candidate source required")
    constants = "ENTRY = " + repr(audit["entry_point"]) + "\nATOL = " + repr(audit["atol"]) + "\n"
    constants += "BASE = " + repr(audit["base_input"]) + "\nPLUS = " + repr(audit["plus_input"]) + "\n"
    files = {"solution.py": model_code, "reference_solution.py": audit["reference_code"],
             "hidden_audit.py": constants + _AUDIT_PROGRAM}
    require(sum(len(value.encode()) for value in files.values()) <= 1_048_576, "Audit source exceeds sandbox source budget")
    return files
