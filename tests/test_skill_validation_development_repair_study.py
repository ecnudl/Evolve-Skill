"""Pure diagnostic bookkeeping fixtures: no API or generated-code execution."""
from copy import deepcopy
import json

import pytest

from skillopt.skill_validation.development_repair_study import (
    direction, regression_tasks, summarize_rows, unique_skills,
)


def source(task, repeat, baseline, current):
    return [{"task_id": task, "repeat": repeat, "partition": "development",
             "condition": condition, "status": status}
            for condition, status in (("no_skill", baseline), ("current", current))]


def test_regression_positions_are_not_independent_tasks():
    rows = source("a", 0, "pass", "fail") + source("a", 1, "pass", "fail")
    rows += source("b", 0, "unknown", "fail") + source("c", 0, "fail", "pass")
    tasks, losses = regression_tasks(rows)
    assert tasks == ["a"]
    assert losses == [{"task_id": "a", "repeat": 0}, {"task_id": "a", "repeat": 1}]
    assert regression_tasks(list(reversed(rows))) == (tasks, losses)


def test_no_final_in_selection_and_missing_duplicates_rejected():
    rows = source("a", 0, "pass", "fail")
    with pytest.raises(ValueError):
        regression_tasks(rows[:1])
    with pytest.raises(ValueError):
        regression_tasks(rows + rows[:1])
    changed = deepcopy(rows)
    changed[0]["partition"] = "final"
    with pytest.raises(ValueError):
        regression_tasks(changed)


def test_deduplicate_adaptive_aliases_without_claiming_independent_updates():
    values = {"no_skill": "", "current": "parent", "fixed_u0": "candidate",
              "adaptive_research_u0": "candidate", "adaptive_no_research_u0": "candidate",
              "contract_only_u0": "other", "coverage_evidence_u0": "parent"}
    skills, aliases = unique_skills(values)
    assert list(skills) == ["no_skill", "current", "contract_only_u0", "fixed_u0"]
    assert aliases["adaptive_research_u0"] == "fixed_u0"
    assert aliases["coverage_evidence_u0"] == "current"
    assert unique_skills(dict(reversed(list(values.items())))) == (skills, aliases)


@pytest.mark.parametrize("values", [
    {"current": "p"}, {"no_skill": "not empty", "current": "p"},
    {"no_skill": "", "current": 1}, {"no_skill": "", "current": "a" * 6001},
])
def test_skill_table_validation(values):
    with pytest.raises(ValueError):
        unique_skills(values)


@pytest.mark.parametrize("before,after,expected", [
    ("pass", "fail", "loss"), ("fail", "pass", "win"),
    ("unknown", "pass", "unknown"), ("fail", "unknown", "unknown"),
    ("fail", "fail", "tie"), ("pass", "pass", "tie"),
])
def test_uncertainty_is_not_a_win_or_loss(before, after, expected):
    assert direction(before, after) == expected


def rows():
    return [{"arm": arm, "task_id": "one-task", "repeat": repeat, "partition": "development",
             "draft_status": draft, "revised_status": revised, "revision_status": action,
             "contract_review_required": True}
            for arm, repeat, draft, revised, action in [
                ("no_skill", 0, "pass", "pass", "kept"),
                ("no_skill", 1, "unknown", "unknown", "skipped"),
                ("current", 0, "fail", "pass", "revised"),
                ("current", 1, "fail", "fail", "fallback")]]


def test_summary_preserves_raw_fail_unknown_contract_flags_and_repair_stages():
    value = summarize_rows(rows())["current"]
    assert value["positions"] == 2 and value["independent_tasks"] == 1
    assert value["draft"] == {"fail": 2}
    assert value["after_public_revision"] == {"pass": 1, "fail": 1}
    assert value["revision_effect"] == {"win": 1, "tie": 1}
    assert value["draft_vs_no_skill"] == {"loss": 1, "unknown": 1}
    assert value["revised_vs_no_skill"] == {"tie": 1, "unknown": 1}
    assert value["contract_flagged_positions"] == 2  # Not dropped from denominator.


def test_missing_duplicate_and_final_summary_rows_fail_closed():
    with pytest.raises(ValueError):
        summarize_rows(rows()[:-1])
    with pytest.raises(ValueError):
        summarize_rows(rows() + rows()[-1:])
    changed = rows()
    changed[0]["partition"] = "final"
    with pytest.raises(ValueError):
        summarize_rows(changed)


def test_full_runner_fabricated_pipeline_and_replay_without_final_or_network(tmp_path, monkeypatch):
    from skillopt.coevolution_v5.core import seal
    from skillopt.validator_pilot.api import digest, write_immutable_json
    from skillopt.skill_validation import development_repair_study as study
    from tests.test_skill_validation_public_revision import CODE, FixtureExecutor, fixture_row, SECRET

    requests = []

    class API:
        model = "fixture-no-model"
        service = {"fixture": True, "provider": "BIGMODEL"}

        def __init__(self, repo, root, **kwargs):
            self.root = root

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def call(self, system, user, kind, key, *, max_tokens, repeat):
            assert SECRET not in system + user
            request = {"model": self.model, "system": system, "user": user, "kind": kind,
                       "key": key, "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
            request_hash = digest(request)
            path = self.root / "calls" / (request_hash + ".json")
            if path.exists():
                return json.loads(path.read_text())
            requests.append(request)
            assert kind in {"public-initial", "public-revision"}
            value = {"request": request, "request_hash": request_hash, "ok": True,
                     "response": json.dumps({"solution.py": CODE}) if kind == "public-initial" else "KEEP",
                     "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "http_attempt_count": 1}
            write_immutable_json(path, value)
            return value

        def parallel(self, jobs, fn, label):
            return [fn(job) for job in jobs]

    prepared = seal({"selected_task_ids": ["a"], "skills": {"no_skill": "", "current": "parent", "fixed_u0": "child"},
                     "contract_review_flags": {"a": "fixture contested convention"}})
    data = {"tasks": {"a": fixture_row()}, "parent": {"text": "parent"}}
    monkeypatch.setattr(study, "prepare", lambda *args, **kwargs: (prepared, data))
    monkeypatch.setattr(study, "CachedAPI", API)
    audits = []

    def fake_audit(row, artifact, executor, root, reference=False):
        audits.append((artifact, reference))
        # No model request ever contains this fabricated host label.
        return seal({"status": "pass", "audit_secret": SECRET})

    monkeypatch.setattr(study, "audit", fake_audit)
    executor = FixtureExecutor()
    executor.transport_identity = {"fixture": True}
    output = tmp_path / "diagnostic"
    result = study.run(tmp_path, tmp_path / "source", output, executor,
                       workers=2, repeats=2, include_updates=False)
    assert result["fixture_only"] and not result["final_access"]
    assert not result["deployment_authorized"]
    assert len(result["rows"]) == 6
    assert len(requests) == 12
    assert all(v["draft"] == {"pass": 2} for v in result["summary"].values())
    assert all(v["revision_actions"] == {"kept": 2} for v in result["summary"].values())
    assert all(v["contract_flagged_positions"] == 2 for v in result["summary"].values())
    replay = study.run(tmp_path, tmp_path / "source", output, executor,
                       workers=2, repeats=2, include_updates=False)
    assert replay == result and len(requests) == 12
