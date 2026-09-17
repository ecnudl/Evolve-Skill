"""Whole experiment orchestration with real runtime and fake transport/child."""

import hashlib
import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v18 import reporting
from skillopt.coevolution_v18 import study as s
from skillopt.validator_pilot.api import digest
from tests.test_coevolution_v18_runtime import forbid, put, tree
from tests.test_coevolution_v18_runtime import fx as runtime_fx  # noqa: F401


@pytest.fixture
def experiment(request, monkeypatch):
    fx = request.getfixturevalue("runtime_fx")
    repo = fx.root
    root = repo / "outputs/coevolution_v18/test"
    code_source = repo / "fixture.txt"
    code_source.write_text("fixture frozen code")
    monkeypatch.setattr(s, "source_hashes", lambda repo: {
        "fixture.txt": hashlib.sha256(code_source.read_bytes()).hexdigest()})
    parents = {str(h): {"text": "PARENT_" + str(h), "learned": True} for h in s.HISTORIES}
    monkeypatch.setattr(s, "load_source", lambda repo: {"skills": parents, "initial_text": "INITIAL"})
    monkeypatch.setattr(s.executor, "sandbox_probe", lambda: {"ok": True, "runner_sha256": s.executor.RUNNER_SHA256})
    tasks = {phase: [] for phase in s.COUNTS}
    for phase, coding_id in zip(s.COUNTS, (601, 511, 11)):
        for domain in s.DOMAINS:
            task = deepcopy(fx.coding if domain == "coding" else fx.qa)
            task.update(phase=phase, split=phase,
                source_split="train" if phase == "development" else "test" if domain == "coding" and phase == "final" else "validation")
            if domain == "coding":
                task.update(id=str(coding_id), task_id=coding_id)
                task["prompt"] += " Phase fixture " + phase
                task["cluster_id"] = task["question_sha256"] = s.runtime.code_data.question_fingerprint(task["prompt"])
            else:
                task["id"] = task["item"]["key"] = "qa_" + phase
                task["item"]["question"] += " Phase fixture " + phase
                task["cluster_id"] = s.runtime.qa_data.question_fingerprint(task["item"]["question"])
            tasks[phase].append(task)
    splits = {domain: {phase: [{"id": t["id"]} for t in rows if t["domain"] == domain]
                       for phase, rows in tasks.items()} for domain in s.DOMAINS}

    def prepare(repo, output, **kwargs):
        return s.save(output / "data_manifest.json", {"splits": splits})

    def materialize(repo, manifest, domain, phase, final_authorization=None):
        if phase == "final":
            assert final_authorization == s.read(root / "final_freeze.json")
            assert final_authorization["data_manifest_hash"] == manifest["record_hash"]
            assert final_authorization["policies_hash"] == digest(final_authorization["histories"])
            assert len(list((root / "learning").glob("*.json"))) == 4
            assert (root / "confirmation_rows.json").exists()
        return deepcopy([t for t in tasks[phase] if t["domain"] == domain])
    monkeypatch.setattr(s.data, "prepare_manifest", prepare)
    monkeypatch.setattr(s.data, "materialize_split", materialize)

    class API(type(fx.api)):
        def __init__(self, target):
            self.root = target
            self._health = "unchecked"
            put(target / "service.json", self.service)

        def call(self, system, user, kind, key, max_tokens=4096, repeat=0):
            if self._health == "failed":
                raise RuntimeError("Synthetic initial transport health failure")
            if kind == "v18_skill_update":
                request = {"model": self.model, "service": self.service, "system": system, "user": user,
                    "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
                identifier = digest(request)
                response = ({"skill": "WHOLE_NEW_" + str(repeat)} if 'Schema {"skill"' in system else
                            {"core": "SHARED_NEW_" + str(repeat), "coding_patch": "CODE_NEW_" + str(repeat)})
                if fx.state.get("invalid_update"):
                    response = {"INVALID": True}
                row = {"request": request, "request_hash": identifier, "ok": True,
                       "response": json.dumps(response), "http_attempt_count": 1}
                put(self.root / "calls" / (identifier + ".json"), row)
                fx.state["api_calls"] += 1
                fx.state["requests"].append(request)
            else:
                row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
            if self._health == "unchecked":
                self._health = "ready" if row["ok"] else "failed"
            if fx.state.pop("pause_on_call", False):
                (root / "PAUSE").touch()
            return row

        @staticmethod
        def parallel(jobs, fn, label):
            assert len(jobs) <= 4
            return [fn(job) for job in jobs]

    def ledger(output, maximum):
        n = len(list((output / "api/calls").glob("*.json")))
        return {"cached_logical_calls": n, "http_attempts_from_cached_records": n,
                "terminal_errors": 0, "total_tokens": n}
    monkeypatch.setattr(s, "closed_ledger", ledger)
    def build():
        return s.Study(repo, root, api_factory=lambda repo, target, **kwargs: API(target))
    return fx, root, build


def test_complete_full_public_shape_and_same_evidence(experiment):
    fx, root, build = experiment
    result = build().run()
    assert result["complete"] is True
    assert result["learning"] == {"positions": 4, "valid": 4}
    assert result["summary"]["unique_tasks"] == 2
    assert result["summary"]["complete_grid_positions"] == 20
    assert fx.state["api_calls"] == result["ledger"]["cached_logical_calls"] == 52
    assert result["evidence_closure"]["calls"] == 52
    assert result["evidence_closure"]["execution_intents"] > 0
    for h in s.HISTORIES:
        whole, layered = (s.read(root / "learning" / f"h{h}-{mode}.json") for mode in ("whole", "layered"))
        assert whole["evidence_hash"] == layered["evidence_hash"]
    learned = [r for r in fx.state["requests"] if r["kind"] == "v18_skill_update"]
    assert all("qa_final" not in r["user"] and "qa_confirmation" not in r["user"] for r in learned)
    assert all("PRIVATE_REFERENCE" not in r["user"] for r in learned)
    report = reporting.render(root)
    assert "core_only_vs_parent" in report and "不是" in report


def test_completed_replay_never_calls_api_or_executes(experiment, monkeypatch):
    fx, root, build = experiment
    result = build().run()
    before = tree(root)
    monkeypatch.setattr(s.OfflineAPI, "call", forbid)
    monkeypatch.setattr(s.executor, "run_cases", forbid)
    monkeypatch.setattr(s.executor, "sandbox_probe", forbid)
    assert build().run() == result
    assert tree(root) == before
    assert fx.state["api_calls"] == 52


def test_pause_drains_chunk_and_resume_reuses_closed_calls(experiment):
    fx, root, build = experiment
    fx.state["pause_on_call"] = True
    with pytest.raises(s.PauseRequested):
        build().run()
    assert fx.state["api_calls"] == 1
    retained = {p.name: p.read_bytes() for p in (root / "api/calls").glob("*.json")}
    (root / "PAUSE").unlink()
    result = build().run()
    assert fx.state["api_calls"] == 52 and result["complete"]
    assert all((root / "api/calls" / name).read_bytes() == body for name, body in retained.items())


def test_invalid_updates_are_explicit_parent_aliases_not_resampled(experiment):
    fx, root, build = experiment
    fx.state["invalid_update"] = True
    result = build().run()
    assert result["learning"] == {"positions": 4, "valid": 0}
    assert fx.state["api_calls"] == 28
    assert all(value["candidate_positions"] == 0 for value in result["deployment_coverage"].values())
    assert result["summary"]["comparisons"]["core_only_vs_parent"]["paired"]["same_request_alias_pairs"] == 4


def test_completed_score_tamper_is_rejected(experiment):
    _, root, build = experiment
    build().run()
    path = next((root / "runtime/solves").glob("*.json"))
    raw = s.read(path)
    raw.pop("record_hash")
    raw["hard"] = 0
    from skillopt.coevolution_v5.core import seal
    put(path, seal(raw))
    with pytest.raises(ValueError):
        build().run()


def test_completed_missing_api_is_not_recreated(experiment):
    fx, root, build = experiment
    build().run()
    next((root / "api/calls").glob("*.json")).unlink()
    with pytest.raises(ValueError):
        build().run()
    assert fx.state["api_calls"] == 52


def test_source_change_blocks_before_new_calls(experiment):
    fx, root, build = experiment
    build().prepare()
    (fx.root / "fixture.txt").write_text("changed")
    with pytest.raises(ValueError):
        build().run()
    assert not list((root / "api/calls").glob("*.json"))


def test_cli_completed_full_tree_byte_hash_is_unchanged(experiment):
    from scripts import coevolution_v18 as cli
    fx, root, build = experiment
    result = build().run()
    for name in (".run.lock", ".audit.lock"):
        (root / name).touch()
    before = tree(root)
    assert cli.completed_replay(fx.root, root) == result
    assert tree(root) == before


def test_first_new_api_failure_stops_before_fanout_and_resumes_closed_unknown(experiment):
    fx, root, build = experiment
    fx.state["api_ok"] = False
    with pytest.raises(s.PauseRequested):
        build().run()
    assert fx.state["api_calls"] == 1
    assert (root / "PAUSE").exists()
    intents = {p.stem for p in (root / "runtime/api_intents").glob("*.json")}
    receipts = {p.stem for p in (root / "api/calls").glob("*.json")}
    assert intents == receipts and len(intents) == 1
    original = next((root / "api/calls").glob("*.json")).read_bytes()
    fx.state["api_ok"] = True
    (root / "PAUSE").unlink()
    result = build().run()
    assert result["complete"] and fx.state["api_calls"] == 52
    assert (root / "api/calls" / (next(iter(receipts)) + ".json")).read_bytes() == original
    development = s.read(root / "development_rows.json")["rows"]
    assert sum(r["hard"] is None for r in development) == 1
