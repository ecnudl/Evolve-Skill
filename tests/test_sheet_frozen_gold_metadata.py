"""Saved-cache qualification controls; not dynamic engine equivalence tests."""
import hashlib

from openpyxl.worksheet.formula import ArrayFormula

from skillopt.continual_eval import sheet_frozen_gold as gold
from tests.test_continual_eval_sheet_frozen_gold import Fake, fixture, manifest


def dynamic(path, cache=("n", "2")):
    fixture(path, {"B1": ArrayFormula(ref="B1", text="=1+1")}, {"B1": cache})
    gold._fixture_xldapr(path)
    return path


def test_metadata_snapshot_is_readonly_and_does_not_authorize_reference_execution(tmp_path):
    h = dynamic(tmp_path / "h.xlsx")
    original = h.read_bytes()
    frozen = manifest(h)
    assert frozen["status"] == "available"
    assert frozen["metadata_snapshot"]["saved_target_cache_only"]
    assert not frozen["metadata_snapshot"]["dynamic_semantics_executed"]
    assert not frozen["cache_freshness_established"] and not frozen["reference_recalculated"]
    p = fixture(tmp_path / "p.xlsx")
    engine = Fake()
    assert gold.evaluate(p, h, "S!B1", engine, frozen)["status"] == "pass"
    assert engine.calls == [p] and h.read_bytes() == original
    assert frozen["reference_sha256"] == hashlib.sha256(original).hexdigest()


def test_bad_candidate_does_not_become_correct_when_metadata_h_is_qualified(tmp_path):
    h = dynamic(tmp_path / "h.xlsx")
    p = fixture(tmp_path / "p.xlsx", {"B1": 3})
    engine = Fake()
    assert gold.evaluate(p, h, "S!B1", engine, manifest(h))["status"] == "fail"
    assert engine.calls == [p]


def test_metadata_known_dispute_still_stops_before_candidate_engine(tmp_path):
    h = dynamic(tmp_path / "h.xlsx")
    p = fixture(tmp_path / "p.xlsx")
    engine = Fake()
    result = gold.evaluate(p, h, "S!B1", engine, manifest(h, dispute=True))
    assert result["reason"] == "known_reference_dispute" and not engine.calls


def test_v3_preserves_fourteen_old_expected_outcomes_and_adds_four_controls(tmp_path):
    old = {"numeric_correct": "pass", "numeric_wrong": "fail", "stale_correct_cache": "fail",
        "empty_string": "pass", "missing_formula_cache": "unknown", "missing_array_follower": "unknown",
        "array_zero_false": "pass", "reference_unsupported_but_cached": "pass",
        "known_reference_dispute": "unknown", "reference_error_literal": "pass", "true_date": "pass",
        "candidate_unsupported": "unknown", "missing_target_sheet": "unknown",
        "candidate_boolean_literal_limit": "unknown"}
    assert all(gold.SCORE_EXPECTED[name] == expected for name, expected in old.items())
    added = set(gold.SCORE_EXPECTED) - set(old)
    assert added == {"metadata_single_cached", "metadata_missing_cache", "metadata_multicell", "metadata_unknown_type"}
    engine = Fake()
    first = gold.qualify(tmp_path / "fixtures", engine)
    controls = {c["name"]: c for c in first["controls"]}
    assert len(controls) == 18 and all(controls[name]["qualified"] for name in added)
    assert all(path.name.endswith("-candidate.xlsx") for path in engine.calls)
    # Fake never recalculates: the stale candidate must still prevent acceptance.
    assert first["status"] == "rejected" and not controls["stale_correct_cache"]["qualified"]
    assert gold.qualify(tmp_path / "fixtures", Fake()) == first
