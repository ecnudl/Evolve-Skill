"""Zero-call ZebraLogic adapter/scorer checks; every puzzle and gold cell is synthetic."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from tests.execskill_zpc_fakes import tmp_path

from skillopt.coevo5.data import TestAccess
from skillopt.execskill import judge, solver, zebralogic as z
from skillopt.execskill.package import empty
from tests.execskill_fakes_env import Script, receipt


def row(task="5*2", index=0, *, item_id=None):
    houses, width = map(int, task.split("*"))
    columns = ["Trait %d" % i for i in range(1, width + 1)]
    return {"bench": z.BENCH, "id": item_id or "synthetic-%s-%d" % (task, index), "size": task, "task": task,
            "puzzle": ("There are %d houses, numbered 1 to %d from left to right, as seen from across the street. "
                       "Synthetic puzzle %d.\nKeep this text exactly.  ") % (houses, houses, index),
            "solution": {"header": ["House"] + columns,
                         "rows": [[str(h)] + ["value %d %d" % (h, c) for c in range(1, width + 1)]
                                  for h in range(1, houses + 1)]}, "source_index": index, "pool_order": index}


def pool_rows():
    result = []
    for task in z.DOMAIN:
        excluded = [item_id for item_id in z.EXCLUDED_IDS if "-" + task.replace("*", "x") + "-" in item_id]
        result.extend(row(task, i, item_id=excluded[i] if i < len(excluded) else None) for i in range(20))
    return result


def materialize(path, rows):
    raw = json.dumps(rows).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def task():
    return z.normalize(row())


def answer(item=None):
    item = item or task()
    return json.dumps({"reasoning": "Synthetic derivation.", "solution": item["private"]["answer"]})


def prediction(reply):
    return {"status": "available", "output": reply, "reason": "model_response_available", "costs": {}}


def scored(reply, item=None):
    item = item or task()
    return z.score(item["public"], item["private"], prediction(reply))


def test_identity_is_by_value_and_never_opens_a_panel(monkeypatch):
    monkeypatch.setattr(Path, "read_bytes", lambda *a, **k: pytest.fail("identity must not read"))
    identity = z.identity()
    assert identity["pool"]["sha256"] == z.POOL_SHA256
    assert identity["sealed"]["sha256"] == z.SEALED_SHA256
    assert len(identity["excluded_ids"]) == len(set(identity["excluded_ids"])) == 27
    assert z.EXCLUDED_IDS_SHA256 == "3e331ed7e5ceb851d3ee75b7c7a6758efe3bd6227453ec466c6ddc3d099517b4"
    assert z.EXCLUDED_IDS_SHA256 == hashlib.sha256(json.dumps(list(z.EXCLUDED_IDS), separators=(",", ":")).encode()).hexdigest()
    assert z.CARD_SHA256 == hashlib.sha256(z.CARD_TEXT.encode()).hexdigest()
    assert z.CARD_TEXT == "Follow the format in the user message."
    assert '"reasoning"' in z.TEMPLATE_TEXT and '"solution"' in z.TEMPLATE_TEXT
    assert "internal use only" in identity["license"]
    assert "first_use" in identity["freshness"]


def test_pool_identity_domain_stratification_probe_exclusion_and_exact_public_shape(tmp_path):
    rows = pool_rows() + [row("4*2", 100)]
    path = tmp_path / "synthetic-pool.json"
    pin = materialize(path, rows)
    tasks = z.load_pool(path, expected_sha256=pin)
    assert len(tasks) == 200
    assert Counter(t["task"] for t in tasks) == {size: 20 for size in z.DOMAIN}
    assert tasks[0]["public"] == {"question": rows[0]["puzzle"], "columns": rows[0]["solution"]["header"][1:]}
    cuts = z.slices(tasks)
    assert {k: len(v) for k, v in cuts.items()} == {"smoke": 10, "run": 60, "accept": 100, "spare": 3}
    ids = [t["task_id"] for items in cuts.values() for t in items]
    assert len(ids) == len(set(ids)) == 173 and not set(ids) & set(z.EXCLUDED_IDS)
    for name, count in z.SLICES_PER_TASK.items():
        assert Counter(t["task"] for t in cuts[name]) == {size: count for size in z.DOMAIN}
    assert cuts == z.slices(list(reversed(tasks)))
    assert cuts != z.slices(tasks, seed=z.SLICE_SEED + 1)
    with pytest.raises(ValueError, match="identity mismatch"):
        z.load_pool(path, expected_sha256="0" * 64)
    path.write_text(json.dumps(rows[:-2]))
    with pytest.raises(ValueError):
        z.load_pool(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def test_pool_never_reads_a_sealed_named_source_or_symlink(tmp_path, monkeypatch):
    forbidden = tmp_path / "sealed-holdout.json"
    forbidden.write_text("[]")
    link = tmp_path / "pool.json"
    link.symlink_to(forbidden)
    monkeypatch.setattr(Path, "read_bytes", lambda *a, **k: pytest.fail("forbidden source opened"))
    for path in (forbidden, link):
        with pytest.raises(ValueError, match="Refuse sealed"):
            z.load_pool(path)


def test_sealed_loader_demands_test_access_before_any_read_and_reads_only_its_fake_panel(tmp_path, monkeypatch):
    path = tmp_path / "fake-sealed-holdout.json"
    pin = materialize(path, pool_rows())
    seen, read = [], Path.read_bytes
    def tracked(path):
        seen.append(str(path))
        return read(path)
    monkeypatch.setattr(Path, "read_bytes", tracked)
    entry = {"path": str(path), "sha256": pin}
    with pytest.raises(ValueError, match="consent-gated"):
        z.test_panel(entry, access=None)
    assert seen == []
    with pytest.raises(ValueError, match="only ZebraLogic"):
        z.test_panel(entry, "searchqa", access=TestAccess("synthetic-read"))
    assert seen == []
    tasks, report = z.test_panel(entry, access=TestAccess("synthetic-read"))
    assert len(tasks) == report["tasks"] == 200 and report["unit"] == "synthetic-read"
    assert all(t["partition"] == "test" for t in tasks)
    assert seen == [str(path)]


def test_solver_public_view_is_exact_and_card_is_grid_contract():
    item = task()
    public = {**item["public"], "answer": item["private"]["answer"], "secret": "DO NOT DISCLOSE"}
    assert solver.routing_view(z.BENCH, public) == item["public"]
    call = Script([answer(item)])
    result = solver.solve(z.BENCH, public, z.CARD_TEXT, empty(step="s0", evidence="engineering_fixture"), call)
    assert result["status"] == "available"
    assert z.parse_user(call.requests[0][1]) == item["public"]
    assert call.requests[0][1] == z.render_user(item["public"])
    assert call.requests[0][0] == solver.QA_SYSTEM
    assert "Python program" not in call.requests[0][0] and "<answer>" not in call.requests[0][0]


@pytest.mark.parametrize("wrapped", [lambda x: x, lambda x: "```json\n" + x + "\n```",
                                     lambda x: "reasoning\n" + x + '\n{"other": "ignored"}'])
def test_correct_grid_bare_and_fenced(wrapped):
    result = scored(wrapped(answer()))
    assert result["status"] == "pass" and result["score"] == 1.0
    assert result["metrics"] == {"invalid_format": 0.0, "correct_cells": 10, "total_cells": 10}


def test_last_solution_object_only_and_no_scalar_answer_rescue():
    wrong = json.loads(answer())
    wrong["solution"]["House 1"]["Trait 1"] = "wrong"
    assert scored(answer() + json.dumps(wrong))["status"] == "fail"
    assert scored(json.dumps(wrong) + answer())["status"] == "pass"
    assert scored(answer() + '{"solution": null}')["metrics"]["invalid_format"] == 1.0
    assert scored('{"answer": ' + answer() + '}')["status"] == "fail"
    assert scored(answer() + '{"solution": {}, " Solution ": {}}')["status"] == "fail"


def test_one_wrong_cell_is_puzzle_failure_but_format_valid():
    wrong = json.loads(answer())
    wrong["solution"]["House 2"]["Trait 1"] = "wrong"
    result = scored(json.dumps(wrong))
    assert result["status"] == "fail" and result["score"] == 0.0
    assert result["metrics"] == {"invalid_format": 0.0, "correct_cells": 9, "total_cells": 10}


@pytest.mark.parametrize("change", [
    lambda grid: grid.pop("House 1"),
    lambda grid: grid.update({"House 6": dict(grid["House 1"])}),
    lambda grid: grid["House 1"].pop("Trait 1"),
    lambda grid: grid["House 1"].update({"extra": "value"}),
    lambda grid: grid.update({" house 1 ": dict(grid["House 1"])}),
    lambda grid: grid["House 1"].update({" trait 1 ": "value 1 1"}),
    lambda grid: grid["House 1"].update({"Trait 1": 4}),
    lambda grid: grid.update({"House 01": grid.pop("House 1")}),
])
def test_missing_extra_casefold_duplicate_nontext_and_wrong_house_keys_fail(change):
    output = json.loads(answer())
    change(output["solution"])
    result = scored(json.dumps(output))
    assert result["status"] == "fail" and result["metrics"]["invalid_format"] == 1.0


@pytest.mark.parametrize("reply", ["", "not JSON", '{"solution":', '{"solution": []}',
    answer().replace('"House 1": {', '"House 1": {}, "House 1": {'),
    answer().replace('"Trait 1": "value 1 1"', '"Trait 1": "value 1 1", "Trait 1": "value 1 1"'),
    answer().replace('"solution": {', '"solution": {}, "solution": {')])
def test_malformed_and_literal_duplicate_keys_are_delivered_failures(reply):
    result = scored(reply)
    assert result["status"] == "fail" and result["metrics"]["invalid_format"] == 1.0


def test_keys_casefold_trim_and_values_collapse_whitespace():
    grid = task()["private"]["answer"]
    varied = {"  " + h.upper() + " ": {" " + c.lower() + " ": "\t" + v.upper().replace(" ", " \t\n ") + " "
                                       for c, v in cells.items()} for h, cells in grid.items()}
    assert scored(json.dumps({" SOLUTION ": varied}))["status"] == "pass"


@pytest.mark.parametrize("public,private,output", [({}, {}, "bad"),
    (task()["public"], {}, answer()), (task()["public"], task()["private"], None),
    ({"question": "q", "columns": ["x", " X "]}, task()["private"], answer())])
def test_invalid_scorer_inputs_stay_unknown(public, private, output):
    result = z.score(public, private, prediction(output))
    assert result["status"] == "unknown" and result["score"] is None


def test_transport_stays_unknown_and_format_flag_does_not_turn_it_into_failure():
    item = task()
    pred = {"status": "unknown", "output": None, "reason": "model_response_unavailable"}
    receipts = [{**receipt(None, ok=False), "error_type": "transport"}]
    result = judge.judge(z.BENCH, item["public"], item["private"], pred, receipts, runtime={})
    assert result["v2"]["token"] == "unknown"
    assert result["format"]["violation"] is None


@pytest.mark.parametrize("reply,token,violation", [(answer(), "pass", False), ("malformed", "fail", True),
    (answer().replace("value 1 1", "wrong"), "fail", False)])
def test_judge_keeps_binary_schema_and_raw_cell_metrics_are_not_promoted(reply, token, violation):
    item = task()
    result = judge.judge(z.BENCH, item["public"], item["private"], prediction(reply), [receipt(reply)], runtime={})
    assert result["v2"]["token"] == result["final"]["token"] == token
    assert result["format"]["violation"] is violation
    assert result["lenient"] == {"pass": None}
    assert "correct_cells" not in json.dumps(result) and "total_cells" not in json.dumps(result)
    assert "value 1 1" not in json.dumps(result)


def test_grid_masking_removes_grids_and_repeated_cells():
    reply = "I chose VALUE 1 1, then value 1 2. " + answer()
    masked = z.mask_reply(reply)
    assert "solution" not in masked and "value" not in masked.casefold()
    assert z.mask_reply('partial {"solution": {"House 1": {"Trait 1": "private guess"}') == "[masked]"
    assert z.mask_reply(answer() + ' {"solution": {"secret": "private guess"') == "[masked]"


def test_real_cell_scoring_persistence_keeps_metrics_only_in_raw_scorer(tmp_path):
    from skillopt.coevo5.calls import Endpoint, Slots
    from skillopt.execskill.cells import Arm, Context, TrainingStore, cell_id, run_cell
    from skillopt.execskill import trajectories

    item = task()
    class Client:
        def call(self, system, user):
            return receipt(answer(item))
    endpoint = Endpoint(Client(), model="glm-5.3", max_tokens=100,
                        slots=Slots(tmp_path / "slots", "glm-5.3", 1), sleep=lambda _: None)
    attempt = tmp_path / "unit" / "attempt-1"
    context = Context(attempt=attempt, endpoint=endpoint, runtime={z.BENCH: {}}, cards={z.BENCH: z.CARD_TEXT},
                      native=None, episodes=None, worker=lambda _: pytest.fail("card needs no worker"),
                      evidence="engineering_fixture")
    unit, item_id = "G/s1-zebralogic/run", z.BENCH + "/" + item["task_id"]
    cell = {"id": cell_id(unit, "C", item_id, 0), "unit": unit, "arm": "C", "benchmark": z.BENCH,
            "task_id": item_id, "run": 0}
    record = run_cell(context, cell, item, Arm("card", empty(step="s0", evidence="engineering_fixture")),
                      store=TrainingStore(attempt))
    assert record["stop"] is None and record["final"]["token"] == "pass"
    assert record["judge"]["v2"]["token"] == "pass"
    raw_score = json.loads((attempt / "artifacts" / (record["attempts"][0]["score"]["sha256"] + ".json")).read_text())
    assert raw_score["metrics"]["correct_cells"] == raw_score["metrics"]["total_cells"] == 10
    assert "correct_cells" not in json.dumps(record) and "total_cells" not in json.dumps(record)
    assert "value 1 1" not in json.dumps(raw_score)
    from skillopt.execskill.evaluation import sealed_cell
    sealed = json.dumps(sealed_cell(record))
    assert "correct_cells" not in sealed and "total_cells" not in sealed and "value 1 1" not in sealed
    trajectory = json.loads((attempt / "trajectories" / (cell["id"] + ".json")).read_text())
    masked = trajectories.masked_view(trajectory, bench=z.BENCH, purpose="examiner")
    assert masked["passed"] is True and masked["task"] == item["public"]
    assert "value 1 1" not in json.dumps(masked)


def test_text_request_reuse_has_no_calculator_or_post_call_hooks():
    from skillopt.execskill import reuse
    package = empty(step="s0", evidence="engineering_fixture")
    view = task()["public"]
    first = reuse.signature(z.BENCH, package, view, None, card_text=z.CARD_TEXT)
    same = reuse.signature(z.BENCH, package, view, None, card_text=z.CARD_TEXT)
    other = reuse.signature(z.BENCH, package, {**view, "question": view["question"] + "x"}, None,
                            card_text=z.CARD_TEXT)
    assert first["post_call"] == []
    assert reuse.interchangeable(first, same, bench=z.BENCH)
    assert not reuse.interchangeable(first, other, bench=z.BENCH)
    assert not reuse.interchangeable({**first, "faults": [{}]}, same, bench=z.BENCH)


def test_no_j6_means_no_independent_card_sample():
    from skillopt.execskill import reuse
    assert reuse.card_sample({"bench": z.BENCH, "card_is_parent": True, "j6_registered": False}) is None


def test_grid_cells_are_protected_in_v23_engineer_excerpts():
    from skillopt.execskill import engineer_payload, trajectories
    output = '{"solution": {"House 1": {"Trait": "ZpcSpecialCell"}}}'
    assert trajectories._carried(z.BENCH, output) == ["ZpcSpecialCell"]
    assert trajectories._carried(z.BENCH, output[:-2]) == ["ZpcSpecialCell"]
    long = "There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street. " + "prefix " * 1800 + " ZpcSpecialCell " + " tail " * 2000
    payload = {"bench": z.BENCH, "trajectories": [{"bench": z.BENCH, "kind": "successes",
        "replies": [output], "calls": [{"user": z.render_user({"question": long, "columns": ["Trait"]})}]}]}
    trimmed = engineer_payload.trim(payload)
    view = z.parse_user(trimmed["trajectories"][0]["calls"][0]["user"])
    assert len(view["question"]) <= 6000 and "ZpcSpecialCell" in view["question"]
    assert z.parse_user(payload["trajectories"][0]["calls"][0]["user"])["question"] == long


def test_hook_receives_exact_public_view_and_table_reaches_solver_with_unchanged_lexicon():
    from skillopt.execskill import notes
    from skillopt.execskill.package import Package
    from tests.execskill_fakes_env import FakeSandbox, procedure
    item = task()
    item["public"]["question"] += " The listed value is format."
    proc = procedure("fx-zpc-table", ("applies", "before_call"), origin=z.BENCH)
    seen = []
    def before(view, state):
        seen.append(view)
        return {"table": [["Trait 1", "format"]]}
    worker = FakeSandbox({proc.id: {"before_call": before}})
    package = Package((proc,), "s1", "engineering_fixture")
    call = Script([answer(item)])
    result = solver.solve(z.BENCH, item["public"], z.CARD_TEXT, package, call, worker=worker)
    assert seen == [item["public"]]
    request = z.parse_user(call.requests[0][1])
    assert "| Trait 1 | format |" in request["procedure_notes"]
    assert result["shell"]["faults"] == [] and result["shell"]["compute"] is None
    assert notes.lexicon_hits("format", bench=z.BENCH) == notes.lexicon_hits("format", bench="searchqa")
    assert notes.lexicon_hits("format", bench=z.BENCH)  # no new ZebraLogic exemption


def test_grid_unknown_and_delivered_failure_keep_historical_l_h_bounds():
    from skillopt.execskill import stats_ext
    item = task()
    unknown = judge.judge(z.BENCH, {}, {}, prediction(answer()), [receipt(answer())], runtime={})["v2"]["token"]
    failed = judge.judge(z.BENCH, item["public"], item["private"], prediction("bad"), [receipt("bad")],
                         runtime={})["v2"]["token"]
    table = {("S'", "u"): [unknown], ("S'", "f"): [failed]}
    assert stats_ext.item_scores(table, "S'", ["u", "f"], side="L") == {"u": 0, "f": 0}
    assert stats_ext.item_scores(table, "S'", ["u", "f"], side="H") == {"u": 1, "f": 0}


def test_scorer_and_hooks_are_versioned_by_value_in_the_identity():
    from skillopt.execskill import protocol
    from skillopt.validator_pilot.api import digest
    identity = z.identity()
    scorer, hooks = identity["scorer"], identity["hooks"]
    assert scorer["version"] == "zebra-pc-v1-grid-scorer" and scorer["puzzle_binary"] is True
    assert scorer["raw_only_cell_metrics"] == ["correct_cells", "total_cells"] and not scorer["persist_gold"]
    assert scorer["duplicates"] == "reject_literal_or_normalized_keys"
    assert scorer["invalid_delivered_string"] == "fail" and scorer["invalid_scorer_input_or_transport"] == "unknown"
    assert hooks["allowed"] == ["applies", "before_call"] and not hooks["bindings"]
    assert hooks["note_cap_chars_per_cell"] == 4000 and hooks["lexicon_exemptions"] == []
    assert hooks["lexicon_terms"] == list(protocol.LEXICON_TERMS)
    assert hooks["verbatim"] == protocol.LEXICON_VERBATIM and hooks["lexicon_match"] == protocol.LEXICON_MATCH
    original = digest(identity)
    for section, key, value in [("scorer", "puzzle_binary", False), ("hooks", "bindings", True),
                                ("hooks", "lexicon_exemptions", ["format"])]:
        changed = json.loads(json.dumps(identity))
        changed[section][key] = value
        assert digest(changed) != original
