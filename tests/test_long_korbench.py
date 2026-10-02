"""Authored metadata/source fixtures, never real model or benchmark execution."""
import hashlib
import json
from copy import deepcopy

import pytest

from scripts import prepare_long_korbench as prepare
from scripts.prepare_long_baselines import PROXY, TRANSPORT
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import BENCHMARKS, build_plan, freeze_plan, read_json, write_json


def inputs(tmp_path):
    legacy = tmp_path / "old"
    tasks = []
    for category in sorted(prepare.CATEGORIES):
        for i in range(100):
            tasks.append({"task_id": f"{category}-{i}", "family_id": f"{category}-{i // 10}",
                "project_id": "", "partition": "development", "public": {"rule": "Authored rule", "question": "Q?"},
                "private": {"category": category, "rule_id": str(i // 10), "upstream_index": str(i),
                            "answer": "HOST_ONLY_SENTINEL"}})
    data = {"version": "continual-panel-v1", "benchmark": "korbench", "provenance": "natural",
            "dataset_revision": "authored-fixture-only", "tasks": tasks}
    panel = legacy / "data/panel.json"
    write_json(panel, data)
    native = tmp_path / "native"
    runtime = {"image": "sha256:" + "a" * 64, "timeout_seconds": 300, "memory_mb": 4096,
               "cpus": 1, "kor_repo": str(native)}
    for key, name in (("eval", "eval/eval_utils.py"), ("common", "utils/common.py"),
                      ("config", "config/config_wrapper.py")):
        path = native / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# authored never-executed scorer fixture\n")
        runtime["kor_" + key + "_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    config = {"version": "continual-eval-v1", "order": list(BENCHMARKS),
        "panels": {b: str(panel) if b == "korbench" else None for b in BENCHMARKS},
        "methods": ["no_skill"], "histories": ["h0"], "partition": "development", "repeats": 2,
        "project_disjoint": False, "exposure_manifest": None, "runtime": {"korbench": runtime},
        "model": {"provider": "bigmodel", "name": "glm-5.3", "max_tokens": 4096,
                  "reasoning_effort": "low", "proxy": PROXY}}
    old = build_plan(config)
    old.pop("record_hash")
    source = legacy / "skillopt/authored.py"
    source.parent.mkdir(parents=True)
    source.write_text("# authored historical source fixture\n")
    old["source_identity"] = {"authored.py": hashlib.sha256(source.read_bytes()).hexdigest()}
    write_json(legacy / "korbench-run/plan.json", seal(old))
    shared = deepcopy(config)
    shared["version"] = "continual-eval-v2"
    shared["model"].update(max_tokens=65536, transport=deepcopy(TRANSPORT))
    common = tmp_path / "common"
    freeze_plan(shared, common)
    return legacy, common, native


def test_full_panel_prep_replay_no_model_or_score(tmp_path, monkeypatch, capsys):
    legacy, common, native = inputs(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("Offline preparation must not execute models, native code or score answers")
    monkeypatch.setattr("skillopt.validator_pilot.api.CachedAPI", forbidden)
    monkeypatch.setattr("skillopt.continual_eval.backends.score", forbidden)
    monkeypatch.setattr("skillopt.continual_eval.backends._native", forbidden)
    before = {str(p): p.read_bytes() for r in (legacy, common, native) for p in r.rglob("*") if p.is_file()}
    out = tmp_path / "new"
    value = prepare.prepare(legacy, common, out)
    assert (value["tasks"], value["families"], value["positions"], value["model_calls"]) == (500, 50, 1000, 0)
    assert not value["old_answers_imported"] and not value["skill_updated"]
    assert prepare.check(out) == value
    assert before == {str(p): p.read_bytes() for r in (legacy, common, native) for p in r.rglob("*") if p.is_file()}
    assert prepare.main(["--check", "--output", str(out)]) == 0
    assert "HOST_ONLY_SENTINEL" not in capsys.readouterr().out
    with pytest.raises(ValueError, match="independent"):
        prepare.prepare(legacy, common, out)


@pytest.mark.parametrize("change", ["subset", "source", "native_source", "runtime", "budget", "final", "model"])
def test_reject_changed_inputs_before_writes(tmp_path, change):
    legacy, common, native = inputs(tmp_path)
    if change in {"source", "native_source"}:
        path = legacy / "skillopt/authored.py" if change == "source" else native / "eval/eval_utils.py"
        path.write_text("# changed\n")
    else:
        path = common / "plan.json" if change == "budget" else legacy / "korbench-run/plan.json"
        value = read_json(path, sealed=True)
        value.pop("record_hash")
        if change == "subset":
            value["tasks"] = value["tasks"][:-1]
        elif change == "runtime":
            value["config"]["runtime"]["korbench"]["memory_mb"] = 8192
        elif change == "budget":
            value["config"]["model"]["max_tokens"] = 8192
        elif change == "final":
            value["config"]["partition"] = "final"
        else:
            value["config"]["model"]["name"] = "another-model"
        path.write_text(json.dumps(seal(value)))
    out = tmp_path / "new"
    with pytest.raises(ValueError):
        prepare.prepare(legacy, common, out)
    assert not out.exists()


def test_later_native_change_breaks_check(tmp_path):
    legacy, common, native = inputs(tmp_path)
    out = tmp_path / "new"
    prepare.prepare(legacy, common, out)
    (native / "utils/common.py").write_text("# changed after freeze\n")
    with pytest.raises(ValueError, match="hash-pinned"):
        prepare.check(out)
