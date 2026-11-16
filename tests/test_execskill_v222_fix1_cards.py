"""D3 whole-card fallback: authored request bytes, no worker/model or real data."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.execskill import cells, instruction_start, profiles as p, reuse, solver, units
from skillopt.execskill import v222_cards as cards, v222_gate as gate, v222_read
from skillopt.execskill.package import empty, with_
from tests.execskill_fakes_env import FakeSandbox
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v222_cards import VIEWS, functions, sample

EVIDENCE = 'engineering_fixture'
PUBLIC = {**VIEWS, 'zebralogic': {
    'question': 'There are 2 houses, numbered 1 to 2 from left to right, as seen from across the street. Ana lives in house 1.',
    'columns': ['Name']}}


def setting(root, *, fallback=(), configuration=p.MAIN_V8):
    return units.Setting(run='a' * 64, root=root, shared=root / 'shared', pools={},
        cards={b: cards.format_text(b) for b in cards.BENCHES}, runtime={b: {} for b in cards.BENCHES},
        clients=None, budget=None, slots={}, sandbox={}, evidence=EVIDENCE,
        extra={'configuration': configuration, 'v222_fallbacks': {'G': list(fallback)}})


def identity(bench, package, text, runtime, configuration):
    worker = FakeSandbox(functions(package)).start(package, kind='cell') if package.for_bench(bench) else None
    try:
        if bench == 'alfworld':
            return gate._alf_signature(package, PUBLIC[bench], worker, card_text=text, configuration=configuration)
        return reuse.signature(bench, package, PUBLIC[bench], worker, card_text=text,
                               runtime=runtime, configuration=configuration)
    finally:
        if worker is not None:
            worker.close()


@pytest.mark.parametrize('bench', cards.BENCHES)
def test_whole_card_c_request_matches_main_v7_bytes_for_every_bench(tmp_path, bench):
    st = setting(tmp_path, fallback=[bench])
    local = units.for_unit(st, 'G', bench, 'G/s1-' + bench + '/run')
    initial = v222_read.start_package(local, 'G')
    assert not initial.for_bench(bench) and not cards.own_segments(initial, bench)
    assert local.cards[bench] == cards.historical_text(bench)
    historical = identity(bench, empty(step='G/s0', evidence=EVIDENCE), cards.historical_text(bench), {}, p.MAIN_V7)
    actual = identity(bench, initial, local.cards[bench], local.runtime[bench], p.MAIN_V8)
    assert actual['request_sha256'] == historical['request_sha256']
    assert actual['post_call'] == historical['post_call'] == []
    assert actual['faults'] == historical['faults'] == []
    # The input setting is not modified, and the other authored home requests
    # retain their original format blocks and exact seed procedure records.
    original = cards.initial_package(evidence=EVIDENCE, step='G/s0')
    for other in set(cards.BENCHES) - {bench}:
        assert local.cards[other] == st.cards[other] == cards.format_text(other)
        assert local.runtime[other] == st.runtime[other] == {}
        assert [q.to_json() for q in cards.own_segments(initial, other)] == [
            q.to_json() for q in cards.own_segments(original, other)]


@pytest.mark.parametrize('label', ['B', 'C0', 'C', 'F', 'S1'])
def test_every_nonblank_arm_receives_whole_card_and_learned_notes_remain_enabled(tmp_path, label):
    bench = 'officeqa'
    st = units.for_unit(setting(tmp_path, fallback=[bench]), 'G', bench, 'G/s2-officeqa/run')
    initial = v222_read.start_package(st, 'G')
    learned = cards.make_segment(bench, 'Use the supplied context carefully.', {'kind': 'public_evidence'},
                                 evidence=EVIDENCE, step=2)
    final = with_(initial, step='G/s2-officeqa', add=[learned])
    assert learned in final.for_bench(bench)
    arms = {**v222_read.arms(final, initial), 'S1': cells.Arm('candidate', final)}
    observed = []
    context = cells.Context(attempt=tmp_path / 'attempt-1', endpoint=SimpleNamespace(model=p.CHAINS['G']),
        runtime=st.runtime, cards=st.cards, native=None, episodes=None, worker=lambda _: None,
        evidence=EVIDENCE, configuration=p.MAIN_V8,
        solve=lambda *args, **kwargs: observed.append((args, kwargs)))
    cells._shell(context, {'benchmark': bench, 'arm': label}, {'public': PUBLIC[bench]}, arms[label], None)
    args, kwargs = observed[0]
    assert args[2] == ('' if label == 'B' else cards.historical_text(bench))
    assert cards.FALLBACK_RUNTIME_KEY not in kwargs['runtime']
    assert kwargs['configuration'] == p.MAIN_V8


def test_shared_qa_structure_cannot_reintroduce_foreign_seed_notes_on_fallback_bench():
    initial = cards.initial_package(evidence=EVIDENCE, fallback=['searchqa'])
    # Quantity-shaped SearchQA could otherwise match OfficeQA's seed predicate.
    view = PUBLIC['officeqa']
    found = reuse.signature('searchqa', initial, view, None,
        card_text=cards.historical_text('searchqa'), configuration=p.MAIN_V8)
    historical = reuse.signature('searchqa', empty(step='G/s0', evidence=EVIDENCE), view, None,
        card_text=cards.historical_text('searchqa'), configuration=p.MAIN_V7)
    assert found['enabled'] == [] and found['request_sha256'] == historical['request_sha256']


@pytest.mark.parametrize('bench', cards.BENCHES)
def test_failed_decomposition_keeps_measured_counts_and_selects_whole_card_without_new_note(bench):
    before = sample(bench, counter=0 if bench == 'alfworld' else 100)
    after = sample(bench, passed=0, counter=1 if bench == 'alfworld' else 100)
    result = cards.decomposition_decision(bench, before, after)
    assert result['decision'] == 'whole_card_fallback'
    assert result['historical'] == before and result['segmented'] == after
    assert result['hygiene_enabled'] is False and result['fallback_additional_model_cells'] == 0
    assert 'fallback_cap' not in result and 'fallback_rendered_chars' not in result


def test_historical_zebra_arm_uses_old_shell_even_before_a_fallback_is_selected(tmp_path):
    st = setting(tmp_path)
    observed = []
    context = cells.Context(attempt=tmp_path / 'attempt-1', endpoint=SimpleNamespace(model=p.CHAINS['G']),
        runtime=st.runtime, cards=st.cards, native=None, episodes=None, worker=lambda _: None,
        evidence=EVIDENCE, configuration=p.MAIN_V8,
        solve=lambda *args, **kwargs: observed.append((args, kwargs)))
    cells._shell(context, {'benchmark': 'zebralogic', 'arm': 'C_hist',
        'unit': 'G/v222-smoke/decomposition/zebralogic'}, {'public': PUBLIC['zebralogic']},
        cells.Arm('card', empty(step='G/s0', evidence=EVIDENCE)), None)
    args, kwargs = observed[0]
    assert solver._system('zebralogic', args[2], kwargs['runtime'], configuration=p.MAIN_V8) == solver.QA_SYSTEM
    assert cards.format_text('zebralogic') in solver._system('zebralogic', st.cards['zebralogic'], {}, configuration=p.MAIN_V8)


def test_fallback_selection_is_per_chain_and_does_not_mutate_the_source_setting(tmp_path):
    st = setting(tmp_path, fallback=['officeqa', 'alfworld'])
    before = deepcopy(st.cards), deepcopy(st.runtime), deepcopy(st.extra['v222_fallbacks'])
    first = units.for_unit(st, 'G', 'officeqa', 'G/s2-officeqa/run')
    second = units.for_unit(st, 'D', 'officeqa', 'D/s2-officeqa/run')
    assert first.cards['officeqa'] == cards.historical_text('officeqa')
    assert second.cards['officeqa'] == cards.format_text('officeqa')
    assert (st.cards, st.runtime, st.extra['v222_fallbacks']) == before
    assert instruction_start.active_cards(first.cards, p.MAIN_V8) == first.cards


def test_decomposition_uses_actual_registered_n_and_refuses_a_smaller_unregistered_identity():
    before = {**sample('searchqa', passed=10, counter=18), 'items': 18,
              'format_applicable': {'tag_present': 18}}
    after = {**before, 'passed': 9, 'observed_passed': 9}
    result = cards.decomposition_decision('searchqa', before, after, registered_count=18)
    assert result['whole_slice_gain'] == -1 / 18 and result['decision'] == 'whole_card_fallback'
    with pytest.raises(ValueError, match='registered practice slice'):
        cards.decomposition_decision('searchqa', before, after, registered_count=20)
    row = {'request_sha256': 'a' * 64, 'post_call': [], 'faults': []}
    pairs = {str(i): {'C_hist': row, 'C': row} for i in range(18)}
    assert cards.decomposition_identity('searchqa', pairs, registered_count=18)['identity_proven']
    with pytest.raises(ValueError, match='entire registered'):
        cards.decomposition_identity('searchqa', pairs, registered_count=19)


def test_available_count_decomposition_draw_has_floor18_and_allows_overlap():
    pools = {bench: ['authored-%02d' % i for i in range(18)] for bench in cards.BENCHES}
    found = cards.decomposition_slices(pools)
    assert all(row['count'] == 18 and set(row['items']) == set(pools[bench]) for bench, row in found.items())
    with pytest.raises(ValueError, match='v222_practice_supply_below_18'):
        cards.decomposition_slices({**pools, 'searchqa': pools['searchqa'][:-1]})


def test_cross_smoke_probe_preserves_whole_card_seed_scopes_and_parent_metadata(tmp_path, monkeypatch):
    from skillopt.execskill import v222_smoke
    parent = cards.initial_package(evidence=EVIDENCE, step='G/s0', fallback=['officeqa'])
    parent = replace(parent, retired=('a' * 64,), describer={parent.order[0]: {
        'prompt_sha256': 'b' * 64, 'text_sha256': 'c' * 64}})
    monkeypatch.setattr(v222_smoke.cards, 'initial_package', lambda **kwargs: parent)
    registered = {'harm': {'sha256': 'd' * 64, 'benches': {b: {'items': 18} for b in cards.BENCHES}}}
    monkeypatch.setattr(v222_smoke, 'practice', lambda st: ({}, {}, registered))
    monkeypatch.setattr(v222_smoke.units, 'drainer', lambda *args: None)
    monkeypatch.setattr(v222_smoke.units, 'run_unit', lambda root, **kwargs: {
        'result': kwargs['work'](tmp_path / 'attempt-1')})
    observed = []
    def check(**kwargs):
        candidate = kwargs['candidate']
        added = set(candidate.order) - set(parent.order)
        assert len(added) == 1 and candidate.procedures[:-1] == parent.procedures
        assert candidate.narrowed == parent.narrowed
        assert candidate.retired == parent.retired and candidate.describer == parent.describer
        assert candidate.parent_sha256 == parent.sha256
        assert {proc.id for proc in candidate.for_bench('officeqa')} == added
        observed.append(candidate)
        narrowed = replace(candidate, narrowed={**candidate.narrowed, next(iter(added)): ['officeqa']})
        return narrowed, {'passed': True, 'paired_item_calls': 2}
    monkeypatch.setattr(v222_smoke.gate, 'check', check)
    result = v222_smoke.cross_probe(setting(tmp_path, fallback=['officeqa']), 'G', fallback=['officeqa'])
    assert len(observed) == 2 and result['passed'] and result['narrowing_exercised']


@pytest.mark.parametrize('bench', [b for b in cards.BENCHES if b != 'zebralogic'])
def test_non_zebra_fallback_and_historical_arm_preserve_runtime_and_environment_digest(tmp_path, bench):
    from skillopt.execskill.alfworld_format import environment_runtime
    from skillopt.validator_pilot.api import digest
    st = setting(tmp_path, fallback=[bench])
    runtime = {'authored_engine_version': 'pinned-v1', 'reset_options': {'seed': 13}}
    st.runtime[bench] = deepcopy(runtime)
    expected = digest(environment_runtime(runtime))
    local = units.for_unit(st, 'G', bench, 'G/s1-' + bench + '/run')
    assert local.runtime[bench] == runtime
    assert digest(environment_runtime(local.runtime[bench])) == expected
    observed = []
    context = cells.Context(attempt=tmp_path / 'attempt-1', endpoint=SimpleNamespace(model=p.CHAINS['G']),
        runtime=local.runtime, cards=local.cards, native=None, episodes=None, worker=lambda _: None,
        evidence=EVIDENCE, configuration=p.MAIN_V8,
        solve=lambda *args, **kwargs: observed.append(kwargs['runtime']))
    cells._shell(context, {'benchmark': bench, 'arm': 'C_hist',
        'unit': 'G/v222-smoke/decomposition/' + bench}, {'public': PUBLIC[bench]},
        cells.Arm('card', empty(step='G/s0', evidence=EVIDENCE)), None)
    assert observed == [runtime]
    assert digest(environment_runtime(observed[0])) == expected
