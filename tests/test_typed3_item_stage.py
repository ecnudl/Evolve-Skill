"""typed-v3 item stage wired into the chain (docs/handoff/typed-v3/CHAIN-DECISIONS.md T3 to T6; build brief P2b): the
sealed option and its quota table, the units of a step under 'planned' and their records, the one replacement round,
the gate list J (its order, the members' real slices, no reuse by a later step), what writers see, the ledger charge
of the analyst and the selector, and resume at the four points -- fakes only (no network, no Docker, no /data).

The chain runs through the REAL ``chain.run``, ``mount``, ``writers`` and P2a's makers and selectors; the clients are
the smoke's scripted ones (``Script`` below: the analyst names its weaknesses from the learn rows it is shown, the
selector matches a candidate's question words to the descriptions, as P2a's tests script them). The solve is the
smoke's fake solve with an outcome rule that reads the item (``solve``).

SearchQA fixture (``SQ_POOL``): 80 questions; item i asks for a year, a person, a place or a count in turn (i % 4) up
to i = 43 and for a count from i = 44 on; learn = items 0..11, gate = 12..19, panel 78, 79; every item has the unique
markers 'Q<i> ' (its question), 'CTX<i>' (its snippet) and 'REF<i>' (its answer). Outcome rules (worked out by hand
in each test): ``strict`` -- B is wrong on the year / person / place questions below 32 and right on every other
item, a card makes every item right; ``lenient`` -- as strict on the learn items, every other item is right (the
made attack items are then no harder than the calibration items: the check fails).
"""
import hashlib
import json
import random
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_typed
from skillopt.execskill import typed as typed_, zebralogic
from skillopt.execskill.typed import SEED, chain, itemstage, library as library_, mount, prepare, smoke, units, writers
from skillopt.execskill.typed import items as items_
from skillopt.execskill.typed.bank import zebra
from skillopt.execskill.typed.items import select_items, store as store_
from tests.test_typed_chain import FakeReads, recovery
from tests.test_typed_schedule import inputs  # noqa: F401 -- prepare's fixture (pools, machinery record, typed tree)

NEUTRAL = Path('/tmp/typed3-p2b-neutral').resolve()  # resolved: route B's safe_path refuses a symlink in any parent
NOW = '2026-11-15T00:00:00'
R = 3
ROLE_PURPOSES = ('item_analyst', 'item_selector', 'card_writer', 'program_writer', 'describer')


@pytest.fixture
def tmp_path():
    """A neutral directory: pytest's own tmp_path carries the word 'test', which the sealed-path guard refuses."""
    NEUTRAL.mkdir(parents=True, exist_ok=True)
    made = Path(tempfile.mkdtemp(prefix='stage-', dir=NEUTRAL))
    try:
        yield made
    finally:
        shutil.rmtree(made, ignore_errors=True)


# ---- the SearchQA fixture -------------------------------------------------------------------------------------------
TOPICS = ('date', 'person', 'place', 'number')
QUESTION = {'date': 'In what year did event %d happen?', 'person': 'Who wrote book %d?',
            'place': 'Where is landmark %d?', 'number': 'How many parts has machine %d?'}
CYCLE = 44


def topic(i):
    return TOPICS[i % 4] if i < CYCLE else 'number'


def sq_id(i):
    return 'searchqa-%02d' % i


def index(item_id):
    return int(item_id.rsplit('-', 1)[1])


def sq_item(i):
    return {'benchmark': 'searchqa', 'task_id': sq_id(i), 'family_id': 'fam-%02d' % i, 'part': 'pool',
            'public': {'question': 'Q%02d %s' % (i, QUESTION[topic(i)] % i),
                       'context': 'CTX%02d snippet on item %d.' % (i, i)},
            'private': {'answers': ['REF%02d' % i]}}


SQ_POOL = [sq_item(i) for i in range(80)]
SQ_SLICES = {'learn': [sq_id(i) for i in range(12)], 'gate': [sq_id(i) for i in range(12, 20)],
             'panel': [sq_id(78), sq_id(79)]}


def markers(i):
    """What of SearchQA item i no role call may see when it is a gate or judging-side item."""
    return ['Q%02d ' % i + QUESTION[topic(i)] % i, 'CTX%02d' % i, 'REF%02d' % i]


def row(a, g, k, sa, sg):
    return {'judging': {'attack': a, 'guard': g, 'calibration': k}, 'shown': {'attack': sa, 'guard': sg}}


ZERO = row(0, 0, 0, 0, 0)
QUOTAS = {'searchqa': row(6, 3, 3, 3, 2), 'officeqa': ZERO, 'zebralogic': row(2, 1, 2, 1, 1),
          'spreadsheetbench': ZERO, 'alfworld': row(2, 1, 1, 1, 1)}


# ---- the ZebraLogic fixture (P2a's small language; sizes 5*2 and 5*3) ------------------------------------------------
VALUES = {'Name': ['Alice', 'Arnold', 'Bob', 'Carol', 'Eric', 'Peter'],
          'Pet': ['bird', 'cat', 'dog', 'fish', 'hamster', 'rabbit'],
          'Mother': ['Aniya', 'Holly', 'Janelle', 'Kailyn', 'Penny', 'Sarah'],
          'Height': ['average', 'short', 'super tall', 'tall', 'very short', 'very tall']}
INTRO = {'Name': 'Each person has a unique name', 'Pet': 'Each person has a unique type of pet',
         'Mother': "The mothers' names in different houses are unique", 'Height': 'People have unique heights'}
PHRASE = {'Name': '%s', 'Pet': 'the person who keeps a %s', 'Mother': "The person whose mother's name is %s",
          'Height': 'the person who is %s'}
LANGUAGE = {'columns': {column: {'intro': INTRO[column],
                                 'values': {str(n): sorted(VALUES[column][:n]) for n in range(2, 7)}} for column in VALUES},
            'phrases': {column: {value: PHRASE[column] % value for value in VALUES[column]} for column in VALUES}}
OTHERS = sorted(column for column in VALUES if column != 'Name')


def zebra_pool(count=30):
    rows = []
    for n in range(count):
        rng = random.Random('pool:%d' % n)
        puzzle = zebra.make(rng, 5, ['Name'] + rng.sample(OTHERS, (2, 3)[n % 2] - 1), LANGUAGE)
        rows.append(zebralogic.normalize(zebra.row_of(puzzle, LANGUAGE, 'zebralogic-%02d' % n), partition='pool'))
    return rows


ZB_POOL = zebra_pool()
ZB_SLICES = {'learn': ['zebralogic-%02d' % n for n in range(12)], 'gate': ['zebralogic-%02d' % n for n in range(12, 20)],
             'panel': ['zebralogic-28', 'zebralogic-29']}


def officeqa_pool(count=12):
    out = []
    for n in range(count):
        public, private = smoke.SYNTHETIC_ITEMS['officeqa']('officeqa-%02d' % n)
        out.append({'benchmark': 'officeqa', 'task_id': 'officeqa-%02d' % n, 'public': public, 'private': private})
    return out


OQ_POOL = officeqa_pool()
OQ_SLICES = {'learn': ['officeqa-%02d' % n for n in range(4)], 'gate': ['officeqa-%02d' % n for n in range(4, 10)],
             'panel': ['officeqa-10', 'officeqa-11']}


def sheet_pool(count=8):
    out = []
    for n in range(count):
        public, private = smoke.SYNTHETIC_ITEMS['spreadsheetbench']('spreadsheetbench-%02d' % n)
        out.append({'benchmark': 'spreadsheetbench', 'task_id': 'spreadsheetbench-%02d' % n, 'public': public,
                    'private': private})
    return out


SH_POOL = sheet_pool()
SH_SLICES = {'learn': ['spreadsheetbench-%02d' % n for n in range(3)],
             'gate': ['spreadsheetbench-%02d' % n for n in range(3, 6)], 'panel': ['spreadsheetbench-06', 'spreadsheetbench-07']}
BENCHES = {'searchqa': (SQ_POOL, SQ_SLICES), 'zebralogic': (ZB_POOL, ZB_SLICES), 'officeqa': (OQ_POOL, OQ_SLICES),
           'spreadsheetbench': (SH_POOL, SH_SLICES)}


# ---- outcome rules --------------------------------------------------------------------------------------------------
def strict(bench, item, mounted):
    if mounted.get('card_text'):
        return 'pass'
    if bench == 'searchqa':
        i = index(item['task_id'])
        return 'fail' if topic(i) != 'number' and i < 32 else 'pass'
    if bench == 'zebralogic':
        return 'fail' if item['task'] == '5*3' else 'pass'
    return 'fail'


def lenient(bench, item, mounted):
    if bench == 'searchqa' and index(item['task_id']) >= 12:
        return 'pass'
    return strict(bench, item, mounted)


def member_rule(bench, item, mounted):
    """D16 fixture: a card helps OfficeQA items only; SearchQA as strict without the card's help."""
    if bench == 'officeqa':
        return 'pass' if mounted.get('card_text') else 'fail'
    return strict(bench, item, {**mounted, 'card_text': None})


def solve(rule):
    """``smoke.fake_solve`` with an outcome rule that reads the item (its id and, for ZebraLogic, its size)."""
    def run(bench, item, mounted, *, call, runtime, worker_factory=None, native=None, nominal_tokens=None, unit, tag,
            scorer_root, mode=None, step=None, episodes=None):
        found = call(mounted.get('system_card') or '', smoke.fake_request(bench, item, mounted))
        enabled = list(mounted.get('enabled') or [])
        token = rule(bench, item, mounted) if found.get('ok') else 'unknown_' + str(found.get('error_type'))
        reply = found.get('response')
        return {'bench': bench, 'item_id': item['task_id'], 'arm': mounted.get('arm'),
                'mount': {k: v for k, v in mounted.items() if k not in ('enabled', 'card_text', 'system_card')},
                'public_hash': library_.canonical_sha256(item['public']),
                'prediction_status': 'available' if found.get('ok') else 'unknown', 'output_excerpt': (reply or '')[:2000],
                'reply': reply, 'correct': None if token.startswith('unknown') else token == 'pass', 'token': token,
                'official': {'status': token, 'reason': 'scripted'}, 'format': {}, 'flags': [],
                'fired': [p['id'] for p in enabled], 'faults': [], 'tokens': call.tokens(), 'sends': call.sends,
                'request_sha256': [s['request_sha256'] for s in call.sends], 'configuration_error': False,
                'infrastructure_unknown': call.infrastructure_unknown(), 'failure': None}
    return run


# ---- the scripted analyst and selector ------------------------------------------------------------------------------
WEAKNESSES = (('dates', 'year', 'Questions that ask for a year (dates).'),
              ('people', 'who', 'Questions that ask who (people).'),
              ('places', 'where', 'Questions that ask where (places).'))
GUARD = 'Questions that ask how many (counts).'
KEYWORD = {'year': 'dates', 'who': 'people', 'where': 'places', 'how many': 'counts'}


def request_of(user):
    return json.loads(user.split('\n\nFormat retry')[0])


def analyst_reply(system, user):
    """SearchQA: one weakness per weak question kind, its evidence the learn items of that kind B failed in at least
    two runs, and the counting questions as the guard; ZebraLogic: three weaknesses on the 5*3 puzzles B failed."""
    request = request_of(user)
    rows = request['learn_items']

    def failed(test):
        return [r['id'] for r in rows if test(r) and sum(o is not True for o in r['outcomes']) >= 2]
    if request['bench'] == 'zebralogic':
        big = failed(lambda r: r.get('size') == '5*3')
        weaknesses = [{'id': name, 'description': 'Five-house puzzles with three attributes (%s).' % name,
                       'evidence': big, 'signature': 'a wrong grid', 'spec': {'sizes': ['5*3']}}
                      for name in ('grids', 'clues', 'columns')]
        return json.dumps({'weaknesses': weaknesses, 'guards': [], 'note': request['request']})
    weaknesses = [{'id': name, 'description': text, 'signature': 'a wrong ' + name, 'spec': {},
                   'evidence': failed(lambda r, word=word: word in (r['public_text'] or '').lower())}
                  for name, word, text in WEAKNESSES]
    return json.dumps({'weaknesses': weaknesses, 'guards': [{'description': GUARD, 'spec': {}}],
                       'note': request['request']})


def selector_reply(system, user):
    request = request_of(user)
    by_word = {word: d['id'] for d in request['descriptions'] for word, kind in KEYWORD.items() if kind in d['description']}
    matches = {}
    for candidate in request['candidates']:
        question = candidate['text'].split('\n')[0].lower()
        found = [by_word[word] for word in KEYWORD if word in question and word in by_word]
        matches[candidate['label']] = found[0] if found else None
    return json.dumps({'matches': matches})


class Script(smoke.Script):
    """The smoke's scripted clients with the analyst and the selector; every send is kept as (purpose, unit, system,
    user), the interrupted ones included; ``broken``: {(purpose, unit)} whose first send raises before it reaches the
    script (a lost connection)."""

    def __init__(self, scripted=None, *, broken=()):
        scripted = dict(scripted or {})
        replies = {'item_analyst': analyst_reply, 'item_selector': selector_reply, **(scripted.get('replies') or {})}
        super().__init__({**scripted, 'replies': replies})
        self.broken, self.requests = set(broken), []

    def send(self, purpose, system, user, *, model, unit=None):
        with self.lock:
            self.requests.append((purpose, unit, system, user))
            if (purpose, unit) in self.broken:
                self.broken.discard((purpose, unit))
                raise RuntimeError('connection lost')
        return super().send(purpose, system, user, model=model, unit=unit)

    def role_requests(self, purposes=ROLE_PURPOSES):
        return [(purpose, unit, system + '\n' + user) for purpose, unit, system, user in self.requests
                if purpose in purposes]


def build(root, script, *, order=('searchqa',), stage='planned', quotas=QUOTAS, limits=None, rule=strict,
          program_learning='single', archive=None):
    """Fake services of the benches of ``order`` (their pools and slices above) through the real mount and writers,
    under the sealed item stage ``stage`` with the quota table ``quotas`` (and the sealed ``archive`` value when
    given, 'repair' only); one card round."""
    manifest = smoke.synthetic_manifest(sizes={bench: {'learn': 1, 'gate': 1, 'panel': 1} for bench in order})
    manifest['slices'] = {bench: {part: list(ids) for part, ids in BENCHES[bench][1].items()} for bench in order}
    manifest.update(program_learning=program_learning, **({'archive': archive} if archive is not None else {}))
    if stage is not None:
        manifest.update(item_stage=stage, item_quotas=quotas if stage == 'planned' else None)
    script.items = {bench: [dict(item) for item in BENCHES[bench][0]] for bench in order}
    modules = SimpleNamespace(mount=mount, writers=writers, reads=FakeReads())
    services = smoke.fake_services(root, 'G', manifest, scripted=script, modules=modules)
    services.order, services.solve_fn = tuple(order), solve(rule)
    services.limits = {**chain.DEFAULT_LIMITS, 'card_rounds': 1, **(limits or {})}
    return services


def run(root, script=None, **kw):
    script = script if script is not None else Script()
    services = build(root, script, **kw)
    return chain.run(root, 'G', services=services, sleep=lambda s: None), services


def read(root, *parts):
    return json.loads(Path(root, 'G', *parts).read_text())


VOLATILE = {'logical_call', 'ledger', 'at', 'started', 'finished', 'updated'}


def strip(value):
    if isinstance(value, dict):
        return {k: strip(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [strip(v) for v in value]
    return value


def records(root):
    """Every JSON record of the chain directory but the state, the ledger, the owner's recovery files, the first
    call's receipt and the calls files (an interrupted send stays in its calls file and the ledger), without the send
    counters, ledger snapshots and wall-clock stamps (P1's comparison)."""
    base, out = Path(root, 'G'), {}
    for path in sorted(base.rglob('*.json')):
        rel = path.relative_to(base).as_posix()
        if (rel in ('state.json', 'ledger.json', 'confirm.json') or rel.startswith('recovery')
                or '/calls/' in '/' + rel):
            continue
        out[rel] = strip(json.loads(path.read_text()))
    return out


def ranked_ids(ids, tag):
    """The seeded draw order of ``coevo5.data.ranked``, written out: sha256 of [seed, tag, id]."""
    return sorted(ids, key=lambda i: hashlib.sha256(json.dumps([SEED, tag, i]).encode()).hexdigest())


def ids_of(entries):
    return [entry['record']['item'] for entry in entries]


def gate_plans(root, k=1):
    """{unit: plan.json} of every gate unit of step k (noise, no-harm, outcomes, card, program and member arms)."""
    base = Path(root, 'G', 's%d' % k)
    return {path.parent.name: json.loads(path.read_text()) for path in sorted(base.glob('*/plan.json'))}


def cells_of(root, unit):
    return [json.loads(p.read_text()) for p in sorted(Path(root, 'G', *unit.split('/'), 'cells').glob('*.json'))]


# ---- the round-1 SearchQA expectations, worked out by hand from the rules ----------------------------------------------
# candidates: items 20..79 (neither learn nor gate, no shared family); batches of 25: 25, 25, 10. Weak kinds in turn,
# one item each in pool order, judging first: w1 (years) 20 24 | w2 (people) 21 25 | w3 (places) 22 26; shown: 28 29
# 30; guards (counting questions in pool order): judging 23 27 31, shown 35 39; calibration: the first 3 of the
# seeded draw that are not taken.
ROUND_1 = {'judging_attack': [20, 24, 21, 25, 22, 26], 'judging_guard': [23, 27, 31], 'shown_attack': [28, 29, 30],
           'shown_guard': [35, 39]}


def round_1_calibration():
    taken = {i for values in ROUND_1.values() for i in values}
    tag = select_items.DRAW_TAG % ('searchqa', 'typed-v3:G:s1:r1')
    return [index(i) for i in ranked_ids([sq_id(i) for i in range(20, 80)], tag) if index(i) not in taken][:3]


# ==== A: the sealed option and the quota table =========================================================================
def test_the_option_its_defaults_and_the_quota_table_of_t5():
    assert (typed_.ITEM_STAGES, typed_.ITEM_STAGE_DEFAULT) == (('none', 'planned'), 'none')
    assert typed_.ITEM_ZERO_REASONS == {'officeqa': 'audit_bing_B36', 'spreadsheetbench': 'maker_not_built'}
    assert run_typed.ITEM_STAGES == typed_.ITEM_STAGES
    assert itemstage.SIDES == items_.SIDES and itemstage.SELECTOR_PURPOSE == select_items.SELECTOR_PURPOSE
    assert itemstage.NOT_BUILT == 'maker_not_built' and itemstage.BASE_ARM == chain.BASE_ARM
    # the default sealed table: T5's judging A / G / K and shown attack / guard, OfficeQA and the sheet at zero
    assert prepare.default_item_quotas() == {
        'searchqa': row(60, 45, 45, 27, 13), 'officeqa': ZERO, 'zebralogic': row(80, 60, 60, 40, 20),
        'spreadsheetbench': ZERO, 'alfworld': row(16, 12, 12, 8, 4)}
    # a typed-v2 style manifest (no field) runs the typed-v2 step flow without a table
    assert prepare.item_stage_of({}) == 'none' and prepare.item_quotas_of({}) is None
    planned = {'item_stage': 'planned', 'item_quotas': prepare.default_item_quotas()}
    assert prepare.item_quotas_of(planned) == prepare.default_item_quotas()
    for bad in ({'item_stage': 'made'}, {'item_stage': None}, {'item_quotas': prepare.default_item_quotas()},
                {'item_stage': 'planned'}, {'item_stage': 'planned', 'item_quotas': {'searchqa': row(1, 1, 1, 1, 1)}},
                {'item_stage': 'planned', 'item_quotas': {**prepare.default_item_quotas(), 'officeqa': row(1, 0, 0, 0, 0)}},
                {'item_stage': 'planned', 'item_quotas': {**prepare.default_item_quotas(),
                                                          'spreadsheetbench': row(0, 0, 0, 0, 1)}},
                {'item_stage': 'planned', 'item_quotas': {**prepare.default_item_quotas(), 'alfworld': row(-1, 0, 0, 0, 0)}}):
        with pytest.raises(ValueError):
            prepare.item_quotas_of(bad)


def test_the_quotas_per_bench_and_the_reasons_of_the_benches_without_items():
    """With the default table SearchQA, ZebraLogic and ALFWorld get T5's counts (three kept weaknesses: the quota as it
    is; fewer: 20 % of each side's total as attack items); OfficeQA and SpreadsheetBench make nothing and say why
    before any call; another zero row says 'no_quota'."""
    table = prepare.default_item_quotas()
    reasons = {bench: itemstage.skip_reason(bench, table) for bench in typed_.ORDER}
    assert reasons == {'searchqa': None, 'officeqa': 'audit_bing_B36', 'zebralogic': None,
                       'spreadsheetbench': 'maker_not_built', 'alfworld': None}
    assert itemstage.skip_reason('alfworld', {**table, 'alfworld': ZERO}) == 'no_quota'
    for bench, (a, g, k, sa, sg) in (('searchqa', (60, 45, 45, 27, 13)), ('zebralogic', (80, 60, 60, 40, 20)),
                                     ('alfworld', (16, 12, 12, 8, 4))):
        found = items_.counts(bench, ['w1', 'w2', 'w3'], table)
        assert (found['rule'], found['judging'], found['shown']) == (
            'quota', {'attack': a, 'guard': g, 'calibration': k}, {'attack': sa, 'guard': sg})
        reduced = items_.counts(bench, ['w1'], table)
        judging, shown = a + g + k, sa + sg
        assert reduced['judging'] == {'attack': judging // 5, 'guard': g, 'calibration': judging - judging // 5 - g}
        assert reduced['shown'] == {'attack': shown // 5, 'guard': shown - shown // 5}
    for bench in ('officeqa', 'spreadsheetbench'):
        assert items_.counts(bench, ['w1', 'w2', 'w3'], table)['rule'] == 'no_items'


def test_prepare_seals_the_item_stage_and_its_table(inputs):
    parent = inputs['parent']
    common = dict(machinery_manifest=inputs['machinery'], roles_repo='/root/roles', pools_root=inputs['pools'],
                  smoke=True, typed_tree=inputs['tree'], root_parent=str(parent))
    default = prepare.prepare(parent / 'execskill-20261112-typed-v3-smoke', **common)
    assert (default['item_stage'], default['item_quotas']) == ('none', None)
    made = prepare.prepare(parent / 'execskill-20261113-typed-v3-smoke', item_stage='planned', **common)
    assert made['item_stage'] == 'planned' and made['item_quotas'] == prepare.default_item_quotas()
    assert prepare.load_manifest(made['root']) == made
    own = {**prepare.default_item_quotas(), 'searchqa': row(6, 3, 3, 3, 2)}
    small = prepare.prepare(parent / 'execskill-20261115-typed-v3-smoke', item_stage='planned', item_quotas=own, **common)
    assert small['item_quotas'] == own
    fields = {key: value for key, value in made.items() if key != 'record_sha256'}
    for key, value in (('item_stage', 'none'), ('item_quotas', own)):  # the hash covers both
        assert prepare.seal({**fields, key: value})['record_sha256'] != made['record_sha256']
    # refused before anything is written: an unknown stage, a table without 'planned', a non-zero OfficeQA row
    for bad in ({'item_stage': 'made'}, {'item_quotas': own},
                {'item_stage': 'planned', 'item_quotas': {**own, 'officeqa': row(1, 1, 1, 1, 1)}},
                {'item_stage': 'planned', 'item_quotas': {'searchqa': row(1, 1, 1, 1, 1)}}):
        new = parent / 'execskill-20261114-typed-v3-smoke'
        with pytest.raises(ValueError):
            prepare.prepare(new, **common, **bad)
        assert not new.exists()
    # load_manifest refuses a changed value (re-sealed, so only the field differs); a manifest without both reads 'none'
    root = Path(made['root'])
    for key, value in (('item_stage', 'made'), ('item_quotas', None), ('item_quotas', {**own, 'officeqa': row(1, 0, 0, 0, 0)})):
        units.write_json(root / 'manifest.json', prepare.seal({**fields, key: value}))
        with pytest.raises(ValueError):
            prepare.load_manifest(root)
    units.write_json(root / 'manifest.json', prepare.seal({key: value for key, value in fields.items()
                                                           if key not in ('item_stage', 'item_quotas')}))
    loaded = prepare.load_manifest(root)
    assert prepare.item_stage_of(loaded) == 'none' and prepare.item_quotas_of(loaded) is None


@pytest.fixture
def environ():
    """main() cleans os.environ in place; the test restores it."""
    import os
    saved = dict(os.environ)
    try:
        yield os.environ
    finally:
        os.environ.clear()
        os.environ.update(saved)


def test_the_cli_names_the_item_stage_on_prepare_only(tmp_path, monkeypatch, environ, capsys):
    parse = run_typed.parser().parse_args
    assert parse(['prepare', '--root', '/r', '--item-stage', 'planned']).item_stage == 'planned'
    assert parse(['prepare', '--root', '/r']).item_stage is None
    for bad in (['prepare', '--root', '/r', '--item-stage', 'made'],
                ['run', '--root', '/r', '--chain', 'G', '--item-stage', 'planned'],
                ['smoke', '--root', '/r', '--chain', 'G', '--fake', '--item-stage', 'planned']):
        with pytest.raises(SystemExit):
            parse(bad)
    calls, adapter = [], run_typed._prepare
    monkeypatch.setattr(run_typed, '_prepare', lambda root, **kw: calls.append(kw) or {
        'configuration': 'typed-v3', 'item_stage': kw.get('item_stage', 'none'),
        'item_quotas': prepare.default_item_quotas() if kw.get('item_stage') == 'planned' else None})
    root, machinery = tmp_path / 'run', tmp_path / 'machinery.json'
    root.mkdir()
    machinery.write_text(json.dumps({'runtime': {}}))
    assert run_typed.main(['prepare', '--root', str(root), '--machinery-manifest', str(machinery),
                           '--item-stage', 'planned']) == 0
    assert calls[-1] == {'machinery_manifest': str(machinery), 'roles_repo': typed_.ROLES_REPO,
                         'pools_root': typed_.POOLS_ROOT, 'smoke': False, 'item_stage': 'planned'}
    printed = json.loads(capsys.readouterr().out)['manifest']
    assert printed['item_stage'] == 'planned' and printed['item_quotas']['searchqa'] == {'judging': 150, 'shown': 40}
    assert printed['item_quotas']['officeqa'] == {'judging': 0, 'shown': 0}
    # the adapter hands prepare the item stage only when the command names it (the code default otherwise)
    seen = []
    monkeypatch.setattr(prepare, 'prepare', lambda root, **kw: seen.append(kw) or {})
    plain = dict(machinery_manifest='/m.json', roles_repo='/creds', pools_root='/pools', smoke=True)
    adapter('/r', **plain)
    adapter('/r', item_stage='planned', **plain)
    assert seen == [plain, {**plain, 'item_stage': 'planned'}]


def test_a_state_started_under_one_item_stage_refuses_the_other(tmp_path):
    """One root never mixes two item stages or two quota tables; a 'none' start writes typed-v2's state shape."""
    plain = chain._open_state(tmp_path / 'a', 'G', 'smoke', False)
    assert 'item_stage' not in plain and 'item_quotas_sha256' not in plain
    table = prepare.default_item_quotas()
    made = chain._open_state(tmp_path / 'b', 'G', 'smoke', False, item_stage='planned', item_quotas=table)
    assert made['item_stage'] == 'planned' and made['item_quotas_sha256'] == library_.canonical_sha256(table)
    (tmp_path / 'b').mkdir()
    units.write_json(tmp_path / 'b' / 'state.json', made)
    assert chain._open_state(tmp_path / 'b', 'G', 'smoke', True, item_stage='planned', item_quotas=table) == made
    other = {**table, 'searchqa': row(6, 3, 3, 3, 2)}
    for kw in ({}, {'item_stage': 'planned', 'item_quotas': other}):
        with pytest.raises(ValueError, match='another'):
            chain._open_state(tmp_path / 'b', 'G', 'smoke', True, **kw)


# ==== B: the units of a step, their records and the gate list J =========================================================
def test_a_searchqa_step_runs_the_units_in_order_and_seals_its_items(tmp_path, monkeypatch):
    """The check holds (B is wrong on every made attack item, right on every calibration item): diagnose, items-plan,
    items, items-check, then items.json and typed-v2's units on J = gate 12..19, attack, guard, calibration."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    state, services = run(tmp_path)
    assert state['complete'], state['paused']
    done = state['done_units']
    s1 = done[done.index('s1/diagnose'):done.index('s1/noise') + 1]
    assert s1 == ['s1/diagnose', 's1/items-plan', 's1/items', 's1/items-check', 's1/noise']
    assert not [unit for unit in done if unit.startswith('s1/items-plan-2') or unit.startswith('s1/items-2')]
    # diagnose: B three times on the 12 learn items; the right runs per item follow the rule
    diagnose = read(tmp_path, 's1', 'diagnose', 'diagnose.json')
    assert diagnose['right_runs'] == [[sq_id(i), 3 if topic(i) == 'number' else 0] for i in range(12)]
    assert diagnose['by_right_runs'] == [[0, 9], [1, 0], [2, 0], [3, 3]]
    assert sorted(c['arm'] for c in cells_of(tmp_path, 's1/diagnose')) == ['B#1'] * 12 + ['B#2'] * 12 + ['B#3'] * 12
    # the plan: three weaknesses, each with its three failed learn items, and the counting guard
    plan = read(tmp_path, 's1', 'items-plan', 'analyst.json')
    assert plan['status'] == 'ok' and plan['round'] == 1 and not plan['revision']
    assert [(w['id'], w['given_id'], w['evidence']) for w in plan['plan']['weaknesses']] == [
        ('w1', 'dates', [sq_id(i) for i in (0, 4, 8)]), ('w2', 'people', [sq_id(i) for i in (1, 5, 9)]),
        ('w3', 'places', [sq_id(i) for i in (2, 6, 10)])]
    assert [g['description'] for g in plan['plan']['guards']] == [GUARD]
    # the items: the selector's three batches, the picks worked out by hand (ROUND_1)
    made = read(tmp_path, 's1', 'items', 'made.json')
    assert made['counts']['rule'] == 'quota' and made['counts']['attack_split'] == {
        'judging': [['w1', 2], ['w2', 2], ['w3', 2]], 'shown': [['w1', 1], ['w2', 1], ['w3', 1]]}
    calibration = round_1_calibration()
    sealed = read(tmp_path, 's1', 'items.json')
    lists = sealed['lists']
    assert ids_of(lists['judging']['attack']) == [sq_id(i) for i in ROUND_1['judging_attack']]
    assert ids_of(lists['judging']['guard']) == [sq_id(i) for i in ROUND_1['judging_guard']]
    assert ids_of(lists['judging']['calibration']) == [sq_id(i) for i in calibration]
    assert ids_of(lists['shown']['attack']) == [sq_id(i) for i in ROUND_1['shown_attack']]
    assert ids_of(lists['shown']['guard']) == [sq_id(i) for i in ROUND_1['shown_guard']]
    assert lists['replaced'] == [] and lists['unused'] == [] and sealed['reason'] is None
    assert [e['record']['weakness'] for e in lists['judging']['attack']] == ['w1', 'w1', 'w2', 'w2', 'w3', 'w3']
    assert [e['slot'] for e in lists['judging']['attack'][:2]] == ['judging-attack-w1-001', 'judging-attack-w1-002']
    for entry in [e for side in ('shown', 'judging') for cls in lists[side] for e in lists[side][cls]]:
        stored = store_.ItemStore(Path(tmp_path, 'G', entry['unit'])).item(entry['slot'])
        assert stored == SQ_POOL[index(entry['record']['item'])]            # the real item and its real reference
        assert entry['record']['item_sha256'] == items_.item_sha256('searchqa', stored)
    assert sealed['gate'] == {'real': 8, 'attack': 6, 'guard': 3, 'calibration': 3, 'total': 20}
    assert sealed['plan_sha256'] == plan['plan_sha256'] and sealed['final_round'] == 1
    # the check: B once on the 6 attack and 3 calibration items: 0 of 6 against 3 of 3 -> holds
    check = read(tmp_path, 's1', 'items-check', 'check.json')
    assert (check['holds'], check['attack']['pass'], check['attack']['n'], check['calibration']['pass'],
            check['calibration']['n']) == (True, 0, 6, 3, 3)
    assert check['by_weakness'] == [['w1', 2, 0], ['w2', 2, 0], ['w3', 2, 0]] and check['cells'] == 9
    assert sorted(c['item_id'] for c in cells_of(tmp_path, 's1/items-check')) == sorted(
        sq_id(i) for i in ROUND_1['judging_attack'] + calibration)
    assert {c['arm'] for c in cells_of(tmp_path, 's1/items-check')} == {'B'}
    assert sealed['checks'] == [check]
    # J at ONE place: every gate unit of the step runs on it, in its order, and names the sealed list
    J = [sq_id(i) for i in list(range(12, 20)) + ROUND_1['judging_attack'] + ROUND_1['judging_guard'] + calibration]
    plans = gate_plans(tmp_path)
    assert {'noise', 'outcomes', 'card-r1', 'outcomes-card', 'program-1-gate'} <= set(plans)
    for name, plan_record in plans.items():
        assert plan_record['items'] == J, name
        assert [row[0] for row in plan_record['identities']] == J and plan_record['items_sha256'] == sealed['record_sha256']
    assert read(tmp_path, 's1', 'noise', 'noise.json')['items'] == 20
    assert sorted(c['item_id'] for c in cells_of(tmp_path, 's1/noise')) == sorted(J * 3)


def captured_run(root, script, **kw):
    """``run`` with the kwargs of every card-writer and engineer call kept (their examples, corpus and ids)."""
    services = build(root, script, **kw)
    captured = {'card': [], 'engineer': []}
    card, propose = services.write_card, services.propose_programs
    services.write_card = lambda **found: captured['card'].append(found) or card(**found)
    services.propose_programs = lambda **found: captured['engineer'].append(found) or propose(**found)
    return chain.run(root, 'G', services=services, sleep=lambda s: None), services, captured


# ==== E: what writers see ==============================================================================================
def test_writers_see_the_learn_and_the_shown_items_attack_first(tmp_path, monkeypatch):
    """F runs once on the 12 learn and the 5 shown items (s1/outcomes, and with the accepted card s1/outcomes-card);
    the card writer's examples are the learn examples (9 failures, 3 successes: strict) and then the shown items'
    (attack 28 29 30 all wrong, then guard 35 39 right); its screen's corpus and practice ids hold the shown items too;
    the engineer gets the learn examples with the card (6 of 12 successes, the bound) and then the 5 shown items."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    script = Script()
    state, services, captured = captured_run(tmp_path, script)
    assert state['complete'], state['paused']
    learn = [sq_id(i) for i in range(12)]
    shown = [sq_id(i) for i in ROUND_1['shown_attack'] + ROUND_1['shown_guard']]
    for unit in ('s1/outcomes', 's1/outcomes-card'):
        single = [c for c in cells_of(tmp_path, unit) if c['arm'] == 'F']
        assert sorted(c['item_id'] for c in single) == sorted(learn + shown), unit
    (card,) = captured['card']
    examples = [e['task_id'] for e in card['examples']]
    assert set(examples[:12]) == set(learn) and [e['outcome'] for e in card['examples'][:12]] == ['fail'] * 9 + ['pass'] * 3
    assert set(examples[12:15]) == {sq_id(i) for i in ROUND_1['shown_attack']} and set(examples[15:]) == {
        sq_id(i) for i in ROUND_1['shown_guard']}
    assert [e['outcome'] for e in card['examples'][12:]] == ['fail'] * 3 + ['pass'] * 2
    assert card['practice_ids'] == learn + shown and [i['task_id'] for i in card['corpus']] == learn + shown
    engineer = captured['engineer'][0]
    found = [e['task_id'] for e in engineer['examples']]
    assert len(found) == 11 and set(found[:6]) <= set(learn)
    assert set(found[6:9]) == {sq_id(i) for i in ROUND_1['shown_attack']}
    assert set(found[9:]) == {sq_id(i) for i in ROUND_1['shown_guard']}
    assert {e['outcome'] for e in engineer['examples']} == {'pass'}
    # the shown items' public text reaches the card writer's request
    (request,) = [text for purpose, _, text in script.role_requests(('card_writer',))]
    assert all('CTX%02d' % index(i) in request for i in shown)


def test_a_rejected_round_runs_its_card_on_the_shown_items_too(tmp_path, monkeypatch):
    """With two card rounds and a card that never helps (lenient: every non-learn item right, the card changes
    nothing on the learn items either), round 1 is rejected and s1/card-r1-learn runs the rejected card on the learn
    AND the shown items, from which round 2's examples come (learn first, then the shown items, attack first)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)

    def no_card(bench, item, mounted):
        return lenient(bench, item, {**mounted, 'card_text': None})
    script = Script()
    state, services, captured = captured_run(tmp_path, script, rule=no_card, limits={'card_rounds': 2})
    assert state['complete'], state['paused']
    sealed = read(tmp_path, 's1', 'items.json')
    shown = ids_of(sealed['lists']['shown']['attack']) + ids_of(sealed['lists']['shown']['guard'])
    learn = [sq_id(i) for i in range(12)]
    assert sorted(c['item_id'] for c in cells_of(tmp_path, 's1/card-r1-learn')) == sorted(learn + shown)
    assert {c['arm'] for c in cells_of(tmp_path, 's1/card-r1-learn')} == {'cand_card'}
    second = captured['card'][1]
    found = [e['task_id'] for e in second['examples']]
    # the rejected card on the learn items: 9 wrong, 3 right (strict on them); every shown item right
    assert second['round'] == 2 and len(found) == 17 and set(found[:12]) == set(learn)
    assert set(found[12:15]) == set(ids_of(sealed['lists']['shown']['attack']))
    assert set(found[15:]) == set(ids_of(sealed['lists']['shown']['guard']))
    assert [e['outcome'] for e in second['examples'][12:]] == ['pass'] * 5
    assert second['practice_ids'] == learn + shown


# ==== decisions.json: the items block and by_class ======================================================================
def test_decisions_carry_the_items_block_and_the_gains_by_class(tmp_path, monkeypatch):
    """The accepted card (strict): on the real items B is right 6 of 24 runs and the card 24 (D 18, +75.0 points), on
    the attack items 0 against 18 (+100.0), on the guard and calibration items 9 against 9 (0.0); B's parity: 100.0 on
    the calibration items, 25.0 on the real ones (75.0)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    state, _ = run(tmp_path)
    assert state['complete'], state['paused']
    decisions, sealed = read(tmp_path, 's1', 'decisions.json'), read(tmp_path, 's1', 'items.json')
    block = decisions['items']
    assert block['reason'] is None and block['items_sha256'] == sealed['record_sha256']
    assert block['counts'] == {'shown': {'attack': 3, 'guard': 2}, 'judging': {'attack': 6, 'guard': 3, 'calibration': 3},
                               'replaced': 0, 'unused': 0}
    assert block['gate'] == {'real': 8, 'attack': 6, 'guard': 3, 'calibration': 3, 'total': 20}
    assert [[(w['id'], w['evidence']) for w in plan['weaknesses']] for plan in block['plans']] == [
        [('w1', 3), ('w2', 3), ('w3', 3)]]
    assert [check['holds'] for check in block['checks']] == [True] and 'outcomes' not in block['checks'][0]
    assert block['replacement'] is None and block['quota'] == row(6, 3, 3, 3, 2)
    card = decisions['cards'][0]
    assert card['accepted']
    expected = {'real': (8, 18, 75.0, 6, 24), 'attack': (6, 18, 100.0, 0, 18), 'guard': (3, 0, 0.0, 9, 9),
                'calibration': (3, 0, 0.0, 9, 9)}
    for name, (n, D, gain, base, cand) in expected.items():
        got = card['by_class'][name]
        assert (got['n'], got['difference_sum'], got['gain_points'], got['baseline_runs_correct'],
                got['candidate_runs_correct']) == (n, D, gain, base, cand), name
    assert card['by_class']['parity'] == {'calibration_pass_points': 100.0, 'real_pass_points': 25.0,
                                          'parity_points': 75.0}
    # every program row carries by_class (None for a row without a gate); the stored unit records are unchanged
    assert all('by_class' in row for row in decisions['programs'])
    assert all((row['by_class'] is None) == ('per_item' not in row) for row in decisions['programs'])
    assert 'by_class' not in read(tmp_path, 's1', 'card-r1', 'decision.json')
    assert chain.recompute_decision(read(tmp_path, 's1', 'card-r1', 'decision.json')) == read(
        tmp_path, 's1', 'card-r1', 'decision.json')


def test_the_analyst_and_the_selector_are_charged_like_every_role_call(tmp_path, monkeypatch):
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    state, _ = run(tmp_path)
    assert state['complete'], state['paused']
    ledger = read(tmp_path, 'ledger.json')
    for unit, calls_files, n in (('s1/items-plan', ['analyst-item_analyst.json'], 1),
                                 ('s1/items', ['selector-%02d-item_selector.json' % b for b in (1, 2, 3)], 3)):
        sends = [send for name in calls_files for send in read(tmp_path, *unit.split('/'), 'calls', name)]
        assert len(sends) == n
        reported = sum(send['receipt']['usage']['total_tokens'] for send in sends)
        row_ = ledger['by_unit'][unit]
        assert row_['calls'] == n and row_['reported'] == reported and row_['charged'] >= reported > 0
    assert ledger['pending'] == {}


# ==== the check and the one replacement round ==========================================================================
def expected_round_2():
    """Round 2 of the lenient scenario by hand: the candidates without round 1's 17 items, the weak kinds in turn in
    pool order (judging 2 each, then shown 1 each), no guard and no calibration asked for."""
    taken = {i for values in ROUND_1.values() for i in values} | set(round_1_calibration())
    lists = {w: [i for i in range(20, 80) if i not in taken and topic(i) == kind]
             for w, kind in (('w1', 'date'), ('w2', 'person'), ('w3', 'place'))}
    out = {}
    for side, each in (('judging', 2), ('shown', 1)):
        need, picks = {w: each for w in lists}, {w: [] for w in lists}
        progress = True
        while progress:
            progress = False
            for w in lists:
                if need[w] and lists[w]:
                    picks[w].append(lists[w].pop(0))
                    need[w] -= 1
                    progress = True
        out[side] = [i for w in ('w1', 'w2', 'w3') for i in picks[w]]   # listing order: by weakness
    return out


def test_a_check_that_does_not_hold_gets_one_replacement_round_of_attack_items(tmp_path, monkeypatch):
    """lenient: B is right on every made item, so the attack items are not 5 points harder than the calibration items
    (6 of 6 against 3 of 3): items-plan-2 (the first plan and the counts only), items-2 (attack items only, as many per
    side as round 1 made, over plan 2's three weaknesses), items-check-2 (B on round 2's 6 attack items; the 3
    calibration items keep their check-1 outcomes); round 1's attack items stay on disk as 'replaced'; no third try."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    script = Script()
    state, _ = run(tmp_path, script, rule=lenient)
    assert state['complete'], state['paused']
    done = state['done_units']
    assert done[done.index('s1/diagnose'):done.index('s1/noise') + 1] == [
        's1/diagnose', 's1/items-plan', 's1/items', 's1/items-check', 's1/items-plan-2', 's1/items-2',
        's1/items-check-2', 's1/noise']
    check_1, check_2 = read(tmp_path, 's1', 'items-check', 'check.json'), read(tmp_path, 's1', 'items-check-2', 'check.json')
    assert (check_1['holds'], check_1['reason'], check_1['attack']['pass'], check_1['calibration']['pass']) == (
        False, 'attack_not_harder', 6, 3)
    # the revision request shows the first plan and the counts per weakness, never an item
    revise = [request_of(user) for purpose, unit, _, user in script.requests
              if purpose == 'item_analyst' and unit == 's1/items-plan-2']
    assert len(revise) == 1 and revise[0]['request'] == 'revise'
    assert revise[0]['revision']['check'] == {'attack': {'n': 6, 'right': 6}, 'calibration': {'n': 3, 'right': 3},
                                              'by_weakness': [['w1', 2, 2], ['w2', 2, 2], ['w3', 2, 2]],
                                              'margin_points': 5}
    assert [w['id'] for w in revise[0]['revision']['first_plan']['weaknesses']] == ['w1', 'w2', 'w3']
    counts = read(tmp_path, 's1', 'items-2', 'made.json')['counts']
    assert counts['judging'] == {'attack': 6, 'guard': 0, 'calibration': 0} and counts['shown'] == {'attack': 3, 'guard': 0}
    assert counts['round_1_attack'] == {'shown': 3, 'judging': 6}
    expected = expected_round_2()
    sealed = read(tmp_path, 's1', 'items.json')
    lists = sealed['lists']
    assert ids_of(lists['judging']['attack']) == [sq_id(i) for i in expected['judging']]
    assert ids_of(lists['shown']['attack']) == [sq_id(i) for i in expected['shown']]
    assert ids_of(lists['judging']['guard']) == [sq_id(i) for i in ROUND_1['judging_guard']]
    assert ids_of(lists['judging']['calibration']) == [sq_id(i) for i in round_1_calibration()]
    assert ids_of(lists['shown']['guard']) == [sq_id(i) for i in ROUND_1['shown_guard']]
    assert sorted(ids_of(lists['replaced'])) == sorted(sq_id(i) for i in ROUND_1['judging_attack'] + ROUND_1['shown_attack'])
    assert all(e['unit'] == 's1/items' for e in lists['replaced'])
    assert all(e['unit'] == 's1/items-2' for side in ('judging', 'shown') for e in lists[side]['attack'])
    for entry in lists['replaced']:  # kept on disk, never used
        assert (tmp_path / 'G' / entry['unit'] / 'items' / (entry['slot'] + '.json')).exists()
    assert sealed['final_round'] == 2 and sealed['plan_sha256'] == read(tmp_path, 's1', 'items-plan-2', 'analyst.json')[
        'plan_sha256']
    assert sealed['replacement'] == {'sides': ['shown', 'judging'], 'reason': None, 'plan_unit': 's1/items-plan-2',
                                     'counts': True}
    assert (check_2['cells'], check_2['reused'], check_2['attack']['n'], check_2['calibration']['n']) == (
        len(expected['judging']), 3, len(expected['judging']), 3)
    assert sorted(c['item_id'] for c in cells_of(tmp_path, 's1/items-check-2')) == sorted(
        sq_id(i) for i in expected['judging'])
    assert sealed['checks'] == [check_1, check_2] and not check_2['holds']
    # whatever check 2 says, there is no third attempt; J holds round 2's attack items
    assert not (tmp_path / 'G' / 's1' / 'items-plan-3').exists() and not (tmp_path / 'G' / 's1' / 'items-3').exists()
    assert Counter(unit for purpose, unit in script.calls if purpose == 'item_analyst') == {
        's1/items-plan': 1, 's1/items-plan-2': 1}
    J = [sq_id(i) for i in list(range(12, 20)) + expected['judging'] + ROUND_1['judging_guard'] + round_1_calibration()]
    assert all(plan['items'] == J for plan in gate_plans(tmp_path).values())
    # round 2's selector never saw a round-1 item (the registry holds them)
    round_2 = '\n'.join(text for purpose, unit, text in script.role_requests(('item_selector',)) if unit == 's1/items-2')
    assert round_2 and not [i for i in ROUND_1['judging_attack'] + ROUND_1['shown_attack'] if 'CTX%02d' % i in round_2]


def test_replacement_counts_follow_the_rule_of_b5():
    records = [items_.item_record(item='i%d' % n, cls='attack', weakness='w1', side=side, family='f%d' % n,
                                  source='selected', certificate=None, item_sha256='a' * 64)
               for n, side in enumerate(['judging'] * 5 + ['shown'] * 2)]
    plan = lambda n: {'weaknesses': [{'id': 'w%d' % (j + 1)} for j in range(n)]}
    table = {**prepare.default_item_quotas(), 'searchqa': row(10, 3, 7, 4, 6)}
    assert itemstage.replacement_counts('searchqa', plan(0), records, table) is None       # none kept: nothing replaced
    three = itemstage.replacement_counts('searchqa', plan(3), records, table)                # as many as round 1 made
    assert three['judging'] == {'attack': 5, 'guard': 0, 'calibration': 0} and three['shown'] == {'attack': 2, 'guard': 0}
    assert three['attack_split'] == {'judging': [['w1', 2], ['w2', 2], ['w3', 1]], 'shown': [['w1', 1], ['w2', 1], ['w3', 0]]}
    # fewer than three kept: min(round 1's count, 20 % of the side's total): judging 20 -> 4, shown 10 -> 2
    two = itemstage.replacement_counts('searchqa', plan(2), records, table)
    assert two['judging']['attack'] == 4 and two['shown']['attack'] == 2
    assert two['attack_split'] == {'judging': [['w1', 2], ['w2', 2]], 'shown': [['w1', 1], ['w2', 1]]}
    few = itemstage.replacement_counts('searchqa', plan(1), records[:1], table)
    assert few['judging']['attack'] == 1 and few['shown']['attack'] == 0


# ==== no judging-side item, gate item or reference reaches a role call ==================================================
@pytest.mark.parametrize('rule', [strict, lenient], ids=['one_round', 'two_rounds'])
def test_no_gate_or_judging_side_item_reaches_a_role_call(tmp_path, monkeypatch, rule):
    """Every role request of a full fake step (the analyst's, the selector's, the card writer's, the engineer's, the
    describer's) is scanned for the question, the snippet and the reference of every gate item and every judging-side
    item (final, replaced or unused): none appears. The selector sees candidates' public text only (no learn or gate
    item, no reference, no item id); writers see the final shown items, never a replaced one."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    script = Script()
    state, _ = run(tmp_path, script, rule=rule)
    assert state['complete'], state['paused']
    sealed = read(tmp_path, 's1', 'items.json')
    judging = [index(e['record']['item']) for e in itemstage.entries_of(sealed) if e['record']['side'] == 'judging']
    shown_final = [index(i) for cls in ('attack', 'guard') for i in ids_of(sealed['lists']['shown'][cls])]
    shown_replaced = [index(e['record']['item']) for e in sealed['lists']['replaced'] if e['record']['side'] == 'shown']
    private = [m for i in list(range(12, 20)) + judging for m in markers(i)]
    roles = script.role_requests()
    # strict accepts the card (one describer call); lenient accepts nothing, so nothing is described
    assert {purpose for purpose, _, _ in roles} == set(ROLE_PURPOSES) - (set() if rule is strict else {'describer'})
    for purpose, unit, text in roles:
        if purpose == 'item_selector':
            hidden = [m for i in range(20) for m in markers(i)] + ['REF', 'searchqa-', 'fam-']
        else:
            hidden = private + [m for i in shown_replaced for m in markers(i)]
        assert [m for m in hidden if m in text] == [], (purpose, unit)
    analyst = [text for purpose, _, text in roles if purpose == 'item_analyst']
    assert all('Q%02d ' % i in analyst[0] for i in range(12))       # the learn items do reach the analyst
    writers_text = '\n'.join(text for purpose, _, text in roles if purpose in ('card_writer', 'program_writer'))
    assert all('CTX%02d' % i in writers_text for i in shown_final)  # and the final shown items the writers


# ==== made items: views and vectors like practice items; a later step; members of a shared type ========================
ZB_LEARN_WRONG = ['zebralogic-%02d' % n for n in range(1, 12, 2)]   # the 5*3 learn puzzles (B wrong in every run)


def found_in(texts, marker):
    """A marker found in a request as written or as it stands inside a JSON string (a puzzle's newlines)."""
    text = '\n'.join(texts)
    return marker in text or json.dumps(marker, ensure_ascii=False)[1:-1] in text


def own_lines(item, items):
    """The clue lines of a puzzle (over 40 characters) that no other puzzle of ``items`` has: its markers."""
    lines = {line for line in item['public']['question'].split('\n') if len(line) > 40}
    for other in items:
        if other['task_id'] != item['task_id']:
            lines -= set(other['public']['question'].split('\n'))
    return sorted(lines)


def test_made_zebralogic_puzzles_join_j_with_views_and_vectors_from_one_batch(tmp_path, monkeypatch):
    """ZebraLogic (strict: B wrong on 5*3, right on 5*2): three weaknesses on the six 5*3 learn puzzles, quota 2 / 1 /
    2 and 1 / 1: judging attack w1, w2 (5*3), guard (5*2: every 5*2 learn puzzle right in all runs), calibration one of
    each size (the gate holds four of each), shown attack w1 (5*3) and guard (5*2). Seven certified puzzles that are no
    practice item: their views and vectors come from ONE embedding batch in list order (judging A, G, K, then shown),
    after the practice source's; every gate unit runs on the 8 real puzzles and the 5 judging ones; no judging puzzle
    reaches a writer."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    script = Script()
    services = build(tmp_path, script, order=('zebralogic',))
    batches, embed, captured = [], services.embed, []
    services.embed = lambda texts: batches.append(list(texts)) or embed(texts)
    card, propose = services.write_card, services.propose_programs
    services.write_card = lambda **kw: captured.append(kw) or card(**kw)
    services.propose_programs = lambda **kw: captured.append(kw) or propose(**kw)
    state = chain.run(tmp_path, 'G', services=services, sleep=lambda s: None)
    assert state['complete'], state['paused']
    plan = read(tmp_path, 's1', 'items-plan', 'analyst.json')['plan']
    assert [(w['id'], w['evidence'], w['spec']) for w in plan['weaknesses']] == [
        (w, ZB_LEARN_WRONG, {'sizes': ['5*3']}) for w in ('w1', 'w2', 'w3')]
    sealed = read(tmp_path, 's1', 'items.json')
    lists = sealed['lists']
    sizes = lambda entries: [e['record']['certificate']['size'] for e in entries]
    assert sizes(lists['judging']['attack']) == ['5*3', '5*3'] and [e['record']['weakness'] for e in lists['judging'][
        'attack']] == ['w1', 'w2']
    assert sizes(lists['judging']['guard']) == ['5*2'] and sizes(lists['judging']['calibration']) == ['5*2', '5*3']
    assert sizes(lists['shown']['attack']) == ['5*3'] and sizes(lists['shown']['guard']) == ['5*2']
    made = [e for cls in ('attack', 'guard', 'calibration') for e in lists['judging'][cls]] + [
        e for cls in ('attack', 'guard') for e in lists['shown'][cls]]
    pool_ids = {item['task_id'] for item in ZB_POOL}
    loaded = []
    for entry in made:
        item = store_.ItemStore(tmp_path / 'G' / entry['unit']).item(entry['slot'])
        loaded.append(item)
        assert item['task_id'] not in pool_ids and item['task_id'].startswith('zm3-') and item['part'] == 'made'
        assert entry['record']['source'] == 'made' and entry['record']['certificate']['text_sha256']
        assert entry['record']['item_sha256'] == items_.item_sha256('zebralogic', item)
    # two embedding batches in the process: the practice source, then the seven made puzzles in list order
    assert len(batches) == 2 and len(batches[0]) == len(ZB_POOL)
    assert batches[1] == [item['public']['question'] for item in loaded]
    check = read(tmp_path, 's1', 'items-check', 'check.json')
    assert (check['holds'], check['attack']['pass'], check['attack']['n'], check['calibration']['pass'],
            check['calibration']['n']) == (True, 0, 2, 1, 2)
    J = ['zebralogic-%02d' % n for n in range(12, 20)] + [item['task_id'] for item in loaded[:5]]
    for name, plan_record in gate_plans(tmp_path).items():
        assert plan_record['items'] == J, name
    # a routed arm mounted the made puzzles with their vectors (F with the card on the shown ones, cand_card on J)
    shown_ids = {item['task_id'] for item in loaded[5:]}
    routed = [c for c in cells_of(tmp_path, 's1/outcomes-card') if c['item_id'] in shown_ids]
    assert len(routed) == 2 and all(c['mount']['signature'] == 'puzzle_template' and c['mount']['distance'] is not None
                                    for c in routed)
    gate_made = [c for c in cells_of(tmp_path, 's1/card-r1') if c['item_id'] in set(J[8:])]
    assert len(gate_made) == 5 * R and all(c['correct'] is True for c in gate_made)
    # writers' examples and screen come from the learn and shown puzzles only
    practice = [i for i in ZB_SLICES['learn']] + [item['task_id'] for item in loaded[5:]]
    assert captured and all({e['task_id'] for e in kw['examples']} <= set(practice) for kw in captured)
    assert [kw['practice_ids'] for kw in captured if 'practice_ids' in kw] == [practice]
    # no role request holds a clue line of a judging or real gate puzzle that no other puzzle of the run has (a
    # writer's view keeps the head and the tail of the solver request; nearly every clue line survives)
    everything = ZB_POOL + loaded
    roles = [text for purpose, _, text in script.role_requests() if purpose != 'item_selector']
    hidden = loaded[:5] + [i for i in ZB_POOL if i['task_id'] in J[:8]]
    for item in hidden:
        lines = own_lines(item, everything)
        assert lines and not [line for line in lines if found_in(roles, line)], item['task_id']
    card_requests = [text for purpose, _, text in script.role_requests(('card_writer',))]
    assert all(any(found_in(card_requests, line) for line in own_lines(item, everything)) for item in loaded[5:])


def test_a_later_step_reads_the_earlier_steps_records_and_never_their_items(tmp_path, monkeypatch):
    """SearchQA (step 1, strict: the card is accepted, +100 points on each weakness's two attack items: B 0 of 6 runs,
    the card 6 of 6), then ZebraLogic (step 2): its analyst's experience log holds step 1's candidates and weaknesses
    with those gains; its maker's registry holds step 1's 17 items; none of them is in step 2's J."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    script = Script()
    state, _ = run(tmp_path, script, order=('searchqa', 'zebralogic'))
    assert state['complete'], state['paused']
    (payload,) = [request_of(user) for purpose, unit, _, user in script.requests
                  if purpose == 'item_analyst' and unit == 's2/items-plan']
    (step,) = payload['experience']
    assert step['step'] == 1 and step['bench'] == 'searchqa'
    # the card over J (20 items): D = 18 (real) + 18 (attack) -> 100 * 36 / (3 * 20) = 60.0 points
    assert step['candidates'][0] == {'candidate': 1, 'kind': 'card', 'decision': 'accepted', 'reason': None,
                                     'gain_points': 60.0, 'n': 20}
    assert all(row['kind'] == 'program' and row['decision'] == 'refused' for row in step['candidates'][1:])
    assert step['weaknesses'] == [{'id': w, 'description': text, 'accepted_candidates_on_attack': [
        {'candidate': 1, 'kind': 'card', 'n': 2, 'gain_points': 100.0}]}
        for w, (_, _, text) in zip(('w1', 'w2', 'w3'), WEAKNESSES)]
    text = json.dumps(payload['experience'])
    assert not [i for i in range(80) if 'Q%02d' % i in text or 'CTX%02d' % i in text or 'REF%02d' % i in text]
    assert read(tmp_path, 's2', 'items', 'made.json')['registry_records'] == 17
    step_1 = {e['record']['item'] for e in itemstage.entries_of(read(tmp_path, 's1', 'items.json'))}
    for plan_record in gate_plans(tmp_path, 2).values():
        assert not set(plan_record['items']) & step_1 and all(i.startswith(('zebralogic-', 'zm3-'))
                                                              for i in plan_record['items'])


def test_members_of_a_shared_type_keep_their_real_gate_slice(tmp_path, monkeypatch):
    """SearchQA (step 1) makes items; OfficeQA (step 2, no items: audit_bing_B36) joins SearchQA's type (no harm: the
    type has no skill yet), so SearchQA is a member of step 2's home type: its member arms run on SearchQA's REAL gate
    slice 12..19 -- never on step 1's J -- and OfficeQA's own units on its real slice."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    state, _ = run(tmp_path, order=('searchqa', 'officeqa'), rule=member_rule)
    assert state['complete'], state['paused']
    d2 = read(tmp_path, 's2', 'decisions.json')
    assert not d2['typing']['new_type'] and [row['bench'] for row in d2['shared_type']] == ['searchqa']
    assert d2['items']['reason'] == 'audit_bing_B36' and d2['items']['gate'] == {
        'real': 6, 'attack': 0, 'guard': 0, 'calibration': 0, 'total': 6}
    assert d2['cards'][0]['accepted'] and [m['bench'] for m in d2['cards'][0]['members']] == ['searchqa']
    plans = gate_plans(tmp_path, 2)
    real_sq, real_oq = [sq_id(i) for i in range(12, 20)], ['officeqa-%02d' % n for n in range(4, 10)]
    members = {name: p for name, p in plans.items() if 'member-searchqa' in name}
    assert {'member-searchqa-base', 'card-r1-member-searchqa'} <= set(members)
    for name, plan_record in members.items():
        assert plan_record['items'] == real_sq and 'items_sha256' not in plan_record, name
    for name, plan_record in plans.items():
        if name not in members:
            assert plan_record['items'] == real_oq, name
    step_1_j = read(tmp_path, 's1', 'noise', 'plan.json')['items']
    assert len(step_1_j) == 20 and step_1_j[:8] == real_sq
    assert d2['shared_type'][0]['routed_gate_items'] <= 8


def comparable(root, *, planned):
    """The records of a chain without what the item stage adds when it makes nothing (items.json, the decisions'
    items block and by_class, a gate plan's items_sha256)."""
    out = {}
    for rel, value in records(root).items():
        if planned and rel.endswith('/items.json'):
            continue
        if planned and rel.endswith('decisions.json'):
            value = {k: v for k, v in value.items() if k != 'items'}
            value['cards'] = [{k: v for k, v in r.items() if k != 'by_class'} for r in value['cards']]
            value['programs'] = [{k: v for k, v in r.items() if k != 'by_class'} for r in value['programs']]
            value['typing'] = {**value['typing'], 'no_harm': [{k: v for k, v in r.items() if k != 'by_class'}
                                                              for r in value['typing']['no_harm']]}
        if planned and rel.endswith('/plan.json'):
            value = {k: v for k, v in value.items() if k != 'items_sha256'}
        out[rel] = value
    return out


def test_benches_without_items_run_as_typed_v2_and_record_their_reason(tmp_path, monkeypatch):
    """OfficeQA (audit_bing_B36) and SpreadsheetBench (maker_not_built) under 'planned' with the default table: no
    diagnose, plan, items or check unit and no analyst or selector call; items.json records the reason; J = R; apart from
    what the stage adds, every record equals the same chain's under 'none'."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    order = ('officeqa', 'spreadsheetbench')
    script_a, script_b = Script(), Script()
    state, _ = run(tmp_path / 'a', script_a, order=order, stage='none')
    assert state['complete'], state['paused']
    state, _ = run(tmp_path / 'b', script_b, order=order, quotas=prepare.default_item_quotas())
    assert state['complete'], state['paused']
    assert [read(tmp_path / 'b', 's%d' % k, 'items.json')['reason'] for k in (1, 2)] == ['audit_bing_B36',
                                                                                        'maker_not_built']
    assert not [u for u in state['done_units'] if u.split('/')[-1].startswith(('diagnose', 'items'))]
    assert not [p for p, _ in script_b.calls if p.startswith('item_')]
    for k, bench in ((1, 'officeqa'), (2, 'spreadsheetbench')):
        real = list(BENCHES[bench][1]['gate'])
        assert read(tmp_path / 'b', 's%d' % k, 'noise', 'plan.json')['items'] == real
        assert read(tmp_path / 'b', 's%d' % k, 'decisions.json')['items']['counts']['judging'] == {
            'attack': 0, 'guard': 0, 'calibration': 0}
    assert comparable(tmp_path / 'b', planned=True) == comparable(tmp_path / 'a', planned=False)
    assert Counter(script_b.calls) == Counter(script_a.calls)


def test_the_default_flow_is_unchanged(tmp_path, monkeypatch):
    """A manifest without the field and one with item_stage 'none' run the same chain byte for byte (apart from the
    volatile keys): no stage unit, no items.json, no items block or by_class, no items_sha256, typed-v2's state."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    state_a, _ = run(tmp_path / 'a', Script(), stage=None)
    state_b, _ = run(tmp_path / 'b', Script(), stage='none')
    assert state_a['complete'] and state_b['complete']
    assert records(tmp_path / 'a') == records(tmp_path / 'b')
    found = records(tmp_path / 'a')
    assert not [rel for rel in found if 'items' in rel.split('/')[-1] or 'diagnose' in rel]
    assert 'items' not in found['s1/decisions.json'] and 'by_class' not in json.dumps(found)
    assert 'items_sha256' not in json.dumps(found) and 'item_stage' not in state_a


# ==== P1's program learning takes the shown items beside the learn items ================================================
def test_the_probe_and_the_paid_round_run_on_the_learn_and_the_shown_items(tmp_path, monkeypatch):
    """Under 'repair' (no free repair round, the one paid round): the proposal's zero-call probe and its paid learn
    round cover the 12 learn items and then the 5 shown items, in that order."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    state, _ = run(tmp_path, program_learning='repair',
                   limits={'program_repair_rounds': 0, 'program_paid_feedback': 1})
    assert state['complete'], state['paused']
    practice = [sq_id(i) for i in list(range(12)) + ROUND_1['shown_attack'] + ROUND_1['shown_guard']]
    probe = read(tmp_path, 's1', 'program-1-probe-0', 'probe.json')
    assert probe['items'] == 17 and [row[0] for row in probe['per_item']] == practice
    paid = cells_of(tmp_path, 's1/program-1-learn')
    assert sorted(c['item_id'] for c in paid) == sorted(practice) and {c['arm'] for c in paid} == {'cand_program'}
    assert read(tmp_path, 's1', 'decisions.json')['programs'][-1]['learn']['items'] == 17


# ==== the analyst's and the selector's infrastructure rule, an unreadable plan ===========================================
def failed_receipt():
    return {'ok': False, 'response': None, 'finish_reason': None, 'usage': {}, 'error_type': 'timeout',
            'returned_model': None}


def failing(times, reply, test=lambda system, user: True):
    """A scripted reply that answers with an infrastructure failure on its first ``times`` matching requests."""
    left = [times]

    def answer(system, user):
        if left[0] and test(system, user):
            left[0] -= 1
            return failed_receipt()
        return reply(system, user)
    return answer


def test_an_analyst_without_a_verdict_is_retried_once_then_pauses(tmp_path, monkeypatch):
    """One infrastructure failure: one automatic retry after 60 s, no record of the failed call, the plan as usual.
    Two: the chain pauses analyst_unavailable without a plan record; the owner's recovery asks once more."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    sleeps = []
    script = Script({'replies': {'item_analyst': failing(1, analyst_reply)}})
    services = build(tmp_path / 'a', script)
    state = chain.run(tmp_path / 'a', 'G', services=services, sleep=sleeps.append)
    assert state['complete'], state['paused']
    assert sleeps == [60] and 's1/items-plan/analyst' in state['infra_retries']
    record = read(tmp_path / 'a', 's1', 'items-plan', 'analyst.json')
    assert record['status'] == 'ok' and len(record['attempts']) == 1 and len(record['plan']['weaknesses']) == 3
    assert len(read(tmp_path / 'a', 's1', 'items-plan', 'calls', 'analyst-item_analyst.json')) == 2
    script = Script({'replies': {'item_analyst': failing(2, analyst_reply)}})
    services = build(tmp_path / 'b', script)
    state = chain.run(tmp_path / 'b', 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'analyst_unavailable' and state['paused']['unit'] == 's1/items-plan'
    assert not (tmp_path / 'b' / 'G' / 's1' / 'items-plan' / 'analyst.json').exists()
    recovery(tmp_path / 'b')
    state = chain.run(tmp_path / 'b', 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    assert Counter(u for p, u in script.calls if p == 'item_analyst') == {'s1/items-plan': 3}


def test_a_selector_batch_without_a_verdict_is_retried_once_and_finished_batches_are_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    sleeps = []
    batch_2 = lambda system, user: 'CTX45' in user
    script = Script({'replies': {'item_selector': failing(1, selector_reply, batch_2)}})
    services = build(tmp_path, script)
    state = chain.run(tmp_path, 'G', services=services, sleep=sleeps.append)
    assert state['complete'], state['paused']
    assert sleeps == [60] and 's1/items/selector' in state['infra_retries']
    sent = [user for p, u, _, user in script.requests if p == 'item_selector' and u == 's1/items']
    assert len(sent) == 4 and sum('CTX20' in user for user in sent) == 1 and sum('CTX45' in user for user in sent) == 2
    assert ids_of(read(tmp_path, 's1', 'items.json')['lists']['judging']['attack']) == [
        sq_id(i) for i in ROUND_1['judging_attack']]


def test_an_unreadable_plan_keeps_no_weakness_and_the_step_goes_on(tmp_path, monkeypatch):
    """Prose twice: the plan has no weakness; the 20 % rule draws 2 judging and 1 shown attack items like calibration
    items (weakness None); without a description the selector is never called; SearchQA's judging guard shortfall (3)
    joins the calibration items (7 + 3); no replacement round (no weakness kept)."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    script = Script({'replies': {'item_analyst': 'I would rather not plan.'}})
    state, _ = run(tmp_path, script)
    assert state['complete'], state['paused']
    record = read(tmp_path, 's1', 'items-plan', 'analyst.json')
    assert record['status'] == 'unreadable' and record['plan']['unreadable'] and len(record['attempts']) == 2
    assert not [c for c in script.calls if c[0] == 'item_selector']
    sealed = read(tmp_path, 's1', 'items.json')
    counts = {side: {cls: len(entries) for cls, entries in sealed['lists'][side].items()} for side in ('judging', 'shown')}
    assert counts == {'judging': {'attack': 2, 'guard': 0, 'calibration': 10}, 'shown': {'attack': 1, 'guard': 0}}
    assert {e['record']['weakness'] for e in sealed['lists']['judging']['attack']} == {None}
    assert sealed['replacement'] is None and sealed['plans'][0]['unreadable'] and sealed['plans'][0]['kept'] == 0
    assert not (tmp_path / 'G' / 's1' / 'items-plan-2').exists()


# ==== resume: kill inside each new unit ==================================================================================
def kill_plan_record(monkeypatch):
    """After the analyst's call (its send and receipt are in the calls file) and before ``analyst.json``."""
    original, hit = chain._Run.record, []

    def record(self, unit, name, compute):
        if (unit, name) == ('s1/items-plan', itemstage.PLAN_RECORD) and not hit:
            hit.append(unit)
            compute()
            raise RuntimeError('killed before the plan record')
        return original(self, unit, name, compute)
    monkeypatch.setattr(chain._Run, 'record', record)


def kill_selector_batch(monkeypatch):
    """In the middle of making: after the selector's second batch call, before that batch's record."""
    original, hit = store_.ItemStore.once, []

    def once(self, parts, compute):
        if tuple(parts) == ('selector', 'batch-02.json') and self.root.parent.name == 's1' and self.root.name == 'items' \
                and not hit:
            hit.append(parts)
            compute()
            raise RuntimeError('killed before the batch record')
        return original(self, parts, compute)
    monkeypatch.setattr(store_.ItemStore, 'once', once)


def kill_slot_records(monkeypatch):
    """In the middle of making: after three slot records of round 1, before the fourth."""
    original, seen = store_.ItemStore.write_slot, []

    def write_slot(self, name, **kw):
        if self.root.name == 'items' and len(seen) == 3:
            seen.append(name)
            raise RuntimeError('killed between two slot records')
        seen.append(name)
        return original(self, name, **kw)
    monkeypatch.setattr(store_.ItemStore, 'write_slot', write_slot)


def kill_items_json(monkeypatch):
    """After every unit of the stage, before ``items.json``."""
    original, hit = itemstage._seal, []

    def seal(path, fields):
        if not hit:
            hit.append(path)
            raise RuntimeError('killed before items.json')
        return original(path, fields)
    monkeypatch.setattr(itemstage, '_seal', seal)


KILLS = {'plan_record': (kill_plan_record, ()), 'selector_batch': (kill_selector_batch, ()),
         'slot_records': (kill_slot_records, ()), 'before_replacement': (None, (('item_analyst', 's1/items-plan-2'),)),
         'items_json': (kill_items_json, ())}


@pytest.mark.parametrize('point', sorted(KILLS))
def test_the_stage_resumes_at_each_point_without_repeating_a_call_or_changing_a_record(tmp_path, monkeypatch, point):
    """The two-round scenario (lenient), killed after the analyst's call before its record, after the selector's
    second batch call before its record, between two slot records, between the check and the replacement (the
    analyst's revision call is lost), and before items.json: the resumed run makes only the missing call (once) and
    every record equals an uninterrupted run's; a later resume of the complete chain sends nothing."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    reference, resumed = tmp_path / 'a', tmp_path / 'b'
    script_a = Script()
    state, _ = run(reference, script_a, rule=lenient)
    assert state['complete'], state['paused']
    kill, broken = KILLS[point]
    script_b = Script(broken=broken)
    services = build(resumed, script_b, rule=lenient)
    with monkeypatch.context() as patched:
        if kill is not None:
            kill(patched)
        state = chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    assert state['paused']['reason'] == 'exception:RuntimeError', state['paused']
    assert not (resumed / 'G' / 's1' / 'items.json').exists()
    recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    found, expected = records(resumed), records(reference)
    assert sorted(found) == sorted(expected)
    for rel in expected:
        assert found[rel] == expected[rel], rel
    assert {'s1/items.json', 's1/items-plan/analyst.json', 's1/items-2/made.json', 's1/items-check-2/check.json'} <= set(
        expected)
    assert Counter(script_b.calls) == Counter(script_a.calls)          # no call whose record exists was repeated
    assert len(script_b.requests) == len(script_a.requests) + len(broken)
    before, files = len(script_b.requests), records(resumed)
    assert chain.run(resumed, 'G', services=services, resume=True)['complete']
    assert len(script_b.requests) == before and records(resumed) == files


# ==== integration with P1's program learning: an accepted archive package under 'planned' ==========================
def planned_archive(monkeypatch, base):
    """A fixture package of chain G on SearchQA (one clean helper record P, through P1's ``fixture_package`` under
    ``base``) and the run options: 'repair' with one free repair round (the smoke's writer answers SearchQA's repair
    with prose, then a refused program: the round ends 'screen') and the one paid round, the sealed archive, and the
    outcome rule ``with_package`` -- a mount with P enabled is right on every item, any other ``strict`` without the
    card's help. Returns (package, P's record, the kwargs of ``build``)."""
    from tests.test_typed3_program_learning import ENTRY, fixture_package, program
    from skillopt.execskill.typed import archives
    made, failed = writers.build_procedure(ENTRY, program('pkg'), bench='searchqa', evidence='smoke',
                                           engineer_call='a' * 64, step=1, ordinal=9)
    assert failed is None
    record = made.to_json()
    package = fixture_package(monkeypatch, base, 'searchqa', record, 'sq-fixture-accepted')

    def with_package(bench, item, mounted):
        if record['id'] in [p['id'] for p in mounted.get('enabled') or []]:
            return 'pass'
        return strict(bench, item, {**mounted, 'card_text': None})
    return package, record, dict(rule=with_package, program_learning='repair', archive=archives.sealed('index'),
                                 limits={'program_repair_rounds': 1, 'program_paid_feedback': 1})


def test_an_accepted_archive_package_under_planned_items_runs_on_j_and_feeds_the_writers_from_its_cells(tmp_path,
                                                                                                      monkeypatch):
    """A fixture package of chain G on SearchQA (one record P, a clean helper program) under 'repair' and 'planned'
    (the round-1 lists of ``ROUND_1``). The outcome rule: a mount with P enabled is right on every item; otherwise
    ``strict`` without the card's help (B and F alike: the card round gains nothing, the item stage is round 1's).
    By hand: on J (gate 12..19, then the 12 judging items) F is right on 15, 19, the guard and the calibration items
    (8 of 20), the package on all 20 (fired on 19: the calibration item 75 lies beyond the type's p95 threshold, no
    type, so no candidate is applied there; B is right on it, a counting question): accepted as candidate 0. Then
    (P1 F3 with P2b T6) s1/outcomes-archive runs the package once on the 12 learn AND the 5 shown items; the
    engineer's examples come from those cells -- its learn examples (12 right: the 6 successes the bound shows) and
    then the shown items' (attack 28 29 30, wrong under F, right with the package; guard 35 39) -- 11 examples, every
    one right, where F's cells would have shown 9 learn and 3 shown failures. The engineer's candidate (F4 with J) is
    probed, repaired and paid on the 17 practice items with P forced and the post-archive cells as its side, and
    gated on J with P forced, never offered; every gate unit of the step (the package's and the candidate's
    included) runs on J and names the sealed item list."""
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    package, record, kw = planned_archive(monkeypatch, tmp_path)
    pid = record['id']
    script = Script()
    state, services, captured = captured_run(tmp_path, script, **kw)
    assert state['complete'], state['paused']
    sealed = read(tmp_path, 's1', 'items.json')
    assert ids_of(sealed['lists']['shown']['attack']) == [sq_id(i) for i in ROUND_1['shown_attack']]
    learn = [sq_id(i) for i in range(12)]
    shown = [sq_id(i) for i in ROUND_1['shown_attack'] + ROUND_1['shown_guard']]
    J = [sq_id(i) for i in list(range(12, 20)) + ROUND_1['judging_attack'] + ROUND_1['judging_guard']
         + [index(e['record']['item']) for e in sealed['lists']['judging']['calibration']]]
    assert sq_id(75) in J
    decisions = read(tmp_path, 's1', 'decisions.json')
    archive, engineer = decisions['programs'][0], decisions['programs'][-1]
    assert (archive['origin'], archive['package'], archive['accepted'], archive['fired_items']) == (
        'archive', package, True, 19)
    assert (archive['baseline']['unit'], engineer['baseline']['unit']) == ('s1/outcomes', 's1/program-0-gate')
    # every gate unit of the step runs on J and names the sealed list; the package and the candidate are forced
    plans = gate_plans(tmp_path)
    assert {'program-0-gate', 'program-1-gate'} <= set(plans)
    assert all(plan['items'] == J and plan['items_sha256'] == sealed['record_sha256'] for plan in plans.values())
    unrouted = {'applied': False, 'kind': 'program', 'reason': 'distance_above_p95'}
    for unit, ids in (('s1/program-0-gate', [pid]), ('s1/program-1-gate', [pid, engineer['procedure_id']])):
        cells = cells_of(tmp_path, unit)
        assert sorted(c['item_id'] for c in cells) == sorted(J * R) and all(c['correct'] is True for c in cells)
        for cell in cells:
            assert cell['mount']['candidate'] == unrouted if cell['item_id'] == sq_id(75) else (
                cell['mount']['candidate']['ids'] == ids and cell['mount']['programs_offered'] == [])
    # the post-archive unit: the package once on the learn and the shown items
    after = {c['item_id']: c for c in cells_of(tmp_path, 's1/outcomes-archive')}
    assert sorted(after) == sorted(learn + shown)
    assert all(c['arm'] == 'cand_program' and c['mount']['candidate']['ids'] == [pid] and c['correct'] is True
               for c in after.values())
    before = {c['item_id']: c['correct'] for c in cells_of(tmp_path, 's1/outcomes') if c['arm'] == 'F'}
    assert sorted(before) == sorted(learn + shown)
    assert [before[i] for i in shown] == [False, False, False, True, True]
    assert sum(before[i] is False for i in learn) == 9
    # the engineer's examples: the post-archive cells, the learn examples then the shown items' (attack, then guard)
    (proposal,) = captured['engineer']
    examples = [(e['task_id'], e['outcome']) for e in proposal['examples']]
    assert len(examples) == 11 and {outcome for _, outcome in examples} == {'pass'}
    assert {i for i, _ in examples[:6]} <= set(learn)
    assert {i for i, _ in examples[6:9]} == {sq_id(i) for i in ROUND_1['shown_attack']}
    assert {i for i, _ in examples[9:]} == {sq_id(i) for i in ROUND_1['shown_guard']}
    # its probe and its paid round: the 17 practice items, P forced, against the post-archive cells
    probe = read(tmp_path, 's1', 'program-1-probe-0', 'probe.json')
    assert [row[0] for row in probe['per_item']] == learn + shown
    assert (probe['learned'], probe['background']) == ('s1/outcomes-archive', [[pid, record['record_sha256']]])
    # its repair request's coverage report: the 17 practice items, no item of J
    (repair,) = [json.loads(user) for purpose, unit, _, user in script.requests
                 if purpose == 'program_writer' and unit == 's1/program-1-repair-1'][:1]
    assert {key: repair['coverage'][key] for key in ('items', 'routed', 'fired', 'noted')} == {
        'items': 17, 'routed': 17, 'fired': 17, 'noted': 0}
    assert not [i for i in J if 'Q%02d ' % index(i) in json.dumps(repair)]
    paid = cells_of(tmp_path, 's1/program-1-learn')
    assert sorted(c['item_id'] for c in paid) == sorted(learn + shown)
    assert all(c['mount']['candidate']['ids'] == [pid, engineer['procedure_id']] for c in paid)
    assert {key: engineer['learn'][key] for key in ('against', 'items', 'fixed', 'broken')} == {
        'against': 's1/outcomes-archive', 'items': 17, 'fixed': 0, 'broken': 0}
    assert decisions['program_learning']['outcomes_with_archive']['learn'] == {
        'items': 12, 'cells': 12, 'pass': 12, 'fail': 0, 'unknown': 0}
    assert decisions['items']['items_sha256'] == sealed['record_sha256'] and archive['by_class'] is not None


@pytest.mark.parametrize('point', ['post_archive_cell', 'proposal_receipt'])
def test_the_planned_archive_step_resumes_without_repeating_a_call_or_changing_a_record(tmp_path, monkeypatch, point):
    """The scenario above killed (a process death, no pause) at the solve of the shown attack item 28 inside
    s1/outcomes-archive, or after the engineer's proposal receipt reached its calls file and before proposals.json
    (P1 F5's window; SearchQA's proposal is prose, then its format retry, then a fix: three receipts). The resumed step
    runs only the missing cells, replays the saved receipts, rebuilds the engineer's learn and shown examples from the
    stored post-archive cells, and every record equals an uninterrupted run's; no call is sent twice."""
    from tests.test_typed3_program_learning import Kill
    monkeypatch.setattr(chain, '_now', lambda: NOW)
    package, record, kw = planned_archive(monkeypatch, tmp_path)
    reference, resumed = tmp_path / 'a', tmp_path / 'b'
    script_a = Script()
    state, _ = run(reference, script_a, **kw)
    assert state['complete'], state['paused']
    assert Counter(script_a.calls)[('program_writer', 's1/programs')] == 3
    script_b, hit = Script(), []
    services = build(resumed, script_b, **kw)
    if point == 'post_archive_cell':
        solve_ = services.solve_fn

        def killing(bench, item, mounted, **rest):
            if rest['unit'] == 's1/outcomes-archive' and item['task_id'] == sq_id(28) and not hit:
                hit.append(item['task_id'])
                raise Kill()
            return solve_(bench, item, mounted, **rest)
        services.solve_fn = killing
    else:
        original = chain._Run.record

        def record_(self, unit, name, compute):
            if (unit, name) == ('s1/programs', 'proposals.json') and not hit:
                compute()
                hit.append(unit)
                raise Kill()
            return original(self, unit, name, compute)
        monkeypatch.setattr(chain._Run, 'record', record_)
    with pytest.raises(Kill):
        chain.run(resumed, 'G', services=services, sleep=lambda s: None)
    assert hit and not (resumed / 'G' / 's1' / 'programs' / 'proposals.json').exists()
    if point == 'post_archive_cell':
        assert not any(c['item_id'] == sq_id(28) for c in cells_of(resumed, 's1/outcomes-archive'))
    recovery(resumed)
    state = chain.run(resumed, 'G', services=services, resume=True, sleep=lambda s: None)
    assert state['complete'], state['paused']
    found, expected = records(resumed), records(reference)
    assert sorted(found) == sorted(expected) and 's1/outcomes-archive/done.json' in expected
    for rel in expected:
        assert found[rel] == expected[rel], rel
    assert Counter(script_b.calls) == Counter(script_a.calls) and len(script_b.requests) == len(script_a.requests)
