"""Offline MBPP snapshot/isolation tests; no downloaded code is executed."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5 import core
from skillopt.coevolution_v10 import data
from skillopt.validator_pilot.api import digest


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _seal(value):
    return core.seal({key: item for key, item in value.items() if key != "record_hash"})


def _snapshot(repo, rows):
    root = repo / data.DIRECTORY
    root.mkdir(parents=True, exist_ok=True)
    bodies = {"dataset": json.dumps(rows), "upstream_readme": "Official split metadata fixture",
              "dataset_card": "---\nlicense:\n- cc-by-4.0\n---\n"}
    files = {}
    for name, body in bodies.items():
        path = root / data.FILENAMES[name]
        path.write_text(body, encoding="utf-8")
        files[name] = {"path": str(path.relative_to(repo)), "sha256": data.file_hash(path), "url": data.URLS[name]}
    snapshot = core.seal({"version": data.SOURCE_VERSION, "dataset": data.DATASET, "revision": data.REVISION,
                          "card_revision": data.CARD_REVISION, "license": "CC-BY-4.0", "files": files,
                          "source_counts": data._counts(rows), "total_rows": len(rows)})
    _write(root / "source_snapshot.json", snapshot)
    return snapshot


@pytest.fixture
def panel(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    identifiers = [*range(1, 8), *range(11, 268), *range(511, 554), *range(601, 721)]
    rows = [{"task_id": identifier, "prompt": f"QUESTION_SECRET_{identifier}",
             "code": "def solve(x):\n    return x\n# REFERENCE_SECRET\n", "test_imports": [],
             "test_list": ["assert solve('HIDDEN_ARGUMENT') == 'HIDDEN_ARGUMENT'"]} for identifier in identifiers]
    _snapshot(repo, rows)
    return repo, rows


COUNTS = {"confirmation": 2, "final": 4}


def _prepare(panel, name="run", counts=None, seed=13):
    repo, _ = panel
    return data.prepare_manifest(repo, repo / "outputs/coevolution_v10" / name, COUNTS if counts is None else counts, seed)


def _authorization(manifest):
    return core.seal({"phase": "final_frozen", "data_manifest_hash": manifest["record_hash"],
                      "policies_hash": "a" * 64, "source_hashes": {"driver.py": "b" * 64}})


def _selected(manifest):
    return [row for rows in manifest["splits"].values() for row in rows]


def _record(rows, identifier):
    return next(row for row in rows if row["task_id"] == identifier)


@pytest.mark.parametrize("identifier,expected", [(1, "prompt"), (10, "prompt"), (11, "test"), (510, "test"),
                                                (511, "validation"), (600, "validation"), (601, "train"), (974, "train")])
def test_canonical_source_splits(identifier, expected):
    assert data.source_split(identifier) == expected


@pytest.mark.parametrize("identifier", [0, 975, True, "11", 11.0, None])
def test_invalid_source_identifiers(identifier):
    with pytest.raises(ValueError):
        data.source_split(identifier)


def test_snapshot_assets_and_release_are_verified(panel):
    snapshot = data.load_snapshot(panel[0])
    assert snapshot["source_counts"] == data.PUBLISHED_COUNTS
    assert snapshot["total_rows"] == 427
    assert data.URLS["dataset"].endswith(f"{data.REVISION}/mbpp/sanitized-mbpp.json")
    assert data.CARD_REVISION in data.URLS["dataset_card"]


@pytest.mark.parametrize("asset", ["dataset", "upstream_readme", "dataset_card"])
def test_changed_snapshot_asset_rejected(panel, asset):
    repo, _ = panel
    path = repo / data.DIRECTORY / data.FILENAMES[asset]
    path.write_text(path.read_text() + "changed")
    with pytest.raises(ValueError, match="asset changed"):
        data.load_snapshot(repo)


@pytest.mark.parametrize("field,value", [("revision", "other"), ("card_revision", "other"),
                                          ("license", "Apache-2.0"), ("dataset", "another"),
                                          ("version", "unknown")])
def test_resealed_wrong_release_not_accepted(panel, field, value):
    repo, _ = panel
    path = repo / data.DIRECTORY / "source_snapshot.json"
    snapshot = json.loads(path.read_text())
    snapshot[field] = value
    _write(path, _seal(snapshot))
    with pytest.raises(ValueError, match="pinned official"):
        data.load_snapshot(repo)


def test_snapshot_rejects_noncanonical_cardinality_even_resealed(panel):
    repo, rows = panel
    _snapshot(repo, rows[:-1])
    with pytest.raises(ValueError, match="counts differ"):
        data.load_snapshot(repo)


def test_static_compilation_does_not_execute_reference(panel, monkeypatch):
    from skillopt.coevolution_v10 import executor

    monkeypatch.setattr(executor, "run_cases", lambda *args, **kwargs: pytest.fail("reference execution in data module"))
    report = data.inspect_compatibility(panel[0])
    assert report["counts"]["test:eligible"] == 257
    assert report["counts"]["train:eligible"] == 120
    assert report["counts"]["validation:eligible"] == 43
    assert report["counts"]["prompt:official_prompt_split"] == 7
    encoded = json.dumps(report)
    assert all(secret not in encoded for secret in ("QUESTION_SECRET", "REFERENCE_SECRET", "HIDDEN_ARGUMENT"))
    assert set(report["implementation_hashes"]) == {"data.py", "assertions.py", "codec.py", "executor.py", "child.py"}


def test_known_id_and_function_exposure_excluded_statically(panel):
    repo, rows = panel
    _record(rows, 601)["task_id"] = 800
    _record(rows, 602)["code"] = "def left_rotate(x):\n    return x\n"
    _record(rows, 602)["test_list"] = ["assert left_rotate(1)==1"]
    _snapshot(repo, rows)
    report = data.inspect_compatibility(repo)
    mapped = {row["task_id"]: row for row in report["records"]}
    assert mapped[800]["reason"] == mapped[602]["reason"] == "known_readiness_exposure"
    manifest = _prepare(panel)
    assert not {800, 602} & {row["task_id"] for row in _selected(manifest)}
    assert manifest["exposure_counts"]["ids"] == 4  # Plus explicitly known prompt IDs 1 and 2.


def test_whole_task_incompatible_when_one_assertion_or_setup_is_unsupported(panel):
    repo, rows = panel
    _record(rows, 601)["test_list"].append("assert sorted(solve([1])) == [1]")
    _record(rows, 602)["test_imports"] = ["import os"]
    _record(rows, 603)["code"] = "import os\ndef solve(x): return x"
    _snapshot(repo, rows)
    report = data.inspect_compatibility(repo)
    mapped = {row["task_id"]: row for row in report["records"]}
    assert mapped[601]["reason"] == mapped[602]["reason"] == "unsupported_native_assertions"
    assert mapped[603]["reason"] == "unsupported_reference_ast"
    assert all(mapped[identifier]["compiled_hash"] is None for identifier in (601, 602, 603))


@pytest.mark.parametrize("code", ["def different_entry(x): return x", "entry = lambda x: x",
                                   "def entry(x): return x\ndef entry(x): return x"])
def test_reference_must_statically_define_one_declared_entry_function(code):
    row = {"code": code, "test_imports": [], "test_list": ["assert entry(1)==1"]}
    assert data._compatibility(row) == {"eligible": False, "reason": "unsupported_reference_interface", "compiled": None}


def test_manifest_is_identity_only_with_preserved_original_splits(panel):
    manifest = _prepare(panel)
    assert {key: len(rows) for key, rows in manifest["splits"].items()} == COUNTS
    assert len({row["task_id"] for row in _selected(manifest)}) == 6
    assert len({row["question_sha256"] for row in _selected(manifest)}) == 6
    assert {row["source_split"] for row in manifest["splits"]["confirmation"]} <= {"train", "validation"}
    assert {row["source_split"] for row in manifest["splits"]["final"]} == {"test"}
    for row in _selected(manifest):
        assert set(row) == {"task_id", "source_split", "question_sha256", "source_row_hash", "compiled_hash"}
    for path in (panel[0] / manifest["run_path"]).glob("*.json"):
        assert all(secret not in path.read_text() for secret in ("QUESTION_SECRET", "REFERENCE_SECRET", "HIDDEN_ARGUMENT"))


def test_cross_source_duplicates_prefer_original_test_before_sampling(panel):
    repo, rows = panel
    _record(rows, 601)["prompt"] = "  question_secret_11 "
    _record(rows, 602)["prompt"] = _record(rows, 601)["prompt"]
    _snapshot(repo, rows)
    manifest = _prepare(panel)
    assert manifest["pool_counts"]["confirmation:duplicate_question"] == 2
    assert manifest["pool_counts"]["confirmation:eligible_unique"] == 161
    assert manifest["pool_counts"]["final:eligible_unique"] == 257


def test_history_path_metadata_prefix_nested_prompt_and_unused_prior_panel(panel):
    repo, rows = panel
    _write(repo / "outputs/old_mbpp/results.json", {"task_id": 601, "ok": False, "score": None})
    _write(repo / "outputs/renamed/record.json", {"dataset": "MBPP", "task_id": 602, "score": 1})
    _write(repo / "outputs/renamed/api.json", {"key": "mbpp/603/repeat0"})
    _write(repo / "outputs/renamed/nested.json",
           {"request": {"user": json.dumps({"query": _record(rows, 604)["prompt"]})}})
    _write(repo / "outputs/old/reservation.json", {"dataset": data.DATASET, "splits": {"final": [{"task_id": 11}]}})
    manifest = _prepare(panel)
    assert manifest["pool_counts"]["confirmation:excluded_id"] == 3
    assert manifest["pool_counts"]["confirmation:excluded_question"] == 1
    assert manifest["pool_counts"]["final:excluded_id"] == 1
    assert manifest["exposure_counts"]["files"] == 5


def test_failed_truncated_mbpp_jsonl_identity_stays_exposed(panel):
    repo, _ = panel
    path = repo / "outputs/old_mbpp/results.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"task_id":601,"unfinished":')
    manifest = _prepare(panel)
    assert manifest["pool_counts"]["confirmation:excluded_id"] == 1


def test_unrelated_numeric_ids_do_not_consume_mbpp_population(panel):
    _write(panel[0] / "outputs/unrelated/results.json", {"task_id": 601, "dataset": "different-benchmark"})
    manifest = _prepare(panel)
    assert manifest["pool_counts"]["confirmation:eligible_unique"] == 163


def test_question_only_historical_reservation_excludes_aliases(panel):
    repo, rows = panel
    fingerprint = data.question_fingerprint(_record(rows, 601)["prompt"])
    _write(repo / "outputs/prior/reservation.json", {"excluded_question_sha256": [fingerprint]})
    manifest = _prepare(panel)
    assert manifest["pool_counts"]["confirmation:excluded_question"] == 1


def test_unused_first_run_reservations_not_entire_eligibility_pool_are_consumed(panel):
    first = _prepare(panel, "first")
    second = _prepare(panel, "second")
    assert not {row["task_id"] for row in _selected(first)} & {row["task_id"] for row in _selected(second)}
    assert second["pool_counts"]["confirmation:eligible_unique"] == 161
    assert second["pool_counts"]["final:eligible_unique"] == 253
    assert second["exposure_counts"]["ids"] == 8  # Six reserved tasks + known prompt IDs 1,2.


def test_unknown_eligibility_catalog_fails_closed(panel):
    repo, _ = panel
    _write(repo / "outputs/coevolution_v10/old/eligibility_manifest.json", core.seal({"version": "unknown"}))
    with pytest.raises(ValueError, match="Unknown historical"):
        _prepare(panel)


def test_resume_does_not_rescan_reselect_execute_or_rewrite(panel, monkeypatch):
    first = _prepare(panel)
    root = panel[0] / first["run_path"]
    before = {p: p.read_bytes() for p in root.glob("*.json")}
    monkeypatch.setattr(data, "_history", lambda *args: pytest.fail("rescan"))
    monkeypatch.setattr(data, "inspect_compatibility", lambda *args: pytest.fail("reselect"))
    assert _prepare(panel) == first
    assert before == {p: p.read_bytes() for p in root.glob("*.json")}


def test_resume_refuses_changed_scanned_history(panel):
    path = panel[0] / "outputs/history/a.json"
    _write(path, {"unrelated": 1})
    _prepare(panel)
    _write(path, {"unrelated": 2})
    with pytest.raises(ValueError, match="Historical exposure input changed"):
        _prepare(panel)


@pytest.mark.parametrize("change", ["seed", "counts", "implementation"])
def test_resume_refuses_changed_settings(panel, monkeypatch, change):
    _prepare(panel)
    kwargs = {}
    if change == "seed":
        kwargs["seed"] = 99
    elif change == "counts":
        kwargs["counts"] = {"confirmation": 3, "final": 4}
    else:
        monkeypatch.setattr(data, "_implementation_hashes", lambda: {"different": "0" * 64})
    with pytest.raises(ValueError, match="settings changed"):
        _prepare(panel, **kwargs)


@pytest.mark.parametrize("name", ["eligibility_manifest.json", "exposure_inventory.json"])
def test_resume_refuses_resealed_tampered_private_manifests(panel, name):
    first = _prepare(panel)
    path = panel[0] / first["run_path"] / name
    value = json.loads(path.read_text())
    value["extra"] = True
    _write(path, _seal(value))
    with pytest.raises(ValueError, match="changed"):
        _prepare(panel)


@pytest.mark.parametrize("counts", [None, {}, {"confirmation": 2}, {"confirmation": 2, "final": 0},
                                    {"confirmation": 2, "final": True}, {"confirmation": 2, "final": 1.5},
                                    {**COUNTS, "train": 1}, {"confirmation": -1, "final": 4}])
def test_invalid_counts(panel, counts):
    with pytest.raises(ValueError, match="counts"):
        data.prepare_manifest(panel[0], panel[0] / "outputs/coevolution_v10/run", counts, 1)


@pytest.mark.parametrize("seed", [True, -1, 2**64, "1", 1.5])
def test_invalid_seed(panel, seed):
    with pytest.raises(ValueError, match="seed"):
        _prepare(panel, seed=seed)


@pytest.mark.parametrize("location", ["outputs/coevolution_v10", "outputs/coevolution_v9/run", "data/run"])
def test_no_unregistered_reservations(panel, location):
    with pytest.raises(ValueError, match="separate run"):
        data.prepare_manifest(panel[0], panel[0] / location, COUNTS, 1)


def test_not_enough_candidates_fails_without_partial_reservation(panel):
    with pytest.raises(ValueError, match="Not enough"):
        _prepare(panel, counts={"confirmation": 192, "final": 128})
    assert not (panel[0] / "outputs/coevolution_v10/run/data_manifest.json").exists()


def test_materialization_returns_host_only_reference_and_compiled_checks(panel):
    manifest = _prepare(panel)
    rows = data.materialize_split(panel[0], manifest, "confirmation")
    assert [row["task_id"] for row in rows] == [row["task_id"] for row in manifest["splits"]["confirmation"]]
    for row in rows:
        assert "REFERENCE_SECRET" in row["reference_code"]
        assert row["compiled"]["compatible"] and row["compiled"]["checks"] and row["compiled"]["cases"]
        public = data.public_task(row)
        assert set(public) == {"task_id", "prompt", "entry_point", "public_interface"}
        assert "REFERENCE_SECRET" not in json.dumps(public) and "HIDDEN_ARGUMENT" not in json.dumps(public)
        public["public_interface"]["keyword_names"].append("changed")
        assert row["public_interface"]["keyword_names"] == []


@pytest.mark.parametrize("authorization", [None, "final_frozen", {}, {"phase": "final_frozen"}])
def test_final_refuses_string_and_unsealed_authorization(panel, authorization):
    manifest = _prepare(panel)
    with pytest.raises(ValueError, match="sealed final_frozen"):
        data.materialize_split(panel[0], manifest, "final", final_authorization=authorization)


@pytest.mark.parametrize("field,value", [("phase", "development"), ("data_manifest_hash", "c" * 64),
                                          ("policies_hash", ""), ("policies_hash", True),
                                          ("policies_hash", "q" * 64), ("source_hashes", {}),
                                          ("source_hashes", []), ("source_hashes", {"driver": ""}),
                                          ("source_hashes", {"": "b" * 64})])
def test_final_refuses_wrong_or_missing_freeze(panel, field, value):
    manifest = _prepare(panel)
    authorization = _authorization(manifest)
    authorization[field] = value
    with pytest.raises(ValueError, match="matching policy/source freeze"):
        data.materialize_split(panel[0], manifest, "final", final_authorization=_seal(authorization))


def test_final_requires_matching_deployment_and_cannot_authorize_nonfinal(panel):
    manifest = _prepare(panel)
    assert len(data.materialize_split(panel[0], manifest, "final", final_authorization=_authorization(manifest))) == 4
    with pytest.raises(ValueError, match="non-final"):
        data.materialize_split(panel[0], manifest, "confirmation", final_authorization=_authorization(manifest))


def test_unknown_split_and_uncommitted_manifest_rejected(panel):
    manifest = _prepare(panel)
    with pytest.raises(ValueError, match="not reserved"):
        data.materialize_split(panel[0], manifest, "train")
    manifest["notes"].append("tamper")
    with pytest.raises(ValueError, match="committed reservation"):
        data.materialize_split(panel[0], _seal(manifest), "confirmation")


def test_materialization_refuses_compatibility_code_drift(panel, monkeypatch):
    manifest = _prepare(panel)
    monkeypatch.setattr(data, "_implementation_hashes", lambda: {"changed": "0" * 64})
    with pytest.raises(ValueError, match="implementation changed"):
        data.materialize_split(panel[0], manifest, "confirmation")


def test_materialization_refuses_resealed_source_change(panel):
    manifest = _prepare(panel)
    rows = panel[1]
    _record(rows, manifest["splits"]["confirmation"][0]["task_id"])["code"] += "\n# changed"
    _snapshot(panel[0], rows)
    with pytest.raises(ValueError, match="snapshot identity changed"):
        data.materialize_split(panel[0], manifest, "confirmation")


def test_even_recommitted_wrong_question_fingerprint_is_rejected(panel):
    manifest = _prepare(panel)
    manifest["splits"]["confirmation"][0]["question_sha256"] = "d" * 64
    manifest = _seal(manifest)
    _write(panel[0] / manifest["run_path"] / "data_manifest.json", manifest)
    with pytest.raises(ValueError, match="source row changed"):
        data.materialize_split(panel[0], manifest, "confirmation")


@pytest.mark.parametrize("mutation", ["duplicate", "source_split", "payload", "count"])
def test_resealed_invalid_manifest_rejected(panel, mutation):
    manifest = _prepare(panel)
    rows = manifest["splits"]["final"]
    if mutation == "duplicate":
        rows[1] = deepcopy(rows[0])
    elif mutation == "source_split":
        rows[0]["source_split"] = "train"
    elif mutation == "payload":
        rows[0]["answer"] = "unwanted"
    else:
        rows.pop()
    with pytest.raises(ValueError):
        data.materialize_split(panel[0], _seal(manifest), "final", final_authorization=_authorization(manifest))


def test_private_interface_field_is_rejected_not_blindly_copied(panel):
    manifest = _prepare(panel)
    row = data.materialize_split(panel[0], manifest, "confirmation")[0]
    row["public_interface"]["test_list"] = ["SECRET"]
    with pytest.raises(ValueError, match="private fields"):
        data.public_task(row)


def test_snapshot_download_completed_resume_is_offline(panel, monkeypatch):
    import httpx

    monkeypatch.setattr(httpx, "Client", lambda **kwargs: pytest.fail("network on completed snapshot"))
    assert data.download_snapshot(panel[0]) == data.load_snapshot(panel[0])


def test_snapshot_download_fixed_urls_scrubbed_transport_and_immutable_assets(tmp_path, monkeypatch):
    import httpx

    source_repo = tmp_path / "source"
    source_repo.mkdir()
    identifiers = [*range(1, 8), *range(11, 268), *range(511, 554), *range(601, 721)]
    rows = [{"task_id": i, "prompt": f"fixture {i}", "code": "def f(x): return x", "test_imports": [],
             "test_list": ["assert f(1)==1"]} for i in identifiers]
    snapshot = _snapshot(source_repo, rows)
    bodies = {item["url"]: (source_repo / item["path"]).read_bytes() for item in snapshot["files"].values()}
    calls = []

    class Response:
        status_code = 200

        def __init__(self, url):
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_bytes(self):
            yield bodies[self.url]

    class Client:
        def __init__(self, **kwargs):
            assert kwargs == {"trust_env": False, "timeout": 45, "follow_redirects": False}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def stream(self, method, url):
            assert method == "GET"
            calls.append(url)
            return Response(url)

    monkeypatch.setattr(httpx, "Client", Client)
    repo = tmp_path / "destination"
    repo.mkdir()
    downloaded = data.download_snapshot(repo)
    assert calls == list(data.URLS.values())
    assert downloaded["source_counts"] == data.PUBLISHED_COUNTS
    assert all((repo / item["path"]).read_bytes() == bodies[item["url"]] for item in downloaded["files"].values())


def test_history_symlink_directory_fails_closed(panel, tmp_path):
    target = tmp_path / "outside_history"
    target.mkdir()
    link = panel[0] / "outputs/history"
    link.parent.mkdir(parents=True)
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        _prepare(panel)


def test_source_parser_rejects_jsonl_duplicate_keys_and_duplicate_ids(panel):
    with pytest.raises(ValueError):
        data._rows('{"task_id":1}\n{"task_id":2}')
    with pytest.raises(ValueError, match="Duplicate JSON"):
        data._rows('[{"task_id":1,"task_id":2}]')
    with pytest.raises(ValueError, match="Duplicate MBPP"):
        data._rows(json.dumps([panel[1][0], panel[1][0]]))


def test_source_parser_never_evaluates_reference_or_test_code():
    row = {"task_id": 601, "prompt": "p", "code": "raise RuntimeError('HOST EXECUTION')", "test_imports": [],
           "test_list": ["raise RuntimeError('HOST EXECUTION')"]}
    assert data._rows(json.dumps([row])) == [row]


def test_deterministic_sampling_separate_identical_histories(panel, tmp_path):
    first = _prepare(panel)
    other = tmp_path / "other"
    other.mkdir()
    _snapshot(other, panel[1])
    second = data.prepare_manifest(other, other / "outputs/coevolution_v10/run", COUNTS, 13)
    assert first["splits"] == second["splits"]


def test_compiled_identity_is_not_a_private_payload_in_manifest(panel):
    manifest = _prepare(panel)
    host = data.materialize_split(panel[0], manifest, "confirmation")
    assert [digest(row["compiled"]) for row in host] == [row["compiled_hash"] for row in manifest["splits"]["confirmation"]]
