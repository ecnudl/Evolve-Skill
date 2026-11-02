"""Cross cards and request classes on authored items; no providers or real datasets."""
from contextlib import contextmanager
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import cells, evaluation, package, profiles as p, readout, v217_implant, v218_read, v219_read
from tests.execskill_fakes_env import FakeSandbox
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v214_evaluation import consent as old_consent
from tests import test_execskill_v217i_evaluation as parent

CHILD = p.CROSS_V5
EVIDENCE = 'engineering_fixture'
PAIRS = [(t, s) for t in p.MAIN_V5_ORDER for s in p.MAIN_V5_ORDER if s != t]


def consent():
    return {**old_consent(), 'date': '2026-11-02', 'multi_arm_arms': ['F', 'C', 'B', 'cross'],
            'note': 'Owner request for the package plus each frozen source card on other panels.'}


@pytest.mark.parametrize('bench', p.MAIN_V5_ORDER)
def test_exact_cross_arm_labels_and_scoring_sides(bench):
    labels = v219_read.labels(bench)
    assert labels == ['F', 'C', 'B'] + ['X_'+source for source in p.MAIN_V5_ORDER if source != bench]
    assert len(labels) == 7 and 'X_'+bench not in labels
    assert {label: readout.side(label) for label in labels} == {
        label: 'H' if label in ('C', 'B') else 'L' for label in labels}


@pytest.mark.parametrize('changes', [{}, {'test_evaluation': False}, {'sheet_test_qualification': False},
    {'by': 'writer'}, {'date': ''}, {'date': '  '}, {'note': ''}, {'extra': True},
    {'multi_arm_arms': ['F', 'C', 'B']}, {'multi_arm_arms': ['F', 'C', 'B', 'stages']},
    {'multi_arm_arms': ['C', 'F', 'B', 'cross']}, {'multi_arm_arms': ['F', 'C', 'B', 'cross', 'X_searchqa']},
    {'multi_arm_arms': ['F', 'C', 'B', 'cross', 'cross']}])
def test_exact_owner_consent_shape_only(tmp_path, changes):
    value = {**consent(), **changes}
    write_json(tmp_path/'consent.json', value)
    if changes:
        with pytest.raises(ValueError, match='consent'):
            evaluation.consent(tmp_path, CHILD)
    else:
        assert evaluation.consent(tmp_path, CHILD) == value
        for earlier in (p.IMPLANT_V5, p.MAIN_V6):
            with pytest.raises(ValueError, match='consent'):
                evaluation.consent(tmp_path, earlier)


def scorer(monkeypatch):
    original = backends.score
    monkeypatch.setattr(backends, 'score', lambda bench, public, private, prediction, **kw:
        {'status': 'pass', 'reason': 'authored_sheet_score', 'metrics': {}}
        if bench == 'spreadsheetbench' else original(bench, public, private, prediction, **kw))


@pytest.mark.parametrize('target, source', PAIRS)
@pytest.mark.parametrize('active', [False, True])
def test_source_card_is_substituted_in_exact_target_shell_slot(tmp_path, monkeypatch, target, source, active):
    """Compare C for an empty package and F for an active package; hold the package fixed."""
    task, replies = parent.authored_task(target, tmp_path/'public', monkeypatch)
    scorer(monkeypatch)
    chosen = parent.authored_package(target) if active else package.empty(step='G/card', evidence=EVIDENCE)
    observed = {}
    for label in ('X_'+source, 'F' if active else 'C'):
        ctx, fake = parent.context(tmp_path/label, CHILD, 'G', target, monkeypatch)
        ctx.environment = None  # Environment acquisition has independent authored lock tests.
        if not label.startswith('X_'):
            ctx.cards[target] = v219_read.cards()[source]
        fake.replies = list(replies)
        row = {'id': cells.cell_id('G/test/'+target, label, task['task_id'], 0),
               'unit': 'G/test/'+target, 'arm': label, 'benchmark': target, 'task_id': task['task_id'], 'run': 0}
        full = cells.run_cell(ctx, row, task, cells.Arm('card' if label == 'C' else 'candidate', chosen),
                              store=evaluation.EvaluationStore(ctx.attempt, evidence=EVIDENCE))
        assert full['stop'] is None and fake.requests
        stored = read_json(ctx.attempt/'cells'/(row['id']+'.json'))
        assert stored['card_source'] == (source if label.startswith('X_') else target)
        assert stored['arm_kind'] == ('card' if label == 'C' else 'candidate')
        assert stored['package_sha256'] == chosen.sha256
        observed[label] = (fake.requests, fake.messages)
    assert observed['X_'+source] == observed['F' if active else 'C']
    if target == p.ZEBRA:
        assert all(v219_read.cards()[source] not in system for system, _ in observed['X_'+source][1])
    elif source == p.ZEBRA:
        assert v219_read.cards()[source] == 'Follow the format in the user message.'
        assert any(v219_read.cards()[source] in system for system, _ in observed['X_'+source][1])


def fixed_worker(final):
    # Execute only the reviewed public fixture programs; keep their actual predicates and ALF hooks.
    # Zebra note contents are an authored stable note to isolate sharing from puzzle-solving ability.
    hooks = {}
    for proc in final.procedures:
        namespace = {}
        exec(compile(proc.source, '<pinned-public-implant-fixture>', 'exec'), namespace)
        hooks[proc.id] = {hook: namespace[hook] for hook in proc.hooks}
        if proc.origin == p.ZEBRA:
            hooks[proc.id]['before_call'] = lambda view, state: {'facts': ['Public clue positions were inspected.']}
    return FakeSandbox(hooks)


def authored_read(root, monkeypatch, chain_id, bench):
    task, replies = parent.authored_task(bench, root/'public', monkeypatch)
    if bench == p.ZEBRA:
        task['public']['question'] += '\n## Clues:\n1. House 1 has its listed attributes.'
    if bench == 'alfworld':
        task['public'] = {key: value for key, value in task['public'].items()
                          if key not in ('routing_view', 'routing_view_sha256')}
    scorer(monkeypatch)
    final = v217_implant.final_package(chain_id, EVIDENCE)
    card = package.empty(step=chain_id+'/card', evidence=EVIDENCE)
    ctx, fake = parent.context(root, CHILD, chain_id, bench, monkeypatch)
    ctx.environment = None
    ctx.worker = lambda _: fixed_worker(final)
    fake.replies = replies * 7
    if bench == 'alfworld':
        monkeypatch.setenv('ALFWORLD_DATA', ctx.runtime['alfworld']['alfworld_data'])
    @contextmanager
    def workers(found, item, **options):
        worker = fixed_worker(final).start(found, kind='cell', **options)
        try:
            yield worker
        finally:
            worker.close()
    unit = root/chain_id/'test'/bench
    ctx.attempt = unit/'attempt-1'
    shared = root/'shared'
    write_json(shared/'consent.json', consent())
    # Authored practice object only: no qualification or test registry access.
    monkeypatch.setattr(evaluation, 'test_tasks', lambda *args, **kwargs: [task])
    result = evaluation.evaluate(unit, run='authored-cross', shared=shared, pinned=None, chain=chain_id,
        bench=bench, arms=v219_read.arms(bench, final, card), context=ctx, workers=1, route_workers=workers,
        canaries=[], run_configuration=CHILD)
    records = [read_json(path) for path in (ctx.attempt/'cells').glob('*.json')]
    return unit, result, records, fake, final


@pytest.mark.parametrize('chain_id', ['G', 'D'])
@pytest.mark.parametrize('bench', p.MAIN_V5_ORDER)
def test_construction_reuse_and_records_on_all_five_authored_panels(tmp_path, monkeypatch, chain_id, bench):
    _, result, records, fake, final = authored_read(tmp_path, monkeypatch, chain_id, bench)
    assert len(records) == 7 and set(result['packages']) == set(v219_read.labels(bench))
    assert 'stages' not in result and result['twins'] == 0
    by_id = {row['cell']['id']: row for row in records}
    by_arm = {row['cell']['arm']: row for row in records}
    expected_dispatches = 7 if bench == 'alfworld' else 2 if bench == p.ZEBRA else 6
    assert sum(row['shared_with'] is None for row in records) == expected_dispatches
    for label, row in by_arm.items():
        assert row['card_source'] == v219_read.card_source(bench, label)
        assert row['arm_kind'] == ('card' if label == 'C' else 'blank' if label == 'B' else 'candidate')
        if label.startswith('X_') or label == 'F':
            assert row['package_sha256'] == final.sha256
        if bench == 'alfworld':
            assert row['shared_with'] is None and row['calls'] and 'request_reuse' not in row
        elif label == 'F' and bench != p.ZEBRA:
            assert by_id[row['shared_with']]['cell']['arm'] == 'C'
            assert set(row['enabled']) <= {proc.id for proc in final.procedures if proc.origin == 'alfworld'}
            assert row['request_reuse']['source_arm'] == 'C'
        elif bench == p.ZEBRA and (label == 'B' or label.startswith('X_')):
            source = 'C' if label == 'B' else 'F'
            assert by_id[row['shared_with']]['cell']['arm'] == source
            assert row['request_reuse']['source_arm'] == source
            assert row['judge'] == by_arm[source]['judge'] and row['calls'] == []
        else:
            assert row['shared_with'] is None and row['calls']
        if row['calls']:
            assert all(call['request_sha256'] for call in row['calls'])
    if bench != 'alfworld':
        assert result['request_reuse']['dispatched_cells'] == expected_dispatches
        assert result['request_reuse']['fallback_cells'] == 0


def test_unseal_retains_card_sources_request_hashes_and_shared_arm(tmp_path, monkeypatch):
    unit, _, records, _, _ = authored_read(tmp_path, monkeypatch, 'D', 'officeqa')
    monkeypatch.setattr(evaluation, '_ended', lambda *_: True)
    monkeypatch.setattr(evaluation, 'continuation', lambda *_: None)
    monkeypatch.setattr(evaluation, '_root_scanned', lambda *a, **kw: {})
    monkeypatch.setattr(evaluation, '_marker', lambda *a, **kw: {'label': 'authored', 'later_reads': False})
    opened = evaluation.unseal(tmp_path, tmp_path/'D', 'D', [unit], run='authored-cross',
                               evidence=EVIDENCE, configuration=CHILD)
    assert 'stages' not in opened
    values = opened['units']['officeqa']
    for row in records:
        key = (row['cell']['arm'], row['cell']['task_id'], row['cell']['run'])
        assert values[key]['card_source'] == row['card_source']
        assert values[key]['arm_kind'] == row['arm_kind']
        assert values[key]['request_sha256'] == [call['request_sha256'] for call in row['calls']]
    item = records[0]['cell']['task_id']
    assert v218_read.identical_item(values, 'F', 'C', item)


def test_identical_cross_representatives_use_fixed_order_and_never_blank():
    labels = ['C', 'F', *v219_read.cross_labels('officeqa'), 'B']
    identity = lambda text: {'request_sha256': text, 'post_call': [], 'faults': [], 'enabled': []}
    found = {label: identity('own' if label in ('C', 'F') else 'same-cross') for label in labels}
    sources = v218_read.representatives(found, labels, bench='officeqa')
    assert sources == {'C': None, 'F': 'C', 'X_searchqa': None, 'X_zebralogic': 'X_searchqa',
                       'X_spreadsheetbench': 'X_searchqa', 'X_alfworld': 'X_searchqa', 'B': 'X_searchqa'}
    assert 'B' not in sources.values()
