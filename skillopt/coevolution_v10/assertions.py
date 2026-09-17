"""Static MBPP-derived assertion compiler; never executes downloaded code.

Every assertion of a task must belong to the closed language. Expected values
stay in ``checks`` on the host; ``cases`` alone may enter the isolated runner.
This deliberately restricted protocol is not the full MBPP checker.
"""

from __future__ import annotations

import ast
import keyword
import math
import operator
import re

from skillopt.coevolution_v10.codec import (
    MAX_DEPTH,
    MAX_INT_BITS,
    MAX_NODES,
    MAX_STRING_CHARS,
    ValueCodecError,
    decode_value,
    encode_value,
)

VERSION = "v10-native-assertions-1"
MAX_TESTS = 64
MAX_TEST_CHARS = 32768
MAX_SOURCE_CHARS = 262144
MAX_ARGUMENTS = 256
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
_ARITHMETIC = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow,
}


class UnsupportedAssertion(ValueError):
    """The whole task is outside the preregistered assertion language."""


def _name(value):
    return (type(value) is str and _NAME.fullmatch(value) is not None
            and not value.startswith("_") and not keyword.iskeyword(value))


def _parse(source):
    if type(source) is not str or len(source) > MAX_TEST_CHARS:
        raise UnsupportedAssertion("Source is not a bounded string")
    try:
        tree = ast.parse(source, mode="exec")
    except (SyntaxError, ValueError, RecursionError) as error:
        raise UnsupportedAssertion("Source does not parse as bounded Python") from error
    pending, count = [(tree, 0)], 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise UnsupportedAssertion("Assertion AST exceeds structural bounds")
        pending.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
    return tree


def _number(value):
    if type(value) is int and value.bit_length() <= MAX_INT_BITS:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise UnsupportedAssertion("Arithmetic requires bounded finite numeric constants")


def _literal(node):
    if isinstance(node, ast.Constant):
        value = node.value
        if type(value) not in (type(None), bool, int, float, str):
            raise UnsupportedAssertion("Unsupported constant type")
        if type(value) in (int, float):
            _number(value)
        if type(value) is str and len(value) > MAX_STRING_CHARS:
            raise UnsupportedAssertion("Literal string exceeds bound")
        return value
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values = [_literal(item) for item in node.elts]
        try:
            return {ast.List: list, ast.Tuple: tuple, ast.Set: set}[type(node)](values)
        except TypeError as error:
            raise UnsupportedAssertion("Unhashable set literal") from error
    if isinstance(node, ast.Dict):
        if any(key is None for key in node.keys):
            raise UnsupportedAssertion("Dictionary unpacking is not supported")
        result = {}
        for key, value in zip(node.keys, node.values):
            try:
                result[_literal(key)] = _literal(value)
            except TypeError as error:
                raise UnsupportedAssertion("Unhashable dictionary literal key") from error
        return result
    if isinstance(node, ast.UnaryOp) and type(node.op) in (ast.UAdd, ast.USub):
        value = _number(_literal(node.operand))
        return _number(value if isinstance(node.op, ast.UAdd) else -value)
    if isinstance(node, ast.BinOp) and type(node.op) in _ARITHMETIC:
        left, right = _number(_literal(node.left)), _number(_literal(node.right))
        if isinstance(node.op, ast.Pow):
            if type(right) is not int or abs(right) > 128:
                raise UnsupportedAssertion("Exponent must be a bounded integer")
            if type(left) is int and right > 0 and left.bit_length() * right > MAX_INT_BITS:
                raise UnsupportedAssertion("Exponentiation would exceed integer bound")
        if isinstance(node.op, ast.Mult) and type(left) is int and type(right) is int:
            if left.bit_length() + right.bit_length() > MAX_INT_BITS + 1:
                raise UnsupportedAssertion("Multiplication would exceed integer bound")
        try:
            return _number(_ARITHMETIC[type(node.op)](left, right))
        except (ArithmeticError, ValueError) as error:
            raise UnsupportedAssertion("Constant arithmetic is undefined or exceeds bounds") from error
    raise UnsupportedAssertion("Only literals and bounded numeric constant arithmetic are supported")


def _call(node):
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or not _name(node.func.id):
        raise UnsupportedAssertion("Assertion must call one direct named function")
    if any(isinstance(argument, ast.Starred) for argument in node.args):
        raise UnsupportedAssertion("Positional unpacking is not supported")
    if len(node.args) + len(node.keywords) > MAX_ARGUMENTS:
        raise UnsupportedAssertion("Invocation exceeds the isolated runner argument bound")
    names = [keyword.arg for keyword in node.keywords]
    if not all(_name(name) for name in names) or len(set(names)) != len(names):
        raise UnsupportedAssertion("Keyword unpacking or duplicate/unsupported keyword names")
    return node.func.id, {
        "args": [encode_value(_literal(argument)) for argument in node.args],
        "kwargs": {keyword.arg: encode_value(_literal(keyword.value)) for keyword in node.keywords},
    }


def _assertion(statement):
    if not isinstance(statement, ast.Assert) or statement.msg is not None:
        raise UnsupportedAssertion("Each test must be one assert without a message expression")
    test = statement.test
    if isinstance(test, ast.Call):
        call, operation, expected = test, "truthy", None
    elif isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not) and isinstance(test.operand, ast.Call):
        call, operation, expected = test.operand, "falsy", None
    elif isinstance(test, ast.Compare) and len(test.ops) == 1:
        call = test.left
        operation = {ast.Eq: "eq", ast.NotEq: "ne", ast.Is: "is", ast.IsNot: "is_not"}.get(type(test.ops[0]))
        if operation is None:
            raise UnsupportedAssertion("Comparison operator is outside the supported subset")
        value = _literal(test.comparators[0])
        if operation in ("is", "is_not") and value is not None and type(value) is not bool:
            raise UnsupportedAssertion("Identity checks support only None and bool singletons")
        expected = encode_value(value)
    else:
        raise UnsupportedAssertion("Assertion expression is outside the supported subset")
    entry, case = _call(call)
    return entry, case, {"operator": operation, "expected": expected}


def compile_tests(test_list, setup_code=""):
    """Return all compiled tests or a wholly unsupported task, never a subset.

    Setup permits only whitespace/comments. No reference code, assertion code,
    or downloaded setup is ever evaluated or executed by this module.
    """
    result = {"version": VERSION, "compatible": False, "reason": None,
              "unsupported_test_index": None, "entry_point": None,
              "public_interface": None, "cases": [], "checks": []}
    index = None
    try:
        if type(test_list) not in (list, tuple) or not 1 <= len(test_list) <= MAX_TESTS:
            raise UnsupportedAssertion("Expected a bounded, nonempty test sequence")
        if any(type(test) is not str for test in test_list):
            raise UnsupportedAssertion("Every test must be a source string")
        if sum(map(len, test_list)) > MAX_SOURCE_CHARS:
            raise UnsupportedAssertion("Test source exceeds total character bound")
        if _parse(setup_code).body:
            raise UnsupportedAssertion("Nonempty executable setup is not supported")
        cases, checks, entries = [], [], set()
        for index, source in enumerate(test_list):
            tree = _parse(source)
            if len(tree.body) != 1:
                raise UnsupportedAssertion("Each test string must contain exactly one assertion")
            entry, case, check = _assertion(tree.body[0])
            entries.add(entry)
            cases.append(case)
            checks.append(check)
        if len(entries) != 1:
            raise UnsupportedAssertion("All assertions must use one unique function entry point")
        entry = next(iter(entries))
        result.update(compatible=True, entry_point=entry, cases=cases, checks=checks,
                      public_interface={"entry_point": entry,
                                        "positional_argument_counts": sorted({len(case["args"]) for case in cases}),
                                        "keyword_names": sorted({name for case in cases for name in case["kwargs"]})})
    except (UnsupportedAssertion, ValueCodecError, RecursionError) as error:
        result.update(reason=str(error), unsupported_test_index=index)
    return result


def _compiled_checks(compiled):
    if (type(compiled) is not dict or compiled.get("version") != VERSION
            or compiled.get("compatible") is not True or not _name(compiled.get("entry_point"))):
        raise ValueError("A compatible compiled assertion task is required")
    cases, checks = compiled.get("cases"), compiled.get("checks")
    if (type(cases) is not list or type(checks) is not list or not 1 <= len(cases) <= MAX_TESTS
            or len(cases) != len(checks)):
        raise ValueError("Compiled case/check cardinality is invalid")
    for case in cases:
        if (type(case) is not dict or set(case) != {"args", "kwargs"}
                or type(case["args"]) is not list or type(case["kwargs"]) is not dict
                or len(case["args"]) + len(case["kwargs"]) > MAX_ARGUMENTS
                or not all(_name(name) for name in case["kwargs"])):
            raise ValueError("Malformed compiled invocation")
        for value in [*case["args"], *case["kwargs"].values()]:
            decode_value(value)
    validated = []
    for check in checks:
        if type(check) is not dict or set(check) != {"operator", "expected"}:
            raise ValueError("Malformed compiled check")
        operation, expected = check["operator"], check["expected"]
        if type(operation) is not str or operation not in ("eq", "ne", "is", "is_not", "truthy", "falsy"):
            raise ValueError("Unsupported compiled comparison")
        if operation in ("truthy", "falsy"):
            if expected is not None:
                raise ValueError("Truthiness checks cannot carry expected values")
            value = None
        else:
            value = decode_value(expected)
            if operation in ("is", "is_not") and value is not None and type(value) is not bool:
                raise ValueError("Only None and bool identity are supported")
        validated.append((operation, value))
    return validated


def evaluate_observations(compiled, observations):
    """Score strictly cardinality-matched typed child observations on the host.

    Malformed transport raises ValueError rather than becoming a semantic zero.
    A genuine candidate exception is a failed assertion, retained explicitly.
    Native Python equality is exact: list differs from tuple, but 1 equals True.
    """
    checks = _compiled_checks(compiled)
    if type(observations) is not list or len(observations) != len(checks):
        raise ValueError("Observation cardinality must exactly match all compiled assertions")
    details = []
    for index, (observation, (operation, expected)) in enumerate(zip(observations, checks)):
        if type(observation) is not dict or set(observation) != {"value", "exception"}:
            raise ValueError("Observation requires exactly value and exception")
        exception = observation["exception"]
        if exception is not None:
            if (type(exception) is not str or not _name(exception) or observation["value"] is not None):
                raise ValueError("Malformed candidate exception observation")
            passed = False
        else:
            value = decode_value(observation["value"])
            if operation == "eq":
                passed = value == expected
            elif operation == "ne":
                passed = value != expected
            elif operation == "is":
                passed = value is expected
            elif operation == "is_not":
                passed = value is not expected
            elif operation == "truthy":
                passed = bool(value)
            else:
                passed = not value
        details.append({"index": index, "passed": passed, "exception": exception})
    return {"passed": all(item["passed"] for item in details),
            "passed_count": sum(item["passed"] for item in details),
            "total": len(details), "checks": details}
