"""Offline tests: frozen source IDs, withheld payloads, exact prompts and scoring."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from skillopt.envs.searchqa.rollout import _build_system, _build_user
from skillopt.scope_evolution_v2 import source_data, source_retention
from skillopt.scope_evolution_v2.source_data import (
    MANIFEST_TYPE,
    materialize_source_split,
    prepare_source_manifest,
    question_fingerprint,
    read_json,
    write_immutable_json,
)

REPO = Path(__file__).resolve().parents[1]
FAKE_FULL_SKILL = """# Offline source-retention test skill

Concise clue-answering rules
Use the requested answer form.

## Extractive / Trivia Evidence Selection
Resolve the requested relation using the supplied evidence.
Keep every explicitly requested name component.

## Jeopardy-Style Wordplay
Use wordplay only when the question requests it.
"""


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def source_fixture(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    # The historical full skill lives in ignored outputs and is not available
    # in clean checkouts. Exercise its exact-section/hash contract with a fixed
    # self-contained stand-in, without weakening the production hash check.
    full = repo / "outputs/repro_searchqa/full_gpt55_seed42/best_skill.md"
    full.parent.mkdir(parents=True)
    full.write_text(FAKE_FULL_SKILL, encoding="utf-8")
    monkeypatch.setattr(source_retention, "BEST_SHA256", hashlib.sha256(FAKE_FULL_SKILL.encode()).hexdigest())
    relative = "skillopt/envs/searchqa/skills/initial.md"
    initial = repo / relative
    initial.parent.mkdir(parents=True)
    initial.write_bytes((REPO / relative).read_bytes())
    records = [{"key": f"key-{i:02d}", "question": f"QUESTION_SECRET_{i:02d}",
                "context": f"Visible source context {i} " + "[DOC] readable passage " * 10,
                "answers": [f"GOLD_SECRET_{i:02d}"]} for i in range(20)]
    records[0]["question"] = "Already viewed"
    records[1]["question"] = "  ALREADY   viewed "
    records[3]["question"] = records[2]["question"]
    arrow = tmp_path / "source-validation.arrow"
    table = pa.Table.from_pylist(records)
    with pa.OSFile(str(arrow), "wb") as stream, ipc.new_stream(stream, table.schema) as writer:
        writer.write_table(table)
    log = repo / "outputs/repro_searchqa/old/results.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps({"id": "key-00", "question": "Already viewed"}) + "\n", encoding="utf-8")
    # The sampler must never inspect ongoing synthetic v1 test artifacts.
    unrelated = repo / "outputs/cross_domain/ongoing/rollouts/test_r0_base.json"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("not valid JSON; do not read", encoding="utf-8")
    return repo, arrow, records


class MockAPI:
    def __init__(self, records, failures=()):
        self.answers = {row["key"]: row["answers"][0] for row in records}
        self.calls = []
        self.failures = set(failures)

    def call(self, system, user, *, key, arm, split):
        assert "GOLD_SECRET" not in system + user
        self.calls.append({"key": key, "arm": arm, "split": split, "system": system, "user": user})
        ok = (key, arm) not in self.failures
        answer = "not the answer" if arm == "base" else self.answers[key]
        return {"ok": ok, "response": f"<answer>{answer}</answer>" if ok else "",
                "request_hash": f"mock-{split}-{arm}-{key}", "usage": {"total_tokens": 10},
                **({} if ok else {"error": "Mock HTTP 429"})}


def _run(fixture, root, phase, api=None, **kwargs):
    repo, arrow, _ = fixture
    return source_retention.run_phase(repo, root, phase, calibration_n=2, holdout_n=4,
                                     cache_path=arrow, workers=1, api=api, **kwargs)


def test_sampling_excludes_history_questions_and_prior_manifest_reservations(source_fixture):
    repo, arrow, _ = source_fixture
    previous = repo / "outputs/scope_evolution_v2/previous/source_manifest.json"
    _json(previous, {"manifest_type": MANIFEST_TYPE, "splits": {
        "calibration": [{"id": "key-04", "question_sha256": question_fingerprint("QUESTION_SECRET_04")}],
        "holdout": [{"id": "key-05", "question_sha256": question_fingerprint("QUESTION_SECRET_05")}],
    }})
    root = repo / "outputs/scope_evolution_v2/new"
    manifest = prepare_source_manifest(repo, root, calibration_n=2, holdout_n=4, cache_path=arrow)
    chosen = [item for split in manifest["splits"].values() for item in split]
    assert len({row["id"] for row in chosen}) == 6
    assert len({row["question_sha256"] for row in chosen}) == 6
    assert not {row["id"] for row in chosen} & {"key-00", "key-01", "key-03", "key-04", "key-05"}
    assert manifest["pool_counts"] == {"source_rows": 20, "excluded_by_id": 3, "excluded_by_question": 1,
                                       "duplicate_pool_questions": 1, "eligible_unique_questions": 15}
    assert len(manifest["exposure"]["previous_source_manifests"]) == 1
    assert prepare_source_manifest(repo, root, calibration_n=2, holdout_n=4, cache_path=arrow) == manifest


def test_prepare_never_materializes_holdout_and_emits_only_counts_hashes(source_fixture, monkeypatch):
    repo, _, records = source_fixture
    root = repo / "outputs/scope_evolution_v2/prepare"
    actual = source_retention.materialize_source_split
    opened = []

    def guarded(manifest, split):
        opened.append(split)
        assert split == "calibration"
        return actual(manifest, split)

    monkeypatch.setattr(source_retention, "materialize_source_split", guarded)
    api = MockAPI(records)
    result = _run(source_fixture, root, "prepare", api)
    assert opened == ["calibration"]
    assert api.calls == []
    assert not (root / "datasets/holdout.json").exists()
    assert result["arms"] == ["base", "full", "extractive"]
    assert result["planned_calls"] == 18
    manifest_text = (root / "source_manifest.json").read_text()
    assert "QUESTION_SECRET" not in manifest_text
    assert "GOLD_SECRET" not in manifest_text
    assert "QUESTION_SECRET" not in json.dumps(result)
    calibration = read_json(root / "datasets/calibration.json")
    holdout_ids = {row["id"] for row in read_json(root / "source_manifest.json")["splits"]["holdout"]}
    assert not {row["id"] for row in calibration} & holdout_ids


def test_holdout_requires_completed_calibration_before_payload_access(source_fixture):
    repo, _, records = source_fixture
    root = repo / "outputs/scope_evolution_v2/no_pilot"
    api = MockAPI(records)
    with pytest.raises(ValueError, match="Complete calibration"):
        _run(source_fixture, root, "test", api)
    assert not api.calls
    assert not (root / "datasets/holdout.json").exists()


def test_mock_pilot_test_uses_fixed_arms_original_prompts_and_separate_ids(source_fixture):
    repo, _, records = source_fixture
    root = repo / "outputs/scope_evolution_v2/complete"
    api = MockAPI(records)
    pilot = _run(source_fixture, root, "pilot", api)
    assert len(api.calls) == 6
    assert not (root / "datasets/holdout.json").exists()
    assert (root / "frozen_source_protocol.json").exists()
    assert pilot["arms"]["base"]["em"] == 0
    assert pilot["arms"]["full"]["em"] == 1
    calibration = {row["id"]: row for row in read_json(root / "datasets/calibration.json")}
    for call in api.calls:
        task = calibration[call["key"]]
        skill = (root / "skills" / f"{call['arm']}.md").read_text()
        assert call["system"] == _build_system(skill)
        assert call["user"] == _build_user(task["question"], task["context"])
    full = (root / "skills/full.md").read_text()
    extractive = (root / "skills/extractive.md").read_text()
    assert extractive in full
    assert "Concise clue-answering rules" not in extractive
    assert "SLOW_UPDATE_START" not in extractive
    test = _run(source_fixture, root, "test", api)
    assert len(api.calls) == 18
    assert test["split"] == "holdout"
    assert set(test["common_ids"]).isdisjoint(pilot["common_ids"])
    assert test["vs_base"]["full"]["paired"]["wins"] == 4
    assert test["vs_base"]["extractive"]["paired"]["wins"] == 4
    assert (root / "holdout_report.md").exists()
    # Repeat phase is a cache replay, not another target generation.
    assert _run(source_fixture, root, "test", api) == test
    assert len(api.calls) == 18


def test_api_failure_uses_same_successful_denominator_for_every_arm(source_fixture):
    repo, _, records = source_fixture
    root = repo / "outputs/scope_evolution_v2/failure"
    _run(source_fixture, root, "prepare")
    identifier = read_json(root / "source_manifest.json")["splits"]["calibration"][0]["id"]
    api = MockAPI(records, failures={(identifier, "extractive")})
    summary = _run(source_fixture, root, "pilot", api)
    assert summary["arms"]["extractive"]["n_api_error"] == 1
    assert summary["arms"]["full"]["n_api_error"] == 0
    assert all(value["n_common_success"] == 1 for value in summary["arms"].values())
    assert summary["excluded_ids_missing_any_arm"] == [identifier]
    rows = [json.loads(line) for line in (root / "searchqa_rollouts/calibration/extractive/results.jsonl").read_text().splitlines()]
    failed = next(row for row in rows if not row["agent_ok"])
    assert failed["hard"] is None and failed["f1"] is None


def test_snapshot_and_protocol_changes_block_holdout(source_fixture):
    repo, _, records = source_fixture
    root = repo / "outputs/scope_evolution_v2/tamper"
    api = MockAPI(records)
    _run(source_fixture, root, "pilot", api)
    path = root / "skills/full.md"
    path.write_text(path.read_text() + "changed", encoding="utf-8")
    with pytest.raises(ValueError, match="Skill snapshot changed"):
        _run(source_fixture, root, "test", api)
    assert not (root / "datasets/holdout.json").exists()


def test_code_change_or_arm_change_blocks_resume(source_fixture, monkeypatch):
    repo, _, records = source_fixture
    root = repo / "outputs/scope_evolution_v2/config_tamper"
    _run(source_fixture, root, "prepare")
    with pytest.raises(ValueError, match="protocol/code changed"):
        _run(source_fixture, root, "pilot", MockAPI(records), arms=("base", "full"))
    monkeypatch.setattr(source_retention, "_code_hashes", lambda: {"changed": "hash"})
    with pytest.raises(ValueError, match="protocol/code changed"):
        _run(source_fixture, root, "pilot", MockAPI(records))


def test_mock_calibration_cannot_be_mistaken_for_real_api_evidence(source_fixture):
    repo, _, records = source_fixture
    root = repo / "outputs/scope_evolution_v2/mock_contract"
    summary = _run(source_fixture, root, "pilot", MockAPI(records))
    assert summary["execution_mode"] == "injected_test_double"
    with pytest.raises(ValueError, match="mix mock and real"):
        _run(source_fixture, root, "test")
    assert not (root / "datasets/holdout.json").exists()


def test_cached_rollout_arm_and_score_provenance_are_checked(source_fixture):
    repo, _, records = source_fixture
    root = repo / "outputs/scope_evolution_v2/row_tamper"
    api = MockAPI(records)
    _run(source_fixture, root, "pilot", api)
    path = root / "searchqa_rollouts/calibration/full/results.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["arm"] = "base"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    with pytest.raises(ValueError, match="provenance"):
        _run(source_fixture, root, "pilot", api)


def test_changed_arrow_is_rejected_before_materialization(source_fixture):
    repo, arrow, _ = source_fixture
    root = repo / "outputs/scope_evolution_v2/cache_tamper"
    manifest = prepare_source_manifest(repo, root, calibration_n=2, holdout_n=4, cache_path=arrow)
    with arrow.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="Arrow changed"):
        materialize_source_split(manifest, "holdout")


def test_prior_new_source_log_is_excluded_by_searchqa_rollout_path(source_fixture):
    repo, arrow, records = source_fixture
    prior = repo / "outputs/scope_evolution_v2/prior/searchqa_rollouts/calibration/full/results.jsonl"
    prior.parent.mkdir(parents=True)
    prior.write_text(json.dumps({"id": records[7]["key"], "question": records[7]["question"]}) + "\n")
    manifest = prepare_source_manifest(repo, repo / "outputs/scope_evolution_v2/later", calibration_n=2, holdout_n=4, cache_path=arrow)
    assert records[7]["key"] in manifest["exposure"]["excluded_ids"]
    assert len(manifest["exposure"]["logs"]) == 2


def test_all_api_failures_are_not_reported_as_zero_accuracy():
    row = {"id": "one", "agent_ok": False, "hard": None, "em": None, "f1": None}
    summary = source_retention.summarize({"base": [row], "full": [row], "extractive": [row]}, bootstrap_n=10)
    assert summary["arms"]["base"]["em"] is None
    assert summary["vs_base"]["full"]["paired_bootstrap95"]["em"] == [None, None]


def test_immutable_artifact_writer_does_not_overwrite_existing_content(tmp_path):
    path = tmp_path / "artifact.json"
    write_immutable_json(path, {"value": 1})
    write_immutable_json(path, {"value": 1})
    with pytest.raises(ValueError, match="overwrite"):
        write_immutable_json(path, {"value": 2})
    assert read_json(path) == {"value": 1}


def test_sampler_determinism_and_no_gold_access(source_fixture, monkeypatch):
    repo, arrow, _ = source_fixture
    # Separate directories outside outputs do not count as prior reservations.
    first = prepare_source_manifest(repo, repo / "test_a", calibration_n=2, holdout_n=4, cache_path=arrow)
    second = prepare_source_manifest(repo, repo / "test_b", calibration_n=2, holdout_n=4, cache_path=arrow)
    assert first["splits"] == second["splits"]
    assert all(set(row) == {"id", "question_sha256"} for split in first["splits"].values() for row in split)
    assert not (repo / "test_a/datasets").exists()
    assert source_data.DEFAULT_CACHE.name == "searchqa-validation.arrow"


@pytest.mark.parametrize("success", [True, False])
def test_real_cache_class_records_actual_call_and_reuses_terminal_outcome(tmp_path, monkeypatch, success):
    # Skip __init__ entirely: this verifies the real cache boundary without
    # reading credentials, configuring a provider, or accessing the network.
    import skillopt.model

    api = object.__new__(source_retention.SourceCachedAPI)
    api.root = tmp_path
    api.protocol = {"protocol_version": "test-protocol", "model": "gpt-5.5",
                    "requested_max_completion_tokens": 16384}
    api.service = {"host": "free-router.opendatalab.com", "path": "/v1", "cap": 8000, "temperature": None}
    calls = []

    def target(**kwargs):
        calls.append(kwargs)
        if not success:
            raise RuntimeError("Mock HTTP 429")
        return "<answer>visible prediction</answer>", {"total_tokens": 12}

    monkeypatch.setattr(skillopt.model, "chat_target", target)
    first = api.call("frozen system", "visible question and context", key="id-1", arm="full", split="calibration")
    repeated = api.call("frozen system", "visible question and context", key="id-1", arm="full", split="calibration")
    assert first == repeated
    assert first["ok"] is success
    assert calls == [{"system": "frozen system", "user": "visible question and context",
                      "max_completion_tokens": 16384, "retries": 3, "timeout": 90,
                      "stage": "source_retention_calibration"}]
    assert first["request_hash"] == source_data.digest(first["request"])
    assert len(list((tmp_path / "calls").glob("*.json"))) == 1
