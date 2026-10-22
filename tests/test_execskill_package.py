"""T-PKG-1..5: procedures and packages -- sealed records, caps, twins, router scopes, edits and restoration
(registration §2.1, §5.7, §6.1, §6.5, §9.2; plan §1 package.py, §2.1, §8.1)."""
from __future__ import annotations

import json

import pytest

from skillopt.execskill import package as pk
from skillopt.execskill import protocol
from skillopt.execskill.errors import PackageInvalid
from skillopt.execskill.package import (Package, Procedure, edits, empty, load, restore, save, validate, with_,
                                        with_describer, withhold)
from skillopt.validator_pilot.api import digest

PARAMETERS = {"applies": "view", "before_call": "view, state", "bindings": "view",
              "sheet_feedback": "view, run_report, state", "alf_before_step": "view, state",
              "alf_after_step": "event, state"}
NOT_SB = ("searchqa", "officeqa", "livemath", "alfworld")
DESCRIBED = {"prompt_sha256": "b" * 64, "text_sha256": "a" * 64}


def source(hooks, marker="one", extra=""):
    """A policy-clean module defining ``hooks`` with their registered parameters."""
    text = '"""A fixture procedure."""\nMARKER = %r\n%s' % (marker, extra)
    for hook in hooks:
        text += "\n\ndef %s(%s):\n    return %s\n" % (hook, PARAMETERS.get(hook, "view"),
                                                    "True" if hook == "applies" else "{}")
    return text


def proc(pid, marker="one", *, hooks=("applies", "before_call"), extra="", **fields):
    """A valid procedure unless ``fields`` say otherwise; ``p-`` ids are smoke records, ``fx-`` ids fixtures."""
    learned = pid.startswith("p-")
    fields.setdefault("origin", pid.split("-")[1] if learned else "officeqa")
    fields.setdefault("evidence", "smoke" if learned else "engineering_fixture")
    fields.setdefault("description", "Lists the numbers of the question (%s)." % marker)
    fields.setdefault("source", source(hooks, marker, extra))
    fields.setdefault("max_note_chars", 500 if set(hooks) & set(pk.NOTE_HOOKS) else 0)
    fields.setdefault("state_bytes", 1024 if "alf_after_step" in hooks else 0)
    return Procedure(id=pid, hooks=hooks, **fields)


P1, P2, P3 = proc("p-officeqa-1-1"), proc("p-officeqa-1-2", "two"), proc("p-searchqa-1-1", "three")
P2V2 = proc("p-officeqa-2-1", "two, revised",
            lineage={"parent": P2.sha256, "revises": "p-officeqa-1-2", "engineer_call": None})
P4 = proc("p-livemath-2-1", "four")
ROOT = empty(step="s0", evidence="smoke")


def base():
    return with_(ROOT, step="s1", add=[P1, P2, P3])


# ---------------------------------------------------------------------------- T-PKG-1 sealed, canonical, write-once
def test_records_are_sealed_and_stable():
    record = P1.to_json()
    assert record["version"] == "fivebench-execskill-v1-procedure" and record["evidence"] == "smoke"
    assert record["record_sha256"] == digest({k: v for k, v in record.items() if k != "record_sha256"})
    assert P1.sha256 == record["record_sha256"] == proc("p-officeqa-1-1").sha256 != proc("p-officeqa-1-1", "x").sha256
    assert Procedure.from_json(json.loads(json.dumps(record))) == P1 and not P1.is_fixture
    package = base()
    value = package.to_json()
    assert value["version"] == "fivebench-execskill-v1-package" and value["evidence"] == "smoke"
    assert value["procedures"] == [P1.sha256, P2.sha256, P3.sha256] and value["order"] == list(package.order)
    assert value["parent_sha256"] == ROOT.sha256 and base().sha256 == package.sha256
    assert Package((P2, P1, P3), "s1", "smoke", ROOT.sha256).sha256 != package.sha256  # the order is content


def test_records_of_another_kind_or_protocol_are_refused():
    with pytest.raises(PackageInvalid):
        Procedure.from_json(base().to_json())
    other = {k: v for k, v in P1.to_json().items() if k != "record_sha256"}
    other["version"] = "fivebench-coevo-v3-procedure"
    with pytest.raises(PackageInvalid):
        Procedure.from_json({**other, "record_sha256": digest(other)})
    broken = P1.to_json()
    broken["description"] = "Changed."
    with pytest.raises(PackageInvalid):
        Procedure.from_json(broken)


def test_save_and_load_round_trip_write_once(tmp_path):
    package = base()
    sha = save(tmp_path, package)
    assert sha == package.sha256 and save(tmp_path, package) == sha  # the same bytes again: a no-op
    assert sorted(p.name for p in (tmp_path / "procedures").iterdir()) == sorted(
        p.sha256 + ".json" for p in package.procedures)
    path = tmp_path / "packages" / (sha + ".json")
    assert load(path) == package
    value = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**value, "step": "s9"}), encoding="utf-8")
    with pytest.raises(ValueError):  # write-once: a different artifact under the same name
        save(tmp_path, package)


@pytest.mark.parametrize("damage", ["package", "procedure", "name"])
def test_tampered_or_misnamed_files_are_refused(tmp_path, damage):
    sha = save(tmp_path, base())
    path = tmp_path / "packages" / (sha + ".json")
    if damage == "name":
        path = path.rename(path.with_name("0" * 64 + ".json"))
    else:
        target = path if damage == "package" else tmp_path / "procedures" / (P2.sha256 + ".json")
        value = json.loads(target.read_text(encoding="utf-8"))
        value["step" if damage == "package" else "description"] = "changed"
        target.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(PackageInvalid):
        load(path)


# ------------------------------------------------------------------------------------------------- T-PKG-2 caps
@pytest.mark.parametrize("build", [
    lambda: proc("p-nowhere-1-1"),
    lambda: proc("q-officeqa-1-1"),
    lambda: proc("p-officeqa-1-1", origin="searchqa"),
    lambda: proc("fx-numbers", evidence="smoke"),
    lambda: proc("p-officeqa-1-1", evidence="real_run"),
    lambda: proc("p-officeqa-1-1", description=""),
    lambda: proc("p-officeqa-1-1", description="d" * 601),
    lambda: proc("p-officeqa-1-1", hooks=("applies",)),
    lambda: proc("p-officeqa-1-1", hooks=("before_call", "applies")),
    lambda: proc("p-officeqa-1-1", hooks=("before_call", "sheet_feedback")),
    lambda: proc("p-officeqa-1-1", hooks=("applies", "after_call")),
    lambda: proc("p-officeqa-1-1", extra="import os\n"),
    lambda: proc("p-officeqa-1-1", extra="X = %r\n" % ("a" * 2001)),
    lambda: proc("p-officeqa-1-1", extra="# %s\n" % ("x" * 6000)),
    lambda: proc("p-officeqa-1-1", source=source(("applies",))),
    lambda: proc("p-officeqa-1-1", source=source(("applies",)) + "\n\ndef before_call(view):\n    return {}\n"),
    lambda: proc("p-officeqa-1-1", source=source(("applies", "before_call", "bindings"))),
    lambda: proc("p-officeqa-1-1", excluded_benches=protocol.BENCHES),
    lambda: proc("p-officeqa-1-1", excluded_benches=("alfworld", "searchqa")),
    lambda: proc("p-officeqa-1-1", excluded_benches=("nowhere",)),
    lambda: proc("p-officeqa-1-1", header="Return the total."),
    lambda: proc("p-officeqa-1-1", header="h" * 201),
    lambda: proc("p-officeqa-1-1", max_note_chars=0),
    lambda: proc("p-officeqa-1-1", max_note_chars=4001),
    lambda: proc("p-alfworld-1-1", hooks=("applies", "alf_after_step"), max_note_chars=100),
    lambda: proc("p-alfworld-1-1", hooks=("applies", "alf_after_step"), state_bytes=0),
    lambda: proc("p-alfworld-1-1", hooks=("applies", "alf_after_step"), state_bytes=pk.MAX_STATE_BYTES + 1),
    lambda: proc("p-officeqa-1-1", requests_second_call=True),
    lambda: proc("p-officeqa-1-1", replay_tests=[{"id": "t1", "hook": "before_call"}] * 2),
    lambda: proc("p-officeqa-1-1", replay_tests=[{"id": "t1", "hook": "bindings"}]),
    lambda: proc("p-officeqa-1-1", lineage={"parent": None, "revises": "p-officeqa-1-0", "engineer_call": None}),
    lambda: proc("p-officeqa-1-1", lineage={"parent": "0" * 64, "revises": "p-officeqa-1-1", "engineer_call": None}),
    lambda: proc("p-officeqa-1-1", lineage={"parent": None, "revises": None}),
    lambda: proc("p-officeqa-1-1", accepted_at="step one"),
])
def test_invalid_procedures_are_refused(build):
    with pytest.raises(PackageInvalid):
        build()


def test_valid_edge_cases():
    header = "A helper program checked the cell format."
    assert proc("p-spreadsheetbench-1-1", header=header, excluded_benches=NOT_SB).header == header
    with pytest.raises(PackageInvalid):  # the same header could fire on OfficeQA
        proc("p-spreadsheetbench-1-1", header=header, excluded_benches=("searchqa", "livemath", "alfworld"))
    assert proc("p-officeqa-1-1", hooks=("applies", "bindings"), requests_second_call=True).requests_second_call
    alf = proc("p-alfworld-1-1", hooks=("applies", "alf_before_step", "alf_after_step"))
    assert (alf.max_note_chars, alf.state_bytes) == (500, 1024)
    fixture = proc("fx-numbers")
    assert fixture.is_fixture and fixture.evidence == "engineering_fixture"
    tested = proc("p-officeqa-1-1", replay_tests=[{"id": "t1", "hook": "before_call", "view": {"question": "1+2"}}])
    assert tested.to_json()["replay_tests"] == [{"id": "t1", "hook": "before_call", "view": {"question": "1+2"}}]


def test_package_caps():
    assert (protocol.MAX_PROCEDURES, protocol.MAX_PACKAGE_BYTES) == (24, 64_000)
    many = [proc("p-officeqa-1-%d" % i, "m%d" % i) for i in range(25)]
    assert len(Package(tuple(many[:24]), "s1", "smoke").order) == 24
    with pytest.raises(PackageInvalid):
        Package(tuple(many), "s1", "smoke")
    padding = "".join("%s = %r\n" % (name, "a" * 1900) for name in "ABC")
    big = [proc("p-officeqa-1-%d" % i, "m%d" % i, extra=padding) for i in range(11)]
    assert sum(len(p.source.encode()) for p in big[:10]) <= 64_000 < sum(len(p.source.encode()) for p in big)
    assert len(Package(tuple(big[:10]), "s1", "smoke").order) == 10
    with pytest.raises(PackageInvalid):
        Package(tuple(big), "s1", "smoke")


@pytest.mark.parametrize("build", [
    lambda: Package((P1, P1), "s1", "smoke"),
    lambda: Package(("not a procedure",), "s1", "smoke"),
    lambda: Package((proc("fx-numbers"),), "s1", "smoke"),
    lambda: Package((P1,), "", "smoke"),
    lambda: Package((P1,), "step one", "smoke"),
    lambda: Package((P1,), "s1", "real_run"),
    lambda: Package((P1,), "s1", "smoke", "parent"),
    lambda: Package((P1,), "s1", "smoke", retired=(P1.sha256,)),
    lambda: Package((P1,), "s1", "smoke", retired=("x",)),
    lambda: Package((P1,), "s1", "smoke", narrowed={P1.id: list(protocol.BENCHES)}),
    lambda: Package((P1,), "s1", "smoke", narrowed={P2.id: ["alfworld"]}),
    lambda: Package((P1,), "s1", "smoke", narrowed={P1.id: ["nowhere"]}),
    lambda: Package((P1,), "s1", "smoke", narrowed={P1.id: []}),
    lambda: Package((P1,), "s1", "smoke", describer={P1.id: {"text_sha256": "a" * 64}}),
    lambda: Package((P1,), "s1", "smoke", describer={P2.id: DESCRIBED}),
])
def test_invalid_packages_are_refused(build):
    with pytest.raises(PackageInvalid):
        build()


def test_fixture_procedures_only_in_fixture_packages():
    fixture = proc("fx-numbers")
    with pytest.raises(PackageInvalid):
        with_(ROOT, step="s1", add=[fixture])
    assert with_(empty(step="s0", evidence="engineering_fixture"), step="s1", add=[fixture]).order == ("fx-numbers",)


def test_at_most_three_edits_per_step():
    assert protocol.MAX_CHANGES == pk.MAX_CHANGES == 3
    with pytest.raises(PackageInvalid):
        with_(ROOT, step="s1", add=[P1, P2, P3, P4])
    four = Package((P1, P2, P3, P4), "s1", "smoke", ROOT.sha256)
    validate(four)  # the invariants alone hold
    with pytest.raises(PackageInvalid):
        validate(four, ROOT)
    package = base()
    validate(package, ROOT)
    with pytest.raises(PackageInvalid):
        validate(package, package)  # the parent link
    with pytest.raises(PackageInvalid):
        validate("package")


def test_with_refuses_inconsistent_edits():
    package = base()
    wrong_parent = proc("p-officeqa-2-1", lineage={"parent": "0" * 64, "revises": "p-officeqa-1-2",
                                                   "engineer_call": None})
    for kwargs in ({"remove": ["p-officeqa-9-9"]},
                   {"remove": ["p-searchqa-1-1"], "narrow": {"p-searchqa-1-1": ["alfworld"]}},
                   {"add": [P2V2]},  # a new procedure revises nothing
                   {"revise": [wrong_parent]},
                   {"add": [P1]}):  # the id is in use
        with pytest.raises(PackageInvalid):
            with_(package, step="s2", **kwargs)


# --------------------------------------------------------------------------------- T-PKG-3 twins are new records
def test_with_and_withhold_produce_new_hashes():
    package = base()
    twin = withhold(package, ["p-officeqa-1-2"])
    assert twin.order == ("p-officeqa-1-1", "p-searchqa-1-1") and twin == withhold(package, ["p-officeqa-1-2"])
    assert (twin.step, twin.parent_sha256, twin.retired) == (package.step, package.parent_sha256, package.retired)
    child = with_(package, step="s2", remove=["p-searchqa-1-1"])
    assert child.parent_sha256 == package.sha256 and child.retired == (P3.sha256,)
    assert len({ROOT.sha256, package.sha256, twin.sha256, child.sha256}) == 4
    frozen = with_describer(child, {"p-officeqa-1-1": DESCRIBED})
    assert frozen.procedures == child.procedures and frozen.sha256 != child.sha256
    assert withhold(frozen, ["p-officeqa-1-1"]).describer == {}
    for ids in ([], ["p-officeqa-9-9"]):
        with pytest.raises(PackageInvalid):
            withhold(package, ids)
    with pytest.raises(PackageInvalid):
        with_describer(child, {"p-searchqa-1-1": DESCRIBED})


# ----------------------------------------------------------------------------- T-PKG-4 the router's bench scope
def test_router_respects_exclusions_and_narrowings():
    p1 = proc("p-officeqa-1-1", excluded_benches=("alfworld",))
    package = with_(ROOT, step="s1", add=[p1, P2, P3])
    narrowed = with_(package, step="s2", narrow={"p-officeqa-1-2": ["alfworld", "livemath"]})
    assert [p.id for p in narrowed.for_bench("officeqa")] == ["p-officeqa-1-1", "p-officeqa-1-2", "p-searchqa-1-1"]
    assert [p.id for p in narrowed.for_bench("livemath")] == ["p-officeqa-1-1", "p-searchqa-1-1"]
    assert [p.id for p in narrowed.for_bench("alfworld")] == ["p-searchqa-1-1"]
    assert narrowed.excluded("p-officeqa-1-2") == ("livemath", "alfworld")
    assert narrowed.excluded("p-officeqa-1-1") == ("alfworld",) and narrowed.get("p-officeqa-1-2") == P2
    with pytest.raises(ValueError):
        narrowed.for_bench("nowhere")
    for narrow in ({"p-officeqa-1-2": list(protocol.BENCHES)}, {"p-officeqa-1-1": ["alfworld"]}):
        with pytest.raises(PackageInvalid):  # no bench left, or a bench already excluded
            with_(package, step="s2", narrow=narrow)
    widened = Package(narrowed.procedures, "s3", "smoke", narrowed.sha256)
    with pytest.raises(PackageInvalid):  # widening a scope is not an edit type
        validate(widened, narrowed)


# ---------------------------------------------------------------------------------- T-PKG-5 edits and restoration
def test_edits_classify_new_revision_deletion_and_narrowing():
    package = base()
    candidate = with_(package, step="s2", add=[P4], revise=[P2V2], remove=["p-searchqa-1-1"])
    changes = edits(package, candidate)
    assert [(e.kind, e.id) for e in changes] == [("revision", "p-officeqa-2-1"), ("new", "p-livemath-2-1"),
                                                 ("deletion", "p-searchqa-1-1")]
    assert changes[0].to_json() == {"kind": "revision", "id": "p-officeqa-2-1", "old": P2.sha256,
                                    "new": P2V2.sha256, "benches": []}
    assert candidate.order == ("p-officeqa-1-1", "p-officeqa-2-1", "p-livemath-2-1")  # in place; new ones appended
    assert candidate.retired == tuple(sorted((P2.sha256, P3.sha256)))
    narrowing = with_(package, step="s2", narrow={"p-officeqa-1-1": ["alfworld"]})
    assert [e.to_json() for e in edits(package, narrowing)] == [
        {"kind": "narrowing", "id": "p-officeqa-1-1", "old": P1.sha256, "new": P1.sha256, "benches": ["alfworld"]}]
    assert edits(package, package) == []
    with pytest.raises(PackageInvalid):  # a fourth edit
        with_(package, step="s2", add=[P4], revise=[P2V2], remove=["p-searchqa-1-1"],
              narrow={"p-officeqa-1-1": ["alfworld"]})
    with pytest.raises(PackageInvalid):  # one id, two contents
        edits(package, Package((proc("p-officeqa-1-1", "changed"), P2, P3), "s2", "smoke", package.sha256))
    kept_old = Package((P1, P2, P3, P2V2), "s2", "smoke", package.sha256)
    assert [e.kind for e in edits(package, kept_old)] == ["new"]  # a revision keeping its old version is new


def test_restore_puts_a_deleted_procedure_back_in_its_parent_position():
    package = base()
    candidate = with_(package, step="s2", add=[P4], revise=[P2V2], remove=["p-searchqa-1-1"])
    twin = restore(candidate, package, ["p-searchqa-1-1"])
    # after p-officeqa-1-2's revision, which stands in its place; the new procedure stays last
    assert twin.order == ("p-officeqa-1-1", "p-officeqa-2-1", "p-searchqa-1-1", "p-livemath-2-1")
    assert (twin.step, twin.parent_sha256, twin.retired) == ("s2", package.sha256, (P2.sha256,))
    assert twin.sha256 not in (package.sha256, candidate.sha256)
    assert restore(candidate, package, ["p-searchqa-1-1"]).sha256 == twin.sha256
    assert [e.kind for e in edits(package, twin)] == ["revision", "new"]
    first = with_(package, step="s2", remove=["p-officeqa-1-1"])
    assert restore(first, package, ["p-officeqa-1-1"]).order == package.order
    for ids in ([], ["p-officeqa-1-2"], ["p-officeqa-1-1"]):  # nothing; revised; unchanged
        with pytest.raises(PackageInvalid):
            restore(candidate, package, ids)


def test_restore_gives_back_the_parents_scope_and_describer():
    package = with_describer(base(), {"p-searchqa-1-1": DESCRIBED})
    narrowed = with_(package, step="s2", narrow={"p-officeqa-1-1": ["alfworld"]})
    back = restore(narrowed, package, ["p-officeqa-1-1"])
    assert back.narrowed == {} and back.for_bench("alfworld") == package.procedures and edits(package, back) == []
    more = with_(narrowed, step="s3", narrow={"p-officeqa-1-1": ["livemath"]})
    assert more.narrowed == {"p-officeqa-1-1": ("livemath", "alfworld")}
    assert restore(more, narrowed, ["p-officeqa-1-1"]).narrowed == {"p-officeqa-1-1": ("alfworld",)}
    deleted = with_(package, step="s2", remove=["p-searchqa-1-1"])
    assert deleted.describer == {} and restore(deleted, package, ["p-searchqa-1-1"]).describer == package.describer
