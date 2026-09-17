"""Offline attribution checks; no live requests or actual holdout artifacts."""

from __future__ import annotations

import copy
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.scope_evolution_v2 import source_attribution as attribution
from skillopt.scope_evolution_v2 import source_data

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def historical_full():
    # This exact historical Skill is permitted; no benchmark payload is read.
    return (REPO / "outputs/repro_searchqa/full_gpt55_seed42/best_skill.md").read_text(encoding="utf-8")


def test_lesions_are_exact_deletions_and_preserve_other_bytes(historical_full):
    full = historical_full
    lesions = attribution.section_lesions(full)
    evidence_start = full.index(attribution.EVIDENCE_HEADER)
    evidence_end = full.index("## Jeopardy-Style Wordplay")
    answer_start = full.index(attribution.ANSWER_HEADER)
    slow_start = full.index(attribution.SLOW_START)
    slow_end = full.index(attribution.SLOW_END) + len(attribution.SLOW_END)
    assert set(lesions) == set(attribution.LESIONS)
    assert lesions[attribution.LESIONS[0]] == full[:evidence_start] + full[evidence_end:]
    assert lesions[attribution.LESIONS[1]] == full[:answer_start] + full[evidence_start:slow_start] + full[slow_end:]
    assert attribution.EVIDENCE_HEADER in lesions[attribution.LESIONS[1]]
    assert attribution.ANSWER_HEADER in lesions[attribution.LESIONS[0]]
    for text in lesions.values():
        assert "## Final Answer Formatting" in text
        assert "## Jeopardy-Style Wordplay" in text
        assert len(text) < len(full)


def test_changed_historical_skill_is_rejected(historical_full):
    with pytest.raises(ValueError, match="historical SHA256"):
        attribution.section_lesions(historical_full + "\n")


def test_duplicate_header_rejected_even_if_hash_check_is_mocked(historical_full, monkeypatch):
    altered = historical_full + "\n" + attribution.EVIDENCE_HEADER + "\n"
    monkeypatch.setattr(attribution, "BEST_SHA256", hashlib.sha256(altered.encode()).hexdigest())
    with pytest.raises(ValueError, match="unique historical headings"):
        attribution.section_lesions(altered)
    with pytest.raises(ValueError, match="exactly one"):
        attribution._section_span(altered, attribution.EVIDENCE_HEADER)


def test_overlapping_or_invalid_deletions_rejected():
    with pytest.raises(ValueError, match="Overlapping"):
        attribution._remove_spans("abcdef", [(0, 3), (2, 4)])
    with pytest.raises(ValueError, match="Invalid deletion"):
        attribution._remove_spans("abcdef", [(-1, 2)])


def _outcomes():
    scores = {"base": [0, 1, 1], "full": [1, 1, 0],
              attribution.LESIONS[0]: [0, 1, 1], attribution.LESIONS[1]: [1, 0, None]}
    return {arm: [{"id": f"synthetic-{index}", "arm": arm, "skill_sha256": f"fixed-hash-{arm}",
                   "agent_ok": value is not None, "hard": value, "em": value, "f1": value}
                  for index, value in enumerate(values)] for arm, values in scores.items()}


def test_summary_common_four_arm_denominator_and_no_hash_relabeling():
    outcomes = _outcomes()
    original = copy.deepcopy(outcomes)
    summary = attribution.summarize(outcomes, bootstrap_n=20)
    assert outcomes == original
    assert summary["reference_aliases_are_summary_only"] is True
    assert summary["common_ids"] == ["synthetic-0", "synthetic-1"]
    assert summary["excluded_ids_missing_any_arm"] == ["synthetic-2"]
    assert all(row["n_common_success"] == 2 for row in summary["arms"].values())
    assert summary["arms"]["base"]["em"] == .5
    assert summary["arms"]["full"]["em"] == 1
    assert summary["vs_base"]["full"]["delta"]["em"] == .5
    assert summary["vs_full"][attribution.LESIONS[0]]["delta"]["em"] == -.5
    assert summary["vs_full"][attribution.LESIONS[1]]["paired"]["losses"] == 1


def test_summary_no_common_api_success_is_undefined():
    outcomes = _outcomes()
    for row in outcomes[attribution.LESIONS[0]]:
        row.update(agent_ok=False, hard=None, em=None, f1=None)
    summary = attribution.summarize(outcomes, bootstrap_n=10)
    assert summary["common_ids"] == []
    assert all(value["em"] is None for value in summary["arms"].values())
    assert summary["vs_full"][attribution.LESIONS[0]]["paired_bootstrap95"]["em"] == [None, None]


def test_summary_requires_all_fixed_arms():
    outcomes = _outcomes()
    outcomes.pop(attribution.LESIONS[1])
    with pytest.raises(ValueError, match="Exactly Base/full"):
        attribution.summarize(outcomes, bootstrap_n=10)


class SequenceAPI:
    def __init__(self, results):
        self.results = iter(results)
        self.n = 0

    def call(self, *args, **kwargs):
        self.n += 1
        value = next(self.results)
        if isinstance(value, BaseException):
            raise value
        return {"ok": value}


def test_guard_first_failure_stops_without_another_request():
    api = SequenceAPI([False, True])
    guarded = attribution._GuardedAPI(api)
    with pytest.raises(RuntimeError, match="fail-fast"):
        guarded.call()
    with pytest.raises(RuntimeError, match="batch stopped"):
        guarded.call()
    assert api.n == 1


def test_guard_three_consecutive_failures_and_success_reset():
    api = SequenceAPI([True, False, False, True, False, False, False, True])
    guarded = attribution._GuardedAPI(api)
    for expected in [True, False, False, True, False, False]:
        assert guarded.call()["ok"] is expected
    with pytest.raises(RuntimeError, match="fail-fast"):
        guarded.call()
    with pytest.raises(RuntimeError, match="batch stopped"):
        guarded.call()
    assert api.n == 7


def test_guard_underlying_exception_stops_later_requests():
    api = SequenceAPI([RuntimeError("synthetic failure"), True])
    guarded = attribution._GuardedAPI(api)
    with pytest.raises(RuntimeError, match="synthetic failure"):
        guarded.call()
    with pytest.raises(RuntimeError, match="batch stopped"):
        guarded.call()
    assert api.n == 1


def test_guard_first_health_barrier_blocks_other_calls():
    entered, release = threading.Event(), threading.Event()
    calls = []

    def call(index):
        calls.append(index)
        if index == 0:
            entered.set()
            assert release.wait(timeout=1)
        return {"ok": True}

    guarded = attribution._GuardedAPI(SimpleNamespace(call=call))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(guarded.call, 0)
        assert entered.wait(timeout=1)
        second = pool.submit(guarded.call, 1)
        assert calls == [0]
        release.set()
        assert first.result(timeout=1)["ok"]
        assert second.result(timeout=1)["ok"]
    assert calls == [0, 1]


@pytest.mark.parametrize("relative,origin", [("datasets/holdout.json", "source"),
                                               ("routes/holdout.json", "routing")])
def test_late_prepare_rejects_before_source_contract_or_payload_read(tmp_path, monkeypatch, relative, origin):
    source, routing, root = (tmp_path / name for name in ("source", "routing", "attribution"))
    marker = {"source": source, "routing": routing}[origin] / relative
    marker.parent.mkdir(parents=True)
    marker.write_text("synthetic marker; must not parse", encoding="utf-8")
    monkeypatch.setattr(attribution, "_deps", lambda repo: (source_data, None))

    def no_source_read(*args):
        raise AssertionError("Late preparation must stop before reading source contract")

    monkeypatch.setattr(attribution, "_source_contract", no_source_read)
    with pytest.raises(ValueError, match="holdout has opened"):
        attribution.prepare(tmp_path, root, source, routing)
    assert not root.exists()


@pytest.mark.parametrize("mode,api", [("real_target_api", object()), ("injected_test_double", None)])
def test_execution_mode_mismatch_stops_before_dependencies(tmp_path, monkeypatch, mode, api):
    def no_dependencies(repo):
        raise AssertionError("No credentials, model, or source reads expected")

    monkeypatch.setattr(attribution, "_deps", no_dependencies)
    with pytest.raises(ValueError, match="Test-double mode"):
        attribution.run_phase(tmp_path, tmp_path / "e", tmp_path / "c", tmp_path / "d", "test",
                              execution_mode=mode, api=api)


def test_source_contract_rejects_mock_evidence_for_real_execution(tmp_path, monkeypatch):
    manifest = {"splits": {"holdout": [{"id": "synthetic-id", "question_sha256": "synthetic-fingerprint"}]}}
    code = {"synthetic.py": "fixed-hash"}
    protocol = {"manifest_hash": source_data.digest(manifest), "code_hashes": code, "arms": {}}
    frozen = {"manifest_hash": source_data.digest(manifest), "protocol_hash": source_data.digest(protocol),
              "code_hashes": code, "arms": {}, "execution_mode": "injected_test_double"}
    lookup = {"source_manifest.json": manifest, "source_protocol.json": protocol, "frozen_source_protocol.json": frozen}
    data = SimpleNamespace(read_json=lambda path: lookup[path.name], digest=source_data.digest)
    monkeypatch.setattr(attribution, "_deps", lambda repo: (data, SimpleNamespace(_code_hashes=lambda: code)))
    with pytest.raises(ValueError, match="execution mode changed"):
        attribution._source_contract(tmp_path, tmp_path / "c", "real_target_api")


def test_borrowed_source_no_calls_guard_and_no_calibration_phase(tmp_path):
    with pytest.raises(ValueError, match="may not regenerate"):
        attribution._NoCalls().call()
    with pytest.raises(ValueError, match="no calibration phase"):
        attribution.run_phase(tmp_path, tmp_path / "e", tmp_path / "c", tmp_path / "d", "calibration")
