"""Closed handwritten actual-probe fixtures; never execute model code."""

import copy
import fcntl
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import coevolution_v14 as cli
from scripts import diagnose_coevolution_v14 as diagnostic
from scripts import report_coevolution_v14 as report
from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest


def put(path, value):
    value = seal({k: v for k, v in value.items() if k != "record_hash"})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return value


def score(success=1, *, oracle=True, delivery=True):
    return {"all_attempt_success": success, "oracle_available": oracle, "delivery_valid": delivery,
            "semantic_success": success if oracle else None}


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root = tmp_path / "outputs/coevolution_v14/diagnostic"
    root.mkdir(parents=True)
    (root / ".run.lock").touch()
    state = {"runs": 0, "action": None}
    class OfflineAPI:
        def call(self):
            pytest.fail("Unexpected model access")
    class Study:
        def __init__(self, repo, output, **kwargs):
            self.complete = (output / "results.json").exists()
            self.api_factory = kwargs["api_factory"]
        def run(self):
            state["runs"] += 1
            if state["action"]:
                return state["action"](self)
            return module.read(root / "results.json")
    def safe_root(repo, output):
        if Path(output) != root or any(p.is_symlink() for p in root.rglob("*")):
            raise ValueError("Unsafe root")
        return root
    module = SimpleNamespace(Study=Study, OfflineAPI=OfflineAPI, safe_root=safe_root,
        read=lambda p: verify(json.loads(p.read_text())), source_hashes=lambda repo: {})
    for target in (cli, diagnostic, report):
        monkeypatch.setattr(target, "study_module", lambda: module)
    preflight = put(root / "task_preflight.json", {"checked_tasks": 3, "checked_probe_tasks": 2,
        "checked_obligation_mutants": 8, "reference": "SECRET_REFERENCE_NOT_OUTPUT"})
    protocol = put(root / "protocol.json", {"design": "smoke", "max_calls": 64, "workers": 4,
        "source_hashes": {}, "histories": 1, "rounds": 1, "learning_arms": ["independent", "constrained"],
        "task_preflight_hash": preflight["record_hash"]})
    solves, paths, probe_paths = [], {}, {}
    for domain, phase, success in (("coding", "development", 1), ("spreadsheet", "development", 0),
                                  ("rule_reasoning", "final", 1)):
        task = f"{domain}-fixture"
        identity = {"task_hash": digest(task), "repeat": 0, "phase": phase}
        path = root / "runtime/solves" / (digest(identity) + ".json")
        row = put(path, {"identity": identity, "task_id": task, "domain": domain, "phase": phase,
            "cluster_id": task, "skill_hash": diagnostic.EMPTY_HASH, "chosen_stage": "revision",
            "stage_api_ok": [True, True], "score": score(success), "artifact": "SECRET_GENERATED_BODY",
            "request_hashes": [digest([task, step]) for step in (0, 1)]})
        solves.append(row)
        paths[domain] = path
    probes = []
    for row in solves[:2]:
        domain = row["domain"]
        task_hash = digest([domain, "probe"])
        key = digest({"solve_hash": row["record_hash"], "history": 0, "round": 0, "probe_task_hash": task_hash})
        identity = {"probe": True, "key": key}
        path = root / "runtime/probes/solves" / (digest(identity) + ".json")
        mapping = {"case1": "boundary", "case2": "preservation"}
        if domain == "coding":
            cases = [{"id": case + ":" + dimension, "passed": case == "case2" or dimension == "input_unchanged"}
                     for case in mapping for dimension in ("behavior", "input_unchanged")]
        else:
            cases = [{"id": case, "passed": case == "case2"} for case in mapping]
        probes.append(put(path, {"identity": identity, "phase": "development", "probe": True,
            "domain": domain, "key": key, "task_hash": task_hash, "source_task_id": row["task_id"],
            "source_task_hash": row["identity"]["task_hash"], "artifact_hash": digest(row["artifact"]),
            "execution_id": digest([domain, "actual probe execution"]), "case_obligations": mapping,
            "evaluation": {"case_results": cases, "private_body": "SECRET_EXPECTED"}, "score": score(0)}))
        probe_paths[domain] = path
    for arm in protocol["learning_arms"]:
        text = "SECRET_SKILL_TEXT" if arm == "constrained" else ""
        put(root / "learning" / f"h0-r0-{arm}.json", {"history": 0, "round": 0, "arm": arm,
            "valid": True, "changed": bool(text), "operations": ["SECRET_PATCH"] if text else [],
            "probe_hashes": [p["record_hash"] for p in probes] * 2 if text else [],
            "final_feedback_used": False, "skill": text, "skill_hash": hashlib.sha256(text.encode()).hexdigest()})
    final = solves[-1]
    grid = put(root / "final_rows.json", {"frozen_hash": digest("frozen"), "rows": [
        {"policy": policy, "chosen_stage": "revision", "rollback_reason": None, "score": final["score"],
         "solver_record_hash": final["record_hash"], "skill_hash": final["skill_hash"]}
        for policy in ("no_skill", "independent", "constrained")]})
    result = put(root / "results.json", {"complete": True, "protocol_hash": protocol["record_hash"],
        "frozen_hash": grid["frozen_hash"], "final_grid_hash": grid["record_hash"], "summary": {"positions": 3},
        "learning": {"proposals": 2, "valid": 2, "text_changes": 1, "local_operations": 1,
                     "probe_native_evaluations": 2},
        "evidence_closure": {"unique_trajectories": 3, "extra_probe_native_evaluations": 2}})
    return SimpleNamespace(repo=tmp_path, root=root, state=state, module=module, protocol=protocol, result=result,
                           solves=solves, probes=probes, paths=paths, probe_paths=probe_paths)


def run(f):
    return diagnostic.diagnose(f.root, repo=f.repo)


def change_probe(f, domain, **changes):
    path = f.probe_paths[domain]
    old = f.module.read(path)
    updated = put(path, {**old, **changes})
    learning_path = f.root / "learning/h0-r0-constrained.json"
    learning = f.module.read(learning_path)
    learning["probe_hashes"] = [updated["record_hash"] if h == old["record_hash"] else h for h in learning["probe_hashes"]]
    put(learning_path, learning)
    return updated


def test_actual_probes_and_mutant_calibration_are_separate_and_readonly(fixture):
    f = fixture
    before = cli.tree(f.root)
    result = run(f)
    assert cli.tree(f.root) == before
    assert result["model_api_calls"] == result["native_executions"] == result["files_written"] == 0
    assert result["authored_calibration_separate"]["checked_obligation_mutants"] == 8
    assert not result["authored_calibration_separate"]["is_actual_model_error_evidence"]
    actual = result["actual_model_probes"]
    assert actual["unique_model_artifact_evaluations"] == 2
    assert actual["by_domain"]["coding"]["oracle_evaluated_failure"] == 1
    assert actual["extra_cases_vs_ordinary_development"]["coding"]["ordinary_pass_probe_fail"] == 1
    assert actual["extra_cases_vs_ordinary_development"]["coding"]["ordinary_pass_probe_behavior_failure"] == 1
    assert actual["extra_cases_vs_ordinary_development"]["coding"]["no_skill_ordinary_pass_probe_fail"] == 1
    assert actual["extra_cases_vs_ordinary_development"]["spreadsheet"]["ordinary_fail_probe_fail"] == 1
    assert result["development_actual_solver"]["overall"]["unique_observations"] == 2
    assert result["final_delivery_only"]["unique_trajectories"] == 1
    assert "SECRET" not in json.dumps(result)


def test_preservation_success_does_not_hide_behavior_failure(fixture):
    actual = run(fixture)["actual_model_probes"]
    assert actual["obligation_behavior_by_domain"]["coding"]["boundary"] == {"pass": 0, "fail": 1, "unknown": 0}
    assert actual["input_preservation_separate_not_obligation_behavior"]["coding"] == {"pass": 2, "fail": 0, "unknown": 0}


def test_behavior_pass_does_not_hide_input_mutation(fixture):
    f = fixture
    raw = f.module.read(f.probe_paths["coding"])
    cases = [{"id": row["id"], "passed": row["id"].endswith(":behavior")} for row in raw["evaluation"]["case_results"]]
    change_probe(f, "coding", evaluation={"case_results": cases})
    actual = run(f)["actual_model_probes"]
    assert actual["obligation_behavior_by_domain"]["coding"]["boundary"]["pass"] == 1
    assert actual["input_preservation_separate_not_obligation_behavior"]["coding"]["fail"] == 2
    assert actual["by_domain"]["coding"]["oracle_evaluated_failure"] == 1
    novelty = actual["extra_cases_vs_ordinary_development"]["coding"]
    assert novelty["ordinary_pass_preservation_only_failure"] == 1
    assert novelty["ordinary_pass_probe_behavior_failure"] == 0


@pytest.mark.parametrize("delivery", [True, False])
def test_unavailable_probe_cases_never_count_as_behavior_failures(fixture, delivery):
    f = fixture
    change_probe(f, "coding", score=score(0, oracle=False, delivery=delivery))
    actual = run(f)["actual_model_probes"]
    for obligation in actual["obligation_behavior_by_domain"]["coding"].values():
        assert obligation == {"pass": 0, "fail": 0, "unknown": 1}
    assert actual["extra_cases_vs_ordinary_development"]["coding"]["probe_unknown"] == 1
    assert actual["extra_cases_vs_ordinary_development"]["coding"]["ordinary_pass_probe_fail"] == 0


def test_all_passing_probes_retain_explicit_zero_novel_failures(fixture):
    f = fixture
    raw = f.module.read(f.probe_paths["coding"])
    for case in raw["evaluation"]["case_results"]:
        case["passed"] = True
    change_probe(f, "coding", score=score(), evaluation=raw["evaluation"])
    actual = run(f)["actual_model_probes"]
    assert actual["by_domain"]["coding"]["pass"] == 1
    assert not any(actual["extra_cases_vs_ordinary_development"]["coding"].values())


def test_role_aliases_do_not_multiply_actual_probe_counts(fixture):
    output = run(fixture)
    # Lexical ordering is not used to identify an arm.
    constrained = next(r for r in output["learning_updates"] if r["arm"] == "constrained")
    assert constrained["probe_refs"] == 4
    assert output["actual_model_probes"]["unique_model_artifact_evaluations"] == 2
    assert constrained["skill_chars"] == len("SECRET_SKILL_TEXT")


@pytest.mark.parametrize("name,raw,api,expected", [
    ("success", score(), True, "pass"),
    ("rollback_success", score(), False, "pass"),
    ("semantic", score(0), True, "oracle_evaluated_failure"),
    ("delivery", score(0, oracle=False, delivery=False), True, "delivery_invalid"),
    ("api", score(0, oracle=False, delivery=False), False, "delivery_api_unavailable"),
    ("unknown", score(0, oracle=False), True, "delivered_oracle_unknown")])
def test_delivery_and_oracle_failure_classes(name, raw, api, expected):
    assert diagnostic._class(raw, api) == expected


def test_frozen_source_guard_and_complete_requirement_precede_score_reads(fixture):
    f = fixture
    (f.root / "results.json").unlink()
    (f.root / "runtime/solves/unclosed.json").write_text("do not read me")
    before = cli.tree(f.root)
    with pytest.raises(ValueError, match="Completed results"):
        run(f)
    assert cli.tree(f.root) == before and f.state["runs"] == 0


@pytest.mark.parametrize("action", ["factory", "api", "native"])
def test_actual_replay_api_and_execution_guards(fixture, action):
    f = fixture
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
        run(f)


def test_exclusive_writer_blocks_even_completed_diagnostic(fixture):
    f = fixture
    with (f.root / ".run.lock").open("rb") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            run(f)
    assert f.state["runs"] == 0


@pytest.mark.parametrize("mutation", ["source", "artifact", "key", "phase", "task_hash"])
def test_probe_cannot_substitute_reference_final_or_different_source(fixture, mutation):
    f = fixture
    change = {"source_task_id": "reference-control"} if mutation == "source" else {
        "artifact_hash": digest("reference")} if mutation == "artifact" else {
        "key": digest("wrong-history")} if mutation == "key" else {
        "phase": "final"} if mutation == "phase" else {"task_hash": digest("other-probe")}
    change_probe(f, "coding", **change)
    with pytest.raises(ValueError):
        run(f)


@pytest.mark.parametrize("mutation", ["missing_behavior", "extra", "duplicate", "not_bool"])
def test_available_coding_probe_requires_complete_boolean_behavior_grid(fixture, mutation):
    f = fixture
    raw = f.module.read(f.probe_paths["coding"])
    rows = raw["evaluation"]["case_results"]
    if mutation == "missing_behavior":
        rows.pop(0)
    elif mutation == "extra":
        rows.append({"id": "extra:behavior", "passed": True})
    elif mutation == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    else:
        rows[0]["passed"] = 1
    change_probe(f, "coding", evaluation={"case_results": rows})
    with pytest.raises(ValueError):
        run(f)


def test_missing_actual_probe_cannot_be_counted_from_calibration(fixture):
    f = fixture
    f.probe_paths["coding"].unlink()
    with pytest.raises(ValueError, match="do not close"):
        run(f)


def test_learning_text_hash_binds_character_count(fixture):
    f = fixture
    path = f.root / "learning/h0-r0-constrained.json"
    put(path, {**f.module.read(path), "skill": "different"})
    with pytest.raises(ValueError, match="text hash"):
        run(f)


def test_calibration_cannot_silently_change(fixture):
    f = fixture
    path = f.root / "task_preflight.json"
    put(path, {**f.module.read(path), "checked_obligation_mutants": 100})
    with pytest.raises(ValueError, match="Calibration evidence"):
        run(f)


def test_main_outputs_only_the_completed_projection(fixture, monkeypatch, capsys):
    f = fixture
    monkeypatch.setattr(diagnostic, "REPO", f.repo)
    original = diagnostic.diagnose
    monkeypatch.setattr(diagnostic, "diagnose", lambda output: original(output, repo=f.repo))
    assert diagnostic.main(["--output", str(f.root)]) == 0
    output = capsys.readouterr().out
    assert "SECRET" not in output and json.loads(output)["files_written"] == 0
