"""Synthetic static bridge tests; no reference/candidate program is executed."""
import ast
import json

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import natural_data as data
from skillopt.validator_pilot.api import digest


def row(identifier=0, *, example=">>> solve(3)\n    6", requirement="Return twice the integer."):
    return {"task_id": f"HumanEval/{identifier}", "entry_point": "solve",
            "prompt": 'def solve(x):\n    """' + requirement + '\n    ' + example + '\n    """\n',
            "canonical_solution": "    return x * 2  # HOST_REFERENCE_SENTINEL\n",
            "test": "def check(candidate):\n    assert candidate(4) == 8\n    assert candidate(97871) == 195742\n",
            "base_input": [[97871]], "plus_input": [[812391]],
            "contract": "    assert isinstance(x, int)  # HOST_CONTRACT_SENTINEL\n", "atol": 0}


def identity(source, partition="development"):
    return {"task_id": source["task_id"], "original_task_id": source["task_id"],
            "family_id": "fixture-family-" + source["task_id"], "source_row_hash": digest(source),
            "question_sha256": digest(source["prompt"]), "partition": partition,
            "source_split": "original_humaneval_test"}


@pytest.mark.parametrize("example", ["solve(3) == 6", "solve(3) => 6", "solve(3) -> 6",
                                    "solve(3) returns 6", "solve(3) should return 6",
                                    ">>> solve(3)\n    6"])
def test_only_literal_public_prompt_examples(example):
    source = row(example=example)
    cases = data.public_examples(source)
    assert len(cases) == 1
    assert json.loads(cases[0].arguments_json) == {"args": [3], "kwargs": {}}
    assert cases[0].expected_json == "6"
    assert cases[0].contract_quote in source["prompt"]


@pytest.mark.parametrize("example", ["solve(make_input()) == 6", "solve(3) == compute_expected()",
                                    "solve([1, 2]) == (1, 2)", "solve(3) == {1, 2}",
                                    "solve(**{'x': 3}) == 6", "solve(3) == 6 + 7",
                                    "solve(3) == 'abc'.upper()"])
def test_never_execute_or_coerce_public_expressions(example):
    assert not data.public_examples(row(example=example))


def test_prompt_only_projection_does_not_consult_hidden_source_fields():
    source = row()
    projected = data.public_examples({key: source[key] for key in ("prompt", "entry_point")})
    assert projected == data.public_examples(source)


@pytest.mark.parametrize("heading", ["Example:", "Examples:"])
def test_explicit_example_section_excludes_humaneval130_style_math_definitions(heading):
    source = {"entry_point": "tri", "prompt": (
        'def tri(n):\n    """Return the sequence through index n.\n'
        '    For example:\n    tri(2) = 2\n    tri(4) = 3\n\n'
        '    ' + heading + '\n    tri(3) = [1, 3, 2, 8]\n    """\n')}
    cases = data.public_examples(source)
    assert len(cases) == 1
    assert json.loads(cases[0].expected_json) == [1, 3, 2, 8]
    assert json.loads(cases[0].arguments_json) == {"args": [3], "kwargs": {}}


def test_explicit_example_section_stops_before_sibling_notes_and_keeps_doctests():
    source = row(example=(
        ">>> solve(3)\n    6\n\n    Examples:\n    solve(4) == 8\n\n"
        "    Notes:\n    solve(7) == 700\n\n    Example:\n    solve(5) == 10"))
    cases = data.public_examples(source)
    assert [json.loads(case.expected_json) for case in cases] == [6, 8, 10]


def test_native_fallback_discloses_one_exact_literal_assertion():
    source = row(example="An integer input is accepted.")
    prompt, cases, origin = data.public_projection(source)
    assert len(cases) == 1
    assert origin == {"kind": "disclosed_original_literal_assertion", "original_assertion_index": 0}
    assert "assert solve(4) == 8" in prompt
    assert "97871" not in prompt and "812391" not in prompt
    assert json.loads(cases[0].arguments_json) == {"args": [4], "kwargs": {}}


def test_public_task_calls_solution_directly_and_hides_audit_payload():
    source = row()
    result = data.materialize_row(source, identity(source))
    task = result["task"]
    assert (task.module, task.function) == ("solution", "solve")
    assert [o.kind for o in task.contract.obligations] == ["requested_behavior"]
    assert not task.relations
    visible = json.dumps(task.to_dict())
    for hidden in ("HOST_REFERENCE_SENTINEL", "HOST_CONTRACT_SENTINEL", "97871", "812391"):
        assert hidden not in visible
        assert hidden not in result["public_wrapper"]["content"]
    wrapped = result["public_task"]
    assert wrapped.contract == task.contract
    assert (wrapped.module, wrapped.function) == ("public_runner", "check")
    assert wrapped.public_cases[0].expected_json == "true"
    assert data.COMPARATOR_NOTE in wrapped.contract.prompt
    ast.parse(result["public_wrapper"]["content"])


def test_native_example_function_rename_does_not_change_string_literals():
    source = row(example="No prompt literal example.")
    source["test"] = "def check(candidate):\n    assert candidate('candidate') == 'candidate'\n"
    prompt, cases, _ = data.public_projection(source)
    assert "assert solve('candidate') == 'candidate'" in prompt
    assert json.loads(cases[0].expected_json) == "candidate"


def test_reference_self_calibration_builder_uses_only_original_reference():
    source = row()
    result = data.materialize_row(source, identity(source))
    files = data.build_audit_files(result, reference=True)
    assert files["solution.py"] == files["reference_solution.py"] == source["prompt"] + source["canonical_solution"]


def test_hidden_builder_retains_all_inputs_and_never_executes(monkeypatch):
    source = row()
    result = data.materialize_row(source, identity(source))
    # Inspect source AST, never run the code delivered to the sandbox.
    files = data.build_audit_files(result, "def solve(x):\n    raise RuntimeError('not executed')\n")
    assert set(files) == {"solution.py", "reference_solution.py", "hidden_audit.py"}
    tree = ast.parse(files["hidden_audit.py"])
    constants = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
                 if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)}
    assert constants["BASE"] == source["base_input"]
    assert constants["PLUS"] == source["plus_input"]
    assert constants["ENTRY"] == "solve"
    assert "base_pass" in files["hidden_audit.py"] and "unsupported_outputs" in files["hidden_audit.py"]
    assert "report[name + \"_unknown\"] += 1" in files["hidden_audit.py"]


def audit_ast():
    """Read the trusted wrapper's branch semantics without executing any code."""
    return next(node for node in ast.parse(data._AUDIT_PROGRAM).body
                if isinstance(node, ast.FunctionDef) and node.name == "audit")


def test_reference_and_candidate_import_failures_have_separate_audit_outcomes():
    load_reference, load_candidate = [node for node in audit_ast().body if isinstance(node, ast.Try)]
    reference_failure = ast.unparse(load_reference.handlers[0])
    candidate_failure = ast.unparse(load_candidate.handlers[0])
    assert "reference_module_or_entrypoint_unavailable" in reference_failure
    assert "report['base_unknown'] = len(BASE)" in reference_failure
    assert "report['status'] = 'fail'" not in reference_failure
    assert "candidate_module_or_entrypoint_unavailable" in candidate_failure
    assert "report['base_pass'] = report['plus_pass'] = False" in candidate_failure
    assert "report['status'] = 'fail'" in candidate_failure
    assert "report['base_observed'] = report['base_failed'] = len(BASE)" in candidate_failure


def test_invalid_reference_output_is_unknown_before_any_candidate_call():
    function = audit_ast()
    input_loop = next(node for node in ast.walk(function) if isinstance(node, ast.For)
                      and isinstance(node.target, ast.Name) and node.target.id == "arguments")
    reference_attempt, candidate_attempt = [node for node in input_loop.body if isinstance(node, ast.Try)]
    assert reference_attempt.lineno < candidate_attempt.lineno
    reference_body = ast.unparse(reference_attempt)
    assert "if not _plain(expected)" in reference_body
    assert "report['reference_unsupported_outputs'] += 1" in reference_body
    assert "report[name + '_unknown'] += 1" in reference_body
    assert "report[name + '_failed']" not in reference_body


def test_candidate_exception_and_unsupported_output_count_as_observed_failures():
    function = audit_ast()
    input_loop = next(node for node in ast.walk(function) if isinstance(node, ast.For)
                      and isinstance(node.target, ast.Name) and node.target.id == "arguments")
    candidate_attempt = [node for node in input_loop.body if isinstance(node, ast.Try)][1]
    failure_handler = ast.unparse(candidate_attempt.handlers[0])
    body = ast.unparse(candidate_attempt)
    assert "report['candidate_errors'] += 1" in failure_handler
    assert "report[name + '_failed'] += 1" in failure_handler
    assert "report[name + '_unknown']" not in body
    assert "report['candidate_unsupported_outputs'] += 1" in body
    observed_increment = next(node for node in input_loop.body if isinstance(node, ast.AugAssign)
                              and ast.unparse(node.target) == "report[name + '_observed']")
    assert observed_increment.lineno < candidate_attempt.lineno


def test_static_eligibility_rejects_special_oracle_and_native_tuple_return():
    assert data.compatibility(row(32))["reason"] == "special_oracle"
    source = row()
    source["canonical_solution"] = "    return (x, x)\n"
    assert data.compatibility(source)["reason"] == "native_non_json_return"


def test_static_eligibility_rejects_missing_public_checks():
    source = row(example="No public literal example.")
    source["test"] = "def check(candidate):\n    assert candidate(generate_input()) == answer()\n"
    assert data.compatibility(source)["reason"] == "no_supported_public_example"


def test_frozen_source_row_change_rejected():
    source = row()
    with pytest.raises(ValueError, match="source row changed"):
        data.materialize_row({**source, "atol": 1e-6}, identity(source))


def diverse_rows():
    requirements = ("Count letters in a string.", "Find the median element in a sequence.",
                    "Compare two arbitrary precision integers.", "Determine whether a graph is connected.",
                    "Reverse the decimal digits.", "Calculate the distance from a point to the origin.")
    return [row(i, requirement=requirement) for i, requirement in enumerate(requirements)]


def test_family_exposure_closure_and_disjoint_deterministic_selection():
    rows = diverse_rows()
    duplicate = {**rows[0], "task_id": "HumanEval/100"}
    inventory = {"excluded_ids": [rows[0]["task_id"]]}
    counts = dict.fromkeys(data.PARTITIONS, 1)
    selected, _, _ = data.select([*rows, duplicate], inventory, counts=counts)
    reverse, _, _ = data.select([duplicate, *reversed(rows)], inventory, counts=counts)
    assert selected == reverse
    identities = [r for group in selected.values() for r in group]
    assert len({r["family_id"] for r in identities}) == len(identities) == 4
    assert not {"HumanEval/0", "HumanEval/100"} & {r["task_id"] for r in identities}


def test_insufficient_population_cannot_silently_lower_protocol_counts():
    with pytest.raises(ValueError, match="136|Positive counts"):
        data.select(diverse_rows(), {"excluded_ids": []})


def test_prepare_is_immutable_and_resumes_without_new_history_scan(tmp_path, monkeypatch):
    source_rows = diverse_rows()
    source = seal({"version": "fixture", "rows": len(source_rows)})
    monkeypatch.setattr(data, "download", lambda repo: (source_rows, source))
    monkeypatch.setattr(data, "_history", lambda *args: seal({"excluded_ids": [], "files": []}))
    output = tmp_path / "outputs/skill_validation/natural"
    counts = dict.fromkeys(data.PARTITIONS, 1)
    manifest = data.prepare(tmp_path, output, counts=counts)
    monkeypatch.setattr(data, "_history", lambda *args: pytest.fail("Resume rescanned new outputs"))
    assert data.prepare(tmp_path, output, counts=counts) == manifest
    loaded = data.load_tasks(tmp_path, manifest, "development")
    assert len(loaded) == 1 and loaded[0]["task"].contract.partition == "development"
    public_manifest = (output / "data_manifest.json").read_text()
    assert "HOST_REFERENCE_SENTINEL" not in public_manifest
    assert "812391" not in public_manifest
    with pytest.raises(ValueError, match="settings changed"):
        data.prepare(tmp_path, output, counts=counts, seed=17)


def test_source_download_hash_tampering_is_rejected_without_network(tmp_path):
    path = tmp_path / data.DIRECTORY / "HumanEvalPlus.jsonl.gz"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not the pinned release")
    with pytest.raises(ValueError, match="asset changed"):
        data.download(tmp_path)


def test_load_requires_actual_frozen_manifest(tmp_path):
    manifest = seal({"version": data.VERSION, "run_path": "outputs/skill_validation/absent"})
    with pytest.raises(FileNotFoundError):
        data.load_tasks(tmp_path, manifest, "final")
