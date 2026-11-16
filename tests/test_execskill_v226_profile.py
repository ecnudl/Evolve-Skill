"""The v2.26 registration is additive and cannot reopen the frozen main-v9 root."""
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.execskill import manifest, profiles as p, protocol
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


CHILD = 'main-v10'


def test_main_v10_has_a_distinct_root_evidence_namespace_and_inherits_every_table():
    assert p.is_v226(CHILD) and not p.is_v226(p.MAIN_V9)
    assert p.RUN_ROOTS[CHILD] == '/data/execskill-20261109-main-v10'
    assert p.MAIN_V10_MANIFEST == p.RUN_ROOTS[CHILD] + '-manifest.json'
    assert p.CHAIN_NAMESPACES[CHILD] == {'G': 'G-v10', 'D': 'D-v10'}
    assert p.REAL_RUN_EVIDENCE[CHILD] == 'main_v10_real_run'
    assert p.verified(p.record('authored', p.REAL_RUN_EVIDENCE[CHILD], {}))
    differences = set()
    for key, table in vars(p).items():
        if key.isupper() and isinstance(table, dict) and p.MAIN_V9 in table:
            assert CHILD in table, key
            if table[CHILD] != table[p.MAIN_V9]:
                differences.add(key)
            if isinstance(table[p.MAIN_V9], (dict, list)):
                assert table[CHILD] is not table[p.MAIN_V9], key
    assert differences == {'RUN_ROOTS', 'CHAIN_NAMESPACES', 'REAL_RUN_EVIDENCE'}


def test_main_v10_has_all_inherited_dispatch_families_and_exact_budgets():
    for name in ('is_v23', 'is_v28', 'is_v29', 'is_v291', 'is_v292', 'is_v293',
                 'is_v294', 'is_v295', 'is_v210', 'is_v211', 'is_v214', 'is_v218',
                 'is_v221', 'is_v222', 'is_v225'):
        assert getattr(p, name)(CHILD), name
    assert p.active_benches(CHILD) == p.active_benches(p.MAIN_V9) == p.MAIN_V5_ORDER
    assert p.read_arms_of(CHILD) == p.read_arms_of(p.MAIN_V9)
    assert protocol.read_arms_of(CHILD) == p.read_arms_of(CHILD)
    assert protocol.stage_arms_max(CHILD) == 5
    assert protocol.estimate_arms(CHILD) == 6
    assert p.train_rounds(CHILD, 'alfworld') == 0
    assert p.card_writer_settings(CHILD) == p.card_writer_settings(p.MAIN_V9)


def test_main_v10_registered_identity_names_corrected_metrics_and_recovery():
    identity = p.main_v10_identity()
    assert identity['configuration'] == CHILD
    assert identity['cl_metrics']['version'] == 'main-v10-cl-metrics-v1'
    assert identity['cl_metrics']['anchor'] == 'C0'
    assert 're-anchored' in identity['cl_metrics']['changed_only']
    assert identity['recovery_v226']['records'].startswith('step.json candidate_errors')
    parent = deepcopy(p.main_v9_identity())
    for key in ('cl_metrics', 'recovery_v226', 'fixes_v226'):
        identity.pop(key)
    identity['configuration'] = p.MAIN_V9
    assert identity == parent
    assert manifest.registered(CHILD)['sizes']['v214'] == manifest._plain(p.main_v10_identity())


@pytest.mark.parametrize('root', [p.MAIN_V9_ROOT, p.MAIN_V9_ROOT + '/G'])
def test_main_v10_refuses_main_v9_root_before_opening_it(root, monkeypatch):
    monkeypatch.setattr(Path, 'open', lambda *_a, **_k: pytest.fail('No frozen root may be opened'))
    with pytest.raises(ValueError, match='main-v9 root is forbidden'):
        manifest._check_run_root(root, CHILD, 'engineering_fixture')


def test_main_v10_real_root_requires_new_registration():
    manifest._check_run_root(p.MAIN_V10_ROOT, CHILD, 'main_v10_real_run')
    with pytest.raises(ValueError, match='registered new root'):
        manifest._check_run_root('/authored/other', CHILD, 'main_v10_real_run')
    manifest._check_run_root(p.MAIN_V10_ROOT + '-smoke/G', CHILD, 'smoke')
    with pytest.raises(ValueError, match='registered.*root'):
        manifest._check_run_root('/authored/smoke', CHILD, 'smoke')


def test_main_v10_route_b_keeps_thinking_disabled(tmp_path):
    from tests.test_execskill_v225_route_thinking import registered
    value = registered(tmp_path, CHILD)
    manifest.check_clients(value['clients'], configuration=CHILD)
    old = registered(tmp_path, p.MAIN_V9)
    assert value['clients'] == old['clients']
    assert value['clients']['solver']['D']['thinking'] == {'type': 'disabled'}
    assert value['clients']['solver']['D']['backend'] == 'northgate'


def test_main_v10_cli_admission_preserves_default():
    from scripts.run_execskill import parser
    commands = parser()._subparsers._group_actions[0].choices
    for suffix in ('snapshot', 'selftest', 's0', 'manifest', 'structural-smoke', 'smoke-run', 'smoke-summary'):
        arg = next(a for a in commands['v214-' + suffix]._actions if a.dest == 'configuration')
        assert CHILD in arg.choices and arg.default == p.MAIN_V5


def test_real_main_v10_evidence_enters_every_package_cell_and_service_boundary(tmp_path):
    from skillopt.execskill import cells, package, policy, precheck, registry, engines, v225_cards
    from tests.test_execskill_integration_b3 import SHEET_RUNTIME
    evidence = 'main_v10_real_run'
    parent = package.empty(step='G/s0', evidence=evidence)
    card = v225_cards.make_card('searchqa', 'Compare the supplied constraints carefully.', evidence=evidence)
    helper = package.Procedure(id='p-searchqa-1-1', origin='searchqa', description='Compare constraints',
        hooks=(), source='GUIDANCE = "Compare constraints"\n', evidence=evidence,
        policy_version=policy.POLICY_VERSION_V222)
    child = package.with_(parent, step='G/s1', add=[card, helper])
    package.save(tmp_path, child)
    assert package.load(tmp_path/'packages'/(child.sha256+'.json')) == child
    assert all(package.Procedure.from_json(row.to_json()) == row for row in child.procedures)
    context = cells.Context(attempt=tmp_path/'attempt', endpoint=None, runtime={}, cards={},
        native=None, episodes=None, worker=None, evidence=evidence, configuration=CHILD)
    assert context.evidence == evidence
    assert registry.Registry(tmp_path/'history', evidence=evidence).evidence == evidence
    assert precheck.report('ok', evidence=evidence)['evidence'] == evidence
    from contextlib import nullcontext
    from types import SimpleNamespace
    engine = engines.sheet_engines(SHEET_RUNTIME, native=SimpleNamespace(hold=nullcontext), evidence=evidence)
    assert engine.qualify.keywords['evidence'] == evidence
