"""Read-only import of closed V15 development receipts (also used by V16).

This adapter does not replay models or candidate code. Checksums establish
internal consistency, not execution authenticity. ``LegacyImport.to_dict`` is a
HOST-ONLY bundle: its ``host_only`` field deliberately retains private audit
evidence. Only the explicitly selected public fields may feed a model view.
Historical records are diagnostic development data, never new formal evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skillopt.coevolution_v5.core import seal, verify
from skillopt.coevolution_v15.evidence import SOURCE_VERSION, project_development_feedback
from skillopt.validator_pilot.api import digest

VERSION = "skill-validation-legacy-v15-v1"
MAX_JSON_BYTES = 16 * 1024 * 1024
SOURCE_KINDS = {"model", "fixture", "mutant"}
_HASH = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class LegacyImport:
    """Host bundle, intentionally not a verifier/model input object."""

    identity: dict[str, Any]
    artifact: dict[str, Any] | None
    public_task: dict[str, Any]
    public_observations: list[dict[str, Any]]
    host_only: dict[str, Any]
    provenance: dict[str, Any]
    source_kind: str
    version: str = VERSION
    import_hash: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "import_hash", digest(self._payload()))

    def _payload(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in (
            "version", "source_kind", "identity", "artifact", "public_task",
            "public_observations", "host_only", "provenance")}

    def verify_integrity(self) -> None:
        """Detect mutation of nested structures after the closed-file import."""
        if digest(self._payload()) != self.import_hash:
            raise ValueError("Legacy import changed after receipt verification")

    def to_dict(self) -> dict[str, Any]:
        """Return a copy for HOST storage/import; includes private audit labels."""
        self.verify_integrity()
        return deepcopy({**self._payload(), "import_hash": self.import_hash})


def _safe_path(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("Legacy receipt path must stay within its run")
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Symlink legacy evidence is unsupported")
    return path


def _read(root: Path, relative: str, *, sealed: bool = True) -> dict:
    path = _safe_path(root, relative)
    if not path.is_file():
        raise ValueError(f"Closed legacy dependency missing: {relative}")
    if path.stat().st_size > MAX_JSON_BYTES:
        raise ValueError("Legacy JSON dependency exceeds byte bound")
    def unique_pairs(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Duplicate JSON keys are ambiguous legacy evidence")
            result[key] = item
        return result

    def finite_only(_):
        raise ValueError("Nonfinite JSON is unsupported legacy evidence")

    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs,
                           parse_constant=finite_only)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Malformed legacy JSON dependency") from error
    if type(value) is not dict:
        raise ValueError("Legacy receipt must be a JSON object")
    return verify(value) if sealed else value


def _hash(value: Any) -> str:
    if type(value) is not str or not _HASH.fullmatch(value):
        raise ValueError("A lowercase SHA256 receipt identifier is required")
    return value


def _source_closure(root: Path, solve: dict) -> dict:
    """Validate present manifests, without needing historical live source files."""
    missing: list[str] = []
    records = {}
    for name in ("protocol.json", "source_snapshot.json", "private_panel.json"):
        if _safe_path(root, name).is_file():
            records[name] = _read(root, name)
        else:
            missing.append(name)
    protocol = records.get("protocol.json", {})
    snapshot = records.get("source_snapshot.json", {})
    panel = records.get("private_panel.json", {})
    for target, hash_field in ((snapshot, "source_snapshot_hash"), (panel, "panel_hash")):
        if protocol and target and protocol.get(hash_field) != target["record_hash"]:
            raise ValueError(f"Legacy protocol {hash_field} mismatch")
    if protocol.get("task_preflight_hash") is not None:
        if not _safe_path(root, "task_preflight.json").is_file():
            missing.append("task_preflight.json")
        else:
            preflight = _read(root, "task_preflight.json")
            if preflight["record_hash"] != protocol["task_preflight_hash"]:
                raise ValueError("Legacy protocol task_preflight_hash mismatch")
    hashes = protocol.get("source_hashes", {})
    files = snapshot.get("files", {})
    if type(hashes) is not dict or type(files) is not dict:
        raise ValueError("Invalid historical source manifest")
    if protocol and not hashes:
        missing.append("protocol.source_hashes")
    for name, expected in hashes.items():
        _hash(expected)
        if name not in files:
            missing.append("source:" + name)
        elif type(files[name]) is not str or hashlib.sha256(files[name].encode()).hexdigest() != expected:
            raise ValueError("Historical source snapshot content/hash mismatch")
    if hashes and set(files) - set(hashes):
        raise ValueError("Historical source snapshot has unregistered files")
    for required in ("skillopt/coevolution_v15/runtime.py", "skillopt/coevolution_v15/evidence.py"):
        if required not in hashes:
            missing.append("source:" + required)
    task_found = False
    if panel:
        groups = panel.get("groups")
        if type(groups) is not dict or type(groups.get("train")) is not list:
            raise ValueError("Legacy panel is missing explicit development tasks")
        candidates = [task for batch in groups["train"] for task in batch] if all(
            type(batch) is list for batch in groups["train"]) else []
        matches = [task for task in candidates if type(task) is dict and task.get("id") == solve["task_id"]]
        if len(matches) != 1 or digest(matches[0]) != solve["identity"]["task_hash"]:
            raise ValueError("Legacy task does not match registered development manifest")
        task_found = True
    return {"source_closure_complete": not missing, "missing_dependencies": sorted(set(missing)),
            "source_file_count": len(hashes), "registered_development_task": task_found,
            "protocol_hash": protocol.get("record_hash"), "source_snapshot_hash": snapshot.get("record_hash"),
            "panel_hash": panel.get("record_hash")}


def _public_projection(task: dict, chosen: dict) -> tuple[dict, list[dict]]:
    """Select public contract/cases and actual chosen-artifact observations only.

    No host-evaluator computed expected output is added. Inputs and expectations
    come only from the original public request. Private or unregistered labels
    cause refusal, not a best-effort guess about whether a row was public.
    """
    allowed = ("domain", "prompt", "files", "editable_paths", "entry_module", "entry_function",
               "input_domain", "allowed_standard_libraries", "available_builtins")
    public = {k: deepcopy(task[k]) for k in allowed if k in task}
    contract = task.get("contract", {})
    if type(contract) is not dict:
        raise ValueError("Unsupported legacy public contract")
    public["contract"] = {k: deepcopy(contract[k]) for k in (
        "change_scope", "preserve_obligations", "supersedes_old_policy") if k in contract}
    cases = task.get("public_cases", [])
    if type(cases) is not list or any(type(case) is not dict for case in cases):
        raise ValueError("Unsupported legacy public cases")
    labels = {}
    projected = []
    for index, case in enumerate(cases):
        label = case.get("label", case.get("id"))
        if type(label) is not str or label in labels or case.get("public", True) is not True:
            raise ValueError("Legacy public cases require unique public identities")
        labels[label] = index
        projected.append({"case_id": f"public_case_{index}", **{k: deepcopy(case[k]) for k in (
            "input", "expected", "exception") if k in case}})
    public["public_cases"] = projected
    evaluation = chosen["public_evaluation"]
    if evaluation.get("private_diagnostics"):
        raise ValueError("Private diagnostics found in public execution")
    rows = evaluation.get("public_observations", [])
    if type(rows) is not list:
        raise ValueError("Unsupported public execution observations")
    case_results = evaluation.get("case_results", [])
    if type(case_results) is not list or any(type(row) is not dict for row in case_results):
        raise ValueError("Unsupported public execution case results")
    output = []
    seen = set()
    for row in rows:
        label = row.get("label")
        if label not in labels or label in seen:
            raise ValueError("Unregistered/duplicate public observation")
        seen.add(label)
        case = cases[labels[label]]
        if "input" in row and row["input"] != case.get("input"):
            raise ValueError("Public observation input differs from original public case")
        behavior = [result for result in case_results if result.get("id") == label + ":behavior"]
        if len(behavior) > 1:
            raise ValueError("Duplicate public behavior result")
        if behavior and (behavior[0].get("label") != label or behavior[0].get("public") is not True
                         or type(behavior[0].get("passed")) is not bool):
            raise ValueError("Behavior result must be a matched boolean public check")
        item = {"case_id": f"public_case_{labels[label]}",
                **{k: deepcopy(case[k]) for k in ("input", "expected") if k in case},
                **{k: deepcopy(row[k]) for k in ("actual", "passed", "exception", "input_unchanged",
                    "input_before_fingerprint", "input_after_fingerprint") if k in row},
                # V3 observation.passed combines return correctness AND input
                # preservation. Do not misattribute a preservation regression
                # to requested behavior, or infer from expected/actual values.
                "behavior_passed": behavior[0]["passed"] if behavior else None,
                "execution_id": chosen["execution_id"],
                "execution_receipt_hash": chosen["execution_receipt_hash"]}
        if "passed" in item and type(item["passed"]) is not bool:
            raise ValueError("Public observation pass state must be boolean")
        if "input_unchanged" in item and type(item["input_unchanged"]) is not bool:
            raise ValueError("Public input preservation state must be boolean")
        output.append(item)
    return public, output


def load_v15_development(run_root: str | Path, solve_id: str, *, source_kind: str) -> LegacyImport:
    """Load one immutable Coding development solve with all durable dependencies.

    ``source_kind`` is explicit provenance, not inferred from a filename. Known
    synthetic transports cannot be imported as natural outputs. Missing runtime
    evidence always fails closed; missing historical manifests stay diagnostic.
    This function never reads credentials, evaluates code, or changes files.
    """
    if source_kind not in SOURCE_KINDS:
        raise ValueError("Explicit model, fixture or mutant origin required")
    _hash(solve_id)
    root = Path(run_root).absolute()
    _safe_path(root, "runtime")
    solve = _read(root, f"runtime/solves/{solve_id}.json")
    if digest(solve.get("identity")) != solve_id:
        raise ValueError("Legacy solve filename/identity mismatch")
    if solve.get("domain") != "coding":
        raise ValueError("Initial legacy importer supports Coding only")
    requests = solve.get("request_hashes")
    executions_ids = solve.get("execution_ids")
    if type(requests) is not list or len(requests) != 2 or type(executions_ids) is not list or len(executions_ids) != 3:
        raise ValueError("V15 requires exactly two stages and three execution references")
    stages, api_receipts, executions = [], [], {}
    for index, identifier in enumerate(requests):
        _hash(identifier)
        name = ("generation", "revision")[index]
        stage = _read(root, f"runtime/stages/{identifier}.json")
        receipt = _read(root, f"api/calls/{identifier}.json", sealed=False)
        intent = _read(root, f"runtime/request_intents/{identifier}.json")
        expected = seal({"version": SOURCE_VERSION, "request_hash": identifier,
                         "identity_hash": digest(solve["identity"]), "stage": name})
        if intent != expected:
            raise ValueError("Legacy request intent mismatch")
        if source_kind == "model" and any(receipt.get("request", {}).get("service", {}).get(k)
                                                  for k in ("synthetic", "fake", "fixture")):
            raise ValueError("Synthetic transport cannot be declared model origin")
        stages.append(stage)
        api_receipts.append(receipt)
    for index, identifier in enumerate(executions_ids):
        _hash(identifier)
        artifact = stages[index]["delivery"]["artifact"] if index < 2 else solve["artifact"]
        expected = seal({"version": SOURCE_VERSION, "task_hash": solve["identity"]["task_hash"],
                         "artifact_hash": digest(artifact), "public_only": index < 2,
                         "identity_hash": digest(solve["identity"])})
        intent = _read(root, f"runtime/execution_intents/{identifier}.json")
        if intent != expected:
            raise ValueError("Legacy execution intent mismatch")
        executions[identifier] = _read(root, f"runtime/executions/{identifier}.json")
    # The old projection is a host-only integrity check; it includes private H.
    projection = project_development_feedback(solve, stages, api_receipts=api_receipts, executions=executions)
    closure = _source_closure(root, solve)
    chosen = stages[0 if solve["chosen_stage"] == "generation" else 1]
    task = json.loads(api_receipts[0]["request"]["user"])["task"]
    public_task, observations = _public_projection(task, chosen)
    artifact = solve["artifact"]
    if artifact is not None and (type(artifact) is not dict or any(
            type(k) is not str or type(v) is not str for k, v in artifact.items())):
        raise ValueError("Coding artifact must be the actual filename-to-source mapping")
    identity = {"task_id": solve["task_id"], "family_id": solve["cluster_id"],
        "project_id": "historical-authored-coding", "repeat": solve["identity"]["repeat"],
        "condition": "no_skill" if solve["skill_hash"] == hashlib.sha256(b"").hexdigest() else "unassigned",
        "skill_hash": solve["skill_hash"], "artifact_hash": digest(artifact), "solve_hash": solve["record_hash"],
        "task_hash": solve["identity"]["task_hash"]}
    provenance = {**closure, "integrity_checked": True, "execution_authenticated": False,
        "historical_only": True, "formal_eligible": False, "purpose": "development",
        "source_kind": source_kind, "source_version": SOURCE_VERSION,
        "source_bundle_hash": projection["provenance"]["source_bundle_hash"],
        "chosen_stage": solve["chosen_stage"], "api_calls": 0, "native_executions": 0,
        "limitation": "Internally consistent historical receipts, not independent authenticity or new efficacy evidence."}
    return LegacyImport(identity=identity, artifact=deepcopy(artifact), public_task=public_task,
        public_observations=observations, source_kind=source_kind, provenance=provenance,
        host_only={"solve": solve, "stages": stages, "api_receipts": api_receipts,
                   "executions": executions, "projection": projection})
