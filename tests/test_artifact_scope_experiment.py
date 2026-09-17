"""Artifact adapter/control-flow checks without real task generation or APIs."""
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from skillopt.cross_domain import evolution
from skillopt.cross_domain import experiment as core
from skillopt.cross_domain.runtime import read_json, write_json
from skillopt.scope_evolution_v2 import experiment as artifact


def _bindings():
    return (core.dataset, core.rollout, core._code_hashes, evolution.rollout, evolution.MECHANISMS)


@pytest.fixture(autouse=True)
def restore_adapter_bindings():
    """A failed restoration assertion must not contaminate the rest of the suite."""
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip
    original = _bindings()
    transports = [module.chat_optimizer for module in (reflect, aggregate, clip)]
    yield
    (core.dataset, core.rollout, core._code_hashes, evolution.rollout, evolution.MECHANISMS) = original
    for module, transport in zip((reflect, aggregate, clip), transports):
        module.chat_optimizer = transport


@pytest.mark.parametrize("fail_in_body", [False, True])
def test_adapter_restores_v1_bindings_after_normal_or_exceptional_exit(fail_in_body):
    old = _bindings()
    try:
        with artifact.artifact_adapter({"mechanisms": ["constraint_preservation"]}):
            assert core.dataset is artifact.artifact_dataset
            assert core.rollout is evolution.rollout is artifact.artifact_rollout
            assert core._code_hashes is artifact.code_hashes
            assert evolution.MECHANISMS == ("constraint_preservation",)
            if fail_in_body:
                raise RuntimeError("simulated body failure")
    except RuntimeError as error:
        assert fail_in_body and str(error) == "simulated body failure"
    assert _bindings() == old


@pytest.mark.parametrize("protocol", [{}, {"mechanisms": None}, {"mechanisms": []}, {"mechanisms": ["unsupported"]}])
def test_adapter_entry_failure_does_not_partially_change_v1_globals(protocol):
    old = _bindings()
    with pytest.raises((KeyError, TypeError, ValueError)):
        with artifact.artifact_adapter(protocol):
            pytest.fail("Invalid protocol must not enter the adapted body")
    assert _bindings() == old


@pytest.mark.parametrize("fail_in_body", [False, True])
def test_adapter_restores_transport_bindings_changed_by_candidate_engine(fail_in_body):
    from skillopt.gradient import aggregate, reflect
    from skillopt.optimizer import clip
    modules = (reflect, aggregate, clip)
    old = [module.chat_optimizer for module in modules]
    try:
        with artifact.artifact_adapter({"mechanisms": ["constraint_preservation"]}):
            for module in modules:
                module.chat_optimizer = object()  # Simulate cached transport installation only.
            if fail_in_body:
                raise RuntimeError("simulated optimizer-stage failure")
    except RuntimeError:
        assert fail_in_body
    assert [module.chat_optimizer for module in modules] == old


def _protocol():
    return {"mechanisms": ["constraint_preservation"], "source_screen_range": [0.25, 0.75],
            "train_per_cell": 4, "dev_per_cell": 4, "seed": 7,
            "model": "offline-model", "workers": 1, "difficulty": "hard"}


def _pilot_rows(scores, *, ok=True, group="positive", mechanism="constraint_preservation"):
    return [{"id": f"{mechanism}-{group}-{i}", "mechanism": mechanism,
             "group": group, "hard": score, "agent_ok": ok} for i, score in enumerate(scores)]


def _pilot_files(root, train, dev):
    write_json(root / "rollouts/pilot_train.json", train)
    write_json(root / "rollouts/pilot_dev.json", dev)


@pytest.mark.parametrize("train,dev,passed", [
    ([1, 0, 0, 0], [1, 1, 1, 0], True),  # Both inclusive bounds.
    ([1, 1, 0, 0], [1, 1, 0, 0], True),
    ([1, 1, 1, 1], [1, 1, 0, 0], False),
    ([1, 1, 0, 0], [1, 1, 1, 1], False),
    ([0, 0, 0, 0], [1, 1, 0, 0], False),
])
def test_headroom_requires_bounded_accuracy_on_both_train_and_dev(tmp_path, train, dev, passed):
    _pilot_files(tmp_path, _pilot_rows(train), _pilot_rows(dev))
    result = artifact.learnability_screen(tmp_path, _protocol())
    assert result["all_tracks_pass"] is passed
    assert result["not_a_benefit_or_safety_certificate"] is True
    assert result["test_accessed"] is False
    assert read_json(tmp_path / "learnability_screen.json") == result


@pytest.mark.parametrize("problem", ["empty", "api_error", "only_protected"])
def test_incomplete_screen_aborts_instead_of_treating_failure_as_headroom(tmp_path, problem):
    bad = [] if problem == "empty" else _pilot_rows([1, 1, 0, 0], ok=problem != "api_error",
                                                   group="near_miss" if problem == "only_protected" else "positive")
    _pilot_files(tmp_path, _pilot_rows([1, 1, 0, 0]), bad)
    with pytest.raises(ValueError, match="Incomplete"):
        artifact.learnability_screen(tmp_path, _protocol())
    assert not (tmp_path / "learnability_screen.json").exists()


@pytest.mark.parametrize("problem", [
    "partial", "duplicate", "missing_id", "bool_score", "float_score", "invalid_score", "truthy_agent_ok",
])
def test_source_screen_rejects_partial_duplicate_or_malformed_cached_rows(tmp_path, problem):
    rows = _pilot_rows([1, 1, 0, 0])
    if problem == "partial":
        rows = [rows[0], rows[2]]  # EM=.5 would pass if completeness were ignored.
    elif problem == "duplicate":
        rows[1]["id"] = rows[0]["id"]
    elif problem == "missing_id":
        rows[1]["id"] = None
    elif problem == "truthy_agent_ok":
        rows[1]["agent_ok"] = "true"
    else:
        rows[1]["hard"] = {"bool_score": True, "float_score": 1.0, "invalid_score": 2}[problem]
    _pilot_files(tmp_path, rows, _pilot_rows([1, 1, 0, 0]))
    with pytest.raises(ValueError, match="Incomplete or invalid"):
        artifact.learnability_screen(tmp_path, _protocol())
    assert not (tmp_path / "learnability_screen.json").exists()


def _candidate(**changes):
    return {"id": "candidate", "content": "A nonempty learned procedure.", "dev_em": 0.75,
            "previous_dev_em": 0.5, "accepted_local_point_gate": True, **changes}


@pytest.mark.parametrize("selected,passed", [
    ([_candidate()], True),
    ([], False),
    ([_candidate(accepted_local_point_gate=False)], False),
    ([_candidate(dev_em=0.5)], False),
    ([_candidate(dev_em=0.25)], False),
    ([_candidate(), _candidate(id="second", accepted_local_point_gate=False)], False),
])
def test_source_update_needs_every_selected_candidate_accepted_and_improving(tmp_path, selected, passed):
    write_json(tmp_path / "candidates.json", {"selected": selected})
    result = artifact.source_update_screen(tmp_path)
    assert result["all_tracks_show_source_gain"] is passed
    assert result["not_a_statistical_scope_certificate"] is True


@pytest.mark.parametrize("changes", [
    {"content": ""}, {"content": "   "}, {"accepted_local_point_gate": "false"},
    {"dev_em": float("inf")}, {"dev_em": 1.5}, {"previous_dev_em": -0.5},
])
def test_invalid_candidate_cannot_pass_source_update_screen(tmp_path, changes):
    write_json(tmp_path / "candidates.json", {"selected": [_candidate(**changes)]})
    try:
        result = artifact.source_update_screen(tmp_path)
    except (ValueError, TypeError):
        return  # Rejecting malformed cached evidence is also a safe outcome.
    assert result["all_tracks_show_source_gain"] is False


@pytest.mark.parametrize("field", ["dev_em", "previous_dev_em"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_candidate_scores_produce_standard_json_and_futility(tmp_path, field, value):
    write_json(tmp_path / "candidates.json", {"selected": [_candidate(**{field: value})]})
    result = artifact.source_update_screen(tmp_path)
    assert result["all_tracks_show_source_gain"] is False
    assert result["selected"][0][field] is None
    assert result["selected"][0]["invalid_score_fields"] == [field]
    json.dumps(result, allow_nan=False)
    output = (tmp_path / "source_update_screen.json").read_text(encoding="utf-8")
    parsed = json.loads(output, parse_constant=lambda value: pytest.fail(f"Nonstandard JSON constant: {value}"))
    assert parsed == result


def test_duplicate_candidate_ids_cannot_satisfy_multiple_source_tracks(tmp_path):
    write_json(tmp_path / "candidates.json", {"selected": [_candidate(), _candidate(dev_em=1.0)]})
    result = artifact.source_update_screen(tmp_path)
    assert result["all_tracks_show_source_gain"] is False
    assert len(result["selected"]) == 2  # Preserve invalid evidence for audit.


@pytest.mark.parametrize("changed", ["protocol", "provider", "generator"])
def test_manifest_refuses_changed_run_identity_and_preserves_existing_manifest(tmp_path, changed):
    repo, root = tmp_path / "repo", tmp_path / "run"
    generator = repo / "skillopt/scope_evolution_v2/tasks.py"
    generator.parent.mkdir(parents=True)
    generator.write_text("# fixed offline generator\n", encoding="utf-8")
    protocol, provider = _protocol(), {"provider_host": "offline.invalid", "model": "offline-model"}
    artifact.prepare(repo, root, protocol, provider)
    original = (root / "protocol.json").read_bytes()
    artifact.prepare(repo, root, protocol, provider)
    assert (root / "protocol.json").read_bytes() == original
    if changed == "protocol":
        protocol = {**protocol, "seed": 8}
    elif changed == "provider":
        provider = {**provider, "model": "another-offline-model"}
    else:
        generator.write_text("# changed offline generator\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Changed protocol/provider/generator"):
        artifact.prepare(repo, root, protocol, provider)
    assert (root / "protocol.json").read_bytes() == original


@pytest.mark.parametrize("failure_stage", ["headroom", "source_update", "nan_update", "inf_update"])
def test_cli_futility_stops_before_validation_and_test(tmp_path, monkeypatch, capsys, failure_stage):
    repo, root = tmp_path / "fake-repo", tmp_path / "fake-repo/outputs/offline"
    protocol = _protocol()
    write_json(repo / "config.json", protocol)
    # Relocate only the module's path metadata; no actual source file is edited.
    monkeypatch.setattr(artifact, "__file__", str(repo / "skillopt/scope_evolution_v2/experiment.py"))
    monkeypatch.setattr(artifact, "configure_api", lambda *_: {"offline": True})
    monkeypatch.setattr(artifact, "prepare", lambda *_: None)
    monkeypatch.setattr(artifact, "CachedAPI", lambda out, *_: SimpleNamespace(root=out))
    calls = []

    def pilot(api, config):
        calls.append("pilot")
        scores = [1, 1, 1, 1] if failure_stage == "headroom" else [1, 1, 0, 0]
        _pilot_files(api.root, _pilot_rows(scores), _pilot_rows(scores))

    def dataset(out, config, split):
        calls.append("dataset:" + split)
        assert split in {"train", "dev"}
        return []

    def candidates(api, train, dev, config):
        calls.append("candidates")
        selected = _candidate(dev_em=0.5, accepted_local_point_gate=False)
        if failure_stage in {"nan_update", "inf_update"}:
            selected = _candidate(dev_em=float("nan") if failure_stage == "nan_update" else float("inf"))
        write_json(api.root / "candidates.json", {"selected": [selected]})

    def forbidden(*args, **kwargs):
        pytest.fail("Futile source experiment must not access validation/test")

    monkeypatch.setattr(core, "pilot", pilot)
    monkeypatch.setattr(artifact, "artifact_dataset", dataset)
    monkeypatch.setattr(evolution, "generate_candidates", candidates)
    monkeypatch.setattr(core, "validate", forbidden)
    monkeypatch.setattr(core, "test", forbidden)
    original = _bindings()
    artifact.main(["--config", "config.json", "--out", "outputs/offline", "--phase", "all"])
    assert _bindings() == original
    assert "[futility]" in capsys.readouterr().out
    assert calls == (["pilot"] if failure_stage == "headroom" else
                     ["pilot", "dataset:train", "dataset:dev", "candidates"])
    assert not (root / "datasets/validation.json").exists()
    assert not (root / "datasets/test.json").exists()
    if failure_stage in {"nan_update", "inf_update"}:
        json.dumps(read_json(root / "source_update_screen.json"), allow_nan=False)


def test_source_screens_do_not_mutate_supplied_protocol(tmp_path):
    protocol = _protocol()
    before = deepcopy(protocol)
    _pilot_files(tmp_path, _pilot_rows([1, 1, 0, 0]), _pilot_rows([1, 1, 0, 0]))
    artifact.learnability_screen(tmp_path, protocol)
    assert protocol == before
