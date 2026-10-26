"""Offline partial-judge regressions from the v29-2 S3a failure brief.

Replies below are authored fixtures; no archived provider content or clients are read.
"""
from copy import deepcopy
import json
import sys

import pytest

from skillopt.execskill import audit, v29_smoke
from tests.test_execskill_v29_audit import Judge, procedure, situation


class EditedJudge(Judge):
    def __init__(self, edit=None, **kwargs):
        super().__init__(**kwargs)
        self.edit = edit

    def plain(self, role, system, user, *, label, max_tokens):
        raw = super().plain(role, system, user, label=label, max_tokens=max_tokens)
        if self.edit is None:
            return raw
        value = self.edit(json.loads(raw), 'A' if system == audit.A_SYSTEM else 'B',
                          label.endswith('/format-retry'))
        return value if isinstance(value, str) else json.dumps(value)


@pytest.fixture(params=[('zebralogic', 'zebra-pc-v7'), ('alfworld', 'alfworld-v4')])
def profile(request):
    return request.param


def two_templates():
    return procedure(source='def before_call(view, state):\n'
                     '    return {"facts": ["First public statement.", "Second public statement."]}\n')


def run(profile, d=None, g=None, *, proc=None, final=False, rows=None, cache=None):
    bench, configuration = profile
    proc = proc or two_templates()
    rows = rows or [situation(step=0 if bench == 'alfworld' else None, pid=proc.id)]
    return audit.run_audit([proc], rows, {'G': g or EditedJudge(), 'D': d or EditedJudge()},
        bench=bench, configuration=configuration, step='D/s1/audit', round=1, change_id='1', final=final,
        cache=cache)


def request(result, part, judge='D'):
    return next(pair['requests'][judge] for pair in result['requests'] if pair['part'] == part)


def confirmed(result, kind):
    return [row for row in result['confirmed'] if row['kind'] == kind]


def test_smoke_optional_p6_other_does_not_discard_shared_template_flag(profile):
    source = ('def before_call(view, state):\n'
              '    parsed = view["question"].splitlines()[:1]\n'
              '    return {"facts": [parsed[0], "All clues were parsed."]}\n')
    proc = procedure(source=source)
    def edit(value, part, retry):
        if part == 'A':
            for row in value['templates']:
                row.update(verdict='P1' if row['t'] == 'T2' else 'ok',
                           false_when='When the task contains more than one clue.')
            value['other'] = [{'verdict': 'P6', 'where': 'before_call',
                'reason': 'The description says it parses every clue but the code only splits off the first line.'}]
        return value
    d = EditedJudge(edit)
    g = EditedJudge(lambda value, part, retry: {**edit(value, part, retry), 'other': []}
                    if part == 'A' else value)
    result = run(profile, d, g, proc=proc)
    assert result['available'] == {'G': True, 'D': True}
    assert [row['t'] for row in confirmed(result, 'template')] == ['T2']
    assert not result['audit_incomplete'] and not result['incomplete_units']
    record = request(result, 'A')
    assert not record['retries'] and not record['abstained']
    assert record['ignored'][0]['path'].startswith('other[0]')
    assert record['ignored'][0]['raw']['verdict'] == 'P6'
    assert record['parsed']['other'] == []
    assert v29_smoke.false_template_confirmed(result, 'zebralogic')


def test_invalid_required_template_abstains_only_that_template(profile):
    def edit(value, part, retry):
        if part == 'A':
            value['templates'][0]['verdict'] = 'P7'
        return value
    result = run(profile, EditedJudge(edit, template='P1'), EditedJudge(template='P1'))
    assert result['available']['D'] and result['audit_incomplete']
    assert [row['t'] for row in confirmed(result, 'template')] == ['T2']
    record = request(result, 'A')
    assert record['covered'] == ['template:T2']
    assert len(record['retries']) == 1
    assert any(row['unit'] == 'template:T1' and row['path'] == 'templates[0].verdict'
               for row in record['abstained'])
    retry = record['retries'][0]['user']
    assert 'templates[0].verdict' in retry and 'P7' in retry and 'ok|P1|P2|P3|P4|P5' in retry
    assert any(row['unit'] == 'template:T1' and 'D' in row['judges'] for row in result['incomplete_units'])


@pytest.mark.parametrize('field,value', [('policy', 'P6'), ('truth', 'maybe')])
def test_invalid_note_field_abstains_whole_note(profile, field, value):
    def edit(parsed, part, retry):
        if part == 'B':
            parsed['situations'][0]['notes'][0][field] = value
        return parsed
    result = run(profile, EditedJudge(edit, truth='false', policy='P2'),
                 EditedJudge(truth='false', policy='P3'))
    assert result['available']['D'] and not confirmed(result, 'note')
    record = request(result, 'B')
    assert record['parsed']['situations'][0]['notes'] == []
    assert record['covered'] == ['program']
    assert all(set(row['judges']) == {'G'} for row in result['advisory'] if row['kind'] == 'note')
    assert len(record['retries']) == 1 and result['audit_incomplete']
    assert any(row['path'] == 'situations[0].notes[0].' + field for row in record['abstained'])
    assert 'situations[0].notes[0].' + field in record['retries'][0]['user']


def test_invalid_note_truth_is_neither_ok_nor_flag(profile):
    def edit(value, part, retry):
        if part == 'B':
            value['situations'][0]['notes'][0]['truth'] = 'maybe'
        return value
    result = run(profile, EditedJudge(edit), EditedJudge(truth='false'))
    assert not confirmed(result, 'note')
    assert len([row for row in result['advisory'] if row['kind'] == 'note']) == 1
    assert result['audit_incomplete'] and result['available']['D']


def test_false_without_evidence_abstains_whole_note(profile):
    def edit(value, part, retry):
        if part == 'B':
            value['situations'][0]['notes'][0]['evidence'] = ' '
        return value
    result = run(profile, EditedJudge(edit, truth='false', policy='P2'), EditedJudge(policy='P3'))
    assert not confirmed(result, 'note')
    assert request(result, 'B')['parsed']['situations'][0]['notes'] == []
    assert request(result, 'B')['covered'] == ['program']
    assert any(row['path'].endswith('.evidence') for row in request(result, 'B')['abstained'])
    assert result['audit_incomplete']


def test_p1_without_false_when_does_not_discard_other_templates(profile):
    def edit(value, part, retry):
        if part == 'A':
            value['templates'][0].pop('false_when')
        return value
    result = run(profile, EditedJudge(edit, template='P1'), EditedJudge(template='P1'))
    assert [row['t'] for row in confirmed(result, 'template')] == ['T2']
    assert any(row['path'] == 'templates[0].false_when' for row in request(result, 'A')['abstained'])


def test_invalid_program_only_abstains_program(profile):
    def edit(value, part, retry):
        if part == 'B':
            value['program']['verdict'] = 'P7'
        return value
    result = run(profile, EditedJudge(edit, template='P1', truth='false'),
                 EditedJudge(template='P2', truth='false', program='P6'))
    assert len(confirmed(result, 'template')) == 2 and len(confirmed(result, 'note')) == 1
    assert not confirmed(result, 'program')
    assert any(row['unit'] == 'program' and row['path'] == 'program.verdict'
               for row in request(result, 'B')['abstained'])
    assert result['available']['D'] and result['audit_incomplete']


def three_templates():
    return procedure(source='def before_call(view, state):\n'
        '    return {"facts": ["First public statement.", "Second public statement.", "Third public statement."]}\n')


def test_missing_units_retry_uses_better_coverage_and_records_remaining_abstention(profile):
    def edit(value, part, retry):
        if part == 'A':
            value['templates'] = value['templates'][:2 if retry else 1]
        return value
    d = EditedJudge(edit, template='P1')
    result = run(profile, d, EditedJudge(template='P2'), proc=three_templates())
    record = request(result, 'A')
    assert record['selected_attempt'] == 1 and record['covered'] == ['template:T1', 'template:T2']
    assert len(record['retries']) == 1
    assert 'missing template T2' in record['retries'][0]['user']
    assert 'missing template T3' in record['retries'][0]['user']
    assert [row['t'] for row in confirmed(result, 'template')] == ['T1', 'T2']
    assert any(row['unit'] == 'template:T3' for row in record['abstained'])


@pytest.mark.parametrize('retry_kind', ['tie', 'worse', 'unusable'])
def test_better_first_attempt_or_tie_keeps_first_without_merging(profile, retry_kind):
    def edit(value, part, retry):
        if part == 'A':
            if retry and retry_kind == 'unusable':
                return 'not JSON'
            value['templates'] = ([value['templates'][-1]] if retry else
                                  value['templates'][:1 if retry_kind == 'tie' else 2])
        return value
    result = run(profile, EditedJudge(edit, template='P1'), EditedJudge(template='P1'), proc=three_templates())
    record = request(result, 'A')
    assert record['available'] and record['selected_attempt'] == 0 and len(record['retries']) == 1
    expected = ['T1'] if retry_kind == 'tie' else ['T1', 'T2']
    assert [row['t'] for row in confirmed(result, 'template')] == expected
    assert not any(row['t'] == 'T3' for row in confirmed(result, 'template'))


@pytest.mark.parametrize('part,shape', [
    ('A', 'not JSON'), ('A', []), ('A', {}), ('A', {'templates': {}}),
    ('B', {'situations': {}, 'program': {}}), ('B', {'situations': [], 'program': []}),
    ('B', {'situations': []}), ('B', {'program': {}}),
])
def test_unusable_request_retries_without_disabling_other_request_agreement(profile, part, shape):
    def edit(value, actual, retry):
        return deepcopy(shape) if actual == part else value
    d = EditedJudge(edit, template='P1', truth='false')
    result = run(profile, d, EditedJudge(template='P2', truth='false'))
    record = request(result, part)
    assert not record['available'] and len(record['retries']) == 1
    assert not result['available']['D'] and result['audit_incomplete'] and result['incomplete_units']
    assert confirmed(result, 'note' if part == 'A' else 'template')


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), float('-inf'), '\ud800'])
def test_noncanonical_extra_top_level_data_remains_shape_error(profile, bad):
    def edit(value, part, retry):
        if part == 'A':
            value['extra'] = bad
        return value
    result = run(profile, EditedJudge(edit, truth='false'), EditedJudge(truth='false'))
    record = request(result, 'A')
    assert not record['available'] and len(record['retries']) == 1
    assert confirmed(result, 'note') and result['audit_incomplete']


def test_deep_json_never_crashes_request_and_preserves_other_agreement(profile):
    depth = sys.getrecursionlimit() + 100
    raw = '{"templates":[],"extra":' + '[' * depth + '0' + ']' * depth + '}'
    result = run(profile, EditedJudge(lambda value, part, retry: raw if part == 'A' else value,
                                     truth='false'), EditedJudge(truth='false'))
    record = request(result, 'A')
    # The C JSON decoder's depth allowance differs between Python versions.
    # It may accept this shape (with missing templates), or reject its depth.
    assert len(record['retries']) == 1 and record['abstained']
    if record['available']:
        assert record['covered'] == []
    assert confirmed(result, 'note') and result['audit_incomplete']


def test_near_recursion_boundary_reply_records_persist_and_cache_reuse_safely(profile, tmp_path):
    from skillopt.validator_pilot.api import write_immutable_json

    previous_limit = sys.getrecursionlimit()
    try:
        sys.setrecursionlimit(1000)
        # The vulnerable depth depends on the surrounding Python call stack.
        # Sweep its narrow band rather than relying on one pytest stack depth.
        for depth in range(450, 501):
            def edit(value, part, retry):
                if part == 'A':
                    return json.dumps(value)[:-1] + ', "extra":' + '[' * depth + '0' + ']' * depth + '}'
                return value
            g, d, cache = EditedJudge(truth='false'), EditedJudge(edit, truth='false'), {}
            first = run(profile, d, g, cache=cache)
            calls = len(d.calls)
            repeated = run(profile, d, g, cache=cache)
            assert len(d.calls) == calls
            assert request(repeated, 'A')['reused']
            assert request(first, 'A')['available'] == request(repeated, 'A')['available']
            assert confirmed(first, 'note') and confirmed(repeated, 'note')
            if not request(first, 'A')['available']:
                assert len(request(first, 'A')['retries']) == 1
            write_immutable_json(tmp_path / ('boundary-%d.json' % depth), {'first': first, 'repeated': repeated})
    finally:
        sys.setrecursionlimit(previous_limit)


@pytest.mark.parametrize('bad_row', [None, 7, {}, {'t': 'UNKNOWN'}, {'t': []}, {'t': {}}])
def test_malformed_unknown_or_unhashable_template_rows_never_discard_valid_rows(profile, bad_row):
    def edit(value, part, retry):
        if part == 'A':
            value['templates'][0] = deepcopy(bad_row)
        return value
    result = run(profile, EditedJudge(edit, template='P1'), EditedJudge(template='P1'))
    record = request(result, 'A')
    assert record['available'] and len(record['retries']) == 1 and record['abstained']
    assert record['ignored'] and {row['unit'] for row in record['abstained']} == {'template:T1'}
    assert [row['t'] for row in confirmed(result, 'template')] == ['T2']


@pytest.mark.parametrize('kind', ['template', 'note'])
def test_identical_duplicate_rows_collapse_without_retry(profile, kind):
    def edit(value, part, retry):
        if part == 'A' and kind == 'template':
            value['templates'].append(deepcopy(value['templates'][0]))
        if part == 'B' and kind == 'note':
            value['situations'][0]['notes'].append(deepcopy(value['situations'][0]['notes'][0]))
        return value
    result = run(profile, EditedJudge(edit, template='P1', truth='false'),
                 EditedJudge(template='P1', truth='false'))
    record = request(result, 'A' if kind == 'template' else 'B')
    assert not record['retries'] and not record['abstained']
    assert len(confirmed(result, kind)) == (2 if kind == 'template' else 1)
    assert not result['audit_incomplete']


def test_conflicting_duplicate_template_abstains_only_duplicate_unit(profile):
    def edit(value, part, retry):
        if part == 'A':
            value['templates'].append({**value['templates'][0], 'verdict': 'P2'})
        return value
    result = run(profile, EditedJudge(edit, template='P1'), EditedJudge(template='P1'))
    assert [row['t'] for row in confirmed(result, 'template')] == ['T2']
    assert any('conflict' in row['reason'].lower() for row in request(result, 'A')['abstained'])


@pytest.mark.parametrize('field,conflict', [('truth', 'true'), ('policy', 'P3'), ('evidence', 'Different quoted input.')])
def test_conflicting_valid_note_judgments_abstain_whole_note(profile, field, conflict):
    def edit(value, part, retry):
        if part == 'B':
            rows = value['situations'][0]['notes']
            rows.append({**rows[0], field: conflict})
        return value
    result = run(profile, EditedJudge(edit, truth='false', policy='P2'), EditedJudge(policy='P3'))
    record = request(result, 'B')
    assert not confirmed(result, 'note') and result['audit_incomplete']
    assert record['parsed']['situations'][0]['notes'] == []
    assert record['covered'] == ['program']
    assert any(row['unit'] == 'note:S1/N1' and 'conflict' in row['reason']
               for row in record['abstained'])


def test_conflicting_required_note_reasons_abstain_whole_note(profile):
    def edit(value, part, retry):
        if part == 'B':
            rows = value['situations'][0]['notes']
            rows.append({**rows[0], 'reason': 'A different required explanation.'})
        return value
    result = run(profile, EditedJudge(edit, truth='false', policy='P2', program='P6'),
                 EditedJudge(truth='false', policy='P2', program='P6'))
    record = request(result, 'B')
    assert not confirmed(result, 'note') and len(confirmed(result, 'program')) == 1
    assert any(row['path'].startswith('situations[0].notes[') and 'conflict' in row['reason']
               for row in record['abstained'])
    assert result['available']['D'] and result['audit_incomplete']


def test_extra_top_level_keys_and_missing_other_do_not_retry(profile):
    def edit(value, part, retry):
        value['explanation'] = {'text': 'Authored optional commentary.'}
        if part == 'A':
            value.pop('other')
        return value
    result = run(profile, EditedJudge(edit, template='P1'), EditedJudge(template='P2'))
    assert result['available']['D'] and not result['audit_incomplete']
    assert len(confirmed(result, 'template')) == 2
    for part in ('A', 'B'):
        record = request(result, part)
        assert not record['retries'] and not record['abstained']
        assert any(row['path'] == 'explanation' and row['raw'] == {'text': 'Authored optional commentary.'}
                   for row in record['ignored'])
    assert request(result, 'A')['parsed']['other'] == []


@pytest.mark.parametrize('optional', ['missing', None, {}, 'malformed', [None], [{'notes': ['S1/N1']}]] )
def test_final_missing_or_invalid_contradictions_abstain_without_retry(profile, optional):
    def edit(value, part, retry):
        if part == 'B':
            if optional == 'missing':
                value.pop('contradictions')
            else:
                value['contradictions'] = deepcopy(optional)
        return value
    result = run(profile, EditedJudge(edit, template='P1'), EditedJudge(template='P1'), final=True)
    record = request(result, 'B')
    assert record['available'] and not record['retries']
    assert record['ignored'] or record['abstained']
    assert not confirmed(result, 'contradiction') and len(confirmed(result, 'template')) == 2
    if not isinstance(optional, list):
        assert any(row['unit'] == 'contradictions' for row in record['abstained'])
        assert result['audit_incomplete']


def test_required_retry_tokens_and_smoke_measurements_count_every_send(profile):
    def edit(value, part, retry):
        if part == 'A':
            value['templates'] = value['templates'][:1]
        return value
    d = EditedJudge(edit, template='P1')
    result = run(profile, d, EditedJudge(template='P2'))
    assert len(d.calls) == 3
    assert result['tokens']['D'] == {'input': 30, 'output': 9, 'charged': 39}
    measured = v29_smoke._audit_measurements({'audit': result, 'duplicate': result})
    assert measured['audit_d']['calls'] == 3 and measured['audit_d']['tokens'] == 39
    assert measured['audit_g']['calls'] == 2 and measured['audit_g']['tokens'] == 26


@pytest.mark.parametrize('unit', ['template', 'note', 'program'])
def test_malformed_required_reason_abstains_its_unit_without_losing_siblings(profile, unit):
    def edit(value, part, retry):
        if part == 'A' and unit == 'template':
            value['templates'][0]['reason'] = None
        if part == 'B' and unit == 'note':
            value['situations'][0]['notes'][0]['reason'] = {}
        if part == 'B' and unit == 'program':
            value['program'].pop('reason')
        return value
    result = run(profile, EditedJudge(edit, template='P1', truth='false', program='P6'),
                 EditedJudge(template='P1', truth='false', program='P6'))
    assert result['available']['D'] and result['audit_incomplete']
    assert len(confirmed(result, 'template')) == (1 if unit == 'template' else 2)
    assert len(confirmed(result, 'note')) == (0 if unit == 'note' else 1)
    assert len(confirmed(result, 'program')) == (0 if unit == 'program' else 1)


@pytest.mark.parametrize('bad', [None, {}, {'n': 'UNKNOWN'}, {'n': []}, {'n': {}}])
def test_malformed_note_ids_are_ignored_and_missing_note_abstains(profile, bad):
    def edit(value, part, retry):
        if part == 'B':
            value['situations'][0]['notes'][0] = deepcopy(bad)
        return value
    result = run(profile, EditedJudge(edit, program='P6'), EditedJudge(program='P6'))
    record = request(result, 'B')
    assert record['available'] and record['abstained'] and len(record['retries']) == 1
    assert record['ignored'] and {row['unit'] for row in record['abstained']} == {'note:S1/N1'}
    assert len(confirmed(result, 'program')) == 1 and not confirmed(result, 'note')


@pytest.mark.parametrize('bad', [None, {}, {'s': [], 'notes': []}, {'s': 'S1', 'notes': {}}, {'s': 'S1'}])
def test_malformed_situation_rows_keep_valid_program(profile, bad):
    def edit(value, part, retry):
        if part == 'B':
            value['situations'][0] = deepcopy(bad)
        return value
    result = run(profile, EditedJudge(edit, program='P6'), EditedJudge(program='P6'))
    record = request(result, 'B')
    assert record['available'] and record['abstained'] and len(record['retries']) == 1
    assert record['ignored'] and {row['unit'] for row in record['abstained']} == {'note:S1/N1'}
    assert len(confirmed(result, 'program')) == 1


@pytest.mark.parametrize('bad', [None, {}, 'text', [None], [{'where': [], 'verdict': 'P2', 'reason': 'R'}]])
def test_invalid_optional_other_shape_or_rows_are_ignored_without_retry(profile, bad):
    def edit(value, part, retry):
        if part == 'A':
            value['other'] = deepcopy(bad)
        return value
    result = run(profile, EditedJudge(edit, template='P1'), EditedJudge(template='P1'))
    record = request(result, 'A')
    assert record['available'] and not record['retries'] and record['ignored']
    assert len(confirmed(result, 'template')) == 2 and not result['audit_incomplete']


def test_valid_final_contradiction_survives_invalid_optional_sibling(profile):
    bench, configuration = profile
    first, second = two_templates(), procedure(pid='p-second')
    row = situation(step=0 if bench == 'alfworld' else None, pid=first.id)
    row['notes'].append({'procedure': second.id, 'text': 'A contradictory public statement.'})
    def edit(value, part, retry):
        if part == 'B':
            value['contradictions'].append({'notes': ['S1/N1'], 'reason': 'Malformed optional pair.'})
        return value
    result = audit.run_audit([first, second], [row],
        {'G': EditedJudge(contradiction=True), 'D': EditedJudge(edit, contradiction=True)},
        bench=bench, configuration=configuration, step='D/s1/audit-final', final=True)
    assert len(confirmed(result, 'contradiction')) == 1
    assert audit.removed_procedures(result, [first.id, second.id]) == [second.id]
    for pair in result['requests']:
        if pair['part'] == 'B':
            assert pair['requests']['D']['ignored'] and not pair['requests']['D']['retries']


def test_extra_unknown_rows_are_recorded_without_retry_when_required_units_are_complete(profile):
    def edit(value, part, retry):
        if part == 'A':
            value['templates'].append({'t': 'UNKNOWN', 'verdict': 'P2', 'reason': 'Invented ID.'})
        else:
            value['situations'][0]['notes'].append({'n': [], 'truth': 'false', 'policy': 'P2',
                'reason': 'Malformed extra ID.', 'evidence': 'Unused text.'})
        return value
    result = run(profile, EditedJudge(edit, template='P1'), EditedJudge(template='P1'))
    assert len(confirmed(result, 'template')) == 2 and not result['audit_incomplete']
    for part in ('A', 'B'):
        record = request(result, part)
        assert record['ignored'] and not record['abstained'] and not record['retries']
        assert record['covered'] == record['required']


def test_program_agrees_across_batches_but_missing_batch_coverage_remains_incomplete(profile):
    def edit(value, part, retry, judge):
        if part == 'B':
            first = value['situations'][0]['s'] == 'S1'
            value['program']['verdict'] = (('P6' if first else 'ok') if judge == 'G'
                                           else ('P7' if first else 'P6'))
        return value
    bench, _ = profile
    rows = [situation('item-%02d' % index, step=0 if bench == 'alfworld' else None) for index in range(8)]
    result = run(profile,
        EditedJudge(lambda value, part, retry: edit(value, part, retry, 'D')),
        EditedJudge(lambda value, part, retry: edit(value, part, retry, 'G')),
        rows=rows, final=True)
    assert len(confirmed(result, 'program')) == 1
    assert result['available'] == {'G': True, 'D': True} and result['audit_incomplete']
    assert result['incomplete_units'] == [{'request': 1, 'procedure': two_templates().id,
                                          'unit': 'program', 'judges': ['D']}]


def test_optional_function_must_belong_to_the_source_shown_in_that_request(profile):
    bench, configuration = profile
    first = two_templates()
    second = procedure(pid='p-second', source='def sibling_only(view):\n'
                       '    return "A public sibling fact."\n'
                       'def before_call(view, state):\n'
                       '    return {"facts": [sibling_only(view)]}\n')
    def edit(value, part, retry):
        if part == 'A':
            value['other'] = [{'where': 'sibling_only', 'verdict': 'P2', 'reason': 'Authored source finding.'}]
        return value
    row = situation(step=0 if bench == 'alfworld' else None, pid=first.id)
    row['notes'].append({'procedure': second.id, 'text': 'A public sibling fact.'})
    result = audit.run_audit([first, second], [row], {'G': EditedJudge(edit), 'D': EditedJudge(edit)},
        bench=bench, configuration=configuration, step='D/s1/audit', final=True)
    assert [finding['procedure'] for finding in confirmed(result, 'other')] == [second.id]
    first_a = next(pair for pair in result['requests'] if pair['part'] == 'A' and pair['procedure'] == first.id)
    for record in first_a['requests'].values():
        assert record['ignored'][0]['path'] == 'other[0].where'
        assert not record['retries'] and not record['abstained']


def assert_required_coverage_consistent(record):
    """No used required row can disagree with coverage or abstention records."""
    required, covered = set(record['required']), set(record['covered'])
    abstained = {row['unit'] for row in record['abstained']}
    assert not covered & abstained
    assert required - covered == required & abstained
    parsed = record['parsed']
    if 'templates' in parsed:
        used = {'template:' + row['t'] for row in parsed['templates']}
    else:
        used = {'note:' + row['s'] + '/' + note['n']
                for row in parsed['situations'] for note in row['notes']}
        if parsed['program']:
            used.add('program')
    assert used == covered


def two_note_situation(profile, item='run-1'):
    bench, _ = profile
    row = situation(item, step=0 if bench == 'alfworld' else None)
    row['notes'].append({'procedure': two_templates().id, 'text': 'A second public fact is visible.'})
    return row


@pytest.mark.parametrize('kind,field,bad', [
    ('template', 'verdict', 'P7'), ('template', 'reason', None), ('template', 'false_when', ''),
    ('note', 'truth', 'maybe'), ('note', 'policy', 'P6'), ('note', 'evidence', ''),
    ('note', 'reason', {}), ('situation', 'notes', {}), ('situation', 'notes', None),
])
@pytest.mark.parametrize('position', ['before', 'after'])
def test_malformed_duplicate_fragment_never_poisons_valid_judgment(profile, kind, field, bad, position):
    def edit(value, part, retry):
        if part == ('A' if kind == 'template' else 'B'):
            rows = (value['templates'] if kind == 'template' else value['situations']
                    if kind == 'situation' else value['situations'][0]['notes'])
            malformed = {**deepcopy(rows[0]), field: deepcopy(bad)}
            rows.insert(0 if position == 'before' else len(rows), malformed)
        return value
    result = run(profile, EditedJudge(edit, template='P1', truth='false'),
                 EditedJudge(template='P2', truth='false'), rows=[two_note_situation(profile)])
    record = request(result, 'A' if kind == 'template' else 'B')
    assert record['covered'] == record['required'] and record['ignored']
    assert not record['abstained'] and not record['retries'] and not result['audit_incomplete']
    assert len(confirmed(result, 'template')) == 2 and len(confirmed(result, 'note')) == 2
    assert_required_coverage_consistent(record)


@pytest.mark.parametrize('fragment', [None, {}, {'s': 'UNKNOWN', 'notes': []}, {'s': [], 'notes': []}])
def test_unknown_situation_fragment_is_ignored_without_phantom_abstention(profile, fragment):
    def edit(value, part, retry):
        if part == 'B':
            value['situations'].append(deepcopy(fragment))
        return value
    result = run(profile, EditedJudge(edit, truth='false'), EditedJudge(truth='false'))
    record = request(result, 'B')
    assert record['ignored'] and not record['abstained'] and not record['retries']
    assert record['covered'] == record['required'] and len(confirmed(result, 'note')) == 1
    assert not result['incomplete_units'] and not result['audit_incomplete']
    assert_required_coverage_consistent(record)


def test_review_valid_s1_with_malformed_duplicate_needs_no_partial_retry(profile):
    def edit(value, part, retry):
        if part == 'B':
            if retry:
                value['situations'][0]['notes'] = value['situations'][0]['notes'][:1]
            value['situations'].append({'s': 'S1', 'notes': {}})
        return value
    d = EditedJudge(edit, truth='false')
    result = run(profile, d, EditedJudge(truth='false'), rows=[two_note_situation(profile)])
    record = request(result, 'B')
    assert record['selected_attempt'] == 0 and not record['retries'] and len(d.calls) == 2
    assert record['covered'] == ['note:S1/N1', 'note:S1/N2', 'program']
    assert record['ignored'][0]['path'] == 'situations[1].notes'
    assert not record['abstained'] and not result['audit_incomplete']
    assert {row['n'] for row in confirmed(result, 'note')} == {'N1', 'N2'}
    assert_required_coverage_consistent(record)


def test_review_malformed_duplicate_preserves_more_covered_first_attempt_and_both_flags(profile):
    def edit(value, part, retry):
        if part == 'B':
            first = next(row for row in value['situations'] if row['s'] == 'S1')
            if retry:
                first['notes'] = first['notes'][:1]
            value['situations'] = [first, {'s': 'S1', 'notes': {}}]
        return value
    result = run(profile, EditedJudge(edit, truth='false'), EditedJudge(truth='false'),
                 rows=[two_note_situation(profile, 'run-a'), two_note_situation(profile, 'run-b')])
    record = request(result, 'B')
    assert record['selected_attempt'] == 0 and len(record['retries']) == 1
    assert record['covered'] == ['note:S1/N1', 'note:S1/N2', 'program']
    assert record['attempts'][1]['covered'] == ['note:S1/N1', 'program']
    assert 'missing note S2/N1' in record['retries'][0]['user']
    assert {row['unit'] for row in record['abstained']} == {'note:S2/N1', 'note:S2/N2'}
    assert {(row['s'], row['n']) for row in confirmed(result, 'note')} == {('S1', 'N1'), ('S1', 'N2')}
    assert result['audit_incomplete'] and result['available'] == {'G': True, 'D': True}
    assert_required_coverage_consistent(record)


def test_review_repeated_malformed_duplicate_never_confirms_abstained_note(profile):
    def edit(value, part, retry):
        if part == 'B':
            value['situations'][0]['notes'][1]['policy'] = 'P6'
            value['situations'].append({'s': 'S1', 'notes': {}})
        return value
    result = run(profile, EditedJudge(edit, truth='false'), EditedJudge(edit, truth='false'),
                 rows=[two_note_situation(profile)])
    assert [(row['s'], row['n']) for row in confirmed(result, 'note')] == [('S1', 'N1')]
    assert not result['advisory'] and result['audit_incomplete']
    assert result['incomplete_units'] == [{'request': 1, 'procedure': two_templates().id,
                                          'unit': 'note:S1/N2', 'judges': ['G', 'D']}]
    for judge in audit.JUDGES:
        record = request(result, 'B', judge)
        assert record['covered'] == ['note:S1/N1', 'program']
        assert record['selected_attempt'] == 0 and len(record['retries']) == 1
        assert {row['unit'] for row in record['abstained']} == {'note:S1/N2'}
        assert record['ignored'] and len(record['attempts']) == 2
        assert_required_coverage_consistent(record)
    assert v29_smoke.judge_counts(result) == {
        judge: {'covered': 4, 'abstained': 1, 'ignored': 2} for judge in audit.JUDGES}


def test_complementary_invalid_note_fragments_are_never_merged(profile):
    def edit(value, part, retry):
        if part == 'B':
            row = value['situations'][0]['notes'][0]
            value['situations'][0]['notes'] = [{**row, 'policy': 'P6'}, {**row, 'truth': 'maybe'}]
        return value
    result = run(profile, EditedJudge(edit, truth='false', policy='P2'),
                 EditedJudge(truth='false', policy='P2'))
    record = request(result, 'B')
    assert record['covered'] == ['program'] and not confirmed(result, 'note')
    assert record['parsed']['situations'][0]['notes'] == []
    assert len(record['retries']) == 1 and len(record['ignored']) == 2
    assert {row['unit'] for row in record['abstained']} == {'note:S1/N1'}
    assert_required_coverage_consistent(record)


def test_retry_selects_complete_note_instead_of_partial_note_flag(profile):
    def edit(value, part, retry):
        if part == 'B' and not retry:
            value['situations'][0]['notes'][0]['policy'] = 'P6'
        return value
    result = run(profile, EditedJudge(edit, truth='false'), EditedJudge(truth='false'))
    record = request(result, 'B')
    assert record['selected_attempt'] == 1 and len(record['retries']) == 1
    assert record['attempts'][0]['covered'] == ['program']
    assert record['covered'] == ['note:S1/N1', 'program'] and not record['abstained']
    assert len(confirmed(result, 'note')) == 1 and not result['audit_incomplete']
    assert_required_coverage_consistent(record)


@pytest.mark.parametrize('part,unit', [('A', 'template:T1'), ('B', 'note:S1/N1'), ('B', 'program')])
def test_findings_explicitly_excludes_uncovered_required_unit(profile, part, unit):
    result = run(profile, EditedJudge(template='P1', truth='false', program='P6'),
                 EditedJudge(template='P1', truth='false', program='P6'))
    record = request(result, part)
    parsed = deepcopy(record['parsed'])
    # Defense in depth: even a stale normalized row must not bypass coverage.
    parsed['_validation']['covered'].remove(unit)
    parsed['_validation']['abstained'].append({'unit': unit, 'path': unit, 'reason': 'Authored abstention.'})
    found = audit.findings(parsed, part=part, procedure=two_templates().id,
                           batch=result['sampling']['situations'])
    expected_kind = unit.split(':')[0]
    assert not any(row['kind'] == expected_kind and
                   (expected_kind != 'template' or row['t'] == 'T1') for row in found.values())

