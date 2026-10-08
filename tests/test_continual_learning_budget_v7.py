"""Learning v7 and queue v4 controls (raised Skill interface, GEPA unknown rule); not method effects."""
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts import continue_fivebench_baselines as sequence
from skillopt.continual_learning.contracts import BUDGET_VERSION, HARDENED_VERSION, check_skill, manifest, skill_budget
from skillopt.continual_learning.gepa import Adapter, _guard_official_best, _parent_known_sets
from skillopt.continual_learning.ledger import LearningPending, Ledger
from skillopt.continual_learning.recovery import POLICY_V6, POLICY_V7
from skillopt.continual_learning.skillopt import run_stage
from skillopt.validator_pilot.api import digest
from tests.test_continual_learning_domains import API as DomainAPI
from tests.test_continual_learning_domains import evaluate, setup
from tests.test_continual_learning_gepa import official_source  # noqa: F401  (pytest fixture)


def auth(version=BUDGET_VERSION, policy=POLICY_V7, *, method="skillopt", selection=2, iterations=1):
    _, base, args = setup(method=method)
    task = base["tasks"][0]
    panel = {**base, "tasks": [{**deepcopy(task), "task_id": str(i), "family_id": str(i)}
                               for i in range(2 + selection)]}
    args.update(version=version, recovery_policy=deepcopy(policy), train_families=["0", "1"],
                selection_families=[str(i) for i in range(2, 2 + selection)])
    args["model"]["transport"]["stream_wall_seconds"] = 3600
    args["budget"].update(max_iterations=iterations, max_metric_calls=64, max_api_calls=200)
    return manifest(panel, **args), panel


class API(DomainAPI):
    """Domain fixture with the hardened v3 service binding that v6/v7 ledgers require."""

    def __init__(self, content="Use the requested constant result."):
        super().__init__()
        self.service = {"fixture": "offline-domain-controls", "delivery_retry_policy": "closed_delivery_error_v3",
                        "max_retries": 2}
        self.content = content

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if not kind.endswith("solver"):
            row["response"] = json.dumps({"batch_size": 2, "patch": {"reasoning": "Fixture only", "edits": [
                {"op": "append", "content": self.content}]}})
        row["attempts"] = [{"usage": dict(row["usage"])}]
        return row


def _scorer(unknown):
    def execute(task, skill):
        prediction, score = evaluate("searchqa")(task, skill)
        if unknown(task["task_id"], skill):
            return prediction, {**score, "status": "unknown", "score": None}
        return prediction, score
    return execute


def test_v7_budget_is_explicit_for_both_methods_and_v6_stays_skillopt_only():
    for method in ("skillopt", "gepa"):
        value, _ = auth(method=method)
        assert value["version"] == BUDGET_VERSION and skill_budget(value) == 32000
    assert skill_budget(auth(HARDENED_VERSION, POLICY_V6)[0]) == 6000
    with pytest.raises(ValueError, match="SkillOpt-only"):
        auth(HARDENED_VERSION, POLICY_V6, method="gepa")
    assert check_skill("x" * 7000, 32000)
    with pytest.raises(ValueError, match="6000"):
        check_skill("x" * 7000)


@pytest.mark.parametrize("version,policy,action", [
    (BUDGET_VERSION, POLICY_V7, "accept_new_best"),
    (HARDENED_VERSION, POLICY_V6, "reject_inadmissible_over_budget"),
])
def test_candidate_between_6000_and_32000_bytes_is_evaluated_only_in_v7(tmp_path, version, policy, action):
    value, panel = auth(version, policy)
    api = API("Use the requested constant result. " + "x" * 7000)
    result = run_stage(value, panel, tmp_path, fixture_api=api, fixture_evaluate=evaluate("searchqa"))
    assert result["status"] == "completed", result
    assert result["steps"][0]["gate_action"] == action
    assert (len(result["candidate_skill"].encode()) > 6000) == (version == BUDGET_VERSION)


def _adapter(tmp_path, value, unknown):
    return Adapter(value, tmp_path, Ledger(tmp_path, value, API()), fixture_evaluate=_scorer(unknown))


def _items(panel, value):
    rows = {"train": [], "selection": []}
    for task in panel["tasks"]:
        role = "train" if task["family_id"] in value["train_families"] else "selection"
        rows[role].append({"role": role, "task": task})
    return rows["train"], rows["selection"]


def test_v7_gepa_leaves_out_parent_unknown_positions(tmp_path):
    value, panel = auth(method="gepa", selection=4)
    adapter = _adapter(tmp_path, value, lambda task_id, skill: task_id == "3" and skill == "")
    train, selection = _items(panel, value)
    kept_train, kept_selection, parent_rows, excluded, _full = _parent_known_sets(adapter, value, train, selection)
    assert excluded == {"train": 0, "selection": 1}
    assert len(kept_train) == 2 and [i["task"]["task_id"] for i in kept_selection] == ["2", "4", "5"]
    assert len(parent_rows) == 3 and all(row["score"] is not None for row in parent_rows)


def test_v7_gepa_coverage_floor_stays_pending(tmp_path):
    value, panel = auth(method="gepa", selection=2)
    adapter = _adapter(tmp_path, value, lambda task_id, skill: task_id in {"2", "3"})
    with pytest.raises(LearningPending, match="insufficient_known_selection"):
        _parent_known_sets(adapter, value, *_items(panel, value))


def test_v7_gepa_candidate_unknown_takes_parent_score_and_leaves_reflection(tmp_path):
    value, panel = auth(method="gepa", selection=2)
    adapter = _adapter(tmp_path, value, lambda task_id, skill: task_id == "2" and skill == "candidate")
    train, selection = _items(panel, value)
    _parent_known_sets(adapter, value, train, selection)
    rows = adapter.evaluate_rows(selection, {"skill": "candidate"})
    assert rows[0]["score"] is None
    valued = adapter._neutral_unknowns(selection, {"skill": "candidate"}, rows)
    assert valued[0]["score"] == adapter.parent_scores[("selection", digest(selection[0]["task"]))]
    assert valued[0]["trajectory"] is None and adapter.imputed
    batch = SimpleNamespace(trajectories=[r["trajectory"] for r in valued])
    assert adapter.make_reflective_dataset({"skill": "candidate"}, batch, ["skill"]) == {
        "skill": [r["trajectory"] for r in valued if r["trajectory"] is not None]}


@pytest.mark.parametrize("hidden,kept", [({"2", "3", "4"}, False), ({"2"}, True)])
def test_v7_gepa_official_best_is_rechecked_on_real_paired_scores(tmp_path, hidden, kept):
    value, panel = auth(method="gepa", selection=8)
    candidate = "Use the requested constant result."
    adapter = _adapter(tmp_path, value, lambda task_id, skill: task_id in hidden and skill == candidate)
    train, selection = _items(panel, value)
    _, selection, parent_rows, _, _full = _parent_known_sets(adapter, value, train, selection)
    skill, record = _guard_official_best(adapter, value, candidate, selection, parent_rows)
    assert (skill == candidate) is kept
    assert record["final_paired"]["candidate_new_unknown"] == len(hidden)
    assert ("official_best_rejected" in record) is (not kept)


def _copy_tree(root, files):
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)


@pytest.fixture
def sources(tmp_path):
    files = {"skillopt/continual_eval/core.py": "x = 1\nrequire(len(skill_text.encode()) <= 6000)\n",
             "skillopt/continual_eval/truncation_recovery.py": "require(len(skill.encode()) <= 6000)\n",
             "skillopt/continual_eval/runner.py": "y = 2\n"}
    original, derived = tmp_path / "original", tmp_path / "derived"
    _copy_tree(original, files)
    _copy_tree(derived, {name: text.replace("<= 6000", "<= 32000") for name, text in files.items()})
    return original, derived


def test_v4_derived_source_may_change_only_the_budget_literal(sources):
    original, derived = sources
    changed = sequence._check_budget_source(original, derived, 32000)
    assert set(changed) == set(sequence.BUDGET_SOURCE_EDITS)
    (derived / "skillopt/continual_eval/runner.py").write_text("y = 3\n")
    with pytest.raises(ValueError, match="outside the Skill budget"):
        sequence._check_budget_source(original, derived, 32000)


def test_v4_derived_source_cannot_change_more_inside_budget_files(sources):
    original, derived = sources
    (derived / "skillopt/continual_eval/core.py").write_text("x = 2\nrequire(len(skill_text.encode()) <= 32000)\n")
    with pytest.raises(ValueError, match="more than the Skill budget"):
        sequence._check_budget_source(original, derived, 32000)


@pytest.mark.parametrize("operation,expected", [("inspect", "frozen"), ("evaluate", "derived"),
                                                ("verify-evaluation", "derived")])
def test_v4_only_new_policy_evaluation_uses_the_derived_source(tmp_path, monkeypatch, operation, expected):
    seen = {}

    def fake_run(command, cwd, env, stdout, stderr):
        seen.update(cwd=cwd, pythonpath=env["PYTHONPATH"])
        (tmp_path / "out.json").write_text("{}")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(sequence.subprocess, "run", fake_run)
    monkeypatch.setattr(sequence, "read_json", lambda *a, **k: {})
    reference = {"root": str(tmp_path), "source": str(tmp_path / "frozen"), "python": "python",
                 "evaluation_source": str(tmp_path / "derived")}
    sequence._invoke(reference, operation, tmp_path / "req.json", tmp_path / "out.json", log=tmp_path / "log")
    assert seen["cwd"] == reference["evaluation_source" if expected == "derived" else "source"]
    assert seen["pythonpath"] == seen["cwd"]


def test_v4_transition_uses_the_frozen_raised_limit():
    long_skill = "x" * 7000
    state = sequence.transition("", {"status": "completed", "candidate_skill": long_skill}, 32000)
    assert state["skill"] == long_skill and state["action"] == "selected_update"
    with pytest.raises(ValueError, match="6000"):
        sequence.transition("", {"status": "completed", "candidate_skill": long_skill})


class GepaAPI(API):
    def call(self, system, user, kind, key, *, max_tokens, repeat):
        row = super().call(system, user, kind, key, max_tokens=max_tokens, repeat=repeat)
        if not kind.endswith("solver"):
            row["response"] = "```\nUse the requested constant result.\n```"
        return row


def test_v7_official_gepa_stage_masks_parent_unknown_and_rechecks_best(tmp_path, official_source):  # noqa: F811
    from skillopt.continual_learning.gepa import run_stage as run_gepa_stage

    value, panel = auth(method="gepa", selection=4)
    api = GepaAPI()
    result = run_gepa_stage(value, panel, tmp_path, gepa_source=official_source, fixture_api=api,
                            fixture_evaluate=_scorer(lambda task_id, skill: task_id == "3" and skill == ""))
    assert result["status"] == "completed", result
    assert result["parent_unknown_excluded"] == {"train": 0, "selection": 1}
    assert result["gepa_unknown_policy"] == POLICY_V7["gepa_unknown"]
    assert "requested constant" in result["candidate_skill"]
    assert result["final_paired"]["paired_admissible"] and result["final_paired"]["candidate_new_unknown"] == 0
    replay = run_gepa_stage(value, panel, tmp_path, gepa_source=official_source, fixture_api=GepaAPI(),
                            fixture_evaluate=_scorer(lambda task_id, skill: task_id == "3" and skill == ""))
    assert replay == result
