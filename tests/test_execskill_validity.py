"""T-VAL-1..4 (implementation plan §8; registration §7.2 "预测效度" after Codex F9, §3.3 G_acc): the examiner's
predictive validity from acceptance rounds -- one (d_gen, d_real) pair per round with its within-round covariance, the
duplicate-arm negative control, and the status rule with the precedence refuted > validated > not_evaluable. The
rounds are sealed with the synthetic acceptance world of tests/test_execskill_acceptance.py. Offline and
deterministic."""
from __future__ import annotations

import math
import statistics

import pytest

from skillopt.execskill import acceptance, stats_ext, validity
from skillopt.execskill.protocol import SEED, VALIDITY_PERMUTATIONS
from tests.test_execskill_acceptance import PATTERNS, make_cells, outcome, seal


def generated(views):
    """The examiner's generator stand-in: one generated item per A* item, generated on its public view."""
    return [{"id": "gen-" + item, "source_item": item} for item in views]


@pytest.fixture(scope="module")
def rounds_sealed(tmp_path_factory):
    return {"gen": seal(tmp_path_factory.mktemp("gen"), generate=generated, dup=True),
            "plain": seal(tmp_path_factory.mktemp("plain"))}


def pairs(n, *, disagree=0, se=0.02, cov=0.0):
    """``n`` monotone rounds (d_gen tracks d_real); the last ``disagree`` rounds read 30 points higher on G_acc."""
    out = []
    for r in range(n):
        d = 0.01 * (r + 1)
        out.append({"d_gen": d + (0.3 if r >= n - disagree else 0.0), "d_real": d, "se_gen": se, "se_real": se,
                    "cov": cov})
    return out


CLEAN = {"pair": "S_dup-S", "gen_ci95": [-0.02, 0.03], "real_ci95": [-0.01, 0.01]}


# ------------------------------------------------------------------- T-VAL-1 one evidence unit per round
def test_t_val_1_one_pair_per_round_with_its_within_round_covariance(tmp_path, monkeypatch, rounds_sealed):
    sealed = rounds_sealed["gen"]
    astar = sealed["plan"]["astar"]
    jobs = [j for block in acceptance.schedule(sealed).values() for j in block if j["set"] == "G_acc"]
    assert sorted({j["arm"] for j in jobs}) == sorted(["S'", "S", "P_y", "C", "S_dup"])
    assert all(j["run"] == 0 and j["source_item"] in astar for j in jobs) and len(jobs) == 5 * len(astar)
    cells = make_cells(sealed)
    pair = validity.round_pair(cells, sealed)
    real = [float(x) for x in acceptance.differences(acceptance.table(cells), "S'", "S", astar)]
    gen = [float(x) for x in acceptance.differences(acceptance.table(cells, "G_acc"), "S'", "S",
                                                    ["gen-" + i for i in astar])]
    n = len(astar)
    assert pair["n_gen"] == pair["n_real"] == n == 45
    assert pair["d_real"] == pytest.approx(statistics.mean(real)) and pair["d_gen"] == pytest.approx(
        statistics.mean(gen))
    assert pair["se_real"] == pytest.approx(statistics.stdev(real) / math.sqrt(n))
    assert pair["se_gen"] == pytest.approx(statistics.stdev(gen) / math.sqrt(n))
    s_gr = sum((g - statistics.mean(gen)) * (r - statistics.mean(real)) for g, r in zip(gen, real)) / (n - 1)
    assert pair["cov"] == pytest.approx(n * s_gr / (n * n)) and pair["cov"] != 0
    # the round is ONE unit: its other contrasts are never further evidence
    assert validity.status([pair], dup=validity.dup_control(cells, sealed))["rounds"] == 1
    # no pair without G_acc, or when the round did not run
    plain = rounds_sealed["plain"]
    plain_cells = make_cells(plain)
    assert validity.round_pair(plain_cells, plain) is None and validity.dup_control(plain_cells, plain) is None
    with pytest.raises(ValueError, match="G_acc"):  # one generated item per A* item at most
        seal(tmp_path / "twice", generate=lambda views: generated(views) * 2)
    monkeypatch.setitem(acceptance.G_ACC, "officeqa", 10)  # the bench's registered maximum (§3.3)
    with pytest.raises(ValueError, match="G_acc"):
        seal(tmp_path / "many", generate=generated)


def test_t_val_1_duplicate_pair_control_on_both_item_sets(rounds_sealed):
    sealed = rounds_sealed["gen"]
    clean = validity.dup_control(make_cells(sealed), sealed)
    assert clean == {"pair": "S_dup-S", "gen_ci95": [0.0, 0.0], "real_ci95": [0.0, 0.0]}
    token = outcome(PATTERNS)
    drift = make_cells(sealed, lambda job: "pass" if job["arm"] == "S_dup" and job["set"] == "G_acc" else token(job))
    control = validity.dup_control(drift, sealed)
    assert control["gen_ci95"][0] > 0 and control["real_ci95"] == [0.0, 0.0]


# ------------------------------------------------------------------------ T-VAL-2 fewer than 8 rounds
def test_t_val_2_fewer_than_eight_rounds_are_not_evaluable_whatever_the_disagreement():
    far = {"d_gen": 0.5, "d_real": -0.5, "se_gen": 0.01, "se_real": 0.01, "cov": 0.0}
    dirty = {"pair": "S_dup-S", "gen_ci95": [0.2, 0.4], "real_ci95": [-0.1, 0.1]}
    out = validity.status([far] * 7, dup=dirty)
    assert out["status"] == "not_evaluable" and out["rounds"] == 7 and out["disagreements"] == 7
    assert out["rho"] is None and out["p_perm"] is None
    assert validity.status(pairs(7) + [None] * 5, CLEAN)["status"] == "not_evaluable"  # rounds without a pair
    assert validity.status([], None)["status"] == "not_evaluable"


# ------------------------------------------------------------------------------------- T-VAL-3 refuted
def test_t_val_3_refuted_by_two_disagreeing_rounds_or_a_drifting_duplicate():
    refuted = validity.status(pairs(8, disagree=2), CLEAN)
    assert refuted["status"] == "refuted" and refuted["disagreements"] == 2
    one = validity.status(pairs(8, disagree=1), CLEAN)  # one disagreeing round refutes nothing
    assert one["status"] != "refuted" and one["disagreements"] == 1
    drifting = validity.status(pairs(8), {"pair": "S_dup-S", "gen_ci95": [0.01, 0.05], "real_ci95": [-0.01, 0.01]})
    assert drifting["status"] == "refuted" and drifting["disagreements"] == 0
    # the pooled SE subtracts the within-round covariance: 5 points apart is within 2 SE only without it
    apart = {"d_gen": 0.10, "d_real": 0.05, "se_gen": 0.02, "se_real": 0.02}
    assert not validity.disagrees({**apart, "cov": 0.0}) and validity.disagrees({**apart, "cov": 0.0002})
    # precedence: the last two rounds keep the ranks monotone (rho = 1) but disagree -> refuted, not validated
    assert stats_ext.spearman_perm([p["d_gen"] for p in pairs(8, disagree=2)],
                                   [p["d_real"] for p in pairs(8, disagree=2)], n=1000)[0] == pytest.approx(1.0)
    with pytest.raises(ValueError):
        validity.status([{"d_gen": 0.1}] * 8, CLEAN)


# ----------------------------------------------------------------------------------- T-VAL-4 validated
def test_t_val_4_validated_by_rank_agreement_over_rounds_with_a_clean_duplicate():
    rounds = pairs(8)
    out = validity.status(rounds, CLEAN)
    rho, p = stats_ext.spearman_perm([r["d_gen"] for r in rounds], [r["d_real"] for r in rounds],
                                     n=VALIDITY_PERMUTATIONS, seed=SEED)
    assert VALIDITY_PERMUTATIONS == 10_000 and SEED == 20261021
    assert out["status"] == "validated" and out["rho"] == pytest.approx(1.0) and out["p_perm"] == p < 0.05
    assert rho == out["rho"]
    assert validity.status(rounds, None)["status"] == "not_evaluable"  # no duplicate pair ran
    real_drift = {"pair": "S_dup-S", "gen_ci95": [-0.02, 0.03], "real_ci95": [0.01, 0.03]}
    assert validity.status(rounds, real_drift)["status"] == "not_evaluable"  # validated needs BOTH sets clean
    reversed_ranks = pairs(8, se=0.1)  # wide SEs: no round disagrees, but the ranks run backwards
    for r in reversed_ranks:
        r["d_gen"] = 0.09 - r["d_real"]
    backwards = validity.status(reversed_ranks, CLEAN)
    assert backwards["status"] == "not_evaluable" and backwards["disagreements"] == 0 and backwards["rho"] < 0
    assert validity.status(rounds * 2, CLEAN)["status"] == "validated"  # 16 rounds, ties in both rankings
