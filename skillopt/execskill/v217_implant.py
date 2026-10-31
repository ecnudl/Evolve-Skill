"""Fixed Zebra implants in main-v5's five-step chain; no learning work."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from skillopt.continual_eval.core import read_json, require, safe_path, write_json

from . import policy, profiles as p, v210_import, v213_import, v217_import
from .package import Package, Procedure, empty, load, save, validate, with_

PIN_KEY = 'implant_v5_import'
EVIDENCE_KIND = 'post_hoc_selected_upper_bound'
ROWS = ['C', 'C', 'C', 'S3', 'S3', 'F']
SKIPS = {1: 'searchqa', 2: 'officeqa', 4: 'spreadsheetbench'}
SKIP_REASON = 'preregistered_implant_chain_no_learning'


def pins():
    """The two immutable source fixtures, without opening benchmark data."""
    return {'G': v217_import.pins(), 'D': v213_import.pins(),
            'stage_rows': list(ROWS), 'evidence_kind': EVIDENCE_KIND}


def zebra_package(chain, parent, *, source=None):
    """Append one NEW fixed procedure, changing only its evidence stamp."""
    require(chain in p.CHAINS and isinstance(parent, Package) and not parent.procedures,
            'The implanted Zebra procedure is NEW on the empty s2 package')
    source = (pins()[chain] if source is None else source)
    require(len(source['procedures']) == 1, 'Exactly one fixed Zebra procedure is implanted')
    procedure = replace(Procedure.from_json(source['procedures'][0]['record']), evidence=parent.evidence)
    main_policy = p.POLICY_VERSIONS[p.machinery_configuration(p.MAIN_V5, p.ZEBRA)]
    require(procedure.origin == p.ZEBRA and procedure.policy_version == main_policy
            and main_policy == policy.POLICY_VERSION_V29
            and not policy.check(procedure.source, version=main_policy),
            'The fixed implant must pass main-v5 Zebra policy without editing')
    candidate = with_(parent, step=chain + '/s3-zebralogic', add=[procedure])
    validate(candidate, parent)
    v210_import.check_learning_capacity(candidate)
    return candidate


def _record(chain, k, bench, parent, package, *, source=None, provenance=None):
    name = '%s/s%d-%s' % (chain, k, bench)
    fields = {'chain': chain, 'k': k, 'bench': bench, 'step': name,
        'learning': 'none' if source is None else 'import',
        'parent_sha256': parent.sha256, 'chain_parent_sha256': parent.sha256,
        'candidate_sha256': None, 'package_sha256': package.sha256,
        'decision': 'skip' if source is None else 'import',
        'reason': SKIP_REASON if source is None else 'preregistered_implant_zebra_import',
        'decision_sha256': None, 'fault_items': [], 'violating_items': [], 'units': {},
        'evidence_kind': EVIDENCE_KIND}
    if source is not None:
        fields.update(origin=source['origin'], source_package_sha256=source['package_record_sha256'],
                      import_sha256=provenance[p.RECORD_HASH])
    return p.record('step-v2-3', parent.evidence, fields)


def run_step(setting, chain_root, chain, k, bench, parent):
    """Skip s1/s2/s4, implant at s3, and use the unchanged v11 composer at s5."""
    require(p.is_implant_v5(p.configuration_of(setting)) and chain in p.CHAINS
            and type(k) is int and 1 <= k <= 5 and p.MAIN_V5_ORDER[k - 1] == bench,
            'An implant-v5 step follows the registered five-bench order')
    require(isinstance(parent, Package) and parent.evidence == setting.evidence,
            'The implant chain retains its evidenced parent package')
    source = pins()
    require(setting.extra.get(PIN_KEY) == source, 'The implant source pins differ from the fixed fixtures')
    if k == 5:
        # The same module, source pins, procedure ordering and capacity check as main-v5.
        return v210_import.import_step(setting, chain_root, chain, k, bench, parent)
    if k in SKIPS:
        require(not parent.procedures if k < 3 else parent == zebra_package(
            chain, empty(step=chain + '/s0', evidence=setting.evidence), source=source[chain]),
            'A skipped implant step retains its prescribed parent package')
        package, provenance = parent, None
        value = _record(chain, k, bench, parent, package)
    else:
        package = zebra_package(chain, parent, source=source[chain])
        original, copied = source[chain]['procedures'][0], package.procedures[0]
        provenance = p.record('implant-v2-17', setting.evidence, {
            'chain': chain, 'origin': source[chain]['origin'], 'source': source[chain],
            'evidence_kind': EVIDENCE_KIND, 'program_bytes_changed': False,
            'source_package_sha256': source[chain]['package_record_sha256'],
            'chain_parent_sha256': parent.sha256, 'package_sha256': package.sha256,
            'procedure': {'id': copied.id, 'source_record_sha256': original['record_sha256'],
                          'source_sha256': original['source_sha256'], 'imported_record_sha256': copied.sha256},
            'changed_procedure_fields': ['evidence', p.RECORD_HASH]})
        value = _record(chain, k, bench, parent, package, source=source[chain], provenance=provenance)
    root = safe_path(chain_root)
    path = root / ('s%d-%s' % (k, bench)) / 'step.json'
    if path.exists():
        require(p.verified(read_json(path), 'step') == value, 'A finished implant step has different pins or parents')
        if provenance is not None:
            require(p.verified(read_json(path.with_name('import.json')), 'implant-v2-17') == provenance,
                    'A finished Zebra implant has different provenance')
            require(load(root / 'packages' / (package.sha256 + '.json')) == package,
                    'A finished Zebra implant package differs')
        return package, value
    if provenance is not None:
        save(root, package)
        write_json(path.with_name('import.json'), provenance)
    write_json(path, value)
    return package, value


def check_read_packages(chain, final, stages):
    """Assert the fixed row sequence and exact treatment composition before cells."""
    require(chain in p.CHAINS and isinstance(final, Package) and isinstance(stages, dict)
            and stages.get('rows') == ROWS and set(stages.get('packages', {})) == {'S3'},
            'The implant read rows must be [C, C, C, S3, S3, F]')
    start = empty(step=chain + '/s0', evidence=final.evidence)
    zebra = zebra_package(chain, start)
    require(stages['packages']['S3'] == zebra, 'S3 is exactly the fixed Zebra implant')
    source = v210_import.pins()
    alf = tuple(replace(Procedure.from_json(row['record']), evidence=final.evidence)
                for row in source['procedures'])
    expected = Package(zebra.procedures + alf, chain + '/s5-alfworld', final.evidence,
                       zebra.sha256, zebra.retired,
                       {**zebra.narrowed, **source['package']['narrowed']},
                       {**zebra.describer, **source['package']['describer']})
    require(final == expected, 'F is the fixed Zebra implant plus the three alfworld-v11 procedures in order')
    validate(final, zebra)
    return stages


def check_stage_rows(chain_root, chain, order, final, start, stages):
    """Bind the expected six rows to every immutable skip/import step record."""
    require(tuple(order) == p.MAIN_V5_ORDER and start == empty(step=chain + '/s0', evidence=final.evidence),
            'The implant read retains main-v5 order and the empty chain start')
    check_read_packages(chain, final, stages)
    zebra = stages['packages']['S3']
    expected = [start, start, zebra, zebra, final]
    parents = [start, start, start, zebra, zebra]
    root = safe_path(chain_root)
    for k, (bench, package, parent) in enumerate(zip(order, expected, parents), 1):
        value = p.verified(read_json(root / ('s%d-%s' % (k, bench)) / 'step.json'), 'step')
        require(value.get('chain') == chain and value.get('k') == k and value.get('bench') == bench
                and value.get('package_sha256') == package.sha256
                and value.get('chain_parent_sha256') == parent.sha256
                and value.get('units') == {} and value.get('candidate_sha256') is None
                and value.get('decision_sha256') is None,
                'Every implant row must match its no-learning step record')
        if k in SKIPS:
            require(value.get('learning') == 'none' and value.get('decision') == 'skip'
                    and value.get('reason') == SKIP_REASON and value.get('parent_sha256') == parent.sha256,
                    'An implant skip retains its parent without learning')
        else:
            require(value.get('learning') == value.get('decision') == 'import'
                    and value.get('source_package_sha256') == (
                        pins()[chain]['package_record_sha256'] if k == 3 else v210_import.PACKAGE_SHA256),
                    'An implant row names its fixed source import')
    return stages


def structural_smoke(root):
    """Persist and check both fixed chains with no clients, workers or task data."""
    from . import evaluation, step

    root = safe_path(root)
    setting = SimpleNamespace(root=root, evidence='engineering_fixture', extra={
        'configuration': p.IMPLANT_V5, PIN_KEY: pins(), 'alfworld_v11_import': v210_import.pins()})
    rows, packages = {}, {}
    for chain in p.CHAINS:
        start = parent = empty(step=chain + '/s0', evidence=setting.evidence)
        for k, bench in enumerate(p.MAIN_V5_ORDER, 1):
            parent = step.run_step(setting, chain, bench, k, parent, services=None).package
        stages = evaluation.stage_rows(root / chain, chain, p.MAIN_V5_ORDER, parent, start)
        check_stage_rows(root / chain, chain, p.MAIN_V5_ORDER, parent, start, stages)
        rows[chain] = stages['rows']
        packages[chain] = {'S3': stages['packages']['S3'].sha256, 'F': parent.sha256}
    return {'passed': True, 'configuration': p.IMPLANT_V5, 'rows': rows, 'packages': packages,
            'model_calls': 0, 'sealed_reads': 0, 'learning_units': 0}
