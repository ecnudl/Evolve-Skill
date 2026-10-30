"""Bounded, run-slice-only explanations of v2.9.4 inert checks.

These helpers inspect existing results; they never execute a hook or read a
dataset. Earlier configurations do not call them.
"""
from __future__ import annotations

import ast
import copy

from . import fault_feedback as faults, profiles
from .package import procedure_input_benches

CAUSES = ('no_effect_hook', 'never_fires', 'empty_notes', 'crashed', 'excluded_bench')
FUNCTIONS = 32
FUNCTION_CHARS = 128
DECLARATION_BYTES = 1000
TASK_ID_BYTES = 512
EXAMPLES = 2


def remember_declaration(change, entry):
    """Preserve absence as well as the raw manifest value before hook derivation."""
    if not hasattr(change, '_inert_declaration'):
        change._inert_declaration = ({'declared_hooks': copy.deepcopy(entry['hooks'])}
                                    if 'hooks' in entry else {})


def _counts(detail):
    return {key: value for key, value in detail.items() if type(value) is int}


def _examples(ctx, tasks, *, procedure=None):
    from . import engineer
    # Membership is validated by the same run-entry selector used for C6c.
    entries = {entry['item']: entry for entry in engineer._run_entries(ctx)}
    if profiles.is_v214(getattr(ctx, 'configuration', None)) and procedure is not None:
        allowed = procedure_input_benches(procedure)
        entries = {item: entry for item, entry in entries.items() if entry['bench'] in allowed}
    views = dict(ctx.routing_items)
    result = []
    for task in sorted(set(tasks).intersection(entries)):
        if faults.serialized_bytes(task) > TASK_ID_BYTES:
            continue  # Never invent a shortened task ID.
        entry = entries[task]
        view = views.get(task, entry.get('request_view') or entry.get('view'))
        if profiles.uses_v211(getattr(ctx, 'configuration', None), ctx.bench) and ctx.bench == 'spreadsheetbench':
            view = copy.deepcopy(view)
            if entry.get('report') is not None:
                view['run_report'] = {k: entry['report'].get(k) for k in ('status', 'exc_type', 'message', 'answer_cells')}
        result.append({'task_id': task, 'view': faults.bounded_json(view, faults.VIEW_CHARS)})
        if len(result) == EXAMPLES:
            break
    return result


def _bound(evidence):
    """Preserve cause names/counts, fit actual UTF-8 request serialization."""
    if faults.serialized_bytes(evidence) <= faults.EVIDENCE_BYTES:
        return evidence
    for cause in reversed(CAUSES):
        detail = evidence.get(cause, {})
        for example in reversed(detail.get('examples', [])):
            excess = faults.serialized_bytes(evidence) - faults.EVIDENCE_BYTES
            if excess <= 0:
                return evidence
            size = faults.serialized_bytes(example['view'])
            example['view'] = faults._argument_bytes(example['view'], max(100, size - excess - 25))
            detail['truncated'] = True
    names = evidence.get('no_effect_hook', {}).get('defined_functions', [])
    while faults.serialized_bytes(evidence) > faults.EVIDENCE_BYTES and names:
        names.pop()
        evidence['no_effect_hook']['truncated'] = True
    # Fixed cause keys/counts plus bounded signatures/declarations/IDs fit even
    # after every view has reached its minimum prefix allowance.
    assert faults.serialized_bytes(evidence) <= faults.EVIDENCE_BYTES
    return evidence


def describe(change, ctx, report, *, effect_hooks, from_replay, from_routing, outcomes):
    """Return ordered cause names and evidence for an already inert change."""
    procedure = change.procedure
    checks = {row['check']: row.get('detail') or {} for row in report['checks']}
    routing, notes = checks.get('C6b', {}), checks.get('C6c', {})
    evidence = {}
    if not set(effect_hooks).intersection(procedure.hooks):
        functions = [node.name for node in ast.parse(change.source).body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        names = [name[:FUNCTION_CHARS] for name in functions[:FUNCTIONS]]
        detail = {'defined_functions': names, 'effect_hooks': list(effect_hooks)}
        declared = getattr(change, '_inert_declaration', {})
        if 'declared_hooks' in declared:
            detail['declared_hooks'] = faults._argument_bytes(declared['declared_hooks'], DECLARATION_BYTES)
        if names != functions or detail.get('declared_hooks') != declared.get('declared_hooks'):
            detail['truncated'] = True
        evidence['no_effect_hook'] = detail
    if from_routing:
        tasks = [row['task_id'] for row in routing.get('captures', ()) if row.get('applies') is False]
        evidence['never_fires'] = {'counts': _counts(routing), 'examples': _examples(ctx, tasks, procedure=procedure)}
    if (notes.get('status') != 'not_applicable' and notes.get('fired', 0) > 0
            and notes.get('nonempty', 0) == 0):
        examples = _examples(ctx, notes.get('empty_task_ids', ()), procedure=procedure)
        evidence['empty_notes'] = {'counts': _counts(notes),
                                   'task_ids': [row['task_id'] for row in examples], 'examples': examples}
    # A routing rejection is not a crashed replay. Require an applicable replay
    # before using the existing all-applicable-replays-crashed condition.
    if from_replay and any(outcome.applies for outcome in outcomes.values()):
        summary = faults.summarize(procedure, report, limit=3, example=False,
                                   configuration=ctx.configuration,
                                   **({'bench': ctx.bench} if profiles.is_v214(ctx.configuration) else {}))
        evidence['crashed'] = {'signatures': summary['signatures']}
        if summary.get('truncated'):
            evidence['crashed']['truncated'] = True
    if (ctx.bench in procedure.excluded_benches or (profiles.is_v214(ctx.configuration)
            and ctx.bench not in procedure_input_benches(procedure))):
        evidence['excluded_bench'] = {'bench': ctx.bench}
    return list(evidence), _bound(evidence)


def causes_ok(value):
    return (isinstance(value, list) and all(type(cause) is str for cause in value)
            and value == [cause for cause in CAUSES if cause in value])
