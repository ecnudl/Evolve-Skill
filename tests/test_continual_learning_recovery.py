"""Bounded recovery engineering controls; no new benchmark effect claims."""
import json
from copy import deepcopy

import httpx
import pytest

from skillopt.continual_eval.core import read_json
from skillopt.continual_learning.contracts import RECOVERY_VERSION, manifest, validate_manifest
from skillopt.continual_learning.ledger import LearningPending, Ledger
from skillopt.continual_learning.recovery import POLICY, solver_call
from skillopt.validator_pilot import api as provider
from skillopt.validator_pilot.api import digest
from tests.test_continual_learning_domains import setup


def auth():
    _, panel, args = setup()
    args.update(version=RECOVERY_VERSION, recovery_policy=deepcopy(POLICY))
    args['model']['transport']['stream_wall_seconds'] = 3600
    return manifest(panel, **args), panel


class API:
    model = 'fixture'
    service = {'fixture': 'closed-delivery-recovery'}

    def __init__(self, finishes, *, complete=True, usage=True):
        self.finishes, self.calls, self.complete, self.usage = finishes, [], complete, usage

    def call(self, system, user, kind, key, *, max_tokens, repeat):
        request = dict(model=self.model, system=system, user=user, kind=kind, key=key,
                       max_tokens=max_tokens, repeat=repeat, service=self.service)
        finish = self.finishes[len(self.calls)]
        self.calls.append(request)
        return dict(request=request, request_hash=digest(request), ok=finish == 'stop',
                    response='partial' if finish == 'length' else '<answer>Paris</answer>',
                    finish_reason=finish, stream_complete=self.complete, status=200,
                    returned_model='glm-5.3', http_attempt_count=1,
                    usage={'prompt_tokens': 20, 'completion_tokens': 30} if self.usage else {})


def test_v4_manifest_explicit_roundtrip():
    value, panel = auth()
    assert validate_manifest(value, panel) == value
    assert value['benchmark'] == 'searchqa'
    assert value['recovery_policy'] == POLICY


def test_legacy_cannot_silently_enable_recovery():
    _, panel, args = setup()
    with pytest.raises(ValueError, match='explicit v4'):
        manifest(panel, **args, recovery_policy=POLICY)
    args['version'] = RECOVERY_VERSION
    with pytest.raises(ValueError, match='recovery policy'):
        manifest(panel, **args)


@pytest.mark.parametrize('field,value', [('length_retries', True), ('length_max_tokens', 131072.0)])
def test_policy_exact_numeric_types(field, value):
    _, panel, args = setup()
    args.update(version=RECOVERY_VERSION, recovery_policy={**POLICY, field: value})
    args['model']['transport']['stream_wall_seconds'] = 3600
    with pytest.raises(ValueError, match='exact types'):
        manifest(panel, **args)


def test_wall_time_float_rejected():
    _, panel, args = setup()
    args.update(version=RECOVERY_VERSION, recovery_policy=POLICY)
    args['model']['transport']['stream_wall_seconds'] = 3600.0
    with pytest.raises(ValueError, match='3600'):
        manifest(panel, **args)


def test_once_length_retry_binds_parent_preserves_cost_and_replays(tmp_path):
    value, _ = auth()
    api = API(['length', 'stop'])
    ledger = Ledger(tmp_path, value, api)
    result = solver_call(ledger, 'task:turn:0', 'system', 'user')
    assert result['ok']
    assert [x['max_tokens'] for x in api.calls] == [100, 131072]
    assert ledger.snapshot()['logical_calls'] == 2
    assert ledger.snapshot()['reported_tokens_known_subtotal'] == 100
    intents = [read_json(p, sealed=True) for p in (tmp_path / 'call_intents').glob('*.json')]
    recovery = next(x for x in intents if 'recovery_of' in x)
    assert recovery['recovery_of'] in {x['record_hash'] for x in intents}
    assert solver_call(ledger, 'task:turn:0', 'system', 'user') == result
    assert len(api.calls) == 2
    with pytest.raises(ValueError, match='Invalid or repeated'):
        ledger.call('solver', recovery['logical_id'] + ':length-recovery:1', 'system', 'user',
                    131072, recovery_of=recovery['record_hash'])


@pytest.mark.parametrize('finish', ['stop', 'sensitive', 'content_filter', 'network_error'])
def test_not_retry_semantic_or_filtered_response(tmp_path, finish):
    value, _ = auth()
    api = API([finish])
    result = solver_call(Ledger(tmp_path, value, api), 'task', 'system', 'user')
    assert result['finish_reason'] == finish and len(api.calls) == 1


def test_still_truncated_after_one_retry_stays_unknown(tmp_path):
    value, _ = auth()
    api = API(['length', 'length'])
    result = solver_call(Ledger(tmp_path, value, api), 'task', 'system', 'user')
    assert not result['ok'] and result['finish_reason'] == 'length' and len(api.calls) == 2


def test_incomplete_stream_does_not_retry(tmp_path):
    value, _ = auth()
    api = API(['length'], complete=False)
    solver_call(Ledger(tmp_path, value, api), 'task', 'system', 'user')
    assert len(api.calls) == 1


def test_conflicting_error_flags_do_not_authorize_length_recovery():
    from skillopt.continual_learning.recovery import is_closed_length

    assert not is_closed_length({'finish_reason': 'length', 'error_type': 'provider_content_filter',
                                 'stream_complete': True, 'status': 200, 'returned_model': 'glm-5.3'})


def test_missing_usage_blocks_recovery_without_inventing_cost(tmp_path):
    value, _ = auth()
    api = API(['length'], usage=False)
    ledger = Ledger(tmp_path, value, api)
    with pytest.raises(LearningPending, match='usage'):
        solver_call(ledger, 'task', 'system', 'user')
    assert ledger.snapshot()['missing_usage_calls'] == 1 and len(api.calls) == 1


def test_extended_cap_cannot_be_requested_without_parent(tmp_path):
    value, _ = auth()
    with pytest.raises(ValueError, match='cap'):
        Ledger(tmp_path, value, API([])).call('solver', 'task', 'system', 'user', 131072)


@pytest.mark.parametrize('enabled,finishes,expected_attempts,ok', [
    (True, ['network_error', 'stop'], 2, True),
    (True, ['network_error'] * 3, 3, False),
    (False, ['network_error'], 1, False),
    (True, ['sensitive'], 1, False),
    (True, ['length'], 1, False),
    (True, ['content_filter'], 1, False),
])
def test_http200_network_finish_bounded_opt_in(tmp_path, monkeypatch, enabled, finishes, expected_attempts, ok):
    monkeypatch.setattr(provider, '_configuration', lambda *a, **k: (
        'https://open.bigmodel.cn/api/paas/v4/chat/completions', 'FIXTURE_NOT_A_KEY'))
    monkeypatch.setattr(provider.time, 'sleep', lambda _: None)
    requests = []
    sync_client, async_client = httpx.Client, httpx.AsyncClient

    def handle(request):
        finish = finishes[len(requests)]
        requests.append(json.loads(request.content))
        event = {'model': 'glm-5.3', 'choices': [{'index': 0, 'delta': {
            'content': 'ok' if finish == 'stop' else ''}, 'finish_reason': finish}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 2}}
        return httpx.Response(200, headers={'content-type': 'text/event-stream'},
                              content=('data: ' + json.dumps(event) + '\n\ndata: [DONE]\n\n').encode())

    monkeypatch.setattr(provider.httpx, 'Client', lambda **k: sync_client(transport=httpx.MockTransport(handle), **k))
    monkeypatch.setattr(provider.httpx, 'AsyncClient', lambda **k: async_client(transport=httpx.MockTransport(handle), **k))
    options = {'delivery_retry_policy': 'closed_network_error_v1'} if enabled else {}
    with provider.CachedAPI(tmp_path, tmp_path / 'api', provider='bigmodel', stream=True,
                            read_timeout_seconds=300, stream_wall_seconds=3600,
                            initial_health_policy='completed_response_v1', **options) as api:
        receipt = api.call('system', 'user', 'smoke', '0', max_tokens=100)
        assert api.call('system', 'user', 'smoke', '0', max_tokens=100) == receipt
    assert len(requests) == expected_attempts == receipt['http_attempt_count']
    assert receipt['ok'] == ok
    assert ('delivery_retry_policy' in receipt['request']['service']) == enabled
    if enabled and finishes[0] == 'network_error':
        assert receipt['attempts'][0]['error_type'] == 'provider_network_error'
    if enabled:
        assert len(receipt['attempts']) == expected_attempts
        assert all(r['usage'] == {'prompt_tokens': 10, 'completion_tokens': 2} for r in receipt['attempts'])


@pytest.mark.parametrize('missing', [False, True])
def test_ledger_accounts_for_failed_http_attempt_usage(tmp_path, missing):
    value, _ = auth()

    class RetriedAPI(API):
        service = {'delivery_retry_policy': 'closed_network_error_v1'}

        def call(self, *args, **kwargs):
            row = super().call(*args, **kwargs)
            row.update(http_attempt_count=2, attempts=[
                {'usage': {} if missing else {'prompt_tokens': 17, 'completion_tokens': 9}},
                {'usage': row['usage']}])
            return row

    ledger = Ledger(tmp_path, value, RetriedAPI(['stop']))
    ledger.call('solver', 'one', 'system', 'user', 100)
    costs = ledger.snapshot()
    assert costs['reported_tokens_known_subtotal'] == (50 if missing else 76)
    assert costs['missing_attempt_usage'] == int(missing)
    assert costs['usage_complete'] is (not missing)
    assert costs['retry_inclusive_usage_known'] is (not missing)


def test_smoke_panel_selection_is_outcome_blind_and_role_disjoint():
    from scripts.smoke_skillopt_recovery import small_panel

    _, panel, args = setup()
    roles = {'train': args['train_families'], 'selection': args['selection_families']}
    subset, groups = small_panel(panel, roles)
    assert len(subset['tasks']) == 4 and not set(groups[0]) & set(groups[1])
    assert panel['tasks'] == subset['tasks'] or {digest(t) for t in panel['tasks']} == {
        digest(t) for t in subset['tasks']}
