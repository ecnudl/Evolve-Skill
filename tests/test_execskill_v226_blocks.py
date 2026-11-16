"""Stable read-unit OfficeQA halves and fail-closed cross-arm strata."""
import pytest

from skillopt.coevo5.calls import Endpoint, Slots
from skillopt.coevo5.protocol import RUNTIME
from skillopt.continual_eval.core import read_json, write_json
from skillopt.execskill import cells, evaluation, package, profiles as p, v222_cards, v225_read as r
from tests.execskill_fakes_env import FakeSandbox
from tests.execskill_v293_fakes import tmp_path  # noqa: F401
from tests.test_execskill_acceptance import fast_statistics  # noqa: F401
from tests.test_execskill_evaluation import ITEMS, Solver
from tests.test_execskill_v225_read import synthetic_units
from tests.test_execskill_v225_reads import consent, panel


@pytest.mark.parametrize('configuration', [p.MAIN_V9, p.MAIN_V10])
def test_officeqa_stage_read_halves_are_stable_only_in_main_v10(tmp_path, configuration):
    root = tmp_path/'run'
    blank = package.empty(step='D/s0', evidence='engineering_fixture')
    fake = Solver()
    endpoint = Endpoint(fake, model=p.CHAINS['D'], max_tokens=100,
                        slots=Slots(root/'slots', 'deepseek', 2), sleep=lambda _: None)
    write_json(root/'shared/consent.json', consent())
    blocks = {}
    for event in ('anchor', 's3', 's4'):
        unit = root/'D/test'/event/'officeqa'
        context = cells.Context(attempt=unit/'attempt-1', endpoint=endpoint, runtime=RUNTIME,
            cards={'officeqa': v222_cards.format_text('officeqa')}, native=None, episodes=None,
            worker=lambda _: FakeSandbox(), evidence='engineering_fixture', configuration=configuration)
        r.evaluate_unit(unit, event=event, run='authored', shared=root/'shared', pinned=None,
            chain='D', bench='officeqa', chosen=r.arms(blank, event, chain='D', evidence='engineering_fixture'),
            context=context, workers=2, canaries=[], panel=panel)
        rows = [read_json(path) for path in (unit/'attempt-1/cells').glob('*.json')]
        blocks[event] = {row['cell']['task_id']: row['cell']['block'] for row in rows}
        seed = 'D/test/officeqa' if p.is_v226(configuration) else 'D/test/' + event + '/officeqa'
        assert blocks[event] == evaluation._blocks(sorted(row['task_id'] for row in ITEMS), 'officeqa', seed)
    if p.is_v226(configuration):
        assert blocks['anchor'] == blocks['s3'] == blocks['s4']
    else:
        assert blocks['anchor'] != blocks['s3']


def test_main_v10_readout_refuses_inconsistent_item_blocks(fast_statistics):
    units = synthetic_units()
    units['officeqa']['S3', '0', 0]['block'] = 'different-time-half'
    with pytest.raises(ValueError, match='main-v10 readout block mismatch across arms: officeqa'):
        r.readout(units, learned=[], procedures={}, label='authored', evidence='engineering_fixture',
                  configuration=p.MAIN_V10)
    # The frozen reader keeps its historical behavior and design function.
    assert r.readout(units, learned=[], procedures={}, label='authored', evidence='engineering_fixture',
                     configuration=p.MAIN_V9)['configuration'] == p.MAIN_V9
