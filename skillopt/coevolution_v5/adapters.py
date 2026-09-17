"""V5 domain adapters: immutable native oracles and evidence, never model verdicts.

The Coding delivery grammar deliberately permits a module to end at the next
exact FILE header or EOF.  This is declared before execution, not a repair of
an evaluated response.  Source bytes and the frozen V3 OS sandbox are unchanged.
QA exact-match/F1 remain the original SearchQA metrics. Citation matching only
establishes provenance; it is never entailment or approval evidence.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import replace
from typing import Mapping

from skillopt.coevolution_v3 import executor
from skillopt.coevolution_v3.tasks import _schema_valid
from skillopt.coevolution_v4.tasks import validate_input as validate_v4_input
from skillopt.envs.searchqa.evaluator import evaluate as score_qa
from skillopt.validator_pilot.api import digest

VERSION = "coevolution-v5-domain-adapters-v1"
TARGET_TOKENS = 8500
MAX_PROBES = 4
_HEADER = re.compile(r"<<<FILE ([A-Za-z][A-Za-z0-9_]*\.py)>>>(?:\r?\n|$)")


def parse_delivery(task: executor.RepoTask, raw: str) -> dict[str, str]:
    """Merge exact module bytes, accepting explicit or implicit module endings."""
    if not isinstance(raw, str) or len(raw) > executor.MAX_ARTIFACT_CHARS + 20000:
        raise ValueError("delivery must be a bounded string")
    patches, current, chunks = {}, None, []

    def close():
        nonlocal current, chunks
        if current is not None:
            source = "".join(chunks)
            if not source.strip():
                raise ValueError("each module must contain source")
            patches[current] = source
        current, chunks = None, []

    for line in raw.splitlines(keepends=True):
        header = _HEADER.fullmatch(line)
        if header:
            close()
            path = header.group(1)
            if path not in task.editable_paths:
                raise ValueError("delivery changes an undeclared or protected path")
            if path in patches:
                raise ValueError("duplicate delivered path")
            current = path
        elif line.rstrip("\r\n") == "<<<END FILE>>>":
            if current is None:
                raise ValueError("unexpected END FILE delimiter")
            close()
        elif line.startswith("<<<") or line.lstrip().startswith("```"):
            raise ValueError("invalid delimiter or markdown fence")
        elif current is None:
            if line.strip():
                raise ValueError("unexpected commentary outside file sections")
        else:
            chunks.append(line)
    close()
    if not patches:
        raise ValueError("delivery requires FILE sections")
    files = {**task.files, **patches}
    _validate_files(task, files)
    return files


def _validate_files(task, files):
    if not isinstance(files, Mapping) or not set(task.editable_paths) <= set(task.files):
        raise ValueError("invalid repository or artifact")
    if any(files.get(path) != source for path, source in task.files.items() if path not in task.editable_paths):
        raise ValueError("artifact changes protected paths")
    executor.validate_files(task, files)


def _phase(task_split, phase):
    """A caller cannot relabel a final/calibration artifact as development."""
    if not isinstance(phase, str):
        raise ValueError("phase must be explicit")
    groups = {
        "development": {"dev", "development", "train"},
        "gate": {"gate", "validation", "val"},
        "promotion": {"promotion", "calibration"},
        "audit": {"audit", "shadow"},
        "final": {"final", "test", "holdout", "evaluation", "eval"},
    }
    normalized = "development" if re.fullmatch(r"learn\d+", phase) else (
        "gate" if re.fullmatch(r"gate\d+", phase) else phase
    )
    if normalized == "calibration":
        normalized = "promotion"
    split = str(task_split).lower()
    if re.fullmatch(r"learn\d+", split):
        split = "development"
    if normalized not in groups or split not in groups[normalized]:
        raise ValueError("task split and evaluation phase disagree")
    return "development" if normalized == "gate" else normalized


def _assess(check, task_id, domain, phase, artifact, rubric, status, kind, *, verified=False, eligible=False, **details):
    from skillopt.coevolution_v5.core import make_assessment

    return make_assessment(
        check_id=check["id"], task_id=task_id, domain=domain, phase=phase,
        artifact_hash=digest(artifact), rubric_hash=rubric.get("rubric_hash", digest(rubric)),
        status=status, evidence_kind=kind, verified=verified, gate_eligible=eligible, details=details,
    )


def _checks(rubric):
    from skillopt.coevolution_v5.core import validate_rubric

    return validate_rubric(rubric)["checks"]


def _bind_phase(rows, task_split, requested_phase):
    """Bind original split to the seal, not just the canonical phase label."""
    from skillopt.coevolution_v5.core import make_assessment

    return [make_assessment(**{key: value for key, value in row.items() if key not in {"receipt_hash", "version", "details"}},
                            details={**row["details"], "task_split": task_split, "requested_phase": requested_phase})
            for row in rows]


def _available_evaluation(task, files, public_only):
    _validate_files(task, files)
    return executor.evaluate(task, {"files": {path: files[path] for path in task.editable_paths}}, public_only=public_only)


def _public_feedback(task, evaluation):
    cases = {case["label"]: case for case in task.public_cases}
    return {
        "error_category": evaluation.get("error_category"),
        "delivery_error": evaluation.get("delivery_error"),
        "execution_ok": evaluation.get("execution_ok"),
        "public_pass": evaluation.get("public_pass"),
        "observations": [{**deepcopy(row), "expected": cases[row["label"]]["expected"],
                          "expected_exception": cases[row["label"]]["exception"]}
                         for row in evaluation.get("public_observations", [])],
    }


def _delivery_evaluation(task, raw, ok):
    if ok is not True:
        return {"files": None, "hard": None, "execution_ok": False,
                "error_category": "transport_unavailable", "public_observations": []}
    try:
        files = parse_delivery(task, raw)
    except (ValueError, TypeError, SyntaxError, RecursionError) as exc:
        return {"files": None, "hard": None, "execution_ok": False,
                "error_category": "delivery", "delivery_error": str(exc)[:200], "public_observations": []}
    return _available_evaluation(task, files, public_only=True)


class CodingAdapter:
    domain = "coding"

    def __init__(self, task: executor.RepoTask):
        if not isinstance(task, executor.RepoTask):
            raise TypeError("CodingAdapter requires a RepoTask")
        self.task = task

    def public_task(self):
        return self.task.public_task()

    def _input_valid(self, value):
        if self.task.id.startswith("repo-v4-"):
            return validate_v4_input(self.task, value)
        try:
            return isinstance(value, dict) and len(json.dumps(value, allow_nan=False)) <= 6000 and _schema_valid(
                value, self.task.input_domain
            )
        except (ValueError, TypeError, RecursionError, OverflowError):
            return False

    def evaluate(self, files, rubric, *, phase, extra_inputs=None, reference_reviewed=True, public_only=None):
        normalized = _phase(self.task.split, phase)
        checks = _checks(rubric)
        if type(reference_reviewed) is not bool:
            raise ValueError("reference_reviewed must be an explicit boolean")
        eligible = normalized in {"development", "promotion"}
        if public_only is not None and type(public_only) is not bool:
            raise ValueError("public_only must be an explicit boolean or None")
        gate = self.task.split in {"gate", "validation", "val"}
        public_only = gate or (normalized == "promotion" if public_only is None else public_only)
        native, reference, artifact_error = None, None, None
        if files is not None:
            try:
                _validate_files(self.task, files)
            except (ValueError, TypeError, SyntaxError, RecursionError) as exc:
                artifact_error = str(exc)[:200]
        else:
            artifact_error = "no executable artifact; delivery or transport unavailable"
        relevant = any(self.domain in check["domains"] and check["id"] in {"coding_contract", "coding_probe"} for check in checks)
        if reference_reviewed and artifact_error is None and relevant:
            native = _available_evaluation(self.task, files, public_only)
            try:
                reference = _available_evaluation(self.task, self.task.reference_files, public_only)
            except (ValueError, TypeError, SyntaxError, RecursionError):
                reference = None
        rows = []
        for check in checks:
            common = (check, self.task.id, self.domain, normalized, files, rubric)
            if self.domain not in check["domains"]:
                rows.append(_assess(*common, "not_applicable", "execution", reason="outside_check_domain"))
                continue
            if check["id"] not in {"coding_contract", "coding_probe"}:
                rows.append(_assess(*common, "unknown", "execution", reason="unsupported_check_executor"))
                continue
            if artifact_error:
                rows.append(_assess(*common, "unknown", "execution", reason="delivery", message=artifact_error))
                continue
            if not reference_reviewed or not reference or reference.get("hard") is not True:
                rows.append(_assess(*common, "unknown", "execution", reason="reference_dispute_or_unavailable",
                                    reference_reviewed=reference_reviewed))
                continue
            if not native or native.get("execution_ok") is not True:
                rows.append(_assess(*common, "unknown", "execution", reason="infrastructure_or_resource_failure"))
                continue
            if not native.get("total_tests"):
                rows.append(_assess(*common, "unknown", "execution", reason="no_fixed_contract_fixtures"))
                continue
            if check["id"] == "coding_contract":
                facts = _public_feedback(self.task, native)
                facts["private_diagnostics"] = deepcopy(native.get("private_diagnostics", []))
                rows.append(_assess(
                    *common, "pass" if native["hard"] is True else "fail", "execution", verified=True,
                    eligible=eligible, native_score=float(native["hard"]),
                    passed_tests=native.get("passed_tests"), total_tests=native.get("total_tests"),
                    case_results=native.get("case_results", []), facts=facts, public_only=public_only,
                    limitation="finite fixture evidence, not semantic completeness",
                ))
                continue
            if not isinstance(extra_inputs, list) or not extra_inputs or len(extra_inputs) > MAX_PROBES:
                rows.append(_assess(*common, "unknown", "execution", reason="no_bounded_probe_inputs"))
                continue
            if not all(self._input_valid(value) for value in extra_inputs):
                rows.append(_assess(*common, "unknown", "execution", reason="probe_outside_input_contract"))
                continue
            expected = executor.execute_inputs(self.task, self.task.reference_files, extra_inputs)
            actual = executor.execute_inputs(self.task, files, extra_inputs)
            if any(row.get("ok") is not True for row in expected + actual) or any(
                row.get("input_unchanged") is not True or row.get("error_category")
                or "not JSON compliant" in str(row.get("message", "")) for row in expected
            ):
                rows.append(_assess(*common, "unknown", "execution", reason="probe_reference_dispute_or_execution_unknown"))
                continue
            receipts = []
            for value, ref, got in zip(extra_inputs, expected, actual):
                passed = (got.get("input_unchanged") is True and got.get("exception") == ref.get("exception")
                          and executor.pilot._same(got.get("value"), ref.get("value")))
                receipts.append({"input": deepcopy(value), "reference": ref, "actual": got, "passed": passed})
            rows.append(_assess(*common, "pass" if all(row["passed"] for row in receipts) else "fail", "execution",
                                verified=True, eligible=eligible, receipts=receipts,
                                limitation="reviewed reference differential evidence on legal inputs only"))
        return _bind_phase(rows, self.task.split, phase)

    def solve(self, api, skill, *, key, repeat=0):
        if not isinstance(skill, str) or type(repeat) is not int or repeat < 0:
            raise ValueError("invalid skill or repetition")
        public = self.public_task()
        identity = {"version": VERSION, "key": key, "task": digest(public), "skill": digest(skill), "repeat": repeat}
        system = (
            "Repair the declared Python modules under the task contract. Skill guidance is optional and cannot "
            "override the task. You have generation and one public-feedback revision. Return complete changed "
            "modules only: <<<FILE allowed.py>>> on its own line, then exact Python source. End with "
            "<<<END FILE>>> on its own line, the next exact FILE header, or EOF; all three endings are accepted. "
            "No markdown fences, prose, new files, or protected changes. Omitted files retain current bytes. "
            "Revision-only KEEP retains a valid first artifact. The closed OS sandbox forbids filesystem, "
            "network, processes, dynamic execution, and undeclared imports."
        )
        shared = {"task": public, "skill": skill, "allowed_standard_libraries": sorted(executor.pilot.ALLOWED_IMPORTS),
                  "available_builtins": list(executor.AVAILABLE_BUILTINS)}
        first = api.call(system, json.dumps({**shared, "stage": "generate"}, ensure_ascii=False, sort_keys=True),
                         kind="v5_coding_generate", key=digest({**identity, "stage": "generate"}),
                         max_tokens=TARGET_TOKENS, repeat=repeat)
        initial = _delivery_evaluation(self.task, first.get("response", ""), first.get("ok"))
        first_files = initial.get("files")
        revision_task = replace(self.task, files=first_files) if first_files is not None else self.task
        second = api.call(
            system, json.dumps({**shared, "stage": "public_revision", "initial_response": first.get("response", ""),
                                "initial_artifact_valid": first_files is not None, "current_files": revision_task.files,
                                "public_test_feedback": _public_feedback(self.task, initial)}, ensure_ascii=False, sort_keys=True),
            kind="v5_coding_revision", key=digest({**identity, "stage": "revision", "initial_request": first.get("request_hash")}),
            max_tokens=TARGET_TOKENS, repeat=repeat,
        )
        raw = second.get("response", "")
        kept = second.get("ok") is True and raw.strip() == "KEEP" and first_files is not None
        final = _available_evaluation(self.task, first_files, True) if kept else _delivery_evaluation(
            revision_task, raw, second.get("ok")
        )
        files = final.get("files")
        return {"version": VERSION, "id": self.task.id, "domain": self.domain, "repeat": repeat,
                "skill_hash": digest(skill), "public_task_hash": digest(public), "files": files,
                "artifact_hash": digest(files), "initial_response": first.get("response", ""), "response": raw,
                "revision_response": raw, "initial_evaluation": initial, "evaluation": final,
                "format_ok": files is not None, "target_ok": second.get("ok") is True,
                "delivery_status": "valid" if files is not None else final.get("error_category", "unknown"),
                "revision_kept": kept, "request_hashes": [first.get("request_hash"), second.get("request_hash")],
                "solver_calls": 2}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate answer JSON key")
        result[key] = value
    return result


def parse_answer(raw):
    if not isinstance(raw, str) or len(raw) > 60000:
        raise ValueError("answer must be bounded JSON text")
    answer = json.loads(raw, object_pairs_hook=_unique_object,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
    return _validate_answer(answer)


def _validate_answer(answer):
    if not isinstance(answer, dict) or not {"answer"} <= set(answer) <= {"answer", "citations"}:
        raise ValueError("answer must have answer and optional citations fields")
    if not isinstance(answer["answer"], str) or len(answer["answer"]) > 12000:
        raise ValueError("answer must be bounded text")
    citations = answer.get("citations", [])
    if not isinstance(citations, list) or len(citations) > 8 or any(
        not isinstance(item, dict) or set(item) != {"context_id", "quote"}
        or type(item["context_id"]) is not int or not isinstance(item["quote"], str)
        or not 1 <= len(item["quote"]) <= 4000 for item in citations
    ):
        raise ValueError("invalid bounded citation schema")
    return {"answer": answer["answer"], "citations": deepcopy(citations)}


class QAAdapter:
    domain = "qa"

    def __init__(self, task):
        required = {"id", "cluster_id", "question", "contexts", "answers", "split"}
        if not isinstance(task, dict) or not required <= set(task):
            raise ValueError("QA task is missing required fields")
        if any(not isinstance(task[field], str) or not task[field] for field in ("id", "cluster_id", "question", "split")):
            raise ValueError("QA identity, question, and split must be nonempty strings")
        if not isinstance(task["contexts"], list) or any(not isinstance(v, str) for v in task["contexts"]):
            raise ValueError("QA contexts must be a list of strings")
        if not isinstance(task["answers"], list) or not task["answers"] or any(
            not isinstance(v, str) or not v.strip() for v in task["answers"]
        ):
            raise ValueError("QA native oracle requires nonempty answer strings")
        self.task = deepcopy(task)

    def public_task(self):
        return {"id": self.task["id"], "question": self.task["question"],
                "contexts": [{"context_id": i, "text": text} for i, text in enumerate(self.task["contexts"])]}

    def _citations(self, answer):
        rows = []
        for citation in answer["citations"]:
            index = citation["context_id"]
            matched = 0 <= index < len(self.task["contexts"]) and citation["quote"] in self.task["contexts"][index]
            rows.append({**citation, "exact_match": matched, "entailment": "unknown"})
        return rows

    def evaluate(self, answer, rubric, *, phase, extra_inputs=None, reference_reviewed=True):
        normalized = _phase(self.task["split"], phase)
        checks = _checks(rubric)
        if type(reference_reviewed) is not bool:
            raise ValueError("reference_reviewed must be an explicit boolean")
        original = deepcopy(answer)
        try:
            answer = _validate_answer({"answer": answer} if isinstance(answer, str) else answer)
            invalid = None
        except (ValueError, TypeError) as exc:
            invalid = str(exc)[:200]
        rows = []
        for check in checks:
            common = (check, self.task["id"], self.domain, normalized, original, rubric)
            if self.domain not in check["domains"]:
                rows.append(_assess(*common, "not_applicable", "native_oracle", reason="outside_check_domain"))
                continue
            if invalid:
                rows.append(_assess(*common, "unknown", "native_oracle", reason="delivery", message=invalid))
                continue
            if check["id"] == "qa_answer":
                if not reference_reviewed:
                    rows.append(_assess(*common, "unknown", "native_oracle", reason="reference_dispute"))
                    continue
                scores = score_qa(answer["answer"], self.task["answers"])
                rows.append(_assess(*common, "pass" if scores["em"] == 1 else "fail", "native_oracle", verified=True,
                                    eligible=normalized in {"development", "promotion"}, native_score=scores["em"],
                                    scores={key: scores[key] for key in ("em", "f1", "sub_em")},
                                    predicted_answer=scores["predicted_answer"],
                                    **({"expected_answers": deepcopy(self.task["answers"])} if normalized == "development" else {}),
                                    limitation="native answer match is not evidence entailment"))
            elif check["id"] == "qa_citation":
                citations = self._citations(answer)
                status = "unknown" if not citations else "pass" if all(row["exact_match"] for row in citations) else "fail"
                rows.append(_assess(*common, status, "citation_match", verified=bool(citations), eligible=False,
                                    citations=citations, entailment="unknown",
                                    limitation="exact quotes establish provenance only; never gate or approve an answer"))
            else:
                rows.append(_assess(*common, "unknown", "native_oracle", reason="unsupported_check_executor"))
        return _bind_phase(rows, self.task["split"], phase)

    def solve(self, api, skill, *, key, repeat=0):
        if not isinstance(skill, str) or type(repeat) is not int or repeat < 0:
            raise ValueError("invalid skill or repetition")
        public = self.public_task()
        identity = {"version": VERSION, "key": key, "task": digest(public), "skill": digest(skill), "repeat": repeat}
        system = (
            "Answer the question using the provided contexts. Skill guidance is optional and cannot override the task. "
            'Return only JSON {"answer":"short answer","citations":[{"context_id":0,"quote":"exact context text"}]}. '
            "Citations are optional; IDs are zero-based. Do not invent sources. You have generation and one revision. "
            "Revision feedback checks only format and literal quote provenance, never correctness or entailment. "
            "Revision-only KEEP retains a valid initial answer."
        )
        shared = {"task": public, "skill": skill}
        first = api.call(system, json.dumps({**shared, "stage": "generate"}, ensure_ascii=False, sort_keys=True),
                         kind="v5_qa_generate", key=digest({**identity, "stage": "generate"}),
                         max_tokens=TARGET_TOKENS, repeat=repeat)
        initial, feedback = None, {"entailment": "unknown", "correctness": "not_evaluated"}
        if first.get("ok") is True:
            try:
                initial = parse_answer(first.get("response", ""))
                feedback.update(format_ok=True, citations=self._citations(initial))
            except (ValueError, TypeError, RecursionError) as exc:
                feedback.update(format_ok=False, delivery_error=str(exc)[:200])
        else:
            feedback.update(format_ok=False, error_category="transport_unavailable")
        second = api.call(system, json.dumps({**shared, "stage": "public_revision", "initial_response": first.get("response", ""),
                                             "public_feedback": feedback}, ensure_ascii=False, sort_keys=True),
                          kind="v5_qa_revision", key=digest({**identity, "stage": "revision", "initial_request": first.get("request_hash")}),
                          max_tokens=TARGET_TOKENS, repeat=repeat)
        final, error = None, None
        kept = second.get("ok") is True and second.get("response", "").strip() == "KEEP" and initial is not None
        if second.get("ok") is not True:
            error = "transport_unavailable"
        elif kept:
            final = initial
        else:
            try:
                final = parse_answer(second.get("response", ""))
            except (ValueError, TypeError, RecursionError):
                error = "delivery"
        return {"version": VERSION, "id": self.task["id"], "domain": self.domain, "repeat": repeat,
                "skill_hash": digest(skill), "public_task_hash": digest(public), "answer": final,
                "artifact_hash": digest(final), "initial_response": first.get("response", ""),
                "response": second.get("response", ""), "revision_response": second.get("response", ""),
                "initial_public_feedback": feedback, "format_ok": final is not None,
                "target_ok": second.get("ok") is True, "delivery_status": "valid" if final is not None else error,
                "revision_kept": kept, "request_hashes": [first.get("request_hash"), second.get("request_hash")],
                "solver_calls": 2}
