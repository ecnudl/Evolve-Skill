"""Benchmark profiles: how a domain's tasks are checked -- inputs/outputs, execution environment, the evidence train
time exposes and hides, the check kinds that are reliable, the task transforms that are allowed and what the mode
cannot observe. Descriptive and hand-maintained (plus the frozen verifier constants); a profile never learns from
labels or scores and never defines what one task requires -- the task text does."""
from __future__ import annotations

import json

from skillopt.continual_eval.core import require
from skillopt.continual_learning.verifier import (
    DEFAULT_POLICIES,
    EXCEPTION_NAMES,
    HARNESS_CAPABILITIES,
    PROBE_KINDS,
    STRUCTURE_KEYS,
)

PROFILE_VERSION = "active-evidence-benchmark-profiles-v2"
# The declarative argument-state check this mode adds beside the frozen v6 probe kinds (checks.py): the harness
# snapshots the JSON-normalized arguments before and after ONE call and compares them.
STATE_CHECK = "state"
INFORMATION_PERMISSIONS = {
    "diagnoser": "public task, generated output, host pass/fail of the step rows, batch summary, profile, frozen rubric",
    "check_review": "limited blinding: contract, candidate checks and rubric only -- no output, host status, hypothesis "
                    "verdict or check rationale",
    "analyst": "public task, generated output, host pass/fail, itemized evidence reports, step summary",
    "hidden_failure_study_arm": "message-branch analysts only: bounded final exception messages (with test names) of "
                                "the failing hidden tests of FAILED development step rows -- label feedback under the "
                                "sealed release profile of the manifest; a study control, never the method",
    "challenge_pool": "development-partition tasks outside the step subset; never shown to diagnoser or analyst",
    "never": "hidden tests, reference answers, canonical solutions, final/held-out data; hidden-test tracebacks stay "
             "host-only except the bounded failure messages of the hidden_failure study arm",
}
PROFILES = {
    "bigcodebench": {
        "supported": True,
        "io": {"public": ["prompt", "entry_point"], "private_hidden": ["test"],
               "output": "one Python program (the solver adapter extracts the source; a missing code fence is not a "
                         "delivery error by itself)"},
        "environment": "pinned native container image (manifest runtime), no network, read-only root, fresh container "
                       "per execution; hidden tests and probe harnesses run through the same official untrusted_check",
        "evidence_available": {
            "train": ["public task text", "generated program", "host pass/fail of the hidden unit tests "
                      "(tracebacks stay host-only)"],
            "hidden": ["hidden unit tests", "canonical solution"],
        },
        "reliable_checks": {
            "executed": [*PROBE_KINDS, STATE_CHECK],
            "capabilities": HARNESS_CAPABILITIES,
            "raises_whitelist": sorted(EXCEPTION_NAMES),
            "structure_keys": {k: list(v) for k, v in STRUCTURE_KEYS.items()},
            "state": "argument objects compared by JSON-normalized snapshot before/after one legal call; applies only "
                     "where the contract states preservation or in-place modification",
        },
        "transforms": {
            "fresh_instances": "real development tasks outside the step subset (challenge pool); no synthetic BCB tasks "
                               "(nothing hidden to score them against)",
            "near_miss": "selection of real tasks whose contract states the inverted condition; never generated",
            "replay": "step rows re-solved by both Skills under fresh rollout keys",
        },
        "limits": ["documentation whitelist covers the Python 3.11 standard library only (no pandas/numpy/matplotlib "
                   "pages)", "structure checks need their own admission", "an identical Skill run twice flips 6-10% "
                   "of positions", "execution cannot observe files, network, stdout, plotting state, dtypes or "
                   "random sample values"],
        "default_rubric": DEFAULT_POLICIES["bigcodebench"],
    },
    "searchqa": {
        "supported": True,
        "io": {"public": ["question", "context"], "private_hidden": ["answers"],
               "output": "free text; the final answer inside <answer>...</answer>"},
        "environment": "no execution; the host scores by SQuAD-normalized exact match against hidden answers",
        "evidence_available": {"train": ["question and public context", "response", "host pass/fail"],
                               "hidden": ["reference answers"]},
        "reliable_checks": {"executed": [], "judged": ["answer form", "question scope"],
                            "note": "no factual oracle: a judged check is at most a pending explanation"},
        "transforms": {"fresh_instances": "real development tasks outside the step subset", "near_miss": "none",
                       "replay": "step rows re-solved by both Skills"},
        "limits": ["no generator", "no execution", "contract quotes come from the question only"],
        "default_rubric": DEFAULT_POLICIES["searchqa"],
    },
    "korbench": {
        "supported": True,
        "io": {"public": ["rule", "question"], "private_hidden": ["answer", "category", "rule_id"],
               "output": "free text; the final answer inside [[...]]"},
        "environment": "the official KOR-Bench scorer runs in the pinned container; one family per rule",
        "evidence_available": {"train": ["rule and question", "response", "host pass/fail"],
                               "hidden": ["reference answer"]},
        "reliable_checks": {"executed": [], "judged": ["format compliance", "one visible rule step"],
                            "note": "this round judges only; the label-free kor.verify formal check (format and visible "
                                    "rule steps, not factual correctness) is not wired into diagnosis yet"},
        "transforms": {"fresh_instances": "real development tasks outside the step subset (unseen rules under family "
                                          "disjointness); the rule-instance generator with near-miss answers is deferred",
                       "near_miss": "deferred (kor_probes.generate)", "replay": "step rows re-solved by both Skills"},
        "limits": ["a formal check is not factual verification", "family disjointness makes fresh tasks unseen-rule"],
        "default_rubric": DEFAULT_POLICIES["korbench"],
    },
    "livemath": {
        "supported": True,
        "arms": [{"feedback": "scalar", "post_update": "none"}],  # no diagnosis tables for this domain yet
        "io": {"public": ["question", "choices"], "private_hidden": ["answer"],
               "output": "free text; exactly one option letter inside <answer>...</answer>"},
        "environment": "no execution; the host compares the letter in the last answer tag with the correct option's "
                       "letter (a reply in any other form is wrong); one family per source paper",
        "evidence_available": {"train": ["question and the five options", "response", "host pass/fail"],
                               "hidden": ["the correct option's letter", "the source theorem and proof sketch"]},
        "reliable_checks": {"executed": [], "judged": ["answer form", "visible reasoning against the stated hypotheses"],
                            "note": "no mathematical oracle: a judged check is at most a pending explanation"},
        "transforms": {"fresh_instances": "real development tasks outside the step subset", "near_miss": "none",
                       "replay": "step rows re-solved by both Skills"},
        "limits": ["no generator", "no execution", "five-way chance is 0.20", "the benchmark's wrong options follow "
                   "construction conventions a Skill can learn"],
        "default_rubric": DEFAULT_POLICIES["livemath"],
    },
    "officeqa": {
        "supported": True,
        "arms": [{"feedback": "scalar", "post_update": "none"}],  # no diagnosis tables for this domain yet
        "io": {"public": ["question", "context"], "private_hidden": ["answer"],
               "output": "free text; the final answer inside <answer>...</answer>"},
        "environment": "no execution; one-call form (the parsed pages the question refers to are supplied, there is "
                       "no retrieval); the host scores the last answer tag by the original normalised exact match",
        "evidence_available": {"train": ["question and supplied pages", "response", "host pass/fail"],
                               "hidden": ["reference answer"]},
        "reliable_checks": {"executed": [], "judged": ["answer form", "question scope"],
                            "note": "no factual oracle: a judged check is at most a pending explanation"},
        "transforms": {"fresh_instances": "real development tasks outside the step subset", "near_miss": "none",
                       "replay": "step rows re-solved by both Skills"},
        "limits": ["no generator yet", "no execution", "exact match without numeric tolerance",
                   "not the multi-turn retrieval task of the benchmark's own protocol"],
        "default_rubric": DEFAULT_POLICIES["officeqa"],
    },
    "spreadsheetbench": {"supported": False,
                         "reason": "no verifier or diagnostic execution adapter in the learning loop; old modes only"},
    "alfworld": {"supported": False,
                 "reason": "no verifier or diagnostic execution adapter in the learning loop; old modes only"},
}


def profile(benchmark):
    require(benchmark in PROFILES, "Unknown benchmark")
    return PROFILES[benchmark]


def supported(benchmark):
    return profile(benchmark)["supported"]


def profile_text(benchmark, limit=3000):
    """The bounded prompt view of a profile (everything except the long frozen harness text, which the probe prompts
    already carry)."""
    value = profile(benchmark)
    require(value["supported"], f"{benchmark}: unsupported by the active-evidence mode")
    view = {k: v for k, v in value.items() if k not in {"supported", "default_rubric"}}
    checks = dict(view["reliable_checks"])
    checks.pop("capabilities", None)
    checks.pop("raises_whitelist", None)
    view["reliable_checks"] = checks
    view["information_permissions"] = INFORMATION_PERMISSIONS
    text = json.dumps({"profile_version": PROFILE_VERSION, "benchmark": benchmark, **view}, ensure_ascii=False, indent=1)
    return text if len(text) <= limit else text[:limit] + " …[truncated]"
