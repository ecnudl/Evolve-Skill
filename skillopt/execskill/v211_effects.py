"""main-v4 hook effects and delivered-field coverage; historical paths never call this module."""
from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict

from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from . import notes, profiles, replay, solver

HOOKS = {bench: ('before_call', 'bindings') for bench in profiles.QA}
HOOKS['spreadsheetbench'] = ('before_call', 'sheet_feedback')


def delivered(call):
    return (call.get('receipt') or {}).get('delivery') in ('delivered', 'truncated')


def shown_fields(bench, package, stored, view, text, *, hook=None):
    """Attribute only stored, source-matching fields whose reconstructed text is delivered."""
    allowed = (hook,) if hook else HOOKS[bench]
    shown = defaultdict(set)
    for row in stored:
        pid = row.get('id')
        if pid not in package.order or row.get('hook') not in allowed:
            continue
        procedure = package.get(pid)
        if row.get('source_sha256') != hashlib.sha256(procedure.source.encode()).hexdigest():
            continue
        kept = notes.Screened(copy.deepcopy(row.get('fields') or {}), solver._public_text(view),
                              outcome_judged=notes.outcome_judged(procedure), audited=notes.audited(procedure))
        rendered = notes.render(kept, bench=bench, header=procedure.header) if kept else ''
        # delivered_text is set after package assembly, including declared and aggregate caps.
        exact = row.get('delivered_text', '')
        if exact and exact == rendered and exact in text:
            shown[pid].update(name for name in notes.FIELD_ORDER if kept.get(name))
    return dict(shown)


def coverage(st, pid, enabled, candidate, cells, made, current, identical, captured):
    """Count distinct run items and retain first/repair phase attribution; never execute a hook."""
    out = {'items': len(enabled), 'with_notes': 0, 'fields': {name: 0 for name in notes.FIELD_ORDER},
           'faults': 0, 'repair_requests': 0, 'phases': {'first': 0, 'repair': 0},
           'bench': st.bench}
    for key in enabled:
        fields, phases, fault, repair = set(), set(), False, False
        if key in identical:
            same = captured.get(key)
            require(same is not None, 'An identical coverage row needs its candidate signature observation')
            for trace in current:
                if trace['task_id'] != key:
                    continue
                for call in trace.get('calls', ()):
                    if call.get('purpose') == 'first' and delivered(call) and call['request_sha256'] == same['request_sha256']:
                        fields.update(same['fields'].get(pid, ()))
                        if fields:
                            phases.add('first')
                fault |= any(f.get('procedure') == pid for f in (trace.get('shell') or {}).get('faults', ()))
        else:
            for cell in cells.get(("S'", key), ()):
                fault |= any(f.get('procedure') == pid for f in cell.get('faults', ()))
                trace = made.get(cell['cell']['id'])
                if trace is None:
                    continue
                shell = trace.get('shell') or {}
                fault |= any(f.get('procedure') == pid for f in shell.get('faults', ()))
                for call in trace.get('calls', ()):
                    purpose = call.get('purpose')
                    if purpose not in ('first', 'repair') or not delivered(call):
                        continue
                    request = json.loads(call['user'])
                    hook = 'sheet_feedback' if purpose == 'repair' else None
                    stored = [row for row in shell.get('notes', ())
                              if (row.get('hook') == 'sheet_feedback') == (purpose == 'repair')]
                    text = str(request.get('repair_notes' if purpose == 'repair' else profiles.NOTES_KEY) or '')
                    found = shown_fields(st.bench, candidate, stored, request, text, hook=hook).get(pid, ())
                    fields.update(found)
                    if found:
                        phases.add(purpose)
                    if purpose == 'repair':
                        repair |= any(row.get('procedure') == pid and row.get('kind') == 'request_repair'
                                      and row.get('permitted') is True and row.get('source_sha256') ==
                                      hashlib.sha256(candidate.get(pid).source.encode()).hexdigest()
                                      for row in shell.get('effects', ()))
        out['with_notes'] += bool(fields)
        out['faults'] += bool(fault)
        out['repair_requests'] += bool(repair)
        for phase in phases:
            out['phases'][phase] += 1
        for name in fields:
            out['fields'][name] += 1
    return out


def routing_checks(procedure, ctx, *, outcomes=None, actual=None):
    """C6 over every registered run/generated item and every applicable hook, with stored sheet reports."""
    from . import engineer, engineer_payload, fault_feedback
    limit = profiles.slice_spec(ctx.configuration, ctx.bench)['run'][0] + profiles.G_SELF_MAX
    require(len(ctx.routing_items) <= limit, 'C6c evaluates the complete registered main-v4 routing set')
    require(len({item for item, _ in ctx.routing_items}) == len(ctx.routing_items), 'Routing items are unique')
    entries = {entry['item']: entry for entry in engineer._run_entries(ctx)}
    applicable = set(procedure.hooks).intersection(HOOKS[ctx.bench])
    firing = {'fires_on': 0, 'items': len(ctx.routing_items), 'predicate_faults': 0,
              'routing_view_keys': sorted({key for _, view in ctx.routing_items for key in view}),
              'captures': [], 'registered_bound': limit}
    detail = {'hook': list(HOOKS[ctx.bench]), 'fired': 0, 'empty': 0, 'exceptions': 0, 'nonempty': 0,
              'first_exception': None, 'view_keys': [], 'sample': None, 'empty_task_ids': [],
              'effects': {'before_call': 0, 'bindings': 0, 'sheet_feedback': 0, 'request_repair': 0},
              'missing_precheck': 0}
    if not applicable:
        detail.update(status='not_applicable', reason='no_note_writing_hook')
    package = replay.solo(procedure)

    def inspect(pair, worker):
        item, view = pair
        original = entries.get(item)
        entry = copy.deepcopy(original) if original else {
            'cell': 'routing:' + digest(item), 'bench': ctx.bench, 'item': item, 'token': None,
            'view': view, 'request_view': view, 'report': None, 'steps': None}
        entry['view'], entry['request_view'] = view, view
        # Runtime never executes bindings on sheets. This local solo projection preserves the source/hash.
        selected = procedure
        if ctx.bench == 'spreadsheetbench' and 'bindings' in procedure.hooks:
            from dataclasses import replace
            selected = replace(procedure, hooks=tuple(h for h in procedure.hooks if h != 'bindings'))
        captured = []
        result = replay.replay(worker, selected, entry, actual=captured, capture_faults=True)
        applies = bool(result.applies)
        firing['fires_on'] += applies
        firing['predicate_faults'] += any(f.get('hook') == 'applies' for f in result.faults)
        # Capture shape mirrors predicate_capture for inherited fault and inert diagnostics.
        captured_faults = list(result.faults)
        if item not in entries:
            captured_faults = [{key: value for key, value in fault.items()
                               if key in ('hook', 'step', 'kind', 'procedure', 'exc_type', 'line', 'informational')}
                               for fault in captured_faults]
        firing['captures'].append({'task_id': item, 'applies': result.applies,
                                  'faults': captured_faults, 'example_eligible': item in entries})
        if not applies or not applicable:
            return result
        detail['fired'] += 1
        detail['view_keys'] = sorted(set(detail['view_keys']) | set(view))
        if detail['sample'] is None and item in entries:
            detail['sample'] = engineer_payload.view_excerpt(view, chars=300)
        present = set()
        for row in result.notes:
            if row.get('text') and (row['hook'] != 'sheet_feedback' or result.repair):
                present.add(row['hook'])
        if result.bindings:
            present.add('bindings')
        if result.repair:
            present.add('request_repair')
        if ctx.bench == 'spreadsheetbench' and 'sheet_feedback' in applicable and entry['report'] is None:
            detail['missing_precheck'] += 1
        for hook in present:
            detail['effects'][hook] += 1
        failed = [row for row in captured if row.get('status') == 'raised']
        detail['exceptions'] += len(failed)
        if failed and detail['first_exception'] is None and item in entries:
            detail['first_exception'] = {k: failed[0].get(k) for k in ('status', 'exc_type', 'message')}
        detail['nonempty' if present else 'empty'] += 1
        if not present and not failed and item in entries and len(detail['empty_task_ids']) < 2:
            detail['empty_task_ids'].append(item)
        return result

    if ctx.bench != 'spreadsheetbench' and getattr(ctx, 'routing_shared_worker', False):
        for _ in replay.run_worker_pass(ctx.routing_items, lambda row: ctx.routing_workers(package, row[0]), inspect):
            pass
    else:
        for pair in ctx.routing_items:
            with ctx.routing_workers(package, pair[0]) as worker:
                inspect(pair, worker)
    skipped = not ctx.routing_items and ctx.mode == 'single'
    if skipped:
        firing.update(skipped=True, reason='no_training_items')
        detail.update(status='not_applicable', reason='no_training_items')
    return {'C6b': (firing['fires_on'] > 0 or skipped, firing),
            'C6c': (not applicable or detail['nonempty'] > 0 or skipped, detail)}
