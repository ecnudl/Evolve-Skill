"""Offline integration checks: fake serving and a trusted toy execution oracle.

No network, real model calls, or execution of model text on the test host. The
separate executor/validator suites exercise the real isolated module runtime.
"""

import json
import threading
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path

import pytest

from skillopt.coevolution_v3 import executor, tasks
from skillopt.coevolution_v3 import experiment as e
from skillopt.coevolution_v3.analysis import POLICIES
from skillopt.coevolution_v3.executor import RepoTask
from skillopt.validator_pilot.api import digest, write_immutable_json

API_CODE = "from logic import calculate\ndef solve(data):\n    return calculate(data)\n"
OLD = {"api.py": API_CODE, "logic.py": "def calculate(data):\n    return data['x']\n"}
GOOD = {**OLD, "logic.py": "def calculate(data):\n    return data['x'] * 2\n"}
ALT = {**OLD, "logic.py": "def calculate(data):\n    return data['x'] + data['x']\n"}
MUTANT = {**OLD, "logic.py": "def calculate(data):\n    return 0\n"}
MUTATION = {**GOOD, "logic.py": "def calculate(data):\n    data['x'] = float(data['x'])\n    return data['x'] * 2\n"}
REPO = Path(__file__).resolve().parents[1]


def tiny_tasks():
    bank = []
    for phase, count in (("learn0", 4), ("gate0", 2), ("learn1", 4), ("gate1", 2), ("holdout", 12)):
        for n in range(count):
            identifier = f"{phase}-task-{n}"
            cases = [
                {
                    "label": "public-one",
                    "input": {"x": 1},
                    "expected": 2,
                    "exception": None,
                    "dimension": "requested_behavior",
                    "public": True,
                },
                {
                    "label": "private-three",
                    "input": {"x": 3},
                    "expected": 6,
                    "exception": None,
                    "dimension": "requested_behavior",
                    "public": False,
                },
            ]
            task = RepoTask(
                identifier,
                phase,
                "toy-contract",
                f"{phase}-project-{n // 2}",
                f"Task {identifier}. Return twice x, preserving input types and key order.",
                deepcopy(OLD),
                deepcopy(GOOD),
                list(OLD),
                {"x": [1, 3]},
                cases[:1],
                cases[1:],
                {
                    "PRIVATE_METADATA_SECRET": True,
                    "controls": {
                        "reference": GOOD,
                        "alternative": ALT,
                        "starter": OLD,
                        "semantic_mutant": MUTANT,
                        "preservation_mutant": MUTATION,
                    },
                },
            )
            bank.append(
                {
                    "task": task,
                    "phase": phase,
                    "context": "toy-project",
                    "mode": "local-update" if n % 2 == 0 else "full-policy-replacement",
                    "mechanism": "constraint-preservation",
                }
            )
    return bank


def toy_execution(task, files, inputs):
    """Trusted pattern oracle for these five fixed test fixtures, never eval()."""
    if not isinstance(files, dict):
        return [
            {
                "ok": True,
                "exception": "ArtifactContractError",
                "input_unchanged": False,
                "error_category": "candidate_contract_violation",
                "value": None,
            }
            for _ in inputs
        ]
    code = files["logic.py"]
    multiplier = 2 if "* 2" in code or "+ data['x']" in code else 0 if "return 0" in code else 1
    preserved = "float(" not in code
    return [
        {
            "ok": True,
            "value": item["x"] * multiplier,
            "exception": None,
            "input_unchanged": preserved,
            "input_before_fingerprint": digest(item),
            "input_after_fingerprint": digest(item) if preserved else digest({"mutated": item}),
        }
        for item in inputs
    ]


class FakeAPI:
    instances = []

    def __init__(self, repo, root, max_calls=1600, workers=4):
        self.root, self.max_calls = Path(root), max_calls
        self.model, self.service = "glm-5.3", {"fake_offline": True, "max_retries": 2}
        self.calls = []
        self._lock = threading.RLock()
        self.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def parallel(self, jobs, fn, label):
        return [fn(job) for job in jobs]

    def call(self, system, user, kind, key, max_tokens=6000, repeat=0):
        request = {
            "model": self.model,
            "system": system,
            "user": user,
            "kind": kind,
            "key": key,
            "max_tokens": max_tokens,
            "repeat": repeat,
            "service": self.service,
        }
        rh = digest(request)
        path = self.root / "calls" / f"{rh}.json"
        with self._lock:
            if path.exists():
                return json.loads(path.read_text())
            if len(self.calls) >= self.max_calls:
                raise RuntimeError("offline logical budget exhausted")
            payload = json.loads(user)
            if kind == "repo_target":
                identifier, skill = payload["task"]["id"], payload["skill"]
                # Candidate improves source but hurts scope: this activates the
                # precise coupled-vs-decoupled distinction, without an LLM.
                correct = not bool(skill) if identifier.startswith("gate") else bool(skill)
                response = json.dumps({"files": GOOD if correct else OLD})
                if identifier.startswith("holdout"):
                    seal = json.loads((self.root.parent / "final_frozen.json").read_text())
                    assert seal["freeze_before_holdout"] is True
            elif kind == "repo_skill":
                assert all(not item["task"]["id"].startswith("holdout") for item in payload["development"])
                response = (
                    "Preserve interfaces and input identity during changes; verify applicability against the "
                    "current contract and keep the unchanged dependencies intact. Local research advice "
                    "is not approved deployment. Revision " + digest(payload)[:12]
                )
            elif kind == "repo_claim":
                assert "files" not in payload["task"]
                assert "private_cases" not in user and "reference_files" not in user
                assert "PRIVATE_METADATA_SECRET" not in user
                assert "kind" not in payload and "artifact_group" not in payload
                response = json.dumps(
                    {
                        "claims": [
                            {
                                "clause_quote": "Return twice x",
                                "candidate_path": "logic.py",
                                "candidate_quote": "def calculate(data):",
                                "input": {"x": 1},
                            }
                        ],
                        "search_note": "A concrete legal boundary probe, not a claimed execution.",
                    }
                )
            else:
                raise AssertionError("Unexpected serving kind")
            result = {
                "request": request,
                "request_hash": rh,
                "response": response,
                "ok": True,
                "http_attempt_count": 1,
                "usage": {"total_tokens": 1},
            }
            write_immutable_json(path, result)
            self.calls.append(result)
            return result

    def ledger(self):
        return {
            "cached_logical_calls": len(self.calls),
            "by_kind": dict(Counter(c["request"]["kind"] for c in self.calls)),
            "max_logical_calls": self.max_calls,
            "http_attempts_from_cached_records": len(self.calls),
            "terminal_errors": 0,
        }


@pytest.fixture(scope="module")
def offline_run(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    bank = tiny_tasks()
    patch.setattr(tasks, "build_tasks", lambda: deepcopy(bank))
    patch.setattr(
        tasks,
        "input_valid",
        lambda identifier, data: identifier in {b["task"].id for b in bank}
        and set(data) == {"x"}
        and type(data["x"]) is int
        and data["x"] in (1, 3),
    )
    patch.setattr(executor, "execute_inputs", toy_execution)
    patch.setattr(e, "sandbox_probe", lambda: {"ok": True})
    patch.setattr(e, "BudgetedAPI", FakeAPI)
    patch.setattr(e.Study, "_snapshot", lambda self: {"offline_runtime": "immutable-test-only"})
    root = tmp_path_factory.mktemp("coevolution-v3-offline")
    study = e.Study(REPO, root)
    result = study.run()
    try:
        yield {"study": study, "root": root, "result": result, "api": FakeAPI.instances[-1], "patch": patch}
    finally:
        patch.undo()


def test_end_to_end_fixed_budget_two_rounds_and_complete_results(offline_run):
    data = offline_run
    result = data["result"]
    assert result["status"] == "complete"
    assert len(result["decisions"]) == 2 * 3 * 2
    assert result["final_analysis"]["n_rows"] == 12 * 2 * 3 * 7
    assert result["final_analysis"]["all_rows_present"]
    assert result["ledger"]["cached_logical_calls"] < 1428 < e.MAX_CALLS


def test_identical_round_zero_proposals_share_exact_serving_draw(offline_run):
    root = offline_run["root"]
    for stream in e.STREAMS:
        proposals = [json.loads((root / "proposals" / f"s{stream}_{p}_r0.json").read_text()) for p in POLICIES]
        assert len({v["request_hash"] for v in proposals}) == 1
        assert len({v["content"] for v in proposals}) == 1
    calls = offline_run["api"].calls
    assert (
        sum(
            c["request"]["kind"] == "repo_skill" and not json.loads(c["request"]["user"])["restricted_history"]
            for c in calls
        )
        == 2
    )


def test_scope_harm_keeps_only_restricted_decoupled_working(offline_run):
    decisions = json.loads((offline_run["root"] / "decisions/r0.json").read_text())
    for key, decision in decisions.items():
        assert decision["local_decision"]["passed"]
        assert not decision["scope_decision"]["passed"]
        assert "known_scope_regression" in decision["scope_decision"]["reasons"]
        branch = json.loads((offline_run["root"] / "states" / f"{key}_r0.json").read_text())
        learning = branch["learning"]
        assert not learning["approved_deployed"]
        assert bool(learning["working_local"]) is (decision["policy"] != "coupled_evolving")
        assert learning["working_scope"]["deployment_allowed"] is False


def test_identical_round_zero_evidence_yields_identical_evolving_memory(offline_run):
    root = offline_run["root"]
    for stream in e.STREAMS:
        branches = {
            policy: json.loads((root / "states" / f"s{stream}_{policy}_r0.json").read_text())
            for policy in POLICIES
        }
        coupled = branches["coupled_evolving"]["validator"]
        decoupled = branches["decoupled_evolving"]["validator"]
        fixed = branches["decoupled_fixed"]["validator"]
        assert coupled == decoupled
        assert coupled["revision"] > 0 and coupled != fixed
        assert fixed["revision"] == 0 and not fixed["memory"] and not fixed["calibration_notes"]


def test_round_one_source_replay_scope_cardinality_and_parent_are_correct(offline_run):
    decisions = json.loads((offline_run["root"] / "decisions/r1.json").read_text())
    for decision in decisions.values():
        assert len(decision["source_pairs"]) == 8
        assert len(decision["replay_pairs"]) == 8
        assert len(decision["gate_pairs"]) == 4
        assert all(p["id"].startswith("learn1") for p in decision["source_pairs"])
        assert all(p["id"].startswith("learn0") for p in decision["replay_pairs"])
        assert all(p["id"].startswith("gate1") for p in decision["gate_pairs"])
        assert bool(decision["learning_before"]["working_local"]) is (decision["policy"] != "coupled_evolving")


def test_same_content_final_aliases_have_identical_calls_not_label_noise(offline_run):
    rows = json.loads((offline_run["root"] / "final_rows.json").read_text())
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["id"], row["stream"], row["repeat"], row["skill_hash"]].append(row)
    for group in grouped.values():
        assert len({v["request_hash"] for v in group}) == 1
        assert len({v["response"] for v in group}) == 1
        assert len({v["hard"] for v in group}) == 1
    assert len({r["request_hash"] for r in rows}) < len(rows)
    assert all(r["diagnostic_not_deployment"] == r["arm"].startswith("working_") for r in rows)


def test_shadow_same_artifact_equal_budget_no_private_or_control_labels(offline_run):
    shadow = json.loads((offline_run["root"] / "shadow_rows.json").read_text())
    paired = defaultdict(list)
    for row in shadow:
        paired[row["stream"], row["artifact_id"]].append(row)
    for pair in paired.values():
        assert {r["validator"] for r in pair} == {"fixed", "evolving"}
        assert len({r["artifact_hash"] for r in pair}) == 1
        assert len({r["oracle_hard"] for r in pair}) == 1
        assert all(r["shadow_not_fed_back"] for r in pair)
        for row in pair:
            request_hash = row["claim"]["request_hash"]
            if request_hash:
                call = json.loads((offline_run["root"] / "api/calls" / f"{request_hash}.json").read_text())
                assert call["request"]["max_tokens"] == e.CLAIM_TOKENS
                user = json.loads(call["request"]["user"])
                assert "files" not in user["task"] and "kind" not in user and "artifact_group" not in user
                assert "reference_files" not in user["task"] and "private_cases" not in user["task"]


def test_shadow_does_not_update_any_final_state(offline_run):
    root = offline_run["root"]
    freeze = json.loads((root / "final_frozen.json").read_text())
    for key, branch in freeze["states"].items():
        assert branch == json.loads((root / "states" / f"{key}_r1.json").read_text())
        assert all(
            entry["source_phase"] != "holdout"
            for entry in branch["validator"]["memory"] + branch["validator"]["calibration_notes"]
        )
    assert offline_run["result"]["final_state_hash"] == digest(freeze["states"])


def test_completed_run_resume_does_not_make_new_calls(offline_run):
    before = len(offline_run["api"].calls)
    assert offline_run["study"].run() == offline_run["result"]
    assert len(offline_run["api"].calls) == before


def test_target_cache_matches_content_and_request_before_reuse(offline_run):
    study, api = offline_run["study"], offline_run["api"]
    job = study._job("learn0-task-0", "", 0, "r0", 0)
    before = len(api.calls)
    first = study._target(api, job)
    second = study._target(api, job)
    assert first == second and len(api.calls) == before


def test_partial_final_freeze_is_rejected_before_target_call(offline_run, tmp_path):
    study = e.Study(REPO, tmp_path)
    protocol = study.prepare()
    write_immutable_json(
        tmp_path / "final_frozen.json",
        {
            "protocol_hash": digest(protocol),
            "freeze_before_holdout": False,
            "states": {},
            "histories_hash": "not-complete",
        },
    )
    api = FakeAPI(REPO, tmp_path / "api")
    with pytest.raises((ValueError, RuntimeError)):
        study._target(api, study._job("holdout-task-0", "", 0, "final", 0))
    assert not api.calls


def test_source_scope_modes_do_not_make_probe_payload_expose_original_files(offline_run):
    for call in offline_run["api"].calls:
        if call["request"]["kind"] != "repo_claim":
            continue
        payload = json.loads(call["request"]["user"])
        assert "candidate_files" in payload
        assert "files" not in payload["task"] and "PRIVATE_METADATA_SECRET" not in call["request"]["user"]


def test_shadow_missing_oracle_stays_unavailable_not_a_detected_true_negative():
    from skillopt.coevolution_v3.analysis import analyze_shadow

    rows = []
    for label in ("fixed", "evolving"):
        rows.append(
            {
                "stream": 0,
                "artifact_id": "unavailable",
                "artifact_hash": "same",
                "artifact_group": "natural",
                "kind": "natural",
                "validator": label,
                "id": "toy",
                "cluster_id": "project",
                "oracle_hard": None,
                "public_pass": False,
                "baseline_available": False,
                "detected": False,
                "search_status": "target_unavailable",
                "schema_valid": False,
                "valid_probes": 0,
            }
        )
    result = analyze_shadow(rows)
    for label in ("fixed", "evolving"):
        values = result["groups"]["natural"][label]
        assert values["unavailable"] == 1 and values["observable"] == 0
        assert values["detected_oracle_failures"] == 0 and values["oracle_passed_artifacts"] == 0
