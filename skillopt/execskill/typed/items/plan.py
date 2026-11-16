"""The analyst of the item stage (CHAIN-DECISIONS T4) and the experience log (brief P2, section C).

- ``learn_rows`` / ``outcomes_of``: what the analyst may see of the learn slice -- per learn item its public text
  (``tasktypes.public_text`` of its routing view, cut as the writers cut an example's view: ``writers.VIEW_CHARS``),
  its R outcomes under B and ONE wrong reply excerpt (cut as the writers cut a reply: ``writers.REPLY_HEAD`` +
  ``writers.REPLY_TAIL``); never a reference answer, never a gate item, no text of an item the provider's content
  filter refused (B7b: its id and outcomes only);
- ``analyst_payload``: the user payload (bench, task card, learn items, experience log, capability sheet; the
  revision block of ``items-plan-2``), fitted to ``profiles.ROLE_INPUT_BYTES`` by a fixed rule;
- ``request_plan``: ONE role call through the ``call(system, user) -> receipt`` P2b hands in (a ``units.CallRecorder``
  over the chain's role client, purpose ``item_analyst``: it charges the ledger and records the send, exactly as a
  writer's call), the reply read by the tolerant reader (``bank.env.read_object``), ONE format retry when unreadable;
  a request whose verdict the recorder already holds is answered from it, never sent again (``send_or_replay``);
- ``validate_plan``: the plan of T4 by fixed code (evidence rule, spec fields of the capability sheet, unique ids);
- ``experience_log`` / ``candidates_of_decisions``: the earlier steps of THIS chain, counts and short descriptions.

No model client is created here; nothing is written. Every count is an integer.
"""
from __future__ import annotations

import json
import math
import re
from fractions import Fraction

from skillopt.continual_eval.core import require
from skillopt.execskill import profiles, v225_writer

from .. import ORDER, tasktypes, units, writers
from ..bank.env import _terminal_receipt, read_object
from . import (EVIDENCE_MIN_FAILED_RUNS, EVIDENCE_MIN_ITEMS, MIN_KEPT_WEAKNESSES, RECORD_VERSION, WEAKNESS_ID)

ANALYST_PURPOSE = 'item_analyst'      # the purpose under which P2b records the call (Services.role_call)
ID_CHARS, DESCRIPTION_CHARS, SIGNATURE_CHARS, NOTE_CHARS = 64, 500, 300, 1000
INPUT_BYTES = profiles.ROLE_INPUT_BYTES   # the role request bound the engineer's payload is fitted to (220,000 bytes)
FIELD_KINDS = ('subset', 'factors', 'choice')

ANALYST_SYSTEM = (
    'You plan practice items for a solver that is being taught one kind of task. A teacher writes instructions for '
    'the solver from what it gets right and wrong; your plan decides which NEW practice items are made or picked for '
    'this round of that teaching: items that help the solver improve on this kind of task, and items that would show '
    'a regression.\n\n'
    'You receive one JSON object:\n'
    '- bench and task_card: the kind of task, described as the teacher reads it (format_block, when present: the '
    'answer format the solver must follow);\n'
    '- learn_items: every practice item the solver was given for learning, each with its id, its public text (what '
    'the solver reads; long texts are cut), outcomes (one entry per independent attempt of the solver: true = right, '
    'false = wrong, null = no usable reply, which counts as wrong) and, for an item it got wrong, wrong_reply (an '
    'excerpt of one wrong reply); some items also name their size or task type;\n'
    '- experience: what the earlier steps of this teaching tried on other kinds of tasks and whether it was kept '
    '(counts and short descriptions only);\n'
    '- capability_sheet: what the item maker for this kind of task can be asked for: its fields and the values each '
    'field allows.\n\n'
    'Three classes of items are made from your plan:\n'
    '- attack items: items of a kind the solver often gets wrong (a weakness). They show whether a new instruction '
    'fixes that weakness, so they must be of that kind;\n'
    '- guard items: items of a kind the solver reliably gets right. They show whether a new instruction breaks what '
    'already works (a regression);\n'
    '- calibration items: ordinary items drawn like the usual practice items, with no targeting. You do not plan '
    'them.\n\n'
    'Rules:\n'
    '1. Name a weakness only from evidence: its evidence lists ids of learn_items that show it. A weakness is kept '
    'only if at least %d of its evidence items are learn_items the solver got wrong in at least %d of its attempts; '
    'any other weakness is discarded. Never invent a weakness: an empty list is a valid plan.\n'
    '2. Describe a weakness by what its items have in common in the TASK (what is asked, how the material is laid '
    'out, what has to be done), so that other items of the same kind can be recognised or made without knowing '
    'their answers. signature says how a wrong reply of this kind looks.\n'
    '3. A guard describes a kind of item the solver got right in every attempt.\n'
    '4. spec asks the item maker for the items of a weakness or a guard: use only the fields of '
    'capability_sheet.fields, with the values each field allows; leave a field out to take its default. Any other '
    'field or value is discarded. When the sheet has no fields, give an empty spec.\n'
    '5. When the request is "revise", revision holds your first plan and, per weakness, how many of its attack '
    'items the solver got right, beside the calibration items: the attack items were not clearly harder than the '
    'calibration items. Write a new plan whose weaknesses are kinds the solver really gets wrong (keep, change or '
    'drop the first plan\'s weaknesses).\n\n'
    'Reply with exactly one JSON object and nothing else:\n'
    '{"weaknesses": [{"id": "a short name", "description": "...", "evidence": ["learn item id", ...], '
    '"signature": "...", "spec": {...}}], "guards": [{"description": "...", "spec": {...}}], "note": "..."}'
) % (EVIDENCE_MIN_ITEMS, EVIDENCE_MIN_FAILED_RUNS)
ANALYST_RETRY = ('\n\nFormat retry: the reply could not be read. Reply with exactly one JSON object with the keys '
                 '"weaknesses" (a list), "guards" (a list) and "note" (a string), as the system message shows, and '
                 'nothing else: no Markdown, no text before or after it.')
REVISION_MEANING = ('Your first plan and the check of its attack items: the solver ran once on the attack items made '
                    'for each weakness and on the calibration items; by_weakness lists [weakness id, items, right]. '
                    'The plan holds only when the attack items are at least %d points harder than the calibration '
                    'items.')


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _bytes(value):
    return len(_json(value).encode('utf-8'))


# ---- what the analyst sees of the learn slice ------------------------------------------------------------------------
def default_view(bench, item):
    """The routing view of a practice item when the caller has none: ALFWorld's registered routing view, else the
    public part (P2b passes ``Services.view_fn`` through ``view_of``)."""
    public = item['public']
    return public['routing_view'] if bench == 'alfworld' else public


def public_text_of(bench, item, view_of=None):
    """``tasktypes.public_text`` of the item's routing view, cut to ``writers.VIEW_CHARS`` as a writer example's view."""
    view = view_of(item) if view_of is not None else default_view(bench, item)
    return v225_writer.truncate(tasktypes.public_text(view), writers.VIEW_CHARS)


def _excerpt(reply):
    return v225_writer.truncate(reply, writers.REPLY_HEAD + writers.REPLY_TAIL, head=writers.REPLY_HEAD,
                                tail=writers.REPLY_TAIL)


def outcomes_of(runs, repeats):
    """{learn id: [R outcomes]} of ``runs`` ({learn id: [R cells of B, run 1 first]}); a cell's ``correct`` is True,
    False or None (a missing or unknown outcome)."""
    out = {}
    for item_id, cells in runs.items():
        require(isinstance(cells, (list, tuple)) and len(cells) == repeats, 'R cells of B per learn item: ' + item_id)
        found = [cell.get('correct') if isinstance(cell, dict) else None for cell in cells]
        require(all(value is True or value is False or value is None for value in found),
                'An outcome is True, False or None')
        out[item_id] = found
    return out


def learn_rows(bench, items, runs, repeats, *, view_of=None, kind_of=None):
    """One row per learn item (``items``: the learn slice in its order): ``{'id', 'public_text', 'outcomes', and
    'wrong_reply' when one of its runs was wrong, plus kind_of(item) (e.g. its size or task type)}``. ``runs``: {id:
    [R cells of B]} from the ``diagnose`` unit; the wrong reply is the reply (``writers._reply``: the cell's reply, else
    its last solver response) of the first run whose outcome is not True and whose reply is not empty. The item's
    references are never read. typed-v3 B7b: an item the provider's content filter refused in one of these runs
    (``units.cell_refused``) keeps its id, outcomes and kind but shows no text -- ``public_text`` None and no
    ``wrong_reply`` -- since an analyst request carrying it may be refused itself; decided from the runs alone, so a
    first pass and a resumed one build the same rows."""
    outcomes = outcomes_of(runs, repeats)
    require(set(runs) == {item['task_id'] for item in items} and len(items) == len(runs),
            'Runs of B for exactly the learn items')
    rows = []
    for item in items:
        refused = any(units.cell_refused(cell) for cell in runs[item['task_id']])
        row = {'id': item['task_id'], 'public_text': None if refused else public_text_of(bench, item, view_of),
               'outcomes': outcomes[item['task_id']]}
        for cell, outcome in ([] if refused else zip(runs[item['task_id']], outcomes[item['task_id']])):
            reply = writers._reply(cell) if isinstance(cell, dict) else ''
            if outcome is not True and isinstance(reply, str) and reply.strip():
                row['wrong_reply'] = _excerpt(reply)
                break
        if kind_of is not None:
            extra = kind_of(item) or {}
            require(not set(extra) & set(row), 'A kind field never replaces a row field')
            row.update(extra)
        rows.append(row)
    return rows


def _fit(payload):
    """Fit the user payload to ``INPUT_BYTES`` (it rarely binds): from the LAST learn item backwards, first the public
    texts of items right in every run, then the wrong replies, then the other public texts are replaced by null /
    dropped, one at a time, until it fits. Returns the counts of what was dropped."""
    dropped = {'stable_texts': 0, 'replies': 0, 'texts': 0}
    rows = payload['learn_items']

    def last(test):
        return next((row for row in reversed(rows) if test(row)), None)
    while _bytes(payload) > INPUT_BYTES:
        row = last(lambda r: r['public_text'] is not None and all(o is True for o in r['outcomes']))
        if row is not None:
            row['public_text'] = None
            dropped['stable_texts'] += 1
            continue
        row = last(lambda r: 'wrong_reply' in r)
        if row is not None:
            del row['wrong_reply']
            dropped['replies'] += 1
            continue
        row = last(lambda r: r['public_text'] is not None)
        require(row is not None, 'The analyst payload fits its input bound')
        row['public_text'] = None
        dropped['texts'] += 1
    return dropped


def analyst_payload(*, bench, task_card, learn, repeats, experience, capability_sheet, format_block=None,
                    revision=None):
    """The analyst's user payload and what fitting dropped: ``(payload, dropped)``. ``learn``: ``learn_rows``;
    ``experience``: ``experience_log``; ``capability_sheet``: the maker's sheet (``check_sheet``); ``revision``:
    ``revision_block`` for ``items-plan-2``, else None. Nothing here reads an item: the rows are what is shown."""
    require(bench in ORDER and isinstance(task_card, str) and task_card, 'A bench and its task card')
    require(type(repeats) is int and repeats >= 1, 'R >= 1')
    rows = []
    for row in learn:
        require(isinstance(row, dict) and isinstance(row.get('id'), str) and isinstance(row.get('outcomes'), list)
                and len(row['outcomes']) == repeats, 'A learn row with R outcomes')
        require(not {'reference', 'answer', 'answers', 'private'} & set(row), 'A learn row never carries a reference')
        rows.append(dict(row))
    require(len({row['id'] for row in rows}) == len(rows), 'Each learn item once')
    payload = {'request': 'plan' if revision is None else 'revise', 'bench': bench, 'task_card': task_card,
               'repeats': repeats, 'learn_items': rows, 'experience': list(experience),
               'capability_sheet': check_sheet(capability_sheet)}
    if format_block:
        payload['format_block'] = format_block
    if revision is not None:
        payload['revision'] = revision
    return payload, _fit(payload)


def revision_block(plan, check):
    """The ``revision`` block of ``items-plan-2``: the first plan (weaknesses with their evidence ids, which are learn
    items, guards, note) and the check's counts (``items.check_items``: per class and per weakness, never an item)."""
    by_weakness = [[w, n, passed] for w, n, passed in check['by_weakness']]
    require(all(type(n) is int and type(passed) is int for _, n, passed in by_weakness), 'Counts only')
    return {'meaning': REVISION_MEANING % check['margin_points'],
            'first_plan': {'weaknesses': [{key: w[key] for key in ('id', 'description', 'evidence', 'signature', 'spec')}
                                          for w in plan['weaknesses']],
                           'guards': [{key: g[key] for key in ('id', 'description', 'spec')} for g in plan['guards']],
                           'note': plan.get('note', '')},
            'check': {'attack': {'n': check['attack']['n'], 'right': check['attack']['pass']},
                      'calibration': {'n': check['calibration']['n'], 'right': check['calibration']['pass']},
                      'by_weakness': by_weakness, 'margin_points': check['margin_points']}}


# ---- the call ------------------------------------------------------------------------------------------------------
def recorded_receipt(call, system, user):
    """The receipt ``call`` already holds for exactly this request when it is a verdict of the model (delivered, or a
    model-side noncompletion: ``bank.env._terminal_receipt``, the first such send of the request), else None.

    WHY: the chain's role call is a ``units.CallRecorder`` that writes every send and its receipt to the unit's calls
    file BEFORE the caller writes its own record, and a resumed unit refills a new recorder's ``sends`` from that file
    (``chain._keep_earlier_sends``). A process killed between the two writes would otherwise send the request again:
    the ledger would pay twice and a new reply could change the plan or the selection. An infrastructure failure is no
    verdict and is sent again. A call without recorded sends (a plain function) holds none."""
    sends = getattr(call, 'sends', None)
    if not isinstance(sends, list):
        return None
    return _terminal_receipt(sends, units.sha256_text(system + '\x00' + user))


def send_or_replay(call, system, user):
    """The receipt of one role request: the recorded verdict of exactly this request (``recorded_receipt``), else a new
    send through ``call``. A replayed receipt is neither charged nor recorded again (the recorder did both when it was
    sent), and the caller's record is the same as after an uninterrupted run."""
    found = recorded_receipt(call, system, user)
    return found if found is not None else call(system, user)


def plan_object(reply):
    """The plan object of a reply (tolerant reading): a JSON object whose ``weaknesses`` is a list and whose
    ``guards``, when present, is a list; None otherwise."""
    found = read_object(reply) if isinstance(reply, str) else None
    if not isinstance(found, dict) or not isinstance(found.get('weaknesses'), list):
        return None
    if found.get('guards') is not None and not isinstance(found['guards'], list):
        return None
    return found


def request_plan(call, payload):
    """ONE analyst request, and ONE format retry when its reply is unreadable (no reply, or no plan object).

    ``call``: ``call(system, user) -> receipt`` (P2b: ``Services.role_call(ANALYST_PURPOSE, unit, 'analyst',
    WRITER_TOKENS)``, which charges the ledger before the send and records it, as for every writer call; a
    ``units.Stop`` at the token cap propagates). Returns ``{'status': 'ok' | 'unreadable' | 'infrastructure', 'raw':
    the plan object or None, 'request_sha256': the request whose reply was read (else the last one), 'attempts':
    [{'request_sha256', 'reply', 'failure', 'readable'}]}``: both replies are kept. An infrastructure failure (no
    verdict of the model, ``writers.reply_failure``) ends the request with status 'infrastructure' and does not use
    the format retry: the chain's rule applies (one automatic retry, then a pause). Each attempt is first looked up in
    the recorder's sends (``send_or_replay``): on resume a request already answered is not sent again."""
    user = _json(payload)
    attempts = []
    for attempt in (1, 2):
        text = user if attempt == 1 else user + ANALYST_RETRY
        receipt = send_or_replay(call, ANALYST_SYSTEM, text)
        reply, failure = writers.reply_of(receipt), writers.reply_failure(receipt)
        raw = plan_object(reply)
        attempts.append({'request_sha256': writers.request_sha256(ANALYST_SYSTEM, text), 'reply': reply,
                         'failure': failure, 'readable': raw is not None})
        if raw is not None:
            return {'status': 'ok', 'raw': raw, 'request_sha256': attempts[-1]['request_sha256'], 'attempts': attempts}
        if str(failure or '').startswith('infrastructure:'):
            return {'status': 'infrastructure', 'raw': None, 'request_sha256': attempts[-1]['request_sha256'],
                    'attempts': attempts}
    return {'status': 'unreadable', 'raw': None, 'request_sha256': attempts[-1]['request_sha256'], 'attempts': attempts}


# ---- the capability sheet and the plan -------------------------------------------------------------------------------
def check_sheet(sheet):
    """A maker's capability sheet ``{'maker', 'what', 'fields': {name: rule}}``, validated. A rule is ``{'kind':
    'subset', 'values': [...]}`` (a list of allowed values), ``{'kind': 'factors', 'keys': [...], 'range': [low,
    high]}`` (numbers per key) or ``{'kind': 'choice', 'values': [...]}`` (one value), each with its ``meaning``."""
    require(isinstance(sheet, dict) and isinstance(sheet.get('what'), str) and isinstance(sheet.get('fields'), dict),
            'A capability sheet: maker, what, fields')
    for name, rule in sheet['fields'].items():
        require(isinstance(name, str) and isinstance(rule, dict) and rule.get('kind') in FIELD_KINDS,
                'A capability field of a registered kind: ' + str(name))
        if rule['kind'] == 'factors':
            low, high = rule.get('range') or (None, None)
            require(isinstance(rule.get('keys'), list) and rule['keys'] and _number(low) and _number(high)
                    and Fraction(low) <= Fraction(high), 'A factors field: keys and a range')
        else:
            require(isinstance(rule.get('values'), list) and rule['values'], 'A field of allowed values')
    return sheet


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _short(value, limit):
    return value[:limit] if isinstance(value, str) else str(value)[:limit]


def check_spec(spec, sheet):
    """(the kept spec, the dropped parts) of one weakness's or guard's spec against the capability sheet: an unknown
    field, a value the field does not allow, a number outside its range or of another type is dropped and named
    (``{'field', 'value'?, 'reason'}``); a field left without a value is dropped as 'empty'. Kept values are in the
    sheet's order (a subset), keyed in the sheet's key order (factors)."""
    fields = check_sheet(sheet)['fields']
    if spec is None:
        return {}, []
    if not isinstance(spec, dict):
        return {}, [{'field': None, 'reason': 'not_an_object'}]
    kept, dropped = {}, []
    for name in sorted(spec, key=str):
        value, rule = spec[name], fields.get(name)
        if rule is None:
            dropped.append({'field': _short(name, ID_CHARS), 'reason': 'unknown_field'})
            continue
        if rule['kind'] == 'subset':
            if not isinstance(value, list):
                dropped.append({'field': name, 'reason': 'not_a_list'})
                continue
            for other in value:
                if other not in rule['values']:
                    dropped.append({'field': name, 'value': _short(other, ID_CHARS), 'reason': 'unknown_value'})
            found = [allowed for allowed in rule['values'] if allowed in value]
            if found:
                kept[name] = found
            else:
                dropped.append({'field': name, 'reason': 'empty'})
        elif rule['kind'] == 'factors':
            if not isinstance(value, dict):
                dropped.append({'field': name, 'reason': 'not_an_object'})
                continue
            low, high = (Fraction(bound) for bound in rule['range'])
            found = {}
            for key in sorted(value, key=str):
                number = value[key]
                if key not in rule['keys']:
                    dropped.append({'field': name, 'value': _short(key, ID_CHARS), 'reason': 'unknown_key'})
                elif not _number(number) or isinstance(number, bool):
                    dropped.append({'field': name, 'value': _short(key, ID_CHARS), 'reason': 'not_a_number'})
                elif not low <= Fraction(number) <= high:
                    dropped.append({'field': name, 'value': _short(key, ID_CHARS), 'reason': 'out_of_range'})
                else:
                    found[key] = number
            if found:
                kept[name] = {key: found[key] for key in rule['keys'] if key in found}
            else:
                dropped.append({'field': name, 'reason': 'empty'})
        else:
            if isinstance(value, str) and value in rule['values']:
                kept[name] = value
            else:
                dropped.append({'field': name, 'value': _short(value, ID_CHARS), 'reason': 'unknown_value'})
    return kept, dropped


def _text(value, limit, name, position, truncated):
    if not isinstance(value, str):
        return ''
    value = value.strip()
    if len(value) > limit:
        truncated.append({'part': name, 'position': position, 'chars': len(value)})
        value = value[:limit]
    return value


def validate_plan(raw, learn_outcomes, repeats, capability_sheet):
    """The plan of T4 from the analyst's raw object, by fixed code: ``(plan, record)``.

    Weaknesses, in the order given: an evidence id that is not a learn item is dropped (``record['evidence']``,
    reason 'not_a_learn_item'); a learn item counts as evidence only when B failed it (an outcome that is not True)
    in at least EVIDENCE_MIN_FAILED_RUNS of its R runs (else 'failed_in_too_few_runs'); a repeated id counts once;
    a weakness is kept only with at least EVIDENCE_MIN_ITEMS counted items and a description. Its spec keeps the
    fields and values of the capability sheet (``check_spec``; the rest is named in ``record['spec']``). Kept
    weaknesses get the ids w1, w2, ... in plan order (the analyst's own id is kept as ``given_id``), guards g1, g2,
    ... : ids are unique and path-safe whatever the analyst wrote. Texts are cut to fixed lengths (named in
    ``record['truncated']``). An unreadable plan (``raw`` None) is the plan without weaknesses or guards and the
    record says so. With fewer than MIN_KEPT_WEAKNESSES kept weaknesses ``items.counts`` applies the 20 % rule."""
    require(type(repeats) is int and repeats >= 1, 'R >= 1')
    require(all(isinstance(v, (list, tuple)) and len(v) == repeats for v in learn_outcomes.values()),
            'R outcomes per learn item')
    check_sheet(capability_sheet)
    record = {'version': RECORD_VERSION, 'readable': isinstance(raw, dict) and isinstance(raw.get('weaknesses'), list),
              'rule': {'evidence_min_items': EVIDENCE_MIN_ITEMS, 'evidence_min_failed_runs': EVIDENCE_MIN_FAILED_RUNS,
                       'repeats': repeats, 'min_kept_weaknesses': MIN_KEPT_WEAKNESSES},
              'weaknesses': [], 'guards': [], 'evidence': [], 'spec': [], 'truncated': []}
    if not record['readable']:
        plan = {'weaknesses': [], 'guards': [], 'note': '', 'unreadable': True}
        record.update(reason='unreadable', kept=0)
        return plan, record
    weaknesses, guards, truncated = [], [], record['truncated']
    for position, entry in enumerate(raw['weaknesses'], 1):
        row = {'position': position, 'given_id': None, 'kept': False, 'id': None, 'reason': None,
               'evidence_given': 0, 'evidence_counted': 0}
        record['weaknesses'].append(row)
        if not isinstance(entry, dict):
            row['reason'] = 'not_an_object'
            continue
        row['given_id'] = _short(entry['id'], ID_CHARS) if entry.get('id') is not None else None
        description = _text(entry.get('description'), DESCRIPTION_CHARS, 'description', position, truncated)
        evidence = entry.get('evidence') if isinstance(entry.get('evidence'), list) else []
        counted, seen = [], set()
        for value in evidence:
            if not isinstance(value, str):
                record['evidence'].append({'weakness': position, 'id': _short(value, ID_CHARS), 'reason': 'not_an_id'})
                continue
            if value in seen:
                continue
            seen.add(value)
            if value not in learn_outcomes:
                record['evidence'].append({'weakness': position, 'id': _short(value, ID_CHARS),
                                           'reason': 'not_a_learn_item'})
                continue
            failed = sum(outcome is not True for outcome in learn_outcomes[value])
            if failed >= EVIDENCE_MIN_FAILED_RUNS:
                counted.append(value)
            else:
                record['evidence'].append({'weakness': position, 'id': value, 'reason': 'failed_in_too_few_runs',
                                           'failed_runs': failed})
        row.update(evidence_given=len(seen), evidence_counted=len(counted))
        spec, dropped = check_spec(entry.get('spec'), capability_sheet)
        record['spec'] += [{'weakness': position, **part} for part in dropped]
        if not description:
            row['reason'] = 'no_description'
        elif len(counted) < EVIDENCE_MIN_ITEMS:
            row['reason'] = 'too_little_evidence'
        else:
            row.update(kept=True, id='w%d' % (len(weaknesses) + 1), reason='kept')
            weaknesses.append({'id': row['id'], 'given_id': row['given_id'], 'description': description,
                               'evidence': counted,
                               'signature': _text(entry.get('signature'), SIGNATURE_CHARS, 'signature', position,
                                                  truncated),
                               'spec': spec})
    for position, entry in enumerate(raw.get('guards') or [], 1):
        row = {'position': position, 'kept': False, 'id': None, 'reason': None}
        record['guards'].append(row)
        description = (_text(entry.get('description'), DESCRIPTION_CHARS, 'guard_description', position, truncated)
                       if isinstance(entry, dict) else '')
        if not description:
            row['reason'] = 'not_an_object' if not isinstance(entry, dict) else 'no_description'
            continue
        spec, dropped = check_spec(entry.get('spec'), capability_sheet)
        record['spec'] += [{'guard': position, **part} for part in dropped]
        row.update(kept=True, id='g%d' % (len(guards) + 1), reason='kept')
        guards.append({'id': row['id'], 'description': description, 'spec': spec})
    note = _text(raw.get('note'), NOTE_CHARS, 'note', 0, truncated)
    require(all(WEAKNESS_ID.match(w['id']) for w in weaknesses), 'Canonical weakness ids')
    plan ={'weaknesses': weaknesses, 'guards': guards, 'note': note, 'unreadable': False}
    record.update(reason='validated', kept=len(weaknesses),
                  rule_applied='quota' if len(weaknesses) >= MIN_KEPT_WEAKNESSES else 'reduced_attack')
    return plan, record


# ---- the experience log ----------------------------------------------------------------------------------------------
EXPERIENCE_KINDS = ('card', 'program', 'archive')
REASON_CHARS = 64
_REASON = re.compile(r'[^A-Za-z0-9_:.\-]')


def reason_label(reason):
    """A refusal reason as a short label: the text before its first ': ' (a screen reason carries its evidence after
    it), characters outside [A-Za-z0-9_:.-] dropped, at most 64 characters."""
    if not isinstance(reason, str) or not reason:
        return 'unknown'
    return _REASON.sub('', reason.split(': ', 1)[0])[:REASON_CHARS] or 'unknown'


def _points(value):
    if value is None:
        return None
    require(_number(value) and not isinstance(value, bool), 'Gains are numbers in points')
    return round(float(value), 2)


def _n(value):
    require(value is None or (type(value) is int and value >= 0), 'n is a count')
    return value


def candidates_of_decisions(decisions):
    """The candidate rows of one earlier step's ``decisions.json`` for ``experience_log``: its card rounds
    (``cards``), then its program rows (``programs``; a row with ``origin`` 'archive' -- P1's archive candidate -- is
    kind 'archive'), each ``{'kind', 'accepted', 'reason', 'gain_points', 'n'}`` (gain and n are None for a row that
    never reached a gate). The gains of accepted candidates on each weakness's attack items (``attack``) are not in a
    typed-v2 record: P2b adds them from the step's item records."""
    rows = []
    for kind_of, key in ((lambda row: 'card', 'cards'),
                         (lambda row: 'archive' if row.get('origin') == 'archive' else 'program', 'programs')):
        for row in decisions.get(key) or []:
            rows.append({'kind': kind_of(row), 'accepted': row.get('accepted') is True, 'reason': row.get('reason'),
                         'gain_points': row.get('gain_points'), 'n': row.get('n')})
    return rows


def experience_log(earlier_steps):
    """The experience log of T4, built by fixed code from THIS chain's earlier steps, counts and short descriptions
    only (no item, no item text, no reply, nothing of a gate or judging item: every field below is whitelisted).

    Input, one plain dict per earlier step, steps increasing::

        {'step': int, 'bench': str,
         'candidates': [{'kind': 'card' | 'program' | 'archive', 'accepted': bool, 'reason': str | None,
                         'gain_points': number | None, 'n': int | None,
                         'attack': {weakness id: {'n': int, 'gain_points': number}}  # optional, accepted ones
                        }, ...],                      # every decision row of the step, in decision order
         'weaknesses': [{'id': 'w1', 'description': str}, ...]}   # the step's kept weaknesses ([] when none)

    Output, one row per step: ``{'step', 'bench', 'candidates': [{'candidate' (1-based), 'kind', 'decision':
    'accepted' | 'refused', 'reason' (a short label, None when accepted), 'gain_points' (2 decimals), 'n'}],
    'weaknesses': [{'id', 'description' (at most 500 characters), 'accepted_candidates_on_attack': [{'candidate',
    'kind', 'n', 'gain_points'}]}]}``."""
    out, last = [], 0
    for entry in earlier_steps:
        require(isinstance(entry, dict) and type(entry.get('step')) is int and entry['step'] > last,
                'Earlier steps in increasing order')
        require(entry.get('bench') in ORDER, 'An earlier step names its bench')
        last = entry['step']
        candidates, rows = [], list(entry.get('candidates') or [])
        for number, row in enumerate(rows, 1):
            require(isinstance(row, dict) and row.get('kind') in EXPERIENCE_KINDS and type(row.get('accepted')) is bool,
                    'A candidate row: kind and accepted')
            candidates.append({'candidate': number, 'kind': row['kind'],
                               'decision': 'accepted' if row['accepted'] else 'refused',
                               'reason': None if row['accepted'] else reason_label(row.get('reason')),
                               'gain_points': _points(row.get('gain_points')), 'n': _n(row.get('n'))})
        weaknesses = []
        for weakness in entry.get('weaknesses') or []:
            require(isinstance(weakness, dict) and isinstance(weakness.get('id'), str)
                    and WEAKNESS_ID.match(weakness['id']) is not None, 'A kept weakness id (w1, w2, ...)')
            description = weakness.get('description') if isinstance(weakness.get('description'), str) else ''
            on_attack = []
            for number, row in enumerate(rows, 1):
                found = (row.get('attack') or {}).get(weakness['id']) if row['accepted'] else None
                if found is not None:
                    require(isinstance(found, dict), 'An attack result is {n, gain_points}')
                    on_attack.append({'candidate': number, 'kind': row['kind'], 'n': _n(found.get('n')),
                                      'gain_points': _points(found.get('gain_points'))})
            weaknesses.append({'id': weakness['id'], 'description': description[:DESCRIPTION_CHARS],
                               'accepted_candidates_on_attack': on_attack})
        out.append({'step': entry['step'], 'bench': entry['bench'], 'candidates': candidates, 'weaknesses': weaknesses})
    return out
