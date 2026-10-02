import pytest

from scripts import probe_bigmodel_budget as probe


class FakeAPI:
    calls = 0
    result_model = "glm-5.3"
    fail = False

    def __init__(self, *args, **kwargs):
        self.service = {"provider": "fixture"}
        assert kwargs["stream"] is True and kwargs["stream_wall_seconds"] == 3600

    async def _long_stream_request(self, payload, diagnostic):
        type(self).calls += 1
        assert payload["max_tokens"] == 131072
        if type(self).fail:
            raise ValueError("private-content-must-not-persist")
        return 200, {}, {"model": self.result_model, "_stream_complete": True,
                         "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
                         "usage": {"total_tokens": 10}}

    def close(self):
        pass


@pytest.fixture(autouse=True)
def fake(monkeypatch):
    FakeAPI.calls = 0
    FakeAPI.result_model = "glm-5.3"
    FakeAPI.fail = False
    monkeypatch.setattr(probe, "CachedAPI", FakeAPI)


def test_short_acceptance_not_long_limit_and_replay(tmp_path):
    result = probe.run(tmp_path, tmp_path / "run")
    assert result["parameter_accepted_and_short_answer_completed"]
    assert not result["effective_long_output_limit_verified"]
    assert probe.run(tmp_path, tmp_path / "run") == result
    assert FakeAPI.calls == 1


def test_error_has_no_raw_exception_or_retry(tmp_path):
    FakeAPI.fail = True
    result = probe.run(tmp_path, tmp_path / "run")
    assert result["error_category"] == "ValueError"
    assert "private-content" not in (tmp_path / "run/result.json").read_text()
    assert FakeAPI.calls == 1


def test_wrong_model_not_accepted(tmp_path):
    FakeAPI.result_model = "wrong"
    assert not probe.run(tmp_path, tmp_path / "run")["parameter_accepted_and_short_answer_completed"]


def test_unclosed_intent_not_resampled(tmp_path):
    root = tmp_path / "run"
    probe.write_json(root / "intent.json", {"unclosed": True})
    with pytest.raises(ValueError, match="Unclosed probe"):
        probe.run(tmp_path, root)
    assert FakeAPI.calls == 0
