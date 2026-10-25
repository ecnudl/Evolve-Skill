"""Review fix 1: reserved-path boundary and official ZeroEval USER rendering.

Only synthetic puzzles/panels are used. Upstream prompt code is read as an AST
literal, never executed; expected rendering is an independent local translation
of the coordinator-supplied official apply_lgp_grid_template function.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.execskill_zpc_fakes import tmp_path

from skillopt.coevo5.calls import _request_hash
from skillopt.execskill import donors, replay, reuse, solver, zebralogic as z
from skillopt.execskill.package import Package, empty
from tests.execskill_fakes_env import FakeSandbox, Script, procedure
from tests.test_execskill_zpc_adapter import answer, row


@pytest.mark.parametrize("name", ["test.json", "test-panel.json", "zebralogic_test.json", "holdout.json",
    "FINAL-data.json", "prefixHeLd_OuTsuffix.json", "xverifier_calibrationx.json", "reserve-pool.json",
    "almost-sealed.json", "pool.json/test-parent/item.json"])
def test_reserved_names_fail_before_resolution_stat_or_content_read(tmp_path, monkeypatch, name):
    path = tmp_path / name
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("reserved path triggered metadata/content access")
    with monkeypatch.context() as patched:
        patched.setattr(Path, "read_bytes", forbidden)
        patched.setattr(Path, "stat", forbidden)
        patched.setattr(Path, "resolve", forbidden)
        patched.setattr(os, "stat", forbidden)
        patched.setattr(os, "lstat", forbidden)
        patched.setattr(os, "readlink", forbidden)
        with pytest.raises(ValueError, match="Refuse sealed or reserved"):
            z.load_pool(path)
    assert calls == []


@pytest.mark.parametrize("name", ["test.json", "test-panel.json", "zebralogic_test.json", "holdout.json",
    "xFINALx.json", "xheld_outx.json", "xverifier_calibrationx.json", "xreservex.json", "xSeAlEdx.json"])
def test_symlink_aliases_fail_before_stat_or_content_read(tmp_path, monkeypatch, name):
    target = tmp_path / name
    target.write_text("private-only sentinel")
    alias = tmp_path / "pool-alias.json"
    alias.symlink_to(target.name)
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("symlink alias reached stat/content read")
    with monkeypatch.context() as patched:
        patched.setattr(Path, "read_bytes", forbidden)
        patched.setattr(Path, "stat", forbidden)
        patched.setattr(Path, "resolve", forbidden)
        patched.setattr(os, "stat", forbidden)
        patched.setattr(os, "lstat", forbidden)
        with pytest.raises(ValueError, match="Refuse sealed or reserved"):
            z.load_pool(alias)
    assert calls == []


def test_directory_symlink_and_dotdot_cannot_hide_reserved_components(tmp_path, monkeypatch):
    reserved = tmp_path / "source-holdout"
    reserved.mkdir()
    (reserved / "subdir").mkdir()
    (reserved / "pool.json").write_text("private-only sentinel")
    alias = tmp_path / "directory-alias"
    alias.symlink_to(reserved / "subdir", target_is_directory=True)
    calls = []
    def forbidden(*args, **kwargs):
        calls.append(args)
        raise AssertionError("resolved reserved path opened")
    with monkeypatch.context() as patched:
        patched.setattr(Path, "read_bytes", forbidden)
        patched.setattr(Path, "stat", forbidden)
        patched.setattr(os, "lstat", forbidden)
        with pytest.raises(ValueError, match="Refuse sealed or reserved"):
            z.load_pool(alias / ".." / "pool.json")
    assert calls == []


def test_safe_symlink_resolution_uses_no_stat_and_preserves_dotdot_semantics(tmp_path, monkeypatch):
    original = tmp_path / "data"
    original.mkdir()
    nested = original / "nested"
    nested.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(nested)
    def forbidden(*args, **kwargs):
        raise AssertionError("guard must not stat or read content")
    with monkeypatch.context() as patched:
        patched.setattr(Path, "read_bytes", forbidden)
        patched.setattr(Path, "stat", forbidden)
        patched.setattr(os, "stat", forbidden)
        patched.setattr(os, "lstat", forbidden)
        assert z.guard_pool_path(alias / ".." / "pool.json") == original / "pool.json"


def official_render(source):
    """Independent direct translation of the supplied official rendering function."""
    file = Path(__file__).resolve().parent / "fixtures/execskill/zebralogic_upstream/ZEBRA_GRID.py.txt"
    raw = file.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "bbeed4d971d19dc04b84e888255598ab1d35c3de6701aad240d7d26abfd4bd08"
    template_text = ast.literal_eval(ast.parse(raw.decode()).body[0].value)
    prompt = template_text.replace("{puzzle}", source["puzzle"])
    template = {"reasoning": "___", "solution": {}}
    for i in range(len(source["solution"]["rows"])):
        template["solution"]["House %d" % (i + 1)] = {column: "___" for column in source["solution"]["header"][1:]}
    return prompt.replace("{json_template}", json.dumps(template, indent=4))


@pytest.mark.parametrize("size", z.DOMAIN)
def test_user_is_byte_exact_official_rendering_and_uses_only_public_house_count(size):
    source = row(size)
    source["solution"]["header"][1] = "Non-ASCII trait \u00e9"
    item = z.normalize(source)
    # Private data is deliberately unusable: inference has only these two fields.
    public = {**item["public"], "private": object(), "solution": object(), "rows": object()}
    expected = official_render(source)
    assert z.render_user(public).encode() == expected.encode()
    assert z.parse_user(expected) == item["public"]
    call = Script([answer(item)])
    found = solver.solve(z.BENCH, public, z.CARD_TEXT, empty(step="s0", evidence="engineering_fixture"), call)
    assert call.requests == [(solver.QA_SYSTEM, expected)]
    assert found["shell"]["calls"][0]["request_sha256"] == _request_hash(solver.QA_SYSTEM, expected)
    assert z.score(item["public"], item["private"], found)["status"] == "pass"


def test_official_template_provenance_and_neutral_card_are_pinned_by_value():
    from skillopt.validator_pilot.api import digest
    found = z.identity()
    template = found["user_template"]
    assert template["text"] == z.TEMPLATE_TEXT
    assert template["sha256"] == hashlib.sha256(z.TEMPLATE_TEXT.encode()).hexdigest()
    assert template["sha256"] == "dd4b8c12996ac0342e3ee2ad0e8737ab1e3043c4756a33721709ac92d60e570d"
    assert template["upstream_commit"] == "8c1485edf12c6efb5f69135a562927c5ad484059"
    assert template["license"] == "Apache-2.0" and template["notes_suffix"] == z.NOTES_SUFFIX
    assert template["upstream_url"].endswith("/src/templates/ZEBRA_GRID.py")
    assert found["card"]["text"] == "Follow the format in the user message."
    assert solver._system(z.BENCH, z.CARD_TEXT, {}) == solver.QA_SYSTEM
    changed = json.loads(json.dumps(found))
    changed["user_template"]["notes_suffix"] += "changed"
    assert digest(changed) != digest(found)


@pytest.mark.parametrize("notes", ["| Trait | Value |", "- Synthetic note.\n| table | row |"])
def test_notes_append_identically_and_hooks_replay_donors_never_get_example_puzzle(notes):
    item = z.normalize(row())
    proc = procedure("fx-zpc-official", ("applies", "before_call"), origin=z.BENCH)
    package = Package((proc,), "s1", "engineering_fixture")
    table = {proc.id: {"before_call": lambda view, state: {"table": [["Trait", "Value"]]}}}
    # The transport utility is shared by solver and identity calculation for all arms.
    rendered = z.render_user(item["public"], notes)
    assert rendered == official_render(row()) + z.NOTES_SUFFIX + notes
    assert z.parse_user(rendered) == {**item["public"], "procedure_notes": notes}
    call = {"purpose": "first", "user": rendered}
    trajectory = {"cell": "synthetic-cell", "task_id": "synthetic-item", "bench": z.BENCH,
                  "token": "fail", "calls": [call], "shell": {"precheck": None}}
    assert donors.donor_inputs(trajectory, bench=z.BENCH)["view"] == item["public"]
    assert replay.inputs_of(trajectory)["view"] == item["public"]
    worker = FakeSandbox(table).start(package, kind="cell")
    signature = reuse.signature(z.BENCH, package, item["public"], worker, card_text=z.CARD_TEXT)
    worker.close()
    script = Script([answer(item)])
    result = solver.solve(z.BENCH, item["public"], z.CARD_TEXT, package, script, worker=FakeSandbox(table))
    assert result["shell"]["calls"][0]["request_sha256"] == signature["request_sha256"]
    assert "Example Puzzle" in script.requests[0][1]
    assert "Example Puzzle" not in z.parse_user(script.requests[0][1])["question"]


def test_public_count_missing_or_ambiguous_is_refused_without_gold_fallback():
    for question in ("Solve these clues.", "There are 5 houses. There are 6 houses."):
        with pytest.raises(ValueError, match="public puzzle"):
            z.render_user({"question": question, "columns": ["Trait"],
                           "solution": {"rows": [["private"]] * 5}})
    source = row()
    source["puzzle"] = "There are 6 houses, numbered 1 to 6 from left to right, as seen from across the street."
    with pytest.raises(ValueError, match="public task size"):
        z.normalize(source)


def test_prompt_roundtrip_keeps_instruction_markers_inside_puzzle_and_notes():
    prefix, remainder = z.TEMPLATE_TEXT.split("{puzzle}")
    separator, suffix = remainder.split("{json_template}")
    question = ("There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street. "
                "A quoted marker follows:") + separator + "a non-template clue."
    view = {"question": question, "columns": ["Trait"]}
    notes = "A quoted marker in notes:" + separator + '{"reasoning": "___", "solution": {}}' + suffix
    rendered = z.render_user(view, notes)
    assert z.parse_user(rendered) == {**view, "procedure_notes": notes}
    # Notes can even quote a complete official grid template, followed by the appendix marker.
    template = {"reasoning": "___", "solution": {"House %d" % i: {"Trait": "___"} for i in range(1, 6)}}
    notes += separator + json.dumps(template, indent=4) + suffix + z.NOTES_SUFFIX + "more notes"
    assert z.parse_user(z.render_user(view, notes)) == {**view, "procedure_notes": notes}


@pytest.mark.parametrize("houses", [5, 6])
def test_house_count_uses_only_exact_opening_not_house_spacing_clues(houses):
    source = row("%d*2" % houses)
    source["puzzle"] += (
        "\n1. There are two houses between the baker and the cyclist."
        "\n2. There is one house between the tea drinker and the gardener."
        "\n3. There are 3 houses between the painter and the person with a dog."
    )
    normalized = z.normalize(source)
    assert z.public_house_count(normalized["public"]) == houses
    assert z.render_user(normalized["public"]) == official_render(source)
    assert z.parse_user(z.render_user(normalized["public"])) == normalized["public"]
    assert z.score(normalized["public"], normalized["private"],
                   {"status": "available", "output": answer(normalized)})["status"] == "pass"


@pytest.mark.parametrize("question", [
    "There are 5 houses, numbered 1 to 6 from left to right, as seen from across the street.",
    "There are 6 houses, numbered 1 to 5 from left to right, as seen from across the street.",
    "There are five houses, numbered 1 to five from left to right, as seen from across the street.",
    "There are 5 houses. There are two houses between the baker and cyclist.",
    "Clues first. There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street.",
    " There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street.",
    "there are 5 houses, numbered 1 to 5 from left to right, as seen from across the street.",
    "There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street!",
])
def test_house_count_refuses_nonregistered_opening_or_mismatched_numbers(question):
    with pytest.raises(ValueError, match="registered house-count sentence"):
        z.public_house_count({"question": question, "columns": ["Trait"]})
