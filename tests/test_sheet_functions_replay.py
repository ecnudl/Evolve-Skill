"""v8 qualification/dispatch fixtures; no Docker, model API or real effects."""
import json
from pathlib import Path

import openpyxl
import pytest

from scripts import replay_sheet_v6 as replay
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from tests.test_sheet_v6_replay import IMAGE, Fake, parent_fixture
from tests.test_sheet_v7_replay import _setup


def prior_fixture(tmp_path, monkeypatch, status="rejected"):
    """Closed q23 with authored receipts: eligible inputs, no real permission."""
    protocol = _setup(tmp_path, monkeypatch, "v7")
    root = tmp_path / "v7"
    fake = Fake()
    fake.identity = protocol["engine"]
    engine = replay.DurableEngine(fake, root, tmp_path / "native.lock")
    rows = []
    for spec in protocol["controls"]:
        receipt = engine.run(spec["path"])
        row = seal({"name": spec["name"], "protocol_hash": protocol["record_hash"],
                    "qualified": status == "qualified", "receipt_hash": receipt["record_hash"], "cleanup_confirmed": True})
        write_json(root / "controls" / (spec["name"] + ".json"), row)
        rows.append(row)
    path = root / "qualification.json"
    write_json(path, seal({"version": replay.VERSION, "status": status, "engine": protocol["engine"],
        "engine_profile": "v7", "protocol_hash": protocol["record_hash"], "controls": rows, "model_api_calls": 0}))
    return path, protocol


def setup(tmp_path, monkeypatch, status="rejected"):
    old, prior = prior_fixture(tmp_path, monkeypatch, status)
    new = replay._qual_setup(tmp_path / "v8", IMAGE, tmp_path / "old" / "qualification.json", tmp_path / "native.lock",
                             "v8", prior_profile_qualification=old)
    return old, prior, new


def test_opt_in_v8_keeps_all23_original_inputs_roles_and_expected(tmp_path, monkeypatch):
    old, prior, new = setup(tmp_path, monkeypatch)
    assert replay._profile({}) == "v6"
    assert len(replay._controls("v6")) == 20 and len(replay._controls("v7")) == 23
    assert len(new["controls"]) == 34 and {c["name"] for c in new["controls"]} == replay._controls("v8")
    assert new["engine_profile"] == "v8" and new["engine"]["version"] == replay.v8.VERSION
    assert not new["old_authorization_inherited"] and new["model_api_calls"] == 0
    assert new["prior_profile_qualification"] == str(old)
    controls = {c["name"]: c for c in new["controls"]}
    for control in prior["controls"]:
        assert controls[control["name"]] == control
        assert new["inventory"][control["path"]] == replay.v5.sha(control["path"])
        assert str(old.parent / "controls" / (control["name"] + ".json")) in new["inventory"]
    assert not (tmp_path / "v8/recalculations").exists()
    replay._engine(new, tmp_path / "v8")  # Identity only, no execution.


def test_old_passed_authorization_does_not_skip_new_qualification(tmp_path, monkeypatch):
    _, _, new = setup(tmp_path, monkeypatch, status="qualified")
    (tmp_path / "v8/PAUSE").touch()
    result = replay.qualify(tmp_path / "v8")
    assert result["status"] == "pending" and result["controls"] == []
    assert result["execution"]["containers_attempted"] == 0
    assert not (tmp_path / "v8/qualification.json").exists()
    assert len(new["controls"]) == 34


def test_old23_alone_cannot_be_relabelled_as_v8_authorization(tmp_path, monkeypatch):
    _, protocol = prior_fixture(tmp_path, monkeypatch, status="qualified")
    path = tmp_path / "v7/protocol.json"
    protocol.pop("record_hash")
    protocol["engine_profile"] = "v8"
    protocol["engine"] = replay.v8.Recalculator(IMAGE).identity
    path.write_text(json.dumps(seal(protocol)))
    with pytest.raises(ValueError, match="control roster"):
        replay.qualify(tmp_path / "v7")


@pytest.mark.parametrize("damage", ["input", "expected", "role", "receipt", "pending"])
def test_prior23_binding_rejects_modified_inputs_roles_expected_and_receipts(tmp_path, monkeypatch, damage):
    old, protocol = prior_fixture(tmp_path, monkeypatch)
    q = read_json(old, sealed=True)
    spec = next(c for c in protocol["controls"] if c["name"] == "original_date_formula")
    if damage == "input":
        Path(spec["path"]).write_bytes(b"authored corruption")
    elif damage in {"expected", "role"}:
        spec["expected" if damage == "expected" else "name"] = 46000 if damage == "expected" else "renamed"
        protocol.pop("record_hash")
        protocol = seal(protocol)
        (old.parent / "protocol.json").write_text(json.dumps(protocol))
        q["protocol_hash"] = protocol["record_hash"]
    elif damage == "receipt":
        key = replay.digest({"input": replay.v5.sha(spec["path"]), "engine": q["engine"]})
        path = old.parent / "recalculations" / (key + ".json")
        receipt = read_json(path, sealed=True)
        receipt.pop("record_hash")
        receipt["input_sha256"] = "a" * 64
        path.write_text(json.dumps(seal(receipt)))
    else:
        q["status"] = "pending"
    q.pop("record_hash")
    old.write_text(json.dumps(seal(q)))
    with pytest.raises(ValueError, match="q23"):
        replay._qual_setup(tmp_path / "v8", IMAGE, tmp_path / "old/qualification.json", tmp_path / "native.lock",
                           "v8", prior_profile_qualification=old)
    assert not (tmp_path / "v8").exists()


@pytest.mark.parametrize("name", ["ifna_fallback", "aggregate_wrong", "original_date_literal"])
def test_resealed_new_protocol_cannot_relax_expected_values(tmp_path, monkeypatch, name):
    _, _, protocol = setup(tmp_path, monkeypatch)
    next(c for c in protocol["controls"] if c["name"] == name)["expected"] = 1234
    protocol.pop("record_hash")
    (tmp_path / "v8/protocol.json").write_text(json.dumps(seal(protocol)))
    with pytest.raises(ValueError, match="expected"):
        replay.qualify(tmp_path / "v8")


def test_profile_and_prior_source_cannot_change_on_resume(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="Frozen engine profile"):
        replay.qualify(tmp_path / "v8", engine_version="v7")
    with pytest.raises(ValueError, match="Frozen prior profile"):
        replay.qualify(tmp_path / "v8", prior_profile_qualification=tmp_path / "different.json")


def test_function_fixtures_express_exact_supported_cases(tmp_path, monkeypatch):
    _, _, protocol = setup(tmp_path, monkeypatch)
    for spec in protocol["controls"]:
        name = spec["name"]
        if name not in replay.V8_EXPECTED:
            continue
        assert spec["expected"] == replay.V8_EXPECTED[name]
        book = openpyxl.load_workbook(spec["path"], data_only=False)
        sheet = book["S"]
        if name == "ifna_fixed_array":
            assert sheet["B1"].value.ref == "B1:B2"
            assert sheet["B1"].value.text == "=_xlfn.IFNA(VLOOKUP(A1:A2,D1:E2,2,FALSE()),5)"
            assert spec["expected"] == {"B1": 7, "B2": 5}
        if name in {"aggregate_ignore_error", "aggregate_wrong"}:
            assert sheet["A2"].data_type == "f" and sheet["A2"].value == "=1/0"
        if name == "alias_text_not_rewritten":
            assert replay.v8.canonical_formula(sheet["B1"].value) == sheet["B1"].value
        if name == "alias_named_formula_rejected":
            assert "MyValue" in book.defined_names
        book.close()


@pytest.mark.parametrize("name", [n for n, expected in replay.V8_EXPECTED.items() if expected is None])
def test_rejection_control_requires_precontainer_unknown(tmp_path, name):
    source = tmp_path / "source.xlsx"
    replay._function_fixture(source, name)
    receipt = seal({"status": "unknown", "reason": "unsupported_extended_function", "cleanup_confirmed": True,
                    "container_execution_attempted": False})
    control = {"name": name, "path": str(source), "expected": None}
    assert replay._control_result(control, receipt, tmp_path)["qualified"]
    receipt["container_execution_attempted"] = True
    assert not replay._control_result(control, receipt, tmp_path)["qualified"]


def test_new_controls_rerun_old23_and_full160_replay_retains_denominator(tmp_path, monkeypatch):
    _, _, protocol = setup(tmp_path, monkeypatch, status="qualified")
    calls = []
    def execute(self, path):
        calls.append(replay.v5.sha(path))
        fake = Fake()
        fake.identity = self.identity
        return fake.run(path)
    monkeypatch.setattr(replay.v8.Recalculator, "run", execute)
    # Deliberately authored judgments test orchestration only, never real LO.
    monkeypatch.setattr(replay, "_control_result", lambda c, r, d: {
        "name": c["name"], "qualified": True, "receipt_hash": r["record_hash"],
        "cleanup_confirmed": r["cleanup_confirmed"], "reason": "authored_fixture"})
    qualification = replay.qualify(tmp_path / "v8")
    assert qualification["status"] == "qualified" and len(qualification["controls"]) == 34
    assert set(calls) == {replay.v5.sha(c["path"]) for c in protocol["controls"]}
    assert len(calls) == len(set(calls))  # Exact duplicate fixture bytes share a NEW receipt.
    parent = parent_fixture(tmp_path)
    before = replay._files(list(parent.rglob("*.json")))
    replay.prepare(parent, Path(__file__).resolve().parents[1], tmp_path / "replay", tmp_path / "v8/qualification.json",
                   tmp_path / "native.lock")
    result = replay.run(tmp_path / "replay")
    assert result["positions"] == result["completed"] == 160
    assert result["counts"] == {"pass": 152, "unknown": 8}
    assert result["engine_profile"] == "v8" and result["model_api_calls"] == 0
    assert not result["historical_scores_replaced"] and not result["feedback_allowed"]
    assert replay._files(list(parent.rglob("*.json"))) == before


@pytest.mark.parametrize("actual,qualified", [(4, True), (2, False)])
def test_wrong_result_cannot_be_repaired_into_expected_answer(tmp_path, monkeypatch, actual, qualified):
    from tests.test_continual_eval_sheet_recalc_v7 import _cache
    source, exported = tmp_path / "source.xlsx", tmp_path / "exported.xlsx"
    replay._function_fixture(source, "aggregate_wrong")
    exported.write_bytes(source.read_bytes())
    _cache(exported, str(actual))
    # The XML fixture includes another formula A2; synthetic content validation
    # is mocked here so this unit isolates result discrimination, not Calc.
    monkeypatch.setattr(replay.v5, "_recalc_valid", lambda *a: None)
    receipt = Fake().run(exported)
    receipt.update(function_alias_view={"version": replay.v8.ALIAS_VERSION,
        "original_input_sha256": replay.v5.sha(source), "execution_input_sha256": "b" * 64},
        execution_receipt={"input_sha256": "b" * 64, "identity": receipt["identity"],
                           "cleanup_confirmed": True, "container_execution_attempted": True})
    receipt.pop("record_hash")
    receipt = seal(receipt)
    control = {"name": "aggregate_wrong", "path": str(source), "expected": 4}
    assert replay._control_result(control, receipt, tmp_path)["qualified"] is qualified


def test_cli_accepts_explicit_v8_prior_profile_argument(tmp_path, monkeypatch, capsys):
    seen = []
    monkeypatch.setattr(replay, "qualify", lambda *args: seen.append(args) or {"status": "qualified"})
    assert replay.main(["qualify", "--output", str(tmp_path / "new"), "--engine-version", "v8",
                        "--prior-profile-qualification", str(tmp_path / "q23.json")]) == 0
    assert seen[0][4] == "v8" and seen[0][6] == str(tmp_path / "q23.json")
    assert json.loads(capsys.readouterr().out)["status"] == "qualified"
