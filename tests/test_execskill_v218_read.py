"""main-v6 request classes on authored panels; no real provider or environment."""
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace

import pytest

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import cells, evaluation, instruction_start, package, profiles as p, readout, reuse, v218_read
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import FakeSandbox, alf_sessions, procedure
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.fixtures.execskill.items import alfworld_items, officeqa_items, searchqa_items, spreadsheetbench_items
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_evaluation import ITEMS, Solver, page, panel
from tests.test_execskill_readout import cell as report_cell
from tests.test_execskill_v214_evaluation import consent
from tests.test_execskill_zpc_pipeline import fixture_pool

CHILD = 'main-v6'
EVIDENCE = 'engineering_fixture'


@pytest.mark.parametrize('changes', [{}, {'multi_arm_arms': ['C', 'F', 'B', 'stages']}, {'date': ''},
                                    {'date': '  '}, {'sheet_test_qualification': False}])
def test_main_v6_consent_requires_ordered_arms_nonempty_date_and_sheet_qualification(tmp_path, changes):
    value = {**consent(), **changes}
    write_json(tmp_path / 'consent.json', value)
    if not changes:
        assert evaluation.consent(tmp_path, CHILD) == value
    else:
        with pytest.raises(ValueError, match='consent'):
            evaluation.consent(tmp_path, CHILD)
    if set(changes) <= {'multi_arm_arms', 'date'}:
        assert evaluation.consent(tmp_path, p.MAIN_V5) == value


def program(pid, bench='officeqa', *, hooks=('applies', 'before_call')):
    return procedure(pid, hooks, origin=bench, header='Authored input facts.',
                     policy_version=p.POLICY_VERSIONS[p.MAIN_V5])


def packages():
    card = package.empty(step='D/s0', evidence=EVIDENCE)
    programs = [program('fx-v218-' + name) for name in ('final', 'equal-final', 'other', 'equal-other')]
    found = [package.Package((proc,), 'D/' + label, EVIDENCE, card.sha256)
             for label, proc in zip(('s5', 's1', 's2', 's3'), programs)]
    arms = {'C': cells.Arm('card', card), 'F': cells.Arm('candidate', found[0]),
            'B': cells.Arm('blank', card)}
    stages = {'rows': ['C', 'S1', 'S2', 'S3', 'S3', 'F'],
              'packages': dict(zip(('S1', 'S2', 'S3'), found[1:]))}
    def note(text):
        return lambda view, state: {} if page(view) % 3 == 0 else {'facts': [text]}
    hooks = {proc.id: {'applies': lambda view: True, 'before_call': note(text)}
             for proc, text in zip(programs, ('Column labels are visible.', 'Column labels are visible.',
                                              'Row labels are visible.', 'Row labels are visible.'))}
    return arms, stages, hooks


def authored_read(root, *, configuration=CHILD, source_fault=False):
    shared = root / 'shared'
    write_json(shared / 'consent.json', {**consent(), 'date': '2026-11-01'})
    arms, stages, hooks = packages()
    fake = Solver()
    endpoint = Endpoint(fake, model=p.CHAINS['D'], max_tokens=100,
                        slots=Slots(root / 'slots', 'deepseek', 2), sleep=lambda _: None)
    unit = root / 'D/test/officeqa'
    faults = {('fx-v218-final', 'before_call'): 'exception'} if source_fault else {}
    context = cells.Context(attempt=unit / 'attempt-1', endpoint=endpoint, runtime=RUNTIME,
        cards={'officeqa': instruction_start.pins()['officeqa']['text']}, native=None, episodes=None,
        worker=lambda _: FakeSandbox(hooks, faults=faults), evidence=EVIDENCE, configuration=configuration)
    @contextmanager
    def workers(found, item, **kwargs):
        worker = FakeSandbox(hooks).start(found, kind='cell', **kwargs)
        try:
            yield worker
        finally:
            worker.close()
    result = evaluation.evaluate(unit, run='authored-v218', shared=shared, pinned=None, chain='D',
        bench='officeqa', arms=arms, context=context, workers=2, route_workers=workers,
        canaries=[], panel=panel, stages=stages, run_configuration=configuration)
    records = [read_json(path) for path in (unit / 'attempt-1/cells').glob('*.json')]
    return unit, result, records, fake


@pytest.mark.parametrize('configuration', [p.MAIN_V5, CHILD])
def test_enabled_silent_and_same_note_programs_share_only_in_main_v6(tmp_path, configuration):
    _, result, records, solver = authored_read(tmp_path, configuration=configuration)
    assert len(records) == 6 * len(ITEMS) == 72
    assert all(row['configuration'] == configuration for row in records)
    if configuration == p.MAIN_V5:
        assert solver.calls == 72 and all(row['shared_with'] is None for row in records)
        assert 'request_reuse' not in result and all('request_reuse' not in row for row in records)
        return
    assert solver.calls == 40
    assert result['request_reuse']['shared_cells'] == 32
    assert result['request_reuse']['shared_cells_by_reason'] == {
        'identical_to_C': 16, 'identical_to_F': 8, 'identical_to_stage': 8}
    assert result['request_reuse']['dispatched_cells'] == 40
    assert result['request_reuse']['fallback_cells'] == result['stages']['fallback'] == 0
    assert result['stages']['sources'] == {
        'S1': {'C': 4, 'F': 8}, 'S2': {'C': 4, 'sent': 8}, 'S3': {'C': 4, 'S2': 8}}
    by_id = {row['cell']['id']: row for row in records}
    for row in records:
        metadata = row['request_reuse']
        assert set(metadata['identity']) == {'request_sha256', 'post_call_sha256', 'fault_free'}
        if row['shared_with'] is not None:
            source = by_id[row['shared_with']]
            assert row['enabled']  # enabled procedures can now share C; their own routes remain visible
            assert row['calls'] == [] and source['calls']
            assert row['judge'] == source['judge'] and row['final'] == source['final']
            assert metadata['source_arm'] == source['cell']['arm']
            assert metadata['identity'] == metadata['source_identity']
        elif row['cell']['arm'] == 'B':
            assert metadata['source_arm'] is None  # the non-Zebra card changes request bytes


def test_source_hook_fault_dispatches_the_target_instead_of_sharing(tmp_path):
    _, result, records, solver = authored_read(tmp_path, source_fault=True)
    fallback = [row for row in records if row['request_reuse']['reason'] == 'source_not_reusable']
    assert len(fallback) == 8 and all(row['cell']['arm'] == 'S1' for row in fallback)
    assert all(row['shared_with'] is None and row['calls'] for row in fallback)
    assert result['request_reuse']['fallback_cells'] == 8 and solver.calls == 48


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa', 'spreadsheetbench', 'zebralogic'])
def test_zero_call_plans_use_real_request_identity_on_every_supported_main_v6_bench(tmp_path, bench):
    task = (searchqa_items(1)[0] if bench == 'searchqa' else officeqa_items(1)[0] if bench == 'officeqa'
            else spreadsheetbench_items(tmp_path / 'workbooks', 1)[0] if bench == 'spreadsheetbench'
            else fixture_pool()[0])
    proc = program('fx-v218-silent', bench)
    card = package.empty(step='D/s0', evidence=EVIDENCE)
    final = package.Package((proc,), 'D/s5', EVIDENCE, card.sha256)
    arms = {'C': cells.Arm('card', card), 'F': cells.Arm('candidate', final), 'B': cells.Arm('blank', card)}
    seen = []
    @contextmanager
    def workers(found, item, **kwargs):
        worker = FakeSandbox({proc.id: {'applies': lambda view: True, 'before_call': lambda *args: {}}})
        worker.start(found, kind='cell', **kwargs)
        seen.append(worker)
        try:
            yield worker
        finally:
            worker.close()
    context = SimpleNamespace(configuration=CHILD, cards={bench: 'Authored instruction.'},
                              runtime={bench: {} if bench == 'zebralogic' else RUNTIME[bench]})
    planned = v218_read.plan({'tasks': [task]}, arms, {}, bench=bench, context=context, workers=workers)
    item = task['task_id']
    assert planned['sources']['F'][item] == 'C'
    assert planned['sources']['B'][item] == ('C' if bench == 'zebralogic' else None)
    assert reuse.interchangeable(planned['identities']['F'][item], planned['identities']['C'][item], bench=bench)
    assert all(worker.closed for worker in seen)
    if bench == 'spreadsheetbench':
        assert all(worker.inputs == ['input.xlsx'] for worker in seen)


@pytest.mark.parametrize('damage', ['fault', 'post_call', 'different_request'])
def test_fault_or_post_call_or_request_difference_prevents_reuse(damage):
    identity = {'request_sha256': 'a'*64, 'post_call': [], 'faults': [], 'enabled': ['p']}
    altered = deepcopy(identity)
    altered[{'fault': 'faults', 'post_call': 'post_call', 'different_request': 'request_sha256'}[damage]] = (
        [{'kind': 'authored'}] if damage != 'different_request' else 'b'*64)
    found = v218_read.representatives({'C': identity, 'F': altered}, ['C', 'F'], bench='officeqa')
    assert found == {'C': None, 'F': None}


def test_alfworld_has_no_request_classes_and_keeps_the_legacy_stage_plan(tmp_path, monkeypatch):
    assert 'alfworld' not in reuse.BENCHES
    assert v218_read.representatives({'C': {'request_sha256': 'a', 'post_call': [], 'faults': []},
                                     'F': {'request_sha256': 'a', 'post_call': [], 'faults': []}},
                                    ['C', 'F'], bench='alfworld') == {'C': None, 'F': None}
    sessions = alf_sessions(monkeypatch)
    tasks = alfworld_items(tmp_path / 'authored-games')
    proc = program('fx-v218-alf', 'alfworld', hooks=('applies', 'alf_before_step'))
    extra = program('fx-v218-alf-unused', 'alfworld', hooks=('applies', 'alf_before_step'))
    final = package.Package((proc, extra), 'D/s5', EVIDENCE)
    stages = {'S1': package.Package((proc,), 'D/s1', EVIDENCE)}
    hooks = {proc.id: {'applies': lambda view: 'mug' in view['task_text']},
             extra.id: {'applies': lambda view: False}}
    @contextmanager
    def workers(found, item):
        worker = FakeSandbox(hooks).start(found, kind='cell')
        try:
            yield worker
        finally:
            worker.close()
    reset = evaluation.alfworld_reset(RUNTIME['alfworld'], Slots(tmp_path / 'slots', 'alfworld-episode', 1))
    plans = []
    for configuration in (p.MAIN_V5, CHILD):
        base = evaluation.test_plan(tasks, final, bench='alfworld', unit='D/test/alfworld',
            runtime=RUNTIME['alfworld'], workers=workers, reset=reset, run_configuration=configuration)
        found = evaluation.stage_plan(base, final, stages, bench='alfworld', runtime=RUNTIME['alfworld'],
                                      workers=workers)
        plans.append((base['sha256'], found['sha256'], found['sources'], found['derived']))
    assert plans[0] == plans[1]
    assert set(plans[0][2]['S1'].values()) == {'C', 'F'}
    assert len(sessions) == 2 * len(tasks) and all(session.closed for session in sessions)


def test_unseal_retains_request_hashes_and_resolves_shared_cells_for_secondary(tmp_path, monkeypatch):
    unit, result, records, _ = authored_read(tmp_path)
    monkeypatch.setattr(evaluation, '_ended', lambda *_: True)
    monkeypatch.setattr(evaluation, 'continuation', lambda *_: None)
    monkeypatch.setattr(evaluation, '_root_scanned', lambda *a, **kw: {})
    monkeypatch.setattr(evaluation, '_marker', lambda *a, **kw: {'label': 'authored', 'later_reads': False})
    opened = evaluation.unseal(tmp_path, tmp_path / 'D', 'D', [unit], run='authored-v218',
                               evidence=EVIDENCE, configuration=CHILD)
    values = opened['units']['officeqa']
    for row in records:
        key = (row['cell']['arm'], row['cell']['task_id'], row['cell']['run'])
        assert values[key]['request_sha256'] == [entry['request_sha256'] for entry in row['calls']]
        assert values[key]['request_reuse'] == row['request_reuse']
    item = ITEMS[0]['task_id']
    assert v218_read.request_hashes(values, 'F', item, 0) == v218_read.request_hashes(values, 'C', item, 0)


def test_primary_and_request_tie_secondary_are_reported_side_by_side(fast_statistics):
    rows = ['C', 'S1', 'S1', 'F', 'F', 'F']
    units = {}
    for bench in p.read_benches(CHILD):
        entries = {}
        for i in range(12):
            for arm in ('C', 'F', 'B', 'S1'):
                value = report_cell('pass' if arm in ('F', 'S1') else 'fail',
                                    room='authored-room-%d' % (i // 3) if bench == 'alfworld' else None)
                value['request_sha256'] = [digest((i, 'same' if i < 6 and arm in ('F', 'C', 'S1') else arm))]
                entries[(arm, 'item-%d' % i, 0)] = value
        units[bench] = entries
    parent = readout.readout(units, learned=['officeqa'], procedures={}, label='authored', evidence=EVIDENCE,
                             stages=rows, configuration=p.MAIN_V5)
    found = readout.readout(units, learned=['officeqa'], procedures={}, label='authored', evidence=EVIDENCE,
                            stages=rows, configuration=CHILD)
    assert 'identical_request_analysis' not in parent
    for key in ('contrasts', 'stages', 'stage_questions', 'q1_home', 'q2_similar', 'q3_noninferiority'):
        assert found[key] == parent[key]
    second = found['identical_request_analysis']
    assert second['conclusions_follow'] == 'primary'
    assert found['contrasts']['officeqa']['F-C']['mean'] == 1
    assert second['contrasts']['officeqa']['F-C']['mean'] == .5
    assert second['contrasts']['officeqa']['F-C']['identical_request_items'] == 6
    assert second['stages']['officeqa'][1]['minus_card']['mean'] == .5
    assert second['stages']['officeqa'][3]['minus_previous']['mean'] == 0


def test_secondary_requires_the_complete_nonempty_request_sequence():
    found = {('F', 'item', 0): {'shared_with': None, 'request_sha256': ['first', 'second-F']},
             ('C', 'item', 0): {'shared_with': None, 'request_sha256': ['first', 'second-C']}}
    assert not v218_read.identical_item(found, 'F', 'C', 'item')
    found[('F', 'item', 0)]['request_sha256'] = []
    found[('C', 'item', 0)]['request_sha256'] = []
    assert not v218_read.identical_item(found, 'F', 'C', 'item')


def test_sx_read_fixture_exercises_the_production_representative_priority():
    found = v218_read.structural_demo()
    assert found['passed'] and found['model_calls'] == found['sealed_reads'] == 0
    assert found['sources']['silent_enabled']['F'] == 'C'
    assert found['sources']['same_F']['S1'] == 'F'
    assert found['sources']['same_F']['S3'] == 'S2'
