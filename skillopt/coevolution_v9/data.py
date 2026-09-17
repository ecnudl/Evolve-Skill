"""Outcome-blind SearchQA reservations with conservative local exposure exclusion.

Only identity columns are read while selecting all splits together. Gold is read
only by ``materialize_split`` on the host and omitted by ``public_task``. Hashes
provide local integrity, not protection against a malicious host or unknown
external/pretraining exposure.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

from skillopt.coevolution_v5 import core
from skillopt.scope_evolution_v2.source_data import file_hash, question_fingerprint
from skillopt.validator_pilot.api import write_immutable_json

VERSION = "v9-searchqa-reservations-v1"
DEFAULT_DIRECTORY = Path(
    "/Users/dulin/.cache/huggingface/datasets/lucadiliello___searchqa/default/0.0.0/"
    "c1a979068ba118d85467179b704031d113d689cc"
)
DEFAULT_CACHES = {name: DEFAULT_DIRECTORY / f"searchqa-{name}.arrow" for name in ("train", "validation")}
_SPLIT = re.compile(r"(?:train|confirmation)_h[0-9]+_r[0-9]+\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9]+(?:[-_:/.][A-Za-z0-9]+)*")
_HEX = re.compile(r"(?<![0-9a-f])[0-9a-f]{16,64}(?![0-9a-f])")
_JSON_QUESTION = re.compile(r'"question"\s*:\s*("(?:\\.|[^"\\])*")', re.DOTALL)
_EXTENSIONS = frozenset({".json", ".jsonl", ".md", ".txt", ".log"})


def _read(path: Path) -> dict[str, Any]:
    return core.verify(json.loads(path.read_text(encoding="utf-8")))


def _category(split: str) -> str:
    if split == "final":
        return "final"
    if not isinstance(split, str) or not _SPLIT.fullmatch(split):
        raise ValueError("Split must be train_hN_rN, confirmation_hN_rN or final")
    return split.split("_", 1)[0]


def _settings(counts, seed, cache_paths):
    if not isinstance(counts, dict) or not counts or "final" not in counts:
        raise ValueError("Nonempty split counts including final are required")
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise ValueError("seed must be a nonnegative bounded integer")
    for split, n in counts.items():
        _category(split)
        if type(n) is not int or n < 1:
            raise ValueError("Every reserved split count must be a positive integer")
    training = {name.removeprefix("train_") for name in counts if _category(name) == "train"}
    confirming = {name.removeprefix("confirmation_") for name in counts if _category(name) == "confirmation"}
    if not training or training != confirming:
        raise ValueError("Every history/round requires matching train and confirmation splits")
    caches = DEFAULT_CACHES if cache_paths is None else cache_paths
    if not isinstance(caches, dict) or set(caches) != {"train", "validation"}:
        raise ValueError("Exactly train and validation Arrow cache paths are required")
    sources = {name: {"path": str(Path(path).resolve()), "sha256": file_hash(Path(path))}
               for name, path in sorted(caches.items())}
    if sources["train"]["path"] == sources["validation"]["path"]:
        raise ValueError("Train and validation caches must be distinct")
    return {"counts": dict(sorted(counts.items())), "seed": seed, "sources": sources}


def _identities(sources):
    """Never access context or answers, including during deduplication."""
    import pyarrow as pa
    import pyarrow.ipc as ipc

    pools, index = {}, {}
    for source in ("train", "validation"):
        rows, seen = [], set()
        with pa.memory_map(sources[source]["path"], "r") as handle:
            reader = ipc.open_stream(handle)
            columns = {key: reader.schema.get_field_index(key) for key in ("key", "question")}
            if any(column < 0 for column in columns.values()):
                raise ValueError("Source Arrow lacks key/question identity columns")
            for batch in reader:
                for identifier, question in zip(batch.column(columns["key"]).to_pylist(),
                                                batch.column(columns["question"]).to_pylist()):
                    identifier = str(identifier)
                    if not identifier or not isinstance(question, str) or not question.strip():
                        raise ValueError("Source identity is empty or malformed")
                    if identifier in seen:
                        raise ValueError("Duplicate ID within a source Arrow")
                    seen.add(identifier)
                    fingerprint = question_fingerprint(question)
                    if identifier in index and index[identifier] != fingerprint:
                        raise ValueError("One source ID maps to different questions")
                    index[identifier] = fingerprint
                    rows.append({"id": identifier, "question_sha256": fingerprint, "source_split": source})
        pools[source] = rows
    return pools, index


def _history_paths(repo: Path, run_dir: Path):
    """Include quarantined/failed calls and unexecuted historical reservations."""
    paths = set()
    for root in (repo / "outputs", repo / "data/searchqa_split", repo / "data/searchqa_id_split"):
        if root.is_symlink():
            raise ValueError("Exposure input symlinks/outside-repository paths are not supported")
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_relative_to(run_dir):
                continue
            # pathlib does not traverse directory symlinks. Reject them rather
            # than silently calling an incompletely scanned history unexposed.
            if path.is_symlink():
                raise ValueError("Exposure input symlinks/outside-repository paths are not supported")
            if not path.is_file() or path.suffix.lower() not in _EXTENSIONS:
                continue
            resolved = path.resolve()
            if resolved == run_dir or run_dir in resolved.parents:
                continue
            if not resolved.is_relative_to(repo):
                raise ValueError("Exposure input symlinks/outside-repository paths are not supported")
            paths.add(path)
    return sorted(paths)


def _exposure(raw, known_ids, known_questions):
    """Extract identities only; response quality and difficulty are never used."""
    ids, questions = set(), set()

    def text_identities(value):
        # Real SearchQA keys are 32-hex strings; the token path also supports
        # self-contained nonhex fixtures and unprefixed source IDs.
        ids.update(token for token in _HEX.findall(value) if token in known_ids)
        for token in _TOKEN.findall(value):
            if token in known_ids:
                ids.add(token)
            for part in re.split(r"[:/]", token):
                if part in known_ids:
                    ids.add(part)
        for match in _JSON_QUESTION.finditer(value):
            try:
                fingerprint = question_fingerprint(json.loads(match.group(1)))
            except (ValueError, TypeError):
                continue
            if fingerprint in known_questions:
                questions.add(fingerprint)
        # Original SearchQA prompts use this heading, including API records
        # without a separate question field. Later headings end the question.
        for question in value.split("## Question\n")[1:]:
            fingerprint = question_fingerprint(question.split("\n## ", 1)[0])
            if fingerprint in known_questions:
                questions.add(fingerprint)

    text_identities(raw)
    try:
        stack = [json.loads(raw)]
    except ValueError:
        stack = []
        # JSONL may have an interrupted last line. Even malformed text above
        # still conservatively contributes any identity tokens it contains.
        for line in raw.splitlines():
            try:
                stack.append(json.loads(line))
            except ValueError:
                continue
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            question = value.get("question")
            if isinstance(question, str):
                fingerprint = question_fingerprint(question)
                if fingerprint in known_questions:
                    questions.add(fingerprint)
            fingerprint = value.get("question_sha256")
            if isinstance(fingerprint, str) and fingerprint in known_questions:
                questions.add(fingerprint)
            # Old reservations may contain a question-only exclusion list.
            excluded = value.get("excluded_question_sha256", [])
            if isinstance(excluded, list):
                questions.update(q for q in excluded if isinstance(q, str) and q in known_questions)
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
        elif isinstance(value, str):
            if value in known_ids:
                ids.add(value)
            # A historical API may use ``query``/``question_text`` or store a
            # question as a list item. Equality to a known identity is enough;
            # no field-name or outcome-dependent eligibility is required.
            fingerprint = question_fingerprint(value)
            if fingerprint in known_questions:
                questions.add(fingerprint)
            # Nested JSON prompts can be escaped more than once. Decode only
            # JSON-looking strings, never evaluate code or alter an artifact.
            if "question" in value.casefold() or "## Question" in value:
                text_identities(value)
                if value.lstrip().startswith(("{", "[")):
                    try:
                        nested = json.loads(value)
                    except ValueError:
                        continue
                    if isinstance(nested, (dict, list)):
                        stack.append(nested)
    return ids, questions


def _history(repo, run_dir, index):
    known_ids, known_questions = set(index), set(index.values())
    ids, questions, files = set(), set(), []
    for path in _history_paths(repo, run_dir):
        data = path.read_bytes()
        try:
            raw = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Exposure text is not UTF-8: {path.relative_to(repo)}") from exc
        found_ids, found_questions = _exposure(raw, known_ids, known_questions)
        ids.update(found_ids)
        questions.update(found_questions)
        # Store every scanned input, even a zero-match file, so resumption does
        # not silently use a changed prior history or newly discover outcomes.
        files.append({"path": str(path.relative_to(repo)), "sha256": hashlib.sha256(data).hexdigest(),
                      "matched_ids": len(found_ids), "matched_questions": len(found_questions)})
    questions.update(index[identifier] for identifier in ids)
    return core.seal({"version": VERSION + "-exposure", "files": files,
                      "excluded_ids": sorted(ids), "excluded_question_sha256": sorted(questions)})


def _validate(manifest):
    core.verify(manifest)
    if manifest.get("version") != VERSION:
        raise ValueError("Unrecognized data manifest version")
    settings, splits = manifest["settings"], manifest["splits"]
    if set(settings["counts"]) != set(splits):
        raise ValueError("Reservation split names differ from frozen counts")
    ids, fingerprints = set(), set()
    for split, rows in splits.items():
        source = "train" if _category(split) == "train" else "validation"
        if len(rows) != settings["counts"][split]:
            raise ValueError("Reservation split count changed")
        for row in rows:
            if set(row) != {"id", "question_sha256", "source_split"}:
                raise ValueError("Reservation entries may contain identities only")
            if (row["source_split"] != source or not isinstance(row["id"], str)
                    or not row["id"] or not _HASH.fullmatch(row["question_sha256"])):
                raise ValueError("Malformed reserved source identity")
            if row["id"] in ids or row["question_sha256"] in fingerprints:
                raise ValueError("Duplicate identity across reserved splits")
            ids.add(row["id"])
            fingerprints.add(row["question_sha256"])
    return manifest


def _verify_inputs(repo, run_dir, manifest):
    inventory = _read(run_dir / "exposure_inventory.json")
    if inventory["record_hash"] != manifest["exposure_inventory_hash"]:
        raise ValueError("Exposure inventory changed")
    for item in inventory["files"]:
        path = (repo / item["path"]).resolve()
        if not path.is_relative_to(repo) or not path.is_file() or file_hash(path) != item["sha256"]:
            raise ValueError("Historical exposure input changed after reservation")
    return inventory


def prepare_manifest(repo, run_dir, counts: dict[str, int], seed: int, cache_paths=None):
    """Reserve every history/round and final ID together, without reading gold.

    Reservation writes are serialised across V9 runs. Resuming checks the old
    snapshot, not a fresh scan that would accidentally exclude its own IDs.
    """
    repo, run_dir = Path(repo).resolve(), Path(run_dir).resolve()
    registry = repo / "outputs/coevolution_v9"
    if run_dir == registry or not run_dir.is_relative_to(registry):
        raise ValueError("Use a separate run beneath outputs/coevolution_v9")
    settings = _settings(counts, seed, cache_paths)
    registry.mkdir(parents=True, exist_ok=True)
    with (registry / ".data-reservation.lock").open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        path = run_dir / "data_manifest.json"
        if path.exists():
            previous = _validate(_read(path))
            if previous["settings"] != settings or previous["run_path"] != str(run_dir.relative_to(repo)):
                raise ValueError("Data reservation settings changed; use a new run directory")
            _verify_inputs(repo, run_dir, previous)
            return previous
        pools, index = _identities(settings["sources"])
        inventory = _history(repo, run_dir, index)
        excluded_ids = set(inventory["excluded_ids"])
        excluded_questions = set(inventory["excluded_question_sha256"])
        represented, eligible, pool_counts = set(), {}, {}
        for source in ("train", "validation"):
            stats = Counter(source_rows=len(pools[source]))
            available = {}
            for row in sorted(pools[source], key=lambda row: row["id"]):
                fingerprint = row["question_sha256"]
                if row["id"] in excluded_ids:
                    stats["excluded_by_id"] += 1
                elif fingerprint in excluded_questions:
                    stats["excluded_by_question"] += 1
                elif fingerprint in represented or fingerprint in available:
                    stats["duplicate_questions"] += 1
                else:
                    available[fingerprint] = row
            represented.update(available)
            eligible[source] = sorted(available.values(), key=lambda row: row["id"])
            stats["eligible_unique_questions"] = len(available)
            pool_counts[source] = dict(stats)
        rng = random.Random(seed)
        splits = {}
        for source in ("train", "validation"):
            names = [name for name in sorted(counts)
                     if ("train" if _category(name) == "train" else "validation") == source]
            required = sum(counts[name] for name in names)
            if required > len(eligible[source]):
                raise ValueError(f"Not enough outcome-blind, unexposed {source} questions")
            selected, offset = rng.sample(eligible[source], required), 0
            for name in names:
                splits[name] = selected[offset:offset + counts[name]]
                offset += counts[name]
        manifest = core.seal({
            "version": VERSION, "dataset": "lucadiliello/searchqa", "settings": settings,
            "run_path": str(run_dir.relative_to(repo)), "splits": splits, "pool_counts": pool_counts,
            "exposure_inventory_hash": inventory["record_hash"],
            "exposure_counts": {"files": len(inventory["files"]), "ids": len(excluded_ids),
                                "question_fingerprints": len(excluded_questions)},
            "notes": ["All splits are reserved before outcomes, using only key/question columns.",
                      "Train samples original train; confirmation/final sample original validation.",
                      "Question identities are deduplicated across caches and all reserved splits.",
                      "Historical quarantine and unused reservations remain exposure.",
                      "Exact normalized-question deduplication cannot detect semantic duplicates or pretraining exposure.",
                      "No question, context, answer or outcome is persisted by this manifest."],
        })
        _validate(manifest)
        write_immutable_json(run_dir / "exposure_inventory.json", inventory)
        write_immutable_json(path, manifest)
        return manifest


def materialize_split(repo, manifest, split, *, final_authorization=None):
    """Materialize host-only rows; final requires the driver's sealed policy freeze."""
    import pyarrow as pa
    import pyarrow.ipc as ipc

    repo = Path(repo).resolve()
    _validate(manifest)
    if split not in manifest["splits"]:
        raise ValueError("Split was not reserved")
    path = (repo / manifest["run_path"] / "data_manifest.json").resolve()
    if not path.is_relative_to(repo / "outputs/coevolution_v9") or _read(path) != manifest:
        raise ValueError("Manifest does not match the committed local reservation")
    if _category(split) == "final":
        try:
            authorization = core.verify(final_authorization)
        except (TypeError, ValueError) as exc:
            raise ValueError("Final requires a sealed final_frozen authorization") from exc
        sources = authorization.get("source_hashes")
        if (authorization.get("phase") != "final_frozen"
                or authorization.get("data_manifest_hash") != manifest["record_hash"]
                or not isinstance(authorization.get("policies_hash"), str)
                or not _HASH.fullmatch(authorization["policies_hash"])
                or not isinstance(sources, dict) or not sources
                or any(not isinstance(k, str) or not k or not isinstance(v, str) or not _HASH.fullmatch(v)
                       for k, v in sources.items())):
            raise ValueError("Final authorization lacks the matching policy/source freeze")
    elif final_authorization is not None:
        raise ValueError("Final authorization cannot authorize a non-final phase")
    source = "train" if _category(split) == "train" else "validation"
    cache = manifest["settings"]["sources"][source]
    if file_hash(Path(cache["path"])) != cache["sha256"]:
        raise ValueError("Source Arrow changed after reservation")
    wanted = {row["id"]: row["question_sha256"] for row in manifest["splits"][split]}
    found = {}
    with pa.memory_map(cache["path"], "r") as handle:
        reader = ipc.open_stream(handle)
        columns = {name: reader.schema.get_field_index(name) for name in ("key", "question", "context", "answers")}
        if any(column < 0 for column in columns.values()):
            raise ValueError("Source Arrow missing a required task field")
        for batch in reader:
            for index, identifier in enumerate(batch.column(columns["key"]).to_pylist()):
                identifier = str(identifier)
                if identifier not in wanted:
                    continue
                row = {name: batch.column(column)[index].as_py() for name, column in columns.items()}
                row["key"] = identifier
                if identifier in found or question_fingerprint(row["question"]) != wanted[identifier]:
                    raise ValueError("Selected question identity changed")
                if not isinstance(row["context"], str) or not isinstance(row["answers"], list):
                    raise ValueError("Source payload does not have the native SearchQA schema")
                if not row["answers"] or any(not isinstance(answer, str) for answer in row["answers"]):
                    raise ValueError("Source answers are missing or malformed")
                found[identifier] = row
    if set(found) != set(wanted):
        raise ValueError("Selected source IDs are missing from the cache")
    return [found[row["id"]] for row in manifest["splits"][split]]


def public_task(row):
    """Allowlist the model-visible fields; never copy gold or host metadata."""
    if (not isinstance(row, dict) or any(name not in row for name in ("key", "question", "context"))
            or any(not isinstance(row[name], str) or not row[name] for name in ("key", "question"))
            or not isinstance(row["context"], str)):
        raise ValueError("Malformed SearchQA public task")
    return {name: row[name] for name in ("key", "question", "context")}
