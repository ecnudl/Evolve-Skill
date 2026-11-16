"""Review regressions: preparation fences and unchanged parent validators."""
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import manifest, profiles as p, v214_smoke, v225_smoke, v225_phase
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
needs_capture = pytest.mark.skipif(not ((Path(__file__).parent / 'fixtures/execskill/v225_parents_before.json').exists() and (Path(__file__).parent / 'fixtures/execskill/v226_parents_before.json').exists()),
                                   reason='parent capture not published (it holds ALFWorld game text)')


@pytest.fixture
def roots(tmp_path, monkeypatch):
    frozen, fresh = tmp_path / 'main-v9', tmp_path / 'main-v10'
    monkeypatch.setattr(p, 'MAIN_V9_ROOT', str(frozen))
    monkeypatch.setitem(p.RUN_ROOTS, p.MAIN_V10, str(fresh))
    return frozen, fresh


@pytest.mark.parametrize('descendant', [False, True])
@pytest.mark.parametrize('entry', ['s0', 'consent', 'manifest-smoke', 'manifest-real', 'selftest'])
def test_preparation_refuses_frozen_root_before_any_input_read(roots, monkeypatch, descendant, entry):
    frozen, fresh = roots
    root = frozen / 'review-smoke' if descendant else frozen
    monkeypatch.setattr(v214_smoke, 'read_json', lambda *_: pytest.fail('Root refusal must precede input reads'))
    from skillopt.execskill import v214_preparation
    monkeypatch.setattr(v214_preparation, 'preparation', lambda *_a, **_k: pytest.fail('Root refusal precedes preparation'))
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        if entry == 's0':
            v214_smoke.collect_s0(fresh / 's0', preparation_file='unused', root=root,
                selftest='unused', configuration=p.MAIN_V10)
        elif entry == 'consent':
            v214_smoke.prepare_consent(root, p.MAIN_V10, consent_file='unused')
        elif entry == 'selftest':
            v214_smoke.selftest(root, preparation_file='unused', configuration=p.MAIN_V10)
        else:
            v214_smoke.make_manifest(fresh / 'manifest.json', root=root, s0_file='unused',
                provenance='unused', roles_repo='unused', route_b_env='unused',
                smoke_chain='G' if entry == 'manifest-smoke' else None, configuration=p.MAIN_V10)
    assert not frozen.exists()


@pytest.mark.parametrize('descendant', [False, True])
@pytest.mark.parametrize('entry', ['s0', 'manifest-smoke', 'manifest-real', 'selftest'])
def test_cli_preparation_refuses_frozen_root_without_opening_it(roots, monkeypatch, descendant, entry):
    from scripts.run_execskill import parser, v214_command
    frozen, fresh = roots
    root = frozen / 'review-smoke' if descendant else frozen
    original = Path.open
    def guarded(path, *args, **kwargs):
        assert path != frozen and frozen not in path.parents, 'Frozen main-v9 path was opened'
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', guarded)
    command = 'manifest' if entry.startswith('manifest') else entry
    argv = ['v214-' + command, '--configuration', p.MAIN_V10, '--out', str(root if entry == 'selftest' else fresh/'out')]
    if command in ('s0', 'selftest'):
        argv += ['--preparation', str(frozen/'preparation.json'), '--zebra-pool', 'unused', '--zebra-split-manifest', 'unused']
        if command == 's0':
            argv += ['--root', str(root), '--selftest', 'unused', '--sheet-runtime', 'unused']
    else:
        argv += ['--root', str(root), '--s0', str(frozen/'s0.json'), '--provenance', 'unused',
                 '--roles-repo', 'unused', '--route-b-env', 'unused', '--sheet-runtime', 'unused']
        if entry == 'manifest-smoke':
            argv += ['--smoke-chain', 'G']
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        v214_command(parser().parse_args(argv))
    assert not frozen.exists()


def test_frozen_consent_source_is_rejected_before_it_is_opened(roots, monkeypatch):
    frozen, fresh = roots
    monkeypatch.setattr(v214_smoke, 'read_json', lambda *_: pytest.fail('Frozen consent must not be opened'))
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        v214_smoke.prepare_consent(fresh, p.MAIN_V10, consent_file=frozen/'shared/consent.json')
    assert not fresh.exists()


def test_real_manifest_rejects_s0_from_another_root_before_copying_consent(roots, monkeypatch):
    frozen, fresh = roots
    checked = p.record('v214-s0', 'smoke', {'configuration': p.MAIN_V10, 'passed': True,
        'root': str(fresh)+'-smoke', 'consent': {'source': 'wrong root'}, 'consent_sha256': 'invalid'})
    monkeypatch.setattr(v214_smoke, 'read_json', lambda *_: checked)
    with pytest.raises(ValueError, match='S0.*root'):
        v214_smoke.make_manifest(fresh/'manifest.json', root=fresh, s0_file='unused', provenance='unused',
            roles_repo='unused', route_b_env='unused', configuration=p.MAIN_V10)
    assert not fresh.exists()


def test_main_v10_preparation_admits_only_registered_run_smoke_and_scratch_roots(roots):
    _, fresh = roots
    for root in (fresh, Path(str(fresh)+'-smoke')/'G', Path(str(fresh)+'-scratch')/'selftest'):
        manifest._check_run_root(root, p.MAIN_V10, 'smoke')
    with pytest.raises(ValueError, match='registered.*root'):
        manifest._check_run_root(fresh.parent/'unregistered', p.MAIN_V10, 'smoke')


@pytest.mark.parametrize('entry', ['raw-manifest', 'snapshot', 'structural'])
def test_other_preparation_entrypoints_refuse_frozen_paths(roots, monkeypatch, entry):
    frozen, fresh = roots
    from skillopt.execskill import v210_smoke
    monkeypatch.setattr(v210_smoke, 'snapshot', lambda *_a, **_k: pytest.fail('Frozen snapshot was entered'))
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        if entry == 'raw-manifest':
            manifest.make(frozen/'manifest.json', root=frozen, evidence='smoke', measured={}, configuration=p.MAIN_V10)
        elif entry == 'snapshot':
            v214_smoke.snapshot(frozen, source=fresh, git_head='unused', configuration=p.MAIN_V10)
        else:
            v225_smoke.structural_smoke(frozen, configuration=p.MAIN_V10)


def test_consent_target_cannot_follow_a_shared_symlink_into_frozen_root(roots, monkeypatch):
    frozen, fresh = roots
    (frozen/'shared').mkdir(parents=True)
    fresh.mkdir()
    (fresh/'shared').symlink_to(frozen/'shared', target_is_directory=True)
    monkeypatch.setattr(v214_smoke, 'read_json', lambda *_: pytest.fail('Frozen symlink target was read'))
    with pytest.raises(ValueError, match='main-v9 root is forbidden|Symlink paths are not supported'):
        v214_smoke.prepare_consent(fresh, p.MAIN_V10, consent_file=fresh.parent/'consent.json')


@pytest.mark.parametrize('pointer', ['preparation_file', 'zebra_pool', 'zebra_split_manifest', 'supply_manifest'])
def test_manifest_refuses_frozen_paths_embedded_in_s0_before_copying_consent(roots, monkeypatch, pointer):
    from skillopt.validator_pilot.api import digest
    frozen, fresh = roots
    fields = {'configuration': p.MAIN_V10, 'passed': True, 'root': str(fresh),
              'consent': {'owner': 'fixture'}, 'consent_sha256': digest({'owner': 'fixture'})}
    if pointer == 'supply_manifest':
        fields['preparation'] = {'data': {'v222_practice': {'supply_manifest': {'path': str(frozen/'pool.json')}}}}
    else:
        fields[pointer] = str(frozen/'pool.json')
    checked = p.record('v214-s0', 'smoke', fields)
    monkeypatch.setattr(v214_smoke, 'read_json', lambda *_: checked)
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        v214_smoke.make_manifest(fresh/'manifest.json', root=fresh, s0_file='unused', provenance='unused',
            roles_repo='unused', route_b_env='unused', configuration=p.MAIN_V10)
    assert not fresh.exists()


def test_manifest_setting_refuses_nested_frozen_inputs_before_setup(roots):
    frozen, fresh = roots
    value = {'configuration': p.MAIN_V10, 'root': str(fresh), 'evidence': 'smoke',
             'data': {'pools': {'searchqa': {'path': str(frozen/'pool.json')}}}}
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        manifest.setting_of(value, 'G')
    assert not fresh.exists()


@needs_capture
def test_structural_smoke_requires_explicit_configuration_like_frozen_main_v9(tmp_path, fast_statistics):
    found = v225_smoke.structural_smoke(tmp_path/'structural')
    found.pop('configuration')
    with pytest.raises(ValueError, match='main-v9 structural smoke pins all card and read mechanisms'):
        v225_smoke.check_structural(found)


def test_measured_smoke_requires_explicit_configuration_like_frozen_main_v9(tmp_path, monkeypatch):
    from tests.test_execskill_v225_smoke import authored_s2
    setting, _, _, _ = authored_s2(tmp_path/'measured', monkeypatch, 'G')
    found = v225_smoke.s2(setting, 'G')
    found.pop('configuration')
    with pytest.raises(ValueError, match='A passing main-v9 measured practice smoke'):
        v225_smoke.check_measured(found)


def test_neutral_scratch_fixture_accepts_arbitrary_checkout_directory(monkeypatch):
    from tests import execskill_v293_fakes as fake
    from tempfile import TemporaryDirectory
    repo = Path(__file__).resolve().parents[1]
    with TemporaryDirectory(prefix='.review-scratch-', dir=repo) as directory:
        monkeypatch.setenv('TMPDIR', directory)
        gen = fake.tmp_path.__wrapped__()
        try:
            assert next(gen).is_relative_to(Path(directory))
        finally:
            gen.close()


@pytest.mark.parametrize('gate_configuration,run_configuration', [(p.MAIN_V10,p.MAIN_V9), (p.MAIN_V9,p.MAIN_V10)])
def test_card_handoff_rejects_gate_from_other_configuration(gate_configuration, run_configuration):
    gate = p.record('v222-cross-gate', 'engineering_fixture', {'configuration': gate_configuration,
        'phase': 'cross_card', 'passed': False, 'candidate_sha256': 'candidate',
        'parent_sha256': 'parent', 'proposed_sha256': 'candidate'})
    rows = [{'gate': gate, 'package_sha256': 'parent', 'target': 'officeqa'}]
    with pytest.raises(ValueError, match='Card handoff binds'):
        if run_configuration == p.MAIN_V9:
            v225_phase.cross_bindings(rows)
        else:
            v225_phase.cross_bindings(rows, configuration=run_configuration)


@needs_capture
def test_parent_capture_contains_all_46_baseline_configurations():
    path = Path(__file__).parent/'fixtures/execskill/v226_parents_before.json'
    before = json.loads(path.read_text())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == '60ed368e3f4cd9e54a608cc9c8bdb3c48653a971627588624d360f2f10cf4a23'
    assert before['source_commit'] == 'e589b5b'
    assert len(before['configurations']) == 46
    assert set(p.CONFIGURATIONS)-set(before['configurations']) == {p.MAIN_V10}
    assert p.MAIN_V9 in before['configurations']
    from tests import test_execskill_v212_profile as parents
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(parents, 'SNAPSHOT', before)
        for name in sorted(before['configurations']):
            parents.test_every_preexisting_profile_keeps_its_exact_registration_prompt_caps_units_and_judges(name)
            tables = before['profile_tables'][name]
            assert manifest._plain({key: getattr(p, key)[name] for key in tables}) == tables


@needs_capture
def test_main_v10_s0_pins_its_46_parent_capture(roots, tmp_path, monkeypatch):
    from skillopt.execskill import sheet_runtime, v214_preparation
    from skillopt.execskill.sandbox import client as sandbox
    _, fresh = roots
    source = tmp_path/'snapshot'
    target = source/'tests/fixtures/execskill'
    target.mkdir(parents=True)
    fixture_root = Path(__file__).parent/'fixtures/execskill'
    for name in ('v225_parents_before.json', 'v226_parents_before.json'):
        (target/name).write_bytes((fixture_root/name).read_bytes())
    monkeypatch.setattr(manifest, 'REPO', source)
    monkeypatch.setattr(v214_smoke, '_source', lambda *_: 'source-sha')
    monkeypatch.setattr(v214_preparation, 'preparation', lambda *_a, **_k: {
        'runtime': {}, 'data': {'v222_practice_supply': {}}})
    monkeypatch.setattr(v214_smoke, 'prepare_consent', lambda *_a, **_k: {'consented': True})
    monkeypatch.setattr(sheet_runtime, 'read', lambda *_a, **_k: {'runtime': {}})
    monkeypatch.setattr(v225_smoke, 'pins', lambda *_a, **_k: {})
    measured = p.record('sandbox-selftest', 'engineering_fixture', {'configuration': p.MAIN_V10,
        'passed': True, 'measured': dict.fromkeys(manifest.MEASURED_FIELDS, 1), 'limits': {},
        'worker_sha256': sandbox.worker_sha256(configuration=p.MAIN_V8)})
    tested = tmp_path/'worker.json'
    write_json(tested, measured)
    found = v214_smoke.collect_s0(tmp_path/'s0', preparation_file=tmp_path/'preparation.json',
        zebra_pool=tmp_path/'zebra.json', zebra_split_manifest=tmp_path/'split.json',
        root=fresh, snapshot_root=source, selftest=tested, checks={'passed': True}, configuration=p.MAIN_V10)
    assert found['parents_before_sha256'] == hashlib.sha256((target/'v226_parents_before.json').read_bytes()).hexdigest()
