"""SpreadsheetBench's no-workbook shortcut probe (ticket C1-2; registration §7.2 shortcut gate, §9.2 shortcut probe;
registrar decision 2026-10-22 row C1-2 and its 13:0x addendum). ``solver.solve(..., shortcut="no_workbook")`` shows the
model neither the workbook preview nor any other sheet content, while the program is still pre-checked and executed on
the real input files; a shortcut-probe cell hands its mode to the shell (on re-execution too) and its record states the
mode the shell ran in; ``examiner.shortcut`` reaches its verdict on such cells and refuses a probe cell that saw the
workbook. Offline and deterministic: FakeNative's pre-check, container runs that record their input and deliver a
workbook, scripted receipts behind the frozen Endpoint, a fixture verdict in place of the recalculating scorer.
Everything is an engineering fixture, never method-effect evidence."""
from __future__ import annotations

import base64
import io
import json
import zipfile
from pathlib import Path

import openpyxl
import pytest

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json
from skillopt.execskill import cells, examiner, solver
from skillopt.execskill.cells import Arm, Context, TrainingStore, cell_id, run_cell
from skillopt.execskill.generators import sheet
from skillopt.execskill.generators.families import generated_item
from skillopt.execskill.package import FIXTURE, Package, empty
from skillopt.execskill.protocol import BENCHES, record, verified
from tests.execskill_fakes_env import FakeNative, FakeSandbox, Script, procedure

CARD = "Write the program from the instruction."
EMPTY = empty(step="s0", evidence=FIXTURE)
SHEET_RUNTIME = {"prompt_layout": "contract-first-v2", "code_extraction_version": "explicit-python-fences-v1",
                 "spreadsheet_preview_version": "public-formula-preview-v1", "_stop_on_cleanup_failure": True,
                 "image": "sha256:" + "0" * 64, "timeout_seconds": 300, "memory_mb": 4096, "cpus": 1}
HISTORICAL = {k: v for k, v in SHEET_RUNTIME.items() if k not in ("code_extraction_version", "prompt_layout",
                                                                 "spreadsheet_preview_version")}
RUNTIMES = {**RUNTIME, "spreadsheetbench": SHEET_RUNTIME}
RIGHT, WRONG = "=SUM(A2:A4)", "=A2"
USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
GENERATOR = "fx-gen-sb-1"
TIMEOUT = {"status": "unknown", "reason": "native_timeout"}


def program(formula):
    return ("```python\nimport openpyxl\nbook = openpyxl.load_workbook('input.xlsx')\n"
            "book.active['B1'] = '%s'\nbook.save('output.xlsx')\n```" % formula)


def workbook(path, tag):
    """A public workbook whose every text is distinctive (``tag``): the sheet title, a header, numbers, a formula and a
    note, so any of it in a request is found."""
    book = openpyxl.Workbook()
    found = book.active
    found.title = "Ledger%s" % tag
    found["A1"] = "Canary %s header" % tag
    for row, value in enumerate((918273.5, 827364.25, 736455.125), 2):
        found.cell(row=row, column=1, value=value)
    found["C2"] = "=ROUND(A2*7.31,2)"
    found["D3"] = "Canary %s note" % tag
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    book.save(path)
    return str(path)


def _delivered():
    book, buffer = openpyxl.Workbook(), io.BytesIO()
    book.active["B1"] = 1
    book.save(buffer)
    return {"status": "available", "output_base64": base64.b64encode(buffer.getvalue()).decode(),
            "reason": "isolated_workbook_generated", "cleanup_confirmed": True}


DELIVERED = _delivered()


def verdict(benchmark, public, private, prediction, *, runtime=None):
    """The fixture verdict in place of the frozen recalculating scorer: a program passes when it writes ``RIGHT``."""
    if prediction.get("status") != "available":
        return {"status": "unknown", "reason": prediction.get("reason"), "metrics": {}}
    passed = RIGHT in prediction["output"]["code"]
    status = "pass" if passed else "fail"
    return {"status": status, "score": float(passed), "reason": "fixture_sheet_verdict", "cleanup_confirmed": True,
            "metrics": {"cases": [{"status": status, "reason": "fixture"}]}}


def containers(monkeypatch, results=()):
    """FakeNative's pre-check; each program execution records its request and returns the next of ``results``, then
    a delivered workbook; the fixture verdict scores. Returns (FakeNative, the executions' requests)."""
    fake, runs, queue = FakeNative().install(monkeypatch), [], list(results)

    def native(request, runtime):
        runs.append(request)
        return queue.pop(0) if queue else dict(DELIVERED)

    monkeypatch.setattr(backends, "_native", native)
    monkeypatch.setattr(backends, "score", verdict)
    return fake, runs


# --------------------------------------------------------------------------------------- the byte-level check
def preview_texts(path, version):
    """Every text (4+ characters) of the frozen preview of the workbook at ``path`` (backends._sheet_preview)."""
    found = set()

    def walk(value):
        if isinstance(value, dict):
            for inner in value.values():
                walk(inner)
        elif isinstance(value, list):
            for inner in value:
                walk(inner)
        elif isinstance(value, str) and len(value) >= 4:
            found.add(value)

    walk(backends._sheet_preview(path, version=version))
    return found


def leaks(requests, path, version):
    """What of the workbook at ``path`` the requests (system, user) carry, byte for byte: the zip signature or member
    names, its bytes in base64, the preview key, any text of its frozen preview (raw or JSON-escaped)."""
    blob = "\n".join(system + "\n" + user for system, user in requests).encode("utf-8")
    raw = Path(path).read_bytes()
    with zipfile.ZipFile(path) as archive:
        members = archive.namelist()
    needles = {"zip signature": b"PK\x03\x04", "base64": base64.b64encode(raw)[:76], "preview key": b"workbook_preview"}
    needles.update({"member " + name: name.encode() for name in members})
    for text in preview_texts(path, version):
        needles["text " + text] = text.encode()
        needles["json " + text] = json.dumps(text, ensure_ascii=False)[1:-1].encode()
    return sorted(name for name, needle in needles.items() if needle in blob)


def assert_no_workbook(requests, paths, version):
    assert requests, "the probe made its call"
    for path in paths:
        found = leaks(requests, path, version)
        assert found == [], "the no-workbook request carries %s of %s" % (found, path)


def public_of(tmp_path, tags=("7f3a", "b2c9")):
    files = [workbook(tmp_path / ("input-%s.xlsx" % tag), tag) for tag in tags]
    return {"instruction": "Write the ledger total into B1.", "input_files": files, "answer_position": "B1"}


def probe(public, runtime, replies, *, shortcut=solver.NO_WORKBOOK, package=EMPTY, worker=None):
    script = Script(list(replies))
    found = solver.solve("spreadsheetbench", public, CARD, package, script, runtime=runtime, worker=worker,
                         shortcut=shortcut)
    return found, script


# ------------------------------------------------------------------------------------------ the shell (solver)
def test_c1_2_the_no_workbook_request_holds_no_workbook_byte_or_preview_text(tmp_path, monkeypatch):
    FakeNative().install(monkeypatch)
    public = public_of(tmp_path)
    for runtime in (SHEET_RUNTIME, HISTORICAL):
        version = runtime.get("spreadsheet_preview_version")
        shown, probe_call = probe(public, runtime, [program(RIGHT)])
        normal, normal_call = probe(public, runtime, [program(RIGHT)], shortcut=None)
        assert_no_workbook(probe_call.requests, public["input_files"], version)
        # sensitivity: the same check finds every preview text of the first workbook in the normal request
        found = leaks(normal_call.requests, public["input_files"][0], version)
        assert "preview key" in found and {"text " + t for t in preview_texts(public["input_files"][0], version)} <= \
            set(found)
        # the only difference between the two requests is the preview: same system prompt, same keys in order
        (system, user), (normal_system, normal_user) = probe_call.requests[0], normal_call.requests[0]
        assert system == normal_system and list(json.loads(user)) == [
            "instruction", "input_path", "required_output_path", "required_answer_position"]
        assert json.loads(user) == {k: v for k, v in json.loads(normal_user).items() if k != "workbook_preview"}
        # the mode changes the request and nothing of the prediction but the shell record's ``shortcut``
        assert {k: v for k, v in shown.items() if k != "shell"} == {k: v for k, v in normal.items() if k != "shell"}
        assert shown["shell"]["shortcut"] == "no_workbook" and "shortcut" not in normal["shell"]
        assert verified(shown["shell"], "shell")["route"]["enabled"] == []
    # the same refusals as the normal mode, before any call
    for broken in ({**SHEET_RUNTIME, "spreadsheet_preview_version": "v0"}, {**SHEET_RUNTIME, "prompt_layout": "x"}):
        refused, call = probe(public, broken, [program(RIGHT)])
        normal, _ = probe(public, broken, [program(RIGHT)], shortcut=None)
        assert refused["status"] == "unknown" and refused["reason"] == normal["reason"] and call.requests == []


def test_c1_2_the_program_still_runs_on_the_real_input_files(tmp_path, monkeypatch):
    fake, runs = containers(monkeypatch)
    public = public_of(tmp_path)
    shown, call = probe(public, SHEET_RUNTIME, [program(RIGHT)])
    assert shown["status"] == "available" and shown["reason"] == "generated_once_executed_per_public_case"
    # one execution per public case, each on the bytes of its own real input file, of the delivered program
    assert [base64.b64decode(run["input_base64"]) for run in runs] == [Path(p).read_bytes()
                                                                        for p in public["input_files"]]
    assert all(run["code"] in program(RIGHT) for run in runs) and len(shown["output"]["cases"]) == 2
    # the pre-check ran once on the first real input; its report stays host-side (never in a request)
    assert [(p["workbook"], p["answer_position"]) for p in fake.prechecks] == [(public["input_files"][0], "B1")]
    assert shown["shell"]["precheck"]["status"] == "ok" and "answer_cells" not in call.requests[0][1]


def test_c1_2_the_mode_is_refused_off_spreadsheetbench_with_procedures_and_unknown(tmp_path, monkeypatch):
    FakeNative().install(monkeypatch)
    public = public_of(tmp_path)
    qa = {"question": "What is 1 + 1?", "context": ["Two."]}
    for bench, item, mode in (("officeqa", qa, "no_workbook"), ("spreadsheetbench", public, "no_table")):
        call = Script(["<answer>2</answer>"])
        with pytest.raises(ValueError, match="one shortcut mode"):
            solver.solve(bench, item, CARD, EMPTY, call, runtime={}, shortcut=mode)
        assert call.requests == []
    # a procedure for the bench could read the mounted workbook or the pre-check report: only the card arm probes
    feedback = procedure("fx-sheet", ("applies", "sheet_feedback"), origin="spreadsheetbench",
                         requests_second_call=True)
    worker = FakeSandbox()
    with pytest.raises(ValueError, match="card arm"):
        probe(public, SHEET_RUNTIME, [program(RIGHT)], package=Package((feedback,), "fixture", FIXTURE),
              worker=worker)
    assert worker.package is None and worker.calls == []


# --------------------------------------------------------------------------------------------------- the cell
class Answers:
    """The solver: the k-th call on an instruction gets the k-th program planned for it; every request is kept."""

    def __init__(self, plan):
        self.plan, self.requests = {key: list(value) for key, value in plan.items()}, []

    def call(self, system, user):
        self.requests.append((system, user))
        reply = program(self.plan[json.loads(user)["instruction"]].pop(0))
        return {"ok": True, "response": reply, "finish_reason": "stop", "error_type": None, "usage": dict(USAGE),
                "attempts": [{"status": 200}]}


def context_of(root, client):
    endpoint = Endpoint(client, model="glm-5.3", max_tokens=100, slots=Slots(root / "slots", "glm-5.3", 2),
                        sleep=lambda _: None)
    return Context(attempt=root / "unit" / "attempt-1", endpoint=endpoint, runtime=RUNTIMES,
                   cards={bench: CARD for bench in BENCHES}, native=Slots(root / "slots", "spreadsheet-native", 1),
                   episodes=Slots(root / "slots", "alfworld-episode", 1), worker=lambda bench: FakeSandbox(),
                   evidence=FIXTURE)


def generated(tmp_path, count):
    """A generated SpreadsheetBench set of ``count`` items, each with its own instruction and real workbooks."""
    found = []
    for n in range(count):
        tag = "g%02dx" % n
        files = [workbook(tmp_path / "gen" / ("input-%d.xlsx" % n), tag)]
        public = {"instruction": "Write the ledger total of block %d into B1." % n, "input_files": files,
                  "answer_position": "B1"}
        found.append(generated_item(evidence=FIXTURE, generator=GENERATOR, number=n, bench="spreadsheetbench",
                                    family="spreadsheetbench.formula_edit", source_item="fx-spreadsheetbench-00",
                                    material_id="m", public=public,
                                    private_fields={"test_files": [workbook(tmp_path / "gen" / ("answer-%d.xlsx" % n),
                                                                            tag)], "answer_position": "B1"},
                                    truth={"kind": "recalc_formula", "checked_by": sheet.CHECKED_BY},
                                    set_name="G_self", seed=1))
    return found


def probe_job(variant, run, unit, *, mode=True):
    """One probe cell as step.py builds it once ticket PR-C12-1 is in: the card arm on the variant, the cell carrying
    ``examiner.probe_mode(variant)`` as ``shortcut``."""
    cell = {"id": cell_id(unit, "C", variant["id"], run), "unit": unit, "arm": "C", "benchmark": "spreadsheetbench",
            "task_id": variant["id"], "run": run}
    if mode:
        cell["shortcut"] = examiner.probe_mode(variant)
    return cell, {"public": variant["public"], "private": variant["private"]}


def test_c1_2_a_probe_cell_hands_its_mode_to_the_shell_and_its_record_states_it(tmp_path, monkeypatch):
    fake, runs = containers(monkeypatch, [TIMEOUT])  # the first execution times out: the cell re-executes
    item = generated(tmp_path, 1)[0]
    variant = examiner.shortcut_variant(item)
    client = Answers({item["public"]["instruction"]: [RIGHT, RIGHT]})
    context = context_of(tmp_path, client)
    unit = "G/s1-spreadsheetbench/generate/shortcut"
    cell, task = probe_job(variant, 0, unit)
    found = run_cell(context, cell, task, Arm("card", EMPTY), store=TrainingStore(context.attempt))
    assert found["cell"]["shortcut"] == "no_workbook" and found["shortcut"] == "no_workbook"
    # the re-execution replayed the stored reply on the same no-workbook request: no P3, one model call
    assert found["stop"] is None and found["remedies"] == {"reexecute": 1} and found["final"]["token"] == "pass"
    assert found["fault_kinds"] == {} and len(client.requests) == 1 and len(fake.prechecks) == 1
    for attempt in found["attempts"]:
        stored = read_json(context.attempt / "artifacts" / (attempt["prediction"]["sha256"] + ".json"))
        assert stored["shell"]["shortcut"] == "no_workbook"
    assert_no_workbook(client.requests, item["public"]["input_files"], "public-formula-preview-v1")
    trajectory = read_json(context.attempt / "trajectories" / (cell["id"] + ".json"))
    assert "workbook_preview" not in trajectory["calls"][0]["user"]
    assert [base64.b64decode(r["input_base64"]) for r in runs] == [Path(item["public"]["input_files"][0]).read_bytes()
                                                                   ] * 2
    # the same item as a plain cell shows the workbook, and its record has no mode
    plain, task = probe_job(variant, 1, unit, mode=False)
    client.plan[item["public"]["instruction"]] = [WRONG]
    normal = run_cell(context, plain, task, Arm("card", EMPTY), store=TrainingStore(context.attempt))
    assert "shortcut" not in normal and "shortcut" not in normal["cell"] and normal["final"]["token"] == "fail"
    assert "preview key" in leaks(client.requests[1:], item["public"]["input_files"][0], "public-formula-preview-v1")


# --------------------------------------------------------------------------------------------------- the gate
def band_cells(items):
    """The parent's band probe on the set, one run per item: half pass (in the band)."""
    tokens = ["pass" if n % 2 else "fail" for n in range(len(items))]
    return [[record("cell", FIXTURE, {"cell": {"id": "S:%s:0" % item["id"], "unit": "G/s1-spreadsheetbench/band",
                                               "arm": "S", "benchmark": "spreadsheetbench", "task_id": item["id"],
                                               "run": 0}, "final": {"token": token}, "judge": {"v2": {"token": token}}})
             for token, item in zip(tokens, items)]]


def probe_cells(tmp_path, monkeypatch, items, plan, *, mode=True):
    """The card arm twice on the shortcut variants of the set's probe items (examiner.probe_items), run sequentially
    through cells.run_cell; ``plan``: {item number: [formula of run 0, formula of run 1]}."""
    containers(monkeypatch)
    variants = [examiner.shortcut_variant(item) for item in examiner.probe_items(items, generator=GENERATOR,
                                                                                purpose="shortcut")]
    client = Answers({items[n]["public"]["instruction"]: formulas for n, formulas in plan.items()})
    context = context_of(tmp_path, client)
    found = []
    for variant in variants:
        for run in (0, 1):
            cell, task = probe_job(variant, run, "G/s1-spreadsheetbench/generate/shortcut", mode=mode)
            found.append(run_cell(context, cell, task, Arm("card", EMPTY), store=TrainingStore(context.attempt)))
    return found, client


def test_c1_2_the_shortcut_gate_reaches_its_verdict_on_cells_run_without_the_workbook(tmp_path, monkeypatch):
    items = generated(tmp_path, 4)
    ids = [item["id"] for item in items]
    bundle = examiner.Generated(GENERATOR, "spreadsheetbench", ({"items": items, "made": 4, "dropped": {},
                                                                 "status": "made", "material": "m",
                                                                 "family": "spreadsheetbench.formula_edit"},))
    # one item of four right in both runs without its workbook: dropped, 25 % is allowed, the set is admitted
    kept, client = probe_cells(tmp_path / "a", monkeypatch, items, {0: [RIGHT, RIGHT], 1: [RIGHT, WRONG],
                                                                    2: [WRONG, WRONG], 3: [WRONG, RIGHT]})
    assert all(c["shortcut"] == "no_workbook" and c["stop"] is None for c in kept) and len(client.requests) == 8
    for item in items:
        assert_no_workbook(client.requests, item["public"]["input_files"], "public-formula-preview-v1")
    cut = examiner.shortcut(kept, ids, bench="spreadsheetbench")
    assert (cut["probe"], cut["probe_items"], cut["dropped"], cut["flagged_share"], cut["used"]) == (
        "no_workbook", 4, [ids[0]], 0.25, True)
    monkeypatch.setattr(examiner, "BAND_PROBE_ITEMS", 4)  # the four-item fixture's band probe (Codex finding #9)
    gated = verified(examiner.gates(bundle, {"band": band_cells(items), "shortcut": kept}, evidence=FIXTURE),
                     "generator-gates")
    assert gated["admitted"] and gated["failed"] == [] and gated["kept"] == ids[1:]
    assert gated["shortcut"]["probe"] == "no_workbook" and gated["labels"]["truth_by_fixed_code"]
    # two of four: above 25 %, the whole set is rejected
    rejected, _ = probe_cells(tmp_path / "b", monkeypatch, items, {0: [RIGHT, RIGHT], 1: [RIGHT, RIGHT],
                                                                   2: [WRONG, WRONG], 3: [WRONG, RIGHT]})
    gated = examiner.gates(bundle, {"band": band_cells(items), "shortcut": rejected}, evidence=FIXTURE)
    assert not gated["admitted"] and gated["failed"] == ["shortcut"] and gated["kept"] == []
    assert gated["shortcut"]["reason"] == "dropped_share_above_maximum" and gated["shortcut"]["flagged_share"] == 0.5
    # probe cells that saw the workbook (no mode asked) measure nothing: the gate refuses them
    seen, client = probe_cells(tmp_path / "c", monkeypatch, items, {n: [WRONG, WRONG] for n in range(4)}, mode=False)
    assert "preview key" in leaks(client.requests, items[0]["public"]["input_files"][0], "public-formula-preview-v1")
    with pytest.raises(ValueError, match="probe mode"):
        examiner.gates(bundle, {"band": band_cells(items), "shortcut": seen}, evidence=FIXTURE)


# ---------------------------------------------------------------------------------------- break-the-code checks
def test_c1_2_a_mutation_that_shows_the_preview_in_the_probe_is_caught(tmp_path, monkeypatch):
    """Two leaks a regression could make: the view ignores the mode (solver.py), or the cell runner forgets to hand
    the mode to the shell (cells.py). The byte-level check fails on the first; the gate refuses the second's cell."""
    public = public_of(tmp_path)
    frozen = solver._sheet_view
    with monkeypatch.context() as patched:
        FakeNative().install(patched)
        patched.setattr(solver, "_sheet_view", lambda view, runtime, shortcut=None: frozen(view, runtime))
        _, leaked = probe(public, SHEET_RUNTIME, [program(RIGHT)])
        with pytest.raises(AssertionError, match="no-workbook request carries"):
            assert_no_workbook(leaked.requests, public["input_files"], "public-formula-preview-v1")
    original = cells._shell
    monkeypatch.setattr(cells, "_shell", lambda context, cell, task, arm, call, **extra: original(
        context, {k: v for k, v in cell.items() if k != "shortcut"}, task, arm, call, **extra))
    items = generated(tmp_path, 2)
    forgot, client = probe_cells(tmp_path / "f", monkeypatch, items, {n: [WRONG, WRONG] for n in range(2)})
    assert all(c["cell"]["shortcut"] == "no_workbook" and c["shortcut"] is None for c in forgot)
    with pytest.raises(AssertionError, match="no-workbook request carries"):
        assert_no_workbook(client.requests, items[0]["public"]["input_files"], "public-formula-preview-v1")
    with pytest.raises(ValueError, match="probe mode"):
        examiner.shortcut(forgot, [item["id"] for item in items], bench="spreadsheetbench")
