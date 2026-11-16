"""Authored practice rows, fake sandbox hooks and scored cells; no services/data."""
from contextlib import contextmanager
from dataclasses import replace
from fractions import Fraction

import pytest

from skillopt.execskill import policy, profiles as p, v222_gate as gate
from skillopt.execskill.package import empty, with_
from skillopt.validator_pilot.api import digest
from tests.execskill_fakes_env import procedure, FakeSandbox


def pools():
    return {bench: [{'task_id': bench + '-%03d' % i, 'benchmark': bench,
        'partition': 'practice', 'public': {'question': 'Authored question %d?' % i,
        'context': ['An authored statement.']}, 'private': {'answer': 'authored'}} for i in range(100)]
        for bench in gate.BENCHES}


def packages():
    parent = empty(step='G/s1-searchqa', evidence='engineering_fixture')
    proc = procedure('fx-v222-cross', ('applies', 'before_call'), origin='zebralogic',
                     policy_version=policy.POLICY_VERSION_V29)
    return parent, with_(parent, step=parent.step, add=[proc])


def simple_inspector(bench, parent, candidate, items):
    def signature(package):
        return {'request_sha256': digest([proc.sha256 for proc in package.for_bench(bench)]),
                'post_call': [], 'faults': []}
    pairs = {row['task_id']: {'S': signature(parent), "S'": signature(candidate)} for row in items}
    fired = [key for key, pair in pairs.items() if not gate.v221_rule.same_request(pair['S'], pair["S'"])]
    return {'bench': bench, 'items': len(items), 'slice_ids': list(pairs), 'fired': len(fired),
            'fired_items': fired, 'faults': [], 'identity_proven': not fired, 'signatures': pairs,
            'parent_sha256': parent.sha256, 'candidate_sha256': candidate.sha256}


def paired(items, *, harmful=False):
    return {(arm, row['task_id']): [{'judge': {'v2': {'token':
            'pass' if harmful and arm == 'S' else 'fail'}}}]
            for row in items for arm in ('S', "S'")}


def test_harm_slices_are_seeded_fixed_and_exclude_protected_items():
    rows = pools()
    first = gate.harm_slices(rows, excluded={'officeqa': [row['task_id'] for row in rows['officeqa'][:10]]})
    second = gate.harm_slices({bench: list(reversed(items)) for bench, items in rows.items()},
        excluded={'officeqa': [row['task_id'] for row in rows['officeqa'][:10]]})
    assert first == second
    assert {bench: len(items) for bench, items in first.items()} == gate.HARM_ITEMS
    assert not {row['task_id'] for row in first['officeqa']} & {row['task_id'] for row in rows['officeqa'][:10]}
    assert gate.harm_slices(rows, seed=1) != gate.harm_slices(rows, seed=2)
    record = gate.registration(first)
    assert record['sha256'] == digest({key: value for key, value in record.items() if key != 'sha256'})
    assert 'Authored question' not in str(record)


@pytest.mark.parametrize('bad', ['test', 'sealed', 'holdout', 'reserve'])
def test_harm_slices_refuse_nonpractice_partitions(bad):
    rows = pools(); rows['officeqa'][0]['partition'] = bad
    with pytest.raises(ValueError, match='practice records'):
        gate.harm_slices(rows)


def test_harm_slice_shortage_and_old_configuration_fail_closed():
    rows = pools(); rows['officeqa'] = rows['officeqa'][:17]
    with pytest.raises(ValueError, match='minimum available 18'):
        gate.harm_slices(rows)
    with pytest.raises(ValueError, match='only to main-v8'):
        gate.harm_slices(pools(), configuration=p.MAIN_V7)


@pytest.mark.parametrize('fired,fixed,broken,whole,passed', [
    (0, 0, 0, None, True), (10, 0, 0, None, True), (10, 5, 5, None, True),
    (10, 4, 5, None, False), (10, 6, 4, Fraction(-1, 100), True),
    (10, 6, 4, Fraction(-11, 1000), False)])
def test_cross_gate_requires_nonnegative_net_and_inclusive_whole_floor(fired, fixed, broken, whole, passed):
    assert gate.counts(fired=fired, fixed=fixed, broken=broken, items=60,
                       whole_slice=whole)['passed'] is passed


def test_zero_firing_proves_identity_without_a_solver():
    parent, _ = packages(); invoked = []
    final, record = gate.check(home='searchqa', parent=parent, candidate=parent,
        slices=gate.harm_slices(pools()), inspector=simple_inspector,
        run_pairs=lambda *args: invoked.append(args), phase='confirmation')
    assert final == parent and record['passed'] and not invoked
    assert set(record['benches']) == set(gate.BENCHES) - {'searchqa'}
    assert all(row['fired'] == 0 and row['identity_proven'] for row in record['benches'].values())
    assert record['paired_item_calls'] == 0


def test_only_fired_items_receive_one_pair_and_harm_narrows_then_rechecks_every_bench():
    parent, candidate = packages(); invoked, inspected = [], []
    def inspect(bench, before, after, items):
        inspected.append((bench, after.sha256))
        return simple_inspector(bench, before, after, items)
    def run(bench, before, after, items):
        invoked.append((bench, [row['task_id'] for row in items]))
        return paired(items, harmful=bench == 'officeqa')
    final, record = gate.check(home='searchqa', parent=parent, candidate=candidate,
        slices=gate.harm_slices(pools()), inspector=inspect, run_pairs=run, phase='confirmation')
    assert record['passed'] and final is not None and final.sha256 != candidate.sha256
    assert final.for_bench('officeqa') == () and final.for_bench('searchqa') == candidate.for_bench('searchqa')
    assert len(invoked) == 4 and len(inspected) == 8
    assert sum(2 * len(ids) for _, ids in invoked) == record['paired_item_calls'] == 400
    assert record['narrowing']['additional_model_calls'] == 0
    assert record['narrowing']['rechecked']['officeqa']['identity_proven']
    assert set(record['narrowing']['rechecked']) == set(gate.BENCHES) - {'searchqa'}


def test_disabled_gate_is_detected_by_harmful_unnarrowable_deletion():
    base, parent = packages()
    candidate = with_(parent, step=parent.step, remove=list(parent.order))
    final, record = gate.check(home='searchqa', parent=parent, candidate=candidate,
        slices=gate.harm_slices(pools()), inspector=simple_inspector,
        run_pairs=lambda bench, before, after, items: paired(items, harmful=True), phase='acceptance')
    assert final is None and not record['passed'] and record['decision'] == 'reject'
    assert record['narrowing'] is None
    assert all(row['net'] < 0 for row in record['benches'].values())


def test_narrowing_residual_changes_cannot_trigger_more_pairs_or_claim_identity():
    parent, candidate = packages(); called = []
    def unchanged_narrower(parent, candidate, **kwargs):
        return candidate
    def run(bench, before, after, items):
        called.append(bench); return paired(items, harmful=True)
    final, record = gate.check(home='searchqa', parent=parent, candidate=candidate,
        slices=gate.harm_slices(pools()), inspector=simple_inspector, run_pairs=run,
        phase='confirmation', narrower=unchanged_narrower)
    assert final is None and not record['passed'] and len(called) == 4
    assert record['narrowing']['additional_model_calls'] == 0


def test_fired_cell_contract_refuses_missing_extra_repeated_and_unscored_runs():
    parent, candidate = packages(); items = pools()['officeqa'][:2]
    inspection = simple_inspector('officeqa', parent, candidate, items)
    good = paired(items)
    invalid = [dict(list(good.items())[:-1]), {**good, ('S', 'extra'): ['fail']},
               {key: rows * 2 for key, rows in good.items()},
               {key: ['unknown'] for key in good}]
    for rows in invalid:
        with pytest.raises(ValueError):
            gate.measured(inspection, rows)


def test_router_uses_delivered_request_identity_not_enabled_predicate():
    parent, candidate = packages(); proc = candidate.procedures[0]
    items = pools()['searchqa'][:2]
    def inspect(fields):
        hooks = {proc.id: {'applies': lambda view: True, 'before_call': lambda *args: fields}}
        @contextmanager
        def workers(package, key):
            worker = FakeSandbox(hooks).start(package, kind='cell')
            try: yield worker
            finally: worker.close()
        return gate.inspect('searchqa', parent, candidate, items, workers)
    silent = inspect({})
    assert silent['fired'] == 0 and silent['identity_proven']
    delivered = inspect({'facts': ['An authored statement.']})
    assert delivered['fired'] == 2 and not delivered['identity_proven']


def test_sheet_callback_without_replay_is_conservatively_measured():
    parent = empty(step='G/s1-searchqa', evidence='engineering_fixture')
    proc = procedure('fx-v222-sheet', ('applies', 'sheet_feedback'), origin='spreadsheetbench',
                     requests_second_call=True, policy_version=policy.POLICY_VERSION_V29)
    candidate = with_(parent, step=parent.step, add=[proc])
    items = pools()['spreadsheetbench'][:1]
    hooks = {proc.id: {'applies': lambda view: True, 'sheet_feedback': lambda *args: {}}}
    @contextmanager
    def workers(package, key):
        worker = FakeSandbox(hooks).start(package, kind='cell')
        try: yield worker
        finally: worker.close()
    key = items[0]['task_id']
    found = gate.inspect('spreadsheetbench', parent, candidate, items, workers,
        views={key: {'instruction': 'Authored instruction.', 'workbook_preview': {}}})
    assert not found['request_changed'] and found['fired_items'] == [key]
    assert found['potential_post_call'][key] == 'changed_sheet_callback_without_practice_replay'


def test_narrowing_cannot_remove_home_or_widen_a_package():
    parent, candidate = packages()
    with pytest.raises(ValueError, match='off-home'):
        gate.narrow_additions(parent, candidate, home='searchqa', benches=['searchqa'])
    narrowed = gate.narrow_additions(parent, candidate, home='searchqa', benches=['officeqa'])
    assert set(candidate.narrowed.get(candidate.order[0], ())) <= set(narrowed.narrowed[candidate.order[0]])


def test_alfworld_frozen_router_proves_idle_identity_and_conservatively_counts_dynamic_hooks():
    parent = empty(step='G/s1-searchqa', evidence='engineering_fixture')
    proc = procedure('fx-v222-alf', ('applies', 'alf_before_step'), origin='alfworld',
                     policy_version=policy.POLICY_VERSION_V29)
    candidate = with_(parent, step=parent.step, add=[proc])
    items = pools()['alfworld'][:1]; key = items[0]['task_id']
    view = {'initial_observation': 'An authored room.', 'admissible_commands_at_reset': ['look'],
            'task_text': 'An authored objective.'}
    def inspect(enabled):
        hooks = {proc.id: {'applies': lambda view: enabled,
                          'alf_before_step': lambda *args: {'fields': {}, 'discourage': []}}}
        @contextmanager
        def workers(package, key):
            worker = FakeSandbox(hooks).start(package, kind='cell')
            try: yield worker
            finally: worker.close()
        return gate.inspect('alfworld', parent, candidate, items, workers, views={key: view})
    idle = inspect(False)
    assert idle['fired'] == 0 and idle['identity_proven']
    active = inspect(True)
    assert active['fired_items'] == [key]
    assert active['potential_post_call'][key] == 'changed_dynamic_episode_hook'


def test_only_sparse_fired_subset_is_measured_and_untouched_denominator_is_sixty():
    parent, candidate = packages(); called = []
    def inspect(bench, before, after, items):
        found = simple_inspector(bench, before, before, items)
        found['candidate_sha256'] = after.sha256
        if bench == 'officeqa':
            found['fired_items'] = found['slice_ids'][:3]
            found.update(fired=3, identity_proven=False)
            for key in found['fired_items']:
                found['signatures'][key]["S'"] = {'request_sha256': digest(key), 'post_call': [], 'faults': []}
        return found
    def run(bench, before, after, items):
        called.append((bench, len(items)))
        return paired(items)
    final, record = gate.check(home='searchqa', parent=parent, candidate=candidate,
        slices=gate.harm_slices(pools()), inspector=inspect, run_pairs=run, phase='acceptance')
    assert final == candidate and record['passed'] and called == [('officeqa', 3)]
    assert record['paired_item_calls'] == 6 and record['benches']['officeqa']['items'] == 60


def test_routing_fault_is_not_zero_firing_identity_proof():
    parent, _ = packages()
    def faulty(bench, before, after, items):
        found = simple_inspector(bench, before, after, items)
        found.update(faults=[{'kind': 'predicate_fault'}], identity_proven=False)
        return found
    final, record = gate.check(home='searchqa', parent=parent, candidate=parent,
        slices=gate.harm_slices(pools()), inspector=faulty,
        run_pairs=lambda *args: pytest.fail('No model run fixes a routing fault'), phase='confirmation')
    assert final is None and not record['passed']
    assert all(row['reason'] == 'routing_fault' for row in record['benches'].values())


def test_gate_never_catches_a_budget_stop_from_its_charged_runner():
    from skillopt.execskill.errors import BudgetStop
    parent, candidate = packages()
    def stopped(*args):
        raise BudgetStop('authored budget stop')
    with pytest.raises(BudgetStop, match='authored budget stop'):
        gate.check(home='searchqa', parent=parent, candidate=candidate, slices=gate.harm_slices(pools()),
                   inspector=simple_inspector, run_pairs=stopped, phase='confirmation')
