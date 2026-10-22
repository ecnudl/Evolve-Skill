"""T-QUAL-1..2 (implementation plan §8.1; registration §1 owner #7, Codex F15; ticket A11-1): the copied qualification
closure stamps this protocol's version while scoring through the frozen helpers, and v3 records enter only through
``IMPORTABLE`` with their original hashes. Ticket C7b1-3 (registrar addendum 2026-10-22): ``engine_runtime`` replaces
only the three qualification fields of v3's SpreadsheetBench runtime and revalidates it, ``revalidate`` wraps the
frozen offline check, ``same_engine_sources`` compares two engine identities by their sources relative to each
snapshot root. Offline: the frozen scorer is replaced by a scripted one; every workbook and engine qualification is a
synthetic file; no model call, no container."""
from __future__ import annotations

import base64
import hashlib
import json
from contextlib import nullcontext
from pathlib import Path

import pytest

from skillopt.coevo5.cells import Pause
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends, sheet_numeric_adapter
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import qualify
from skillopt.execskill.protocol import IMPORTABLE, kind, verified
from skillopt.validator_pilot.api import digest

EVIDENCE = "engineering_fixture"
RUNTIME = {"spreadsheet_scorer": "qualified_lo_recalc_v7_v1", "recalculation": {"image": "sha256:" + "f" * 64}}
V3 = "fivebench-coevolution-v3-sheet-qualification"


class Native:
    def __init__(self):
        self.holds = 0

    def hold(self):
        self.holds += 1
        return nullcontext()


def tasks(root, n):
    out = []
    for k in range(n):
        path = Path(root) / ("reference-%d.xlsx" % k)
        path.write_bytes(b"synthetic workbook %d" % k)
        out.append({"task_id": "sb-fixture-%d" % k, "public": {"instruction": "Fill B1.", "input_files": []},
                    "private": {"test_files": [str(path)], "answer_position": "B1"}})
    return out


def scorer(failing, calls):
    """The frozen scorer's shape: pass, unless the item is in ``failing`` (a reference recalculation failure)."""
    def score(benchmark, public, private, prediction, *, runtime=None):
        calls.append((benchmark, prediction["output"]["cases"][0]["output_base64"], runtime["_score_context"]))
        bad = any(Path(p).name in failing for p in private["test_files"])
        case = {"status": "fail" if bad else "pass",
                "reason": "reference:recalculation_failed" if bad else "cell_values_match"}
        return {"status": case["status"], "reason": case["reason"], "cleanup_confirmed": True,
                "metrics": {"cases": [case]}}
    return score


def test_qual1_the_copied_closure_stamps_this_protocol_and_scores_through_the_frozen_helpers(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(backends, "score", scorer({"reference-1.xlsx"}, calls))
    items = tasks(tmp_path, 3)
    native = Native()
    found = qualify.qualify(items, tmp_path / "q1", RUNTIME, side="train", native=native, workers=2,
                            evidence=EVIDENCE)
    # the record: this protocol's stamp (never v3), the frozen fields read by generators.sheet (ticket A11-1)
    assert found["version"] == kind("sheet-qualification") == "fivebench-execskill-v1-sheet-qualification"
    assert verified(found, "sheet-qualification") == found and found["evidence"] == EVIDENCE
    assert found["qualified"] == ["sb-fixture-0", "sb-fixture-2"] and found["scorings_per_item"] == 2
    assert found["excluded"] == {"sb-fixture-1": "reference_recalculation_failed"} and found["model_calls"] == 0
    assert found["task_hashes"] == {t["task_id"]: digest(t) for t in items}
    # the frozen reference prediction was scored twice per item, each in its own scoring directory, under the slot
    assert len(calls) == 6 == native.holds
    assert {c[1] for c in calls} == {base64.b64encode(Path(t["private"]["test_files"][0]).read_bytes()).decode()
                                    for t in items}
    assert len({c[2]["artifact_dir"] for c in calls}) == 6
    # every file written is this protocol's record (T-ID-2): no v3 stamp anywhere
    written = sorted((tmp_path / "q1").rglob("*.json"))
    assert len(written) == 7
    for path in written:
        text = path.read_text(encoding="utf-8")
        assert "fivebench-coevolution-v3" not in text
        assert json.loads(text)["version"].startswith("fivebench-execskill-v1-")
    assert qualify.load(tmp_path / "q1" / "qualification.json") == found
    assert qualify.summary(found) == {"side": "train", "items": 3, "qualified": 2,
                                      "excluded": {"reference_recalculation_failed": 1}}
    # a qualification runs in a new directory (frozen rule)
    with pytest.raises(ValueError, match="new directory"):
        qualify.qualify(items, tmp_path / "q1", RUNTIME, side="train", native=native, workers=1, evidence=EVIDENCE)


def test_qual1_a_configuration_reason_pauses_the_qualification_through_the_frozen_check(tmp_path, monkeypatch):
    def broken(benchmark, public, private, prediction, *, runtime=None):
        return {"status": "fail", "reason": "missing_public_workbook", "metrics": {"cases": []}}

    monkeypatch.setattr(backends, "score", broken)
    with pytest.raises(Pause) as stop:
        qualify.qualify(tasks(tmp_path, 1), tmp_path / "q", RUNTIME, side="test", native=Native(), workers=1,
                        evidence=EVIDENCE)
    assert stop.value.kind == "configuration"


def v3_record(items):
    return seal({"version": V3, "side": "train", "tasks": len(items), "qualified": [items[0]["task_id"]],
                 "excluded": {t["task_id"]: "other" for t in items[1:]},
                 "counts": {name: 0 for name in qualify.CATEGORIES}, "scorings_per_item": 2, "model_calls": 0,
                 "scorer": RUNTIME["spreadsheet_scorer"], "recalculation": RUNTIME["recalculation"],
                 "task_hashes": {t["task_id"]: digest(t) for t in items}})


def test_qual2_v3_records_enter_only_through_importable_with_their_original_hashes(tmp_path):
    items = tasks(tmp_path, 2)
    original = v3_record(items)
    write_json(tmp_path / "v3.json", original)
    assert IMPORTABLE == (V3,)
    loaded = qualify.load(tmp_path / "v3.json")
    assert loaded == original and qualify.record_digest(loaded) == original["record_hash"]
    qualify.reverify(loaded, pinned=original["record_hash"], tasks=items)  # zero calls, pinned hash
    with pytest.raises(ValueError, match="pinned"):
        qualify.reverify(loaded, pinned="0" * 64)
    with pytest.raises(ValueError, match="other items"):
        qualify.reverify(loaded, pinned=original["record_hash"], tasks=items[:1])
    # outside the explicit table: refused, whatever its hash
    with pytest.raises(ValueError, match="importable"):
        qualify.load(tmp_path / "v3.json", importable=())
    other = seal({**{k: v for k, v in original.items() if k != "record_hash"},
                  "version": "fivebench-coevolution-v2-sheet-qualification"})
    write_json(tmp_path / "v2.json", other)
    with pytest.raises(ValueError, match="importable"):
        qualify.load(tmp_path / "v2.json")
    # a changed v3 record keeps no valid hash
    tampered = dict(original, qualified=[t["task_id"] for t in items], excluded={})
    write_json(tmp_path / "tampered.json", tampered)
    with pytest.raises(ValueError):
        qualify.load(tmp_path / "tampered.json")
    with pytest.raises(ValueError, match="content"):
        qualify.reverify(tampered, pinned=original["record_hash"])
    assert read_json(tmp_path / "v3.json") == original  # the import never rewrites the v3 record


# ------------------------------------------------------------------------- C7b1-3: the recalculation engine
IMAGE = "sha256:f7f6f598c4f0b16ea514614c22325e8b3a2d5d0317f423757dcdfa1bb2c4d790"
SOURCES = ("skillopt/continual_eval/sheet_recalc.py", "skillopt/continual_eval/sheet_recalc_worker.py",
           "skillopt/continual_eval/spreadsheet_compat.py", "skillopt/envs/spreadsheetbench/evaluator.py",
           "skillopt/skill_validation/sandbox.py", "skillopt/continual_eval/sheet_recalc_v6.py",
           "skillopt/continual_eval/sheet_recalc_v7.py")  # the seven sources of v3's q23-f identity


def identity(root, **changes):
    """An engine identity of the frozen v7 shape (sheet_recalc.py:404-408 + v6/v7), its sources under ``root``."""
    value = {"version": "spreadsheet-independent-lo-recalculation-v7", "image_id": IMAGE, "timeout_seconds": 120,
             "memory_mb": 1024, "cpus": 1, "pids_limit": 128, "network": "none", "root_read_only": True,
             "source_read_only": True, "user": "65534:65534", "macros": "never_execute", "links": "no_update",
             "comparison_view": "original-general-formula-numeric-read-view-v1",
             "sources": {"%s/%s" % (root, name): "%064x" % n for n, name in enumerate(SOURCES)}}
    value.update(changes)
    return value


def engine_record(path, engine, **changes):
    """A sealed engine qualification in the shape ``scripts/replay_sheet_v6.py qualify`` writes."""
    value = seal({"version": "spreadsheet-v6-independent-replay-v1", "status": "qualified", "protocol_hash": "p" * 64,
                  "engine": engine, "engine_profile": "v7", "controls": [], "execution": {},
                  "evidence_kind": "engineering_fixture", "model_api_calls": 0, "excel_equivalence_proven": False,
                  **changes})
    write_json(path, value)
    return value


def v3_sheet_runtime():
    """v3's ``runtime.spreadsheetbench`` shape (/data/coevo5-20261019-v3-run-manifest.json)."""
    return {"prompt_layout": "contract-first-v2", "image": "sha256:" + "0a" * 32, "timeout_seconds": 300,
            "memory_mb": 4096, "cpus": 1, "code_extraction_version": "explicit-python-fences-v1",
            "spreadsheet_preview_version": "public-formula-preview-v1", "_stop_on_cleanup_failure": True,
            "spreadsheet_scorer": "qualified_lo_recalc_v7_v1",
            "recalculation": {"image": IMAGE, "timeout_seconds": 120,
                              "qualification_path": "/data/coevo5-20261019-v3-sheet-q23-f/qualification.json",
                              "qualification_sha256": "7" * 64, "qualification_hash": "4" * 64}}


def test_c7b1_3_engine_runtime_replaces_only_the_three_qualification_fields_and_revalidates(tmp_path, monkeypatch):
    path = tmp_path / "q23" / "qualification.json"
    record = engine_record(path, identity("/data/execskill-20261021-source"))
    base, seen = v3_sheet_runtime(), []
    found = qualify.engine_runtime(base, path, check=seen.append)
    assert seen == [found] and base == v3_sheet_runtime()  # checked once; the v3 block itself is not changed
    expected = v3_sheet_runtime()
    expected["recalculation"].update(qualification_path=str(path), qualification_hash=record["record_hash"],
                                     qualification_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    assert found == expected  # image, timeout and every other field kept
    # a relative path is pinned absolute; the default check is ``revalidate`` (the frozen offline qualified_engine)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(qualify, "revalidate", lambda runtime: seen.append(("default", runtime)))
    found = qualify.engine_runtime(base, "q23/qualification.json")
    assert found["recalculation"]["qualification_path"] == str(path) and seen[-1] == ("default", found)
    # a failing check fails the runtime: nothing is returned
    def stale(runtime):
        raise ValueError("Engine/source/image changed")

    with pytest.raises(ValueError, match="Engine/source/image changed"):
        qualify.engine_runtime(base, path, check=stale)
    # refusals before any check: another image or timeout, an unqualified or tampered record, another scorer
    engine_record(tmp_path / "other" / "qualification.json", identity("/x", image_id="sha256:" + "1" * 64))
    with pytest.raises(ValueError, match="image and timeout"):
        qualify.engine_runtime(base, tmp_path / "other" / "qualification.json", check=stale)
    engine_record(tmp_path / "pending" / "qualification.json", identity("/x"), status="pending")
    with pytest.raises(ValueError, match="Not a qualified"):
        qualify.engine_runtime(base, tmp_path / "pending" / "qualification.json", check=stale)
    write_json(tmp_path / "tampered" / "qualification.json", {**record, "engine_profile": "v8"})
    with pytest.raises(ValueError):
        qualify.engine_runtime(base, tmp_path / "tampered" / "qualification.json", check=stale)
    with pytest.raises(ValueError, match="v7 scorer"):
        qualify.engine_runtime({**base, "spreadsheet_scorer": "native"}, path, check=stale)
    with pytest.raises(ValueError, match="No engine qualification"):
        qualify.engine_runtime(base, tmp_path / "missing.json", check=stale)


def test_c7b1_3_revalidate_names_the_frozen_refusal_and_returns_the_qualified_hash(monkeypatch):
    runtime = v3_sheet_runtime()
    runtime["recalculation"]["qualification_path"] = "/nonexistent-i1/qualification.json"
    with pytest.raises(ValueError, match="C7b1-3.*(FileNotFoundError|OSError)"):  # the real frozen check, offline
        qualify.revalidate(runtime)
    for error in (ValueError("Engine/source/image changed"), KeyError("engine"), TypeError("x")):
        def refused(value, error=error):
            raise error

        monkeypatch.setattr(sheet_numeric_adapter, "qualified_engine", refused)
        with pytest.raises(ValueError, match="does not revalidate from this checkout") as found:
            qualify.revalidate(runtime)
        assert type(error).__name__ in str(found.value)
    monkeypatch.setattr(sheet_numeric_adapter, "qualified_engine", lambda value: (object(), {"record_hash": "h" * 64}))
    assert qualify.revalidate(runtime) == "h" * 64


def test_c7b1_3_same_engine_sources_compares_sources_relative_to_each_snapshot_root(tmp_path):
    old = tmp_path / "v3" / "qualification.json"
    engine_record(old, identity("/data/coevo5-20261019-v3-source-f"))
    new = tmp_path / "new" / "qualification.json"
    engine_record(new, identity("/data/execskill-20261021-source"))
    found = qualify.same_engine_sources(new, old)
    assert found == {"same": True, "fields": {"compared": 13, "differing": []},
                     "sources": {"new": 7, "old": 7, "equal": 7, "differing": []},
                     "roots": {"new": "/data/execskill-20261021-source", "old": "/data/coevo5-20261019-v3-source-f"}}
    # a snapshot root whose own name holds "skillopt" (the last package component is the root's child)
    engine_record(tmp_path / "nested" / "qualification.json", identity("/home/u/skillopt"))
    found = qualify.same_engine_sources(tmp_path / "nested" / "qualification.json", old)
    assert found["same"] is True and found["roots"]["new"] == "/home/u/skillopt"
    # one changed source, one source only one side has, one changed field: each named
    changed = identity("/data/execskill-20261021-source")
    changed["sources"]["/data/execskill-20261021-source/" + SOURCES[6]] = "f" * 64
    changed["sources"]["/data/execskill-20261021-source/skillopt/continual_eval/extra.py"] = "e" * 64
    changed["memory_mb"] = 2048
    engine_record(tmp_path / "changed" / "qualification.json", changed)
    found = qualify.same_engine_sources(tmp_path / "changed" / "qualification.json", old)
    assert found["same"] is False and found["fields"]["differing"] == ["memory_mb"]
    assert found["sources"] == {"new": 8, "old": 7, "equal": 6,
                                "differing": ["skillopt/continual_eval/extra.py", SOURCES[6]]}
    image = identity("/data/execskill-20261021-source", image_id="sha256:" + "2" * 64)
    engine_record(tmp_path / "image" / "qualification.json", image)
    found = qualify.same_engine_sources(tmp_path / "image" / "qualification.json", old)
    assert found["same"] is False and found["fields"]["differing"] == ["image_id"] and found["sources"]["equal"] == 7
    # only sealed, qualified v7 records are compared; sources must be modules of the package
    engine_record(tmp_path / "rejected" / "qualification.json", identity("/x"), status="rejected")
    with pytest.raises(ValueError, match="Not a qualified"):
        qualify.same_engine_sources(tmp_path / "rejected" / "qualification.json", old)
    with pytest.raises(ValueError, match="package"):
        qualify.snapshot_root({"/opt/elsewhere/sheet_recalc.py": "0" * 64})
    with pytest.raises(ValueError, match="absolute"):
        qualify.snapshot_root({"skillopt/sheet_recalc.py": "0" * 64})
