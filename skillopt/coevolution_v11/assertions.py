"""V11 truthiness-aware scoring over V10's unchanged static assertion language.

Only a trusted child observes arbitrary returned objects. The host handles
closed-schema typed builtins or the child's uniform boolean observation, never
downloaded Python and never a live arbitrary object. Private predicates remain
here and are never sent to the child or model.
"""

from skillopt.coevolution_v10 import assertions as _legacy
from skillopt.coevolution_v10.codec import decode_value, encode_value

VERSION = "v11-native-assertions-truthiness-1"
UnsupportedAssertion = _legacy.UnsupportedAssertion


class ObservationUnavailable(ValueError):
    """A valid observation lacks the type information needed by its predicate."""


def compile_tests(test_list, setup_code=""):
    result = _legacy.compile_tests(test_list, setup_code)
    return {**result, "version": VERSION}


def _native(compiled):
    if type(compiled) is not dict or compiled.get("version") != VERSION:
        raise ValueError("A V11 compiled assertion task is required")
    return {**compiled, "version": _legacy.VERSION}


def _compiled_checks(compiled):
    return _legacy._compiled_checks(_native(compiled))


def evaluate_observations(compiled, observations):
    """Retain native predicates; untyped equality is unknown, not coerced.

    Truthiness can be scored even for otherwise unencodable library objects.
    Exceptions remain semantic failures except MemoryError, which is unknown.
    A transport/schema error raises ValueError and must never become a score.
    """
    checks = _compiled_checks(compiled)
    if type(observations) is not list or len(observations) != len(checks):
        raise ValueError("Observation cardinality must match all compiled assertions")
    converted = []
    unavailable = False
    for row, (operation, _expected) in zip(observations, checks):
        if type(row) is not dict or set(row) != {"value", "exception", "truthiness", "typed"}:
            raise ValueError("A V11 observation requires value, exception, truthiness and typed")
        if type(row["typed"]) is not bool:
            raise ValueError("Malformed typed flag")
        if row["exception"] is not None:
            if (not _legacy._name(row["exception"]) or row["value"] is not None
                    or row["truthiness"] is not None or row["typed"]):
                raise ValueError("Malformed candidate exception observation")
            unavailable |= row["exception"] == "MemoryError"
            converted.append({"value": None, "exception": row["exception"]})
            continue
        if type(row["truthiness"]) is not bool:
            raise ValueError("Malformed truthiness observation")
        if row["typed"]:
            value = decode_value(row["value"])
            if bool(value) is not row["truthiness"]:
                raise ValueError("Typed value and observed truthiness differ")
        elif row["value"] is not None:
            raise ValueError("Untyped observation cannot carry a typed value")
        if operation in ("truthy", "falsy"):
            value = encode_value(row["truthiness"])
        elif row["typed"]:
            value = row["value"]
        else:
            unavailable = True
            value = encode_value(None)  # Never scored when any required observation is unavailable.
        converted.append({"value": value, "exception": None})
    if unavailable:
        raise ObservationUnavailable("A required typed observation or resource-limited result is unavailable")
    result = _legacy.evaluate_observations(_native(compiled), converted)
    return {**result, "version": VERSION, "uniform_truthiness_observations": True}
