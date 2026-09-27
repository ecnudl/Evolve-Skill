"""Only fake model receipts/documents and scripted execution; never network."""
import hashlib
import json

import pytest

from scripts import run_probe_fact_smoke as smoke
from skillopt.validator_pilot.api import digest, write_immutable_json
from tests.test_skill_validation_admissibility_study import Executor

URL = "https://docs.python.org/3.11/library/stdtypes.html#str.split"
DOC = ("Fixture documentation only: split(None) splits Unicode whitespace including U+00A0. "
       "An explicit space separator only splits U+0020 and leaves U+00A0 inside a token.")


class Fetcher:
    identity = {"kind": "fixture-document-transport", "no_network": True}

    def __init__(self):
        self.calls = []

    def __call__(self, urls, root):
        assert urls == [URL]
        self.calls.append((urls, root))
        return [{"source_id": "fixture-doc", "url": URL, "status": "available", "text": DOC,
            "text_sha256": hashlib.sha256(DOC.encode()).hexdigest(),
            "retrieved_text_sha256": hashlib.sha256(DOC.encode()).hexdigest(),
            "retrieved_utc": "fixture-no-network", "source_version": "Python 3.11"}]


@pytest.fixture
def provider(monkeypatch):
    state = {"fresh_calls": 0, "prompts": [], "plan": "investigate", "bad_review": False}
    class API:
        def __init__(self, repo, root, **kwargs):
            assert kwargs["workers"] == 1 and kwargs["provider"] == "bigmodel"
            self.root, self.model, self.service = root, "fixture-model", {"provider": "fixture-only"}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def call(self, system, user, kind, key, *, max_tokens, repeat):
            request = {"model": self.model, "system": system, "user": user, "kind": kind,
                "key": key, "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
            request_hash = digest(request)
            path = self.root / "calls" / (request_hash + ".json")
            if path.exists():
                return json.loads(path.read_text())
            state["fresh_calls"] += 1
            payload = json.loads(user)
            state["prompts"].append(payload)
            if kind == "probe-fact-plan":
                response = {"status": state["plan"], "urls": [URL] if state["plan"] == "investigate" else [],
                    "reason": "Scripted fixture fact plan."}
            elif kind == "probe-fact-select":
                source = payload["sources"][0]
                response = {"status": "evidence_selected", "citations": [{"source_id": source["source_id"],
                    "span_id": source["evidence_spans"][0]["id"]}], "reason": "One fixture evidence fragment.",
                    "uncertainty": "Fixture selection is not independent validation."}
            elif kind == "pre-execution-admissibility":
                near = "with the explicit separator U+0020" in payload["task"]
                response = {"checks": [{"probe_id": check["probe_id"],
                    "decision": "abstain" if near else "keep",
                    "reason_code": "expected_inconsistent" if near else
                        "document_supported" if payload["sources"] else "contract_supported",
                    "reason": "Scripted fixture review.", "fact_question": ""} for check in payload["checks"]]}
                if state["bad_review"]:
                    response = "{malformed"
            else:
                raise AssertionError("Unexpected paid stage " + kind)
            record = {"request": request, "request_hash": request_hash, "ok": True,
                "response": response if type(response) is str else json.dumps(response),
                "usage": {"prompt_tokens": 10, "completion_tokens": 10}, "http_attempt_count": 1}
            write_immutable_json(path, record)
            return record
    monkeypatch.setattr(smoke, "CachedAPI", API)
    return state


def run(tmp_path, provider, *, executor=None, fetcher=None):
    executor = executor or Executor([{"actual": ["a", "b"]}, {"actual": ["a\u00a0b"]}])
    fetcher = fetcher or Fetcher()
    output = tmp_path / "outputs/skill_validation/fact-smoke"
    result = smoke.run(tmp_path, output, executor, fetcher)
    return result, executor, fetcher, output


def test_live_shape_pipeline_has_six_call_cap_and_no_skill_claim(tmp_path, provider):
    result, executor, fetcher, output = run(tmp_path, provider)
    assert provider["fresh_calls"] == result["cost"]["terminal_logical_requests"] == 6
    assert len(fetcher.calls) == 2 and len(executor.calls) == 2
    normal, near = result["cases"]
    assert normal["review_decisions"][0]["decision"] == "keep"
    assert [r["probe_status"] for r in normal["executions"]] == ["match", "mismatch"]
    assert near["review_decisions"][0]["decision"] == "abstain"
    assert all(r["probe_status"] == "not_executed" for r in near["executions"])
    assert all(case["question_origin"] == "caller_declared_not_model_discovered" for case in result["cases"])
    assert result["provenance"] == "handwritten_engineering_fixture"
    assert result["gate"] == "not_applicable_fixture_only"
    assert not any(result[key] for key in ("natural_method_efficacy", "research_incremental_effect_established",
        "deployment_authorized", "feedback_authorized", "hidden_oracle_access", "final_access"))
    assert result["new_solver_calls"] == result["skill_update_calls"] == 0
    assert (output / "source_snapshot.json").is_file()
    assert smoke.run(tmp_path, output, executor, fetcher) == result
    assert provider["fresh_calls"] == 6 and len(fetcher.calls) == 2 and len(executor.calls) == 2


def test_no_update_is_normal_and_public_review_is_not_research_success(tmp_path, provider):
    provider["plan"] = "no_update"
    result, executor, fetcher, _ = run(tmp_path, provider)
    assert provider["fresh_calls"] == 4 and not fetcher.calls
    assert all(case["fact_status"] == "no_update" and not case["review_had_research_evidence"]
               for case in result["cases"])
    assert len(executor.calls) == 2
    assert result["research_incremental_effect_established"] is False


def test_invalid_review_is_not_execution_or_admissibility_success(tmp_path, provider):
    provider["bad_review"] = True
    result, executor, _, _ = run(tmp_path, provider)
    assert not executor.calls
    assert all(case["review_status"] == "format_invalid" for case in result["cases"])
    assert all(row["probe_status"] == "not_executed" for case in result["cases"] for row in case["executions"])


def test_view_has_neither_implementations_nor_human_answer_labels(tmp_path, provider):
    run(tmp_path, provider)
    view = json.dumps(provider["prompts"])
    assert all(token not in view for token in ("def split_tokens", "intended_conforming", "intended_counterexample",
        "host_fixture_expectation", "source_ref", "unassigned", "canonical_solution", "audit_status"))
    assert all(payload["probe"]["expected"] == ["a", "b"] for payload in provider["prompts"] if "probe" in payload)


def test_configuration_change_stops_before_new_paid_request(tmp_path, provider):
    _, executor, _, output = run(tmp_path, provider)
    fetcher = Fetcher()
    fetcher.identity = {**fetcher.identity, "changed": True}
    with pytest.raises(ValueError, match="Immutable"):
        smoke.run(tmp_path, output, executor, fetcher)
    assert provider["fresh_calls"] == 6 and not fetcher.calls


def test_execution_failure_prevents_second_problem_calls_and_replay_resampling(tmp_path, provider):
    executor, fetcher = Executor(crash=True), Fetcher()
    output = tmp_path / "outputs/skill_validation/fact-smoke"
    with pytest.raises(ValueError, match="Execution infrastructure"):
        smoke.run(tmp_path, output, executor, fetcher)
    assert provider["fresh_calls"] == 3 and len(executor.calls) == 1
    with pytest.raises(ValueError, match="Execution infrastructure"):
        smoke.run(tmp_path, output, executor, fetcher)
    assert provider["fresh_calls"] == 3 and len(executor.calls) == 1
    assert not (output / "results.json").exists()


def test_fixture_expected_values_are_not_rewritten_for_near_miss():
    normal, near = smoke.fixtures()
    assert normal["task"].content_hash != near["task"].content_hash
    assert normal["proposal"]["probes"][0]["expected"] == near["proposal"]["probes"][0]["expected"]
    assert normal["host_fixture_expectation"] == "keep" and near["host_fixture_expectation"] == "abstain"
    assert all(a.provenance_kind == "fixture" and a.condition == "unassigned"
               for case in (normal, near) for _, a in case["artifacts"])


def test_missing_provenance_interface_stops_before_any_model_or_transport(tmp_path, monkeypatch, provider):
    monkeypatch.setattr(smoke, "resolve_gap", lambda *args, **kwargs: None)
    executor, fetcher = Executor(), Fetcher()
    with pytest.raises(ValueError, match="explicit caller_declared_fixture_gap"):
        smoke.run(tmp_path, tmp_path / "outputs/skill_validation/unsupported", executor, fetcher)
    assert provider["fresh_calls"] == 0 and not executor.calls and not fetcher.calls
