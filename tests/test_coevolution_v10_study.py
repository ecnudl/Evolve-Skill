"""Offline full V10 transfer using a synthetic 427-row dataset and fake I/O.

No downloaded source, live model, or candidate execution is used in this module.
Actual assertion compilation, evidence binding, gate and replay run unchanged.
"""

import hashlib
import json
from contextlib import contextmanager
from copy import deepcopy

import pytest

from skillopt.coevolution_v5 import core
from skillopt.coevolution_v9 import study as parent
from skillopt.coevolution_v10 import data, execution, executor
from skillopt.coevolution_v10 import study as s
from skillopt.validator_pilot.api import digest


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def tree(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def forbidden(*args, **kwargs):
    pytest.fail("Offline replay must not open API, execute child, or reconstruct evidence")


def reseal(path, change):
    row = json.loads(path.read_text())
    row.pop("record_hash")
    change(row)
    put(path, core.seal(row))


class FakeAPI:
    model = "glm-5.3"
    service = {"offline_fixture": True, "max_retries": 2}

    def __init__(self, root, maximum, state):
        self.root, self.state = root, state
        put(root / "service.json", self.service)
        put(root / "budget_protocol.json", {"max_logical_calls": maximum, "model": self.model,
            "workers": 4, "service_sha256": digest(self.service)})

    def call(self, system, user, kind, key, max_tokens=4096, repeat=0):
        request = {"model": self.model, "service": self.service, "system": system, "user": user,
                   "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
        identifier = digest(request)
        path = self.root / "calls" / (identifier + ".json")
        if path.exists():
            return json.loads(path.read_text())
        self.state["calls"] += 1
        put(self.root / "budget_reservations" / (identifier + ".json"),
            {"request_hash": identifier, "kind": kind})
        code = "def solve(x):\n    return x\n" + ("# WRONG_CANDIDATE" if "RAW_TWO" in system else "")
        ok = not self.state.get("fail_api")
        receipt = {"request": request, "request_hash": identifier, "ok": ok,
            "response": json.dumps({"code": code}) if ok else "",
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2} if ok else {},
            "http_attempt_count": 1, "finish_reason": "stop", "error_type": None if ok else "timeout"}
        put(path, receipt)
        if self.state.get("pause_after_call") == self.state["calls"]:
            s.request_pause(self.root.parent)
        return receipt

    def parallel(self, jobs, function, label):
        result = [function(job) for job in jobs]
        self.state["chunks"].append(len(jobs))
        if self.state.get("drift_after_chunk"):
            self.state["source_hash"] = "b" * 64
        return result


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    snapshot_root = repo / data.DIRECTORY
    snapshot_root.mkdir(parents=True)
    identifiers = [*range(1, 8), *range(11, 268), *range(511, 554), *range(601, 721)]
    rows = [{"task_id": identifier, "prompt": f"SYNTHETIC_PUBLIC_QUESTION_{identifier}",
        "code": f"def solve(x):\n    return x\n# REFERENCE_SECRET_{identifier}\n", "test_imports": [],
        "test_list": ["assert solve('HIDDEN_ARGUMENT') == 'HIDDEN_ARGUMENT'"]} for identifier in identifiers]
    bodies = {"dataset": json.dumps(rows), "upstream_readme": "Synthetic official split metadata",
              "dataset_card": "---\nlicense:\n- cc-by-4.0\n---\n"}
    files = {}
    for name, body in bodies.items():
        path = snapshot_root / data.FILENAMES[name]
        path.write_text(body)
        files[name] = {"path": str(path.relative_to(repo)), "sha256": data.file_hash(path), "url": data.URLS[name]}
    put(snapshot_root / "source_snapshot.json", core.seal({"version": data.SOURCE_VERSION,
        "dataset": data.DATASET, "revision": data.REVISION, "card_revision": data.CARD_REVISION,
        "license": "CC-BY-4.0", "files": files, "source_counts": data._counts(rows), "total_rows": len(rows)}))
    initial = "Initial source placeholder."
    state = {"calls": 0, "children": 0, "probes": 0, "source_hash": "a" * 64, "chunks": []}
    anchor = {"parent_run": "synthetic-parent", "parent_result_hash": "c" * 64,
        "parent_freeze_hash": "d" * 64, "parent_audit_hash": "e" * 64,
        "source_domain": "searchqa", "initial_text": initial, "skills": {
            str(h): {"text": text, "skill_hash": s.learning.text_hash(text), "learned": text != initial}
            for h, text in enumerate(("RAW_ONE", initial, "RAW_TWO"))},
        "no_new_learning_or_research_in_this_run": True}
    monkeypatch.setattr(s, "load_source", lambda _repo: deepcopy(anchor))
    monkeypatch.setattr(s, "source_hashes", lambda _repo: {"fixture": state["source_hash"]})
    monkeypatch.setattr(parent, "audit_pacing", lambda *_args: {"offline_fixture": True})

    def probe():
        state["probes"] += 1
        return {"ok": True, "runner_sha256": executor.RUNNER_SHA256, "offline_fixture": True}

    def fake_child(code, entry_point, cases):
        state["children"] += 1
        payload = executor._payload(code, entry_point, cases)
        wrong = "WRONG_CANDIDATE" in code or (state.get("fail_reference") and "REFERENCE_SECRET" in code)
        observations = [{"value": executor.encode_value("WRONG") if wrong else case["args"][0],
                         "exception": None} for case in cases]
        return {"version": executor.VERSION, "runner_sha256": executor.RUNNER_SHA256,
            "code_hash": hashlib.sha256(code.encode()).hexdigest(), "status": "completed",
            "observations": observations, "error_category": None,
            "payload_hash": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()}

    monkeypatch.setattr(executor, "sandbox_probe", probe)
    monkeypatch.setattr(executor, "run_cases", fake_child)
    root = repo / "outputs/coevolution_v10/fixture"

    @contextmanager
    def factory(_repo, api_root, *, max_calls, workers):
        assert workers == 4 and _repo == repo
        yield FakeAPI(api_root, max_calls, state)

    def build(design="smoke"):
        return s.Study(repo, root, design=design, api_factory=factory)

    return root, state, factory, build


def test_smoke_has_four_unique_requests_and_three_shared_histories(fixture):
    root, state, _, build = fixture
    result = build().run()
    assert result["complete"] and result["smoke_not_effect_evidence"]
    assert state["calls"] == result["ledger"]["cached_logical_calls"] == 24
    assert state["children"] == 30 and state["probes"] == 1
    assert result["summary"]["n_observation_positions"] == 48
    assert result["summary"]["unique_actual_requests"] == 16
    assert result["summary"]["scope_fallback_positions"] == 12
    assert result["summary"]["actual_learned_usage"]["scope_gated"] == 0
    assert result["summary"]["actual_learned_usage"]["raw_transfer"] == 8
    assert not any(row["approve"] for row in result["gate"]["decisions"].values())
    rows = json.loads((root / "final_rows.json").read_text())["rows"]
    for task in {row["task_id"] for row in rows}:
        base = [r for r in rows if r["task_id"] == task and r["policy"] == "no_skill"]
        fallback = [r for r in rows if r["task_id"] == task and r["policy"] == "scope_gated"]
        assert len({r["request_hash"] for r in base + fallback}) == 1
        assert all(r["hard"] == 1 for r in base + fallback)
    for path in (root / "api/calls").glob("*.json"):
        request = json.loads(path.read_text())["request"]
        assert request["kind"] == execution.KIND and request["model"] == "glm-5.3"
        assert all(secret not in request["user"] + request["system"]
                   for secret in ("REFERENCE_SECRET", "HIDDEN_ARGUMENT", "test_list"))


def test_completed_replay_zero_api_zero_child_zero_evidence_writes(fixture, monkeypatch):
    root, state, _, build = fixture
    expected = build().run()
    before, counts = tree(root), (state["calls"], state["children"], state["probes"])
    monkeypatch.setattr(executor, "run_cases", forbidden)
    monkeypatch.setattr(executor, "sandbox_probe", forbidden)
    monkeypatch.setattr(execution, "write_immutable_json", forbidden)
    monkeypatch.setattr(parent, "write_immutable_json", forbidden)
    assert build().run(api_factory=forbidden) == expected
    assert tree(root) == before
    assert (state["calls"], state["children"], state["probes"]) == counts


def test_failed_references_keep_all_positions_unknown_without_replacement(fixture):
    root, state, _, build = fixture
    state["fail_reference"] = True
    result = build().run()
    assert result["reference_summary"] == {
        "confirmation": {"total": 2, "valid": 0, "unknown": 2},
        "final": {"total": 4, "valid": 0, "unknown": 4}}
    assert state["calls"] == 24 and state["children"] == 6
    rows = json.loads((root / "final_rows.json").read_text())["rows"]
    assert len(rows) == 48 and len({row["task_id"] for row in rows}) == 4
    assert all(row["hard"] is None and row["soft"] is None for row in rows)
    assert all(row["api_ok"] is True for row in rows)
    assert result["outcome_categories"] == {"reference_unavailable": 24}


def test_all_api_failures_are_unknown_without_candidate_execution(fixture):
    _, state, _, build = fixture
    state["fail_api"] = True
    result = build().run()
    assert state["calls"] == 24 and state["children"] == 6
    assert result["ledger"]["successful_calls"] == 0
    assert result["outcome_categories"] == {"api_unknown": 24}


@pytest.mark.parametrize("missing", ["protocol.json", "source_anchor.json", "data_manifest.json",
    "exposure_inventory.json", "eligibility_manifest.json", "sandbox_probe.json", "gate.json",
    "final_freeze.json", "final_rows.json", "confirmation_rows.json"])
def test_missing_completed_metadata_never_rebuilt(fixture, missing):
    root, state, _, build = fixture
    build().run()
    (root / missing).unlink()
    before, counts = tree(root), (state["calls"], state["children"])
    with pytest.raises((ValueError, FileNotFoundError)):
        build().run(api_factory=forbidden)
    assert before == tree(root) and counts == (state["calls"], state["children"])


@pytest.mark.parametrize("directory", ["references", "executions", "execution_intents", "solves",
                                       "api/calls", "api/budget_reservations"])
def test_missing_completed_request_or_execution_never_repaired(fixture, directory):
    root, state, _, build = fixture
    build().run()
    next((root / directory).glob("*.json")).unlink()
    before, counts = tree(root), (state["calls"], state["children"])
    with pytest.raises((ValueError, FileNotFoundError)):
        build().run(api_factory=forbidden)
    assert before == tree(root) and counts == (state["calls"], state["children"])


@pytest.mark.parametrize("target", ["gate", "final_freeze", "results", "solves"])
def test_resealed_semantic_tampering_rejected(fixture, target):
    root, _, _, build = fixture
    build().run()
    if target == "solves":
        path = next((root / target).glob("*.json"))
        reseal(path, lambda row: row.update(hard=1 - row["hard"]))
    else:
        path = root / (target + ".json")
        reseal(path, lambda row: row.update(injected_claim=True))
    before = tree(root)
    with pytest.raises(ValueError):
        build().run(api_factory=forbidden)
    assert tree(root) == before


def test_midrun_source_drift_blocks_final_access(fixture):
    root, state, _, build = fixture
    state["drift_after_chunk"] = True
    with pytest.raises(ValueError, match="Frozen implementation changed"):
        build().run()
    assert state["calls"] == 8
    assert not (root / "final_freeze.json").exists()
    assert not (root / "results.json").exists()


def test_pause_drains_four_request_chunk_then_resumes_cached_work(fixture):
    root, state, _, build = fixture
    state["pause_after_call"] = 2
    with pytest.raises(s.PauseRequested):
        build().run()
    assert state["calls"] == 4 and state["chunks"] == [4]
    checkpoint = json.loads((root / "checkpoints/pause_000001.json").read_text())
    assert checkpoint["state"] == "paused_drained"
    assert checkpoint["ledger"]["cached_logical_calls"] == 4
    assert not (root / "final_freeze.json").exists()
    original_receipts = tree(root / "api/calls")
    with pytest.raises(s.PauseRequested):
        build().run(api_factory=forbidden)
    assert state["calls"] == 4
    s.resume(root)
    result = build().run()
    assert result["complete"] and state["calls"] == 24 and state["children"] == 30
    assert all((root / "api/calls" / name).read_bytes() == body for name, body in original_receipts.items())
    assert len(list((root / "api/budget_reservations").glob("*.json"))) == 24


def test_prepare_opens_no_model_or_final_payload(fixture, monkeypatch):
    root, state, _, build = fixture
    monkeypatch.setattr(data, "materialize_split", forbidden)
    protocol = build().prepare()
    assert protocol["max_calls"] == 24
    assert state["calls"] == state["children"] == 0
    assert not (root / "final_freeze.json").exists()


def test_formal_design_budget_and_no_threshold_loosening(fixture):
    _, state, _, build = fixture
    study = build("formal")
    protocol = study.prepare()
    assert study.counts == {"confirmation": 64, "final": 128}
    assert study.maximum == 768 and protocol["gate"]["minimum_clusters"] == 64
    assert state["calls"] == state["children"] == 0


def test_symlink_run_rejected(fixture):
    root, _, _, build = fixture
    root.mkdir(parents=True)
    (root / "redirect").symlink_to(root.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        build()
