"""Start measurements travel with shell/cell lifecycle evidence, without old-field changes."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from skillopt.execskill import cells, protocol, solver
from tests.test_execskill_solver import ClosingSandbox, CARD, FACTS, Script, package
from tests.fixtures.execskill.items import officeqa_items


START = {"container": "execskill-sbx-" + "a" * 32, "seconds": 30.0,
         "ready_timeout_seconds": 90, "ready": True}


@pytest.mark.parametrize("starts", [None, []])
def test_older_worker_lifecycle_has_exact_prior_keys(starts):
    worker = SimpleNamespace(restarts=[], cleanups=[])
    if starts is not None:
        worker.starts = starts
    assert solver._Shell.sandbox(SimpleNamespace(worker=worker)) == {"restarts": [], "cleanups": []}


def test_shell_copies_successful_and_failed_starts_with_cleanup_after_close():
    worker = ClosingSandbox({"fx-facts": {"before_call": lambda view, state: {"facts": ["one fact"]}}})
    failed = {**START, "container": "execskill-sbx-" + "b" * 32, "seconds": 90.0, "ready": False}
    worker.starts = [failed, dict(START)]
    item = officeqa_items(1)[0]
    result = solver.solve("officeqa", item["public"], CARD, package(FACTS), Script(["<answer>1</answer>"]),
                          worker=worker)
    box = protocol.verified(result["shell"], "shell")["sandbox"]
    assert worker.closed and len(box["cleanups"]) == 1
    assert box["starts"] == [failed, START]
    worker.starts[-1]["seconds"] = 999
    assert box["starts"][-1]["seconds"] == 30


def test_cell_records_start_measurements_with_correct_step_and_without_mutation():
    failed = {**START, "ready": False, "seconds": 90.0}
    runs = [("solve", {"shell": {"sandbox": {"starts": [failed, dict(START)]}}}),
            ("reexecute", {"shell": {"sandbox": {"starts": [dict(START)]}}})]
    before = deepcopy(runs)
    found = cells._sandbox(runs)
    assert found == {"restarts": [], "cleanups": [], "starts": [
        {**failed, "step": "solve"}, {**START, "step": "solve"}, {**START, "step": "reexecute"}]}
    assert runs == before


@pytest.mark.parametrize("runs", [[], [("solve", {})], [("solve", {"shell": {"sandbox": {"starts": []}}})]])
def test_no_new_cell_field_without_measured_start(runs):
    assert cells._sandbox(runs) == {"restarts": [], "cleanups": []}
