"""Offline orchestration integration; no API, containers, or method-effect evidence.

Real plans, checkpoints, receipts, learner adapters/gates/replay and reports run.
Inference/native execution are authored fixtures; the optional official GEPA
optimizer is replaced at its entry point, not represented as an official run.
"""
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import continue_fivebench_baselines as sequence
from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import runner
from skillopt.continual_eval.core import BENCHMARKS, freeze_plan, read_json, write_json
from skillopt.continual_learning import gepa, skillopt
from tests.test_continual_learning_domains import API, evaluate, setup

# Native append intentionally retains these bytes; reuse must not strip them.
SKILL = "\n\nUse the requested constant result.\n"
SERVICE = {"fixture": "offline-domain-controls"}


def reseal(path, **changes):
    value = read_json(path, sealed=True)
    value.pop("record_hash")
    value.update(changes)
    path.write_text(json.dumps(seal(value)))


@pytest.fixture
def study(tmp_path, monkeypatch, request):
    """Exercise actual orchestration and completed evidence replay in-process."""
    root = tmp_path / "study"
    counters = {"evaluated_cells": [], "learning_started": [], "api_calls": []}
    control = {"pending": None, "cleanup": False, "open_model": False, "no_update": False}
    recovery = getattr(request, "param", None) == "distinct-v2"
    baseline_service = deepcopy(SERVICE)
    if recovery:
        from skillopt.validator_pilot.api import long_stream_service

        baseline_service = long_stream_service(
            {**baseline_service, "timeout_seconds": {"connect": 20, "read": 300, "write": 30, "pool": 20}},
            read_timeout_seconds=300, stream_wall_seconds=1800)
        # Native qualification has its own replay suite. These authored
        # contracts only distinguish old/new scorer routing, not engine fitness.
        monkeypatch.setattr("skillopt.continual_eval.sheet_recalc_adapter.qualified_engine", lambda _: None)
        monkeypatch.setattr("skillopt.continual_eval.sheet_numeric_adapter.qualified_engine", lambda _: None)
    learning_service = ({**baseline_service, "stream_max_wall_seconds": 3600,
                         "delivery_retry_policy": "closed_network_error_v1"} if recovery else baseline_service)
    client_options, qualification_checks = [], []
    original_generate, original_score = runner.generate, runner.score_checkpoint
    original_skillopt, original_gepa = skillopt.run_stage, gepa.run_stage

    class Client:
        service = baseline_service

        def __init__(self, *args, **kwargs):
            client_options.append(deepcopy(kwargs))
            is_learning = kwargs.get("delivery_retry_policy") == "closed_network_error_v1"
            if recovery and is_learning:
                self.service = learning_service
                if control.get("learning_service_mismatch"):
                    self.service = {**self.service, "temperature": 99}
            elif recovery and control.get("evaluation_service_mismatch"):
                self.service = learning_service

        def close(self):
            pass

    monkeypatch.setattr("skillopt.validator_pilot.api.CachedAPI", Client)

    def generate(output, **kwargs):
        method = kwargs["method"]
        write_json(Path(output) / "model_service.json", seal(baseline_service))
        if method != "no_skill":
            counters["evaluated_cells"].append((method, kwargs["benchmark"], kwargs["stage"]))
        def solve(benchmark, public, text, call, *, runtime):
            return {"status": "available", "output": "authored fixture output", "reason": "fixture"}
        return original_generate(output, **kwargs, fixture_solve=solve)

    def score(output, **kwargs):
        def fixture_score(*args, **unused):
            return {"status": "pass", "score": 1., "metrics": {}, "reason": "fixture"}
        return original_score(output, **kwargs, fixture_score=fixture_score)

    monkeypatch.setattr(runner, "generate", generate)
    monkeypatch.setattr(runner, "score_checkpoint", score)

    def invoke(reference, operation, request, output, *, log):
        return sequence.worker(operation, request, output)

    monkeypatch.setattr(sequence, "_invoke", invoke)

    class ReflectionAPI(API):
        def __init__(self, method, parent):
            super().__init__(no_update=bool(parent) or control["no_update"])
            self.method = method
            self.service = learning_service

        def call(self, *args, **kwargs):
            if control["open_model"]:
                raise RuntimeError("Authored fixture interruption after durable call intent")
            row = super().call(*args, **kwargs)
            if recovery:
                row["attempts"] = [{"usage": deepcopy(row["usage"])}]
            counters["api_calls"].append(row["request_hash"])
            if self.method == "gepa":
                row["response"] = "" if control["no_update"] else SKILL
            return row

    class OptimizerFixture:
        @staticmethod
        def optimize(**kwargs):
            adapter, parent = kwargs["adapter"], kwargs["seed_candidate"]
            base = adapter.evaluate_rows(kwargs["valset"], parent)
            adapter.evaluate_rows(kwargs["trainset"], parent)
            candidate = {"skill": kwargs["reflection_lm"]("Authored fixture, no private labels.")}
            proposed = adapter.evaluate_rows(kwargs["valset"], candidate)
            scores = [sum(r["score"] for r in batch) / len(batch) for batch in (base, proposed)]
            candidates = [parent, candidate]
            return SimpleNamespace(best_candidate=candidates[max(range(2), key=lambda i: scores[i])],
                                   to_dict=lambda: {"candidates": candidates, "val_aggregate_scores": scores})

    monkeypatch.setattr(gepa, "official_gepa", lambda _: (OptimizerFixture(), {"fixture_only": "offline"}))

    def learn(manifest, panel, output, *, repo=None, gepa_source=None):
        if not (Path(output) / "result.json").exists():
            counters["learning_started"].append((manifest["method"], panel["benchmark"]))
        api = ReflectionAPI(manifest["method"], manifest["parent_skill"])
        def execute(task, text):
            prediction, outcome = evaluate(panel["benchmark"])(task, text)
            if control["pending"] == panel["benchmark"]:
                reason = "container_cleanup_unconfirmed" if control["cleanup"] else "fixture_unavailable"
                outcome = {"status": "unknown", "score": None, "metrics": {}, "reason": reason}
                if control["cleanup"]:
                    outcome["execution_costs"] = {"container_calls": 1}
            return prediction, outcome
        if manifest["method"] == "skillopt":
            return original_skillopt(manifest, panel, output, fixture_api=api, fixture_evaluate=execute)
        return original_gepa(manifest, panel, output, gepa_source=gepa_source,
                             fixture_api=api, fixture_evaluate=execute)

    monkeypatch.setattr(skillopt, "run_stage", learn)
    monkeypatch.setattr(gepa, "run_stage", learn)
    references = {}
    for benchmark in BENCHMARKS:
        baseline = tmp_path / ("baseline-" + benchmark)
        auth, panel, _ = setup(benchmark)
        path = tmp_path / (benchmark + "-panel.json")
        write_json(path, panel)
        config = {"version": "continual-eval-v2", "order": list(BENCHMARKS),
                  "panels": {b: str(path) if b == benchmark else None for b in BENCHMARKS},
                  "partition": "development", "methods": ["no_skill"], "histories": ["h0"],
                  "repeats": 2, "model": auth["model"], "runtime": {},
                  "project_disjoint": False, "exposure_manifest": None}
        if recovery and benchmark == "spreadsheetbench":
            config["runtime"] = {benchmark: {"spreadsheet_scorer": "qualified_lo_recalc_v5_v1",
                "recalculation": {"image": "fixture-image-not-executed", "timeout_seconds": 20}}}
        freeze_plan(config, baseline)
        write_json(baseline / "model_service.json", seal(baseline_service))
        generate(baseline, method="no_skill", history="h0", stage=0, benchmark=benchmark)
        score(baseline, method="no_skill", history="h0", stage=0, benchmark=benchmark)
        references[benchmark] = {"root": str(baseline), "source": str(Path(__file__).resolve().parents[1]),
                                 "python": sys.executable}
    config = {"version": sequence.VERSION, "references": references,
              "families": {b: {"train": 2, "selection": 2} for b in BENCHMARKS},
              "budget": auth["budget"], "seed": 19,
              "native_lock": str(tmp_path / "native.lock"), "workers": 1,
              "learning_sheet_qualification": None}
    if recovery:
        from skillopt.continual_learning.recovery import POLICY

        qualification = tmp_path / "fixture-qualification.json"
        write_json(qualification, seal({"evidence_kind": "authored_fixture_no_native_execution"}))
        config.update(version=sequence.RECOVERY_SEQUENCE, learning_recovery_policy=deepcopy(POLICY),
                      learning_sheet_scorer="qualified_lo_recalc_v7_v1",
                      learning_sheet_qualification=str(qualification))
        def readiness(runtime):
            qualification_checks.append(deepcopy(runtime))
            return {"status": "ready"}
        monkeypatch.setattr("skillopt.continual_eval.sheet_numeric_adapter.readiness", readiness)
    config_path = tmp_path / "config.json"
    write_json(config_path, config)
    protocol = sequence.prepare(config_path, root)

    def run(method="skillopt"):
        return sequence.run(root, method, repo=tmp_path, gepa_source=tmp_path)

    return SimpleNamespace(root=root, run=run, counters=counters, control=control, protocol=protocol,
                           baseline_service=baseline_service, learning_service=learning_service,
                           client_options=client_options, qualification_checks=qualification_checks)


def stages(study, method="skillopt"):
    return [read_json(study.root / method / f"s{i}-{b}/stage.json", sealed=True)
            for i, b in enumerate(BENCHMARKS, 1)]


def test_all_five_stages_two_methods_share_real_policy_evidence_and_replay(study):
    first = study.run()
    assert first["status"] == "completed" and first["completed_learning_stages"] == 5
    assert len(study.counters["evaluated_cells"]) == 5
    second = study.run("gepa")
    assert second["status"] == "completed" and second["final_skill"] == first["final_skill"] == SKILL
    assert len(study.counters["evaluated_cells"]) == 5  # Not another 25 or another method's five.
    assert len(list((study.root / "evaluated_policies").glob("*.json"))) == 5
    for method in ("skillopt", "gepa"):
        previous = None
        for row in stages(study, method):
            assert row["parent_stage_hash"] == previous
            assert set(row["cells"]) == set(BENCHMARKS)
            assert row["learning_scores_used_from_evaluation"] is False
            previous = row["record_hash"]
        if method == "gepa":
            assert all(cell["reused"] and not cell["independent_new_observation"]
                       for row in stages(study, method) for cell in row["cells"].values())
    before = deepcopy(study.counters)
    assert study.run() == first and study.run("gepa") == second
    assert study.counters == before


def test_v2_runs_v4_learning_but_retains_original_evaluation(study):
    from skillopt.continual_learning.recovery import POLICY

    model = deepcopy(study.protocol['model'])
    model['transport']['stream_wall_seconds'] = 3600
    config = {**study.protocol['config'], 'version': sequence.RECOVERY_SEQUENCE,
              'learning_recovery_policy': POLICY, 'learning_sheet_scorer': 'qualified_lo_recalc_v7_v1'}
    reseal(study.root / 'protocol.json', version=sequence.RECOVERY_SEQUENCE, config=config,
           model=model, learning_version='continual-learning-v4',
           learning_model_service=seal(SERVICE), learning_client_options={})
    result = study.run()
    assert result['version'] == sequence.RECOVERY_SEQUENCE and result['completed_learning_stages'] == 5
    assert len(study.counters['evaluated_cells']) == 5
    for i, benchmark in enumerate(BENCHMARKS, 1):
        value = read_json(study.root / f'skillopt/s{i}-{benchmark}/manifest.json', sealed=True)
        assert value['version'] == 'continual-learning-v4' and value['recovery_policy'] == POLICY
        assert value['model']['transport']['stream_wall_seconds'] == 3600
        if i == 1:
            for target in BENCHMARKS:
                path = study.root / f'skillopt/s1-{benchmark}/evaluations/{target}/plan.json'
                assert read_json(path, sealed=True)['config']['model']['transport']['stream_wall_seconds'] == 1800
    before = deepcopy(study.counters)
    assert study.run() == result and before == study.counters


def test_changed_future_panel_after_stage_one_blocks_next_stage(study, monkeypatch):
    original = sequence.transition
    changed = False

    def transition(*args):
        nonlocal changed
        result = original(*args)
        if not changed:
            path = Path(study.protocol['roles']['searchqa']['path'])
            path.write_text(path.read_text() + '\n')
            changed = True
        return result

    monkeypatch.setattr(sequence, 'transition', transition)
    with pytest.raises(ValueError, match='Frozen input changed'):
        study.run()
    assert len(study.counters['learning_started']) == 1


def test_pending_carries_parent_and_continues_without_claiming_full_learning(study):
    study.control["pending"] = "searchqa"
    result = study.run()
    rows = stages(study)
    assert result["status"] == "attempts_finished_with_pending"
    assert result["completed_learning_stages"] == 4 and result["attempted_stages"] == 5
    assert rows[2]["action"] == "pending_carry_parent" and rows[2]["skill"] == rows[1]["skill"]
    assert rows[3]["parent_skill"] == rows[2]["skill"]
    assert len(study.counters["evaluated_cells"]) == 5


def test_both_methods_unchanged_empty_parent_only_reference_historical_s0(study):
    study.control["no_update"] = True
    for method in ("skillopt", "gepa"):
        result = study.run(method)
        assert result["status"] == "completed" and result["final_skill"] == ""
        assert all(row["action"] == "completed_no_update" for row in stages(study, method))
        assert all(cell["kind"] == "historical_empty_policy" and cell["reused"]
                   and cell["new_model_calls"] == 0 and not cell["independent_new_observation"]
                   for row in stages(study, method) for cell in row["cells"].values())
    assert not study.counters["evaluated_cells"]


@pytest.mark.parametrize("artifact", ["learning_result", "learning_call", "evaluation_score", "parent_chain"])
def test_completed_replay_rejects_changed_or_missing_real_evidence(study, artifact):
    study.run()
    before = deepcopy(study.counters)
    first = study.root / "skillopt/s1-bigcodebench"
    if artifact == "learning_result":
        (first / "learning/result.json").unlink()
    elif artifact == "learning_call":
        path = next((first / "learning/calls").glob("*.json"))
        receipt = read_json(path, sealed=True)["receipt"]
        receipt["response"] += " changed"
        reseal(path, receipt=receipt)
    elif artifact == "evaluation_score":
        next((first / "evaluations/bigcodebench/host_only/scores").glob("*.json")).unlink()
    else:
        reseal(study.root / "skillopt/s2-spreadsheetbench/stage.json", parent_stage_hash="f" * 64)
    with pytest.raises((ValueError, FileNotFoundError)):
        study.run()
    assert study.counters == before


def test_begun_unfinished_stage_is_not_retried(study):
    directory = study.root / "skillopt/s1-bigcodebench"
    directory.mkdir(parents=True)
    with pytest.raises(ValueError, match="Interrupted stage"):
        study.run()
    assert not study.counters["learning_started"] and not study.counters["evaluated_cells"]


def test_registry_must_bind_its_policy_text_to_actual_evaluation(study):
    study.run()
    path = next((study.root / "evaluated_policies").glob("*.json"))
    entry = read_json(path, sealed=True)
    changed_skill = "This text was never evaluated."
    ref = study.protocol["references"][entry["cell"]["result"]["benchmark"]]
    forged = study.root / "evaluated_policies" / (sequence.policy_key(ref, changed_skill) + ".json")
    write_json(forged, seal({"protocol_hash": entry["protocol_hash"], "skill": changed_skill, "cell": entry["cell"]}))
    before = deepcopy(study.counters)
    with pytest.raises(ValueError):
        study.run("gepa")
    assert study.counters == before


def test_cleanup_unknown_cannot_start_the_next_domain(study):
    study.control.update(pending="bigcodebench", cleanup=True)
    with pytest.raises(ValueError, match="(?i)(cleanup|resource|closed|unsafe)"):
        study.run()
    assert study.counters["learning_started"] == [("skillopt", "bigcodebench")]
    assert not study.counters["evaluated_cells"]


def test_open_model_intent_cannot_advance_to_the_next_domain(study):
    study.control["open_model"] = True
    with pytest.raises(ValueError, match="Open model intents"):
        study.run()
    assert study.counters["learning_started"] == [("skillopt", "bigcodebench")]
    assert not study.counters["evaluated_cells"]


def test_actual_service_change_fails_before_learning_or_evaluation(study, monkeypatch):
    monkeypatch.setattr("skillopt.validator_pilot.api.CachedAPI.service", {"fixture": "different-service"})
    with pytest.raises(ValueError, match="frozen model service"):
        study.run()
    assert not study.counters["learning_started"] and not study.counters["evaluated_cells"]


def test_completed_stage_cannot_omit_an_evaluation_domain(study):
    study.run()
    path = study.root / "skillopt/s1-bigcodebench/stage.json"
    cells = read_json(path, sealed=True)["cells"]
    cells.pop("alfworld")
    reseal(path, cells=cells)
    before = deepcopy(study.counters)
    with pytest.raises(ValueError, match="(?i)(domain|cell|matrix)"):
        study.run()
    assert study.counters == before


@pytest.mark.parametrize("study", ["distinct-v2"], indirect=True)
def test_v2_real_prepare_and_all_stages_keep_learning_and_eval_services_separate(study):
    protocol = study.protocol
    assert protocol["learning_model_service"] == seal(study.learning_service)
    assert study.learning_service != study.baseline_service
    assert protocol["methods"] == ["skillopt"]
    assert len(study.qualification_checks) == 1
    assert study.qualification_checks[0]["spreadsheet_scorer"] == "qualified_lo_recalc_v7_v1"
    assert protocol["roles"]["spreadsheetbench"]["runtime"] == study.qualification_checks[0]
    originals = {str(path): path.read_bytes() for ref in protocol["references"].values()
                 for path in Path(ref["root"]).rglob("*.json")}
    result = study.run()
    assert result["status"] == "completed" and result["completed_learning_stages"] == 5
    assert len(study.counters["evaluated_cells"]) == 5
    for index, row in enumerate(stages(study), 1):
        directory = study.root / f"skillopt/s{index}-{row['benchmark']}"
        value = read_json(directory / "manifest.json", sealed=True)
        assert value["version"] == "continual-learning-v4"
        assert value["model"]["transport"]["stream_wall_seconds"] == 3600
        assert read_json(directory / "learning/model_service.json", sealed=True) == seal(study.learning_service)
        for cell in row["cells"].values():
            assert cell["result"]["model_service"] == seal(study.baseline_service)
            if index > 1:
                assert cell["reused"] and cell["new_model_calls"] == 0
    assert len(study.client_options) == 6  # One learning preflight + five old-source eval clients.
    assert study.client_options[0]["stream_wall_seconds"] == 3600
    assert study.client_options[0]["delivery_retry_policy"] == "closed_network_error_v1"
    assert all(options["stream_wall_seconds"] == 1800 and "delivery_retry_policy" not in options
               for options in study.client_options[1:])
    sheet = study.root / "skillopt/s1-bigcodebench/evaluations/spreadsheetbench/plan.json"
    old_runtime = read_json(sheet, sealed=True)["config"]["runtime"]["spreadsheetbench"]
    assert old_runtime["spreadsheet_scorer"] == "qualified_lo_recalc_v5_v1"
    assert "qualification_path" not in old_runtime["recalculation"]
    before = deepcopy(study.counters)
    assert study.run() == result and study.counters == before
    assert originals == {str(path): path.read_bytes() for ref in protocol["references"].values()
                         for path in Path(ref["root"]).rglob("*.json")}
    with pytest.raises(ValueError, match="Unsupported method"):
        study.run("gepa")
    assert study.counters == before


@pytest.mark.parametrize("study", ["distinct-v2"], indirect=True)
def test_v2_learning_service_drift_stops_before_any_learning_call(study):
    study.control["learning_service_mismatch"] = True
    with pytest.raises(ValueError, match="frozen model service"):
        study.run()
    assert not study.counters["learning_started"] and not study.counters["evaluated_cells"]
    assert not study.counters["api_calls"]


@pytest.mark.parametrize("study", ["distinct-v2"], indirect=True)
def test_v2_recovery_service_is_rejected_by_old_evaluation_worker_before_generation(study):
    study.control["evaluation_service_mismatch"] = True
    with pytest.raises(ValueError, match="frozen model service"):
        study.run()
    assert study.counters["learning_started"] == [("skillopt", "bigcodebench")]
    assert len(study.counters["api_calls"]) == 1
    assert not study.counters["evaluated_cells"]
    assert not list((study.root / "skillopt/s1-bigcodebench/evaluations/bigcodebench/predictions").glob("*"))


@pytest.mark.parametrize("study", ["distinct-v2"], indirect=True)
@pytest.mark.parametrize("mutation", ["source", "panel"])
def test_frozen_change_while_waiting_for_native_lock_blocks_first_paid_stage(study, monkeypatch, mutation):
    import fcntl

    original_lock, original_sources = fcntl.flock, sequence._source_files
    waiting_change = False
    def sources():
        value = original_sources()
        if waiting_change and mutation == "source":
            value[next(iter(value))] = "f" * 64
        return value
    def lock(fd, operation):
        nonlocal waiting_change
        result = original_lock(fd, operation)
        # output_lock uses EX|NB. The blocking EX here is the native queue lock.
        if operation == fcntl.LOCK_EX and not waiting_change:
            waiting_change = True
            if mutation == "panel":
                path = Path(study.protocol["roles"]["bigcodebench"]["path"])
                path.write_bytes(path.read_bytes() + b"\n")
        return result
    monkeypatch.setattr(sequence, "_source_files", sources)
    monkeypatch.setattr(fcntl, "flock", lock)
    with pytest.raises(ValueError, match="learning sources changed|Frozen input changed"):
        study.run()
    assert waiting_change and not study.client_options
    assert not study.counters["learning_started"] and not study.counters["api_calls"]


def test_actual_cached_client_matches_v2_service_derivation_without_any_http(tmp_path, monkeypatch):
    import httpx

    from skillopt.validator_pilot import api as provider

    monkeypatch.setattr(provider, "_configuration", lambda *a, **k: (
        "https://open.bigmodel.cn/api/paas/v4/chat/completions", "OFFLINE_TEST_NOT_A_KEY"))
    original_client = httpx.Client
    calls = []
    def forbidden(request):
        calls.append(request)
        pytest.fail("Service preflight must not submit HTTP requests")
    monkeypatch.setattr(provider.httpx, "Client", lambda **kwargs: original_client(
        transport=httpx.MockTransport(forbidden), **kwargs))
    _, _, args = setup(natural=True)
    old_model = args["model"]
    with provider.CachedAPI(tmp_path, tmp_path / "original", provider=old_model["provider"],
                            model=old_model["name"], reasoning_effort=old_model["reasoning_effort"],
                            workers=1, **old_model["transport"]) as client:
        original_service = deepcopy(client.service)
    derived = provider.long_stream_service(original_service, read_timeout_seconds=300, stream_wall_seconds=3600)
    derived["delivery_retry_policy"] = "closed_network_error_v1"
    new_model = deepcopy(old_model)
    new_model["transport"]["stream_wall_seconds"] = 3600
    sequence.check_client_service(tmp_path, new_model, tmp_path / "learning", seal(derived),
                                  client_options={"delivery_retry_policy": "closed_network_error_v1"})
    sequence.check_client_service(tmp_path, old_model, tmp_path / "evaluation", seal(original_service))
    with pytest.raises(ValueError, match="frozen model service"):
        sequence.check_client_service(tmp_path, new_model, tmp_path / "wrong-evaluation", seal(original_service),
                                      client_options={"delivery_retry_policy": "closed_network_error_v1"})
    with pytest.raises(ValueError, match="frozen model service"):
        sequence.check_client_service(tmp_path, old_model, tmp_path / "wrong-learning", seal(derived))
    assert not calls
    assert original_service["stream_max_wall_seconds"] == 1800
    assert "delivery_retry_policy" not in original_service
