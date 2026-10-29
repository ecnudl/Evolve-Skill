"""Bounded main-v4 chain-G measured smoke stages; authored fixtures remain engineering evidence."""
from __future__ import annotations

from dataclasses import replace
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

from skillopt.coevo5.cells import exclusive
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest
from . import (audit, budgets, chain, engineer, engineer_v28, engineer_v291, engineer_v294,
               engineer_v211, fixtures, manifest, profiles as p, rounds, smoke, solver,
               step, units, v210_import)
from .cells import Arm
from .package import Package, Procedure, empty
from .registry import Registry


def fixture_pools(setting):
    from . import v211_fixtures
    root = safe_path(setting.root) / 'G' / 'v211-smoke' / 'fixtures'
    if not (root / fixtures.RECORD_FILE).exists():
        v211_fixtures.make(root)
    v211_fixtures.verify(root)
    selected = {b: fixtures.load_items(root, b) for b in fixtures.BENCHES}
    allocation = setting.extra['allocations']['searchqa']['slices']['smoke']
    lookup = {i['task_id']: i for i in setting.pools['searchqa']}
    selected['searchqa'] = [lookup[key] for key in allocation]
    # Preparation registered these games for smoke; no import learning is performed.
    from . import supply
    selected['alfworld'] = supply.slices('alfworld', setting.pools['alfworld'],
        supply.registered_sizes('alfworld'))['smoke']
    return selected


def _package(bench, evidence):
    if bench == 'alfworld':
        rows = v210_import.pins()['procedures']
        return Package(tuple(replace(Procedure.from_json(row['record']), evidence=evidence) for row in rows),
                       'G/v211-smoke/import', evidence)
    return fixtures.fixture_package()


def s2(setting):
    """Every adapter on C and X; no acceptance placebo and no sealed test reads."""
    pools, results = fixture_pools(setting), {}
    for k, bench in enumerate(p.BENCHES, 1):
        items = pools[bench][:6 if bench == 'alfworld' else 20]
        require(len(items) == (6 if bench == 'alfworld' else 20), 'Exact S2 fixture counts before dispatch')
        name = 'G/v211-smoke/S2/' + bench
        root = safe_path(setting.root) / name
        local = units.for_unit(setting, 'G', bench, name)
        def work(attempt, bench=bench, items=items, name=name, local=local):
            endpoint = budgets.endpoint(local, ('overall', 'G:solver'),
                client=local.clients(p.CHAINS['G'], bench), max_tokens_bound=p.ledger_bound(p.CHAINS['G'], bench))
            tasks = {rounds.key(bench, i['task_id']): {'public': i['public'], 'private': i['private']} for i in items}
            arms = {'C': Arm('card', empty(step=name, evidence=local.evidence)),
                    'X': Arm('candidate', _package(bench, local.evidence))}
            first_key = next(iter(tasks))
            first = rounds.run_round(replace(local, workers=1), attempt, endpoint, name, {'C': arms['C']},
                {'C': [(first_key, 1)]}, tasks, tag='first-response')
            require(next(iter(first.values()))[0]['final'] is not None and next(iter(first.values()))[0]['stop'] is None,
                    'An actual first model response precedes concurrent smoke cells')
            got = rounds.run_round(local, attempt, endpoint, name, arms,
                {'C': [(key, 1) for key in tasks if key != first_key],
                 'X': [(key, 1) for key in tasks]}, tasks, tag='measured')
            got.update(first)
            cells = [cell for group in got.values() for cell in group]
            measured = smoke.measured_cells(cells)
            successful = sum(cell.get('final', {}).get('token') in ('pass', 'fail') for cell in cells)
            return {'passed': successful == len(cells) and len(cells) == 2 * len(items),
                'items': len(items), 'cells': len(cells), 'measurements': measured,
                'settled_tokens': sum(s.get('charged', 0) for c in cells for s in c['sends']),
                'by_arm': {a: smoke.measured_cells([c for c in cells if c['cell']['arm'] == a]) for a in arms},
                'first_response_confirmed': True,
                'source_kind': 'reserved_smoke' if bench in ('searchqa', 'alfworld') else 'authored_fixture',
                'sealed_reads': 0}
        results[bench] = units.run_unit(root, run=setting.run, identity={'unit': name}, work=work,
            evidence=setting.evidence, configuration=p.MAIN_V4,
            drain=units.drainer(setting, 'G', name))['result']
    return {'passed': all(v['passed'] for v in results.values()), 'benches': results, 'solver_chain': 'G'}


def fixture_step(setting, services, bench, substage):
    pools = fixture_pools(setting)
    rows = deepcopy(pools[bench][:6])
    require(len(rows) == 6, 'S3 has four run and two authored confirmation items')
    for i, row in enumerate(rows[4:]):
        row['task_id'] = 'v211-' + bench + '-authored-confirm-%d' % i
        row['family_id'] = row['task_id']
        row['part'] = 'engineering_fixture'
        if bench == 'searchqa':
            row['public'] = {'question': 'Authored fixture: which tree is described?',
                             'context': ['The authored tree is cedar.']}
            row['private'] = {'answers': ['cedar']}
    root = safe_path(setting.root) / 'G' / 'v211-smoke' / substage / bench
    local = replace(setting, pools={**setting.pools, bench: rows})
    services = replace(services, registry=Registry(root / 'history', evidence=setting.evidence))
    parent = empty(step='G/s0', evidence=setting.evidence)
    st = step._Step(local, services, 'G', bench, p.BENCHES.index(bench) + 1, parent, root, None)
    return st, {'run': rows[:4], 'accept': [], 'confirm': rows[4:]}


def _context(st, cut, inputs_dirs=None):
    _, _, publics = step._training_publics(cut, None, st.bench)
    ctx = engineer.Context(bench=st.bench, k=st.k, step=st.name, evidence=st.evidence, parent=st.parent,
        trajectories=step._run_trajectories(st), current=step._current(st, []), corpora=step._corpora(st, cut),
        workers=st.services.workers, inputs_dirs=inputs_dirs, roles=st.roles('engineer'), label=st.label('engineer-r1'),
        card=st.setting.cards[st.bench], mode='train', round=1, base=st.parent,
        configuration=p.MAIN_V4, echo=True, counterfactual=True,
        routing_items=[(key, solver.routing_view(st.bench, public, runtime=st.runtime())) for key, public in publics.items()],
        routing_workers=step._item_workers(st, publics), routing_shared_worker=st.bench != 'spreadsheetbench',
        audit_judges=units.audit_judges(st.setting, 'G', st.bench, st.k))
    ctx.sheet['v211_prompt_pins'] = engineer_v211.pins()
    return ctx


def _authored(ctx, n, variant):
    public = 'instruction' if ctx.bench == 'spreadsheetbench' else 'question'
    body = ('return {"facts": ["Public text has %d characters." % len(view.get("' + public + '", ""))]}'
            if variant == 'correct' else 'return {"facts": ["All public conditions were checked."]}'
            if variant == 'audit' else 'return {"facts": [view["missing_authored_fault_key"]]}'
            if variant == 'fault' else 'return {}')
    source = 'def before_call(view, state):\n    ' + body + '\n'
    entry = {'kind': 'new', 'description': 'Computes a public-text check for the task.', 'hooks': ['before_call'],
             'max_note_chars': 1200, 'excluded_benches': [b for b in p.BENCHES if b != ctx.bench]}
    return engineer.Change(n, 'new', entry, source, digest({'entry': entry, 'source': source}))


def _drills(st, cut):
    """Exercise bounded repair APIs with authored faults; outcomes are recorded without claiming efficacy."""
    def work(attempt):
        with step._inputs_dirs(st, step._run_trajectories(st), cut) as inputs_dirs:
            return drill(inputs_dirs)
    def drill(inputs_dirs):
        ctx = _context(st, cut, inputs_dirs)
        correct = _authored(ctx, 1, 'correct')
        report = engineer.check(correct, ctx)
        require(report['passed'] and not report.get('inert'), 'The authored effective fixture passes fatal checks')
        audited = audit.audit1(ctx, correct, report)
        fault = _authored(ctx, 2, 'fault')
        fault_report = engineer.check(fault, ctx)
        _, _, _, fault_repair = engineer_v291.repair(ctx, fault, fault_report, max_repairs=1)
        inert = _authored(ctx, 3, 'inert')
        inert_report = engineer.check(inert, ctx)
        _, _, _, inert_repair = engineer_v294.repair(ctx, inert, inert_report)
        retried, failures = engineer_v28.read_call(ctx, 'unusable authored envelope', 'authored-envelope', 'smoke-format')
        error = _authored(ctx, 4, 'audit')
        error_report = engineer.check(error, ctx)
        mistaken = audit.audit1(ctx, error, error_report) if error_report['passed'] else None
        # A deliberately authored semantic problem requests the same frozen audit-fix API.
        request = {'request': 'audit_fix', 'bench': st.bench, 'change': dict(error.entry, source=error.source),
                   'instruction': audit.audit_fix_prompt(error, mistaken) if mistaken else
                   'The authored fixture claims all public conditions were checked without computing any check.',
                   'exercise': True}
        fixed, call = engineer._ask(ctx, request, 'audit-fix/4')
        fixed_changes, fixed_failures = engineer_v28.read_call(ctx, fixed, call, 'audit-fix/4', change=error)
        candidate = Package((correct.procedure,), st.name, st.evidence, st.parent.sha256)
        step.save(st.chain_root, candidate)
        return {'passed': all(audited['available'].values()) and bool(fault_repair['calls'])
            and bool(inert_repair['calls']) and bool(ctx.sheet.get('format_retries')) and call is not None,
            'candidate_sha256': candidate.sha256, 'engineer': {'audits': [audited] + ([mistaken] if mistaken else [])}, 'audit': audited, 'authored_error_audit': mistaken,
            'fault_repair': fault_repair, 'inert_repair': inert_repair,
            'authored_fault_checks': fault_report, 'authored_inert_checks': inert_report,
            'gate_basis': 'path exercised; repair outcomes are recorded, not assumed successful',
            'format_retry': ctx.sheet.get('format_retries', []), 'format_failures': failures,
            'audit_fix': {'call': call, 'parsed': bool(fixed_changes) and not fixed_failures,
                          'exercise': True, 'decision_used_for_adoption': False},
            'exercise': True, 'decision_used_for_adoption': False}
    return st.unit('engineer-r1', work)



def _measured_roles(st):
    """Record each actual role, including ask calls and nested leakage adjudication."""
    roles, path = st.roles, st.chain_root / 'role-measurements.jsonl'
    def measured_roles(group):
        made = roles(group)
        for method in ('plain', 'ask'):
            original = getattr(made, method)
            def measured(*args, _original=original, **kwargs):
                before = len(made.calls)
                try:
                    return _original(*args, **kwargs)
                finally:
                    rows = []
                    for call in made.calls[before:]:
                        role = call['role']
                        role = ('leakage' if role == 'leak_adjudicate' else
                                'examiner_research' if role.startswith('research_') else
                                'engineer' if group == 'analyst' else group)
                        sends = call.get('sends') or []
                        rows.append({'role': role, 'charged': sum(v.get('charged', 0) for v in sends),
                            'request_bytes': max([v.get('request_bytes', 0) for v in sends], default=0),
                            'request_sha256': call['request_sha256']})
                    if rows:
                        path.parent.mkdir(parents=True, exist_ok=True)
                        with path.open('a') as handle:
                            handle.write(''.join(json.dumps(row, sort_keys=True)+'\n' for row in rows))
            setattr(made, method, measured)
        return made
    st.roles = measured_roles
    return path


def role_probe_pins():
    from skillopt.coevo5 import leakage
    from . import describer, examiner, research
    rows = {'leakage': (leakage.ADJUDICATE_SYSTEM, {'rule': 'Compute only from the current public input.'}),
        'describer': (describer.DESCRIBER_SYSTEM, {'code': 'def before_call(view, state): return {}',
            'description': 'An authored no-op for the smoke cost probe.'}),
        'examiner': (examiner.POLICY_SYSTEM_V2, {'request': 'policy', 'families': [], 'requests': [],
            'instruction': 'Return no families and no research requests for this authored cost probe.'}),
        'examiner_research': (research.QUERY_SYSTEM, {'purpose': 'verify',
            'request': 'Find public documentation of integer addition.', 'queries': [], 'pages': []})}
    return {role: {'system': system, 'user': json.dumps(user, ensure_ascii=False, sort_keys=True),
                  'system_sha256': hashlib.sha256(system.encode()).hexdigest(),
                  'user_sha256': hashlib.sha256(json.dumps(user, ensure_ascii=False, sort_keys=True).encode()).hexdigest()}
            for role, (system, user) in rows.items()}


def _role_probes(st):
    """One bounded authored request per inherited role; no external research fetch."""
    pins = role_probe_pins()
    def work(attempt):
        output = {}
        for role, pin in pins.items():
            made = st.roles(role)
            reply = made.plain(role, pin['system'], pin['user'], label=st.name+'/cost-probe/'+role)
            output[role] = {'passed': reply is not None, 'calls': made.calls,
                'system_sha256': pin['system_sha256'], 'user_sha256': pin['user_sha256'],
                'authored_engineering_fixture': True, 'decision_used_for_adoption': False}
        return {'passed': all(v['passed'] for v in output.values()), 'roles': output,
                'request_pins': pins, 'external_research_fetches': 0}
    # Standalone unit: no collision with the actual generate/freeze unit.
    return units.run_unit(st.chain_root/'role-cost-probes',run=st.setting.run,
        identity={'unit':st.name+'/role-cost-probes','pins':digest(pins)},work=work,
        evidence=st.evidence,configuration=p.MAIN_V4)['result']


def s3(setting, services):
    from . import v29_smoke, v211_audit_control, v211_confirm_control
    results = {}
    for bench in p.BENCHES[:-1]:
        st, cut = fixture_step(setting, services, bench, 'S3-drills')
        measure_path = _measured_roles(st)
        step._run(st, cut)
        drills = _drills(st, cut)
        candidate = step._package(st, drills['candidate_sha256'])
        trained = step._train_eval(st, cut, 1, st.parent, candidate, None)
        confirmed = step._confirm_eval(st, cut, 1, st.parent, candidate, exercise=True)
        confirm_control = v211_confirm_control.confirmation_controls(st, cut, candidate, confirmed)
        final, final_audit = step._audit_final(st, candidate, [{'round': 1}])
        audit_control = v211_audit_control.audit2_control(st, candidate)
        actual, actual_cut = fixture_step(setting, services, bench, 'S3-real')
        actual_path = _measured_roles(actual)
        step._run(actual, actual_cut)
        step._diagnose(actual, actual_cut)
        generated = step._generate(actual, actual_cut)
        real = step._engineer_train(actual, actual_cut, 1, actual.parent, done=[], fed=None, history=[],
            training=None, lint=[], reserved=frozenset(), analysed=frozenset(), disclosed=frozenset(), generated=generated)
        probes = _role_probes(actual)
        role_rows = [json.loads(line) for path in (measure_path, actual_path) if path.exists()
                     for line in path.read_text().splitlines()]
        measured = {**smoke.role_calls_measured(role_rows), **v29_smoke._audit_measurements(drills, real, final_audit)}
        parsed = any(row['parsed'] for row in real['engineer']['proposals'])
        results[bench] = {'passed': drills['passed'] and probes['passed'] and parsed and all(final_audit['audit_final']['available'].values())
            and confirm_control['passed'] and audit_control['passed'],
            'drills': drills, 'bounded_role_probes': probes, 'real_engineer': real,
            'authored_controls': {'confirmation': confirm_control, 'audit2': audit_control}, 'training': trained, 'confirm': confirmed,
            'audit_final': final_audit, 'role_measurements': measured,
            'confirm_measurements': smoke.measured_cells(list(confirmed['candidate_cells'].values()) +
                                                         list(confirmed['incumbent_cells'].values())),
            'exercise': True, 'benchmark_effect_evidence': False,
            'confirmation_fixture_sha256': digest(cut['confirm']),
            'confirmation_fixture_ids': [row['task_id'] for row in cut['confirm']]}
    return {'passed': all(v['passed'] for v in results.values()), 'benches': results}


def projection(m, s2_result, s3_result):
    """Maximum-schedule projections using actual sends, including both auditors."""
    import math
    from fractions import Fraction
    from skillopt.coevo5.ledger import reservation
    from . import v211_limits
    require(set(s2_result['benches']) == set(p.BENCHES)
        and set(s3_result['benches']) == set(p.BENCHES[:-1]), 'Every benchmark has smoke measurements')
    classes, sizes = {}, {}
    actual = charged = 0
    for bench, row in s2_result['benches'].items():
        measured = row['measurements']
        classes[bench] = measured['per_class'][bench]
        sizes[bench] = measured['request_bytes'][bench]
        actual += measured['actual']
        charged += row['settled_tokens']
    require(actual > 0 and charged > 0, 'Measured solver charges and usage are positive')
    ratio = Fraction(charged, actual)
    per_cell = smoke._per_cell(classes)
    for bench, row in s3_result['benches'].items():
        confirm = row['confirm_measurements']
        entry = confirm.get('per_class', {}).get(bench, {}).get('procedure')
        if entry and entry['cells']:
            per_cell[bench]['procedure'] = max(per_cell[bench]['procedure'], entry['tokens'] / entry['cells'])
        sizes[bench] = max(sizes[bench], confirm.get('request_bytes', {}).get(bench, 0))
    roles = v211_limits.method_projection({bench: row['role_measurements'] for bench, row in s3_result['benches'].items()})
    solver_scopes, totals = {}, {}
    for chain_id in p.CHAINS:
        caps = budgets.chain_caps(chain_id, p.MAIN_V4)
        bounds = m['clients']['solver'][chain_id]['B']
        maximum = max(reservation(sizes[b], bounds[b]) for b in p.BENCHES)
        scopes = smoke._scope_cells(chain_id, p.MAIN_V4)
        for scope, alternatives in scopes.items():
            estimate = max(sum(per_cell[b]['card'] * card + per_cell[b]['procedure'] * proc
                               for b, (card, proc) in cells.items()) for cells in alternatives)
            need = math.ceil(estimate * float(ratio) + maximum)
            solver_scopes[scope] = {'projected': need, 'cap': caps[scope], 'passed': need <= caps[scope]}
        method = roles[chain_id + ':glm']
        method_need = method['needed']
        total = solver_scopes[chain_id + ':solver']['projected'] + method_need
        totals[chain_id] = {'projected': total, 'cap': caps['overall'], 'passed': total <= caps['overall']}
    terms = p.read_estimate_terms(per_cell, ratio, p.MAIN_V4)
    return {'passed': all(r['passed'] for r in solver_scopes.values())
            and all(r.get('fits', r.get('passed', False)) for r in roles.values())
            and all(r['passed'] for r in totals.values()),
        'configuration': p.MAIN_V4, 'chain': 'G', 'all_scopes_projected': True,
        'per_cell': per_cell, 'ratio': str(ratio), 'solver_scopes': solver_scopes,
        'method_scopes': roles, 'overall': totals, 'maximum_schedule': v211_limits.identity(),
        'read_terms': {b: str(v) for b, v in terms.items()}, 'read_estimate': math.ceil(sum(terms.values())),
        'D_cost_basis': 'G measured tokens are a projection placeholder; separate D route probes required'}


def sx(setting, services):
    """Real training and sealed acceptance on the reserved SearchQA mini-step."""
    pools = fixture_pools(setting)
    items = pools['searchqa'][20:280]
    require(len(items) == 260, 'SX uses the registered reserved 100+160 SearchQA items')
    root = safe_path(setting.root) / 'G' / 'v211-smoke' / 'SX'
    # The frozen SmokeStep sends into the dedicated smoke ledger; retain the new
    # configuration's conservative envelopes rather than the historical tiny smoke caps.
    confirms = {}
    for r in range(1, 7):
        rows = deepcopy(items[:2])
        for i, row in enumerate(rows):
            row['task_id'] = 'v211-authored-confirm-r%d-%d' % (r, i)
            row['family_id'] = row['task_id']
            row['part'] = 'engineering_fixture'
            row['public'] = {'question': 'Authored fixture: what word is given in the context?',
                             'context': ['The authored fixture word is cedar.']}
            row['private'] = {'answers': ['cedar']}
        confirms['confirm-r%d' % r] = rows
    extra = {**setting.extra, 'verify': setting.extra.get('verify', lambda: None),
             'v211_smoke_confirms': confirms}
    local_pools = {**setting.pools, 'searchqa': list(setting.pools['searchqa']) +
        [item for rows in confirms.values() for item in rows]}
    from skillopt.coevo5.budget import Budget
    local = replace(setting, budget=Budget(root / 'ledger'), extra=extra, pools=local_pools, branch=None, longest=None)
    from . import v211_limits
    cap = v211_limits.smoke_caps('SX')
    local.budget.declare({'overall': cap['overall'], 'smoke:solver': cap['solver'], 'smoke:glm': cap['method'],
        **{'smoke:role:' + key: n for key, n in cap['audit_caps']['searchqa'].items()}})
    registry = Registry(root / 'history', evidence=setting.evidence)
    services = replace(services, registry=registry)
    parent = empty(step='smoke/s0', evidence=setting.evidence)
    example = step.SmokeStep(items=tuple(items), candidate=None, model=p.CHAINS['G'], train=True)
    found = step.run_step(local, budgets.SMOKE, 'searchqa', 1, parent, services=services,
                          chain_root=root, smoke=example)
    judged = smoke.sx_judged(root, found.record, registry, items, local.budget.snapshot(), configuration=p.MAIN_V4)
    entries = registry.entries(budgets.SMOKE, 'searchqa')
    records = [json.loads(line) for line in registry.path(budgets.SMOKE, 'searchqa').read_text().splitlines()]
    registered = [row['item_id'] for row in records if row['state'] == 'registered']
    formal = {row['task_id'] for row in items}
    exercised = {key for key, row in entries.items() if '/confirm-r' in row['unit']}
    allowed = {row['task_id'] for rows in confirms.values() for row in rows}
    counts = {key: registered.count(key) for key in registered}
    run_ids = {row['task_id'] for row in items[:100]}
    accept_ids = formal - run_ids
    consumption = (set(entries) == formal | exercised and exercised <= allowed
        and counts == {key: 1 for key in formal | exercised}
        and all(entries[key]['state'] == 'decided' and entries[key]['unit'] == 'smoke/s1-searchqa/run' for key in run_ids)
        and all(entries[key]['state'] in ('decided', 'routed_not_dispatched')
            and entries[key]['unit'] == 'smoke/s1-searchqa/accept' for key in accept_ids)
        and all(entries[key]['state'] == 'decided' for key in exercised))
    sealed = p.verified(read_json(root / 's1-searchqa/accept/sealed.json'), 'acceptance-sealed')
    from . import acceptance
    dispatched = set(acceptance.dispatched(sealed))
    confirm_units = {row['task_id']: 'smoke/s1-searchqa/'+name for name, rows in confirms.items() for row in rows}
    consumption = consumption and all(entries[key]['state'] == ('decided' if key in dispatched else 'routed_not_dispatched')
        for key in accept_ids) and all(entries[key]['unit'] == confirm_units[key] for key in exercised)
    ledger = local.budget.snapshot()
    judged['rows']['all_scopes_clean'] = all(row['open'] == 0 and row['settled'] <= row['cap'] for row in ledger.values())
    judged['all_scopes'] = ledger
    judged['rows']['consumption'] = consumption
    judged['passed'] = all(judged['rows'].values())
    judged.update(evidence_kind='engineering_smoke', benchmark_effect_evidence=False,
        confirm_exercise=True, authored_confirm_sha256=digest(confirms))
    return judged
