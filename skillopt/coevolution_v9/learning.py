"""Audited transport adapter for SkillOpt's native SearchQA patch pipeline.

The analyst, merger, ranking prompts and patch application are upstream code,
not a new prompt optimizer. This controlled configuration disables meta/slow
updates and skill-aware reflection. It uses stable aggregate input order, an
explicit 4,096-token transport cap, and terminal request caches. Acceptance is
deliberately outside this module: one candidate can feed both comparison gates.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.engine.trainer import _normalise_patches
from skillopt.envs.searchqa import evaluator, rollout
from skillopt.gradient import aggregate, reflect
from skillopt.optimizer import clip
from skillopt.optimizer.skill import apply_patch_with_report
from skillopt.prompts import load_prompt
from skillopt.validator_pilot.api import digest, write_immutable_json

VERSION = "v9-native-skillopt-controlled-patch-v1"
TOKEN_CAP = 4096
MAX_OPTIMIZER_CALLS = 16
MINIBATCH_SIZE = 8
EDIT_BUDGET = 4
_OPTIMIZER_LOCK = threading.RLock()
_REPO = Path(__file__).resolve().parents[2]


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def native_qa_messages(skill, item):
    """Byte-identical native single-turn SearchQA prompts, including truncation."""
    if not isinstance(skill, str) or not isinstance(item, dict):
        raise ValueError("Skill text and SearchQA item required")
    question, context = item.get("question"), item.get("context", "")
    if not isinstance(question, str) or not isinstance(context, str):
        raise ValueError("SearchQA question/context must be text")
    return rollout._build_system(skill), rollout._build_user(question, context)


def score_qa(raw, item):
    """Original answer extraction, SQuAD normalization, EM/F1 (not a new judge)."""
    answers = item.get("answers")
    if (not isinstance(raw, str) or not isinstance(answers, list)
            or not answers or any(not isinstance(answer, str) for answer in answers)):
        raise ValueError("Raw response and nonempty native gold-answer list required")
    result = evaluator.evaluate(raw, answers)
    return {**result, "hard": int(result["em"]), "soft": result["f1"]}


def _read(path):
    try:
        return verify(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Missing or unreadable immutable learning evidence") from exc


def _save(path, value):
    record = seal(value)
    write_immutable_json(path, record)
    return record


def _write_text(path, text):
    """Atomic, immutable text for the unmodified native trajectory reader."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError("Immutable native trajectory differs")
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".native-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_text(encoding="utf-8") != text:
                raise ValueError("Concurrent native trajectory differs") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _sources():
    paths = [
        "skillopt/coevolution_v9/learning.py", "skillopt/engine/trainer.py",
        "skillopt/envs/searchqa/rollout.py", "skillopt/envs/searchqa/evaluator.py",
        "skillopt/gradient/reflect.py", "skillopt/gradient/aggregate.py",
        "skillopt/optimizer/clip.py", "skillopt/optimizer/skill.py",
        "skillopt/optimizer/update_modes.py", "skillopt/optimizer/meta_skill.py",
        "skillopt/optimizer/skill_aware.py", "skillopt/utils/json_utils.py",
        "skillopt/coevolution_v5/core.py", "skillopt/validator_pilot/api.py",
        "skillopt/envs/searchqa/prompts/rollout_system.md",
        "skillopt/envs/searchqa/prompts/analyst_error.md",
        "skillopt/envs/searchqa/prompts/analyst_success.md",
        "skillopt/prompts/merge_failure.md", "skillopt/prompts/merge_success.md",
        "skillopt/prompts/merge_final.md", "skillopt/prompts/ranking.md",
    ]
    return {path: hashlib.sha256((_REPO / path).read_bytes()).hexdigest() for path in paths}


def _safe_output(root):
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise ValueError("Symlink learning output forbidden")
    if root.exists() and any(path.is_symlink() for path in root.rglob("*")):
        raise ValueError("Symlink learning artifact forbidden")


def _receipt(receipt, *, system, user):
    if not isinstance(receipt, dict) or type(receipt.get("ok")) is not bool:
        raise ValueError("Actual API receipt with explicit outcome required")
    request = receipt.get("request")
    if (not isinstance(request, dict) or digest(request) != receipt.get("request_hash")
            or request.get("system") != system or request.get("user") != user
            or not isinstance(receipt.get("response"), str)):
        raise ValueError("API request/response lineage differs from native prompts")
    return deepcopy(receipt)


def _inputs(skill, train_rows):
    if not isinstance(train_rows, list) or not 1 <= len(train_rows) <= 32:
        raise ValueError("Controlled history requires 1 to 32 training rows")
    rows, identifiers, requests = [], set(), set()
    for row in train_rows:
        item = deepcopy(row["item"])
        identifier = str(item.get("key", item.get("id", "")))
        if (not re.fullmatch(r"[A-Za-z0-9_.-]{1,180}", identifier)
                or identifier in {".", ".."} or identifier in identifiers):
            raise ValueError("Unique safe native training identifiers required")
        split = item.get("split")
        if not isinstance(split, str) or not re.fullmatch(r"train(?:_h\d+_r\d+)?", split):
            raise ValueError("Only source training rows can reach native reflection")
        system, user = native_qa_messages(skill, item)
        receipt = _receipt(row["receipt"], system=system, user=user)
        if receipt["request_hash"] in requests:
            raise ValueError("Training rows cannot duplicate an API request")
        # Validate gold even if transport failed; failed responses are not scored.
        score_qa("", item)
        rows.append({"id": identifier, "item": item, "receipt": receipt})
        identifiers.add(identifier)
        requests.add(receipt["request_hash"])
    return sorted(rows, key=lambda row: row["id"])


def _materialize(rows, skill, root):
    native, statuses = [], []
    for row in rows:
        item, receipt, identifier = row["item"], row["receipt"], row["id"]
        statuses.append({"id": identifier, "request_hash": receipt["request_hash"],
                         "status": "available" if receipt["ok"] else "unknown",
                         "error_type": receipt.get("error_type")})
        if not receipt["ok"]:
            # Native rollout likewise has no conversation before an API response.
            # Do not feed transport failures to the analyst as wrong reasoning.
            continue
        raw, scores = receipt["response"], score_qa(receipt["response"], item)
        result = {"id": identifier, "question": item["question"], **scores,
                  "response": raw, "agent_ok": True, "n_turns": 1, "fail_reason": ""}
        if scores["em"] < 1:
            result["fail_reason"] = (f"EM=0: predicted '{scores['predicted_answer']}' "
                                     f"but expected {item['answers']}")
        verification = (
            f"[EVALUATION RESULT]\nQuestion: {item['question']}\n"
            f"Predicted answer: {scores['predicted_answer']!r}\n"
            f"Gold answers: {item['answers']!r}\nExact Match: {scores['em']}\n"
            f"F1: {scores['f1']:.4f}"
        )
        directory = root / "predictions" / identifier
        write_immutable_json(directory / "conversation.json", [
            {"type": "message", "turn": 1, "content": raw},
            {"role": "system", "content": verification},
        ])
        system, user = native_qa_messages(skill, item)
        _write_text(directory / "target_system_prompt.txt", system)
        _write_text(directory / "target_user_prompt.txt", user)
        native.append(result)
    return native, statuses


class _Bridge:
    def __init__(self, api, root, round_key):
        self.api, self.root, self.round_key = api, root, round_key
        self.lock = threading.Lock()
        self.budget_exhausted = (root / "budget_exhausted.json").exists()
        self.fatal = False
        intents = {path.stem for path in (root / "intents").glob("*.json")}
        calls = {path.stem for path in (root / "calls").glob("*.json")}
        if intents != calls:
            raise ValueError("Unresolved native optimizer intent; no silent retry")
        if len(calls) > MAX_OPTIMIZER_CALLS:
            raise ValueError("Existing native optimizer budget exceeded")
        for token in calls:
            cached, saved_intent = _read(root / "calls" / f"{token}.json"), _read(root / "intents" / f"{token}.json")
            intent = cached["intent"]
            if digest(intent) != token or saved_intent != seal(intent) or intent["round_key"] != round_key:
                raise ValueError("Native optimizer evidence identity differs")
            _receipt(cached["receipt"], system=intent["system"], user=intent["user"])

    def chat(self, system, user, max_completion_tokens=16384, retries=3, stage="optimizer", **kwargs):
        if stage not in {"analyst", "merge", "ranking"} or kwargs:
            self.fatal = True
            raise RuntimeError("Undeclared native optimizer transport options")
        effective = min(max_completion_tokens, TOKEN_CAP)
        intent = {"round_key": self.round_key, "stage": stage, "system": system, "user": user,
                  "requested_max_tokens": max_completion_tokens, "effective_max_tokens": effective,
                  "native_retries_requested": retries, "transport_owns_bounded_http_retries": True}
        token = digest(intent)
        intent_path, call_path = self.root / "intents" / f"{token}.json", self.root / "calls" / f"{token}.json"
        # Serial optimizer admission gives deterministic bounded accounting even
        # though the unmodified reflection dispatcher owns a thread pool.
        with self.lock:
            if self.fatal:
                raise RuntimeError("Native optimizer has unclosed evidence; further requests forbidden")
            if call_path.exists():
                cached = _read(call_path)
                if cached["intent"] != intent or _read(intent_path) != seal(intent):
                    self.fatal = True
                    raise RuntimeError("Native optimizer cache identity mismatch")
                receipt = cached["receipt"]
            else:
                if intent_path.exists():
                    self.fatal = True
                    raise RuntimeError("Unresolved native optimizer intent; no silent retry")
                if self.budget_exhausted or len(list((self.root / "intents").glob("*.json"))) >= MAX_OPTIMIZER_CALLS:
                    self.budget_exhausted = True
                    _save(self.root / "budget_exhausted.json", {"round_key": self.round_key,
                          "max_optimizer_calls": MAX_OPTIMIZER_CALLS, "action": "keep_parent"})
                    raise RuntimeError("Frozen native optimizer call budget exhausted")
                _save(intent_path, intent)
                try:
                    receipt = self.api.call(system, user, "v9_native_" + stage,
                                            self.round_key + ":" + token,
                                            max_tokens=effective, repeat=0)
                    receipt = _receipt(receipt, system=system, user=user)
                    request = receipt["request"]
                    if (request.get("kind") != "v9_native_" + stage
                            or request.get("key") != self.round_key + ":" + token
                            or request.get("max_tokens") != effective or request.get("repeat") != 0):
                        raise ValueError("Optimizer receipt identity/budget differs")
                    _save(call_path, {"intent": intent, "receipt": receipt})
                except Exception:
                    self.fatal = True
                    raise RuntimeError("Native optimizer request lacks a closed receipt") from None
        if not receipt["ok"]:
            raise RuntimeError("Recorded terminal optimizer response")
        return receipt["response"], deepcopy(receipt.get("usage", {}))


@contextmanager
def _native_transport(bridge):
    with _OPTIMIZER_LOCK:
        modules = (reflect, aggregate, clip)
        originals = [module.chat_optimizer for module in modules]
        try:
            for module in modules:
                module.chat_optimizer = bridge.chat
            yield
        finally:
            for module, original in zip(modules, originals):
                module.chat_optimizer = original


def _files(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(root.rglob("*")) if path.is_file() and path != root / "result.json"}


def _stage(root, name, fn):
    path = root / (name + ".json")
    if path.exists():
        return _read(path)["value"]
    value = fn()
    _save(path, {"value": value})
    return value


def _normalise(raw):
    try:
        failure, success = _normalise_patches(deepcopy(raw), update_mode="patch")
        return {"failure": failure, "success": success, "error": None}
    except (ValueError, TypeError, AttributeError, OverflowError):
        return {"failure": [], "success": [], "error": "invalid_native_patch_metadata"}


def propose_candidate(api, skill, train_rows, output, *, round_key):
    """Produce one shared native candidate, without accepting or enlarging scope.

    ``train_rows`` minimally contains ``item`` (key/id, question, context,
    answers) and the actual cached ``receipt`` returned by ``api.call``. The
    caller must supply only its predeclared source-training split. Available
    trajectories are natively rescored; terminal responses remain unknown.
    """
    if not isinstance(round_key, str) or not round_key.strip() or len(round_key) > 200:
        raise ValueError("Bounded nonempty round identity required")
    root = Path(output).absolute()
    _safe_output(root)
    rows = _inputs(skill, train_rows)
    identity = seal({"version": VERSION, "parent_text": skill, "parent_hash": text_hash(skill),
                     "round_key": round_key, "training_inputs": rows, "sources": _sources(),
                     "configuration": {"minibatch_size": MINIBATCH_SIZE, "edit_budget": EDIT_BUDGET,
                         "merge_batch_size": 8, "analyst_workers": 1, "failure_only": False,
                         "meta_skill": False, "slow_update": False, "skill_aware": False,
                         "native_json_repair_preserved": True, "effective_token_cap": TOKEN_CAP,
                         "max_optimizer_calls": MAX_OPTIMIZER_CALLS,
                         "stable_aggregate_order": "content_digest", "gate": "external"}})
    result_path = root / "result.json"
    if result_path.exists():
        result = _read(result_path)
        if (_read(root / "identity.json") != identity or result["identity_hash"] != identity["record_hash"]
                or result["artifact_files"] != _files(root)):
            raise ValueError("Completed native learning evidence changed; no reconstruction")
        return result
    write_immutable_json(root / "identity.json", identity)
    bridge = _Bridge(api, root / "optimizer", round_key)
    native_rows, statuses = _materialize(rows, skill, root)
    with _native_transport(bridge):
        raw = _stage(root, "reflection", lambda: sorted(
            reflect.run_minibatch_reflect(
                native_rows, skill, str(root / "predictions"), str(root / "patches"),
                workers=1, failure_only=False, minibatch_size=MINIBATCH_SIZE,
                edit_budget=EDIT_BUDGET, random_seed=20260913,
                error_system=load_prompt("analyst_error", env="searchqa"),
                success_system=load_prompt("analyst_success", env="searchqa"),
                step_buffer_context="", meta_skill_context="", update_mode="patch",
                skill_aware_reflection=False), key=digest))
        normalised = _stage(root, "normalised", lambda: _normalise(raw))
        failure, success = normalised["failure"], normalised["success"]
        merged = _stage(root, "merged", lambda: aggregate.merge_patches(
            skill, failure, success, batch_size=8, workers=1, verbose=False, update_mode="patch"))
        selected = _stage(root, "selected", lambda: clip.rank_and_select(
            skill, merged, max_edits=EDIT_BUDGET, update_mode="patch"))
    if bridge.fatal:
        raise ValueError("Unclosed native optimizer evidence; preserved without new sampling")
    if bridge.budget_exhausted:
        candidate, application = skill, []
        status = "budget_exhausted_keep_parent"
    else:
        candidate, application = apply_patch_with_report(skill, selected)
        status = "candidate_ready" if candidate != skill else "no_change_keep_parent"
    calls = [_read(path) for path in sorted((root / "optimizer/calls").glob("*.json"))]
    if len(calls) != len(list((root / "optimizer/intents").glob("*.json"))):
        raise ValueError("Unresolved native optimizer intent; result cannot be completed")
    result = {"version": VERSION, "identity_hash": identity["record_hash"], "round_key": round_key,
              "parent_text": skill, "parent_hash": text_hash(skill), "candidate_text": candidate,
              "candidate_hash": text_hash(candidate), "status": status, "acceptance": "not_decided",
              "scope_expansion_authorized": False, "training_statuses": statuses,
              "available_training_rows": len(native_rows), "raw_patches": raw,
              "normalised_patches": {"failure": failure, "success": success},
              "normalisation_error": normalised["error"],
              "merged_patch": merged, "selected_patch": selected, "apply_report": application,
              "optimizer_calls": len(calls), "optimizer_request_hashes": [c["receipt"]["request_hash"] for c in calls],
              "optimizer_terminal_calls": sum(not c["receipt"]["ok"] for c in calls),
              "optimizer_receipt_hashes": [c["record_hash"] for c in calls], "artifact_files": _files(root)}
    return _save(result_path, result)
