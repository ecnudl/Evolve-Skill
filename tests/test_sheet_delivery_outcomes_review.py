"""Independent receipt-adaptation controls; no real model or native execution."""

from copy import deepcopy

import pytest

from scripts import report_sheet_delivery_outcomes as audit
from skillopt.continual_eval import delivery_outcomes
from skillopt.continual_eval.core import read_json
from tests.test_sheet_delivery_outcomes_report import BUDGET, _rewrite, fixture


@pytest.mark.parametrize(
    "error_type,finish,stream_complete,http_status,budget_exhausted",
    [
        (None, "length", True, 200, True),
        ("truncated_content", "length", True, 200, True),
        ("truncated_content", "max_tokens", True, 200, True),
        ("timeout", "length", True, 200, False),
        ("unexpected_response_model", "length", True, 200, False),
        ("incomplete_stream", "length", False, 200, False),
        ("truncated_content", "stop", True, 200, False),
        ("truncated_content", "length", False, 200, False),
        ("truncated_content", "length", True, 503, False),
    ],
)
def test_provider_content_truncation_is_not_transport_failure(
    tmp_path, error_type, finish, stream_complete, http_status, budget_exhausted
):
    args, slots = fixture(tmp_path)
    call_path = next((audit.safe_path(slots[BUDGET]["prediction_path"]).parent / "calls").glob("*.json"))

    def adapt(row):
        row["receipt"].update(
            error_type=error_type, finish_reason=finish, stream_complete=stream_complete, status=http_status
        )

    _rewrite(call_path, adapt)
    result = audit.build(**args)
    assert result["positions"] == 160
    assert result["delivery_outcomes"].get("completed_model_budget_exhaustion", 0) == int(budget_exhausted)
    assert result["semantic_to_end_to_end"]["unknown->fail"] == 5 + int(budget_exhausted)
    assert not result["semantic_scores_changed"]
    assert not result["policy"]["preregistered_before_original_model_calls"]


def test_reviewed_generated_line_must_appear_in_preserved_generated_traceback(tmp_path):
    args, slots = fixture(tmp_path)
    archive = read_json(args["attribution_report"], sealed=True)
    evidence = audit.Evidence()
    _, _, records = audit._native_records(evidence, args["native_replay"], archive)
    slot = slots[0]
    prediction, _, _ = audit._prediction(evidence, slot)
    reviewed = deepcopy(archive["rows"][0])
    identity = {key: reviewed[key] for key in delivery_outcomes.IDENTITY_FIELDS}
    row = deepcopy(records[slot["id"]])
    # A claimed list of lines does not establish that the reviewed line was
    # observed: the actual retained generated frame is only line 3.
    row["result"]["diagnostic"]["generated_lines"].append(999)
    reviewed["generated_line"] = 999
    with pytest.raises(ValueError):
        observation = audit._observed_native(row, identity, slot, prediction)
        delivery_outcomes.assess_delivery_outcome(
            identity=identity,
            semantic_score={"status": "unknown", "score": None},
            observation=observation,
            attribution=reviewed,
        )
