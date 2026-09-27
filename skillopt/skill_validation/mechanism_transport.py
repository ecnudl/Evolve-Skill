"""Configurable transport to the unchanged SSH-to-Docker execution protocol.

This adapter supports a dedicated local Linux VM or an explicitly configured
remote host. It does not execute submitted Python locally, change global SSH
configuration, provision host-key trust, reconnect, or implement a new daemon.
An explicit SSH config is a trusted operator input, not model-provided data.
Its bytes are frozen and rechecked before every call; only its path and digest
enter transport receipts, never its contents or private-key material.
"""
from __future__ import annotations

import hashlib
import posixpath
import queue
import re
import shlex
import threading
from pathlib import Path

from .models import require
from .natural_study import ExecutorPool
from .panel import checked_path
from .remote_executor import SSHExecutor
from .single_round import IMAGE

VERSION = "mechanism-configured-ssh-docker-v1"
SSH_BINARY = "/usr/bin/ssh"
MAX_CONFIG_BYTES = 65536


def _config(path):
    """Read only the explicit regular configuration file, not identity files."""
    require(isinstance(path, (str, Path)) and Path(path).is_absolute(),
            "SSH config must be an explicit absolute path")
    path = checked_path(path)
    require(path.is_file(), "SSH config must be a regular existing file")
    require(0 < path.stat().st_size <= MAX_CONFIG_BYTES, "SSH config exceeds bounded size or is empty")
    raw = path.read_bytes()
    require(0 < len(raw) <= MAX_CONFIG_BYTES and b"\x00" not in raw, "Invalid SSH config bytes")
    text = raw.decode("utf-8")
    for line in text.splitlines():
        line = re.sub(r"^(\s*[A-Za-z][A-Za-z0-9]*)\s*=\s*", r"\1 ", line, count=1)
        tokens = shlex.split(line, comments=True)
        if not tokens:
            continue
        key, values = tokens[0].lower(), [v.lower() for v in tokens[1:]]
        require(key != "include", "SSH config Include is unsupported; freeze one explicit expanded config")
        require(not (key in {"userknownhostsfile", "globalknownhostsfile"}
                     and any(v == "none" or posixpath.normpath(v) == "/dev/null" for v in values)),
                "SSH config cannot disable known-host verification")
        require(not (key == "nohostauthenticationforlocalhost" and "yes" in values),
                "SSH config cannot bypass localhost host authentication")
        require(not (key == "match" and "exec" in values),
                "SSH config Match exec is unsupported in a frozen transport")
    return path, hashlib.sha256(raw).hexdigest()


class ConfiguredSSHExecutor(SSHExecutor):
    """Existing serial SSH executor with an optional frozen '-F' config."""

    def __init__(self, image=IMAGE, *, ssh_config=None, **kwargs):
        self.ssh_config, self.ssh_config_hash = (None, None) if ssh_config is None else _config(ssh_config)
        super().__init__(image, **kwargs)

    def _check_config(self):
        if self.ssh_config is not None:
            path, content_hash = _config(self.ssh_config)
            require(path == self.ssh_config and content_hash == self.ssh_config_hash,
                    "SSH config changed after transport initialization; cannot reuse this run")

    @property
    def transport_identity(self):
        return {**super().transport_identity, "configured_transport_version": VERSION,
                "configured_transport_source_hash": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "ssh_binary": SSH_BINARY, "ssh_config_path": str(self.ssh_config) if self.ssh_config else None,
                "ssh_config_sha256": self.ssh_config_hash,
                "config_scope": "explicit_file_without_include" if self.ssh_config else "existing_ssh_configuration",
                "global_ssh_configuration_modified": False}

    def _command(self):
        self._check_config()
        command = super()._command()
        require(command[0] == "ssh", "Unexpected base SSH command")
        # Preserve every existing policy option, including strict host-key checks.
        return [SSH_BINARY] + (["-F", str(self.ssh_config)] if self.ssh_config else []) + command[1:]

    def run(self, *args, **kwargs):
        # Also guard an already-connected worker; changing a config never
        # silently reuses an existing connection under a different identity.
        try:
            self._check_config()
        except (ValueError, OSError, UnicodeError):
            self.close()
            raise
        return super().run(*args, **kwargs)


class ConfiguredExecutorPool(ExecutorPool):
    """Bounded queue and fail-closed health behavior inherited unchanged."""

    def __init__(self, remote_repo, workers=4, *, host="PJ-CL4MIND-DULIN",
                 remote_python="/root/miniconda3/envs/skill_validation/bin/python", image=IMAGE,
                 ssh_config=None, timeout_seconds=10, call_timeout_seconds=40, memory_mb=256, cpus=1):
        require(type(workers) is int and 1 <= workers <= 6, "Execution workers must be an integer in 1..6")
        self.workers = [ConfiguredSSHExecutor(image, host=host, remote_repo=remote_repo,
            remote_python=remote_python, ssh_config=ssh_config, timeout_seconds=timeout_seconds,
            call_timeout_seconds=call_timeout_seconds, memory_mb=memory_mb, cpus=cpus) for _ in range(workers)]
        self.identity = self.workers[0].identity
        transport = self.workers[0].transport_identity
        require(all(worker.identity == self.identity and worker.transport_identity == transport
                    for worker in self.workers), "SSH worker configuration changed during pool construction")
        self.transport_identity = {**transport, "parallel_ssh_workers": workers}
        self.available = queue.Queue()
        for worker in self.workers:
            self.available.put(worker)
        self.failed = threading.Event()
