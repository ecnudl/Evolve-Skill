"""Child-only bounded inert-repair/audit cycle after the inherited fix and fault repair."""
from __future__ import annotations

from collections import defaultdict

from . import audit, diagnostics_feedback, engineer_v294, profiles as p

AUDIT_FIX_PARAGRAPH = (
    'Fix every confirmed finding. Do not make the program silent on every item: where the program cannot verify that '
    'every condition of an item was understood, return no note for that item only and say why in `diagnostics`.'
)


def prompt_pins():
    return {'audit_fix_paragraph': {'text': AUDIT_FIX_PARAGRAPH,
                                    'sha256': audit.text_sha256(AUDIT_FIX_PARAGRAPH)}}


def audit_fix_evidence(ctx, change, report):
    """Current, already measured run replays only; no generated view or new hook call."""
    from . import engineer
    own = engineer._verified_run_cells(ctx)
    entries, outcomes = ctx.sheet.get('audit_replays', {}).get(change.procedure.id, ([], {}))
    by_item = defaultdict(list)
    for entry in entries:
        outcome = outcomes.get(entry['cell'])
        if entry['cell'] in own and entry['bench'] == ctx.bench and outcome is not None:
            by_item[entry['item']].append(outcome)
    fired = [rows for rows in by_item.values() if any(outcome.applies for outcome in rows)]
    has_exception = lambda rows: any(not fault.get('informational')
        and str(fault.get('kind', '')).startswith('crash:') for outcome in rows for fault in outcome.faults)
    has_note = lambda rows: any(str(note.get('text', '')).strip() for outcome in rows for note in outcome.notes)
    exceptions = sum(has_exception(rows) for rows in fired)
    nonempty = sum(has_note(rows) for rows in fired)
    # As in C6c, a failed hook is an exception rather than a successful empty return.
    empty = sum(not has_note(rows) and not has_exception(rows) for rows in fired)
    result = {'notes': {'fired': len(fired), 'nonempty': nonempty, 'empty': empty, 'exceptions': exceptions}}
    diagnostics_feedback.attach(result, lambda: diagnostics_feedback.from_checks(ctx, change.procedure, report),
                                sink=ctx.sheet, stage='audit_fix_evidence')
    return result


def _audit_calls(result):
    """An audit operation contains multiple judge requests, not one engineer request hash."""
    return {judge: [request['label'] if attempt['attempt'] == 0 else
                    request['retries'][attempt['attempt'] - 1]['label']
                    for pair in result.get('requests', ()) for request in [pair['requests'][judge]]
                    if not request.get('reused')
                    for attempt in request.get('attempts', ()) if attempt.get('dispatched', True)]
            for judge in audit.JUDGES}


def repair_cycle(ctx, change, report, taken=(), *, attempts):
    """Run only v15's cycle, retaining every checked attempt in ``attempts``.

    A rejected inert reply or failed audit fix restores the previous current
    attempt's replay cache. Every accepted reply advances that cache, including
    still-inert inert repairs; subsequent audits/feedback therefore use its exact
    source. ``kept_attempt`` is the caller's global index. The legacy inert-repair
    ``kept_index`` is relative to the cycle's entering attempt and checked replies.
    Audit feedback belongs only to the source attempt that was actually audited.

    Engineer call-count refusal (``e._ask`` returning ``call is None``, including
    a refused format retry) ends the cycle with ``no_calls_left``. Token-ledger
    ``BudgetStop`` is never caught: it propagates through ``engineer_v28.run`` to
    the unit's budget pause, exactly as in v14.
    """
    from . import engineer as e, engineer_v28
    if not p.is_v216(ctx.configuration):
        raise ValueError('The bounded repair cycle belongs to zebra-pc-v15')
    current, final = report, change
    checked_indices = [next(index for index, attempt in enumerate(attempts) if attempt is current)]
    inert_record = {'causes': list(current.get('inert_causes', ())), 'calls': [],
                    'kept_index': 0, 'stop_reason': 'not_triggered'}
    cycle = {'steps': [], 'inert_repairs': 0, 'audit_fixes': 0, 'audits': 0, 'stop_reason': None}
    fields = {'inert_repair': inert_record, 'repair_cycle': cycle}
    survived = False

    def index():
        return next(n for n, attempt in enumerate(attempts) if attempt is current)

    def restore(saved):
        ctx.sheet.setdefault('audit_replays', {}).clear()
        ctx.sheet['audit_replays'].update(saved)

    def step(kind, call, *, confirmed=None):
        row = {'kind': kind, 'call': call, 'attempt_index': index(), 'became_current': False,
               'inert_after': bool(current.get('inert')), 'confirmed': confirmed}
        cycle['steps'].append(row)
        return row

    def parsed(reply, call, purpose):
        start = len(ctx.sheet.get('format_retries', ()))
        found, failures = engineer_v28.read_call(ctx, reply, call, purpose, change=final)
        denied = any(event.get('call') is None for event in ctx.sheet.get('format_retries', ())[start:])
        return (found[0] if len(found) == 1 and not failures else None), denied

    def ask(request, purpose):
        return e._ask(ctx, request, purpose)

    while True:
        if not engineer_v294._fatal_passed(current):
            cycle['stop_reason'] = 'failed_checks'
            break
        if current.get('deferred'):
            cycle['stop_reason'] = 'deferred'
            break
        if current.get('inert'):
            causes = list(current.get('inert_causes', ()))
            eligible = (engineer_v294.REPAIRABLE_CAUSES.intersection(causes)
                        and not engineer_v294.EXCLUDED_CAUSES.intersection(causes))
            if not eligible or cycle['inert_repairs'] >= p.V216_INERT_REPAIRS:
                cycle['stop_reason'] = 'inert'
                break
            if not cycle['inert_repairs']:
                inert_record['causes'] = causes
            request = {'request': 'inert_repair', 'bench': ctx.bench,
                       'change': dict(final.entry, source=final.source),
                       'evidence': current.get('inert_evidence', {}),
                       'instruction': engineer_v294.inert_repair_instruction(ctx.configuration, causes)}
            purpose = 'inert-repair/%d/%d' % (change.n, cycle['inert_repairs'] + 1)
            reply, call = ask(request, purpose)
            row = step('inert_repair', call)
            if call is None:
                cycle['stop_reason'] = inert_record['stop_reason'] = 'no_calls_left'
                break
            cycle['inert_repairs'] += 1
            event = {'call': call, 'parsed': False, 'checked': False, 'passed_fatal_checks': False,
                     'inert_after': None, 'kept': False, 'request': request}
            inert_record['calls'].append(event)
            saved = dict(ctx.sheet.get('audit_replays', {}))
            candidate, denied = parsed(reply, call, purpose)
            if denied:
                restore(saved)
                cycle['stop_reason'] = inert_record['stop_reason'] = 'no_calls_left'
                break
            if candidate is None:
                restore(saved)
                inert_record['stop_reason'] = 'unparseable'
                continue
            event.update(parsed=True, parsed_call=candidate.call)
            checked = e.check(candidate, ctx, taken)
            attempts.append(checked)
            checked_indices.append(len(attempts) - 1)
            fatal = engineer_v294._fatal_passed(checked)
            event.update(checked=True, passed_fatal_checks=fatal, inert_after=bool(checked.get('inert')),
                         deferred=bool(checked.get('deferred')))
            row.update(attempt_index=len(attempts) - 1, inert_after=bool(checked.get('inert')))
            if fatal and not checked.get('deferred'):
                final, current = candidate, checked
                event['kept'] = row['became_current'] = True
                inert_record.update(kept_index=len(checked_indices) - 1,
                                    stop_reason='still_inert' if current.get('inert') else 'fixed')
            else:
                restore(saved)
                inert_record['stop_reason'] = 'failed_checks'
            continue

        audited = audit.audit1(ctx, final, current)
        cycle['audits'] += 1
        fields.setdefault('audits', []).append(audited)
        fields.setdefault('audit_fix_calls', 0)
        step('audit', _audit_calls(audited), confirmed=bool(audited['confirmed']))
        current.setdefault('lint', {'id': final.procedure.id, 'tests': [], 'problems': []})['audit'] = audit.feedback(audited)
        if not audited['confirmed']:
            survived = True
            cycle['stop_reason'] = 'survived'
            break
        if cycle['audit_fixes'] >= p.V216_AUDIT_FIXES:
            cycle['stop_reason'] = fields['reason'] = 'audit_confirmed'
            break
        request = {'request': 'audit_fix', 'bench': ctx.bench,
                   'change': dict(final.entry, source=final.source),
                   'instruction': audit.audit_fix_prompt(final, audited) + '\n\n' + AUDIT_FIX_PARAGRAPH,
                   'evidence': audit_fix_evidence(ctx, final, current)}
        purpose = 'audit-fix/%d/%d' % (change.n, cycle['audit_fixes'] + 1)
        reply, call = ask(request, purpose)
        row = step('audit_fix', call)
        if call is None:
            cycle['stop_reason'] = 'no_calls_left'
            break
        cycle['audit_fixes'] += 1
        fields['audit_fix_calls'] += 1
        saved = dict(ctx.sheet.get('audit_replays', {}))
        candidate, denied = parsed(reply, call, purpose)
        if denied:
            restore(saved)
            cycle['stop_reason'] = 'no_calls_left'
            break
        if candidate is None:
            restore(saved)
            cycle['stop_reason'] = fields['reason'] = 'audit_fix_failed_checks'
            break
        checked = e.check(candidate, ctx, taken)
        attempts.append(checked)
        checked_indices.append(len(attempts) - 1)
        row.update(attempt_index=len(attempts) - 1, inert_after=bool(checked.get('inert')))
        if not engineer_v294._fatal_passed(checked):
            restore(saved)
            cycle['stop_reason'] = fields['reason'] = 'audit_fix_failed_checks'
            break
        final, current = candidate, checked
        row['became_current'] = True

    return final, current, survived, fields
