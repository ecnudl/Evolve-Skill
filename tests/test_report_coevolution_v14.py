"""Offline report fixtures: no actual tasks, model calls or generated execution."""

import copy
import fcntl
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import coevolution_v14 as cli
from scripts import report_coevolution_v14 as report
from skillopt.coevolution_v5.core import seal, verify
from skillopt.coevolution_v14 import analysis
from skillopt.validator_pilot.api import digest


def put(path, value):
    value = seal({k: v for k, v in value.items() if k != "record_hash"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return value


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root = tmp_path / "outputs/coevolution_v14/fixture"
    root.mkdir(parents=True)
    (root / ".run.lock").touch()
    (root / "supervisor.log").write_text("operational metadata\n")
    state = {"runs": 0, "action": None, "source_hashes": {}}
    class OfflineAPI:
        def call(self):
            pytest.fail("Unexpected API call")
    class Study:
        def __init__(self, repo, output, **kwargs):
            self.complete = (output / "results.json").is_file()
            self.api_factory = kwargs["api_factory"]
            assert kwargs["workers"] == 4
        def run(self):
            state["runs"] += 1
            if state["action"]:
                return state["action"](self)
            return module.read(root / "results.json")
    def safe_root(repo, output):
        output = Path(output).absolute()
        if (output != root or any(p.is_symlink() for p in (output, *output.parents))
                or any(p.is_symlink() for p in root.rglob("*"))):
            raise ValueError("Unsafe experiment output")
        return output
    module = SimpleNamespace(Study=Study, OfflineAPI=OfflineAPI, safe_root=safe_root,
        read=lambda path: verify(json.loads(path.read_text())), source_hashes=lambda repo: state["source_hashes"])
    monkeypatch.setattr(cli, "study_module", lambda: module)
    monkeypatch.setattr(report, "study_module", lambda: module)

    def prepare(design="smoke", *, alias=False, revision=False):
        histories, rounds, families = (1, 1, 1) if design == "smoke" else (3, 2, 8)
        protocol = put(root / "protocol.json", {"design": design, "model": "glm-5.3", "workers": 4,
            "max_calls": 64 if design == "smoke" else 640, "histories": histories, "rounds": rounds,
            "learning_arms": ["independent", "constrained"], "source_hashes": state["source_hashes"]})
        proposals, probe_ids = [], set()
        for h in range(histories):
            for r in range(rounds):
                for arm in protocol["learning_arms"]:
                    probes = [digest([h, r, i]) for i in range(2)] if arm == "constrained" else []
                    probe_ids.update(probes)
                    proposals.append(put(root / "learning" / f"h{h}-r{r}-{arm}.json", {
                        "history": h, "round": r, "arm": arm, "valid": True, "changed": True,
                        "operations": ["SECRET_OPERATION"] if arm == "constrained" else [],
                        "probe_hashes": probes, "final_feedback_used": False,
                        "skill": "SECRET_SKILL_BODY", "reason": "SECRET_MODEL_REPLY"}))
        expected, rows = {}, []
        for domain in analysis.DOMAINS:
            for family in range(families):
                task = f"{domain}-{family}"
                expected[task] = {"domain": domain, "cluster_id": f"{domain}-f{family}"}
                for h in range(histories):
                    for policy in analysis.POLICIES:
                        text = "independent" if alias and policy == "constrained" else policy
                        skill_hash = analysis.EMPTY_SKILL_HASH if policy == "no_skill" else digest([text, h])
                        requests = [digest([task, h, skill_hash, i]) for i in range(2)]
                        rollback = revision and policy != "no_skill"
                        rows.append({"task_id": task, **expected[task], "history": h, "policy": policy,
                            "skill_hash": skill_hash, "request_hashes": requests, "solver_record_hash": digest(requests),
                            "score": {"all_attempt_success": 1, "delivery_valid": True,
                                      "oracle_available": True, "semantic_success": 1},
                            "chosen_stage": "generation" if rollback else "revision",
                            "rollback_reason": "revision_delivery_invalid" if rollback else None})
        frozen_hash = digest("frozen fixture")
        grid = put(root / "final_rows.json", {"rows": rows, "frozen_hash": frozen_hash})
        summary = analysis.summarize(rows, expected, bootstrap_samples=100) if design == "formal" else {
            "smoke_only": True, "positions": len(rows), "scientific_inference": False,
            "success_by_policy": dict.fromkeys(analysis.POLICIES, 1)}
        result = put(root / "results.json", {"complete": True, "design": design,
            "protocol_hash": protocol["record_hash"], "frozen_hash": frozen_hash, "final_grid_hash": grid["record_hash"],
            "summary": summary, "learning": {"proposals": len(proposals), "valid": len(proposals),
                "text_changes": len(proposals), "local_operations": sum(len(p["operations"]) for p in proposals),
                "probe_native_evaluations": len(probe_ids)},
            "evidence_closure": {"extra_probe_native_evaluations": len(probe_ids),
                "unique_solver_requests": 18, "unique_optimizer_requests": len(proposals)},
            "ledger": {"cached_logical_calls": 20, "max_logical_calls": protocol["max_calls"],
                "http_attempts_from_cached_records": 21, "successful_calls": 19, "terminal_errors": 1,
                "prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500, "missing_usage_calls": 1}})
        return protocol, result
    return SimpleNamespace(repo=tmp_path, root=root, target=tmp_path / "docs/results.md", module=module,
                           state=state, prepare=prepare)


def publish(f):
    return report.report(f.root, f.target, repo=f.repo)


def test_smoke_report_is_offline_immutable_and_not_science(fixture):
    f = fixture
    f.prepare()
    before = cli.tree(f.root)
    first, second = publish(f), publish(f)
    text = f.target.read_text()
    assert first["created"] and not second["created"]
    assert first["audit_hash"] == second["audit_hash"]
    assert first["model_api_calls"] == first["native_executions"] == 0
    assert "仅为 smoke 工程验收" in text and "预设主比较" not in text
    assert "SECRET" not in text
    assert cli.tree(f.root) == before and f.state["runs"] == 2


def test_formal_report_preserves_primary_exploratory_and_budget_limits(fixture):
    f = fixture
    f.prepare("formal")
    publish(f)
    text = f.target.read_text()
    for expected in ("24 个新合成任务", "72 条实际轨迹、144 次请求", "macro", "spreadsheet",
                     "Holm", "Independent −", "8 家族", "0.0078125", "零宽 bootstrap", "全部 12 次更新",
                     "不等 oracle/context 预算", "未运行 DeepResearch", "并非同一检验", "缺少 usage"):
        # The direction is explicitly documented using the actual primary label.
        if expected == "Independent −":
            expected = "Constrained − Independent"
        assert expected in text
    assert "| NoSkill | 100.00% | 100.00% | 100.00% | 100.00% | 100.00% | 0.00 pp |" in text
    assert "selected" not in text and "不能把跨版本分数差直接归因" in text
    assert "SECRET" not in text


def test_aliases_count_rollbacks_once_but_keep_policy_positions(fixture):
    f = fixture
    _, result = f.prepare("formal", alias=True, revision=True)
    delivery = report._delivery_summary(f.root, result)
    assert delivery["unique_trajectories"] == 144 and delivery["unique_rollbacks"] == 72
    assert delivery["by_policy_positions"]["constrained"]["revision_delivery_invalid"] == 72
    publish(f)
    assert "去重后最终 144 条真实轨迹中，72 条触发交付保护" in f.target.read_text()


def test_empty_legal_abstention_is_not_reported_as_learned_generalization(fixture):
    f = fixture
    f.prepare()
    grid = f.module.read(f.root / "final_rows.json")
    base = {r["task_id"]: r for r in grid["rows"] if r["policy"] == "no_skill"}
    for row in grid["rows"]:
        if row["policy"] == "constrained":
            for key in ("skill_hash", "request_hashes", "solver_record_hash"):
                row[key] = copy.deepcopy(base[row["task_id"]][key])
    grid = put(f.root / "final_rows.json", grid)
    result = f.module.read(f.root / "results.json")
    result = put(f.root / "results.json", {**result, "final_grid_hash": grid["record_hash"]})
    summary = report._delivery_summary(f.root, result)
    assert summary["unique_trajectories"] == 6
    assert summary["skill_coverage_positions"]["constrained"] == {"positions": 3, "nonempty": 0}
    publish(f)
    text = f.target.read_text()
    assert "| Constrained | 0/3 |" in text and "合法保留/弃权" in text
    assert "其无退化不能证明已学出泛化能力" in text


@pytest.mark.parametrize("method", ["append", "create"])
def test_supervisor_log_changes_do_not_break_report_idempotence(fixture, method):
    f = fixture
    f.prepare()
    log = f.root / "supervisor.log"
    if method == "create":
        log.unlink()
    first = publish(f)
    log.write_text("supervisor appended finished metadata\n")
    before = cli.tree(f.root)
    second = publish(f)
    assert first["audit_hash"] == second["audit_hash"] and first["report_sha256"] == second["report_sha256"]
    assert cli.tree(f.root) == before and not second["created"]


def test_changed_scientific_evidence_changes_commitment_not_existing_report(fixture):
    f = fixture
    f.prepare()
    publish(f)
    original = f.target.read_bytes()
    (f.root / "new_evidence.json").write_text("{}")
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        publish(f)
    assert f.target.read_bytes() == original


@pytest.mark.parametrize("action", ["factory", "api", "native"])
def test_report_replay_guards_model_and_native_execution(fixture, action):
    f = fixture
    f.prepare()
    def attempt(study):
        if action == "factory":
            study.api_factory()
        elif action == "api":
            f.module.OfflineAPI.call(None)
        else:
            from skillopt.coevolution_v14 import runtime
            runtime.legacy.evaluate(None)
    f.state["action"] = attempt
    with pytest.raises(ValueError, match="model access or native execution"):
        publish(f)
    assert not f.target.exists()


def test_incomplete_report_never_creates_run_or_doc(fixture):
    with pytest.raises(ValueError, match="Completed results"):
        publish(fixture)
    assert not fixture.target.exists()


def test_writer_lock_blocks_report(fixture):
    f = fixture
    f.prepare()
    with (f.root / ".run.lock").open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            publish(f)
    assert f.state["runs"] == 0


@pytest.mark.parametrize("mutation", ["missing", "orphan", "identity", "final_feedback", "summary", "probes"])
def test_learning_grid_and_summary_disagreement_block_publication(fixture, mutation):
    f = fixture
    f.prepare()
    path = f.root / "learning/h0-r0-independent.json"
    proposal = f.module.read(path)
    if mutation == "missing":
        path.unlink()
    elif mutation == "orphan":
        put(f.root / "learning/orphan.json", proposal)
    elif mutation == "identity":
        put(path, {**proposal, "history": 4})
    elif mutation == "final_feedback":
        put(path, {**proposal, "final_feedback_used": True})
    else:
        result = f.module.read(f.root / "results.json")
        if mutation == "summary":
            result["learning"]["valid"] = 0
        else:
            result["evidence_closure"]["extra_probe_native_evaluations"] = 0
        put(f.root / "results.json", result)
    with pytest.raises(ValueError):
        publish(f)
    assert not f.target.exists()


@pytest.mark.parametrize("mutation", ["binding", "frozen", "guard", "count"])
def test_final_grid_metadata_is_closed(fixture, mutation):
    f = fixture
    f.prepare()
    grid = f.module.read(f.root / "final_rows.json")
    if mutation == "binding":
        grid["extra"] = True
    elif mutation == "frozen":
        grid["frozen_hash"] = digest("wrong")
    elif mutation == "guard":
        grid["rows"][0]["chosen_stage"] = "generation"
    else:
        grid["rows"].pop()
    updated = put(f.root / "final_rows.json", grid)
    if mutation != "binding":
        result = f.module.read(f.root / "results.json")
        put(f.root / "results.json", {**result, "final_grid_hash": updated["record_hash"]})
    with pytest.raises(ValueError):
        publish(f)
    assert not f.target.exists()


def test_report_cannot_replace_frozen_source(fixture):
    f = fixture
    f.state["source_hashes"] = {"docs/results.md": digest("frozen")}
    f.prepare()
    with pytest.raises(ValueError, match="frozen sources"):
        publish(f)


@pytest.mark.parametrize("target", ["outside.md", "docs/results.txt", "outputs/coevolution_v14/fixture/report.md"])
def test_bad_report_path_is_rejected(fixture, target):
    f = fixture
    f.prepare()
    with pytest.raises(ValueError, match="Markdown"):
        report.report(f.root, f.repo / target, repo=f.repo)


def test_report_symlink_is_rejected(fixture):
    f = fixture
    f.prepare()
    f.target.parent.mkdir()
    f.target.symlink_to(f.repo / "elsewhere.md")
    with pytest.raises(ValueError, match="Markdown"):
        publish(f)


def test_report_source_drift_blocks_before_publication(fixture):
    f = fixture
    f.prepare()
    def changed(_):
        f.state["source_hashes"] = {"new": "drift"}
        return f.module.read(f.root / "results.json")
    f.state["action"] = changed
    with pytest.raises(ValueError, match="source drift"):
        publish(f)
    assert not f.target.exists()


def test_render_does_not_mutate_inputs(fixture):
    f = fixture
    protocol, result = f.prepare("formal")
    original = copy.deepcopy((protocol, result))
    proposals = report._learning_rows(f.root, protocol, result)
    delivery = report._delivery_summary(f.root, result)
    report.render(protocol, result, {"verified_evidence_files": 42, "record_hash": "audit"}, proposals, delivery)
    assert (protocol, result) == original


def test_main_delegates_only_to_completed_report(fixture, monkeypatch, capsys):
    f = fixture
    def fake(output, target):
        assert output == f.root and target == f.target
        return {"model_api_calls": 0, "native_executions": 0}
    monkeypatch.setattr(report, "report", fake)
    assert report.main(["--output", str(f.root), "--report", str(f.target)]) == 0
    assert json.loads(capsys.readouterr().out) == {"model_api_calls": 0, "native_executions": 0}
