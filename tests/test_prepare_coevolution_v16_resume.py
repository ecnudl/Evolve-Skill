"""Pure-ledger checks for quarantining an interrupted V16 request tail.

These fixtures contain no trajectories or API configuration.  Selection must
depend on the registered time boundary, never on a request's success.
"""

from copy import deepcopy

import pytest

from scripts import prepare_coevolution_v16_resume as resume

BOUNDARY = 100.0
SLEEP = 150.0


def _hash(number):
    return f"{number:064x}"


@pytest.fixture
def ledger():
    """Three completed calls followed by an eight-call interrupted batch."""
    calls = {}
    admissions = {}
    attempts = {}

    def add(sequence, number, admitted, finished):
        request_hash = _hash(number)
        call = calls.setdefault(
            request_hash,
            {
                "request_hash": request_hash,
                "ok": True,
                "http_attempt_count": 0,
                "pacing": {"attempts": []},
            },
        )
        call["http_attempt_count"] += 1
        call["pacing"]["attempts"].append({"sequence": sequence})
        admissions[sequence] = {
            "sequence": sequence,
            "request_hash": request_hash,
            "admitted_wall": admitted,
        }
        attempts[sequence] = {
            "sequence": sequence,
            "request_hash": request_hash,
            "finished_wall": finished,
        }

    add(1, 1, 10.0, 20.0)
    add(2, 2, 30.0, 35.0)
    add(3, 2, 40.0, 45.0)  # One retained logical call has two HTTP attempts.
    add(4, 3, 60.0, 70.0)
    for sequence, number, admitted in [
        (5, 4, 100.0),
        (6, 5, 110.0),
        (7, 6, 120.0),
        (8, 7, 130.0),
        (9, 8, 140.0),
        (10, 9, 145.0),
        (11, 10, 160.0),
        (12, 11, 170.0),
    ]:
        add(sequence, number, admitted, 155.0 if sequence == 10 else admitted + 2.0)
    return calls, admissions, attempts


def _choose(ledger, *, boundary_wall=BOUNDARY, sleep_wall=SLEEP):
    calls, admissions, attempts = ledger
    return resume.choose_tail(
        calls,
        admissions,
        attempts,
        boundary_wall=boundary_wall,
        sleep_wall=sleep_wall,
    )


def test_time_boundary_excludes_whole_eight_call_batch_and_keeps_attempt_prefix(ledger):
    selected = _choose(ledger)
    assert selected["retained_calls"] == [_hash(number) for number in range(1, 4)]
    assert selected["excluded_calls"] == [_hash(number) for number in range(4, 12)]
    assert selected["retained_sequences"] == [1, 2, 3, 4]
    assert selected["excluded_sequences"] == list(range(5, 13))
    assert selected["overlap_calls"] == [_hash(number) for number in (9, 10, 11)]


def test_receipt_at_boundary_belongs_to_excluded_batch(ledger):
    selected = _choose(ledger)
    assert _hash(4) in selected["excluded_calls"]
    assert 5 in selected["excluded_sequences"]


def test_completed_pre_sleep_tail_calls_are_not_cherry_picked_back_in(ledger):
    selected = _choose(ledger)
    # These calls completed before sleep but belong to the same registered batch.
    assert all(_hash(number) in selected["excluded_calls"] for number in range(4, 9))


def test_dark_wake_requests_count_even_without_an_attempt_crossing_sleep_onset(ledger):
    ledger[2][10]["finished_wall"] = SLEEP - 1.0
    selected = _choose(ledger)
    assert selected["overlap_calls"] == [_hash(10), _hash(11)]
    assert selected["excluded_calls"] == [_hash(number) for number in range(4, 12)]


@pytest.mark.parametrize("number", [1, 4, 9, 11])
def test_success_or_failure_does_not_affect_boundary_selection(ledger, number):
    expected = _choose(ledger)
    ledger[0][_hash(number)]["ok"] = False
    assert _choose(ledger) == expected


def test_result_is_sorted_and_independent_of_dictionary_insertion_order(ledger):
    expected = _choose(ledger)
    reversed_ledger = tuple(dict(reversed(list(records.items()))) for records in ledger)
    assert _choose(reversed_ledger) == expected


def test_selection_does_not_modify_source_receipts(ledger):
    original = deepcopy(ledger)
    _choose(ledger)
    assert ledger == original


def test_request_with_retry_admissions_on_both_sides_of_boundary_is_rejected(ledger):
    calls, admissions, attempts = ledger
    crossing = _hash(2)
    previous = admissions[5]["request_hash"]
    del calls[previous]
    admissions[5]["request_hash"] = crossing
    attempts[5]["request_hash"] = crossing
    calls[crossing]["pacing"]["attempts"].append({"sequence": 5})
    calls[crossing]["http_attempt_count"] += 1
    with pytest.raises(ValueError):
        _choose(ledger)


def test_single_inflight_attempt_crossing_boundary_is_rejected(ledger):
    ledger[2][4]["finished_wall"] = BOUNDARY + 1.0
    with pytest.raises(ValueError):
        _choose(ledger)


@pytest.mark.parametrize("finished", [SLEEP, SLEEP + 1.0])
def test_retained_attempt_must_finish_strictly_before_sleep(ledger, finished):
    ledger[2][4]["finished_wall"] = finished
    with pytest.raises(ValueError):
        _choose(ledger)


def test_boundary_after_sleep_cannot_retain_an_attempt_admitted_after_sleep(ledger):
    calls, admissions, attempts = ledger
    for sequence in range(5, 13):
        admissions[sequence]["admitted_wall"] += 100.0
        attempts[sequence]["finished_wall"] += 100.0
    admissions[4]["admitted_wall"] = SLEEP + 1.0
    attempts[4]["finished_wall"] = SLEEP + 2.0
    with pytest.raises(ValueError):
        _choose((calls, admissions, attempts), boundary_wall=200.0)


def test_no_attempt_during_or_after_sleep_is_not_an_interrupted_batch(ledger):
    with pytest.raises(ValueError):
        _choose(ledger, sleep_wall=200.0)


@pytest.mark.parametrize("sequence", [1, 10, 12])
def test_missing_http_outcome_rejects_retained_and_excluded_receipts(ledger, sequence):
    del ledger[2][sequence]
    with pytest.raises(ValueError):
        _choose(ledger)


@pytest.mark.parametrize("sequence", [1, 4, 8])
def test_gap_in_admission_and_outcome_sequences_is_rejected(ledger, sequence):
    calls, admissions, attempts = ledger
    request_hash = admissions[sequence]["request_hash"]
    del admissions[sequence]
    del attempts[sequence]
    call = calls[request_hash]
    call["pacing"]["attempts"] = [
        record for record in call["pacing"]["attempts"] if record["sequence"] != sequence
    ]
    call["http_attempt_count"] -= 1
    if not call["http_attempt_count"]:
        del calls[request_hash]
    with pytest.raises(ValueError):
        _choose(ledger)


def test_outcome_without_admission_is_rejected(ledger):
    del ledger[1][10]
    with pytest.raises(ValueError):
        _choose(ledger)


def test_admission_and_outcome_request_hashes_must_agree(ledger):
    ledger[2][10]["request_hash"] = _hash(8)
    with pytest.raises(ValueError):
        _choose(ledger)


def test_call_receipt_cannot_claim_another_requests_attempt(ledger):
    ledger[0][_hash(8)]["pacing"]["attempts"] = [{"sequence": 10}]
    with pytest.raises(ValueError):
        _choose(ledger)


def test_missing_logical_call_receipt_is_rejected(ledger):
    del ledger[0][_hash(9)]
    with pytest.raises(ValueError):
        _choose(ledger)


def test_declared_http_attempt_count_must_match_receipt(ledger):
    ledger[0][_hash(2)]["http_attempt_count"] = 1
    with pytest.raises(ValueError):
        _choose(ledger)
