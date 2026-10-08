"""Canonical five-domain train/val/test split (fivebench-split-v2; ids only, zero model calls).

One split shared by every baseline (No-Skill, SkillOpt, GEPA) and by the main method:
``train`` may be used for learning, ``val`` for selection, ``test`` only for final
reporting, and ``reserve`` for nothing yet. It reuses the project's existing
partitions wherever they exist -- development -> train, skill_confirmation -> val,
final -> test, verifier_calibration -> reserve (BigCodeBench, KOR-Bench, and
SpreadsheetBench, whose partitions equal the native SkillOpt train/val/test) -- and
the native SkillOpt splits elsewhere (SearchQA: train/val, a fixed seeded 400-task
sample of test, the remaining native test as reserve; ALFWorld: train,
valid_seen, valid_unseen). Families follow the panel importers (a KOR rule, an
ALFWorld scenario, an exact SearchQA question), and no task or family may cross
parts. The builder also proves that the five-domain study F evaluated exactly
the train part and learned only inside it, and binds that proof to the study's
protocol, reference plans and learning panels, so its Skills can be tested on
``test``. "Held out from study F" is not "historically unexposed": known earlier
use of val/test items by this project is recorded per benchmark, and the split
is not an exposure-filtered independent final. Only task and family ids are
written; no question, answer or test. (v1 was the pre-review draft: the same
assignment without the study binding and exposure notes.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.continual_eval.datasets import _family

VERSION = "fivebench-split-v2"
SEED = "fivebench-split-v1-20261005"  # unchanged from the v1 draft: the assignment is identical
PARTS = ("train", "val", "test", "reserve")
PROJECT_PARTITIONS = {"train": "development", "val": "skill_confirmation", "test": "final",
                      "reserve": "verifier_calibration"}
SEARCHQA_TEST = 400
UNRECORDED = ("no recorded evaluation of the val, test or reserve partitions was found (run plans on the "
              "development machine searched by panel path on 2026-10-05); not a proof of non-exposure")
EXPOSURE = {
    "bigcodebench": UNRECORDED,
    "korbench": UNRECORDED,
    "searchqa": "the native SkillOpt train/val/test items all received predictions in the project's earlier GPT "
                "reproduction of native SkillOpt (docs/skill-validation-baselines-20260928.md); val, test and "
                "reserve are held out from study F but are not historically unexposed",
    "spreadsheetbench": "val and test equal the native SkillOpt val/test of Verified 400; held out from study F; "
                        "earlier use outside study F was not audited",
    "alfworld": "native SkillOpt valid_seen / valid_unseen manifests; held out from study F; earlier use "
                "outside study F was not audited",
}


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _entries(tasks):
    return sorted(({"task_id": str(t["task_id"]), "family_id": str(t["family_id"])} for t in tasks),
                  key=lambda e: e["task_id"])


def _panel_tasks(path):
    tasks = read_json(path)["tasks"]
    require(type(tasks) is list and tasks, "Empty panel")
    return tasks


def _from_partitions(folder, parts, sources):
    """Project partition panels -> parts, checking each task carries its partition label."""
    out = {}
    for part, partition in parts.items():
        path = safe_path(folder) / f"{partition}.json"
        tasks = _panel_tasks(path)
        require(all(t["partition"] == partition for t in tasks), "Partition label mismatch in " + str(path))
        sources[str(path)] = _sha(path)
        out[part] = _entries(tasks)
    return out


def _searchqa(folder, sources):
    items = {}
    for part in ("train", "val", "test"):
        path = safe_path(folder) / part / "items.json"
        sources[str(path)] = _sha(path)
        items[part] = read_json(path)
        require(all({"id", "question", "context", "answers"} <= set(i) for i in items[part]),
                "SearchQA split must be materialized")

    def entries(rows):
        return _entries({"task_id": str(r["id"]), "family_id": _family(str(r["id"]), {"question": r["question"]}, None)}
                        for r in rows)
    test = sorted(items["test"], key=lambda r: str(r["id"]))
    chosen = set(random.Random(SEED + ":searchqa:test").sample([str(r["id"]) for r in test], SEARCHQA_TEST))
    return {"train": entries(items["train"]), "val": entries(items["val"]),
            "test": entries(r for r in test if str(r["id"]) in chosen),
            "reserve": entries(r for r in test if str(r["id"]) not in chosen)}


def _alfworld(folder, sources):
    out = {}
    for part, native in (("train", "train"), ("val", "val"), ("test", "test")):
        path = safe_path(folder) / native / "items.json"
        sources[str(path)] = _sha(path)
        rows = read_json(path)
        expected = {"train": "train", "val": "valid_seen", "test": "valid_unseen"}[part]
        require(all(Path(r["gamefile"]).parts[1] == expected for r in rows), "Unexpected ALFWorld source split")
        # The importer's family: trials sharing one scenario (json_2.1.1/<split>/<scenario>/<trial>/game).
        out[part] = _entries({"task_id": str(r["id"]),
                              "family_id": _family(str(r["id"]), {"scenario": Path(r["gamefile"]).parts[2]}, None)}
                             for r in rows)
    out["reserve"] = []
    return out


def _check(benchmark, parts):
    seen_tasks, seen_families = {}, {}
    for part in PARTS:
        tasks = [e["task_id"] for e in parts[part]]
        require(len(tasks) == len(set(tasks)), f"{benchmark}: duplicate task in {part}")
        for e in parts[part]:
            require(seen_tasks.setdefault(e["task_id"], part) == part, f"{benchmark}: task crosses parts")
            require(seen_families.setdefault(e["family_id"], part) == part, f"{benchmark}: family crosses parts")
    require(all(parts[p] for p in ("train", "val", "test")), f"{benchmark}: empty train/val/test")


def _study_usage(f_study, benchmark, parts):
    """F's evaluated panel must be exactly train, and its learning tasks must lie inside train."""
    protocol = read_json(safe_path(f_study) / "protocol.json", sealed=True)
    plan = read_json(safe_path(protocol["references"][benchmark]["root"]) / "plan.json", sealed=True)
    require(plan["record_hash"] == protocol["references"][benchmark]["plan_hash"], "Reference plan changed")
    evaluated = {str(t["task_id"]) for t in plan["tasks"] if t["benchmark"] == benchmark}
    learning = {str(t["task_id"]) for t in read_json(protocol["roles"][benchmark]["path"])["tasks"]}
    train = {e["task_id"] for e in parts["train"]}
    held = {e["task_id"] for p in ("val", "test", "reserve") for e in parts[p]}
    require(evaluated == train, f"{benchmark}: F's evaluation panel is not exactly train")
    require(learning <= train and not learning & held, f"{benchmark}: F learned outside train")
    return {"protocol_hash": protocol["record_hash"], "reference_plan_hash": plan["record_hash"],
            "learning_panel_sha256": _sha(protocol["roles"][benchmark]["path"]),
            "f_evaluated_tasks": len(evaluated), "f_learning_tasks": len(learning)}


def build(*, f_study, searchqa_split, alfworld_split, sheet_panels, bcb_partitions, kor_panels):
    sources, splits = {}, {}
    splits["bigcodebench"] = _from_partitions(bcb_partitions, PROJECT_PARTITIONS, sources)
    sheet = dict(PROJECT_PARTITIONS)
    sheet.pop("reserve")  # SpreadsheetBench has no verifier_calibration partition
    splits["spreadsheetbench"] = {**_from_partitions(sheet_panels, sheet, sources), "reserve": []}
    splits["searchqa"] = _searchqa(searchqa_split, sources)
    splits["korbench"] = _from_partitions(kor_panels, PROJECT_PARTITIONS, sources)
    splits["alfworld"] = _alfworld(alfworld_split, sources)
    usage = {}
    for benchmark, parts in splits.items():
        _check(benchmark, parts)
        usage[benchmark] = _study_usage(f_study, benchmark, parts)
    counts = {b: {p: len(parts[p]) for p in PARTS} for b, parts in splits.items()}
    return seal({"version": VERSION, "seed": SEED, "parts": {
                     "train": "learning only", "val": "selection only (repeated use allowed)",
                     "test": "final reporting only; never used for learning or selection",
                     "reserve": "not assigned; not used by study F"},
                 "exposure": EXPOSURE,
                 "claim": "val/test/reserve are held out from study F's learning, selection and evaluation; "
                          "not an exposure-filtered independent final",
                 "project_partitions": PROJECT_PARTITIONS, "searchqa_test_sample": SEARCHQA_TEST,
                 "counts": counts, "splits": splits, "sources": sources, "f_study_usage": usage,
                 "family_rule": "importer families: BCB/Sheet/KOR as frozen in the project partitions, KOR = rule, "
                                "ALFWorld = scenario, SearchQA = exact normalized question",
                 "builder_sha256": _sha(Path(__file__)), "model_calls": 0,
                 "contains_private_content": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New directory for split_manifest.json")
    parser.add_argument("--f-study", required=True)
    parser.add_argument("--searchqa-split", required=True)
    parser.add_argument("--alfworld-split", required=True)
    parser.add_argument("--sheet-panels", required=True)
    parser.add_argument("--bcb-partitions", required=True)
    parser.add_argument("--kor-panels", required=True)
    args = parser.parse_args()
    out = safe_path(args.output)
    require(not out.exists(), "Use a new output directory")
    value = build(f_study=args.f_study, searchqa_split=args.searchqa_split, alfworld_split=args.alfworld_split,
                  sheet_panels=args.sheet_panels, bcb_partitions=args.bcb_partitions, kor_panels=args.kor_panels)
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "split_manifest.json", value)
    print(json.dumps({"record_hash": value["record_hash"], "counts": value["counts"],
                      "f_study_usage": value["f_study_usage"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
