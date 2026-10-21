"""Zero-call report of a finished (or pending) learning-v11 ``active_evidence`` stage: the evidence chain of each
step in one compact JSON (problem -> hypotheses -> research -> checks -> edits -> challenge -> decision), costs and
the stage outcome. Reads sealed records only; never calls a model or re-scores anything.

Usage: python scripts/report_active_evidence_stage.py --stage <stage dir> [--json]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from skillopt.continual_eval.core import read_json, safe_path

LABEL_HEADER = "HIDDEN TEST FAILURES"
ATTRIBUTION_WORDS = ("hidden test", "failure message", "label feedback", "tests complained", "test complained")


def _released_tokens(learning, step):
    """Test names, exception classes and quoted literals (>= 4 chars) of the failure-message study's released
    reports, or None when the step released nothing (counts only leave this host)."""
    folder = learning / "diagnosis" / str(step) / "reports"
    texts = [read_json(p, sealed=True)["feedback"] for p in sorted(folder.glob("*.json"))] if folder.exists() else []
    texts = [t for t in texts if t.startswith(LABEL_HEADER)]
    if not texts:
        return None
    names, classes, literals = set(), set(), set()
    for text in texts:
        for line in text.splitlines()[1:]:
            match = re.match(r"- (\S+): (.*)", line)
            if match:
                names.add(match.group(1))
                head = match.group(2).split(":", 1)[0].strip()
                if re.match(r"^[A-Za-z_][\w.]*(?:Error|Exception|Warning)$", head):
                    classes.add(head)
        for single, double in re.findall(r"'([^']{4,})'|\"([^\"]{4,})\"", text):
            literals.add(single or double)
    return {"rows": len(texts), "test_names": names, "exception_classes": classes, "literals": literals}


def _reasoning_texts(value, key_names=("reasoning", "rationale")):
    """Every string under a reasoning-like key of a nested JSON value (never edit contents)."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in key_names and isinstance(item, str):
                found.append(item)
            else:
                found.extend(_reasoning_texts(item, key_names))
    elif isinstance(value, list):
        for item in value:
            found.extend(_reasoning_texts(item, key_names))
    return found


def _attribution(tokens, text):
    lowered = text.lower()
    return {"cites_test_names": sum(1 for n in tokens["test_names"] if n in text),
            "cites_exception_classes": sorted(c for c in tokens["exception_classes"] if c in text),
            "cites_released_literals": sum(1 for l in tokens["literals"] if l in text),
            "mentions_failure_messages": any(word in lowered for word in ATTRIBUTION_WORDS)}


def _cited(attribution):
    return bool(attribution["cites_test_names"] or attribution["cites_exception_classes"]
                or attribution["cites_released_literals"] or attribution["mentions_failure_messages"])


def _study_audits(learning, step):
    """Descriptive audits of the failure-message study (never a gate): label echo (released literals/test names found
    verbatim in the treatment Skill) and explicit attribution -- do the REASONING texts of the selected edits, and
    separately of the per-minibatch raw proposals, cite released content (test names, exception classes, quoted
    literals, or the words hidden test / failure message)? Absent attribution is reported as mechanism unknown,
    never as 'messages did not shape the edits'."""
    tokens = _released_tokens(learning, step)
    if tokens is None:
        return None
    native = learning / "native" / str(step)
    result = read_json(native / "result.json", sealed=True) if (native / "result.json").exists() else None
    skill = (result or {}).get("candidate_skill") or ""
    selected_reasoning = " ".join(_reasoning_texts((result or {}).get("selected")))
    patch_files = sorted((native / "patches").rglob("*.json")) if (native / "patches").exists() else []
    minibatch_reasoning = " ".join(text for p in patch_files
                                   for text in _reasoning_texts(json.loads(p.read_text(encoding="utf-8"))))
    selected = _attribution(tokens, selected_reasoning)
    minibatch = _attribution(tokens, minibatch_reasoning)
    mechanism = ("cited_in_selected_edits" if _cited(selected) else "cited_in_minibatch_proposals_only"
                 if _cited(minibatch) else "unknown")
    return {"released_rows": tokens["rows"], "released_test_names": len(tokens["test_names"]),
            "released_exception_classes": sorted(tokens["exception_classes"]), "released_literals": len(tokens["literals"]),
            "label_echo": {"literals_in_treatment_skill": sum(1 for l in tokens["literals"] if l in skill),
                           "test_names_in_treatment_skill": sum(1 for n in tokens["test_names"] if n in skill)},
            "attribution": {"selected_edit_reasoning": selected, "minibatch_proposal_reasoning": minibatch,
                            "reasoning_texts": {"selected": len(selected_reasoning) > 0,
                                                "minibatch_files": len(patch_files)},
                            "mechanism": mechanism}}


def holdout_overlap(stage, prior_stages):
    """Development-reuse disclosure: how many of this stage's drawn holdout tasks were fresh-challenge tasks of each
    earlier stage (solved there under other Skills; never shown to any analyst). Hashes only."""
    learning = safe_path(stage) / "learning"
    draws = sorted((learning / "challenge").glob("*/draw.json")) if (learning / "challenge").exists() else []
    drawn = {e["task_hash"] for p in draws for e in read_json(p, sealed=True)["fresh"]}
    overlap = {}
    union = set()
    for prior in prior_stages:
        folder = safe_path(prior) / "learning" / "challenge"
        used = {e["task_hash"] for p in (sorted(folder.glob("*/draw.json")) if folder.exists() else [])
                for e in read_json(p, sealed=True)["fresh"]}
        overlap[Path(prior).name] = len(drawn & used)
        union |= drawn & used
    return {"holdout_positions": len(drawn), "overlap_by_prior_stage": overlap,
            "holdout_tasks_used_by_any_prior_stage": len(union),
            "note": "reused development evaluation: these tasks were solved in earlier stages (under other Skills and, "
                    "for sealed reference Skills reused here, under the same texts); no analyst, diagnoser or Research "
                    "call ever saw them, and no reference was chosen by those outcomes"}


def _decision_details(learning, step):
    """Rule version, sealed limits and the count-only decision inputs of one step (no text)."""
    path = learning / "challenge" / str(step) / "decision.json"
    if not path.exists():
        return {}
    record = read_json(path, sealed=True)
    inputs = record.get("inputs", {})
    details = {"rule_version": record.get("rule_version"), "limits": record.get("limits"),
               "flags": inputs.get("flags"), "fresh": inputs.get("fresh"), "replay": inputs.get("replay"),
               "fresh_adverse": inputs.get("fresh_adverse")}
    shadow = record.get("in_sample_shadow")
    if shadow is not None:
        # the optional in-sample reading (never a decision input): actions, flags and counts only
        details["in_sample_shadow"] = {k: shadow.get(k) for k in (
            "version", "action", "reason", "flags", "evidence", "min_paired_known", "by_step_status",
            "reused_positions", "size_matched_fresh", "decision_input")}
    return details


def report(stage):
    out = safe_path(stage)
    record = read_json(out / "stage.json", sealed=True)
    learning = out / "learning"
    result = read_json(learning / "result.json", sealed=True) if (learning / "result.json").exists() else None
    learned = read_json(out / "learned.json", sealed=True) if (out / "learned.json").exists() else None
    steps = []
    for chain_path in sorted((learning / "chain").glob("*.json")) if (learning / "chain").exists() else []:
        chain = read_json(chain_path, sealed=True)
        step = chain["step"]
        summary = None
        if (learning / "diagnosis" / str(step) / "summary.json").exists():
            summary = read_json(learning / "diagnosis" / str(step) / "summary.json", sealed=True)
        checks = summary["checks"] if summary else []
        audit_path = learning / "diagnosis" / str(step) / "release_audit.json"
        release = None
        if audit_path.exists():
            audit = read_json(audit_path, sealed=True)
            release = {k: audit.get(k) for k in ("release_profile", "denominators", "message_classes", "delivered")}
        steps.append({
            "matched": chain.get("matched"),  # the matched-branch study record (both branches, holdout, outcome class)
            # the composition-aware screen: arms, controls, paired counts and the selection (training selection only)
            "update_mode": chain.get("update_mode"), "screen": chain.get("screen"),
            "native_candidate_hash": chain.get("native_candidate_hash"),
            "information_release": chain.get("information_release"),
            "release": release,
            "study_audits": _study_audits(learning, step),
            "step": step,
            "rollout": chain["rollout"],
            "problem": {"host_fail": len(chain["problem"]["host_fail"]), "host_pass": len(chain["problem"]["host_pass"])},
            "diagnosis": None if summary is None else {
                "status": summary["status"], "cases": len(summary.get("cases", [])),
                "hypotheses": summary.get("hypotheses", []),
                "grades": summary.get("grades", {}),
                "executed_checks": sum(c["executed"] for c in checks),
                "observations": [{k: o[k] for k in ("hypothesis_id", "verdict", "checks")} for o in summary.get("observations", [])],
                "research": [{k: r.get(k) for k in ("evidence_hash", "status", "documented", "new_information")}
                             for r in summary.get("research", [])],
                "fact_needs": summary.get("fact_needs", []),
                "rows_with_evidence": len(summary.get("report_hashes", {})),
                "cases_skipped_for_reserve": summary.get("cases_skipped_for_reserve", []),
                "delivery": summary.get("delivery"),  # per-case accounting of what reached the analysts' package
                "summary_text": summary.get("summary_text")},
            "edits": chain["edits"],
            "challenge": chain["challenge"],
            "decision": {**chain["decision"], **_decision_details(learning, step)},
            "intervened": chain["intervened"],
        })
    costs = None if result is None else result["costs"]
    test = None
    if (out / "summary.json").exists():  # the one-time test cell paired with the recorded No-Skill cell (numbers only)
        cell = read_json(out / "summary.json", sealed=True)
        test = {k: cell.get(k) for k in ("test_positions", "test_counts", "no_skill_counts", "wins_vs_no_skill",
                                         "losses_vs_no_skill", "net_vs_no_skill", "jointly_known", "families_improving",
                                         "families_regressing", "skill_sha256", "record_hash")}
        test["costs"] = {k: (cell.get("test_costs") or {}).get(k) for k in ("logical_calls", "reported_tokens", "usage_complete")}
    references = [{k: r.get(k) for k in ("name", "benchmark", "method", "learning_version", "action", "selection_tasks",
                                         "skill_sha256", "stage_hash", "skill_bytes")}
                  for r in record.get("reference_skills", [])]
    return {"stage": str(out), "method": record["method"], "arms": record.get("arms"), "benchmark": record["benchmark"],
            "reference_skills": references,  # evaluation-only holdout references of the matched study (provenance)
            "update_mode": record.get("update_mode"),
            "limits": record.get("limits"), "limits_requested": record.get("limits_requested"),
            "eligible_fresh_tasks": record.get("eligible_fresh_tasks"),
            "parent": record.get("parent"), "parent_skill_sha256": record.get("parent_skill_sha256"),
            "train_tasks": record.get("train_tasks"), "challenge_tasks": record.get("challenge_tasks"),
            "status": None if result is None else result["status"], "reason": None if result is None else result["reason"],
            "action": None if learned is None else learned["action"],
            "decisions": None if result is None else result.get("decisions"),
            "skill_bytes": None if learned is None else learned["skill_bytes"],
            "costs": None if costs is None else {k: costs.get(k) for k in ("logical_calls", "solver_calls", "verifier_calls",
                                                                          "reflection_calls", "reported_tokens_known_subtotal",
                                                                          "missing_usage_calls", "unclosed_calls")},
            "tests": sorted(p.name for p in out.glob("summary*.json")),
            "test": test,
            "steps": steps,
            "note": "learning-process data (dynamic tasks and replay); never a final evaluation"}


def public(value):
    """The publishable projection: counts, grades, hashes and decisions only -- no hypothesis statements, summary
    text, Skill text or task text (those stay on the Linux host with the sealed records)."""
    out = {k: v for k, v in value.items() if k != "stage"}
    out["stage_basename"] = Path(value["stage"]).name
    parent = out.get("parent")
    if type(parent) is str and parent[:2] in ("g:", "m:", "f:"):
        # a parent taken from another stage or from a fixed text file: publish the basename, not the host directory
        kind, _, rest = parent.partition(":")
        path, colon, branch = rest.rpartition(":") if kind == "m" else (rest, "", "")
        out["parent"] = kind + ":" + Path(path).name + colon + branch
    for step in out["steps"]:
        diagnosis = step.get("diagnosis")
        if diagnosis:
            diagnosis.pop("summary_text", None)
            diagnosis["hypotheses"] = [{"id": h["id"], "kind": h["kind"], "needs_fact": h["needs_fact"] is not None}
                                       for h in diagnosis["hypotheses"]]
            diagnosis["fact_needs"] = [{k: v for k, v in f.items() if k != "question"} for f in diagnosis.get("fact_needs", [])]
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, nargs="+")
    parser.add_argument("--json", action="store_true", help="full JSON (default: compact, without the summary text)")
    parser.add_argument("--export", help="write the publishable projection of all stages to this JSON file")
    parser.add_argument("--prior-stage", nargs="*", default=[],
                        help="earlier stages whose fresh-challenge draws are compared with each stage's holdout (reuse disclosure)")
    args = parser.parse_args()
    values = [report(stage) for stage in args.stage]
    if args.prior_stage:
        for value in values:
            value["holdout_reuse"] = holdout_overlap(value["stage"], args.prior_stage)
    if args.export:
        from skillopt.coevolution_v5.core import seal
        from skillopt.continual_eval.core import write_json

        write_json(args.export, seal({"version": "active-evidence-stage-export-v1", "stages": [public(v) for v in values],
                                      "note": "learning-process data; counts and hashes only; never a final evaluation"}))
    for value in values:
        if not args.json:
            for step in value["steps"]:
                if step["diagnosis"]:
                    step["diagnosis"] = {k: v for k, v in step["diagnosis"].items() if k != "summary_text"}
        print(json.dumps(value, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
