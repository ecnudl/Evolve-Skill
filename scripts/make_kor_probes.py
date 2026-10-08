"""Write a sealed set of fresh KOR probes for a frozen five-domain study (zero model calls).

The public rule texts and answer-format instructions come from the KOR panel bound
to the study's frozen No-Skill plan; every probe is new, and its reference answer
passed the label-free verifier while a mutated reference failed. Probes are scored
only by that verifier, never by the official scorer, and never enter evaluation.
"""
from __future__ import annotations

import argparse
import json
import os

from scripts.report_kor_applicability import _panel
from skillopt.applicability import kor, kor_probes
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require, safe_path, write_json


def build(study, *, per_rule, seed):
    require(type(per_rule) is int and 1 <= per_rule <= 100 and type(seed) is int, "Invalid probe request")
    protocol = read_json(safe_path(study) / "protocol.json", sealed=True)
    reference = protocol["references"]["korbench"]
    tasks, _, _, _ = _panel(reference)
    for task in tasks.values():
        handler = kor.RULES.get(kor.rule_hash(task["public"]["rule"]))
        if handler is not None:
            require((task["private"]["category"], task["private"]["rule_id"]) == kor.RULE_IDS[handler],
                    "Rule registry does not match the panel's rule identity")
    public = {k: {"task_id": t["task_id"], "public": t["public"]} for k, t in tasks.items()}  # no private fields
    probes = kor_probes.generate(public, per_rule=per_rule, seed=seed)
    return seal({"version": kor_probes.VERSION, "verifier": kor.VERSION, "protocol_hash": protocol["record_hash"],
                 "panel_plan_hash": reference["plan_hash"], "seed": seed, "per_rule": per_rule,
                 "handlers": sorted({p["handler"] for p in probes}), "probes": probes,
                 "qualification": "each reference passes and each mutated reference fails the verifier",
                 "scored_by": "label_free_verifier_only", "model_api_calls": 0})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True)
    parser.add_argument("--per-rule", type=int, default=8)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", required=True, help="New directory outside the frozen study")
    args = parser.parse_args()
    study, output = safe_path(args.study), safe_path(args.output)
    inside = any(parent.exists() and os.path.samefile(parent, study) for parent in (output, *output.parents))
    require(not output.exists() and not inside, "Use a new output directory outside the frozen study")
    value = build(study, per_rule=args.per_rule, seed=args.seed)
    output.mkdir(parents=True, mode=0o700)
    write_json(output / "probes.json", value)
    print(json.dumps({"probes": len(value["probes"]), "record_hash": value["record_hash"]}))


if __name__ == "__main__":
    main()
