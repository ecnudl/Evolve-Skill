"""Natural runner orchestration tests with fabricated observations only.

No model API, SSH, Python exec/eval, benchmark import, or artifact execution is
used. Explicit fixture H labels exercise control flow, never method efficacy.
"""
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import natural_data as data
from skillopt.skill_validation import natural_study as study
from skillopt.skill_validation.checks import CallableTask, PublicCase
from skillopt.skill_validation.models import ArtifactRecord, Obligation, SourceFile, TaskContract
from skillopt.skill_validation.natural_metrics import calibrate_policy
from skillopt.skill_validation.task_probes import execute_probes, parse_probes
from skillopt.validator_pilot.api import digest, write_immutable_json

PARENT = "Use a conditional procedure and follow the explicit task contract."
CANDIDATE = ("## Mechanism\nPublic contract conformance.\n## When\nThe stated contract supports the check.\n"
             "## Procedure\nCheck legal boundary behavior.\n## Avoid\nAbstain from unsupported requirements.")
H_SECRET = "HOST_ONLY_SENTINEL_NEVER_SEND_TO_MODEL"


def test_adapter_amendment_preserves_same_panel_and_old_receipts(tmp_path):
    old = tmp_path / "outputs/skill_validation/old"
    new = tmp_path / "outputs/skill_validation/new"
    parent = seal({"text": PARENT})
    manifest = seal({"settings": {"implementation_hash": digest("old adapter")},
                     "splits": {"development": [{"task_id": "same task"}]},
                     "run_path": str(old.relative_to(tmp_path))})
    protocol = seal({"manifest_hash": manifest["record_hash"], "parent_hash": parent["record_hash"]})
    for name, value in {"data_manifest.json": manifest, "protocol.json": protocol,
                        "parent_skill.json": parent, "source_snapshot.json": seal({"source": "unchanged"}),
                        "exposure_inventory.json": seal({"old_exposures": []}),
                        "eligibility_manifest.json": seal({"eligibility": "original"})}.items():
        study._write(old / name, value)
    before = {p: p.read_bytes() for p in old.rglob("*.json")}
    amended = study.amend_panel(tmp_path, new, old)
    assert amended["splits"] == manifest["splits"]
    assert amended["amendment"]["same_panel_not_new_independent_sample"] is True
    assert amended["amendment"]["previous_manifest_hash"] == manifest["record_hash"]
    assert amended["settings"]["implementation_hash"] != manifest["settings"]["implementation_hash"]
    assert study._read(new / "parent_skill.json") == parent
    assert {p: p.read_bytes() for p in old.rglob("*.json")} == before
    assert study.amend_panel(tmp_path, new, old) == amended
    with pytest.raises(ValueError):
        study.amend_panel(tmp_path, old, old)


def fixture_row(partition, index):
    key = partition + "-" + str(index)
    prompt = "Return the integer argument unchanged. Fixture task: " + key + "."
    contract = TaskContract(key, key, "family-" + key, "fixture-project", partition, "coding", "return_contract",
                            prompt, (Obligation("requested_behavior", "requested_behavior", prompt, prompt),))
    case = PublicCase("public-one", '{"args":[1],"kwargs":{}}', prompt,
                      ("requested_behavior",), expected_json="1")
    direct = CallableTask(contract, "solution", "solve", (case,))
    public_case = replace(case, arguments_json='{"args":[],"kwargs":{}}', expected_json="true")
    return {"task": direct, "public_task": CallableTask(contract, "public_runner", "check", (public_case,)),
            "public_wrapper": {"path": "public_runner.py", "content": "# Fixture public wrapper, never executed\n"},
            "host_audit": {"secret": H_SECRET}, "key": key}


def proposed(task):
    return {"probes": [{"kind": "expected", "calls": [{"args": [99], "kwargs": {}}], "expected": 99,
                        "obligation_id": "requested_behavior", "contract_quote": "Return the integer argument unchanged.",
                        "rationale": "The stated identity behavior includes this integer."}]}


class FixtureAPI:
    def __init__(self, repo, root, *, state, workers=4, **kwargs):
        self.root, self.state, self.workers = root, state, workers
        self.model = "fixture-no-real-api"
        self.service = {"fixture": True, "max_retries": 0}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def call(self, system, user, kind, key, max_tokens=2048, repeat=0):
        request = {"model": self.model, "system": system, "user": user, "kind": kind, "key": key,
                   "max_tokens": max_tokens, "repeat": repeat, "service": self.service}
        request_hash = digest(request)
        path = self.root / "calls" / (request_hash + ".json")
        if path.exists():
            return json.loads(path.read_text())
        self.state["new_api_calls"].append(request)
        payload = json.loads(user)
        assert H_SECRET not in user
        if kind == "natural-solver":
            task_key = payload["task"].split("Fixture task: ", 1)[1].split(".", 1)[0]
            skill = payload["optional_skill"]
            role = "no_skill" if not skill else "current" if skill == PARENT else "candidate"
            marker = json.dumps({"task": task_key, "role": role}, sort_keys=True)
            response = json.dumps({"solution.py": "# fixture:" + marker + "\ndef solve(value):\n    return value\n"})
        elif kind.startswith("natural-policy-plan-"):
            action = self.state["policy_action"]
            response = json.dumps({"status": action, "questions": ["Which legal boundary is uncovered?"], "urls": []})
        elif kind.startswith("natural-policy-synthesis-"):
            response = json.dumps({"status": "update", "policy": payload["example_policy"], "citations": [],
                                   "reason": "Fixture conditional proposal."})
        elif kind.startswith("natural-probes-"):
            response = "not a JSON proposal" if self.state.get("invalid_probes") else json.dumps(proposed(None))
        elif kind == "natural-skill-update":
            assert not any(p in {"skill_confirmation", "final"} for p in self.state["loaded_partitions"])
            response = CANDIDATE
        else:
            raise AssertionError("Unexpected fixture model request: " + kind)
        record = {"request": request, "request_hash": request_hash, "ok": True, "response": response,
                  "usage": {"prompt_tokens": 1, "completion_tokens": 1}, "http_attempt_count": 1}
        write_immutable_json(path, record)
        return record

    def parallel(self, jobs, fn, label):
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            return list(pool.map(fn, jobs))


class FixtureExecutor:
    identity = {"kind": "natural-study-nonexecuting-fixture"}
    transport_identity = {"kind": "fixture-no-network-no-interpreter"}

    def __init__(self, failures=(), *, unavailable=False):
        self.failures, self.calls, self.unavailable = set(failures), [], unavailable

    def run(self, files, module, function, args, kwargs):
        call = {"module": module, "function": function, "args": args, "kwargs": kwargs}
        self.calls.append(deepcopy({"files": files, **call}))
        actual = True
        if module == "hidden_audit":
            # This is JSON fixture metadata, never parsed or executed as Python.
            metadata = json.loads(files["hidden_audit.py"])
            marker = {} if metadata["reference"] else self.marker(files)
            failed = (marker.get("task"), marker.get("role")) in self.failures
            actual = {"base_pass": True, "plus_pass": not failed, "base_count": 2, "plus_count": 3}
        elif module == "solution":
            marker = self.marker(files)
            failed = (marker["task"], marker["role"]) in self.failures
            actual = 0 if failed and args == [99] else args[0]
        return seal({"status": "unsupported" if self.unavailable else "observed", "actual": actual,
                     "exception": None, "reason": "explicit_fixture_observation", "cleanup_confirmed": True,
                     "input_hash": digest({"files": files, **call}), "source_hash": digest(files),
                     "call_hash": digest(call), "executor_identity": self.identity,
                     "before_args": deepcopy(args), "after_args": deepcopy(args),
                     "before_kwargs": deepcopy(kwargs), "after_kwargs": deepcopy(kwargs)})

    @staticmethod
    def marker(files):
        return json.loads(files["solution.py"].splitlines()[0].removeprefix("# fixture:"))


def prepare(tmp_path, monkeypatch, *, calibration_tasks=3, policy_action="investigate"):
    root = tmp_path / "study"
    counts = {"development": 3, "verifier_calibration": calibration_tasks, "skill_confirmation": 3, "final": 3}
    manifest = seal({"fixture_only": True, "counts": counts,
                     "splits": {p: [{"task_id": p + "-" + str(i)} for i in range(n)] for p, n in counts.items()}})
    write_immutable_json(root / "data_manifest.json", manifest)
    write_immutable_json(root / "parent_skill.json", seal({"text": PARENT}))
    rows = {partition: [fixture_row(partition, i) for i in range(count)] for partition, count in counts.items()}
    state = {"new_api_calls": [], "loaded_partitions": [], "policy_action": policy_action}

    def load(repo, given, partition):
        assert given == manifest
        if partition in {"skill_confirmation", "final"}:
            frozen = study._read(root / "frozen_candidates.json")
            assert frozen["all_frozen_before_confirmation_and_final"] is True
            assert {candidate["skill"] for candidate in frozen["candidates"].values()} == {CANDIDATE}
        state["loaded_partitions"].append(partition)
        return rows[partition]

    def audit_files(row, code, *, reference=False):
        return {"solution.py": "# fixture reference" if reference else code,
                "hidden_audit.py": json.dumps({"task": row["key"], "reference": reference, "private": H_SECRET})}

    monkeypatch.setattr(data, "load_tasks", load)
    monkeypatch.setattr(data, "build_audit_files", audit_files)
    monkeypatch.setattr(study, "CachedAPI", lambda repo, path, **kwargs: FixtureAPI(repo, path, state=state, **kwargs))
    return root, rows, state


@pytest.mark.parametrize("partition", ["final", "development"])
def test_public_incompatibility_is_unknown_not_model_failure_or_discard(tmp_path, monkeypatch, partition):
    root, rows, state = prepare(tmp_path, monkeypatch)
    manifest = study._read(root / "data_manifest.json")
    records = [seal({"task_id": row["key"], "partition": p,
                     "status": "fail" if p == partition and i == 0 else "pass"})
               for p, group in rows.items() for i, row in enumerate(group)]
    preflight = seal({"manifest_hash": manifest["record_hash"], "model_calls": 0,
                      "hidden_audit_executed": False, "rows": records})
    path = tmp_path / "public-preflight.json"
    study._write(path, preflight)
    if partition == "development":
        with pytest.raises(ValueError, match="incompatible development"):
            study.run(tmp_path, root, FixtureExecutor(), repeats=1, update_repeats=1, public_preflight=path)
        assert not state["new_api_calls"]
    else:
        result = study.run(tmp_path, root, FixtureExecutor(), repeats=1, update_repeats=1, public_preflight=path)
        assert result["final"]["arms"]["no_skill"]["counts"] == {"pass": 2, "fail": 0, "unknown": 1}
        assert result["final"]["arms"]["no_skill"]["attempts"] == 3
        assert not any("Fixture task: final-0." in r["user"] for r in state["new_api_calls"]
                       if r["kind"] == "natural-solver")


@pytest.mark.parametrize("policy_action", ["investigate", "no_update"])
def test_pending_or_no_update_never_projects_probes_and_aliases_share_requests(tmp_path, monkeypatch, policy_action):
    root, _, state = prepare(tmp_path, monkeypatch, policy_action=policy_action)
    executor = FixtureExecutor()
    result = study.run(tmp_path, root, executor, workers=4, repeats=1, update_repeats=1)
    assert set(result["verifier_gate"].values()) == {"pending"}
    assert result["unique_candidate_texts"] == 1
    assert result["unique_update_requests"] == 2  # contract-only versus identical public-feedback aliases
    assert result["deployment_authorized"] is result["cross_domain_evidence"] is False
    assert result["final"]["tasks"] == 3
    assert result["final"]["arms"]["fixed_u0"]["attempts"] == 3
    freeze = study._read(root / "frozen_candidates.json")
    assert all(not c["extra_probe_feedback_used"] for c in freeze["candidates"].values())
    assert freeze["candidates"]["fixed_u0"]["request_ref"] == freeze["candidates"]["adaptive_research_u0"]["request_ref"]
    updates = [r for r in state["new_api_calls"] if r["kind"] == "natural-skill-update"]
    assert updates and all("qualified_probe_feedback" not in r["user"] for r in updates)
    assert all("verifier_calibration-" not in r["user"] and "final-" not in r["user"] for r in updates)
    if policy_action == "no_update":
        assert not any(r["kind"].startswith("natural-probes-") for r in state["new_api_calls"])
    for path in (root / "artifacts").glob("*.json"):
        assert study._read(path)["provenance_kind"] == "fixture"
    assert study._read(root / "skill_decision.json")["action"] == "Pending"

    before = {p: p.read_bytes() for p in root.rglob("*.json")}
    api_count, executions = len(state["new_api_calls"]), len(executor.calls)
    assert study.run(tmp_path, root, executor, workers=4, repeats=1, update_repeats=1) == result
    assert len(state["new_api_calls"]) == api_count
    assert len(executor.calls) == executions + 1  # only the harmless preflight runs again
    assert {p: p.read_bytes() for p in root.rglob("*.json")} == before


def test_calibrated_hypotheses_only_reach_development_updater(tmp_path, monkeypatch):
    root, _, state = prepare(tmp_path, monkeypatch, calibration_tasks=8)
    failures = {(f"verifier_calibration-{i}", arm) for i in (0, 1) for arm in ("no_skill", "current")}
    failures.add(("development-0", "current"))
    result = study.run(tmp_path, root, FixtureExecutor(failures), workers=4, repeats=1, update_repeats=1)
    assert set(result["verifier_gate"].values()) == {"accepted"}
    authorities = study._read(root / "verifier_authorities.json")["authorities"]
    for authority in authorities.values():
        assert authority["counts"]["natural_errors"] == 4
        assert authority["counts"]["natural_correct"] == 12
        assert authority["net_new_detection"] == 4
        assert authority["false_rejection_increase"] == 0
        assert authority["deployment_authorized"] is False
    updates = [json.loads(r["user"]) for r in state["new_api_calls"] if r["kind"] == "natural-skill-update"]
    extra = [u["qualified_probe_feedback"] for u in updates if "qualified_probe_feedback" in u]
    assert extra
    for feedback in extra:
        assert len(feedback) == 3
        for item in feedback:
            assert "development-" in item["public_task"]
            assert set(item["roles"]) == {"no_skill", "current"}
            for checks in item["roles"].values():
                assert all(c["information_origin"] == "model_hypothesis_not_ground_truth" for c in checks)
    encoded = json.dumps(updates)
    assert H_SECRET not in encoded and "audit_status" not in encoded
    assert "verifier_calibration-" not in encoded and "skill_confirmation-" not in encoded and "final-" not in encoded
    assert result["unique_candidate_texts"] == 1  # distinct prompts do not establish distinct effects
    assert result["deployment_authorized"] is False


def test_invalid_new_probes_are_rejected_without_updater_hypothesis_feedback(tmp_path, monkeypatch):
    root, _, state = prepare(tmp_path, monkeypatch, calibration_tasks=8)
    state["invalid_probes"] = True
    failures = {(f"verifier_calibration-{i}", arm) for i in (0, 1) for arm in ("no_skill", "current")}
    result = study.run(tmp_path, root, FixtureExecutor(failures), workers=4, repeats=1, update_repeats=1)
    assert set(result["verifier_gate"].values()) == {"rejected"}
    updates = [r for r in state["new_api_calls"] if r["kind"] == "natural-skill-update"]
    assert updates and all("qualified_probe_feedback" not in r["user"] for r in updates)
    assert all(not candidate["extra_probe_feedback_used"] for candidate in
               study._read(root / "frozen_candidates.json")["candidates"].values())


def test_changing_only_final_audit_cannot_change_candidate_or_update_prompts(tmp_path, monkeypatch):
    first, _, first_state = prepare(tmp_path / "first", monkeypatch, policy_action="no_update")
    first_result = study.run(tmp_path, first, FixtureExecutor(), workers=4, repeats=1, update_repeats=1)
    second, _, second_state = prepare(tmp_path / "second", monkeypatch, policy_action="no_update")
    failures = {(f"final-{i}", "candidate") for i in range(3)}
    second_result = study.run(tmp_path, second, FixtureExecutor(failures), workers=4, repeats=1, update_repeats=1)
    assert first_result["final"] != second_result["final"]
    assert study._read(first / "frozen_candidates.json") == study._read(second / "frozen_candidates.json")
    def updates(state):
        return [r for r in state["new_api_calls"] if r["kind"] == "natural-skill-update"]
    assert sorted(updates(first_state), key=digest) == sorted(updates(second_state), key=digest)


def test_unavailable_preflight_has_no_model_requests(tmp_path, monkeypatch):
    root, _, state = prepare(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="Sandbox unavailable"):
        study.run(tmp_path, root, FixtureExecutor(unavailable=True), repeats=1, update_repeats=1)
    assert not state["new_api_calls"] and not list((root / "api").glob("calls/*.json"))


def test_failed_probe_infrastructure_stops_before_any_skill_update(tmp_path, monkeypatch):
    root, _, state = prepare(tmp_path, monkeypatch)

    class ProbeFailure(FixtureExecutor):
        def __init__(self):
            super().__init__()
            self.failed = threading.Event()

        def run(self, files, module, function, args, kwargs):
            if module == "solution":
                self.failed.set()
                raise RuntimeError("fixture SSH failure, never real transport")
            return super().run(files, module, function, args, kwargs)

    with pytest.raises(ValueError, match="[Ii]nfrastructure|[Ee]xecution pool"):
        study.run(tmp_path, root, ProbeFailure(), workers=4, repeats=1, update_repeats=1)
    assert not any(r["kind"] == "natural-skill-update" for r in state["new_api_calls"])
    assert not (root / "frozen_candidates.json").exists()


def feedback_fixture(tmp_path):
    task = fixture_row("development", 0)["task"]
    artifacts = []
    for role in ("no_skill", "current"):
        marker = json.dumps({"task": "development-0", "role": role})
        code = "# fixture:" + marker + "\ndef solve(value):\n    return value\n"
        skill = "" if role == "no_skill" else PARENT
        artifacts.append(ArtifactRecord(task.contract.content_hash, 0, role, "fixture", hashlib.sha256(skill.encode()).hexdigest(),
            (SourceFile("solution.py", code),), "available", "fixture", True, False, "fixture", digest("fixture")))
    policy_hash = digest("frozen-policy")
    proposal = parse_probes(proposed(task), task)
    proposal_record = seal({"policy_hash": policy_hash, "proposal": proposal, "status": "proposed", "request_hash": digest("api")})
    reports = tuple(execute_probes(task, artifact, proposal, FixtureExecutor(), tmp_path / "execute") for artifact in artifacts)
    records = [{"task_id": "calibration-" + str(i), "family_id": "family-" + str(i), "repeat": 0,
                "condition": "no_skill", "audit_status": "fail" if i == 0 else "pass", "fixed_status": "pass",
                "new_status": "fail" if i == 0 else "pass", "artifact_hash": digest(["artifact", i]),
                "report_hash": digest(["report", i]), "audit_hash": digest(["audit", i]), "partition": "verifier_calibration"}
               for i in range(3)]
    authority = calibrate_policy(records, policy_hash=policy_hash, protocol_hash=digest("protocol"),
        manifest_hash=digest("manifest"), config={"min_independent_families": 3, "min_natural_errors": 1,
                                               "min_natural_correct": 2})
    return task, tuple(artifacts), reports, authority, policy_hash, proposal_record


def reseal(value, **changes):
    return seal({**{k: v for k, v in value.items() if k != "record_hash"}, **changes})


def test_qualified_projection_keeps_hypotheses_and_excludes_host_authority_metadata(tmp_path):
    args = feedback_fixture(tmp_path)
    result = study.project_probe_feedback(*args)
    assert set(result["roles"]) == {"no_skill", "current"}
    assert result["roles"]["current"][0]["information_origin"] == "model_hypothesis_not_ground_truth"
    assert "config" not in json.dumps(result) and "audit_hash" not in json.dumps(result)


@pytest.mark.parametrize("change", [{"status": "pending"}, {"status": "rejected"},
                                    {"qualified_development_feedback_authorized": False},
                                    {"policy_hash": digest("another-policy")}])
def test_unauthorized_projection_rejected(tmp_path, change):
    args = list(feedback_fixture(tmp_path))
    args[3] = reseal(args[3], **change)
    with pytest.raises(ValueError, match="Uncalibrated"):
        study.project_probe_feedback(*args)


def test_unapproved_generation_policy_or_different_proposal_rejected(tmp_path):
    args = list(feedback_fixture(tmp_path))
    original = args[5]
    args[5] = reseal(original, policy_hash=digest("another-generator"))
    with pytest.raises(ValueError, match="authorized policy"):
        study.project_probe_feedback(*args)
    changed = proposed(args[0])
    changed["probes"][0]["expected"] = 17
    args[5] = reseal(original, proposal=parse_probes(changed, args[0]))
    with pytest.raises(ValueError, match="artifact mismatch"):
        study.project_probe_feedback(*args)


@pytest.mark.parametrize("scope", [{"adapter_domain": "spreadsheet"}, {"obligation_kinds": ["input_preservation"]},
                                  {"allowed_partition": "final"}])
def test_unapproved_scope_cannot_project_feedback(tmp_path, scope):
    args = list(feedback_fixture(tmp_path))
    args[3] = reseal(args[3], scope={**args[3]["scope"], **scope})
    with pytest.raises(ValueError, match="Calibration scope"):
        study.project_probe_feedback(*args)


def test_incomplete_duplicate_or_unpaired_roles_rejected(tmp_path):
    base = feedback_fixture(tmp_path)
    cases = [(base[1][:1], base[2]), (base[1], base[2][:1]),
             ((base[1][0], base[1][0]), base[2]),
             ((base[1][0], replace(base[1][1], repeat=1)), base[2])]
    for artifacts, reports in cases:
        with pytest.raises(ValueError, match="Complete paired"):
            study.project_probe_feedback(base[0], artifacts, reports, *base[3:])


def test_confirmation_or_final_cannot_enter_feedback(tmp_path):
    args = list(feedback_fixture(tmp_path))
    for partition in ("verifier_calibration", "skill_confirmation", "final"):
        args[0] = replace(args[0], contract=replace(args[0].contract, partition=partition))
        with pytest.raises(ValueError, match="Only development"):
            study.project_probe_feedback(*args)


def test_wrong_artifact_binding_is_rejected(tmp_path):
    args = list(feedback_fixture(tmp_path))
    args[1] = tuple(replace(a, repeat=1) for a in args[1])
    with pytest.raises(ValueError, match="artifact mismatch"):
        study.project_probe_feedback(*args)


def test_probe_prediction_is_a_verifier_guess_not_a_semantic_authorization():
    assert study.probe_prediction("pass", seal({"status": "mismatch"})) == "fail"
    assert study.probe_prediction("pass", seal({"status": "unknown"})) == "unknown"
    assert study.probe_prediction("fail", seal({"status": "unknown"})) == "fail"
    assert study.probe_prediction("unknown", seal({"status": "match"})) == "unknown"
    assert study.probe_prediction("pass", seal({"status": "match"})) == "pass"
    with pytest.raises(ValueError):
        study.probe_prediction("pass", {"status": "match", "record_hash": "tampered"})
