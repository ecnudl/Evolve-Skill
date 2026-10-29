"""Child-only five-benchmark preparation and fail-closed measured-smoke evidence.

All preparation is zero-call and never opens sealed test panels. The structural
receipt is engineering evidence only. The registered chain-G measured stages,
source pins and maximum schedule must agree before a real main-v4 manifest.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from fractions import Fraction
import hashlib
import math
from pathlib import Path
import sys

from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import (budgets, chain, evaluation, exclusion, instruction_start, manifest,
               prelaunch, profiles as p, routes, step, v210_import, v210_smoke)
from .sandbox import client as sandbox

S0_FILE = 'v211-s0.json'
STAGES = ('S0', 'S2', 'S3', 'SE6', 'SX')
RESULT = 'v211-smoke-result.json'
HISTORICAL = 'tests/fixtures/execskill/v211_parents_before.json'
# The immutable before-edit capture also recorded these two incidental local
# interpreter caches. They are not source fixtures and snapshots never copy them.
CAPTURED_GENERATED_CACHE = frozenset({
    'tests/fixtures/execskill/__pycache__/__init__.cpython-313.pyc',
    'tests/fixtures/execskill/__pycache__/items.cpython-313.pyc',
})
AMENDMENT = {
    'historical_exposure': 'unknown', 'route_history_fresh': 'unknown',
    'within_run_disjoint': True, 'decision_uses_per_slice': 1,
    'decision': 'coordinator_2026-10-29_accepts_disclosed_within_run_amendment',
    'selection_check': 'preregistered_selection_check',
    'new_supplies_authorized': False,
}


def _sha(path):
    return hashlib.sha256(safe_path(path).read_bytes()).hexdigest()


def _bind_exclusion(root, imported):
    """The child uses the persisted exclusion layout consumed by step._tail."""
    bound = {}
    for name, value in imported['exclusion_records'].items():
        target = root / (p.CANARIES if name == 'test_canaries' else exclusion.EXCLUSION_DIR + '/' + name + '.json')
        if target.exists():
            require(read_json(target) == value, 'An inherited exclusion record changed')
        else:
            write_json(target, value)
        bound[name] = {'path': str(target), 'record_sha256': value[p.RECORD_HASH]}
    return bound


def check_route_probes(value):
    from . import client, v29_route_probe
    require(isinstance(value, dict), 'The separate D readiness artifact is required')
    found = p.verified(value, 'v211-route-probes')
    require(found['configuration'] == p.MAIN_V4 and found['chain'] == 'D'
            and found['evidence'] == 'smoke' and found['passed'] is True and found['calls'] == 15
            and found['code_sha256'] == digest(manifest.pin_code(manifest.REPO))
            and set(found['benches']) == set(p.BENCHES),
            'D readiness requires all five measured Northgate probes on this source')
    for bench, row in found['benches'].items():
        ceiling = row.get('request_ceiling')
        nominal = p.solver_tokens(p.CHAINS['D'], bench)
        receipts = row.get('receipts', [])
        counts = [(r.get('usage') or {}).get('completion_tokens') for r in receipts]
        require(type(ceiling) is int and ceiling >= nominal
            and len(receipts) == 3
            and all(type(count) is int and 0 < count <= ceiling for count in counts)
            and row.get('longest') == max(counts)
            and all(r.get('passed') is True and r.get('route') == client.ROUTE_B
                and r.get('returned_model') in client.NORTHGATE_RESPONSE_MODEL_IDS
                and isinstance(r.get('request_sha256'), str) and len(r['request_sha256']) == 64
                and all(c in '0123456789abcdef' for c in r['request_sha256']) for r in receipts),
            'D probe receipts require actual model responses inside the pinned request ceiling')
        require(row['bench'] == bench and row['provider'] == 'northgate' and row['route'] == 'B'
            and row['model'] == client.NORTHGATE_MODEL and row['max_tokens'] == nominal
            and row['passed'] is True and row['first_response_confirmed'] is True and row['calls'] == 3
            and len(row['receipts']) == 3 and all(r['passed'] for r in row['receipts'])
            and row['prompt'] == v29_route_probe.prompt_pins()
            and row['code_sha256'] == found['code_sha256']
            and row['ledger_bound'] == p.ledger_bound(p.CHAINS['D'], bench, branch='N', longest=row['longest']),
            'Every D benchmark binds provider/model, request ceiling and a measured response bound')
    return found


def snapshot(out, *, source, git_head, configuration=p.MAIN_V4):
    require(p.is_v211(configuration), 'The main-v4 snapshot')
    return v210_smoke.snapshot(out, source=source, git_head=git_head, configuration=configuration)


def historical_fingerprints(root):
    """Recompute every captured legacy value and fixture; no historical writes."""
    from skillopt.coevo5.outcomes import Verdict
    from . import audit, judge
    root = safe_path(root)
    before = read_json(root / HISTORICAL)
    require(len(before['configurations']) == 32, 'All 32 historical configurations were captured before edits')
    found = {}
    for name, row in before['configurations'].items():
        found[name] = manifest._plain({
            'features': {key: getattr(p, key).get(name, {'unregistered': True}) for key in row['features']},
            'registered': manifest.registered(name), 'prompts': manifest.prompt_sha(name),
            'roles': manifest.role_settings(name), 'budgets': {c: budgets.chain_caps(c, name) for c in p.CHAINS},
            'call_budgets': [p.ENGINEER_CALL_BUDGETS[name], p.TRAIN_ENGINEER_CALL_BUDGETS[name]],
            'units': list(step.training_units(name)), 'runtime': row['runtime'],
            'k1_judge': {label: judge.judge('alfworld', {'game_file': 'authored'}, {}, case['prediction'],
                runtime=row['runtime'], score=case['score'], verdict=Verdict(**case['verdict']))
                for label, case in before['k1_episodes'].items()},
            'audit_views': {key: audit.public_view('alfworld', view)
                for key, view in before['audit_public_inputs'].items()},
            'audit_keys': {key: audit.situation_key({'item': before['audit_item'], 'step': int(key),
                'view': audit.public_view('alfworld', view)}) for key, view in before['audit_public_inputs'].items()}})
        require(found[name] == row, 'Historical configuration changed: ' + name)
    for name, tables in before['profile_tables'].items():
        require(manifest._plain({key: getattr(p, key)[name] for key in tables}) == tables,
                'Historical profile tables changed: ' + name)
    fixtures = {path: sha for path, sha in before['fixtures_sha256'].items()
                if path not in CAPTURED_GENERATED_CACHE}
    for path, sha in fixtures.items():
        require(_sha(root / path) == sha, 'Historical fixture changed: ' + path)
    return {'configurations': {name: digest(row) for name, row in found.items()},
            'capture_sha256': _sha(root / HISTORICAL), 'fixtures_sha256': fixtures,
            'excluded_generated_cache': {path: before['fixtures_sha256'][path]
                                         for path in sorted(CAPTURED_GENERATED_CACHE)},
            'passed': True, 'count': 32}


def protected_ids(imported):
    from skillopt.coevo5.data import TestAccess
    from . import v211_protection
    return v211_protection.derive(imported, access=TestAccess('v211-s0-protected-ids'))


def allocations(imported, *, protected=None):
    """Read pinned training supplies only; retain the actual exclusion qualification."""
    from types import SimpleNamespace
    from . import v211_allocation, v211_protection
    data = imported['data']
    protected = protected_ids(imported) if protected is None else v211_protection.validate(protected)
    v211_protection.check_items('alfworld', manifest._items(data['pools']['alfworld'], 'alfworld'),
                               protected['alfworld']['id_hashes'])
    pools = {bench: manifest._items(data['pools'][bench], bench) for bench in p.BENCHES[:-1]}
    # _tail enforces the source file hash and the persisted exclusion record identity.
    carrier = SimpleNamespace(setting=SimpleNamespace(extra={'searchqa_tail': manifest._searchqa_tail(data)}))
    tail, kept = step._tail(carrier)
    output = {}
    for bench, pool in pools.items():
        _, output[bench] = v211_allocation.allocate(bench, pool,
            tail=tail if bench == 'searchqa' else (), kept=kept if bench == 'searchqa' else None,
            protected_hashes=protected[bench]['id_hashes'], source_pins={'pool': deepcopy(data['pools'][bench]),
                'protected_ids': deepcopy(protected[bench]),
                'tail': deepcopy(data.get('searchqa_tail')) if bench == 'searchqa' else None,
                'exclusions': deepcopy(data['exclusion']),
                'qualification': deepcopy(imported['sheet_qualification']) if bench == 'spreadsheetbench' else None},
            provenance={key: AMENDMENT[key] for key in ('historical_exposure', 'route_history_fresh',
                'within_run_disjoint', 'decision_uses_per_slice')})
    return output


def collect_s0(out, *, preparation_file, root, snapshot_root=None, selftest, sheet_runtime=None, checks=None):
    from . import engineer_v211
    out, root = safe_path(out), safe_path(root)
    require(not (out / S0_FILE).exists() and not out.is_relative_to(manifest.REPO),
            'A new S0 outside the checkout')
    allowed = evaluation.consent(root / 'shared', p.MAIN_V4)
    imported = v210_smoke.preparation(preparation_file)
    cards = instruction_start.active_cards(imported['cards'], p.MAIN_V4)
    tested = p.verified(read_json(selftest), 'sandbox-selftest')
    require(tested.get('passed') is True and set(tested['measured']) == manifest.MEASURED_FIELDS,
            'A passing measured sandbox selftest')
    source = safe_path(snapshot_root or manifest.REPO)
    from . import sheet_runtime as launch_sheet
    sheet = launch_sheet.read(sheet_runtime, snapshot_root=source) if sheet_runtime is not None else None
    history = historical_fingerprints(source)
    protected = protected_ids(imported)
    allocated = allocations(imported, protected=protected)
    checked = prelaunch.zero_call_checks(source, python=sys.executable) if checks is None else checks
    value = p.record('v211-s0', 'smoke', {
        'configuration': p.MAIN_V4, 'root': str(root), **imported,
        'launch_sheet_runtime': sheet,
        'active_cards': cards, 'instructions': instruction_start.pins(),
        'instruction_start': instruction_start.START, 'blank_arm': instruction_start.blank_definition(),
        'consent': deepcopy(allowed), 'consent_sha256': digest(allowed),
        'alfworld_v11_import': v210_import.pins(), 'historical_fingerprints': history,
        'allocations': allocated, 'protected_ids': protected, 'freshness_amendment': deepcopy(AMENDMENT),
        'v211_prompt_pins': engineer_v211.pins(), 'smoke_schedule': schedule(),
        'sandbox_required': True, 'sandbox': tested[p.RECORD_HASH],
        'limits': deepcopy(tested['limits']), 'measured': deepcopy(tested['measured']),
        'pytest': checked, 'sealed_reads': 0, 'training_units': list(step.training_units(p.MAIN_V4)),
        'snapshot_root': str(source),
        'snapshot_sha256': hashlib.sha256(prelaunch.sha256_list(source).encode()).hexdigest(),
        'passed': checked.get('passed') is True})
    write_json(out / S0_FILE, value)
    return value


def schedule():
    """The reviewed finite schedule is fixed before any paid smoke dispatch."""
    from . import v211_limits, v211_stages
    return {'configuration': p.MAIN_V4, 'solver_chain': 'G', 'solver_model': p.CHAINS['G'],
        'stages': list(STAGES), 'D_S1': False, 'benchmarks': list(p.BENCHES),
        'learned_benchmarks': list(p.BENCHES[:-1]), 'rounds': 6, 'patience': 4,
        'S2': {'searchqa': 20, 'officeqa': 20, 'livemath': 20, 'spreadsheetbench': 20, 'alfworld': 6},
        'S3': {b: {'run_items': 4, 'real_engineer_rounds': 1, 'confirm_items': 2,
                   'confirm_exercise': True, 'judges': ['G', 'D']} for b in p.BENCHES[:-1]},
        'authored_S3_controls': {'version': 'main-v4-selection-audit-controls-1', 'model_calls': 0,
            'confirmation': ['same-round identical receipt and unchanged ledger',
                             'cross-round repeated slice refused before dispatch'],
            'audit2': ['actual train/confirm public situations', 'stale note/package-source refusal',
                      'injected contradiction agreement and removal without engineer calls'],
            'evidence': 'engineering_fixture', 'excluded_from_cost_projection': True},
        'SX': {'searchqa_run': 100, 'searchqa_accept': 160, 'supply': 'reserved_smoke'},
        'scarce_supply': 'authored_fixtures_only',
        'caps': manifest._plain(v211_limits.smoke_identity()),
        'role_cost_probes': v211_stages.role_probe_pins(), 'unit_calls': {'single': 31, 'train': 41},
        'test_items': {b: p.read_items(p.MAIN_V4, b) for b in p.BENCHES},
        'test_arms': ['F', 'C', 'B'], 'maximum_schedule': manifest._plain(v211_limits.identity())}


def _stage_path(root, stage):
    return safe_path(root) / 'G' / 'v211-smoke' / (stage + '.json')


def checked_stage(path, *, run=None, stage=None):
    found = p.verified(read_json(path), 'v211-smoke-stage')
    require(found['configuration'] == p.MAIN_V4 and found['chain'] == 'G'
        and found['schedule_sha256'] == digest(schedule())
        and (run is None or found['run'] == run) and (stage is None or found['stage'] == stage),
        'A stage binds the current main-v4 chain-G schedule and manifest')
    return found


def measured_readiness(root, *, source_sha256, s0_sha256):
    """Structural, synthetic, stale, incomplete or failed smoke cannot authorize launch."""
    root = safe_path(root)
    found = p.verified(read_json(root / RESULT), 'v211-smoke-result')
    require(found['evidence'] == 'smoke' and found['passed'] is True
        and found['configuration'] == p.MAIN_V4 and found['chain'] == 'G'
        and found['schedule_sha256'] == digest(schedule())
        and found['snapshot_sha256'] == source_sha256 and found['s0_sha256'] == s0_sha256,
        'Real main-v4 requires measured chain-G smoke on the same source, S0 and schedule')
    require(set(found['stages']) == set(STAGES), 'Measured readiness requires S0/S2/S3/SE6/SX')
    for stage in STAGES:
        row = checked_stage(_stage_path(root, stage), run=found['run'], stage=stage)
        require(row[p.RECORD_HASH] == found['stages'][stage] and row['result']['passed'] is True
            and row['evidence'] == 'smoke' and row.get('measured') is True
            and row['snapshot_sha256'] == found['snapshot_sha256'] and row['s0_sha256'] == found['s0_sha256']
            and row['manifest_sha256'] == found['run'],
            'Every measured stage must pass without fixture or structural substitution')
    se6 = checked_stage(_stage_path(root, 'SE6'))['result']
    require(set(se6['per_cell']) == set(p.BENCHES) and se6['all_scopes_projected'] is True,
            'Measured SE6 covers every benchmark and maximum-schedule scope')
    return found, se6


def make_manifest(out, *, root, s0_file, provenance, roles_repo, route_b_env, sheet_runtime,
                  smoke_chain=None, measured_smoke=None, route_probes=None, environment_found=None):
    from . import engineer_v211
    checked = p.verified(read_json(s0_file), 'v211-s0')
    require(checked['passed'] and checked['configuration'] == p.MAIN_V4,
            'A passing main-v4 S0')
    root = safe_path(root)
    require(smoke_chain in (None, 'G'), 'The main-v4 measured smoke uses chain G only')
    require(smoke_chain == 'G' or str(root) == p.RUN_ROOTS[p.MAIN_V4], 'The registered real main-v4 root')
    allowed = evaluation.consent(root / 'shared', p.MAIN_V4)
    require(digest(allowed) == checked['consent_sha256'], 'S0 and manifest bind the same exact consent')
    imported = v210_smoke.preparation(checked['registration']['preparation']['path'])
    require(all(checked[key] == value for key, value in imported.items()), 'Preparation still matches S0')
    from . import sheet_runtime as launch_sheet
    sheet = launch_sheet.for_manifest(sheet_runtime, checked, snapshot_root=manifest.REPO)
    protected = protected_ids(imported)
    require(checked['protected_ids'] == protected, 'S0 protected-ID source identity remains unchanged')
    require(checked['allocations'] == allocations(imported, protected=protected),
            'S0 allocation and provenance remain unchanged')
    require(checked['v211_prompt_pins'] == engineer_v211.pins()
        and checked['smoke_schedule'] == schedule() and checked['freshness_amendment'] == AMENDMENT,
        'S0 pins the child prompts, schedule and accepted freshness amendment')
    require(checked['instructions'] == instruction_start.pins()
        and checked['active_cards'] == instruction_start.active_cards(imported['cards'], p.MAIN_V4)
        and checked['alfworld_v11_import'] == v210_import.pins(), 'S0 instruction and import hashes remain unchanged')
    source = hashlib.sha256(prelaunch.sha256_list(manifest.REPO).encode()).hexdigest()
    proven = read_json(provenance)
    require(checked['snapshot_sha256'] == source == proven.get('sha256_list_sha256')
        and safe_path(checked['snapshot_root']) == manifest.REPO
        and safe_path(proven['snapshot_root']) == manifest.REPO,
        'S0 and provenance certify the current source snapshot')
    require(checked['historical_fingerprints'] == historical_fingerprints(manifest.REPO),
            'The historical fingerprints remain unchanged since S0')
    per_cell = {b: {'card': p.CELL_ANCHORS[b][1], 'procedure_assumed': True} for b in p.BENCHES}
    terms = p.read_estimate_terms(per_cell, 1, p.MAIN_V4)
    readiness = {'measured': False, 'basis': 'smoke_manifest_only'}
    probes = None
    if smoke_chain is None:
        require(measured_smoke is not None, 'Real main-v4 requires measured smoke; structural smoke is insufficient')
        receipt, se6 = measured_readiness(measured_smoke, source_sha256=source, s0_sha256=checked[p.RECORD_HASH])
        terms = {b: Fraction(v) for b, v in se6['read_terms'].items()}
        readiness = {'measured': True, 'receipt': receipt}
        require(route_probes is not None, 'Real main-v4 requires separate D route probes')
        probes = check_route_probes(read_json(route_probes))
    longest = max(row['longest'] for row in probes['benches'].values()) if probes else routes.S1B_CEILING
    blocks = {'G': manifest.solver_block('G', env_path=roles_repo, configuration=p.MAIN_V4),
        'D': manifest.solver_block('D', env_path=route_b_env, branch='N', longest=longest,
                                  configuration=p.MAIN_V4)}
    data = {**imported['data'], 'exclusion': _bind_exclusion(root, imported),
        'launch_sheet_runtime': sheet, 'inherited_sheet_runtime': launch_sheet.inherited(imported),
        'v211_preparation': imported['registration'], 'v211_s0': checked,
        's0_sha256': checked[p.RECORD_HASH], 'snapshot_sha256': source,
        'allocations': deepcopy(checked['allocations']), 'protected_ids': deepcopy(protected),
        'freshness_amendment': deepcopy(AMENDMENT),
        'v211_prompt_pins': engineer_v211.pins(), 'smoke_schedule': schedule(),
        'launchable_chains': ['G'] if smoke_chain else ['G', 'D'], 'readiness': readiness,
        'route_probes': probes,
        'test_read_estimate': {c: math.ceil(sum(terms.values())) for c in p.CHAINS},
        'test_read_terms': {c: {b: str(v) for b, v in terms.items()} for c in p.CHAINS}}
    return manifest.make(out, evidence='smoke' if smoke_chain else p.REAL_RUN_EVIDENCE[p.MAIN_V4],
        measured=checked['measured'], limits={k: sandbox.Limits(**v) for k, v in checked['limits'].items()},
        environment_found=environment_found, configuration=p.MAIN_V4, root=str(root), data=data,
        cards=imported['cards'], contracts=imported['contracts'],
        runtime={**imported['runtime'], 'spreadsheetbench': sheet['runtime']},
        sheet_qualification=sheet['qualification'], fixtures=imported['fixtures'], provenance=proven,
        clients={'solver': blocks, 'roles': manifest.role_settings(p.MAIN_V4), 'routes': {'D': {'B':
            routes.pin('D', 'B', env_path=route_b_env, solver_block=blocks['D'], configuration=p.MAIN_V4)}}})


def structural_smoke(manifest_path, *, out):
    value = manifest.load(manifest_path, verify=False)
    require(value['configuration'] == p.MAIN_V4, 'The main-v4 manifest')
    manifest.verify_code(value)
    allowed = evaluation.consent(safe_path(value['root']) / 'shared', p.MAIN_V4)
    result = p.record('v211-structural-smoke', 'engineering_fixture', {
        'configuration': p.MAIN_V4, 'manifest': value[p.RECORD_HASH], 'passed': True,
        'model_calls': 0, 'sealed_reads': 0, 'measured_readiness': False,
        'consent_sha256': digest(allowed), 'schedule_sha256': digest(schedule()),
        'allocations_sha256': digest(value['data']['allocations']),
        'read_arms': ['F', 'C', 'B'], 'scope': 'four learned steps + imported ALFWorld'})
    require(not safe_path(out).exists(), 'A structural smoke receipt is written once')
    write_json(out, result)
    return result


def _stage_setting(setting, stage):
    """Isolated ledgers declare the independently derived stage ceilings."""
    from dataclasses import replace
    from skillopt.coevo5.budget import Budget
    from . import v211_limits
    cap = v211_limits.smoke_caps(stage)
    ledger = Budget(safe_path(setting.root) / 'G' / 'v211-smoke' / stage / 'stage-ledger')
    declared = {'overall': cap['overall'], 'G:solver': cap['solver'], 'G:glm': max(1, cap['method'])}
    if stage == 'S3':
        for k, bench in enumerate(p.BENCHES[:-1], 1):
            for kind in budgets.step_kinds(p.MAIN_V4):
                declared[budgets.solver_scopes('G', bench, k, kind)[-1]] = cap['solver_by_bench'][bench]
            for role in budgets.ROLES:
                declared[budgets.glm_scopes('G', role, bench, k)[-1]] = cap['method_by_bench'][bench]
            for judge in ('G', 'D'):
                declared[budgets.audit_scopes('G', judge, bench, k)[-1]] = cap['audit_caps'][bench]['audit_'+judge.lower()]
    ledger.declare(declared)
    return replace(setting, budget=ledger)


def run_stage(manifest_path, stage, *, _setting=None, _services=None):
    """Execute one ordered stage. Tests may inject only engineering-fixture settings."""
    from skillopt.coevo5.cells import exclusive
    from . import v211_stages, v211_smoke_controls
    require(stage in STAGES, 'A registered main-v4 smoke stage')
    m = manifest.load(manifest_path, verify=_setting is None)
    require(m['configuration'] == p.MAIN_V4 and m['evidence'] == 'smoke'
            and m['data']['launchable_chains'] == ['G'], 'The measured runner uses the chain-G smoke manifest')
    if _setting is None:
        setting = manifest.setting_of(m, 'G', path=manifest_path)
        services = manifest.services_of(m, 'G', setting=setting)
    else:
        require(_setting.evidence == 'engineering_fixture' and _services is not None,
                'Injected smoke services are engineering fixtures, never readiness')
        setting, services = _setting, _services
    path = _stage_path(setting.root, stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    with exclusive(path.parent / '.stage-lock'):
        if path.exists():
            found = checked_stage(path, run=setting.run, stage=stage)
            require(found['manifest_sha256'] == m[p.RECORD_HASH], 'A smoke stage cannot change its manifest')
            return found
        for previous in STAGES[:STAGES.index(stage)]:
            require(checked_stage(_stage_path(setting.root, previous), run=setting.run,
                                  stage=previous)['result']['passed'] is True,
                    'Earlier smoke stages must pass before dispatch')
        if stage == 'S0':
            s0 = p.verified(m['data']['v211_s0'], 'v211-s0')
            result = {'passed': s0['passed'], 's0_sha256': s0[p.RECORD_HASH],
                'sandbox_selftest': s0['sandbox'], 'historical_configurations': s0['historical_fingerprints']['count'],
                'sealed_reads': 0, 'model_calls': 0}
        elif stage == 'SE6':
            result = v211_stages.projection(m,
                checked_stage(_stage_path(setting.root, 'S2'))['result'],
                checked_stage(_stage_path(setting.root, 'S3'))['result'])
        elif stage == 'SX':
            result = v211_stages.sx(setting, services)
        else:
            local = _stage_setting(setting, stage)
            if stage == 'S2':
                v211_stages.fixture_pools(local)
                controls = v211_smoke_controls.controls(path.parent / 'fixtures')
                require(controls['passed'], 'The authored calculator/repair/fallback controls must pass')
                result = {**v211_stages.s2(local), 'authored_controls': controls}
            else:
                result = v211_stages.s3(local, services)
            ledger = local.budget.snapshot()
            clean = all(row.get('open') == 0 and row.get('settled', 0) <= row.get('cap', -1)
                        for row in ledger.values())
            result.update(ledger=ledger, passed=result['passed'] and clean)
        value = p.record('v211-smoke-stage', setting.evidence, {
            'configuration': p.MAIN_V4, 'chain': 'G', 'stage': stage, 'run': setting.run,
            'manifest_sha256': m[p.RECORD_HASH], 'schedule_sha256': digest(schedule()),
            'snapshot_sha256': m['data']['snapshot_sha256'], 's0_sha256': m['data']['s0_sha256'],
            'measured': setting.evidence == 'smoke', 'benchmark_effect_evidence': False, 'result': result})
        write_json(path, value)
        return value


def summarize(manifest_path):
    """Seal readiness only from every persisted passing measured stage."""
    m = manifest.load(manifest_path)
    require(m['configuration'] == p.MAIN_V4 and m['evidence'] == 'smoke', 'A main-v4 smoke manifest')
    stages = {stage: checked_stage(_stage_path(m['root'], stage), run=m[p.RECORD_HASH], stage=stage)
              for stage in STAGES}
    require(all(row['manifest_sha256'] == m[p.RECORD_HASH] and row['measured'] is True
                and row['evidence'] == 'smoke' and row['result']['passed'] is True for row in stages.values()),
            'Every stage must be a passing measured receipt of this manifest')
    value = p.record('v211-smoke-result', 'smoke', {'configuration': p.MAIN_V4, 'chain': 'G',
        'run': m[p.RECORD_HASH], 'manifest_sha256': m[p.RECORD_HASH], 'schedule_sha256': digest(schedule()),
        'snapshot_sha256': m['data']['snapshot_sha256'], 's0_sha256': m['data']['s0_sha256'],
        'stages': {stage: row[p.RECORD_HASH] for stage, row in stages.items()}, 'passed': True,
        'benchmark_effect_evidence': False, 'D_readiness': 'requires separate five-benchmark route probes'})
    target = safe_path(m['root']) / RESULT
    if target.exists():
        require(read_json(target) == value, 'The smoke summary is immutable')
    else:
        write_json(target, value)
    measured_readiness(m['root'], source_sha256=m['data']['snapshot_sha256'], s0_sha256=m['data']['s0_sha256'])
    return value


def selftest(out, *, preparation_file):
    """Measure worker/public views and the historical native probe on training inputs."""
    from . import s0, smoke
    out = safe_path(out)
    require(not (out / smoke.SELFTEST).exists(), 'A self-test is written once')
    imported = v210_smoke.preparation(preparation_file)
    item_files, workbooks = [], []
    for bench in p.BENCHES:
        path = out / 'training-views' / (bench + '.json')
        items = manifest._items(imported['data']['pools'][bench], bench)
        if path.exists():
            require(read_json(path) == items, 'The selftest training view pin cannot change')
        else:
            write_json(path, items)
        item_files.append(path)
        if bench == 'spreadsheetbench':
            workbooks.extend(safe_path(name) for item in items for name in item['public'].get('input_files') or [])
    require(workbooks, 'The native peak measurement requires a pinned training workbook')
    largest = max(workbooks, key=lambda path: path.stat().st_size)
    # Preserve the inherited write-once receipt and its diagnostic latency/count.
    # The public child receipt has the exact manifest measurement schema.
    worker_out = out / 'worker-selftest'
    tested = smoke.sandbox_selftest(worker_out, item_files=item_files, configuration=p.MAIN_V4)
    peak = s0.native_peak(largest, sandbox.Docker())
    require(type(peak) is int and peak > 0, 'A positive measured native peak RSS is required')
    measured = {'vsz_kib': tested['measured']['vsz_kib'], 'rss_kib': tested['measured']['rss_kib'],
                'view_bytes_p99': tested['measured']['view_bytes_p99'], 'native_peak_rss_kib': peak}
    value = p.record('sandbox-selftest', tested['evidence'], {
        **{key: deepcopy(found) for key, found in tested.items()
           if key not in ('version', 'evidence', p.RECORD_HASH, 'measured')},
        'measured': measured,
        'measurement_sources': {
            'worker_selftest': {'path': str(worker_out / smoke.SELFTEST), 'record_sha256': tested[p.RECORD_HASH]},
            'native_peak': {'collector': 'skillopt.execskill.s0.native_peak',
                            'probe_sha256': hashlib.sha256(s0.NATIVE_PROBE.encode()).hexdigest(),
                            'workbook': {'path': str(largest), 'sha256': _sha(largest)}}}})
    write_json(out / smoke.SELFTEST, value)
    return value
