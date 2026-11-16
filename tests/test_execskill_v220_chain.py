"""The real chain and step entry points compose two imports, then one consented QA read."""
from dataclasses import replace
import functools
from pathlib import Path

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (chain, evaluation, manifest, profiles as p, step,
                               v218_lock, v220_import as imp)
from skillopt.execskill.package import empty
from tests.execskill_v220_fakes import pinned_source
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_chain import setting as base_setting

CONSENT = {'test_evaluation': True, 'sheet_test_qualification': False, 'multi_arm_arms': ['F', 'C'],
           'by': 'owner', 'date': '2026-11-02', 'note': 'Authored owner-requested post-hoc read fixture.'}


def setting(root, chain_id, *, consent=True):
    source = pinned_source(root / 'source')
    st = base_setting(root, chain_=chain_id, consent=False)
    st.extra.update(configuration=p.SEARCHQA_HP_V6,
                    **{imp.PIN_KEY: source}, test_read_terms={chain_id: {'searchqa': '1000'}})
    if consent:
        write_json(st.shared / 'consent.json', CONSENT)
    return st


def forbid_non_read_work(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('The SearchQA-only fixed chain reached a role, qualification, or environment service')
    monkeypatch.setattr(manifest, 'services_of', forbidden)
    monkeypatch.setattr(evaluation, 'prepare_test_qualification', forbidden)
    monkeypatch.setattr(v218_lock, 'environment', forbidden)
    for name in ('_slices', '_run', '_diagnose', '_generate', '_trained', '_accept', '_freeze'):
        monkeypatch.setattr(step, name, forbidden)
    for name in ('solver_endpoint', 'role_endpoint', 'audit_judges'):
        monkeypatch.setattr(step.units, name, forbidden)
    return forbidden


def launch_into(events):
    def launch(st, spec):
        events.append(('read', spec['bench'], spec['package_sha256']))
        assert spec['bench'] == 'searchqa'
        write_json(Path(spec['unit_root']) / 'unit.json', p.record('evaluation', st.evidence,
            {'run': st.run, 'chain': spec['chain'], 'bench': spec['bench'],
             'packages': {'F': spec['package_sha256']}}))
        return chain.EXIT_COMPLETE
    return launch


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_chain_runs_both_real_imports_then_one_searchqa_read_without_environment_or_roles(tmp_path, monkeypatch, chain_id):
    st = setting(tmp_path, chain_id)
    forbid_non_read_work(monkeypatch)
    events = []
    original = step.run_step
    def import_step(*args, **kwargs):
        assert kwargs['services'] is None
        events.append(('import', args[2]))
        return original(*args, **kwargs)
    monkeypatch.setattr(step, 'run_step', import_step)
    def first(st, selected, **kwargs):
        assert evaluation.consent(st.shared, p.SEARCHQA_HP_V6) == CONSENT
        events.append(('first', selected))
    monkeypatch.setattr(chain, 'first_call', first)
    result = chain.run(st, chain_id, learn=functools.partial(step.learn, services=None), launch=launch_into(events))
    assert result == {'status': 'complete'}
    assert events[:3] == [('first', chain_id), ('import', 'main-v6-final'), ('import', 'searchqa-candidate')]
    assert len(events) == 4 and events[3][:2] == ('read', 'searchqa')
    root = st.root / chain_id
    run = p.verified(read_json(root / 'chain.json'), 'chain')
    assert run['order'] == list(imp.STEPS) and run['configuration'] == p.SEARCHQA_HP_V6
    read = p.verified(read_json(root / 'test-read.json'), 'test-read')
    complete = p.verified(read_json(root / 'chain-complete.json'), 'chain-complete')
    assert read['arms'] == ['F', 'C'] and read['learning'] == 'import'
    assert read['evidence_kind'] == 'post_hoc_selected_upper_bound'
    assert read['imported'] == list(imp.STEPS) and 'blank_arm' not in read
    assert read['status'] == 'read' and read['gate']['units'] == ['searchqa']
    assert read['gate']['cost_check'] == 'not_applicable_no_learning_run'
    expected = imp.final_package(chain_id, st.evidence, st.extra[imp.PIN_KEY])
    assert read['package_sha256'] == complete['package_sha256'] == expected.sha256
    assert len(complete['steps']) == 2
    assert not (tmp_path / 'slots' / chain.HEAVY_LOCK).exists()
    assert set(path.name for path in (root / 'test').iterdir()) == {'searchqa'}
    assert chain.run(st, chain_id, learn=functools.partial(step.learn, services=None), launch=launch_into(events)) == {'status': 'complete'}
    assert len(events) == 4


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_missing_consent_pauses_before_first_reply_or_import(tmp_path, monkeypatch, chain_id):
    st = setting(tmp_path, chain_id, consent=False)
    forbidden = forbid_non_read_work(monkeypatch)
    monkeypatch.setattr(chain, 'first_call', forbidden)
    result = chain.run(st, chain_id, learn=forbidden, launch=forbidden)
    assert result['status'] == 'paused' and result['kind'] == 'consent_missing'
    root = st.root / chain_id
    assert not (root / 's1-main-v6-final').exists() and not (root / 'test').exists()
    wait = p.verified(read_json(root / chain.READ_WAITING), 'read-waiting')
    assert wait['read_units'] == 1 and wait['read_attempts'] == wait['units_complete'] == 0


@pytest.mark.parametrize('part', ['missing_candidate', 'order', 'source'])
def test_chain_refuses_wrong_composition_before_any_read_launch(tmp_path, monkeypatch, part):
    st = setting(tmp_path, 'G')
    forbid_non_read_work(monkeypatch)
    monkeypatch.setattr(chain, 'first_call', lambda *args, **kwargs: None)
    def learn(st, root, selected, k, bench, parent):
        package, record = step.learn(st, root, selected, k, bench, parent, services=None)
        if k == 2:
            procedures = list(package.procedures)
            if part == 'missing_candidate':
                procedures.pop()
            elif part == 'order':
                procedures[-2:] = reversed(procedures[-2:])
            else:
                procedures[-1] = replace(procedures[-1], source=procedures[-1].source + '\n# changed\n')
            package = replace(package, procedures=tuple(procedures))
        return package, record
    with pytest.raises(ValueError, match='exactly main-v6 order'):
        chain.run(st, 'G', learn=learn, launch=lambda *args: pytest.fail('Wrong package reached read launch'))
    assert not (st.root / 'G/test').exists()
    assert not (st.root / 'G/chain-complete.json').exists()


@pytest.mark.parametrize('chain_id', ['G', 'D'])
@pytest.mark.parametrize('k', [1, 2])
def test_step_child_confirms_route_and_constructs_no_role_clients(tmp_path, monkeypatch, chain_id, k):
    st = setting(tmp_path, chain_id)
    forbid_non_read_work(monkeypatch)
    if k == 2:
        step.run_step(st, chain_id, imp.STEPS[0], 1,
                      empty(step=chain_id + '/s0', evidence=st.evidence), services=None)
    seen = []
    monkeypatch.setattr(step, 'confirmation', lambda *args, **kwargs: seen.append(kwargs))
    monkeypatch.setattr(manifest, 'setting_of', lambda *args, **kwargs: st)
    spec = tmp_path / 'spec.json'
    write_json(spec, {'chain': chain_id, 'bench': imp.STEPS[k-1], 'k': k})
    result = step.run_unit_spec({'configuration': p.SEARCHQA_HP_V6, 'root': str(st.root),
                                p.RECORD_HASH: 'authored'}, spec=spec)
    assert result == chain.EXIT_COMPLETE and seen == [{'configuration': p.SEARCHQA_HP_V6}]
    record = p.verified(read_json(st.root / chain_id / ('s%d-%s' % (k, imp.STEPS[k-1])) / 'step.json'), 'step')
    assert record['learning'] == 'import' and record['units'] == {}


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_manifest_runner_binds_none_services_to_real_step_learning(tmp_path, monkeypatch, chain_id):
    st = setting(tmp_path, chain_id)
    forbid_non_read_work(monkeypatch)
    monkeypatch.setattr(manifest, 'setting_of', lambda *args, **kwargs: st)
    seen = []
    def run(actual, selected, *, learn):
        assert actual is st and selected == chain_id
        assert learn.func is step.learn and learn.keywords == {'services': None}
        seen.append(True)
        return {'status': 'complete'}
    monkeypatch.setattr(chain, 'run', run)
    assert chain.run_manifest({'configuration': p.SEARCHQA_HP_V6, 'evidence': 'engineering_fixture'},
                              chain=chain_id, path=tmp_path / 'manifest.json') == {'status': 'complete'}
    assert seen == [True]
