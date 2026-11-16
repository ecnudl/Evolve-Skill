"""Authored v2.21 review regressions; no model, environment or benchmark data."""
from dataclasses import replace

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import audit, profiles as p, step, units, v221_learning, v221_rule
from skillopt.execskill.package import save, with_
from tests.test_execskill_v221_learning import FixtureStep, packages
from tests.test_execskill_v221_rule import finding
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


def accepted(st, round_, incumbent, candidate, *, fixed=10, broken=1):
    contrast = replace(candidate, parent_sha256=incumbent.sha256)
    selection = p.record('immediate-acceptance-selection', st.evidence, {
        'incumbent_sha256': incumbent.sha256, 'candidate_sha256': candidate.sha256,
        'contrast_candidate_sha256': contrast.sha256})
    write_json(st.root / ('accept-selection-r%d.json' % round_), selection)
    result = {'decision': 'accept', 'reason': None, 'decision_sha256': 'own-decision-%d' % round_,
              'candidate_sha256': contrast.sha256, 'incumbent_sha256': incumbent.sha256,
              'rule': v221_rule.counts(touched=fixed + broken, fixed=fixed, broken=broken,
                                       batch=fixed + broken)}
    st.results['accept-r%d' % round_] = result
    return {'round': round_, 'adopted': True, 'candidate_sha256': candidate.sha256}, result


@pytest.mark.parametrize('prior', ['none', 'Q', 'P'])
def test_final_audit_pq_cannot_freeze_q_under_pq_acceptance(tmp_path, monkeypatch, prior):
    """Confirmation: Q fixes ten/P breaks one; acceptance: P fixes ten/Q breaks one."""
    parent, candidates = packages(tmp_path)
    both = candidates[1]
    proc_p, proc_q = both.procedures
    q_only = with_(parent, step=both.step, add=(proc_q,))
    save(tmp_path, q_only)
    st = FixtureStep(tmp_path, parent)
    st.name = 'G/s1-searchqa'
    previous = {'none': parent, 'Q': q_only, 'P': candidates[0]}[prior]
    history = []
    if prior != 'none':
        row, _ = accepted(st, 1, parent, previous, fixed=6, broken=0)
        history.append(row)
    row, pq_decision = accepted(st, len(history) + 1, previous, both)
    history.append(row)
    assert pq_decision['rule']['decision'] == 'accept'
    own = {proc_p.id: {'fixed': 0, 'broken': 1, 'touched': 1},
           proc_q.id: {'fixed': 10, 'broken': 0, 'touched': 10}}
    assert v221_rule.counts(touched=11, fixed=10, broken=1, batch=11)['decision'] == 'accept'
    monkeypatch.setattr(step, '_train', lambda *a: (both, history, both))
    monkeypatch.setattr(units, 'audit_judges', lambda *a: {})
    monkeypatch.setattr(audit, 'run_audit', lambda *a, **kw:
        {'confirmed': [{**finding(), 'procedure': proc_p.id}], 'tokens': {}})
    monkeypatch.setattr(v221_learning, 'audit_confirmation', lambda *a, **kw: own)
    checks = []
    monkeypatch.setattr(step, '_selftest', lambda st, unit, candidate, generated:
        checks.append(candidate.sha256) or {'blocked': False})
    monkeypatch.setattr(step, '_accept', lambda *a, **kw: pytest.fail('rollback adds no acceptance read'))
    candidate, outcome, training = step._trained(st, {}, None)
    final_audit = training['audit_final']
    assert final_audit['removed'] == [proc_p.id]
    assert final_audit['candidate_sha256'] == both.sha256
    assert final_audit['final_sha256'] != both.sha256
    binding = training['acceptance_binding']
    assert binding['audit_result_sha256'] == final_audit['final_sha256']
    assert training['final_sha256'] == candidate.sha256
    if prior == 'Q':
        assert candidate.sha256 == q_only.sha256
        assert outcome['decision'] == 'accept' and outcome['decision_sha256'] == 'own-decision-1'
        assert outcome['decision_sha256'] != pq_decision['decision_sha256']
        assert binding['action'] == 'rollback_to_accepted_package' and binding['selected_round'] == 1
        assert checks == [q_only.sha256] and outcome['accepted_rounds'] == [1]
    else:
        assert candidate.sha256 == parent.sha256 and outcome['decision'] == 'not_run'
        assert outcome['decision_sha256'] is None
        assert binding['action'] == 'rollback_to_step_parent' and binding['selected_round'] is None
        assert outcome['reason'] == 'audit_rollback_to_step_parent' and not checks


def test_final_acceptance_rejects_a_decision_bound_to_another_package(tmp_path):
    parent, candidates = packages(tmp_path)
    st = FixtureStep(tmp_path, parent)
    row, decision = accepted(st, 1, parent, candidates[0])
    decision['candidate_sha256'] = candidates[1].sha256
    with pytest.raises(ValueError, match='own immediate acceptance decision'):
        step._v221_final_acceptance(st, candidates[0], [row], {'removed': []})


def test_final_acceptance_preserves_exact_unchanged_package_and_its_decision(tmp_path):
    parent, candidates = packages(tmp_path)
    st = FixtureStep(tmp_path, parent)
    row, decision = accepted(st, 1, parent, candidates[0])
    chosen, outcome, binding = step._v221_final_acceptance(st, candidates[0], [row], {'removed': []})
    assert chosen.sha256 == candidates[0].sha256 and outcome == decision
    assert binding['action'] == 'unchanged' and binding['selected_round'] == 1

