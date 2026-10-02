"""Host-H isolation and cache completeness; fixtures, not method-effect data."""
import base64
import hashlib
from pathlib import Path

import pytest
from openpyxl.worksheet.formula import ArrayFormula

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import sheet_frozen_gold as gold

PROVENANCE = {"source_protocol_hash": "a" * 64, "task_id": "fixture", "evidence_kind": "engineering_fixture"}


def fixture(path, cells=None, caches=None):
    gold._fixture_book(path, cells or {"B1": 2}, caches)
    return path


def manifest(path, target="S!B1", **kwargs):
    return gold.freeze_reference(path, gold.recalc.sha(path), target, provenance=PROVENANCE, **kwargs)


class Fake:
    identity = {"version": "fixture_only"}

    def __init__(self, output=None, status="available", cleanup=True):
        self.output, self.status, self.cleanup, self.calls = output, status, cleanup, []

    def run(self, path):
        self.calls.append(Path(path))
        raw = Path(self.output or path).read_bytes()
        return seal({"identity": self.identity, "input_sha256": gold.recalc.sha(path),
                     "status": self.status, "reason": "authored_fixture", "cleanup_confirmed": self.cleanup,
                     "output_base64": base64.b64encode(raw).decode(), "output_sha256": hashlib.sha256(raw).hexdigest()})


@pytest.mark.parametrize("value", [2, 0, False, "text", "#N/A"])
def test_literal_cache_and_no_reference_execution(tmp_path, value):
    h = fixture(tmp_path / "gold.xlsx", {"B1": value})
    p = fixture(tmp_path / "pred.xlsx", {"B1": value})
    engine = Fake()
    frozen = manifest(h)
    result = gold.evaluate(p, h, "S!B1", engine, frozen)
    assert result["status"] == "pass" and engine.calls == [p]
    assert frozen["cache_freshness_established"] is False
    assert "target_values" not in frozen and result["reference_executed"] is False


def test_plain_blank_is_not_missing_formula(tmp_path):
    h = fixture(tmp_path / "h.xlsx", {"A1": 1})
    assert manifest(h)["status"] == "available"
    assert manifest(h)["cache_counts"] == {"ordinary_blank": 1}


@pytest.mark.parametrize("cache,expected", [(None, "unknown"), (("n", ""), "unknown"),
                                           (("str", ""), "available"), (("n", "0"), "available")])
def test_explicit_empty_string_differs_from_missing_or_empty_numeric(tmp_path, cache, expected):
    h = fixture(tmp_path / "h.xlsx", {"B1": '=IF(TRUE(),"",2)'}, {"B1": cache} if cache else None)
    assert manifest(h)["status"] == expected


@pytest.mark.parametrize("follower,expected", [(None, "unknown"), (("n", ""), "unknown"),
                                              (("b", "0"), "available"), (("n", "0"), "available"),
                                              (("str", ""), "available")])
def test_array_follower_must_have_real_result(tmp_path, follower, expected):
    caches = {"B1": ("n", "0")}
    if follower:
        caches["B2"] = follower
    h = fixture(tmp_path / "h.xlsx", {"B1": ArrayFormula(ref="B1:B2", text="=ROW(A1:A2)-1"),
                                     "B2": 0 if follower else None}, caches)
    assert manifest(h, "S!B1:B2")["status"] == expected


def test_missing_gold_cache_beats_other_mismatch_and_does_not_execute(tmp_path):
    h = fixture(tmp_path / "h.xlsx", {"B1": "=1+1", "B2": 999})
    p = fixture(tmp_path / "p.xlsx", {"B1": 2, "B2": 0})
    engine = Fake()
    result = gold.evaluate(p, h, "S!B1:B2", engine, manifest(h, "S!B1:B2"))
    assert result["status"] == "unknown" and not engine.calls


def test_stale_candidate_correct_cache_does_not_decide_score(tmp_path):
    h = fixture(tmp_path / "h.xlsx")
    p = fixture(tmp_path / "p.xlsx", {"A1": 3, "B1": "=A1+1"}, {"B1": ("n", "2")})
    fresh = fixture(tmp_path / "fresh.xlsx", {"A1": 3, "B1": "=A1+1"}, {"B1": ("n", "4")})
    assert gold.evaluate(p, h, "S!B1", Fake(fresh), manifest(h))["status"] == "fail"


def test_unsupported_reference_formula_is_not_sent_to_engine(tmp_path):
    h = fixture(tmp_path / "h.xlsx", {"A1": 2, "B1": "=_xlfn.UNIQUE(A1)"}, {"B1": ("n", "2")})
    p = fixture(tmp_path / "p.xlsx")
    engine = Fake()
    assert gold.evaluate(p, h, "S!B1", engine, manifest(h))["status"] == "pass"
    assert engine.calls == [p]


def test_known_dispute_stays_unknown(tmp_path):
    h = fixture(tmp_path / "h.xlsx")
    engine = Fake()
    result = gold.evaluate(h, h, "S!B1", engine, manifest(h, dispute=True))
    assert result["reason"] == "known_reference_dispute" and not engine.calls


@pytest.mark.parametrize("damage", ["seal", "bytes", "target"])
def test_reference_binding_is_mandatory(tmp_path, damage):
    h = fixture(tmp_path / "h.xlsx")
    frozen = manifest(h)
    if damage == "seal":
        frozen["status"] = "fake"
    elif damage == "bytes":
        fixture(h, {"B1": 99})
    with pytest.raises(ValueError):
        gold.evaluate(h, h, "S!B2" if damage == "target" else "S!B1", Fake(), frozen)


@pytest.mark.parametrize("damage", ["identity", "input_sha256", "output_sha256", "seal"])
def test_candidate_receipt_binding_is_mandatory(tmp_path, damage):
    h = fixture(tmp_path / "h.xlsx")
    engine = Fake()
    original = engine.run

    def damaged(path):
        receipt = original(path)
        receipt.pop("record_hash")
        receipt[damage] = "damaged"
        result = seal(receipt)
        if damage == "seal":
            result["reason"] = "changed"
        return result

    engine.run = damaged
    with pytest.raises(ValueError):
        gold.evaluate(h, h, "S!B1", engine, manifest(h))


@pytest.mark.parametrize("kwargs,reason", [({"cleanup": False}, "candidate_cleanup_unconfirmed"),
                                         ({"status": "unknown"}, "prediction:authored_fixture")])
def test_execution_unknown_never_passes(tmp_path, kwargs, reason):
    h = fixture(tmp_path / "h.xlsx")
    result = gold.evaluate(h, h, "S!B1", Fake(**kwargs), manifest(h))
    assert result["status"] == "unknown" and result["reason"] == reason


def test_candidate_formula_change_still_rejected(tmp_path):
    h = fixture(tmp_path / "h.xlsx")
    p = fixture(tmp_path / "p.xlsx", {"B1": "=1+1"})
    result = gold.evaluate(p, h, "S!B1", Fake(h), manifest(h))
    assert result["status"] == "unknown" and "formula" in result["reason"]


@pytest.mark.parametrize("target", ["Missing!B1", "S!B2:B1", "", "S!XFE1"])
def test_invalid_target_stays_unknown(tmp_path, target):
    h = fixture(tmp_path / "h.xlsx")
    assert manifest(h, target)["status"] == "unknown"


def test_engineering_score_qualification_has_fixed_expected_roster(tmp_path):
    # Fake does not recalculate -> stale control MUST reject; this cannot
    # manufacture a successful real-environment qualification from fixtures.
    result = gold.qualify(tmp_path / "fixtures", Fake())
    assert result["status"] == "rejected"
    assert {c["name"] for c in result["controls"]} == gold.SCORE_CONTROLS
    stale = next(c for c in result["controls"] if c["name"] == "stale_correct_cache")
    assert stale["expected"] == "fail" and not stale["qualified"]
