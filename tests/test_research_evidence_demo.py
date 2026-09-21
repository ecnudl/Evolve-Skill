"""Published real-record excerpts: offline consistency, never artifact execution."""
import hashlib
import json
import shutil
import socket
import subprocess

import pytest

from scripts.replay_research_demo import DEFAULT_ROOT, inspect_package, main


def test_real_record_counts_and_unknown_pairing():
    result = inspect_package()
    assert result["final_tasks"] == 16 and result["final_positions"] == 96
    assert result["rates"]["no_skill"] == {
        "pass": 30, "fail": 2, "unknown": 0, "positions": 32, "all_attempt_success": .9375}
    assert result["rates"]["parent"]["pass"] == 26
    assert result["rates"]["candidate"]["pass"] == 27
    assert result["paired"]["candidate_vs_parent"] == {"win": 2, "loss": 0, "tie": 26, "unknown": 4}
    assert result["paired"]["candidate_vs_no_skill"] == {"win": 0, "loss": 0, "tie": 29, "unknown": 3}
    assert result["method_effect_established"] is False
    assert result["raw_source_authenticity_verified"] is False


def test_read_only_without_network_or_subprocess(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("No network, subprocess or generated code execution is allowed")

    before = {p: p.read_bytes() for p in DEFAULT_ROOT.rglob("*") if p.is_file()}
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    result = inspect_package()
    assert result["model_calls"] == 0 and result["executed_artifact_code"] is False
    assert all(p.read_bytes() == content for p, content in before.items())


def test_diagnostics_keep_disagreement_and_no_execution_claim():
    cases = {r["id"]: r for r in inspect_package()["cases"]}
    dispute = [r for r in cases["audit_disagreement"]["recorded_diagnostics"] if r["args"] == ["é.txt"]]
    assert {r["condition"]: r["actual"] for r in dispute} == {
        "canonical_reference": "Yes", "current": "No", "no_skill": "No"}
    assert all(r["public_expected"] == "No" for r in dispute)
    assert not cases["public_check_blindspot"]["recorded_diagnostics"]
    assert all(r["new_probe_execution_claimed"] is False for r in cases.values())


def test_cli_json_and_skill_diff(capsys):
    assert main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["final_positions"] == 96
    assert main(["--show-skill-diff"]) == 0
    assert "--- parent" in capsys.readouterr().out
    with pytest.raises(SystemExit) as error:
        main(["--json", "--show-skill-diff"])
    assert error.value.code == 2


@pytest.fixture
def copied(tmp_path):
    target = tmp_path / "demo"
    shutil.copytree(DEFAULT_ROOT, target)
    return target


def rewrite(root, name, mutate, *, reseal=True):
    path = root / name
    data = json.loads(path.read_text())
    mutate(data)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if reseal:
        manifest = json.loads((root / "manifest.json").read_text())
        manifest["files"][name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                   "bytes": path.stat().st_size}
        (root / "manifest.json").write_text(json.dumps(manifest))


def test_file_tampering_detected(copied):
    rewrite(copied, "cases/power_boundary.json", lambda c: c.update(research_credit=True), reseal=False)
    with pytest.raises(ValueError, match="checksum mismatch"):
        inspect_package(copied)


@pytest.mark.parametrize("damage", ["missing", "duplicate", "invalid_status", "relabel_final"])
def test_final_rows_not_silently_dropped_or_reclassified(copied, damage):
    def mutate(d):
        if damage == "missing":
            d["rows"].pop()
        elif damage == "duplicate":
            d["rows"][0] = d["rows"][1]
        elif damage == "invalid_status":
            d["rows"][0]["status"] = "not_applicable"
        else:
            d["partition"] = "development"

    rewrite(copied, "single_round_final_outcomes.json", mutate)
    with pytest.raises(ValueError):
        inspect_package(copied)


@pytest.mark.parametrize("damage", ["code", "artifact", "observation", "research", "feedback"])
def test_case_bindings_remain_honest_even_if_manifest_recomputed(copied, damage):
    def mutate(c):
        if damage == "code":
            c["artifacts"][0]["solution_py"] += "# changed\n"
        elif damage == "artifact":
            c["artifacts"][0]["source"]["original_record_hash"] = "0" * 64
        elif damage == "observation":
            c["diagnostics"][0]["execution"]["actual"] = "invented"
        elif damage == "research":
            c["research_credit"] = True
        else:
            c["diagnostics"][0]["used_by_updater"] = True

    rewrite(copied, "cases/power_boundary.json", mutate)
    with pytest.raises(ValueError):
        inspect_package(copied)


@pytest.mark.parametrize("bad_path", ["../outside", "/tmp/outside", "a\\outside"])
def test_manifest_cannot_read_outside_package(copied, bad_path):
    path = copied / "manifest.json"
    m = json.loads(path.read_text())
    m["files"][bad_path] = {"sha256": "0" * 64, "bytes": 0}
    path.write_text(json.dumps(m))
    with pytest.raises(ValueError, match="Unsafe package path"):
        inspect_package(copied)


def test_symlink_refused(copied):
    p = copied / "skill_update/parent.md"
    content = p.read_bytes()
    other = copied.parent / "outside.md"
    other.write_bytes(content)
    p.unlink()
    p.symlink_to(other)
    with pytest.raises(ValueError, match="symlinks"):
        inspect_package(copied)


def test_no_unreviewed_secret_or_execution_fields_in_export():
    for p in DEFAULT_ROOT.rglob("*.json"):
        text = p.read_text()
        for marker in ('"api_key"', '"authorization"', '"ssh_transport"', '"reference_code"',
                       '"plus_input"', '"base_input"', '/Users/', '/root/'):
            assert marker not in text, (p.relative_to(DEFAULT_ROOT), marker)


def test_failed_cli_is_nonzero(tmp_path, capsys):
    with pytest.raises(SystemExit) as error:
        main(["--root", str(tmp_path)])
    assert error.value.code == 2
    assert "Evidence replay refused" in capsys.readouterr().err
