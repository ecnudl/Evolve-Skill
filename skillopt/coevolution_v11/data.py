"""Pinned MBPP-sanitized snapshots and outcome-blind, one-use reservations.

This module never executes benchmark code. Reference eligibility is STATIC;
reference correctness must be calibrated separately in the OS sandbox. Gold
and compiled checks are host-only. The model projection contains only task
description and a value-free callable interface.
"""

from __future__ import annotations

import ast
import fcntl
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

from skillopt.coevolution_v5 import core
from skillopt.scope_evolution_v2.source_data import file_hash, question_fingerprint, write_immutable_text
from skillopt.validator_pilot.api import digest, write_immutable_json

VERSION = "v11-mbpp-sanitized-data-v1"
SOURCE_VERSION = "v10-mbpp-sanitized-official-source-v1"
REVISION = "08a8d6736475776f42ffac23b2c13111a28e5795"
CARD_REVISION = "4bb6404fdc6cacfda99d4ac4205087b89d32030c"
DATASET = "google-research/mbpp-sanitized"
DIRECTORY = Path("data/coevolution_v10/mbpp_sanitized_08a8d673")
URLS = {
    "dataset": f"https://raw.githubusercontent.com/google-research/google-research/{REVISION}/mbpp/sanitized-mbpp.json",
    "upstream_readme": f"https://raw.githubusercontent.com/google-research/google-research/{REVISION}/mbpp/README.md",
    "dataset_card": f"https://huggingface.co/datasets/google-research-datasets/mbpp/raw/{CARD_REVISION}/README.md",
}
FILENAMES = {"dataset": "sanitized-mbpp.json", "upstream_readme": "UPSTREAM_README.md", "dataset_card": "DATASET_CARD.md"}
PUBLISHED_COUNTS = {"prompt": 7, "train": 120, "validation": 43, "test": 257}
EXPOSED_IDS = frozenset({1, 2, *range(800, 808)})
EXPOSED_FUNCTIONS = frozenset({"left_rotate"})
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_PREFIXED_ID = re.compile(r"(?i)(?<![a-z])mbpp(?:[-_]sanitized)?[/:_-]+([0-9]{1,3})(?![0-9])")
_NUMERIC_ID = re.compile(r'"(?:task_id|id|key)"\s*:\s*"?([0-9]{1,3})(?![0-9])')
_EXTENSIONS = frozenset({".json", ".jsonl", ".md", ".txt", ".log"})


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key in source or artifact")
        value[key] = item
    return value


def _json(text):
    return json.loads(text, object_pairs_hook=_unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")))


def _read(path):
    return core.verify(_json(Path(path).read_text(encoding="utf-8")))


def _save(path, value):
    sealed = core.seal(value)
    write_immutable_json(Path(path), sealed)
    return sealed


def source_split(task_id):
    """Official ID-based split; sanitized inherits these original assignments."""
    if type(task_id) is not int or not 1 <= task_id <= 974:
        raise ValueError("MBPP task_id must be an integer in [1,974]")
    if task_id <= 10:
        return "prompt"
    if task_id <= 510:
        return "test"
    if task_id <= 600:
        return "validation"
    return "train"


def _rows(text):
    rows = _json(text)
    if not isinstance(rows, list):
        raise ValueError("Official sanitized MBPP must be one JSON array")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Malformed MBPP source row")
        source_split(row.get("task_id"))
        if row["task_id"] in seen:
            raise ValueError("Duplicate MBPP source task_id")
        seen.add(row["task_id"])
        if any(not isinstance(row.get(field), str) or not row[field].strip() for field in ("prompt", "code")):
            raise ValueError("MBPP source lacks prompt/reference text")
        if (not isinstance(row.get("test_list"), list) or not row["test_list"]
                or any(not isinstance(test, str) or not test.strip() for test in row["test_list"])):
            raise ValueError("MBPP source test_list is missing or malformed")
        if (not isinstance(row.get("test_imports"), list)
                or any(not isinstance(item, str) for item in row["test_imports"])):
            raise ValueError("MBPP source test_imports is malformed")
    return rows


def _counts(rows):
    return dict(Counter(source_split(row["task_id"]) for row in rows))


def download_snapshot(repo):
    """Fetch only three fixed official text assets; never execute their contents.

    No credentials are read. Reuse a completed, verified snapshot without
    network access. A partial download is compared immutably against its URL.
    """
    import httpx

    repo = Path(repo).resolve()
    root = repo / DIRECTORY
    path = root / "source_snapshot.json"
    if path.exists():
        return load_snapshot(repo, path)
    bodies = {}
    with httpx.Client(trust_env=False, timeout=45, follow_redirects=False) as client:
        for name, url in URLS.items():
            with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise ValueError(f"Official {name} snapshot returned HTTP {response.status_code}")
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 4 * 1024 * 1024:
                        raise ValueError("Official text snapshot exceeds fixed size limit")
                    chunks.append(chunk)
                bodies[name] = b"".join(chunks).decode("utf-8")
    rows = _rows(bodies["dataset"])
    if len(rows) != 427 or _counts(rows) != PUBLISHED_COUNTS:
        raise ValueError("Pinned source disagrees with official sanitized split cardinalities")
    if not re.search(r"license:\s*\n\s*-\s*cc-by-4\.0", bodies["dataset_card"], re.IGNORECASE):
        raise ValueError("Pinned official dataset card does not declare CC-BY-4.0")
    files = {}
    for name, body in bodies.items():
        target = root / FILENAMES[name]
        write_immutable_text(target, body)
        files[name] = {"path": str(target.relative_to(repo)), "sha256": file_hash(target), "url": URLS[name]}
    return _save(path, {
        "version": SOURCE_VERSION, "dataset": DATASET, "revision": REVISION,
        "card_revision": CARD_REVISION, "license": "CC-BY-4.0", "files": files,
        "source_counts": _counts(rows), "total_rows": len(rows),
        "notes": ["Immutable official raw assets; no task/reference/test body is in this metadata.",
                  "Sanitized JSON-array rows retain official ID-based splits.",
                  "No benchmark code executed by snapshot acquisition."],
    })


def load_snapshot(repo, source_path=None):
    repo = Path(repo).resolve()
    path = (repo / DIRECTORY / "source_snapshot.json") if source_path is None else Path(source_path).resolve()
    if not path.is_relative_to(repo / "data/coevolution_v10"):
        raise ValueError("Source snapshot must reside beneath data/coevolution_v10")
    snapshot = _read(path)
    if (snapshot.get("version") != SOURCE_VERSION or snapshot.get("dataset") != DATASET
            or snapshot.get("revision") != REVISION or snapshot.get("card_revision") != CARD_REVISION
            or snapshot.get("license") != "CC-BY-4.0" or set(snapshot.get("files", {})) != set(URLS)):
        raise ValueError("Source snapshot does not identify the pinned official release")
    for name, item in snapshot["files"].items():
        target = (repo / item["path"]).resolve()
        if (not target.is_relative_to(repo / "data/coevolution_v10") or item["url"] != URLS[name]
                or not target.is_file() or file_hash(target) != item["sha256"]):
            raise ValueError("Official snapshot asset changed or escaped source directory")
    rows = _rows((repo / snapshot["files"]["dataset"]["path"]).read_text(encoding="utf-8"))
    if (_counts(rows) != snapshot["source_counts"] or len(rows) != snapshot["total_rows"]
            or len(rows) != 427 or _counts(rows) != PUBLISHED_COUNTS):
        raise ValueError("Snapshot source counts differ from its actual rows")
    return snapshot


def _source_rows(repo, snapshot):
    return _rows((Path(repo) / snapshot["files"]["dataset"]["path"]).read_text(encoding="utf-8"))


def _compatibility(row):
    from .assertions import compile_tests
    from .executor import validate_code

    compiled = compile_tests(row["test_list"], setup_code="\n".join(row["test_imports"]))
    if compiled.get("compatible") is not True:
        # Fixed structural category; never persist an exception containing a
        # reference solution, hidden assertion, literal argument or answer.
        return {"eligible": False, "reason": "unsupported_native_assertions", "compiled": None}
    try:
        tree = validate_code(row["code"])
    except (ValueError, SyntaxError, TypeError, RecursionError):
        return {"eligible": False, "reason": "unsupported_reference_ast", "compiled": None}
    if len([node for node in tree.body if isinstance(node, ast.FunctionDef)
            and node.name == compiled["entry_point"]]) != 1:
        return {"eligible": False, "reason": "unsupported_reference_interface", "compiled": None}
    return {"eligible": True, "reason": None, "compiled": compiled}


def _implementation_hashes():
    root = Path(__file__).resolve().parents[2]
    names = ("skillopt/coevolution_v11/data.py", "skillopt/coevolution_v11/assertions.py",
             "skillopt/coevolution_v11/executor.py", "skillopt/coevolution_v11/child.py",
             "skillopt/coevolution_v10/codec.py", "skillopt/coevolution_v10/assertions.py")
    return {name: file_hash(root / name) for name in names}


def inspect_compatibility(repo, source_path=None):
    """Host-only static inspection. Public output is counts and identity hashes."""
    snapshot = load_snapshot(repo, source_path)
    records, counts = [], Counter()
    for row in _source_rows(repo, snapshot):
        category = source_split(row["task_id"])
        result = _compatibility(row)
        try:
            tree = ast.parse(row["code"])
            known_function = any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                                 and node.name in EXPOSED_FUNCTIONS for node in ast.walk(tree))
        except (SyntaxError, ValueError, RecursionError):
            known_function = False
        known_exposure = row["task_id"] in EXPOSED_IDS or known_function
        reason = ("official_prompt_split" if category == "prompt" else
                  "known_readiness_exposure" if known_exposure else result["reason"])
        eligible = reason is None and result["eligible"]
        counts[f"{category}:source"] += 1
        counts[f"{category}:" + ("eligible" if eligible else reason)] += 1
        records.append({"task_id": row["task_id"], "source_split": category,
                        "question_sha256": question_fingerprint(row["prompt"]), "source_row_hash": digest(row),
                        "compiled_hash": digest(result["compiled"]) if result["compiled"] is not None else None,
                        "eligible": bool(eligible), "reason": reason})
    return core.seal({"version": VERSION + "-eligibility", "dataset": DATASET,
                      "source_snapshot_hash": snapshot["record_hash"],
                      "implementation_hashes": _implementation_hashes(),
                      "counts": dict(sorted(counts.items())), "records": records,
                      "notes": ["Static source/grammar compatibility only; no model outcome or reference execution.",
                                "Reference correctness calibration is a separate sandbox-only stage."]})


def _history_paths(repo, run_dir):
    root = repo / "outputs"
    if root.is_symlink():
        raise ValueError("Historical exposure symlinks are not supported")
    if not root.exists():
        return []
    paths = []
    for path in root.rglob("*"):
        if path.is_relative_to(run_dir):
            continue
        if path.is_symlink():
            raise ValueError("Historical exposure symlinks are not supported")
        if path.is_file() and path.suffix.lower() in _EXTENSIONS:
            paths.append(path)
    return sorted(paths)


def _extract_history(raw, *, known_ids, known_questions, mbpp_path):
    ids, questions = set(), set()
    if mbpp_path or re.search(r'"(?:dataset|source_dataset|benchmark)"\s*:\s*"[^"\n]*mbpp', raw, re.IGNORECASE):
        # Preserve identifiable exposure even in a truncated final JSONL line.
        ids.update(int(match.group(1)) for match in _NUMERIC_ID.finditer(raw)
                   if int(match.group(1)) in known_ids)
    for match in _PREFIXED_ID.finditer(raw):
        identifier = int(match.group(1))
        if identifier in known_ids:
            ids.add(identifier)
    try:
        stack = [(_json(raw), mbpp_path)]
    except ValueError:
        stack = []
        for line in raw.splitlines():
            try:
                stack.append((_json(line), mbpp_path))
            except ValueError:
                continue
    while stack:
        value, scoped = stack.pop()
        if isinstance(value, dict):
            scoped = scoped or any(isinstance(value.get(name), str) and "mbpp" in value[name].casefold()
                                   for name in ("dataset", "source_dataset", "benchmark", "version", "manifest_type"))
            for name in ("task_id", "id", "key"):
                identifier = value.get(name)
                if scoped and (type(identifier) is int or isinstance(identifier, str) and identifier.isdigit()):
                    if int(identifier) in known_ids:
                        ids.add(int(identifier))
            if scoped:
                for name in ("excluded_ids", "task_ids", "reserved_ids"):
                    for identifier in value.get(name, []) if isinstance(value.get(name), list) else []:
                        if ((type(identifier) is int or isinstance(identifier, str) and identifier.isdigit())
                                and int(identifier) in known_ids):
                            ids.add(int(identifier))
            for name in ("question_sha256", "prompt_sha256"):
                fingerprint = value.get(name)
                if isinstance(fingerprint, str) and fingerprint in known_questions:
                    questions.add(fingerprint)
            for fingerprint in value.get("excluded_question_sha256", []) if isinstance(
                    value.get("excluded_question_sha256"), list) else []:
                if isinstance(fingerprint, str) and fingerprint in known_questions:
                    questions.add(fingerprint)
            stack.extend((item, scoped) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, scoped) for item in value)
        elif isinstance(value, str):
            fingerprint = question_fingerprint(value)
            if fingerprint in known_questions:
                questions.add(fingerprint)
            for match in _PREFIXED_ID.finditer(value):
                identifier = int(match.group(1))
                if identifier in known_ids:
                    ids.add(identifier)
            if value.lstrip().startswith(("{", "[")):
                try:
                    nested = _json(value)
                except ValueError:
                    continue
                if isinstance(nested, (dict, list)):
                    stack.append((nested, scoped))
    return ids, questions


def _history(repo, run_dir, records):
    index = {row["task_id"]: row["question_sha256"] for row in records}
    known_ids, known_questions = set(index), set(index.values())
    ids = set(EXPOSED_IDS) & known_ids
    questions, files = set(), []
    for row in records:
        if row["reason"] == "known_readiness_exposure":
            ids.add(row["task_id"])
    for path in _history_paths(repo, run_dir):
        body = path.read_bytes()
        try:
            raw = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Historical exposure input is not UTF-8") from exc
        catalog_versions = {"coevolution_v10": "v10-mbpp-sanitized-data-v1-eligibility",
                            "coevolution_v11": VERSION + "-eligibility"}
        catalog_version = next((version for registry, version in catalog_versions.items()
                                if path.is_relative_to(repo / "outputs" / registry)), None)
        if path.name == "eligibility_manifest.json" and catalog_version is not None:
            catalog = core.verify(_json(raw))
            if catalog.get("version") != catalog_version:
                raise ValueError("Unknown historical eligibility catalog")
            # A host-only static catalog lists the entire source pool. It is
            # neither a model exposure nor a reservation of every listed ID.
            # Its bytes are still sealed as a scanned historical input below.
            found_ids, found_questions = set(), set()
        else:
            found_ids, found_questions = _extract_history(
                raw, known_ids=known_ids, known_questions=known_questions, mbpp_path="mbpp" in str(path).casefold())
        ids.update(found_ids)
        questions.update(found_questions)
        files.append({"path": str(path.relative_to(repo)), "sha256": hashlib.sha256(body).hexdigest(),
                      "matched_ids": len(found_ids), "matched_questions": len(found_questions)})
    questions.update(index[identifier] for identifier in ids)
    return core.seal({"version": VERSION + "-exposure", "dataset": DATASET, "files": files,
                      "excluded_ids": sorted(ids), "excluded_question_sha256": sorted(questions)})


def _validate_manifest(manifest):
    core.verify(manifest)
    if manifest.get("version") != VERSION or manifest.get("dataset") != DATASET:
        raise ValueError("Unknown MBPP data manifest")
    counts = manifest["settings"]["counts"]
    if set(counts) != {"confirmation", "final"} or set(manifest["splits"]) != set(counts):
        raise ValueError("Exactly confirmation and final are reserved")
    ids, questions = set(), set()
    for split, rows in manifest["splits"].items():
        if type(counts[split]) is not int or counts[split] < 1 or len(rows) != counts[split]:
            raise ValueError("Reserved cardinality differs from frozen counts")
        allowed = {"train", "validation"} if split == "confirmation" else {"test"}
        for row in rows:
            if set(row) != {"task_id", "source_split", "question_sha256", "source_row_hash", "compiled_hash"}:
                raise ValueError("Reservation may contain identity/hash fields only")
            if (source_split(row["task_id"]) != row["source_split"] or row["source_split"] not in allowed
                    or any(not isinstance(row[key], str) or not _HASH.fullmatch(row[key])
                           for key in ("question_sha256", "source_row_hash", "compiled_hash"))):
                raise ValueError("Invalid source split or identity checksum")
            if row["task_id"] in ids or row["question_sha256"] in questions:
                raise ValueError("Duplicate identity across reservations")
            ids.add(row["task_id"])
            questions.add(row["question_sha256"])
    return manifest


def _verify_history(repo, root, manifest):
    inventory = _read(root / "exposure_inventory.json")
    if inventory["record_hash"] != manifest["exposure_inventory_hash"]:
        raise ValueError("Exposure inventory changed")
    for item in inventory["files"]:
        path = (repo / item["path"]).resolve()
        if not path.is_relative_to(repo) or not path.is_file() or file_hash(path) != item["sha256"]:
            raise ValueError("Historical exposure input changed after reservation")
    eligibility = _read(root / "eligibility_manifest.json")
    if eligibility["record_hash"] != manifest["eligibility_manifest_hash"]:
        raise ValueError("Eligibility manifest changed")


def prepare_manifest(repo, run_dir, counts, seed, source_path=None):
    """Reserve one shared portfolio confirmation and one independent final panel."""
    repo, run_dir = Path(repo).resolve(), Path(run_dir).resolve()
    registry = repo / "outputs/coevolution_v11"
    if run_dir == registry or not run_dir.is_relative_to(registry):
        raise ValueError("Use a separate run beneath outputs/coevolution_v11")
    if (not isinstance(counts, dict) or set(counts) != {"confirmation", "final"}
            or any(type(n) is not int or n < 1 for n in counts.values())):
        raise ValueError("Positive confirmation/final counts are required")
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("Nonnegative bounded integer seed required")
    snapshot = load_snapshot(repo, source_path)
    snapshot_path = repo / DIRECTORY / "source_snapshot.json" if source_path is None else Path(source_path).resolve()
    settings = {"counts": dict(sorted(counts.items())), "seed": seed,
                "source_snapshot_path": str(snapshot_path.relative_to(repo)),
                "source_snapshot_hash": snapshot["record_hash"], "implementation_hashes": _implementation_hashes()}
    registry.mkdir(parents=True, exist_ok=True)
    with (registry / ".data-reservation.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        path = run_dir / "data_manifest.json"
        if path.exists():
            previous = _validate_manifest(_read(path))
            if previous["settings"] != settings or previous["run_path"] != str(run_dir.relative_to(repo)):
                raise ValueError("Frozen data reservation settings changed")
            _verify_history(repo, run_dir, previous)
            return previous
        eligibility = inspect_compatibility(repo, snapshot_path)
        inventory = _history(repo, run_dir, eligibility["records"])
        excluded_ids, excluded_questions = set(inventory["excluded_ids"]), set(inventory["excluded_question_sha256"])
        pools = {"confirmation": [], "final": []}
        pool_counts, represented = Counter(), set()
        # Prefer the original test representative when an exact question is
        # duplicated across original splits, conservatively keeping it out of
        # confirmation. This priority is fixed before any model call.
        ordered = sorted(eligibility["records"], key=lambda row: (row["source_split"] != "test", row["task_id"]))
        for row in ordered:
            if not row["eligible"]:
                continue
            split = "final" if row["source_split"] == "test" else "confirmation"
            if row["task_id"] in excluded_ids:
                pool_counts[f"{split}:excluded_id"] += 1
            elif row["question_sha256"] in excluded_questions:
                pool_counts[f"{split}:excluded_question"] += 1
            elif row["question_sha256"] in represented:
                pool_counts[f"{split}:duplicate_question"] += 1
            else:
                represented.add(row["question_sha256"])
                pools[split].append({key: value for key, value in row.items() if key not in {"eligible", "reason"}})
        rng, splits = random.Random(seed), {}
        for split in ("confirmation", "final"):
            pool_counts[f"{split}:eligible_unique"] = len(pools[split])
            if len(pools[split]) < counts[split]:
                raise ValueError(f"Not enough statically compatible, unexposed {split} tasks")
            splits[split] = rng.sample(sorted(pools[split], key=lambda row: row["task_id"]), counts[split])
        manifest = core.seal({
            "version": VERSION, "dataset": DATASET, "run_path": str(run_dir.relative_to(repo)),
            "settings": settings, "splits": splits, "pool_counts": dict(sorted(pool_counts.items())),
            "eligibility_manifest_hash": eligibility["record_hash"], "exposure_inventory_hash": inventory["record_hash"],
            "exposure_counts": {"files": len(inventory["files"]), "ids": len(excluded_ids),
                                "question_fingerprints": len(excluded_questions)},
            "notes": ["One shared confirmation panel for a frozen portfolio, not per-history independent panels.",
                      "Confirmation uses original train/validation; final uses original test.",
                      "Eligibility is static and outcome-blind; reference calibration occurs separately.",
                      "No task text, code, tests, arguments or answers are persisted in this manifest.",
                      "Normalized-question dedup cannot exclude semantic duplicates or pretraining exposure."],
        })
        _validate_manifest(manifest)
        write_immutable_json(run_dir / "eligibility_manifest.json", eligibility)
        write_immutable_json(run_dir / "exposure_inventory.json", inventory)
        write_immutable_json(path, manifest)
        return manifest


def _final_authorized(manifest, authorization):
    try:
        core.verify(authorization)
    except (ValueError, TypeError) as exc:
        raise ValueError("Final requires a sealed final_frozen deployment") from exc
    sources = authorization.get("source_hashes")
    if (authorization.get("phase") != "final_frozen"
            or authorization.get("data_manifest_hash") != manifest["record_hash"]
            or not isinstance(authorization.get("policies_hash"), str)
            or not _HASH.fullmatch(authorization["policies_hash"])
            or not isinstance(sources, dict) or not sources
            or any(not isinstance(k, str) or not k or not isinstance(v, str) or not _HASH.fullmatch(v)
                   for k, v in sources.items())):
        raise ValueError("Final deployment lacks a matching policy/source freeze")


def materialize_split(repo, manifest, split, *, final_authorization=None):
    """Return host-only reference/check payloads after the appropriate freeze."""
    repo = Path(repo).resolve()
    _validate_manifest(manifest)
    if split not in manifest["splits"]:
        raise ValueError("Split is not reserved")
    root = (repo / manifest["run_path"]).resolve()
    if not root.is_relative_to(repo / "outputs/coevolution_v11") or _read(root / "data_manifest.json") != manifest:
        raise ValueError("Data manifest differs from the committed reservation")
    if split == "final":
        _final_authorized(manifest, final_authorization)
    elif final_authorization is not None:
        raise ValueError("Final deployment cannot authorize a non-final split")
    if manifest["settings"]["implementation_hashes"] != _implementation_hashes():
        raise ValueError("Frozen compatibility implementation changed")
    snapshot = load_snapshot(repo, repo / manifest["settings"]["source_snapshot_path"])
    if snapshot["record_hash"] != manifest["settings"]["source_snapshot_hash"]:
        raise ValueError("Source snapshot identity changed")
    rows = {row["task_id"]: row for row in _source_rows(repo, snapshot)}
    found = []
    for identity in manifest["splits"][split]:
        row = rows.get(identity["task_id"])
        if (row is None or digest(row) != identity["source_row_hash"]
                or question_fingerprint(row["prompt"]) != identity["question_sha256"]):
            raise ValueError("Reserved source row changed or disappeared")
        compatibility = _compatibility(row)
        compiled = compatibility["compiled"]
        if not compatibility["eligible"] or digest(compiled) != identity["compiled_hash"]:
            raise ValueError("Reserved native assertion compatibility changed")
        found.append({"task_id": row["task_id"], "source_split": source_split(row["task_id"]), "split": split,
                      "prompt": row["prompt"], "reference_code": row["code"], "compiled": compiled,
                      "entry_point": compiled["entry_point"], "public_interface": compiled["public_interface"],
                      "source_row_hash": identity["source_row_hash"], "question_sha256": identity["question_sha256"]})
    return found


def public_task(row):
    """Strict model projection. Native input values and checks never appear."""
    if not isinstance(row, dict) or type(row.get("task_id")) is not int:
        raise ValueError("Malformed public MBPP task identity")
    source_split(row["task_id"])
    interface = row.get("public_interface")
    if (not isinstance(row.get("prompt"), str) or not row["prompt"].strip()
            or not isinstance(row.get("entry_point"), str) or not row["entry_point"].isidentifier()
            or not isinstance(interface, dict)
            or set(interface) != {"entry_point", "positional_argument_counts", "keyword_names"}
            or interface["entry_point"] != row["entry_point"]
            or not isinstance(interface["positional_argument_counts"], list)
            or not interface["positional_argument_counts"]
            or any(type(n) is not int or n < 0 for n in interface["positional_argument_counts"])
            or not isinstance(interface["keyword_names"], list)
            or any(not isinstance(name, str) or not name.isidentifier() for name in interface["keyword_names"])):
        raise ValueError("Public MBPP interface is malformed or contains private fields")
    # JSON-copy also prevents the caller from mutating the private adapter's
    # nested interface after a request hash has been constructed.
    return json.loads(json.dumps({key: row[key] for key in ("task_id", "prompt", "entry_point", "public_interface")}))
