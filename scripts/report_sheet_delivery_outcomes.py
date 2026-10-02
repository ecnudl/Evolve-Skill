"""Zero-execution sidecar for a complete frozen-gold spreadsheet replay.

Original prediction bytes, model-call closure, actual native diagnostic records,
and reviewed static attribution must agree. Semantic statuses are copied from a
completed replay. A separately named retrospective end-to-end metric counts
confirmed program failures and completed token-budget exhaustion as failures;
contract ambiguity, extraction defects and compatibility gaps remain unknown.
No historical score, candidate, code, workbook or model response is replaced.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from collections import Counter
from pathlib import Path

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends, code_delivery, delivery_outcomes
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

VERSION = "spreadsheet-frozen-delivery-sidecar-v1"
POLICY = {"version": "retrospective-workbook-end-to-end-v1",
          "preserve_known_semantic_status": True,
          "unknown_semantics_count_as_failure_only_for": ["generated_program_failure", "completed_model_budget_exhaustion"],
          "other_unknown_semantics": "unknown", "historical_protocol_changed": False,
          "preregistered_before_original_model_calls": False}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


class Evidence:
    """Track the exact files read; private file contents never enter the report."""
    def __init__(self):
        self.inventory = {}

    def read(self, path):
        path = safe_path(path)
        raw = path.read_bytes()
        value = read_json(path, sealed=True)
        require(path.read_bytes() == raw, "Evidence changed while reading")
        self.inventory[str(path)] = _sha(raw)
        return value

    def recheck(self):
        require(all(_sha(safe_path(path).read_bytes()) == expected for path, expected in self.inventory.items()),
                "Evidence changed during the sidecar audit")


def _terminal(evidence, root, protocol, *, count, hash_field="result_hashes"):
    terminals = []
    for path in sorted((root / "reports").glob("*.json")):
        row = evidence.read(path)
        require(row["protocol_hash"] == protocol["record_hash"], "Report protocol differs")
        if row["status"] == "complete":
            require(row["positions"] == row["completed"] == count and len(row[hash_field]) == count,
                    "Incomplete terminal report")
            require(not row["execution"]["open_workbook_intents"] and not row["execution"]["cleanup_unconfirmed"],
                    "Unclosed semantic replay")
            terminals.append(row)
    require(len(terminals) == 1, "Exactly one completed semantic report required")
    return terminals[0]


def _native_records(evidence, root, attribution):
    protocol = evidence.read(root / "protocol.json")
    require(protocol["version"] == "native-unknown-replay-v1"
            and protocol["snapshot"]["benchmark"] == "spreadsheetbench", "Wrong native diagnostic protocol")
    report = evidence.read(root / "reports" / (attribution["source_report_hash"] + ".json"))
    selected = protocol["snapshot"]["selected"]
    require(report["record_hash"] == attribution["source_report_hash"] and report["status"] == "completed"
            and report["protocol_hash"] == protocol["record_hash"]
            and report["closed_cases"] == report["selected_cases"] == len(selected), "Native diagnostic is not closed")
    expected = {digest(item) for item in selected}
    require(len(expected) == len(selected) and set(report["record_hashes"]) == expected
            and {p.stem for p in (root / "records").glob("*.json")} == expected
            and {p.stem for p in (root / "intents").glob("*.json")} == expected,
            "Native record/intent roster differs")
    rows = {}
    for item in selected:
        key = digest(item)
        row = evidence.read(root / "records" / (key + ".json"))
        identity = {"protocol_hash": protocol["record_hash"], "item": item}
        require(row["record_hash"] == report["record_hashes"][key] and row["identity"] == identity
                and evidence.read(root / "intents" / (key + ".json")) == seal(identity)
                and row["cleanup_unconfirmed"] is False, "Native diagnostic identity or cleanup differs")
        require(item["position"] not in rows, "Multiple native cases require an explicit aggregation policy")
        rows[item["position"]] = row
    return protocol, report, rows


def _prediction(evidence, slot):
    path = safe_path(slot["prediction_path"])
    prediction = evidence.read(path)
    request = prediction["request"]
    require(prediction["record_hash"] == slot["prediction_hash"] and digest(request) == slot["id"]
            and request["benchmark"] == "spreadsheetbench" and request["repeat"] == slot["repeat"]
            and evidence.read(path.parent / "intent.json") == seal(request), "Original prediction identity differs")
    calls = list((path.parent / "calls").glob("*.json"))
    intents = list((path.parent / "call_intents").glob("*.json"))
    require(len(calls) == len(intents) == 1 and calls[0].name == intents[0].name, "Original call is not uniquely closed")
    call = evidence.read(calls[0])
    require(call["request"]["position"] == request and call["request"]["turn"] == 0
            and evidence.read(intents[0]) == seal(call["request"])
            and calls[0].stem == digest(call["request"]), "Original call intent differs")
    receipt = call["receipt"]
    require(receipt["request_hash"] == digest(receipt["request"])
            and all(receipt["request"][k] == call["request"][k] for k in ("system", "user", "max_tokens"))
            and type(receipt["http_attempt_count"]) is int and receipt["http_attempt_count"] >= 1,
            "Original model receipt identity differs")
    code = (prediction["prediction"].get("output") or {}).get("code")
    if code is not None:
        require(type(code) is str and receipt["ok"] is True and receipt["status"] == 200
                and receipt["stream_complete"] is True and receipt["finish_reason"] == "stop"
                and receipt["error_type"] is None and code == backends._code(receipt["response"]),
                "Original code differs from its closed unmodified response")
    return prediction, call, code


def _observed_native(row, identity, slot, prediction):
    item, result = row["identity"]["item"], row["result"]
    cases = (prediction["prediction"].get("output") or {}).get("cases", [])
    require(item["position"] == slot["id"] and item["prediction_hash"] == prediction["record_hash"]
            and item["code_sha256"] == identity["code_sha256"] and item["score_hash"] == slot["old_score_hash"]
            and item["task_hash"] == prediction["request"]["task_hash"] and item["repeat"] == slot["repeat"]
            and type(item["case"]) is int and 0 <= item["case"] < len(cases)
            and cases[item["case"]]["reason"] == item["original_reason"], "Native diagnostic belongs to another original case")
    require(result["cleanup_confirmed"] is True and result["execution_costs"]["container_calls"] == 1
            and result["execution_costs"]["includes_cleanup"] is True
            and result["runtime_image_id"] == cases[item["case"]]["runtime_image_id"],
            "Native diagnostic lacks a completed container receipt")
    diagnostic = result.get("diagnostic", {})
    if result["status"] == "missing_output":
        require(result["reason"] == "output.xlsx_not_produced" and not diagnostic, "Missing-output evidence differs")
        status, lines, exception = "missing_output", [], None
    else:
        require(result["status"] == "unknown" and diagnostic.get("phase") == "generated_execution"
                and result["reason"] == "native_exception:" + diagnostic["exception_type"]
                and any(frame["origin"] == "generated" and frame["line"] in diagnostic["generated_lines"]
                        for frame in diagnostic["frames"]), "No completed generated-code traceback")
        frame_lines = {frame["line"] for frame in diagnostic["frames"] if frame["origin"] == "generated"}
        # The helper line list alone is not a traceback: reviewed attribution
        # must match a line actually saved in a generated-source frame.
        lines = [line for line in diagnostic["generated_lines"] if line in frame_lines]
        status, exception = "execution_failed", diagnostic["exception_type"]
    return {"identity": identity, "kind": "native_execution", "status": status, "completed": True,
            "cleanup_confirmed": True, "generated_lines": lines, "exception_type": exception,
            "expected_artifacts": len(slot["references"]), "artifact_sha256s": []}


def _extractor_evidence(evidence, root, slot, identity, call, diagnostic):
    """Use actual frozen parser/replay receipts; never infer a bug from SyntaxError."""
    protocol = evidence.read(root / "protocol.json")
    require(protocol["version"] == "frozen-fenced-delivery-replay-v1", "Wrong fenced replay protocol")
    matches = [item for item in protocol["audit"] if item["position"] == slot["id"] and item["eligible"]]
    require(len(matches) == 1, "No unique independently replayed extraction")
    item = matches[0]
    require(item["prediction_hash"] == identity["prediction_hash"] and item["call_hash"] == call["record_hash"]
            and item["old_code_sha256"] == identity["code_sha256"] and item["score_hash"] == slot["old_score_hash"]
            and item["repeat"] == slot["repeat"] and item["closed_stop"] is True
            and item["substantive_extraction_changed"] is True, "Frozen extraction identity differs")
    parser = code_delivery.extract_python(call["receipt"]["response"])
    require(parser["status"] == "available" and parser["candidate_kind"] == "explicit_python"
            and {k: v for k, v in parser.items() if k != "code"} == item["parser"]
            and _sha(call["receipt"]["response"].encode()) == item["raw_sha256"], "Frozen literal extraction changed")
    row = evidence.read(root / "records" / (slot["id"] + ".json"))
    frozen_identity = {"protocol_hash": protocol["record_hash"], "item": item}
    require(row["identity"] == frozen_identity
            and evidence.read(root / "intents" / (slot["id"] + ".json")) == seal(frozen_identity)
            and row["cleanup_unconfirmed"] is False and row["new_model_calls"] == 0
            and len(row["case_record_hashes"]) == len(slot["references"]) == len(row["cases"]),
            "Frozen extraction execution is incomplete")
    for index, expected in enumerate(row["case_record_hashes"]):
        case = evidence.read(root / "cases" / slot["id"] / f"{index}.json")
        require(case["record_hash"] == expected and case["status"] == "available"
                and case["cleanup_confirmed"] is True and case["execution_costs"]["container_calls"] == 1
                and {k: v for k, v in case.items() if k not in {"record_hash", "output_base64"}} == row["cases"][index],
                "Actual extraction artifact receipt differs")
        require(bool(base64.b64decode(case["output_base64"], validate=True)), "Recovered artifact missing")
    require(diagnostic["result"]["status"] == "invalid_program"
            and diagnostic["result"]["diagnostic"]["phase"] == "generated_compile"
            and diagnostic["result"]["diagnostic"]["exception_type"] == "SyntaxError",
            "Original extractor failure not diagnosed")
    observation = {"identity": identity, "kind": "extraction", "literal_source_verified": True,
                   "response_sha256": parser["source_sha256"], "literal_code_sha256": parser["code_sha256"],
                   "literal_span": parser["span"]}
    attribution = {**identity, "attribution": "extractor_bug", "exception_type": "SyntaxError",
                   "generated_line": diagnostic["result"]["diagnostic"]["line"],
                   "finding": "The original extraction failed compilation; the independently frozen parser selected one unchanged explicit Python span and its completed replay delivered all required artifacts.",
                   "evidence_limit": "The recovered artifacts and their semantic scores do not replace the original prediction or semantic scores in this sidecar.",
                   "fenced_record_hash": row["record_hash"], "fenced_protocol_hash": protocol["record_hash"],
                   **{k: observation[k] for k in ("response_sha256", "literal_code_sha256", "literal_span")}}
    return observation, attribution


def _original_delivery(slot, prediction):
    cases = (prediction["prediction"].get("output") or {}).get("cases", [])
    artifacts = []
    for case in cases:
        if case["status"] == "available":
            require(case["cleanup_confirmed"] is True, "Original artifact cleanup was not confirmed")
            artifacts.append(_sha(base64.b64decode(case["output_base64"], validate=True)))
    require(len(cases) in {0, len(slot["references"])}, "Original delivery case denominator differs")
    return cases, artifacts


def build(*, semantic_replay, prior_replay, native_replay, attribution_report, output, fenced_replay=None):
    semantic_root, prior_root, native_root, root = map(safe_path, (semantic_replay, prior_replay, native_replay, output))
    fenced_root = safe_path(fenced_replay) if fenced_replay else None
    evidence = Evidence()
    require(not root.exists(), "New immutable sidecar directory required")
    protocol = evidence.read(semantic_root / "protocol.json")
    prior = evidence.read(prior_root / "protocol.json")
    require(protocol["version"] == "spreadsheet-frozen-gold-full-replay-v1" and protocol["kind"] == "replay"
            and protocol["previous_protocol_hash"] == prior["record_hash"]
            and protocol["previous_replay"] == str(prior_root) and protocol["root"] == str(semantic_root)
            and prior["root"] == str(prior_root) and prior["engine_profile"] == "v8"
            and protocol["original_source"] == prior["source"], "Frozen semantic/prior replay binding differs")
    source = safe_path(prior["source"])
    inputs = [semantic_root, prior_root, native_root, source, safe_path(attribution_report).parent]
    if fenced_root:
        inputs.append(fenced_root)
    require(all(not root.is_relative_to(path) and not path.is_relative_to(root) for path in inputs),
            "Sidecar must be separate from its evidence directories")
    slots = protocol["slots"]
    tasks = {s["task_id"] for s in slots}
    require(len(slots) == len({s["id"] for s in slots}) == 160 and len(tasks) == 80
            and all({s["repeat"] for s in slots if s["task_id"] == task} == {0, 1} for task in tasks),
            "Full 80-task / 160-position roster required")
    prior_slots = {s["id"]: s for s in prior["slots"]}
    require(len(prior_slots) == len(prior["slots"]) == 160 and set(prior_slots) == {s["id"] for s in slots}
            and all(all(slot.get(k) == v for k, v in prior_slots[slot["id"]].items()) for slot in slots),
            "Original roster changed between replays")
    semantic_report = _terminal(evidence, semantic_root, protocol, count=160)
    prior_report = _terminal(evidence, prior_root, prior, count=160)
    archive = evidence.read(attribution_report)
    require(archive["version"] == "spreadsheet-delivery-static-attribution-v1"
            and archive["status"] == "completed_static_attribution", "Reviewed static attribution required")
    reviewed = {(r["task_id"], r["repeat"]): r for r in archive["rows"]}
    require(len(reviewed) == len(archive["rows"]) == archive["selected_positions"]
            and set(reviewed) <= {(s["task_id"], s["repeat"]) for s in slots}, "Attribution roster differs")
    native_protocol, native_report, native_rows = _native_records(evidence, native_root, archive)
    require(native_protocol["parent"] == str(source), "Native replay uses another original source")
    records = []
    for slot in slots:
        key = slot["id"]
        semantic = evidence.read(semantic_root / "positions" / (key + ".json"))
        previous = evidence.read(prior_root / "positions" / (key + ".json"))
        require(semantic["record_hash"] == semantic_report["result_hashes"][key]
                and semantic["protocol_hash"] == protocol["record_hash"] and semantic["slot_id"] == key
                and previous["record_hash"] == prior_report["result_hashes"][key] == slot["previous_result_hash"]
                and previous["protocol_hash"] == prior["record_hash"] and previous["slot_id"] == key
                and previous["status"] == semantic["previous_status"] == slot["previous_status"]
                and semantic["old_status"] == previous["old_status"] == slot["old_status"], "Semantic position binding differs")
        prediction, call, code = _prediction(evidence, slot)
        old = evidence.read(source / "host_only/scores" / (key + ".json"))
        require(old["record_hash"] == slot["old_score_hash"] and old["prediction_hash"] == prediction["record_hash"]
                and old["task_id"] == slot["task_id"] and old["repeat"] == slot["repeat"]
                and old["status"] == slot["old_status"], "Historical score binding differs")
        native = native_rows.get(key)
        identity = {"task_id": slot["task_id"], "repeat": slot["repeat"], "prediction_hash": prediction["record_hash"],
                    "original_call_record_hash": call["record_hash"], "code_sha256": _sha(code.encode()) if code is not None else None,
                    "diagnostic_record_hash": native["record_hash"] if native else prediction["record_hash"] if code is not None else None}
        cases, artifacts = _original_delivery(slot, prediction)
        delivery = "delivered" if len(artifacts) == len(slot["references"]) else "partial" if artifacts else "undelivered"
        require(semantic["delivery_status"] == delivery, "Semantic replay changed original delivery state")
        attribution = reviewed.get((slot["task_id"], slot["repeat"]))
        observation = None
        if attribution is not None:
            require(native is not None and all(attribution[k] == identity[k] for k in identity), "Reviewed attribution identity differs")
            observation = _observed_native(native, identity, slot, prediction)
        elif delivery == "delivered":
            observation = {"identity": identity, "kind": "native_execution", "status": "delivered", "completed": True,
                           "cleanup_confirmed": True, "generated_lines": [], "exception_type": None,
                           "expected_artifacts": len(slot["references"]), "artifact_sha256s": artifacts}
        elif code is None:
            receipt = call["receipt"]
            observation = {"identity": identity, "kind": "model_call", "closed": True,
                           "http_status": receipt["status"], "stream_complete": receipt["stream_complete"],
                           "finish_reason": receipt["finish_reason"],
                           # The client records a closed length response as a
                           # content error. The axis assessor still requires
                           # HTTP 200 + complete stream + length/max_tokens.
                           "transport_error": receipt["error_type"] not in {None, "truncated_content"}}
        elif native and native["result"]["status"] == "invalid_program" and fenced_root:
            item = native["identity"]["item"]
            require(item["prediction_hash"] == identity["prediction_hash"] and item["code_sha256"] == identity["code_sha256"]
                    and item["score_hash"] == slot["old_score_hash"], "Original compile diagnostic identity differs")
            observation, attribution = _extractor_evidence(evidence, fenced_root, slot, identity, call, native)
        score = {"status": semantic["status"], "score": None if semantic["status"] == "unknown" else float(semantic["status"] == "pass"),
                 "source_record_hash": semantic["record_hash"], "reason": "unchanged_frozen_semantic_replay_status"}
        assessment = delivery_outcomes.assess_delivery_outcome(identity=identity, semantic_score=score,
                                                              observation=observation, attribution=attribution)
        end_to_end = semantic["status"]
        if end_to_end == "unknown" and assessment["delivery"]["outcome"] in POLICY["unknown_semantics_count_as_failure_only_for"]:
            end_to_end = "fail"
        records.append(seal({"version": VERSION, "slot_id": key, "task_id": slot["task_id"], "repeat": slot["repeat"],
            "semantic_record_hash": semantic["record_hash"], "previous_record_hash": previous["record_hash"],
            "original_score_hash": old["record_hash"], "original_delivery_status": delivery,
            "assessment": assessment, "end_to_end_status": end_to_end, "policy_version": POLICY["version"],
            "model_api_calls": 0, "container_calls": 0, "historical_scores_replaced": False}))
    require(Counter(r["assessment"]["semantic_score"]["status"] for r in records) == semantic_report["counts"],
            "Semantic denominator or counts changed")
    evidence.recheck()
    frozen = seal({"version": VERSION, "root": str(root), "policy": POLICY,
        "semantic_protocol_hash": protocol["record_hash"], "semantic_report_hash": semantic_report["record_hash"],
        "prior_protocol_hash": prior["record_hash"], "prior_report_hash": prior_report["record_hash"],
        "attribution_report_hash": archive["record_hash"], "native_report_hash": native_report["record_hash"],
        "sources": {str(safe_path(p)): _sha(Path(p).read_bytes()) for p in (__file__, delivery_outcomes.__file__, code_delivery.__file__, backends.__file__)},
        "inventory": evidence.inventory, "positions": 160, "independent_tasks": 80,
        "model_api_calls": 0, "container_calls": 0, "historical_scores_replaced": False, "feedback_allowed": False})
    report = seal({"version": VERSION, "status": "completed", "protocol_hash": frozen["record_hash"],
        "positions": 160, "independent_tasks": 80, "policy": POLICY,
        "semantic_counts": dict(Counter(r["assessment"]["semantic_score"]["status"] for r in records)),
        "end_to_end_counts": dict(Counter(r["end_to_end_status"] for r in records)),
        "original_delivery_counts": dict(Counter(r["original_delivery_status"] for r in records)),
        "delivery_outcomes": dict(Counter(r["assessment"]["delivery"]["outcome"] for r in records)),
        "semantic_to_end_to_end": dict(Counter(r["assessment"]["semantic_score"]["status"] + "->" + r["end_to_end_status"] for r in records)),
        "semantic_report_hash": semantic_report["record_hash"], "attribution_report_hash": archive["record_hash"],
        "native_report_hash": native_report["record_hash"], "result_hashes": {r["slot_id"]: r["record_hash"] for r in records},
        "undelivered_rows": [{"task_id": r["task_id"], "repeat": r["repeat"], "prediction_hash": r["assessment"]["identity"]["prediction_hash"],
            "semantic_status": r["assessment"]["semantic_score"]["status"], "delivery_outcome": r["assessment"]["delivery"]["outcome"],
            "attribution": r["assessment"]["attribution"]["category"], "end_to_end_status": r["end_to_end_status"],
            "record_hash": r["record_hash"]} for r in records if r["original_delivery_status"] != "delivered"],
        "evidence_kind": "retrospective_frozen_model_output_delivery_audit", "new_model_api_calls": 0, "new_container_calls": 0,
        "historical_scores_replaced": False, "semantic_scores_changed": False, "answers_modified": False,
        "feedback_allowed": False, "is_method_effect": False,
        "limits": ["This new retrospective end-to-end policy was not preregistered before the original model calls.",
                   "Compatibility unknowns, contract ambiguity and extractor defects are not automatically model failures.",
                   "Recovered extraction artifacts are evidence about the extractor only; original predictions remain the evaluated delivery."]})
    root.mkdir(parents=True, mode=0o700)
    write_json(root / "protocol.json", frozen)
    for row in records:
        write_json(root / "positions" / (row["slot_id"] + ".json"), row)
    write_json(root / "report.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("semantic-replay", "prior-replay", "native-replay", "attribution-report", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--fenced-replay")
    result = build(**vars(parser.parse_args(argv)))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
