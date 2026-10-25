"""The static policy of procedure source (registration §2.1, §2.6, §5.4 C2-C4; plan §1 policy.py, §4,
T-POLICY-1..6).

Hygiene and determinism, NOT the security boundary: the boundary is the container (§2.6). ``check(source)`` returns
the violations of one procedure module:

- size: at most 6,000 UTF-8 bytes; it must parse;
- module level (§2.1): an optional docstring, imports, constants (one name bound to a literal written in at most
  2,000 characters) and plain function definitions; nothing else (no classes, decorators, async code, ``global``,
  ``nonlocal``);
- imports: only the allowlisted modules, and from-imports only of public members that are not forbidden;
- names (§2.6, by name, not only by import): exec, eval, compile, open, input, the getattr family, globals, locals,
  vars, dir, id, hash, print, breakpoint, help, exit, quit and every dunder name;
- attributes: every private or dunder attribute, frame and code internals, the module names of ``FORBIDDEN_MODULES``
  except ``time`` and ``random`` (``datetime.time`` and a seeded generator's ``random()`` are ordinary), and the
  library entry points that can run code, touch files, read the clock or draw randomness: sympify, parse_expr,
  lambdify, pandas eval/query/read_*/to_*/ExcelFile/ExcelWriter/HDFStore, numpy load/save/fromfile/..., openpyxl.load_workbook, now/today/utcnow,
  and the reflection helpers ``operator.attrgetter``/``methodcaller`` that turn a constructed string into attribute
  access or a method call (Codex 2026-10-22 finding 6; the container stays the real boundary, §2.6);
- ``numpy.random`` only as ``<numpy>.random.default_rng(seed)`` (or ``default_rng(seed)`` imported from
  ``numpy.random``) with exactly one positional seed that is not None; clock strings ("now", "today") passed to
  Timestamp/datetime64/Period; sympy's ``S`` applied to a string; a string literal holding a dunder name (a format
  string can read attributes);
- the three static bans of check C4 (§5.4), applied to every procedure by default because a procedure may fire on
  every bench (§5.7): LiveMath's meta option (any four consecutive words of ``STRONGER_OPTION``, or "stronger
  result" / "stronger statement", anywhere in the source; ``meta_option_hits`` applies the same test to rendered
  notes), OfficeQA bulletin-issue and page literals and ALFWorld numbered receptacle literals (in string literals).

What the policy cannot see (an alias of the numpy module bound by assignment, sympy functions that parse string
arguments themselves) is left to the container and to the engineer's determinism check C6 (two hash seeds, two
orders). ``POLICY`` is the whole policy as data; ``policy_sha256()`` is its canonical-JSON hash (the frozen
``validator_pilot.api.digest`` form) and ``write_policy_json()`` writes exactly those bytes to
``sandbox/policy.json``, which the manifest hashes. This module imports only the standard library, so the sandbox
worker can load this same file from its read-only runner directory and check policy and syntax again inside (plan §4).

v2.3 (owner request 2026-10-25 E3): a separately pinned policy also permits the listed pure constant expressions.
The default policy and its canonical bytes stay frozen; callers select the version explicitly.
"""
from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

POLICY_VERSION = "fivebench-execskill-v1-policy"
POLICY_PATH = Path(__file__).resolve().parent / "sandbox" / "policy.json"
POLICY_VERSION_V23 = "fivebench-execskill-v2-3-policy"
POLICY_VERSION_V24 = POLICY_VERSION_V23.replace("v2-3", "v2-4")
POLICY_PATH_V24 = POLICY_PATH.with_name("policy-v2-4.json")
POLICY_PATH_V23 = POLICY_PATH.with_name("policy-v2-3.json")
BENCHES = ("searchqa", "officeqa", "livemath", "spreadsheetbench", "alfworld")
MAX_SOURCE_BYTES = 6000
MAX_CONSTANT_CHARS = 2000

# the frozen LiveMath meta option, by value (skillopt/coevo5/protocol.py:222)
STRONGER_OPTION = "One of the remaining options is correct, but a stronger result can be proven."
META_PHRASES = ("stronger result", "stronger statement")
META_SHINGLE_WORDS = 4
# ALFWorld (ALFRED) receptacle classes as the text environment spells them
RECEPTACLES = (
    "armchair", "bathtub", "bathtubbasin", "bed", "bowl", "box", "cabinet", "cart", "coffeemachine", "coffeetable",
    "countertop", "cup", "desk", "diningtable", "drawer", "dresser", "fridge", "garbagecan", "handtowelholder",
    "laundryhamper", "microwave", "mug", "ottoman", "paintinghanger", "pan", "plate", "pot", "safe", "shelf",
    "sidetable", "sinkbasin", "sofa", "stoveburner", "toaster", "toilet", "toiletpaperhanger", "towelholder",
    "tvstand",
)
MONTHS = ("january|february|march|april|may|june|july|august|september|october|november|december"
          "|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")
BULLETIN_PATTERNS = (
    r"treasury[\s_-]*bulletin[\s_-]*\d",  # a bulletin file or issue: treasury_bulletin_1985_03
    r"\b(?:%s)\.?,?\s+(?:18|19|20)\d\d\b" % MONTHS,  # an issue month: March 1985
    r"\bpages?\s*\d+",  # page 23
    r"\bpp?\.\s*\d+",  # p. 23, pp. 4
)
RECEPTACLE_PATTERN = r"\b(?:%s)\s+\d+\b" % "|".join(sorted(RECEPTACLES, key=len, reverse=True))

IMPORTABLE = (  # ``import X`` and ``from X import <public member>``
    "bisect", "calendar", "collections", "copy", "datetime", "decimal", "difflib", "fractions", "functools", "heapq",
    "itertools", "json", "math", "numpy", "openpyxl.utils", "operator", "pandas", "re", "statistics", "string",
    "sympy", "textwrap", "unicodedata",
)
FROM_ONLY = {  # ``from X import <listed member>`` only
    "numpy.random": ("default_rng",),
    "openpyxl.utils.cell": ("column_index_from_string", "coordinate_from_string", "get_column_letter",
                            "range_boundaries"),
}
FORBIDDEN_NAMES = (
    "breakpoint", "compile", "delattr", "dir", "eval", "exec", "exit", "getattr", "globals", "hasattr", "hash",
    "help", "id", "input", "locals", "open", "print", "quit", "setattr", "vars",
)
FORBIDDEN_MODULES = (
    "asyncio", "atexit", "builtins", "code", "codeop", "concurrent", "ctypes", "faulthandler", "fcntl", "gc", "glob",
    "http", "httpx", "importlib", "inspect", "io", "logging", "marshal", "mmap", "multiprocessing", "os", "pathlib",
    "pickle", "platform", "pty", "queue", "random", "requests", "resource", "runpy", "sched", "secrets", "select",
    "shelve", "shutil", "signal", "site", "socket", "sqlite3", "ssl", "subprocess", "sys", "sysconfig", "tarfile",
    "tempfile", "threading", "time", "traceback", "tracemalloc", "urllib", "uuid", "warnings", "zipfile",
)
ORDINARY_ATTRIBUTES = ("random", "time")  # module names that are also ordinary attribute names
FORBIDDEN_ATTRIBUTES = (
    "ExcelFile", "ExcelWriter", "HDFStore",  # file-reading/-writing constructors (isolation review 9)
    # attrgetter/methodcaller turn a CONSTRUCTED string into attribute access, so the literal dunder check cannot see
    # a name like ``"_"*2 + "globals" + "_"*2``; banning them closes that reflection route (Codex 2026-10-22 finding 6)
    "ag_code", "ag_frame", "attrgetter", "cr_code", "cr_frame", "eval", "f_back", "f_builtins", "f_code", "f_globals",
    "f_locals", "format_map", "fromfile", "fromregex", "genfromtxt", "gi_code", "gi_frame", "gi_yieldfrom", "lambdify",
    "load", "load_workbook", "loadtxt", "memmap", "methodcaller", "mro", "now", "parse_expr", "parsing", "query",
    "save", "savetxt", "savez", "savez_compressed", "sympify", "tb_frame", "tb_next", "today", "tofile", "utcnow",
)
FORBIDDEN_ATTRIBUTE_PREFIXES = ("_", "read_", "to_")
FORBIDDEN_STATEMENTS = ("AsyncFor", "AsyncFunctionDef", "AsyncWith", "Await", "ClassDef", "Global", "Nonlocal")
CLOCK_CALLS = ("Period", "Timestamp", "datetime64")
CLOCK_STRINGS = ("now", "today")
DUNDER_STRING = r"__[A-Za-z][A-Za-z0-9_]*__"
RULES = ("size", "syntax", "module_level", "constant_size", "statement", "decorator", "import", "name", "attribute",
         "numpy_random", "clock", "sympify", "dunder_string", "meta_option", "bulletin_literal", "receptacle_literal")

POLICY = {
    "version": POLICY_VERSION,
    "registration": "fivebench-execskill-v1 registration §2.1, §2.6, §5.4 C2-C4",
    "rules": list(RULES),
    "max_source_bytes": MAX_SOURCE_BYTES,
    "max_constant_chars": MAX_CONSTANT_CHARS,
    "module_level": ["docstring", "import", "constant", "function"],
    "importable": list(IMPORTABLE),
    "from_only": {module: list(members) for module, members in FROM_ONLY.items()},
    "forbidden_names": list(FORBIDDEN_NAMES),
    "forbidden_modules": list(FORBIDDEN_MODULES),
    "ordinary_attributes": list(ORDINARY_ATTRIBUTES),
    "forbidden_attributes": list(FORBIDDEN_ATTRIBUTES),
    "forbidden_attribute_prefixes": list(FORBIDDEN_ATTRIBUTE_PREFIXES),
    "forbidden_statements": list(FORBIDDEN_STATEMENTS),
    "seeded_random": {"module": "numpy", "attribute": "random", "only": "default_rng", "positional_seeds": 1},
    "clock_calls": list(CLOCK_CALLS),
    "clock_strings": list(CLOCK_STRINGS),
    "sympify_calls": ["S"],
    "dunder_string": DUNDER_STRING,
    "static_bans": {
        "livemath": {"sentence": STRONGER_OPTION, "phrases": list(META_PHRASES), "shingle_words": META_SHINGLE_WORDS,
                     "scope": "source text and rendered notes"},
        "officeqa": {"patterns": list(BULLETIN_PATTERNS), "flags": "IGNORECASE", "scope": "string literals"},
        "alfworld": {"pattern": RECEPTACLE_PATTERN, "flags": "IGNORECASE", "scope": "string literals"},
    },
}
POLICY_V23 = {**POLICY, "version": POLICY_VERSION_V23,
              "registration": "Route B v2.3 request 2026-10-25 E3",
              "constant_expressions": ["literal", "re.compile(str[, re flags joined by |])",
                                       "set/frozenset(literal iterable)", "tuple/list/dict/sorted(literal)",
                                       "str.split([str])", "str.join(literal list/tuple of str)",
                                       "same-type literal +", "previous constant name"],
              "constant_bindings": "whole-module, all-scope binding audit; plain import re exempt; constructors, "
                                   "re, compile and used flags must be unbound elsewhere; referenced constants "
                                   "must have one defining assignment and audited dependencies; otherwise literal-only"}
POLICY_V24 = {**POLICY_V23, "version": POLICY_VERSION_V24,
              "registration": "Route B v2.4 request 2026-10-25 item 5", "max_source_bytes": 10_000}
POLICIES = {POLICY_VERSION: POLICY, POLICY_VERSION_V23: POLICY_V23, POLICY_VERSION_V24: POLICY_V24}

BULLETIN = re.compile("|".join("(?:%s)" % p for p in BULLETIN_PATTERNS), re.I)
RECEPTACLE = re.compile(RECEPTACLE_PATTERN, re.I)
DUNDER = re.compile(DUNDER_STRING)


def _words(text):
    return " ".join(re.findall(r"[a-z0-9]+", text.casefold()))


_SENTENCE = _words(STRONGER_OPTION).split()
META_TERMS = tuple(dict.fromkeys(
    list(META_PHRASES) + [" ".join(_SENTENCE[i:i + META_SHINGLE_WORDS])
                          for i in range(len(_SENTENCE) - META_SHINGLE_WORDS + 1)]))


@dataclass(frozen=True)
class Violation:
    rule: str
    detail: str
    line: int = 0

    def to_json(self):
        return {"rule": self.rule, "detail": self.detail, "line": self.line}


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def policy_sha256(*, version=POLICY_VERSION):
    """The canonical-JSON hash of ``POLICY`` (equal to ``validator_pilot.api.digest(POLICY)``)."""
    return hashlib.sha256(_canonical(POLICIES[version])).hexdigest()


def source_limit(version=POLICY_VERSION):
    """The UTF-8 source byte limit of the explicitly selected policy."""
    if type(version) is not str or version not in POLICIES:
        raise ValueError("Unknown policy version")
    return POLICIES[version]["max_source_bytes"]


def write_policy_json(path=None, *, version=POLICY_VERSION):
    """Write ``POLICY`` as canonical JSON, so the file's sha256 is ``policy_sha256()``. An existing file must hold the
    same bytes: a changed policy is a new protocol version, never an overwrite."""
    paths = {POLICY_VERSION: POLICY_PATH, POLICY_VERSION_V23: POLICY_PATH_V23, POLICY_VERSION_V24: POLICY_PATH_V24}
    path = Path(path) if path is not None else paths[version]
    data = _canonical(POLICIES[version])
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("policy.json differs from POLICY; a changed policy needs a new protocol version")
        return policy_sha256(version=version)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return policy_sha256(version=version)


def _literal(node):
    try:
        return True, ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return False, None


RE_FLAGS = frozenset({"A", "ASCII", "I", "IGNORECASE", "L", "LOCALE", "M", "MULTILINE", "S", "DOTALL",
                      "U", "UNICODE", "X", "VERBOSE", "DEBUG", "NOFLAG", "T", "TEMPLATE"})
CONSTRUCTORS = frozenset({"set", "frozenset", "tuple", "list", "dict", "sorted"})


def _re_flags(node, bound):
    return ((isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "re"
             and node.attr in RE_FLAGS and node.attr not in bound)
            or (isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
                and _re_flags(node.left, bound) and _re_flags(node.right, bound)))


def _constant_bindings(tree):
    """Review finding 1: every binding counts, regardless of its scope or evaluation order.

    Keep defining nodes so a previous constant can exempt exactly its own assignment. Attribute/subscript
    targets also invalidate their root; flag/compile attribute writes count through aliases conservatively.
    No expression is executed and only a plain ``import re`` is exempt from the import census.
    """
    bound = {}

    def add(name, node):
        if name:
            bound.setdefault(name, []).append(node)

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            add(node.id, node)
        elif isinstance(node, ast.arg):
            add(node.arg, node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            add(node.name, node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if isinstance(node, ast.Import) and alias.name == "re" and alias.asname is None:
                    continue
                add(alias.asname or (alias.name.split(".")[0] if isinstance(node, ast.Import) else alias.name), node)
        elif isinstance(node, ast.ExceptHandler):
            add(node.name, node)
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            for name in node.names:
                add(name, node)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)):
            add(node.name, node)
        elif isinstance(node, ast.MatchMapping):
            add(node.rest, node)
        elif type(node).__name__ in ("TypeVar", "ParamSpec", "TypeVarTuple"):
            add(node.name, node)
        elif isinstance(node, (ast.Attribute, ast.Subscript)) and isinstance(node.ctx, (ast.Store, ast.Del)):
            if isinstance(node, ast.Attribute) and node.attr in RE_FLAGS | {"compile"}:
                add(node.attr, node)
            root = node.value
            while isinstance(root, (ast.Attribute, ast.Subscript)):
                root = root.value
            if isinstance(root, ast.Name):
                add(root.id, node)
    return bound


def _unbound_literal_names(node, bound):
    # ast.literal_eval permits set() even inside container literals. When a larger, newly admitted expression
    # uses that spelling, it still relies on the actual builtin, rather than an arbitrary binding named set.
    return not any(isinstance(part, ast.Name) and isinstance(part.ctx, ast.Load)
                   and (part.id in bound or "*" in bound) for part in ast.walk(node))


def _addition_type(node):
    literal, value = _literal(node)
    if literal:
        return type(value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _addition_type(node.left), _addition_type(node.right)
        if left is right and left in (str, bytes, bool, int, float, complex, list, tuple):
            return left
    return None


def _pure_constant(node, defined, bound, re_imported):
    """E3's closed AST grammar; no procedure expression is executed by the validator."""
    if _literal(node)[0]:
        return True
    if isinstance(node, ast.Name):
        return node.id in defined
    if not _unbound_literal_names(node, bound):
        return False
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _addition_type(node) is not None
    if not isinstance(node, ast.Call) or node.keywords or any(isinstance(a, ast.Starred) for a in node.args):
        return False
    if isinstance(node.func, ast.Name) and node.func.id in CONSTRUCTORS and node.func.id not in bound:
        if len(node.args) != 1:
            return False
        literal, value = _literal(node.args[0])
        return literal and (node.func.id not in ("set", "frozenset")
                            or isinstance(value, (str, bytes, list, tuple, set, dict)))
    if not isinstance(node.func, ast.Attribute):
        return False
    obj, method = node.func.value, node.func.attr
    if (isinstance(obj, ast.Name) and obj.id == "re" and re_imported and method == "compile"
            and "compile" not in bound):
        return (len(node.args) in (1, 2) and isinstance(node.args[0], ast.Constant)
                and type(node.args[0].value) is str and (len(node.args) == 1 or _re_flags(node.args[1], bound)))
    if not isinstance(obj, ast.Constant) or type(obj.value) is not str:
        return False
    if method == "split":
        return len(node.args) == 0 or (len(node.args) == 1 and isinstance(node.args[0], ast.Constant)
                                       and type(node.args[0].value) is str)
    if method == "join" and len(node.args) == 1 and isinstance(node.args[0], (ast.List, ast.Tuple)):
        return all(isinstance(a, ast.Constant) and type(a.value) is str for a in node.args[0].elts)
    return False


def _module_level_v23(source, tree):
    out, defined, bound, re_imported = [], set(), _constant_bindings(tree), False
    for index, node in enumerate(tree.body):
        if (index == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and type(node.value.value) is str):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name = alias.asname or (alias.name.split(".")[0] if isinstance(node, ast.Import) else alias.name)
                defined.discard(name)
                if name == "re":
                    re_imported = isinstance(node, ast.Import) and alias.name == "re" and alias.asname is None
            continue
        if isinstance(node, ast.FunctionDef):
            defined.discard(node.name)
            if node.name == "re":
                re_imported = False
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            allowed = _pure_constant(node.value, defined, bound, re_imported)
            written = ast.get_source_segment(source, node.value) or ""
            if not allowed:
                out.append(Violation("module_level", "a constant must be a literal or a registered pure expression",
                                     node.lineno))
            elif len(written) > MAX_CONSTANT_CHARS:
                out.append(Violation("constant_size", "%d characters" % len(written), node.lineno))
            elif (bound.get(name) == [node.targets[0]] and "*" not in bound
                  and (not _literal(node.value)[0] or _unbound_literal_names(node.value, bound))):
                defined.add(name)
            if not allowed or len(written) > MAX_CONSTANT_CHARS:
                defined.discard(name)
            if name == "re":
                re_imported = False
            continue
        out.append(Violation("module_level", type(node).__name__, node.lineno))
    return out


def meta_option_hits(text):
    """The LiveMath meta-option terms (§5.4 C4) in ``text``: whole words, ignoring case and punctuation."""
    padded = " " + _words(text) + " "
    return [term for term in META_TERMS if " " + term + " " in padded]


def literal_hits(text):
    """The OfficeQA bulletin and ALFWorld receptacle literals (§5.4 C4) in one string: [(rule, hit)]."""
    return ([("bulletin_literal", m.group(0)) for m in BULLETIN.finditer(text)]
            + [("receptacle_literal", m.group(0)) for m in RECEPTACLE.finditer(text)])


def _module_level(source, tree):
    out = []
    for index, node in enumerate(tree.body):
        if (index == 0 and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and type(node.value.value) is str):
            continue
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef)):
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                out.append(Violation("module_level", "a constant must be a literal", node.lineno))
                continue
            written = ast.get_source_segment(source, node.value) or ""
            if len(written) > MAX_CONSTANT_CHARS:
                out.append(Violation("constant_size", "%d characters" % len(written), node.lineno))
            continue
        out.append(Violation("module_level", type(node).__name__, node.lineno))
    return out


def _numpy_names(tree):
    return {alias.asname or "numpy" for node in ast.walk(tree) if isinstance(node, ast.Import)
            for alias in node.names if alias.name == "numpy"}


def _forbidden_member(name):
    return (name in FORBIDDEN_NAMES or name in FORBIDDEN_ATTRIBUTES or name in FORBIDDEN_MODULES
            or name.startswith(FORBIDDEN_ATTRIBUTE_PREFIXES))


def _imports(node):
    if isinstance(node, ast.Import):
        return [Violation("import", a.name, node.lineno) for a in node.names if a.name not in IMPORTABLE]
    module = node.module or ""
    if node.level or (module not in IMPORTABLE and module not in FROM_ONLY):
        return [Violation("import", "." * node.level + module, node.lineno)]
    allowed = FROM_ONLY.get(module)
    return [Violation("import", "%s.%s" % (module, a.name), node.lineno) for a in node.names
            if a.name == "*" or (allowed is not None and a.name not in allowed) or _forbidden_member(a.name)]


def _seeded(call):
    return (isinstance(call, ast.Call) and len(call.args) == 1 and not call.keywords
            and not isinstance(call.args[0], ast.Starred)
            and not (isinstance(call.args[0], ast.Constant) and call.args[0].value is None))


def _attribute(node, parents, numpy_names):
    if node.attr == "random" and isinstance(node.value, ast.Name) and node.value.id in numpy_names:
        parent = parents.get(node)
        call = parents.get(parent)
        if (isinstance(parent, ast.Attribute) and parent.attr == "default_rng" and isinstance(call, ast.Call)
                and call.func is parent and _seeded(call)):
            return []
        return [Violation("numpy_random", "numpy.random is allowed only as default_rng(seed)", node.lineno)]
    if (node.attr in FORBIDDEN_ATTRIBUTES or node.attr.startswith(FORBIDDEN_ATTRIBUTE_PREFIXES)
            or (node.attr in FORBIDDEN_MODULES and node.attr not in ORDINARY_ATTRIBUTES)):
        return [Violation("attribute", node.attr, node.lineno)]
    return []


def _call(node):
    callee = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
    strings = [a.value for a in node.args if isinstance(a, ast.Constant) and type(a.value) is str]
    if callee == "default_rng" and not _seeded(node):
        return [Violation("numpy_random", "default_rng needs exactly one positional seed", node.lineno)]
    if callee in CLOCK_CALLS and any(s.strip().casefold() in CLOCK_STRINGS for s in strings):
        return [Violation("clock", callee, node.lineno)]
    if callee == "S" and strings:
        return [Violation("sympify", "S(<string>)", node.lineno)]
    return []


def _node(node, parents, numpy_names):
    line = getattr(node, "lineno", 0)
    if type(node).__name__ in FORBIDDEN_STATEMENTS:
        return [Violation("statement", type(node).__name__, line)]
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        return _imports(node)
    if isinstance(node, ast.FunctionDef):
        out = [Violation("decorator", node.name, line)] if node.decorator_list else []
        return out + ([Violation("name", node.name, line)]
                      if node.name.startswith("__") or node.name in FORBIDDEN_NAMES else [])
    names = {ast.arg: "arg", ast.alias: "asname", ast.Name: "id"}
    if type(node) in names:
        name = getattr(node, names[type(node)]) or ""
        return [Violation("name", name, line)] if name.startswith("__") or name in FORBIDDEN_NAMES else []
    if isinstance(node, ast.Attribute):
        return _attribute(node, parents, numpy_names)
    if isinstance(node, ast.Call):
        return _call(node)
    if isinstance(node, ast.Constant) and type(node.value) is str:
        return ([Violation("dunder_string", m.group(0), line) for m in DUNDER.finditer(node.value)]
                + [Violation(rule, hit, line) for rule, hit in literal_hits(node.value)])
    return []


def check(source, *, bench=None, version=POLICY_VERSION):
    """The violations of one procedure module, sorted (empty: the module passes). ``bench`` restricts the static bans
    of §5.4 C4 to that bench's; ``None`` applies every bench's, as for a procedure whose scope is every bench."""
    if type(version) is not str or version not in POLICIES:
        raise ValueError("Unknown policy version")
    if bench is not None and bench not in BENCHES + ("zebralogic",):
        raise ValueError("Unknown bench")
    if type(source) is not str:
        return [Violation("size", "source is not text")]
    size = len(source.encode("utf-8"))
    if size > source_limit(version):
        return [Violation("size", "%d bytes" % size)]
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, MemoryError, RecursionError) as error:
        return [Violation("syntax", type(error).__name__, getattr(error, "lineno", 0) or 0)]
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    numpy_names = _numpy_names(tree)
    out = (_module_level_v23 if version in (POLICY_VERSION_V23, POLICY_VERSION_V24) else _module_level)(source, tree)
    for node in ast.walk(tree):
        out.extend(_node(node, parents, numpy_names))
    if bench in (None, "livemath"):
        out.extend(Violation("meta_option", term) for term in meta_option_hits(source))
    banned = {None: ("bulletin_literal", "receptacle_literal"), "officeqa": ("bulletin_literal",),
              "alfworld": ("receptacle_literal",)}.get(bench, ())
    out = [v for v in out if v.rule not in ("bulletin_literal", "receptacle_literal") or v.rule in banned]
    return sorted(set(out), key=lambda v: (v.line, v.rule, v.detail))
