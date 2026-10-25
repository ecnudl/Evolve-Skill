"""Accepted Codex review finding 1: whole-module binding audit, without executing procedure source."""
from __future__ import annotations

import ast
import hashlib

import pytest

from skillopt.execskill import policy
from skillopt.execskill.sandbox import worker

V23 = policy.POLICY_VERSION_V23
HOOKS = "def applies(view):\n    return True\n"


def load(source, version=V23):
    return worker.handle_load({
        "seq": 1, "package_sha256": "a" * 64, "policy_version": version,
        "policy_sha256": policy.policy_sha256(version=version),
        "procedures": [{"id": "review", "source": source, "hooks": ["applies"], "policy_version": version}],
        "limits": {"address_space_mb": 2048, "frame_bytes": 1 << 20},
    }, {"loaded": None}, policy)


def rejected_assignment(source, name="X"):
    line = next(i for i, text in enumerate(source.splitlines(), 1) if text.startswith(name + " = "))
    assert any(v.rule == "module_level" and v.line == line for v in policy.check(source, version=V23))
    result = load(source)
    assert result["ok"] and not result["loaded"]
    assert "module_level" in result["rejected"][0]["reason"]


BINDINGS = [
    "def shadow(arg=($NAME := EVENTS.append)):\n    return arg",
    "def shadow(arg: ($NAME := 1)):\n    return arg",
    "def shadow() -> ($NAME := 1):\n    return 1",
    "@($NAME := lambda fn: fn)\ndef shadow():\n    return 1",
    "def shadow(arg=[($NAME := 1) for item in []]):\n    return arg",
    "def shadow(arg=[$NAME for $NAME in []]):\n    return arg",
    "def shadow(arg=(lambda: ($NAME := 1))):\n    return arg",
    "def shadow(arg=(lambda $NAME: 1)):\n    return arg",
    "$NAME = 1",
    "$NAME: int = 1",
    "$NAME: int",
    "$NAME += 1",
    "def shadow():\n    $NAME = 1",
    "def shadow():\n    $NAME: int = 1",
    "def shadow():\n    $NAME += 1",
    "def shadow():\n    $NAME, other = (1, 2)",
    "def shadow():\n    [$NAME, *other] = [1, 2]",
    "def shadow():\n    first, *$NAME = [1, 2]",
    "def $NAME(arg):\n    return arg",
    "async def $NAME(arg):\n    return arg",
    "class $NAME:\n    pass",
    "def shadow($NAME):\n    return 1",
    "def shadow($NAME, /):\n    return 1",
    "def shadow(*$NAME):\n    return 1",
    "def shadow(*, $NAME):\n    return 1",
    "def shadow(**$NAME):\n    return 1",
    "import math as $NAME",
    "from math import pi as $NAME",
    "def shadow():\n    import math as $NAME",
    "def shadow():\n    from math import pi as $NAME",
    "def shadow():\n    for $NAME in []:\n        pass",
    "async def shadow():\n    async for $NAME in []:\n        pass",
    "def shadow():\n    with resource as $NAME:\n        pass",
    "async def shadow():\n    async with resource as $NAME:\n        pass",
    "def shadow():\n    try:\n        pass\n    except ValueError as $NAME:\n        pass",
    "def shadow():\n    global $NAME",
    "def shadow():\n    nonlocal $NAME",
    "def shadow(value):\n    match value:\n        case $NAME:\n            pass",
    "def shadow(value):\n    match value:\n        case [*$NAME]:\n            pass",
    "def shadow(value):\n    match value:\n        case {\"key\": $NAME}:\n            pass",
    "def shadow(value):\n    match value:\n        case {**$NAME}:\n            pass",
    "def shadow(value):\n    match value:\n        case Point(x=$NAME):\n            pass",
    "def shadow():\n    del $NAME",
]
if hasattr(ast, "TypeVar"):
    BINDINGS += ["def shadow[$NAME]():\n    pass", "def shadow[**$NAME]():\n    pass",
                 "def shadow[*$NAME]():\n    pass", "type $NAME = int"]


@pytest.mark.parametrize("binding", BINDINGS)
@pytest.mark.parametrize("dependency", ["set", "A"])
def test_every_binding_construct_disqualifies_constructors_and_earlier_constants(binding, dependency):
    source = "EVENTS = []\nA = [1]\n" + binding.replace("$NAME", dependency) + "\n"
    source += ("X = set([1])\n" if dependency == "set" else "X = A\n") + HOOKS
    rejected_assignment(source)


@pytest.mark.parametrize("constructor", sorted(policy.CONSTRUCTORS))
def test_all_builtin_constructors_are_audited_even_when_binding_is_later(constructor):
    source = "X = " + constructor + "([])\ndef shadow(" + constructor + "):\n    return 1\n" + HOOKS
    rejected_assignment(source)


@pytest.mark.parametrize("binding", [
    "def shadow(re):\n    return re",
    "def shadow(arg=(re := EVENTS)):\n    return arg",
    "import re as re",
    "from math import pi as re",
    "from re import *",
    "from math import *",
    "def shadow():\n    re.compile = other",
    "def shadow():\n    re.compile: object = other",
    "def shadow():\n    re.compile += other",
    "def shadow():\n    del re.compile",
    "import re as alias\ndef shadow():\n    alias.compile = other",
])
def test_regex_module_and_compile_bindings_are_audited(binding):
    rejected_assignment("import re\nEVENTS = []\nX = re.compile('x')\n" + binding + "\n" + HOOKS)


@pytest.mark.parametrize("flag", sorted(policy.RE_FLAGS))
@pytest.mark.parametrize("binding", ["def shadow($FLAG):\n    return 1",
                                     "def shadow():\n    re.$FLAG = 0",
                                     "import re as alias\ndef shadow():\n    alias.$FLAG = 0"])
def test_used_flag_names_and_attributes_are_audited_in_every_scope(flag, binding):
    source = "import re\nX = re.compile('x', re." + flag + ")\n" + binding.replace("$FLAG", flag) + "\n" + HOOKS
    rejected_assignment(source)


@pytest.mark.parametrize("binding", [
    "def shadow():\n    alias.I: int = 0", "def shadow():\n    alias.I += 1",
    "def shadow():\n    del alias.I", "from re import I", "from math import pi as I",
    "def shadow(arg=(I := 0)):\n    return arg",
])
def test_flag_binding_forms_and_one_member_of_flag_union_are_audited(binding):
    source = "import re\nimport re as alias\nX = re.compile('x', re.M | re.I)\n" + binding + "\n" + HOOKS
    rejected_assignment(source)


@pytest.mark.parametrize("source", [
    "A = [1]\nB = A\nX = B\ndef shadow(A):\n    return 1\n",
    "A = [1]\nB = A\nX = B\ndef shadow(B):\n    return 1\n",
    "A = set([1])\nB = A\nX = B\ndef shadow(set):\n    return 1\n",
    "A = [1]\nX = A\nA = [2]\n",
    "A = [1]\nX = A\ndef shadow():\n    A[0] = 2\n",
    "A = set()\nX = A\ndef shadow(set):\n    return 1\n",
    "X = tuple([set()])\ndef shadow(set):\n    return 1\n",
    "X = [set()] + []\ndef shadow(set):\n    return 1\n",
])
def test_transitive_and_nested_literal_dependencies_are_audited(source):
    rejected_assignment(source + HOOKS)


@pytest.mark.parametrize("source", [
    "A = [1]\nB = A\nX = B\n",
    "A = set([1])\nB = A\nX = B\n",
    "set = [1]\nX = set\n",
    "X = tuple([set()])\n",
    "import re\nX = re.compile('x', re.I | re.M)\n",
    "import re\nimport re\nX = re.compile('x', re.I)\n",
    "import re\ndef shadow():\n    import re\nX = re.compile('x')\n",
    "import re\ndef shadow(unrelated):\n    return unrelated\nX = re.compile('x')\n",
    "import re\nI = 1\nX = re.compile('x', re.M)\n",
    "def shadow(set):\n    return set\nX = 'a b'.split()\n",
    "def shadow(set):\n    return set\nX = 1 + 2\n",
])
def test_unbound_dependencies_and_plain_re_import_exemption_still_pass(source):
    source += HOOKS
    assert not policy.check(source, version=V23)
    result = load(source)
    assert result["ok"] and result["loaded"] == ["review"] and not result["rejected"]


def test_review_example_rejects_x_and_retains_the_legacy_literal_verdict():
    source = "EVENTS = []\ndef shadow(x=(set := EVENTS.append)):\n    return x\nX = set([1])\n" + HOOKS
    rejected_assignment(source)
    assert [v.to_json() for v in policy.check(source)] == [
        {"rule": "module_level", "detail": "a constant must be a literal", "line": 4}]
    # Literal-only fallback is the existing ast.literal_eval verdict, including its set() spelling.
    literal = source.replace("X = set([1])", "X = set()")
    assert not policy.check(literal) and not policy.check(literal, version=V23)
    assert not policy.check("def shadow(set):\n    return set\nX = [1]\n", version=V23)


def test_policy_files_match_their_separately_pinned_hashes():
    assert hashlib.sha256(policy.POLICY_PATH.read_bytes()).hexdigest() == policy.policy_sha256()
    assert hashlib.sha256(policy.POLICY_PATH_V23.read_bytes()).hexdigest() == policy.policy_sha256(version=V23)
    assert "whole-module" in policy.POLICY_V23["constant_bindings"]
