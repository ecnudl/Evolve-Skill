"""Requested Amendment-2 worker/mount regressions and repeated-benchmark corpus provenance."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.execskill_zpc_fakes import tmp_path

from skillopt.continual_eval.core import write_json
from skillopt.execskill import engineer, profiles as protocol, solver, step
from skillopt.execskill.package import FIXTURE, Package, Procedure, empty
from tests.execskill_fakes_env import FakeSandbox


@pytest.mark.parametrize("custom", [False, True])
def test_c6b_reuses_default_non_sheet_worker_but_custom_factories_stay_per_item(tmp_path, monkeypatch, custom):
    parent = empty(step="D/s0", evidence=FIXTURE)
    created, captured = [], []
    @contextmanager
    def workers(package, *, kind, inputs_dir=None):
        worker = FakeSandbox().start(package, kind=kind, inputs_dir=inputs_dir)
        created.append(worker)
        yield worker
        worker.close()
    @contextmanager
    def item_workers(package, item):
        with workers(package, kind="cell") as worker:
            yield worker
    setting = SimpleNamespace(extra={"configuration": protocol.MAIN_V2_3}, cards={}, runtime={"officeqa": {}},
                              evidence=FIXTURE)
    st = step._Step(setting, SimpleNamespace(workers=workers, item_workers=item_workers if custom else None),
                    "D", "officeqa", 1, parent, tmp_path)
    cut = {"run": [{"benchmark": "officeqa", "task_id": str(i), "public": {"question": "Task %d" % i,
                    "context": "Context"}, "private": {"answer": str(i)}} for i in range(4)]}
    proposal = Procedure(id="fx-shared-c6b", origin="officeqa", description="Generic public predicate.",
                         hooks=("applies", "before_call"), source="def applies(view):\n    return True\ndef before_call(view, state):\n    return None\n", evidence=FIXTURE, max_note_chars=100)
    def capture(ctx):
        captured.append(ctx)
        passed, detail = engineer._firing(proposal, ctx)
        assert passed and detail["fires_on"] == detail["items"] == 4
        return None, {"captured": True}
    monkeypatch.setattr(st, "unit", lambda name, work, **kwargs: work(tmp_path))
    monkeypatch.setattr(st, "roles", lambda _: None)
    for name in ("_earlier", "_run_trajectories", "_current", "_evaluated"):
        monkeypatch.setattr(step, name, lambda *args, **kwargs: [])
    monkeypatch.setattr(engineer, "run_train", capture)
    step._engineer_train(st, cut, 1, parent, done=[], fed=None, history=[], training=None, lint=[],
                         reserved=[], analysed=[], disclosed=[])
    assert captured[0].routing_shared_worker is (not custom)
    assert len(created) == (4 if custom else 1)
    assert sum(len(w.calls) for w in created) == 4 and all(w.closed for w in created)


def test_spreadsheet_c6b_matches_train_routing_views_runtime_and_per_item_mounts(tmp_path, monkeypatch):
    """No custom item_workers: distinct run/generated workbooks reach both routing passes."""
    run_book, generated_book = tmp_path / "run.xlsx", tmp_path / "generated.xlsx"
    from openpyxl import Workbook, load_workbook
    for path, sentinel in [(run_book, "RUN-WORKBOOK-SENTINEL"), (generated_book, "GENERATED-WORKBOOK-SENTINEL")]:
        book = Workbook()
        book.active["A1"] = sentinel
        book.save(path)
        book.close()
    def content(path):
        book = load_workbook(path, read_only=True)
        try:
            return book.active["A1"].value
        finally:
            book.close()
    previews, opened, routed, captured = [], [], [], []
    def preview(path, *, version):
        previews.append((str(path), version))
        return content(path)
    monkeypatch.setattr(solver, "_sheet_preview", preview)
    @contextmanager
    def workers(package, *, kind, inputs_dir=None):
        mounted = content(Path(inputs_dir) / "input.xlsx")
        opened.append((kind, mounted))
        class Worker:
            def call(self, proc, hook, args, *, timeout_s):
                view = args[0]
                routed.append((view, mounted, timeout_s))
                assert view["workbook_preview"] == mounted
                return {"ok": True, "value": True}
        yield Worker()
    def public(path):
        return {"instruction": "Inspect the public workbook.", "input_files": [str(path)], "answer_position": "A1"}
    run = {"benchmark": "spreadsheetbench", "task_id": "run-book", "public": public(run_book), "private": {}}
    made = protocol.record("generated-item", FIXTURE, {"id": "g-book", "benchmark": "spreadsheetbench",
        "public": public(generated_book), "private": {}})
    generated = {"generator": {"status": "admitted"}, "g_self": [made]}
    parent = empty(step="D/s0", evidence=FIXTURE)
    setting = SimpleNamespace(extra={"configuration": protocol.MAIN_V2_3}, cards={}, evidence=FIXTURE,
                              runtime={"spreadsheetbench": {"spreadsheet_preview_version": "runtime-sentinel"}})
    st = step._Step(setting, SimpleNamespace(workers=workers, item_workers=None), "D", "spreadsheetbench", 1,
                    parent, tmp_path)
    procedure = Procedure(id="fx-workbook-c6b", origin="spreadsheetbench", description="Public workbook predicate.",
        hooks=("applies", "before_call"), source="def applies(view):\n    return True\ndef before_call(view, state):\n    return None\n", evidence=FIXTURE, max_note_chars=100)
    def capture(ctx):
        captured.append(ctx)
        passed, detail = engineer._firing(procedure, ctx)
        assert passed and detail["fires_on"] == 2
        return None, {"captured": True}
    monkeypatch.setattr(st, "unit", lambda name, work, **kwargs: work(tmp_path))
    monkeypatch.setattr(st, "roles", lambda _: None)
    for name in ("_earlier", "_run_trajectories", "_current", "_evaluated"):
        monkeypatch.setattr(step, name, lambda *args, **kwargs: [])
    monkeypatch.setattr(engineer, "run_train", capture)
    step._engineer_train(st, {"run": [run]}, 1, parent, done=[], fed=None, history=[], training=None, lint=[],
                         reserved=[], analysed=[], disclosed=[], generated=generated)
    ctx = captured[0]
    _, _, publics = step._training_publics({"run": [run]}, generated, "spreadsheetbench")
    entries = [(key, solver.routing_view(st.bench, p, runtime=st.runtime())) for key, p in publics.items()]
    logs = step._routes(st, Package((procedure,), "D/s1", FIXTURE), entries, publics)
    assert ctx.routing_items == entries and not ctx.routing_shared_worker
    assert list(logs) == ["spreadsheetbench/run-book", "g-book"]
    assert all(log.enabled == (procedure.id,) for log in logs.values())
    assert routed[:2] == routed[2:]
    assert opened == [("cell", sentinel) for sentinel in ["RUN-WORKBOOK-SENTINEL", "GENERATED-WORKBOOK-SENTINEL"]] * 2
    assert previews == [(str(book), "runtime-sentinel") for book in [run_book, generated_book]] * 2


def corpus_item(bench, ident, answer):
    private = {"answers": [answer]} if bench == "searchqa" else {"answer": answer}
    return {"benchmark": bench, "task_id": ident, "public": {"question": ident, "context": "Context"},
            "private": private}


def test_repeated_benchmark_corpus_keeps_current_identity_and_earlier_provenance(tmp_path, monkeypatch):
    old = corpus_item("officeqa", "old", "EarlierWord")
    now = corpus_item("officeqa", "current", "CurrentWord")
    other = corpus_item("searchqa", "other", "OtherWord")
    root = tmp_path / "D"
    old_record = protocol.record("step-slices", FIXTURE, {"slices": {"run": ["old"]}})
    write_json(root / "s1-officeqa" / step.SLICES_FILE, old_record)
    write_json(root / "s2-searchqa" / step.SLICES_FILE,
               protocol.record("step-slices", FIXTURE, {"slices": {"run": ["other"]}}))
    monkeypatch.setattr(step, "_earlier", lambda *args: [(1, "officeqa", {}), (2, "searchqa", {})])
    st = SimpleNamespace(bench="officeqa", k=3, chain_root=root,
                         setting=SimpleNamespace(pools={"officeqa": [old, now], "searchqa": [other]}))
    found = step._corpora(st, {"run": [now]})
    assert list(found) == ["officeqa", "officeqa@s1", "searchqa"]
    assert found["officeqa"].words == {"currentword"}
    assert found["officeqa@s1"].words == {"earlierword"}
    assert found["officeqa@s1"].provenance == {"bench": "officeqa", "k": 1, "step": "s1-officeqa",
                                                   "slices_sha256": old_record[protocol.RECORD_HASH]}
    assert not hasattr(found["officeqa"], "provenance")
    monkeypatch.setattr(step, "_earlier", lambda *args: [(2, "searchqa", {})])
    unchanged = step._corpora(st, {"run": [now]})
    assert list(unchanged) == ["officeqa", "searchqa"]
    assert all(not hasattr(corpus, "provenance") for corpus in unchanged.values())
    assert vars(unchanged["officeqa"]) == vars(found["officeqa"])
    assert vars(unchanged["searchqa"]) == vars(found["searchqa"])
