"""Authored protocol/launcher controls; no model, native evaluator, or network.

Natural-shaped fixture labels exercise the production preparation checks only;
these files are not real tasks, historical evidence, or a method-effect study.
"""
import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import prepare_long_baselines as prepare
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import BENCHMARKS, build_plan, load_plan, read_json, write_json
from skillopt.continual_learning.contracts import manifest


def legacy_inputs(tmp_path):
    old_learning, old_eval = tmp_path / "old-learning", tmp_path / "old-evaluation"
    tasks = [{"task_id": str(i), "family_id": str(i if i < 399 else 0), "project_id": "",
              "partition": "development", "public": {"prompt": "Authored fixture implement solve.", "entry_point": "solve"},
              "private": {"test": "HOST_ONLY_TEST_CANARY"}} for i in range(400)]
    data = {"version": "continual-panel-v1", "benchmark": "bigcodebench", "dataset_revision": "authored-old-v1",
            "provenance": "natural", "tasks": tasks}
    selected = {**deepcopy(data), "tasks": [t for t in tasks if int(t["family_id"]) < 128]}
    panel_path = old_eval / "data/development.json"
    write_json(panel_path, data)
    write_json(old_learning / "data/panel.json", selected)
    model = {"provider": "bigmodel", "name": "glm-5.3", "reasoning_effort": "low", "max_tokens": 4096,
             "proxy": prepare.PROXY}
    config = {"version": "continual-eval-v1", "order": list(BENCHMARKS),
              "panels": {b: str(panel_path) if b == "bigcodebench" else None for b in BENCHMARKS},
              "partition": "development", "methods": ["no_skill"], "histories": ["h0"], "repeats": 2,
              "model": model, "runtime": {"bigcodebench": {"memory_mb": 8192, "timeout_seconds": 300}},
              "project_disjoint": False, "exposure_manifest": None}
    # Minimal authored historical source roster, not a claim about real source.
    for root in (old_learning, old_eval):
        (root / "skillopt").mkdir(parents=True)
        (root / "skillopt/authored.py").write_text("# authored historical test source\n")
    source_hashes = {"authored.py": hashlib.sha256((old_eval / "skillopt/authored.py").read_bytes()).hexdigest()}
    plan = build_plan(config)
    plan.pop("record_hash")
    plan["source_identity"] = source_hashes
    write_json(old_eval / "run/plan.json", seal(plan))
    for method in ("skillopt", "gepa"):
        value = manifest(selected, train_families=[str(i) for i in range(64)],
                         selection_families=[str(i) for i in range(64, 128)], model=deepcopy(model),
                         budget=deepcopy(prepare.OLD_BUDGET), runtime=config["runtime"]["bigcodebench"],
                         method=method, seed=20260928)
        value.pop("record_hash")
        value["source_identity"] = source_hashes
        write_json(old_learning / "manifests" / (method + ".json"), seal(value))
    return old_learning, old_eval


def no_api(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Preparation must not open an API client or execute a native evaluator")
    monkeypatch.setattr("skillopt.validator_pilot.api.CachedAPI", forbidden)
    monkeypatch.setattr("skillopt.continual_eval.backends.readiness", forbidden)
    monkeypatch.setattr("skillopt.continual_eval.backends.score", forbidden)


def test_freezes_common_new_configuration_preserves_old_data_and_roles(tmp_path, monkeypatch):
    old_learning, old_eval = legacy_inputs(tmp_path)
    before = {str(p): p.read_bytes() for root in (old_learning, old_eval) for p in root.rglob("*") if p.is_file()}
    no_api(monkeypatch)
    study = tmp_path / "new-study"
    value = prepare.prepare(study, legacy_learning_root=old_learning, legacy_no_skill_root=old_eval)
    assert value["evaluation_tasks"] == 400 and value["evaluation_positions"] == 800
    assert value["train_tasks"] == 65 and value["train_families"] == value["selection_tasks"] == value["selection_families"] == 64
    assert value["model_calls"] == 0 and not value["optimizer_resumed"] and not value["old_answers_imported"]
    assert "not_new_holdout" in value["data_provenance"]
    assert prepare.check(study) == value
    plan = load_plan(study / "no_skill")
    assert plan["version"] == "continual-eval-v2" and len(plan["tasks"]) == 400 and plan["repeats"] == 2
    assert plan["config"]["methods"] == ["no_skill"] and plan["config"]["partition"] == "development"
    assert all(v is None for k, v in plan["config"]["panels"].items() if k != "bigcodebench")
    assert not plan["evolution_enabled"] and not plan["protocol_complete"]
    for method in ("skillopt", "gepa"):
        old = read_json(old_learning / "manifests" / (method + ".json"), sealed=True)
        new = read_json(study / "manifests" / (method + ".json"), sealed=True)
        assert new["version"] == "continual-learning-v2"
        for key in ("train_families", "selection_families", "authorized_tasks", "runtime", "seed", "parent_skill"):
            assert old[key] == new[key]
        assert new["parent_skill"] == ""
        assert new["budget"] == {**old["budget"], "solver_max_tokens": 65536}
        assert new["model"] == plan["config"]["model"]
        assert new["model"]["transport"] == prepare.TRANSPORT and new["model"]["proxy"] == prepare.PROXY
        assert new["budget"]["reflection_max_tokens"] == 4096
    assert before == {str(p): p.read_bytes() for root in (old_learning, old_eval) for p in root.rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="new study"):
        prepare.prepare(study, legacy_learning_root=old_learning, legacy_no_skill_root=old_eval)


@pytest.mark.parametrize("corruption", ["budget", "parent", "family", "source", "panel", "final", "count", "proxy"])
def test_bad_legacy_inputs_fail_before_creating_new_study(tmp_path, corruption):
    old_learning, old_eval = legacy_inputs(tmp_path)
    if corruption == "source":
        (old_eval / "skillopt/authored.py").write_text("# changed\n")
    elif corruption in {"panel", "final", "count"}:
        path = old_learning / "data/panel.json"
        value = read_json(path)
        if corruption == "panel":
            value["tasks"][0]["public"]["prompt"] = "changed public task"
        elif corruption == "final":
            for task in value["tasks"]:
                task["partition"] = "final"
        else:
            value["tasks"].pop()
        path.write_text(json.dumps(value))
    else:
        path = old_learning / "manifests/skillopt.json"
        value = read_json(path, sealed=True)
        value.pop("record_hash")
        if corruption == "budget":
            value["budget"]["reflection_max_tokens"] = 8192
        elif corruption == "parent":
            value["parent_skill"] = "illicit parent"
        elif corruption == "proxy":
            value["model"]["proxy"] = "http://unexpected.example:3128"
        else:
            value["train_families"][0] = "64"
        path.write_text(json.dumps(seal(value)))
    study = tmp_path / "new-study"
    with pytest.raises(ValueError):
        prepare.prepare(study, legacy_learning_root=old_learning, legacy_no_skill_root=old_eval)
    assert not study.exists()


def test_check_detects_changed_prepared_manifest_before_launch(tmp_path):
    old_learning, old_eval = legacy_inputs(tmp_path)
    study = tmp_path / "new-study"
    prepare.prepare(study, legacy_learning_root=old_learning, legacy_no_skill_root=old_eval)
    path = study / "manifests/gepa.json"
    value = read_json(path, sealed=True)
    value.pop("record_hash")
    value["model"]["transport"]["stream"] = False
    path.write_text(json.dumps(seal(value)))
    with pytest.raises(ValueError, match="Frozen study inputs"):
        prepare.check(study)


def test_cli_only_prints_summary(tmp_path, capsys):
    old_learning, old_eval = legacy_inputs(tmp_path)
    study = tmp_path / "new-study"
    assert prepare.main(["--output", str(study), "--legacy-learning-root", str(old_learning),
                         "--legacy-no-skill-root", str(old_eval)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["model_calls"] == 0 and summary["evaluation_positions"] == 800
    assert "HOST_ONLY_TEST_CANARY" not in json.dumps(summary)
    assert prepare.main(["--check", "--output", str(study)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "validated_not_launched"


def shell_harness(tmp_path):
    """Record launcher argv and lock/proxy boundaries without starting clients."""
    fakebin = tmp_path / "bin"
    fakebin.mkdir()
    code = f"#!{sys.executable}\n" + '''
import json, os, pathlib, sys
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["TEST_BASELINE_COMMAND_LOG"], "a") as out:
    out.write(json.dumps({"name": name, "args": args, "native_lock": os.environ.get("TEST_NATIVE_LOCK_HELD"),
                          "proxy": os.environ.get("TEST_PROXY_ON")}) + "\\n")
if name == "uname":
    print("Linux")
elif name == "flock":
    os.environ["TEST_NATIVE_LOCK_HELD"] = args[0]
    os.execvp(args[1], args[1:])
elif name == "bash":
    assert args[0] == "-ic" and "proxy_on >/dev/null && exec" in args[1]
    os.environ["TEST_PROXY_ON"] = "1"
    command = args[args.index("--") + 1:]
    os.execvp(command[0], command)
elif name == "fake-python":
    if "scripts.run_continual_learning" in args:
        assert os.environ.get("TEST_NATIVE_LOCK_HELD") and os.environ.get("TEST_PROXY_ON") == "1"
        method = args[args.index("--method") + 1]
        sys.exit(int(os.environ.get("TEST_SKILLOPT_STATUS", "0")) if method == "skillopt" else 0)
    if "generate" in args:
        assert not os.environ.get("TEST_NATIVE_LOCK_HELD") and os.environ.get("TEST_PROXY_ON") == "1"
        assert args[args.index("--workers") + 1] == "6"
        sys.exit(int(os.environ.get("TEST_GENERATE_STATUS", "0")))
    if "score" in args:
        assert os.environ.get("TEST_NATIVE_LOCK_HELD")
    print("{}")
'''
    for name in ("uname", "flock", "bash", "fake-python"):
        path = fakebin / name
        path.write_text(code)
        path.chmod(0o700)
    study = tmp_path / "study"
    study.mkdir()
    log = tmp_path / "commands.jsonl"
    env = {**os.environ, "PATH": str(fakebin) + os.pathsep + os.environ["PATH"], "TEST_BASELINE_COMMAND_LOG": str(log)}
    script = Path(__file__).parents[1] / "scripts/run_long_baselines_linux.sh"
    args = ["/bin/bash", str(script), "MODE", str(study), str(fakebin / "fake-python"),
            str(tmp_path / "credential-repo"), str(tmp_path / "gepa-source")]
    return args, env, log, study


@pytest.mark.parametrize("mode,status", [("learning", 0), ("learning", 3), ("no_skill", 0), ("no_skill", 1)])
def test_shell_fixed_argv_proxy_lock_and_independent_scoring(tmp_path, mode, status):
    args, env, log, study = shell_harness(tmp_path)
    args[2] = mode
    env["TEST_SKILLOPT_STATUS" if mode == "learning" else "TEST_GENERATE_STATUS"] = str(status)
    result = subprocess.run(args, env=env, text=True, capture_output=True, timeout=20)
    assert result.returncode == status, result.stderr
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    calls = [row for row in rows if row["name"] == "fake-python"]
    if mode == "learning":
        methods = [r["args"][r["args"].index("--method") + 1] for r in calls if "--method" in r["args"]]
        assert methods == (["skillopt", "gepa"] if status == 0 else ["skillopt"])
        assert all(r["native_lock"] == str(study / "native.lock") for r in calls if "--execute" in r["args"])
    else:
        assert [r["args"][2] for r in calls[1:]] == ["generate", "score", "report"]
        assert next(r for r in calls if "score" in r["args"])["native_lock"] == str(study / "native.lock")
    assert "HOST_ONLY" not in result.stdout
    before = {str(p): p.read_bytes() for p in (study / "launches").rglob("*") if p.is_file()}
    repeated = subprocess.run(args, env=env, text=True, capture_output=True, timeout=20)
    assert repeated.returncode != 0
    assert before == {str(p): p.read_bytes() for p in (study / "launches").rglob("*") if p.is_file()}


def test_shell_syntax():
    subprocess.run(["bash", "-n", str(Path(__file__).parents[1] / "scripts/run_long_baselines_linux.sh")], check=True)
