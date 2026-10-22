"""T-STATS-1..7 (implementation plan §8.1): the primary one-sided paired t-test (plain, block-stratified, ALFWorld
games-weighted on room means; registration §6.4 after Codex F1), its size under the registered skewed null by exact
enumeration (calc T9), null uniformity by a small seeded simulation, the sensitivity analyses that never decide,
IUT, Holm, the validity rounds' permutation Spearman, L/H item scores with ``unknown_fault`` (§6.3), and the power
model of §6.6 (calc T1-T2). Offline and deterministic (fixed seeds).
"""
from __future__ import annotations

import math
import random
from fractions import Fraction
from statistics import NormalDist

import pytest

from skillopt.execskill import stats_ext

Z95, Z80 = NormalDist().inv_cdf(0.95), NormalDist().inv_cdf(0.80)


def df1(t):
    """P(T_1 >= t): Cauchy, closed form."""
    return 0.5 - math.atan(t) / math.pi


def df2(t):
    """P(T_2 >= t), closed form."""
    return 0.5 - t / (2 * math.sqrt(2 + t * t))


# ------------------------------------------------------------------------- T-STATS-1: the plain test by hand
def test_t_stats_1_paired_t_equals_a_hand_computation():
    found = stats_ext.paired_t([0.25, 0.75])  # mean 0.5, s^2 0.125, se 0.25, t 2, df 1
    assert found["mean"] == 0.5 and found["df"] == 1
    assert found["se"] == pytest.approx(0.25) and found["t"] == pytest.approx(2.0)
    assert found["p"] == pytest.approx(df1(2.0), abs=1e-12)
    found = stats_ext.paired_t([Fraction(0), Fraction(1, 2), Fraction(1)])  # t = sqrt(3), df 2
    assert found["t"] == pytest.approx(math.sqrt(3)) and found["p"] == pytest.approx(df2(math.sqrt(3)), abs=1e-12)
    assert stats_ext.t_upper(-2.0, 1) == pytest.approx(1 - df1(2.0), abs=1e-12)
    assert stats_ext.t_upper(0.0, 7) == pytest.approx(0.5)


def test_t_stats_1_degenerate_and_invalid_inputs():
    assert stats_ext.paired_t([0.5, 0.5]) == {"mean": 0.5, "se": 0.0, "df": 1, "t": None, "p": 0.0}
    assert stats_ext.paired_t([0, 0, 0])["p"] == 1.0
    for bad in ([0.5], [], [1.5, 0], [True, 0.5]):
        with pytest.raises(ValueError):
            stats_ext.paired_t(bad)


# -------------------------------------------------------- T-STATS-2: blocks and ALFWorld's games-weighted rooms
def test_t_stats_2_block_stratified_t():
    d, strata = [0.25, 0.75, -0.5, 0.5], ["b1", "b1", "b2", "b2"]
    found = stats_ext.paired_t(d, strata=strata)  # block means 0.5 / 0; pooled SS 0.625 on 4 - 2 df
    assert found["df"] == 2 and found["mean"] == pytest.approx(0.25)
    assert found["se"] == pytest.approx(math.sqrt(0.625 / 2 / 4))
    assert found["p"] == pytest.approx(df2(0.25 / math.sqrt(0.625 / 2 / 4)), abs=1e-12)
    assert stats_ext.paired_t(d)["df"] == 3  # unstratified
    with pytest.raises(ValueError):
        stats_ext.paired_t([0.5, 0.25], strata=["b1", "b2"])  # no residual degree of freedom


def test_t_stats_2_alfworld_games_weighted_t_on_room_means():
    d, rooms = [1, 0, 0.5, -0.5, 0, 0.5], ["r1", "r1", "r2", "r3", "r3", "r3"]
    found = stats_ext.paired_t(d, clusters=rooms)  # room means .5/.5/0, weights 2/1/3, df = 3 rooms - 1 block
    assert found["df"] == 2 and found["mean"] == pytest.approx(0.25)
    assert found["t"] == pytest.approx(math.sqrt(2)) and found["p"] == pytest.approx(df2(math.sqrt(2)), abs=1e-12)
    # equal room sizes: the plain t-test on the room means
    even = stats_ext.paired_t([1, 0, 0.5, 0.5, -0.5, 0.5], clusters=["a", "a", "b", "b", "c", "c"])
    plain = stats_ext.paired_t([0.5, 0.5, 0])
    assert (even["df"], even["t"], even["p"]) == (plain["df"], pytest.approx(plain["t"]), pytest.approx(plain["p"]))
    # blocks made of whole rooms: df = rooms - blocks
    blocked = stats_ext.paired_t([1, 0, 0.5, -0.5, 0, 0.5], clusters=["a", "a", "b", "c", "d", "d"],
                                 strata=["x", "x", "x", "y", "y", "y"])
    assert blocked["df"] == 4 - 2
    with pytest.raises(ValueError, match="whole rooms"):
        stats_ext.paired_t([1, 0, 0.5, 0.5], clusters=["a", "a", "b", "b"], strata=["x", "y", "x", "x"])


# --------------------------------------------------- T-STATS-3: size under the skewed null N1 (calc T9), exactly
def compositions(n, parts):
    if parts == 1:
        yield (n,)
        return
    for k in range(n + 1):
        for rest in compositions(n - k, parts - 1):
            yield (k,) + rest


def exact_size(null, n):
    """P(one-sided 5 % rejection) of ``paired_t`` under an i.i.d. null, by enumerating every composition."""
    size = 0.0
    for counts in compositions(n, len(null)):
        weight = math.factorial(n)
        for (_, p), k in zip(null, counts):
            weight = weight / math.factorial(k) * p ** k
        sample = [Fraction(v) for (v, _), k in zip(null, counts) for _ in range(k)]
        size += weight * (stats_ext.paired_t(sample)["p"] <= 0.05)
    return size


@pytest.mark.parametrize("null,n,expected", [
    (((0.25, 0.8), (-1.0, 0.2)), 30, 0.123),  # N1 (Codex), calc T9
    (((0.25, 0.8), (-1.0, 0.2)), 41, 0.066),
    (((-0.5, 0.25), (0.0, 0.5), (0.5, 0.25)), 30, 0.049),  # N0, the symmetric reference
])
def test_t_stats_3_exact_size_reproduces_calc_t9(null, n, expected):
    assert round(exact_size(null, n), 3) == expected


def test_t_stats_3_null_p_values_are_near_uniform_in_a_small_simulation():
    rng = random.Random(20261021)
    for n in (10, 30):
        ps = [stats_ext.paired_t([rng.uniform(-1, 1) for _ in range(n)])["p"] for _ in range(4000)]
        assert 0.04 <= sum(p <= 0.05 for p in ps) / len(ps) <= 0.06
        assert 0.22 <= sum(p <= 0.25 for p in ps) / len(ps) <= 0.28
        assert 0.47 <= sum(p <= 0.5 for p in ps) / len(ps) <= 0.53


# -------------------------------------------------------------- T-STATS-4: sensitivity analyses never decide
def test_t_stats_4_wilcoxon_and_signflip_by_hand():
    found = stats_ext.wilcoxon([0.5, -0.25, 0.25, 0.5])  # midranks 1.5/1.5/3.5/3.5, W+ 8.5, tie-corrected
    z = (8.5 - 5) / math.sqrt(4 * 5 * 9 / 24 - (6 + 6) / 48)
    assert found == pytest.approx(1 - NormalDist().cdf(z))
    assert stats_ext.wilcoxon([0, 0]) == 1.0
    assert stats_ext.signflip([0.5, 0.25, -0.25]) == pytest.approx(3 / 8)  # exact over 8 patterns
    assert stats_ext.signflip([0.5, 0.5, -0.25], clusters=["a", "a", "b"]) == pytest.approx(1 / 2)  # rooms flip whole
    many = [0.5] * 12 + [-0.25] * 8  # 2^20 > n: seeded Monte Carlo, reproducible
    assert stats_ext.signflip(many, n=2000, seed=7) == stats_ext.signflip(many, n=2000, seed=7)
    assert 0 < stats_ext.signflip(many, n=2000, seed=7) < 0.05


def test_t_stats_4_a_decision_follows_the_t_test_only():
    symmetric_break = [Fraction(1, 5)] * 25 + [Fraction(-1)] * 5  # mean exactly 0, skewed
    assert stats_ext.paired_t(symmetric_break)["p"] == pytest.approx(0.5)
    assert stats_ext.wilcoxon(symmetric_break) < 0.05  # Wilcoxon tests symmetry, not the mean (calc T9)
    assert stats_ext.signflip(symmetric_break, n=2000, seed=1) > 0.05
    decision = stats_ext.iut(symmetric_break, symmetric_break)
    assert decision.reject is False and decision.p == pytest.approx(0.5)
    assert set(decision.contrasts[0]) == {"mean", "se", "df", "t", "p"}  # no sensitivity value enters it


# ---------------------------------------------------------------------------------- T-STATS-5: IUT and Holm
def test_t_stats_5_iut_takes_the_larger_p():
    strong = [0.5] * 20 + [-0.25] * 10
    weak = [0.25] * 16 + [-0.25] * 14
    both = stats_ext.iut(strong, strong)
    assert both.reject is True and both.p == stats_ext.paired_t(strong)["p"]
    one = stats_ext.iut(strong, weak)
    assert one.reject is False and one.p == stats_ext.paired_t(weak)["p"] > 0.05
    rooms = stats_ext.iut(strong, strong, design1={"clusters": list(range(15)) * 2})
    assert rooms.contrasts[0]["df"] == 14
    harmful_sham = stats_ext.iut(strong, strong, alpha=0.025)
    assert harmful_sham.alpha == 0.025
    with pytest.raises(ValueError):
        stats_ext.iut(strong, strong, alpha=1.5)


def test_t_stats_5_holm():
    assert stats_ext.holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert stats_ext.holm([0.2, 0.5]) == pytest.approx([0.4, 0.5])
    assert stats_ext.holm([0.6, 0.9, 0.8]) == pytest.approx([1.0, 1.0, 1.0])
    assert stats_ext.holm([]) == []
    with pytest.raises(ValueError):
        stats_ext.holm([1.2])


# ------------------------------------------------------------ T-STATS-6: Spearman with permutations over rounds
def test_t_stats_6_spearman_permutes_over_rounds():
    assert stats_ext.spearman_perm([1, 2, 3], [10, 20, 30]) == (pytest.approx(1.0), pytest.approx(1 / 6))
    # rho 0.8: the identity and the three adjacent swaps reach it, exactly over the 24 orders
    assert stats_ext.spearman_perm([1, 2, 3, 4], [1, 3, 2, 4]) == (pytest.approx(0.8), pytest.approx(4 / 24))
    assert stats_ext.spearman_perm([1, 2, 3, 4], [4, 3, 2, 1]) == (pytest.approx(-1.0), pytest.approx(1.0))
    assert stats_ext.spearman_perm([1, 1, 1], [1, 2, 3]) == (None, 1.0)
    tied = stats_ext.spearman_perm([1, 2, 2, 3], [1, 2, 3, 4])
    assert tied[0] == pytest.approx(0.9486832980505138)
    rounds = list(range(8))  # 8! > 10,000: seeded permutations, p = (1 + hits) / (n + 1)
    rho, p = stats_ext.spearman_perm(rounds, rounds)
    assert rho == pytest.approx(1.0) and p < 0.001 and (rho, p) == stats_ext.spearman_perm(rounds, rounds)
    with pytest.raises(ValueError):
        stats_ext.spearman_perm([1], [1])


# --------------------------------------------------------------- T-STATS-7: L/H item scores with unknown_fault
def test_t_stats_7_item_scores_with_unknown_fault():
    cells = {("S'", "a"): ["pass", "unknown_fault"], ("S'", "b"): ["unknown_artifact", "fail"],
             ("S", "a"): ["unknown_fault", "unknown"], ("S", "b"): ["fail", "pass"]}
    assert stats_ext.item_scores(cells, "S'", ["a", "b"], side="L") == {"a": Fraction(1, 2), "b": Fraction(0)}
    assert stats_ext.item_scores(cells, "S", ["a", "b"], side="H") == {"a": Fraction(1), "b": Fraction(1, 2)}
    assert stats_ext.infrastructure_share(cells, "S", ["a", "b"]) == Fraction(1, 4)
    assert stats_ext.infrastructure_share(cells, "S'", ["a", "b"]) == Fraction(0)
    d = [stats_ext.item_scores(cells, "S'", ["a", "b"], side="L")[i]
         - stats_ext.item_scores(cells, "S", ["a", "b"], side="H")[i] for i in ("a", "b")]
    assert d == [Fraction(-1, 2), Fraction(-1, 2)]
    with pytest.raises(ValueError):
        stats_ext.item_scores(cells, "S'", ["a", "c"], side="L")
    with pytest.raises(ValueError):
        stats_ext.item_scores({("S'", "a"): ["maybe"]}, "S'", ["a"], side="H")
    with pytest.raises(ValueError):
        stats_ext.item_scores(cells, "S'", ["a"], side="M")


# ------------------------------------------------------------------------- the power model (§6.6, calc T1-T2)
def test_power_table_reproduces_calc_t1_t2():
    sb = 0.122 * math.sqrt(46 / 60) * 100 / (Z95 + Z80)  # calc ANCHOR / K
    oq = 0.103 * math.sqrt(37 / 50) * 100 / (Z95 + Z80)
    table = stats_ext.power_table(sb)
    assert [round(table[e]["single"], 2) for e in (3, 5, 10)] == [0.17, 0.32, 0.75]
    assert [round(table[e]["joint"], 2) for e in (3, 5, 10)] == [0.07, 0.17, 0.62]
    assert round(stats_ext.power_table(oq, effects=(5,))[5]["joint"], 2) == 0.24
    assert round(stats_ext.mde(sb), 1) == 12.1 and round(stats_ext.mde(oq, rho=0.7), 1) == 9.8


def test_bootstrap_ci_is_seeded_and_resamples_whole_rooms():
    d = [0.5] * 10 + [0.0] * 10
    lo, hi = stats_ext.bootstrap_ci(d, resamples=400, seed=3)
    assert lo < 0.25 < hi and (lo, hi) == stats_ext.bootstrap_ci(d, resamples=400, seed=3)
    rooms = stats_ext.bootstrap_ci(d, clusters=[i // 2 for i in range(20)], resamples=400, seed=3)
    assert rooms[0] <= 0.25 <= rooms[1]
