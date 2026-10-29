"""v2.10 acceptance arm removal and unchanged v2.3 instruments; authored offline cells."""
from collections import Counter

import pytest

from skillopt.execskill import acceptance, donors, placebo, profiles, reuse
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import fast_statistics, make_cells, seal  # noqa: F401
from tests.test_execskill_v23_acceptance_amendment import amend, physical


@pytest.mark.parametrize('kind', ['new', 'empty', 'delete'])
def test_prepare_never_builds_donors_or_shams_and_dispatch_has_no_placebo(kind, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('v2.10 must not generate donors or sham content')
    for module, name in ((donors, 'donor_corpus'), (placebo, 'placebo_package'),
                         (placebo, 'real_lengths'), (placebo, 'build_y'), (placebo, 'build_i')):
        monkeypatch.setattr(module, name, forbidden)
    sealed = seal(tmp_path, kind=kind, configuration=profiles.MAIN_V3,
                  rule=profiles.ACCEPT_RULES[profiles.MAIN_V3],
                  generate=lambda views: [{'id': 'g-' + key, 'source_item': key} for key in list(views)[:4]])
    jobs = physical(sealed)
    assert {'P_y', 'P_i'}.isdisjoint(job['arm'] for job in jobs)
    assert {j['arm'] for j in jobs if j['set'] == 'G_acc'} == {"S'", 'S', 'C'}
    assert sealed['corpus'] is sealed['placebo_y'] is sealed['placebo_i'] is None
    assert sealed['plan']['donors'] == {'pairs': {}, 'reuse': {}}
    assert sealed['seals']['donor_corpus'] is sealed['seals']['placebo_y'] is None
    assert 'placebo' not in sealed['packages']


@pytest.mark.parametrize('kind', ['new', 'empty', 'delete'])
def test_decision_removes_j2_and_uses_original_parent_gain(kind, tmp_path, fast_statistics):
    sealed = seal(tmp_path, kind=kind, configuration=profiles.MAIN_V3,
                  rule=profiles.ACCEPT_RULES[profiles.MAIN_V3])
    cells = make_cells(sealed)
    found = acceptance.decide(cells, sealed)
    assert found['guards']['J2'] == {'removed': True}
    assert found['placebo_rule'] == 'removed'
    assert set(found['contrasts']) == {"S'-S", "S'-C", 'S-C'}
    assert found['guards']['J1']['whole_batch'] == found['contrasts']["S'-S"]['whole_batch']
    assert found['guards']['J1']['rule'] == profiles.ACCEPT_RULES['main-v2-3']['name']
    assert acceptance.reproduce(cells, sealed, found)
    assert 'informational' not in found['guards']['J3']


def test_c_sample_and_same_text_j6_instrument_stay_independent(tmp_path, fast_statistics):
    old = seal(tmp_path, kind='empty', configuration=profiles.MAIN_V3,
               rule=profiles.ACCEPT_RULES[profiles.MAIN_V3])
    sealed = amend(old, lambda job: 'same')
    sample = sealed['reuse']['card_sample']
    assert len(sample['items']) == 30
    assert Counter(job['arm'] for job in physical(sealed)) == {'S': 120, 'C': 120}
    found = acceptance.decide(make_cells(sealed), sealed)
    assert found['guards']['J2'] == {'removed': True}
    assert found['guards']['J6_dup']['pairs'][0]['pair'] == 'C-S'
    assert found['contrasts']['S-C']['sample'] == 'sealed_C_instrument'
    assert found['contrasts']["S'-S"]['whole_batch'] == 0
    assert found['decision'] == 'reject'
    assert reuse.from_signatures(old, sealed['reuse']['signatures']) == sealed['reuse']


def test_inherited_auxiliary_instruments_remain_and_j2_is_removed_on_small_round(tmp_path, fast_statistics):
    instrument = seal(tmp_path / 'dup', configuration=profiles.MAIN_V3, dup=True,
                      rule=profiles.ACCEPT_RULES[profiles.MAIN_V3])
    assert 'S_dup' in {job['arm'] for job in physical(instrument)}
    assert acceptance.decide(make_cells(instrument), instrument)['guards']['J6_dup'] is not None
    small = seal(tmp_path / 'small', configuration=profiles.MAIN_V3, fires_n=lambda n: n < 2,
                 rule=profiles.ACCEPT_RULES[profiles.MAIN_V3])
    found = acceptance.decide([], small)
    assert found['decision'] == acceptance.SMALL and found['guards']['J2'] == {'removed': True}
