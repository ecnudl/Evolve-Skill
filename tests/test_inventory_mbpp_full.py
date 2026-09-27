"""Synthetic source records exercise static inventory only, never execution."""
import json
from pathlib import Path

import pytest

from scripts import inventory_mbpp_full as m
from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import write_immutable_json


def row(identifier=200, text="Compute the unique fixture increment.", **kwargs):
    return {"task_id": identifier, "text": text, "code": "def increment(x):\n    return x + 1\n",
            "test_list": ["assert increment(1) == 2"], "test_setup_code": "", "challenge_test_list": [], **kwargs}


def encoded(rows):
    return ("\n".join(json.dumps(r) for r in rows) + "\n").encode()


def test_output_metadata_omits_prompts_code_assertions_and_values():
    records = m.parse_full(encoded([row(text="PRIVATE_PROMPT_SENTINEL")]))
    result = m.inventory(records, [])
    assert verify(result) == result
    text = json.dumps(result)
    for secret in ("PRIVATE_PROMPT_SENTINEL", "def increment", "assert increment", "return x + 1"):
        assert secret not in text
    assert result["counts"]["candidate_tasks"] == 1
    assert result["source_provenance"] == "fixture_or_unverified_input"
    assert result["formal_partition_created"] is False
    assert result["model_calls"] == result["execution_calls"] == 0
    assert result["records"][0]["source_line"] == 1


def test_entire_sanitized_pool_excluded_even_if_not_in_history():
    raw = [row(200, "Unique red fixture"), row(300, "An unrelated violet counting operation")]
    result = m.inventory(m.parse_full(encoded(raw)), [{"task_id": 200, "prompt": "Unique red fixture"}])
    assert result["counts"]["sanitized_ids_excluded"] == 1
    assert result["records"][0]["reasons"] == ["sanitized_pool_excluded"]
    assert result["records"][1]["eligible_candidate"]


def test_transitive_lexical_closure_includes_sanitized_rephrasing():
    raw = [row(100, "a" * 100), row(200, "x" * 100), row(300, "a" * 90 + "b" * 10),
           row(400, "a" * 80 + "b" * 20)]
    sanitized = [{"task_id": 200, "prompt": "a" * 100}]
    families = m.lexical_families(raw, sanitized)
    assert len(set(families.values())) == 1
    result = m.inventory(m.parse_full(encoded(raw)), sanitized)
    assert result["counts"]["candidate_tasks"] == 0
    assert result["reason_counts_nonexclusive"]["lexical_family_exposure_closure"] == 3


@pytest.mark.parametrize("setup", ["import math", "from math import sqrt", "x = 1", "__import__('os').system('false')"])
def test_executable_setup_explicitly_excluded_not_dropped_or_executed(setup):
    assert m.compatibility(row(test_setup_code=setup)) == {"eligible": False, "reason": "unsupported_nonempty_setup"}
    assert m.compatibility(row(test_setup_code="# harmless comment\n"))["eligible"]


def test_all_challenge_tests_compiled_and_unsupported_assertion_excludes_whole_task():
    assert m.compatibility(row(challenge_test_list=["assert increment(3) == 4"]))["eligible"]
    result = m.compatibility(row(challenge_test_list=["assert all(increment(x) for x in [1, 2])"]))
    assert not result["eligible"] and result["reason"] == "unsupported_native_assertions"


def test_readiness_function_prompt_and_explicit_history_exclusions():
    raw = [row(5, "prompt problem"), row(800, "known warmup problem"), row(700, "new recorded history"),
           row(710, "rotation function", code="def left_rotate(x):\n    return x\n", test_list=["assert left_rotate(1) == 1"])]
    result = m.inventory(m.parse_full(encoded(raw)), [], history_ids={700})
    reasons = {r["task_id"]: r["reasons"] for r in result["records"]}
    assert "official_prompt_few_shot" in reasons[5]
    assert "known_readiness_exposure" in reasons[800]
    assert "historical_inventory_exposure" in reasons[700]
    assert "known_readiness_function_exposure" in reasons[710]


@pytest.mark.parametrize("body", [b"", b"{}\n", b"\n", b'{"task_id":200,"task_id":201}\n', b"{\"x\":NaN}\n"])
def test_malformed_sources_rejected(body):
    with pytest.raises(ValueError): m.parse_full(body)


def test_duplicates_cardinality_and_byte_bound():
    with pytest.raises(ValueError, match="Duplicate"):
        m.parse_full(encoded([row(), row()]))
    with pytest.raises(ValueError, match="cardinality"):
        m.parse_full(encoded([row()]), expected_count=974)
    with pytest.raises(ValueError, match="Bounded"):
        m.parse_full(b"x" * (m.MAX_BYTES + 1))


def test_history_reuses_only_explicit_verified_mbpp_inventories(tmp_path):
    path = tmp_path / "outputs/prior/exposure_inventory.json"
    write_immutable_json(path, seal({"dataset": m.legacy.DATASET, "version": "v11-mbpp-sanitized-data-v1-exposure",
                                    "excluded_ids": [200, 300], "excluded_question_sha256": [], "files": []}))
    ids, sources = m.historical_inventories(tmp_path)
    assert ids == {200, 300} and len(sources) == 1
    assert sources[0]["excluded_ids"] == 2
    path.write_text(path.read_text().replace('"task"', '"changed"').replace("300", "301"))
    with pytest.raises(ValueError): m.historical_inventories(tmp_path)


def test_history_has_independent_cap_without_relaxing_source_limit(tmp_path, monkeypatch):
    assert m.MAX_BYTES == 16 * 1024 * 1024
    assert m.MAX_HISTORY_BYTES == 64 * 1024 * 1024
    path = tmp_path / "outputs/prior/exposure_inventory.json"
    write_immutable_json(path, seal({"dataset": m.legacy.DATASET, "version": "v11-mbpp-sanitized-data-v1-exposure",
                                    "excluded_ids": [200], "excluded_question_sha256": [], "files": [],
                                    "fixture_padding": "x" * 200}))
    monkeypatch.setattr(m, "MAX_BYTES", 64)
    assert path.stat().st_size > m.MAX_BYTES
    assert m.historical_inventories(tmp_path)[0] == {200}
    with pytest.raises(ValueError, match="Bounded"):
        m.parse_full(encoded([row()]))
    monkeypatch.setattr(m, "MAX_HISTORY_BYTES", 64)
    with pytest.raises(ValueError, match="historical"):
        m.historical_inventories(tmp_path)


def fake_sanitized(monkeypatch):
    source = seal({"files": {"dataset_card": {"url": "fixture-license"}, "upstream_readme": {"url": "fixture-readme"}}})
    monkeypatch.setattr(m.legacy, "load_snapshot", lambda repo: source)
    monkeypatch.setattr(m.legacy, "download_snapshot", lambda repo: source)
    monkeypatch.setattr(m.legacy, "_source_rows", lambda repo, receipt: [{"task_id": i, "prompt": "fixture"} for i in range(1, 428)])


def test_download_requires_opt_in_is_immutable_and_cached_is_offline(tmp_path, monkeypatch):
    fake_sanitized(monkeypatch)
    calls = []
    body = encoded([row(i) for i in range(1, 975)])
    def fetch(url):
        calls.append(url)
        return body
    with pytest.raises(ValueError, match="download"):
        m.snapshot(tmp_path, fetch=fetch)
    assert not calls
    receipt, rows, sanitized = m.snapshot(tmp_path, download=True, fetch=fetch)
    assert len(rows) == 974 and len(sanitized) == 427 and calls == [m.URL]
    assert receipt["license_source"]["url"] == "fixture-license"
    assert m.snapshot(tmp_path, fetch=lambda _: pytest.fail("Unexpected fetch"))[0] == receipt
    target = tmp_path / m.DIRECTORY / "mbpp.jsonl"
    target.write_bytes(body + b"\n")
    with pytest.raises(ValueError, match="bytes changed"):
        m.snapshot(tmp_path)


def test_download_url_allowlist_and_path_guards(tmp_path):
    with pytest.raises(ValueError, match="pinned"):
        m._fetch("https://example.com/untrusted.jsonl")
    with pytest.raises(ValueError, match="Unsafe"):
        m._safe(tmp_path / ".." / "escape")
    with pytest.raises(ValueError, match="dedicated"):
        m.run(tmp_path, output=tmp_path / "outputs/skill_validation")
