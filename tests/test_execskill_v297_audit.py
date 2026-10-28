"""Whole-episode audit evidence on the supplied real trajectory; no services."""
from copy import deepcopy
import json
from pathlib import Path
import re
from types import SimpleNamespace

import pytest

from skillopt.execskill import audit, profiles as p, replay
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

FIXTURE = Path(__file__).parent / 'fixtures/execskill/v297_alf10_loop_guard_trajectory.json'
REAL = json.loads(FIXTURE.read_text())
PARENTS = json.loads((FIXTURE.parent / 'v297_parents_before.json').read_text())
PID = 'p-alfworld-1-13'
SOURCE = ('def alf_before_step(view, state):\n    return {"facts": ["Previously executed actions are counted."]}\n'
          'def alf_after_step(event, state):\n    return state\n')


def fixture_inputs(*, step_zero=False):
    """Adapt the read-only excerpt into ordinary stored request/replay containers.

    Real actions, post observations, the three disclosed views and note claims
    are unmodified. Missing source/request metadata is authored, never inferred
    from an outcome. No source is executed and no judge is called here.
    """
    proc = SimpleNamespace(id=PID, description='loop/action-repeat guard with untried go-to commands first', source=SOURCE)
    selected = {row['step']: row for row in REAL['final_audit_situations']}
    calls, logged, output_notes = [], [], []
    base = next(iter(selected.values()))['view']
    rows = REAL['alfworld_steps']
    for i, row in enumerate(rows):
        view = deepcopy(selected[i]['view']) if i in selected else {
            'initial_observation': base['initial_observation'], 'task_text': base['task_text'],
            'observation': row['observation'], 'recent_history': [
                {'observation': old['observation'], 'action': old['action']} for old in rows[max(0, i - 5):i]],
            'admissible_commands': []}
        texts = [n['text'] for n in selected[i]['notes'] if n['procedure'] == PID] if i in selected else []
        if i == 0 and step_zero:
            texts = ['No earlier action was executed.']
        text = '\n'.join(texts)
        calls.append({'purpose': 'step', 'user': json.dumps({**view, p.NOTES_KEY: text})})
        if text:
            logged.append({'id': PID, 'hook': 'alf_before_step', 'step': i,
                           'delivered_text': text, 'source_sha256': audit.text_sha256(SOURCE)})
            output_notes.append({'step': i, 'text': text})
    cell = {**deepcopy(REAL), 'bench': 'alfworld', 'unit': 'D/s1-alfworld/confirm-r5',
            'calls': calls, 'shell': {'notes': logged}}
    entry = replay.inputs_of(cell)
    outcome = SimpleNamespace(notes=output_notes, faults=[], applies=True)
    return proc, cell, entry, {cell['cell']: outcome}


def situations(path, configuration=p.ALFWORLD_V11, *, step_zero=False):
    proc, cell, entry, outcomes = fixture_inputs(step_zero=step_zero)
    if path == 'replay':
        return audit.situations_from_replays(proc, [entry], outcomes, configuration=configuration,
                                            trajectories={cell['cell']: cell})
    return audit.situations_from_cells([cell], SimpleNamespace(procedures=[proc]), configuration=configuration)


@pytest.mark.parametrize('path', ['replay', 'requests'])
@pytest.mark.parametrize('step', [44, 45, 47])
def test_real_whole_episode_counts_three_while_recent_window_shows_only_drawer_one(path, step):
    current = next(row for row in situations(path) if row['step'] == step)
    history = current['view']['episode_history']
    assert [row['step'] for row in history] == list(range(step))
    for target in ('go to drawer 1', 'go to drawer 7', 'go to drawer 8'):
        assert sum(row['action'] == target for row in history) == 3
        assert sum(row['action'] == target for row in current['view']['recent_history']) == (1 if target == 'go to drawer 1' else 0)
    for i, row in enumerate(history):
        original = REAL['alfworld_steps'][i]
        assert row == {'step': i, 'action': original['action'],
                       'observation': audit._observation(original['post_observation'])}
        assert set(row) == {'step', 'action', 'observation'}
    parent = next(row for row in situations(path, p.ALFWORLD_V10) if row['step'] == step)
    assert {k: v for k, v in current['view'].items() if k != 'episode_history'} == parent['view']
    assert audit.situation_key(current) != audit.situation_key(parent)


@pytest.mark.parametrize('path', ['replay', 'requests'])
def test_step_zero_has_explicit_empty_history(path):
    first = next(row for row in situations(path, step_zero=True) if row['step'] == 0)
    assert first['view']['episode_history'] == []


def test_both_paths_disclose_exactly_the_same_history_and_claims():
    direct = {row['step']: row for row in situations('requests')}
    for row in situations('replay'):
        assert row['view'] == direct[row['step']]['view']
        assert row['notes'] == direct[row['step']]['notes']
        assert audit.situation_key(row) == audit.situation_key(direct[row['step']])


@pytest.mark.parametrize('configuration', sorted(PARENTS['configurations']))
def test_every_parent_public_view_and_key_matches_before_snapshot(configuration):
    old = PARENTS['configurations'][configuration]
    for index, view in PARENTS['audit_public_inputs'].items():
        found = audit.public_view('alfworld', view, configuration=configuration)
        assert found == old['audit_views'][index]
        assert audit.situation_key({'item': PARENTS['audit_item'], 'step': int(index), 'view': found}) == old['audit_keys'][index]
    for path in ('replay', 'requests'):
        assert situations(path, configuration) == situations(path, None)
        assert all('episode_history' not in row['view'] for row in situations(path, configuration))


@pytest.mark.parametrize('path', ['replay', 'requests'])
def test_observations_use_returned_text_truncate_with_mark_and_keep_every_step(path):
    proc, cell, entry, outcomes = fixture_inputs()
    long = '返回\n"' * 200
    cell['alfworld_steps'][0]['post_observation'] = long
    following = json.loads(cell['calls'][1]['user'])
    following['observation'] = long
    cell['calls'][1]['user'] = json.dumps(following)
    if path == 'replay':
        entry = replay.inputs_of(cell)
        entry['steps'][0]['view']['observation'] = 'Before the action, not returned.'
        found = audit.situations_from_replays(proc, [entry], outcomes, configuration=p.ALFWORLD_V11,
                                            trajectories={cell['cell']: cell})
    else:
        found = audit.situations_from_cells([cell], SimpleNamespace(procedures=[proc]), configuration=p.ALFWORLD_V11)
    history = found[0]['view']['episode_history']
    assert len(history) == found[0]['step']
    assert history[0]['observation'] == long[:240 - len(audit.EPISODE_TRUNCATION_MARK)] + audit.EPISODE_TRUNCATION_MARK
    assert len(history[0]['observation']) == 240
    assert history[0]['action'] == 'go to drawer 1'


@pytest.mark.parametrize('tamper', ['missing_event', 'wrong_step', 'wrong_action'])
def test_incomplete_or_misaligned_replay_history_is_refused(tamper):
    proc, cell, entry, outcomes = fixture_inputs()
    if tamper == 'missing_event':
        entry['steps'][0]['event'] = None
    elif tamper == 'wrong_step':
        entry['steps'][0]['event']['step'] = 1
    else:
        entry['steps'][0]['event']['action'] = 'invented'
    with pytest.raises(ValueError, match='earlier alf_after_step event'):
        audit.situations_from_replays(proc, [entry], outcomes, configuration=p.ALFWORLD_V11,
                                     trajectories={cell['cell']: cell})


@pytest.mark.parametrize('tamper', ['missing_action', 'duplicate_step', 'wrong_post_observation'])
def test_incomplete_request_history_or_wrong_transition_is_refused(tamper):
    proc, cell, _, _ = fixture_inputs()
    if tamper == 'missing_action':
        cell['alfworld_steps'].pop(0)
    elif tamper == 'duplicate_step':
        cell['alfworld_steps'][0]['i'] = 1
    else:
        cell['alfworld_steps'][0]['post_observation'] = 'Not the following hook observation.'
    with pytest.raises(ValueError, match='earlier logged action|post-action observation'):
        audit.situations_from_cells([cell], SimpleNamespace(procedures=[proc]), configuration=p.ALFWORLD_V11)


@pytest.mark.parametrize('part,final', [('A', False), ('B', False), ('B', True)])
def test_new_prompt_is_exact_parent_plus_one_pinned_passage(part, final):
    before = audit.system_prompt(part, configuration=p.ALFWORLD_V10, final=final)
    after = audit.system_prompt(part, configuration=p.ALFWORLD_V11, final=final)
    assert after == before + '\n' + audit.EPISODE_HISTORY_RULE
    assert after.count(audit.EPISODE_HISTORY_RULE) == 1
    pins = audit.prompt_pins(p.ALFWORLD_V11)
    key = 'templates_system' if part == 'A' else 'final_system' if final else 'situations_system'
    assert pins[key] == {'text': after, 'sha256': audit.text_sha256(after)}
    assert pins['episode_history']['text'] == audit.EPISODE_HISTORY_RULE
    old = audit.prompt_pins(p.ALFWORLD_V10)
    assert {k: v for k, v in pins.items() if k not in ('templates_system', 'situations_system', 'final_system', 'episode_history')} == {
        k: v for k, v in old.items() if k not in ('templates_system', 'situations_system', 'final_system')}


class Judge:
    """A deterministic format-correct endpoint; makes no policy-effect claim."""
    def __init__(self, *, invalid=None):
        self.calls, self.seen, self.invalid = [], [], invalid

    def plain(self, role, system, user, *, label, max_tokens):
        self.calls.append({'sends': []})
        self.seen.append((system, user, max_tokens))
        if self.invalid is not None and not label.endswith('/format-retry') and system.startswith(audit.B_SYSTEM):
            return self.invalid
        if system.startswith(audit.A_SYSTEM):
            return json.dumps({'templates': [{'t': t, 'verdict': 'ok', 'reason': '', 'false_when': ''}
                for t in re.findall(r'^(T\d+):', user, re.M)], 'other': []})
        found = []
        for part in re.split(r'^Situation ', user, flags=re.M)[1:]:
            sid = part.split()[0]
            found.append({'s': sid, 'notes': [{'n': n, 'truth': 'unverifiable', 'policy': 'ok',
                'evidence': '', 'reason': ''} for n in re.findall(r'^(N\d+) \[', part, re.M)]})
        result = {'situations': found, 'program': {'verdict': 'ok', 'reason': ''}}
        if audit.CONTRADICTIONS in system:
            result['contradictions'] = []
        return json.dumps(result)


@pytest.mark.parametrize('path', ['replay', 'audit1'])
@pytest.mark.parametrize('tamper', [
    'missing_leading_row', 'missing_interior_row', 'duplicate_index',
    'misnumbered_rows', 'wrong_post_observation', 'captured_action_disagrees',
])
def test_round_history_checks_raw_rows_before_replay_can_hide_corruption(monkeypatch, path, tamper):
    from skillopt.execskill import engineer
    proc, cell, _, outcomes = fixture_inputs()
    if tamper == 'missing_leading_row':
        cell['alfworld_steps'].pop(0)
    elif tamper == 'missing_interior_row':
        cell['alfworld_steps'].pop(7)
    elif tamper == 'duplicate_index':
        cell['alfworld_steps'].append(deepcopy(cell['alfworld_steps'][0]))
    elif tamper == 'misnumbered_rows':
        cell['alfworld_steps'][7]['i'] = 99
    elif tamper == 'wrong_post_observation':
        cell['alfworld_steps'][0]['post_observation'] = 'Contradicts the following request observation.'
    entry = replay.inputs_of(cell)
    if tamper == 'captured_action_disagrees':
        # Keep the captured entry internally consistent: only comparison with
        # the original verified trajectory can reveal the invented action.
        entry['steps'][0]['action'] = 'invented action'
        entry['steps'][0]['event']['action'] = 'invented action'
    trajectories = {cell['cell']: cell}
    parent = audit.situations_from_replays(proc, [entry], outcomes, configuration=p.ALFWORLD_V10,
                                          trajectories=trajectories)
    assert parent == audit.situations_from_replays(proc, [entry], outcomes)
    judges = {'G': Judge(), 'D': Judge()}
    monkeypatch.setattr(engineer, '_verified_run_cells', lambda ctx: trajectories)
    ctx = SimpleNamespace(sheet={'audit_replays': {proc.id: ([entry], outcomes)}}, configuration=p.ALFWORLD_V11,
        audit_judges=judges, bench='alfworld', step='D/s1-alfworld', round=5)
    with pytest.raises(ValueError):
        if path == 'replay':
            audit.situations_from_replays(proc, [entry], outcomes, configuration=p.ALFWORLD_V11,
                                         trajectories=trajectories)
        else:
            audit.audit1(ctx, SimpleNamespace(procedure=proc, n=1), {})
    assert all(not judge.calls for judge in judges.values())
    assert 'audits' not in ctx.sheet


@pytest.mark.parametrize('mapping', ['omitted', 'empty', 'different_cell'])
def test_child_round_history_requires_the_entry_in_the_verified_trajectory_map(mapping):
    proc, cell, entry, outcomes = fixture_inputs()
    kwargs = {} if mapping == 'omitted' else {
        'trajectories': {} if mapping == 'empty' else {'different-cell': cell}}
    with pytest.raises(ValueError):
        audit.situations_from_replays(proc, [entry], outcomes, configuration=p.ALFWORLD_V11, **kwargs)
    assert audit.situations_from_replays(proc, [entry], outcomes, configuration=p.ALFWORLD_V10, **kwargs) == (
        audit.situations_from_replays(proc, [entry], outcomes))


def audited(*, final=False, rows=None, g=None, d=None):
    proc = fixture_inputs()[0]
    return audit.run_audit([proc], rows or situations('requests'), {'G': g or Judge(), 'D': d or Judge()},
        bench='alfworld', configuration=p.ALFWORLD_V11, step='D/s1-alfworld/audit', round=5,
        final=final, change_id='1')


@pytest.mark.parametrize('final', [False, True])
def test_both_judges_receive_history_and_prompt_passage_in_round_and_final_audits(final):
    g, d = Judge(), Judge()
    result = audited(final=final, g=g, d=d)
    assert result['available'] == {'G': True, 'D': True} and not result['audit_incomplete']
    assert not result['confirmed']
    for endpoint in (g, d):
        for system, user, cap in endpoint.seen:
            assert audit.EPISODE_HISTORY_RULE in system and cap == 8192
            if system.startswith(audit.B_SYSTEM):
                assert 'episode_history' in user
    for pair in result['requests']:
        for record in pair['requests'].values():
            bound = record['episode_disclosure']
            assert bound['observation_chars'] == 240 and bound['within_limit']
            assert bound['input_bytes'] == len((record['system'] + record['user']).encode())
            assert bound['input_bytes'] <= p.ROLE_INPUT_BYTES


def prompt_batches(user):
    return [json.loads(block.split('\n--- Notes it produced ---')[0])
            for block in user.split('--- What the helper saw ---\n')[1:]]


def test_oversize_prompt_halves_only_observations_and_preserves_all_steps(monkeypatch):
    batch = deepcopy(situations('requests'))
    for situation in batch:
        situation['view']['episode_history'] = [
            {**event, 'observation': '长' * 240} for event in situation['view']['episode_history']]
    system = audit.system_prompt('B', configuration=p.ALFWORLD_V11)
    proc = fixture_inputs()[0]
    render = lambda rows: audit.situation_prompt([proc], 'alfworld', rows, {})
    # The authored lower input allowance forces the production fitting path.
    monkeypatch.setattr(p, 'ROLE_INPUT_BYTES', 50000)
    original = deepcopy(batch)
    numbered = [dict(row, s='S%d' % (i + 1), notes=[dict(note, n='N%d' % (j + 1))
        for j, note in enumerate(row['notes'])]) for i, row in enumerate(batch)]
    user, measured = audit.fit_episode_prompt(system, render, numbered)
    assert measured['within_limit'] and measured['observation_chars'] < 240
    shown = prompt_batches(user)
    assert sum(len(view['episode_history']) for view in shown) == sum(row['step'] for row in batch)
    for view, source in zip(shown, original):
        assert {k: v for k, v in view.items() if k != 'episode_history'} == {
            k: v for k, v in source['view'].items() if k != 'episode_history'}
        assert [(row['step'], row['action']) for row in view['episode_history']] == [
            (row['step'], row['action']) for row in source['view']['episode_history']]
        assert all(row['observation'].endswith(audit.EPISODE_TRUNCATION_MARK) for row in view['episode_history'])
    assert batch == original


def test_retry_fits_from_structured_history_without_editing_raw_reply(monkeypatch):
    rows = situations('requests')
    for row in rows:
        for event in row['view']['episode_history']:
            event['observation'] = '长' * 240
    raw = 'invalid: {"episode_history": [{"observation": "keep this exact raw text"}]} ' + 'x' * 25000
    monkeypatch.setattr(p, 'ROLE_INPUT_BYTES', 80000)
    result = audited(final=True, rows=rows, g=Judge(invalid=raw), d=Judge())
    request = next(pair['requests']['G'] for pair in result['requests'] if pair['part'] == 'B')
    retry = request['retries'][0]
    assert request['available'] and request['raw_replies'][0] == raw
    assert '\nPrevious reply: ' + raw + '\nParse problem: ' in retry['user']
    assert retry['episode_disclosure']['within_limit']
    assert retry['episode_disclosure']['observation_chars'] < request['episode_disclosure']['observation_chars']
    assert retry['episode_disclosure']['history_steps'] == request['episode_disclosure']['history_steps']
    assert len((retry['system'] + retry['user']).encode()) <= p.ROLE_INPUT_BYTES


def test_retry_that_cannot_fit_is_recorded_without_calling_judge(monkeypatch):
    monkeypatch.setattr(p, 'ROLE_INPUT_BYTES', 30000)
    g = Judge(invalid='x' * 40000)
    result = audited(g=g, d=Judge())
    request = next(pair['requests']['G'] for pair in result['requests'] if pair['part'] == 'B')
    assert not request['available'] and result['audit_incomplete']
    assert len([row for row in g.seen if row[0].startswith(audit.B_SYSTEM)]) == 1
    assert not request['attempts'][-1]['dispatched']
    assert request['unavailable_reason'] == 'audit_input_limit_after_observation_truncation'
    assert request['retries'][0]['episode_disclosure']['observation_chars'] == len(audit.EPISODE_TRUNCATION_MARK)


def test_initial_nonhistory_content_that_cannot_fit_is_refused_before_any_call(monkeypatch):
    monkeypatch.setattr(p, 'ROLE_INPUT_BYTES', 100)
    g, d = Judge(), Judge()
    result = audited(g=g, d=d)
    assert not g.calls and not d.calls
    assert result['audit_incomplete'] and result['available'] == {'G': False, 'D': False}
    assert all(not request['attempts'][0]['dispatched'] for pair in result['requests']
               for request in pair['requests'].values())


def test_audit1_passes_configuration_and_verified_raw_map_into_replay_situation_path(monkeypatch):
    proc, cell, entry, outcomes = fixture_inputs()
    trajectories = {cell['cell']: cell}
    seen = []
    original = audit.situations_from_replays
    def captured(*args, **kwargs):
        seen.append(kwargs['configuration'])
        assert kwargs['trajectories'] is trajectories
        return original(*args, **kwargs)
    monkeypatch.setattr(audit, 'situations_from_replays', captured)
    from skillopt.execskill import engineer
    monkeypatch.setattr(engineer, '_verified_run_cells', lambda ctx: trajectories)
    ctx = SimpleNamespace(sheet={'audit_replays': {proc.id: ([entry], outcomes)}}, configuration=p.ALFWORLD_V11,
        audit_judges={'G': Judge(), 'D': Judge()}, bench='alfworld', step='D/s1-alfworld', round=5)
    found = audit.audit1(ctx, SimpleNamespace(procedure=proc, n=1), {})
    assert seen == [p.ALFWORLD_V11]
    assert all('episode_history' in row['view'] for row in found['sampling']['situations'])
    final = {row['step']: row for row in audit.situations_from_cells(
        [cell], SimpleNamespace(procedures=[proc]), configuration=p.ALFWORLD_V11)}
    for row in found['sampling']['situations']:
        assert row['view'] == final[row['step']]['view']
        assert audit.situation_key(row) == audit.situation_key(final[row['step']])


def test_final_step_passes_configuration_into_request_situation_path(monkeypatch, tmp_path):
    from skillopt.execskill import step
    class ReachedSituations(Exception):
        pass
    seen = []
    def captured(cells, package, *, configuration):
        seen.append(configuration)
        raise ReachedSituations
    monkeypatch.setattr(audit, 'situations_from_cells', captured)
    parent = SimpleNamespace(sha256='parent')
    st = SimpleNamespace(parent=parent, setting=SimpleNamespace(extra={'configuration': p.ALFWORLD_V11}),
                         unit=lambda name, work: work(tmp_path))
    with pytest.raises(ReachedSituations):
        step._audit_final(st, SimpleNamespace(sha256='candidate'), [])
    assert seen == [p.ALFWORLD_V11]
