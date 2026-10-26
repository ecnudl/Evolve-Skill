"""Host side of the route-B sandbox (protocol ``fivebench-execskill-v1``; registration §2.6, §4.4 P1/P4; implementation
plan §4 and its sandbox/client.py row; T-SBX-1..13; the registrar decisions of 2026-10-22 on safety review findings
3, 4 and 5).

The security boundary is the container; the policy is hygiene. A ``Worker`` owns one container at a time, started
lazily at its first call (plan §4: a cell's, an episode's, a detector's or a generator's worker) from the pinned native
image with the registered argv (``docker_command``: the frozen ``_native`` hardening, continual_eval/backends.py:169-178,
with the route-B changes of plan §4: ``-i``, pids 64, shm 16m, nofile 64:64, its own env, the read-only runner and
input mounts, a 16m tmpfs, ``python -s -B -P /runner/worker.py``). The docker CLI runs with ``DOCKER_ENV`` only (the dev
machine's shell exports unrelated keys, §2.6).

Names (safety review 3): ``execskill-sbx-<chain>-<unit12>-<uuid4 hex>`` for a worker given ``tag=unit_tag(chain,
unit)``, else the registered ``execskill-sbx-<uuid4 hex>``. ``drain_unit`` checks one unit's names only, so a unit of
one chain drains while the other chain's units run (ticket A5-2); ``drain_check`` with the bare prefix stays the
machine-wide check for a point where no route-B unit runs.

Error mapping (§2.6, §4.4):
- every call failure inside the worker -- exception, memory, timeout, CPU, kill, bad output, cap -- comes back as a
  fault of the call's procedure (P1); the container keeps serving;
- a lost worker -- end-of-file, a corrupt frame, a ``seq`` or echo mismatch, a refused call (safety review 4), a reply
  past the call's timeout plus grace -- is classified by bounded docker queries made before the container is removed
  (``_cause``; safety review 5): docker not answering or the pinned image gone -> ``SandboxUnavailable`` (P4); the
  container OOM-killed or vanished -> it is replaced and the call retried ONCE with the procedure still loaded (a
  second loss is charged as below); otherwise, and on that second loss, the in-flight call gets fault ``worker`` (P1),
  the container is removed, the procedure is dropped and the next call restarts the container without it
  (``dropped``);
- docker missing, the image missing, docker not answering, a container that does not start or answer its ready ping
  within ``SANDBOX_READY_SECONDS`` twice in a row (one start retry), a failed restart: ``SandboxUnavailable`` (P4);
- a container whose forced removal is not confirmed after ``CLEANUP_TRIES`` tries: ``CleanupUnconfirmed``. ``close``
  verifies only its own exact container name (the frozen ``_native`` likewise checks only its own uuid name,
  backends.py:158, :190); ``drain_unit``/``drain_check`` check a name prefix once, after every worker of a unit has
  exited (Codex F14);
- a ``ping`` or ``load`` the worker refuses (a host-side bug, or a runner policy that differs from the host's):
  ConfigurationError.
``restarts`` records every container replaced without dropping a procedure, ``cleanups`` every confirmed removal with
its latency (the S0/S2 reports of safety reviews 3 and 5).

Slots (plan §4; ``slots.py``): with ``live`` (the ``execskill-sandbox-live`` pool, or a unit's capped view of it) a
container holds one slot from before its start until its removal is confirmed; with ``per_call`` (the
``execskill-sandbox`` pool) each exchange holds one short slot (``hold_short``: P4 after two 600 s waits). The live slot
is taken before the per-call one, as ``slots.LOCK_ORDER`` requires. A Worker is used by one thread.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import select
import shutil
import subprocess
import tempfile
import time
import uuid
from contextlib import ExitStack, contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path

from skillopt.continual_eval.core import require

from .. import policy
from ..errors import CleanupUnconfirmed, ConfigurationError, SandboxUnavailable
from ..protocol import CLEANUP_SECONDS, SANDBOX_READY_SECONDS
from .worker import (FAULTS, HEADER, LIMIT_RANGES, MAX_TIMEOUT_SECONDS, WORKER_PROTOCOL, canonical, frame, sha256,
                     strict_loads)

IMAGE = "sha256:0a0a5dcb7dd4e56215c729d2ccdd6a8862d1a644bb6f992f8bb591d4e0a0f0dd"  # coevo5/protocol.py:346, §2.6
PREFIX = "execskill-sbx-"
CHAIN_TAG = re.compile(r"[a-z0-9]{1,8}")
TAG = re.compile(r"[a-z0-9]{1,8}-[0-9a-f]{12}")  # unit_tag: chain and the first 12 hex digits of sha256(unit)
NAME = re.compile(re.escape(PREFIX) + r"(?:[a-z0-9]{1,8}-[0-9a-f]{12}-)?[0-9a-f]{32}")
DOCKER_ENV = {"PATH": "/usr/bin:/bin"}
WORKER_FILE = Path(__file__).with_name("worker.py")
INPUT_FILE = "input.xlsx"  # the one file of the read-only /input mount (§2.5, ``solver._inputs_dir``)
POLICY_FILE = Path(policy.__file__)
REPLY_GRACE_SECONDS = 10  # a call's reply may arrive this long after its wall timeout before the worker counts as lost
CLEANUP_TRIES = 3  # safety review 3: removal and its exact-name check tried three times, each command CLEANUP_SECONDS
CLEANUP_PAUSE_SECONDS = 1  # between two tries
START_TRIES = 2  # safety review 5: one retry of a failed start or ready ping
CALL_FAULTS = FAULTS + ("worker",)
RESULT_KEYS = {True: ("ok", "value", "value_sha256", "cpu_ms", "rss_kib"),
               False: ("ok", "fault", "exc_type", "message", "line")}
UNAVAILABLE = {"daemon": "sandbox_daemon_unreachable", "image": "sandbox_image_missing"}
RETRIED = ("oom", "gone")  # docker-side losses: the container is replaced and the call retried once


@dataclass(frozen=True)
class Limits:
    """One worker kind's container limits (plan §4: start values until S0 registers its measurements)."""
    pids: int
    memory_mb: int
    cpus: float
    address_space_mb: int  # RLIMIT_AS of each call's child
    frame_bytes: int  # the frame cap: max(1 MiB, 4 x the p100 view bytes) from S0

    def __post_init__(self):
        require(type(self.pids) is int and 16 <= self.pids <= 1024 and type(self.memory_mb) is int
                and 256 <= self.memory_mb <= 4096 and type(self.cpus) in (int, float) and 0 < self.cpus <= 4,
                "Sandbox container limits out of range")
        for key in LIMIT_RANGES:
            low, high = LIMIT_RANGES[key]
            require(type(getattr(self, key)) is int and low <= getattr(self, key) <= high, "Sandbox %s out of range" % key)

    def worker(self):
        """The limits the worker applies itself (sent with ``load``)."""
        return {"address_space_mb": self.address_space_mb, "frame_bytes": self.frame_bytes}


CELL_LIMITS = Limits(pids=64, memory_mb=768, cpus=0.5, address_space_mb=2048, frame_bytes=1 << 20)
LIMITS = {"cell": CELL_LIMITS, "episode": CELL_LIMITS, "detector": CELL_LIMITS,
          "generator": Limits(pids=64, memory_mb=1024, cpus=1, address_space_mb=2048, frame_bytes=1 << 20)}
KINDS = tuple(LIMITS)


def worker_sha256():
    """The sha256 of the pinned worker file (the manifest's ``sandbox.worker_sha256``)."""
    return hashlib.sha256(WORKER_FILE.read_bytes()).hexdigest()


def unit_tag(chain, unit):
    """The chain-and-unit part of a container name (safety review 3): the chain lower-cased (G -> g, D -> d, smoke)
    and the first 12 hex digits of sha256(unit), e.g. ``g-1a2b3c4d5e6f`` for ``unit_tag("G", "G/s1-officeqa/run")``."""
    require(type(chain) is str and CHAIN_TAG.fullmatch(chain.lower()) is not None and type(unit) is str and unit,
            "A unit tag names a chain (1-8 letters or digits) and a unit")
    return "%s-%s" % (chain.lower(), hashlib.sha256(unit.encode("utf-8")).hexdigest()[:12])


def docker_command(kind, limits, mounts, *, name, hashseed=0, docker="docker", image=IMAGE):
    """The registered ``docker run`` argv of one sandbox container (plan §4). ``limits``: None for the kind's start
    values; ``mounts``: {"runner": dir, "input": dir or None}, both mounted read-only."""
    require(kind in KINDS, "Unknown sandbox kind")
    limits = limits or LIMITS[kind]
    argv = [docker, "run", "-i", "--pull=never", "--name", name, "--network=none", "--read-only",
            "--user=65534:65534", "--cap-drop=ALL", "--security-opt=no-new-privileges=true",
            f"--pids-limit={limits.pids}", f"--memory={limits.memory_mb}m", f"--memory-swap={limits.memory_mb}m",
            f"--cpus={limits.cpus}", "--ipc=private", "--shm-size=16m", "--no-healthcheck", "--log-driver=none",
            "--ulimit=nofile=64:64", "--ulimit=core=0:0", "--env", f"PYTHONHASHSEED={hashseed}",
            "--env", "OMP_NUM_THREADS=1", "--env", "OPENBLAS_NUM_THREADS=1", "--env", "MKL_NUM_THREADS=1",
            "--env", f"EXECSKILL_SANDBOX={WORKER_PROTOCOL}",
            "--mount", f"type=bind,source={mounts['runner']},target=/runner,readonly"]
    if mounts.get("input") is not None:
        argv += ["--mount", f"type=bind,source={mounts['input']},target=/input,readonly"]
    return argv + ["--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m", "--workdir=/tmp", "--entrypoint=python", image,
                   "-s", "-B", "-P", "/runner/worker.py"]


def argv_template(kind, limits=None):
    """``docker_command`` with placeholders for the per-container parts (the manifest's argv template)."""
    return docker_command(kind, limits, {"runner": "<runner>", "input": "<input>"},
                          name=PREFIX + "<chain>-<unit12>-<uuid4>", hashseed="<0|1>")


@dataclass(frozen=True)
class Completed:
    """A bounded docker command: its exit code (None when it did not run or timed out) and its stdout."""
    code: int | None
    stdout: bytes


class Docker:
    """The docker CLI: the binary on ``path``, run with ``DOCKER_ENV`` as its whole environment."""

    def __init__(self, path=DOCKER_ENV["PATH"]):
        self.binary = shutil.which("docker", path=path)

    def spawn(self, argv):
        """``docker run -i``: stdin and stdout are the frame channel; stderr is discarded."""
        return subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                env=dict(DOCKER_ENV), start_new_session=True)

    def run(self, argv, timeout):
        try:
            done = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  env=dict(DOCKER_ENV), timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return Completed(None, b"")
        return Completed(done.returncode, done.stdout)


def _listed(docker, pattern):
    """The container names one bounded ``docker ps -a`` lists for ``pattern``; None when the listing failed."""
    listed = docker.run([docker.binary, "ps", "-a", "--filter", "name=" + pattern, "--format", "{{.Names}}"],
                        CLEANUP_SECONDS)
    return None if listed.code != 0 else listed.stdout.decode("utf-8", "replace").split()


def cleanup(name, *, docker=None):
    """Force-remove the container ``name`` and confirm that exactly this name is gone; never looks at other workers'
    containers (Codex F14). Up to ``CLEANUP_TRIES`` tries of ``docker rm --force`` and the exact-name check, each
    command bounded by ``CLEANUP_SECONDS`` and the tries ``CLEANUP_PAUSE_SECONDS`` apart, so one slow removal is not a
    stop (safety review 3). CleanupUnconfirmed after the last try."""
    require(type(name) is str and NAME.fullmatch(name) is not None, "Not a sandbox container name")
    docker = docker or Docker()
    if docker.binary is None:
        raise CleanupUnconfirmed("sandbox cleanup unconfirmed (%s): docker unavailable" % name)
    started, remaining = time.monotonic(), None
    for attempt in range(CLEANUP_TRIES):
        if attempt:
            time.sleep(CLEANUP_PAUSE_SECONDS)
        docker.run([docker.binary, "rm", "--force", name], CLEANUP_SECONDS)
        remaining = _listed(docker, "^/%s$" % name)
        if remaining == []:
            return
    raise CleanupUnconfirmed("sandbox cleanup unconfirmed (%s): %s after %d tries in %.1f s" % (
        name, "still listed" if remaining else "docker ps failed", CLEANUP_TRIES, time.monotonic() - started))


def drain_check(prefix=PREFIX, *, docker=None):
    """Once the workers that use names under ``prefix`` have all exited: no container whose name starts with
    ``prefix`` remains (Codex F14). The listing is tried up to ``CLEANUP_TRIES`` times while docker fails to answer; a
    listed container is a finding at once. CleanupUnconfirmed otherwise."""
    require(type(prefix) is str and prefix.startswith(PREFIX) and re.fullmatch(r"[a-z0-9-]+", prefix) is not None,
            "A sandbox name prefix")
    docker = docker or Docker()
    if docker.binary is None:
        raise CleanupUnconfirmed("sandbox cleanup unconfirmed (%s*): docker unavailable" % prefix)
    remaining = None
    for attempt in range(CLEANUP_TRIES):
        if attempt:
            time.sleep(CLEANUP_PAUSE_SECONDS)
        remaining = _listed(docker, "^/" + prefix)
        if remaining is not None:
            break
    if remaining is None:
        raise CleanupUnconfirmed("sandbox cleanup unconfirmed (%s*): docker ps failed after %d tries" % (
            prefix, CLEANUP_TRIES))
    if remaining:
        raise CleanupUnconfirmed("sandbox containers remain (%s*): %s" % (prefix, ", ".join(sorted(remaining)[:10])))


def drain_unit(chain, unit, *, docker=None):
    """The unit drain of §2.6 (registrar decision on safety review 3): once every worker of ``unit`` -- each made with
    ``tag=unit_tag(chain, unit)`` -- has exited, none of its containers remains; other units' and the other chain's
    containers are not looked at. CleanupUnconfirmed otherwise."""
    drain_check(PREFIX + unit_tag(chain, unit) + "-", docker=docker)


class _Lost(Exception):
    """The worker process is gone or its channel is unusable; ``ended``: the worker process is known to have ended
    (end-of-file or a broken pipe), so docker has its exit state once the local docker client exits."""

    def __init__(self, message, *, ended=False):
        super().__init__(message)
        self.ended = ended


class _Container:
    """A container: its name, the local ``docker run -i`` process (None until spawned, or when the spawn failed), the
    reply buffer and its slot stack."""

    def __init__(self, name, stack):
        self.name, self.process, self.stack, self.buffer = name, None, stack, bytearray()

    def send(self, data, deadline):
        if self.process is None:
            raise _Lost("docker did not start")
        fd = self.process.stdin.fileno()
        os.set_blocking(fd, False)
        view = memoryview(data)
        while view:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _Lost("request write timed out")
            _, ready, _ = select.select([], [fd], [], remaining)
            if not ready:
                continue
            try:
                view = view[os.write(fd, view):]
            except BlockingIOError:
                continue
            except BrokenPipeError:
                raise _Lost("request write failed: BrokenPipeError", ended=True) from None
            except OSError as error:
                raise _Lost("request write failed: %s" % type(error).__name__) from None

    def receive(self, deadline, cap):
        if self.process is None:
            raise _Lost("docker did not start")
        fd = self.process.stdout.fileno()
        while True:
            if len(self.buffer) >= HEADER.size:
                (length,) = HEADER.unpack_from(self.buffer)
                if length > cap:
                    raise _Lost("corrupt frame: %d bytes over the cap" % length)
                if len(self.buffer) >= HEADER.size + length:
                    payload = bytes(self.buffer[HEADER.size:HEADER.size + length])
                    del self.buffer[:HEADER.size + length]
                    try:
                        reply = strict_loads(payload)
                    except (ValueError, UnicodeDecodeError):
                        raise _Lost("corrupt frame: invalid JSON") from None
                    if not isinstance(reply, dict):
                        raise _Lost("corrupt frame: not an object")
                    return reply
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _Lost("no reply in time")
            ready, _, _ = select.select([fd], [], [], remaining)
            if ready:
                chunk = os.read(fd, 1 << 16)
                if not chunk:
                    raise _Lost("worker exited (end of file)", ended=True)
                self.buffer += chunk


def _fault(kind, message, exc_type=None, line=None):
    return {"ok": False, "fault": kind, "exc_type": exc_type, "message": str(message)[:500], "line": line}


def _entries(package):
    """The load entries of a package: any object with ``sha256`` and ``procedures`` whose items carry ``id``,
    ``source`` and ``hooks`` (the entry points the host may call) -- ``package.Package`` or a detector/generator
    bundle."""
    entries = [{"id": p.id, "source": p.source, "hooks": list(p.hooks)} for p in package.procedures]
    # E3: carry a v2.3 procedure's policy through every replay/solver sandbox; old frames stay unchanged.
    for entry, procedure in zip(entries, package.procedures):
        version = getattr(procedure, "policy_version", policy.POLICY_VERSION)
        if version != policy.POLICY_VERSION:
            entry["policy_version"] = version
    require(type(package.sha256) is str and re.fullmatch(r"[0-9a-f]{64}", package.sha256) is not None
            and all(type(e["id"]) is str and type(e["source"]) is str and all(type(h) is str for h in e["hooks"])
                    for e in entries) and len({e["id"] for e in entries}) == len(entries),
            "A package has a sha256 and procedures with distinct ids, sources and hook names")
    return entries


class Worker:
    """One sandbox container at a time for one cell, episode, detector or generator run (plan §4).

    ``start`` binds the package and kind and returns the worker; the container starts at the first ``call`` or
    ``ping``. ``limits`` replaces kinds' start values with the registered ones; ``hashseed`` is the container's
    PYTHONHASHSEED (0, or 1 for the second worker of the engineer's determinism check); ``live``/``per_call``: the
    slot pools of the module docstring; ``scratch``: where the read-only runner directory is made; ``docker``: the CLI
    (a fake in tests); ``tag``: ``unit_tag(chain, unit)`` of the unit the worker serves (its containers' names carry
    it, so ``drain_unit`` finds them). After a call, ``dropped`` lists the procedures removed by a restart,
    ``rejected`` the ones the worker refused at load ({id: reason}), ``names`` every container this worker started,
    ``unconfirmed`` the containers whose removal was not confirmed (their live slots stay held), ``restarts`` the
    containers replaced without dropping a procedure ({cause, container, procedure}) and ``cleanups`` the confirmed
    removals ({container, seconds})."""

    def __init__(self, *, docker=None, limits=None, hashseed=0, live=None, per_call=None, scratch=None, image=IMAGE,
                 tag=None):
        require(hashseed in (0, 1) and (limits is None or set(limits) <= set(KINDS))
                and (tag is None or (type(tag) is str and TAG.fullmatch(tag) is not None)), "Invalid worker settings")
        self.docker = docker or Docker()
        self.limits = {**LIMITS, **(limits or {})}
        self.hashseed, self.live, self.per_call, self.image, self.tag = hashseed, live, per_call, image, tag
        self.scratch = scratch
        self.package = self.kind = self.inputs_dir = None
        self.dropped, self.rejected, self.names, self.unconfirmed, self.info = [], {}, [], [], None
        self.restarts, self.cleanups = [], []
        self._entries, self._container, self._runner, self._seq, self._closed = [], None, None, 0, False

    def start(self, package, *, kind, inputs_dir=None):
        """Bind ``package`` (lazy: no container yet). ``inputs_dir``: the cell's public input directory, mounted
        read-only at /input: exactly one regular file ``input.xlsx`` (``solver._inputs_dir``), so no reference or
        answer workbook beside the input can be mounted (isolation review 9); its path may not contain a comma."""
        require(self.package is None and not self._closed, "A worker is started once")
        require(kind in KINDS, "Unknown sandbox kind")
        if inputs_dir is not None:
            inputs_dir = Path(inputs_dir)
            require(inputs_dir.is_absolute() and inputs_dir.is_dir() and "," not in str(inputs_dir),
                    "The input directory is an absolute directory path without commas")
            entries = list(inputs_dir.iterdir())
            require(len(entries) == 1 and entries[0].name == INPUT_FILE and entries[0].is_file()
                    and not entries[0].is_symlink(),
                    "The input directory holds exactly one regular file, " + INPUT_FILE)
        self._entries = _entries(package)
        if any(e.get("policy_version") in (policy.POLICY_VERSION_V28, policy.POLICY_VERSION_V29) for e in self._entries):
            self.hashseed = 0
        self.package, self.kind, self.inputs_dir = package, kind, inputs_dir
        return self

    def call(self, proc_id, fn, args, *, timeout_s):
        """Run ``fn(*args)`` of procedure ``proc_id`` in a fresh child of the worker: {ok: True, value, value_sha256,
        cpu_ms, rss_kib} or {ok: False, fault (one of ``CALL_FAULTS``), exc_type, message, line} (P1).
        SandboxUnavailable (P4) when no container can serve the call (module docstring)."""
        require(self.package is not None and not self._closed, "Call a started, open worker")
        require(type(proc_id) is str and type(fn) is str and isinstance(args, (list, tuple))
                and type(timeout_s) in (int, float) and 0 < timeout_s <= MAX_TIMEOUT_SECONDS,
                "A call names a procedure and function, with positional arguments and a timeout of (0, 600] s")
        args = list(args)
        try:
            args_sha256 = sha256(args)
        except (TypeError, ValueError):
            raise ConfigurationError("Sandbox call arguments must be canonical JSON") from None
        if proc_id not in {e["id"] for e in self._entries} or proc_id in self.dropped:
            return _fault("not_loaded", "procedure %s is not loaded in this sandbox" % proc_id)
        request = {"op": "call", "proc": proc_id, "fn": fn, "args": args, "timeout_s": timeout_s}
        cap = self.limits[self.kind].frame_bytes
        if len(canonical(request)) + 64 > cap:
            return _fault("over_cap", "the call's arguments exceed the frame cap of %d bytes" % cap)
        self._ensure()
        if proc_id in self.rejected:
            return _fault("not_loaded", "rejected inside the sandbox: %s" % self.rejected[proc_id])
        retried = False
        while True:
            lost = None
            with self._call_slot():
                try:
                    result = self._result(self._exchange(request, timeout_s + REPLY_GRACE_SECONDS),
                                          proc_id, fn, args_sha256)
                except _Lost as error:
                    lost = error
            if lost is None:
                return result
            cause = self._cause(lost)
            if cause in UNAVAILABLE:
                self._unavailable(cause, lost)
            if cause in RETRIED and not retried:
                retried = True
                self.restarts.append({"cause": cause, "container": self._container.name, "procedure": proc_id})
                self._discard()
                self._ensure()
                continue
            self.dropped.append(proc_id)
            self._discard()
            return _fault("worker", "worker lost during the call (%s; docker: %s); it restarts without %s" % (
                lost, cause, proc_id))

    def ping(self):
        """A fresh ping of the current container (starting one if needed): worker protocol and sha256, policy sha256,
        hash seed, dumpable flag, python and library versions, VmSize/VmRSS in KiB."""
        require(self.package is not None and not self._closed, "Ping a started, open worker")
        self._ensure()
        try:
            return self._exchange({"op": "ping"}, SANDBOX_READY_SECONDS)
        except _Lost as error:
            self._discard()
            raise SandboxUnavailable("sandbox worker lost on ping: %s" % error) from None

    def close(self):
        """Remove the container (confirmed by its exact name) and the runner directory; idempotent."""
        if self._closed:
            return
        self._discard()
        if self._runner is not None:
            shutil.rmtree(self._runner)
            self._runner = None
        self._closed = True

    # ------------------------------------------------------------------------------------------------ internals

    def _call_slot(self):
        return self.per_call.hold_short() if self.per_call is not None else nullcontext()

    def _runner_dir(self):
        if self._runner is None:
            root = Path(tempfile.mkdtemp(prefix="execskill-runner-", dir=self.scratch))
            for source in (WORKER_FILE, POLICY_FILE):
                (root / source.name).write_bytes(source.read_bytes())
                (root / source.name).chmod(0o444)
            root.chmod(0o755)  # the container user 65534 reads it, as for the frozen _native's directory
            self._runner = root
        return self._runner

    def _ensure(self):
        """A running, loaded container (lazy start, plan §4). A start that fails or misses its ready ping is retried
        once (safety review 5) unless docker or the image is gone; SandboxUnavailable (P4) then, or after the retry."""
        if self._container is not None:
            return
        if self.docker.binary is None:
            raise SandboxUnavailable("sandbox_unavailable: docker not found on %s" % DOCKER_ENV["PATH"])
        for attempt in range(START_TRIES):
            try:
                self._start()
                return
            except _Lost as error:
                name = self._container.name
                cause = self._missing()
                if cause is not None:
                    self._unavailable(cause, error)
                self._discard()
                if attempt + 1 == START_TRIES:
                    raise SandboxUnavailable("sandbox_start_failed: %s (%s)" % (error, name)) from None
                self.restarts.append({"cause": "start_failed", "container": name, "procedure": None})

    def _start(self):
        """One container: its live slot, the ``docker run -i`` process and the handshake; _Lost when it does not come
        up (safety review minor 13: the container is attached right after its slot is taken)."""
        name = PREFIX + ("%s-" % self.tag if self.tag else "") + uuid.uuid4().hex
        argv = docker_command(self.kind, self.limits[self.kind], {"runner": self._runner_dir(),
                              "input": self.inputs_dir}, name=name, hashseed=self.hashseed,
                              docker=self.docker.binary, image=self.image)
        container = _Container(name, ExitStack())
        if self.live is not None:
            container.stack.enter_context(self.live.hold())
        self._container = container  # attached at once: whatever fails next, ``_discard`` releases the slot
        self.names.append(name)
        try:
            container.process = self.docker.spawn(argv)
        except OSError:
            pass  # no process: the handshake's first exchange is lost ("docker did not start")
        try:
            self.info = self._handshake()
        except ConfigurationError:
            self._discard()
            raise

    def _handshake(self):
        """The ready ping (within ``SANDBOX_READY_SECONDS``) and the load of every procedure not dropped."""
        ping = self._exchange({"op": "ping"}, SANDBOX_READY_SECONDS)
        if (ping.get("ok") is not True or ping.get("worker") != WORKER_PROTOCOL
                or ping.get("worker_sha256") != worker_sha256() or ping.get("hashseed") != str(self.hashseed)
                or ping.get("policy_sha256") != policy.policy_sha256()):
            raise ConfigurationError("sandbox worker identity mismatch: %s" % {
                k: ping.get(k) for k in ("worker", "worker_sha256", "hashseed", "policy_sha256")})
        entries = [e for e in self._entries if e["id"] not in self.dropped]
        versions = {e.get("policy_version", policy.POLICY_VERSION) for e in entries}
        version = (policy.POLICY_VERSION_V29 if policy.POLICY_VERSION_V29 in versions else
                   policy.POLICY_VERSION_V28 if policy.POLICY_VERSION_V28 in versions else
                   policy.POLICY_VERSION_V25 if policy.POLICY_VERSION_V25 in versions else
                   policy.POLICY_VERSION_V24 if policy.POLICY_VERSION_V24 in versions else
                   policy.POLICY_VERSION_V23 if policy.POLICY_VERSION_V23 in versions else policy.POLICY_VERSION)
        modern = version != policy.POLICY_VERSION
        reply = self._exchange({"op": "load", "package_sha256": self.package.sha256,
                                "policy_sha256": policy.policy_sha256(version=version),
                                **({"policy_version": version} if modern else {}),
                                "limits": self.limits[self.kind].worker(),
                                "procedures": entries}, SANDBOX_READY_SECONDS)
        rejected = reply.get("rejected")
        if (reply.get("ok") is not True or reply.get("package_sha256") != self.package.sha256
                or not isinstance(rejected, list) or not all(isinstance(r, dict) for r in rejected)
                or sorted(reply.get("loaded", []) + [r.get("id") for r in rejected])
                != sorted(e["id"] for e in entries)):
            raise _Lost("corrupt load reply")
        self.rejected = {r["id"]: r.get("reason") for r in rejected}
        return ping

    def _exchange(self, request, timeout):
        self._seq += 1
        request = {**request, "seq": self._seq}
        deadline = time.monotonic() + timeout
        self._container.send(frame(request), deadline)
        reply = self._container.receive(deadline, self.limits[self.kind].frame_bytes)
        if reply.get("seq") != self._seq:
            raise _Lost("seq mismatch")
        if reply.get("ok") is False and "error" in reply:
            if request["op"] == "call":  # safety review 4: a refused call is a broken channel, never a stop
                raise _Lost("the worker refused the call: %s" % str(reply["error"])[:200])
            raise ConfigurationError("sandbox worker refused the request: %s" % str(reply["error"])[:200])
        return reply

    @staticmethod
    def _result(reply, proc_id, fn, args_sha256):
        """The call's Result after checking the echo and the value hash; _Lost when they do not hold."""
        if (reply.get("op"), reply.get("proc"), reply.get("fn"), reply.get("args_sha256")) != (
                "call", proc_id, fn, args_sha256):
            raise _Lost("echo mismatch")
        ok = reply.get("ok")
        if ok not in (True, False) or not set(RESULT_KEYS[ok]) <= set(reply):
            raise _Lost("corrupt call reply")
        if ok:
            try:
                same = sha256(reply["value"]) == reply["value_sha256"]
            except (TypeError, ValueError):
                same = False
            if not same:
                raise _Lost("value hash mismatch")
        elif reply["fault"] not in FAULTS:
            raise _Lost("unknown fault kind")
        return {key: reply[key] for key in RESULT_KEYS[ok]}

    def _missing(self):
        """"daemon" when docker does not answer, "image" when the pinned image is gone (bounded queries), else None."""
        if self.docker.run([self.docker.binary, "version", "--format", "{{.Server.Version}}"],
                           CLEANUP_SECONDS).code != 0:
            return "daemon"
        if self.docker.run([self.docker.binary, "image", "inspect", self.image], CLEANUP_SECONDS).code != 0:
            return "image"
        return None

    def _cause(self, lost):
        """Why the current container was lost (safety review 5), asked of docker before the container is removed:
        "oom" (docker reports it OOM-killed), "worker" (it is there and was not: the worker crashed, stalled or broke
        the frame protocol), else ``_missing``'s "daemon" or "image", or "gone" (it vanished while docker and the image
        are there). After an end-of-file the local docker client is first given ``CLEANUP_SECONDS`` to exit, which it
        does once docker has recorded the container's exit."""
        container = self._container
        if lost.ended and container.process is not None:
            try:
                container.process.wait(timeout=CLEANUP_SECONDS)
            except subprocess.TimeoutExpired:
                pass
        state = self.docker.run([self.docker.binary, "inspect", "--format", "{{json .State}}", container.name],
                                CLEANUP_SECONDS)
        if state.code == 0:
            try:
                found = json.loads(state.stdout)
            except ValueError:
                found = None
            return "oom" if isinstance(found, dict) and found.get("OOMKilled") is True else "worker"
        return self._missing() or "gone"

    def _unavailable(self, cause, error):
        """Remove the current container and raise SandboxUnavailable (P4) for a docker-side ``cause`` of
        ``UNAVAILABLE``. While docker does not answer, its removal cannot be confirmed either: that is the same P4,
        and the container stays in ``unconfirmed``; an unconfirmed removal while docker answers stays a stop."""
        reason = "%s: %s (%s)" % (UNAVAILABLE[cause], error, self._container.name)
        try:
            self._discard()
        except CleanupUnconfirmed as unconfirmed:
            if cause != "daemon":
                raise
            raise SandboxUnavailable("%s; removal unconfirmed: %s" % (reason, unconfirmed)) from None
        raise SandboxUnavailable(reason)

    def _discard(self):
        """Remove the current container: close its stdin, force-remove it, reap the local docker process, confirm
        the exact name is gone (recording the latency), then release its live slot (kept when removal is
        unconfirmed)."""
        container, self._container = self._container, None
        if container is None:
            return
        process, started = container.process, time.monotonic()
        try:
            if process is not None:
                process.stdin.close()
            cleanup(container.name, docker=self.docker)
        except CleanupUnconfirmed:
            self.unconfirmed.append(container)  # keeps its live slot held while this worker exists
            raise
        finally:
            if process is not None:
                _reap(process)
        self.cleanups.append({"container": container.name, "seconds": round(time.monotonic() - started, 3)})
        container.stack.close()


def _reap(process):
    try:
        process.wait(timeout=CLEANUP_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=CLEANUP_SECONDS)
        except subprocess.TimeoutExpired:
            raise CleanupUnconfirmed("the docker client of a removed sandbox container does not exit") from None
    finally:
        if process.stdout is not None:
            process.stdout.close()


@contextmanager
def with_worker(package, *, kind, inputs_dir=None, **options):
    """A started ``Worker`` for the block, closed (and its container's removal confirmed) afterwards."""
    worker = Worker(**options).start(package, kind=kind, inputs_dir=inputs_dir)
    try:
        yield worker
    finally:
        worker.close()
