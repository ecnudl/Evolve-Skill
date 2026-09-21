"""Synthetic end-to-end pilot tests: no HTTP/SSH, no execution of Python code."""
import ast
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import single_round as study
from skillopt.skill_validation import single_round_data as data
from skillopt.skill_validation.research import ResearchResult, fixed_rubric
from skillopt.validator_pilot.api import digest, write_immutable_json
from tests.test_skill_validation_single_round_data import identity, source_row

PARENT = "Use task-specific boundary reasoning and check the requested behavior."
CANDIDATE = "## Mechanism\nContract conformance.\n## When\nA task gives explicit requirements.\n## Procedure\nCheck required boundaries.\n## Avoid\nDo not invent constraints."


class FakeAPI:
    """All receipts explicitly marked fixture; no upstream API is reachable."""
    def __init__(self, repo, root, workers=4, **kwargs):
        self.root, self.workers, self.model = root, workers, "fixture"
        self.service = {"fixture": True, "max_retries": 0}
        self.new_calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def call(self, system, user, kind, key, max_tokens=2048, repeat=0):
        request = {"model": self.model, "system": system, "user": user, "kind": kind,
                   "key": key, "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        request_hash = digest(request)
        path = self.root / "calls" / (request_hash + ".json")
        if path.exists():
            return json.loads(path.read_text())
        self.new_calls += 1
        response = (json.dumps({"solution.py": "def solve(values):\n    return sorted(values)\n"})
                    if kind == "single-round-solver" else CANDIDATE if kind == "single-round-skill-update" else
                    json.dumps({"status": "no_update", "questions": [], "urls": []}))
        receipt = {"request": request, "request_hash": request_hash, "ok": True, "response": response,
                   "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "http_attempt_count": 1}
        write_immutable_json(path, receipt)
        return receipt

    def parallel(self, jobs, fn, label):
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(fn, jobs))


class FixtureExecutor:
    """Handwritten observations, not an interpreter for the supplied Python."""
    identity = {"kind": "fixture-nonexecuting-observer"}
    transport_identity = {"kind": "fixture-no-ssh"}

    def __init__(self, unavailable=False):
        self.calls = []
        self.unavailable = unavailable

    def run(self, files, module, function, args, kwargs):
        self.calls.append(module)
        actual = True
        if module == "hidden_audit":
            count = sum(isinstance(node, ast.Assert) for node in ast.walk(ast.parse(files["hidden_audit.py"])))
            actual = [{"passed": True, "exception": None} for _ in range(count)]
        call = {"module": module, "function": function, "args": args, "kwargs": kwargs}
        return seal({"status": "unsupported" if self.unavailable else "observed", "actual": actual,
            "exception": None, "reason": "fixture observation", "cleanup_confirmed": True,
            "input_hash": digest({"files": files, **call}), "source_hash": digest(files), "call_hash": digest(call),
            "executor_identity": self.identity, "before_args": deepcopy(args), "after_args": deepcopy(args),
            "before_kwargs": deepcopy(kwargs), "after_kwargs": deepcopy(kwargs), "duration_seconds": 0.0})


def prepare_fixture(tmp_path, monkeypatch):
    root = tmp_path / "study"
    manifest = seal({"settings": {"counts": {"development": 8, "verifier_calibration": 4, "final": 16}}})
    write_immutable_json(root / "data_manifest.json", manifest)
    write_immutable_json(root / "parent_skill.json", seal({"text": PARENT}))
    pools = {}
    for phase, count, offset in (("development", 8, 601), ("verifier_calibration", 4, 551), ("final", 16, 11)):
        rows = []
        for n in range(count):
            row = source_row(task_id=offset + n)
            row["prompt"] += " Fixture task " + str(offset + n)
            rows.append(data.materialize_row(row, identity(row, phase)))
        pools[phase] = rows

    def materialize(repo, given, phase, **kwargs):
        assert given == manifest
        if phase == "final":
            freeze = study._read(root / "frozen_candidates.json")
            assert kwargs["final_authorization"] == freeze
            assert set(freeze["candidate_skill_hashes"]) == set(study.ARMS)
        return pools[phase]

    monkeypatch.setattr(data, "materialize_tasks", materialize)
    monkeypatch.setattr(study, "CachedAPI", FakeAPI)
    return root


def test_complete_shadow_round_freezes_candidates_then_evaluates_and_replays(tmp_path, monkeypatch):
    root = prepare_fixture(tmp_path, monkeypatch)
    executor = FixtureExecutor()
    result = study.run(tmp_path, root, executor)
    assert result["deployment_authorized"] is result["cross_domain_evidence"] is False
    assert result["unique_updater_requests"] == result["unique_feedback_prompts"] == 1
    assert set(result["candidate_status"].values()) == {"candidate"}
    assert set(result["calibration_status"].values()) == {"pending"}
    assert result["final"]["rates"]["fixed"]["positions"] == 32
    assert result["final"]["rates"]["fixed"]["independent_task_ids"] == 16
    assert result["final"]["unique_final_model_requests"] == 96
    assert result["cost"]["terminal_logical_requests"] == 123  # 24 dev/cal +2 proposals+1 update+96final
    api_before = {str(p): p.read_bytes() for p in (root / "api").rglob("*.json")}
    calls_before = len(executor.calls)
    assert study.run(tmp_path, root, executor) == result
    assert len(executor.calls) == calls_before + 1  # explicit harmless runtime health probe only
    assert api_before == {str(p): p.read_bytes() for p in (root / "api").rglob("*.json")}
    requests = [json.loads(p.read_text())["request"] for p in (root / "api/calls").glob("*.json")]
    assert all("assert solve([9, 7])" not in r["user"] for r in requests)
    for path in root.rglob("artifacts/*.json"):
        assert study._read(path)["provenance_kind"] == "fixture"


def test_unavailable_preflight_sends_no_paid_requests(tmp_path, monkeypatch):
    root = prepare_fixture(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="infrastructure unavailable"):
        study.run(tmp_path, root, FixtureExecutor(unavailable=True))
    assert not list((root / "api/calls").glob("*.json"))
    assert len(list((root / "runtime_probes").glob("*.json"))) == 1


def test_budget_cache_repeat_and_interrupted_intent(tmp_path):
    api = FakeAPI(tmp_path, tmp_path / "api")
    calls = study.BoundedCalls(api, tmp_path / "budget", "a" * 64, 2)
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(lambda _: calls.call("s", "u", "single-round-solver"), range(4)))
    assert len({r["request_hash"] for r in records}) == 1 and api.new_calls == 1
    second = calls.call("s", "u", "single-round-solver", repeat=1)
    assert api.new_calls == 2 and second["request_hash"] != records[0]["request_hash"]
    with pytest.raises(ValueError, match="budget exhausted"):
        calls.call("different", "u", "single-round-solver")
    (api.root / "calls" / (second["request_hash"] + ".json")).unlink()
    with pytest.raises(ValueError, match="Interrupted"):
        calls.call("s", "u", "single-round-solver", repeat=1)


@pytest.mark.parametrize("response", ["def solve(x): return x", '{"wrong.py":"code"}',
    '{"solution.py":"a","solution.py":"b"}', '{"solution.py":null}'])
def test_bad_code_is_not_repaired_or_executed(response):
    with pytest.raises((ValueError, json.JSONDecodeError)):
        study.parse_code(response)


def test_unknown_is_not_removed_and_repeats_are_not_tasks():
    rows = [{"task_id": "task", "repeat": repeat, "arm": arm, "status": status,
             "request_ref": str((repeat, arm))}
            for repeat in (0, 1) for arm, status in (("no_skill", "pass"), ("parent", "pass"),
                ("fixed", "unknown"), ("adaptive_no_research", "fail"), ("adaptive_research", "pass"))]
    result = study.summarize_final(rows)
    assert result["rates"]["fixed"]["unknown"] == result["rates"]["fixed"]["positions"] == 2
    assert result["rates"]["fixed"]["independent_task_ids"] == 1
    assert result["paired"]["fixed_vs_parent"]["positions"] == {"unknown": 2}
    assert result["paired"]["adaptive_no_research_vs_parent"]["positions"] == {"loss": 2}


def test_equivalent_adaptive_pipelines_share_a_freeze(tmp_path, monkeypatch):
    root = prepare_fixture(tmp_path, monkeypatch)
    original = study._proposal
    shared = fixed_rubric()
    from dataclasses import replace
    shared = replace(shared, version="fixture-shared-updated-version")

    def proposal(research, arm, views, root, protocol_hash):
        if arm == "fixed":
            return original(research, arm, views, root, protocol_hash)
        return ResearchResult("update", arm, shared, (), (), {}, (), "fixture identical pipeline", True)

    monkeypatch.setattr(study, "_proposal", proposal)
    result = study.run(tmp_path, root, FixtureExecutor())
    assert result["unique_updater_requests"] == 1
    assert set(result["calibration_status"].values()) == {"pending"}
    assert len([p for p in (root / "verifier_gate/freezes").glob("*.json")
                if not p.name.endswith(".development.json")]) == 1
