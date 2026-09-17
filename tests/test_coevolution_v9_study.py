"""Offline full native-learning study; fabricated data/transport, no paid calls."""

import json
from contextlib import contextmanager

import pyarrow as pa
import pyarrow.ipc as ipc
import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v9 import study as s
from skillopt.validator_pilot.api import digest


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def tree(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def forbidden(*args, **kwargs):
    pytest.fail("Completed replay/prepare must not write or open live transport")


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
        h = digest(request)
        path = self.root / "calls" / (h + ".json")
        if path.exists():
            return json.loads(path.read_text())
        self.state["calls"] += 1
        put(self.root / "budget_reservations" / (h + ".json"), {"request_hash": h, "kind": kind})
        patch = {"edits": [{"op": "append", "content": "Verify documented answer."}]}
        if kind == "v9_searchqa_solve":
            raw = "<answer>Alice</answer>" if "Verify documented answer" in system else "<answer>Bob</answer>"
        elif kind == "v9_native_analyst":
            raw = json.dumps({"batch_size": 4, "patch": patch})
        elif kind == "v9_native_merge":
            raw = json.dumps(patch)
        else:
            raw = json.dumps({"selected_indices": [0]})
        ok = not self.state.get("fail_all")
        row = {"request": request, "request_hash": h, "ok": ok, "response": raw if ok else "",
               "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2} if ok else {},
               "http_attempt_count": 1, "finish_reason": "stop", "error_type": None if ok else "timeout"}
        put(path, row)
        return row

    @staticmethod
    def parallel(jobs, fn, label):
        return [fn(job) for job in jobs]


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    initial = repo / "skillopt/envs/searchqa/skills/initial.md"
    initial.parent.mkdir(parents=True)
    initial.write_text("Initial skill.\n")
    caches = {}
    for split, offset in (("train", 0), ("validation", 1000)):
        rows = [{"key": f"{i + offset:032x}", "question": f"{split} question {i}?",
                 "context": "The person is Alice.", "answers": ["Alice"]} for i in range(600)]
        table = pa.Table.from_pylist(rows)
        caches[split] = tmp_path / (split + ".arrow")
        with pa.OSFile(str(caches[split]), "wb") as handle, ipc.new_stream(handle, table.schema) as writer:
            writer.write_table(table)
    state = {"calls": 0, "source_hash": "a" * 64}
    monkeypatch.setattr(s, "source_hashes", lambda _repo: {"fixture": state["source_hash"]})
    # Real pacing integrity has independent tests using real _Pacer records.
    monkeypatch.setattr(s, "audit_pacing", lambda *_args: {"offline_fixture": True})
    root = repo / "outputs/coevolution_v9/fixture"

    @contextmanager
    def factory(_repo, api_root, *, max_calls, workers):
        assert workers == 4
        yield FakeAPI(api_root, max_calls, state)

    def build(design="smoke"):
        return s.Study(repo, root, design=design, cache_paths=caches)

    return root, state, factory, build


def test_real_native_pipeline_two_gates_and_frozen_final(fixture):
    root, state, factory, build = fixture
    result = build().run(api_factory=factory)
    assert result["complete"] and result["smoke_not_effect_evidence"]
    history = result["histories"][0]
    assert history["candidate_changed"] and history["gate"]["standard_accept"]
    assert not history["gate"]["ours_accept"]
    assert history["skills"]["ours"]["skill_hash"] == history["parent_hash"]
    assert result["summary"]["n_observation_positions"] == 16
    assert result["summary"]["unique_actual_requests"] == 12
    assert 0 < state["calls"] == result["ledger"]["cached_logical_calls"] <= 56
    assert result["summary"]["policy_summary"]["skillopt"]["all_attempt_em"] == 1
    manifest = json.loads((root / "data_manifest.json").read_text())
    identity = (root / "learning/history_0/identity.json").read_text()
    for split in ("confirmation_h0_r0", "final"):
        assert all(row["id"] not in identity for row in manifest["splits"][split])
    for path in (root / "api/calls").glob("*.json"):
        row = json.loads(path.read_text())
        if row["request"]["kind"] == "v9_searchqa_solve":
            assert '"answers"' not in row["request"]["user"]


def test_completed_replay_is_offline_and_byte_identical(fixture, monkeypatch):
    root, state, factory, build = fixture
    expected = build().run(api_factory=factory)
    before, count = tree(root), state["calls"]
    monkeypatch.setattr(s, "write_immutable_json", forbidden)
    monkeypatch.setattr(s.learning, "write_immutable_json", forbidden)
    assert build().run(api_factory=forbidden) == expected
    assert tree(root) == before and state["calls"] == count


@pytest.mark.parametrize("missing", ["protocol.json", "data_manifest.json", "exposure_inventory.json",
    "final_freeze.json", "learning/history_0/result.json", "final_rows.json"])
def test_missing_completed_evidence_is_not_rebuilt(fixture, missing):
    root, state, factory, build = fixture
    build().run(api_factory=factory)
    (root / missing).unlink()
    before, count = tree(root), state["calls"]
    with pytest.raises((ValueError, FileNotFoundError)):
        build().run(api_factory=forbidden)
    assert before == tree(root) and count == state["calls"]


@pytest.mark.parametrize("directory", ["solves", "api/calls", "api/budget_reservations"])
def test_missing_completed_grid_is_not_repaired(fixture, directory):
    root, state, factory, build = fixture
    build().run(api_factory=factory)
    next((root / directory).glob("*.json")).unlink()
    before = tree(root)
    with pytest.raises((ValueError, FileNotFoundError)):
        build().run(api_factory=forbidden)
    assert before == tree(root)


def test_all_transport_failures_retained_without_semantic_learning(fixture):
    _, state, factory, build = fixture
    state["fail_all"] = True
    result = build().run(api_factory=factory)
    history = result["histories"][0]
    assert not history["candidate_changed"] and not history["gate"]["standard_accept"]
    assert history["optimizer_requests"] == []
    assert result["ledger"]["successful_calls"] == 0
    assert all(row["all_attempt_em"] == 0 for row in result["summary"]["policy_summary"].values())


def test_code_drift_blocks_final_access(fixture, monkeypatch):
    root, state, factory, build = fixture
    original = s.learning.propose_candidate

    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        state["source_hash"] = "b" * 64
        return result

    monkeypatch.setattr(s.learning, "propose_candidate", change)
    with pytest.raises(ValueError, match="Code changed"):
        build().run(api_factory=factory)
    assert not (root / "final_freeze.json").exists()


def test_resealed_gate_tampering_fails_replay(fixture):
    root, _, factory, build = fixture
    build().run(api_factory=factory)
    path = root / "histories/0.json"
    row = json.loads(path.read_text())
    row.pop("record_hash")
    row["gate"]["ours_accept"] = True
    put(path, seal(row))
    with pytest.raises(ValueError, match="Immutable"):
        build().run(api_factory=forbidden)


def test_source_design_and_nonempty_initial(fixture):
    _, _, _, build = fixture
    study = build("source")
    assert study.maximum == 1360 and len(study.histories) == 3
    assert sum(study.counts.values()) == 416 and study.counts["final"] == 128
    assert s.learning.text_hash(study.initial) != s.learning.text_hash("")


def test_prepare_never_materializes_or_calls_model(fixture, monkeypatch):
    root, state, _, build = fixture
    monkeypatch.setattr(s.data, "materialize_split", forbidden)
    build().prepare()
    assert state["calls"] == 0 and not (root / "final_freeze.json").exists()


def test_symlink_run_is_rejected(fixture):
    root, _, _, build = fixture
    root.mkdir(parents=True)
    (root / "redirect").symlink_to(root.parent, target_is_directory=True)
    with pytest.raises(ValueError, match="Symlink"):
        build()
