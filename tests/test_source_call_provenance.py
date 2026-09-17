"""Synthetic-only source/E call provenance checks; no Arrow or API access."""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from scripts import audit_source_call_provenance as audit


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def builders():
    def evaluate(response, answers):
        answer = response.removeprefix("<answer>").removesuffix("</answer>")
        correct = float(answer in answers)
        return {"em": correct, "f1": correct, "predicted_answer": answer}

    return lambda skill: "SYSTEM\n" + skill, lambda question, context: "USER\n" + question + "\n" + context, evaluate


def snapshots(root, arms):
    result = {}
    for arm in arms:
        text = f"fixed synthetic skill for {arm}"
        path = root / "skills" / f"{arm}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        result[arm] = {"snapshot": str(path.relative_to(root)), "sha256": audit._file_hash(path)}
    return result


def save_rows(root, split, arm, rows):
    path = root / "searchqa_rollouts" / split / arm / "results.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def make_calls(root, protocol, tasks, service, arms, split="holdout"):
    system, user, evaluate = builders()
    rows_by_arm = {}
    for arm in arms:
        skill = (root / protocol["arms"][arm]["snapshot"]).read_text(encoding="utf-8")
        rows = []
        for task in tasks:
            request = {"protocol": protocol["protocol_version"], "model": protocol["model"],
                       "system": system(skill), "user": user(task["question"], task["context"]),
                       "key": task["id"], "arm": arm, "split": split, "service": service,
                       "max_completion_tokens": protocol["requested_max_completion_tokens"]}
            identifier = audit._digest(request)
            response = "<answer>" + task["answers"][0] + "</answer>"
            usage = {"total_tokens": 7}
            cache = {"request_hash": identifier, "request": request, "ok": True, "response": response, "usage": usage}
            write_json(root / "calls" / (identifier + ".json"), cache)
            row = {"id": task["id"], "arm": arm, "split": split, "env": "searchqa", "question": task["question"],
                   "gold_answers": task["answers"], "question_sha256": hashlib.sha256(task["question"].strip().casefold().encode()).hexdigest(),
                   "skill_sha256": hashlib.sha256(skill.encode()).hexdigest(), "request_hash": identifier,
                   "agent_ok": True, "response": response, "usage": usage, "api_error": None,
                   "hard": 1.0, **evaluate(response, task["answers"])}
            rows.append(row)
        rows_by_arm[arm] = rows
        save_rows(root, split, arm, rows)
    return rows_by_arm


@pytest.fixture
def source_run(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    tasks = [{"id": f"item-{index}", "question": f"PRIVATE_QUESTION_{index}",
              "context": f"PRIVATE_CONTEXT_{index}", "answers": [f"PRIVATE_GOLD_{index}"]} for index in range(2)]
    fake_arrow = tmp_path / "synthetic.arrow"
    fake_arrow.write_bytes(b"not an actual Arrow file; must not be opened by materializer")
    manifest = {"settings": {"cache_path": str(fake_arrow), "cache_sha256": audit._file_hash(fake_arrow)},
                "splits": {"holdout": [{"id": task["id"]} for task in tasks]}}
    protocol = {"protocol_version": "synthetic-source", "arms": snapshots(root, ("base", "full", "extractive")),
                "manifest_hash": audit._digest(manifest), "code_hashes": {}, "model": "synthetic-model",
                "required_provider_host": "synthetic.invalid", "effective_max_tokens_cap": 8000,
                "requested_max_completion_tokens": 16384}
    service = {"host": "synthetic.invalid", "path": "/v1", "cap": 8000, "temperature": None}
    provider = {"service": service, "provider": {"provider_host": "synthetic.invalid", "model": "synthetic-model"}}
    write_json(root / "source_provider.json", provider)
    frozen = {"manifest_hash": audit._digest(manifest), "protocol_hash": audit._digest(protocol),
              "arms": protocol["arms"], "code_hashes": {}, "execution_mode": "real_target_api",
              "calibration_artifact_hashes": {"source_provider.json": audit._file_hash(root / "source_provider.json")}}
    for name, value in {"source_protocol.json": protocol, "source_manifest.json": manifest,
                        "frozen_source_protocol.json": frozen, "datasets/holdout.json": tasks,
                        "holdout_summary.json": {"split": "holdout", "execution_mode": "real_target_api",
                                                 "protocol_hash": audit._digest(protocol)}}.items():
        write_json(root / name, value)
    monkeypatch.setattr(audit, "_manifest_tasks", lambda manifest, split: copy.deepcopy(tasks))
    monkeypatch.setattr(audit, "_builders", builders)
    rows = make_calls(root, protocol, tasks, service, protocol["arms"])
    return {"repo": tmp_path, "root": root, "tasks": tasks, "protocol": protocol, "manifest": manifest,
            "service": service, "provider": provider, "rows": rows}


def run(fixture, root=None):
    return audit.audit_run(root or fixture["root"], "holdout", repo=fixture["repo"])


def first_cache(fixture, arm="full"):
    identifier = fixture["rows"][arm][0]["request_hash"]
    path = fixture["root"] / "calls" / (identifier + ".json")
    return path, read_json(path)


def test_source_audits_all_three_arms_with_reconstructed_requests(source_run):
    result = run(source_run)
    assert result["status"] == "complete"
    assert result["kind"] == "source"
    assert result["counts"]["arms_expected"] == 3
    assert result["counts"]["rows_expected"] == result["counts"]["rows_passed"] == 6
    assert result["counts"]["call_caches_checked"] == 6
    assert result["read_only"] and not result["server_authenticity_verified"]


@pytest.mark.parametrize("field", ["system", "user", "arm", "model", "max_completion_tokens", "service"])
def test_tampered_request_field_fails_even_with_self_consistent_hash(source_run, field):
    path, cache = first_cache(source_run)
    cache["request"][field] = {"host": "changed.invalid"} if field == "service" else 99 if field == "max_completion_tokens" else "PRIVATE_TAMPER"
    identifier = audit._digest(cache["request"])
    cache["request_hash"] = identifier
    write_json(path.parent / (identifier + ".json"), cache)
    source_run["rows"]["full"][0]["request_hash"] = identifier
    save_rows(source_run["root"], "holdout", "full", source_run["rows"]["full"])
    result = run(source_run)
    assert result["status"] == "failed"
    assert "REQUEST_" + field.upper() + "_MISMATCH" in result["error_counts"]
    assert "RECONSTRUCTED_REQUEST_HASH_MISMATCH" in result["error_counts"]


@pytest.mark.parametrize("field,code", [("response", "RESPONSE_MISMATCH"), ("usage", "USAGE_MISMATCH"),
                                        ("request_hash", "CACHE_REQUEST_HASH_MISMATCH")])
def test_cache_outcome_or_hash_tampering_is_rejected(source_run, field, code):
    path, cache = first_cache(source_run)
    cache[field] = {"total_tokens": 99} if field == "usage" else "PRIVATE_TAMPER"
    write_json(path, cache)
    result = run(source_run)
    assert result["status"] == "failed"
    assert code in result["error_counts"]


@pytest.mark.parametrize("field,value,code", [("arm", "base", "ROW_ARM_MISMATCH"),
                                             ("request_hash", "bad-hash", "INVALID_ROW_REQUEST_HASH"),
                                             ("hard", 0.0, "SCORE_HARD_MISMATCH")])
def test_row_provenance_or_score_tampering_is_rejected(source_run, field, value, code):
    source_run["rows"]["full"][0][field] = value
    save_rows(source_run["root"], "holdout", "full", source_run["rows"]["full"])
    result = run(source_run)
    assert result["status"] == "failed"
    assert code in result["error_counts"]


def test_missing_call_cache_is_incomplete_not_repaired(source_run):
    path, _ = first_cache(source_run)
    path.unlink()
    result = run(source_run)
    assert result["status"] == "incomplete"
    assert result["missing_required_files"] == 1
    assert not path.exists()


def test_partial_result_rows_are_incomplete(source_run):
    save_rows(source_run["root"], "holdout", "full", source_run["rows"]["full"][:1])
    result = run(source_run)
    assert result["status"] == "incomplete"
    assert "INCOMPLETE_RESULT_ROWS" in result["error_counts"]


def test_api_failure_is_consistent_only_when_scores_are_none(source_run):
    path, cache = first_cache(source_run)
    cache.update(ok=False, response="", usage={}, error="RuntimeError (details omitted)")
    write_json(path, cache)
    row = source_run["rows"]["full"][0]
    row.update(agent_ok=False, response="", usage={}, api_error=cache["error"],
               hard=None, em=None, f1=None, predicted_answer=None)
    save_rows(source_run["root"], "holdout", "full", source_run["rows"]["full"])
    result = run(source_run)
    assert result["status"] == "complete"
    assert result["counts"]["api_error_rows"] == 1
    row.update(hard=0, em=0, f1=0)
    save_rows(source_run["root"], "holdout", "full", source_run["rows"]["full"])
    result = run(source_run)
    assert result["status"] == "failed"
    assert "API_ERROR_HAS_SCORES" in result["error_counts"]


def test_modified_dataset_cannot_redefine_expected_prompt(source_run):
    altered = copy.deepcopy(source_run["tasks"])
    altered[0]["context"] = "PRIVATE_TAMPER"
    write_json(source_run["root"] / "datasets/holdout.json", altered)
    result = run(source_run)
    assert result["status"] == "failed"
    assert "TASKS_DIFFER_FROM_FROZEN_CACHE" in result["error_counts"]


def test_nonreal_source_is_rejected(source_run):
    path = source_run["root"] / "frozen_source_protocol.json"
    frozen = read_json(path)
    frozen["execution_mode"] = "injected_test_double"
    write_json(path, frozen)
    assert "NONREAL_EXECUTION_MODE" in run(source_run)["error_counts"]


def test_attribution_audits_only_its_two_new_arms(source_run):
    source, root = source_run["root"], source_run["repo"] / "attribution"
    arms = ("base", "full", *audit.E_ARMS)
    protocol = {**source_run["protocol"], "protocol_version": "synthetic-attribution",
                "arms": snapshots(root, arms), "execution_mode": "real_target_api", "new_arms": list(audit.E_ARMS),
                "settings": {"source_dir": str(source)}, "source_manifest_digest": audit._digest(source_run["manifest"]),
                "source_artifacts": {name: audit._file_hash(source / name) for name in
                                     ("source_protocol.json", "source_manifest.json", "frozen_source_protocol.json")}}
    write_json(root / "attribution_protocol.json", protocol)
    write_json(root / "attribution_seal.json", {"protocol_sha256": audit._file_hash(root / "attribution_protocol.json")})
    borrowed = {name: audit._file_hash(source / name) for name in ("datasets/holdout.json", "holdout_summary.json")}
    write_json(root / "borrowed_source_holdout_artifacts.json", borrowed)
    write_json(root / "datasets/holdout.json", source_run["tasks"])
    write_json(root / "source_provider.json", source_run["provider"])
    write_json(root / "holdout_summary.json", {"split": "holdout", "execution_mode": "real_target_api",
                                               "protocol_sha256": audit._file_hash(root / "attribution_protocol.json")})
    make_calls(root, protocol, source_run["tasks"], source_run["service"], audit.E_ARMS)
    # No local Base/full rollouts or call caches are created in E.
    result = run(source_run, root)
    assert result["status"] == "complete"
    assert result["kind"] == "attribution"
    assert result["counts"]["arms_expected"] == 2
    assert result["counts"]["rows_expected"] == result["counts"]["call_caches_checked"] == 4
    assert not (root / "searchqa_rollouts/holdout/base/results.jsonl").exists()
    assert audit.audit_run(root, "calibration", repo=source_run["repo"])["status"] == "failed"


def test_cli_never_prints_private_prompt_answer_or_corrupt_response(source_run, capsys):
    path, cache = first_cache(source_run)
    cache["response"] = "PRIVATE_TAMPER_RESPONSE"
    write_json(path, cache)
    assert audit.main(["--run-dir", str(source_run["root"]), "--split", "holdout"]) == 1
    output = capsys.readouterr()
    assert "PRIVATE_" not in output.out + output.err
    parsed = json.loads(output.out)
    assert parsed["status"] == "failed"
    assert all(set(error) == {"code", "path"} for error in parsed["errors"])
