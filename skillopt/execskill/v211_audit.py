"""Frozen main-v4 public audit adapters. No task loading, execution, or private outcomes."""
from __future__ import annotations

import copy
import hashlib
import json
import random
from collections import defaultdict

from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from . import notes, profiles, replay
from .v211_effects import delivered

LEARNED = ('searchqa', 'officeqa', 'livemath', 'spreadsheetbench')
MARK = '…[truncated]'
LIMITS = {'question': 8000, 'context': 24000, 'choice': 2000, 'instruction': 8000,
          'report_message': 2000, 'answer_cells': 100, 'qa_group_bytes': 32000,
          'sheet_group_bytes': 64000, 'judge_input_bytes': 220000}
FIELDS = {b: ('question', 'context') for b in ('searchqa', 'officeqa')}
FIELDS['livemath'] = ('question', 'choices')
FIELDS['spreadsheetbench'] = ('instruction', 'workbook_preview', 'input_path', 'required_output_path',
                              'required_answer_position')


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))


def _clip(text, limit, path, metadata):
    if len(text) <= limit:
        return text
    # Keep the marker even at the minimum: immutable identifiers and note text are never clipped.
    keep = max(0, limit - len(MARK))
    left, right = (keep + 1) // 2, keep // 2
    shown = text[:left] + MARK + (text[-right:] if right else '')
    metadata[path] = {'original_length': len(text), 'disclosed_length': len(shown),
                      'original_sha256': sha(text)}
    return shown


def _tree(value, limit, path, metadata, *, labels=False):
    """Divide the text budget proportionally over ordered leaves without dropping containers or labels."""
    def leaves(node, here, name=None):
        if isinstance(node, str):
            return [] if labels and name in ('label', 'id', 'key') else [(here, len(node))]
        if isinstance(node, dict):
            return [leaf for k, v in node.items() for leaf in leaves(v, here + '/' + str(k), k)]
        if isinstance(node, list):
            return [leaf for i, v in enumerate(node) for leaf in leaves(v, here + '/' + str(i))]
        return []
    lengths = leaves(value, path)
    total = sum(n for _, n in lengths)
    base = sum(min(n, len(MARK)) for _, n in lengths)
    extra = max(0, total - base)
    available = max(0, limit - base)
    caps = {here: n if total <= limit else min(n, len(MARK)) +
            int(available * max(0, n - len(MARK)) / max(extra, 1)) for here, n in lengths}
    if total > limit and base > limit:
        metadata[path + '/_incomplete'] = {'reason': 'container_structure_and_truncation_mark_exceed_field_limit',
                                          'limit': limit, 'minimum_disclosure_length': base}
    def walk(node, here, name=None):
        if isinstance(node, str):
            return node if here not in caps else _clip(node, caps[here], here, metadata)
        if isinstance(node, dict):
            return {k: walk(v, here + '/' + str(k), k) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v, here + '/' + str(i)) for i, v in enumerate(node)]
        return copy.deepcopy(node)
    return walk(value, path)


def disclosure(bench, view, *, report=None, scale=1):
    require(bench in LEARNED, 'A main-v4 learned benchmark audit view')
    out = {key: copy.deepcopy(view[key]) for key in FIELDS[bench] if key in view}
    meta = {}
    for key in ('question', 'instruction'):
        if key in out:
            out[key] = _tree(out[key], int(LIMITS[key] * scale), key, meta)
    if 'context' in out:
        out['context'] = _tree(out['context'], int(LIMITS['context'] * scale), 'context', meta)
    if 'choices' in out:
        choices = out['choices']
        if isinstance(choices, dict):
            out['choices'] = {k: _tree(v, int(LIMITS['choice'] * scale), 'choices/' + str(k), meta, labels=True)
                              for k, v in choices.items()}
        elif isinstance(choices, list):
            out['choices'] = [_tree(v, int(LIMITS['choice'] * scale), 'choices/' + str(i), meta, labels=True)
                              for i, v in enumerate(choices)]
        elif isinstance(choices, str):
            from skillopt.continual_eval.datasets import LIVEMATH_LABELS, livemath_options
            options = livemath_options(choices)
            if options is not None:
                out['choices'] = '\n\n'.join(label + '. ' + _clip(text, int(LIMITS['choice'] * scale),
                    'choices/' + label, meta) for label, text in zip(LIVEMATH_LABELS, options))
            else:
                # An unregistered choice layout cannot safely be clipped across unseen labels.
                out['choices'] = choices
                if len(choices) > LIMITS['choice'] * scale:
                    meta['choices/_incomplete'] = {'reason': 'unregistered_choice_labels',
                                                   'original_sha256': sha(choices)}
        else:
            out['choices'] = copy.deepcopy(choices)
    if bench == 'spreadsheetbench':
        # The runtime preview is already 20 sheets x 5 rows x 20 columns. Only request fitting shortens its text.
        if 'workbook_preview' in out and scale < 1:
            out['workbook_preview'] = _tree(out['workbook_preview'], int(size(out['workbook_preview']) * scale),
                                             'workbook_preview', meta)
        if report is None:
            report = view.get('run_report')
        if report is not None:
            shown = {k: copy.deepcopy(report.get(k)) for k in ('status', 'exc_type', 'message', 'answer_cells')}
            shown['message'] = _tree(shown['message'], int(LIMITS['report_message'] * scale), 'run_report/message', meta)
            cells = shown['answer_cells']
            if isinstance(cells, (dict, list)):
                total = len(cells)
                if isinstance(cells, dict):
                    shown['answer_cells'] = dict(list(cells.items())[:LIMITS['answer_cells']])
                else:
                    shown['answer_cells'] = cells[:LIMITS['answer_cells']]
                if total > LIMITS['answer_cells']:
                    meta['run_report/answer_cells'] = {'original_length': total,
                        'disclosed_length': LIMITS['answer_cells'], 'omitted_count': total - LIMITS['answer_cells'],
                        'original_sha256': digest(cells)}
                if scale < 1:
                    shown['answer_cells'] = _tree(shown['answer_cells'], int(size(shown['answer_cells']) * scale),
                                                     'run_report/answer_cells_text', meta)
            out['run_report'] = shown
    return out, meta


def public_view(bench, view):
    return disclosure(bench, view)[0]


def _situation(*, bench, item, cell, package, source_hash, hook, request_hash, raw_view, text, procedure,
               source, package_procedures=None, replayed=False):
    from .audit import split_notes
    view, truncated = disclosure(bench, raw_view)
    phase = 'repair' if hook == 'sheet_feedback' else 'first'
    identity = digest([bench, item, cell, package, source_hash, hook, phase, request_hash, text])
    return {'bench': bench, 'item': item, 'cell': cell, 'step': None, 'package_sha256': package,
            'procedure_source_sha256': source_hash, 'hook': hook, 'phase': phase,
            'request_sha256': request_hash, 'source': source, 'view': view,
            'public_view_sha256': digest(raw_view), 'delivered_note_sha256': sha(text),
            'delivered_note_identity': identity, 'truncation': truncated,
            'package_procedures': copy.deepcopy(package_procedures or {procedure: source_hash}),
            'replayed': replayed,
            'notes': [{'procedure': procedure, 'text': sentence} for sentence in split_notes(text)]}


def situations_from_replays(procedure, entries, outcomes, *, trajectories):
    result = []
    for entry in entries:
        outcome = outcomes.get(entry['cell'])
        if outcome is None:
            continue
        require(trajectories is not None and entry['cell'] in trajectories,
                'A main-v4 audit replay requires its verified run trajectory')
        trace = trajectories[entry['cell']]
        call = next((c for c in trace.get('calls', ()) if c.get('purpose') == 'first'), None)
        if call is None or not delivered(call):
            continue
        for row in outcome.notes:
            hook, text = row.get('hook'), row.get('text')
            if hook not in ('before_call', 'bindings', 'sheet_feedback') or not text:
                continue
            if hook == 'sheet_feedback' and not outcome.repair:
                continue  # A note without a requested repair has no delivery occasion.
            raw = {k: copy.deepcopy(entry['request_view'][k]) for k in FIELDS[entry['bench']]
                   if k in entry['request_view']}
            if hook == 'sheet_feedback':
                if entry.get('report') is None:
                    continue
                raw['run_report'] = {k: copy.deepcopy(entry['report'].get(k))
                                     for k in ('status', 'exc_type', 'message', 'answer_cells')}
            result.append(_situation(bench=entry['bench'], item=entry['item'], cell=entry['cell'],
                package=replay.solo(procedure).sha256, source_hash=sha(procedure.source),
                hook=hook, request_hash=digest({'source_request': call['request_sha256'], 'hook': hook,
                    'view': raw, 'note': text}), raw_view=raw, text=text, procedure=procedure.id,
                source='run', replayed=True))
    return result


def situations_from_cells(cells, package):
    result = []
    by_id = {p.id: p for p in package.procedures}
    for trace in cells:
        if trace.get('arm') not in ("S'", 'candidate') and trace.get('arm_kind') != 'candidate':
            continue
        unit = trace.get('unit', '')
        source = 'confirm' if '/confirm-r' in unit else 'train' if '/train-r' in unit else None
        bench = trace['bench']
        if source is None or bench not in LEARNED:
            continue
        calls = {c['purpose']: c for c in trace.get('calls', ()) if c.get('purpose') in ('first', 'repair')}
        first = calls.get('first')
        if first is None:
            continue
        original = json.loads(first['user'])
        for row in (trace.get('shell') or {}).get('notes', ()):
            pid, hook = row.get('id'), row.get('hook')
            if pid not in by_id or hook not in ('before_call', 'bindings', 'sheet_feedback'):
                continue
            proc = by_id[pid]
            if row.get('source_sha256') != sha(proc.source):
                continue
            if (trace.get('package_procedures') or {}).get(pid, sha(proc.source)) != sha(proc.source):
                continue
            call = calls.get('repair' if hook == 'sheet_feedback' else 'first')
            if call is None or not delivered(call):
                continue
            request = json.loads(call['user'])
            container = str(request.get('repair_notes' if hook == 'sheet_feedback' else profiles.NOTES_KEY) or '')
            text = row.get('delivered_text')
            if not text or text not in container:
                continue
            raw = {key: copy.deepcopy(original[key]) for key in FIELDS[bench] if key in original}
            if hook == 'sheet_feedback':
                report = (trace.get('shell') or {}).get('precheck')
                if report is None:
                    continue
                raw['run_report'] = {k: copy.deepcopy(report.get(k)) for k in ('status', 'exc_type', 'message', 'answer_cells')}
            result.append(_situation(bench=bench, item=trace['task_id'], cell=trace['cell'],
                package=trace.get('package_sha256'), source_hash=sha(proc.source), hook=hook,
                request_hash=call['request_sha256'], raw_view=raw, text=text, procedure=pid, source=source,
                package_procedures=trace.get('package_procedures')))
    return result


def situation_key(row):
    return digest({key: row.get(key) for key in ('bench', 'item', 'hook', 'phase', 'view', 'procedure_source_sha256')})


def sample_situations(situations, *, bench, configuration, step, round, change_id, source_sha256,
                      exclude=(), final=False, final_package_sha256=None, final_procedures=None):
    from .audit import marked
    count = 8 if bench == 'spreadsheetbench' else 12
    seed = digest([configuration, step, round, change_id, source_sha256])
    rng = random.Random(int(seed, 16))
    def priority(row):
        if not final:
            return 0, 0
        sources = row.get('package_procedures') or {}
        return (0 if final_package_sha256 and row.get('package_sha256') == final_package_sha256 else
                1 if final_procedures and all(sources.get(k) == v for k, v in final_procedures.items()) else 2,
                0 if row.get('source') == 'confirm' else 1)
    seen, groups, excluded = set(), defaultdict(list), set(exclude)
    for row in sorted(situations, key=lambda r: (priority(r), r['item'], r.get('phase', ''), r.get('hook', ''), r['cell'])):
        key = situation_key(row)
        if key not in seen and key not in excluded and row['notes']:
            seen.add(key)
            groups[row['item']].append(row)
    tiers = defaultdict(list)
    for item, rows in sorted(groups.items()):
        tiers[min(priority(row) for row in rows)].append(item)
    items = []
    for tier in sorted(tiers):
        rng.shuffle(tiers[tier])
        items.extend(tiers[tier])
    selected = items[:count]
    extra = [item for item in items[count:] if any(marked(n['text'], bench) for row in groups[item] for n in row['notes'])][:4]
    selected += extra
    chosen = []
    for item in selected:
        # Keep every available hook/phase of the best evidence for this item, never split a sheet's phases.
        best, used = min(priority(row) for row in groups[item]), set()
        for row in groups[item]:
            key = (row.get('phase'), row.get('hook'), tuple(n['procedure'] for n in row['notes']))
            if priority(row) == best and key not in used:
                used.add(key)
                chosen.append(copy.deepcopy(row))
    for i, row in enumerate(chosen):
        row['s'] = 'S%d' % (i + 1)
        row['notes'] = [dict(note, n='N%d' % (j + 1)) for j, note in enumerate(row['notes'])]
    return {'seed_sha256': seed, 'eligible': len(seen), 'eligible_items': len(groups), 'extra': len(extra),
            'requested_items': count, 'sampled_items': len(selected), 'shortfall': max(0, count - len(selected)),
            'batch_unit': 'item_group', 'situations': chosen}


def batches(rows, bench):
    groups = defaultdict(list)
    for row in rows:
        groups[row['item']].append(row)
    grouped = list(groups.values())
    width = 2 if bench == 'spreadsheetbench' else 4
    return [[row for group in grouped[start:start + width] for row in group]
            for start in range(0, len(grouped), width)]


def fit_prompt(system, render, batch, *, bench, prefix='', suffix=''):
    scale = 1
    while True:
        shown = copy.deepcopy(batch)
        for row in shown:
            row['view'], more = disclosure(bench, row['view'], scale=scale)
            original = row.get('truncation', {})
            row['truncation'] = {**more, **original}
            for key, detail in more.items():
                if key in original and 'disclosed_length' in detail:
                    row['truncation'][key] = {**original[key], 'disclosed_length': detail['disclosed_length']}
        groups = defaultdict(list)
        for row in shown:
            groups[row['item']].append(row)
        cap = LIMITS['sheet_group_bytes' if bench == 'spreadsheetbench' else 'qa_group_bytes']
        group_bytes = {item: size(rows) for item, rows in groups.items()}
        user = prefix + render(shown) + suffix
        request_bytes = len((system + user).encode('utf-8'))
        representable = not any(k.endswith('/_incomplete') for row in shown for k in row['truncation'])
        within = (representable and request_bytes <= LIMITS['judge_input_bytes']
                  and all(n <= cap for n in group_bytes.values()))
        metadata = {'input_bytes': request_bytes, 'limit_bytes': LIMITS['judge_input_bytes'],
                    'group_limit_bytes': cap, 'group_bytes': group_bytes, 'public_text_scale': scale,
                    'within_limit': within, 'truncation': {r['s']: r['truncation'] for r in shown}}
        if within or scale <= 1 / 65536:
            return user, metadata
        scale /= 2


def run_audit(procedures, situations, judges, *, bench, configuration, step, round=0, change_id='', counts=None,
              cache=None, exclude=(), final=False, context_procedures=None, final_package_sha256=None):
    """Inherited verdict/parser/agreement; child-only item grouping, views, pins and completeness records."""
    from . import audit, engineer_v211
    cache = {} if cache is None else cache
    counts = counts or {}
    context_procedures = tuple(context_procedures or procedures)
    sampled = sample_situations(situations, bench=bench, configuration=configuration, step=step, round=round,
        change_id=change_id, source_sha256=sha(procedures[0].source) if len(procedures) == 1 else digest([sha(p.source) for p in procedures]),
        exclude=exclude, final=final, final_package_sha256=final_package_sha256,
        final_procedures={p.id: sha(p.source) for p in procedures})
    requests, findings = [], {j: {} for j in audit.JUDGES}
    available, incomplete = {j: True for j in audit.JUDGES}, []
    extracted_records = {}
    def pair(part, proc, user, *, extracted=None, batch=(), render=None):
        system = engineer_v211.audit_system(part, final=final)
        selected = 'A' if part == 'A' else 'final' if final else 'B'
        pinned = engineer_v211.pins()['audit'][bench][selected]
        require(system == pinned['text'] and sha(system) == pinned['sha256'],
                'The dispatched audit system matches the child benchmark/purpose pin')
        row = {'part': part, 'procedure': proc.id, 'requests': {}}
        required = audit._required_units(part, extracted=extracted, batch=batch)
        parser = lambda raw: audit.parse_verdict(raw, part, extracted=extracted, batch=batch, final=final,
                                                procedures=(proc,) if part == 'A' else procedures)
        renderer = render or (lambda shown: user)
        fit = lambda prefix, suffix: fit_prompt(system, renderer, batch, bench=bench, prefix=prefix, suffix=suffix)
        for judge in audit.JUDGES:
            found = audit._request(judge, judges.get(judge), system, user,
                label='audit/%s/%s/%s/%s' % (step, change_id, proc.id, len(requests)), parser=parser, cache=cache,
                required=required, final=final and part == 'B', fit_user=fit, disclosure_name='public_view_disclosure')
            found['system_sha256'] = sha(found['system'])
            found['user_sha256'] = sha(found['user'])
            for retry in found['retries']:
                retry['system_sha256'] = sha(retry['system'])
                retry['user_sha256'] = sha(retry['user'])
            row['requests'][judge] = found
            available[judge] &= found['available']
            if found['available']:
                findings[judge].update(audit.findings(found['parsed'], part=part, procedure=proc.id, batch=batch))
        for unit in required + (['contradictions'] if final and part == 'B' else []):
            missing = [j for j in audit.JUDGES if unit not in row['requests'][j]['covered']
                       and not (unit == 'contradictions' and row['requests'][j]['available']
                                and row['requests'][j]['parsed']['_validation']['contradictions_covered'])]
            if missing:
                incomplete.append({'request': len(requests), 'procedure': proc.id, 'unit': unit, 'judges': missing})
        requests.append(row)
    for proc in procedures:
        extracted = audit.templates(proc.source, bench)
        extracted_records[proc.id] = extracted
        user = audit.template_prompt(proc, bench, extracted, configuration=configuration)
        pair('A', proc, user, extracted=extracted)
        relevant = [row for row in sampled['situations'] if final or any(n['procedure'] == proc.id for n in row['notes'])]
        for batch in batches(relevant, bench):
            def render(rows):
                text = audit.situation_prompt(context_procedures if final else (proc,), bench, rows, counts,
                                              final=final, configuration=configuration)
                return text + ('\nThe program-level verdict is for Program ' + proc.id + '.' if final else '')
            pair('B', proc, render(batch), batch=batch, render=render)
    confirmed, advisory = audit.agreement(findings, available)
    totals = {j: {k: sum(pair['requests'][j]['tokens'][k] for pair in requests if not pair['requests'][j]['reused'])
                  for k in ('input', 'output', 'charged')} for j in audit.JUDGES}
    coverage = {'bench': bench, 'eligible_items': sampled['eligible_items'], 'sampled_items': sampled['sampled_items'],
                'requested_items': sampled['requested_items'], 'shortfall': sampled['shortfall'],
                'hooks': sorted({s['hook'] for s in sampled['situations']}),
                'phases': sorted({s['phase'] for s in sampled['situations']}), 'does_not_certify_other_benches': True}
    return {'phase': 2 if final else 1, 'policy_sha256': sha(audit.POLICY), 'sampling': sampled,
            'templates': extracted_records, 'counts': counts, 'requests': requests, 'available': available,
            'incomplete_units': incomplete, 'audit_incomplete': bool(incomplete) or not all(available.values()) or bool(sampled['shortfall']),
            'confirmed': confirmed, 'advisory': advisory, 'decision': 'confirmed' if confirmed else 'pass',
            'tokens': totals, 'situation_keys': [situation_key(s) for s in sampled['situations']],
            'coverage_by_bench': {bench: coverage}}
