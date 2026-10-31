"""v2.16 inherits the frozen v2.15 diagnostics and worker; authored inputs only."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from skillopt.execskill import diagnostics, diagnostics_runtime, evaluation, profiles as p, replay, reuse
from skillopt.execskill.sandbox import client, worker_v215
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import FakeSandbox
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v215_diagnostics_runtime import FIELDS, VIEW, entry, package, run
from tests import test_execskill_v212_evaluation as eval_parent

CHILD, PARENT = 'zebra-pc-v15', 'zebra-pc-v14'
ORIGINAL_WORKER = 'bb1ccc0d90cafbda1f842569454ec676a8329d721a423246d92572632cf4ea0d'
DIAGNOSTIC_WORKER = '389f24d070303186eca992117c47b2ebb2c281fdfa1dcfe69a9f5c2827c535d7'


@pytest.mark.parametrize('arm', ['F', 'C', 'B', 'S', "S'", 'withhold', 'restore'])
@pytest.mark.parametrize('value', [FIELDS, {**FIELDS, 'diagnostics': ['Clue remains unresolved.']},
                                   {**FIELDS, 'diagnostics': [None, 'x' * 300 + '<answer>withheld']},
                                   {**FIELDS, 'diagnostics': {'not': 'a list'}}])
def test_child_requests_and_shell_records_are_exactly_parent_protocol(arm, value):
    parent, before, _ = run(value, configuration=PARENT, arm=arm)
    child, after, _ = run(value, configuration=CHILD, arm=arm)
    assert after == before and child == parent
    plain, base, _ = run(FIELDS, configuration=CHILD, arm=arm)
    assert after == base
    assert child['shell']['faults'] == plain['shell']['faults']
    assert child['shell']['notes_chars'] == plain['shell']['notes_chars']


@pytest.mark.parametrize('configuration', [None, 'main-v5', 'zebra-pc-v13', PARENT, CHILD])
def test_worker_pin_changes_only_for_the_inheriting_child(configuration):
    expected = DIAGNOSTIC_WORKER if configuration in (PARENT, CHILD) else ORIGINAL_WORKER
    assert client.worker_sha256(configuration=configuration) == expected
    assert diagnostics.enabled(configuration) == (configuration in (PARENT, CHILD))
    assert diagnostics.identity()['configuration'] == PARENT


def test_child_selects_frozen_worker_with_canonical_parent_handshake(tmp_path, monkeypatch):
    pack = package('def before_call(view,state):\n    return {"diagnostics":["Clue remains unresolved."]}\n')
    child = client.Worker(scratch=tmp_path, diagnostics_configuration=CHILD).start(pack, kind='cell')
    state = {'loaded': {}, 'limits': child.limits['cell'].worker()}
    calls = []
    monkeypatch.setattr(child, '_ensure', lambda: setattr(child, '_container', SimpleNamespace(name='authored')))
    def exchange(request, timeout):
        calls.append(deepcopy(request))
        if request['op'] == 'diagnostics-v215':
            return worker_v215.handle_diagnostics({**request, 'seq': 1}, state)
        result = worker_v215.execute(compile(pack.procedures[0].source, '<authored-v216>', 'exec'),
            request['fn'], request['args'], 1024, diagnostics_spec=state['diagnostics_v215'])
        return {**result, 'op': 'call', 'proc': request['proc'], 'fn': request['fn'],
                'args_sha256': digest(request['args']), 'value_sha256': digest(result['value']),
                'cpu_ms': 0, 'rss_kib': 1}
    monkeypatch.setattr(child, '_exchange', exchange)
    result = child.call_diagnostics(pack.order[0], 'before_call', [VIEW, None], timeout_s=1)
    assert result['ok'] and result['value'] == {}
    assert calls[0]['configuration'] == PARENT
    assert calls[1]['diagnostics_v215'] is True
    assert hashlib.sha256((child._runner_dir() / 'worker.py').read_bytes()).hexdigest() == DIAGNOSTIC_WORKER
    assert child.diagnostics_configuration == CHILD


def test_child_replay_signature_and_fault_sidecar_match_parent():
    pack = package()
    proc = pack.procedures[0]
    raw = {**FIELDS, 'diagnostics': ['Clue remains unresolved.']}
    observations = []
    for configuration in (PARENT, CHILD):
        fake = FakeSandbox({proc.id: {'before_call': lambda *_: raw}}).start(pack, kind='cell')
        result = replay.replay(fake, proc, entry(), configuration=configuration)
        signature = reuse.signature(p.ZEBRA, pack, VIEW, fake, configuration=configuration)
        failed = {'ok': False, 'fault': 'output', 'exc_type': 'OutputFault', 'message': 'not JSON: set',
                  'line': None, 'diagnostics': diagnostics.extract(raw, configuration=configuration)[1]}
        clean, report = diagnostics_runtime.capture(failed, configuration=configuration, procedure=proc)
        observations.append((result.summary(), signature, clean, report))
    assert observations[0] == observations[1]
    assert 'diagnostics' not in observations[1][2]
    assert observations[1][3]['strings'][0]['text'] == 'Clue remains unresolved.'


def test_child_compact_evaluation_keeps_parent_metadata_without_diagnostic_text(tmp_path, monkeypatch):
    monkeypatch.setattr(eval_parent, 'CONFIG', CHILD)
    eval_parent.test_sealed_cells_preserve_inherited_route_keyword_and_model_metadata(tmp_path)
