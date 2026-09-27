"""Deterministic synthetic panels; fixtures never execute submitted Python."""
import ast
import hashlib
import json
from copy import deepcopy

import pytest

from skillopt.coevolution_v5.core import seal, verify
from skillopt.skill_validation import curriculum_tasks as curriculum
from skillopt.skill_validation import mechanism_tasks as tasks
from skillopt.skill_validation.models import ArtifactRecord, SourceFile
from skillopt.skill_validation.public_revision import _parts
from skillopt.validator_pilot.api import digest


SEED = 20260925


class FixtureExecutor:
    """Fabricated execution receipts, explicitly not real qualification."""
    identity = {"fixture_executor": "mechanism-tasks", "real_execution": False}

    def __init__(self, *, unavailable=False, rejected=False, returns=True, malformed=False):
        self.calls = 0
        self.unavailable, self.rejected = unavailable, rejected
        self.returns, self.malformed = returns, malformed
        self.requests = []

    @staticmethod
    def _case_count(source):
        # Read host-owned literal data, not code execution or candidate output.
        tree = ast.parse(source)
        node = next(node for node in tree.body if isinstance(node, ast.Assign)
                    and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "CASES")
        return len(ast.literal_eval(node.value))

    def run(self, files, module, function, args, kwargs):
        self.calls += 1
        self.requests.append({"files": files, "module": module, "function": function})
        if module == "screen" and "audit_check.py" in files:
            count = self._case_count(files["audit_check.py"])
            actual = {"references_pass": not self.rejected, "public_wrappers_pass": True,
                      "wrong_return_detected": True, "audit_cases": count,
                      "reference_case_comparisons": 2 * count}
        elif module == "screen":
            count = self._case_count(files["screen.py"])
            actual = {"reference_agreement": not self.rejected, "contract_states_valid": True,
                      "wrong_return_detected": True, "wrong_state_detected": True,
                      "nonconstant_return": True, "public_wrappers_valid": True,
                      "public_mutants_detected": True, "comparisons": count * 3,
                      "inputs": count, "roles": 3}
        else:
            count = self._case_count(files["hidden_audit.py"])
            actual = {"cases": [{"return_pass": self.returns, "state_pass": True, "exception": None}
                                for _ in range(count)]}
        if self.malformed:
            actual = {"malformed": True}
        call = {"module": module, "function": function, "args": args, "kwargs": kwargs}
        return seal({"status": "unsupported" if self.unavailable else "observed", "actual": actual,
                     "exception": None, "executor_identity": self.identity,
                     "input_hash": digest({"files": files, **call}), "source_hash": digest(files),
                     "call_hash": digest(call), "fixture_only": True})


def artifact(row, *, unavailable=False):
    return ArtifactRecord(row["task"].contract.content_hash, 0, "no_skill", "none",
        hashlib.sha256(b"").hexdigest(), () if unavailable else (SourceFile("solution.py", "# fixture, never executed"),),
        "parse_failure" if unavailable else "available", "fixture", True, False, "fixture:mechanism", digest("fixture"))


@pytest.fixture(scope="module")
def panel():
    return tasks.build_panel(SEED)


def test_default_counts_deterministic_selection_and_explicit_limits(panel):
    assert panel["manifest"] == tasks.build_panel(SEED)["manifest"]
    assert {key: len(panel[key]) for key in ("development", "confirmation")} == {"development": 30, "confirmation": 78}
    manifest = verify(panel["manifest"])
    assert manifest["counts"]["development"]["regions"] == {
        "target_related": 8, "near_miss": 8, "boundary_control": 8, "unrelated": 6}
    assert manifest["counts"]["confirmation"]["regions"] == {
        "target_related": 24, "near_miss": 24, "boundary_control": 24, "unrelated": 6}
    assert manifest["all_tasks_frozen_before_solver"] is True
    assert manifest["source_type"] == tasks.ORIGIN
    for key in ("deployment_authorized", "statistical_noninferiority_established", "cross_domain_evaluated"):
        assert manifest[key] is False
    assert "finite-behavior" in " ".join(manifest["limitations"])
    assert tasks.build_panel(SEED + 1)["manifest"] != manifest


@pytest.mark.parametrize("seed,dev,confirm", [(True, 8, 24), (-1, 8, 24), (2**64, 8, 24),
    (1, True, 24), (1, 0, 24), (1, 8, 65), (1, 8, 0)])
def test_invalid_seed_or_budget_rejected(seed, dev, confirm):
    with pytest.raises(ValueError):
        tasks.build_panel(seed, dev, confirm)


def test_family_and_finite_behavior_disjointness_and_role_clustering(panel):
    manifest = panel["manifest"]
    for field in ("structural_hash", "finite_behavior_hash"):
        dev = {r[field] for r in manifest["related"]["development"]}
        confirm = {r[field] for r in manifest["related"]["confirmation"]}
        assert len(dev) == 8 and len(confirm) == 24 and not dev & confirm
    for part in ("development", "confirmation"):
        related = [r for r in panel[part] if r["task_kind"] == "list_pipeline"]
        for family in {r["family_id"] for r in related}:
            rows = [r for r in related if r["family_id"] == family]
            assert len(rows) == 3
            assert {r["region"] for r in rows} == {"target_related", "near_miss", "boundary_control"}
        assert all(r["task"].contract.domain == "coding" for r in panel[part])
        for row in related:
            assert row["region"] == tasks.REGIONS[row["host_only"]["role"]]
            kinds = {o.kind for o in row["task"].contract.obligations}
            assert ("input_preservation" in kinds) == (row["region"] == "target_related")
    assert not set(manifest["unrelated_catalog_ids"]["development"]) & set(manifest["unrelated_catalog_ids"]["confirmation"])
    assert set(sum(manifest["unrelated_catalog_ids"].values(), [])) == set(tasks.UNRELATED)


def test_role_observable_aliases_do_not_use_unrequired_intermediate_states():
    # A v1 cross-partition overlap: both count the nonzero input elements.
    # The required in-place transformations differ, but preserve/unconstrained
    # are observational aliases. No model output or confirmation score is used.
    a = {"steps": [{"op": "filter", "kind": "nonzero"}, {"op": "map", "kind": "abs"},
                   {"op": "reorder", "kind": "descending"}], "aggregate": "count"}
    b = deepcopy(a)
    b["steps"][1]["kind"] = "square"
    assert curriculum.behavior_fingerprint(a) != curriculum.behavior_fingerprint(b)
    left, right = tasks.role_behavior_fingerprints(a), tasks.role_behavior_fingerprints(b)
    assert left["preserve"] == right["preserve"]
    assert left["unconstrained"] == right["unconstrained"]
    assert left["inplace"] != right["inplace"]
    assert len(set(left.values())) == 3  # Opposite obligations remain separate roles.


@pytest.mark.parametrize("development,confirmation", [(8, 24), (12, 32), (64, 64)])
def test_v2_panel_role_observable_disjointness_at_default_and_budget_maxima(development, confirmation):
    panel = tasks.build_panel(SEED, development, confirmation)
    manifest = panel["manifest"]
    assert manifest["version"] == "deterministic-mechanism-panel-v2"
    assert manifest["semantic_family_independence_certified"] is False
    assert "same_role_observable" in manifest["alias_screen"]
    all_entries = manifest["related"]["development"] + manifest["related"]["confirmation"]
    for role in tasks.REGIONS:
        signatures = [tasks.role_behavior_fingerprints(row["spec"])[role] for row in all_entries]
        assert len(signatures) == len(set(signatures)) == development + confirmation
        assert signatures == [row["role_behavior_hashes"][role] for row in all_entries]
    assert len(panel["development"]) == 3 * development + 6
    assert len(panel["confirmation"]) == 3 * confirmation + 6


def test_role_observable_signature_validates_specs_and_returns_fresh_mapping():
    spec = json.loads(tasks._catalog()[0][2])
    first = tasks.role_behavior_fingerprints(spec)
    first["preserve"] = "tampered"
    assert tasks.role_behavior_fingerprints(spec)["preserve"] != "tampered"
    with pytest.raises(ValueError):
        tasks.role_behavior_fingerprints({**spec, "hidden_expected": 1})


def test_catalog_excludes_constant_or_identity_families_before_solver():
    entries = tasks._catalog()
    assert len({r[0] for r in entries}) == len({r[1] for r in entries}) == len(entries)
    for _, behavior, raw in entries:
        spec = json.loads(raw)
        results = [curriculum._evaluate(spec, values) for values in curriculum._audit_inputs()]
        assert len({r[0] for r in results}) > 1
        assert any(r[1] != values for r, values in zip(results, curriculum._audit_inputs()))
        assert behavior == curriculum.behavior_fingerprint(spec)


def test_serialization_roundtrip_is_detached_and_public_protocol_compatible(panel):
    for row in panel["development"] + panel["confirmation"]:
        raw = tasks.serialize_row(row)
        decoded = tasks.deserialize_row(json.loads(json.dumps(raw)))
        assert decoded == row
        task, public, wrapper = _parts(decoded)
        assert task.contract == public.contract
        assert wrapper.path == "public_runner.py"
        assert "reference_a" not in json.dumps(task.to_dict())
        assert "audit_runner" not in json.dumps(public.to_dict())
        assert decoded["host_only"] is not row["host_only"]
    row = tasks._unrelated("prime_integer", "development")
    row["host_only"]["reference_a"] = "changed"
    assert tasks._unrelated("prime_integer", "development")["host_only"]["reference_a"] != "changed"


@pytest.mark.parametrize("changed", ["region", "family_id", "family_origin", "audit_runner", "expected", "reference"])
def test_row_changes_rejected_before_executor(changed, tmp_path):
    row = tasks._unrelated("prime_integer", "development")
    if changed in {"region", "family_id", "family_origin"}:
        row[changed] = "tampered"
    elif changed == "expected":
        row["host_only"]["audit_cases"][0]["expected"] = True
    elif changed == "reference":
        row["host_only"]["reference_a"] += "# edit\n"
    else:
        row["host_only"][changed] += "# edit\n"
    executor = FixtureExecutor()
    with pytest.raises(ValueError):
        tasks.qualify_row(row, executor, tmp_path)
    assert executor.calls == 0
    with pytest.raises(ValueError):
        tasks.deserialize_row(tasks.serialize_row(row))


@pytest.mark.parametrize("name,args,expected", [
    ("balanced_parentheses", ["(())"], True), ("balanced_parentheses", [")("], False),
    ("run_length_encoding", ["aabccbaa"], [["a", 2], ["b", 1], ["c", 2], ["b", 1], ["a", 2]]),
    ("wildcard_matching", ["", "***"], True), ("wildcard_matching", ["abab", "?a*"], False),
    ("key_value_parsing", ["c=9;a=0;c=1;b=2"], {"a": 0, "b": 2, "c": 1}),
    ("directed_reachability", [1, [], 0, 0], True),
    ("directed_reachability", [3, [[0, 1], [1, 2]], 2, 0], False),
    ("undirected_components", [4, [[0, 1], [1, 2], [1, 2], [3, 3]]], 2),
    ("directed_cycle", [1, [[0, 0]]], True), ("directed_cycle", [1, []], False),
    ("coprime_integers", [0, 0], False), ("coprime_integers", [-5, 12], True),
    ("prime_integer", [-1], False), ("prime_integer", [49], False), ("prime_integer", [61], True),
    ("binary_addition", ["1111", "1111"], "11110"), ("binary_addition", ["0", "0"], "0"),
    ("base_conversion", [255, 7], "513"), ("base_conversion", [0, 2], "0"),
    ("interval_union", [[[0, 0], [1, 1]]], [[0, 0], [1, 1]]),
    ("interval_union", [[[2, 3], [-3, -1], [-1, 2]]], [[-3, 3]]),
])
def test_trusted_oracles_against_hand_checked_cases(name, args, expected):
    actual = tasks._oracle(name, args)
    assert type(actual) is type(expected) and actual == expected


@pytest.mark.parametrize("name", tasks.UNRELATED)
def test_unrelated_sources_parse_no_host_execution_and_cases_bound(name):
    row = tasks._unrelated(name, "development")
    host = row["host_only"]
    assert host["no_state_preservation_requirement"] is True
    assert {o.kind for o in row["task"].contract.obligations} == {"requested_behavior"}
    assert host["reference_a"] != host["reference_b"]
    for text in (host["reference_a"], host["reference_b"], host["audit_runner"], row["public_wrapper"]["content"]):
        ast.parse(text)
    assert len(host["audit_cases"]) == len({digest(case["args"]) for case in host["audit_cases"]})
    assert len({digest(case["expected"]) for case in host["audit_cases"]}) > 1
    assert len(row["task"].public_cases) == 4
    assert FixtureExecutor._case_count(row["public_wrapper"]["content"]) == 4
    assert FixtureExecutor._case_count(host["audit_runner"]) > 4
    assert len(json.dumps({"cases": [{"return_pass": True, "state_pass": True, "exception": None}
                         for _ in host["audit_cases"]]}).encode()) < 65536


@pytest.mark.parametrize("kind", ["list_pipeline", "unrelated"])
def test_qualification_is_replayable_fixture_only_and_not_verifier_gate(kind, tmp_path, panel):
    row = next(r for r in panel["development"] if r["task_kind"] == kind)
    executor = FixtureExecutor()
    result = tasks.qualify_row(row, executor, tmp_path)
    assert result["status"] == "qualified" and result["formal_eligible"] is False
    assert result["not_verifier_calibration"] is True and result["deployment_authorized"] is False
    assert result["evidence_origin"] == tasks.ORIGIN
    assert tasks.qualify_row(row, executor, tmp_path) == result
    assert executor.calls == 1


@pytest.mark.parametrize("options,status", [({"unavailable": True}, "unknown"),
    ({"malformed": True}, "unknown"), ({"rejected": True}, "rejected")])
def test_qualification_failure_not_silently_dropped(options, status, tmp_path):
    row = tasks._unrelated("coprime_integers", "development")
    result = tasks.qualify_row(row, FixtureExecutor(**options), tmp_path)
    assert result["status"] == status and result["formal_eligible"] is False
    assert result["receipt"] is not None


def test_panel_qualification_has_all_families_and_fixture_is_pending(tmp_path):
    panel = tasks.build_panel(SEED, 1, 1)
    executor = FixtureExecutor()
    result = tasks.qualify_panel(panel, executor, tmp_path)
    assert result["status"] == "pending" and result["formal_eligible"] is False
    assert result["families"] == len(result["results"]) == executor.calls == 14
    assert tasks.qualify_panel(panel, executor, tmp_path) == result and executor.calls == 14
    changed = deepcopy(panel)
    changed["confirmation"].pop()
    with pytest.raises(ValueError, match="reservation"):
        tasks.qualify_panel(changed, executor, tmp_path)
    assert executor.calls == 14


@pytest.mark.parametrize("kind", ["list_pipeline", "unrelated"])
@pytest.mark.parametrize("options,status", [({}, "pass"), ({"returns": False}, "fail"),
    ({"unavailable": True}, "unknown"), ({"malformed": True}, "unknown")])
def test_audit_replay_and_unknown_preserves_all_positions(kind, options, status, tmp_path, panel):
    row = next(r for r in panel["development"] if r["task_kind"] == kind)
    executor = FixtureExecutor(**options)
    result = tasks.audit_row(row, artifact(row), executor, tmp_path)
    assert result["status"] == result["return_status"] == status
    assert result["real_isolated_execution"] is False and result["deployment_authorized"] is False
    if kind == "unrelated":
        assert result["state_status"] == "not_applicable"
    assert (result["audit_outcomes"] is None) == (status == "unknown")
    if status != "unknown":
        assert len(result["audit_outcomes"]) == len(row["host_only"]["audit_inputs"])
    assert tasks.audit_row(row, artifact(row), executor, tmp_path) == result and executor.calls == 1


def test_missing_artifact_does_not_call_executor_or_become_semantic_failure(tmp_path):
    row = tasks._unrelated("coprime_integers", "development")
    executor = FixtureExecutor()
    result = tasks.audit_row(row, artifact(row, unavailable=True), executor, tmp_path)
    assert result["status"] == "unknown" and result["receipt"] is None
    assert executor.calls == 0
    other = tasks._unrelated("prime_integer", "development")
    with pytest.raises(ValueError):
        tasks.audit_row(row, artifact(other), executor, tmp_path)
    assert executor.calls == 0


def test_no_unisolated_execution_fallback(tmp_path):
    class ForbiddenHostExecutor(FixtureExecutor):
        identity = {"real_execution": True, "host": True}
    executor = ForbiddenHostExecutor()
    row = tasks._unrelated("prime_integer", "development")
    with pytest.raises(ValueError, match="isolated"):
        tasks.qualify_row(row, executor, tmp_path)
    assert executor.calls == 0


@pytest.mark.parametrize("kind", ["list_pipeline", "unrelated"])
def test_existing_rule_solver_accepts_panel_without_reading_host_data(kind, panel, tmp_path):
    from skillopt.skill_validation.rule_skill import RuleSkill
    from skillopt.skill_validation.rule_solver import solve_rule_condition
    from tests.test_skill_validation_rule_solver import CachedFixtureCalls
    from tests.test_skill_validation_public_revision import FixtureExecutor as PublicFixture

    row = next(r for r in panel["development"] if r["task_kind"] == kind)
    class PublicOnlyRow(dict):
        def __getitem__(self, key):
            assert key in {"task", "public_task", "public_wrapper"}, "Solver accessed host metadata"
            return super().__getitem__(key)
    calls, executor = CachedFixtureCalls(), PublicFixture()
    result = solve_rule_condition(PublicOnlyRow(row), RuleSkill("fixture-h0", ()), "no_skill", 0,
                                  calls, executor, tmp_path)
    assert result["artifact"].task_hash == row["task"].contract.content_hash
    assert result["exposure"]["hidden_feedback_used"] is False
    assert result["record"]["shadow_only"] is True
    for record in calls.calls:
        visible = json.loads(record["user"])
        assert visible["optional_skill"] == ""
        assert "reference_a" not in record["user"] and "audit_cases" not in record["user"]
        assert "independent_algorithm_control" not in record["user"]
