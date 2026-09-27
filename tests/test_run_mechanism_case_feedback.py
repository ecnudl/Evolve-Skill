"""Offline driver integration; no real API, SSH, Docker, or A artifacts read."""
import json
from pathlib import Path

import pytest

from scripts import run_mechanism_case_feedback as driver
from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation.mechanism_study import _collect_development
from skillopt.skill_validation.mechanism_tasks import build_panel, serialize_row
from skillopt.skill_validation.rule_skill import RuleSkill
from skillopt.skill_validation.single_round import BoundedCalls
from skillopt.validator_pilot.api import digest
from tests.test_skill_validation_public_revision import CODE, FixtureExecutor


SECRET = "PRIVATE_HOST_DATA_MUST_NOT_ENTER_PROPOSAL"


class FixtureAPI:
    instances = []
    proposal_response = "NO_UPDATE"
    proposal_ok = True

    def __init__(self, repo, root, **kwargs):
        self.root = Path(root)
        self.model = "fixture-no-model"
        self.service = {"fixture": True, "provider": "FIXTURE"}
        self.requests, self.fresh_requests = [], []
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def parallel(self, jobs, fn, label):
        return [fn(job) for job in jobs]

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        request = {"model": self.model, "system": system, "user": user, "kind": kind,
                   "key": key, "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        self.requests.append(request)
        path = self.root / "calls" / (digest(request) + ".json")
        if path.exists():
            return json.loads(path.read_text())
        self.fresh_requests.append(request)
        response = (json.dumps({"solution.py": CODE}) if kind == "public-initial" else
                    "KEEP" if kind == "public-revision" else self.proposal_response)
        ok = True if kind in {"public-initial", "public-revision"} else self.proposal_ok
        value = {"request": request, "request_hash": digest(request), "response": response,
                 "ok": ok, "fixture_only": True, "http_attempt_count": 1,
                 "usage": {"prompt_tokens": 0, "completion_tokens": 0}}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return value


def write(path, record):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record))


def reseal(record):
    return seal({k: v for k, v in record.items() if k != "record_hash"})


def source_fixture(tmp_path, *, histories=1):
    """Create a three-task, development-only source with bound fixture receipts."""
    source = tmp_path / "source"
    rows = build_panel(20260925, 1, 1)["development"][:3]
    raw_rows = [serialize_row(row) for row in rows]
    for row in raw_rows:
        row["host_only"] = {"private": SECRET}
        row["region"] = SECRET
    manifest = seal({"version": "fixture-registered-panel", "row_hashes": {
        "development": [digest(row) for row in raw_rows], "confirmation": []}})
    protocol = seal({"version": "fixture-source-protocol", "histories": histories,
                     "manifest_hash": manifest["record_hash"], "service": {"fixture": True}})
    write(source / "protocol.json", protocol)
    write(source / "host_only/panel.json", seal({"version": "fixture-panel", "manifest": manifest,
          "development": raw_rows, "confirmation": [{"private_reference": SECRET}]}))
    write(source / "frozen_panel.json", seal({"protocol_hash": protocol["record_hash"],
          "manifest_hash": manifest["record_hash"], "before_learning": True}))
    executor = FixtureExecutor()
    api = FixtureAPI(tmp_path, source / "api")
    for index in range(histories):
        name = f"h{index}"
        parent = RuleSkill("fixture-parent-" + name, ())
        base = source / "histories" / name
        calls = BoundedCalls(api, base / "budget", digest(["fixture", name]), 32)
        feedback = _collect_development(rows, parent, calls, executor, base / "development", api, 1)
        write(base / "parent.json", seal({"skill": parent.to_dict()}))
        write(base / "feedback.json", feedback)
    # Explicitly poison paths the importer has no reason to read.
    write(source / "confirmation_rows.json", {"not_to_be_read": SECRET})
    write(source / "summary.json", {"not_to_be_read": SECRET})
    return source, executor


@pytest.fixture(autouse=True)
def fake_api(monkeypatch):
    monkeypatch.setattr(driver, "CachedAPI", FixtureAPI)
    monkeypatch.setattr(FixtureAPI, "instances", [])
    monkeypatch.setattr(FixtureAPI, "proposal_response", "NO_UPDATE")
    monkeypatch.setattr(FixtureAPI, "proposal_ok", True)


def test_load_source_projects_only_public_rows_and_never_reads_confirmation(tmp_path, monkeypatch):
    source, _ = source_fixture(tmp_path, histories=2)
    read, accessed = driver._read, []
    allowed = {"protocol.json", "frozen_panel.json", "host_only/panel.json",
               "histories/h0/parent.json", "histories/h0/feedback.json",
               "histories/h1/parent.json", "histories/h1/feedback.json"}
    def guarded(path):
        relative = str(path.relative_to(source))
        assert relative in allowed
        accessed.append(relative)
        return read(path)
    monkeypatch.setattr(driver, "_read", guarded)
    rows, histories, index = driver.load_source(source)
    assert set(accessed) == allowed and len(rows) == 3 and set(histories) == {"h0", "h1"}
    assert all(set(row) == {"task", "public_task", "public_wrapper"} for row in rows)
    assert SECRET not in str(rows) and SECRET not in str(index)
    assert index["confirmation_outputs_read"] is False and index["hidden_audit_used"] is False


@pytest.mark.parametrize("tamper", ["manifest_seal", "protocol_manifest", "development_hash",
                                     "changed_public_wrapper", "not_frozen"])
def test_changed_registration_cannot_reuse_old_frozen_identity(tmp_path, tamper):
    source, _ = source_fixture(tmp_path)
    if tamper == "not_frozen":
        path = source / "frozen_panel.json"
        value = json.loads(path.read_text()); value["before_learning"] = False
    elif tamper == "protocol_manifest":
        path = source / "protocol.json"
        value = json.loads(path.read_text()); value["manifest_hash"] = digest("wrong")
        value = reseal(value)
        write(path, value)
        frozen_path = source / "frozen_panel.json"
        frozen = json.loads(frozen_path.read_text()); frozen["protocol_hash"] = value["record_hash"]
        write(frozen_path, reseal(frozen))
        with pytest.raises(ValueError):
            driver.load_source(source)
        return
    else:
        path = source / "host_only/panel.json"
        value = json.loads(path.read_text())
        if tamper == "manifest_seal":
            value["manifest"]["version"] = "changed-with-old-hash"
        elif tamper == "development_hash":
            value["development"].pop()
        else:
            value["development"][0]["public_wrapper"]["content"] += "\n# changed wrapper\n"
    write(path, reseal(value))
    with pytest.raises(ValueError):
        driver.load_source(source)


@pytest.mark.parametrize("relation", ["same", "inside", "ancestor"])
def test_output_cannot_overlap_source_in_either_direction(tmp_path, relation):
    source, executor = source_fixture(tmp_path)
    output = source if relation == "same" else source / "new" if relation == "inside" else tmp_path
    before = len(FixtureAPI.instances)
    with pytest.raises(ValueError, match="output|outside|overlap|directory"):
        driver.run(tmp_path, source, output, executor, repeats=1, workers=1)
    assert len(FixtureAPI.instances) == before


def test_complete_comparison_same_instructions_only_annex_differs_and_resume_is_cached(tmp_path):
    source, executor = source_fixture(tmp_path)
    output = tmp_path / "comparison"
    result = driver.run(tmp_path, source, output, executor, repeats=1, workers=1)
    assert result["status"] == "completed_proposal_diagnostic"
    assert result["provenance"] == "engineering_fixture"
    assert not result["skill_effect_evaluated"] and not result["cross_domain_evaluated"]
    assert not result["deployment_authorized"]
    protocol = verify(json.loads((output / "protocol.json").read_text()))
    assert protocol["confirmation_candidate_selection"] == "repeat_0_only_no_best_of_n_selection"
    assert protocol["additional_proposal_repeats"] == "stability_diagnostics_not_candidate_selection"
    assert len(result["rows"]) == 2 and {r["status"] for r in result["rows"]} == {"no_update"}
    api = FixtureAPI.instances[-1]
    assert len(api.fresh_requests) == result["accounting"]["terminal_logical_requests"] == 2
    assert {r["kind"] for r in api.requests} == {"mechanism-public-case-annex-update"}
    records = [verify(json.loads((output / "histories/h0/updates" / f"{arm}-0.json").read_text()))
               for arm in driver.ARMS]
    left, right = records
    assert left["request"]["system"] == right["request"]["system"]
    luser, ruser = json.loads(left["request"]["user"]), json.loads(right["request"]["user"])
    assert luser.pop("public_case_annex") == []
    assert ruser.pop("public_case_annex")
    assert luser == ruser
    assert all(SECRET not in row["request"]["user"] for row in records)
    assert all(row["api_receipt"]["request_hash"] == digest(row["api_receipt"]["request"]) for row in records)
    count = len(executor.calls)
    assert driver.run(tmp_path, source, output, executor, repeats=1, workers=1) == result
    assert not FixtureAPI.instances[-1].fresh_requests and len(executor.calls) == count


def test_histories_and_repeats_have_distinct_requests_without_new_solver_calls(tmp_path):
    source, executor = source_fixture(tmp_path, histories=2)
    result = driver.run(tmp_path, source, tmp_path / "comparison", executor, repeats=2, workers=1)
    api = FixtureAPI.instances[-1]
    assert len(result["rows"]) == len(api.fresh_requests) == 8
    assert len({digest(r) for r in api.fresh_requests}) == 8
    assert {r["repeat"] for r in api.fresh_requests} == {0, 1, 2, 3}
    assert {r["kind"] for r in api.requests} == {"mechanism-public-case-annex-update"}
    assert {(r["history"], r["arm"], r["repeat"]) for r in result["rows"]} == {
        (h, a, r) for h in ("h0", "h1") for a in driver.ARMS for r in (0, 1)}


@pytest.mark.parametrize("response,ok,status", [("NO_UPDATE", True, "no_update"),
    ("{broken", True, "invalid"), ("", False, "api_failure")])
def test_terminal_negative_results_retained_without_resampling(tmp_path, monkeypatch, response, ok, status):
    source, executor = source_fixture(tmp_path)
    monkeypatch.setattr(FixtureAPI, "proposal_response", response)
    monkeypatch.setattr(FixtureAPI, "proposal_ok", ok)
    output = tmp_path / "comparison"
    result = driver.run(tmp_path, source, output, executor, repeats=1, workers=1)
    assert len(result["rows"]) == 2 and {r["status"] for r in result["rows"]} == {status}
    assert all(r["candidate"] is None and not r["semantic_support_verified"] for r in result["rows"])
    assert len(FixtureAPI.instances[-1].fresh_requests) == 2
    assert driver.run(tmp_path, source, output, executor, repeats=1, workers=1) == result
    assert not FixtureAPI.instances[-1].fresh_requests


def test_protocol_change_cannot_resume_same_output(tmp_path):
    source, executor = source_fixture(tmp_path)
    output = tmp_path / "comparison"
    driver.run(tmp_path, source, output, executor, repeats=1, workers=1)
    count = len(executor.calls)
    with pytest.raises(ValueError):
        driver.run(tmp_path, source, output, executor, repeats=2, workers=1)
    assert not FixtureAPI.instances[-1].fresh_requests and len(executor.calls) == count


def test_interrupted_request_retains_intent_and_cannot_silently_retry(tmp_path, monkeypatch):
    source, executor = source_fixture(tmp_path)
    output = tmp_path / "comparison"
    original = FixtureAPI.call
    def interrupted(*args, **kwargs):
        raise RuntimeError("fixture interrupted before any response")
    monkeypatch.setattr(FixtureAPI, "call", interrupted)
    with pytest.raises(RuntimeError, match="fixture interrupted"):
        driver.run(tmp_path, source, output, executor, repeats=1, workers=1)
    assert len(list((output / "budget/intents").glob("*.json"))) == 1
    assert not list((output / "api/calls").glob("*.json"))
    assert not (output / "summary.json").exists()
    count = len(executor.calls)
    monkeypatch.setattr(FixtureAPI, "call", original)
    with pytest.raises(ValueError, match="Interrupted"):
        driver.run(tmp_path, source, output, executor, repeats=1, workers=1)
    assert not FixtureAPI.instances[-1].fresh_requests and len(executor.calls) == count


@pytest.mark.parametrize("kwargs", [{"repeats": True}, {"repeats": 0}, {"repeats": 4},
    {"workers": True}, {"workers": 0}, {"workers": 5}])
def test_invalid_budget_fails_before_source_read_or_api(tmp_path, monkeypatch, kwargs):
    monkeypatch.setattr(driver, "load_source", lambda *a: pytest.fail("Budget must be checked first"))
    with pytest.raises(ValueError):
        driver.run(tmp_path, tmp_path / "source", tmp_path / "new", FixtureExecutor(), **kwargs)
    assert not FixtureAPI.instances


def test_preflight_difference_outside_annex_stops_before_paid_calls(tmp_path, monkeypatch):
    source, executor = source_fixture(tmp_path)
    original = driver.build_request
    def changed(*args, arm, **kwargs):
        result = original(*args, arm=arm, **kwargs)
        if arm == "case_details":
            user = json.loads(result["user"])
            user["unrelated_change"] = True
            result = {**result, "user": json.dumps(user)}
        return result
    monkeypatch.setattr(driver, "build_request", changed)
    with pytest.raises(ValueError, match="annex"):
        driver.run(tmp_path, source, tmp_path / "comparison", executor, repeats=1, workers=1)
    assert not FixtureAPI.instances[-1].fresh_requests


def test_only_prompt_size_exception_becomes_pre_api_pending_budget(tmp_path, monkeypatch):
    from skillopt.skill_validation import mechanism_case_feedback
    source, executor = source_fixture(tmp_path)
    monkeypatch.setattr(mechanism_case_feedback, "MAX_PROMPT_BYTES", 1)
    output = tmp_path / "budget-pending"
    result = driver.run(tmp_path, source, output, executor, repeats=1, workers=1)
    assert result["status"] == "pending_prompt_budget"
    assert result["stage"] == "before_any_model_call" and result["history"] == "h0"
    assert result["actual_bytes"] > result["limit_bytes"] == 1
    assert result["accounting"]["terminal_logical_requests"] == 0
    assert result["accounting"]["reserved_logical_requests"] == 0
    assert not result["skill_effect_evaluated"] and not result["deployment_authorized"]
    assert verify(json.loads((output / "pending_prompt_budget.json").read_text())) == result
    assert not (output / "summary.json").exists() and not FixtureAPI.instances[-1].fresh_requests


def test_integrity_error_is_not_swallowed_as_budget_pending(tmp_path, monkeypatch):
    source, executor = source_fixture(tmp_path)
    def invalid(*a, **k):
        raise ValueError("fixture binding integrity error")
    monkeypatch.setattr(driver, "build_request", invalid)
    output = tmp_path / "integrity-error"
    with pytest.raises(ValueError, match="binding integrity"):
        driver.run(tmp_path, source, output, executor, repeats=1, workers=1)
    assert not (output / "pending_prompt_budget.json").exists()
    assert not FixtureAPI.instances[-1].fresh_requests
