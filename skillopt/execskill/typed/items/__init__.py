"""typed-v3 item stage tools (docs/handoff/typed-v3/CHAIN-DECISIONS.md T3 to T5; build brief P2a): the TOOLS of a
step's item stage, called by the chain's units (P2b). Nothing here runs a unit, writes ``items.json`` or decides a gate.

This module holds the data and pure functions every maker shares:

- ``ITEM_QUOTAS``: the table of T5 (per bench the judging-side attack / guard / calibration counts and the shown-side
  attack / guard counts); a bench absent from a table, or with all zeros, gets no made items;
- the constants of T4 and T3.4 and ``counts`` (the exact per-class, per-side counts of one step, with the split of the
  attack counts over the kept weaknesses) and ``check_plan`` / ``check_items`` (the plan check of T3.4, in exact
  fractions);
- ``item_record`` (the validating constructor of an item record) and ``item_sha256`` (the hash of everything a
  solver and the judge read of an item);
- ``largest_remainder`` (sizes or task types in the proportion of the real gate slice);
- ``MakeInput`` (the one argument of every maker's entry point) and the registry ``MAKERS`` (bench -> maker; resolved
  on first access, PEP 562, so that importing this module stays light).

Counts are integers, every comparison of rates is exact (``fractions.Fraction``); a float never decides a count.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from skillopt.continual_eval.core import require

from .. import ORDER
from ..library import canonical_sha256

RECORD_VERSION = 'typed-v3-items-1'   # the format of the records written by this package
SIDES = ('shown', 'judging')
CLASSES = ('attack', 'guard', 'calibration')
SHOWN_CLASSES = ('attack', 'guard')   # the shown side has no calibration class (T5)
SOURCES = ('made', 'selected')
RECORD_KEYS = ('item', 'class', 'weakness', 'side', 'family', 'source', 'certificate', 'item_sha256')
WEAKNESS_ID = re.compile(r'^w[1-9][0-9]*$')
HEX64 =re.compile(r'^[0-9a-f]{64}$')

# T5: judging-side attack / guard / calibration and shown-side attack / guard per bench (owner approved 4 : 3 : 3).
ITEM_QUOTAS = {
    'searchqa': {'judging': {'attack': 60, 'guard': 45, 'calibration': 45}, 'shown': {'attack': 27, 'guard': 13}},
    'officeqa': {'judging': {'attack': 32, 'guard': 24, 'calibration': 24}, 'shown': {'attack': 16, 'guard': 8}},
    'zebralogic': {'judging': {'attack': 80, 'guard': 60, 'calibration': 60}, 'shown': {'attack': 40, 'guard': 20}},
    'spreadsheetbench': {'judging': {'attack': 24, 'guard': 18, 'calibration': 18}, 'shown': {'attack': 13, 'guard': 7}},
    'alfworld': {'judging': {'attack': 16, 'guard': 12, 'calibration': 12}, 'shown': {'attack': 8, 'guard': 4}},
}

# T4: a weakness is kept only with at least EVIDENCE_MIN_ITEMS learn items, each failed by B in at least
# EVIDENCE_MIN_FAILED_RUNS of its R runs (a failed run: an outcome that is not True; a model-side unknown scores 0).
EVIDENCE_MIN_ITEMS = 3
EVIDENCE_MIN_FAILED_RUNS = 2
# T4: with fewer than MIN_KEPT_WEAKNESSES kept weaknesses the attack share of a side falls to REDUCED_ATTACK_SHARE of
# that side's total, rounded down; the judging guard count is unchanged and the rest is calibration; the shown guard
# count takes the rest of the shown total (this shown-side rule is brief P2a's decision: T4 speaks of judging items).
MIN_KEPT_WEAKNESSES = 3
REDUCED_ATTACK_SHARE = Fraction(1, 5)
# T3.4: the plan holds when the attack items' pass rate is at least CHECK_MARGIN_POINTS points below the calibration
# items' pass rate (B once on the judging-side attack and calibration items).
CHECK_MARGIN_POINTS = 5
CHECK_RULE = 'attack pass rate <= calibration pass rate - %d points (exact fractions)' % CHECK_MARGIN_POINTS


# ---- quotas and counts ---------------------------------------------------------------------------------------------
def quota_row(bench, quotas=ITEM_QUOTAS):
    """The bench's row of a quota table, validated, or None when the bench is absent or all its counts are zero."""
    require(isinstance(quotas, dict), 'A quota table is a dict of benches')
    row = quotas.get(bench)
    if row is None:
        return None
    require(isinstance(row, dict) and set(row) == set(SIDES), 'A quota row holds the judging and the shown side')
    require(isinstance(row['judging'], dict) and set(row['judging']) == set(CLASSES)
            and isinstance(row['shown'], dict) and set(row['shown']) == set(SHOWN_CLASSES),
            'A quota row: judging attack/guard/calibration and shown attack/guard')
    values = list(row['judging'].values()) + list(row['shown'].values())
    require(all(type(value) is int and value >= 0 for value in values), 'Quota counts are integers >= 0')
    if not any(values):
        return None
    return {'judging': dict(row['judging']), 'shown': dict(row['shown'])}


def split_in_turn(total, ways):
    """``total`` items given to ``ways`` weaknesses in turn (round robin in plan order): each gets total // ways, and
    the first total % ways weaknesses in plan order get one more."""
    require(type(total) is int and total >= 0 and type(ways) is int and ways >= 1, 'A count over at least one way')
    return [total // ways + (1 if index < total % ways else 0) for index in range(ways)]


def reduced_attack(total):
    """floor(REDUCED_ATTACK_SHARE * total), in integers."""
    require(type(total) is int and total >= 0, 'A count')
    return total * REDUCED_ATTACK_SHARE.numerator // REDUCED_ATTACK_SHARE.denominator


def counts(bench, kept_weaknesses, quotas=ITEM_QUOTAS):
    """The exact counts of one step's made or selected items of ``bench``.

    ``kept_weaknesses``: the number of kept weaknesses, or their ids in plan order (``validate_plan``'s
    ``[w['id'] for w in plan['weaknesses']]``). Rule (T4, T5): with at least MIN_KEPT_WEAKNESSES kept weaknesses the
    quota row as it is ('quota'); with fewer (0 included) judging attack = floor(20 % of the judging total), judging
    guard unchanged, calibration = the rest, and shown attack = floor(20 % of the shown total), shown guard = the rest
    ('reduced_attack'); a bench absent from the table or at zero: every count 0 ('no_items'). ``attack_split``: per
    side, the attack count of each kept weakness, ``[[id, count], ...]`` in plan order (``split_in_turn``; ids w1, w2,
    ... when only a number is given); empty without kept weaknesses (the attack items are then drawn like
    calibration items, weakness None)."""
    if isinstance(kept_weaknesses, int) and not isinstance(kept_weaknesses, bool):
        require(kept_weaknesses >= 0, 'A number of kept weaknesses >= 0')
        ids = ['w%d' % (index + 1) for index in range(kept_weaknesses)]
    else:
        ids = list(kept_weaknesses)
        require(all(isinstance(value, str) and value for value in ids) and len(set(ids)) == len(ids),
                'Kept weakness ids are distinct strings')
    row = quota_row(bench, quotas)
    zero = {'judging': {name: 0 for name in CLASSES}, 'shown': {name: 0 for name in SHOWN_CLASSES}}
    if row is None:
        out, rule = zero, 'no_items'
    elif len(ids) >= MIN_KEPT_WEAKNESSES:
        out, rule = row, 'quota'
    else:
        judging_total, shown_total = sum(row['judging'].values()), sum(row['shown'].values())
        attack, shown_attack = reduced_attack(judging_total), reduced_attack(shown_total)
        guard = row['judging']['guard']
        require(attack + guard <= judging_total, 'The reduced attack count and the guard count fit the judging total')
        out = {'judging': {'attack': attack, 'guard': guard, 'calibration': judging_total - attack - guard},
               'shown': {'attack': shown_attack, 'guard': shown_total - shown_attack}}
        rule = 'reduced_attack'
    split = {side: ([[w, n] for w, n in zip(ids, split_in_turn(out[side]['attack'], len(ids)))] if ids else [])
             for side in SIDES}
    return {'bench': bench, 'weaknesses': len(ids), 'weakness_ids': ids, 'rule': rule,
            'judging': dict(out['judging']), 'shown': dict(out['shown']), 'attack_split': split,
            'totals': {side: sum(out[side].values()) for side in SIDES}}


def check_counts(found):
    """A ``counts`` record (or a reduced one P2b builds for a replacement round), validated: the classes of both
    sides as integers >= 0 and an attack split that adds up to each side's attack count when it is not empty."""
    require(isinstance(found, dict) and isinstance(found.get('judging'), dict) and isinstance(found.get('shown'), dict),
            'A counts record with both sides')
    require(set(found['judging']) == set(CLASSES) and set(found['shown']) == set(SHOWN_CLASSES)
            and all(type(v) is int and v >= 0 for side in SIDES for v in found[side].values()),
            'Counts of the registered classes, integers >= 0')
    split = found.get('attack_split') or {side: [] for side in SIDES}
    ids = list(found.get('weakness_ids') or [])
    for side in SIDES:
        rows = split.get(side) or []
        require(all(isinstance(row, (list, tuple)) and len(row) == 2 and type(row[1]) is int and row[1] >= 0
                    for row in rows), 'An attack split row is [weakness id, count]')
        require([row[0] for row in rows] == ids if rows else True, 'The attack split follows the kept weaknesses')
        require(not rows or sum(row[1] for row in rows) == found[side]['attack'],
                'The attack split adds up to the attack count of the side')
    return found


# ---- the plan check (T3.4) -----------------------------------------------------------------------------------------
def _rate(passed, n):
    return Fraction(100 * passed, n)


def _shown_fraction(value):
    return {'points': round(float(value), 4), 'exact': '%d/%d' % (value.numerator, value.denominator)}


def check_plan(attack_pass, attack_n, calibration_pass, calibration_n):
    """T3.4: holds iff 100 * attack_pass / attack_n <= 100 * calibration_pass / calibration_n - CHECK_MARGIN_POINTS,
    compared exactly; a class without items never holds (reason ``empty_class``). The float ``points`` are for the
    record only."""
    for name, passed, n in (('attack', attack_pass, attack_n), ('calibration', calibration_pass, calibration_n)):
        require(type(passed) is int and type(n) is int and 0 <= passed <= n, 'Pass counts of %s are 0..n' % name)
    out = {'rule': CHECK_RULE, 'margin_points': CHECK_MARGIN_POINTS,
           'attack': {'n': attack_n, 'pass': attack_pass}, 'calibration': {'n': calibration_n, 'pass': calibration_pass}}
    if not attack_n or not calibration_n:
        return {**out, 'holds': False, 'reason': 'empty_class', 'difference_points': None}
    attack, calibration = _rate(attack_pass, attack_n), _rate(calibration_pass, calibration_n)
    out['attack']['rate'] = _shown_fraction(attack)
    out['calibration']['rate'] = _shown_fraction(calibration)
    holds = attack + CHECK_MARGIN_POINTS <= calibration
    return {**out, 'holds': holds, 'reason': 'holds' if holds else 'attack_not_harder',
            'difference_points': _shown_fraction(calibration - attack)}


def check_items(records, outcomes):
    """The items check of T3.4 from the judging-side item records and B's ONE run on them (``outcomes``: {item id:
    True / False / None}; only True passes): counts per class and, for the attack items, per weakness (counts only:
    what ``items-plan-2`` may show the analyst), and ``check_plan``. Guard items are not read here."""
    rows = [check_record(record) for record in records]
    require(all(row['side'] == 'judging' for row in rows), 'The check reads judging-side items only')
    tally = {name: {'n': 0, 'pass': 0} for name in ('attack', 'calibration')}
    by_weakness = {}
    for row in rows:
        if row['class'] not in tally:
            continue
        require(row['item'] in outcomes, 'An outcome for every checked item: ' + row['item'])
        passed = outcomes[row['item']] is True
        tally[row['class']]['n'] += 1
        tally[row['class']]['pass'] += passed
        if row['class'] == 'attack':
            entry = by_weakness.setdefault(row['weakness'] or 'none', {'n': 0, 'pass': 0})
            entry['n'] += 1
            entry['pass'] += passed
    found = check_plan(tally['attack']['pass'], tally['attack']['n'], tally['calibration']['pass'],
                       tally['calibration']['n'])
    return {**found, 'by_weakness': [[key, value['n'], value['pass']] for key, value in sorted(
        by_weakness.items(), key=lambda pair: _weakness_order(pair[0]))]}


def _weakness_order(key):
    return (1, 0) if key == 'none' else (0, int(key[1:]))


# ---- proportions -------------------------------------------------------------------------------------------------
def largest_remainder(total, weights):
    """``total`` items over keys in proportion to their weights (Hamilton's largest remainder method, in integers).
    ``weights``: ``[(key, weight), ...]`` with integer weights >= 0, at least one above 0 (when ``total`` > 0), in the
    order that breaks ties. Each key gets floor(total * weight / W); the rest go one each to the largest remainders,
    ties broken by the larger weight, then by the listed order. Returns ``[(key, count), ...]`` in the listed order."""
    rows = list(weights)
    require(type(total) is int and total >= 0, 'A count')
    require(all(type(w) is int and w >= 0 for _, w in rows) and len({k for k, _ in rows}) == len(rows),
            'Integer weights >= 0 of distinct keys')
    W = sum(w for _, w in rows)
    if total == 0:
        return [(key, 0) for key, _ in rows]
    require(W > 0, 'A proportion needs a weight above 0')
    base = [total * w // W for _, w in rows]
    remainders = [total * w % W for _, w in rows]
    left = total - sum(base)
    order = sorted(range(len(rows)), key=lambda j: (-remainders[j], -rows[j][1], j))
    for j in order[:left]:
        base[j] += 1
    return [(key, count) for (key, _), count in zip(rows, base)]


def ordered_proportion(total, weights):
    """``largest_remainder`` spread as one sequence of keys: every key repeated its count, keys interleaved in turn
    (round robin in the listed order), so a prefix of the sequence keeps the proportion as far as it can."""
    left = [[key, count] for key, count in largest_remainder(total, weights) if count]
    out = []
    while left:
        for row in left:
            out.append(row[0])
            row[1] -= 1
        left = [row for row in left if row[1]]
    return out


# ---- item records ------------------------------------------------------------------------------------------------
def item_sha256(bench, item):
    """The hash of everything a solver and the judge read of an item, in its benchmark form (``zebra_build.
    item_digest``'s idea): ZebraLogic: ``item_digest`` itself (id, size, question, columns, grid); SearchQA: the id, the
    whole public part (question and snippets: the solver's view) and the private ``answers`` (what the judge reads);
    every other bench (ALFWorld: the game file, its registered routing view and its hash; the private game metadata):
    the id, the whole public part and the whole private part. Bookkeeping fields (benchmark, family, part, position,
    room, task type, revisions) are not hashed: a solver and the judge never read them."""
    require(isinstance(item, dict) and isinstance(item.get('task_id'), str) and item['task_id']
            and isinstance(item.get('public'), dict) and isinstance(item.get('private'), dict),
            'An item in its benchmark form (task_id, public, private)')
    if bench == 'zebralogic':
        from ..bank.zebra_build import item_digest
        return item_digest(item)
    if bench == 'searchqa':
        require('answers' in item['private'], 'A SearchQA item carries its answers')
        return canonical_sha256({'task_id': item['task_id'], 'public': item['public'],
                                 'private': {'answers': item['private']['answers']}})
    require(bench in ORDER, 'A registered bench: ' + str(bench))
    return canonical_sha256({'task_id': item['task_id'], 'public': item['public'], 'private': item['private']})


def item_record(*, item, cls, weakness, side, family, source, certificate, item_sha256):
    """One item record ``{'item', 'class', 'weakness', 'side', 'family', 'source', 'certificate', 'item_sha256'}``,
    validated (``check_record``)."""
    return check_record({'item': item, 'class': cls, 'weakness': weakness, 'side': side, 'family': family,
                         'source': source, 'certificate': certificate, 'item_sha256': item_sha256})


def check_record(record):
    """An item record as this package writes it, or ValueError: exactly ``RECORD_KEYS``; a non-empty item id and
    family; a registered side and class (the shown side has attack and guard items only); ``weakness`` a canonical
    weakness id (w1, w2, ...) for an attack item made for a weakness, None otherwise; a made item has a certificate
    (a dict), a selected item none; the item hash is 64 hex digits."""
    require(isinstance(record, dict) and tuple(sorted(record)) == tuple(sorted(RECORD_KEYS)),
            'An item record has exactly the keys ' + ', '.join(RECORD_KEYS))
    require(isinstance(record['item'], str) and record['item'], 'An item record names its item')
    require(record['side'] in SIDES, 'A registered side: %r' % (record['side'],))
    require(record['class'] in (SHOWN_CLASSES if record['side'] == 'shown' else CLASSES),
            'A registered class of its side: %r' % (record['class'],))
    weakness = record['weakness']
    require(weakness is None or (record['class'] == 'attack' and isinstance(weakness, str)
                                 and WEAKNESS_ID.match(weakness) is not None),
            'A weakness id only on an attack item: %r' % (weakness,))
    require(isinstance(record['family'], str) and record['family'], 'An item record names its family')
    require(record['source'] in SOURCES, 'A registered source: %r' % (record['source'],))
    require(isinstance(record['certificate'], dict) if record['source'] == 'made' else record['certificate'] is None,
            'A made item has its certificate, a selected item none')
    require(isinstance(record['item_sha256'], str) and HEX64.match(record['item_sha256']) is not None,
            'An item hash of 64 hex digits')
    return record


# ---- the makers' entry point ---------------------------------------------------------------------------------------
class RoleUnavailable(RuntimeError):
    """A role call of a maker (the SearchQA selector) delivered no verdict of the model: an infrastructure failure
    (``writers.reply_failure`` 'infrastructure:...'). Nothing of that call was recorded as a result, so running the
    maker again sends it again; the chain applies its rule (one automatic retry, then a pause). ``purpose``, ``tag``
    and ``failure`` name the call."""

    def __init__(self, purpose, tag, failure):
        super().__init__('%s %s: %s' % (purpose, tag, failure))
        self.purpose, self.tag, self.failure = purpose, tag, failure


@dataclass
class MakeInput:
    """The one argument of ``MAKERS[bench].make`` (what P2b hands a maker).

    bench: the bench of the step. plan: ``plan.validate_plan``'s plan. counts: ``counts(bench, [kept ids])`` (or a
    reduced counts record for the replacement round: only the classes to make, others 0; ``check_counts``).
    pool: the bench's pinned practice pool in pool order (``Services.items[bench]``); pool_pin: its manifest pin
    ``{'path', 'sha256'}``. learn_ids / gate_ids: the run's learn and gate slices of the bench. outcomes: {learn id:
    [R outcomes of B: True / False / None]} (the step's ``diagnose`` unit). repeats: R. identity: {'version',
    'chain', 'step', 'round'} (round 1 for ``items``, 2 for ``items-2``; it enters every seed and draw tag).
    registry: ``store.RunRegistry`` of the items this chain made or selected before (any step, any round; the maker
    adds what it makes). store: ``store.ItemStore`` of the unit (every file the maker writes). role_call: ``tag ->
    call(system, user) -> receipt`` (the SearchQA selector only; one tag per batch). view_of: ``item -> routing
    view`` (``Services.view_fn``; default: the item's public part, ALFWorld's registered routing view).
    language: the ZebraLogic language record of this step when already learned (else learned into the store)."""
    bench: str
    plan: dict
    counts: dict
    pool: list
    pool_pin: dict
    learn_ids: list
    gate_ids: list
    outcomes: dict
    repeats: int
    identity: dict
    registry: object
    store: object
    role_call: object = None
    view_of: object = None
    language: object = None

    def check(self):
        require(isinstance(self.plan, dict) and isinstance(self.plan.get('weaknesses'), list),
                'A validated plan (validate_plan)')
        check_counts(self.counts)
        ids = [item['task_id'] for item in self.pool]
        require(len(set(ids)) == len(ids), 'A pool lists each item once')
        known = set(ids)
        require(set(self.learn_ids) <= known and set(self.gate_ids) <= known
                and not set(self.learn_ids) & set(self.gate_ids), 'Disjoint learn and gate slices of the pool')
        require(type(self.repeats) is int and self.repeats >= 1, 'R >= 1')
        require(set(self.outcomes) == set(self.learn_ids)
                and all(isinstance(v, (list, tuple)) and len(v) == self.repeats
                        and all(o is True or o is False or o is None for o in v) for v in self.outcomes.values()),
                'Outcomes of B: R values (True, False or None) for every learn item')
        identity = self.identity
        require(isinstance(identity, dict) and isinstance(identity.get('version'), str) and identity['version']
                and identity.get('chain') in ('G', 'D') and type(identity.get('step')) is int and identity['step'] >= 1
                and type(identity.get('round', 1)) is int and identity.get('round', 1) in (1, 2),
                'A step identity {version, chain, step, round}')
        return self


def identity_tag(identity):
    """The text of a step identity inside seeds and draw tags: '<version>:<chain>:s<step>:r<round>'."""
    return '%s:%s:s%d:r%d' % (identity['version'], identity['chain'], identity['step'], identity.get('round', 1))


def no_items(inp, reason):
    """The result of a maker that makes nothing (``maker_not_built``, ``no_quota``): recorded, never an error."""
    return {'bench': inp.bench if inp is not None else None, 'status': 'no_items', 'reason': reason, 'records': [],
            'slots': [], 'shortfalls': [], 'made_counts': {side: {name: 0 for name in CLASSES} for side in SIDES},
            'record': {'version': RECORD_VERSION}}


def made_counts(records):
    out = {side: {name: 0 for name in CLASSES} for side in SIDES}
    for record in records:
        out[record['side']][record['class']] += 1
    return out


EXPORTS = ('MAKERS',)


def __getattr__(name):
    """``MAKERS`` (bench -> maker) is built on first access: the makers import this module."""
    if name == 'MAKERS':
        from .registry import MAKERS
        return MAKERS
    raise AttributeError('module %r has no attribute %r' % (__name__, name))
