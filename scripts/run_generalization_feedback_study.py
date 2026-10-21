#!/usr/bin/env python3
"""Generalization feedback study (``fivebench-generalization-feedback-study-v1``; design
docs/handoff/generalization-architecture-20261015.md; module skillopt/feedback_study/generalization_feedback.py).

Steps (all zero calls except the generation, the calibration probes and ``run``):
  split    --template <v10 OfficeQA stage> --held-out 16 --output <split.json>
           the template's training tasks split by bulletin file into L (learn) and H (held out)
  (generate: scripts/generate_officeqa_diagnostic_tasks.py on L, scripts/generate_officeqa_transfer_tasks.py on H, page-only)
  pools    --template <stage> --split <split.json> --generation-d <dir> --generation-t <dir> --output <pools dir>
           items written from L's pages -> diagnostic candidates (pool-D.json), from H's pages -> transfer pool (pool-T.json)
  (calibrate: scripts/weak_solver_probe.py run --model glm-5.3 --skill parent=f:<template parent> --runs 3 on each pool)
  prepare  --template <stage> --pools <pools dir> --calibration <D probe dir> <T probe dir> --output <new dir>
           --blocks N [--series L]       go/no-go (registered): >= 30 informative diagnostic items, >= 25 non-ceiling
                                         transfer items; the study panel = L's real tasks + informative D + T
  run      --template <stage> --output <dir>          F's native lock, client check, one run, never resumed
  report   --output <dir> [<dir> ...]                 the registered analysis over the pooled sealed blocks of a series
"""
from __future__ import annotations

import argparse
import fcntl
import json
import random
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.continual_eval.core import read_json, require, safe_path, write_json  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402

TEMPLATE_KEYS = ("model", "runtime", "parent_skill", "seed", "recovery_policy")
MIN_INFORMATIVE_D, MIN_NONCEILING_T, CALIBRATION_RUNS = 30, 25, 3
_FILE = re.compile(r"### (\S+\.txt) page (\d+)")


def _template(template_dir):
    root = safe_path(template_dir)
    value = read_json(root / "manifest.json", sealed=True)
    panel = read_json(root / "panel.json")
    record = read_json(root / "stage.json", sealed=True)
    require(record["manifest_hash"] == value["record_hash"] and digest(panel) == value["panel_hash"]
            and value["benchmark"] == "officeqa", "The template stage's manifest and panel do not match its record")
    return root, value, panel, record


def held_out_tasks(files, held_out, seed):
    """Tasks that share a bulletin file form one component; components are shuffled by ``seed`` and added to H until it
    holds at least ``held_out`` tasks. Returns H's task ids (sorted)."""
    parent = {t: t for t in files}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner = {}
    for task, names in sorted(files.items()):
        for name in sorted(names):
            if name in owner:
                parent[find(task)] = find(owner[name])
            else:
                owner[name] = task
    components = {}
    for task in sorted(files):
        components.setdefault(find(task), []).append(task)
    groups = sorted(components.values())
    random.Random(seed).shuffle(groups)
    held = []
    for group in groups:
        if len(held) >= held_out:
            break
        held.extend(group)
    return sorted(held)


def informative(counts):
    """Items the parent failed at least once in at least two known calibration runs."""
    return sorted(i for i, (passes, known) in counts.items() if known >= 2 and passes < known)


def split(template_dir, output, held_out=16):
    """L/H by bulletin file: tasks sharing a bulletin file stay on one side (connected components), components are
    shuffled by a seed derived from the template and added to H until it holds ``held_out`` tasks."""
    root, value, panel, _ = _template(template_dir)
    train = [t for t in panel["tasks"] if t["family_id"] in set(value["train_families"])]
    files = {t["task_id"]: {f for f, _ in _FILE.findall(t["public"]["context"])} for t in train}
    require(all(files.values()), "Every training task names its bulletin file")
    held = held_out_tasks(files, held_out, digest({"split": "generalization-feedback-v1", "manifest": value["record_hash"]}))
    learn = sorted(t for t in files if t not in held)
    record = seal({"template_stage": root.name, "manifest_hash": value["record_hash"], "learn_tasks": learn,
                   "held_out_tasks": sorted(held), "files": {t: sorted(f) for t, f in sorted(files.items())},
                   "rule": "bulletin-file components, seeded shuffle, H filled to at least %d tasks" % held_out})
    require(not {f for t in learn for f in files[t]} & {f for t in held for f in files[t]}, "A bulletin file crosses L/H")
    write_json(safe_path(output), record)
    return record


def _task(item, partition, family):
    return {"task_id": item["id"], "family_id": family, "project_id": "", "partition": partition,
            "public": {"question": item["question"], "context": item["context"]}, "private": {"answer": item["answer"]}}


def pools(template_dir, split_path, generation_d, generation_t, output):
    """Zero calls: the diagnostic candidates (learn-side generation, generator v2) and the transfer pool (held-out-side
    generation, page-only), each checked against the split, the template's seed and its own side."""
    from scripts import generate_officeqa_diagnostic_tasks as gen_d
    from scripts import generate_officeqa_transfer_tasks as gen_t

    root, value, panel, _ = _template(template_dir)
    cut = read_json(safe_path(split_path), sealed=True)
    require(cut["manifest_hash"] == value["record_hash"], "The split belongs to another template")
    train = {digest(t): t for t in panel["tasks"] if t["family_id"] in set(value["train_families"])}
    by_id = {t["task_id"]: t for t in train.values()}
    sides = {}
    for kind, directory, side, partition, prefix in ((gen_d, generation_d, "learn", "development", "officeqa:gen-d:"),
                                                     (gen_t, generation_t, "held_out", "skill_confirmation", "officeqa:gen-t:")):
        path, record, result = kind.check(directory)
        ids = cut["learn_tasks"] if side == "learn" else cut["held_out_tasks"]
        require(record["side"] == side and record["lh_split_hash"] == cut["record_hash"] and record["seed"] == value["seed"]
                and record["source_task_hashes"] == sorted(digest(by_id[i]) for i in ids),
                "The %s generation is not this template's %s side" % (side, side))
        derivations = kind.derivations(directory)
        items = json.loads(Path(path).read_text(encoding="utf-8"))
        tasks = []
        for item in items:
            source = train[derivations[item["id"]]["source_task_hash"]]
            require(source["task_id"] in set(ids), "An item's source task is not on its side")
            tasks.append(_task(item, partition, prefix + source["task_id"]))
        sides[side] = (tasks, derivations, {i["id"]: i["category"] for i in items}, record, result)
    out = safe_path(output)
    require(not out.exists(), "Use a new directory")
    out.mkdir(parents=True, mode=0o700)
    d_tasks, d_derivations, d_categories, d_record, d_result = sides["learn"]
    t_tasks, _, t_categories, t_record, t_result = sides["held_out"]
    write_json(out / "pool-D.json", {"tasks": d_tasks})
    write_json(out / "pool-T.json", {"tasks": t_tasks})
    write_json(out / "derivations.json", seal({"derivations": d_derivations}))
    summary = seal({"template_stage": root.name, "manifest_hash": value["record_hash"], "split_hash": cut["record_hash"],
                    "learn_tasks": cut["learn_tasks"], "held_out_tasks": cut["held_out_tasks"],
                    "generation_hash": {"learn": d_record["record_hash"], "held_out": t_record["record_hash"]},
                    "generation_result_hash": {"learn": d_result["record_hash"], "held_out": t_result["record_hash"]},
                    "diagnostic_candidates": sorted(t["task_id"] for t in d_tasks),
                    "transfer_items": sorted(t["task_id"] for t in t_tasks),
                    "categories": {**d_categories, **t_categories},
                    "pool_D_hash": digest({"tasks": d_tasks}), "pool_T_hash": digest({"tasks": t_tasks})})
    write_json(out / "pools.json", summary)
    return summary


def _calibration(directory, pool_path, partition, parent_skill):
    """Per item: [passes, known runs] of the parent in a COMPLETED probe of exactly this pool and parent text: the
    probe's config, summary and the complete item x run inventory of its records are all checked; the inventory's hash
    is returned for the protocol."""
    from scripts import weak_solver_probe as probe

    d = safe_path(directory)
    config = json.loads((d / "config.json").read_text())
    summary = json.loads((d / "summary.json").read_text())
    rows = probe.load_items("%s:%s" % (pool_path, partition))
    ids = [r["id"] for r in rows]
    require(summary.get("status") == "completed" and summary.get("config_hash") == probe.digest(config)
            and config["version"] == probe.VERSION and config["model"] == "glm-5.3" and config["reasoning_effort"] == "low"
            and config["benchmark"] == "officeqa" and config["runs"] == CALIBRATION_RUNS
            and config["item_ids_hash"] == probe.digest(sorted(ids))
            and config["items_hash"] == probe.digest(sorted(probe.digest(r) for r in rows))
            and set(config["skills"]) == {"parent"} and config["skills"]["parent"]["hash"] == probe.digest(parent_skill),
            "Not a completed calibration of this pool and parent")
    seen, inventory = set(), []
    counts = {i: [0, 0] for i in ids}
    files = sorted((d / "records").rglob("*.json"))
    for path in files:
        r = json.loads(path.read_text())
        key = (r.get("item"), r.get("run"))
        require(path.parent.name == "parent" and r.get("skill") == "parent" and r.get("item") in counts
                and r.get("run") in range(CALIBRATION_RUNS) and key not in seen
                and path.name == "%s.%d.json" % (probe.digest(r["item"])[:24], r["run"])
                and r.get("status") in ("pass", "fail", "unknown"), "A calibration record is not this inventory's")
        seen.add(key)
        inventory.append([r["item"], r["run"], r["status"]])
        if r["status"] in ("pass", "fail"):
            counts[r["item"]][0] += r["status"] == "pass"
            counts[r["item"]][1] += 1
    require(len(seen) == len(ids) * CALIBRATION_RUNS, "The calibration inventory is incomplete")
    parent = summary["per_skill"]["parent"]
    require([parent["pass"], parent["fail"], parent["unknown"]] ==
            [sum(1 for x in inventory if x[2] == s) for s in ("pass", "fail", "unknown")], "Summary and records differ")
    return {"probe_config_hash": probe.digest(config), "inventory_hash": digest(sorted(inventory)), "counts": counts}


def spec_from_inputs(template_dir, pools_dir, calibration_dirs, blocks, series=None):
    from skillopt.feedback_study import generalization_feedback as gf

    root, value, panel, record = _template(template_dir)
    pdir = safe_path(pools_dir)
    summary = read_json(pdir / "pools.json", sealed=True)
    require(summary["manifest_hash"] == value["record_hash"], "The pools belong to another template")
    pool_d, pool_t = read_json(pdir / "pool-D.json"), read_json(pdir / "pool-T.json")
    require(digest(pool_d) == summary["pool_D_hash"] and digest(pool_t) == summary["pool_T_hash"], "A pool changed")
    derivations = read_json(pdir / "derivations.json", sealed=True)["derivations"]
    cal_d = _calibration(calibration_dirs[0], pdir / "pool-D.json", "development", value["parent_skill"])
    cal_t = _calibration(calibration_dirs[1], pdir / "pool-T.json", "skill_confirmation", value["parent_skill"])
    informative_d, nonceiling = informative(cal_d["counts"]), informative(cal_t["counts"])
    distribution = lambda counts: {"%d/%d" % (p, k): sum(1 for v in counts.values() if v == [p, k])
                                   for p, k in sorted({tuple(v) for v in counts.values()})}
    calibration = {"rule": "a diagnostic item is informative when the parent failed it at least once in >= 2 known of "
                           "%d runs; the transfer pool keeps every item" % CALIBRATION_RUNS,
                   "min_informative_diagnostic": MIN_INFORMATIVE_D, "min_nonceiling_transfer": MIN_NONCEILING_T,
                   "diagnostic": {"candidates": len(cal_d["counts"]), "informative": len(informative_d),
                                  "distribution": distribution(cal_d["counts"]), "probe_config_hash": cal_d["probe_config_hash"],
                                  "inventory_hash": cal_d["inventory_hash"]},
                   "transfer": {"items": len(cal_t["counts"]), "nonceiling": len(nonceiling),
                                "distribution": distribution(cal_t["counts"]), "probe_config_hash": cal_t["probe_config_hash"],
                                "inventory_hash": cal_t["inventory_hash"]}}
    go = len(informative_d) >= MIN_INFORMATIVE_D and len(nonceiling) >= MIN_NONCEILING_T
    require(set(informative_d) <= set(summary["diagnostic_candidates"]), "Informative items come from the diagnostic pool")
    keep_d = [t for t in pool_d["tasks"] if t["task_id"] in set(informative_d)]
    learn, held = set(summary["learn_tasks"]), set(summary["held_out_tasks"])
    real_learn = [t for t in panel["tasks"] if t["family_id"] in set(value["train_families"]) and t["task_id"] in learn]
    require(len(real_learn) == len(learn) and not {t["task_id"] for t in real_learn} & held, "The learn tasks are not the split's")
    study_panel = {**{k: panel[k] for k in ("version", "benchmark", "dataset_revision", "provenance")},
                   "tasks": real_learn + keep_d + pool_t["tasks"]}
    train_families = sorted({t["family_id"] for t in real_learn + keep_d})
    selection_families = sorted({t["family_id"] for t in pool_t["tasks"]})
    template = {"panel_hash": digest(study_panel), "train_families": train_families,
                "selection_families": selection_families, **{k: value[k] for k in TEMPLATE_KEYS}}
    kept = {i: derivations[i] for i in informative_d}
    transfer = sorted(t["task_id"] for t in pool_t["tasks"])
    pools_spec = {"learn_tasks": sorted(learn), "held_out_tasks": sorted(held), "diagnostic_items": informative_d,
                  "transfer_items": transfer, "categories": {i: summary["categories"][i] for i in informative_d + transfer}}
    source = {"template_stage": root.name, "stage_hash": record["record_hash"], "manifest_hash": value["record_hash"],
              "pools_hash": summary["record_hash"], "generation_hash": summary["generation_hash"],
              "split_hash": summary["split_hash"], "go": go, **({"series": series} if series else {})}
    spec = gf.build_spec(template, pools_spec, digest(kept), calibration, blocks, source)
    return spec, study_panel, kept, record, go


def prepare(template_dir, pools_dir, calibration_dirs, output, blocks, series=None):
    from skillopt.feedback_study import generalization_feedback as gf

    spec, panel, derivations, _, go = spec_from_inputs(template_dir, pools_dir, calibration_dirs, blocks, series)
    root = safe_path(output) / "study"
    require(not (root / "started.json").exists(), "The study has already started")
    if not go:
        write_json(safe_path(output) / "no-go.json", seal({"calibration": spec["calibration"],
                                                          "reason": "registered go/no-go not met: the study is not run"}))
        return spec, False
    write_json(root / "protocol.json", spec)
    write_json(root / "study.json", gf._manifest(spec, panel))
    write_json(safe_path(output) / "inputs.json", seal({"pools": str(safe_path(pools_dir)),
                                                       "calibration": [str(safe_path(c)) for c in calibration_dirs]}))
    return spec, True


def run(template_dir, output):
    from scripts import continue_fivebench_baselines as sequence
    from skillopt.feedback_study.generalization_feedback import _manifest, run_study

    out = safe_path(output)
    saved = read_json(out / "study" / "protocol.json", sealed=True)
    inputs = read_json(out / "inputs.json", sealed=True)
    spec, panel, derivations, record, go = spec_from_inputs(template_dir, inputs["pools"], inputs["calibration"],
                                                            saved["blocks"], saved["source"].get("series"))
    require(go, "The registered go/no-go is not met")
    with safe_path(record["native_lock"]).open("a") as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        require(saved == spec and read_json(out / "study" / "study.json", sealed=True) == _manifest(spec, panel),
                "The prepared protocol or manifest differs from the one rebuilt from the inputs and current code")
        sequence.check_client_service(record["repo"], spec["template"]["model"], out / "client-check",
                                      record["learning_model_service"], client_options=record["client_options"])
        result = run_study(spec, panel, derivations, out / "study", repo=record["repo"])
        if result["status"] == "completed":
            sequence.verify_service(out / "study", record["learning_model_service"])
    return result


def _comparable(spec):
    value = {k: v for k, v in spec.items() if k not in ("record_hash", "blocks")}
    value["source"] = {k: v for k, v in spec["source"].items() if k != "series"}
    return json.dumps(value, sort_keys=True)


def report(outputs, allow_closure_differences=False):
    """Zero calls: the registered analysis over the sealed blocks of one or more studies of one series."""
    from skillopt.feedback_study import generalization_feedback as gf

    candidates, outcomes, protocols, closures, seen, lines = [], [], set(), {}, set(), []
    first = None
    for output in outputs:
        root = safe_path(output) / "study"
        spec = read_json(root / "protocol.json", sealed=True)
        first = first or spec
        protocols.add(_comparable(spec))
        study = read_json(root / "study.json", sealed=True)["study"]
        closures.setdefault(digest({k: study[k] for k in ("study_sources", "native_sources", "code_closure")}), []).append(root.parent.name)
        require((root / "result.json").exists(), "A study without a result is not pooled: " + root.parent.name)
        result = gf.verify_result(root)  # zero calls: bindings and the evidence inventory
        lines.append("study %s series %s: %s %s | costs %s" % (
            root.parent.name, spec["source"].get("series"), None if result is None else result["status"],
            None if result is None else result.get("reason"),
            None if result is None else {k: result["costs"].get(k) for k in ("solver_calls", "verifier_calls", "reflection_calls",
                                                                            "reported_tokens_known_subtotal", "unknown_cost_attempts")}))
        for b in sorted((root / "blocks").iterdir(), key=lambda p: int(p.name)) if (root / "blocks").exists() else []:
            if not (b / "outcome.json").exists():
                continue
            c, o = read_json(b / "candidates.json", sealed=True), read_json(b / "outcome.json", sealed=True)
            require(o["candidates_hash"] == c["record_hash"] and c["protocol_hash"] == spec["record_hash"] == o["protocol_hash"],
                    "A block's records do not bind")
            require(c["record_hash"] not in seen, "The same sealed block was given twice")
            seen.add(c["record_hash"])
            candidates.append(c)
            outcomes.append(o)
    require(len(protocols) == 1, "The studies differ beyond the series label and the block count: report them separately")
    if len(closures) != 1:
        require(allow_closure_differences, "Different implementation identities: pass --allow-closure-differences to pool")
        lines.append("DISCLOSURE: pooled across implementation identities %s" % closures)
    if not outcomes:
        return "\n".join(lines + ["no completed block"])
    a = gf.analyze(first, candidates, outcomes)
    p = a["parent"]
    lines.append("blocks %d | parent on the transfer pool (two passes): %d/%d (unknown %d)" % (a["blocks"], p["pass"], p["positions"], p["unknown"]))
    for arm, v in a["arms"].items():
        lines.append("  %-14s pass %4d/%-4d (unknown %d) yield %.3f | dispositions %s | blocks with feedback %s" % (
            arm, v["pass"], v["positions"], v["unknown"], v["yield"], v["dispositions"], v["blocks_with_feedback"]))
    lines.append("  verifier: text authorized in %d blocks, code in %d; error modes on failed generated rows %s" % (
        a["verifier"]["text_authorized_blocks"], a["verifier"]["code_authorized_blocks"], a["verifier"]["code_error_modes"]))
    for c in a["contrasts"]:
        lines.append("  contrast %-13s - %-12s %s per block %s mean %+.2f | positions wins %d losses %d | block sign-flip p=%.4f (%s) | unknown bounds %s | supported %s" % (
            c["treatment"], c["control"], "PRIMARY" if c["primary"] else "       ", c["differences"], c["mean_difference"],
            c["paired_positions"]["wins"], c["paired_positions"]["losses"], c["block_sign_flip"]["p_value"], c["direction"],
            [round(x, 2) for x in c["unknown_sensitivity_mean_bounds"]], c["supported"]))
    for slot, counts in a["by_category"].items():
        lines.append("  by category %-14s %s" % (slot, {k: "%d/%d" % (v["pass"], v["positions"]) for k, v in sorted(counts.items())}))
    lines.append("noise reference: %s - %s (identical inputs)" % tuple(a["noise_reference"]))
    lines.append("claim limits: " + a["claim_limits"])
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("split")
    s.add_argument("--template", required=True)
    s.add_argument("--held-out", type=int, default=16)
    s.add_argument("--output", required=True)
    p = sub.add_parser("pools")
    for name in ("--template", "--split", "--generation-d", "--generation-t", "--output"):
        p.add_argument(name, required=True)
    q = sub.add_parser("prepare")
    q.add_argument("--template", required=True)
    q.add_argument("--pools", required=True)
    q.add_argument("--calibration", nargs=2, required=True)
    q.add_argument("--output", required=True)
    q.add_argument("--blocks", type=int, required=True)
    q.add_argument("--series")
    r = sub.add_parser("run")
    r.add_argument("--template", required=True)
    r.add_argument("--output", required=True)
    t = sub.add_parser("report")
    t.add_argument("--output", nargs="+", required=True)
    t.add_argument("--allow-closure-differences", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "split":
        record = split(args.template, args.output, args.held_out)
        print(json.dumps({"learn": len(record["learn_tasks"]), "held_out": len(record["held_out_tasks"])}))
    elif args.command == "pools":
        summary = pools(args.template, args.split, args.generation_d, args.generation_t, args.output)
        print(json.dumps({"diagnostic_candidates": len(summary["diagnostic_candidates"]),
                          "transfer_items": len(summary["transfer_items"])}))
    elif args.command == "prepare":
        spec, go = prepare(args.template, args.pools, args.calibration, args.output, args.blocks, args.series)
        print(json.dumps({"go": go, "calibration": spec["calibration"], "protocol_hash": spec["record_hash"]}, indent=1))
        return 0 if go else 2
    elif args.command == "run":
        result = run(args.template, args.output)
        print(json.dumps({k: result[k] for k in ("status", "reason", "completed_blocks", "blocks") if k in result}))
        return 0 if result["status"] == "completed" else 1
    else:
        print(report(args.output, args.allow_closure_differences))
    return 0


if __name__ == "__main__":
    sys.exit(main())
