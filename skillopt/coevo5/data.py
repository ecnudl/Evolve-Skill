"""Data of the protocol (registration §2, §0 test isolation).

Five training pools -- each benchmark's historical train and val parts, labels kept -- from the very files the
baselines use (study F's development panels, the fivebench-split-v2 val sources, the extension study's panels), every
file pinned by SHA-256. Seeded draws and the regression panels shared by all chains are hash orders of task ids.

Test isolation: every reader here except ``test_panel`` refuses a test item; ``test_panel`` is opened only by the
evaluation step with a ``TestAccess`` it creates. The OfficeQA and LiveMath test items exist upstream as ids only, in
source files that hold every part; only the evaluation step reads those files (with its ``TestAccess``), renders the
test items there by the frozen renderers that produced the training panels, and first proves the identity on the
training items (``_proof``).
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from copy import deepcopy
from pathlib import Path

from skillopt.continual_eval import datasets
from skillopt.continual_eval.core import read_json, require, safe_path

from .protocol import (
    MAX_UNKNOWN_SHARE,
    ORDER,
    PARENT_REGRESSION_RUNS,
    POOLS,
    REGRESSION_ITEMS,
    REGRESSION_RUNS,
    SHEET_MIN_QUALIFIED,
    TEST_SIZES,
    TRAIN_ROLLOUT,
)

TRAIN, VAL = "train", "val"
PARTITION = {TRAIN: "development", VAL: "skill_confirmation"}
EXTENSIONS = ("officeqa", "livemath")
SPLIT_VERSION = "fivebench-split-v2"
LAYOUT_VERSION = "extension-layout-v1"
TEST_PARTITION = "final"

# The development machine's frozen inputs (the pre-launch manifest records this mapping and every file's SHA-256).
DEV_MACHINE = {
    "split": "/root/fivebench-split-20261005-v2/split_manifest.json",
    "train": {"searchqa": "/root/continual-searchqa-long-20261001-study/data/panel.json",
              "officeqa": "/root/extension-20261013/officeqa/dev_panel.json",
              "livemath": "/root/extension-20261013/livemath/dev_panel.json",
              "spreadsheetbench": "/root/continual-spreadsheet-long-20261001-study/baseline/data/panel.json",
              "alfworld": "/root/continual-alfworld-long-20261001-study/data/panel.json"},
    "val": {"searchqa": "/root/fivebench-split-20261005-source/data/searchqa_split/val/items.json",
            "officeqa": "/root/extension-20261013/officeqa/val_panel.json",
            "livemath": "/root/extension-20261013/livemath/val_panel.json",
            "spreadsheetbench": "/root/continual-spreadsheet-20260928-a/prepared/panels/skill_confirmation.json",
            "alfworld": "/root/fivebench-split-20261005-source/data/alfworld_path_split/val/items.json"},
    "layouts": {"officeqa": "/root/extension-20261013/officeqa/layout.json",
                "livemath": "/root/extension-20261013/livemath/layout.json"},
    "alfworld_data": "/root/continual-alf-prep-20260928/data",
    "test": {"searchqa": "/root/fivebench-test-eval-20261005-h/panels/searchqa.json",
             "spreadsheetbench": "/root/fivebench-test-eval-20261005-h/panels/spreadsheetbench.json",
             "alfworld": "/root/fivebench-test-eval-20261005-h/panels/alfworld.json"},
    "upstream": {"officeqa": "/root/officeqa-upstream-20261013", "livemath": "/root/livemath-upstream-20261013"},
}


def sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _files(config):
    return [config["split"], *config["train"].values(), *config["val"].values(), *config["layouts"].values(),
            *config["test"].values()]


def pin(config):
    """The config with the SHA-256 of every input file (computed once, before launch, into the manifest). Hashing reads
    bytes only: no item, test or not, is parsed here."""
    require(set(config) == set(DEV_MACHINE) and set(config["train"]) == set(config["val"]) == set(ORDER)
            and set(config["layouts"]) == set(EXTENSIONS) and set(config["test"]) == set(ORDER) - set(EXTENSIONS)
            and set(config["upstream"]) == set(EXTENSIONS), "Invalid data configuration")
    return {"paths": deepcopy(config), "sha256": {str(safe_path(p)): sha(p) for p in _files(config)}}


def _checked(pinned, path):
    path = str(safe_path(path))
    require(pinned["sha256"].get(path) == sha(path), "A data file is not the pinned file: " + path)
    return path


def _split(pinned):
    split = read_json(_checked(pinned, pinned["paths"]["split"]), sealed=True)
    require(split["version"] == SPLIT_VERSION, "Unexpected split version")
    return split


def _layout(pinned, benchmark):
    layout = read_json(_checked(pinned, pinned["paths"]["layouts"][benchmark]), sealed=True)
    require(layout["version"] == LAYOUT_VERSION and layout["benchmark"] == benchmark, "Unexpected data layout")
    return layout


def _part_ids(pinned, benchmark, part):
    """{task_id: family_id} of a historical part; test ids are ids only."""
    if benchmark in EXTENSIONS:
        entries = _layout(pinned, benchmark)["parts"][part]
    else:
        entries = _split(pinned)["splits"][benchmark][part]
    ids = {str(e["task_id"]): str(e["family_id"]) for e in entries}
    require(len(ids) == len(entries), "Duplicate ids in a part")
    return ids


def test_ids(pinned, benchmark):
    """The ids of a benchmark's test part (no content): every non-evaluation reader refuses these."""
    require(benchmark in ORDER, "Unknown benchmark")
    return frozenset(_part_ids(pinned, benchmark, "test"))


def _refuse_tests(pinned, benchmark, tasks):
    tests = test_ids(pinned, benchmark)
    for task in tasks:
        require(str(task["task_id"]) not in tests and task["partition"] != TEST_PARTITION,
                "A test item reached a non-evaluation reader")


def _load(pinned, benchmark, part):
    path = _checked(pinned, pinned["paths"][part][benchmark])
    if part == VAL and benchmark not in EXTENSIONS:  # the very file the split was built from
        require(_split(pinned)["sources"].get(path) == sha(path), "Val source is not the split's file")
    if part == VAL and benchmark == "searchqa":  # as the stage tool builds it (run_fivebench_g_stage.val_panel)
        split = _split(pinned)
        wanted = _part_ids(pinned, benchmark, VAL)
        rows = [r for r in read_json(path) if str(r["id"]) in wanted]
        panel = datasets.import_searchqa(
            rows, partition=PARTITION[VAL],
            revision="skillopt-searchqa-native-val:%s:%s" % (SPLIT_VERSION, split["record_hash"][:12]))
    elif part == VAL and benchmark == "alfworld":
        wanted = _part_ids(pinned, benchmark, VAL)
        panel = datasets.import_alfworld(path, data_root=pinned["paths"]["alfworld_data"], partition=PARTITION[VAL],
                                         revision="alfworld-json_2.1.1-val18:%s" % SPLIT_VERSION,
                                         family_map=wanted)
    else:
        panel = datasets.load_panel(path)
    datasets.validate_panel(panel)
    require(panel["benchmark"] == benchmark, "Panel benchmark mismatch")
    _refuse_tests(pinned, benchmark, panel["tasks"])
    require(all(t["partition"] == PARTITION[part] for t in panel["tasks"]), "Unexpected partition label")
    wanted = _part_ids(pinned, benchmark, part)
    require({str(t["task_id"]): str(t["family_id"]) for t in panel["tasks"]} == wanted,
            "%s %s: the panel differs from its pinned part" % (benchmark, part))
    return panel


def pool(pinned, benchmark):
    """The training pool (§2): the historical train and val parts, each item labelled with its part."""
    require(benchmark in ORDER, "Unknown benchmark")
    items = []
    for part in (TRAIN, VAL):
        panel = _load(pinned, benchmark, part)
        items += [{"benchmark": benchmark, "task_id": str(t["task_id"]), "family_id": t["family_id"], "part": part,
                   "public": t["public"], "private": t["private"]} for t in panel["tasks"]]
    require((sum(i["part"] == TRAIN for i in items), sum(i["part"] == VAL for i in items)) == POOLS[benchmark],
            "Unexpected pool size")
    require(len({i["task_id"] for i in items}) == len(items), "An item is in two parts")
    return items


def item_hash(item):
    return hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def ranked(items, seed, tag):
    """A seeded hash order of task ids, independent of the input order and of Python's random module."""
    key = lambda item: hashlib.sha256(json.dumps([seed, tag, item["task_id"]]).encode()).hexdigest()  # noqa: E731
    return sorted(items, key=key)


def qualified(items, qualification):
    """SpreadsheetBench: the reference-qualified part of a pool (§2.1); other benchmarks unchanged."""
    if not items or items[0]["benchmark"] != "spreadsheetbench":
        return list(items)
    ids = set(qualification["qualified"])
    require(ids <= {i["task_id"] for i in items}, "Qualification of other items")
    return [i for i in items if i["task_id"] in ids]


def training_items(items, benchmark, seed, size=None):
    """The items of a stage's training execution (§2), the same for every chain: all of a small pool, else a seeded
    draw (SearchQA 200 of 600, LiveMath 100 of 283). SpreadsheetBench: every qualified item. ``size``: the smoke's
    smaller draw (§14 step 5), the first items of the same seeded order; a launch manifest sets none."""
    full = len(items) if benchmark == "spreadsheetbench" else TRAIN_ROLLOUT[benchmark][0]
    require(len(items) >= full and full > 0, "Pool smaller than the registered draw")
    require(size is None or (type(size) is int and 0 < size <= full), "A smaller draw has fewer items")
    return sorted(ranked(items, seed, "train:" + benchmark)[:full if size is None else size],
                  key=lambda i: i["task_id"])


def regression_items(items, benchmark, seed):
    """The bench's regression panel, drawn once before launch and shared by all chains (§2): 60 items of the pool, or
    every qualified SpreadsheetBench item when fewer; none for ALFWorld (last) or below the qualified minimum."""
    if benchmark == ORDER[-1] or (benchmark == "spreadsheetbench" and len(items) < SHEET_MIN_QUALIFIED):
        return []
    return sorted(ranked(items, seed, "regression:" + benchmark)[:min(REGRESSION_ITEMS, len(items))],
                  key=lambda i: i["task_id"])


def sheet_tolerances(qualified_count):
    """(t_k, t_b) for SpreadsheetBench's actual qualified size by the registered rules: t_k by §5.5 (the focal panel
    minus 8 trigger items, one run each, unchanged in v2); t_b by v2 delta §5.2 (the regression panel, min(60,
    qualified) items, the parent run ``PARENT_REGRESSION_RUNS`` times, a rule ``REGRESSION_RUNS``); None below the
    qualified minimum ("面板不足")."""
    if qualified_count < SHEET_MIN_QUALIFIED:
        return None
    import importlib.util
    import sys

    path = Path(__file__).resolve().parents[2] / "docs/handoff/coevo5_power_sim_v2.py"
    spec = importlib.util.spec_from_file_location("coevo5_power_sim_v2", path)
    module = importlib.util.module_from_spec(spec)
    saved = list(sys.path)
    try:  # the v2 rule imports the v1 model beside it
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = saved
    return (module.calibrate("spreadsheetbench", qualified_count - 8, 1),
            module.calibrate_split("spreadsheetbench", min(REGRESSION_ITEMS, qualified_count),
                                   PARENT_REGRESSION_RUNS, REGRESSION_RUNS))


# ----------------------------------------------------------------------------------------------- test (evaluation)
class TestAccess:
    """Created by the evaluation step only (evaluation.py), for one evaluation unit; every test reader requires it."""

    __test__ = False  # not a pytest class

    def __init__(self, unit):
        require(isinstance(unit, str) and unit, "A test reader serves one evaluation unit")
        self.unit = unit


def _pinned_bytes(root, name, expected):
    """A pinned upstream file's bytes, read once and checked (no gap between the check and the parse)."""
    raw = safe_path(root / name).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, "Upstream file changed: " + name)
    return raw


def _officeqa_rows(pinned, ids, *, access, sources=None):
    """The pilot's one-call rendering (scripts/pilot_officeqa_headroom.draw) of the given ids: question, the parsed
    pages the source hints point to, answer. An id whose hints resolve to no parsed page is returned as dropped. The
    question table holds every part, so only the evaluation step reads it. ``sources``: a dict that receives each kept
    item's source files (the readings resample the items that share a file together, §12.6)."""
    from scripts import pilot_officeqa_headroom as pilot
    from skillopt.envs.officeqa.tool_runtime import _as_list, build_oracle_parsed_pages_context

    require(isinstance(access, TestAccess), "Only the evaluation step reads a source that holds test items")
    root = safe_path(pinned["paths"]["upstream"]["officeqa"])
    files = _layout(pinned, "officeqa")["source"]["files"]
    text = _pinned_bytes(root, "officeqa_full.csv", files["officeqa_full.csv"]).decode("utf-8")
    rows = {}
    for row in csv.DictReader(io.StringIO(text, newline="")):
        require(row["uid"] not in rows, "Duplicate question id upstream")
        rows[row["uid"]] = row
    docs = [str(root / "treasury_bulletins_parsed" / "transformed")]
    items, dropped = [], []
    for uid in ids:
        require(uid in rows, "A question id is missing upstream: " + uid)
        row = rows[uid]
        require(row["question"].strip() and row["answer"].strip(), "Unexpected question record")
        context = build_oracle_parsed_pages_context(row["source_files"], row["source_docs"], docs,
                                                    evidence_note=pilot.EVIDENCE_NOTE)
        if not context.strip():
            dropped.append(uid)
            continue
        items.append({"id": uid, "question": row["question"].strip(), "context": context,
                      "answer": row["answer"].strip()})
        if sources is not None:
            sources[uid] = sorted(set(_as_list(row["source_files"])))
    return items, dropped


def _livemath_rows(pinned, ids, *, access):
    """The extension builder's rendering (scripts/make_extension_study.render_livemath) of the given ids, from exactly
    the monthly item files the layout pinned (each read once and checked; a duplicate item is refused). The files
    hold every part, so only the evaluation step reads them."""
    from scripts.make_extension_study import render_livemath

    require(isinstance(access, TestAccess), "Only the evaluation step reads a source that holds test items")
    root = safe_path(pinned["paths"]["upstream"]["livemath"])
    records = {}
    for name, expected in sorted(_layout(pinned, "livemath")["source"]["files"].items()):
        month = Path(name).parent.name
        for record in json.loads(_pinned_bytes(root, name, expected)):
            key = "%s:%s" % (month, record["no"])
            require(key not in records, "Duplicate item upstream: " + key)
            records[key] = record
    missing = [name for name in ids if name not in records]
    require(not missing, "Item ids missing upstream: %s" % missing[:5])
    return [render_livemath(records[name], name.split(":")[0]) for name in ids], []


def _rendered(pinned, benchmark, ids, label, partition, access, sources=None):
    if benchmark == "officeqa":
        rows, dropped = _officeqa_rows(pinned, ids, access=access, sources=sources)
    else:
        rows, dropped = _livemath_rows(pinned, ids, access=access)
    importer = getattr(datasets, "import_" + benchmark)
    panel = importer(rows, partition=partition, revision=label,
                     family_map={row["id"]: "%s:%s" % (benchmark, row["id"]) for row in rows})
    return panel, dropped


def _proof(pinned, benchmark, access):
    """Inside the evaluation step, before any test item is used: the renderer reproduces the frozen training panels
    exactly (public content and answer, item by item). Returns the number of items checked."""
    checked = 0
    for part in (TRAIN, VAL):
        panel = _load(pinned, benchmark, part)
        ids = [str(t["task_id"]) for t in panel["tasks"]]
        rendered, dropped = _rendered(pinned, benchmark, ids, panel["dataset_revision"], PARTITION[part], access)
        require(not dropped, "A training item lost its pages")
        by_id = {str(t["task_id"]): t for t in rendered["tasks"]}
        for task in panel["tasks"]:
            twin = by_id[str(task["task_id"])]
            require(twin["public"] == task["public"] and twin["private"]["answer"] == task["private"]["answer"],
                    "The renderer differs from the frozen panel at " + str(task["task_id"]))
            checked += 1
    return checked


def test_panel(pinned, benchmark, *, access):
    """(tasks, report) of a benchmark's test set -- the evaluation step only. SearchQA, SpreadsheetBench and ALFWorld:
    the frozen 10/5 test panels (pinned). OfficeQA, LiveMath: rendered from upstream by the training renderers, after
    the renderer reproduced the frozen training panels (``_proof``); an OfficeQA item whose source hints resolve to no
    parsed page is excluded and reported, and more than a tenth of such items stops the evaluation. The report names
    each OfficeQA item's source files (``source_files``; None for the other benchmarks)."""
    require(isinstance(access, TestAccess), "Only the evaluation step reads a test set")
    require(benchmark in ORDER, "Unknown benchmark")
    wanted = _part_ids(pinned, benchmark, "test")
    checked, sources = None, {} if benchmark == "officeqa" else None
    if benchmark in EXTENSIONS:
        checked = _proof(pinned, benchmark, access)
        label = "%s:%s:coevo5-test-render" % (benchmark, _layout(pinned, benchmark)["source"]["revision"][:12])
        panel, dropped = _rendered(pinned, benchmark, sorted(wanted), label, TEST_PARTITION, access, sources)
        require(len(dropped) <= MAX_UNKNOWN_SHARE * TEST_SIZES[benchmark],
                "More than a tenth of the test items have no parsed page")
    else:
        panel, dropped = datasets.load_panel(_checked(pinned, pinned["paths"]["test"][benchmark])), []
    datasets.validate_panel(panel)
    tasks = panel["tasks"]
    require(panel["benchmark"] == benchmark and all(t["partition"] == TEST_PARTITION for t in tasks)
            and {str(t["task_id"]) for t in tasks} <= set(wanted)
            and len(tasks) + len(dropped) == TEST_SIZES[benchmark], "The test panel differs from its pinned part")
    report = {"benchmark": benchmark, "tasks": len(tasks), "excluded_without_pages": sorted(dropped),
              "training_items_identical": checked, "panel_hash": datasets.panel_hash(panel), "unit": access.unit,
              "source_files": sources}
    return tasks, report
