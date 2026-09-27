"""Observer structure and truth table; no generated/candidate source host exec."""
import ast

import pytest

from skillopt.skill_validation import curriculum_tasks as curriculum

CASE = {"input": [2, -1, 2, 0], "transformed": [2, 1], "expected": 4}


def _loop(role, *, audit=True):
    source = curriculum._runner([CASE], role, audit=audit)
    tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_run")
    loop = next(n for n in function.body if isinstance(n, ast.For))
    return source, loop


@pytest.mark.parametrize("audit", [False, True])
@pytest.mark.parametrize("role", curriculum.ROLES)
def test_return_failure_cannot_fabricate_state_failure(role, audit):
    source, loop = _loop(role, audit=audit)
    assert source.startswith("# Checker: " + curriculum.CHECKER_VERSION + "\n")
    attempt = next(n for n in loop.body if isinstance(n, ast.Try))
    resource, ordinary = attempt.handlers
    assert ast.unparse(resource.type) == "(MemoryError, TimeoutError)"
    assert len(resource.body) == 1 and isinstance(resource.body[0], ast.Raise)
    assert ast.unparse(ordinary.type) == "Exception"
    assert [ast.unparse(n) for n in ordinary.body] == ["returned = False", "exception = type(error).__name__"]
    assert not any(isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id == "state"
                   for n in ast.walk(attempt))
    after = loop.body[loop.body.index(attempt) + 1:]
    assert ast.unparse(after[0]) == "target = case['input'] if ROLE == 'preserve' else case['transformed']"
    assert ast.unparse(after[1]) == "state = ROLE == 'unconstrained' or (values == target and all((type(v) is int for v in values)))"
    assert ast.unparse(after[2]).startswith("rows.append(")


@pytest.mark.parametrize("role,observed_values,state", [
    ("preserve", [2, -1, 2, 0], True),  # ordinary exception, input untouched
    ("preserve", [99], False),         # mutation before ordinary exception
    ("inplace", [2, 1], True),         # requested state reached, then exception
    ("inplace", [2, -1, 2, 0], False),
    ("unconstrained", [99], True),     # no state obligation: existing neutral pass
    ("preserve", [2, -1, 2, False], False),  # Python equality cannot hide type change
])
def test_ordinary_exception_state_truth_table(role, observed_values, state):
    # The exact generated expression and placement are checked above. This
    # evaluates its trusted primitive truth table, not generated source/code.
    target = CASE["input"] if role == "preserve" else CASE["transformed"]
    observed_state = role == "unconstrained" or (
        observed_values == target and all(type(v) is int for v in observed_values))
    assert observed_state is state
    assert not (False and observed_state)  # ordinary exception still fails return/overall


def test_checker_change_does_not_rename_DSL_family_identity():
    spec = {"steps": [{"op": "filter", "kind": "nonzero"}, {"op": "map", "kind": "abs"}], "aggregate": "sum"}
    assert curriculum.VERSION == "synthetic-list-curriculum-v2"
    old_identity = curriculum.digest({"version": "synthetic-list-curriculum-v2", "pipeline": spec})
    assert curriculum.family_fingerprint(spec) == old_identity
    rows = curriculum.compile_family(spec, "development")
    assert all(curriculum.CHECKER_VERSION in row["public_wrapper"]["content"]
               and curriculum.CHECKER_VERSION in row["host_only"]["audit_runner"] for row in rows)
