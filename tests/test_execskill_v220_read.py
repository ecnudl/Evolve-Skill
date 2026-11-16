"""SearchQA import reads on authored public items and scripted solver receipts only."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import cells, evaluation, package, profiles as p, v218_read, v220_import, v220_read
from tests.execskill_fakes_env import FakeSandbox, Script
from tests.execskill_v220_fakes import pinned_source
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.fixtures.execskill.items import searchqa_items
from tests import test_execskill_v217i_evaluation as parent

CHILD = p.SEARCHQA_HP_V6
EVIDENCE = 'engineering_fixture'


def consent():
    return {'test_evaluation': True, 'sheet_test_qualification': False, 'multi_arm_arms': ['F', 'C'],
            'by': 'owner', 'date': '2026-11-02', 'note': 'Post-hoc rejected SearchQA candidate read.'}


def test_searchqa_fc_consent_stays_explicit_only(tmp_path):
    write_json(tmp_path / 'consent.json', consent())
    assert evaluation.consent(tmp_path, CHILD) == consent()
    with pytest.raises(ValueError, match='consent'):
        evaluation.consent(tmp_path)


def authored_items():
    items = searchqa_items(2)
    items[0]['public'].update(
        question='Who was Ada Lovelace and this mathematician studied mechanical engines?',
        context='[DOC] [TLE] Mechanical notes [PAR] Ada Lovelace studied mechanical engines with Charles Babbage. | London\n'
                '[DOC] [TLE] Engine notes [PAR] Ada Lovelace and Charles Babbage studied mechanical engines.')
    items[1]['public'].update(question='where?', context='all lowercase prose without a proper name.')
    return items


def fixed_worker(final):
    hooks = {}
    for procedure in final.procedures:
        namespace = {}
        exec(compile(procedure.source, '<fixed-training-side-program>', 'exec'), namespace)
        hooks[procedure.id] = {hook: namespace[hook] for hook in procedure.hooks}
    return FakeSandbox(hooks)


def routed_context(root, configuration, chain, source, monkeypatch):
    original = parent.units.cell_context
    def bound(setting, *args, **kwargs):
        if configuration == CHILD:
            setting.extra[v220_import.PIN_KEY] = source
        return original(setting, *args, **kwargs)
    with monkeypatch.context() as scoped:
        scoped.setattr(parent.units, 'cell_context', bound)
        return parent.context(root, configuration, chain, 'searchqa', monkeypatch)


def authored_read(root, monkeypatch, chain='G'):
    source = pinned_source(root / 'source')
    final = v220_import.final_package(chain, EVIDENCE, source)
    card = package.empty(step=chain + '/card', evidence=EVIDENCE)
    context, fake = routed_context(root, CHILD, chain, source, monkeypatch)
    context.environment = lambda *_: pytest.fail('SearchQA never enters an environment lock')
    context.searchqa_import = source
    context.worker = lambda _: fixed_worker(final)
    fake.replies = ['<answer>Fixtown 0</answer>'] * 8
    @contextmanager
    def workers(found, item, **options):
        worker = fixed_worker(final).start(found, kind='cell', **options)
        try:
            yield worker
        finally:
            worker.close()
    root = root / 'run'
    unit = root / chain / 'test/searchqa'
    context.attempt = unit / 'attempt-1'
    write_json(root / 'shared/consent.json', consent())
    monkeypatch.setattr(evaluation, 'test_tasks', lambda *args, **kwargs: authored_items())
    found = evaluation.evaluate(unit, run='authored-searchqa-import', shared=root / 'shared', pinned=None,
        chain=chain, bench='searchqa', arms=v220_read.arms(final, card), context=context, workers=1,
        route_workers=workers, canaries=[], run_configuration=CHILD)
    records = [read_json(path) for path in (context.attempt / 'cells').glob('*.json')]
    return root, unit, found, records, fake, final


@pytest.mark.parametrize('changes', [{}, {'test_evaluation': False}, {'sheet_test_qualification': True},
    {'by': 'writer'}, {'date': ''}, {'date': ' '}, {'note': ''}, {'extra': True},
    {'multi_arm_arms': ['C', 'F']}, {'multi_arm_arms': ['F', 'C', 'B']},
    {'multi_arm_arms': ['F', 'C', 'stages']}, {'multi_arm_arms': ['F', 'F', 'C']}])
def test_searchqa_consent_is_exact_fc_without_sheet_qualification(tmp_path, changes):
    value = {**consent(), **changes}
    write_json(tmp_path / 'consent.json', value)
    if changes:
        with pytest.raises(ValueError, match='consent'):
            evaluation.consent(tmp_path, CHILD)
    else:
        assert evaluation.consent(tmp_path, CHILD) == value
        for older in (p.MAIN_V6, p.CROSS_V5, p.IMPLANT_V5):
            with pytest.raises(ValueError, match='consent'):
                evaluation.consent(tmp_path, older)


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_exact_fc_read_uses_candidate_programs_and_shares_silent_items(tmp_path, monkeypatch, chain):
    _, _, result, rows, fake, final = authored_read(tmp_path, monkeypatch, chain)
    assert set(result['packages']) == {'F', 'C'} and 'stages' not in result and result['twins'] == 0
    assert len(rows) == 4 and len(fake.requests) == 3
    assert result['request_reuse']['shared_cells'] == 1 and result['request_reuse']['dispatched_cells'] == 3
    assert result['request_reuse']['fallback_cells'] == 0
    by_id = {row['cell']['id']: row for row in rows}
    final_rows = [row for row in rows if row['cell']['arm'] == 'F']
    assert {tuple(row['searchqa_fired']['emitted_note_ids']) for row in final_rows} == {
        (), tuple(sorted(v220_import.PROCEDURE_IDS[chain]))}
    for row in rows:
        assert row['request_reuse']['version'] == v218_read.VERSION
        assert 'delivered_text' not in str(row['searchqa_fired'])
        if row['cell']['arm'] == 'C':
            assert row['searchqa_fired']['enabled'] == row['searchqa_fired']['emitted_note_ids'] == []
        else:
            assert row['package_sha256'] == final.sha256
        if row['shared_with']:
            assert row['calls'] == [] and row['searchqa_fired']['emitted_note_ids'] == []
            assert by_id[row['shared_with']]['cell']['arm'] == 'C'
            assert row['request_reuse']['reason'] == 'identical_to_C'
    assert not (rows and any(row['cell']['benchmark'] != 'searchqa' for row in rows))


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_target_shell_and_route_requests_match_main_v6_by_value(tmp_path, monkeypatch, chain):
    source = pinned_source(tmp_path / 'source')
    final = v220_import.final_package(chain, EVIDENCE, source)
    task = authored_items()[0]
    requests = {}
    for configuration in (p.MAIN_V6, CHILD):
        context, fake = routed_context(tmp_path / configuration, configuration, chain, source, monkeypatch)
        context.worker = lambda _: fixed_worker(final)
        context.environment = None
        fake.replies = ['<answer>Fixtown 0</answer>']
        unit = chain + '/test/searchqa'
        cell = {'id': cells.cell_id(unit, 'F', task['task_id'], 0), 'unit': unit, 'arm': 'F',
                'benchmark': 'searchqa', 'task_id': task['task_id'], 'run': 0}
        found = cells.run_cell(context, cell, task, cells.Arm('candidate', final),
                               store=evaluation.EvaluationStore(context.attempt, evidence=EVIDENCE))
        assert found['stop'] is None
        requests[configuration] = fake.requests
    assert requests[p.MAIN_V6] == requests[CHILD]


@pytest.mark.parametrize('unit,arm,bench', [
    ('G/s1-searchqa/train-r1', 'F', 'searchqa'), ('G/test/searchqa', 'B', 'searchqa'),
    ('G/test/searchqa', 'X_officeqa', 'searchqa'), ('G/test/officeqa', 'F', 'officeqa'),
    ('H/test/searchqa', 'F', 'searchqa'), ('G/v214-smoke/S1/searchqa', 'F', 'searchqa'),
    ('G/v214-smoke/S2/searchqa/extra', 'F', 'searchqa')])
def test_no_other_bench_arm_or_learning_scope_reaches_dispatch(tmp_path, unit, arm, bench):
    context = cells.Context(tmp_path, None, {'searchqa': {}}, {}, None, None,
        lambda *_: pytest.fail('No worker'), EVIDENCE, configuration=CHILD,
        solve=lambda *a, **kw: pytest.fail('No shell'))
    task = authored_items()[0]
    row = {'id': cells.cell_id(unit, arm, task['task_id'], 0), 'unit': unit, 'arm': arm,
           'benchmark': bench, 'task_id': task['task_id'], 'run': 0}
    with pytest.raises(ValueError, match='refuses arm'):
        cells._shell(context, row, task, cells.Arm('candidate', package.empty(step='G/card', evidence=EVIDENCE)), Script([]))


@pytest.mark.parametrize('mismatch', ['missing_pins', 'different_final', 'empty_final', 'extra_arm', 'stage_rows',
                                    'withheld_procedure'])
def test_read_validates_composition_and_fc_before_opening_panel(tmp_path, monkeypatch, mismatch):
    source = pinned_source(tmp_path / 'source')
    final = v220_import.final_package('G', EVIDENCE, source)
    card = package.empty(step='G/card', evidence=EVIDENCE)
    arms = v220_read.arms(final, card)
    stages = None
    if mismatch == 'different_final':
        arms['F'] = cells.Arm('candidate', package.Package(final.procedures[:-1], final.step, EVIDENCE))
    elif mismatch == 'empty_final':
        arms['F'] = arms['C']
    elif mismatch == 'extra_arm':
        arms['B'] = cells.Arm('blank', card)
    elif mismatch == 'stage_rows':
        stages = {'rows': ['C', 'F'], 'packages': {}}
    elif mismatch == 'withheld_procedure':
        arms['F'] = cells.Arm('candidate', final, withhold={v220_import.PROCEDURE_IDS['G'][0]})
    context = cells.Context(tmp_path / 'G/test/searchqa/attempt-1', None, {'searchqa': {}}, {}, None, None,
        None, EVIDENCE, configuration=CHILD, searchqa_import=None if mismatch == 'missing_pins' else source)
    write_json(tmp_path / 'shared/consent.json', consent())
    monkeypatch.setattr(evaluation, 'test_tasks', lambda *a, **kw: pytest.fail('No test panel before validation'))
    with pytest.raises(ValueError):
        evaluation._evaluate(tmp_path / 'G/test/searchqa', 'G/test/searchqa', run='authored',
            shared=tmp_path / 'shared', pinned=None, chain='G', bench='searchqa', arms=arms,
            context=context, workers=1, route_workers=None, canaries=[], panel=None, reset=None,
            stages=stages, run_configuration=CHILD)


def test_unseal_keeps_reuse_and_firing_metadata(tmp_path, monkeypatch):
    root, unit, _, rows, _, final = authored_read(tmp_path, monkeypatch)
    monkeypatch.setattr(evaluation, '_ended', lambda *_: True)
    monkeypatch.setattr(evaluation, 'continuation', lambda *_: None)
    monkeypatch.setattr(evaluation, '_root_scanned', lambda *a, **kw: {})
    monkeypatch.setattr(evaluation, '_marker', lambda *a, **kw: {'label': 'authored', 'later_reads': False})
    opened = evaluation.unseal(root, root / 'G', 'G', [unit], run='authored-searchqa-import',
                               evidence=EVIDENCE, configuration=CHILD)
    assert set(opened['units']) == {'searchqa'} and 'stages' not in opened
    found = opened['units']['searchqa']
    for row in rows:
        key = (row['cell']['arm'], row['cell']['task_id'], row['cell']['run'])
        assert found[key]['searchqa_fired'] == row['searchqa_fired']
        assert found[key]['request_reuse'] == row['request_reuse']
        assert found[key]['request_sha256'] == [call['request_sha256'] for call in row['calls']]
    counts = v220_read.fired_counts(found, {proc.id: proc.origin for proc in final.procedures})
    assert counts['items'] == 2 and counts['fired_items'] == 1
    assert all(row['fired_items'] == 1 for row in counts['per_procedure'].values())


def test_canaries_open_only_searchqa_after_consent_and_skip_practice_duplicates(tmp_path):
    question = 'Authored SearchQA public question with enough characters to form a canary?'
    training = [{'task_id': 'practice', 'public': {'question': question}, 'private': {}}]
    write_json(tmp_path / 'practice.json', training)
    pools = {'searchqa': {'path': str(tmp_path / 'practice.json'),
                         'sha256': hashlib.sha256((tmp_path / 'practice.json').read_bytes()).hexdigest()}}
    root = tmp_path / 'run'
    seen = []
    def panel(pin, bench, *, access):
        seen.append((pin, bench))
        return [training[0], {'public': {'question': question + ' Additional authored detail.'}}], {'panel_hash': 'f' * 64}
    with pytest.raises(ValueError, match='consent'):
        evaluation.make_read_canaries(root, 'authored-pin', pools=pools, run='authored', evidence=EVIDENCE,
            panel=panel, order=v220_import.STEPS, configuration=CHILD)
    assert seen == []
    write_json(root / 'shared/consent.json', consent())
    value = evaluation.make_read_canaries(root, 'authored-pin', pools=pools, run='authored', evidence=EVIDENCE,
        panel=panel, order=v220_import.STEPS, configuration=CHILD)
    assert seen == [('authored-pin', 'searchqa')]
    assert value['counts'] == value['skipped'] == {'searchqa': 1} and value['extends'] is None
    assert evaluation.read_canary_sources(CHILD) == {'searchqa': 'question'}
    assert evaluation.load_canaries(root, read=True, configuration=CHILD) == value['canaries']
    assert not (root / p.CANARIES).exists()


def test_other_panel_and_sheet_qualification_refuse_before_any_data_or_environment_access(tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail('No other data or environment work')
    with pytest.raises(ValueError, match='never opens another benchmark'):
        evaluation.test_tasks(tmp_path, None, 'spreadsheetbench', 'G/test/spreadsheetbench', run='authored',
            runtime={}, native=None, workers=1, evidence=EVIDENCE, panel=forbidden, configuration=CHILD)
    with pytest.raises(ValueError, match='qualification prerequisite'):
        evaluation.prepare_test_qualification(SimpleNamespace(extra={'configuration': CHILD}), 'G', panel=forbidden)
