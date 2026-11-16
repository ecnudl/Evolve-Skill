"""Preparation inputs cannot reopen frozen main-v9 paths through source pins."""
from pathlib import Path

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import manifest, profiles as p, v214_preparation, v222_smoke
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    root = tmp_path/'main-v9'
    monkeypatch.setattr(p, 'MAIN_V9_ROOT', str(root))
    original = Path.read_bytes
    def read(path, *args, **kw):
        assert path != root and root not in path.parents, 'Frozen source was opened'
        return original(path, *args, **kw)
    monkeypatch.setattr(Path, 'read_bytes', read)
    return root


def test_preparation_source_refuses_frozen_input_before_open(frozen):
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        v214_preparation.preparation(frozen/'s0.json', configuration=p.MAIN_V10)


def test_preparation_verify_refuses_frozen_source_before_hash(frozen):
    value = {'registration': {'configuration': p.MAIN_V10,
                             'source_main_v4_s0': {'path': str(frozen/'s0.json'), 'sha256': 'unused'}}}
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        v214_preparation.verify(value)


@pytest.mark.parametrize('pin', ['pool', 'tail'])
def test_preparation_nested_source_pins_are_checked_before_allocations(tmp_path, frozen, monkeypatch, pin):
    data = {'pools': {bench: {'path': str(tmp_path/(bench+'.json'))} for bench in p.BENCHES},
            'searchqa_tail': {'path': str(tmp_path/'tail.json')}}
    if pin == 'pool':
        data['pools']['officeqa']['path'] = str(frozen/'pool.json')
    else:
        data['searchqa_tail']['path'] = str(frozen/'tail.json')
    source = p.record('v211-s0', 'smoke', {'configuration': p.MAIN_V4, 'passed': True,
        'sealed_reads': 0, 'pytest': {'passed': True}, 'data': data,
        **{key: dict.fromkeys(p.BENCHES, {}) for key in ('cards', 'contracts', 'runtime')}})
    path = tmp_path/'source.json'
    write_json(path, source)
    monkeypatch.setattr(v214_preparation, '_allocations',
                        lambda *_: pytest.fail('Source path exclusion must precede allocation reads'))
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        v214_preparation.preparation(path, configuration=p.MAIN_V10)


def test_practice_supply_manifest_refuses_frozen_source(frozen):
    imported = {'registration': {'configuration': p.MAIN_V10}, 'data': {}}
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        v222_smoke.prepare_practice(imported, supply_file=frozen/'supply.json')


def test_practice_supply_nested_pin_refuses_frozen_source(tmp_path, frozen):
    imported = {'registration': {'configuration': p.MAIN_V10}, 'data': {}, 'protected_ids': {}}
    path = tmp_path/'supply.json'
    write_json(path, {'configuration': p.MAIN_V10,
                     'pools': {'officeqa': {'path': str(frozen/'pool.json'), 'sha256': 'unused'}}})
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        v222_smoke.prepare_practice(imported, supply_file=path)


def test_practice_imported_pool_refuses_frozen_source_before_loading(frozen, monkeypatch):
    imported = {'registration': {'configuration': p.MAIN_V10}, 'protected_ids': {},
                'data': {'pools': {'searchqa': {'path': str(frozen/'pool.json')}}}}
    monkeypatch.setattr(manifest, '_items', lambda *_: pytest.fail('Frozen imported pool would be opened'))
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        v222_smoke.prepare_practice(imported)


@pytest.mark.parametrize('nested', [False, True])
def test_frozen_input_walk_allows_recorded_interpreter_symlink(tmp_path, frozen, monkeypatch, nested):
    target = tmp_path/'python-real'
    target.touch()
    interpreter = tmp_path/'python'
    interpreter.symlink_to(target)
    value = {'environment': {'python': str(interpreter)}}
    if nested:
        value = {'records': [[value]]}
    monkeypatch.setattr(manifest, 'safe_path', lambda *_: pytest.fail('Exclusion is not a reader'))
    monkeypatch.setattr(Path, 'open', lambda *_a, **_k: pytest.fail('Metadata must not be opened'))
    v214_preparation._check_frozen_inputs(p.MAIN_V10, value)
    manifest._check_frozen_paths(p.MAIN_V10, None, interpreter)


@pytest.mark.parametrize('nested', [False, True])
@pytest.mark.parametrize('descendant', [False, True])
def test_frozen_input_symlink_target_is_refused(tmp_path, frozen, nested, descendant):
    alias = tmp_path/'alias'
    # The target need not exist: exclusion must resolve with strict=False.
    alias.symlink_to(frozen/'missing' if descendant else frozen, target_is_directory=True)
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        if nested:
            v214_preparation._check_frozen_inputs(p.MAIN_V10, {'records': [[str(alias)]]})
        else:
            manifest._check_frozen_paths(p.MAIN_V10, alias)


@pytest.mark.parametrize('location', ['lexical-root', 'lexical-child', 'resolved-root', 'resolved-child'])
def test_symlinked_frozen_root_excludes_both_names(tmp_path, frozen, location):
    target = tmp_path/'frozen-target'
    target.mkdir()
    frozen.symlink_to(target, target_is_directory=True)
    path = frozen if location.startswith('lexical') else target
    if location.endswith('child'):
        path /= 'missing'
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        manifest._check_frozen_paths(p.MAIN_V10, path)


def test_lexical_frozen_descendant_cannot_escape_via_symlink(tmp_path, frozen):
    frozen.mkdir()
    alias = frozen/'escape'
    alias.symlink_to(tmp_path/'outside', target_is_directory=True)
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        manifest._check_frozen_paths(p.MAIN_V10, alias/'missing')


@pytest.mark.parametrize('into_frozen', [False, True])
def test_run_root_retains_reader_symlink_policy(tmp_path, frozen, monkeypatch, into_frozen):
    registered = tmp_path/'main-v10'
    monkeypatch.setitem(p.RUN_ROOTS, p.MAIN_V10, str(registered))
    registered.symlink_to(frozen if into_frozen else tmp_path/'outside', target_is_directory=True)
    message = 'main-v9 root is forbidden' if into_frozen else 'Symlink paths are not supported'
    with pytest.raises(ValueError, match=message):
        manifest._check_run_root(registered, p.MAIN_V10, 'main_v10_real_run')


def test_preparation_passes_recorded_interpreter_symlink_to_allocations(tmp_path, frozen, monkeypatch):
    from tests.test_execskill_v214_preparation import prepared, reseal
    source, _, kwargs, _ = prepared(tmp_path, monkeypatch)
    target = tmp_path/'python-real'
    target.touch()
    interpreter = tmp_path/'python'
    interpreter.symlink_to(target)
    source.setdefault('environment', {})['python'] = str(interpreter)
    path = tmp_path/'source-with-interpreter.json'
    write_json(path, reseal(source))

    class AllocationsReached(Exception):
        pass

    def reached(value):
        assert value['environment']['python'] == str(interpreter)
        raise AllocationsReached

    # Stop immediately after the real source read, verification, input walk and
    # map validation; later practice-supply preparation is outside this regression.
    monkeypatch.setattr(v214_preparation, '_allocations', reached)
    with pytest.raises(AllocationsReached):
        v214_preparation.preparation(path, configuration=p.MAIN_V10, **kwargs)


def test_preparation_reader_still_refuses_symlinked_source(tmp_path, frozen):
    source = tmp_path/'source.json'
    source.symlink_to(tmp_path/'outside.json')
    with pytest.raises(ValueError, match='Symlink paths are not supported'):
        v214_preparation.preparation(source, configuration=p.MAIN_V10)
