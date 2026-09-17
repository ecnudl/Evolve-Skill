"""Local-only, outcome-blind SearchQA sampling with explicit exposure exclusions."""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import tempfile
from pathlib import Path
from typing import Any

DEFAULT_CACHE = Path(
    "/Users/dulin/.cache/huggingface/datasets/lucadiliello___searchqa/default/0.0.0/"
    "c1a979068ba118d85467179b704031d113d689cc/searchqa-validation.arrow"
)
MANIFEST_TYPE = "searchqa-source-retention-v2"


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def file_hash(path: Path) -> str:
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_immutable_json(path: Path, value: Any) -> None:
    """Idempotent identical writes, but never overwrite a different artifact."""
    path = Path(path)
    if path.exists():
        if read_json(path) != value:
            raise ValueError(f"Refusing to overwrite changed artifact: {path}")
        return
    write_immutable_text(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def write_immutable_text(path: Path, text: str) -> None:
    """Atomically create a complete file without replacing an existing target."""
    path = Path(path)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"Refusing to overwrite changed artifact: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != text:
                raise ValueError(f"Refusing to overwrite changed artifact: {path}") from None
    finally:
        os.unlink(temporary)


def question_fingerprint(question: str) -> str:
    normalized = re.sub(r"\s+", " ", question).strip().casefold()
    return hashlib.sha256(normalized.encode()).hexdigest()


def historical_exposure(repo: Path, *, exclude_run: Path | None = None) -> dict[str, Any]:
    """Read known SearchQA logs and prior v2 reservations, never v1 test outputs."""
    repo = Path(repo).resolve()
    exclude = Path(exclude_run).resolve() if exclude_run is not None else None
    ids, questions, logs, previous_manifests = set(), set(), [], []
    outputs = repo / "outputs"
    if outputs.exists():
        paths = sorted(path for path in outputs.rglob("results.jsonl")
                       if "searchqa" in str(path.relative_to(outputs)).lower()
                       and (exclude is None or exclude not in path.resolve().parents))
        for path in paths:
            count = 0
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    ids.add(str(row["id"]))
                    if isinstance(row.get("question"), str) and row["question"].strip():
                        questions.add(question_fingerprint(row["question"]))
                    count += 1
            logs.append({"path": str(path.relative_to(repo)), "rows": count, "sha256": file_hash(path)})
        for path in sorted(outputs.rglob("source_manifest.json")):
            if exclude is not None and exclude in path.resolve().parents:
                continue
            previous = read_json(path)
            if previous.get("manifest_type") != MANIFEST_TYPE:
                raise ValueError(f"Unrecognized source manifest; inspect its reservations before sampling: {path}")
            reserved = [item for split in previous["splits"].values() for item in split]
            ids.update(str(item["id"]) for item in reserved)
            questions.update(item["question_sha256"] for item in reserved)
            previous_manifests.append({"path": str(path.relative_to(repo)), "reserved": len(reserved), "sha256": file_hash(path)})
    # Existing materialized splits are conservatively exposed even if a log was
    # removed. This also supplies question fingerprints missing from older logs.
    declared = []
    for split in ("train", "val", "test"):
        path = repo / "data" / "searchqa_split" / split / "items.json"
        if path.exists():
            rows = read_json(path)
            ids.update(str(row["id"]) for row in rows)
            questions.update(question_fingerprint(row["question"]) for row in rows)
            declared.append({"path": str(path.relative_to(repo)), "n": len(rows), "sha256": file_hash(path)})
    return {"excluded_ids": sorted(ids), "excluded_question_sha256": sorted(questions),
            "logs": logs, "declared_old_splits": declared, "previous_source_manifests": previous_manifests,
            "n_excluded_ids": len(ids), "n_excluded_question_fingerprints": len(questions)}


def prepare_source_manifest(repo: Path, run_dir: Path, *, seed: int = 20260908,
                            calibration_n: int = 128, holdout_n: int = 256,
                            cache_path: Path = DEFAULT_CACHE) -> dict[str, Any]:
    """Freeze IDs/fingerprints only. Never extract or persist holdout contexts/answers."""
    import pyarrow as pa
    import pyarrow.ipc as ipc

    if calibration_n < 1 or holdout_n < 1:
        raise ValueError("Both source splits must be nonempty")
    cache_path, run_dir = Path(cache_path).resolve(), Path(run_dir).resolve()
    path = run_dir / "source_manifest.json"
    cache_sha = file_hash(cache_path)
    settings = {"seed": seed, "calibration_n": calibration_n, "holdout_n": holdout_n,
                "cache_path": str(cache_path), "cache_sha256": cache_sha}
    if path.exists():
        previous = read_json(path)
        if previous.get("manifest_type") != MANIFEST_TYPE or previous.get("settings") != settings:
            raise ValueError("Source manifest changed; use a new run directory")
        return previous
    exposure = historical_exposure(repo, exclude_run=run_dir)
    excluded_ids = set(exposure["excluded_ids"])
    excluded_questions = set(exposure["excluded_question_sha256"])
    # Keep one stable representative per normalized question before sampling.
    candidates: dict[str, str] = {}
    source_ids = set()
    id_exclusions = question_exclusions = duplicate_questions = 0
    with pa.memory_map(str(cache_path), "r") as stream:
        reader = ipc.open_stream(stream)
        key_col, question_col = (reader.schema.get_field_index(key) for key in ("key", "question"))
        if key_col < 0 or question_col < 0:
            raise ValueError("Local Arrow lacks SearchQA key/question columns")
        for batch in reader:
            # Deliberately do not convert context/answers columns during sampling.
            for identifier, question in zip(batch.column(key_col).to_pylist(), batch.column(question_col).to_pylist()):
                identifier = str(identifier)
                if identifier in source_ids:
                    raise ValueError("Duplicate IDs in local source Arrow")
                source_ids.add(identifier)
                fingerprint = question_fingerprint(question)
                if identifier in excluded_ids:
                    id_exclusions += 1
                elif fingerprint in excluded_questions:
                    question_exclusions += 1
                elif fingerprint in candidates:
                    duplicate_questions += 1
                    candidates[fingerprint] = min(identifier, candidates[fingerprint])
                else:
                    candidates[fingerprint] = identifier
    eligible = sorted((identifier, fingerprint) for fingerprint, identifier in candidates.items())
    if len(eligible) < calibration_n + holdout_n:
        raise ValueError("Not enough unexposed, deduplicated source questions")
    sampled = random.Random(seed).sample(eligible, calibration_n + holdout_n)
    entries = [{"id": identifier, "question_sha256": fingerprint} for identifier, fingerprint in sampled]
    manifest = {
        "manifest_type": MANIFEST_TYPE, "source_dataset": "lucadiliello/searchqa",
        "source_original_split": "validation", "settings": settings, "exposure": exposure,
        "pool_counts": {"source_rows": len(source_ids), "excluded_by_id": id_exclusions,
                        "excluded_by_question": question_exclusions, "duplicate_pool_questions": duplicate_questions,
                        "eligible_unique_questions": len(eligible)},
        "splits": {"calibration": entries[:calibration_n], "holdout": entries[calibration_n:]},
        "notes": ["All split IDs are selected together before any new task outcome.",
                  "Sampling inspects only IDs and question fingerprints, never gold answers or difficulty scores.",
                  "Previous source manifests reserve both splits, even if their holdout was never executed.",
                  "Exact normalized-question deduplication cannot exclude semantic duplicates or pretraining contamination.",
                  "No holdout context, question text or answers are persisted by this manifest."],
    }
    write_immutable_json(path, manifest)
    return manifest


def materialize_source_split(manifest: dict[str, Any], split: str) -> list[dict[str, Any]]:
    """Read only the selected split's payload; caller must authorize holdout phase."""
    import pyarrow as pa
    import pyarrow.ipc as ipc

    if split not in {"calibration", "holdout"}:
        raise ValueError("Unknown source split")
    path = Path(manifest["settings"]["cache_path"])
    if file_hash(path) != manifest["settings"]["cache_sha256"]:
        raise ValueError("Source Arrow changed after manifest freeze")
    wanted = {item["id"]: item["question_sha256"] for item in manifest["splits"][split]}
    found = {}
    with pa.memory_map(str(path), "r") as stream:
        reader = ipc.open_stream(stream)
        columns = {key: reader.schema.get_field_index(key) for key in ("key", "question", "context", "answers")}
        if any(index < 0 for index in columns.values()):
            raise ValueError("Source Arrow missing required QA fields")
        for batch in reader:
            for index, identifier in enumerate(batch.column(columns["key"]).to_pylist()):
                identifier = str(identifier)
                if identifier not in wanted:
                    continue
                values = {key: batch.column(column)[index].as_py() for key, column in columns.items() if key != "key"}
                if question_fingerprint(values["question"]) != wanted[identifier]:
                    raise ValueError("Selected question changed after manifest freeze")
                found[identifier] = {"id": identifier, **values}
    if set(found) != set(wanted):
        raise ValueError("Selected source IDs missing from local cache")
    return [found[item["id"]] for item in manifest["splits"][split]]
