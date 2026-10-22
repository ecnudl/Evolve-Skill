"""Registrar addendum 2026-10-23 05:3x: the owner's smoke waiver (``smoke.waiver``, ``protocol.SMOKE_WAIVER``,
``protocol.WAIVABLE_SMOKE_ROWS``), the test-read estimate of a waived smoke (``chain.read_estimate_record``, which
records the waiver) and ``run_execskill.py smoke-waiver``. Zero calls; every smoke root and waiver file here is a
throwaway engineering fixture under ``tmp_path`` (the real waiver file is the owner's alone)."""
from __future__ import annotations

import hashlib
import json

import pytest

from scripts import run_execskill as cli
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import chain, protocol, smoke

PER_CELL = {b: {"card": float(protocol.CELL_ANCHORS[b][1]), "procedure": 1.6 * protocol.CELL_ANCHORS[b][1],
                "procedure_assumed": True} for b in protocol.BENCHES}
S2_ROWS = ("faults", "format", "hooks", "ledger", "leftovers", "native_lock", "receipts")
NOTE = "owner: proceed despite the S2 format row (fixture)"


def _smoke(root, *, s2=("format",), stages=("S2", "SE6"), se6=True, also=()):
    """A smoke root as ``smoke.summary`` leaves it: S2 recorded with the rows ``s2`` failing, S-E6 passed or failed
    with the per-cell tokens when it is a stage, and each (stage, passed, rows) of ``also`` -> (spec, result); the
    result is sealed once every listed stage is recorded."""
    spec = protocol.record("smoke-spec", "smoke", {"root": str(root), "stages": list(stages)})
    write_json(root / smoke.SPEC, spec)
    smoke.record(spec, "S2", {"passed": not s2, "rows": {row: row not in s2 for row in S2_ROWS}})
    for stage, passed, rows in also:
        smoke.record(spec, stage, {"passed": passed, "rows": rows})
    if "SE6" in stages:
        smoke.record(spec, "SE6", {"passed": se6, "rows": {"ratio": se6}, "per_cell": PER_CELL, "ratio": 1.0})
    return spec, smoke.summary(spec)


def _waive(root, result, drop=(), **changes):
    """The owner's waiver file (a fixture here) naming ``result``, with ``changes`` and without the ``drop`` keys."""
    value = {"decision": "waive", "smoke_result": result[protocol.RECORD_HASH], "rows": ["S2.format"], "note": NOTE,
             **changes}
    path = root / protocol.SMOKE_WAIVER
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({key: v for key, v in value.items() if key not in drop}), encoding="utf-8")
    return path


def _refused(root, result, match):
    """``smoke.waiver``, the test-read estimate and ``smoke-waiver`` (the last two on a sealed result) refuse it."""
    with pytest.raises(ValueError, match=match):
        smoke.waiver(root, result)
    if (root / smoke.RESULT).exists():
        with pytest.raises(ValueError, match=match):
            chain.read_estimate_record(root)
        with pytest.raises(ValueError, match=match):
            cli.main(["smoke-waiver", "--spec", str(root / smoke.SPEC)])


def test_without_a_waiver_a_failed_smoke_gives_no_estimate(tmp_path, capsys):
    """As before the addendum: no waiver file, no estimate of a failed smoke; ``smoke-waiver`` says absent and writes
    nothing."""
    root = tmp_path / "smoke"
    _, result = _smoke(root)
    assert result["passed"] is False and result["rows"]["S2"]["format"] == "fail"
    assert smoke.waiver(root, result) is None
    with pytest.raises(ValueError, match="passed smoke"):
        chain.read_estimate_record(root)
    assert cli.main(["smoke-waiver", "--spec", str(root / smoke.SPEC)]) == 0
    assert json.loads(capsys.readouterr().out) == {"waiver": "absent"}
    assert not (root / protocol.SMOKE_WAIVER).exists()


def test_a_valid_waiver_admits_the_estimate_and_is_recorded_in_it(tmp_path, capsys):
    """A failed S2 format row under the owner's valid waiver: the estimate is made and records the waiver's sha256 and
    rows; ``smoke-waiver`` prints them; the file is only read. A passed smoke's estimate records no waiver."""
    root = tmp_path / "smoke"
    _, result = _smoke(root)
    path = _waive(root, result)
    before = path.read_bytes()
    want = {"sha256": hashlib.sha256(before).hexdigest(), "rows": ["S2.format"]}
    assert smoke.waiver(root, result) == want
    found = chain.read_estimate_record(root)
    assert found["waiver"] == want and found["smoke"]["result"] == result[protocol.RECORD_HASH]
    assert cli.main(["smoke-waiver", "--spec", str(root / smoke.SPEC)]) == 0
    assert json.loads(capsys.readouterr().out) == {"waiver": "valid", **want}
    out = tmp_path / "ops" / "test-read-estimate.json"
    assert cli.main(["test-read-estimate", "--smoke", str(root), "--out", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["waiver"] == want
    assert protocol.verified(read_json(out), "test-read-estimate")["waiver"] == want
    assert path.read_bytes() == before
    passed = tmp_path / "passed"
    assert _smoke(passed, s2=())[1]["passed"] is True
    assert chain.read_estimate_record(passed)["waiver"] is None


def test_the_waiver_must_name_this_smoke_result(tmp_path):
    root = tmp_path / "smoke"
    _, result = _smoke(root)
    _waive(root, result, smoke_result="0" * 64)
    _refused(root, result, "names another smoke-result")


def test_the_waived_rows_are_exactly_the_failing_rows(tmp_path):
    """A failing row left out, a row that did not fail, or an extra row is refused."""
    two = tmp_path / "two"  # S2.format and S2.receipts failed: waiving S2.format alone leaves a failing row out
    _, result = _smoke(two, s2=("format", "receipts"))
    _waive(two, result)
    _refused(two, result, "exactly the failing rows")
    unfailed = tmp_path / "unfailed"  # S2 passed and S3 failed without a failing row: S2.format did not fail
    _, result = _smoke(unfailed, s2=(), stages=("S2", "S3", "SE6"), also=[("S3", False, {"engineer": True})])
    _waive(unfailed, result)
    _refused(unfailed, result, "exactly the failing rows")
    extra = tmp_path / "extra"  # an extra row beside the failing S2.format
    _, result = _smoke(extra)
    _waive(extra, result, rows=["S2.format", "S2.receipts"])
    _refused(extra, result, "Only S2.format may be waived")


def test_only_the_allowlisted_rows_may_be_waived(tmp_path):
    """S3's generator_research row is not waivable, even as the only failing row that the waiver names exactly."""
    root = tmp_path / "smoke"
    _, result = _smoke(root, s2=(), stages=("S2", "S3", "SE6"),
                       also=[("S3", False, {"engineer": True, "generator_research": False})])
    assert result["passed"] is False
    _waive(root, result, rows=["S3.generator_research"])
    _refused(root, result, "Only S2.format may be waived")


def test_a_waived_smoke_needs_its_se6_required_and_passed(tmp_path):
    failed = tmp_path / "se6-failed"
    _, result = _smoke(failed, se6=False)
    _waive(failed, result)
    _refused(failed, result, "S-E6 is required and passed")
    unlisted = tmp_path / "se6-not-required"
    _, result = _smoke(unlisted, stages=("S2",))
    _waive(unlisted, result)
    _refused(unlisted, result, "S-E6 is required and passed")


@pytest.mark.parametrize("change, match", [
    ({"drop": ("note",)}, "exactly decision, smoke_result, rows and note"),
    ({"by": "owner"}, "exactly decision, smoke_result, rows and note"),
    ({"decision": "proceed"}, "decides"),
    ({"note": "  "}, "decides"),
    ({"rows": []}, "sorted, unique, non-empty"),
    ({"rows": ["S2.format", "S2.format"]}, "sorted, unique, non-empty"),
    ({"rows": ["S2.format", "S2.faults"]}, "sorted, unique, non-empty"),
    ({"rows": ["format"]}, "sorted, unique, non-empty"),
    ({"rows": [1]}, "sorted, unique, non-empty"),
    ({"rows": "S2.format"}, "sorted, unique, non-empty"),
])
def test_the_waiver_holds_exactly_its_four_keys_and_their_forms(tmp_path, change, match):
    root = tmp_path / "smoke"
    _, result = _smoke(root)
    _waive(root, result, **change)
    _refused(root, result, match)


def test_a_waiver_with_a_repeated_key_is_refused(tmp_path):
    root = tmp_path / "smoke"
    _, result = _smoke(root)
    path = _waive(root, result)
    path.write_text(path.read_text(encoding="utf-8")[:-1] + ', "rows": ["S2.format"]}', encoding="utf-8")
    _refused(root, result, "repeats a key")


def test_a_waiver_beside_a_passed_smoke_is_refused(tmp_path):
    root = tmp_path / "smoke"
    _, result = _smoke(root, s2=())
    assert result["passed"] is True
    _waive(root, result)
    _refused(root, result, "A passed smoke needs no waiver")


def test_a_waiver_refuses_a_missing_stage_and_a_failing_stage_without_a_failing_row(tmp_path):
    """A required stage not yet recorded (a result reported, not sealed), or a failing stage none of whose rows
    failed, is refused: the waiver covers failing rows only."""
    running = tmp_path / "running"
    _, result = _smoke(running, stages=("S2", "S3", "SE6"))
    assert result["stages"]["S3"] == "missing" and not (running / smoke.RESULT).exists()
    _waive(running, result)
    _refused(running, result, "no missing stage")
    rowless = tmp_path / "rowless"
    _, result = _smoke(rowless, stages=("S2", "S3", "SE6"), also=[("S3", False, {"engineer": True})])
    _waive(rowless, result)
    _refused(rowless, result, "fails on a waived row")


def test_smoke_waiver_reads_only_a_sealed_result_and_writes_nothing(tmp_path):
    root = tmp_path / "smoke"
    _smoke(root, stages=("S2", "S3", "SE6"))  # S3 not recorded: nothing is sealed
    with pytest.raises(ValueError, match="no sealed smoke-result"):
        cli.main(["smoke-waiver", "--spec", str(root / smoke.SPEC)])
    assert sorted(path.name for path in root.iterdir()) == ["smoke.json", "stages"]
