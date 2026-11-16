"""main-v8 retains the frozen ALF import reservation before candidate adoption."""
import pytest

from skillopt.execskill import engineer, profiles as p, v210_import as imp, v222_cards
from skillopt.execskill.errors import PackageInvalid
from tests.test_execskill_v210_capacity import change, context as original_context, parent


def context(package, configuration):
    ctx = original_context(package, configuration)
    ctx.trajectories, ctx.routing_items = [], []
    return ctx


def test_main_v8_payload_counts_seed_segments_inside_reserved_import_capacity():
    seed = v222_cards.initial_package(evidence='engineering_fixture', step='D/s0')
    capacity = engineer.payload(context(seed, p.MAIN_V8))['package_capacity']
    assert capacity == imp.learning_capacity(seed)
    assert capacity['used_procedures'] == len(seed.procedures) == 11
    assert capacity['package_procedures'] == 21
    assert capacity['remaining_procedures'] == 10
    assert capacity['reserved_import_procedures'] == 3
    assert capacity['reserved_import_source_bytes'] == 5404


@pytest.mark.parametrize('sizes,size', [([200] * 21, 200), ([6000] * 9 + [4000], 597)])
def test_main_v8_individual_candidate_respects_both_import_reservations(sizes, size):
    proposed = change(size)
    with pytest.raises(PackageInvalid, match='reserves 5404 source bytes and 3 procedure slots') as failed:
        engineer._build(proposed, context(parent(sizes), p.MAIN_V8))
    feedback = engineer._size_detail(proposed, failed.value, configuration=p.MAIN_V8)
    assert feedback['caps']['package_source_bytes'] == 58596
    assert feedback['caps']['package_procedures'] == 21


@pytest.mark.parametrize('sizes,size', [([200] * 20, 200), ([6000] * 9 + [4000], 400)])
def test_main_v8_combination_drops_suffix_before_consuming_reserved_import(sizes, size):
    prior = parent(sizes)
    ctx = context(prior, p.MAIN_V8)
    proposals = [change(size, n) for n in (1, 2)]
    for proposed in proposals:
        engineer._build(proposed, ctx)
    trained, kept = engineer._combined_train(ctx, proposals)
    single, single_kept = engineer._combined(prior, proposals, ctx.step, configuration=p.MAIN_V8)
    assert kept == single_kept == proposals[:1]
    assert trained.procedures == single.procedures
    assert imp.check_learning_capacity(trained) is trained
