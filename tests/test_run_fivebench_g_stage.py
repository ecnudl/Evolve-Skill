"""Controls for the learning-v8 stage redo tool (panel construction and paired test comparison); no model calls."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import run_fivebench_g_stage as tool
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval.core import write_json


def _dev_panel(benchmark, n_families, per_family=1, categories=None):
    tasks = []
    for f in range(n_families):
        for t in range(per_family):
            private = {"answer": "x", "category": categories[f % len(categories)] if categories else "logic",
                       "rule_id": str(f), "upstream_index": str(t)} if benchmark == "korbench" else {"answers": ["x"]}
            public = ({"rule": "r", "question": "q"} if benchmark == "korbench"
                      else {"question": "q", "context": ["c"]})
            tasks.append({"task_id": f"{f}:{t}", "family_id": f"rule{f}", "project_id": "", "partition": "development",
                          "public": public, "private": private})
    return {"version": "continual-panel-v1", "benchmark": benchmark, "dataset_revision": "fixture-v1",
            "provenance": "fixture", "tasks": tasks}


def _split(benchmark, dev_panel, val_ids):
    return {"splits": {benchmark: {"train": [{"task_id": t["task_id"], "family_id": t["family_id"]}
                                             for t in dev_panel["tasks"]],
                                   "val": [{"task_id": i, "family_id": "val" + i} for i in val_ids]}}}


def test_kor_train_families_are_category_stratified_with_a_task_cap():
    panel = _dev_panel("korbench", 50, per_family=10, categories=["cipher", "logic", "operation", "puzzle", "counterfactual"])
    split = _split("korbench", panel, [])
    tasks, families = tool.train_tasks(panel, split, "korbench", 7)
    assert len(families) == 30 and len(tasks) == 90
    by_category = {}
    for t in tasks:
        by_category.setdefault(t["private"]["category"], set()).add(t["family_id"])
    assert all(len(v) == 6 for v in by_category.values())
    assert all(sum(t["family_id"] == f for t in tasks) == 3 for f in families)
    again, families_again = tool.train_tasks(panel, split, "korbench", 7)
    assert again == tasks and families_again == families  # seeded, outcome-blind, deterministic
    other, _ = tool.train_tasks(panel, split, "korbench", 8)
    assert other != tasks


def test_train_tasks_must_stay_inside_canonical_train_and_panel_has_no_family_overlap():
    panel = _dev_panel("searchqa", 200)
    split = _split("searchqa", panel, ["v1", "v2"])
    tasks, families = tool.train_tasks(panel, split, "searchqa", 1)
    assert len(tasks) == len(families) == 128 and all(t["partition"] == "development" for t in tasks)
    bad = deepcopy(split)
    bad["splits"]["searchqa"]["train"] = bad["splits"]["searchqa"]["train"][:10]
    with pytest.raises(ValueError, match="canonical train"):
        tool.train_tasks(panel, bad, "searchqa", 1)
    val = {"tasks": [{"task_id": "v1", "family_id": "valv1", "partition": "skill_confirmation"}]}
    learning, train_families, selection = tool.learning_panel(panel, val, split, "searchqa", 1)
    assert len(learning["tasks"]) == 129 and selection == ["valv1"] and len(train_families) == 128
    overlap = {"tasks": [{"task_id": "z", "family_id": train_families[0], "partition": "skill_confirmation"}]}
    with pytest.raises(ValueError, match="overlap"):
        tool.learning_panel(panel, overlap, split, "searchqa", 1)


def test_compare_pairs_positions_with_the_recorded_no_skill_cell(tmp_path):
    rows = [{"task_id": str(i), "family_id": "f" + str(i // 2), "repeat": 0, "status": "pass" if i % 3 else "fail",
             "record_hash": "0" * 64} for i in range(12)]
    config = {"panels": {"korbench": "/p/korbench.json"}, "partition": "final", "repeats": 1, "methods": ["no_skill"],
              "model": {"name": "m"}}

    def plan(root, methods):
        value = seal({"config": {**config, "methods": methods}, "source_identity": {"a": 1}, "host_runtime": {"b": 2}})
        write_json(root / "plan.json", value)
        return value["record_hash"]

    base_root, new_root = tmp_path / "base", tmp_path / "new"
    baseline = seal({"benchmark": "korbench", "policy": "no_skill", "rows": rows, "root": str(base_root),
                     "plan_hash": plan(base_root, ["no_skill"]), "counts": {"pass": 8, "fail": 4}, "positions": 12})
    write_json(tmp_path / "no_skill.json", baseline)
    new_rows = deepcopy(rows)
    for r in new_rows[:3]:  # first three positions: fail->pass, pass->fail, pass->pass
        r["status"] = {"0": "pass", "1": "fail", "2": "pass"}[r["task_id"]]
    result = {"rows": new_rows, "positions": 12, "counts": {"pass": 8, "fail": 4}, "costs": {"logical_calls": 12},
              "root": str(new_root), "plan_hash": plan(new_root, ["no_skill", "skillopt"])}
    record = {"record_hash": "h" * 64, "benchmark": "korbench", "parent": "f-s3"}
    learned = {"skill_sha256": "s" * 64, "steps": []}
    request = {"no_skill_cell": str(tmp_path / "no_skill.json"), "no_skill_cell_hash": baseline["record_hash"],
               "benchmark": "korbench"}
    result["benchmark"] = "korbench"
    new_rows[11]["status"] = "unknown"  # a new unknown is neither a win nor a loss, and is reported
    summary = tool.compare(tmp_path, record, learned, request, result)
    assert summary["wins_vs_no_skill"] == 1 and summary["losses_vs_no_skill"] == 1 and summary["net_vs_no_skill"] == 0
    assert summary["new_unknown"] == 1 and summary["no_skill_unknown"] == 0 and summary["jointly_known"] == 11
    assert summary["families_improving"] == 0 and summary["families_regressing"] == 0  # f0 nets to zero
    assert json.loads((tmp_path / "summary.json").read_text())["one_test_cell_not_a_study"] is True
    bad = {**result, "rows": new_rows[:-1], "positions": 11}
    bad["benchmark"] = "korbench"
    with pytest.raises(ValueError, match="positions differ"):
        tool.compare(tmp_path / "x", record, learned, request, bad)
    with pytest.raises(ValueError, match="Wrong No-Skill cell"):
        tool.compare(tmp_path / "y", record, learned, {**request, "no_skill_cell_hash": "f" * 64}, result)
    other_root = tmp_path / "other"
    other = {**result, "root": str(other_root), "plan_hash": plan(other_root, ["no_skill", "skillopt"])}
    (other_root / "plan.json").write_text(json.dumps(seal({"config": {**config, "partition": "development",
                                                                      "methods": ["no_skill", "skillopt"]},
                                                           "source_identity": {"a": 1}, "host_runtime": {"b": 2}})))
    other["plan_hash"] = json.loads((other_root / "plan.json").read_text())["record_hash"]
    with pytest.raises(ValueError, match="same frozen evaluation"):
        tool.compare(tmp_path / "z", record, learned, request, other)


def test_parent_names_and_api_only_scope():
    assert set(tool.PARENTS) == {"none", "f-s1", "f-s3", "f-s4"} and tool.API_ONLY == ("bigcodebench", "searchqa", "korbench")
    assert tool.BUDGET["max_iterations"] == 3 and tool.BUDGET["solver_max_tokens"] == 65536
    assert Path(tool.__file__).name == "run_fivebench_g_stage.py"


def test_g_parent_chains_a_completed_stage_and_rejects_tampering(tmp_path, monkeypatch):
    import hashlib

    monkeypatch.setattr(tool, "_sha", lambda path: "t" * 64 if str(path).endswith("run_fivebench_g_stage.py")
                        else hashlib.sha256(Path(path).read_bytes()).hexdigest())
    protocol = {"record_hash": "p" * 64, "root": "/root/study-f"}
    skill = "## Coding checklist\n- run the example"

    def make(name, *, action="selected_update", status="completed", split="s" * 64, tool_hash="t" * 64, skill_text=skill):
        prev = tmp_path / name
        (prev / "learning").mkdir(parents=True)
        write_json(prev / "panel.json", {"tasks": []})
        manifest_record = seal({"parent_skill": "", "method": "skillopt"})
        write_json(prev / "manifest.json", manifest_record)
        stage = seal({"version": tool.VERSION, "protocol_hash": protocol["record_hash"], "benchmark": "bigcodebench",
                      "study": protocol["root"], "split_hash": split, "tool_sha256": tool_hash,
                      "manifest_hash": manifest_record["record_hash"],
                      "panel_sha256": hashlib.sha256((prev / "panel.json").read_bytes()).hexdigest()})
        write_json(prev / "stage.json", stage)
        identity = seal({"manifest": manifest_record})
        write_json(prev / "learning/identity.json", identity)
        (prev / "learning/calls").mkdir()
        write_json(prev / "learning/calls/a.json", {"x": 1})
        result = seal({"status": status, "candidate_skill": skill_text if action == "selected_update" else "",
                       "identity_hash": identity["record_hash"],
                       "artifacts": {"calls/a.json": hashlib.sha256((prev / "learning/calls/a.json").read_bytes()).hexdigest()}})
        write_json(prev / "learning/result.json", result)
        deployed = skill_text if action == "selected_update" else ""
        learned = seal({"stage_hash": stage["record_hash"], "skill": deployed, "action": action, "status": status,
                        "learning_result_hash": result["record_hash"],
                        "skill_sha256": hashlib.sha256(deployed.encode()).hexdigest()})
        write_json(prev / "learned.json", learned)
        return prev, stage, learned

    prev, stage, learned = make("prev")
    text, record = tool.parent_skill(None, protocol, f"g:{prev}", "s" * 64)
    assert text == skill and record["parent_stage_hash"] == stage["record_hash"]
    assert record["parent_learned_hash"] == learned["record_hash"] and record["parent_skill_sha256"] == learned["skill_sha256"]
    # a completed stage without an update carries its parent ("" here) and may still be chained from
    carried, _, _ = make("carried", action="completed_no_update")
    assert tool.parent_skill(None, protocol, f"g:{carried}", "s" * 64)[0] == ""
    with pytest.raises(ValueError, match="study/split"):
        tool.parent_skill(None, {**protocol, "record_hash": "q" * 64}, f"g:{prev}", "s" * 64)
    with pytest.raises(ValueError, match="study/split"):
        tool.parent_skill(None, protocol, f"g:{prev}", "z" * 64)
    other_tool, _, _ = make("othertool", tool_hash="u" * 64)
    with pytest.raises(ValueError, match="compatible tool"):
        tool.parent_skill(None, protocol, f"g:{other_tool}", "s" * 64)
    pending, _, _ = make("pending", action="pending_carry_parent", status="pending")
    with pytest.raises(ValueError, match="completed"):
        tool.parent_skill(None, protocol, f"g:{pending}", "s" * 64)
    tampered, _, learned_t = make("tampered")
    (tampered / "learned.json").write_text(json.dumps(seal({**{k: v for k, v in learned_t.items() if k != "record_hash"},
                                                            "skill": skill + " extra"})))
    with pytest.raises(ValueError, match="completed, consistently"):
        tool.parent_skill(None, protocol, f"g:{tampered}", "s" * 64)
    with pytest.raises(ValueError, match="Unknown parent"):
        tool.parent_skill(None, protocol, "f-s2")
    # archived evidence: a changed or unrecorded receipt blocks chaining from the stage
    changed, _, _ = make("changed")
    (changed / "learning/calls/a.json").write_text('{"x": 2}')
    with pytest.raises(ValueError, match="missing or changed"):
        tool.parent_skill(None, protocol, f"g:{changed}", "s" * 64)
    extra, _, _ = make("extra")
    (extra / "learning/calls/b.json").write_text('{"y": 1}')
    with pytest.raises(ValueError, match="does not record"):
        tool.parent_skill(None, protocol, f"g:{extra}", "s" * 64)
    # the same holds for every governed category: native proposals, steps, host-side scorer artifacts
    for relative in ("native/0/extra.json", "steps/9.json", "host_only/scorer_artifacts/pos/receipt.json"):
        unrecorded, _, _ = make("unrecorded-" + relative.split("/")[0].replace("_", ""))
        target = unrecorded / "learning" / relative
        target.parent.mkdir(parents=True)
        target.write_text('{"cleanup_confirmed": false}')
        with pytest.raises(ValueError, match="does not record"):
            tool.parent_skill(None, protocol, f"g:{unrecorded}", "s" * 64)
    # files outside the governed inventories (e.g. GEPA's official_state) are not judged
    tolerated, _, _ = make("tolerated")
    (tolerated / "learning/official_state").mkdir()
    (tolerated / "learning/official_state/state.json").write_text("{}")
    assert tool.parent_skill(None, protocol, f"g:{tolerated}", "s" * 64)[0] == skill


def test_compatible_predecessor_hashes_are_full_digests_and_suffix_marks_other_domains():
    assert all(len(h) == 64 and set(h) <= set("0123456789abcdef") for h in tool.COMPATIBLE_TOOL_HASHES)
    assert len(tool.COMPATIBLE_TOOL_HASHES) == 3
    record = {"benchmark": "korbench"}
    assert tool._suffix(record, "korbench") == "" and tool._suffix(record, "searchqa") == "-searchqa"
    # replicate cells never collide with the primary cell or with other domains
    assert tool._suffix(record, "korbench", 1) == "-r1" and tool._suffix(record, "searchqa", 2) == "-searchqa-r2"
    with pytest.raises(ValueError, match="Replicate"):
        tool._suffix(record, "korbench", 0)


def test_learning_protocols_v8_and_v9_are_explicit():
    from skillopt.continual_learning.recovery import POLICY_V8, POLICY_V9

    version, policy, budget = tool._protocol("v8")
    assert version == "continual-learning-v8" and policy == POLICY_V8 and budget["reflection_max_tokens"] == 4096
    version, policy, budget = tool._protocol("v9")
    assert version == "continual-learning-v9" and policy == POLICY_V9
    assert budget["reflection_max_tokens"] == 8192 and budget["max_metric_calls"] == 8000
    assert policy["selection_gate"] == "family_sign_test_screen_then_fresh_confirmation_v1" and "min_net_wins" not in policy
    with pytest.raises(ValueError, match="Unknown learning version"):
        tool._protocol("v7")


def test_recorded_outcome_binds_action_skill_and_result(tmp_path):
    import hashlib

    out = tmp_path / "stage"
    (out / "learning").mkdir(parents=True)
    record = {"record_hash": "r" * 64}
    value = {"parent_skill": "parent text"}

    identity = seal({"manifest": value})
    write_json(out / "learning/identity.json", identity)
    (out / "learning/calls").mkdir()
    write_json(out / "learning/calls/a.json", {"x": 1})
    recorded = {"calls/a.json": hashlib.sha256((out / "learning/calls/a.json").read_bytes()).hexdigest()}

    def write(result_status, candidate, action, skill, learned_status="completed"):
        result = seal({"status": result_status, "candidate_skill": candidate, "identity_hash": identity["record_hash"],
                       "artifacts": recorded})
        write_json(out / "learning/result.json", result)
        learned = seal({"stage_hash": record["record_hash"], "learning_result_hash": result["record_hash"],
                        "status": learned_status, "action": action, "skill": skill,
                        "skill_sha256": hashlib.sha256(skill.encode()).hexdigest()})
        write_json(out / "learned.json", learned)
        return learned

    learned = write("completed", "new text", "selected_update", "new text")
    assert tool._recorded_outcome(out, record, value) == learned
    for f in ("learning/result.json", "learned.json"):
        (out / f).unlink()
    learned = write("completed", "parent text", "completed_no_update", "parent text")
    assert tool._recorded_outcome(out, record, value) == learned
    for f in ("learning/result.json", "learned.json"):
        (out / f).unlink()
    # a "no update" record whose sealed result actually changed the Skill is inconsistent
    write("completed", "new text", "completed_no_update", "parent text")
    with pytest.raises(ValueError, match="does not bind"):
        tool._recorded_outcome(out, record, value)
    for f in ("learning/result.json", "learned.json"):
        (out / f).unlink()
    # pending must carry the parent and be recorded as pending
    learned = write("pending", "parent text", "pending_carry_parent", "parent text", learned_status="pending")
    assert tool._recorded_outcome(out, record, value)["action"] == "pending_carry_parent"


def test_learning_protocol_v10_is_the_main_method_and_hands_on_the_verifier_policy(tmp_path, monkeypatch):
    import hashlib

    from skillopt.continual_learning.recovery import POLICY_V10
    from skillopt.continual_learning.verifier import default_policy_record
    from skillopt.validator_pilot.api import digest

    version, policy, budget = tool._protocol("v10")
    assert version == "continual-learning-v10" and policy == POLICY_V10
    assert budget["max_verifier_calls"] == 2000 and budget["verifier_max_tokens"] == 4096
    assert budget["reflection_max_tokens"] == 8192 and budget["max_metric_calls"] == 8000  # v9 gate budget kept
    assert policy["selection_gate"] == "family_sign_test_screen_then_fresh_confirmation_v1"
    assert policy["verifier_policy_arm"] == "adaptive_research" and policy["verifier_probes_per_task"] == 2

    # a completed rubric_research stage hands its verifier policy mapping to the next stage, bound by hash
    monkeypatch.setattr(tool, "_sha", lambda path: "t" * 64 if str(path).endswith("run_fivebench_g_stage.py")
                        else hashlib.sha256(Path(path).read_bytes()).hexdigest())
    protocol = {"record_hash": "p" * 64, "root": "/root/study-f"}
    mapping = {"bigcodebench": default_policy_record("bigcodebench")}

    def make(name, *, policy_hash=None):
        prev = tmp_path / name
        (prev / "learning").mkdir(parents=True)
        write_json(prev / "panel.json", {"tasks": []})
        manifest_record = seal({"parent_skill": "", "method": "rubric_research"})
        write_json(prev / "manifest.json", manifest_record)
        stage = seal({"version": tool.VERSION, "protocol_hash": protocol["record_hash"], "benchmark": "bigcodebench",
                      "study": protocol["root"], "split_hash": "s" * 64, "tool_sha256": "t" * 64,
                      "manifest_hash": manifest_record["record_hash"],
                      "panel_sha256": hashlib.sha256((prev / "panel.json").read_bytes()).hexdigest()})
        write_json(prev / "stage.json", stage)
        identity = seal({"manifest": manifest_record})
        write_json(prev / "learning/identity.json", identity)
        (prev / "learning/verifier/0").mkdir(parents=True)
        write_json(prev / "learning/verifier/0/policy.json", {"x": 1})
        result = seal({"status": "completed", "candidate_skill": "", "identity_hash": identity["record_hash"],
                       "artifacts": {"verifier/0/policy.json": hashlib.sha256((prev / "learning/verifier/0/policy.json").read_bytes()).hexdigest()},
                       "verifier_policy": mapping})
        write_json(prev / "learning/result.json", result)
        learned = seal({"stage_hash": stage["record_hash"], "skill": "", "action": "completed_no_update",
                        "status": "completed", "learning_result_hash": result["record_hash"],
                        "skill_sha256": hashlib.sha256(b"").hexdigest(),
                        "verifier_policy_hash": policy_hash or digest(mapping)})
        write_json(prev / "learned.json", learned)
        return prev

    prev = make("rr")
    text, record = tool.parent_skill(None, protocol, f"g:{prev}", "s" * 64)
    assert text == "" and record["parent_verifier_policy"] == mapping
    with pytest.raises(ValueError, match="verifier policy differs"):
        tool.parent_skill(None, protocol, f"g:{make('rr-bad', policy_hash='0' * 64)}", "s" * 64)
    # an unrecorded verifier record blocks chaining like any other governed artifact
    extra = make("rr-extra")
    write_json(extra / "learning/verifier/0/summary.json", {"y": 1})
    with pytest.raises(ValueError, match="does not record"):
        tool.parent_skill(None, protocol, f"g:{extra}", "s" * 64)
