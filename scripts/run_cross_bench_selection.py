"""SkillOpt with its training tasks from one benchmark and its validation gate on ANOTHER benchmark
(docs/handoff/cross-bench-selection-design-20261013.md) -- an experiment on what transfers.

The frozen learning-v9 SkillOpt loop (skillopt/continual_learning/skillopt.py ``run_stage``) is re-run step by
step with two prepared, unbegun SkillOpt v9 stages of the stage tool as its inputs:

* the TRAIN stage (benchmark A) supplies the manifest and the training rows: rollouts under the current Skill and
  the native proposal (``propose_native``: analysts see task, answer, pass/fail and -- SkillOpt's labelled feedback
  -- the reference answer or sanitized evidence of FAILED training rows);
* the SELECTION stage (benchmark B) supplies the manifest and the validation rows on which the frozen two-pass
  sign-test gate (``confirm_selection``) screens and confirms every candidate.

So a candidate learned from A's training tasks is kept only if it improves B's validation tasks. A's validation
rows and B's training rows are used by neither learning nor selection; after the last step they serve as held-out
evaluation of the final Skill, of the empty Skill and of any named reference Skill on both benchmarks. Every call
goes through each stage's own frozen manifest, ledger and adapter; nothing in ``continual_learning`` changes. The
two prepared stage directories stay as they are (never begun); this run writes only into its own directory. Unlike
the frozen stage, a run that stops keeps no accepted prefix as a deployed Skill: it is a pending record.

Usage:
  python scripts/run_cross_bench_selection.py prepare --train-stage <prepared v9 skillopt stage of A> \\
      --selection-stage <prepared v9 skillopt stage of B> [--reference name=g:<completed stage>] --output <new dir>
  python scripts/run_cross_bench_selection.py run --output <prepared dir>
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_fivebench_g_stage as tool  # noqa: E402
from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json  # noqa: E402
from skillopt.validator_pilot.api import digest  # noqa: E402

VERSION = "cross-bench-selection-v1"
EDIT_BUDGET = 4  # as in the frozen loop


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _stage(directory):
    """A prepared, never begun SkillOpt v9 stage: (path, stage record, manifest, panel, split train / selection)."""
    out, record, _, _, value, panel = tool._load(directory)
    require(record["method"] == "skillopt" and record["learning_version"] == "continual-learning-v9"
            and record["parent"] == "none" and value["parent_skill"] == ""
            and record.get("selection_source", "canonical_validation_partition") == "canonical_validation_partition",
            "A prepared learning-v9 SkillOpt stage with the empty parent and the canonical validation set is expected")
    require(not (out / "learning").exists() and not (out / "learned.json").exists(), "The stage was already begun")
    train, selection = [], []
    for task in panel["tasks"]:
        role = "train" if task["family_id"] in value["train_families"] else "selection"
        (train if role == "train" else selection).append({"role": role, "task": task})
    return out, record, value, panel, train, selection


def prepare(train_stage, selection_stage, output, references=()):
    from scripts.run_active_evidence_panel_eval import NAME, verified_stage
    from skillopt.continual_learning.contracts import check_skill, skill_budget

    out = safe_path(output)
    require(not out.exists(), "Use a new directory")
    a_dir, a, a_value, _, a_train, a_selection = _stage(train_stage)
    b_dir, b, b_value, _, b_train, b_selection = _stage(selection_stage)
    require(a["benchmark"] != b["benchmark"] and a["study"] == b["study"] and a["protocol_hash"] == b["protocol_hash"]
            and a["split_hash"] == b["split_hash"] and a["recovery_policy"] == b["recovery_policy"]
            and a["budget"] == b["budget"] and a["learning_model_service"] == b["learning_model_service"]
            and a["native_lock"] == b["native_lock"] and a["repo"] == b["repo"],
            "Two stages of the same study, split, policy and service on DIFFERENT benchmarks are expected")
    _, protocol = tool._study(a["study"])
    named = []
    for spec in references:
        name, separator, where = spec.partition("=")
        require(separator == "=" and NAME.fullmatch(name) is not None and name not in {"empty", "final"}
                and name not in {n for n, _, _ in named} and where.startswith("g:"),
                "A reference is name=g:<completed G stage directory> with a unique name")
        stage, learned = verified_stage(protocol, safe_path(where[2:]), a["split_hash"])
        check_skill(learned["skill"], skill_budget(a_value))
        named.append((name, learned["skill"], {
            "stage": safe_path(where[2:]).name, "stage_hash": stage["record_hash"], "learned_hash": learned["record_hash"],
            "benchmark": stage["benchmark"], "method": stage["method"], "learning_version": stage["learning_version"],
            "action": learned["action"], "skill_sha256": learned["skill_sha256"], "skill_bytes": len(learned["skill"].encode()),
            # which of this run's held-out sets that stage itself trained or selected on (so that the reader knows)
            "trained_on_train_benchmark_rows": bool(set(stage.get("train_families", [])) & set(a_value["train_families"])),
            "selection_tasks": stage.get("selection_tasks")}))
    out.mkdir(parents=True, mode=0o700)
    texts = seal({"references": [{"name": n, "skill": s} for n, s, _ in named]})
    write_json(out / "references.json", texts)
    record = seal({"version": VERSION, "study": a["study"], "protocol_hash": a["protocol_hash"],
                   "split_hash": a["split_hash"], "repo": a["repo"], "native_lock": a["native_lock"],
                   "learning_model_service": a["learning_model_service"], "client_options": a["client_options"],
                   "train": {"stage": str(a_dir), "stage_hash": a["record_hash"], "benchmark": a["benchmark"],
                             "seed": a["seed"], "train_tasks": len(a_train), "heldout_validation_tasks": len(a_selection)},
                   "selection": {"stage": str(b_dir), "stage_hash": b["record_hash"], "benchmark": b["benchmark"],
                                 "seed": b["seed"], "selection_tasks": len(b_selection), "heldout_train_tasks": len(b_train)},
                   "max_iterations": a_value["budget"]["max_iterations"], "edit_budget": EDIT_BUDGET,
                   "gate": a_value["recovery_policy"]["selection_gate"],
                   "references": [{"name": n, **source} for n, _, source in named],
                   "references_hash": texts["record_hash"],
                   "design": "train rollouts and labelled native proposals on the train benchmark; the frozen two-pass "
                             "sign-test gate on the selection benchmark's validation rows; the train benchmark's "
                             "validation rows and the selection benchmark's training rows are held-out evaluation only",
                   "tool_sha256": _sha(Path(__file__)), "stage_tool_sha256": _sha(Path(tool.__file__)),
                   "deployment_authorized": False})
    write_json(out / "cross.json", record)
    return record


def _counts(rows):
    return {"pass": sum(r["score"] == 1 for r in rows), "fail": sum(r["score"] is not None and r["score"] != 1 for r in rows),
            "unknown": sum(r["score"] is None for r in rows)}


def learn(out, record, a, b, references, *, apis, fixture_evaluate=None):
    """The frozen v9 loop with the train rows of ``a`` and the selection rows of ``b``. ``a`` is (manifest, panel,
    train items, held-out validation items), ``b`` is (manifest, panel, held-out train items, selection items);
    ``apis`` the two clients. Returns the result fields."""
    from skillopt.continual_learning.gepa import Adapter
    from skillopt.continual_learning.ledger import Ledger
    from skillopt.continual_learning.skillopt import _known_mean, _label_leak, _paired_counts, confirm_selection, propose_native

    (a_value, a_panel, a_train, a_heldout), (b_value, b_panel, b_heldout, b_selection) = a, b
    sides = {}
    evaluators = fixture_evaluate if type(fixture_evaluate) is tuple else (fixture_evaluate, fixture_evaluate)
    for name, value, panel, api, evaluator in (("train", a_value, a_panel, apis[0], evaluators[0]),
                                               ("selection", b_value, b_panel, apis[1], evaluators[1])):
        root = out / name
        write_json(root / "panel.json", panel)  # the frozen trace binding re-reads the authorized panel from here
        write_json(root / "model_service.json", seal(api.service))
        ledger = Ledger(root, value, api)
        sides[name] = (root, ledger, Adapter(value, root, ledger, fixture_evaluate=evaluator))
    (a_root, a_ledger, a_adapter), (_, _, b_adapter) = sides["train"], sides["selection"]
    policy, tries = a_value["recovery_policy"], a_value["budget"]["max_iterations"]
    current = ""
    selected = b_adapter.evaluate_rows(b_selection, {"skill": current})
    _known_mean(selected, policy, "insufficient_known_selection")
    first_parent = selected
    steps, accepted = [], []
    for step in range(tries):
        rows = a_adapter.evaluate_rows(a_train, {"skill": current}, rollout=step)
        labels = list(a_adapter.train_labels)  # every label any analyst call has seen so far
        _known_mean(rows, policy, "insufficient_known_train")
        known = [r for r in rows if r["score"] is not None]
        traces = [{**r["trajectory"], "evidence_hash": r["output"]["evidence_hash"]} for r in known
                  if r["trajectory"] is not None]
        require(len(traces) == len(known), "Native reflection needs executed train rows only")
        proposal = propose_native(current, traces, a_root / "native" / str(step), a_ledger, step=step,
                                  seed=a_value["seed"] + step, minibatch_size=a_value["budget"]["minibatch_size"],
                                  edit_budget=EDIT_BUDGET)
        base = {"step": step, "parent_skill_hash": digest(current), "proposal_hash": proposal["record_hash"],
                "native_fallbacks": proposal["native_fallbacks"], "train_rollout": _counts(rows),
                "train_tasks": len(a_train), "selection_tasks": len(b_selection), "deployment_authorized": False}
        if proposal["status"] == "candidate_ready" and _label_leak(proposal["candidate_skill"], current, labels, policy):
            verdict = {"gate_action": "reject_label_leakage", "candidate_skill_hash": digest(proposal["candidate_skill"])}
        elif proposal["status"] == "rejected_inadmissible_over_budget":
            verdict = {"gate_action": "reject_inadmissible_over_budget",
                       "candidate_skill_hash": proposal["rejected_candidate_hash"]}
        elif proposal["status"] == "no_update":
            verdict = {"gate_action": "no_update_proposed", "candidate_skill_hash": digest(proposal["candidate_skill"])}
        else:
            require(proposal["status"] == "candidate_ready", "Unexpected proposal status")
            candidate = proposal["candidate_skill"]
            scores = b_adapter.evaluate_rows(b_selection, {"skill": candidate})
            verdict = {"candidate_skill_hash": digest(candidate), "candidate_skill_bytes": len(candidate.encode()),
                       **confirm_selection(b_adapter, b_selection, current, candidate, selected, scores, policy,
                                           tries=tries, rollout=step + 1)}
            write_json(out / "candidates" / f"{step}.json", seal({"step": step, "skill": candidate}))
            if verdict["accepted"]:
                current, selected = candidate, scores
                _known_mean(selected, policy, "insufficient_known_selection")
                accepted.append(step)
        steps.append(seal({**base, **verdict}))
        write_json(out / "steps" / f"{step}.json", steps[-1])
    # held-out evaluation on both benchmarks: rows neither learning nor selection used in this run
    arms = [("empty", ""), ("final", current)] + [(r["name"], r["skill"]) for r in references]
    heldout = {}
    solved = {}
    for name, skill in arms:
        if skill not in solved:  # an unchanged final Skill is the empty Skill: one solve, reported under both names
            solved[skill] = (a_adapter.evaluate_rows(a_heldout, {"skill": skill}, rollout=900),
                             b_adapter.evaluate_rows(b_heldout, {"skill": skill}, rollout=900))
        heldout[name] = {"train_benchmark_validation_rows": _counts(solved[skill][0]),
                         "selection_benchmark_training_rows": _counts(solved[skill][1])}
    paired = {}
    for name, skill in arms[1:]:
        if skill == "":
            continue
        paired[name + "-empty"] = {
            "train_benchmark_validation_rows": _paired_counts(solved[""][0], solved[skill][0], a_heldout),
            "selection_benchmark_training_rows": _paired_counts(solved[""][1], solved[skill][1], b_heldout)}
    costs = {"train": a_ledger.snapshot(), "selection": sides["selection"][1].snapshot()}
    blocked = {"train": bool(a_ledger.usage_blocks_completion(costs["train"])),
               "selection": bool(sides["selection"][1].usage_blocks_completion(costs["selection"]))}
    return {"steps": [s["record_hash"] for s in steps], "gate_actions": [s["gate_action"] for s in steps],
            "accepted_steps": accepted, "final_skill": current, "final_skill_sha256": hashlib.sha256(current.encode()).hexdigest(),
            "final_skill_bytes": len(current.encode()),
            "selection_rows_parent_first_pass": _counts(first_parent), "selection_rows_final_first_pass": _counts(selected),
            "heldout": heldout, "heldout_paired_vs_empty": paired,
            "costs": costs, "usage_blocks_completion": blocked}


def run(output, *, fixture_apis=None, fixture_evaluate=None):
    from skillopt.continual_learning.ledger import BudgetExhausted, LearningPending
    from skillopt.continual_learning.recovery import client_options
    from skillopt.validator_pilot.api import CachedAPI

    out = safe_path(output)
    record = read_json(out / "cross.json", sealed=True)
    require(record["version"] == VERSION and record["tool_sha256"] == _sha(Path(__file__)), "Tool changed")
    a_dir, a, a_value, a_panel, a_train, a_selection = _stage(record["train"]["stage"])
    b_dir, b, b_value, b_panel, b_train, b_selection = _stage(record["selection"]["stage"])
    require(a["record_hash"] == record["train"]["stage_hash"] and b["record_hash"] == record["selection"]["stage_hash"],
            "The prepared stages changed")
    references = read_json(out / "references.json", sealed=True)
    require(references["record_hash"] == record["references_hash"], "Reference Skills changed")
    # as the frozen stage does before it runs: both manifests must still be what the current sources produce
    from skillopt.continual_learning.contracts import validate_manifest

    validate_manifest(a_value, a_panel)
    validate_manifest(b_value, b_panel)
    fixture = a_value["model"]["provider"] == "fixture"
    require(fixture or (fixture_apis is None and fixture_evaluate is None), "Natural run cannot inject fixtures")
    require(not fixture or (fixture_apis is not None and fixture_evaluate is not None), "Invalid fixture callbacks")
    with safe_path(record["native_lock"]).open("a") as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        with output_lock(out / "train"), output_lock(out / "selection"):
            if (out / "result.json").exists():
                return read_json(out / "result.json", sealed=True)
            base = {"version": VERSION, "cross_hash": record["record_hash"]}
            if (out / "started.json").exists():
                result = seal({**base, "status": "pending", "reason": "interrupted_run_no_automatic_resume"})
                write_json(out / "result.json", result)
                return result
            fields, reason, apis = {}, None, []
            try:
                if not fixture:
                    from skillopt.continual_eval import backends
                    from skillopt.continual_learning.feedback import benchmark_for

                    sequence = tool._sequence()
                    for value, name in ((a_value, "train"), (b_value, "selection")):
                        require(backends.readiness(benchmark_for(value), value["runtime"])["status"] == "ready",
                                "Benchmark native runtime is not ready")
                        sequence.check_client_service(record["repo"], value["model"], out / ("client-check-" + name),
                                                      record["learning_model_service"],
                                                      client_options=record["client_options"])
                write_json(out / "started.json", seal({"cross_hash": record["record_hash"]}))
                if fixture:
                    apis = list(fixture_apis)
                else:
                    for value, name in ((a_value, "train"), (b_value, "selection")):
                        model = value["model"]
                        apis.append(CachedAPI(Path(record["repo"]), out / name / "api", provider=model["provider"],
                                              model=model["name"], workers=1, reasoning_effort=model["reasoning_effort"],
                                              **model.get("transport", {"initial_health_policy": "completed_response_v1"}),
                                              **({"proxy": model["proxy"]} if "proxy" in model else {}),
                                              **client_options(value)))
                try:
                    fields = learn(out, record, (a_value, a_panel, a_train, a_selection),
                                   (b_value, b_panel, b_train, b_selection),
                                   references["references"], apis=apis, fixture_evaluate=fixture_evaluate)
                finally:
                    for api in apis:
                        api.close()
                if not fixture:
                    for name in ("train", "selection"):
                        sequence.verify_service(out / name, record["learning_model_service"])
            except (LearningPending, BudgetExhausted) as exc:
                reason = "%s:%s" % (type(exc).__name__, str(exc)[:200])
            except Exception as exc:  # the type only
                reason = "error:" + type(exc).__name__
            if reason is None and any(fields["usage_blocks_completion"].values()):
                reason = "usage_or_receipt_accounting_incomplete"  # as in a stage: no completion over a usage gap
            result = seal({**base, "status": "completed" if reason is None else "pending", "reason": reason, **fields,
                           "steps_written": sorted(p.name for p in (out / "steps").glob("*.json")) if (out / "steps").exists() else []})
            write_json(out / "result.json", result)
            return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--train-stage", required=True)
    p.add_argument("--selection-stage", required=True)
    p.add_argument("--reference", action="append", default=[])
    p.add_argument("--output", required=True)
    sub.add_parser("run").add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        record = prepare(args.train_stage, args.selection_stage, args.output, tuple(args.reference))
        value = {"version": record["version"], "train": record["train"]["benchmark"],
                 "selection": record["selection"]["benchmark"], "record_hash": record["record_hash"]}
    else:
        result = run(args.output)
        value = {k: result.get(k) for k in ("version", "status", "reason", "gate_actions", "accepted_steps",
                                            "final_skill_bytes", "heldout", "record_hash")}
    print(json.dumps(value))
    return 0 if args.command == "prepare" or value["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
