"""FakeDocker for the fivebench-execskill-v1 sandbox tests (implementation plan §7; T-SBX-1..13): the docker
contract of ``execskill.sandbox.client`` without docker, so the tests run offline on a Linux host. The real
container is exercised in the S0 smoke on dl.

``spawn`` accepts only the registered ``docker run -i`` argv (``check_argv``) and runs the SAME worker.py, with the
same framing, in a local subprocess of its own session: the container's ``--env`` pairs are its whole environment, a
temporary container root maps /runner and /input onto the bind-mount sources (the worker locates both relative to its
own file), and the worker's stderr is a pipe drained into ``FakeContainer.stderr`` so a test can see what reached it
(a pipe, as under docker: a regular file would be shielded by the child's RLIMIT_FSIZE 0). ``run``
serves ``rm --force`` (kills every process of the container: the worker's group and its call children's own groups),
``ps -a --filter name=<regex> --format {{.Names}}`` (matched against "/<name>", as docker does), ``image inspect``,
``inspect --format {{json .State}}`` (Status, Running, OOMKilled, ExitCode of a listed container) and ``version``.

Injections: ``fail_starts`` (the next n starts exit at once, as docker does on a daemon error), ``image_missing``
(every start fails and ``image inspect`` finds nothing), ``daemon_down`` (every start and every command fails, as
when docker does not answer), ``sticky`` (names whose ``rm --force`` leaves them listed), ``transient`` ({name: n}:
the first n ``rm --force`` of that name fail and leave it listed, a slow removal), ``corrupt`` = (n, mode), or a list
of them for the next containers in turn (that container's n-th reply frame, counting from 0, is replaced: "garbage"
bytes, a "seq" off by 1000 or a "refuse" reply; or lost with the container: "oom" (docker reports it OOM-killed),
"gone" (it vanishes) or "daemon" (docker stops answering)), ``kill_worker`` (SIGKILL of a container's processes; it
stays listed as exited, ``oom``: OOM-killed), ``remove`` (the container vanishes, removed from outside) and
``kill_child`` (SIGKILL of the child process running a call).
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from skillopt.execskill.sandbox.client import IMAGE, NAME, Completed
from skillopt.execskill.sandbox.worker import HEADER, WORKER_PROTOCOL, canonical

REQUIRED = ("--pull=never", "--network=none", "--read-only", "--user=65534:65534", "--cap-drop=ALL",
            "--security-opt=no-new-privileges=true", "--ipc=private", "--shm-size=16m", "--no-healthcheck",
            "--log-driver=none", "--ulimit=nofile=64:64", "--ulimit=core=0:0",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=16m", "--workdir=/tmp", "--entrypoint=python")
ENV_KEYS = ("PYTHONHASHSEED", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "EXECSKILL_SANDBOX")
TAIL = ["-s", "-B", "-P", "/runner/worker.py"]
LIMIT_FLAGS = re.compile(r"--(pids-limit=\d+|memory=\d+m|memory-swap=\d+m|cpus=[0-9.]+)")


def check_argv(argv, binary, image):
    """(name, env, mounts {target: source}) of a registered sandbox ``docker run`` argv; AssertionError on any
    deviation from the contract of plan §4."""
    assert argv[:3] == [binary, "run", "-i"], argv[:3]
    assert argv[-5:] == [image] + TAIL, argv[-5:]
    name, env, mounts, flags = None, {}, {}, []
    tokens = iter(argv[3:-5])
    for token in tokens:
        if token == "--name":
            name = next(tokens)
        elif token == "--env":
            key, _, value = next(tokens).partition("=")
            env[key] = value
        elif token == "--mount":
            parts = next(tokens).split(",")
            options = dict(p.split("=", 1) for p in parts if "=" in p)
            assert options["type"] == "bind" and "readonly" in parts and Path(options["source"]).is_absolute()
            mounts[options["target"]] = options["source"]
        else:
            flags.append(token)
    assert name is not None and NAME.fullmatch(name), name
    assert sorted(set(flags) - set(REQUIRED)) == sorted(f for f in flags if LIMIT_FLAGS.fullmatch(f)), flags
    assert set(REQUIRED) <= set(flags) and len(flags) == len(REQUIRED) + 4, flags
    memory = [f.split("=")[1] for f in flags if f.startswith(("--memory=", "--memory-swap="))]
    assert len(memory) == 2 and memory[0] == memory[1], memory
    assert tuple(env) == ENV_KEYS and env["PYTHONHASHSEED"] in ("0", "1"), env
    assert env["EXECSKILL_SANDBOX"] == WORKER_PROTOCOL and env["OMP_NUM_THREADS"] == "1", env
    assert "/runner" in mounts and set(mounts) <= {"/runner", "/input"}, mounts
    return name, env, mounts


def _parent(stat):
    """The parent pid in a /proc/<pid>/stat file (after the parenthesised command name), None once it is gone."""
    try:
        return int(stat.read_text().rpartition(")")[2].split()[1])
    except (OSError, IndexError, ValueError):
        return None


def _descendants(pid):
    """Every live descendant of ``pid`` (scans /proc/<pid>/stat: Linux)."""
    children = {}
    for stat in Path("/proc").glob("[0-9]*/stat"):
        children.setdefault(_parent(stat), []).append(int(stat.parent.name))
    found, queue = [], [pid]
    while queue:
        for child in children.get(queue.pop(), []):
            found.append(child)
            queue.append(child)
    return found


def _kill(pid, *, group):
    try:
        (os.killpg if group else os.kill)(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class FakeContainer:
    def __init__(self, name, process, root):
        self.name, self.process, self.root, self._stderr = name, process, root, bytearray()
        self.oom_killed = False
        self._drain = threading.Thread(target=self._read_stderr, daemon=True)
        self._drain.start()

    def _read_stderr(self):
        for chunk in iter(lambda: self.process.stderr.read1(1 << 16), b""):
            self._stderr += chunk

    @property
    def stderr(self):
        """Everything the worker and its children wrote to fd 2 (complete once the process has exited)."""
        return bytes(self._stderr)

    def stop(self):
        """Kill every process of the container, as ``docker rm --force`` and the end of its pid namespace do: the
        worker's group, then each descendant and its group (call children run in groups of their own)."""
        descendants = _descendants(self.process.pid)
        _kill(self.process.pid, group=True)
        for pid in descendants:
            _kill(pid, group=False)
            _kill(pid, group=True)
        self.process.wait(timeout=10)
        self._drain.join(timeout=10)

    def state(self):
        """``docker inspect --format {{json .State}}`` of this container."""
        code = self.process.poll()
        return {"Status": "running" if code is None else "exited", "Running": code is None,
                "OOMKilled": self.oom_killed, "ExitCode": 0 if code is None else (128 - code if code < 0 else code)}


class Relay:
    """A container whose ``index``-th reply frame is corrupted on its way to the host, or lost with the container
    (``lose(mode)`` for the modes of ``LOST``), a Popen look-alike."""

    LOST = ("oom", "gone", "daemon")

    def __init__(self, process, index, mode, lose):
        self.process, self.pid, self.stdin = process, process.pid, process.stdin
        read_fd, write_fd = os.pipe()
        self.stdout = os.fdopen(read_fd, "rb")
        threading.Thread(target=self._relay, args=(os.fdopen(write_fd, "wb"), index, mode, lose), daemon=True).start()

    def _relay(self, sink, index, mode, lose):
        source, count = self.process.stdout, 0
        try:
            with sink:
                while True:
                    head = source.read(HEADER.size)
                    if len(head) < HEADER.size:
                        return
                    body = source.read(HEADER.unpack(head)[0])
                    if count == index and mode in self.LOST:
                        lose(mode)
                        return  # the reply never reaches the host: end of file
                    if count == index and mode == "garbage":
                        body = b"\xff" * len(body)
                    elif count == index and mode == "refuse":
                        body = canonical({"seq": json.loads(body)["seq"], "ok": False, "error": "forged refusal"})
                    elif count == index:
                        reply = json.loads(body)
                        body = canonical({**reply, "seq": reply["seq"] + 1000})
                    sink.write(HEADER.pack(len(body)) + body)
                    sink.flush()
                    count += 1
        except (OSError, ValueError):
            return  # the host closed its end

    def poll(self):
        return self.process.poll()

    def wait(self, timeout=None):
        return self.process.wait(timeout)

    def kill(self):
        self.process.kill()


class FakeDocker:
    """The docker CLI of ``client.Docker`` (``binary``, ``spawn``, ``run``) over local worker processes."""

    binary = "docker"

    def __init__(self, root, *, image=IMAGE):
        self.root, self.image = Path(root), image
        self.containers = {}  # name -> FakeContainer, until removed
        self.argvs, self.commands = [], []
        self.fail_starts, self.image_missing, self.sticky, self.corrupt = 0, False, set(), None
        self.daemon_down, self.transient = False, {}

    def spawn(self, argv):
        name, env, mounts = check_argv(argv, self.binary, self.image)
        self.argvs.append(argv)
        if self.image_missing or self.fail_starts or self.daemon_down:
            self.fail_starts = max(0, self.fail_starts - 1)
            return subprocess.Popen([sys.executable, "-c", "raise SystemExit(125)"], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        root = self.root / name
        (root / "tmp").mkdir(parents=True)
        for target, source in mounts.items():
            (root / target.strip("/")).symlink_to(source, target_is_directory=True)
        process = subprocess.Popen([sys.executable] + TAIL[:3] + [str(root / "runner" / "worker.py")],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                                   cwd=root / "tmp", start_new_session=True)
        self.containers[name] = FakeContainer(name, process, root)
        if self.corrupt:
            queue = self.corrupt if isinstance(self.corrupt, list) else [self.corrupt]
            (index, mode), self.corrupt = queue[0], queue[1:] or None
            return Relay(process, index, mode, lambda lost: self._lose(name, lost))
        return process

    def _lose(self, name, mode):
        if mode == "gone":
            self.remove(name)
        else:
            self.kill_worker(name, oom=mode == "oom")
            self.daemon_down = self.daemon_down or mode == "daemon"

    def run(self, argv, timeout):
        assert argv[0] == self.binary and timeout > 0, argv
        command = argv[1:]
        self.commands.append(command)
        if self.daemon_down:
            return Completed(1, b"")
        if command[:2] == ["rm", "--force"] and len(command) == 3:
            container = self.containers.get(command[2])
            if container is None:
                return Completed(1, b"")
            container.stop()
            if self.transient.get(command[2], 0) > 0:
                self.transient[command[2]] -= 1
                return Completed(1, b"")  # a slow removal: still listed for now
            if command[2] not in self.sticky:
                del self.containers[command[2]]
            return Completed(0, b"")
        if command[:3] == ["ps", "-a", "--filter"] and command[4:] == ["--format", "{{.Names}}"]:
            pattern = re.compile(command[3].removeprefix("name="))
            names = sorted(n for n in self.containers if pattern.search("/" + n))
            return Completed(0, "".join(n + "\n" for n in names).encode())
        if command[:2] == ["image", "inspect"] and len(command) == 3:
            return Completed(1 if self.image_missing or command[2] != self.image else 0, b"[]")
        if command[:4] == ["image", "inspect", "--format", "{{.Id}}"] and len(command) == 5:
            found = not self.image_missing and command[4] == self.image  # ``manifest.image_id``: the pinned id
            return Completed(0 if found else 1, (self.image + "\n").encode() if found else b"")
        if command[:3] == ["inspect", "--format", "{{json .State}}"] and len(command) == 4:
            container = self.containers.get(command[3])
            return Completed(1, b"[]") if container is None else Completed(0, json.dumps(container.state()).encode())
        if command == ["version", "--format", "{{.Server.Version}}"]:
            return Completed(0, b"fake\n")
        raise AssertionError("unexpected docker command: %s" % command)

    def kill_worker(self, name, *, oom=False):
        """SIGKILL every process of the container (as when its first process dies); it stays listed, exited.
        ``oom``: docker reports it OOM-killed."""
        container = self.containers[name]
        container.oom_killed = container.oom_killed or oom
        container.stop()

    def remove(self, name):
        """The container vanishes: removed from outside this worker (a prune, another process)."""
        self.containers.pop(name).stop()

    def children(self, name, *, wait_s=10):
        """The pids of the container worker's call children, once one exists (scans /proc/<pid>/stat: Linux)."""
        pid = self.containers[name].process.pid
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            children = [int(stat.parent.name) for stat in Path("/proc").glob("[0-9]*/stat") if _parent(stat) == pid]
            if children:
                return children
            time.sleep(0.01)
        raise AssertionError("no call child appeared")

    def kill_child(self, name):
        """SIGKILL the running call's child (an OOM kill as the memory cgroup does it); its pids."""
        children = self.children(name)
        for child in children:
            os.kill(child, signal.SIGKILL)
        return children

    def close(self):
        for container in list(self.containers.values()):
            container.stop()
        self.containers.clear()
