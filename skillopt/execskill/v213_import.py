"""Fixed, post-hoc-selected v3r4 import; static validation only, no learned adoption."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re

from skillopt.continual_eval.core import read_json, require, safe_path, write_json

from . import policy, profiles as p
from .package import Package, Procedure, empty, load, save, validate, with_

FIXTURE = Path(__file__).resolve().parents[2] / 'tests/fixtures/execskill/v213_zebra_hp_v3r4_package'
PIN_KEY = 'zebra_hp_v3r4_import'
ORIGIN = 'zebra-pc-v3/round-4'
EVIDENCE_KIND = 'post_hoc_selected_upper_bound'
PROBE_PACKAGE_SHA256 = 'f93c90fbeb348f645b48601db2fbe78cfe2e92de63b69e49fa88b3de0d1ce5ba'
SOURCE_SHA256 = 'c9d5fc91962a79d83b0ce9882d55545798a7a4a58e856e195e6d39c0f05fcc85'
REPLY_SHA256 = '782bf1fc4ba350670b539791ef77a6024ad8c1e23d294feac2ac17eba22e2431'
SOURCE_BYTES = 10_955
PACKAGE_SHA256 = '404415581c92ea6fe9caa03c22d41e5b5e5617ce66bec7a3356555f378bbf0b8'
PACKAGE_FILE_SHA256 = 'c69cc4afaeaafb404dfa3e29606f09a6ab15150ec6fcb7e1f4419ddf25755007'
PROCEDURE_SHA256 = 'b0f98638e477c95c8c25f14c79597b2933cdec8327a5bc03ee0ccb0a364122b1'
PROCEDURE_FILE_SHA256 = '95046c5713b25392108cc5479fe524509a08a8d2203b0c452e4aebbae7ce57e6'
PARENT_SHA256 = '405fe690ccff6cb6da29837c8224e6323b96e4209ae425fc2644bbd4ba7eb1ba'
PARENT_FILE_SHA256 = '11da6507f6d878d82e13f34e5997dc1f351616a22a57fa4114dd8dae6dcdb96d'
PROVENANCE_SHA256 = '179bc3ce1e9f28532f4e05fb989a2bc5cd8c63a3c35a7a0f9a64b7da7df93f0e'


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def build(source, reply):
    """Rebuild the documented NEW-on-empty probe treatment from exact input bytes.

    The contemporary wrapper pins v2.9 policy and new fixture metadata. The
    historical builder/records were not supplied, so its hash is provenance,
    not a claim that we reproduced its unavailable wrapper fields.
    """
    require(type(source) is bytes and len(source) == SOURCE_BYTES and _sha(source) == SOURCE_SHA256,
            'The fixed v3r4 source bytes differ from their input pin')
    require(type(reply) is bytes and _sha(reply) == REPLY_SHA256,
            'The fixed v3r4 engineer reply differs from its input pin')
    entry = json.loads(re.search(r'```json\s*(.*?)```', reply.decode('utf-8'), re.S).group(1))['changes'][0]
    procedure = Procedure('p-zebralogic-1-1', p.ZEBRA, entry['description'][:600], tuple(entry['hooks']),
        source.decode('utf-8'), 'engineering_fixture', header=entry['header'],
        max_note_chars=entry['max_note_chars'], requests_second_call=entry['requests_second_call'],
        state_bytes=entry['state_bytes'], excluded_benches=tuple(entry.get('excluded_benches', ())),
        replay_tests=(), policy_version=p.POLICY_VERSIONS[p.ZEBRA_PC_V13])
    parent = empty(step='zebra-hp-v3r4/s0', evidence='engineering_fixture')
    candidate = with_(parent, step='zebra-hp-v3r4/import', add=[procedure])
    validate(candidate, parent)
    require(procedure.policy_version == policy.POLICY_VERSION_V29
            and not policy.check(procedure.source, version=p.POLICY_VERSIONS[p.ZEBRA_PC_V13]),
            'The fixed program must pass current Zebra package policy without editing')
    require(candidate.sha256 == PACKAGE_SHA256 and parent.sha256 == PARENT_SHA256,
            'The fixed v3r4 reconstruction differs from its package pin')
    return parent, candidate


def pins(*, fixture=None):
    """Load detached package/provenance pins; reject even resealed fixture changes."""
    root = safe_path(fixture or FIXTURE)
    files = {
        'inputs/v3r4-c6.py': SOURCE_SHA256, 'inputs/v3r4-c6.reply.txt': REPLY_SHA256,
        'packages/' + PACKAGE_SHA256 + '.json': PACKAGE_FILE_SHA256,
        'packages/' + PARENT_SHA256 + '.json': PARENT_FILE_SHA256,
        'procedures/' + PROCEDURE_SHA256 + '.json': PROCEDURE_FILE_SHA256,
        'provenance.json': PROVENANCE_SHA256,
    }
    for name, expected in files.items():
        require(_sha((root / name).read_bytes()) == expected, 'The fixed v3r4 fixture file hash differs: ' + name)
    parent, rebuilt = build((root / 'inputs/v3r4-c6.py').read_bytes(),
                            (root / 'inputs/v3r4-c6.reply.txt').read_bytes())
    candidate = load(root / 'packages' / (PACKAGE_SHA256 + '.json'))
    require(load(root / 'packages' / (PARENT_SHA256 + '.json')) == parent and candidate == rebuilt,
            'The fixed v3r4 package differs from the exact input reconstruction')
    require(len(candidate.procedures) == len(candidate.for_bench(p.ZEBRA)) == 1,
            'The fixed import is one nonempty Zebra procedure')
    procedure = candidate.procedures[0]
    return {'origin': ORIGIN, 'evidence_kind': EVIDENCE_KIND, 'package_record_sha256': PACKAGE_SHA256,
        'package_file_sha256': PACKAGE_FILE_SHA256, 'package': candidate.to_json(),
        'procedures': [{'id': procedure.id, 'record_sha256': procedure.sha256,
            'file_sha256': PROCEDURE_FILE_SHA256, 'source_sha256': SOURCE_SHA256, 'record': procedure.to_json()}],
        'provenance_sha256': PROVENANCE_SHA256, 'provenance': read_json(root / 'provenance.json')}


def import_step(setting, chain_root, chain, k, bench, parent):
    """Import the sole preregistered program without calling any learning service."""
    require(p.is_v213(p.configuration_of(setting)) and chain == 'D' and k == 1 and bench == p.ZEBRA,
            'The fixed Zebra import is chain D step 1')
    source = pins()
    require(setting.extra.get(PIN_KEY) == source, 'The v3r4 import pins differ from the immutable fixture')
    require(isinstance(parent, Package) and not parent.procedures,
            'The fixed Zebra import starts from the empty parent')
    root, name = safe_path(chain_root), 'D/s1-zebralogic'
    procedures = tuple(replace(Procedure.from_json(row['record']), evidence=setting.evidence)
                       for row in source['procedures'])
    require(len(procedures) == 1, 'An empty import cannot trigger an F/C read')
    imported = Package(procedures, name + '/import', setting.evidence, parent_sha256=PACKAGE_SHA256)
    final = Package(procedures, name, setting.evidence, parent_sha256=parent.sha256)
    validate(final, parent)
    provenance = p.record('import-v2-13', setting.evidence, {
        'origin': ORIGIN, 'evidence_kind': EVIDENCE_KIND, 'source': source,
        'imported_package_sha256': imported.sha256, 'program_bytes_changed': False,
        'procedures': [{'id': original['id'], 'source_record_sha256': original['record_sha256'],
            'source_sha256': original['source_sha256'], 'imported_record_sha256': copied.sha256}
            for original, copied in zip(source['procedures'], procedures)]})
    value = p.record('step-v2-3', setting.evidence, {
        'chain': chain, 'k': k, 'bench': bench, 'step': name, 'learning': 'import', 'origin': ORIGIN,
        'parent_sha256': imported.sha256, 'chain_parent_sha256': parent.sha256,
        'source_package_sha256': PACKAGE_SHA256, 'candidate_sha256': None, 'package_sha256': final.sha256,
        'decision': 'import', 'reason': 'preregistered_post_hoc_v3r4_import', 'decision_sha256': None,
        'fault_items': [], 'violating_items': [], 'units': {}, 'evidence_kind': EVIDENCE_KIND,
        'import_sha256': provenance[p.RECORD_HASH]})
    record_path = root / 's1-zebralogic/step.json'
    if record_path.exists():
        require(p.verified(read_json(record_path), 'step') == value,
                'A finished import step has different pins or parents')
        require(p.verified(read_json(record_path.with_name('import.json')), 'import-v2-13') == provenance,
                'A finished import has different provenance')
        return load(root / 'packages' / (final.sha256 + '.json')), value
    save(root, imported)
    save(root, final)
    write_json(record_path.with_name('import.json'), provenance)
    write_json(record_path, value)
    return final, value
