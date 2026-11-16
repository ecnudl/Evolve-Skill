"""Reproduce each defect with exact base functions and the current v10 registry.

Run from the checkout, one fresh interpreter per case::

    TMPDIR="$PWD/.runtime-tmp" PATH=<python-bin>:$PATH \
      PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='-p no:cacheprovider' \
      python3 docs/handoff/v226-20261109/base_probe.py F1

Expected base exits are 1 (assertion failures); ``--fixed`` runs the same checks
without restoring functions and must exit 0. No checkout/source file is changed:
``git show`` reads e589b5b and AST compilation replaces only named functions in
memory. Registry/configuration admissions stay current, so unknown main-v10 is
never the intended failure. F4 deliberately delegates to the byte-identical
historical metric implementation with its registered main-v9 configuration.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

import pytest
from tests.execskill_v293_fakes import tmp_path  # noqa: F401

BASE = 'e589b5b'
TEST = 'tests/test_execskill_v226_'
CASES = {
    'K1': ([('step', '_previous')], [
        TEST + 'diagnostics.py::test_previous_executed_acceptance_shows_counts_only']),
    'F1': ([('step', '_Step.unit')], [
        TEST + 'diagnostics.py::test_engineer_replay_in_sheet_unit_matches_zebra_value_hash_and_faults']),
    'F2': ([('step', '_pair_signatures'), ('acceptance', 'prepare')], [
        TEST + 'identity.py::test_real_pair_signatures_card_full_touch_equals_solver_request_on_every_bench',
        TEST + 'identity.py::test_acceptance_seals_composed_card_request_as_sent_by_solver']),
    'F3': ([('v222_gate', 'inspect'), ('v222_gate', 'check')], [
        TEST + 'gate.py::test_inherited_zebra_fault_does_not_reject_sheet_procedure_or_card',
        TEST + 'gate.py::test_flaky_inherited_fault_with_a_changed_request_is_measured',
        TEST + 'gate.py::test_narrowing_recheck_ignores_identical_inherited_faults']),
    'F4': ([], [TEST + 'metrics.py::test_c0_reanchoring_removes_false_harm_and_exposes_masked_harm']),
    'F5': ([('engineer_v28', 'prepare'), ('engineer', '_scope_entries'),
            ('engineer', '_resolve_change')], [
        TEST + 'scope.py::test_prepare_uses_built_procedure_scope_for_zebra_replays',
        TEST + 'scope.py::test_reference_resolution_uses_policy_scope_before_procedure_hash']),
    'F6': ([('step', '_confirm_eval'), ('v221_split', 'evaluate'), ('v221_split', '_resume_cells')], [
        str(Path(__file__).relative_to(ROOT)) + '::test_probe_confirmation_resume',
        str(Path(__file__).relative_to(ROOT)) + '::test_probe_split_resume']),
    'F7': ([('v225_read', 'evaluate_unit')], [
        TEST + 'blocks.py::test_officeqa_stage_read_halves_are_stable_only_in_main_v10']),
    'F8': ([('sandbox.client', 'Worker.call'), ('sandbox.client', 'Worker.call_diagnostics')], [
        TEST + 'worker_recovery.py::test_first_diagnostics_exchange_loss_retries_once_inside_call_slot']),
}


def restore(module_name, qualified_name):
    module = importlib.import_module('skillopt.execskill.' + module_name)
    path = 'skillopt/execskill/' + module_name.replace('.', '/') + '.py'
    source = subprocess.check_output(['git', 'show', BASE + ':' + path], cwd=ROOT, text=True)
    node, owner = ast.parse(source, filename=BASE + ':' + path), module
    names = qualified_name.split('.')
    for index, name in enumerate(names):
        node = next(child for child in node.body if isinstance(child, (ast.ClassDef, ast.FunctionDef))
                    and child.name == name)
        if index < len(names) - 1:
            owner = getattr(owner, name)
    assert isinstance(node, ast.FunctionDef), qualified_name
    # Keep the real module globals: patched functions must resolve the same
    # registered profiles, workers and dependent production functions as before.
    previous = module.__dict__.get(node.name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), BASE + ':' + path, 'exec'), module.__dict__)
    function = module.__dict__[node.name]
    if owner is not module:
        if previous is None:
            del module.__dict__[node.name]
        else:
            module.__dict__[node.name] = previous
        setattr(owner, node.name, function)
    print('RESTORED', path + ':' + qualified_name, flush=True)


def test_probe_confirmation_resume(tmp_path, monkeypatch):
    """Accept either envelope; fail only if changing hook faults prevents retry."""
    from skillopt.continual_eval.core import read_json
    from skillopt.execskill import step
    from skillopt.execskill.cells import Pause
    from tests.test_execskill_v226_resume import setup, redo, assert_faults_preserved
    from tests.test_execskill_v226_card_units import zebra_pool
    st, parent, candidate, state, _ = setup(tmp_path, monkeypatch)
    cut = {'confirm': zebra_pool(2)}
    with pytest.raises(Pause):
        step._confirm_eval(st, cut, 1, parent, candidate, exercise=True)
    path = st.root / 'confirm-selection-r1.json'
    sealed = read_json(path)
    assert_faults_preserved(sealed['request_signatures'])
    redo(st, 'confirm-r1')
    state['fault'] = False
    result = step._confirm_eval(st, cut, 1, parent, candidate, exercise=True)
    assert result['request_signatures'] == sealed['request_signatures']
    assert result['request_identities'] == sealed['request_identities']
    assert read_json(path) == sealed


@pytest.mark.parametrize('confirmation', [False, True])
def test_probe_split_resume(tmp_path, monkeypatch, confirmation):
    from skillopt.continual_eval.core import read_json
    from skillopt.execskill import v221_split
    from skillopt.execskill.cells import Pause
    from tests.test_execskill_v226_resume import setup, redo, assert_faults_preserved
    from tests.test_execskill_v226_card_units import zebra_pool
    st, parent, candidate, state, _ = setup(tmp_path, monkeypatch)
    rows = zebra_pool(2)
    cut, source = {'confirm': rows, 'run': rows}, {'slice_ids': [row['task_id'] for row in rows]}
    unit = ('confirm' if confirmation else 'train') + '-r1-split-p1'
    def run():
        return v221_split.evaluate(st, cut, 1, 1, parent, candidate, candidate, source, None,
                                   confirmation=confirmation)
    with pytest.raises(Pause):
        run()
    path = st.root / unit / 'split-binding.json'
    sealed = read_json(path)
    assert_faults_preserved(sealed['request_signatures'])
    redo(st, unit)
    state['fault'] = False
    assert run()['request_signatures'] == sealed['request_signatures']
    assert read_json(path) == sealed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', choices=CASES)
    parser.add_argument('--fixed', action='store_true', help='Run current functions as a positive control')
    args = parser.parse_args()
    os.chdir(ROOT)
    os.environ.setdefault('TMPDIR', str(ROOT / '.runtime-tmp'))
    Path(os.environ['TMPDIR']).mkdir(parents=True, exist_ok=True)
    replacements, tests = CASES[args.case]
    if not args.fixed:
        for module, function in replacements:
            restore(module, function)
        if args.case == 'F4':
            from skillopt.execskill import profiles, v225_metrics, v226_metrics
            v226_metrics.compute = lambda aggregate, chain: v225_metrics.compute(
                {**aggregate, 'configuration': profiles.MAIN_V9}, chain)
            print('USING unchanged v225_metrics.compute(configuration=main-v9)', flush=True)
    print('CASE', args.case, 'fixed' if args.fixed else 'base functions', flush=True)
    return pytest.main(['-q', '-p', 'no:cacheprovider', *tests])


if __name__ == '__main__':
    raise SystemExit(main())
