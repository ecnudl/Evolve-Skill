"""V16-only orchestration regression: fixed V15 tasks, no live APIs or Python artifacts."""

import hashlib
import json
from pathlib import Path

import pytest

from skillopt.coevolution_v15 import research as parent_research
from skillopt.coevolution_v15 import study as parent
from skillopt.coevolution_v15 import tasks
from skillopt.coevolution_v16 import study
from skillopt.validator_pilot.api import digest
from tests.test_coevolution_v12_study import forbidden, put, tree
from tests.test_coevolution_v15_study import FakeAPI as ParentAPI
from tests.test_coevolution_v15_study import setup as parent_setup  # noqa: F401


class FakeAPI(ParentAPI):
    """Receipt-faithful fixture accepting both unchanged and V16 proposal kinds."""

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
            elif kind.endswith("_validator_search"):
                response = json.dumps({"inputs": tasks.canonical_inputs(self.state["tasks"][value["task"]["id"]])})
            elif kind.endswith("_validator_proposal"):
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


@pytest.fixture
def setup(request, tmp_path, monkeypatch):
    # Reuse only V15's OFFLINE mock executor/official-document transport fixture.
    # No V15 production state, source, final responses or old output is modified.
    _, state, _ = request.getfixturevalue("parent_setup")
    monkeypatch.setattr(study.research, "fetch_sources", parent_research.fetch_sources)
    source = tmp_path / "fixture.txt"
    monkeypatch.setattr(study, "source_hashes", lambda repo: {"fixture.txt": hashlib.sha256(source.read_bytes()).hexdigest()})
    root = tmp_path / "outputs/coevolution_v16/test"
    def build(design="smoke"):
        panel = tasks.build_panel(smoke=design == "smoke")
        state["tasks"].update({tasks.payload(a)["id"]: a
            for group in [*panel["train"], *panel["calibration"], panel["final"]] for a in group})
        return study.Study(tmp_path, root, design=design, panel=panel,
            api_factory=lambda repo, api_root, max_calls, workers: FakeAPI(api_root, max_calls, state))
    return root, state, build


def test_same_tasks_seed_designs_and_core_mechanism_are_reused():
    assert study.tasks is parent.tasks and study.runtime is parent.runtime
    assert study.learning is parent.learning and study.evidence is parent.evidence
    assert study.analysis is parent.analysis
    assert study.SEED == parent.SEED and study.DESIGNS == parent.DESIGNS
    assert study.validator is not parent.validator
    assert study.VERSION.startswith("v16-")


def test_source_closure_contains_all_v15_dependencies_and_new_v16():
    repo = Path(__file__).resolve().parents[1]
    prior = parent.source_hashes(repo)
    current = study.source_hashes(repo)
    assert prior and all(current.get(name) == value for name, value in prior.items())
    required = {str(p.relative_to(repo)) for p in (repo / "skillopt/coevolution_v16").glob("*.py")}
    required |= {"scripts/coevolution_v16.py", "scripts/launch_coevolution_v16.py", "docs/coevolution-v16-protocol.md"}
    assert required <= set(current)
    for name in required:
        assert current[name] == hashlib.sha256((repo / name).read_bytes()).hexdigest()
    assert "skillopt/coevolution_v15/reporting.py" in current
    assert "skillopt/coevolution_v15/tasks.py" in current


@pytest.mark.parametrize("location", ["outputs/coevolution_v15/old", "outputs/coevolution_v16", "outputs/else/run", "."])
def test_safe_root_rejects_old_runs_or_broad_targets(tmp_path, location):
    with pytest.raises(ValueError, match="coevolution_v16"):
        study.safe_root(tmp_path, tmp_path / location)


def test_safe_root_allows_only_dedicated_v16_nonsymlink_root(tmp_path):
    target = tmp_path / "outputs/coevolution_v16/new"
    assert study.safe_root(tmp_path, target) == target
    assert not target.exists()
    with pytest.raises(ValueError):
        study.safe_root(tmp_path, tmp_path / "outputs/coevolution_v16/a/../new")
    parent_dir = target.parent
    parent_dir.mkdir(parents=True)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    target.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="nonsymlink"):
        study.safe_root(tmp_path, target)


@pytest.mark.parametrize("design", ["smoke", "pilot"])
def test_complete_v16_grid_closure_aliases_and_zero_call_replay(setup, monkeypatch, design):
    root, state, build = setup
    expected = build(design).run()
    histories, rounds = study.DESIGNS[design]["histories"], study.DESIGNS[design]["rounds"]
    assert expected["complete"] and expected["learning"]["update_positions"] == histories * rounds * 3
    assert expected["validator_evolution"]["proposals"] == histories * (rounds - 1) * 2
    assert expected["evidence_closure"]["all_api_receipts_accounted"]
    assert expected["evidence_closure"]["unresolved_native_intents"] == 0
    assert expected["ledger"]["cached_logical_calls"] == state["calls"] <= study.DESIGNS[design]["max_calls"]
    panel = study.read(root / "private_panel.json")["groups"]
    rows = study.read(root / "final_rows.json")["rows"]
    assert len(rows) == len(panel["final"]) * histories * 4
    for h in range(histories):
        first = [study.read(root / "learning" / f"h{h}-r0-{arm}.json") for arm in study.learning.ARMS]
        assert len({r["parent_hash"] for r in first}) == len({r["request_hash"] for r in first}) == 1
    # Aliases remain separate policy positions, but never new independent evidence.
    assert len({tuple(r["request_hashes"]) for r in rows if r["policy"] == "no_skill"}) == len(panel["final"]) * histories
    ids = {t["id"] for t in panel["final"]}
    final_start = next(i for i, r in enumerate(state["receipts"])
        if json.loads(r["request"]["user"]).get("task", {}).get("id") in ids)
    assert all(not r["request"]["kind"].endswith(("update", "proposal", "search"))
               for r in state["receipts"][final_start:])
    proposals = [json.loads(p.read_text()) for p in (root / "validator/proposals").glob("*.json")]
    assert any(r["arm"] == "adaptive_research" and r["valid"] for r in proposals)
    before, calls = tree(root), state["calls"]
    monkeypatch.setattr(study.runtime.legacy, "evaluate", forbidden)
    monkeypatch.setattr(study.research, "fetch_sources", forbidden)
    monkeypatch.setattr(study.OfflineAPI, "call", forbidden)
    runner = build(design)
    runner.api_factory = forbidden
    assert runner.run() == expected
    assert tree(root) == before and state["calls"] == calls


def test_source_drift_replay_refuses_without_api(setup, monkeypatch):
    root, state, build = setup
    build().run()
    before, calls = tree(root), state["calls"]
    monkeypatch.setattr(study, "source_hashes", lambda repo: {"fixture.txt": "f" * 64})
    runner = build()
    runner.api_factory = forbidden
    with pytest.raises(ValueError):
        runner.run()
    assert tree(root) == before and state["calls"] == calls


def test_invalid_skill_is_retained_as_explicit_frozen_empty_positions(setup):
    root, state, build = setup
    state["invalid_skill"] = True
    result = build().run()
    rows = study.read(root / "final_rows.json")["rows"]
    assert result["learning"]["valid"] == 0
    assert len(rows) == 12 and all(not r["skill_nonempty"] for r in rows)


def test_pause_preserves_receipts_and_explicit_resume(setup):
    root, state, build = setup
    state["pause_at"] = 1
    with pytest.raises(study.PauseRequested):
        build().run()
    receipts = {p.name: p.read_bytes() for p in (root / "api/calls").glob("*.json")}
    assert receipts and not (root / "results.json").exists()
    (root / "PAUSE").unlink()
    assert build().run()["complete"]
    assert all((root / "api/calls" / name).read_bytes() == value for name, value in receipts.items())


def test_final_tasks_cannot_enter_calibration(setup):
    _, _, build = setup
    runner = build()
    runner.panel["calibration"][0] = runner.panel["final"][:2]
    with pytest.raises(ValueError, match="overlap"):
        runner.prepare()


def test_completed_cli_replay_is_read_only_zero_api(setup, tmp_path, monkeypatch, capsys):
    from scripts import coevolution_v16 as cli
    root, state, build = setup
    expected = build().run()
    (root / ".run.lock").touch()
    (root / ".audit.lock").touch()
    # Inject the same offline fixture panel; production runs have a native
    # preflight receipt, whereas this fixture intentionally has none.
    original = study.Study
    def replay_study(repo, output, **kwargs):
        return original(repo, output, panel=tasks.build_panel(smoke=True), **kwargs)
    monkeypatch.setattr(study, "Study", replay_study)
    before, calls = tree(root), state["calls"]
    capsys.readouterr()
    assert cli.completed_replay(tmp_path, root) == expected
    assert tree(root) == before and state["calls"] == calls
    assert capsys.readouterr().out == ""
