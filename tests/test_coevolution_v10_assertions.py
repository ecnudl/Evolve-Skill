"""Handwritten offline fixtures only; no benchmark or candidate execution."""

import ast
import copy
import json
import math
from pathlib import Path

import pytest

from skillopt.coevolution_v10 import assertions as a
from skillopt.coevolution_v10 import codec as c


def observation(value):
    return {"value": c.encode_value(value), "exception": None}


@pytest.mark.parametrize("value", [
    None, False, True, 0, -1, 10**100, 0.0, -0.0, 1 / 3, float("inf"), float("-inf"),
    "", "中文\n\t", "\ud800", [], (), set(), {}, [1, (2, 3)], {(1, 2): [True, None]},
    {1, "x", (2, 3)}, {1: "int", "1": "str"}, ([], {1: {2, 3}}),
])
def test_codec_exact_types_round_trip(value):
    encoded = c.encode_value(value)
    decoded = c.decode_value(json.loads(json.dumps(encoded)))
    assert type(decoded) is type(value)
    assert decoded == value
    if type(value) is float:
        assert decoded.hex() == value.hex()


def test_codec_nan_output_is_representable_not_equal():
    encoded = c.encode_value(float("nan"))
    assert encoded == {"type": "float", "value": "nan"}
    assert math.isnan(c.decode_value(encoded))


@pytest.mark.parametrize("encoded", [
    None, [], {}, {"type": "none"}, {"type": "none", "value": 0},
    {"type": "none", "value": None, "extra": 1}, {"type": "bool", "value": 1},
    {"type": "int", "value": 1}, {"type": "int", "value": "+1"},
    {"type": "int", "value": "01"}, {"type": "int", "value": "-0"},
    {"type": "int", "value": "1" * 311}, {"type": "float", "value": "1.0"},
    {"type": "float", "value": "Infinity"}, {"type": "float", "value": "NaN"},
    {"type": "float", "value": 1.0}, {"type": "float", "value": "0x1p+50000"},
    {"type": "str", "value": 123}, {"type": "bytes", "value": "secret"},
    {"type": "list", "value": ()}, {"type": "dict", "value": [[c.encode_value(1)]]},
    {"type": "dict", "value": [[c.encode_value([]), c.encode_value(1)]]},
    {"type": "dict", "value": [[c.encode_value(1), c.encode_value(2)],
                                  [c.encode_value(True), c.encode_value(3)]]},
    {"type": "set", "value": [c.encode_value(1), c.encode_value(True)]},
    {"type": "set", "value": [c.encode_value([])]},
])
def test_codec_rejects_malformed_or_lossy_wire(encoded):
    with pytest.raises(c.ValueCodecError):
        c.decode_value(encoded)


def test_codec_never_calls_candidate_hooks():
    class Trap:
        def __iter__(self):
            pytest.fail("Foreign iteration executed")

        def __repr__(self):
            pytest.fail("Foreign repr executed")

        def __eq__(self, other):
            pytest.fail("Foreign equality executed")

    class ForeignList(list):
        def __iter__(self):
            pytest.fail("Subclass iteration executed")

    for value in (Trap(), ForeignList([1]), [Trap()], {"safe": Trap()}):
        with pytest.raises(c.ValueCodecError):
            c.encode_value(value)


@pytest.mark.parametrize("value", [b"bytes", 1j, frozenset({1}), range(3), 1 << 1024,
                                    "x" * (c.MAX_STRING_CHARS + 1)])
def test_codec_rejects_unsupported_output(value):
    with pytest.raises(c.ValueCodecError):
        c.encode_value(value)


def test_codec_structural_and_cyclic_bounds():
    deep = None
    for _ in range(c.MAX_DEPTH + 1):
        deep = [deep]
    cyclic = []
    cyclic.append(cyclic)
    for value in (deep, cyclic, [None] * c.MAX_NODES,
                  ["a" * c.MAX_STRING_CHARS] * 5):
        with pytest.raises(c.ValueCodecError):
            c.encode_value(value)
    encoded = {"type": "none", "value": None}
    for _ in range(c.MAX_DEPTH + 1):
        encoded = {"type": "list", "value": [encoded]}
    with pytest.raises(c.ValueCodecError):
        c.decode_value(encoded)


def test_static_literals_preserve_arguments_expected_and_public_privacy():
    compiled = a.compile_tests([
        "assert transform([1234567, -2], (3, 4), flag=True) == {'private': (9876543, None)}",
        "assert transform({1, 2}, (3,), flag=False) != []",
    ])
    assert compiled["compatible"]
    assert compiled["entry_point"] == "transform"
    assert compiled["public_interface"] == {
        "entry_point": "transform", "positional_argument_counts": [2], "keyword_names": ["flag"],
    }
    assert c.decode_value(compiled["cases"][0]["args"][0]) == [1234567, -2]
    assert type(c.decode_value(compiled["cases"][0]["args"][1])) is tuple
    assert c.decode_value(compiled["checks"][0]["expected"]) == {"private": (9876543, None)}
    public = json.dumps(compiled["public_interface"])
    assert not any(secret in public for secret in ("1234567", "9876543", "private", "True"))
    assert "expected" not in json.dumps(compiled["cases"])


@pytest.mark.parametrize("test, expected", [
    ("assert f() == None", None), ("assert f() == True", True),
    ("assert f() == False", False), ("assert f() == -5", -5),
    ("assert f() == +(3)", 3), ("assert f() == 1.5", 1.5),
    ("assert f() == 1 + 2 * 3", 7), ("assert f() == 9 / 2", 4.5),
    ("assert f() == -9 // 2", -5), ("assert f() == -9 % 2", 1),
    ("assert f() == 2 ** -3", 0.125), ("assert f() == 2 ** 10", 1024),
    ("assert f() == '文字'", "文字"), ("assert f() == []", []),
    ("assert f() == ()", ()), ("assert f() == {}", {}),
    ("assert f() == {1, 2, 1}", {1, 2}),
    ("assert f() == {1: 'a', True: 'b'}", {1: "b"}),
])
def test_compile_closed_literal_language(test, expected):
    compiled = a.compile_tests([test])
    assert compiled["compatible"], compiled["reason"]
    decoded = c.decode_value(compiled["checks"][0]["expected"])
    assert type(decoded) is type(expected)
    assert decoded == expected
    assert a.evaluate_observations(compiled, [observation(expected)])["passed"]


@pytest.mark.parametrize("test", [
    "assert f(1) < 2", "assert f(1) <= 2", "assert f(1) in [1]",
    "assert f(1) == g(1)", "assert f(g(1)) == 2", "assert obj.f(1) == 2",
    "assert f(*[1]) == 2", "assert f(**{'x':1}) == 2", "assert f(x=1,x=2) == 2",
    "assert f([x for x in range(3)]) == []", "assert f() == set()",
    "assert f() == list((1,))", "assert f() == float('nan')", "assert f() == 1e999",
    "assert f() == 1/0", "assert f() == 2**1000000", "assert f() == (-1)**0.5",
    "assert f() == 'x'*999999999", "assert f() == (lambda: 1)()",
    "assert f() == b'bytes'", "assert f() == 1j", "assert f() == ...",
    "assert f() == {**{'a':1}}", "assert f() == {[]:1}", "assert f() == {[]}",
    "assert f() is 100", "assert f() is not []", "assert f() == 1 == 1",
    "assert f() and True", "assert f() or False", "assert not (f() == 1)",
    "assert f()[0] == 1", "assert f() == variable", "assert f() == 1, 'message'",
    "assert f() == 1; assert f() == 2", "x = 1", "pass", "", "assert (",
    "import os\nassert f() == 1", "assert __import__('os') == 1",
])
def test_unsupported_never_silently_keeps_earlier_assertions(test):
    compiled = a.compile_tests(["assert f() == 1", test])
    assert not compiled["compatible"]
    assert compiled["reason"]
    assert compiled["unsupported_test_index"] == 1
    assert compiled["cases"] == [] and compiled["checks"] == []
    assert compiled["entry_point"] is None and compiled["public_interface"] is None


@pytest.mark.parametrize("setup", ["import math", "x=1", "pass", "def helper():\n return 1", "'docstring'"])
def test_setup_execution_is_never_allowed(setup):
    compiled = a.compile_tests(["assert f() == 1"], setup)
    assert not compiled["compatible"]
    assert "setup" in compiled["reason"]


def test_comments_and_arity_metadata_supported():
    compiled = a.compile_tests(["assert f() == 1 # retained", "assert f(2, key=3) == 4"], "\n # no code\n")
    assert compiled["compatible"]
    assert compiled["public_interface"]["positional_argument_counts"] == [0, 1]
    assert compiled["public_interface"]["keyword_names"] == ["key"]


def test_multiple_entry_points_are_whole_task_unsupported():
    compiled = a.compile_tests(["assert f(1) == 2", "assert other(2) == 3"])
    assert not compiled["compatible"]
    assert "unique" in compiled["reason"]
    assert compiled["cases"] == []


@pytest.mark.parametrize("test", [
    "assert _private(1) == 2", "assert f(_private=1) == 2",
    "assert f(" + ",".join(["1"] * 257) + ") == 2",
])
def test_static_invocations_fit_the_runner_contract(test):
    assert not a.compile_tests([test])["compatible"]


@pytest.mark.parametrize("tests", [[], {}, None, "assert f()==1", [1], ["assert f()==1"] * 65,
                                    ["assert f() == '" + "x" * 32768 + "'"],
                                    ["assert f()==1 #" + "x" * 10000] * 30])
def test_compile_input_bounds_fail_closed(tests):
    compiled = a.compile_tests(tests)
    assert not compiled["compatible"]
    assert compiled["cases"] == []


@pytest.mark.parametrize("test,value,expected", [
    ("assert f() == 1", True, True), ("assert f() == True", 1, True),
    ("assert f() == 1", 1.0, True), ("assert f() == [1]", (1,), False),
    ("assert f() == (1,)", [1], False), ("assert f() == {1}", {True}, True),
    ("assert f() == {1: 'x'}", {True: "x"}, True),
    ("assert f() == 0.3", 0.1 + 0.2, False),
    ("assert f() != 0.3", 0.1 + 0.2, True),
    ("assert f() == 1.0", 1.0 + 1e-12, False),
    ("assert f() == -0.0", 0.0, True),
    ("assert f() == 1", float("nan"), False),
    ("assert f() != 1", float("nan"), True),
    ("assert f() is True", 1, False), ("assert f() is True", True, True),
    ("assert f() is False", False, True), ("assert f() is None", None, True),
    ("assert f() is not None", False, True), ("assert f() is not True", 1, True),
    ("assert f()", [0], True), ("assert f()", [], False), ("assert f()", 1, True),
    ("assert not f()", {}, True), ("assert not f()", [0], False),
])
def test_native_predicates_not_approximate_or_overstrict_type_matching(test, value, expected):
    compiled = a.compile_tests([test])
    assert compiled["compatible"]
    result = a.evaluate_observations(compiled, [observation(value)])
    assert result["passed"] is expected
    assert result["passed_count"] == int(expected)
    assert result["total"] == 1


def test_exceptions_are_failed_assertions_not_dropped():
    compiled = a.compile_tests(["assert f(1) == 2", "assert f(2) == 3"])
    result = a.evaluate_observations(compiled, [observation(2), {"value": None, "exception": "ValueError"}])
    assert not result["passed"] and result["passed_count"] == 1 and result["total"] == 2
    assert result["checks"][1] == {"index": 1, "passed": False, "exception": "ValueError"}


@pytest.mark.parametrize("observations", [
    [], [observation(1), observation(1)], {}, [None], [{"value": c.encode_value(1)}],
    [{"value": c.encode_value(1), "exception": None, "passed": True}],
    [{"value": None, "exception": None}], [{"value": c.encode_value(1), "exception": "ValueError"}],
    [{"value": None, "exception": 3}], [{"value": None, "exception": ""}],
])
def test_invalid_observations_are_transport_errors(observations):
    compiled = a.compile_tests(["assert f() == 1"])
    with pytest.raises(ValueError):
        a.evaluate_observations(compiled, observations)


@pytest.mark.parametrize("field,value", [
    ("compatible", False), ("version", "other"), ("entry_point", "a.b"),
    ("checks", []), ("cases", []),
    ("checks", [{"operator": "eval", "expected": c.encode_value(1)}]),
    ("checks", [{"operator": "is", "expected": c.encode_value(1)}]),
    ("checks", [{"operator": "truthy", "expected": c.encode_value(1)}]),
    ("cases", [{"args": [], "kwargs": {}, "expected": 1}]),
    ("cases", [{"args": [], "kwargs": {"__import__": c.encode_value(1)}}]),
])
def test_malformed_compiled_schema_never_scores(field, value):
    compiled = a.compile_tests(["assert f() == 1"])
    compiled[field] = value
    with pytest.raises(ValueError):
        a.evaluate_observations(compiled, [observation(1)])


def test_no_module_contains_host_eval_exec_or_compile_calls():
    for path in (Path(a.__file__), Path(c.__file__)):
        tree = ast.parse(path.read_text())
        forbidden = [node.func.id for node in ast.walk(tree)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                     and node.func.id in {"eval", "exec", "compile"}]
        assert forbidden == []


def test_evaluation_does_not_mutate_inputs():
    compiled = a.compile_tests(["assert f([1]) == [2]"])
    observations = [observation([2])]
    frozen = copy.deepcopy((compiled, observations))
    a.evaluate_observations(compiled, observations)
    assert (compiled, observations) == frozen
