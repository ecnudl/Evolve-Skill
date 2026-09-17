"""Offline file-operation tests; synthetic receipts, no API or native execution.

The existing full scientific auditor has its own integration tests. Here its
full-result layer is stubbed, while the actual receipt and pacing readers remain
active, so we can test the exact 53/144 fork partition without model calls.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from scripts import prepare_coevolution_v7_checkpoint as checkpoint
from skillopt.coevolution_v5 import core
from skillopt.coevolution_v7 import transport
from skillopt.validator_pilot.api import digest


def save(path, value, *, sealed=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(core.seal(value) if sealed else value, sort_keys=True))


def fake_complete(run, repo, require_complete):
    assert require_complete is True
    protocol = checkpoint._payload(run / "protocol.json")
    result = checkpoint._payload(run / "results.json")
    assert result["status"] == "complete"
    for p, sha in protocol["source_hashes"].items():
        checkpoint._require(checkpoint._sha(repo / p) == sha, "Source changed")
    calls, ledger = checkpoint.audit.prior._receipts(run, protocol, True)
    pacing = checkpoint.audit._pacing(run, protocol, calls)
    checkpoint._require(ledger["ledger"] == result["ledger"], "Ledger changed")
    return core.seal({"complete": True, "fixture_only": True, "ledger": ledger, "pacing": pacing})


@pytest.fixture(scope="module")
def source_fixture(tmp_path_factory):
    repo = tmp_path_factory.mktemp("v7-checkpoint-fixture")
    source = repo / "outputs/coevolution_v7/original"
    source.mkdir(parents=True)
    sentinel = repo / "frozen.txt"
    sentinel.write_text("frozen fixture dependency")
    sleep = datetime.fromisoformat(checkpoint.SLEEP_START).timestamp()
    policy = vars(transport.PacingPolicy())
    service = {"max_retries": 2, "model": "glm-5.3", "fixture": "no network"}
    protocol = {"version": checkpoint.audit.experiment.VERSION, "histories": 2, "blocks": 4,
                "model": "glm-5.3", "workers": 4, "max_calls": 700, "pacing_policy": policy,
                "source_hashes": {"frozen.txt": checkpoint._sha(sentinel)}}
    for name in checkpoint.ROOT_KEEP:
        save(source / name, {"inherited_metadata": name}, sealed=True)
    save(source / "protocol.json", protocol, sealed=True)
    save(source / "panel.json", {"development": [{}] * 3, "calibration": [{}] * 6, "final": [{}] * 18}, sealed=True)
    save(source / "final_frozen.json", {"interventions": ["same fixed task/skill matrix"], "final_results_known": False}, sealed=True)
    save(source / "api/service.json", service)
    save(source / "api/budget_protocol.json", {"model": "glm-5.3", "workers": 4, "max_logical_calls": 700,
                                               "service_sha256": digest(service)})
    pacing = core.seal({"policy": policy, "service_hash": digest(service)})
    save(source / "api/pacing/protocol.json", pacing)
    calls, sequence = [], 0
    for i in range(197):
        kind = ("v5_coding_generate" if i < 36 and i % 2 == 0 else "v5_coding_revision" if i < 36 else
                "v5_validator_probe" if i < 48 else "v7_skill" if i < 52 else "v7_rubric_plan" if i == 52 else
                "v6_native_generate" if i % 2 else "v6_native_revision")
        request = {"model": "glm-5.3", "service": service, "kind": kind, "key": str(i)}
        h = digest(request)
        count = 2 if i < 2 or 53 <= i < 82 else 1
        refs, outcomes = [], []
        for attempt in range(1, count + 1):
            sequence += 1
            wall = sleep - 1000 + sequence * 4 if i < 53 else sleep - 20 + (sequence - 55) * 4
            admission = core.seal({"sequence": sequence, "request_hash": h, "protocol_hash": pacing["record_hash"],
                "attempt": attempt, "admitted_wall": wall, "admitted_monotonic": wall - (sleep - 2000),
                "waited_seconds": 0.0, "process_epoch": "one-fake-process", "kind": kind})
            outcome = {"attempt": attempt, "ok": attempt == count, "status": 200 if attempt == count else 503,
                       "error_type": None if attempt == count else "http_status", "wall_seconds": 1.0}
            receipt = core.seal({"sequence": sequence, "request_hash": h, "protocol_hash": pacing["record_hash"],
                "admission_hash": admission["record_hash"], "api_attempt": outcome, "cooldown_hash": None,
                "finished_wall": wall + 1})
            save(source / f"api/pacing/admissions/{sequence:08d}.json", admission)
            save(source / f"api/pacing/attempts/{sequence:08d}.json", receipt)
            refs.append({"sequence": sequence, "admission_hash": admission["record_hash"],
                         "attempt_receipt_hash": receipt["record_hash"]})
            outcomes.append(outcome)
        row = {"request": request, "request_hash": h, "ok": i not in {36, 37, 38, 39},
               "response": "", "error_type": "response_error" if i in {36, 37, 38, 39} else None,
               "http_attempt_count": count, "attempts": outcomes, "usage": {"completion_tokens": 2},
               "pacing": {"protocol_hash": pacing["record_hash"], "attempts": refs}}
        row["transport_diagnostic"] = transport.classify_failure(row)
        save(source / f"api/calls/{h}.json", row)
        save(source / f"api/budget_reservations/{h}.json", {"request_hash": h, "kind": kind})
        calls.append(h)
    assert sequence == 228
    for phase, pairs in (("development", [calls[i:i + 2] for i in range(0, 36, 2)]),
                         ("final", [calls[i:i + 2] for i in range(53, 197, 2)])):
        for i, hashes in enumerate(pairs):
            identity = {"kind": "v7_solve", "phase": phase, "test_index": i}
            h = digest({"namespace": "targets", "identity": identity})
            save(source / f"targets/{h}.json", {"identity": identity, "result": {"request_hashes": hashes,
                                                                                  "fixture_score": i % 2}}, sealed=True)
    for folder, count in (("feedback_probes", 12), ("skill_proposals", 4), ("source_initial", 2),
                          ("source_next", 2), ("research", 4)):
        for i in range(count):
            save(source / folder / f"fixture-{i}.json", {"not_reevaluated": True}, sealed=True)
    _, accounting = checkpoint.audit.prior._receipts(source, protocol, True)
    result = {"status": "complete", "calibration": None, "research": {"proposed_rubric": None, "calls_used": 1},
              "ledger": accounting["ledger"]}
    save(source / "results.json", result, sealed=True)
    save(source / "final_rows.json", {"scores": [0, 1]}, sealed=True)
    save(source / "final_summary.json", {"scores": "excluded together, never selected"}, sealed=True)
    return repo


@pytest.fixture
def run_copy(source_fixture, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    shutil.copytree(source_fixture, repo)
    source = repo / "outputs/coevolution_v7/original"
    clean = source.parent / "clean"
    archive = source.parent / "quarantined/original_sleep_excluded"
    monkeypatch.setattr(checkpoint.audit, "audit", fake_complete)
    return repo, source, clean, archive


def test_plan_is_readonly_and_whole_final_stage_not_score_selection(run_copy):
    repo, source, clean, archive = run_copy
    before = checkpoint._files(source)
    prepared = checkpoint.plan(*run_copy)
    assert len(prepared["inherited_request_hashes"]) == 53 and len(prepared["excluded_final_request_hashes"]) == 144
    assert len(prepared["inherited_terminal_error_hashes"]) == 4
    assert prepared["inherited_http_sequences"] == list(range(1, 56))
    assert prepared["excluded_final_http_sequences"] == list(range(56, 229))
    assert "final_frozen.json" in prepared["retained_files"]
    assert checkpoint.ROOT_EXCLUDE <= set(prepared["excluded_files"])
    assert prepared["parent_fork_id"] != prepared["fork_id"]
    assert prepared["inherited_training_is_not_new_independent_evidence"]
    assert not clean.exists() and not archive.exists() and checkpoint._files(source) == before


def test_apply_copies_unchanged_prefix_then_archives_intact_and_pauses(run_copy):
    repo, source, clean, archive = run_copy
    prepared = checkpoint.plan(*run_copy)
    original = checkpoint._files(source)
    receipt = checkpoint.apply(prepared, user_authorized=True, original_run_stopped=True)
    assert receipt["status"] == "paused_checkpoint_ready" and receipt["deleted_files"] == 0
    assert not source.exists() and checkpoint._files(archive) == original
    for p in prepared["retained_files"]:
        assert (clean / p).read_bytes() == (archive / p).read_bytes()
    assert all(not (clean / p).exists() for p in prepared["excluded_files"])
    manifest = checkpoint._json(clean / "exclusion_manifest.json", sealed=True)
    assert manifest["plan"] == prepared
    assert manifest["copied_prefix_audit"]["ledger"]["ledger"]["terminal_errors"] == 4
    assert manifest["copied_prefix_audit"]["pacing"]["http_attempt_admissions"] == 55
    assert manifest["plan"]["original_cost_ledger"]["cached_logical_calls"] == 197
    with pytest.raises(ValueError):
        checkpoint.apply(prepared, user_authorized=True, original_run_stopped=True)


@pytest.mark.parametrize("destination", ["checkpoint", "archive"])
def test_existing_destination_not_overwritten(run_copy, destination):
    _, source, clean, archive = run_copy
    target = clean if destination == "checkpoint" else archive
    target.mkdir(parents=True)
    (target / "user.txt").write_text("preserve")
    with pytest.raises(ValueError, match="absent destinations"):
        checkpoint.plan(*run_copy)
    assert source.exists() and (target / "user.txt").read_text() == "preserve"


@pytest.mark.parametrize("kind", ["source", "nested", "dangling", "destination_parent"])
def test_symlinks_fail_before_audit_or_writes(run_copy, monkeypatch, kind):
    repo, source, clean, archive = run_copy
    if kind == "source":
        linked = source.parent / "linked"
        linked.symlink_to(source, target_is_directory=True)
        source = linked
    elif kind in {"nested", "dangling"}:
        (source / "link").symlink_to(repo / ("frozen.txt" if kind == "nested" else "absent"))
    else:
        outside = repo / "outside"
        outside.mkdir()
        archive.parent.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(checkpoint.audit, "audit", lambda *_a, **_k: pytest.fail("preflight must precede audit"))
    with pytest.raises(ValueError, match="Symlink"):
        checkpoint.plan(repo, source, clean, archive)
    assert not clean.exists()


@pytest.mark.parametrize("kind", ["missing_result", "incomplete", "missing_reservation", "missing_attempt", "dependency"])
def test_incomplete_or_changed_source_rejected(run_copy, kind):
    repo, source, clean, _ = run_copy
    if kind == "missing_result":
        (source / "results.json").unlink()
    elif kind == "incomplete":
        record = checkpoint._payload(source / "results.json")
        record["status"] = "running"
        save(source / "results.json", record, sealed=True)
    elif kind == "missing_reservation":
        next((source / "api/budget_reservations").glob("*.json")).unlink()
    elif kind == "missing_attempt":
        (source / "api/pacing/attempts/00000055.json").unlink()
    else:
        (repo / "frozen.txt").write_text("changed")
    with pytest.raises((ValueError, AssertionError, FileNotFoundError)):
        checkpoint.plan(*run_copy)
    assert not clean.exists()


def test_sleep_boundary_cannot_be_moved_to_select_outcomes(run_copy):
    with pytest.raises(ValueError, match="fixed observed"):
        checkpoint.plan(*run_copy, sleep_start="2026-09-11T17:00:00+08:00")


def test_retained_completed_attempt_after_sleep_rejected(run_copy):
    _, source, clean, _ = run_copy
    path = source / "api/pacing/attempts/00000055.json"
    record = checkpoint._payload(path)
    record["finished_wall"] = datetime.fromisoformat(checkpoint.SLEEP_START).timestamp() + 1
    save(path, record, sealed=True)
    with pytest.raises(ValueError):
        checkpoint.plan(*run_copy)
    assert not clean.exists()


def test_selective_failure_only_removal_not_accepted(run_copy):
    _, source, clean, _ = run_copy
    bad = next(p for p in (source / "api/calls").glob("*.json") if not checkpoint._json(p)["ok"])
    bad.unlink()
    with pytest.raises(ValueError):
        checkpoint.plan(*run_copy)
    assert not clean.exists()


def test_apply_revalidates_source_and_user_authorization(run_copy):
    _, source, clean, _ = run_copy
    prepared = checkpoint.plan(*run_copy)
    with pytest.raises(ValueError, match="authorization"):
        checkpoint.apply(prepared)
    save(source / "source_initial/fixture-0.json", {"changed_after_plan": True}, sealed=True)
    with pytest.raises(ValueError, match="changed"):
        checkpoint.apply(prepared, user_authorized=True, original_run_stopped=True)
    assert source.exists() and not clean.exists()


def test_copy_failure_preserves_original_and_does_not_archive(run_copy, monkeypatch):
    _, source, clean, archive = run_copy
    prepared = checkpoint.plan(*run_copy)
    original = checkpoint._files(source)
    real_copy = shutil.copy2

    def broken_copy(src, dst, **kwargs):
        real_copy(src, dst, **kwargs)
        Path(dst).write_text("corrupted during copy")

    monkeypatch.setattr(checkpoint.shutil, "copy2", broken_copy)
    with pytest.raises(ValueError, match="Copied evidence bytes"):
        checkpoint.apply(prepared, user_authorized=True, original_run_stopped=True)
    assert checkpoint._files(source) == original and not archive.exists() and clean.exists()


def test_operations_never_construct_client_read_env_or_execute_oracle(run_copy, monkeypatch):
    def forbidden(*_a, **_k):
        raise AssertionError("No API, credentials or native execution")

    monkeypatch.setattr(transport, "make_budgeted_api", forbidden)
    monkeypatch.setattr(transport.PacedCachedAPI, "__init__", forbidden)
    monkeypatch.setattr(checkpoint.audit.CodingAdapter, "evaluate", forbidden)
    monkeypatch.setattr(checkpoint.audit.prior.NativeAdapter, "evaluate", forbidden)
    read = Path.read_text

    def safe_read(path, *args, **kwargs):
        assert not path.name.startswith(".env")
        return read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", safe_read)
    prepared = checkpoint.plan(*run_copy)
    assert checkpoint.apply(prepared, user_authorized=True, original_run_stopped=True)["status"] == "paused_checkpoint_ready"
