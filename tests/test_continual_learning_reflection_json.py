"""Offline strict-parser controls, never natural learning/effect evidence."""
import hashlib
import json
from copy import deepcopy

import pytest

from skillopt.continual_eval.core import read_json
from skillopt.continual_learning.contracts import manifest
from skillopt.continual_learning.ledger import LearningPending, Ledger
from skillopt.continual_learning.recovery import POLICY as RECOVERY_POLICY
from skillopt.continual_learning.recovery import VERSION
from skillopt.continual_learning.reflection_json import (
    POLICY,
    NativeJSONError,
    prepare_native_json,
    strict_native_object,
)
from skillopt.continual_learning.skillopt import _NativeBridge, _transport, run_stage
from skillopt.validator_pilot.api import digest
from tests.test_continual_learning_domains import API, evaluate, setup


def v4_setup(*, natural=False):
    _, panel, args = setup(natural=natural)
    args["model"]["transport"]["stream_wall_seconds"] = 3600
    return manifest(panel, **{**args, "version": VERSION, "recovery_policy": deepcopy(RECOVERY_POLICY)}), panel


def assert_only_audited_insertions(raw, body, audit):
    original = raw.encode()
    start, end = audit["body_start_byte"], audit["body_end_byte"]
    offsets = set(audit["insert_backslash_before_response_byte_offsets"])
    reconstructed = b"".join((b"\\" if index in offsets else b"") + original[index:index + 1]
                             for index in range(start, end))
    assert body.encode() == reconstructed
    assert audit["response_sha256"] == hashlib.sha256(original).hexdigest()
    assert audit["delivered_body_sha256"] == hashlib.sha256(body.encode()).hexdigest()


@pytest.mark.parametrize("suffix", list("-_dDsSwW.()[]{}:;,$%=+!?xX0Ncé"))
def test_only_invalid_escape_is_preserved_as_literal_backslash(suffix):
    raw = '{"content":"中文\\' + suffix + ' end","nested":{"keep":[true,null,3,1.25]}}'
    body, audit = prepare_native_json(raw)
    assert strict_native_object(body) == {"content": "中文\\" + suffix + " end",
                                          "nested": {"keep": [True, None, 3, 1.25]}}
    assert audit["status"] == "repaired" and audit["repair_count"] == 1
    assert audit["version"] == POLICY
    assert_only_audited_insertions(raw, body, audit)


@pytest.mark.parametrize("prefix,suffix", [("", ""), (" \t\n", " \n"),
                                         ("```json\n", "\n```"), ("```\r\n", "\r\n```")])
def test_whole_object_envelope_and_exact_manual_repair(prefix, suffix):
    raw = prefix + r'{"patch":{"edits":[{"op":"append","content":"Use [a-z\-]"}]},"n":4}' + suffix
    body, audit = prepare_native_json(raw)
    assert strict_native_object(body) == {"patch": {"edits": [{"op": "append", "content": r"Use [a-z\-]"}]}, "n": 4}
    assert body == raw[len(prefix):len(raw) - len(suffix) if suffix else None].replace(r"\-", r"\\-")
    assert_only_audited_insertions(raw, body, audit)


def test_all_valid_escapes_and_nested_values_are_unchanged():
    raw = r'{"s":"\"\\\/\b\f\n\r\t\u0041\ud83d\ude80","n":-2.5e3,"v":[false,null,{},[]]}'
    body, audit = prepare_native_json(raw)
    assert body == raw and strict_native_object(body) == json.loads(raw)
    assert audit["status"] == "strict" and audit["repair_count"] == 0
    assert_only_audited_insertions(raw, body, audit)


def test_even_and_odd_backslash_runs_and_escaped_quotes():
    expected = {"even": r"\\-", "odd": r"\\-", "quote": 'a"b\\-c', "key\\-": "value"}
    strict = json.dumps(expected)
    raw = strict.replace(r"\\\\-", r"\\\-", 1).replace(r"b\\-", r"b\-").replace(r"key\\-", r"key\-")
    body, audit = prepare_native_json(raw)
    assert strict_native_object(body) == expected
    assert audit["repair_count"] == 3
    assert_only_audited_insertions(raw, body, audit)


@pytest.mark.parametrize("raw", [
    r'{"x":"abc\-', r'{"x":"abc\-"', r'{"x":"abc\-",}', r'{x:"abc\-"}',
    "{'x': 'abc\\-'}", r'{"x":1}{"x":2}', r'[{"x":"abc\-"}]', 'null', '42',
    r'{"x":1,"x":2}', r'{"x":{"a":1,"\u0061":2}}', r'{"a\-":1,"a\\-":2}',
    r'{"x":"bad\u12"}', r'{"x":"bad\uXX12"}', r'{"x":"bad\u-123"}',
    r'{"x":"\ud800"}', r'{"x":"\udc00"}', r'{"x":NaN}', r'{"x":Infinity}',
    r'{"x":-Infinity}', r'{"x":1e999}', r'{"x":-1e999}', r'{"x":\-1}',
    '{"x":"line\\\nbreak"}', '{"x":"\x01"}',
    'Prose {"x":1}', '{"x":1} trailing prose', '```json\n{"x":1}',
    '```json\n{"x":1}\n```\n{"x":2}', 'Before\n```json\n{"x":1}\n```',
    '```python\n{"x":1}\n```', '```json\n{"x":1}\n```\nAfter',
])
def test_no_structural_repair_extraction_duplicate_or_nonfinite_acceptance(raw):
    with pytest.raises(NativeJSONError) as error:
        prepare_native_json(raw)
    audit = error.value.audit
    assert audit["status"] == "rejected"
    assert "delivered_body_sha256" not in audit
    assert audit["response_sha256"] == hashlib.sha256(raw.encode()).hexdigest()


@pytest.mark.parametrize("raw", [None, 1, True, {}, [], b'{"x":1}'])
def test_nontext_input_rejected(raw):
    with pytest.raises(NativeJSONError, match="response_text_required"):
        prepare_native_json(raw)


def test_strict_parser_itself_does_not_repair_or_unwrap():
    for raw in (r'{"x":"a\-"}', '```json\n{"x":1}\n```'):
        with pytest.raises(NativeJSONError):
            strict_native_object(raw)


def test_response_bound_and_metadata_only_audit(monkeypatch):
    monkeypatch.setattr("skillopt.continual_learning.reflection_json.MAX_RESPONSE_BYTES", 64)
    with pytest.raises(NativeJSONError, match="oversized"):
        prepare_native_json(json.dumps({"content": "x" * 64}))
    canary = "RESPONSE_CONTENT_MUST_NOT_ENTER_AUDIT"
    _, audit = prepare_native_json('{"content":"' + canary + r'\-"}')
    assert canary not in json.dumps(audit)


class ParserAPI(API):
    def __init__(self, raw, **kwargs):
        super().__init__(**kwargs)
        self.raw, self.receipts = raw, []

    def call(self, *args, **kwargs):
        receipt = super().call(*args, **kwargs)
        if not args[2].endswith("solver"):
            receipt["response"] = self.raw
        self.receipts.append(deepcopy(receipt))
        return receipt


REPAIRABLE = r'{"batch_size":2,"patch":{"reasoning":"Fixture only","edits":[{"op":"append","content":"Use the requested constant result; preserve [a-z\-]."}]}}'


def test_v4_real_native_stage_records_repair_without_touching_model_receipt(tmp_path, monkeypatch):
    # No optional json_repair dependency or old extract_json fallback may run.
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip
    def forbidden(_):
        raise AssertionError("Legacy permissive parser reached by v4")
    for module in (aggregate, reflect, clip):
        monkeypatch.setattr(module, "extract_json", forbidden)
    auth, panel = v4_setup()
    api = ParserAPI(REPAIRABLE)
    result = run_stage(auth, panel, tmp_path, fixture_api=api, fixture_evaluate=evaluate("searchqa"))
    assert result["status"] == "completed", result
    assert result["steps"][0]["gate_action"] == "accept_new_best"
    assert r"[a-z\-]" in result["candidate_skill"]
    assert len(api.calls) == 1  # Lexical handling is not another model attempt.
    audit = read_json(tmp_path / "native/0/parser_audits/0.json", sealed=True)
    call_file = next((tmp_path / "calls").glob("*.json"))
    call_bytes = call_file.read_bytes()
    receipt = read_json(call_file, sealed=True)["receipt"]
    assert receipt == api.receipts[0] and receipt["response"] == REPAIRABLE
    assert audit["repair_count"] == 1 and audit["status"] == "repaired"
    assert audit["manifest_hash"] == auth["record_hash"]
    assert audit["receipt_hash"] == digest(receipt)
    assert audit["request_hash"] == receipt["request_hash"]
    assert audit["call_intent_hash"] == call_file.stem
    assert "native/0/parser_audits/0.json" in result["artifacts"]
    replay = run_stage(auth, panel, tmp_path, fixture_api=api, fixture_evaluate=evaluate("searchqa"))
    assert replay == result and call_file.read_bytes() == call_bytes and len(api.calls) == 1
    assert all(module.extract_json is forbidden for module in (aggregate, reflect, clip))


@pytest.mark.parametrize("raw", [r'{"patch":{"edits":[]} ,"patch":{"edits":[]}}',
                                REPAIRABLE[:-1], r'{"patch":{"edits":[],"x":NaN}}'])
def test_v4_invalid_reply_retains_parent_and_audits_rejection(tmp_path, raw):
    auth, panel = v4_setup()
    api = ParserAPI(raw)
    result = run_stage(auth, panel, tmp_path, fixture_api=api, fixture_evaluate=evaluate("searchqa"))
    assert result["status"] == "pending" and result["candidate_skill"] == auth["parent_skill"]
    assert not result["steps"] and len(api.calls) == 1
    audit = read_json(tmp_path / "native/0/parser_audits/0.json", sealed=True)
    assert audit["status"] == "rejected" and "native/0/parser_audits/0.json" in result["artifacts"]


def test_v4_audit_tampering_blocks_completed_replay(tmp_path):
    auth, panel = v4_setup()
    api = ParserAPI(REPAIRABLE)
    assert run_stage(auth, panel, tmp_path, fixture_api=api, fixture_evaluate=evaluate("searchqa"))["status"] == "completed"
    (tmp_path / "native/0/parser_audits/0.json").write_text("{}")
    with pytest.raises(ValueError, match="evidence changed"):
        run_stage(auth, panel, tmp_path, fixture_api=api, fixture_evaluate=evaluate("searchqa"))
    assert len(api.calls) == 1


def test_legacy_bridge_and_parser_bindings_remain_unchanged(tmp_path):
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip
    auth, _, _ = setup()
    api = ParserAPI(REPAIRABLE)
    bridge = _NativeBridge(Ledger(tmp_path, auth, api), 0)
    modules = (aggregate, reflect, clip)
    parsers = [module.extract_json for module in modules]
    with _transport(bridge):
        response, _ = bridge.chat("system", "user", stage="analyst")
        assert response == REPAIRABLE
        assert [module.extract_json for module in modules] == parsers
    assert [module.extract_json for module in modules] == parsers
    assert not list(tmp_path.rglob("parser_audits"))


def test_v4_strict_parser_prevents_embedded_fence_reinterpretation_and_restores(tmp_path):
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip
    auth, _ = v4_setup()
    raw = json.dumps({"patch": {"reasoning": "```json 42```", "edits": []}})
    bridge = _NativeBridge(Ledger(tmp_path, auth, ParserAPI(raw)), 0, audit_root=tmp_path / "audit")
    modules = (aggregate, reflect, clip)
    before = [(module.chat_optimizer, module.extract_json) for module in modules]
    with pytest.raises(RuntimeError, match="fixture body"):
        with _transport(bridge):
            response, _ = bridge.chat("system", "user", stage="analyst")
            assert all(module.extract_json(response) == json.loads(raw) for module in modules)
            raise RuntimeError("fixture body")
    assert [(module.chat_optimizer, module.extract_json) for module in modules] == before


@pytest.mark.parametrize("stage", ["analyst", "merge", "ranking"])
def test_parser_failure_latches_all_native_stage_fallbacks(tmp_path, stage):
    auth, _ = v4_setup()
    api = ParserAPI(REPAIRABLE[:-1])
    bridge = _NativeBridge(Ledger(tmp_path, auth, api), 0, audit_root=tmp_path / "audit")
    with pytest.raises(LearningPending, match="json_rejected"):
        bridge.chat("system", "user", stage=stage)
    assert bridge.failure is not None
    with pytest.raises(LearningPending, match="earlier_native_optimizer_failure"):
        bridge.chat("system", "user", stage="ranking")
    assert len(api.calls) == 1


def test_v4_requires_explicit_parser_policy_and_audit_directory(tmp_path):
    auth, _ = v4_setup()
    with pytest.raises(ValueError, match="audit output"):
        _NativeBridge(Ledger(tmp_path, auth, API()), 0)
    wrong = deepcopy(auth)
    wrong["recovery_policy"]["reflection_parser"] = "permissive"
    with pytest.raises(ValueError, match="policy differs"):
        _NativeBridge(Ledger(tmp_path, wrong, API()), 0, audit_root=tmp_path / "audit")


def test_v4_client_options_are_forwarded(tmp_path, monkeypatch):
    auth, panel = v4_setup(natural=True)
    api = ParserAPI(REPAIRABLE, model="glm-5.3")
    seen = []
    def client(*args, **kwargs):
        seen.append(kwargs)
        return api
    monkeypatch.setattr("skillopt.continual_learning.skillopt.CachedAPI", client)
    result = run_stage(auth, panel, tmp_path, repo=tmp_path)
    assert result["status"] == "completed", result
    assert seen[0]["delivery_retry_policy"] == "closed_network_error_v1"
    assert seen[0]["stream_wall_seconds"] == 3600


def test_v4_repaired_content_does_not_relax_missing_usage_completion_guard(tmp_path):
    auth, panel = v4_setup()
    class MissingUsageAPI(ParserAPI):
        def call(self, *args, **kwargs):
            receipt = super().call(*args, **kwargs)
            receipt["usage"] = {}
            return receipt
    api = MissingUsageAPI(REPAIRABLE)
    result = run_stage(auth, panel, tmp_path, fixture_api=api, fixture_evaluate=evaluate("searchqa"))
    assert result["status"] == "pending" and result["candidate_skill"] == auth["parent_skill"]
    assert result["reason"] == "incomplete_usage"
    assert not result["costs"]["usage_complete"] and result["costs"]["missing_usage_calls"] == 1
    assert read_json(tmp_path / "native/0/parser_audits/0.json", sealed=True)["status"] == "repaired"
    assert len(api.calls) == 1
