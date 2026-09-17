"""Native SkillOpt integration with fake transport, never paid model calls."""

import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.coevolution_v9 import learning
from skillopt.envs.searchqa import evaluator, rollout
from skillopt.validator_pilot.api import digest


def receipt(system, user, key, response, *, ok=True, kind="v9_train", max_tokens=4096):
    request = {"system": system, "user": user, "kind": kind, "key": key,
               "max_tokens": max_tokens, "repeat": 0, "model": "glm-5.3", "service": {"fake": True}}
    return {"request_hash": digest(request), "request": request, "ok": ok,
            "response": response, "usage": {}, "error_type": None if ok else "timeout",
            "http_attempt_count": 1}


def rows(skill="initial", count=2, *, failed_api=()):
    result = []
    for index in range(count):
        item = {"key": f"qa_{index}", "question": f"Who is person {index}?", "context": "Name is Alice.",
                "answers": ["Alice"], "split": "train"}
        system, user = learning.native_qa_messages(skill, item)
        result.append({"item": item, "receipt": receipt(system, user, item["key"],
                       "<answer>Bob</answer>" if index % 2 else "<answer>Alice</answer>",
                       ok=index not in failed_api)})
    return result


class API:
    def __init__(self, *, response=None, fail_stages=(), unusable_stages=(), edits=1):
        self.calls = []
        self.response, self.fail_stages, self.unusable_stages, self.edits = response, fail_stages, unusable_stages, edits

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        stage = kind.removeprefix("v9_native_")
        if self.response is not None:
            raw = self.response
        elif stage in self.unusable_stages:
            raw = "not json"
        elif stage == "analyst":
            raw = json.dumps({"batch_size": 1, "patch": {"edits": [
                {"op": "append", "content": f"Verify answer {index}."} for index in range(self.edits)]}})
        elif stage == "merge":
            raw = json.dumps({"edits": [
                {"op": "append", "content": f"Merged rule {index}."} for index in range(self.edits)]})
        else:
            raw = json.dumps({"selected_indices": [0, 1, 2, 3]})
        record = receipt(system, user, key, raw, ok=stage not in self.fail_stages, kind=kind, max_tokens=max_tokens)
        self.calls.append(record)
        return record


def run(tmp_path, api=None, source=None):
    api = api or API()
    result = learning.propose_candidate(api, "initial", rows() if source is None else source,
                                        tmp_path / "learning", round_key="history_0")
    return result, api


def bytes_under(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()}


@pytest.mark.parametrize("skill", ["", "initial", "## Skill\nVerify carefully."])
def test_native_messages_are_identical(skill):
    item = {"question": "who?", "context": "start" + "[DOC]" + "x" * 6500}
    system, user = learning.native_qa_messages(skill, item)
    assert system == rollout._build_system(skill)
    assert user == rollout._build_user(item["question"], item["context"])
    assert "x" * 6500 not in user


@pytest.mark.parametrize("raw", ["<answer>Alice</answer>", "Reason\nAlice", "<answer>The ALICE!</answer>",
                                  "<answer>not Alice</answer>", ""])
def test_scores_are_original_native_metrics(raw):
    item = {"answers": ["Alice"]}
    expected = evaluator.evaluate(raw, item["answers"])
    assert learning.score_qa(raw, item) == {**expected, "hard": int(expected["em"]), "soft": expected["f1"]}


def test_real_native_analyst_merge_apply_and_provenance(tmp_path):
    result, api = run(tmp_path)
    verify(result)
    assert result["candidate_text"] == "initial\n\nMerged rule 0.\n"
    assert result["status"] == "candidate_ready"
    assert result["acceptance"] == "not_decided" and not result["scope_expansion_authorized"]
    assert result["optimizer_calls"] == len(api.calls) == 3
    assert {call["request"]["kind"] for call in api.calls} == {"v9_native_analyst", "v9_native_merge"}
    assert sorted(result["optimizer_request_hashes"]) == sorted(call["request_hash"] for call in api.calls)
    assert result["apply_report"][0]["status"] == "applied_append"
    assert all(call["request"]["max_tokens"] == 4096 for call in api.calls)
    assert all("<answer>" in call["request"]["user"] for call in api.calls[:2])
    saved = [json.loads(path.read_text()) for path in (tmp_path / "learning/optimizer/intents").glob("*.json")]
    assert all(call["requested_max_tokens"] == 16384 and call["effective_max_tokens"] == 4096 for call in saved)


def test_native_prompts_are_not_replaced(tmp_path):
    _, api = run(tmp_path)
    analyst_prompts = {call["request"]["system"] for call in api.calls if call["request"]["kind"] == "v9_native_analyst"}
    assert analyst_prompts == {learning.load_prompt("analyst_error", env="searchqa"),
                               learning.load_prompt("analyst_success", env="searchqa")}
    assert api.calls[-1]["request"]["system"] == learning.load_prompt("merge_final")


def test_analyst_trajectory_payload_matches_native_process_one(tmp_path, monkeypatch):
    source = rows()
    monkeypatch.setattr(rollout, "is_target_exec_backend", lambda: False)
    for row in source:
        monkeypatch.setattr(rollout, "chat_target", lambda **_kwargs: (row["receipt"]["response"], {}))
        item = {**row["item"], "id": row["item"]["key"]}
        rollout.process_one(item, str(tmp_path / "original"), "initial", max_turns=1)
    run(tmp_path, source=source)
    for row in source:
        identifier = row["item"]["key"]
        original = tmp_path / "original/predictions" / identifier
        adapted = tmp_path / "learning/predictions" / identifier
        assert json.loads((original / "conversation.json").read_text()) == json.loads(
            (adapted / "conversation.json").read_text())
        for name in ("target_system_prompt.txt", "target_user_prompt.txt"):
            assert (original / name).read_text() == (adapted / name).read_text()


def test_completed_replay_is_readonly_without_api(tmp_path, monkeypatch):
    result, api = run(tmp_path)
    before = bytes_under(tmp_path)

    def forbidden(*_a, **_k):
        pytest.fail("Completed learning must not call model or write")

    api.call = forbidden
    monkeypatch.setattr(learning, "write_immutable_json", forbidden)
    assert learning.propose_candidate(api, "initial", rows(), tmp_path / "learning", round_key="history_0") == result
    assert bytes_under(tmp_path) == before


@pytest.mark.parametrize("path", ["identity.json", "reflection.json", "selected.json",
                                  "predictions/qa_0/conversation.json"])
def test_missing_completed_evidence_is_not_reconstructed(tmp_path, path):
    _, api = run(tmp_path)
    (tmp_path / "learning" / path).unlink()
    before = bytes_under(tmp_path)
    with pytest.raises(ValueError):
        run(tmp_path, api)
    assert len(api.calls) == 3 and bytes_under(tmp_path) == before


@pytest.mark.parametrize("change", ["parent", "round", "row_response", "gold", "request"])
def test_changed_completed_identity_fails_before_api(tmp_path, change):
    _, api = run(tmp_path)
    source, parent, key = rows(), "initial", "history_0"
    if change == "parent":
        parent = "other"
    elif change == "round":
        key = "history_1"
    elif change == "row_response":
        source[0]["receipt"]["response"] = "Different"
    elif change == "gold":
        source[0]["item"]["answers"] = ["Bob"]
    else:
        source[0]["receipt"]["request"]["system"] = "Other"
    with pytest.raises(ValueError):
        learning.propose_candidate(api, parent, source, tmp_path / "learning", round_key=key)
    assert len(api.calls) == 3


@pytest.mark.parametrize("terminal", [False, True])
def test_invalid_and_terminal_analysts_keep_parent_no_resampling(tmp_path, terminal):
    api = API(fail_stages=("analyst",)) if terminal else API(unusable_stages=("analyst",))
    result, _ = run(tmp_path, api)
    assert result["status"] == "no_change_keep_parent"
    assert result["candidate_text"] == "initial" and result["optimizer_calls"] == 2
    assert result["optimizer_terminal_calls"] == (2 if terminal else 0)
    assert run(tmp_path, api)[0] == result and len(api.calls) == 2


@pytest.mark.parametrize("terminal", [False, True])
def test_original_merge_fallback_preserved(tmp_path, terminal):
    api = API(fail_stages=("merge",)) if terminal else API(unusable_stages=("merge",))
    with pytest.warns(UserWarning, match="fallback"):
        result, _ = run(tmp_path, api)
    assert "fallback" in result["merged_patch"]["reasoning"]
    assert result["candidate_text"].count("Verify answer 0.") == 2
    assert len(api.calls) == 3


def test_ranking_only_runs_above_four_edits(tmp_path):
    result, api = run(tmp_path, API(edits=6))
    assert [call["request"]["kind"] for call in api.calls][-1] == "v9_native_ranking"
    assert len(result["selected_patch"]["edits"]) == 4


def test_native_ranking_fallback_preserved(tmp_path):
    result, api = run(tmp_path, API(edits=6, unusable_stages=("ranking",)))
    assert "fallback truncated" in result["selected_patch"]["reasoning"]
    assert len(result["selected_patch"]["edits"]) == 4 and len(api.calls) == 4


def test_terminal_source_is_unknown_never_a_false_semantic_failure(tmp_path):
    result, api = run(tmp_path, source=rows(failed_api=(1,)))
    assert result["available_training_rows"] == 1
    assert result["training_statuses"][1]["status"] == "unknown"
    assert len(api.calls) == 1
    assert "Failed Trajectories" not in api.calls[0]["request"]["user"]
    assert not (tmp_path / "learning/predictions/qa_1").exists()


def test_all_terminal_sources_make_no_optimizer_calls(tmp_path):
    result, api = run(tmp_path, source=rows(failed_api=(0, 1)))
    assert result["available_training_rows"] == 0 and api.calls == []
    assert result["candidate_text"] == "initial"


def test_patches_are_stably_sorted_and_source_order_not_significant(tmp_path):
    first, api = run(tmp_path)
    assert first["raw_patches"] == sorted(first["raw_patches"], key=digest)
    assert run(tmp_path, api, list(reversed(rows())))[0] == first


def test_32_source_rows_have_bounded_real_native_call_count(tmp_path):
    result, api = run(tmp_path, source=rows(count=32))
    assert result["optimizer_calls"] == len(api.calls) == 7  # 4 analysts, 2 group merges, 1 final merge
    assert len(api.calls) <= learning.MAX_OPTIMIZER_CALLS


def test_partial_resume_reuses_saved_stages_without_model(tmp_path):
    result, api = run(tmp_path)
    (tmp_path / "learning/result.json").unlink()
    assert run(tmp_path, api)[0] == result
    assert len(api.calls) == 3


def test_unresolved_optimizer_intent_fails_closed_without_api(tmp_path):
    _, api = run(tmp_path)
    (tmp_path / "learning/result.json").unlink()
    next((tmp_path / "learning/optimizer/calls").glob("*.json")).unlink()
    with pytest.raises(ValueError, match="Unresolved"):
        run(tmp_path, api)
    assert len(api.calls) == 3


def test_monkeypatch_transport_is_restored_after_request_error(tmp_path):
    originals = [module.chat_optimizer for module in (learning.reflect, learning.aggregate, learning.clip)]
    api = API()

    attempted = []

    def unresolved(*_a, **_k):
        attempted.append(True)
        raise RuntimeError("host failure")

    api.call = unresolved
    with pytest.raises(ValueError, match="Unclosed"):
        run(tmp_path, api)
    assert len(attempted) == 1
    assert originals == [module.chat_optimizer for module in (learning.reflect, learning.aggregate, learning.clip)]


@pytest.mark.parametrize("identifier", ["..", ".", "../oops", "a/b", ""])
def test_unsafe_ids_rejected(tmp_path, identifier):
    source = rows()
    source[0]["item"]["key"] = identifier
    with pytest.raises(ValueError, match="identifiers"):
        run(tmp_path, source=source)


@pytest.mark.parametrize("split", ["final", "test", "holdout", "calibration", "audit",
                                  "confirmation_h0_r0", "final_h0_r0", "training", "", None])
def test_forbidden_splits_do_not_enter_reflection(tmp_path, split):
    source = rows()
    source[0]["item"]["split"] = split
    with pytest.raises(ValueError, match="training"):
        run(tmp_path, source=source)


def test_missing_source_split_is_rejected(tmp_path):
    source = rows()
    del source[0]["item"]["split"]
    with pytest.raises(ValueError, match="training"):
        run(tmp_path, source=source)


def test_namespaced_training_split_is_accepted(tmp_path):
    source = rows()
    for row in source:
        row["item"]["split"] = "train_h2_r0"
    assert run(tmp_path, source=source)[0]["status"] == "candidate_ready"


def test_duplicate_training_identity_rejected(tmp_path):
    source = rows()
    source.append(deepcopy(source[0]))
    with pytest.raises(ValueError, match="identifiers"):
        run(tmp_path, source=source)


def test_source_receipt_must_be_for_original_prompt(tmp_path):
    source = rows()
    request = source[0]["receipt"]["request"]
    request["user"] += " extra instructions"
    source[0]["receipt"]["request_hash"] = digest(request)
    with pytest.raises(ValueError, match="lineage"):
        run(tmp_path, source=source)


def test_symlink_output_is_rejected(tmp_path):
    target = tmp_path / "outside"
    target.mkdir()
    (tmp_path / "learning").symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        run(tmp_path)


def test_invalid_native_metadata_keeps_parent_and_records_issue(tmp_path):
    raw = json.dumps({"batch_size": "not integer", "patch": {"edits": [{"op": "append", "content": "new"}]}})
    result, api = run(tmp_path, API(response=raw))
    assert result["normalisation_error"] == "invalid_native_patch_metadata"
    assert result["candidate_text"] == "initial" and len(api.calls) == 2


def test_native_tolerant_json_extractor_not_replaced_with_strict_parser(tmp_path):
    raw = '```json\n{"patch":{"edits":[{"op":"append","content":"Native rule."}]}}\n```'
    result, _ = run(tmp_path, API(response=raw), source=rows(count=1))
    assert result["candidate_text"] == "initial\n\nNative rule.\n"


def test_call_cap_keeps_parent_and_is_sticky_on_partial_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(learning, "MAX_OPTIMIZER_CALLS", 1)
    result, api = run(tmp_path)
    assert len(api.calls) == 1
    assert result["status"] == "budget_exhausted_keep_parent" and result["candidate_text"] == "initial"
    (tmp_path / "learning/result.json").unlink()
    assert run(tmp_path, api)[0] == result and len(api.calls) == 1


def test_record_hash_tampering_is_rejected(tmp_path):
    run(tmp_path)
    path = tmp_path / "learning/result.json"
    record = json.loads(path.read_text())
    record["candidate_text"] = "tampered"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="checksum"):
        run(tmp_path)


def test_completed_missing_optimizer_metadata_is_rejected_even_if_result_is_resealed(tmp_path):
    result, _ = run(tmp_path)
    next((tmp_path / "learning/optimizer/calls").glob("*.json")).unlink()
    path = tmp_path / "learning/result.json"
    path.write_text(json.dumps(seal({k: v for k, v in result.items() if k != "record_hash"})))
    with pytest.raises(ValueError, match="changed"):
        run(tmp_path)
