"""Authored, zero-call fixtures for main-v6's environment-only memory lock."""
from __future__ import annotations

import fcntl
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import cells, chain, evaluation, profiles as p, step, units, v218_lock as locks
from skillopt.execskill.generators.sheet import Engine
from skillopt.execskill.package import empty
from skillopt.execskill.slots import CALL, EPISODE, LIVE, NATIVE
from tests.execskill_v293_fakes import tmp_path  # noqa: F401 -- OS scratch, never the checkout


def setting(root, configuration=p.MAIN_V6, unit='G/s4-spreadsheetbench/diagnose'):
    return units.Setting(run='fixture-run', root=root / 'root', shared=root / 'root/shared', pools={},
        cards={}, runtime={'spreadsheetbench': {}}, clients=None, budget=None, slots={}, sandbox={},
        evidence='engineering_fixture', extra={'configuration': configuration, 'slot_root': str(root / 'slots'),
            'memory_lock_chain': 'G', 'memory_lock_unit': unit})


def lock_path(s):
    return s.root.parent / 'slots' / chain.HEAVY_LOCK


def probe(path, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, mode | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        return False
    finally:
        os.close(fd)


def modes(s):
    return probe(lock_path(s), fcntl.LOCK_SH), probe(lock_path(s), fcntl.LOCK_EX)


@pytest.mark.parametrize('benches,expected,label', [
    (('spreadsheetbench',), (False, False), 'exclusive'),
    (('alfworld',), (True, False), 'shared'),
    (('alfworld', 'spreadsheetbench'), (False, False), 'exclusive'),
])
def test_environment_modes_holder_and_exception_release(tmp_path, benches, expected, label):
    s = setting(tmp_path)
    with pytest.raises(RuntimeError, match='fixture failure'):
        with locks.environment(s, *benches):
            assert modes(s) == expected
            holders = locks._holders(lock_path(s))
            assert len(holders) == 1
            assert holders[0] == {'unit': s.extra['memory_lock_unit'], 'pid': os.getpid(),
                                  'mode': label, 'since': holders[0]['since']}
            raise RuntimeError('fixture failure')
    assert modes(s) == (True, True)
    assert locks._holders(lock_path(s)) == []


@pytest.mark.parametrize('configuration', [p.MAIN_V5, p.ZEBRA_PC_V15, p.IMPLANT_V5, p.ZEBRA_HP_G3R2])
def test_manager_is_inert_for_frozen_parents(tmp_path, configuration):
    s = setting(tmp_path, configuration)
    with locks.environment(s, 'spreadsheetbench'):
        assert not lock_path(s).exists()
    assert not lock_path(s).exists()


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa', 'zebralogic'])
def test_non_environment_benches_never_take_lock(tmp_path, bench):
    s = setting(tmp_path)
    with locks.environment(s, bench):
        assert not lock_path(s).exists()


def test_nested_same_unit_worker_threads_join_without_reflocking(tmp_path, monkeypatch):
    s = setting(tmp_path)
    real, calls = fcntl.flock, []
    def traced(fd, mode):
        calls.append(mode)
        return real(fd, mode)
    monkeypatch.setattr(locks.fcntl, 'flock', traced)
    def child():
        with locks.environment(s, 'spreadsheetbench'):
            return 'nested'
    with ThreadPoolExecutor(max_workers=1) as pool:
        with locks.environment(s, 'alfworld', 'spreadsheetbench'):
            with locks.environment(s, 'alfworld'):
                assert pool.submit(child).result(timeout=2) == 'nested'
    assert calls == [fcntl.LOCK_EX | fcntl.LOCK_NB]


def test_shared_to_exclusive_upgrade_fails_before_blocking(tmp_path):
    s = setting(tmp_path)
    with locks.environment(s, 'alfworld'):
        with pytest.raises(ValueError, match='strongest lock'):
            with locks.environment(s, 'spreadsheetbench'):
                pytest.fail('An upgrade would self-deadlock')
    assert modes(s) == (True, True)


def test_same_unit_thread_cannot_wait_for_its_own_shared_lock_upgrade(tmp_path):
    s = setting(tmp_path)
    def upgrade():
        with locks.environment(s, 'spreadsheetbench'):
            pytest.fail('A unit cannot block on its own weaker lock')
    with ThreadPoolExecutor(max_workers=1) as pool:
        with locks.environment(s, 'alfworld'):
            with pytest.raises(ValueError, match='strongest lock'):
                pool.submit(upgrade).result(timeout=2)


def test_wait_logs_once_with_non_authoritative_holder_and_elapsed_time(tmp_path, monkeypatch, capsys):
    s = setting(tmp_path)
    path = lock_path(s)
    path.parent.mkdir(parents=True)
    held = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(held, fcntl.LOCK_EX)
    holder = {'unit': 'D/test/spreadsheetbench', 'pid': 98765,
              'mode': 'exclusive', 'since': '2026-11-01T00:00:00+00:00'}
    path.with_name(path.name + '.holder-98765.json').write_text(json.dumps(holder))
    waiting = threading.Event()
    original = locks._waiting
    def observe(*args):
        original(*args)
        waiting.set()
    monkeypatch.setattr(locks, '_waiting', observe)
    def acquire():
        with locks.environment(s, 'alfworld'):
            return locks._holders(path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(acquire)
        try:
            assert waiting.wait(2), 'A contended lock must announce its wait before blocking'
            assert not future.done()
        finally:
            os.close(held)
        assert any(value['pid'] == os.getpid() for value in future.result(timeout=2))
    lines = (s.root / 'G/chain.log').read_text().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith('waiting for memory-heavy lock shared since ')
    assert 'for G/s4-spreadsheetbench/diagnose; holder D/test/spreadsheetbench 98765 exclusive since ' in lines[0]
    assert capsys.readouterr().err.splitlines() == lines
    receipts = [json.loads(line) for line in (s.root / 'G/lock-waits.jsonl').read_text().splitlines()]
    assert len(receipts) == 1
    receipt = receipts[0]
    assert set(receipt) == {'unit', 'mode', 'requested', 'acquired', 'waited_seconds', 'holder_at_request'}
    assert receipt['unit'] == s.extra['memory_lock_unit'] and receipt['mode'] == 'shared'
    assert receipt['acquired'] >= receipt['requested'] and receipt['waited_seconds'] >= 0
    assert receipt['holder_at_request'] == [holder]
    assert not path.with_name(path.name + '.holder-%s.json' % os.getpid()).exists()


def test_holder_io_failure_never_changes_locking(tmp_path, monkeypatch):
    s = setting(tmp_path)
    def unavailable(*args):
        raise OSError('fixture: informational storage unavailable')
    monkeypatch.setattr(locks, '_write', unavailable)
    with locks.environment(s, 'spreadsheetbench'):
        assert modes(s) == (False, False)
    assert modes(s) == (True, True)


def test_workbook_workers_lock_and_other_replays_do_not(tmp_path):
    s = setting(tmp_path)
    observations = []
    @contextmanager
    def factory(package, *, inputs_dir=None, **kwargs):
        observations.append((inputs_dir, modes(s)))
        yield 'fixture-worker'
    opened = locks.workers(factory, s)
    for kind in ('cell', 'replay', 'selftest', 'audit'):
        with opened(None, kind=kind):
            assert modes(s) == (True, True)
        with opened(None, kind=kind, inputs_dir=tmp_path / 'authored-workbook'):
            assert modes(s) == (False, False)
    assert [entry[1] for entry in observations] == [(True, True), (False, False)] * 4


def test_native_engine_operations_lock_without_enclosing_role_calls(tmp_path):
    s = setting(tmp_path)
    observations = []
    def native(*args, **kwargs):
        observations.append(modes(s))
        return 'fixture-result'
    wrapped = locks.engine(Engine(native, native, {}, None), s)
    assert modes(s) == (True, True)  # the surrounding generator/examiner request
    assert wrapped.recalc('authored.xlsx') == 'fixture-result'
    assert modes(s) == (True, True)
    assert wrapped.qualify([]) == 'fixture-result'
    assert observations == [(False, False), (False, False)]


@pytest.mark.parametrize('bench,expected', [('spreadsheetbench', (False, False)),
    ('alfworld', (True, False)), ('officeqa', (True, True))])
def test_solver_cell_boundary_covers_environment_and_releases_on_error(tmp_path, monkeypatch, bench, expected):
    s = setting(tmp_path)
    context = cells.Context(attempt=tmp_path, endpoint=SimpleNamespace(model='fixture'), runtime={}, cards={},
        native=None, episodes=None, worker=None, evidence='engineering_fixture', configuration=p.MAIN_V6,
        environment=lambda actual, unit: locks.environment(s, actual, unit=unit))
    def reached(cell):
        assert modes(s) == expected
        raise RuntimeError('fixture stops before any actual solver or scorer')
    monkeypatch.setattr(cells, '_check_cell', reached)
    with pytest.raises(RuntimeError, match='fixture stops'):
        cells.run_cell(context, {'benchmark': bench, 'unit': s.extra['memory_lock_unit']}, None, None, store=None)
    assert modes(s) == (True, True)


def test_role_only_step_unit_and_completed_readback_take_no_lock(tmp_path, monkeypatch):
    s = setting(tmp_path)
    services = step.Services(SimpleNamespace(bound=lambda root: None), None, lambda *args, **kwargs: nullcontext())
    st = step._Step(s, services, 'G', 'spreadsheetbench', 4,
                    empty(step='G/s0', evidence=s.evidence), s.root / 'G')
    monkeypatch.setattr(st, 'verify', lambda: None)
    def forbidden(*args, **kwargs):
        pytest.fail('Role-only and completed units cannot enter the memory lock')
    monkeypatch.setattr(locks, 'environment', forbidden)
    monkeypatch.setattr(step, 'heavy', forbidden)
    assert st.unit('diagnose', lambda attempt: {'diagnosis': 'authored-fixture'}) == {'diagnosis': 'authored-fixture'}
    assert st.unit('diagnose', forbidden) == {'diagnosis': 'authored-fixture'}


def test_step_worker_and_engine_hooks_are_scoped_to_environment_work(tmp_path, monkeypatch):
    s = setting(tmp_path)
    @contextmanager
    def worker(package, **kwargs):
        yield modes(s)
    native = lambda *args, **kwargs: modes(s)
    services = step.Services(SimpleNamespace(bound=lambda root: None), None, worker,
                             engine=Engine(native, native, {}, None))
    st = step._Step(s, services, 'G', 'spreadsheetbench', 4,
                    empty(step='G/s0', evidence=s.evidence), s.root / 'G')
    monkeypatch.setattr(st, 'verify', lambda: None)
    def work(attempt):
        assert modes(s) == (True, True)
        with st.services.workers(None, kind='replay') as found:
            assert found == (True, True)
        with st.services.workers(None, kind='audit', inputs_dir=tmp_path / 'authored') as found:
            assert found == (False, False)
        assert st.services.engine.recalc('authored') == (False, False)
        return {'ok': True}
    assert st.unit('diagnose', work) == {'ok': True}
    assert st.services is services


def test_mixed_unit_heavy_operations_use_strongest_mode_but_other_work_stays_free(tmp_path, monkeypatch):
    s = setting(tmp_path)
    services = step.Services(SimpleNamespace(bound=lambda root: None), None, lambda *args, **kwargs: nullcontext())
    st = step._Step(s, services, 'G', 'spreadsheetbench', 4,
                    empty(step='G/s0', evidence=s.evidence), s.root / 'G')
    monkeypatch.setattr(st, 'verify', lambda: None)
    def work(attempt):
        with locks.environment(st.setting, 'searchqa'):
            assert modes(s) == (True, True)
        with locks.environment(st.setting, 'alfworld'):
            assert modes(s) == (False, False)
            with locks.environment(st.setting, 'spreadsheetbench'):
                assert modes(s) == (False, False)
        return {'ok': True}
    assert st.unit('selftest', work, benches=('alfworld',)) == {'ok': True}
    assert 'memory_lock_benches' not in s.extra


def test_completed_read_child_bypasses_qualification_and_lock(tmp_path, monkeypatch):
    s = setting(tmp_path)
    root = evaluation.read_root(s, 'G', 'spreadsheetbench')
    write_json(root / 'unit.json', {'fixture': 'completed marker'})
    spec = tmp_path / 'spec.json'
    write_json(spec, {'chain': 'G', 'bench': 'spreadsheetbench', 'package_sha256': 'a' * 64,
                      'unit_root': str(root)})
    monkeypatch.setattr(evaluation, 'setting_of', lambda *args, **kwargs: s)
    monkeypatch.setattr(evaluation, 'consent', lambda *args: None)
    monkeypatch.setattr(chain, 'confirmation', lambda *args, **kwargs: None)
    def forbidden(*args, **kwargs):
        pytest.fail('A completed read child does no environment work')
    monkeypatch.setattr(evaluation, 'prepare_test_qualification', forbidden)
    monkeypatch.setattr(locks, 'environment', forbidden)
    assert evaluation.run_unit_spec({}, spec=spec) == chain.EXIT_COMPLETE


@pytest.mark.parametrize('bench,expected', [('spreadsheetbench', (False, False)), ('alfworld', (True, False))])
def test_active_read_child_keeps_its_environment_mode(tmp_path, monkeypatch, bench, expected):
    s = setting(tmp_path)
    s.runtime[bench] = {}
    s.clients = lambda *args: None
    package = empty(step='G/s0', evidence=s.evidence)
    root = evaluation.read_root(s, 'G', bench)
    spec = tmp_path / 'spec.json'
    write_json(spec, {'chain': 'G', 'bench': bench, 'package_sha256': package.sha256, 'unit_root': str(root)})
    monkeypatch.setattr(evaluation, 'setting_of', lambda *args, **kwargs: s)
    monkeypatch.setattr(evaluation, 'consent', lambda *args: None)
    monkeypatch.setattr(chain, 'confirmation', lambda *args, **kwargs: None)
    monkeypatch.setattr(evaluation, 'prepare_test_qualification', lambda *args, **kwargs: None)
    monkeypatch.setattr(evaluation, 'stage_rows', lambda *args: [])
    monkeypatch.setattr(evaluation, 'make_read_canaries', lambda *args, **kwargs: None)
    monkeypatch.setattr(evaluation, 'load_canaries', lambda *args, **kwargs: [])
    monkeypatch.setattr(evaluation.budgets, 'endpoint', lambda *args, **kwargs: None)
    monkeypatch.setattr(evaluation.units, 'cell_context', lambda *args: None)
    observed = []
    monkeypatch.setattr(evaluation, 'evaluate', lambda *args, **kwargs: observed.append(modes(s)))
    assert evaluation.run_unit_spec({'data': {}}, spec=spec) == chain.EXIT_COMPLETE
    assert observed == [expected] and modes(s) == (True, True)


def test_read_parent_launches_without_holding_child_environment_lock(tmp_path, monkeypatch):
    s = setting(tmp_path)
    package = empty(step='G/s0', evidence=s.evidence)
    monkeypatch.setattr(evaluation, 'prepare_test_qualification', lambda *args: None)
    def forbidden(*args, **kwargs):
        pytest.fail('The parent cannot own the child environment lock')
    monkeypatch.setattr(locks, 'environment', forbidden)
    monkeypatch.setattr(chain, 'heavy', forbidden)
    observed = []
    def launch(own, spec):
        observed.append(spec['bench'])
        write_json(chain.unit_root(s, 'G', spec['bench']) / 'unit.json', p.record('evaluation', s.evidence,
            {'run': s.run, 'chain': 'G', 'packages': {'F': package.sha256}}))
        return chain.EXIT_COMPLETE
    chain.evaluate(s, 'G', package, launch=launch)
    assert set(observed) == set(evaluation.read_benches(p.MAIN_V6))


def test_completed_chain_readback_does_not_qualify_launch_or_lock(tmp_path, monkeypatch):
    s = setting(tmp_path)
    package = empty(step='G/s0', evidence=s.evidence)
    for bench in evaluation.read_benches(p.MAIN_V6):
        write_json(chain.unit_root(s, 'G', bench) / 'unit.json', p.record('evaluation', s.evidence,
            {'run': s.run, 'chain': 'G', 'packages': {'F': package.sha256}}))
    def forbidden(*args, **kwargs):
        pytest.fail('All read units are complete')
    monkeypatch.setattr(evaluation, 'prepare_test_qualification', forbidden)
    monkeypatch.setattr(locks, 'environment', forbidden)
    assert set(chain.evaluate(s, 'G', package, launch=forbidden)) == set(evaluation.read_benches(p.MAIN_V6))


def test_sheet_qualification_itself_owns_exclusive_environment_lock(tmp_path, monkeypatch):
    s = setting(tmp_path)
    s.slots[NATIVE] = None
    monkeypatch.setattr(evaluation, 'consent', lambda *args: None)
    monkeypatch.setattr(evaluation, 'contained', lambda *args: nullcontext())
    observations = []
    monkeypatch.setattr(evaluation, 'test_tasks', lambda *args, **kwargs: observations.append(modes(s)))
    evaluation.prepare_test_qualification(s, 'G', panel=lambda *args: pytest.fail('No data access'))
    assert observations == [(False, False)]
    assert modes(s) == (True, True)


def test_read_route_worker_locks_only_workbook_mount(tmp_path, monkeypatch):
    s = units.for_unit(setting(tmp_path), 'G', 'spreadsheetbench', 'G/test/spreadsheetbench')
    s.slots.update({LIVE: None, CALL: None})
    @contextmanager
    def worker(package, **kwargs):
        yield modes(s)
    monkeypatch.setattr(evaluation.sandbox, 'with_worker', worker)
    with evaluation._route_worker(s, None, None) as found:
        assert found == (True, True)
    with evaluation._route_worker(s, None, None, inputs_dir=tmp_path / 'authored') as found:
        assert found == (False, False)


def test_cell_worker_uses_zebra_diagnostics_per_actual_bench(tmp_path, monkeypatch):
    s = setting(tmp_path)
    class Pool:
        def limited(self, cap):
            return self
    s.slots.update({name: Pool() for name in (LIVE, CALL, NATIVE, EPISODE)})
    monkeypatch.setattr(units, 'Worker', lambda **kwargs: kwargs)
    context = units.cell_context(s, tmp_path, SimpleNamespace(model=p.CHAINS['G']))
    assert context.environment is not None
    assert context.worker('zebralogic')['diagnostics_configuration'] == p.ZEBRA_PC_V15
    assert 'diagnostics_configuration' not in context.worker('spreadsheetbench')
    old = replace(s, extra={**s.extra, 'configuration': p.MAIN_V5})
    old_context = units.cell_context(old, tmp_path, SimpleNamespace(model=p.CHAINS['G']))
    assert old_context.environment is None
    assert 'diagnostics_configuration' not in old_context.worker('zebralogic')


@pytest.mark.parametrize('configuration', [p.MAIN_V6, p.MAIN_V5, p.IMPLANT_V5])
def test_preparation_locks_native_measurement_and_checks_both_main_v6_workers(tmp_path, monkeypatch, configuration):
    from skillopt.execskill import s0, smoke, v214_preparation, v214_smoke
    s = setting(tmp_path, configuration)
    workbook = tmp_path / 'authored-workbook.xlsx'
    workbook.write_bytes(b'authored fixture bytes; native operation is mocked')
    selected = list(p.active_benches(configuration))
    monkeypatch.setattr(p, 'SLOT_ROOT', str(tmp_path / 'slots'))
    monkeypatch.setattr(v214_preparation, 'preparation', lambda *args, **kwargs:
                        {'data': {'pools': {bench: bench for bench in selected}}})
    monkeypatch.setattr(v214_smoke.manifest, '_items', lambda path, bench:
        [{'task_id': 'authored-' + bench, 'public': {'input_files': [str(workbook)]}
            if bench == 'spreadsheetbench' else {}, 'private': {}}])
    seen = []
    def worker(out, **kwargs):
        seen.append(kwargs['configuration'])
        assert modes(s) == (True, True)  # empty-package pings do not mount a workbook
        extra = 5 if kwargs['configuration'] == p.ZEBRA_PC_V15 else 0
        return p.record('sandbox-selftest', 'engineering_fixture', {'passed': True, 'limits': {},
            'measured': {'vsz_kib': 10 + extra, 'rss_kib': 20 + extra, 'view_bytes_p99': 30}})
    monkeypatch.setattr(smoke, 'sandbox_selftest', worker)
    monkeypatch.setattr(v214_smoke.sandbox, 'Docker', lambda: object())
    def native(path, docker):
        assert path == workbook
        assert modes(s) == ((False, False) if configuration == p.MAIN_V6 else (True, True))
        return 123
    monkeypatch.setattr(s0, 'native_peak', native)
    result = v214_smoke.selftest(tmp_path / 'selftest', preparation_file='authored', zebra_pool='authored',
                               zebra_split_manifest='authored', configuration=configuration)
    assert seen == ([p.MAIN_V6, p.ZEBRA_PC_V15] if configuration == p.MAIN_V6 else [configuration])
    assert result['measured'] == {'vsz_kib': 15 if configuration == p.MAIN_V6 else 10,
        'rss_kib': 25 if configuration == p.MAIN_V6 else 20, 'view_bytes_p99': 30, 'native_peak_rss_kib': 123}
    assert ('zebra_worker' in result['measurement_sources']) == (configuration == p.MAIN_V6)
