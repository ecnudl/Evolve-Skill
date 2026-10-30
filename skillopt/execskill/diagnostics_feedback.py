"""Bounded, engineer-only v2.15 evidence over already measured public hook returns."""
from __future__ import annotations

import copy
from collections import defaultdict

from skillopt.coevo5.roles import message_bytes
from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from . import diagnostics

KEY = 'engineer_diagnostics'
ENVELOPE_BYTES = diagnostics.INPUT_BYTES - len(KEY) - 6
MAX_ITEMS = 60
TASK_ID_BYTES = 512
TOP = 8
VERSION = 'execskill-v2-15-diagnostics-feedback'
SOURCES = ('replay', 'routing', 'candidate', 'identical_request_candidate', 'unchanged_routing_current', 'unavailable')
LABELS = ('fixed', 'broken', 'unchanged_wrong', 'no_note', 'faulted', 'fired', 'never_fires')


def _identity(task):
    require(type(task) is str, 'A diagnostic item has its original task identity')
    return ({'task_id': task} if message_bytes(task) <= TASK_ID_BYTES else
            {'task_id_sha256': digest(task), 'id_omitted': True})


def _seal(value):
    return {**value, 'sha256': digest(value)}


def _display(text, *, limit=None):
    """Screen exactly the text to be displayed, including newly exposed word prefixes."""
    from . import audit, notes
    shown = text if limit is None else text[:limit]
    screened = bool(audit.marked(shown, 'zebralogic') or
                    any(marker in shown.lower() for marker in notes.CHANNEL_MARKERS_V29))
    if screened:
        shown = diagnostics.SCREENED_MARKER
    return {'text': shown, 'full_text_sha256': diagnostics.sha256(text), 'chars': len(text),
            'truncated': screened or shown != text, 'screened': screened}


def _omission(sink, stage, reason):
    """Fixed reason/count telemetry is recorded outside every model payload."""
    if sink is not None:
        tally = sink.setdefault('diagnostics_omissions', {'count': 0, 'reasons': {}, 'stages': {}})
        tally['count'] += 1
        tally['reasons'][reason] = tally['reasons'].get(reason, 0) + 1
        tally['stages'][stage] = tally['stages'].get(stage, 0) + 1


def telemetry(sink):
    return ({'diagnostics_omissions': copy.deepcopy(sink['diagnostics_omissions'])}
            if sink and sink.get('diagnostics_omissions') else {})


def attach(container, builder, *, sink, stage):
    """An informational builder or validator failure can only omit this envelope."""
    try:
        value = builder()
    except Exception:
        _omission(sink, stage, 'build_failed')
        return container
    try:
        own = {row.get('task_id', row.get('task_id_sha256')) for row in value['items']}
        require(valid(value, own=own), 'Valid informational envelope')
    except Exception:
        _omission(sink, stage, 'validation_failed')
        return container
    container[KEY] = value
    return container


def sanitize_training(training, *, own, sink):
    """Keep all legacy training validation strict; only this optional channel may disappear."""
    if isinstance(training, dict) and KEY in training:
        try:
            require(valid(training[KEY], own=own) and training[KEY]['items_count'] == len(own),
                    'Valid run-only informational envelope')
        except Exception:
            _omission(sink, 'training_context', 'validation_failed')
            return {key: value for key, value in training.items() if key != KEY}
    return training


def sanitize_request(user, *, sink, stage):
    """Remove failed metadata before prompt selection; preserve every legacy request byte.

    Strip before copying so even an unserializable diagnostic envelope cannot
    interfere with the ordinary request. The caller's recorded request is updated
    to match the actual transmitted request when metadata is omitted.
    """
    extras = []
    def strip(value):
        if isinstance(value, dict):
            if KEY in value:
                extras.append(value[KEY])
            return {key: strip(child) for key, child in value.items() if key != KEY}
        if isinstance(value, list):
            return [strip(child) for child in value]
        return value
    base = strip(user)
    if extras:
        try:
            check_request(user)
        except Exception:
            _omission(sink, stage, 'request_validation_failed')
            user.clear()
            user.update(base)
    return user


def build(items, *, examples=(), bench='zebralogic'):
    """Keep every item/digest/count; fit only the new displayed diagnostic strings.

    Repeated replay passes and duplicate strings count once per item. Dictionary
    order is frequency, then lexical text; the aggregate always names its top eight.
    """
    require(len(items) <= MAX_ITEMS and len({row['task_id'] for row in items}) == len(items),
            'Diagnostic feedback uses distinct items from the 60-item run slice')
    rows, texts, members = [], {}, defaultdict(set)
    for item in sorted(items, key=lambda row: row['task_id']):
        records = {}
        for value in item.get('records', ()):
            checked = diagnostics.verified_record(value, bench=bench)
            records[checked['sha256']] = checked
        records = [records[key] for key in sorted(records)]
        found = {string['text'] for record in records for string in record['strings']}
        for text in found:
            texts[text] = diagnostics.sha256(text)
            if 'fired' in item.get('labels', ()):
                members[text].add(item['task_id'])
        rows.append({**_identity(item['task_id']), 'source': item.get('source', 'unavailable'),
            'labels': [name for name in LABELS if name in item.get('labels', ())],
            'diagnostics_sha256': digest(records), 'records': len(records),
            'strings': sum(len(record['strings']) for record in records),
            'screened': sum(record['screened_count'] for record in records),
            'truncated': sum(record['truncated_strings'] for record in records),
            'omitted': sum(record['omitted_strings'] for record in records),
            'ignored': sum(record['ignored_values'] for record in records),
            '_texts': found})
    ordered = sorted(texts, key=lambda text: (-len(members[text]), text))
    aggregate = [text for text in ordered if members[text]][:TOP]
    index = {text: n for n, text in enumerate(ordered)}
    for row in rows:
        row['text_indices'] = sorted(index[text] for text in row.pop('_texts'))
        row['display_omitted'] = 0
    value = {'version': VERSION, 'items': rows, 'texts': [_display(text)
        for text in ordered], 'aggregate': [{'text_index': index[text], 'items': len(members[text])}
                                          for text in aggregate],
        'example_indices': [n for n, row in enumerate(sorted(items, key=lambda row: row['task_id']))
                            if row['task_id'] in set(examples)],
        'items_count': len(rows), 'distinct_strings': len(ordered), 'display_omitted': 0,
        'display_truncated': False, 'display_screened': 0, 'limit_bytes': diagnostics.INPUT_BYTES}
    value['display_screened'] = sum(entry['screened'] for entry in value['texts'])
    # Preserve all text identities while reducing their displayed prefixes first.
    if message_bytes(_seal(value)) > ENVELOPE_BYTES:
        value['display_truncated'] = True
        for n in range(TOP, len(value['texts'])):
            entry = _display(ordered[n], limit=32)
            value['texts'][n] = entry
        value['display_screened'] = sum(entry['screened'] for entry in value['texts'])
    # Even empty prefixes can exceed the allowance with many distinct strings.
    # Remove only lower-ranked dictionary displays, retaining all item counts/digests.
    while message_bytes(_seal(value)) > ENVELOPE_BYTES and len(value['texts']) > min(TOP, len(ordered)):
        removed = len(value['texts']) - 1
        value['texts'].pop()
        value['display_omitted'] += 1
        value['display_truncated'] = True
        for row in rows:
            if removed in row['text_indices']:
                row['text_indices'].remove(removed)
                row['display_omitted'] += 1
    require(message_bytes(_seal(value)) <= ENVELOPE_BYTES,
            'Every diagnostic item identity and aggregate must fit the dedicated sub-budget')
    sealed = _seal(value)
    require(valid(sealed, own={item['task_id'] for item in items}),
            'Every built diagnostic display is screened and internally consistent')
    return sealed


def valid(value, *, own):
    """Validate bounded feedback and membership without consulting private answers."""
    try:
        from . import audit, notes
        def sha(text):
            return type(text) is str and len(text) == 64 and all(c in '0123456789abcdef' for c in text)
        if set(value) != {'version', 'items', 'texts', 'aggregate', 'example_indices', 'items_count',
                          'distinct_strings', 'display_omitted', 'display_truncated', 'display_screened',
                          'limit_bytes', 'sha256'}:
            return False
        body = {key: child for key, child in value.items() if key != 'sha256'}
        if (value.get('version') != VERSION or value.get('sha256') != digest(body)
                or value.get('limit_bytes') != diagnostics.INPUT_BYTES
                or message_bytes(value) > ENVELOPE_BYTES
                or value['items_count'] != len(value['items']) or len(value['items']) > MAX_ITEMS
                or len(value['aggregate']) > TOP or type(value['display_truncated']) is not bool
                or type(value['display_omitted']) is not int or value['display_omitted'] < 0
                or type(value['display_screened']) is not int or value['display_screened'] < 0
                or value['distinct_strings'] != len(value['texts']) + value['display_omitted']):
            return False
        allowed = {_identity(task).get('task_id', _identity(task).get('task_id_sha256')) for task in own}
        seen = set()
        for row in value['items']:
            identity = row.get('task_id', row.get('task_id_sha256'))
            identity_fields = {'task_id'} if 'task_id' in row else {'task_id_sha256', 'id_omitted'}
            if (set(row) != identity_fields | {'source', 'labels', 'diagnostics_sha256', 'records', 'strings',
                    'screened', 'truncated', 'omitted', 'ignored', 'text_indices', 'display_omitted'}
                    or identity not in allowed or identity in seen or row['source'] not in SOURCES
                    or not sha(row['diagnostics_sha256'])
                    or row['labels'] != [label for label in LABELS if label in row['labels']]
                    or any(type(row[name]) is not int or row[name] < 0 for name in (
                        'records', 'strings', 'screened', 'truncated', 'omitted', 'ignored', 'display_omitted'))
                    or not all(type(n) is int and 0 <= n < len(value['texts']) for n in row['text_indices'])):
                return False
            if 'task_id' in row and message_bytes(row['task_id']) > TASK_ID_BYTES:
                return False
            if 'task_id' not in row and (row.get('id_omitted') is not True or not sha(identity)):
                return False
            seen.add(identity)
        for row in value['texts']:
            if (set(row) != {'text', 'full_text_sha256', 'chars', 'truncated', 'screened'}
                    or type(row['text']) is not str or len(row['text']) > diagnostics.MAX_CHARS
                    or not sha(row['full_text_sha256']) or type(row['chars']) is not int
                    or row['chars'] < 0 or type(row['truncated']) is not bool or type(row['screened']) is not bool
                    or (row['screened'] and (row['text'] != diagnostics.SCREENED_MARKER or not row['truncated']))
                    or (not row['screened'] and row['chars'] < len(row['text']))
                    or audit.marked(row['text'], 'zebralogic')
                    or any(marker in row['text'].lower() for marker in notes.CHANNEL_MARKERS_V29)
                    or (not row['truncated'] and diagnostics.sha256(row['text']) != row['full_text_sha256'])):
                return False
        return (sum(row['screened'] for row in value['texts']) <= value['display_screened']
                <= sum(row['screened'] for row in value['texts']) + value['display_omitted']
                and all(type(n) is int and 0 <= n < len(value['items']) for n in value['example_indices'])
                and all(set(row) == {'items', 'text_index'}
                        and type(row['items']) is int and 0 < row['items'] <= len(value['items'])
                        and type(row['text_index']) is int and 0 <= row['text_index'] < len(value['texts'])
                        for row in value['aggregate']))
    except Exception:
        return False


def check_request(user):
    """The old content keeps its full allowance; only the new envelope spends the extra 64k."""
    base, extra = copy.deepcopy(user), []
    def remove(value):
        if isinstance(value, dict):
            if KEY in value:
                extra.append(value.pop(KEY))
            for child in value.values():
                remove(child)
        elif isinstance(value, list):
            for child in value:
                remove(child)
    remove(base)
    from .profiles import ROLE_INPUT_BYTES
    require(message_bytes(base) <= ROLE_INPUT_BYTES, 'The original engineer evidence retains its 220000-byte bound')
    require(len(extra) <= 1, 'One dedicated diagnostic envelope per engineer request')
    for value in extra:
        identities = {row.get('task_id', row.get('task_id_sha256')) for row in value.get('items', ())}
        require(valid(value, own=identities), 'Diagnostic feedback must remain bounded, screened and hash-verified')
    # The reserved allowance includes the new key and its serialization punctuation.
    require(message_bytes(user) - message_bytes(base) <= diagnostics.INPUT_BYTES,
            'Only the fixed diagnostic envelope may extend the engineer request')
    require(message_bytes(user) <= ROLE_INPUT_BYTES + diagnostics.INPUT_BYTES,
            'The complete v2.15 engineer payload is at most 284000 bytes')


def from_checks(ctx, procedure, report, *, only_faulted=False, examples=()):
    """Combine C6 and C6c observations only for verified items of this step's run slice."""
    from . import engineer
    run = {entry['item']: entry for entry in engineer._run_entries(ctx)}
    items = {task: {'task_id': task, 'records': [], 'labels': [], 'source': 'replay'} for task in run}
    checks = {row['check']: row.get('detail') or {} for row in report.get('checks', ())}
    for row in checks.get('C6', {}).get('items', ()):
        task = row.get('task_id')
        if task not in items:
            continue
        item = items[task]
        for phase in ('first', 'second'):
            outcome = row.get(phase) or {}
            item['records'].extend(outcome.get('diagnostics') or ())
            if outcome.get('applies'):
                item['labels'].append('fired')
            if any(not fault.get('informational') and fault.get('procedure', procedure.id) == procedure.id
                   for fault in outcome.get('faults', ())):
                item['labels'].append('faulted')
    for row in checks.get('C6c', {}).get('diagnostics', ()):
        if row['task_id'] in items:
            item = items[row['task_id']]
            item['records'].extend(row['records'])
            item['labels'] += ['fired'] + (['no_note'] if row['no_note'] else [])
    for item in items.values():
        if 'fired' not in item['labels']:
            item['labels'].append('never_fires')
    selected = [item for item in items.values() if not only_faulted or 'faulted' in item['labels']]
    return build(selected, examples=examples, bench=ctx.bench)


def training(*, bench, run_keys, verdict, routed, candidate, cells, made, current, observed=None, examples=()):
    """All run items, including candidate observations whose solver request was reused.

    Equal enabled IDs imply the same immutable procedures; their current public
    diagnostics can be attributed to the candidate without executing another hook.
    Equal requests with different IDs use the candidate's actual signature shell.
    """
    from . import step
    current_by_item = defaultdict(list)
    for trace in current:
        if trace['bench'] == bench and trace['task_id'] in run_keys:
            current_by_item[trace['task_id']].append(trace)
    fixed, broken = set(verdict['fixed']), set(verdict['broken'])
    identical = set(verdict.get('identical', ()))
    items = []
    for task in sorted(run_keys):
        traces = [made[row['cell']['id']] for row in cells.get(("S'", task), ())
                  if row['cell']['id'] in made]
        traces = [trace for trace in traces if trace['bench'] == bench and trace['task_id'] == task
                  and trace.get('arm_kind') == 'candidate']
        records, no_note, source = [], False, 'unavailable'
        if traces:
            source = 'candidate'
            records = [record for trace in traces for record in (trace.get('shell') or {}).get('diagnostics', ())]
            no_note = any(not step._notes_text(trace) for trace in traces)
        elif task in identical and task in (observed or {}):
            seen = observed[task]
            source, records, no_note = 'identical_request_candidate', seen['records'], seen['no_note']
            traces = current_by_item[task]
        elif routed.get(task, {}).get('candidate') == routed.get(task, {}).get('incumbent'):
            traces = current_by_item[task]
            source = 'unchanged_routing_current'
            records = [record for trace in traces for record in (trace.get('shell') or {}).get('diagnostics', ())]
            no_note = (any(not step._notes_text(trace) for trace in traces) if traces else
                       not routed.get(task, {}).get('candidate'))
        checked = []
        for record in records:
            pid = record.get('procedure')
            if pid in candidate.order and record.get('source_sha256') == diagnostics.sha256(candidate.get(pid).source):
                checked.append(record)
        labels = (['fixed'] if task in fixed else ['broken'] if task in broken else
                  ['unchanged_wrong'] if any(trace.get('token') == 'fail' for trace in traces) else [])
        if no_note:
            labels.append('no_note')
        if routed.get(task, {}).get('candidate'):
            labels.append('fired')
        items.append({'task_id': task, 'records': checked, 'labels': labels, 'source': source})
    return build(items, examples=examples, bench=bench)
