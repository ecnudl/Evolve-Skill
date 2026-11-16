"""Older configurations never enter v2.26 containment or recovery adapters."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import profiles as p, step, v221_learning, v221_split, v222_gate, v226_candidates
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


LEGACY = tuple(configuration for configuration in p.CONFIGURATIONS if not p.is_v226(configuration))


def forbidden(*args, **kwargs):
    pytest.fail('An older configuration entered a v2.26-only adapter')


def state(root, configuration):
    return SimpleNamespace(
        setting=SimpleNamespace(extra={'configuration': configuration}, cards={}),
        parent=object(), chain_root=root / 'G', root=root / 'G' / 's1-searchqa',
        k=1, bench='searchqa', label=lambda unit: 'G/s1-searchqa/' + unit,
        done=lambda unit: None, runtime=lambda: {},
    )


@pytest.mark.parametrize('configuration', LEGACY)
def test_older_accept_and_selftest_do_not_inspect_candidate_before_unit(tmp_path, monkeypatch, configuration):
    st = state(tmp_path, configuration)
    calls = []
    sentinel = object()
    def unit(name, work, **options):
        calls.append((name, options))
        return sentinel
    st.unit = unit
    monkeypatch.setattr(step, '_candidate_guard', forbidden)
    monkeypatch.setattr(v226_candidates, 'guard', forbidden)
    assert step._accept(st, {'accept': []}, object(), None) is sentinel
    assert step._selftest(st, 'selftest', object(), None) is sentinel
    assert [name for name, _ in calls] == ['accept', 'selftest']
    assert set(calls[0][1]) == {'settle'}
    assert calls[1][1] == {'benches': ()}


@pytest.mark.parametrize('configuration', [p.MAIN_V2_3, p.MAIN_V7, p.MAIN_V9])
def test_older_empty_selftest_executes_without_candidate_identity(tmp_path, monkeypatch, configuration):
    st = state(tmp_path, configuration)
    st.unit = lambda name, work, **options: work(tmp_path / 'attempt-1')
    monkeypatch.setattr(step, '_candidate_guard', forbidden)
    monkeypatch.setattr(step, '_system_cells', forbidden)
    assert step._selftest(st, 'selftest', object(), None) == {
        'sets': {}, 'blocked': False, 'reason': 'no_generated_items', 'cells': 0,
    }


@pytest.mark.parametrize('phase', ['train', 'confirm', 'split-train', 'split-confirm'])
def test_main_v9_learning_passes_original_work_directly_to_unit(tmp_path, monkeypatch, phase):
    st = state(tmp_path, p.MAIN_V9)
    calls = []
    sentinel = object()
    def unit(name, work, **options):
        calls.append(name)
        return sentinel
    st.unit = unit
    monkeypatch.setattr(step, '_candidate_guard', forbidden)
    monkeypatch.setattr(step, '_request_core', forbidden)
    candidate, incumbent = object(), object()
    if phase == 'train':
        result = step._train_eval(st, {'run': []}, 1, incumbent, candidate, None)
        expected = 'train-r1'
    elif phase == 'confirm':
        result = step._confirm_eval(st, {'confirm': [{'task_id': 'a'}, {'task_id': 'b'}]},
                                    1, incumbent, candidate, exercise=True)
        expected = 'confirm-r1'
    else:
        confirmation = phase == 'split-confirm'
        result = v221_split.evaluate(st, {}, 1, 1, incumbent, candidate, object(), {}, None,
                                    confirmation=confirmation)
        expected = ('confirm' if confirmation else 'train') + '-r1-split-p1'
    assert result is sentinel
    assert calls == [expected]


@pytest.mark.parametrize('configuration', [p.PILOT, p.MAIN_V7, p.MAIN_V9])
def test_older_completion_and_previous_reads_use_frozen_loader(tmp_path, monkeypatch, configuration):
    st = state(tmp_path, configuration)
    unit = p.record('unit', 'engineering_fixture', {'result': {'finished': True}})
    write_json(st.root / 'train-r1' / 'unit.json', unit)
    previous = p.record('step', 'engineering_fixture', {
        'decision': 'accept', 'fault_items': ['original-item'], 'violating_items': 2,
    })
    write_json(st.root / step.STEP_FILE, previous)
    monkeypatch.setattr(step, '_read_record', forbidden)
    assert step._Step.done(st, 'train-r1') == {'finished': True}
    st.k = 2
    assert step._previous(st) == {
        'decision': 'accepted', 'faults': {'fault_items': ['original-item']},
        'format': {'violating_items': 2},
    }


@pytest.mark.parametrize('configuration', [p.MAIN_V2_3, p.MAIN_V7, p.MAIN_V9])
def test_older_pair_signatures_keep_candidate_first_without_arm_adapters(tmp_path, monkeypatch, configuration):
    st = state(tmp_path, configuration)
    candidate, parent = object(), object()
    seen = []
    def label(package):
        return 'candidate' if package is candidate else 'parent'
    @contextmanager
    def workers(package, key):
        seen.append(('open', label(package), key))
        yield package
        seen.append(('close', label(package), key))
    def signature(bench, package, view, worker, **options):
        assert worker is package
        seen.append(('signature', label(package), view))
        return {'identity': label(package)}
    monkeypatch.setattr(step, '_item_workers', lambda st, publics: workers)
    monkeypatch.setattr(step.request_reuse, 'signature', signature)
    monkeypatch.setattr(v226_candidates, 'package_arm', forbidden)
    monkeypatch.setattr(step, 'nullcontext', forbidden, raising=False)
    assert step._pair_signatures(st, candidate, parent, {'a': {}}, [('a', 'view')]) == {
        'a': {"S'": {'identity': 'candidate'}, 'S': {'identity': 'parent'}},
    }
    assert seen == [
        ('open', 'candidate', 'a'), ('signature', 'candidate', 'view'), ('close', 'candidate', 'a'),
        ('open', 'parent', 'a'), ('signature', 'parent', 'view'), ('close', 'parent', 'a'),
    ]


def test_frozen_live_math_acceptance_bypasses_all_v226_adapters(tmp_path, monkeypatch):
    """Exercise the actual J7 recorder fixture with all new adapters unavailable."""
    from tests.test_execskill_fivebench_step import (
        test_j7_the_accept_unit_registers_the_probe_and_sends_it_options_only as check_j7,
    )
    for name in ('_candidate_guard', '_evaluation_arm', '_system_cells', '_read_record'):
        monkeypatch.setattr(step, name, forbidden)
    check_j7(tmp_path, monkeypatch)


@pytest.mark.parametrize('configuration', [p.MAIN_V8, p.MAIN_V9])
def test_older_cross_inspection_does_not_read_new_fault_attribution_inputs(monkeypatch, configuration):
    class Package:
        def __init__(self, sha):
            self.sha256 = sha

        @property
        def procedures(self):
            pytest.fail('Legacy cross inspection read v2.26 fault-attribution inputs')

    parent, candidate = Package('p' * 64), Package('c' * 64)
    seen = []
    @contextmanager
    def workers(package, key):
        seen.append(('open', package.sha256, key))
        yield package
        seen.append(('close', package.sha256, key))

    signature = {'request_sha256': 'r' * 64, 'post_call': [], 'faults': []}
    monkeypatch.setattr(v222_gate.reuse, 'signature', lambda *args, **kwargs: signature)
    monkeypatch.setattr(v226_candidates, 'arm', forbidden)
    result = v222_gate.inspect('searchqa', parent, candidate,
        [{'task_id': 'a', 'public': {}}], workers, views={'a': {}}, configuration=configuration)
    assert result['identity_proven'] is True
    assert result['faults'] == []
    assert 'candidate_faults' not in result and 'inherited_faults' not in result
    assert seen == [('open', parent.sha256, 'a'), ('close', parent.sha256, 'a'),
                    ('open', candidate.sha256, 'a'), ('close', candidate.sha256, 'a')]


def test_main_v9_confirmation_stops_reading_after_first_exhausted_round(tmp_path, monkeypatch):
    st = state(tmp_path, p.MAIN_V9)
    st.bench = p.ZEBRA  # Zebra shares the frozen confirmation slice across rounds.
    read = []
    def done(unit):
        read.append(unit)
        assert unit == 'confirm-r1', 'An exhausted legacy confirmation must not open later rounds'
        return {'slice_ids': ['already-confirmed']}
    st.done = done
    exhausted = object()
    monkeypatch.setattr(v221_learning, 'exhausted_confirmation', lambda *args: exhausted)
    assert step._confirm_eval(st, {}, 3, object(), object()) is exhausted
    assert read == ['confirm-r1']


@pytest.mark.parametrize('configuration', [p.PILOT, p.MAIN_V9])
def test_older_accept_settlement_reads_raw_json_and_ignores_candidate_error_key(tmp_path, monkeypatch, configuration):
    st = state(tmp_path, configuration)
    registry = object()
    st.services = SimpleNamespace(registry=registry)
    captured = {}
    def unit(name, work, **options):
        captured.update(options)
    st.unit = unit
    monkeypatch.setattr(step, '_read_record', forbidden)
    calls = []
    monkeypatch.setattr(step.acceptance, 'settle', lambda *args, **kwargs: calls.append((args, kwargs)))
    step._accept(st, {'accept': []}, object(), None)
    attempt = st.root / 'accept' / 'attempt-1'
    decision, sealed = {'decision': 'reject'}, {'original': 'unverified sealed input'}
    write_json(attempt / 'decision' / 'decision.json', decision)
    write_json(st.root / 'accept' / 'sealed.json', sealed)
    captured['settle'](attempt, {'candidate_error': {'kind': 'legacy extension key'}})
    assert calls == [((decision, sealed, registry, {}), {'attempt': 1})]
