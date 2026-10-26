"""v2.9.1 next-round fault/format evidence and patience; authored offline cells."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from skillopt.execskill import engineer, profiles as p, rounds, step
from tests.test_execskill_v24_training import add_cell, feedback_fixture, trajectory


@pytest.fixture(params=['zebra-pc-v8', 'alfworld-v5'])
def configuration(request):
    return request.param


def feedback_case(tmp_path, configuration, *, count=5):
    st, cut, _ = feedback_fixture(tmp_path, configuration=configuration, count=count)
    if p.is_alfworld(configuration):
        st.bench = 'alfworld'
    cells, made = {}, {}
    for item in cut['run']:
        for arm in ('S', "S'"):
            trace = trajectory(item, arm, 'pass', note='Delivered public note. ' * 60)
            trace['bench'] = st.bench
            trace['task_id'] = rounds.key(st.bench, item['task_id'])
            trace['cell'] = arm + '/' + trace['task_id'] + '/0'
            trace['shell'] = {'faults': []}
            if st.bench == 'alfworld':
                trace['alfworld_steps'] = [{'notes': 'Actual ALF note. ' * 80}]
            add_cell(cells, made, trace)
    before, after = SimpleNamespace(order=(), narrowed={}), SimpleNamespace(order=('p-new',), narrowed={})
    routed = {key: {'incumbent': [], 'candidate': ['p-new']} for arm, key in cells}
    return st, cut, cells, made, before, after, routed


def emit(case):
    st, cut, cells, made, before, after, routed = case
    keys = sorted({key for arm, key in cells})
    own = step._run_keys(st, cut)
    verdict = step.train_verdict(cells, [key for key in keys if key in own], [key for key in keys if key not in own],
        {'p-new'}, predicate_faults=0, routed=len(keys), sign=False, configuration=p.configuration_of(st.setting))
    for rows in cells.values():
        for cell in rows:
            made[cell['cell']['id']]['judge'] = deepcopy(cell['judge'])
    return step._feedback(st, cut, 'train-r1', verdict, routed, before, after, cells, made), verdict


def valid_feedback(case, value):
    st, cut, cells, made, *_ = case
    references = step._references(st, cut, [], also=[row['task_id'] for row in value['unfixed_examples']])
    return engineer._training_ok(value, references, step._run_keys(st, cut), made, st.bench,
        v24=True, v25=st.bench == 'zebralogic', v28=True, v29=True, v291=True)


def test_fault_feedback_unions_cell_and_shell_faults_and_deduplicates_cells(tmp_path, configuration):
    case = feedback_case(tmp_path, configuration)
    st, cut, cells, made, *_ = case
    fault = {'procedure': 'p-new', 'hook': 'before_call', 'kind': 'crash:IndexError',
             'exc_type': 'IndexError', 'message': 'Public exception. ' * 30}
    keys = sorted(step._run_keys(st, cut))
    for key in keys[:2]:
        cell = cells[("S'", key)][0]
        cell['faults'] = [deepcopy(fault), deepcopy(fault)]
        made[cell['cell']['id']]['shell']['faults'] = [deepcopy(fault)]
    cell = cells[("S'", keys[2])][0]
    made[cell['cell']['id']]['shell']['faults'] = [deepcopy(fault)]
    cells[("S'", keys[3])][0]['faults'] = [{**fault, 'informational': True}]
    cells[("S'", keys[4])][0]['faults'] = [{**fault, 'procedure': 'inherited'}]
    value, verdict = emit(case)
    actual = value['procedures'][0]['faults']
    assert actual['cells'] == 3 and len(actual['signatures']) == 1
    signature = actual['signatures'][0]
    assert signature['cells'] == 3 and signature['message'] == fault['message'][:200]
    assert signature['example_task_id'] in keys[:3] and signature['exc_type'] == 'IndexError'
    assert valid_feedback(case, value)
    reversed_case = (st, {**cut, 'run': list(reversed(cut['run']))}, dict(reversed(list(cells.items()))),
                     dict(reversed(list(made.items()))), *case[4:])
    assert emit(reversed_case)[0] == value


def test_fault_top_three_counts_generated_cells_without_showing_nonrun_id(tmp_path, configuration):
    case = feedback_case(tmp_path, configuration)
    st, cut, cells, made, *_ = case
    own = step._run_keys(st, cut)
    for index, key in enumerate(sorted(own)):
        cells[("S'", key)][0]['faults'] = [{'procedure': 'p-new', 'hook': 'before_call',
            'kind': 'timeout-' + str(index), 'message': 'public diagnostic'}]
    foreign = deepcopy(cells[("S'", sorted(own)[0])][0])
    foreign['cell'].update(id='generated-cell', task_id='GENERATED-ID')
    foreign['faults'] = [{'procedure': 'p-new', 'hook': 'before_call', 'kind': 'timeout-0', 'message': 'public diagnostic'}]
    cells[("S'", 'GENERATED-ID')] = [foreign]
    parent = deepcopy(foreign)
    parent['cell'].update(id='generated-parent', arm='S')
    parent['faults'] = []
    cells[('S', 'GENERATED-ID')] = [parent]
    # Aggregate measurements may count generated cells; no generated trajectory is disclosed.
    details = step._procedure_fault_feedback('p-new', cells, made, own, 'authored')
    assert details['cells'] == 6 and len(details['signatures']) == 3
    assert details['signatures'][0]['cells'] == 2
    assert all(row['example_task_id'] in own for row in details['signatures'])


def test_format_feedback_is_recorded_bounded_run_only_and_uses_reply_tail(tmp_path, configuration):
    case = feedback_case(tmp_path, configuration)
    st, cut, cells, made, *_ = case
    own = sorted(step._run_keys(st, cut))
    detail = 'Recorded format detail with exact punctuation: ' + '!' * 500
    for key in own:
        cells[("S'", key)][0]['judge']['format'] = {'violation': True, 'detail': detail}
    # Any incumbent violation on this item excludes it, even when another S cell is clean.
    cells[('S', own[0])][0]['judge']['format'] = {'violation': True}
    clean = deepcopy(cells[('S', own[0])][0])
    clean['cell']['id'] += '/second'
    clean['judge']['format']['violation'] = False
    cells[('S', own[0])].append(clean)
    made[clean['cell']['id']] = {**deepcopy(made[cells[('S', own[0])][0]['cell']['id']]), 'cell': clean['cell']['id']}
    value, verdict = emit(case)
    fmt = value['format']
    assert fmt == {**verdict['format_cells'], 'margin': verdict['format_margin'],
                   'blocked': not verdict['guards']['format'], 'examples': fmt['examples']}
    assert fmt['blocked'] and len(fmt['examples']) == 2
    for example in fmt['examples']:
        trace = made[example['cell']]
        assert example['task_id'] in own[1:]
        assert example['detail'] == detail[:300]
        assert example['notes'] == step._notes_text(trace)[:600]
        assert example['candidate_reply'] == trace['replies'][-1][-600:]
        assert 'reference' not in example
    assert valid_feedback(case, value)
    changed = deepcopy(value)
    changed['format']['examples'][0]['candidate_reply'] = 'Unrecorded text'
    assert not valid_feedback(case, changed)
    changed = deepcopy(value)
    changed['format']['examples'][0]['task_id'] = 'GENERATED-ID'
    assert not valid_feedback(case, changed)


def test_format_uses_actual_judge_fields_when_no_text_detail_and_never_foreign_items(tmp_path, configuration):
    case = feedback_case(tmp_path, configuration)
    st, cut, cells, made, *_ = case
    own = step._run_keys(st, cut)
    for key in own:
        cells[("S'", key)][0]['judge']['format'] = {'violation': True, 'grid': False, 'reply': True}
    value, verdict = emit(case)
    assert all(row['detail'] == '{"grid": false, "reply": true, "violation": true}'
               for row in value['format']['examples'])
    other = deepcopy(cells[("S'", sorted(own)[0])][0])
    other['cell'].update(id='foreign-candidate', task_id='SEALED-ITEM')
    cells[("S'", 'SEALED-ITEM')] = [other]
    cells[('S', 'SEALED-ITEM')] = [{'judge': {'format': {'violation': False}}}]
    made['foreign-candidate'] = {**deepcopy(made[value['format']['examples'][0]['cell']]),
                               'cell': 'foreign-candidate', 'task_id': 'SEALED-ITEM'}
    assert step._format_feedback(cells, made, own, verdict, 'authored')['examples']
    assert all(row['task_id'] in own for row in step._format_feedback(cells, made, own, verdict, 'authored')['examples'])


@pytest.mark.parametrize('configuration', ['zebra-pc-v7', 'alfworld-v4'])
def test_parent_feedback_keeps_its_original_fields(tmp_path, configuration):
    value, _ = emit(feedback_case(tmp_path, configuration))
    assert 'format' not in value
    assert all('faults' not in row for row in value['procedures'])


def test_history_adds_verdict_counts_and_uses_kept_attempt_only_for_children(configuration):
    engineered = {'candidate_sha256': 'candidate', 'engineer': {'changes': [], 'dropped': []}}
    verdict = {'adopted': False, 'items': 5, 'generated': 0, 'fixed': [], 'broken': [], 'net': '0/1',
               'p_sign': 1, 'reason': 'guard:format', 'own_fault_cells': 3, 'format_cells': {'S': 1, "S'": 4}}
    line = step._line(1, engineered, {'verdict': verdict}, configuration=configuration)
    assert line['own_fault_cells'] == 3 and line['format_cells'] == verdict['format_cells']
    line['patience_counted'] = True
    assert engineer._history_line(line, 2, v24=True, v28=True, v29=True, v291=True)
    assert not engineer._history_line(line, 2, v24=True, v28=True, v29=True)
    old = step._line(1, engineered, {'verdict': verdict})
    assert 'own_fault_cells' not in old and 'format_cells' not in old
    engineered['candidate_sha256'] = None
    engineered['engineer']['changes'] = [{'id': 'p-new', 'n': 1, 'kind': 'new', 'target': None,
        'summary': 'Leak-checked description', 'survived': False, 'kept_attempt': 0,
        'attempts': [{'failed': 'C7'}, {'failed': 'C4'}]}]
    line = step._line(1, engineered, None, configuration=configuration)
    assert line['proposals'][0]['fate'] == 'check_failed:C7'
    assert line['own_fault_cells'] == 0 and line['format_cells'] == {'S': 0, "S'": 0}


def scripted_training(monkeypatch, configuration, outcomes):
    st = SimpleNamespace(parent=SimpleNamespace(sha256='parent'), setting=SimpleNamespace(extra={'configuration': configuration}))
    def propose(st, cut, r, incumbent, **kwargs):
        return {'candidate_sha256': None if outcomes[r - 1] == 'none' else 'candidate-' + str(r),
                'engineer': {'changes': [], 'dropped': [], 'analysis': {'items': []}, 'disclosed': [], 'lint': []}}
    def evaluate(st, cut, r, incumbent, candidate, generated, **kwargs):
        adopted = outcomes[r - 1] == 'adopt'
        return {'candidate_sha256': candidate.sha256, 'cells': 2, 'adopted': adopted, 'feedback': {},
                'verdict': {'adopted': adopted, 'items': 1, 'generated': 0, 'fixed': ['a'] if adopted else [],
                            'broken': [], 'net': '1/1' if adopted else '0/1', 'p_sign': 0.5,
                            'reason': None if adopted else 'gain:fixed_over_broken', 'own_fault_cells': 0,
                            'format_cells': {'S': 0, "S'": 0}}}
    monkeypatch.setattr(step, '_engineer_train', propose)
    monkeypatch.setattr(step, '_train_eval', evaluate)
    monkeypatch.setattr(step, '_package', lambda st, sha: SimpleNamespace(sha256=sha))
    monkeypatch.setattr(step, '_current', lambda st, done: [])
    monkeypatch.setattr(step, '_confirm_eval', lambda *args: {})
    monkeypatch.setattr(step, '_confirmed_training', lambda evaluation, confirm: evaluation)
    return step._train(st, {'run': []}, None)


@pytest.mark.parametrize('configuration,expected', [('zebra-pc-v8', 4), ('alfworld-v5', 4),
                                                  ('zebra-pc-v7', 2), ('alfworld-v4', 2)])
def test_patience_is_configuration_specific(monkeypatch, configuration, expected):
    _, records, _ = scripted_training(monkeypatch, configuration, ['miss'] * 6)
    assert len(records) == expected == p.train_patience(configuration)
    assert p.TRAIN_PATIENCE == 2 and p.TRAIN_ROUNDS == 6


def test_new_patience_preserves_no_candidate_rule_and_adoption_reset(monkeypatch, configuration):
    _, records, _ = scripted_training(monkeypatch, configuration, ['miss', 'none', 'adopt', 'miss', 'none', 'miss'])
    assert len(records) == 6 and [row['patience_counted'] for row in records] == [True, False, True, True, False, True]
