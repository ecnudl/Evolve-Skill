"""V11 trusted child: uniform typed and truthiness observations, no private checks.

The candidate module gets a separate global namespace, never these globals.
Expected values are absent. This is deliberately a restricted Python subset.
"""

import bisect as _bisect
import builtins as _builtins
import collections as _collections
import functools as _functools
import heapq as _heapq
import itertools as _itertools
import json
import math as _math
import re as _re
import resource as _resource
import string as _string
import sys as _sys
import types as _types
import typing as _typing

VERSION = "v11-uniform-child-observations-v1"

IMPORT_MEMBERS = {
    "math": tuple(name for name in dir(_math) if not name.startswith("_")),
    "collections": ("Counter", "defaultdict", "deque", "OrderedDict"),
    "itertools": (
        "accumulate", "chain", "combinations", "combinations_with_replacement",
        "compress", "count", "cycle", "dropwhile", "filterfalse", "groupby",
        "islice", "pairwise", "permutations", "product", "repeat", "starmap",
        "takewhile", "tee", "zip_longest",
    ),
    "typing": (
        "Any", "List", "Dict", "Tuple", "Set", "FrozenSet", "Optional", "Union",
        "Iterable", "Iterator", "Sequence", "Mapping", "MutableMapping", "Callable",
    ),
    "heapq": (
        "heapify", "heappop", "heappush", "heappushpop", "heapreplace", "merge",
        "nlargest", "nsmallest",
    ),
    "bisect": ("bisect", "bisect_left", "bisect_right", "insort", "insort_left", "insort_right"),
    "functools": ("reduce", "cmp_to_key"),
    "re": (
        "match", "fullmatch", "search", "sub", "subn", "split", "findall", "finditer",
        "compile", "escape", "IGNORECASE", "MULTILINE", "DOTALL", "ASCII", "VERBOSE",
    ),
    "string": (
        "ascii_letters", "ascii_lowercase", "ascii_uppercase", "digits", "hexdigits",
        "octdigits", "punctuation", "printable", "whitespace",
    ),
}
AVAILABLE_BUILTINS = (
    "abs", "all", "any", "bin", "bool", "callable", "chr", "dict", "divmod",
    "enumerate", "filter", "float", "format", "frozenset", "hex", "int", "isinstance",
    "issubclass", "iter", "len", "list", "map", "max", "min", "next", "oct", "ord",
    "pow", "range", "repr", "reversed", "round", "set", "slice", "sorted", "str",
    "sum", "tuple", "zip", "Exception", "ValueError", "TypeError", "KeyError",
    "IndexError", "RuntimeError", "ZeroDivisionError", "StopIteration", "AssertionError",
    "PermissionError", "OverflowError", "ArithmeticError", "LookupError", "NameError",
)
_MODULES = {
    "math": _math, "collections": _collections, "itertools": _itertools,
    "typing": _typing, "heapq": _heapq, "bisect": _bisect,
    "functools": _functools, "re": _re, "string": _string,
}


def _fresh_builtins():
    proxies = {
        name: _types.SimpleNamespace(**{
            member: getattr(_MODULES[name], member)
            for member in members if hasattr(_MODULES[name], member)
        })
        for name, members in IMPORT_MEMBERS.items()
    }

    def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
        if level or name not in proxies:
            raise ImportError("module not allowlisted")
        if any(member not in IMPORT_MEMBERS[name] for member in (fromlist or ())):
            raise ImportError("member not allowlisted")
        return proxies[name]

    result = {name: getattr(_builtins, name) for name in AVAILABLE_BUILTINS}
    result["__import__"] = safe_import
    result["print"] = lambda *args, **kwargs: None
    return result


def _main(encode_value, decode_value):
    _resource.setrlimit(_resource.RLIMIT_CPU, (5, 5))
    _resource.setrlimit(_resource.RLIMIT_FSIZE, (0, 0))
    _resource.setrlimit(_resource.RLIMIT_NOFILE, (32, 32))
    payload = json.load(_sys.stdin)
    code = compile(payload["code"], "candidate.py", "exec")
    rows = []
    for case in payload["cases"]:
        environment = {"__builtins__": _fresh_builtins(), "__name__": "candidate"}
        try:
            exec(code, environment, environment)
            args = [decode_value(value) for value in case["args"]]
            kwargs = {key: decode_value(value) for key, value in case["kwargs"].items()}
            function = environment[payload["entry_point"]]
            if not isinstance(function, _types.FunctionType):
                raise TypeError("declared entry point is not a Python function")
            value = function(*args, **kwargs)
            truthiness = _builtins.bool(value)
        except Exception as error:
            rows.append({"value": None, "exception": type(error).__name__, "truthiness": None, "typed": False})
        else:
            try:
                encoded = encode_value(value)
            except (ValueError, TypeError, OverflowError, RecursionError):
                rows.append({"value": None, "exception": None, "truthiness": truthiness, "typed": False})
            else:
                rows.append({"value": encoded, "exception": None, "truthiness": truthiness, "typed": True})
    encoded = json.dumps({"observations": rows}, allow_nan=False)
    if len(encoded.encode("utf-8")) > 250000:
        raise ValueError("output exceeds transport bound")
    _sys.stdout.write(encoded)


if __name__ == "__main__":
    # codec.py definitions precede this trusted file in executor.CHILD_RUNNER.
    _main(encode_value, decode_value)  # noqa: F821
