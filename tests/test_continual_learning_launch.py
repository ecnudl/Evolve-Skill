"""ALF process setup fixtures; no native episode, generated code, or paid call."""
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from skillopt.continual_learning.launch import learning_environment


def auth(tmp_path, *, provider="bigmodel", benchmark="alfworld"):
    root = tmp_path / "data"
    (root / "logic").mkdir(parents=True)
    (root / "logic/alfred.pddl").write_text("fixture domain")
    (root / "logic/alfred.twl2").write_text("fixture grammar")
    return {"benchmark": benchmark, "model": {"provider": provider},
            "runtime": {"alfworld_data": str(root)}}


def test_unset_environment_is_bound_to_manifest_and_restored(tmp_path, monkeypatch):
    value = auth(tmp_path)
    monkeypatch.delenv("ALFWORLD_DATA", raising=False)
    with learning_environment(value):
        assert os.environ["ALFWORLD_DATA"] == value["runtime"]["alfworld_data"]
    assert "ALFWORLD_DATA" not in os.environ


def test_existing_matching_environment_preserved_on_failure(tmp_path, monkeypatch):
    value = auth(tmp_path)
    root = value["runtime"]["alfworld_data"]
    monkeypatch.setenv("ALFWORLD_DATA", root)
    with pytest.raises(RuntimeError, match="test failure"):
        with learning_environment(value):
            raise RuntimeError("test failure")
    assert os.environ["ALFWORLD_DATA"] == root


def test_unset_environment_restored_on_failure(tmp_path, monkeypatch):
    value = auth(tmp_path)
    monkeypatch.delenv("ALFWORLD_DATA", raising=False)
    with pytest.raises(RuntimeError):
        with learning_environment(value):
            raise RuntimeError("fixture Pending/error")
    assert "ALFWORLD_DATA" not in os.environ


def test_conflicting_environment_rejected_before_dispatch(tmp_path, monkeypatch):
    value = auth(tmp_path)
    monkeypatch.setenv("ALFWORLD_DATA", "/another/frozen/root")
    with pytest.raises(ValueError, match="differs"):
        with learning_environment(value):
            pytest.fail("Must not dispatch learner")
    assert os.environ["ALFWORLD_DATA"] == "/another/frozen/root"


@pytest.mark.parametrize("missing", ["alfred.pddl", "alfred.twl2"])
def test_missing_native_logic_rejected_without_environment_mutation(tmp_path, monkeypatch, missing):
    value = auth(tmp_path)
    (tmp_path / "data/logic" / missing).unlink()
    monkeypatch.delenv("ALFWORLD_DATA", raising=False)
    with pytest.raises(ValueError, match="unavailable"):
        with learning_environment(value):
            pytest.fail("Missing prerequisites")
    assert "ALFWORLD_DATA" not in os.environ


@pytest.mark.parametrize("root", [None, "", "relative/path", 0])
def test_missing_or_relative_explicit_root_rejected(tmp_path, monkeypatch, root):
    value = auth(tmp_path)
    value["runtime"]["alfworld_data"] = root
    monkeypatch.delenv("ALFWORLD_DATA", raising=False)
    with pytest.raises(ValueError, match="absolute"):
        with learning_environment(value):
            pytest.fail("Cannot infer host root")


@pytest.mark.parametrize("provider,benchmark", [("fixture", "alfworld"), ("bigmodel", "searchqa")])
def test_other_launches_do_not_touch_environment(tmp_path, monkeypatch, provider, benchmark):
    value = auth(tmp_path, provider=provider, benchmark=benchmark)
    monkeypatch.setenv("ALFWORLD_DATA", "existing unrelated value")
    with learning_environment(value):
        assert os.environ["ALFWORLD_DATA"] == "existing unrelated value"
    assert os.environ["ALFWORLD_DATA"] == "existing unrelated value"


def test_worker_threads_cannot_change_process_environment(tmp_path, monkeypatch):
    value = auth(tmp_path)
    monkeypatch.delenv("ALFWORLD_DATA", raising=False)
    def worker():
        with learning_environment(value):
            pytest.fail("Cannot set globals inside concurrent episode worker")
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(ValueError, match="main thread"):
            pool.submit(worker).result()
    assert "ALFWORLD_DATA" not in os.environ


def test_native_smoke_driver_records_cleanup_and_does_not_use_model(tmp_path, monkeypatch):
    from scripts import smoke_alfworld_launch as smoke
    from skillopt.coevolution_v5.core import seal
    from skillopt.continual_eval.core import write_json
    from skillopt.validator_pilot.api import digest

    value = auth(tmp_path)
    panel = {"benchmark": "alfworld", "tasks": [{"public": {"game_file": "fixture"}}]}
    value = seal({**value, "panel_hash": digest(panel)})
    write_json(tmp_path / "manifest.json", value)
    write_json(tmp_path / "panel.json", panel)
    monkeypatch.delenv("ALFWORLD_DATA", raising=False)
    class Episode:
        process = None
        closed = False
        def __init__(self):
            self.process = self
        def reset(self):
            assert os.environ["ALFWORLD_DATA"] == value["runtime"]["alfworld_data"]
            return ["public reset"], None, [{"admissible_commands": ["look"]}]
        def step(self, actions):
            assert actions == ["look"]
            return ["public observation"], None, [0], [False], [{"won": False}]
        def close(self):
            self.closed = True
        def is_alive(self):
            return not self.closed
    episode = Episode()
    monkeypatch.setattr(smoke, "_new_alfworld", lambda *_: episode)
    result = smoke.run(tmp_path / "manifest.json", tmp_path / "panel.json", tmp_path / "run", tmp_path / "native.lock")
    assert result["status"] == "native_reset_step_ready"
    assert result["cleanup_confirmed"] and result["environment_restored"]
    assert result["model_calls"] == result["new_live_child_processes"] == 0
    assert episode.closed and "ALFWORLD_DATA" not in os.environ
    with pytest.raises(ValueError, match="new smoke output"):
        smoke.run(tmp_path / "manifest.json", tmp_path / "panel.json", tmp_path / "run", tmp_path / "native.lock")


def test_native_smoke_panel_mismatch_never_initializes(tmp_path, monkeypatch):
    from scripts import smoke_alfworld_launch as smoke
    from skillopt.coevolution_v5.core import seal
    from skillopt.continual_eval.core import write_json

    value = seal({**auth(tmp_path), "panel_hash": "wrong"})
    write_json(tmp_path / "manifest.json", value)
    write_json(tmp_path / "panel.json", {"benchmark": "alfworld", "tasks": []})
    monkeypatch.setattr(smoke, "_new_alfworld", lambda *_: pytest.fail("No native launch"))
    with pytest.raises(ValueError, match="binding mismatch"):
        smoke.run(tmp_path / "manifest.json", tmp_path / "panel.json", tmp_path / "run", tmp_path / "native.lock")
    assert not (tmp_path / "run").exists()
