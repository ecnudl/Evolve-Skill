"""The selectors of the item stage (brief P2, section D, second paragraph): REAL practice items are picked for a step,
never made. A selected item keeps its real reference (its item is the pool item, unchanged).

Candidates are the practice-source items of the run that are in neither the learn nor the gate slice and were not
selected before in this chain (``RunRegistry``). Shown and judging sides never share an item or a family:

- SearchQA (``SearchQASelector``): a family is the item's ``family_id`` (the tree's exact-question family: the sha256
  of the normalised question; the item id when absent); a candidate whose family is the family of a learn or gate item,
  or of an item selected before, is no candidate (a near-duplicate question). The analyst's weakness and guard
  descriptions are matched to the candidates by ONE selector call per batch of BATCH candidates (role client,
  purpose ``item_selector``; the candidates' public text only, cut as a writer example's view; never a reference),
  the reply read by the tolerant reader with one format retry per batch: a reply is readable only as an object
  ``{"matches": {label: description id or null}}`` whose every value is null or one of the batch's description ids (a
  list, an object, a number or an unknown id makes it unreadable); an unreadable batch selects nothing and is
  recorded. A batch request whose verdict the call recorder already holds (a unit killed after the receipt was written
  and before the batch record) is answered from it, never sent again (``plan.send_or_replay``). Fixed code then
  takes, in the pool's order, the attack items of each weakness in turn (judging side, then shown side) and the guard
  items (judging, then shown); judging-side shortfalls of attack and guard items go
  to calibration and are recorded; shown-side shortfalls are recorded (the shown side has no calibration class).
  Calibration items, and the attack items when no weakness is kept, are a seeded draw (``coevo5.data.ranked``) from the
  candidates not chosen.
- ALFWorld (``ALFWorldSelector``): candidates are the practice-source games with a registered routing view; a game's
  task type and room come from its own game file (``supply.task_folder``, the tree's reading of
  ``.../<type>-<object>-<movable>-<receptacle>-<scene>/trial_*/game.tw-pddl``; an item's own ``task_type`` / ``room``
  fields must agree); the family of a game is its room (scene): shown and judging games never share a room. No model
  call. In a seeded order of the candidates: the attack games of each weakness in turn take games of the weakness's
  task types (its spec's ``task_types``; every type when it names none); guard games take, type by type in turn, the
  types every learn game of which B won in all R runs -- there is no fallback (the two-highest rule is ZebraLogic's):
  when no type qualifies, the judging-side guard count goes to calibration (recorded as ``guard_to_calibration``) and
  the shown-side guard count is a recorded shortfall (reason ``no_guard_type``); calibration games follow the gate
  slice's type proportions (``items.largest_remainder``), and so do the attack games when no weakness is kept. Other
  shortfalls are recorded, never filled with another class.

The selection of a unit is written once as ``selection.json`` (a resumed unit recomputes it from the stored batch
records and must find the same), then every item file and slot record (``store.ItemStore``).
"""
from __future__ import annotations

import json

from skillopt.coevo5.data import ranked
from skillopt.continual_eval.core import require
from skillopt.execskill import supply

from .. import SEED, writers
from ..bank.env import read_object
from . import (CLASSES, RECORD_VERSION, SIDES, RoleUnavailable, identity_tag, item_record, item_sha256,
               largest_remainder, made_counts, no_items, ordered_proportion)
from .plan import public_text_of, send_or_replay
from .store import slot_name

SELECTOR_PURPOSE = 'item_selector'   # the purpose under which P2b records a selector call (Services.role_call)
BATCH = 25
DRAW_TAG = 'typed-v3-items:%s:draw:%s'   # bench, identity tag: the seeded draw of calibration-like items
SELECTION = 'selection.json'
SELECTOR_SYSTEM = (
    'You sort practice questions for a study of a question-answering solver. You receive one JSON object:\n'
    '- descriptions: kinds of questions, each with an id (d1, d2, ...) and a description;\n'
    '- candidates: up to %d practice questions, each with a label (c01, c02, ...) and its public text (the question '
    'and the retrieved snippets the solver reads).\n'
    'For every candidate decide which ONE description it clearly matches, judged from its text alone; when none '
    'matches clearly, or several would match equally, give null. Do not answer the questions.\n\n'
    'Reply with exactly one JSON object and nothing else, naming every candidate label once:\n'
    '{"matches": {"c01": "d2", "c02": null, ...}}') % BATCH
SELECTOR_RETRY = ('\n\nFormat retry: the reply could not be read. Reply with exactly one JSON object {"matches": {...}} '
                  'that names every candidate label once with a description id or null, and nothing else.')
SEARCHQA_WHAT = ('Real practice questions (a question with retrieved snippets) are picked for each weakness and guard by '
                 'a reader who sees only a candidate question\'s text and your description, never an answer: '
                 'describe a weakness or a guard so that a matching question can be recognised from its text alone. '
                 'There are no spec fields.')
TYPES = ('pick_and_place_simple', 'look_at_obj_in_light', 'pick_clean_then_place_in_recep',
         'pick_heat_then_place_in_recep', 'pick_cool_then_place_in_recep', 'pick_two_obj_and_place')
TYPE_TEXT = {'pick_and_place_simple': 'find an object and put it in or on a receptacle',
             'look_at_obj_in_light': 'find an object and examine it under a lamp',
             'pick_clean_then_place_in_recep': 'clean an object (at a sink) and put it somewhere',
             'pick_heat_then_place_in_recep': 'heat an object (microwave) and put it somewhere',
             'pick_cool_then_place_in_recep': 'cool an object (fridge) and put it somewhere',
             'pick_two_obj_and_place': 'find two objects of a kind and put both in or on a receptacle'}
ALFWORLD_WHAT = ('Real practice games of a household agent are picked by their task type (one of six, read from the '
                 'game itself): ask for the task types whose games show a weakness.')
ROOM_FAMILY = 'alfworld-room:'
JUDGING_FIRST = ('judging', 'shown')   # the order in which the sides are filled and listed


# ---- shared ----------------------------------------------------------------------------------------------------------
def _order_key(row):
    side, cls, weakness = row[0], row[1], row[2]
    return (JUDGING_FIRST.index(side), CLASSES.index(cls), (1, 0) if weakness is None else (0, int(weakness[1:])))


def write_picks(inp, bench, picks):
    """Write the picked items of a selector: ``picks`` ``[(side, cls, weakness, item, detail)]`` in pick order. The
    listing order is judging before shown, attack / guard / calibration, weakness w1, w2, ... (None last), then pick
    order; a slot's number counts within its side, class and weakness. Each item file is the pool item unchanged, then
    its slot record (``source`` 'selected', no certificate). Returns (records, rows) in listing order."""
    ordered = sorted(enumerate(picks), key=lambda pair: (_order_key(pair[1]), pair[0]))
    numbers, records, rows = {}, [], []
    for _, (side, cls, weakness, item, detail) in ordered:
        key = (side, cls, weakness)
        numbers[key] = numbers.get(key, 0) + 1
        name = slot_name(side, cls, weakness, numbers[key])
        record = item_record(item=item['task_id'], cls=cls, weakness=weakness, side=side, family=detail['family'],
                             source='selected', certificate=None, item_sha256=item_sha256(bench, item))
        stored = inp.store.slot(name)
        if stored is None:
            inp.store.write_item(name, item)
            stored = inp.store.write_slot(name, record=record, shortfall=None, attempts=[], detail=dict(detail))
        require(stored['record'] == record and stored['detail'] == detail, 'The slot %s holds another pick' % name)
        require(item_sha256(bench, inp.store.item(name)) == record['item_sha256'],
                'The item of slot %s is not the one its record names' % name)
        inp.registry.add(record)
        records.append(record)
        rows.append({'slot': name, 'side': side, 'class': cls, 'weakness': weakness, 'item': item['task_id'],
                     'shortfall': None, **{k: v for k, v in detail.items() if k != 'family'}})
    return records, rows


def _selection(inp, value):
    stored = inp.store.once((SELECTION,), lambda: value)
    require(stored == json.loads(json.dumps(value)), 'The stored selection of this unit is of other inputs')
    return stored


def _counts_empty(counts):
    return not any(counts[side][name] for side in SIDES for name in counts[side])


class _Picker:
    """The bookkeeping of one selection: items taken once, a family on one side only (also across earlier units:
    ``registry``), picks in order."""

    def __init__(self, registry, family_of):
        self.family_of, self.taken, self.picks, self.side_of = family_of, set(), [], {}
        for family, sides in registry.families.items():
            self.side_of[family] = next(iter(sides)) if len(sides) == 1 else None   # None: blocked on both sides

    def eligible(self, item, side):
        family = self.family_of(item)
        return item['task_id'] not in self.taken and self.side_of.get(family, side) == side

    def take(self, item, side, cls, weakness, detail):
        self.taken.add(item['task_id'])
        self.side_of[self.family_of(item)] = side
        self.picks.append((side, cls, weakness, item, {'family': self.family_of(item), **detail}))

    def first(self, items, side, test=lambda item: True):
        return next((item for item in items if test(item) and self.eligible(item, side)), None)


# ---- SearchQA ------------------------------------------------------------------------------------------------------
def searchqa_family(item):
    found = item.get('family_id')
    return found if isinstance(found, str) and found else item['task_id']


def read_matches(reply, ids):
    """The ``matches`` object of a selector reply (tolerant reading) when it is readable, else None: a JSON object
    whose ``matches`` is an object and whose every value is null or a string naming one of the batch's description ids
    ``ids`` (a list, an object, a number or an unknown id makes the whole reply unreadable). Its keys are not checked
    here: a key that is no candidate label of the batch is named in the batch record and selects nothing."""
    found = read_object(reply) if isinstance(reply, str) else None
    if not isinstance(found, dict) or not isinstance(found.get('matches'), dict):
        return None
    matches = found['matches']
    if not all(value is None or (isinstance(value, str) and value in ids) for value in matches.values()):
        return None
    return matches


class SearchQASelector:
    """``MAKERS['searchqa']``: real practice questions matched to the plan by a selector call per batch."""

    bench = 'searchqa'
    built = True

    def capability_sheet(self, *, pool=None, learn_ids=None, gate_ids=None):
        return {'maker': 'searchqa-selector', 'what': SEARCHQA_WHAT, 'fields': {}}

    def public_kind(self, item):
        return {}

    def candidates(self, inp):
        """(candidates in pool order, excluded counts): neither learn nor gate items nor of their families, never
        selected before in this chain, nor of a family selected before."""
        by_id = {item['task_id']: item for item in inp.pool}
        used = set(inp.learn_ids) | set(inp.gate_ids)
        families = {searchqa_family(by_id[i]) for i in used}
        excluded = {'learn_or_gate': 0, 'family_of_learn_or_gate': 0, 'selected_before': 0,
                    'family_selected_before': 0}
        out = []
        for item in inp.pool:
            family = searchqa_family(item)
            reason = ('learn_or_gate' if item['task_id'] in used else 'family_of_learn_or_gate' if family in families
                      else 'selected_before' if item['task_id'] in inp.registry.ids
                      else 'family_selected_before' if inp.registry.family_sides(family) else None)
            if reason is None:
                out.append(item)
            else:
                excluded[reason] += 1
        return out, excluded

    def request_text(self, inp, descriptions, chunk):
        """(user text, {label: item id}) of one batch: the descriptions with opaque ids d1, d2, ... and the candidates
        with labels c01, c02, ... and their public text only."""
        labels = {'c%02d' % (j + 1): item['task_id'] for j, item in enumerate(chunk)}
        user = {'descriptions': [{'id': 'd%d' % (n + 1), 'description': text} for n, (_, text) in enumerate(descriptions)],
                'candidates': [{'label': label, 'text': public_text_of('searchqa', item, inp.view_of)}
                               for label, item in zip(labels, chunk)]}
        return json.dumps(user, ensure_ascii=False, sort_keys=True), labels

    def ask(self, inp, number, user, labels, ids):
        """One batch: the selector call and one format retry when its reply is unreadable (``read_matches``); an
        infrastructure failure raises ``RoleUnavailable`` (nothing is stored, so the batch is sent again). Each attempt
        is first looked up in the recorder's sends (``plan.send_or_replay``): a request answered before the process
        was killed is not sent again. The batch record: the labels, the description ids, both replies, the matches by
        item id (None: no match) and the keys of the reply that are no candidate label."""
        tag = 'selector-%02d' % number
        require(inp.role_call is not None, 'The SearchQA selector needs the role call of its unit')
        call, attempts, found = inp.role_call(tag), [], None
        for attempt in (1, 2):
            text = user if attempt == 1 else user + SELECTOR_RETRY
            receipt = send_or_replay(call, SELECTOR_SYSTEM, text)
            reply, failure = writers.reply_of(receipt), writers.reply_failure(receipt)
            found = read_matches(reply, ids)
            attempts.append({'request_sha256': writers.request_sha256(SELECTOR_SYSTEM, text), 'reply': reply,
                             'failure': failure, 'readable': found is not None})
            if found is not None:
                break
            if str(failure or '').startswith('infrastructure:'):
                raise RoleUnavailable(SELECTOR_PURPOSE, tag, failure)
        matches, unknown_labels = {item_id: None for item_id in labels.values()}, []
        for label in sorted(found or {}, key=str):
            value = found[label]          # None or one of ``ids`` (read_matches)
            if label not in labels:
                unknown_labels.append(str(label)[:16])
            elif value is not None:
                matches[labels[label]] = ids[value]
        return {'version': RECORD_VERSION, 'batch': number, 'request_sha256': attempts[0]['request_sha256'],
                'labels': labels, 'descriptions': ids, 'readable': found is not None, 'matches': matches,
                'unknown_labels': unknown_labels, 'attempts': attempts}

    def classify(self, inp, candidates, descriptions):
        """({item id: plan id or None}, batch summaries): every batch of BATCH candidates in pool order, each through
        its write-once record ``selector/batch-<nn>.json`` (a stored batch is used only for the same request)."""
        ids = {'d%d' % (n + 1): plan_id for n, (plan_id, _) in enumerate(descriptions)}
        matches, batches = {}, []
        for number, start in enumerate(range(0, len(candidates), BATCH), 1):
            user, labels = self.request_text(inp, descriptions, candidates[start:start + BATCH])
            record = inp.store.once(('selector', 'batch-%02d.json' % number),
                                    lambda: self.ask(inp, number, user, labels, ids))
            require(record['request_sha256'] == writers.request_sha256(SELECTOR_SYSTEM, user)
                    and record['labels'] == labels, 'The stored selector batch %d is of another request' % number)
            matches.update(record['matches'])
            batches.append({'batch': number, 'candidates': len(labels), 'readable': record['readable'],
                            'matched': sum(value is not None for value in record['matches'].values()),
                            'calls': len(record['attempts'])})
        return matches, batches

    def make(self, inp):
        inp.check()
        require(inp.bench == self.bench, 'The SearchQA selector picks SearchQA items')
        if _counts_empty(inp.counts):
            return no_items(inp, 'no_quota')
        candidates, excluded = self.candidates(inp)
        counts, split = inp.counts, inp.counts['attack_split']
        weaknesses = {w['id']: w for w in inp.plan['weaknesses']}
        attack_ids = [w for w, _ in split['judging'] or split['shown']]
        require(all(w in weaknesses for w in attack_ids), 'The attack split names kept weaknesses of the plan')
        guard_ids = [g['id'] for g in inp.plan['guards']] if counts['judging']['guard'] or counts['shown']['guard'] else []
        descriptions = ([(w, weaknesses[w]['description']) for w in attack_ids]
                        + [(g['id'], g['description']) for g in inp.plan['guards'] if g['id'] in guard_ids])
        matches, batches = self.classify(inp, candidates, descriptions) if descriptions else ({}, [])
        picker, shortfalls = _Picker(inp.registry, searchqa_family), []
        for side in JUDGING_FIRST:    # judging, then shown
            lists = {w: [item for item in candidates if matches.get(item['task_id']) == w] for w, _ in split[side]}
            need = {w: n for w, n in split[side]}
            progress = True
            while progress:         # weaknesses in turn, one item each, in the pool's order
                progress = False
                for w, _ in split[side]:
                    found = picker.first(lists[w], side) if need[w] else None
                    if found is not None:
                        picker.take(found, side, 'attack', w, {'how': 'matched'})
                        need[w] -= 1
                        progress = True
            shortfalls += [{'side': side, 'class': 'attack', 'weakness': w, 'missing': n} for w, n in need.items() if n]
        guards = [item for item in candidates if matches.get(item['task_id']) in guard_ids]
        for side in JUDGING_FIRST:
            got = 0
            while got < counts[side]['guard']:
                found = picker.first(guards, side)
                if found is None:
                    break
                picker.take(found, side, 'guard', None, {'how': 'matched'})
                got += 1
            if got < counts[side]['guard']:
                shortfalls.append({'side': side, 'class': 'guard', 'weakness': None,
                                   'missing': counts[side]['guard'] - got})
        drawn = ranked(candidates, SEED, DRAW_TAG % (self.bench, identity_tag(inp.identity)))

        def draw(side, cls, n):
            got = 0
            while got < n:
                found = picker.first(drawn, side)
                if found is None:
                    break
                picker.take(found, side, cls, None, {'how': 'drawn'})
                got += 1
            return got
        for side in JUDGING_FIRST:
            if not split[side] and counts[side]['attack']:
                got = draw(side, 'attack', counts[side]['attack'])
                if got < counts[side]['attack']:
                    shortfalls.append({'side': side, 'class': 'attack', 'weakness': None,
                                       'missing': counts[side]['attack'] - got})
        for row in shortfalls:
            row['filled_by'] = 'calibration' if row['side'] == 'judging' else None
        want = counts['judging']['calibration'] + sum(row['missing'] for row in shortfalls if row['side'] == 'judging')
        got = draw('judging', 'calibration', want)
        if got < want:
            shortfalls.append({'side': 'judging', 'class': 'calibration', 'weakness': None, 'missing': want - got,
                               'filled_by': None})
        selection = {'version': RECORD_VERSION, 'bench': self.bench, 'identity': dict(inp.identity),
                     'candidates': len(candidates), 'excluded': excluded, 'batches': batches,
                     'descriptions': [plan_id for plan_id, _ in descriptions],
                     'picks': [[side, cls, weakness, item['task_id'], detail['how']]
                               for side, cls, weakness, item, detail in picker.picks],
                     'calibration_wanted': want, 'shortfalls': shortfalls}
        _selection(inp, selection)
        records, rows = write_picks(inp, self.bench, picker.picks)
        return {'bench': self.bench, 'status': 'made', 'reason': None, 'records': records, 'slots': rows,
                'shortfalls': shortfalls, 'made_counts': made_counts(records), 'record': selection}


# ---- ALFWorld ------------------------------------------------------------------------------------------------------
def game_type(item):
    """(task type, room) of an ALFWorld game from its own game file (``supply.task_folder``); an item's own
    ``task_type`` and ``room`` fields, when present, must agree. ValueError for a game of another layout or type."""
    room, kind = supply.task_folder(item['public']['game_file'])
    require(item.get('task_type', kind) == kind and str(item.get('room', room)) == room,
            'The game file and the item disagree on the task type or room: ' + item['task_id'])
    require(kind in TYPES, 'One of the six ALFWorld task types: ' + kind)
    return kind, room


def _type_or_none(item):
    try:
        return game_type(item)
    except (ValueError, KeyError, TypeError):
        return None


def type_guards(learn_items, outcomes, repeats):
    """(types, rule): the task types every learn game of which B won in all R runs, in ``TYPES`` order ('all_right'),
    or no type at all ('none_all_right'): ALFWorld has no fallback (the two-highest rule is ZebraLogic's). Games whose
    type cannot be read are left out."""
    tally = {}
    for item in learn_items:
        found = _type_or_none(item)
        if found is None:
            continue
        row = tally.setdefault(found[0], [0, 0])
        row[0] += 1
        row[1] += sum(outcome is True for outcome in outcomes[item['task_id']])
    require(tally, 'Learn games of a readable task type')
    right = [kind for kind in TYPES if kind in tally and tally[kind][1] == tally[kind][0] * repeats]
    return (right, 'all_right') if right else ([], 'none_all_right')


class ALFWorldSelector:
    """``MAKERS['alfworld']``: real practice games picked by task type, no model call."""

    bench = 'alfworld'
    built = True

    def capability_sheet(self, *, pool=None, learn_ids=None, gate_ids=None):
        return {'maker': 'alfworld-selector', 'what': ALFWORLD_WHAT, 'fields': {
            'task_types': {'kind': 'subset', 'values': list(TYPES), 'types': dict(TYPE_TEXT),
                           'meaning': 'the task types of the games that show this weakness; leave out for every type'}}}

    def public_kind(self, item):
        found = _type_or_none(item)
        return {} if found is None else {'task_type': found[0]}

    @staticmethod
    def family_of(item):
        return ROOM_FAMILY + game_type(item)[1]

    def candidates(self, inp):
        """(candidates in pool order, excluded counts): games with a registered routing view and a readable task
        type, neither learn nor gate games, never selected before in this chain."""
        used = set(inp.learn_ids) | set(inp.gate_ids)
        excluded = {'learn_or_gate': 0, 'no_routing_view': 0, 'no_task_type': 0, 'selected_before': 0}
        out = []
        for item in inp.pool:
            public = item.get('public') or {}
            reason = ('learn_or_gate' if item['task_id'] in used
                      else 'no_routing_view' if not (isinstance(public.get('routing_view'), dict)
                                                     and isinstance(public.get('routing_view_sha256'), str))
                      else 'no_task_type' if _type_or_none(item) is None
                      else 'selected_before' if item['task_id'] in inp.registry.ids else None)
            if reason is None:
                out.append(item)
            else:
                excluded[reason] += 1
        return out, excluded

    def make(self, inp):
        inp.check()
        require(inp.bench == self.bench, 'The ALFWorld selector picks ALFWorld games')
        if _counts_empty(inp.counts):
            return no_items(inp, 'no_quota')
        by_id = {item['task_id']: item for item in inp.pool}
        candidates, excluded = self.candidates(inp)
        counts, split = inp.counts, inp.counts['attack_split']
        weaknesses = {w['id']: w for w in inp.plan['weaknesses']}
        require(all(w in weaknesses for side in SIDES for w, _ in split[side]),
                'The attack split names kept weaknesses of the plan')
        guard, rule = type_guards([by_id[i] for i in inp.learn_ids], inp.outcomes, inp.repeats)
        gate_types = [_type_or_none(by_id[i]) for i in inp.gate_ids]
        gate = [(kind, sum(1 for found in gate_types if found is not None and found[0] == kind)) for kind in TYPES]
        ordered = ranked(candidates, SEED, DRAW_TAG % (self.bench, identity_tag(inp.identity)))
        picker, shortfalls = _Picker(inp.registry, self.family_of), []

        def of_types(types):
            return lambda item: game_type(item)[0] in types

        for side in JUDGING_FIRST:
            if split[side]:
                need = {w: n for w, n in split[side]}
                progress = True
                while progress:     # weaknesses in turn, one game each
                    progress = False
                    for w, _ in split[side]:
                        types = weaknesses[w]['spec'].get('task_types') or list(TYPES)
                        found = picker.first(ordered, side, of_types(types)) if need[w] else None
                        if found is not None:
                            picker.take(found, side, 'attack', w, {'task_type': game_type(found)[0]})
                            need[w] -= 1
                            progress = True
                shortfalls += [{'side': side, 'class': 'attack', 'weakness': w, 'missing': n}
                               for w, n in need.items() if n]
            else:
                shortfalls += self._by_types(picker, ordered, side, 'attack',
                                             ordered_proportion(counts[side]['attack'], gate))
        # no guard type: the judging guard count is drawn as calibration (with it, by the gate's type proportions),
        # the shown guard count is a shortfall (the shown side has no calibration)
        guard_to_calibration = 0 if guard else counts['judging']['guard']
        for side in JUDGING_FIRST:
            if guard:
                sequence = [guard[j % len(guard)] for j in range(counts[side]['guard'])]
                shortfalls += self._by_types(picker, ordered, side, 'guard', sequence)
            elif side == 'shown' and counts[side]['guard']:
                shortfalls.append({'side': side, 'class': 'guard', 'weakness': None, 'task_type': None,
                                   'missing': counts[side]['guard'], 'reason': 'no_guard_type'})
        shortfalls += self._by_types(picker, ordered, 'judging', 'calibration',
                                     ordered_proportion(counts['judging']['calibration'] + guard_to_calibration, gate))
        selection = {'version': RECORD_VERSION, 'bench': self.bench, 'identity': dict(inp.identity),
                     'candidates': len(candidates), 'excluded': excluded,
                     'guard_types': {'types': guard, 'rule': rule}, 'guard_to_calibration': guard_to_calibration,
                     'gate_types': [[k, n] for k, n in gate],
                     'picks': [[side, cls, weakness, item['task_id'], detail['task_type'], detail['family']]
                               for side, cls, weakness, item, detail in picker.picks],
                     'shortfalls': shortfalls}
        _selection(inp, selection)
        records, rows = write_picks(inp, self.bench, picker.picks)
        return {'bench': self.bench, 'status': 'made', 'reason': None, 'records': records, 'slots': rows,
                'shortfalls': shortfalls, 'made_counts': made_counts(records), 'record': selection}

    @staticmethod
    def _by_types(picker, ordered, side, cls, sequence):
        """One game per entry of ``sequence`` (task types, in turn), each the first eligible game of its type in the
        seeded order; the shortfalls per type (recorded, not filled)."""
        missing = {}
        for kind in sequence:
            found = picker.first(ordered, side, lambda item, kind=kind: game_type(item)[0] == kind)
            if found is None:
                missing[kind] = missing.get(kind, 0) + 1
            else:
                picker.take(found, side, cls, None, {'task_type': kind})
        return [{'side': side, 'class': cls, 'weakness': None, 'task_type': kind, 'missing': n}
                for kind, n in missing.items()]
