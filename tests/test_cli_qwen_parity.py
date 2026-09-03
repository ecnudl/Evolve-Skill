"""CLI parity checks for Qwen and generic OpenAI-compatible backends."""

from __future__ import annotations

import copy
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("script", ["train", "eval_only"])
def test_primary_clis_expose_qwen_and_openai_compatible(script: str) -> None:
    result = subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / f"{script}.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert re.search(r"(?<![A-Za-z0-9_])qwen(?![A-Za-z0-9_])", result.stdout)
    assert "qwen_chat" in result.stdout
    assert "openai_compatible" in result.stdout


def test_eval_only_exposes_qwen_configuration_flags() -> None:
    result = subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "eval_only.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    for flag in (
        "--qwen_chat_base_url",
        "--qwen_chat_api_key",
        "--qwen_chat_thinking_mode",
        "--optimizer_qwen_chat_base_url",
        "--target_qwen_chat_base_url",
    ):
        assert flag in result.stdout


def test_eval_only_warns_when_qwen_credentials_are_supplied_on_cli() -> None:
    import scripts.eval_only as eval_script

    args = SimpleNamespace(
        qwen_chat_api_key="do-not-echo-this-value",
        cfg_options=["model.target_qwen_chat_api_key=also-do-not-echo"],
    )

    with pytest.warns(DeprecationWarning) as captured:
        eval_script._warn_cli_credentials(args)

    messages = [str(item.message) for item in captured]
    assert len(messages) == 2
    assert all("do-not-echo" not in message for message in messages)
    assert any("QWEN_CHAT_API_KEY" in message for message in messages)


class _QwenConfigured(RuntimeError):
    """Stop eval-only after model configuration, before dataset evaluation."""


def test_eval_only_qwen_backend_routes_target_and_applies_cli_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    import scripts.eval_only as eval_script

    skill_path = tmp_path / "skill.md"
    skill_path.write_text("# Test skill\n", encoding="utf-8")
    cfg = {
        "model": {
            "backend": "azure_openai",
            "optimizer_backend": "openai_chat",
            "target_backend": "openai_chat",
            "optimizer": "gpt-5.5",
            "target": "gpt-5.5",
            # Empty inherited role values must not override the shared CLI mode.
            "optimizer_qwen_chat_thinking_mode": "",
            "target_qwen_chat_thinking_mode": "",
        },
        "env": {"out_root": str(tmp_path / "output")},
    }
    args = SimpleNamespace(
        config="unused.yaml",
        skill=str(skill_path),
        split="valid_seen",
        cfg_options=[],
        backend="qwen",
        target_model="qwen3.8-27b",
        qwen_chat_base_url="https://provider.example/v1",
        qwen_chat_api_key="test-key",
        qwen_chat_thinking_mode="disabled",
    )
    monkeypatch.setattr(eval_script, "parse_args", lambda: args)
    monkeypatch.setattr(
        "skillopt.config.load_config",
        lambda *args, **kwargs: copy.deepcopy(cfg),
    )

    calls: dict[str, object] = {}
    monkeypatch.setattr(eval_script, "configure_azure_openai", mock.Mock())
    monkeypatch.setattr(
        eval_script,
        "set_optimizer_backend",
        lambda value: calls.__setitem__("optimizer_backend", value),
    )
    monkeypatch.setattr(
        eval_script,
        "set_target_backend",
        lambda value: calls.__setitem__("target_backend", value),
    )
    monkeypatch.setattr(
        eval_script,
        "set_optimizer_deployment",
        lambda value: calls.__setitem__("optimizer_model", value),
    )
    monkeypatch.setattr(
        eval_script,
        "set_target_deployment",
        lambda value: calls.__setitem__("target_model", value),
    )
    for name in (
        "configure_codex_exec_from_config",
        "configure_claude_code_exec",
        "configure_cursor_exec",
        "configure_copilot_exec",
        "configure_copilot_chat",
    ):
        monkeypatch.setattr(eval_script, name, mock.Mock())

    def stop_after_qwen_config(**kwargs) -> None:
        calls["qwen_config"] = kwargs
        raise _QwenConfigured

    monkeypatch.setattr(eval_script, "configure_qwen_chat", stop_after_qwen_config)

    with pytest.warns(DeprecationWarning, match="QWEN_CHAT_API_KEY"):
        with pytest.raises(_QwenConfigured):
            eval_script.main()

    assert calls["optimizer_backend"] == "openai_chat"
    assert calls["target_backend"] == "qwen_chat"
    assert calls["target_model"] == "qwen3.8-27b"
    assert calls["qwen_config"] == {
        "base_url": "https://provider.example/v1",
        "api_key": "test-key",
        "temperature": None,
        "timeout_seconds": None,
        "max_tokens": None,
        "enable_thinking": None,
        "thinking_mode": "disabled",
        "optimizer_base_url": None,
        "optimizer_api_key": None,
        "optimizer_temperature": None,
        "optimizer_timeout_seconds": None,
        "optimizer_max_tokens": None,
        "optimizer_enable_thinking": None,
        "optimizer_thinking_mode": None,
        "target_base_url": None,
        "target_api_key": None,
        "target_temperature": None,
        "target_timeout_seconds": None,
        "target_max_tokens": None,
        "target_enable_thinking": None,
        "target_thinking_mode": None,
    }


def test_trainer_empty_role_modes_do_not_override_shared_qwen_mode(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from skillopt.engine import trainer as trainer_module

    cfg = {
        "out_root": str(tmp_path / "output"),
        "model_backend": "qwen_chat",
        "optimizer_backend": "openai_chat",
        "target_backend": "openai_chat",
        "optimizer_model": "gpt-5.5",
        "target_model": "qwen3.8-27b",
        "qwen_chat_thinking_mode": "disabled",
        "optimizer_qwen_chat_thinking_mode": "",
        "target_qwen_chat_thinking_mode": "",
    }
    adapter = mock.Mock()
    adapter.get_dataloader.return_value = None

    for name in (
        "set_optimizer_backend",
        "set_target_backend",
        "configure_codex_exec_from_config",
        "configure_azure_openai",
        "set_optimizer_deployment",
        "set_target_deployment",
        "configure_claude_code_exec",
        "configure_cursor_exec",
        "configure_copilot_exec",
        "configure_copilot_chat",
    ):
        monkeypatch.setattr(trainer_module, name, mock.Mock())

    def stop_after_qwen_config(**kwargs) -> None:
        assert kwargs["thinking_mode"] == "disabled"
        assert kwargs["optimizer_thinking_mode"] is None
        assert kwargs["target_thinking_mode"] is None
        raise _QwenConfigured

    monkeypatch.setattr(trainer_module, "configure_qwen_chat", stop_after_qwen_config)

    with pytest.raises(_QwenConfigured):
        trainer_module.ReflACTTrainer(cfg, adapter).train()
