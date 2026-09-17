"""Offline routing fairness checks: no credentials, models, or network required."""

import json
from collections import Counter
from types import SimpleNamespace

import pytest

from skillopt.cross_domain.gate import pair_stats
from skillopt.cross_domain.policies import (
    fit_scope_groups,
    mask_from_scope,
    matched_coverage_masks,
    paired_rows,
    partition_validation,
    route_inputs,
    route_labels,
)


class InputOnlyTask:
    """Any access to hidden annotations must fail loudly, even on the router."""

    def __init__(self, task_id, prompt="Observed task input only"):
        self.id, self.prompt = task_id, prompt

    def __getattr__(self, name):
        raise AssertionError(f"Routing accessed hidden task field: {name}")


class FakeAPI:
    def __init__(self, root, response):
        self.root, self.response = root, response
        self.calls = []

    def call(self, system, user, **kwargs):
        self.calls.append({"system": system, "user": user, **kwargs})
        return {"ok": True, "response": json.dumps(self.response), "request_hash": "offline"}

    def parallel(self, jobs, fn, label):
        return [fn(job) for job in jobs]


def _skill():
    return {"id": "skill_a", "source_domain": "coding", "content": "One fixed skill.",
            "scope": {"description": "Check prerequisites.", "apply_if": ["An explicit constraint"],
                      "avoid_if": ["The task overrides that constraint"]}}


def _task(task_id, domain="coding", mechanism="constraint_preservation", group="positive"):
    return SimpleNamespace(id=task_id, domain=domain, mechanism=mechanism, group=group)


def _outcomes(tasks, score, *, ok=True):
    return [{"id": t.id, "hard": score, "agent_ok": ok} for t in tasks]


def _routes(tasks):
    return {t.id: {"ok": True, "domain": "coding" if i % 2 else "spreadsheet",
                   "scores": {"skill_a": i / max(1, len(tasks) - 1)}}
            for i, t in enumerate(tasks)}


def test_router_reads_only_input_and_id_not_gold_or_generator_annotations(tmp_path):
    task = InputOnlyTask("opaque-task")
    api = FakeAPI(tmp_path, {"domain": "coding", "scores": {"skill_a": 0.9}})
    result = route_inputs(api, [task], [_skill()], "offline_router")
    assert result[task.id]["ok"]
    assert api.calls[0]["user"] == task.prompt
    assert api.calls[0]["kind"] == "router"
    assert "One fixed skill." not in api.calls[0]["system"]  # Scope, not answer traces.


@pytest.mark.parametrize("response", [
    {"domain": "secret-label", "scores": {"skill_a": 0.9}},
    {"domain": "coding", "scores": {}},
    {"domain": "coding", "scores": {"skill_a": float("nan")}},
    {"domain": "coding", "scores": {"skill_a": 1.01}},
])
def test_invalid_router_output_falls_back_to_unknown_zero_scores(tmp_path, response):
    task = InputOnlyTask("opaque-task")
    result = route_inputs(FakeAPI(tmp_path, response), [task], [_skill()], "invalid")
    assert result[task.id]["ok"] is False
    assert result[task.id]["domain"] == "unknown"
    assert result[task.id]["scores"] == {"skill_a": 0.0}


def test_shuffled_labels_preserve_coverage_within_predicted_domains_and_input_order():
    tasks = [InputOnlyTask(f"opaque-{i:03d}") for i in range(40)]
    routes = _routes(tasks)
    labels = route_labels(tasks, routes, "skill_a", 0.6, 1701)
    assert labels == route_labels(list(reversed(tasks)), routes, "skill_a", 0.6, 1701)
    for domain in {r["domain"] for r in routes.values()}:
        ids = [tid for tid, r in routes.items() if r["domain"] == domain]
        assert Counter(labels["mechanism"][tid] for tid in ids) == Counter(labels["shuffled"][tid] for tid in ids)
    assert labels["domain"] == {tid: r["domain"] for tid, r in routes.items()}


def test_failed_router_abstains_in_every_scope_even_if_allowed():
    tasks = [InputOnlyTask("opaque")]
    routes = {"opaque": {"ok": False, "domain": "unknown", "scores": {"skill_a": 1.0}}}
    labels = route_labels(tasks, routes, "skill_a", 0.0, 1701)
    assert {mapping["opaque"] for mapping in labels.values()} == {"__abstain__"}
    for mapping in labels.values():
        assert mask_from_scope(mapping, ["__abstain__", "unknown", "match", "nonmatch"]) == {"opaque": False}


@pytest.mark.parametrize("fraction", [0.0, 0.1, 0.25, 0.5, 0.75, 1.0])
def test_matched_coverage_is_exact_equal_and_reads_no_hidden_fields(fraction):
    tasks = [InputOnlyTask(f"opaque-{i:03d}") for i in range(37)]
    routes = _routes(tasks)
    masks = matched_coverage_masks(tasks, routes, _skill(), fraction, 1701)
    assert set(masks) == {"mechanism", "domain", "shuffled"}
    assert {sum(mask.values()) for mask in masks.values()} == {round(len(tasks) * fraction)}
    assert all(set(mask) == {t.id for t in tasks} for mask in masks.values())
    assert masks == matched_coverage_masks(list(reversed(tasks)), routes, _skill(), fraction, 1701)


def test_validation_fit_confirmation_are_disjoint_balanced_and_order_invariant():
    tasks = [_task(f"{domain}-{group}-{i}", domain=domain, group=group)
             for domain in ("coding", "spreadsheet") for group in ("positive", "near_miss", "unrelated")
             for i in range(7)]
    fit, confirmation = partition_validation(tasks)
    fit_ids, confirm_ids = {t.id for t in fit}, {t.id for t in confirmation}
    assert fit_ids.isdisjoint(confirm_ids)
    assert fit_ids | confirm_ids == {t.id for t in tasks}
    assert partition_validation(list(reversed(tasks))) == (fit, confirmation)
    for domain in ("coding", "spreadsheet"):
        for group in ("positive", "near_miss", "unrelated"):
            assert sum(t.domain == domain and t.group == group for t in fit) == 4
            assert sum(t.domain == domain and t.group == group for t in confirmation) == 3


def test_scope_fitting_uses_only_explicit_task_ids_not_extra_outcome_rows():
    fit = [_task(f"fit-{i}") for i in range(16)]
    withheld = [_task(f"confirm-{i}") for i in range(40)]
    base = _outcomes(fit, 0) + _outcomes(withheld, 1)
    current = _outcomes(fit, 0) + _outcomes(withheld, 1)
    candidate = _outcomes(fit, 1) + _outcomes(withheld, 0)
    labels = {"mechanism": {t.id: "match" for t in fit},
              "domain": {t.id: "coding" for t in fit},
              "shuffled": {t.id: "match" for t in fit}}
    result = fit_scope_groups(fit, labels, base, current, candidate, parent_empty=True)
    assert result["mechanism"]["allowed_groups"] == ["match"]
    assert result["domain"]["allowed_groups"] == ["coding"]
    stats = result["mechanism"]["estimates"]["match"]
    assert stats["n"] == 16
    assert stats["comparisons"]["baseline"]["delta"] == 1
    assert not any(t.id in stats["comparisons"]["baseline"]["counterexample_ids"] for t in withheld)


def test_unseen_scope_labels_fall_back_without_reinterpreting_gold():
    assert mask_from_scope({"a": "coding", "b": "rule_reasoning", "c": "unknown"}, ["coding"]) == {
        "a": True, "b": False, "c": False}


def test_reserved_abstain_and_unknown_labels_never_activate_even_if_allowed():
    labels = {"a": "coding", "b": "__abstain__", "c": "unknown"}
    assert mask_from_scope(labels, ["coding", "__abstain__", "unknown"]) == {
        "a": True, "b": False, "c": False}


@pytest.mark.parametrize("reserved_label", ["__abstain__", "unknown"])
def test_fit_cannot_propose_reserved_groups_even_with_large_observed_gains(reserved_label):
    tasks = [_task(f"fit-{i}") for i in range(20)]
    labels = {"mechanism": {t.id: reserved_label for t in tasks}}
    base = _outcomes(tasks, 0)
    candidate = _outcomes(tasks, 1)
    result = fit_scope_groups(tasks, labels, base, base, candidate, parent_empty=True)
    assert result["mechanism"]["estimates"][reserved_label]["comparisons"]["baseline"]["delta"] == 1.0
    assert result["mechanism"]["allowed_groups"] == []


def test_fallback_reuses_baseline_and_marks_structural_identity_only_when_true():
    tasks = [_task("a"), _task("b")]
    base = [{"id": "a", "hard": 1, "agent_ok": True}, {"id": "b", "hard": 0, "agent_ok": True}]
    candidate = [{"id": "a", "hard": 0, "agent_ok": True}, {"id": "b", "hard": 1, "agent_ok": True}]
    rows = paired_rows(tasks, base, base, candidate, mask={"a": False, "b": False}, parent_empty=True)
    assert all(r["candidate"] == r["baseline"] for r in rows)
    assert all(r["candidate_is_baseline"] and r["current_is_baseline"] and not r["applied"] for r in rows)
    stats = pair_stats(rows)
    assert all(c["structural_identity"] for c in stats["comparisons"].values())
    assert stats["comparisons"]["baseline"]["delta_interval"] == [0.0, 0.0]

    nonempty_current = paired_rows(tasks, base, base, candidate,
                                  mask={"a": False, "b": False}, parent_empty=False)
    stats = pair_stats(nonempty_current)
    assert stats["comparisons"]["baseline"]["structural_identity"]
    assert not stats["comparisons"]["current"]["structural_identity"]


def test_equal_observed_scores_with_injection_do_not_assert_baseline_identity():
    tasks = [_task("a")]
    base = _outcomes(tasks, 1)
    rows = paired_rows(tasks, base, base, base, mask={"a": True}, parent_empty=True)
    assert rows[0]["applied"]
    assert not rows[0]["candidate_is_baseline"]
    assert not pair_stats(rows)["comparisons"]["baseline"]["structural_identity"]


def test_paired_rows_reclassify_other_mechanism_positives_only_for_evaluation():
    tasks = [_task("other", mechanism="evidence_verification"),
             _task("near", mechanism="evidence_verification", group="near_miss")]
    base = _outcomes(tasks, 1)
    rows = paired_rows(tasks, base, base, base, mechanism="constraint_preservation")
    assert rows[0]["group"] == "unrelated"
    assert rows[0]["original_group"] == "positive"
    assert rows[1]["group"] == "near_miss"


def test_api_failures_are_not_converted_to_model_errors_in_pairing():
    tasks = [_task("a")]
    base, failure = _outcomes(tasks, 1), _outcomes(tasks, None, ok=False)
    assert paired_rows(tasks, base, base, failure) == []
    # Fallback is defined structurally from base; caller separately enforces
    # a common complete-case set across policies for comparable denominators.
    rows = paired_rows(tasks, base, base, failure, mask={"a": False}, parent_empty=True)
    assert len(rows) == 1 and rows[0]["candidate"] == 1
