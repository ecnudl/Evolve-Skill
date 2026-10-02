"""Offline receipt fixtures only; no generated program or container executes."""
import base64
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import report_sheet_delivery_outcomes as audit
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from skillopt.validator_pilot.api import digest

IMAGE = "sha256:" + "a" * 64
PROGRAMS = {0, 2, 4, 6, 7}
CONTRACT, BUDGET, EXTRACTOR, COMPATIBILITY = 8, 10, 12, 14


def _save(path, value):
    value = seal(value)
    write_json(path, value)
    return value


def _rewrite(path, transform):
    value = read_json(path, sealed=True)
    value.pop("record_hash")
    transform(value)
    path.write_text(json.dumps(seal(value)))  # Deliberate fixture tampering.


def fixture(tmp_path):
    source, prior, gold, native, fenced = [tmp_path / name for name in ("source", "prior", "gold", "native", "fenced")]
    slots, predictions, calls, selected, index_to_key = [], {}, {}, [], {}
    missing = PROGRAMS | {CONTRACT, BUDGET, EXTRACTOR}
    for index in range(160):
        task_id, repeat = "fixture-" + str(index // 2), index % 2
        request = {"plan_hash": "1" * 64, "checkpoint_hash": "2" * 64, "benchmark": "spreadsheetbench",
                   "task_hash": digest(task_id), "repeat": repeat}
        key = digest(request)
        index_to_key[index] = key
        base = source / "predictions" / key
        _save(base / "intent.json", request)
        response = "print('PRIVATE_FIXTURE_RESPONSE')\n"
        if index == EXTRACTOR:
            response = "```excel\n=A1\n```\ninvalid prose\n```python\nprint('literal')\n```"
        call_request = {"position": request, "turn": 0, "system": "PRIVATE_FIXTURE_SYSTEM", "user": "PRIVATE_FIXTURE_INPUT", "max_tokens": 65536}
        receipt_request = {"system": call_request["system"], "user": call_request["user"], "max_tokens": 65536, "model": "fixture"}
        receipt = {"request": receipt_request, "request_hash": digest(receipt_request), "ok": index != BUDGET,
                   "status": 200, "stream_complete": True, "finish_reason": "length" if index == BUDGET else "stop",
                   "error_type": "truncated_content" if index == BUDGET else None,
                   "http_attempt_count": 1, "response": "" if index == BUDGET else response}
        call_key = digest(call_request)
        _save(base / "call_intents" / (call_key + ".json"), call_request)
        calls[index] = _save(base / "calls" / (call_key + ".json"), {"request": call_request, "receipt": receipt})
        code = audit.backends._code(response)
        case = {"status": "available", "reason": "isolated_workbook_generated", "cleanup_confirmed": True,
                "runtime_image_id": IMAGE, "execution_costs": {"container_calls": 1, "includes_cleanup": True},
                "output_base64": base64.b64encode(b"opaque engineering fixture, never scored").decode()}
        if index in missing:
            case.pop("output_base64")
            case["status"] = "missing_output" if index == CONTRACT else "unknown"
            case["reason"] = "output.xlsx_not_produced" if index == CONTRACT else "native_exception:SyntaxError" if index == EXTRACTOR else "native_exception:AttributeError"
        prediction = {"status": "unknown", "reason": "model_response_truncated", "output": None} if index == BUDGET else {
            "status": "available", "reason": "generated_once_executed_per_public_case", "output": {"code": code, "cases": [case]}}
        predictions[index] = _save(base / "prediction.json", {"request": request, "prediction": prediction})
        status = "unknown" if index in missing | {COMPATIBILITY} else "pass" if index % 2 else "fail"
        score = _save(source / "host_only/scores" / (key + ".json"), {"prediction_hash": predictions[index]["record_hash"],
            "task_id": task_id, "repeat": repeat, "status": status, "score": None if status == "unknown" else float(status == "pass")})
        slot = {"id": key, "prediction_path": str(base / "prediction.json"), "prediction_hash": predictions[index]["record_hash"],
                "old_score_hash": score["record_hash"], "old_status": status, "task_id": task_id, "repeat": repeat,
                "references": ["host-only-reference.xlsx"], "answer_position": "A1"}
        slots.append(slot)
        if index in PROGRAMS | {CONTRACT, EXTRACTOR}:
            selected.append({"position": key, "task_hash": request["task_hash"], "repeat": repeat,
                "prediction_hash": predictions[index]["record_hash"], "score_hash": score["record_hash"],
                "code_sha256": audit._sha(code.encode()), "case": 0, "input_sha256": "3" * 64, "original_reason": case["reason"]})
    prior_protocol = _save(prior / "protocol.json", {"version": "spreadsheet-v6-independent-replay-v1", "kind": "replay",
        "root": str(prior), "source": str(source), "engine_profile": "v8", "slots": slots})
    prior_rows, gold_slots = {}, []
    for slot in slots:
        previous = _save(prior / "positions" / (slot["id"] + ".json"), {"protocol_hash": prior_protocol["record_hash"],
            "slot_id": slot["id"], "status": slot["old_status"], "old_status": slot["old_status"], "cases": []})
        prior_rows[slot["id"]] = previous["record_hash"]
        gold_slots.append({**slot, "previous_status": previous["status"], "previous_result_hash": previous["record_hash"]})
    execution = {"open_workbook_intents": 0, "cleanup_unconfirmed": 0}
    _save(prior / "reports/terminal.json", {"protocol_hash": prior_protocol["record_hash"], "status": "complete", "positions": 160,
        "completed": 160, "execution": execution, "result_hashes": prior_rows})
    gold_protocol = _save(gold / "protocol.json", {"version": "spreadsheet-frozen-gold-full-replay-v1", "kind": "replay",
        "root": str(gold), "previous_replay": str(prior), "previous_protocol_hash": prior_protocol["record_hash"],
        "original_source": str(source), "slots": gold_slots})
    gold_rows = {}
    for index, slot in enumerate(gold_slots):
        row = _save(gold / "positions" / (slot["id"] + ".json"), {"protocol_hash": gold_protocol["record_hash"],
            "slot_id": slot["id"], "status": slot["old_status"], "old_status": slot["old_status"],
            "previous_status": slot["previous_status"], "delivery_status": "undelivered" if index in missing else "delivered", "cases": []})
        gold_rows[slot["id"]] = row["record_hash"]
    _save(gold / "reports/terminal.json", {"protocol_hash": gold_protocol["record_hash"], "status": "complete", "positions": 160,
        "completed": 160, "execution": execution, "result_hashes": gold_rows, "counts": dict(Counter(s["old_status"] for s in slots))})
    native_protocol = _save(native / "protocol.json", {"version": "native-unknown-replay-v1", "parent": str(source),
        "snapshot": {"benchmark": "spreadsheetbench", "fixture": True, "selected": selected}})
    native_rows, reviewed, by_position = {}, [], {}
    for item in selected:
        index = next(i for i, k in index_to_key.items() if k == item["position"])
        identity = {"protocol_hash": native_protocol["record_hash"], "item": item}
        diagnostic = {"phase": "generated_execution", "exception_type": "AttributeError", "generated_lines": [3],
                      "frames": [{"origin": "generated", "line": 3}]}
        result = {"status": "unknown", "reason": "native_exception:AttributeError", "diagnostic": diagnostic,
                  "cleanup_confirmed": True, "runtime_image_id": IMAGE, "execution_costs": {"container_calls": 1, "includes_cleanup": True}}
        if index == CONTRACT:
            result.update(status="missing_output", reason="output.xlsx_not_produced")
            result.pop("diagnostic")
        if index == EXTRACTOR:
            result = {"status": "invalid_program", "reason": "frozen_generated_syntax_error",
                      "diagnostic": {"phase": "generated_compile", "exception_type": "SyntaxError", "line": 1}}
        key = digest(item)
        _save(native / "intents" / (key + ".json"), identity)
        row = _save(native / "records" / (key + ".json"), {"identity": identity, "result": result, "cleanup_unconfirmed": False})
        native_rows[key] = row["record_hash"]
        by_position[item["position"]] = row
        if index != EXTRACTOR:
            reviewed.append({"task_id": slots[index]["task_id"], "repeat": slots[index]["repeat"],
                "prediction_hash": item["prediction_hash"], "original_call_record_hash": calls[index]["record_hash"],
                "code_sha256": item["code_sha256"], "diagnostic_record_hash": row["record_hash"],
                "attribution": "task_delivery_contract_ambiguity" if index == CONTRACT else "generated_program_defect",
                "exception_type": None if index == CONTRACT else "AttributeError", "generated_line": None if index == CONTRACT else 3,
                "finding": "Reviewed engineering fixture finding.", "evidence_limit": "Fixture; no program actually executed."})
    native_report = seal({"protocol_hash": native_protocol["record_hash"], "status": "completed",
        "closed_cases": len(selected), "selected_cases": len(selected), "record_hashes": native_rows})
    write_json(native / "reports" / (native_report["record_hash"] + ".json"), native_report)
    archive_path = tmp_path / "reviewed/attribution.json"
    _save(archive_path, {"version": "spreadsheet-delivery-static-attribution-v1", "status": "completed_static_attribution",
        "source_report_hash": native_report["record_hash"], "selected_positions": len(reviewed), "rows": reviewed})
    parsed = audit.code_delivery.extract_python(calls[EXTRACTOR]["receipt"]["response"])
    original = by_position[index_to_key[EXTRACTOR]]["identity"]["item"]
    item = {"position": index_to_key[EXTRACTOR], "eligible": True, "prediction_hash": original["prediction_hash"],
            "call_hash": calls[EXTRACTOR]["record_hash"], "old_code_sha256": original["code_sha256"], "score_hash": original["score_hash"],
            "repeat": slots[EXTRACTOR]["repeat"], "closed_stop": True, "substantive_extraction_changed": True,
            "parser": {k: v for k, v in parsed.items() if k != "code"}, "raw_sha256": parsed["source_sha256"]}
    fenced_protocol = _save(fenced / "protocol.json", {"version": "frozen-fenced-delivery-replay-v1", "audit": [item]})
    identity = {"protocol_hash": fenced_protocol["record_hash"], "item": item}
    _save(fenced / "intents" / (item["position"] + ".json"), identity)
    case = _save(fenced / "cases" / item["position"] / "0.json", {"status": "available", "cleanup_confirmed": True,
        "execution_costs": {"container_calls": 1}, "output_base64": base64.b64encode(b"recovered fixture").decode()})
    _save(fenced / "records" / (item["position"] + ".json"), {"identity": identity, "cleanup_unconfirmed": False, "new_model_calls": 0,
        "case_record_hashes": [case["record_hash"]], "cases": [{k: v for k, v in case.items() if k not in {"record_hash", "output_base64"}}]})
    return {"semantic_replay": gold, "prior_replay": prior, "native_replay": native, "attribution_report": archive_path,
            "output": tmp_path / "sidecar", "fenced_replay": fenced}, slots


def test_full_panel_sidecar_separates_semantics_and_new_retrospective_end_to_end_metric(tmp_path, monkeypatch):
    args, slots = fixture(tmp_path)
    before = {str(p): p.read_bytes() for p in tmp_path.rglob("*.json")}
    monkeypatch.setattr(audit.backends, "_bounded_command", lambda *a, **k: pytest.fail("No process may execute"))
    result = audit.build(**args)
    assert result["positions"] == 160 and result["independent_tasks"] == 80
    assert result["original_delivery_counts"] == {"delivered": 152, "undelivered": 8}
    assert result["delivery_outcomes"] == {"generated_program_failure": 5, "contract_ambiguity": 1,
        "completed_model_budget_exhaustion": 1, "extractor_bug": 1, "delivered": 152}
    assert result["semantic_counts"]["unknown"] == 9
    assert result["end_to_end_counts"]["unknown"] == 3
    assert result["end_to_end_counts"]["fail"] == result["semantic_counts"]["fail"] + 6
    assert result["semantic_to_end_to_end"]["unknown->fail"] == 6
    assert not result["policy"]["preregistered_before_original_model_calls"]
    assert result["new_model_api_calls"] == result["new_container_calls"] == 0
    assert not result["semantic_scores_changed"] and not result["answers_modified"] and not result["feedback_allowed"]
    assert before == {path: Path(path).read_bytes() for path in before}
    serialized = json.dumps(result)
    assert all(marker not in serialized for marker in ("PRIVATE_FIXTURE", "host-only-reference", "opaque engineering", "recovered fixture"))
    rows = [read_json(p, sealed=True) for p in (args["output"] / "positions").glob("*.json")]
    assert len(rows) == 160 and all(r["assessment"]["semantic_score"]["status"] == next(s["old_status"] for s in slots if s["id"] == r["slot_id"]) for r in rows)
    with pytest.raises(ValueError, match="New immutable"):
        audit.build(**args)


def test_missing_fenced_evidence_stays_unknown_without_blame(tmp_path):
    args, _ = fixture(tmp_path)
    args["fenced_replay"] = None
    result = audit.build(**args)
    assert result["delivery_outcomes"]["unknown"] == 1
    assert "extractor_bug" not in result["delivery_outcomes"]
    assert result["end_to_end_counts"]["unknown"] == 3


@pytest.mark.parametrize("change", ["generated_line", "diagnostic_record_hash", "prediction_hash", "original_call_record_hash"])
def test_reviewed_claims_require_exact_original_and_actual_traceback_evidence(tmp_path, change):
    args, _ = fixture(tmp_path)
    _rewrite(args["attribution_report"], lambda doc: doc["rows"][0].__setitem__(change, 999 if change == "generated_line" else "f" * 64))
    with pytest.raises(ValueError, match="identity differs|observed exception"):
        audit.build(**args)
    assert not args["output"].exists()


@pytest.mark.parametrize("field,value", [("stream_complete", False), ("error_type", "transport_error"),
    ("error_type", "timeout"), ("status", 503), ("finish_reason", "stop")])
def test_closed_length_requires_actual_complete_stream_not_historical_reason(tmp_path, field, value):
    args, slots = fixture(tmp_path)
    call_path = next((Path(slots[BUDGET]["prediction_path"]).parent / "calls").glob("*.json"))
    _rewrite(call_path, lambda row: row["receipt"].__setitem__(field, value))
    result = audit.build(**args)
    assert "completed_model_budget_exhaustion" not in result["delivery_outcomes"]
    assert result["semantic_to_end_to_end"]["unknown->fail"] == 5


def test_original_response_must_match_the_unmodified_code(tmp_path):
    args, slots = fixture(tmp_path)
    slot = slots[0]
    call_path = next((Path(slot["prediction_path"]).parent / "calls").glob("*.json"))
    _rewrite(call_path, lambda row: row["receipt"].__setitem__("response", "different_code()"))
    with pytest.raises(ValueError, match="closed unmodified response"):
        audit.build(**args)
    assert not args["output"].exists()


def test_unclosed_semantic_replay_or_roster_cannot_publish_sidecar(tmp_path):
    args, _ = fixture(tmp_path)
    _rewrite(args["semantic_replay"] / "reports/terminal.json", lambda row: row["execution"].__setitem__("open_workbook_intents", 1))
    with pytest.raises(ValueError, match="Unclosed semantic replay"):
        audit.build(**args)
    assert not args["output"].exists()


def test_native_failure_requires_actual_container_completion_not_the_static_finding(tmp_path):
    args, slots = fixture(tmp_path)
    archive = read_json(args["attribution_report"], sealed=True)
    evidence = audit.Evidence()
    _, _, native = audit._native_records(evidence, args["native_replay"], archive)
    slot = slots[0]
    prediction, call, code = audit._prediction(evidence, slot)
    row = deepcopy(native[slot["id"]])
    row["result"]["cleanup_confirmed"] = False
    identity = {"code_sha256": audit._sha(code.encode())}
    with pytest.raises(ValueError, match="completed container receipt"):
        audit._observed_native(row, identity, slot, prediction)
