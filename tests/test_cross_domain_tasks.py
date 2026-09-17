"""Hard-oracle and isolation checks for the synthetic cross-domain diagnostic."""
from __future__ import annotations

import json
from collections import Counter

import pytest

from skillopt.cross_domain.tasks import CELLS, DEFAULT_DOMAINS, SPLITS, Task, build_tasks, evaluate_answer


def test_determinism_balance_and_serialization():
    for split in SPLITS:
        tasks = build_tasks(17, split, 3)
        assert tasks == build_tasks(17, split, 3)
        assert len(tasks) == len(DEFAULT_DOMAINS[split]) * len(CELLS) * 3
        counts = Counter((t.domain, t.mechanism, t.group) for t in tasks)
        assert set(counts.values()) == {3}
        assert len({t.id for t in tasks}) == len(tasks)
        assert len({t.prompt for t in tasks}) == len(tasks)
        for task in tasks:
            assert Task.from_dict(json.loads(json.dumps(task.to_dict()))) == task
            assert evaluate_answer(task, json.dumps({"answer": task.gold}))["correct"]


def test_disjoint_structural_families_and_held_out_domain():
    datasets = {split: build_tasks(42, split, 2) for split in SPLITS}
    for i, split in enumerate(SPLITS):
        for other in SPLITS[i + 1:]:
            assert not {t.id for t in datasets[split]} & {t.id for t in datasets[other]}
            assert not {t.family for t in datasets[split]} & {t.family for t in datasets[other]}
            assert not {t.metadata["structural_template"] for t in datasets[split]} & {
                t.metadata["structural_template"] for t in datasets[other]
            }
    assert {t.domain for t in datasets["train"]} == {"coding"}
    assert {t.domain for t in datasets["dev"]} == {"coding"}
    assert {t.domain for t in datasets["validation"]} == {"coding", "spreadsheet"}
    assert {t.domain for t in datasets["test"]} == {"coding", "spreadsheet", "rule_reasoning"}
    with pytest.raises(ValueError, match="held-out"):
        build_tasks(split="validation", domains=["rule_reasoning"])


def test_prompts_do_not_expose_labels_or_oracles():
    for split in SPLITS:
        for task in build_tasks(42, split, 2):
            for forbidden in ["constraint_preservation", "evidence_verification", "near_miss", "unrelated", '"gold"', task.id]:
                assert forbidden not in task.prompt
            assert task.prompt.endswith("Arrays must preserve the requested order.")
            assert task.metadata["mechanism_label_status"] == "hypothesized_not_behaviorally_proven"


def test_parameter_draws_prefix_stable():
    small = {t.id: t for t in build_tasks(8, "test", 2)}
    larger = {t.id: t for t in build_tasks(8, "test", 5)}
    assert all(larger[key] == task for key, task in small.items())


def test_constraint_training_oracle_independent():
    for task in build_tasks(41, "train", 5):
        if task.mechanism != "constraint_preservation":
            continue
        p = task.metadata["parameters"]
        if task.group == "near_miss":
            expected = [sum(p["inputs"]) * p["new_rate"], 0, 0]
        else:
            total, count, positions = 0, 0, 0
            for i, x in enumerate(p["inputs"]):
                value = x * p["new_rate"] if x >= p["threshold"] else x + p["bias"]
                total += value
                if value % p["modulus"] == 0:
                    count += 1
                    positions += i
            expected = [total, count, positions]
        assert task.gold == expected


def test_constraint_validation_oracle_independent():
    for task in build_tasks(9, "validation", 5):
        if task.mechanism != "constraint_preservation":
            continue
        p = task.metadata["parameters"]
        prices, total, fees = [], 0, 0
        for row in p["rows"]:
            price = row["price"]
            if task.group == "near_miss":
                price = p["new_discount"]
            elif row["category"] == p["target"] and not row["locked"]:
                price -= p["new_discount"]
            prices.append(price)
            line = price * row["quantity"]
            fee = p["fee"] if line > p["limit"] else 0
            total += line + fee
            fees += fee
        assert task.gold == [total, fees, prices]


def test_constraint_dev_ledger_oracle_independent():
    for task in build_tasks(12, "dev", 8):
        if task.mechanism != "constraint_preservation":
            continue
        p = task.metadata["parameters"]
        names = list(p["opening"])
        state = [0 if task.group == "near_miss" else p["opening"][key] for key in names]
        trace_total = 0
        for key, delta in p["events"]:
            i = names.index(key)
            if task.group == "positive":
                if key == p["target"]:
                    delta *= p["new_rate"]
                state[i] += delta
                if state[i] < 0:
                    state[i] = 0
                if state[i] > p["cap"]:
                    state[i] = p["cap"]
            else:
                state[i] += delta
            trace_total += sum(state)
        assert task.gold == state + [trace_total]


def test_constraint_test_oracle_independent_and_reset_not_preservation():
    for task in build_tasks(13, "test", 5):
        if task.mechanism != "constraint_preservation":
            continue
        p = task.metadata["parameters"]
        a, b, c = p["order"]
        if task.group == "near_miss":
            live, mirror, snapshot = [0] * 3, [0] * 3, [0] * 3
            live[a] = p["new_increment"]
            snapshot[b] = -p["offset"]
            # Initial snapshot[a] is zero because a,b,c are distinct.
            mirror[c] = 0
            snapshot[a] = 0
        else:
            live = p["initial"].copy()
            live[a] += p["new_increment"]
            live[c] += p["initial"][a]
            mirror = live.copy()
            snapshot = p["initial"].copy()
            snapshot[b] -= p["offset"]
            snapshot[a] = live[b] + live[c]
        assert task.gold == [live, mirror, snapshot, sum(live + mirror + snapshot)]
        if task.group == "near_miss":
            # Keeping the old initialization/alias contract violates the reset.
            old_live = p["initial"].copy()
            old_live[a] += p["new_increment"]
            old_live[c] += p["initial"][a]
            old_snapshot = p["initial"].copy()
            old_snapshot[b] -= p["offset"]
            old_snapshot[a] = old_live[b] + old_live[c]
            wrong = [old_live, old_live, old_snapshot, sum(old_live) * 2 + sum(old_snapshot)]
            assert not evaluate_answer(task, json.dumps({"answer": wrong}))["correct"]


def test_evidence_selection_and_calculation_independent():
    for split in SPLITS:
        for task in build_tasks(6, split, 5):
            if task.mechanism != "evidence_verification":
                continue
            p = task.metadata["parameters"]
            if task.group == "near_miss":
                assert p["selected_id"] != p["active_selected_id"]
                selected = next(r for r in p["records"] if r["id"] == p["selected_id"])
            else:
                eligible = []
                for r in p["records"]:
                    if split == "train":
                        ok = r["signed"] and r["issuer"] == p["authority"] and r["region"] == p["region"] and r["valid_from"] <= p["day"] < r["valid_until"]
                    elif split == "dev":
                        ok = r["hash"] in p["permitted_hashes"] and r["status"] == "approved" and r["region"] == p["region"]
                    elif split == "validation":
                        ok = r["signed"] and r["status"] == "approved" and r["issuer"] == p["authority"] and r["region"] == p["region"]
                    else:
                        ok = r["signed"] and not r["revoked"] and r["issuer"] == p["authority"] and r["valid_from"] <= p["day"] < r["valid_until"]
                    if ok:
                        eligible.append(r)
                assert len(eligible) == 3
                selected = max(eligible, key=lambda r: r["revision"])
                assert selected["id"] == p["selected_id"]
            values = []
            for q in p["quantities"]:
                value = q * selected["rate"] + selected["bias"]
                value = min(value, selected["cap"])
                value = max(value, 0)
                values.append(value)
            k = len([v for v in values if v >= p["threshold"]])
            expected = [sum(values) - k * selected["fee"], k,
                        sum(i * v for i, v in enumerate(values, 1)), max(values)]
            assert task.gold == expected


def test_counterfactual_evidence_is_not_automatically_replaced_by_active_policy():
    found_distinct = False
    for task in build_tasks(42, "validation", 10):
        if task.mechanism != "evidence_verification" or task.group != "near_miss":
            continue
        p = task.metadata["parameters"]
        eligible = [r for r in p["records"] if r["signed"] and r["status"] == "approved"
                    and r["issuer"] == p["authority"] and r["region"] == p["region"]]
        r = max(eligible, key=lambda r: r["revision"])
        values = [max(0, min(r["cap"], q * r["rate"] + r["bias"])) for q in p["quantities"]]
        k = sum(v >= p["threshold"] for v in values)
        active = [sum(values) - k * r["fee"], k, sum(i * v for i, v in enumerate(values, 1)), max(values)]
        if active != task.gold:
            found_distinct = True
            assert not evaluate_answer(task, json.dumps({"answer": active}))["correct"]
    assert found_distinct


def test_evidence_ids_are_not_a_fixed_answer_shortcut():
    tasks = build_tasks(42, "train", 20)
    active_ids = [t.metadata["parameters"]["active_selected_id"] for t in tasks
                  if t.mechanism == "evidence_verification" and t.group == "positive"]
    assert len(set(active_ids)) > 15


def test_evidence_revision_bands_overlap():
    active_revisions, distractor_revisions = [], []
    for task in build_tasks(42, "train", 20):
        if task.mechanism != "evidence_verification" or task.group != "positive":
            continue
        p = task.metadata["parameters"]
        active = next(r for r in p["records"] if r["id"] == p["active_selected_id"])
        assert len({r["revision"] for r in p["records"]}) == 8
        ineligible = [r for r in p["records"] if not (
            r["signed"] and r["issuer"] == p["authority"] and r["region"] == p["region"]
            and r["valid_from"] <= p["day"] < r["valid_until"]
        )]
        assert max(r["revision"] for r in ineligible) > active["revision"]
        active_revisions.append(active["revision"])
        distractor_revisions.extend(r["revision"] for r in ineligible)
    assert min(distractor_revisions) < min(active_revisions)
    assert max(distractor_revisions) > max(active_revisions)


def test_unrelated_oracles_independent():
    for split in SPLITS:
        for task in build_tasks(29, split, 3):
            if task.group != "unrelated":
                continue
            values = task.metadata["parameters"]["values"]
            if split == "train":
                kept = [x for x in values if x > 0 and x % 2 != 0]
                expected = [len(kept), sum(kept), sorted(kept)]
            elif split == "dev":
                prefixes = [sum(values[:i]) for i in range(1, len(values) + 1)]
                expected = [prefixes, max(prefixes), min(prefixes)]
            elif split == "validation":
                differences = [b - a for a, b in zip(values, values[1:])]
                expected = [differences, sum(map(abs, differences)), len([x for x in differences if x > 0])]
            else:
                products = [a * b for a, b in zip(values[:5], reversed(values[5:]))]
                expected = [products, sum(products), sorted(products)[len(products) // 2]]
            assert task.gold == expected


@pytest.mark.parametrize("response", [
    "not json", '```json\n{"answer": [1, 2]}\n```', '{"answer":[1,2],"extra":0}',
    '{"answer":[1,2],"answer":[1,2]}', '{"answer":NaN}', '{"answer":1e999}', '[1,2]', '{"answer":[true,2]}',
])
def test_strict_output_failure(response):
    assert not evaluate_answer({"gold": [1, 2]}, response)["correct"]


def test_numeric_equivalence_and_array_order():
    assert evaluate_answer({"gold": [1, 2]}, '{"answer":[1.0,2]}')["correct"]
    assert not evaluate_answer({"gold": [1, 2]}, '{"answer":[2,1]}')["correct"]


@pytest.mark.parametrize("kwargs", [
    {"split": "unknown"}, {"n_per_cell": 0}, {"n_per_cell": True},
    {"domains": []}, {"domains": ["coding", "coding"]}, {"domains": ["made_up"]},
])
def test_invalid_protocol_parameters(kwargs):
    with pytest.raises(ValueError):
        build_tasks(**kwargs)
