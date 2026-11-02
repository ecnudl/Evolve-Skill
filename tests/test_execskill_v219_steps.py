"""Cross-v5 composes existing pinned imports and the existing environment lock."""
from dataclasses import replace
import hashlib
import os
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import write_json
from skillopt.execskill import (chain, manifest, policy, profiles as p, step, units,
                               v210_import, v217_implant as implant, v218_lock as locks)
from skillopt.execskill.errors import PackageInvalid
from skillopt.execskill.package import empty, validate
from skillopt.execskill.slots import CALL, EPISODE, LIVE, NATIVE
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_v217i_steps import forbid_learning, setting
from tests.test_execskill_v218_locks import lock_path, modes, setting as lock_setting


def build(st, c):
    start = current = empty(step=c + '/s0', evidence=st.evidence)
    result = []
    for k, bench in enumerate(p.MAIN_V5_ORDER, 1):
        found = step.run_step(st, c, bench, k, current, services=None)
        result.append(found)
        current = found.package
    return start, result


@pytest.mark.parametrize('c', ['G', 'D'])
def test_fixed_chain_reuses_implant_module_and_exact_packages_without_learning(tmp_path, monkeypatch, c):
    forbid_learning(monkeypatch)
    old = setting(tmp_path / 'parent', configuration=p.IMPLANT_V5)
    new = setting(tmp_path / 'child', configuration=p.CROSS_V5)
    _, expected = build(old, c)
    original, called = implant.run_step, []

    def existing_implementation(*args, **kwargs):
        called.append((args[2], args[3], args[4]))
        return original(*args, **kwargs)

    monkeypatch.setattr(implant, 'run_step', existing_implementation)
    start, found = build(new, c)
    assert called == [(c, k, bench) for k, bench in enumerate(p.MAIN_V5_ORDER, 1)]
    assert [row.package for row in found] == [row.package for row in expected]
    assert found[0].package is found[1].package is start
    assert found[3].package is found[2].package
    assert len(found[2].package.procedures) == 1 and len(found[4].package.procedures) == 4
    for k, row in enumerate(found, 1):
        assert row.record['units'] == {}
        assert row.record['candidate_sha256'] is row.record['decision_sha256'] is None
        assert row.record['decision'] == ('skip' if k in (1, 2, 4) else 'import')
        assert row.record['reason'] == expected[k - 1].record['reason']
        if k in (1, 2, 4):
            assert row.record['learning'] == 'none'
            assert row.record['package_sha256'] == row.record['parent_sha256']
    assert build(new, c) == (start, found)
    assert step.training_units(p.CROSS_V5) == ()
    assert not list(new.root.rglob('unit.json')) and not list(new.root.rglob('attempt-*'))


@pytest.mark.parametrize('c', ['G', 'D'])
def test_real_identity_changes_only_evidence_and_derived_package_hashes(tmp_path, c):
    old = setting(tmp_path / 'parent', configuration=p.IMPLANT_V5, evidence='implant_v5_test_read')
    new = setting(tmp_path / 'child', configuration=p.CROSS_V5, evidence='cross_v5_test_read')
    _, parent = build(old, c)
    _, child = build(new, c)
    final, expected = child[-1].package, parent[-1].package
    assert final.order == expected.order
    assert final.order[0] == implant.pins()[c]['procedures'][0]['id']
    assert final.order[1:] == tuple(row[0] for row in v210_import.PROCEDURES)
    clean_procedure = lambda row: {key: value for key, value in row.items() if key not in ('evidence', p.RECORD_HASH)}
    for got, before in zip(final.procedures, expected.procedures):
        assert got.source.encode() == before.source.encode()
        assert clean_procedure(got.to_json()) == clean_procedure(before.to_json())
        assert got.evidence == 'cross_v5_test_read' and before.evidence == 'implant_v5_test_read'
        assert got.sha256 != before.sha256
    assert final.step == expected.step and final.retired == expected.retired
    assert final.narrowed == expected.narrowed and final.describer == expected.describer
    assert final.parent_sha256 != expected.parent_sha256 and final.sha256 != expected.sha256
    validate(final, child[2].package)
    assert v210_import.learning_capacity(final)['remaining_procedures'] == v210_import.learning_capacity(expected)['remaining_procedures']
    for k in (0, 1, 2, 3):
        assert child[k].record['evidence_kind'] == 'post_hoc_selected_upper_bound_transfer'
    # The unchanged ALF composer retains its own import-kind provenance.
    assert child[4].record['evidence_kind'] == parent[4].record['evidence_kind'] == 'import'


@pytest.mark.parametrize('c', ['G', 'D'])
def test_bad_pins_nonempty_parent_and_policy_failure_keep_original_refusals(tmp_path, monkeypatch, c):
    st = setting(tmp_path, configuration=p.CROSS_V5)
    parent = empty(step=c + '/s0', evidence=st.evidence)
    st.extra[implant.PIN_KEY][c]['package_record_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='source pins differ'):
        step.run_step(st, c, p.ZEBRA, 3, parent, services=None)
    st.extra[implant.PIN_KEY] = implant.pins()
    nonempty = implant.zebra_package(c, parent)
    with pytest.raises(ValueError, match='empty s2'):
        step.run_step(st, c, p.ZEBRA, 3, nonempty, services=None)
    source = implant.pins()[c]['procedures'][0]
    before = hashlib.sha256(source['record']['source'].encode()).hexdigest()
    monkeypatch.setattr(policy, 'check', lambda *args, **kwargs: [
        SimpleNamespace(to_json=lambda: {'reason': 'authored policy refusal'})])
    with pytest.raises(PackageInvalid, match='Policy violations'):
        step.run_step(st, c, p.ZEBRA, 3, parent, services=None)
    assert hashlib.sha256(source['record']['source'].encode()).hexdigest() == before == source['source_sha256']
    assert not (tmp_path / c).exists()


@pytest.mark.parametrize('c', ['G', 'D'])
@pytest.mark.parametrize('k', [1, 2, 3, 4, 5])
def test_child_entry_reuses_confirmation_and_builds_no_learning_services(tmp_path, monkeypatch, c, k):
    st = setting(tmp_path, configuration=p.CROSS_V5)
    start, found = build(st, c)
    parent = start if k == 1 else found[k - 2].package
    forbid_learning(monkeypatch)
    confirmed = []
    monkeypatch.setattr(step, 'confirmation', lambda *args, **kwargs: confirmed.append((args, kwargs)))
    monkeypatch.setattr(manifest, 'setting_of', lambda *args, **kwargs: st)
    monkeypatch.setattr(step.budgets, 'own_ledger', lambda *args: SimpleNamespace(declare=lambda caps: None))
    monkeypatch.setattr(step, 'parent_of', lambda *args: parent)
    spec = tmp_path / 'step-spec.json'
    write_json(spec, {'chain': c, 'bench': p.MAIN_V5_ORDER[k - 1], 'k': k})
    result = step.run_unit_spec({'configuration': p.CROSS_V5, 'root': str(tmp_path), p.RECORD_HASH: 'authored'}, spec=spec)
    assert result == chain.EXIT_COMPLETE and len(confirmed) == 1
    assert confirmed[0][1] == {'configuration': p.CROSS_V5}


@pytest.mark.parametrize('configuration', [p.CROSS_V5, p.MAIN_V6, p.IMPLANT_V5])
@pytest.mark.parametrize('bench, active', [('spreadsheetbench', (False, False)),
                                         ('alfworld', (True, False)), ('searchqa', (True, True))])
def test_environment_lock_is_shared_implementation_and_parent_stays_inert(tmp_path, configuration, bench, active):
    st = lock_setting(tmp_path, configuration, unit='G/test/' + bench)
    with locks.environment(st, bench):
        assert modes(st) == (active if configuration != p.IMPLANT_V5 else (True, True))
        holders = locks._holders(lock_path(st))
        if configuration != p.IMPLANT_V5 and bench != 'searchqa':
            assert len(holders) == 1 and holders[0]['pid'] == os.getpid()
            assert holders[0]['unit'] == 'G/test/' + bench
        else:
            assert holders == []
    assert modes(st) == (True, True) and locks._holders(lock_path(st)) == []


def test_cross_cell_environment_hook_keeps_implant_worker_and_main_v6_lock(tmp_path, monkeypatch):
    st = lock_setting(tmp_path, p.CROSS_V5)

    class Pool:
        def limited(self, cap):
            return self

    st.slots.update({name: Pool() for name in (LIVE, CALL, NATIVE, EPISODE)})
    monkeypatch.setattr(units, 'Worker', lambda **kwargs: kwargs)
    context = units.cell_context(st, tmp_path, SimpleNamespace(model=p.CHAINS['G']))
    assert context.environment is not None
    assert 'diagnostics_configuration' not in context.worker('zebralogic')
    with context.environment('spreadsheetbench', 'G/test/spreadsheetbench'):
        assert modes(st) == (False, False)
    assert modes(st) == (True, True)
    old = replace(st, extra={**st.extra, 'configuration': p.IMPLANT_V5})
    assert units.cell_context(old, tmp_path, SimpleNamespace(model=p.CHAINS['G'])).environment is None
