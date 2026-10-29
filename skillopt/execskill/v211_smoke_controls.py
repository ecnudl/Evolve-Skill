"""Authored zero-call adapter controls, separate from measured smoke costs.

Only fixed local replies, hooks and native outcomes are injected. The production
shell still performs binding validation, calculator, pre-check delivery, repair
selection and fallback. These receipts are engineering controls, never model or
method-effect evidence. They run sequentially before the measured S2 cells.
"""
from dataclasses import replace
import json
from unittest.mock import patch

from skillopt.continual_eval import backends
from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest
from . import fixtures, precheck, solver, profiles as p
from .package import Package, Procedure, FIXTURE


class _Worker:
    """The authored hook outputs; no untrusted source executes in this control."""
    def __init__(self, hooks):
        self.hooks, self.closed = hooks, False
    def start(self, package, *, kind, inputs_dir=None):
        self.package = package
        return self
    def call(self, pid, fn, args, *, timeout_s):
        value = self.hooks[fn](*args) if fn in self.hooks else True if fn == 'applies' else None
        return {'ok': True, 'value': value, 'value_sha256': digest(value), 'cpu_ms': 0}
    def close(self):
        self.closed = True


class _Replies:
    def __init__(self, replies):
        self.replies, self.requests = replies, []
    def __call__(self, system, user):
        response, finish = self.replies[len(self.requests)]
        self.requests.append({'system_sha256': digest(system), 'user_sha256': digest(user)})
        return {'ok': True, 'response': response, 'finish_reason': finish, 'status': 200,
                'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}}


def controls(fixture_root):
    fx = fixtures.fixture_package()
    bind = next(p for p in fx.procedures if p.id == 'fx-bindings')
    public = {'question': 'How much larger is the later value?', 'context': 'Earlier 100; later 120.'}
    bindings = [{'name': 'earlier', 'quote': 'Earlier 100', 'value': '100'},
                {'name': 'later', 'quote': 'later 120', 'value': '120'}]
    call = _Replies([('<calc>later - earlier</calc>', 'stop'), ('<answer>20</answer>', 'stop')])
    bound = solver.solve('officeqa', public, '', Package((bind,), 'control', FIXTURE), call,
        configuration=p.MAIN_V4, worker=_Worker({'applies': lambda v: True, 'bindings': lambda v: {'bindings': bindings}}))
    sheet = next(p for p in fx.procedures if p.id == 'fx-sheet-repair')
    item = fixtures.load_items(fixture_root, 'spreadsheetbench')[0]
    program = '```python\nx = 1\n```'
    rows = {}
    report = precheck.report('exception', evidence=FIXTURE, exc_type='ValueError', message='Authored failure',
                             answer_cells={})
    with patch.object(solver._Shell, 'run_precheck', return_value=report), patch.object(backends, '_native',
            return_value={'status': 'available', 'reason': 'authored_native_outcome', 'cleanup_confirmed': True}):
        for case, second, finish in [('requested_repair', '```python\nx = 2\n```', 'stop'),
                                     ('repair_fallback', '```python\nx =', 'length')]:
            calls = _Replies([(program, 'stop'), (second, finish)])
            got = solver.solve('spreadsheetbench', item['public'], '', Package((sheet,), 'control', FIXTURE), calls,
                runtime={'code_extraction_version': 'explicit-python-fences-v1'},
                configuration=p.MAIN_V4, worker=_Worker({'sheet_feedback': lambda v, r, state: {
                    'fields': {'warnings': ['The authored pre-check raised an exception.']}, 'request_repair': True}}))
            rows[case] = {'shell': got['shell'], 'requests': calls.requests, 'calls': len(calls.requests),
                         'injected_precheck_sha256': digest(report)}
    passed = (len(call.requests) == 2 and bound['shell']['compute'] is not None
        and bound['shell']['deciding_receipt'] == 1 and rows['requested_repair']['calls'] == 2
        and rows['requested_repair']['shell']['deciding_receipt'] == 1
        and rows['repair_fallback']['shell']['fallback'] == solver.FALLBACK
        and rows['repair_fallback']['shell']['deciding_receipt'] == 0)
    return {'passed': passed, 'evidence': FIXTURE, 'model_calls': 0, 'external_calls': 0,
        'benchmark_effect_evidence': False, 'injections': ['authored replies', 'authored hook outputs',
            'authored pre-check report', 'authored native outcome'],
        'bindings_calculator': {'shell': bound['shell'], 'requests': call.requests}, **rows}
