"""main-v7's same-slice split, ordered merge, and best-single fallback.

Every subcandidate is immutable, and every reused cell retains its actual source.
The original confirmation decision consumes the slice; these units explicitly bind
to that decision rather than pretending that its items are fresh a second time.
"""
from __future__ import annotations

from fractions import Fraction
import re

from skillopt.continual_eval.core import read_json, require, write_json

from . import confirm, profiles, reuse, rounds, solver, units, v221_learning, v221_rule
from .cells import Arm
from .errors import PackageInvalid
from .package import Package, save, validate

TRAIN_UNIT = re.compile(r"(?P<chain>[^/]+)/s(?P<k>\d+)-(?P<bench>[a-z]+)/train-r(?P<r>\d+)-split-(?:p[1-3]|merge)")


def _read_record(st, path, kind=None):
    if profiles.is_v226(profiles.configuration_of(st.setting)):
        from .v226_candidates import read_record
        return read_record(path, kind)
    value = read_json(path)
    return profiles.verified(value, kind) if kind is not None else value


def changed(incumbent, candidate):
    return [p for p in candidate.procedures if p.id not in incumbent.order]


def subcandidate(base, incumbent, candidate, procedure, changes, *, configuration=None):
    """Keep the exact candidate procedure, including its already-rebased lineage."""
    change = next((c for c in changes if c.get('id') == procedure.id), {})
    target = change.get('target') if change.get('kind') == 'revision' else None
    if target is None and procedure.lineage['revises'] in incumbent.order:
        target = procedure.lineage['revises']
    require(target is None or target in incumbent.order, 'Split revision names an incumbent procedure')
    procedures = tuple(procedure if p.id == target else p for p in incumbent.procedures)
    if target is None:
        procedures += (procedure,)
    kept = {p.id for p in procedures}
    scopes = {k: v for k, v in incumbent.narrowed.items() if k in kept}
    if profiles.is_v222(configuration) and procedure.id in candidate.narrowed:
        scopes[procedure.id] = candidate.narrowed[procedure.id]
    result = Package(procedures, candidate.step, candidate.evidence, base.sha256,
                     tuple(base.retired) + tuple(p.sha256 for p in base.procedures if p.id not in kept),
                     scopes,
                     {k: v for k, v in incumbent.describer.items() if k in kept})
    validate(result, base)
    return result


def counts(procedure, training=None, confirmation=None, *, reason=None):
    safe = confirm.counts_only((confirmation or {}).get('confirm', {}))
    verdict = (training or {}).get('verdict')
    return {'procedure': procedure,
            'training': ({'fixed': len(verdict['fixed']), 'broken': len(verdict['broken']), 'net': verdict['net']}
                         if verdict else None),
            'confirmation': ({k: safe[k] for k in ('fixed', 'broken', 'net')} if safe else None),
            'passed': bool(safe.get('passed')),
            'reason': reason or (safe.get('reason') if safe else verdict['reason'] if verdict else 'split_invalid')}


def counts_ok(rows):
    if not isinstance(rows, list) or not 2 <= len(rows) <= profiles.MAX_CHANGES:
        return False
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'procedure', 'training', 'confirmation', 'passed', 'reason'}
                or not isinstance(row['procedure'], str) or len(row['procedure']) > 80
                or type(row['passed']) is not bool
                or (row['reason'] is not None and (not isinstance(row['reason'], str) or len(row['reason']) > 200))):
            return False
        for name in ('training', 'confirmation'):
            value = row[name]
            if value is None:
                continue
            if (not isinstance(value, dict) or set(value) != {'fixed', 'broken', 'net'}
                    or any(type(value[k]) is not int or value[k] < 0 for k in ('fixed', 'broken'))):
                return False
            if name == 'confirmation':
                if type(value['net']) is not int or value['net'] != value['fixed'] - value['broken']:
                    return False
            else:
                if not isinstance(value['net'], str) or re.fullmatch(r'-?\d+/[1-9]\d*', value['net']) is None:
                    return False
    return True


def winner(rows):
    eligible = [i for i, row in enumerate(rows) if row['passed']]
    return max(eligible, key=lambda i: (rows[i]['confirmation']['net'], Fraction(rows[i]['training']['net']), -i)) \
        if eligible else None


def source_trajectories(st, cells, *, allow_confirmation=False):
    """Read exact training trajectories by source cell id, including earlier attempts."""
    wanted = {cell['cell']['id'] for rows in cells.values() for cell in rows}
    names = {cell['cell']['unit'].rsplit('/', 1)[-1] for rows in cells.values() for cell in rows}
    result = {}
    for name in sorted(names):
        require(name == 'run' or name.startswith('train-r') or (allow_confirmation and name.startswith('confirm-r')),
                'Split feedback never reads confirmation trajectories')
        root = units.unit_path(st.chain_root, st.k, st.bench, name)
        for path in sorted(root.glob('attempt-*/trajectories/*.json')):
            value = (_read_record(st, path, 'trajectory') if profiles.is_v226(profiles.configuration_of(st.setting))
                     else profiles.verified(read_json(path), 'trajectory'))
            if value['cell'] in wanted:
                result[value['cell']] = value
    return result


def _resume_cells(st, unit, binding):
    """A restarted split reuses only completed, fault-free cells of its pinned request plan."""
    from . import step
    root = units.unit_path(st.chain_root, st.k, st.bench, unit)
    plan = root / 'split-binding.json'
    if plan.exists():
        if profiles.is_v226(step.configuration_of(st.setting)):
            previous = _read_record(st, plan, 'v226-split-requests')
            require(previous['core'] == binding['core'], 'A split restart requires the same deterministic request core')
            binding = previous
        else:
            previous = read_json(plan)
            require(previous == binding, 'A split restart requires the same immutable request plan')
    else:
        write_json(plan, binding)
    result = {}
    for path in sorted(root.glob('attempt-*/cells/*.json')):
        cell = (_read_record(st, path, 'cell') if profiles.is_v226(step.configuration_of(st.setting))
                else profiles.verified(read_json(path), 'cell'))
        key, arm = cell['cell']['task_id'], cell['cell']['arm']
        if profiles.is_v222(step.configuration_of(st.setting)) and unit.startswith('confirm-r'):
            from . import v222_gate
            bench = cell['cell'].get('benchmark')
            if (bench in v222_gate.BENCHES and bench != st.bench
                    and cell['cell']['unit'] == st.label(unit) + '/cross-' + bench):
                pin = root / ('v222-cross-' + bench + '.json')
                require(pin.exists(), 'A cross-gate attempt cell has its immutable paired plan')
                cross = (_read_record(st, pin) if profiles.is_v226(step.configuration_of(st.setting))
                         else read_json(pin))
                require(cross.get('configuration') == step.configuration_of(st.setting)
                        and cross.get('phase') == 'confirmation' and cross.get('bench') == bench
                        and cross.get('parent_sha256') == binding['incumbent_sha256']
                        and cross.get('candidate_sha256') == binding['candidate_sha256']
                        and key in cross.get('items', ()) and arm in ('S', "S'")
                        and cell['cell'].get('run') == 0
                        and cell['cell'].get('id') == step.cell_id(cell['cell']['unit'], arm, key, 0),
                        'A cross-gate attempt cell belongs to its immutable paired plan')
                continue  # The cross gate resumes these cells under its own bound plan.
        require(cell['cell']['unit'] == st.label(unit) and key in binding['items']
                and arm in ('S', "S'") and cell['cell'].get('run') == 0,
                'A split attempt cell belongs to its immutable one-run plan')
        if step._confirm_cell_reusable(cell, key):
            result[(arm, key)] = cell
    return result


def evaluate(st, cut, r, n, incumbent, candidate, full, source, generated, *, confirmation=False, current=None):
    """Same item sets and verdicts, one run per item, with explicit cell provenance."""
    from . import step
    configuration = step.configuration_of(st.setting)
    require(profiles.is_v221(configuration), 'Procedure splitting belongs only to main-v7')
    unit = '%s-r%d-split-%s' % ('confirm' if confirmation else 'train', r, 'merge' if n == 'merge' else 'p%d' % n)
    name = st.label(unit)
    prior = st.done(unit)
    require(prior is None or (prior['candidate_sha256'] == candidate.sha256
            and prior['incumbent_sha256'] == incumbent.sha256 and prior['full_candidate_sha256'] == full.sha256),
            'A completed split resumes only with the same candidate, incumbent and original candidate')

    def work(attempt):
        if confirmation:
            selected = cut.get('confirm-r%d' % r, cut.get('confirm', ()))
            items = {rounds.key(st.bench, item['task_id']): item for item in selected}
            made, publics = {}, {key: item['public'] for key, item in items.items()}
            require([item['task_id'] for item in selected] == source['slice_ids'],
                    'Split confirmation re-tests exactly the original decision slice')
        else:
            items, made, publics = step._training_publics(cut, generated, st.bench)
        views = [(key, solver.routing_view(st.bench, public, runtime=st.runtime())) for key, public in publics.items()]
        fixed = profiles.is_v226(configuration)
        if fixed:
            plan = units.unit_path(st.chain_root, st.k, st.bench, unit) / 'split-binding.json'
            core = step._request_core(st, round=r, ids=list(publics), candidate=candidate, incumbent=incumbent,
                                      full=full, views=views, publics=publics)
            core.update(unit=unit, confirmation=confirmation)
        if fixed and plan.exists():
            binding = _read_record(st, plan, 'v226-split-requests')
            require(binding['core'] == core, 'A split restart requires the same deterministic request core')
            before, after = step._restore_routes(binding['before']), step._restore_routes(binding['after'])
            evaluated, signatures = binding['items'], binding['request_signatures']
            captured, observed = binding['captured'], binding['observed']
            identical = binding['identical']
            full_signatures = source.get('request_signatures') or {}
        else:
            before, after = step._routes(st, incumbent, views, publics), step._routes(st, candidate, views, publics)
            evaluated = [key for key, _ in views]
            captured, observed = {}, {} if profiles.uses_v215(configuration, st.bench) and not confirmation else None
            signatures = step._pair_signatures(st, candidate, incumbent, publics,
                        [(key, view) for key, view in views if key in evaluated],
                        **({'note_coverage': captured} if not confirmation else {}),
                        **({'diagnostics_observer': observed} if observed is not None else {}))
            full_signatures = source.get('request_signatures') or {}
            identical = [key for key in evaluated if reuse.interchangeable(signatures[key]["S'"], signatures[key]['S'], bench=st.bench)]
            binding = {'configuration': configuration, 'round': r, 'incumbent_sha256': incumbent.sha256,
                       'candidate_sha256': candidate.sha256, 'full_candidate_sha256': full.sha256,
                       'items': list(publics), 'request_signatures': signatures,
                       'original_decision_unit': st.label('confirm-r%d' % r) if confirmation else None}
            if fixed:
                from .v226_bindings import json_observations
                captured, observed = json_observations(captured), json_observations(observed)
                binding = profiles.record('v226-split-requests', st.evidence, {**binding, 'core': core,
                    'before': {key: row.to_json() for key, row in before.items()},
                    'after': {key: row.to_json() for key, row in after.items()},
                    'captured': captured, 'observed': observed, 'identical': identical})
        resumed = _resume_cells(st, unit, binding)
        cells, rules, jobs = {}, {}, []
        for key in evaluated:
            if key in identical:
                rules[key] = {arm: {'rule': 'identical_to_incumbent', 'source': None,
                                   'identity': signatures[key]['S']} for arm in ('S', "S'")}
                continue
            rules[key] = {}
            for arm, kind, package, side in (('S', 'parent', incumbent, 'incumbent'), ("S'", 'candidate', candidate, 'candidate')):
                saved = source.get(side + '_cells', {}).get(key)
                if isinstance(saved, list):
                    saved = next((c for c in saved if c['cell'].get('run', 0) == 0), None)
                matches = reuse.interchangeable(signatures[key][arm], full_signatures.get(key, {}).get(arm, {}), bench=st.bench)
                cell, rule = resumed.get((arm, key)), 'resumed'
                if cell is None and saved and matches and step._confirm_cell_reusable(saved, key):
                    cell, rule = saved, 'reused_incumbent' if arm == 'S' else 'identical_to_candidate'
                rules[key][arm] = {'rule': rule if cell else 'dispatched',
                                    'source': cell['cell']['id'] if cell else None,
                                    'identity': signatures[key][arm]}
                if cell:
                    cells[(arm, key)] = [cell]
                else:
                    item = items.get(key)
                    task = ({'benchmark': st.bench, 'public': item['public'], 'private': item['private']}
                            if item is not None else step._task(made[key]))
                    jobs.append((arm, Arm(kind, package), key, 0, task))
        if fixed:
            found = step._system_cells(st, attempt, st.solver('confirm' if confirmation else 'selftest', attempt), name, jobs,
                                tag='split-confirm' if confirmation else 'split-train') if jobs else []
        else:
            found = step._cells(st, attempt, st.solver('confirm' if confirmation else 'selftest', attempt), name, jobs,
                                tag='split-confirm' if confirmation else 'split-train') if jobs else []
        for cell in found:
            arm, key = cell['cell']['arm'], cell['cell']['task_id']
            cells[(arm, key)] = [cell]
            rules[key][arm]['source'] = cell['cell']['id']
        diagnostic = v221_learning.infrastructure(cells)
        routed = {key: {'incumbent': list(before[key].enabled), 'candidate': list(after[key].enabled)} for key, _ in views}
        out = {'round': r, 'incumbent_sha256': incumbent.sha256, 'candidate_sha256': candidate.sha256,
               'full_candidate_sha256': full.sha256,
               'cells': len(found), 'cell_rules': rules, 'request_signatures': signatures, 'identical': identical,
               'incumbent_cells': {key: rows for (arm, key), rows in cells.items() if arm == 'S'},
               'candidate_cells': {key: rows for (arm, key), rows in cells.items() if arm == "S'"}}
        if confirmation:
            result = v221_learning.confirmation_verdict(cells, evaluated, signatures, bench=st.bench, items=len(items),
                                                       configuration=configuration)
            result.update(reused_cells=sum(rule['rule'] != 'dispatched' for row in rules.values() for rule in row.values()),
                          tokens=confirm.tokens(found), exercise=False)
            out.update(confirm=result, procedure_confirmation=v221_learning.confirmation_counts(st, cells, publics, views, signatures, incumbent, candidate), slice_ids=[item['task_id'] for item in selected],
                       selection_check='preregistered_split_of_original_decision')
        else:
            changed_ids = {p.id for p in changed(incumbent, candidate)}
            verdict = step.train_verdict(cells, [key for key in evaluated if key in items],
                [key for key in evaluated if key in made], changed_ids,
                predicate_faults=sum(f.get('procedure') in changed_ids for key, _ in views for f in after[key].faults),
                routed=len(views), sign=step.TRAIN_SIGN[configuration],
                request_faults=[key for key, arms in signatures.items() if any(f.get('procedure') in changed_ids for f in arms["S'"]['faults'])],
                configuration=configuration, identical=identical, runs=1,
                touched=v221_rule.identity_touched(signatures, bench=st.bench,
                    trajectories=v221_learning._cell_trajectories(cells)))
            telemetry = {}
            coverage = {key: {'request_sha256': signatures[key]["S'"]['request_sha256'],
                              'fields': captured[key]["S'"]} for key in identical if key in items}
            if st.bench == 'zebralogic':
                for key, arms in rules.items():
                    if key in items and arms["S'"]['rule'] == 'identical_to_candidate':
                        # The source trajectory belongs to the full candidate. Its empty/dropped notes can
                        # name procedures absent from this subcandidate even when the delivered request is equal.
                        coverage[key] = {'request_sha256': signatures[key]["S'"]['request_sha256'],
                                         'fields': captured[key]["S'"], 'candidate_sha256': candidate.sha256,
                                         'source_cells': [arms["S'"]['source']]}
            feedback = step._feedback(st, cut, unit, verdict, routed, incumbent, candidate, cells,
                source_trajectories(st, cells), current=current or [],
                note_coverage=coverage,
                **({'diagnostics_observations': observed, 'diagnostics_telemetry': telemetry} if observed is not None else {}))
            out.update(learning=step.TRAIN, adopted=verdict['adopted'], verdict=verdict, feedback=feedback)
            v221_learning.attach_training(st, out, cells, publics, views, signatures, incumbent, candidate)
            if observed is not None:
                from . import diagnostics_feedback
                out.update(diagnostics_feedback.telemetry(telemetry))
        out['infrastructure'] = diagnostic
        if profiles.is_v222(configuration) and confirmation:
            from . import v222_runtime
            out = v222_runtime.confirmation(st, attempt, unit=unit, parent=incumbent,
                                            candidate=candidate, result=out)
        return out

    if profiles.is_v226(configuration):
        def rejected(event):
            result = (step._candidate_confirmation_error(st, r, incumbent, candidate, event) if confirmation else
                      step._candidate_training_error(st, r, incumbent, candidate, event))
            return {**result, 'full_candidate_sha256': full.sha256}
        key = 'procedure-r%d-split-%s' % (r, 'merge' if n == 'merge' else 'p%d' % n)
        work = step._candidate_guard(st, key, incumbent, work, rejected)
    return st.unit(unit, work)


def run(st, cut, r, incumbent, candidate, engineered, training, confirmation, generated, *, current, evaluator=None):
    """Keep every passing subcandidate in order; merged failure keeps best single."""
    from . import step
    evaluator = evaluate if evaluator is None else evaluator
    child = profiles.is_v222(step.configuration_of(st.setting))
    result = step._confirmed_training(training, confirmation,
        **({'configuration': step.configuration_of(st.setting)}
           if profiles.is_v226(step.configuration_of(st.setting)) else {}))
    procedures = changed(incumbent, candidate)
    if (not profiles.is_v221(step.configuration_of(st.setting)) or not training['adopted']
            or confirmation['confirm']['passed'] or len(procedures) < 2
            or (profiles.is_v226(step.configuration_of(st.setting)) and confirmation.get('candidate_error'))
            or confirmation['confirm'].get('reason') == 'confirmation_pool_exhausted'):
        return candidate, result
    require(len(procedures) <= profiles.MAX_CHANGES, 'Split count stays within the registered change cap')
    rows, packages, evaluations = [], [], []
    changes = engineered['engineer']['changes']
    for n, procedure in enumerate(procedures, 1):
        try:
            sub = subcandidate(st.parent, incumbent, candidate, procedure, changes,
                               **({'configuration': step.configuration_of(st.setting)} if child else {}))
        except (PackageInvalid, ValueError):
            rows.append(counts(procedure.id, reason='split_invalid'))
            packages.append(None)
            evaluations.append(None)
            continue
        save(st.chain_root, sub)
        train = evaluator(st, cut, r, n, incumbent, sub, candidate, training, generated, current=current)
        held = (evaluator(st, cut, r, n, incumbent, sub, candidate, confirmation, generated, confirmation=True)
                if train['adopted'] else None)
        if child and held is not None and (not profiles.is_v226(step.configuration_of(st.setting))
                or 'cross_gate' in held and not held.get('candidate_error')):
            from . import v222_runtime
            sub = v222_runtime.confirmed_candidate(st, sub, held)
            train = v222_runtime.bind_training(train, sub, held)
        rows.append(counts(procedure.id, train, held))
        packages.append(sub)
        evaluations.append(step._confirmed_training(train, held,
            **({'configuration': step.configuration_of(st.setting)}
               if profiles.is_v226(step.configuration_of(st.setting)) else {})) if held else train)
    chosen = winner(rows)
    passing = [i for i, row in enumerate(rows) if row['passed']]
    merged_check = None
    selected_ids = []
    if chosen is not None:
        selected, result = packages[chosen], evaluations[chosen]
        selected_ids = [procedures[chosen].id]
        result = {**result, 'training_unit': 'train-r%d-split-p%d' % (r, chosen + 1),
                  'confirmation_unit': 'confirm-r%d-split-p%d' % (r, chosen + 1)}
        # Merge all passing changes in their registered order. Even a two-change
        # merge receives one train and one confirmation check on those same items.
        if len(passing) > 1:
            merged = incumbent
            try:
                for i in passing:
                    merged = subcandidate(st.parent, merged, packages[i] if child else candidate, procedures[i], changes,
                                          **({'configuration': step.configuration_of(st.setting)} if child else {}))
            except (PackageInvalid, ValueError):
                merged = None
                merged_check = counts('merged', reason='split_merge_invalid')
            if merged is not None:
                save(st.chain_root, merged)
                train = evaluator(st, cut, r, 'merge', incumbent, merged, candidate, training, generated, current=current)
                held = (evaluator(st, cut, r, 'merge', incumbent, merged, candidate, confirmation,
                                  generated, confirmation=True) if train['adopted'] else None)
                if child and held is not None and (not profiles.is_v226(step.configuration_of(st.setting))
                        or 'cross_gate' in held and not held.get('candidate_error')):
                    from . import v222_runtime
                    merged = v222_runtime.confirmed_candidate(st, merged, held)
                    train = v222_runtime.bind_training(train, merged, held)
                merged_check = counts('merged', train, held)
                if held and held['confirm']['passed']:
                    selected, result = merged, step._confirmed_training(train, held,
                        **({'configuration': step.configuration_of(st.setting)}
                           if profiles.is_v226(step.configuration_of(st.setting)) else {}))
                    selected_ids = [procedures[i].id for i in passing]
                    result = {**result, 'training_unit': 'train-r%d-split-merge' % r,
                              'confirmation_unit': 'confirm-r%d-split-merge' % r}
        candidate = selected
    result = {**result, **{key: training[key] for key in ('proposed_sha256', 'pruned') if key in training},
              'split': rows, 'split_winner': rows[chosen]['procedure'] if chosen is not None else None,
              'split_adopted': selected_ids, 'split_merge': merged_check}
    require(counts_ok(rows), 'Only split counts cross into engineer history')
    return candidate, result
