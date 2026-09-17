"""Offline identity isolation tests, with no real payloads or model calls."""

from __future__ import annotations

import json
from copy import deepcopy

import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from skillopt.coevolution_v5 import core
from skillopt.coevolution_v9 import data


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _arrow(path, rows):
    table = pa.Table.from_pylist(rows)
    with pa.OSFile(str(path), "wb") as handle, ipc.new_stream(handle, table.schema) as writer:
        writer.write_table(table)


def _seal(value):
    return core.seal({key: item for key, item in value.items() if key != "record_hash"})


@pytest.fixture
def panel(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    rows = {}
    caches = {}
    for source, offset in (("train", 0), ("validation", 100)):
        rows[source] = [{"key": f"{offset + i:032x}", "question": f"QUESTION_SECRET_{offset + i}",
                         "context": f"CONTEXT_SECRET_{offset + i}", "answers": [f"GOLD_SECRET_{offset + i}"]}
                        for i in range(30)]
        caches[source] = tmp_path / f"{source}.arrow"
        _arrow(caches[source], rows[source])
    return repo, caches, rows


COUNTS = {"train_h0_r0": 3, "confirmation_h0_r0": 4, "final": 5}


def _prepare(panel, name="run", counts=None, seed=17):
    repo, caches, _ = panel
    root = repo / "outputs/coevolution_v9" / name
    return data.prepare_manifest(repo, root, COUNTS if counts is None else counts, seed, caches)


def _authorization(manifest):
    return core.seal({"phase": "final_frozen", "data_manifest_hash": manifest["record_hash"],
                      "policies_hash": "a" * 64, "source_hashes": {"driver.py": "b" * 64}})


def _selected(manifest):
    return [row for split in manifest["splits"].values() for row in split]


def test_identity_only_manifest_and_native_source_split_mapping(panel):
    repo, _, _ = panel
    manifest = _prepare(panel)
    core.verify(manifest)
    assert {name: len(rows) for name, rows in manifest["splits"].items()} == COUNTS
    assert len({row["id"] for row in _selected(manifest)}) == sum(COUNTS.values())
    assert len({row["question_sha256"] for row in _selected(manifest)}) == sum(COUNTS.values())
    for name, rows in manifest["splits"].items():
        assert {row["source_split"] for row in rows} == {"train" if name.startswith("train_") else "validation"}
        assert all(set(row) == {"id", "question_sha256", "source_split"} for row in rows)
    for path in (repo / manifest["run_path"]).glob("*.json"):
        text = path.read_text()
        assert all(marker not in text for marker in ("GOLD_SECRET", "CONTEXT_SECRET", "QUESTION_SECRET"))


def test_sampling_never_requires_gold_or_context_columns(panel):
    _, caches, rows = panel
    for source in caches:
        _arrow(caches[source], [{key: row[key] for key in ("key", "question")} for row in rows[source]])
    manifest = _prepare(panel)
    assert sum(len(v) for v in manifest["splits"].values()) == 12
    with pytest.raises(ValueError, match="required task field"):
        data.materialize_split(panel[0], manifest, "train_h0_r0")


def test_history_excludes_results_materialized_data_api_prompt_and_unused_reservations(panel):
    repo, _, rows = panel
    _write(repo / "data/searchqa_split/train/items.json", [rows["train"][0]])
    _write(repo / "data/searchqa_id_split/val/items.json", [{"id": rows["validation"][0]["key"]}])
    _write(repo / "outputs/quarantined/api/calls/a.json",
           {"request": {"key": "not-the-source-id", "user": json.dumps({"question": rows["train"][1]["question"]})},
            "ok": False, "score": 0})
    _write(repo / "outputs/renamed/api/calls/b.json",
           {"request": {"user": "## Context\nold text\n\n## Question\n" + rows["validation"][1]["question"]}})
    _write(repo / "outputs/unexecuted/source_manifest.json",
           {"splits": {"holdout": [{"question_sha256": data.question_fingerprint(rows["validation"][2]["question"])}]}})
    manifest = _prepare(panel)
    selected = {row["id"] for row in _selected(manifest)}
    assert not selected & {rows[source][i]["key"] for source, i in
                           (("train", 0), ("train", 1), ("validation", 0), ("validation", 1), ("validation", 2))}
    assert manifest["pool_counts"]["train"]["eligible_unique_questions"] == 28
    assert manifest["pool_counts"]["validation"]["eligible_unique_questions"] == 27
    assert manifest["exposure_counts"]["files"] == 5


def test_nested_json_with_case_whitespace_duplicate_and_heading_end(panel):
    repo, caches, rows = panel
    rows["train"][1]["question"] = "  question_secret_0  "
    _arrow(caches["train"], rows["train"])
    nested = json.dumps({"question": rows["train"][0]["question"]})
    _write(repo / "outputs/opaque/a.json", {"request": {"user": json.dumps({"other": nested})}})
    _write(repo / "outputs/opaque/b.json", {"request": {"user": "## Question\n" + rows["validation"][0]["question"]
                                                     + "\n## Instructions\nnot part of question"}})
    manifest = _prepare(panel)
    assert manifest["pool_counts"]["train"]["eligible_unique_questions"] == 28
    assert manifest["pool_counts"]["validation"]["eligible_unique_questions"] == 29


def test_exposure_id_inside_request_key_and_malformed_line(panel):
    repo, _, rows = panel
    path = repo / "outputs/renamed/events.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"key": "history:" + rows["train"][0]["key"] + ":revision"})
                    + '\n{"incomplete":"' + rows["validation"][0]["key"], encoding="utf-8")
    manifest = _prepare(panel)
    assert manifest["exposure_counts"]["ids"] == 2


def test_all_outcomes_excluded_equally(panel):
    repo, _, rows = panel
    for i, score in enumerate((0, 1, None, "unknown")):
        _write(repo / "outputs/anything" / f"{i}.json",
               {"id": rows["train"][i]["key"], "score": score, "ok": bool(i)})
    manifest = _prepare(panel)
    assert manifest["pool_counts"]["train"]["excluded_by_id"] == 4


def test_cross_cache_and_within_cache_normalized_question_deduplication(panel):
    _, caches, rows = panel
    rows["train"][1]["question"] = "  question_secret_0  "
    rows["validation"][0]["question"] = rows["train"][0]["question"]
    rows["validation"][2]["question"] = rows["validation"][1]["question"]
    for source in caches:
        _arrow(caches[source], rows[source])
    manifest = _prepare(panel)
    assert manifest["pool_counts"]["train"]["eligible_unique_questions"] == 29
    assert manifest["pool_counts"]["validation"]["eligible_unique_questions"] == 28
    assert manifest["pool_counts"]["train"]["duplicate_questions"] == 1
    assert manifest["pool_counts"]["validation"]["duplicate_questions"] == 2


def test_unused_first_run_final_is_excluded_from_new_run(panel):
    first = _prepare(panel, "first")
    second = _prepare(panel, "second")
    assert not {r["id"] for r in _selected(first)} & {r["id"] for r in _selected(second)}
    assert not {r["question_sha256"] for r in _selected(first)} & {r["question_sha256"] for r in _selected(second)}
    assert second["exposure_counts"]["ids"] == 12
    assert second["exposure_counts"]["files"] == 2


def test_prepare_resume_no_rescan_no_writes(panel, monkeypatch):
    repo, _, _ = panel
    first = _prepare(panel)
    root = repo / first["run_path"]
    before = {p: p.read_bytes() for p in root.glob("*.json")}
    # A new unrelated historical file is not folded into an already frozen
    # exposure snapshot. This is not permission to reuse a prior reservation.
    _write(repo / "outputs/newly_written/a.json", {"question": "new text"})
    monkeypatch.setattr(data, "_history", lambda *args: pytest.fail("rescan on resume"))
    monkeypatch.setattr(data, "_identities", lambda *args: pytest.fail("identity resampling"))
    assert _prepare(panel) == first
    assert {p: p.read_bytes() for p in root.glob("*.json")} == before


def test_prepare_resume_refuses_changed_old_input(panel):
    repo, _, _ = panel
    path = repo / "outputs/old/a.json"
    _write(path, {"unrelated": 1})
    _prepare(panel)
    _write(path, {"unrelated": 2})
    with pytest.raises(ValueError, match="Historical exposure input changed"):
        _prepare(panel)


@pytest.mark.parametrize("change", ["seed", "counts", "cache"])
def test_prepare_resume_refuses_changed_settings(panel, change):
    _, caches, rows = panel
    _prepare(panel)
    kwargs = {}
    if change == "seed":
        kwargs["seed"] = 2
    elif change == "counts":
        kwargs["counts"] = {**COUNTS, "final": 4}
    else:
        rows["train"][0]["context"] += " changed"
        _arrow(caches["train"], rows["train"])
    with pytest.raises(ValueError, match="settings changed"):
        _prepare(panel, **kwargs)


@pytest.mark.parametrize("counts", [None, {}, {"final": 2}, {"train_h0_r0": 2, "final": 2},
                                     {"train_h0_r0": 2, "confirmation_h1_r0": 2, "final": 2},
                                     {**COUNTS, "dev": 2}, {**COUNTS, "final": 0},
                                     {**COUNTS, "final": -1}, {**COUNTS, "final": True},
                                     {**COUNTS, "final": 1.5}])
def test_invalid_counts(panel, counts):
    repo, caches, _ = panel
    with pytest.raises(ValueError):
        data.prepare_manifest(repo, repo / "outputs/coevolution_v9/run", counts, 1, caches)


@pytest.mark.parametrize("seed", [-1, True, "1", 1.2, 2**64])
def test_invalid_seed(panel, seed):
    with pytest.raises(ValueError, match="seed"):
        _prepare(panel, seed=seed)


def test_insufficient_split_pool_no_partial_manifest(panel):
    with pytest.raises(ValueError, match="Not enough"):
        _prepare(panel, counts={**COUNTS, "final": 40})
    assert not (panel[0] / "outputs/coevolution_v9/run/data_manifest.json").exists()


@pytest.mark.parametrize("location", ["outputs/coevolution_v9", "outputs/elsewhere/run", "unregistered"])
def test_reservation_must_use_global_registry(panel, location):
    repo, caches, _ = panel
    with pytest.raises(ValueError, match="separate run"):
        data.prepare_manifest(repo, repo / location, COUNTS, 1, caches)


@pytest.mark.parametrize("case", ["same_path", "missing", "extra"])
def test_invalid_cache_mapping(panel, case):
    repo, caches, _ = panel
    caches = dict(caches)
    if case == "same_path":
        caches["validation"] = caches["train"]
    elif case == "missing":
        caches.pop("train")
    else:
        caches["test"] = caches["train"]
    with pytest.raises(ValueError):
        data.prepare_manifest(repo, repo / "outputs/coevolution_v9/run", COUNTS, 1, caches)


@pytest.mark.parametrize("source", ["train", "validation"])
def test_duplicate_ids_fail_before_any_reservation(panel, source):
    _, caches, rows = panel
    rows[source][1]["key"] = rows[source][0]["key"]
    _arrow(caches[source], rows[source])
    with pytest.raises(ValueError, match="Duplicate ID"):
        _prepare(panel)


def test_same_source_id_different_question_is_rejected(panel):
    _, caches, rows = panel
    rows["validation"][0]["key"] = rows["train"][0]["key"]
    _arrow(caches["validation"], rows["validation"])
    with pytest.raises(ValueError, match="different questions"):
        _prepare(panel)


def test_three_histories_three_round_names_and_joint_disjointness(panel):
    counts = {**{f"{kind}_h{history}_r{round_index}": 1 for history in range(3) for round_index in range(3)
                 for kind in ("train", "confirmation")}, "final": 5}
    manifest = _prepare(panel, counts=counts)
    assert len(_selected(manifest)) == len({row["question_sha256"] for row in _selected(manifest)}) == 23


@pytest.mark.parametrize("split", ["train_h0_r0", "confirmation_h0_r0"])
def test_host_materialization_and_gold_free_public_projection(panel, split):
    manifest = _prepare(panel)
    rows = data.materialize_split(panel[0], manifest, split)
    assert [row["key"] for row in rows] == [row["id"] for row in manifest["splits"][split]]
    assert all(set(row) == {"key", "question", "context", "answers"} for row in rows)
    for row in rows:
        public = data.public_task({**row, "score": 1, "rubric_gold": "DO_NOT_COPY"})
        assert set(public) == {"key", "question", "context"}
        assert "GOLD_SECRET" not in json.dumps(public) and "DO_NOT_COPY" not in json.dumps(public)


@pytest.mark.parametrize("authorization", [None, "final_frozen", {}, {"phase": "final_frozen"},
                                            {"record_hash": "0" * 64}])
def test_final_refuses_unsealed_authorization(panel, authorization):
    manifest = _prepare(panel)
    with pytest.raises(ValueError, match="sealed final_frozen"):
        data.materialize_split(panel[0], manifest, "final", final_authorization=authorization)


@pytest.mark.parametrize("field,value", [("phase", "development"), ("data_manifest_hash", "c" * 64),
                                          ("policies_hash", ""), ("policies_hash", True),
                                          ("policies_hash", "q" * 64), ("source_hashes", {}),
                                          ("source_hashes", []), ("source_hashes", {"driver": ""}),
                                          ("source_hashes", {"": "b" * 64}),
                                          ("source_hashes", {"driver": 17})])
def test_final_refuses_mismatched_or_incomplete_freeze(panel, field, value):
    manifest = _prepare(panel)
    authorization = _authorization(manifest)
    authorization[field] = value
    with pytest.raises(ValueError, match="matching policy/source freeze"):
        data.materialize_split(panel[0], manifest, "final", final_authorization=_seal(authorization))


def test_final_materializes_only_with_sealed_matching_freeze(panel):
    manifest = _prepare(panel)
    rows = data.materialize_split(panel[0], manifest, "final", final_authorization=_authorization(manifest))
    assert len(rows) == 5
    assert [row["key"] for row in rows] == [row["id"] for row in manifest["splits"]["final"]]


def test_final_authorization_cannot_be_repurposed_as_training_authorization(panel):
    manifest = _prepare(panel)
    with pytest.raises(ValueError, match="non-final"):
        data.materialize_split(panel[0], manifest, "train_h0_r0", final_authorization=_authorization(manifest))


def test_unknown_split_and_uncommitted_manifest_fail(panel):
    manifest = _prepare(panel)
    with pytest.raises(ValueError, match="not reserved"):
        data.materialize_split(panel[0], manifest, "confirmation_h99_r0")
    changed = deepcopy(manifest)
    changed["notes"].append("uncommitted change")
    with pytest.raises(ValueError, match="committed local reservation"):
        data.materialize_split(panel[0], _seal(changed), "train_h0_r0")


def test_materialization_refuses_changed_cache(panel):
    manifest = _prepare(panel)
    with panel[1]["train"].open("ab") as handle:
        handle.write(b"changed")
    with pytest.raises(ValueError, match="Arrow changed"):
        data.materialize_split(panel[0], manifest, "train_h0_r0")


@pytest.mark.parametrize("mutation", ["duplicate", "wrong_source", "extra_payload", "wrong_count"])
def test_resealed_invalid_manifest_still_rejected(panel, mutation):
    manifest = _prepare(panel)
    manifest = deepcopy(manifest)
    rows = manifest["splits"]["train_h0_r0"]
    if mutation == "duplicate":
        rows[1] = deepcopy(rows[0])
    elif mutation == "wrong_source":
        rows[0]["source_split"] = "validation"
    elif mutation == "extra_payload":
        rows[0]["answers"] = ["never legal in manifest"]
    else:
        rows.pop()
    with pytest.raises(ValueError):
        data.materialize_split(panel[0], _seal(manifest), "train_h0_r0")


def test_exposure_inventory_tampering_is_rejected_on_resume(panel):
    manifest = _prepare(panel)
    path = panel[0] / manifest["run_path"] / "exposure_inventory.json"
    inventory = json.loads(path.read_text())
    inventory["excluded_ids"].append("other")
    _write(path, _seal(inventory))
    with pytest.raises(ValueError, match="inventory changed"):
        _prepare(panel)


@pytest.mark.parametrize("row", [{}, {"key": "1", "question": "q"},
                                  {"key": "1", "question": "", "context": "c"},
                                  {"key": "1", "question": "q", "context": []},
                                  {"key": 1, "question": "q", "context": "c"}, None])
def test_public_projection_rejects_malformed_task(row):
    with pytest.raises(ValueError, match="Malformed"):
        data.public_task(row)


def test_nonhex_fixture_identity_and_jsonl_question_extraction():
    index = {"key-001", "key-002"}
    fingerprint = data.question_fingerprint("Question goes here")
    raw = json.dumps({"key": "key-001"}) + "\n" + json.dumps({"question": "  QUESTION   GOES here "})
    ids, questions = data._exposure(raw, index, {fingerprint})
    assert ids == {"key-001"} and questions == {fingerprint}


@pytest.mark.parametrize("field", ["query", "question_text", "unfamiliar_history_field"])
def test_full_question_in_other_historical_field_is_conservatively_exposure(field):
    fingerprint = data.question_fingerprint("Question goes here")
    _, questions = data._exposure(json.dumps({field: "  Question GOES here "}), set(), {fingerprint})
    assert questions == {fingerprint}


def test_sampling_deterministic_across_separate_identical_repositories(panel, tmp_path):
    first = _prepare(panel)
    second_repo = tmp_path / "second_repo"
    second_repo.mkdir()
    second = data.prepare_manifest(second_repo, second_repo / "outputs/coevolution_v9/run", COUNTS, 17, panel[1])
    assert first["splits"] == second["splits"]


def test_exposure_symlinks_are_not_silently_traversed(panel, tmp_path):
    repo, _, _ = panel
    target = tmp_path / "outside.json"
    target.write_text("{}")
    link = repo / "outputs/history/link.json"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symlinks"):
        _prepare(panel)


def test_historical_directory_symlink_is_rejected_instead_of_silently_skipped(panel, tmp_path):
    repo, _, _ = panel
    target = tmp_path / "outside_history"
    target.mkdir()
    _write(target / "history.json", {"exposure": "unscanned"})
    link = repo / "outputs/historical_dir"
    link.parent.mkdir(parents=True)
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        _prepare(panel)
