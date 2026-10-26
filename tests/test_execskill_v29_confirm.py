"""Offline authored confirmation slices, rules, reuse and disclosure boundaries."""
from collections import Counter
from copy import deepcopy
from types import SimpleNamespace

import pytest

from skillopt.execskill import confirm, profiles as p, step, supply, zebralogic as z
from tests.test_execskill_zpc_adapter import pool_rows


def zebra_pool():
    return [z.normalize(row, partition="pool") for row in pool_rows()]


def alf_pool():
    return [{"benchmark": "alfworld", "task_id": "room-%03d-game-%d" % (room, game),
             "room": "room-%03d" % room, "public": {}, "private": {}}
            for room in range(108) for game in range(7)]


def cell(arm, key, passed, violation=False):
    return {"cell": {"arm": arm, "task_id": key, "id": arm + "/" + key},
            "judge": {"v2": {"token": "pass" if passed else "fail"},
                      "format": {"violation": violation}}, "final": {"outcome": "pass" if passed else "fail",
                      "kind": "scored"}, "faults": [], "sends": [], "stop": None}


def test_zebra_confirm_exact_registered_union_and_domain():
    pool = zebra_pool()
    selected, pin = confirm.slice_items("zebra-pc-v7", pool)
    split = z.slices(pool)
    expected = {row["task_id"] for name in ("spare", "smoke") for row in split[name]} | set(z.EXCLUDED_IDS)
    assert set(pin["ids"]) == expected and len(selected) == 40
    assert {key: len(ids) for key, ids in pin["provenance"]["parts"].items()} == {
        "spare": 3, "excluded_probe": 27, "smoke": 10}
    assert not expected & {row["task_id"] for name in ("run", "accept") for row in split[name]}
    assert {row["task"] for row in selected} <= set(z.DOMAIN)
    assert pin == confirm.identity("zebra-pc-v7", list(reversed(pool)))
    assert pin["freshness"] == "zebra_split_v1_confirm_spare_probe_smoke_first_use"


def test_alf_confirm_40_spare_whole_capped_rooms_seeded_order():
    pool = alf_pool()
    selected, pin = confirm.slice_items("alfworld-v4", pool)
    rooms = supply.room_groups(supply.room_order(pool))
    counts = Counter(row["room"] for row in selected)
    assert len(selected) == 40 and set(counts.values()) == {p.MAX_GAMES_PER_ROOM}
    assert list(counts) == rooms["spare"][:8]
    assert not set(counts) & {room for name in ("run", "accept", "select", "smoke") for room in rooms[name]}
    assert pin == confirm.identity("alfworld-v4", list(reversed(pool)))
    assert pin["provenance"]["room_order"] == list(counts)


@pytest.mark.parametrize("configuration,builder", [("zebra-pc-v7", zebra_pool), ("alfworld-v4", alf_pool)])
def test_confirm_excludes_test_and_protected_ids(configuration, builder):
    pool = builder()
    _, pin = confirm.slice_items(configuration, pool)
    with pytest.raises(ValueError, match="overlaps"):
        confirm.slice_items(configuration, pool, excluded=pin["ids"][:1])
    with pytest.raises(ValueError, match="practice"):
        confirm.slice_items(configuration, [{**row, "partition": "test"} for row in pool])


@pytest.mark.parametrize("fixed,broken,bad_format,expected", [(1, 0, 0, True), (2, 1, 0, True),
    (1, 1, 0, False), (0, 1, 0, False), (1, 0, 3, False), (1, 0, 2, True), (0, 0, 0, False)])
def test_confirmation_gain_and_exact_format_margin(fixed, broken, bad_format, expected):
    cells, ids = {}, [str(i) for i in range(40)]
    for i, key in enumerate(ids):
        cells[("S'", key)] = [cell("S'", key, i < fixed, i < bad_format)]
        cells[("S", key)] = [cell("S", key, fixed <= i < fixed + broken)]
    result = confirm.verdict(cells, ids)
    assert (result["fixed"], result["broken"], result["net"]) == (fixed, broken, fixed - broken)
    assert result["passed"] is expected and result["format_margin"] == 2


def test_no_different_routes_and_identical_requests_never_confirm():
    assert confirm.verdict({}, [])["reason"] == "no_item_routes_differently"
    value = confirm.verdict({}, ["a", "b"], identical=["a", "b"])
    assert not value["passed"] and value["fixed"] == value["broken"] == 0
    assert value["candidate_cells"] == 2


def test_count_boundary_removes_ids_notes_replies_and_gold():
    value = {"items": 40, "fixed": 2, "broken": 1, "passed": True,
             "slice_ids": ["CONFIRM-ID"], "notes": "CONFIRM-NOTE", "reply": "SOLVER-SECRET", "gold": "GOLD"}
    assert confirm.counts_only(value) == {"items": 40, "fixed": 2, "broken": 1, "passed": True}


class FakeStep:
    def __init__(self, tmp_path):
        self.bench = "zebralogic"
        self.setting = SimpleNamespace(extra={"configuration": "zebra-pc-v7"}, cards={})
        self.finished, self.tmp_path, self.solver_kinds = {}, tmp_path, []
        self.signature_version = "original"
        self.runtime_value = {}
    def runtime(self):
        return self.runtime_value
    def label(self, name):
        return "D/s1-zebralogic/" + name
    def done(self, name):
        return self.finished.get(name)
    def unit(self, name, work):
        if name not in self.finished:
            attempt = self.tmp_path / name
            attempt.mkdir()
            self.finished[name] = work(attempt)
        return self.finished[name]
    def solver(self, kind, attempt):
        self.solver_kinds.append(kind)
        return object()


def fixture_confirm(n=40):
    return {"confirm": [{"task_id": str(i), "public": {"question": "confirm public " + str(i), "columns": []},
                         "private": {"answer": "hidden"}} for i in range(n)]}


def fake_eval(monkeypatch, tmp_path, *, identical=False):
    st, calls = FakeStep(tmp_path), []
    monkeypatch.setattr(step, "Arm", lambda kind, package: SimpleNamespace(kind=kind, package=package))
    monkeypatch.setattr(step.solver, "routing_view", lambda bench, public, **kw: public)
    monkeypatch.setattr(step, "_routes", lambda st, package, views, publics: {
        key: SimpleNamespace(enabled=() if package.sha256 == "parent" else (package.sha256,), faults=[],
                             to_json=lambda: {"per_procedure": {"p": {"applies": "default_true"}}})
        for key, _ in views})
    def signatures(st, candidate, parent, publics, views, **kw):
        return {key: {arm: {"request_sha256": st.signature_version + ":" + package.sha256 + ":" + key,
                            "post_call": [], "faults": [], "enabled": [package.sha256]}
                      for arm, package in (("S", parent), ("S'", candidate))} for key, _ in views}
    monkeypatch.setattr(step, "_pair_signatures", signatures)
    def run(st, attempt, endpoint, unit, jobs, **kw):
        calls.append([(arm, key) for arm, _, key, _, _ in jobs])
        return [cell(arm, key, arm == "S'") for arm, _, key, _, _ in jobs]
    monkeypatch.setattr(step, "_cells", run)
    return st, calls


def test_incumbent_confirm_cells_reused_across_rounds_and_resume(monkeypatch, tmp_path):
    st, calls = fake_eval(monkeypatch, tmp_path)
    parent = SimpleNamespace(sha256="parent")
    one = step._confirm_eval(st, fixture_confirm(), 1, parent, SimpleNamespace(sha256="one"))
    two = step._confirm_eval(st, fixture_confirm(), 2, parent, SimpleNamespace(sha256="two"))
    again = step._confirm_eval(st, fixture_confirm(), 2, parent, SimpleNamespace(sha256="two"))
    assert one["confirm"]["passed"] and two == again
    assert list(map(len, calls)) == [80, 40]
    assert two["confirm"]["reused_cells"] == 40 and two["confirm"]["evaluated"] == 40
    assert all(log["S'"]["per_procedure"]["p"]["applies"] == "default_true" for log in two["routing"].values())
    assert all(arm == "S'" for arm, _ in calls[1]) and st.solver_kinds == ["confirm", "confirm"]


def test_incumbent_hash_change_invalidates_cache(monkeypatch, tmp_path):
    st, calls = fake_eval(monkeypatch, tmp_path)
    step._confirm_eval(st, fixture_confirm(), 1, SimpleNamespace(sha256="parent"), SimpleNamespace(sha256="one"))
    step._confirm_eval(st, fixture_confirm(), 2, SimpleNamespace(sha256="unseen"), SimpleNamespace(sha256="two"))
    assert list(map(len, calls)) == [80, 80]


def test_changed_request_signature_reruns_all_40_incumbent_confirm_cells(monkeypatch, tmp_path):
    """The reviewer's unchanged-package / changed-signature reproduction."""
    st, calls = fake_eval(monkeypatch, tmp_path)
    parent = SimpleNamespace(sha256="parent")
    step._confirm_eval(st, fixture_confirm(), 1, parent, SimpleNamespace(sha256="one"))
    st.signature_version = "changed-request"
    result = step._confirm_eval(st, fixture_confirm(), 2, parent, SimpleNamespace(sha256="two"))
    assert len(calls[1]) == 80 and sum(arm == "S" for arm, _ in calls[1]) == 40
    assert result["confirm"]["reused_cells"] == 0


@pytest.mark.parametrize("invalid", ["faults", "stopped", "missing_stop", "missing_final", "empty_final", "fault_token"])
def test_faulted_or_incomplete_saved_incumbent_confirm_cell_reruns(monkeypatch, tmp_path, invalid):
    st, calls = fake_eval(monkeypatch, tmp_path)
    parent = SimpleNamespace(sha256="parent")
    first = step._confirm_eval(st, fixture_confirm(), 1, parent, SimpleNamespace(sha256="one"))
    key = next(iter(first["incumbent_cells"]))
    saved = first["incumbent_cells"][key]
    if invalid == "faults":
        saved["faults"] = [{"kind": "crash", "procedure": "fx-faulted"}]
    elif invalid == "stopped":
        saved["stop"] = {"kind": "exception"}
    elif invalid == "missing_stop":
        saved.pop("stop")
    elif invalid == "missing_final":
        saved["final"] = None
    elif invalid == "empty_final":
        saved["final"] = {}
    else:
        saved["judge"]["v2"]["token"] = "unknown_fault"
    result = step._confirm_eval(st, fixture_confirm(), 2, parent, SimpleNamespace(sha256="two"))
    assert len(calls[1]) == 41 and ("S", key) in calls[1]
    assert result["confirm"]["reused_cells"] == 39


@pytest.mark.parametrize("current_missing", [False, True])
def test_missing_confirmation_request_identity_never_matches(monkeypatch, tmp_path, current_missing):
    st, calls = fake_eval(monkeypatch, tmp_path)
    parent = SimpleNamespace(sha256="parent")
    first = step._confirm_eval(st, fixture_confirm(), 1, parent, SimpleNamespace(sha256="one"))
    if current_missing:
        monkeypatch.setattr(step, "_pair_signatures", lambda *a, **kw: {})
    else:
        first.pop("request_identities")
        first.pop("request_signatures")
    result = step._confirm_eval(st, fixture_confirm(), 2, parent, SimpleNamespace(sha256="two"))
    assert len(calls[1]) == 80 and result["confirm"]["reused_cells"] == 0


def test_promoted_candidate_confirm_cells_match_current_incumbent_identity(monkeypatch, tmp_path):
    st, calls = fake_eval(monkeypatch, tmp_path)
    promoted = SimpleNamespace(sha256="one")
    step._confirm_eval(st, fixture_confirm(), 1, SimpleNamespace(sha256="parent"), promoted)
    result = step._confirm_eval(st, fixture_confirm(), 2, promoted, SimpleNamespace(sha256="two"))
    assert len(calls[1]) == 40 and result["confirm"]["reused_cells"] == 40


@pytest.mark.parametrize("passed", [False, True])
def test_complete_production_verdict_shape_is_reusable(passed):
    from dataclasses import asdict
    from skillopt.coevo5.outcomes import SCORED, Verdict
    verdict = Verdict("pass" if passed else "fail", SCORED, "official_score", "10")
    stored = cell("S", "item", passed)
    stored["final"] = {**asdict(verdict), "token": verdict.token}
    assert step._confirm_cell_reusable(stored, "item")


@pytest.mark.parametrize("changed", [None, "game", "view", "runtime", "card"])
def test_alf_confirm_episode_identity_pins_package_game_view_runtime_and_card(monkeypatch, tmp_path, changed):
    st, calls = fake_eval(monkeypatch, tmp_path)
    st.bench, st.setting.extra = "alfworld", {"configuration": "alfworld-v4"}
    st.setting.cards = {"alfworld": "Frozen card."}
    monkeypatch.setattr(step, "_pair_signatures", lambda *a, **kw: {})
    cut = fixture_confirm()
    for item in cut["confirm"]:
        view = {"observation": "A public room.", "admissible_commands": ["look"]}
        item["public"] = {"routing_view": view, "routing_view_sha256": step.digest(view)}
        item["views_runtime_sha256"] = step.digest(st.runtime())
    parent = SimpleNamespace(sha256="parent")
    first = step._confirm_eval(st, cut, 1, parent, SimpleNamespace(sha256="one"))
    identity = next(iter(first["request_identities"].values()))["S"]
    assert identity["package_sha256"] == "parent"
    assert set(identity) == {"version", "package_sha256", "game_id", "view_sha256", "runtime_sha256", "card_sha256"}
    cut = deepcopy(cut)
    if changed == "runtime":
        st.runtime_value = {"runtime": "changed"}
        for item in cut["confirm"]:
            item["views_runtime_sha256"] = step.digest(st.runtime())
    elif changed == "card":
        st.setting.cards["alfworld"] = "A changed card."
    elif changed in ("game", "view"):
        for item in cut["confirm"]:
            if changed == "game":
                item["task_id"] += "-changed"
            else:
                item["public"]["routing_view"]["observation"] = "A different public room."
                item["public"]["routing_view_sha256"] = step.digest(item["public"]["routing_view"])
    result = step._confirm_eval(st, cut, 2, parent, SimpleNamespace(sha256="two"))
    assert len(calls[1]) == (40 if changed is None else 80)
    assert result["confirm"]["reused_cells"] == (40 if changed is None else 0)


@pytest.mark.parametrize("reason", ["audit_confirmed", "audit_fix_failed_checks"])
def test_audit_dropped_proposal_never_inherits_surviving_siblings_adopted_fate(reason):
    changes = [{"n": 0, "id": "fx-dropped", "kind": "new", "target": None, "summary": "Dropped description.",
                "survived": False, "attempts": [{"failed": "C2" if reason == "audit_fix_failed_checks" else None}],
                "reason": reason},
               {"n": 1, "id": "fx-surviving", "kind": "new", "target": None, "summary": "Surviving description.",
                "survived": True, "attempts": [{"failed": None}]}]
    engineered = {"candidate_sha256": "surviving-package", "engineer": {"changes": changes, "dropped": []}}
    evaluated = {"verdict": {"adopted": True, "items": 40, "generated": 0, "fixed": ["item"], "broken": [],
                              "net": "1/1", "p_sign": 0.5, "reason": None}}
    line = step._line(1, engineered, evaluated)
    assert line["adopted"]
    assert [proposal["fate"] for proposal in line["proposals"]] == [reason, "adopted"]


def test_confirm_smoke_exercise_exactly_two_items(monkeypatch, tmp_path):
    st, calls = fake_eval(monkeypatch, tmp_path)
    result = step._confirm_eval(st, fixture_confirm(2), 1, SimpleNamespace(sha256="parent"),
                                SimpleNamespace(sha256="one"), exercise=True)
    assert result["confirm"]["exercise"] and result["confirm"]["items"] == 2 and len(calls[0]) == 4


def test_final_adoption_and_feedback_use_counts_only():
    evaluated = {"adopted": True, "verdict": {"reason": None}, "feedback": {"run": "run-only"}}
    result = step._confirmed_training(evaluated, {"confirm": {
        "items": 40, "fixed": 0, "broken": 1, "passed": False, "reason": "gain:fixed_over_broken",
        "slice_ids": ["DO-NOT-DISCLOSE"], "notes": "DO-NOT-DISCLOSE"}})
    assert not result["adopted"] and result["verdict"]["reason"] == "confirm:gain:fixed_over_broken"
    assert "DO-NOT-DISCLOSE" not in repr(result)
    assert evaluated["adopted"]  # The sealed training verdict remains unchanged.


def test_engineer_confirmation_validator_rejects_content_and_ids():
    from skillopt.execskill.engineer_v29 import confirm_feedback_ok
    safe = {"items": 40, "fixed": 2, "broken": 1, "passed": True,
            "format_cells": {"S": 0, "S'": 0}, "net": 1}
    assert confirm_feedback_ok(safe)
    for key in ("slice_ids", "question", "notes", "reply", "gold", "cell", "task_id"):
        assert not confirm_feedback_ok({**safe, key: "CONFIRM-CONTENT"})
    assert not confirm_feedback_ok({**safe, "format_cells": {"S": "CONFIRM-CONTENT"}})


def test_confirm_failures_consume_training_patience(monkeypatch):
    parent, candidate = SimpleNamespace(sha256="parent"), SimpleNamespace(sha256="candidate")
    st = SimpleNamespace(parent=parent, setting=SimpleNamespace(extra={"configuration": "zebra-pc-v7"}))
    proposed = []
    def engineer(st, cut, r, incumbent, **kw):
        proposed.append((r, incumbent.sha256, kw["history"]))
        return {"candidate_sha256": "candidate", "engineer": {"changes": [], "dropped": [],
                "analysis": {"items": []}, "disclosed": [], "lint": []}}
    monkeypatch.setattr(step, "_engineer_train", engineer)
    monkeypatch.setattr(step, "_package", lambda *a: candidate)
    monkeypatch.setattr(step, "_current", lambda *a: [])
    monkeypatch.setattr(step, "_train_eval", lambda *a, **kw: {"candidate_sha256": "candidate", "adopted": True,
        "cells": 2, "feedback": {}, "verdict": {"adopted": True, "items": 1, "generated": 0, "fixed": ["run"],
        "broken": [], "net": "1/1", "p_sign": 0.5, "reason": None}})
    monkeypatch.setattr(step, "_confirm_eval", lambda *a, **kw: {"confirm": {"items": 40, "evaluated": 40,
        "fixed": 0, "broken": 1, "passed": False, "reason": "gain:fixed_over_broken"}})
    final, history, last = step._train(st, {}, None)
    assert final is parent and last is candidate and len(proposed) == p.TRAIN_PATIENCE
    assert all(line["patience_counted"] and not line["adopted"] for line in history)
    assert all(line["reason"] == "confirm:gain:fixed_over_broken" for line in history)


@pytest.mark.parametrize("emptied", [False, True])
def test_final_audit_precedes_selftest_and_empty_package_releases(monkeypatch, emptied):
    parent, candidate = SimpleNamespace(sha256="parent"), SimpleNamespace(sha256="candidate")
    st = SimpleNamespace(parent=parent, smoke=None, setting=SimpleNamespace(extra={"configuration": "zebra-pc-v7"}))
    seen = []
    monkeypatch.setattr(step, "_train", lambda *a: (candidate, [], candidate))
    monkeypatch.setattr(step, "edits", lambda *a: ["new"])
    def audit(*args):
        seen.append("audit")
        return (parent if emptied else candidate), {"decision": "audit_emptied" if emptied else "continue"}
    monkeypatch.setattr(step, "_audit_final", audit)
    monkeypatch.setattr(step, "_audit_summary", lambda *a: {})
    monkeypatch.setattr(step, "_selftest", lambda *a: seen.append("selftest") or {"blocked": False})
    final, outcome, training = step._trained(st, {}, None)
    assert seen == (["audit"] if emptied else ["audit", "selftest"])
    assert (outcome or {}).get("reason") == ("audit_emptied" if emptied else None)
    assert training["final_sha256"] == final.sha256


@pytest.mark.parametrize("remove", [False, True])
def test_final_audit_reads_public_candidate_notes_and_never_engineer(monkeypatch, tmp_path, remove):
    from dataclasses import replace
    from skillopt.execskill import audit, policy
    from skillopt.execskill.package import empty, with_
    from tests.test_execskill_v25_training import procedure, trace
    st = FakeStep(tmp_path)
    st.chain_root, st.k, st.name, st.chain = tmp_path / "chain", 1, "D/s1-zebralogic", "D"
    st.parent = empty(step="D/s0", evidence="engineering_fixture")
    proc = replace(procedure("p-a", fields={"facts": ["A public clue mentions format."]}),
                   policy_version=policy.POLICY_VERSION_V29)
    candidate = with_(st.parent, step=st.name, add=(proc,))
    row = trace(candidate)
    row.update(unit="D/s1-zebralogic/confirm-r1", private={"answer": "HIDDEN-GOLD"},
               package_sha256=candidate.sha256)
    row["calls"][0]["purpose"] = "first"
    row["replies"] = ["HIDDEN-SOLVER-ANSWER"]
    st.finished.update({"engineer-r1": {"engineer": {"audits": [{"situation_keys": ["already-seen"],
        "counts": {proc.id: {"items": 60, "fired": 60, "non_empty": 60, "faults": 0}},
        "requests": [{"part": "A", "requests": {"G": {"system": "template system", "user": "template user",
                     "max_tokens": 8192, "available": True}}},
                     {"part": "B", "requests": {"G": {"system": "old public situations", "user": "run only",
                     "max_tokens": 8192, "available": True}}}]}]}},
        "confirm-r1": {"confirm": {}}, "train-r1": {}})
    monkeypatch.setattr(step, "_unit_trajectories", lambda st, name: [row] if name.startswith("confirm") else [])
    monkeypatch.setattr(step.units, "audit_judges", lambda *a: {"G": object(), "D": object()})
    monkeypatch.setattr(step.engineer, "run_train", lambda *a: pytest.fail("Audit 2 never calls engineer"))
    captured = []
    def run(procedures, situations, judges, **kw):
        captured.append((procedures, situations, kw))
        return {"confirmed": [{"kind": "template", "procedure": proc.id}] if remove else [],
                "audit_incomplete": False, "tokens": {}}
    monkeypatch.setattr(audit, "run_audit", run)
    final, record = step._audit_final(st, candidate, [{"round": 1}])
    assert bool(captured[0][1]) and captured[0][1][0]["source"] == "confirm"
    assert "HIDDEN-" not in repr(captured) and captured[0][2]["final"]
    assert captured[0][2]["final_package_sha256"] == candidate.sha256
    assert captured[0][1][0]["package_sha256"] == candidate.sha256
    assert captured[0][1][0]["package_procedures"] == {proc.id: audit.text_sha256(proc.source)}
    assert captured[0][2]["exclude"] == {"already-seen"}
    assert captured[0][2]["counts"][proc.id]["items"] == 60
    cache = list(captured[0][2]["cache"].values())
    assert len(cache) == 1 and cache[0]["user"] == "template user"
    assert cache[0]["reused_from_unit"] == "D/s1-zebralogic/engineer-r1"
    assert final.order == (() if remove else candidate.order)
    assert record["decision"] == ("audit_emptied" if remove else "continue")
