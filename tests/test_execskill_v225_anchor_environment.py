"""Offline production-shaped read contexts: environment, solver, cells and sealed stores.

Only external resources are faked: provider transport, native spreadsheet execution/
scoring, ALFWorld sessions, sandbox workers and the machine environment lock.
"""
from contextlib import contextmanager
from copy import copy, deepcopy
from dataclasses import replace
import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (cells, evaluation, instruction_start, package, profiles as p,
                               slots, solver, units, v218_lock, v222_cards, v225_cards,
                               v225_client, v225_read as read)
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import FakeNative, FakeSandbox, alf_sessions, receipt
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.fixtures.execskill.items import (alfworld_games, officeqa_items, searchqa_items,
                                          spreadsheetbench_items)
from tests.test_execskill_routes import Gateway, completion, route_b_config
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401

EVIDENCE = 'engineering_fixture'
BENCHES = p.MAIN_V5_ORDER
CARD = 'Compare all supplied constraints carefully.'
PROGRAM = "```python\nimport openpyxl\nb = openpyxl.load_workbook('input.xlsx')\nb.active['B1'] = 15\nb.save('output.xlsx')\n```"


class Pool:
    """Observable resource ownership, without containers or a machine-wide lock."""
    def __init__(self):
        self.depth = self.entries = 0

    def limited(self, _):
        return self

    @contextmanager
    def hold(self):
        self.entries += 1
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1


def task_for(root, bench):
    if bench == 'searchqa':
        return searchqa_items(1)[0]
    if bench == 'officeqa':
        return officeqa_items(1)[0]
    if bench == 'spreadsheetbench':
        return spreadsheetbench_items(root / 'workbooks', 1)[0]
    if bench == 'alfworld':
        game = alfworld_games()[0]
        game['plan'] = ['look']
        path = root / 'games' / game['gamefile']
        write_json(path, game)
        return {'benchmark': bench, 'task_id': game['task_id'],
                'public': {'game_file': str(path)}, 'private': {}}
    return {'benchmark': bench, 'task_id': 'authored-zebra',
            'public': {'question': 'There are 5 houses, numbered 1 to 5 from left to right, as seen from across the street. An authored puzzle.',
                       'columns': ['Name', 'Color']},
            'private': {'answer': {'House ' + str(i): {'Name': 'Name' + str(i), 'Color': 'Color' + str(i)}
                                   for i in range(1, 6)}}}


def production_context(root, endpoint, monkeypatch, *, attempt=None, configuration=p.MAIN_V9):
    pools = {name: Pool() for name in (slots.LIVE, slots.CALL, slots.NATIVE, slots.EPISODE)}
    locked, workers, nominal = Pool(), [], []
    runtime = deepcopy(RUNTIME)
    runtime['zebralogic'] = {}
    runtime['spreadsheetbench'].update(spreadsheet_scorer='qualified_lo_recalc_v7_v1', recalculation={})
    cards = {bench: v222_cards.format_text(bench) for bench in BENCHES}
    if not p.is_v222(configuration):
        cards = {bench: v222_cards.historical_text(bench) for bench in BENCHES}
    setting = SimpleNamespace(slots=pools, sandbox={}, runtime=runtime, cards=cards,
                              evidence=EVIDENCE, extra={'configuration': configuration})

    def environment(found, bench, *, unit):
        assert found is setting and bench in BENCHES
        return locked.hold()

    def worker(**_):
        made = FakeSandbox()
        workers.append(made)
        return made

    def solve(*args, **kwargs):
        assert locked.depth == 1
        nominal.append(kwargs['nominal_tokens'])
        return solver.solve(*args, **kwargs)

    monkeypatch.setattr(v218_lock, 'environment', environment)
    monkeypatch.setattr(units, 'Worker', worker)
    context = units.cell_context(setting, attempt or root / 'attempt-1', endpoint, solve=solve)
    assert context.environment is not None
    return context, SimpleNamespace(pools=pools, lock=locked, workers=workers, nominal=nominal)


class FirstCall(BaseException):
    pass


class StopEndpoint:
    def __init__(self, chain):
        self.model = p.CHAINS[chain]
        self.requests = []

    def recorder(self, label):
        endpoint = self

        class Recorder:
            sends, receipts = [], []

            def __call__(self, system, user):
                endpoint.requests.append((system, user))
                raise FirstCall()

        return Recorder()


@pytest.mark.parametrize('chain', p.CHAINS)
@pytest.mark.parametrize('bench', BENCHES)
@pytest.mark.parametrize('label', read.labels('anchor'))
def test_anchor_environment_reaches_first_call_with_identical_request(tmp_path, monkeypatch, chain, bench, label):
    endpoint = StopEndpoint(chain)
    context, resources = production_context(tmp_path, endpoint, monkeypatch)
    task = task_for(tmp_path, bench)
    alf_sessions(monkeypatch)
    arm = read.arms(None, 'anchor', chain=chain, evidence=EVIDENCE)[label]
    own = read.context_for(context, bench, label)
    unit = chain + '/test/anchor/' + bench
    cell = {'id': cells.cell_id(unit, label, task['task_id'], 0), 'unit': unit, 'arm': label,
            'benchmark': bench, 'task_id': task['task_id'], 'run': 0}
    before_cards, before_runtime = deepcopy(own.cards), deepcopy(own.runtime)
    with pytest.raises(FirstCall):
        cells.run_cell(own, cell, task, arm, store=SimpleNamespace(claim=lambda _: None))
    assert resources.lock.entries == 1 and resources.lock.depth == 0
    assert own.environment is context.environment
    assert own.cards == before_cards and own.runtime == before_runtime
    assert len(endpoint.requests) == 1
    expected_system = (solver.ALF_SYSTEM + ('\n' + solver.GUIDANCE + own.cards[bench] if own.cards[bench] else '')
                       if bench == 'alfworld' else
                       solver._system(bench, own.cards[bench], own.runtime[bench], configuration=p.MAIN_V9))
    assert endpoint.requests[0][0] == expected_system
    if label == 'B':
        assert own.cards[bench] == '' and solver.GUIDANCE not in endpoint.requests[0][0]
    # This is the previously working environment-less request, including the
    # historical Zebra user prompt. Compare the complete request byte for byte.
    without = copy(own)
    without.environment = None
    without.solve = solver.solve
    with pytest.raises(FirstCall):
        cells.run_cell(without, cell, task, arm, store=SimpleNamespace(claim=lambda _: None))
    assert endpoint.requests[0] == endpoint.requests[1]
    assert resources.pools[slots.EPISODE].depth == 0


@pytest.mark.parametrize('chain', p.CHAINS)
@pytest.mark.parametrize('bench', BENCHES)
@pytest.mark.parametrize('event', read.EVENTS)
def test_every_read_event_completes_with_environment(tmp_path, monkeypatch, chain, bench, event):
    task = task_for(tmp_path, bench)
    text = {'searchqa': '<answer>Fixtown 0</answer>', 'officeqa': '<answer>200</answer>',
            'zebralogic': '{}', 'spreadsheetbench': PROGRAM, 'alfworld': '<action>look</action>'}[bench]
    requests = []
    gateway = Gateway(completion(text))
    if chain == 'D':
        client = v225_client.solver_client(p.CHAINS['D'], configuration=p.MAIN_V9,
            config={**route_b_config(tmp_path, max_tokens=p.solver_tokens(p.CHAINS['D'], bench)),
                    'thinking': {'type': 'disabled'}}, transport=gateway.transport)
    else:
        def call(system, user):
            requests.append((system, user))
            return receipt(text)
        client = SimpleNamespace(call=call)
    endpoint = Endpoint(client, model=p.CHAINS[chain], max_tokens=p.solver_tokens(p.CHAINS[chain], bench),
                        slots=Slots(tmp_path / 'slots', p.CHAINS[chain], 1), sleep=lambda _: None)
    root = tmp_path / 'run'
    unit = root / chain / 'test' / event / bench
    context, resources = production_context(root, endpoint, monkeypatch, attempt=unit / 'attempt-1')
    sessions = alf_sessions(monkeypatch)
    native = FakeNative().install(monkeypatch)
    if bench == 'spreadsheetbench':
        def generate(request, runtime):
            assert resources.pools[slots.NATIVE].depth == 1
            return {**native.native(request, runtime), 'output_base64':
                    base64.b64encode(Path(task['private']['test_files'][0]).read_bytes()).decode()}
        monkeypatch.setattr(backends, '_native', generate)
    original_score = backends.score
    scorings = []

    def score(found, public, private, prediction, *, runtime=None):
        if found != 'spreadsheetbench':
            return original_score(found, public, private, prediction, runtime=runtime)
        assert resources.pools[slots.NATIVE].depth == 1
        scorings.append(runtime['_score_context'])
        return {'status': 'pass', 'reason': 'authored_native_score', 'cleanup_confirmed': True,
                'metrics': {'cases': [{'status': 'pass', 'reason': 'cell_values_match'}]}}

    monkeypatch.setattr(backends, 'score', score)
    opened = []

    def panel(pinned, found, *, access):
        assert found == bench and access.unit == chain + '/test/' + event + '/' + bench
        opened.append(access.unit)
        return [deepcopy(task)], {'panel_hash': digest(task), 'excluded_without_pages': [], 'source_files': []}

    write_json(root / 'shared/consent.json', {'test_evaluation': True, 'sheet_test_qualification': True,
        'multi_arm_arms': list(read.ARMS), 'by': 'owner', 'date': '2026-11-06', 'note': 'Authored offline fixture.'})
    start = package.empty(step=chain + '/s0', evidence=EVIDENCE)
    stage = package.with_(start, step=chain + '/s5', add=[v225_cards.make_card(bench, CARD)])
    chosen = read.arms(stage, event, chain=chain, evidence=EVIDENCE)
    try:
        result = read.evaluate_unit(unit, event=event, run='authored', shared=root / 'shared', pinned=None,
            chain=chain, bench=bench, chosen=chosen, context=context, workers=1, canaries=[], panel=panel)
    finally:
        if chain == 'D':
            client.http.close()
    rows = [read_json(path) for path in (context.attempt / 'cells').glob('*.json')]
    count = len(read.labels(event)) * evaluation.TEST_RUNS
    assert opened and len(rows) == count
    assert {row['cell']['arm'] for row in rows} == set(read.labels(event))
    assert result['request_reuse'] == {'shared_cells': 0, 'dispatched_cells': count}
    assert result['structural_zero'] == 0
    assert all(row['shared_with'] is None and len(row['calls']) == 1 for row in rows)
    assert resources.lock.entries == count + (bench == 'alfworld') and resources.lock.depth == 0
    assert resources.nominal == [p.solver_tokens(p.CHAINS['D'], bench) if chain == 'D' else None] * count
    assert all(pool.depth == 0 for pool in resources.pools.values())
    assert not (context.attempt / 'transient').exists()
    if chain == 'D':
        assert len(gateway.bodies) == count
        assert all(body['thinking'] == {'type': 'disabled'} and body['reasoning_effort'] == 'none'
                   for body in gateway.bodies)
        requests = [(body['messages'][0]['content'], body['messages'][1]['content']) for body in gateway.bodies]
    assert len(requests) == count
    if event not in ('anchor', 'c_end'):
        assert all(CARD in system for system, _ in requests)
    if bench == 'alfworld':
        assert len(sessions) == count + 1 and all(session.closed for session in sessions)
        assert resources.pools[slots.EPISODE].entries == count + 1
        # main-v9 card-only/empty packages deliberately never start a sandbox.
        assert all(worker.package is None and worker.pings == 0 for worker in resources.workers)
    if bench == 'spreadsheetbench':
        assert len(native.prechecks) == len(native.cases) == count
        assert len(scorings) == count + 2  # two real qualification passes, then one score per cell
        assert len({row['position'] for row in scorings}) == count + 2
        assert all('/transient/' in row['artifact_dir'] for row in scorings if 'cell' in row['request'])


@pytest.mark.parametrize('configuration', [p.MAIN_V9, p.MAIN_V8, p.MAIN_V7])
@pytest.mark.parametrize('fail_reset', [False, True])
def test_alfworld_preparation_lock_and_episode_order(tmp_path, monkeypatch, configuration, fail_reset):
    """Real evaluate_unit -> alfworld_reset; fake sessions expose resource lifetime."""
    import fcntl
    from skillopt.execskill.chain import heavy_mode

    root = tmp_path / 'run'
    unit = 'G/test/anchor/alfworld'
    context, resources = production_context(root, StopEndpoint('G'), monkeypatch,
        attempt=root / unit / 'attempt-1', configuration=configuration)
    tasks = [task_for(root / str(index), 'alfworld') for index in range(2)]
    for index, task in enumerate(tasks):
        task['task_id'] += '-' + str(index)
    events = []
    locked = p.is_v225(configuration)
    original_environment, original_hold = context.environment, context.episodes.hold

    @contextmanager
    def environment(bench, found_unit):
        assert bench == 'alfworld' and found_unit == unit
        assert heavy_mode((bench,)) == fcntl.LOCK_SH
        assert resources.pools[slots.EPISODE].depth == 0
        with original_environment(bench, found_unit):
            events.append('environment_enter')
            try:
                yield
            finally:
                assert resources.pools[slots.EPISODE].depth == 0
                events.append('environment_exit')

    @contextmanager
    def episode():
        assert resources.lock.depth == int(locked)
        with original_hold():
            events.append('episode_enter')
            try:
                yield
            finally:
                assert events[-1] == 'close'
                events.append('episode_exit')

    context.environment = environment
    monkeypatch.setattr(context.episodes, 'hold', episode)
    opened = []

    def new_session(public, runtime):
        assert resources.lock.depth == int(locked)
        assert resources.pools[slots.EPISODE].depth == 1
        assert public == {'game_file': tasks[len(opened)]['public']['game_file']}
        assert runtime is context.runtime['alfworld']
        opened.append(public)
        events.append('open')

        def reset():
            events.append('reset')
            if fail_reset and len(opened) == 2:
                raise RuntimeError('authored reset failure')
            return ['Authored initial observation'], None, [{'admissible_commands': ['look']}]

        def close():
            assert resources.lock.depth == int(locked)
            assert resources.pools[slots.EPISODE].depth == 1
            events.append('close')

        return SimpleNamespace(reset=reset, close=close)

    monkeypatch.setattr(backends, '_new_alfworld', new_session)

    def panel(pinned, bench, *, access):
        assert bench == 'alfworld' and access.unit == unit
        return deepcopy(tasks), {'panel_hash': digest(tasks), 'excluded_without_pages': [], 'source_files': []}

    def prepared(own, jobs, **kwargs):
        assert not fail_reset
        assert resources.lock.depth == resources.pools[slots.EPISODE].depth == 0
        assert all('routing_view_sha256' in task['public'] for _, task, _ in jobs)
        events.append('cells')
        raise FirstCall()

    monkeypatch.setattr(cells, 'run_cells', prepared)
    write_json(root / 'shared/consent.json', {'test_evaluation': True, 'sheet_test_qualification': True,
        'multi_arm_arms': list(read.ARMS), 'by': 'owner', 'date': '2026-11-06', 'note': 'Authored offline fixture.'})
    with pytest.raises(cells.Pause):
        read.evaluate_unit(root / unit, event='anchor', run='authored', shared=root / 'shared', pinned=None,
            chain='G', bench='alfworld', chosen=read.arms(None, 'anchor', chain='G', evidence=EVIDENCE),
            context=context, workers=1, canaries=[], panel=panel)
    one_reset = ['episode_enter', 'open', 'reset', 'close', 'episode_exit']
    if locked:
        one_reset = ['environment_enter', *one_reset, 'environment_exit']
    assert events == one_reset * 2 + ([] if fail_reset else ['cells'])
    assert resources.lock.entries == 2 * int(locked)
    assert resources.pools[slots.EPISODE].entries == 2
    assert resources.lock.depth == resources.pools[slots.EPISODE].depth == 0


LEGACY_ENV = [name for name in p.CONFIGURATIONS if p.uses_environment_lock(name) and not p.is_v225(name)]


@pytest.mark.parametrize('configuration', LEGACY_ENV)
def test_legacy_environment_still_reconstructs_and_revalidates(tmp_path, monkeypatch, configuration):
    endpoint = StopEndpoint('G')
    context, resources = production_context(tmp_path, endpoint, monkeypatch, configuration=configuration)
    observed = []
    original = instruction_start.active_cards

    def active_cards(cards, found):
        observed.append((deepcopy(cards), found))
        return original(cards, found)

    monkeypatch.setattr(instruction_start, 'active_cards', active_cards)
    task = task_for(tmp_path, 'searchqa')
    unit = 'G/test/searchqa'
    cell = {'id': cells.cell_id(unit, 'C', task['task_id'], 0), 'unit': unit, 'arm': 'C',
            'benchmark': 'searchqa', 'task_id': task['task_id'], 'run': 0}
    arm = cells.Arm('card', package.empty(step='G/s0', evidence=EVIDENCE))
    with pytest.raises(FirstCall):
        cells.run_cell(context, cell, task, arm, store=SimpleNamespace(claim=lambda _: None))
    assert observed == [(context.cards, configuration)]
    assert context.environment is not None and resources.lock.depth == 0
    context.cards['searchqa'] = ''
    with pytest.raises(ValueError):
        cells.run_cell(context, cell, task, arm, store=SimpleNamespace(claim=lambda _: None))
    assert len(endpoint.requests) == 1


@pytest.mark.parametrize('bench', BENCHES)
@pytest.mark.parametrize('text', ['', 'unregistered guidance'])
def test_main_v9_chain_context_validation_remains_strict(tmp_path, monkeypatch, bench, text):
    context, _ = production_context(tmp_path, StopEndpoint('G'), monkeypatch)
    cards = {**context.cards, bench: text}
    with pytest.raises(ValueError, match='active cards'):
        instruction_start.active_cards(cards, p.MAIN_V9)
    with pytest.raises(ValueError, match='active cards'):
        replace(context, cards=cards)
