"""main-v8's practice-only, bounded cross-benchmark no-harm check.

Selection and routing do not call a solver. The orchestration supplies the
charged paired-cell runner; it receives only the fired items, once per gate.
Narrowing excludes harmful benches for new additions and proves identity again
without more solver calls. A revision/deletion which cannot be narrowed safely
is rejected rather than silently changing its incumbent behavior.
"""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
import hashlib
import json

from skillopt.coevo5.calls import _request_hash
from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest

from . import profiles as p, reuse, solver, v221_rule
from .package import edits, procedure_benches, validate

VERSION = 'cross-bench-no-harm-v2-22'
BENCHES = ('searchqa', 'officeqa', 'zebralogic', 'spreadsheetbench', 'alfworld')
HARM_ITEMS = {bench: 20 if bench == 'alfworld' else 60 for bench in BENCHES}
MIN_PRACTICE_ITEMS = 18
HARM_TAG = 'main-v8:fixed-practice-harm-slices'
MAX_PAIRED_ITEM_CALLS = 4 * 60 * 2


def _configuration(configuration):
    require(p.is_v222(configuration), 'The cross-bench gate belongs only to main-v8')


def harm_slices(practice_pools, *, seed=p.SEED, excluded=None, configuration='main-v8'):
    """Seeded available-count draws from practice, excluding own acceptance.

Run and confirmation practice allocations may be used. The registered actual
denominator is capped at sixty (twenty games) with an eighteen-item floor.
    """
    _configuration(configuration)
    require(set(practice_pools) == set(BENCHES), 'All five available practice pools are required')
    excluded = excluded or {}
    slices = {}
    for bench in BENCHES:
        rows = list(practice_pools[bench])
        require(all(isinstance(row, dict) and isinstance(row.get('task_id'), str)
                    and row.get('benchmark', bench) == bench and isinstance(row.get('public'), dict)
                    and row.get('partition') not in ('test', 'sealed', 'holdout', 'reserve')
                    for row in rows), 'Harm slices contain practice records of their bench only')
        ids = [row['task_id'] for row in rows]
        require(len(ids) == len(set(ids)), 'Distinct harm-slice pool items')
        held = set(excluded.get(bench, ()))
        available = [row for row in rows if row['task_id'] not in held]
        require(len(available) >= MIN_PRACTICE_ITEMS,
                'main-v8 practice_supply below minimum available 18 for ' + bench)
        slices[bench] = sorted(available, key=lambda row: hashlib.sha256(json.dumps(
            [seed, HARM_TAG, bench, row['task_id']], ensure_ascii=False).encode()).hexdigest())[
                :min(HARM_ITEMS[bench], len(available))]
    return slices


def practice_supply(practice_pools, *, excluded=None):
    """The manifest/S0 actual denominators for both seeded practice draws."""
    harms = harm_slices(practice_pools, excluded=excluded)
    excluded = excluded or {}
    rows = {}
    for bench in BENCHES:
        available = len({row['task_id'] for row in practice_pools[bench]} - set(excluded.get(bench, ())))
        rows[bench] = {'available': available,
            'decomposition_items': min(20 if bench == 'alfworld' else 100, available),
            'harm_items': len(harms[bench]),
            'acceptance_excluded': len(set(excluded.get(bench, ())))}
    return {'source': 'all_practice_except_own_acceptance', 'minimum_available': MIN_PRACTICE_ITEMS,
            'decomposition_harm_overlap_allowed': True, 'benches': rows}


def registration(slices, *, seed=p.SEED, configuration='main-v8'):
    """Bind the selected practice identities and public views without copying text."""
    _configuration(configuration)
    require(set(slices) == set(BENCHES), 'All five harm slices are registered together')
    rows = {}
    for bench in BENCHES:
        items = list(slices[bench])
        require(MIN_PRACTICE_ITEMS <= len(items) <= HARM_ITEMS[bench],
                'The registered actual harm denominator stays within its floor and cap')
        ids = [row['task_id'] for row in items]
        require(len(ids) == len(set(ids)), 'Distinct registered harm items')
        rows[bench] = {'items': len(items), 'task_ids': ids,
                       'public_sha256': {row['task_id']: digest(row['public']) for row in items},
                       'item_sha256': {row['task_id']: digest(row) for row in items}}
    value = {'version': VERSION, 'configuration': configuration, 'seed': seed,
             'tag': HARM_TAG, 'source': 'all_practice_except_own_acceptance', 'benches': rows}
    return {**value, 'sha256': digest(value)}


def _alf_signature(package, view, worker, *, card_text, configuration):
    """Initial request plus conservative identities of enabled dynamic hooks.

The production router fixes the episode's enabled set at reset. Unchanged
enabled dynamic hooks have the same future behavior; changed ones are potential
request changes even if their first-step note happens to be empty.
    """
    if p.is_v225(configuration):
        from .v225_cards import compose
        card_text = compose('alfworld', card_text, package)
    def no_call(*args, **kwargs):
        raise AssertionError('Cross-bench routing never calls a solver')
    shell = solver._Shell('alfworld', package, no_call, worker, withhold=(), restore=(), placebo=None,
                          text=None, native=None, nominal=None, configuration=configuration)
    shell.started = worker is not None
    shell.route_on(view)
    initial = view['initial_observation']
    shown = {'initial_observation': initial, 'observation': initial,
             'admissible_commands': list(view['admissible_commands_at_reset']), 'recent_history': []}
    text, _ = shell.before_step(shown, {}, 0)
    if text:
        shown[p.NOTES_KEY] = text
    system = solver.ALF_SYSTEM + ('\n' + solver.GUIDANCE + card_text if card_text.strip() else '')
    dynamic = [{'hook': 'alf_episode', 'procedure': proc.id, 'version': proc.sha256,
                'hooks': list(proc.hooks)} for proc in shell.enabled(('before_call', 'alf_before_step', 'alf_after_step'))]
    return {'request_sha256': _request_hash(system, json.dumps(shown, ensure_ascii=False)),
            'post_call': dynamic, 'faults': [dict(row) for row in shell.faults],
            'enabled': list(shell.route.enabled)}


def inspect(bench, parent, candidate, items, workers, *, card_text='', runtime=None,
            configuration='main-v8', views=None, practice_reports=None):
    """Run only sandbox routing/note hooks and compare actual rendered requests.

``workers(package, task_id)`` is the same started-worker context used by normal
practice routing. A changed sheet callback without a replay report is marked
potential, never incorrectly called an identity proof. It is measured once by
the gate's paired runner. Predicate faults likewise cannot prove identity.
    """
    _configuration(configuration)
    require(bench in BENCHES, 'A registered harm benchmark')
    items, runtime = list(items), runtime or {}
    ids = [row['task_id'] for row in items]
    require(len(ids) == len(set(ids)), 'Distinct inspected harm items')
    views = views or {row['task_id']: solver.routing_view(bench, row['public'], runtime=runtime) for row in items}
    require(set(views) == set(ids), 'Exactly the registered harm views are inspected')
    signatures, observations, faults, potential = {}, [], [], {}
    if p.is_v226(configuration):
        from contextlib import contextmanager
        from . import v226_candidates
        candidate_faults, inherited_faults = [], []
        parent_versions = {proc.id: proc.sha256 for proc in parent.procedures}
        changed_procedures = {proc.id for proc in candidate.procedures
                              if parent_versions.get(proc.id) != proc.sha256}
        original_workers = workers

        @contextmanager
        def workers(package, key):
            with v226_candidates.arm(arm), original_workers(package, key) as worker:
                yield worker

    for item in items:
        key, pair = item['task_id'], {}
        for arm, package in (('S', parent), ("S'", candidate)):
            with workers(package, key) as worker:
                if bench == 'alfworld':
                    pair[arm] = _alf_signature(package, views[key], worker,
                                               card_text=card_text, configuration=configuration)
                else:
                    def observed(shell, _text):
                        report = (practice_reports or {}).get(key)
                        if report is not None:
                            shell.feedback(views[key], report)
                            observations.append({'task_id': key, 'arm': arm,
                                'post_call_effects': v221_rule.post_call_effects(
                                    shell.record(), package=package, practice_replay=True)})
                    pair[arm] = reuse.signature(bench, package, views[key], worker, card_text=card_text,
                        runtime=runtime, configuration=configuration, note_observer=observed)
            faults.extend({'item': key, 'arm': arm, **fault} for fault in pair[arm].get('faults', ()))
        signatures[key] = pair
        if p.is_v226(configuration):
            # Keep the original evidence intact. Only S' faults introduced by
            # this edit count as harm; an identical inherited failure in both
            # arms is informational. A flaky inherited note still changes the
            # rendered request and therefore goes through the paired runner.
            inherited_faults.extend({'item': key, 'arm': 'S', **fault}
                                    for fault in pair['S'].get('faults', ()))
            for fault in pair["S'"].get('faults', ()):
                pid = fault.get('procedure')
                # Independent hook failures of an unchanged, enabled procedure
                # are inherited even when nondeterminism affects only S'. Shell
                # interactions can depend on other procedures and remain harm.
                inherited = (pid in parent_versions and pid not in changed_procedures
                    and pid in pair['S'].get('enabled', ()) and pid in pair["S'"].get('enabled', ())
                    and fault.get('hook') != 'notes'
                    and fault.get('kind') not in ('note_duplicate_name', 'note_over_declared_cap'))
                attributable = (pid in changed_procedures or
                    not inherited and fault not in pair['S'].get('faults', ()))
                (candidate_faults if attributable else inherited_faults).append(
                    {'item': key, 'arm': "S'", **fault})
        if bench == 'spreadsheetbench' and key not in (practice_reports or {}):
            callbacks = lambda arm: [row for row in pair[arm]['post_call'] if row.get('hook') == 'sheet_feedback']
            if callbacks('S') != callbacks("S'"):
                potential[key] = 'changed_sheet_callback_without_practice_replay'
        if bench == 'alfworld' and pair['S']['post_call'] != pair["S'"]['post_call']:
            potential[key] = 'changed_dynamic_episode_hook'
    changed = [key for key, pair in signatures.items() if not v221_rule.same_request(pair['S'], pair["S'"])]
    touched = (set(changed) if bench == 'alfworld' else
               set(v221_rule.identity_touched(signatures, bench=bench, trajectories=observations)))
    fired = [key for key in ids if key in touched or key in potential]
    return {'bench': bench, 'items': len(items), 'slice_ids': ids, 'fired': len(fired), 'fired_items': fired,
            'request_changed': changed, 'potential_post_call': potential, 'faults': faults,
            'identity_proven': not fired and not (candidate_faults if p.is_v226(configuration) else faults),
            **({'candidate_faults': candidate_faults, 'inherited_faults': inherited_faults,
                'observations': observations}
               if p.is_v226(configuration) else {}), 'signatures': signatures,
            'parent_sha256': parent.sha256, 'candidate_sha256': candidate.sha256}


def counts(*, fired, fixed, broken, items, whole_slice=None):
    """The cross-bench rule does not require the home's positive gain floor."""
    require(all(type(value) is int and value >= 0 for value in (fired, fixed, broken, items))
            and fixed + broken <= fired <= items and items > 0, 'Valid cross-bench decision counts')
    net = fixed - broken
    whole = Fraction(net, items) if whole_slice is None else Fraction(str(whole_slice))
    require(-1 <= whole <= 1, 'A bounded whole harm-slice contrast')
    passed = net >= 0 and whole >= p.WHOLE_BATCH_FLOOR
    return {'fired': fired, 'fixed': fixed, 'broken': broken, 'net': net, 'items': items,
            'whole_slice': float(whole), 'whole_slice_floor': float(p.WHOLE_BATCH_FLOOR),
            'passed': passed, 'decision': 'accept' if passed else 'reject'}


def measured(inspection, cells):
    """One run per fired method package; registered unknowns remain wrong on L."""
    from collections import Counter
    from .outcomes_ext import TOKENS
    keys, fired = inspection['slice_ids'], inspection['fired_items']
    expected = {(arm, key) for key in fired for arm in ('S', "S'")}
    require(set(cells) == expected, 'Only the fired parent/candidate cells may be measured')
    require(all(len(rows) == 1 and isinstance(rows[0], dict) and v221_rule.token(rows[0]) in TOKENS
                for rows in cells.values()), 'One scored run per fired item and arm is required')
    unknown_by_token = {arm: dict(Counter(v221_rule.token(cells[(arm, key)][0]) for key in fired
                                       if v221_rule.token(cells[(arm, key)][0]).startswith('unknown')))
                        for arm in ('S', "S'")}
    changes = v221_rule.item_changes(cells, keys, touched=fired)
    result = counts(fired=len(fired), fixed=len(changes['fixed']), broken=len(changes['broken']),
                    items=len(keys), whole_slice=sum(changes['deltas'].values(), Fraction(0)) / len(keys))
    return {**result, 'bench': inspection['bench'], 'fixed_items': changes['fixed'],
            'broken_items': changes['broken'], 'paired_item_calls': len(cells),
            'unknown': {arm: sum(values.values()) for arm, values in unknown_by_token.items()},
            'unknown_by_token': unknown_by_token, 'scoring_sides': {'S': 'L', "S'": 'L'}}


def narrow_additions(parent, candidate, *, home, benches):
    """Restrict new additions to safe benches; unsafe other edit kinds reject.

The package's registered exclusion layer is a conjunction with ``applies``.
No task identifier or benchmark name is inserted into procedure source.
    """
    blocked = set(benches)
    require(home in BENCHES and blocked <= set(BENCHES) - {home}, 'Only off-home scopes may be narrowed')
    changes = edits(parent, candidate)
    if not changes or any(change.kind != 'new' for change in changes):
        return None
    scopes = {pid: set(rows) for pid, rows in candidate.narrowed.items()}
    for change in changes:
        proc = change.new
        eligible = set(procedure_benches(proc)) - set(proc.excluded_benches)
        own = scopes.setdefault(proc.id, set())
        own.update(blocked & eligible)
        if not eligible - own or home not in eligible - own:
            return None
    narrowed = replace(candidate, narrowed={pid: list(rows) for pid, rows in scopes.items() if rows})
    validate(narrowed)
    return narrowed


def check(*, home, parent, candidate, slices, inspector, run_pairs, phase,
          configuration='main-v8', narrower=narrow_additions, registered_counts=None, smoke=False):
    """Bounded gate used at confirmation and again at acceptance.

``inspector(bench, parent, candidate, items)`` returns ``inspect``'s record.
``run_pairs(bench, parent, candidate, fired_items)`` returns the cell mapping
consumed by ``measured``. Narrowing permits a zero-call recheck only: any newly
changed request after it is rejected, so the registered 480-call bound holds.
    """
    _configuration(configuration)
    cross_card = p.is_v225(configuration) and phase == 'cross_card'
    route_targets = None
    if cross_card and p.is_v226(configuration):
        from .v225_cards import metadata
        route_targets = {metadata(change.new)['route'] for change in edits(parent, candidate)
                         if change.new is not None and metadata(change.new) is not None}
        require(len(route_targets) == 1, 'A cross card has exactly one route target')
    require(not smoke or cross_card and candidate.evidence in ('smoke', 'engineering_fixture'),
            'Small cross-card slices are reserved for the explicit practice smoke')
    require(home in BENCHES and (phase in ('confirmation', 'acceptance', 'hygiene') or cross_card), 'A registered cross-gate phase')
    require(set(slices) == set(BENCHES), 'The gate requires all five registered slices')
    counts_by_bench = ({bench: len(items) for bench, items in slices.items()}
                       if registered_counts is None else registered_counts)
    require(set(counts_by_bench) == set(BENCHES)
            and all(type(counts_by_bench[b]) is int and (1 if smoke else MIN_PRACTICE_ITEMS) <= counts_by_bench[b] <= HARM_ITEMS[b]
                    and len(slices[b]) == counts_by_bench[b] for b in BENCHES),
            'Every cross gate uses its registered actual practice denominator')
    benches = [bench for bench in BENCHES if bench != home]
    inspections, results, harmful, calls = {}, {}, [], 0
    for bench in benches:
        items = list(slices[bench])
        require(len(items) == counts_by_bench[bench], 'Every cross gate uses its registered actual denominator')
        found = inspector(bench, parent, candidate, items)
        require(found['bench'] == bench and found['slice_ids'] == [row['task_id'] for row in items]
                and found['parent_sha256'] == parent.sha256 and found['candidate_sha256'] == candidate.sha256,
                'Routing evidence binds the same packages and harm slice')
        require(found['fired'] == len(found['fired_items']) == len(set(found['fired_items']))
                and set(found['fired_items']) <= set(found['slice_ids']), 'A firing plan has distinct registered items')
        inspections[bench] = found
        harmful_faults = found.get('candidate_faults', found['faults']) if p.is_v226(configuration) else found['faults']
        if harmful_faults:
            results[bench] = {'bench': bench, 'fired': found['fired'], 'passed': False,
                              'decision': 'reject', 'reason': 'routing_fault', 'paired_item_calls': 0}
            harmful.append(bench)
        elif not found['fired_items']:
            results[bench] = {**counts(fired=0, fixed=0, broken=0, items=len(items)),
                              'bench': bench, 'identity_proven': True, 'paired_item_calls': 0}
        else:
            by_id = {row['task_id']: row for row in items}
            cells = run_pairs(bench, parent, candidate, [by_id[key] for key in found['fired_items']])
            result = measured(found, cells)
            if cross_card and (route_targets is None or bench in route_targets):
                from . import v225_phase
                require(found['fired'] == len(items), 'A cross card touches its entire route slice')
                card_rule = v225_phase.counts(touched=found['fired'], fixed=result['fixed'],
                    broken=result['broken'], batch=len(items), whole_batch=result['whole_slice'])
                result.update(passed=card_rule['decision'] == 'accept', decision=card_rule['decision'],
                              card_rule=card_rule)
            calls += result['paired_item_calls']
            results[bench] = {**result, 'identity_proven': False}
            if not result['passed']:
                harmful.append(bench)
        if p.is_v226(configuration):
            results[bench].update(candidate_faults=harmful_faults,
                                  inherited_faults=found.get('inherited_faults', []))
    require(calls <= MAX_PAIRED_ITEM_CALLS, 'The cross-bench gate obeys its registered call cap')
    final, narrowing, passed = candidate, None, not harmful
    if harmful:
        final = None if cross_card else narrower(parent, candidate, home=home, benches=harmful)
        if final is not None:
            rechecks = {bench: inspector(bench, parent, final, list(slices[bench])) for bench in benches}
            # Existing passing fired results remain valid only where the narrowed
            # package has identical request identities to the measured candidate.
            checks = {}
            for bench, found in rechecks.items():
                old = inspections[bench]
                require(found['slice_ids'] == old['slice_ids'] and found['parent_sha256'] == parent.sha256
                        and found['candidate_sha256'] == final.sha256, 'Narrowing rechecks the same slices and parent')
                unchanged = all(v221_rule.same_request(old['signatures'][key]["S'"],
                    found['signatures'][key]["S'"]) for key in found['slice_ids'])
                harmful_faults = (found.get('candidate_faults', found['faults'])
                                  if p.is_v226(configuration) else found['faults'])
                safe = not harmful_faults and (found['identity_proven'] or
                    bench not in harmful and unchanged and results[bench]['passed'])
                checks[bench] = {'fired': found['fired'], 'identity_proven': found['identity_proven'],
                                 'same_measured_candidate': unchanged, 'passed': safe}
                if p.is_v226(configuration):
                    checks[bench].update(candidate_faults=harmful_faults,
                                         inherited_faults=found.get('inherited_faults', []))
            passed = all(row['passed'] for row in checks.values())
            narrowing = {'benches': harmful, 'candidate_sha256': final.sha256, 'rechecked': checks,
                         'additional_model_calls': 0, 'passed': passed}
        if not passed:
            final = None
    record = {'rule_version': VERSION, 'configuration': configuration, 'phase': phase, 'home': home,
              'parent_sha256': parent.sha256, 'proposed_sha256': candidate.sha256,
              'candidate_sha256': final.sha256 if final is not None else None,
              'passed': passed, 'decision': 'accept' if passed else 'reject',
              'benches': results, 'narrowing': narrowing, 'paired_item_calls': calls,
              'call_bound': MAX_PAIRED_ITEM_CALLS}
    return final, p.record('v222-cross-gate', candidate.evidence, record)
