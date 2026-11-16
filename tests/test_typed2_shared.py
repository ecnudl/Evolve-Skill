"""typed-v2 step 5x (owner decision D16, with D5, O1, O5, O6, D17): shared-type learning and gating.

When the home type of step k also holds sources of earlier benches (the other members M), (a) the card writer (both
rounds) and the engineer also see each member bench's base card and examples from its LEARN slice under the current
mount (``s<k>/member-<b'>-outcomes``; after an accepted card ``-outcomes-card``), capped at the current bench's counts,
in a block labelled with its source, with a sentence naming the member sources and the acceptance rule; (b) a
candidate that passed the home rule is accepted only if no_regress holds on every member bench's gate slice (R runs
per item and arm; member baseline = the current mount F, after an accepted card that card's member runs; reason
``member_harm`` naming the bench); (c) the records store every member check and ``gates.recompute`` reproduces them;
the readout shows the related gain; (d) a type of one bench changes nothing.

Fixtures: the fake chain of ``tests/test_typed_chain.py`` (SearchQA at step 1, OfficeQA at step 2 merging into
SearchQA's type) and the smoke's scripted services through the REAL mount, writers and reads (requests).

Golden values (``GOLDEN_SINGLE``): two scenarios in which OfficeQA's no-harm check fails, so every type holds one
bench; per run the digests of every request, cell, done unit, file path and decision record (time keys and the
ledger stripped). Computed on 2026-11-12 with the 5w tree BEFORE any 5x edit (twice under Python 3.13, once under
3.10, equal); the 5x tree must reproduce them byte for byte, apart from the coord-1 wording of the [import] row of the
program-writer texts (fix-b; mapped back by ``undo_coord1`` in the requests and, through ``coord1_hashes``, in the
request hashes the decision records name). The 5w tree was never committed: the tie of these scenarios to committed
old code is ``tests/test_typed2_base.py::test_format_base_one_bench_requests_are_cdf85b6s`` (fix-b, rb-requests F1).
"""
import hashlib
import json
import shutil
import tempfile
from collections import Counter
from pathlib import Path

import pytest

from skillopt.coevo5.roles import message_bytes
from skillopt.execskill import engineer_payload, profiles, v225_cards
from skillopt.execskill.typed import (ORDER, chain, engineer_prompt, gates, gatestats, mount, readout, smoke,
                                      tasktypes as typing_, units, writers)
from tests.test_typed2_base import (Capture, cell_rows, coord1_hashes, coord1_touched, digest, exact_embedder, remap,
                                    request_rows, searchqa_cards_fail)
from tests.test_typed_chain import FakeWriters, build, recovery

R = 3
NEUTRAL = Path('/tmp/typed2-neutral')
TIME_KEYS = {'at', 'accepted_at', 'updated', 'started', 'saved_at', 'frozen_at', 'created_at', 'seconds', 'applied_at',
             'bound_at'}
GOLDEN_SINGLE = {  # the 5w tree (before 5x), Python 3.13 twice and 3.10 once: equal
    'smoke': {'types': ['t01', 't02', 't03', 't04', 't05'], 'n_requests': 260, 'n_cells': 233, 'n_units': 82,
              'n_files': 712,
              'requests': '391aa0a2ff70d5443528b4a77f00c23c67e5abf69d7d94bee8e319816b2ee358',
              'cells': 'f6e2c9165b5e904afb5e78be003180445af391ed0b57a73576eeaff7ce3ed0a8',
              'units': 'adef57568dce48f521dba3dc96b0d2681cfcc70e3e662d04ca49e578ae7db8be',
              'files': '0a7b0b1b4df16c021b90e3ba8ad3d7c650d7294840238fb926fafb82a31ff382',
              'decisions': '95a7929fc93ebf382558804bf9bd06f33144cc9b163afda67641b49246a62fbe'},
    'default': {'types': ['t01', 't02', 't03', 't04', 't05'], 'n_requests': 292, 'n_cells': 244, 'n_units': 85,
                'n_files': 762,
                'requests': '28933c30571064330f87a8d4c444a02486ba565c82b96d582d9cd9b84a9be5a6',
                'cells': '692fc3301d3d1cc387e8bb016ed4e25970357eba6180b02150e66c91cd75a256',
                'units': 'd3aa4ff7a633bbb278f4408f31c7fa5211f57c41620422ae847b0abe47a16ef6',
                'files': 'fb0619b0259740711fbba2b4ae4ed21d978ba155e7741b2ac975270e1c8ca4ae',
                'decisions': 'b8a191db6d660e4bcb77d0f70bbf43c23fcd184dd3c49fb188cb22b6baab32ae'},
}
SENTENCE_SHA256 = {  # the four D16 sentences, pinned (a change is a visible change of the writer requests)
    'writers.MEMBERS_MEANING': 'ed38a8dacee55c254e8ff49adac5132c03e0e2c2e9459e2ba2023c5cf3e8cc9e',
    'writers.MEMBER_BASE_MEANING': 'ad353a944831667a7b185e35b84f99c1a17ca74d929646a69fd9988b89141a23',
    'engineer_prompt.MEMBERS_MEANING': '13a5a9326ac9c7856c0812c0087feb47564be3865d4a34dacbd1d22c4977ac9a',
    'engineer_prompt.MEMBER_BASE_MEANING': '819540410008d05c7df3ea7f497746858183d8dae3f5b39143dd62bbc97f3c2a',
}


@pytest.fixture
def tmp_path():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='shared-', dir=NEUTRAL))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ---- (d) a type of one bench changes nothing ----------------------------------------------------------------------
def officeqa_own_type(bench, item_id, mounted):
    """OfficeQA items routed to SearchQA's type fail: its no-harm check fails and it opens its own type."""
    if bench == 'officeqa' and mounted.get('type') == 't01':
        return 'fail'
    return smoke.default_outcome(bench, item_id, mounted)


def default_own_type(bench, item_id, mounted):
    if bench == 'officeqa' and mounted.get('type') == 't01':
        return 'fail'
    return searchqa_cards_fail(bench, item_id, mounted)


SINGLE = {'smoke': (smoke.SMOKE_LIMITS, officeqa_own_type), 'default': (chain.DEFAULT_LIMITS, default_own_type)}


def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in TIME_KEYS}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def real_run(root, *, limits, outcomes, order=None, base_card=None):
    """The fake chain through the REAL mount, writers and reads (scripted replies, exact axis embeddings)."""
    manifest = smoke.synthetic_manifest() if base_card is None else smoke.synthetic_manifest(base_card=base_card)
    script = Capture({'outcomes': outcomes} if not isinstance(outcomes, dict) else outcomes)
    services = smoke.fake_services(root, 'G', manifest, scripted=script)
    services.embed = exact_embedder
    services.slices = smoke.smoke_slices(services.items, services.slices)
    services.limits = dict(limits)
    if order is not None:
        services.order = order
    return chain.run(root, 'G', services=services, sleep=lambda s: None), script, services


@pytest.mark.parametrize('name', sorted(GOLDEN_SINGLE))
def test_one_bench_per_type_sends_every_request_unit_cell_and_record_of_5w(tmp_path, name):
    """Addendum D16 (d): with one bench per type nothing changes. Every request (purpose, unit, sha256 of system NUL
    user), every cell (unit, label, item, request and selection hashes), every done unit in order, every file path
    and every decision record (time keys stripped) equals the 5w tree's, byte for byte, with the coord-1 wording of
    the program-writer texts mapped back (it touches the program-writer requests and nothing else)."""
    root = tmp_path / ('single-%s-smoke' % name)
    limits, outcomes = SINGLE[name]
    state, script, _ = real_run(root, limits=limits, outcomes=outcomes)
    assert state['complete'] and state['paused'] is None
    base = root / 'G'
    types = [json.loads((base / ('s%d' % k) / 'typing' / 'typing.json').read_text())['type'] for k in range(1, 6)]
    requests, cells = request_rows(script, coord1=True), cell_rows(root, relabel=False)
    assert coord1_touched(script.requests) == ({'program_writer'}, True)
    files = sorted(str(p.relative_to(base)) for p in base.rglob('*') if p.is_file())
    # typed-v2 step 6s (DESIGN 3.6): every freeze adds its write-once receipt s<k>/frozen.json (s0 .. s5) and nothing
    # else; the receipts are pinned here and the 5w file list holds for the rest
    receipts = ['s%d/frozen.json' % k for k in range(6)]
    assert [f for f in files if f.endswith('frozen.json')] == receipts
    files = [f for f in files if f not in receipts]
    # typed-v2 step rp-int (read-plan R75, T25): every start writes the write-once solver-settings.json, under 'full'
    # too; pinned here and taken out, so the 5w file list holds for the rest
    assert 'solver-settings.json' in files
    files = [f for f in files if f != 'solver-settings.json']
    records = []
    for k in range(1, 6):
        doc = json.loads((base / ('s%d' % k) / 'decisions.json').read_text())
        doc.pop('ledger', None)
        # typed-v3 (T1): the record carries the new version and evidence labels, and the hash of its type map, whose
        # record names the module version; mapped back to typed-v2's, the 5w digests hold byte for byte (the version
        # switch changes nothing else in a typed-v2 style run)
        assert (doc['version'], doc['evidence']) == ('typed-v3', 'typed_v3_smoke')
        doc.update(version='typed-v2', evidence='typed_v2_smoke')
        frozen = json.loads((base / ('s%d' % k) / 'typing' / 'typemap.json').read_text())
        frozen.pop('record_sha256')
        assert frozen['module'] == 'typed-v3' and doc['typing']['typemap_sha256'] == typing_._sha(frozen)
        doc['typing']['typemap_sha256'] = typing_._sha({**frozen, 'module': 'typed-v2'})
        records.append(strip(doc))
        assert 'shared_type' not in doc and not any('shared_with' in row for row in doc['cards'] + doc['programs'])
    found = {'types': types, 'n_requests': len(requests), 'requests': digest(requests), 'n_cells': len(cells),
             'cells': digest(cells), 'n_units': len(state['done_units']), 'units': digest(state['done_units']),
             'n_files': len(files), 'files': digest(files),
             'decisions': digest(remap(records, coord1_hashes(script.requests)))}
    assert found == GOLDEN_SINGLE[name]
    assert not any('member' in unit for unit in state['done_units'])
    assert not any('"members"' in user for purpose, _, _, user in script.requests if purpose != 'solver')


# ---- (a) the writers' member block, through the real writers --------------------------------------------------------
OFFICEQA_CARD = ('- Read every part of the task before answering.\n'
                 '- Check the unit of every quantity in the table before you compute.\n'
                 '- Give exactly one final answer in the required format.')
MARK = 'Check the unit of every quantity'


def card_by_request(system, user):
    """The scripted card writer: OfficeQA's request (it carries the member block) gets OFFICEQA_CARD."""
    return OFFICEQA_CARD if '"members"' in user else smoke.DEFAULT_CARD


def officeqa_card_harms_searchqa(bench, item_id, mounted):
    """OfficeQA's card helps at home and harms SearchQA; everything else is flat (so OfficeQA merges at step 2)."""
    helped = MARK in (mounted.get('card_text') or '')
    if bench == 'officeqa':
        return 'pass' if helped else 'fail'
    if bench == 'searchqa':
        return 'fail' if helped else 'pass'
    return smoke.default_outcome(bench, item_id, mounted)


def head(source, base_card, meaning, bench='searchqa'):
    """A member source block's head: its label, its format block always, its base card only where the base adds to the
    format block (as 5b shows the current bench's: never under 'format')."""
    found = {'source': source, 'format_block': mount.format_block(bench)}
    if mount.base_text(bench, base_card) != mount.format_block(bench):
        found['base_card'] = {'meaning': meaning, 'text': mount.historical_card(bench)}
    return found


def json_requests(script, purpose, prefix):
    out = []
    for kind, unit, system, user in script.requests:
        if kind == purpose and unit and unit.startswith(prefix):
            try:
                out.append((unit, json.loads(user)))
            except ValueError:
                continue  # a retry appends a sentence after the JSON
    return out


@pytest.mark.parametrize('base_card', ['format', 'historical'])
def test_step_two_writer_requests_hold_the_labelled_member_block_and_no_gate_item(tmp_path, base_card):
    """OfficeQA joins SearchQA's type at step 2. Both card rounds and the engineer see SearchQA's block: labelled with
    its source, its base card (D17), its LEARN-slice examples (at most as many as OfficeQA's), and the sentence
    naming the source and the rule; round 2's summary adds the member check (counts and points, the source label,
    never a bench name). The current bench's part keeps the 5w keys; no gate or panel item of any bench reaches a
    writer; step 1 (a type of one bench) sends no member block."""
    root = tmp_path / 'req-smoke'
    state, script, services = real_run(root, limits=chain.DEFAULT_LIMITS, order=('searchqa', 'officeqa'),
                                       base_card=base_card,
                                       outcomes={'outcomes': officeqa_card_harms_searchqa,
                                                 'replies': {'card_writer': card_by_request}})
    assert state['complete'], state['paused']
    typing = json.loads((root / 'G' / 's2' / 'typing' / 'typing.json').read_text())
    assert typing['type'] == 't01' and not typing['new_type']  # OfficeQA merged into SearchQA's type
    sid = typing_.source_id(chain._pool_pin(services.manifest, 'searchqa'))
    learn_q = services.slices['searchqa']['learn']
    hidden = [i for b in ORDER for part in ('gate', 'panel') for i in services.slices[b][part]]
    cards_s2 = json_requests(script, 'card_writer', 's2/')
    assert [unit for unit, _ in cards_s2] == ['s2/card-r1', 's2/card-r2']
    for unit, request in cards_s2:
        block = request['members']
        assert block['meaning'] == writers.MEMBERS_MEANING % sid and sid in block['meaning']
        assert [s['source'] for s in block['sources']] == [sid]
        source = block['sources'][0]
        assert {k: v for k, v in source.items() if k != 'examples'} == head(sid, base_card, writers.MEMBER_BASE_MEANING)
        assert source['examples'] and all(any(i in row['view'] for i in learn_q) for row in source['examples'])
        assert len(source['examples']) <= len(request['examples'])  # at most as many as the current bench's
        assert set(request) - {'members'} == {'request', 'task_card', 'format_block', 'current_card', 'card_rules',
                                              'examples', 'evidence'} | ({'base_card'} if base_card == 'historical'
                                                                         else set()) | (
            {'previous_card', 'result'} if unit.endswith('r2') else set())
        assert all('officeqa-l' in row['view'] for row in request['examples'])  # the home part: OfficeQA's own
    summary = cards_s2[1][1]['result']
    assert summary['failing_clause'] == 'member_harm' and summary['member_rule'] == writers.MEMBER_RULE
    (check,) = summary['member_check']
    assert check['source'] == sid and check['decision'] == 'harm' and check['broken'] == 3 and check['fixed'] == 0
    assert 'searchqa' not in json.dumps(summary)  # labels and counts only
    engineers = json_requests(script, 'program_writer', 's2/programs')
    assert engineers and all('members' in request for _, request in engineers[:1])
    block = engineers[0][1]['members']
    assert block['meaning'] == engineer_prompt.MEMBERS_MEANING % sid
    (source,) = block['sources']
    assert {k: v for k, v in source.items() if k in ('source', 'format_block', 'base_card')} == head(
        sid, base_card, engineer_prompt.MEMBER_BASE_MEANING)
    assert source['trajectories'] and all(any(i in t['calls'][0]['user'] for i in learn_q)
                                          for t in source['trajectories'])
    for purpose in ('card_writer', 'program_writer'):
        for kind, unit, system, user in script.requests:
            if kind == purpose:
                assert not any(item in user for item in hidden), (unit, purpose)  # no gate / panel item, any bench
                assert ('"members"' in user) == unit.startswith('s2/'), unit  # step 1: a type of one bench
    decision = json.loads((root / 'G' / 's2' / 'card-r1' / 'decision.json').read_text())
    assert decision['reason'] == 'member_harm' and decision['member_harm'] == 'searchqa'
    assert chain.recompute_decision(decision) == decision


# ---- (b), (c) the gate, through the fake chain ----------------------------------------------------------------------
def shared_outcome(home='gain', member='hold'):
    """Step 1 SearchQA: its card passes the even items. Step 2 OfficeQA joins SearchQA's type (its no-harm check
    holds: no SearchQA skill helps or harms it). ``home``: 'gain' = OfficeQA's card passes OfficeQA's even items,
    'none' = it changes nothing. ``member``: on SearchQA items OfficeQA's card passes every item ('hold': a related
    gain on the odd items) or fails every item ('harm'). A program passes everywhere."""
    def outcome(bench, item_id, mounted):
        text, even = mounted.get('card_text') or '', int(item_id[-1]) % 2 == 0
        if mounted.get('enabled'):
            return 'pass'
        if bench == 'searchqa':
            if 'officeqa' in text:
                return 'pass' if member == 'hold' else 'fail'
            return 'pass' if 'searchqa' in text and even else 'fail'
        return 'pass' if home == 'gain' and 'officeqa' in text and even else 'fail'
    return outcome


def counting(services):
    seen, real = Counter(), services.solve_fn

    def solve(bench, item, mounted, **kwargs):
        seen[(kwargs['unit'], item['task_id'], mounted['arm'], kwargs['tag'])] += 1
        return real(bench, item, mounted, **kwargs)
    services.solve_fn = solve
    return seen


def fake_run(root, *, home='gain', member='hold', proposals=None, writers_=None):
    services, modules, script = build(root, order=('searchqa', 'officeqa'), proposals=proposals, writers=writers_,
                                      scripted={'outcomes': shared_outcome(home, member)})
    seen = counting(services)
    return chain.run(root, 'G', services=services, sleep=lambda s: None), services, modules, seen


def records_of(chain_dir):
    """Every stored gate record with statistics: noise, no-harm, card rounds and programs (their member checks
    inside), from decisions.json and from the unit copies."""
    found = []
    for path in sorted(Path(chain_dir).glob('s[0-9]*/decisions.json')):
        doc = json.loads(path.read_text())
        found += [doc['noise']] + list(doc['typing']['no_harm'])
        found += [row for row in doc['cards'] + doc['programs'] if 'per_item' in row]
    found += [json.loads(p.read_text()) for p in sorted(Path(chain_dir).rglob('decision.json'))]
    return [row for row in found if 'per_item' in row]


def member_cells(chain_dir, k=2):
    return {p.parent.parent.name: len(list(p.parent.glob('*.json')))
            for p in sorted((Path(chain_dir) / ('s%d' % k)).glob('*member*/cells/*.json'))}


def test_a_card_that_gains_at_home_and_regresses_on_the_member_is_rejected_member_harm(tmp_path):
    state, services, modules, seen = fake_run(tmp_path, member='harm')
    assert state['complete'], state['paused']
    chain_dir = tmp_path / 'G'
    d2 = json.loads((chain_dir / 's2' / 'decisions.json').read_text())
    assert d2['typing']['type'] == 't01' and not d2['typing']['new_type']
    sid = typing_.source_id(chain._pool_pin(services.manifest, 'searchqa'))
    for j, row in enumerate(d2['cards'], 1):
        assert (row['accepted'], row['reason'], row['member_harm']) == (False, 'member_harm', 'searchqa')
        assert row['gain_points'] > row['tau_points'] and row['better'] > row['worse']  # it passed the home rule
        # fix-c (addendum RP15): a source member, all 3 of its gate items routed into the home type (pin moved on
        # purpose: the record now names the member kind and the routed gate-item count)
        assert row['shared_with'] == [{'bench': 'searchqa', 'source': sid, 'member': 'source', 'routed_gate_items': 3}]
        (check,) = row['members']
        assert check['kind'] == 'member' and check['bench'] == 'searchqa' and not check['no_regress']
        assert (check['n'], check['repeats'], check['difference_sum'], check['worse'], check['tau_points']) == (
            3, R, -6, 2, 3.0)
        assert check['units'] == {'baseline': 's2/member-searchqa-base', 'candidate': 's2/card-r%d-member-searchqa' % j}
        assert check['labels'] == {'baseline': ['F#1', 'F#2', 'F#3'],
                                   'candidate': ['cand_card#1', 'cand_card#2', 'cand_card#3']}
        assert check['baseline_selected'] is False and check['cells'] == 3 * R
    step1_card = json.loads((chain_dir / 's1' / 'typemap.json').read_text())['types']['t01']['card']
    assert json.loads((chain_dir / 's2' / 'typemap.json').read_text())['types']['t01']['card'] == step1_card
    # the member base ran once (R runs per gate item), shared by both rounds
    assert member_cells(chain_dir) == {'member-searchqa-outcomes': 2, 'member-searchqa-base': 3 * R,
                                       'card-r1-member-searchqa': 3 * R, 'card-r2-member-searchqa': 3 * R}
    assert all(count == 1 for count in seen.values())
    for record in records_of(chain_dir):
        assert chain.recompute_decision(record) == record


def test_a_card_that_gains_at_home_and_holds_on_the_member_is_accepted_with_its_related_gain(tmp_path):
    state, services, modules, seen = fake_run(tmp_path, member='hold')
    assert state['complete'], state['paused']
    chain_dir = tmp_path / 'G'
    d2 = json.loads((chain_dir / 's2' / 'decisions.json').read_text())
    (row,) = d2['cards']
    assert (row['accepted'], row['reason'], row['member_harm']) == (True, 'accepted', None)
    (check,) = row['members']
    assert check['no_regress'] and check['difference_sum'] == 3 and check['better'] == 1 and check['worse'] == 0
    assert check['gain_points'] == pytest.approx(100 / 3)
    skill = json.loads((chain_dir / 's2' / 'card-r1' / 'skill.json').read_text())['skill']
    assert skill['home_type'] == 't01'
    assert json.loads((chain_dir / 's2' / 'typemap.json').read_text())['types']['t01']['card'] == skill['skill_id']
    # the readout shows the home gain and the related gain (informational)
    doc = readout.chain_readout(tmp_path, 'G', order=('searchqa', 'officeqa'))
    rows = [d for d in doc['steps'][2]['decisions'] if d['kind'] == 'card']
    assert rows[0]['mean_points'] == pytest.approx(200 / 3) and rows[0]['shared_with'] == ['searchqa']
    (related,) = rows[0]['related']
    assert related['bench'] == 'searchqa' and related['gain_points'] == pytest.approx(100 / 3) and related['no_regress']
    assert related['baseline'] == 's2/member-searchqa-base' and related['baseline_selected'] is False
    text = readout.markdown(doc)
    assert 'related gain pts' in text and '+33.3' in text and 'Related gain is informational' in text
    assert not any('related' in d for d in doc['steps'][1]['decisions'])  # step 1: a type of one bench
    for record in records_of(chain_dir):
        assert chain.recompute_decision(record) == record


def test_a_candidate_rejected_at_home_runs_no_member_cell(tmp_path):
    """Both card rounds fail the home rule (OfficeQA's card changes nothing at home): no member base and no member
    arm runs, only the writers' member examples (learn slice). A program that never fires is rejected at home too."""
    state, services, modules, seen = fake_run(tmp_path, home='none')
    assert state['complete'], state['paused']
    chain_dir = tmp_path / 'G'
    d2 = json.loads((chain_dir / 's2' / 'decisions.json').read_text())
    assert [(r['accepted'], r['reason'], r['members'], r['member_harm']) for r in d2['cards']] == [
        (False, 'gain_below_tau', [], None)] * 2
    assert member_cells(chain_dir) == {'member-searchqa-outcomes': 2}  # the writers' examples (learn slice)
    assert not any('member' in unit and 'outcomes' not in unit for unit in state['done_units'])
    assert not any(key[0].split('/')[1].startswith(('member-searchqa-base', 'card-r1-member', 'card-r2-member'))
                   for key in seen)
    # a home-rejected program as well: it never fires
    other = tmp_path / 'other'
    writers_ = FakeWriters(proposals={'officeqa': ['p-oq-1']})
    services, modules, script = build(other, order=('searchqa', 'officeqa'), writers=writers_,
                                      scripted={'outcomes': shared_outcome('none', 'hold'),
                                                'fires': lambda bench, item_id, procedure: False})
    state = chain.run(other, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    d2 = json.loads((other / 'G' / 's2' / 'decisions.json').read_text())
    (program,) = d2['programs']
    assert (program['accepted'], program['reason'], program['members']) == (False, 'never_fired', [])
    assert set(member_cells(other / 'G')) == {'member-searchqa-outcomes'}  # no base, no member arm of any candidate
    for record in records_of(other / 'G'):
        assert chain.recompute_decision(record) == record


def test_after_an_accepted_card_the_program_member_baseline_is_that_cards_member_runs(tmp_path):
    state, services, modules, seen = fake_run(tmp_path, member='hold', proposals={'officeqa': ['p-oq-1']})
    assert state['complete'], state['paused']
    chain_dir = tmp_path / 'G'
    d2 = json.loads((chain_dir / 's2' / 'decisions.json').read_text())
    assert d2['cards'][0]['accepted']
    (program,) = d2['programs']
    assert program['accepted'] and program['baseline_selected'] is True  # the home side: O5
    (check,) = program['members']
    assert check['baseline'] == {'unit': 's2/member-searchqa-outcomes-card', 'arm': 'F',
                                 'shared_from': {'unit': 's2/card-r1-member-searchqa', 'arm': 'cand_card'}}
    assert check['units'] == {'baseline': 's2/card-r1-member-searchqa', 'candidate': 's2/program-1-member-searchqa'}
    assert check['labels']['baseline'] == ['cand_card#1', 'cand_card#2', 'cand_card#3']
    assert check['baseline_selected'] is True and check['no_regress']
    card_check = d2['cards'][0]['members'][0]
    assert check['per_item'] == [[i, b, k] for (i, _, b), (_, _, k) in zip(card_check['per_item'], check['per_item'])]
    assert [row[1] for row in check['per_item']] == [row[2] for row in card_check['per_item']]  # the card's runs
    # the member's outcomes-card unit ran its learn cells only: its gate arm is the card's member runs
    labels = {json.loads(p.read_text())['arm']
              for p in (chain_dir / 's2' / 'member-searchqa-outcomes-card' / 'cells').glob('*.json')}
    assert labels == {'F'}
    shared = d2['shared_type'][0]
    assert shared['outcomes_with_card']['gate']['source'] == {'unit': 's2/card-r1-member-searchqa', 'arm': 'cand_card'}
    # the engineer's member examples come from the card-mounted member outcomes
    (propose,) = [c for c in modules.writers.propose_calls if c['bench'] == 'officeqa']
    (member,) = propose['members']
    assert member['source'] == shared['source'] and all(e['outcome'] == 'pass' for e in member['examples'])
    for record in records_of(chain_dir):
        assert chain.recompute_decision(record) == record


def test_resume_inside_a_member_unit_runs_no_finished_cell_again(tmp_path):
    """A cell of a card round's member arm and one of a program's member arm raise outside the shell: each pause
    leaves its unit incomplete; the recovery runs exactly the missing cell, every finished cell (home and member
    units) keeps its single run, every plan.json is byte-identical (the reloaded program decision registers its
    member arms again in their order) and every record is reproduced by recompute."""
    broken = {'cells': {('s2/card-r1-member-searchqa', 'searchqa-g1', 'cand_card#2'),
                        ('s2/program-2-member-searchqa', 'searchqa-g2', 'cand_program#3')}}  # not a first cell
    services, modules, script = build(tmp_path, order=('searchqa', 'officeqa'),
                                      proposals={'officeqa': ['p-oq-1', 'p-oq-2']},
                                      scripted={'outcomes': shared_outcome('gain', 'hold')})
    seen = counting(services)
    inner = services.solve_fn

    def solve(bench, item, mounted, **kwargs):
        for unit, item_id, label in list(broken['cells']):
            if kwargs['unit'] == unit and item['task_id'] == item_id and kwargs['tag'] == units.cell_tag(
                    bench, item_id, label):
                broken['cells'].discard((unit, item_id, label))
                raise KeyError('missing runtime')
        return inner(bench, item, mounted, **kwargs)
    services.solve_fn = solve
    chain_dir = tmp_path / 'G'
    pauses = []
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    for _ in range(3):  # two faults: at most two pauses (bounded, so a pause that recurs fails instead of looping)
        if not state['paused']:
            break
        pauses.append((state['paused']['reason'], state['paused']['unit']))
        before = {p: p.read_bytes() for p in chain_dir.rglob('plan.json')}
        recovery(tmp_path)
        state = chain.run(tmp_path, 'G', services=services, resume=True, sleep=lambda s: None)
        assert all(p.read_bytes() == data for p, data in before.items())
    assert state['complete'] and pauses == [('incomplete_unit:missing_cells', 's2/card-r1-member-searchqa'),
                                            ('incomplete_unit:missing_cells', 's2/program-2-member-searchqa')]
    assert all(count == 1 for count in seen.values()), [k for k, v in seen.items() if v != 1]
    d2 = json.loads((chain_dir / 's2' / 'decisions.json').read_text())
    assert [p['members'][0]['units'] for p in d2['programs']] == [
        {'baseline': 's2/card-r1-member-searchqa', 'candidate': 's2/program-%d-member-searchqa' % i} for i in (1, 2)]
    plan = json.loads((chain_dir / 's2' / 'program-2-member-searchqa' / 'plan.json').read_text())
    assert [row['unit'] for row in plan['compared']] == ['s2/member-searchqa-base', 's2/card-r1-member-searchqa',
                                                        's2/member-searchqa-outcomes-card',
                                                        's2/program-1-member-searchqa']
    expected = {'member-searchqa-outcomes': 2, 'member-searchqa-base': 3 * R, 'card-r1-member-searchqa': 3 * R,
                'member-searchqa-outcomes-card': 2, 'program-1-member-searchqa': 3 * R,
                'program-2-member-searchqa': 3 * R}
    assert member_cells(chain_dir) == expected
    for record in records_of(chain_dir):
        assert chain.recompute_decision(record) == record


# ---- RP15: a routed member (an earlier bench whose gate items the step routes into the home type) -------------------
ROUTED_ITEM = 'searchqa-g0'
OFFICEQA_TWIN = typing_.public_text(smoke.SYNTHETIC_ITEMS['officeqa']('officeqa-g0')[0])


def routed_embedder(texts):
    """The exact axis embeddings, except that SearchQA's gate item g0 is embedded as OfficeQA's gate item g0: it lies
    in OfficeQA's cluster, so once OfficeQA has a type of its own the type map routes it there (addendum RP15)."""
    return exact_embedder([OFFICEQA_TWIN if ROUTED_ITEM in text else text for text in texts])


def officeqa_card(system, user):
    """The scripted card writer: OfficeQA's request (its examples are OfficeQA's learn items) gets OFFICEQA_CARD."""
    return OFFICEQA_CARD if 'officeqa-l' in user else smoke.DEFAULT_CARD


def routed_outcome(member='hold'):
    """Step 1 SearchQA: B passes only the routed item g0, its card (DEFAULT_CARD) the even items: accepted. Step 2
    OfficeQA: SearchQA's type fails every OfficeQA item, so OfficeQA's no-harm check fails and it opens its own type
    t02; there B passes the odd items and OfficeQA's card every item (it passes the home rule). On a SearchQA item
    OfficeQA's card passes ('hold') or fails ('harm'). Programs never fire (they are rejected at home)."""
    def outcome(bench, item_id, mounted):
        text = mounted.get('card_text') or ''
        if bench == 'officeqa':
            if mounted.get('type') == 't01':
                return 'fail'
            return 'pass' if MARK in text or int(item_id[-1]) % 2 == 1 else 'fail'
        if MARK in text:
            return 'pass' if member == 'hold' else 'fail'
        if text.strip():
            return 'pass' if int(item_id[-1]) % 2 == 0 else 'fail'
        return 'pass' if item_id == ROUTED_ITEM else 'fail'
    return outcome


def routed_run(root, *, member='hold', routed=True):
    """The fake chain SearchQA, OfficeQA through the REAL mount, writers and reads (scripted replies)."""
    script = Capture({'outcomes': routed_outcome(member), 'replies': {'card_writer': officeqa_card},
                      'fires': lambda bench, item_id, procedure: False})
    services = smoke.fake_services(root, 'G', smoke.synthetic_manifest(), scripted=script)
    services.embed = routed_embedder if routed else exact_embedder
    services.slices = smoke.smoke_slices(services.items, services.slices)
    services.limits = dict(smoke.SMOKE_LIMITS)
    services.order = ('searchqa', 'officeqa')
    seen = counting(services)
    return chain.run(root, 'G', services=services, sleep=lambda s: None), services, script, seen


def gate_cells(chain_dir, unit):
    """{item: {(the type its cell was routed to, whether the candidate was applied)}} over the cells of ``unit``."""
    found = {}
    for path in (Path(chain_dir) / unit / 'cells').glob('*.json'):
        cell = json.loads(path.read_text())
        found.setdefault(cell['item_id'], set()).add((cell['mount']['type'],
                                                      (cell['mount'].get('candidate') or {}).get('applied')))
    return found


@pytest.mark.parametrize('member', ['hold', 'harm'])
def test_a_split_bench_with_gate_items_routed_into_the_home_type_is_a_routed_member(tmp_path, member):
    """RP15: OfficeQA opens its own type t02 at step 2 (its no-harm check in SearchQA's type fails), but SearchQA's gate
    item g0 lies in OfficeQA's cluster, so the step's type map routes it into t02 and t02's card would change its
    requests. SearchQA is a ROUTED member of t02: its examples reach the writer, OfficeQA's card is checked on
    SearchQA's whole gate slice (only g0 mounts the candidate, the other items keep SearchQA's type), and the records
    name the member kind and the routed gate-item count. A card that regresses SearchQA there is rejected
    (member_harm); one that holds is accepted. gates.recompute reproduces every decision."""
    root = tmp_path / 'routed-smoke'
    state, services, script, seen = routed_run(root, member=member)
    assert state['complete'], state['paused']
    chain_dir = root / 'G'
    d2 = json.loads((chain_dir / 's2' / 'decisions.json').read_text())
    assert d2['typing']['type'] == 't02' and d2['typing']['new_type'] and not d2['typing']['no_harm'][0]['merge']
    sid = typing_.source_id(chain._pool_pin(services.manifest, 'searchqa'))
    scope = {'bench': 'searchqa', 'source': sid, 'member': 'routed', 'routed_gate_items': 1}
    assert [{key: row[key] for key in scope} for row in d2['shared_type']] == [scope]
    (card,) = d2['cards']
    assert card['shared_with'] == [scope] and card['gain_points'] > card['tau_points']   # it passed the home rule
    (check,) = card['members']
    assert check['bench'] == 'searchqa' and check['n'] == 3 and check['repeats'] == R   # the member's whole gate slice
    assert check['units'] == {'baseline': 's2/member-searchqa-base', 'candidate': 's2/card-r1-member-searchqa'}
    # only the routed item mounts t02 and so the candidate; the other items keep SearchQA's type and mount (arm F)
    assert gate_cells(chain_dir, 's2/card-r1-member-searchqa') == {
        'searchqa-g0': {('t02', True)}, 'searchqa-g1': {('t01', False)}, 'searchqa-g2': {('t01', False)}}
    assert gate_cells(chain_dir, 's2/member-searchqa-base') == {
        'searchqa-g0': {('t02', None)}, 'searchqa-g1': {('t01', None)}, 'searchqa-g2': {('t01', None)}}
    if member == 'hold':
        assert (card['accepted'], card['reason'], card['member_harm']) == (True, 'accepted', None)
        assert check['no_regress'] and check['difference_sum'] == 0
        assert json.loads((chain_dir / 's2' / 'typemap.json').read_text())['types']['t02']['card'] is not None
    else:
        assert (card['accepted'], card['reason'], card['member_harm']) == (False, 'member_harm', 'searchqa')
        assert not check['no_regress'] and check['difference_sum'] == -R and check['worse'] == 1
        assert json.loads((chain_dir / 's2' / 'typemap.json').read_text())['types']['t02']['card'] is None
    # D16 (a) for the routed member too: the card writer saw its block, labelled with SearchQA's source
    ((unit, request),) = json_requests(script, 'card_writer', 's2/')
    assert [source['source'] for source in request['members']['sources']] == [sid]
    assert {'member-searchqa-outcomes', 'member-searchqa-base', 'card-r1-member-searchqa'} <= set(member_cells(chain_dir))
    assert all(count == 1 for count in seen.values())
    for record in records_of(chain_dir):
        assert chain.recompute_decision(record) == {**record, **(record.get('gate_verdict') or {})}
    # the readout names the member kind and the count beside the related gain
    doc = readout.chain_readout(root, 'G', order=('searchqa', 'officeqa'))
    (row,) = [d for d in doc['steps'][2]['decisions'] if d['kind'] == 'card']
    (related,) = row['related']
    assert (related['member'], related['routed_gate_items']) == ('routed', 1)
    assert 'searchqa (routed: 1 gate item)' in readout.markdown(doc)


def test_a_split_bench_with_no_gate_item_routed_into_the_home_type_is_no_member(tmp_path):
    """RP15, the other side: the same chain without the routed item (every SearchQA item stays in its own cluster):
    SearchQA is no member of OfficeQA's type t02, so nothing of D16 runs at step 2 (no member unit, no shared field,
    no member block), and OfficeQA's card is decided by the home rule alone."""
    root = tmp_path / 'unrouted-smoke'
    state, services, script, seen = routed_run(root, member='harm', routed=False)
    assert state['complete'], state['paused']
    chain_dir = root / 'G'
    d2 = json.loads((chain_dir / 's2' / 'decisions.json').read_text())
    assert d2['typing']['type'] == 't02' and d2['typing']['new_type']
    assert 'shared_type' not in d2 and not any('shared_with' in row for row in d2['cards'] + d2['programs'])
    assert d2['cards'][0]['accepted'] and member_cells(chain_dir) == {}
    assert not any('member' in unit for unit in state['done_units'])
    assert not any('"members"' in user for purpose, _, _, user in script.requests
                   if purpose in ('card_writer', 'program_writer'))


# ---- the pure verdict and recompute ---------------------------------------------------------------------------------
def runs(sums):
    return {'sums': dict(sums), 'squares': dict(sums), 'unknown': 0}


def stats(base, cand):
    items = sorted(base)
    return gates.repeat_statistics(runs(base), runs(cand), items=items, repeats=R, minimum_points=3.0, multiplier=2.0)


def member(bench, base, cand):
    return {**gates.member_decision(stats(base, cand)), 'bench': bench, 'source': 'src-' + bench}


def test_shared_verdict_accepts_only_the_home_rule_and_every_member_and_recompute_rebuilds_it():
    home = gates.card_decision(stats({'a': 0, 'b': 0, 'c': 0}, {'a': 3, 'b': 3, 'c': 0}))
    assert home['accepted']
    shared_with = [{'bench': 'searchqa', 'source': 'src-searchqa'}, {'bench': 'zebra', 'source': 'src-zebra'}]
    hold = member('searchqa', {'a': 1, 'b': 2, 'c': 3}, {'a': 1, 'b': 2, 'c': 3})
    hold2 = member('zebra', {'a': 1, 'b': 2, 'c': 3}, {'a': 3, 'b': 2, 'c': 3})
    harm = member('searchqa', {'a': 3, 'b': 3, 'c': 3}, {'a': 0, 'b': 3, 'c': 3})
    assert hold['no_regress'] and hold2['no_regress'] and not harm['no_regress']
    assert gates.shared_verdict(home, [hold, hold2], shared_with) == {'accepted': True, 'reason': 'accepted',
                                                                      'member_harm': None}
    assert gates.shared_verdict(home, [harm], shared_with) == {'accepted': False, 'reason': 'member_harm',
                                                               'member_harm': 'searchqa'}
    rejected = gates.card_decision(stats({'a': 0, 'b': 0, 'c': 0}, {'a': 0, 'b': 0, 'c': 0}))
    assert gates.shared_verdict(rejected, [], shared_with) == {'accepted': False, 'reason': 'gain_below_tau',
                                                               'member_harm': None}
    for bad in ([hold], [hold2, hold], [harm, hold2]):  # missing member, wrong order, a check after a harm
        with pytest.raises(ValueError):
            gates.shared_verdict(home, bad, shared_with)
    with pytest.raises(ValueError):  # a member check of a candidate that failed at home
        gates.shared_verdict(rejected, [hold], shared_with)
    with pytest.raises(ValueError):
        gates.shared_verdict(home, [], [])
    record = {**home, 'shared_with': shared_with, 'members': [hold, hold2],
              **gates.shared_verdict(home, [hold, hold2], shared_with), 'unit': 's2/card-r1'}
    assert gates.recompute(record) == record and gatestats.recompute(record['members'][0]) == hold
    tampered = json.loads(json.dumps(record))
    tampered['members'][1]['per_item'][0][2] = 0  # zebra's candidate loses item a: still no_regress? recompute says
    found = gates.recompute(tampered)
    assert found['members'][1]['difference_sum'] == -1 and found != tampered
    flipped = {**record, 'members': [{**hold, 'no_regress': False}, hold2]}
    assert gates.recompute(flipped) == record  # the verdict comes from per_item, never from a stored flag
    harmed = {**record, 'members': [{**harm}], 'accepted': True, 'reason': 'accepted', 'member_harm': None}
    assert gates.recompute(harmed)['reason'] == 'member_harm' and gates.recompute(harmed) != harmed
    with pytest.raises(ValueError):
        gates.recompute({**gates.no_harm_decision(stats({'a': 0}, {'a': 0})), 'shared_with': shared_with,
                         'members': []})
    assert gates.MEMBER_HARM == 'member_harm' and gates.member_decision is gatestats.member_decision


# ---- the writers' functions -----------------------------------------------------------------------------------------
def example(task_id, outcome, *, bench='searchqa', reference=None):
    row = {'task_id': task_id, 'view': 'view of %s (%s)' % (task_id, bench), 'reply': 'reply %s' % task_id,
           'outcome': outcome, 'request_user': json.dumps({'question': 'q %s' % task_id, 'context': 'c'})}
    if reference is not None:
        row['reference'] = reference
    return row


HOME = [example('officeqa-l0', 'fail', bench='officeqa', reference='42'),
        example('officeqa-l1', 'pass', bench='officeqa')]
MEMBER = [example('searchqa-l%d' % i, 'fail', reference='Ada Lovelace') for i in range(3)] + [
    example('searchqa-l%d' % i, 'pass') for i in range(3, 6)]


def test_member_examples_are_at_most_as_many_as_the_current_bench_examples_in_their_order():
    """The member's list is chosen by the current bench's rule (failures first, each group in its seeded order); the
    block keeps its first len(current examples) rows."""
    kept = writers.cap_member_examples(HOME, MEMBER)
    assert [row['task_id'] for row in kept] == ['searchqa-l0', 'searchqa-l1']
    four = HOME + [example('officeqa-l2', 'fail', bench='officeqa'), example('officeqa-l3', 'pass', bench='officeqa')]
    assert writers.cap_member_examples(four, MEMBER) == MEMBER[:4]
    assert writers.cap_member_examples(MEMBER + MEMBER, MEMBER) == MEMBER  # never more than the member has
    assert writers.cap_member_examples([], MEMBER) == []
    with pytest.raises(ValueError):
        writers.cap_member_examples(HOME, [dict(MEMBER[0], outcome=None)])


def test_card_request_adds_the_member_block_and_leaves_the_current_bench_part_as_it_was():
    members = [{'bench': 'searchqa', 'source': 'src-aaaa', 'examples': MEMBER}]
    for base_card in ('format', 'historical'):
        for round_ in (1, 2):
            kw = {'bench': 'officeqa', 'runtime': {}, 'current_text': '', 'examples': HOME, 'round': round_,
                  'base_card': base_card}
            if round_ == 2:
                kw.update(previous='- an earlier card', result={'stage': 'gate'})
            plain, dropped_plain = writers.card_request(**kw)
            shared, dropped = writers.card_request(**kw, members=members)
            block = shared.pop('members')
            assert shared == plain and dropped == {**dropped_plain, 'member_successes': 0, 'member_failures': 0}
            assert block == {'meaning': writers.MEMBERS_MEANING % 'src-aaaa', 'sources': [{
                **head('src-aaaa', base_card, writers.MEMBER_BASE_MEANING),
                'examples': [writers._shown(MEMBER[0]), writers._shown(MEMBER[1])]}]}
    assert writers.card_request(bench='officeqa', runtime={}, current_text='', examples=HOME, round=1, members=[])[0] \
        == writers.card_request(bench='officeqa', runtime={}, current_text='', examples=HOME, round=1)[0]


def test_an_oversized_request_drops_member_examples_before_any_example_of_the_current_bench():
    big = 'x' * 50_000
    home = [dict(example('officeqa-l%d' % i, 'fail', bench='officeqa'), view=big[:20_000]) for i in range(2)]
    member_rows = [dict(example('searchqa-l%d' % i, outcome), view=big[:30_000])
                   for i, outcome in enumerate(['fail', 'fail', 'pass'])]
    home.append(dict(example('officeqa-l9', 'pass', bench='officeqa'), view=big[:20_000]))
    request, dropped = writers.card_request(bench='officeqa', runtime={}, current_text='', examples=home, round=1,
                                            members=[{'bench': 'searchqa', 'source': 'src-aaaa',
                                                      'examples': member_rows}])
    assert len(request['examples']) == 3 and dropped['successes'] == dropped['failures'] == 0
    assert dropped['member_successes'] == 1 and dropped['member_failures'] >= 1
    assert len(json.dumps(request, ensure_ascii=False, sort_keys=True)) <= v225_cards.CARD_WRITER_INPUT_CHARS


def test_the_card_screen_reads_the_member_examples_corpora_and_ids():
    """A card that copies a member's reference is refused (``references``) only because the member block was shown;
    without the member the same text passes the screen."""
    from skillopt.execskill.typed import cards
    items = [{'benchmark': 'searchqa', 'task_id': 'searchqa-l0',
              'public': {'question': 'Who wrote it?', 'context': 'It was written by Ada Lovelace.'},
              'private': {'answers': ['Ada Lovelace']}}]
    calls = []

    def call(system, user):
        calls.append(user)
        return {'ok': True, 'finish_reason': 'stop', 'response': '- Name the author as Ada Lovelace when asked.'}
    officeqa = [{'benchmark': 'officeqa', 'task_id': 'officeqa-l0', 'public': {'question': 'Total?', 'context': 't'},
                 'private': {'answer': '42'}}]
    base = {'bench': 'officeqa', 'runtime': {}, 'current_text': '', 'examples': HOME,
            'corpus': writers.corpus_for('officeqa', officeqa), 'practice_ids': ['officeqa-l0', 'officeqa-l1'],
            'round': 1}
    alone = writers.write_card(call=call, **base)
    assert alone['text'] is not None and alone['attempts'][0]['violation'] is None
    shared = writers.write_card(call=call, **base, members=[{
        'bench': 'searchqa', 'source': 'src-aaaa', 'examples': MEMBER, 'corpus': writers.corpus_for('searchqa', items),
        'practice_ids': ['searchqa-l0']}])
    assert shared['text'] is None and [a['violation'] for a in shared['attempts']] == ['references', 'references']
    assert cards.content_chars(alone['text']) > 0


def test_program_payload_adds_trimmed_member_trajectories_and_fits_them_first():
    members = [{'bench': 'searchqa', 'source': 'src-aaaa', 'examples': MEMBER}]
    kw = {'bench': 'officeqa', 'runtime': {}, 'skill_index': [], 'examples': HOME,
          'hook_view': {'routing_view': {}, 'hook_view': {}}}
    plain = writers.program_payload(**kw)
    shared = writers.program_payload(**kw, members=members)
    block = shared.pop('members')
    assert shared == plain
    (source,) = block['sources']
    assert block['meaning'] == engineer_prompt.MEMBERS_MEANING % 'src-aaaa'
    assert {k: v for k, v in source.items() if k in ('source', 'format_block', 'base_card')} == head(
        'src-aaaa', 'format', engineer_prompt.MEMBER_BASE_MEANING)
    assert [t['task_id'] for t in source['trajectories']] == ['searchqa-l0', 'searchqa-l1']
    assert source['trajectories'] == engineer_payload.trim({'bench': 'searchqa', 'trajectories': writers.trajectory_examples(
        MEMBER[:2], 'searchqa')})['trajectories']  # rendered and trimmed as the current bench's
    assert source['trajectories_omitted'] == 0 and 'payload_trimming' in source
    assert writers._message_bytes(shared) == message_bytes(shared)  # the size fit() measures
    # a payload over the bound drops member trajectories first
    huge = [dict(row, request_user=json.dumps({'question': 'q', 'context': 'w ' * 40_000}), reply='r ' * 30_000)
            for row in MEMBER]
    home = [dict(row, reply='r ' * 30_000) for row in HOME]
    big = writers.program_payload(**{**kw, 'examples': home},
                                  members=[{'bench': 'searchqa', 'source': 'src-aaaa', 'examples': huge}])
    assert big['trajectories_omitted'] == 0 and len(big['trajectories']) == 2
    assert message_bytes(big) <= profiles.ROLE_INPUT_BYTES


def test_program_payload_fits_member_trajectories_as_fit_measures_the_message(monkeypatch):
    """fix-b (rb-requests F2), D16 (a): ``fit`` adds ``trajectories_omitted`` (27 bytes) before it measures, so the
    member loop must measure the payload with that key too. Bound: 5 bytes above the size of the payload after one
    member trajectory is dropped, measured WITHOUT the key, i.e. inside the 27-byte window. A member trajectory must
    go first (here both), never a trajectory of the current bench while a member trajectory is left."""
    members = [{'bench': 'searchqa', 'source': 'src-aaaa', 'examples': MEMBER}]
    kw = {'bench': 'officeqa', 'runtime': {}, 'skill_index': [], 'examples': HOME,
          'hook_view': {'routing_view': {}, 'hook_view': {}}}
    probe = writers.program_payload(**kw, members=members)            # nothing dropped at the real bound
    assert probe.pop('trajectories_omitted') == 0 and len(probe['members']['sources'][0]['trajectories']) == 2
    source = probe['members']['sources'][0]
    source['trajectories'], source['trajectories_omitted'] = source['trajectories'][:-1], 1
    edge = message_bytes(probe) + 5
    assert message_bytes({**probe, 'trajectories_omitted': 0}) > edge   # the window of the defect
    monkeypatch.setattr(profiles, 'ROLE_INPUT_BYTES', edge)
    fitted = writers.program_payload(**kw, members=members)
    kept = fitted['members']['sources'][0]
    assert (fitted['trajectories_omitted'], len(fitted['trajectories'])) == (0, 2)   # the current bench's part as is
    assert (kept['trajectories_omitted'], kept['trajectories']) == (2, [])
    assert message_bytes(fitted) <= edge


def test_the_revision_summary_adds_the_member_check_as_counts_and_points_only():
    home = gates.card_decision(stats({'a': 0, 'b': 0, 'c': 0}, {'a': 3, 'b': 3, 'c': 0}))
    shared_with = [{'bench': 'searchqa', 'source': 'src-aaaa'}, {'bench': 'zebra', 'source': 'src-bbbb'}]
    harm = member('searchqa', {'a': 3, 'b': 3, 'c': 3}, {'a': 0, 'b': 3, 'c': 3})
    decision = {**home, 'shared_with': shared_with, 'members': [harm],
                **gates.shared_verdict(home, [harm], shared_with)}
    summary = writers.revision_result(decision)
    plain = writers.revision_result(home)
    assert {k: v for k, v in summary.items() if k not in ('member_rule', 'member_check', 'decision', 'failing_clause')} \
        == {k: v for k, v in plain.items() if k not in ('decision', 'failing_clause')}
    assert summary['failing_clause'] == 'member_harm' and summary['decision'] == 'reject'
    assert summary['member_check'] == [
        {'source': 'src-aaaa', 'touched': 3, 'fixed': 0, 'broken': 1, 'net': -1, 'tied': 2,
         'mean_gain_points': harm['gain_points'], 'allowed_loss_points': 3.0, 'decision': 'harm'},
        {'source': 'src-bbbb', 'decision': 'not_run'}]
    assert 'searchqa' not in json.dumps(summary) and 'zebra' not in json.dumps(summary)


def test_the_d16_sentences_are_pinned_and_name_the_sources():
    found = {'writers.MEMBERS_MEANING': writers.MEMBERS_MEANING,
             'writers.MEMBER_BASE_MEANING': writers.MEMBER_BASE_MEANING,
             'engineer_prompt.MEMBERS_MEANING': engineer_prompt.MEMBERS_MEANING,
             'engineer_prompt.MEMBER_BASE_MEANING': engineer_prompt.MEMBER_BASE_MEANING}
    assert {key: sha256(text) for key, text in found.items()} == SENTENCE_SHA256
    for key in ('writers.MEMBERS_MEANING', 'engineer_prompt.MEMBERS_MEANING'):
        assert found[key].count('%s') == 1 and 'no worse' in found[key]
    assert engineer_prompt.verify()['version'] == engineer_prompt.PROMPT_VERSION  # the ten system texts unchanged
