"""Small synthetic archives only; no workbook/code execution or network."""

import io
import json
import tarfile

import pytest

from scripts import prepare_verified400 as staging


def archive(entries):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        for name, body, kind in entries:
            member = tarfile.TarInfo(name)
            member.type = kind
            member.size = len(body) if kind == tarfile.REGTYPE else 0
            if kind in {tarfile.SYMTYPE, tarfile.LNKTYPE}:
                member.linkname = "/private/secret"
            tar.addfile(member, io.BytesIO(body) if kind == tarfile.REGTYPE else None)
    return output.getvalue()


@pytest.fixture
def source(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    splits = {"train": 1, "val": 1, "test": 1}
    monkeypatch.setattr(staging, "SPLITS", splits)
    location = repo / "data/spreadsheetbench_id_split"
    location.mkdir(parents=True)
    (location / "split_manifest.json").write_bytes(staging.encoded({"source_revision": staging.REVISION,
        "source_file": staging.FILENAME, "counts": splits}))
    items, entries = [], []
    for i, split in enumerate(splits):
        task_id = f"fixture-{i}"
        item = {"id": task_id, "spreadsheet_path": f"spreadsheet/{task_id}", "instruction_type": "Cell-Level Manipulation",
                "instruction": "DO_NOT_PRINT_PRIVATE_INSTRUCTION", "answer_position": "DO_NOT_PRINT_PRIVATE_GOLD_POSITION"}
        items.append(item)
        (location / split).mkdir()
        (location / split / "items.json").write_bytes(staging.encoded([
            {k: item[k] for k in ("id", "spreadsheet_path", "instruction_type") }]))
        entries.extend([(f"release/spreadsheet/{task_id}/initial.xlsx", b"UNEXECUTED_INPUT", tarfile.REGTYPE),
                        (f"release/spreadsheet/{task_id}/golden.xlsx", b"UNEXECUTED_GOLD", tarfile.REGTYPE)])
    entries.append(("release/metadata.json", staging.encoded(items), tarfile.REGTYPE))
    body = archive(entries)
    monkeypatch.setattr(staging, "ARCHIVE_BYTES", len(body))
    calls = []
    def fetch(url, limit):
        calls.append(url)
        return body if url == staging.URL else b"---\nlicense: cc-by-sa-4.0\n---\n"
    return repo, body, fetch, calls, entries


def test_exact_new_target_staging_counts_privacy_and_immutable_replay(source, capsys):
    repo, _, fetch, calls, _ = source
    result = staging.prepare(repo, fetch=fetch)
    assert result["complete"] and result["tasks"] == result["cases"] == 3
    assert result["workbooks"] == 6 and result["regular_files"] == 7
    assert result["split_counts"] == {"train": 1, "val": 1, "test": 1}
    assert result["model_api_calls"] == 0 and not result["workbook_execution_performed"]
    assert calls == [staging.URL, staging.README_URL]
    assert "PRIVATE" not in json.dumps(result) and "GOLD" not in json.dumps(result)
    assert not capsys.readouterr().out
    root = staging.root_path(repo)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    replayed = staging.prepare(repo, fetch=lambda *args: pytest.fail("Network during complete replay"))
    assert replayed == result
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert not (repo / "data/spreadsheetbench_split").exists()
    private = staging.read_sealed(root / "private_inventory.json")
    assert private["host_only"] and not private["model_ready"]
    assert any(row["split"] == "test" for row in private["items"])
    assert root.stat().st_mode & 0o777 == 0o700
    assert (root / "private_inventory.json").stat().st_mode & 0o777 == 0o600


def test_download_only_never_extracts_or_materializes_task_content(source):
    repo, _, fetch, _, _ = source
    result = staging.prepare(repo, download_only=True, fetch=fetch)
    root = staging.root_path(repo)
    assert result["phase"] == "download_only" and not (root / "extracted").exists()
    assert not (root / "private_inventory.json").exists()


@pytest.mark.parametrize("name", ["../outside", "/absolute", "a/../../outside", "C:/drive", "a\\b"])
def test_archive_unsafe_paths_rejected_before_extraction(name):
    with pytest.raises(ValueError):
        staging.regular_members(archive([(name, b"x", tarfile.REGTYPE)]))


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE, tarfile.FIFOTYPE])
def test_archive_links_and_special_members_rejected(kind):
    with pytest.raises(ValueError, match="link or special"):
        staging.regular_members(archive([("unsafe", b"", kind)]))


@pytest.mark.parametrize("names", [["a", "a"], ["A.xlsx", "a.xlsx"], ["parent", "parent/child"], ["PARENT", "parent/child"]])
def test_duplicate_case_and_parent_aliases_rejected(names):
    with pytest.raises(ValueError):
        staging.regular_members(archive([(name, b"x", tarfile.REGTYPE) for name in names]))


@pytest.mark.parametrize("bound", ["MAX_ENTRIES", "MAX_MEMBER_BYTES", "MAX_TOTAL_BYTES", "MAX_TAR_BYTES"])
def test_archive_all_resource_bounds_are_enforced(monkeypatch, bound):
    monkeypatch.setattr(staging, bound, 1)
    with pytest.raises(ValueError, match="bound"):
        staging.regular_members(archive([("a", b"abcd", tarfile.REGTYPE), ("b", b"efgh", tarfile.REGTYPE)]))


def test_existing_user_content_is_never_overwritten(tmp_path):
    target = tmp_path / "owned"
    target.write_bytes(b"user")
    with pytest.raises(ValueError, match="no overwrite"):
        staging.immutable(target, b"different")
    assert target.read_bytes() == b"user"


def test_staging_symlink_target_rejected(tmp_path):
    (tmp_path / "outputs/datasets").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / staging.RELATIVE).symlink_to(outside)
    with pytest.raises(ValueError, match="symlinks"):
        staging.root_path(tmp_path)


def test_mismatched_size_or_license_refuses_source_publication(source):
    repo, body, _, _, _ = source
    with pytest.raises(ValueError, match="byte count"):
        staging.prepare(repo, fetch=lambda *args: b"bad")
    root = staging.root_path(repo)
    assert not (root / staging.FILENAME).exists()
    with pytest.raises(ValueError, match="license"):
        staging.prepare(repo, fetch=lambda url, limit: body if url == staging.URL else b"license: unknown")
    assert not (root / staging.FILENAME).exists()


def test_changed_staged_source_refuses_replay(source):
    repo, _, fetch, _, _ = source
    staging.prepare(repo, download_only=True, fetch=fetch)
    (staging.root_path(repo) / staging.FILENAME).write_bytes(b"changed")
    with pytest.raises(ValueError, match="source changed"):
        staging.prepare(repo, fetch=lambda *args: pytest.fail("Network"))


def test_id_discrepancy_and_missing_gold_fail_closed_without_extraction(source):
    repo, _, _, _, entries = source
    indices, _ = staging.source_indices(repo)
    files = staging.regular_members(archive(entries))
    with pytest.raises(ValueError, match="identities"):
        staging.inventory(files, {k: v for i, (k, v) in enumerate(indices.items()) if i})
    missing = [(name, body) for name, body in files if not name.endswith("fixture-0/golden.xlsx")]
    with pytest.raises(ValueError, match="gold partner"):
        staging.inventory(missing, indices)


def test_ambiguous_directory_or_unrecognized_workbooks_rejected(source):
    repo, body, _, _, _ = source
    files = staging.regular_members(body)
    indices, _ = staging.source_indices(repo)
    with pytest.raises(ValueError, match="ambiguous"):
        staging.inventory(files + [("other/spreadsheet/fixture-0/initial.xlsx", b"input")], indices)
    with pytest.raises(ValueError, match="Unpaired"):
        staging.inventory(files + [("release/spreadsheet/fixture-0/extra.xlsx", b"input")], indices)


def test_index_revision_and_count_changes_refused(source):
    repo, _, fetch, _, _ = source
    manifest = repo / "data/spreadsheetbench_id_split/split_manifest.json"
    value = json.loads(manifest.read_bytes())
    value["source_revision"] = "wrong"
    manifest.write_bytes(staging.encoded(value))
    with pytest.raises(ValueError, match="pinned"):
        staging.prepare(repo, fetch=fetch)
