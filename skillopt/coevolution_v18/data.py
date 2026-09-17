"""Outcome-blind two-domain reservations for the public V18 experiment.

Preparation reads SearchQA identities and statically inspects MBPP compatibility;
it never executes benchmark code. All phases are reserved together. Materialized
answers, reference code and native assertions are HOST ONLY, not model prompts.
"""

from __future__ import annotations

import fcntl
import hashlib
import re
from collections import Counter
from pathlib import Path

from skillopt.coevolution_v5 import core
from skillopt.coevolution_v9 import data as qa
from skillopt.coevolution_v11 import data as mbpp
from skillopt.scope_evolution_v2.source_data import file_hash, question_fingerprint
from skillopt.validator_pilot.api import digest, write_immutable_json

VERSION = "v18-public-two-domain-reservations-v1"
DOMAINS = ("searchqa", "coding")
PHASES = ("development", "confirmation", "final")
DEFAULT_COUNTS = {"development": 12, "confirmation": 12, "final": 24}
SOURCE_SPLITS = {
    "searchqa": {"development": "train", "confirmation": "validation", "final": "validation"},
    "coding": {"development": "train", "confirmation": "validation", "final": "test"},
}
_HASH = re.compile(r"[0-9a-f]{64}\Z")


def _read(path):
    return core.verify(mbpp._json(Path(path).read_text(encoding="utf-8")))


def safe_root(repo, run_dir):
    repo = Path(repo).resolve()
    path = Path(run_dir)
    if not path.is_absolute():
        path = repo / path
    # Resolve only after rejecting symlinks; otherwise the evidence of traversal
    # could disappear, including symlinks that remain inside the registry.
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError("V18 reservation paths must not traverse symlinks")
    path = path.resolve()
    registry = repo / "outputs/coevolution_v18"
    if path == registry or not path.is_relative_to(registry):
        raise ValueError("Use a separate run beneath outputs/coevolution_v18")
    return path


def implementation_hashes():
    root = Path(__file__).resolve().parents[2]
    names = (*mbpp._implementation_hashes(), "skillopt/coevolution_v9/data.py",
             "skillopt/coevolution_v18/data.py", "skillopt/coevolution_v5/core.py",
             "skillopt/scope_evolution_v2/source_data.py", "skillopt/validator_pilot/api.py")
    return {name: file_hash(root / name) for name in sorted(set(names))}


def _settings(repo, counts, seed, qa_cache_paths, mbpp_source_path):
    if (not isinstance(counts, dict) or set(counts) != set(PHASES)
            or any(type(n) is not int or n < 1 for n in counts.values())):
        raise ValueError("Positive development/confirmation/final counts are required")
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("seed must be a bounded nonnegative integer")
    caches = qa.DEFAULT_CACHES if qa_cache_paths is None else qa_cache_paths
    if not isinstance(caches, dict) or set(caches) != {"train", "validation"}:
        raise ValueError("Exactly train and validation SearchQA caches are required")
    sources = {name: {"path": str(Path(path).resolve()), "sha256": file_hash(Path(path))}
               for name, path in sorted(caches.items())}
    if sources["train"]["path"] == sources["validation"]["path"]:
        raise ValueError("SearchQA source splits must use distinct caches")
    source_path = repo / mbpp.DIRECTORY / "source_snapshot.json" if mbpp_source_path is None else Path(mbpp_source_path).resolve()
    snapshot = mbpp.load_snapshot(repo, source_path)
    return {"counts": dict(sorted(counts.items())), "seed": seed, "qa_sources": sources,
            "mbpp_source_snapshot_path": str(source_path.relative_to(repo)),
            "mbpp_source_snapshot_hash": snapshot["record_hash"],
            "implementation_hashes": implementation_hashes()}


def _catalog_only(repo, path, raw):
    versions = {"coevolution_v10": "v10-mbpp-sanitized-data-v1-eligibility",
                "coevolution_v11": mbpp.VERSION + "-eligibility"}
    expected = next((version for name, version in versions.items()
                     if path.is_relative_to(repo / "outputs" / name)), None)
    if path.name != "eligibility_manifest.json" or expected is None:
        return False
    if core.verify(mbpp._json(raw)).get("version") != expected:
        raise ValueError("Unknown historical host-only eligibility catalog")
    return True


def _history(repo, run_dir, qa_index, coding_records):
    indexes = {"searchqa": qa_index,
               "coding": {row["task_id"]: row["question_sha256"] for row in coding_records}}
    ids = {"searchqa": set(), "coding": set(mbpp.EXPOSED_IDS) & set(indexes["coding"])}
    ids["coding"].update(row["task_id"] for row in coding_records if row["reason"] == "known_readiness_exposure")
    questions = {domain: set() for domain in DOMAINS}
    files = []
    known_ids = {domain: set(indexes[domain]) for domain in DOMAINS}
    known_questions = {domain: set(indexes[domain].values()) for domain in DOMAINS}
    for path in qa._history_paths(repo, run_dir):
        body = path.read_bytes()
        try:
            raw = body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Historical exposure input is not UTF-8") from exc
        matches = {"searchqa": qa._exposure(raw, known_ids["searchqa"], known_questions["searchqa"])}
        catalog = _catalog_only(repo, path, raw)
        matches["coding"] = (set(), set()) if catalog else mbpp._extract_history(
            raw, known_ids=known_ids["coding"], known_questions=known_questions["coding"],
            mbpp_path="mbpp" in str(path).casefold())
        matched = {}
        for domain, (found_ids, found_questions) in matches.items():
            ids[domain].update(found_ids)
            questions[domain].update(found_questions)
            matched[domain] = {"ids": len(found_ids), "questions": len(found_questions)}
        files.append({"path": str(path.relative_to(repo)), "sha256": hashlib.sha256(body).hexdigest(),
                      "matched": matched, "host_only_eligibility_catalog": catalog})
    excluded = {}
    for domain in DOMAINS:
        questions[domain].update(indexes[domain][identifier] for identifier in ids[domain])
        excluded[domain] = {"dataset": mbpp.DATASET if domain == "coding" else "lucadiliello/searchqa",
                            "excluded_ids": sorted(ids[domain]),
                            "excluded_question_sha256": sorted(questions[domain])}
    return core.seal({"version": VERSION + "-exposure", "files": files, "excluded": excluded,
                      "scope": ["outputs/** (including quarantines and unused reservations)",
                                "data/searchqa_split/**", "data/searchqa_id_split/**"]})


def _verify_history(repo, root, manifest):
    inventory = _read(root / "exposure_inventory.json")
    if inventory["record_hash"] != manifest["exposure_inventory_hash"]:
        raise ValueError("Frozen exposure inventory changed")
    for item in inventory["files"]:
        path = repo / item["path"]
        if (path.is_symlink() or not path.resolve().is_relative_to(repo)
                or not path.is_file() or file_hash(path) != item["sha256"]):
            raise ValueError("Historical exposure input changed after reservation")


def _rank(seed, domain, identity):
    return hashlib.sha256(f"v18-public-transfer-v1|{seed}|{domain}|{identity}".encode()).hexdigest()


def _reserve(settings, qa_pools, coding_records, inventory):
    pools = {domain: {source: [] for source in set(SOURCE_SPLITS[domain].values())} for domain in DOMAINS}
    pool_counts, represented = Counter(), set()
    # Holdout representatives take priority, fixed before outcomes. This also
    # keeps exact cross-domain duplicate questions out of different phases.
    ordered = [("coding", row) for row in sorted(coding_records, key=lambda row: (
        {"test": 0, "validation": 1, "train": 2, "prompt": 3}[row["source_split"]], row["task_id"]))]
    ordered += [("searchqa", row) for source in ("validation", "train")
                for row in sorted(qa_pools[source], key=lambda row: row["id"])]
    excluded_ids = {domain: set(inventory["excluded"][domain]["excluded_ids"]) for domain in DOMAINS}
    excluded_questions = set().union(*(inventory["excluded"][domain]["excluded_question_sha256"] for domain in DOMAINS))
    for domain, row in ordered:
        source = row["source_split"]
        if domain == "coding" and not row["eligible"]:
            pool_counts[f"{domain}:{source}:ineligible"] += 1
            continue
        identifier = row["task_id"] if domain == "coding" else row["id"]
        fingerprint = row["question_sha256"]
        reason = ("excluded_id" if identifier in excluded_ids[domain] else
                  "excluded_question" if fingerprint in excluded_questions else
                  "duplicate_question" if fingerprint in represented else None)
        if reason:
            pool_counts[f"{domain}:{source}:{reason}"] += 1
            continue
        represented.add(fingerprint)
        identity = {"id": str(identifier), "domain": domain, "source_split": source,
                    "question_sha256": fingerprint, "cluster_id": fingerprint}
        if domain == "coding":
            identity.update({"dataset": mbpp.DATASET, "task_id": identifier,
                             "source_row_hash": row["source_row_hash"], "compiled_hash": row["compiled_hash"]})
        pools[domain][source].append(identity)
    splits = {domain: {} for domain in DOMAINS}
    for domain in DOMAINS:
        for source, rows in pools[domain].items():
            pool_counts[f"{domain}:{source}:eligible_unique"] = len(rows)
            rows.sort(key=lambda row: (_rank(settings["seed"], domain, row["id"]), row["id"]))
        for phase in PHASES:
            source, count = SOURCE_SPLITS[domain][phase], settings["counts"][phase]
            pool = pools[domain][source]
            if len(pool) < count:
                raise ValueError(f"Not enough unexposed statically compatible {domain}/{phase} tasks")
            splits[domain][phase] = [{**row, "phase": phase} for row in pool[:count]]
            del pool[:count]
    return splits, dict(sorted(pool_counts.items()))


def validate_manifest(manifest):
    core.verify(manifest)
    if manifest.get("version") != VERSION or set(manifest.get("splits", {})) != set(DOMAINS):
        raise ValueError("Unknown V18 data manifest")
    counts = manifest["settings"]["counts"]
    if set(counts) != set(PHASES) or any(type(n) is not int or n < 1 for n in counts.values()):
        raise ValueError("Malformed frozen phase counts")
    identities, questions = set(), set()
    base_keys = {"id", "domain", "source_split", "question_sha256", "cluster_id", "phase"}
    for domain in DOMAINS:
        if set(manifest["splits"][domain]) != set(PHASES):
            raise ValueError("All three phases must be reserved together")
        for phase, rows in manifest["splits"][domain].items():
            if not isinstance(rows, list) or len(rows) != counts[phase]:
                raise ValueError("Reserved cardinality differs from frozen counts")
            for row in rows:
                keys = base_keys | ({"dataset", "task_id", "source_row_hash", "compiled_hash"} if domain == "coding" else set())
                if set(row) != keys:
                    raise ValueError("Reservation entries may contain identity/hash fields only")
                if (row["domain"] != domain or row["phase"] != phase
                        or row["source_split"] != SOURCE_SPLITS[domain][phase]
                        or not isinstance(row["id"], str) or not row["id"]
                        or not isinstance(row["question_sha256"], str) or not _HASH.fullmatch(row["question_sha256"])
                        or row["cluster_id"] != row["question_sha256"]):
                    raise ValueError("Malformed identity or original source split")
                if domain == "coding" and (row["dataset"] != mbpp.DATASET or str(row["task_id"]) != row["id"]
                        or mbpp.source_split(row["task_id"]) != row["source_split"]
                        or any(not isinstance(row[key], str) or not _HASH.fullmatch(row[key])
                               for key in ("source_row_hash", "compiled_hash"))):
                    raise ValueError("Malformed MBPP reservation")
                if (domain, row["id"]) in identities or row["question_sha256"] in questions:
                    raise ValueError("Duplicate identity or question across reservations")
                identities.add((domain, row["id"]))
                questions.add(row["question_sha256"])
    return manifest


def prepare_manifest(repo, run_dir, counts=None, seed=1801, qa_cache_paths=None, mbpp_source_path=None):
    """Reserve both domains/all phases, without model calls or native execution."""
    repo = Path(repo).resolve()
    root = safe_root(repo, run_dir)
    settings = _settings(repo, DEFAULT_COUNTS if counts is None else counts, seed, qa_cache_paths, mbpp_source_path)
    registry = repo / "outputs/coevolution_v18"
    registry.mkdir(parents=True, exist_ok=True)
    with (registry / ".data-reservation.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        path = root / "data_manifest.json"
        if path.exists():
            previous = validate_manifest(_read(path))
            if previous["settings"] != settings or previous["run_path"] != str(root.relative_to(repo)):
                raise ValueError("Frozen data reservation settings changed")
            _verify_history(repo, root, previous)
            return previous
        eligibility = mbpp.inspect_compatibility(repo, repo / settings["mbpp_source_snapshot_path"])
        qa_pools, qa_index = qa._identities(settings["qa_sources"])
        inventory = _history(repo, root, qa_index, eligibility["records"])
        splits, pool_counts = _reserve(settings, qa_pools, eligibility["records"], inventory)
        manifest = core.seal({
            "version": VERSION, "run_path": str(root.relative_to(repo)), "settings": settings,
            "splits": splits, "pool_counts": pool_counts, "exposure_inventory_hash": inventory["record_hash"],
            "static_eligibility": {"record_hash": eligibility["record_hash"], "counts": eligibility["counts"]},
            "notes": ["Original source splits are preserved: coding train/validation/test; QA train/validation/validation.",
                      "All six panels are one-use reservations; unused finals are also excluded from future experiments.",
                      "Selection is deterministic, outcome-blind and normalized-question deduplicated across phases/domains.",
                      "Static MBPP compatibility is not reference correctness calibration.",
                      "No full eligibility catalog is persisted: a catalog is not wholesale benchmark exposure.",
                      "Local artifact auditing cannot establish absence of semantic duplicates or pretraining contamination."]})
        validate_manifest(manifest)
        write_immutable_json(root / "exposure_inventory.json", inventory)
        write_immutable_json(path, manifest)
        return manifest


def _materialize_qa(manifest, phase):
    import pyarrow as pa
    import pyarrow.ipc as ipc

    selected = manifest["splits"]["searchqa"][phase]
    cache = manifest["settings"]["qa_sources"][SOURCE_SPLITS["searchqa"][phase]]
    if file_hash(Path(cache["path"])) != cache["sha256"]:
        raise ValueError("SearchQA source cache changed after reservation")
    wanted = {row["id"]: row["question_sha256"] for row in selected}
    found = {}
    with pa.memory_map(cache["path"], "r") as handle:
        reader = ipc.open_stream(handle)
        columns = {name: reader.schema.get_field_index(name) for name in ("key", "question", "context", "answers")}
        if any(column < 0 for column in columns.values()):
            raise ValueError("SearchQA source lacks native payload fields")
        for batch in reader:
            for index, identifier in enumerate(batch.column(columns["key"]).to_pylist()):
                identifier = str(identifier)
                if identifier not in wanted:
                    continue
                item = {name: batch.column(column)[index].as_py() for name, column in columns.items()}
                item["key"] = identifier
                if identifier in found or question_fingerprint(item["question"]) != wanted[identifier]:
                    raise ValueError("Selected SearchQA identity changed")
                if (not isinstance(item["context"], str) or not isinstance(item["answers"], list)
                        or not item["answers"] or any(not isinstance(answer, str) for answer in item["answers"])):
                    raise ValueError("SearchQA source payload is malformed")
                found[identifier] = item
    if set(found) != set(wanted):
        raise ValueError("Selected SearchQA IDs disappeared from source")
    return [{**identity, "split": phase, "item": found[identity["id"]]} for identity in selected]


def _materialize_coding(repo, manifest, phase):
    snapshot = mbpp.load_snapshot(repo, repo / manifest["settings"]["mbpp_source_snapshot_path"])
    if snapshot["record_hash"] != manifest["settings"]["mbpp_source_snapshot_hash"]:
        raise ValueError("MBPP snapshot changed after reservation")
    rows = {row["task_id"]: row for row in mbpp._source_rows(repo, snapshot)}
    found = []
    for identity in manifest["splits"]["coding"][phase]:
        row = rows.get(identity["task_id"])
        if (row is None or digest(row) != identity["source_row_hash"]
                or question_fingerprint(row["prompt"]) != identity["question_sha256"]):
            raise ValueError("Selected MBPP row changed or disappeared")
        compatibility = mbpp._compatibility(row)
        compiled = compatibility["compiled"]
        if not compatibility["eligible"] or digest(compiled) != identity["compiled_hash"]:
            raise ValueError("Selected MBPP assertion compatibility changed")
        found.append({**identity, "split": phase, "prompt": row["prompt"], "reference_code": row["code"],
                      "compiled": compiled, "entry_point": compiled["entry_point"],
                      "public_interface": compiled["public_interface"]})
    return found


def materialize_split(repo, manifest, domain, phase, *, final_authorization=None):
    """Read HOST-ONLY payloads; final requires a sealed manifest/candidate freeze.

    ``policies_hash`` in the authorization is the digest of the candidate freeze.
    No source payload is opened before authorization is checked.
    """
    repo = Path(repo).resolve()
    validate_manifest(manifest)
    if domain not in DOMAINS or phase not in PHASES:
        raise ValueError("Unknown V18 domain/phase")
    root = safe_root(repo, repo / manifest["run_path"])
    if _read(root / "data_manifest.json") != manifest:
        raise ValueError("Manifest differs from committed reservation")
    if phase == "final":
        mbpp._final_authorized(manifest, final_authorization)
        histories = final_authorization.get("histories")
        if (not isinstance(histories, list) or not histories
                or final_authorization["policies_hash"] != digest(histories)
                or final_authorization.get("no_more_learning") is not True
                or not isinstance(final_authorization.get("protocol_hash"), str)
                or not _HASH.fullmatch(final_authorization["protocol_hash"])
                or _read(root / "final_freeze.json") != final_authorization):
            raise ValueError("Final requires a committed matching candidate freeze")
    elif final_authorization is not None:
        raise ValueError("Final authorization cannot authorize a non-final phase")
    if manifest["settings"]["implementation_hashes"] != implementation_hashes():
        raise ValueError("Frozen data implementation changed")
    return _materialize_qa(manifest, phase) if domain == "searchqa" else _materialize_coding(repo, manifest, phase)


def public_task(task):
    """Allowlist projection, excluding gold, tests, split labels and host hashes."""
    if task.get("domain") == "searchqa":
        return qa.public_task(task["item"])
    if task.get("domain") == "coding":
        return mbpp.public_task(task)
    raise ValueError("Unknown task domain")
