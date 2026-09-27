"""Offline transparent-transport fixtures; no SSH, Docker, or model calls."""
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.coevolution_v5.core import seal
from skillopt.skill_validation import mechanism_transport as transport
from skillopt.skill_validation.natural_study import ExecutorPool
from skillopt.skill_validation.remote_executor import SSHExecutor
from tests.test_skill_validation_remote_executor import IMAGE, PAYLOAD


CONFIG = "Host skill-vm\n  HostName 127.0.0.1\n  Port 2222\n  User fixture\n  IdentityFile /fixture/private-key\n"


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "ssh.config"
    path.write_text(CONFIG)
    return path


def test_command_only_changes_binary_and_inserts_config(config):
    kwargs = {"host": "skill-vm", "remote_repo": "/home/fixture/repo", "remote_python": "/usr/bin/python3"}
    old = SSHExecutor(IMAGE, **kwargs)
    new = transport.ConfiguredSSHExecutor(IMAGE, ssh_config=config, **kwargs)
    assert new._command() == ["/usr/bin/ssh", "-F", str(config)] + old._command()[1:]
    assert "StrictHostKeyChecking=yes" in new._command() and "BatchMode=yes" in new._command()
    assert new.identity == old.identity
    assert new.transport_identity["ssh_config_sha256"] == hashlib.sha256(config.read_bytes()).hexdigest()
    visible = json.dumps(new.transport_identity)
    assert CONFIG not in visible and "/fixture/private-key" not in visible
    assert new.transport_identity["global_ssh_configuration_modified"] is False


def test_none_config_uses_existing_policy_without_f_flag():
    executor = transport.ConfiguredSSHExecutor(IMAGE)
    assert "-F" not in executor._command()
    assert executor.transport_identity["ssh_config_path"] is None
    assert executor.transport_identity["config_scope"] == "existing_ssh_configuration"


@pytest.mark.parametrize("suffix", ["Include other.config\n", "include=other.config\n",
    " Include =other.config\n", "UserKnownHostsFile = /dev/./null\n",
    "UserKnownHostsFile /dev/null\n", "GlobalKnownHostsFile=none\n",
    "NoHostAuthenticationForLocalhost yes\n", "Match exec 'arbitrary shell'\n"])
def test_unsafe_or_unfrozen_config_is_rejected(config, suffix):
    config.write_text(CONFIG + suffix)
    with pytest.raises(ValueError):
        transport.ConfiguredSSHExecutor(IMAGE, ssh_config=config)


@pytest.mark.parametrize("value", ["relative.config", "/nonexistent/config-597101", "", 17])
def test_invalid_config_path_rejected(value):
    with pytest.raises(ValueError):
        transport.ConfiguredSSHExecutor(IMAGE, ssh_config=value)


def test_directory_symlink_and_oversized_config_rejected(config, tmp_path):
    with pytest.raises(ValueError):
        transport.ConfiguredSSHExecutor(IMAGE, ssh_config=tmp_path)
    link = tmp_path / "linked.config"
    link.symlink_to(config)
    with pytest.raises(ValueError, match="Symlink"):
        transport.ConfiguredSSHExecutor(IMAGE, ssh_config=link)
    config.write_text("#" * (transport.MAX_CONFIG_BYTES + 1))
    with pytest.raises(ValueError, match="bounded"):
        transport.ConfiguredSSHExecutor(IMAGE, ssh_config=config)


def test_content_change_blocks_command_and_existing_connection(config, monkeypatch):
    executor = transport.ConfiguredSSHExecutor(IMAGE, ssh_config=config)
    initial_identity = executor.transport_identity
    called = []
    monkeypatch.setattr(SSHExecutor, "run", lambda *a, **k: called.append(True))
    config.write_text(CONFIG + "# changed transport\n")
    with pytest.raises(ValueError, match="changed"):
        executor._command()
    with pytest.raises(ValueError, match="changed"):
        executor.run(**PAYLOAD)
    assert not called and executor._terminal_reason == "ssh_executor_closed"
    assert executor.transport_identity == initial_identity  # Old run cannot adopt new contents.
    new = transport.ConfiguredSSHExecutor(IMAGE, ssh_config=config)
    assert new.transport_identity != initial_identity


def test_removed_config_cannot_fall_back_to_global_ssh(config, monkeypatch):
    executor = transport.ConfiguredSSHExecutor(IMAGE, ssh_config=config)
    called = []
    monkeypatch.setattr(SSHExecutor, "run", lambda *a, **k: called.append(True))
    config.unlink()  # Only the isolated test fixture, never a user SSH file.
    with pytest.raises(ValueError, match="existing"):
        executor.run(**PAYLOAD)
    assert not called and executor._terminal_reason == "ssh_executor_closed"


@pytest.mark.parametrize("workers", [True, 0, -1, 7, 1.0, "2"])
def test_pool_rejects_invalid_concurrency(workers):
    with pytest.raises(ValueError):
        transport.ConfiguredExecutorPool("/fixture/repo", workers=workers)


def test_base_validation_still_requires_pinned_image_and_normalized_target():
    for kwargs in ({"image": "python:latest"}, {"host": "x; injected"}, {"remote_python": "python"}):
        with pytest.raises(ValueError):
            transport.ConfiguredExecutorPool("/fixture/repo", **kwargs)
    with pytest.raises(ValueError):
        transport.ConfiguredExecutorPool("/fixture/../repo")


def test_pool_inherits_queue_health_run_and_close_without_new_protocol(config, monkeypatch):
    calls, closed = [], []
    def run(worker, *args, **kwargs):
        calls.append(worker)
        return seal({"status": "observed", "cleanup_confirmed": True, "fixture_only": True})
    monkeypatch.setattr(transport.ConfiguredSSHExecutor, "run", run)
    monkeypatch.setattr(transport.ConfiguredSSHExecutor, "close", lambda self: closed.append(self))
    pool = transport.ConfiguredExecutorPool("/fixture/repo", workers=2, host="skill-vm",
                                           remote_python="/usr/bin/python3", image=IMAGE, ssh_config=config)
    assert isinstance(pool, ExecutorPool)
    assert type(pool).run is ExecutorPool.run and type(pool).close is ExecutorPool.close
    assert pool.identity == pool.workers[0].identity
    assert pool.transport_identity["parallel_ssh_workers"] == 2
    for _ in range(3):
        assert pool.run(**PAYLOAD)["fixture_only"] is True
    assert calls == [pool.workers[0], pool.workers[1], pool.workers[0]]
    assert pool.available.qsize() == 2 and not pool.failed.is_set()
    pool.close()
    assert closed == pool.workers


def test_pool_infrastructure_failure_is_terminal_without_retry(config, monkeypatch):
    calls = []
    def run(worker, *args, **kwargs):
        calls.append(worker)
        return seal({"status": "execution_error", "reason": "ssh_fixture_disconnected",
                     "cleanup_confirmed": False, "fixture_only": True})
    monkeypatch.setattr(transport.ConfiguredSSHExecutor, "run", run)
    pool = transport.ConfiguredExecutorPool("/fixture/repo", workers=2, ssh_config=config)
    with pytest.raises(ValueError, match="infrastructure"):
        pool.run(**PAYLOAD)
    assert pool.failed.is_set() and pool.available.qsize() == 2
    with pytest.raises(ValueError, match="stopped"):
        pool.run(**PAYLOAD)
    assert len(calls) == 1


def test_changed_config_marks_pool_failed_before_base_ssh_run(config, monkeypatch):
    calls = []
    monkeypatch.setattr(SSHExecutor, "run", lambda *a, **k: calls.append(True))
    pool = transport.ConfiguredExecutorPool("/fixture/repo", workers=2, ssh_config=config)
    config.write_text(CONFIG + "# changed\n")
    with pytest.raises(ValueError, match="changed"):
        pool.run(**PAYLOAD)
    assert pool.failed.is_set() and not calls
