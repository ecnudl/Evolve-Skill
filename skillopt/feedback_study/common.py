"""Shared mechanisms of the sidecar feedback studies: a frozen-rubric verifier, the study manifest, evidence
binding of a fresh train rollout and a cell scheduler. Nothing here changes a learning protocol."""
from __future__ import annotations

import hashlib
import re
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, require
from skillopt.continual_learning.contracts import MULTIDOMAIN_VERSIONS, VERIFIER_METHOD, VERIFIER_VERSION, manifest
from skillopt.continual_learning.feedback import VERIFIER_PROFILE
from skillopt.continual_learning.ledger import LearningPending
from skillopt.continual_learning.verifier import Verifier, validate_policy
from skillopt.validator_pilot.api import digest

RUBRIC_FIELDS = {"benchmark", "policy", "policy_hash", "status", "citations", "sources", "parent_policy_hash"}
ARM_NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")


def study_sources(names):
    """The code identity of ONE study protocol: exactly the package modules it executes (the learning sources are
    bound by the base manifest). Naming them explicitly keeps a later study's new module from changing it."""
    package = Path(__file__).resolve().parent
    require(type(names) is tuple and names and all(type(n) is str and n.endswith(".py") and "/" not in n for n in names)
            and len(set(names)) == len(names), "Explicit study module names required")
    return {"feedback_study/" + name: hashlib.sha256((package / name).read_bytes()).hexdigest() for name in sorted(names)}


def unsealed(record):
    return {k: v for k, v in record.items() if k != "record_hash"}


def validate_rubric_record(record, benchmark):
    """A complete frozen rubric record: the exact seven-field policy, its hash and the fields the v10 report and
    calibration code read. The rubric text is the treatment; nothing in it is ever re-proposed."""
    require(type(record) is dict and RUBRIC_FIELDS <= set(record) and record["benchmark"] == benchmark
            and validate_policy(record["policy"]) is record["policy"]
            and digest(record["policy"]) == record["policy_hash"]
            and type(record["citations"]) is list and type(record["sources"]) is list,
            "A frozen rubric needs its exact policy, hash, status, citations and sources")
    return record


def local_rubric(record):
    """The study-local view of a frozen rubric record: the same policy, hash, status, citations and sources, but none
    of the source step's own call trace -- ``_calibrate``'s delivery accounting counts a policy record's trace, and a
    historical proposal's calls are not this study's calls (the full record stays in the protocol)."""
    return {**{k: record[k] for k in sorted(RUBRIC_FIELDS)}, "verifier_version": record.get("verifier_version"),
            "source_record_hash": record.get("record_hash"), "trace": []}


class FixedRubricVerifier(Verifier):
    """The v10 verifier under ONE frozen rubric: no policy proposal, no Research, no learning step.

    Rows are judged (KOR/QA) exactly as ``Verifier._probe_row`` judges them under the given rubric, with the same
    prompts, parser and v7 delivery handling. Every rubric arm has its own record tree (``verifier/<rollout>-<arm>``,
    ``host_only/verifier/<rollout>-<arm>``) and its own ledger logical ids (``verifier:<rollout>-<arm>:judge:
    <evidence>``), so arms judging the same rows never share a cache identity. ``self.arm`` stays the base class's
    research-arm attribute; the study arm is ``self.rubric_arm``.
    """

    def __init__(self, manifest_value, ledger, root, rollout, arm, policy_record):
        require(type(arm) is str and ARM_NAME.fullmatch(arm) is not None, "Invalid rubric arm name")
        require(type(rollout) is int and rollout >= 0, "Invalid rollout")
        require(manifest_value["benchmark"] in {"korbench", "searchqa"},
                "Fixed-rubric studies judge text domains only (no probe execution, no Research)")
        super().__init__(manifest_value, ledger, root, f"{rollout}-{arm}")
        self.rollout, self.rubric_arm = rollout, arm
        self.rubric = local_rubric(validate_rubric_record(policy_record, self.benchmark))

    def run(self, *args, **kwargs):
        raise AssertionError("A fixed-rubric verifier has no proposal step; use judge_row/calibrate")

    def propose_policy(self, *args, **kwargs):
        raise AssertionError("A fixed-rubric verifier never proposes a policy")

    def _research(self, *args, **kwargs):
        raise AssertionError("A fixed-rubric study runs no Research")

    def judge_row(self, item, row):
        return self._probe_row(item, row, self.rubric)

    def calibrate(self, records):
        """The v10 calibration, reports and summary of this arm's records (zero calls)."""
        return self._calibrate(records, self.rubric)


def study_manifest(template, budget, extension):
    """The learning-v10 manifest the study's ledger, solver adapter and verifier run under -- rebuilt by the frozen
    ``contracts.manifest`` from the source stage's inputs with the study's own budget -- plus the study binding.

    ``template`` holds the source's panel, families, model, runtime, parent Skill, seed and recovery policy.
    """
    base = manifest(template["panel"], train_families=template["train_families"],
                    selection_families=template["selection_families"], model=template["model"], budget=budget,
                    runtime=template["runtime"], parent_skill=template["parent_skill"], seed=template["seed"],
                    method=VERIFIER_METHOD, version=VERIFIER_VERSION, recovery_policy=template["recovery_policy"],
                    feedback_profile=VERIFIER_PROFILE, parent_verifier_policy=None)
    require("study" not in base, "The learning manifest already has a study field")
    return seal({**unsealed(base), "study": extension})


def bind_rows(ledger, value, items, rows, skill, rollout):
    """Every known row of a fresh train rollout bound to its sealed evaluation and intent: the request (this
    manifest, the Skill, the task, train role, this rollout) is re-derived, never looked up by the row's own claim."""
    require(len(items) == len(rows), "Items and rows must be given pairwise")
    pairs, unknown = [], 0
    for item, row in zip(items, rows):
        task = item["task"]
        request = {"manifest_hash": value["record_hash"], "candidate_hash": digest({"skill": skill}),
                   "task_hash": digest(task), "role": "train", "repeat": 0}
        if value["version"] in MULTIDOMAIN_VERSIONS:
            request["benchmark"] = value["benchmark"]
        request["rollout"] = rollout
        key = digest(request)
        saved = read_json(ledger.root / "evaluations" / (key + ".json"), sealed=True)
        require(item["role"] == "train" and value["authorized_tasks"].get(digest(task)) == "train"
                and saved["request"] == request
                and read_json(ledger.root / "evaluation_intents" / (key + ".json"), sealed=True) == seal(request),
                "A train row is not this rollout's sealed evaluation of its task")
        if row["score"] is None:
            require(saved["score"]["status"] == "unknown" and row["trajectory"] is None, "Unknown row mismatch")
            unknown += 1
            continue
        require(row["output"]["evidence_hash"] == saved["record_hash"]
                and row["output"]["output"] == saved["prediction"]["output"]
                and row["score"] == saved["score"]["score"] and saved["score"]["status"] in {"pass", "fail"},
                "A train row differs from its sealed evaluation")
        pairs.append((item, row))
    return pairs, unknown


def run_cells(cells, verifiers, pairs_by_token, workers):
    """Judge the scheduled (arm, evidence) cells: the first alone (the first real reply is the health barrier), the
    rest on ``workers`` threads in schedule order. The FIRST failure is recorded under a lock and published to every
    arm's verifier (their per-call abort checks then refuse new requests, retries and recoveries included) by the
    failing worker itself, before it re-raises; a queued cell checks that flag before it starts and never starts
    after a failure. Requests already in flight finish; nothing is retried. Returns {arm: {token: row record}}."""
    require(type(workers) is int and workers >= 1, "Invalid worker count")
    records = {arm: {} for arm in verifiers}
    lock = threading.Lock()
    state = {"failure": None}

    def abort(exc):
        reason = str(exc) if isinstance(exc, LearningPending) else type(exc).__name__
        with lock:
            if state["failure"] is None:
                state["failure"] = exc
            for verifier in verifiers.values():
                if not verifier.pending_reason:
                    verifier.pending_reason = reason

    def one(cell):
        with lock:
            if state["failure"] is not None:
                return None  # queued after a failure: never started
        arm, token = cell
        try:
            item, row = pairs_by_token[token]
            record = verifiers[arm].judge_row(item, row)
            require(record["evidence_hash"] == token and record["policy_hash"] == verifiers[arm].rubric["policy_hash"],
                    "A judged row does not belong to its cell")
        except BaseException as exc:
            abort(exc)
            raise
        with lock:
            records[arm][token] = record
        return record

    if cells:
        one(cells[0])  # a failure here has already been published and propagates as is
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(one, cell) for cell in cells[1:]]
            wait(futures)
    if state["failure"] is not None:
        raise state["failure"]
    return records
