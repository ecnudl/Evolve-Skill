"""Child-only output-shape evidence, sourced from the shell rule; offline fixtures."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.execskill import donors, engineer, fault_feedback as ff, profiles as p, solver, step
from tests.test_execskill_v29_runtime import procedure
from tests.test_execskill_v291_diagnostic_bounds import five_signature_report, maximum_source, wire_bytes
from tests.test_execskill_v291_engineer import run
from tests.test_execskill_v291_feedback import feedback_case, emit
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401

CHILDREN = ['zebra-pc-v9', 'alfworld-v6']
EXPECTED = {
    'before_call': 'None or {<note fields>}',
    'bindings': 'None or {<note fields>}',
    'sheet_feedback': 'None or {"fields": {<note fields>}, "request_repair": <bool>}',
    'alf_before_step': 'None or {"fields": {<note fields>}, "discourage": [<command strings>]}',
}


def shape_report(hook, returned='dict'):
    fault = {'hook': hook, 'kind': 'output_shape', 'message': returned, 'line': None,
             'arguments': {'view': {}, 'state': None}}
    return {'checks': [{'check': 'C6', 'detail': {'items': [
        {'task_id': 'run-1', 'first': {'applies': True, 'faults': [fault]}, 'second': {}}]}}]}


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('hook', EXPECTED)
def test_each_shape_signature_has_generated_expected_and_returned_in_repair_and_lint(configuration, hook):
    report = shape_report(hook)
    old_report = deepcopy(report)
    for example in (False, True):
        value = ff.summarize(procedure(), report, configuration=configuration, example=example, limit=3)
        signature = value['signatures'][0]
        assert signature['expected'] == EXPECTED[hook] == donors.expected_shape(hook)
        assert signature['returned'] == signature['message'] == 'dict'
        row = {**ff.lint_extension(value), 'fired_items': value['fired'], 'faulted_items': value['faulted']}
        assert ff.lint_details_ok(row, v292=True)
        assert not ff.lint_details_ok(row)
        for key in ('expected', 'returned'):
            changed = deepcopy(row)
            changed['signatures'][0][key] = 'unrecorded or incorrect description'
            assert not ff.lint_details_ok(changed, v292=True)
            changed['signatures'][0].pop(key)
            assert not ff.lint_details_ok(changed, v292=True)
    assert report == old_report


@pytest.mark.parametrize('configuration', ['zebra-pc-v8', 'alfworld-v5'])
def test_parent_shape_diagnostics_keep_exact_prior_fields(configuration):
    baseline = ff.summarize(procedure(), shape_report('before_call'))
    explicit = ff.summarize(procedure(), shape_report('before_call'), configuration=configuration)
    assert baseline == explicit
    assert not {'expected', 'returned'} & baseline['signatures'][0].keys()


def frozen_shaped(value, extra):
    """Literal pre-v2.9.2 rule to exercise falsey fields and unknown extras."""
    default = False if extra == 'request_repair' else []
    if value is None:
        return {}, default
    if extra is None:
        return (value, None) if isinstance(value, dict) else None
    if isinstance(value, dict) and set(value) <= {'fields', extra}:
        fields, other = value.get('fields') or {}, value.get(extra, default)
        valid = (type(other) is bool if extra == 'request_repair'
                 else type(other) is list and all(type(c) is str for c in other))
        if isinstance(fields, dict) and valid:
            return fields, other
    return None


@pytest.mark.parametrize('extra', [None, 'request_repair', 'discourage', 'unknown'])
def test_shared_shape_rule_preserves_all_old_acceptance_and_fault_records(extra):
    values = [None, {}, [], '', 0, False, 'text', 1, True, {'facts': ['x']}, {'extra': 1}]
    values += [{'fields': fields, extra: other} for fields in ({}, [], '', 0, False, None, {'facts': ['x']}, 'x', True)
               for other in (None, False, True, [], ['go north'], [1], 0, '')]
    for value in values:
        expected = frozen_shaped(value, extra)
        assert donors.shaped(value, extra) == expected
        faults = []
        shell = SimpleNamespace(fault=lambda *args: faults.append(args))
        assert solver._Shell.shaped(shell, SimpleNamespace(id='p'), 'before_call', value, extra) == expected
        assert faults == ([] if expected is not None else [('p', 'before_call', 'output_shape', None, type(value).__name__)])


def test_expected_shape_is_generated_from_the_same_type_rule_the_shell_checks(monkeypatch):
    monkeypatch.setitem(donors.SHAPE_EXTRA_TYPES, 'request_repair', (list, str))
    assert donors.expected_shape('sheet_feedback') == 'None or {"fields": {<note fields>}, "request_repair": [<command strings>]}'
    assert donors.shaped({'request_repair': ['command']}, 'request_repair') == ({}, ['command'])
    assert donors.shaped({'request_repair': True}, 'request_repair') is None
    assert ff.output_shape_fields('sheet_feedback', 'output_shape', 'bool', v292=True)['expected'] == donors.expected_shape('sheet_feedback')


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('example', [False, True])
def test_new_shape_fields_still_fit_the_actual_lint_and_evidence_byte_bounds(configuration, example):
    report = five_signature_report(message='🧩', arguments={'view': {'question': '🧩' * 3900}, 'state': None})
    for item in report['checks'][0]['detail']['items']:
        for phase in ('first', 'second'):
            item[phase]['faults'][0].update(kind='output_shape', exc_type=None)
    value = ff.summarize(procedure(maximum_source(unit='🧩')), report, configuration=configuration,
                         example=example, limit=5 if example else 3)
    assert value['fired'] == value['faulted'] == 15
    assert value['truncated'] is True
    assert wire_bytes(value if example else ff.lint_extension(value)) <= (16000 if example else 4000)
    assert value['signatures'] and all(ff.shape_fields_ok(row, v292=True) for row in value['signatures'])
    assert all(len(row['source_line']) <= 200 for row in value['signatures'])
    if example:
        assert value['example_call']['arguments']['state'] is None
    else:
        assert ff.lint_details_ok({**ff.lint_extension(value), 'fired_items': 15, 'faulted_items': 15}, v292=True)


@pytest.mark.parametrize('configuration', CHILDREN)
def test_shape_fields_propagate_through_real_repair_lint_context_and_validator(configuration):
    hook = 'alf_before_step' if p.is_alfworld(configuration) else 'before_call'
    source = 'def %s(view, state):\n    return []\n' % hook
    ctx, package, record = run(source, source, configuration=configuration)
    assert package is None
    repair = record['changes'][0]['fault_repair']
    signature = repair['calls'][0]['request']['evidence']['signatures'][0]
    assert signature['kind'] == 'output_shape' and signature['expected'] == EXPECTED[hook]
    assert signature['returned'] == 'list'
    c6 = next(row for row in record['lint'][0]['information'] if row['check'] == 'C6')
    assert c6['signatures'][0]['expected'] == EXPECTED[hook]
    assert engineer.payload(replace(ctx, round=2, lint=record['lint']))['lint'] == record['lint']
    changed = deepcopy(record['lint'])
    next(row for row in changed[0]['information'] if row['check'] == 'C6')['signatures'][0].pop('expected')
    with pytest.raises(ValueError):
        replace(ctx, round=2, lint=changed)


@pytest.mark.parametrize('configuration', CHILDREN)
@pytest.mark.parametrize('hook', EXPECTED)
def test_training_feedback_shape_fields_and_validation_are_child_only(tmp_path, configuration, hook):
    case = feedback_case(tmp_path, configuration)
    st, cut, cells, made, *_ = case
    own = step._run_keys(st, cut)
    for key in own:
        cells[("S'", key)][0]['faults'] = [{'procedure': 'p-new', 'hook': hook,
            'kind': 'output_shape', 'exc_type': None, 'message': 'list'}]
    feedback, _ = emit(case)
    fault = feedback['procedures'][0]['faults']
    signature = fault['signatures'][0]
    assert signature['expected'] == EXPECTED[hook] and signature['returned'] == 'list'
    assert engineer._fault_feedback_ok(fault, own, v292=True)
    assert not engineer._fault_feedback_ok(fault, own)
    references = step._references(st, cut, [], also=[row['task_id'] for row in feedback['unfixed_examples']])
    assert engineer._training_ok(feedback, references, own, made, st.bench,
        v24=True, v25=st.bench == 'zebralogic', v28=True, v29=True, v291=True, v292=True)
    old = step._procedure_fault_feedback('p-new', cells, made, own, 'prior', configuration='zebra-pc-v8')
    assert engineer._fault_feedback_ok(old, own)
    assert not {'expected', 'returned'} & old['signatures'][0].keys()
    for name in ('expected', 'returned'):
        changed = deepcopy(fault)
        changed['signatures'][0].pop(name)
        assert not engineer._fault_feedback_ok(changed, own, v292=True)


def test_non_shape_signatures_never_accept_the_extra_fields():
    row = {'hook': 'before_call', 'kind': 'crash:exception', 'message': 'list'}
    assert ff.shape_fields_ok(row, v292=True)
    assert ff.output_shape_fields('before_call', 'crash:exception', 'list', v292=True) == {}
    assert not ff.shape_fields_ok({**row, 'expected': EXPECTED['before_call'], 'returned': 'list'}, v292=True)
    assert not ff.shape_fields_ok({'hook': [], 'kind': 'output_shape', 'message': 'list'}, v292=True)
    assert not ff.shape_fields_ok({'hook': 'before_call', 'kind': 'output_shape', 'message': None}, v292=True)
