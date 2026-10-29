"""Zero-send confirmation invariant controls beside the measured exercise unit."""
from dataclasses import replace
from copy import deepcopy

from skillopt.continual_eval.core import require
from skillopt.validator_pilot.api import digest
from skillopt.execskill import step


def confirmation_controls(st, cut, candidate, completed):
    """Resume the completed pair, then inject a reused slice and require pre-dispatch refusal."""
    before = st.setting.budget.snapshot()
    resumed = step._confirm_eval(st, cut, 1, st.parent, candidate, exercise=True)
    after_resume = st.setting.budget.snapshot()
    same = resumed == completed and before == after_resume
    reused = deepcopy(cut)
    reused['confirm-r1'] = deepcopy(cut['confirm'])
    reused['confirm-r2'] = deepcopy(cut['confirm'])
    # Even a future regression of the early disjointness check cannot dispatch
    # a model call from the deliberate negative control.
    trial = replace(st)
    def forbidden(*args, **kwargs):
        raise AssertionError('Authored confirmation control forbids model dispatch')
    trial.solver = forbidden
    reason = None
    try:
        step._confirm_eval(trial, reused, 2, st.parent, candidate, exercise=True)
    except ValueError as error:
        reason = str(error)
    after = st.setting.budget.snapshot()
    refused = reason == 'Confirmation rounds are pairwise disjoint'
    return {'passed': same and refused and before == after,
        'evidence': 'engineering_fixture', 'model_calls': 0, 'external_calls': 0,
        'benchmark_effect_evidence': False, 'excluded_from_cost_projection': True,
        'same_round_resume': {'same_receipt': resumed == completed, 'unchanged_ledger': before == after_resume,
            'completed_result_sha256': digest(completed)},
        'cross_round_refusal': {'refused_before_dispatch': refused, 'reason': reason,
            'injection': 'Two round keys deliberately contain the same authored slice',
            'slice_sha256': digest(cut['confirm'])},
        'ledger_before_sha256': digest(before), 'ledger_after_sha256': digest(after)}
