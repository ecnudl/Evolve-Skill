"""Opt-in v2.9.1 fault repair; prior engineer prompts and records stay frozen."""
from __future__ import annotations

from . import audit, engineer_v29, notes, profiles as p

ALF_STATE_RULE = ('`state` is None at step 0 and stays None until your `alf_after_step` returns a value. '
                  'The first fault of a procedure (exception, timeout, note over a cap, oversized state) '
                  'disables it for the rest of that episode.')
FAULT_RULE = ('Faults (exceptions, timeouts, notes over `max_note_chars` or the bench cap, oversized state) '
              "suppress that item's notes. They are reported back with exception type, message, source line "
              'and an example input; a change that faults on at least 10% of the items where it fires gets '
              'up to 2 fault-repair calls.')
FAULT_REPAIR_INSTRUCTION = ('Fix these faults so the procedure runs without raising and its notes fit the caps; '
                            'keep its intended behaviour; return the corrected change in the usual format.')


def note_caps_rule(configuration):
    """Generate the runtime's field and rendered-note limits without copied numbers."""
    fields = notes.FIELD_TYPES
    facts, warnings = fields['facts']['max_chars'], fields['warnings']['max_chars']
    listed = ('facts/warnings items ≤ %d characters each' % facts if facts == warnings else
              'facts items ≤ %d characters each, warnings items ≤ %d characters each' % (facts, warnings))
    table, bindings = fields['table'], fields['bindings']
    bench = p.active_benches(configuration)[0]
    label, unit = ('ALFWorld', 'step') if p.is_alfworld(configuration) else ('ZebraLogic', 'request')
    return ('Note caps: %s, candidates ≤ %d characters each, table ≤ %d rows × %d columns with cells ≤ %d '
            'characters, bindings %s ≤ %d characters each; a field over its cap is dropped whole and counts '
            'as a fault; rendered notes must also fit `max_note_chars` and the %s bench cap of %s characters '
            'per %s.' % (listed, fields['candidates']['max_chars'], table['max_rows'], table['max_columns'],
                        table['max_chars'], '/'.join(bindings['keys']), bindings['max_chars'], label,
                        format(p.MAX_NOTE_CHARS[bench], ','), unit))


def system(configuration, *, train):
    text = engineer_v29.system(configuration, train=train).replace('(v2.9)', '(v2.9.1)')
    if train:
        text = text.replace('patience %d;' % p.TRAIN_PATIENCE,
                            'patience %d;' % p.train_patience(configuration))
    else:
        text += 'Training, when used, has patience %d over at most %d rounds.\n' % (
            p.train_patience(configuration), p.TRAIN_ROUNDS)
    return (text + (ALF_STATE_RULE + '\n' if p.is_alfworld(configuration) else '') + FAULT_RULE + '\n'
            + note_caps_rule(configuration) + '\n')


def prompt_pins():
    values = {configuration + '/' + mode: system(configuration, train=mode == 'train')
              for configuration in ('zebra-pc-v8', 'alfworld-v5') for mode in ('single', 'train')}
    values.update({configuration + '/note_caps': note_caps_rule(configuration)
                   for configuration in ('zebra-pc-v8', 'alfworld-v5')})
    values.update(fix=engineer_v29.FIX_SYSTEM, format_retry=engineer_v29.FORMAT_RETRY_SYSTEM,
                  audit_fix=engineer_v29.AUDIT_FIX_SYSTEM, fault_repair=FAULT_REPAIR_INSTRUCTION)
    return {key: {'text': value, 'sha256': audit.text_sha256(value)} for key, value in values.items()}


def _read_once(ctx, reply, call, change):
    """S3c must make exactly one engineer request, even for an unusable reply."""
    from . import engineer as e, engineer_reader as reader
    try:
        results = reader.read(reply, ctx, fix_change=change)
    except reader.Unusable:
        return None
    if len(results) != 1 or results[0]['error']:
        return None
    row = results[0]
    return e.Change(change.n, row['entry']['kind'], row['entry'], row['source'], call,
                    repairs=list(change.repairs or ()) + row['repairs'])


def _evidence(ctx, procedure, report):
    from . import fault_feedback
    result = fault_feedback.summarize(procedure, report, configuration=ctx.configuration,
        **({'bench': ctx.bench} if p.is_v214(ctx.configuration) else {}))
    if p.is_v215(ctx.configuration):
        from . import diagnostics_feedback
        example = result.get('example_call')
        diagnostics_feedback.attach(result, lambda: diagnostics_feedback.from_checks(
            ctx, procedure, report, only_faulted=True,
            examples=[example['task_id']] if example else ()), sink=ctx.sheet, stage='fault_evidence')
    return result


def repair(ctx, change, report, taken=(), *, max_repairs=None, format_retry=True):
    """Return the best change/report, every checked repair, and its repair record.

    The original is index zero. A repair is kept only if fatal checks pass, it is
    not deferred, and its distinct faulted-item count strictly decreases. Every
    attempt remains recorded, but rejected attempts never supply audit evidence.
    """
    from . import engineer as e, engineer_v28, fault_feedback
    best, best_report = change, report
    evidence = _evidence(ctx, best.procedure, best_report)
    record = {key: evidence[key] for key in ('fired', 'faulted', 'threshold', 'triggered')}
    record.update(calls=[], kept_index=0, stop_reason='not_triggered')
    checked = []
    limit = p.FAULT_REPAIRS if max_repairs is None else min(p.FAULT_REPAIRS, max_repairs)
    best_replays = dict(ctx.sheet.get('audit_replays', {}))
    while evidence['triggered']:
        if len(record['calls']) >= limit:
            record['stop_reason'] = 'limit'
            break
        number = len(record['calls']) + 1
        request = {'request': 'fault_repair', 'bench': ctx.bench,
                   'change': dict(best.entry, source=best.source), 'evidence': evidence,
                   'instruction': FAULT_REPAIR_INSTRUCTION}
        purpose = 'fault-repair/%d/%d' % (change.n, number)
        reply, call = e._ask(ctx, request, purpose)
        if call is None:
            record['stop_reason'] = 'no_calls_left'
            break
        event = {'call': call, 'parsed': False, 'checked': False, 'passed_fatal_checks': False,
                 'faulted_after': None, 'kept': False, 'request': request}
        record['calls'].append(event)
        if format_retry:
            changes, failures = engineer_v28.read_call(ctx, reply, call, purpose, change=best)
            candidate = changes[0] if len(changes) == 1 and not failures else None
        else:
            candidate = _read_once(ctx, reply, call, best)
        if candidate is None:
            record['stop_reason'] = 'unparseable'
            break
        event.update(parsed=True, parsed_call=candidate.call)
        candidate_report = e.check(candidate, ctx, taken)
        checked.append(candidate_report)
        fatal_passed = bool(candidate_report['passed']) and all(
            row['passed'] or row.get('informational') for row in candidate_report['checks'])
        event.update(checked=True, passed_fatal_checks=fatal_passed,
                     deferred=bool(candidate_report.get('deferred')))
        after = (_evidence(ctx, candidate.procedure, candidate_report)
                 if candidate.procedure is not None and any(
                     row['check'] == 'C6' for row in candidate_report['checks']) else None)
        event['faulted_after'] = after['faulted'] if after is not None else None
        if not fatal_passed or candidate_report.get('deferred') or after is None:
            record['stop_reason'] = 'failed_checks'
            break
        if after['faulted'] >= evidence['faulted']:
            record['stop_reason'] = 'no_improvement'
            break
        best, best_report, evidence = candidate, candidate_report, after
        best_replays = dict(ctx.sheet.get('audit_replays', {}))
        event['kept'] = True
        record['kept_index'] = number
        record['stop_reason'] = 'fixed' if not evidence['triggered'] else 'limit'
    # check() caches replay evidence by stable procedure id. Restore the kept
    # source's evidence after an unkept repair overwrote that cache entry.
    ctx.sheet.setdefault('audit_replays', {}).clear()
    ctx.sheet['audit_replays'].update(best_replays)
    record['final'] = {key: evidence[key] for key in ('fired', 'faulted', 'threshold', 'triggered')}
    return best, best_report, checked, record
