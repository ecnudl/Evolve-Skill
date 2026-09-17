"""Offline smoke-protocol tests; every API/document operation is mocked."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import smoke_coevolution_v4_research as s


def put(path, value, v3=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if v3:
        value = {**value, "record_sha256": s.digest(value)}
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    files = {"api.py": "from policy import plan\n", "policy.py": "def visit(node):\n    if node in done:\n        return\n"}
    prompt = "A dirty prerequisite makes every reachable dependent dirty. Preserve the legacy wrapper."
    public = {"id": s.EXPECTED_TASK, "prompt": prompt, "files": {"policy.py": "starter"},
              "editable_paths": list(files), "input_domain": {"type": "object"}, "public_cases": [],
              "entry_module": "api", "entry_function": "solve"}
    candidate_hash, contract_hash = s.digest(files), s.digest(prompt)
    monkeypatch.setattr(s, "EXPECTED_CANDIDATE", candidate_hash)
    monkeypatch.setattr(s, "EXPECTED_CONTRACT", contract_hash)
    target_name = "1" * 64
    monkeypatch.setattr(s, "SOURCE_TARGET", "targets/" + target_name + ".json")
    request = {"model": "glm-5.3", "kind": "repo_target", "key": target_name,
               "user": json.dumps({"task": public, "skill": "untrusted historical guidance"})}
    api_hash = s.digest(request)
    monkeypatch.setattr(s, "SOURCE_API", "api/calls/" + api_hash + ".json")
    call = {"request": request, "request_hash": api_hash, "ok": True, "response": "synthetic raw code"}
    target = {"id": s.EXPECTED_TASK, "phase": "learn1", "stage": "r1", "stream": 0, "repeat": 0,
              "target_ok": True, "files": files, "request_hash": api_hash, "response": call["response"]}
    ref = {"ok": True, "exception": None, "input_unchanged": True,
           "value": {"result": ["d", "b", "c", "a"], "api_version": 1}}
    actual = {**ref, "value": {"result": ["d", "b", "a"], "api_version": 1}}
    receipt = {"task_id": s.EXPECTED_TASK, "phase": "learn1", "candidate_hash": candidate_hash,
               "contract_hash": contract_hash, "status": "verified_mismatch", "reason": "return_value_difference",
               "input": deepcopy(s.EXPECTED_INPUT), "input_preserved": True, "candidate_path": "policy.py",
               "candidate_quote": "if node in done:\n        return", "clause_quote": prompt,
               "reference_observation": ref, "candidate_observation": actual}
    receipt_hash = s.digest(receipt)
    monkeypatch.setattr(s, "EXPECTED_RECEIPT", receipt_hash)
    receipt["receipt_hash"] = receipt_hash
    claim = {"artifact_hash": candidate_hash, "receipts": [receipt]}
    old = repo / s.SOURCE_RUN
    put(old / s.SOURCE_CLAIM, claim, True)
    put(old / s.SOURCE_TARGET, target, True)
    put(old / s.SOURCE_API, call)
    monkeypatch.setattr(s, "SOURCES", ("source.py", "docs/protocol.md"))
    (repo / "source.py").write_text("# immutable synthetic source\n")
    (repo / "docs").mkdir()
    (repo / "docs/protocol.md").write_text("Synthetic frozen test protocol.\n")
    output = repo / "outputs/coevolution_v4_research_smoke/test"
    return {"repo": repo, "output": output, "old": old, "claim": claim, "target": target, "call": call}


def test_source_reads_only_three_pinned_development_files(fixture):
    packet, provenance = s.load_development_packet(fixture["repo"])
    assert packet["split"] == "development" and packet["source_phase"] == "learn1"
    assert packet["classification"] == "semantic" and packet["research_trigger"]
    assert packet["failed_cases"][0]["expected"] != packet["failed_cases"][0]["actual"]
    assert len(provenance["source_files"]) == 3
    assert provenance["reference_implementation_read"] is False
    assert provenance["tasks_private_or_final_artifacts_read"] is False
    assert "reference_files" not in json.dumps(packet)
    assert "historical guidance" not in json.dumps(packet)


@pytest.mark.parametrize("field,value", [("phase", "holdout"), ("stage", "final"), ("stream", 1),
                                        ("repeat", 1), ("target_ok", False), ("id", "other")])
def test_wrong_target_provenance_rejected(fixture, field, value):
    fixture["target"][field] = value
    put(fixture["old"] / s.SOURCE_TARGET, fixture["target"], True)
    with pytest.raises(ValueError, match="intended natural"):
        s.load_development_packet(fixture["repo"])


def test_wrong_candidate_files_rejected_even_after_resealing(fixture):
    fixture["target"]["files"]["policy.py"] += "# changed"
    put(fixture["old"] / s.SOURCE_TARGET, fixture["target"], True)
    with pytest.raises(ValueError, match="pinned artifact"):
        s.load_development_packet(fixture["repo"])


def test_tampered_old_record_rejected(fixture):
    path = fixture["old"] / s.SOURCE_CLAIM
    value = json.loads(path.read_text())
    value["artifact_hash"] = "0" * 64
    put(path, value)
    with pytest.raises(ValueError, match="checksum"):
        s.load_development_packet(fixture["repo"])


def test_receipt_tampering_rejected_despite_resealed_outer_record(fixture):
    fixture["claim"]["receipts"][0]["phase"] = "holdout"
    put(fixture["old"] / s.SOURCE_CLAIM, fixture["claim"], True)
    with pytest.raises(ValueError, match="receipt checksum"):
        s.load_development_packet(fixture["repo"])


def test_duplicate_receipt_rejected(fixture):
    fixture["claim"]["receipts"].append(fixture["claim"]["receipts"][0])
    put(fixture["old"] / s.SOURCE_CLAIM, fixture["claim"], True)
    with pytest.raises(ValueError, match="exactly one"):
        s.load_development_packet(fixture["repo"])


def test_api_request_digest_and_actual_response_are_bound(fixture):
    fixture["call"]["response"] = "different candidate response"
    put(fixture["old"] / s.SOURCE_API, fixture["call"])
    with pytest.raises(ValueError, match="actual successful"):
        s.load_development_packet(fixture["repo"])


def test_private_task_field_rejected(fixture, monkeypatch):
    call = fixture["call"]
    user = json.loads(call["request"]["user"])
    user["task"]["private_cases"] = ["unavailable"]
    call["request"]["user"] = json.dumps(user)
    identifier = s.digest(call["request"])
    call["request_hash"] = identifier
    monkeypatch.setattr(s, "SOURCE_API", "api/calls/" + identifier + ".json")
    fixture["target"]["request_hash"] = identifier
    put(fixture["old"] / s.SOURCE_API, call)
    put(fixture["old"] / s.SOURCE_TARGET, fixture["target"], True)
    with pytest.raises(ValueError, match="public-only"):
        s.load_development_packet(fixture["repo"])


def test_prepare_is_offline_and_freezes_protocol_before_client(fixture, monkeypatch):
    monkeypatch.setattr(s, "BudgetedAPI", lambda *_args, **_kw: pytest.fail("prepare must not create API client"))
    protocol = s.prepare(fixture["repo"], fixture["output"])
    assert protocol["max_logical_calls"] == 6 and protocol["max_tokens_per_call"] == 6000
    assert protocol["validator_activation"] is False and protocol["independent_calibration"] is False
    assert s.verify(fixture["repo"], fixture["output"]) == protocol
    assert not (fixture["output"] / "api").exists()
    assert s.prepare(fixture["repo"], fixture["output"]) == protocol


@pytest.mark.parametrize("path", ["outputs/coevolution_v4/main", "outputs/coevolution_v3/old",
                                  "outputs/coevolution_v4_research_smoke", "arbitrary"])
def test_write_roots_cannot_touch_primary_or_old_runs(fixture, path):
    with pytest.raises(ValueError, match="own run"):
        s.prepare(fixture["repo"], fixture["repo"] / path)


@pytest.mark.parametrize("change", ["source", "packet", "protocol", "state"])
def test_frozen_smoke_inputs_cannot_change(fixture, change):
    s.prepare(fixture["repo"], fixture["output"])
    if change == "source":
        (fixture["repo"] / "source.py").write_text("# new code")
    else:
        name = {"packet": "development_packet.json", "protocol": "protocol.json", "state": "initial_state.json"}[change]
        path = fixture["output"] / name
        value = json.loads(path.read_text())
        if change == "protocol":
            value["max_logical_calls"] = 60
        else:
            value["changed"] = True
        put(path, value)
    with pytest.raises(ValueError, match="changed"):
        s.verify(fixture["repo"], fixture["output"])


def doc_source():
    text = "A return statement without an expression returns None. The explicit task still determines correct graph outputs."
    return {"ok": True, "requested_url": "https://docs.python.org/3/reference/simple_stmts.html#the-return-statement",
            "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "raw_html_sha256": "1" * 64, "snapshot_id": "2" * 64, "retrieved_utc": "2026-09-09T00:00:00Z"}


class FakeAPI:
    def __init__(self, repo, root, max_calls, workers, *, invalid=None):
        assert max_calls == 6 and workers == 4
        assert (Path(root).parent / "protocol.json").exists()
        self.calls, self.invalid = [], invalid

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def call(self, system, user, kind, key, max_tokens):
        assert max_tokens == 6000 and len(self.calls) < 6
        self.calls.append({"kind": kind, "key": key, "max_tokens": max_tokens})
        stage = kind.rsplit("_", 1)[-1]
        research = "smoke-research:" in key
        if stage == "plan":
            value = {"questions": [{"topic": "return values", "question": "Does a cached visit preserve its Boolean result?"}]}
            if research:
                value["urls"] = [doc_source()["requested_url"]]
        elif stage == "synthesis":
            row = {"topic": "return", "gap": "Cached branch returns no Boolean value.",
                   "proposedtest": "Use a shared prerequisite under two target branches.",
                   "uncertainty": "Language behavior does not prescribe the domain's output policy."}
            if research:
                row.update(oldcriterion="dependencies", evidenceurls=[doc_source()["requested_url"]],
                           evidencequotes=[{"url": doc_source()["requested_url"],
                                            "quote": "A return statement without an expression returns None."}])
            value = {"findings": [row], "limits": ["Requires independent calibration."]}
        else:
            strategies = deepcopy(s.validator.initial_state()["strategies"])
            strategies[1]["search"] += " Check repeat visits to a shared prerequisite."
            value = {"strategies": strategies, "rationale": "The source-local natural failure motivates a shared-state diagnostic."}
        return {"ok": True, "response": "malformed" if stage == self.invalid else json.dumps(value),
                "request_hash": s.digest(self.calls[-1]), "finish_reason": "stop", "usage": {"total_tokens": 20}}

    def ledger(self):
        return {"cached_logical_calls": len(self.calls), "total_tokens": len(self.calls) * 20,
                "max_logical_calls": 6, "http_attempts_from_cached_records": len(self.calls)}


def test_six_call_feature_smoke_never_promotes_or_executes(fixture, monkeypatch):
    fetched = []
    def fetch(urls, root):
        fetched.append((urls, root))
        return [doc_source()]
    monkeypatch.setattr(s.validator, "fetch_sources", fetch)
    result = s.run(fixture["repo"], fixture["output"], api_factory=FakeAPI)
    assert result["status"] == "complete" and result["ledger"]["cached_logical_calls"] == 6
    assert result["candidate_executions"] == 0 and result["no_validator_promoted"]
    assert len(fetched) == 1
    feedback, research = result["arms"]
    assert feedback["research_executed"] is False and feedback["source_backed_findings"] == 0
    assert research["research_executed"] and research["sources_available"] == 1
    assert research["verified_exact_quotes"] == 1 and research["proposed_validator_schema_valid"]
    assert s.report(fixture["repo"], fixture["output"]) == result
    assert s.run(fixture["repo"], fixture["output"], api_factory=lambda *_args, **_kw: pytest.fail("no rerun")) == result


def test_malformed_stage_is_recorded_without_reroll(fixture, monkeypatch):
    monkeypatch.setattr(s.validator, "fetch_sources", lambda *_: [doc_source()])
    def factory(*args, **kwargs):
        return FakeAPI(*args, **kwargs, invalid="revision")
    result = s.run(fixture["repo"], fixture["output"], api_factory=factory)
    assert result["ledger"]["cached_logical_calls"] == 6
    assert all(row["proposal_status"] == "proposal_invalid" for row in result["arms"])
    assert result["no_validator_promoted"]


def test_report_tampering_rejected(fixture, monkeypatch):
    monkeypatch.setattr(s.validator, "fetch_sources", lambda *_: [doc_source()])
    s.run(fixture["repo"], fixture["output"], api_factory=FakeAPI)
    path = fixture["output"] / "results.json"
    value = json.loads(path.read_text())
    value["no_validator_promoted"] = False
    put(path, value)
    with pytest.raises(ValueError, match="result integrity"):
        s.report(fixture["repo"], fixture["output"])


def test_cli_prepare_only(fixture, capsys):
    s.main(["prepare", "--repo", str(fixture["repo"]), "--root", str(fixture["output"])])
    result = json.loads(capsys.readouterr().out)
    assert result["purpose"] == "secondary_engineering_feature_smoke_not_efficacy"
    assert result["max_logical_calls"] == 6
