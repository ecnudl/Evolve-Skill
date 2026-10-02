"""New opt-in compatibility must never relax task identity or invent caches."""
import base64
import io
import xml.etree.ElementTree as ET
import zipfile

import openpyxl
import pytest

from skillopt.continual_eval import spreadsheet_compat as compat


@pytest.mark.parametrize("text,sheets,targets", [
    ("Daily Numbers'!Q3:Q24", ["Daily Numbers"], [("Daily Numbers", "Q3:Q24")]),
    ("Sheet1'!A1:F14", ["Sheet1"], [("Sheet1", "A1:F14")]),
    ("'PL Recon Items!'A1:D2,'Statement Recon Items!'A1:J3", ["PL Recon Items", "Statement Recon Items"],
     [("PL Recon Items", "A1:D2"), ("Statement Recon Items", "A1:J3")]),
    ("'Sheet1!'A1:A50,'Sheet2!'A1:E20,'Sheet3!'A1:A50'", ["Sheet1", "Sheet2", "Sheet3"],
     [("Sheet1", "A1:A50"), ("Sheet2", "A1:E20"), ("Sheet3", "A1:A50")]),
    ("'Main!'A2:M70", ["Main"], [("Main", "A2:M70")]),
    ("Sheet1'!G2:I7", ["Sheet1"], [("Sheet1", "G2:I7")]),
    ("Compiled and located schools da'!B2:B1461", ["Compiled and located schools da"],
     [("Compiled and located schools da", "B2:B1461")]),
])
def test_official_quote_compat(text, sheets, targets):
    result = compat.resolve_targets(text, sheets)
    assert result["targets"] == targets
    assert result["mode"] == "official_edge_single_quotes"


@pytest.mark.parametrize("text", ["", "A0", "A2:A1", "XFE1", "A1048577", "A1,", "A1,,B2", "A1+1",
                                      "Unknown!A1", "Unknown'!A1", "S!!A1", "S!A1:B0", "S!A1:XFD1048576",
                                      "S!A1);import os", "[other.xlsx]S!A1", "!A1"])
def test_bad_target_not_silently_accepted(text):
    with pytest.raises(ValueError):
        compat.resolve_targets(text, ["S"])


def test_valid_complex_sheet_names_keep_strict_semantics():
    result = compat.resolve_targets("'a,b'!A1,'Bob''s'!$B$2", ["a,b", "Bob's"])
    assert result["mode"] == "strict"
    assert result["targets"] == [("a,b", "A1"), ("Bob's", "$B$2")]


def workbook(tmp_path, name, *, cache_kind="string_empty", value="", second=1):
    """Author a fixture with explicit OOXML cache states; no benchmark assets."""
    book = openpyxl.Workbook()
    book.active.title = "S"
    book.active["A1"] = '=IF(1,"",2)'
    book.active["B1"] = second
    raw = io.BytesIO()
    book.save(raw)
    book.close()
    target = tmp_path / name
    ns = {"m": compat.MAIN_NS}
    with zipfile.ZipFile(raw) as source, zipfile.ZipFile(target, "w") as dest:
        for member in source.infolist():
            body = source.read(member.filename)
            if member.filename == "xl/worksheets/sheet1.xml":
                root = ET.fromstring(body)
                cell = root.find('.//m:c[@r="A1"]', ns)
                cell.set("t", "str" if cache_kind in {"string_empty", "string_missing", "string_value"} else "n")
                cached = cell.find("m:v", ns)
                if cached is not None:
                    cell.remove(cached)
                if cache_kind not in {"string_missing", "numeric_missing"}:
                    cached = ET.SubElement(cell, f"{{{compat.MAIN_NS}}}v")
                    cached.text = value
                body = ET.tostring(root)
            dest.writestr(member, body)
    return target


def test_explicit_empty_string_is_cache_not_missing(tmp_path):
    gold = workbook(tmp_path, "gold.xlsx")
    pred = workbook(tmp_path, "pred.xlsx")
    before = gold.read_bytes(), pred.read_bytes()
    assert compat.explicit_empty_formula_strings(gold) == {("S", "A1")}
    old = compat._legacy().evaluate(pred, gold, "", "A1")
    assert old["status"] == "unknown"  # Historical protocol remains unchanged.
    result = compat.evaluate(pred, gold, "", "S'!A1")
    assert result["status"] == "passed"
    assert result["evidence"]["reference_empty_string_caches_used"] == 1
    assert result["evidence"]["prediction_empty_string_caches_used"] == 1
    assert before == (gold.read_bytes(), pred.read_bytes())


@pytest.mark.parametrize("kind", ["string_missing", "numeric_missing", "numeric_empty"])
def test_absent_or_ambiguous_cache_stays_unknown(tmp_path, kind):
    gold = workbook(tmp_path, "gold.xlsx")
    pred = workbook(tmp_path, "pred.xlsx", cache_kind=kind)
    assert compat.explicit_empty_formula_strings(pred) == set()
    assert compat.evaluate(pred, gold, "", "A1")["status"] == "unknown"
    assert compat.reference_readiness(pred, "A1")["unresolved_formula_caches"] == 1


def test_real_mismatch_survives_another_unknown(tmp_path):
    gold = workbook(tmp_path, "gold.xlsx")
    pred = workbook(tmp_path, "pred.xlsx", cache_kind="numeric_empty", second=2)
    result = compat.evaluate(pred, gold, "", "A1:B1")
    assert result["status"] == "failed"
    assert result["evidence"]["unavailable_cells"] == 1


def test_bad_reference_sheet_is_unknown_not_model_error(tmp_path):
    gold = workbook(tmp_path, "gold.xlsx")
    pred = workbook(tmp_path, "pred.xlsx")
    assert compat.evaluate(pred, gold, "", "Absent'!A1")["status"] == "unknown"


def test_blank_reference_not_equal_to_nonempty_prediction(tmp_path):
    gold = workbook(tmp_path, "gold.xlsx")
    pred = workbook(tmp_path, "pred.xlsx", cache_kind="string_value", value="wrong")
    assert compat.evaluate(pred, gold, "", "A1")["status"] == "failed"


@pytest.mark.parametrize("member,body", [
    ("xl/workbook.xml", b'<!DOCTYPE doc [<!ENTITY x "bad">]><x/>'),
    ("xl/workbook.xml", '<!DOCTYPE doc [<!ENTITY x "bad">]><x/>'.encode("utf-16")),
    ("../escape.xml", b"<x/>"),
    ("/escape.xml", b"<x/>"),
])
def test_untrusted_zip_or_xml_rejected(tmp_path, member, body):
    path = tmp_path / "bad.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, body)
    with pytest.raises(compat.CompatibilityError):
        compat.explicit_empty_formula_strings(path)


def test_missing_output_distinct_from_bad_reference(tmp_path):
    gold = workbook(tmp_path, "gold.xlsx")
    assert compat.evaluate(tmp_path / "none.xlsx", gold, "", "A1")["status"] == "missing_output"
    assert compat.evaluate(tmp_path / "none.xlsx", tmp_path / "bad.xlsx", "", "A1")["status"] == "unknown"


def test_backend_explicit_profile_preserves_old_default(tmp_path):
    from skillopt.continual_eval import backends
    gold = workbook(tmp_path, "gold.xlsx")
    pred = workbook(tmp_path, "pred.xlsx")
    prediction = {"status": "available", "output": {"cases": [{"status": "available",
        "output_base64": base64.b64encode(pred.read_bytes()).decode()}]}}
    public = {"answer_position": "S'!A1"}
    private = {"test_files": [str(gold)], "answer_position": public["answer_position"]}
    old = backends.score("spreadsheetbench", public, private, prediction)
    assert old["status"] == "unknown"
    new = backends.score("spreadsheetbench", public, private, prediction,
                         runtime={"spreadsheet_scorer": compat.VERSION})
    assert new["status"] == "pass"
    assert new["metrics"]["cases"][0]["evaluator_version"] == compat.VERSION
    bad = backends.score("spreadsheetbench", public, private, prediction,
                         runtime={"spreadsheet_scorer": "unsupported-profile"})
    assert bad["status"] == "unknown"


def test_unsupported_profile_blocks_before_native_readiness(monkeypatch):
    from skillopt.continual_eval import backends
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid profile must not invoke Docker")
    monkeypatch.setattr(backends, "_native", forbidden)
    assert backends.readiness("spreadsheetbench", {"spreadsheet_scorer": "bad"})["status"] == "unsupported"
