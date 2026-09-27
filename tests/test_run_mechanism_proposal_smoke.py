"""Script integration with fabricated durable receipts: no real API or solver.

The production command intentionally labels real API + fixture feedback. This
test replaces its API; the mock service and receipts explicitly remain fixtures.
It does not exercise model compliance, semantic support, or learning effects.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_mechanism_proposal_smoke as smoke
from skillopt.coevolution_v5.core import verify
from skillopt.skill_validation.mechanism_learning import CALL_KIND, STRATEGIES
from skillopt.validator_pilot import api as provider_api
from skillopt.validator_pilot.api import digest, write_immutable_json


def _proposal(user):
    """Handwritten schema fixture, never a learned or semantically certified rule."""
    payload = json.loads(user)
    evidence = payload["evidence_catalog"][0]["id"]
    rule = {"id": "fixture-rule", "mechanism": "Fixture mechanism",
            "procedure": ["Inspect the explicitly required input state."],
            "when": "An unchanged input is explicitly required.", "exceptions": [],
            "scope": {"required_obligation_kinds": ["input_preservation"],
                      "forbidden_obligation_kinds": []}, "evidence_ids": [evidence]}
    return json.dumps({"parent_hash": payload["parent_hash"], "edits": [{
        "operation": "add", "rule_id": rule["id"], "rule": rule, "evidence_ids": [evidence],
        "reason": "Handwritten format fixture; does not establish semantic evidence support."}]})


@pytest.fixture
def harness(monkeypatch, tmp_path):
    state = SimpleNamespace(instances=[], answer=_proposal, ok=True, interrupted=False,
                            tamper=None, durable=True)

    def deny_external(*args, **kwargs):
        raise AssertionError("This offline test must not read credentials or create an HTTP client")

    monkeypatch.setattr(provider_api, "_configuration", deny_external)
    monkeypatch.setattr(provider_api.httpx, "Client", deny_external)

    class FixtureAPI:
        def __init__(self, repo, root, **options):
            self.root, self.repo, self.options = Path(root), Path(repo), options
            self.model = "fixture-no-model"
            self.service = {"fixture": True, "provider": "FIXTURE", "real_model": False}
            self.requests, self.fresh_requests, self.jobs = [], [], []
            self.closed = False
            state.instances.append(self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True
            return False

        def parallel(self, jobs, fn, label):
            self.jobs = list(jobs)
            return [fn(job) for job in self.jobs]

        def call(self, system, user, kind, key, *, max_tokens, repeat):
            request = {"model": self.model, "system": system, "user": user, "kind": kind,
                       "key": key, "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
            self.requests.append(deepcopy(request))
            path = self.root / "calls" / (digest(request) + ".json")
            if path.exists():
                return json.loads(path.read_text())
            self.fresh_requests.append(deepcopy(request))
            if state.interrupted:
                raise RuntimeError("Fixture interruption after reservation, before durable receipt")
            answer = state.answer(user) if callable(state.answer) else state.answer
            record = {"request": request, "request_hash": digest(request), "ok": state.ok,
                      "response": answer, "fixture_only": True, "http_attempt_count": 1,
                      "finish_reason": "stop", "stream_complete": True,
                      "usage": {"prompt_tokens": 11, "completion_tokens": 7},
                      "attempts": [{"attempt": 1, "ok": state.ok, "fixture_only": True}]}
            if state.tamper == "wrong_request":
                record["request"]["repeat"] += 1
                record["request_hash"] = digest(record["request"])
            elif state.tamper == "missing_hash":
                del record["request_hash"]
            if state.durable:
                write_immutable_json(path, record)
            return record

    monkeypatch.setattr(smoke, "CachedAPI", FixtureAPI)
    repo, output = tmp_path / "repo", tmp_path / "smoke"
    source = repo / "skillopt" / "skill_validation" / "fixture_source.py"
    source.parent.mkdir(parents=True)
    source.write_text("# Handwritten source-hash fixture, never executed.\n")

    def invoke(**options):
        return smoke.run(repo, output, **options)

    return SimpleNamespace(invoke=invoke, state=state, repo=repo, output=output, source=source)


def _read(path):
    return verify(json.loads(path.read_text()))


def test_same_cold_parent_public_feedback_controls_and_durable_complete_receipts(harness):
    result = harness.invoke(proxy="http://127.0.0.1:12345")
    api = harness.state.instances[-1]
    verify(result)
    assert api.closed
    assert api.options == {"workers": 2, "provider": "bigmodel", "stream": True,
                           "reasoning_effort": "low", "proxy": "http://127.0.0.1:12345"}
    assert api.jobs == [(strategy, repeat) for repeat in range(3) for strategy in STRATEGIES]
    assert len(api.requests) == len(api.fresh_requests) == len(result["rows"]) == 6
    assert len({r["user"] for r in api.requests}) == 1
    assert len({r["system"] for r in api.requests}) == 2
    assert len({r["key"] for r in api.requests}) == 6
    payload = json.loads(api.requests[0]["user"])
    assert payload["parent_skill"] == "" and payload["parent_rules"] == []
    assert payload["evidence_catalog"] and payload["feedback"]["paired_development"]
    assert all(r["kind"] == CALL_KIND and r["max_tokens"] == 2048 for r in api.requests)
    for request in api.requests:
        assert all(hidden not in request["user"] for hidden in
                   ("hidden_audit", "host_only", "fixture-rule-project", "mechanism-api-fixture-only"))
    protocol = _read(harness.output / "protocol.json")
    feedback = _read(harness.output / "fixture_feedback.json")
    assert protocol["parent"]["rules"] == []
    assert protocol["feedback_hash"] == feedback["record_hash"]
    assert protocol["source_hashes"] and protocol["script_hash"]
    assert protocol["service"]["fixture"] is True
    assert result["protocol_hash"] == protocol["record_hash"]
    assert result["provenance"] == "engineering_fixture_feedback_not_natural_experiment"
    assert not protocol["method_effect_evaluated"] and not protocol["deployment_authorized"]
    assert not result["method_effect_evaluated"] and not result["deployment_authorized"]
    assert "syntax only" in result["warning"]
    for row in result["rows"]:
        update = _read(harness.output / "updates" / f"{row['strategy']}-{row['repeat']}.json")
        receipt = update["api_receipt"]
        cached = json.loads((harness.output / "api" / "calls" / (row["request_hash"] + ".json")).read_text())
        assert receipt == cached
        assert receipt["request_hash"] == digest(receipt["request"])
        assert update["api_receipt_hash"] == digest(receipt)
        assert update["fixture_only"] and receipt["fixture_only"]
        assert row["status"] == update["status"] == "candidate"
        assert row["candidate"] == update["update"]["candidate"]
        assert not row["semantic_support_verified"] and not update["deployment_authorized"]
        assert update["confirmation_required"] and not update["retry_authorized"]
    accounting = result["accounting"]
    assert accounting["reserved_logical_requests"] == accounting["terminal_logical_requests"] == 6
    assert accounting["request_limit"] == accounting["http_attempts"] == 6
    assert accounting["terminal_reported_tokens"] == 6 * 18
    assert accounting["terminal_failures"] == 0
    assert _read(harness.output / "summary.json") == result


def test_replay_never_resamples_or_overwrites_and_keeps_exact_bytes(harness):
    first = harness.invoke(repeats=2)
    before = {str(p.relative_to(harness.output)): p.read_bytes()
              for p in harness.output.rglob("*.json")}
    harness.state.answer = "An alternative later reply must never replace frozen responses."
    second = harness.invoke(repeats=2)
    assert first == second
    assert harness.state.instances[-1].fresh_requests == []
    assert before == {str(p.relative_to(harness.output)): p.read_bytes()
                      for p in harness.output.rglob("*.json")}


@pytest.mark.parametrize("answer,ok,status", [
    ("NO_UPDATE", True, "no_update"), ("{}", True, "invalid"),
    (None, True, "invalid"), ("NO_UPDATE", False, "api_failure"),
])
def test_non_candidates_remain_visible_terminal_outcomes_without_resampling(harness, answer, ok, status):
    harness.state.answer, harness.state.ok = answer, ok
    result = harness.invoke(repeats=1)
    assert [r["status"] for r in result["rows"]] == [status, status]
    assert all(r["candidate"] is None for r in result["rows"])
    assert result["accounting"]["terminal_failures"] == (0 if ok else 2)
    assert len(harness.state.instances[-1].fresh_requests) == 2
    assert harness.invoke(repeats=1) == result
    assert harness.state.instances[-1].fresh_requests == []


@pytest.mark.parametrize("envelope,status", [
    ("%s", "candidate"), ("```json\n%s\n```", "candidate"),
    ("Explanation.\n```json\n%s\n```", "invalid"),
    ("```json\n%s\n```\nTrailing text.", "invalid"),
    ("```json\n%s\n```\n```json\n{}\n```", "invalid"),
])
def test_only_complete_json_envelope_not_prose_extraction(harness, envelope, status):
    harness.state.answer = lambda user: envelope % _proposal(user)
    result = harness.invoke(repeats=1)
    assert [r["status"] for r in result["rows"]] == [status, status]
    assert len(harness.state.instances[-1].fresh_requests) == 2
    for update_file in (harness.output / "updates").glob("*.json"):
        update = _read(update_file)
        assert update["api_receipt"]["response"] == harness.state.answer(update["request"]["user"])
        assert not update["retry_authorized"]


def test_response_code_is_never_executed_or_repaired(harness):
    marker = harness.output.parent / "must-not-exist"
    harness.state.answer = f"__import__('pathlib').Path({str(marker)!r}).write_text('unsafe')"
    result = harness.invoke(repeats=1)
    assert all(row["status"] == "invalid" for row in result["rows"])
    assert not marker.exists()


@pytest.mark.parametrize("malformation", ["duplicate_key", "wrong_parent", "missing_edit_evidence", "extra_rule_field"])
def test_complete_json_still_enforces_identity_evidence_and_exact_schema(harness, malformation):
    def response(user):
        value = json.loads(_proposal(user))
        if malformation == "duplicate_key":
            return '{"parent_hash":"' + value["parent_hash"] + '",' + _proposal(user)[1:]
        if malformation == "wrong_parent":
            value["parent_hash"] = "0" * 64
        elif malformation == "missing_edit_evidence":
            del value["edits"][0]["evidence_ids"]
        else:
            value["edits"][0]["rule"]["deployment_authorized"] = True
        return json.dumps(value)
    harness.state.answer = response
    result = harness.invoke(repeats=1)
    assert all(row["status"] == "invalid" and row["candidate"] is None for row in result["rows"])
    assert len(harness.state.instances[-1].fresh_requests) == 2
    assert not result["deployment_authorized"]


@pytest.mark.parametrize("repeats", [True, False, 0, -1, 4, 1.0, "1", None])
def test_invalid_repeat_budget_rejected_before_api_or_output(harness, repeats):
    with pytest.raises(ValueError, match="Smoke repeats"):
        harness.invoke(repeats=repeats)
    assert not harness.state.instances and not harness.output.exists()


@pytest.mark.parametrize("tamper", ["wrong_request", "missing_hash", "missing_durable_receipt"])
def test_invalid_receipt_is_integrity_failure_not_no_update_or_retry(harness, tamper):
    harness.state.tamper = tamper
    harness.state.durable = tamper != "missing_durable_receipt"
    with pytest.raises(ValueError, match="Provider request binding changed|Missing durable model receipt"):
        harness.invoke(repeats=1)
    assert len(harness.state.instances[-1].fresh_requests) == 1
    assert not (harness.output / "summary.json").exists()
    assert not (harness.output / "updates").exists()
    assert len(list((harness.output / "budget" / "intents").glob("*.json"))) == 1


def test_interrupted_intent_cannot_be_automatically_reissued_on_resume(harness):
    harness.state.interrupted = True
    with pytest.raises(RuntimeError, match="Fixture interruption"):
        harness.invoke(repeats=1)
    assert len(harness.state.instances[-1].fresh_requests) == 1
    harness.state.interrupted = False
    with pytest.raises(ValueError, match="Interrupted API request retained"):
        harness.invoke(repeats=1)
    assert harness.state.instances[-1].requests == []
    assert not (harness.output / "summary.json").exists()


@pytest.mark.parametrize("change", ["repeats", "source_hash"])
def test_frozen_protocol_cannot_change_in_place(harness, change):
    harness.invoke(repeats=1)
    old_protocol = (harness.output / "protocol.json").read_bytes()
    old_summary = (harness.output / "summary.json").read_bytes()
    repeats = 2 if change == "repeats" else 1
    if change == "source_hash":
        harness.source.write_text("# Changed source fixture; historical run must remain frozen.\n")
    with pytest.raises(ValueError, match="Immutable artifact differs"):
        harness.invoke(repeats=repeats)
    assert harness.state.instances[-1].requests == []
    assert (harness.output / "protocol.json").read_bytes() == old_protocol
    assert (harness.output / "summary.json").read_bytes() == old_summary


def test_concurrent_same_output_serializes_and_reuses_single_request_set(harness):
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: harness.invoke(repeats=1), range(2)))
    assert results[0] == results[1]
    assert len(harness.state.instances) == 2
    assert sum(len(api.fresh_requests) for api in harness.state.instances) == 2
    assert all(api.closed for api in harness.state.instances)


def test_cli_prints_only_accounting_statuses_and_non_effect_flag(harness, monkeypatch, capsys):
    monkeypatch.chdir(harness.repo)
    monkeypatch.setattr("sys.argv", ["run_mechanism_proposal_smoke", "--output", str(harness.output),
                                     "--repeats", "1"])
    smoke.main()
    printed = json.loads(capsys.readouterr().out)
    assert set(printed) == {"accounting", "statuses", "method_effect_evaluated"}
    assert printed["statuses"] == ["candidate", "candidate"]
    assert printed["method_effect_evaluated"] is False
    assert printed["accounting"]["terminal_logical_requests"] == 2
