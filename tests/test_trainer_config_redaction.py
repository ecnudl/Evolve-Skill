"""Regression tests for credentials persisted in trainer run metadata."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest import mock

import pytest

from skillopt.engine import trainer as trainer_module

_FLAT_CREDENTIALS = {
    "azure_api_key": "azure-legacy-value",
    "azure_openai_api_key": "azure-shared-value",
    "optimizer_azure_openai_api_key": "azure-optimizer-value",
    "target_azure_openai_api_key": "azure-target-value",
    "qwen_chat_api_key": "qwen-shared-value",
    "optimizer_qwen_chat_api_key": "qwen-optimizer-value",
    "target_qwen_chat_api_key": "qwen-target-value",
    "minimax_api_key": "minimax-value",
    "vendor_access_token": "vendor-token-value",
    "backend_client_secret": "client-secret-value",
    "service_password": "password-value",
}


def test_redact_cfg_redacts_credentials_without_mutating_input() -> None:
    cfg = {
        **_FLAT_CREDENTIALS,
        "nested": {
            "headers": {"Authorization": "Bearer nested-value"},
            "providers": [{"refresh_token": "refresh-value"}],
        },
    }
    original = copy.deepcopy(cfg)

    redacted = trainer_module._redact_cfg(cfg)
    serialized = json.dumps(redacted)

    for secret in (
        *_FLAT_CREDENTIALS.values(),
        "Bearer nested-value",
        "refresh-value",
    ):
        assert secret not in serialized
    assert cfg == original
    assert redacted["nested"]["headers"]["Authorization"] == "[REDACTED]"
    assert redacted["nested"]["providers"][0]["refresh_token"] == "[REDACTED]"


def test_redact_cfg_preserves_non_secret_config() -> None:
    cfg = {
        "qwen_chat_max_tokens": 4096,
        "target_model": "qwen3.8-27b",
        "azure_openai_endpoint": "https://provider.example/v1",
        "reasoning_effort": "high",
        "empty_api_key": "",
        "missing_api_key": None,
    }

    assert trainer_module._redact_cfg(cfg) == cfg


class _AfterConfigPersisted(RuntimeError):
    """Stop the trainer immediately after its config artifact is written."""


def test_trainer_persists_only_redacted_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    out_root = tmp_path / "run"
    cfg = {
        "out_root": str(out_root),
        "model_backend": "openai_chat",
        "optimizer_backend": "openai_chat",
        "target_backend": "openai_chat",
        "optimizer_model": "optimizer-model",
        "target_model": "target-model",
        "skill_init": str(tmp_path / "missing-skill.md"),
        "batch_size": 1,
        "num_epochs": 1,
        "accumulation": 1,
        "seed": 0,
        "merge_batch_size": 2,
        "train_size": 1,
        "edit_budget": 4,
        **_FLAT_CREDENTIALS,
    }
    adapter = mock.Mock()
    adapter.get_dataloader.return_value = None
    adapter.requires_ray.return_value = False

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
        "configure_qwen_chat",
        "configure_minimax_chat",
        "set_reasoning_effort",
    ):
        monkeypatch.setattr(trainer_module, name, mock.Mock())
    monkeypatch.setattr(
        trainer_module,
        "build_scheduler",
        mock.Mock(side_effect=_AfterConfigPersisted),
    )

    with pytest.raises(_AfterConfigPersisted):
        trainer_module.ReflACTTrainer(cfg, adapter).train()

    config_path = out_root / "config.json"
    serialized = config_path.read_text(encoding="utf-8")
    persisted = json.loads(serialized)
    for secret in _FLAT_CREDENTIALS.values():
        assert secret not in serialized
    assert persisted["qwen_chat_api_key"] == "[REDACTED]"
    assert persisted["target_azure_openai_api_key"] == "[REDACTED]"
    assert persisted["target_model"] == "target-model"
    assert persisted["train_size"] == 1
