"""V3 benchmark adapters: scalar development feedback and public-only traces.

These projections adapt task representation, not either optimization algorithm.
Spreadsheet reflection sees the public instruction/target and generated code,
not workbook bytes, reference cells, native stderr or hidden case-level feedback.
ALFWorld sees a fixed, explicitly abbreviated public interaction trajectory.
"""
from __future__ import annotations

import hashlib
import json

from skillopt.continual_eval.core import require
from skillopt.continual_eval.datasets import _asset_paths, file_hash

from .contracts import (
    BUDGET_VERSION,
    GENERALIZATION_VERSIONS,
    MULTIDOMAIN_VERSIONS,
    VERIFIER_METHOD,
    VERIFIER_VERSION,
)
from .execution_evidence import PROFILE as EVIDENCE_PROFILE
from .execution_evidence import sanitize
from .ledger import LearningPending

PROFILE = "benchmark-public-feedback-v1"
# V8: a failed TRAIN execution also shows what the checker expected, so the analyst
# can name the actual mistake instead of guessing it: KOR-Bench and SearchQA give the
# expected answer text, BigCodeBench the sanitized structural execution evidence of the
# v7 ablation (never hidden test text), SpreadsheetBench the expected cell values at the
# answer positions, ALFWorld nothing beyond its public trajectory. Selection rows and
# successful rows stay scalar. Both methods receive exactly the same projection.
LABELED_PROFILE = "benchmark-labeled-failure-feedback-v1"
# V10 (main method): the projection itself stays scalar and label-free on every row; the stage
# driver attaches the sealed verifier report (Rubric -> probe -> Research, calibrated against the
# host audit) to failed train rows after this projection. No benchmark label ever enters it.
VERIFIER_PROFILE = "rubric-research-verifier-feedback-v1"
EXPECTED_CHARS = 2000
ALF_FIRST_STEPS = 2
ALF_LAST_STEPS = 4
ALF_OBSERVATION_CHARS = 1500


def benchmark_for(manifest):
    return manifest["benchmark"] if manifest["version"] in MULTIDOMAIN_VERSIONS else "bigcodebench"


def validate_public(benchmark, public):
    fields = {
        "bigcodebench": {"prompt", "entry_point"},
        "searchqa": {"question", "context"},
        "korbench": {"rule", "question"},
        "spreadsheetbench": {"instruction", "answer_position"},
        "alfworld": {"initial_observation", "initial_observation_truncated"},
    }
    require(benchmark in fields and type(public) is dict and set(public) == fields[benchmark],
            "Unexpected benchmark public feedback fields")
    for key, value in public.items():
        if key == "context" and type(value) is list:
            require(all(type(item) is str for item in value), "Invalid public context")
        elif key == "initial_observation_truncated":
            require(type(value) is bool, "Invalid observation truncation marker")
        else:
            require(type(value) is str, "Public feedback text required")


def _alf_public(prediction):
    trace = prediction.get("trace")
    require(type(trace) is list and trace, "ALFWorld requires actual public interaction evidence")
    indices = sorted(set(range(min(ALF_FIRST_STEPS, len(trace))))
                     | set(range(max(0, len(trace) - ALF_LAST_STEPS), len(trace))))
    rows = []
    for index in indices:
        row = trace[index]
        require(type(row) is dict and type(row.get("observation")) is str
                and type(row.get("action")) is str, "Invalid ALFWorld public interaction")
        item = {"step": index, "observation": row["observation"][:ALF_OBSERVATION_CHARS],
                "observation_truncated": len(row["observation"]) > ALF_OBSERVATION_CHARS,
                "action": row["action"]}
        require(len(item["action"]) <= 1000, "ALFWorld action exceeds native limit")
        if "post_observation" in row:
            post = row["post_observation"]
            require(post is None or type(post) is str, "Invalid public post-observation")
            status = row.get("post_observation_status")
            require(status in {"complete", "truncated", "missing"}, "Invalid post-observation status")
            item.update(post_observation=post[:ALF_OBSERVATION_CHARS] if post is not None else None,
                        post_observation_status=status,
                        post_observation_projection_truncated=post is not None and len(post) > ALF_OBSERVATION_CHARS)
        rows.append(item)
    initial = trace[0]["observation"]
    public = {"initial_observation": initial[:12000], "initial_observation_truncated": len(initial) >= 12000}
    return public, json.dumps({"public_steps": rows, "episode_steps": len(trace),
                              "omitted_steps": len(trace) - len(rows)}, ensure_ascii=False, sort_keys=True)


def evidence_enabled(manifest):
    """The sanitized-evidence profile is valid only for a v7 BigCodeBench SkillOpt manifest."""
    if manifest.get("feedback_profile") != EVIDENCE_PROFILE:
        return False
    require(manifest.get("version") == BUDGET_VERSION and manifest.get("benchmark") == "bigcodebench"
            and manifest.get("method") == "skillopt",
            "Execution-evidence feedback is a v7 BigCodeBench SkillOpt ablation only")
    return True


def labeled_enabled(manifest):
    """V8 labeled failure feedback; the profile is valid for v8/v9 only (both methods, every domain)."""
    if manifest.get("feedback_profile") != LABELED_PROFILE:
        return False
    require(manifest.get("version") in GENERALIZATION_VERSIONS and manifest.get("version") != VERIFIER_VERSION,
            "Labeled failure feedback is learning v8/v9 only")
    return True


def verifier_enabled(manifest):
    """V10 verifier feedback; the profile is valid for the v10 rubric_research manifest only."""
    if manifest.get("feedback_profile") != VERIFIER_PROFILE:
        return False
    require(manifest.get("version") == VERIFIER_VERSION and manifest.get("method") == VERIFIER_METHOD,
            "Verifier feedback is the learning v10 rubric_research protocol only")
    return True


def expected_text(benchmark, private):
    """What the checker expected, as bounded text; None where no compact label exists."""
    if benchmark == "korbench":
        require(type(private.get("answer")) is str, "KOR-Bench label text required")
        value = private["answer"]
    elif benchmark == "searchqa":
        answers = private.get("answers")
        require(type(answers) is list and answers and all(type(a) is str for a in answers),
                "SearchQA label list required")
        value = " | ".join(answers)
    else:
        return None
    return value if len(value) <= EXPECTED_CHARS else value[:EXPECTED_CHARS] + " …[truncated]"


def project(manifest, public, prediction, score, private=None, role="train"):
    """Recomputable projection bound to saved execution; labels only on v8 failed train rows."""
    evidence = evidence_enabled(manifest)  # fail fast on an unauthorized profile tuple
    labeled = labeled_enabled(manifest)
    verifier_enabled(manifest)  # v10: scalar projection here; verifier reports are attached by the stage
    require(role in {"train", "selection"}, "Unknown learning role")
    if score["status"] == "unknown":
        raise LearningPending("unknown_is_not_failure_feedback")
    output = prediction["output"]
    if manifest["version"] in MULTIDOMAIN_VERSIONS:
        require(score["status"] in {"pass", "fail"}
                and type(score["score"]) in {int, float}
                and score["score"] == int(score["status"] == "pass"), "Inconsistent native hard feedback")
        benchmark = benchmark_for(manifest)
        require(manifest["feedback_profile"] in {PROFILE, EVIDENCE_PROFILE, LABELED_PROFILE, VERIFIER_PROFILE},
                "Unsupported public feedback profile")
        if benchmark == "spreadsheetbench":
            require(type(output) is dict and type(output.get("code")) is str, "Actual spreadsheet code required")
            public = {key: public[key] for key in ("instruction", "answer_position")}
            output = output["code"]
        elif benchmark == "alfworld":
            public, output = _alf_public(prediction)
        validate_public(benchmark, public)
        require(type(output) is str, "Textual public model output required")
    feedback = {"status": score["status"], "score": score["score"]}
    if evidence and score["status"] == "fail":
        # Host development diagnostic, recomputed from the saved execution only.
        feedback["execution_evidence"] = sanitize(output, (score.get("metrics") or {}).get("details"))
    if labeled and score["status"] == "fail" and role == "train":
        require(type(private) is dict, "Labeled feedback needs the task's private record")
        if benchmark_for(manifest) == "bigcodebench":
            feedback["execution_evidence"] = sanitize(output, (score.get("metrics") or {}).get("details"))
        else:
            expected = expected_text(benchmark_for(manifest), private)
            if expected is not None:
                feedback["expected"] = expected
    return {"Inputs": public, "Generated Outputs": output, "Feedback": feedback}


def task_description(benchmark, public):
    validate_public(benchmark, public)
    return public["prompt"] if benchmark == "bigcodebench" else json.dumps(public, ensure_ascii=False, sort_keys=True)


def verify_task_assets(manifest, task):
    """Recheck natural file-backed tasks immediately before execution or replay."""
    if manifest["version"] not in MULTIDOMAIN_VERSIONS or manifest["model"]["provider"] == "fixture":
        return
    for name in _asset_paths(benchmark_for(manifest), task):
        expected = manifest["asset_identity"].get(name)
        require(expected is not None and expected["status"] == "ready"
                and file_hash(name) == expected["sha256"], "Frozen learning asset changed")


def artifacts(ledger):
    result = ledger.artifacts()
    if ledger.manifest["version"] in MULTIDOMAIN_VERSIONS:
        result.update({str(path.relative_to(ledger.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in sorted((ledger.root / "host_only/scorer_artifacts").rglob("*"))
                       if path.is_file() and path.name != ".writer.lock"})
    if ledger.manifest["version"] == VERIFIER_VERSION:
        # V10: the verifier's sealed records (policy, probes, reviews, executions, reports), its retrieved
        # document bytes and the host-only calibration are governed evidence of the stage, like
        # receipts and proposals: every file under these two trees.
        result.update({str(path.relative_to(ledger.root)): hashlib.sha256(path.read_bytes()).hexdigest()
                       for folder in ("verifier", "host_only/verifier")
                       for path in sorted((ledger.root / folder).rglob("*")) if path.is_file()})
    return result
