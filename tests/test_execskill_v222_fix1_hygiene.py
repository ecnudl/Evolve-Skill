"""D2 enters existing charged training decisions; no extra unit or role call."""
from copy import deepcopy

import pytest

from skillopt.execskill import budgets, profiles as p, step, v221_learning, v222_feedback, v222_limits, v222_runtime
from skillopt.execskill.package import edits, save, validate, with_
from tests.execskill_fakes_env import procedure
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v221_learning import FixtureStep, pool, training, confirmation
from tests.test_execskill_v222_hygiene import own, parent, trajectory


def setup(root):
    original = parent()
    save(root, original)
    st = FixtureStep(root, original)
    st.name = 'G/s1-searchqa'
    st.setting.extra = {'configuration': p.MAIN_V8, 'v222_fallbacks': {}}
    st.setting.evidence = st.evidence
    st.roles = lambda *_: pytest.fail('Controller deletion must not create or call a role')
    cut = {'run': pool(4), 'accept': pool(5)}
    pid = own(original)[0]
    current = [trajectory(original, [pid], 'searchqa/' + row['task_id']) for row in cut['run']]
    return st, cut, current, pid


def engineer_round(st, cut, r, incumbent=None):
    return step._engineer_train(st, cut, r, incumbent or st.parent, done=[], fed=None, history=[], training=None,
        lint=[], reserved=frozenset(), analysed=frozenset(), disclosed=frozenset(), generated=None)


def test_controller_proposal_occupies_one_ordinary_unit_without_role_calls_and_resumes(tmp_path, monkeypatch):
    st, cut, current, pid = setup(tmp_path)
    before = deepcopy(budgets.caps(p.MAIN_V8))
    monkeypatch.setattr(step, '_current', lambda *_: current)
    monkeypatch.setattr(step.engineer, 'run_train', lambda *_: pytest.fail('No parallel engineer proposal'))
    first = engineer_round(st, cut, 1)
    candidate = step._package(st, first['candidate_sha256'])
    assert len(edits(st.parent, candidate)) == 1 and edits(st.parent, candidate)[0].kind == 'deletion'
    assert set(st.parent.order) - set(candidate.order) == {pid}
    assert candidate.parent_sha256 == st.parent.sha256 and candidate.step == st.name
    validate(candidate, st.parent)
    sealed = p.verified(first['engineer'], 'engineer')
    assert sealed['source'] == 'card_hygiene_controller' and sealed['hygiene_mode'] == 'measured_candidates'
    assert sealed['calls'] == 0 and sealed['proposals'] == sealed['audits'] == []
    assert len(sealed['changes']) == 1 and sealed['changes'][0]['kind'] == 'deletion'
    assert sealed['changes'][0]['id'] is None and sealed['changes'][0]['target'] == pid
    assert first['hygiene']['confirmation_candidates'] == 1
    monkeypatch.setattr(step, '_current', lambda *_: pytest.fail('Completed unit must resume without selecting again'))
    assert engineer_round(st, cut, 1) == first
    assert st.invocations == ['engineer-r1'] and budgets.caps(p.MAIN_V8) == before


def test_rejected_deletion_can_use_next_ordinary_round_without_new_retry_rules(tmp_path, monkeypatch):
    st, cut, current, pid = setup(tmp_path)
    monkeypatch.setattr(step, '_current', lambda *_: current)
    first, second = engineer_round(st, cut, 1), engineer_round(st, cut, 2)
    assert first['candidate_sha256'] == second['candidate_sha256']
    assert first['hygiene']['selected'] == second['hygiene']['selected'] == pid
    assert st.invocations == ['engineer-r1', 'engineer-r2']
    assert all(row['engineer']['calls'] == 0 for row in (first, second))


def test_hygiene_rebase_obeys_existing_step_edit_budget_instead_of_adding_a_candidate_slot(tmp_path):
    st, cut, current, _ = setup(tmp_path)
    additions = [procedure('fx-cap-' + str(n), ('applies', 'before_call'), origin='searchqa') for n in range(p.MAX_CHANGES)]
    incumbent = with_(st.parent, step=st.name, add=additions)
    proposed, record = v222_runtime.hygiene_candidate(st, cut, 2, incumbent, current)
    assert proposed is None and record['selected'] is None
    assert record['reason'] == 'existing_step_edit_budget' and record['confirmation_candidates'] == 0
    assert len(edits(st.parent, incumbent)) == p.MAX_CHANGES == 3
    assert v222_limits.maximum_candidates(p, 'searchqa', 'confirm') == 30
    assert v222_limits.maximum_candidates(p, 'searchqa', 'accept') == 6


def test_hygiene_uses_only_current_registered_run_items_not_other_available_practice(tmp_path):
    st, cut, current, pid = setup(tmp_path)
    outside = [trajectory(st.parent, [pid], 'searchqa/confirmation-%d' % i) for i in range(10)]
    proposed, record = v222_runtime.hygiene_candidate(st, cut, 1, st.parent, current[:2] + outside)
    assert proposed is None
    assert next(row for row in record['segments'] if row['segment'] == pid)['touched'] == 2


def test_whole_card_runtime_has_no_deletion_proposal_even_with_stale_parent_notes(tmp_path):
    st, cut, current, _ = setup(tmp_path)
    st.setting.extra['v222_fallbacks'] = {'G': ['searchqa']}
    proposed, record = v222_runtime.hygiene_candidate(st, cut, 1, st.parent, current)
    assert proposed is None and record['reason'] == 'whole_card_fallback'


def test_deleted_own_segment_remains_in_count_only_coverage_using_incumbent_identity():
    before = parent(); pid = own(before)[0]
    candidate = with_(before, step='G/s1-searchqa', remove=[pid])
    keys = ['a', 'b', 'c']
    record = v222_feedback.coverage(5, keys, {pid: keys}, candidate, incumbent=before)
    assert record['segments'][pid] == record['procedures'][pid]
    assert record['segments'][pid]['touched'] == 3 and v222_feedback.coverage_ok(record)


@pytest.mark.parametrize('stop_at', ['none', 'train', 'home-confirm', 'cross-confirm', 'accept'])
def test_deletion_runs_unchanged_train_confirmation_crossgate_and_acceptance_before_adoption(tmp_path, monkeypatch, stop_at):
    st, cut, current, pid = setup(tmp_path)
    monkeypatch.setattr(step, '_current', lambda *_: current)
    rounds = p.train_rounds
    monkeypatch.setattr(p, 'train_rounds', lambda configuration: 1 if p.is_v222(configuration) else rounds(configuration))
    events = []
    def train(st, cut, r, incumbent, candidate, generated, **kwargs):
        assert set(incumbent.order) - set(candidate.order) == {pid}
        events.append(('train', r))
        return {**training(fixed=0 if stop_at == 'train' else 3), 'candidate_sha256': candidate.sha256,
                'incumbent_sha256': incumbent.sha256}
    monkeypatch.setattr(step, '_train_eval', train)
    def cross(st, attempt, *, unit, phase, parent, candidate):
        events.append(('cross-' + phase, 1))
        passed = stop_at != 'cross-confirm'
        return (candidate if passed else None), {'passed': passed,
            'parent_sha256': parent.sha256, 'proposed_sha256': candidate.sha256,
            'candidate_sha256': candidate.sha256 if passed else None, 'benches': {}}
    monkeypatch.setattr(v222_runtime, 'cross_gate', cross)
    def confirm(st, cut, r, incumbent, candidate, **kwargs):
        events.append(('confirm', r))
        result = confirmation(fixed=0 if stop_at == 'home-confirm' else 3)
        return v222_runtime.confirmation(st, st.root, unit='confirm-r%d' % r,
            parent=incumbent, candidate=candidate, result=result)
    monkeypatch.setattr(step, '_confirm_eval', confirm)
    def accept(st, cut, r, incumbent, candidate, generated):
        events.append(('accept', r))
        counted = p.GAIN_MIN_ITEMS if stop_at != 'accept' else 0
        from skillopt.execskill import v221_rule
        rule = v221_rule.counts(touched=3, fixed=counted, broken=0, batch=3)
        return {'decision': rule['decision'], 'reason': None if counted else 'gain_and_no_harm', 'rule': rule}
    monkeypatch.setattr(v221_learning, 'immediate_acceptance', accept)
    final, history, _ = step._train(st, cut, None)
    accepted = stop_at == 'none'
    assert history[0]['adopted'] is accepted
    assert (pid not in final.order) is accepted
    assert events[0] == ('train', 1)
    expected = [('train', 1)]
    if stop_at != 'train': expected += [('confirm', 1), ('cross-confirmation', 1)]
    if stop_at in ('none', 'accept'): expected += [('accept', 1)]
    assert events == expected
    assert st.done('engineer-r1')['engineer']['calls'] == 0
    assert history[0]['proposals'][0]['kind'] == 'deletion'
