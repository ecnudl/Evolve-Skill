"""Stage ONE pinned official SpreadsheetBench archive; never execute its data.

The full inventory is HOST-ONLY and contains instructions/answer locations.
CLI output is aggregate counts/checksums only. This is not model-ready data.
"""

from __future__ import annotations

import argparse
import fcntl
import gzip
import hashlib
import io
import json
import os
import re
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parents[1]
RELATIVE = Path("outputs/datasets/verified400_20260915")
REVISION = "ab0b742b0fc95b946f212d80ac7771b5531272e4"
FILENAME = "spreadsheetbench_verified_400.tar.gz"
URL = f"https://huggingface.co/datasets/KAKA22/SpreadsheetBench/resolve/{REVISION}/{FILENAME}"
README_URL = f"https://huggingface.co/datasets/KAKA22/SpreadsheetBench/resolve/{REVISION}/README.md"
ARCHIVE_BYTES = 14958255
VERSION = "verified400-private-staging-v1"
SPLITS = {"train": 80, "val": 40, "test": 280}
MAX_ENTRIES = 10000
MAX_MEMBER_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_TAR_BYTES = MAX_TOTAL_BYTES + 32 * 1024 * 1024


def sha(value):
    return hashlib.sha256(value).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def seal(value):
    return {**value, "record_hash": sha(encoded(value))}


def read_sealed(path):
    value = json.loads(path.read_bytes())
    body = {k: v for k, v in value.items() if k != "record_hash"}
    if sha(encoded(body)) != value.get("record_hash"):
        raise ValueError("Staging receipt checksum mismatch")
    return value


def no_symlinks(path):
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Staging paths may not contain symlinks")


def root_path(repo):
    repo = Path(repo).absolute()
    no_symlinks(repo)
    root = repo / RELATIVE
    no_symlinks(root)
    if root.exists() and not root.is_dir():
        raise ValueError("Exact staging target exists but is not a directory")
    return root


def immutable(path, body):
    """Atomic no-overwrite publication with private file permissions."""
    path = Path(path)
    no_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.exists():
        if not path.is_file() or path.read_bytes() != body:
            raise ValueError("Existing staged file differs; no overwrite permitted")
        return
    descriptor, temporary = tempfile.mkstemp(prefix=".staging-", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != body:
                raise ValueError("Concurrent staging file differs") from None
    finally:
        temporary.unlink(missing_ok=True)


def _fetch(url, maximum):
    import httpx

    with httpx.Client(trust_env=False, timeout=60, follow_redirects=True, max_redirects=8) as client:
        with client.stream("GET", url) as response:
            if response.status_code != 200:
                raise ValueError("Official public download did not return HTTP 200")
            pieces, size = [], 0
            for piece in response.iter_bytes():
                size += len(piece)
                if size > maximum:
                    raise ValueError("Official download exceeds frozen size bound")
                pieces.append(piece)
            return b"".join(pieces)


def download(root, fetch=_fetch):
    receipt = root / "source_snapshot.json"
    if receipt.exists():
        previous = read_sealed(receipt)
        if (previous.get("version") != VERSION or previous.get("revision") != REVISION
                or previous.get("canonical_url") != URL or previous.get("license") != "CC-BY-SA-4.0"):
            raise ValueError("Existing snapshot does not identify the fixed official source")
        for name, row in previous["files"].items():
            if name not in {FILENAME, "UPSTREAM_README.md"}:
                raise ValueError("Unexpected source snapshot member")
            path = root / name
            no_symlinks(path)
            if not path.is_file() or path.stat().st_size != row["bytes"] or sha(path.read_bytes()) != row["sha256"]:
                raise ValueError("Staged official source changed")
        if set(previous["files"]) != {FILENAME, "UPSTREAM_README.md"}:
            raise ValueError("Source snapshot is incomplete")
        if previous["files"][FILENAME]["bytes"] != ARCHIVE_BYTES or previous.get("license_source_url") != README_URL:
            raise ValueError("Source snapshot changed the pinned size or license origin")
        return previous
    archive = fetch(URL, ARCHIVE_BYTES)
    if len(archive) != ARCHIVE_BYTES:
        raise ValueError("Official archive differs from the fixed byte count")
    readme = fetch(README_URL, 128 * 1024)
    if not re.search(rb"license:\s*cc-by-sa-4\.0", readme, re.IGNORECASE):
        raise ValueError("Pinned official README lacks the expected license declaration")
    immutable(root / FILENAME, archive)
    immutable(root / "UPSTREAM_README.md", readme)
    value = seal({"version": VERSION, "revision": REVISION, "canonical_url": URL,
        "license": "CC-BY-SA-4.0", "license_source_url": README_URL,
        "files": {FILENAME: {"sha256": sha(archive), "bytes": len(archive)},
                  "UPSTREAM_README.md": {"sha256": sha(readme), "bytes": len(readme)}},
        "download_only_no_workbook_or_code_execution": True})
    immutable(receipt, encoded(value))
    return value


def member_path(name):
    if not isinstance(name, str) or "\\" in name or "\x00" in name:
        raise ValueError("Unsupported archive path")
    raw = name.split("/")
    if any(part == ".." for part in raw) or name.startswith("/") or ":" in name:
        raise ValueError("Archive path traversal or absolute path")
    path = PurePosixPath(name)
    if path.is_absolute():
        raise ValueError("Absolute archive path")
    return str(path)


def regular_members(archive):
    """Validate ALL members before extracting any file, including case aliases."""
    result, seen, total = [], set(), 0
    # Bound decompression BEFORE tarfile parses extended/PAX header payloads;
    # member-size validation alone does not bound malicious metadata headers.
    with gzip.GzipFile(fileobj=io.BytesIO(archive)) as compressed:
        raw_tar = compressed.read(MAX_TAR_BYTES + 1)
    if len(raw_tar) > MAX_TAR_BYTES:
        raise ValueError("Decompressed tar size bound exceeded")
    with tarfile.open(fileobj=io.BytesIO(raw_tar), mode="r:") as tar:
        for i, member in enumerate(tar):
            if i >= MAX_ENTRIES:
                raise ValueError("Archive entry bound exceeded")
            path = member_path(member.name)
            if not (member.isdir() or member.isfile()):
                raise ValueError("Archive contains link or special member")
            if path == ".":
                if member.isdir():
                    continue
                raise ValueError("Archive root cannot be a file")
            key = path.casefold()
            if key in seen:
                raise ValueError("Archive has duplicate or case-colliding paths")
            seen.add(key)
            if member.isdir():
                continue
            if member.size < 0 or member.size > MAX_MEMBER_BYTES:
                raise ValueError("Archive member size bound exceeded")
            total += member.size
            if total > MAX_TOTAL_BYTES:
                raise ValueError("Archive total size bound exceeded")
            stream = tar.extractfile(member)
            if stream is None:
                raise ValueError("Archive regular file cannot be read")
            body = stream.read(MAX_MEMBER_BYTES + 1)
            if len(body) != member.size:
                raise ValueError("Archive file bytes disagree with member header")
            result.append((path, body))
    if not result:
        raise ValueError("Empty archive")
    paths = {path.casefold() for path, _ in result}
    if any(str(parent) in paths for name in paths for parent in PurePosixPath(name).parents if str(parent) != "."):
        raise ValueError("Archive regular file shadows a parent directory")
    return result


def source_indices(repo):
    location = Path(repo) / "data/spreadsheetbench_id_split"
    no_symlinks(location / "split_manifest.json")
    manifest = json.loads((location / "split_manifest.json").read_bytes())
    if (manifest.get("source_revision") != REVISION or manifest.get("source_file") != FILENAME
            or manifest.get("counts") != SPLITS):
        raise ValueError("Existing split manifest differs from pinned Verified400 source")
    rows, hashes = {}, {"split_manifest.json": sha((location / "split_manifest.json").read_bytes())}
    for split, count in SPLITS.items():
        path = location / split / "items.json"
        no_symlinks(path)
        body = path.read_bytes()
        items = json.loads(body)
        if not isinstance(items, list) or len(items) != count:
            raise ValueError("Split cardinality differs from existing manifest")
        hashes[f"{split}/items.json"] = sha(body)
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item["id"] in rows:
                raise ValueError("Malformed or repeated task identity in existing indices")
            rows[item["id"]] = {"split": split, "index": item}
    return rows, hashes


def _metadata_candidates(files):
    found = []
    for name, body in files:
        if not name.lower().endswith((".json", ".jsonl")):
            continue
        try:
            value = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            try:
                value = [json.loads(line) for line in body.decode().splitlines() if line.strip()]
            except (ValueError, UnicodeDecodeError):
                continue
        if isinstance(value, dict):
            value = value.get("data", value.get("items", value.get("tasks")))
        if (isinstance(value, list) and value and all(isinstance(row, dict) and "id" in row for row in value)
                and any("instruction" in row for row in value)):
            found.append((name, value))
    return found


def inventory(files, indices):
    candidates = _metadata_candidates(files)
    if len(candidates) != 1:
        raise ValueError("Expected exactly one official full task metadata table")
    metadata_path, items = candidates[0]
    tasks, file_map = {}, {name: body for name, body in files}
    for item in items:
        identifier = str(item.get("id", ""))
        if identifier in tasks:
            raise ValueError("Repeated official metadata task identity")
        tasks[identifier] = item
    if set(tasks) != set(indices):
        raise ValueError("Official task identities do not exactly match existing split indices")
    output, workbook_count = [], 0
    for identifier, registration in indices.items():
        item = tasks[identifier]
        for field in ("instruction", "spreadsheet_path", "instruction_type", "answer_position"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError("Official task lacks complete required metadata")
        if item["instruction_type"] != registration["index"]["instruction_type"]:
            raise ValueError("Instruction type differs from registered split")
        # Official spreadsheet_path may use a release-relative prefix. Resolve
        # its suffix to one unique actual archived directory, not arbitrary IO.
        expected = member_path(item["spreadsheet_path"]).rstrip("/")
        directories = {str(PurePosixPath(name).parent) for name in file_map if name.lower().endswith(".xlsx")}
        matches = [name for name in directories if name == expected or name.endswith("/" + expected)]
        if not matches:
            last = PurePosixPath(expected).name
            matches = [name for name in directories if PurePosixPath(name).name == last]
        if len(matches) != 1:
            raise ValueError("Workbook directory is missing or ambiguous")
        directory = matches[0]
        workbooks = sorted(name for name in file_map if str(PurePosixPath(name).parent) == directory and name.lower().endswith(".xlsx"))
        pairs, used = [], set()
        for name in workbooks:
            base = PurePosixPath(name).name
            partner = None
            if base.endswith("_input.xlsx"):
                partner = name[:-len("_input.xlsx")] + "_answer.xlsx"
            elif base.endswith("_init.xlsx"):
                partner = name[:-len("_init.xlsx")] + "_golden.xlsx"
            elif base == "initial.xlsx":
                partner = str(PurePosixPath(name).with_name("golden.xlsx"))
            if partner is None:
                continue
            if partner not in file_map:
                raise ValueError("Input workbook lacks its gold partner")
            pairs.append({"input": {"path": "extracted/" + name, "sha256": sha(file_map[name]), "bytes": len(file_map[name])},
                          "gold": {"path": "extracted/" + partner, "sha256": sha(file_map[partner]), "bytes": len(file_map[partner])}})
            used.update((name, partner))
        if not pairs or used != set(workbooks):
            raise ValueError("Unpaired or unrecognized workbook file in official task directory")
        workbook_count += len(workbooks)
        output.append({"task_id": identifier, "split": registration["split"], "metadata": item,
                       "metadata_hash": sha(encoded(item)), "cases": pairs})
    return {"metadata_source_path": "extracted/" + metadata_path, "items": output, "workbooks": workbook_count,
            "cases": sum(len(row["cases"]) for row in output)}


def prepare(repo=REPO, *, download_only=False, fetch=_fetch):
    repo = Path(repo).absolute()
    root = root_path(repo)
    indices, index_hashes = source_indices(repo)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    lock_path = root / ".staging.lock"
    no_symlinks(lock_path)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        snapshot = download(root, fetch)
        if download_only:
            return {"phase": "download_only", "archive_bytes": ARCHIVE_BYTES,
                    "archive_sha256": snapshot["files"][FILENAME]["sha256"], "model_api_calls": 0}
        files = regular_members((root / FILENAME).read_bytes())
        mapped = inventory(files, indices)
        # Complete safety and identity validation precedes extraction.
        for name, body in files:
            immutable(root / "extracted" / name, body)
        private = seal({"version": VERSION + "-inventory", "host_only": True, "model_ready": False,
            "source_snapshot_hash": snapshot["record_hash"], "index_hashes": index_hashes,
            "split_counts": SPLITS, **mapped,
            "file_inventory": [{"path": "extracted/" + name, "sha256": sha(body), "bytes": len(body)} for name, body in files],
            "test_gold_sealed_host_side_never_model_projection": True,
            "workbook_execution_performed": False, "formula_recalculation_performed": False})
        immutable(root / "private_inventory.json", encoded(private))
        summary = seal({"version": VERSION + "-summary", "complete": True, "staging_only_not_model_ready": True,
            "archive_bytes": ARCHIVE_BYTES, "archive_sha256": snapshot["files"][FILENAME]["sha256"],
            "source_snapshot_hash": snapshot["record_hash"], "private_inventory_hash": private["record_hash"],
            "split_counts": SPLITS, "tasks": len(mapped["items"]), "cases": mapped["cases"],
            "workbooks": mapped["workbooks"], "regular_files": len(files),
            "uncompressed_bytes": sum(len(body) for _, body in files), "model_api_calls": 0,
            "workbook_execution_performed": False, "formula_recalculation_performed": False})
        immutable(root / "staging_summary.json", encoded(summary))
        return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(prepare(download_only=args.download_only), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
