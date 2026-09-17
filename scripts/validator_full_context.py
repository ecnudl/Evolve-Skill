"""Explicit supplemental engineering-bundle experiment; never alters its source run."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

VERSION = "full-development-engineering-bundle-v1"
MAX_USER_CHARS = 180000
MAX_CALLS = 240
VISIBLE_KEYS = ("prompt", "requirements", "description", "starter_code", "public_cases",
                "public_tests", "entry_point", "interface")
BOUNDARY = (
    " Deployment boundary for every proposed additive check: evaluate ONLY the supplied "
    "candidate native Python code against its visible task contract and visible public execution. "
    "Development labels and old judgments are diagnostic training evidence, not available "
    "inputs at deployment. Do not require development_failed_checks, old_judgment, private "
    "oracle, reference solutions, hidden tests, output-format instructions, rejudging, or "
    "infrastructure status in proposed checks. Grammar and infrastructure guards are handled "
    "by the orchestrator. Write semantic code checks with bounded applicability, not additions "
    "to the judge's response protocol. Do not mention DECISION= or EVIDENCE= in checks."
)


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def normalize_final(text: str) -> str:
    """Remove only empty lines and line-edge whitespace; never change nonempty content."""
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def validate_output(source: Path, output: Path) -> None:
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("supplemental output must be outside the immutable source run")
    if source.parent != output.parent:
        raise ValueError("supplemental output must be a new sibling of the source run")


def verify_source(source: Path, repo: Path = REPO) -> dict:
    """Preparation-safe provenance: no private manifest, results, or holdout reads."""
    protocol = read(source / "protocol.json")
    snapshot = read(source / "source_snapshot.json")
    expected = protocol["source_hashes"]
    if set(snapshot) != set(expected):
        raise ValueError("source snapshot manifest mismatch")
    required = {"skillopt/validator_scale_rubrics.py", "skillopt/validator_scale_experiment.py",
                "skillopt/validator_pilot/api.py", "skillopt/validator_pilot/analysis.py"}
    if not required.issubset(expected):
        raise ValueError("source manifest lacks frozen validator implementation")
    for name, checksum in expected.items():
        if digest(snapshot[name]) != checksum or digest((repo / name).read_text()) != checksum:
            raise ValueError("borrowed frozen implementation changed: " + name)
    return protocol


def full_cases(original: list[dict]) -> list[dict]:
    if len(original) != 12:
        raise ValueError("supplement requires exactly the original twelve selected dev cases")
    cases = []
    for case in original:
        if case.get("split") != "dev" or case.get("task", {}).get("split", "dev") != "dev":
            raise ValueError("repair input must be development only")
        cases.append({
            "id": case["id"], "split": "dev",
            "task": {key: deepcopy(case["task"][key]) for key in VISIBLE_KEYS if key in case["task"]},
            "candidate_code": case["candidate_code"],
            "public_evidence": deepcopy(case["public_test_log"]),
            "old_judgment": deepcopy(case["old_judgment"]),
            "development_hard": case["development_hard"],
            "development_failed_checks": deepcopy(case["development_failed_checks"]),
        })
    return cases


def full_messages(stage: str, cases: list[dict], prior: str | None = None,
                  research_pack: dict | None = None) -> tuple[str, str]:
    from skillopt.validator_scale_rubrics import repair_stage_messages

    system, encoded = repair_stage_messages(stage, cases, prior, research_pack)
    payload = json.loads(encoded)
    payload["development_cases"] = deepcopy(cases)
    payload["selection"] = {
        "case_ids": [case["id"] for case in cases], "selected_count": len(cases),
        "fixed_context_hash": digest(cases), "truncated": False,
        "development_context_chars": len(json.dumps(cases, ensure_ascii=False, sort_keys=True)),
        "max_context_chars": MAX_USER_CHARS, "source": "original selected full development evidence",
    }
    user = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(user) > MAX_USER_CHARS:
        raise ValueError("full request exceeds 180000 characters; refusing evidence clipping")
    return system + BOUNDARY, user


def bounded_call(api, messages: tuple[str, str], kind: str, key: str,
                 tokens: int, repeat: int = 0) -> dict:
    from skillopt.validator_scale_experiment import expected_call

    identifier, _ = expected_call(api, messages, kind, key, tokens, repeat)
    if not (api.root / "calls" / (identifier + ".json")).exists():
        if sum(1 for _ in (api.root / "calls").glob("*.json")) >= MAX_CALLS:
            raise RuntimeError("supplemental logical-call cap reached")
    return api.call(messages[0], messages[1], kind=kind, key=key,
                    max_tokens=tokens, repeat=repeat)


def prepare(source: Path, output: Path) -> dict:
    validate_output(source, output)
    source_protocol = verify_source(source)
    original = read(source / "development_revision_cases.json")
    cases = full_cases(original)
    documents = read(source / "research/sources/sources.json")
    pack = {"sources": [{"id": f"S{index + 1}", "url": item["requested_url"],
                          "text": item["text"], "ok": True}
                         for index, item in enumerate(documents) if item.get("ok")]}
    if len(pack["sources"]) != 3:
        raise ValueError("supplement requires the three already frozen successful official sources")
    full_messages("gap_analysis", cases)
    full_messages("research_synthesis", cases, research_pack=pack)
    from skillopt.validator_pilot.api import CachedAPI, write_immutable_json
    from skillopt.validator_scale_experiment import ledger
    from skillopt.validator_scale_rubrics import parse_additions

    protocol = {
        "version": VERSION, "source": str(source), "source_protocol_hash": digest(source_protocol),
        "source_development_cases_hash": digest(original), "full_context_hash": digest(cases),
        "script_hash": digest(Path(__file__).read_text()), "model": "glm-5.3",
        "bundle": ["unclipped selected development evidence",
                   "final check-list blank-line/line-edge normalization only",
                   "shared semantic-only deployment-boundary prompt"],
        "not_a_pure_context_ablation": True, "independent_final_proposals_per_arm": 1,
        "revision_calls_per_arm": 3, "revision_max_output_tokens": 4000,
        "temperature": 0, "reasoning_effort": "low", "judge_repeats": 2,
        "borrowed_holdout_artifacts": 56, "new_target_generations": 0,
        "new_candidate_executions": 0, "planned_max_calls": 230,
        "logical_call_cap": MAX_CALLS, "http_attempt_cap": MAX_CALLS * 3,
        "max_user_chars": MAX_USER_CHARS, "judge_parser": "unchanged strict frozen parser",
        "preparation_holdout_access": False, "prepare_concurrency": 1, "evaluate_concurrency": 4,
    }
    write_immutable_json(output / "protocol.json", protocol)
    write_immutable_json(output / "full_development_cases.json", cases)
    write_immutable_json(output / "research_pack.json", pack)
    write_immutable_json(output / "source_snapshot.json", {
        "script": Path(__file__).read_text(), "borrowed_source_hashes": source_protocol["source_hashes"]})
    revisions, rubrics = {}, {}
    with CachedAPI(REPO, output / "api", workers=4, stream=True, reasoning_effort="low") as api:
        for arm in ("feedback_full", "docs_full"):
            prior, stages = None, []
            final = None
            failure = None
            sequence = ("gap_analysis", "critique" if arm == "feedback_full" else "research_synthesis", "final")
            for stage in sequence:
                research = pack if arm == "docs_full" and stage != "gap_analysis" else None
                try:
                    messages = full_messages(stage, cases, prior, research)
                    request_payload = json.loads(messages[1])
                    if request_payload["development_cases"] != cases:
                        raise ValueError("full development evidence changed across stages")
                    call = bounded_call(api, messages, "repair_" + arm + "_" + stage,
                                        digest({"arm": arm, "stage": stage, "protocol": protocol}), 4000)
                    stages.append({"stage": stage, "request_hash": call["request_hash"],
                                   "ok": call["ok"], "user_chars": len(messages[1]),
                                   "full_context_hash": digest(request_payload["development_cases"])})
                    if not call["ok"]:
                        failure = "revision_api_unavailable"
                        break
                    prior = call["response"]
                    if stage == "final":
                        final = prior
                except (ValueError, RuntimeError) as error:
                    failure = type(error).__name__ + ": " + str(error)
                    break
            normalized = normalize_final(final) if final is not None else None
            parsed = parse_additions(normalized, pack if arm == "docs_full" else None) if normalized is not None else {
                "valid": False, "errors": [failure or "missing_final"], "checks": []}
            revision = {"arm": arm, "stages": stages, "raw_final": final,
                        "normalized_final": normalized, "whitespace_changed": final != normalized,
                        "normalization": "empty lines removed; surviving line edges stripped",
                        "parsed": parsed, "failure": failure,
                        "source_synthesis_is_unverified_proposal": True}
            write_immutable_json(output / "revisions" / (arm + ".json"), revision)
            revisions[arm] = revision
            if parsed["valid"]:
                rubrics[arm] = parsed["rubric"]
    write_immutable_json(output / "rubrics_frozen.json", rubrics)
    write_immutable_json(output / "rubrics_freeze_manifest.json", {
        "rubrics_hash": digest(rubrics), "protocol_hash": digest(protocol),
        "full_context_hash": digest(cases), "revisions_hash": digest(revisions),
        "source_holdout_read": False})
    result = {"status": "rubrics_frozen", "valid_arms": list(rubrics),
              "failed_arms": [arm for arm in revisions if arm not in rubrics],
              "source_holdout_read": False, "ledger": ledger(output)}
    write_immutable_json(output / "prepare_result.json", result)
    return result


def evaluation_barrier(source: Path, output: Path) -> dict:
    # Own immutable rubric freeze is checked BEFORE opening even source results.
    if not (output / "rubrics_freeze_manifest.json").exists():
        raise RuntimeError("own verified rubric freeze required before any holdout access")
    frozen = read(output / "rubrics_freeze_manifest.json")
    if (frozen["rubrics_hash"] != digest(read(output / "rubrics_frozen.json"))
            or frozen["protocol_hash"] != digest(read(output / "protocol.json"))
            or frozen["full_context_hash"] != digest(read(output / "full_development_cases.json"))
            or frozen.get("source_holdout_read") is not False):
        raise ValueError("own rubric freeze integrity mismatch")
    revisions = {path.stem: read(path) for path in sorted((output / "revisions").glob("*.json"))}
    if frozen["revisions_hash"] != digest(revisions):
        raise ValueError("frozen revision integrity mismatch")
    if not (source / "results.json").exists():
        raise RuntimeError("source run must be complete before holdout evaluation")
    result = read(source / "results.json")
    if result.get("status") != "complete":
        raise RuntimeError("source run is not complete")
    return result


def rehydrate(source: Path, baseline: list[dict], tasks: dict) -> list[dict]:
    """Recover exact judge-visible artifacts from frozen requests; execute no candidate."""
    from skillopt.validator_pilot.experiment import public_evidence
    from skillopt.validator_scale_experiment import read_record, visible
    from skillopt.validator_scale_rubrics import baseline_rubric, judge_messages, parse_judgment

    groups = defaultdict(list)
    for row in baseline:
        if row["split"] != "holdout" or row["target_repeat"] != 0:
            raise ValueError("borrowed evaluation must contain holdout solver-repeat-zero only")
        path = source / "judgments/static_v0" / f"{row['id']}__{row['skill_version']}__j{row['judge_repeat']}.json"
        if read_record(path) != row:
            raise ValueError("baseline aggregate differs from signed source row")
        groups[(row["id"], row["skill_version"], row["origin"])].append(row)
    if len(groups) != 56 or len(baseline) != 112:
        raise ValueError("expected exactly 56 borrowed artifacts and two baseline judge draws")
    artifacts = []
    for (_, _, _), pair in sorted(groups.items()):
        if {row["judge_repeat"] for row in pair} != {0, 1} or len(pair) != 2:
            raise ValueError("baseline judge draws not paired")
        first = pair[0]
        for key in ("hard", "target_ok", "execution_ok", "artifact_sha256", "request_hash", "guard_forced"):
            if pair[0][key] != pair[1][key]:
                raise ValueError("baseline artifact identity differs across judge draws")
        if not first["target_ok"]:
            if first["origin"] != "natural":
                raise ValueError("unavailable controlled target is unsupported")
            artifact = read_record(source / "targets" / f"{first['id']}__{first['skill_version']}__0.json")
            if digest(artifact) != first["artifact_sha256"]:
                raise ValueError("unavailable target identity mismatch")
            artifacts.append(artifact)
            continue
        calls = []
        for row in pair:
            call = read(source / "api/calls" / (row["judge_request_hash"] + ".json"))
            request = call["request"]
            if (digest(request) != row["judge_request_hash"] or call["request_hash"] != row["judge_request_hash"]
                    or request["kind"] != "judge_static_v0" or request["key"] != row["request_hash"]
                    or request["repeat"] != row["judge_repeat"] or call["ok"] != row["judge_ok"]
                    or digest(call["response"]) != row["raw_response_sha256"]):
                raise ValueError("baseline source call integrity mismatch")
            if call["ok"] and parse_judgment(call["response"]) != row["judgment"]:
                raise ValueError("baseline parse does not match frozen response")
            calls.append(call)
        request = calls[0]["request"]
        if any(call["request"]["user"] != request["user"] or call["request"]["system"] != request["system"] for call in calls):
            raise ValueError("baseline public evidence changed between draws")
        payload = json.loads(request["user"])
        public = payload["public_execution"]
        status = public["status"]
        evaluation = {"execution_ok": first["execution_ok"], "hard": first["hard"],
                      "public_observations": public.get("tests", []),
                      "error_category": None if status == "executed" else status,
                      "safety_error": public.get("error")}
        code = payload["candidate_code"]
        messages = judge_messages(visible(tasks[first["id"]]), code, public_evidence(evaluation), baseline_rubric())
        if messages != (request["system"], request["user"]):
            raise ValueError("borrowed artifact fails exact original public-input reconstruction")
        reason = first["guarded_judgment"]["feedback"][0] if first["guard_forced"] else None
        artifact = {key: first[key] for key in ("id", "skill_version", "origin", "family", "cluster_id",
                                               "split", "target_ok", "execution_ok", "hard", "request_hash")}
        artifact.update(arm=first["skill_version"], repeat=0, response=code, code=code,
                        evaluation=evaluation, guard_reason=reason,
                        source_artifact_sha256=first["artifact_sha256"],
                        rehydration="exact public request and source hard labels; no execution")
        artifacts.append(artifact)
    return artifacts


def evaluate_supplement(source: Path, output: Path) -> dict:
    validate_output(source, output)
    source_result = evaluation_barrier(source, output)
    source_protocol = verify_source(source)
    protocol = read(output / "protocol.json")
    if (protocol["source_protocol_hash"] != digest(source_protocol)
            or protocol["script_hash"] != digest(Path(__file__).read_text())
            or source_result["protocol_hash"] != digest(source_protocol)):
        raise ValueError("source or supplemental protocol identity changed")
    tasks = read(source / "tasks_private.json")
    if digest(tasks) != source_protocol["task_manifest_hash"]:
        raise ValueError("source private manifest integrity mismatch")
    baseline = read(source / "holdout_judgments.json")["static_v0"]
    artifacts = rehydrate(source, baseline, tasks)
    rubrics = read(output / "rubrics_frozen.json")
    from skillopt.validator_pilot.analysis import compare_judges
    from skillopt.validator_pilot.api import CachedAPI, write_immutable_json
    from skillopt.validator_scale_experiment import ScaleStudy, judge_instability, ledger, summarize_judges

    class BoundedStudy(ScaleStudy):
        def _call(self, api, messages, kind, key, tokens, repeat=0):
            return bounded_call(api, messages, kind, key, tokens, repeat)

    write_immutable_json(output / "borrowed_artifacts_private.json", artifacts)
    write_immutable_json(output / "borrowed_static_v0_judgments.json", baseline)
    study = BoundedStudy(REPO, output, workers=4)
    study.tasks = tasks
    with CachedAPI(REPO, output / "api", workers=4, stream=True, reasoning_effort="low") as api:
        rows = study._audit(api, artifacts, rubrics, "holdout")
    raw = {"static_v0": baseline, **rows}
    guarded = {arm: [{**row, "judgment": row["guarded_judgment"],
                      "judge_ok": row["raw_judge_ok"] or row["guard_forced"]} for row in values]
               for arm, values in raw.items()}
    result = {
        "status": "complete", "protocol_hash": digest(protocol), "source_results_hash": digest(source_result),
        "valid_revised_arms": list(rubrics), "borrowed_artifacts": len(artifacts),
        "new_target_generations": 0, "new_candidate_executions": 0,
        "holdout_raw": {arm: summarize_judges(values) for arm, values in raw.items()},
        "holdout_guarded": {arm: summarize_judges(values) for arm, values in guarded.items()},
        "paired_raw": {arm: compare_judges(baseline, values) for arm, values in rows.items()},
        "paired_guarded": {arm: compare_judges(guarded["static_v0"], guarded[arm]) for arm in rows},
        "judge_instability": {arm: judge_instability(values) for arm, values in raw.items()},
        "ledger": ledger(output),
        "limitations": [
            "Supplemental three-component engineering bundle, not pure full-context causal ablation.",
            "One final proposal per arm; two judge draws are not independent rubric-generation replicates.",
            "Same borrowed artifacts and baseline calls; this is not a fresh independent benchmark.",
            "Strict frozen judge parser for all arms; only final rubric whitespace was normalized.",
            "All source outputs remain unchanged; no skill evolution or cross-domain safety claim.",
        ],
    }
    write_immutable_json(output / "results.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    phase = parser.add_mutually_exclusive_group(required=True)
    phase.add_argument("--prepare-rubrics", action="store_true")
    phase.add_argument("--evaluate", action="store_true")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    function = prepare if args.prepare_rubrics else evaluate_supplement
    result = function(args.source.resolve(), args.output.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
