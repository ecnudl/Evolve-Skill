"""Proposal exclusions, replay-test scope and built C6 scope agree in main-v10."""
from dataclasses import replace

import pytest

from skillopt.execskill import engineer as e, engineer_v28, profiles as p, v222_cards
from skillopt.execskill.package import procedure_benches
from tests.test_execskill_v24_engineer import context, change, claim


def context_after_zebra(bench, configuration='main-v10'):
    ctx, _ = context()
    ctx = replace(ctx, bench=bench, k=4, step='D/s4-' + bench,
        configuration=configuration, card=v222_cards.format_text(bench),
        label='D/s4-' + bench + '/engineer-r1', routing_items=[], routing_shared_worker=False)
    return ctx


@pytest.mark.parametrize('bench', ['searchqa', 'officeqa', 'spreadsheetbench'])
@pytest.mark.parametrize('excluded', [[], ['zebralogic']])
def test_prepare_uses_built_procedure_scope_for_zebra_replays(bench, excluded):
    ctx = context_after_zebra(bench)
    proposed = change(ctx, tests=[claim(ctx)])
    proposed.entry['excluded_benches'] = list(excluded)
    dropped = engineer_v28.prepare(proposed, ctx)
    assert proposed.entry['excluded_benches'] == excluded
    before = e._scope_entries(ctx, set(excluded))
    candidate = e._build(proposed, ctx)
    assert procedure_benches(proposed.procedure) == p.SUPPORTED_BENCHES
    assert before == e._scope(ctx, candidate, proposed.procedure)
    if excluded:
        assert dropped and dropped[0]['reason'] == 'trajectory_not_in_scope'
        assert not before and not proposed.procedure.replay_tests
    else:
        assert not dropped and len(before) == 1
        assert proposed.procedure.replay_tests[0]['trajectory'] == ctx.trajectories[0]['cell']


@pytest.mark.parametrize('bench', ['searchqa', 'spreadsheetbench'])
def test_reference_resolution_uses_policy_scope_before_procedure_hash(bench):
    ctx = context_after_zebra(bench)
    test = {**claim(ctx), 'trajectory': ctx.trajectories[0]['task_id']}
    proposed = change(ctx, tests=[test])
    proposed.entry['excluded_benches'] = []
    e._resolve_change(proposed, ctx)
    assert proposed.entry['replay_tests'][0]['trajectory'] == ctx.trajectories[0]['cell']
    assert proposed.trajectory_resolution[0]['rule'] == 'task_id'
    candidate = e._build(proposed, ctx)
    assert proposed.procedure.replay_tests[0]['trajectory'] in e._scope(ctx, candidate, proposed.procedure)


def test_main_v9_exclusion_normalization_and_prebuild_scope_stay_frozen():
    ctx = context_after_zebra('spreadsheetbench', p.MAIN_V9)
    proposed = change(ctx, tests=[claim(ctx)])
    proposed.entry['excluded_benches'] = ['zebralogic']
    dropped = engineer_v28.prepare(proposed, ctx)
    assert proposed.entry['excluded_benches'] == []
    assert dropped and dropped[0]['reason'] == 'trajectory_not_in_scope'
    assert e._scope_entries(ctx, set()) == {}
