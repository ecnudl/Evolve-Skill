"""Authored metadata fixtures only; no API or real benchmark evaluation."""
import hashlib
import json
from copy import deepcopy

import pytest

from scripts import prepare_long_searchqa as prepare
from scripts.prepare_long_baselines import PROXY, TRANSPORT
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import BENCHMARKS, build_plan, freeze_plan, read_json, write_json


def inputs(tmp_path):
    legacy = tmp_path / "old"
    tasks = [{"task_id": str(i), "family_id": str(i), "project_id": "", "partition": "development",
              "public": {"question": "Authored fixture?", "context": "Authored fixture context."},
              "private": {"answers": ["HOST_ONLY_SENTINEL"]}} for i in range(400)]
    data = {"version": "continual-panel-v1", "benchmark": "searchqa", "provenance": "natural",
            "dataset_revision": "authored-fixture-only", "tasks": tasks}
    panel = legacy / "data/panel.json"
    write_json(panel, data)
    config = {"version": "continual-eval-v1", "order": list(BENCHMARKS),
        "panels": {b: str(panel) if b == "searchqa" else None for b in BENCHMARKS},
        "methods": ["no_skill"], "histories": ["h0"], "partition": "development", "repeats": 2,
        "project_disjoint": False, "exposure_manifest": None, "runtime": {},
        "model": {"provider": "bigmodel", "name": "glm-5.3", "max_tokens": 4096,
                  "reasoning_effort": "low", "proxy": PROXY}}
    old = build_plan(config)
    old.pop("record_hash")
    path = legacy / "skillopt/authored.py"
    path.parent.mkdir(parents=True)
    path.write_text("# authored fixture only\n")
    old["source_identity"] = {"authored.py": hashlib.sha256(path.read_bytes()).hexdigest()}
    write_json(legacy / "run/plan.json", seal(old))
    shared = deepcopy(config)
    shared.update(version="continual-eval-v2")
    shared["model"].update(max_tokens=65536, transport=deepcopy(TRANSPORT))
    common = tmp_path / "common"
    freeze_plan(shared, common)
    return legacy, common


def test_freezes_all_tasks_no_answers_or_paid_calls(tmp_path, monkeypatch, capsys):
    legacy, common = inputs(tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("Preparation must not call models or execute candidates")
    monkeypatch.setattr("skillopt.validator_pilot.api.CachedAPI", forbidden)
    monkeypatch.setattr("skillopt.continual_eval.backends.score", forbidden)
    before = {str(p): p.read_bytes() for r in (legacy, common) for p in r.rglob("*") if p.is_file()}
    out = tmp_path / "new"
    value = prepare.prepare(legacy, common, out)
    assert value["positions"] == 800 and value["model_calls"] == 0 and not value["old_answers_imported"]
    assert prepare.check(out) == value
    assert before == {str(p): p.read_bytes() for r in (legacy, common) for p in r.rglob("*") if p.is_file()}
    assert prepare.main(["--check", "--output", str(out)]) == 0
    assert "HOST_ONLY_SENTINEL" not in capsys.readouterr().out
    with pytest.raises(ValueError, match="independent"):
        prepare.prepare(legacy, common, out)


@pytest.mark.parametrize("change", ["panel", "source", "budget", "final", "subset", "runtime"])
def test_bad_inputs_do_not_start_a_study(tmp_path, change):
    legacy, common = inputs(tmp_path)
    if change in {"panel", "source"}:
        path = legacy / ("data/panel.json" if change == "panel" else "skillopt/authored.py")
        path.write_text("{}")
    else:
        path = common / "plan.json" if change == "budget" else legacy / "run/plan.json"
        value = read_json(path, sealed=True)
        value.pop("record_hash")
        if change == "budget":
            value["config"]["model"]["max_tokens"] = 8192
        elif change == "final":
            value["config"]["partition"] = "final"
        elif change == "subset":
            value["tasks"] = value["tasks"][:-1]
        else:
            value["config"]["runtime"] = {"searchqa": {"unexpected": True}}
        path.write_text(json.dumps(seal(value)))
    out = tmp_path / "new"
    with pytest.raises((ValueError, KeyError)):
        prepare.prepare(legacy, common, out)
    assert not out.exists()
