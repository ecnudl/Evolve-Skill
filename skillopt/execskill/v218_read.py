"""main-v6 read-only request classes and the registered identical-request analysis."""
from __future__ import annotations

from collections import Counter
from contextlib import nullcontext
from fractions import Fraction

from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from . import notes, profiles as p, reuse, solver
from .cells import Arm

VERSION = 'main-v6-read-request-reuse-v1'


def public_identity(identity):
    """Persist hashes only: neither rendered notes nor post-call binding values."""
    return {'request_sha256': identity['request_sha256'],
            'post_call_sha256': digest(identity['post_call']), 'fault_free': not identity['faults']}


def representatives(identities, labels, *, bench):
    running, sources = [], {}
    for label in labels:
        source = next((other for other in running if reuse.interchangeable(
            identities[label], identities[other], bench=bench)), None)
        sources[label] = source
        if source is None and label != 'B':
            running.append(label)
    return sources


def plan(base, arms, packages, *, bench, context, workers):
    """C wins, then running F/stage representatives; B never represents another arm."""
    from . import evaluation
    require((context.configuration == p.MAIN_V6 or p.is_v219(context.configuration)) and bench in reuse.BENCHES,
            'Request-class read planning belongs only to main-v6 request-identity benches')
    cross = p.is_v219(context.configuration)
    if cross:
        from . import v219_read
        require(not packages, 'Cross reads have no stage packages')
    labels = (['C', 'F', *v219_read.cross_labels(bench), 'B'] if cross else
              ['C', 'F', *sorted(packages, key=lambda label: int(label[1:])), 'B'])
    chosen = {**arms, **{label: Arm('candidate', package) for label, package in packages.items()}}
    require(set(chosen) == set(labels) and all(isinstance(arm, Arm) for arm in chosen.values()),
            'The main-v6 read has plain C/F/B and stage arms')
    tasks = {task['task_id']: task for task in base['tasks']}
    workers = evaluation.mounting(workers, evaluation.public_inputs(bench, tasks))
    identities, routes, sources, planning_metadata = ({label: {} for label in labels} for _ in range(4))
    for item in sorted(tasks):
        view = solver.routing_view(bench, tasks[item]['public'], runtime=context.runtime[bench])
        for label in labels:
            arm = chosen[label]
            captured = []
            factory = workers(arm.package, item) if arm.package.for_bench(bench) else nullcontext(None)
            with factory as worker:
                identity = reuse.signature(bench, arm.package, view, worker,
                    card_text=(v219_read.card_text(context, bench, label) if cross else
                               '' if arm.kind == 'blank' else context.cards.get(bench, '')),
                    runtime=context.runtime[bench], configuration=context.configuration,
                    note_observer=lambda shell, text: captured.append((shell.route, {
                        'keyword_hits': notes.keyword_summary([row for entry in shell.notes
                                                               for row in entry['dropped']])})))
            identities[label][item] = identity
            routes[label][item], planning_metadata[label][item] = captured[0]
        chosen_sources = representatives({label: identities[label][item] for label in labels}, labels, bench=bench)
        for label in labels:
            sources[label][item] = chosen_sources[label]
    summary = {'version': v219_read.VERSION if cross else VERSION, 'sources': sources, 'planning_metadata': planning_metadata,
        'identities': {label: {item: public_identity(identity) for item, identity in entries.items()}
                       for label, entries in identities.items()}}
    if cross:
        summary['card_sources'] = {label: v219_read.card_source(bench, label) for label in labels}
        summary['card_sha256'] = {label: digest(v219_read.card_text(context, bench, label)) for label in labels}
    return {**summary, 'identities': identities, 'routes': routes, 'arms': chosen, 'sha256': digest(summary),
            'staged': {'routes': {label: routes[label] for label in packages},
                       'sources': {label: sources[label] for label in packages},
                       'derived': {label: 0 for label in packages}, 'sha256': digest(summary)}}


def shareable(source, identity):
    """A zero-call identity must match the fault-free cell actually dispatched."""
    calls = source.get('logical_calls') or []
    return bool(source.get('shared_with') is None and source.get('stop') is None
                and source.get('final') is not None and not source.get('faults')
                and list(source.get('enabled') or []) == identity.get('enabled')
                and calls and calls[0].get('request_sha256') == identity.get('request_sha256'))


def checked_match(configuration, bench, source, value):
    require((configuration == p.MAIN_V6 or p.is_v219(configuration)) and isinstance(value, dict)
            and reuse.interchangeable(value.get('identity'), value.get('source_identity'), bench=bench)
            and shareable(source, value['source_identity']),
            'main-v6 shares only a fault-free, interchangeable request that its source actually sent')
    return value


class Store:
    """Annotate every logical cell, preserving the frozen store's hash-only boundary."""
    def __init__(self, store, planned):
        self.store, self.planned, self.fallback = store, planned, set()

    def __getattr__(self, name):
        return getattr(self.store, name)

    def save(self, value, trajectory):
        cell = value['cell']
        label, item = cell['arm'], cell['task_id']
        source = self.planned['sources'][label][item]
        fallback = cell['id'] in self.fallback
        reason = ('source_not_reusable' if fallback else 'dispatched' if source is None else
                  'identical_to_C' if source == 'C' else 'identical_to_F' if source == 'F' else
                  'identical_to_cross' if source.startswith('X_') else 'identical_to_stage')
        identity = self.planned['identities'][label][item]
        fields = {key: found for key, found in value.items() if key not in ('version', 'evidence', p.RECORD_HASH)}
        fields['request_reuse'] = {'version': self.planned['version'], 'plan_sha256': self.planned['sha256'],
            'reason': reason, 'identity': public_identity(identity),
            'source_arm': None if fallback else source, 'planned_source_arm': source,
            'source_identity': (public_identity(self.planned['identities'][source][item])
                                if source is not None and not fallback else None)}
        return self.store.save(p.record('cell', value['evidence'], fields), trajectory)


def linked(context, jobs, sources, planned, *, store):
    """Representatives have run in the normal blocks; unsafe sources dispatch the target."""
    from .cells import share_cell, share_same
    fallback = []
    for (cell, task, arm), source_label in jobs:
        label, item, run = cell['arm'], cell['task_id'], cell['run']
        source = sources[(source_label, item, run)]
        original = planned['identities'][source_label][item]
        if not shareable(source, original):
            store.fallback.add(cell['id'])
            fallback.append((cell, task, arm))
            continue
        identity = {'identity': planned['identities'][label][item], 'source_identity': original,
                    'planning_metadata': planned['planning_metadata'][label][item]}
        route = planned['routes'][label][item].to_json()
        if source_label == 'C':
            share_cell(context, cell, task, arm, source, route, store=store, request_reuse=identity)
        else:
            share_same(context, cell, task, arm, source, route,
                planned['routes'][source_label][item].to_json(), planned['arms'][source_label].package,
                store=store, request_reuse=identity)
    return fallback


def counts(cells, planned):
    shared = [row for row in cells if row['shared_with'] is not None]
    return {'version': planned['version'], 'plan_sha256': planned['sha256'], 'shared_cells': len(shared),
            'shared_cells_by_reason': dict(sorted(Counter(row['request_reuse']['reason'] for row in shared).items())),
            'dispatched_cells': len(cells) - len(shared),
            'fallback_cells': sum(row['request_reuse']['reason'] == 'source_not_reusable' for row in cells)}


def request_hashes(cells, arm, item, run):
    """Resolve a shared cell to the actually dispatched request sequence."""
    visited = set()
    while arm not in visited:
        visited.add(arm)
        value = cells[(arm, item, run)]
        if value.get('shared_with') is None:
            hashes = value.get('request_sha256') or []
            return hashes if hashes and all(isinstance(h, str) and h for h in hashes) else None
        arm = value.get('shared_arm') or 'C'
    return None


def identical_item(cells, first, second, item):
    from . import readout as r
    runs = r._runs(cells, first, item)
    if not runs or runs != r._runs(cells, second, item):
        return False
    return all((own := request_hashes(cells, first, item, run)) is not None
               and own == request_hashes(cells, second, item, run) for run in runs)


def contrast(cells, first, second, items, **options):
    """The registered second analysis: complete byte-identical requests contribute zero."""
    from . import readout as r
    values = r.differences(cells, first, second, items)
    tied = [identical_item(cells, first, second, item) for item in items]
    return {**r.estimate([Fraction(0) if tie else value for value, tie in zip(values, tied)],
                       design=r._design(cells, items), **options), 'identical_request_items': sum(tied)}


def secondary(units, rows):
    """All registered pairwise contrasts, exact request ties, beside the unchanged primary."""
    from . import readout as r

    contrasts, stages = {}, {}
    for bench, cells in units.items():
        contrasts[bench] = {a + '-' + b: contrast(cells, a, b, r._items(cells, a, b),
            bootstrap=True, sensitivity=True) for a, b in (('F', 'C'), ('C', 'B'), ('F', 'B'))}
        items = r._items(cells, *sorted(set(rows)))
        stages[bench] = []
        for k, arm in enumerate(rows):
            entry = {'k': k, 'arm': arm, 'n': len(items)}
            if arm == 'C':
                entry['minus_card'] = {'mean': 0.0, 'reading': 'no program accepted at this step'}
            elif len(items) >= 2:
                entry['minus_card'] = contrast(cells, arm, 'C', items, bootstrap=True)
            if k and rows[k - 1] != arm and len(items) >= 2:
                entry['minus_previous'] = contrast(cells, arm, rows[k - 1], items, bootstrap=True)
            stages[bench].append(entry)
    return {'rule': 'items with byte-identical solver request sequences count as ties',
            'conclusions_follow': 'primary', 'contrasts': contrasts, 'stages': stages}


def structural_demo():
    """Authored zero-call SX fixture through the same read representative planner."""
    labels = ['C', 'F', 'S1', 'S2', 'S3', 'B']
    own = lambda text, enabled=(): {'request_sha256': digest(text), 'post_call': [], 'faults': [],
                                   'enabled': list(enabled)}
    scenarios = {
        'silent_enabled': {'C': own('card'), 'F': own('card', ['silent']),
                          'S1': own('card', ['silent-stage']), 'S2': own('note', ['first']),
                          'S3': own('note', ['other-procedure']), 'B': own('blank')},
        'same_F': {'C': own('card'), 'F': own('note', ['first']), 'S1': own('note', ['revised']),
                   'S2': own('other', ['second']), 'S3': own('other', ['third']), 'B': own('blank')},
    }
    found = {name: representatives(identities, labels, bench='officeqa')
             for name, identities in scenarios.items()}
    require(found == {
        'silent_enabled': {'C': None, 'F': 'C', 'S1': 'C', 'S2': None, 'S3': 'S2', 'B': None},
        'same_F': {'C': None, 'F': None, 'S1': 'F', 'S2': None, 'S3': 'S2', 'B': None}},
        'The main-v6 structural read exercises C, F, stage and distinct request classes')
    return {'passed': True, 'model_calls': 0, 'sealed_reads': 0, 'sources': found,
            'evidence': 'engineering_fixture', 'benchmark_effect_evidence': False}
