"""BigCodeBench execution-evidence ablation: sanitizer and wiring controls, not method effects."""
import json
from copy import deepcopy

import pytest

from skillopt.continual_learning.contracts import BUDGET_VERSION, HARDENED_VERSION, manifest
from skillopt.continual_learning.execution_evidence import PROFILE, render, sanitize
from skillopt.continual_learning.feedback import PROFILE as SCALAR
from skillopt.continual_learning.feedback import project
from skillopt.continual_learning.recovery import POLICY_V6, POLICY_V7
from skillopt.continual_learning.skillopt import run_stage
from tests.test_continual_learning_budget_v7 import API
from tests.test_continual_learning_domains import setup

CODE = "import pandas as pd\n\ndef task_func(df):\n    total = df['col'].sum()\n    return total\n"
SECRET = "secret_column_42"


def frame(path, line, name="f"):
    return f'  File "{path}", line {line}, in {name}\n    hidden_source_line({SECRET!r})\n'


def tb(*frames, last=f"KeyError: '{SECRET}'", tail="Expected 1234 but got 99"):
    return "Traceback (most recent call last):\n" + "".join(frames) + last + "\n" + tail + "\n"


TEST = "/tmp/x/__test__.py"


@pytest.mark.parametrize("details,expected", [
    ({"test_case_1": tb(frame(TEST, 20, "test_case_1"), frame(TEST, 4, "task_func"))},
     {"exception": "KeyError", "locus": "candidate_code", "candidate_line": 4,
      "candidate_source": "total = df['col'].sum()"}),
    ({"test_case_1": tb(frame(TEST, 20, "test_case_1"), last=f"AssertionError: {SECRET} != 7")},
     {"exception": "AssertionError", "locus": "hidden_test_assertion"}),
    ({"test_case_1": tb(frame(TEST, 20, "test_case_1"), frame(TEST, 4, "task_func"),
                        frame("/usr/lib/python3/pandas/core.py", 99), last=f"ValueError: {SECRET}")},
     {"exception": "ValueError", "locus": "library_called_from_candidate", "candidate_line": 4,
      "candidate_source": "total = df['col'].sum()"}),
    ({"test_case_1": tb(frame(TEST, 20, "test_case_1"), frame("/usr/lib/python3/pandas/testing.py", 7),
                        last="AssertionError: DataFrame shape mismatch")},
     {"exception": "AssertionError", "locus": "library_called_from_hidden_test"}),
    # Non-builtin names are not copied: they could be hidden values shaped like a class.
    ({"test_case_1": tb(frame(TEST, 21, "test_case_1"), last=f"urllib.error.URLError: <urlopen {SECRET}>")},
     {"exception": "NonBuiltinException", "locus": "hidden_test_code"}),
    # Control characters inside a message must not split it into a fake exception line.
    ({"test_case_1": tb(frame(TEST, 20, "test_case_1"), last=f"SyntaxError: x = \x0b{SECRET}\x0bHIDDEN")},
     {"exception": "SyntaxError", "locus": "hidden_test_code"}),
    # Frame-less SyntaxError locations (no ", in <name>") still point at the candidate line.
    ({"test_case_1": "Traceback (most recent call last):\n" + frame(TEST, 20, "test_case_1")
      + '  File "__test__.py", line 4\n    total = df[\n          ^\nSyntaxError: invalid syntax\n'},
     {"exception": "SyntaxError", "locus": "candidate_code", "candidate_line": 4,
      "candidate_source": "total = df['col'].sum()"}),
    # A chained failure is attributed to its terminal block, not the earlier cause.
    ({"test_case_1": tb(frame(TEST, 20, "test_case_1"), frame(TEST, 4, "task_func"))
      + "\nDuring handling of the above exception, another exception occurred:\n\n"
      + tb(frame(TEST, 22, "test_case_1"), last=f"AssertionError: {SECRET}")},
     {"exception": "AssertionError", "locus": "hidden_test_assertion"}),
    # Library files that merely end with the combined name are not the combined file.
    ({"test_case_1": tb(frame("/usr/lib/not__test__.py", 3), last="TypeError: bad")},
     {"exception": "TypeError", "locus": "unknown"}),
])
def test_sanitizer_keeps_structure_and_drops_hidden_text(details, expected):
    evidence = sanitize(CODE, details)
    assert evidence["status"] == "available" and evidence["failing_cases"] == 1
    assert evidence["cases"] == [expected]
    text = render(evidence) + json.dumps(evidence)
    for hidden in (SECRET, "1234", "hidden_source_line", "Expected", "shape mismatch", "urlopen"):
        assert hidden not in text


def test_unparsed_or_module_level_diagnostics_are_not_evidence():
    # The checker stores raw module-level messages (str(e)) under ALL; never parse or count them.
    module = sanitize(CODE, {"ALL": tb(frame(TEST, 4, "task_func"))})
    assert module["status"] == "unavailable" and module["failing_cases"] == 0 and module["non_test_entries"] == 1
    timeout = sanitize(CODE, {"test_case_1": "Timeout"})
    assert timeout["status"] == "unavailable" and timeout["cases"] == [{"exception": "unparsed", "locus": "unknown"}]
    assert render(module) == render(timeout) == "Sanitized execution evidence unavailable."


def test_sanitizer_is_bounded_and_deterministic():
    details = {f"test_case_{i:02d}": tb(frame(TEST, 20 + i), last="AssertionError") for i in range(10)}
    evidence = sanitize(CODE, details)
    assert evidence["failing_cases"] == 10 and len(evidence["cases"]) == 8
    assert render(evidence).endswith("2 more omitted.") and sanitize(CODE, dict(reversed(details.items()))) == evidence
    assert sanitize(CODE, None)["status"] == "unavailable" and sanitize(None, {})["status"] == "unavailable"


def test_the_case_bound_never_hides_parsed_evidence():
    # Unparsed failures sorting first must not crowd out the one parsed case.
    details = {f"test_a_{i:02d}": "Timeout" for i in range(10)}
    details["test_z"] = tb(frame(TEST, 20, "test_z"), frame(TEST, 4, "task_func"))
    evidence = sanitize(CODE, details)
    assert evidence["status"] == "available" and evidence["parsed_cases"] == 1 and len(evidence["cases"]) == 8
    assert evidence["cases"][0]["locus"] == "candidate_code" and render(evidence).endswith("3 more omitted.")


def auth(version=BUDGET_VERSION, policy=POLICY_V7, *, benchmark="bigcodebench", method="skillopt", profile=PROFILE):
    _, panel, args = setup(benchmark, method=method)
    args.update(version=version, recovery_policy=deepcopy(policy))
    args["model"]["transport"]["stream_wall_seconds"] = 3600
    return manifest(panel, **args, feedback_profile=profile), panel


def test_profile_is_a_v7_bigcodebench_skillopt_ablation_only():
    value, _ = auth()
    assert value["feedback_profile"] == PROFILE
    assert auth(profile=None)[0]["feedback_profile"] == SCALAR
    for kwargs in ({"version": HARDENED_VERSION, "policy": POLICY_V6}, {"benchmark": "searchqa"}, {"method": "gepa"}):
        with pytest.raises(ValueError, match="ablation only"):
            auth(**kwargs)


@pytest.mark.parametrize("field,value", [("version", HARDENED_VERSION), ("method", "gepa"), ("benchmark", "searchqa")])
def test_direct_projection_cannot_bypass_the_profile_gate(field, value):
    good, panel = auth()
    failed = {"status": "fail", "score": 0.0, "metrics": {"details": {}}}
    with pytest.raises(ValueError, match="ablation only"):
        project({**good, field: value}, panel["tasks"][0]["public"], {"status": "available", "output": CODE}, failed)


def test_projection_adds_evidence_only_to_failed_executions_under_the_profile():
    value, panel = auth()
    public = panel["tasks"][0]["public"]
    details = {"test_case_1": tb(frame(TEST, 20, "test_case_1"), frame(TEST, 4, "task_func"))}
    failed = {"status": "fail", "score": 0.0, "metrics": {"details": details}}
    prediction = {"status": "available", "output": CODE}
    trace = project(value, public, prediction, failed)
    assert trace["Feedback"]["execution_evidence"]["cases"][0]["locus"] == "candidate_code"
    assert "execution_evidence" not in project(value, public, prediction, {"status": "pass", "score": 1.0})["Feedback"]
    scalar, _ = auth(profile=None)
    assert set(project(scalar, public, prediction, failed)["Feedback"]) == {"status", "score"}


def test_native_reflection_sees_sanitized_evidence_in_the_checker_message(tmp_path):
    value, panel = auth()
    details = {"test_case_1": tb(frame(TEST, 20, "test_case_1"), frame(TEST, 1, "task_func"))}

    def evaluate(task, skill):
        passed = "requested constant" in skill
        return ({"status": "available", "output": CODE, "reason": "fixture"},
                {"status": "pass" if passed else "fail", "score": float(passed), "reason": "fixture",
                 "metrics": {} if passed else {"details": details}})

    result = run_stage(value, panel, tmp_path, fixture_api=API(), fixture_evaluate=evaluate)
    assert result["status"] == "completed", result
    messages = [json.loads(p.read_text())[-1]["content"]
                for p in sorted((tmp_path / "native/0/predictions").glob("*/conversation.json"))]
    assert messages and all("Sanitized execution evidence" in m and "import pandas as pd" in m for m in messages)
    assert not any(SECRET in m or "1234" in m for m in messages)
