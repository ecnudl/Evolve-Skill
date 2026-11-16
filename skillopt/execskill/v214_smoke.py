"""Lean, source-bound main-v5 smoke and launch preparation.

S0 and SX are zero-call checks. Real readiness requires both measured chain
routes; authored structural receipts can never authorize a real manifest.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import hashlib
import math
import sys

from skillopt.coevo5.cells import exclusive
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest
from . import budgets, evaluation, manifest, prelaunch, profiles as p, routes, v210_import, v210_smoke, v211_smoke
from .sandbox import client as sandbox

CONFIGURATION = 'main-v5'
S0_FILE = 'v214-s0.json'
STAGES = ('S0', 'S1', 'S2', 'S3', 'SE6', 'SX')
RESULT = 'v214-smoke-result.json'
S2_ITEMS = {'searchqa': 20, 'officeqa': 20, 'zebralogic': 10, 'spreadsheetbench': 20, 'alfworld': 6}


def _options(configuration):
    require(configuration in (CONFIGURATION, p.IMPLANT_V5, p.MAIN_V6, p.CROSS_V5, p.SEARCHQA_HP_V6, p.MAIN_V7, p.MAIN_V8, p.MAIN_V9, p.MAIN_V10), 'A main-v5 or implant-v5 configuration')
    return {} if configuration == CONFIGURATION else {'configuration': configuration}


def _identity(configuration):
    if p.is_v226(configuration):
        return p.main_v10_identity()
    if p.is_v225(configuration):
        return p.main_v9_identity()
    if p.is_v222(configuration):
        return p.main_v8_identity()
    if p.is_v221(configuration):
        return p.main_v7_identity()
    if p.is_v220(configuration):
        return p.searchqa_hp_v6_identity()
    return (p.cross_v5_identity() if p.is_v219(configuration) else
            p.main_v6_identity() if p.is_v218(configuration) else
            p.implant_v5_identity() if p.is_implant_v5(configuration) else p.main_v5_identity())


def stages_of(configuration=CONFIGURATION):
    if p.is_v220(configuration):
        from . import v220_smoke
        return v220_smoke.STAGES
    return ('S0', 'S1', 'S2', 'SE6') if p.is_implant_v5(configuration) else STAGES


def prepare_consent(root, configuration, *, consent_file=None):
    """Copy the supplied owner record before this no-learning chain can launch."""
    if p.is_v226(configuration):
        manifest._check_run_root(root, configuration, 'smoke')
        manifest._check_frozen_paths(configuration, consent_file, safe_path(root)/'shared/consent.json')
    root = safe_path(root)
    if (p.is_implant_v5(configuration) or p.is_v218(configuration) or p.is_v220(configuration)) and consent_file is not None:
        source = safe_path(consent_file)
        value = read_json(source)
        require(isinstance(value, dict) and set(value) == p.CONSENT_FIELDS
                and value.get('by') == 'owner' and value.get('test_evaluation') is True
                and value.get('sheet_test_qualification') is (not p.is_v220(configuration))
                and value.get('multi_arm_arms') == list(p.read_arms_of(configuration))
                and isinstance(value.get('date'), str) and value['date'].strip()
                and isinstance(value.get('note'), str) and value['note'].strip(),
                'The supplied implant consent has the exact owner-approved five-benchmark shape')
        target = root / 'shared/consent.json'
        if target.exists():
            require(read_json(target) == value, 'Preparation does not replace different owner consent')
        else:
            write_json(target, value)
    return evaluation.consent(root / 'shared', configuration)


def implant_solver_probe(first, chain, probe=None):
    """Bind the actual first response as well as D's inherited length probe."""
    from . import client
    first = p.verified(first, 'first-call')
    echo = client.NORTHGATE_RESPONSE_MODEL_IDS if chain == 'D' else {p.CHAINS['G']}
    require(first.get('passed') is True and first.get('identity', {}).get('chain') == chain
            and first.get('model') == p.CHAINS[chain] and first.get('returned_model') in echo
            and first.get('bench') == 'searchqa'
            and type(first.get('charged')) is int and first['charged'] > 0
            and isinstance(first.get('request_sha256'), str) and len(first['request_sha256']) == 64,
            'The implant smoke requires its confirmed first solver response')
    if chain == 'D':
        checked_s1_probe(probe)
        return {**probe, 'first_call': first}
    require(first.get('returned_model') == p.CHAINS['G']
            and first.get('bound') == first.get('max_tokens') == p.ledger_bound(p.CHAINS['G'], 'searchqa'),
            'The G implant probe uses the fixed main-v5 solver bound')
    return {'passed': True, 'chain': chain, 'model': p.CHAINS[chain], 'first_call': first}


def check_implant_probe(chain, probe):
    require(isinstance(probe, dict), 'The implant smoke retains its measured solver probe')
    length = {key: value for key, value in probe.items() if key != 'first_call'} if chain == 'D' else None
    require(probe == implant_solver_probe(probe.get('first_call'), chain, length),
            'The implant probe is the confirmed response and unchanged route probe')
    return probe


def prompt_pins(configuration=CONFIGURATION):
    """The exact inherited strings, selected by benchmark, never rewritten."""
    if p.is_v220(configuration):
        from . import v220_smoke
        return v220_smoke.prompt_pins()
    if p.is_v221(configuration):
        from . import engineer_v221
        found = prompt_pins(p.MAIN_V6)
        pins = engineer_v221.prompt_pins(configuration) if p.is_v222(configuration) else engineer_v221.prompt_pins()
        found['v221'] = pins
        found['engineer'] = {b: hashlib.sha256(p.engineer_prompt(configuration, b, 'single').encode()).hexdigest()
                             for b in p.active_benches(configuration)[:-1]}
        found['v2']['engineer'] = {b: hashlib.sha256(p.engineer_prompt(configuration, b, 'train').encode()).hexdigest()
                                   for b in p.active_benches(configuration)[:-1]}
        if p.is_v225(configuration):
            from . import v225_cards
            found['v225'] = v225_cards.prompt_pins()
        return found
    zebra_configuration = p.ZEBRA_PC_V15 if p.is_v218(configuration) else p.ZEBRA_PC_V13
    old, zebra = manifest.prompt_sha(p.MAIN_V4), manifest.prompt_sha(zebra_configuration)
    selected = ('searchqa', 'officeqa', 'spreadsheetbench')
    return {'parents': {'main-v4': old, zebra_configuration: zebra},
        'engineer': {**{b: old['engineer'][b] for b in selected}, 'zebralogic': zebra['engineer']},
        'v2': {'engineer': {**{b: old['v2']['engineer'][b] for b in selected},
                            'zebralogic': zebra['v2']['engineer']}},
        'dispatch': {b: p.machinery_configuration(configuration, b) for b in p.active_benches(configuration)}}


def schedule(configuration=CONFIGURATION):
    if p.is_v225(configuration):
        from . import v225_smoke
        return v225_smoke.schedule(**({'configuration': configuration} if p.is_v226(configuration) else {}))
    if p.is_v222(configuration):
        from . import v222_cards, v222_gate
        value = schedule(p.MAIN_V7)
        value.update(configuration=configuration, S2_arms=['C0'], maximum_schedule=manifest._plain(_identity(configuration)))
        value['decomposition'] = {'items': {b: 20 if b == 'alfworld' else 100 for b in v222_cards.BENCHES},
            'arms': ['C_hist', 'C'], 'once': True, 'fallback_only_arm': 'C', 'card_pins': v222_cards.manifest_pins()}
        value['cross_narrowing'] = {'cases': ['harmful_format', 'benign'],
            'paired_item_calls_max': 2 * v222_gate.MAX_PAIRED_ITEM_CALLS,
            'paired_item_calls_per_case_max': v222_gate.MAX_PAIRED_ITEM_CALLS,
            'actual_fired_pairs_required': True, 'measured_harm_and_narrowing_required': False,
            'narrow_when_harm_measured': True, 'no_measured_harm_reason': 'no_measured_harm'}
        value['SX']['purpose'] += '; structural own-only instruction segments'
        value['SE6']['procedure_cost'] = 'registered factor over measured C0'
        return value
    if p.is_v220(configuration):
        from . import v220_smoke
        return v220_smoke.schedule()
    if p.is_implant_v5(configuration):
        found = schedule()
        found.update(configuration=configuration, stages=list(stages_of(configuration)),
                     maximum_schedule=manifest._plain(_identity(configuration)))
        found.pop('S3')
        found.pop('SX')
        if p.is_v219(configuration):
            from . import v219_read
            found['S2_arms'] = {bench: list(v219_read.labels(bench)) for bench in p.active_benches(configuration)}
            found['S2_cross_items_per_bench'] = 1
            found['SE6'] = {'procedure_cost': 'max(registered factor over measured card, measured procedure)',
                'card_cost': 'maximum dispatched per-arm mean; shared cells excluded',
                'stage_packages': 0, 'gate': 'worst full cross read plus one read-unit retry and reservation'}
        return found
    return {'configuration': configuration, 'chains': ['G', 'D'], 'stages': list(stages_of(configuration)),
        'benchmarks': list(p.active_benches(configuration)), 'S2': dict(S2_ITEMS), 'S2_arms': ['C'],
        'S1': {'G': 'one first reply; fixed registered GLM bound',
               'D': 'one first reply plus three inherited Zebra northgate length probes'},
        'S3': {'engineer_calls': 1, 'benchmark': 'searchqa', 'repairs': 0, 'other_role_calls': 0},
        'SE6': {'procedure_cost': 'registered factor over measured C', 'stage_packages': 4,
                'gate': 'worst full read plus one reservation'},
        'SX': {'model_calls': 0, 'evidence': 'engineering_fixture', 'purpose': ('three-stage rule, early acceptance, split merge, audit non-drop, infrastructure retry'
                          if p.is_v221(configuration) else 'stage rows and cell sharing')},
        'maximum_schedule': manifest._plain(_identity(configuration))}


def snapshot(out, *, source, git_head, configuration=CONFIGURATION):
    if p.is_v226(configuration):
        manifest._check_frozen_paths(configuration, out, source)
    return v210_smoke.snapshot(out, source=source, git_head=git_head, configuration=configuration)


def _source(root):
    return hashlib.sha256(prelaunch.sha256_list(root).encode()).hexdigest()


def collect_s0(out, *, preparation_file, zebra_pool=None, zebra_split_manifest=None, root, snapshot_root=None,
               selftest, sheet_runtime=None, checks=None, configuration=CONFIGURATION, consent_file=None,
               main_v6_root=None, v222_practice_supply=None):
    if p.is_v226(configuration):
        manifest._check_run_root(root, configuration, 'smoke')
        manifest._check_frozen_paths(configuration, out, preparation_file, zebra_pool, zebra_split_manifest,
                                     snapshot_root, selftest, sheet_runtime, consent_file, v222_practice_supply)
    if p.is_v220(configuration):
        from . import v220_smoke
        return v220_smoke.collect_s0(out, preparation_file=preparation_file, root=root, selftest=selftest,
            main_v6_root=main_v6_root or p.MAIN_V6_ROOT, snapshot_root=snapshot_root, checks=checks, consent_file=consent_file)
    from . import engineer_v211, instruction_start, sheet_runtime as launch_sheet, v214_preparation
    out, root, source = safe_path(out), safe_path(root), safe_path(snapshot_root or manifest.REPO)
    require(not (out / S0_FILE).exists() and not out.is_relative_to(manifest.REPO),
            'A new S0 outside the checkout')
    imported = v214_preparation.preparation(preparation_file, zebra_pool=zebra_pool,
                                            zebra_split_manifest=zebra_split_manifest, **_options(configuration),
                                            **({'v222_practice_supply': v222_practice_supply} if p.is_v222(configuration) else {}))
    tested = p.verified(read_json(selftest), 'sandbox-selftest')
    require(tested.get('passed') is True and set(tested['measured']) == manifest.MEASURED_FIELDS,
            'A passing measured sandbox selftest')
    if p.is_v222(configuration):
        require(tested.get('configuration') == configuration
                and tested.get('worker_sha256') == sandbox.worker_sha256(configuration=p.MAIN_V8),
                'main-v8 S0 requires measurements of its new instruction worker')
    allowed = prepare_consent(root, configuration, consent_file=consent_file)
    sheet = launch_sheet.read(sheet_runtime, snapshot_root=source)
    checked = prelaunch.zero_call_checks(source, python=sys.executable) if checks is None else checks
    # The parent fingerprint artifact is a public source fixture, never a data panel.
    fingerprint = source / ('tests/fixtures/execskill/v226_parents_before.json' if p.is_v226(configuration) else
                            'tests/fixtures/execskill/v225_parents_before.json' if p.is_v225(configuration) else
                            'tests/fixtures/execskill/v222_parents_before.json' if p.is_v222(configuration) else
                            'tests/fixtures/execskill/v221_parents_before.json' if p.is_v221(configuration) else
                            'tests/fixtures/execskill/v219_parents_before.json' if p.is_v219(configuration) else
                            'tests/fixtures/execskill/v218_parents_before.json' if p.is_v218(configuration) else
                            'tests/fixtures/execskill/v217i_parents_before.json'
                            if p.is_implant_v5(configuration) else 'tests/fixtures/execskill/v214_parents_before.json')
    require(fingerprint.is_file(), 'The before-edit parent fingerprint is included in the snapshot')
    value = p.record('v214-s0', 'smoke', {'configuration': configuration, 'root': str(root),
        'preparation': imported, 'preparation_file': str(safe_path(preparation_file)),
        'zebra_pool': str(safe_path(zebra_pool)), 'zebra_split_manifest': str(safe_path(zebra_split_manifest)),
        'launch_sheet_runtime': sheet, 'consent_sha256': digest(allowed), 'consent': allowed,
        'instructions': instruction_start.pins(), 'v211_prompt_pins': engineer_v211.pins(),
        'prompt_pins': prompt_pins(configuration), 'smoke_schedule': schedule(configuration), 'alfworld_v11_import': v210_import.pins(),
        'parents_before_sha256': hashlib.sha256(fingerprint.read_bytes()).hexdigest(),
        'sandbox': tested[p.RECORD_HASH], 'limits': tested['limits'], 'measured': tested['measured'],
        'pytest': checked, 'sealed_reads': 0, 'snapshot_root': str(source), 'snapshot_sha256': _source(source),
        'passed': tested['passed'] is True and checked.get('passed') is True,
        **({'v222_practice_supply': deepcopy(imported['data']['v222_practice_supply'])}
           if p.is_v222(configuration) else {})})
    if p.is_v225(configuration):
        from . import v225_smoke
        fields = {k:v for k,v in value.items() if k not in ('version','evidence',p.RECORD_HASH)}
        runtime = {**imported['runtime'], 'spreadsheetbench': sheet['runtime']}
        value = p.record('v214-s0', 'smoke', {**fields, 'v225': v225_smoke.pins(runtime,
            **({'configuration': configuration} if p.is_v226(configuration) else {}))})
    write_json(out / S0_FILE, value)
    return value


def solver_bounds(chain, probe=None, *, configuration=CONFIGURATION):
    require(chain in p.CHAINS, 'A registered smoke chain')
    if chain == 'D':
        require(isinstance(probe, dict) and probe.get('passed') is True and probe.get('route') == 'B'
                and type(probe.get('longest')) is int and probe['longest'] > 0,
                'S1 must produce a passing northgate probe')
        branch, longest = 'N', probe['longest']
    else:
        branch, longest = None, None
    return {'branch': branch, 'longest': longest, 'ledger_bound': {
        b: p.ledger_bound(p.CHAINS[chain], b, branch=branch, longest=longest)
        for b in p.active_benches(configuration)}}


def checked_s1_probe(probe):
    """Recompute D's recorded bound from its three actual receipt summaries."""
    from . import client, v29_route_probe, zebralogic as z
    require(isinstance(probe, dict), 'S1 requires its measured northgate probe')
    rows = probe.get('receipts', [])
    nominal = p.solver_tokens(p.CHAINS['D'], z.BENCH)
    ceiling = probe.get('request_ceiling')
    require(probe.get('passed') is True and probe.get('route') == client.ROUTE_B
            and probe.get('provider') == client.ROUTES[client.ROUTE_B].backend
            and probe.get('model') == client.NORTHGATE_MODEL and probe.get('branch') == 'N'
            and probe.get('bench') == z.BENCH and probe.get('max_tokens') == nominal
            and probe.get('prompt') == v29_route_probe.prompt_pins()
            and probe.get('calls') == v29_route_probe.PROBE_CALLS
            and isinstance(rows, list) and len(rows) == v29_route_probe.PROBE_CALLS
            and probe.get('first_response_confirmed') is True
            and probe.get('code_sha256') == digest(manifest.pin_code())
            and type(ceiling) is int and ceiling >= nominal,
            'S1 binds three measured Zebra northgate receipts, current source and frozen prompt')
    counts = []
    for row in rows:
        count = (row.get('usage') or {}).get('completion_tokens')
        request = row.get('request_sha256')
        require(row.get('passed') is True and row.get('route') == client.ROUTE_B
                and row.get('returned_model') in client.NORTHGATE_RESPONSE_MODEL_IDS
                and type(count) is int and 0 < count <= ceiling
                and isinstance(request, str) and len(request) == 64
                and all(c in '0123456789abcdef' for c in request)
                and type(row.get('tokens')) is int and row['tokens'] > 0,
                'S1 probe receipts require accepted responses, positive usage and pinned requests')
        counts.append(count)
    longest = max(counts)
    require(probe.get('longest') == longest
            and probe.get('ledger_bound') == p.ledger_bound(p.CHAINS['D'], z.BENCH, branch='N', longest=longest)
            and probe.get('tokens') == sum(row['tokens'] for row in rows),
            'S1 longest and ledger bound must derive from its measured receipt completion counts')
    return probe


def check_solver_bounds(chain, stages, *, configuration=CONFIGURATION):
    """Cross-receipt binding, not merely an internally consistent later bound."""
    if p.is_v220(configuration):
        from . import v220_smoke
        return v220_smoke.check_solver_bounds(chain, stages)
    probe = stages['S1']['result'].get('solver_probe')
    if chain == 'D':
        checked_s1_probe(probe)
    if p.is_implant_v5(configuration):
        check_implant_probe(chain, probe)
        require(probe['first_call']['identity']['run'] == stages['S1']['manifest_sha256']
                and stages['S1']['result'].get('solver_confirmation') == probe['first_call'][p.RECORD_HASH],
                'The implant probe first response belongs to its smoke manifest')
        require(all(stages[name]['result'].get('solver_probe') == probe
                    for name in ('S1', 'S2', 'SE6')),
                'S1, S2 and SE6 must pass on the same solver probe')
    expected = solver_bounds(chain, probe, **_options(configuration))
    require(stages['S1']['result'].get('solver_bounds') == expected, 'S1 solver bounds match its probe')
    for stage in stages_of(configuration)[2:]:
        require(stages[stage]['result'].get('solver_bounds') == expected,
                stage + ' solver_bounds must equal S1 probe bounds')
    return expected


def _path(root, chain, stage):
    return safe_path(root) / chain / 'v214-smoke' / (stage + '.json')


def checked_stage(path, *, run=None, chain=None, stage=None, configuration=CONFIGURATION):
    row = p.verified(read_json(path), 'v214-smoke-stage')
    require(row.get('configuration') == configuration and row.get('schedule_sha256') == digest(schedule(configuration))
            and (run is None or row.get('manifest_sha256') == run)
            and (chain is None or row.get('chain') == chain) and (stage is None or row.get('stage') == stage),
            'A main-v5 stage binds its manifest, chain, schedule and stage')
    return row


def checked_readiness(value, *, chain, source_sha256, s0_sha256, configuration=CONFIGURATION):
    """Validate every embedded receipt, including a resealed bound mismatch."""
    from . import v214_stages
    found = p.verified(value, 'v214-smoke-result')
    require(found.get('configuration') == configuration and found.get('chain') == chain
            and found['evidence'] == 'smoke' and found.get('passed') is True
            and found.get('snapshot_sha256') == source_sha256 and found.get('s0_sha256') == s0_sha256
            and found.get('schedule_sha256') == digest(schedule(configuration)) and found.get('sealed_reads') == 0,
            'Real main-v5 requires measured readiness on the same source, S0 and schedule')
    stages = found.get('stage_records', {})
    require(set(stages) == set(stages_of(configuration)), 'Measured readiness requires every lean smoke stage')
    for name, row in stages.items():
        p.verified(row, 'v214-smoke-stage')
        require(row.get('configuration') == configuration and row.get('chain') == chain
                and row.get('stage') == name and row.get('manifest_sha256') == found.get('manifest_sha256')
                and row.get('schedule_sha256') == digest(schedule(configuration)) and row['evidence'] == 'smoke'
                and row.get('measured') is True and row.get('result', {}).get('passed') is True
                and row.get('snapshot_sha256') == source_sha256 and row.get('s0_sha256') == s0_sha256
                and found.get('stages', {}).get(name) == row[p.RECORD_HASH],
                'Every readiness stage is a passing measured receipt of the same smoke manifest')
    bounds = check_solver_bounds(chain, stages, **_options(configuration))
    projected = v214_stages.projection(stages['S2']['result'], chain,
                                      s3=stages.get('S3', {}).get('result'), bounds=bounds, **_options(configuration))
    require(projected == stages['SE6']['result'], 'SE6 is the recomputed measured full-read projection')
    if p.is_v225(configuration):
        from . import v225_smoke
        v225_smoke.check_measured(stages['S2']['result'])
        v225_smoke.check_structural(stages['SX']['result'])
    elif p.is_v222(configuration):
        from . import v222_smoke
        v222_smoke.check_measured(stages['S2']['result'])
        v222_smoke.check_structural(stages['SX']['result'])
    elif p.is_v221(configuration):
        from . import v221_smoke
        v221_smoke.check_result(stages['SX']['result'])
    return found, projected


def measured_readiness(path, *, chain, source_sha256, s0_sha256, configuration=CONFIGURATION):
    result_path = safe_path(path)
    if result_path.is_dir():
        result_path = result_path / chain / 'v214-smoke' / RESULT
    value = read_json(result_path)
    found, projected = checked_readiness(value, chain=chain, source_sha256=source_sha256, s0_sha256=s0_sha256, **_options(configuration))
    # The persisted stages must equal the summary, so replacing either alone fails.
    for name, row in found['stage_records'].items():
        require(checked_stage(result_path.parent / (name + '.json'), run=found['manifest_sha256'],
                              chain=chain, stage=name, **_options(configuration)) == row, 'Summary and persisted stage receipts differ')
    return found, projected


def make_manifest(out, *, root, s0_file, provenance, roles_repo, route_b_env, sheet_runtime=None,
                  smoke_chain=None, measured_smoke=(), environment_found=None, configuration=CONFIGURATION):
    if p.is_v226(configuration):
        manifest._check_run_root(root, configuration,
                                 'smoke' if smoke_chain else p.REAL_RUN_EVIDENCE[configuration])
        manifest._check_frozen_paths(configuration, out, s0_file, provenance, roles_repo, route_b_env,
                                     sheet_runtime, safe_path(root)/'shared/consent.json', *measured_smoke)
    if p.is_v220(configuration):
        from . import v220_smoke
        return v220_smoke.make_manifest(out, root=root, s0_file=s0_file, provenance=provenance,
            roles_repo=roles_repo, route_b_env=route_b_env, smoke_chain=smoke_chain,
            measured_smoke=measured_smoke, environment_found=environment_found)
    from . import sheet_runtime as launch_sheet, v214_preparation
    checked = p.verified(read_json(s0_file), 'v214-s0')
    require(checked.get('passed') is True and checked.get('configuration') == configuration,
            'A passing main-v5 S0')
    root = safe_path(root)
    require(smoke_chain in (None, 'G', 'D'), 'A smoke names one chain')
    require(smoke_chain is not None or str(root) == p.RUN_ROOTS[configuration], 'The registered real main-v5 root')
    if p.is_v226(configuration) and smoke_chain is None:
        require(checked.get('root') == str(root), 'S0 and real manifest require the same registered root')
    if p.is_v226(configuration):
        practice = checked.get('preparation', {}).get('data', {}).get('v222_practice', {})
        manifest._check_frozen_paths(configuration, checked.get('preparation_file'), checked.get('zebra_pool'),
            checked.get('zebra_split_manifest'), checked.get('snapshot_root'),
            (practice.get('supply_manifest') or {}).get('path'))
    if (p.is_implant_v5(configuration) or p.is_v218(configuration)) and not (root / 'shared/consent.json').exists():
        require(digest(checked['consent']) == checked['consent_sha256'], 'S0 consent bytes are pinned')
        write_json(root / 'shared/consent.json', checked['consent'])
    allowed = evaluation.consent(root / 'shared', configuration)
    require(digest(allowed) == checked['consent_sha256'], 'S0 and manifest bind the same consent')
    imported = v214_preparation.preparation(checked['preparation_file'], zebra_pool=checked['zebra_pool'],
                                            zebra_split_manifest=checked['zebra_split_manifest'], **_options(configuration),
                                            **({'v222_practice_supply': (checked['preparation']['data']['v222_practice'].get('supply_manifest') or {}).get('path'),
                                                'v222_alf_views': checked['preparation']['data']['v222_practice']['alfworld_routing_overlay']}
                                               if p.is_v222(configuration) else {}))
    require(imported == checked['preparation'], 'Preparation and training supplies remain identical to S0')
    proven, source = read_json(provenance), _source(manifest.REPO)
    require(checked['snapshot_sha256'] == source == proven.get('sha256_list_sha256')
            and safe_path(checked['snapshot_root']) == manifest.REPO
            and safe_path(proven['snapshot_root']) == manifest.REPO,
            'S0 and provenance certify the current source snapshot')
    require(checked['smoke_schedule'] == schedule(configuration) and checked['prompt_pins'] == prompt_pins(configuration),
            'The smoke schedule and inherited prompts are unchanged')
    sheet = launch_sheet.for_manifest(sheet_runtime, checked, snapshot_root=manifest.REPO)
    readiness, terms = {}, {}
    if smoke_chain is None:
        require(len(measured_smoke) == 2, 'Real main-v5 requires both measured chain smoke receipts')
        for path in measured_smoke:
            raw = p.verified(read_json(path), 'v214-smoke-result')
            chain = raw.get('chain')
            require(chain in p.CHAINS and chain not in readiness, 'One measured receipt per chain')
            receipt, se6 = measured_readiness(path, chain=chain, source_sha256=source,
                                             s0_sha256=checked[p.RECORD_HASH], **_options(configuration))
            if p.is_v222(configuration):
                from . import v222_smoke
                if p.is_v225(configuration):
                    from . import v225_smoke as v222_smoke
                v222_smoke.check_bound_practice(receipt['stage_records']['S2']['result'], imported['data']['v222_practice'])
            readiness[chain], terms[chain] = receipt, se6['read_terms']
        require(set(readiness) == set(p.CHAINS), 'Both routes have measured smoke')
    for chain in p.CHAINS:
        if chain not in terms:
            anchor = {b: {'card': p.CELL_ANCHORS[b][1 if chain == 'G' else 0], 'procedure_assumed': True}
                      for b in p.active_benches(configuration)}
            terms[chain] = {b: str(v) for b, v in p.read_estimate_terms(anchor, 1, configuration).items()}
            if p.is_v225(configuration):
                from .v225_read import estimate_unit_terms
                terms[chain] = {key: str(value) for key, value in estimate_unit_terms(anchor, 1).items()}
    longest = (readiness['D']['stage_records']['S1']['result']['solver_bounds']['longest']
               if readiness else routes.S1B_CEILING)
    blocks = {'G': manifest.solver_block('G', env_path=roles_repo, configuration=configuration),
              'D': manifest.solver_block('D', env_path=route_b_env, branch='N', longest=longest,
                                         configuration=configuration)}
    data = {**imported['data'], 'exclusion': v211_smoke._bind_exclusion(root, imported),
        'launch_sheet_runtime': sheet, 'inherited_sheet_runtime': launch_sheet.inherited(imported),
        'v214_s0': checked, 'v214_preparation': imported['registration'],
        's0_sha256': checked[p.RECORD_HASH], 'snapshot_sha256': source,
        'allocations': imported['allocations'], 'protected_ids': imported['protected_ids'],
        'confirm': imported['confirm'], 'v211_prompt_pins': checked['v211_prompt_pins'],
        'freshness_amendment': deepcopy(v211_smoke.AMENDMENT), 'smoke_schedule': schedule(configuration),
        'launchable_chains': [smoke_chain] if smoke_chain else ['G', 'D'], 'v214_readiness': readiness,
        'test_read_terms': terms,
        'test_read_estimate': {c: math.ceil(sum(Fraction(v) for v in row.values())) for c, row in terms.items()}}
    cards = imported['cards']
    if p.is_v222(configuration):
        from . import v222_cards
        cards = {bench: v222_cards.format_text(bench) for bench in p.active_benches(configuration)}
        data['v222_fallbacks'] = ({} if p.is_v225(configuration) else
            {chain: receipt['stage_records']['S2']['result']['decomposition']['fallbacks']
             for chain, receipt in readiness.items()})
    return manifest.make(out, evidence='smoke' if smoke_chain else p.REAL_RUN_EVIDENCE[configuration],
        measured=checked['measured'], limits={k: sandbox.Limits(**v) for k, v in checked['limits'].items()},
        environment_found=environment_found, configuration=configuration, root=str(root), data=data,
        cards=cards, contracts=imported['contracts'], fixtures=imported['fixtures'],
        runtime={**imported['runtime'], 'spreadsheetbench': sheet['runtime']},
        sheet_qualification=sheet['qualification'], provenance=proven,
        clients={'solver': blocks, 'roles': manifest.role_settings(configuration), 'routes': {'D': {'B':
            routes.pin('D', 'B', env_path=route_b_env, solver_block=blocks['D'], configuration=configuration)}}})


def check_manifest(value):
    if p.is_v220(value['configuration']):
        from . import v220_smoke
        return v220_smoke.check_manifest(value)
    from . import engineer_v211, sheet_runtime, zebralogic as z
    configuration = value['configuration']
    data = value['data']
    sheet_runtime.verify_manifest(value, snapshot_root=manifest.REPO)
    s0 = p.verified(data.get('v214_s0'), 'v214-s0')
    require(s0.get('passed') is True and s0.get('configuration') == configuration
            and s0.get('sealed_reads') == 0 and s0.get('pytest', {}).get('passed') is True
            and s0[p.RECORD_HASH] == data.get('s0_sha256') and s0.get('snapshot_sha256') == data.get('snapshot_sha256')
            and s0.get('smoke_schedule') == data.get('smoke_schedule') == schedule(configuration)
            and s0.get('prompt_pins') == value['prompt_sha'] == prompt_pins(configuration)
            and data.get('v211_prompt_pins') == engineer_v211.pins(), 'A complete source-bound main-v5 S0')
    imported = s0['preparation']
    if p.is_v225(configuration):
        from . import v225_smoke
        require(s0.get('v225') == v225_smoke.pins(value['runtime'],
            **({'configuration': configuration} if p.is_v226(configuration) else {})), 'main-v9 S0 pins recompute exactly')
    require(value['importable_versions'] == [*p.IMPORTABLE, p.TEXTS_IMPORT, z.CARD_VERSION]
            and value['contracts'][z.BENCH] == imported['contracts'][z.BENCH]
            and value['runtime'][z.BENCH] == imported['runtime'][z.BENCH],
            'Mixed import versions and Zebra contract/runtime are pinned')
    require(data.get('allocations') == imported['allocations']
            and set(data['allocations']) == {'searchqa', 'officeqa', 'spreadsheetbench'}
            and data.get('protected_ids') == imported['protected_ids']
            and data.get('confirm') == imported['confirm']
            and data.get('pools') == imported['data']['pools']
            and data.get('zebra_pc') == z.identity()
            and data.get('freshness_amendment') == v211_smoke.AMENDMENT,
            'Mixed training allocations and Zebra source identities remain sealed')
    if p.is_v222(configuration):
        require(data.get('v222_practice') == imported['data']['v222_practice']
                and data.get('v222_practice_supply') == s0.get('v222_practice_supply')
                == imported['data']['v222_practice_supply'] == data['v222_practice']['v222_practice_supply']
                and data.get('v222_fallbacks') == ({} if p.is_v225(configuration) else
                    {chain: receipt['stage_records']['S2']['result']['decomposition']['fallbacks']
                    for chain, receipt in data.get('v214_readiness', {}).items()}),
                'main-v8 practice and fallback P0 are bound to S0 and measured readiness')
    require(value['sizes']['v214'] == manifest._plain(_identity(configuration)), 'The mixed maximum schedule is pinned')
    require(data.get('launchable_chains') in (['G'], ['D'], ['G', 'D']), 'One smoke chain or both real chains')
    if value['evidence'] == p.REAL_RUN_EVIDENCE[configuration]:
        require(set(data.get('v214_readiness', {})) == set(p.CHAINS), 'Both chain smoke receipts are required')
        for chain, receipt in data['v214_readiness'].items():
            _, se6 = checked_readiness(receipt, chain=chain, source_sha256=data['snapshot_sha256'],
                                       s0_sha256=data['s0_sha256'], **_options(configuration))
            if p.is_v222(configuration):
                from . import v222_smoke
                if p.is_v225(configuration):
                    from . import v225_smoke as v222_smoke
                v222_smoke.check_bound_practice(receipt['stage_records']['S2']['result'], data['v222_practice'])
            require(data['test_read_terms'][chain] == se6['read_terms']
                    and data['test_read_estimate'][chain] == se6['read_estimate'], 'Measured full-read estimate is pinned')
            bounds = receipt['stage_records']['S1']['result']['solver_bounds']
            block = value['clients']['solver'][chain]
            require(block['branch'] == bounds['branch'] and block['longest'] == bounds['longest']
                    and block['B'] == bounds['ledger_bound'], 'The real manifest solver bounds equal S1')
    return value


def structural_smoke(manifest_path, *, out, configuration=CONFIGURATION):
    if p.is_v226(configuration):
        manifest._check_frozen_paths(configuration, manifest_path, out)
    from . import v214_stages
    value = manifest.load(manifest_path, verify=False)
    require(value['configuration'] == configuration, 'The main-v5 manifest')
    manifest.verify_code(value)
    if p.is_v220(configuration):
        from . import v220_import
        demo = v220_import.structural_smoke(safe_path(out).parent / 'v220-structural-demo',
                                           value['data'][v220_import.PIN_KEY])
    elif p.is_implant_v5(configuration):
        from . import v217_implant
        demo = v217_implant.structural_smoke(safe_path(out).parent / (configuration + '-structural-stage-demo'),
            **({'configuration': configuration} if p.is_v219(configuration) else {}))
    else:
        demo = v214_stages.sx(safe_path(out).parent / 'v214-structural-stage-demo', **_options(configuration))
    result = p.record('v214-structural-smoke', 'engineering_fixture', {
        'configuration': configuration, 'manifest': value[p.RECORD_HASH], 'passed': demo['passed'],
        'model_calls': 0, 'sealed_reads': 0, 'measured_readiness': False, 'stage_demo': demo,
        'schedule_sha256': digest(schedule(configuration))})
    write_json(out, result)
    return result


def run_stage(manifest_path, chain, stage, *, _setting=None, configuration=CONFIGURATION):
    if p.is_v226(configuration):
        manifest._check_frozen_paths(configuration, manifest_path)
    from . import v214_stages
    require(chain in p.CHAINS and stage in stages_of(configuration), 'A registered main-v5 smoke chain and stage')
    m = manifest.load(manifest_path, verify=_setting is None)
    require(m['configuration'] == configuration and m['evidence'] == 'smoke'
            and chain in m['data']['launchable_chains'], 'An isolated main-v5 smoke manifest')
    setting = manifest.setting_of(m, chain, path=manifest_path) if _setting is None else _setting
    require(_setting is None or setting.evidence == 'engineering_fixture', 'Injected settings are fixtures only')
    setting.budget.declare({**budgets.chain_caps(chain, configuration), **budgets.first_call_caps(chain)})
    path = _path(setting.root, chain, stage)
    with exclusive(path.parent / '.stage-lock'):
        if path.exists():
            return checked_stage(path, run=m[p.RECORD_HASH], chain=chain, stage=stage, **_options(configuration))
        previous = {name: checked_stage(_path(setting.root, chain, name), run=m[p.RECORD_HASH],
                                        chain=chain, stage=name, **_options(configuration)) for name in stages_of(configuration)[:stages_of(configuration).index(stage)]}
        require(all(row['result']['passed'] is True for row in previous.values()), 'Earlier smoke stages must pass')
        bounds = None
        if stages_of(configuration).index(stage) > 1:
            bounds = solver_bounds(chain, previous['S1']['result'].get('solver_probe'), **_options(configuration))
            setting = replace(setting, branch=bounds['branch'], longest=bounds['longest'])
            if p.is_implant_v5(configuration) or p.is_v220(configuration):
                setting = replace(setting, extra={**setting.extra,
                    'solver_probe': previous['S1']['result']['solver_probe']})
        if stage == 'S0':
            result = {'passed': m['data']['v214_s0']['passed'], 'model_calls': 0, 'sealed_reads': 0}
        elif stage == 'S1':
            result = v214_stages.s1(setting, chain)
        elif stage == 'S2':
            result = v214_stages.s2(setting, chain)
        elif stage == 'S3':
            result = v214_stages.s3(setting, chain)
        elif stage == 'SE6':
            result = v214_stages.projection(previous['S2']['result'], chain,
                                             s3=previous.get('S3', {}).get('result'), bounds=bounds, **_options(configuration))
        else:
            result = v214_stages.sx(path.parent / 'stage-demo', **_options(configuration))
        if bounds is not None:
            result['solver_bounds'] = bounds
            if p.is_implant_v5(configuration) or p.is_v220(configuration):
                result['solver_probe'] = previous['S1']['result']['solver_probe']
        row = p.record('v214-smoke-stage', setting.evidence, {'configuration': configuration,
            'chain': chain, 'stage': stage, 'manifest_sha256': m[p.RECORD_HASH],
            'snapshot_sha256': m['data']['snapshot_sha256'], 's0_sha256': m['data']['s0_sha256'],
            'schedule_sha256': digest(schedule(configuration)), 'measured': setting.evidence == 'smoke', 'result': result})
        write_json(path, row)
        return row


def summarize(manifest_path, chain, *, configuration=CONFIGURATION):
    if p.is_v226(configuration):
        manifest._check_frozen_paths(configuration, manifest_path)
    m = manifest.load(manifest_path)
    require(m['configuration'] == configuration and m['evidence'] == 'smoke', 'A main-v5 smoke manifest')
    stages = {name: checked_stage(_path(m['root'], chain, name), run=m[p.RECORD_HASH], chain=chain, stage=name, **_options(configuration))
              for name in stages_of(configuration)}
    value = p.record('v214-smoke-result', 'smoke', {'configuration': configuration, 'chain': chain,
        'manifest_sha256': m[p.RECORD_HASH], 'snapshot_sha256': m['data']['snapshot_sha256'],
        's0_sha256': m['data']['s0_sha256'], 'schedule_sha256': digest(schedule(configuration)),
        'stages': {name: row[p.RECORD_HASH] for name, row in stages.items()}, 'stage_records': stages,
        'passed': True, 'sealed_reads': 0, 'benchmark_effect_evidence': False})
    checked_readiness(value, chain=chain, source_sha256=m['data']['snapshot_sha256'], s0_sha256=m['data']['s0_sha256'], **_options(configuration))
    target = _path(m['root'], chain, 'SX').parent / RESULT
    if target.exists():
        require(read_json(target) == value, 'Measured readiness is immutable')
    else:
        write_json(target, value)
    return value


def selftest(out, *, preparation_file, zebra_pool=None, zebra_split_manifest=None, configuration=CONFIGURATION,
             v222_practice_supply=None):
    """Future operator path: sandbox measurements use active practice inputs only."""
    if p.is_v226(configuration):
        manifest._check_run_root(out, configuration, 'smoke')
        manifest._check_frozen_paths(configuration, preparation_file, zebra_pool, zebra_split_manifest,
                                     v222_practice_supply)
    if p.is_v220(configuration):
        from . import v220_smoke
        return v220_smoke.selftest(out, preparation_file=preparation_file)
    from . import s0, smoke, v214_preparation
    out = safe_path(out)
    require(not (out / smoke.SELFTEST).exists(), 'A selftest is written once')
    imported = v214_preparation.preparation(preparation_file, zebra_pool=zebra_pool,
                                            zebra_split_manifest=zebra_split_manifest, **_options(configuration),
                                            **({'v222_practice_supply': v222_practice_supply} if p.is_v222(configuration) else {}))
    item_files, workbooks = [], []
    for bench in p.active_benches(configuration):
        items = manifest._items(imported['data']['pools'][bench], bench)
        target = out / 'training-views' / (bench + '.json')
        if target.exists():
            require(read_json(target) == items, 'Selftest practice inputs remain unchanged')
        else:
            write_json(target, items)
        item_files.append(target)
        if bench == 'spreadsheetbench':
            workbooks.extend(safe_path(path) for item in items for path in item['public'].get('input_files', []))
    require(workbooks, 'Native measurements need a practice workbook')
    largest = max(workbooks, key=lambda path: path.stat().st_size)
    worker = smoke.sandbox_selftest(out / 'worker-selftest', item_files=item_files, configuration=configuration)
    measured = {key: worker['measured'][key] for key in ('vsz_kib', 'rss_kib', 'view_bytes_p99')}
    zebra_worker = None
    if p.is_v222(configuration):
        from . import v218_lock
        require(worker.get('worker_sha256') == sandbox.worker_sha256(configuration=p.MAIN_V8),
                'The new instruction worker is measured before main-v8')
        with v218_lock.preparation(out, 'native-peak'):
            measured['native_peak_rss_kib'] = s0.native_peak(largest, sandbox.Docker())
    elif p.is_v218(configuration):
        from . import v218_lock
        zebra_worker = smoke.sandbox_selftest(out / 'zebra-worker-selftest', item_files=item_files,
                                              configuration=p.ZEBRA_PC_V15)
        require(zebra_worker['passed'] is True, 'The main-v6 Zebra diagnostics worker selftest must pass')
        measured = {key: max(value, zebra_worker['measured'][key]) for key, value in measured.items()}
        with v218_lock.preparation(out, 'native-peak'):
            measured['native_peak_rss_kib'] = s0.native_peak(largest, sandbox.Docker())
    elif p.is_v219(configuration):
        from . import v218_lock
        with v218_lock.preparation(out, 'native-peak'):
            measured['native_peak_rss_kib'] = s0.native_peak(largest, sandbox.Docker())
    else:
        measured['native_peak_rss_kib'] = s0.native_peak(largest, sandbox.Docker())
    require(type(measured['native_peak_rss_kib']) is int and measured['native_peak_rss_kib'] > 0,
            'Positive measured native RSS')
    value = p.record('sandbox-selftest', worker['evidence'], {
        **{key: row for key, row in worker.items() if key not in ('version', 'evidence', p.RECORD_HASH, 'measured')},
        'measured': measured, 'measurement_sources': {
            'worker': worker[p.RECORD_HASH], 'practice_workbook_sha256': hashlib.sha256(largest.read_bytes()).hexdigest(),
            **({'zebra_worker': zebra_worker[p.RECORD_HASH], 'zebra_worker_configuration': p.ZEBRA_PC_V15}
               if zebra_worker is not None else {})}})
    write_json(out / smoke.SELFTEST, value)
    return value

