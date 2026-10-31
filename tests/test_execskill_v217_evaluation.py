"""Authored-only G read: exact inherited requests, consent, sharing and upper-bound labels."""
from contextlib import contextmanager
import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts.weak_solver_probe import Client, MODELS
from skillopt.coevo5.budget import Budget
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import (budgets, cells, chain, client, evaluation, instruction_start,
                               manifest, package, profiles as p, readout, slots, solver, units,
                               v217_import as imp, zebralogic as z)
from skillopt.validator_pilot.api import digest
from tests import test_execskill_v212_evaluation as parent_tests
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_chain import Launch, setting as chain_setting
from tests.test_execskill_readout import cell
from tests.test_execskill_zpc_pipeline import SourceWorker, fixture_pool, offline, public_grid  # noqa: F401

CHILD = p.ZEBRA_HP_G3R2
EVIDENCE = 'engineering_fixture'
NOTE = 'Use the public clues.'
SOURCE = '''def applies(view):
    return "fixture structural zero" not in view["question"]
def before_call(view, state):
    if "fixture silent" in view["question"]:
        return {}
    return {"facts": ["Use the public clues."]}
'''


def authored_package():
    procedure = package.Procedure('fx-zebra-v217', p.ZEBRA, NOTE, ('applies', 'before_call'),
        SOURCE, EVIDENCE, header='Authored helper', max_note_chars=200,
        policy_version=p.POLICY_VERSIONS[CHILD])
    return package.Package((procedure,), 'G/s1-zebralogic', EVIDENCE)


def consent():
    return {**parent_tests.consent(), 'date': '2026-10-31',
            'note': 'Delegated owner consent for the fixed G round-2 solver read.'}


def byte_string(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


class BodyOnlyClient(Client):
    """Keep the production body method; replace credential construction and all I/O."""
    def __init__(self, repo, model, *, proxy, max_tokens, read_timeout, transport=None):
        self.constructor = (repo, model, proxy, max_tokens, read_timeout, transport)
        self.backend, self.thinking, self.effort, _, self.response_model_ids = MODELS[model]
        self.model, self.max_tokens = model, max_tokens
        self.requests, self.messages = [], []
        self.remaining_undelivered = 0

    def call(self, system, user):
        self.requests.append(byte_string(self.body(system, user)))
        self.messages.append((system, user))
        if self.remaining_undelivered:
            self.remaining_undelivered -= 1
            return {'ok': False, 'response': None, 'finish_reason': None, 'usage': {},
                    'error_type': 'transport', 'attempts': [{'error': 'ReadTimeout'}]}
        view = z.parse_user(user)
        return {'ok': True, 'response': json.dumps({'solution': public_grid(view)}),
                'finish_reason': 'stop', 'error_type': None, 'returned_model': self.model,
                'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
                'attempts': [{'status': 200}]}


def context(tmp_path, monkeypatch, configuration, *, attempt=None):
    monkeypatch.setattr(client, 'Client', BodyOnlyClient)
    monkeypatch.setattr(client, 'unpooled', lambda found, **kw: found)
    # A nonexistent authored roles-repo path: the fake constructor never opens it.
    model = p.CHAINS['G']
    given = {'configuration': configuration, 'root': str(tmp_path),
             'clients': {'solver': {'G': {'model': model, 'env_path': str(tmp_path / 'roles-repo'),
                                        'proxy': client.GATEWAY}}, 'roles': manifest.ROLES}}
    factory = manifest._clients(given, 'G', transport=None)
    ledger = Budget(tmp_path / configuration / 'ledger', sleep=lambda _: None)
    ledger.declare(budgets.chain_caps('G', configuration))
    own = SimpleNamespace(slots=slots.pools(tmp_path / 'slots', poll=0.01, log=lambda _: None),
        sandbox={}, evidence=EVIDENCE, budget=ledger, cooldown=0, clients=factory,
        extra={'configuration': configuration}, runtime={p.ZEBRA: {}},
        cards={bench: z.CARD_TEXT if bench == p.ZEBRA else instruction_start.pins()[bench]['text']
               for bench in p.active_benches(configuration)})
    endpoint = budgets.endpoint(own, budgets.solver_scopes('G', None, None, 'test'),
        client=factory(model, p.ZEBRA), max_tokens_bound=p.ledger_bound(model, p.ZEBRA), sleep=lambda _: None)
    ctx = units.cell_context(own, attempt or tmp_path / configuration / 'attempt-1', endpoint)
    ctx.worker = lambda _: SourceWorker()
    return ctx, endpoint.client


def run_authored(ctx, task, arm, *, unit='G/test/zebralogic'):
    row = {'id': cells.cell_id(unit, arm, task['task_id'], 0), 'unit': unit,
           'arm': arm, 'benchmark': p.ZEBRA, 'task_id': task['task_id'], 'run': 0}
    choice = cells.Arm('candidate', authored_package()) if arm == 'F' else cells.Arm(
        'card', package.empty(step='G/card', evidence=EVIDENCE))
    return cells.run_cell(ctx, row, task, choice, store=evaluation.EvaluationStore(ctx.attempt, evidence=EVIDENCE))


@pytest.mark.parametrize('task_index', [0, 80, 199])
@pytest.mark.parametrize('undelivered', [0, 1])
def test_exact_main_v5_g_request_bytes_and_note_only_difference(tmp_path, monkeypatch, task_index, undelivered):
    task = fixture_pool()[task_index]
    compared = {}
    for configuration in (p.MAIN_V5, CHILD):
        compared[configuration] = {}
        for arm in ('C', 'F'):
            ctx, fake = context(tmp_path, monkeypatch, configuration,
                                attempt=tmp_path / configuration / arm / 'attempt-1')
            fake.remaining_undelivered = undelivered
            full = run_authored(ctx, task, arm)
            persisted = read_json(ctx.attempt / 'cells' / (full['cell']['id'] + '.json'))
            assert full['stop'] is None and full['final']['token'] == 'pass'
            assert persisted['configuration'] == configuration
            assert persisted['solver_route'] == {'route': None, 'model': 'glm-5.3'}
            assert persisted['returned_model'] == 'glm-5.3'
            assert len(fake.requests) == 1 + undelivered
            assert all(request == fake.requests[0] for request in fake.requests)
            assert fake.constructor == (str(tmp_path / 'roles-repo'), 'glm-5.3', client.GATEWAY, 65536, 2400, None)
            assert ctx.nominal == {} and ctx.endpoint.max_tokens == 65536
            assert ctx.cards[p.ZEBRA] == z.CARD_TEXT
            system, user = fake.messages[-1]
            expected_hash = hashlib.sha256((system + '\x00' + user).encode()).hexdigest()
            assert persisted['calls'] == [{'purpose': 'first', 'request_sha256': expected_hash,
                'reply_sha256': hashlib.sha256(full['sends'][-1]['receipt']['response'].encode()).hexdigest(),
                'completion_tokens': 5}]
            assert persisted['sends'] == 1 + undelivered
            compared[configuration][arm] = fake.requests[0]
    assert compared[CHILD] == compared[p.MAIN_V5]
    card, proc = (json.loads(compared[CHILD][arm]) for arm in ('C', 'F'))
    assert card['model'] == 'glm-5.3' and card['max_tokens'] == 65536
    assert card['temperature'] == 0 and card['thinking'] == {'type': 'enabled'}
    assert card['reasoning_effort'] == 'low'
    assert card['messages'][0] == {'role': 'system', 'content': solver.QA_SYSTEM}
    assert card['messages'][1]['content'] == z.render_user(task['public'])
    assert proc['messages'][1]['content'].startswith(card['messages'][1]['content'] + z.NOTES_SUFFIX)
    assert NOTE in proc['messages'][1]['content'][len(card['messages'][1]['content']):]
    proc['messages'][1]['content'] = card['messages'][1]['content']
    assert byte_string(proc) == byte_string(card)


def test_exact_consent_and_legacy_implicit_consent_stays_frozen(tmp_path):
    write_json(tmp_path / 'consent.json', consent())
    assert evaluation.consent(tmp_path, CHILD) == consent()
    with pytest.raises(ValueError, match='consent'):
        evaluation.consent(tmp_path)


@pytest.mark.parametrize('changes', [
    {'multi_arm_arms': ['F', 'C', 'B']}, {'multi_arm_arms': ['F', 'C', 'P_F']},
    {'multi_arm_arms': ['F', 'C', 'T_F']}, {'multi_arm_arms': ['F', 'C', 'withholding']},
    {'multi_arm_arms': ['F', 'C', 'C']}, {'multi_arm_arms': ['C']}, {'multi_arm_arms': ['C', 'F']},
    {'test_evaluation': False}, {'sheet_test_qualification': True}, {'by': 'agent'},
    {'note': ''}, {'date': ''}, {'extra': True},
])
def test_other_consent_is_refused(tmp_path, changes):
    write_json(tmp_path / 'consent.json', {**consent(), **changes})
    with pytest.raises(ValueError, match='consent'):
        evaluation.consent(tmp_path, CHILD)


@contextmanager
def workers(found, item, **kw):
    worker = SourceWorker().start(found, kind='cell')
    try:
        yield worker
    finally:
        worker.close()


def test_g_fc_interleaving_zero_dispatch_and_hashes(tmp_path, monkeypatch):
    tasks = fixture_pool()[:4]
    tasks[0]['public']['question'] += '\nfixture structural zero'
    tasks[1]['public']['question'] += '\nfixture silent'
    root, shared = tmp_path / 'G/test/zebralogic', tmp_path / 'shared'
    write_json(shared / 'consent.json', consent())
    ctx, fake = context(tmp_path, monkeypatch, CHILD, attempt=root / 'attempt-1')
    def panel(pinned, bench, *, access):
        assert bench == p.ZEBRA
        return tasks, {'panel_hash': digest(tasks), 'excluded_without_pages': [], 'source_files': None}
    result = evaluation.evaluate(root, run='authored-v217', shared=shared, pinned=None, chain='G', bench=p.ZEBRA,
        arms={'F': cells.Arm('candidate', authored_package()),
              'C': cells.Arm('card', package.empty(step='G/card', evidence=EVIDENCE))},
        context=ctx, workers=1, route_workers=workers, canaries=[], panel=panel, run_configuration=CHILD)
    records = [read_json(path) for path in (ctx.attempt / 'cells').glob('*.json')]
    assert result['counts']['by_arm'] == {'C': 4, 'F': 4}
    assert result['twins'] == 0 and result['structural_zero'] == 1
    assert len(records) == 8 and len(fake.requests) == 7
    assert {row['cell']['arm'] for row in records} == {'F', 'C'}
    assert {row['cell']['run'] for row in records} == {0}
    assert all(row['configuration'] == CHILD for row in records)
    assert all(len(call['request_sha256']) == 64 for row in records for call in row['calls'])
    shares = [row for row in records if row['shared_with'] is not None]
    assert len(shares) == 1 and shares[0]['cell']['arm'] == 'F' and shares[0]['calls'] == []
    assert next(row for row in records if row['cell']['id'] == shares[0]['shared_with'])['cell']['arm'] == 'C'
    silent = {row['cell']['arm']: row for row in records if row['cell']['task_id'] == tasks[1]['task_id']}
    assert all(row['shared_with'] is None and len(row['calls']) == 1 for row in silent.values())
    assert silent['F']['calls'][0]['request_sha256'] == silent['C']['calls'][0]['request_sha256']
    assert not (ctx.attempt / 'transient').exists()


@pytest.mark.parametrize('refusal', ['D', 'F=C'])
def test_invalid_read_refused_before_panel_or_dispatch(tmp_path, monkeypatch, refusal):
    root, shared = tmp_path / 'read', tmp_path / 'shared'
    write_json(shared / 'consent.json', consent())
    ctx, fake = context(tmp_path, monkeypatch, CHILD, attempt=root / 'attempt-1')
    card = package.empty(step='G/card', evidence=EVIDENCE)
    def forbidden(*a, **kw):
        pytest.fail('Invalid read accessed a panel or worker')
    with pytest.raises(ValueError, match='chain G ZebraLogic only' if refusal == 'D' else 'F = C'):
        evaluation.evaluate(root, run='authored-v217', shared=shared, pinned=None,
            chain='D' if refusal == 'D' else 'G', bench=p.ZEBRA,
            arms={'F': cells.Arm('candidate', card if refusal == 'F=C' else authored_package()),
                  'C': cells.Arm('card', card)}, context=ctx, workers=1,
            route_workers=forbidden, canaries=[], panel=forbidden, run_configuration=CHILD)
    assert not fake.requests and not ctx.attempt.exists()


def test_chain_g_import_reads_once_without_learning(tmp_path, monkeypatch):
    setting = chain_setting(tmp_path, chain_='G', consent=False)
    setting.extra.update(configuration=CHILD, test_read_terms={'G': {p.ZEBRA: '1000'}},
                         **{imp.PIN_KEY: imp.pins()})
    write_json(setting.shared / 'consent.json', consent())
    monkeypatch.setattr(chain, 'first_call', lambda *a, **kw: None)
    launch = Launch(tmp_path)
    assert chain.run(setting, 'G', learn=imp.import_step, launch=launch) == {'status': 'complete'}
    step = p.verified(read_json(setting.root / 'G/s1-zebralogic/step.json'), 'step')
    read = p.verified(read_json(setting.root / 'G/test-read.json'), 'test-read')
    assert step['decision'] == step['learning'] == read['learning'] == 'import'
    assert step['decision_sha256'] is None and step['units'] == {}
    assert read['arms'] == ['F', 'C'] and read['evidence_kind'] == 'post_hoc_selected_upper_bound'
    assert read['gate']['cost_check'] == 'not_applicable_no_learning_run'
    assert [spec['bench'] for spec in launch.specs] == [p.ZEBRA]
    assert chain.run(setting, 'G', learn=imp.import_step, launch=launch) == {'status': 'complete'}
    assert len(launch.specs) == 1


def test_report_imported_upper_bound_has_only_registered_fc(tmp_path, monkeypatch, fast_statistics):
    root = tmp_path / 'root'
    setting = chain_setting(tmp_path, chain_='G', consent=False)
    setting.extra.update(configuration=CHILD, **{imp.PIN_KEY: imp.pins()})
    final, _ = imp.import_step(setting, root / 'G', 'G', 1, p.ZEBRA,
                              package.empty(step='G/s0', evidence=EVIDENCE))
    write_json(root / 'G/test-read.json', p.record('test-read', EVIDENCE,
        {'status': 'read', 'package_sha256': final.sha256}))
    rows = {(arm, 'authored-%d' % i, 0): cell('pass' if arm == 'F' else 'fail')
            for arm in ('F', 'C') for i in range(4)}
    def unseal(*a, **kw):
        assert kw['configuration'] == CHILD
        return {'units': {p.ZEBRA: rows}, 'label': 'engineering'}
    monkeypatch.setattr(evaluation, 'unseal', unseal)
    out = tmp_path / 'readout'
    hashes = readout.report({'root': str(root), p.RECORD_HASH: 'authored-v217', 'evidence': EVIDENCE,
        'configuration': CHILD, 'data': {'launchable_chains': ['G']}}, out=out)
    value = p.verified(read_json(out / 'readout-G.json'), 'readout')
    assert hashes == {'G': value[p.RECORD_HASH]}
    assert value['evidence_kind'] == 'post_hoc_selected_upper_bound'
    assert value['imported'] == [p.ZEBRA] and value['learned'] == [] and value['q1_home'] is None
    assert set(value['contrasts'][p.ZEBRA]) == {'F-C'}
    assert set(value['arms'][p.ZEBRA]) == {'F', 'C'}
    assert value['placebo'] == value['code_vs_text'] == value['twins'] == {'removed': True}
