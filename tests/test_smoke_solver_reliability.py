"""Smoke orchestration fixtures only: no network, model or candidate execution."""
import hashlib
import json
from pathlib import Path

import pytest

from scripts import smoke_solver_reliability as smoke
from skillopt.coevolution_v5.core import verify
from tests.test_skill_validation_mechanism_study import StudyExecutor
from tests.test_skill_validation_solver_profile_integration import ProfileMechanismAPI

REPO = Path(__file__).resolve().parents[1]
SECRET = "host-only-smoke-sentinel"


@pytest.fixture
def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "CachedAPI", ProfileMechanismAPI)
    monkeypatch.setattr(ProfileMechanismAPI, "instances", [])
    compile_family = smoke.compile_family

    class PublicOnly(dict):
        def __getitem__(self, key):
            assert key in {"task", "public_task", "public_wrapper"}, "Hidden field accessed"
            return super().__getitem__(key)

    def compile_public(spec, partition):
        return [PublicOnly(**row, sentinel=SECRET) for row in compile_family(spec, partition)]

    monkeypatch.setattr(smoke, "compile_family", compile_public)
    return tmp_path / "run", StudyExecutor()


def test_complete_fixture_is_public_only_uniform_and_bounded(setup):
    root, executor = setup
    result = smoke.run(REPO, root, executor)
    api = ProfileMechanismAPI.instances[-1]
    assert result["status"] == "completed_engineering_smoke" and result["fixture_only"]
    assert result["positions"] == 9 and result["tasks"] == 3
    assert result["independent_task_families"] == 1
    assert result["hidden_audit_calls"] == 0 and not result["skill_updated"]
    assert not result["method_effect_evaluated"] and not result["deployment_authorized"]
    assert result["accounting"]["terminal_logical_requests"] == len(api.fresh_requests) == 12
    assert result["accounting"]["reserved_logical_requests"] == 12
    assert {r["condition"] for r in result["records"]} == {"no_skill", "current", "candidate"}
    assert {r["kind"] for r in api.requests} == {"public-initial", "public-revision"}
    assert all(r["max_tokens"] == 4096 and r["repeat"] == 0 for r in api.requests)
    assert all("compact_json_v1" in r["system"] for r in api.requests)
    assert all(SECRET not in r["system"] + r["user"] for r in api.requests)
    protocol = verify(json.loads((root / "protocol.json").read_text()))
    assert protocol["skills"]["current"] == protocol["skills"]["candidate"]
    assert protocol["skill_origin"] == "handwritten_engineering_control_not_learned"
    assert protocol["solver_profile"]["initial_health_policy"] == api.service["initial_health_policy"]
    assert protocol["request_limit"] == 18


def test_replay_reuses_terminal_calls_and_public_checks(setup):
    root, executor = setup
    first = smoke.run(REPO, root, executor)
    count = len(executor.calls)
    assert smoke.run(REPO, root, executor) == first
    assert not ProfileMechanismAPI.instances[-1].fresh_requests
    assert len(executor.calls) == count + 1  # Only the documented new preflight ping.


@pytest.mark.parametrize("outcome", [
    {"actual": False}, {"status": "unsupported"}, {"cleanup_confirmed": False},
])
def test_unavailable_preflight_stops_before_any_model_request(setup, outcome):
    root, _ = setup
    with pytest.raises(ValueError):
        smoke.run(REPO, root, StudyExecutor(outcome))
    assert not ProfileMechanismAPI.instances[-1].fresh_requests
    assert not (root / "summary.json").exists()
    assert not list((root / "budget/intents").glob("*.json"))


def test_interrupted_call_is_not_resampled(setup):
    root, executor = setup
    smoke.run(REPO, root, executor)
    # The disposable fixture loses a durable terminal receipt, not a real run.
    initial = next(path for path in (root / "api/calls").glob("*.json")
                   if json.loads(path.read_text())["request"]["kind"] == "public-initial")
    initial.unlink()
    with pytest.raises(ValueError, match="Interrupted API request"):
        smoke.run(REPO, root, executor)
    assert not ProfileMechanismAPI.instances[-1].fresh_requests


def test_nondeterministic_public_observations_fit_predeclared_budget(setup):
    root, _ = setup
    # Identical Current/Candidate code need not produce identical observations.
    # Distinct revision prompts must fit without relying on cache aliasing.
    outcomes = [{"actual": True}] + [{"actual": value} for value in (True, False, True) * 3]
    result = smoke.run(REPO, root, StudyExecutor(*outcomes))
    assert result["positions"] == 9 and result["status"] == "completed_engineering_smoke"
    assert 12 < len(ProfileMechanismAPI.instances[-1].fresh_requests) <= 18
    assert len(list((root / "budget/intents").glob("*.json"))) <= 18


def test_source_binding_uses_loaded_code_not_credential_repo(setup, tmp_path):
    root, executor = setup
    smoke.run(tmp_path, root, executor)
    protocol = verify(json.loads((root / "protocol.json").read_text()))
    loaded = Path(smoke.rule_solver.__file__).resolve()
    assert protocol["source_hashes"][loaded.name] == hashlib.sha256(loaded.read_bytes()).hexdigest()
