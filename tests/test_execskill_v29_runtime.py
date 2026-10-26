"""v2.9 runtime contract on authored in-process workers; no external calls."""
from contextlib import contextmanager
from dataclasses import replace
import hashlib

import pytest

from skillopt.execskill import donors, notes, placebo, policy, replay, router, solver
from skillopt.execskill.package import Package, Procedure, default_applies, empty
from skillopt.execskill.sandbox.client import Worker
from tests.execskill_fakes_env import FakeSandbox, Script
from tests.test_execskill_replay import qa_trajectories, alf_trajectory
from tests.test_execskill_v28_execution import procedure as old_procedure
from tests.test_execskill_zpc_pipeline import offline

FACT = 'There are 3 units. Answer with JSON.'
SOURCE = 'def before_call(view, state):\n    return {"facts": [' + repr(FACT) + ']}\n'


def procedure(source=SOURCE, **changes):
    return replace(old_procedure(source=source, hooks=('before_call',)),
                   policy_version=policy.POLICY_VERSION_V29, **changes)


def worker(proc, fields=None):
    def forbidden(*args):
        raise AssertionError('Missing applies must never enter a worker')
    hooks = {'applies': forbidden, 'before_call': lambda *args: fields or {'facts': [FACT]},
             'alf_before_step': lambda *args: {'fields': fields or {'facts': [FACT]}, 'discourage': []}}
    return FakeSandbox({proc.id: hooks})


def test_optional_applies_router_replay_and_live_have_no_worker_predicate_call():
    proc = procedure()
    package = replay.solo(proc)
    entry = replay.inputs_of(qa_trajectories()[0])
    instance = worker(proc).start(package, kind='cell')
    route = router.route(package, entry['bench'], entry['view'], instance)
    assert route.enabled == route.fired == (proc.id,)
    assert route.per_procedure[proc.id]['applies'] == 'default_true'
    assert instance.calls == []
    out = replay.replay(instance, proc, entry)
    assert out.applies == 'default_true' and out.notes
    assert all(call[1] != 'applies' for call in instance.calls)
    call = Script(['<answer>3</answer>'])
    prediction = solver.solve(entry['bench'], entry['request_view'], 'Read input', package, call,
                              worker=worker(proc))
    assert prediction['shell']['route']['per_procedure'][proc.id]['applies'] == 'default_true'
    assert FACT in call.requests[0][1]


def test_optional_applies_respects_withholding_shadow_firing():
    proc = procedure()
    package = replay.solo(proc)
    route = router.route(package, 'searchqa', {}, worker(proc), withhold={proc.id})
    assert route.enabled == () and route.fired == (proc.id,)
    assert route.per_procedure[proc.id] == {
        'applies': 'default_true', 'enabled': False, 'withheld': True,
        'restored': False, 'shadow_fired': True, 'fault': None}


def test_default_uses_top_level_definition_not_text_or_declaration():
    source = 'def before_call(view, state):\n    def applies(view):\n        return False\n    return {}\n'
    assert default_applies(procedure(source))
    source = 'def applies(view):\n    return False\n' + SOURCE
    proc = procedure(source, hooks=('applies', 'before_call'))
    assert not default_applies(proc)
    fake = FakeSandbox({proc.id: {'applies': lambda view: False}})
    assert router.route(replay.solo(proc), 'searchqa', {}, fake.start(replay.solo(proc), kind='cell')).enabled == ()


def test_optional_applies_acceptance_plan_records_firing():
    proc = procedure()
    parent = empty(step='fixture-parent', evidence=proc.evidence)
    package = Package((proc,), step='fixture-candidate', evidence=proc.evidence, parent_sha256=parent.sha256)
    @contextmanager
    def workers(package, item):
        yield worker(proc).start(package, kind='cell')
    plan = router.plan(package, parent, 'searchqa', {'authored': {}}, workers,
                       unit='fixture', donors=('donor',), minimum={'items': 0, 'rooms': 0})
    assert plan['astar'] == ['authored']
    assert plan['routes']['authored']['candidate']['fired'] == [proc.id]


def test_all_live_arms_keep_notes_and_log_identical_keyword_hashes():
    proc = procedure()
    package = replay.solo(proc)
    entry = replay.inputs_of(qa_trajectories()[0])
    values = []
    for arm in ('S', "S'", 'P_y', 'C'):
        # C has no procedure: a zero count; the same shared boundary handles every procedure arm.
        selected = empty(step='fixture-parent', evidence=proc.evidence) if arm == 'C' else package
        sham = {'procedures': {proc.id: {'before_call': {'facts': [FACT]}}}, 'seed': 'fixture'} if arm == 'P_y' else None
        call = Script(['<answer>3</answer>'])
        pred = solver.solve(entry['bench'], entry['request_view'], 'Read input', selected, call,
                            worker=worker(proc), placebo=sham)
        if arm == 'C':
            assert FACT not in call.requests[0][1]
            continue
        assert FACT in call.requests[0][1] and pred['shell']['faults'] == []
        values.append(pred['shell']['keyword_hits'])
    expected = notes.keyword_summary(notes.screen({'facts': [FACT]}, bench='searchqa', audited=True)[1])
    assert values == [expected] * 3


def test_replay_donor_and_placebo_use_the_same_log_only_screen():
    proc = procedure()
    package = replay.solo(proc)
    entry = replay.inputs_of(qa_trajectories()[0])
    out = replay.replay(worker(proc).start(package, kind='cell'), proc, entry)
    assert FACT in out.notes[0]['text']
    faults = []
    content = donors.procedure_outputs(worker(proc).start(package, kind='cell'), proc,
        {'id': 'donor', 'item': 'item', 'view': entry['request_view'], 'report': None, 'steps': None},
        bench='searchqa', faults=faults)
    assert content == {'before_call': {'facts': [FACT]}}
    expected = notes.keyword_summary(notes.screen({'facts': [FACT]}, bench='searchqa', audited=True)[1])
    assert out.summary()['keyword_hits'] == notes.keyword_summary(faults) == expected
    assert all(f.get('informational') for f in faults)
    rendered = placebo.rendered(content['before_call'], bench='searchqa', header='', outcome_judged=True, audited=True)
    sham, band = placebo.sham_fields([content['before_call']], rendered, bench='searchqa', header='', cap=1500,
                                    outcome_judged=True, audited=True)
    assert sham == content['before_call'] and band['chars'] == rendered


@pytest.mark.parametrize('bad', [{'warnings': ['x' * 201]}, {'warnings': 1}, {'unknown': []},
                                  {'warnings': ['<answer>3</answer>']}])
def test_log_only_never_bypasses_fault_or_answer_channel_suppression(bad):
    fields = {'facts': [FACT], **bad}
    proc = procedure()
    package = replay.solo(proc)
    entry = replay.inputs_of(qa_trajectories()[0])
    call = Script(['<answer>3</answer>'])
    pred = solver.solve(entry['bench'], entry['request_view'], 'Read input', package, call,
                        worker=worker(proc, fields))
    assert FACT not in call.requests[0][1] and pred['shell']['faults']
    out = replay.replay(worker(proc, fields).start(package, kind='cell'), proc, entry)
    assert not out.notes
    assert placebo.rendered(fields, bench='searchqa', header='', outcome_judged=True, audited=True) == 0


def test_sentence_hashes_and_header_use_the_same_splitter():
    text = '- There are 3 units.\n* Answer with JSON.'
    assert notes.sentence_elements(text) == ['There are 3 units.', 'Answer with JSON.']
    rows = notes.keyword_hits(text, bench='zebralogic')
    assert [row['sentence_sha256'] for row in rows] == [
        hashlib.sha256(sentence.encode()).hexdigest() for sentence in notes.sentence_elements(text)]
    header, events = notes.screen_header(text, audited=True, bench='zebralogic')
    assert header == text and notes.keyword_summary(events) == {
        'count': sum(row['count'] for row in rows),
        'sentences': [{'sentence_sha256': row['sentence_sha256'], 'count': row['count']} for row in rows]}


def test_applies_default_alfworld_live_and_replay():
    source = 'def alf_before_step(view, state):\n    return {"fields": {"facts": [' + repr(FACT) + ']}, "discourage": []}\n'
    proc = procedure(source, origin='alfworld', hooks=('alf_before_step',))
    package = replay.solo(proc)
    entry = replay.inputs_of(alf_trajectory())
    out = replay.replay(worker(proc).start(package, kind='cell'), proc, entry)
    assert out.applies == 'default_true' and out.notes
    assert all(note['text'].endswith(FACT) for note in out.notes)


def test_v29_worker_seed_and_policy_roundtrip():
    proc = procedure()
    assert proc.to_json()['version'].endswith('procedure-v2-9')
    assert Procedure.from_json(proc.to_json()) == proc
    runtime = Worker(hashseed=1).start(replay.solo(proc), kind='cell')
    assert runtime.hashseed == 0
    runtime.close()


@pytest.mark.parametrize('arm_name,arm_kind', [('S', 'parent'), ("S'", 'candidate'), ('P_y', 'placebo_y'), ('C', 'card')])
def test_cell_trajectory_and_sealed_test_record_keep_route_model_and_keyword_counts(tmp_path, arm_name, arm_kind):
    from skillopt.continual_eval.core import read_json
    from skillopt.execskill import cells, client, evaluation
    from tests.test_execskill_cells import _Client, _context, _cell, _reply
    from tests.fixtures.execskill.items import searchqa_items
    proc = procedure()
    package = empty(step='fixture', evidence=proc.evidence) if arm_name == 'C' else replay.solo(proc)
    response = {**_reply('<answer>Fixtown 0</answer>'), 'returned_model': client.NORTHGATE_MODEL, 'route': 'B'}
    fake = _Client(response)
    fake.route, fake.request_model = 'B', client.NORTHGATE_MODEL
    context = _context(tmp_path, fake, worker=lambda bench: worker(proc))
    context.configuration = 'zebra-pc-v7'
    item = searchqa_items(1)[0]
    cell = _cell(item, arm=arm_name, unit='D/s1-zebralogic/run')
    sham = {'procedures': {proc.id: {'before_call': {'facts': [FACT]}}}, 'seed': 'fixture'} if arm_name == 'P_y' else None
    result = cells.run_cell(context, cell, item, cells.Arm(arm_kind, package, placebo=sham),
                            store=cells.TrainingStore(context.attempt))
    assert result['solver_route'] == {'route': 'B', 'model': client.NORTHGATE_MODEL}
    assert result['returned_model'] == client.NORTHGATE_MODEL
    assert result['returned_models'] == [client.NORTHGATE_MODEL]
    assert bool(result['keyword_hits']['count']) is (arm_name != 'C')
    assert result['applies'] == ({} if arm_name == 'C' else {proc.id: 'default_true'})
    trajectory = read_json(context.attempt / 'trajectories' / (cell['id'] + '.json'))
    assert trajectory['returned_model'] == client.NORTHGATE_MODEL
    assert trajectory['keyword_hits'] == result['keyword_hits']
    assert trajectory['calls'][0]['receipt']['route'] == 'B'
    sealed = evaluation.sealed_cell(result)
    for key in ('returned_model', 'returned_models', 'keyword_hits', 'applies', 'configuration'):
        assert sealed[key] == result[key]


def test_structural_zero_reuse_preserves_v29_metadata(tmp_path):
    from skillopt.execskill import cells, client
    from tests.test_execskill_cells import _Client, _context, _cell, _reply
    from tests.fixtures.execskill.items import searchqa_items
    item = searchqa_items(1)[0]
    package = empty(step='fixture', evidence='engineering_fixture')
    response = {**_reply('<answer>Fixtown 0</answer>'), 'returned_model': client.NORTHGATE_MODEL, 'route': 'B'}
    fake = _Client(response)
    fake.route, fake.request_model = 'B', client.NORTHGATE_MODEL
    context = _context(tmp_path, fake)
    context.configuration = 'zebra-pc-v7'
    card = _cell(item, arm='C')
    store = cells.TrainingStore(context.attempt)
    source = cells.run_cell(context, card, item, cells.Arm('card', package), store=store)
    route = router.route(package, 'searchqa', solver.routing_view('searchqa', item['public']), None).to_json()
    shared = cells.share_cell(context, _cell(item, arm="S'"), item, cells.Arm('candidate', package),
                              source, route, store=store)
    assert shared['shared_with'] == card['id'] and shared['sends'] == []
    assert shared['keyword_hits'] == source['keyword_hits'] == {'count': 0, 'sentences': []}
    assert shared['returned_model'] == client.NORTHGATE_MODEL and shared['solver_route'] == source['solver_route']


@pytest.mark.parametrize('cap', (1500, 1))
def test_alf_delivered_attribution_includes_discouragement_and_caps(cap):
    source = 'def alf_before_step(view, state):\n    return {"fields": {"facts": ["An apple is visible."]}, "discourage": ["look"]}\n'
    proc = procedure(source, origin='alfworld', hooks=('alf_before_step',), max_note_chars=cap)
    package = replay.solo(proc)
    fake = FakeSandbox({proc.id: {'alf_before_step': lambda *args: {
        'fields': {'facts': ['An apple is visible.']}, 'discourage': ['look']}}})
    shell = solver._Shell('alfworld', package, lambda *args: None, fake, withhold=(), restore=(),
                          placebo=None, text=None, native=None, nominal=None)
    shell.start('cell')
    view = {'initial_observation': 'An apple is visible.', 'observation': 'An apple is visible.',
            'task_text': 'Inspect the room', 'recent_history': [], 'admissible_commands': ['look']}
    shell.route_on(view)
    text, _ = shell.before_step(view, {}, 0)
    row = shell.notes[0]
    assert row['step'] == 0 and row['source_sha256'] == hashlib.sha256(source.encode()).hexdigest()
    assert row['procedure_sha256'] == proc.sha256 and row['delivered_text'] == text
    if cap == 1500:
        assert 'An apple is visible.' in text and solver.NOT_RECOMMENDED_PREFIX + 'look' in text
    else:
        assert text == ''
