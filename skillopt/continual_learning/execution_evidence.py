"""Sanitized development execution evidence for the v7 BigCodeBench feedback ablation.

Input: the candidate's own code and the official checker's per-test tracebacks
(``untrusted_check`` runs ``code + test`` as one ``__test__.py``). Output: per
failing test only a fixed-vocabulary exception class, where the terminal failure
surfaced (the candidate's code, a hidden-test assertion or hidden-test code, or
a library reached from either) and the candidate's own source line. No text of
the traceback itself is copied: hidden test code, exception messages, values and
non-builtin exception names are dropped, and ambiguous structure fails closed.
This is a host development diagnostic, not a public verifier check.
"""
from __future__ import annotations

import builtins
import re
from pathlib import PurePosixPath

PROFILE = "bcb-execution-evidence-v1"
MAX_CASES = 8
MAX_SOURCE_CHARS = 200
COMBINED_FILE = "__test__.py"
_START = "Traceback (most recent call last):"
# CPython frame lines; SyntaxError frames have no ", in <name>" part.
_FRAME = re.compile(r'^  File "([^"]+)", line ([1-9][0-9]*)(?:, in .+)?$')
_EXCEPTION = re.compile(r"^([A-Za-z_][\w.]*)(?::|$)")
_BUILTIN = frozenset(name for name, value in vars(builtins).items()
                     if isinstance(value, type) and issubclass(value, BaseException))
_UNAVAILABLE = {"exception": "unparsed", "locus": "unknown"}


def _case(code_lines, key, traceback):
    # Raw module-level messages (str(e)) arrive under non-test keys such as ALL.
    if type(key) is not str or not key.startswith("test") or type(traceback) is not str:
        return dict(_UNAVAILABLE)
    # Only real newlines: str.splitlines() would also split on \x0b and similar.
    lines = traceback.split("\n")
    starts = [i for i, line in enumerate(lines) if line == _START]
    if not starts:
        return dict(_UNAVAILABLE)
    frames, exception = [], None
    for line in lines[starts[-1] + 1:]:  # terminal block of a chained failure
        frame = _FRAME.match(line)
        if frame:
            frames.append((PurePosixPath(frame.group(1)).name, int(frame.group(2))))
        elif frames and not line.startswith(" "):
            match = _EXCEPTION.match(line)
            if not match:
                return dict(_UNAVAILABLE)
            name = match.group(1).rsplit(".", 1)[-1]
            exception = name if name in _BUILTIN else "NonBuiltinException"
            break
    if not frames or exception is None:
        return dict(_UNAVAILABLE)
    combined = [line for name, line in frames if name == COMBINED_FILE]
    library_last = frames[-1][0] != COMBINED_FILE
    entry = {"exception": exception}
    if not combined:
        entry["locus"] = "unknown"
    elif combined[-1] <= len(code_lines):
        entry["locus"] = "library_called_from_candidate" if library_last else "candidate_code"
        entry["candidate_line"] = combined[-1]
        entry["candidate_source"] = code_lines[combined[-1] - 1].strip()[:MAX_SOURCE_CHARS]
    elif library_last:
        entry["locus"] = "library_called_from_hidden_test"
    else:
        entry["locus"] = "hidden_test_assertion" if exception == "AssertionError" else "hidden_test_code"
    return entry


def sanitize(code, details):
    """Bounded structural evidence for one failed development execution.

    Only per-test entries count as failing cases; evidence is available only when
    at least one of them parsed, so unparsed diagnostics never inflate coverage.
    Parsed cases are kept first, so the case bound never hides the evidence.
    """
    if type(code) is not str or type(details) is not dict:
        return {"profile": PROFILE, "failing_cases": 0, "parsed_cases": 0, "non_test_entries": 0,
                "cases": [], "status": "unavailable"}
    lines = code.split("\n")
    tests = sorted(key for key in details if type(key) is str and key.startswith("test"))
    cases = [_case(lines, key, details[key]) for key in tests]
    parsed = [case for case in cases if case["exception"] != "unparsed"]
    kept = (parsed + [case for case in cases if case["exception"] == "unparsed"])[:MAX_CASES]
    return {"profile": PROFILE, "failing_cases": len(cases), "parsed_cases": len(parsed),
            "non_test_entries": len(details) - len(tests), "cases": kept,
            "status": "available" if parsed else "unavailable"}


_WHERE = {"candidate_code": "raised in your code", "library_called_from_candidate": "raised in a library your code called",
          "hidden_test_assertion": "a hidden-test assertion failed", "hidden_test_code": "raised in hidden-test code",
          "library_called_from_hidden_test": "raised in a library the hidden test called",
          "unknown": "location unknown"}


def render(evidence):
    """One reflection-ready line: fixed vocabulary plus the candidate's own source lines."""
    if evidence["status"] != "available":
        return "Sanitized execution evidence unavailable."
    parts = []
    for index, case in enumerate(evidence["cases"], 1):
        text = f"[{index}] {case['exception']}: {_WHERE[case['locus']]}"
        if "candidate_line" in case:
            text += f" at line {case['candidate_line']}: `{case['candidate_source']}`"
        parts.append(text)
    omitted = evidence["failing_cases"] - len(evidence["cases"])
    return ("Sanitized execution evidence (no hidden test inputs, messages or expected values): "
            f"{evidence['failing_cases']} failing hidden test case(s). " + "; ".join(parts)
            + (f"; {omitted} more omitted." if omitted else "."))
