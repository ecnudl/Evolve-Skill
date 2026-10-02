"""Engineering fixtures only: these tests do not measure benchmark performance."""
import copy
import hashlib
import json

import pytest

from skillopt.continual_eval.datasets import (
    BENCHMARKS,
    import_alfworld,
    import_bigcodebench,
    import_korbench,
    import_searchqa,
    import_spreadsheetbench,
    load_panel,
    panel_hash,
    public_view,
    readiness,
    validate_panel,
)


def panel(benchmark="searchqa"):
    public, private = {
        "searchqa": ({"question": "Fixture question", "context": "Fixture context"}, {"answers": ["fixture answer"]}),
        "bigcodebench": ({"prompt": "Fixture function", "entry_point": "f"}, {"test": "# fixture only"}),
        "korbench": ({"rule": "Fixture rule", "question": "Fixture question"},
                     {"answer": "fixture", "category": "logic", "rule_id": "0", "upstream_index": "0"}),
        "spreadsheetbench": ({"instruction": "Fixture change", "input_files": ["input.xlsx"], "answer_position": "A1"},
                             {"test_files": ["expected.xlsx"], "answer_position": "A1"}),
        "alfworld": ({"game_file": "game.tw-pddl"}, {"game_metadata": {"split": "fixture"}}),
    }[benchmark]
    return {"version": "continual-panel-v1", "benchmark": benchmark, "dataset_revision": "fixture-v1",
            "provenance": "fixture", "tasks": [{"task_id": "fixture-task", "family_id": "fixture-family",
            "project_id": "", "partition": "final", "public": public, "private": private}]}


@pytest.mark.parametrize("benchmark", BENCHMARKS)
def test_all_five_normalized_panel_shapes(tmp_path, benchmark):
    source = tmp_path / "panel.json"
    source.write_text(json.dumps(panel(benchmark)))
    data = load_panel(source)
    result = readiness(data)
    assert result["tasks"] == result["families"] == 1
    assert result["provenance"] == "fixture"
    assert result["scope"] == "dataset_only"
    assert result["status"] == ("blocked" if benchmark in {"spreadsheetbench", "alfworld"} else "ready")
    assert len(panel_hash(data)) == 64


def test_only_whitelisted_public_view_and_deepcopy():
    data = panel()
    task = data["tasks"][0]
    view = public_view(task)
    assert set(view) == {"question", "context"}
    assert "fixture answer" not in json.dumps(view)
    view["question"] = "different"
    assert task["public"]["question"] == "Fixture question"


@pytest.mark.parametrize("where,key", [("root", "model"), ("task", "condition"),
                                     ("public", "answers"), ("private", "unused")])
def test_unknown_fields_rejected(where, key):
    data = panel()
    target = data if where == "root" else data["tasks"][0]
    if where in {"public", "private"}:
        target = target[where]
    target[key] = "leak"
    with pytest.raises(ValueError, match="fields"):
        validate_panel(data)


def test_same_family_cross_partition_rejected():
    data = panel()
    other = copy.deepcopy(data["tasks"][0])
    other.update(task_id="second", partition="development")
    data["tasks"].append(other)
    with pytest.raises(ValueError, match="Family partition conflict"):
        validate_panel(data)


def test_duplicate_task_ids_rejected_even_same_partition():
    data = panel()
    data["tasks"].append(copy.deepcopy(data["tasks"][0]))
    with pytest.raises(ValueError, match="Duplicate task_id"):
        validate_panel(data)


def test_project_isolation_not_silently_assumed():
    data = panel()
    data["tasks"][0]["project_id"] = "shared-project"
    other = copy.deepcopy(data["tasks"][0])
    other.update(task_id="second", family_id="other-family", partition="development")
    data["tasks"].append(other)
    assert validate_panel(data) is data  # global project policy belongs to protocol


def test_panel_hash_changes_for_private_or_public_changes():
    data = panel()
    first = panel_hash(data)
    assert panel_hash(copy.deepcopy(data)) == first
    data["tasks"][0]["private"]["answers"] = ["different private"]
    assert panel_hash(data) != first


def test_file_bytes_and_expected_hashes_bound(tmp_path):
    data = panel("spreadsheetbench")
    for name in ("input.xlsx", "expected.xlsx"):
        (tmp_path / name).write_bytes(b"fixture workbook stand-in")
    digest = hashlib.sha256(b"fixture workbook stand-in").hexdigest()
    data["tasks"][0]["private"]["asset_sha256"] = {"input.xlsx": digest}
    path = tmp_path / "panel.json"
    path.write_text(json.dumps(data))
    loaded = load_panel(path)
    assert readiness(loaded)["status"] == "ready"
    first = panel_hash(loaded)
    (tmp_path / "input.xlsx").write_bytes(b"changed bytes")
    assert panel_hash(loaded) != first
    assert readiness(loaded)["asset_failures"] == {"hash_mismatch": 1}


def test_aliased_private_workbook_rejected(tmp_path):
    data = panel("spreadsheetbench")
    data["tasks"][0]["private"]["test_files"] = ["./input.xlsx"]
    path = tmp_path / "panel.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Private workbook exposed"):
        load_panel(path)


def test_other_tasks_private_workbook_cannot_be_public_input():
    data = panel("spreadsheetbench")
    other = copy.deepcopy(data["tasks"][0])
    other["task_id"] = "second"
    other["public"]["input_files"] = ["expected.xlsx"]
    other["private"]["test_files"] = ["another-expected.xlsx"]
    data["tasks"].append(other)
    with pytest.raises(ValueError, match="across tasks"):
        validate_panel(data)


def test_shared_asset_mismatch_not_overwritten_by_unpinned_task(tmp_path):
    source = tmp_path / "game.tw-pddl"
    source.write_bytes(b"fixture")
    data = panel("alfworld")
    data["tasks"][0]["public"]["game_file"] = str(source)
    data["tasks"][0]["private"]["asset_sha256"] = {str(source): "0" * 64}
    other = copy.deepcopy(data["tasks"][0])
    other["task_id"] = "another-task"
    other["private"].pop("asset_sha256")
    data["tasks"].append(other)
    assert readiness(data)["asset_failures"] == {"hash_mismatch": 1}


@pytest.mark.parametrize("text", ['{"version": 1, "version": 2}', '{"extra": NaN}'])
def test_ambiguous_json_rejected(tmp_path, text):
    path = tmp_path / "panel.json"
    path.write_text(text)
    with pytest.raises(ValueError):
        load_panel(path)


@pytest.mark.parametrize("revision", ["main", "latest", "HEAD", ""])
def test_mutable_or_missing_revision_rejected(revision):
    data = panel()
    data["dataset_revision"] = revision
    with pytest.raises(ValueError):
        validate_panel(data)


def test_searchqa_import_materialized_not_manifest(tmp_path):
    row = {"id": "fixture-id", "question": "Fixture question", "context": "Evidence", "answers": ["answer"]}
    path = tmp_path / "items.json"
    path.write_text(json.dumps([row]))
    data = import_searchqa(path, revision="local-fixture-source-v1", family_map={"fixture-id": "reviewed-family"})
    assert data["tasks"][0]["family_id"] == "reviewed-family"
    assert data["tasks"][0]["private"]["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert set(public_view(data["tasks"][0])) == {"question", "context"}
    with pytest.raises(ValueError, match="ID-only"):
        import_searchqa([{"id": "fixture-id"}], revision="v1")


def test_searchqa_question_duplicates_share_family():
    rows = [{"key": "a", "question": " A  Question ", "context": "evidence", "answers": ["x"]},
            {"key": "b", "question": "a question", "context": "other evidence", "answers": ["x"]}]
    data = import_searchqa(rows, revision="fixture-source-v1")
    assert len({task["family_id"] for task in data["tasks"]}) == 1


def test_family_manifest_must_cover_all_imported_rows():
    rows = [{"id": "a", "question": "Q", "context": "C", "answers": ["A"]}]
    with pytest.raises(ValueError, match="Family map lacks"):
        import_searchqa(rows, revision="fixture-v1", family_map={})


def test_bigcodebench_import_drops_solution_and_preserves_test_privately():
    row = {"task_id": "fixture/1", "instruct_prompt": "Write fixture", "complete_prompt": "def f():",
           "entry_point": "f", "test": "# private fixture test", "canonical_solution": "private solution"}
    data = import_bigcodebench([row], revision="fixture-source-v1")
    assert data["tasks"][0]["public"]["prompt"] == "Write fixture"
    assert data["tasks"][0]["private"]["test"] == row["test"]
    assert "private solution" not in json.dumps(data)


def test_kor_join_groups_rule_family():
    rows = [{"idx": i, "rule_id": "r", "question": f"Fixture {i}", "answer": "a"} for i in range(2)]
    rules = [{"idx": "r", "rule_content": "Fixture rule"}]
    data = import_korbench(rows, rules, category="logic", revision="fixture-source-v1")
    assert len({task["family_id"] for task in data["tasks"]}) == 1
    assert data["tasks"][0]["private"]["rule_id"] == "r"
    assert data["tasks"][0]["public"]["rule"] == "Fixture rule"
    with pytest.raises(ValueError, match="missing rule"):
        import_korbench(rows, [{"idx": "other", "rule_content": "rule"}], category="logic", revision="v1")


def test_empty_panels_and_nonjson_native_rejected():
    data = panel()
    data["tasks"] = []
    with pytest.raises(ValueError, match="nonempty"):
        validate_panel(data)
    data = panel()
    data["tasks"][0]["private"]["answers"] = ("tuple",)
    with pytest.raises(ValueError, match="JSON-native"):
        validate_panel(data)


def _sheet_row():
    return {"id": "fixture", "instruction": "Fixture change", "instruction_type": "Cell-Level Manipulation",
            "spreadsheet_path": "spreadsheet/fixture", "answer_position": "A1"}


@pytest.mark.parametrize("names", [("1_fixture_input.xlsx", "1_fixture_answer.xlsx"),
                                  ("1_fixture_init.xlsx", "1_fixture_golden.xlsx"),
                                  ("initial.xlsx", "golden.xlsx")])
def test_spreadsheet_import_supported_release_naming(tmp_path, names):
    directory = tmp_path / "spreadsheet/fixture"
    directory.mkdir(parents=True)
    for name in names:
        (directory / name).write_bytes(b"unexecuted fixture workbook")
    data = import_spreadsheetbench([_sheet_row()], data_root=tmp_path, revision="fixture-source-v1")
    task = data["tasks"][0]
    assert task["public"]["input_files"] == [str(directory / names[0])]
    assert task["public"]["answer_position"] == task["private"]["answer_position"] == "A1"
    assert task["private"]["test_files"] == [str(directory / names[1])]
    assert len(task["private"]["asset_sha256"]) == 2
    assert readiness(data)["status"] == "ready"
    assert names[1] not in json.dumps(public_view(task))


@pytest.mark.parametrize("names", [("initial.xlsx",), ("initial.xlsx", "golden.xlsx", "extra.xlsx"), ()])
def test_spreadsheet_import_rejects_incomplete_and_ambiguous_assets(tmp_path, names):
    directory = tmp_path / "spreadsheet/fixture"
    directory.mkdir(parents=True)
    for name in names:
        (directory / name).write_bytes(b"unexecuted fixture")
    with pytest.raises(ValueError):
        import_spreadsheetbench([_sheet_row()], data_root=tmp_path, revision="fixture-source-v1")


def test_spreadsheet_import_never_guesses_missing_path(tmp_path):
    directory = tmp_path / "different-root/spreadsheet/fixture"
    directory.mkdir(parents=True)
    for name in ("initial.xlsx", "golden.xlsx"):
        (directory / name).write_bytes(b"unexecuted")
    with pytest.raises(ValueError, match="Explicit spreadsheet_path"):
        import_spreadsheetbench([_sheet_row()], data_root=tmp_path, revision="fixture-source-v1")


def test_spreadsheet_manifest_is_not_full_metadata(tmp_path):
    with pytest.raises(ValueError, match="full metadata"):
        import_spreadsheetbench([{"id": "fixture", "spreadsheet_path": "spreadsheet/fixture"}],
                               data_root=tmp_path, revision="fixture-v1")


def _alf_row(trial="a", split="train"):
    return {"id": "fixture-" + trial, "task_type": "pick_and_place_simple",
            "gamefile": f"json_2.1.1/{split}/pick_and_place_simple-object-room/trial_{trial}/game.tw-pddl"}


def test_alfworld_import_binds_support_files_and_families(tmp_path):
    rows = [_alf_row("a"), _alf_row("b")]
    for row in rows:
        path = tmp_path / row["gamefile"]
        path.parent.mkdir(parents=True)
        path.write_bytes(b"unexecuted fixture game")
        path.with_name("traj_data.json").write_text("{}")
    (tmp_path / "logic").mkdir()
    for name in ("alfred.pddl", "alfred.twl2"):
        (tmp_path / "logic" / name).write_bytes(b"unexecuted fixture logic")
    data = import_alfworld(rows, data_root=tmp_path, revision="fixture-v1")
    assert readiness(data)["status"] == "ready"
    assert readiness(data)["assets"] == 6
    assert len({task["family_id"] for task in data["tasks"]}) == 1
    initial_hash = panel_hash(data)
    (tmp_path / "logic/alfred.pddl").write_bytes(b"different logic")
    assert panel_hash(data) != initial_hash
    assert readiness(data)["status"] == "blocked"
    assert set(public_view(data["tasks"][0])) == {"game_file"}


def test_alfworld_missing_data_does_not_become_ready(tmp_path):
    data = import_alfworld([_alf_row()], data_root=tmp_path, revision="fixture-v1")
    assert readiness(data)["asset_failures"] == {"missing_or_not_file": 4}


@pytest.mark.parametrize("path", ["../other/game.tw-pddl", "$ALFWORLD_DATA/game.tw-pddl", "unknown/game.tw-pddl"])
def test_alfworld_import_rejects_unregistered_or_escaping_layout(tmp_path, path):
    row = _alf_row()
    row["gamefile"] = path
    with pytest.raises(ValueError):
        import_alfworld([row], data_root=tmp_path, revision="fixture-v1")


def test_alfworld_support_paths_survive_serialized_roundtrip(tmp_path):
    data = import_alfworld([_alf_row()], data_root=tmp_path, revision="fixture-v1")
    path = tmp_path / "panel.json"
    path.write_text(json.dumps(data))
    loaded = load_panel(path)
    assert panel_hash(loaded) == panel_hash(data)


def test_spreadsheet_symlink_cannot_escape_data_root(tmp_path):
    root = tmp_path / "assets"
    directory = root / "spreadsheet/fixture"
    directory.mkdir(parents=True)
    (directory / "initial.xlsx").write_bytes(b"input")
    hidden = tmp_path / "outside.xlsx"
    hidden.write_bytes(b"not allowed")
    (directory / "golden.xlsx").symlink_to(hidden)
    with pytest.raises(ValueError, match="escapes"):
        import_spreadsheetbench([_sheet_row()], data_root=root, revision="fixture-v1")


def test_spreadsheet_output_region_is_public_and_must_match_native_scoring():
    data = panel("spreadsheetbench")
    assert data["tasks"][0]["public"]["answer_position"] == "A1"
    data["tasks"][0]["private"]["answer_position"] = "B1"
    with pytest.raises(ValueError, match="Public output contract"):
        validate_panel(data)
