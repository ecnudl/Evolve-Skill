"""Writers of typed-v2 (design §5.6): the card writer (the v2.25 prompts, the typed card screen of ``cards`` and one
retry), the program writer (the typed-owned prompt of ``engineer_prompt``, the typed reply reader ``replies`` with
one format retry per unit attempt, the unchanged static screen plus the typed hooks check, one fix call with screen
evidence per screened failure, and the promotion of a later proposal when an earlier one fails the screen; DESIGN
3.2, 3.3) with a typed payload (a skill index of names and descriptions in place of the card body and the package
sources), and the describer (the probe-3 description prompt of ``library``).

Every model call goes through ``call(system, user) -> receipt`` (``units.CallRecorder``): a reply counts only when the
receipt delivered (``ok`` and ``finish_reason == 'stop'``), anything else is "no reply" and is recorded like a screen
failure. The request identity of a call is ``request_sha256(system, user)``; a program's lineage carries the identity
of the call that wrote its final source. Nothing here opens test material: the examples are learn-slice cells and
practice items handed in by the chain, and the writer never sees item references other than those of failed
practice items (as the v2.25 writer does).
"""
from __future__ import annotations

import hashlib
import json
import re

from skillopt.coevo5 import texts
from skillopt.coevo5.data import ranked
from skillopt.coevo5.roles import fit
from skillopt.continual_eval.core import require
from skillopt.execskill import (engineer, engineer_payload, engineer_reader, policy, profiles, v222_cards, v225_cards,
                                v225_writer)
from skillopt.execskill.corpus import Corpus
from skillopt.execskill.errors import PackageInvalid
from skillopt.execskill.package import MAX_STATE_BYTES, NOTE_HOOKS, SECOND_CALL_HOOKS, Procedure

from . import BASE_CARD_DEFAULT, DESCRIPTION_CHAR_CAP, MACHINERY, MAX_PROGRAM_CANDIDATES, MAX_PROGRAM_PROPOSALS, SEED
from . import cards, engineer_prompt, library, replies, tasktypes, units

VIEW_CHARS, REPLY_HEAD, REPLY_TAIL = v225_writer.VIEW_CHARS, v225_writer.REPLY_HEAD, v225_writer.REPLY_TAIL
REFERENCE_CHARS = v225_writer.REFERENCE_CHARS
CARD_ATTEMPTS = 2            # one write + one retry on a screen failure (design §2.4)
DESCRIBE_ATTEMPTS = 2        # one call + one format retry
EXAMPLE_TAG = 'typed-v1:writer-examples'  # draw key, typed-v1's value (addendum O4): same writer-example draw
POLICY_VERSION = profiles.POLICY_VERSIONS[MACHINERY]      # fivebench-execskill-v2-22-policy (design §5.4)
MAX_DETAIL_CHARS = 600
# The status of one row of s<k>/programs/proposals.json (DESIGN 3.2): the six of the promotion loop, and 'no_reply'
# for the one row of a proposal call that delivered no reply (typed-v1's 'no_reply' row).
PROPOSAL_STATUS = ('passed', 'passed_after_fix', 'dropped_screen', 'unreadable', 'kind_not_new', 'not_needed',
                   'no_reply')
HOOK_VIEW_CAPS = {'string_chars': 1500, 'list_entries': 20}
HOOK_VIEW_MEANING = 'Exact hook view arguments, truncated only at the stated caps; not the solver prompt.'
DESCRIPTION_RETRY = ('\n\nFormat retry: return exactly one JSON object {"description": "..."} whose string has at most '
                     '%d characters, with no Markdown and no additional keys.' % DESCRIPTION_CHAR_CAP)
INDEX_KEYS = frozenset({'name', 'kind', 'description', 'home_type'})  # home_type: an opaque type id, never a bench
# Addendum D17: the label of the base card block of the card writer's request (the engineer's is
# ``engineer_prompt.BASE_CARD_MEANING``); shown only where the base adds to the format block (``base_card_block``).
BASE_CARD_MEANING = ('The instruction the solver already receives on every task of this kind: this whole text is '
                     'placed in its system prompt right after your card, unchanged, and it contains every line of '
                     'format_block. Your card adds to it: do not repeat it and do not contradict it. The length '
                     'limits apply to your card alone.')
# Addendum D16 (a): the card writer's request of a shared type (its home type also holds sources of earlier benches)
# gets the key ``members``: this sentence, naming the member sources (``%s``) and stating the acceptance rule (b), and
# one block per member source labelled with it (its format block and, where the base adds to it, its base card under
# MEMBER_BASE_MEANING, as 5b shows the current bench's (D17); and its examples). The engineer's are
# ``engineer_prompt.MEMBERS_MEANING`` / ``MEMBER_BASE_MEANING``. A type of one bench gets no such key.
MEMBERS_MEANING = ('Your card is also placed, unchanged, in the system prompt of every task of the other sources of '
                   'this task type: %s. members.sources shows for each of them what the solver already receives there '
                   '(its format_block and, where given, its base card) and examples of the solver\'s attempts there '
                   'under the current card, with their scored outcome; write the card so that it holds for those '
                   'tasks too. A card is kept only if, on held-out practice tasks, the solver does clearly better with '
                   'it on tasks like those in examples AND, on the tasks of each of these sources, no worse with it '
                   'than without it beyond the measured noise.')
MEMBER_BASE_MEANING = ('The instruction the solver already receives on every task of this source: this whole text is '
                       'placed in its system prompt right after your card, unchanged, and it contains every line of '
                       'this source\'s format_block. Your card adds to it: do not repeat it and do not contradict it.')
MEMBER_RULE = 'mean gain >= minus the required points on each listed source'  # the revision summary's member clause
# typed-v3 T7 (brief P3b): the revision summary's clauses under the gate rule 'evolution' (counts on the improvement
# items E = R + A, the harm clause on the whole gate list J) and of a round refused at its screen (no gate ran)
EVOLUTION_RULE = 'mean gain >= required points and fixed > broken on the improvement items'
HARM_RULE = 'no loss beyond the allowed points on the whole gate list'
SCREEN_RULE = 'one run per screen item: passes >= the mean passes of the current mount'


# ---- shared helpers --------------------------------------------------------------------------------------------
def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _text(value):
    return value if isinstance(value, str) else _json(value)


def request_sha256(system, user):
    """The identity of one role request: what attempt records and a program's lineage name."""
    return hashlib.sha256(_json({'system': system, 'user': user}).encode('utf-8')).hexdigest()


def reply_of(receipt):
    """The reply text of a delivered receipt (ok, finished with 'stop'); None otherwise (no reply)."""
    if not isinstance(receipt, dict) or receipt.get('ok') is not True or receipt.get('finish_reason') != 'stop':
        return None
    response = receipt.get('response')
    return response if isinstance(response, str) else None


def _send(call, system, user):
    """One recorded call; the shell's call wrapper charges and records, this only reads the reply."""
    return reply_of(call(system, user)), request_sha256(system, user)


def task_card(bench, runtime_table):
    """The public task-kind text the writers read (ZebraLogic's own card, else the coevo5 card under the layout)."""
    return v225_writer.task_card(bench, runtime_table or {})


def corpus_for(bench, items):
    """The leakage corpus of the practice items; ALFWorld surfaces are the registered initial observations."""
    items = list(items)
    if bench != 'alfworld':
        return Corpus(bench, items)
    observations = {}
    for item in items:
        view = (item.get('public') or {}).get('routing_view') or {}
        if isinstance(view.get('initial_observation'), str):
            observations[item['task_id']] = view['initial_observation']
    return Corpus(bench, items, alfworld_texts=observations)


def hook_view_for(bench, view):
    """One item's exact routing view, excerpted as ``engineer.hook_views`` does (strings 1500, lists 20 entries);
    ALFWorld's hook view is the first step's view derived from the reset view (observation = initial, no history)."""
    require(isinstance(view, dict) and view, 'A hook view sample needs a public routing view')
    hook = view
    if bench == 'alfworld':
        hook = {'initial_observation': view['initial_observation'], 'observation': view['initial_observation'],
                'admissible_commands': list(view.get('admissible_commands_at_reset') or []), 'recent_history': []}
    return {'routing_view': engineer_payload.view_excerpt(view), 'hook_view': engineer_payload.view_excerpt(hook),
            **HOOK_VIEW_CAPS, 'meaning': HOOK_VIEW_MEANING}


# ---- examples from learn-slice outcomes ----------------------------------------------------------------------
def _items_by_id(items):
    found = items if isinstance(items, dict) else {item['task_id']: item for item in items}
    require(all(isinstance(item, dict) and 'public' in item for item in found.values()), 'Practice items carry a public view')
    return found


def _solver_sends(cell):
    """The shell's sends of a cell. The chain records a cell's program-selection call apart (``selection_sends``);
    a send carrying the selection system prompt is skipped here all the same, so that no writer ever reads the
    selection payload (skill index + task) as the solver request."""
    return [s for s in (cell.get('sends') or []) if isinstance(s, dict) and s.get('system') != library.SELECTION_SYSTEM]


def _first_user(cell):
    """The solver's first request (the public view as sent, plus any procedure notes): the example's view."""
    for send in _solver_sends(cell):
        if isinstance(send.get('user'), str) and send['user']:
            return send['user']
    raise ValueError('A writer example needs the solver request of its cell: ' + str(cell.get('item_id')))


def _reply(cell):
    if isinstance(cell.get('reply'), str):
        return cell['reply']
    for send in reversed(_solver_sends(cell)):
        response = (send.get('receipt') or {}).get('response')
        if isinstance(response, str):
            return response
    return ''


def _alfworld_reference(cell):
    """ALFWorld has no answer: the episode's end (won/lost), its step count and the last observation seen."""
    sends = _solver_sends(cell)
    observation = ''
    if sends:
        try:
            last = json.loads(sends[-1].get('user') or '{}')
            observation = last.get('observation') if isinstance(last, dict) else ''
        except ValueError:
            observation = ''
    outcome = 'won' if cell.get('correct') is True else 'lost'
    return '%s after %d steps; last observation: %s' % (outcome, len(sends), observation or '')


def _sheet_reference(private):
    """The answer-position values of the item's first answer workbook (route B's frozen reading); None when unread."""
    try:
        from skillopt.execskill.step import _sheet_reference as read_reference
        return read_reference(private)
    except Exception:  # an unreadable workbook only costs the writer its reference, never the step
        return None


def reference_of(bench, item, cell):
    """A failed item's reference in route B's frozen answer shape, as text; None when the bench or item has none."""
    if bench == 'alfworld':
        return _alfworld_reference(cell)
    private = item.get('private') or {}
    if bench == 'spreadsheetbench':
        value = _sheet_reference(private)
    elif bench == 'searchqa':
        value = private.get('answers')
    else:
        value = private.get('answer')
    return _text(value) if isinstance(value, (str, list, dict)) and value else None


def _example(bench, cell, item, outcome):
    user = _first_user(cell)
    entry = {'task_id': cell['item_id'], 'view': v225_writer.truncate(user, VIEW_CHARS),
             'reply': v225_writer.truncate(_reply(cell), REPLY_HEAD + REPLY_TAIL, head=REPLY_HEAD, tail=REPLY_TAIL),
             'outcome': outcome, 'request_user': user}
    if outcome == 'fail':
        reference = reference_of(bench, item, cell)
        if reference:
            entry['reference'] = reference[:REFERENCE_CHARS]
    return entry


def outcomes_for_writer(cells, items, *, bench, max_failures=profiles.ENGINEER_SHOWN['failures'],
                        max_successes=profiles.ENGINEER_SHOWN['successes'], seed=SEED, baseline=None):
    """Learn-slice outcomes as writer examples: failures first, each group in the seeded order of ``data.ranked``
    (as ``v225_writer.select_examples``); unknown outcomes are never shown; one example per item. Each example:
    task_id, view (<= 3000 chars of the solver request), reply (300 head + 1200 tail), outcome, reference (failures)
    and ``request_user`` (the full solver request, what the engineer's trajectories carry). ``baseline``
    ({item id: correct} of the current arm) is the revision round's ordering key of v2.25: within each group the
    items the candidate card CHANGED come first (failures it broke, successes it fixed), then the seeded order."""
    by_id = _items_by_id(items)
    chosen = {}
    for cell in cells:
        if cell.get('bench') != bench or cell.get('correct') not in (True, False) or cell['item_id'] in chosen:
            continue
        require(cell['item_id'] in by_id, 'Writer cells belong to the supplied practice items')
        chosen[cell['item_id']] = cell
    out = []
    for outcome, limit in (('fail', max_failures), ('pass', max_successes)):
        found = [{'task_id': item_id, 'cell': cell} for item_id, cell in chosen.items()
                 if (cell['correct'] is True) == (outcome == 'pass')]
        ordered = ranked(found, seed, EXAMPLE_TAG + ':' + bench)
        if baseline is not None:  # changed outcomes first, the seeded order within each half (stable sort)
            ordered = sorted(ordered, key=lambda row: 0 if baseline.get(row['task_id']) == (outcome == 'fail') else 1)
        for row in ordered[:limit]:
            out.append(_example(bench, row['cell'], by_id[row['task_id']], outcome))
    return out


def _shown(example):
    """The v2.25 writer shape of one example (what the request shows and the screens compare with)."""
    shown = {'view': example['view'], 'reply': example.get('reply') or '', 'outcome': example['outcome']}
    if example.get('reference') is not None:
        shown['reference'] = example['reference']
    return shown


# ---- the card writer -------------------------------------------------------------------------------------------
def revision_result(decision):
    """The gate's counts for the revision round: numbers and short labels only, never rows, replies or item ids.

    A typed-v2 card decision (``gates.card_decision``, DESIGN 3.4) is read on item means of R runs per arm: items
    better / worse / tied, the mean gain ``gain_points`` and this decision's own tau (from its baseline's repeats);
    ``excluded_unknown`` is always 0 (no item is excluded; a model-side unknown run scores 0). The keys of the
    result are typed-v1's, so the round-2 request keeps its shape (DESIGN 4.2 (2)). A decision of a shared type
    (addendum D16 a: ``shared_with``) adds ``member_rule`` and ``member_check``: per member source (its label, never a
    bench name) the counts and points of its check, or ``not_run`` when the round never reached it.

    typed-v3 T7 (brief P3b): a card decided under the gate rule 'evolution' (its ``evolution`` block) gives the counts
    and points on the improvement items E = R + A as above (``rule`` EVOLUTION_RULE; ``failing_clause`` may be 'harm')
    and the harm clause on the whole gate list J (its items, mean gain and allowed loss, ``harm_rule``); a round refused
    at its screen (``screen_run``, no gate) gives the screen's counts (``stage`` 'screen'). Never the ids of E or of
    the screen items: counts and short labels only, as before. A typed-v2 style decision gives exactly the keys above."""
    require(isinstance(decision, dict), 'A revision carries its gate decision')
    screen = decision.get('screen_run')
    if decision.get('kind') == 'card' and isinstance(screen, dict) and 'per_item' not in decision:
        # typed-v3 T7: the round was refused at its screen and no gate ran: the screen's counts only
        out = {'stage': 'screen', 'touched': screen['items'], 'passes': screen['c'],
               'baseline_runs_right': screen['b'], 'baseline_runs_per_item': screen['repeats'],
               'pass_points': screen['candidate_pass_points'], 'baseline_pass_points': screen['baseline_pass_points'],
               'rule': SCREEN_RULE, 'decision': 'reject', 'failing_clause': decision['reason']}
        if decision.get('shared_with'):
            out.update(member_rule=MEMBER_RULE, member_check=_member_check(decision))
    elif decision.get('kind') == 'card':  # a gates.card_decision record
        require(type(decision.get('repeats')) is int and decision.get('excluded_unknown') == 0,
                'A typed-v2 card decision (R runs per item and arm, no item excluded)')
        evolution = decision.get('evolution')
        if evolution is None:
            better, worse = decision['better'], decision['worse']
            out = {'stage': 'gate', 'touched': decision['n'], 'fixed': better, 'broken': worse, 'net': better - worse,
                   'tied': decision['tied'], 'excluded_unknown': decision['excluded_unknown'],
                   'mean_gain_points': decision['gain_points'], 'required_mean_gain_points': decision['tau_points'],
                   'rule': 'mean gain >= required points and fixed > broken on the gate slice',
                   'decision': 'accept' if decision['accepted'] else 'reject',
                   'failing_clause': None if decision['accepted'] else decision['reason']}
        else:  # typed-v3 T7 (gate rule 'evolution'): the deciding counts on E = R + A, the harm clause on J
            better, worse = evolution['better'], evolution['worse']
            out = {'stage': 'gate', 'touched': evolution['n'], 'fixed': better, 'broken': worse, 'net': better - worse,
                   'tied': evolution['tied'], 'excluded_unknown': decision['excluded_unknown'],
                   'mean_gain_points': evolution['gain_points'], 'required_mean_gain_points': evolution['tau_points'],
                   'rule': EVOLUTION_RULE, 'whole_list_items': decision['n'],
                   'whole_list_mean_gain_points': decision['gain_points'], 'allowed_loss_points': decision['tau_points'],
                   'harm_rule': HARM_RULE, 'decision': 'accept' if decision['accepted'] else 'reject',
                   'failing_clause': None if decision['accepted'] else decision['reason']}
        if decision.get('shared_with'):
            out.update(member_rule=MEMBER_RULE, member_check=_member_check(decision))
    else:
        out = dict(decision)
    for key, value in out.items():
        for inner in ([v for row in value for v in row.values()] if key == 'member_check' else [value]):
            require(inner is None or type(inner) in (int, float, bool) or (type(inner) is str and len(inner) <= 80),
                    'Card feedback holds counts and short labels only')
    return out


def _member_check(decision):
    """The member part of a revision summary (addendum D16 a): counts and points only, one row per member source."""
    checked = {row['bench']: row for row in decision.get('members') or []}
    rows = []
    for member in decision['shared_with']:
        found = checked.get(member['bench'])
        if found is None:
            rows.append({'source': member['source'], 'decision': 'not_run'})
            continue
        rows.append({'source': member['source'], 'touched': found['n'], 'fixed': found['better'],
                     'broken': found['worse'], 'net': found['better'] - found['worse'], 'tied': found['tied'],
                     'mean_gain_points': found['gain_points'], 'allowed_loss_points': found['tau_points'],
                     'decision': 'hold' if found['no_regress'] else 'harm'})
    return rows


def _fit_examples(request):
    """Drop shown successes, then failures, until the request plus the retry sentence fits the v2.25 ceiling. A
    shared type's member examples (addendum D16 a) go first, successes then failures, the last source first, so the
    current bench's part of the request stays as it would be without them whenever the members can make room."""
    dropped = {'successes': 0, 'failures': 0}
    retry_chars = 2 + max(len(v225_cards.CARD_RETRY.format(reason=r)) for r in v225_cards.RETRY_REASONS.values())
    if 'members' in request:
        dropped.update(member_successes=0, member_failures=0)
        blocks = request['members']['sources']
        while (len(_json(request)) + retry_chars > v225_cards.CARD_WRITER_INPUT_CHARS
               and any(block['examples'] for block in blocks)):
            passing = [b for b in blocks if any(row['outcome'] == 'pass' for row in b['examples'])]
            rows = (passing or [b for b in blocks if b['examples']])[-1]['examples']
            successes = [i for i, row in enumerate(rows) if row['outcome'] == 'pass']
            removed = rows.pop(successes[-1] if successes else len(rows) - 1)
            dropped['member_successes' if removed['outcome'] == 'pass' else 'member_failures'] += 1
    while len(_json(request)) + retry_chars > v225_cards.CARD_WRITER_INPUT_CHARS and request['examples']:
        successes = [i for i, row in enumerate(request['examples']) if row['outcome'] == 'pass']
        removed = request['examples'].pop(successes[-1] if successes else len(request['examples']) - 1)
        dropped['successes' if removed['outcome'] == 'pass' else 'failures'] += 1
    require(len(_json(request)) + retry_chars <= v225_cards.CARD_WRITER_INPUT_CHARS,
            'Fixed writer request fits its registered input ceiling')
    return dropped


def base_card_block(bench, base_card, meaning):
    """The base card block of a writer request (addendum D17): what the solver already receives besides the learned
    text, ``{'meaning': meaning, 'text': mount.base_text(bench, base_card)}`` -- the text every learned mount of the
    bench composes on, so the writer sees exactly what the solver gets. None where the base adds nothing to the
    request's ``format_block`` (the base 'format', and ZebraLogic, whose C is its format block): those requests stay
    byte-identical to the requests without D17."""
    from .mount import base_text, format_block  # lazily: the writers' import list stays as it was before D17
    text = base_text(bench, base_card)
    return None if text == format_block(bench) else {'meaning': meaning, 'text': text}


def _screen_public(request):
    """The public text block of the card screen (``cards.card_screen``'s ``format_block``): the request's format
    block, and under D17 the base card block the writer was shown (text the solver already receives is never a leak
    or a copy of an example); with no base card block it is the format block alone, as before D17. A shared type's
    request (addendum D16) adds each member source's format block and base card text."""
    block = request.get('base_card')
    public = request['format_block'] + ('\n' + block['text'] if block is not None else '')
    for source in (request.get('members') or {}).get('sources') or []:
        public += '\n' + source['format_block'] + ('\n' + source['base_card']['text'] if 'base_card' in source else '')
    return public


def cap_member_examples(examples, member_examples):
    """Addendum D16 (a): a member source's examples are chosen by the rule of the current bench's (``outcomes_for_
    writer``: failures first, each group in its seeded order, unknown outcomes never shown) and are at most as many:
    the first ``len(examples)`` rows of the member's list, in its order. Returns the kept rows."""
    require(all(row.get('outcome') in ('fail', 'pass') for row in member_examples),
            'A member example has a scored outcome')
    return list(member_examples[:len(examples)])


def _member_rows(members):
    """The member rows the chain hands a writer (addendum D16 a): bench, source label and examples each."""
    require(isinstance(members, list) and members, 'A shared type hands the writer at least one member')
    for row in members:
        require(isinstance(row, dict) and isinstance(row.get('bench'), str) and isinstance(row.get('source'), str)
                and row['source'] and isinstance(row.get('examples'), list), 'A member row is bench, source, examples')
    require(len({row['source'] for row in members}) == len(members), 'Each member source once')
    return members


def _member_source(row, base_card, meaning):
    """The head of one member source's block: its label, and what the solver already receives on its tasks shown as
    5b shows the current bench's (addendum D17): its ``format_block`` always, and its ``base_card`` block
    (``base_card_block`` with ``meaning``) only where the run's base adds to that format block."""
    found = {'source': row['source'], 'format_block': v222_cards.format_text(row['bench'])}
    block = base_card_block(row['bench'], base_card, meaning)
    if block is not None:
        found['base_card'] = block
    return found


def card_members(members, examples, *, base_card=BASE_CARD_DEFAULT):
    """The ``members`` block of a shared type's card writer request (addendum D16 a): ``MEMBERS_MEANING`` naming the
    member sources, and per source (in member order) its label, its format block and base card (``_member_source``,
    ``MEMBER_BASE_MEANING``) and its examples (``cap_member_examples``, shown as the current bench's are). Learn-slice
    examples only."""
    rows = _member_rows(members)
    return {'meaning': MEMBERS_MEANING % ', '.join(row['source'] for row in rows),
            'sources': [{**_member_source(row, base_card, MEMBER_BASE_MEANING),
                         'examples': [_shown(example) for example in cap_member_examples(examples, row['examples'])]}
                        for row in rows]}


def card_request(*, bench, runtime, current_text, examples, round, previous=None, result=None,
                 base_card=BASE_CARD_DEFAULT, members=None):
    """The writer's user payload with the keys of ``v225_writer.build_request`` ('write' in round 1, 'revise' with the
    previous card and the gate counts in round 2), plus the base card block (``base_card_block``, addendum D17) when
    the run's base adds to the format block, and for a shared type (``members``, addendum D16 a) the ``members``
    block (``card_members``); returns (request, dropped example counts). Without members the request is the 5w one."""
    require(round in (1, 2) and isinstance(current_text, str), 'A registered card round with the current card text')
    request = {'request': 'write' if round == 1 else 'revise', 'task_card': task_card(bench, runtime),
               'format_block': v222_cards.format_text(bench), 'current_card': current_text,
               'card_rules': {'max_chars': v225_cards.MAX_CARD_CHARS, 'max_bullets': v225_cards.MAX_CARD_BULLETS,
                              'forbidden': list(v225_writer.FORBIDDEN)},
               'examples': [_shown(example) for example in examples], 'evidence': 'practice_only'}
    block = base_card_block(bench, base_card, BASE_CARD_MEANING)
    if block is not None:
        request['base_card'] = block
    if round == 2:
        require(isinstance(previous, str), 'A revision carries its previous card')
        request.update(previous_card=previous, result=revision_result(result))
    if members:
        request['members'] = card_members(members, examples, base_card=base_card)
    return request, _fit_examples(request)


def screen_card(text, *, bench, corpus, shown, task_card, format_block, practice_ids):
    """None when the card text passes the typed-v2 card screen (``cards.card_screen``: no text, more than 4,500
    content characters or more than 12 bullet lines is 'length', then the four v2.25 content screens), else the
    failing key (one of the five ``v225_cards.RETRY_REASONS`` keys)."""
    return cards.card_screen(text, bench=bench, corpus=corpus, shown=shown, task_card=task_card,
                             format_block=format_block, practice_ids=practice_ids)['violation']


def write_card(*, bench, runtime, current_text, examples, corpus, practice_ids, call, round, previous=None, result=None,
               base_card=BASE_CARD_DEFAULT, members=None):
    """One card round: the v2.25 write (round 1) or revise (round 2) prompt (it still tells 3,000 characters and 12
    bullet points), the reply screened by ``cards.card_screen``, one retry whose sentence is ``cards.retry_text``: the
    v2.25 sentence after a content screen; after 'length' the measured cause when it fits the writer's input ceiling.
    Every attempt row holds ``chars`` (content characters, the final newline not counted) and ``bullets``.
    ``base_card``: the run's sealed base (addendum D17): its block in the request where it adds to the format block
    (``card_request``), and the public text of the screen (``_screen_public``); the length rules of D2 count the
    learned text only. ``members`` (a shared type, addendum D16 a): rows {'bench', 'source', 'examples', 'corpus'
    (the member's leakage corpus), 'practice_ids' (its learn ids)}: the request's ``members`` block, and the screen
    reads every example shown and every corpus and practice id behind them (a card never copies a member's example
    or reference either). Returns {'text': str|None, 'attempts': [...], 'request': ..., 'dropped': ...,
    'card_limits': cards.LIMITS_RECORD}."""
    request, dropped = card_request(bench=bench, runtime=runtime, current_text=current_text, examples=examples,
                                    round=round, previous=previous, result=result, base_card=base_card,
                                    members=members)
    shown, corpora, ids = request['examples'], corpus, practice_ids
    if members:
        shown = shown + [row for source in request['members']['sources'] for row in source['examples']]
        corpora = (corpus,) + tuple(row['corpus'] for row in members)
        ids = list(practice_ids) + [i for row in members for i in row['practice_ids']]
    system = v225_cards.CARD_WRITE_SYSTEM if round == 1 else v225_cards.CARD_REVISE_SYSTEM
    message = _json(request)
    attempts, text, seen = [], None, None
    for attempt in range(1, CARD_ATTEMPTS + 1):
        user = message if attempt == 1 else (
            message + '\n\n' + cards.retry_text(seen, room=v225_cards.CARD_WRITER_INPUT_CHARS - len(message) - 2))
        reply, sha = _send(call, system, user)
        text = texts.instruction_text(reply) if isinstance(reply, str) else None
        seen = cards.card_screen(text, bench=bench, corpus=corpora, shown=shown,
                                 task_card=request['task_card'], format_block=_screen_public(request),
                                 practice_ids=ids)
        attempts.append({'request_sha256': sha, 'violation': seen['violation'], 'chars': seen['chars'],
                         'bullets': seen['bullets'], 'no_reply': reply is None})
        if seen['violation'] is None:
            break
    return {'text': text if seen['violation'] is None else None, 'attempts': attempts, 'request': request,
            'dropped': dropped, 'card_limits': dict(cards.LIMITS_RECORD)}


# ---- the program writer (typed engineer prompt, typed reply reader, typed payload) ----------------------------
def engineer_system(bench, purpose):
    """The program writer's system text: ``engineer_prompt.system`` (typed-owned and pinned, the same family on all
    five benches; ValueError for an unknown bench or a purpose other than 'propose' / 'fix')."""
    return engineer_prompt.system(bench, purpose)


_PROMPT_CHECK = {}   # engineer_prompt.verify() of this process (memoised on success)


def _prompt_verified():
    """``engineer_prompt.verify()`` once per process: the ten pinned texts re-rendered from the bound modules and the
    22 rule examples run through the frozen screen (RuntimeError on a mismatch, so no request is built from a text
    that disagrees with the screen that runs). Returns its ``{'version', 'pins'}``."""
    if 'verified' not in _PROMPT_CHECK:
        _PROMPT_CHECK['verified'] = engineer_prompt.verify()
    return _PROMPT_CHECK['verified']


def trajectory_examples(examples, bench):
    """Writer examples in the shape ``engineer._shown_view`` gives the engineer: one 'first' call holding the exact
    solver request, the reply, the token and (failures) the reference; an empty shell record."""
    out = []
    for example in examples:
        require(isinstance(example.get('request_user'), str) and example['request_user'],
                'An engineer example carries the solver request of its cell')
        kind = 'failures' if example['outcome'] == 'fail' else 'successes'
        entry = {'kind': kind, 'bench': bench, 'task_id': example['task_id'], 'token': example['outcome'],
                 'calls': [{'purpose': 'first', 'user': example['request_user']}],
                 'replies': [example.get('reply') or ''], 'shell': {'notes': [], 'faults': [], 'procedure_calls': []}}
        if kind == 'failures' and example.get('reference') is not None:
            entry['reference'] = example['reference']
        out.append(entry)
    return out


def _index_rows(skill_index):
    """Names, kinds, descriptions and (when given) the opaque home type only: a row carrying anything else (a body,
    a text) is refused here. The engineer sees the index of ALL types (design §5.2)."""
    rows = []
    for row in skill_index:
        require(isinstance(row, dict) and set(row) <= INDEX_KEYS and isinstance(row.get('name'), str)
                and isinstance(row.get('description'), str), 'A skill index row is name, kind, description and home type')
        found = {'name': row['name'], 'kind': row.get('kind'), 'description': row['description']}
        if row.get('home_type') is not None:
            found['home_type'] = str(row['home_type'])
        rows.append(found)
    return rows


def program_payload(*, bench, runtime, skill_index, examples, hook_view, base_card=BASE_CARD_DEFAULT, members=None):
    """The proposal user message: task kind, format block, the skill index, the trajectories (trimmed to 6,000-char
    public excerpts, then fitted to ROLE_INPUT_BYTES), one hook view sample; no learned card text, no package
    sources. Under addendum D17 it also holds the base card block (``base_card_block`` with
    ``engineer_prompt.BASE_CARD_MEANING``) where the run's base adds to the format block. For a shared type
    (``members``, addendum D16 a) it holds ``members`` (``program_members``); the members' trajectories are fitted
    first (the last ones of the last source go first), so the current bench's part stays as it is whenever they can
    make room. Without members the payload is the 5w one."""
    user = {'request': 'propose', 'bench': bench, 'task_card': task_card(bench, runtime),
            'format_block': v222_cards.format_text(bench), 'skill_index': _index_rows(skill_index),
            'trajectories': trajectory_examples(examples, bench), 'hook_views': hook_view,
            'detectors': {}, 'previous': None}
    block = base_card_block(bench, base_card, engineer_prompt.BASE_CARD_MEANING)
    if block is not None:
        user['base_card'] = block
    payload = engineer_payload.trim(user)
    if members:
        payload['members'] = program_members(members, examples, base_card=base_card)
        sources = payload['members']['sources']
        # measured as ``fit`` measures it, with its key ``trajectories_omitted`` (fix-b, review rb-requests F2: without
        # it a bound inside those bytes made ``fit`` drop a current-bench trajectory while a member one was left)
        while (_message_bytes({**payload, 'trajectories_omitted': 0}) > profiles.ROLE_INPUT_BYTES
               and any(s['trajectories'] for s in sources)):
            source = [s for s in sources if s['trajectories']][-1]
            source['trajectories'], source['trajectories_omitted'] = (source['trajectories'][:-1],
                                                                      source['trajectories_omitted'] + 1)
    return fit(payload, 'trajectories', profiles.ROLE_INPUT_BYTES)


def _message_bytes(user):
    """The UTF-8 size of a role message as ``fit`` measures it (``coevo5.roles.message_bytes``, the same expression;
    kept here so that ``typed`` reads no further frozen name)."""
    return len(json.dumps(user, ensure_ascii=False, sort_keys=True).encode())


def program_members(members, examples, *, base_card=BASE_CARD_DEFAULT):
    """The ``members`` block of a shared type's proposal payload (addendum D16 a): ``engineer_prompt.MEMBERS_MEANING``
    naming the member sources and stating the member rule, and per source (in member order) its label, its format
    block and base card (``_member_source`` with ``engineer_prompt.MEMBER_BASE_MEANING``, D17) and its trajectories:
    the member's examples, at most as many as the current bench's (``cap_member_examples``), rendered by
    ``trajectory_examples`` and trimmed by ``engineer_payload.trim`` exactly as the current bench's are (with its
    ``payload_trimming`` counts)."""
    rows = _member_rows(members)
    sources = []
    for row in rows:
        trimmed = engineer_payload.trim({'bench': row['bench'], 'trajectories': trajectory_examples(
            cap_member_examples(examples, row['examples']), row['bench'])})
        sources.append({**_member_source(row, base_card, engineer_prompt.MEMBER_BASE_MEANING),
                        'trajectories': trimmed['trajectories'], 'trajectories_omitted': 0,
                        'payload_trimming': trimmed['payload_trimming']})
    return {'meaning': engineer_prompt.MEMBERS_MEANING % ', '.join(row['source'] for row in rows), 'sources': sources}


def _bounded_entry(entry, source):
    """The procedure metadata the registrar derives (as ``engineer_v28.prepare``): hooks are the module's defined
    hooks, texts cut to their caps, note/state caps bounded by the declared hooks; typed-v2 keeps no replay tests
    and no bench exclusions (routing is by type). A note or state cap that is absent, wrong-typed, 0 or negative is
    the largest one (4,000 note characters, 65,536 state bytes, as the prompt says), a larger one is cut to it
    (DESIGN 3.2: typed-v1 turned the default 0 into the LOWER bound 1); a program without a note hook keeps 0.
    Returns (values, repairs)."""
    hooks = engineer_reader.defined_hooks(source)
    values, repairs = {**engineer.OPTIONAL, 'description': 'Helper procedure.', 'hooks': hooks}, []
    for key, type_ in engineer.PROCEDURE_KEYS.items():
        if key in ('hooks', 'replay_tests', 'excluded_benches'):
            continue
        value = entry.get(key)
        if type(value) is type_:
            values[key] = value
        elif value is not None:
            repairs.append({'rule': 'schema_default', 'path': '$.' + key})
    if entry.get('hooks') != hooks:
        repairs.append({'rule': 'derived', 'path': '$.hooks', 'before': entry.get('hooks'), 'after': hooks})
    for name, cap in (('description', profiles.MAX_DESCRIPTION_CHARS), ('header', profiles.MAX_HEADER_CHARS)):
        if len(values[name]) > cap:
            values[name] = values[name][:cap]
            repairs.append({'rule': 'truncated', 'path': '$.' + name, 'cap': cap})
    if not values['description'].strip():
        values['description'] = 'Helper procedure.'
        repairs.append({'rule': 'schema_default', 'path': '$.description'})
    notes = any(h in NOTE_HOOKS for h in hooks)
    bounds = {'max_note_chars': (1, max(profiles.MAX_NOTE_CHARS.values())) if notes else (0, 0),
              'state_bytes': (1, MAX_STATE_BYTES) if 'alf_after_step' in hooks else (0, 0)}
    for key, (low, high) in bounds.items():
        before = values[key]
        values[key] = high if before < low else min(high, before)
        if values[key] != before:
            repairs.append({'rule': 'bounded_metadata', 'path': '$.' + key, 'before': before, 'after': values[key]})
    if values['requests_second_call'] and not any(h in SECOND_CALL_HOOKS for h in hooks):
        values['requests_second_call'] = False
        repairs.append({'rule': 'derived', 'path': '$.requests_second_call'})
    return values, repairs


def build_procedure(entry, source, *, bench, evidence, engineer_call, step=1, ordinal=1):
    """The policy/structure screen: a typed Procedure (origin = bench, no bench exclusions, main-v10's policy, the
    writing call in its lineage) or (None, {'check', 'detail', ...}) naming the first failing check, in this order:
    'source' (no program text), 'policy' (the unchanged frozen screen ``policy.check(source,
    version=POLICY_VERSION)``, no bench), 'hooks' (typed, addendum O7: the program defines none of the bench's note
    hooks ``engineer_prompt.NOTE_HOOKS_BY_BENCH``, so it could never write a note; rule 'no_hook_function'),
    'structure' (the frozen ``Procedure`` validation)."""
    if not isinstance(source, str) or not source.strip():
        return None, {'check': 'source', 'detail': 'no procedure source block'}
    values, repairs = _bounded_entry(entry if isinstance(entry, dict) else {}, source)
    violations = policy.check(source, version=POLICY_VERSION)
    if violations:
        return None, {'check': 'policy', 'detail': [v.to_json() for v in violations[:5]], 'repairs': repairs}
    require(bench in engineer_prompt.NOTE_HOOKS_BY_BENCH, 'A registered bench for a program')
    if not any(hook in engineer_prompt.NOTE_HOOKS_BY_BENCH[bench] for hook in values['hooks']):
        defined = 'defined: ' + (', '.join(values['hooks']) or 'none')
        return None, {'check': 'hooks', 'detail': [{'rule': 'no_hook_function', 'line': 0, 'detail': defined}],
                      'repairs': repairs}
    try:
        procedure = Procedure(id='p-%s-%d-%d' % (bench, step, ordinal), origin=bench, description=values['description'],
                              hooks=tuple(values['hooks']), source=source, evidence=evidence, header=values['header'],
                              max_note_chars=values['max_note_chars'],
                              requests_second_call=values['requests_second_call'], state_bytes=values['state_bytes'],
                              excluded_benches=(), replay_tests=(),
                              lineage={'parent': None, 'revises': None, 'engineer_call': engineer_call},
                              policy_version=POLICY_VERSION)
    except PackageInvalid as error:
        return None, {'check': 'structure', 'detail': str(error)[:MAX_DETAIL_CHARS], 'repairs': repairs}
    return procedure, None


def _reason_text(failed):
    detail = failed.get('detail')
    return failed['check'] + ': ' + (detail if isinstance(detail, str) else _json(detail))


def _step_of(parent):
    """The step a mount package label names ('typed/<chain>/s<k>'), else 1."""
    match = re.search(r'/s(\d+)$', getattr(parent, 'step', '') or '')
    return int(match.group(1)) if match else 1


def _next_id(bench, step, taken):
    ordinal = 1
    while 'p-%s-%d-%d' % (bench, step, ordinal) in taken:
        ordinal += 1
    return ordinal


def _unreadable(problem):
    """The screen reason of a reply or change that could not be read: 'unparseable: <code>: <sentence>' (``code`` one
    of ``replies.PROBLEM_CODES``, the sentence of ``replies.PROBLEM_SENTENCES``: counts and key names only)."""
    return ('unparseable: %s: %s' % (problem['code'], problem['detail']))[:MAX_DETAIL_CHARS]


def _problem_of(result):
    """The whole-reply problem of a reader result, else the first problem among its records, else None."""
    if result['problem'] is not None:
        return result['problem']
    return next((record['problem'] for record in result['records'] if record['problem'] is not None), None)


def _first_screen(failed):
    """What the first screen of a proposal found: {'passed', 'check', 'rules'}; ``rules`` are the distinct rule ids,
    in the checker's order, of the violations ``build_procedure`` reports (its first five), or the rule name of the
    check ('no_hook_function', 'structure', 'source'); the fix record's ``screen_evidence`` holds the rows shown."""
    if failed is None:
        return {'passed': True, 'check': None, 'rules': []}
    check = failed['check']
    rules = ([row['rule'] for row in failed['detail']] if check == 'policy'
             else [engineer_prompt.CHECK_WORDS[check]['rule']])
    return {'passed': False, 'check': check, 'rules': list(dict.fromkeys(rules))}


def _row(n, status, sha, *, slot=None, procedure=None, reason=None, first_screen=None, fix=None, read=None,
         format_retry=None, entry=None, source=None, kind=None, repairs=()):
    """One row of ``s<k>/programs/proposals.json`` (DESIGN 3.2, 4.1), with typed-v1's entry, source, kind and the
    reader's repair rows kept beside it (spec/engineer.md 3)."""
    require(status in PROPOSAL_STATUS, 'A registered proposal status')
    return {'n': n, 'status': status, 'slot': slot,
            'procedure': procedure.to_json() if procedure is not None else None,
            'screen': {'passed': procedure is not None, 'reason': reason}, 'first_screen': first_screen, 'fix': fix,
            'request_sha256': sha, 'read': read, 'format_retry': format_retry,
            'entry': entry, 'source': source, 'kind': kind, 'repairs': list(repairs)}


def _fix_once(entry, source, failed, *, bench, evidence, call, budget, step, ordinal):
    """The ONE fix call of a proposal that failed the screen (DESIGN 3.2). System ``engineer_system(bench, 'fix')``;
    user ``{'request': 'fix', 'bench', 'change': <the entry, no source key>, 'failed_source': <the program text>,
    'failed': engineer_prompt.screen_evidence(failed, source, bench)}``. The reply is read by ``replies.read_fix``
    through ``replies.read_with_retry`` with the unit's one ``budget`` and screened again by ``build_procedure``,
    whose lineage names the call whose reply gave the final source (the format retry's, when it was used).
    Returns (procedure | None, fix record {'request_sha256', 'parsed', 'reason', 'entry', 'source', 'repairs',
    'read', 'format_retry', 'problem', 'screen_evidence'})."""
    shown = engineer_prompt.screen_evidence(failed, source, bench)
    change = {key: value for key, value in entry.items() if key not in replies.INLINE_KEYS}
    user = {'request': 'fix', 'bench': bench, 'change': change, 'failed_source': source, 'failed': shown}
    reply, sha = _send(call, engineer_system(bench, 'fix'), _json(user))
    outcome = replies.read_with_retry(
        reply, sha, purpose='fix', bench=bench, send=lambda system, text: _send(call, system, text), budget=budget,
        read=lambda text: replies.read_fix(text, change={'entry': entry, 'source': source}))
    record = {'request_sha256': outcome['request_sha256'], 'parsed': False, 'reason': None, 'entry': None,
              'source': None, 'repairs': [], 'read': None, 'format_retry': outcome['format_retry'], 'problem': None,
              'screen_evidence': engineer_prompt.evidence_record(shown)}
    result = outcome['result']
    if result is None:
        record['reason'] = 'no_reply'
        return None, record
    found = result['records'][0] if result['records'] else None
    problem = _problem_of(result)
    if problem is not None:
        record.update(reason=_unreadable(problem), problem=problem, read=found['read'] if found else None,
                      repairs=(found or result)['repairs'])
        return None, record
    record.update(parsed=True, entry=found['entry'], source=found['source'], repairs=found['repairs'],
                  read=found['read'])
    procedure, failed_again = build_procedure(found['entry'], found['source'], bench=bench, evidence=evidence,
                                              engineer_call=outcome['request_sha256'], step=step, ordinal=ordinal)
    record['reason'] = None if procedure is not None else _reason_text(failed_again)
    return procedure, record


def propose_programs(*, bench, runtime, skill_index, examples, hook_view, parent, call,
                     max_candidates=MAX_PROGRAM_CANDIDATES, evidence, step=None, base_card=BASE_CARD_DEFAULT,
                     members=None):
    """One attempt of the programs unit (DESIGN 3.2, 3.3). ``engineer_prompt.verify()`` (once per process), then one
    proposal call (``engineer_system(bench, 'propose')``, the typed payload); the reply is read by
    ``replies.read_proposals`` through ``replies.read_with_retry`` with one ``replies.RetryBudget`` per call of this
    function, shared with every fix read. Then the promotion loop over the at most MAX_PROGRAM_PROPOSALS records, in
    the writer's order: a record with a reading problem -> 'unreadable'; a kind other than 'new' -> 'kind_not_new';
    all ``max_candidates`` slots taken -> 'not_needed' (not screened, no call); else the record takes the next id and
    is screened by ``build_procedure``: a pass -> 'passed'; a failure -> exactly one fix call (``_fix_once``) ->
    'passed_after_fix' or 'dropped_screen'. A pass takes the next slot (1, 2, ...). So a later proposal is used only
    because an earlier one was unreadable or failed the screen; smoke and gate failures never promote (the chain
    runs units for the slot rows only). Every send goes through ``call`` (the unit's recorder writes it before it
    is made), at most 1 + MAX_PROGRAM_PROPOSALS + replies.FORMAT_RETRIES_PER_UNIT = 5 per attempt.

    Rows: {'n', 'status', 'slot', 'procedure': record|None, 'screen': {'passed', 'reason'}, 'first_screen', 'fix',
    'request_sha256', 'read', 'format_retry', 'entry', 'source', 'kind', 'repairs'}; ``request_sha256`` names the
    call whose reply gave the row (the format retry's, when it was used). A proposal call without a reply gives one
    'no_reply' row; a reply that stays unreadable as a whole one 'unreadable' row (``n`` None); an explicit empty
    ``changes`` list no row. Ids are p-<bench>-<step>-<ordinal> with ``step`` from the parent's label unless given;
    every screened record takes one and none is reused, so slot 1 may hold p-<bench>-<step>-2. ``base_card``: the
    run's sealed base (addendum D17), shown in the proposal payload (``program_payload``); the fix request is
    about the static screen and does not carry it. ``members`` (a shared type, addendum D16 a): rows {'bench',
    'source', 'examples'}, shown in the proposal payload only (``program_members``)."""
    require(type(max_candidates) is int and max_candidates >= 1, 'At least one program candidate')
    _prompt_verified()
    step = _step_of(parent) if step is None else step
    budget = replies.RetryBudget()
    user = program_payload(bench=bench, runtime=runtime, skill_index=skill_index, examples=examples,
                           hook_view=hook_view, base_card=base_card, members=members)
    reply, sha = _send(call, engineer_system(bench, 'propose'), _json(user))
    if reply is None:
        return [_row(None, 'no_reply', sha, reason='no_reply')]
    outcome = replies.read_with_retry(
        reply, sha, purpose='propose', bench=bench, send=lambda system, text: _send(call, system, text),
        budget=budget, read=lambda text: replies.read_proposals(text, parent_ids=tuple(parent.order)))
    result, sha, retry = outcome['result'], outcome['request_sha256'], outcome['format_retry']
    if result['problem'] is not None:
        return [_row(None, 'unreadable', sha, reason=_unreadable(result['problem']), format_retry=retry,
                     repairs=result['repairs'])]
    records = result['records']
    require(len(records) <= MAX_PROGRAM_PROPOSALS, 'At most MAX_PROGRAM_PROPOSALS proposals per unit')
    rows, taken, slots = [], set(parent.order), 0
    for record in records:
        n, entry, source, kind = record['n'], record['entry'], record['source'], record['kind']
        kept = {'read': record['read'], 'format_retry': retry, 'entry': entry, 'source': source, 'kind': kind,
                'repairs': record['repairs']}
        if record['problem'] is not None:
            rows.append(_row(n, 'unreadable', sha, reason=_unreadable(record['problem']), **kept))
            continue
        if kind != 'new':
            rows.append(_row(n, 'kind_not_new', sha, reason='kind_not_new:' + str(kind), **kept))
            continue
        if slots >= max_candidates:
            rows.append(_row(n, 'not_needed', sha, reason='not_needed', **kept))
            continue
        ordinal = _next_id(bench, step, taken)
        taken.add('p-%s-%d-%d' % (bench, step, ordinal))
        procedure, failed = build_procedure(entry, source, bench=bench, evidence=evidence, engineer_call=sha,
                                            step=step, ordinal=ordinal)
        first, fix, reason = _first_screen(failed), None, None
        if procedure is None:
            procedure, fix = _fix_once(entry, source, failed, bench=bench, evidence=evidence, call=call,
                                       budget=budget, step=step, ordinal=ordinal)
            reason = None if procedure is not None else _reason_text(failed) + ' | fix: ' + str(fix['reason'])
        slot = None
        if procedure is not None:
            slots += 1
            slot = slots
        status = 'dropped_screen' if procedure is None else 'passed' if fix is None else 'passed_after_fix'
        rows.append(_row(n, status, sha, slot=slot, procedure=procedure, reason=reason, first_screen=first, fix=fix,
                         **kept))
    return rows


# ---- the program repair (typed-v3, CHAIN-DECISIONS T8) and the archive screen (T9) ----------------------------
# The status of a repair round's writer record: a screened revision; the same program again; a revision the static
# screen refused (no fix call: the repair ends with the last good version); a reply that stayed unreadable after its
# one format retry; no reply.
REPAIR_STATUS = ('revised', 'unchanged', 'dropped_screen', 'unreadable', 'no_reply')
COVERAGE_CLASSES = ('fired_without_note', 'not_fired')   # then 'fault:<kind>' per fault kind, sorted
REPAIR_SHOWN_ITEMS = engineer_prompt.REPAIR_SHOWN_ITEMS  # the number the repair text states
# The procedure fields that make two versions the same program (lineage and the record stamp left out: a revision's
# lineage names its own writing call, so two equal programs never have the same record hash).
PROGRAM_FIELDS = ('id', 'origin', 'description', 'hooks', 'source', 'header', 'max_note_chars', 'requests_second_call',
                  'state_bytes', 'excluded_benches', 'replay_tests', 'policy_version', 'evidence')


def repair_entry(procedure, bench):
    """The entry of a screened procedure record in the fields the engineer prompt asks for (``engineer_prompt.
    _entry_items``): the ``change`` a repair request shows and the reader inherits for an entry left out."""
    require(isinstance(procedure, dict) and isinstance(procedure.get('source'), str), 'A screened procedure record')
    entry = {'kind': 'new', 'description': procedure['description'], 'hooks': list(procedure['hooks']),
             'header': procedure['header'], 'max_note_chars': procedure['max_note_chars']}
    if bench == 'spreadsheetbench':
        entry['requests_second_call'] = procedure['requests_second_call']
    if bench == 'alfworld':
        entry['state_bytes'] = procedure['state_bytes']
    return entry


def _public_excerpt(view):
    """The public text of a learn item as a repair request shows it: the routing view's public text (what the
    describer's examples show), cut like a writer example's view (``VIEW_CHARS``)."""
    return v225_writer.truncate(tasktypes.public_text(view), VIEW_CHARS)


def _shown_tasks(item_ids, views, limit):
    return [{'task_id': item_id, 'view': _public_excerpt(views[item_id])} for item_id in item_ids[:limit]]


def coverage_report(probe, items, views, *, shown=REPAIR_SHOWN_ITEMS, exclude=()):
    """The ``coverage`` block of a repair request (T8): the probe's counts (``items``, ``routed``, ``fired``,
    ``noted``, ``faults`` by kind, ``scope``) and, per failure class among the routed items (``fired_without_note``,
    ``not_fired``, ``fault:<kind>``; an item with a fault is in its fault classes only), the class's count and up to
    ``shown`` of its items in the probe's (learn-slice) order with their public text. An item the probe lists as
    ``not_routed`` (the type map mounts the program elsewhere or nowhere) is in no class: no version can note there.
    Only the supplied learn items may appear (a probe row of any other item is refused, as ``outcomes_for_writer``
    refuses a cell of another item); no outcome, reply or reference of any item is shown (the probe made no call).
    ``exclude`` (typed-v3 B7b): ids whose text is never listed -- the step's items the provider's content filter refused
    (``chain._Run.refused_ids``); such an item still counts in its class and the class's next items fill its place."""
    by_id, hidden = _items_by_id(items), set(exclude)
    classes, unrouted = {}, set(probe.get('not_routed') or ())
    for item_id, fired, note_chars, kinds in probe['per_item']:
        require(item_id in by_id and item_id in views, 'A coverage row belongs to the supplied learn items')
        if item_id in unrouted:
            continue
        if kinds:
            names = ['fault:' + kind for kind in sorted(set(kinds))]
        elif not fired:
            names = ['not_fired']
        elif note_chars <= 0:
            names = ['fired_without_note']
        else:
            names = []
        for name in names:
            classes.setdefault(name, []).append(item_id)
    order = [name for name in COVERAGE_CLASSES if name in classes] + sorted(n for n in classes if n.startswith('fault:'))
    return {'items': probe['items'], 'routed': probe['routed'], 'fired': probe['fired'], 'noted': probe['noted'],
            'faults': dict(probe['faults']), 'scope': probe['scope'],
            'classes': [{'class': name, 'count': len(classes[name]),
                         'tasks': _shown_tasks([i for i in classes[name] if i not in hidden], views, shown)}
                        for name in order]}


def learn_report(fixed, broken, items, views, *, shown=REPAIR_SHOWN_ITEMS):
    """The ``learn`` block of the one feedback repair (T8.4): the counts of the paid learn round against the current
    arm's learn attempts (``fixed``: right only with the program; ``broken``: right only without it) and up to
    ``shown`` broken learn items (learn-slice order) with their public text and outcome labels; nothing else of any
    item (no reply, no reference)."""
    by_id = _items_by_id(items)
    require(all(item_id in by_id and item_id in views for item_id in list(fixed) + list(broken)),
            'A learn report shows learn items only')
    return {'fixed': len(fixed), 'broken': len(broken),
            'broken_tasks': [{**row, 'outcome': 'fail', 'without_program': 'pass'}
                             for row in _shown_tasks(list(broken), views, shown)]}


def _id_parts(procedure_id, bench):
    """(step, ordinal) of a learned id ``p-<bench>-<step>-<ordinal>``: a revision keeps its version's id."""
    prefix, step, ordinal = procedure_id.rsplit('-', 2)
    require(prefix == 'p-' + bench and step.isdigit() and ordinal.isdigit(), 'A learned procedure id of ' + bench)
    return int(step), int(ordinal)


def same_program(first, second):
    """Two procedure records hold the same program: equal on ``PROGRAM_FIELDS`` (lineage and stamps left out)."""
    return all(first.get(key) == second.get(key) for key in PROGRAM_FIELDS)


def repair_program(*, bench, procedure, coverage, call, evidence, learn=None):
    """One repair call of a screened program (T8.3, and T8.4 with ``learn``). ``engineer_prompt.verify()`` (once per
    process), then system ``engineer_prompt.repair_system(bench)`` and user ``{'request': 'repair', 'bench', 'change':
    <its entry, repair_entry>, 'source': <its program text>, 'coverage': <coverage_report>[, 'learn': <learn_report>]}``.
    The reply is read as a fix reply (``replies.read_fix``, the change under repair inherited for an entry left out)
    through ``replies.read_with_retry`` with ONE format retry of its own (a new ``RetryBudget``), and screened by
    ``build_procedure`` under the version's id (a revision keeps its id; its lineage names the call whose reply gave
    the source). No fix call: a revision the screen refuses is reported and ends the repair.

    Returns {'status' (``REPAIR_STATUS``), 'reason', 'request_sha256' (the call whose reply was read),
    'first_request_sha256', 'read', 'format_retry', 'problem', 'entry', 'source', 'repairs', 'screen' (the first
    screen: passed, check, rules) and 'procedure' (the revised record, only for 'revised')}."""
    require(type(bench) is str and isinstance(coverage, dict), 'A repair names its bench and its coverage report')
    _prompt_verified()
    entry, source = repair_entry(procedure, bench), procedure['source']
    step, ordinal = _id_parts(procedure['id'], bench)
    user = {'request': 'repair', 'bench': bench, 'change': entry, 'source': source, 'coverage': coverage}
    if learn is not None:
        user['learn'] = learn
    reply, sha = _send(call, engineer_prompt.repair_system(bench), _json(user))
    outcome = replies.read_with_retry(
        reply, sha, purpose='fix', bench=bench, send=lambda system, text: _send(call, system, text),
        budget=replies.RetryBudget(), read=lambda text: replies.read_fix(text, change={'entry': entry, 'source': source}))
    record = {'status': None, 'reason': None, 'request_sha256': outcome['request_sha256'], 'first_request_sha256': sha,
              'read': None, 'format_retry': outcome['format_retry'], 'problem': None, 'entry': None, 'source': None,
              'repairs': [], 'screen': None, 'procedure': None}
    result = outcome['result']
    if result is None:
        return {**record, 'status': 'no_reply', 'reason': 'no_reply'}
    found = result['records'][0] if result['records'] else None
    problem = _problem_of(result)
    if problem is not None:
        return {**record, 'status': 'unreadable', 'reason': _unreadable(problem), 'problem': problem,
                'read': found['read'] if found else None, 'repairs': (found or result)['repairs']}
    revised, failed = build_procedure(found['entry'], found['source'], bench=bench, evidence=evidence,
                                      engineer_call=outcome['request_sha256'], step=step, ordinal=ordinal)
    record.update(entry=found['entry'], source=found['source'], repairs=found['repairs'], read=found['read'],
                  screen=_first_screen(failed))
    if revised is None:
        return {**record, 'status': 'dropped_screen', 'reason': _reason_text(failed)}
    revised = revised.to_json()
    if same_program(revised, procedure):
        return {**record, 'status': 'unchanged', 'reason': 'unchanged'}
    return {**record, 'status': 'revised', 'procedure': revised}


def screen_record(record, bench):
    """The typed static screen of an ARCHIVED procedure record (T9), as ``build_procedure`` screens a new program's
    source and in its order: 'source' (no program text), 'policy' (the unchanged frozen screen ``policy.check(source,
    version=POLICY_VERSION)``, no bench) and 'hooks' (none of the bench's note hooks among the hook functions the
    source defines, addendum O7). The record is not rebuilt (nothing is fixed; its own loader verified its structure
    and hash). Returns {'passed', 'check', 'rules', 'evidence'}: ``evidence`` is the screen's evidence record
    (``engineer_prompt.evidence_record`` of ``screen_evidence``), None when it passed."""
    require(bench in engineer_prompt.NOTE_HOOKS_BY_BENCH, 'A registered bench for a program')
    source = record.get('source') if isinstance(record, dict) else None
    failed = None
    if not isinstance(source, str) or not source.strip():
        failed = {'check': 'source', 'detail': 'no procedure source block'}
    else:
        violations = policy.check(source, version=POLICY_VERSION)
        hooks = engineer_reader.defined_hooks(source) if not violations else []
        if violations:
            failed = {'check': 'policy', 'detail': [v.to_json() for v in violations[:5]]}
        elif not any(hook in engineer_prompt.NOTE_HOOKS_BY_BENCH[bench] for hook in hooks):
            failed = {'check': 'hooks', 'detail': [{'rule': 'no_hook_function', 'line': 0,
                                                    'detail': 'defined: ' + (', '.join(hooks) or 'none')}]}
    if failed is None:
        return {**_first_screen(None), 'evidence': None}
    return {**_first_screen(failed),
            'evidence': engineer_prompt.evidence_record(engineer_prompt.screen_evidence(failed, source, bench))}


# ---- the describer ---------------------------------------------------------------------------------------------
def _description_example(example):
    """A public practice excerpt with its outcome (never a reference): a plain text or a writer example."""
    if isinstance(example, str):
        return example
    require(isinstance(example, dict) and isinstance(example.get('view'), str), 'A description example is public text')
    outcome = example.get('outcome')
    prefix = '[outcome with this skill: %s]\n' % outcome if outcome in ('pass', 'fail') else ''
    return prefix + example['view']


def reply_failure(receipt):
    """Why a receipt delivered no usable reply: None when it did; 'infrastructure:<error_type>' for a transport /
    HTTP / receipt-guard failure (no verdict of the model); 'model_side:<finish or error>' for a model-side
    noncompletion (length, filtered, empty: the model did answer and the answer is unusable)."""
    if reply_of(receipt) is not None:
        return None
    if not isinstance(receipt, dict):
        return 'infrastructure:invalid_receipt'
    if receipt.get('ok') is True:
        return 'model_side:finish_' + str(receipt.get('finish_reason'))
    error_type = str(receipt.get('error_type') or 'unknown')
    return ('model_side:' if error_type in units.MODEL_SIDE_ERRORS else 'infrastructure:') + error_type


def describe(skill, examples, call):
    """The frozen index description of an accepted skill: the probe-3 prompt over exactly three practice examples,
    parsed and capped at DESCRIPTION_CHAR_CAP characters, one format retry. {'description': str|None,
    'request_sha256', 'attempts', 'infrastructure'}: ``infrastructure`` is True when no description arrived and the
    LAST attempt failed for an infrastructure reason (the chain retries or pauses: infrastructure never rejects a
    gate-accepted skill); a parsed-but-invalid or model-side failure is a description failure."""
    request = library.description_request(skill, [_description_example(example) for example in examples])
    attempts, description = [], None
    for attempt in range(1, DESCRIBE_ATTEMPTS + 1):
        user = request['user'] if attempt == 1 else request['user'] + DESCRIPTION_RETRY
        receipt = call(request['system'], user)
        reply, sha = reply_of(receipt), request_sha256(request['system'], user)
        record = {'request_sha256': sha, 'error': None, 'no_reply': None}
        try:
            if reply is None:
                record['no_reply'] = reply_failure(receipt)
                raise ValueError('no reply')
            description = library.parse_description(reply, cap=DESCRIPTION_CHAR_CAP)
        except ValueError as error:
            record['error'] = str(error)[:120]
        attempts.append(record)
        if description is not None:
            break
    infrastructure = description is None and str(attempts[-1]['no_reply'] or '').startswith('infrastructure:')
    return {'description': description, 'request_sha256': attempts[-1]['request_sha256'], 'attempts': attempts,
            'infrastructure': infrastructure}
