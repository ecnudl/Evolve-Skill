"""One learning-v8 stage redo on a frozen five-domain study, then one test cell (paid; user request 10/6).

Study F (learning v7) accepted its BigCodeBench and KOR-Bench updates on a margin of one
selection position and learned from 64 train tasks with pass/fail feedback only; on the
held-out test split those updates are noise. Learning v8 (``continual-learning-v8``) keeps
every v7 guard and changes four things: the selection role is the canonical **val** part
of ``fivebench-split-v2`` (never test), an update must win a frozen paired margin on it
(new unknowns are charged as losses), failed train rows show the expected answer or the
sanitized BigCodeBench execution evidence to the analyst (never to the solver), and the
native analysts get a transfer requirement. This tool runs exactly one such stage for one
domain from a chosen parent Skill (empty or one of F's recorded stage Skills), on train
families drawn outcome-blind from F's own development panel (KOR-Bench: stratified by
category with a per-rule task cap), and then evaluates the resulting Skill once on that
domain's test panel of the completed test evaluation -- the very panel file (by hash),
evaluation source, model service, scorer runtime and code identity that evaluated F's
policies, so the cell is paired position-by-position with the recorded No-Skill cell.

Scope: a stage redo for one domain is not a sequential five-domain study, not a
cross-domain interference measurement, and not a GEPA comparison; those need the
orchestrated v5 sequence. ``learn`` never resumes a begun stage (completed stages
replay), ``test`` never resumes a begun cell, and both re-verify the frozen inputs first.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import random
import subprocess
import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

VERSION = "fivebench-g-stage-v1"
SPLIT_VERSION = "fivebench-split-v2"
# The extension study (scripts/make_extension_study.py, 2026-10-13): single-call benchmarks added beside study F
# with their own protocol and split; study F, its split and every earlier artifact are untouched.
EXTENSION_STUDY = "extension-study-v1"
EXTENSION_SPLIT = "extension-split-v1"
EXTENSION_BENCHMARKS = ("livemath", "officeqa")
# Reviewed predecessor hashes of this file (Codex ACCEPTABLE) whose prepared stages this version may
# chain from, test and report: every later change was additive (cross-domain test cells, chaining).
# A stage still records the hash it was prepared with; an operation records the hash that ran it.
COMPATIBLE_TOOL_HASHES = frozenset({
    "b900086a6ac8c3ed5d383b57142600f2c12065c8098361220cc1479ae62d25a3",  # 10/6 SkillOpt redo queue (review round 4)
    "99082a7ac837a99d3aa601f2f0a7644c5e43e55dbb152d053a6c6573eea5ff4a",  # 10/6 + GEPA method support (reviewed)
    "e53255a3abaacce1fc5d780586124e861d3bd9332ddbcd00fb47848f76c8a28d",  # 10/6 chains: g: parents, cross-domain cells
    "d5c1e017ac73d181ef81985ec5908bc2d936db28c9f825622c5c617790ed7ea0",  # 10/8 v10 main-method stages (commit 7420960)
})
API_ONLY = ("bigcodebench", "searchqa", "korbench") + EXTENSION_BENCHMARKS  # Sheet/ALF need the native learning environment
# benchmarks whose validation-gated stages can take GENERATED selection tasks: (generator module, panel importer)
GENERATED_VAL = {"searchqa": ("scripts.generate_searchqa_tasks", "import_searchqa"),
                 "officeqa": ("scripts.generate_officeqa_tasks", "import_officeqa")}
# Learning v11 (``active_evidence``): the sibling package's own protocol; the stage record names the method and
# the manifest is the package's v10-shaped compatibility record (see skillopt/active_evidence/protocol.py).
ACTIVE_EVIDENCE = "active_evidence"
PARENTS = {"none": None, "f-s1": ("skillopt", 1), "f-s3": ("skillopt", 3), "f-s4": ("skillopt", 4)}
BUDGET = {"max_metric_calls": 4000, "max_reflection_calls": 128, "max_api_calls": 12000,
          "max_reported_tokens": 60_000_000, "max_iterations": 3, "minibatch_size": 8,
          "solver_max_tokens": 65536, "reflection_max_tokens": 4096}
# V9 (two-pass sign-test gate): confirmation passes need more metric calls, and labeled analyst
# output overflowed the 4096-token reflection cap on KOR-Bench (10/6), so the cap is doubled.
BUDGET_V9 = {**BUDGET, "max_metric_calls": 8000, "reflection_max_tokens": 8192}
# V10 (main method, rubric_research): v9 plus the verifier's own call budget. Per step: two policy
# calls, one probe/judge call per executed train row (128 on BigCodeBench/SearchQA, 90 on KOR-Bench),
# one review per row with probes and at most two research calls per reviewed row with a fact
# question -- an upper bound of 2 + 128 x 5 = 642 per step, 1,926 per three-step stage (realistic:
# ~650 per stage). The cap is a safety stop, not the expected cost; 4096 output tokens per call.
BUDGET_V10 = {**BUDGET_V9, "max_verifier_calls": 2000, "verifier_max_tokens": 4096}
# V11 (active_evidence): one step per stage by default (the post-update challenge replaces the val gate); the
# diagnoser proposes several hypotheses in one reply (8192 output tokens); the challenge re-solves up to
# 2 x (96 + 32 + 8) positions per step (decision rule v2) on top of the 128-row step rollout.
BUDGET_V11 = {**BUDGET_V10, "max_iterations": 1, "max_metric_calls": 12000, "max_verifier_calls": 3000,
              "verifier_max_tokens": 8192}
TRAIN = {"bigcodebench": {"families": 128}, "searchqa": {"families": 128},
         "korbench": {"families": 30, "tasks_per_family": 3, "stratify": "category"},
         # officeqa: 48 of the 50 training items of the SkillOpt paper's split (learning v11 needs a non-empty rest)
         "livemath": {"families": 128}, "officeqa": {"families": 48}}


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _sequence():
    from scripts import continue_fivebench_baselines as sequence
    return sequence


# ----------------------------------------------------------------------------- inputs
def _study(study):
    sequence = _sequence()
    root = safe_path(study)
    protocol = read_json(root / "protocol.json", sealed=True)
    if protocol.get("version") == EXTENSION_STUDY:
        # what the extension carries from study F (model record, learning service, retry options, lock, Skill
        # budget) is re-verified against F itself at every load; it has no reference plans or evaluation sources
        require(protocol["root"] == str(root) and protocol["references"] == {} and protocol["order"]
                and set(protocol["roles"]) == set(protocol["order"]) == set(protocol["layouts"])
                and set(protocol["order"]) <= set(EXTENSION_BENCHMARKS)
                and all(set(role) == {"runtime", "path"} and role["runtime"] == {} for role in protocol["roles"].values())
                and set(protocol["files"]) == {str(safe_path(role["path"])) for role in protocol["roles"].values()},
                "Invalid extension study")
        for benchmark in protocol["order"]:
            extension_layout(protocol, benchmark)  # the pinned, sealed data layout still is what the study binds
        parent = read_json(safe_path(protocol["derived_from"]["study"]) / "protocol.json", sealed=True)
        require(parent.get("version") == sequence.BUDGET_SEQUENCE, "An extension study derives from study F itself")
        _, base = _study(protocol["derived_from"]["study"])
        require(base["version"] == sequence.BUDGET_SEQUENCE
                and base["record_hash"] == protocol["derived_from"]["protocol_hash"]
                and all(protocol.get(key) == base.get(key)
                        for key in ("model", "learning_model_service", "learning_client_options"))
                and protocol["config"] == {"native_lock": base["config"]["native_lock"],
                                           "learning_recovery_policy": base["config"]["learning_recovery_policy"]},
                "The extension study no longer matches the study it was derived from")
        return root, protocol
    require(protocol["version"] == sequence.BUDGET_SEQUENCE and protocol["root"] == str(root),
            "Only the budget-derived (v4) study F and its extension study are supported")
    for ref in protocol["references"].values():
        sequence._check_budget_source(ref["source"], ref["evaluation_source"], sequence._skill_limit(protocol))
    return root, protocol


def extension_layout(protocol, benchmark):
    """(directory, record) of the sealed data layout an extension study pins for a benchmark, verified: the layout's
    hash, its benchmark, and that the study's development panel is that layout's panel, by path and hash."""
    pinned = protocol["layouts"][benchmark]
    require(type(pinned) is dict and set(pinned) == {"directory", "layout_hash"}, "Invalid layout reference")
    directory = safe_path(pinned["directory"])
    layout = read_json(directory / "layout.json", sealed=True)
    dev = str(directory / "dev_panel.json")
    require(layout["record_hash"] == pinned["layout_hash"] and layout["benchmark"] == benchmark
            and protocol["roles"][benchmark]["path"] == dev
            and protocol["files"].get(dev) == layout["dev_panel_sha256"],
            "The extension study does not match its pinned data layout")
    return directory, layout


def check_split(split, protocol, benchmark):
    """The split belongs to this study: study F reads the five-benchmark split, an extension study its own -- and an
    extension split must be exactly the study's pinned layout (parts, families, panel hashes, evaluation blocks): a
    resealed split that drops, say, the sealed test part is refused, since the split's own hash proves only itself."""
    extension = protocol.get("version") == EXTENSION_STUDY
    require(split["version"] == (EXTENSION_SPLIT if extension else SPLIT_VERSION)
            and split["f_study_usage"][benchmark]["protocol_hash"] == protocol["record_hash"],
            "The split was not verified against this study")
    if extension:
        directory, layout = extension_layout(protocol, benchmark)
        sources = {}
        for name in protocol["order"]:  # exactly the pinned panels of the study's benchmarks: no other source
            other, pinned = extension_layout(protocol, name)
            sources[str(other / "dev_panel.json")] = pinned["dev_panel_sha256"]
            sources[str(other / "val_panel.json")] = pinned["val_panel_sha256"]
        require(split["splits"][benchmark] == {**{part: layout["parts"][part] for part in ("train", "val", "test")},
                                               "reserve": []}
                and split["sources"] == sources and set(split["splits"]) == set(protocol["order"])
                and split["evaluation_blocks"][benchmark] == layout["evaluation_blocks"]
                and split["counts"][benchmark] == layout["counts"],
                "The split differs from the study's pinned data layout")


def check_val_source(protocol, benchmark, source):
    """The validation panel of an extension stage is the pinned layout's own file, unchanged (the split's source
    list alone could be extended by a resealed split)."""
    if protocol.get("version") != EXTENSION_STUDY:
        return
    directory, layout = extension_layout(protocol, benchmark)
    require(safe_path(source) == directory / "val_panel.json" and _sha(source) == layout["val_panel_sha256"],
            "The validation source is not the validation panel of the study's data layout")


def check_evaluation_block(protocol, benchmark, items):
    """An item file evaluated for an extension benchmark is one of its layout's evaluation blocks, unchanged."""
    if protocol.get("version") != EXTENSION_STUDY:
        return
    _, layout = extension_layout(protocol, benchmark)
    require(_sha(items) in {block["sha256"] for block in layout["evaluation_blocks"]["blocks"]},
            "The item file is not an evaluation block of the study's data layout")


def dev_panel_path(protocol, benchmark):
    """The development panel a stage draws its training tasks from, bound by hash in the study protocol: study F
    names it through its No-Skill reference plan, an extension study directly."""
    if protocol.get("version") == EXTENSION_STUDY:
        dev_path = protocol["roles"][benchmark]["path"]
    else:
        ref = protocol["references"][benchmark]
        plan = read_json(safe_path(ref["root"]) / "plan.json", sealed=True)
        require(plan["record_hash"] == ref["plan_hash"], "Reference plan changed")
        dev_path = plan["config"]["panels"][benchmark]
    require(protocol["files"].get(str(safe_path(dev_path))) == _sha(dev_path),
            "The development panel is not the frozen input the study recorded")
    return dev_path


def parent_skill(root, protocol, name, split_hash=None):
    """Empty, exactly the Skill a recorded F stage deployed, or the Skill a completed G stage deployed.

    ``g:<stage directory>`` chains stages: the parent is that stage's ``learned.json`` Skill --
    an accepted update or the carried parent of a COMPLETED stage (a pending stage never
    advances a chain) -- of the same study and split, prepared by this tool or a reviewed
    compatible predecessor, with its manifest/panel/result bindings re-verified.
    """
    if type(name) is str and name.startswith("f:"):
        # ``f:<text file>``: a FIXED operator-supplied text as the parent (learning v11, and v9 / v10 stages whose
        # selection set is generated -- see ``prepare``), e.g. the hand-written
        # generic instruction of active-evidence-generic-control-design-20261011.md, so that a step measures what
        # learning adds ON TOP of it. Bound by its hash: the file must stay unchanged for the life of the stage.
        # Authorship and what the author had seen are disclosed in the design memo, not verifiable here.
        require(Path(name[2:]).is_absolute(), "A fixed parent text is given by an absolute path (every later "
                                              "command re-reads it, from whatever working directory)")
        path = safe_path(name[2:])
        require(path.is_file(), "A fixed parent text is an existing file")
        skill = path.read_text(encoding="utf-8")
        require(skill.strip() != "", "A fixed parent text is not empty (the empty parent is 'none')")
        return skill, {"parent": name, "parent_stage_hash": None, "parent_action": "fixed_text",
                       "parent_skill_sha256": hashlib.sha256(skill.encode()).hexdigest()}
    if type(name) is str and name.startswith("m:"):
        # ``m:<study stage dir>:comparator|treatment``: one UNSELECTED branch candidate of a completed v11 matched
        # study (a frozen base for a refinement stage); bound to that stage's sealed records like a study reference
        skill, source = _study_branch(protocol, name, split_hash)
        return skill, {"parent": name, "parent_stage_hash": source["stage_hash"],
                       "parent_skill_sha256": source["skill_sha256"], "parent_proposal_hash": source["proposal_hash"]}
    if type(name) is str and name.startswith("g:"):
        previous = safe_path(name[2:])
        stage = read_json(previous / "stage.json", sealed=True)
        learned = read_json(previous / "learned.json", sealed=True)
        require(stage["version"] == VERSION and stage["protocol_hash"] == protocol["record_hash"]
                and stage["study"] == protocol["root"]
                and (split_hash is None or stage["split_hash"] == split_hash)
                and stage["tool_sha256"] in {_sha(Path(__file__)), *COMPATIBLE_TOOL_HASHES},
                "Parent G stage is not a stage of this study/split prepared by a compatible tool")
        manifest_record = read_json(previous / "manifest.json", sealed=True)
        result = read_json(previous / "learning/result.json", sealed=True)
        _verify_learning_evidence(previous, manifest_record, result)
        require(manifest_record["record_hash"] == stage["manifest_hash"]
                and _sha(previous / "panel.json") == stage["panel_sha256"]
                and learned["stage_hash"] == stage["record_hash"]
                and learned["learning_result_hash"] == result["record_hash"]
                and learned["status"] == result["status"] == "completed"
                and learned["action"] in {"selected_update", "completed_no_update"}
                and learned["skill_sha256"] == hashlib.sha256(learned["skill"].encode()).hexdigest()
                and learned["skill"] == (result["candidate_skill"] if learned["action"] == "selected_update"
                                         else manifest_record["parent_skill"])
                and (learned["action"] == "selected_update") == (result["candidate_skill"] != manifest_record["parent_skill"]),
                "Parent G stage is not a completed, consistently recorded stage")
        record = {"parent": name, "parent_stage_hash": stage["record_hash"],
                  "parent_learned_hash": learned["record_hash"], "parent_skill_sha256": learned["skill_sha256"]}
        if "verifier_policy" in result:
            require(learned.get("verifier_policy_hash") == digest(result["verifier_policy"]),
                    "Parent stage's recorded verifier policy differs from its sealed result")
            record["parent_verifier_policy"] = deepcopy(result["verifier_policy"])
        return learned["skill"], record
    require(name in PARENTS, "Unknown parent")
    if PARENTS[name] is None:
        return "", {"parent": name, "parent_stage_hash": None}
    method, number = PARENTS[name]
    benchmark = protocol["order"][number - 1]
    stage = read_json(root / method / f"s{number}-{benchmark}" / "stage.json", sealed=True)
    require(stage["protocol_hash"] == protocol["record_hash"] and stage["action"] == "selected_update",
            "Parent stage is not an accepted update of this study")
    return stage["skill"], {"parent": name, "parent_stage_hash": stage["record_hash"],
                            "parent_skill_sha256": hashlib.sha256(stage["skill"].encode()).hexdigest()}


def _drawn_challenge_tasks(previous):
    """Task hashes of every fresh position a v11 stage drew from its reserved pool (its sealed draw records)."""
    folder = previous / "learning" / "challenge"
    draws = sorted(folder.glob("*/draw.json")) if folder.exists() else []
    return {entry["task_hash"] for path in draws for entry in read_json(path, sealed=True)["fresh"]}


def _completed_stage(protocol, previous, split_hash):
    stage = read_json(previous / "stage.json", sealed=True)
    learned = read_json(previous / "learned.json", sealed=True)
    require(stage["version"] == VERSION and stage["protocol_hash"] == protocol["record_hash"]
            and stage["study"] == protocol["root"] and stage["split_hash"] == split_hash
            and learned["stage_hash"] == stage["record_hash"] and learned["status"] == "completed"
            and learned["action"] in {"selected_update", "completed_no_update"}
            and learned["skill_sha256"] == hashlib.sha256(learned["skill"].encode()).hexdigest(),
            "Reference stage is not a completed, consistently recorded G stage of this study and split")
    return stage, learned


def _study_branch(protocol, name, split_hash):
    """The text and provenance of ``m:<study stage dir>:comparator|treatment``: one branch candidate of a completed
    v11 matched study -- matched-scalar: comparator = the scalar branch, treatment = the feedback branch (both
    unselected); selection study: comparator = the native candidate (unselected; its treatment is a screen SELECTION
    and is not offered here). The chain must be the completed stage's own sealed step-0 chain (bound through the
    learned record to the learning result, and to the stage's manifest and arms); the proposal and the Skill must be
    the ones that chain records."""
    where, _, branch = name.rpartition(":")
    require(where.startswith("m:") and branch in {"comparator", "treatment"},
            "A study branch is given as m:<study stage directory>:comparator or :treatment")
    previous = safe_path(where[2:])
    stage, learned = _completed_stage(protocol, previous, split_hash)
    post_update = stage.get("arms", {}).get("post_update")
    require(stage["method"] == ACTIVE_EVIDENCE and post_update in {"matched_scalar_branch", "matched_selection_branch"},
            "A study reference comes from a v11 matched study stage")
    require(post_update == "matched_scalar_branch" or branch == "comparator",
            "A selection study offers its native candidate (comparator) only: its treatment is a screen selection")
    chain = read_json(previous / "learning" / "chain" / "0.json", sealed=True)
    result = read_json(previous / "learning" / "result.json", sealed=True)
    require(learned.get("learning_result_hash") == result["record_hash"] and result["status"] == "completed"
            and result.get("evidence_chain_hashes", [None])[0] == chain["record_hash"]
            and learned.get("evidence_chain_hashes") == result["evidence_chain_hashes"]
            and chain.get("manifest_hash") == stage["manifest_hash"] and chain.get("step") == 0
            and chain.get("arms") == stage["arms"],
            "Study reference chain is not the completed stage's own sealed step-0 chain")
    folder = "native_matched" if branch == "comparator" and post_update == "matched_scalar_branch" else "native"
    proposal = read_json(previous / "learning" / folder / "0" / "result.json", sealed=True)
    recorded = chain["matched"][branch]
    require(proposal["status"] == "candidate_ready" and recorded["proposal_hash"] == proposal["record_hash"]
            and recorded["skill_hash"] == digest(proposal["candidate_skill"]),
            "Study reference is not the recorded unselected branch candidate of a matched study")
    skill = proposal["candidate_skill"]
    return skill, {"stage": str(previous), "stage_hash": stage["record_hash"], "learned_hash": learned["record_hash"],
                   "benchmark": stage["benchmark"], "method": stage["method"], "learning_version": stage["learning_version"],
                   "selection_tasks": stage.get("selection_tasks"), "train_families": stage["train_families"],
                   "skill_sha256": hashlib.sha256(skill.encode()).hexdigest(), "action": "study_branch:" + branch,
                   "study": post_update, "proposal_hash": proposal["record_hash"],
                   "selection_exposure": "none (an unselected branch candidate of a study that deploys nothing)",
                   "provenance": "sealed stage, learned, result, chain and proposal records cross-checked; learning "
                                 "evidence not re-verified"}


def reference_skill(protocol, spec, split_hash, challenge_families, pool_hashes):
    """An evaluation-only reference Skill of a matched study, from a finished stage of the same study and split:

    * ``name=g:<stage dir>`` -- the Skill that stage's ``learned.json`` records (an accepted update or the carried
      parent of a COMPLETED stage). Refused when that stage SELECTED it on tasks of this stage's holdout pool: a v11
      stage's decision used fresh panels drawn from its reserved pool, and a Skill kept on some of the very tasks it
      is now compared on is not a clean reference (baseline stages selected on the canonical validation split, which
      is never in this panel).
    * ``name=m:<study stage dir>:comparator|treatment`` -- one UNSELECTED branch candidate of a completed v11 matched
      study (a study deploys nothing and selects nothing; its holdout outcomes were never used to choose the text).

    * ``name=none`` -- the EMPTY Skill, for a stage whose parent is a non-empty text (with an empty parent the parent
      reference already is the empty Skill).

    * ``name=f:<text file>`` -- a FIXED text the operator supplies (e.g. a hand-written, dataset-agnostic instruction
      used as a control): not learned from and not selected on any task, so there is nothing to cross-check except
      that it is a valid Skill text; the record seals its hash. Who wrote it and what its author had seen is the
      operator's disclosure (design memo), not something this record can show.

    For the two learned kinds the stage must not have trained on any family of this stage's challenge pool. Sealed
    stage / learned / chain / proposal records are read and cross-checked; the learning evidence is NOT re-verified
    here (the Skill is only solved on the drawn holdout, never used as a parent)."""
    name, separator, where = spec.partition("=")
    require(separator == "=" and (where == "none" or where[:2] in {"g:", "m:", "f:"}),
            "A reference is given as name=g:<finished G stage directory>, name=m:<study stage directory>:<branch>, "
            "name=f:<fixed Skill text file> or name=none (the empty Skill)")
    if where == "none":
        # the EMPTY Skill as a named reference: only for a stage whose parent is not empty (prepare checks it), so
        # that "no Skill" is measured on the same holdout as the parent text and the branches learned from it
        return {"name": name, "skill": "",
                "source": {"skill_sha256": hashlib.sha256(b"").hexdigest(), "skill_bytes": 0, "action": "empty_skill",
                           "selection_exposure": "none (the empty Skill: no text)"}}
    if where.startswith("f:"):
        path = safe_path(where[2:])
        require(path.is_file(), "A fixed reference text is an existing file")
        skill = path.read_text(encoding="utf-8")
        require(skill.strip() != "", "A fixed reference text is not empty (the empty Skill is the parent reference)")
        return {"name": name, "skill": skill,
                "source": {"file": str(path), "skill_sha256": hashlib.sha256(skill.encode()).hexdigest(),
                           "skill_bytes": len(skill.encode()), "action": "fixed_text",
                           "selection_exposure": "none (a fixed operator-supplied text: not learned from and not "
                                                 "selected on any task of this study)",
                           "provenance": "operator-supplied file sealed by its hash; authorship and what the author "
                                         "had seen are disclosed in the design memo, not verifiable here"}}
    if where.startswith("m:"):
        skill, source = _study_branch(protocol, where, split_hash)
        require(not set(source.pop("train_families")) & set(challenge_families),
                "A reference Skill was learned from families of this stage's holdout pool")
        return {"name": name, "skill": skill, "source": {**source, "train_families_disjoint_from_holdout_pool": True}}
    previous = safe_path(where[2:])
    stage, learned = _completed_stage(protocol, previous, split_hash)
    require(not set(stage["train_families"]) & set(challenge_families),
            "A reference Skill was learned from families of this stage's holdout pool")
    overlap = len(_drawn_challenge_tasks(previous) & set(pool_hashes))
    require(overlap == 0, "A reference Skill was selected on tasks of this stage's holdout pool")
    return {"name": name, "skill": learned["skill"],
            "source": {"stage": str(previous), "stage_hash": stage["record_hash"], "learned_hash": learned["record_hash"],
                       "benchmark": stage["benchmark"], "method": stage["method"],
                       "learning_version": stage["learning_version"], "selection_tasks": stage.get("selection_tasks"),
                       "train_families_disjoint_from_holdout_pool": True, "skill_sha256": learned["skill_sha256"],
                       "action": learned["action"],
                       "selection_exposure": "none on this stage's holdout pool (no sealed fresh draw overlaps it)",
                       "provenance": "sealed stage and learned records cross-checked; learning evidence not re-verified"}}


def _val_families(split, benchmark):
    return {e["task_id"]: e["family_id"] for e in split["splits"][benchmark]["val"]}


def val_panel(split, benchmark, source):
    """The canonical val part from the very file the split was built from (by hash)."""
    from skillopt.continual_eval import datasets

    require(split["sources"].get(str(safe_path(source))) == _sha(source), "Val source is not the split's file")
    wanted = _val_families(split, benchmark)
    if benchmark == "searchqa":
        rows = [r for r in read_json(source) if str(r["id"]) in wanted]
        panel = datasets.import_searchqa(rows, partition="skill_confirmation",
                                         revision=f"skillopt-searchqa-native-val:{SPLIT_VERSION}:{split['record_hash'][:12]}")
    else:
        panel = read_json(source)
    datasets.validate_panel(panel)
    require({str(t["task_id"]): str(t["family_id"]) for t in panel["tasks"]} == wanted
            and all(t["partition"] == "skill_confirmation" for t in panel["tasks"]),
            f"{benchmark}: val panel differs from the split")
    return panel



def generated_val_panel(directory, protocol, split, benchmark, seed, dev_panel):
    """The selection set of a validation-gated stage made of GENERATED tasks instead of the canonical validation
    partition (docs/handoff/generated-validation-design-20261013.md): the published items of a COMPLETED generation
    (the benchmark's generator of ``GENERATED_VAL``) that was made from exactly this stage's training tasks -- same
    study, split and seed, the same training-task hashes. The tasks carry the selection label the frozen learner
    expects; no canonical validation, test or reserve item is read. Returns (panel, provenance)."""
    import importlib

    from skillopt.continual_eval import datasets

    require(benchmark in GENERATED_VAL, "Generated validation tasks exist for SearchQA and OfficeQA only so far")
    generation = importlib.import_module(GENERATED_VAL[benchmark][0])
    path, record, result = generation.check(directory)
    train, _ = train_tasks(dev_panel, split, benchmark, seed)
    require(record["protocol_hash"] == protocol["record_hash"] and record["split_hash"] == split["record_hash"]
            and record["benchmark"] == benchmark and record["seed"] == seed
            and record["source_task_hashes"] == sorted(digest(t) for t in train),
            "The generated tasks were not made from this stage's training tasks")
    # One family per SOURCE training task: the questions written from the same snippets are siblings, and the
    # frozen gate's sign test counts one sign per family (never one per sibling).
    family_map = generation.family_map(directory)
    panel = getattr(datasets, GENERATED_VAL[benchmark][1])(
        read_json(path), partition="skill_confirmation",
        revision=f"{record['version']}:{result['items_sha256'][:12]}", family_map=family_map)
    datasets.validate_panel(panel)
    canonical = [e for part in split["splits"][benchmark].values() for e in part]
    families = {t["family_id"] for t in panel["tasks"]}
    require(len(panel["tasks"]) >= 1 and all(f.startswith("generated-") for f in families)
            and not families & {e["family_id"] for e in canonical}
            and not families & {t["family_id"] for t in dev_panel["tasks"]}
            and not {str(t["task_id"]) for t in panel["tasks"]} & {str(e["task_id"]) for e in canonical},
            "A generated task collides with a task or family of the canonical split")
    return panel, {"generation": safe_path(directory).name, "generation_hash": record["record_hash"],
                   "generation_result_hash": result["record_hash"], "items": result["items"],
                   "items_sha256": result["items_sha256"], "source_tasks": record["source_tasks"],
                   "families": len(families), "generator_version": record["version"]}

def train_tasks(dev_panel, split, benchmark, seed, spec=None):
    """Outcome-blind train families from F's development panel (all inside canonical train). ``spec`` overrides the
    frozen per-benchmark draw (learning v11 only: a larger step subset); the ranking by seeded family hash is the
    same, so a larger draw contains the default one."""
    spec = TRAIN[benchmark] if spec is None else spec
    train_ids = {e["task_id"] for e in split["splits"][benchmark]["train"]}
    tasks = [t for t in dev_panel["tasks"] if t["partition"] == "development"]
    require(tasks and {str(t["task_id"]) for t in tasks} <= train_ids, "Development panel leaves canonical train")
    by_family = {}
    for task in tasks:
        by_family.setdefault(task["family_id"], []).append(task)
    key = lambda family: hashlib.sha256(json.dumps([seed, benchmark, family]).encode()).hexdigest()  # noqa: E731
    if spec.get("stratify") == "category":
        groups = {}
        for family, members in by_family.items():
            category = {m["private"]["category"] for m in members}
            require(len(category) == 1, "A rule spans categories")
            groups.setdefault(category.pop(), []).append(family)
        per_group, remainder = divmod(spec["families"], len(groups))
        chosen = []
        for index, category in enumerate(sorted(groups)):
            ranked = sorted(groups[category], key=key)
            count = per_group + (1 if index < remainder else 0)
            require(len(ranked) >= count, f"Not enough {category} rules")
            chosen.extend(ranked[:count])
    else:
        ranked = sorted(by_family, key=key)
        require(len(ranked) >= spec["families"], "Not enough train families")
        chosen = ranked[:spec["families"]]
    out = []
    for family in sorted(chosen):
        members = sorted(by_family[family], key=lambda t: str(t["task_id"]))
        cap = spec.get("tasks_per_family")
        if cap is not None:
            members = random.Random(key(family)).sample(members, min(cap, len(members)))
        out.extend(sorted(members, key=lambda t: str(t["task_id"])))
    return out, sorted(chosen)


def learning_panel(dev_panel, val, split, benchmark, seed):
    train, families = train_tasks(dev_panel, split, benchmark, seed)
    panel = {**deepcopy(dev_panel), "tasks": deepcopy(train) + deepcopy(val["tasks"])}
    require(not {t["family_id"] for t in train} & {t["family_id"] for t in val["tasks"]}, "Train/val family overlap")
    return panel, families, sorted({t["family_id"] for t in val["tasks"]})


def _outside(out, root, protocol, extra=()):
    frozen = {root, *map(safe_path, extra)} | {safe_path(ref[k]) for ref in protocol["references"].values()
                                               for k in ("root", "source", "evaluation_source") if k in ref}
    require(all(not out.is_relative_to(p) and not p.is_relative_to(out) for p in frozen),
            "Use a new directory outside the study and its inputs")


# ----------------------------------------------------------------------------- learn
def _protocol(learning_version):
    """(learning version id, frozen policy, budget) of the supported learning protocols."""
    from skillopt.continual_learning.contracts import CONFIRMATION_VERSION, GENERALIZATION_VERSION, VERIFIER_VERSION
    from skillopt.continual_learning.recovery import POLICY_V8, POLICY_V9, POLICY_V10

    require(learning_version in {"v8", "v9", "v10", "v11"}, "Unknown learning version")
    if learning_version == "v11":
        return VERIFIER_VERSION, POLICY_V10, BUDGET_V11  # the base record of the active-evidence protocol
    if learning_version == "v10":
        return VERIFIER_VERSION, POLICY_V10, BUDGET_V10
    if learning_version == "v9":
        return CONFIRMATION_VERSION, POLICY_V9, BUDGET_V9
    return GENERALIZATION_VERSION, POLICY_V8, BUDGET


# Limits a stage may override at preparation (the shape of diagnosis and of the update); the operating point of the
# post-update decision and of the screen (panel sizes, coverage, alphas) is frozen and never overridable here.
# ``train_panel_rows`` (optional, absent by default) sizes the in-sample shadow measurement, which the acting
# decision never reads.
OVERRIDABLE_LIMITS = frozenset({"view_rows", "view_output_chars", "max_hypotheses", "max_checks_per_case",
                                "max_diagnoser_calls_per_step", "max_research_pages", "edit_budget", "report_chars",
                                "summary_chars", "train_panel_rows"})


def limit_overrides(specs):
    """``key=integer`` overrides of the overridable limits (ranges are validated by the protocol)."""
    overrides = {}
    for spec in specs:
        key, separator, value = spec.partition("=")
        require(separator == "=" and key in OVERRIDABLE_LIMITS and key not in overrides and value.isdigit(),
                "A limit override is key=integer for one of: " + ", ".join(sorted(OVERRIDABLE_LIMITS)))
        overrides[key] = int(value)
    return overrides


def prepare_active_evidence(study, split_path, output, repo, *, benchmark, parent, seed, learning_version, arms,
                            references=(), update_mode="native", train_families=None, limits=(),
                            analyst_profile="native"):
    """A learning v11 stage: the step subset (F's outcome-blind train draw) plus the challenge pool (every other
    development task of F's panel, all inside canonical train). No canonical validation split is read or authorized;
    the challenge pool is a fixed reserved development pool that serves the post-update selection (decision rule v2)
    and is held out from diagnosis, reflection and Research. The effective limits are fixed here, before any outcome."""
    from skillopt.active_evidence import PROTOCOL
    from skillopt.active_evidence import protocol as ae
    from skillopt.continual_learning.recovery import RETRY_POLICIES

    version, policy, budget = _protocol(learning_version)
    require(learning_version == "v11", "The active-evidence method is learning v11")
    require(benchmark in API_ONLY, "This tool runs API-only domains; Sheet/ALF need the native learning environment")
    root, protocol = _study(study)
    out = safe_path(output)
    _outside(out, root, protocol, [split_path])
    require(not out.exists(), "Use a new directory")
    split = read_json(split_path, sealed=True)
    check_split(split, protocol, benchmark)
    dev_path = dev_panel_path(protocol, benchmark)
    dev_panel = read_json(dev_path)
    skill, parent_record = parent_skill(root, protocol, parent, split["record_hash"])
    parent_record.pop("parent_verifier_policy", None)  # the rubric is frozen this round: nothing is inherited
    train_spec = dict(TRAIN[benchmark])
    if train_families is not None:
        # a larger step subset: the development tasks a validation split would have used go to learning instead (the
        # reserved challenge pool shrinks accordingly); same seeded ranking, so it contains the default subset
        require(type(train_families) is int and train_families >= train_spec["families"],
                "--train-families can only enlarge the frozen step subset")
        # the native updater makes one analyst call per minibatch: its sealed reflection ceiling grows with the rows
        # (a matched-scalar study on 256 rows needs 156-168 calls against the default ceiling of 128)
        scale = -(-train_families // train_spec["families"])
        budget = {**budget, "max_reflection_calls": budget["max_reflection_calls"] * scale}
        train_spec["families"] = train_families
    train, step_families = train_tasks(dev_panel, split, benchmark, seed, train_spec)
    train_ids = {e["task_id"] for e in split["splits"][benchmark]["train"]}
    pool = sorted((t for t in dev_panel["tasks"] if t["partition"] == "development"
                   and t["family_id"] not in set(step_families)), key=lambda t: str(t["task_id"]))
    require(pool and {str(t["task_id"]) for t in pool} <= train_ids, "Challenge pool leaves canonical train")
    challenge_families = sorted({t["family_id"] for t in pool})
    panel = {**deepcopy(dev_panel), "tasks": deepcopy(train) + deepcopy(pool)}
    pool_hashes = frozenset(digest(t) for t in pool)
    if type(parent) is str and parent.startswith("m:"):
        # a study-branch parent must not have been learned from this stage's holdout pool either
        require(not set(_study_branch(protocol, parent, split["record_hash"])[1]["train_families"]) & set(challenge_families),
                "The parent Skill was learned from families of this stage's holdout pool")
    reference_skills = [reference_skill(protocol, spec, split["record_hash"], challenge_families, pool_hashes)
                        for spec in references]
    require(skill != "" or all(r["skill"] != "" for r in reference_skills),
            "The empty Skill is already this stage's parent reference")
    value = ae.manifest(panel, step_families=step_families, challenge_families=challenge_families,
                        model=deepcopy(protocol["model"]), budget=budget, runtime=protocol["roles"][benchmark]["runtime"],
                        parent_skill=skill, seed=seed, arms=arms,
                        limits={**ae.effective_limits(arms, len(pool)), **limit_overrides(limits)},
                        reference_skills=reference_skills, update_mode=update_mode, analyst_profile=analyst_profile)
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "panel.json", panel)
    write_json(out / "manifest.json", value)
    record = seal({"version": VERSION, "study": str(root), "protocol_hash": protocol["record_hash"],
                   "split": str(safe_path(split_path)), "split_hash": split["record_hash"], "benchmark": benchmark,
                   **parent_record, "seed": seed, "repo": str(safe_path(repo)), "method": ACTIVE_EVIDENCE,
                   "learning_version": PROTOCOL, "base_learning_version": version, "recovery_policy": policy,
                   "arms": value["active_evidence"]["arms"], "limits": value["active_evidence"]["limits"],
                   "update_mode": value["active_evidence"]["update_mode"],
                   **({} if analyst_profile == "native" else {"analyst_profile": analyst_profile}),
                   # requested defaults; the effective fresh panel is capped by the eligible challenge-pool tasks
                   "limits_requested": ae.default_limits(arms), "eligible_fresh_tasks": len(pool),
                   "limit_overrides": limit_overrides(limits),
                   "reference_skills": [{"name": r["name"], **r["source"]} for r in reference_skills],
                   "client_options": {"delivery_retry_policy": RETRY_POLICIES[version]},
                   "learning_model_service": protocol["learning_model_service"],
                   "train_spec": train_spec, "train_spec_default": TRAIN[benchmark],
                   "train_families": step_families, "train_tasks": len(train),
                   "challenge_families": len(challenge_families), "challenge_tasks": len(pool),
                   "selection_tasks": 0, "selection_families": 0,
                   "selection_partition": "no_canonical_validation_split__reserved_development_challenge_pool_selects",
                   "val_source_sha256": None, "dev_panel_sha256": protocol["files"][str(safe_path(dev_path))],
                   "manifest_hash": value["record_hash"], "panel_sha256": _sha(out / "panel.json"),
                   "native_lock": protocol["config"]["native_lock"], "budget": budget,
                   "tool_sha256": _sha(Path(__file__)), "learning_sources": value["source_identity"],
                   "package_sources": value["active_evidence"]["package_sources"],
                   "data_scope": "step_and_reserved_challenge_pool_are_development_inside_canonical_train__canonical_validation_"
                                 "and_test_untouched",
                   "deployment_authorized": False})
    write_json(out / "stage.json", record)
    return record


def prepare(study, split_path, output, repo, *, benchmark, parent, val_source, seed, method="skillopt",
            gepa_source=None, learning_version="v8", arms=None, references=(), update_mode="native",
            train_families=None, limits=(), generated_val=None, analyst_profile="native"):
    from skillopt.continual_learning.contracts import VERIFIER_METHOD, manifest
    from skillopt.continual_learning.feedback import LABELED_PROFILE, VERIFIER_PROFILE
    from skillopt.continual_learning.recovery import RETRY_POLICIES

    if method == ACTIVE_EVIDENCE or learning_version == "v11":
        require(method == ACTIVE_EVIDENCE and learning_version == "v11" and gepa_source is None
                and generated_val is None,
                "The active-evidence method is learning v11 and vice versa (no GEPA source, no generated validation)")
        return prepare_active_evidence(study, split_path, output, repo, benchmark=benchmark, parent=parent, seed=seed,
                                       learning_version=learning_version,
                                       arms=arms or {"feedback": "diagnosis_research", "post_update": "challenge_replay"},
                                       references=references, update_mode=update_mode, train_families=train_families,
                                       limits=limits, analyst_profile=analyst_profile)
    require(arms is None and not references and update_mode == "native" and train_families is None and not limits
            and analyst_profile == "native",
            "Arms and reference Skills belong to the active-evidence method")
    # a fixed-text parent outside learning v11: only for the SkillOpt / Rubric+Research learners (v9 / v10), and
    # there only (a) with a GENERATED selection set (generated-validation-design-20261013.md, section 6) or (b) in
    # an extension study, which has no chains and no test cells and whose default starting point is an initial
    # instruction (owner's decision of 2026-10-13); study-F stages gated on the canonical validation partition keep
    # their chain parents. Part (b) is checked below, once the study is loaded.
    fixed_parent = type(parent) is str and parent.startswith("f:")
    require(not fixed_parent or (method in {"skillopt", VERIFIER_METHOD} and learning_version in {"v9", "v10"}),
            "A fixed-text parent is a learning v11 option, or goes with a generated validation set (v9 / v10)")
    version, policy, budget = _protocol(learning_version)

    require(benchmark in API_ONLY, "This tool runs API-only domains; Sheet/ALF need the native learning environment")
    require(method in {"skillopt", "gepa", VERIFIER_METHOD} and (method == "gepa") == (gepa_source is not None),
            "GEPA needs the pinned official source; SkillOpt takes none")
    require((method == VERIFIER_METHOD) == (learning_version == "v10"),
            "The main method (rubric_research) is learning v10 and vice versa")
    if method == "gepa":
        from skillopt.continual_learning.gepa import official_gepa

        official_gepa(gepa_source)  # pinned commit, clean tree, installed package byte-identical
    root, protocol = _study(study)
    require(not fixed_parent or generated_val is not None or protocol.get("version") == EXTENSION_STUDY,
            "A fixed-text parent is a learning v11 option, or goes with a generated validation set (v9 / v10)")
    out = safe_path(output)
    require((val_source is None) != (generated_val is None),
            "Give the canonical validation source or a generated validation set, not both")
    require(generated_val is None or method in {"skillopt", VERIFIER_METHOD},
            "Generated validation tasks serve the SkillOpt and Rubric+Research learners")
    _outside(out, root, protocol, [split_path, val_source or generated_val])
    require(not out.exists(), "Use a new directory")
    split = read_json(split_path, sealed=True)
    check_split(split, protocol, benchmark)
    dev_path = dev_panel_path(protocol, benchmark)
    dev_panel = read_json(dev_path)
    generated = None
    if generated_val is None:
        check_val_source(protocol, benchmark, val_source)
        val = val_panel(split, benchmark, val_source)
    else:
        val, generated = generated_val_panel(generated_val, protocol, split, benchmark, seed, dev_panel)
    skill, parent_record = parent_skill(root, protocol, parent, split["record_hash"])
    panel, train_families, selection_families = learning_panel(dev_panel, val, split, benchmark, seed)
    model = deepcopy(protocol["model"])  # F's learning model: same service, 3600 s recovery ceiling
    verifier_policy = None
    if method == VERIFIER_METHOD:
        # The co-evolving rubric comes only from a completed rubric_research G stage (per domain);
        # any other parent (empty, an F stage, a baseline G stage) starts from the frozen defaults.
        verifier_policy = parent_record.pop("parent_verifier_policy", None)
    else:
        parent_record.pop("parent_verifier_policy", None)
    value = manifest(panel, train_families=train_families, selection_families=selection_families, model=model,
                     budget=budget, runtime=protocol["roles"][benchmark]["runtime"], parent_skill=skill,
                     seed=seed, method=method, version=version, recovery_policy=deepcopy(policy),
                     feedback_profile=VERIFIER_PROFILE if method == VERIFIER_METHOD else LABELED_PROFILE,
                     parent_verifier_policy=verifier_policy)
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "panel.json", panel)
    write_json(out / "manifest.json", value)
    record = seal({"version": VERSION, "study": str(root), "protocol_hash": protocol["record_hash"],
                   "split": str(safe_path(split_path)), "split_hash": split["record_hash"], "benchmark": benchmark,
                   **parent_record, "seed": seed, "repo": str(safe_path(repo)), "method": method,
                   **({"gepa_source": str(safe_path(gepa_source))} if method == "gepa" else {}),
                   "learning_version": version, "recovery_policy": policy,
                   "client_options": {"delivery_retry_policy": RETRY_POLICIES[version]},
                   "learning_model_service": protocol["learning_model_service"],
                   "train_spec": TRAIN[benchmark], "train_families": train_families,
                   "train_tasks": sum(t["partition"] == "development" for t in panel["tasks"]),
                   "selection_tasks": len(val["tasks"]), "selection_families": len(selection_families),
                   "selection_partition": "skill_confirmation",
                   "selection_source": ("canonical_validation_partition" if generated is None else
                                        "generated_from_this_stage_training_tasks__no_canonical_validation_read"),
                   **({} if generated is None else {"generated_val": generated}),
                   "val_source_sha256": _sha(val_source) if generated is None else generated["items_sha256"],
                   "dev_panel_sha256": protocol["files"][str(safe_path(dev_path))],
                   "manifest_hash": value["record_hash"], "panel_sha256": _sha(out / "panel.json"),
                   "native_lock": protocol["config"]["native_lock"], "budget": budget,
                   "tool_sha256": _sha(Path(__file__)), "learning_sources": value["source_identity"],
                   "data_scope": ("train_is_development_inside_canonical_train_selection_is_canonical_val_test_untouched"
                                  if generated is None else
                                  "train_is_development_inside_canonical_train_selection_is_generated_from_these_"
                                  "training_tasks_canonical_val_and_test_untouched"),
                   "deployment_authorized": False})
    write_json(out / "stage.json", record)
    return record


def _load(output):
    out = safe_path(output)
    record = read_json(out / "stage.json", sealed=True)
    require(record["version"] == VERSION
            and record["tool_sha256"] in {_sha(Path(__file__)), *COMPATIBLE_TOOL_HASHES},
            "Tool changed (not this version nor a reviewed compatible predecessor)")
    root, protocol = _study(record["study"])
    require(protocol["record_hash"] == record["protocol_hash"], "Study changed")
    value = read_json(out / "manifest.json", sealed=True)
    panel = read_json(out / "panel.json")
    require(value["record_hash"] == record["manifest_hash"] and _sha(out / "panel.json") == record["panel_sha256"],
            "Stage inputs changed")
    skill, parent_record = parent_skill(root, protocol, record["parent"], record["split_hash"])
    policy = parent_record.pop("parent_verifier_policy", None)
    require(value["parent_skill"] == skill and all(record[k] == v for k, v in parent_record.items()), "Parent changed")
    if _method(record) == ACTIVE_EVIDENCE:
        require(value.get("parent_verifier_policy") is None
                and value.get("active_evidence", {}).get("method") == ACTIVE_EVIDENCE, "Active-evidence manifest expected")
    else:
        require(value.get("parent_verifier_policy") == (policy if value["method"] == "rubric_research" else None),
                "Parent verifier policy changed")
    return out, record, root, protocol, value, panel


def _manifest_method(record):
    """The method string the stage's manifest carries (the v11 package runs on a v10-shaped compatibility record)."""
    return "rubric_research" if _method(record) == ACTIVE_EVIDENCE else _method(record)


def _active_evidence_handoff(learning_root):
    """Learning v11: diagnostic probe executions the package began need a receipt with confirmed cleanup."""
    sequence = _sequence()
    for intent in (safe_path(learning_root) / "diagnosis").glob("*/executions/*.intent.json"):
        receipt = intent.with_name(intent.name[: -len(".intent.json")] + ".json")
        require(receipt.exists(), "Open diagnostic execution intents require operator review")
        sequence._require_cleanup(read_json(receipt, sealed=True)["execution"])


def _verify_learning_evidence(out, value, result):
    """Archived learning evidence of a finished stage, without rebuilding its manifest from current sources.

    The sealed result names the identity it ran under and every artifact (call and evaluation
    receipts, intents, native proposals, steps, service) by content hash; a completed replay in
    the learner checks exactly these. Here the saved identity must bind this stage's manifest and
    every recorded artifact must still exist with its recorded hash.
    """
    learning = out / "learning"
    identity = read_json(learning / "identity.json", sealed=True)
    require(result["identity_hash"] == identity["record_hash"] and identity["manifest"] == value,
            "Learning result does not belong to this stage's manifest")
    artifacts = result["artifacts"]
    require(type(artifacts) is dict and artifacts, "Learning result records no artifacts")
    for name, expected in artifacts.items():
        path = safe_path(learning / name)
        require(path.is_relative_to(learning) and path.is_file() and _sha(path) == expected,
                "A recorded learning artifact is missing or changed")
    # Inventory: nothing may exist in a governed artifact category that the sealed result does not
    # record (the categories the learners themselves inventory: ledger receipts and intents, native
    # proposals and steps, host-side scorer artifacts). Other files (e.g. GEPA's official_state, API
    # cache, workspaces) are outside these inventories and are not judged here.
    recorded = set(artifacts)
    present = {f"{folder}/{p.name}" for folder in ("calls", "call_intents", "evaluations", "evaluation_intents")
               for p in (learning / folder).glob("*.json")}
    present |= {str(p.relative_to(learning)) for folder in ("native", "steps")
                for p in (learning / folder).rglob("*.json")}
    present |= {str(p.relative_to(learning)) for p in (learning / "host_only/scorer_artifacts").rglob("*")
                if p.is_file() and p.name != ".writer.lock"}
    # V10: the verifier's sealed records, retrieved document bytes and host-only calibration are governed too.
    present |= {str(p.relative_to(learning)) for folder in ("verifier", "host_only/verifier")
                for p in (learning / folder).rglob("*") if p.is_file()}
    if result.get("method") == ACTIVE_EVIDENCE:
        # V11: the package's sealed records (chain, challenge, diagnosis incl. documents and executions, host-only
        # triage) and the stage's top-level markers are governed too.
        # (every file, not only JSON: the stage's own replay inventories every file of these folders)
        present |= {str(p.relative_to(learning)) for folder in ("chain", "challenge", "diagnosis", "host_only/triage",
                                                                 "native", "native_matched", "steps", "screen")
                    for p in (learning / folder).rglob("*") if p.is_file()}
        present |= {name for name in ("identity.json", "panel.json", "started.json") if (learning / name).exists()}
    require(present <= recorded, "Learning evidence contains artifacts the sealed result does not record")


def _recorded_outcome(out, record, value):
    """The stage's recorded learning outcome, verified against its sealed result (no replay, no calls)."""
    learned = read_json(out / "learned.json", sealed=True)
    result = read_json(out / "learning/result.json", sealed=True)
    _verify_learning_evidence(out, value, result)
    deployed = result["candidate_skill"] if learned["action"] == "selected_update" else value["parent_skill"]
    require(learned["stage_hash"] == record["record_hash"] and learned["learning_result_hash"] == result["record_hash"]
            and learned["status"] == result["status"]
            and learned["action"] in {"selected_update", "completed_no_update", "pending_carry_parent"}
            and (learned["status"] == "completed") == (learned["action"] != "pending_carry_parent")
            and (learned["action"] == "selected_update") == (result["status"] == "completed"
                                                             and result["candidate_skill"] != value["parent_skill"])
            and learned["skill"] == deployed
            and learned["skill_sha256"] == hashlib.sha256(learned["skill"].encode()).hexdigest(),
            "Recorded learning outcome does not bind its sealed result")
    return learned


def status(output):
    """Zero-call: verified outcome of a stage (used by the chain driver before advancing)."""
    out, record, root, protocol, value, panel = _load(output)
    require(value["method"] == _manifest_method(record), "Manifest method differs from the stage record")
    if not (out / "learned.json").exists():
        return {"version": VERSION, "benchmark": record["benchmark"], "status": "prepared", "action": None,
                "record_hash": record["record_hash"]}
    learned = _recorded_outcome(out, record, value)
    return {**learned, "tests": sorted(p.name for p in out.glob("summary*.json"))}


def learn(output):
    from skillopt.continual_learning.contracts import validate_manifest

    out, record, root, protocol, value, panel = _load(output)
    require(value["method"] == _manifest_method(record), "Manifest method differs from the stage record")
    if (out / "learned.json").exists():
        # Completed stage: the historical record stands (older compatible snapshots included);
        # it is verified against its sealed result, never re-validated against current sources.
        return _recorded_outcome(out, record, value)
    active = _method(record) == ACTIVE_EVIDENCE
    if active:
        from skillopt.active_evidence import protocol as ae
        from skillopt.active_evidence import stage as ae_stage

        ae.validate_manifest(value, panel)

        def run_stage(value, panel, output, *, repo):
            return ae_stage.run_stage(value, panel, output, repo=repo)
    else:
        validate_manifest(value, panel)
        if _method(record) == "gepa":
            from skillopt.continual_learning.gepa import run_stage as gepa_stage

            def run_stage(value, panel, output, *, repo):
                return gepa_stage(value, panel, output, repo=repo, gepa_source=record["gepa_source"])
        else:
            from skillopt.continual_learning.skillopt import run_stage
    sequence = _sequence()
    with safe_path(record["native_lock"]).open("a") as resource:
        # F's native lock serializes every paid workload of this study family: one native (container)
        # workload at a time and one holder of the key's concurrency ceiling, for all three domains.
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        sequence.check_client_service(record["repo"], value["model"], out / "client-check",
                                      record["learning_model_service"], client_options=record["client_options"])
        result = run_stage(value, panel, out / "learning", repo=record["repo"])
        sequence.verify_service(out / "learning", record["learning_model_service"])
        sequence.require_safe_handoff(out / "learning", result)
        if active:
            _active_evidence_handoff(out / "learning")
    state = sequence.transition(value["parent_skill"], result, value["recovery_policy"]["skill_budget_bytes"])
    step_keys = (("step", "rollout", "known", "unknown", "diagnosis_status", "rows_with_evidence", "proposal_status",
                  "candidate_hash", "challenge_status", "challenge_summary", "decision", "decision_reason",
                  "decision_hash", "chain_hash", "matched_outcome", "matched_reason") if active else
                 ("step", "gate_action", "wins", "losses", "ties", "net_wins", "required_net_wins",
                  "candidate_new_unknown", "families_improving", "families_regressing", "parent_score",
                  "candidate_score", "leaked_evidence", "first_pass", "confirmation_pass", "pooled_p_value",
                  "accept_alpha_effective", "screen_alpha", "tries"))
    summary = seal({"version": VERSION, "stage_hash": record["record_hash"], "benchmark": record["benchmark"],
                    "operated_by_tool_sha256": _sha(Path(__file__)),
                    "learning_result_hash": result["record_hash"], "status": result["status"],
                    "reason": result["reason"], **state,
                    "skill_sha256": hashlib.sha256(state["skill"].encode()).hexdigest(),
                    "skill_bytes": len(state["skill"].encode()),
                    "steps": [{k: s.get(k) for k in step_keys} for s in result.get("steps", [])],
                    "accepted_steps": result.get("accepted_steps"), "costs": result["costs"],
                    "method": _method(record),
                    **({"protocol": result.get("protocol"), "arms": result.get("arms"),
                        "decisions": result.get("decisions"),
                        "evidence_chain_hashes": result.get("evidence_chain_hashes")} if active else {}),
                    **({"verifier_steps": result.get("verifier_steps"),
                        "verifier_policy_hash": digest(result["verifier_policy"]),
                        "verifier_policy_status": {k: v["status"] for k, v in result["verifier_policy"].items()}}
                       if _method(record) == "rubric_research" else {}),
                    **({k: result.get(k) for k in ("official_best_is_parent", "official_best_rejected", "final_margin",
                                                   "leaked_candidates_refused", "parent_unknown_excluded")}
                       if _method(record) == "gepa" else {}),
                    "deployment_authorized": False})
    write_json(out / "learned.json", summary)
    return summary


# ----------------------------------------------------------------------------- test
def _method(record):
    """The stage's method; the first reviewed predecessor wrote SkillOpt-only records without the key."""
    return record.get("method", "skillopt")


def _suffix(record, benchmark, replicate=None):
    """File/run suffix of a test cell: other domains get ``-<domain>``, replicate cells ``-r<k>``."""
    require(replicate is None or (type(replicate) is int and 1 <= replicate <= 9), "Replicate index must be 1..9")
    return ("" if benchmark == record["benchmark"] else "-" + benchmark) + ("" if replicate is None else f"-r{replicate}")


def _test_request(record, protocol, test_eval, out, skill, benchmark=None, replicate=None):
    """A one-repeat test cell of this Skill (on this or another domain's test panel) in the
    completed test evaluation's own terms. ``replicate`` k names an additional independent cell
    of the same Skill (fresh samples), used to measure run-to-run noise; it never replaces the
    primary cell."""
    benchmark = benchmark or record["benchmark"]
    require(benchmark in protocol["order"], "Unknown test domain")
    ref = protocol["references"][benchmark]
    plan = read_json(safe_path(ref["root"]) / "plan.json", sealed=True)
    require(plan["record_hash"] == ref["plan_hash"], "Reference plan changed")
    panel_path = safe_path(test_eval) / f"panels/{benchmark}.json"
    eval_plan = read_json(safe_path(test_eval) / "test_eval.json", sealed=True)
    require(eval_plan["protocol_hash"] == protocol["record_hash"] and eval_plan["split_hash"] == record["split_hash"]
            and eval_plan["panels"][benchmark] == _sha(panel_path), "Test evaluation does not belong to this study/split")
    config = deepcopy(plan["config"])
    config["panels"] = {b: (str(panel_path) if b == benchmark else None) for b in config["panels"]}
    config["partition"], config["repeats"], config["methods"] = "final", 1, ["no_skill", _method(record)]
    override = protocol.get("evaluation_runtime_overrides", {}).get(benchmark)
    if override is not None:
        runtime = config["runtime"][benchmark]
        runtime["recalculation"] = {**runtime["recalculation"], **override["recalculation"]}
    orchestrator = [p for p in protocol["source_files"] if p.endswith("scripts/continue_fivebench_baselines.py")]
    require(len(orchestrator) == 1, "The study binds exactly one frozen orchestrator")
    return seal({"version": VERSION, "operation": "test", "benchmark": benchmark, "skill": skill,
                 "method": _method(record),
                 **({"replicate": replicate} if replicate is not None else {}),
                 "provenance": "fivebench_g_stage:" + record["record_hash"]
                 + ("" if replicate is None else f":replicate:{replicate}"), "config": config,
                 "orchestrator": orchestrator[0], "orchestrator_sha256": protocol["source_files"][orchestrator[0]],
                 "run": str(out / ("test-cell" + _suffix(record, benchmark, replicate))), "repo": record["repo"],
                 "workers": protocol["config"]["workers"],
                 "service": eval_plan["services"][benchmark], "panel_sha256": eval_plan["panels"][benchmark],
                 "expected_source_identity": eval_plan["identities"][benchmark]["source_identity"],
                 "expected_host_runtime": eval_plan["identities"][benchmark]["host_runtime"],
                 "evaluation_source": ref["evaluation_source"], "python": ref["python"],
                 "no_skill_cell": str(safe_path(test_eval) / f"results/{benchmark}/no_skill.json"),
                 "no_skill_cell_hash": read_json(safe_path(test_eval) / f"results/{benchmark}/no_skill.json",
                                                 sealed=True)["record_hash"],
                 "tool_sha256": _sha(Path(__file__))})


def test(output, test_eval, benchmark=None, replicate=None):
    out, record, root, protocol, value, panel = _load(output)
    require(protocol.get("version") != EXTENSION_STUDY,
            "An extension study provides no test cells (its sealed test parts are listed by id only)")
    # a v9 / v10 stage that started from a fixed text has no test cell: its parent was never measured on the test
    # panel, so neither "the parent is already measured" (no update) nor a chain comparison holds for it
    require(record.get("parent_action") != "fixed_text" or _method(record) == ACTIVE_EVIDENCE,
            "A v9 / v10 stage with a fixed-text parent has no test cell; it is read with the panel evaluation tool")
    learned = _recorded_outcome(out, record, value)
    # The primary cell exists only for an accepted update (a stage without one deploys its parent,
    # whose cells are already recorded). A replicate cell re-measures whatever a COMPLETED stage
    # deploys -- including the empty Skill of a no-update stage from parent none, i.e. No-Skill.
    require(learned["action"] == "selected_update"
            or (replicate is not None and learned["action"] == "completed_no_update"),
            "Only an accepted update is tested (the parent is already measured); replicates need a completed stage")
    benchmark = benchmark or record["benchmark"]
    suffix = _suffix(record, benchmark, replicate)
    request_path = out / f"test-request{suffix}.json"
    if request_path.exists():
        request = read_json(request_path, sealed=True)
        fresh = _test_request(record, protocol, test_eval, out, learned["skill"], benchmark, replicate)
        drop = {"tool_sha256", "record_hash"}
        old = {"method": "skillopt", **request}  # the first reviewed predecessor wrote SkillOpt-only requests
        require({k: v for k, v in old.items() if k not in drop} == {k: v for k, v in fresh.items() if k not in drop}
                and request["tool_sha256"] in {_sha(Path(__file__)), *COMPATIBLE_TOOL_HASHES},
                "Test request changed (only a reviewed compatible predecessor's tool hash may differ)")
    else:
        request = _test_request(record, protocol, test_eval, out, learned["skill"], benchmark, replicate)
        write_json(request_path, request)
    result_path = out / f"test-result{suffix}.json"
    if not result_path.exists():
        env = dict(os.environ, PYTHONPATH=request["evaluation_source"])
        command = [request["python"], str(Path(__file__).absolute()), "worker", "--request", str(request_path),
                   "--output", str(result_path)]
        with safe_path(record["native_lock"]).open("a") as resource, (out / f"test-worker{suffix}.log").open("ab") as handle:
            # Generation and native scoring of the cell run under the same lock F's test controller held.
            fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
            code = subprocess.run(command, cwd=request["evaluation_source"], env=env, stdout=handle, stderr=handle).returncode
        require(code == 0 and result_path.is_file(), "Test worker failed; inspect the log, do not retry")
    result = read_json(result_path, sealed=True)
    # A recorded result must be this request's own cell for this Skill (also on replay).
    checkpoint = read_json(safe_path(result["root"]) / f"checkpoints/{_method(record)}/h0/s1.json", sealed=True)
    require(result["request_hash"] == request["record_hash"] and result["root"] == request["run"]
            and result["skill_sha256"] == learned["skill_sha256"] == hashlib.sha256(learned["skill"].encode()).hexdigest()
            and checkpoint["skill_text"] == learned["skill"] and checkpoint["provenance"] == request["provenance"]
            and checkpoint["plan_hash"] == result["plan_hash"] and checkpoint["record_hash"] == result["checkpoint_hash"],
            "Recorded test cell does not belong to this request and Skill")
    return compare(out, record, learned, request, result)


def compare(out, record, learned, request, result):
    """Position-paired comparison with the recorded No-Skill test cell of the same panel."""
    baseline = read_json(request["no_skill_cell"], sealed=True)
    require(baseline["record_hash"] == request["no_skill_cell_hash"] and baseline["benchmark"] == request["benchmark"]
            == result["benchmark"] and baseline["policy"] == "no_skill", "Wrong No-Skill cell")
    # The No-Skill cell must be the same frozen plan family as the new cell: same panel file, partition,
    # repeats, code and interpreter identity (its sealed plan is re-read, not trusted from the summary).
    base_plan = read_json(safe_path(baseline["root"]) / "plan.json", sealed=True)
    new_plan = read_json(safe_path(result["root"]) / "plan.json", sealed=True)
    require(base_plan["record_hash"] == baseline["plan_hash"] and new_plan["record_hash"] == result["plan_hash"]
            and base_plan["config"]["panels"] == new_plan["config"]["panels"]
            and base_plan["config"]["partition"] == new_plan["config"]["partition"] == "final"
            and base_plan["config"]["repeats"] == new_plan["config"]["repeats"] == 1
            and base_plan["source_identity"] == new_plan["source_identity"]
            and base_plan["host_runtime"] == new_plan["host_runtime"]
            and {k: v for k, v in base_plan["config"].items() if k != "methods"}
            == {k: v for k, v in new_plan["config"].items() if k != "methods"},
            "No-Skill cell and new cell are not the same frozen evaluation (panel, partition, runtime, model)")
    base = {(r["task_id"], r["repeat"]): r["status"] for r in baseline["rows"]}
    rows = {(r["task_id"], r["repeat"]): r["status"] for r in result["rows"]}
    require(set(base) == set(rows), "Test cell positions differ from the No-Skill cell")
    # Same paired semantics as the F test report: a win is a confirmed No-Skill failure that the new
    # Skill passes, a loss a No-Skill pass that it fails; positions unknown on either side are
    # reported separately, never counted as a win or a loss.
    known = {k for k in rows if base[k] in {"pass", "fail"} and rows[k] in {"pass", "fail"}}
    wins = sum(base[k] == "fail" and rows[k] == "pass" for k in known)
    losses = sum(base[k] == "pass" and rows[k] == "fail" for k in known)
    unknown = {"no_skill_unknown": sum(base[k] not in {"pass", "fail"} for k in rows),
               "new_unknown": sum(rows[k] not in {"pass", "fail"} for k in rows),
               "jointly_known": len(known)}
    families = {}
    for r in result["rows"]:
        k = (r["task_id"], r["repeat"])
        if k not in known:
            continue
        delta = int(rows[k] == "pass") - int(base[k] == "pass")
        families[r["family_id"]] = families.get(r["family_id"], 0) + delta
    summary = seal({"version": VERSION, "stage_hash": record["record_hash"], "benchmark": request["benchmark"],
                    "operated_by_tool_sha256": _sha(Path(__file__)),
                    **({"replicate": request["replicate"]} if "replicate" in request else {}),
                    "learned_on": record["benchmark"], "parent": record["parent"], "skill_sha256": learned["skill_sha256"],
                    "test_positions": result["positions"], "test_counts": result["counts"],
                    "no_skill_counts": baseline["counts"], "wins_vs_no_skill": wins, "losses_vs_no_skill": losses,
                    "net_vs_no_skill": wins - losses, **unknown,
                    "families_improving": sum(v > 0 for v in families.values()),
                    "families_regressing": sum(v < 0 for v in families.values()),
                    "val_gate": learned["steps"], "test_costs": result["costs"],
                    "one_test_cell_not_a_study": True, "deployment_authorized": False})
    write_json(out / ("summary" + _suffix(record, request["benchmark"], request.get("replicate")) + ".json"), summary)
    return summary


# ----------------------------------------------------------------------------- worker (evaluation source)
def _frozen_module(path):
    import importlib.util

    spec = importlib.util.spec_from_file_location("frozen_sequence", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worker(request_path, output):
    from skillopt.continual_eval import core, runner
    from skillopt.continual_eval.core import freeze_plan, load_checkpoint, load_plan, register_checkpoint

    request = read_json(request_path, sealed=True)
    require(request["version"] == VERSION and request["operation"] == "test", "Unsupported worker request")
    require(_sha(Path(__file__)) == request["tool_sha256"], "The tool changed")
    require(Path(core.__file__).resolve().parents[2] == safe_path(request["evaluation_source"]),
            "Worker imported the wrong evaluation source")
    require(core.source_identity() == request["expected_source_identity"]
            and core.runtime_identity() == request["expected_host_runtime"],
            "Evaluation code or interpreter differs from the test evaluation's")
    config, benchmark, new = request["config"], request["benchmark"], safe_path(request["run"])
    require(_sha(config["panels"][benchmark]) == request["panel_sha256"], "The test panel changed")
    require(_sha(request["orchestrator"]) == request["orchestrator_sha256"], "The study orchestrator changed")
    sequence = _frozen_module(request["orchestrator"])  # the study's own helpers, not the evaluation source's scripts/
    require(not new.exists() and not safe_path(output).exists(), "Never silently retry a begun evaluation")
    plan = freeze_plan(config, new)
    require(plan["config"] == config and plan["source_identity"] == request["expected_source_identity"]
            and plan["host_runtime"] == request["expected_host_runtime"], "Frozen plan does not bind this request")
    sequence.check_client_service(request["repo"], config["model"], new / "api", request["service"])
    method = request["method"]
    require(method in {"skillopt", "gepa", "rubric_research", ACTIVE_EVIDENCE} and config["methods"] == ["no_skill", method],
            "Unsupported method")
    register_checkpoint(new, method, "h0", 1, request["skill"], provenance=request["provenance"])
    runner.generate(new, method=method, history="h0", stage=1, benchmark=benchmark,
                    repo=request["repo"], workers=request["workers"])
    sequence.require_eval_handoff(new)
    runner.score_checkpoint(new, method=method, history="h0", stage=1, benchmark=benchmark)
    plan = load_plan(new)
    checkpoint = load_checkpoint(new, method, "h0", 1, plan)
    require(checkpoint["skill_text"] == request["skill"] and checkpoint["provenance"] == request["provenance"],
            "Policy checkpoint changed")
    sequence.verify_service(new, request["service"])
    sequence.require_eval_handoff(new)
    accounting = runner.report(new)
    rows = [read_json(p, sealed=True) for p in sorted((new / "host_only/scores").glob("*.json"))]
    expected = len([t for t in plan["tasks"] if t["benchmark"] == benchmark]) * plan["repeats"]
    require(len(rows) == expected and accounting["run_accounting"]["unclosed_calls"] == 0, "Incomplete test cell")
    result = seal({"root": str(new), "plan_hash": plan["record_hash"], "benchmark": benchmark, "positions": expected,
                   "request_hash": request["record_hash"], "skill_sha256": checkpoint["skill_hash"],
                   "checkpoint_hash": checkpoint["record_hash"],
                   "counts": dict(Counter(r["status"] for r in rows)), "costs": accounting["run_accounting"],
                   "rows": [{k: r[k] for k in ("task_id", "family_id", "repeat", "status", "record_hash")} for r in rows]})
    write_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "learn", "test", "status", "worker"))
    parser.add_argument("--output", required=True)
    parser.add_argument("--study")
    parser.add_argument("--split")
    parser.add_argument("--repo")
    parser.add_argument("--benchmark", choices=API_ONLY)
    parser.add_argument("--parent", help="none, f-s1/f-s3/f-s4 (study F stage Skills), g:<finished G stage dir>, "
                                         "m:<v11 study stage dir>:comparator|treatment (an unselected study branch) "
                                         "or, learning v11 only, f:<fixed text file> (an operator-supplied text)")
    parser.add_argument("--test-benchmark", choices=API_ONLY + ("spreadsheetbench", "alfworld"),
                        help="test cell domain (default: the stage's own domain)")
    parser.add_argument("--val-source")
    parser.add_argument("--analyst-profile",
                        help="prepare only, active-evidence with pass/fail feedback and the native update: an analyst "
                             "prompt profile of skillopt/active_evidence/updater.py (default native = unchanged); "
                             "the profile is sealed at preparation and cannot be given to any other command")
    parser.add_argument("--generated-val",
                        help="SkillOpt / Rubric+Research stages only, instead of --val-source: the directory of a "
                             "completed scripts/generate_{searchqa,officeqa}_tasks.py generation of this stage's training "
                             "tasks; its tasks become the selection set (no canonical validation data is read)")
    parser.add_argument("--seed", type=int, default=20261006)
    parser.add_argument("--test-eval")
    parser.add_argument("--request")
    parser.add_argument("--method", choices=("skillopt", "gepa", "rubric_research", ACTIVE_EVIDENCE), default="skillopt")
    parser.add_argument("--learning-version", choices=("v8", "v9", "v10", "v11"), default="v8")
    parser.add_argument("--arm-feedback", choices=("scalar", "diagnosis", "diagnosis_research", "hidden_failure"),
                        help="active_evidence only: the feedback arm (default diagnosis_research)")
    parser.add_argument("--limit", action="append", default=[],
                        help="active-evidence only, repeatable: key=integer override of a diagnosis/update limit "
                             "(e.g. view_rows=64); decision and screen operating points are not overridable")
    parser.add_argument("--train-families", type=int,
                        help="active-evidence only: a larger step subset than the frozen per-benchmark draw (the "
                             "reserved challenge pool shrinks accordingly)")
    parser.add_argument("--arm-update", choices=("native", "screened"), default="native",
                        help="active-evidence only: how a step's candidate text is chosen (screened = the "
                             "composition-aware screen on the step rows)")
    parser.add_argument("--arm-post-update", choices=("none", "challenge_replay", "matched_scalar_branch",
                                                      "matched_selection_branch"),
                        help="active_evidence only: the post-update arm (default challenge_replay)")
    parser.add_argument("--reference", action="append", default=[],
                        help="matched-branch study only, repeatable: name=g:<finished G stage dir>, "
                             "name=m:<study stage dir>:<branch>, name=f:<fixed text file> or name=none (the empty "
                             "Skill, under a non-empty parent) -- an evaluation-only "
                             "reference Skill solved on the drawn holdout")
    parser.add_argument("--replicate", type=int, help="k >= 1: an additional independent test cell of the deployed Skill")
    parser.add_argument("--gepa-source")
    args = parser.parse_args()
    require(args.command == "prepare" or args.analyst_profile is None,
            "--analyst-profile belongs to prepare: a stage runs under the profile sealed in its manifest")
    if args.command == "prepare":
        arms = None
        if args.method == ACTIVE_EVIDENCE:
            arms = {"feedback": args.arm_feedback or "diagnosis_research",
                    "post_update": args.arm_post_update or "challenge_replay"}
        else:
            require(args.arm_feedback is None and args.arm_post_update is None, "Arms belong to the active-evidence method")
        result = prepare(args.study, args.split, args.output, args.repo, benchmark=args.benchmark,
                         parent=args.parent, val_source=args.val_source, seed=args.seed, method=args.method,
                         gepa_source=args.gepa_source, learning_version=args.learning_version, arms=arms,
                         references=tuple(args.reference), update_mode=args.arm_update,
                         train_families=args.train_families, limits=tuple(args.limit),
                         generated_val=args.generated_val, analyst_profile=args.analyst_profile or "native")
    elif args.command == "learn":
        result = learn(args.output)
    elif args.command == "test":
        result = test(args.output, args.test_eval, args.test_benchmark, args.replicate)
    elif args.command == "status":
        result = status(args.output)
    else:
        result = worker(args.request, args.output)
    print(json.dumps({k: v for k, v in result.items() if k in (
        "version", "benchmark", "status", "action", "reason", "net_wins", "wins_vs_no_skill", "losses_vs_no_skill",
        "net_vs_no_skill", "accepted_steps", "train_tasks", "selection_tasks", "record_hash")}, ensure_ascii=False))
    if args.command == "learn" and result["action"] == "pending_carry_parent":
        # A pending learning result is an operator-review stop, not a completed stage: exit nonzero so
        # a queue never advances past it. completed_no_update is a normal (successful) outcome.
        sys.exit(3)
    if args.command == "status":
        # 0 = completed with an accepted update, 10 = completed without update, 20 = any other recorded state.
        # Uncaught exceptions exit 1, so no verified outcome shares a code with a failure.
        sys.exit(0 if result["action"] == "selected_update" else 10 if result["action"] == "completed_no_update" else 20)


if __name__ == "__main__":
    main()
