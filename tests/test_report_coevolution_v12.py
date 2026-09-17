"""Offline metadata-only V12 report fixtures: no task execution or model calls."""

import copy
import fcntl
import json

import pytest

from scripts import report_coevolution_v12 as report
from skillopt.coevolution_v5.core import seal
from skillopt.coevolution_v12 import analysis
from skillopt.validator_pilot.api import digest


def put(path, value):
    value = {k: v for k, v in value.items() if k != "record_hash"}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(seal(value)), encoding="utf-8")
    return seal(value)


def formal_summary():
    rows, expected = [], {}
    for domain in analysis.DOMAINS:
        for cluster in range(4):
            task = f"{domain}-{cluster}"
            metadata = {"domain": domain, "cluster_id": str(cluster)}
            expected[task] = metadata
            for history in range(3):
                for policy in analysis.POLICIES:
                    arm = policy.removeprefix("selected_")
                    skill = analysis.EMPTY_SKILL_HASH if arm == "no_skill" else digest([arm, history])
                    success = int(arm != "independent" or cluster > 0)
                    rows.append({"task_id": task, **metadata, "history": history, "policy": policy,
                        "skill_hash": skill, "request_hashes": [digest([task, skill, i]) for i in (0, 1)],
                        "score": {"all_attempt_success": success, "semantic_success": success,
                                  "oracle_available": True, "delivery_valid": True}})
    return analysis.summarize(rows, expected, bootstrap_samples=100)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root = tmp_path / "outputs/coevolution_v12/test"
    root.mkdir(parents=True)
    (root / ".run.lock").touch()
    protocol = put(root / "protocol.json", {"design": "formal", "histories": 3, "rounds": 3,
        "learning_arms": ["independent", "contrastive"], "model": "glm-5.3",
        "source_hashes": {"docs/coevolution-v12-protocol.md": "frozen"}})
    proposals = []
    for h in range(3):
        for r in range(3):
            for arm in protocol["learning_arms"]:
                identity = {"history": h, "round": r, "arm": arm}
                key = f"h{h}-r{r}-{arm}.json"
                row = {**identity, "valid": True, "changed": r != 1,
                       "reason": "valid_text_candidate", "skill": "SECRET_SKILL_SENTINEL"}
                put(root / "learning" / key, row)
                put(root / "selection" / key, {**identity, "accept": r == 0,
                                               "skill": "SECRET_SELECTION_SENTINEL"})
                proposals.append({**row, "accepted": r == 0})
    put(root / "private_panel.json", {"body": "SECRET_TASK_BODY_SENTINEL"})
    result = put(root / "results.json", {"complete": True, "design": "formal",
        "protocol_hash": protocol["record_hash"], "summary": formal_summary(),
        "learning": {"proposals": 18, "valid": 18, "text_changes": 12, "selection_acceptances": 6},
        "ledger": {"cached_logical_calls": 120, "max_logical_calls": 1536,
            "http_attempts_from_cached_records": 122, "successful_calls": 119, "terminal_errors": 1,
            "prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500,
            "missing_usage_calls": 1}})
    state = {"calls": 0, "mutate": None}

    class Replay:
        def __init__(self, repo, output, *, design, api_factory):
            assert output == root and design in ("formal", "smoke")
            self.complete = True
            self.api_factory = api_factory

        def run(self):
            state["calls"] += 1
            if state["mutate"]:
                return state["mutate"](self)
            return report.study.read(root / "results.json")

    monkeypatch.setattr(report.study, "Study", Replay)
    monkeypatch.setattr(report.study, "source_hashes", lambda repo: protocol["source_hashes"])
    return {"repo": tmp_path, "root": root, "target": tmp_path / "docs/report.md",
            "protocol": protocol, "result": result, "proposals": proposals, "state": state}


def publish(f):
    return report.report(f["root"], f["target"], repo=f["repo"])


def test_full_report_metadata_complete_and_zero_side_effects(fixture):
    f = fixture
    before = report._tree(f["root"])
    result = publish(f)
    text = f["target"].read_text()
    assert result["created"] and result["model_api_calls"] == result["native_executions"] == 0
    assert f["state"]["calls"] == 1 and report._tree(f["root"]) == before
    for word in ("NoSkill", "Independent（raw）", "Contrastive（raw）", "selected 诊断", "Coding",
                 "Spreadsheet", "Rule Reasoning", "各历史", "Holm", "95% CI", "全部 18", "120/1536",
                 "+25.00 pp", "1 次缺少 usage", "非原生 SkillOpt", "DeepResearch", "可评失败", "4 个结构家族",
                 "0.125", "不能在 0.05 水平确认 Rule 增益"):
        assert word in text
    assert "SECRET_" not in text
    assert not publish(f)["created"]
    assert report._tree(f["root"]) == before


def test_smoke_is_explicitly_not_scientific_inference(fixture):
    f = fixture
    protocol = {**f["protocol"], "design": "smoke", "histories": 1, "rounds": 1}
    result = {**f["result"], "summary": {"positions": 10, "smoke_only": True,
        "scientific_inference": False, "success_by_policy": dict.fromkeys(analysis.POLICIES, 0.5)}}
    audit = {"verified_run_files": 12, "record_hash": "audit"}
    text = report.render(protocol, result, audit, f["proposals"][:2])
    assert "smoke 工程验收，不作效果推断" in text and "50.00%" in text
    assert "Holm 校正 p" not in text and "95% CI" not in text
    assert "包含全部 2 次候选" in text


def test_supervisor_append_between_reports_preserves_immutable_report(fixture):
    path = fixture["root"] / "supervisor.log"
    path.write_text("started\n")
    initial_tree = report._tree(fixture["root"])
    first = publish(fixture)
    assert report._tree(fixture["root"]) == initial_tree
    content = fixture["target"].read_bytes()
    path.write_text("started\nreport JSON\nfinished\n")
    updated_tree = report._tree(fixture["root"])
    second = publish(fixture)
    assert report._tree(fixture["root"]) == updated_tree
    assert first["audit_hash"] == second["audit_hash"]
    assert first["report_sha256"] == second["report_sha256"]
    assert not second["created"] and fixture["target"].read_bytes() == content
    assert "仅排除根级 supervisor.log" in content.decode()


def test_supervisor_mutation_during_replay_still_rejected(fixture):
    path = fixture["root"] / "supervisor.log"
    path.write_text("before")
    def mutate(_):
        path.write_text("after")
        return fixture["result"]
    fixture["state"]["mutate"] = mutate
    with pytest.raises(ValueError, match="changed experiment files"):
        publish(fixture)
    assert not fixture["target"].exists()


@pytest.mark.parametrize("relative", ["other.log", "nested/supervisor.log"])
def test_only_exact_root_supervisor_log_is_excluded(fixture, relative):
    path = fixture["root"] / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("before")
    publish(fixture)
    content = fixture["target"].read_bytes()
    path.write_text("after")
    with pytest.raises(ValueError, match="overwrite"):
        publish(fixture)
    assert fixture["target"].read_bytes() == content


@pytest.mark.parametrize("name", ["results.json", ".run.lock"])
def test_missing_completed_prerequisite_never_replays(fixture, name):
    (fixture["root"] / name).unlink()
    with pytest.raises(ValueError, match="Completed result"):
        publish(fixture)
    assert fixture["state"]["calls"] == 0


@pytest.mark.parametrize("field,value", [("complete", False), ("protocol_hash", "wrong")])
def test_invalid_completion_binding(fixture, field, value):
    put(fixture["root"] / "results.json", {**fixture["result"], field: value})
    with pytest.raises(ValueError, match="binding"):
        publish(fixture)
    assert fixture["state"]["calls"] == 0


def test_shared_lock_refuses_active_writer(fixture):
    with (fixture["root"] / ".run.lock").open("rb") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            publish(fixture)
    assert not fixture["target"].exists()


def test_changed_report_is_not_overwritten(fixture):
    fixture["target"].parent.mkdir()
    fixture["target"].write_text("user report")
    with pytest.raises(ValueError, match="overwrite"):
        publish(fixture)
    assert fixture["target"].read_text() == "user report"


def test_replay_mutation_blocks_publication(fixture):
    def mutate(_):
        (fixture["root"] / "bad.txt").write_text("mutation")
        return fixture["result"]
    fixture["state"]["mutate"] = mutate
    with pytest.raises(ValueError, match="changed experiment files"):
        publish(fixture)
    assert not fixture["target"].exists()


def test_different_replayed_result_blocks_publication(fixture):
    fixture["state"]["mutate"] = lambda _: {**fixture["result"], "extra": True}
    with pytest.raises(ValueError, match="replay differs"):
        publish(fixture)


@pytest.mark.parametrize("action", ["api_factory", "api_call", "execution"])
def test_replay_execution_and_api_tripwires(fixture, action):
    def attempt(replay):
        if action == "api_factory":
            replay.api_factory()
        elif action == "api_call":
            report.study.OfflineAPI.call(None)
        else:
            report.runtime.legacy.evaluate(None)
    fixture["state"]["mutate"] = attempt
    with pytest.raises(ValueError, match="model access or native execution"):
        publish(fixture)
    assert not fixture["target"].exists()


def test_frozen_source_drift_blocks_publication(fixture, monkeypatch):
    monkeypatch.setattr(report.study, "source_hashes", lambda repo: {"drift": True})
    with pytest.raises(ValueError, match="Frozen sources"):
        publish(fixture)


@pytest.mark.parametrize("directory", ["learning", "selection"])
@pytest.mark.parametrize("orphan", [True, False])
def test_learning_grid_exact_set(fixture, directory, orphan):
    root = fixture["root"] / directory
    if orphan:
        put(root / "orphan.json", {})
    else:
        (root / "h0-r0-independent.json").unlink()
    with pytest.raises(ValueError, match="incomplete or orphaned"):
        publish(fixture)


def test_learning_aggregate_requires_all_records(fixture):
    result = copy.deepcopy(fixture["result"])
    result["learning"]["valid"] -= 1
    put(fixture["root"] / "results.json", result)
    with pytest.raises(ValueError, match="summary disagrees"):
        publish(fixture)


def test_selection_identity_match(fixture):
    path = fixture["root"] / "selection/h0-r0-independent.json"
    row = report.study.read(path)
    put(path, {**row, "round": 1})
    with pytest.raises(ValueError, match="identity mismatch"):
        publish(fixture)


@pytest.mark.parametrize("path", ["outside.md", "docs/report.txt", "docs/coevolution-v12-protocol.md"])
def test_target_scope_and_frozen_source_protection(fixture, path):
    fixture["target"] = fixture["repo"] / path
    with pytest.raises(ValueError, match="Markdown file|frozen sources"):
        publish(fixture)


def test_symlink_target_rejected(fixture):
    fixture["target"].parent.mkdir()
    (fixture["repo"] / "other.md").write_text("keep")
    fixture["target"].symlink_to(fixture["repo"] / "other.md")
    with pytest.raises(ValueError, match="Symlink report"):
        publish(fixture)


def test_main_cli_arguments(monkeypatch, capsys, tmp_path):
    calls = []
    def fake(output, target):
        calls.append((output, target))
        return {"ok": True}
    monkeypatch.setattr(report, "report", fake)
    assert report.main(["--output", str(tmp_path / "out"), "--report", str(tmp_path / "r.md")]) == 0
    assert calls == [(tmp_path / "out", tmp_path / "r.md")]
    assert json.loads(capsys.readouterr().out) == {"ok": True}
