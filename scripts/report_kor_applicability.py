"""Zero-call label-free KOR applicability study for a frozen five-domain study.

The executable verifier (skillopt.applicability.kor) judges every recorded KOR
response of the No-Skill reference and of each stage's forced Skill from the
public rule and question only. Gold answers and official scores are read here
solely to validate that instrument: (1) gold qualification, keeping golds that
violate their own public constraints (label noise) apart from golds the
verifier cannot judge; (2) agreement with the official scores; (3) label-free
paired Skill-vs-No-Skill deltas against the official deltas on the same
positions. Every observation is bound plan -> sealed checkpoint holding the
declared Skill text -> score -> prediction -> frozen task. A post-hoc
measurement study on previously exposed development data: no new observations,
no independent final estimate, no deployment authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter, defaultdict

from scripts.report_scope_routed_deployment import ACTIONS, SEQUENCES, observed
from skillopt.applicability import kor
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import BENCHMARKS, checkpoint_path, read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

VERSION = "kor-applicability-study-v5"
BENCHMARK = "korbench"
GOLD_SCOPE = {"pass": "gold_qualified", "unknown": "gold_unverified", "fail": "gold_inconsistent"}
POPULATIONS = {"gold_qualified": {"gold_qualified"}, "not_gold_inconsistent": {"gold_qualified", "gold_unverified"}}


def _gold_response(handler, answer):
    # The official 24-game scorer reads only the first line of a multi-line gold.
    if handler == "puzzle:twenty_four":
        match = re.search(r"\[\[(.*?)\]\]", answer, re.S)
        return "[[" + match.group(1).strip().split("\n")[0] + "]]" if match else answer
    return answer


def _comparable(plan):
    # A Skill cell may differ from the No-Skill reference only in its declared methods.
    return {k: v for k, v in plan["config"].items() if k != "methods"}


def _panel(reference):
    """KOR tasks bound one by one to the frozen No-Skill plan, its positions and its comparable configuration."""
    plan = read_json(safe_path(reference["root"]) / "plan.json", sealed=True)
    require(plan["record_hash"] == reference["plan_hash"], "No-Skill plan is not the frozen reference plan")
    hashes = {t["task_id"]: t["task_hash"] for t in plan["tasks"] if t["benchmark"] == BENCHMARK}
    tasks = {t["task_id"]: t for t in read_json(plan["config"]["panels"][BENCHMARK])["tasks"]}
    require(set(tasks) == set(hashes) and all(digest(tasks[k]) == v for k, v in hashes.items()),
            "KOR panel does not match the frozen plan")
    return tasks, hashes, {(task_id, r) for task_id in hashes for r in range(plan["repeats"])}, _comparable(plan)


def _responses(result, hashes, positions, skill, config):
    """Recorded responses of one cell, bound plan -> checkpoint (declared Skill) -> score -> prediction -> task."""
    root = safe_path(result["root"])
    plan = read_json(root / "plan.json", sealed=True)
    require(plan["record_hash"] == result["plan_hash"]
            and {t["task_id"]: t["task_hash"] for t in plan["tasks"] if t["benchmark"] == BENCHMARK} == hashes,
            "Evaluation plan does not bind to the frozen KOR tasks")
    require(_comparable(plan) == config, "Evaluation model, budget or runtime differs from the No-Skill reference")
    require({(t, r) for t in hashes for r in range(plan["repeats"])} == positions == set(observed(result["rows"])),
            "Incomplete or foreign evaluation cell")
    scores = {}
    for path in (root / "host_only/scores").glob("*.json"):
        score = read_json(path, sealed=True)
        scores[score["record_hash"]] = score
    predictions = {}
    for path in (root / "predictions").glob("*/prediction.json"):
        prediction = read_json(path, sealed=True)
        predictions[prediction["record_hash"]] = prediction
    checkpoints, out = {}, {}
    for row in result["rows"]:
        score = scores.get(row["record_hash"])
        require(score is not None and score["plan_hash"] == plan["record_hash"]
                and (score["task_id"], score["repeat"], score["status"]) == (row["task_id"], row["repeat"], row["status"]),
                "Row does not bind to its score")
        slot = (score["method"], score["history"], score["stage"])
        if slot not in checkpoints:
            checkpoint = read_json(checkpoint_path(root, *slot), sealed=True)
            require(checkpoint["plan_hash"] == plan["record_hash"]
                    and (checkpoint["method"], checkpoint["history"], checkpoint["stage"]) == slot
                    and hashlib.sha256(checkpoint["skill_text"].encode()).hexdigest() == checkpoint["skill_hash"]
                    and checkpoint["skill_text"] == skill, "Evaluation checkpoint does not hold the declared Skill")
            checkpoints[slot] = checkpoint
        require(score["checkpoint_hash"] == checkpoints[slot]["record_hash"], "Score does not bind to its checkpoint")
        prediction = predictions.get(score["prediction_hash"])
        request = prediction["request"] if prediction else {}
        require(prediction is not None and request.get("benchmark") == BENCHMARK
                and request.get("plan_hash") == plan["record_hash"]
                and request.get("task_hash") == hashes[row["task_id"]] and request.get("repeat") == row["repeat"]
                and request.get("checkpoint_hash") == score["checkpoint_hash"], "Score does not bind to its prediction")
        # An interrupted or unavailable attempt carries no answer to judge.
        out[(row["task_id"], row["repeat"])] = (row["status"], prediction["prediction"].get("status"),
                                                 prediction["prediction"].get("output"))
    require(len(checkpoints) == 1, "An evaluation cell must score exactly one policy checkpoint")
    return out


def _stages(root, protocol, method):
    """Forced KOR cells of each completed stage, with the stage chain re-verified."""
    previous, parent_hash, cells = "", None, []
    seen = {digest(""): observed(protocol["references"][BENCHMARK]["rows"])}
    for number, benchmark in enumerate(BENCHMARKS, 1):
        path = root / method / f"s{number}-{benchmark}" / "stage.json"
        if not path.is_file():
            break
        stage = read_json(path, sealed=True)
        require(stage["protocol_hash"] == protocol["record_hash"] and stage["method"] == method
                and stage["stage"] == number and stage["benchmark"] == benchmark
                and stage["parent_skill"] == previous and stage["parent_stage_hash"] == parent_hash,
                "Stage chain binding mismatch")
        require(stage["action"] in ACTIONS and (stage["action"] == "selected_update") == (stage["skill"] != previous),
                "Only an accepted update may change the Skill, and it must change it")
        result = stage["cells"][BENCHMARK]["result"]
        require(result["benchmark"] == BENCHMARK
                and result["model_service"] == protocol["references"][BENCHMARK]["model_service"],
                "Evaluation cell belongs to another domain or model service")
        current = observed(result["rows"])
        require(seen.setdefault(digest(stage["skill"]), current) == current, "A recurring Skill changed its observation")
        cells.append((number, stage, result))
        previous, parent_hash = stage["skill"], stage["record_hash"]
    return cells


def _pair(skill, base):
    if skill not in {"pass", "fail"} or base not in {"pass", "fail"}:
        return "unknown"
    return "tie" if skill == base else "win" if skill == "pass" else "loss"


def _verdicts(tasks, responses):
    return {key: kor.verify(tasks[key[0]]["public"]["rule"], tasks[key[0]]["public"]["question"], output)
            if available == "available" and type(output) is str
            else {"status": "unknown", "reason": "prediction_unavailable", "handler": None}
            for key, (_, available, output) in responses.items()}


def build(study, method="skillopt"):
    root = safe_path(study)
    protocol = read_json(root / "protocol.json", sealed=True)
    require(protocol["version"] in SEQUENCES and protocol["order"] == list(BENCHMARKS)
            and method in protocol["methods"], "Unsupported study or method")
    reference = protocol["references"][BENCHMARK]
    tasks, hashes, positions, config = _panel(reference)
    handlers = {}
    for task_id, task in tasks.items():
        handler = kor.RULES.get(kor.rule_hash(task["public"]["rule"]))
        if handler is not None:
            require((task["private"]["category"], task["private"]["rule_id"]) == kor.RULE_IDS[handler],
                    "Rule registry does not match the panel's rule identity")
        handlers[task_id] = handler
    qualification, gold, noisy = defaultdict(Counter), {}, {}
    for task_id, task in sorted(tasks.items()):
        if handlers[task_id] is None:
            continue
        verdict = kor.verify(task["public"]["rule"], task["public"]["question"],
                             _gold_response(handlers[task_id], task["private"]["answer"]))
        qualification[handlers[task_id]][verdict["status"]] += 1
        gold[task_id] = GOLD_SCOPE[verdict["status"]]
        if verdict["status"] == "fail":  # the gold itself violates a public constraint
            noisy[task_id] = verdict["reason"]
    base = _responses(reference, hashes, positions, "", config)
    base_verdicts = _verdicts(tasks, base)
    conditions = [("no_skill", None, base, base_verdicts)]
    for number, stage, result in _stages(root, protocol, method):
        responses = _responses(result, hashes, positions, stage["skill"], config)
        conditions.append((f"s{number}", stage, responses, _verdicts(tasks, responses)))

    agreement = {}
    for name, _, responses, verdicts in conditions:
        table = defaultdict(Counter)
        for key, (official, _, _) in responses.items():
            category, handler = tasks[key[0]]["private"]["category"], handlers[key[0]]
            if handler is None:
                table[category]["unregistered"] += 1
                continue
            for label in (category, handler):
                table[f"{label}|{gold[key[0]]}"][f"official_{official}|verifier_{verdicts[key]['status']}"] += 1
        agreement[name] = {k: dict(sorted(v.items())) for k, v in sorted(table.items())}
    deltas = {}
    for name, stage, responses, verdicts in conditions[1:]:
        populations = {}
        for population, scopes in POPULATIONS.items():
            table = defaultdict(lambda: {"official_all": Counter(), "verifier": Counter(),
                                         "official_same_positions": Counter()})
            for key, (official, _, _) in responses.items():
                if handlers[key[0]] is None or gold[key[0]] not in scopes:
                    continue
                label_free = _pair(verdicts[key]["status"], base_verdicts[key]["status"])
                for label in (tasks[key[0]]["private"]["category"], "registered"):
                    table[label]["official_all"][_pair(official, base[key][0])] += 1
                    table[label]["verifier"][label_free] += 1
                    if label_free != "unknown":
                        table[label]["official_same_positions"][_pair(official, base[key][0])] += 1
            populations[population] = {k: {m: dict(c) for m, c in v.items()} for k, v in sorted(table.items())}
        deltas[name] = {"skill_hash": digest(stage["skill"]), "action": stage["action"], **populations}
    repeats = len(positions) // len(hashes)
    scope_tasks = Counter(gold.values())
    return seal({"version": VERSION, "verifier": kor.VERSION, "protocol_hash": protocol["record_hash"],
                 "method": method, "registered_rules": len(kor.RULES),
                 "positions": {"total": len(positions), "registered": len(gold) * repeats,
                               **{scope: scope_tasks[scope] * repeats for scope in GOLD_SCOPE.values()}},
                 "gold_qualification": {k: dict(v) for k, v in sorted(qualification.items())},
                 "gold_inconsistent_tasks": dict(sorted(noisy.items())),
                 "agreement": agreement, "paired_deltas": deltas,
                 "model_api_calls": 0, "new_observations": 0, "post_hoc_diagnostic": True,
                 "independent_final": False, "deployment_authorized": False,
                 "data_scope": "previously_exposed_development_with_learning_overlap_not_final"})


def _rate(table, scope):
    counts = Counter()
    for key, value in table.items():
        label, _, group = key.partition("|")
        if group == scope and label in {"operation", "puzzle", "cipher"}:
            counts.update(value)
    agree = counts["official_pass|verifier_pass"] + counts["official_fail|verifier_fail"]
    definite = agree + counts["official_pass|verifier_fail"] + counts["official_fail|verifier_pass"]
    return agree, definite, sum(counts.values())


def markdown(report):
    p = report["positions"]
    lines = [f"# KOR无标签适用性验证（{report['method']}）", "",
             f"验证器`{report['verifier']}`，{report['registered_rules']}条已登记规则；0模型调用、0新观测；"
             "黄金与官方分数只用于检验仪器，事后诊断，非独立final。", "",
             f"登记位置 {p['registered']}/{p['total']}：黄金资格通过 {p['gold_qualified']}、"
             f"无法判定 {p['gold_unverified']}、违反公开约束 {p['gold_inconsistent']}。", "",
             "| 条件 | 资格通过：一致/双方有判定 | 双方有判定/全部 |", "|---|---:|---:|"]
    for name, table in report["agreement"].items():
        agree, definite, total = _rate(table, "gold_qualified")
        lines.append(f"| {name} | {agree}/{definite} | {definite}/{total} |")
    lines += ["", "| 阶段 | 人群 | 范围 | 官方全部：改善/退化/持平/未知 | 无标签：改善/退化/持平/未知"
              " | 同位置官方：改善/退化/持平/未知 |", "|---|---|---|---|---|---|"]
    for name, delta in report["paired_deltas"].items():
        for population in POPULATIONS:
            for scope, cells in delta[population].items():
                row = [cells[k] for k in ("official_all", "verifier", "official_same_positions")]
                lines.append(f"| {name} | {population} | {scope} | " + " | ".join(
                    "/".join(str(c.get(k, 0)) for k in ("win", "loss", "tie", "unknown")) for c in row) + " |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", required=True)
    parser.add_argument("--method", default="skillopt", choices=("skillopt", "gepa"))
    parser.add_argument("--output", required=True, help="New directory outside the frozen study")
    args = parser.parse_args()
    study, output = safe_path(args.study), safe_path(args.output)
    inside = any(parent.exists() and os.path.samefile(parent, study) for parent in (output, *output.parents))
    require(not output.exists() and not inside, "Use a new export directory outside the frozen study")
    report = build(study, args.method)
    output.mkdir(parents=True, mode=0o700)
    write_json(output / "report.json", report)
    (output / "report.md").write_text(markdown(report))
    print(json.dumps({"stages": len(report["paired_deltas"]), "record_hash": report["record_hash"]}))


if __name__ == "__main__":
    main()
