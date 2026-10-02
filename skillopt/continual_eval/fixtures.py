"""Public, answer-free-of-research-claims engineering demonstration.

Mock inference and mock native execution are intentional for four benches;
SearchQA additionally uses its real deterministic scorer. No model or generated
code is executed. This exercises orchestration, NOT five real benchmarks.
"""
from __future__ import annotations

from . import VERSION
from .core import BENCHMARKS, freeze_plan, register_checkpoint, safe_path, write_json
from .runner import generate, report, score_checkpoint


def fixture_panel(benchmark):
    public = {
        "searchqa": {"question": "What color is the fixture square?", "context": "The square is blue."},
        "bigcodebench": {"prompt": "Return 1.", "entry_point": "task_func"},
        "spreadsheetbench": {"instruction": "Set A1 to one.", "input_files": ["fixture-input.xlsx"],
                             "answer_position": "Sheet1!A1"},
        "korbench": {"rule": "Answer YES to the word blue.", "question": "blue"},
        "alfworld": {"game_file": "fixture-game.tw-pddl"},
    }
    private = {
        "searchqa": {"answers": ["blue"]},
        "bigcodebench": {"test": "# fixture, never executed"},
        "spreadsheetbench": {"test_files": ["fixture-gold.xlsx"], "answer_position": "Sheet1!A1"},
        "korbench": {"answer": "YES", "category": "logic", "rule_id": "fixture-rule", "upstream_index": "0"},
        "alfworld": {"game_metadata": {}},
    }
    return {"version": "continual-panel-v1", "benchmark": benchmark, "dataset_revision": "engineering-fixture-1",
            "provenance": "fixture", "tasks": [{"task_id": benchmark + "/fixture", "family_id": "fixture-family",
                "project_id": "fixture-project", "partition": "final",
                "public": public[benchmark], "private": private[benchmark]}]}


def fixture_config(root, *, methods=None, repeats=1):
    root = safe_path(root)
    panels = {}
    for benchmark in BENCHMARKS:
        path = root / "panels" / (benchmark + ".json")
        write_json(path, fixture_panel(benchmark))
        panels[benchmark] = str(path)
    return {"version": VERSION, "order": list(BENCHMARKS), "panels": panels, "partition": "final",
            "methods": methods or ["no_skill"], "histories": ["h0"], "repeats": repeats,
            "model": {"provider": "fixture", "name": "fixture", "max_tokens": 4096, "reasoning_effort": "low"},
            "runtime": {}, "project_disjoint": False, "exposure_manifest": None}


def fixture_solve(benchmark, public, skill_text, call, *, runtime):
    assert set(public) == set(fixture_panel(benchmark)["tasks"][0]["public"])
    return {"status": "available", "output": "<answer>blue</answer>" if benchmark == "searchqa" else "fixture",
            "reason": "mock_inference_not_a_model_run"}


def fixture_score(benchmark, public, private, prediction, *, runtime):
    if benchmark == "searchqa":
        from .backends import score
        return score(benchmark, public, private, prediction, runtime=runtime)
    return {"status": "pass", "score": 1.0, "metrics": {"fixture": True}, "reason": "mock_native_score"}


def smoke(root):
    root = safe_path(root)
    config = fixture_config(root)
    freeze_plan(config, root)
    counts = {"positions": 0, "new_positions": 0}
    for stage in range(6):
        if stage:
            register_checkpoint(root, "no_skill", "h0", stage, "", provenance="fixture_unchanged_baseline")
        for benchmark in BENCHMARKS:
            run = generate(root, method="no_skill", history="h0", stage=stage, benchmark=benchmark,
                           fixture_solve=fixture_solve)
            for key in counts:
                counts[key] += run[key]
            score_checkpoint(root, method="no_skill", history="h0", stage=stage, benchmark=benchmark,
                             fixture_score=fixture_score)
    result = report(root)
    return {"evidence_kind": "engineering_fixture", "benchmarks": 5, "checkpoints": 6, **counts,
            "report_hash": result["record_hash"], "real_model_calls": 0, "real_benchmark_runs": 0,
            "hidden_score_feedback_to_solver": False,
            "meaning": "Orchestration/replay only; no Skill, Research or generalization effect."}
