"""Synthetic complete-run fixtures only; no model/API or candidate execution."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts import audit_coevolution_v3_delivery as audit


def put(root, relative, value):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def sealed(value):
    return {**value, "state_hash": audit.digest(value)}


def target(root, identifier, skill, stream, stage, repeat, phase):
    job = audit._job(identifier, skill, stream, stage, repeat)
    target_ok = repeat != 1
    execution_ok = target_ok and repeat != 2
    format_ok = target_ok and skill != "delivery"
    hard = None if not target_ok or not execution_ok else skill not in {"delivery", "semantic"}
    row = {
        "id": identifier,
        "stream": stream,
        "stage": stage,
        "repeat": repeat,
        "arm": "shared_content",
        "cluster_id": "cluster-" + identifier,
        "family": "synthetic",
        "mode": "local-update" if identifier.endswith("a") else "full-policy-replacement",
        "phase": phase,
        "skill_hash": audit.digest(skill),
        "skill_active": bool(skill),
        "target_ok": target_ok,
        "execution_ok": execution_ok,
        "format_ok": format_ok,
        "hard": hard,
        "case_fraction": None if hard is None else int(hard),
        "response": "synthetic delivery artifact",
        "files": {"api.py": "synthetic"} if format_ok else None,
        "request_hash": "logical-request-" + audit.digest(job),
        "evaluation_mode": "finite_private_tests",
        "evaluation": {"hard": hard, "execution_ok": execution_ok},
        "research_execution_only": True,
    }
    put(root, "targets/" + audit.digest(job) + ".json", {**row, "record_sha256": audit.digest(row)})
    return job, row


def fixture_run(root):
    root.mkdir()
    protocol = {
        "version": audit.PROTOCOL_VERSION,
        "streams": [0, 1],
        "rounds": [0, 1],
        "policies": list(audit.POLICIES),
        "final_arms": list(audit.ARMS),
        "final_repeats": [0, 1, 2],
        "phase_counts": {"holdout": 2},
        "shared_identical_content_draws_including_final": True,
    }
    put(root, "protocol.json", protocol)
    previous = {}
    histories, result_decisions = [], []
    for s in protocol["streams"]:
        for p in audit.POLICIES:
            previous[s, p] = {
                "learning": sealed({"working_local": "", "approved_deployed": "", "policy": p, "revision": 0}),
                "validator": sealed({"revision": 0, "memory": []}),
            }
    for r in protocol["rounds"]:
        decision_seal = {}
        for s in protocol["streams"]:
            for p in audit.POLICIES:
                key = f"s{s}_{p}"
                before = deepcopy(previous[s, p])
                content = {"coupled_evolving": "", "decoupled_fixed": "semantic", "decoupled_evolving": "delivery"}[p]
                candidate = {"content": content, "content_hash": audit.digest(content), "valid": bool(content)}
                groups = {}
                for source, identity, phase in (
                    ("source", f"learn{r}-a", f"learn{r}"),
                    ("replay", "learn0-a", "learn0"),
                ):
                    pairs = []
                    if source == "source" or r:
                        for rep in (0, 1):
                            pair = {"id": identity, "repeat": rep}
                            for condition, skill in (
                                ("base", ""),
                                ("working", before["learning"]["working_local"]),
                                ("candidate", content),
                            ):
                                _, row = target(root, identity, skill, s, f"r{r}", rep, phase)
                                pair[condition] = {
                                    "available": row["target_ok"] and row["execution_ok"],
                                    "hard": row["evaluation"]["hard"],
                                }
                            pairs.append(pair)
                    groups[source] = pairs
                record = {
                    "stream": s,
                    "policy": p,
                    "round": r,
                    "candidate": candidate,
                    "learning_before": before["learning"],
                    "validator_before": before["validator"],
                    "local_decision": {"action": "AcceptLocal"},
                    "scope_decision": {"action": "Restrict"},
                    "source_pairs": groups["source"],
                    "replay_pairs": groups["replay"],
                    "gate_pairs": [],
                }
                after = {
                    "learning": sealed(
                        {"working_local": content, "approved_deployed": "", "policy": p, "revision": r + 1}
                    ),
                    "validator": sealed({"revision": r + 1, "memory": []}),
                }
                history = {
                    **record,
                    "learning_after": after["learning"],
                    "validator_after": after["validator"],
                    "hidden_gate_losses": 0,
                    "deployed_with_hidden_gate_loss": False,
                }
                histories.append(history)
                decision_seal[key] = record
                put(root, f"states/{key}_r{r}.json", after)
                result_decisions.append(
                    {
                        field: history[field]
                        for field in (
                            "stream",
                            "policy",
                            "round",
                            "local_decision",
                            "scope_decision",
                            "hidden_gate_losses",
                            "deployed_with_hidden_gate_loss",
                        )
                    }
                )
                previous[s, p] = after
        put(root, f"histories/r{r}.json", histories)
        put(root, f"decisions/r{r}.json", decision_seal)
    states = {f"s{s}_{p}": value for (s, p), value in previous.items()}
    put(
        root,
        "final_frozen.json",
        {
            "protocol_hash": audit.digest(protocol),
            "histories_hash": audit.digest(histories),
            "states": states,
            "freeze_before_holdout": True,
        },
    )
    rows, plan = [], []
    for s in protocol["streams"]:
        for identifier in ("held-a", "held-b"):
            for arm in audit.ARMS:
                skill = (
                    ""
                    if not arm.startswith("working_")
                    else states[f"s{s}_{arm.removeprefix('working_')}"]["learning"]["working_local"]
                )
                for rep in protocol["final_repeats"]:
                    job, row = target(root, identifier, skill, s, "final", rep, "holdout")
                    rows.append(
                        {
                            **row,
                            "arm": arm,
                            "shared_draw_job_hash": audit.digest(job),
                            "diagnostic_not_deployment": arm.startswith("working_"),
                        }
                    )
                    plan.append({"arm": arm, "job_hash": audit.digest(job)})
    put(root, "final_rows.json", rows)
    put(root, "final_alias_plan.json", plan)
    arms = {}
    for arm in audit.ARMS:
        selected = [r for r in rows if r["arm"] == arm]
        observable = [r for r in selected if r["target_ok"] and r["execution_ok"]]
        arms[arm] = {
            "n_expected_rows": len(selected),
            "n_rows": len(selected),
            "n_observable": len(observable),
            "hard_passes": sum(r["hard"] is True for r in observable),
            "hard_failures": sum(r["hard"] is False for r in observable),
            "skill_active_rows": sum(r["skill_active"] for r in selected),
            "macro_cluster_mean": 0.123456789,
            "original_marker": "copied, not recomputed",
        }
    unique = len({r["request_hash"] for r in rows})
    results = {
        "status": "complete",
        "protocol_hash": audit.digest(protocol),
        "final_state_hash": audit.digest(states),
        "decisions": result_decisions,
        "final_analysis": {
            "n_rows": len(rows),
            "expected_rows": len(rows),
            "all_rows_present": True,
            "n_tasks": 2,
            "n_project_clusters": 2,
            "unique_api_requests": unique,
            "shared_alias_rows": len(rows) - unique,
            "arms": arms,
        },
    }
    put(root, "results.json", results)
    return root


def load(root, relative):
    return json.loads((root / relative).read_text())


@pytest.fixture
def run(tmp_path):
    return fixture_run(tmp_path / "completed-run")


def test_complete_final_five_categories_preserve_original_denominator_and_dedup(run):
    result = audit.audit(run)
    counts = result["final"]["all"]
    assert counts["logical_rows"] == 84
    assert counts["actual_request_hash_count"] == 36
    assert all(counts["five_categories_logical_rows"][key] > 0 for key in audit.CATEGORIES)
    assert sum(counts["five_categories_logical_rows"].values()) == 84
    assert sum(counts["five_categories_unique_request_hashes"].values()) == 36
    delivery = result["final"]["by_arm"]["working_decoupled_evolving"]
    assert delivery["five_categories_logical_rows"]["delivery_failure"] == 4
    assert delivery["original_hard_accounting"]["observable_denominator"] == 4
    assert delivery["original_hard_accounting"]["hard_failures"] == 4
    assert delivery["nonempty_skill_rows"] == 12
    assert delivery["distinct_nonempty_skill_hashes"] == 1
    assert delivery["original_arm_statistics_copied_without_recomputation"]["macro_cluster_mean"] == 0.123456789
    assert result["development"] == {"included": False}
    assert not result["candidate_reexecution"] and result["model_calls"] == 0


def test_development_round_source_conditions_keep_shared_logical_aliases_separate(run):
    result = audit.audit(run, include_development=True)
    development = result["development"]
    assert development["all"]["logical_rows"] == 108
    assert development["all"]["actual_request_hash_count"] < 108
    assert set(development["by_round_source_condition"]) == {
        f"r{r}/{source}/{condition}"
        for r, source in ((0, "source"), (1, "source"), (1, "replay"))
        for condition in ("base", "working", "candidate")
    }
    assert len(development["by_policy_round_source_condition"]) == 27
    assert not any("gate_private" in relative or relative.startswith("api/") for relative in result["input_sha256"])


@pytest.mark.parametrize("status", ["running", "failed", None])
def test_completion_barrier_reads_only_results(tmp_path, monkeypatch, status):
    root = tmp_path / "unfinished"
    root.mkdir()
    put(root, "results.json", {"status": status})
    seen = []
    original = Path.read_bytes

    def spy(path):
        seen.append(path.name)
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", spy)
    with pytest.raises(ValueError, match="Completion barrier"):
        audit.audit(root, include_development=True)
    assert seen == ["results.json"]


def test_missing_results_never_reads_holdout(tmp_path, monkeypatch):
    root = tmp_path / "unfinished"
    root.mkdir()
    seen = []
    original = Path.read_bytes

    def spy(path):
        seen.append(path.name)
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", spy)
    with pytest.raises(FileNotFoundError):
        audit.audit(root)
    assert seen == ["results.json"]


@pytest.mark.parametrize(
    "artifact,mutation",
    [
        ("results.json", lambda value: value.update(protocol_hash="wrong")),
        ("final_frozen.json", lambda value: value.update(freeze_before_holdout=False)),
        ("final_frozen.json", lambda value: value.update(histories_hash="wrong")),
        ("states/s0_decoupled_fixed_r1.json", lambda value: value["learning"].update(working_local="altered")),
        ("histories/r1.json", lambda value: value.pop()),
        ("decisions/r0.json", lambda value: value["s0_coupled_evolving"]["local_decision"].update(action="different")),
        ("final_alias_plan.json", lambda value: value.pop()),
        ("final_rows.json", lambda value: value[0].update(format_ok=False)),
        ("results.json", lambda value: value["final_analysis"]["arms"]["noskill"].update(n_observable=999)),
    ],
)
def test_seal_alias_record_and_original_summary_mismatches_fail_closed(run, artifact, mutation):
    value = load(run, artifact)
    mutation(value)
    put(run, artifact, value)
    with pytest.raises(ValueError):
        audit.audit(run)


def test_target_record_hash_mismatch_rejected(run):
    first = load(run, "final_rows.json")[0]
    path = "targets/" + first["shared_draw_job_hash"] + ".json"
    record = load(run, path)
    record["format_ok"] = False
    put(run, path, record)
    with pytest.raises(ValueError, match="record hash"):
        audit.audit(run)


def test_shared_request_must_not_change_classification():
    row = {
        "id": "a",
        "stream": 0,
        "stage": "final",
        "repeat": 0,
        "skill_hash": "empty",
        "skill_active": False,
        "target_ok": True,
        "execution_ok": True,
        "format_ok": True,
        "hard": True,
        "request_hash": "same",
    }
    with pytest.raises(ValueError, match="aliases disagree"):
        audit.counts([row, {**row, "format_ok": False, "hard": False}])


def test_delivery_failure_does_not_erase_known_failure_denominator():
    row = {
        "target_ok": True,
        "execution_ok": True,
        "format_ok": False,
        "hard": False,
        "skill_active": True,
        "skill_hash": "skill",
        "stream": 0,
        "request_hash": "known",
    }
    result = audit.counts([row])
    assert result["original_hard_accounting"] == {
        "expected_rows": 1,
        "observable_denominator": 1,
        "hard_passes": 0,
        "hard_failures": 1,
        "unknown": 0,
        "delivery_failures_remain_in_original_denominator": True,
    }


@pytest.mark.parametrize("relative", [".env", "api/calls/request.json", "../other.json", "targets/not-a-hash.json"])
def test_reader_explicitly_rejects_credentials_api_or_arbitrary_paths(run, relative):
    reader = audit.Reader(run)
    reader.complete = True
    with pytest.raises(ValueError, match="Forbidden"):
        reader.read(relative)


def test_cli_creates_new_external_report_without_modifying_any_source_bytes(run, tmp_path):
    before = {str(path.relative_to(run)): path.read_bytes() for path in run.rglob("*") if path.is_file()}
    output = tmp_path / "delivery-audit"
    assert audit.main(["--run", str(run), "--output", str(output), "--include-development"]) == 0
    report = load(output, "delivery_audit.json")
    assert report["status"] == "completed_source_audited"
    assert report["original_hard_labels_and_denominators_changed"] is False
    assert {str(path.relative_to(run)): path.read_bytes() for path in run.rglob("*") if path.is_file()} == before
    assert audit.main(["--run", str(run), "--output", str(output)]) == 1


def test_output_inside_source_or_existing_directory_is_refused(run, tmp_path):
    with pytest.raises(ValueError, match="outside"):
        audit.write_report({}, run / "audit", run)
    with pytest.raises(ValueError, match="already exists"):
        audit.write_report({}, tmp_path, run)


def test_unfinished_cli_never_creates_output(tmp_path):
    root = tmp_path / "pending"
    root.mkdir()
    put(root, "results.json", {"status": "running"})
    output = tmp_path / "must-not-be-created"
    assert audit.main(["--run", str(root), "--output", str(output)]) == 1
    assert not output.exists()


def test_reader_rejects_symlinked_artifact_even_after_completion(run, tmp_path):
    original = run / "final_rows.json"
    external = tmp_path / "external-final.json"
    external.write_bytes(original.read_bytes())
    original.unlink()
    original.symlink_to(external)
    with pytest.raises(ValueError, match="Symlinked"):
        audit.audit(run)


def test_script_has_no_model_execution_or_credential_imports():
    import ast

    tree = ast.parse(Path(audit.__file__).read_text())
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    modules |= {name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names}
    assert modules <= {"__future__", "argparse", "hashlib", "json", "re", "collections", "pathlib"}
