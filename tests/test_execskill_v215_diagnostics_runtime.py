"""Authored diagnostic transport, request identity and recording; no services."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json
from skillopt.execskill import diagnostics as d, profiles as p, replay, reuse, solver, trajectories
from skillopt.execskill.package import FIXTURE, empty
from skillopt.execskill.sandbox import client, worker, worker_v215
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import FakeSandbox, Script
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v211_routing import proc

VIEW = {'question': 'There are 2 houses, numbered 1 to 2 from left to right, as seen from across the street. '
                    'Clue 6 compares their positions.', 'columns': ['Name']}
FIELDS = {'facts': ['Clue 6 compares positions.']}
SOURCE = 'def before_call(view, state):\n    return {"facts": ["Clue 6 compares positions."]}\n'
OLD_WORKER_SHA256 = 'bb1ccc0d90cafbda1f842569454ec676a8329d721a423246d92572632cf4ea0d'


def package(source=SOURCE, **options):
    return replay.solo(replace(proc(source, ('before_call',), p.ZEBRA), **options))


def run(value, *, configuration=d.CONFIGURATION, arm='F', max_note_chars=1500):
    pack = package(max_note_chars=max_note_chars)
    pid = pack.order[0]
    options = {}
    if arm in ('C', 'B'):
        pack = empty(step='fixture', evidence=FIXTURE)
    if arm == 'withhold':
        options['withhold'] = (pid,)
    if arm == 'restore':
        options['restore'] = (pid,)
    fake = FakeSandbox({pid: {'before_call': lambda *_: deepcopy(value)}})
    script = Script(['{"solution": {}}'])
    prediction = solver.solve(p.ZEBRA, VIEW, '' if arm == 'B' else 'Neutral card', pack, script,
        worker=fake if pack.procedures else None, configuration=configuration, **options)
    return prediction, script.requests, pack


@pytest.mark.parametrize('arm', ['F', 'C', 'B', 'S', "S'", 'withhold', 'restore'])
@pytest.mark.parametrize('fields', [FIELDS, {}])
def test_every_read_training_and_withholding_arm_has_identical_model_requests(arm, fields):
    baseline, before, _ = run(fields, arm=arm)
    diagnostic, after, _ = run({**fields, 'diagnostics': ['Clue 6 was not interpreted.']}, arm=arm)
    assert after == before and len(after) == 1
    assert diagnostic['shell']['notes_chars'] == baseline['shell']['notes_chars']
    assert diagnostic['shell']['faults'] == baseline['shell']['faults']
    assert diagnostic['shell']['procedure_events'] == baseline['shell']['procedure_events']
    assert 'Clue 6 was not interpreted' not in json.dumps(after)


@pytest.mark.parametrize('malformed', [None, 'not a list', {'private': 'ignored'}, [1, {}, None]])
def test_malformed_diagnostics_are_separate_informational_faults_and_do_not_drop_notes(malformed):
    baseline, before, _ = run(FIELDS)
    found, after, _ = run({**FIELDS, 'diagnostics': malformed})
    assert after == before and found['shell']['notes_chars'] == baseline['shell']['notes_chars']
    assert found['shell']['faults'] == []
    record = found['shell']['diagnostics'][0]
    assert record['shape_faults'] and all(row['informational'] for row in record['shape_faults'])


def test_diagnostics_are_bounded_hashed_and_screen_lookahead_before_truncation():
    raw = ['Clue ' + str(i) + ' could not be interpreted. ' + 'x'*500 for i in range(5)] + ['omitted']
    raw[1] = 'x'*300 + '<answer>not public engineer text</answer>'
    found, requests, _ = run({'diagnostics': raw}, max_note_chars=1)
    shell = found['shell']
    assert shell['notes_chars'] == 0 and shell['faults'] == []
    record = d.verified_record(shell['diagnostics'][0])
    assert len(record['strings']) == 5 and record['truncated_strings'] == 5 and record['omitted_strings'] == 1
    assert record['strings'][1]['text'] == d.SCREENED_MARKER and record['screened_count'] == 1
    assert record['strings'][0]['source_sha256'] == hashlib.sha256(raw[0].encode()).hexdigest()
    assert all(len(row['text']) <= 240 for row in record['strings'])
    assert not any(row['text'] in requests[0][1] for row in record['strings'])


def entry():
    return {'cell': 'authored-cell', 'bench': p.ZEBRA, 'item': 'authored-item', 'token': 'fail',
            'view': VIEW, 'request_view': VIEW, 'report': None, 'steps': None}


def test_replay_separates_diagnostics_from_notes_core_hashes_and_raw_capture():
    pack = package()
    procedure = pack.procedures[0]
    outcomes = []
    for raw in (FIELDS, {**FIELDS, 'diagnostics': ['Clue 6 was not interpreted.']}):
        fake = FakeSandbox({procedure.id: {'before_call': lambda *_, value=raw: value}})
        fake.start(pack, kind='cell')
        actual = []
        result = replay.replay(fake, procedure, entry(), configuration=d.CONFIGURATION, actual=actual)
        outcomes.append(result)
        assert 'diagnostics' not in json.dumps(actual)
        assert result.faults == []
    assert outcomes[0].notes == outcomes[1].notes and outcomes[0].values == outcomes[1].values
    assert outcomes[1].diagnostics[0]['strings'][0]['text'] == 'Clue 6 was not interpreted.'
    assert outcomes[1].summary()['diagnostics'] == outcomes[1].diagnostics


def test_routing_note_projection_and_signature_observer_keep_diagnostic_free_identity():
    pack = package()
    procedure = pack.procedures[0]
    raw = {**FIELDS, 'diagnostics': ['Clue 6 was not interpreted.']}
    result = {'ok': True, 'value': raw, 'value_sha256': digest(raw)}
    seen = []
    text = replay.screened_note(procedure, p.ZEBRA, VIEW, result,
                               configuration=d.CONFIGURATION, diagnostics=seen)
    assert text and seen and 'diagnostics' not in text
    identities = []
    captured = []
    for value in (FIELDS, raw):
        fake = FakeSandbox({procedure.id: {'before_call': lambda *_, v=value: v}}).start(pack, kind='cell')
        identities.append(reuse.signature(p.ZEBRA, pack, VIEW, fake, configuration=d.CONFIGURATION,
            note_observer=lambda shell, _: captured.append(shell.diagnostics)))
    assert identities[0] == identities[1] and reuse.interchangeable(*identities, bench=p.ZEBRA)
    assert captured[0] == [] and captured[1] == seen


def test_training_trajectory_keeps_channel_but_old_engineer_whitelist_omits_it(tmp_path):
    prediction, _, pack = run({'diagnostics': ['Clue 6 was not interpreted.']})
    cell = {'id': 'authored-cell', 'unit': 'D/s1-zebralogic/train-r1', 'arm': "S'", 'benchmark': p.ZEBRA,
            'task_id': 'authored-item', 'run': 0}
    value = trajectories.build(cell, evidence=FIXTURE, arm_kind='candidate', package_sha256=pack.sha256,
        calls=[], prediction=prediction, judge={'v2': {'token': 'fail'}}, deciding=None, worst=None,
        logical_calls=0, dispatch_ts=0, finish_ts=1, configuration=d.CONFIGURATION)
    trajectories.write(tmp_path, cell['id'], value)
    stored = read_json(tmp_path / 'trajectories' / 'authored-cell.json')
    assert stored['shell']['diagnostics'] == prediction['shell']['diagnostics']
    assert 'diagnostics' not in trajectories.whitelisted(stored)['shell']


@pytest.mark.parametrize('configuration', [name for name in p.CONFIGURATIONS if not p.is_v215(name)])
def test_all_36_older_configurations_keep_unknown_field_behavior_and_original_worker_hash(configuration):
    found, _, _ = run({**FIELDS, 'diagnostics': ['Clue 6 was not interpreted.']}, configuration=configuration)
    assert 'diagnostics' not in found['shell']
    assert any(row['kind'] == 'note_unknown_field' for row in found['shell']['faults'])
    assert client.worker_sha256(configuration=configuration) == OLD_WORKER_SHA256


@pytest.mark.parametrize('raw', ['["x"*2000000]', '["x"*1000+"<answer>suffix"]',
                                  '{"ignored": "x"*2000000}', '[object()]'])
def test_child_worker_extracts_before_plain_json_and_output_caps(raw):
    source = 'def before_call(view,state):\n    return {"facts":["Clue could not be parsed."],"diagnostics":'+raw+'}\n'
    code = compile(source, '<authored-diagnostics>', 'exec')
    found = worker_v215.execute(code, 'before_call', [VIEW, None], 1024, diagnostics_spec=d.worker_spec())
    plain = worker.execute(compile('def before_call(view,state):\n    return {"facts":["Clue could not be parsed."]}\n',
                                  '<authored-no-diagnostics>', 'exec'), 'before_call', [VIEW, None], 1024)
    assert found['ok'] and found['value'] == plain['value']
    assert len(worker.canonical(found)) < worker_v215.DIAGNOSTICS_ENVELOPE_BYTES
    d.verified_record(found['diagnostics'])


def test_child_worker_preserves_core_output_cap_and_old_worker_bytes():
    code = compile('def before_call(view,state):\n    return {"facts":["x"*2000],"diagnostics":["bounded"]}\n',
                   '<authored-core-cap>', 'exec')
    assert worker_v215.execute(code, 'before_call', [VIEW, None], 1024,
                               diagnostics_spec=d.worker_spec())['fault'] == 'over_cap'
    assert client.worker_sha256() == OLD_WORKER_SHA256
    assert client.worker_sha256(configuration=d.CONFIGURATION) != OLD_WORKER_SHA256


def test_child_worker_selected_only_explicitly_and_client_retains_bounded_sidecar(tmp_path, monkeypatch):
    pack = package('def before_call(view,state):\n    return {"diagnostics":["x"*2000000]}\n')
    old = client.Worker(scratch=tmp_path / 'old')
    (tmp_path / 'old').mkdir()
    assert hashlib.sha256((old._runner_dir() / 'worker.py').read_bytes()).hexdigest() == OLD_WORKER_SHA256
    child = client.Worker(scratch=tmp_path / 'child', diagnostics_configuration=d.CONFIGURATION)
    (tmp_path / 'child').mkdir()
    child.start(pack, kind='cell')
    state = {'loaded': {}, 'limits': child.limits['cell'].worker()}
    requests = []
    monkeypatch.setattr(child, '_ensure', lambda: setattr(child, '_container', SimpleNamespace(name='authored')))
    def exchange(request, timeout):
        requests.append(deepcopy(request))
        if request['op'] == 'diagnostics-v215':
            return worker_v215.handle_diagnostics({**request, 'seq': 1}, state)
        result = worker_v215.execute(compile(pack.procedures[0].source, '<authored>', 'exec'),
            request['fn'], request['args'], 1024, diagnostics_spec=state['diagnostics_v215'])
        return {**result, 'op': 'call', 'proc': request['proc'], 'fn': request['fn'],
                'args_sha256': digest(request['args']), 'value_sha256': digest(result['value']), 'cpu_ms': 0, 'rss_kib': 1}
    monkeypatch.setattr(child, '_exchange', exchange)
    result = child.call_diagnostics(pack.order[0], 'before_call', [VIEW, None], timeout_s=1)
    assert result['ok'] and result['value'] == {} and result['diagnostics']['truncated_strings'] == 1
    assert requests[-1]['diagnostics_v215'] is True
    assert hashlib.sha256((child._runner_dir() / 'worker.py').read_bytes()).hexdigest() == client.worker_sha256(d.CONFIGURATION)
    with pytest.raises(ValueError, match='v2.15 Zebra worker'):
        old.call_diagnostics(pack.order[0], 'before_call', [VIEW, None], timeout_s=1)
