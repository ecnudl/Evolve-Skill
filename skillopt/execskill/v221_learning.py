"""main-v7's fresh immediate acceptance and counts-only learning decisions.

Only the already allocated practice/acceptance slices enter this module. Routing
reads public views only, and selection never invokes a solver or opens a panel.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from skillopt.continual_eval.core import read_json, require, write_json
from . import profiles as p, rounds, reuse, solver
from .package import restore, save, validate, withhold

TARGET_TOUCHED = 60


def infrastructure(cells, arms=('S', "S'")):
    """The unchanged round J5 count, explicitly diagnostic for this child."""
    result = {}
    for arm in arms:
        rows = [cell for (side, _), found in cells.items() if side == arm for cell in found]
        count = rounds._infrastructure(rows)
        result[arm] = {'unknown': count, 'cells': len(rows),
                       'passed': count <= p.INFRA_UNKNOWN_MAX * len(rows)}
    return {'J5': result, 'warnings': ['J5:' + arm for arm, row in result.items() if not row['passed']],
            'deciding': False}


def _cell_trajectories(cells):
    """Keep the evaluated arm/item identity beside its recorded callback effects."""
    return [{**row, 'task_id': key, 'arm': arm}
            for (arm, key), rows in cells.items() for row in rows]


def _procedure_comparison(incumbent, candidate, pid):
    before, after = pid in incumbent.order, pid in candidate.order
    return {'candidate_sha256': candidate.sha256, 'incumbent_sha256': incumbent.sha256,
            'procedure_sha256': (candidate if after else incumbent).get(pid).sha256,
            'candidate_present': after, 'incumbent_present': before,
            'direction': ('candidate_present_vs_incumbent_absent' if not before else
                          'candidate_absent_vs_incumbent_present' if not after else
                          'candidate_narrowed_vs_incumbent_previous_scope')}


def per_procedure_touched(st, incumbent, candidate, publics, views, signatures, *, trajectories=()):
    """Public identities with one addition withheld or its previous scope restored.

This attributes overlapping notes to every contributing procedure; these are
coverage counts, never disjoint causal-effect estimates.
    """
    from . import step, v221_rule
    before, after = set(incumbent.order), set(candidate.order)
    changed = [pid for pid in candidate.order if pid not in before]
    changed += [pid for pid in incumbent.order if pid not in after or
                set(candidate.narrowed.get(pid, ())) != set(incumbent.narrowed.get(pid, ()))]
    result = {}
    active = set(v221_rule.identity_touched(signatures, bench=st.bench, trajectories=trajectories))
    for pid in changed:
        # Restore the incumbent's scope for deletion/narrowing. Withholding a
        # narrowed candidate would compare two packages that already omit P.
        if pid not in after:
            # Retired revisions also use the old source, which restore() does
            # not treat as a deletion. Keep its actual parent-arm effects.
            pairs = step._pair_signatures(st, incumbent, withhold(incumbent, [pid]), publics, views)
        else:
            reference = withhold(candidate, [pid]) if pid not in before else restore(candidate, incumbent, [pid])
            pairs = step._pair_signatures(st, candidate, reference, publics, views)
        effects = []
        for trace in trajectories:
            recorded = trace.get('post_call_effects')
            if recorded is None:
                recorded = v221_rule.post_call_effects(trace.get('shell') or {}, trace.get('calls') or ())
            effect = {**trace, 'post_call_effects': {pid: recorded[pid]} if pid in recorded else {}}
            if pid not in after:
                arm = trace.get('arm', (trace.get('cell') or {}).get('arm'))
                effect['arm'] = "S'" if arm == 'S' else 'S'
            effects.append(effect)
        result[pid] = [key for key in v221_rule.identity_touched(
            pairs, bench=st.bench, trajectories=effects) if key in active]
    return result


def attach_training(st, result, cells, publics, views, signatures, incumbent, candidate):
    from . import v221_rule
    trajectories = _cell_trajectories(cells)
    effects = v221_rule.identity_report(signatures, bench=st.bench, trajectories=trajectories)
    touched = effects['touched']
    own = per_procedure_touched(st, incumbent, candidate, publics, views, signatures, trajectories=trajectories)
    coverage = v221_rule.coverage(len(publics), touched, own)
    if p.is_v222(p.configuration_of(st.setting)):
        from . import v222_feedback
        coverage = v222_feedback.coverage(len(publics), touched, own, candidate, incumbent=incumbent)
    result['feedback']['coverage'] = coverage
    result['feedback']['rule'] = result['verdict']['rule']
    result.update(coverage=coverage, procedure_touched=own,
                  infrastructure=infrastructure(cells), touched=touched, request_effects=effects)
    return result


def confirmation_verdict(cells, evaluated, signatures, *, bench, items, configuration=None):
    from . import confirm, v221_rule
    effects = v221_rule.identity_report(signatures, bench=bench, trajectories=_cell_trajectories(cells))
    touched = effects['touched']
    # Legacy measured format fields are retained as diagnostics. Safe identical
    # skips alone are omitted from cells; faulted equal requests may dispatch.
    skipped = [key for key in evaluated if ('S', key) not in cells and ("S'", key) not in cells]
    result = confirm.verdict(cells, evaluated, identical=skipped, items=items)
    rule = v221_rule.decide(cells, evaluated, touched=touched)
    if p.is_v225(configuration):
        from .v225_phase import procedure_confirmation
        rule = procedure_confirmation(rule, configuration=configuration, items=items)
    result.update(fixed=rule['fixed'], broken=rule['broken'], net=rule['net'],
                  passed=rule['decision'] == 'accept', reason=None if rule['decision'] == 'accept' else 'gain_and_no_harm',
                  rule=rule, touched=touched, diagnostic_only=['format'], infrastructure=infrastructure(cells),
                  request_effects=effects)
    return result


def exhausted_confirmation(st, r, incumbent, candidate):
    """The frozen Zebra 40-item confirmation pool is consumed once, never recycled."""
    from . import v221_rule
    rule = v221_rule.counts(touched=0, fixed=0, broken=0, batch=0)
    result = {'items': 0, 'evaluated': 0, 'fixed': 0, 'broken': 0, 'net': 0,
              'format_cells': {"S'": 0, 'S': 0}, 'format_margin': 2, 'candidate_cells': 0,
              'passed': False, 'reason': 'confirmation_pool_exhausted', 'rule': rule, 'touched': [],
              'reused_cells': 0, 'tokens': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0},
              'exercise': False, 'diagnostic_only': ['format'], 'infrastructure': infrastructure({})}
    return st.unit('confirm-r%d' % r, lambda attempt: {'confirm': result, 'round': r,
        'incumbent_sha256': incumbent.sha256, 'candidate_sha256': candidate.sha256, 'slice_ids': [],
        'freshness': p.CONFIRM_FRESHNESS[p.MAIN_V7], 'selection_check': 'frozen_pool_exhausted',
        'cross_round_cache': False, 'procedure_confirmation': {}, 'routed': {}, 'routing': {},
        'identical': [], 'request_signatures': {}, 'request_identities': {}, 'reused': {}, 'cells': 0,
        'incumbent_cells': {}, 'candidate_cells': {}})


def confirmation_counts(st, cells, publics, views, signatures, incumbent, candidate):
    from . import v221_rule
    own = per_procedure_touched(st, incumbent, candidate, publics, views, signatures,
                                trajectories=_cell_trajectories(cells))
    return {pid: {**v221_rule.decide(cells, list(publics), touched=keys),
                  'comparison': _procedure_comparison(incumbent, candidate, pid)} for pid, keys in own.items()}


def select_acceptance(pool, signature, *, used=(), maximum, target=TARGET_TOUCHED):
    """Deterministic unseen prefix; ``signature(item)`` receives public-only data.

The selected prefix includes untouched items for the whole-batch denominator.
Every examined item is consumed on decision, so failed samples cannot recycle.
    """
    from . import v221_rule
    require(type(maximum) is int and maximum >= 0 and type(target) is int and target > 0,
            'A bounded fresh acceptance selection')
    ids = [item['task_id'] for item in pool]
    require(len(ids) == len(set(ids)), 'Distinct acceptance pool IDs')
    require(all(item.get('partition') not in ('test', 'sealed', 'holdout') for item in pool),
            'Immediate acceptance uses practice items only')
    seen, selected, touched, signatures = set(used), [], [], {}
    for item in pool:
        key = item['task_id']
        if key in seen:
            continue
        if len(selected) >= maximum or len(touched) >= target:
            break
        public = {'task_id': key, 'benchmark': item.get('benchmark'), 'public': item['public']}
        pair = signature(public)
        signatures[key] = pair
        selected.append(item)
        bench = item.get('benchmark')
        if v221_rule.identity_touched({key: pair}, bench=bench):
            touched.append(key)
    return {'selected': selected, 'touched': touched, 'request_signatures': signatures,
            'examined': [item['task_id'] for item in selected], 'maximum': maximum, 'target': target,
            'exhausted': len([key for key in ids if key not in seen]) <= len(selected)}


def immediate_acceptance(st, cut, r, incumbent, candidate, generated=None):
    """One immutable, disjoint selection and its normal charged acceptance unit."""
    from . import step
    configuration = p.configuration_of(st.setting)
    require(p.is_v221(configuration), 'Immediate acceptance belongs only to main-v7')
    # Engineer candidates stay rebased to the step's original parent. The
    # acceptance contrast alone points to the current incumbent; procedure
    # records (including post-call identity hashes) are byte-for-byte unchanged.
    contrast = replace(candidate, parent_sha256=incumbent.sha256)
    validate(contrast)
    save(st.chain_root, contrast)
    unit = 'accept-r%d' % r
    selection_path = st.root / ('accept-selection-r%d.json' % r)
    used = set()
    if p.is_v225(configuration):
        from .v225_phase import used_acceptance
        used.update(used_acceptance(st))
    for previous in range(1, r):
        path = st.root / ('accept-selection-r%d.json' % previous)
        if path.exists():
            previous_selection = (step._read_record(st, path, 'immediate-acceptance-selection')
                if p.is_v226(configuration) else p.verified(read_json(path), 'immediate-acceptance-selection'))
            used.update(previous_selection['examined'])
    pool = list(cut['accept'])
    by_id = {item['task_id']: item for item in pool}
    if p.is_v226(configuration):
        def select(*, read_only=False):
            if selection_path.exists():
                selection = step._read_record(st, selection_path, 'immediate-acceptance-selection')
                require(selection['incumbent_sha256'] == incumbent.sha256 and selection['candidate_sha256'] == candidate.sha256
                        and selection['contrast_candidate_sha256'] == contrast.sha256
                        and selection['pool_ids'] == list(by_id) and selection['previously_examined'] == sorted(used),
                        'Acceptance resume binds its original packages and fresh pool')
                selected = [by_id[key] for key in selection['examined']]
            else:
                require(not read_only, "A completed acceptance retains its sealed selection")
                def signature(item):
                    key, public = item['task_id'], item['public']
                    views = [(key, solver.routing_view(st.bench, public, runtime=st.runtime()))]
                    return step._pair_signatures(st, contrast, incumbent, {key: public}, views)[key]
                sampled = select_acceptance(pool, signature, used=used,
                    maximum=p.slice_spec(configuration, st.bench)['accept'][0])
                selected = sampled.pop('selected')
                selection = {**sampled, 'configuration': configuration, 'round': r,
                    'incumbent_sha256': incumbent.sha256, 'candidate_sha256': candidate.sha256,
                    'contrast_candidate_sha256': contrast.sha256, 'pool_ids': list(by_id), 'previously_examined': sorted(used), 'selection': 'public_request_identity_only'}
                selection = p.record('immediate-acceptance-selection', st.evidence, selection)
                write_json(selection_path, selection)
            require(not used & set(selection['examined']), 'Each immediate acceptance sample is fresh')
            return selected, selection
        # Selection executes inside accept-rN's protected work, before registration.
        # On resume the selection is read from its sealed record without rerouting.
        result = step._accept(st, cut, contrast, None, unit=unit, incumbent=incumbent, select=select)
        if result.get('candidate_error') or result.get('reason') == 'cross_bench_harm':
            return {**result, 'accepted': False, 'candidate_sha256': candidate.sha256,
                    'contrast_candidate_sha256': contrast.sha256}
        selected, selection = select(read_only=True)  # no sandbox work outside the unit
    else:
        if selection_path.exists():
            selection = p.verified(read_json(selection_path), 'immediate-acceptance-selection')
            require(selection['incumbent_sha256'] == incumbent.sha256 and selection['candidate_sha256'] == candidate.sha256
                    and selection['contrast_candidate_sha256'] == contrast.sha256
                    and selection['pool_ids'] == list(by_id) and selection['previously_examined'] == sorted(used),
                    'Acceptance resume binds its original packages and fresh pool')
            selected = [by_id[key] for key in selection['examined']]
        else:
            def signature(item):
                key, public = item['task_id'], item['public']
                views = [(key, solver.routing_view(st.bench, public, runtime=st.runtime()))]
                return step._pair_signatures(st, contrast, incumbent, {key: public}, views)[key]
            sampled = select_acceptance(pool, signature, used=used,
                maximum=p.slice_spec(configuration, st.bench)['accept'][0])
            selected = sampled.pop('selected')
            selection = {**sampled, 'configuration': configuration, 'round': r,
                'incumbent_sha256': incumbent.sha256, 'candidate_sha256': candidate.sha256,
                'contrast_candidate_sha256': contrast.sha256, 'pool_ids': list(by_id), 'previously_examined': sorted(used), 'selection': 'public_request_identity_only'}
            selection = p.record('immediate-acceptance-selection', st.evidence, selection)
            write_json(selection_path, selection)
        require(not used & set(selection['examined']), 'Each immediate acceptance sample is fresh')
        if not selected:
            return st.unit(unit, lambda attempt: {**step._release('acceptance_pool_exhausted'),
                'selection': selection, 'accepted': False})
        result = step._accept(st, {**cut, 'accept': selected, 'accept_probe': []}, contrast, None,
                              unit=unit, incumbent=incumbent)
    if p.is_v222(configuration) and result['decision'] == 'accept':
        from .package import load
        accepted_contrast = load(st.chain_root / 'packages' / (result['candidate_sha256'] + '.json'))
        accepted = replace(accepted_contrast, parent_sha256=candidate.parent_sha256)
        save(st.chain_root, accepted)
        binding = p.record('v222-acceptance-binding', st.evidence, {
            'selection_sha256': selection[p.RECORD_HASH], 'proposed_candidate_sha256': candidate.sha256,
            'incumbent_sha256': incumbent.sha256,
            'accepted_candidate_sha256': accepted.sha256,
            'accepted_contrast_candidate_sha256': accepted_contrast.sha256})
        write_json(st.root / ('v222-accepted-selection-r%d.json' % r), binding)
        return {**result, 'selection': selection, 'accepted': True,
                'accepted_binding': binding,
                'accepted_candidate_sha256': accepted.sha256,
                'candidate_sha256': accepted.sha256, 'contrast_candidate_sha256': accepted_contrast.sha256}
    return {**result, 'selection': selection, 'accepted': result['decision'] == 'accept',
            'candidate_sha256': candidate.sha256, 'contrast_candidate_sha256': contrast.sha256}


def apply_acceptance(incumbent, candidate, confirmed, acceptance):
    """Production adoption controller: failed fresh acceptance restores incumbent."""
    accepted = bool(confirmed['adopted'] and acceptance['decision'] == 'accept')
    result = dict(confirmed)
    reason = None if accepted else 'accept:' + str(acceptance.get('reason') or acceptance['decision'])
    safe = acceptance.get('rule')
    result.update(adopted=accepted, verdict={**confirmed['verdict'], 'adopted': accepted, 'reason': reason},
                  feedback={**confirmed['feedback'], 'adopted': accepted, 'reason': reason,
                            'early_acceptance': safe}, early_acceptance=safe)
    return (candidate if accepted else incumbent), result


def audit_confirmation(st, rounds_done, *, candidate=None):
    """Only bound, forward evidence for the retained procedure can establish harm.

    A deletion's candidate-minus-incumbent breaks favor retaining the procedure;
    they are recorded in that direction, never added to its own harm counts.
    """
    found = {}
    for line in rounds_done:
        r = line['round']
        # Count only the selected evaluation, not whole/split alternatives of the
        # same item set; otherwise one confirmation item would vote repeatedly.
        name = line.get('confirmation_unit', 'confirm-r%d' % r)
        result = st.done(name)
        for pid, row in (result or {}).get('procedure_confirmation', {}).items():
            comparison = row.get('comparison', {})
            if (comparison.get('direction') != 'candidate_present_vs_incumbent_absent'
                    or comparison.get('candidate_present') is not True
                    or comparison.get('incumbent_present') is not False
                    or comparison.get('candidate_sha256') != result.get('candidate_sha256')
                    or comparison.get('incumbent_sha256') != result.get('incumbent_sha256')
                    or not comparison.get('procedure_sha256')):
                continue
            if candidate is not None and (pid not in candidate.order or
                    comparison['procedure_sha256'] != candidate.get(pid).sha256):
                continue
            count = found.setdefault(pid, {'fixed': 0, 'broken': 0, 'touched': 0})
            for key in count:
                count[key] += row[key]
    return found


def structural_smoke(root):
    """Authored production decisions/controllers; no client, worker process or panel."""
    from contextlib import contextmanager
    from types import SimpleNamespace
    from . import acceptance, audit, step, v221_rule, v221_split
    from .package import Procedure, empty, with_
    from skillopt.validator_pilot.api import digest

    parent = empty(step='G/s1-searchqa', evidence='engineering_fixture')
    procedures = tuple(Procedure(id='fx-v221-' + name, origin='searchqa', accepted_at='G/s1-searchqa',
        description='Authored structural decision fixture', hooks=('applies', 'before_call'),
        source='def applies(view):\n    return True\ndef before_call(view, state):\n    return {"facts": ["Authored practice note."]}\n',
        header='', max_note_chars=200, requests_second_call=False, state_bytes=0, excluded_benches=(),
        replay_tests=(), lineage={'parent': None, 'revises': None, 'engineer_call': None},
        evidence='engineering_fixture') for name in ('first', 'second'))
    candidate = with_(parent, step='G/s1-searchqa', add=procedures)
    keys = ['authored-%d' % i for i in range(6)]
    views = {key: {'question': 'Authored question %d?' % i, 'context': ['Authored passage.']}
             for i, key in enumerate(keys)}

    class Worker:
        def call(self, pid, hook, args, *, timeout_s):
            value = True if hook == 'applies' else {'facts': ['Authored practice note.']}
            return {'ok': True, 'value': value, 'value_sha256': digest(value), 'cpu_ms': 0, 'rss_kib': 0}
        def ping(self):
            return {'ok': True}

    @contextmanager
    def workers(package, item):
        yield Worker()

    def cells_for(fixed, broken=0):
        return {(arm, key): [{'judge': {'v2': {'token': 'pass' if
            ((i < fixed and arm == "S'") or (fixed <= i < fixed + broken and arm == 'S')) else 'fail'}},
            'faults': [], 'final': {'outcome': 'pass', 'kind': 'score'}}]
            for i, key in enumerate(keys) for arm in ('S', "S'")}

    def training(fixed, broken=0):
        verdict = step.train_verdict(cells_for(fixed, broken), keys, [], set(candidate.order),
            predicate_faults=0, routed=len(keys), sign=False, identical=[], configuration=p.MAIN_V7, touched=keys)
        return {'adopted': verdict['adopted'], 'verdict': verdict, 'feedback': {}, 'cells': 12}

    identities = {key: {'S': reuse.signature('searchqa', parent, views[key], Worker(), card_text='Fixture card.'),
                        "S'": reuse.signature('searchqa', candidate, views[key], Worker(), card_text='Fixture card.')}
                  for key in keys}

    def confirmed(fixed, broken=0):
        return {'confirm': confirmation_verdict(cells_for(fixed, broken), keys, identities,
                                               bench='searchqa', items=len(keys))}

    sealed = acceptance.prepare(Path(root) / 'acceptance', chain='G-v7', bench='searchqa',
        step='G/s1-searchqa', unit='G/s1-searchqa/accept-r1', candidate=candidate, parent=parent,
        views=views, blocks={key: '1' for key in keys}, workers=workers, trajectories=[],
        rule=p.acceptance_rule(p.MAIN_V7, 'searchqa'), configuration=p.MAIN_V7,
        reuse={'card_text': 'Fixture card.', 'runtime': {}, 'views': {}})
    physical = []
    for n, job in enumerate(job for jobs in acceptance.schedule(sealed).values() for job in jobs):
        physical.append({'arm': job['arm'], 'task_id': job['item'], 'run': job['run'], 'set': job['set'],
            'judge': {'v2': {'token': 'pass' if job['arm'] == "S'" and keys.index(job['item']) < 3 else 'fail'},
                      'format': {'violation': False}, 'flags': []}, 'faults': [],
            'logical_calls': [{'purpose': 'first'}], 'worst_delivery': 'delivered',
            'sends': [{'receipt': {'ok': True}}], 'dispatch_ts': float(n), 'finish_ts': float(n + 1)})
    accepted = acceptance.decide(physical, sealed)
    trained, confirmation = training(3), confirmed(3)
    effective = step._confirmed_training(trained, confirmation)
    selected, adopted = apply_acceptance(parent, candidate, effective,
        {'decision': accepted['decision'], 'reason': accepted['reason'], 'rule': accepted['gain_and_no_harm']})
    decisions = {'training': trained['verdict']['rule'], 'confirmation': confirmation['confirm']['rule'],
                 'acceptance': accepted['gain_and_no_harm']}
    require(len({digest(row) for row in decisions.values()}) == 1 and decisions['training']['decision'] == 'accept',
            'The same production rule decides every stage')

    split_calls = []
    def evaluate(st, cut, r, n, incumbent, sub, full, source, generated, **kwargs):
        split_calls.append((n, bool(kwargs.get('confirmation'))))
        return confirmed(3) if kwargs.get('confirmation') else training(3)
    st = SimpleNamespace(parent=parent, chain_root=root, setting=SimpleNamespace(extra={'configuration': p.MAIN_V7}))
    merged, split_result = v221_split.run(st, {}, 1, parent, candidate,
        {'engineer': {'changes': [{'id': pid, 'kind': 'new', 'target': None} for pid in candidate.order]}},
        training(3), confirmed(0, 3), None, current=[], evaluator=evaluate)
    audit_result = {'confirmed': [{'procedure': procedures[0].id,
        'judges': {'G': {'truth': 'false'}, 'D': {'truth': 'false'}}}]}
    audit_decision = audit.v221_decisions(audit_result, list(candidate.order),
        {procedures[0].id: {'fixed': 3, 'broken': 0, 'touched': 6}})
    early = {'passed': selected.sha256 == candidate.sha256 and adopted['adopted'],
             'incumbent_sha256': parent.sha256, 'accepted_sha256': selected.sha256,
             'rule': adopted['early_acceptance']}
    split_check = {'passed': merged.order == candidate.order and split_result['adopted']
                   and ('merge', True) in split_calls and ('merge', False) in split_calls,
                   'adopted': split_result['split_adopted'], 'counts': split_result['split'],
                   'merged': split_result['split_merge']}
    non_drop = {'passed': all(row['decision'] == 'keep' for row in audit_decision), 'decisions': audit_decision}
    require(early['passed'] and split_check['passed'] and non_drop['passed'],
            'Immediate acceptance, ordered split merge, and audit non-drop are exercised')
    return {'passed': True, 'model_calls': 0, 'sealed_reads': 0, 'fixture_only': True,
            'decisions': decisions, 'early_acceptance': early, 'split_merge': split_check, 'audit_non_drop': non_drop}
