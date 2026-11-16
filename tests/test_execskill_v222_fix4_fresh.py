"""Fresh main-v8 S2 roots need only new authored cells, never archived receipts."""
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import shutil

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import profiles as p, reuse, units, v214_smoke, v214_stages
from skillopt.execskill import v222_cards as cards, v222_smoke as smoke
from skillopt.execskill.cells import Arm
from skillopt.execskill.package import empty
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v222_gate import simple_inspector


def authored_cell(unit, arm, key, token, *, field, counter):
    bench = smoke.rounds.bench_of(key)
    outcome = 'unknown' if token.startswith('unknown') else token
    return p.record('cell', 'engineering_fixture', {
        'cell': {'id': digest([unit, arm, key]), 'unit': unit, 'benchmark': bench,
                 'arm': arm, 'task_id': key, 'run': 0},
        'stop': None, 'faults': [], 'enabled': [], 'sends': [],
        'final': {'outcome': outcome, 'token': token, 'kind': 'authored_answer', 'remedy': None},
        'judge': {'v2': {'token': token}, 'format': {field: counter}}})


@pytest.mark.parametrize('chain', ['G', 'D'])
@pytest.mark.parametrize('archive_state', ['kept', 'removed'])
def test_fresh_s2_uses_new_unknown_cells_without_reading_archived_roots(tmp_path, monkeypatch, chain, archive_state):
    old, archived, root = [tmp_path / name for name in ('old-smoke', 'archived-smoke', 'new-smoke')]
    old_cell = old / chain / 'v222-smoke/decomposition/spreadsheetbench/attempt-1/cells/old.json'
    old_cell.parent.mkdir(parents=True)
    old_cell.write_text('Authored unusable old receipt; never a source for this run.')
    old.rename(archived)
    if archive_state == 'removed':
        shutil.rmtree(archived)
    for method in ('read_bytes', 'read_text'):
        original = getattr(Path, method)
        def guarded(path, *args, original=original, **kwargs):
            assert not path.is_relative_to(old) and not path.is_relative_to(archived), 'Archived roots stay unread'
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, method, guarded)

    pools = {bench: [{'task_id': '%s-%02d' % (bench, i), 'benchmark': bench,
        'partition': 'practice', 'public': {'question': 'Authored public question.'}, 'private': {}}
        for i in range(20)] for bench in cards.BENCHES}
    harm = smoke.gate.harm_slices(pools)
    registration = {'decomposition': cards.decomposition_slices({bench: [row['task_id'] for row in rows]
        for bench, rows in pools.items()}), 'harm': smoke.gate.registration(harm),
        smoke.SUPPLY_FLAG: smoke.gate.practice_supply(pools)}
    selected = {bench: [next(row for row in pools[bench] if row['task_id'] == key)
        for key in draw['items']] for bench, draw in registration['decomposition'].items()}
    setting = units.Setting(run=digest(['new-authored-run', chain]), root=root, shared=root/'shared',
        pools=pools, cards={bench: cards.format_text(bench) for bench in cards.BENCHES},
        runtime={bench: {} for bench in cards.BENCHES}, clients=None, budget=None, slots={}, sandbox={},
        evidence='engineering_fixture', extra={'configuration': p.MAIN_V8})
    monkeypatch.setattr(smoke, 'practice', lambda _: (deepcopy(selected), deepcopy(harm), deepcopy(registration)))
    monkeypatch.setattr(smoke, '_endpoint', lambda *_: None)
    monkeypatch.setattr(smoke, '_workers', lambda *_: lambda *args: nullcontext(None))
    monkeypatch.setattr(smoke.solver, 'routing_view', lambda bench, public, **kwargs: public)
    monkeypatch.setattr(reuse, 'signature', lambda *args, **kwargs:
        {'request_sha256': 'a' * 64, 'post_call': [], 'faults': []})
    monkeypatch.setattr(smoke.gate, 'inspect', lambda bench, before, after, rows, *args, **kwargs:
        simple_inspector(bench, before, after, rows))
    monkeypatch.setattr(v214_stages, 'fixture_pools', lambda *_:
        {bench: rows[:v214_smoke.S2_ITEMS[bench]] for bench, rows in pools.items()})
    sent = []

    def run(local, attempt, endpoint, unit, arms, schedule, tasks, *, tag):
        assert Path(attempt).is_relative_to(root)
        found = {}
        for arm, jobs in schedule.items():
            for key, _ in jobs:
                bench = smoke.rounds.bench_of(key)
                field = 'violation' if bench == 'alfworld' else 'grid' if bench == 'zebralogic' else smoke.COUNTERS[bench]
                token = 'unknown' if bench in ('officeqa', 'spreadsheetbench') else 'pass'
                if '/cross-narrowing/' in unit and bench == 'officeqa' and arm == 'S':
                    token = 'pass'
                counter = None if token == 'unknown' else bench != 'alfworld'
                row = authored_cell(unit, arm, key, token, field=field, counter=counter)
                write_json(Path(attempt) / 'cells' / (row['cell']['id'] + '.json'), row)
                sent.append((unit, arm, key, token))
                found[(arm, key)] = [row]
        return found

    monkeypatch.setattr(smoke.rounds, 'run_round', run)
    result = smoke.s2(setting, chain)
    assert result['passed'] and smoke.check_measured(result) == result
    assert result['decomposition']['new_model_cells'] == 4 * 20 * 2  # Zebra uses its exact identity.
    assert result['cross_narrowing']['narrowing_exercised']
    for case in result['cross_narrowing']['cases'].values():
        assert case['gate']['narrowing']['benches'] == ['officeqa']
        assert case['gate']['benches']['spreadsheetbench']['net'] == 0
    assert result['cells'] == sum(v214_smoke.S2_ITEMS.values()) == 76
    assert len(sent) == 160 + 2 * 160 + 76
    for bench in ('officeqa', 'spreadsheetbench'):
        row = result['decomposition']['benches'][bench]
        assert row['historical']['passed'] == row['segmented']['passed'] == 20
        assert row['decision'] == 'accept_split'
        assert result['benches'][bench]['passed']
    receipts = list(root.rglob('unit.json'))
    assert len(receipts) == 12
    assert all(p.verified(read_json(path), 'unit')['run'] == setting.run for path in receipts)
    stored_cells = list(root.rglob('cells/*.json'))
    assert len(stored_cells) == len(sent)
    assert all('/attempt-1/' in str(path) for path in stored_cells)

    # Completion reuse remains local to this new root, with no second fake call.
    before = list(sent)
    monkeypatch.setattr(smoke.rounds, 'run_round', lambda *_args, **_kwargs: pytest.fail('Completed new units are reused'))
    assert smoke.s2(setting, chain) == result and sent == before


@pytest.mark.parametrize('token', ['unknown', 'unknown_artifact'])
def test_practice_retry_reuses_complete_unknown_receipts(tmp_path, monkeypatch, token):
    @dataclass
    class Local:
        run: str = 'a' * 64
        workers: int = 2
    unit, key = 'G/v222-smoke/decomposition/spreadsheetbench', 'spreadsheetbench/authored'
    package = empty(step='G/s0', evidence='engineering_fixture')
    arms = {label: Arm('card', package) for label in ('C_hist', 'C')}
    tasks = {key: {'public': {}, 'private': {}}}
    sent = []
    def run(local, attempt, endpoint, name, selected, schedule, tasks, *, tag):
        found = {}
        for arm, jobs in schedule.items():
            for task, _ in jobs:
                row = authored_cell(name, arm, task, token, field='program_delivered', counter=None)
                write_json(Path(attempt) / 'cells' / (arm + '.json'), row)
                sent.append(arm)
                found[(arm, task)] = [row]
        return found
    monkeypatch.setattr(smoke.rounds, 'run_round', run)
    expected = smoke._practice_round(Local(), tmp_path/'attempt-1', None, unit, arms, tasks, tag='authored')
    assert sent == ['C_hist', 'C']
    monkeypatch.setattr(smoke.rounds, 'run_round', lambda *_args, **_kwargs: pytest.fail('A complete unknown is reusable'))
    assert smoke._practice_round(Local(), tmp_path/'attempt-2', None, unit, arms, tasks, tag='authored') == expected
