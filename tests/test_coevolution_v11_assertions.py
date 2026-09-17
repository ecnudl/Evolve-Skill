"""Exact predicate compatibility and truthiness transport, synthetic inputs only."""

from copy import deepcopy

import pytest

from skillopt.coevolution_v10 import assertions as old
from skillopt.coevolution_v10.codec import encode_value
from skillopt.coevolution_v11 import assertions as a


def row(value):
    return {"value": encode_value(value), "exception": None, "truthiness": bool(value), "typed": True}


@pytest.mark.parametrize("test", [
    "assert f((1,2)) == (1,2)", "assert f([1]) != (1,)", "assert f(1) is True",
    "assert f(None) is not False", "assert f(1)", "assert not f(0)",
    "assert f(x=1+2) == 3", "assert sorted(f(1)) == [1]", "import os", "assert f(1) > 0",
])
def test_compile_language_unchanged_except_version(test):
    previous, current = old.compile_tests([test]), a.compile_tests([test])
    assert current == {**previous, "version": a.VERSION}
    if current["compatible"]:
        assert a._compiled_checks(current) == old._compiled_checks(previous)
    with pytest.raises(ValueError):
        a._compiled_checks(previous)


@pytest.mark.parametrize("test,value", [
    ("assert f(0)", [1]), ("assert not f(0)", []), ("assert f(0)", float("nan")),
    ("assert f(0) == True", 1), ("assert f(0) is True", 1),
    ("assert f(0) == (1,)", [1]), ("assert f(0) != (1,)", [1]),
    ("assert f(0) is None", None), ("assert f(0) is not False", 0),
    ("assert f(0) == 1.00000000000001", 1.0),
])
def test_typed_native_semantics_equal_frozen_comparator(test, value):
    previous = old.evaluate_observations(old.compile_tests([test]), [{"value": encode_value(value), "exception": None}])
    current = a.evaluate_observations(a.compile_tests([test]), [row(value)])
    assert current["passed"] == previous["passed"]
    assert current["checks"] == previous["checks"]
    assert current["uniform_truthiness_observations"]


@pytest.mark.parametrize("truthiness", [True, False])
@pytest.mark.parametrize("predicate", ["assert f(0)", "assert not f(0)"])
def test_untyped_truthiness_is_scored_without_fabricating_object(truthiness, predicate):
    observation = {"value": None, "exception": None, "truthiness": truthiness, "typed": False}
    score = a.evaluate_observations(a.compile_tests([predicate]), [observation])
    assert score["passed"] is (not truthiness if "not" in predicate else truthiness)


@pytest.mark.parametrize("predicate", ["== 1", "!= 1", "is None", "is not False"])
def test_untyped_nontruthiness_predicates_raise_unknown(predicate):
    observation = {"value": None, "exception": None, "truthiness": True, "typed": False}
    with pytest.raises(a.ObservationUnavailable):
        a.evaluate_observations(a.compile_tests(["assert f(0) " + predicate]), [observation])


def test_unknown_required_case_does_not_score_partial_task():
    compiled = a.compile_tests(["assert f(0)", "assert f(1) == 1"])
    with pytest.raises(a.ObservationUnavailable):
        a.evaluate_observations(compiled, [row(1), {"value": None, "exception": None, "truthiness": True, "typed": False}])


@pytest.mark.parametrize("mutation", [
    {"typed": 1}, {"truthiness": 1}, {"typed": False}, {"truthiness": False},
    {"exception": "ValueError"}, {"value": None}, {"passed": True},
])
def test_malformed_schema_never_produces_score(mutation):
    observation = {**row(1), **mutation}
    with pytest.raises(ValueError):
        a.evaluate_observations(a.compile_tests(["assert f(0)"]), [observation])


@pytest.mark.parametrize("observations", [None, [], [row(1), row(2)]])
def test_exact_cardinality(observations):
    with pytest.raises(ValueError):
        a.evaluate_observations(a.compile_tests(["assert f(0)"]), observations)


def test_python_exception_failure_and_memory_unknown():
    compiled = a.compile_tests(["assert f(0)"])
    observation = {"value": None, "exception": "ValueError", "truthiness": None, "typed": False}
    assert a.evaluate_observations(compiled, [observation])["passed"] is False
    with pytest.raises(a.ObservationUnavailable):
        a.evaluate_observations(compiled, [{**observation, "exception": "MemoryError"}])


def test_no_compiled_or_observed_mutation():
    compiled = a.compile_tests(["assert f(0)"])
    observations = [row([1])]
    saved = deepcopy((compiled, observations))
    a.evaluate_observations(compiled, observations)
    assert (compiled, observations) == saved


def test_host_cannot_receive_arbitrary_object_or_call_its_bool():
    class HostPoison:
        def __bool__(self):
            pytest.fail("Host attempted bool(arbitrary object)")
    malformed = {"value": HostPoison(), "exception": None, "truthiness": True, "typed": True}
    with pytest.raises(ValueError):
        a.evaluate_observations(a.compile_tests(["assert f(0)"]), [malformed])
