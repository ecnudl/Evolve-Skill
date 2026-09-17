"""Synthetic, entirely offline V18 reservation and host-payload boundary tests."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5 import core
from skillopt.coevolution_v11 import data as mbpp
from skillopt.coevolution_v18 import data
from skillopt.scope_evolution_v2.source_data import question_fingerprint
from skillopt.validator_pilot.api import digest
from tests.test_coevolution_v9_data import _arrow
from tests.test_coevolution_v11_data import _snapshot


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _seal(value):
    return core.seal({key: item for key, item in value.items() if key != "record_hash"})


@pytest.fixture
def panel(tmp_path, monkeypatch):
    from skillopt.coevolution_v11 import executor

    monkeypatch.setattr(executor, "run_cases", lambda *a, **kw: pytest.fail("Data preparation executed code"))
    repo = tmp_path / "repo"
    repo.mkdir()
    identifiers = [*range(1, 8), *range(11, 268), *range(511, 554), *range(601, 721)]
    coding = [{"task_id": identifier, "prompt": f"MBPP_QUESTION_SECRET_{identifier}",
               "code": "def solve(x):\n    return x\n# REFERENCE_SECRET\n", "test_imports": [],
               "test_list": ["assert solve('HIDDEN_ARGUMENT') == 'HIDDEN_ARGUMENT'"]} for identifier in identifiers]
    _snapshot(repo, coding)
    caches, qa_rows = {}, {}
    for source, offset in (("train", 0), ("validation", 100)):
        qa_rows[source] = [{"key": f"{offset + i:032x}", "question": f"QA_QUESTION_SECRET_{offset + i}",
                            "context": f"CONTEXT_SECRET_{offset + i}", "answers": [f"GOLD_SECRET_{offset + i}"]}
                           for i in range(32)]
        caches[source] = tmp_path / f"{source}.arrow"
        _arrow(caches[source], qa_rows[source])
    return repo, caches, qa_rows, coding


COUNTS = {"development": 2, "confirmation": 2, "final": 3}


def _prepare(panel, name="run", counts=None, seed=1801):
    repo, caches, _, _ = panel
    return data.prepare_manifest(repo, repo / "outputs/coevolution_v18" / name,
                                 COUNTS if counts is None else counts, seed, qa_cache_paths=caches)


def _selected(manifest, domain=None):
    return [row for name, phases in manifest["splits"].items() if domain is None or name == domain
            for rows in phases.values() for row in rows]


def _authorization(repo, manifest):
    histories = [{"history": "h1", "texts": {"parent": {"searchqa": "parent", "coding": "parent"}}}]
    value = core.seal({"phase": "final_frozen", "data_manifest_hash": manifest["record_hash"],
                       "histories": histories, "policies_hash": digest(histories),
                       "protocol_hash": "a" * 64, "source_hashes": {"driver.py": "b" * 64},
                       "no_more_learning": True})
    _write(repo / manifest["run_path"] / "final_freeze.json", value)
    return value


def _tree(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_identity_only_static_reservation_and_actual_source_splits(panel):
    manifest = _prepare(panel)
    data.validate_manifest(manifest)
    assert len(_selected(manifest)) == 14
    assert len({row["cluster_id"] for row in _selected(manifest)}) == 14
    for domain in data.DOMAINS:
        assert {phase: len(rows) for phase, rows in manifest["splits"][domain].items()} == COUNTS
        for phase, rows in manifest["splits"][domain].items():
            assert {row["source_split"] for row in rows} == {data.SOURCE_SPLITS[domain][phase]}
            assert {row["phase"] for row in rows} == {phase}
    root = panel[0] / manifest["run_path"]
    assert not (root / "eligibility_manifest.json").exists()
    for path in root.glob("*.json"):
        assert all(secret not in path.read_text() for secret in
                   ("QUESTION_SECRET", "GOLD_SECRET", "CONTEXT_SECRET", "REFERENCE_SECRET", "HIDDEN_ARGUMENT"))


def test_preparation_does_not_require_qa_gold_or_context(panel):
    for source, path in panel[1].items():
        _arrow(path, [{key: row[key] for key in ("key", "question")} for row in panel[2][source]])
    assert _prepare(panel)["version"] == data.VERSION


def test_resume_is_byte_identical_and_does_not_rescan_or_compile(panel, monkeypatch):
    manifest = _prepare(panel)
    before = _tree(panel[0] / "outputs")
    monkeypatch.setattr(data, "_history", lambda *a: pytest.fail("resume rescanned history"))
    monkeypatch.setattr(mbpp, "inspect_compatibility", lambda *a: pytest.fail("resume recompiled catalog"))
    assert _prepare(panel) == manifest
    assert _tree(panel[0] / "outputs") == before


def test_reservations_exclude_all_prior_phases_even_unused_final(panel):
    first = _prepare(panel)
    second = _prepare(panel, name="second")
    for domain in data.DOMAINS:
        assert {row["id"] for row in _selected(first, domain)}.isdisjoint(
            row["id"] for row in _selected(second, domain))
    assert {row["cluster_id"] for row in _selected(first)}.isdisjoint(row["cluster_id"] for row in _selected(second))


def test_quarantine_nested_prompts_and_legacy_reservations_are_excluded(panel):
    repo, _, rows, coding = panel
    qa_row = rows["train"][0]
    coding_row = next(row for row in coding if row["task_id"] == 601)
    _write(repo / "outputs/old/quarantine.json", {"messages": [{"content": json.dumps({
        "question": qa_row["question"], "prompt": coding_row["prompt"]})}]})
    _write(repo / "data/searchqa_id_split/final.json", [{"key": rows["validation"][0]["key"]}])
    _write(repo / "outputs/old/unused.json", {"dataset": mbpp.DATASET, "splits": {"final": [{"task_id": 11}]}})
    manifest = _prepare(panel)
    inventory = data._read(repo / manifest["run_path"] / "exposure_inventory.json")
    assert question_fingerprint(qa_row["question"]) in inventory["excluded"]["searchqa"]["excluded_question_sha256"]
    assert question_fingerprint(coding_row["prompt"]) in inventory["excluded"]["coding"]["excluded_question_sha256"]
    assert rows["validation"][0]["key"] in inventory["excluded"]["searchqa"]["excluded_ids"]
    assert 11 in inventory["excluded"]["coding"]["excluded_ids"]


def test_host_only_legacy_eligibility_catalog_is_not_reservation(panel):
    repo = panel[0]
    catalog = mbpp.inspect_compatibility(repo)
    _write(repo / "outputs/coevolution_v11/old/eligibility_manifest.json", catalog)
    manifest = _prepare(panel)
    assert manifest["pool_counts"]["coding:train:eligible_unique"] == 120
    inventory = data._read(repo / manifest["run_path"] / "exposure_inventory.json")
    assert inventory["files"][0]["host_only_eligibility_catalog"] is True


def test_question_dedup_prioritizes_original_holdouts(panel):
    repo, caches, qa_rows, coding = panel
    qa_rows["train"][0]["question"] = qa_rows["validation"][0]["question"]
    _arrow(caches["train"], qa_rows["train"])
    next(row for row in coding if row["task_id"] == 601)["prompt"] = next(row for row in coding if row["task_id"] == 11)["prompt"]
    _snapshot(repo, coding)
    manifest = _prepare(panel)
    assert manifest["pool_counts"]["searchqa:train:duplicate_question"] == 1
    assert manifest["pool_counts"]["coding:train:duplicate_question"] == 1
    assert all(row["id"] != "601" for row in manifest["splits"]["coding"]["development"])


@pytest.mark.parametrize("domain", data.DOMAINS)
@pytest.mark.parametrize("phase", ("development", "confirmation"))
def test_materialized_true_phase_and_public_projection_excludes_gold(panel, domain, phase):
    manifest = _prepare(panel)
    rows = data.materialize_split(panel[0], manifest, domain, phase)
    assert len(rows) == COUNTS[phase]
    assert {row["phase"] for row in rows} == {phase}
    assert {row["split"] for row in rows} == {phase}
    for row in rows:
        if domain == "coding":
            assert row["id"] == str(row["task_id"])
            assert "REFERENCE_SECRET" in row["reference_code"]
        else:
            assert row["id"] == row["item"]["key"]
            assert "GOLD_SECRET" in row["item"]["answers"][0]
        public = json.dumps(data.public_task(row))
        assert all(secret not in public for secret in ("REFERENCE_SECRET", "GOLD_SECRET", "HIDDEN_ARGUMENT", "source_split"))


@pytest.mark.parametrize("domain", data.DOMAINS)
def test_final_requires_committed_candidate_freeze_before_payload_access(panel, monkeypatch, domain):
    manifest = _prepare(panel)
    monkeypatch.setattr(data, "_materialize_qa", lambda *a: pytest.fail("unauthorized QA payload"))
    monkeypatch.setattr(data, "_materialize_coding", lambda *a: pytest.fail("unauthorized MBPP payload"))
    with pytest.raises(ValueError, match="Final"):
        data.materialize_split(panel[0], manifest, domain, "final")


@pytest.mark.parametrize("domain", data.DOMAINS)
def test_final_materializes_after_matching_freeze(panel, domain):
    manifest = _prepare(panel)
    auth = _authorization(panel[0], manifest)
    assert len(data.materialize_split(panel[0], manifest, domain, "final", final_authorization=auth)) == COUNTS["final"]


@pytest.mark.parametrize("field,value", [("no_more_learning", False), ("policies_hash", "c" * 64),
                                          ("data_manifest_hash", "d" * 64), ("protocol_hash", "bad")])
def test_resealed_malformed_candidate_freezes_are_refused(panel, field, value):
    manifest = _prepare(panel)
    auth = _authorization(panel[0], manifest)
    auth[field] = value
    auth = _seal(auth)
    _write(panel[0] / manifest["run_path"] / "final_freeze.json", auth)
    with pytest.raises(ValueError, match="Final"):
        data.materialize_split(panel[0], manifest, "coding", "final", final_authorization=auth)


def test_uncommitted_freeze_is_refused(panel):
    manifest = _prepare(panel)
    auth = _authorization(panel[0], manifest)
    auth["histories"][0]["texts"]["parent"]["coding"] = "changed"
    auth["policies_hash"] = digest(auth["histories"])
    with pytest.raises(ValueError, match="committed"):
        data.materialize_split(panel[0], manifest, "coding", "final", final_authorization=_seal(auth))


def test_freeze_is_not_accepted_for_development(panel):
    manifest = _prepare(panel)
    with pytest.raises(ValueError, match="non-final"):
        data.materialize_split(panel[0], manifest, "coding", "development", final_authorization=_authorization(panel[0], manifest))


def test_historical_source_mutation_refuses_resume(panel):
    path = panel[0] / "outputs/old/log.json"
    _write(path, {"note": "old"})
    _prepare(panel)
    _write(path, {"note": "changed"})
    with pytest.raises(ValueError, match="Historical exposure input changed"):
        _prepare(panel)


@pytest.mark.parametrize("which", ("qa", "mbpp"))
def test_changed_source_refuses_materialization(panel, which):
    manifest = _prepare(panel)
    if which == "qa":
        path = panel[1]["train"]
        path.write_bytes(path.read_bytes() + b"changed")
        domain = "searchqa"
    else:
        path = panel[0] / mbpp.DIRECTORY / mbpp.FILENAMES["dataset"]
        path.write_text(path.read_text() + " ")
        domain = "coding"
    with pytest.raises(ValueError, match="changed"):
        data.materialize_split(panel[0], manifest, domain, "development")


@pytest.mark.parametrize("counts", [{"development": 0, "confirmation": 2, "final": 3},
                                   {"development": True, "confirmation": 2, "final": 3},
                                   {"confirmation": 2, "final": 3}])
def test_invalid_counts_are_rejected(panel, counts):
    with pytest.raises(ValueError, match="counts"):
        _prepare(panel, counts=counts)


@pytest.mark.parametrize("seed", [-1, True, 2**64])
def test_invalid_seed_is_rejected(panel, seed):
    with pytest.raises(ValueError, match="seed"):
        _prepare(panel, seed=seed)


def test_insufficient_pool_leaves_no_partial_manifest(panel):
    with pytest.raises(ValueError, match="Not enough"):
        _prepare(panel, counts={"development": 200, "confirmation": 2, "final": 3})
    assert not (panel[0] / "outputs/coevolution_v18/run/data_manifest.json").exists()


def test_resealed_payload_in_manifest_is_refused(panel):
    manifest = deepcopy(_prepare(panel))
    manifest["splits"]["coding"]["final"][0]["prompt"] = "PRIVATE"
    with pytest.raises(ValueError, match="identity/hash"):
        data.validate_manifest(_seal(manifest))


def test_outside_or_symlink_run_is_refused(panel, tmp_path):
    with pytest.raises(ValueError, match="separate run"):
        data.safe_root(panel[0], panel[0] / "outputs/coevolution_v11/run")
    target = panel[0] / "outputs/coevolution_v18"
    target.mkdir(parents=True)
    (target / "alias").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        data.safe_root(panel[0], target / "alias/run")
