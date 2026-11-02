"""Cross-v5 practice-only request coverage, using the registered read planner."""
from __future__ import annotations

from fractions import Fraction
from functools import partial

from skillopt.continual_eval.core import require

from . import evaluation, profiles as p, reuse, rounds, smoke, units, v214_smoke as v
from . import v217_implant, v218_read, v219_read
from .cells import TrainingStore, cell_id, run_cells
from .package import empty


def practice(setting, attempt, endpoint, unit, bench, tasks, chain):
    """Keep every inherited C measurement and exercise all cross arms on one practice item."""
    require(p.is_v219(p.configuration_of(setting)), 'Cross smoke belongs only to cross-v5')
    context = units.cell_context(setting, attempt, endpoint)
    card = empty(step=unit, evidence=setting.evidence)
    arms = v219_read.arms(bench, v217_implant.final_package(chain, setting.evidence), card)
    key = next(iter(tasks))
    task = tasks[key]
    first_task = {'task_id': key, **task}
    planned = (v219_read.plan({'tasks': [first_task]}, arms, {}, bench=bench, context=context,
               workers=partial(evaluation._route_worker, setting)) if bench in reuse.BENCHES else None)

    class CapturedStore(TrainingStore):
        def __init__(self):
            super().__init__(attempt)
            self.rows = {}

        def save(self, value, trajectory):
            self.rows[value['cell']['id']] = value
            return super().save(value, trajectory)

    captured = CapturedStore()
    store = v218_read.Store(captured, planned) if planned is not None else captured
    jobs, linked = [], []
    for label in v219_read.labels(bench):
        cell = {'id': cell_id(unit, label, key, 0), 'unit': unit, 'arm': label,
                'benchmark': bench, 'task_id': key, 'run': 0}
        job = cell, task, arms[label]
        source = planned['sources'][label][key] if planned is not None else None
        if source is None:
            jobs.append(job)
        else:
            linked.append((job, source))
    first_job = next(job for job in jobs if job[0]['arm'] == 'C')
    first = run_cells(context, [first_job], workers=1, store=store)[0]
    require(first.get('final') is not None and first.get('stop') is None,
            'A confirmed actual first reply precedes concurrent practice cells')
    sources = {('C', key, 0): first}
    rest_jobs = [job for job in jobs if job is not first_job]
    order = rounds._order(list(range(len(rest_jobs))), p.round_tag(unit) + ':cross-practice')
    rest_jobs = [rest_jobs[i] for i in order]
    ran = run_cells(context, rest_jobs, workers=setting.workers, store=store)
    sources.update({(job[0]['arm'], key, 0): value for job, value in zip(rest_jobs, ran)})
    if planned is not None:
        fallback = v218_read.linked(context, linked, sources, planned, store=store)
        if fallback:
            run_cells(context, fallback, workers=setting.workers, store=store)
    first_cells = list(captured.rows.values())
    remainder = rounds.run_round(setting, attempt, endpoint, unit, {'C': arms['C']},
        {'C': [(item, 1) for item in tasks if item != key]}, tasks, tag='measured')
    cells = first_cells + [row for group in remainder.values() for row in group]
    dispatched = [row for row in cells if row.get('shared_with') is None]
    measured = smoke.measured_cells(dispatched)
    cost_by_arm = {}
    for label in v219_read.labels(bench):
        found = [row for row in dispatched if row['cell']['arm'] == label]
        if found:
            cost_by_arm[label] = smoke.measured_cells(found)['per_class'][bench]
    first_by_arm = {row['cell']['arm']: row for row in first_cells}
    coverage = {label: {'cells': 1, 'cell': first_by_arm[label]['cell']['id'],
        'card_source': first_by_arm[label]['card_source'],
        'shared_with': first_by_arm[label].get('shared_with'),
        'source_arm': first_by_arm[label].get('request_reuse', {}).get('source_arm'),
        'request_sha256': [call['request_sha256'] for call in first_by_arm[label].get('logical_calls', [])],
        'request_reuse': first_by_arm[label].get('request_reuse')}
        for label in v219_read.labels(bench)}
    valid = sum((row.get('final') or {}).get('token') in ('pass', 'fail') for row in cells)
    parsed = (sum(((row.get('judge') or {}).get('format') or {}).get('grid') is True
                  for row in cells if row['cell']['arm'] == 'C') if bench == p.ZEBRA else None)
    return {'passed': valid == len(cells) == v.S2_ITEMS[bench] + 6 and (parsed is None or parsed >= 9),
        'items': len(tasks), 'cells': len(cells), 'dispatched_cells': len(dispatched),
        'arms': list(v219_read.labels(bench)), 'measurements': measured, 'cost_by_arm': cost_by_arm,
        'cross_coverage': coverage,
        'request_reuse': v218_read.counts(first_cells, planned) if planned is not None else None,
        'settled_tokens': sum(send.get('charged', 0) for row in dispatched for send in row['sends']),
        'parsed': parsed, 'first_response_confirmed': True, 'sealed_reads': 0,
        'source_kind': 'authored_fixture' if bench in ('officeqa', 'spreadsheetbench') else 'reserved_smoke'}


def measured_prices(row, bench):
    """Validate all cross shapes and conservatively price dispatched card/procedure arms."""
    labels = v219_read.labels(bench)
    coverage = row.get('cross_coverage', {})
    measured = row.get('measurements', {})
    per_arm = measured.get('per_arm', {}).get(bench, {})
    require(row.get('passed') is True and row.get('arms') == list(labels)
            and row.get('items') == v.S2_ITEMS[bench] and row.get('cells') == v.S2_ITEMS[bench] + 6
            and set(coverage) == set(labels) and row.get('sealed_reads') == 0
            and row.get('first_response_confirmed') is True,
            'Cross SE6 requires every arm on practice items before launch')
    for label in labels:
        entry = coverage[label]
        require(entry.get('cells') == 1 and isinstance(entry.get('cell'), str) and entry['cell']
                and entry.get('card_source') == v219_read.card_source(bench, label),
                'Cross S2 records each arm and its registered card source')
        if entry.get('shared_with') is None:
            require(per_arm.get(label, {}).get('cells') == (v.S2_ITEMS[bench] if label == 'C' else 1)
                    and per_arm[label].get('tokens', 0) > 0
                    and isinstance(entry.get('request_sha256'), list) and entry['request_sha256'],
                    'Every dispatched cross shape has measured usage and request hashes')
        else:
            annotation = entry.get('request_reuse')
            source_label = entry.get('source_arm')
            require(bench in reuse.BENCHES and source_label in labels and source_label != label
                    and isinstance(annotation, dict) and annotation.get('version') == v219_read.VERSION
                    and annotation.get('source_arm') == annotation.get('planned_source_arm') == source_label,
                    'Shared cross smoke shapes retain request reuse attribution')
            source = coverage[source_label]
            identity = annotation.get('identity')
            require(isinstance(identity, dict) and identity == annotation.get('source_identity')
                    and identity.get('fault_free') is True and source.get('shared_with') is None
                    and entry['shared_with'] == source.get('cell')
                    and source.get('request_sha256') and source['request_sha256'][0] == identity.get('request_sha256'),
                    'Shared cross smoke identity matches the fault-free request its actual source sent')
    costs = row.get('cost_by_arm', {})
    require(set(costs) == set(per_arm), 'Cross S2 binds each dispatched arm cost')
    prices = {'card': [], 'procedure': []}
    for label, groups in costs.items():
        require(set(groups) <= set(prices) and groups, 'Measured solver cost classes')
        require(sum(entry['cells'] for entry in groups.values()) == per_arm[label]['cells']
                and sum(entry['tokens'] for entry in groups.values()) == per_arm[label]['tokens'],
                'Per-arm cost classes sum to the measured usage')
        for kind, entry in groups.items():
            require(entry['cells'] > 0 and entry['tokens'] > 0, 'Positive dispatched usage')
            prices[kind].append(Fraction(entry['tokens'], entry['cells']))
    require(prices['card'], 'Cross smoke includes measured C card cells')
    card = max(prices['card'])
    procedure = max([card * p.PROCEDURE_ARM_FACTOR[1], *prices['procedure']])
    return {'card': str(card), 'procedure': str(procedure), 'procedure_assumed': not bool(prices['procedure']),
            'basis': 'maximum dispatched per-arm class mean; procedure at least registered card factor'}
