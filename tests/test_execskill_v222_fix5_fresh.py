"""Both measured probe cases use only their fresh root and their own cell cache."""
from collections import Counter
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
import shutil

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import profiles as p, reuse, units, v214_smoke, v214_stages
from skillopt.execskill import v222_cards as cards, v222_smoke as smoke
from skillopt.execskill.cells import Pause
from skillopt.validator_pilot.api import digest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v222_fix4_fresh import authored_cell
from tests.test_execskill_v222_gate import simple_inspector


def authored_s2(tmp_path, monkeypatch, chain, behavior, archive_state='kept', *, interrupt=False):
    old, archived, root = [tmp_path / name for name in ('old-smoke', 'archived-smoke', 'new-smoke')]
    old_cell = old / chain / 'v222-smoke/cross-narrowing/attempt-1/cells/old.json'
    old_cell.parent.mkdir(parents=True)
    old_cell.write_text('Authored unusable old probe receipt.')
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
        'partition': 'practice', 'public': {'question': 'Authored public quantity?',
        'context': 'Authored public evidence.'}, 'private': {}}
        for i in range(42 if bench == 'officeqa' else 20)] for bench in cards.BENCHES}
    harms = smoke.gate.harm_slices(pools)
    registration = {'decomposition': cards.decomposition_slices({bench: [row['task_id'] for row in rows]
        for bench, rows in pools.items()}), 'harm': smoke.gate.registration(harms),
        smoke.SUPPLY_FLAG: smoke.gate.practice_supply(pools)}
    selected = {bench: [next(row for row in pools[bench] if row['task_id'] == key)
        for key in draw['items']] for bench, draw in registration['decomposition'].items()}
    setting = units.Setting(run=digest(['fresh-authored-probes', chain, behavior]), root=root, shared=root/'shared',
        pools=pools, cards={bench: cards.format_text(bench) for bench in cards.BENCHES},
        runtime={bench: {} for bench in cards.BENCHES}, clients=None, budget=None, slots={}, sandbox={},
        evidence='engineering_fixture', extra={'configuration': p.MAIN_V8})
    monkeypatch.setattr(smoke, 'practice', lambda _: (deepcopy(selected), deepcopy(harms), deepcopy(registration)))
    monkeypatch.setattr(smoke, '_endpoint', lambda *_: None)
    monkeypatch.setattr(smoke, '_workers', lambda *_: lambda *args: nullcontext(None))
    monkeypatch.setattr(smoke.solver, 'routing_view', lambda bench, public, **kwargs: public)
    monkeypatch.setattr(reuse, 'signature', lambda *args, **kwargs:
        {'request_sha256': 'a' * 64, 'post_call': [], 'faults': []})
    # The production gate still decides fired pairs, harm, narrowing and rechecks.
    # This authored routing seam isolates the reported 42-item OfficeQA firing.
    monkeypatch.setattr(smoke.gate, 'inspect', lambda bench, before, after, rows, *args, **kwargs:
        simple_inspector(bench, before, after if bench == 'officeqa' else before, rows)
        | {'candidate_sha256': after.sha256})
    monkeypatch.setattr(v214_stages, 'fixture_pools', lambda *_:
        {bench: rows[:v214_smoke.S2_ITEMS[bench]] for bench, rows in pools.items()})
    sent, interrupted = [], []

    def token_for(unit, arm, key):
        if '/cross-narrowing/' not in unit:
            return 'pass'
        case = unit.split('/cross-narrowing/', 1)[1].split('/', 1)[0]
        # The prior single-case probe used cross-narrowing/officeqa for this
        # same benign response. Retain it so restoring that function fails
        # at its no-harm smoke requirement, not at this fixture's dispatch.
        if case == 'officeqa':
            case = 'benign'
        assert case in ('harmful_format', 'benign')
        i = int(key.rsplit('-', 1)[1])
        if case == 'harmful_format':
            return 'fail' if behavior == 'measured_harm' and arm == "S'" else 'pass'
        if chain == 'D' and behavior == 'measured_harm':
            return 'fail' if i < 12 and arm == "S'" else 'pass'
        # G's reported benign candidate: fixes 3, breaks 2, correctly accepted.
        if i < 3:
            return 'fail' if arm == 'S' else 'pass'
        if i < 5:
            return 'pass' if arm == 'S' else 'fail'
        return 'pass'

    def run(local, attempt, endpoint, unit, arms, schedule, tasks, *, tag):
        assert Path(attempt).is_relative_to(root)
        found = {}
        for arm, jobs in schedule.items():
            for key, _ in jobs:
                bench = smoke.rounds.bench_of(key)
                token = token_for(unit, arm, key)
                field = 'violation' if bench == 'alfworld' else 'grid' if bench == 'zebralogic' else smoke.COUNTERS[bench]
                row = authored_cell(unit, arm, key, token, field=field, counter=bench != 'alfworld')
                write_json(Path(attempt) / 'cells' / (row['cell']['id'] + '.json'), row)
                sent.append((unit, arm, key, token, Path(attempt).name))
                found[(arm, key)] = [row]
                if interrupt and '/cross-narrowing/benign/' in unit and not interrupted:
                    interrupted.append(True)
                    raise RuntimeError('Authored interruption after one persisted benign cell')
        return found

    monkeypatch.setattr(smoke.rounds, 'run_round', run)
    return setting, registration, sent


@pytest.mark.parametrize('chain', ['G', 'D'])
@pytest.mark.parametrize('behavior', ['measured_harm', 'no_harm'])
@pytest.mark.parametrize('archive_state', ['kept', 'removed'])
def test_fresh_s2_records_both_probe_cases_for_both_solver_behaviors(
        tmp_path, monkeypatch, chain, behavior, archive_state):
    setting, registration, sent = authored_s2(tmp_path, monkeypatch, chain, behavior, archive_state)
    value = smoke.s2(setting, chain)
    assert value['passed'] and smoke.check_bound_practice(value, registration) == value
    probe = value['cross_narrowing']
    assert set(probe['cases']) == {'harmful_format', 'benign'}
    assert probe['paired_item_calls'] == 2 * 42 * 2
    assert probe['narrowing_exercised'] is (behavior == 'measured_harm')
    assert probe['reason'] == (None if behavior == 'measured_harm' else 'no_measured_harm')
    assert len(sent) == 204 + 168 + 76
    assert len(list(setting.root.rglob('unit.json'))) == 12
    for case_name, case in probe['cases'].items():
        record = case['gate']; row = record['benches']['officeqa']
        assert record['paired_item_calls'] == 84 and row['fired'] == row['items'] == 42
        assert record['passed'] and record['decision'] == 'accept'
        if case_name == 'harmful_format' and behavior == 'measured_harm':
            assert row['fixed'] == 0 and row['broken'] == 42
        elif case_name == 'benign' and chain == 'D' and behavior == 'measured_harm':
            assert row['fixed'] == 0 and row['broken'] == 12
        elif case_name == 'benign':
            assert row['fixed'] == 3 and row['broken'] == 2 and row['net'] == 1
            assert row['whole_slice'] == 1 / 42
        else:
            assert row['fixed'] == row['broken'] == 0
        if row['net'] < 0:
            assert case['narrowing_exercised'] and case['reason'] is None
            assert record['narrowing']['benches'] == ['officeqa']
            assert record['narrowing']['additional_model_calls'] == 0
        else:
            assert case['narrowing_exercised'] is False and case['reason'] == 'no_measured_harm'
            assert record['narrowing'] is None and record['candidate_sha256'] == record['proposed_sha256']

    # Both candidates measure their own parent pairs; no cells cross case roots.
    ids = Counter((unit, arm, key) for unit, arm, key, _, _ in sent)
    assert set(ids.values()) == {1}
    probe_units = {unit for unit, *_ in sent if '/cross-narrowing/' in unit}
    assert probe_units == {chain + '/v222-smoke/cross-narrowing/' + case + '/officeqa'
                           for case in ('harmful_format', 'benign')}
    monkeypatch.setattr(smoke.rounds, 'run_round', lambda *_a, **_k: pytest.fail('Completed cases must be reused'))
    assert smoke.s2(setting, chain) == value


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_partial_benign_retry_reuses_only_its_own_cells_and_completed_harmful_case(tmp_path, monkeypatch, chain):
    setting, registration, sent = authored_s2(tmp_path, monkeypatch, chain, 'no_harm', interrupt=True)
    with pytest.raises(Pause, match='RuntimeError'):
        smoke.s2(setting, chain)
    case_root = setting.root / chain / 'v222-smoke/cross-narrowing'
    assert (case_root / 'harmful_format/unit.json').is_file()
    assert not (case_root / 'benign/unit.json').exists()
    prior_cells = [row for row in sent if '/cross-narrowing/' in row[0]]
    assert len(prior_cells) == 84 + 1
    write_json(case_root / 'benign/attempt-1/recovery.json',
               {'by': 'owner', 'date': '2026-11-04', 'decision': 'Resume this authored fixture only'})
    value = smoke.s2(setting, chain)
    assert value['passed'] and smoke.check_bound_practice(value, registration) == value
    probe_cells = [row for row in sent if '/cross-narrowing/' in row[0]]
    assert len(probe_cells) == 168
    assert len({(unit, arm, key) for unit, arm, key, *_ in probe_cells}) == 168
    assert all(attempt == 'attempt-1' for unit, *_, attempt in probe_cells if '/harmful_format/' in unit)
    benign = [row for row in probe_cells if '/benign/' in row[0]]
    assert Counter(row[-1] for row in benign) == {'attempt-1': 1, 'attempt-2': 83}
    assert value['cross_narrowing']['narrowing_exercised'] is False
    assert p.verified(read_json(case_root / 'benign/unit.json'), 'unit')['attempt'] == 'attempt-2'
