"""The registrar's smoke fixtures (``skillopt.execskill.fixtures``; registration §10 engineering fixtures, S0 sandbox
and determinism rows, S2 package X and its placebo P; implementation plan §7, §8). Offline and deterministic: the
procedures run only in the real worker.py through FakeDocker (local subprocesses), the solver is a script, the native
runs and the ALFWorld environment are the fakes of tests/execskill_fakes_env.py. Nothing here needs a real container;
the escape probe and the real image belong to the S0 self-test (smoke.sandbox_selftest)."""
from __future__ import annotations

import argparse
import json
import re
import threading
from contextlib import contextmanager
from fractions import Fraction
from functools import partial

import openpyxl
import pytest

from skillopt.coevo5.protocol import STRONGER_OPTION
from skillopt.continual_eval import backends, datasets, spreadsheet_compat
from skillopt.execskill import fixtures, notes, package, placebo, policy, replay, solver
from skillopt.execskill.errors import CleanupUnconfirmed
from skillopt.execskill.protocol import (
    COMPUTE_INVITE,
    HOOKS,
    NOT_EVALUATED,
    NOT_RECOMMENDED_PREFIX,
    NOTE_HEADERS,
    NOTES_KEY,
)
from skillopt.execskill.sandbox import client
from skillopt.execskill.supply import routing_view as alf_routing_view
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_docker import FakeDocker
from tests.execskill_fakes_env import FakeAlfEnv, FakeNative, Script, alf_sessions
from tests.fixtures.execskill.items import alfworld_games, alfworld_items

LIMITS = {kind: client.Limits(pids=64, memory_mb=768, cpus=0.5, address_space_mb=512, frame_bytes=1 << 20)
          for kind in client.KINDS}
P99 = 300_000
SHEET_RUNTIME = {"prompt_layout": "contract-first-v2", "code_extraction_version": "explicit-python-fences-v1",
                 "spreadsheet_preview_version": "public-formula-preview-v1", "_stop_on_cleanup_failure": True,
                 "image": client.IMAGE, "timeout_seconds": 300, "memory_mb": 4096, "cpus": 1}
PROGRAM = ("```python\nimport openpyxl\nbook = openpyxl.load_workbook('input.xlsx')\n"
           "book.active['D2'] = '=SUM(B2:B6)'\nbook.save('output.xlsx')\n```")
REPAIRED = PROGRAM.replace("B2:B6", "B2:B7")
ERROR_REPORT = {"status": "exception", "exc_type": "KeyError", "message": "KeyError: 'Total'"}
CARD = "Read the table rows before computing."


@pytest.fixture(scope="module")
def made(tmp_path_factory):
    root = tmp_path_factory.mktemp("fixtures")
    return root, fixtures.make_fixtures(root, p99_workbook_bytes=P99)


@pytest.fixture
def docker(tmp_path):
    fake = FakeDocker(tmp_path / "containers")
    yield fake
    fake.close()


def items(root, bench):
    return fixtures.load_items(root, bench)


# ------------------------------------------------------------------------------------- the 60 fixtures (§10)
def test_fixtures_are_deterministic_portable_and_sealed(made, tmp_path):
    root, found = made
    again = fixtures.make_fixtures(tmp_path / "elsewhere", p99_workbook_bytes=P99)
    assert again == found  # the same record, hashes included, wherever it is written
    assert fixtures.make_fixtures(root, p99_workbook_bytes=P99) == found  # an identical rewrite is accepted
    assert fixtures.verify(root) == found
    assert found["version"] == "fivebench-execskill-v1-fixtures" and found["evidence"] == "engineering_fixture"
    for bench in fixtures.BENCHES:
        listed = found["benches"][bench]["items"]
        assert len(listed) == fixtures.COUNT == len(items(root, bench))
        assert len({entry["sha256"] for entry in listed}) == fixtures.COUNT
        assert found["benches"][bench]["set_sha256"] == digest([entry["sha256"] for entry in listed])
        assert all(item["part"] == "engineering_fixture" for item in items(root, bench))
    assert fixtures.make_fixtures(tmp_path / "unpadded")["set_sha256"] != found["set_sha256"]  # p99 bound by hash
    assert found["p99"]["input_bytes"] >= P99 and found["p99"]["task_id"] == "fx-spreadsheetbench-19"
    path = items(root, "spreadsheetbench")[3]["private"]["test_files"][0]
    with open(path, "ab") as handle:
        handle.write(b"tampered")
    with pytest.raises(ValueError):
        fixtures.verify(root)
    with open(path, "rb+") as handle:  # restore for the module's other tests
        data = handle.read()
        handle.seek(0)
        handle.write(data[:-len(b"tampered")])
        handle.truncate()
    assert fixtures.verify(root) == found


def test_shapes_equal_the_frozen_public_views(made):
    root, _ = made
    for bench in fixtures.BENCHES:
        found = items(root, bench)
        assert all(set(i["public"]) == set(backends._PUBLIC[bench]) == datasets._PUBLIC[bench] for i in found)
        assert all(backends._public_view(bench, i["public"]) == i["public"] for i in found)  # value types
        assert all(datasets._PRIVATE[bench] <= set(i["private"]) <= datasets._PRIVATE[bench] | datasets._OPTIONAL
                   for i in found)
        assert all(set(i) == {"benchmark", "task_id", "family_id", "part", "public", "private"} for i in found)
        fixtures._validated(bench, found)  # the frozen panel validator
    for item in items(root, "livemath"):
        options = datasets.livemath_options(item["public"]["choices"])
        assert options is not None and len(set(options)) == 5
        assert options["ABCDE".index(item["private"]["answer"])] != STRONGER_OPTION  # the meta option is never the key


def _table(context):
    rows = [[c.strip() for c in line.strip("|").split("|")] for line in context.splitlines()
            if re.match(r"\| [0-9]{4} \|", line)]
    header = [c.strip() for c in [line for line in context.splitlines() if line.startswith("| Fiscal year")][0]
              .strip("|").split("|")]
    return {int(r[0]): {header[k]: int(r[k]) for k in range(1, len(header))} for r in rows}


def test_officeqa_and_livemath_truth_recomputes_from_the_public_text(made):
    root, found = made
    for item, entry in zip(items(root, "officeqa"), found["benches"]["officeqa"]["items"]):
        question, context = item["public"]["question"], item["public"]["context"]
        table, years = _table(context), [int(y) for y in re.findall(r"fiscal year (\d{4})", question)]
        named = sorted((c for c in fixtures.OQ_COLUMNS if "%s receipts" % c.lower() in question),
                       key=lambda c: question.index("%s receipts" % c.lower()))
        kind = entry["truth"]["kind"]
        column = named[0] if named else None
        if kind == "difference":
            value = Fraction(table[years[1]][column] - table[years[0]][column])
        elif kind == "ratio":
            value = Fraction(table[years[0]][column], table[years[0]][named[1]])
        elif kind == "percent_change":
            value = Fraction(100 * (table[years[1]][column] - table[years[0]][column]), table[years[0]][column])
        elif kind == "sum":
            value = Fraction(sum(table[years[0]].values()))
        else:
            refund = int(re.search(r"refunds of (\d+) million", context).group(1))
            value = Fraction(table[years[0]][column] - refund)
        assert item["private"]["answer"] == fixtures._decimal(value), item["task_id"]
    metas = 0
    for item in items(root, "livemath"):
        options = datasets.livemath_options(item["public"]["choices"])
        question, key = item["public"]["question"], "ABCDE".index(item["private"]["answer"])
        numbers = [int(x) for x in re.findall(r"-?\d+", question.replace("f(x)", ""))]
        if question.startswith("What is the sum of all integers"):
            truth = Fraction(sum(range(numbers[0], numbers[1] + 1)))
        elif "greatest common divisor" in question:
            truth = Fraction(_gcd(numbers[0], numbers[1]))
        elif question.startswith("Let f(x)"):
            c2, c1, c0, x = [int(v) for v in re.findall(r"\d+", question.split("=")[1].replace("x^2", "x"))]
            signs = re.findall(r" ([+-]) ", question)
            c1, c0 = (c1 if signs[0] == "+" else -c1), (c0 if signs[1] == "+" else -c0)
            truth = Fraction(c2 * x * x + c1 * x + c0)
        elif "remainder" in question:
            truth = Fraction(pow(numbers[0], numbers[1], numbers[2]))
        else:
            a, b, c, d = numbers
            truth = Fraction(a, b) + Fraction(c, d)
        assert Fraction(options[key]) == truth and [Fraction(o) for o in options if o != STRONGER_OPTION].count(
            truth) == 1, item["task_id"]
        metas += options[4] == STRONGER_OPTION
        assert options[key] != STRONGER_OPTION
    assert metas == 5


def _gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def test_spreadsheetbench_references_agree_with_their_instruction(made, tmp_path):
    root, found = made
    legacy = spreadsheet_compat._legacy()  # the frozen cache-only comparison (no recalculation)
    for item, entry in zip(items(root, "spreadsheetbench"), found["benches"]["spreadsheetbench"]["items"]):
        instruction, position = item["public"]["instruction"], item["public"]["answer_position"]
        source = openpyxl.load_workbook(item["public"]["input_files"][0], data_only=True)["Sheet1"]
        reference = openpyxl.load_workbook(item["private"]["test_files"][0])
        cached = openpyxl.load_workbook(item["private"]["test_files"][0], data_only=True)
        last = int(re.search(r"B2:B(\d+)|D2:D(\d+)|C2:C(\d+)", instruction).group(0).split(":")[1][1:])
        quantity = [source.cell(row=r, column=2).value for r in range(2, last + 1)]
        price = [source.cell(row=r, column=3).value for r in range(2, last + 1)]
        if "totals the Quantity" in instruction:
            expected = {"D2": sum(quantity)}
        elif "multiplied by its Price" in instruction:
            expected = {"D%d" % (r + 2): quantity[r] * price[r] for r in range(len(quantity))}
        elif "average Quantity" in instruction:
            assert sum(quantity) % len(quantity) == 0
            expected = {"D2": sum(quantity) // len(quantity)}
        elif "greater than" in instruction:
            threshold = int(re.search(r"greater than (\d+)", instruction).group(1))
            expected = {"D2": sum(1 for q in quantity if q > threshold)}
        else:
            expected = {"D2": max(price)}
        assert position == ("D2" if len(expected) == 1 else "D2:D%d" % last)
        for coordinate, value in expected.items():
            assert cached["Sheet1"][coordinate].value == value, (item["task_id"], coordinate)  # the written cache
            assert reference["Sheet1"][coordinate].value == entry["truth"]["formulas"]["Sheet1!" + coordinate]
            assert entry["truth"]["expected"]["Sheet1!" + coordinate] == value
        for row in source.iter_rows():  # outside the answer cells the reference is the input
            for c in row:
                assert cached[c.parent.title][c.coordinate].value == c.value
        assert source.cell(row=1, column=4).value is None and all(
            source.cell(row=r, column=4).value is None for r in range(2, last + 1))
        answer, given = item["private"]["test_files"][0], item["public"]["input_files"][0]
        assert spreadsheet_compat.resolve_targets(position, reference.sheetnames) == {
            "mode": "strict", "targets": [("Sheet1", position)], "target_cells_including_union_overlap": len(expected)}
        assert legacy.compare_workbooks(answer, answer, position) == (True, "")  # the cache is complete
        assert legacy.compare_workbooks(answer, given, position)[0] is False  # the untouched input fails
        output = openpyxl.load_workbook(given)
        for coordinate, value in expected.items():  # a correct values-only output passes against the cache
            output["Sheet1"][coordinate] = value
        output.save(tmp_path / "output.xlsx")
        assert legacy.compare_workbooks(answer, str(tmp_path / "output.xlsx"), position) == (True, "")
    padded = items(root, "spreadsheetbench")[fixtures.PADDED]
    book = openpyxl.load_workbook(padded["public"]["input_files"][0], read_only=True)
    assert book.sheetnames == ["Sheet1", "Padding"]  # the answer position resolves on the first sheet
    book.close()


# ----------------------------------------------------------------------------------------------- package X (§10 S2)
def test_package_x_loads_passes_the_policy_and_covers_every_hook(tmp_path):
    found = fixtures.fixture_package()
    assert fixtures.fixture_package().sha256 == found.sha256  # deterministic
    sha = package.save(tmp_path / "store", found)
    loaded = package.load(tmp_path / "store" / "packages" / (sha + ".json"))
    assert loaded == found and loaded.evidence == "engineering_fixture" and loaded.step == fixtures.STEP
    assert list(loaded.order) == ["fx-note", "fx-bindings", "fx-print", "fx-crash", "fx-sheet-repair",
                                  "fx-alf-tracker"]
    for procedure in loaded.procedures:
        assert policy.check(procedure.source) == [] and procedure.description and procedure.replay_tests
        assert procedure.is_fixture and "applies" in procedure.hooks
    assert {h for p in loaded.procedures for h in p.hooks} == set(HOOKS)
    assert fixtures.FX_CRASH_SUBSET == fixtures.crash_subset() and all(
        len(ids) == fixtures.CRASH_PER_BENCH for ids in fixtures.FX_CRASH_SUBSET.values())


def _workers(docker, tmp_path):
    @contextmanager
    def opened(pkg, *, kind, hashseed, inputs_dir):
        worker = client.Worker(docker=docker, limits=LIMITS, scratch=tmp_path, hashseed=hashseed)
        worker.start(pkg, kind=kind, inputs_dir=inputs_dir)
        try:
            yield worker
        finally:
            worker.close()

    return opened


def test_replay_tests_pass_in_the_sandbox_except_fx_crash_on_its_subset(made, docker, tmp_path):
    root, _ = made
    entries = {c: replay.inputs_of(t) for c, t in fixtures.replay_trajectories(root).items()}
    dirs = fixtures.public_input_dirs(root, tmp_path / "inputs")
    workers = _workers(docker, tmp_path)
    subset = {fixtures.cell(b, t) for b, ids in fixtures.FX_CRASH_SUBSET.items() for t in ids}
    for procedure in fixtures.fixture_package().procedures:
        if procedure.id == "fx-alf-tracker":
            scope = [fixtures.ALF_FAIL, fixtures.ALF_PASS]
        elif procedure.id == "fx-sheet-repair":
            scope = [c for c in entries if c.startswith("fx/spreadsheetbench/")][:4]
        elif procedure.id == "fx-bindings":
            scope = [c for c in entries if c.startswith("fx/officeqa/")][:3]
        else:  # one item of each fixture bench, plus the fx-crash subset
            scope = sorted({fixtures.cell(b, "fx-%s-00" % b) for b in fixtures.BENCHES}
                           | {t["trajectory"] for t in procedure.replay_tests} | subset)
        chosen = [entries[c] for c in scope]
        report, outcomes = replay.zero_crash(procedure, chosen, workers, inputs_dirs=dirs)
        crashed = {f["cell"] for f in replay.crash_faults(outcomes)}
        if procedure.id == "fx-crash":
            assert crashed == subset and not report["passed"]  # faults exactly where registered
            outcomes = {c: o for c, o in outcomes.items() if c not in subset}
        else:
            assert report["passed"] and crashed == set(), (procedure.id, report)
        tests = replay.run_tests(procedure, {c: entries[c] for c in scope if c not in subset or
                                             procedure.id != "fx-crash"}, outcomes, workers, inputs_dirs=dirs)
        assert tests["passed"], (procedure.id, tests)
        assert replay.format_guard(outcomes) == []
        if procedure.id == "fx-alf-tracker":
            assert tests["tracker_agreement"][0] == tests["tracker_agreement"][1] > 0  # the D3 reference, 100 %


# ------------------------------------------------------------------- every hook kind through the real shell
def _worker(docker, tmp_path):
    return client.Worker(docker=docker, limits=LIMITS, scratch=tmp_path)


def _fired(shell):
    """The hook kinds that ran without a fault in one cell; ``applies`` when the router enabled a procedure."""
    return {e["fn"] for e in shell["procedure_events"] if e["fault"] is None} | (
        {"applies"} if shell["route"]["enabled"] else set())


def test_every_hook_kind_fires_with_a_visible_effect_through_the_real_shell(made, docker, tmp_path, monkeypatch):
    root, _ = made
    x = fixtures.fixture_package()
    fired = set()
    # OfficeQA: notes, bindings and the exact <calc> round trip (§2.4)
    item = items(root, "officeqa")[0]
    name, value = (lambda p: (p["name"], p["value"]))(x.get("fx-bindings").replay_tests[0]["property"])
    call = Script(["<calc>%s + 1</calc>" % name, "<answer>%d</answer>" % (int(value) + 1)])
    prediction = solver.solve("officeqa", item["public"], CARD, x, call, worker=_worker(docker, tmp_path))
    first, second = (json.loads(user) for _, user in call.requests)
    assert first[NOTES_KEY].endswith(COMPUTE_INVITE) and "Numbers quoted in the task text:" in first[NOTES_KEY]
    assert "Characters in the task text:" in first[NOTES_KEY] and "%s = %s" % (name, value) in first[NOTES_KEY]
    assert second["computed"] == [{"expr": "%s + 1" % name, "value": str(int(value) + 1)}]
    shell = prediction["shell"]
    assert shell["faults"] == [] and shell["deciding_receipt"] == 1 and prediction["output"] == call.receipts[1][
        "response"]
    assert shell["route"]["enabled"] == ["fx-note", "fx-bindings", "fx-print", "fx-crash"]  # the predicates decide
    fired |= _fired(shell)
    # the registered fx-crash item: one procedure fault, the cell completes
    crashed = next(i for i in items(root, "officeqa") if i["task_id"] in fixtures.FX_CRASH_SUBSET["officeqa"])
    prediction = solver.solve("officeqa", crashed["public"], CARD, x, Script(["<answer>1</answer>"]),
                              worker=_worker(docker, tmp_path))
    assert prediction["status"] == "available" and [(f["procedure"], f["kind"], f["exc_type"]) for f in
                                                    prediction["shell"]["faults"]] == [
        ("fx-crash", "exception", "RuntimeError")]
    # SpreadsheetBench: the pre-check report, sheet_feedback and the one repair call (§2.5)
    native = FakeNative(report=ERROR_REPORT).install(monkeypatch)
    sheet = items(root, "spreadsheetbench")[0]
    call = Script([PROGRAM, REPAIRED])
    prediction = solver.solve("spreadsheetbench", sheet["public"], CARD, x, call, runtime=SHEET_RUNTIME,
                              worker=_worker(docker, tmp_path))
    repair = json.loads(call.requests[1][1])
    assert NOTE_HEADERS["warnings"] in repair["repair_notes"] and "The first sheet Sheet1 holds" in repair[
        "repair_notes"]
    assert repair["run_report"] == ERROR_REPORT and len(native.prechecks) == 1
    assert prediction["shell"]["faults"] == [] and "B2:B7" in prediction["output"]["code"]
    assert "fx-sheet-repair" in prediction["shell"]["route"]["enabled"]
    fired |= _fired(prediction["shell"])
    # ALFWorld: the recorder's notes, the discouraged command and the host-kept state
    alf_sessions(monkeypatch)
    game, pool = alfworld_games()[0], alfworld_items(tmp_path / "alf")[0]
    observations, _, infos = FakeAlfEnv(game).reset()
    view = alf_routing_view(observations[0], infos[0]["admissible_commands"])
    public = {**pool["public"], "routing_view": view, "routing_view_sha256": digest(view)}
    call = Script(["<action>%s</action>" % step for step in game["plan"]])
    prediction = solver.solve("alfworld", public, CARD, x, call, worker=_worker(docker, tmp_path))
    assert prediction["output"] == {"won": True, "steps": len(game["plan"])}
    second_step = json.loads(call.requests[1][1])
    assert second_step[NOTES_KEY].endswith(NOT_RECOMMENDED_PREFIX + "go to countertop 1")
    assert "Places reached so far: countertop 1" in second_step[NOTES_KEY]
    steps = prediction["shell"]["alfworld_steps"]
    assert steps[1]["discouraged"] == ["go to countertop 1"] and steps[0]["state_sha256"]["fx-alf-tracker"]
    assert prediction["shell"]["faults"] == [] and prediction["shell"]["route"]["enabled"] == ["fx-alf-tracker"]
    fired |= _fired(prediction["shell"])
    assert fired == set(HOOKS)
    assert docker.containers == {}
    client.drain_check(docker=docker)


def test_placebo_p_shows_irrelevant_text_in_the_same_slots(made, docker, tmp_path):
    root, _ = made
    x = fixtures.fixture_package()
    chosen = items(root, "officeqa")[:2] + items(root, "livemath")[:1]
    content = fixtures.fixture_placebo(chosen, unit="smoke/s2/officeqa")
    assert fixtures.fixture_placebo(chosen, unit="smoke/s2/officeqa") == content  # deterministic
    for entry in content.values():
        for sham in entry["procedures"].values():
            for hook, fields in sham.items():
                for bench in ("officeqa", "livemath", "spreadsheetbench", "searchqa"):
                    fields_ = fields[0]["fields"] if hook == "alf_before_step" else fields
                    assert notes.screen(fields_, bench=bench)[1] == []  # lexicon-clean everywhere
    item = chosen[0]
    call = Script(["<calc>2 + 2</calc>", "<answer>4</answer>"])
    prediction = solver.solve("officeqa", item["public"], CARD, x, call, worker=_worker(docker, tmp_path),
                              placebo=placebo.arm(content, item["task_id"], seed="smoke-seed"))
    first, second = (json.loads(user) for _, user in call.requests)
    text = content[item["task_id"]]["procedures"]["fx-note"]["before_call"]["facts"][0]
    assert text in first[NOTES_KEY] and "Numbers quoted" not in first[NOTES_KEY]
    assert second["computed"] == [{"expr": "2 + 2", "value": NOT_EVALUATED}]
    assert prediction["shell"]["faults"] == [] and prediction["shell"]["arm"]["placebo"] == sorted(
        p.id for p in x.procedures if p.id in content[item["task_id"]]["procedures"])


# -------------------------------------------------------------------------------------- the S0 sandbox suite
def _in_thread(function):
    out = {}
    thread = threading.Thread(target=lambda: out.update(result=function()))
    thread.start()
    return thread, out


def test_sandbox_suite_procedures_give_their_fault_class_and_the_cell_completes(made, docker, tmp_path):
    root, _ = made
    suite, cases = fixtures.sandbox_suite()
    assert {c["id"] for c in cases} | {fixtures.HEALTHY} == set(fixtures.SUITE_SOURCES)
    assert {c["id"] for c in cases if policy.check(fixtures.SUITE_SOURCES[c["id"]][0])} == {"fx-sbx-banned"}
    padded = fixtures.public_input_dirs(root, tmp_path / "inputs")[
        fixtures.cell("spreadsheetbench", "fx-spreadsheetbench-%02d" % fixtures.PADDED)]
    plain = client.Worker(docker=docker, limits=LIMITS, scratch=tmp_path).start(suite, kind="cell")
    mounted = client.Worker(docker=docker, limits=LIMITS, scratch=tmp_path).start(suite, kind="cell",
                                                                                  inputs_dir=padded)
    view = {"text": "fixture view"}
    try:
        for case in cases:
            worker = mounted if case["inputs"] == "p99" else plain
            assert worker.call(fixtures.HEALTHY, "applies", [view], timeout_s=2)["value"] is True
            run = partial(worker.call, case["id"], case["fn"], case["args"], timeout_s=case["timeout_s"])
            if case["action"] is None:
                result = run()
            else:
                name = worker.names[-1]
                thread, out = _in_thread(run)
                docker.children(name)
                (docker.kill_child if case["action"] == "kill_child" else docker.kill_worker)(name)
                thread.join(60)
                result = out["result"]
            expected = case["expected"]
            if expected["class"] == "procedure_fault":
                assert result["ok"] is False and result["fault"] == expected["fault"], (case["id"], result)
            else:
                assert result["ok"] is True, (case["id"], result)
            assert worker.call(fixtures.HEALTHY, "applies", [view], timeout_s=2)["value"] is True  # cell goes on
        assert plain.dropped == ["fx-sbx-worker-kill"] and plain.rejected == {"fx-sbx-banned": "policy:import"}
    finally:
        for worker in (plain, mounted):
            try:
                worker.close()
            except CleanupUnconfirmed:
                pass
    assert docker.containers == {}


def test_two_hash_seeds_and_two_orders_give_the_same_value_hashes(made, docker, tmp_path):
    root, _ = made
    x = fixtures.fixture_package()
    views = {bench: [solver.routing_view(bench, i["public"], runtime=fixtures.SHEET_RUNTIME)
                     for i in items(root, bench)[:3]] for bench in fixtures.BENCHES}
    game = alfworld_games()[1]
    observations, _, infos = FakeAlfEnv(game).reset()
    views["alfworld"] = [alf_routing_view(observations[0], infos[0]["admissible_commands"])]
    runs = []
    for seed, reverse in ((0, False), (1, True)):
        worker = client.Worker(docker=docker, limits=LIMITS, scratch=tmp_path, hashseed=seed).start(x, kind="cell")
        try:
            runs.append(fixtures.determinism_hashes(worker, x, views, reverse=reverse))
            assert worker.ping()["hashseed"] == str(seed)
        finally:
            worker.close()
    assert runs[0] == runs[1]
    assert {key.rsplit("/", 1)[1] for key in runs[0]} == {"applies", "before_call", "bindings", "alf_before_step"}
    crashed = {"livemath/%d/fx-crash/before_call" % k for k in range(3)
               if "fx-livemath-%02d" % k in fixtures.FX_CRASH_SUBSET["livemath"]}
    assert crashed and {key for key, value in runs[0].items() if value.startswith("fault:")} == crashed


# ---------------------------------------------------------------------------------------------------------- CLI
def test_make_fixtures_cli_writes_and_prints_counts(tmp_path, capsys):
    top = argparse.ArgumentParser()
    fixtures.add_arguments(top.add_subparsers(dest="command", required=True))
    args = top.parse_args(["make-fixtures", "--out", str(tmp_path / "cli"), "--p99-workbook-bytes", "20000"])
    assert fixtures.make_fixtures_cli(args) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["counts"] == {"officeqa": 20, "livemath": 20, "spreadsheetbench": 20}
    assert printed["p99"]["input_bytes"] >= 20000 and printed["package_sha256"] == fixtures.fixture_package().sha256
    assert fixtures.verify(tmp_path / "cli")["record_sha256"] == printed["record_sha256"]
