"""Offline launcher tests: import ordering, narrow preload, and secret hygiene."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import source_retention_session_mvp as launcher


@pytest.fixture
def clean_launcher(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "REPO", tmp_path)
    for key in launcher.SESSION_KEYS:
        monkeypatch.delenv(key, raising=False)
    return tmp_path


def test_importing_launcher_does_not_import_frozen_cli_or_backend():
    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-c", "import scripts.source_retention_session_mvp; import sys; "
         "assert 'scripts.source_retention_mvp' not in sys.modules; "
         "assert 'skillopt.model.openai_compatible_backend' not in sys.modules"],
        cwd=repo, check=False, text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_only_session_values_loaded_with_role_precedence(clean_launcher, monkeypatch, capsys):
    (clean_launcher / ".env").write_text(
        "OPENAI_COMPATIBLE_SESSION_ID=private-shared\n"
        "TARGET_OPENAI_COMPATIBLE_SESSION_ID=private-target\n"
        "OPTIMIZER_OPENAI_COMPATIBLE_SESSION_ID=private-optimizer\n"
        "OPENAI_COMPATIBLE_API_KEY=never-export-this-key\n"
        "OPENAI_COMPATIBLE_BASE_URL=https://never-export.invalid\n"
        "UNRELATED_PRIVATE=never-export-this-value\n", encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "existing-key-kept")
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "existing-url-kept")
    monkeypatch.delenv("UNRELATED_PRIVATE", raising=False)
    assert launcher.preload_session_environment(clean_launcher) == "private-target"
    assert os.environ["OPTIMIZER_OPENAI_COMPATIBLE_SESSION_ID"] == "private-optimizer"
    assert os.environ["OPENAI_COMPATIBLE_API_KEY"] == "existing-key-kept"
    assert os.environ["OPENAI_COMPATIBLE_BASE_URL"] == "existing-url-kept"
    assert "UNRELATED_PRIVATE" not in os.environ
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("phase", ["pilot", "test"])
def test_preload_precedes_import_and_real_phase_checks_backend(clean_launcher, monkeypatch, capsys, phase):
    (clean_launcher / ".env").write_text("OPENAI_COMPATIBLE_SESSION_ID=private-session\n", encoding="utf-8")
    events = []
    actual_import = importlib.import_module

    def delegate_main(arguments):
        events.append(("main", arguments))
        return 17

    def fake_import(name):
        if name == "scripts.source_retention_mvp":
            assert os.environ["OPENAI_COMPATIBLE_SESSION_ID"] == "private-session"
            events.append("import-cli")
            return SimpleNamespace(main=delegate_main)
        if name == "skillopt.model.openai_compatible_backend":
            events.append("inspect-backend")
            return SimpleNamespace(TARGET_CONFIG=SimpleNamespace(session_id="private-session"))
        return actual_import(name)

    monkeypatch.setattr(launcher.importlib, "import_module", fake_import)
    assert launcher.main(["--phase", phase, "--workers", "6"]) == 17
    assert events == ["import-cli", "inspect-backend",
                      ("main", ["--phase", phase, "--workers", "6", "--out", str(launcher.DEFAULT_OUT)])]
    captured = capsys.readouterr()
    assert "private-session" not in captured.out + captured.err


def test_missing_session_stops_before_any_skillopt_import(clean_launcher, monkeypatch, capsys):
    def never_import(name):
        raise AssertionError(f"Unexpected import: {name}")

    monkeypatch.setattr(launcher.importlib, "import_module", never_import)
    with pytest.raises(ValueError, match="No existing target/shared"):
        launcher.main(["--phase=pilot"])
    assert capsys.readouterr() == ("", "")


def test_already_initialized_wrong_session_blocks_delegate(clean_launcher, monkeypatch, capsys):
    (clean_launcher / ".env").write_text("OPENAI_COMPATIBLE_SESSION_ID=private-session\n", encoding="utf-8")
    called = []

    def fake_import(name):
        if name == "scripts.source_retention_mvp":
            return SimpleNamespace(main=lambda args: called.append(args))
        return SimpleNamespace(TARGET_CONFIG=SimpleNamespace(session_id=None))

    monkeypatch.setattr(launcher.importlib, "import_module", fake_import)
    with pytest.raises(ValueError, match="fresh launcher process") as error:
        launcher.main(["--phase", "test"])
    assert "private-session" not in str(error.value)
    assert not called
    assert capsys.readouterr() == ("", "")


def test_prepare_without_session_delegates_without_backend_check(clean_launcher, monkeypatch):
    imported = []

    def fake_import(name):
        imported.append(name)
        assert name == "scripts.source_retention_mvp"
        return SimpleNamespace(main=lambda args: args)

    monkeypatch.setattr(launcher.importlib, "import_module", fake_import)
    custom = "outputs/scope_evolution_v2/custom-sessionfix"
    assert launcher.main(["--phase", "prepare", "--out", custom]) == ["--phase", "prepare", "--out", custom]
    assert imported == ["scripts.source_retention_mvp"]


def test_old_failed_output_cannot_be_reused(clean_launcher):
    with pytest.raises(ValueError, match="Preserve the failed"):
        launcher.main(["--phase", "pilot", "--out", str(launcher.FAILED_OUT)])


def test_empty_or_optimizer_only_session_is_not_a_target_session(clean_launcher, monkeypatch):
    monkeypatch.setenv("OPTIMIZER_OPENAI_COMPATIBLE_SESSION_ID", "private-optimizer-only")
    assert launcher.preload_session_environment(clean_launcher) is None
    monkeypatch.setenv("OPENAI_COMPATIBLE_SESSION_ID", "private-shared")
    (clean_launcher / ".env").write_text("TARGET_OPENAI_COMPATIBLE_SESSION_ID='   '\n", encoding="utf-8")
    assert launcher.preload_session_environment(clean_launcher) is None
