"""Offline real evaluation-entry checks: confirmation before panels and no baseline training pools."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from skillopt.coevo5.budget import Budget
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import budgets, chain, evaluation, instruction_start, profiles as p, slots, units
from skillopt.execskill.package import empty
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_evaluation import (ITEMS, READ_TEXTS, ReadPanel, Solver, consent_value,
                                            panel as office_panel, pool_pins, s0_canaries)


class FixtureSolver(Solver):
    """Local replies behind the real endpoint, including chain.first_call's confirmation receipt."""

    def __init__(self, chain_id):
        super().__init__()
        self.model, self.max_tokens = p.CHAINS[chain_id], 100
        self.chain_id, self.confirm_calls = chain_id, 0

    def call(self, system, user):
        if user == p.FIRST_CALL_USER:
            self.confirm_calls += 1
            echo = chain._confirm_of('unused', self.chain_id, 'B' if self.chain_id == 'D' else None)[3]
            return {'ok': True, 'response': 'ready', 'returned_model': sorted(echo)[0],
                    'finish_reason': 'stop', 'error_type': None, 'reasoning_tokens': 0, 'reasoning_chars': 0,
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
                    'attempts': [{'status': 200}]}
        return super().call(system, user)


def entry(tmp_path, monkeypatch, configuration, chain_id):
    root = tmp_path / 'run'
    model = FixtureSolver(chain_id)
    st = units.Setting(run='v210-entry-fixture', root=root, shared=root / 'shared', pools={},
        cards={b: pin['text'] for b, pin in instruction_start.pins().items()}, runtime=deepcopy(RUNTIME),
        clients=lambda model_name, bench: model, budget=Budget(budgets.ledger_root(root, chain_id)),
        slots=slots.pools(tmp_path / 'slots'), sandbox={}, evidence='engineering_fixture', branch='N',
        longest=100, workers=2, cooldown=0,
        extra={'configuration': configuration, 'route': 'B' if chain_id == 'D' else None})
    st.budget.declare({**budgets.chain_caps(chain_id, configuration), **budgets.first_call_caps(chain_id)})
    write_json(st.shared / 'consent.json', consent_value(multi_arm_arms=list(p.read_arms_of(configuration))))
    package = empty(step=chain_id + '/s0', evidence=st.evidence)
    spec = tmp_path / 'spec.json'
    write_json(spec, {'chain': chain_id, 'bench': 'officeqa', 'package_sha256': package.sha256,
                      'unit_root': str(root / chain_id / 'test/officeqa')})
    missing = {b: {'path': str(tmp_path / ('absent-' + b + '-pool.json')), 'sha256': '0' * 64}
               for b in p.BENCHES}
    manifest = {'data': {'pools': missing}}
    # Construct the already verified Setting locally; all entry, confirmation, canary, cell and read logic is real.
    monkeypatch.setattr(evaluation, 'setting_of', lambda *args, **kwargs: st)
    return st, manifest, spec, model


@pytest.mark.parametrize('configuration', [p.BASELINE_V210, p.MAIN_V3])
@pytest.mark.parametrize('chain_id', ['G', 'D'])
@pytest.mark.parametrize('invalid', ['missing', 'other_run', 'other_route', 'failed'])
def test_evaluation_entry_refuses_unconfirmed_chain_before_canaries_or_test_tasks(
        tmp_path, monkeypatch, configuration, chain_id, invalid):
    st, manifest, spec, model = entry(tmp_path, monkeypatch, configuration, chain_id)
    identity, filename = chain._confirm_of(st.run, chain_id, 'B' if chain_id == 'D' else None)[:2]
    if invalid != 'missing':
        identity = dict(identity)
        if invalid == 'other_run':
            identity['run'] = 'another-run'
        elif invalid == 'other_route':
            identity['route'] = 'A'
        write_json(st.root / chain_id / filename, p.record('first-call', st.evidence, {
            'identity': identity, 'passed': invalid != 'failed'}))

    def forbidden(*args, **kwargs):
        pytest.fail('Unconfirmed evaluation reached canaries or test-panel access')
    monkeypatch.setattr(evaluation, 'make_read_canaries', forbidden)
    monkeypatch.setattr(evaluation, 'test_tasks', forbidden)
    with pytest.raises(ValueError, match='confirmed first call|first-call record'):
        evaluation.run_unit_spec(manifest, spec=spec, panel=forbidden)
    assert not (st.root / chain_id / 'test').exists()
    assert model.calls == model.confirm_calls == 0


@pytest.mark.parametrize('chain_id', ['G', 'D'])
def test_confirmed_baseline_prepares_canaries_and_reads_with_absent_training_pools(tmp_path, monkeypatch, chain_id):
    st, manifest, spec, model = entry(tmp_path, monkeypatch, p.BASELINE_V210, chain_id)
    confirmed = chain.first_call(st, chain_id)
    assert confirmed == chain.confirmation(st.root, st.run, chain_id, configuration=p.BASELINE_V210)
    assert model.confirm_calls == 1
    s0_canaries(st.root)
    canary_panel = ReadPanel()

    def panels(pinned, bench, *, access):
        if access.unit == evaluation.READ_CANARY_UNIT:
            return canary_panel(pinned, bench, access=access)
        assert access.unit == chain_id + '/test/officeqa'
        # The historical OfficeQA panel fixture pins chain D; only its authored data is reused here.
        return office_panel(pinned, bench, access=evaluation.data.TestAccess('D/test/officeqa'))

    def forbidden(*args, **kwargs):
        pytest.fail('The baseline touched training pools or a procedure sandbox')
    monkeypatch.setattr(evaluation, '_training_side', forbidden)
    monkeypatch.setattr(evaluation, '_route_worker', forbidden)
    monkeypatch.setattr(units, 'Worker', forbidden)
    assert all(not Path(pin['path']).exists() for pin in manifest['data']['pools'].values())
    assert evaluation.run_unit_spec(manifest, spec=spec, panel=panels) == chain.EXIT_COMPLETE
    made = p.verified(read_json(st.root / evaluation.READ_CANARIES), 'test-read-canaries')
    assert made['training_side'] == {'skipped': True, 'reason': 'baseline_has_no_training', 'pool_reads': 0}
    assert made['training_pools'] == {b: None for b in evaluation.READ_CANARY_SOURCES}
    assert made['skipped'] == {b: 0 for b in evaluation.READ_CANARY_SOURCES}
    found = p.verified(read_json(st.root / chain_id / 'test/officeqa/unit.json'), 'evaluation')
    assert found['counts']['cells'] == 2 * len(ITEMS)
    assert found['counts']['by_arm'] == {'B': len(ITEMS), 'C': len(ITEMS)}
    assert model.calls == 2 * len(ITEMS) and model.confirm_calls == 1
    assert all(not Path(pin['path']).exists() for pin in manifest['data']['pools'].values())
    assert evaluation.run_unit_spec(manifest, spec=spec, panel=forbidden) == chain.EXIT_COMPLETE
    assert model.calls == 2 * len(ITEMS) and model.confirm_calls == 1


def test_main_v3_retains_training_pool_canaries_and_duplicate_exclusion(tmp_path):
    root = tmp_path / 'main'
    write_json(root / 'shared/consent.json', consent_value(multi_arm_arms=['F', 'C', 'B']))
    s0_canaries(root)
    duplicate = READ_TEXTS['officeqa'][0]
    pools = pool_pins(tmp_path / 'pools', {b: [duplicate] if b == 'officeqa' else ['Authored training text only.']
                                         for b in evaluation.READ_CANARY_SOURCES})
    # The five-bench registration also pins SearchQA and ALFWorld; canaries open only the three relevant fields.
    pools.update({b: {'path': str(tmp_path / (b + '-unopened.json')), 'sha256': 'a' * 64}
                  for b in ('searchqa', 'alfworld')})
    made = evaluation.make_read_canaries(root, None, pools=pools, run='main-canary-fixture',
        evidence='engineering_fixture', panel=ReadPanel(), order=p.BENCHES, configuration=p.MAIN_V3)
    assert 'training_side' not in made
    assert made['training_pools'] == {b: pools[b]['sha256'] for b in evaluation.READ_CANARY_SOURCES}
    assert made['skipped'] == {'officeqa': 1, 'livemath': 0, 'spreadsheetbench': 0}
    assert evaluation.canary(duplicate) not in made['canaries']
    other = tmp_path / 'main-missing'
    write_json(other / 'shared/consent.json', consent_value(multi_arm_arms=['F', 'C', 'B']))
    s0_canaries(other)
    Path(pools['officeqa']['path']).unlink()
    panel = ReadPanel()
    with pytest.raises(FileNotFoundError):
        evaluation.make_read_canaries(other, None, pools=pools, run='missing', evidence='engineering_fixture',
            panel=panel, order=p.BENCHES, configuration=p.MAIN_V3)
    assert panel.seen == [] and not (other / evaluation.READ_CANARIES).exists()


@pytest.mark.parametrize('change', ['missing_metadata', 'pool_pin', 'skipped_text'])
def test_baseline_refuses_a_resealed_canary_record_claiming_training_reads(tmp_path, change):
    root = tmp_path / 'baseline'
    write_json(root / 'shared/consent.json', consent_value(multi_arm_arms=['C', 'B']))
    s0_canaries(root)
    value = evaluation.make_read_canaries(root, None, pools=None, run='baseline', evidence='engineering_fixture',
        panel=ReadPanel(), order=p.BENCHES, configuration=p.BASELINE_V210)
    if change == 'missing_metadata':
        del value['training_side']
    elif change == 'pool_pin':
        value['training_pools']['officeqa'] = 'a' * 64
    else:
        value['skipped']['officeqa'] = 1
    altered = p.record('test-read-canaries', value['evidence'], {
        k: v for k, v in value.items() if k not in ('version', 'evidence', p.RECORD_HASH)})
    (root / evaluation.READ_CANARIES).write_text(json.dumps(altered))
    with pytest.raises(ValueError, match='baseline canaries skip training-side'):
        evaluation.load_canaries(root, read=True, configuration=p.BASELINE_V210)
