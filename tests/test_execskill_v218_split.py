"""Authored split decisions and request reuse; no models, environments or source data."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import confirm, engineer, profiles as p, step, v218_split as split
from skillopt.execskill.package import empty, with_
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import procedure
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


def packages():
    parent = empty(step='G/s2-officeqa', evidence='engineering_fixture')
    good, bad = [procedure('fx-v218-' + name, ('applies', 'before_call'), origin='zebralogic')
                 for name in ('helpful', 'harmful')]
    return parent, with_(parent, step='G/s3-zebralogic', add=(good, bad))


def signature(text):
    return {'request_sha256': digest(text), 'post_call': [], 'faults': []}


def cell(unit, arm, key, token, run=0):
    return p.record('cell-v2-3', 'engineering_fixture', {
        'cell': {'id': digest([unit, arm, key, run]), 'unit': unit, 'task_id': key, 'arm': arm, 'run': run},
        'stop': None, 'faults': [], 'judge': {'v2': {'token': token}},
        'final': {'outcome': token, 'kind': 'score', 'remedy': None}, 'sends': []})


class FixtureStep:
    def __init__(self, root, parent):
        self.setting = SimpleNamespace(extra={'configuration': p.MAIN_V6})
        self.parent, self.chain_root, self.k, self.bench = parent, root, 3, 'zebralogic'
        self.smoke = None
        self.results, self.attempts = {}, {}

    def label(self, name):
        return 'G/s3-' + self.bench + '/' + name

    def runtime(self):
        return {}

    def solver(self, kind, attempt):
        assert kind in ('selftest', 'confirm')
        return None

    def done(self, unit):
        return self.results.get(unit)

    def unit(self, name, work):
        if name in self.results:
            return self.results[name]
        self.attempts[name] = self.attempts.get(name, 0) + 1
        attempt = self.chain_root / ('s3-' + self.bench) / name / ('attempt-%d' % self.attempts[name])
        attempt.mkdir(parents=True)
        result = work(attempt)
        self.results[name] = result
        return result


def setup_evaluation(tmp_path, monkeypatch, *, missing_parent=False, bench='zebralogic'):
    parent, full = packages()
    st = FixtureStep(tmp_path, parent)
    st.bench = bench
    cut = {kind: [{'task_id': kind + '-' + item, 'public': {'question': item}, 'private': {}}
                  for item in ('help', 'hurt', 'joint', 'idle')] for kind in ('run', 'confirm')}
    dispatched = []

    def request(package, key):
        item = key.rsplit('-', 1)[-1]
        enabled = [pid for pid in package.order if
                   ('helpful' in pid and item in ('help', 'joint', 'idle')) or
                   ('harmful' in pid and item in ('hurt', 'joint'))]
        active = [] if item == 'idle' else enabled
        if missing_parent and item == 'joint' and len(active) == 2:
            active = []
        return enabled, signature([key, active])

    def routes(st, package, views, publics):
        return {key: SimpleNamespace(enabled=request(package, key)[0], faults=[]) for key, _ in views}

    def signatures(st, candidate, incumbent, publics, views, *, note_coverage=None, **kwargs):
        if note_coverage is not None:
            note_coverage.update({key: {'S': {}, "S'": {}} for key, _ in views})
        return {key: {'S': request(incumbent, key)[1], "S'": request(candidate, key)[1]} for key, _ in views}

    def token(package, key):
        item = key.rsplit('-', 1)[-1]
        if item == 'help':
            return 'pass' if any('helpful' in pid for pid in package.order) else 'fail'
        if item == 'hurt':
            return 'fail' if any('harmful' in pid for pid in package.order) else 'pass'
        if item == 'joint':
            if 'confirm-' in key:
                return 'fail' if any('harmful' in pid for pid in package.order) else 'pass'
            return 'pass' if any('helpful' in pid for pid in package.order) else 'fail'
        return 'pass'

    def dispatch(st, attempt, endpoint, unit, jobs, **kwargs):
        result = []
        for arm, chosen, key, run, task in jobs:
            assert run == 0
            found = cell(unit, arm, key, token(chosen.package, key))
            write_json(attempt / 'cells' / (found['cell']['id'] + '.json'), found)
            dispatched.append((unit, arm, key))
            result.append(found)
        return result

    monkeypatch.setattr(step, '_routes', routes)
    monkeypatch.setattr(step, '_pair_signatures', signatures)
    monkeypatch.setattr(step.solver, 'routing_view', lambda bench, public, **kwargs: public)
    monkeypatch.setattr(step, '_cells', dispatch)
    monkeypatch.setattr(step, '_feedback', lambda st, cut, unit, verdict, *args, **kwargs: {
        'adopted': verdict['adopted'], 'reason': verdict['reason']})
    sources = []
    for kind in ('run', 'confirm'):
        unit = st.label(('train' if kind == 'run' else 'confirm') + '-r1')
        selected = cut[kind]
        keys = [st.bench + '/' + item['task_id'] for item in selected]
        views = [(key, {}) for key in keys]
        sigs = signatures(st, full, parent, {}, views)
        identical = [key for key in keys if sigs[key]['S'] == sigs[key]["S'"]]
        cells = {(arm, key): [cell(unit, arm, key, token(package, key))]
                 for key in keys if key not in identical for arm, package in (('S', parent), ("S'", full))}
        source = {'candidate_sha256': full.sha256, 'request_signatures': sigs, 'cells': len(cells),
                  'incumbent_cells': {key: rows for (arm, key), rows in cells.items() if arm == 'S'},
                  'candidate_cells': {key: rows for (arm, key), rows in cells.items() if arm == "S'"}}
        if kind == 'run':
            verdict = step.train_verdict(cells, keys, [], set(full.order), predicate_faults=0, routed=len(keys),
                                        sign=False, configuration=p.MAIN_V6, identical=identical)
            source.update(adopted=verdict['adopted'], verdict=verdict, feedback={})
        else:
            source.update(confirm=confirm.verdict(cells, keys, identical=identical, items=len(keys)),
                          slice_ids=[item['task_id'] for item in selected])
        sources.append(source)
    return st, cut, full, sources, dispatched


def test_whole_fails_helpful_split_wins_with_all_reuse_rules_and_restart(tmp_path, monkeypatch):
    st, cut, full, (training, confirmation), dispatched = setup_evaluation(tmp_path, monkeypatch)
    assert training['adopted'] and not confirmation['confirm']['passed']
    engineered = {'engineer': {'changes': [{'id': pid, 'kind': 'new', 'target': None} for pid in full.order]}}
    selected, result = split.run(st, cut, 1, st.parent, full, engineered, training, confirmation, None, current=[])
    assert selected.order == (full.order[0],) and result['adopted']
    assert result['split_winner'] == full.order[0]
    assert result['split'][0]['confirmation'] == {'fixed': 1, 'broken': 0, 'net': 1}
    assert result['split'][1]['confirmation'] is None
    evaluated = st.done('train-r1-split-p1')
    rules = {entry['rule'] for row in evaluated['cell_rules'].values() for entry in row.values()}
    assert rules == {'identical_to_incumbent', 'identical_to_candidate', 'reused_incumbent', 'dispatched'}
    assert len(dispatched) == 3  # one new joint candidate per performed sub-unit
    before = list(dispatched)
    assert split.run(st, cut, 1, st.parent, full, engineered, training, confirmation, None, current=[])[0] == selected
    assert dispatched == before


def test_actual_training_loop_promotes_split_and_records_proposal_fates(tmp_path, monkeypatch):
    st, cut, full, (training, confirmation), dispatched = setup_evaluation(tmp_path, monkeypatch)
    changes = [{'id': pid, 'kind': 'new', 'target': None, 'summary': 'Authored procedure', 'n': i,
                'attempts': [], 'survived': True} for i, pid in enumerate(full.order)]
    engineered = {'candidate_sha256': full.sha256,
                  'engineer': {'changes': changes, 'analysis': {'items': []}, 'disclosed': [], 'lint': [], 'dropped': []}}
    monkeypatch.setattr(step, '_engineer_train', lambda *args, **kwargs: engineered)
    monkeypatch.setattr(step, '_train_eval', lambda *args, **kwargs: training)
    monkeypatch.setattr(step, '_confirm_eval', lambda *args, **kwargs: confirmation)
    monkeypatch.setattr(step, '_current', lambda *args, **kwargs: [])
    monkeypatch.setattr(step, '_package', lambda st, sha: full)
    monkeypatch.setattr(p, 'train_rounds', lambda configuration: 1)
    selected, rows, _ = step._train(st, cut, None)
    assert selected.order == (full.order[0],) and rows[0]['adopted']
    assert rows[0]['proposals'][0]['fate'] == 'adopted_by_split'
    assert rows[0]['proposals'][1]['fate'].startswith('not_adopted:split:')
    assert rows[0]['incumbent_sha256'] == selected.sha256
    assert split.counts_ok(rows[0]['split'])


def test_split_mid_unit_restart_uses_finished_cells(tmp_path, monkeypatch):
    st, cut, full, (training, _), dispatched = setup_evaluation(tmp_path, monkeypatch, missing_parent=True)
    sub = split.subcandidate(st.parent, st.parent, full, full.procedures[0], [])
    real = step._cells

    def interrupted(st, attempt, endpoint, unit, jobs, **kwargs):
        real(st, attempt, endpoint, unit, jobs[:1], **kwargs)
        raise RuntimeError('authored interruption')

    monkeypatch.setattr(step, '_cells', interrupted)
    with pytest.raises(RuntimeError, match='authored interruption'):
        split.evaluate(st, cut, 1, 1, st.parent, sub, full, training, None, current=[])
    first = dispatched[0]
    monkeypatch.setattr(step, '_cells', real)
    result = split.evaluate(st, cut, 1, 1, st.parent, sub, full, training, None, current=[])
    assert result['adopted']
    assert dispatched.count(first) == 1 and len(dispatched) == 2
    assert any(entry['rule'] == 'resumed' for row in result['cell_rules'].values() for entry in row.values())


@pytest.mark.parametrize('bench', ['officeqa', 'spreadsheetbench'])
def test_generated_training_slice_and_parent_run_zero_are_used_once(tmp_path, monkeypatch, bench):
    st, cut, full, (training, _), dispatched = setup_evaluation(tmp_path, monkeypatch, bench=bench)
    sub = split.subcandidate(st.parent, st.parent, full, full.procedures[0], [])
    key = bench + '/run-help'
    training['candidate_cells'][key].append(cell(st.label('train-r1'), "S'", key, 'fail', run=1))
    training['incumbent_cells'][key].append(cell(st.label('train-r1'), 'S', key, 'pass', run=1))
    generated_item = p.record('generated-item', 'engineering_fixture', {
        'id': 'generated-joint', 'benchmark': bench, 'public': {'question': 'joint'}, 'private': {}})
    generated = {'generator': {'status': 'admitted'}, 'g_self': [generated_item]}
    result = split.evaluate(st, cut, 1, 1, st.parent, sub, full, training, generated, current=[])
    assert result['adopted'] and result['verdict']['generated'] == 1
    assert result['candidate_cells'][key][0]['cell']['run'] == 0
    assert result['candidate_cells'][key][0]['judge']['v2']['token'] == 'pass'
    assert [(arm, item) for _, arm, item in dispatched if item == 'generated-joint'] == [
        ('S', 'generated-joint'), ("S'", 'generated-joint')]
    assert result['verdict']['fixed'] == sorted([key, bench + '/run-joint', 'generated-joint'])


def test_faulted_full_candidate_cell_cannot_be_reused(tmp_path, monkeypatch):
    st, cut, full, (training, _), dispatched = setup_evaluation(tmp_path, monkeypatch)
    sub = split.subcandidate(st.parent, st.parent, full, full.procedures[0], [])
    key = 'zebralogic/run-help'
    original = training['candidate_cells'][key][0]
    fields = {k: v for k, v in original.items() if k not in ('version', 'evidence', p.RECORD_HASH)}
    fields['faults'] = [{'procedure': full.order[0], 'kind': 'output'}]
    training['candidate_cells'][key][0] = p.record('cell-v2-3', 'engineering_fixture', fields)
    result = split.evaluate(st, cut, 1, 1, st.parent, sub, full, training, None, current=[])
    assert result['cell_rules'][key]["S'"]['rule'] == 'dispatched'
    assert any(arm == "S'" and item == key for _, arm, item in dispatched)
    assert result['candidate_cells'][key][0]['faults'] == []


@pytest.mark.parametrize('reason', ['one_change', 'training_failed', 'confirmation_passed', 'older'])
def test_no_split_outside_registered_trigger(tmp_path, reason):
    parent, full = packages()
    st = FixtureStep(tmp_path, parent)
    if reason == 'one_change':
        full = with_(parent, step=full.step, add=full.procedures[:1])
    if reason == 'older':
        st.setting.extra['configuration'] = p.MAIN_V5
    training = {'adopted': reason != 'training_failed', 'verdict': {'reason': None}, 'feedback': {}}
    confirmation = {'confirm': {'passed': reason == 'confirmation_passed', 'reason': 'gain:fixed_over_broken'}}
    selected, result = split.run(st, {}, 1, parent, full, {}, training, confirmation, None, current=[],
        evaluator=lambda *args, **kwargs: pytest.fail('No split should run'))
    assert selected == full and 'split' not in result


def test_revised_procedure_is_exact_and_invalid_subcandidate_is_skipped(tmp_path):
    base, full = packages()
    old = full.procedures[0]
    incumbent = with_(base, step=full.step, add=(old,))
    revision = replace(old, id='fx-v218-revision', lineage={'parent': old.sha256, 'revises': old.id, 'engineer_call': None})
    raw = with_(incumbent, step=full.step, revise=(revision,), add=(full.procedures[1],))
    rebased = engineer.rebase(raw, base, incumbent, step=full.step)
    procedure_new = rebased.get(revision.id)
    sub = split.subcandidate(base, incumbent, rebased, procedure_new,
                             [{'id': revision.id, 'kind': 'revision', 'target': old.id}])
    assert sub.order == (revision.id,) and sub.procedures[0].to_json() == procedure_new.to_json()
    assert sub.parent_sha256 == base.sha256
    st = FixtureStep(tmp_path, base)
    invalid = {'engineer': {'changes': [{'id': full.order[0], 'kind': 'revision', 'target': 'fx-missing'}]}}
    training = {'adopted': True, 'verdict': {'reason': None}, 'feedback': {}}
    confirmation = {'confirm': {'passed': False, 'reason': 'gain:fixed_over_broken'}}
    no_gain = {'adopted': False, 'verdict': {'adopted': False, 'reason': 'gain:net', 'fixed': [], 'broken': [], 'net': '0/1'},
               'feedback': {}}
    _, result = split.run(st, {}, 1, base, full, invalid, training, confirmation, None,
                          current=[], evaluator=lambda *args, **kwargs: no_gain)
    assert result['split'][0]['reason'] == 'split_invalid'


def test_counts_boundary_and_registered_ties():
    rows = [{'procedure': 'fx-v218-%d' % i, 'training': {'fixed': 2, 'broken': 0, 'net': '2/1'},
             'confirmation': {'fixed': 1, 'broken': 0, 'net': 1}, 'passed': True, 'reason': None} for i in range(3)]
    assert split.counts_ok(rows) and split.winner(rows) == 0
    rows[1]['training']['net'] = '3/1'
    assert split.winner(rows) == 1
    rows[2]['confirmation'].update(fixed=2, net=2)
    assert split.winner(rows) == 2
    injected = deepcopy(rows)
    injected[0]['confirmation']['question'] = 'Never engineer-visible'
    assert not split.counts_ok(injected)
    line = {'round': 1, 'candidate': True, 'adopted': True, 'items': 4, 'generated': 0, 'fixed': 2,
            'broken': 0, 'net': '2/1', 'p_sign': 0.25, 'reason': None, 'proposals': [], 'split': rows}
    assert engineer._history_line(line, 2, v218=True)
    assert not engineer._history_line(line, 2)
    line['split'] = injected
    assert not engineer._history_line(line, 2, v218=True)


def test_structural_smoke_and_unit_names(tmp_path):
    result = split.structural_smoke(tmp_path)
    assert result['calls'] == 0 and result['adopted_by_split'] == 'fx-v218-helpful'
    assert 'train-r6-split-p3' in step.training_units(p.MAIN_V6)
    assert not any('split' in unit for unit in step.training_units(p.MAIN_V5))
