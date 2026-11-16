"""Core modules of typed-v2: typing, gates, library (fakes only; no network, no /data)."""
import json
import math
import random
import shutil
import tempfile
from pathlib import Path

import pytest

from skillopt.execskill.typed import gates, gatestats as gates_stats, library, tasktypes as typing_


@pytest.fixture
def tmp_path():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses
    (the frozen library and type map files go through it like every other typed writer)."""
    root = Path('/tmp/typed2-neutral')
    root.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='core-', dir=root))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


# ---- typing --------------------------------------------------------------------------------------------------
def fake_embedder(texts):
    """Deterministic 8-d vectors: direction by a text 'family' keyword, small per-text jitter."""
    rows = []
    for text in texts:
        base = [0.0] * 8
        if 'puzzle' in text:
            base[0] = 1.0
        elif 'workbook' in text:
            base[1] = 1.0
        elif 'kitchen' in text:
            base[2] = 1.0
        elif 'treasury' in text:
            base[3] = 1.0
        else:
            base[4] = 1.0
        rng = random.Random(text)
        rows.append([x + rng.uniform(-.05, .05) for x in base])
    return rows


def test_signature_and_public_text_by_structure():
    assert typing_.structural_signature({'question': 'q', 'context': 'c'}) == 'question/context'
    assert typing_.structural_signature({'question': 'q', 'columns': [], 'rows': []}) == 'puzzle_template'
    assert typing_.structural_signature({'instruction': 'i', 'workbook_preview': [{'sheet': 'S', 'preview': [[1, 2]]}]}) == 'workbook_preview'
    assert typing_.structural_signature({'initial_observation': 'o', 'admissible_commands_at_reset': ['look'], 'task_text': 'put a mug'}) == 'admissible_commands'
    with pytest.raises(ValueError):
        typing_.structural_signature({'foo': 1})
    assert typing_.public_text({'question': 'q', 'context': 'x' * 2000}) == 'q\n' + 'x' * 1500
    text = typing_.public_text({'instruction': 'sum', 'workbook_preview': [{'sheet': 'S', 'preview': [[1, 2], [3, 4]]}]})
    assert text.startswith('sum\n') and '[3, 4]' not in text
    obs = 'You are in a kitchen.\n\nYour task is to: put a mug in sink.'
    assert typing_.alfworld_goal(obs) == 'put a mug in sink.'
    assert typing_.public_text({'initial_observation': obs, 'admissible_commands_at_reset': []}) == 'put a mug in sink.\n' + obs


def test_typemap_fit_assign_merge_freeze(tmp_path):
    tm = typing_.TypeMap()
    qa_vectors = fake_embedder(['who wrote %d' % i for i in range(40)])
    oqa_vectors = fake_embedder(['treasury table %d' % i for i in range(30)])
    sid_qa = tm.add_source({'path': '/x/searchqa.json', 'sha256': 'a' * 64}, 'question/context', qa_vectors, step=1)
    assert sid_qa.startswith('src-')
    with pytest.raises(ValueError):
        tm.add_source({'path': '/x/searchqa.json', 'sha256': 'a' * 64}, 'question/context', qa_vectors, step=1)
    assert tm.assign('question/context', qa_vectors[0])['unknown_reason'] == 'unseen_signature'  # no type yet
    t1 = tm.new_type(sid_qa, step=1)
    near = tm.assign('question/context', fake_embedder(['who wrote x'])[0])
    assert near['type'] == t1 and near['unknown_reason'] is None and near['distance'] <= near['threshold']
    far = tm.assign('question/context', fake_embedder(['treasury table z'])[0])
    assert far['type'] is None and far['unknown_reason'] == 'distance_above_p95'
    assert tm.assign('puzzle_template', qa_vectors[0])['unknown_reason'] == 'unseen_signature'
    sid_oqa = tm.add_source({'path': '/x/officeqa.json', 'sha256': 'b' * 64}, 'question/context', oqa_vectors, step=2)
    tm.merge_source(sid_oqa, t1, step=2, evidence={'mean_points': 1.0})
    assert tm.assign('question/context', fake_embedder(['treasury table z'])[0])['type'] == t1
    with pytest.raises(ValueError):
        tm.merge_source(sid_oqa, t1, step=2, evidence={})
    tm.set_card(t1, 'card-t01-s1', step=1)
    tm.add_program(t1, 'prog-t01-s1-a', step=1)
    with pytest.raises(ValueError):
        tm.add_program(t1, 'prog-t01-s1-a', step=1)
    digest = tm.freeze(tmp_path / 'typemap-s2.json', step=2)
    loaded = typing_.TypeMap.load(tmp_path / 'typemap-s2.json')
    assert loaded.summary() == tm.summary() == {t1: {'signature': 'question/context', 'sources': [sid_qa, sid_oqa],
                                                     'card': 'card-t01-s1', 'programs': ['prog-t01-s1-a']}}
    raw = json.loads((tmp_path / 'typemap-s2.json').read_text())
    assert raw['record_sha256'] == digest and raw['step'] == 2
    raw['types'][t1]['card'] = 'tampered'
    (tmp_path / 'bad.json').write_text(json.dumps(raw))
    with pytest.raises(ValueError):
        typing_.TypeMap.load(tmp_path / 'bad.json')
    with pytest.raises(ValueError, match='sealed'):  # the sealed-path guard applies to frozen type maps too
        tm.freeze(tmp_path / 'test-read-S1-searchqa' / 'typemap.json', step=2)
    view = {'question': 'who wrote y', 'context': 'c'}
    assigned = tm.assign_view(view, embedder=fake_embedder)
    assert assigned['signature'] == 'question/context' and assigned['type'] == t1


def test_embed_texts_checks_alignment_and_normalizes():
    vectors = typing_.embed_texts(['a', 'b'], embedder=lambda texts: [[3.0, 4.0], [0.0, 2.0]])
    assert vectors == [[0.6, 0.8], [0.0, 1.0]]
    with pytest.raises(RuntimeError):
        typing_.embed_texts(['a', 'b'], embedder=lambda texts: [[1.0, 0.0]])
    with pytest.raises(ValueError):
        typing_.embed_texts(['a'], embedder=lambda texts: [[0.0, 0.0]])
    assert typing_.embed_texts([], embedder=lambda texts: []) == []


# ---- gates ---------------------------------------------------------------------------------------------------
@pytest.mark.parametrize('df,expected', [(1, 12.706205), (2, 4.302653), (5, 2.570582), (10, 2.228139),
                                         (19, 2.093024), (30, 2.042272), (100, 1.983972), (1000, 1.962339)])
def test_student_t_quantile_matches_tables(df, expected):
    assert abs(gates.student_t_quantile975(df) - expected) < 1e-5


def test_paired_statistics_and_noise_threshold():
    stats = gates.paired_statistics([1, 0, 0, -1, 1, 0, 0, 0, 1, 0])
    assert stats['n'] == 10 and stats['better'] == 3 and stats['worse'] == 1 and stats['tied'] == 6
    assert abs(stats['mean'] - 0.2) < 1e-12 and stats['t_interval95'][0] < 0.2 < stats['t_interval95'][1]
    assert gates.paired_statistics([])['mean'] is None
    quiet = [('i%d' % i, True, True) for i in range(100)]
    noise = gates.noise_threshold(quiet)
    assert noise['tau_points'] == 3.0 and noise['flip_rate'] == 0 and noise['n'] == 100
    noisy = [('i%d' % i, i % 2 == 0, i % 4 == 0) for i in range(100)] + [('u', None, True)]
    noise = gates.noise_threshold(noisy)
    assert noise['excluded_unknown'] == 1 and noise['tau_points'] > 3.0
    assert abs(noise['tau_points'] - 2 * noise['se_points']) < 1e-9


def decide(kind, pairs, *, repeats=3, fired=None):
    """typed-v2 step 5w (DESIGN 3.4): the typed-v1 pair cases of this file as R identical runs per item and arm
    (S = R * x), through ``gates.arm_runs`` / ``repeat_statistics`` and the decision functions ``gates`` re-exports."""
    items = [item for item, _, _ in pairs]
    cells = {}
    for item, current, candidate in pairs:
        for arm, value in (('F', current), ('cand', candidate)):
            for label in gates.repeat_labels(arm, repeats):
                cells[(item, label)] = {'correct': value}
    kw = {'items': items, 'repeats': repeats, 'minimum_points': 3.0, 'multiplier': 2.0}
    baseline, candidate = gates.arm_runs(cells, items, 'F', repeats), gates.arm_runs(cells, items, 'cand', repeats)
    stats = gates.repeat_statistics(baseline, candidate, **kw)
    if kind == 'card':
        return gates.card_decision(stats)
    if kind == 'no_harm':
        return gates.no_harm_decision(stats)
    counts = {item: repeats if item in fired else 0 for item in items}
    subset = [item for item in items if counts[item]]
    return gates.program_decision(stats, gates.repeat_statistics(baseline, candidate, subset=subset, **kw), counts)


def test_card_program_and_no_harm_decisions():
    """typed-v2 step 5w: the typed-v1 decision functions are gone from ``gates`` (module placement); the same cases
    through the repeat decisions of DESIGN 3.4 (R identical runs per item: no variance, tau = the 3-point floor)."""
    assert not hasattr(gates, '_summary') and gates.card_decision is gates_stats.card_decision
    pairs = [('i%d' % i, i % 5 == 0, i % 5 in (0, 1)) for i in range(100)]  # current 20%, candidate 40%
    card = decide('card', pairs)
    assert card['accepted'] and card['gain_points'] == card['mean_points'] == 20.0 and card['better'] == 20
    assert card['worse'] == 0 and card['tau_points'] == 3.0 and card['repeats'] == 3
    assert card['baseline_runs_correct'] == 3 * 20 and card['candidate_runs_correct'] == 3 * 40
    assert gates.recompute(card) == card
    mixed = [('a', False, True), ('b', True, False), ('c', True, False), ('d', False, True), ('e', False, True)]
    assert decide('card', mixed)['reason'] == 'accepted'  # +20 points over 5 items, 3 better and 2 worse
    assert decide('card', [(i, b, not c) for i, b, c in mixed])['reason'] == 'gain_below_tau'
    tie = [('a', False, True), ('b', True, False)] + [('t%d' % i, True, True) for i in range(5)] + [('c', False, True)]
    assert decide('card', tie[:-1] + [('c', True, True)])['reason'] == 'gain_below_tau'  # D = 0
    unknown = decide('card', [('u', None, True), ('v', True, True)])  # a model-side unknown run scores 0 (O1)
    assert unknown['excluded_unknown'] == 0 and unknown['unknown_final'] == {'baseline': 3, 'candidate': 0}
    assert unknown['n'] == 2 and unknown['accepted']
    fired = {'i%d' % i for i in range(0, 100, 5)} | {'i1', 'i6'}
    prog = decide('program', pairs, fired=fired)
    assert prog['accepted'] and prog['fired_items'] == 22 and prog['n'] == 100 and gates.recompute(prog) == prog
    assert decide('program', pairs, fired=set())['reason'] == 'never_fired'
    harm = [('i%d' % i, True, i % 2 == 0) for i in range(40)]
    assert decide('program', harm, fired={'i0', 'i2'})['reason'] == 'gain_below_tau'
    regress = [('f', False, True)] * 1 + [('i%d' % i, True, False) for i in range(20)]
    assert decide('program', regress, fired={'f'})['reason'] == 'harm'
    assert decide('no_harm', [('i%d' % i, True, True) for i in range(30)])['merge']
    found = decide('no_harm', harm)
    assert found == {**found, 'merge': False, 'reason': 'harm_beyond_tau'} and gates.recompute(found) == found


# ---- library -------------------------------------------------------------------------------------------------
def card_skill(step=1, home='t01', name='evidence-answer-card'):
    return library.make_skill(skill_id='card-%s-s%d' % (home, step), name=name, kind='card', home_type=home,
                              body={'text': '- read all snippets'}, origin={'chain': 'G', 'step': step, 'bench': 'searchqa'})


def test_library_versions_index_and_descriptions(tmp_path):
    lib = library.Library()
    with pytest.raises(ValueError):
        library.make_skill(skill_id='x', name='Bad Name', kind='card', home_type='t01', body={'text': 'a'}, origin={})
    sid = lib.add(card_skill())
    assert lib.next_id('card', 't01', 1) == 'card-t01-s1-a' and lib.next_id('program', 't01', 1) == 'prog-t01-s1-a'
    with pytest.raises(ValueError):
        lib.add(card_skill(name='second-card'))  # active card exists
    with pytest.raises(ValueError):
        lib.index(home_type='t01')  # no description yet
    lib.get(sid)['description'] = 'For evidence QA.'
    prog = library.make_skill(skill_id='prog-t01-s1-a', name='snippet-scanner', kind='program', home_type='t01',
                              body={'procedure': {'id': 'p-x', 'source': 'def applies(view):\n    return True\n'}},
                              origin={'chain': 'G', 'step': 1, 'bench': 'searchqa'}, description='Scans snippets.')
    lib.add(prog)
    assert [r['name'] for r in lib.index()] == ['evidence-answer-card', 'snippet-scanner']
    assert lib.index(home_type='t01', kinds=('program',)) == [{'name': 'snippet-scanner', 'description': 'Scans snippets.'}]
    assert lib.index(home_type='t02') == []
    lib.retire_card('t01', step=2)
    assert lib.active_card('t01') is None and lib.get(sid)['retired_at_step'] == 2
    lib.add(card_skill(step=2, name='evidence-answer-card-v2'))
    assert lib.active_card('t01')['skill_id'] == 'card-t01-s2' and len(lib.programs('t01')) == 1
    digest = lib.save(tmp_path / 'library-s2.json', step=2)
    loaded = library.Library.load(tmp_path / 'library-s2.json')
    assert loaded.summary() == lib.summary() and loaded.data['record_sha256'] == digest if 'record_sha256' in loaded.data else True
    with pytest.raises(ValueError, match='sealed'):  # the sealed-path guard applies to library versions too
        lib.save(tmp_path / 'test-read-S1-searchqa' / 'library.json', step=2)
    assert library.body_text(prog).startswith('def applies')
    req = library.description_request(prog, ['q1', 'q2', 'q3'])
    assert '"skill_content"' in req['user'] and req['system'] == library.DESCRIPTION_SYSTEM
    with pytest.raises(ValueError):
        library.description_request(prog, ['q1'])
    assert library.parse_description('{"description": "Use for X."}') == 'Use for X.'
    assert library.parse_description('```json\n{"description": "Use for X."}\n```') == 'Use for X.'
    with pytest.raises(ValueError):
        library.parse_description(json.dumps({'description': 'x' * 451}))
    with pytest.raises(ValueError):
        library.parse_description('{"description": "a", "extra": 1}')


def test_selection_prompt_and_parse():
    index = [{'name': 'grid-solver', 'description': 'Solves grids.'}, {'name': 'helper', 'description': 'Helps.'}]
    req = library.selection_request(index, 'puzzle text')
    assert req['system'] == library.SELECTION_SYSTEM and json.loads(req['user'])['skills'] == index
    retry = library.selection_format_retry(req)
    assert retry['user'].endswith(library.SELECTION_RETRY) and retry['request_sha256'] != req['request_sha256']
    assert library.parse_selection('{"use": ["grid-solver"], "why": "grid"}', {'grid-solver', 'helper'}) == {'use': ['grid-solver'], 'why': 'grid'}
    assert library.parse_selection('{"use": [], "why": "none"}', {'grid-solver'})['use'] == []
    for bad in ('{"use": ["other"], "why": "x"}', '{"use": ["grid-solver", "grid-solver"], "why": "x"}', '{"use": [], "why": "x", "z": 1}', 'not json'):
        with pytest.raises(ValueError):
            library.parse_selection(bad, {'grid-solver', 'helper'})
    with pytest.raises(ValueError):
        library.selection_request([], 'text')
