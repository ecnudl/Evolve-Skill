"""Pure core of the typed-v2 economy read plan (``T/readplan.py``; spec/read-plan.md R8-R47, R78-R81, R91; RP3, RP8).

A small fake world plays the integration: per item a mount_identity output and a capture-mounted record built the way
``T/mount.py`` builds them (C0 = format block, C = historical card, F = learned card over the base card of D17, the
unknown branch mounting the base card as Q23 decided), a first-request capture through ``CaptureCall``, and two
embedder runs. No model, panel, chain state or ledger is touched; files go to a neutral scratch directory.
"""
import copy
import hashlib
import json
import pickle
import secrets
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.execskill.typed import FORBIDDEN_PATH_WORDS, ORDER
from skillopt.execskill.typed import readplan as rp

WORKTREE = Path(__file__).resolve().parents[1]
SCRATCH = Path('/tmp/typed2-rpcore')
NON_ZEBRA = [b for b in ORDER if b != 'zebralogic']
H = lambda text: hashlib.sha256(text.encode('utf-8')).hexdigest()  # noqa: E731


@pytest.fixture
def scratch():
    """A neutral directory (hex name): pytest's tmp_path carries 'test', which the sealed-path guard refuses."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    made = SCRATCH / ('rp-' + secrets.token_hex(6))
    made.mkdir()
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


def frozen_receipts(salt=''):
    entries = {}
    for event in rp.EVENTS:
        step = rp.step_of(event)
        entries[event] = {'step': step, **{key: H('%s%s-%d' % (salt, key, step)) for key in rp.FROZEN_KEYS
                                            if key != 'step'}}
    return entries


class World:
    """The integration's side of the pass, in memory. ``state[(bench, event, item)]`` is an S-event mount:
    {'type', 'unknown', 'card', 'programs': [(skill_id, body sha, name, description)]}; the default is an unknown
    item (unseen signature). ``second`` overrides the second embedder run. Two integration slips (review F1):
    ``mount_as[(bench, event)] = other`` mounts the event's items as ``other`` (its arm and state) while reporting the
    event's own frozen state; ``loaded[(bench, event)] = other`` loads the frozen state of ``other`` and reports it."""

    def __init__(self, *, base='historical', n=3, smoke=True):
        self.base, self.smoke = base, smoke
        self.ids = {b: sorted('PLANTED-ID-%s-%02d' % (b, i) for i in range(n)) for b in ORDER}
        self.public = {b: {i: {'question': 'SECRET TEXT %s' % i} for i in self.ids[b]} for b in ORDER}
        self.views = {b: {i: {'bench': b, 'body': 'VIEW TEXT %s' % i} for i in self.ids[b]} for b in ORDER}
        self.state, self.second = {}, {}
        self.raising, self.disagree, self.sends, self.user_salt = set(), set(), {}, {}
        self.mount_as, self.loaded = {}, {}
        self.header = {'chain': 'G', 'smoke': smoke, 'schedule': 'learn_first', 'read_plan': 'economy',
                       'base_card': base, 'manifest_record_sha256': H('manifest'),
                       'solver_settings_sha256': H('settings'), 'order': list(ORDER), 'frozen': frozen_receipts()}
        self.probe = None
        self.vectors = {b: [[[0.25, -0.5, float(k)] for k in range(n)] for _run in range(2)] for b in ORDER}

    @staticmethod
    def format_text(bench):
        return 'FORMAT BLOCK ' + bench

    @classmethod
    def historical_text(cls, bench):
        return cls.format_text(bench) if bench == 'zebralogic' else 'HISTORICAL CARD ' + bench

    def learn(self, bench, from_step, **state):
        for k in range(from_step, 6):
            for item in self.ids[bench]:
                self.state[(bench, 'S%d' % k, item)] = dict(state)

    def mount(self, bench, event, item, run):
        arm = rp.arm_of(event)
        mounted = {'arm': arm, 'type': None, 'source': None, 'unknown_reason': None, 'card_skill': None,
                   'programs_offered': [], 'selection': None}
        offered = []
        if arm == 'C0':
            system = self.format_text(bench)
        elif arm == 'C':
            system = self.historical_text(bench)
        else:
            state = (self.second if run == 2 else {}).get((bench, event, item)) or \
                self.state.get((bench, event, item)) or {'unknown': 'unseen_signature'}
            base = self.historical_text(bench) if self.base == 'historical' else self.format_text(bench)
            card = state.get('card') or ''
            system = card + '\n\n' + base if card.strip() else base
            if state.get('type') is not None:
                offered = list(state.get('programs') or [])
                mounted.update({'type': state['type'], 'source': 'src-' + state['type'],
                                'card_skill': 'card-x' if card.strip() else None,
                                'programs_offered': [p[0] for p in offered]})
                if offered:
                    index = json.dumps([[p[2], p[3]] for p in offered]) + json.dumps(self.views[bench][item])
                    mounted['selection'] = {'status': 'parse_failure', 'attempts': [H(index), H(index + 'retry')],
                                            'raw_excerpt': 'read_plan_capture', 'failure': 'Reply is not a JSON object'}
                else:
                    mounted['selection'] = {'status': 'not_needed', 'attempts': [], 'raw_excerpt': None,
                                            'failure': None}
            else:
                mounted['unknown_reason'] = state.get('unknown', 'unseen_signature')
        mounted.update({'card_text': system, 'system_card': system, 'system_card_sha256': H(system)})
        identity = {'system_card_sha256': H(system), 'programs_offered': [[p[0], p[1]] for p in offered],
                    'forced': None}
        if (bench, event) in self.disagree:
            mounted['system_card_sha256'] = H(system + ' other')
        return identity, mounted, system

    def read_mount(self, event):
        """The frozen state the integration loaded for an event, as it reports it (``load_frozen``'s file hashes)."""
        frozen = self.header['frozen'][event]
        return {key: frozen[key] for key in rp.READ_MOUNT_KEYS}

    def record(self, bench, event, item, run, *, source=None):
        identity, mounted, system = self.mount(bench, source or event, item, run)
        components = rp.item_components(identity, mounted, arm=rp.arm_of(event),
                                        public_sha256=rp.public_sha256(self.public[bench][item]),
                                        view_sha256=rp.view_sha256(self.views[bench][item]))
        first = None
        if run == 1 and rp.first_request_required(bench, components):
            call = rp.CaptureCall()
            user = json.dumps(self.public[bench][item], sort_keys=True) + self.user_salt.get((bench, event), '')
            for _ in range(self.sends.get((bench, event), 1)):
                call(system, user)
            first = call.first_request()
        return rp.item_record(bench, components, first_request=first)

    def entry(self, bench, event):
        ids = self.ids[bench]
        loaded = self.loaded.get((bench, event), event)
        source, mount = self.mount_as.get((bench, event), loaded), self.read_mount(loaded)
        if (bench, event) in self.raising:  # a non-stop exception of an identity call (R16)
            return rp.event_entry(bench, event, ids, None, read_mount=mount, reason='identity_exception')
        try:
            records = [self.record(bench, event, i, 1, source=source) for i in ids]
            second = [self.record(bench, event, i, 2, source=source) for i in ids] if event in rp.S_EVENTS else None
        except rp.ReadPlanError as error:
            return rp.event_entry(bench, event, ids, None, read_mount=mount, reason=error.code)
        return rp.event_entry(bench, event, ids, records, read_mount=mount, second=second)

    def inputs(self, bench):
        ids = self.ids[bench]
        views = [self.views[bench][i] for i in ids]
        return rp.inputs_record('G', bench, ids, [rp.view_sha256(v) for v in views],
                                alfworld_views=views if bench == 'alfworld' else None, vectors=self.vectors[bench])

    def files(self):
        benches = {b: {'inputs': self.inputs(b), 'entries': {e: self.entry(b, e) for e in rp.EVENTS},
                       'registry_sha256': None if self.smoke else H('registry ' + b),
                       'run_constants_sha256': H('constants ' + b)} for b in ORDER}
        return rp.plan_files(**self.header, benches=benches, probe=self.probe)

    def plan(self):
        return self.files()[rp.PLAN_FILE]


def classes(plan, bench):
    return [(c['members'], c['representative']) for c in plan['benches'][bench]['classes']]


S = ['S1', 'S2', 'S3', 'S4', 'S5']


# ---- classes, representatives, both base cards, ZebraLogic (R28-R31, R40, R91) -------------------------------
@pytest.mark.parametrize('base', ['historical', 'format'])
def test_identical_events_form_one_class_with_the_latest_event_as_representative(base):
    plan = World(base=base).plan()
    for bench in NON_ZEBRA:
        if base == 'historical':  # R91 b: {C0} > C0, {C, S1..S5} > S5
            assert classes(plan, bench) == [(['C0'], 'C0'), (['C'] + S, 'S5')]
        else:                     # R91 a: {C0, S1..S5} > S5, {C} > C
            assert classes(plan, bench) == [(['C0'] + S, 'S5'), (['C'], 'C')]
    assert classes(plan, 'zebralogic') == [(['C0', 'C'] + S, 'S5')]   # R91 d: C equals C0 under every base
    assert plan['counts'] == {'pairs': 35, 'fresh': 9, 'alias': 26, 'fallback': 0}       # R40 best case
    second = 'C0' if base == 'historical' else 'C'
    assert plan['read_order'] == [['S5', list(ORDER)], [second, NON_ZEBRA]]           # D10 e, R36
    assert rp.verify_plan(plan) is plan


def test_historical_base_card_less_and_unknown_items_have_the_identity_of_C():
    world = World(base='historical')
    for i, item in enumerate(world.ids['officeqa']):  # S1: one unknown item, the others typed without a card
        world.state[('officeqa', 'S1', item)] = {'unknown': 'distance_above_p95'} if i == 0 else {'type': 'qa'}
    entries = {e: world.entry('officeqa', e) for e in ('C0', 'C', 'S1')}
    assert entries['S1']['identity'] == entries['C']['identity'] != entries['C0']['identity']
    assert [c['type'] for c in entries['S1']['components']] == [None, 'qa', 'qa']
    plan = world.plan()
    assert classes(plan, 'officeqa') == [(['C0'], 'C0'), (['C'] + S, 'S5')]
    row = plan['benches']['officeqa']['events']['S1']
    assert (row['typed'], row['unknown'], row['with_card']) == (2, 1, 0)


def test_format_base_card_less_and_unknown_items_have_the_identity_of_C0():
    world = World(base='format')
    for item in world.ids['searchqa']:
        world.state[('searchqa', 'S2', item)] = {'type': 'qa'}
    entries = {e: world.entry('searchqa', e) for e in ('C0', 'C', 'S1', 'S2')}
    assert entries['S1']['identity'] == entries['S2']['identity'] == entries['C0']['identity'] != entries['C']['identity']


def test_zebralogic_C_equals_C0_and_shares_first_requests():
    world = World(base='historical')
    c0, c = world.entry('zebralogic', 'C0'), world.entry('zebralogic', 'C')
    assert c0['identity'] == c['identity'] and c0['first_request'] == c['first_request']
    assert all(h is not None for h in c0['first_request'])


@pytest.mark.parametrize('base', ['historical', 'format'])
@pytest.mark.parametrize('k', [1, 2, 3])
def test_a_card_learned_at_step_k_splits_before_and_after(base, k):
    world = World(base=base)
    world.learn('officeqa', k, type='qa', card='LEARNED CARD')
    got = classes(world.plan(), 'officeqa')
    before, after = S[:k - 1], S[k - 1:]
    if base == 'historical':
        expected = [(['C0'], 'C0'), (['C'] + before, (['C'] + before)[-1]), (after, 'S5')]
    else:
        expected = [(['C0'] + before, (['C0'] + before)[-1]), (['C'], 'C'), (after, 'S5')]
    assert sorted(got) == sorted(expected)


@pytest.mark.parametrize('change', ['card', 'selection', 'programs'])
def test_a_change_of_card_selection_or_offered_programs_splits_the_class(change):
    world = World(base='historical')
    program = ('prog-a', H('body a'), 'prog-a', 'description a')
    base_state = {'type': 'qa', 'card': 'CARD', 'programs': [program] if change != 'card' else []}
    world.learn('officeqa', 1, **base_state)
    item = world.ids['officeqa'][1]  # one item only: the all-items rule still splits (T4)
    changed = dict(base_state)
    if change == 'card':
        changed['card'] = 'CARD v2'
    elif change == 'selection':
        changed['programs'] = [(program[0], program[1], program[2], 'description b')]  # same body, new index text
    else:
        changed['programs'] = [(program[0], H('body b'), program[2], program[3])]      # same name, other body (R15 a)
    for event in ('S3', 'S4', 'S5'):
        world.state[('officeqa', event, item)] = changed
    plan = world.plan()
    assert classes(plan, 'officeqa') == [(['C0'], 'C0'), (['C'], 'C'), (['S1', 'S2'], 'S2'), (['S3', 'S4', 'S5'], 'S5')]
    rows = plan['benches']['officeqa']['events']
    assert rows['S2']['identity_list_sha256'] != rows['S3']['identity_list_sha256']
    if change != 'card':  # programs offered: no first request for those items (RP3)
        assert rows['S3']['captured'] == 0 and rows['S3']['with_programs'] == 3


@pytest.mark.parametrize('field', ['public_sha256', 'view_sha256', 'system_sha256', 'selection_sha256', 'programs'])
def test_every_hashed_component_splits_and_descriptive_fields_do_not(field):
    world = World()
    world.learn('searchqa', 1, type='qa', programs=[('p', H('body'), 'p', 'd')])
    ids = world.ids['searchqa']
    base = [world.record('searchqa', 'S1', i, 1) for i in ids]
    other = deepcopy(base)
    value = {'programs': [H('other body')], 'selection_sha256': H('other selection')}.get(field, H('other ' + field))
    other[0]['components'][field] = value
    other[0] = rp.item_record('searchqa', other[0]['components'], first_request=other[0]['first_request'])
    entries = {e: rp.event_entry('searchqa', e, ids, base if e != 'S5' else other, read_mount=world.read_mount(e),
                                 second=base if e != 'S5' else other) for e in S}
    summaries = {e: rp.event_summary('searchqa', ids, entries[e]) for e in S}
    final, found = rp.compute_classes('searchqa', summaries)
    assert [(c['members'], c['representative']) for c in found if c['members'][0] != 'C0' and c['members'] != ['C']] \
        == [(['S1', 'S2', 'S3', 'S4'], 'S4'), (['S5'], 'S5')]
    # RP8: type id, source, unknown reason, card skill and offered ids are stored beside the identity, never hashed
    renamed = deepcopy(base[0]['components'])
    renamed.update({'type': 'other-type', 'source': 'src-z', 'card_skill': 'card-z', 'offered': ['q']})
    assert rp.item_identity('searchqa', renamed) == base[0]['identity']


def test_a_type_id_only_difference_does_not_split_and_flips_are_counted():
    world = World(base='historical')
    world.learn('searchqa', 1, type='qa-a', card='CARD')
    for item in world.ids['searchqa']:
        world.state[('searchqa', 'S3', item)] = {'type': 'qa-b', 'card': 'CARD'}  # same card text, other type id
    world.second[('searchqa', 'S4', world.ids['searchqa'][0])] = {'type': 'qa-c', 'card': 'CARD'}
    plan = world.plan()
    assert classes(plan, 'searchqa') == [(['C0'], 'C0'), (['C'], 'C'), (S, 'S5')]
    assert plan['benches']['searchqa']['embed'] == {'runs': 2, 'descriptive_flips': 1}
    assert plan['counts']['fallback'] == 0


# ---- first requests (RP3, R19, R29) and fallbacks (R16, R30, R31) ------------------------------------------
def test_first_request_condition_splits_where_both_hashes_exist_and_differ():
    world = World(base='historical')
    world.user_salt[('searchqa', 'S4')] = ' other user text'   # same identity, another first request
    world.user_salt[('alfworld', 'S4')] = ' other user text'   # ALFWorld: no capture, so no difference
    plan = world.plan()
    rows = plan['benches']['searchqa']['events']
    assert rows['S4']['identity_list_sha256'] == rows['S3']['identity_list_sha256']
    assert {e: rows[e]['reason'] for e in ['C'] + S} == {
        e: 'first_request_mismatch' for e in ['C'] + S}   # S4 differs from every other member: all of them fall back
    assert classes(plan, 'searchqa') == [([e], e) for e in rp.EVENTS]
    assert classes(plan, 'alfworld') == [(['C0'], 'C0'), (['C'] + S, 'S5')]
    assert plan['benches']['alfworld']['events']['S4']['first_request_list_sha256'] is None


def test_first_request_mismatch_rule_on_summaries():
    good = {'status': 'ok', 'reason': None, 'identity_list_sha256': H('x'), 'first_request_list_sha256': H('f1')}
    other = dict(good, first_request_list_sha256=H('f2'))
    final, found = rp.compute_classes('searchqa', {'C': good, 'S1': good, 'S2': other, 'S3': good})
    assert final['S2'] == final['S1'] == {'status': 'fallback', 'reason': 'first_request_mismatch'}
    assert final['C0'] == {'status': 'fallback', 'reason': 'identity_exception'}  # missing summary
    same, _ = rp.compute_classes('searchqa', {e: good for e in rp.EVENTS})
    assert all(v['status'] == 'ok' for v in same.values())
    # an ok summary that lacks the first-request list where RP3 requires one is unreadable
    bad, _ = rp.compute_classes('officeqa', {e: dict(good, first_request_list_sha256=None) for e in rp.EVENTS})
    assert all(v == {'status': 'fallback', 'reason': 'identity_exception'} for v in bad.values())


def test_missing_or_unreadable_identity_is_its_own_fallback_class():
    good = {'status': 'ok', 'reason': None, 'identity_list_sha256': H('x'), 'first_request_list_sha256': None}
    summaries = {e: dict(good) for e in rp.EVENTS}
    del summaries['S2']                                          # missing
    summaries['S3'] = {'status': 'ok', 'identity_list_sha256': 'not a hash'}   # unreadable
    summaries['S4'] = dict(good, status='fallback', reason='identity_exception')  # equal list hash, still alone (T8 k)
    final, found = rp.compute_classes('alfworld', summaries)
    assert [(c['members'], c['representative']) for c in found] == [
        (['C0', 'C', 'S1', 'S5'], 'S5'), (['S2'], 'S2'), (['S3'], 'S3'), (['S4'], 'S4')]
    assert final['S2'] == final['S3'] == {'status': 'fallback', 'reason': 'identity_exception'}
    # in the pass: an identity call that raised, a disagreement, a record that does not recompute
    world = World()
    world.raising.add(('officeqa', 'S2'))
    world.disagree.add(('officeqa', 'S3'))
    entry = world.entry('officeqa', 'S4')
    entry['identity'][0] = H('forged identity')
    files = world.files()
    rows = files[rp.PLAN_FILE]['benches']['officeqa']['events']
    assert (rows['S2']['reason'], rows['S3']['reason']) == ('identity_exception', 'identity_disagreement')
    assert rows['S2']['identity_list_sha256'] is None
    broken = rp.identities_record('G', 'officeqa', world.inputs('officeqa'),
                                  {**{e: world.entry('officeqa', e) for e in rp.EVENTS}, 'S4': entry},
                                  frozen=world.header['frozen'])
    assert broken['events']['S4']['reason'] == 'identity_exception' and broken['events']['S4']['identity'] is None
    partial = rp.identities_record('G', 'officeqa', world.inputs('officeqa'), {'C0': world.entry('officeqa', 'C0')},
                                   frozen=world.header['frozen'])
    assert all(partial['events'][e]['reason'] == 'identity_exception' for e in rp.EVENTS if e != 'C0')
    assert classes(files[rp.PLAN_FILE], 'officeqa') == [
        (['C0'], 'C0'), (['C', 'S1', 'S4', 'S5'], 'S5'), (['S2'], 'S2'), (['S3'], 'S3')]


@pytest.mark.parametrize('sends', [0, 2])
def test_capture_without_exactly_one_send_is_capture_failed(sends):
    world = World()
    world.sends[('spreadsheetbench', 'S1')] = sends
    world.sends[('alfworld', 'S1')] = sends  # never captured
    plan = world.plan()
    assert plan['benches']['spreadsheetbench']['events']['S1']['reason'] == 'capture_failed'
    assert plan['benches']['alfworld']['events']['S1']['status'] == 'ok'
    assert (['S1'], 'S1') in classes(plan, 'spreadsheetbench')


def test_embedder_instability_is_a_fallback():
    world = World()
    world.second[('searchqa', 'S2', world.ids['searchqa'][0])] = {'type': 'qa', 'card': 'CARD'}
    plan = world.plan()
    assert plan['benches']['searchqa']['events']['S2']['reason'] == 'embedder_unstable'
    ids = world.ids['searchqa']
    records = [world.record('searchqa', 'S1', i, 1) for i in ids]
    assert rp.event_entry('searchqa', 'S1', ids, records, read_mount=world.read_mount('S1'))['reason'] \
        == 'embedder_unstable'  # no second run
    with pytest.raises(ValueError):
        rp.event_entry('searchqa', 'C', ids, records, read_mount=world.read_mount('C'), second=records)


def test_smoke_probe_turns_a_would_be_alias_into_its_own_class():
    world = World(base='historical')
    world.probe = ['C0', 'zebralogic']
    plan = world.plan()
    rows = plan['benches']['zebralogic']['events']
    assert rows['C0']['reason'] == 'smoke_probe'
    assert rows['C0']['identity_list_sha256'] == rows['C']['identity_list_sha256']           # S3 c
    assert rows['C0']['first_request_list_sha256'] == rows['C']['first_request_list_sha256']
    assert classes(plan, 'zebralogic') == [(['C0'], 'C0'), (['C'] + S, 'S5')]
    assert plan['counts'] == {'pairs': 35, 'fresh': 10, 'alias': 25, 'fallback': 1}
    world_real = World(smoke=False)
    world_real.probe = ['C0', 'zebralogic']
    with pytest.raises(ValueError):
        world_real.plan()


def test_item_identity_collision_attempts():
    world = World()
    comps = rp.item_components(*world.mount('searchqa', 'C', world.ids['searchqa'][0], 1)[:2], arm='C',
                               public_sha256=H('p'), view_sha256=H('v'))
    two = dict(comps, programs=[H('x'), H('y')], offered=['a', 'b'], selection_sha256=H('s'))
    one = dict(comps, programs=[H('xy')], offered=['a'], selection_sha256=H('s'))
    swapped = dict(two, programs=[H('y'), H('x')])
    assert len({rp.item_identity('searchqa', c) for c in (comps, two, one, swapped)}) == 4   # T8 b, c
    assert rp.item_identity('searchqa', comps) != rp.item_identity('officeqa', comps)       # T8 j
    ids = world.ids['searchqa']
    hashes = [H('i%d' % k) for k in range(len(ids))]
    renamed = [ids[0] + '-other'] + ids[1:]
    assert rp.identity_list_sha256('searchqa', ids, hashes) != rp.identity_list_sha256('searchqa', sorted(renamed),
                                                                                        hashes)   # T8 h
    with pytest.raises(ValueError):
        rp.inputs_record('G', 'searchqa', [], [])                                          # T8 i
    with pytest.raises(rp.ReadPlanError) as raised:
        rp.item_components({'system_card_sha256': H('s'), 'programs_offered': [], 'forced': H('candidate')},
                           {'arm': 'F', 'system_card_sha256': H('s'), 'programs_offered': []}, arm='F',
                           public_sha256=H('p'), view_sha256=H('v'))
    assert raised.value.code == 'identity_exception'                                       # R11: no candidate in a read


def test_selection_hash_reduction_and_capture_objects():
    assert rp.selection_sha256({'selection': None}) is None
    assert rp.selection_sha256({'selection': {'attempts': []}}) is None
    assert rp.selection_sha256({'selection': {'attempts': [H('a'), H('b')]}}) == H('a')
    assert rp.capture_selector('s', 'u') == {'ok': False, 'error_type': 'read_plan_capture', 'usage': {}}
    call = rp.CaptureCall()
    receipt = call('system text', 'user text')
    assert receipt['ok'] is False and receipt['error_type'] == 'read_plan_capture'
    assert call.first_request() == H('system text\x00user text') and call.tokens() == 0
    assert call.infrastructure_unknown() is False
    call('again', 'again')
    assert call.first_request() is None and [s['request_sha256'] for s in call.sends][1] is None


# ---- the plan: canonical bytes, self-hash, write_once, load, verify (R32, R44, R80) -------------------------
def test_plan_self_hash_detects_any_tampered_byte(scratch):
    plan = World().plan()
    path = rp.plan_path(scratch, 'G')
    digest = rp.write_once(path, plan)
    data = path.read_bytes()
    assert digest == hashlib.sha256(data).hexdigest() and data == rp.canonical_bytes(plan)
    assert rp.load_plan(path, file_sha256=digest, plan_sha256=plan['plan_sha256']) == plan
    alphabet = {**{c: '0123456789abcdef' for c in '0123456789abcdef'}, ' ': '\t', '\n': ' '}
    for position in range(len(data)):  # every byte: a value, a key, a space, a newline, a bracket, the hash itself
        old = chr(data[position])
        new = next((c for c in alphabet.get(old, 'xyzXYZ') if c != old), 'q')
        tampered = data[:position] + new.encode() + data[position + 1:]
        with pytest.raises(rp.ReadPlanError) as raised:
            rp.plan_from_bytes(tampered)
        assert raised.value.code in ('plan_file_mismatch', 'plan_self_check')
        with pytest.raises(rp.ReadPlanError):
            rp.plan_from_bytes(tampered, file_sha256=digest)


def test_verify_plan_recomputes_classes_order_and_counts():
    plan = World().plan()
    edits = [lambda p: p['counts'].update(fresh=8),
             lambda p: p['read_order'].reverse(),
             lambda p: p['benches']['searchqa']['classes'][1].update(representative='S4'),
             lambda p: p['benches']['searchqa']['events']['S3'].update(status='fallback', reason='smoke_probe'),
             lambda p: p['benches']['officeqa']['events']['S1'].update(identity_list_sha256=H('other')),
             lambda p: p.update(base_card='other'),
             lambda p: p['frozen']['C'].update(receipt_sha256=H('other'))]
    for edit in edits:
        changed = deepcopy(plan)
        edit(changed)
        resealed = {k: v for k, v in changed.items() if k != 'plan_sha256'}
        resealed['plan_sha256'] = rp.canonical_sha256(resealed)
        with pytest.raises(rp.ReadPlanError) as raised:
            rp.verify_plan(resealed)
        assert raised.value.code == 'plan_self_check'
    with pytest.raises(rp.ReadPlanError) as raised:
        rp.verify_plan(plan, plan_sha256=H('bound elsewhere'))
    assert raised.value.code == 'plan_file_mismatch'


def test_write_once_accepts_identical_and_refuses_different_bytes(scratch):
    path = scratch / 'G' / rp.PLAN_FILE
    record = {'a': 1, 'b': [H('x')]}
    first = rp.write_once(path, record)
    assert rp.write_once(path, {'b': [H('x')], 'a': 1}) == first          # same canonical bytes
    with pytest.raises(rp.WriteOnceMismatch):
        rp.write_once(path, {'a': 2, 'b': [H('x')]})
    assert path.read_bytes() == rp.canonical_bytes(record)
    assert [p.name for p in path.parent.iterdir()] == [rp.PLAN_FILE]      # no temporary file left
    stale = path.parent / ('.%s.%d.%s.part' % (rp.PLAN_FILE, 4242, '0123456789abcdef'))
    stale.write_bytes(b'{"partial": ')
    assert rp.PART_NAME.fullmatch(stale.name) and rp.record_names(path.parent) == [rp.PLAN_FILE]
    assert rp.remove_part_files(path.parent) == 1 and not stale.exists()
    sealed = rp.inputs_path(scratch, 'G', 'searchqa', smoke=False)
    with pytest.raises(ValueError):
        rp.write_once(sealed, record)                                      # 'test-read-plan' is sealed by its name
    rp.write_once(sealed, record, allow_sealed=True)
    with pytest.raises(ValueError):
        rp.write_once(scratch / 'G' / 'plan.txt', record)


def test_sealed_files_round_trip_and_detect_changes(scratch):
    world = World(smoke=False)
    files = world.files()
    inputs, identities = files[rp.inputs_name('alfworld')], files[rp.identities_name('alfworld')]
    assert inputs['alfworld_views'] is not None and files[rp.inputs_name('searchqa')]['alfworld_views'] is None
    in_path = rp.inputs_path(scratch, 'G', 'alfworld', smoke=False)
    id_path = rp.identities_path(scratch, 'G', 'alfworld', smoke=False)
    in_hash = rp.write_once(in_path, inputs, allow_sealed=True)
    id_hash = rp.write_once(id_path, identities, allow_sealed=True)
    plan = files[rp.PLAN_FILE]
    assert (plan['benches']['alfworld']['inputs_sha256'], plan['benches']['alfworld']['identities_sha256']) \
        == (in_hash, id_hash)
    loaded = rp.load_sealed(in_path, 'inputs', file_sha256=in_hash)
    assert rp.load_sealed(id_path, 'identities', file_sha256=id_hash, inputs=loaded) == identities
    with pytest.raises(rp.ReadPlanError) as raised:
        rp.sealed_from_bytes(in_path.read_bytes().replace(b'0.25', b'0.26', 1), 'inputs')
    assert raised.value.code == 'inputs_mismatch'
    with pytest.raises(rp.ReadPlanError) as raised:
        rp.sealed_from_bytes(id_path.read_bytes(), 'identities', file_sha256=H('other'))
    assert raised.value.code == 'sealed_file_mismatch'
    searchqa = files[rp.inputs_name('searchqa')]
    rp.check_views(searchqa, list(searchqa['view_sha256']))
    with pytest.raises(rp.ReadPlanError) as raised:
        rp.check_views(searchqa, [H('recomputed other view')] + searchqa['view_sha256'][1:])
    assert raised.value.code == 'view_mismatch'
    with pytest.raises(ValueError):
        rp.inputs_record('G', 'searchqa', searchqa['item_ids'], searchqa['view_sha256'],
                         vectors=[[[float('nan')]] * 3] * 2)


# ---- replay comparison (R47 core, T10) -----------------------------------------------------------------------
def stored_bytes(files):
    return {name: rp.canonical_bytes(record) for name, record in files.items()}


def mutations():
    def item(bench, k=0):
        return lambda w: w.ids[bench][k]
    return {
        'base_card': lambda w: w.header.update(base_card='format'),
        'manifest': lambda w: w.header.update(manifest_record_sha256=H('other manifest')),
        'settings': lambda w: w.header.update(solver_settings_sha256=H('other settings')),
        'frozen': lambda w: w.header.update(frozen=frozen_receipts('other ')),
        'order': lambda w: w.header.update(order=list(reversed(ORDER))),
        'view': lambda w: w.views['officeqa'][item('officeqa')(w)].update(body='OTHER VIEW'),
        'public': lambda w: w.public['spreadsheetbench'][item('spreadsheetbench')(w)].update(question='OTHER'),
        'vector': lambda w: w.vectors['alfworld'][1][0].__setitem__(0, 0.75),
        'card': lambda w: w.learn('searchqa', 4, type='qa', card='CARD'),
        'first_request': lambda w: w.user_salt.update({('zebralogic', 'S5'): ' other'}),
        'probe': lambda w: setattr(w, 'probe', ['C0', 'zebralogic']),
        'items': lambda w: w.ids.update(searchqa=sorted(w.ids['searchqa'] + ['PLANTED-ID-searchqa-99'])),
    }


def mutated_world(name):
    world = World()
    if name == 'items':
        mutations()[name](world)
        extra = 'PLANTED-ID-searchqa-99'
        world.public['searchqa'][extra] = {'question': 'SECRET TEXT ' + extra}
        world.views['searchqa'][extra] = {'bench': 'searchqa', 'body': 'VIEW TEXT ' + extra}
        world.vectors['searchqa'] = [[[0.25, -0.5, float(k)] for k in range(4)] for _run in range(2)]
    else:
        mutations()[name](world)
    return world


def test_replay_comparison_is_equal_on_equal_inputs_and_different_on_any_change():
    stored = stored_bytes(World().files())
    again = World().files()
    assert rp.replay_compare(stored, again) == {'verdict': 'equal', 'files': 11, 'equal': 11, 'different': 0,
                                                'missing': 0, 'reason': None}
    for name in mutations():
        verdict = rp.replay_compare(stored, mutated_world(name).files())
        assert verdict['verdict'] == 'different' and verdict['reason'] == 'replay_different', name
        assert verdict['different'] >= 1, name
    partial = dict(stored)
    del partial[rp.identities_name('searchqa')]
    assert rp.replay_compare(partial, again)['missing'] == 1
    with pytest.raises(ValueError):
        rp.replay_compare({'notes.json': b'{}'}, {})


def test_replay_bytes_do_not_depend_on_the_hash_seed():
    code = ('import sys, hashlib; sys.path.insert(0, %r); from tests.test_typed_readplan_core import World, rp; '
            'w = World(); w.learn("officeqa", 3, type="qa", card="CARD"); f = w.files(); '
            'print(hashlib.sha256(b"".join(rp.canonical_bytes(f[n]) for n in sorted(f))).hexdigest())') % str(WORKTREE)
    digests = set()
    for seed in ('1', '2'):
        done = subprocess.run([sys.executable, '-c', code], cwd=str(WORKTREE), env={'PYTHONHASHSEED': seed},
                              capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stderr[-2000:]
        digests.add(done.stdout.strip())
    world = World()
    world.learn('officeqa', 3, type='qa', card='CARD')
    files = world.files()
    digests.add(hashlib.sha256(b''.join(rp.canonical_bytes(files[n]) for n in sorted(files))).hexdigest())
    assert len(digests) == 1


# ---- alias records (R39, R41, RP3; 3.4) ----------------------------------------------------------------------
CHECK = {'items': 3, 'equal': 3, 'unequal': 0}
COUNTS = {'unknown': 1, 'infrastructure_unknown': 1, 'configuration_errors': 0}


def test_alias_build_verify_and_state_entry(scratch):
    plan = World(base='historical').plan()
    assert ('C', 'searchqa') in rp.alias_pairs(plan) and len(rp.alias_pairs(plan)) == plan['counts']['alias']
    assert rp.members_of(plan, 'searchqa', 'S5') == ['C', 'S1', 'S2', 'S3', 'S4']
    record = rp.build_alias(plan, 'S2', 'searchqa', check=CHECK, representative_aggregate_sha256=H('aggregate'),
                            representative_counts=COUNTS)
    assert record['representative'] == {'event': 'S5', 'unit': 'practice-read-S5-searchqa'}
    assert record['identity_list_sha256']['member'] == record['identity_list_sha256']['representative']
    assert record['representative_counts'] == COUNTS and record['plan_sha256'] == plan['plan_sha256']
    path = rp.alias_path(scratch, 'G', 'S2', 'searchqa')
    rp.write_once(path, record)
    assert rp.load_alias(path, plan, representative_aggregate_sha256=H('aggregate')) == record
    assert rp.alias_state_entry(record) == {'kind': 'alias', 'status': 'alias', 'alias_of': 'S5', 'items': 3,
                                            'alias_sha256': record['record_sha256']}
    with pytest.raises(rp.ReadPlanError) as raised:
        rp.verify_alias(record, plan, representative_aggregate_sha256=H('rebuilt mirror'))   # R44 a
    assert raised.value.code == 'read_alias_invalid'
    with pytest.raises(rp.ReadPlanError):
        rp.verify_alias(record, plan, representative_counts=dict(COUNTS, unknown=0))      # counts from the mirror
    assert rp.verify_alias(record, plan, representative_counts=COUNTS) == record
    moved = rp.alias_path(scratch, 'G', 'S1', 'searchqa')     # a valid record under another pair's name
    rp.write_once(moved, record)
    with pytest.raises(rp.ReadPlanError):
        rp.load_alias(moved, plan)


@pytest.mark.parametrize('edit', ['representative', 'unit', 'plan_hash', 'unresealed'])
def test_alias_with_a_wrong_representative_or_plan_hash_fails(edit):
    plan = World(base='historical').plan()
    record = rp.build_alias(plan, 'C', 'officeqa', check=CHECK, representative_aggregate_sha256=H('aggregate'),
                            representative_counts=COUNTS)
    changed = deepcopy(record)
    if edit == 'representative':
        changed['representative'] = {'event': 'S4', 'unit': 'practice-read-S4-officeqa'}
    elif edit == 'unit':
        changed['representative']['unit'] = 'test-read-S5-officeqa'
    elif edit == 'plan_hash':
        changed['plan_sha256'] = H('another plan')
    else:
        changed['items'] = 4
    if edit != 'unresealed':
        changed = {k: v for k, v in changed.items() if k != 'record_sha256'}
        changed['record_sha256'] = rp.canonical_sha256(changed)
    with pytest.raises(rp.ReadPlanError) as raised:
        rp.verify_alias(changed, plan)
    assert raised.value.code == 'read_alias_invalid'
    other = World(base='format').plan()
    with pytest.raises(rp.ReadPlanError):
        rp.verify_alias(record, other)


def test_alias_refusals():
    world = World(base='historical')
    world.probe = ['C0', 'zebralogic']
    plan = world.plan()
    kw = {'representative_aggregate_sha256': H('a'), 'representative_counts': COUNTS}
    with pytest.raises(ValueError):
        rp.build_alias(plan, 'S5', 'searchqa', check=CHECK, **kw)            # a representative
    with pytest.raises(ValueError):
        rp.build_alias(plan, 'C0', 'zebralogic', check=CHECK, **kw)          # a fallback
    with pytest.raises(ValueError):
        rp.build_alias(plan, 'C', 'searchqa', check={'items': 3, 'equal': 2, 'unequal': 1}, **kw)
    with pytest.raises(ValueError):
        rp.build_alias(plan, 'C', 'searchqa', check={'items': 3, 'equal': 2, 'unequal': 0}, **kw)


def test_post_read_check_counts():
    world = World()
    world.learn('officeqa', 1, type='qa', programs=[('prog-a', H('body'), 'prog-a', 'd')])
    identities = world.files()[rp.identities_name('officeqa')]
    expected = rp.expected_for_check(identities, 'S5')
    rows = []
    for item, want in zip(world.ids['officeqa'], expected):
        _identity, mounted, _system = world.mount('officeqa', 'S5', item, 1)
        rows.append({'mount': mounted, 'public_hash': want['public_sha256'], 'request_sha256': [H('solver')]})
    observed = [rp.observed_from_row(row, {'prog-a': H('body')}.__getitem__) for row in rows]
    assert rp.post_read_check(expected, observed) == {'items': 3, 'equal': 3, 'unequal': 0}
    assert rp.check_passed(rp.post_read_check(expected, observed), 3)
    observed[1] = dict(observed[1], public_sha256=H('other'))
    observed[2] = None
    assert rp.post_read_check(expected, observed) == {'items': 3, 'equal': 1, 'unequal': 1}
    unknown = rp.observed_from_row(rows[0], {}.__getitem__)
    assert unknown['programs'] == [None]


# ---- open records and names (R81, 3.8, T23) ------------------------------------------------------------------
def test_open_records_hold_hashes_and_counts_only(scratch):
    world = World(base='historical')
    world.learn('officeqa', 2, type='qa', card='LEARNED CARD TEXT')
    world.probe = ['C0', 'zebralogic']
    plan = world.plan()
    assert rp.members_of(plan, 'officeqa', 'S1') == ['C']
    record = rp.build_alias(plan, 'C', 'officeqa', check=CHECK, representative_aggregate_sha256=H('aggregate'),
                            representative_counts=COUNTS)
    ids = [i for b in ORDER for i in world.ids[b]]
    planted = ['SECRET TEXT', 'VIEW TEXT', 'LEARNED CARD TEXT', 'HISTORICAL CARD', 'FORMAT BLOCK']
    vocabulary = set(rp.EVENTS) | set(ORDER) | set(rp.READ_PLAN_REASONS) | set(rp.STATUSES) | {
        'C0', 'C', 'F', 'G', 'learn_first', 'economy', 'historical', 'format', 'alias', rp.PLAN_VERSION,
        rp.IDENTITY_VERSION, rp.ALIAS_VERSION} | {rp.read_unit_name(e, b, smoke=True) for e in rp.EVENTS for b in ORDER}

    def strings(value):
        if isinstance(value, dict):
            for key, inner in value.items():
                yield key
                yield from strings(inner)
        elif isinstance(value, list):
            for inner in value:
                yield from strings(inner)
        elif isinstance(value, str):
            yield value
        else:
            assert value is None or type(value) in (int, bool), type(value)   # counts and flags, never a score
    for doc in (plan, record):
        assert rp.check_open_record(doc, item_ids=ids, texts=planted) is doc
        for text in strings(doc):
            assert rp.is_hash(text) or text in vocabulary or text in rp.PLAN_KEYS + rp.BENCH_KEYS + rp.EVENT_KEYS \
                + rp.CLASS_KEYS + rp.ALIAS_KEYS + rp.FROZEN_KEYS + rp.CHECK_KEYS + rp.COUNT_KEYS + (
                    'pairs', 'fresh', 'fallback', 'runs', 'descriptive_flips', 'member', 'representative', 'event',
                    'unit', 'items'), text
    blob = rp.canonical_bytes(plan) + rp.canonical_bytes(record)
    assert not any(token.encode() in blob for token in ids + planted)
    cases = {'item_id': {'note': ids[0]}, 'planted_text': {'x': 'has SECRET TEXT inside'},
             'long_string': {'x': 'y' * 65}, 'float': {'accuracy_points': 61.5}, 'forbidden_key': {'reply': None},
             'reason_outside_vocabulary': {'reason': 'some free text'}, 'verdict_outside_vocabulary': {'verdict': 'ok'}}
    for code, planted_doc in cases.items():
        assert code in rp.open_record_violations(planted_doc, item_ids=ids, texts=planted), code
        with pytest.raises(rp.OpenRecordViolation):
            rp.check_open_record(planted_doc, item_ids=ids, texts=planted)
    assert rp.open_record_violations({'detail': rp.replay_error_detail('exit_7'), 'failures': ['pass_exception']}) == []
    assert rp.open_record_violations({'hash': H('digits'), 'count': 3}, item_ids=['12345']) == []   # hex ids: exact


def test_names_arms_and_vocabulary_match_the_typed_code():
    from skillopt.execskill.typed import reads
    for event in rp.EVENTS:
        assert rp.arm_of(event) == reads.arm_of(event)
        for bench in ORDER:
            for smoke in (False, True):
                assert rp.read_unit_name(event, bench, smoke=smoke) == reads.unit_name(event, bench, smoke=smoke)
    for name in (rp.PLAN_FILE, rp.ALIAS_DIR, rp.ARCHIVE_DIR, rp.SMOKE_SEALED_DIR, rp.PLAN_UNIT):
        assert not any(word in name for word in FORBIDDEN_PATH_WORDS), name
    assert 'test' in rp.SEALED_DIR
    assert rp.record_kind('read-plan.json') == 'plan' and rp.record_kind('S3-alfworld.json') == 'alias'
    assert rp.record_kind('.read-plan.json.1.0123456789abcdef.part') is None
    assert len(set(rp.READ_PLAN_REASONS)) == len(rp.READ_PLAN_REASONS)
    assert rp.is_reason('replay_error:timeout') and not rp.is_reason('replay_error:free text')
    with pytest.raises(ValueError):
        rp.ReadPlanError('not a registered code')
    assert rp.step_of('C') == rp.step_of('C0') == 0 and rp.step_of('S4') == 4
    assert rp.registry_sha256({'run': H('a'), 'panel': 'x'}) == rp.registry_sha256({'run': H('b'), 'panel': 'x'})
    constants = dict(runtime={'k': 1}, worker_options={'w': 2}, nominal_tokens=None, machinery='main-v10')
    assert rp.run_constants_sha256('searchqa', **constants) != rp.run_constants_sha256(
        'searchqa', **dict(constants, nominal_tokens=4096))


# ---- review fixes F1, F2, F4 and the checks the review found untested (F3) ---------------------------------
def test_a_record_mounted_through_another_arm_never_gives_the_event_an_identity():
    """R16, K-A (review F1): C0's items mounted through arm F (the S1 path) while the event's own frozen state is
    reported. Without the arm check C0 joins {C, S1..S5} > S5 on every bench and the no-skill row is aliased."""
    world = World(base='historical')
    for bench in ORDER:
        world.mount_as[(bench, 'C0')] = 'S1'
    plan = world.plan()
    for bench in ORDER:
        row = plan['benches'][bench]['events']['C0']
        assert (row['status'], row['reason'], row['identity_list_sha256']) == (
            'fallback', 'identity_disagreement', None), bench
        assert classes(plan, bench) == [(['C0'], 'C0'), (['C'] + S, 'S5')], bench
    assert plan['counts'] == {'pairs': 35, 'fresh': 10, 'alias': 25, 'fallback': 5}
    # per item: the capture-mounted record must carry the event's arm; only the three read arms are accepted (R11)
    identity, mounted, _system = world.mount('searchqa', 'S1', world.ids['searchqa'][0], 1)
    hashes = dict(public_sha256=H('public'), view_sha256=H('view'))
    assert rp.item_components(identity, mounted, arm='F', **hashes)['system_sha256'] == identity['system_card_sha256']
    for arm, code in (('C0', 'identity_disagreement'), ('C', 'identity_disagreement'),
                      ('cand_card', 'identity_exception'), (None, 'identity_exception')):
        with pytest.raises(rp.ReadPlanError) as raised:
            rp.item_components(identity, mounted, arm=arm, **hashes)
        assert raised.value.code == code, arm
    with pytest.raises(rp.ReadPlanError) as raised:
        rp.item_components(identity, {k: v for k, v in mounted.items() if k != 'arm'}, arm='F', **hashes)
    assert raised.value.code == 'identity_disagreement'


def test_identities_computed_from_another_frozen_state_never_alias():
    """K-A (review F1, optional part): S2's identities computed from S3's frozen state, an off-by-one load that the
    integration reports truthfully. True states: s1 = s2 without a card, s3..s5 with one. R41 on S5 would pass, so
    only the binding of each entry to the plan's frozen[event] keeps S2 from a false alias to S5."""
    world = World(base='historical')
    world.learn('officeqa', 3, type='qa', card='LEARNED CARD')
    world.loaded[('officeqa', 'S2')] = 'S3'
    files = world.files()
    plan = files[rp.PLAN_FILE]
    row = plan['benches']['officeqa']['events']['S2']
    assert (row['status'], row['reason'], row['identity_list_sha256']) == ('fallback', 'identity_disagreement', None)
    assert classes(plan, 'officeqa') == [(['C0'], 'C0'), (['C', 'S1'], 'S1'), (['S2'], 'S2'),
                                         (['S3', 'S4', 'S5'], 'S5')]
    identities, inputs = files[rp.identities_name('officeqa')], files[rp.inputs_name('officeqa')]
    assert all(rp.entry_mounted_from(identities['events'][e], world.header['frozen'][e]) for e in rp.EVENTS)
    # a stored record checked against other frozen states, and a plan header that names other states
    other = frozen_receipts('other ')
    assert rp.verify_identities(identities, inputs=inputs, frozen=world.header['frozen']) is identities
    with pytest.raises(rp.ReadPlanError) as raised:
        rp.verify_identities(identities, inputs=inputs, frozen=other)
    assert raised.value.code == 'sealed_file_mismatch'
    benches = {b: {'inputs': files[rp.inputs_name(b)], 'identities': files[rp.identities_name(b)],
                   'registry_sha256': None, 'run_constants_sha256': H('constants ' + b)} for b in ORDER}
    assert rp.build_plan(**world.header, benches=benches) == plan
    with pytest.raises(rp.ReadPlanError) as raised:
        rp.build_plan(**dict(world.header, frozen=other), benches=benches)
    assert raised.value.code == 'sealed_file_mismatch'
    # an entry that names its own step but another library file is a disagreement too
    entries = {e: world.entry('officeqa', e) for e in rp.EVENTS}
    entries['S4'] = dict(entries['S4'], library_file_sha256=H('another library file'))
    record = rp.identities_record('G', 'officeqa', inputs, entries, frozen=world.header['frozen'])
    assert record['events']['S4']['reason'] == 'identity_disagreement'


def deeply_nested(depth=100000):
    value = []
    for _ in range(depth):
        value = [value]
    return value


def test_unreadable_bytes_and_records_raise_the_fixed_code():
    """R44 a, R80, R81 (review F2): bytes that parse but cannot be written back (an out-of-range number, a lone
    surrogate) or nest too deeply are unreadable records with the reader's fixed code, never a raw ValueError,
    UnicodeEncodeError or RecursionError; the verify functions map a too deeply nested record the same way."""
    unreadable = [b'{\n "a": 1e999\n}\n', b'{\n "a": "\\ud800"\n}\n',
                  b'{"a": ' + b'[' * 100000 + b']' * 100000 + b'}\n']
    readers = [(rp.plan_from_bytes, 'plan_file_mismatch'),
               (lambda data: rp.sealed_from_bytes(data, 'inputs'), 'inputs_mismatch'),
               (lambda data: rp.sealed_from_bytes(data, 'identities'), 'sealed_file_mismatch'),
               (lambda data: rp.alias_from_bytes(data, {}), 'read_alias_invalid')]
    for data in unreadable:
        for read, code in readers:
            with pytest.raises(rp.ReadPlanError) as raised:
                read(data)
            assert raised.value.code == code
    nested = deeply_nested()
    alfworld = World().inputs('alfworld')
    alfworld['alfworld_views'][0] = {'deep': nested}
    identities = {'version': rp.IDENTITIES_VERSION, 'chain': 'G', 'bench': 'searchqa', 'item_ids': ['a'],
                  'inputs_sha256': H('inputs'), 'events': {}, 'record_sha256': H('record')}
    cases = [(lambda: rp.verify_plan(dict({k: None for k in rp.PLAN_KEYS}, plan_sha256=H('x'), counts=nested)),
              'plan_self_check'),
             (lambda: rp.verify_alias(dict({k: None for k in rp.ALIAS_KEYS}, record_sha256=H('x'), check=nested), {}),
              'read_alias_invalid'),
             (lambda: rp.verify_inputs(alfworld), 'inputs_mismatch'),
             (lambda: rp.verify_identities(identities, inputs=nested), 'sealed_file_mismatch')]
    for verify, code in cases:
        with pytest.raises(rp.ReadPlanError) as raised:
            verify()
        assert raised.value.code == code


def test_errors_survive_pickle_and_copy():
    """R16, R31 (review F4): the error classes rebuild from their arguments, so a per-item error carried back from a
    process pool is still a fallback with its code, never a broken pool."""
    errors = [rp.ReadPlanError('identity_exception'), rp.ReadPlanError('identity_exception', 'mount record'),
              rp.WriteOnceMismatch('read-plan.json'), rp.OpenRecordViolation(['float', 'item_id'])]
    for error in errors:
        for back in (pickle.loads(pickle.dumps(error)), copy.deepcopy(error), copy.copy(error)):
            assert type(back) is type(error) and back.args == error.args and vars(back) == vars(error)
            assert str(back) == str(error)
    assert (str(errors[0]), str(errors[1]), errors[1].code) == (
        'identity_exception', 'identity_exception: mount record', 'identity_exception')
    assert str(errors[2]) == 'write_once: other bytes already stored under read-plan.json'
    assert str(errors[3]) == 'open record violations: float, item_id' and errors[3].codes == ('float', 'item_id')


def test_post_read_check_compares_the_planned_first_request():
    """R41, RP3 (review F3, M1): for an item without offered programs the plan holds its first request, and a
    representative cell whose first request differs, or that holds none, is unequal (the direct proof of members)."""
    world = World()
    expected = rp.expected_for_check(world.files()[rp.identities_name('searchqa')], 'S5')
    assert all(want['first_request'] is not None and not want['programs'] for want in expected)
    rows = []
    for item, want in zip(world.ids['searchqa'], expected):
        _identity, mounted, _system = world.mount('searchqa', 'S5', item, 1)
        rows.append({'mount': mounted, 'public_hash': want['public_sha256'],
                     'request_sha256': [want['first_request'], H('a later send')]})
    observed = [rp.observed_from_row(row, {}.__getitem__) for row in rows]
    assert rp.post_read_check(expected, observed) == {'items': 3, 'equal': 3, 'unequal': 0}
    observed[1] = rp.observed_from_row(dict(rows[1], request_sha256=[H('another first request')]), {}.__getitem__)
    observed[2] = rp.observed_from_row(dict(rows[2], request_sha256=[]), {}.__getitem__)
    assert rp.post_read_check(expected, observed) == {'items': 3, 'equal': 1, 'unequal': 2}
    assert not rp.check_passed(rp.post_read_check(expected, observed), 3)


def test_offered_ids_must_agree_between_the_identity_and_the_mount_record():
    """R16 (review F3, M4): mount_identity and the capture-mounted record name the same offered programs, in the
    same order; any other list is identity_disagreement."""
    identity = {'system_card_sha256': H('system'), 'programs_offered': [['p', H('body p')], ['q', H('body q')]],
                'forced': None}
    mounted = {'arm': 'F', 'system_card_sha256': H('system'), 'programs_offered': ['p', 'q'],
               'selection': {'attempts': [H('selection')]}, 'type': 't', 'source': None, 'unknown_reason': None,
               'card_skill': None}
    hashes = dict(arm='F', public_sha256=H('public'), view_sha256=H('view'))
    assert rp.item_components(identity, mounted, **hashes)['offered'] == ['p', 'q']
    for offered in (['q', 'p'], ['p'], ['p', 'q', 'r'], ['p', 'x']):
        with pytest.raises(rp.ReadPlanError) as raised:
            rp.item_components(identity, dict(mounted, programs_offered=offered), **hashes)
        assert raised.value.code == 'identity_disagreement', offered


def test_components_must_carry_the_stored_view_hashes():
    """R78 (review F3, M6): an entry whose components carry another view hash than the sealed inputs record is a
    fallback identity_exception in the pass, and a stored record holding one verifies only without its inputs."""
    world = World()
    inputs = world.inputs('officeqa')
    entries = {e: world.entry('officeqa', e) for e in rp.EVENTS}
    changed = deepcopy(entries['S2'])
    components = changed['components'][0]
    components['view_sha256'] = H('another view')
    changed['identity'][0] = rp.item_record('officeqa', components, first_request=changed['first_request'][0])[
        'identity']
    record = rp.identities_record('G', 'officeqa', inputs, dict(entries, S2=changed), frozen=world.header['frozen'])
    assert (record['events']['S2']['status'], record['events']['S2']['reason']) == ('fallback', 'identity_exception')
    assert record['events']['S2']['identity'] is None
    assert [e for e in rp.EVENTS if record['events'][e]['status'] != 'ok'] == ['S2']
    good = rp.identities_record('G', 'officeqa', inputs, entries, frozen=world.header['frozen'])
    stored = deepcopy(good)
    stored['events']['S2'] = changed
    stored = {k: v for k, v in stored.items() if k != 'record_sha256'}
    stored['record_sha256'] = rp.canonical_sha256(stored)
    assert rp.verify_identities(stored) is stored
    with pytest.raises(rp.ReadPlanError) as raised:
        rp.verify_identities(stored, inputs=inputs)
    assert raised.value.code == 'sealed_file_mismatch'


def test_identities_are_bound_to_their_inputs_record():
    """3.3, R78 (review F3, M7): a stored identities record verifies only with its own inputs record: the same file
    hash, ids, chain and bench."""
    world = World()
    files = world.files()
    identities, inputs = files[rp.identities_name('officeqa')], files[rp.inputs_name('officeqa')]
    assert rp.verify_identities(identities, inputs=inputs) is identities
    other_vectors = rp.inputs_record('G', 'officeqa', inputs['item_ids'], inputs['view_sha256'],
                                     vectors=[[[0.5, 0.5, float(k)] for k in range(3)] for _run in range(2)])
    other_chain = rp.inputs_record('D', 'officeqa', inputs['item_ids'], inputs['view_sha256'],
                                   vectors=inputs['vectors'])
    for other in (other_vectors, other_chain, files[rp.inputs_name('searchqa')]):
        with pytest.raises(rp.ReadPlanError) as raised:
            rp.verify_identities(identities, inputs=other)
        assert raised.value.code == 'sealed_file_mismatch'
    with pytest.raises(rp.ReadPlanError) as raised:
        rp.sealed_from_bytes(rp.canonical_bytes(identities), 'identities', inputs=other_vectors)
    assert raised.value.code == 'sealed_file_mismatch'


def test_a_stored_ok_entry_that_breaks_RP3_is_a_fallback():
    """RP3, R19 (review F3, M10): an entry marked ok whose first requests break RP3 is inconsistent, so it is a
    fallback identity_exception and the other members keep their class: a missing hash where one is required, or a
    hash where none may be (an item with offered programs)."""
    world = World()
    entries = {e: world.entry('officeqa', e) for e in rp.EVENTS}
    missing = deepcopy(entries['S3'])
    missing['first_request'][0] = None
    record = rp.identities_record('G', 'officeqa', world.inputs('officeqa'), dict(entries, S3=missing),
                                  frozen=world.header['frozen'])
    assert (record['events']['S3']['status'], record['events']['S3']['reason']) == ('fallback', 'identity_exception')
    assert [e for e in rp.EVENTS if record['events'][e]['status'] != 'ok'] == ['S3']
    world.learn('officeqa', 1, type='qa', programs=[('p', H('body'), 'p', 'description')])
    entries = {e: world.entry('officeqa', e) for e in rp.EVENTS}
    extra = deepcopy(entries['S4'])
    extra['first_request'][0] = H('a first request beside offered programs')
    record = rp.identities_record('G', 'officeqa', world.inputs('officeqa'), dict(entries, S4=extra),
                                  frozen=world.header['frozen'])
    assert (record['events']['S4']['status'], record['events']['S4']['reason']) == ('fallback', 'identity_exception')
    assert [e for e in rp.EVENTS if record['events'][e]['status'] != 'ok'] == ['S4']


def test_alfworld_stored_views_are_bound_to_their_view_hashes():
    """R78, 3.3 (review F3, M19): the ALFWorld views a replay loads from the inputs record must hash to the stored
    view hashes, at build time and in a resealed record."""
    world = World()
    ids = world.ids['alfworld']
    views = [world.views['alfworld'][i] for i in ids]
    hashes = [rp.view_sha256(v) for v in views]
    assert rp.inputs_record('G', 'alfworld', ids, hashes, alfworld_views=views)['alfworld_views'] == views
    with pytest.raises(ValueError):
        rp.inputs_record('G', 'alfworld', ids, [H('another view')] + hashes[1:], alfworld_views=views)
    changed = world.inputs('alfworld')
    changed['alfworld_views'][0]['body'] = 'ANOTHER VIEW'
    changed['views_sha256'] = rp._views_sha256(changed['view_sha256'], changed['alfworld_views'])
    changed = {k: v for k, v in changed.items() if k != 'record_sha256'}
    changed['record_sha256'] = rp.canonical_sha256(changed)
    with pytest.raises(rp.ReadPlanError) as raised:
        rp.verify_inputs(changed)
    assert raised.value.code == 'inputs_mismatch'


def test_frozen_entries_must_name_the_step_of_their_event():
    """3.2, R27 (review F3, M20): a resealed plan whose frozen S3 entry names step 2 is refused (plan_self_check)."""
    plan = World().plan()
    changed = deepcopy(plan)
    changed['frozen']['S3']['step'] = 2
    changed = {k: v for k, v in changed.items() if k != 'plan_sha256'}
    changed['plan_sha256'] = rp.canonical_sha256(changed)
    with pytest.raises(rp.ReadPlanError) as raised:
        rp.verify_plan(changed)
    assert raised.value.code == 'plan_self_check'


def test_two_items_that_swap_system_texts_give_other_lists():
    """T8 (a): items a and b swap their system texts between S3 and S4, so the lists differ and the events split;
    the list hashes pair every id with its own value, so a swap of two identities or first requests is another
    list."""
    world = World(base='historical')
    a, b, _c = world.ids['officeqa']
    for event in S:
        swap = event in ('S4', 'S5')
        world.state[('officeqa', event, a)] = {'type': 'qa', 'card': 'CARD B' if swap else 'CARD A'}
        world.state[('officeqa', event, b)] = {'type': 'qa', 'card': 'CARD A' if swap else 'CARD B'}
    plan = world.plan()
    rows = plan['benches']['officeqa']['events']
    assert rows['S3']['identity_list_sha256'] != rows['S4']['identity_list_sha256']
    assert classes(plan, 'officeqa') == [(['C0'], 'C0'), (['C'], 'C'), (['S1', 'S2', 'S3'], 'S3'), (['S4', 'S5'], 'S5')]
    ids = world.ids['officeqa']
    values = [H('value %d' % k) for k in range(3)]
    swapped = [values[1], values[0], values[2]]
    assert rp.identity_list_sha256('officeqa', ids, values) != rp.identity_list_sha256('officeqa', ids, swapped)
    assert rp.first_request_list_sha256('officeqa', ids, values) != rp.first_request_list_sha256('officeqa', ids,
                                                                                                 swapped)
