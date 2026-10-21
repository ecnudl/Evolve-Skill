"""coevo5 readings (registration §12; v2: delta §9; v3: delta §1): paired resampling with OfficeQA source-file groups,
the three missingness variants with one value per shared record, the claims' bounds, the transfer classes, and the
registered set of a family -- v3: I-ds beyond its instructions and its Q1-Q3 primary, E-ds secondary, the NoSkill-ds
reference at stage 0 only; v2's GLM-5.3 family keeps E-glm primary. No baseline test."""
import pytest

from skillopt.coevo5 import readout as r
from skillopt.coevo5.protocol import ORDER

N = 40
E, I = r.METHOD, r.INSTRUCTED  # v3: E-ds, I-ds


def _panels(n=N):
    return {b: r.panel(["%s-%02d" % (b, i) for i in range(n)]) for b in ORDER}


def _units(rate, *, chains=r.CHAIN_NAMES, n=N):
    """Every chain at every stage (the reference at stage 0 only) passes the first round(rate(chain, stage, bench) *
    n) items."""
    units = {}
    for chain in chains:
        for stage in r.STAGES if chain != r.REFERENCE else (0,):
            for bench in ORDER:
                passed = round(rate(chain, stage, bench) * n)
                tokens = {"%s-%02d" % (bench, i): "pass" if i < passed else "fail" for i in range(n)}
                units[(chain, stage, bench)] = r.Unit("%s/s%d/%s" % (chain, stage, bench), tokens)
    return units


def _set(units, key, item, token):
    tokens = dict(units[key].tokens)
    tokens[item] = token
    units[key] = r.Unit(units[key].source, tokens)


def test_items_sharing_a_source_file_are_resampled_together():
    found = r.panel(["a", "b", "c", "d", "e"], {"a": ["f1"], "b": ["f2", "f3"], "c": ["f3"], "d": ["f4"],
                                                "e": ["f1", "f5"]})
    assert found.items == ("a", "b", "c", "d", "e") and found.groups == (0, 1, 1, 2, 0)
    assert r.panel(["x", "y"]).groups == (0, 1)
    with pytest.raises(ValueError):
        r.panel(["a", "b"], {"a": ["f"]})


def test_the_transfer_classes_follow_the_similarity_map():
    cells = r.transfer_cells()
    assert len(cells["self"]) == 5 and len(cells["rest"]) == 15
    assert cells["similar"] == [(1, "officeqa"), (2, "livemath"), (2, "searchqa"), (3, "officeqa"),
                                (4, "officeqa")]
    assert (2, "spreadsheetbench") in cells["rest"]  # similar, but no checkable target


def test_identical_chains_give_zero_and_the_draw_is_seeded():
    units = _units(lambda chain, stage, bench: 0.5)
    first = r.Readings(units, _panels(), resamples=500).reading(r.difference(r.macro(E, 5),
                                                                              r.macro(I, 5)))
    again = r.Readings(units, _panels(), resamples=500).reading(r.difference(r.macro(E, 5),
                                                                              r.macro(I, 5)))
    assert first == again and first["known"]["estimate"] == 0 and first["known"]["interval95"] == [0, 0]


def test_a_shared_record_has_one_value_and_cancels():
    units = _units(lambda chain, stage, bench: 0.5)
    _set(units, (E, 1, "searchqa"), "searchqa-30", "unknown")
    units[(E, 2, "searchqa")] = units[(E, 1, "searchqa")]  # reused for a byte-identical Skill
    readings = r.Readings(units, _panels(), resamples=200)
    found = readings.reading(r.difference(r.macro(E, 2), r.macro(E, 1)))
    assert {v: found[v]["estimate"] for v in r.VARIANTS} == {"known": 0, "low": 0, "high": 0}
    assert found["known"]["items"]["searchqa"] == N - 1 and found["low"]["items"]["searchqa"] == N


def test_unknown_records_move_the_reading_down_in_low_and_up_in_high():
    units = _units(lambda chain, stage, bench: 0.5)
    _set(units, (E, 5, "officeqa"), "officeqa-39", "unknown")  # positive coefficient
    _set(units, (I, 5, "officeqa"), "officeqa-38", "unknown_artifact")  # negative coefficient
    found = r.Readings(units, _panels(), resamples=200).reading(
        r.difference(r.macro(E, 5), r.macro(I, 5)))
    step = 100 / 5 / N  # one record, in macro points
    assert found["low"]["estimate"] == pytest.approx(-step) and found["high"]["estimate"] == pytest.approx(step)
    assert found["known"]["estimate"] == 0 and found["known"]["items"]["officeqa"] == N - 2  # dropped pairwise


def test_a_transformed_reading_is_computed_on_the_records_imputed_for_its_sum():
    units = _units(lambda chain, stage, bench: 0.5 if stage < 5 else 0.4)
    readings = r.Readings(units, _panels(), resamples=200)
    plain = readings.reading(r.mean_forgetting(E))
    truncated = r.chain_readings(readings, E)["mean_forgetting_truncated"]
    assert plain["known"]["estimate"] == pytest.approx(10) and truncated["known"]["estimate"] == pytest.approx(10)
    units = _units(lambda chain, stage, bench: 0.5 if stage < 5 or bench != "searchqa" else 0.6)
    found = r.chain_readings(r.Readings(units, _panels(), resamples=200), E)
    assert found["mean_forgetting"]["known"]["estimate"] == pytest.approx(-2.5)
    assert found["mean_forgetting_truncated"]["known"]["estimate"] == pytest.approx(0)


def test_a_chain_that_was_not_evaluated_gives_readings_that_are_not_assessable():
    units = {k: v for k, v in _units(lambda chain, stage, bench: 0.5).items() if k[0] != I or k[1] < 3}
    readings = r.Readings(units, _panels(), resamples=200)
    found = readings.reading(r.difference(r.macro(E, 5), r.macro(I, 5)))
    assert found["available"] is False and I + "/s5/searchqa" in found["missing"]
    assert r.noninferiority(found, 3) is None and r.holds_large(found, 0) is None


def test_noninferiority_has_three_outcomes():
    def outcome(method):
        units = _units(lambda chain, stage, bench: method if chain == E and stage == 5 else 0.5, n=200)
        found = r.Readings(units, _panels(200), resamples=500).reading(
            r.difference(r.macro(E, 5), r.macro(I, 5)))
        return r.noninferiority(found, 3)
    assert outcome(0.6) == "not_worse" and outcome(0.3) == "worse" and outcome(0.47) == "uncertain"


def test_v3_registers_the_deepseek_family_with_i_ds_primary_and_no_baseline_test():
    assert (r.METHOD, r.INSTRUCTED, r.REFERENCE) == ("E-ds", "I-ds", "NoSkill-ds") and r.FAMILY == "ds"
    flat = _units(lambda chain, stage, bench: 0.5, n=200)
    found = r.registered(r.Readings(flat, _panels(200), resamples=300), {})
    assert set(found) == {"family", "chains", "updates", "primary", "transfer", "secondary"}
    primary = found["primary"]
    assert (primary["chain"], primary["kind"]) == ("I-ds", "exceeds_instructions")
    assert primary["status"] == {"method_moved": None, "stages_with_accepted_rules": None, "verdict": False}
    assert set(found["chains"]) == {"I-ds", "E-ds", "NoSkill-ds"}
    assert set(found["chains"]["NoSkill-ds"]) == {"macro", "accuracy"}
    # no I-ds merge record (the chain has not ended): its updates are unavailable, never "no update"
    assert found["transfer"]["similar_placement_used"] is None and found["updates"]["E-ds"]["moved"] is None
    assert (found["secondary"]["chain"], found["secondary"]["kind"]) == ("E-ds", "learning_gain")


@pytest.mark.parametrize("updates, moved, similar", [
    ({}, None, None),  # I-ds has not ended
    ({"I-ds": {1: {"local": 1, "similar": 0}, 2: {"local": 0, "similar": 0}}}, None, None),  # ended at stage 2
    ({"I-ds": {1: {"local": 1, "similar": 0}, 2: {"local": 0, "similar": 1}}}, True, True),  # already decided
    ({"I-ds": {k: {"local": int(k == 1), "similar": 0} for k in range(1, 6)}}, False, False)])
def test_the_primary_chain_s_update_status_is_unavailable_until_its_records_decide_it(updates, moved, similar):
    units = _units(lambda chain, stage, bench: 0.5, n=60)
    found = r.registered(r.Readings(units, _panels(60), resamples=50), updates)
    assert found["primary"]["status"]["method_moved"] is moved
    assert found["transfer"]["similar_placement_used"] is similar and found["transfer"]["method_moved"] is moved


def test_the_registered_readings_when_i_ds_learns_beyond_its_instructions():
    def rate(chain, stage, bench):
        if chain == r.REFERENCE:
            return 0.3
        if chain == "E-ds":
            return 0.4  # the scaffold adds 10 points over the blank prompt and E-ds learns nothing
        return 0.5 + (0.2 if stage >= r.stage_of(bench) else 0.0)  # learned benches rise and stay; no forgetting
    updates = {"I-ds": {1: {"local": 1}, 2: {"similar": 1}, 3: {"local": 2}},
               "E-ds": {k: {"local": 0, "similar": 0} for k in range(1, 6)}}
    found = r.registered(r.Readings(_units(rate, n=200), _panels(200), resamples=300), updates)
    primary = found["primary"]
    assert primary["reading"]["known"]["estimate"] == pytest.approx(20)
    assert primary["status"] == {"method_moved": True, "stages_with_accepted_rules": 3, "verdict": True}
    assert found["transfer"]["Q1"] is True and found["transfer"]["Q3"] is True
    assert found["transfer"]["Q2"] is False  # the similar benches did not rise before their own stage
    secondary = found["secondary"]
    assert secondary["gain"]["verdict"] is False and secondary["gain"]["reading"]["known"]["estimate"] == 0
    assert secondary["scaffold"]["known"]["estimate"] == pytest.approx(10)  # M_E-ds[0] - M_NoSkill-ds[0]
    assert secondary["scaffold_reaches_instructions"]["verdict"] == "worse"  # 40 against I-ds' 50 at stage 0
    assert found["updates"]["E-ds"] == {"stages_with_accepted_rules": 0, "moved": False, "similar_used": False}
    assert secondary["transfer"]["Q1"] is False and secondary["transfer"]["method_moved"] is False


def test_the_glm_family_keeps_v2_s_reading_with_e_glm_primary():
    names = r.FAMILIES["glm"]

    def rate(chain, stage, bench):
        if chain == names["reference"]:
            return 0.4
        if chain != names["method"]:
            return 0.5
        return 0.5 + (0.3 if stage >= r.stage_of(bench) else 0.0)
    chains = (names["method"], names["instructed"], names["reference"])
    units = {}
    for chain in chains:  # the reference at stage 0 only
        for stage in r.STAGES if chain != names["reference"] else (0,):
            for bench in ORDER:
                passed = round(rate(chain, stage, bench) * 200)
                units[(chain, stage, bench)] = r.Unit("%s/s%d/%s" % (chain, stage, bench), {
                    "%s-%02d" % (bench, i): "pass" if i < passed else "fail" for i in range(200)})
    updates = {"E-glm": {1: {"local": 1}, 2: {"similar": 1}, 3: {"local": 2}},
               "I-glm": {k: {"local": 0, "similar": 0} for k in range(1, 6)}}
    found = r.registered(r.Readings(units, _panels(200), resamples=300), updates, family="glm")
    assert (found["primary"]["chain"], found["primary"]["kind"]) == ("E-glm", "learning_gain")
    assert found["primary"]["reading"]["known"]["estimate"] == pytest.approx(30)
    assert found["primary"]["status"] == {"method_moved": True, "stages_with_accepted_rules": 3, "verdict": True}
    secondary = found["secondary"]
    assert (secondary["chain"], secondary["kind"]) == ("I-glm", "exceeds_instructions")
    assert secondary["gain"]["verdict"] is False and secondary["scaffold"]["known"]["estimate"] == pytest.approx(10)
    assert secondary["scaffold_reaches_instructions"]["verdict"] == "not_worse"
