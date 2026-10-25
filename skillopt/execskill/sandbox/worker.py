"""In-container worker of the route-B sandbox (protocol ``fivebench-execskill-v1``; registration §2.6, §4.4 P1;
implementation plan §4 and its sandbox/worker.py row).

The host client mounts this file read-only at ``/runner/worker.py`` beside a copy of ``execskill/policy.py`` and starts
it inside the pinned native image as ``python -s -B -P /runner/worker.py`` (``-I`` would ignore PYTHONHASHSEED). At
import time it needs only the standard library: ``main`` preloads numpy, openpyxl, pandas and sympy when the image has
them (a procedure's import then costs nothing and every call starts from the same library state), and
``safe_sympify`` imports sympy only when it is called, so this module also imports on a host without sympy.

Channel. ``docker run -i`` gives the worker only stdin and stdout. Requests arrive on fd 0; responses leave on a
private duplicate of the original fd 1, and fd 1 itself (with ``sys.stdout``) is pointed at fd 2, which the host
discards, so nothing printed in the worker reaches the frame stream. A frame is an 8-byte big-endian length followed
by canonical JSON (``json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)``, the
form of ``validator_pilot.api.digest``). Every response echoes the request's ``seq``. A request the worker cannot
read (a frame over the cap, a cut frame, invalid JSON) ends the worker; the host sees end-of-file.

Ops:
- ``ping`` -> the worker protocol, this file's sha256, the hash seed, the python and library versions, the
  worker's dumpable flag (0, or None without prctl) and its memory (VmSize and VmRSS, the S0 measurement);
- ``load`` (once) {package_sha256, policy_sha256, limits {address_space_mb, frame_bytes}, procedures [{id, source,
  hooks}]} -> {package_sha256, loaded, rejected [{id, reason}]}: the policy (the runner's policy.py, whose
  ``policy_sha256()`` must equal the request's) and the syntax are checked again here; nothing is executed;
- ``call`` {proc, fn, args, timeout_s} -> {ok: true, value, value_sha256, cpu_ms, rss_kib} or {ok: false, fault,
  exc_type, message (at most 500 characters), line}, echoing proc, fn and args_sha256.
A request the worker refuses (unknown op, malformed fields, a second load, a policy hash mismatch) gets
{seq, ok: false, error}.

Each call runs in a fresh child (``os.fork``) in a process group of its own: the frame channel closed, fds 0/1/2 on
/dev/null, non-dumpable, RLIMIT_CPU (the wall timeout + 1 s), RLIMIT_AS (registered from S0, passed in ``load``),
RLIMIT_FSIZE 0, RLIMIT_NOFILE 32, ``oom_score_adj`` 1000, cwd and TMPDIR a private per-call directory; then the
procedure module is executed into a new namespace (no module state survives a call) and the named entry point is
called with the JSON arguments. The private directory is removed when the call ends, and in the container the shared
/tmp is swept back to its start-up state, so no filesystem state survives a request either (§2.6, Codex #6). The child serializes
the value (nesting at most 32, the value cap) and writes it to its own pipe. The parent kills the child's whole
process group with SIGKILL at the wall timeout, and kills what is left of the group after every call before it reaps
the child, so no descendant of a procedure outlives its call. Every way a call can fail is a fault of that call's
procedure (P1), never of the worker (``FAULTS``).

Worker parent (registrar decision on safety review 4, 2026-10-22): before serving, it ignores SIGINT and marks itself
non-dumpable (``prctl(PR_SET_DUMPABLE, 0)`` through ctypes), so a call child of the same uid can neither interrupt it
nor ptrace it or open its /proc files (its frame channel among them). The children inherit the flag and lift it only
for their own oom_score_adj write (a non-dumpable process's /proc files belong to root), before any procedure code
runs. Where prctl is not available (not Linux, or no ctypes) the flag stays as it was and the ping reports ``dumpable:
None``; the container remains the boundary. Not covered: a descendant that leaves the call's process group (possible
only past the hygiene layer, which bans ``os``) survives the group kill until the container is removed.
"""
from __future__ import annotations

import builtins
import hashlib
import importlib
import importlib.util
import json
import math
import operator
import os
import re
import resource
import select
import shutil
import signal
import struct
import sys
import tempfile
import time
import types
from fractions import Fraction

WORKER_PROTOCOL = "execskill-worker-v1"  # also the container's EXECSKILL_SANDBOX value
HEADER = struct.Struct(">Q")
RUNNER = os.path.dirname(os.path.abspath(__file__))  # /runner in the container
INPUT_WORKBOOK = os.path.join(os.path.dirname(RUNNER), "input", "input.xlsx")  # /input/input.xlsx
POLICY_FILE = os.path.join(RUNNER, "policy.py")
LIBRARIES = ("numpy", "openpyxl", "pandas", "sympy")
BOOT_FRAME_BYTES = 1 << 20  # the frame cap until ``load`` sets the registered one
LIMIT_RANGES = {"address_space_mb": (128, 65_536), "frame_bytes": (1 << 20, 1 << 26)}
ENVELOPE_BYTES = 4_096  # room for the response around a value: value cap = frame cap - this
MAX_DEPTH = 32
NOFILE = 32
OOM_SCORE_ADJ = "1000"
MESSAGE_CHARS = 500
MAX_TIMEOUT_SECONDS = 600
FAULTS = ("exception", "memory", "timeout", "cpu", "killed", "no_result", "output", "over_cap", "not_loaded",
          "undeclared")
HELPERS = ("public_workbook", "safe_sympify")
PR_GET_DUMPABLE, PR_SET_DUMPABLE = 3, 4  # linux/prctl.h


class ProtocolError(Exception):
    """A request frame the worker cannot read; the worker exits."""


class OutputFault(Exception):
    """A value that is not plain JSON."""


class CapFault(Exception):
    """A value over the size or nesting cap."""


def canonical(value):
    """Canonical JSON bytes (the ``validator_pilot.api.digest`` form); ValueError for a non-finite number."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def sha256(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def _no_constant(name):
    raise ValueError("Non-finite JSON constant: %s" % name)


def strict_loads(data):
    """JSON from UTF-8 bytes, refusing NaN and Infinity."""
    return json.loads(data.decode("utf-8"), parse_constant=_no_constant)


def check_plain(value):
    """Raise OutputFault unless ``value`` is plain JSON (dict with str keys, list, tuple, str, int, bool, finite
    float, None) and CapFault when containers nest deeper than ``MAX_DEPTH`` (which also stops a cycle)."""
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, (dict, list, tuple)):
            if depth > MAX_DEPTH:
                raise CapFault("value nests deeper than %d" % MAX_DEPTH)
            if isinstance(item, dict):
                for key, child in item.items():
                    if type(key) is not str:
                        raise OutputFault("a dict key is %s, not str" % type(key).__name__)
                    stack.append((child, depth + 1))
            else:
                stack.extend((child, depth + 1) for child in item)
        elif isinstance(item, float):
            if not math.isfinite(item):
                raise OutputFault("a non-finite number")
        elif item is not None and not isinstance(item, (str, int)):
            raise OutputFault("not JSON: %s" % type(item).__name__)


# ----------------------------------------------------------------------------- helpers exposed to procedures


def _cell_value(value):
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if hasattr(value, "isoformat"):  # datetime, date, time
        return value.isoformat()
    return str(value)  # timedelta, error values and anything else openpyxl yields


def _formula(cell):
    if cell.data_type != "f":
        return None
    return cell.value if isinstance(cell.value, str) else str(getattr(cell.value, "text", cell.value))


def public_workbook():
    """The cell's public input workbook (``/input/input.xlsx``, mounted read-only) as plain data: {"sheets": [{"name",
    "cells": {coordinate: {"value", "formula"}}}]}, the cached values and the formulas read with openpyxl (read-only
    mode, twice); dates and times as ISO text. FileNotFoundError when the sandbox has no workbook."""
    import openpyxl

    if not os.path.isfile(INPUT_WORKBOOK):
        raise FileNotFoundError("no public workbook in this sandbox")
    values = openpyxl.load_workbook(INPUT_WORKBOOK, read_only=True, data_only=True)
    formulas = openpyxl.load_workbook(INPUT_WORKBOOK, read_only=True, data_only=False)
    try:
        sheets = []
        for name in formulas.sheetnames:
            cells = {}
            for row in formulas[name].iter_rows():
                for cell in row:
                    if cell.value is not None:
                        cells[cell.coordinate] = {"value": None, "formula": _formula(cell)}
            for row in values[name].iter_rows():
                for cell in row:
                    if cell.value is not None:
                        cells.setdefault(cell.coordinate, {"value": None, "formula": None})
                        cells[cell.coordinate]["value"] = _cell_value(cell.value)
            sheets.append({"name": name, "cells": cells})
        return {"sheets": sheets}
    finally:
        values.close()
        formulas.close()


SYMPY_FUNCTIONS = ("sqrt", "exp", "log", "sin", "cos", "tan", "asin", "acos", "atan", "Abs")
SYMPY_CONSTANTS = ("pi", "E", "I")
MAX_EXPRESSION_CHARS = 1_000
MAX_EXPRESSION_DEPTH = 40
MAX_POWER_EXPONENT = 1_000
TOKEN = re.compile(r"\s*(?:(?P<num>\d+(?:\.\d+)?)|(?P<name>[A-Za-z][A-Za-z0-9]{0,31})|(?P<op>\*\*|[-+*/^(),]))")
BINARY = {"+": "add", "-": "sub", "*": "mul", "/": "div"}


def _tokens(text):
    if type(text) is not str or len(text) > MAX_EXPRESSION_CHARS:
        raise ValueError("an expression is a string of at most %d characters" % MAX_EXPRESSION_CHARS)
    out, position = [], 0
    while text[position:].strip():
        match = TOKEN.match(text, position)
        if match is None:
            raise ValueError("unexpected character at %d" % position)
        kind = match.lastgroup
        out.append((kind, match.group(kind)))
        position = match.end()
    return out


def parse_expression(text):
    """``text`` as a tree of tuples over a whitelisted grammar -- decimal numbers, names, + - * / and ^ or ** (right
    associative), unary signs, parentheses and the functions of ``SYMPY_FUNCTIONS`` -- with no evaluation of any
    kind; ValueError for anything else."""
    tokens = _tokens(text)
    position = 0

    def peek():
        return tokens[position] if position < len(tokens) else (None, None)

    def take(value=None):
        nonlocal position
        token = peek()
        if token[0] is None or (value is not None and token[1] != value):
            raise ValueError("expected %s" % (value or "a token"))
        position += 1
        return token

    def expression(depth):
        if depth > MAX_EXPRESSION_DEPTH:
            raise ValueError("expression nests too deep")
        node = term(depth)
        while peek()[1] in ("+", "-"):
            node = (BINARY[take()[1]], node, term(depth))
        return node

    def term(depth):
        node = unary(depth)
        while peek()[1] in ("*", "/"):
            node = (BINARY[take()[1]], node, unary(depth))
        return node

    def unary(depth):
        if peek()[1] in ("+", "-"):
            sign = take()[1]
            operand = unary(depth + 1)
            return ("neg", operand) if sign == "-" else operand
        base = atom(depth)
        if peek()[1] in ("**", "^"):
            take()
            return ("pow", base, unary(depth + 1))
        return base

    def atom(depth):
        kind, value = take()
        if kind == "num":
            return ("num", value)
        if kind == "name":
            if value in SYMPY_FUNCTIONS:
                take("(")
                arguments = [expression(depth + 1)]
                while peek()[1] == ",":
                    take()
                    arguments.append(expression(depth + 1))
                take(")")
                return ("call", value, tuple(arguments))
            return ("const", value) if value in SYMPY_CONSTANTS else ("name", value)
        if value == "(":
            node = expression(depth + 1)
            take(")")
            return node
        raise ValueError("unexpected %r" % value)

    tree = expression(0)
    if position != len(tokens):
        raise ValueError("unexpected %r" % (tokens[position][1],))
    return tree


def _build(node, sympy):
    kind = node[0]
    if kind == "num":
        number = Fraction(node[1])
        return sympy.Rational(number.numerator, number.denominator)
    if kind == "name":
        return sympy.Symbol(node[1])
    if kind == "const":
        return {"pi": sympy.pi, "E": sympy.E, "I": sympy.I}[node[1]]
    if kind == "call":
        return getattr(sympy, node[1])(*[_build(argument, sympy) for argument in node[2]])
    if kind == "neg":
        return -_build(node[1], sympy)
    left, right = _build(node[1], sympy), _build(node[2], sympy)
    if kind == "pow":
        if right.is_Integer and abs(int(right)) > MAX_POWER_EXPONENT:
            raise ValueError("an integer exponent above %d" % MAX_POWER_EXPONENT)
        return left ** right
    return {"add": operator.add, "sub": operator.sub, "mul": operator.mul, "div": operator.truediv}[kind](left, right)


def safe_sympify(text):
    """A sympy expression from ``text`` without ``sympify``/``parse_expr``: the whitelisted grammar of
    ``parse_expression`` mapped onto sympy constructors (Rational, Symbol, the arithmetic operators, the listed
    functions and constants). sympy is imported only here; RuntimeError when the sandbox has none."""
    tree = parse_expression(text)
    try:
        import sympy
    except ImportError:
        raise RuntimeError("sympy is not available in this sandbox") from None
    return _build(tree, sympy)


# ----------------------------------------------------------------------------- one call in a fresh child


def fault(kind, exc_type=None, message="", line=None):
    return {"ok": False, "fault": kind, "exc_type": exc_type, "message": str(message)[:MESSAGE_CHARS], "line": line}


def _message(error):
    try:
        return str(error)
    except Exception:  # an exception whose __str__ fails still has a type
        return ""


def _line(error, filename):
    line, trace = None, error.__traceback__
    while trace is not None:
        if trace.tb_frame.f_code.co_filename == filename:
            line = trace.tb_lineno
        trace = trace.tb_next
    return line


def execute(code, fn, args, value_cap):
    """Run ``fn(*args)`` of the procedure ``code`` in a new namespace; the outcome as a dict (a value or a fault)."""
    namespace = {"__name__": "procedure", "__builtins__": builtins, "public_workbook": public_workbook,
                 "safe_sympify": safe_sympify}
    try:
        exec(code, namespace)
        function = namespace.get(fn)
        if not isinstance(function, types.FunctionType):
            return fault("undeclared", None, "%s is not a function of the procedure" % fn)
        value = function(*args)
    except MemoryError as error:
        return fault("memory", "MemoryError", _message(error), _line(error, code.co_filename))
    except BaseException as error:  # whatever the procedure raises is its fault (P1)
        return fault("exception", type(error).__name__, _message(error), _line(error, code.co_filename))
    try:
        check_plain(value)
        size = len(canonical(value))
    except CapFault as error:
        return fault("over_cap", None, _message(error))
    except MemoryError as error:
        return fault("memory", "MemoryError", _message(error))
    except BaseException as error:  # OutputFault, a lone surrogate, a dict subclass that raises
        return fault("output", type(error).__name__, _message(error))
    if size > value_cap:
        return fault("over_cap", None, "value of %d bytes exceeds %d" % (size, value_cap))
    return {"ok": True, "value": value}


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]


def set_dumpable(flag):
    """``prctl(PR_SET_DUMPABLE, flag)`` through ctypes (safety review 4). While the flag is 0, processes of the same
    uid can neither ptrace this process nor open its /proc files, which then belong to root -- its own
    /proc/self/oom_score_adj included. Returns the flag read back, or None where prctl is not available (not Linux,
    or no ctypes)."""
    try:
        import ctypes

        prctl = ctypes.CDLL(None, use_errno=True).prctl
    except (ImportError, OSError, AttributeError):
        return None
    if prctl(PR_SET_DUMPABLE, flag, 0, 0, 0) != 0:
        return None
    return prctl(PR_GET_DUMPABLE, 0, 0, 0, 0)


# ----------------------------------------------------------------- per-call writable state (Codex 2026-10-22 #6)
# §2.6 requires that hidden state cannot survive a request. ``RLIMIT_FSIZE 0`` stops a call child writing file
# CONTENT but not ``os.mkdir``/``os.open(O_CREAT)`` (a zero-length directory or file), so a child that reached ``os``
# -- by a reflection route the hygiene layer missed -- could leave a marker in the shared ``/tmp`` tmpfs that the next
# call's child would see. The real boundary is the container (§2.6), so this is enforced at the OS boundary, not only
# by policy: every call runs in a fresh private directory that is removed when the call ends, and in the container
# (where ``/tmp`` is this container's own tmpfs and the worker is PID 1) every other entry a call created in the
# writable base is swept afterwards, back to the entries present when the worker started serving.
_BASELINE = {"base": None, "names": None}


def _writable_base():
    """The one writable location (the container's ``/tmp`` tmpfs; a host test may redirect it with ``TMPDIR``)."""
    return os.environ.get("TMPDIR") or "/tmp"


def _rmtree_force(path):
    """Best-effort removal of a file or directory tree a call left behind; a call child of the same uid can ``chmod``
    an entry unreadable, so an entry that will not go is chmod-ed 0o700 and retried. Never raises."""
    def retry(func, target, _):
        try:
            os.chmod(target, 0o700)
            func(target)
        except OSError:
            pass
    try:
        if os.path.islink(path) or not os.path.isdir(path):
            os.remove(path)
        else:
            shutil.rmtree(path, onerror=retry)
    except OSError:
        pass


def _new_call_dir():
    """A fresh private writable directory for one call. The first call in the container records the base's entries
    (after start-up and library preload), so the after-call sweep keeps exactly those."""
    base = _writable_base()
    if os.getpid() == 1 and _BASELINE["base"] != base:
        try:
            _BASELINE["names"] = set(os.listdir(base))
        except OSError:
            _BASELINE["names"] = set()
        _BASELINE["base"] = base
    return tempfile.mkdtemp(prefix="execskill-call-", dir=base)


def _reset_writable(call_dir):
    """Remove the call's private directory and, in the container only (worker is PID 1, so ``/tmp`` is this
    container's alone), every other entry the call created in the writable base -- a marker planted through a route
    that bypassed the hygiene layer included. On a host (the offline tests, not PID 1) only the private directory is
    removed, so the shared ``/tmp`` is never swept."""
    _rmtree_force(call_dir)
    if os.getpid() != 1:
        return
    base = _writable_base()
    baseline = _BASELINE["names"] if _BASELINE["base"] == base else set()
    try:
        names = os.listdir(base)
    except OSError:
        names = []
    for name in names:
        if name not in (baseline or set()):
            _rmtree_force(os.path.join(base, name))


def _child(code, fn, args, timeout_s, limits, write_fd, call_dir):
    null = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(null, fd)
    os.close(null)
    set_dumpable(1)  # the flag 0 inherited from the worker parent makes the file below root's (uid 65534 may not write)
    try:
        with open("/proc/self/oom_score_adj", "w") as handle:  # the memory cgroup kills the child first
            handle.write(OOM_SCORE_ADJ)
    except OSError:
        pass  # no procfs entry (not Linux): the container limits still bound the child
    set_dumpable(0)  # before any procedure code runs
    try:  # the call's writes (a relative path, ``tempfile``) land in its private dir, removed when the call ends (§2.6)
        os.chdir(call_dir)
        for key in ("TMPDIR", "TMP", "TEMP"):
            os.environ[key] = call_dir
    except OSError:
        pass
    cpu = math.ceil(timeout_s) + 1
    address = limits["address_space_mb"] << 20
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    resource.setrlimit(resource.RLIMIT_AS, (address, address))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (NOFILE, NOFILE))
    outcome = execute(code, fn, args, limits["frame_bytes"] - ENVELOPE_BYTES)
    _write_all(write_fd, canonical(outcome))
    for stream in (sys.stdout, sys.stderr):  # anything a procedure printed goes to /dev/null now
        try:
            stream.flush()
        except (OSError, ValueError):
            pass


def _drain(read_fd, deadline, cap):
    """The child's bytes and how reading ended: "eof", "timeout" or "over" (more than ``cap`` bytes)."""
    chunks, size = [], 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return b"".join(chunks), "timeout"
        ready, _, _ = select.select([read_fd], [], [], remaining)
        if not ready:
            continue
        chunk = os.read(read_fd, 65_536)
        if not chunk:
            return b"".join(chunks), "eof"
        size += len(chunk)
        if size > cap:
            return b"", "over"
        chunks.append(chunk)


def _kill_group(pid):
    """SIGKILL the call's process group: the child, if it still runs, and every descendant still in the group."""
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _reap(pid, deadline):
    """(status, rusage, late) of the call's child: waits until ``deadline`` for it to exit (``late``: it did not, and
    its process group was killed); then kills what is left of the group -- descendants of the procedure -- while the
    exited child still holds the group's id, and only then reaps the child (no pid of another process is ever hit)."""
    late = False
    while os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT) is None:
        if time.monotonic() >= deadline:
            late = True
            _kill_group(pid)
            os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT)
            break
        time.sleep(0.002)
    _kill_group(pid)
    _, status, usage = os.wait4(pid, 0)
    return status, usage, late


def _reap_orphans():
    """Reap the exited processes left to the worker: in the container it is PID 1, so the killed descendants of a call
    are re-parented to it and would otherwise stay zombies that count against the pids limit."""
    if os.getpid() != 1:
        return
    while True:
        try:
            found, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if found == 0:
            return


def run_call(code, fn, args, timeout_s, limits, channel):
    """One call in a fresh child process of its own process group; the call's outcome (value or fault). The child runs
    in a private writable directory removed when the call ends, so no filesystem state survives a request (§2.6)."""
    call_dir = _new_call_dir()
    read_fd, write_fd = os.pipe()
    deadline = time.monotonic() + timeout_s
    pid = os.fork()
    if pid == 0:
        status = 3
        try:
            os.setpgid(0, 0)
            os.close(read_fd)
            os.close(channel)
            _child(code, fn, args, timeout_s, limits, write_fd, call_dir)
            status = 0
        finally:
            os._exit(status)  # bypasses the parent's ``finally`` below, so only the parent sweeps
    try:
        try:
            os.setpgid(pid, pid)  # here too, so the group exists before any kill whichever process runs first
        except OSError:
            pass  # the child set it already, or has already exited
        os.close(write_fd)
        try:
            data, ended = _drain(read_fd, deadline, limits["frame_bytes"])
        finally:
            os.close(read_fd)
        if ended != "eof":
            _kill_group(pid)
        status, usage, late = _reap(pid, deadline)
        _reap_orphans()
        if ended == "over":
            return fault("over_cap", None, "result exceeds the frame cap of %d bytes" % limits["frame_bytes"])
        if ended == "timeout" or late:
            return fault("timeout", None, "wall timeout of %s s" % timeout_s)
        if os.WIFSIGNALED(status):
            number = os.WTERMSIG(status)
            if number == signal.SIGXCPU:
                return fault("cpu", None, "CPU limit of the call")
            return fault("killed", None, "child killed by signal %d (SIGKILL: memory cgroup or external kill)" % number)
        try:
            outcome = strict_loads(data) if os.WEXITSTATUS(status) == 0 else None
        except (ValueError, UnicodeDecodeError):
            outcome = None
        if not isinstance(outcome, dict) or outcome.get("ok") not in (True, False):
            return fault("no_result", None, "the child ended without a result (exit status %d)" % os.WEXITSTATUS(status))
        if not outcome["ok"]:
            return outcome
        value = outcome["value"]
        return {"ok": True, "value": value, "value_sha256": sha256(value),
                "cpu_ms": round((usage.ru_utime + usage.ru_stime) * 1000), "rss_kib": usage.ru_maxrss}
    finally:
        _reset_writable(call_dir)


# ----------------------------------------------------------------------------- the request loop


def _memory():
    out = {"vsz_kib": None, "rss_kib": None}
    try:
        with open("/proc/self/status") as handle:
            for line in handle:
                if line.startswith(("VmSize:", "VmRSS:")):
                    out["vsz_kib" if line.startswith("VmSize") else "rss_kib"] = int(line.split()[1])
    except OSError:
        pass  # no procfs (not Linux)
    return out


def load_policy():
    """The runner's copy of execskill/policy.py (standard library only), loaded by path because ``-P`` keeps the
    runner directory off sys.path."""
    spec = importlib.util.spec_from_file_location("execskill_sandbox_policy", POLICY_FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolves the string annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def preload():
    """{library: version or None}: imports the image's libraries once, before any call is served."""
    versions = {}
    for name in LIBRARIES:
        try:
            module = importlib.import_module(name)
        except ImportError:
            versions[name] = None
        else:
            versions[name] = str(getattr(module, "__version__", "unknown"))
    return versions


def _read_exact(fd, size):
    data = bytearray()
    while len(data) < size:
        chunk = os.read(fd, min(size - len(data), 1 << 20))
        if not chunk:
            return bytes(data)
        data += chunk
    return bytes(data)


def read_request(fd, cap):
    """The next request, or None at end-of-file before a frame; ProtocolError for an unreadable frame."""
    head = _read_exact(fd, HEADER.size)
    if not head:
        return None
    if len(head) < HEADER.size:
        raise ProtocolError("cut frame header")
    (length,) = HEADER.unpack(head)
    if length > cap:
        raise ProtocolError("request frame over the cap")
    body = _read_exact(fd, length)
    if len(body) < length:
        raise ProtocolError("cut frame")
    try:
        request = strict_loads(body)
    except (ValueError, UnicodeDecodeError):
        raise ProtocolError("invalid JSON") from None
    if not isinstance(request, dict):
        raise ProtocolError("a request is a JSON object")
    return request


def frame(value):
    data = canonical(value)
    return HEADER.pack(len(data)) + data


def _refuse(seq, error):
    return {"seq": seq, "ok": False, "error": error}


def _limits(value):
    if not isinstance(value, dict) or set(value) != set(LIMIT_RANGES):
        return None
    for key, (low, high) in LIMIT_RANGES.items():
        if type(value[key]) is not int or not low <= value[key] <= high:
            return None
    return dict(value)


def handle_load(request, state, policy):
    seq = request["seq"]
    if state["loaded"] is not None:
        return _refuse(seq, "a worker loads one package")
    version = request.get("policy_version", policy.POLICY_VERSION)
    if (type(version) is not str or version not in policy.POLICIES
            or request.get("policy_sha256") != policy.policy_sha256(version=version)):
        return _refuse(seq, "policy_mismatch: the runner's policy.py differs from the host's")
    limits, entries = _limits(request.get("limits")), request.get("procedures")
    package = request.get("package_sha256")
    versions = ((policy.POLICY_VERSION, policy.POLICY_VERSION_V23, policy.POLICY_VERSION_V24)
                if version == policy.POLICY_VERSION_V24 else (policy.POLICY_VERSION, version))
    if limits is None or type(package) is not str or not isinstance(entries, list) or not all(
            isinstance(e, dict) and {"id", "source", "hooks"} <= set(e) <= {"id", "source", "hooks", "policy_version"}
            and e.get("policy_version", policy.POLICY_VERSION) in versions
            and type(e["id"]) is str
            and type(e["source"]) is str and isinstance(e["hooks"], list)
            and all(type(h) is str for h in e["hooks"]) for e in entries):
        return _refuse(seq, "malformed load request")
    if len({e["id"] for e in entries}) != len(entries):
        return _refuse(seq, "duplicate procedure ids")
    loaded, rejected = {}, []
    for entry in entries:
        violations = policy.check(entry["source"], version=entry.get("policy_version", policy.POLICY_VERSION))
        if violations:
            rules = sorted({v.rule for v in violations})
            rejected.append({"id": entry["id"], "reason": "policy:" + ",".join(rules)})
            continue
        filename = "<procedure %s>" % entry["id"]
        try:
            code = compile(entry["source"], filename, "exec", dont_inherit=True)
        except (SyntaxError, ValueError, MemoryError, RecursionError, OverflowError) as error:
            rejected.append({"id": entry["id"], "reason": "syntax:" + type(error).__name__})
            continue
        loaded[entry["id"]] = (code, tuple(entry["hooks"]))
    state.update(loaded=loaded, limits=limits)
    return {"op": "load", "seq": seq, "ok": True, "package_sha256": package, "loaded": list(loaded),
            "rejected": rejected}


def handle_call(request, state, channel):
    seq, proc, fn, args, timeout_s = (request.get(k) for k in ("seq", "proc", "fn", "args", "timeout_s"))
    if state["loaded"] is None:
        return _refuse(seq, "call before load")
    if (type(proc) is not str or type(fn) is not str or not isinstance(args, list)
            or type(timeout_s) not in (int, float) or not 0 < timeout_s <= MAX_TIMEOUT_SECONDS):
        return _refuse(seq, "malformed call request")
    head = {"op": "call", "seq": seq, "proc": proc, "fn": fn, "args_sha256": sha256(args)}
    if proc not in state["loaded"]:
        return {**head, **fault("not_loaded", None, "procedure %s is not loaded" % proc)}
    code, hooks = state["loaded"][proc]
    if fn not in hooks:
        return {**head, **fault("undeclared", None, "%s is not a declared entry point of %s" % (fn, proc))}
    return {**head, **run_call(code, fn, args, timeout_s, state["limits"], channel)}


def handle(request, state, policy, info, channel):
    seq = request.get("seq")
    if type(seq) is not int:
        return _refuse(None, "a request carries an integer seq")
    op = request.get("op")
    if op == "ping":
        return {"op": "ping", "seq": seq, "ok": True, **info, **_memory()}
    if op == "load":
        return handle_load(request, state, policy)
    if op == "call":
        return handle_call(request, state, channel)
    return _refuse(seq, "unknown op")


def serve(policy, info, channel):
    """Answer requests on fd 0 through ``channel`` until end-of-file (0) or an unreadable request (2)."""
    state = {"loaded": None, "limits": None}
    while True:
        cap = state["limits"]["frame_bytes"] if state["limits"] else BOOT_FRAME_BYTES
        try:
            request = read_request(0, cap)
        except ProtocolError:
            return 2
        if request is None:
            return 0
        _write_all(channel, frame(handle(request, state, policy, info, channel)))


def main():
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # safety review 4: no call child can interrupt the worker parent
    dumpable = set_dumpable(0)
    channel = os.dup(1)  # the private frame channel
    os.dup2(2, 1)  # fd 1, and sys.stdout with it, now reach only the discarded stderr
    with open(os.path.abspath(__file__), "rb") as handle:
        own = hashlib.sha256(handle.read()).hexdigest()
    policy = load_policy()
    info = {"worker": WORKER_PROTOCOL, "worker_sha256": own, "hashseed": os.environ.get("PYTHONHASHSEED"),
            "python": "%d.%d.%d" % sys.version_info[:3], "policy_sha256": policy.policy_sha256(),
            "dumpable": dumpable, **preload()}
    try:
        return serve(policy, info, channel)
    finally:
        os.close(channel)


if __name__ == "__main__":
    sys.exit(main())
