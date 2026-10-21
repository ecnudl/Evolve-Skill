"""Runner v2 of the generalization feedback study: v3 generations on both sides, single-part diagnostic items in the
study's v1 derivation shape, both sides' fidelity sealed with the pools, the registered go/no-go (fidelity, informative
diagnostic items, difficulty against the real training items), and the unchanged study run on v3 derivations."""
import json
from copy import deepcopy

import pytest

from scripts import build_training_profile as builder
from scripts import generate_officeqa_feature_tasks as gen3
from scripts import run_generalization_feedback_study_v2 as runner
from scripts import weak_solver_probe as probe
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import read_json, write_json
from skillopt.continual_learning.recovery import POLICY_V10
from skillopt.feedback_study import error_modes as em
from skillopt.feedback_study import generalization_feedback as gf
from skillopt.validator_pilot.api import digest
from tests.test_continual_learning_officeqa_generated_validation import PAGES, _study
from tests.test_feedback_study_generalization_feedback import GenAPI, _probe_dir
from tests.test_generate_officeqa_feature_tasks import STDEV, FeatureWriter

PARENT = "Read the table.\n"
MODEL = {"provider": "fixture", "name": "fixture", "max_tokens": 65536, "reasoning_effort": "low",
         "transport": {"stream": True, "read_timeout_seconds": 300, "stream_wall_seconds": 3600,
                       "initial_health_policy": "completed_response_v1"}}


def _derivation(parts, figures=STDEV["figures"]):
    values = {f["name"]: gen3.v1.figure(f["value"]) for f in figures}
    return {"source_task_hash": "s", "question": STDEV["question"], "figures": deepcopy(figures),
            "parts": parts, "answer": gen3.answer_text(gen3._answers(parts, values)), "type": "stdev"}


def test_a_single_part_v3_derivation_feeds_the_studys_code_layer_and_leak_check():
    stat = runner.v1_shape(_derivation(STDEV["parts"]))
    assert set(stat) == {"source_task_hash", "question", "figures", "expression", "decimals", "answer", "category"}
    assert stat["expression"] == "stdev_pop(a, b, c)" and stat["decimals"] == 3 and stat["category"] == "stdev"
    pages = PAGES % "u1.txt"
    diagnosis = em.diagnose(stat, pages, "<answer>1</answer>")  # outside v1's grammar: no variant search
    assert diagnosis["mode"] == "derivation_unavailable" and diagnosis["expected"] == stat["answer"]
    note = em.render(stat, diagnosis, 2000)
    assert "expected %s" % stat["answer"] in note and "stdev_pop(a, b, c)" in note and "| 1934 | 4,908 | 507 |" in note
    assert gf.derivation_leak("Compute stdev_pop(a, b, c) for these rows.", {"x": stat})[0]["what"] == "expression"
    assert gf.derivation_leak("The answer is %s." % stat["answer"], {"x": stat})[0]["what"] == "answer"
    assert not gf.derivation_leak("Use the population standard deviation for complete periods.", {"x": stat})
    # a v1-grammar expression keeps the variant search
    ratio = runner.v1_shape(_derivation([{"expression": "(b - a) / a * 100", "decimals": 2}], STDEV["figures"][:2]))
    assert ratio["answer"] == "20.21"
    assert em.diagnose(ratio, pages, "<answer>0.2021</answer>")["mode"] == "power_of_ten"
    with pytest.raises(ValueError):  # a multi-part item has no v1-shaped derivation
        runner.v1_shape(_derivation([{"expression": "stdev_pop(a, b, c)", "decimals": 3},
                                     {"expression": "mean(a, b, c)", "decimals": 0}]))


# ----------------------------------------------------------------------------- a template, a split, two generations
def _material(tmp_path, monkeypatch):
    from scripts import run_fivebench_g_stage as tool

    where = _study(tmp_path, monkeypatch)
    split = read_json(where[1], sealed=True)
    dev = read_json(tmp_path / "study" / "dev_panel.json")
    train, _ = tool.train_tasks(dev, split, "officeqa", 3)
    panel = {**{k: v for k, v in dev.items() if k != "tasks"}, "tasks": deepcopy(train)}
    stage = tmp_path / "template"
    write_json(stage / "panel.json", panel)
    manifest = seal({"benchmark": "officeqa", "panel_hash": digest(panel), "seed": 3, "parent_skill": PARENT,
                     "train_families": sorted({t["family_id"] for t in train}), "model": deepcopy(MODEL),
                     "runtime": {}, "recovery_policy": deepcopy(POLICY_V10)})
    write_json(stage / "manifest.json", manifest)
    write_json(stage / "stage.json", seal({"manifest_hash": manifest["record_hash"], "native_lock": str(tmp_path / "lock"),
                                           "repo": str(tmp_path), "learning_model_service": {"fixture": True},
                                           "client_options": {}}))
    ids = sorted(t["task_id"] for t in train)
    write_json(tmp_path / "lh.json", seal({"learn_tasks": ids[:4], "held_out_tasks": ids[4:],
                                           "manifest_hash": manifest["record_hash"]}))
    lh = str(tmp_path / "lh.json")
    builder.build(tmp_path / "study" / "dev_panel.json", tmp_path / "profile.json", partition="development",
                  tasks_spec="%s:learn_tasks" % lh)
    profile = str(tmp_path / "profile.json")
    for side, name in (("learn", "g"), ("held_out", "t")):
        gen3.prepare(*where, str(tmp_path / name), str(tmp_path), side=side, seed=3, lh_split=lh, profile=profile)
        assert gen3.run(str(tmp_path / name), fixture_api=FeatureWriter())["status"] == "completed"
    return {"where": where, "stage": str(stage), "lh": lh, "profile": profile, "g": str(tmp_path / "g"),
            "t": str(tmp_path / "t"), "train": train}


def _reference(path, tasks, parent, passes, *, runs=2, model="glm-5.3", **settings):
    """A completed probe of ``parent`` (named bzero) on ``tasks``: the first ``passes`` runs in task order pass."""
    items = path.parent / (path.name + "-items.json")
    items.write_text(json.dumps({"tasks": tasks}))
    rows = probe.load_items("%s:development" % items)
    config = {"version": probe.VERSION, "model": model, "reasoning_effort": "low", "benchmark": "officeqa", "runs": runs,
              **settings,
              "items": ["%s:development" % items], "item_ids_hash": probe.digest(sorted(r["id"] for r in rows)),
              "n_items": len(rows),
              "items_hash": probe.digest(sorted(probe.digest(r) for r in rows)),
              "skills": {"bzero": {"hash": probe.digest(parent), "bytes": len(parent)}}}
    path.mkdir(parents=True)
    (path / "config.json").write_text(json.dumps(config))
    for n, task in enumerate(sorted(tasks, key=lambda t: t["task_id"])):
        for run in range(runs):
            target = path / "records" / "bzero" / ("%s.%d.json" % (probe.digest(task["task_id"])[:24], run))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"skill": "bzero", "item": task["task_id"], "run": run,
                                          "status": "pass" if n * runs + run < passes else "fail"}))
    (path / "summary.json").write_text(json.dumps({"status": "completed", "config_hash": probe.digest(config)}))
    return "%s:bzero" % path


def test_pools_keep_single_part_diagnostic_items_and_seal_both_sides_fidelity(tmp_path, monkeypatch):
    m = _material(tmp_path, monkeypatch)
    summary = runner.pools(m["stage"], m["lh"], m["g"], m["t"], m["profile"], tmp_path / "pools")
    assert len(summary["diagnostic_candidates"]) == 4 and summary["multi_part_learn_items_left_out"] == 4
    assert len(summary["transfer_items"]) == 6  # the transfer pool keeps the two-part items
    derivations = read_json(tmp_path / "pools" / "derivations.json", sealed=True)["derivations"]
    assert set(derivations) == set(summary["diagnostic_candidates"])
    assert all(d["expression"] == "stdev_pop(a, b, c)" and d["decimals"] == 3 for d in derivations.values())
    pool_t = read_json(tmp_path / "pools" / "pool-T.json")["tasks"]
    assert sum(t["private"]["answer"].startswith("[") for t in pool_t) == 3
    assert {t["partition"] for t in pool_t} == {"skill_confirmation"}
    # statistics items against a lookup-only training profile: the registered fidelity fails on both sides
    assert summary["fidelity"]["learn"]["passed"] is False and summary["fidelity"]["held_out"]["passed"] is False
    assert summary["fidelity"]["learn"]["limits"] == gen3.FIDELITY_LIMITS and summary["runner"] == runner.VERSION
    with pytest.raises(ValueError):  # written once
        runner.pools(m["stage"], m["lh"], m["g"], m["t"], m["profile"], tmp_path / "pools")
    with pytest.raises(ValueError):  # the sides swapped
        runner.pools(m["stage"], m["lh"], m["t"], m["g"], m["profile"], tmp_path / "p1")
    builder.build(tmp_path / "study" / "dev_panel.json", tmp_path / "all.json", partition="development")
    with pytest.raises(ValueError):  # fidelity only against the profile the generations were prepared with
        runner.pools(m["stage"], m["lh"], m["g"], m["t"], str(tmp_path / "all.json"), tmp_path / "p2")
    assert not (tmp_path / "p1").exists() and not (tmp_path / "p2").exists()


def test_prepare_applies_the_registered_go_rule_and_the_study_runs_on_v3_derivations(tmp_path, monkeypatch):
    m = _material(tmp_path, monkeypatch)
    monkeypatch.setattr(gen3, "FIDELITY_LIMITS", {k: 1.0 for k in gen3.FIDELITY_LIMITS})  # the fixture's types
    runner.pools(m["stage"], m["lh"], m["g"], m["t"], m["profile"], tmp_path / "pools")
    cal = [_probe_dir(tmp_path / "cal-d", tmp_path / "pools" / "pool-D.json", "development", PARENT),
           _probe_dir(tmp_path / "cal-t", tmp_path / "pools" / "pool-T.json", "skill_confirmation", PARENT)]
    # every calibration item fails once in three runs: pass rate 2/3 on both pools
    hard = _reference(tmp_path / "ref-hard", m["train"], PARENT, passes=7)  # G 7/14: the pools are 1/6 easier
    spec, go = runner.prepare(m["stage"], tmp_path / "pools", cal, hard, tmp_path / "s0", 1)
    checks = spec["calibration"]["checks"]
    assert not go and checks["diagnostic_not_easier"] is False and checks["transfer_not_easier"] is False
    assert checks["informative_diagnostic"] is False  # 4 informative items < 20
    assert (tmp_path / "s0" / "no-go.json").exists() and not (tmp_path / "s0" / "study").exists()
    monkeypatch.setattr(runner, "MIN_INFORMATIVE_D", 4)
    reference = _reference(tmp_path / "ref", m["train"], PARENT, passes=8)  # G 8/14: 2/3 - 4/7 = 0.095
    spec, go = runner.prepare(m["stage"], tmp_path / "pools", cal, reference, tmp_path / "s1", 1)
    assert go and all(spec["calibration"]["checks"].values()) and spec["source"]["go_rule"]["min_informative_diagnostic"] == 4
    assert spec["calibration"]["reference"]["pass_rate"] == round(8 / 14, 6) and spec["source"]["runner"] == runner.VERSION
    assert spec["calibration"]["diagnostic"]["minus_reference"] == round(2 / 3 - 8 / 14, 6)
    assert read_json(tmp_path / "s1" / "study" / "protocol.json", sealed=True) == spec
    with pytest.raises(ValueError):  # a prepared output is never prepared again
        runner.prepare(m["stage"], tmp_path / "pools", cal, reference, tmp_path / "s1", 1)
    for bad in (_reference(tmp_path / "other", m["train"], "Other.\n", passes=8),  # another parent text
                _reference(tmp_path / "flash", m["train"], PARENT, passes=8, model="glm-5.3-flash"),
                _reference(tmp_path / "few", m["train"][:-1], PARENT, passes=8),  # not every training task
                _reference(tmp_path / "regraded", [{**t, "private": {"answer": "x"}} for t in m["train"]], PARENT,
                           passes=8),
                _reference(tmp_path / "longer", m["train"], PARENT, passes=8, max_tokens=4096),  # other settings
                _reference(tmp_path / "superset", m["train"] + [{**m["train"][0], "task_id": "val-x"}], PARENT,
                           passes=8)):  # G and one more item (a validation item, say): refused unread
        with pytest.raises(ValueError):
            runner.spec_from_inputs(m["stage"], tmp_path / "pools", cal, bad, 1)
    # an item file without the panel's provenance key holds the same scoring inputs (the reference answer)
    plain = [{**t, "private": {"answer": t["private"]["answer"]}} for t in m["train"]]
    extra = [{**t, "private": {**t["private"], "source_sha256": "0" * 64}} for t in m["train"]]
    for name, tasks in (("plain", plain), ("extra", extra)):
        assert runner.spec_from_inputs(m["stage"], tmp_path / "pools", cal,
                                       _reference(tmp_path / name, tasks, PARENT, passes=8), 1)[4]
    # the unchanged study runs on these v3 derivations (the fixture model); its code layer reports the statistics
    # expressions as derivation_unavailable and still shows the expected answer and the expression
    spec, panel, derivations, _, _ = runner.spec_from_inputs(m["stage"], tmp_path / "pools", cal, reference, 1)
    failing = set(sorted(derivations)[:2])

    def host(task, skill):
        tid = task["task_id"]
        if tid in derivations:
            ok = tid not in failing
            output = "<answer>%s</answer>" % (derivations[tid]["answer"] if ok else "1")
        else:
            ok = task["partition"] == "development" or "decimal places" in skill
            output = "<answer>%s</answer>" % ("12.50" if ok else "12")
        return ({"status": "available", "output": output, "reason": "fixture"},
                {"status": "pass" if ok else "fail", "score": float(ok), "reason": "fixture", "metrics": {}})

    api = GenAPI()
    result = gf.run_study(spec, panel, derivations, tmp_path / "run", fixture_api=api, fixture_evaluate=host)
    assert result["status"] == "completed", result.get("reason")
    c = json.loads((tmp_path / "run" / "blocks" / "0" / "candidates.json").read_text())
    assert c["train"]["generated_rows"] == 4 and c["train"]["host_fail_generated_rows"] == 2
    assert c["verifier"]["code_diag"]["error_modes"] == {"derivation_unavailable": 2}
    code_users = [u for _, kind, _, u in api.reflections if kind in ("code", "both")]
    assert any("stdev_pop(a, b, c)" in u and "derivation_unavailable" in u for u in code_users)
