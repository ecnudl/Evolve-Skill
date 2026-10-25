"""Registered positive-control profile, scopes and caps; synthetic, no external work."""
from fractions import Fraction
from types import SimpleNamespace

import pytest

from tests.execskill_zpc_fakes import tmp_path

from skillopt.execskill import budgets, notes, policy, profiles as p, protocol as old
from skillopt.execskill import examiner, generators, package, replay, units
from skillopt.execskill.corpus import Corpus
from skillopt.coevo5.leakage import findings
from tests.test_execskill_zpc_adapter import row
from skillopt.execskill import zebralogic as z


@pytest.mark.parametrize("name", [
    "LEARNING", "FIX_ECHO", "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES",
    "ENGINEER_MAX_TOKENS", "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING", "ENGINEER_RECORDS",
    "IDENTICAL_REQUEST_REUSE", "POLICY_VERSIONS", "CODE_EXTRACTION", "MULTIPLE_PYTHON_BLOCKS",
])
def test_feature_family_inherits_every_main_v23_feature(name):
    assert p.is_v23(p.ZEBRA_PC_V1) and p.is_v23(p.MAIN_V2_3)
    assert getattr(p, name)[p.ZEBRA_PC_V1] == getattr(old, name)[old.MAIN_V2_3]
    assert {key: value for key, value in getattr(p, name).items() if key != p.ZEBRA_PC_V1} == getattr(old, name)


def test_explicit_active_read_and_historical_registration_rosters():
    assert p.active_benches(p.ZEBRA_PC_V1) == p.read_benches(p.ZEBRA_PC_V1) == (z.BENCH,)
    assert p.CONFIGURATIONS[p.ZEBRA_PC_V1]["order"] == (z.BENCH,)
    assert old.BENCHES == ("searchqa", "officeqa", "livemath", "spreadsheetbench", "alfworld")
    assert p.ZEBRA_PC_V1 not in old.CONFIGURATIONS
    assert p.stage_arms_max(p.ZEBRA_PC_V1) == 0 and p.read_arms_of(p.ZEBRA_PC_V1) == old.TEST_ARMS
    setting = SimpleNamespace(extra={"configuration": p.ZEBRA_PC_V1})
    assert [p.namespace_of(setting, chain) for chain in ("G", "D")] == ["G-zpc1", "D-zpc1"]
    assert p.RUN_ROOTS[p.ZEBRA_PC_V1] == "/data/execskill-20261025-zebra-pc-v1"
    assert p.REAL_RUN_EVIDENCE[p.ZEBRA_PC_V1] == "zebra_pc_v1_real_run"
    for config in old.CONFIGURATIONS:
        assert p.active_benches(config) == p.read_benches(config) == old.BENCHES
        assert p.CONFIGURATIONS[config] == old.CONFIGURATIONS[config]
    for fn in (p.first_call_bench, p.active_benches, p.read_benches, p.is_v23):
        with pytest.raises(ValueError):
            fn("unregistered")


def test_registered_slices_gates_and_explicit_selection_only_capabilities():
    assert p.SLICES[z.BENCH] == {"run": (60, 1), "accept": (100, 1), "blocks": 1}
    assert p.G_ACC[z.BENCH] == 0 and z.BENCH not in p.GENERATING
    assert generators.mode(z.BENCH) == "selection_only" and generators.FAMILIES[z.BENCH] == {}
    with pytest.raises(ValueError):
        examiner._generating(z.BENCH)
    assert p.MDE_POINTS[z.BENCH] == 10.0
    assert p.ACCEPT_RULES[p.ZEBRA_PC_V1]["gain_points"] == 5
    assert z.BENCH not in p.ACCEPT_RULES[p.ZEBRA_PC_V1]["significance_benches"]
    assert not p.TRAIN_SIGN[p.ZEBRA_PC_V1]


def test_client_bounds_and_exact_three_times_budget_arithmetic():
    assert p.solver_tokens(p.CHAINS["G"], z.BENCH) == p.ledger_bound(p.CHAINS["G"], z.BENCH) == 65536
    assert p.read_timeout(p.CHAINS["G"], z.BENCH) == 2400
    assert p.solver_tokens(p.CHAINS["D"], z.BENCH) == 16384
    assert p.read_timeout(p.CHAINS["D"], z.BENCH) == 600
    assert p.ledger_bound(p.CHAINS["D"], z.BENCH, branch="E") == 32768
    assert p.ledger_bound(p.CHAINS["D"], z.BENCH, branch="N", longest=6440) == 65536
    for kind, cells in p.ZEBRA_SCHEDULE[z.BENCH].items():
        need = sum(5300 * (card + Fraction(8, 5) * proc) for card, proc in cells.values()) + 16 * 520192
        assert p.ZEBRA_STEP_CAPS[z.BENCH][kind] >= 3 * need
        assert p.ZEBRA_STEP_CAPS[z.BENCH][kind] < 3 * need + 100000
    assert p.ZEBRA_SOLVER_CAP == 235000000 and p.ZEBRA_READ_CAP == 54000000
    caps = budgets.chain_caps("D", p.ZEBRA_PC_V1)
    assert caps["D:solver"] == p.ZEBRA_SOLVER_CAP
    assert all(not any(b in key for b in old.BENCHES) for key in caps)
    assert p.read_estimate_terms({z.BENCH: {"card": 5300}}, 1, p.ZEBRA_PC_V1) == {z.BENCH: 7844000}
    with pytest.raises(ValueError):
        p.read_estimate_terms({"searchqa": {"card": 5300}}, 1, p.ZEBRA_PC_V1)


SOURCE = "def applies(view):\n    return True\ndef before_call(view, state):\n    return {'table': [['1', 'amber']]}\n"


def procedure(origin, excluded=()):
    return package.Procedure(id="p-" + origin + "-1-1", origin=origin, evidence="engineering_fixture",
                             description="Solves a synthetic constraint.", hooks=("applies", "before_call"),
                             source=SOURCE, header="", max_note_chars=4000, requests_second_call=False,
                             state_bytes=0, excluded_benches=excluded, policy_version=policy.POLICY_VERSION_V23)


def test_old_procedures_do_not_silently_acquire_new_scope_and_grid_hooks_are_explicit(tmp_path):
    historical = procedure("officeqa")
    old_package = package.Package((historical,), "s0", "engineering_fixture")
    assert old_package.for_bench(z.BENCH) == ()
    assert package.procedure_benches(historical) == old.BENCHES
    grid = procedure(z.BENCH, old.BENCHES)
    grid_package = package.Package((grid,), "s1", "engineering_fixture")
    assert grid_package.for_bench(z.BENCH) == (grid,)
    assert all(grid_package.for_bench(b) == () for b in old.BENCHES)
    assert package.Procedure.from_json(grid.to_json()) == grid
    assert policy.check(SOURCE, bench=z.BENCH, version=policy.POLICY_VERSION_V23) == []
    assert units.unit_path(tmp_path, 1, z.BENCH, "run").name == "run"


def test_grid_note_screen_has_no_exemptions_and_historical_hash_is_unchanged():
    assert notes.lexicon_sha256() == "a007ee266909803d13b10bde9030bd20ada6d676060b4b71633d5a799793ff4b"
    for term in old.LEXICON_TERMS:
        assert term in notes.lexicon_hits(term, bench=z.BENCH)
    text, skipped = notes.assemble([("x", "a" * 4000, 4000), ("y", "b", 4000)], bench=z.BENCH)
    assert len(text) == 4000 and skipped[0]["reason"] == "over_total_cap"
    assert z.BENCH in replay.SUPPORTED_MUTATIONS["strip_digits"]
    assert replay.MUTATIONS == old.MUTATIONS


def test_grid_corpus_indexes_public_surfaces_cells_and_assignments():
    item = z.normalize(row())
    corpus = Corpus(z.BENCH, [item])
    assert corpus.benchmark == z.BENCH and corpus.size == 1
    assert findings("value 1 1", corpus)["answer_text"]
    assert tuple("house 1 trait 1 value 1 1".split()) in corpus.phrases


def test_profile_budget_stop_is_persisted_and_explicit_cap_raise_allows_resume(tmp_path):
    from skillopt.coevo5.budget import Budget
    from skillopt.execskill.errors import BudgetStop
    ledger = Budget(tmp_path / "ledger", sleep=lambda _: None)
    caps = budgets.chain_caps("D", p.ZEBRA_PC_V1)
    scopes = budgets.solver_scopes("D", z.BENCH, 1, "accept")
    # A deliberately reduced fixture cap, never a production experiment or cap mutation.
    ledger.declare({**caps, scopes[-1]: 1})
    with pytest.raises(BudgetStop):
        ledger.reserve(scopes, 2, label="synthetic-control", generation=ledger.generation())
    assert ledger.snapshot()[scopes[-1]]["settled"] == 0
    restarted = Budget(tmp_path / "ledger", sleep=lambda _: None)
    restarted.raise_cap(scopes[-1], caps[scopes[-1]], deviation="synthetic fixture resume")
    reservation = restarted.reserve(scopes, 2, label="synthetic-control", generation=restarted.generation())
    restarted.settle(reservation, 2, detail={"fixture": True})
    assert restarted.snapshot()[scopes[-1]]["settled"] == 2
    assert restarted.snapshot()["D:solver"]["settled"] == 2
