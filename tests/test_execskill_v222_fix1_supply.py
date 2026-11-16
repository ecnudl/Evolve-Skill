"""D1 actual practice denominators, acceptance isolation and measured bindings."""
from copy import deepcopy
from types import SimpleNamespace
import hashlib
import tempfile
from pathlib import Path

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import profiles as p, v222_cards as cards, v222_gate as gate
from skillopt.execskill import v222_runtime as runtime, v222_smoke as smoke
from skillopt.validator_pilot.api import digest
from tests.test_execskill_v222_gate import packages, paired, simple_inspector
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

AVAILABLE = {'searchqa': 104, 'officeqa': 34, 'zebralogic': 19, 'spreadsheetbench': 51, 'alfworld': 18}


def source(counts=None):
    counts = counts or AVAILABLE
    pools = {bench: [{'task_id': bench + '-%03d' % i, 'benchmark': bench, 'partition': 'practice',
        'public': {'question': 'Authored public question.'}, 'private': {'answer': 'authored'}}
        for i in range(n + 2)] for bench, n in counts.items()}
    allocations = {bench: {'slices': {'run': [r['task_id'] for r in rows[:5]],
        'confirm-r1': [r['task_id'] for r in rows[5:-2]],
        'accept': [r['task_id'] for r in rows[-2:]]}} for bench, rows in pools.items()}
    from tests.execskill_v222_fakes import alf_rows
    pools['alfworld'], runtime = alf_rows(pools['alfworld'], Path(tempfile.mkdtemp(prefix='alf-games-')))
    return {'data': {'pools': pools}, 'allocations': allocations, 'protected_ids': {},
            'runtime': {'alfworld': runtime}}


def prepared(monkeypatch, imported=None, **kwargs):
    imported = imported or source()
    monkeypatch.setattr(smoke.manifest, '_items', lambda rows, bench: deepcopy(rows))
    return smoke.prepare_practice(imported, **kwargs)


def receipt(registration):
    initial = cards.initial_package(evidence='engineering_fixture')
    found = {}
    for bench in cards.BENCHES:
        count = registration[smoke.SUPPLY_FLAG]['benches'][bench]['decomposition_items']
        field = 'violation' if bench == 'alfworld' else 'grid' if bench == 'zebralogic' else smoke.COUNTERS[bench]
        def run(labels, package, field=field, bench=bench, count=count):
            return {label: [{'judge': {'v2': {'token': 'pass'},
                'format': {field: bench != 'alfworld'}}} for _ in range(count)] for label in labels}
        row = smoke.measure_decomposition(bench, list(range(count)), run, initial=initial, registered_count=count)
        found[bench] = {**row, 'cards_sha256': digest(cards.manifest_pins()),
                       'slice_sha256': digest(registration['decomposition'][bench])}
    return {'configuration': p.MAIN_V8, 'benches': found, 'slices': registration['decomposition'],
        'fallbacks': [], 'passed': True, 'new_model_cells': sum(row['new_model_cells'] for row in found.values()),
        'cards_sha256': digest(cards.manifest_pins()), smoke.SUPPLY_FLAG: registration[smoke.SUPPLY_FLAG],
        'decomposition': {b: row['decision'] for b, row in found.items()}, 'sealed_reads': 0}


def test_available_counts_register_without_extra_supply_and_allow_confirmation_and_overlap(monkeypatch):
    imported = source(); found = prepared(monkeypatch, imported)
    assert found['supply_pins'] == {} and found['supply_manifest'] is None
    supplied = found[smoke.SUPPLY_FLAG]
    assert supplied['minimum_available'] == 18 and supplied['decomposition_harm_overlap_allowed']
    for bench, n in AVAILABLE.items():
        row = supplied['benches'][bench]
        assert row == {'available': n, 'decomposition_items': min(n, 20 if bench == 'alfworld' else 100),
                       'harm_items': min(n, gate.HARM_ITEMS[bench]), 'acceptance_excluded': 2}
        old = imported['allocations'][bench]['slices']
        harm = set(found['harm']['benches'][bench]['task_ids'])
        decomposition = set(found['decomposition'][bench]['items'])
        assert not (harm | decomposition) & set(old['accept'])
        assert harm & set(old['confirm-r1'])
        assert harm & decomposition
        assert found['harm']['benches'][bench]['items'] == row['harm_items']


@pytest.mark.parametrize('bench', cards.BENCHES)
def test_available_floor_stops_preparation_at_seventeen(monkeypatch, bench):
    counts = {**AVAILABLE, bench: 17}
    with pytest.raises(ValueError, match='practice_supply below minimum available 18 for ' + bench):
        prepared(monkeypatch, source(counts))


def test_optional_pinned_supply_adds_to_original_practice_and_remains_optional(tmp_path, monkeypatch):
    imported = source()
    rows = [{'task_id': 'extra-%d' % i, 'benchmark': 'officeqa', 'partition': 'development',
        'public': {'question': 'Authored extra question.'}, 'private': {'answer': 'authored'}} for i in range(5)]
    path = tmp_path / 'extra-practice.json'; write_json(path, rows)
    pins = {'officeqa': {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}}
    specification = tmp_path / 'supply.json'
    write_json(specification, {'configuration': p.MAIN_V8, 'pools': pins})
    found = prepared(monkeypatch, imported, supply_file=specification)
    assert found[smoke.SUPPLY_FLAG]['benches']['officeqa']['available'] == 39
    assert found['decomposition']['officeqa']['count'] == found['harm']['benches']['officeqa']['items'] == 39
    assert found['supply_pins'] == pins


def test_actual_registration_is_seeded_and_runtime_rejects_changed_counts(tmp_path, monkeypatch):
    imported = source(); found = prepared(monkeypatch, imported)
    reversed_source = deepcopy(imported)
    for rows in reversed_source['data']['pools'].values(): rows.reverse()
    assert prepared(monkeypatch, reversed_source) == found
    setting = SimpleNamespace(shared=tmp_path / 'shared', pools=imported['data']['pools'], runtime=imported['runtime'],
        extra={'configuration': p.MAIN_V8, 'v211_allocation': imported['allocations'], 'v222_practice': found})
    slices, registered = runtime.preflight(setting)
    assert registered == found['harm']
    assert len(slices['officeqa']) == 34 and len(slices['alfworld']) == 18
    setting.extra['v222_practice'][smoke.SUPPLY_FLAG]['benches']['officeqa']['available'] += 1
    with pytest.raises(ValueError, match='actual main-v8 practice counts changed'):
        runtime.preflight(setting)


def test_measured_readiness_uses_registered_actual_counts_and_whole_slice_denominator(monkeypatch):
    imported = source(); registered = prepared(monkeypatch, imported)
    decomposition = receipt(registered)
    assert smoke.check_decomposition(decomposition) == decomposition
    carrier = SimpleNamespace(pools=imported['data']['pools'], extra={'v211_allocation': imported['allocations']})
    available, excluded = runtime._training_allocations(carrier)
    slices = gate.harm_slices(available, excluded=excluded)
    parent, candidate = packages()
    _, record = gate.check(home='searchqa', parent=parent, candidate=candidate, slices=slices,
        inspector=simple_inspector, run_pairs=lambda bench, a, b, rows: paired(rows, harmful=bench == 'officeqa'),
        phase='confirmation', registered_counts={b: row['items'] for b, row in registered['harm']['benches'].items()})
    assert record['benches']['officeqa']['items'] == 34
    assert record['benches']['officeqa']['whole_slice'] == -1.0
    from tests.test_execskill_v222_smoke import cross_probe_receipt
    probe = cross_probe_receipt(record)
    value = {'passed': True, 'decomposition': decomposition, 'cross_narrowing': probe}
    assert smoke.check_measured(value) == value
    fields = {k: deepcopy(v) for k, v in record.items() if k not in ('version', 'evidence', p.RECORD_HASH)}
    fields['benches']['officeqa']['items'] = 60
    probe['cases']['harmful_format']['gate'] = p.record('v222-cross-gate', 'engineering_fixture', fields)
    with pytest.raises(ValueError, match='Cross smoke requires outcomes'):
        smoke.check_measured(value)
    mismatch = {b: len(rows) for b, rows in slices.items()}; mismatch['officeqa'] = 35
    with pytest.raises(ValueError, match='registered actual practice denominator'):
        gate.check(home='searchqa', parent=parent, candidate=candidate, slices=slices,
            inspector=lambda *_: pytest.fail('No routing before count validation'), run_pairs=None,
            phase='confirmation', registered_counts=mismatch)


def test_measured_decomposition_requires_its_registered_actual_n(monkeypatch):
    found = receipt(prepared(monkeypatch))
    found['benches']['officeqa']['items'] = 35
    with pytest.raises(ValueError, match='actual decomposition denominator'):
        smoke.check_decomposition(found)
