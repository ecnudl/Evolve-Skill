"""Split retries isolate registered cross-gate cells in their shared attempt store."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import profiles as p, step, trajectories, v221_split
from tests.test_execskill_v221_learning import FixtureStep, packages
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


def attempted_split(root, unit, configuration):
    parent, candidates = packages(root)
    st = FixtureStep(root, parent); st.setting.extra['configuration'] = configuration
    location = st.root / unit
    first = location / 'attempt-1'; (location / 'attempt-2').mkdir(parents=True)
    binding = {'configuration': configuration, 'incumbent_sha256': parent.sha256,
               'candidate_sha256': candidates[0].sha256, 'items': ['home-item']}
    home = p.record('cell', st.evidence, {'cell': {
        'id': step.cell_id(st.label(unit), 'S', 'home-item', 0), 'unit': st.label(unit),
        'benchmark': st.bench, 'task_id': 'home-item', 'arm': 'S', 'run': 0},
        'stop': None, 'faults': [], 'final': {'outcome': 'pass', 'kind': 'score'},
        'judge': {'v2': {'token': 'pass'}}})
    cross_unit = st.label(unit) + '/cross-officeqa'
    cross = {'cell': {'id': step.cell_id(cross_unit, "S'", 'cross-item', 0),
        'unit': cross_unit, 'benchmark': 'officeqa', 'task_id': 'cross-item', 'arm': "S'", 'run': 0},
        'stop': {'kind': 'authored_partial'}, 'faults': [], 'final': None, 'judge': {}}
    pin = {'configuration': p.MAIN_V8, 'phase': 'confirmation', 'bench': 'officeqa',
        'parent_sha256': parent.sha256, 'candidate_sha256': candidates[0].sha256,
        'items': ['cross-item'], 'harm_registration_sha256': 'c' * 64}
    write_json(first / 'cells' / 'home.json', home)
    return st, location, first, binding, home, cross, pin


@pytest.mark.parametrize('unit', ['confirm-r1-split-p1', 'confirm-r1-split-merge'])
@pytest.mark.parametrize('configuration', [p.MAIN_V8, p.MAIN_V7])
def test_split_and_merged_retry_isolate_only_new_child_cross_cells(tmp_path, unit, configuration):
    st, root, first, binding, home, cross, pin = attempted_split(tmp_path, unit, configuration)
    write_json(first / 'cells' / 'cross.json', p.record('cell', st.evidence, cross))
    write_json(root / 'v222-cross-officeqa.json', pin)
    if configuration == p.MAIN_V7:
        with pytest.raises(ValueError, match='split attempt cell belongs'):
            v221_split._resume_cells(st, unit, binding)
    else:
        assert v221_split._resume_cells(st, unit, binding) == {('S', 'home-item'): home}


@pytest.mark.parametrize('problem', ['unrelated_unit', 'wrong_home', 'wrong_phase', 'wrong_parent',
                                    'wrong_candidate', 'unknown_item', 'missing_pin', 'wrong_cell_id'])
def test_child_retry_still_rejects_foreign_or_unbound_cells(tmp_path, problem):
    unit = 'confirm-r1-split-p1'
    st, root, first, binding, home, cross, pin = attempted_split(tmp_path, unit, p.MAIN_V8)
    original = deepcopy(binding)
    if problem == 'unrelated_unit': cross['cell']['unit'] = 'G/s9-searchqa/' + unit + '/cross-officeqa'
    elif problem == 'wrong_home': cross['cell']['benchmark'] = 'searchqa'
    elif problem == 'wrong_phase': pin['phase'] = 'acceptance'
    elif problem == 'wrong_parent': pin['parent_sha256'] = 'd' * 64
    elif problem == 'wrong_candidate': pin['candidate_sha256'] = 'd' * 64
    elif problem == 'unknown_item': pin['items'] = ['other-item']
    elif problem == 'wrong_cell_id': cross['cell']['id'] = 'd' * 64
    write_json(first / 'cells' / 'cross.json', p.record('cell', st.evidence, cross))
    if problem != 'missing_pin': write_json(root / 'v222-cross-officeqa.json', pin)
    with pytest.raises(ValueError, match='attempt cell'):
        v221_split._resume_cells(st, unit, binding)
    assert binding == original


@pytest.mark.parametrize('configuration,expected', [(p.MAIN_V7, 3), (p.MAIN_V8, 1)])
def test_cross_confirmation_situations_are_separate_from_home_audit_evidence(tmp_path, monkeypatch, configuration, expected):
    name = 'G/s1-searchqa/confirm-r1'
    rows = [{'unit': name, 'bench': 'searchqa', 'cell': 'own'},
            {'unit': name + '/cross-officeqa', 'bench': 'officeqa', 'cell': 'other'},
            {'unit': name + '/cross-alfworld', 'bench': 'alfworld', 'cell': 'episode'}]
    st = SimpleNamespace(setting=SimpleNamespace(extra={'configuration': configuration}),
        chain_root=tmp_path, k=1, bench='searchqa',
        label=lambda unit: 'G/s1-searchqa/' + unit)
    monkeypatch.setattr(trajectories, 'load_run', lambda root: list(rows))
    actual = step._unit_trajectories(st, 'confirm-r1')
    assert len(actual) == expected
    if configuration == p.MAIN_V8:
        assert actual == rows[:1]
