"""coevo5 data (registration §2, §0 test isolation): the five training pools from pinned files, the seeded draws and
regression panels shared by every chain, the test-id refusal of every non-evaluation reader, and the evaluation-only
test panels (OfficeQA and LiveMath rendered by the training renderers) -- on small fixture files."""
import csv
import json

import pytest

from scripts import pilot_officeqa_headroom as officeqa_pilot
from scripts.make_extension_study import render_livemath
from skillopt.coevo5 import data
from skillopt.coevo5.protocol import ORDER
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import datasets
from skillopt.envs.officeqa import tool_runtime

SIZES = {"searchqa": (3, 2, 2), "officeqa": (2, 2, 10), "livemath": (2, 2, 2), "spreadsheetbench": (3, 2, 2),
         "alfworld": (2, 2, 2)}  # train, val, test
PARTS = ("train", "val", "test")
PARTITION = {"train": "development", "val": "skill_confirmation", "test": "final"}
MONTH = {"train": "2025-01", "val": "2025-02", "test": "2025-03"}
NO_PAGES = "of-test-2"  # an OfficeQA test item whose source hints resolve to no parsed page


def _ids(benchmark, part):
    count = SIZES[benchmark][PARTS.index(part)]
    if benchmark == "livemath":
        return ["%s:%d" % (MONTH[part], n + 1) for n in range(count)]
    return ["%s-%s-%d" % (benchmark[:2], part, n) for n in range(count)]


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return str(path)


def _content(benchmark, task_id):
    return {"searchqa": ({"question": "Q " + task_id, "context": ["c"]}, {"answers": ["a"]}),
            "spreadsheetbench": ({"instruction": "Do " + task_id, "input_files": [task_id + "_init.xlsx"],
                                  "answer_position": "A1"},
                                 {"test_files": [task_id + "_golden.xlsx"], "answer_position": "A1"}),
            "alfworld": ({"game_file": "json_2.1.1/train/scene-%s/trial_1/game.tw-pddl" % task_id},
                         {"game_metadata": {"task_type": "pick"}})}[benchmark]


def _panel(benchmark, ids, part):
    tasks = [{"task_id": i, "family_id": "%s:%s" % (benchmark, i), "project_id": "", "partition": PARTITION[part],
              "public": _content(benchmark, i)[0], "private": _content(benchmark, i)[1]} for i in ids]
    return {"version": datasets.VERSION, "benchmark": benchmark, "dataset_revision": "fixture-" + part,
            "provenance": "fixture", "tasks": tasks}


def _mcq(name):
    return {"question": "Which is %s?" % name, "correct_choice": {"label": "A", "text": "right " + name},
            "choices": [{"label": label, "text": "wrong %s %s" % (label, name)} for label in "BCDE"]}


def _pages(source_files, source_docs, roots, *, evidence_note):
    """The parsed-page builder, patched: no page for the hint "none" or a hint in ``_pages.empty``."""
    _pages.calls.append((tuple(roots), evidence_note))
    if source_files == "none" or source_files in _pages.empty:
        return ""
    return "page of %s (%s)" % (source_files, evidence_note)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A configuration of the DEV_MACHINE form over fixture files; POOLS and TEST_SIZES follow SIZES."""
    _pages.calls, _pages.empty = [], set()
    monkeypatch.setattr(tool_runtime, "build_oracle_parsed_pages_context", _pages)
    monkeypatch.setattr(data, "POOLS", {b: SIZES[b][:2] for b in ORDER})
    monkeypatch.setattr(data, "TEST_SIZES", {b: SIZES[b][2] for b in ORDER})
    root = tmp_path / "inputs"
    config = {"train": {}, "val": {}, "layouts": {}, "test": {}, "upstream": {},
              "alfworld_data": str(root / "alfworld-data")}
    splits, sources = {}, {}
    for benchmark in ("searchqa", "spreadsheetbench", "alfworld"):
        entries = {part: [{"task_id": i, "family_id": "%s:%s" % (benchmark, i)} for i in _ids(benchmark, part)]
                   for part in PARTS}
        config["train"][benchmark] = _write(root / benchmark / "train.json",
                                            _panel(benchmark, _ids(benchmark, "train"), "train"))
        config["test"][benchmark] = _write(root / benchmark / "test.json",
                                           _panel(benchmark, _ids(benchmark, "test"), "test"))
        val = root / benchmark / "val.json"
        if benchmark == "searchqa":  # raw records, imported as the stage tool does
            rows = [{"id": i, "question": "Q " + i, "context": ["c"], "answers": ["a"]} for i in _ids(benchmark, "val")]
            families = {t["task_id"]: t["family_id"] for t in datasets.import_searchqa(rows, revision="r")["tasks"]}
            entries["val"] = [{"task_id": i, "family_id": families[i]} for i in _ids(benchmark, "val")]
            _write(val, rows + [{"id": "unlisted", "question": "Q", "context": ["c"], "answers": ["a"]}])
        elif benchmark == "alfworld":  # game-path records
            _write(val, [{"id": i, "gamefile": _content(benchmark, i)[0]["game_file"], "task_type": "pick"}
                         for i in _ids(benchmark, "val")])
        else:
            _write(val, _panel(benchmark, _ids(benchmark, "val"), "val"))
        config["val"][benchmark] = str(val)
        sources[str(val)] = data.sha(val)
        splits[benchmark] = entries
    config["split"] = _write(root / "split_manifest.json",
                             seal({"version": data.SPLIT_VERSION, "splits": splits, "sources": sources}))
    upstream = root / "upstream"
    # LiveMath: monthly item files, rendered by the extension builder's renderer
    files = {}
    for part in PARTS:
        name = "data/%s/qa_%s_final.json" % (MONTH[part], MONTH[part])
        _write(upstream / "livemath" / name, [{"no": int(i.split(":")[1]), "mcq": _mcq(i)}
                                              for i in _ids("livemath", part)])
        files[name] = data.sha(upstream / "livemath" / name)
    _layout(root, config, "livemath", {"files": files, "revision": "livemath-upstream-rev"})
    # OfficeQA: the question table; the parsed pages come from the (patched) page builder
    table = upstream / "officeqa" / "officeqa_full.csv"
    table.parent.mkdir(parents=True)
    with table.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, ["uid", "question", "answer", "source_files", "source_docs"])
        writer.writeheader()
        for part in PARTS:
            for i in _ids("officeqa", part):
                writer.writerow({"uid": i, "question": " How much in %s? " % i, "answer": " 42 ",
                                 "source_files": "none" if i == NO_PAGES else i + ".json",
                                 "source_docs": "https://example.org/" + i})
    _layout(root, config, "officeqa", {"files": {"officeqa_full.csv": data.sha(table), "parsed_pages": "0" * 64},
                                       "revision": "officeqa-upstream-rev"})
    config["upstream"] = {b: str(upstream / b) for b in data.EXTENSIONS}
    for part in ("train", "val"):  # the frozen training panels, as the extension builder rendered them
        rows = {"livemath": [render_livemath({"no": int(i.split(":")[1]), "mcq": _mcq(i)}, MONTH[part])
                             for i in _ids("livemath", part)],
                "officeqa": [{"id": i, "question": "How much in %s?" % i, "answer": "42",
                              "context": "page of %s.json (%s)" % (i, officeqa_pilot.EVIDENCE_NOTE)}
                             for i in _ids("officeqa", part)]}
        for benchmark in data.EXTENSIONS:
            panel = getattr(datasets, "import_" + benchmark)(
                rows[benchmark], partition=PARTITION[part], revision="%s-%s" % (benchmark, part),
                family_map={i: "%s:%s" % (benchmark, i) for i in _ids(benchmark, part)})
            config[part][benchmark] = _write(root / benchmark / (part + ".json"), panel)
    return config


def _layout(root, config, benchmark, source):
    parts = {part: [{"task_id": i, "family_id": "%s:%s" % (benchmark, i)} for i in _ids(benchmark, part)]
             for part in PARTS}
    config["layouts"][benchmark] = _write(root / benchmark / "layout.json", seal(
        {"version": data.LAYOUT_VERSION, "benchmark": benchmark, "parts": parts, "source": source}))


def _rewrite(path, change):
    value = json.loads(open(path, encoding="utf-8").read())
    change(value)
    _write(data.safe_path(path), value)


def _relayout(world, benchmark, name):
    """Re-pin one upstream file of a benchmark's layout (as if the layout had been built from it)."""
    layout = json.loads(open(world["layouts"][benchmark], encoding="utf-8").read())
    files = {**layout["source"]["files"], name: data.sha(data.safe_path(world["upstream"][benchmark]) / name)}
    _layout(data.safe_path(world["layouts"][benchmark]).parents[1], world, benchmark,
            {"files": files, "revision": layout["source"]["revision"]})


# ------------------------------------------------------------------------------------------------- the pools
def test_every_pool_holds_its_train_and_val_parts_with_their_labels(world):
    pinned = data.pin(world)
    assert len(pinned["sha256"]) == 1 + 5 + 5 + 2 + 3
    for benchmark in ORDER:
        items = data.pool(pinned, benchmark)
        for part in ("train", "val"):
            assert sorted(i["task_id"] for i in items if i["part"] == part) == sorted(_ids(benchmark, part))
        assert not {i["task_id"] for i in items} & data.test_ids(pinned, benchmark)
        assert set(items[0]) == {"benchmark", "task_id", "family_id", "part", "public", "private"}


def test_the_configuration_is_complete_and_every_file_is_the_pinned_one(world):
    with pytest.raises(ValueError):
        data.pin({**world, "test": {}})
    pinned = data.pin(world)
    _rewrite(world["train"]["searchqa"], lambda panel: panel["tasks"][0]["public"].update(question="changed"))
    with pytest.raises(ValueError, match="not the pinned file"):
        data.pool(pinned, "searchqa")


def test_a_val_source_must_be_the_file_the_split_was_built_from(world):
    _rewrite(world["val"]["alfworld"], lambda rows: rows[0].update(task_type="heat"))
    with pytest.raises(ValueError, match="split's file"):
        data.pool(data.pin(world), "alfworld")


def test_a_test_item_never_reaches_a_training_reader(world):
    test_task = _panel("searchqa", _ids("searchqa", "test")[:1], "train")["tasks"][0]
    _rewrite(world["train"]["searchqa"], lambda panel: panel["tasks"].append(test_task))
    with pytest.raises(ValueError, match="non-evaluation reader"):
        data.pool(data.pin(world), "searchqa")


def test_a_panel_must_equal_its_pinned_part(world):
    _rewrite(world["train"]["spreadsheetbench"], lambda panel: panel["tasks"].pop())
    with pytest.raises(ValueError, match="differs from its pinned part"):
        data.pool(data.pin(world), "spreadsheetbench")


# ------------------------------------------------------------------------------------------------- the draws
def _items(benchmark, count):
    return [{"benchmark": benchmark, "task_id": "t%03d" % n} for n in range(count)]


def test_draws_are_seeded_hash_orders_independent_of_the_input_order():
    items = _items("searchqa", 600)
    drawn = data.training_items(items, "searchqa", 7)
    assert len(drawn) == 200 and drawn == data.training_items(items[::-1], "searchqa", 7)
    assert drawn == sorted(drawn, key=lambda i: i["task_id"]) and drawn != data.training_items(items, "searchqa", 8)
    assert len(data.training_items(_items("spreadsheetbench", 52), "spreadsheetbench", 7)) == 52  # all qualified
    with pytest.raises(ValueError):
        data.training_items(_items("livemath", 99), "livemath", 7)


def test_the_smoke_s_smaller_draw_is_the_head_of_the_registered_order():
    items = _items("searchqa", 600)
    full = {i["task_id"] for i in data.training_items(items, "searchqa", 7)}
    small = data.training_items(items, "searchqa", 7, size=60)
    assert len(small) == 60 and {i["task_id"] for i in small} <= full and small == sorted(small, key=lambda i:
                                                                                            i["task_id"])
    assert small == data.training_items(items[::-1], "searchqa", 7, size=60)
    for size in (0, 201, 6.0, True):  # never more than the registered draw, never empty
        with pytest.raises(ValueError):
            data.training_items(items, "searchqa", 7, size=size)


def test_regression_panels_are_shared_draws_of_at_most_sixty_items():
    panel = data.regression_items(_items("officeqa", 74), "officeqa", 7)
    assert len(panel) == 60 and panel == data.regression_items(_items("officeqa", 74)[::-1], "officeqa", 7)
    assert panel != data.regression_items(_items("officeqa", 74), "officeqa", 8)
    assert len(data.regression_items(_items("spreadsheetbench", 52), "spreadsheetbench", 7)) == 52
    assert data.regression_items(_items("spreadsheetbench", 29), "spreadsheetbench", 7) == []
    assert data.regression_items(_items("alfworld", 57), "alfworld", 7) == []  # the last bench has none


def test_only_qualified_spreadsheet_items_enter_the_pool():
    items = _items("spreadsheetbench", 5)
    assert [i["task_id"] for i in data.qualified(items, {"qualified": ["t001", "t003"]})] == ["t001", "t003"]
    assert data.qualified(_items("searchqa", 3), {"qualified": []}) == _items("searchqa", 3)
    with pytest.raises(ValueError):
        data.qualified(items, {"qualified": ["elsewhere"]})
    assert data.sheet_tolerances(data.SHEET_MIN_QUALIFIED - 1) is None


# --------------------------------------------------------------------------------------------- the test sets
def test_only_the_evaluation_step_reads_a_test_set(world):
    pinned = data.pin(world)
    with pytest.raises(ValueError, match="Only the evaluation step"):
        data.test_panel(pinned, "searchqa", access=None)
    with pytest.raises(ValueError):
        data.TestAccess("")
    tasks, report = data.test_panel(pinned, "searchqa", access=data.TestAccess("E-glm/s0/evaluation/searchqa"))
    assert sorted(t["task_id"] for t in tasks) == _ids("searchqa", "test")
    assert {t["partition"] for t in tasks} == {"final"} and report["unit"] == "E-glm/s0/evaluation/searchqa"
    assert report["panel_hash"] == datasets.panel_hash(datasets.load_panel(world["test"]["searchqa"]))


def test_a_test_panel_must_have_its_registered_size(world, monkeypatch):
    pinned = data.pin(world)
    monkeypatch.setattr(data, "TEST_SIZES", {**data.TEST_SIZES, "alfworld": 3})
    with pytest.raises(ValueError, match="differs from its pinned part"):
        data.test_panel(pinned, "alfworld", access=data.TestAccess("unit"))


def test_livemath_test_items_are_rendered_by_the_training_renderer(world):
    tasks, report = data.test_panel(data.pin(world), "livemath", access=data.TestAccess("unit"))
    assert sorted(t["task_id"] for t in tasks) == _ids("livemath", "test") and report["excluded_without_pages"] == []
    assert report["training_items_identical"] == 4  # the renderer reproduced every frozen training item first
    first = next(t for t in tasks if t["task_id"] == "2025-03:1")
    expected = render_livemath({"no": 1, "mcq": _mcq("2025-03:1")}, "2025-03")
    assert first["public"] == {"question": expected["question"], "choices": expected["choices"]}
    assert first["private"]["answer"] == expected["answer"] and first["family_id"] == "livemath:2025-03:1"
    assert {t["partition"] for t in tasks} == {"final"}


def test_an_officeqa_test_item_without_pages_is_excluded_and_reported(world):
    tasks, report = data.test_panel(data.pin(world), "officeqa", access=data.TestAccess("unit"))
    assert report["excluded_without_pages"] == [NO_PAGES] and len(tasks) == SIZES["officeqa"][2] - 1
    assert report["training_items_identical"] == 4
    assert report["source_files"] == {t["task_id"]: [t["task_id"] + ".json"] for t in tasks}  # §12.6 groups
    docs = data.safe_path(world["upstream"]["officeqa"]) / "treasury_bulletins_parsed" / "transformed"
    assert set(_pages.calls) == {((str(docs),), officeqa_pilot.EVIDENCE_NOTE)}
    assert all(t["public"]["question"] == t["public"]["question"].strip() for t in tasks)


def test_more_than_a_tenth_of_officeqa_test_items_without_pages_stops_the_evaluation(world):
    _pages.empty = {"of-test-5.json"}
    with pytest.raises(ValueError, match="More than a tenth"):
        data.test_panel(data.pin(world), "officeqa", access=data.TestAccess("unit"))


def test_the_renderer_must_reproduce_the_frozen_training_panels_before_any_test_item(world):
    def wrong_letter(panel):
        private = panel["tasks"][0]["private"]
        private["answer"] = "B" if private["answer"] == "A" else "A"

    _rewrite(world["val"]["livemath"], wrong_letter)
    with pytest.raises(ValueError, match="renderer differs"):
        data.test_panel(data.pin(world), "livemath", access=data.TestAccess("unit"))


def test_sources_that_hold_test_items_are_read_only_with_test_access(world):
    pinned = data.pin(world)
    for render in (data._livemath_rows, data._officeqa_rows):
        with pytest.raises(ValueError, match="Only the evaluation step"):
            render(pinned, [], access=None)


def test_only_the_pinned_upstream_files_are_read_and_a_duplicate_item_is_refused(world):
    root = data.safe_path(world["upstream"]["livemath"])
    _write(root / "data" / "2025-03" / "qa_2025-03_extra.json", [{"no": 1, "mcq": _mcq("an unpinned twin")}])
    tasks, _ = data.test_panel(data.pin(world), "livemath", access=data.TestAccess("unit"))
    assert "unpinned" not in json.dumps(tasks)  # a file the layout did not pin is never read
    name = "data/2025-03/qa_2025-03_final.json"
    _rewrite(root / name, lambda records: records.append(dict(records[0])))
    _relayout(world, "livemath", name)
    with pytest.raises(ValueError, match="Duplicate item upstream"):
        data.test_panel(data.pin(world), "livemath", access=data.TestAccess("unit"))


def test_a_duplicate_officeqa_question_id_is_refused(world):
    table = data.safe_path(world["upstream"]["officeqa"]) / "officeqa_full.csv"
    with table.open("a", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow(["of-test-0", "Another question?", "7", "x.json", "https://example.org/x"])
    _relayout(world, "officeqa", "officeqa_full.csv")
    with pytest.raises(ValueError, match="Duplicate question id"):
        data.test_panel(data.pin(world), "officeqa", access=data.TestAccess("unit"))


def test_a_changed_upstream_file_stops_the_rendering(world):
    pinned = data.pin(world)
    path = data.safe_path(world["upstream"]["livemath"]) / "data" / "2025-03" / "qa_2025-03_final.json"
    _rewrite(path, lambda records: records[0]["mcq"].update(question="changed"))
    with pytest.raises(ValueError, match="Upstream file changed"):
        data.test_panel(pinned, "livemath", access=data.TestAccess("unit"))
