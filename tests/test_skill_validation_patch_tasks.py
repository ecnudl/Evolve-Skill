"""Host-oracle/schema and nonexecuting receipt tests; no generated code exec."""
import ast
import hashlib
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import patch_tasks as tasks
from skillopt.skill_validation.models import ArtifactRecord, SourceFile
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_public_revision import FixtureExecutor


@pytest.fixture
def panel():
    return tasks.build_development_panel()


def artifact(row, *, availability="available"):
    return ArtifactRecord(row["task"].contract.content_hash, 0, "no_skill", "none", hashlib.sha256(b"").hexdigest(),
        (SourceFile("solution.py", "def solve(payload):\n    return None\n"),) if availability == "available" else (),
        availability, "fixture", True, False, "nonexecuting-fixture", digest("fixture"))


def test_exact_twelve_sources_twenty_four_contracts_not_twenty_four_families(panel):
    rows, manifest = panel["development"], panel["manifest"]
    assert len(rows) == manifest["task_count"] == 24
    assert len({r["family_id"] for r in rows}) == manifest["source_family_count"] == 12
    assert all({r["region"] for r in rows if r["family_id"] == family} == {"preserve", "replace"}
               for family in {r["family_id"] for r in rows})
    assert all(r["task"].contract.family_id == r["family_id"] and r["task"].contract.partition == "development" for r in rows)
    assert not manifest["official_benchmark"] and not manifest["natural_independent_projects"]
    assert manifest["prior_development_overlap"]["interval_policy"]
    assert len({r["host_only"]["starter"] for r in rows}) == 12
    assert tasks.build_development_panel() == panel
    reordered = tasks.build_development_panel(5)
    assert {r["task"].content_hash for r in reordered["development"]} == {r["task"].content_hash for r in rows}


@pytest.mark.parametrize("seed", [-1, True, "5", 2**64])
def test_invalid_seed_is_not_implicit_task_selection(seed):
    with pytest.raises(ValueError):
        tasks.build_development_panel(seed)


def test_starter_is_visible_but_reference_and_hidden_examples_are_not(panel):
    for row in panel["development"]:
        prompt = row["task"].contract.prompt
        host = row["host_only"]
        assert host["starter"] in prompt and row["task"].contract.public_files[0].content == host["starter"]
        assert host["reference"] not in prompt and "def _new(" not in host["starter"]
        assert len(host["starter"].splitlines()) <= 60
        assert len(row["task"].public_cases) == 4 and len(host["audit_cases"]) == 12
        assert not {digest(c["input"]) for c in host["public_cases"]} & {digest(c["input"]) for c in host["audit_cases"]}
        assert "legacy_expected" not in row["public_wrapper"]["content"]
        assert "batch-7" not in prompt and "batch-7" not in row["public_wrapper"]["content"]
        for code in (host["starter"], host["reference"], host["audit_runner"], row["public_wrapper"]["content"]):
            ast.parse(code)  # Parse only; strings are never executed on this host.


def test_frozen_rows_roundtrip_and_reject_changes(panel):
    for row in panel["development"]:
        raw = tasks.serialize_row(row)
        assert tasks.serialize_row(tasks.deserialize_row(raw)) == raw
        bad = deepcopy(raw)
        bad["host_only"]["audit_cases"][0]["expected"]["summary"]["tag"] = "wrong"
        with pytest.raises(ValueError, match="registration changed"):
            tasks.deserialize_row(bad)


# Each expectation is independently specified here, not read back from _cases.
EXPECTED_NEW = {
    "config_overlay": {"a": 1, "b": 2},
    "inventory_reservation": {"accepted": [2], "remaining": {"a": 0}},
    "stable_priority": ["b", "a", "c"],
    "path_normalization": "/a/c",
    "csv_serialization": '"a,b","x""y",plain',
    "topological_order": ["b", "a", "c"],
    "cache_eviction": {"reads": [1], "items": [["a", 1], ["c", 3]]},
    "log_redaction": [{"password": "[REDACTED]", "token": "[REDACTED]", "user": "u"}],
    "pagination_cursor": ["b"],
    "group_aggregation": [["a", 0], ["b", 2]],
    "interval_policy": [[0, 1]],
    "nested_record_update": {"a": {"x": 1}, "b": {"y": 2}},
}


@pytest.mark.parametrize("family", tuple(EXPECTED_NEW))
def test_hand_checked_new_policy_witness_and_host_oracle_does_not_mutate(family):
    data = deepcopy(tasks.DATA[family][1])
    saved = deepcopy(data)
    assert tasks._host_result(family, data, True) == EXPECTED_NEW[family]
    assert tasks._host_result(family, data, False) != EXPECTED_NEW[family]
    assert data == saved


def test_every_task_has_required_change_and_separate_retention_obligations(panel):
    for row in panel["development"]:
        cases = row["host_only"]["public_cases"] + row["host_only"]["audit_cases"]
        assert any(c["expected"] != c["legacy_expected"] for c in cases)
        assert all(c["expected"]["summary"] == c["legacy_expected"]["summary"] for c in cases)
        assert any("tag" not in c["input"] and c["input"]["data"] for c in row["host_only"]["audit_cases"])
        assert all(c["expected"]["summary"]["tag"] == c["input"].get("tag", "") for c in cases)
        if row["region"] == "preserve":
            assert {c["kind"] for c in cases} == {"target", "retained"}
            assert all(c["expected"] == c["legacy_expected"] for c in cases if c["kind"] == "retained")
        else:
            assert {c["kind"] for c in cases} == {"target", "replaced"}
            assert any(c["expected"] != c["legacy_expected"] for c in cases if c["kind"] == "replaced")
        assert "retained_behavior" in {o.id for o in row["task"].contract.obligations}


def test_nonexecuting_qualification_cannot_be_formal(panel, tmp_path):
    executor = FixtureExecutor()
    result = tasks.qualify_panel(panel, executor, tmp_path)
    assert result["status"] == "pending" and not result["formal_eligible"]
    assert result["families"] == 12 and result["tasks"] == 24
    assert len(executor.calls) == 24
    for call in executor.calls:
        source = call["files"]["qualify.py"] if isinstance(call, dict) else call[0]["qualify.py"]
        assert "policy_reversal_mutant_detected" in source and "exception_state_separated" in source
    assert all(r["receipt"]["engineering_fixture_only"] for r in result["results"])
    assert tasks.qualify_panel(panel, executor, tmp_path) == result
    assert len(executor.calls) == 24


def test_qualification_rejects_rebound_or_removed_row(panel, tmp_path):
    broken = {**panel, "development": panel["development"][:-1]}
    with pytest.raises(ValueError, match="manifest"):
        tasks.qualify_panel(broken, FixtureExecutor(), tmp_path)


def test_empty_or_trimmed_resealed_manifest_cannot_vacuously_qualify(panel, tmp_path):
    for rows in ([], panel["development"][:2]):
        manifest = seal({**{k: v for k, v in panel["manifest"].items() if k != "record_hash"},
                         "row_hashes": [digest(tasks.serialize_row(row)) for row in rows]})
        executor = FixtureExecutor()
        with pytest.raises(ValueError, match="entire canonical"):
            tasks.qualify_panel({"manifest": manifest, "development": rows}, executor, tmp_path)
        assert executor.calls == []


def _observations(row):
    return [{"id": c["id"], "target": True if c["kind"] == "target" else None,
             "retained": True, "replaced": True if c["kind"] == "replaced" else None,
             "state": True, "exception": None} for c in row["host_only"]["audit_cases"]]


@pytest.mark.parametrize("role", tasks.ROLES)
def test_obligations_have_separate_denominators_and_replacement_is_not_regression(role, tmp_path):
    row = tasks._row("config_overlay", role)
    observations = _observations(row)
    executor = FixtureExecutor({"actual": {"cases": observations}})
    report = tasks.audit_row(row, artifact(row), executor, tmp_path)
    assert report["status"] == "pass"
    assert report["coverage"]["target"]["applicable"] == 6
    assert report["coverage"]["retained"]["applicable"] == 12
    assert report["state_status"] == "pass"
    assert report["replaced_status"] == ("not_applicable" if role == "preserve" else "pass")
    assert report["coverage"]["replaced"]["applicable"] == (0 if role == "preserve" else 6)


@pytest.mark.parametrize("dimension", tasks.DIMENSIONS)
def test_each_obligation_failure_is_separately_reported(dimension, tmp_path):
    row = tasks._row("config_overlay", "replace")
    observations = _observations(row)
    next(r for r in observations if r[dimension] is not None)[dimension] = False
    report = tasks.audit_row(row, artifact(row), FixtureExecutor({"actual": {"cases": observations}}), tmp_path)
    assert report["status"] == "fail" and report[dimension + "_status"] == "fail"
    assert all(report[d + "_status"] == "pass" for d in tasks.DIMENSIONS if d != dimension)


@pytest.mark.parametrize("bad", [None, True, {"cases": []}, {"cases": [{"id": "invented"}]}])
def test_incomplete_or_malformed_execution_is_unknown_not_semantic_failure(bad, tmp_path):
    row = tasks._row("config_overlay", "preserve")
    report = tasks.audit_row(row, artifact(row), FixtureExecutor({"actual": bad}), tmp_path)
    assert report["status"] == report["target_status"] == report["retained_status"] == report["state_status"] == "unknown"
    assert report["replaced_status"] == "not_applicable"


@pytest.mark.parametrize("error", ["MemoryError", "TimeoutError"])
def test_resource_limited_execution_remains_unknown(error, tmp_path):
    row = tasks._row("config_overlay", "replace")
    report = tasks.audit_row(row, artifact(row), FixtureExecutor({"actual": None, "exception": error}), tmp_path)
    assert report["status"] == "unknown"


def test_unavailable_artifact_does_not_execute_and_has_explicit_unknown(tmp_path):
    row, executor = tasks._row("cache_eviction", "preserve"), FixtureExecutor()
    report = tasks.audit_row(row, artifact(row, availability="api_failure"), executor, tmp_path)
    assert report["status"] == "unknown" and report["receipt"] is None
    assert executor.calls == []


def test_artifact_for_another_contract_cannot_be_audited(tmp_path):
    row = tasks._row("cache_eviction", "preserve")
    foreign = artifact(tasks._row("cache_eviction", "replace"))
    with pytest.raises(ValueError, match="another task"):
        tasks.audit_row(row, foreign, FixtureExecutor(), tmp_path)


def test_executor_without_isolation_or_fixture_identity_is_rejected(panel, tmp_path):
    class Unsafe:
        identity = {"kind": "host-exec"}
        def run(self, *args):
            raise AssertionError("Must never execute")
    with pytest.raises(ValueError, match="isolated"):
        tasks.qualify_panel(panel, Unsafe(), tmp_path)


def test_observer_only_measures_state_after_exception_not_assumes_mutation():
    source = tasks._row("config_overlay", "preserve")["host_only"]["audit_runner"]
    assert "state=equal(payload,case['input'])" in source
    assert "result,retained,state=False,False,False" not in source
    ast.parse(source)
