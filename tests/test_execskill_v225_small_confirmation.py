"""Authored procedure confirmation cells; no solver or external inputs."""
import json
from types import SimpleNamespace

import pytest

from skillopt.execskill import profiles as p, step, v221_learning as learning, v221_rule, v222_runtime
from skillopt.execskill import v221_split as split, v225_phase as phase
from skillopt.execskill.package import with_
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import procedure
from tests.test_execskill_v221_learning import paired, signature
from tests.test_execskill_v225_phase import AuthoredStep


def comparison(fixed, broken, *, items=4, touched=None):
    touched = items if touched is None else touched
    assert fixed + broken <= touched <= items
    keys, cells = paired(fixed, broken, items - fixed - broken)
    signatures = {key: {'S': signature([key, 'parent']),
                        "S'": signature([key, 'candidate' if i < touched else 'parent'])}
                  for i, key in enumerate(keys)}
    # Production skips both cells when the rendered requests are identical.
    cells = {(arm, key): rows for (arm, key), rows in cells.items() if key in keys[:touched]}
    return keys, cells, signatures


def verdict(fixed, broken, *, items=4, touched=None, bench='officeqa', **kwargs):
    keys, cells, signatures = comparison(fixed, broken, items=items, touched=touched)
    return learning.confirmation_verdict(cells, keys, signatures, bench=bench, items=items, **kwargs)


@pytest.mark.parametrize('bench', ['officeqa', 'spreadsheetbench'])
@pytest.mark.parametrize('fixed,broken,passed', [
    (1, 0, True), (2, 0, True), (3, 0, True), (4, 0, True), (2, 1, True),
    (0, 0, False), (0, 1, False), (1, 1, False), (1, 2, False),
])
def test_main_v9_four_item_procedure_confirmation_table(bench, fixed, broken, passed):
    found = verdict(fixed, broken, bench=bench, configuration=p.MAIN_V9)
    assert (found['fixed'], found['broken'], found['net']) == (fixed, broken, fixed - broken)
    assert found['passed'] is passed
    assert found['reason'] == (None if passed else 'gain_and_no_harm')
    assert found['rule']['decision'] == ('accept' if passed else 'reject')
    assert found['rule']['gain_floor'] == 1
    assert found['rule']['small_slice_clause'] is True
    assert json.loads(json.dumps(found)) == found


@pytest.mark.parametrize('bench', ['searchqa', 'zebralogic'])
@pytest.mark.parametrize('touched', [4, 30])
@pytest.mark.parametrize('fixed,passed', [(2, False), (4, True)])
def test_forty_item_slice_keeps_old_floor_even_when_few_items_are_touched(bench, touched, fixed, passed):
    found = verdict(fixed, 0, items=40, touched=touched, bench=bench, configuration=p.MAIN_V9)
    assert found['passed'] is passed
    assert found['rule']['gain_floor'] == 3
    assert 'small_slice_clause' not in found['rule']
    assert found == verdict(fixed, 0, items=40, touched=touched, bench=bench)


@pytest.mark.parametrize('items,passed', [(29, True), (30, False)])
def test_small_slice_cutoff_is_strict_and_uses_slice_size(items, passed):
    found = verdict(2, 0, items=items, touched=4, configuration=p.MAIN_V9)
    assert found['passed'] is passed
    assert found['rule']['gain_floor'] == (1 if passed else 3)
    assert ('small_slice_clause' in found['rule']) is passed


@pytest.mark.parametrize('configuration', [None, p.MAIN_V7, p.MAIN_V8])
def test_old_configurations_and_default_keep_the_entire_confirmation_record(configuration):
    found = verdict(2, 0, configuration=configuration)
    keys, cells, _ = comparison(2, 0)
    assert found == verdict(2, 0)
    assert not found['passed'] and found['rule']['gain_floor'] == 3
    assert found['rule'] == v221_rule.decide(cells, keys, touched=keys)
    assert 'small_slice_clause' not in found['rule']


def test_small_clause_changes_only_effective_floor_decision_and_marker_in_rule():
    old = verdict(1, 0)['rule']
    new = verdict(1, 0, configuration=p.MAIN_V9)['rule']
    assert new == {**old, 'gain_floor': 1, 'decision': 'accept', 'small_slice_clause': True}
    assert new['constants']['GAIN_MIN_ITEMS'] == 3


def test_small_clause_still_requires_gain_when_no_request_changes():
    found = verdict(0, 0, touched=0, configuration=p.MAIN_V9)
    assert not found['passed'] and found['reason'] == 'gain_and_no_harm'
    assert found['rule']['reason'] == 'no_touched_items'
    assert found['rule']['small_slice_clause'] is True and found['rule']['gain_floor'] == 1


def test_small_clause_harm_ratio_rejects_despite_positive_net_and_whole_batch():
    found = verdict(4, 3, items=7, configuration=p.MAIN_V9)
    rule = found['rule']
    assert rule['net'] == rule['gain_floor'] == 1 and rule['whole_batch'] > 0
    assert rule['broken'] > rule['harm_cap'] and rule['small_slice_clause'] is True
    assert not found['passed'] and found['reason'] == 'gain_and_no_harm'


@pytest.mark.parametrize('bench', ['officeqa', 'spreadsheetbench'])
def test_small_clause_accepts_three_fixed_two_broken_at_exact_harm_cap(bench):
    # Five distinct changed items cannot fit in the ordinary four-item slice.
    found = verdict(3, 2, items=5, bench=bench, configuration=p.MAIN_V9)
    rule = found['rule']
    assert (rule['fixed'], rule['broken'], rule['net']) == (3, 2, 1)
    assert rule['broken'] == rule['harm_cap'] == 2
    assert rule['gain_floor'] == 1 and rule['small_slice_clause'] is True
    assert rule['decision'] == 'accept' and found['passed'] and found['reason'] is None


@pytest.mark.parametrize('whole_batch,passed', [(-.02, False), (-.01, True)])
def test_small_clause_retains_whole_batch_floor(monkeypatch, whole_batch, passed):
    # Confirmation has one binary-scored run per arm: positive net alone makes
    # its observed whole-batch delta positive. Inject an authored contrast via
    # the real upstream rule's explicit override to isolate this retained guard.
    decide = v221_rule.decide
    monkeypatch.setattr(v221_rule, 'decide', lambda cells, evaluated, *, touched:
        decide(cells, evaluated, touched=touched, whole_batch=whole_batch))
    found = verdict(2, 1, configuration=p.MAIN_V9)
    rule = found['rule']
    assert rule['net'] == rule['gain_floor'] == 1 and rule['broken'] <= rule['harm_cap']
    assert rule['whole_batch'] == whole_batch and rule['small_slice_clause'] is True
    assert found['passed'] is passed
    assert found['reason'] == (None if passed else 'gain_and_no_harm')


def test_profile_pins_small_procedure_clause_without_changing_main_v8_or_cards():
    identity = p.main_v9_identity()
    assert identity['confirmation_small_slice'] == {
        'below_items': phase.CONFIRMATION_SMALL_SLICE_BELOW_ITEMS,
        'gain_floor': phase.CONFIRMATION_SMALL_SLICE_GAIN_FLOOR,
        'harm_ratio': p.HARM_RATIO, 'whole_batch_floor': p.WHOLE_BATCH_FLOOR,
    }
    assert identity['confirmation_small_slice']['below_items'] == 30
    assert identity['confirmation_small_slice']['gain_floor'] == 1
    assert 'confirmation_small_slice' not in p.main_v8_identity()
    assert identity['card_phase']['confirmation'] == {'searchqa': 40}
    assert identity['card_phase']['gain_floor'] == 'max(3,ceil(0.05*T))'


def test_small_procedure_clause_does_not_relax_training_acceptance_or_card_rules():
    keys, cells, signatures = comparison(2, 0)
    trained = step.train_verdict(cells, keys, [], {'authored'}, predicate_faults=0,
        routed=4, sign=False, identical=[], configuration=p.MAIN_V9, touched=keys)
    assert not trained['adopted'] and trained['rule']['gain_floor'] == 3
    # Procedure acceptance consumes this same unchanged count rule.
    assert v221_rule.decide(cells, keys, touched=keys)['decision'] == 'reject'
    card = phase.decide(cells, keys, signatures=signatures)
    assert card['decision'] == 'reject' and card['gain_floor'] == 3
    assert 'small_slice_clause' not in card


def wire_confirmation(monkeypatch, *, fixed=1):
    """Author the paired outcomes while keeping each confirmation evaluator real."""
    monkeypatch.setattr(step, '_routes', lambda _st, package, views, publics: {
        key: SimpleNamespace(enabled=(), faults=[], to_json=lambda: {}) for key, _ in views})
    monkeypatch.setattr(step.solver, 'routing_view', lambda _bench, public, **kw: public)
    monkeypatch.setattr(step, '_pair_signatures', lambda _st, candidate, incumbent, publics, views, **kw: {
        key: {'S': signature([key, list(incumbent.order)]),
              "S'": signature([key, list(candidate.order)])} for key, _ in views})
    dispatched = []
    def dispatch(_st, attempt, endpoint, name, jobs, **kw):
        dispatched.extend(jobs)
        return [{'cell': {'id': digest([name, arm, key]), 'arm': arm, 'task_id': key, 'run': run},
                 'judge': {'v2': {'token': 'pass' if arm == "S'" and task['public']['index'] < fixed else 'fail'}},
                 'faults': [], 'final': {'outcome': 'pass', 'kind': 'score'}, 'sends': []}
                for arm, package, key, run, task in jobs]
    monkeypatch.setattr(step, '_cells', dispatch)
    monkeypatch.setattr(v222_runtime, 'cross_gate', lambda _st, attempt, **kw:
        (kw['candidate'], {'passed': True, 'candidate_sha256': kw['candidate'].sha256}))
    return dispatched


@pytest.mark.parametrize('bench', ['officeqa', 'spreadsheetbench'])
@pytest.mark.parametrize('configuration,passed', [(p.MAIN_V7, False), (p.MAIN_V8, False), (p.MAIN_V9, True)])
def test_production_confirm_eval_passes_configuration_to_real_gate(tmp_path, monkeypatch, bench,
                                                                 configuration, passed):
    st = AuthoredStep(tmp_path, bench)
    st.setting.extra['configuration'] = configuration
    candidate = with_(st.parent, step=st.name, add=(procedure(
        'fx-small-confirmation', ('applies', 'before_call'), origin=bench),))
    dispatched = wire_confirmation(monkeypatch)

    found = step._confirm_eval(st, st.cut, 1, st.parent, candidate)
    assert found['confirm']['passed'] is passed
    assert found['confirm']['rule']['gain_floor'] == (1 if passed else 3)
    assert ('small_slice_clause' in found['confirm']['rule']) is passed
    assert len(dispatched) == 8 and len(found['slice_ids']) == 4
    assert [kind for kind, _, _ in st.services.registry.calls] == ['register', 'dispatch', 'decide']
    # Per-procedure tallies remain unchanged feedback, even when the gate passes.
    feedback = found['procedure_confirmation'][candidate.order[0]]
    assert feedback['fixed'] == 1 and feedback['gain_floor'] == 3 and feedback['decision'] == 'reject'
    assert 'small_slice_clause' not in feedback


@pytest.mark.parametrize('bench', ['officeqa', 'spreadsheetbench'])
@pytest.mark.parametrize('configuration,passed', [(p.MAIN_V7, False), (p.MAIN_V8, False), (p.MAIN_V9, True)])
@pytest.mark.parametrize('fixed', [1, 2])
@pytest.mark.parametrize('n', [1, 'merge'])
def test_split_and_merged_confirmation_pass_configuration_to_real_gate(tmp_path, monkeypatch, bench,
                                                                      configuration, passed, fixed, n):
    st = AuthoredStep(tmp_path, bench)
    st.setting.extra['configuration'] = configuration
    procedures = tuple(procedure('fx-small-split-%d' % i, ('applies', 'before_call'), origin=bench)
                       for i in range(3))
    full = with_(st.parent, step=st.name, add=procedures)
    candidate = with_(st.parent, step=st.name, add=procedures[:2 if n == 'merge' else 1])
    dispatched = wire_confirmation(monkeypatch, fixed=fixed)
    source = {'slice_ids': [item['task_id'] for item in st.cut['confirm-r1']],
              'confirm': {'passed': False, 'reason': 'gain_and_no_harm'}}

    found = split.evaluate(st, st.cut, 1, n, st.parent, candidate, full, source, [], confirmation=True)

    rule = found['confirm']['rule']
    assert (rule['fixed'], rule['broken'], rule['net']) == (fixed, 0, fixed)
    assert found['confirm']['passed'] is passed
    assert rule['decision'] == ('accept' if passed else 'reject')
    assert found['confirm']['reason'] == (None if passed else 'gain_and_no_harm')
    assert rule['gain_floor'] == (1 if passed else 3)
    assert ('small_slice_clause' in rule) is passed
    assert found['slice_ids'] == source['slice_ids'] and len(found['slice_ids']) == 4
    assert found['full_candidate_sha256'] == full.sha256
    assert found['candidate_sha256'] == candidate.sha256
    assert found['selection_check'] == 'preregistered_split_of_original_decision'
    assert len(dispatched) == found['cells'] == 8
    assert all(row['rule'] == 'dispatched' for pair in found['cell_rules'].values() for row in pair.values())
    assert st.invocations == ['confirm-r1-split-' + ('merge' if n == 'merge' else 'p1')]
    # Split confirmation reuses the original decision occasion, not a new slice.
    assert st.services.registry.calls == []
    assert set(found['procedure_confirmation']) == set(candidate.order)
    for feedback in found['procedure_confirmation'].values():
        assert feedback['fixed'] == fixed and feedback['gain_floor'] == 3
        assert feedback['decision'] == 'reject' and 'small_slice_clause' not in feedback
