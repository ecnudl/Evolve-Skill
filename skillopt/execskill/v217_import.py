"""The fixed main-v5 G/r2 strict solver: post-hoc import, never learned adoption."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

from skillopt.continual_eval.core import read_json, require, safe_path, write_json

from . import policy, profiles as p
from .package import Package, Procedure, empty, load, save, validate, with_

FIXTURE = Path(__file__).resolve().parents[2] / 'tests/fixtures/execskill/v217_zebra_hp_g3r2_package'
PIN_KEY = 'zebra_hp_g3r2_import'
ORIGIN = 'main-v5/G/s3-zebralogic/engineer-r2'
EVIDENCE_KIND = 'post_hoc_selected_upper_bound'
SOURCE_BYTES = 6_872
SOURCE_SHA256 = 'f50b4548bc5520e64d68eefa503ab228d81eafe2f0c0ef78973fe8f62149cfe7'
SOURCE_PROCEDURE_SHA256 = '54f577f83a44251e64c895f5867068d2e489cfcf9ae6980db625e68729a92352'
SOURCE_PROCEDURE_FILE_SHA256 = '4fec5a6ac8b7129015195e9fd37d943c1d5dcb4d71db908442508e31e5ac7c49'
SOURCE_CANDIDATE_SHA256 = '4223c1c09e5813b835e92c02b3aebcc940df58d369a91faf6e7725c9cc097673'
SOURCE_CANDIDATE_FILE_SHA256 = 'd026abea2b64dc638f9c1180a1953ec03ec66e22c0befedc3ee053debb349ff7'
SOURCE_PARENT_SHA256 = 'db55b5a2baa7e542d25b3ea2e8ddbceebb1ca4812029ecb93691df42f21c174f'
PACKAGE_SHA256 = '3a624e69b8d371eec2ac427ca439e03baedb9028a99b95f0a972fe734e796eb2'
PACKAGE_FILE_SHA256 = 'f793079fbe85e65856d28b3a740a1afd223d51cf8bfb659322b34bb1157a561d'
PROCEDURE_SHA256 = 'dff6e5fa52bc0c6fcd3822ea33cad15c9baf7b0fb3e5b6a43ca983cd78c6191f'
PROCEDURE_FILE_SHA256 = '4b0ea472b00de3da2239d1afe465fa934b94d1486bbccb8bfbb7c09a399fbe48'
PARENT_SHA256 = 'dfa658e134f346f305b82513fe79c2643630002dc9c0767a5f57dfcfe14cab67'
PARENT_FILE_SHA256 = '8061069829b46be90e230d9cd4ffea86c2e22ec7a64166d15a5fb9951d53e4e3'
PROVENANCE_SHA256 = '393ea844024c7ce2cea03ebbb8b038072815cd14d22d0cead69533e347de0d90'


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build(source, stored_record):
    """Rebuild exactly one NEW procedure on empty, retaining its stored metadata.

    The fixture changes only procedure evidence. It retains the original id and
    engineer-call lineage; the new package has its own step, evidence and parent.
    No program execution, repair or new audit is performed.
    """
    require(type(source) is bytes and len(source) == SOURCE_BYTES and _sha(source) == SOURCE_SHA256,
            'The fixed G/r2 source bytes differ from their input pin')
    require(type(stored_record) is bytes and _sha(stored_record) == SOURCE_PROCEDURE_FILE_SHA256,
            'The fixed G/r2 procedure record differs from its input pin')
    original = Procedure.from_json(json.loads(stored_record.decode('utf-8')))
    require(original.sha256 == SOURCE_PROCEDURE_SHA256 and original.source.encode('utf-8') == source,
            'The stored G/r2 procedure and source pins differ')
    procedure = replace(original, evidence='engineering_fixture')
    parent = empty(step='zebra-hp-g3r2/s0', evidence='engineering_fixture')
    candidate = with_(parent, step='zebra-hp-g3r2/import', add=[procedure])
    validate(candidate, parent)
    main_policy = p.POLICY_VERSIONS[p.machinery_configuration(p.MAIN_V5, p.ZEBRA)]
    require(procedure.policy_version == main_policy == policy.POLICY_VERSION_V29
            and not policy.check(procedure.source, version=main_policy),
            'The fixed program must pass main-v5 Zebra package policy without editing')
    require(candidate.sha256 == PACKAGE_SHA256 and parent.sha256 == PARENT_SHA256,
            'The fixed G/r2 reconstruction differs from its package pin')
    return parent, candidate


def pins(*, fixture=None):
    """Load detached package/provenance pins, rejecting even resealed changes."""
    root = safe_path(fixture or FIXTURE)
    files = {
        'inputs/g3r2-p-zebralogic-3-3.py': SOURCE_SHA256,
        'inputs/g3r2-p-zebralogic-3-3.procedure.json': SOURCE_PROCEDURE_FILE_SHA256,
        'inputs/g3r2-candidate-4223c1c0.package.json': SOURCE_CANDIDATE_FILE_SHA256,
        'packages/' + PACKAGE_SHA256 + '.json': PACKAGE_FILE_SHA256,
        'packages/' + PARENT_SHA256 + '.json': PARENT_FILE_SHA256,
        'procedures/' + PROCEDURE_SHA256 + '.json': PROCEDURE_FILE_SHA256,
        'provenance.json': PROVENANCE_SHA256,
    }
    for name, expected in files.items():
        require(_sha((root / name).read_bytes()) == expected,
                'The fixed G/r2 fixture file hash differs: ' + name)
    parent, rebuilt = build((root / 'inputs/g3r2-p-zebralogic-3-3.py').read_bytes(),
                            (root / 'inputs/g3r2-p-zebralogic-3-3.procedure.json').read_bytes())
    historical = p.verified(read_json(root / 'inputs/g3r2-candidate-4223c1c0.package.json'), 'package')
    require(historical[p.RECORD_HASH] == SOURCE_CANDIDATE_SHA256
            and historical['parent_sha256'] == SOURCE_PARENT_SHA256
            and historical['order'] == ['p-zebralogic-3-3', 'p-zebralogic-3-4']
            and historical['procedures'][0] == SOURCE_PROCEDURE_SHA256
            and empty(step='G/s0', evidence='main_v5_real_run').sha256 == SOURCE_PARENT_SHA256,
            'The G/r2 candidate provenance does not name the pinned NEW-on-empty source')
    candidate = load(root / 'packages' / (PACKAGE_SHA256 + '.json'))
    require(load(root / 'packages' / (PARENT_SHA256 + '.json')) == parent and candidate == rebuilt,
            'The fixed G/r2 package differs from the exact input reconstruction')
    require(len(candidate.procedures) == len(candidate.for_bench(p.ZEBRA)) == 1,
            'The fixed import is one nonempty Zebra procedure')
    procedure = candidate.procedures[0]
    return {'origin': ORIGIN, 'evidence_kind': EVIDENCE_KIND, 'package_record_sha256': PACKAGE_SHA256,
        'package_file_sha256': PACKAGE_FILE_SHA256, 'package': candidate.to_json(),
        'procedures': [{'id': procedure.id, 'record_sha256': procedure.sha256,
            'file_sha256': PROCEDURE_FILE_SHA256, 'source_sha256': SOURCE_SHA256, 'record': procedure.to_json()}],
        'provenance_sha256': PROVENANCE_SHA256, 'provenance': read_json(root / 'provenance.json')}


def import_step(setting, chain_root, chain, k, bench, parent):
    """Import the single solver without calling any learning service."""
    require(p.is_v217(p.configuration_of(setting)) and chain == 'G' and k == 1 and bench == p.ZEBRA,
            'The fixed G/r2 Zebra import is chain G step 1')
    source = pins()
    require(setting.extra.get(PIN_KEY) == source, 'The G/r2 import pins differ from the immutable fixture')
    require(isinstance(parent, Package) and not parent.procedures,
            'The fixed Zebra import starts from the empty parent')
    root, name = safe_path(chain_root), 'G/s1-zebralogic'
    procedures = tuple(replace(Procedure.from_json(row['record']), evidence=setting.evidence)
                       for row in source['procedures'])
    require(len(procedures) == 1, 'An empty import cannot trigger an F/C read')
    imported = Package(procedures, name + '/import', setting.evidence, parent_sha256=PACKAGE_SHA256)
    final = Package(procedures, name, setting.evidence, parent_sha256=parent.sha256)
    validate(final, parent)
    provenance = p.record('import-v2-17', setting.evidence, {
        'origin': ORIGIN, 'evidence_kind': EVIDENCE_KIND, 'source': source,
        'imported_package_sha256': imported.sha256, 'program_bytes_changed': False,
        'procedures': [{'id': original['id'], 'source_record_sha256': original['record_sha256'],
            'source_sha256': original['source_sha256'], 'imported_record_sha256': copied.sha256}
            for original, copied in zip(source['procedures'], procedures)]})
    value = p.record('step-v2-3', setting.evidence, {
        'chain': chain, 'k': k, 'bench': bench, 'step': name, 'learning': 'import', 'origin': ORIGIN,
        'parent_sha256': imported.sha256, 'chain_parent_sha256': parent.sha256,
        'source_package_sha256': PACKAGE_SHA256, 'candidate_sha256': None, 'package_sha256': final.sha256,
        'decision': 'import', 'reason': 'preregistered_post_hoc_g3r2_import', 'decision_sha256': None,
        'fault_items': [], 'violating_items': [], 'units': {}, 'evidence_kind': EVIDENCE_KIND,
        'import_sha256': provenance[p.RECORD_HASH]})
    record_path = root / 's1-zebralogic/step.json'
    if record_path.exists():
        require(p.verified(read_json(record_path), 'step') == value,
                'A finished import step has different pins or parents')
        require(p.verified(read_json(record_path.with_name('import.json')), 'import-v2-17') == provenance,
                'A finished import has different provenance')
        return load(root / 'packages' / (final.sha256 + '.json')), value
    save(root, imported)
    save(root, final)
    write_json(record_path.with_name('import.json'), provenance)
    write_json(record_path, value)
    return final, value
