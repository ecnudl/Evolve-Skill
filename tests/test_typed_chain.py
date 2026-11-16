"""The typed-v2 chain and smoke on fully faked services (no network, no Docker, no /data, nothing paid).

The fakes of mount / writers / reads follow the design §5.5-5.8 contracts; the scripted clients, hash embeddings,
synthetic items and fake solve are the smoke's own (``smoke.fake_services`` with injected modules).
"""
import json
import shutil
import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.execskill.typed import ORDER, cards, chain, library as library_, smoke, tasktypes as typing_, units


@pytest.fixture
def tmp_path():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    root = Path('/tmp/typed2-neutral')
    root.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='chain-', dir=root))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


# ---- fakes of the other typed modules (design §5.5, §5.6, §5.8) ----------------------------------------------
class FakeMount:
    """mount.mount: C0 = format only, C = historical card, B = the learning base alone (typed-v2 step 5b, addendum
    D17), F = the type's card + selected programs. The learned arms compose on the base the chain hands over
    (``base_card``: 'FORMAT' or 'HISTORICAL' in the fake system text), which every row records."""

    @staticmethod
    def mount(bench, item, *, arm, typemap, library, vector, selector=None, candidate=None, view=None, runtime=None,
              base_card='format'):
        view = smoke.synthetic_view(bench, item) if view is None else view
        signature = typing_.structural_signature(view)
        row = {'arm': arm, 'signature': signature, 'type': None, 'source': None, 'distance': None, 'threshold': None,
               'unknown_reason': None, 'card_skill': None, 'card_text': None, 'programs_offered': [], 'selection': None,
               'programs_enabled': [], 'enabled': [], 'base_card': base_card}
        if arm == 'C':
            row['card_text'] = 'historical card'
        elif arm not in ('C0', 'B'):
            row.update(typemap.assign(signature, vector))
            tid = row['type']
            card = library.active_card(tid) if tid else None
            if card is not None:
                row['card_skill'], row['card_text'] = card['skill_id'], card['body']['text']
            programs = library.programs(tid) if tid else []
            if programs and selector is not None:
                request = library_.selection_request([{'name': p['name'], 'description': p['description']} for p in programs],
                                                     typing_.public_text(view))
                found = selector(request['system'], request['user'])
                try:
                    chosen, status = library_.parse_selection(found.get('response') or '', {p['name'] for p in programs}), 'ok'
                except ValueError:
                    chosen, status = {'use': [], 'why': None}, 'parse_failure'
                row['programs_offered'] = [p['skill_id'] for p in programs]
                row['selection'] = {'use': chosen['use'], 'status': status, 'request_sha256': request['request_sha256']}
                row['programs_enabled'] = [p['skill_id'] for p in programs if p['name'] in chosen['use']]
                row['enabled'] = [p['body']['procedure'] for p in programs if p['name'] in chosen['use']]
            if arm == 'cand_card':
                row['card_text'] = candidate['text']
            if arm == 'cand_program':
                row['enabled'] = row['enabled'] + [candidate['procedure']]
        base = 'HISTORICAL' if base_card == 'historical' and arm not in ('C0', 'C') else 'FORMAT'
        row['system_card'] = (row['card_text'] + '\n\n' + base) if row['card_text'] else base
        row['system_card_sha256'] = units.sha256_text(row['system_card'])  # typed-v2 step 5w: as mount.mount records it
        return row

    @staticmethod
    def mount_identity(bench, item, *, arm, typemap, library, vector, candidate=None, view=None, runtime=None,
                       base_card='format'):
        """typed-v2 step 5w (DESIGN 3.4 "Shared arms"): ``mount.mount_identity`` of this fake, consistent with its
        ``mount`` (the system card, the programs its type offers with their bodies, the forced candidate), zero calls."""
        row = FakeMount.mount(bench, item, arm=arm, typemap=typemap, library=library, vector=vector, selector=None,
                              candidate=candidate, view=view, runtime=runtime, base_card=base_card)
        tid = row['type']
        offered = ([[p['skill_id'], units.sha256_text(json.dumps(p['body'], sort_keys=True))] for p in library.programs(tid)]
                   if tid and arm not in ('C0', 'C', 'B') else [])
        forced = units.sha256_text(json.dumps(candidate['procedure'], sort_keys=True)) if arm == 'cand_program' else None
        return {'system_card_sha256': row['system_card_sha256'], 'programs_offered': offered, 'forced': forced}

    @staticmethod
    def package_for(records, *, step, evidence):
        return SimpleNamespace(step=step, evidence=evidence, order=[r['id'] for r in records])


def procedure(pid):
    return {'id': pid, 'origin': 'searchqa', 'description': 'fake helper', 'hooks': ['applies'],
            'source': 'def applies(view):\n    return True\n', 'excluded_benches': []}


# typed-v2 (step 4c): the screen reason a writer row of each unpromoted status carries (``writers._row``; 4b's report)
UNPROMOTED_REASONS = {'dropped_screen': 'policy: [{"rule": "import"}] | fix: policy: [{"rule": "name"}]',
                      'unreadable': 'unparseable: entry_field: Change 2: a field has the wrong type.',
                      'kind_not_new': 'kind_not_new:revise', 'no_reply': 'no_reply'}


def proposal_row(n, status, sha, *, slot=None, pid=None):
    """One ``proposals.json`` row of the typed-v2 shape (DESIGN 3.2, 4.1; ``writers._row``): the procedure exactly
    for a row with a slot, a whole-reply row (``no_reply``) with ``n`` None."""
    made = procedure(pid) if slot is not None else None
    reason = None if slot is not None else 'not_needed' if status == 'not_needed' else UNPROMOTED_REASONS[status]
    return {'n': n, 'status': status, 'slot': slot, 'procedure': made, 'screen': {'passed': made is not None, 'reason': reason},
            'first_screen': {'passed': True, 'check': None, 'rules': []} if status == 'passed' else None, 'fix': None,
            'request_sha256': sha, 'read': None, 'format_retry': None, 'entry': {'description': 'fake'} if pid else None,
            'source': procedure(pid)['source'] if pid else None, 'kind': 'new', 'repairs': []}


class FakeWriters:
    """Fakes of ``writers`` (design §5.6). ``proposals``: {bench: [spec]} in the writer's order; a spec is a procedure
    id (a proposal that passes the screen) or (status, id) for any other status. Like ``writers.propose_programs``
    the fake promotes: a passing spec takes the next slot while one is free, else it is ``not_needed``."""

    def __init__(self, *, proposals=None, card_text=None, crash=None):
        self.proposals = proposals or {}
        self.card_text = card_text or (lambda bench, round_: '- card for %s round %d' % (bench, round_))
        self.crash = crash  # callable(bench, round) -> bool: raise inside write_card
        self.describe_calls, self.propose_calls, self.write_calls = [], [], []

    @staticmethod
    def corpus_for(bench, items):
        return {'bench': bench, 'ids': [item['task_id'] for item in items]}

    @staticmethod
    def hook_view_for(bench, view):
        return {'routing_view': view, 'bench': bench}

    def write_card(self, *, bench, runtime, current_text, examples, corpus, practice_ids, call, round, previous=None, result=None,
                   base_card='format', members=None):
        if self.crash is not None and self.crash(bench, round):
            raise RuntimeError('writer crashed')
        # typed-v2 step 5x (addendum D16): a shared type's member rows are recorded (the chain passes none otherwise)
        self.write_calls.append({'bench': bench, 'round': round, 'current': current_text, 'previous': previous,
                                 'result': result, 'examples': len(examples), 'ids': list(practice_ids), 'corpus': corpus,
                                 'base_card': base_card, **({'members': members} if members is not None else {})})
        call('CARD_WRITE' if round == 1 else 'CARD_REVISE', json.dumps({'bench': bench, 'round': round}))
        text = self.card_text(bench, round)
        sha = call.sends[-1]['request_sha256']
        # typed-v2 attempt rows (DESIGN 3.1): content characters (a final newline not counted) and bullet lines
        return {'text': text, 'attempts': [{'request_sha256': sha, 'violation': None if text else 'length',
                                            'chars': cards.content_chars(text), 'bullets': cards.bullet_count(text)}],
                'request': {'kind': 'write' if round == 1 else 'revise', 'request_sha256': sha}}

    def propose_programs(self, *, bench, runtime, skill_index, examples, hook_view, parent, call, max_candidates=2, evidence,
                         step=None, base_card='format', members=None):
        self.propose_calls.append({'bench': bench, 'index': skill_index, 'parent': parent, 'evidence': evidence, 'step': step,
                                   'examples': len(examples), 'view_keys': sorted(hook_view['routing_view']),
                                   'base_card': base_card, **({'members': members} if members is not None else {})})
        call('ENGINEER', json.dumps({'bench': bench, 'index': skill_index}))
        sha = call.sends[-1]['request_sha256']
        rows, slots = [], 0
        for n, spec in enumerate(self.proposals.get(bench, []), 1):
            status, pid = ('passed', spec) if isinstance(spec, str) else spec
            if status in chain.SLOT_STATUSES and slots < max_candidates:
                slots += 1
                rows.append(proposal_row(n, status, sha, slot=slots, pid=pid))
            else:
                status = 'not_needed' if status in chain.SLOT_STATUSES else status
                rows.append(proposal_row(None if status == 'no_reply' else n, status, sha, pid=pid))
        return rows

    def describe(self, skill, examples, call):
        request = library_.description_request(skill, examples)
        found = call(request['system'], request['user'])
        self.describe_calls.append(skill['skill_id'])
        return {'description': library_.parse_description(found['response']), 'request_sha256': request['request_sha256'],
                'attempts': [request['request_sha256']]}

    @staticmethod
    def outcomes_for_writer(cells, items, *, bench, seed=0, baseline=None):
        return [{'task_id': row['item_id'], 'view': 'public text of ' + row['item_id'], 'reply': row.get('reply') or '',
                 'outcome': 'pass' if row.get('correct') else 'fail', 'reference': None, 'baseline': baseline}
                for row in cells]


class FakeReads:
    """reads.read_panel: records the call, writes the open count-only mirror, returns a status. ``stop``: a stop
    reason every read reports; ``missing``: {(event, bench): missing cells} reported once (the resumed read is
    complete); ``statuses``: a callable(event, bench, n) -> status overriding the default (consumed per call)."""

    def __init__(self):
        self.calls, self.lock, self.stop, self.missing, self.statuses = [], threading.Lock(), None, {}, None

    def read_panel(self, root, chain_name, event, bench, *, library, typemap, services):
        tasks = smoke.practice_panel(services)(bench, 'read-%s-%s' % (event, bench))
        with self.lock:
            self.calls.append((event, bench, [t['task_id'] for t in tasks], library.summary(), typemap.summary()))
            missing = self.missing.pop((event, bench), 0)
        status = {'event': event, 'bench': bench, 'cells': len(tasks) - missing, 'expected_cells': len(tasks),
                  'missing_cells': missing, 'status': 'complete' if not missing and not self.stop else 'incomplete',
                  'tokens': 7, 'stop_reason': self.stop}
        if self.statuses is not None:
            status = self.statuses(event, bench, len(tasks)) or status
        units.write_json(Path(root) / chain_name / 'read-status' / ('%s-%s.json' % (event, bench)), status)
        return status


def scripted_outcome(bench, item_id, mounted):
    """No skill: fail. A card: pass on even-numbered items. A program enabled: pass."""
    if mounted.get('enabled'):
        return 'pass'
    if mounted.get('card_text'):
        return 'pass' if int(item_id[-1]) % 2 == 0 else 'fail'
    return 'fail'


def build(root, chain_name='G', *, order=ORDER, proposals=None, scripted=None, writers=None, reads=None, cap=None, sizes=None):
    """Fake services on the synthetic manifest (smoke slices: learn 2, gate 3, panel 2 per bench unless ``sizes``)
    with the fake modules injected."""
    manifest = smoke.synthetic_manifest(**({'sizes': sizes} if sizes else {}))
    modules = SimpleNamespace(mount=FakeMount, writers=writers or FakeWriters(proposals=proposals), reads=reads or FakeReads())
    script = smoke.Script({'outcomes': scripted_outcome, **(scripted or {})})
    services = smoke.fake_services(root, chain_name, manifest, scripted=script, modules=modules)
    services.order, services.cap = order, cap
    if sizes is None:
        services.slices = smoke.smoke_slices(services.items, services.slices)
    return services, modules, script


def recovery(root, chain_name='G', decision='continue'):
    units.write_json(Path(root) / chain_name / 'recovery.json', {'by': 'owner', 'date': '2026-11-10', 'decision': decision})


def state_of(root, chain_name='G'):
    return json.loads((Path(root) / chain_name / 'state.json').read_text())


# ---- tests -------------------------------------------------------------------------------------------------------
def test_full_chain_units_decisions_and_reads(tmp_path):
    services, modules, script = build(tmp_path, proposals={'searchqa': ['p-sq-1'], 'zebralogic': ['p-zb-1']},
                                      scripted={'faults': {'p-zb-1': ['zebralogic-l0']}})
    state = chain.run(tmp_path, 'G', services=services)
    assert state['complete'] and state['paused'] is None, state
    chain_dir = tmp_path / 'G'
    confirm = json.loads((chain_dir / 'confirm.json').read_text())
    assert confirm['passed'] and 'response' not in confirm and confirm['checks']['model']
    done = state['done_units']
    expected_head = ['confirm'] + ['read-C0-%s' % b for b in ORDER] + ['read-C-%s' % b for b in ORDER] + ['step-0']
    assert done[:len(expected_head)] == expected_head
    s1 = done[done.index('s1/noise'):done.index('step-1') + 1]
    assert s1 == ['s1/noise', 's1/typing', 's1/outcomes', 's1/card-r1', 's1/outcomes-card', 's1/programs',
                  's1/program-1-smoke', 's1/program-1-gate'] + ['read-S1-%s' % b for b in ORDER] + ['step-1']
    # noise -> tau (identical requests, no mixed item -> the 3-point floor); typed-v2 step 5b (addendum D17): the
    # learning base B (mount arm B, the manifest's base 'format' here) takes the place of C0; step 5w (DESIGN 3.4):
    # R = 3 fresh runs per item, labels B#1..3
    noise = json.loads((chain_dir / 's1' / 'noise' / 'noise.json').read_text())
    assert noise['tau_points'] == 3.0 and noise['n'] == 3 and noise['mixed_items'] == 0 and noise['mount_arm'] == 'B'
    assert noise['repeats'] == 3 and noise['cells'] == 9 and noise['rule'] == 'baseline_repeats'
    cells = [json.loads(p.read_text()) for p in (chain_dir / 's1' / 'noise' / 'cells').glob('*.json')]
    assert sorted(c['arm'] for c in cells) == ['B#1'] * 3 + ['B#2'] * 3 + ['B#3'] * 3
    assert all(c['mount']['arm'] == 'B' for c in cells)
    assert all(c['mount']['base_card'] == 'format' for c in cells)
    # step 1: card accepted (even items pass), program accepted (fires everywhere, lifts the odd item), both described
    decisions = json.loads((chain_dir / 's1' / 'decisions.json').read_text())
    assert decisions['cards'][0]['accepted'] and decisions['cards'][0]['reason'] == 'accepted'
    assert decisions['programs'][0]['accepted'] and decisions['programs'][0]['fired_items'] == 3
    # step 5w: a new type without skills mounts F = B (DESIGN 3.4 case (b)): s1/outcomes runs its learn cells only and
    # its gate runs are B@noise's (n * R runs counted, the source named)
    assert decisions['outcomes']['gate'] == {'items': 3, 'cells': 9, 'repeats': 3, 'pass': 0, 'fail': 9, 'unknown': 0,
                                             'source': {'unit': 's1/noise', 'arm': 'B'}}
    lib = library_.Library.load(chain_dir / 's1' / 'library.json')
    card, prog = lib.active_card('t01'), lib.programs('t01')[0]
    assert card['name'] == 'evidence-qa-card-s1' and card['description'].startswith('Scripted skill')
    assert prog['skill_id'] == 'prog-t01-s1-a' and prog['name'] == 'evidence-qa-program-s1-a' and prog['description']
    tm = typing_.TypeMap.load(chain_dir / 's1' / 'typemap.json')
    assert tm.summary()['t01'] == {'signature': 'question/context', 'sources': [tm.data['types']['t01']['sources'][0]],
                                   'card': 'card-t01-s1', 'programs': ['prog-t01-s1-a']}
    assert modules.writers.describe_calls[:2] == ['card-t01-s1', 'prog-t01-s1-a']
    # step 2: officeqa shares the signature -> no-harm unit -> merged into t01; card revision round rejected twice;
    # the revision round's examples come from the rejected card's LEARN cells (card-r1-learn), ordered against the
    # current arm's outcomes
    typing = json.loads((chain_dir / 's2' / 'typing' / 'typing.json').read_text())
    assert typing['type'] == 't01' and not typing['new_type'] and typing['no_harm'][0]['merge']
    assert 's2/noharm-t01' in done
    d2 = json.loads((chain_dir / 's2' / 'decisions.json').read_text())
    assert [r['accepted'] for r in d2['cards']] == [False, False] and d2['cards'][1]['round'] == 2
    assert [r['examples_unit'] for r in d2['cards']] == ['s2/outcomes', 's2/card-r1-learn']
    assert done[done.index('s2/card-r1'):done.index('s2/card-r2') + 1] == ['s2/card-r1', 's2/card-r1-learn', 's2/card-r2']
    learn_cells = [json.loads(p.read_text()) for p in (chain_dir / 's2' / 'card-r1-learn' / 'cells').glob('*.json')]
    assert sorted(c['item_id'] for c in learn_cells) == ['officeqa-l0', 'officeqa-l1'] and {c['arm'] for c in learn_cells} == {'cand_card'}
    assert modules.writers.write_calls[2]['previous'] == '- card for officeqa round 1' and modules.writers.write_calls[2]['result']['kind'] == 'card'
    assert d2['programs'] == []  # no proposal for officeqa
    # step 3: zebralogic -> new type; its program faults on a smoke item -> rejected before any gate
    d3 = json.loads((chain_dir / 's3' / 'decisions.json').read_text())
    assert d3['typing']['type'] == 't02' and d3['typing']['new_type']
    assert d3['programs'][0]['reason'] == 'smoke_fault' and d3['programs'][0]['smoke']['faults'][0]['item_id'] == 'zebralogic-l0'
    assert 's3/program-1-smoke' in done and 's3/program-1-gate' not in done
    # the engineer ran after the card acceptance and saw names + descriptions (+ the opaque home type) only, never a
    # card body; it sees the index of ALL types (step 3 evolves t02 and still sees t01's skills)
    index = modules.writers.propose_calls[0]['index']
    assert [row['name'] for row in index] == ['evidence-qa-card-s1'] and set(index[0]) == {'name', 'kind', 'description', 'home_type'}
    assert [row['name'] for row in modules.writers.propose_calls[1]['index']] == ['evidence-qa-card-s1', 'evidence-qa-program-s1-a']
    assert [(row['name'], row['home_type']) for row in modules.writers.propose_calls[2]['index']] == [
        ('evidence-qa-card-s1', 't01'), ('evidence-qa-program-s1-a', 't01'), ('grid-puzzle-card-s3', 't02')]
    assert not any('body' in row or 'text' in row for call in modules.writers.propose_calls for row in call['index'])
    parent = modules.writers.propose_calls[1]['parent']
    assert parent.order == ['p-sq-1'] and parent.step == 'typed/G/s2' and modules.writers.propose_calls[1]['step'] == 2
    assert modules.writers.propose_calls[0]['evidence'] == 'smoke' and modules.writers.propose_calls[0]['parent'].order == []
    assert modules.writers.write_calls[0]['corpus'] == {'bench': 'searchqa', 'ids': ['searchqa-l0', 'searchqa-l1']}
    # reads: C0 and C anchors, then one event per step, five panels each, with the frozen library of the step
    events = [(e, b) for e, b, *_ in modules.reads.calls]
    assert len(events) == 35 and events[:5] == [('C0', b) for b in ORDER] and events[30:] == [('S5', b) for b in ORDER]
    s1_read = [row for row in modules.reads.calls if row[0] == 'S1' and row[1] == 'searchqa'][0]
    assert s1_read[2] == ['searchqa-p0', 'searchqa-p1'] and s1_read[4]['t01']['card'] == 'card-t01-s1'
    assert (chain_dir / 'read-status' / 'S1-searchqa.json').exists()
    assert set(state['reads']['S1']['searchqa']) == {'event', 'bench', 'cells', 'expected_cells', 'missing_cells', 'status',
                                                      'tokens', 'stop_reason'}
    # frozen per step, library versions immutable, five steps
    for k in range(0, 6):
        assert (chain_dir / ('s%d' % k) / 'library.json').exists() and (chain_dir / ('s%d' % k) / 'typemap.json').exists()
    assert library_.Library.load(chain_dir / 's5' / 'library.json').summary()[0]['skill_id'] == 'card-t01-s1'
    # no file of the learning side carries a sealed word; the ledger settled every send
    assert not [p for p in chain_dir.rglob('*') if 'test' in str(p.relative_to(tmp_path)).lower()]
    ledger = json.loads((chain_dir / 'ledger.json').read_text())
    assert ledger['pending'] == {} and ledger['reported'] > 0 and state['ledger']['sends'] == ledger['sends']


def test_writer_screen_failure_and_description_failure(tmp_path):
    writers = FakeWriters(proposals={'searchqa': ['p-1']}, card_text=lambda bench, r: None)
    services, modules, script = build(tmp_path, order=('searchqa',), writers=writers,
                                      scripted={'replies': {'describer': 'not json'}})
    state = chain.run(tmp_path, 'G', services=services)
    assert state['complete']
    d1 = json.loads((tmp_path / 'G' / 's1' / 'decisions.json').read_text())
    assert d1['cards'] == [dict(d1['cards'][0])] and d1['cards'][0]['reason'] == 'writer_screens_failed'
    assert 's1/card-r2' not in state['done_units'] and 's1/outcomes-card' not in state['done_units']
    assert d1['programs'][0]['reason'] == 'description_failed' and not d1['programs'][0]['accepted']
    assert library_.Library.load(tmp_path / 'G' / 's1' / 'library.json').skills == []
    # Codex review round 2, finding 1: the overridden program decision is reproduced from its own record, and an
    # override the gate does not allow (another reason, or a gate verdict that rejects) is never reproduced
    program = d1['programs'][0]
    assert program['gate_verdict']['accepted'] is True and chain.recompute_decision(program) == program
    assert chain.recompute_decision({**program, 'reason': 'harm'}) != {**program, 'reason': 'harm'}
    flipped = {**program, 'gate_verdict': {'accepted': False, 'reason': 'gain_below_tau'}}
    assert chain.recompute_decision(flipped) != flipped


def test_first_call_unconfirmed_pauses_before_anything_paid(tmp_path):
    services, modules, script = build(tmp_path, order=('searchqa',), scripted={'echo': {'G': 'other-model'}})
    state = chain.run(tmp_path, 'G', services=services)
    assert state['paused']['reason'] == 'first_call_unconfirmed' and state['paused']['unit'] == 'confirm'
    assert (tmp_path / 'G' / 'confirm-failed-1.json').exists() and not (tmp_path / 'G' / 'confirm.json').exists()
    assert modules.reads.calls == [] and script.counts == {'first_call': 1}


def test_cap_pause_and_recovery_consumed_once(tmp_path):
    usage = {'prompt_tokens': 100, 'completion_tokens': 4000, 'total_tokens': 4100}  # within the bounds, 4100 per send
    big = lambda system, user: {**smoke.receipt('x', model='glm-5.3'), 'usage': usage}
    services, modules, script = build(tmp_path, order=('searchqa',), cap=20_000, scripted={'replies': {'solver': big}})
    state = chain.run(tmp_path, 'G', services=services)
    assert state['paused']['reason'] == 'token_cap' and state['paused']['unit'] == 's1/noise'
    assert json.loads((tmp_path / 'G' / 'ledger.json').read_text())['stop_reason'] == 'token_cap'
    with pytest.raises(ValueError):
        chain.run(tmp_path, 'G', services=services)  # existing state without resume
    with pytest.raises(ValueError):
        chain.run(tmp_path, 'G', services=services, resume=True)  # resume without the owner's recovery.json
    units.write_json(tmp_path / 'G' / 'recovery.json', {'by': 'owner', 'date': '2026-11-10', 'decision': 'retry'})
    state = chain.run(tmp_path, 'G', services=services, resume=True)
    assert not (tmp_path / 'G' / 'recovery.json').exists() and (tmp_path / 'G' / 'recovery-consumed-1.json').exists()
    assert state['recoveries'][0]['decision'] == 'retry' and state['paused']['reason'] == 'token_cap'  # cap never cleared
    with pytest.raises(ValueError):
        chain.run(tmp_path, 'G', services=services, resume=True)  # consumed exactly once
    assert len(list((tmp_path / 'G').glob('recovery-consumed-*.json'))) == 1


def test_crash_after_step_one_then_resume_continues_without_redoing(tmp_path):
    crash = {'on': True}
    writers = FakeWriters(crash=lambda bench, r: crash['on'] and bench == 'officeqa')
    services, modules, script = build(tmp_path, order=('searchqa', 'officeqa'), writers=writers)
    state = chain.run(tmp_path, 'G', services=services)
    assert state['paused']['reason'] == 'exception:RuntimeError' and state['paused']['unit'] == 's2/card-r1'
    assert 'step-1' in state['done_units'] and 's2/outcomes' in state['done_units']
    before = len([c for c in script.calls if c[1] and c[1].startswith('s1/')])
    reads_before = len(modules.reads.calls)
    crash['on'] = False
    units.write_json(tmp_path / 'G' / 'recovery.json', {'by': 'owner', 'date': '2026-11-10', 'decision': 'continue'})
    state = chain.run(tmp_path, 'G', services=services, resume=True)
    assert state['complete'] and state['paused'] is None
    assert len([c for c in script.calls if c[1] and c[1].startswith('s1/')]) == before  # step-1 units not redone
    assert [e for e, *_ in modules.reads.calls[reads_before:]] == ['S2'] * 2  # only the pending reads ran
    assert state['done_units'].count('s1/noise') == 1 and state['recoveries'][0]['paused']['unit'] == 's2/card-r1'
    assert json.loads((tmp_path / 'G' / 's2' / 'decisions.json').read_text())['typing']['type'] == 't01'


def test_first_cell_configuration_failure_pauses_and_resumes(tmp_path):
    broken = {'on': True}
    services, modules, script = build(tmp_path, order=('searchqa',))
    real_solve = services.solve_fn

    def solve(bench, item, mounted, **kwargs):
        if broken['on'] and kwargs['unit'] == 's1/outcomes':
            raise KeyError('missing runtime')
        return real_solve(bench, item, mounted, **kwargs)
    services.solve_fn = solve
    state = chain.run(tmp_path, 'G', services=services)
    assert state['paused']['reason'] == 'first_cell_configuration:searchqa' and state['paused']['unit'] == 's1/outcomes'
    assert (tmp_path / 'G' / 's1' / 'outcomes' / 'failure.json').exists()
    broken['on'] = False
    units.write_json(tmp_path / 'G' / 'recovery.json', {'by': 'owner', 'date': '2026-11-10', 'decision': 'fixed'})
    state = chain.run(tmp_path, 'G', services=services, resume=True)
    assert state['complete'] and (tmp_path / 'G' / 's1' / 'outcomes' / 'done-stopped-1.json').exists()
    done = json.loads((tmp_path / 'G' / 's1' / 'outcomes' / 'done.json').read_text())
    assert done['missing_cells'] == 0 and done['stop_reason'] is None


def test_infrastructure_stop_retries_once_after_sixty_seconds(tmp_path):
    """Eight consecutive transport failures in the noise unit (a gate of ten) stop it; the one automatic retry
    re-runs the eight infrastructure-unknown cells (archived under rerun/) and the calibration ends complete."""
    failing = {'left': 8}
    naps = []

    def flaky(system, user):
        if failing['left'] > 0:
            failing['left'] -= 1
            return {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'http_502'}
        return 'The answer is 42.'
    sizes = {bench: {'learn': 2, 'gate': 10, 'panel': 2} for bench in ORDER}
    services, modules, script = build(tmp_path, order=('searchqa',), scripted={'replies': {'solver': flaky}}, sizes=sizes)
    state = chain.run(tmp_path, 'G', services=services, sleep=naps.append)
    assert state['complete'] and naps == [60] and list(state['infra_retries']) == ['s1/noise']
    noise_dir = tmp_path / 'G' / 's1' / 'noise'
    noise = json.loads((noise_dir / 'noise.json').read_text())
    # typed-v2 step 5w: R = 3 runs per gate item (30 noise cells); the 8 re-run cells are counted in the record
    assert noise['unknown_final'] == 0 and noise['n'] == 10 and noise['tau_points'] == 3.0 and noise['reruns'] == 8
    assert len(list((noise_dir / 'rerun').glob('*.json'))) == 8 and (noise_dir / 'done-stopped-1.json').exists()
    assert all(json.loads(p.read_text())['infrastructure_unknown'] for p in (noise_dir / 'rerun').glob('*.json'))
    cells = [json.loads(p.read_text()) for p in (noise_dir / 'cells').glob('*.json')]
    assert len(cells) == 30 and not any(c['infrastructure_unknown'] for c in cells)
    assert json.loads((tmp_path / 'G' / 'ledger.json').read_text())['reopened'][0]['reason'] == chain.INFRA_STOP
    # a persistent failure pauses after the one retry (20 noise cells, 8 fail, retry, 8 fail again)
    dead = lambda s, u: {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'transport'}
    other = tmp_path / 'other'
    services2, _, _ = build(other, order=('searchqa',), scripted={'replies': {'solver': dead}}, sizes=sizes)
    naps2 = []
    state2 = chain.run(other, 'G', services=services2, sleep=naps2.append)
    assert state2['paused'] == {**state2['paused'], 'reason': chain.INFRA_STOP, 'unit': 's1/noise'} and naps2 == [60]
    assert list(state2['infra_retries']) == ['s1/noise'] and (other / 'G' / 's1' / 'noise' / 'done-stopped-1.json').exists()


def test_noise_with_too_few_known_pairs_pauses_and_recovers_by_rerunning_unknown_cells(tmp_path):
    """Every other send fails (no streak of eight): every noise pair has an unknown side, the calibration would
    rest on the bare floor; typed-v2 step 5w (DESIGN 3.4 "Cells"): any infrastructure unknown left in a gate arm
    makes it undecidable, so the chain pauses 'gate_cells_unknown' (was 'noise_uncalibrated'); the owner's recovery re-runs the
    infrastructure-unknown cells and the step continues."""
    counter = {'n': 0, 'healthy': False}

    def alternating(system, user):
        counter['n'] += 1
        if not counter['healthy'] and counter['n'] % 2 == 0:
            return {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'transport'}
        return 'The answer is 42.'
    sizes = {bench: {'learn': 2, 'gate': 6, 'panel': 2} for bench in ORDER}
    services, modules, script = build(tmp_path, order=('searchqa',), scripted={'replies': {'solver': alternating}}, sizes=sizes)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'gate_cells_unknown' and state['paused']['unit'] == 's1/noise'
    noise_dir = tmp_path / 'G' / 's1' / 'noise'
    assert not (noise_dir / 'noise.json').exists() and (noise_dir / 'done-stopped-1.json').exists() and not (noise_dir / 'done.json').exists()
    unknown = sum(json.loads(p.read_text())['infrastructure_unknown'] for p in (noise_dir / 'cells').glob('*.json'))
    assert unknown == 9 and state['infra_retries'] == {}  # 18 noise cells (R = 3), every other send failed
    counter['healthy'] = True
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    noise = json.loads((noise_dir / 'noise.json').read_text())
    assert noise['n'] == 6 and noise['unknown_final'] == 0 and len(list((noise_dir / 'rerun').glob('*.json'))) == 9
    assert noise['reruns'] == 9 and noise['cells'] == 18


def test_route_b_stop_on_a_later_cell_pauses_with_its_kind_and_resumes(tmp_path):
    """A sandbox outage on the second gate item of s1/outcomes (not the bench's first cell) stops the unit with
    the route-B kind 'sandbox' and pauses the chain; nothing is silently dropped from the gate's denominator."""
    from skillopt.execskill.errors import SandboxUnavailable
    broken = {'on': True}
    services, modules, script = build(tmp_path, order=('searchqa',))
    real_solve = services.solve_fn

    def solve(bench, item, mounted, **kwargs):
        # typed-v2 step 5w: s1/outcomes runs learn cells only (its gate arm F is B@noise's): the second learn item
        if broken['on'] and kwargs['unit'] == 's1/outcomes' and item['task_id'] == 'searchqa-l1':
            raise SandboxUnavailable('docker down')
        return real_solve(bench, item, mounted, **kwargs)
    services.solve_fn = solve
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'sandbox' and state['paused']['unit'] == 's1/outcomes'
    unit = tmp_path / 'G' / 's1' / 'outcomes'
    stop = json.loads((unit / 'stop.json').read_text())
    assert stop == {**stop, 'reason': 'sandbox', 'failure': 'SandboxUnavailable', 'bench': 'searchqa'}
    done = json.loads((unit / 'done.json').read_text())
    assert done['stop_reason'] == 'sandbox' and done['missing_cells'] >= 1 and not (unit / 'unsubmitted').exists()
    assert json.loads((tmp_path / 'G' / 'ledger.json').read_text())['stop_reason'] == 'sandbox'
    assert not (tmp_path / 'G' / 's1' / 'decisions.json').exists()
    broken['on'] = False
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'] and json.loads((unit / 'done.json').read_text())['missing_cells'] == 0
    d1 = json.loads((tmp_path / 'G' / 's1' / 'decisions.json').read_text())
    assert d1['outcomes']['learn'] == {'items': 2, 'cells': 2, 'pass': 0, 'fail': 2, 'unknown': 0}
    assert d1['outcomes']['gate'] == {'items': 3, 'cells': 9, 'repeats': 3, 'pass': 0, 'fail': 9, 'unknown': 0,
                                      'source': {'unit': 's1/noise', 'arm': 'B'}}


def test_cell_raising_outside_the_shell_on_a_later_cell_pauses_as_incomplete(tmp_path):
    """A non-stop exception on a later cell leaves no record (unsubmitted); the unit is not complete and the chain
    pauses instead of deciding on a reduced slice; the recovery completes the unit without redoing finished cells."""
    broken = {'on': True}
    services, modules, script = build(tmp_path, order=('searchqa',))
    real_solve = services.solve_fn

    def solve(bench, item, mounted, **kwargs):
        if broken['on'] and kwargs['unit'] == 's1/outcomes' and item['task_id'] == 'searchqa-l1':  # step 5w: learn
            raise KeyError('missing runtime')
        return real_solve(bench, item, mounted, **kwargs)
    services.solve_fn = solve
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'incomplete_unit:missing_cells' and state['paused']['unit'] == 's1/outcomes'
    unit = tmp_path / 'G' / 's1' / 'outcomes'
    assert len(list((unit / 'unsubmitted').glob('*.json'))) == 1 and json.loads((unit / 'done.json').read_text())['missing_cells'] == 1
    before = len([c for c in script.calls if c[1] == 's1/outcomes'])
    broken['on'] = False
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'] and len([c for c in script.calls if c[1] == 's1/outcomes']) == before + 1
    outcomes = json.loads((tmp_path / 'G' / 's1' / 'decisions.json').read_text())['outcomes']
    assert outcomes['learn']['cells'] == 2 and outcomes['gate']['cells'] == 9


def test_incomplete_read_pauses_and_a_pure_infrastructure_read_stop_retries_once(tmp_path):
    reads = FakeReads()
    reads.missing[('C0', 'officeqa')] = 1
    services, modules, script = build(tmp_path, order=('searchqa', 'officeqa'), reads=reads)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'incomplete_read:missing_cells' and state['paused']['unit'] == 'read-C0-officeqa'
    assert not any(u.startswith('read-') for u in state['done_units']) and state['reads']['C0']['officeqa']['missing_cells'] == 1
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'] and [e for e, b, *_ in reads.calls[:4]] == ['C0', 'C0', 'C0', 'C0']  # both re-read, then on
    # a pure infrastructure stop in one read of an event: sixty seconds, the ledger reopened, only that read redone
    other = tmp_path / 'other'
    flaky = FakeReads()
    seen = {'n': 0}

    def statuses(event, bench, n):
        if event == 'C0' and bench == 'searchqa' and seen['n'] == 0:
            seen['n'] += 1
            services2.ledger.stop(chain.INFRA_STOP)
            return {'event': event, 'bench': bench, 'cells': 1, 'expected_cells': n, 'missing_cells': n - 1,
                    'status': 'incomplete', 'tokens': 7, 'stop_reason': chain.INFRA_STOP}
        return None
    flaky.statuses = statuses
    naps = []
    services2, _, _ = build(other, order=('searchqa', 'officeqa'), reads=flaky)
    state2 = chain.run(other, 'G', services=services2, sleep=naps.append)
    assert state2['complete'] and naps == [60] and state2['infra_retries']['read-C0']['benches'] == ['searchqa']
    assert [(e, b) for e, b, *_ in flaky.calls[:3]] == [('C0', 'searchqa'), ('C0', 'officeqa'), ('C0', 'searchqa')]
    assert json.loads((other / 'G' / 'ledger.json').read_text())['reopened'][0]['reason'] == chain.INFRA_STOP


def test_unit_drain_is_recorded_and_a_failed_drain_pauses_with_its_stop_kind(tmp_path):
    from skillopt.execskill.errors import CleanupUnconfirmed
    drained = []
    services, modules, script = build(tmp_path, order=('searchqa',))
    services.drain = lambda unit: drained.append(unit) or {'cleanups': [], 'starts': [], 'unit': unit}
    services.worker_options = {'cleanup_grace_seconds': 120, 'ready_timeout_seconds': 90}
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'] and state['worker_options'] == {'cleanup_grace_seconds': 120, 'ready_timeout_seconds': 90}
    assert drained == ['s1/noise', 's1/outcomes', 's1/card-r1', 's1/outcomes-card']  # every cell unit (no proposal here)
    record = json.loads((tmp_path / 'G' / 's1' / 'outcomes' / 'drain.json').read_text())
    assert record['result']['unit'] == 's1/outcomes' and record['error'] is None
    other = tmp_path / 'other'
    services2, _, _ = build(other, order=('searchqa',))
    services2.drain = lambda unit: (_ for _ in ()).throw(CleanupUnconfirmed('containers remain'))
    state2 = chain.run(other, 'G', services=services2, sleep=lambda s: None)
    assert state2['paused']['reason'] == 'cleanup' and state2['paused']['unit'] == 's1/noise'
    assert json.loads((other / 'G' / 's1' / 'noise' / 'drain.json').read_text())['error'] == 'CleanupUnconfirmed'


def test_exception_in_one_read_unit_stops_the_ledger_so_the_event_winds_down(tmp_path):
    reads = FakeReads()
    broken = {'on': True}

    def statuses(event, bench, n):
        if broken['on'] and bench == 'officeqa':
            raise ValueError('consent refused')
        return None
    reads.statuses = statuses
    services, modules, script = build(tmp_path, order=('searchqa', 'officeqa'), reads=reads)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'exception:ValueError' and state['paused']['detail'] == 'ValueError'
    assert json.loads((tmp_path / 'G' / 'ledger.json').read_text())['stop_reason'] == 'read_unit_exception:ValueError'
    broken['on'] = False
    recovery(tmp_path)
    assert chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)['complete']


def test_token_cap_inside_a_role_call_pauses_with_the_ledger_reason(tmp_path):
    """The card writer's reservation (4 x (bytes + 512 + 32,768)) exceeds a 100,000-token cap after the cheap cells
    (4 x (bytes + 512 + 4,096) each): the pause names 'token_cap' at the writer's unit, not 'exception:Stop'."""
    services, modules, script = build(tmp_path, order=('searchqa',), cap=100_000)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'token_cap' and state['paused']['unit'] == 's1/card-r1'
    assert state['paused']['detail'] == 'Stop' and json.loads((tmp_path / 'G' / 'ledger.json').read_text())['stop_reason'] == 'token_cap'
    assert 's1/outcomes' in state['done_units'] and 's1/card-r1' not in state['done_units']


def test_second_program_candidate_is_gated_against_the_same_current_arm(tmp_path):
    """Two proposals in one step: only the first changes any outcome. The second must be gated with the mount the
    step started from (without candidate 1), so it gains nothing and is rejected."""
    def outcome(bench, item_id, mounted):
        return 'pass' if any(p['id'] == 'p-sq-1' for p in mounted.get('enabled') or []) else 'fail'
    services, modules, script = build(tmp_path, order=('searchqa',), proposals={'searchqa': ['p-sq-1', 'p-sq-2']},
                                      scripted={'outcomes': outcome})
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    d1 = json.loads((tmp_path / 'G' / 's1' / 'decisions.json').read_text())
    first, second = d1['programs']
    assert first['accepted'] and first['procedure_id'] == 'p-sq-1' and abs(first['gain_points_fired'] - 100.0) < 1e-9
    # typed-v2 step 5w: the reason names of DESIGN 3.4 (typed-v1 'fired_gain_below_tau')
    assert not second['accepted'] and second['reason'] == 'gain_below_tau' and second['gain_points_fired'] == 0.0
    assert first['mount_snapshot']['library'] == second['mount_snapshot']['library'] == []
    gate_cells = [json.loads(p.read_text()) for p in (tmp_path / 'G' / 's1' / 'program-2-gate' / 'cells').glob('*.json')]
    assert all(c['mount']['programs_offered'] == [] and c['mount']['programs_enabled'] == [] for c in gate_cells)
    lib = library_.Library.load(tmp_path / 'G' / 's1' / 'library.json')
    assert [s['skill_id'] for s in lib.skills] == ['prog-t01-s1-a']  # candidate 1 alone, with its own id


def test_describer_infrastructure_failure_retries_then_pauses_and_never_rejects(tmp_path):
    """A transport failure of the describer is no verdict on a gate-accepted program: one retry after 60 s, then a
    pause; after the recovery the program is described and enters the library."""
    down = {'on': True}
    dead = {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'transport'}
    describer = lambda system, user: dead if down['on'] else smoke.DEFAULT_DESCRIPTION
    writers = FakeWriters(proposals={'searchqa': ['p-1']}, card_text=lambda bench, r: None)
    naps = []
    services, modules, script = build(tmp_path, order=('searchqa',), writers=writers, scripted={'replies': {'describer': describer}})
    # the fake describer wraps the real writers.describe so that the infrastructure classification is exercised
    from skillopt.execskill.typed import writers as real_writers
    services.describe = real_writers.describe
    state = chain.run(tmp_path, 'G', services=services, sleep=naps.append)
    assert state['paused']['reason'] == 'describer_unavailable' and state['paused']['unit'] == 's1/program-1' and naps == [60]
    assert list(state['infra_retries']) == ['s1/program-1/describe-prog-t01-s1-a']
    assert not (tmp_path / 'G' / 's1' / 'program-1' / 'decision.json').exists()
    down['on'] = False
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=naps.append)
    assert state['complete'] and naps == [60]
    d1 = json.loads((tmp_path / 'G' / 's1' / 'decisions.json').read_text())
    assert d1['programs'][0]['accepted'] and d1['programs'][0]['reason'] == 'accepted'
    assert library_.Library.load(tmp_path / 'G' / 's1' / 'library.json').get('prog-t01-s1-a')['description'].startswith('Scripted')
    # a parsed-but-invalid description after the retry stays a description failure (no pause)
    other = tmp_path / 'other'
    services2, _, _ = build(other, order=('searchqa',), writers=FakeWriters(proposals={'searchqa': ['p-1']}, card_text=lambda b, r: None),
                            scripted={'replies': {'describer': 'not json'}})
    services2.describe = real_writers.describe
    state2 = chain.run(other, 'G', services=services2, sleep=lambda s: None)
    assert state2['complete'] and json.loads((other / 'G' / 's1' / 'decisions.json').read_text())['programs'][0]['reason'] == 'description_failed'


def test_no_harm_rejection_opens_a_second_type_and_a_revised_card_can_be_accepted(tmp_path):
    """searchqa's card (accepted at step 1) harms officeqa items: officeqa opens t02 instead of joining t01. Its
    round-1 card fails and the revised round-2 card passes (cards are told apart by their round)."""
    def outcome(bench, item_id, mounted):
        card = mounted.get('card_text') or ''
        if bench == 'searchqa':
            return 'pass' if card else 'fail'
        if 'round 2' in card:
            return 'pass'
        if card:
            return 'fail'  # officeqa: any other card (searchqa's, its own round 1) breaks every item
        return 'pass' if int(item_id[-1]) % 2 == 0 else 'fail'  # no card: even items pass
    services, modules, script = build(tmp_path, order=('searchqa', 'officeqa'), scripted={'outcomes': outcome})
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    d2 = json.loads((tmp_path / 'G' / 's2' / 'decisions.json').read_text())
    check = d2['typing']['no_harm'][0]
    assert d2['typing']['type'] == 't02' and d2['typing']['new_type'] and check['type'] == 't01' and not check['merge']
    assert check['reason'] == 'harm_beyond_tau' and abs(check['mean_points'] + 200 / 3) < 1e-9 and check['worse'] == 2
    assert [(r['round'], r['accepted']) for r in d2['cards']] == [(1, False), (2, True)]
    lib = library_.Library.load(tmp_path / 'G' / 's2' / 'library.json')
    assert lib.active_card('t02')['skill_id'] == 'card-t02-s2' and lib.active_card('t01')['skill_id'] == 'card-t01-s1'
    assert (tmp_path / 'G' / 's2' / 'card-r2' / 'skill.json').exists() and 's2/card-r1-learn' in state['done_units']
    tm = typing_.TypeMap.load(tmp_path / 'G' / 's2' / 'typemap.json')
    assert len(tm.data['types']) == 2 and tm.summary()['t02']['card'] == 'card-t02-s2'


def test_recovery_forwards_the_owner_decision_to_a_paused_sheet_qualification(tmp_path):
    """A chain paused on route B's 'qualification_paused' Pause writes the owner's decision into the paused
    qualification attempt (route B admits a new attempt only then); any other pause leaves it alone."""
    from skillopt.coevo5.cells import Pause
    attempt = tmp_path / 'shared' / 'test' / chain.SHEET_QUALIFICATION / 'attempt-2'
    attempt.mkdir(parents=True)
    (tmp_path / 'shared' / 'test' / chain.SHEET_QUALIFICATION / 'attempt-1').mkdir()
    services, modules, script = build(tmp_path, order=('searchqa',))
    state = chain._open_state(tmp_path / 'G', 'G', 'smoke', False)
    runner = chain._Run(services, state, sleep=lambda s: None)
    services.ledger = units.Ledger(tmp_path / 'G' / 'ledger.json', 10 ** 6)
    error = Pause('qualification_paused', 'attempt-2', 'spreadsheetbench-qualification')
    assert chain._pause_detail(error) == 'Pause:qualification_paused'
    runner.pause('exception:Pause', 'read-C0-spreadsheetbench', chain._pause_detail(error))
    recovery(tmp_path, decision='qualification host fixed')
    runner.recover()
    forwarded = json.loads((attempt / 'recovery.json').read_text())
    assert forwarded == {'by': 'owner', 'date': '2026-11-10', 'decision': 'qualification host fixed'}
    assert state['recoveries'][0]['qualification_attempt'] == 'attempt-2' and not (tmp_path / 'shared' / 'test' / chain.SHEET_QUALIFICATION / 'attempt-1' / 'recovery.json').exists()
    runner.pause('exception:KeyError', 's1/noise', 'KeyError')
    recovery(tmp_path)
    runner.recover()
    assert state['recoveries'][1]['qualification_attempt'] is None and len(list(attempt.glob('*.json'))) == 1


def test_stopped_read_pauses_the_chain(tmp_path):
    reads = FakeReads()
    reads.stop = 'token_cap'
    services, modules, script = build(tmp_path, order=('searchqa',), reads=reads)
    state = chain.run(tmp_path, 'G', services=services)
    assert state['paused']['reason'] == 'token_cap' and state['paused']['unit'].startswith('read-C0-')
    assert not any(u.startswith('read-') for u in state['done_units'])


def test_chain_d_first_call_needs_no_reasoning(tmp_path):
    services, modules, script = build(tmp_path, 'D', order=('searchqa',))
    state = chain.run(tmp_path, 'D', services=services)
    assert state['complete']
    confirm = json.loads((tmp_path / 'D' / 'confirm.json').read_text())
    assert confirm['checks'] == {'reply': True, 'model': True, 'settled': True, 'reasoning': True}
    thinking = tmp_path / 'thinking'
    reasoning = lambda s, u: {**smoke.receipt('ready', model='deepseek-v4-flash'), 'reasoning_chars': 12}
    services2, _, _ = build(thinking, 'D', order=('searchqa',), scripted={'replies': {'first_call': reasoning}})
    assert chain.run(thinking, 'D', services=services2)['paused']['reason'] == 'first_call_unconfirmed'


def test_smoke_run_uses_its_own_root_limits_and_held_out_panel(tmp_path):
    manifest = smoke.synthetic_manifest()
    modules = SimpleNamespace(mount=FakeMount, writers=FakeWriters(proposals={b: ['p-%s' % b, 'p2-%s' % b] for b in ORDER}),
                              reads=FakeReads())
    services = smoke.fake_services(tmp_path / 'run', 'G', manifest, scripted={'outcomes': scripted_outcome}, modules=modules)
    state = smoke.run(tmp_path / 'run', 'G', services=services)
    assert state['complete'] and state['mode'] == 'smoke' and (tmp_path / 'run-smoke' / 'G' / 'state.json').exists()
    assert not (tmp_path / 'run').exists()
    assert services.limits == smoke.SMOKE_LIMITS and services.slices['searchqa'] == {
        'learn': ['searchqa-l0', 'searchqa-l1'], 'gate': ['searchqa-g0', 'searchqa-g1', 'searchqa-g2'],
        'panel': ['searchqa-p0', 'searchqa-p1']}
    panel = smoke.practice_panel(services)('alfworld', 'x')
    assert [t['task_id'] for t in panel] == ['alfworld-p0', 'alfworld-p1'] and len(modules.reads.calls) == 35
    assert not hasattr(chain.Services, 'panel_tasks')  # the consent gate inside reads.read_panel is the only panel path
    done = state['done_units']
    assert 's1/card-r2' not in done and 's1/program-2-smoke' not in done and 's1/program-1-gate' in done
    for bench in ORDER:  # every unit type ran on every bench (one proposal each, one card round each)
        k = ORDER.index(bench) + 1
        assert 's%d/program-1-smoke' % k in done and 's%d/card-r1' % k in done
    d4 = json.loads((tmp_path / 'run-smoke' / 'G' / 's4' / 'decisions.json').read_text())
    assert d4['typing']['signature'] == 'workbook_preview' and d4['evidence'] == 'typed_v3_smoke'
    assert modules.writers.propose_calls[0]['evidence'] == 'smoke'


def test_fake_smoke_through_the_real_mount_writers_and_reads(tmp_path):
    """``smoke --fake`` as the CLI runs it: no injected modules, the synthetic manifest, scripted replies through the
    real mount (type assignment, system card, selection call), writers (prompts, screens, reader, policy) and reads
    (practice-read units, sealed aggregate, open mirror)."""
    state = smoke.run(tmp_path / 'run', 'G', fake=True, sleep=lambda s: None)
    assert state['complete'] and state['paused'] is None, state['paused']
    chain_dir = tmp_path / 'run-smoke' / 'G'
    lib = library_.Library.load(chain_dir / 's5' / 'library.json')
    # a program is judged against the card-mounted arm: searchqa's and spreadsheetbench's scripted helpers gain
    # nothing over their accepted cards (every gate item already passes) and are rejected; officeqa's, zebralogic's
    # and alfworld's lift an item each
    assert [s['skill_id'] for s in lib.skills] == ['card-t01-s1', 'prog-t01-s2-a', 'card-t02-s3', 'prog-t02-s3-a',
                                                   'card-t03-s4', 'card-t04-s5', 'prog-t04-s5-a']
    assert all(s['description'] and s['name'] for s in lib.skills)
    tm = typing_.TypeMap.load(chain_dir / 's5' / 'typemap.json')
    assert len(tm.data['types']) == 4 and len(tm.data['types']['t01']['sources']) == 2  # officeqa joined searchqa's type
    d1 = json.loads((chain_dir / 's1' / 'decisions.json').read_text())
    # typed-v2 (step 4c): searchqa's programs unit takes the scripted promotion path (DESIGN 3.2, 3.3): an unreadable
    # proposal, the one format retry, proposal 1 refused by the screen and by its one fix (a zero-call decision: no
    # unit), proposal 2 promoted to slot 1 as p-searchqa-1-2 (typed-v1: one proposal, p-searchqa-1-1)
    dropped, promoted = d1['programs']
    assert d1['cards'][0]['accepted'] and promoted['procedure_id'] == 'p-searchqa-1-2'
    assert not promoted['accepted'] and promoted['reason'] == 'gain_below_tau'  # step 5w: DESIGN 3.4 reason name
    assert (promoted['proposal'], promoted['status'], promoted['candidate'], promoted['unit']) == (2, 'passed', 1, 's1/program-1')
    assert (dropped['proposal'], dropped['status'], dropped['candidate'], dropped['unit'], dropped['accepted']) == (
        1, 'dropped_screen', None, None, False)
    assert dropped['reason'].startswith('screen:policy: ') and '"import"' in dropped['reason'] and '| fix: policy: ' in dropped['reason']
    rows = json.loads((chain_dir / 's1' / 'programs' / 'proposals.json').read_text())
    assert [(r['n'], r['status'], r['slot']) for r in rows] == [(1, 'dropped_screen', None), (2, 'passed', 1)]
    assert all(r['format_retry']['readable'] for r in rows) and rows[0]['fix']['reason'].startswith('policy: ')
    sends = json.loads((chain_dir / 's1' / 'programs' / 'calls' / 'writer-program_writer.json').read_text())
    assert [json.loads(s['user'])['request'] for s in sends] == ['propose', 'format_retry', 'fix']
    from skillopt.execskill.typed import writers as real_writers
    retry_call = real_writers.request_sha256(sends[1]['system'], sends[1]['user'])
    assert rows[1]['request_sha256'] == retry_call == rows[1]['procedure']['lineage']['engineer_call']
    assert sorted(p.name for p in (chain_dir / 's1').iterdir() if p.name.startswith('program')) == [
        'program-1', 'program-1-gate', 'program-1-smoke', 'programs']
    for k, bench in enumerate(ORDER[1:], 2):  # one clean proposal elsewhere; ALFWorld's uses its own note hook
        rows = json.loads((chain_dir / ('s%d' % k) / 'programs' / 'proposals.json').read_text())
        assert [(r['n'], r['status'], r['slot']) for r in rows] == [(1, 'passed', 1)], bench
        assert rows[0]['procedure']['hooks'] == (['alf_before_step'] if bench == 'alfworld' else ['applies', 'before_call'])
    # step 5w: the card-mounted gate runs are the accepted round's (DESIGN 3.4 case (e)): 3 items x 3 runs, all pass
    assert d1['program_gate_current'] == 's1/outcomes-card' and d1['outcomes_with_card']['gate']['pass'] == 9
    assert d1['outcomes_with_card']['gate']['source'] == {'unit': 's1/card-r1', 'arm': 'cand_card'}
    assert d1['programs'][1]['baseline_selected'] is True  # addendum O5: the program baseline is the accepted runs
    d2 = json.loads((chain_dir / 's2' / 'decisions.json').read_text())
    assert not d2['cards'][0]['accepted'] and d2['program_gate_current'] == 's2/outcomes' and d2['programs'][0]['accepted']
    assert json.loads((chain_dir / 's2' / 'typing' / 'typing.json').read_text())['no_harm'][0]['merge']
    reads = [p.name for p in chain_dir.iterdir() if p.name.startswith('practice-read-')]
    assert len(reads) == 35 and not any('test' in p.name.lower() for p in chain_dir.rglob('*'))
    mirrors = sorted((chain_dir / 'read-status').glob('*.json'))
    status = json.loads(mirrors[0].read_text())
    assert len(mirrors) == 35 and status['status'] == 'complete' and not {'correct', 'incorrect', 'items_ids'} & set(status)
    assert (chain_dir / 'practice-read-S1-searchqa' / 'aggregate.json').exists()  # sealed inside the unit
    ledger = json.loads((chain_dir / 'ledger.json').read_text())
    assert ledger['pending'] == {} and ledger['stopped'] is False and ledger['sends'] == state['ledger']['sends']


def test_learning_cells_with_a_selection_call_feed_the_writers_the_solver_request(tmp_path):
    """Once t01 holds a program (accepted at step 1 on searchqa), every step-2 officeqa learning cell makes a
    selection call first; the real card writer and engineer must still see the SOLVER request of those cells,
    never the selection payload (skill index + task)."""
    def outcome(bench, item_id, mounted):
        return 'pass' if mounted.get('enabled') else 'fail'
    manifest = smoke.synthetic_manifest()
    services = smoke.fake_services(tmp_path / 'run', 'G', manifest, scripted={'outcomes': outcome})
    services.order = ('searchqa', 'officeqa')
    state = smoke.run(tmp_path / 'run', 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    chain_dir = tmp_path / 'run-smoke' / 'G'
    d1 = json.loads((chain_dir / 's1' / 'decisions.json').read_text())
    # typed-v2 (step 4c): the scripted searchqa unit drops proposal 1 (zero-call decision) and promotes proposal 2
    assert [(p['status'], p['candidate']) for p in d1['programs']] == [('dropped_screen', None), ('passed', 1)]
    assert not d1['cards'][0]['accepted'] and d1['programs'][1]['accepted']
    assert json.loads((chain_dir / 's2' / 'typing' / 'typing.json').read_text())['type'] == 't01'
    cells = [json.loads(p.read_text()) for p in (chain_dir / 's2' / 'outcomes' / 'cells').glob('*.json')]
    assert cells and all(len(c['selection_sends']) == 1 and c['selection_sends'][0]['system'] == library_.SELECTION_SYSTEM
                         and len(c['sends']) == 1 and c['sends'][0]['user'].startswith('{"question"') for c in cells)
    assert all(c['tokens'] == c['solver_tokens'] + c['selection_tokens'] and c['selection_tokens'] > 0 for c in cells)
    writer = json.loads((chain_dir / 's2' / 'card-r1' / 'calls' / 'writer-card_writer.json').read_text())
    shown = json.loads(writer[0]['user'])['examples']
    assert shown and all(e['view'].startswith('{"question"') and '"skills"' not in e['view'] for e in shown)
    engineer = json.loads((chain_dir / 's2' / 'programs' / 'calls' / 'writer-program_writer.json').read_text())
    trajectories = json.loads(engineer[0]['user'])['trajectories']
    assert trajectories and all('question' in json.loads(t['calls'][0]['user']) and 'skills' not in json.loads(t['calls'][0]['user'])
                                for t in trajectories)
    index = json.loads(engineer[0]['user'])['skill_index']
    assert [row['name'] for row in index] == ['evidence-qa-program-s1-a'] and index[0]['home_type'] == 't01'


def test_smoke_default_script_and_hash_embedder():
    manifest = smoke.synthetic_manifest()
    items = smoke.synthetic_items(manifest)
    assert [len(items[b]) for b in ORDER] == [7] * 5
    for bench in ORDER:
        texts = [typing_.public_text(smoke.synthetic_view(bench, item)) for item in items[bench]]
        tm = typing_.TypeMap()
        sid = tm.add_source({'path': bench}, typing_.structural_signature(smoke.synthetic_view(bench, items[bench][0])),
                            smoke.hash_embedder(texts), step=1)
        tm.new_type(sid, step=1)
        vectors = typing_.embed_texts(texts, embedder=smoke.hash_embedder)
        assert tm.assign(tm.data['sources'][sid]['signature'], vectors[-1])['type'] == 't01'
    script = smoke.Script()
    assert script.reply('selection', library_.SELECTION_SYSTEM, json.dumps({'task': 't', 'skills': [{'name': 'a-b', 'description': 'd'}]})) == \
        json.dumps({'use': ['a-b'], 'why': 'scripted: the first listed skill'})
    assert library_.parse_description(script.reply('describer', '', ''))
    assert smoke.solver_purpose(library_.SELECTION_SYSTEM) == 'selection' and smoke.solver_purpose('x') == 'solver'
    assert smoke.smoke_root('/tmp/typed2-neutral/r').name == 'r-smoke' and smoke.smoke_root('/tmp/typed2-neutral/r-smoke').name == 'r-smoke'
    with pytest.raises(ValueError):
        smoke.smoke_slices(items, {'searchqa': {'learn': ['a'], 'gate': ['a', 'b', 'c']}})


def test_card_describer_failure_installs_the_card_with_the_fallback_description(tmp_path):
    """A gate-accepted card is installed even when its describer reply never parses: it gets the frozen fallback
    description (public structure only) and says so; its origin names the writer attempt that produced it (Codex
    review 11/10, findings 5 and 7)."""
    services, modules, script = build(tmp_path, order=('searchqa',), scripted={'replies': {'describer': 'not json'}})
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    d1 = json.loads((tmp_path / 'G' / 's1' / 'decisions.json').read_text())
    assert d1['cards'][0]['accepted'] and len(d1['cards'][0]['request_sha256']) == 64
    card = library_.Library.load(tmp_path / 'G' / 's1' / 'library.json').active_card('t01')
    assert card['description'] == chain.CARD_FALLBACK_DESCRIPTION % 'question/context'
    assert card['origin']['description_source'] == 'fallback_after_describer_failure'
    assert card['origin']['writer_call_sha256'] == d1['cards'][0]['request_sha256']
    assert '- card for' not in card['description']  # never the card body


def test_card_chars_are_content_characters_in_the_attempt_the_decision_and_the_skill(tmp_path):
    """DESIGN 3.1: the stored card keeps the final newline that the real writer's ``texts.instruction_text`` appends,
    and ``chars`` never counts it: the writer's attempt row, the card decision (also in decisions.json) and the
    accepted card's skill record (its origin's decision) all hold ``len(text) - 1``; the same with the fake writer."""
    services = smoke.fake_services(tmp_path / 'run', 'G', smoke.synthetic_manifest())
    services.order = ('searchqa',)
    state = smoke.run(tmp_path / 'run', 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    chain_dir = tmp_path / 'run-smoke' / 'G'
    unit = chain_dir / 's1' / 'card-r1'
    written, decision = units.read_json(unit / 'writer.json'), units.read_json(unit / 'decision.json')
    skill = units.read_json(unit / 'skill.json')['skill']
    text = skill['body']['text']
    assert decision['accepted'] and text == smoke.DEFAULT_CARD + '\n' and written['card_limits'] == cards.LIMITS_RECORD
    assert [(a['violation'], a['chars'], a['bullets']) for a in written['attempts']] == [(None, len(text) - 1, 3)]
    assert decision['attempts'] == written['attempts'] and decision['chars'] == len(text) - 1
    assert skill['origin']['decision']['chars'] == len(text) - 1
    assert json.loads((chain_dir / 's1' / 'decisions.json').read_text())['cards'][0]['chars'] == len(text) - 1
    stored = library_.Library.load(chain_dir / 's1' / 'library.json').active_card('t01')
    assert stored['body']['text'] == text and stored['origin']['decision']['chars'] == len(text) - 1
    # the fake writer of this file, with a card that ends in its newline as a real one does
    card_text = '- read every snippet\n- prefer the entity that several snippets support\n'
    services, modules, script = build(tmp_path / 'fake', order=('searchqa',),
                                      writers=FakeWriters(card_text=lambda bench, r: card_text))
    assert chain.run(tmp_path / 'fake', 'G', services=services, sleep=lambda s: None)['complete']
    row = json.loads((tmp_path / 'fake' / 'G' / 's1' / 'decisions.json').read_text())['cards'][0]
    assert row['accepted'] and row['chars'] == len(card_text) - 1
    assert [(a['chars'], a['bullets']) for a in row['attempts']] == [(len(card_text) - 1, 2)]
    fake_card = library_.Library.load(tmp_path / 'fake' / 'G' / 's1' / 'library.json').active_card('t01')
    assert fake_card['origin']['decision']['chars'] == len(card_text) - 1


def test_recovery_consumed_but_not_applied_is_applied_by_the_next_resume(tmp_path):
    """The owner's record is consumed by one atomic rename; a crash before its application leaves a consumed record
    without ``recovery-applied-<n>.json``, which the next resume applies (Codex review 11/10, finding 8)."""
    usage = {'prompt_tokens': 100, 'completion_tokens': 4000, 'total_tokens': 4100}
    big = lambda system, user: {**smoke.receipt('x', model='glm-5.3'), 'usage': usage}
    services, modules, script = build(tmp_path, order=('searchqa',), cap=60_000, scripted={'replies': {'solver': big}})
    state = chain.run(tmp_path, 'G', services=services)
    assert state['paused']['reason'] == 'token_cap'
    recovery(tmp_path)
    # the crash window: the record was renamed (consumed) but never applied
    (tmp_path / 'G' / 'recovery.json').rename(tmp_path / 'G' / 'recovery-consumed-1.json')
    state = chain.run(tmp_path, 'G', services=services, resume=True)
    assert [r['n'] for r in state['recoveries']] == [1] and (tmp_path / 'G' / 'recovery-applied-1.json').exists()
    with pytest.raises(ValueError):
        chain.run(tmp_path, 'G', services=services, resume=True)  # applied: nothing left to consume
    # an unapplied consumed record and a new owner record at once: the owner keeps one of them
    (tmp_path / 'G' / 'recovery-applied-1.json').unlink()
    recovery(tmp_path)
    with pytest.raises(ValueError):
        chain.run(tmp_path, 'G', services=services, resume=True)


def test_replayed_recovery_forwards_only_to_the_bound_qualification_attempt(tmp_path):
    """Second review 11/10: recovery n is bound to its qualification attempt before it is consumed; a crash after the
    forwarding and a new failed attempt from the other chain must not let the replay approve that new attempt."""
    from skillopt.coevo5.cells import Pause
    base = tmp_path / 'shared' / 'test' / chain.SHEET_QUALIFICATION
    (base / 'attempt-1').mkdir(parents=True)
    services, modules, script = build(tmp_path, order=('searchqa',))
    state = chain._open_state(tmp_path / 'G', 'G', 'smoke', False)
    runner = chain._Run(services, state, sleep=lambda s: None)
    services.ledger = units.Ledger(tmp_path / 'G' / 'ledger.json', 10 ** 6)
    runner.pause('exception:Pause', 'read-C0-spreadsheetbench',
                 chain._pause_detail(Pause('qualification_paused', 'attempt-1', chain.SHEET_QUALIFICATION)))
    recovery(tmp_path, decision='host fixed')
    # the crash window: bound, consumed and forwarded, but never applied
    runner.bind_qualification_target(1)
    (tmp_path / 'G' / 'recovery.json').rename(tmp_path / 'G' / 'recovery-consumed-1.json')
    assert runner.forward_qualification_recovery(units.read_json(tmp_path / 'G' / 'recovery-consumed-1.json'),
                                                 runner.qualification_target(1)) == 'attempt-1'
    (base / 'attempt-2').mkdir()  # the other chain's next attempt failed in the meantime
    runner.recover()  # the replay
    assert (base / 'attempt-1' / 'recovery.json').exists() and not (base / 'attempt-2' / 'recovery.json').exists()
    assert state['recoveries'][-1]['qualification_attempt'] == 'attempt-1'
    assert (tmp_path / 'G' / 'recovery-applied-1.json').exists()


# ---- typed-v2 promotion inside the programs unit (DESIGN 3.2, 3.3; spec/engineer.md changes 11 to 13; step 4c) ----
def cells_in(unit_dir):
    return [json.loads(p.read_text()) for p in sorted((Path(unit_dir) / 'cells').glob('*.json'))]


def program_dirs(step_dir):
    return sorted(p.name for p in Path(step_dir).iterdir() if p.name.startswith('program'))


def fired_anywhere(chain_dir):
    """Every procedure id that fired in any cell of any unit of the chain."""
    return {pid for path in Path(chain_dir).rglob('cells/*.json') for pid in json.loads(path.read_text()).get('fired') or []}


def writer_requests(unit_dir):
    sends = json.loads((Path(unit_dir) / 'calls' / 'writer-program_writer.json').read_text())
    return sends, [json.loads(send['user'])['request'] for send in sends]


def refused(i):
    """A distinct proposal that the static screen refuses ([import]), and its entry."""
    entry = {**smoke.REFUSED_ENTRY, 'description': 'Refused helper %d: it reads the process environment.' % i}
    return entry, 'import %s\n\n\n' % ('os', 'sys', 'subprocess')[i - 1] + smoke.HELPER_SOURCE


def clean(i):
    entry = {**smoke.HELPER_ENTRY, 'description': 'Clean helper %d: a caution before the answer.' % i}
    return entry, smoke.HELPER_SOURCE.replace('Read the whole task', 'Read the whole task (helper %d)' % i)


def real_writer_services(root, program_writer, *, order=('searchqa',), limits=None, scripted=None):
    """The REAL mount, writers and reads through ``smoke.fake_services`` on the synthetic manifest (learn 2, gate 3,
    panel 2), ``chain.DEFAULT_LIMITS`` unless ``limits``, with a scripted program writer."""
    services = smoke.fake_services(root, 'G', smoke.synthetic_manifest(),
                                   scripted={**(scripted or {}), 'replies': {'program_writer': program_writer}})
    services.order = order
    if limits is not None:
        services.limits = dict(limits)
    return services


def test_slot_rows_run_units_other_rows_get_zero_call_decisions(tmp_path):
    """The chain iterates over ALL rows of proposals.json: a dropped, unreadable, kind_not_new or no_reply row gets a
    zero-call decision row (candidate and unit null, no unit directory, never a cell); a third row promoted after two
    unpromoted ones runs program-1-smoke / -gate; a not_needed row stays in proposals.json; a step without a slot
    explains every proposal and runs no program unit. ``base`` names the proposal and its status."""
    proposals = {'searchqa': [('dropped_screen', 'p-drop'), ('unreadable', None), 'p-third'],
                 'officeqa': ['p-o1', 'p-o2', 'p-o3'],
                 'zebralogic': [('kind_not_new', None), ('dropped_screen', 'p-z')],
                 'spreadsheetbench': [('no_reply', None)]}
    order = ('searchqa', 'officeqa', 'zebralogic', 'spreadsheetbench')
    services, modules, script = build(tmp_path, order=order, proposals=proposals)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    chain_dir, done = tmp_path / 'G', state['done_units']
    d = {k: json.loads((chain_dir / ('s%d' % k) / 'decisions.json').read_text())['programs'] for k in (1, 2, 3, 4)}
    keys = lambda rows: [(r['proposal'], r['status'], r['candidate'], r['unit'], r['procedure_id'], r['reason']) for r in rows]
    # step 1: the dropped and the unreadable row never reach a unit; the third row is promoted to slot 1
    assert keys(d[1])[:2] == [(1, 'dropped_screen', None, None, None, 'screen:' + UNPROMOTED_REASONS['dropped_screen']),
                              (2, 'unreadable', None, None, None, 'unreadable:entry_field')]
    assert keys(d[1])[2][:5] == (3, 'passed', 1, 's1/program-1', 'p-third') and d[1][2]['smoke']['faults'] == []
    assert not any(r['accepted'] for r in d[1][:2]) and all('smoke' not in r and 'items' not in r for r in d[1][:2])
    assert all(r['request_sha256'] == d[1][2]['request_sha256'] and r['screen']['passed'] is False for r in d[1][:2])
    assert program_dirs(chain_dir / 's1') == ['program-1', 'program-1-gate', 'program-1-smoke', 'programs']
    assert {tuple(c['fired']) for u in ('program-1-smoke', 'program-1-gate') for c in cells_in(chain_dir / 's1' / u)} == {('p-third',)}
    s1 = done[done.index('s1/programs'):done.index('step-1')]
    assert [u for u in s1 if u.startswith('s1/')] == ['s1/programs', 's1/program-1-smoke', 's1/program-1-gate']
    # step 2: two slots, the third passing proposal is not needed: proposals.json only, no decision, no unit
    rows = json.loads((chain_dir / 's2' / 'programs' / 'proposals.json').read_text())
    assert [(r['n'], r['status'], r['slot']) for r in rows] == [(1, 'passed', 1), (2, 'passed', 2), (3, 'not_needed', None)]
    assert [(r['proposal'], r['candidate'], r['unit']) for r in d[2]] == [(1, 1, 's2/program-1'), (2, 2, 's2/program-2')]
    assert program_dirs(chain_dir / 's2') == ['program-1', 'program-1-gate', 'program-1-smoke', 'program-2',
                                              'program-2-gate', 'program-2-smoke', 'programs']
    # steps 3 and 4: no slot at all -- every proposal explained, no program unit ran
    assert keys(d[3]) == [(1, 'kind_not_new', None, None, None, 'kind_not_new'),
                          (2, 'dropped_screen', None, None, None, 'screen:' + UNPROMOTED_REASONS['dropped_screen'])]
    assert keys(d[4]) == [(None, 'no_reply', None, None, None, 'no_reply')]
    for k in (3, 4):
        assert program_dirs(chain_dir / ('s%d' % k)) == ['programs'] and not [u for u in done if u.startswith('s%d/program-' % k)]
    # no dropped, unreadable or not-needed proposal ever reached a cell of any unit
    assert fired_anywhere(chain_dir) == {'p-third', 'p-o1', 'p-o2'}
    assert all(r['mount_snapshot'] == d[1][2]['mount_snapshot'] for r in d[1])  # one snapshot per step


def test_unpromoted_reasons_and_the_row_checks():
    reason = chain._unpromoted_reason
    assert reason(proposal_row(1, 'dropped_screen', 'h')) == 'screen:' + UNPROMOTED_REASONS['dropped_screen']
    assert reason(proposal_row(2, 'unreadable', 'h')) == 'unreadable:entry_field'
    assert reason({'status': 'unreadable', 'screen': {'reason': 'unparseable: no_manifest: No JSON object was found.'}}) == \
        'unreadable:no_manifest'
    assert reason({'status': 'unreadable', 'screen': {'reason': 'garbled'}}) == 'unreadable:garbled'  # never raises
    assert reason(proposal_row(1, 'kind_not_new', 'h')) == 'kind_not_new' and reason(proposal_row(None, 'no_reply', 'h')) == 'no_reply'
    good = [proposal_row(1, 'dropped_screen', 'h'), proposal_row(2, 'passed', 'h', slot=1, pid='p'),
            proposal_row(3, 'not_needed', 'h', pid='q')]
    chain._check_proposal_rows(good, 1)
    chain._check_proposal_rows([], 2)
    bad = [[proposal_row(1, 'passed', 'h', slot=2, pid='p')],                                    # slot 2 without slot 1
           [proposal_row(1, 'passed', 'h', slot=1, pid='p'), proposal_row(2, 'passed', 'h', slot=2, pid='q')],  # over 1
           [{**proposal_row(1, 'dropped_screen', 'h'), 'slot': 1}],                               # a slot on a dropped row
           [{**proposal_row(1, 'passed', 'h', slot=1, pid='p'), 'procedure': None}],              # a slot without procedure
           [{**proposal_row(1, 'not_needed', 'h'), 'procedure': procedure('p')}],                 # a procedure without slot
           [{**proposal_row(1, 'passed', 'h', slot=1, pid='p'), 'status': 'over_max_candidates'}]]  # typed-v1 status
    for rows in bad:
        with pytest.raises(ValueError):
            chain._check_proposal_rows(rows, 1)


def test_a_malformed_proposal_row_pauses_before_any_program_unit(tmp_path):
    """A row the chain cannot read (here a slot beyond max_program_candidates) pauses the chain at once: no
    program-<n> unit, no decision, the proposals record kept for the owner."""
    writers = FakeWriters()
    writers.propose_programs = lambda **kw: [proposal_row(1, 'passed', 'h', slot=3, pid='p-3')]
    services, modules, script = build(tmp_path, order=('searchqa',), writers=writers)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'exception:ValueError' and state['paused']['unit'] == 's1/programs'
    assert program_dirs(tmp_path / 'G' / 's1') == ['programs'] and (tmp_path / 'G' / 's1' / 'programs' / 'proposals.json').exists()
    assert not (tmp_path / 'G' / 's1' / 'decisions.json').exists()


def test_real_writer_rows_promote_a_third_proposal_and_nothing_else_reaches_a_unit(tmp_path):
    """The real writer and reader in the chain: proposal 1 is refused by the screen and by its one fix, proposal 2 is
    unreadable (an unknown kind), proposal 3 passes and takes slot 1 as p-searchqa-1-2 (proposal 1 took ordinal 1);
    only slot 1 runs units, and the refused proposal's id never reaches a cell."""
    (e1, s1_), (e3, s3_) = refused(1), clean(3)
    unknown = {**smoke.HELPER_ENTRY, 'kind': 'bogus', 'description': 'An entry of an unknown kind.'}
    reply = ('```json\n' + json.dumps({'changes': [e1, unknown, e3]}) + '\n```'
             + ''.join('\n\n```python\n' + source + '```' for source in (s1_, s3_)))  # no block for the unknown kind

    def writer(system, user):
        return smoke.FIX_REFUSED if json.loads(user)['request'] == 'fix' else reply
    services = real_writer_services(tmp_path, writer)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    step = tmp_path / 'G' / 's1'
    rows = json.loads((step / 'programs' / 'proposals.json').read_text())
    assert [(r['n'], r['status'], r['slot']) for r in rows] == [(1, 'dropped_screen', None), (2, 'unreadable', None), (3, 'passed', 1)]
    assert rows[0]['fix']['reason'].startswith('policy: ') and rows[2]['procedure']['id'] == 'p-searchqa-1-2'
    decisions = json.loads((step / 'decisions.json').read_text())['programs']
    assert [(r['proposal'], r['status'], r['candidate'], r['unit'], r['procedure_id']) for r in decisions] == [
        (1, 'dropped_screen', None, None, None), (2, 'unreadable', None, None, None), (3, 'passed', 1, 's1/program-1', 'p-searchqa-1-2')]
    assert decisions[0]['reason'].startswith('screen:policy: ') and decisions[1]['reason'] == 'unreadable:unknown_kind'
    assert program_dirs(step) == ['program-1', 'program-1-gate', 'program-1-smoke', 'programs']
    assert fired_anywhere(tmp_path / 'G') == {'p-searchqa-1-2'}
    assert writer_requests(step / 'programs')[1] == ['propose', 'fix']


def test_a_smoke_fault_or_a_gate_rejection_of_a_slot_candidate_promotes_nothing(tmp_path):
    """Three clean proposals, two slots: slot 1 faults in its smoke unit, slot 2 gains nothing at its gate. Neither
    failure brings in the third proposal: it stays not_needed (no id, no screen, no unit, no decision)."""
    reply = smoke.program_reply([clean(1), clean(2), clean(3)])
    services = real_writer_services(tmp_path, reply, scripted={'faults': {'p-searchqa-1-1': ['searchqa-l0']},
                                                               'outcomes': lambda bench, item_id, mounted: 'fail'})
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    step = tmp_path / 'G' / 's1'
    rows = json.loads((step / 'programs' / 'proposals.json').read_text())
    assert [(r['n'], r['status'], r['slot']) for r in rows] == [(1, 'passed', 1), (2, 'passed', 2), (3, 'not_needed', None)]
    assert rows[2]['procedure'] is None and rows[2]['first_screen'] is None and rows[2]['fix'] is None
    first, second = json.loads((step / 'decisions.json').read_text())['programs']
    assert (first['candidate'], first['accepted'], first['reason']) == (1, False, 'smoke_fault')
    assert (second['candidate'], second['accepted']) == (2, False) and second['reason'] != 'smoke_fault' and second['items'] == 3
    assert program_dirs(step) == ['program-1', 'program-1-smoke', 'program-2', 'program-2-gate', 'program-2-smoke', 'programs']
    assert fired_anywhere(tmp_path / 'G') == {'p-searchqa-1-1', 'p-searchqa-1-2'}  # p-searchqa-1-3 was never made
    assert writer_requests(step / 'programs')[1] == ['propose']
    assert library_.Library.load(step / 'library.json').programs('t01') == []


def five_calls_after_a_proposal_retry(system, user):
    """The format retry on the proposal, then three refused proposals with three refused fixes: 1 + 1 + 3 calls."""
    request = json.loads(user)
    if request['request'] == 'propose':
        return smoke.UNREADABLE_PROPOSAL
    if request['request'] == 'format_retry':
        return smoke.program_reply([refused(1), refused(2), refused(3)])
    return smoke.FIX_REFUSED


def five_calls_after_a_fix_retry(system, user):
    """Three refused proposals; fix 1 is unreadable and takes the retry, fix 2 is refused, fix 3 is unreadable with
    the budget spent: 1 + 3 + 1 calls (chosen by the change under repair, so the writer keeps no state)."""
    request = json.loads(user)
    if request['request'] == 'propose':
        return smoke.program_reply([refused(1), refused(2), refused(3)])
    if request['request'] == 'format_retry':
        return smoke.FIX_REFUSED
    unreadable = request['change']['description'] in (refused(1)[0]['description'], refused(3)[0]['description'])
    return smoke.UNREADABLE_PROPOSAL if unreadable else smoke.FIX_REFUSED


@pytest.mark.parametrize('writer, expected', [
    (five_calls_after_a_proposal_retry, ['propose', 'format_retry', 'fix', 'fix', 'fix']),
    (five_calls_after_a_fix_retry, ['propose', 'fix', 'format_retry', 'fix', 'fix'])])
def test_at_most_five_writer_calls_per_programs_unit_attempt(tmp_path, writer, expected):
    """The two worst cases of DESIGN 3.2 through the chain: exactly 5 writer calls, every proposal dropped with a
    zero-call decision, no program unit."""
    services = real_writer_services(tmp_path, writer)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    step = tmp_path / 'G' / 's1'
    sends, requests = writer_requests(step / 'programs')
    assert requests == expected and services.script.counts['program_writer'] == 5
    assert len({send['logical_call'] for send in sends}) == 5
    assert json.loads((tmp_path / 'G' / 'ledger.json').read_text())['by_unit']['s1/programs']['calls'] == 5
    rows = json.loads((step / 'programs' / 'proposals.json').read_text())
    assert [(r['n'], r['status'], r['slot']) for r in rows] == [(n, 'dropped_screen', None) for n in (1, 2, 3)]
    if writer is five_calls_after_a_fix_retry:
        assert rows[0]['fix']['format_retry']['readable'] and rows[2]['fix']['format_retry']['skipped'] == 'budget_spent'
    decisions = json.loads((step / 'decisions.json').read_text())['programs']
    assert [(r['proposal'], r['candidate'], r['unit'], r['accepted']) for r in decisions] == [(n, None, None, False) for n in (1, 2, 3)]
    assert program_dirs(step) == ['programs'] and not [u for u in state['done_units'] if u.startswith('s1/program-')]


def test_an_interruption_inside_the_promotion_loop_keeps_every_send_in_the_calls_file(tmp_path):
    """DESIGN 3.3: an attempt interrupted inside the loop (the second fix call raises) leaves every send it made in
    the unit's calls file, the interrupted one included; the resumed unit starts again from the proposal call with a
    new retry budget, at most 5 calls, and the file then holds every send of both attempts, as the ledger counted."""
    entries = [refused(1), refused(2), clean(3)]
    broken = {'on': True}

    def writer(system, user):
        request = json.loads(user)
        if request['request'] == 'propose':
            return smoke.UNREADABLE_PROPOSAL
        if request['request'] == 'format_retry':
            return smoke.program_reply(entries)
        if broken['on'] and request['change']['description'] == entries[1][0]['description']:
            raise RuntimeError('writer connection lost')
        return smoke.FIX_REFUSED
    services = real_writer_services(tmp_path, writer)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'exception:RuntimeError' and state['paused']['unit'] == 's1/programs'
    unit = tmp_path / 'G' / 's1' / 'programs'
    first, requests = writer_requests(unit)
    assert requests == ['propose', 'format_retry', 'fix', 'fix']
    assert all(send['receipt']['ok'] for send in first[:3]) and first[3]['receipt'] is None
    assert first[3]['exception'] == 'RuntimeError'
    assert not (unit / 'proposals.json').exists() and 's1/programs' not in state['done_units']
    assert program_dirs(tmp_path / 'G' / 's1') == ['programs']
    broken['on'] = False
    recovery(tmp_path)
    state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    every, requests = writer_requests(unit)
    assert every[:4] == first  # the interrupted attempt's sends stay as they were
    assert requests[4:] == ['propose', 'format_retry', 'fix', 'fix']  # again from the proposal call, a new budget
    assert [s['request_sha256'] for s in every[4:]] == [s['request_sha256'] for s in first]
    assert len({send['logical_call'] for send in every}) == 8
    assert json.loads((tmp_path / 'G' / 'ledger.json').read_text())['by_unit']['s1/programs']['calls'] == 8
    rows = json.loads((unit / 'proposals.json').read_text())
    assert [(r['n'], r['status'], r['slot']) for r in rows] == [(1, 'dropped_screen', None), (2, 'dropped_screen', None), (3, 'passed', 1)]
    decisions = json.loads((tmp_path / 'G' / 's1' / 'decisions.json').read_text())['programs']
    assert [(r['proposal'], r['candidate'], r['procedure_id']) for r in decisions] == [(1, None, None), (2, None, None), (3, 1, 'p-searchqa-1-3')]
    assert fired_anywhere(tmp_path / 'G') == {'p-searchqa-1-3'}
    # a later resume of the complete chain sends nothing and leaves the file alone
    before = services.script.counts['program_writer']
    assert chain.run(tmp_path, 'G', services=services, resume=True)['complete']
    assert services.script.counts['program_writer'] == before and writer_requests(unit)[0] == every
