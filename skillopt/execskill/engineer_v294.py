"""Opt-in v2.9.4 inert feedback and one repair; historical prompts stay frozen."""
from __future__ import annotations

from . import audit, engineer_v29, engineer_v291, engineer_v293, profiles as p

INERT_REPAIRS = p.INERT_REPAIRS
REPAIRABLE_CAUSES = frozenset({'no_effect_hook', 'never_fires', 'empty_notes'})
EXCLUDED_CAUSES = frozenset({'crashed', 'excluded_bench'})
INERT_REPAIR_INSTRUCTION = (
    'The program had no effect because {causes}. The shell calls only top-level functions named exactly '
    'like these hooks: {hooks}; declaring a hook in the manifest does not create it. Return the corrected '
    'change in the usual format (same id and kind), keeping its intended behaviour, or withdraw it. '
    + engineer_v29.SHORT_POLICY
)


def hook_names(configuration):
    """Generate this bench's callable names from the registered hook vocabulary."""
    allowed = {'applies', 'alf_before_step', 'alf_after_step'} if p.is_alfworld(configuration) else {
        'applies', 'before_call'}
    return tuple(hook for hook in p.HOOKS if hook in allowed)


def hook_rule(configuration):
    return ('The shell calls only top-level functions whose names are exactly the hook names (%s); '
            'declaring a hook in the manifest does not create it; a program that defines no note-writing '
            'hook, never applies, or never returns a note has no effect and is not trained.'
            % ', '.join(hook_names(configuration)))


def inert_repair_instruction(configuration, causes):
    return INERT_REPAIR_INSTRUCTION.format(causes=', '.join(causes),
                                           hooks=', '.join(hook_names(configuration)))


def system(configuration, *, train):
    parent = {'zebra-pc-v11': 'zebra-pc-v10', 'alfworld-v8': 'alfworld-v7'}[configuration]
    return (engineer_v293.system(parent, train=train).replace('(v2.9.3)', '(v2.9.4)')
            + hook_rule(configuration) + '\n')


def prompt_pins():
    configurations = ('zebra-pc-v11', 'alfworld-v8')
    values = {configuration + '/' + mode: system(configuration, train=mode == 'train')
              for configuration in configurations for mode in ('single', 'train')}
    for configuration in configurations:
        values[configuration + '/note_caps'] = engineer_v291.note_caps_rule(configuration)
        values[configuration + '/hook_rule'] = hook_rule(configuration)
        values[configuration + '/inert_repair'] = inert_repair_instruction(configuration, ['<cause>'])
    values.update(fix=engineer_v29.FIX_SYSTEM, format_retry=engineer_v293.FORMAT_RETRY_SYSTEM,
                  audit_fix=engineer_v29.AUDIT_FIX_SYSTEM,
                  fault_repair=engineer_v291.FAULT_REPAIR_INSTRUCTION,
                  inert_repair=INERT_REPAIR_INSTRUCTION)
    return {key: {'text': value, 'sha256': audit.text_sha256(value)} for key, value in values.items()}


def _fatal_passed(report):
    return bool(report['passed']) and all(row['passed'] or row.get('informational')
                                         for row in report['checks'])


def repair(ctx, change, report, taken=()):
    """Keep the one repair only when fatal checks pass and the change has an effect.

    The original remains index zero. A rejected attempt keeps its report but
    cannot overwrite the original's replay evidence or next-round feedback.
    """
    from . import engineer as e, engineer_v28
    causes = list(report.get('inert_causes', ()))
    record = {'causes': causes, 'calls': [], 'kept_index': 0, 'stop_reason': 'not_triggered'}
    if (not p.is_v294(ctx.configuration) or change.kind not in e.CODED
            or not _fatal_passed(report) or report.get('deferred') or not report.get('inert')
            or not REPAIRABLE_CAUSES.intersection(causes) or EXCLUDED_CAUSES.intersection(causes)):
        return change, report, [], record
    original_replays = dict(ctx.sheet.get('audit_replays', {}))
    request = {'request': 'inert_repair', 'bench': ctx.bench,
               'change': dict(change.entry, source=change.source),
               'evidence': report.get('inert_evidence', {}),
               'instruction': inert_repair_instruction(ctx.configuration, causes)}
    if p.uses_v211(ctx.configuration, ctx.bench):
        from . import engineer_v211
        request.update(causes=sorted(set(causes)),
                       instruction=engineer_v211.inert_repair_instruction(ctx.bench, causes))
    purpose = 'inert-repair/%d/1' % change.n
    reply, call = e._ask(ctx, request, purpose)
    if call is None:
        record['stop_reason'] = 'no_calls_left'
        return change, report, [], record
    event = {'call': call, 'parsed': False, 'checked': False, 'passed_fatal_checks': False,
             'inert_after': None, 'kept': False, 'request': request}
    record['calls'].append(event)
    changes, failures = engineer_v28.read_call(ctx, reply, call, purpose, change=change)
    if len(changes) != 1 or failures:
        record['stop_reason'] = 'unparseable'
        return change, report, [], record
    candidate = changes[0]
    event.update(parsed=True, parsed_call=candidate.call)
    checked = e.check(candidate, ctx, taken)
    fatal_passed = _fatal_passed(checked)
    inert_after = bool(checked.get('inert'))
    event.update(checked=True, passed_fatal_checks=fatal_passed,
                 inert_after=inert_after, deferred=bool(checked.get('deferred')))
    if fatal_passed and not checked.get('deferred') and not inert_after:
        event['kept'] = True
        record.update(kept_index=1, stop_reason='fixed')
        return candidate, checked, [checked], record
    record['stop_reason'] = ('failed_checks' if not fatal_passed or checked.get('deferred')
                             else 'still_inert')
    ctx.sheet.setdefault('audit_replays', {}).clear()
    ctx.sheet['audit_replays'].update(original_replays)
    return change, report, [checked], record
