#!/usr/bin/env python3
"""Generalization feedback study, runner v2 (2026-10-16; design docs/handoff/two-architectures-design-20261016.md
sections 4-5): the same study (``fivebench-generalization-feedback-study-v1`` in
skillopt/feedback_study/generalization_feedback.py, unchanged) fed by generator v3 (feature-aware, both sides from
scripts/generate_officeqa_feature_tasks.py) instead of generator v2. Runner v1 stays as it was (it imports v2 by name).

What differs from runner v1:
- ``pools``: both sides are v3 generations; a learn-side item enters the diagnostic pool only with a single part, and
  its derivation is handed to the study in the study's v1 shape (figures, expression, decimals, answer): the study's
  code layer re-evaluates v1-grammar expressions and reports "derivation_unavailable" for the others (the statistics)
  -- its note still shows the expected answer, the expression and the figure quotes -- and its leak check covers the
  expression. Multi-part learn-side items are counted and left out; the transfer pool keeps every item. Each pool's
  fidelity -- of the items it keeps, against the training profile its generation was prepared with, generator v3
  limits -- is computed here and sealed with the pools (each whole generation's too, descriptive).
- ``prepare``: the registered go/no-go of this design: both sides' fidelity passed; at least MIN_INFORMATIVE_D
  diagnostic items the parent failed at least once; and neither pool easier than the real training items by more than
  MAX_EASIER (pool pass rate minus G pass rate, the parent's pass rates over known runs; G's from a completed glm-5.3
  low probe of the template's parent text on exactly the template's training tasks).
Everything else (split, calibration checks, run, report) is runner v1's.

Usage:
  run_generalization_feedback_study_v2.py pools --template <stage> --split <split.json> --generation-d <v3 learn dir>
      --generation-t <v3 held-out dir> --profile <training profile.json> --output <new pools dir>
  run_generalization_feedback_study_v2.py prepare --template <stage> --pools <dir> --calibration <D probe> <T probe>
      --reference <probe dir>:<skill> --output <new dir> --blocks N [--series L]
  run_generalization_feedback_study_v2.py run --template <stage> --output <dir>
  run_generalization_feedback_study_v2.py report --output <dir> [<dir> ...]
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_generalization_feedback_study as v1  # noqa: E402
from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.continual_eval.core import read_json, require, safe_path, write_json  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402

VERSION = "generalization-feedback-runner-v2"
MIN_INFORMATIVE_D, MAX_EASIER = 20, 0.10


def go_rule():
    return {"fidelity": "both pools' fidelity passed: the items each pool keeps (D: the single-part learn-side items) "
                        "against the training profile its generation was prepared with, generator v3 limits",
            "min_informative_diagnostic": MIN_INFORMATIVE_D,
            "difficulty": "pool pass rate - G pass rate <= %.2f for the diagnostic and the transfer pool (the parent's "
                          "pass rates over known runs; design section 4)" % MAX_EASIER}


def tool_sha256():
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def v1_shape(derivation):
    """A single-part v3 derivation in the shape the study's code layer and leak check read."""
    require(len(derivation["parts"]) == 1, "Only a single-part item has a v1-shaped derivation")
    part = derivation["parts"][0]
    return {"source_task_hash": derivation["source_task_hash"], "question": derivation["question"],
            "figures": derivation["figures"], "expression": part["expression"], "decimals": part["decimals"],
            "answer": derivation["answer"], "category": derivation["type"]}


def pools(template_dir, split_path, generation_d, generation_t, profile, output):
    """Zero calls: runner v1's pools from two v3 generations (one per side), checked against the split, the
    template's seed and its own side; single-part learn-side items only for the diagnostic pool; both sides' fidelity."""
    from scripts import generate_officeqa_feature_tasks as gen3

    root, value, panel, _ = v1._template(template_dir)
    cut = read_json(safe_path(split_path), sealed=True)
    require(cut["manifest_hash"] == value["record_hash"], "The split belongs to another template")
    train = {digest(t): t for t in panel["tasks"] if t["family_id"] in set(value["train_families"])}
    by_id = {t["task_id"]: t for t in train.values()}
    sides, dropped = {}, 0
    for directory, side, partition, prefix in ((generation_d, "learn", "development", "officeqa:gen3-d:"),
                                               (generation_t, "held_out", "skill_confirmation", "officeqa:gen3-t:")):
        path, record, result = gen3.check(directory)
        ids = cut["learn_tasks"] if side == "learn" else cut["held_out_tasks"]
        require(record["version"] == gen3.VERSION and record["side"] == side
                and record["lh_split_hash"] == cut["record_hash"] and record["seed"] == value["seed"]
                and record["source_task_hashes"] == sorted(digest(by_id[i]) for i in ids),
                "The %s generation is not this template's %s side" % (side, side))
        derivations = gen3.derivations(directory)
        items = json.loads(Path(path).read_text(encoding="utf-8"))
        tasks, kept, categories = [], {}, {}
        for item in items:
            d = derivations[item["id"]]
            source = train[d["source_task_hash"]]
            require(source["task_id"] in set(ids), "An item's source task is not on its side")
            if side == "learn":
                if len(d["parts"]) != 1:
                    dropped += 1
                    continue
                kept[item["id"]] = v1_shape(d)
            tasks.append(v1._task(item, partition, prefix + source["task_id"]))
            categories[item["id"]] = item["category"]
        sides[side] = (tasks, kept, categories, record, result,
                       gen3.fidelity_value(directory, profile, {t["task_id"] for t in tasks}),
                       gen3.fidelity_value(directory, profile))
    out = safe_path(output)
    require(not out.exists(), "Use a new directory")
    out.mkdir(parents=True, mode=0o700)
    d_tasks, d_derivations, d_categories, d_record, d_result, d_fidelity, d_all = sides["learn"]
    t_tasks, _, t_categories, t_record, t_result, t_fidelity, t_all = sides["held_out"]
    write_json(out / "pool-D.json", {"tasks": d_tasks})
    write_json(out / "pool-T.json", {"tasks": t_tasks})
    write_json(out / "derivations.json", seal({"derivations": d_derivations}))
    keys = ("items", "profile", "profile_sha256", "distance", "limits", "passed")
    fidelity = {side: {k: f[k] for k in keys} for side, f in (("learn", d_fidelity), ("held_out", t_fidelity))}
    generation_fidelity = {side: {k: f[k] for k in keys} for side, f in (("learn", d_all), ("held_out", t_all))}
    summary = seal({"runner": VERSION, "runner_sha256": tool_sha256(), "generator": gen3.VERSION,
                    "generator_sha256": gen3.tool_sha256(), "template_stage": root.name,
                    "manifest_hash": value["record_hash"], "split_hash": cut["record_hash"],
                    "learn_tasks": cut["learn_tasks"], "held_out_tasks": cut["held_out_tasks"],
                    "generation_hash": {"learn": d_record["record_hash"], "held_out": t_record["record_hash"]},
                    "generation_result_hash": {"learn": d_result["record_hash"], "held_out": t_result["record_hash"]},
                    "fidelity": fidelity, "generation_fidelity": generation_fidelity,
                    "diagnostic_candidates": sorted(t["task_id"] for t in d_tasks),
                    "multi_part_learn_items_left_out": dropped,
                    "transfer_items": sorted(t["task_id"] for t in t_tasks),
                    "categories": {**d_categories, **t_categories},
                    "pool_D_hash": digest({"tasks": d_tasks}), "pool_T_hash": digest({"tasks": t_tasks})})
    write_json(out / "pools.json", summary)
    return summary


SOLVER_KEYS = ("model", "reasoning_effort", "thinking", "max_tokens", "temperature", "benchmark")


def solver(directory):
    """The solver settings of a probe directory that the difficulty comparison holds fixed."""
    config = json.loads((safe_path(directory) / "config.json").read_text(encoding="utf-8"))
    return {k: config.get(k) for k in SOLVER_KEYS}


def reference_rate(spec, template_value, train_tasks):
    """The parent's pass rate over known runs on the template's training tasks, from a completed glm-5.3 low probe of
    exactly the parent text that measured exactly these tasks and nothing else -- its registered item ids are checked
    before any of its item sources is read, so that a probe that also measured validation items is refused unread --
    with the same public fields and reference answer (what the OfficeQA scorer reads), every one with its full number
    of runs."""
    from scripts import weak_solver_probe as probe

    directory, _, skill = spec.rpartition(":")
    require(bool(directory) and bool(skill), "A reference is <probe dir>:<skill>")
    d = safe_path(directory)
    config = json.loads((d / "config.json").read_text(encoding="utf-8"))
    summary = json.loads((d / "summary.json").read_text(encoding="utf-8"))
    require(summary.get("status") == "completed" and summary.get("config_hash") == probe.digest(config)
            and config["model"] == "glm-5.3" and config["reasoning_effort"] == "low" and config["benchmark"] == "officeqa"
            and config["skills"].get(skill, {}).get("hash") == probe.digest(template_value["parent_skill"]),
            "Not a completed glm-5.3 low probe of the template's parent")
    ids = sorted(t["task_id"] for t in train_tasks)
    require(config.get("item_ids_hash") == probe.digest(ids) and config.get("n_items") == len(ids),
            "The reference probe did not measure exactly the template's training tasks")
    rows = [row for item_spec in config["items"] for row in probe.load_items(item_spec)]
    require(probe.digest(sorted(probe.digest(r) for r in rows)) == config["items_hash"], "The probe's item sources changed")
    require(sorted(r["id"] for r in rows) == ids, "The reference probe's item sources hold other items")
    found = {r["id"]: (r["public"], r["private"].get("answer")) for r in rows}
    require(all(found[t["task_id"]] == (t["public"], t["private"].get("answer")) for t in train_tasks),
            "The reference probe measured other questions or answers under the training task ids")
    runs = {}
    for path in (d / "records" / skill).glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        require(record.get("skill") == skill, "A reference record of another Skill")
        runs.setdefault(record["item"], {})[record["run"]] = record["status"]
    require(all(sorted(runs.get(i, {})) == list(range(config["runs"])) for i in ids),
            "The reference probe's runs on the training tasks are incomplete")
    known = [s for i in ids for s in runs[i].values() if s in ("pass", "fail")]
    require(known, "No known reference run")
    return {"probe_config_hash": probe.digest(config), "skill": skill, "tasks": len(ids), "runs": config["runs"],
            "known_runs": len(known), "pass_rate": round(sum(s == "pass" for s in known) / len(known), 6)}


def _rate(counts):
    known = sum(k for _, k in counts.values())
    return round(sum(p for p, _ in counts.values()) / known, 6) if known else None


def spec_from_inputs(template_dir, pools_dir, calibration_dirs, reference, blocks, series=None):
    """Runner v1's spec, with this design's go/no-go (recorded in source.go_rule; the calibration record keeps runner
    v1's field names, with no transfer minimum)."""
    from scripts import generate_officeqa_feature_tasks as gen3
    from skillopt.feedback_study import generalization_feedback as gf

    root, value, panel, record = v1._template(template_dir)
    pdir = safe_path(pools_dir)
    summary = read_json(pdir / "pools.json", sealed=True)
    require(summary["manifest_hash"] == value["record_hash"] and summary.get("runner") == VERSION,
            "The pools belong to another template or runner")
    require(all(summary["fidelity"][side]["limits"] == gen3.FIDELITY_LIMITS for side in ("learn", "held_out")),
            "The pools' fidelity was computed with other limits")
    pool_d, pool_t = read_json(pdir / "pool-D.json"), read_json(pdir / "pool-T.json")
    require(digest(pool_d) == summary["pool_D_hash"] and digest(pool_t) == summary["pool_T_hash"], "A pool changed")
    derivations = read_json(pdir / "derivations.json", sealed=True)["derivations"]
    cal_d = v1._calibration(calibration_dirs[0], pdir / "pool-D.json", "development", value["parent_skill"])
    cal_t = v1._calibration(calibration_dirs[1], pdir / "pool-T.json", "skill_confirmation", value["parent_skill"])
    train_tasks = sorted((t for t in panel["tasks"] if t["family_id"] in set(value["train_families"])),
                         key=lambda t: t["task_id"])
    ref = reference_rate(reference, value, train_tasks)
    settings = [solver(calibration_dirs[0]), solver(calibration_dirs[1]), solver(reference.rpartition(":")[0])]
    require(settings[0] == settings[1] == settings[2],
            "The calibration and reference probes differ in solver settings: their pass rates are not comparable")
    informative_d, nonceiling = v1.informative(cal_d["counts"]), v1.informative(cal_t["counts"])
    rate_d, rate_t = _rate(cal_d["counts"]), _rate(cal_t["counts"])
    distribution = lambda counts: {"%d/%d" % (p, k): sum(1 for v in counts.values() if v == [p, k])
                                   for p, k in sorted({tuple(v) for v in counts.values()})}
    easier = lambda rate: None if rate is None else round(rate - ref["pass_rate"], 6)
    checks = {"fidelity_learn": summary["fidelity"]["learn"]["passed"],
              "fidelity_held_out": summary["fidelity"]["held_out"]["passed"],
              "informative_diagnostic": len(informative_d) >= MIN_INFORMATIVE_D,
              "diagnostic_not_easier": rate_d is not None and easier(rate_d) <= MAX_EASIER,
              "transfer_not_easier": rate_t is not None and easier(rate_t) <= MAX_EASIER}
    go = all(checks.values())
    calibration = {"rule": "a diagnostic item is informative when the parent failed it at least once in >= 2 known of "
                           "%d runs; the transfer pool keeps every item" % v1.CALIBRATION_RUNS,
                   "min_informative_diagnostic": MIN_INFORMATIVE_D, "min_nonceiling_transfer": None,
                   "diagnostic": {"candidates": len(cal_d["counts"]), "informative": len(informative_d),
                                  "pass_rate": rate_d, "minus_reference": easier(rate_d),
                                  "distribution": distribution(cal_d["counts"]),
                                  "probe_config_hash": cal_d["probe_config_hash"], "inventory_hash": cal_d["inventory_hash"]},
                   "transfer": {"items": len(cal_t["counts"]), "nonceiling": len(nonceiling), "pass_rate": rate_t,
                                "minus_reference": easier(rate_t), "distribution": distribution(cal_t["counts"]),
                                "probe_config_hash": cal_t["probe_config_hash"], "inventory_hash": cal_t["inventory_hash"]},
                   "reference": ref, "fidelity": summary["fidelity"], "checks": checks}
    require(set(informative_d) <= set(summary["diagnostic_candidates"]), "Informative items come from the diagnostic pool")
    keep_d = [t for t in pool_d["tasks"] if t["task_id"] in set(informative_d)]
    learn, held = set(summary["learn_tasks"]), set(summary["held_out_tasks"])
    real_learn = [t for t in panel["tasks"] if t["family_id"] in set(value["train_families"]) and t["task_id"] in learn]
    require(len(real_learn) == len(learn) and not {t["task_id"] for t in real_learn} & held, "The learn tasks are not the split's")
    study_panel = {**{k: panel[k] for k in ("version", "benchmark", "dataset_revision", "provenance")},
                   "tasks": real_learn + keep_d + pool_t["tasks"]}
    template = {"panel_hash": digest(study_panel), "train_families": sorted({t["family_id"] for t in real_learn + keep_d}),
                "selection_families": sorted({t["family_id"] for t in pool_t["tasks"]}),
                **{k: value[k] for k in v1.TEMPLATE_KEYS}}
    kept = {i: derivations[i] for i in informative_d}
    transfer = sorted(t["task_id"] for t in pool_t["tasks"])
    pools_spec = {"learn_tasks": sorted(learn), "held_out_tasks": sorted(held), "diagnostic_items": informative_d,
                  "transfer_items": transfer, "categories": {i: summary["categories"][i] for i in informative_d + transfer}}
    source = {"template_stage": root.name, "stage_hash": record["record_hash"], "manifest_hash": value["record_hash"],
              "pools_hash": summary["record_hash"], "generation_hash": summary["generation_hash"],
              "split_hash": summary["split_hash"], "go": go, "go_rule": go_rule(), "runner": VERSION,
              "runner_sha256": tool_sha256(), "generator": summary["generator"],
              "generator_sha256": summary["generator_sha256"], **({"series": series} if series else {})}
    spec = gf.build_spec(template, pools_spec, digest(kept), calibration, blocks, source)
    return spec, study_panel, kept, record, go


def prepare(template_dir, pools_dir, calibration_dirs, reference, output, blocks, series=None):
    from skillopt.feedback_study import generalization_feedback as gf

    out = safe_path(output)
    require(not out.exists(), "Use a new directory")
    spec, panel, _, _, go = spec_from_inputs(template_dir, pools_dir, calibration_dirs, reference, blocks, series)
    if not go:
        write_json(out / "no-go.json", seal({"calibration": spec["calibration"], "go_rule": go_rule(),
                                            "reason": "registered go/no-go not met: the study is not run"}))
        return spec, False
    write_json(out / "study" / "protocol.json", spec)
    write_json(out / "study" / "study.json", gf._manifest(spec, panel))
    write_json(out / "inputs.json", seal({"pools": str(safe_path(pools_dir)),
                                         "calibration": [str(safe_path(c)) for c in calibration_dirs],
                                         "reference": reference}))
    return spec, True


def run(template_dir, output):
    from scripts import continue_fivebench_baselines as sequence
    from skillopt.feedback_study.generalization_feedback import _manifest, run_study

    out = safe_path(output)
    saved = read_json(out / "study" / "protocol.json", sealed=True)
    inputs = read_json(out / "inputs.json", sealed=True)
    spec, panel, derivations, record, go = spec_from_inputs(template_dir, inputs["pools"], inputs["calibration"],
                                                            inputs["reference"], saved["blocks"],
                                                            saved["source"].get("series"))
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pools")
    for name in ("--template", "--split", "--generation-d", "--generation-t", "--profile", "--output"):
        p.add_argument(name, required=True)
    q = sub.add_parser("prepare")
    for name in ("--template", "--pools", "--reference", "--output"):
        q.add_argument(name, required=True)
    q.add_argument("--calibration", nargs=2, required=True)
    q.add_argument("--blocks", type=int, required=True)
    q.add_argument("--series")
    r = sub.add_parser("run")
    r.add_argument("--template", required=True)
    r.add_argument("--output", required=True)
    t = sub.add_parser("report")
    t.add_argument("--output", nargs="+", required=True)
    t.add_argument("--allow-closure-differences", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "pools":
        summary = pools(args.template, args.split, args.generation_d, args.generation_t, args.profile, args.output)
        print(json.dumps({"diagnostic_candidates": len(summary["diagnostic_candidates"]),
                          "transfer_items": len(summary["transfer_items"]),
                          "multi_part_learn_items_left_out": summary["multi_part_learn_items_left_out"],
                          "fidelity": {s: {"passed": f["passed"], **f["distance"]} for s, f in summary["fidelity"].items()}},
                         indent=1))
    elif args.command == "prepare":
        spec, go = prepare(args.template, args.pools, args.calibration, args.reference, args.output, args.blocks,
                           args.series)
        print(json.dumps({"go": go, "checks": spec["calibration"]["checks"], "protocol_hash": spec["record_hash"]},
                         indent=1))
        return 0 if go else 2
    elif args.command == "run":
        result = run(args.template, args.output)
        print(json.dumps({k: result[k] for k in ("status", "reason", "completed_blocks", "blocks") if k in result}))
        return 0 if result["status"] == "completed" else 1
    else:
        print(v1.report(args.output, args.allow_closure_differences))
    return 0


if __name__ == "__main__":
    sys.exit(main())
