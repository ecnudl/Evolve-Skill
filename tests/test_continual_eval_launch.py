"""Provider-free launch regressions; these fixtures are not natural evidence."""
from copy import deepcopy

import pytest

from skillopt.continual_eval import runner
from skillopt.continual_eval.core import BENCHMARKS, freeze_plan, validate_config, write_json
from skillopt.continual_eval.fixtures import fixture_config, fixture_panel
from skillopt.validator_pilot.api import digest


def natural_shape_config(tmp_path, *, task_count=2):
    config = fixture_config(tmp_path / "fixtures")
    panel = fixture_panel("searchqa")
    panel["provenance"] = "natural"  # Exercise natural branch with no real calls or data.
    for index in range(1, task_count):
        extra = deepcopy(panel["tasks"][0])
        extra.update(task_id=f"extra-{index}", family_id=f"extra-{index}")
        panel["tasks"].append(extra)
    path = tmp_path / "panel.json"
    write_json(path, panel)
    config["panels"] = {b: str(path) if b == "searchqa" else None for b in BENCHMARKS}
    config["model"].update(provider="bigmodel", name="glm-5.3",
                           proxy="http://httpproxy-headless.kubebrain.svc.pjlab.local:3128")
    return config


@pytest.mark.parametrize("outcome", ["timeout", "ok", "length"])
@pytest.mark.parametrize("workers", [1, 10])
def test_first_real_position_controls_fanout(tmp_path, monkeypatch, outcome, workers):
    instances = []

    class API:
        model = "glm-5.3"
        service = {"model": "glm-5.3", "provider": "TEST_ONLY"}

        def __init__(self, *args, **kwargs):
            self.calls = 0
            self.closed = False
            assert kwargs["proxy"] == "http://httpproxy-headless.kubebrain.svc.pjlab.local:3128"
            instances.append(self)

        def call(self, system, user, kind, key, *, max_tokens, repeat):
            self.calls += 1
            request = {"model": self.model, "service": self.service, "system": system, "user": user,
                       "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
            return {"request": request, "request_hash": digest(request), "ok": outcome == "ok",
                    "response": "<answer>blue</answer>" if outcome == "ok" else "",
                    "finish_reason": "length" if outcome == "length" else "stop",
                    "status": None if outcome == "timeout" else 200,
                    "http_attempt_count": 1, "usage": {"prompt_tokens": 2, "completion_tokens": 1}}

        @staticmethod
        def _initial_ready(receipt):
            return receipt["status"] == 200

        def close(self):
            self.closed = True

    monkeypatch.setattr(runner, "CachedAPI", API)
    root = tmp_path / "run"
    freeze_plan(natural_shape_config(tmp_path), root)
    kwargs = dict(method="no_skill", history="h0", stage=0, benchmark="searchqa", repo=tmp_path, workers=workers)
    if outcome == "timeout":
        with pytest.raises(ValueError, match="remaining positions were not submitted"):
            runner.generate(root, **kwargs)
        expected = 1
    else:
        result = runner.generate(root, **kwargs)
        assert result["positions"] == 2
        assert result["unknown"] == (2 if outcome == "length" else 0)
        expected = 2
    assert instances[0].calls == expected and instances[0].closed
    assert len(list((root / "predictions").glob("*/intent.json"))) == expected
    assert len(list((root / "predictions").glob("*/prediction.json"))) == expected


@pytest.mark.parametrize("proxy", ["http://evil.example:3128", "http://user:secret@127.0.0.1:8080",
                                  "http://httpproxy-headless.kubebrain.svc.pjlab.local:8000"])
def test_proxy_requires_explicit_approved_destination(tmp_path, proxy):
    config = natural_shape_config(tmp_path)
    config["model"]["proxy"] = proxy
    with pytest.raises(ValueError):
        validate_config(config)


@pytest.mark.parametrize("workers", [1, 10])
@pytest.mark.parametrize("cached_outcome,new_outcome", [("ok", "timeout"), ("timeout", "ok")])
def test_resume_health_uses_first_pending_not_cached_first(tmp_path, monkeypatch, workers,
                                                         cached_outcome, new_outcome):
    """Post-launch local hardening; cached answers are never retried/replaced."""
    from skillopt.coevolution_v5.core import seal
    from skillopt.continual_eval import backends
    from skillopt.continual_eval.core import load_checkpoint, panel_tasks, public_view, read_json

    instances = []

    class API:
        model = "glm-5.3"
        service = {"model": "glm-5.3", "provider": "TEST_ONLY"}

        def __init__(self, *args, **kwargs):
            self.outcome = new_outcome
            self.calls = 0
            self.failed = self.closed = False
            instances.append(self)

        def call(self, system, user, kind, key, *, max_tokens, repeat):
            if self.failed:
                raise RuntimeError("initial health barrier failed; no HTTP request")
            self.calls += 1
            request = {"model": self.model, "service": self.service, "system": system, "user": user,
                       "kind": kind, "key": key, "max_tokens": max_tokens, "repeat": repeat}
            self.failed = self.outcome == "timeout"
            return {"request": request, "request_hash": digest(request), "ok": not self.failed,
                    "response": "<answer>blue</answer>" if not self.failed else "",
                    "finish_reason": "stop", "status": None if self.failed else 200,
                    "http_attempt_count": 1, "usage": {"prompt_tokens": 2, "completion_tokens": 1}}

        @staticmethod
        def _initial_ready(receipt):
            return receipt["status"] == 200

        def close(self):
            self.closed = True

    root = tmp_path / "run"
    plan = freeze_plan(natural_shape_config(tmp_path, task_count=3), root)
    checkpoint = load_checkpoint(root, "no_skill", "h0", 0, plan)
    tasks = panel_tasks(plan, "searchqa")

    # Seed exactly one terminal position through the real receipt wrapper,
    # representing a prior process. The remaining positions were never reserved.
    seed_api = API()
    seed_api.outcome = cached_outcome
    base, request = runner.position(root, checkpoint, "searchqa", tasks[0], 0)
    write_json(base / "intent.json", seal(request))
    call = runner.PositionCalls(seed_api, base, request, plan["config"]["model"]["max_tokens"], 1)
    prediction = backends.solve("searchqa", public_view(tasks[0]), "", call)
    record = seal({"request": request, "prediction": prediction, "evidence_kind": plan["evidence_kind"],
                   "costs": runner._position_costs(base), "score_feedback_allowed": False})
    write_json(base / "prediction.json", record)
    original_bytes = (base / "prediction.json").read_bytes()
    seed_api.close()

    monkeypatch.setattr(runner, "CachedAPI", API)
    kwargs = dict(method="no_skill", history="h0", stage=0, benchmark="searchqa", repo=tmp_path, workers=workers)
    if new_outcome == "timeout":
        with pytest.raises(ValueError, match="remaining positions were not submitted"):
            runner.generate(root, **kwargs)
        assert instances[-1].calls == 1
        assert len(list((root / "predictions").glob("*/prediction.json"))) == 2
        third, _ = runner.position(root, checkpoint, "searchqa", tasks[2], 0)
        assert not (third / "intent.json").exists()
    else:
        result = runner.generate(root, **kwargs)
        assert result["new_positions"] == 2 and result["positions"] == 3
        assert result["available"] == 2 and result["unknown"] == 1
        assert instances[-1].calls == 2
        # A fully cached second resume opens no API client at all.
        count = len(instances)
        assert runner.generate(root, **kwargs)["new_positions"] == 0
        assert len(instances) == count
    assert instances[-1].closed
    assert (base / "prediction.json").read_bytes() == original_bytes
    assert read_json(base / "prediction.json", sealed=True) == record
    assert seed_api.calls == 1
