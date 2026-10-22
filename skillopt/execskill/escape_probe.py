"""Escape probe of the route-B sandbox (implementation plan §4; registration §2.6, the S0 escape-probe row of §10):
fixed registrar code, started by ``run_execskill.py sandbox-selftest`` with the registered container argv in place of
/runner/worker.py (``smoke.escape_argv``). It prints one JSON report on stdout and changes nothing outside the
container; ``smoke.escape_rows`` judges the report.

The probe of integration note B2, appendix A (sha256 fd769fba...e08090c5), with three changes: it reads
``sys.flags.no_user_site`` (the argv's ``-s``; the B2 probe read ``no_site`` by mistake), it refuses to run outside
the sandbox (``EXECSKILL_SANDBOX`` unset), because its checks fork up to 200 processes, allocate 1 GiB and try the
network -- never on the host -- and its imports are sorted.

The ``worker`` section (ticket fixer-9 item 2, C5-3 item 8; registrar decision C5-3, 2026-10-22): the real worker
started as a child in the pinned image reports its ``dumpable`` flag on a ping and still answers a ping after SIGINT;
one call through ``run_call`` reports the child's pid, process group and dumpable flag and forks a sleeping
descendant, which must be gone (or a zombie awaiting its reaper) once the call returned. ``s0.fixer9_rows`` judges
it."""
import errno
import fnmatch
import importlib.util
import json
import os
import signal
import socket
import sys
import time

PATTERNS = ("*.env", "*key*", "consent*", "ledger*")
SKIP = ("/proc", "/sys", "/dev")
CHILD = '''
import os
import resource
import socket


def write_file():
    fd = os.open("/tmp/probe-child-file", os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        os.write(fd, b"x")
    finally:
        os.close(fd)
    return "written"


def oom_score_adj():
    with open("/proc/self/oom_score_adj") as handle:
        return handle.read().strip()


def limits():
    return {name: list(resource.getrlimit(getattr(resource, name)))
            for name in ("RLIMIT_CPU", "RLIMIT_AS", "RLIMIT_FSIZE", "RLIMIT_NOFILE")}


def standard_streams():
    return [os.readlink("/proc/self/fd/%d" % fd) for fd in (0, 1, 2)]


def connect():
    sock = socket.socket()
    sock.settimeout(2)
    sock.connect(("1.1.1.1", 53))
    return "connected"


def allocate():
    return len(bytearray(2 << 30))
'''
GROUP_CHILD = '''
import ctypes
import os
import time


def group():
    descendant = os.fork()
    if descendant == 0:
        os.closerange(0, 1024)  # it must not hold the call's result pipe: the call ends when the child does
        time.sleep(30)
        os._exit(0)
    dumpable = ctypes.CDLL(None, use_errno=True).prctl(3, 0, 0, 0, 0)
    return [os.getpid(), os.getpgid(0), dumpable, descendant]
'''


def name_of(error):
    if isinstance(error, OSError) and error.errno:
        return errno.errorcode.get(error.errno, str(error.errno))
    return type(error).__name__


def tcp(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    try:
        sock.connect((host, port))
        return "connected"
    except OSError as error:
        return name_of(error)
    finally:
        sock.close()


def udp(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(b"x", (host, port))
        return "sent"
    except OSError as error:
        return name_of(error)
    finally:
        sock.close()


def dns(host):
    try:
        socket.getaddrinfo(host, 443)
        return "resolved"
    except OSError as error:
        return type(error).__name__


def write(path):
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except OSError as error:
        return name_of(error)
    try:
        os.write(fd, b"x")
    except OSError as error:
        return "created_then_" + name_of(error)
    finally:
        os.close(fd)
        os.unlink(path)
    return "writable"


def execute_from_tmp():
    path = "/tmp/probe-exec.sh"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o700)
        os.write(fd, b"#!/bin/sh\nexit 0\n")
        os.close(fd)
    except OSError as error:
        return "not_created_" + name_of(error)
    pid = os.fork()
    if pid == 0:
        try:
            os.execv(path, [path])
        except OSError as error:
            os._exit(100 + (error.errno or 0) % 100)
        os._exit(99)
    _, status = os.waitpid(pid, 0)
    os.unlink(path)
    code = os.WEXITSTATUS(status) if os.WIFEXITED(status) else -1
    if code == 0:
        return "executed"
    return "refused_" + errno.errorcode.get(code - 100, str(code)) if code >= 100 else "status_%d" % code


def listable(path):
    try:
        os.listdir(path)
        return True
    except OSError as error:
        return name_of(error)


def status_fields():
    keep = ("CapInh", "CapPrm", "CapEff", "CapBnd", "CapAmb", "NoNewPrivs", "Seccomp")
    fields = {}
    with open("/proc/self/status") as handle:
        for line in handle:
            key, _, value = line.partition(":")
            if key in keep:
                fields[key] = value.strip()
    return fields


def secret_names():
    hits = []
    for root, dirs, files in os.walk("/", onerror=lambda error: None):
        dirs[:] = [d for d in dirs if os.path.join(root, d) not in SKIP]
        for name in dirs + files:
            if any(fnmatch.fnmatch(name.lower(), pattern) for pattern in PATTERNS):
                hits.append(os.path.join(root, name))
    return sorted(hits)


def pids_limit(cap=200):
    children, stopped = [], None
    for _ in range(cap):
        try:
            pid = os.fork()
        except OSError as error:
            stopped = name_of(error)
            break
        if pid == 0:
            time.sleep(30)
            os._exit(0)
        children.append(pid)
    for pid in children:
        os.kill(pid, signal.SIGKILL)
    for pid in children:
        os.waitpid(pid, 0)
    return {"forked": len(children), "stopped_by": stopped}


def memory_limit(mib=1024):
    pid = os.fork()
    if pid == 0:
        try:
            with open("/proc/self/oom_score_adj", "w") as handle:
                handle.write("1000")
            block = b"x" * (mib << 20)
            os._exit(0 if block else 1)
        except MemoryError:
            os._exit(3)
    _, status = os.waitpid(pid, 0)
    if os.WIFSIGNALED(status):
        return "killed_by_signal_%d" % os.WTERMSIG(status)
    return "exited_%d" % os.WEXITSTATUS(status)


def worker_child():
    """The real worker's per-call child (worker.run_call) inside the real container."""
    spec = importlib.util.spec_from_file_location("sandbox_worker", "/runner/worker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    code = compile(CHILD, "<escape probe>", "exec")
    limits = {"address_space_mb": 2048, "frame_bytes": 1 << 20}
    out = {}
    for fn in ("write_file", "oom_score_adj", "limits", "standard_streams", "connect", "allocate"):
        channel = os.open(os.devnull, os.O_WRONLY)
        try:
            out[fn] = module.run_call(code, fn, [], 5, limits, channel)
        finally:
            os.close(channel)
    return out


def _process_state(pid):
    try:
        with open("/proc/%d/stat" % pid) as handle:
            return "zombie" if handle.read().rsplit(")", 1)[1].split()[0] == "Z" else "alive"
    except OSError:
        return "gone"


def _ping(process, module, seq):
    process.stdin.write(module.frame({"op": "ping", "seq": seq}))
    process.stdin.flush()
    head = process.stdout.read(module.HEADER.size)
    if len(head) < module.HEADER.size:
        return None
    (length,) = module.HEADER.unpack(head)
    return json.loads(process.stdout.read(length))


def worker_process():
    """fixer-9 item 2: the real worker (``python -s -B -P /runner/worker.py``) as a child: its ping's ``dumpable``,
    and whether it still answers after SIGINT; then one call child's process group and its descendant."""
    import subprocess

    spec = importlib.util.spec_from_file_location("sandbox_worker", "/runner/worker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    process = subprocess.Popen([sys.executable, "-s", "-B", "-P", "/runner/worker.py"], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        first = _ping(process, module, 1) or {}
        process.send_signal(signal.SIGINT)
        time.sleep(0.2)
        second = _ping(process, module, 2) if process.poll() is None else None
    finally:
        process.stdin.close()
        process.wait(10)
    channel = os.open(os.devnull, os.O_WRONLY)
    try:
        result = module.run_call(compile(GROUP_CHILD, "<escape probe group>", "exec"), "group", [], 5,
                                 {"address_space_mb": 2048, "frame_bytes": 1 << 20}, channel)
    finally:
        os.close(channel)
    value = result["value"] if result.get("ok") else [None, None, None, None]
    state = _process_state(value[3]) if value[3] else "unknown"
    for _ in range(50):
        if state != "alive":
            break
        time.sleep(0.02)
        state = _process_state(value[3])
    return {"dumpable": first.get("dumpable"),
            "after_sigint": "answered" if second and second.get("ok") is True else "lost",
            "group": {"child_pid": value[0], "child_pgid": value[1], "parent_pgid": os.getpgid(0),
                      "child_dumpable": value[2], "descendant": state,
                      "call": {key: result.get(key) for key in ("ok", "fault", "exc_type", "message")}}}


def main():
    if os.environ.get("EXECSKILL_SANDBOX") != "execskill-worker-v1":
        sys.exit("The escape probe runs only inside the route-B sandbox container")
    report = {
        "identity": {"uid": os.getuid(), "gid": os.getgid(), "groups": os.getgroups(), "pid": os.getpid()},
        "python": {"version": sys.version.split()[0], "safe_path": sys.flags.safe_path,
                   "no_user_site": sys.flags.no_user_site, "dont_write_bytecode": sys.flags.dont_write_bytecode,
                   "isolated": sys.flags.isolated},
        "env_keys": sorted(os.environ),
        "env": {key: os.environ.get(key) for key in ("PYTHONHASHSEED", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                                                     "MKL_NUM_THREADS", "EXECSKILL_SANDBOX")},
        "network": {"tcp_1.1.1.1_53": tcp("1.1.1.1", 53), "tcp_8.8.8.8_443": tcp("8.8.8.8", 443),
                    "udp_1.1.1.1_53": udp("1.1.1.1", 53), "dns_example.com": dns("example.com"),
                    "interfaces": sorted(os.listdir("/sys/class/net"))},
        "writes": {where or "/": write(where + "/probe-write") for where in ("", "/runner", "/input", "/etc", "/usr",
                                                                             "/tmp")},
        "tmp": {"mode": oct(os.stat("/tmp").st_mode & 0o7777), "exec": execute_from_tmp()},
        "mounts": [line.split()[:4] for line in open("/proc/self/mounts")
                   if line.split()[1] in ("/", "/runner", "/input", "/tmp")],
        "status": status_fields(),
        "host_paths": {path: os.path.exists(path) for path in ("/data", "/var/run/docker.sock", "/run/docker.sock",
                                                               "/root/.config/weak-solver/elucid.env",
                                                               "/data/skillopt-work/.env")},
        "root_listable": listable("/root"),
        "secret_names": secret_names(),
        "pids": pids_limit(),
        "memory": memory_limit(),
        "worker_child": worker_child(),
        "worker": worker_process(),
    }
    sys.stdout.write(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
