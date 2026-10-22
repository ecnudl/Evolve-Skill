"""Codex findings #1 and #3 of 2026-10-22 (docs/handoff/execskill-codex-review-code-20261022.md; registration §2.5-§2.6,
§8.1/F16; registrar fixer-1). #1: a SpreadsheetBench test read routes (``test_plan``) and measures placebo lengths
(``placebo_arm``) with each item's PUBLIC input workbook mounted, as training does (``step._item_workers``), so a
workbook-dependent procedure dispatches real F/P_F/T_F cells instead of a silent structural zero; a reference workbook
is never mounted; P_F's per-item donor seed is a valid tag (``yoke_seed``). #3: the test-side reference qualification
deletes its reference-derived scorer artifacts on every exit
(complete, pause, exception) once its scoring workers drained, records the deletion, sweeps an attempt a killed process
left before any retry and keeps sanitized results only. Offline and deterministic: fixture workbooks
(tests/fixtures/execskill/items.py), a stateless fake solver behind the frozen Endpoint, FakeSandbox workers whose hooks
read the mount through the worker's own ``public_workbook`` helper, the fake native runs and a scripted frozen scorer;
never a test pool, no model call, no container."""
from __future__ import annotations

import base64
import hashlib
import itertools
import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import donors, evaluation
from skillopt.execskill.cells import Arm, Context, Pause
from skillopt.execskill.package import empty, with_
from skillopt.execskill.protocol import BENCHES, NOTES_KEY, TEST_ARMS, verified
from skillopt.execskill.sandbox import worker as sandbox_worker
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import FakeNative, FakeSandbox, procedure
from tests.fixtures.execskill.items import officeqa_items, spreadsheetbench_items

EVIDENCE = "engineering_fixture"
BENCH, CHAIN, RUN = "spreadsheetbench", "D", "fixture-run"
UNIT = "%s/test/%s" % (CHAIN, BENCH)
CARD_TEXT = "Read the workbook preview before writing the program."
INSTRUCTION = "Put the sum of A1:A5 into B1."  # the fixture items' public instruction (a canary of the read)
USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
PROGRAM = ("```python\nimport openpyxl\nbook = openpyxl.load_workbook('input.xlsx')\n"
           "book.active['B1'] = '=SUM(A1:A5)'\nbook.save('output.xlsx')\n```")
PASSED = {"status": "pass", "reason": "qualified_numeric_recalculation_hard_all_cases", "cleanup_confirmed": True,
          "metrics": {"cases": [{"status": "pass", "reason": "cell_values_match"}]}}
CONFIGURATION = {"status": "fail", "reason": "missing_public_workbook", "metrics": {"cases": []}}
SHEET = procedure("p-spreadsheetbench-1-1", ("applies", "before_call"), header="Column notes.", evidence=EVIDENCE)
CARD = empty(step="pilot/s1-spreadsheetbench/t1", evidence=EVIDENCE)
FINAL = with_(CARD, step="pilot/s1-spreadsheetbench/t2", add=[SHEET])
DONOR = "Donor note: the totals go below column A."
NO_MOUNT = "/nonexistent-execskill-input/input.xlsx"
QUALIFICATION = "spreadsheetbench-qualification"
_PATCH = threading.Lock()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def column_a():
    """Column A of the mounted workbook through the worker's own helper (sandbox/worker.py ``public_workbook``):
    FileNotFoundError without a mount, exactly as in the sandbox."""
    cells = sandbox_worker.public_workbook()["sheets"][0]["cells"]
    return [cells["A%d" % row]["value"] for row in range(1, 6)]


# a workbook-dependent predicate (fires when A1 is odd) and a note read from the workbook
HOOKS = {SHEET.id: {"applies": lambda view: column_a()[0] % 2 == 1,
                    "before_call": lambda view, state: {"facts": ["Column A runs from %d to %d." % (
                        column_a()[0], column_a()[-1])]}}}


def firing(items):
    """The items whose public workbook makes the predicate fire (A1 = n + 1 odd: the even-numbered fixtures)."""
    return {item["task_id"] for item in items if int(item["task_id"].rsplit("-", 1)[1]) % 2 == 0}


class WorkbookSandbox(FakeSandbox):
    """A FakeSandbox whose hooks see its /input mount: during a call the worker helper's ``INPUT_WORKBOOK`` points at
    the mounted ``input.xlsx`` (at a path that does not exist without a mount). Every start is recorded in ``mounts``:
    origin, item (route workers only), the directory, its listing and the sha256 of ``input.xlsx``."""

    def __init__(self, hooks, mounts, origin, item=None):
        super().__init__(hooks)
        self.mounts, self.origin, self.item, self.directory = mounts, origin, item, None

    def start(self, package, *, kind, inputs_dir=None):
        super().start(package, kind=kind, inputs_dir=inputs_dir)
        self.directory = None if inputs_dir is None else Path(inputs_dir)
        mounted = self.directory is not None
        self.mounts.append({"origin": self.origin, "item": self.item, "directory": self.directory,
                            "listing": sorted(p.name for p in self.directory.iterdir()) if mounted else None,
                            "sha256": sha(self.directory / "input.xlsx") if mounted else None})
        return self

    def call(self, proc_id, fn, args, *, timeout_s):
        with _PATCH:
            saved = sandbox_worker.INPUT_WORKBOOK
            sandbox_worker.INPUT_WORKBOOK = str(self.directory / "input.xlsx") if self.directory else NO_MOUNT
            try:
                return super().call(proc_id, fn, args, timeout_s=timeout_s)
            finally:
                sandbox_worker.INPUT_WORKBOOK = saved


def route_workers(mounts, hooks=HOOKS):
    """The read's base factory (``evaluation._route_worker``'s signature): ``inputs_dir`` is the mount."""
    @contextmanager
    def factory(package, item, inputs_dir=None):
        worker = WorkbookSandbox(hooks, mounts, "route", item).start(package, kind="cell", inputs_dir=inputs_dir)
        try:
            yield worker
        finally:
            worker.close()
    return factory


def donor_corpus():
    """The sealed donor corpus of the round that accepted SHEET: three parent run-slice trajectories (training side,
    no workbook needed: the donor note is fixed)."""
    trajectories = [{"cell": "pilot/s1-spreadsheetbench/run/S/run-%02d/0" % k, "task_id": "run-%02d" % k,
                     "bench": BENCH, "arm_kind": "parent", "shell": {"precheck": None},
                     "calls": [{"purpose": "first", "user": json.dumps({"instruction": "Fill B%d." % k})}]}
                    for k in range(3)]
    hooks = {SHEET.id: {"before_call": lambda view, state: {"facts": [DONOR]}}}

    @contextmanager
    def workers(package, item):
        worker = FakeSandbox(hooks).start(package, kind="cell")
        try:
            yield worker
        finally:
            worker.close()

    return donors.donor_corpus(FINAL, CARD, trajectories, workers)


def consent_value(**changes):
    value = {"test_evaluation": True, "sheet_test_qualification": True, "multi_arm_arms": list(TEST_ARMS),
             "by": "owner", "date": "2026-10-22", "note": "Read the five test sets once."}
    value.update(changes)
    return value


def sheet_panel(items):
    def panel(pinned, bench, *, access):
        assert bench == BENCH and access.unit == UNIT
        tasks = [{"task_id": i["task_id"], "public": i["public"], "private": i["private"]} for i in items]
        return tasks, {"panel_hash": digest(tasks), "excluded_without_pages": 0, "source_files": None}
    return panel


def reference_score(seen=None, *, script=None):
    """The frozen scorer's shape, scripted. A qualification scoring (the reference workbook as the answer) writes what
    the v7 adapter keeps under its scoring directory -- the recalculated reference workbook and a result -- and passes;
    ``script(task_id, scoring)`` runs first (it may wait: a slow scoring) and returns None, another score, or an
    exception raised once the artifacts are written (a crash). A cell's scoring passes."""
    def score(benchmark, public, private, prediction, *, runtime=None):
        if prediction.get("reason") != "reference_as_answer":
            return json.loads(json.dumps(PASSED))
        context = runtime["_score_context"]
        request = context["request"]
        found = script(request["task_id"], request["scoring"]) if script is not None else None
        directory = Path(context["artifact_dir"])
        (directory / "recalculations").mkdir(parents=True, exist_ok=True)
        raw = base64.b64decode(prediction["output"]["cases"][0]["output_base64"])
        (directory / "recalculations" / "0.xlsx").write_bytes(raw)
        write_json(directory / "result.json", {"reference_sha256": hashlib.sha256(raw).hexdigest()})
        if seen is not None:
            seen.append((request["task_id"], request["scoring"]))
        if isinstance(found, BaseException):
            raise found
        return json.loads(json.dumps(found or PASSED))
    return score


class SheetClient:
    """Stateless: every request gets the same program; the request views are kept."""

    def __init__(self):
        self.views, self.lock = [], threading.Lock()

    def call(self, system, user):
        with self.lock:
            self.views.append(json.loads(user))
        return {"ok": True, "response": PROGRAM, "finish_reason": "stop", "error_type": None, "usage": dict(USAGE),
                "attempts": [{"status": 200}]}


def read(tmp_path, monkeypatch, items, *, canaries=()):
    """One SpreadsheetBench read unit of chain D through ``evaluation.evaluate`` (qualification included)."""
    root = tmp_path / "run-root"
    shared = root / "shared"
    write_json(shared / "consent.json", consent_value())
    FakeNative().install(monkeypatch)
    monkeypatch.setattr(backends, "score", reference_score())
    client, mounts = SheetClient(), []
    endpoint = Endpoint(client, model="deepseek-v4.1-flash-1017", max_tokens=100,
                        slots=Slots(tmp_path / "slots", "deepseek", 2), sleep=lambda _: None)
    unit_root = root / CHAIN / "test" / BENCH
    ticks = itertools.count()
    context = Context(attempt=unit_root / "attempt-1", endpoint=endpoint, runtime=RUNTIME,
                      cards={b: CARD_TEXT for b in BENCHES}, native=Slots(tmp_path / "slots", "spreadsheet-native", 1),
                      episodes=Slots(tmp_path / "slots", "alfworld-episode", 1),
                      worker=lambda bench: WorkbookSandbox(HOOKS, mounts, "cell"), evidence=EVIDENCE,
                      clock=lambda: float(next(ticks)))
    workers = route_workers(mounts)
    arms = {"F": Arm("candidate", FINAL), "C": Arm("card", CARD),
            "P_F": evaluation.placebo_arm(FINAL, {SHEET.id: donor_corpus()}, bench=BENCH, unit=UNIT,
                                          runtime=RUNTIME[BENCH], workers=workers),
            "T_F": Arm("text", FINAL, text={SHEET.id: "Names the first and last values of column A."})}
    found = evaluation.evaluate(unit_root, run=RUN, shared=shared, pinned=None, chain=CHAIN, bench=BENCH, arms=arms,
                                context=context, workers=2, route_workers=workers, canaries=list(canaries),
                                panel=sheet_panel(items))
    return root, unit_root, found, client, mounts


# ------------------------------------------------------------------------------------------- Codex finding #1
def test_codex1_a_workbook_dependent_predicate_dispatches_real_f_cells_on_spreadsheetbench_test_items(tmp_path,
                                                                                                    monkeypatch):
    items = spreadsheetbench_items(tmp_path / "sb", 6)
    fire = firing(items)
    root, unit_root, found, client, mounts = read(tmp_path, monkeypatch, items,
                                                  canaries=[evaluation.canary(INSTRUCTION)])
    assert verified(found, "evaluation")["status"] == "complete"
    assert len(fire) == 3 and found["structural_zero"] == len(items) - len(fire)  # never all six
    attempt = unit_root / found["attempt"]
    by_key = {(c["cell"]["arm"], c["cell"]["task_id"]): c for c in (verified(read_json(p), "evaluation-cell")
                                                                    for p in (attempt / "cells").glob("*.json"))}
    for item in (i["task_id"] for i in items):
        for arm in ("F", "P_F", "T_F"):
            cell = by_key[(arm, item)]
            if item in fire:  # real cells: F's procedure enabled on the item's own workbook
                assert cell["shared_with"] is None and cell["enabled"] == [SHEET.id] and len(cell["calls"]) == 1
            else:
                assert cell["shared_with"] == by_key[("C", item)]["cell"]["id"] and cell["calls"] == []
    # the notes read the mounted workbook: F's real note, and P_F's donor note at the length measured with the mount
    notes = [view.get(NOTES_KEY, "") for view in client.views]
    assert sum("Column A runs from" in note for note in notes) == len(fire)
    assert sum(DONOR in note for note in notes) == len(fire)
    # every routing and placebo-length worker mounted its item's PUBLIC workbook alone; no reference was mounted; the
    # isolated directories are gone
    public = {i["task_id"]: sha(i["public"]["input_files"][0]) for i in items}
    references = {sha(i["private"]["test_files"][0]) for i in items}
    route = [m for m in mounts if m["origin"] == "route"]
    assert len(route) == 2 * len(items)  # the plan's routing and the placebo lengths, once per item each
    assert all(m["listing"] == ["input.xlsx"] and m["sha256"] == public[m["item"]] for m in route)
    assert all(m["listing"] == ["input.xlsx"] and m["sha256"] in public.values() for m in mounts)
    assert not {m["sha256"] for m in mounts} & references
    assert not any(m["directory"].exists() for m in mounts)
    # the test qualification kept no reference-derived artifact (Codex finding #3) and the read's scan stayed clean
    qualification = root / "shared" / "test" / QUALIFICATION / "attempt-1"
    deleted = verified(read_json(qualification / evaluation.QUALIFICATION_DELETED), "transient-deletion")
    assert deleted["when"] == "complete" and deleted["files"] == 2 * 2 * len(items) and deleted["entries"] == [
        "host_only"]
    assert not (qualification / "host_only").exists()
    assert verified(read_json(attempt / "canary_scan.json"), "canary-scan")["hits"] == 0


def test_codex1_the_placebo_lengths_are_measured_with_the_items_public_workbook_mounted(tmp_path):
    items = spreadsheetbench_items(tmp_path / "sb", 2)
    corpora, view_runtime = {SHEET.id: donor_corpus()}, RUNTIME[BENCH]

    def shams(workers):
        arm = evaluation.placebo_arm(FINAL, corpora, bench=BENCH, unit=UNIT, runtime=view_runtime, workers=workers)
        out = {}
        for item in items:
            cell = {"id": "cell-%s" % item["task_id"], "task_id": item["task_id"]}
            chosen = arm(cell, {"public": item["public"], "private": item["private"]})
            assert chosen.kind == "placebo_y"
            out[item["task_id"]] = chosen.placebo["procedures"][SHEET.id]["before_call"]
        return out

    mounts = []
    found = shams(route_workers(mounts))
    assert all(DONOR in " ".join(fields.get("facts", [])) for fields in found.values())  # a real length on each item
    assert [(m["item"], m["listing"], m["sha256"]) for m in mounts] == [
        (i["task_id"], ["input.xlsx"], sha(i["public"]["input_files"][0])) for i in items]
    assert not any(m["directory"].exists() for m in mounts)

    @contextmanager
    def unmounted(package, item, inputs_dir=None):  # control: the same factory ignoring the mount
        with route_workers([])(package, item) as worker:
            yield worker

    assert all(fields == {} for fields in shams(unmounted).values())  # length 0: the sham shows nothing


def test_codex1_the_reference_workbook_is_never_mounted(tmp_path):
    item = spreadsheetbench_items(tmp_path / "sb", 1)[0]
    public, reference = item["public"]["input_files"][0], item["private"]["test_files"][0]
    tasks = {item["task_id"]: {"public": item["public"], "private": item["private"]}}
    assert evaluation.public_inputs(BENCH, tasks) == {item["task_id"]: public}
    assert evaluation.public_inputs("officeqa", {i["task_id"]: i for i in officeqa_items(2)}) == {}
    for exposed in (reference, str(Path(reference).parent) + "/./" + Path(reference).name):
        bad = {"x": {"public": {**item["public"], "input_files": [exposed]}, "private": item["private"]}}
        with pytest.raises(ValueError, match="never mounted"):
            evaluation.public_inputs(BENCH, bad)
    seen = []

    @contextmanager
    def base(package, item_id, inputs_dir=None):
        seen.append((item_id, inputs_dir, sorted(p.name for p in inputs_dir.iterdir()),
                     sha(inputs_dir / "input.xlsx")))
        yield "worker"

    mounted = evaluation.mounting(base, evaluation.public_inputs(BENCH, tasks))
    with mounted(FINAL, item["task_id"]) as worker:
        assert worker == "worker"
    (item_id, directory, listing, digest_), = seen
    assert item_id == item["task_id"] and listing == ["input.xlsx"] and digest_ == sha(public) != sha(reference)
    assert not directory.exists()
    with pytest.raises(ValueError, match="public workbook"):
        with mounted(FINAL, "another-item"):
            pass
    assert evaluation.mounting(base, {}) is base  # the other benches: the factory itself, no mount


def test_the_p_f_donor_seed_is_a_valid_tag_for_any_item_id():
    """``placebo_arm`` seeded ``donors.pair`` with ``"<unit>:<item>"``, which ``protocol.yoke_tag`` refuses (no ':' in
    a tag part): every P_F arm raised at its first cell. ``yoke_seed`` is a valid tag part whatever the item id."""
    from skillopt.execskill.protocol import yoke_tag

    with pytest.raises(ValueError, match="short name"):
        yoke_tag("%s:%s" % (UNIT, "fx-spreadsheetbench-00"))
    seeds = {evaluation.yoke_seed(UNIT, item) for item in ("fx-spreadsheetbench-00", "cat:7", "a b", "x" * 300)}
    assert len(seeds) == 4 and all(yoke_tag(seed).startswith("execskill-v1:yoke:%s/" % UNIT) for seed in seeds)
    assert evaluation.yoke_seed(UNIT, "cat:7") == evaluation.yoke_seed(UNIT, "cat:7")  # deterministic


# ------------------------------------------------------------------------------------------- Codex finding #3
def qualification_root(tmp_path):
    return tmp_path / "shared" / "test" / QUALIFICATION


def sheet_tasks(tmp_path, monkeypatch, items, *, score, workers=2):
    shared = tmp_path / "shared"
    if not (shared / "consent.json").exists():
        write_json(shared / "consent.json", consent_value())
    monkeypatch.setattr(backends, "score", score)
    return evaluation.test_tasks(shared, None, BENCH, UNIT, run=RUN, runtime=RUNTIME[BENCH],
                                 native=Slots(tmp_path / "slots", "spreadsheet-native", 2), workers=workers,
                                 evidence=EVIDENCE, panel=sheet_panel(items))


def kept(attempt):
    """The attempt's files (relative) and whether any of them is a workbook (zip archive)."""
    files = sorted(str(p.relative_to(attempt)) for p in attempt.rglob("*") if p.is_file())
    return files, any(p.read_bytes()[:4] == b"PK\x03\x04" for p in attempt.rglob("*") if p.is_file())


def manifest(attempt, names):
    """``_delete_entries``' manifest hash of the files below ``names``, computed before they go."""
    files = []
    for name in sorted(names):
        entry = attempt / name
        for path in sorted(p for p in entry.rglob("*") if p.is_file()) if entry.is_dir() else [entry]:
            files.append({"path": str(path.relative_to(attempt)), "sha256": sha(path)})
    return len(files), digest(files)


def test_codex3_a_completed_test_qualification_keeps_sanitized_results_only(tmp_path, monkeypatch):
    items = spreadsheetbench_items(tmp_path / "sb", 3)
    seen = []
    tasks = sheet_tasks(tmp_path, monkeypatch, items, score=reference_score(seen))
    assert [t["task_id"] for t in tasks] == [i["task_id"] for i in items] and len(seen) == 6
    attempt = qualification_root(tmp_path) / "attempt-1"
    files, workbook = kept(attempt)
    assert not workbook and not (attempt / "host_only").exists()
    assert {f.split("/")[0] for f in files} == {"qualification.json", "scores", evaluation.QUALIFICATION_DELETED}
    deleted = verified(read_json(attempt / evaluation.QUALIFICATION_DELETED), "transient-deletion")
    assert (deleted["when"], deleted["entries"], deleted["files"]) == ("complete", ["host_only"], 2 * 6)
    # the score records are statuses, reasons and hashes: no workbook bytes, no reference value
    for path in (attempt / "scores").glob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "output_base64" not in text and "UEsDB" not in text
        assert verified(json.loads(text), "sheet-qualification-score")["score"]["status"] == "pass"
    # a second read (the other chain) only loads the pointer: nothing is swept or scored again
    before = kept(attempt)
    assert [t["task_id"] for t in sheet_tasks(tmp_path, monkeypatch, items, score=reference_score(seen))] == [
        i["task_id"] for i in items]
    assert len(seen) == 6 and kept(attempt) == before


@pytest.mark.parametrize("failure", ["configuration", "exception"])
def test_codex3_a_failed_test_qualification_deletes_its_reference_artifacts_after_the_workers_drain(tmp_path,
                                                                                                  monkeypatch,
                                                                                                  failure):
    """Scoring 0 of the first item fails at once (the frozen ``_check``'s configuration pause, or a crash) after its
    scorer wrote artifacts; scoring 1 runs alongside and writes its artifacts only later. The cleanup comes after the
    drain, so both are deleted and recorded, and nothing is left."""
    items = spreadsheetbench_items(tmp_path / "sb", 2)
    first, running = items[0]["task_id"], threading.Event()

    def script(task_id, scoring):
        if task_id == first and scoring == 0:
            assert running.wait(10), "the other scoring never started"
            return OSError("scorer crashed") if failure == "exception" else CONFIGURATION
        running.set()
        time.sleep(0.3)  # still running when the other scoring fails: its artifacts come later
        return None

    expected = Pause if failure == "configuration" else OSError
    with pytest.raises(expected):
        sheet_tasks(tmp_path, monkeypatch, items, score=reference_score(script=script))
    attempt = qualification_root(tmp_path) / "attempt-1"
    status = verified(read_json(attempt / "status.json"), "unit-status")
    assert status["status"] == "paused" and status["kind"] == failure
    assert status["reason"] == ("missing_public_workbook" if failure == "configuration" else "OSError")
    deleted = verified(read_json(attempt / evaluation.QUALIFICATION_DELETED), "transient-deletion")
    assert deleted["when"] == ("paused" if failure == "configuration" else "exception")
    assert deleted["entries"] == ["host_only"] and deleted["files"] == 2 * 2  # both scorings' artifacts
    files, workbook = kept(attempt)
    assert not workbook and not (attempt / "host_only").exists()
    assert {f.split("/")[0] for f in files} <= evaluation.QUALIFICATION_KEPT
    assert not (tmp_path / "shared" / "test" / (QUALIFICATION + ".json")).exists()


def test_codex3_an_interrupted_test_qualification_is_swept_before_any_retry(tmp_path, monkeypatch):
    items = spreadsheetbench_items(tmp_path / "sb", 2)
    base = qualification_root(tmp_path)
    crashed = base / "attempt-1"  # what a killed process left: scorer artifacts, a score, an unfinished write
    artifacts = crashed / "host_only" / "scorer_artifacts" / ("a" * 64)
    (artifacts / "recalculations").mkdir(parents=True)
    (artifacts / "recalculations" / "0.xlsx").write_bytes(Path(items[0]["private"]["test_files"][0]).read_bytes())
    write_json(artifacts / "started.json", {"binding_hash": "b" * 64})
    write_json(crashed / "scores" / ("a" * 64 + ".json"), {"status": "pass"})
    (crashed / ".pending-x1.json").write_text("{", encoding="utf-8")
    count, sealed = manifest(crashed, [".pending-x1.json", "host_only"])
    seen = []
    with pytest.raises(Pause) as stop:  # no owner decision yet: no retry, but the leftovers are already swept
        sheet_tasks(tmp_path, monkeypatch, items, score=reference_score(seen))
    assert (stop.value.kind, stop.value.reason) == ("qualification_paused", "attempt-1") and seen == []
    swept = verified(read_json(crashed / evaluation.QUALIFICATION_SWEPT), "transient-deletion")
    assert (swept["when"], swept["entries"], swept["files"], swept["manifest_sha256"]) == (
        "swept", [".pending-x1.json", "host_only"], count, sealed) and count == 3
    files, workbook = kept(crashed)
    assert files == sorted(["scores/" + "a" * 64 + ".json", evaluation.QUALIFICATION_SWEPT]) and not workbook
    with pytest.raises(Pause):  # nothing left: no second sweep record
        sheet_tasks(tmp_path, monkeypatch, items, score=reference_score(seen))
    assert kept(crashed) == (files, False) and seen == []
    write_json(crashed / "recovery.json", {"by": "owner", "date": "2026-10-22", "decision": "redo after a kill"})
    assert [t["task_id"] for t in sheet_tasks(tmp_path, monkeypatch, items, score=reference_score(seen))] == [
        i["task_id"] for i in items] and len(seen) == 4
    retried = verified(read_json(base / "attempt-2" / evaluation.QUALIFICATION_DELETED), "transient-deletion")
    assert retried["when"] == "complete" and not (base / "attempt-2" / "host_only").exists()
    pointer = verified(read_json(tmp_path / "shared" / "test" / (QUALIFICATION + ".json")),
                       "test-qualification-pointer")
    assert pointer["attempt"] == "attempt-2"
    # an artifact appearing in an attempt already swept is refused, never silently kept
    (crashed / "host_only").mkdir()
    (crashed / "host_only" / "late.xlsx").write_bytes(b"PK\x03\x04late")
    with pytest.raises(ValueError, match="deleted once"):
        sheet_tasks(tmp_path, monkeypatch, items, score=reference_score(seen))


def test_codex3_a_workbook_among_the_kept_results_is_refused(tmp_path, monkeypatch):
    """A scorer that copied a workbook next to the score records (outside ``host_only/``) would keep reference content
    among the sanitized results: the qualification is refused, no pointer is written."""
    items = spreadsheetbench_items(tmp_path / "sb", 1)
    inner = reference_score()

    def leaking(benchmark, public, private, prediction, *, runtime=None):
        found = inner(benchmark, public, private, prediction, runtime=runtime)
        attempt = Path(runtime["_score_context"]["artifact_dir"]).parents[2]
        (attempt / "scores").mkdir(parents=True, exist_ok=True)
        (attempt / "scores" / "copy.xlsx").write_bytes(Path(private["test_files"][0]).read_bytes())
        return found

    with pytest.raises(ValueError, match="never a workbook"):
        sheet_tasks(tmp_path, monkeypatch, items, score=leaking, workers=1)
    assert not (tmp_path / "shared" / "test" / (QUALIFICATION + ".json")).exists()
