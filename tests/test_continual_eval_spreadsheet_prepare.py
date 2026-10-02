"""Engineering fixtures for the new private source bridge, never real scores."""
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from scripts import prepare_continual_spreadsheet as preparation
from scripts import prepare_verified400 as source


@pytest.fixture
def staged(tmp_path, monkeypatch):
    repo, cache, output = tmp_path / "repo", tmp_path / "source", tmp_path / "prepared"
    indices = repo / "data/spreadsheetbench_id_split"
    indices.mkdir(parents=True)
    monkeypatch.setattr(source, "SPLITS", {"train": 1, "val": 1, "test": 1})
    (indices / "split_manifest.json").write_text(json.dumps({"source_revision": source.REVISION,
        "source_file": source.FILENAME, "counts": source.SPLITS}))
    metadata, files = [], []
    for number, split in enumerate(source.SPLITS):
        identifier = f"fixture-{number}"
        row = {"id": identifier, "instruction": "Private fixture instruction " + str(number),
               "instruction_type": "Cell-Level Manipulation", "spreadsheet_path": "spreadsheet/" + identifier,
               "answer_position": "A1"}
        metadata.append(row)
        (indices / split).mkdir()
        (indices / split / "items.json").write_text(json.dumps([{key: row[key] for key in
            ("id", "instruction_type", "spreadsheet_path")}]))
        directory = "release/spreadsheet/" + identifier
        files.append((directory + "/1_" + identifier + "_init.xlsx", b"unexecuted fixture input"))
        gold_identifier = identifier if split != "test" else "misnamed"
        files.append((directory + "/1_" + gold_identifier + "_golden.xlsx", b"unexecuted fixture gold"))
    files.append(("release/metadata.json", json.dumps(metadata).encode()))
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as tar:
        for name, body in files:
            member = tarfile.TarInfo(name)
            member.size = len(body)
            tar.addfile(member, io.BytesIO(body))
    archive = stream.getvalue()
    monkeypatch.setattr(source, "ARCHIVE_BYTES", len(archive))
    cache.mkdir()
    source.download(cache, fetch=lambda url, _: archive if url == source.URL else b"license: cc-by-sa-4.0\n")
    return repo, cache, output


def test_prepare_preserves_splits_denominators_and_does_not_guess_gold(staged):
    repo, cache, output = staged
    result = preparation.prepare(repo, cache, output)
    assert result["source_tasks"] == 3
    assert result["unresolved_by_split"] == {"test": 1}
    assert result["panels"]["train"]["status"] == "ready"
    assert result["panels"]["test"]["status"] == "blocked"
    assert result["model_api_calls"] == 0 and not result["final_scoring_performed"]
    panel = json.loads((output / "panels/final.json").read_bytes())
    task = panel["tasks"][0]
    assert len(panel["tasks"]) == 1
    assert not Path(task["private"]["test_files"][0]).exists()
    assert "misnamed" not in task["private"]["test_files"][0]
    assert "Private fixture" not in json.dumps(result)
    assert preparation.prepare(repo, cache, output) == result


def test_prepare_detects_changed_original_archive(staged):
    repo, cache, output = staged
    (cache / source.FILENAME).write_bytes(b"changed")
    with pytest.raises(ValueError, match="Staged official source changed"):
        preparation.prepare(repo, cache, output)
    assert not output.exists()


def test_native_replay_does_not_execute_again_and_checks_fixture_hash(tmp_path, monkeypatch):
    directory = tmp_path / "native_controls"
    directory.mkdir()
    fixture = directory / "input.xlsx"
    fixture.write_bytes(b"fixture")
    (directory / "gold.xlsx").write_bytes(b"fixture")
    monkeypatch.setattr(preparation, "source_identity", lambda: {"fixture.py": "frozen-source"})
    fixture_hashes = {name: hashlib.sha256(b"fixture").hexdigest() for name in ("input.xlsx", "gold.xlsx")}
    report = {"runtime": {"image": "fixture"}, "fixture_hashes": fixture_hashes,
              "version": preparation.VERSION + "-native-controls", "source_identity": preparation.source_identity(),
              "preparation_script_sha256": preparation.datasets.file_hash(preparation.__file__),
              "controls": {name: {"status": status, "cleanup_confirmed": True} for name, status in
                           {"correct": "pass", "wrong": "fail", "dependency_unavailable": "unknown"}.items()}}
    (tmp_path / "native_qualification.json").write_text(json.dumps(report))
    monkeypatch.setattr(preparation.backends, "readiness", lambda *args: pytest.fail("Native repeat called"))
    assert preparation.native_smoke(tmp_path, {"image": "fixture"}) == report
    with pytest.raises(ValueError, match="runtime differs"):
        preparation.native_smoke(tmp_path, {"image": "changed"})
    with monkeypatch.context() as scoped:
        scoped.setattr(preparation, "source_identity", lambda: {"fixture.py": "changed-source"})
        with pytest.raises(ValueError, match="source identity differs"):
            preparation.native_smoke(tmp_path, {"image": "fixture"})
    for field, value in (("status", "fail"), ("cleanup_confirmed", False)):
        previous = report["controls"]["correct"][field]
        report["controls"]["correct"][field] = value
        (tmp_path / "native_qualification.json").write_text(json.dumps(report))
        with pytest.raises(ValueError, match="statuses or cleanup"):
            preparation.native_smoke(tmp_path, {"image": "fixture"})
        report["controls"]["correct"][field] = previous
    for hashes in ({}, {"input.xlsx": fixture_hashes["input.xlsx"]},
                   {"../outside": fixture_hashes["input.xlsx"], "gold.xlsx": fixture_hashes["gold.xlsx"]}):
        report["fixture_hashes"] = hashes
        (tmp_path / "native_qualification.json").write_text(json.dumps(report))
        with pytest.raises(ValueError, match="fixture identities differ"):
            preparation.native_smoke(tmp_path, {"image": "fixture"})
    report["fixture_hashes"] = fixture_hashes
    (tmp_path / "native_qualification.json").write_text(json.dumps(report))
    fixture.write_bytes(b"changed")
    with pytest.raises(ValueError, match="fixture changed"):
        preparation.native_smoke(tmp_path, {"image": "fixture"})


def test_static_qualification_keeps_unknown_tasks_without_final_reads(tmp_path):
    import openpyxl

    from skillopt.continual_eval.datasets import VERSION

    tasks = []
    for number, (position, value) in enumerate((("A1", 2), ("not a region", 2), ("A1", "=1+1"))):
        paths = []
        for role in ("input", "gold"):
            book = openpyxl.Workbook()
            book.active["A1"] = value
            path = tmp_path / f"{number}_{role}.xlsx"
            book.save(path)
            book.close()
            paths.append(str(path))
        tasks.append({"task_id": str(number), "family_id": str(number), "project_id": "", "partition": "development",
                      "public": {"instruction": "fixture", "input_files": paths[:1], "answer_position": position},
                      "private": {"test_files": paths[1:], "answer_position": position}})
    (tmp_path / "panels").mkdir()
    (tmp_path / "panels/development.json").write_text(json.dumps({"version": VERSION, "benchmark": "spreadsheetbench",
        "provenance": "fixture", "dataset_revision": "fixture-v1", "tasks": tasks}))
    report = preparation.qualify_development(tmp_path)
    assert report["tasks"] == 3 and report["ready"] == 1 and report["unknown_risk"] == 2
    assert report["tasks_filtered"] == report["final_workbooks_opened"] == 0
    assert report["unparseable_target"] == report["tasks_with_missing_formula_cache"] == 1
