"""Main-v5 lean smoke implementations; test panels remain closed throughout."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import hashlib
import json
import math
from types import SimpleNamespace

from skillopt.coevo5.ledger import reservation
from skillopt.continual_eval.core import require, safe_path, write_json
from skillopt.validator_pilot.api import digest
from . import budgets, chain as chains, engineer, engineer_reader, engineer_v211, evaluation, fixtures
from . import profiles as p, rounds, smoke, units, v211_fixtures, v214_smoke as v, zebralogic as z
from .cells import Arm
from .package import Package, Procedure, empty, save


def s1(setting, chain):
    first = chains.first_call(setting, chain)
    probe = None
    if chain == 'D':
        from . import v29_route_probe
        probe = v29_route_probe.measure(setting, bench=z.BENCH)
    selected = (getattr(setting, 'extra', None) or {}).get('configuration', v.CONFIGURATION)
    configuration = selected if selected in (p.IMPLANT_V5, p.MAIN_V6) else v.CONFIGURATION
    if p.is_implant_v5(configuration):
        probe = v.implant_solver_probe(first, chain, probe)
    return {'passed': first['passed'] is True and (probe is None or probe['passed'] is True),
            'solver_confirmation': first[p.RECORD_HASH], 'solver_probe': probe,
            'solver_bounds': v.solver_bounds(chain, probe, **v._options(configuration)), 'sealed_reads': 0}


def fixture_pools(setting, chain):
    """Inherited smoke slices; scarce OQ/sheet examples are authored fixtures."""
    root = safe_path(setting.root) / chain / 'v214-smoke' / 'fixtures'
    if not (root / fixtures.RECORD_FILE).exists():
        v211_fixtures.make(root)
    v211_fixtures.verify(root)
    selected = {b: fixtures.load_items(root, b) for b in ('officeqa', 'spreadsheetbench')}
    lookup = {row['task_id']: row for row in setting.pools['searchqa']}
    selected['searchqa'] = [lookup[key] for key in setting.extra['allocations']['searchqa']['slices']['smoke']][:20]
    selected[z.BENCH] = z.slices(setting.pools[z.BENCH])['smoke']
    from . import supply
    selected['alfworld'] = supply.slices('alfworld', setting.pools['alfworld'],
                                        supply.registered_sizes('alfworld'))['smoke'][:6]
    require({b: len(rows) for b, rows in selected.items()} == v.S2_ITEMS, 'Exact lean practice counts')
    return selected


def s2(setting, chain):
    selected = (getattr(setting, 'extra', None) or {}).get('configuration', v.CONFIGURATION)
    configuration = selected if selected in (p.IMPLANT_V5, p.MAIN_V6) else v.CONFIGURATION
    pools, results = fixture_pools(setting, chain), {}
    for bench in p.active_benches(configuration):
        name = chain + '/v214-smoke/S2/' + bench
        local = units.for_unit(setting, chain, bench, name)
        def work(attempt, bench=bench, local=local, name=name):
            endpoint = budgets.endpoint(local, ('overall', chain + ':solver'),
                client=local.clients(p.CHAINS[chain], bench),
                max_tokens_bound=p.ledger_bound(p.CHAINS[chain], bench, branch=local.branch, longest=local.longest))
            tasks = {rounds.key(bench, row['task_id']): {'public': row['public'], 'private': row['private']}
                     for row in pools[bench]}
            card = Arm('card', empty(step=name, evidence=local.evidence))
            first_key = next(iter(tasks))
            first = rounds.run_round(replace(local, workers=1), attempt, endpoint, name, {'C': card},
                {'C': [(first_key, 1)]}, tasks, tag='first-response')
            first_cell = next(iter(first.values()))[0]
            require(first_cell.get('final') is not None and first_cell.get('stop') is None,
                    'A confirmed actual first reply precedes concurrent practice cells')
            rest = rounds.run_round(local, attempt, endpoint, name, {'C': card},
                {'C': [(key, 1) for key in tasks if key != first_key]}, tasks, tag='measured')
            rest.update(first)
            cells = [cell for group in rest.values() for cell in group]
            measured = smoke.measured_cells(cells)
            valid = sum((cell.get('final') or {}).get('token') in ('pass', 'fail') for cell in cells)
            parsed = (sum(((cell.get('judge') or {}).get('format') or {}).get('grid') is True for cell in cells)
                      if bench == z.BENCH else None)
            return {'passed': valid == len(cells) == v.S2_ITEMS[bench]
                    and (parsed is None or parsed >= 9), 'items': len(tasks), 'cells': len(cells),
                'arms': ['C'], 'measurements': measured,
                'settled_tokens': sum(send.get('charged', 0) for cell in cells for send in cell['sends']),
                'parsed': parsed, 'first_response_confirmed': True, 'sealed_reads': 0,
                'source_kind': 'authored_fixture' if bench in ('officeqa', 'spreadsheetbench') else 'reserved_smoke'}
        results[bench] = units.run_unit(safe_path(setting.root) / name, run=setting.run, identity={'unit': name},
            work=work, evidence=setting.evidence, configuration=configuration,
            drain=units.drainer(setting, chain, name))['result']
    return {'passed': all(row['passed'] for row in results.values()), 'chain': chain,
            'benches': results, 'cells': sum(row['cells'] for row in results.values()), 'sealed_reads': 0}


def s3(setting, chain):
    """Exactly one inherited engineer proposal, no repair or method-effect claim."""
    configuration = p.MAIN_V6 if p.is_v218(p.configuration_of(setting)) else v.CONFIGURATION
    name = chain + '/v214-smoke/S3'
    def work(attempt):
        endpoint = units._bounded_endpoint(units.role_endpoint(setting, chain, 'engineer', 'searchqa', 1),
                                            p.ENGINEER_MAX_TOKENS[v.CONFIGURATION])
        system = engineer_v211.system('searchqa', train=True)
        request = {'request': 'propose', 'bench': 'searchqa', 'mode': 'train', 'round': 1,
            'instruction': 'Propose a helper for this authored practice example; return the registered delivery schema.',
            'authored_example': {'question': 'Which tree is described?', 'context': ['The described tree is cedar.']},
            'current_package': [], 'schema': engineer_reader.schema_document(),
            'evidence': 'engineering_fixture', 'decision_used_for_adoption': False}
        user = json.dumps(request, ensure_ascii=False, sort_keys=True)
        recorder = endpoint.recorder(label=name + '/engineer')
        receipt = endpoint.send(system, user, recorder)
        parsed, no_change, parsed_changes, schema_errors = False, False, 0, 0
        if receipt.get('ok') is True:
            try:
                reply = receipt.get('response', '')
                context = SimpleNamespace(configuration=configuration, mode='train', bench='searchqa',
                    parent=empty(step=name + '/parent', evidence=setting.evidence))
                found = engineer_reader.read(reply, context)
                parsed_changes = sum(row['error'] is None for row in found)
                schema_errors = sum(row['error'] is not None for row in found)
                parsed = bool(found) and schema_errors == 0
                if not found:
                    # A normalized missing changes field is not an explicit no-change response.
                    blocks = list(engineer_reader.FENCE.finditer(reply))
                    candidates = [match.group(3) for match in blocks if match.group(2).strip().lower()
                                  in ('json', 'jsonc', 'json5', '')]
                    for candidate in candidates if blocks else [reply]:
                        try:
                            document, _ = engineer_reader.tolerant_json(candidate)
                            no_change = no_change or (isinstance(document, dict) and document.get('changes') == [])
                        except engineer_reader.Unusable:
                            pass
                    parsed = no_change
            except (ValueError, engineer_reader.Unusable):
                pass
        charged = sum(row.get('charged', 0) for row in recorder.sends)
        return {'passed': receipt.get('ok') is True and parsed and charged > 0,
            'engineer_calls': 1, 'transport_sends': len(recorder.sends), 'parsed': parsed, 'tokens': charged,
            'parsed_changes': parsed_changes, 'schema_errors': schema_errors, 'no_change': no_change,
            'reader': 'inherited_engineer_reader_no_retries',
            'request_bytes': max((row.get('request_bytes', 0) for row in recorder.sends), default=0),
            'system_sha256': hashlib.sha256(system.encode()).hexdigest(),
            'request_sha256': digest({'system': system, 'user': user}),
            'unmeasured_roles': 'assumed; no additional role probes', 'sealed_reads': 0,
            'benchmark_effect_evidence': False}
    return units.run_unit(safe_path(setting.root) / name, run=setting.run, identity={'unit': name}, work=work,
        evidence=setting.evidence, configuration=configuration,
        drain=units.drainer(setting, chain, name))['result']


def projection(s2, chain, *, s3=None, bounds, configuration=v.CONFIGURATION):
    """Price every worst-case read cell from this chain's measured card usage."""
    require(chain in p.CHAINS and set(s2.get('benches', {})) == set(p.active_benches(configuration)),
            'SE6 needs measurements for all five benchmarks on this chain')
    if not p.is_implant_v5(configuration):
        require(s3.get('passed') is True and s3.get('engineer_calls') == 1 and s3.get('tokens', 0) > 0,
                'SE6 requires the one measured engineer call')
    require(bounds == v.solver_bounds(chain, {'passed': True, 'route': 'B', 'longest': bounds.get('longest')}
                                      if chain == 'D' else None, **v._options(configuration)), 'Registered S1 solver bounds')
    per_cell, sizes, actual, charged = {}, {}, 0, 0
    for bench, row in s2['benches'].items():
        measured = row['measurements']
        entry = measured.get('per_class', {}).get(bench, {}).get('card', {})
        require(row.get('passed') is True and row.get('arms') == ['C'] and row.get('items') == v.S2_ITEMS[bench]
                and entry.get('cells') == v.S2_ITEMS[bench] and entry.get('tokens', 0) > 0,
                'SE6 only uses the registered measured C practice cells')
        card = Fraction(entry['tokens'], entry['cells'])
        per_cell[bench] = {'card': str(card), 'procedure': str(card * p.PROCEDURE_ARM_FACTOR[1]),
                           'procedure_assumed': True}
        sizes[bench] = measured['request_bytes'][bench]
        actual += measured['actual']
        charged += row['settled_tokens']
    require(actual > 0 and charged > 0, 'Measured usage and settled charge are positive')
    ratio = Fraction(charged, actual)
    numerical = {b: {**row, 'card': Fraction(row['card']), 'procedure': Fraction(row['procedure'])}
                 for b, row in per_cell.items()}
    terms = p.read_estimate_terms(numerical, ratio, configuration)
    estimate = math.ceil(sum(terms.values()))
    reserved = max(reservation(sizes[b], bounds['ledger_bound'][b]) for b in sizes)
    caps = budgets.chain_caps(chain, configuration)
    scope_rows = {}
    for scope, alternatives in smoke._scope_cells(chain, configuration).items():
        cost = max((sum(numerical[b]['card'] * card + numerical[b]['procedure'] * proc
                        for b, (card, proc) in cells.items()) for cells in alternatives), default=0)
        need = math.ceil(cost * ratio + reserved)
        # Implant/main-v6 test scopes also fund one read retry. Other test scopes
        # use the registered FIRED_SHARES maximum, identical to read_budget.
        if scope == chain + ':test' and not (p.is_implant_v5(configuration) or p.is_v218(configuration)):
            need = estimate + reserved
        scope_rows[scope] = {'projected': need, 'cap': caps[scope], 'passed': need <= caps[scope]}
    read_need = max(estimate + reserved, math.ceil(estimate * p.TEST_START_FACTOR))
    read_scopes = {scope: {'projected': read_need, 'cap': caps[scope],
                           'passed': read_need <= caps[scope]}
                   for scope in (chain + ':test', chain + ':solver')}
    return {'passed': all(row['passed'] for row in scope_rows.values())
            and all(row['passed'] for row in read_scopes.values()),
        'configuration': configuration, 'chain': chain, 'per_cell': per_cell, 'ratio': str(ratio),
        'read_terms': {b: str(n) for b, n in terms.items()}, 'read_estimate': estimate,
        'read_reservation': reserved, 'read_start_factor': str(p.TEST_START_FACTOR),
        'later_G_cost_factor': ('not_applicable_no_learning_run' if p.is_implant_v5(configuration)
                                else 'runtime read_budget rechecks max(1, measured training factor)'),
        'read_scopes': read_scopes, 'solver_scopes': scope_rows,
        'stage_packages': 4, 'solver_bounds': deepcopy(bounds), 'sealed_reads': 0,
        'method_cost': ({'model_calls': 0, 'all_role_caps': 0, 'learning': 'none'}
                        if p.is_implant_v5(configuration) else
                        {'engineer_tokens_per_call': s3['tokens'], 'other_roles': 'unmeasured; assumed',
                         'one_engineer_call_only': True}),
        **({'solver_probe': deepcopy(s2['solver_probe'])} if p.is_implant_v5(configuration) else {}),
        'maximum_schedule': manifest_identity(**v._options(configuration))}


def manifest_identity(configuration=v.CONFIGURATION):
    from .manifest import _plain
    return _plain(v._identity(configuration))


def sx(root, *, configuration=v.CONFIGURATION):
    if p.is_v218(configuration):
        from . import v218_split, v218_read
        stage_rows = sx(safe_path(root) / "stage-rows")
        split = v218_split.structural_smoke(safe_path(root) / "split")
        reused = v218_read.structural_demo()
        return {"passed": stage_rows["passed"] and split["passed"] and reused["passed"],
                "configuration": configuration, "stage_rows": stage_rows,
                "split": split, "read_reuse": reused, "model_calls": 0, "sealed_reads": 0}

    """Authored zero-model stage demo exercising persisted rows and route sharing."""
    from . import router
    root = safe_path(root)
    start = empty(step='G/s0', evidence='engineering_fixture')
    source = 'def applies(view):\n    return True\ndef before_call(view, state):\n    return {"facts": ["An authored public-input check."]}\n'
    first = Procedure('fx-v214-first', 'searchqa', 'Authored stage demo check.', ('applies', 'before_call'),
                      source, 'engineering_fixture', header='Authored notes.', max_note_chars=200,
                      policy_version=p.POLICY_VERSIONS[v.CONFIGURATION])
    second = replace(first, id='fx-v214-second', origin='officeqa')
    middle = Package((first,), 'G/s2', 'engineering_fixture', start.sha256)
    silent = replace(first, id='fx-v214-silent', origin='officeqa')
    later = Package((first, silent), 'G/s4', 'engineering_fixture', middle.sha256)
    final = Package((first, second, silent), 'G/s5', 'engineering_fixture', later.sha256)
    for package in (middle, later, final):
        save(root, package)
    for k, (bench, package) in enumerate(zip(p.active_benches(v.CONFIGURATION),
                                            (start, middle, middle, later, final)), 1):
        target = root / ('s%d-%s' % (k, bench)) / 'step.json'
        if not target.exists():
            write_json(target, p.record('step', 'engineering_fixture', {
                'chain': 'G', 'k': k, 'bench': bench, 'package_sha256': package.sha256}))
    rows = evaluation.stage_rows(root, 'G', p.active_benches(v.CONFIGURATION), final, start)
    # Derived routes need no sandbox: the fixture explicitly declares all three
    # equality cases; no benchmark task or solver response is manufactured.
    summaries = {}
    for bench in p.active_benches(v.CONFIGURATION):
        tasks = [{'task_id': mode, 'public': ({'instruction': '', 'input_files': ['/tmp/v214-authored.xlsx'], 'answer_position': 'A1'}
                  if bench == 'spreadsheetbench' else {}), 'private': {}}
                 for mode in ('zero', 'equal-final', 'stage-only')]
        routes = {}
        for task in tasks:
            mode = task['task_id']
            enabled = () if mode == 'zero' else (first.id,) if mode == 'equal-final' else (first.id, second.id)
            routes[mode] = router.RouteLog(bench, final.sha256, digest({'fixture': mode}), {
                proc.id: {'applies': proc.id in enabled, 'enabled': proc.id in enabled,
                          'withheld': False, 'restored': False, 'shadow_fired': False, 'fault': None}
                for proc in final.procedures}, (), 'engineering_fixture')
        plan = {'tasks': tasks, 'routes': routes}
        def no_workers(*args, **kwargs):
            raise AssertionError('Derived fixture routes must not start workers')
        staged = evaluation.stage_plan(plan, final, rows['packages'], bench=bench, runtime={}, workers=no_workers)
        summaries[bench] = staged['sources']
    expected = {'zero': 'C', 'equal-final': 'F', 'stage-only': None}
    passed = rows['rows'] == ['C', 'C', 'S2', 'S2', 'S4', 'F'] and all(
        row['S2'] == ({key: 'C' for key in expected} if bench == z.BENCH else expected)
        and row['S4'] == ({key: 'C' for key in expected} if bench == z.BENCH
                         else {**expected, 'stage-only': 'S2'}) for bench, row in summaries.items())
    return {'passed': passed, 'rows': rows['rows'], 'sources': summaries,
            'model_calls': 0, 'sealed_reads': 0, 'evidence': 'engineering_fixture',
            'benchmark_effect_evidence': False}
