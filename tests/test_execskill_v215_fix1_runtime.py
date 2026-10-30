"""Authored F2/F3 runtime regressions; no Docker, model, network or dataset use."""
from copy import deepcopy
import hashlib
import json
import os
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from skillopt.execskill import diagnostics as d, diagnostics_runtime, engineer_v291, fault_feedback, replay
from skillopt.execskill.sandbox import client, worker, worker_v215 as w
from skillopt.validator_pilot.api import digest
from tests.test_execskill_v215_diagnostics_runtime import FIELDS, VIEW, entry, package, run
from tests.test_execskill_v24_engineer import context

PATTERNS = ['x reply with neighbors ', 'only the neighbor remains unresolved ']


def large(pattern):
    return (pattern * (1_000_000 // len(pattern) + 1))[:1_000_000]


def code(raw, *, facts='["Clue 6 compares positions."]'):
    return compile('def before_call(view,state):\n    return {"facts":' + facts +
                   ',"diagnostics":' + raw + '}\n', '<authored-fix1>', 'exec')


@pytest.mark.parametrize('pattern', PATTERNS)
def test_five_megabyte_adversarial_diagnostics_keep_note_and_finish_under_half_second(pattern, monkeypatch):
    monkeypatch.setattr(w, '_diagnostics_module', lambda: d)
    raw = '[' + ','.join(repr(pattern) + '*%d' % (1_000_000 // len(pattern)) for _ in range(5)) + ']'
    started = time.monotonic()
    found = w.execute(code(raw), 'before_call', [VIEW, None], 1024, diagnostics_spec=d.worker_spec())
    elapsed = time.monotonic() - started
    assert elapsed < .5
    assert found['ok'] and found['value'] == FIELDS
    record = d.verified_record(found['diagnostics'])
    assert len(record['strings']) == 5
    text = pattern * (1_000_000 // len(pattern))
    assert all(row['source_sha256'] == hashlib.sha256(text.encode()).hexdigest()
               and row['original_chars'] == len(text) for row in record['strings'])


@pytest.mark.parametrize('arm', ['F', 'C', 'B', 'S', "S'", 'withhold', 'restore'])
@pytest.mark.parametrize('pattern', PATTERNS)
def test_every_arm_retains_identical_requests_with_five_megabyte_diagnostics(arm, pattern):
    plain, before, _ = run(FIELDS, arm=arm)
    observed, after, _ = run({**FIELDS, 'diagnostics': [large(pattern)] * 5}, arm=arm)
    assert after == before and len(after) == 1
    for field in ('faults', 'notes_chars', 'procedure_events'):
        assert observed['shell'][field] == plain['shell'][field]


def test_bounded_window_still_catches_cut_crossing_and_rescreens_display_prefix():
    for text in ('x' * 235 + ' <answer>hidden', 'x' * 233 + ' answerable'):
        record = d.safe_bounded([text], screen_spec=d.worker_spec())
        assert record['strings'][0]['text'] == d.SCREENED_MARKER
        assert record['strings'][0]['source_sha256'] == d.sha256(text)
    beyond = 'x' * (d.MAX_CHARS + d.LOOKAHEAD + 1) + '<answer>not displayed'
    record = d.safe_bounded([beyond], screen_spec=d.worker_spec())
    assert record['strings'][0]['text'] == 'x' * d.MAX_CHARS


@pytest.mark.parametrize('failure', ['raises', 'overruns'])
def test_host_processing_failure_omits_only_diagnostics_and_preserves_request(failure, monkeypatch):
    plain, before, _ = run(FIELDS)
    def failed(*args, **kwargs):
        if failure == 'raises':
            raise RuntimeError('DO_NOT_DISCLOSE_THIS_EXCEPTION')
        return d._seal({'malformed': True})
    monkeypatch.setattr(d, 'bounded', failed)
    if failure == 'overruns':
        clock = iter((0., .2))
        monkeypatch.setattr(d.time, 'monotonic', lambda: next(clock, .2))
    found, after, _ = run({**FIELDS, 'diagnostics': ['ignored']})
    assert after == before and found['shell']['faults'] == plain['shell']['faults']
    records = found['shell']['diagnostics']
    assert records and records[0]['shape_faults'][0]['informational'] is True
    assert 'DO_NOT_DISCLOSE' not in json.dumps(found)


@pytest.mark.parametrize('ok', [True, False])
def test_client_and_host_bad_sidecar_is_informational_for_success_and_fault(ok):
    core = {'ok': True, 'value': FIELDS, 'value_sha256': digest(FIELDS), 'cpu_ms': 12, 'rss_kib': 34} if ok else \
        w.fault('output', 'OutputFault', 'not JSON: set')
    proc = package().procedures[0]
    raw = {**core, 'op': 'call', 'proc': proc.id, 'fn': 'before_call', 'args_sha256': digest([VIEW, None]),
           'diagnostics': {'sha256': 'broken'}}
    result = client.Worker._result(raw, proc.id, 'before_call', digest([VIEW, None]), diagnostics_v215=True)
    assert {k: v for k, v in result.items() if k != 'diagnostics'} == core
    assert result['diagnostics']['shape_faults'][0]['reason'] == 'invalid_record'
    clean, record = diagnostics_runtime.capture({**core, 'diagnostics': {'sha256': 'broken'}},
        configuration=d.CONFIGURATION, procedure=proc)
    assert clean == core and record['shape_faults'][0]['reason'] == 'invalid_record'


@pytest.mark.parametrize('failure', ['raises', 'overruns'])
@pytest.mark.parametrize('facts', ['["Clue 6 compares positions."]', '{"bad"}'])
def test_worker_accepts_core_before_diagnostic_failure_or_separate_budget_timeout(failure, facts, monkeypatch):
    original = d.safe_bounded
    def failed(*args, **kwargs):
        if failure == 'raises':
            raise RuntimeError('DO_NOT_DISCLOSE_THIS_EXCEPTION')
        time.sleep(.2)
        return original(*args, **kwargs)
    monkeypatch.setattr(w, '_diagnostics_module', lambda: SimpleNamespace(safe_bounded=failed))
    read_fd, write_fd = os.pipe()
    def emit():
        try:
            def accepted(outcome, pending):
                w._write_all(write_fd, w.frame({'outcome': outcome, 'diagnostics_pending': pending,
                                              'cpu_ms': 12, 'rss_kib': 34}))
            outcome = w.execute(code('["ignored"]', facts=facts), 'before_call', [VIEW, None], 1024,
                                diagnostics_spec=d.worker_spec(), accepted=accepted)
            w._write_all(write_fd, w.frame({'diagnostics': outcome.get('diagnostics')}))
        except BrokenPipeError:
            pass
        finally:
            os.close(write_fd)
    thread = threading.Thread(target=emit)
    thread.start()
    started = time.monotonic()
    try:
        result, status, _ = w._diagnostic_outcome(read_fd, started + .05, {'frame_bytes': 4096})
    finally:
        os.close(read_fd)
    elapsed = time.monotonic() - started
    thread.join()
    assert status == 'accepted' and elapsed < .5
    assert result['diagnostics']['shape_faults'][0]['reason'] == (
        'processing_failed' if failure == 'raises' else 'processing_timeout')
    if facts.startswith('['):
        assert result['ok'] and result['value'] == FIELDS
        assert result['cpu_ms'] == 12 and result['rss_kib'] == 34
    else:
        assert {k: v for k, v in result.items() if k != 'diagnostics'} == w.fault(
            'output', 'OutputFault', 'not JSON: set')


def test_diagnostic_phase_does_not_extend_hook_acceptance_deadline():
    read_fd, write_fd = os.pipe()
    try:
        started = time.monotonic()
        result, ended, deadline = w._diagnostic_outcome(read_fd, started + .01, {'frame_bytes': 4096})
        assert result is None and ended == 'timeout' and deadline == started + .01
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_review_set_in_facts_retains_fault_and_diagnostic_through_repair_evidence(monkeypatch):
    reason = 'Unresolved alternatives remain after parsing the clues.'
    source = 'def before_call(view,state):\n    return {"facts": {"bad"}, "diagnostics": [' + repr(reason) + ']}\n'
    proc = package(source).procedures[0]
    spec = d.worker_spec()
    reply = w.execute(compile(source, '<authored-set>', 'exec'), 'before_call', [VIEW, None], 1024,
                      diagnostics_spec=spec)
    plain = worker.execute(compile(source.replace(', "diagnostics": [' + repr(reason) + ']', ''),
                                   '<authored-set>', 'exec'), 'before_call', [VIEW, None], 1024)
    assert {k: v for k, v in reply.items() if k != 'diagnostics'} == plain
    raw = {**reply, 'op': 'call', 'proc': proc.id, 'fn': 'before_call', 'args_sha256': digest([VIEW, None])}
    result = client.Worker._result(raw, proc.id, 'before_call', digest([VIEW, None]), diagnostics_v215=True)
    ctx, _ = context(configuration=d.CONFIGURATION)
    inputs = replay.inputs_of(ctx.trajectories[0])
    class Returned:
        def call(self, *args, **kwargs):
            return deepcopy(result)
    actual = []
    outcome = replay.replay(Returned(), proc, inputs, configuration=d.CONFIGURATION, actual=actual,
                            capture_faults=True)
    assert outcome.faults[0]['message'] == plain['message']
    assert reason not in json.dumps(actual)
    report = {'checks': [{'check': 'C6', 'detail': {'items': [
        {'task_id': inputs['item'], 'first': outcome.summary(), 'second': outcome.summary()}]}}]}
    old = fault_feedback.summarize(proc, report, configuration=d.CONFIGURATION)
    evidence = engineer_v291._evidence(ctx, proc, report)
    assert {k: v for k, v in evidence.items() if k != 'engineer_diagnostics'} == old
    assert reason in json.dumps(evidence['engineer_diagnostics'])
    seen = []
    assert replay.screened_note(proc, 'zebralogic', VIEW, result, configuration=d.CONFIGURATION,
                                diagnostics=seen) == ''
    assert seen and seen[0]['strings'][0]['text'] == reason


@pytest.mark.parametrize('faulted', [False, True])
def test_actual_child_process_preserves_accepted_outcome_after_diagnostic_deadline(faulted, monkeypatch):
    """Exercise production fork/pipe/reap, with only the diagnostic helper delayed."""
    def slow(*args, **kwargs):
        time.sleep(.3)
        return d.safe_bounded(*args, **kwargs)
    monkeypatch.setattr(w, '_diagnostics_module', lambda: SimpleNamespace(safe_bounded=slow))
    if sys.platform == 'darwin':
        # Linux resource setup and killpg are unavailable in this host sandbox.
        # Keep real fork/pipe/reap and the exact production execute/send phase.
        # This authored child has no descendants and exits after 300 ms.
        monkeypatch.setattr(w, '_kill_group', lambda pid: None)
        def portable_child(code, fn, args, timeout_s, limits, write_fd, call_dir, *, diagnostics_spec=None):
            return w._execute_and_send(code, fn, args, limits, write_fd, diagnostics_spec=diagnostics_spec)
        monkeypatch.setattr(w, '_child', portable_child)
    channel = os.open(os.devnull, os.O_RDONLY)
    try:
        result = w.run_call(code('["ignored"]', facts='{"bad"}' if faulted else repr(FIELDS['facts'])),
            'before_call', [VIEW, None], .1, {'address_space_mb': 65_536, 'frame_bytes': 1 << 20},
            channel, diagnostics_spec=d.worker_spec())
    finally:
        os.close(channel)
    assert result['diagnostics']['shape_faults'][0]['reason'] == 'processing_timeout'
    if faulted:
        assert {k: v for k, v in result.items() if k != 'diagnostics'} == w.fault(
            'output', 'OutputFault', 'not JSON: set')
    else:
        assert result['ok'] and result['value'] == FIELDS and result['value_sha256'] == digest(FIELDS)
