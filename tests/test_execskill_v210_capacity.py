"""Reserve the immutable ALF import within the inherited 64 KB/24-procedure cap."""
from types import SimpleNamespace

import pytest

from skillopt.execskill import engineer, instruction_start, profiles as p, policy, v210_import as imp
from skillopt.execskill.errors import PackageInvalid
from skillopt.execskill.package import Package, Procedure
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

SOURCE = 'def applies(view):\n    return True\ndef before_call(view, state):\n    return {"facts": ["count 2"]}\n'


def source(size):
    result = SOURCE + '\n#' + 'x' * (size - len(SOURCE.encode()) - 2)
    assert len(result.encode()) == size
    return result


def parent(sizes):
    return Package(tuple(Procedure('p-searchqa-1-%d' % n, 'searchqa', 'Counts public values.',
        ('applies', 'before_call'), source(size), 'engineering_fixture', max_note_chars=100,
        policy_version=policy.POLICY_VERSION_V23) for n, size in enumerate(sizes, 1)),
        'D/s3-livemath', 'engineering_fixture')


def context(package, configuration=p.MAIN_V3):
    return SimpleNamespace(configuration=configuration, parent=package, base=package, bench='spreadsheetbench',
        k=4, mode='train', step='D/s4-spreadsheetbench', label='D/s4-spreadsheetbench/engineer-r1',
        evidence=package.evidence, sheet={}, reserved=frozenset(),
        card=instruction_start.pins()['spreadsheetbench']['text'], current=[], references={}, echo=True, detectors={}, previous=None,
        round=1, history=[], training=None, lint=[])


def change(size, n=1):
    return engineer.Change(n, 'new', {'kind': 'new', 'description': 'Counts public values.',
        'hooks': ['applies', 'before_call'], 'max_note_chars': 100, 'excluded_benches': [], 'replay_tests': []},
        source(size), 'a' * 64)


def test_exact_source_boundary_preserves_final_original_cap(tmp_path):
    prior = parent([6000] * 9 + [4596])
    assert imp.IMPORT_SOURCE_BYTES == 5404 and imp.LEARNED_SOURCE_BYTES == 58596
    assert imp.check_learning_capacity(prior) is prior
    st = SimpleNamespace(extra={'configuration': p.MAIN_V3, 'alfworld_v11_import': imp.pins()},
                         evidence='engineering_fixture')
    package, _ = imp.import_step(st, tmp_path, 'D', 5, 'alfworld', prior)
    assert sum(len(proc.source.encode()) for proc in package.procedures) == p.MAX_PACKAGE_BYTES == 64000
    too_large = parent([6000] * 9 + [4597])
    with pytest.raises(PackageInvalid, match='58596'):
        imp.check_learning_capacity(too_large)


def test_exact_slot_boundary_reserves_three_without_expanding_historical_limit(tmp_path):
    prior = parent([200] * 21)
    assert imp.LEARNED_PROCEDURES == 21 and imp.IMPORT_PROCEDURES == 3
    st = SimpleNamespace(extra={'configuration': p.MAIN_V3, 'alfworld_v11_import': imp.pins()},
                         evidence='engineering_fixture')
    package, _ = imp.import_step(st, tmp_path, 'G', 5, 'alfworld', prior)
    assert len(package.procedures) == p.MAX_PROCEDURES == 24
    with pytest.raises(PackageInvalid, match='21 procedures'):
        imp.check_learning_capacity(parent([200] * 22))


def test_one_change_checks_capacity_before_any_expensive_registrar_work():
    ctx = context(parent([6000] * 9 + [4000]))
    assert sum(len(proc.source.encode()) for proc in engineer._build(change(596), ctx).procedures) == 58596
    report = engineer.check(change(597), ctx)
    assert report['failed'] == 'C3'
    assert [entry['check'] for entry in report['checks']] == ['C1', 'C2', 'C4', 'C3']
    assert report['checks'][-1]['detail']['caps']['package_source_bytes'] == 58596
    assert report['checks'][-1]['detail']['caps']['package_procedures'] == 21


def test_combined_changes_reserve_capacity_after_each_individual_change_passes():
    prior = parent([6000] * 9 + [4000])
    ctx = context(prior)
    changes = [change(400, n) for n in (1, 2)]
    for proposed in changes:
        engineer._build(proposed, ctx)
    trained, kept = engineer._combined_train(ctx, changes)
    assert kept == changes[:1]
    assert imp.learning_capacity(trained)['remaining_source_bytes'] == 196
    single, single_kept = engineer._combined(prior, changes, ctx.step, configuration=p.MAIN_V3)
    assert single_kept == kept and single.procedures == trained.procedures
    historical, old_kept = engineer._combined_train(context(prior, p.MAIN_V2_3), changes)
    assert old_kept == changes and sum(len(proc.source.encode()) for proc in historical.procedures) == 58800


def test_proposal_payload_reports_true_reserved_and_remaining_capacity_only_for_main_v3():
    prior = parent([200])
    new = engineer.payload(context(prior))
    assert new['package_capacity'] == {
        'package_source_bytes': 58596, 'package_procedures': 21,
        'reserved_import_source_bytes': 5404, 'reserved_import_procedures': 3,
        'used_source_bytes': 200, 'used_procedures': 1,
        'remaining_source_bytes': 58396, 'remaining_procedures': 20}
    assert 'package_capacity' not in engineer.payload(context(prior, p.MAIN_V2_3))
