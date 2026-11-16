"""Authored main-v8 reads; no real panel, worker, model, or network."""
from contextlib import contextmanager
from copy import deepcopy

import pytest

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import cells, evaluation, package, profiles as p, readout, v222_cards, v222_read
from tests.execskill_fakes_env import FakeSandbox
from tests.test_execskill_evaluation import ITEMS, Solver, panel
from tests.test_execskill_readout import cell as report_cell
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401

EVIDENCE = 'engineering_fixture'


def test_frozen_seed_segments_are_not_reported_as_learning_but_deletions_are():
    initial = v222_cards.initial_package(evidence=EVIDENCE)
    assert v222_read.learned_benches(initial, initial) == []
    own = v222_cards.own_segments(initial, 'officeqa')[0]
    deleted = package.with_(initial, step='G/s2', remove=[own.id])
    assert v222_read.learned_benches(deleted, initial) == ['officeqa']
    changed = v222_cards.make_segment('searchqa', 'Consider supplied evidence.', {'kind': 'public_evidence'},
        evidence=EVIDENCE, step=1, ordinal=9)
    learned = package.with_(initial, step='G/s1', add=[changed])
    assert v222_read.learned_benches(learned, initial) == ['searchqa']
    from tests.execskill_fakes_env import procedure
    imported = package.with_(initial, step='G/s5', add=[procedure('fx-alf-import', ('applies', 'before_call'), origin='alfworld')])
    assert v222_read.learned_benches(imported, initial) == []


class SegmentWorker(FakeSandbox):
    def start(self, found, **kwargs):
        for proc in found.procedures:
            namespace = {}
            exec(compile(proc.source, '<authored-card-segment>', 'exec'), namespace)
            self.hooks[proc.id] = {hook: namespace[hook] for hook in proc.hooks}
        return super().start(found, **kwargs)


def consent():
    return {'test_evaluation': True, 'sheet_test_qualification': True,
            'multi_arm_arms': ['B', 'C0', 'C', 'F', 'stages'], 'by': 'owner',
            'date': '2026-11-03', 'note': 'Authored consent fixture.'}


@pytest.mark.parametrize('change', [{}, {'multi_arm_arms': ['F', 'C', 'B', 'stages']},
    {'multi_arm_arms': ['C_hist', 'C', 'B', 'F', 'stages']}, {'sheet_test_qualification': False}, {'date': ''}])
def test_main_v8_consent_binds_all_four_arms_and_stages(tmp_path, change):
    value = {**consent(), **change}
    write_json(tmp_path / 'consent.json', value)
    if change:
        with pytest.raises(ValueError):
            evaluation.consent(tmp_path, p.MAIN_V8)
    else:
        assert evaluation.consent(tmp_path, p.MAIN_V8) == value


def authored_read(root):
    initial = v222_cards.initial_package(evidence=EVIDENCE, step='D/s0')
    foreign = v222_cards.make_segment('searchqa', 'Read the supplied public rows carefully.',
        {'kind': 'public_evidence'}, evidence=EVIDENCE, ordinal=9, step=1)
    final = package.with_(initial, step='D/s5', add=[foreign])
    arms = v222_read.arms(final, initial)
    write_json(root / 'shared/consent.json', consent())
    fake = Solver()
    endpoint = Endpoint(fake, model=p.CHAINS['D'], max_tokens=100,
                        slots=Slots(root / 'slots', 'deepseek', 2), sleep=lambda _: None)
    unit = root / 'D/test/officeqa'
    context = cells.Context(attempt=unit / 'attempt-1', endpoint=endpoint, runtime=RUNTIME,
        cards={'officeqa': v222_cards.format_text('officeqa')}, native=None, episodes=None,
        worker=lambda _: SegmentWorker(), evidence=EVIDENCE, configuration=p.MAIN_V8)
    @contextmanager
    def workers(found, item, **kwargs):
        worker = SegmentWorker().start(found, kind='cell', **kwargs)
        try:
            yield worker
        finally:
            worker.close()
    result = evaluation.evaluate(unit, run='authored-v222', shared=root / 'shared', pinned=None,
        chain='D', bench='officeqa', arms=arms, context=context, workers=2, route_workers=workers,
        canaries=[], panel=panel, stages={'rows': ['C', 'F', 'F', 'F', 'F', 'F'], 'packages': {}},
        run_configuration=p.MAIN_V8)
    records = [read_json(path) for path in (unit / 'attempt-1/cells').glob('*.json')]
    return unit, result, records, fake, foreign


def test_four_arm_read_delivers_p0_and_retains_actual_foreign_note_touches(tmp_path):
    _, result, records, fake, foreign = authored_read(tmp_path)
    assert len(records) == 4 * len(ITEMS)
    assert {row['cell']['arm'] for row in records} == {'B', 'C0', 'C', 'F'}
    assert all(row['configuration'] == p.MAIN_V8 for row in records)
    assert fake.calls == result['request_reuse']['dispatched_cells']
    for row in records:
        if row['cell']['arm'] == 'F':
            assert row['cross_identity']['non_home'] == [{'id': foreign.id, 'origin': 'searchqa',
                'segment': True, 'note_emitted': True, 'request_changed': False}]
        else:
            assert row['cross_identity']['non_home'] == []
        if row['cell']['arm'] == 'B':
            assert row['card'] == '' and row['enabled'] == []
        if row['cell']['arm'] == 'C0':
            assert row['enabled'] == []
        if row['cell']['arm'] == 'C':
            assert row['enabled']
        assert 'delivered_text' not in str(row['cross_identity'])


def test_enabled_dropped_and_blank_notes_do_not_count_as_cross_identity_touches():
    initial = v222_cards.initial_package(evidence=EVIDENCE)
    proc = initial.procedures[0]
    empty = v222_read.metadata('officeqa', initial, [{'route': {'enabled': [proc.id]},
        'notes': [{'id': proc.id, 'delivered_text': ''}, {'id': proc.id, 'delivered_text': '  '}]}])
    assert empty['non_home'] == []
    emitted = v222_read.metadata('officeqa', initial, [{'notes': [{'id': proc.id, 'delivered_text': 'A note.'}]}])
    assert emitted['non_home'][0]['note_emitted'] is True


def test_cross_identity_counts_items_not_notes_and_labels_f_c_as_descriptive():
    values = {}
    for n in range(4):
        for arm in ('B', 'C0', 'C', 'F'):
            value = report_cell('pass' if (arm == 'F' and n == 0) or (arm == 'C' and n == 1) else 'fail')
            value['cross_identity'] = {'version': v222_read.VERSION, 'non_home': [
                {'id': 'p-searchqa-1-1', 'origin': 'searchqa', 'segment': True,
                 'note_emitted': True, 'request_changed': False}] if arm == 'F' and n < 2 else []}
            values[(arm, str(n), 0)] = value
    result = v222_read.cross_identity({'officeqa': values})['officeqa']
    assert (result['items'], result['touched'], result['fixed'], result['broken']) == (4, 2, 1, 1)
    assert result['extra_model_calls'] == 0 and not result['identity_proven']
    assert 'not isolated procedure attribution' in result['comparison']
    values[('F', '3', 0)].pop('cross_identity')
    with pytest.raises(ValueError, match='Every main-v8 F cell'):
        v222_read.cross_identity({'officeqa': values})


def test_readout_has_c0_contrasts_stage_rows_and_cross_identity(fast_statistics):
    values = {}
    for n in range(12):
        for arm in ('B', 'C0', 'C', 'F'):
            value = report_cell('pass' if n % 2 else 'fail')
            value['cross_identity'] = {'version': v222_read.VERSION, 'non_home': []}
            values[(arm, str(n), 0)] = value
    units = {bench: deepcopy(values) for bench in p.active_benches(p.MAIN_V8)}
    for (_, item, _), value in units['alfworld'].items():
        value['room'] = 'room-' + str(int(item) % 3)
    result = readout.readout(units, learned=['officeqa'], procedures={},
        label='authored', evidence=EVIDENCE, stages=['C', 'F', 'F', 'F', 'F', 'F'], configuration=p.MAIN_V8)
    assert set(result['contrasts']['officeqa']) == {'C0-B', 'C-C0', 'F-C', 'C-B', 'F-B'}
    assert result['cross_identity']['officeqa']['identity_proven'] is True
    assert len(result['stages']['officeqa']) == 6


def test_sheet_callback_assembly_is_not_delivery_and_effects_bind_the_current_procedure():
    from skillopt.execskill import policy
    from tests.execskill_fakes_env import procedure
    proc = procedure('fx-cross-callback', ('applies', 'sheet_feedback'), origin='searchqa',
                     requests_second_call=True, policy_version=policy.POLICY_VERSION_V222)
    found = package.Package((proc,), 'G/s1', EVIDENCE)
    shell = {'notes': [{'id': proc.id, 'hook': 'sheet_feedback', 'delivered_text': 'Assembled but not sent.'}],
             'effects': [{'procedure': proc.id, 'hook': 'sheet_feedback', 'permitted': True}]}
    assert v222_read.metadata('spreadsheetbench', found, [shell])['non_home'] == []
    wrong = {proc.id: {'procedure_sha256': 'b' * 64, 'note_emitted': True, 'repair_requested': True}}
    assert v222_read.metadata('spreadsheetbench', found, [shell], post_call_effects=wrong)['non_home'] == []
    bound = {proc.id: {**wrong[proc.id], 'procedure_sha256': proc.sha256}}
    assert v222_read.metadata('spreadsheetbench', found, [shell], post_call_effects=bound)['non_home'] == [
        {'id': proc.id, 'origin': 'searchqa', 'segment': False, 'note_emitted': True, 'request_changed': True}]


@pytest.mark.parametrize('source_arm', ['C', 'S1'])
@pytest.mark.parametrize('repair', [False, True])
def test_shared_cells_keep_actual_same_version_off_home_callback_effects(tmp_path, monkeypatch, source_arm, repair):
    from dataclasses import replace
    from skillopt.execskill import policy, reuse, solver
    from tests.execskill_fakes_env import procedure
    from tests.test_execskill_cells import (_Client, _context, _reply, _cell, _sheet, PROGRAM, REPAIRED,
                                          DELIVERED, PASSED)
    from tests.fixtures.execskill.items import spreadsheetbench_items
    proc = procedure('fx-cross-shared-callback', ('applies', 'sheet_feedback'), origin='searchqa',
                     requests_second_call=True, policy_version=policy.POLICY_VERSION_V222)
    found = package.Package((proc,), 'G/s1', EVIDENCE)
    hooks = {proc.id: {'applies': lambda view: True, 'sheet_feedback': lambda *args:
                      {'fields': {'facts': ['The supplied report was inspected.']}, 'request_repair': repair}}}
    _sheet(monkeypatch, [DELIVERED], [PASSED])
    provider = _Client(*[_reply(text) for text in ([PROGRAM, REPAIRED] if repair else [PROGRAM])])
    context = replace(_context(tmp_path, provider, worker=lambda _: FakeSandbox(hooks)), configuration=p.MAIN_V8,
                      cards={'spreadsheetbench': v222_cards.format_text('spreadsheetbench')})
    item = spreadsheetbench_items(tmp_path / 'authored', 1)[0]
    source_spec = _cell(item, arm=source_arm, unit='G/test/spreadsheetbench')
    store = cells.TrainingStore(context.attempt)
    source = cells.run_cell(context, source_spec, item, cells.Arm('card' if source_arm == 'C' else 'candidate', found), store=store)
    view = solver.routing_view('spreadsheetbench', item['public'], runtime=context.runtime['spreadsheetbench'])
    worker = FakeSandbox(hooks).start(found, kind='cell')
    captured = []
    signature = reuse.signature('spreadsheetbench', found, view, worker,
        card_text=context.cards['spreadsheetbench'], runtime=context.runtime['spreadsheetbench'],
        configuration=p.MAIN_V8, note_observer=lambda shell, _: captured.append(shell.route.to_json()))
    worker.close()
    planned = v222_read.metadata('spreadsheetbench', found, [])
    assert planned['non_home'] == []  # first-request inspection cannot observe a later callback
    request_reuse = {'identity': signature, 'source_identity': signature,
                     'planning_metadata': {'keyword_hits': {'count': 0, 'sentences': []}, 'cross_identity': planned}}
    target = _cell(item, arm='F', unit=source_spec['unit'])
    if source_arm == 'C':
        result = cells.share_cell(context, target, item, cells.Arm('candidate', found), source,
                                  captured[0], store=store, request_reuse=request_reuse)
    else:
        result = cells.share_same(context, target, item, cells.Arm('candidate', found), source,
            captured[0], captured[0], found, store=store, request_reuse=request_reuse)
    assert result['shared_with'] == source['cell']['id']
    assert result['cross_identity'] == source['cross_identity']
    assert bool(result['cross_identity']['non_home']) is repair
    if repair:
        row = result['cross_identity']['non_home'][0]
        assert row['note_emitted'] is True and row['request_changed'] is True
    assert planned['non_home'] == []  # own pre-dispatch record is immutable
