"""Fixture-only CLI tests; no benchmark or real engine outcome claims."""
import base64
from pathlib import Path

import pytest

from scripts import replay_sheet_passive_links as cli
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import sheet_passive_links as links
from skillopt.continual_eval import sheet_recalc as recalc
from skillopt.continual_eval.core import read_json, write_json
from tests.test_continual_eval_sheet_passive_links import IMAGE, display_fixture, fixture, native_fixture


@pytest.mark.parametrize("name", cli.NEW_EXPECTED)
def test_all_new_control_inputs_follow_declared_boundary(tmp_path, name):
    path = tmp_path / (name + ".xlsx")
    cli._fixture(path, name)
    assert recalc.screen(path) == "unsupported_external_relationship"
    if cli.NEW_EXPECTED[name] is None:
        with pytest.raises(ValueError):
            links._checked_screen(path)
    else:
        assert links._checked_screen(path)["hyperlink_count"] == 1


@pytest.mark.parametrize("name,actual,qualified", [
    ("passive_correct", "3", True), ("passive_correct", "4", False),
    ("passive_wrong", "4", True), ("passive_wrong", "3", False),
])
def test_wrong_candidate_is_not_redefined_as_correct(tmp_path, name, actual, qualified):
    path = fixture(tmp_path / "control.xlsx", cache=actual)
    control = {"name": name, "path": str(path), "expected": cli.NEW_EXPECTED[name]}
    engine = links.Recalculator(IMAGE)
    receipt = native_fixture(engine, path)
    receipt = seal({**{k: v for k, v in receipt.items() if k != "record_hash"},
                    "execution_input_sha256": recalc.sha(path)})
    row = cli._control(control, receipt, tmp_path)
    assert row["qualified"] is qualified


def test_unknown_negative_needs_precontainer_rejection_and_cleanup(tmp_path):
    control = {"name": "passive_file", "expected": None, "path": str(tmp_path / "unused")}
    base = {"status": "unknown", "reason": "unsupported_external_relationship",
            "record_hash": "fixture", "container_execution_attempted": False, "cleanup_confirmed": True}
    assert cli._control(control, base, tmp_path)["qualified"]
    for change in ({"container_execution_attempted": True}, {"reason": "timeout"}, {"cleanup_confirmed": False}):
        assert not cli._control(control, {**base, **change}, tmp_path)["qualified"]


def test_control_expected_cannot_be_altered_to_match_actual(tmp_path):
    with pytest.raises(ValueError, match="expected changed"):
        cli._control({"name": "passive_correct", "expected": 4}, {}, tmp_path)


def test_existing_34_controls_use_original_judgment_function(tmp_path, monkeypatch):
    calls = []
    control, receipt = {"name": "array_wrong"}, {"status": "fixture"}
    monkeypatch.setattr(cli.replay, "_control_result", lambda *args: calls.append(args) or {"sentinel": True})
    assert cli._control(control, receipt, tmp_path) == {"sentinel": True}
    assert calls == [(control, receipt, tmp_path)]


def test_unqualified_link_engine_cannot_prepare(tmp_path, monkeypatch):
    q = tmp_path / "qual" / "qualification.json"
    write_json(q, seal({"status": "rejected"}))
    monkeypatch.setattr(cli, "_previous", lambda *a: pytest.fail("No prior read allowed before qualification"))
    with pytest.raises(ValueError, match="qualification"):
        cli.prepare(tmp_path / "old", q, tmp_path / "new", tmp_path / "lock")


def test_sources_bound_and_engine_scope_cannot_inherit_parent_identity(tmp_path):
    protocol = {"version": cli.VERSION, "root": str(tmp_path), "sources": {}, "inventory": {},
                "engine": links.Recalculator(IMAGE).identity}
    with pytest.raises(ValueError, match="source/root"):
        cli._engine(protocol, tmp_path)
    protocol["sources"] = cli._sources()
    protocol["engine"]["version"] = "old"
    with pytest.raises(ValueError, match="engine identity"):
        cli._engine(protocol, tmp_path)


def test_link_scoring_controls_have_fixed_reference_and_actual_wrong_failure(tmp_path, monkeypatch):
    reference = tmp_path / "reference.xlsx"
    cli.scoring._fixture_book(reference, {"B1": 3})
    correct = fixture(tmp_path / "correct.xlsx", cache="3")
    wrong = fixture(tmp_path / "wrong.xlsx", cache="4")
    seen = []
    def traced(self, path):
        assert Path(path) != reference
        seen.append(str(path))
        return native_fixture(self, path)
    monkeypatch.setattr(links.Recalculator, "_run_passive_native", traced)
    protocol = {"link_score_reference": str(reference), "record_hash": "engineering-fixture",
                "inventory": {str(reference): recalc.sha(reference)}, "controls": [
                    {"name": "passive_correct", "path": str(correct)}, {"name": "passive_wrong", "path": str(wrong)}]}
    rows = cli._link_scores(protocol, links.Recalculator(IMAGE))
    assert [r["result"]["status"] for r in rows] == ["pass", "fail"]
    assert all(r["qualified"] for r in rows) and len(seen) == 2


def _fixture_donor(tmp_path, monkeypatch, *, version="passive-hyperlinks-frozen-h-replay-v1"):
    """Authenticity/association plumbing fixture, not engine qualification."""
    root = tmp_path / "donor"
    root.mkdir()
    controls = []
    legacy = []
    for name in sorted(cli.replay._controls("v8") | set(cli.NEW_EXPECTED)):
        path = root / (name + ".xlsx")
        path.write_bytes(b"fixture-only bytes " + name.encode())
        row = {"name": name, "path": str(path), "expected": cli.NEW_EXPECTED.get(name, 3)}
        controls.append(row)
        if name not in cli.NEW_EXPECTED:
            legacy.append(dict(row))
    identity = {"image_id": IMAGE, "sources": {}}
    protocol = seal({"version": version, "kind": "qualification",
        "root": str(root), "engine": identity, "controls": controls, "sources": {},
        "inventory": cli.replay._files([c["path"] for c in controls]), "native_lock": "fixture-only"})
    write_json(root / "protocol.json", protocol)
    receipts, rows = [], []
    for control in controls:
        receipt = seal({"input_sha256": recalc.sha(control["path"]), "identity": identity})
        receipts.append(receipt)
        row = seal({"name": control["name"], "protocol_hash": protocol["record_hash"],
                    "receipt_hash": receipt["record_hash"]})
        rows.append(row)
        write_json(root / "controls" / (control["name"] + ".json"), row)
    costs = {"open_workbook_intents": 0, "cleanup_unconfirmed": 0}
    class Donor:
        def receipts(self):
            return receipts
        def unsafe_cleanup(self):
            return False
    monkeypatch.setattr(cli.replay, "DurableEngine", lambda *a: Donor())
    monkeypatch.setattr(cli.replay, "_execution", lambda *a: costs)
    extra = ({"score_qualification": {"status": "qualified", "controls": [{}] * 18}, "link_score_controls": [
        {"name": n, "expected": s, "qualified": True, "result": {"status": s}}
        for n, s in (("passive_correct", "pass"), ("passive_wrong", "fail"))]} if version.endswith("v2") else {})
    value = seal({"version": protocol["version"], "status": "qualified" if extra else "rejected",
                  "protocol_hash": protocol["record_hash"], "engine": identity, "controls": rows,
                  "execution": costs, "model_api_calls": 0, **extra})
    path = root / "qualification.json"
    write_json(path, value)
    return path, legacy


def test_rejected_a_inputs_are_reused_without_inheriting_authorization(tmp_path, monkeypatch):
    path, legacy = _fixture_donor(tmp_path, monkeypatch)
    controls, inventory = cli._passive_fixtures(path, legacy, IMAGE)
    assert len(controls) == 7 and set(cli.NEW_EXPECTED) == {c["name"] for c in controls}
    assert all(str(path.parent) in c["path"] and inventory[c["path"]] == recalc.sha(c["path"]) for c in controls)
    assert read_json(path)["status"] == "rejected"


@pytest.mark.parametrize("change", ["bytes", "expected"])
def test_mixed_legacy_donors_are_rejected(tmp_path, monkeypatch, change):
    path, legacy = _fixture_donor(tmp_path, monkeypatch)
    if change == "expected":
        legacy[0]["expected"] = "different"
    else:
        replacement = tmp_path / "other.xlsx"
        replacement.write_bytes(b"other valid donor bytes")
        legacy[0]["path"] = str(replacement)
    with pytest.raises(ValueError, match="fixture donors differ"):
        cli._passive_fixtures(path, legacy, IMAGE)


def test_c_reuses_b_all_seven_original_passive_inputs_without_inheriting_authorization(tmp_path, monkeypatch):
    path, legacy = _fixture_donor(tmp_path, monkeypatch, version="passive-hyperlinks-frozen-h-replay-v2")
    controls, inventory = cli._passive_fixtures(path, legacy, IMAGE, prior=True)
    assert len(controls) == 7 and {c["name"] for c in controls} == set(cli.NEW_EXPECTED)
    assert all(inventory[c["path"]] == recalc.sha(c["path"]) for c in controls)
    with pytest.raises(ValueError, match="fixture evidence"):
        cli._passive_fixtures(path, legacy, IMAGE)  # A and B donor versions are explicit.


@pytest.mark.parametrize("change", ["bytes", "expected"])
def test_b_and_q34_donor_mismatch_is_not_authorized(tmp_path, monkeypatch, change):
    path, legacy = _fixture_donor(tmp_path, monkeypatch, version="passive-hyperlinks-frozen-h-replay-v2")
    if change == "expected":
        legacy[0]["expected"] = "different"
    else:
        replacement = tmp_path / "different.xlsx"
        replacement.write_bytes(b"different valid donor")
        legacy[0]["path"] = str(replacement)
    with pytest.raises(ValueError, match="fixture donors differ"):
        cli._passive_fixtures(path, legacy, IMAGE, prior=True)


def test_original_a_cannot_be_silently_used_in_place_of_b(tmp_path, monkeypatch):
    path, legacy = _fixture_donor(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="fixture evidence"):
        cli._passive_fixtures(path, legacy, IMAGE, prior=True)


@pytest.mark.parametrize("name", cli.DISPLAY_EXPECTED)
def test_display_control_matches_real_export_structure_with_unchanged_numeric_expectation(tmp_path, name):
    path = tmp_path / (name + ".xlsx")
    cli._fixture(path, name)
    assert links._checked_screen(path)["hyperlink_count"] == 1
    import openpyxl
    book = openpyxl.load_workbook(path)
    assert book.active["C1"].value == "Documentation"
    assert book.active["C1"].hyperlink.display == book.active["C1"].hyperlink.target != book.active["C1"].value
    assert book.active["C1"].hyperlink.tooltip is None
    assert book.active["B1"].value == ("=A1+1" if cli.DISPLAY_EXPECTED[name] == 3 else "=A1+2")
    book.close()


@pytest.mark.parametrize("restored,qualified", [(1, True), (0, False), (True, False), (None, False)])
def test_new_display_qualification_requires_actual_new_view_branch(tmp_path, monkeypatch, restored, qualified):
    source = display_fixture(tmp_path / "source.xlsx")
    exported = display_fixture(tmp_path / "export.xlsx", exported=True)
    def transformed(self, path):
        row = native_fixture(self, path)
        return seal({**{k: v for k, v in row.items() if k != "record_hash"},
                     "output_base64": base64.b64encode(exported.read_bytes()).decode(), "output_sha256": recalc.sha(exported)})
    monkeypatch.setattr(links.Recalculator, "_run_passive_native", transformed)
    receipt = links.Recalculator(IMAGE).run(source)
    receipt["display_comparison_view"]["display_attributes_restored"] = restored
    receipt = seal({k: v for k, v in receipt.items() if k != "record_hash"})
    control = {"name": "display_href_correct", "path": str(source), "expected": 3}
    assert cli._control(control, receipt, tmp_path)["qualified"] is qualified


def test_c_adds_display_scores_without_replacing_original_link_scores(tmp_path, monkeypatch):
    reference = tmp_path / "reference.xlsx"
    cli.scoring._fixture_book(reference, {"B1": 3})
    controls = []
    exports = {}
    for name, result in {"passive_correct": "3", "passive_wrong": "4",
                         "display_href_correct": "3", "display_href_wrong": "4"}.items():
        path = tmp_path / (name + ".xlsx")
        if name.startswith("display_"):
            display_fixture(path, cache=result)
            exports[str(path)] = display_fixture(tmp_path / (name + "-export.xlsx"), cache=result, exported=True)
        else:
            fixture(path, cache=result)
            exports[str(path)] = path
        controls.append({"name": name, "path": str(path)})
    calls = []
    def transformed(self, path):
        assert path != reference
        calls.append(path)
        row = native_fixture(self, path)
        exported = exports[str(path)]
        return seal({**{k: v for k, v in row.items() if k != "record_hash"},
                     "output_base64": base64.b64encode(exported.read_bytes()).decode(), "output_sha256": recalc.sha(exported)})
    monkeypatch.setattr(links.Recalculator, "_run_passive_native", transformed)
    protocol = {"version": cli.VERSION, "link_score_reference": str(reference), "record_hash": "fixture",
                "inventory": {str(reference): recalc.sha(reference)}, "controls": controls}
    rows = cli._link_scores(protocol, links.Recalculator(IMAGE))
    assert [r["name"] for r in rows] == [c["name"] for c in controls]
    assert [r["result"]["status"] for r in rows] == ["pass", "fail", "pass", "fail"]
    assert all(r["qualified"] for r in rows) and len(calls) == 4


class FakeEngine:
    def unsafe_cleanup(self):
        return False


def test_replay_preserves_undelivered_and_invokes_frozen_h_only_on_candidate(tmp_path, monkeypatch):
    root, previous, original = tmp_path / "new", tmp_path / "previous", tmp_path / "original"
    for p in (root, previous, original):
        p.mkdir()
        (p / ".writer.lock").touch()
    delivered = fixture(tmp_path / "prediction.xlsx")
    slots = []
    for index, prediction in enumerate([
        {"status": "available", "reason": "ok", "output": {"cases": [{"status": "available", "output_base64": base64.b64encode(delivered.read_bytes()).decode()}]}},
        {"status": "unknown", "reason": "native_exception:TypeError", "output": None},
    ]):
        saved = seal({"prediction": prediction})
        path = original / f"{index}.json"
        write_json(path, saved)
        slots.append({"id": str(index), "prediction_path": str(path), "prediction_hash": saved["record_hash"],
                      "references": ["reference-must-not-be-recalculated"], "reference_manifests": ["fixture"],
                      "answer_position": "B1", "old_status": "unknown", "previous_status": "unknown"})
    write_json(root / "host_only/references/fixture.json", seal({"status": "available"}))
    protocol = seal({"version": cli.VERSION, "root": str(root), "kind": "replay", "slots": slots,
                     "previous_replay": str(previous), "original_source": str(original), "truth_basis": "engineering_fixture"})
    write_json(root / "protocol.json", protocol)
    calls = []
    def score(path, reference, answer, engine, manifest):
        assert Path(path).read_bytes() == delivered.read_bytes()
        assert reference == "reference-must-not-be-recalculated" and answer == "B1"
        calls.append(path)
        return {"status": "fail", "reason": "fixture_actual_wrong"}
    monkeypatch.setattr(cli, "_engine", lambda *a: FakeEngine())
    monkeypatch.setattr(cli.replay, "_execution", lambda *a: {"open_workbook_intents": 0, "cleanup_unconfirmed": 0})
    monkeypatch.setattr(cli.scoring, "evaluate", score)
    value = cli.run(root)
    assert value["counts"] == {"fail": 1, "unknown": 1} and len(calls) == 1
    assert value["status"] == "pending"  # Fixtures are not an actual 160-position panel.
    assert read_json(root / "positions/1.json")["delivery_status"] == "undelivered"
    assert cli.run(root) == value and len(calls) == 1
