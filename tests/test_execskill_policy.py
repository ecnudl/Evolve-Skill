"""T-POLICY-1..6: the static procedure policy (registration §2.1, §2.6, §5.4 C2-C4; plan §1 policy.py, §8.1)."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from skillopt.coevo5.protocol import STRONGER_OPTION as FROZEN_STRONGER_OPTION
from skillopt.execskill import policy, protocol
from skillopt.execskill.policy import POLICY, check, meta_option_hits, policy_sha256, write_policy_json
from skillopt.validator_pilot.api import digest

ALLOWED = '''"""Fixture: a well-behaved procedure using every allowlisted library."""
import collections
import math
import re
from datetime import date
from fractions import Fraction

import numpy as np
import pandas as pd
import sympy
from numpy.random import default_rng
from openpyxl.utils import get_column_letter

LIMIT = 5
NAMES = ("total", "sum")


def applies(view):
    return "question" in view and bool(re.search(r"\\d", view["question"]))


def before_call(view, state):
    numbers = [Fraction(n) for n in re.findall(r"\\d+", view["question"])][:LIMIT]
    counts = collections.Counter(view["question"].split())
    rng = np.random.default_rng(7)
    other = default_rng(11)
    frame = pd.DataFrame({"n": [float(n) for n in numbers]})
    x = sympy.Symbol("x")
    facts = ["%d numbers" % len(numbers), "column %s" % get_column_letter(3), str(sympy.Rational(1, 3) + x),
             "mean %.2f" % float(frame["n"].mean() if len(frame) else 0), str(math.gcd(12, 18)),
             str(rng.random() < 2), str(other.integers(0, 2) < 2), str(date(2020, 1, 1).year), str(len(counts))]
    return {"facts": facts}
'''


def source(body, imports=""):
    return imports + "\n\ndef applies(view):\n    return True\n\n\ndef before_call(view, state):\n" + "".join(
        "    " + line + "\n" for line in body.splitlines())


def rules(text, **kwargs):
    return {v.rule for v in check(text, **kwargs)}


# ------------------------------------------------------------------------------------- T-POLICY-1 forbidden names
@pytest.mark.parametrize("name", policy.FORBIDDEN_NAMES)
def test_each_forbidden_name_rejected(name):
    assert "name" in rules(source("x = %s\nreturn {}" % name))


@pytest.mark.parametrize("text", [
    "x = __builtins__\nreturn {}",
    "def __init__(a):\n    return a\nreturn {}",
    "return {'facts': [str(view.__class__)]}",
])
def test_dunder_names_and_attributes_rejected(text):
    assert rules(source(text)) & {"name", "attribute"}


# --------------------------------------------------------------------------------- T-POLICY-2 forbidden attributes
@pytest.mark.parametrize("attribute", [
    "sympify", "parse_expr", "lambdify", "load_workbook", "now", "today", "utcnow", "query", "eval", "read_csv",
    "read_excel", "to_csv", "to_numeric", "load", "save", "fromfile", "_values", "gi_frame", "f_globals", "os",
    "sys", "subprocess", "builtins", "format_map",
])
def test_each_forbidden_attribute_rejected(attribute):
    assert "attribute" in rules(source("return view.%s" % attribute))


@pytest.mark.parametrize("text, ok", [
    ("rng = np.random.default_rng(0)\nreturn {}", True),
    ("rng = np.random.default_rng(seed)\nreturn {}", True),
    ("return {'facts': [str(np.random.rand())]}", False),
    ("rng = np.random.default_rng()\nreturn {}", False),
    ("rng = np.random.default_rng(None)\nreturn {}", False),
    ("rng = np.random.default_rng(seed=1)\nreturn {}", False),
    ("make = np.random.default_rng\nreturn {}", False),
    ("rng = state['rng']\nreturn {'facts': [str(rng.random())]}", True),
])
def test_numpy_random_only_as_seeded_default_rng(text, ok):
    found = rules(source(text, "import numpy as np"))
    assert (not found) if ok else ("numpy_random" in found)


def test_from_numpy_random_import_default_rng_needs_a_seed():
    imports = "from numpy.random import default_rng"
    assert not rules(source("rng = default_rng(3)\nreturn {}", imports))
    assert "numpy_random" in rules(source("rng = default_rng()\nreturn {}", imports))


@pytest.mark.parametrize("text, rule", [
    ("return {'facts': [str(pd.Timestamp('now'))]}", "clock"),
    ("return {'facts': [str(np.datetime64(' Today '))]}", "clock"),
    ("return {'facts': [str(sympy.S('x+1'))]}", "sympify"),
    ("return {'facts': ['{0.__class__}'.format(view)]}", "dunder_string"),
])
def test_clock_strings_sympify_and_format_strings(text, rule):
    assert rule in rules(source(text, "import numpy as np\nimport pandas as pd\nimport sympy"))


# ---------------------------------------------------------------------------------- T-POLICY-3 module-level shape
@pytest.mark.parametrize("text, rule", [
    ("X = compute()\n", "module_level"),
    ("X = [1, 2] * 3\n", "module_level"),
    ("if True:\n    X = 1\n", "module_level"),
    ("for i in range(3):\n    pass\n", "module_level"),
    ("try:\n    X = 1\nexcept Exception:\n    X = 2\n", "module_level"),
    ('"""doc"""\n"""second string"""\n', "module_level"),
    ("X: int = 1\n", "module_level"),
    ("class Helper:\n    pass\n", "statement"),
    ("async def f():\n    return 1\n", "statement"),
    ("def f():\n    global X\n    return 1\n", "statement"),
    ("import functools\n\n\n@functools.lru_cache\ndef f(x):\n    return x\n", "decorator"),
    ("X = '%s'\n" % ("a" * 2001), "constant_size"),
])
def test_module_level_statements_rejected(text, rule):
    assert rule in rules(text)


def test_module_level_literals_docstring_and_functions_pass():
    text = '"""doc"""\nimport re\nX = %r\nT = (1, -2.5, None, True, {"a": [1, 2]})\n\n\ndef f(x):\n    return x\n' % (
        "a" * 1990)
    assert check(text) == []


def test_size_and_syntax():
    assert rules("X = 1\n" + "#" * 6000) == {"size"}
    assert rules("def f(:\n") == {"syntax"}
    assert rules(None) == {"size"}
    assert policy.MAX_SOURCE_BYTES == protocol.MAX_PROCEDURE_BYTES == 6000
    assert policy.MAX_CONSTANT_CHARS == protocol.MAX_CONSTANT_CHARS == 2000


# --------------------------------------------------------------------------------- T-POLICY-4 C4 static literals
@pytest.mark.parametrize("text", [
    "# pick the option saying a stronger result can be proven\nX = 1\n",
    "X = 'One of the remaining options is correct'\n",
    "X = 'prefer the STRONGER   statement'\n",
    "X = '%s'\n" % FROZEN_STRONGER_OPTION,
])
def test_livemath_meta_option_fragments_rejected(text):
    assert "meta_option" in rules(text)
    assert "meta_option" in rules(text, bench="livemath")
    assert "meta_option" not in rules(text, bench="officeqa")


@pytest.mark.parametrize("literal", [
    "treasury_bulletin_1985_03.txt", "Treasury Bulletin 1990", "see March 1985", "Sept. 2001 issue", "page 23",
    "pages 4-5", "p. 17",
])
def test_officeqa_bulletin_literals_rejected(literal):
    text = "X = %r\n" % literal
    assert "bulletin_literal" in rules(text)
    assert "bulletin_literal" in rules(text, bench="officeqa")
    assert "bulletin_literal" not in rules(text, bench="alfworld")


@pytest.mark.parametrize("literal", ["drawer 3", "go to countertop 12", "Cabinet 1", "the sinkbasin 2 is empty"])
def test_alfworld_numbered_receptacle_literals_rejected(literal):
    text = "def applies(view):\n    return %r in view['observation']\n" % literal
    assert "receptacle_literal" in rules(text)
    assert "receptacle_literal" in rules(text, bench="alfworld")
    assert "receptacle_literal" not in rules(text, bench="spreadsheetbench")


def test_unnumbered_and_ordinary_text_passes():
    text = ("X = ('drawer', 'go to', 'Treasury Bulletin tables', 'the result can be checked', 'March')\n"
            "def applies(view):\n    return 'drawer' in view['observation']\n")
    assert check(text) == []
    with pytest.raises(ValueError):
        check(text, bench="nowhere")


def test_meta_option_hits_on_rendered_text():
    assert meta_option_hits("A stronger result can be proven here.")
    assert meta_option_hits("Result: stronger") == []
    assert policy.STRONGER_OPTION == FROZEN_STRONGER_OPTION == protocol.LIVEMATH_META_OPTION


# ------------------------------------------------------------------------------------------ T-POLICY-5 imports
def test_allowed_imports_pass():
    assert check(ALLOWED) == []


@pytest.mark.parametrize("statement", [
    "import os", "import sys", "import subprocess", "import random", "import time", "import pathlib", "import io",
    "import importlib", "import pickle", "import socket", "import threading", "import ctypes", "import openpyxl",
    "import numpy.random", "from os import path", "from . import helper", "from numpy import random",
    "from pandas import read_csv", "from sympy import sympify", "from math import *", "from datetime import time",
    "from numpy.random import rand", "from openpyxl import load_workbook",
])
def test_disallowed_imports_rejected(statement):
    assert "import" in rules(statement + "\n")


# ---------------------------------------------------------------------- T-POLICY-6 the policy as data, hashed
def test_policy_is_canonical_json_and_hashed_like_digest():
    assert json.loads(json.dumps(POLICY)) == POLICY
    assert policy_sha256() == digest(POLICY)
    assert POLICY["version"] == protocol.kind("policy")
    assert tuple(policy.BENCHES) == protocol.BENCHES
    assert set(POLICY["rules"]) >= {v.rule for v in check("import os\nX = f()\n")}


def test_policy_json_in_the_tree_is_current(tmp_path):
    shipped = policy.POLICY_PATH
    assert shipped.exists(), "regenerate with policy.write_policy_json()"
    assert hashlib.sha256(shipped.read_bytes()).hexdigest() == policy_sha256()
    copy = tmp_path / "policy.json"
    assert write_policy_json(copy) == policy_sha256() and copy.read_bytes() == shipped.read_bytes()
    assert write_policy_json(copy) == policy_sha256()  # the same bytes again: no-op
    copy.write_text("{}")
    with pytest.raises(ValueError):
        write_policy_json(copy)


def test_policy_module_imports_only_the_standard_library():
    tree = ast.parse(Path(policy.__file__).read_text(encoding="utf-8"))
    modules = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    modules |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert modules == {"__future__", "ast", "hashlib", "json", "re", "dataclasses", "pathlib"}


# ------------------------------------------------------------------------- fixer regressions (reviews 2026-10-22)
def test_isolation_9_file_reading_constructors_are_banned():
    for source in ('import pandas as pd\n\ndef before_call(view, state):\n'
                   '    return {"facts": [str(pd.ExcelFile("/input/1_1_answer.xlsx").parse(0))]}\n',
                   'import pandas as pd\n\ndef before_call(view, state):\n    return {"facts": [str(pd.HDFStore("x"))]}\n'):
        assert any(v.rule == "attribute" for v in check(source)), source


# ------------------------------- reflection helpers that build attribute access from a string (Codex 2026-10-22 #6)
# A constructed name like ``"_" * 2 + "globals" + "_" * 2`` is not a literal, so the dunder-string rule never sees it;
# ``operator.attrgetter("__globals__")(safe_sympify)["os"]`` would then reach the worker helper's ``os`` module. The
# container is the real boundary (§2.6), but the policy must still refuse the helpers that turn a constructed string
# into attribute access (``attrgetter``) or a method call (``methodcaller``).
REFLECTION = {
    "attrgetter-dotted": "import operator\n\n\ndef applies(view):\n    return operator.attrgetter('real')(view) is None\n",
    "attrgetter-aliased": "import operator as op\n\n\ndef applies(view):\n    return op.attrgetter('real')(view) is None\n",
    "attrgetter-constructed-dunder": (
        "import operator\n\n\ndef before_call(view, state):\n"
        "    name = '_' * 2 + 'globals' + '_' * 2\n"
        "    return {'facts': [str(operator.attrgetter(name)(view))]}\n"),
    "methodcaller-constructed-dunder": (
        "import operator\n\n\ndef before_call(view, state):\n"
        "    return {'facts': [str(operator.methodcaller('_' * 2 + 'class' + '_' * 2)(view))]}\n"),
}


@pytest.mark.parametrize("name", sorted(REFLECTION))
def test_reflection_helpers_that_build_attribute_access_from_a_string_are_banned(name):
    assert "attribute" in {v.rule for v in check(REFLECTION[name])}


@pytest.mark.parametrize("statement", ["from operator import attrgetter", "from operator import methodcaller"])
def test_reflection_helpers_cannot_be_from_imported(statement):
    assert "import" in rules(statement + "\n")


def test_operator_non_reflection_members_still_pass():
    assert check("import operator\n\n\ndef applies(view):\n    return operator.add(1, 2) == 3\n") == []
