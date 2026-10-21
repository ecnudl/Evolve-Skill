#!/usr/bin/env python3
"""Zero-call builders of the EXTENSION study: new single-call benchmarks beside the five-benchmark study F.

The owner replaced BigCodeBench and KOR-Bench by LiveMathematicianBench and OfficeQA on 2026-10-13. The frozen
five-benchmark protocol, split and artifacts stay as they are; the new benchmarks get their own study protocol and
split, derived from study F only in what must be identical (the model record, the learning model service, the
client retry options, the native lock, the Skill budget). Build order -- each step binds the previous by hash:

    data   --benchmark livemath --upstream U --id-split S --revision SHA --output DIR
           materialise the items of one benchmark and cut them into parts (zero calls):
             DIR/dev_panel.json    development partition = the pool training tasks are drawn from
             DIR/val_panel.json    skill_confirmation partition = the validation gate's tasks
             DIR/eval_blocks/*/items.json   evaluation blocks OUTSIDE the split (the panel evaluation tool
                                            refuses any item that shares a task or family with the split)
             DIR/layout.json       sealed: sources, seed, the ids of every part (test ids are ids only)
    study  --base F --data DIR [--data DIR2] --output STUDY     the extension study protocol
    split  --study STUDY --output FILE                          the split manifest for the stage tools

Data discipline. A benchmark's sealed TEST part is listed by id only: its items are never rendered, written or
sent anywhere by these builders. Nothing here calls a model.

LiveMathematicianBench layout (608 items, one family per item = per source paper):
    test   the 125 test items of the SkillOpt paper's split (ids only)
    eval   the 200 items of the headroom pilot of 2026-10-13 (months 2026-03..06), rendered exactly as there
    val    128 of the remaining 283 items, by a hash order
    train  the other 155
Every rendered item carries its five options in the pilot's hash-drawn order.

OfficeQA layout (246 items, one-call form: the question plus the parsed pages its source hints point to) -- the
SkillOpt paper's own split, by the owner's decision of 2026-10-13:
    train  its 50 training items          val  its 24 validation items
    test   its 172 test items (ids only)  eval none: every item is in the split
One family per item. The paper's split is NOT document-disjoint (items of different parts cite the same bulletins).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import pilot_livemath_headroom as livemath_pilot  # noqa: E402
from scripts import pilot_officeqa_headroom as officeqa_pilot  # noqa: E402
from scripts import run_fivebench_g_stage as tool  # noqa: E402
from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.continual_eval import datasets  # noqa: E402
from skillopt.continual_eval.core import read_json, require, safe_path, write_json  # noqa: E402

LAYOUT_VERSION = "extension-layout-v1"
PILOT_SEED, PILOT_PER_MONTH = 20261013, 50  # the headroom pilot's draw (docs/handoff/benchmark-replacement-pilot-20261013.md)
BLOCK = 25


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _digest(*parts):
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()


def _ids(id_split, part):
    return ["%s:%s" % (item["month"], item["no"])
            for item in json.loads((safe_path(id_split) / part / "items.json").read_text(encoding="utf-8"))]


def render_livemath(record, month, seed=PILOT_SEED):
    """One upstream record as a materialised row {"id", "question", "choices", "answer"}: the correct option and
    the four wrong ones in the hash-drawn order of the headroom pilot (same rule, same seed)."""
    mcq = record["mcq"]
    correct = mcq["correct_choice"]
    choices = [correct] + list(mcq["choices"])
    labels = livemath_pilot.LABELS
    require(len(choices) == len(labels) and len({c["label"] for c in choices}) == len(labels)
            and all(type(c["text"]) is str and c["text"].strip() for c in choices)
            and len({c["text"].strip() for c in choices}) == len(labels)
            and type(mcq["question"]) is str and mcq["question"].strip(), "Unexpected multiple-choice record")
    name = "%s:%s" % (month, record["no"])
    order = sorted(choices, key=lambda c: livemath_pilot._digest(seed, "order", name, c["label"]))
    return {"id": name, "question": mcq["question"],
            "choices": "\n\n".join("%s. %s" % (labels[k], c["text"].strip()) for k, c in enumerate(order)),
            "answer": labels[[c["label"] for c in order].index(correct["label"])]}


def layout_livemath(upstream, id_split, seed, *, val=128):
    """(rows by part, sealed-test ids, source file hashes, notes). The paper's test items are never rendered."""
    root = safe_path(upstream)
    test = _ids(id_split, "test")
    published = livemath_pilot.published_months(id_split)
    pilot_items, _ = livemath_pilot.draw(upstream, published, PILOT_PER_MONTH, PILOT_SEED)
    pilot_rows = [{"id": i["id"], **i["public"], "answer": i["private"]["answer"]} for i in pilot_items]
    records, files = {}, {}
    for path in sorted((root / "data").glob("*/qa_*_final.json")):
        files[str(path.relative_to(root))] = _sha(path)
        for record in json.loads(path.read_text(encoding="utf-8")):
            name = "%s:%s" % (path.parent.name, record["no"])
            require(name not in records, "Duplicate upstream item")
            records[name] = (path.parent.name, record)
    require(set(test) <= set(records) and len(set(test)) == len(test), "The paper's test ids are not all upstream")
    # the family rule "one family per item" rests on one item per source paper
    require(len({record["paper_link"] for _, record in records.values()}) == len(records),
            "Two items share a source paper: they would need one family")
    held = set(test) | {row["id"] for row in pilot_rows}
    require(not set(test) & {row["id"] for row in pilot_rows}, "A pilot item is a test item")
    rest = sorted((name for name in records if name not in held), key=lambda name: _digest(seed, "split", name))
    require(len(rest) > val, "Not enough items for a training pool")
    rows = {"eval": pilot_rows,
            "val": [render_livemath(records[name][1], records[name][0]) for name in sorted(rest[:val])],
            "train": [render_livemath(records[name][1], records[name][0]) for name in sorted(rest[val:])]}
    # the renderer here and the pilot's draw are the same rule: a pilot item rendered here is the pilot's row
    for row in pilot_rows[:20]:
        require(render_livemath(records[row["id"]][1], records[row["id"]][0]) == row,
                "The renderer differs from the pilot's")
    notes = {"family_rule": "one family per item (per source paper)",
             "exposure": {"test": "sealed: ids only, never rendered by this builder",
                          "eval": "solved once by four fixed Skill texts in the headroom pilot of 2026-10-13; "
                                  "no learner has seen them",
                          "train_val": "unused"},
             "implementation": ("scripts/pilot_livemath_headroom.py",)}
    return rows, sorted(test), files, notes


def layout_officeqa(upstream, id_split, seed):
    """The SkillOpt paper's split as it is: its training and validation items rendered in the one-call form by the
    headroom pilot's own ``draw`` (question, parsed pages, answer), its test items as ids only. ``seed`` is unused:
    nothing is drawn."""
    root = safe_path(upstream)
    items, dropped, pages = officeqa_pilot.draw(upstream, id_split)
    require(not dropped, "An item of the paper's training or validation part has no parsed page")
    rows = {part: [{"id": i["id"], **i["public"], "answer": i["private"]["answer"]}
                   for i in items if i["meta"]["part"] == part] for part in ("train", "val")}
    rows["eval"] = []
    test = [str(item["uid"]) for item in
            json.loads((safe_path(id_split) / "test" / "items.json").read_text(encoding="utf-8"))]
    files = {"officeqa_full.csv": _sha(root / "officeqa_full.csv"),
             "parsed_pages": hashlib.sha256(json.dumps(sorted(pages.items())).encode()).hexdigest()}
    notes = {"family_rule": "one family per item; the split is the SkillOpt paper's and is not document-disjoint "
                            "(items of different parts cite the same bulletins)",
             "exposure": {"test": "sealed: ids only, never rendered by this builder",
                          "eval": "none: every item is in the split",
                          "train_val": "solved once by four fixed Skill texts in the headroom pilot of 2026-10-13; "
                                       "the paper's checkpoint Skill was learned and selected on them"},
             "implementation": ("scripts/pilot_livemath_headroom.py", "scripts/pilot_officeqa_headroom.py",
                                "skillopt/envs/officeqa/tool_runtime.py")}
    return rows, sorted(test), files, notes


LAYOUTS = {"livemath": layout_livemath, "officeqa": layout_officeqa}


def data(benchmark, upstream, id_split, output, *, revision, seed=20261013):
    require(benchmark in LAYOUTS, "No layout for this benchmark yet")
    out = safe_path(output)
    require(not out.exists(), "Use a new directory")
    require(len(revision) == 40, "Give the 40-character source revision")
    rows, test, files, notes = LAYOUTS[benchmark](upstream, id_split, seed)
    ids = {part: [row["id"] for row in rows[part]] for part in ("train", "val", "eval")}
    everything = ids["train"] + ids["val"] + ids["eval"] + test
    require(len(set(everything)) == len(everything), "An item is in two parts")
    family = lambda name: "%s:%s" % (benchmark, name)  # noqa: E731  one family per item
    label = "%s:%s:%s" % (benchmark, revision[:12], LAYOUT_VERSION)
    importer = getattr(datasets, "import_" + benchmark)
    dev = importer(rows["train"], partition="development", revision=label,
                   family_map={name: family(name) for name in ids["train"]})
    confirmation = importer(rows["val"], partition="skill_confirmation", revision=label,
                            family_map={name: family(name) for name in ids["val"]})
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "dev_panel.json", dev)
    write_json(out / "val_panel.json", confirmation)
    blocks = []
    for start in range(0, len(rows["eval"]), BLOCK):
        name = "block_e%02d" % (start // BLOCK + 1)
        (out / "eval_blocks" / name).mkdir(parents=True)
        path = out / "eval_blocks" / name / "items.json"
        path.write_text(json.dumps(rows["eval"][start:start + BLOCK], ensure_ascii=False, indent=2), encoding="utf-8")
        blocks.append({"block": name, "tasks": len(rows["eval"][start:start + BLOCK]), "sha256": _sha(path)})
    record = seal({"version": LAYOUT_VERSION, "benchmark": benchmark, "seed": seed,
                   "source": {"revision": revision, "files": files,
                              "id_split_sha256": {name: _sha(safe_path(id_split) / name)
                                                  for name in ("split_manifest.json", "train/items.json",
                                                               "val/items.json", "test/items.json")}},
                   "panel_revision": label, "family_rule": notes["family_rule"],
                   "parts": {"train": [{"task_id": n, "family_id": family(n)} for n in ids["train"]],
                             "val": [{"task_id": n, "family_id": family(n)} for n in ids["val"]],
                             "test": [{"task_id": n, "family_id": family(n)} for n in test]},
                   "evaluation_blocks": {"items": ids["eval"], "blocks": blocks},
                   "counts": {**{part: len(ids[part]) for part in ids}, "test": len(test)},
                   "dev_panel_sha256": _sha(out / "dev_panel.json"), "val_panel_sha256": _sha(out / "val_panel.json"),
                   "exposure": notes["exposure"],
                   "implementation_sha256": {name: _sha(PROJECT_ROOT / name) for name in notes["implementation"]},
                   "builder_sha256": _sha(Path(__file__)), "model_calls": 0})
    write_json(out / "layout.json", record)
    return record


def _layout(directory):
    d = safe_path(directory)
    layout = read_json(d / "layout.json", sealed=True)
    require(layout["version"] == LAYOUT_VERSION and _sha(d / "dev_panel.json") == layout["dev_panel_sha256"]
            and _sha(d / "val_panel.json") == layout["val_panel_sha256"]
            and all(_sha(d / "eval_blocks" / block["block"] / "items.json") == block["sha256"]
                    for block in layout["evaluation_blocks"]["blocks"]), "Materialised panels or blocks changed")
    dev, val = read_json(d / "dev_panel.json"), read_json(d / "val_panel.json")
    datasets.validate_panel(dev)
    datasets.validate_panel(val)
    pairs = lambda panel: [{"task_id": t["task_id"], "family_id": t["family_id"]} for t in panel["tasks"]]  # noqa: E731
    require(dev["benchmark"] == val["benchmark"] == layout["benchmark"]
            and all(t["partition"] == "development" for t in dev["tasks"])
            and all(t["partition"] == "skill_confirmation" for t in val["tasks"])
            and sorted(pairs(dev), key=str) == sorted(layout["parts"]["train"], key=str)
            and sorted(pairs(val), key=str) == sorted(layout["parts"]["val"], key=str),
            "Panels differ from the sealed layout")
    return d, layout


def study(base, directories, output):
    """The extension study protocol: study F's model, service, retry options, lock and Skill budget, verbatim;
    the new benchmarks' development panels bound by path and hash. No reference plans, no evaluation sources:
    test cells of the extension benchmarks are not provided by this protocol."""
    base_root, base_protocol = tool._study(base)
    require(base_protocol["version"] != tool.EXTENSION_STUDY, "Derive the extension from study F itself")
    out = safe_path(output)
    require(not out.exists(), "Use a new directory")
    roles, files, layouts = {}, {}, {}
    for directory in directories:
        d, layout = _layout(directory)
        benchmark = layout["benchmark"]
        require(benchmark not in roles and benchmark in tool.EXTENSION_BENCHMARKS, "Unexpected or repeated benchmark")
        roles[benchmark] = {"runtime": {}, "path": str(d / "dev_panel.json")}
        files[str(d / "dev_panel.json")] = layout["dev_panel_sha256"]
        layouts[benchmark] = {"directory": str(d), "layout_hash": layout["record_hash"]}
    require(roles, "Give at least one materialised benchmark")
    copied = {key: deepcopy(base_protocol[key]) for key in ("model", "learning_model_service",
                                                             "learning_client_options") if key in base_protocol}
    protocol = seal({"version": tool.EXTENSION_STUDY, "root": str(out),
                     "derived_from": {"study": str(base_root), "protocol_hash": base_protocol["record_hash"],
                                      "copied": sorted(copied) + ["config.native_lock",
                                                                  "config.learning_recovery_policy"]},
                     **copied,
                     "config": {"native_lock": base_protocol["config"]["native_lock"],
                                "learning_recovery_policy": deepcopy(base_protocol["config"]["learning_recovery_policy"])},
                     "order": sorted(roles), "roles": roles, "references": {}, "files": files, "layouts": layouts,
                     "test_cells": "not provided: the sealed test parts are listed by id in the split only",
                     "builder_sha256": _sha(Path(__file__)), "model_calls": 0})
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "protocol.json", protocol)
    tool._study(out)  # the tools accept what was written
    return protocol


def split(study_dir, output):
    """The split manifest the stage tools read (train / val / test by task and family id; the evaluation blocks are
    recorded beside the split because they are deliberately outside it)."""
    root, protocol = tool._study(study_dir)
    require(protocol["version"] == tool.EXTENSION_STUDY, "The split belongs to an extension study")
    target = safe_path(output)
    require(not target.exists(), "Use a new file")
    splits, sources, usage, blocks, exposure, counts = {}, {}, {}, {}, {}, {}
    for benchmark in protocol["order"]:
        d, layout = _layout(protocol["layouts"][benchmark]["directory"])
        require(layout["record_hash"] == protocol["layouts"][benchmark]["layout_hash"]
                and protocol["files"][str(d / "dev_panel.json")] == layout["dev_panel_sha256"],
                "The study was built from another layout")
        splits[benchmark] = {**{part: layout["parts"][part] for part in ("train", "val", "test")}, "reserve": []}
        sources[str(d / "dev_panel.json")] = layout["dev_panel_sha256"]
        sources[str(d / "val_panel.json")] = layout["val_panel_sha256"]
        usage[benchmark] = {"protocol_hash": protocol["record_hash"],
                            "learning_panel_sha256": layout["dev_panel_sha256"],
                            "learning_tasks": layout["counts"]["train"]}
        blocks[benchmark] = layout["evaluation_blocks"]
        exposure[benchmark] = layout["exposure"]
        counts[benchmark] = layout["counts"]
        seen = [e["task_id"] for part in ("train", "val", "test") for e in layout["parts"][part]]
        families = [e["family_id"] for part in ("train", "val", "test") for e in layout["parts"][part]]
        require(len(set(seen)) == len(seen) and len(set(families)) == len(families)
                and not set(seen) & set(layout["evaluation_blocks"]["items"]), "A task or family crosses parts")
    record = seal({"version": tool.EXTENSION_SPLIT, "study": str(root), "parts": ["train", "val", "test", "reserve"],
                   "splits": splits, "sources": sources, "f_study_usage": usage, "evaluation_blocks": blocks,
                   "exposure": exposure, "counts": counts,
                   "family_rule": "a family never crosses parts; one family per item for these benchmarks",
                   "builder_sha256": _sha(Path(__file__)), "model_calls": 0, "contains_private_content": False})
    write_json(target, record)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("data")
    for name in ("benchmark", "upstream", "id-split", "revision", "output"):
        d.add_argument("--" + name, required=True)
    d.add_argument("--seed", type=int, default=20261013)
    s = sub.add_parser("study")
    s.add_argument("--base", required=True)
    s.add_argument("--data", action="append", required=True)
    s.add_argument("--output", required=True)
    p = sub.add_parser("split")
    p.add_argument("--study", required=True)
    p.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "data":
        record = data(args.benchmark, args.upstream, args.id_split, args.output, revision=args.revision, seed=args.seed)
        value = {"benchmark": record["benchmark"], "counts": record["counts"],
                 "blocks": len(record["evaluation_blocks"]["blocks"]), "record_hash": record["record_hash"]}
    elif args.command == "study":
        record = study(args.base, args.data, args.output)
        value = {"version": record["version"], "order": record["order"], "record_hash": record["record_hash"]}
    else:
        record = split(args.study, args.output)
        value = {"version": record["version"], "counts": record["counts"], "record_hash": record["record_hash"]}
    print(json.dumps(value, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
