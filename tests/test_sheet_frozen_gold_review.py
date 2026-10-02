"""Independent malformed-reference and immutable-H review controls."""

import base64
import copy
import io
import xml.etree.ElementTree as ET
import zipfile

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import sheet_frozen_gold as gold

NS = gold.compat.MAIN_NS
PROVENANCE = {"source_protocol_hash": "d" * 64, "task_id": "review-fixture", "evidence_kind": "engineering_fixture"}


def _book(path, cells, caches=None):
    gold._fixture_book(path, cells, caches)
    return path


def _worksheet_edit(path, callback):
    result = io.BytesIO()
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(result, "w") as target:
        for member in source.infolist():
            raw = source.read(member.filename)
            if member.filename == "xl/worksheets/sheet1.xml":
                tree = ET.fromstring(raw)
                callback(tree)
                raw = ET.tostring(tree, encoding="utf-8", xml_declaration=True)
            target.writestr(member, raw)
    path.write_bytes(result.getvalue())


def _manifest(path, target="S!B1"):
    return gold.freeze_reference(path, gold.recalc.sha(path), target, provenance=PROVENANCE)


@pytest.mark.parametrize("spelling", ["B1", "b1"])
def test_duplicate_cell_identity_rejected_after_coordinate_normalization(tmp_path, spelling):
    path = _book(tmp_path / "duplicate.xlsx", {"B1": 2})

    def edit(tree):
        row = tree.find(f".//{{{NS}}}row")
        duplicate = copy.deepcopy(row.find(f"{{{NS}}}c"))
        duplicate.set("r", spelling)
        row.append(duplicate)

    _worksheet_edit(path, edit)
    assert _manifest(path)["status"] == "unknown"


def test_orphan_shared_formula_with_cached_value_is_not_a_valid_reference(tmp_path):
    path = _book(tmp_path / "orphan.xlsx", {"B1": "=1+1"}, {"B1": ("n", "2")})

    def edit(tree):
        formula = tree.find(f".//{{{NS}}}f")
        formula.attrib.update(t="shared", si="404")
        formula.text = None

    _worksheet_edit(path, edit)
    assert _manifest(path)["status"] == "unknown"


def test_shared_formula_missing_cache_is_not_an_ordinary_blank(tmp_path):
    path = _book(tmp_path / "shared.xlsx", {"B1": "=1+1", "B2": "=1+1"}, {"B1": ("n", "2")})

    def edit(tree):
        formulas = tree.findall(f".//{{{NS}}}f")
        formulas[0].attrib.update(t="shared", si="0", ref="B1:B2")
        formulas[1].attrib.update(t="shared", si="0")
        formulas[1].text = None

    _worksheet_edit(path, edit)
    assert _manifest(path, "S!B1:B2")["status"] == "unknown"


@pytest.mark.parametrize(
    "shape,expected", [("valid", "available"), ("outside_range", "unknown"), ("duplicate_anchor", "unknown")]
)
def test_shared_formula_anchor_and_follower_structure(tmp_path, shape, expected):
    path = _book(
        tmp_path / "shared-cached.xlsx", {"B1": "=ROW()", "B2": "=ROW()"}, {"B1": ("n", "1"), "B2": ("n", "2")}
    )

    def edit(tree):
        anchor, follower = tree.findall(f".//{{{NS}}}f")
        anchor.attrib.update(t="shared", si="0", ref="B1" if shape == "outside_range" else "B1:B2")
        follower.attrib.update(t="shared", si="0")
        if shape == "duplicate_anchor":
            follower.set("ref", "B1:B2")
        else:
            follower.text = None

    _worksheet_edit(path, edit)
    result = _manifest(path, "S!B1:B2")
    assert result["status"] == expected
    if shape == "valid":
        assert result["cache_counts"] == {"available_calculated_cache": 2}
        assert result["target_cells"] == 2


def test_cell_metadata_without_standard_metadata_path_stays_unknown(tmp_path):
    path = _book(tmp_path / "metadata.xlsx", {"B1": 2})

    def edit(tree):
        cell = tree.find(f".//{{{NS}}}c")
        cell.set("cm", "1")
        cell.find(f"{{{NS}}}v").text = None

    _worksheet_edit(path, edit)
    assert _manifest(path)["status"] == "unknown"


def test_malformed_formula_type_is_not_accepted_as_complete_cache(tmp_path):
    path = _book(tmp_path / "malformed.xlsx", {"B1": "=1+1"}, {"B1": ("n", "2")})

    def edit(tree):
        tree.find(f".//{{{NS}}}f").set("t", "not-a-formula-type")

    _worksheet_edit(path, edit)
    assert _manifest(path)["status"] == "unknown"


def test_candidate_boolean_literal_rewrite_remains_unknown_under_new_h_protocol(tmp_path):
    reference = _book(tmp_path / "gold.xlsx", {"B1": 0, "B2": False})
    candidate = _book(tmp_path / "candidate.xlsx", {"B1": 0, "B2": False})
    exported = _book(tmp_path / "exported.xlsx", {"B1": 0, "B2": "=FALSE()"}, {"B2": ("b", "0")})
    frozen = _manifest(reference, "S!B1:B2")
    assert frozen["status"] == "available"
    assert frozen["cache_counts"] == {"literal": 2}

    class LiteralRewriteFixture:
        identity = {"version": "authored-boolean-export-control"}
        calls = []

        def run(self, path):
            self.calls.append(path)
            return seal(
                {
                    "identity": self.identity,
                    "input_sha256": gold.recalc.sha(path),
                    "status": "available",
                    "reason": "authored_literal_to_formula_export",
                    "cleanup_confirmed": True,
                    "output_base64": base64.b64encode(exported.read_bytes()).decode(),
                    "output_sha256": gold.recalc.sha(exported),
                }
            )

    engine = LiteralRewriteFixture()
    result = gold.evaluate(candidate, reference, "S!B1:B2", engine, frozen)
    assert result["status"] == "unknown"
    assert result["reason"] == "prediction:recalculation_changed_literal_cell"
    assert engine.calls == [candidate]
    assert gold.SCORE_EXPECTED["candidate_boolean_literal_limit"] == "unknown"
