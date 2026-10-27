"""Configuration-bound training units, stopping rules and observers; no services."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from skillopt.execskill import engineer, profiles as p, smoke, step, units
from skillopt.execskill.package import FIXTURE, empty
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v24_engineer import context
from tests.test_execskill_v291_feedback import scripted_training
from tests.test_execskill_zpc_pipeline import offline  # noqa: F401


def configured_step(configuration, root):
    return step._Step(setting=SimpleNamespace(extra={'configuration': configuration}),
        services=None, chain='D', bench=p.active_benches(configuration)[0], k=1,
        parent=empty(step='D/s0', evidence=FIXTURE), chain_root=root)


@pytest.mark.parametrize('configuration,rounds', [('zebra-pc-v12', 10), ('alfworld-v9', 6)])
def test_registered_step_units_include_all_engineer_train_confirm_rounds(configuration, rounds, tmp_path):
    st = configured_step(configuration, tmp_path)
    expected = ('run', 'diagnose', 'generate',
        *('%s-r%d' % (kind, r) for r in range(1, rounds + 1) for kind in ('engineer', 'train', 'confirm')),
        'audit-final', 'selftest', 'accept', 'freeze')
    assert st.units == step.training_units(configuration) == expected
    assert len(st.units) == 7 + 3 * rounds
    for kind in ('engineer', 'train', 'confirm'):
        assert kind + '-r%d' % rounds in st.units
        assert kind + '-r%d' % (rounds + 1) not in st.units
        assert units.unit_path(tmp_path, 1, st.bench, kind + '-r%d' % rounds).name == kind + '-r%d' % rounds


@pytest.mark.parametrize('configuration', [c for c in p.CONFIGURATIONS if not p.is_v295(c)])
def test_every_older_configuration_keeps_its_exact_unit_tuple(configuration, tmp_path):
    st = configured_step(configuration, tmp_path)
    if p.LEARNING[configuration] != 'train':
        assert st.units == step.UNITS
    else:
        expected = step.UNITS_V29 if p.is_v29(configuration) else step.UNITS_V2
        assert st.units is expected
        assert p.train_rounds(configuration) == 6


@pytest.mark.parametrize('kind', ['engineer', 'train', 'confirm'])
def test_dispatch_allows_round_ten_but_rejects_round_eleven_before_work(kind, tmp_path, monkeypatch):
    st = configured_step('zebra-pc-v12', tmp_path)
    class ReachedVerification(Exception):
        pass
    def stop_before_services(self):
        raise ReachedVerification
    monkeypatch.setattr(step._Step, 'verify', stop_before_services)
    with pytest.raises(ReachedVerification):
        st.unit(kind + '-r10', lambda path: pytest.fail('No service call'))
    with pytest.raises(ValueError, match='Unknown sub-step unit'):
        st.unit(kind + '-r11', lambda path: pytest.fail('No service call'))


@pytest.mark.parametrize('configuration,rounds,patience', [
    ('zebra-pc-v12', 10, 8), ('alfworld-v9', 6, 4),
    ('zebra-pc-v11', 6, 4), ('alfworld-v8', 6, 4),
    ('zebra-pc-v9', 6, 4), ('alfworld-v7', 6, 4)])
def test_round_limit_and_candidate_only_patience(configuration, rounds, patience, monkeypatch):
    parent, no_candidates, last = scripted_training(monkeypatch, configuration, ['none'] * 12)
    assert len(no_candidates) == rounds and last is None and parent.sha256 == 'parent'
    assert [row['round'] for row in no_candidates] == list(range(1, rounds + 1))
    assert all(not row['patience_counted'] for row in no_candidates)
    _, misses, last = scripted_training(monkeypatch, configuration, ['miss'] * 12)
    assert len(misses) == patience and last.sha256 == 'candidate-' + str(patience)
    assert all(row['patience_counted'] for row in misses)


def test_no_candidate_rounds_do_not_spend_eight_candidate_patience(monkeypatch):
    _, rows, _ = scripted_training(monkeypatch, 'zebra-pc-v12', ['miss', 'none'] * 6)
    assert len(rows) == 10 and sum(row['patience_counted'] for row in rows) == 5


def test_adoption_resets_patience_and_round_ten_still_stops(monkeypatch):
    final, rows, _ = scripted_training(monkeypatch, 'zebra-pc-v12', ['miss'] * 7 + ['adopt'] + ['miss'] * 4)
    assert len(rows) == 10 and final.sha256 == 'candidate-8'
    assert [row['round'] for row in rows if row['adopted']] == [8]


@pytest.mark.parametrize('round_number', [7, 8, 9, 10])
def test_engineer_context_accepts_late_round_and_payload_reports_ten(round_number):
    original, _ = context(configuration='zebra-pc-v12')
    ctx = replace(original, round=round_number)
    request = engineer.payload(ctx)
    assert request['round'] == round_number and request['rounds'] == 10
    assert ctx.calls_cap == original.calls_cap == 41


@pytest.mark.parametrize('configuration,invalid', [('zebra-pc-v12', 11), ('alfworld-v9', 7),
                                                 ('zebra-pc-v11', 7), ('alfworld-v8', 7)])
def test_context_rejects_above_its_configuration_limit(configuration, invalid):
    ctx, _ = context(configuration=configuration, bench=p.active_benches(configuration)[0])
    with pytest.raises(ValueError, match='training round'):
        replace(ctx, round=invalid)
    assert engineer.payload(ctx)['rounds'] == p.train_rounds(configuration)


def test_late_round_accepts_prior_multidigit_training_unit_without_changing_regex():
    ctx, _ = context(configuration='zebra-pc-v12')
    original = ctx.trajectories[0]
    prior = p.record('trajectory', original['evidence'], {
        key: value for key, value in dict(original, unit='D/s1-zebralogic/train-r9').items()
        if key not in ('evidence', 'version', p.RECORD_HASH)})
    late = replace(ctx, round=10, current=[prior])
    assert engineer.TRAIN_UNIT.fullmatch('D/s1-zebralogic/train-r10')['r'] == '10'
    assert engineer.payload(late)['round'] == 10
    with pytest.raises(ValueError, match='earlier training'):
        replace(late, round=9)


@pytest.mark.parametrize('configuration,expected', [('zebra-pc-v12', 10), ('alfworld-v9', 6), (None, 6)])
def test_sx_observer_reads_the_configured_unit_roster(configuration, expected, tmp_path, monkeypatch):
    seen = []
    def missing(path, kind):
        if kind == 'unit':
            seen.append(path.parent.name)
        return None
    monkeypatch.setattr(smoke, '_one', missing)
    registry = SimpleNamespace(entries=lambda *args: {}, path=lambda *args: tmp_path / 'absent-registry')
    value = {'units': {}, 'reason': 'authored', p.RECORD_HASH: 'a' * 64}
    result = smoke.sx_judged(tmp_path, value, registry, [], {}, configuration=configuration)
    assert not result['passed']
    assert 'engineer-r%d' % expected in seen and 'train-r%d' % expected in seen
    assert 'engineer-r%d' % (expected + 1) not in seen
    assert seen == list(step.training_units(configuration) if p.is_v295(configuration) else step.UNITS_V2)


def test_cli_monitor_reports_round_ten_completed_and_open_units(tmp_path, monkeypatch):
    from scripts import run_execskill
    root = tmp_path / 'observer'
    for name in ('engineer-r6', 'engineer-r10', 'confirm-r10'):
        unit = root / 'D/s1-zebralogic' / name
        unit.mkdir(parents=True)
        (unit / 'unit.json').write_text('{}\n')
    pending = root / 'D/s1-zebralogic/train-r10/attempt-1'
    pending.mkdir(parents=True)
    found = []
    monkeypatch.setattr(run_execskill, '_print', found.append)
    run_execskill.monitor(SimpleNamespace(root=str(root)))
    assert found[0]['complete'] == ['D/s1-zebralogic/confirm-r10', 'D/s1-zebralogic/engineer-r10',
                                    'D/s1-zebralogic/engineer-r6']
    assert found[0]['open'] == ['D/s1-zebralogic/train-r10/attempt-1']
