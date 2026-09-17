"""Frozen-skill control construction, source separation and exact answer tests."""
from __future__ import annotations

import json
from collections import Counter

import pytest

from skillopt.envs.searchqa.rollout import _build_user
from skillopt.scope_evolution_v2.retention_controls import (
    CROSS_DOMAINS,
    DOMAINS,
    GROUPS,
    SPLITS,
    Task,
    build_controls,
    evaluate_control_answer,
    normalize_control_answer,
)


@pytest.mark.parametrize("split", SPLITS)
def test_pilot_is_48_not_144_and_is_deterministic(split):
    tasks = build_controls(split=split)
    assert len(tasks) == 48
    assert tasks == build_controls(split=split)
    assert Counter(t.group for t in tasks) == Counter({g: 16 for g in GROUPS})
    for group in ["positive", "unrelated"]:
        counts = Counter(t.domain for t in tasks if t.group == group)
        assert set(counts) == set(CROSS_DOMAINS if group == "positive" else DOMAINS)
        assert max(counts.values()) - min(counts.values()) <= 1
    near_counts = Counter(t.domain for t in tasks if t.group == "near_miss")
    assert near_counts["searchqa"] == 8
    assert sum(near_counts[d] for d in CROSS_DOMAINS) == 8
    for task in tasks:
        assert Task.from_dict(json.loads(json.dumps(task.to_dict()))) == task
        assert evaluate_control_answer(task, f"<answer>{task.gold}</answer>")["correct"]


def test_calibration_holdout_have_disjoint_entities_and_structural_families():
    calibration, holdout = (build_controls(split=s) for s in SPLITS)
    assert not {t.id for t in calibration} & {t.id for t in holdout}
    assert not {t.family for t in calibration} & {t.family for t in holdout}
    c_entities = {e for t in calibration for e in t.metadata["entities"]}
    h_entities = {e for t in holdout for e in t.metadata["entities"]}
    assert not c_entities & h_entities
    assert not {t.gold for t in calibration if t.group != "unrelated"} & {t.gold for t in holdout if t.group != "unrelated"}


def test_original_searchqa_builder_preserves_entire_context():
    for split in SPLITS:
        for task in build_controls(split=split):
            assert task.prompt == _build_user(task.metadata["question"], task.metadata["context"])
            assert len(task.metadata["context"]) < 6000
            assert task.metadata["context"] in task.prompt
            assert task.id not in task.prompt
            for marker in ['"gold":', '"latent_records":', '"selected_index":', "relation_constrained_evidence"]:
                assert marker not in task.prompt


def test_positive_oracle_unique_relation_join_and_random_winning_index():
    winners = []
    for task in build_controls(n_per_group=24):
        if task.group != "positive":
            continue
        constraints = task.metadata["query_constraints"]
        matches = [r for r in task.metadata["latent_records"] if all(r[k] == v for k, v in constraints.items())]
        assert len(matches) == 1
        assert matches[0]["answer"] == task.gold
        for record in task.metadata["latent_records"]:
            if record["answer"] != task.gold:
                assert any(record[key] != value for key, value in constraints.items())
        winners.append(task.metadata["selected_index"])
    assert len(set(winners)) >= 6


def test_near_miss_subtypes_are_not_confounded_with_domain():
    tasks = build_controls(n_per_group=36)
    for domain in DOMAINS:
        subtypes = {t.metadata["near_miss_kind"] for t in tasks if t.group == "near_miss" and t.domain == domain}
        assert subtypes == {"explicit_full_name", "specified_verbatim_text", "dependent_copies_vs_direct_source"}


def test_name_words_and_verbatim_articles_are_not_normalized_away():
    for split in SPLITS:
        for task in build_controls(split=split, n_per_group=27):
            if task.group != "near_miss":
                continue
            kind = task.metadata["near_miss_kind"]
            if kind == "explicit_full_name":
                shorthand = task.metadata["forbidden_shorthand"]
                assert not evaluate_control_answer(task, f"<answer>{shorthand}</answer>")["correct"]
                assert len(task.gold.split()) == 3
            elif kind == "specified_verbatim_text":
                shortened = " ".join(task.gold.split()[1:])
                assert not evaluate_control_answer(task, f"<answer>{shortened}</answer>")["correct"]
            else:
                wrong = task.metadata["copied_claim"]
                assert wrong != task.gold
                assert task.metadata["context"].count(wrong) > task.metadata["context"].count(task.gold)
                assert not evaluate_control_answer(task, f"<answer>{wrong}</answer>")["correct"]


def test_unrelated_numerical_oracles():
    for split in SPLITS:
        for task in build_controls(split=split):
            if task.group != "unrelated":
                continue
            p = task.metadata["parameters"]
            expected = p["a"] + p["b"] * p["c"] if split == "calibration" else (p["a"] + p["b"]) // p["c"]
            assert task.gold == str(expected)


def test_prefix_stability_for_prespecified_larger_runs():
    small = {t.id: t for t in build_controls(n_per_group=3)}
    large = {t.id: t for t in build_controls(n_per_group=16)}
    assert all(large[key] == value for key, value in small.items())


def test_only_whitespace_and_canonical_unicode_normalization():
    gold = {"gold": "The Ana María Research Unit"}
    assert evaluate_control_answer(gold, " <answer> The   Ana Mari\u0301a\nResearch Unit </answer> ")["correct"]
    for wrong in ["Ana María Research Unit", "The Ana María", "the Ana María Research Unit", "The Ana María Research Unit."]:
        assert not evaluate_control_answer(gold, f"<answer>{wrong}</answer>")["correct"]
    assert normalize_control_answer("a  b") == "a b"


@pytest.mark.parametrize("response", [
    "Some explanation <answer>X</answer>", "<answer>X</answer> extra", "<answer>X</answer><answer>X</answer>",
    "```<answer>X</answer>```", '{"answer":"X"}', "<answer></answer>", "<answer><b>X</b></answer>",
])
def test_output_schema_is_unambiguous_and_strict(response):
    assert not evaluate_control_answer({"gold": "X"}, response)["correct"]


@pytest.mark.parametrize("kwargs", [
    {"split": "train"}, {"n_per_group": 0}, {"n_per_group": True}, {"domains": []},
    {"domains": ["coding", "coding"]}, {"domains": ["unknown"]},
])
def test_invalid_parameters(kwargs):
    with pytest.raises(ValueError):
        build_controls(**kwargs)
