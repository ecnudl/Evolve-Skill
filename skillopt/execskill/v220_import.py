"""Two pinned, post-hoc imports for the SearchQA-only v2.20 read; no learning calls."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from skillopt.continual_eval.core import read_json, require, safe_path, write_json

from . import policy, profiles as p
from .package import Package, Procedure, edits, empty, load, save, validate

FIXTURE = Path(__file__).resolve().parents[2] / 'tests/fixtures/execskill/v220_searchqa_hp'
PIN_KEY = 'searchqa_hp_v6_import'
ORIGIN = 'main-v6-final+rejected-searchqa'
SOURCE_EVIDENCE = 'main_v6_real_run'
EVIDENCE_KIND = 'post_hoc_selected_upper_bound'
STEPS = ('main-v6-final', 'searchqa-candidate')
PROCEDURE_IDS = {'G': ('p-searchqa-1-2', 'p-searchqa-1-3'),
                 'D': ('p-searchqa-1-10', 'p-searchqa-1-11')}
PACKAGE_SHA256 = {'G': '846f3b522c962dfdc242a534cadc2fb79cbd3be97543f9e48012befa1cd3440f',
                  'D': '6796a8d412f4f91e9a1f0ffb63fe82bd5ca0d0aee3e6d3e51aa078d60a70e11c'}
FILE_SHA256 = {
    'D/packages/6796a8d412f4f91e9a1f0ffb63fe82bd5ca0d0aee3e6d3e51aa078d60a70e11c.json': '7d7642409bc14c21e239d866dcca1ee5878643b99c8730997b89d9dea3898798',
    'D/procedures/7abdb4afe13d9e60d62c9ff5dff80113eca74765fa2540f8ab95e5f5d33b7c6d.json': 'd448708d8cd4c0405eb20865ece49f2c003a3bc38e644049e269d9654d2aeac2',
    'D/procedures/a5bb2ab29eed5aab5921b7b19663bf007f371fa7a88726916bec4494417880f7.json': '1d4c42501abba744e6e9f586138c9184bc294953359edf8b965cd63d31dc58d1',
    'D/provenance.json': '9f3d0b6f87d74d0039e45b22607e02252f8e27cd688f99c8ee0f706521a1b448',
    'G/packages/846f3b522c962dfdc242a534cadc2fb79cbd3be97543f9e48012befa1cd3440f.json': 'da73d027d5aed88852c9537ba0b346c25d208c98e493e9f2e439845aaebe0f64',
    'G/procedures/cb17af6ecf2dab654389cddddcb214d84f436719f2fdf0ac32eebf75a25cdefe.json': '8744b2f13f43dd4c18dc9ea3647d6c9c818875727f92aab38137da0361ce09f0',
    'G/procedures/e1d1b328d6f7b9522a9725721176bdfdc14f7cf89fcdc34f8e6ebe5844ee09e7.json': '65769c2e697a2a5665ea3bae15f2110ee4d31f37cc5d1fe341dc7fd0ce56a050',
    'G/provenance.json': '136f7b08948170b4d346e2f27635884ec4eb54e61a9a7a83c1d5bdfbfacb812b',
    'manifest.json': '75e0f04477b4e5538de46fb705f071e14bf7b4f27c871238bb187c230e2272c8',
}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _candidate_policy(candidate, chain):
    version = p.POLICY_VERSIONS[p.machinery_configuration(p.MAIN_V6, 'searchqa')]
    validate(candidate)
    require(candidate.evidence == SOURCE_EVIDENCE and candidate.order == PROCEDURE_IDS[chain]
            and candidate.sha256 == PACKAGE_SHA256[chain], 'The fixed SearchQA candidate identity differs')
    for procedure in candidate.procedures:
        require(procedure.origin == 'searchqa' and procedure.evidence == SOURCE_EVIDENCE
                and procedure.policy_version == version and not policy.check(procedure.source, version=version)
                and procedure.lineage['revises'] is None,
                'Every fixed SearchQA procedure must pass main-v6 policy unchanged and be NEW')
    return candidate


def fixture_pins(*, fixture=None):
    """Verify all nine immutable, training-side files and retain rejection provenance."""
    root = safe_path(fixture or FIXTURE)
    for name, expected in FILE_SHA256.items():
        path = safe_path(root / name)
        require(path.is_file() and _sha(path.read_bytes()) == expected,
                'The fixed SearchQA fixture file hash differs: ' + name)
    manifest = read_json(root / 'manifest.json')
    chains = {}
    for chain in p.CHAINS:
        provenance = read_json(root / chain / 'provenance.json')
        candidate = _candidate_policy(load(root / chain / 'packages' / (PACKAGE_SHA256[chain] + '.json')), chain)
        require(manifest['chains'][chain] == provenance and provenance['decision'] == 'reject'
                and provenance['reason'] == 'failed: J1' and provenance['rule'] == 'practical-v2-11-pooled',
                'The SearchQA candidate retains its rejected acceptance provenance')
        procedures = []
        for original, procedure in zip(provenance['procedures'], candidate.procedures):
            require(original['id'] == procedure.id and original['record_sha256'] == procedure.sha256
                    and original['source_bytes'] == len(procedure.source.encode())
                    and original['source_sha256'] == _sha(procedure.source.encode())
                    and original['file_sha256'] == FILE_SHA256[chain + '/procedures/' + procedure.sha256 + '.json'],
                    'The fixed SearchQA procedure differs from its provenance')
            procedures.append({'id': procedure.id, 'record_sha256': procedure.sha256,
                'file_sha256': original['file_sha256'], 'source_sha256': original['source_sha256'],
                'record': procedure.to_json()})
        chains[chain] = {'package_record_sha256': candidate.sha256,
            'package_file_sha256': FILE_SHA256[chain + '/packages/' + candidate.sha256 + '.json'],
            'package': candidate.to_json(), 'procedures': procedures,
            'provenance_sha256': FILE_SHA256[chain + '/provenance.json'], 'provenance': provenance}
    return {'files': dict(FILE_SHA256), 'manifest_sha256': FILE_SHA256['manifest.json'],
            'manifest': manifest, 'chains': chains}


def _file_pin(path):
    path = safe_path(path)
    require(path.is_file(), 'A main-v6 source record is missing: ' + str(path))
    raw, record = path.read_bytes(), read_json(path)
    return {'record': record, 'record_sha256': record.get(p.RECORD_HASH),
            'file_sha256': _sha(raw), 'file_text': raw.decode('utf-8')}


def _checked_file(entry, kind=None, *, procedure=False):
    require(isinstance(entry, dict) and {'record', 'record_sha256', 'file_sha256', 'file_text'} <= set(entry)
            and type(entry['file_text']) is str and _sha(entry['file_text'].encode()) == entry['file_sha256'],
            'A pinned main-v6 file differs from its file hash')
    require(json.loads(entry['file_text']) == entry['record'], 'A pinned main-v6 record differs from its file copy')
    record = entry['record']
    found = Procedure.from_json(record).to_json() if procedure else p.verified(record, kind)
    require(found == record and found[p.RECORD_HASH] == entry['record_sha256'],
            'A pinned main-v6 record hash differs')
    return record


def _bundle_package(bundle, chain):
    require(isinstance(bundle, dict) and set(bundle) == {'chain_complete', 'package', 'procedures'},
            'A main-v6 source bundle names its completion, package and every procedure')
    complete = _checked_file(bundle['chain_complete'], 'chain-complete')
    record = _checked_file(bundle['package'], 'package')
    require(complete['evidence'] == record['evidence'] == SOURCE_EVIDENCE
            and complete.get('identity', {}).get('chain') == chain
            and complete.get('package_sha256') == record[p.RECORD_HASH],
            'The main-v6 completion does not name this chain and package')
    require(isinstance(bundle['procedures'], list) and len(bundle['procedures']) == len(record['procedures']),
            'The main-v6 procedure copies do not match the package')
    procedures = []
    for row, expected in zip(bundle['procedures'], record['procedures']):
        procedure = Procedure.from_json(_checked_file(row, procedure=True))
        require(procedure.sha256 == expected and procedure.evidence == SOURCE_EVIDENCE
                and procedure.id == row.get('id') and _sha(procedure.source.encode()) == row.get('source_sha256'),
                'The main-v6 procedure copy has a different identity or source hash')
        procedures.append(procedure)
    found = Package(tuple(procedures), record['step'], record['evidence'], record['parent_sha256'],
                    tuple(record['retired']), record['narrowed'], record['describer'])
    require(found.to_json() == record, 'The main-v6 package copy does not rebuild exactly')
    return found


def pins(main_v6_root):
    """S0 only: require BOTH completed chains and pin their exact content-addressed records."""
    root = safe_path(main_v6_root)
    require(all(safe_path(root / chain / 'chain-complete.json').is_file() for chain in p.CHAINS),
            'Both main-v6 chains must have chain-complete.json before this read is prepared')
    chains = {}
    for chain in p.CHAINS:
        complete = _file_pin(root / chain / 'chain-complete.json')
        record = p.verified(complete['record'], 'chain-complete')
        package_sha = record.get('package_sha256')
        require(type(package_sha) is str and len(package_sha) == 64
                and all(c in '0123456789abcdef' for c in package_sha), 'The main-v6 completion names a package hash')
        package = _file_pin(root / chain / 'packages' / (package_sha + '.json'))
        value = p.verified(package['record'], 'package')
        require(value[p.RECORD_HASH] == package_sha, 'The main-v6 package filename and record hash differ')
        procedures = []
        for sha in value['procedures']:
            require(type(sha) is str and len(sha) == 64 and all(c in '0123456789abcdef' for c in sha),
                    'The main-v6 package names procedure hashes')
            entry = _file_pin(root / chain / 'procedures' / (sha + '.json'))
            procedure = Procedure.from_json(entry['record'])
            entry.update(id=procedure.id, source_sha256=_sha(procedure.source.encode()))
            procedures.append(entry)
        chains[chain] = {'chain_complete': complete, 'package': package, 'procedures': procedures}
    result = {'origin': ORIGIN, 'evidence_kind': EVIDENCE_KIND, 'main_v6_root': str(root),
              'main_v6': chains, 'candidate': fixture_pins()}
    validate_pins(result)
    return result


def validate_pins(source):
    """Validate S0's copies without touching the main-v6 root; the manifest binds this object."""
    require(isinstance(source, dict) and set(source) == {
        'origin', 'evidence_kind', 'main_v6_root', 'main_v6', 'candidate'}
        and source['origin'] == ORIGIN and source['evidence_kind'] == EVIDENCE_KIND
        and type(source['main_v6_root']) is str and Path(source['main_v6_root']).is_absolute()
        and '..' not in Path(source['main_v6_root']).parts,
        'The SearchQA import pins have a different identity')
    require(source['candidate'] == fixture_pins(), 'The SearchQA candidate pins differ from the immutable fixture')
    require(isinstance(source['main_v6'], dict) and set(source['main_v6']) == set(p.CHAINS),
            'The SearchQA import pins need both completed main-v6 chains')
    for chain in p.CHAINS:
        _bundle_package(source['main_v6'][chain], chain)
    return source


def _restamp(package, evidence):
    return Package(tuple(replace(procedure, evidence=evidence) for procedure in package.procedures),
        package.step, evidence, package.parent_sha256, package.retired, package.narrowed, package.describer)


def _main_package(chain, evidence, source):
    original = _bundle_package(source['main_v6'][chain], chain)
    copied = _restamp(original, evidence)
    start = empty(step=chain + '/s0', evidence=evidence)
    return Package(copied.procedures, chain + '/s1-main-v6-final', evidence, start.sha256,
                   copied.retired, copied.narrowed, copied.describer)


def final_package(chain, evidence, source):
    require(chain in p.CHAINS, 'The SearchQA import chain is G or D')
    validate_pins(source)
    parent = _main_package(chain, evidence, source)
    rows = source['candidate']['chains'][chain]
    new = tuple(replace(Procedure.from_json(row['record']), evidence=evidence) for row in rows['procedures'])
    require(not set(parent.order) & set(PROCEDURE_IDS[chain])
            and all(procedure.lineage['revises'] is None for procedure in new),
            'The rejected SearchQA procedures must be NEW in the main-v6 package')
    candidate = rows['package']
    final = Package(parent.procedures + new, chain + '/s2-searchqa-candidate', evidence, parent.sha256,
        parent.retired, {**parent.narrowed, **candidate['narrowed']}, {**parent.describer, **candidate['describer']})
    validate(final, parent)
    require([(edit.kind, edit.id) for edit in edits(parent, final)] == [('new', pid) for pid in PROCEDURE_IDS[chain]],
            'The second import appends exactly two NEW SearchQA procedures')
    return final


def check_read_package(chain, final, source):
    require(isinstance(final, Package), 'The SearchQA read requires its imported package')
    expected = final_package(chain, final.evidence, source)
    require(final == expected, 'The SearchQA read package is exactly main-v6 order followed by both rejected procedures')
    return final


def _changed(before, after):
    return sorted(key for key in set(before) | set(after) if before.get(key) != after.get(key))


def run_step(setting, chain_root, chain, k, bench, parent):
    require(p.is_v220(p.configuration_of(setting)) and chain in p.CHAINS
            and type(k) is int and 1 <= k <= 2 and bench == STEPS[k - 1],
            'The SearchQA post-hoc chain has only main-v6-final and searchqa-candidate import steps')
    require(isinstance(parent, Package) and parent.evidence == setting.evidence,
            'The SearchQA imports retain the evidenced chain parent')
    source = validate_pins(setting.extra.get(PIN_KEY))
    name = '%s/s%d-%s' % (chain, k, bench)
    if k == 1:
        require(parent == empty(step=chain + '/s0', evidence=setting.evidence),
                'The main-v6 import starts from the empty chain parent')
        original = _bundle_package(source['main_v6'][chain], chain)
        final = _main_package(chain, setting.evidence, source)
    else:
        require(parent == _main_package(chain, setting.evidence, source),
                'The SearchQA candidate appends to the pinned main-v6 import')
        rows = source['candidate']['chains'][chain]
        value = rows['package']
        original = Package(tuple(Procedure.from_json(row['record']) for row in rows['procedures']),
                           value['step'], value['evidence'], value['parent_sha256'],
                           tuple(value['retired']), value['narrowed'], value['describer'])
        final = final_package(chain, setting.evidence, source)
    copied = _restamp(original, setting.evidence)
    provenance = p.record('import-v2-20', setting.evidence, {
        'origin': ORIGIN, 'evidence_kind': EVIDENCE_KIND, 'chain': chain, 'source_step': bench,
        'source': deepcopy(source['main_v6'][chain] if k == 1 else source['candidate']['chains'][chain]),
        'source_package_sha256': original.sha256, 'imported_package_sha256': copied.sha256,
        'chain_parent_sha256': parent.sha256, 'package_sha256': final.sha256,
        'program_bytes_changed': False,
        'changed_procedure_fields': ['evidence', p.RECORD_HASH],
        'changed_imported_package_fields': _changed(original.to_json(), copied.to_json()),
        'changed_chain_package_fields': _changed(original.to_json(), final.to_json()),
        'procedures': [{'id': old.id, 'source_record_sha256': old.sha256,
            'source_sha256': _sha(old.source.encode()), 'imported_record_sha256': new.sha256}
            for old, new in zip(original.procedures, copied.procedures)]})
    record = p.record('step-v2-3', setting.evidence, {
        'chain': chain, 'k': k, 'bench': bench, 'step': name, 'learning': 'import', 'origin': ORIGIN,
        'parent_sha256': copied.sha256, 'chain_parent_sha256': parent.sha256,
        'source_package_sha256': original.sha256, 'candidate_sha256': None,
        'package_sha256': final.sha256, 'decision': 'import', 'reason': 'preregistered_searchqa_hp_v6_import',
        'decision_sha256': None, 'fault_items': [], 'violating_items': [], 'units': {},
        'evidence_kind': EVIDENCE_KIND, 'import_sha256': provenance[p.RECORD_HASH]})
    root = safe_path(chain_root)
    path = root / ('s%d-%s' % (k, bench)) / 'step.json'
    if path.exists():
        require(p.verified(read_json(path), 'step') == record, 'A finished SearchQA import step has different pins or parents')
        require(p.verified(read_json(path.with_name('import.json')), 'import-v2-20') == provenance,
                'A finished SearchQA import has different provenance')
        require(load(root / 'packages' / (final.sha256 + '.json')) == final,
                'A finished SearchQA import package differs')
        return final, record
    save(root, copied)
    save(root, final)
    write_json(path.with_name('import.json'), provenance)
    write_json(path, record)
    return final, record


def structural_smoke(root, source):
    """Exercise both complete import chains using pinned copies only; no clients or tasks."""
    from . import step
    root = safe_path(root)
    setting = SimpleNamespace(root=root, evidence='engineering_fixture',
        extra={'configuration': p.SEARCHQA_HP_V6, PIN_KEY: validate_pins(source)})
    packages, orders = {}, {}
    for chain in p.CHAINS:
        parent = empty(step=chain + '/s0', evidence=setting.evidence)
        for k, bench in enumerate(STEPS, 1):
            parent = step.run_step(setting, chain, bench, k, parent, services=None).package
        check_read_package(chain, parent, source)
        packages[chain], orders[chain] = parent.sha256, list(parent.order)
    return {'passed': True, 'configuration': p.SEARCHQA_HP_V6, 'packages': packages, 'orders': orders,
            'steps': list(STEPS), 'model_calls': 0, 'sealed_reads': 0, 'learning_units': 0}
