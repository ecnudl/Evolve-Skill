"""Closed V15 orchestration fixtures, no live API or generated Python execution."""

import hashlib
import json
from pathlib import Path
from threading import Lock

import pytest

from skillopt.coevolution_v5.adapters import CodingAdapter
from skillopt.coevolution_v9 import study as transport
from skillopt.coevolution_v15 import research, runtime, study, tasks, validator
from skillopt.validator_pilot.api import digest
from tests.test_coevolution_v12_study import forbidden, put, tree


class FakeAPI:
    model = "glm-5.3"
    service = {"offline_fixture": True, "max_retries": 2}

    def __init__(self, root, maximum, state):
        self.root, self.state = Path(root), state
        put(self.root / "service.json", self.service)
        put(self.root / "budget_protocol.json", {"max_logical_calls": maximum, "model": self.model,
            "workers": 4, "service_sha256": digest(self.service)})

    def call(self, **arguments):
        with self.state["lock"]:
            request = {**arguments, "model": self.model, "service": self.service}
            identifier = digest(request)
            path = self.root / "calls" / (identifier + ".json")
            if path.exists():
                return json.loads(path.read_text())
            value, kind = json.loads(arguments["user"]), arguments["kind"]
            if kind == "v15_skill_update":
                response = "## When\nWhen task constraints apply.\n## Procedure\nVerify affected outputs.\n## Avoid\nInventing constraints."
                if self.state.get("invalid_skill"):
                    response = "Invalid Skill output"
            elif kind == "v15_validator_search":
                response = json.dumps({"inputs": tasks.canonical_inputs(self.state["tasks"][value["task"]["id"]])})
            elif kind == "v15_validator_proposal":
                citations = [{"url": d["url"], "quote": d["text"][:30]} for d in value["official_excerpts"][:1]]
                response = json.dumps({"search_policy": "Use legal paired boundary cases and ordinary controls.",
                                       "when": "Only under the declared contract.", "citations": citations})
            else:
                public = value["task"]
                if value["stage"] == "revision":
                    response = '{"action":"keep"}'
                elif "files" in public:
                    filename = public["editable_paths"][0]
                    response = f"<<<FILE {filename}>>>\n{public['files'][filename]}\n<<<END FILE>>>"
                elif public["domain"] == "spreadsheet":
                    response = json.dumps({"formulas": {k: public["formulas"][k] for k in public["editable_cells"]}})
                else:
                    response = json.dumps({"rules": public["rules"]})
            receipt = {"request": request, "request_hash": identifier, "ok": True, "response": response,
                       "http_attempt_count": 1, "finish_reason": "stop", "usage": {"total_tokens": 2}}
            put(self.root / "budget_reservations" / (identifier + ".json"), {"request_hash": identifier, "kind": kind})
            put(path, receipt)
            self.state["calls"] += 1
            self.state["receipts"].append(receipt)
            if self.state.get("pause_at") == self.state["calls"]:
                (self.root.parent / "PAUSE").touch()
            return receipt

    def close(self):
        self.state["closed"] += 1


@pytest.fixture
def setup(tmp_path, monkeypatch):
    panel = tasks.build_panel(smoke=True)
    lookup = {tasks.payload(a)["id"]: a for group in [*panel["train"], *panel["calibration"], panel["final"]] for a in group}
    state = {"calls": 0, "closed": 0, "receipts": [], "executions": 0, "lock": Lock(), "tasks": lookup}
    source = tmp_path / "fixture.txt"
    source.write_text("frozen test source")
    monkeypatch.setattr(study, "source_hashes", lambda repo: {"fixture.txt": hashlib.sha256(source.read_bytes()).hexdigest()})
    monkeypatch.setattr(transport, "audit_pacing", lambda *a: {"offline_fixture": True})
    native = runtime.legacy.evaluate

    def evaluate(adapter, artifact, *, public_only):
        state["executions"] += 1
        if not isinstance(adapter, CodingAdapter) or artifact is None:
            return native(adapter, artifact, public_only=public_only)
        correct = artifact["logic.py"].startswith(adapter.task.reference_files["logic.py"])
        preserved = "data['values'].append(0)" not in artifact["logic.py"]
        cases = adapter.task.public_cases + ([] if public_only else adapter.task.private_cases)
        observations = [{"label": c["label"], "input": c["input"], "passed": correct,
                         "actual": c["expected"] if correct else {}, "exception": None,
                         "input_unchanged": preserved} for c in cases]
        checks = [{"id": c["label"] + ":" + suffix, "passed": correct if suffix == "behavior" else preserved}
                  for c in cases for suffix in ("behavior", "input_unchanged")]
        return {"files": artifact, "hard": all(c["passed"] for c in checks), "execution_ok": True,
            "public_pass": correct and preserved, "case_results": checks,
            "passed_tests": sum(c["passed"] for c in checks), "total_tests": len(checks),
            "public_observations": [o for o, c in zip(observations, cases) if c["public"]],
            "private_diagnostics": [{**o, "expected": c["expected"]} for o, c in zip(observations, cases) if not c["public"] and not correct]}

    monkeypatch.setattr(runtime.legacy, "evaluate", evaluate)

    def fetch(urls, root):
        text = "This is a synthetic official documentation fixture for exact quotation tests."
        records = [{"requested_url": url, "ok": True, "text": text,
                    "text_sha256": hashlib.sha256(text.encode()).hexdigest()} for url in urls]
        for i, row in enumerate(records):
            put(root / f"fixture-{i}.json", row)
        return records

    monkeypatch.setattr(research, "fetch_sources", fetch)
    root = tmp_path / "outputs/coevolution_v15/test"

    def build(design="smoke"):
        selected = panel if design == "smoke" else tasks.build_panel(smoke=False)
        state["tasks"].update({tasks.payload(a)["id"]: a for group in [*selected["train"], *selected["calibration"], selected["final"]] for a in group})
        return study.Study(tmp_path, root, design=design, panel=selected,
            api_factory=lambda repo, api_root, max_calls, workers: FakeAPI(api_root, max_calls, state))

    return root, state, build


def test_complete_closed_three_learning_arms_and_no_final_feedback(setup):
    root, state, build = setup
    result = build().run()
    assert result["complete"] and result["learning"]["update_positions"] == 6
    assert result["learning"]["valid"] == 6
    assert result["validator_evolution"]["proposals"] == 2
    assert result["evidence_closure"]["all_api_receipts_accounted"]
    assert result["ledger"]["cached_logical_calls"] == state["calls"] <= 192
    assert len(study.read(root / "final_rows.json")["rows"]) == 12
    final_ids = {t["id"] for t in study.read(root / "private_panel.json")["groups"]["final"]}
    first_final = next(i for i, r in enumerate(state["receipts"]) if json.loads(r["request"]["user"]).get("task", {}).get("id") in final_ids)
    assert all(not r["request"]["kind"].endswith(("update", "proposal", "search")) for r in state["receipts"][first_final:])
    for receipt in state["receipts"]:
        req = receipt["request"]
        if req["kind"] in {"v15_skill_update", "v15_validator_proposal", "v15_validator_search"}:
            assert all(identifier not in req["user"] for identifier in final_ids)
            assert '"reference_files":' not in req["user"] and '"reference_artifact":' not in req["user"]


def test_complete_replay_forbids_api_native_and_research_and_keeps_bytes(setup, monkeypatch):
    root, state, build = setup
    expected = build().run()
    before, count = tree(root), state["calls"]
    monkeypatch.setattr(runtime.legacy, "evaluate", forbidden)
    monkeypatch.setattr(research, "fetch_sources", forbidden)
    runner = build()
    runner.api_factory = forbidden
    assert runner.run() == expected
    assert tree(root) == before and state["calls"] == count


def test_first_round_common_parent_and_exact_update_alias(setup):
    root, _, build = setup
    build().run()
    first = [study.read(root / "learning" / f"h0-r0-{arm}.json") for arm in study.learning.ARMS]
    assert len({r["parent_hash"] for r in first}) == len({r["request_hash"] for r in first}) == 1
    second = [study.read(root / "learning" / f"h0-r1-{arm}.json") for arm in study.learning.ARMS]
    assert len({r["parent_hash"] for r in second}) == 1


def test_invalid_skill_does_not_drop_positions_or_invent_fallback_gain(setup):
    root, state, build = setup
    state["invalid_skill"] = True
    result = build().run()
    assert result["learning"]["valid"] == 0
    rows = study.read(root / "final_rows.json")["rows"]
    assert len(rows) == 12 and all(not row["skill_nonempty"] for row in rows)


def test_pause_drains_inflight_and_explicit_resume_preserves_receipts(setup):
    root, state, build = setup
    state["pause_at"] = 1
    with pytest.raises(study.PauseRequested):
        build().run()
    before = {p.name: p.read_bytes() for p in (root / "api/calls").glob("*.json")}
    assert before and not (root / "results.json").exists()
    (root / "PAUSE").unlink()
    assert build().run()["complete"]
    assert all((root / "api/calls" / name).read_bytes() == value for name, value in before.items())


def test_task_final_cannot_be_used_as_calibration(setup):
    _, _, build = setup
    runner = build()
    runner.panel["calibration"][0] = runner.panel["final"][:2]
    with pytest.raises(ValueError, match="overlap"):
        runner.prepare()


def test_initial_policy_is_shared_and_fixed_correctness_schema():
    state = validator.initial_state()
    assert validator.validate_state(state) == state
    assert "expected" not in state and "oracle" not in state


def test_four_round_three_history_registered_pilot_closes_under_budget(setup):
    root, state, build = setup
    result = build("pilot").run()
    assert result["complete"] and result["learning"]["update_positions"] == 36
    assert result["validator_evolution"]["proposals"] == 18
    assert result["ledger"]["cached_logical_calls"] == state["calls"] <= 1536
    rows = study.read(root / "final_rows.json")["rows"]
    assert len(rows) == 3 * 4 * 18
    bases = [r for r in rows if r["policy"] == "no_skill"]
    assert len({tuple(r["request_hashes"]) for r in bases}) == 54
    checkpoints = study.read(root / "checkpoint_rows.json")["rows"]
    assert len(checkpoints) == 4 * 3 * 4 * 4
