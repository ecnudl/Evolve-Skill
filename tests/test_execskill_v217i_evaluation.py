"""Implanted five-benchmark reads use authored items and fake clients only."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts.weak_solver_probe import Client, MODELS
from skillopt.coevo5.budget import Budget
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (alfworld_format, budgets, cells, chain, client, evaluation,
                               instruction_start, manifest, package, profiles as p, readout,
                               routes, slots, units, v217_implant as imp, zebralogic as z)
from tests.execskill_fakes_env import FakeNative, FakeSandbox, alf_sessions, procedure
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.fixtures.execskill.items import officeqa_items, searchqa_items, spreadsheetbench_items
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_cells import RUNTIMES, PROGRAM
from tests.test_execskill_chain import setting as chain_setting
from tests.test_execskill_readout import cell
from tests.test_execskill_solver import alf_public, plan_replies
from tests.test_execskill_v214_evaluation import consent as main_consent
from tests.test_execskill_zpc_pipeline import fixture_pool, public_grid

CONFIG = p.IMPLANT_V5
EVIDENCE = 'engineering_fixture'
ROWS = ['C', 'C', 'C', 'S3', 'S3', 'F']
NOTE = 'The visible input has been checked.'


def consent():
    return {**main_consent(), 'date': '2026-11-01',
            'note': 'Owner consent for both implanted chains and all five panels.'}


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


class RecordCalls:
    def _record(self, system, user):
        self.requests.append(wire(self.body(system, user)))
        self.messages.append((system, user))
        response = self.replies.pop(0)
        return {'ok': True, 'response': response, 'finish_reason': 'stop', 'error_type': None,
                'returned_model': getattr(self, 'request_model', self.model),
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
                'visible_completion_tokens': 5, 'attempts': [{'status': 200}]}

    def call(self, system, user):
        return self._record(system, user)


class BodyOnlyG(RecordCalls, Client):
    """Keep production body construction, replace credentials and I/O."""
    def __init__(self, repo, model, *, proxy, max_tokens, read_timeout, transport=None):
        self.constructor = (repo, model, proxy, max_tokens, read_timeout, transport)
        self.backend, self.thinking, self.effort, _, self.response_model_ids = MODELS[model]
        self.model, self.max_tokens = model, max_tokens
        self.requests, self.messages, self.replies = [], [], []


class BodyOnlyD(RecordCalls, client.NorthgateClient):
    def __init__(self, env_path, *, proxy, max_tokens, read_timeout, transport=None):
        self.constructor = (env_path, proxy, max_tokens, read_timeout, transport)
        route = self.ROUTE
        self.backend, self.model, self.max_tokens = route.backend, client.ELUCID_MODEL, max_tokens
        self.route, self.request_model, self.exhausted = route.id, route.model, None
        self.thinking, self.effort, self.response_model_ids = None, client.REASONING_EFFORT, route.response_model_ids
        self.requests, self.messages, self.replies = [], [], []


def authored_task(bench, root, monkeypatch):
    if bench == 'searchqa':
        return searchqa_items(1)[0], ['<answer>Fixtown 0</answer>']
    if bench == 'officeqa':
        return officeqa_items(1)[0], ['<answer>200</answer>']
    if bench == p.ZEBRA:
        task = fixture_pool()[0]
        return task, [json.dumps({'solution': public_grid(task['public'])})]
    if bench == 'spreadsheetbench':
        FakeNative().install(monkeypatch)
        task = spreadsheetbench_items(root, 1)[0]
        return task, [PROGRAM]
    alf_sessions(monkeypatch)
    public, game = alf_public(root)
    return {'task_id': 'authored-alfworld', 'public': public, 'private': {}}, plan_replies(game)


def authored_package(bench):
    hook = 'alf_before_step' if bench == 'alfworld' else 'before_call'
    return package.Package((procedure('fx-implant-request', ('applies', hook), origin=bench,
        policy_version=p.POLICY_VERSIONS[CONFIG], max_note_chars=1500),), 'authored/final', EVIDENCE)


def authored_worker(bench):
    hook = 'alf_before_step' if bench == 'alfworld' else 'before_call'
    value = {'facts': [NOTE]}
    if hook == 'alf_before_step':
        value = {'fields': value, 'discourage': []}
    return FakeSandbox({'fx-implant-request': {'applies': lambda view: True,
                                              hook: lambda *args: deepcopy(value)}})


def context(root, configuration, chain_id, bench, monkeypatch):
    monkeypatch.setattr(client, 'Client', BodyOnlyG)
    monkeypatch.setitem(client.ROUTE_CLIENTS, 'B', BodyOnlyD)
    monkeypatch.setattr(client, 'unpooled', lambda found, **kw: found)
    blocks = {'G': manifest.solver_block('G', env_path=root / 'unread-roles', configuration=configuration),
              'D': manifest.solver_block('D', env_path=root / 'unread-route.env', branch='N',
                                         longest=60000, configuration=configuration)}
    route = routes.pin('D', 'B', env_path=root / 'unread-route.env', solver_block=blocks['D'],
                       configuration=configuration)
    given = {'configuration': configuration, 'root': str(root), p.RECORD_HASH: 'authored-run',
             'clients': {'solver': blocks, 'roles': manifest.role_settings(configuration), 'routes': {'D': {'B': route}}}}
    factory = manifest._clients(given, chain_id, transport=None, route='B' if chain_id == 'D' else None)
    runtime = deepcopy(RUNTIMES)
    runtime[p.ZEBRA] = {}
    runtime['alfworld'] = alfworld_format.bind(runtime['alfworld'], configuration)
    ledger = Budget(root / configuration / chain_id / 'ledger', sleep=lambda _: None)
    ledger.declare(budgets.chain_caps(chain_id, configuration))
    own = SimpleNamespace(slots=slots.pools(root / 'slots', poll=0.01, log=lambda _: None),
        sandbox={}, evidence=EVIDENCE, budget=ledger, cooldown=0, clients=factory,
        extra={'configuration': configuration}, runtime=runtime,
        cards={b: z.CARD_TEXT if b == p.ZEBRA else instruction_start.pins()[b]['text']
               for b in p.active_benches(configuration)})
    model = p.CHAINS[chain_id]
    endpoint = budgets.endpoint(own, budgets.solver_scopes(chain_id, None, None, 'test'),
        client=factory(model, bench), max_tokens_bound=p.ledger_bound(model, bench,
            branch='N' if chain_id == 'D' else None, longest=60000 if chain_id == 'D' else None),
        sleep=lambda _: None)
    ctx = units.cell_context(own, root / configuration / chain_id / bench / 'attempt-1', endpoint)
    ctx.worker = lambda b: authored_worker(b)
    return ctx, endpoint.client


@pytest.mark.parametrize('chain_id', ['G', 'D'])
@pytest.mark.parametrize('bench', ['searchqa', 'officeqa', p.ZEBRA, 'spreadsheetbench', 'alfworld'])
def test_both_chain_all_bench_request_bytes_match_main_v5_and_note_is_only_difference(
        tmp_path, monkeypatch, chain_id, bench):
    task, replies = authored_task(bench, tmp_path / 'public-fixtures', monkeypatch)
    # The native scorer is an authored boundary; no Docker, reference data or real environment is used.
    original_score = backends.score
    monkeypatch.setattr(backends, 'score', lambda b, public, private, prediction, **kw:
        {'status': 'pass', 'reason': 'authored_sheet_score', 'metrics': {}}
        if b == 'spreadsheetbench' else original_score(b, public, private, prediction, **kw))
    compared = {}
    for configuration in (p.MAIN_V5, CONFIG):
        compared[configuration] = {}
        for arm in ('C', 'F'):
            ctx, fake = context(tmp_path / arm, configuration, chain_id, bench, monkeypatch)
            fake.replies = list(replies)
            task_id = task['task_id']
            unit = chain_id + '/test/' + bench
            row = {'id': cells.cell_id(unit, arm, task_id, 0), 'unit': unit, 'arm': arm,
                   'benchmark': bench, 'task_id': task_id, 'run': 0}
            choice = cells.Arm('candidate', authored_package(bench)) if arm == 'F' else cells.Arm(
                'card', package.empty(step=chain_id + '/card', evidence=EVIDENCE))
            full = cells.run_cell(ctx, row, task, choice,
                                 store=evaluation.EvaluationStore(ctx.attempt, evidence=EVIDENCE))
            persisted = read_json(ctx.attempt / 'cells' / (row['id'] + '.json'))
            assert full['stop'] is None and fake.requests
            assert persisted['configuration'] == configuration
            assert persisted['solver_route']['route'] == ('B' if chain_id == 'D' else None)
            hashes = [hashlib.sha256((system + '\0' + user).encode()).hexdigest()
                      for system, user in fake.messages]
            assert [call['request_sha256'] for call in persisted['calls']] == hashes
            assert len(persisted['calls']) == len(replies)
            assert fake.constructor[0] == str(tmp_path / arm / ('unread-route.env' if chain_id == 'D' else 'unread-roles'))
            compared[configuration][arm] = fake.requests
    assert compared[CONFIG] == compared[p.MAIN_V5]
    for without_note, with_note in zip(compared[CONFIG]['C'], compared[CONFIG]['F']):
        card, final = json.loads(without_note), json.loads(with_note)
        assert card['temperature'] == 0 and card['max_tokens'] == p.solver_tokens(p.CHAINS[chain_id], bench)
        assert card['messages'][0] == final['messages'][0]
        if bench == p.ZEBRA:
            assert final['messages'][1]['content'].startswith(card['messages'][1]['content'] + z.NOTES_SUFFIX)
        else:
            bare, noted = json.loads(card['messages'][1]['content']), json.loads(final['messages'][1]['content'])
            assert NOTE in noted.pop(p.NOTES_KEY)
            assert noted == bare
        final['messages'][1]['content'] = card['messages'][1]['content']
        assert wire(final) == wire(card)


def test_owner_consent_matches_main_v5_shape(tmp_path):
    write_json(tmp_path / 'consent.json', consent())
    assert evaluation.consent(tmp_path, CONFIG) == evaluation.consent(tmp_path, p.MAIN_V5) == consent()


@pytest.mark.parametrize('change', [
    {'test_evaluation': False}, {'sheet_test_qualification': False}, {'by': 'writer'}, {'date': ''}, {'note': ''},
    {'multi_arm_arms': ['F', 'C']}, {'multi_arm_arms': ['F', 'C', 'B']},
    {'multi_arm_arms': ['C', 'F', 'B', 'stages']}, {'multi_arm_arms': ['F', 'C', 'B', 'stages', 'S3']},
    {'multi_arm_arms': ['F', 'C', 'B', 'stages', 'stages']}, {'extra': True},
])
def test_other_consent_refused(tmp_path, change):
    write_json(tmp_path / 'consent.json', {**consent(), **change})
    with pytest.raises(ValueError, match='consent'):
        evaluation.consent(tmp_path, CONFIG)


def authored_units():
    return {bench: {(arm, 'authored-%d' % i, 0): cell(
        'pass' if arm != 'B' and (arm != 'C' or i % 3) else 'fail',
        enabled=('fixed-zebra',) if arm in ('S3', 'F') else (),
        room='room-%d' % (i // 3) if bench == 'alfworld' else None)
        for arm in ('F', 'C', 'B', 'S3') for i in range(12)} for bench in p.read_benches(CONFIG)}


def test_five_bench_primary_contrasts_rows_and_upper_bound_labels(fast_statistics):
    result = readout.readout(authored_units(), learned=[], procedures={}, label='authored', evidence=EVIDENCE,
                             stages=ROWS, configuration=CONFIG)
    assert result['evidence_kind'] == 'post_hoc_selected_upper_bound'
    assert result['learned'] == [] and result['imported'] == [p.ZEBRA, 'alfworld']
    assert result['q1_home'] is None
    assert set(result['stages']) == set(p.read_benches(CONFIG))
    assert all([row['arm'] for row in rows] == ROWS for rows in result['stages'].values())
    assert all(set(contrasts) == {'F-C', 'C-B', 'F-B'} for contrasts in result['contrasts'].values())
    assert [row['related_benches'] for row in result['stage_questions']] == [
        ['officeqa'], ['searchqa', 'spreadsheetbench'], [], ['officeqa'], []]
    assert result['stage_questions'][3]['reuses_row'] == 3
    with pytest.raises(ValueError, match='no newly learned'):
        readout.readout(authored_units(), learned=[p.ZEBRA], procedures={}, label='authored', evidence=EVIDENCE,
                        stages=ROWS, configuration=CONFIG)


def test_report_classifies_both_fixed_chains_as_imported_not_learned(tmp_path, monkeypatch, fast_statistics):
    root = tmp_path / 'run'
    structure = imp.structural_smoke(root)
    for chain_id in p.CHAINS:
        write_json(root / chain_id / 'test-read.json', p.record('test-read', EVIDENCE, {
            'status': 'read', 'package_sha256': structure['packages'][chain_id]['F']}))
        for bench in p.read_benches(CONFIG):
            write_json(root / chain_id / 'test' / bench / 'unit.json', {'authored_fixture': True})
    opened_chains = []
    def authored_unseal(run_root, chain_root, chain_id, unit_roots, **kwargs):
        assert kwargs['configuration'] == CONFIG
        assert [path.name for path in unit_roots] == list(p.read_benches(CONFIG))
        opened_chains.append(chain_id)
        return {'units': authored_units(), 'label': 'authored',
                'stages': {bench: ROWS for bench in p.read_benches(CONFIG)}}
    monkeypatch.setattr(evaluation, 'unseal', authored_unseal)
    found = readout.report({'root': str(root), p.RECORD_HASH: 'authored-run', 'evidence': EVIDENCE,
                            'configuration': CONFIG}, out=tmp_path / 'readout')
    assert set(found) == set(opened_chains) == {'G', 'D'}
    for chain_id in p.CHAINS:
        value = read_json(tmp_path / 'readout' / ('readout-' + chain_id + '.json'))
        assert value['learned'] == [] and value['imported'] == [p.ZEBRA, 'alfworld']
        assert value['evidence_kind'] == 'post_hoc_selected_upper_bound'


def test_direct_unit_checks_step_rows_before_sheet_qualification_or_clients(tmp_path, monkeypatch):
    st = chain_setting(tmp_path, chain_='G', consent=False)
    st.extra['configuration'] = CONFIG
    write_json(st.shared / 'consent.json', consent())
    monkeypatch.setattr(evaluation, 'setting_of', lambda *a, **kw: st)
    monkeypatch.setattr(chain, 'confirmation', lambda *a, **kw: None)
    monkeypatch.setattr(evaluation, 'prepare_test_qualification', lambda *a, **kw: pytest.fail('Malformed steps reached qualification'))
    start = package.empty(step='G/s0', evidence=st.evidence)
    spec = tmp_path / 'spec.json'
    root = st.root / 'G/test/searchqa'
    write_json(spec, {'chain': 'G', 'bench': 'searchqa', 'package_sha256': start.sha256, 'unit_root': str(root)})
    with pytest.raises(ValueError, match='Every step'):
        evaluation.run_unit_spec({'data': {'pinned': {}}}, spec=spec)
    assert not root.exists()
