"""The item stage of one typed-v3 step (docs/handoff/typed-v3/CHAIN-DECISIONS.md T3 steps 1 to 5, T4, T5, T6; build
brief P2b): what runs before the gate units of bench b at step k under the sealed item stage 'planned', and the gate
list J the step's gate units then run on (``chain._Run.gate_items``). The tools are P2a's (``items``: quotas and
counts, item records and hashes, the analyst's request and plan check, the experience log, the makers and selectors);
this module only runs them as units of the chain, through the chain's own cell units, role calls and records.

Units under ``s<k>/``, in this order (each write-once and resumable; a resumed step repeats no call whose record
exists):

1. ``diagnose``: the learning base B (the base card alone, as ``noise`` mounts it) R times on the LEARN slice (labels
   ``B#1..R``, ``_Run.cells``), decidable as a gate arm is (``_Run.arm_runs``: a missing run or an infrastructure /
   configuration unknown pauses, a model-side unknown is a final 0); ``diagnose.json`` keeps the right runs per item.
2. ``items-plan``: ONE analyst call (``Services.plan_items``: ``items.plan.request_plan`` with its one format retry,
   then ``validate_plan``) on the role client, purpose ``item_analyst``, tag ``analyst``, charged by the ledger as every
   role call; its request is replayed from the calls file when its verdict was recorded (``plan.send_or_replay``
   through ``chain._keep_earlier_sends``). An infrastructure failure writes no record: one automatic retry after 60 s,
   then the pause ``analyst_unavailable``. ``analyst.json`` keeps the validated plan and its check record.
3. ``items``: the bench's maker or selector (``Services.make_items``; ``items.MAKERS``) with ``counts`` of the plan and
   the sealed quota table, the registry of the chain's items of the EARLIER steps, the unit's ``ItemStore`` (files named
   by slot) and, for the SearchQA selector, its role calls (purpose ``item_selector``, one tag per batch); a selector
   call without a verdict raises ``RoleUnavailable``: one automatic retry after 60 s, then ``selector_unavailable``.
   ``made.json`` lists every item record with its slot.
4. ``items-check``: B ONCE (label ``B``) on the judging-side attack and calibration items (``items.check_items``: holds
   iff the attack items' pass rate is at least 5 points below the calibration items'); ``check.json``. Not held and at
   least one weakness kept: ``items-plan-2`` (the first plan and the check's counts, ``plan.revision_block``),
   ``items-2`` and ``items-check-2``, never a third attempt. ``items-2`` replaces ATTACK items only (build decision B5):
   per side at most as many as round 1 made, split in turn over plan 2's kept weaknesses (fewer than 3 kept:
   min(round 1's count, the 20 % rule's attack count of ``counts``); none kept: nothing is replaced and the record says
   so); its registry also holds every round-1 item. A side is replaced when round 2 made at least one attack item
   there: round 1's attack items of that side stay on disk, listed as ``replaced`` and never used; round 1's guard and
   calibration items stay as they are (a SearchQA judging shortfall of round 2 drawn as calibration joins the
   calibration items, as the selector's rule fills a shortfall). ``items-check-2`` runs B once on round 2's judging
   items only; the calibration items of round 1 keep their check-1 outcomes. These cells are used for nothing else.
5. ``items.json`` (write-once, with its ``record_sha256``): the final lists by side and class (every entry the unit,
   slot and full item record with its hash), the replaced and unused items, the plans (weaknesses with their evidence
   counts) and the final plan's hash, both checks, the gate counts of J and the reason when no item was made.

A bench whose sealed quota row is zero (OfficeQA ``audit_bing_B36``, SpreadsheetBench ``maker_not_built``: typed's
``ITEM_ZERO_REASONS``; any other zero row ``no_quota``) or whose maker is not built (``maker_not_built``) runs none of
the units above: its ``items.json`` records the reason and the step runs with J = R exactly as typed-v2's.

Once ``items.json`` is sealed (and again when a resumed step reads it) the step's item list is held in memory
(``_Run.step_items``): J = the real gate slice, then the judging-side attack, guard and calibration items in that order
(``_Run.gate_items``); the shown items, attack first (``_Run.shown_items``). Made items that are no practice item get
their routing views (``Services.view_fn``) and embedding vectors (``tasktypes.embed_texts`` with the services'
embedder, ONE batch of the step's final made items in list order) exactly as practice items, in memory only (never
written, never handed to a writer); selected items are practice items and keep the source's. Writers see the learn
items and the shown items; no judging-side item, gate item or reference of either reaches a writer, the analyst or
the selector (the describer's examples skip them too: ``private_ids``).
"""
from __future__ import annotations

import json

from skillopt.continual_eval.core import require
from skillopt.execskill import v222_cards

from . import ITEM_ZERO_REASONS, VERSION, chain, gates, gatestats, tasktypes, units, writers
from .library import canonical_sha256

STAGE_VERSION = 'typed-v3-item-stage-1'
ITEMS_FILE = 'items.json'
# (the analyst's record is not called plan.json: that name is a gate unit's sharing plan, chain.PLAN)
DIAGNOSE_RECORD, PLAN_RECORD, MADE_RECORD, CHECK_RECORD = 'diagnose.json', 'analyst.json', 'made.json', 'check.json'
BASE_ARM = 'B'                     # chain.BASE_ARM: the learning base, the arm of diagnose and of both checks
ANALYST_TAG = 'analyst'
SELECTOR_PURPOSE = 'item_selector'   # items.select_items.SELECTOR_PURPOSE (held equal by a test)
NOT_BUILT = 'maker_not_built'      # items.registry.NOT_BUILT
NO_QUOTA = 'no_quota'
NO_ITEMS_MADE = 'no_items_made'
GATE_ORDER = ('attack', 'guard', 'calibration')   # J = R + A + G + K
SHOWN_ORDER = ('attack', 'guard')
CHECKED = ('attack', 'calibration')               # the classes the check runs B on
SIDES = ('shown', 'judging')        # items.SIDES (held equal by a test)


def _tools():
    """P2a's item tools (``items``, ``items.plan``, ``items.store``), imported at their first use: importing this
    module loads no typed subpackage (the bound driver imports every top-level typed module and counts what loads)."""
    from . import items
    from .items import plan, store
    return items, plan, store


def _unit(k, name, n=1):
    return 's%d/%s%s' % (k, name, '' if n == 1 else '-%d' % n)


def _maker(bench):
    items_, plan_, store_ = _tools()
    return items_.MAKERS[bench]


def _ids(rows):
    return [row['task_id'] for row in rows]


def _json_sha256(value):
    return units.sha256_text(json.dumps(value, ensure_ascii=False, sort_keys=True))


# ---- the real services' defaults ----------------------------------------------------------------------------------
def plan_items(*, call, payload, learn_outcomes, repeats, sheet):
    """``Services.plan_items`` of the real services: ``items.plan.request_plan`` (one request, one format retry, a
    recorded verdict replayed) and, unless it ended for an infrastructure reason, ``validate_plan`` (T4's rules).
    Returns {'call': the request record, 'plan': the plan or None, 'validation': its check record or None}."""
    items_, plan_, store_ = _tools()
    found = plan_.request_plan(call, payload)
    if found['status'] == 'infrastructure':
        return {'call': found, 'plan': None, 'validation': None}
    plan, validation = plan_.validate_plan(found['raw'], learn_outcomes, repeats, sheet)
    return {'call': found, 'plan': plan, 'validation': validation}


def make_items(inp):
    """``Services.make_items`` of the real services: the registry's maker of the bench (``items.MAKERS``)."""
    return _maker(inp.bench).make(inp)


def skip_reason(bench, quotas):
    """Why a step makes no item, known before any call, or None: the bench's sealed quota row is zero (the reason of
    ``ITEM_ZERO_REASONS``, else ``no_quota``) or its maker is not built (``maker_not_built``)."""
    items_, plan_, store_ = _tools()
    if items_.quota_row(bench, quotas) is None:
        return ITEM_ZERO_REASONS.get(bench, NO_QUOTA)
    if not _maker(bench).built:
        return NOT_BUILT
    return None


# ---- the stage ----------------------------------------------------------------------------------------------------
def stage(run, k, bench):
    """The item stage of step k on ``bench`` (``run`` is the chain's ``_Run``): the sealed ``s<k>/items.json``, read
    when it exists (a resumed step), else built unit by unit (module text); then the step's item list in memory
    (``_activate``). Returns the sealed record."""
    path = run.root / ('s%d' % k) / ITEMS_FILE
    record = _read_sealed(path, run.s.chain, k, bench) if path.exists() else _build(run, k, bench, path)
    _activate(run, k, bench, record)
    return record


def _build(run, k, bench, path):
    items_, plan_, store_ = _tools()
    quotas = run.item_quotas
    reason = skip_reason(bench, quotas)
    if reason is not None:
        return _seal(path, _fields(run, k, bench, reason=reason))
    R, learn, gate = run.repeats(), run.items(bench, 'learn'), run.items(bench, 'gate')
    diagnosis = _diagnose(run, k, bench, learn, R)
    sheet = _maker(bench).capability_sheet(pool=run.s.items[bench], learn_ids=_ids(learn), gate_ids=_ids(gate))
    earlier = _earlier_records(run, k)
    plan_1 = _plan_round(run, k, bench, 1, diagnosis, sheet)
    counts_1 = items_.counts(bench, [w['id'] for w in plan_1['plan']['weaknesses']], quotas)
    made_1 = _make_round(run, k, bench, 1, diagnosis, plan_1['plan'], counts_1, earlier)
    judging_1 = [entry for entry in made_1['entries'] if entry['record']['side'] == 'judging']
    checked_1 = [entry for entry in judging_1 if entry['record']['class'] in CHECKED]
    check_1 = _check_round(run, k, bench, 1, [entry['record'] for entry in checked_1], checked_1, {})
    second = None
    if not check_1['holds'] and plan_1['plan']['weaknesses']:
        second = _second_round(run, k, bench, diagnosis, sheet, plan_1, made_1, check_1, quotas, earlier)
    return _seal(path, _fields(run, k, bench, plans=[plan_1] + ([second['plan']] if second else []),
                               counts=[counts_1, second['counts'] if second else None], made=[made_1, second and second['made']],
                               checks=[check_1, second['check'] if second else None], second=second))


def _second_round(run, k, bench, diagnosis, sheet, plan_1, made_1, check_1, quotas, earlier):
    """``items-plan-2``, ``items-2`` and ``items-check-2`` (module text, item 4)."""
    items_, plan_, store_ = _tools()
    plan_2 = _plan_round(run, k, bench, 2, diagnosis, sheet, revision=plan_.revision_block(plan_1['plan'], check_1))
    counts_2 = replacement_counts(bench, plan_2['plan'], [entry['record'] for entry in made_1['entries']], quotas)
    out = {'plan': plan_2, 'counts': counts_2, 'made': None, 'check': None, 'sides': [], 'reason': None}
    if counts_2 is None:
        out['reason'] = 'plan_2_kept_no_weakness'
        return out
    made_2 = _make_round(run, k, bench, 2, diagnosis, plan_2['plan'], counts_2,
                         earlier + [entry['record'] for entry in made_1['entries']])
    out['made'] = made_2
    out['sides'] = [side for side in SIDES if any(entry['record']['side'] == side and entry['record']['class'] == 'attack'
                                                  for entry in made_2['entries'])]
    if not out['sides']:
        out['reason'] = 'round_2_made_no_attack_item'
        return out
    if 'judging' not in out['sides']:
        out['reason'] = 'judging_side_not_replaced'
        return out
    lists = compose_lists(made_1['entries'], made_2['entries'], out['sides'])
    checked = [entry for cls in CHECKED for entry in lists['judging'][cls]]
    fresh = [entry for entry in checked if entry['unit'] == made_2['unit']]
    kept = {entry['record']['item'] for entry in checked if entry['unit'] == made_1['unit']}
    reused = {item: outcome for item, outcome in check_1['outcomes'] if item in kept}
    out['check'] = _check_round(run, k, bench, 2, [entry['record'] for entry in checked], fresh, reused)
    return out


def replacement_counts(bench, plan, round_1_records, quotas):
    """The counts record of ``items-2`` (build decision B5): attack items only, per side n = the number of attack items
    round 1 made there when plan 2 keeps at least ``MIN_KEPT_WEAKNESSES`` weaknesses, else min(that number, the 20 %
    rule's attack count of ``items.counts`` for plan 2's weaknesses), split in turn over plan 2's kept weaknesses
    (``items.split_in_turn``); None when plan 2 keeps none (nothing is replaced)."""
    items_, plan_, store_ = _tools()
    ids = [weakness['id'] for weakness in plan['weaknesses']]
    if not ids:
        return None
    full = items_.counts(bench, ids, quotas)
    made = {side: sum(1 for record in round_1_records if record['side'] == side and record['class'] == 'attack')
            for side in SIDES}
    n = {side: made[side] if len(ids) >= items_.MIN_KEPT_WEAKNESSES else min(made[side], full[side]['attack'])
         for side in SIDES}
    found = {'bench': bench, 'weaknesses': len(ids), 'weakness_ids': ids, 'rule': 'replacement',
             'round_1_attack': made, 'judging': {'attack': n['judging'], 'guard': 0, 'calibration': 0},
             'shown': {'attack': n['shown'], 'guard': 0},
             'attack_split': {side: [[w, c] for w, c in zip(ids, items_.split_in_turn(n[side], len(ids)))]
                              for side in SIDES},
             'totals': dict(n)}
    return items_.check_counts(found)


def compose_lists(round_1, round_2, sides):
    """The final lists of a step from the entries of its rounds (``made.json``): {'shown': {attack, guard}, 'judging':
    {attack, guard, calibration}, 'replaced', 'unused'}, each list in the rounds' listing order. On a side round 2
    replaced (``sides``), its attack items replace round 1's (listed as ``replaced``) and its other items (a SearchQA
    judging shortfall drawn as calibration) follow round 1's of their class; on any other side round 1's items stay
    and round 2's are ``unused``."""
    def pick(entries, side, cls):
        return [entry for entry in entries if entry['record']['side'] == side and entry['record']['class'] == cls]
    out = {'shown': {}, 'judging': {}, 'replaced': [], 'unused': []}
    for side in SIDES:
        for cls in (GATE_ORDER if side == 'judging' else SHOWN_ORDER):
            first, second = pick(round_1, side, cls), pick(round_2, side, cls)
            if side not in sides:
                out[side][cls] = first
                out['unused'] += second
            elif cls == 'attack':
                out[side][cls] = second
                out['replaced'] += first
            else:
                out[side][cls] = first + second
    return out


# ---- the units ----------------------------------------------------------------------------------------------------
def _diagnose(run, k, bench, learn, R):
    """Unit 1: B R times on the learn slice; {'unit', 'runs': {id: [R cells, run 1 first]}, 'outcomes', 'repeats'}."""
    items_, plan_, store_ = _tools()
    unit, labels, ids = _unit(k, 'diagnose'), gates.repeat_labels(BASE_ARM, R), _ids(learn)
    cells = run.cells(unit, bench, [(bench, item, labels) for item in learn])
    run.arm_runs(unit, cells, {'items': ids, 'arm': BASE_ARM, 'repeats': R})  # decidable, else a pause
    runs = {item_id: [cells[(item_id, label)] for label in labels] for item_id in ids}
    outcomes = plan_.outcomes_of(runs, R)
    right = [[item_id, sum(value is True for value in outcomes[item_id])] for item_id in ids]
    run.record(unit, DIAGNOSE_RECORD, lambda: {
        'version': STAGE_VERSION, 'unit': unit, 'bench': bench, 'step': k, 'arm': BASE_ARM, 'labels': list(labels),
        'repeats': R, 'items': len(ids), 'right_runs': right,
        'by_right_runs': [[r, sum(1 for _, found in right if found == r)] for r in range(R + 1)]})
    return {'unit': unit, 'runs': runs, 'outcomes': outcomes, 'repeats': R}


def _plan_round(run, k, bench, n, diagnosis, sheet, *, revision=None):
    """Unit 2 (``items-plan``) or ``items-plan-2`` (``revision``): the write-once ``analyst.json``."""
    items_, plan_, store_ = _tools()
    unit, R = _unit(k, 'items-plan', n), diagnosis['repeats']
    run.current(unit)

    def compute():
        learn, views = run.items(bench, 'learn'), run.views_of(bench)
        rows = plan_.learn_rows(bench, learn, diagnosis['runs'], R, view_of=lambda item: views[item['task_id']],
                                kind_of=_maker(bench).public_kind)
        experience = experience_of(run, k)
        payload, dropped = plan_.analyst_payload(
            bench=bench, task_card=writers.task_card(bench, run.s.runtime), learn=rows, repeats=R,
            experience=experience, capability_sheet=sheet, format_block=v222_cards.format_text(bench),
            revision=revision)
        found = _ask_analyst(run, unit, payload, diagnosis['outcomes'], R, sheet)
        call, plan = found['call'], found['plan']
        require(isinstance(plan, dict) and isinstance(found.get('validation'), dict),
                'The analyst of %s returned a validated plan' % unit)
        return {'version': STAGE_VERSION, 'unit': unit, 'bench': bench, 'step': k, 'round': n, 'status': call['status'],
                'request_sha256': call['request_sha256'],
                'attempts': [{key: attempt.get(key) for key in ('request_sha256', 'failure', 'readable')}
                             for attempt in call['attempts']],
                'payload_sha256': _json_sha256(payload), 'dropped': dropped, 'sheet_sha256': canonical_sha256(sheet),
                'experience_steps': len(experience), 'revision': revision is not None, 'plan': plan,
                'plan_sha256': canonical_sha256(plan), 'validation': found['validation']}
    record = run.record(unit, PLAN_RECORD, compute)
    run.mark(unit)
    return record


def _ask_analyst(run, unit, payload, outcomes, R, sheet):
    """The analyst call of one round (``Services.plan_items``): a verdict returns; an infrastructure failure is
    retried once after 60 s (``state['infra_retries']``), then pauses ``analyst_unavailable`` (no record written)."""
    items_, plan_, store_ = _tools()
    ask = run.s.plan_items or plan_items
    key = unit + '/' + ANALYST_TAG
    for attempt in (1, 2):
        call = chain._keep_earlier_sends(run.s.role_call(plan_.ANALYST_PURPOSE, unit, ANALYST_TAG, chain.WRITER_TOKENS))
        found = ask(call=call, payload=payload, learn_outcomes=outcomes, repeats=R, sheet=sheet)
        require(isinstance(found, dict) and isinstance(found.get('call'), dict), 'An analyst result with its call')
        if found['call'].get('status') != 'infrastructure':
            return found
        if attempt == 1 and not run.state['infra_retries'].get(key):
            run.state['infra_retries'][key] = {'at': chain._now(), 'seconds': chain.RETRY_SECONDS}
            run.persist()
            run.sleep(chain.RETRY_SECONDS)
            continue
        raise chain.Paused('analyst_unavailable', unit, 'infrastructure')


def _make_round(run, k, bench, n, diagnosis, plan, counts, registry_records):
    """Unit 3 (``items``) or ``items-2``: the maker on the unit's store; the write-once ``made.json`` with every item
    record and its slot (``entries``)."""
    items_, plan_, store_ = _tools()
    unit = _unit(k, 'items', n)
    path = run.root / unit / MADE_RECORD
    if path.exists():
        found = units.read_json(path)
        run.mark(unit)
        return found
    run.current(unit)
    make = run.s.make_items or make_items
    language = None
    if bench == 'zebralogic' and n > 1:  # P2a: round 2 makes its puzzles in round 1's language
        first = store_.ItemStore(run.root / _unit(k, 'items'))
        language = first.read('zebralogic', 'language.json') if first.exists('zebralogic', 'language.json') else None
    learn_ids, gate_ids = _ids(run.items(bench, 'learn')), _ids(run.items(bench, 'gate'))
    key = unit + '/selector'
    for attempt in (1, 2):
        inp = items_.MakeInput(
            bench=bench, plan=plan, counts=counts, pool=list(run.s.items[bench]),
            pool_pin=chain._pool_pin(run.s.manifest, bench), learn_ids=learn_ids, gate_ids=gate_ids,
            outcomes=diagnosis['outcomes'], repeats=diagnosis['repeats'],
            identity={'version': VERSION, 'chain': run.s.chain, 'step': k, 'round': n},
            registry=store_.RunRegistry(registry_records), store=store_.ItemStore(run.root / unit),
            role_call=lambda tag: chain._keep_earlier_sends(run.s.role_call(SELECTOR_PURPOSE, unit, tag,
                                                                            chain.WRITER_TOKENS)),
            view_of=lambda item: run.s.view_fn(bench, item), language=language)
        try:
            result = make(inp)
            break
        except items_.RoleUnavailable as error:
            if attempt == 1 and not run.state['infra_retries'].get(key):
                run.state['infra_retries'][key] = {'at': chain._now(), 'seconds': chain.RETRY_SECONDS}
                run.persist()
                run.sleep(chain.RETRY_SECONDS)
                continue
            raise chain.Paused('selector_unavailable', unit, str(error.tag)[:32]) from None
    slot_of = {row['item']: row['slot'] for row in result['slots'] if row.get('item')}
    entries = [{'unit': unit, 'slot': slot_of[record['item']], 'record': items_.check_record(record)}
               for record in result['records']]
    found = {'version': STAGE_VERSION, 'unit': unit, 'bench': bench, 'step': k, 'round': n, 'status': result['status'],
             'reason': result['reason'], 'counts': counts, 'plan_sha256': canonical_sha256(plan),
             'registry_records': len(registry_records), 'entries': entries, 'shortfalls': result['shortfalls'],
             'made_counts': result['made_counts'], 'slots': result['slots']}
    units.write_json(path, found)
    run.mark(unit)
    return found


def _check_round(run, k, bench, n, judged, fresh, reused):
    """Unit 4 (``items-check``) or ``items-check-2``: B once on the items of ``fresh`` (entries), the outcomes of
    ``reused`` ({item: outcome} of check 1) for the others; ``items.check_items`` on the judged attack and
    calibration records; the write-once ``check.json`` with the per-item outcomes (checks only)."""
    items_, plan_, store_ = _tools()
    unit = _unit(k, 'items-check', n)
    path = run.root / unit / CHECK_RECORD
    if path.exists():
        found = units.read_json(path)
        run.mark(unit)
        return found
    run.current(unit)
    loaded = [_item_of(bench, run.root, entry) for entry in fresh]
    _register_views(run, bench, loaded)
    cells = run.cells(unit, bench, [(bench, item, (BASE_ARM,)) for item in loaded]) if loaded else {}
    ids = _ids(loaded)
    unknown = sum(1 for item_id in ids if _undecided(cells.get((item_id, BASE_ARM))))
    if unknown:  # an infrastructure or configuration unknown decides nothing (as a gate arm)
        units.archive_done(run.root / unit)
        raise chain.Paused('gate_cells_unknown', unit, '%d of %d runs infrastructure or configuration unknown'
                           % (unknown, len(ids)))
    outcomes = {**reused, **{item_id: cells[(item_id, BASE_ARM)]['correct'] for item_id in ids}}
    checked = items_.check_items(judged, outcomes)
    found = {'version': STAGE_VERSION, 'unit': unit, 'bench': bench, 'step': k, 'round': n, 'arm': BASE_ARM,
             'cells': len(ids), 'reused': len(reused),
             'outcomes': [[record['item'], outcomes[record['item']]] for record in judged], **checked}
    units.write_json(path, found)
    run.mark(unit)
    return found


def _undecided(row):
    return row is not None and row.get('correct') is None and bool(row.get('infrastructure_unknown')
                                                                   or row.get('configuration_error'))


# ---- items.json ---------------------------------------------------------------------------------------------------
def _plan_summary(record):
    plan = record['plan']
    return {'unit': record['unit'], 'round': record['round'], 'status': record['status'],
            'unreadable': bool(plan.get('unreadable')), 'kept': len(plan['weaknesses']),
            'rule': record['validation'].get('rule_applied'),
            'weaknesses': [{'id': w['id'], 'given_id': w.get('given_id'), 'description': w['description'],
                            'evidence': len(w['evidence'])} for w in plan['weaknesses']],
            'guards': len(plan['guards']), 'plan_sha256': record['plan_sha256']}


def _fields(run, k, bench, *, reason=None, plans=(), counts=(), made=(), checks=(), second=None):
    """The fields of ``items.json`` (module text, item 5)."""
    items_, plan_, store_ = _tools()
    real = _ids(run.items(bench, 'gate'))
    rounds = [found for found in made if found]
    replaced = list(second['sides']) if second else []
    lists = compose_lists(rounds[0]['entries'] if rounds else [], rounds[1]['entries'] if len(rounds) > 1 else [],
                          replaced)
    final_round = (2 if 'judging' in replaced else 1) if plans else None
    made_any = any(lists[side][cls] for side in ('shown', 'judging') for cls in lists[side])
    if reason is None and not made_any:
        reason = rounds[0]['reason'] if rounds and rounds[0]['reason'] else NO_ITEMS_MADE
    gate = {'real': len(real), **{cls: len(lists['judging'][cls]) for cls in GATE_ORDER}}
    gate['total'] = sum(gate.values())
    return {'version': STAGE_VERSION, 'chain': run.s.chain, 'step': k, 'bench': bench, 'item_stage': 'planned',
            'reason': reason, 'quota': items_.quota_row(bench, run.item_quotas),
            'plans': [_plan_summary(record) for record in plans], 'final_round': final_round,
            'plan_sha256': plans[final_round - 1]['plan_sha256'] if final_round else None,
            'counts': [found for found in counts if found is not None],
            'made': [{key: found[key] for key in ('unit', 'status', 'reason', 'made_counts', 'shortfalls')}
                     for found in rounds],
            'checks': [found for found in checks if found is not None],
            'replacement': None if second is None else {
                'sides': replaced, 'reason': second['reason'],
                'plan_unit': second['plan']['unit'], 'counts': second['counts'] is not None},
            'lists': lists, 'gate': gate}


def _seal(path, fields):
    record = chain._sealed(fields)
    units.write_json(path, record)
    return record


def _read_sealed(path, chain_name, k, bench=None):
    """A sealed ``items.json``: its own hash, this version, chain and step, and (when given) bench."""
    record = units.read_json(path)
    require(isinstance(record, dict) and isinstance(record.get('record_sha256'), str), 'A sealed items.json')
    body = {key: value for key, value in record.items() if key != 'record_sha256'}
    require(canonical_sha256(body) == record['record_sha256'], 'The items.json of s%d is the one sealed' % k)
    require(record.get('version') == STAGE_VERSION and record.get('chain') == chain_name and record.get('step') == k
            and (bench is None or record.get('bench') == bench),
            'The items.json of s%d belongs to this chain, step and bench' % k)
    return record


def sealed_of(run, j):
    """The verified ``items.json`` of an earlier step j of this chain (every step of a planned run seals one)."""
    path = run.root / ('s%d' % j) / ITEMS_FILE
    require(path.exists(), 'Every earlier step of a planned item stage sealed its items.json (s%d)' % j)
    return _read_sealed(path, run.s.chain, j)


def entries_of(record):
    """Every item entry of a sealed ``items.json``: the final lists, then the replaced and unused items."""
    lists = record['lists']
    return ([entry for side, order in (('shown', SHOWN_ORDER), ('judging', GATE_ORDER)) for cls in order
             for entry in lists[side][cls]] + list(lists['replaced']) + list(lists['unused']))


def _earlier_records(run, k):
    """The item records of this chain's earlier steps (every list of their ``items.json``, replaced and unused
    items included): the registry of the maker of step k (an item is made or selected once in a run)."""
    out = []
    for j in range(1, k):
        out += [entry['record'] for entry in entries_of(sealed_of(run, j))]
    return out


# ---- the step's item list in memory -------------------------------------------------------------------------------
def _item_of(bench, root, entry):
    """The item of an entry, read from its unit's store (``items/<slot>.json``) and verified against its record."""
    items_, plan_, store_ = _tools()
    item = store_.ItemStore(root / entry['unit']).item(entry['slot'])
    require(isinstance(item, dict) and item.get('task_id') == entry['record']['item']
            and items_.item_sha256(bench, item) == entry['record']['item_sha256'],
            'The item of %s/%s is the one its record names' % (entry['unit'], entry['slot']))
    return item


def _register_views(run, bench, loaded):
    """Routing views (``Services.view_fn``) of items that are no practice item, in memory, for the check's cells."""
    views = run.views_of(bench)
    for item in loaded:
        if item['task_id'] not in views:
            views[item['task_id']] = run.s.view_fn(bench, item)


def _register(run, bench, loaded):
    """Routing views and embedding vectors of the step's final made items that are no practice item, exactly as
    practice items get theirs (``view_fn``, ``tasktypes.public_text``, ``tasktypes.embed_texts`` with the services'
    embedder), in ONE batch in list order, in memory only."""
    vectors, views = run.vectors_of(bench), run.views_of(bench)
    new = [item for item in loaded if item['task_id'] not in vectors]
    if not new:
        return
    found = [run.s.view_fn(bench, item) for item in new]
    embedded = tasktypes.embed_texts([tasktypes.public_text(view) for view in found], embedder=run.s.embed)
    for item, view, vector in zip(new, found, embedded):
        views[item['task_id']], vectors[item['task_id']] = view, vector


def _activate(run, k, bench, record):
    """``run.step_items`` of the sealed record: the judging items of J in its order, the shown items by class, the
    class map of J (real, attack, guard, calibration) and the private ids (every judging-side item of the step)."""
    lists = record['lists']
    judging = [_item_of(bench, run.root, entry) for cls in GATE_ORDER for entry in lists['judging'][cls]]
    shown = [[_item_of(bench, run.root, entry) for entry in lists['shown'][cls]] for cls in SHOWN_ORDER]
    _register(run, bench, judging + [item for group in shown for item in group])
    real = _ids(run.items(bench, 'gate'))
    classes = {item_id: 'real' for item_id in real}
    for cls in GATE_ORDER:
        for entry in lists['judging'][cls]:
            require(entry['record']['item'] not in classes, 'An item is once in the gate list J')
            classes[entry['record']['item']] = cls
    private = set(real) | {entry['record']['item'] for entry in entries_of(record)
                           if entry['record']['side'] == 'judging'}
    run.step_items = {'step': k, 'bench': bench, 'judging': judging, 'shown': shown, 'classes': classes,
                      'private': private, 'record': record}


def private_ids(run, bench):
    """The ids no role call may see of ``bench`` in the current step: its real gate slice and, once its items are
    sealed, every judging-side item of the step (the final lists, the replaced and the unused ones)."""
    found = run.own_items(bench)
    return set(_ids(run.items(bench, 'gate'))) | (found['private'] if found is not None else set())


def gate_classes(run, bench):
    """The class map of J ({item: real | attack | guard | calibration}) of the current step's bench (the real slice
    alone before the seal or for another bench)."""
    found = run.own_items(bench)
    return dict(found['classes']) if found is not None else {item_id: 'real' for item_id in
                                                              _ids(run.items(bench, 'gate'))}


# ---- the experience log (T4) ------------------------------------------------------------------------------------------
def experience_of(run, k):
    """The analyst's experience log of step k (``items.plan.experience_log``) from THIS chain's earlier steps: their
    ``decisions.json`` (every card and program row: kind, accepted or the reason, gain and n) and ``items.json`` (the
    final plan's kept weaknesses and, for every accepted candidate, its gain on each weakness's judging attack items
    from the row's own ``per_item``). Counts and descriptions only."""
    items_, plan_, store_ = _tools()
    steps = []
    for j in range(1, k):
        step_dir = run.root / ('s%d' % j)
        decisions, sealed = units.read_json(step_dir / 'decisions.json'), sealed_of(run, j)
        candidates = plan_.candidates_of_decisions(decisions)
        rows = list(decisions.get('cards') or []) + list(decisions.get('programs') or [])
        require(len(rows) == len(candidates), 'One candidate per decision row')
        weakness_of = {entry['record']['item']: entry['record']['weakness']
                       for entry in sealed['lists']['judging']['attack'] if entry['record']['weakness']}
        for candidate, row in zip(candidates, rows):
            if candidate['accepted'] and weakness_of and isinstance(row.get('per_item'), list):
                candidate['attack'] = attack_gains(row, weakness_of)
        final = sealed['plans'][sealed['final_round'] - 1] if sealed.get('final_round') else None
        steps.append({'step': j, 'bench': decisions['bench'], 'candidates': candidates,
                      'weaknesses': [{'id': w['id'], 'description': w['description']}
                                     for w in (final or {}).get('weaknesses', [])]})
    return plan_.experience_log(steps)


def attack_gains(row, weakness_of):
    """{weakness: {'n', 'gain_points'}} of one decision row over the judging attack items of each weakness
    (gain = 100 D / (R n), D the difference of the run sums on those items, as ``gatestats.class_gains``)."""
    R, found = row['repeats'], {}
    for item_id, baseline, candidate in row['per_item']:
        weakness = weakness_of.get(item_id)
        if weakness:
            n, D = found.get(weakness, (0, 0))
            found[weakness] = (n + 1, D + candidate - baseline)
    return {w: {'n': n, 'gain_points': 100 * D / (R * n)}
            for w, (n, D) in sorted(found.items(), key=lambda pair: int(pair[0][1:]))}


# ---- decisions.json ---------------------------------------------------------------------------------------------------
def add_to_decisions(run, k, bench, decisions):
    """typed-v3 (brief P2b) additions to a step's ``decisions.json`` under 'planned': the block ``items`` (counts by
    side and class, the plans' weaknesses with their evidence counts, both checks, the replacement, the gate counts of
    J and the reason when no item was made) and on every card, program and no-harm row ``by_class``
    (``gatestats.class_gains`` over J with the step's class map; informational, it decides nothing here). A row that
    never reached a gate (no ``per_item``) gets ``by_class`` None. The stored unit records are not changed."""
    found = run.own_items(bench)
    require(found is not None, 'A planned step finalizes with its sealed item list')
    record, classes = found['record'], found['classes']
    lists = record['lists']
    decisions['items'] = {
        'reason': record['reason'], 'items_sha256': record['record_sha256'], 'quota': record['quota'],
        'counts': {'shown': {cls: len(lists['shown'][cls]) for cls in SHOWN_ORDER},
                   'judging': {cls: len(lists['judging'][cls]) for cls in GATE_ORDER},
                   'replaced': len(lists['replaced']), 'unused': len(lists['unused'])},
        'gate': dict(record['gate']), 'plans': record['plans'], 'final_round': record['final_round'],
        'plan_sha256': record['plan_sha256'],
        'checks': [{key: value for key, value in check.items() if key != 'outcomes'} for check in record['checks']],
        'replacement': record['replacement'], 'made': record['made']}
    decisions['cards'] = [with_classes(row, classes) for row in decisions['cards']]
    decisions['programs'] = [with_classes(row, classes) for row in decisions['programs']]
    typing = decisions['typing']
    decisions['typing'] = {**typing, 'no_harm': [with_classes(row, classes) for row in typing['no_harm']]}
    return decisions


def with_classes(row, classes):
    """A decision row with ``by_class``: ``gatestats.class_gains`` of its ``per_item`` (which must be over J) with the
    class map, R from the row; None for a row without a gate."""
    per_item = row.get('per_item')
    if not isinstance(per_item, list) or not per_item:
        return {**row, 'by_class': None}
    ids = [item[0] for item in per_item]
    require(set(ids) == set(classes) and len(ids) == len(classes), 'A decision row of the step is over its list J')
    return {**row, 'by_class': gatestats.class_gains(per_item, classes, row['repeats'])}
