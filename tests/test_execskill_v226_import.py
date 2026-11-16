"""The imported fifth step explicitly reports zero candidate containment events."""
from types import SimpleNamespace

import pytest

from skillopt.continual_eval.core import read_json
from skillopt.execskill import profiles as p, v210_import
from skillopt.execskill.package import empty
from tests.execskill_v293_fakes import tmp_path  # noqa: F401


@pytest.mark.parametrize('configuration', [p.MAIN_V9, p.MAIN_V10])
def test_import_step_has_main_v10_only_candidate_error_fields(tmp_path, configuration):
    setting = SimpleNamespace(root=tmp_path, evidence='engineering_fixture', extra={
        'configuration': configuration, 'alfworld_v11_import': v210_import.pins()})
    parent = empty(step='G/s4-spreadsheetbench', evidence=setting.evidence)
    args = (setting, tmp_path/'G', 'G', 5, 'alfworld', parent)
    result, record = v210_import.import_step(*args)
    stored = p.verified(read_json(tmp_path/'G/s5-alfworld/step.json'), 'step')
    assert record == stored and record['decision'] == 'import'
    if p.is_v226(configuration):
        assert record['candidate_errors'] == {}
        assert record['candidate_error_events'] == []
    else:
        assert 'candidate_errors' not in record and 'candidate_error_events' not in record
    assert v210_import.import_step(*args) == (result, record)
