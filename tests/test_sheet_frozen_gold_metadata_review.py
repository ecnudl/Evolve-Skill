"""Independent narrowly scoped metadata-H controls; all workbooks are authored."""

import copy
import io
import xml.etree.ElementTree as ET
import zipfile

import pytest
from openpyxl.worksheet.formula import ArrayFormula

from skillopt.continual_eval import sheet_frozen_gold as gold

MAIN = gold.compat.MAIN_NS
RELS = gold.compat.REL_NS
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
DYNAMIC = "http://schemas.microsoft.com/office/spreadsheetml/2017/dynamicarray"
MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheetMetadata+xml"
REL_TYPE = gold.compat.DOC_REL_NS + "/sheetMetadata"
PROVENANCE = {"source_protocol_hash": "e" * 64, "task_id": "metadata-review", "evidence_kind": "engineering_fixture"}
METADATA = f'''<metadata xmlns="{MAIN}" xmlns:xda="{DYNAMIC}">
<metadataTypes count="1"><metadataType name="XLDAPR" minSupportedVersion="120000" copy="1" pasteAll="1" pasteValues="1" merge="1" splitFirst="1" rowColShift="1" clearFormats="1" clearComments="1" assign="1" coerce="1" cellMeta="1"/></metadataTypes>
<futureMetadata name="XLDAPR" count="1"><bk><extLst><ext uri="{{bdbb8cdc-fa1e-496e-a857-3c3f30c029c3}}"><xda:dynamicArrayProperties fDynamic="1" fCollapsed="0"/></ext></extLst></bk></futureMetadata>
<cellMetadata count="1"><bk><rc t="1" v="0"/></bk></cellMetadata></metadata>'''


def workbook(path, *, cache=("n", "2"), formula_range="B1"):
    gold._fixture_book(path, {"B1": ArrayFormula(ref=formula_range, text="=2")}, {"B1": cache} if cache else None)
    parts = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            parts[name] = archive.read(name)
    sheet = ET.fromstring(parts["xl/worksheets/sheet1.xml"])
    sheet.find(f".//{{{MAIN}}}c").set("cm", "1")
    parts["xl/worksheets/sheet1.xml"] = ET.tostring(sheet)
    rels = ET.fromstring(parts["xl/_rels/workbook.xml.rels"])
    ET.SubElement(rels, f"{{{RELS}}}Relationship", {"Id": "reviewMetadata", "Type": REL_TYPE, "Target": "metadata.xml"})
    parts["xl/_rels/workbook.xml.rels"] = ET.tostring(rels)
    types = ET.fromstring(parts["[Content_Types].xml"])
    ET.SubElement(types, f"{{{CT}}}Override", {"PartName": "/xl/metadata.xml", "ContentType": MIME})
    parts["[Content_Types].xml"] = ET.tostring(types)
    parts["xl/metadata.xml"] = METADATA.encode()
    save_parts(path, parts)
    return parts


def save_parts(path, parts):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    path.write_bytes(buffer.getvalue())


def frozen(path, target="S!B1"):
    return gold.freeze_reference(path, gold.recalc.sha(path), target, provenance=PROVENANCE)


@pytest.mark.parametrize("cache", [("n", "2"), ("n", "0"), ("b", "0"), ("str", "")])
def test_metadata_keeps_explicit_zero_false_and_empty_string_without_freshness_claim(tmp_path, cache):
    path = tmp_path / "h.xlsx"
    workbook(path, cache=cache)
    before = path.read_bytes()
    result = frozen(path)
    assert result["status"] == "available"
    assert not result["reference_recalculated"] and not result["cache_freshness_established"]
    assert result["truth_basis"] == "frozen_benchmark_label_not_independent_oracle"
    assert path.read_bytes() == before


@pytest.mark.parametrize("target", ["S!B1:B2", "S!B2"])
def test_metadata_target_without_cell_is_not_ordinary_blank(tmp_path, target):
    path = tmp_path / "h.xlsx"
    workbook(path)
    assert frozen(path, target)["status"] == "unknown"


@pytest.mark.parametrize("cache", [None, ("n", ""), ("str", None)])
def test_metadata_missing_cache_is_not_empty_string(tmp_path, cache):
    path = tmp_path / "h.xlsx"
    parts = workbook(path, cache=cache)
    if cache == ("str", None):
        sheet = ET.fromstring(parts["xl/worksheets/sheet1.xml"])
        cell = sheet.find(f".//{{{MAIN}}}c")
        cell.remove(cell.find(f"{{{MAIN}}}v"))
        parts["xl/worksheets/sheet1.xml"] = ET.tostring(sheet)
        save_parts(path, parts)
    assert frozen(path)["status"] == "unknown"


@pytest.mark.parametrize(
    "damage",
    [
        "wrong_namespace",
        "wrong_dynamic_namespace",
        "wrong_count",
        "duplicate_type",
        "duplicate_future",
        "duplicate_cell_metadata",
        "extra_root_attribute",
        "extra_dynamic_attribute",
        "wrong_rc",
        "collapsed",
    ],
)
def test_metadata_schema_cannot_be_relaxed_by_duplicates_or_namespace(tmp_path, damage):
    path = tmp_path / "h.xlsx"
    parts = workbook(path)
    tree = ET.fromstring(parts["xl/metadata.xml"])
    if damage == "wrong_namespace":
        tree.tag = "{urn:unqualified}metadata"
    elif damage == "wrong_dynamic_namespace":
        tree.find(f".//{{{DYNAMIC}}}dynamicArrayProperties").tag = "{urn:unqualified}dynamicArrayProperties"
    elif damage == "wrong_count":
        tree.find(f"{{{MAIN}}}cellMetadata").set("count", "2")
    elif damage == "duplicate_type":
        types = tree.find(f"{{{MAIN}}}metadataTypes")
        types.append(copy.deepcopy(types[0]))
    elif damage in {"duplicate_future", "duplicate_cell_metadata"}:
        tag = "futureMetadata" if damage == "duplicate_future" else "cellMetadata"
        tree.append(copy.deepcopy(tree.find(f"{{{MAIN}}}{tag}")))
    elif damage == "extra_root_attribute":
        tree.set("unqualified", "1")
    elif damage == "extra_dynamic_attribute":
        tree.find(f".//{{{DYNAMIC}}}dynamicArrayProperties").set("unqualified", "1")
    elif damage == "wrong_rc":
        tree.find(f".//{{{MAIN}}}rc").set("v", "1")
    else:
        tree.find(f".//{{{DYNAMIC}}}dynamicArrayProperties").set("fCollapsed", "1")
    parts["xl/metadata.xml"] = ET.tostring(tree)
    save_parts(path, parts)
    assert frozen(path)["status"] == "unknown"


@pytest.mark.parametrize(
    "damage", ["duplicate_relationship", "external_relationship", "wrong_target", "wrong_mime", "duplicate_override"]
)
def test_metadata_requires_exact_package_relationship_and_content_type(tmp_path, damage):
    path = tmp_path / "h.xlsx"
    parts = workbook(path)
    if damage in {"wrong_mime", "duplicate_override"}:
        member = "[Content_Types].xml"
        tree = ET.fromstring(parts[member])
        node = next(node for node in tree if node.get("PartName") == "/xl/metadata.xml")
        if damage == "wrong_mime":
            node.set("ContentType", "application/xml")
        else:
            tree.append(copy.deepcopy(node))
    else:
        member = "xl/_rels/workbook.xml.rels"
        tree = ET.fromstring(parts[member])
        node = next(node for node in tree if node.get("Type") == REL_TYPE)
        if damage == "duplicate_relationship":
            duplicate = copy.deepcopy(node)
            duplicate.set("Id", "anotherMetadata")
            tree.append(duplicate)
        elif damage == "external_relationship":
            node.set("TargetMode", "External")
        else:
            node.set("Target", "../metadata.xml")
    parts[member] = ET.tostring(tree)
    save_parts(path, parts)
    assert frozen(path)["status"] == "unknown"


@pytest.mark.parametrize(
    "member,local_name", [("[Content_Types].xml", "Types"), ("xl/_rels/workbook.xml.rels", "Relationships")]
)
def test_metadata_package_roots_require_the_expected_namespace(tmp_path, member, local_name):
    path = tmp_path / "h.xlsx"
    parts = workbook(path)
    tree = ET.fromstring(parts[member])
    tree.tag = "{urn:unqualified}" + local_name
    parts[member] = ET.tostring(tree)
    save_parts(path, parts)
    assert frozen(path)["status"] == "unknown"


def test_metadata_relationship_cannot_contain_unqualified_nested_payload(tmp_path):
    path = tmp_path / "h.xlsx"
    parts = workbook(path)
    tree = ET.fromstring(parts["xl/_rels/workbook.xml.rels"])
    relation = next(node for node in tree if node.get("Type") == REL_TYPE)
    ET.SubElement(relation, "{urn:unqualified}payload")
    parts["xl/_rels/workbook.xml.rels"] = ET.tostring(tree)
    save_parts(path, parts)
    assert frozen(path)["status"] == "unknown"


@pytest.mark.parametrize("attribute,value", [("cm", "0"), ("cm", "2"), ("vm", "1")])
def test_cell_metadata_index_is_not_guessed(tmp_path, attribute, value):
    path = tmp_path / "h.xlsx"
    parts = workbook(path)
    tree = ET.fromstring(parts["xl/worksheets/sheet1.xml"])
    tree.find(f".//{{{MAIN}}}c").set(attribute, value)
    parts["xl/worksheets/sheet1.xml"] = ET.tostring(tree)
    save_parts(path, parts)
    assert frozen(path)["status"] == "unknown"


def test_multicell_dynamic_array_not_authorized_by_single_cached_anchor(tmp_path):
    path = tmp_path / "h.xlsx"
    workbook(path, formula_range="B1:B2")
    assert frozen(path)["status"] == "unknown"
