"""Authored callbacks exercise measured readiness without model, Docker or data access."""
from copy import deepcopy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json, write_json
from skillopt.validator_pilot.api import digest
from skillopt.execskill import profiles as p, smoke, v214_smoke, v214_stages, v222_cards as cards, v222_smoke as v
from skillopt.execskill.cells import Arm
from skillopt.execskill.package import empty
from skillopt.execskill.sandbox import client as sandbox
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


def scored(bench, *, passed=100, good=100):
    n = 20 if bench == 'alfworld' else 100
    field = 'violation' if bench == 'alfworld' else 'grid' if bench == 'zebralogic' else v.COUNTERS[bench]
    return [{'judge': {'v2': {'token': 'pass' if i < passed else 'fail'}, 'format': {field: i < good}},
             'final': {'token': 'pass' if i < passed else 'fail'}} for i in range(n)]


@pytest.mark.parametrize('bench', cards.BENCHES)
def test_measured_decomposition_keeps_full_denominators_and_both_measured_format_counters(bench):
    count = 20 if bench == 'alfworld' else 100
    calls = []
    def run(labels, package):
        calls.append(labels)
        return {label: scored(bench, passed=count, good=0 if bench == 'alfworld' else count) for label in labels}
    result = v.measure_decomposition(bench, list(range(count)), run,
                                     initial=cards.initial_package(evidence='engineering_fixture'))
    assert result['passed'] and result['decision'] == 'accept_split' and not result['fallback']
    assert result['new_model_cells'] == 2 * count and calls == [('C_hist', 'C')]
    assert result['historical'] == result['segmented']


def test_fallback_retains_historical_shell_without_an_extra_measured_arm():
    calls = []
    def run(labels, package):
        calls.append((labels, len(cards.own_segments(package, 'searchqa'))))
        return {label: scored('searchqa', passed=98 if label == 'C' and len(calls) == 1 else 100) for label in labels}
    result = v.measure_decomposition('searchqa', list(range(100)), run,
                                    initial=cards.initial_package(evidence='engineering_fixture'))
    assert result['passed'] and result['fallback'] and result['new_model_cells'] == 200
    assert result['decision'] == 'whole_card_fallback'
    assert calls == [(('C_hist', 'C'), 2)]
    assert 'fallback_check' not in result and 'fallback_cell_hashes' not in result


@pytest.mark.parametrize('bench', ['officeqa', 'spreadsheetbench', 'alfworld'])
def test_whole_card_fallback_continues_without_truncating_or_buying_another_comparison(bench):
    count = 20 if bench == 'alfworld' else 100
    calls = []
    def run(labels, package):
        calls.append(labels)
        return {label: scored(bench, passed=count if label == 'C_hist' else 0, good=0 if bench == 'alfworld' else count)
                for label in labels}
    result = v.measure_decomposition(bench, list(range(count)), run,
                                    initial=cards.initial_package(evidence='engineering_fixture'))
    assert result['passed'] and result['decision'] == 'whole_card_fallback'
    assert result['fallback'] and calls == [('C_hist', 'C')]
    assert result['new_model_cells'] == 2 * count


def test_format_regression_can_fail_an_accuracy_improvement_and_short_slices_refuse_calls():
    def run(labels, package):
        return {label: scored('officeqa', passed=90 if label == 'C_hist' else 100,
                              good=100 if label == 'C_hist' else 99) for label in labels}
    result = v.measure_decomposition('officeqa', list(range(100)), run,
                                    initial=cards.initial_package(evidence='engineering_fixture'))
    assert result['whole_slice_gain'] > 0 and result['passed'] and result['fallback']
    with pytest.raises(ValueError, match='denominator'):
        v.measure_decomposition('officeqa', list(range(99)), lambda *_: pytest.fail('no call'),
                                initial=cards.initial_package(evidence='engineering_fixture'), registered_count=100)


def signatures():
    signature = {'request_sha256': 'a' * 64, 'post_call': [], 'faults': []}
    return {str(i): {'C_hist': deepcopy(signature), 'C': deepcopy(signature)} for i in range(100)}


def test_exact_request_identity_allows_zero_call_neutral_zebra_check_only_with_complete_evidence():
    result = v.measure_decomposition('zebralogic', list(range(100)), lambda *_: pytest.fail('no call'),
        initial=cards.initial_package(evidence='engineering_fixture'), identity_pairs=signatures())
    assert result['passed'] and result['identity_proven'] and result['new_model_cells'] == 0
    pairs = signatures()
    pairs['0']['C']['request_sha256'] = 'b' * 64
    calls = []
    def run(labels, package):
        calls.append(labels)
        return {label: scored('zebralogic') for label in labels}
    result = v.measure_decomposition('zebralogic', list(range(100)), run,
        initial=cards.initial_package(evidence='engineering_fixture'), identity_pairs=pairs)
    assert result['passed'] and calls == [('C_hist', 'C')]


def decomposition_receipt():
    initial = cards.initial_package(evidence='engineering_fixture')
    slices = cards.decomposition_slices({b: [str(i) for i in range(100)] for b in cards.BENCHES})
    rows = {}
    for bench in cards.BENCHES:
        count = 20 if bench == 'alfworld' else 100
        row = v.measure_decomposition(bench, list(range(count)),
            lambda labels, package, bench=bench, count=count: {
                label: scored(bench, passed=count, good=0 if bench == 'alfworld' else count) for label in labels},
            initial=initial)
        rows[bench] = {**row, 'cards_sha256': digest(cards.manifest_pins()), 'slice_sha256': digest(slices[bench])}
    supply = v.gate.practice_supply({b: [{'task_id': str(i), 'public': {}} for i in range(100)] for b in cards.BENCHES})
    return {'configuration': p.MAIN_V8, 'benches': rows, 'slices': slices, 'fallbacks': [],
        v.SUPPLY_FLAG: supply, 'decomposition': {b: row['decision'] for b, row in rows.items()},
        'passed': True, 'new_model_cells': 840, 'cards_sha256': digest(cards.manifest_pins()), 'sealed_reads': 0}


@pytest.mark.parametrize('field', ['denominator', 'format', 'outcome', 'slice', 'cellhash', 'fallback'])
def test_decomposition_readiness_recomputes_measured_claims(field):
    value = decomposition_receipt()
    assert v.check_decomposition(value) == value
    row = value['benches']['searchqa']
    if field == 'denominator': row['items'] = 99
    elif field == 'format': row['segmented']['format']['tag_present'] = 99
    elif field == 'outcome': row['segmented']['passed'] = 90
    elif field == 'slice': value['slices']['searchqa']['items'][0] = 'other'
    elif field == 'cellhash': row['cell_hashes']['C'].pop()
    else: row['fallback'] = True
    with pytest.raises(ValueError):
        v.check_decomposition(value)


def test_structural_smoke_uses_source_pinned_home_predicates_and_inherits_all_previous_mechanisms(tmp_path):
    value = v214_stages.sx(tmp_path, configuration=p.MAIN_V8)
    assert v.check_structural(value) == value and value['segments']['enabled']['zebralogic'] == []
    assert value['inherited']['configuration'] == p.MAIN_V7
    value['segments']['enabled']['officeqa'].append(value['segments']['enabled']['searchqa'][0])
    with pytest.raises(ValueError, match='own seed'):
        v.check_structural(value)


def test_schedule_changes_only_main_v8_and_prices_c0_instead_of_historical_card():
    parent, child = v214_smoke.schedule(p.MAIN_V7), v214_smoke.schedule(p.MAIN_V8)
    assert child['S2_arms'] == ['C0'] and parent['S2_arms'] == ['C']
    assert child['decomposition']['items']['alfworld'] == 20
    assert child['decomposition']['items']['zebralogic'] == 100
    assert child['decomposition']['once'] and child['cross_narrowing']['actual_fired_pairs_required']
    assert child['maximum_schedule'] == v214_stages.manifest_identity(p.MAIN_V8)


@pytest.mark.parametrize('worker_configuration', [p.MAIN_V8, p.ZEBRA_PC_V15, None])
def test_s0_worker_selftest_selects_and_binds_the_isolated_instruction_worker(tmp_path, monkeypatch, worker_configuration):
    seen = []
    monkeypatch.setattr(smoke, '_escape_report', lambda *a, **k: {})
    monkeypatch.setattr(smoke, 'escape_rows', lambda *_: {'authored': True})
    monkeypatch.setattr(smoke, 'view_bytes', lambda *_: {'items': 1, 'p99': 100})
    def worker(**options):
        seen.append(options)
        found = SimpleNamespace(ping=lambda: {'vsz_kib': 1, 'rss_kib': 2,
            'worker_sha256': sandbox.worker_sha256(configuration=worker_configuration)}, close=lambda: None)
        return SimpleNamespace(start=lambda *a, **k: found)
    if worker_configuration == p.MAIN_V8:
        value = smoke.sandbox_selftest(tmp_path, item_files=[], docker=object(), worker=worker, configuration=p.MAIN_V8)
        assert value['configuration'] == p.MAIN_V8 and value['passed']
        assert seen[0]['instruction_configuration'] == p.MAIN_V8
    else:
        with pytest.raises(ValueError, match='selftest executed'):
            smoke.sandbox_selftest(tmp_path, item_files=[], docker=object(), worker=worker, configuration=p.MAIN_V8)


def test_partial_decomposition_retry_reuses_completed_historical_cells(tmp_path, monkeypatch):
    initial = empty(step='G/s0', evidence='engineering_fixture')
    local = SimpleNamespace(run='a' * 64, workers=3)
    # replace(local, workers=1) must use a dataclass as production Setting does.
    from dataclasses import make_dataclass
    local = make_dataclass('Local', [('run', str), ('workers', int)])('a' * 64, 3)
    unit, key = 'G/v222-smoke/decomposition/searchqa', 'searchqa/authored'
    tasks = {key: {'public': {'question': 'authored'}, 'private': {}}}
    arms = {label: Arm('card', initial) for label in ('C_hist', 'C')}
    sent = []
    def run(local, attempt, endpoint, name, arms, schedule, tasks, *, tag):
        result = {}
        for label, jobs in schedule.items():
            for key, _ in jobs:
                sent.append(label)
                cell = {'id': label, 'unit': name, 'arm': label, 'task_id': key, 'run': 0}
                row = p.record('cell', 'engineering_fixture', {'cell': cell, 'stop': None, 'faults': [],
                    'final': {'outcome': 'pass', 'token': 'pass', 'kind': 'answer', 'remedy': None},
                    'judge': {'v2': {'token': 'pass'}}})
                write_json(Path(attempt) / 'cells' / (label + '.json'), row)
                result[(label, key)] = [row]
        return result
    monkeypatch.setattr(v.rounds, 'run_round', run)
    attempt = tmp_path / 'attempt-1'
    assert len(v._practice_round(local, attempt, None, unit, arms, tasks, tag='decomposition')) == 2
    (attempt / 'cells/C.json').unlink()
    sent.clear()
    result = v._practice_round(local, tmp_path / 'attempt-2', None, unit, arms, tasks, tag='decomposition')
    assert len(result) == 2 and sent == ['C']
    with pytest.raises(ValueError, match='original request inputs'):
        v._practice_round(local, tmp_path / 'attempt-3', None, unit, arms, {key: {'public': {}, 'private': {}}}, tag='decomposition')


def test_cli_accepts_main_v8_practice_supply_without_repurposing_older_defaults():
    from scripts.run_execskill import parser
    args = parser().parse_args(['v214-selftest', '--configuration', p.MAIN_V8, '--out', '/authored',
        '--preparation', '/authored/s0.json', '--zebra-pool', '/authored/pool.json',
        '--zebra-split-manifest', '/authored/inventory.json', '--v222-practice-supply', '/authored/practice.json'])
    assert args.configuration == p.MAIN_V8 and args.v222_practice_supply == '/authored/practice.json'


def cross_probe_receipt(record, *, benign=None, harm_registration_sha256='a' * 64):
    """Authored readiness records; the second proposal has an independent identity.

    These schema fixtures replay authored counts. Actual two-case dispatch and
    separate persisted cells are exercised by the probe and fresh-root tests.
    """
    if benign is None:
        fields = {key: deepcopy(row) for key, row in record.items()
                  if key not in ('version', 'evidence', p.RECORD_HASH)}
        fields['proposed_sha256'] = digest([record['proposed_sha256'], 'authored-second-proposal'])
        fields['candidate_sha256'] = (fields['proposed_sha256'] if fields['narrowing'] is None else
                                      digest([record['candidate_sha256'], 'authored-second-proposal']))
        if fields['narrowing'] is not None:
            fields['narrowing']['candidate_sha256'] = fields['candidate_sha256']
        benign = p.record('v222-cross-gate', 'engineering_fixture', fields)
    cases = {}
    for name, gate in (('harmful_format', record), ('benign', benign)):
        narrowed = gate['narrowing'] is not None
        segment = v.probe_segment(name, evidence='engineering_fixture')
        cases[name] = {'passed': gate['passed'], 'gate': deepcopy(gate),
            'probe_source_sha256': hashlib.sha256(segment.source.encode()).hexdigest(),
            'narrowing_exercised': narrowed, 'reason': None if narrowed else 'no_measured_harm',
            'sealed_reads': 0}
    narrowed = any(case['narrowing_exercised'] for case in cases.values())
    return {'passed': all(case['passed'] for case in cases.values()), 'cases': cases,
        'narrowing_exercised': narrowed, 'reason': None if narrowed else 'no_measured_harm',
        'paired_item_calls': sum(case['gate']['paired_item_calls'] for case in cases.values()),
        'call_bound': 2 * v.gate.MAX_PAIRED_ITEM_CALLS,
        'harm_registration_sha256': harm_registration_sha256, 'sealed_reads': 0}


def cross_receipt():
    from tests.test_execskill_v222_gate import packages, pools, paired, simple_inspector
    parent, candidate = packages()
    _, record = v.gate.check(home='searchqa', parent=parent, candidate=candidate,
        slices=v.gate.harm_slices(pools()), inspector=simple_inspector,
        run_pairs=lambda bench, a, b, rows: paired(rows, harmful=bench == 'officeqa'), phase='confirmation')
    return cross_probe_receipt(record)


@pytest.mark.parametrize('change', ['none', 'no-calls', 'inert-claim', 'no-harm', 'wrong-count', 'no-recheck'])
def test_measured_readiness_recomputes_cross_harm_counts_and_bounded_narrowing(change):
    value = {'passed': True, 'decomposition': decomposition_receipt(), 'cross_narrowing': cross_receipt()}
    case = value['cross_narrowing']['cases']['harmful_format']
    record = case['gate']
    if change == 'none':
        assert v.check_measured(value) == value
        return
    fields = {key: deepcopy(row) for key, row in record.items() if key not in ('version', 'evidence', p.RECORD_HASH)}
    if change == 'no-calls': fields['paired_item_calls'] = 0
    elif change == 'inert-claim': fields['benches']['officeqa']['paired_item_calls'] = 0
    elif change == 'no-harm': fields['benches']['officeqa']['broken'] = 0
    elif change == 'wrong-count': fields['benches']['officeqa']['items'] = 59
    else: fields['narrowing']['rechecked'].pop('alfworld')
    case['gate'] = p.record('v222-cross-gate', 'engineering_fixture', fields)
    with pytest.raises(ValueError):
        v.check_measured(value)


def test_cross_probe_dispatches_only_canonical_fired_cells_then_measures_narrowing(tmp_path, monkeypatch):
    from dataclasses import make_dataclass
    from tests.test_execskill_v222_gate import pools, simple_inspector
    Setting = make_dataclass('Setting', [('root', object), ('run', str), ('evidence', str), ('workers', int), ('runtime', dict)])
    setting = Setting(tmp_path, 'a' * 64, 'engineering_fixture', 3, {b: {} for b in cards.BENCHES})
    slices = v.gate.harm_slices(pools())
    monkeypatch.setattr(v, 'practice', lambda _: ({}, slices, {'harm': v.gate.registration(slices)}))
    monkeypatch.setattr(v.units, 'for_unit', lambda setting, *a: setting)
    monkeypatch.setattr(v.units, 'drainer', lambda *a: None)
    monkeypatch.setattr(v.units, 'run_unit', lambda path, **kw: {'result': kw['work'](path / 'attempt-1')})
    monkeypatch.setattr(v, '_endpoint', lambda *a: None)
    monkeypatch.setattr(v, '_workers', lambda *a: None)
    monkeypatch.setattr(v.gate, 'inspect', lambda b, a, c, rows, *x, **kw: simple_inspector(b, a, c, rows))
    calls = []
    def run(local, attempt, endpoint, unit, arms, schedule, tasks, *, tag):
        result = {}
        for arm, jobs in schedule.items():
            for key, _ in jobs:
                bench = v.rounds.bench_of(key)
                calls.append((bench, arm))
                result[(arm, key)] = [{'final': {'token': 'pass' if bench == 'officeqa' and arm == 'S' else 'fail'},
                                       'stop': None}]
        return result
    monkeypatch.setattr(v.rounds, 'run_round', run)
    result = v.cross_probe(setting, 'G')
    assert result['passed'] and result['narrowing_exercised']
    assert len(calls) == result['paired_item_calls'] == 800
    assert set(result['cases']) == {'harmful_format', 'benign'}
    for case in result['cases'].values():
        assert case['gate']['paired_item_calls'] == 400
        assert case['gate']['narrowing']['benches'] == ['officeqa']
        assert case['gate']['narrowing']['additional_model_calls'] == 0


@pytest.mark.parametrize('chain', ['G', 'D'])
def test_main_v8_stage_runner_dispatches_actual_s1_then_child_s2_and_reuses_the_receipt(tmp_path, monkeypatch, chain):
    from skillopt.coevo5.budget import Budget
    from skillopt.execskill import manifest, units, v29_route_probe
    value = {p.RECORD_HASH: 'a' * 64, 'root': str(tmp_path), 'configuration': p.MAIN_V8, 'evidence': 'smoke',
        'data': {'launchable_chains': [chain], 'snapshot_sha256': 'b' * 64, 's0_sha256': 'c' * 64,
                 'v214_s0': {'passed': True}}}
    setting = units.Setting('a' * 64, tmp_path, tmp_path / 'shared', {}, {}, {}, None,
        Budget(tmp_path / 'ledger'), {}, {}, 'engineering_fixture',
        extra={'configuration': p.MAIN_V8})
    monkeypatch.setattr(manifest, 'load', lambda *a, **kw: value)
    monkeypatch.setattr(v214_stages.chains, 'first_call', lambda *_: {'passed': True, p.RECORD_HASH: 'd' * 64})
    monkeypatch.setattr(v29_route_probe, 'measure', lambda *a, **kw:
        {'passed': True, 'route': 'B', 'longest': 60000})
    invoked = []
    def child_s2(found, selected):
        invoked.append((p.configuration_of(found), selected, found.branch, found.longest))
        return {'passed': True, 'configuration': p.MAIN_V8, 'child_decomposition_entry': True}
    monkeypatch.setattr(v, 's2', child_s2)
    for stage in ('S0', 'S1', 'S2'):
        first = v214_smoke.run_stage(tmp_path / 'authored-manifest', chain, stage,
                                    _setting=setting, configuration=p.MAIN_V8)
        assert first['configuration'] == p.MAIN_V8
        assert first == v214_smoke.run_stage(tmp_path / 'authored-manifest', chain, stage,
                                            _setting=setting, configuration=p.MAIN_V8)
    assert first['result']['child_decomposition_entry']
    assert invoked == [(p.MAIN_V8, chain, 'N' if chain == 'D' else None, 60000 if chain == 'D' else None)]
    assert set(first['result']['solver_bounds']['ledger_bound']) == set(cards.BENCHES)
