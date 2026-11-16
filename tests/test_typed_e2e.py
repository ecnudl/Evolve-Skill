"""End-to-end run of typed-v2 on fakes: the REAL ``chain.run``, ``mount.mount``, the real writers (prompts,
screens, engineer reader, policy), ``reads.read_panel`` under consent with a practice panel standing in for the
test panel, and ``readout.build`` in closed and open mode.

Synthetic manifest with two benches (searchqa: question/context, zebralogic: question/columns), 3 learn + 4 gate
items each and a 2-item panel per bench; scripted fake clients (one reply per purpose), a fake ``mount.solve`` with
deterministic outcomes keyed by the mounted arm (the card gate accepts on searchqa and rejects on zebralogic, the
program gate accepts exactly once), a fake embedder. No network, no Docker, no /data, nothing paid. The program
writer proposes one canonical program on searchqa; on zebralogic it takes the promotion path of DESIGN 3.2 / 3.3
(an unreadable reply, the format retry, a proposal refused by the screen and by its fix, the next one in slot 1).
"""
import builtins
import functools
import io
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from skillopt.coevo5 import data
from skillopt.execskill.typed import (READ_ARMS, chain, gates, library as library_, readout, reads, smoke,
                                      tasktypes as typing_, units)
from skillopt.validator_pilot.api import digest

# pytest's tmp_path carries the word "test" (refused by the sealed-path guard) and, on macOS, /tmp is a symlink,
# which route B's safe_path (the panel registry) refuses in any parent: the neutral root through its resolved spelling.
NEUTRAL = Path('/tmp/typed2-neutral').resolve()
BENCHES = ('searchqa', 'zebralogic')
SIZES = {bench: {'learn': 3, 'gate': 4} for bench in BENCHES}
PANEL_SIZE = 2
CANARY = 'REPLY-CANARY'
DESCRIPTION = 'Scripted skill for tasks of this public structure; not for other structures.'
PROGRAM_ID = 'p-searchqa-1-1'


@pytest.fixture
def tmp_path():
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='e2e-', dir=NEUTRAL))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


# ---- the synthetic world -------------------------------------------------------------------------------------
def number_of(item_id):
    """'searchqa-g3' -> 3, 'zebralogic-p1' -> 1 (the slice letter is dropped)."""
    return int(item_id.rsplit('-', 1)[-1][1:])


def outcome(bench, item_id, mounted):
    """Deterministic judge tokens keyed by the mounted arm. searchqa: nothing -> item 0 only; a library or candidate
    card -> items 0..2; an enabled program -> every item. zebralogic: even items only, whatever is mounted (so its
    card and program candidates gain nothing and the gates reject them)."""
    n = number_of(item_id)
    card = mounted.get('arm') == 'cand_card' or mounted.get('card_skill') is not None
    program = bool(mounted.get('enabled'))
    if bench == 'searchqa':
        if program:
            return 'pass'
        if card:
            return 'pass' if n <= 2 else 'fail'
        return 'pass' if n == 0 else 'fail'
    return 'pass' if n % 2 == 0 else 'fail'


def family_embedder(texts):
    """Exactly unit-norm vectors, one per structure (a puzzle text names houses): every item of a bench sits on its
    centroid, so the p95 threshold is 0 and every panel item of the structure is typed deterministically."""
    return [[0.0, 1.0] if 'houses' in text else [1.0, 0.0] for text in texts]


def panel_items(bench):
    rows = []
    for i in range(PANEL_SIZE):
        task_id = '%s-p%d' % (bench, i)
        public, private = smoke.SYNTHETIC_ITEMS[bench](task_id)
        rows.append({'benchmark': bench, 'task_id': task_id, 'public': public, 'private': private})
    return rows


def panel_reader(by_bench, seen):
    """The practice panel standing in for ``coevo5.data.test_panel`` behind the one ``data.TestAccess``."""
    def panel(pinned, benchmark, *, access):
        assert isinstance(access, data.TestAccess) and 'test-read' in access.unit
        seen.append((benchmark, access.unit))
        tasks = [json.loads(json.dumps(item)) for item in by_bench[benchmark]]
        return tasks, {'benchmark': benchmark, 'tasks': len(tasks), 'excluded_without_pages': [],
                       'panel_hash': digest(tasks), 'source_files': None}
    return panel


def solver_reply(ids):
    """The solver's scripted reply names the item it answered (a canary the sealed units must keep inside)."""
    def reply(system, user):
        found = next((i for i in ids if i in user), 'none')
        return 'The answer is 42. ' + CANARY + '-' + found
    return reply


def card_reply(system, user):
    """Round 1 writes the default card; the revision round (zebralogic) returns a different, still clean card."""
    if '"request": "revise"' in user:
        return smoke.DEFAULT_CARD.replace('Give exactly one final answer', 'State one final answer')
    return smoke.DEFAULT_CARD


def program_reply(system, user):
    """searchqa: the canonical one-program reply. zebralogic (typed-v2, step 4c): prose, then on the format retry a
    proposal the screen refuses ([import]) and a clean one; the one fix of the refused proposal is refused again."""
    request = json.loads(user)
    if request['bench'] == 'searchqa':
        return smoke.DEFAULT_PROGRAM
    if request['request'] == 'propose':
        return smoke.UNREADABLE_PROPOSAL
    if request['request'] == 'format_retry':
        return smoke.program_reply([(smoke.REFUSED_ENTRY, smoke.REFUSED_SOURCE), (smoke.HELPER_ENTRY, smoke.HELPER_SOURCE)])
    return smoke.FIX_REFUSED


def consent(root):
    units.write_json(root / 'shared' / 'consent.json', {
        'test_evaluation': True, 'sheet_test_qualification': True, 'multi_arm_arms': list(READ_ARMS), 'by': 'owner',
        'date': '2026-11-10', 'note': 'typed-v2 end-to-end fixture: practice items stand in for the panels'})


def build(root):
    """Fake services through the REAL mount / writers / reads, in mode 'test' (evidence engineering_fixture) so the
    reads open their panels under consent into sealed test-read units."""
    manifest = {**smoke.synthetic_manifest(sizes=SIZES),
                'pinned': {'paths': {}, 'sha256': {}, 'zebralogic': {'path': '/fake/sealed-zebra.json', 'sha256': 'f' * 64}}}
    panels = {bench: panel_items(bench) for bench in BENCHES}
    ids = sorted([i for bench in BENCHES for part in ('learn', 'gate') for i in manifest['slices'][bench][part]]
                 + [item['task_id'] for rows in panels.values() for item in rows], key=len, reverse=True)
    script = smoke.Script({'replies': {'solver': solver_reply(ids), 'card_writer': card_reply,
                                       'program_writer': program_reply,
                                       'describer': json.dumps({'description': DESCRIPTION})},
                           'outcomes': outcome})
    services = smoke.fake_services(root, 'G', manifest, scripted=script)
    services.mode, services.order, services.embed = 'test', BENCHES, family_embedder
    seen = []
    services.read_panel = functools.partial(reads.read_panel, panel=panel_reader(panels, seen))
    consent(root)
    return services, script, panels, seen


def files_with(root, marker):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob('*')
                  if p.is_file() and marker in p.read_text(encoding='utf-8', errors='replace'))


def cells_of(unit_dir):
    return [json.loads(p.read_text()) for p in sorted((unit_dir / 'cells').glob('*.json'))]


def sealed_guard(monkeypatch):
    """Any open of a path that carries 'test-read' fails the test: closed mode must never touch a sealed unit."""
    real_open, real_read_text = io.open, Path.read_text

    def guarded_open(file, *args, **kwargs):
        if 'test-read' in str(file):
            raise AssertionError('sealed path opened in closed mode: ' + str(file))
        return real_open(file, *args, **kwargs)

    def guarded_read_text(self, *args, **kwargs):
        if 'test-read' in str(self):
            raise AssertionError('sealed path opened in closed mode: ' + str(self))
        return real_read_text(self, *args, **kwargs)
    monkeypatch.setattr(io, 'open', guarded_open)
    monkeypatch.setattr(builtins, 'open', guarded_open)
    monkeypatch.setattr(Path, 'read_text', guarded_read_text)


# ---- the run ------------------------------------------------------------------------------------------------------
def test_end_to_end_two_bench_chain_with_interruption_resume_and_readouts(tmp_path, monkeypatch):
    root = tmp_path / 'run'
    services, script, panels, seen = build(root)
    real_solve = services.solve_fn
    broken = {'unit': 'test-read-S1-zebralogic'}

    def solve(bench, item, mounted, **kwargs):  # the injected interruption: the first cell of one read unit raises
        if kwargs['unit'] == broken['unit']:
            raise RuntimeError('injected interruption')
        return real_solve(bench, item, mounted, **kwargs)
    services.solve_fn = solve
    state = chain.run(root, 'G', services=services, sleep=lambda s: None)
    chain_dir = root / 'G'
    assert state['paused']['reason'] == 'first_cell_configuration:zebralogic' and state['paused']['awaiting_owner']
    assert state['paused']['unit'] == 'read-S1-zebralogic' and 's1/program-1-gate' in state['done_units']
    assert 'step-1' not in state['done_units'] and 'read-S1-searchqa' not in state['done_units']  # marked after the reads
    assert json.loads((chain_dir / 'test-read-S1-zebralogic' / 'done.json').read_text())['stop_reason'] == state['paused']['reason']
    # resume requires the owner's recovery record; a done unit is never redone
    with pytest.raises(ValueError):
        chain.run(root, 'G', services=services, resume=True)
    broken['unit'] = None
    units.write_json(chain_dir / 'recovery.json', {'by': 'owner', 'date': '2026-11-10', 'decision': 'injected fault fixed'})
    state = chain.run(root, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'] and state['paused'] is None and len(state['recoveries']) == 1
    assert (chain_dir / 'recovery-consumed-1.json').exists() and not (chain_dir / 'recovery.json').exists()
    assert (chain_dir / 'test-read-S1-zebralogic' / 'done-stopped-1.json').exists()
    assert json.loads((chain_dir / 'test-read-S1-zebralogic' / 'done.json').read_text())['stop_reason'] is None
    # every cell of every unit was solved exactly once across both runs (the resumed run reused finished cells)
    sends = {}
    for purpose, unit in script.calls:
        if purpose == 'solver':  # the first call is its own purpose and has no cell
            sends[unit] = sends.get(unit, 0) + 1
    # 8 reads, 6 cell units in step 1, 7 in step 2 (the rejected round-1 card is run on the learn slice for the revision)
    assert script.counts['first_call'] == 1 and len(sends) == 8 + 6 + 7
    for unit, count in sends.items():
        assert count == len(cells_of(chain_dir / unit)), unit
    # units and their names
    assert state['done_units'] == (
        ['confirm', 'read-C0-searchqa', 'read-C0-zebralogic', 'read-C-searchqa', 'read-C-zebralogic', 'step-0',
         's1/noise', 's1/typing', 's1/outcomes', 's1/card-r1', 's1/outcomes-card', 's1/programs', 's1/program-1-smoke',
         's1/program-1-gate', 'read-S1-searchqa', 'read-S1-zebralogic', 'step-1',
         's2/noise', 's2/typing', 's2/outcomes', 's2/card-r1', 's2/card-r1-learn', 's2/card-r2', 's2/programs',
         's2/program-1-smoke', 's2/program-1-gate', 'read-S2-searchqa', 'read-S2-zebralogic', 'step-2'])
    assert sorted(p.name for p in chain_dir.iterdir() if p.is_dir()) == sorted(
        ['confirm', 's0', 's1', 's2', 'read-status'] + ['test-read-%s-%s' % (e, b) for e in ('C0', 'C', 'S1', 'S2') for b in BENCHES])
    assert sorted(p.name for p in (chain_dir / 'confirm').rglob('*') if p.is_file()) == ['first-call.json']
    assert sorted(p.name for p in (chain_dir / 's1').iterdir() if p.is_dir()) == sorted(
        ['noise', 'typing', 'outcomes', 'card-r1', 'outcomes-card', 'programs', 'program-1', 'program-1-smoke', 'program-1-gate'])
    assert sorted(p.name for p in (chain_dir / 's1' / 'program-1').iterdir()) == ['calls', 'decision.json', 'skill.json']
    assert set(seen) == {(b, 'G/test-read-%s-%s' % (e, b)) for e in ('C0', 'C', 'S1', 'S2') for b in BENCHES}
    assert seen.count(('zebralogic', 'G/test-read-S1-zebralogic')) == 2  # reopened after the recovery: same registered panel
    assert all(seen.count(key) == 1 for key in seen if not key[1].startswith('G/test-read-S1-'))
    # noise -> tau: identical requests, no mixed item, the 3-point floor (typed-v2 step 5w: R = 3 runs of B per item,
    # tau from B's own repeats; no item is ever excluded, a model-side unknown run would count in unknown_final)
    noise = json.loads((chain_dir / 's1' / 'noise' / 'noise.json').read_text())
    assert (noise['tau_points'], noise['n'], noise['mixed_items'], noise['unknown_final'], noise['items']) == (3.0, 4, 0, 0, 4)
    assert (noise['repeats'], noise['cells'], noise['rule'], noise['reruns']) == (3, 12, 'baseline_repeats', 0)
    assert gates.recompute(noise) == noise
    # decisions.json denominators of step 1 (searchqa): card accepted, program accepted against the card-mounted arm
    d1 = json.loads((chain_dir / 's1' / 'decisions.json').read_text())
    assert d1['bench'] == 'searchqa' and d1['evidence'] == 'engineering_fixture' and d1['typing']['new_type'] and d1['typing']['no_harm'] == []
    # step 5w: gate counts are runs (n * R) and name the arm that holds them (a new type without skills: F = B@noise)
    assert d1['outcomes'] == {'learn': {'items': 3, 'cells': 3, 'pass': 1, 'fail': 2, 'unknown': 0},
                              'gate': {'items': 4, 'cells': 12, 'repeats': 3, 'pass': 3, 'fail': 9, 'unknown': 0,
                                       'source': {'unit': 's1/noise', 'arm': 'B'}}}
    card = d1['cards'][0]
    assert (card['accepted'], card['reason'], card['n'], card['better'], card['worse'], card['excluded_unknown']) == (True, 'accepted', 4, 2, 0, 0)
    assert abs(card['mean_points'] - 50.0) < 1e-9 and card['tau_points'] == 3.0 and card['items'] == 4 and card['cells'] == 12
    assert card['baseline'] == {'unit': 's1/outcomes', 'arm': 'F', 'shared_from': {'unit': 's1/noise', 'arm': 'B'}}
    assert card['candidate_arm'] == {'unit': 's1/card-r1', 'arm': 'cand_card', 'shared_from': None}
    assert card['repeats'] == 3 and card['per_item'] and gates.recompute(card) == card
    assert d1['program_gate_current'] == 's1/outcomes-card'
    assert d1['outcomes_with_card'] == {'unit': 's1/outcomes-card', 'learn': {'items': 3, 'cells': 3, 'pass': 3, 'fail': 0, 'unknown': 0},
                                        'gate': {'items': 4, 'cells': 12, 'repeats': 3, 'pass': 9, 'fail': 3, 'unknown': 0,
                                                 'source': {'unit': 's1/card-r1', 'arm': 'cand_card'}}}
    program, = d1['programs']
    assert (program['accepted'], program['reason'], program['n'], program['fired_items'], program['procedure_id']) == (True, 'accepted', 4, 4, PROGRAM_ID)
    assert program['screen']['passed'] and program['smoke'] == {'items': 3, 'cells': 3, 'faults': []}
    assert (program['better_fired'], program['worse_fired']) == (1, 0) and abs(program['gain_points_fired'] - 25.0) < 1e-9
    assert program['baseline_selected'] is True  # addendum O5: the baseline is the accepted card round's runs
    assert program['fired_cells'] == [[row[0], 3] for row in d1['noise']['per_item']]  # fired in all R cells (O6)
    assert gates.recompute(program) == program
    # typed-v2 (step 4c): the decision names its proposal, the proposal's status and its slot (DESIGN 3.2, 4.1)
    assert (program['proposal'], program['status'], program['candidate'], program['unit']) == (1, 'passed', 1, 's1/program-1')
    # step 2 (zebralogic): a new type, both card rounds rejected, the program rejected at its gate
    d2 = json.loads((chain_dir / 's2' / 'decisions.json').read_text())
    assert d2['bench'] == 'zebralogic' and d2['typing']['type'] == 't02' and d2['typing']['new_type'] and d2['typing']['signature'] == 'puzzle_template'
    assert [(r['round'], r['accepted'], r['reason']) for r in d2['cards']] == [(1, False, 'gain_below_tau'), (2, False, 'gain_below_tau')]
    assert d2['cards'][0]['text_sha256'] != d2['cards'][1]['text_sha256']  # the revision round wrote another card
    assert d2['program_gate_current'] == 's2/outcomes' and d2['outcomes_with_card'] is None
    # typed-v2 (step 4c): proposal 1 (refused by the screen and its fix) gets a zero-call decision, proposal 2 is
    # promoted to slot 1 as p-zebralogic-2-2 (typed-v1 pin: one proposal p-zebralogic-2-1) and rejected at its gate
    dropped, promoted = d2['programs']
    assert (promoted['accepted'], promoted['reason'], promoted['procedure_id']) == (False, 'gain_below_tau', 'p-zebralogic-2-2')
    assert (promoted['proposal'], promoted['status'], promoted['candidate'], promoted['unit']) == (2, 'passed', 1, 's2/program-1')
    assert (dropped['proposal'], dropped['status'], dropped['candidate'], dropped['unit'], dropped['accepted']) == (
        1, 'dropped_screen', None, None, False)
    assert dropped['reason'].startswith('screen:policy: ') and 'smoke' not in dropped and dropped['procedure_id'] is None
    rows2 = json.loads((chain_dir / 's2' / 'programs' / 'proposals.json').read_text())
    assert [(r['n'], r['status'], r['slot']) for r in rows2] == [(1, 'dropped_screen', None), (2, 'passed', 1)]
    assert rows2[0]['first_screen'] == {'passed': False, 'check': 'policy', 'rules': ['import']}
    assert rows2[0]['fix']['reason'].startswith('policy: ') and all(r['format_retry']['readable'] for r in rows2)
    engineer = json.loads((chain_dir / 's2' / 'programs' / 'calls' / 'writer-program_writer.json').read_text())
    assert [json.loads(send['user'])['request'] for send in engineer] == ['propose', 'format_retry', 'fix']
    # the promoted program's lineage names the format retry call, whose reply gave it
    assert rows2[1]['procedure']['lineage']['engineer_call'] == rows2[1]['request_sha256'] == \
        rows2[1]['format_retry']['request_sha256'] != rows2[1]['format_retry']['first_request_sha256']
    assert sorted(p.name for p in (chain_dir / 's2').iterdir() if p.name.startswith('program')) == [
        'program-1', 'program-1-gate', 'program-1-smoke', 'programs']
    # the library after each step: the card with its frozen description, the program with the writer's call in its lineage
    s1 = library_.Library.load(chain_dir / 's1' / 'library.json')
    assert [s['skill_id'] for s in s1.skills] == ['card-t01-s1', 'prog-t01-s1-a']
    assert s1.get('card-t01-s1')['description'] == DESCRIPTION and s1.get('card-t01-s1')['body']['text'].strip() == smoke.DEFAULT_CARD
    assert s1.get('card-t01-s1')['name'] == 'evidence-qa-card-s1' and s1.get('prog-t01-s1-a')['name'] == 'evidence-qa-program-s1-a'
    procedure = s1.get('prog-t01-s1-a')['body']['procedure']
    proposals = json.loads((chain_dir / 's1' / 'programs' / 'proposals.json').read_text())
    assert procedure['id'] == PROGRAM_ID and procedure['lineage'] == {'parent': None, 'revises': None, 'engineer_call': proposals[0]['request_sha256']}
    assert [(r['n'], r['status'], r['slot']) for r in proposals] == [(1, 'passed', 1)]  # typed-v2 rows (step 4c)
    assert proposals[0]['first_screen'] == {'passed': True, 'check': None, 'rules': []} and proposals[0]['format_retry'] is None
    assert len(json.loads((chain_dir / 's1' / 'programs' / 'calls' / 'writer-program_writer.json').read_text())) == 1
    assert len(procedure['lineage']['engineer_call']) == 64 and procedure['evidence'] == 'engineering_fixture'
    assert s1.get('prog-t01-s1-a')['description'] == DESCRIPTION and s1.get('prog-t01-s1-a')['origin']['step'] == 1
    assert [s['skill_id'] for s in library_.Library.load(chain_dir / 's2' / 'library.json').skills] == ['card-t01-s1', 'prog-t01-s1-a']
    assert library_.Library.load(chain_dir / 's0' / 'library.json').skills == []
    # the type map: two signatures, two types, sources named by the pool pins
    tm = typing_.TypeMap.load(chain_dir / 's2' / 'typemap.json')
    sources = tm.data['sources']
    assert tm.summary() == {'t01': {'signature': 'question/context', 'sources': [typing_.source_id(services.manifest['pools']['searchqa'])],
                                    'card': 'card-t01-s1', 'programs': ['prog-t01-s1-a']},
                            't02': {'signature': 'puzzle_template', 'sources': [typing_.source_id(services.manifest['pools']['zebralogic'])],
                                    'card': None, 'programs': []}}
    assert all(src['members'] == 7 and src['threshold'] == 0.0 for src in sources.values())
    assert typing_.TypeMap.load(chain_dir / 's1' / 'typemap.json').summary().keys() == {'t01'}
    # reads: S1 / S2 cells carry mount records; S1 zebralogic is unseen (no type yet), S2 zebralogic typed without a card
    s1_sq = cells_of(chain_dir / 'test-read-S1-searchqa')
    assert len(s1_sq) == 2 and all(set(reads.MOUNT_KEYS) <= set(c['mount']) for c in s1_sq)
    assert all(c['mount']['type'] == 't01' and c['mount']['card_skill'] == 'card-t01-s1' and c['mount']['programs_enabled'] == ['prog-t01-s1-a']
               and c['mount']['selection']['status'] == 'ok' and c['correct'] is True and c['arm'] == 'F' for c in s1_sq)
    assert all(len(c['sends']) == 1 and len(c['selection_sends']) == 1 and c['selection_tokens'] > 0 and c['fired'] == [PROGRAM_ID]
               and c['tokens'] == c['solver_tokens'] + c['selection_tokens'] for c in s1_sq)
    s1_zb = cells_of(chain_dir / 'test-read-S1-zebralogic')
    assert len(s1_zb) == 2 and all(c['mount']['type'] is None and c['mount']['unknown_reason'] == 'unseen_signature' for c in s1_zb)
    s2_zb = cells_of(chain_dir / 'test-read-S2-zebralogic')
    assert all(c['mount']['type'] == 't02' and c['mount']['card_skill'] is None and c['mount']['selection']['status'] == 'not_needed' for c in s2_zb)
    c0_sq = cells_of(chain_dir / 'test-read-C0-searchqa')
    assert sorted(c['correct'] for c in c0_sq) == [False, True] and all(c['mount']['card_skill'] is None for c in c0_sq)
    # open mirrors: counts only
    mirror = json.loads((chain_dir / 'read-status' / 'S1-searchqa.json').read_text())
    assert mirror['status'] == 'complete' and mirror['cells'] == 2 and mirror['mount']['typed_fraction'] == 1.0
    assert mirror['mount']['selection_status'] == {'ok': 2} and mirror['tokens']['selection'] > 0
    for stem in ('S1-searchqa', 'S1-zebralogic', 'S2-searchqa', 'C0-zebralogic'):
        text = (chain_dir / 'read-status' / (stem + '.json')).read_text()
        assert not {'correct', 'incorrect', 'reply', 'item_ids'} & set(json.loads(text)) and CANARY not in text and '-p0' not in text
    assert not any(word in json.dumps(state['reads']) for word in ('correct', 'pass', CANARY))
    # no file outside the test-read-* directories carries a panel item's reply text; the sealed units do
    for rows in panels.values():
        for item in rows:
            found = files_with(root, CANARY + '-' + item['task_id'])
            assert found and all(path.split('/')[1].startswith('test-read-') for path in found), (item['task_id'], found)
    assert files_with(root, CANARY + '-searchqa-l0')  # practice replies live in the open learning units
    # the closed readout never opens a sealed directory and carries no reply text
    sealed_guard(monkeypatch)
    closed = readout.build(root, now=0)
    monkeypatch.undo()
    doc = closed['chains']['G']
    assert doc['mode'] == 'closed' and 'panels' not in doc and doc['steps'][1]['bench'] == 'searchqa' and doc['steps'][2]['bench'] == 'zebralogic'
    assert doc['steps'][1]['noise']['tau_points'] == 3.0 and doc['mount_check']['all_present']
    decisions = {(d['label'], d['accepted']) for d in doc['steps'][1]['decisions']}
    assert ('cards[0]', True) in decisions and ('programs[0]', True) in decisions
    # the zero-call decision of the dropped zebralogic proposal is a readout row of its own (no unit, no counts)
    rows = {d['label']: d for d in doc['steps'][2]['decisions']}
    assert rows['programs[0]']['accepted'] is False and rows['programs[0]']['reason'].startswith('screen:policy: ')
    assert rows['programs[0]']['n'] is None and rows['programs[1]']['reason'] == 'gain_below_tau'  # step 5w names
    # step 5w: outcomes-card runs its learn cells only (its gate arm shares the accepted round's runs); a card round
    # runs R = 3 cells per gate item; the readout folds the repeat labels into their arm
    units1, units2 = doc['steps'][1]['units'], doc['steps'][2]['units']
    assert units1['outcomes-card']['cells'] == 3 and units2['card-r2']['cells'] == 12
    assert units1['outcomes-card']['gate_plan']['shared_from'] == {'unit': 's1/card-r1', 'arm': 'cand_card'}
    assert units2['card-r2']['by_arm']['cand_card']['cells'] == 12 and set(units2['card-r2']['by_arm']) == {'cand_card'}
    assert sorted(units2['card-r2']['by_arm']['cand_card']['repeats']) == ['1', '2', '3']
    text = Path(closed['written']['G']['markdown']).read_text()
    assert 'status: complete' in text and 'Closed mode' in text and CANARY not in text and CANARY not in Path(closed['written']['G']['json']).read_text()
    # the open readout: paired tables, the 5x5 rows of this chain's order, CL metrics with the recorded home steps
    opened = readout.build(root, open_sealed=True, now=1, order=BENCHES)['chains']['G']
    sq = opened['panels']['searchqa']
    assert sq['events'] == ['C0', 'C', 'S1', 'S2'] and sq['items_common'] == 2
    assert {e: sq['per_event'][e]['accuracy']['L'] for e in sq['events']} == {'C0': .5, 'C': .5, 'S1': 1.0, 'S2': 1.0}
    assert set(sq['pairs']) == {'S1-C0', 'S1-C', 'S2-C0', 'S2-C', 'S2-S1'}
    pair = sq['pairs']['S1-C0']
    assert (pair['n'], pair['excluded_unknown'], pair['better'], pair['worse'], pair['tied']) == (2, 0, 1, 0, 1) and abs(pair['mean_points'] - 50.0) < 1e-9
    assert sq['pairs']['S2-S1']['mean_points'] == 0.0 and sq['per_event']['S1']['routing']['programs'] == {'prog-t01-s1-a': 2}
    zb = opened['panels']['zebralogic']
    assert {e: zb['per_event'][e]['accuracy']['L'] for e in zb['events']} == {'C0': .5, 'C': .5, 'S1': .5, 'S2': .5}
    assert zb['same_request_noise']['identical_requests'] == 2 and zb['same_request_noise']['noise']['flip_rate'] == 0.0
    assert zb['per_event']['S1']['routing']['unknown_by_reason'] == {'unseen_signature': 2} and zb['per_event']['S2']['routing']['typed_fraction'] == 1.0
    five = opened['five_by_five']
    assert [(row['step'], row['evolved_bench']) for row in five.values()] == [(1, 'searchqa'), (2, 'zebralogic')]
    assert abs(five['S1']['diff_points_vs_C0']['searchqa'] - 50.0) < 1e-9 and five['S1']['diff_points_vs_C0']['zebralogic'] == 0.0
    assert five['S2']['accuracy_L']['searchqa'] == 1.0 and five['S2']['accuracy_L']['officeqa'] is None
    cl = opened['cl_metrics']
    assert cl['final_event'] == 'S2' and cl['home_steps'] == {'searchqa': 1, 'zebralogic': 2}
    s = cl['per_bench']['searchqa']
    assert s['home_step'] == 1 and s['final_event'] == 'S2' and s['L'] == {**s['L'], 'final': 1.0, 'C0': .5, 'gain_over_C0': .5, 'forgetting': 0.0,
                                                                       'backward_transfer': 0.0, 'forward_transfer': None, 'plasticity': .5}
    z = cl['per_bench']['zebralogic']['L']
    assert z == {**z, 'final': .5, 'gain_over_C0': 0.0, 'forward_transfer': 0.0, 'backward_transfer': None, 'plasticity': 0.0}
    assert cl['macro']['L']['gain_over_C0'] == {'mean': .25, 'n_benches': 2}
    check = opened['mount_check']
    assert check['all_present'] and check['reads']['S1-searchqa']['skills_seen'] == ['card-t01-s1', 'prog-t01-s1-a']
    assert check['reads']['S2-zebralogic']['typed_fraction'] == 1.0 and check['reads']['S1-zebralogic']['typed_fraction'] == 0.0
    assert opened['read_units']['S1-zebralogic']['done'] and opened['read_units']['S1-zebralogic']['stop_reason'] is None
    assert opened['read_tokens']['S1-searchqa'] == sum(c['tokens'] for c in s1_sq)
    # the ledger settled every send; a third run of a complete chain returns its state without any call
    ledger = json.loads((chain_dir / 'ledger.json').read_text())
    assert ledger['pending'] == {} and ledger['stopped'] is False and ledger['reported'] > 0
    before = len(script.calls)
    assert chain.run(root, 'G', services=services, resume=True)['complete'] and len(script.calls) == before
    # the s2 revision round's examples came from the rejected round-1 card's learn cells (a revise request shows the
    # solver's attempts WITH the previous card, as its system prompt says)
    d2_learn = cells_of(chain_dir / 's2' / 'card-r1-learn')
    assert len(d2_learn) == 3 and {c['arm'] for c in d2_learn} == {'cand_card'} and d2['cards'][1]['examples_unit'] == 's2/card-r1-learn'
    revise = json.loads((chain_dir / 's2' / 'card-r2' / 'calls' / 'writer-card_writer.json').read_text())[0]
    request = json.loads(revise['user'])
    assert request['request'] == 'revise' and request['previous_card'].strip() == smoke.DEFAULT_CARD
    assert {e['view'] for e in request['examples']} <= {c['sends'][0]['user'][:3000] for c in d2_learn}


def test_read_cell_raising_on_a_later_item_pauses_as_incomplete_and_the_recovery_completes_the_panel(tmp_path):
    """A non-first panel cell that raises outside the shell leaves no record: the read is incomplete, the chain
    pauses (the partial panel is never marked done), the owner's recovery reopens the unit and only the missing
    cell is solved; the opened readout then sees the whole panel."""
    root = tmp_path / 'run'
    services, script, panels, seen = build(root)
    services.order = ('searchqa',)
    real_solve = services.solve_fn
    broken = {'on': True}

    def solve(bench, item, mounted, **kwargs):
        if broken['on'] and kwargs['unit'] == 'test-read-C0-searchqa' and item['task_id'] == 'searchqa-p1':
            raise KeyError('searchqa-p1')  # a KeyError naming a test task id: its text must not reach the open state
        return real_solve(bench, item, mounted, **kwargs)
    services.solve_fn = solve
    state = chain.run(root, 'G', services=services, sleep=lambda s: None)
    chain_dir = root / 'G'
    assert state['paused']['reason'] == 'incomplete_read:missing_cells' and state['paused']['unit'] == 'read-C0-searchqa'
    assert 'read-C0-searchqa' not in state['done_units'] and 'searchqa-p1' not in (chain_dir / 'state.json').read_text()
    mirror = json.loads((chain_dir / 'read-status' / 'C0-searchqa.json').read_text())
    assert mirror == {**mirror, 'status': 'incomplete', 'cells': 1, 'missing_cells': 1, 'unsubmitted': 1, 'stop_reason': None}
    assert len(list((chain_dir / 'test-read-C0-searchqa' / 'unsubmitted').glob('*.json'))) == 1
    broken['on'] = False
    units.write_json(chain_dir / 'recovery.json', {'by': 'owner', 'date': '2026-11-10', 'decision': 'cell fixed'})
    solves_before = len([c for c in script.calls if c[1] == 'test-read-C0-searchqa'])
    state = chain.run(root, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert len([c for c in script.calls if c[1] == 'test-read-C0-searchqa']) == solves_before + 1  # only the missing cell
    mirror = json.loads((chain_dir / 'read-status' / 'C0-searchqa.json').read_text())
    assert mirror == {**mirror, 'status': 'complete', 'cells': 2, 'missing_cells': 0, 'unsubmitted': 1}
    assert (chain_dir / 'test-read-C0-searchqa' / 'done-stopped-1.json').exists()
    opened = readout.build(root, open_sealed=True, now=2, order=('searchqa',))['chains']['G']
    assert opened['panels']['searchqa']['items_common'] == 2 and opened['panels']['searchqa']['per_event']['C0']['n'] == 2
