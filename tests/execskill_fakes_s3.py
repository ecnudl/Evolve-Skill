"""The S3 rehearsal's fakes (registration §10 S3 row; implementation plan §7, §10 step 7; notes/C7d.md): the smoke's
method roles end to end with zero network -- owned by C7d, beside A2's ``execskill_fakes.py``, A11's
``execskill_fakes_research.py`` and B2's ``execskill_fakes_docker.py`` (all unchanged).

- ``S3Script``: the scripted GLM-5.3 replies of S3's role calls, chosen by the pinned system prompt of each call (the
  leakage adjudicator, the engineer, the examiner's detector and generator calls, the researcher's query, pick and
  conclude calls, the describer); injections: the first reply replaced (``first``: another model's echo, an
  undelivered call), no detector written, nothing found by the research.
- ``SympyDocker``: FakeDocker whose containers import ``SYMPY_STUB`` as ``sympy`` -- the pinned image has sympy, the
  host interpreter does not -- so the registrar's LiveMath checker (``generators.livemath.CHECKER_SOURCE``) runs
  unchanged in the real sandbox worker through the real client.
- ``S3Rehearsal``: the bundle ``smoke_roles`` uses in fake mode -- the scripted GLM-5.3 gateway behind the real frozen
  client (one transport that fails the test on any solver request: S3 makes none), FakeWikipedia and SympyDocker.
Nothing here is real benchmark content.
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import httpx

from skillopt.coevo5 import leakage
from skillopt.execskill import describer, engineer, examiner, research
from skillopt.execskill.protocol import ROLE_MODEL
from skillopt.execskill.sandbox.client import IMAGE
from tests.execskill_fakes import FakeProvider, Reply, engineer_reply, fenced
from tests.execskill_fakes_docker import TAIL, FakeContainer, FakeDocker, check_argv
from tests.execskill_fakes_research import DEFINITION, FakeWikipedia

SYMPY_STUB = '''"""A minimal stand-in for sympy (tests only, tests/execskill_fakes_s3.py): exact rational arithmetic on
expression trees -- Symbol, Rational, + - * / and integer powers, diff and integrate of a polynomial in one symbol,
binomial, a finite summation, simplify, N -- enough for the LiveMath checker's templates. Anything else raises."""
import math
from decimal import Decimal, localcontext
from fractions import Fraction

__version__ = "0+fake"


def _e(value):
    if isinstance(value, Expr):
        return value
    if isinstance(value, (int, Fraction)) and not isinstance(value, bool):
        return Expr("num", Fraction(value))
    raise TypeError("not an expression")


def _merge(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, 0) + v
    return {k: v for k, v in out.items() if v}


def _times(a, b):
    out = {}
    for i, x in a.items():
        for j, y in b.items():
            out[i + j] = out.get(i + j, 0) + x * y
    return {k: v for k, v in out.items() if v}


class Expr:
    def __init__(self, op, *args):
        self.op, self.args = op, args

    def __add__(self, other):
        return Expr("add", self, _e(other))

    def __radd__(self, other):
        return Expr("add", _e(other), self)

    def __sub__(self, other):
        return Expr("add", self, Expr("neg", _e(other)))

    def __rsub__(self, other):
        return Expr("add", _e(other), Expr("neg", self))

    def __mul__(self, other):
        return Expr("mul", self, _e(other))

    def __rmul__(self, other):
        return Expr("mul", _e(other), self)

    def __truediv__(self, other):
        return Expr("div", self, _e(other))

    def __rtruediv__(self, other):
        return Expr("div", _e(other), self)

    def __pow__(self, other):
        return Expr("pow", self, _e(other))

    def __rpow__(self, other):
        return Expr("pow", _e(other), self)

    def __neg__(self):
        return Expr("neg", self)

    def free(self):
        if self.op == "sym":
            return {self.args[0]}
        if self.op == "num":
            return set()
        return set().union(*(a.free() for a in self.args))

    def value(self, env=None):
        env = env or {}
        op, args = self.op, self.args
        if op == "num":
            return args[0]
        if op == "sym":
            if args[0] not in env:
                raise ValueError("a free symbol")
            return env[args[0]]
        if op == "neg":
            return -args[0].value(env)
        left, right = args[0].value(env), args[1].value(env)
        if op == "add":
            return left + right
        if op == "mul":
            return left * right
        if op == "div":
            return left / right
        if right.denominator != 1:
            raise ValueError("a non-integer power")
        return left ** int(right)

    def subs(self, symbol, value):
        if self.op == "sym":
            return _e(value) if self.args[0] == symbol.args[0] else self
        if self.op == "num":
            return self
        return Expr(self.op, *(a.subs(symbol, value) for a in self.args))

    def poly(self, name):
        op, args = self.op, self.args
        if op == "num":
            return {0: args[0]} if args[0] else {}
        if op == "sym":
            if args[0] != name:
                raise ValueError("another symbol")
            return {1: Fraction(1)}
        if op == "neg":
            return {k: -v for k, v in args[0].poly(name).items()}
        if op == "add":
            return _merge(args[0].poly(name), args[1].poly(name))
        if op == "mul":
            return _times(args[0].poly(name), args[1].poly(name))
        if args[1].free():
            raise ValueError("not a polynomial")
        if op == "div":
            divisor = args[1].value()
            return {k: v / divisor for k, v in args[0].poly(name).items()}
        exponent = args[1].value()
        if exponent.denominator != 1 or exponent < 0:
            raise ValueError("not a polynomial power")
        out = {0: Fraction(1)}
        for _ in range(int(exponent)):
            out = _times(out, args[0].poly(name))
        return out

    @property
    def is_Rational(self):
        return not self.free()

    @property
    def is_Integer(self):
        return not self.free() and self.value().denominator == 1

    def __int__(self):
        return int(self.value())

    def __str__(self):
        return str(self.value()) if not self.free() else "Expr(%s)" % self.op

    __repr__ = __str__


def Symbol(name, **assumptions):
    return Expr("sym", name)


def Rational(p, q=1):
    return Expr("num", Fraction(p, q))


pi = E = I = None  # the grammar's constants: no template of the tests uses one


def _from_poly(poly, symbol):
    total = Expr("num", Fraction(0))
    for power, c in sorted(poly.items()):
        total = total + Expr("num", c) * symbol ** Expr("num", Fraction(power))
    return total


def diff(expr, symbol, order=1):
    poly = _e(expr).poly(symbol.args[0])
    for _ in range(int(order)):
        poly = {k - 1: v * k for k, v in poly.items() if k}
    return _from_poly(poly, symbol)


def integrate(expr, bounds):
    symbol, lower, upper = bounds
    anti = {k + 1: v / (k + 1) for k, v in _e(expr).poly(symbol.args[0]).items()}

    def at(x):
        return sum((c * x ** k for k, c in anti.items()), Fraction(0))

    return Expr("num", at(_e(upper).value()) - at(_e(lower).value()))


def binomial(n, k):
    n, k = _e(n).value(), _e(k).value()
    if n.denominator != 1 or k.denominator != 1:
        raise ValueError("integer arguments")
    return Expr("num", Fraction(math.comb(int(n), int(k))))


def summation(term, bounds):
    symbol, lower, upper = bounds
    name, term = symbol.args[0], _e(term)
    return Expr("num", sum((term.value({name: Fraction(i)}) for i in range(int(_e(lower)), int(_e(upper)) + 1)),
                           Fraction(0)))


def simplify(expr):
    expr = _e(expr)
    return Expr("num", expr.value()) if not expr.free() else expr


class Float:
    def __init__(self, text):
        self.text = text

    def __str__(self):
        return self.text


def N(expr, digits=15):
    value = _e(expr).value()
    with localcontext() as context:
        context.prec = int(digits)
        return Float(str(Decimal(value.numerator) / Decimal(value.denominator)))
'''


class SympyDocker(FakeDocker):
    """FakeDocker whose containers import ``SYMPY_STUB`` (written to ``<root>/fakelib/sympy.py``, on the worker's
    PYTHONPATH -- an environment key of the local process only; the registered argv is checked unchanged). The
    injected failures are FakeDocker's own."""

    def __init__(self, root, *, image=IMAGE):
        super().__init__(root, image=image)
        self.fakelib = self.root / "fakelib"
        self.fakelib.mkdir(parents=True, exist_ok=True)
        (self.fakelib / "sympy.py").write_text(SYMPY_STUB, encoding="utf-8")

    def spawn(self, argv):
        if self.image_missing or self.fail_starts or self.daemon_down or self.corrupt:
            return super().spawn(argv)
        name, env, mounts = check_argv(argv, self.binary, self.image)
        self.argvs.append(argv)
        root = self.root / name
        (root / "tmp").mkdir(parents=True)
        for target, source in mounts.items():
            (root / target.strip("/")).symlink_to(source, target_is_directory=True)
        process = subprocess.Popen([sys.executable] + TAIL[:3] + [str(root / "runner" / "worker.py")],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env={**env, "PYTHONPATH": str(self.fakelib)}, cwd=root / "tmp",
                                   start_new_session=True)
        self.containers[name] = FakeContainer(name, process, root)
        return process


# ------------------------------------------------------------------------------------------- the role replies
WORDS = """
def applies(view):
    return True

def before_call(view, state):
    return {"facts": ["The question has %d words." % len(view["question"].split())]}
"""
DETECTOR = """
import re


def detect(view):
    replies = view.get("replies") or []
    return re.search(r"[0-9]", str(replies[0] if replies else "")) is None
"""
PARAMS = [  # livemath.derivative parameter sets inside the registered ranges
    {"coefficients": [3, -2, 1], "at": 2, "order": 1},
    {"coefficients": [1, 0, -4, 5], "at": -1, "order": 1},
    {"coefficients": [2, 5], "at": 3, "order": 1},
    {"coefficients": [-1, 4, 0, 2], "at": 1, "order": 2},
    {"coefficients": [5, -3, 2, -7, 1], "at": 0, "order": 2},
    {"coefficients": [4, -9], "at": -5, "order": 1},
]
TRUTHS = ["10", "-1", "2", "2", "4", "4"]  # the derivative values of PARAMS, in order
NOTE_TEXT = ("This helper counts the words of the task's question and shows that count as a short fact, a hint about "
             "how much detail the question carries.")
ROLE_OF = {leakage.ADJUDICATE_SYSTEM: "leakage", engineer.ENGINEER_SYSTEM: "engineer",
           examiner.DETECTOR_SYSTEM: "detector", research.QUERY_SYSTEM: "query", research.PICK_SYSTEM: "pick",
           research.CONCLUDE_SYSTEM["definition"]: "conclude", examiner.GENERATOR_SYSTEM: "generator",
           describer.DESCRIBER_SYSTEM: "describer"}


def _parsed(user):
    try:
        return json.loads(user)
    except ValueError:
        return user


class S3Script:
    """FakeProvider's ``answer(system, user)`` for S3: the reply of each role call by its pinned system prompt (a call
    with any other system prompt fails the test). ``first``: the reply that replaces the first call's (a ``Reply``);
    ``detectors=False``: the examiner writes none; ``found=False``: the researcher concludes "none". ``seen`` lists
    (role, payload) in order."""

    def __init__(self, *, first=None, detectors=True, found=True):
        self.first, self.detectors, self.found = first, detectors, found
        self.seen, self.lock = [], threading.Lock()

    def roles(self):
        return [name for name, _ in self.seen]

    def __call__(self, system, user):
        name, payload = ROLE_OF.get(system), _parsed(user)
        if name is None:
            raise AssertionError("S3 sent an unregistered system prompt")
        with self.lock:
            self.seen.append((name, payload))
            first = len(self.seen) == 1
        if first and self.first is not None:
            return self.first
        return getattr(self, "_" + name)(payload)

    @staticmethod
    def _leakage(payload):
        return json.dumps({"verdict": "no", "reason": "General advice on reading the task."})

    @staticmethod
    def _engineer(payload):
        shown = payload["trajectories"] if isinstance(payload, dict) and payload.get("trajectories") else []
        failed = [t for t in shown if t.get("kind") == "failures"] or shown
        cell = failed[0]["cell"] if failed else "unknown-cell"
        test = {"id": "rt-1", "trajectory": cell, "hook": "before_call",
                "property": {"kind": "note_contains", "value": "words."}, "claims_fix": True,
                "nonvacuity": {"withheld_expect": False, "mutation": None}}
        change = {"kind": "new", "description": "Counts the words of the question.",
                  "hooks": ["applies", "before_call"], "max_note_chars": 600, "replay_tests": [test]}
        return engineer_reply({"changes": [change]}, [WORDS])

    def _detector(self, payload):
        if not self.detectors:
            return fenced(json.dumps({"detectors": []}), "json")
        manifest = {"detectors": [{"description": "Predicts a failure when the first reply carries no digit."}]}
        return fenced(json.dumps(manifest), "json") + "\n\n" + fenced(DETECTOR)

    @staticmethod
    def _query(payload):
        return json.dumps({"queries": ["derivative definition"]})

    @staticmethod
    def _pick(payload):
        return json.dumps({"pages": ["R1"]})

    def _conclude(self, payload):
        if not self.found:
            return json.dumps({"status": "none"})
        return json.dumps({"status": "found", "page": "P1", "quote": DEFINITION})

    @staticmethod
    def _generator(payload):
        materials = payload.get("materials") or [{"id": "no-material"}]
        return json.dumps({"specs": [{"family": "livemath.derivative", "material": materials[0]["id"],
                                      "params": PARAMS}]})

    @staticmethod
    def _describer(payload):
        return NOTE_TEXT


class S3Rehearsal:
    """What ``smoke_roles`` runs on in fake mode: ``transport`` routes glm-5.3 requests to the scripted gateway
    ``glm`` (``script``: an ``S3Script``) and fails the test on any other model's request; ``wikipedia``
    (FakeWikipedia) answers the research; ``docker`` (SympyDocker under ``root``) runs the sandbox."""

    def __init__(self, root, *, script=None):
        self.script = script or S3Script()
        self.glm = FakeProvider(ROLE_MODEL, self.script)
        self.wikipedia = FakeWikipedia()
        self.docker = SympyDocker(Path(root) / "docker")
        self.transport = httpx.MockTransport(self._route)

    def _route(self, request):
        model = json.loads(request.content).get("model")
        if model != ROLE_MODEL:
            raise AssertionError("S3 makes no solver call: a request for %s" % model)
        return self.glm._handle(request)


def wrong_model_first():
    """A first reply echoing another model (the frozen client refuses it: not a confirmed glm-5.3 reply)."""
    return Reply(text=json.dumps({"verdict": "no", "reason": "General advice."}), model="glm-4.6")
