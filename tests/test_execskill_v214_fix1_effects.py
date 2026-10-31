"""Paired authored effect records and inert views; no providers, data or containers."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json
from skillopt.execskill import (inert_feedback, profiles as p, replay, solver, trajectories,
                                v210_import, v211_effects)
from skillopt.execskill.package import FIXTURE, Package, Procedure, empty
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.execskill_fakes_env import FakeSandbox, Script
from tests.test_execskill_replay import SHEET_VIEW, precheck
from tests.test_execskill_v211_routing import context, proc
from tests.test_execskill_zpc_pipeline import SourceWorker

SOURCE = '''def sheet_feedback(view, report, state):
    return {"fields": {}, "request_repair": report["status"] == "exception"}
'''
FACTS = '''def before_call(view, state):
    return {"facts": ["There are 17 baskets."]}
'''


def shell(configuration, bench, package=None, worker=None):
    return solver._Shell(bench, package or empty(step='fixture', evidence=FIXTURE), None, worker,
        withhold=(), restore=(), placebo=None, text=None, native=None, nominal=None,
        configuration=configuration)


def trace(configuration, bench, package, recorded, calls=()):
    cell = {'id': 'authored-cell', 'unit': 'D/s1-' + bench + '/run', 'arm': "S'",
            'benchmark': bench, 'task_id': 'authored-item', 'run': 0}
    return trajectories.build(cell, evidence=FIXTURE, arm_kind='candidate', package_sha256=package.sha256,
        calls=calls, prediction={'shell': recorded}, judge={'v2': {'token': 'pass'}},
        deciding=0 if calls else None, worst='delivered' if calls else None,
        logical_calls=len(calls), dispatch_ts=0, finish_ts=1, configuration=configuration)


def test_sheet_same_authored_helper_records_persists_and_counts_repair_for_both_parents(tmp_path):
    procedure = proc(SOURCE, ('sheet_feedback',), 'spreadsheetbench', requests_second_call=True)
    package = replay.solo(procedure)
    found = []
    for configuration in (p.MAIN_V4, p.MAIN_V5):
        worker = SourceWorker()
        current = shell(configuration, 'spreadsheetbench', package, worker)
        current.start('cell')
        current.route_on(SHEET_VIEW)
        try:
            notes, repair = current.feedback(SHEET_VIEW, precheck('exception', 'KeyError', 'Total'))
            recorded = current.record()
        finally:
            current.close()
        assert repair and notes == ''
        assert recorded['effects'] == [{'procedure': procedure.id, 'hook': 'sheet_feedback',
            'kind': 'request_repair', 'permitted': True,
            'source_sha256': hashlib.sha256(SOURCE.encode()).hexdigest()}]
        call = {'purpose': 'repair', 'system': 'Authored repair fixture', 'user': json.dumps(SHEET_VIEW),
            'request_sha256': 'a' * 64, 'receipt': {'ok': True, 'response': 'authored reply',
                'finish_reason': 'stop', 'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2}}}
        value = trace(configuration, 'spreadsheetbench', package, recorded, [call])
        attempt = tmp_path / configuration
        trajectories.write(attempt, 'authored-cell', value)
        persisted = p.verified(read_json(attempt / trajectories.TRAJECTORIES / 'authored-cell.json'), 'trajectory')
        assert persisted['shell']['effects'] == recorded['effects']
        cells = {("S'", 'authored-item'): [{'cell': {'id': 'authored-cell'}, 'faults': []}]}
        coverage = v211_effects.coverage(SimpleNamespace(bench='spreadsheetbench'), procedure.id,
            ['authored-item'], package, cells, {'authored-cell': persisted}, [], set(), {})
        assert coverage['repair_requests'] == 1
        found.append((recorded, persisted['shell'], coverage))
    assert found[0] == found[1]


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa'])
def test_qa_shell_and_persisted_effect_shape_match_main_v4(bench):
    procedure = proc(FACTS, ('before_call',), bench)
    package = replay.solo(procedure)
    view = {'question': 'Count 17 baskets.', 'context': ['There are 17 baskets.']}
    found = []
    for configuration in (p.MAIN_V4, p.MAIN_V5):
        prediction = solver.solve(bench, view, 'Instruction', package, Script(['<answer>17</answer>']),
                                  worker=SourceWorker(), configuration=configuration)
        assert prediction['shell']['effects'] == []
        value = trace(configuration, bench, package, prediction['shell'])
        assert value['shell']['effects'] == []
        found.append((prediction, value['shell']))
    assert found[0] == found[1]


def test_imported_alfworld_cells_keep_main_v4_empty_effect_record():
    # Source-only immutable import, never an ALFWorld episode or a sealed panel.
    pinned = v210_import.pins()
    package = Package(tuple(replace(Procedure.from_json(row['record']), evidence=FIXTURE)
                            for row in pinned['procedures']), 'fixture-import', FIXTURE)
    found = []
    for configuration in (p.MAIN_V4, p.MAIN_V5):
        current = shell(configuration, 'alfworld', package, FakeSandbox())
        recorded = current.record()
        value = trace(configuration, 'alfworld', package, recorded)
        assert recorded['effects'] == value['shell']['effects'] == []
        found.append((recorded, value['shell']))
    assert found[0] == found[1]


def test_zebra_shell_and_trajectory_keep_v212_shape_without_v211_effects():
    found = []
    for configuration in (p.ZEBRA_PC_V13, p.MAIN_V5):
        current = shell(configuration, p.ZEBRA)
        recorded = current.record()
        value = trace(configuration, p.ZEBRA, current.package, recorded)
        assert 'effects' not in recorded and 'effects' not in value['shell']
        found.append((recorded, value['shell']))
    assert found[0] == found[1]


@pytest.mark.parametrize('configuration', [name for name in p.CONFIGURATIONS
                                         if name not in (p.MAIN_V5, p.IMPLANT_V5, p.MAIN_V6)])
def test_every_older_configuration_preserves_literal_parent_effect_shape(configuration):
    for bench in ('spreadsheetbench', 'alfworld', p.ZEBRA):
        current = shell(configuration, bench)
        recorded = current.record()
        value = trace(configuration, bench, current.package, recorded)
        assert ('effects' in recorded) == ('effects' in value['shell']) == (configuration == p.MAIN_V4)


def test_inert_sheet_examples_keep_same_public_run_report_without_mutating_input():
    ctx, _ = context('spreadsheetbench', report=precheck('exception', 'KeyError', 'Missing Total'))
    before = deepcopy(ctx.routing_items)
    ctx.configuration = p.MAIN_V4
    expected = inert_feedback._examples(ctx, ['item-0'])
    ctx.configuration = p.MAIN_V5
    found = inert_feedback._examples(ctx, ['item-0'])
    assert found == expected
    assert found[0]['view']['run_report'] == {'status': 'exception', 'exc_type': 'KeyError',
                                            'message': 'Missing Total', 'answer_cells': None}
    assert ctx.routing_items == before


@pytest.mark.parametrize('configuration', [p.MAIN_V3, p.ZEBRA_PC_V13])
def test_inert_sheet_examples_keep_older_non_v211_shape(configuration):
    ctx, _ = context('spreadsheetbench', report=precheck('exception', 'KeyError', 'Missing Total'))
    ctx.configuration = configuration
    assert 'run_report' not in inert_feedback._examples(ctx, ['item-0'])[0]['view']


@pytest.mark.parametrize('origin,excluded,allowed', [
    ('spreadsheetbench', ('spreadsheetbench',), False),
    (p.ZEBRA, (), True),
    (p.ZEBRA, ('spreadsheetbench',), False),
])
def test_inert_examples_filter_procedure_scope_only_under_main_v5(origin, excluded, allowed):
    ctx, _ = context('spreadsheetbench', report=precheck('exception', 'KeyError', 'Missing Total'))
    procedure = proc(SOURCE, ('sheet_feedback',), origin, excluded_benches=excluded)
    ctx.configuration = p.MAIN_V4
    assert inert_feedback._examples(ctx, ['item-0'], procedure=procedure)
    ctx.configuration = p.MAIN_V5
    assert bool(inert_feedback._examples(ctx, ['item-0'], procedure=procedure)) is allowed


@pytest.mark.parametrize('configuration,excluded', [(p.MAIN_V4, False), (p.MAIN_V5, True)])
def test_inert_intrinsic_exclusion_cannot_trigger_repair(configuration, excluded):
    procedure = proc(FACTS, ('before_call',), 'spreadsheetbench')
    ctx = SimpleNamespace(configuration=configuration, bench=p.ZEBRA)
    causes, evidence = inert_feedback.describe(SimpleNamespace(procedure=procedure), ctx, {'checks': []},
        effect_hooks=('before_call',), from_replay=False, from_routing=False, outcomes={})
    assert ('excluded_bench' in causes) is excluded
    assert ('excluded_bench' in evidence) is excluded
