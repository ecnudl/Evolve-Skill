"""Generalization feedback study (``fivebench-generalization-feedback-study-v1``; 2026-10-15, written before any
result; design docs/handoff/generalization-architecture-20261015.md, approved by the owner on 10/15).

Question: in the main method's own flow (train execution -> rubric feedback -> analyst -> candidate), does feedback
that knows the DERIVATION of self-generated diagnostic items -- the host's exact computation, and the error mode a
wrong answer reproduces -- produce one-step candidates that transfer better to pages the learner never saw, alone or
added to a benchmark-agnostic text rubric (the owner's proposed final form: a text and a code version of the rubric,
global granularity)?

Material (OfficeQA; the study's runner builds it, zero calls): the template stage's training tasks are split by bulletin
file into L (learn) and H (held out). D = category-targeted generated items written from L's pages (generator v2),
kept when the parent failed them at least once in three calibration runs; T = generated items written from H's pages
(the selection pool; H's own real questions are never solved here). Every block shares ONE fresh train rollout of the
parent over L's real tasks and D, and every distinct candidate and the parent are scored TWICE on T.

Arms (a 2 x 2 of a text layer and a code layer, plus a repeated scalar proposal as the in-block noise reference):

  scalar         pass/fail only
  scalar_repeat  identical inputs to scalar, a second analyst sample: the same-input noise of the block
  global_text    the benchmark-agnostic rubric judged by the model on every training row (v10 calibration/authorization)
  code_diag      on generated rows, the host's derivation check: the expected answer, its derivation and the error
                 mode a wrong answer reproduces (rounding, unit/percent scale, sign, operand order, a neighbouring cell)
  global_code    both layers (the owner's proposed final form)

The judge never sees a reference answer; the code layer's derivation is the generator's computation from public pages
of TRAINING tasks, never a dataset label (an information change from v10's label-free verification, recorded in the
protocol). Updater, parser, retries and the analyst prompts are the frozen native ones (``rubric_form.propose_arm``).

Reading (pre-registered in ANALYSIS): primary contrasts global_code - global_text and code_diag - scalar, exact block
sign-flip over blocks of the summed pass counts of the two scoring passes, six blocks of one sign needed; all other
contrasts, per-position counts and per-category counts are descriptive; scalar_repeat - scalar is reported per block
as the noise reference. A candidate scored higher on T is not an accepted Skill; held-out real items and other
datasets are evaluated after the study, outside it.
"""
from __future__ import annotations

import hashlib
import random
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json
from skillopt.continual_learning.gepa import Adapter
from skillopt.continual_learning.ledger import LearningPending, Ledger
from skillopt.continual_learning.recovery import POLICY_V10, client_options
from skillopt.continual_learning.skillopt import native_sources
from skillopt.continual_learning.verifier import MAX_REPORT_CHARS
from skillopt.continual_learning.verifier import VERSION as VERIFIER_VERSION
from skillopt.validator_pilot.api import CachedAPI, digest

from . import error_modes as em
from . import rubric_form as rf
from .common import bind_rows, local_rubric, run_cells, study_manifest, study_sources, validate_rubric_record
from .fixed_rubric import arm_metrics, sign_flip_two_sided

PROTOCOL = "fivebench-generalization-feedback-study-v1"
BENCHMARK = "officeqa"
ARMS = ("scalar", "scalar_repeat", "global_text", "code_diag", "global_code")
SLOTS = ("parent", *ARMS)
PASSES = 2
MODULES = ("__init__.py", "common.py", "fixed_rubric.py", "matched_feedback.py", "rubric_form.py", "error_modes.py",
           "generalization_feedback.py")
PLAN_SEED = 20261015
EDIT_BUDGET = rf.EDIT_BUDGET
BUDGET = dict(rf.BUDGET)
TEXT_ARM, CODE_ARM, BOTH_ARM = "global_text", "code_diag", "global_code"
CODE_NOTE = {
    "version": "generated-item-derivation-note-v1",
    "preamble": (
        "\n\nGENERATED TRAINING ITEMS. Some failed rows are GENERATED training items written from the same kind of "
        "pages. For those rows only, the verifier note shows the answer the host computed exactly from the quoted "
        "cells, its derivation, and which simple variant (another rounding, a truncation, a power of ten, the sign, "
        "swapped figures, a neighbouring cell of the quoted table) reproduces the wrong number -- the one exception to "
        "'no expected answer is shown'. A matching variant is a hint, not a proof of the solver's reasoning. Use it to "
        "name the procedural step that went wrong and write the reusable check that would have caught it; never copy "
        "the item's numbers, quotes, table labels or entities into the skill."),
}

CODE_POLICY = rf._policy(
    "A generated training item's answer was computed exactly by the host from quoted table cells; a wrong answer is "
    "compared with simple variants of that derivation.",
    "Generated training items only; real training items get no code check.",
    "Real training items, and generated rows whose derivation the host cannot re-evaluate.",
    "The item's derivation (figures with their page quotes, the expression, the rounding) and the solver's final answer.",
    "One check per generated row: does the final answer equal the derivation's answer; on failure, name the first "
    "variant that reproduces the solver's number (rounding, unit or percent scale, sign, operand order, a "
    "neighbouring cell of the same table).",
    "A named variant reproduces the number; it is not a proof of the solver's reasoning. An unexplained difference is "
    "reported as unexplained.")
BOTH_POLICY = rf._policy(
    "Two layers: a judge applies a benchmark-agnostic answer-form-and-scope rubric to every training row; the host "
    "checks generated rows against their exact derivation.",
    "Text layer: any question-answering row with a public answer form. Code layer: generated training rows only.",
    "The judge abstains when the question does not determine a check; the code layer skips rows without a derivation.",
    "Text layer: the response compared with the question's explicit demands. Code layer: the derivation and the answer.",
    "Text layer: at most two obligations (one value of the asked kind with the stated unit, scale and rounding; the "
    "asked item, not a neighbouring one). Code layer: the derivation check and the reproduced variant.",
    "The judge sees no reference answer and can tell form and scope only; the code layer's variant reproduces a "
    "number, it does not prove the solver's reasoning.")


def rubrics():
    records = rf.rubrics(BENCHMARK)
    return {TEXT_ARM: records["global_text"],
            CODE_ARM: rf._record(BENCHMARK, CODE_POLICY, "study_host_executed_derivation"),
            BOTH_ARM: rf._record(BENCHMARK, BOTH_POLICY, "study_text_and_host_derivation")}


ANALYSIS = {
    "unit": "block: one shared fresh train rollout of the parent over the learn tasks and the diagnostic items, one "
            "candidate per arm, every distinct candidate and the parent scored twice on the transfer pool",
    "confirmatory": {"test": "exact_block_sign_flip_two_sided_on_summed_pass_count_differences", "alpha": 0.05,
                     "note": "with fewer than six blocks no contrast can reach alpha; the study is then descriptive"},
    "primary": [["global_code", "global_text"], ["code_diag", "scalar"]],
    "contrasts": [["global_code", "global_text"], ["code_diag", "scalar"], ["global_text", "scalar"],
                  ["global_code", "scalar"], ["global_code", "code_diag"], ["scalar_repeat", "scalar"]],
    "noise_reference": ["scalar_repeat", "scalar"],
    "multiplicity": "each primary contrast is tested on its own at alpha 0.05 without correction; only a primary "
                    "contrast can be 'supported'; a supported difference may be negative (two-sided)",
    "descriptive": "per-position paired wins/losses pooled over blocks and both passes (positions of a block share a "
                   "candidate: not independent); per transfer-item category (writer-assigned labels the reviewer does "
                   "not verify: descriptive only); unknown sensitivity bounds",
    "information_change": "the code layer shows the analyst the expected answer and derivation of GENERATED training "
                          "items (computed by the host from public pages of training tasks); v10's verification shows "
                          "no answer. No validation or test item and no dataset label reaches any prompt",
    "claim_limits": "one parent Skill (the zero-shot instruction), one benchmark, generated transfer items from held-out "
                    "pages, candidates never gated nor evaluated on real held-out items within the study; a difference "
                    "between arms is a difference between the candidates their feedback produced on these blocks",
}


# ----------------------------------------------------------------------------- verifiers
class DiagnosisVerifier:
    """The code layer: the record tree, calibration rule and report shape of a v10 arm; zero calls. A generated row
    gets one check against its derivation (host-scored); a real row gets none."""

    def __init__(self, manifest_value, root, rollout, arm, policy_record, derivations):
        require(arm == CODE_ARM and type(rollout) is int and rollout >= 0, "Invalid derivation arm")
        self.manifest, self.rollout, self.rubric_arm = manifest_value, rollout, arm
        self.step = f"{rollout}-{arm}"
        self.root = safe_path(root) / "verifier" / self.step
        self.host_root = safe_path(root) / "host_only" / "verifier" / self.step
        self.rubric = local_rubric(validate_rubric_record(policy_record, BENCHMARK))
        self.policy = manifest_value["recovery_policy"]
        self.binding = {"manifest_hash": manifest_value["record_hash"], "step": self.step}
        self.derivations = derivations
        self.notes = {}

    def judge_row(self, item, row):
        task = item["task"]
        token = row["output"]["evidence_hash"]
        derivation = self.derivations.get(task["task_id"])
        probes, note = [], None
        if derivation is not None:
            failed = row["score"] == 0
            diagnosis = em.diagnose(derivation, task["public"]["context"], row["output"]["output"]) if failed else None
            probes = [{"kind": "host_check", "name": "derivation", "outcome": "fail" if failed else "pass",
                       "obligation": "the final answer equals the answer of the item's exact derivation",
                       "quote": task["public"]["question"][:160],
                       "detail": diagnosis["detail"] if failed else "matches the derivation",
                       "mode": diagnosis["mode"] if failed else None}]
            note = em.render(derivation, diagnosis, MAX_REPORT_CHARS) if failed else None
        record = seal({"verifier_version": VERIFIER_VERSION, **self.binding, "evidence_hash": token,
                       "policy_hash": self.rubric["policy_hash"], "host_status": "fail" if row["score"] == 0 else "pass",
                       "probes": probes, "note": note, "trace": [],
                       "information_origin": "host_derivation_of_a_generated_training_item" if derivation else "none_real_row"})
        path = self.root / "rows" / (token + ".json")
        if path.exists():
            require(read_json(path, sealed=True) == record, "Derivation check replay changed")
            return record
        write_json(path, record)
        return record

    def calibrate(self, records):
        """v10's calibration rule (detections on host-failed rows, false rejections on host-passed rows, enough
        controls, the cap); reports carry the rendered derivation note on host-failed generated rows when authorized."""
        row_hashes = sorted(r["record_hash"] for r in records)
        summary_path = self.root / "summary.json"
        if summary_path.exists():
            summary = read_json(summary_path, sealed=True)
            require(summary["row_record_hashes"] == row_hashes and summary["policy_hash"] == self.rubric["policy_hash"]
                    and {k: summary[k] for k in self.binding} == self.binding, "Derivation summary replay changed")
            reports = {}
            for r in records:
                report = read_json(self.root / "reports" / (r["evidence_hash"] + ".json"), sealed=True)
                require(report["row_record_hash"] == r["record_hash"] and report["calibration_hash"] == summary["calibration_hash"],
                        "Derivation report replay changed")
                reports[r["evidence_hash"]] = report
            return summary, reports
        host_fail = [r for r in records if r["host_status"] == "fail"]
        host_pass = [r for r in records if r["host_status"] == "pass"]
        detections = sum(any(p["outcome"] == "fail" for p in r["probes"]) for r in host_fail)
        false_rejections = sum(any(p["outcome"] == "fail" for p in r["probes"]) for r in host_pass)
        frr = false_rejections / len(host_pass) if len(host_pass) >= self.policy["verifier_min_pass_controls"] else None
        authorized = (detections >= self.policy["verifier_min_detections"] and frr is not None
                      and frr <= self.policy["verifier_max_false_rejection_rate"])
        calibration = seal({"verifier_version": VERIFIER_VERSION, **self.binding, "policy_hash": self.rubric["policy_hash"],
                            "host_fail_rows": len(host_fail), "host_pass_rows": len(host_pass), "detections": detections,
                            "false_rejections": false_rejections, "false_rejection_rate": frr, "authorized": authorized,
                            "information_origin": "host_development_audit_calibration"})
        write_json(self.host_root / "calibration.json", calibration)
        reports = {}
        for record in records:
            feedback = record["note"] if authorized and record["host_status"] == "fail" else None
            report = seal({"verifier_version": VERIFIER_VERSION, **self.binding, "evidence_hash": record["evidence_hash"],
                           "policy_hash": self.rubric["policy_hash"], "authorized": authorized,
                           "row_record_hash": record["record_hash"], "calibration_hash": calibration["record_hash"],
                           "probes": record["probes"], "feedback": feedback})
            write_json(self.root / "reports" / (record["evidence_hash"] + ".json"), report)
            reports[record["evidence_hash"]] = report
        modes = {}
        for r in host_fail:
            for p in r["probes"]:
                if p.get("mode"):
                    modes[p["mode"]] = modes.get(p["mode"], 0) + 1
        summary = seal({"verifier_version": VERIFIER_VERSION, **self.binding, "arm": self.rubric_arm,
                        "policy_status": self.rubric["status"], "policy_hash": self.rubric["policy_hash"],
                        "row_record_hashes": row_hashes, "rows": len(records),
                        "rows_with_probes": sum(bool(r["probes"]) for r in records), "error_modes": modes,
                        "coverage": {"rows": len(records), "decided": sum(bool(r["probes"]) for r in records)},
                        "delivery": {"calls": 0, "host_executed": True}, "authorized": authorized,
                        "detections": detections, "false_rejections": false_rejections,
                        "host_pass_rows": len(host_pass), "host_fail_rows": len(host_fail),
                        "false_rejection_rate": frr, "calibration_hash": calibration["record_hash"]})
        write_json(summary_path, summary)
        return summary, reports


CODE_SHARE = 1000  # characters of a combined note reserved for the code layer (its essentials come first)


def _bounded(text, limit):
    return text if len(text) <= limit else text[:limit] + " …[truncated]"


def layered(code_note, text_note):
    """The combined arm's note: the code layer FIRST (its diagnosis leads the note, so its essentials survive), bounded to
    CODE_SHARE when the text layer is present too; the text layer bounded to the remaining room; the whole within the
    frozen report bound."""
    marker = len(" …[truncated]")
    if code_note is None and text_note is None:
        return None
    if text_note is None:
        return _bounded(code_note, MAX_REPORT_CHARS)
    if code_note is None:
        return _bounded(text_note, MAX_REPORT_CHARS)
    code_part = _bounded(code_note, CODE_SHARE)
    room = MAX_REPORT_CHARS - len(code_part) - 1 - marker
    return code_part + "\n" + _bounded(text_note, max(room, 0))


def combine(manifest_value, root, rollout, policy_record, text, code):
    """The global_code arm's record tree: per row the text layer's report (when that layer is authorized) and the code
    layer's report (when authorized), concatenated and bounded; authorized when either layer is. Zero calls: both
    layers' sealed summaries and reports are its inputs and are bound by hash."""
    (text_summary, text_reports), (code_summary, code_reports) = text, code
    step = f"{rollout}-{BOTH_ARM}"
    folder = safe_path(root) / "verifier" / step
    rubric = local_rubric(validate_rubric_record(policy_record, BENCHMARK))
    binding = {"manifest_hash": manifest_value["record_hash"], "step": step}
    authorized = bool(text_summary["authorized"] or code_summary["authorized"])
    require(set(text_reports) == set(code_reports), "Both layers report on the same rows")
    calibration = seal({"verifier_version": VERIFIER_VERSION, **binding, "policy_hash": rubric["policy_hash"],
                        "text_summary_hash": text_summary["record_hash"], "code_summary_hash": code_summary["record_hash"],
                        "authorized": authorized, "information_origin": "union_of_the_two_layers_sealed_reports"})
    summary_path = folder / "summary.json"
    reports = {}
    for token in sorted(text_reports):
        code_note = code_reports[token]["feedback"] if code_reports[token]["authorized"] else None
        text_note = text_reports[token]["feedback"] if text_reports[token]["authorized"] else None
        feedback = layered(code_note, text_note)
        report = seal({"verifier_version": VERIFIER_VERSION, **binding, "evidence_hash": token,
                       "policy_hash": rubric["policy_hash"], "authorized": authorized,
                       "row_record_hash": digest([text_reports[token]["record_hash"], code_reports[token]["record_hash"]]),
                       "calibration_hash": calibration["record_hash"],
                       "layers": {"text": text_reports[token]["record_hash"], "code": code_reports[token]["record_hash"]},
                       "feedback": feedback})
        path = folder / "reports" / (token + ".json")
        if path.exists():
            require(read_json(path, sealed=True) == report, "Combined report replay changed")
        else:
            write_json(path, report)
        reports[token] = report
    summary = seal({"verifier_version": VERIFIER_VERSION, **binding, "arm": BOTH_ARM, "policy_status": rubric["status"],
                    "policy_hash": rubric["policy_hash"], "authorized": authorized,
                    "text_authorized": text_summary["authorized"], "code_authorized": code_summary["authorized"],
                    "calibration_hash": calibration["record_hash"], "rows": len(reports),
                    "rows_with_feedback": sum(r["feedback"] is not None for r in reports.values())})
    if summary_path.exists():
        require(read_json(summary_path, sealed=True) == summary, "Combined summary replay changed")
    else:
        write_json(summary_path, summary)
    return summary, reports, rubric, folder


_NUMBER_TOKEN = re.compile(r"(?<![\d.])-?\d[\d,]*(?:\.\d+)?(?![\d])")


LEAK_WINDOW = 24  # characters of any quoted excerpt that may not reappear verbatim in a candidate


def significant_digits(number_text):
    digits = number_text.replace(",", "").lstrip("-").replace(".", "").lstrip("0")
    return len(digits)


def derivation_leak(skill, derivations):
    """What of a generated item's derivation a candidate Skill carries verbatim: an answer with at least three
    significant digits as a number token, an expression of at least eight characters, or ANY run of LEAK_WINDOW
    characters of a figure quote (whitespace collapsed) -- the only page excerpts a note shows (a neighbour cell is
    described by position and value), however they were cut. Single printed numbers of the pages (figure values, a
    neighbour's value) are page content the solver reads when it solves the training item and are not refused. []
    when nothing.

    Boundary: what is PRIVATE to the host -- a generated item's answer and derivation -- and the page excerpts the code
    layer displays are refused here. The text layer is the frozen v10 judge: it sees the public task and the response
    only (never a derivation), so its notes carry public training-page or response text, exactly as in every v10 run;
    keeping task-specific public text out of a Skill is the frozen transfer preamble's job, as for every arm."""
    tokens = {t.replace(",", "").lstrip("-") for t in _NUMBER_TOKEN.findall(skill)}
    squashed = " ".join(skill.split())
    found = []
    for item, d in sorted(derivations.items()):
        answer = d["answer"].replace(",", "").lstrip("-")
        if significant_digits(answer) >= 3 and answer in tokens:
            found.append({"item": item, "what": "answer"})
        if any(len(e) >= 8 and e in skill for e in {d["expression"], em.canonical(d["expression"])}):
            found.append({"item": item, "what": "expression"})
        for f in d["figures"]:
            quote = " ".join(f["quote"].split())
            if any(quote[i:i + LEAK_WINDOW] in squashed for i in range(0, max(1, len(quote) - LEAK_WINDOW + 1))
                   if len(quote) >= LEAK_WINDOW):
                found.append({"item": item, "what": "quote"})
    return found[:20]


# ----------------------------------------------------------------------------- protocol
def build_spec(template, pools, derivations_hash, calibration, blocks, source):
    require(type(blocks) is int and 1 <= blocks <= 16, "One to sixteen blocks")
    records = rubrics()
    spec = seal({"protocol": PROTOCOL, "benchmark": BENCHMARK, "arms": list(ARMS), "passes": PASSES, "blocks": blocks,
                 "rubrics": records, "rubric_policy_hashes": {k: v["policy_hash"] for k, v in records.items()},
                 "template": template, "pools": pools, "derivations_hash": derivations_hash, "calibration": calibration,
                 "budget": dict(BUDGET), "plan_seed": PLAN_SEED, "edit_budget": EDIT_BUDGET, "analysis": ANALYSIS,
                 "code_note": dict(CODE_NOTE), "code_share": CODE_SHARE, "leak_window": LEAK_WINDOW, "source": source,
                 "deployment_authorized": False,
                 "information_origin": "fresh_train_rollouts; label_free_text_rubric_reports; host_derivations_of_"
                                       "generated_training_items_only"})
    validate_spec(spec)
    return spec


def validate_spec(spec):
    verify(spec)
    require(spec["protocol"] == PROTOCOL and spec["benchmark"] == BENCHMARK and spec["arms"] == list(ARMS)
            and spec["passes"] == PASSES and type(spec["blocks"]) is int and 1 <= spec["blocks"] <= 16
            and spec["budget"] == BUDGET and spec["plan_seed"] == PLAN_SEED and spec["edit_budget"] == EDIT_BUDGET
            and spec["analysis"] == ANALYSIS and spec["rubrics"] == rubrics() and spec["code_note"] == CODE_NOTE
            and spec["code_share"] == CODE_SHARE and spec["leak_window"] == LEAK_WINDOW, "Not this study's registered protocol")
    for arm, record in spec["rubrics"].items():
        validate_rubric_record(record, BENCHMARK)
        require(spec["rubric_policy_hashes"][arm] == record["policy_hash"], "Rubric hash registry differs")
    template = spec["template"]
    require(set(template) == {"panel_hash", "train_families", "selection_families", "model", "runtime", "parent_skill",
                              "seed", "recovery_policy"} and template["recovery_policy"] == POLICY_V10,
            "The template is not a v10 (v7 delivery) template")
    pools = spec["pools"]
    require(set(pools) == {"learn_tasks", "held_out_tasks", "diagnostic_items", "transfer_items", "categories"}
            and not set(pools["learn_tasks"]) & set(pools["held_out_tasks"])
            and not set(pools["diagnostic_items"]) & set(pools["transfer_items"]), "Pools overlap")
    return spec


def block_plan(spec, block):
    rng = random.Random(digest({"plan_seed": spec["plan_seed"], "protocol": PROTOCOL, "block": block,
                                "series": spec["source"].get("series")}))
    proposal_order, evaluation_order = list(ARMS), list(SLOTS)
    rng.shuffle(proposal_order)
    rng.shuffle(evaluation_order)
    width = len(SLOTS) * PASSES
    return {"block": block, "train_rollout": block, "minibatch_seed": rng.randrange(2**31),
            "judge_seed": rng.randrange(2**31), "proposal_order": proposal_order, "evaluation_order": evaluation_order,
            "validation_rollouts": {slot: [1 + width * block + PASSES * index + k for k in range(PASSES)]
                                    for index, slot in enumerate(SLOTS)}}


def _counts(rows):
    return {"positions": len(rows), "pass": sum(r["score"] == 1 for r in rows), "fail": sum(r["score"] == 0 for r in rows),
            "unknown": sum(r["score"] is None for r in rows),
            "statuses": ["pass" if r["score"] == 1 else "fail" if r["score"] == 0 else "unknown" for r in rows],
            "evidence_digest": digest([r["output"]["evidence_hash"] for r in rows])}


# ----------------------------------------------------------------------------- one block
def run_block(spec, value, root, ledger, adapter, train, selection, block, workers, derivations):
    plan = block_plan(spec, block)
    folder = root / "blocks" / str(block)
    write_json(folder / "plan.json", seal({"protocol_hash": spec["record_hash"], **plan}))
    parent, rollout = value["parent_skill"], plan["train_rollout"]
    rows = adapter.evaluate_rows(train[:1], {"skill": parent}, rollout=rollout)  # first reply alone (health barrier)
    rows += adapter.evaluate_rows(train[1:], {"skill": parent}, rollout=rollout)
    pairs, unknown = bind_rows(ledger, value, train, rows, parent, rollout)
    if not pairs:
        raise LearningPending("insufficient_known_train")
    by_token = {row["output"]["evidence_hash"]: (item, row) for item, row in pairs}
    tokens = sorted(by_token)
    traces = [{**row["trajectory"], "evidence_hash": row["output"]["evidence_hash"]} for _, row in pairs]
    cells = [[TEXT_ARM, token] for token in tokens]
    random.Random(plan["judge_seed"]).shuffle(cells)
    write_json(folder / "schedule.json", seal({"protocol_hash": spec["record_hash"], "block": block,
                                               "eligible_tokens": tokens, "cells": cells}))
    text_verifier = rf.TextRubricVerifier(value, ledger, root, rollout, TEXT_ARM, spec["rubrics"][TEXT_ARM])
    text_records = run_cells([tuple(cell) for cell in cells], {TEXT_ARM: text_verifier}, by_token, workers)[TEXT_ARM]
    ordered = [row["output"]["evidence_hash"] for _, row in pairs]
    text = text_verifier.calibrate([text_records[t] for t in ordered])
    code_verifier = DiagnosisVerifier(value, root, rollout, CODE_ARM, spec["rubrics"][CODE_ARM], derivations)
    code_records = {t: code_verifier.judge_row(*by_token[t]) for t in tokens}
    code = code_verifier.calibrate([code_records[t] for t in ordered])
    both_summary, both_reports, both_rubric, both_root = combine(value, root, rollout, spec["rubrics"][BOTH_ARM], text, code)
    layers = {TEXT_ARM: (text[0], text[1], text_verifier.rubric, text_verifier.root),
              CODE_ARM: (code[0], code[1], code_verifier.rubric, code_verifier.root),
              BOTH_ARM: (both_summary, both_reports, both_rubric, both_root)}
    generated = {t for t in tokens if by_token[t][0]["task"]["task_id"] in derivations}
    meta = [{"token": row["output"]["evidence_hash"], "family": item["task"]["family_id"],
             "host_status": "fail" if row["score"] == 0 else "pass"} for item, row in pairs]
    proposals, injected, failures = {}, {}, {}
    for arm in plan["proposal_order"]:
        arm_traces, kwargs = deepcopy(traces), {}
        if arm in layers and layers[arm][0]["authorized"]:
            summary, reports, rubric, verifier_root = layers[arm]
            for trace in arm_traces:
                report = reports.get(trace["evidence_hash"])
                if (trace["Feedback"]["status"] == "fail" and report is not None and report["authorized"]
                        and report["feedback"] is not None):
                    trace["Feedback"] = {**trace["Feedback"], "verifier": report["feedback"]}
            kwargs = {"verifier_root": verifier_root, "verifier_reports": reports, "policy_record": rubric}
            if arm in (CODE_ARM, BOTH_ARM) and code[0]["authorized"]:
                kwargs["analyst_binding"] = spec["code_note"]
        injected[arm] = {"all": sum("verifier" in t["Feedback"] for t in arm_traces),
                         "generated": sum("verifier" in t["Feedback"] and t["evidence_hash"] in generated for t in arm_traces)}
        try:
            proposals[arm] = rf.propose_arm(parent, arm_traces, root / "native" / str(block) / arm, ledger, arm=arm,
                                            label=f"{rollout}-{arm}", rollout=rollout, seed=plan["minibatch_seed"],
                                            minibatch_size=value["budget"]["minibatch_size"], edit_budget=spec["edit_budget"],
                                            study=PROTOCOL, **kwargs)
        except LearningPending as exc:
            tolerated = rf.tolerated_proposal_failure(exc)
            if tolerated is None:
                raise
            failures[arm] = tolerated
            proposals[arm] = None
    leaks = {}
    for arm in ARMS:
        if proposals.get(arm) is not None and proposals[arm]["status"] == "candidate_ready":
            found = derivation_leak(proposals[arm]["candidate_skill"], derivations)
            if found:
                leaks[arm] = found
    dispositions = {}
    for arm in ARMS:
        common = {"verifier_authorized": layers[arm][0]["authorized"] if arm in layers else None,
                  "traces_with_feedback": injected[arm]["all"], "generated_traces_with_feedback": injected[arm]["generated"]}
        proposal = proposals[arm]
        if proposal is None:
            dispositions[arm] = {"proposal_hash": None, "status": "proposal_failed", "failure": failures[arm],
                                 "candidate_hash": None, "candidate_bytes": None, "evaluated": "parent_fallback",
                                 "native_fallbacks": None, **common}
            continue
        if arm in leaks:  # the arm stays on the parent: a generated item's derivation may never reach a solver
            dispositions[arm] = {"proposal_hash": proposal["record_hash"], "status": "rejected_derivation_leak",
                                 "failure": None, "leak": leaks[arm], "candidate_hash": None, "candidate_bytes": None,
                                 "evaluated": "parent_fallback", "native_fallbacks": proposal["native_fallbacks"], **common}
            continue
        changed = proposal["status"] == "candidate_ready"
        dispositions[arm] = {"proposal_hash": proposal["record_hash"], "status": proposal["status"], "failure": None,
                             "candidate_hash": digest(proposal["candidate_skill"]) if changed else None,
                             "candidate_bytes": len(proposal["candidate_skill"].encode()) if changed else None,
                             "evaluated": "candidate" if changed else "parent_fallback",
                             "native_fallbacks": proposal["native_fallbacks"], **common}
    candidates = seal({"protocol_hash": spec["record_hash"], "block": block, "train_rollout": rollout,
                       "train": {"tasks": len(train), "eligible_rows": len(pairs), "unknown_rows": unknown,
                                 "generated_rows": len(generated),
                                 "host_fail_rows": sum(m["host_status"] == "fail" for m in meta),
                                 "host_fail_generated_rows": sum(by_token[t][1]["score"] == 0 for t in generated),
                                 "host_pass_rows": sum(m["host_status"] == "pass" for m in meta)},
                       "verifier": {
                           TEXT_ARM: {"summary_hash": text[0]["record_hash"], "authorized": text[0]["authorized"],
                                      "all_eligible_rows": arm_metrics(meta, text_records)},
                           CODE_ARM: {"summary_hash": code[0]["record_hash"], "authorized": code[0]["authorized"],
                                      "error_modes": code[0]["error_modes"], "detections": code[0]["detections"],
                                      "host_fail_rows": code[0]["host_fail_rows"]},
                           BOTH_ARM: {"summary_hash": both_summary["record_hash"], "authorized": both_summary["authorized"]}},
                       "dispositions": dispositions, "frozen_before_validation": True})
    write_json(folder / "candidates.json", candidates)
    evaluations, by_skill = {}, {}
    for slot in plan["evaluation_order"]:
        if slot == "parent":
            skill = parent
        elif dispositions[slot]["evaluated"] == "candidate":
            skill = proposals[slot]["candidate_skill"]
        else:
            continue
        if digest(skill) in by_skill:
            dispositions[slot]["shares_evaluation_of"] = by_skill[digest(skill)]
            continue
        passes = []
        for r in plan["validation_rollouts"][slot]:
            passes.append({"rollout": r, **_counts(adapter.evaluate_rows(selection, {"skill": skill}, rollout=r))})
        evaluations[slot] = {"skill_hash": digest(skill), "passes": passes,
                             **{k: sum(p[k] for p in passes) for k in ("positions", "pass", "fail", "unknown")}}
        by_skill[digest(skill)] = slot
    arms = {}
    for arm in ARMS:
        slot = ("parent" if dispositions[arm]["evaluated"] != "candidate"
                else dispositions[arm].get("shares_evaluation_of", arm))
        arms[arm] = {**evaluations[slot], "evaluated": dispositions[arm]["evaluated"], "evaluation_slot": slot}
    outcome = seal({"protocol_hash": spec["record_hash"], "block": block, "candidates_hash": candidates["record_hash"],
                    "selection_task_ids": [i["task"]["task_id"] for i in selection], "evaluations": evaluations,
                    "arms": arms, "shared_evaluations": {arm: dispositions[arm]["shares_evaluation_of"] for arm in ARMS
                                                         if "shares_evaluation_of" in dispositions[arm]}})
    write_json(folder / "outcome.json", outcome)
    return candidates, outcome


# ----------------------------------------------------------------------------- analysis
def analyze(spec, candidates, outcomes):
    categories = spec["pools"]["categories"]

    def contrast(treatment, control):
        primary = [treatment, control] in spec["analysis"]["primary"]
        differences = [o["arms"][treatment]["pass"] - o["arms"][control]["pass"] for o in outcomes]
        exact = sign_flip_two_sided(differences)
        wins = losses = 0
        for o in outcomes:
            for pa, pb in zip(o["arms"][treatment]["passes"], o["arms"][control]["passes"]):
                for a, b in zip(pa["statuses"], pb["statuses"]):
                    wins += a == "pass" and b == "fail"
                    losses += a == "fail" and b == "pass"
        low = [o["arms"][treatment]["pass"] - o["arms"][control]["pass"] - o["arms"][control]["unknown"] for o in outcomes]
        high = [o["arms"][treatment]["pass"] + o["arms"][treatment]["unknown"] - o["arms"][control]["pass"] for o in outcomes]
        total = sum(differences)
        return {"treatment": treatment, "control": control, "primary": primary, "differences": differences,
                "mean_difference": total / len(differences),
                "block_sign_flip": {"observed_sum": exact["observed_sum"], "informative_blocks": exact["informative_families"],
                                    "p_value": exact["p_value"]},
                "paired_positions": {"wins": wins, "losses": losses, "net": wins - losses},
                "unknown_sensitivity_mean_bounds": [sum(low) / len(low), sum(high) / len(high)],
                "direction": "treatment_higher" if total > 0 else "control_higher" if total < 0 else "equal",
                "supported": bool(primary and total != 0 and exact["p_value"] <= spec["analysis"]["confirmatory"]["alpha"])}

    contrasts = [contrast(t, c) for t, c in spec["analysis"]["contrasts"]]
    arms, by_category = {}, {}
    for arm in ARMS:
        totals = {k: sum(o["arms"][arm][k] for o in outcomes) for k in ("pass", "fail", "unknown", "positions")}
        arms[arm] = {**totals, "yield": totals["pass"] / totals["positions"],
                     "dispositions": {s: sum(c["dispositions"][arm]["status"] == s for c in candidates)
                                      for s in sorted({c["dispositions"][arm]["status"] for c in candidates})},
                     "blocks_with_feedback": sum(c["dispositions"][arm]["traces_with_feedback"] > 0 for c in candidates)}
    for slot in ("parent", *ARMS):
        counts = {}
        for o in outcomes:
            source = o["evaluations"]["parent"] if slot == "parent" else o["arms"][slot]
            for p in source["passes"]:
                for task_id, status in zip(o["selection_task_ids"], p["statuses"]):
                    cat = categories.get(task_id, "unknown_category")
                    entry = counts.setdefault(cat, {"pass": 0, "positions": 0})
                    entry["pass"] += status == "pass"
                    entry["positions"] += 1
        by_category[slot] = counts
    parent = {k: sum(o["evaluations"]["parent"][k] for o in outcomes) for k in ("pass", "fail", "unknown", "positions")}
    verifier = {"text_authorized_blocks": sum(c["verifier"][TEXT_ARM]["authorized"] for c in candidates),
                "code_authorized_blocks": sum(c["verifier"][CODE_ARM]["authorized"] for c in candidates),
                "code_error_modes": {}}
    for c in candidates:
        for mode, n in c["verifier"][CODE_ARM]["error_modes"].items():
            verifier["code_error_modes"][mode] = verifier["code_error_modes"].get(mode, 0) + n
    return {"contrasts": contrasts, "arms": arms, "parent": parent, "by_category": by_category, "verifier": verifier,
            "blocks": len(outcomes), "noise_reference": spec["analysis"]["noise_reference"],
            "claim_limits": spec["analysis"]["claim_limits"]}


# ----------------------------------------------------------------------------- run / verify
CODE_ENTRIES = ("skillopt/feedback_study/generalization_feedback.py", "scripts/run_generalization_feedback_study.py")


def code_closure():
    from .matched_feedback import code_closure as walk
    import skillopt.feedback_study.matched_feedback as mf

    saved = mf.CODE_ENTRIES
    try:
        mf.CODE_ENTRIES = CODE_ENTRIES
        return walk()
    finally:
        mf.CODE_ENTRIES = saved


def _manifest(spec, panel):
    template = {k: v for k, v in spec["template"].items() if k != "panel_hash"}
    return study_manifest({**template, "panel": panel}, spec["budget"],
                          {"protocol": PROTOCOL, "protocol_hash": spec["record_hash"],
                           "study_sources": study_sources(MODULES), "native_sources": native_sources(),
                           "code_closure": code_closure()})


def _artifacts(root, ledger):
    files = ("protocol.json", "study.json", "panel.json", "derivations.json", "started.json", "model_service.json")
    result = {**rf.learning_artifacts(ledger),
              **{name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files if (root / name).exists()}}
    result.update({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for folder in ("blocks", "native") for p in sorted((root / folder).rglob("*")) if p.is_file()})
    return result


def verify_result(output):
    root = safe_path(output)
    saved = read_json(root / "result.json", sealed=True)
    protocol = read_json(root / "protocol.json", sealed=True)
    value = read_json(root / "study.json", sealed=True)
    require(saved["version"] == protocol["protocol"] == PROTOCOL and saved["protocol_hash"] == protocol["record_hash"]
            and saved["study_hash"] == value["record_hash"] and value["study"]["protocol_hash"] == protocol["record_hash"]
            and value["study"]["protocol"] == PROTOCOL and saved["status"] in {"completed", "pending"}
            and saved["artifacts"] == _artifacts(root, Ledger(root, value, None)),
            "The finished study's bindings or evidence inventory changed")
    return saved


def run_study(spec, panel, derivations, output, *, repo=None, fixture_api=None, fixture_evaluate=None):
    validate_spec(spec)
    require(digest(panel) == spec["template"]["panel_hash"], "The panel is not the registered panel")
    require(digest(derivations) == spec["derivations_hash"], "The derivations are not the registered ones")
    require(set(derivations) == set(spec["pools"]["diagnostic_items"]), "Exactly the diagnostic items carry derivations")
    root = safe_path(output)
    with output_lock(root):
        if (root / "result.json").exists():
            saved = verify_result(root)
            require(saved["protocol_hash"] == spec["record_hash"], "The finished study belongs to another protocol")
            return saved
        if (root / "started.json").exists():
            return {"status": "pending", "reason": "interrupted_study_no_automatic_resume", "model_calls_submitted": 0}
        value = _manifest(spec, panel)
        if (root / "protocol.json").exists() or (root / "study.json").exists():
            require(read_json(root / "protocol.json", sealed=True) == spec
                    and read_json(root / "study.json", sealed=True) == value,
                    "The prepared protocol or manifest (implementation identity) differs from the current rebuild")
        fixture = value["model"]["provider"] == "fixture"
        require(fixture == (fixture_api is not None and fixture_evaluate is not None)
                and (fixture or (fixture_api is None and fixture_evaluate is None)),
                "Fixture hooks belong to a fixture study only")
        write_json(root / "protocol.json", spec)
        write_json(root / "study.json", value)
        write_json(root / "panel.json", panel)
        write_json(root / "derivations.json", seal({"derivations": derivations}))
        if not fixture:
            require(repo is not None, "A natural study needs the credential repository")
            require(backends.readiness(BENCHMARK, value["runtime"])["status"] == "ready", "Runtime is not ready")
        started = seal({"protocol_hash": spec["record_hash"], "study_hash": value["record_hash"],
                        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        write_json(root / "started.json", started)
        api, pending = fixture_api, None
        families = set(value["train_families"])
        train = [{"role": "train", "task": t} for t in panel["tasks"] if t["family_id"] in families]
        selection = [{"role": "selection", "task": t} for t in panel["tasks"] if t["family_id"] not in families]
        candidates, outcomes = [], []
        try:
            if not fixture:
                model = value["model"]
                api = CachedAPI(Path(repo), root / "api", provider=model["provider"], model=model["name"], workers=1,
                                reasoning_effort=model["reasoning_effort"],
                                **model.get("transport", {"initial_health_policy": "completed_response_v1"}),
                                **({"proxy": model["proxy"]} if "proxy" in model else {}), **client_options(value))
            write_json(root / "model_service.json", seal(api.service))
            ledger = Ledger(root, value, api)
            adapter = Adapter(value, root, ledger, fixture_evaluate=fixture_evaluate)
            for block in range(spec["blocks"]):
                frozen, outcome = run_block(spec, value, root, ledger, adapter, train, selection, block,
                                            value["recovery_policy"]["verifier_workers"], derivations)
                candidates.append(frozen)
                outcomes.append(outcome)
        except LearningPending as exc:
            pending = str(exc)
        except Exception as exc:  # the type only: provider text never enters a record
            pending = "error:" + type(exc).__name__
        finally:
            if api is not None and not fixture:
                api.close()
        ledger = Ledger(root, value, None)
        costs = ledger.snapshot()
        if pending is None and (costs.get("unclosed_calls") != 0 or ledger.usage_blocks_completion(costs)):
            pending = "usage_or_receipt_accounting_incomplete"
        analysis = analyze(spec, candidates, outcomes) if pending is None else None
        result = seal({"version": PROTOCOL, "protocol_hash": spec["record_hash"], "study_hash": value["record_hash"],
                       "status": "completed" if pending is None else "pending", "reason": pending,
                       "completed_blocks": len(outcomes), "blocks": spec["blocks"],
                       **({} if analysis is None else analysis), "costs": costs,
                       "artifacts": _artifacts(root, ledger), "deployment_authorized": False})
        write_json(root / "result.json", result)
        return result
