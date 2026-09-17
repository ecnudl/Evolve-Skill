"""Frozen-task construction for authored multi-file Coding migration projects.

These are bounded original diagnostic projects, not independent public benchmark
problems and not a cross-domain claim. Two requests share every project cluster.
"""

from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from functools import lru_cache

from skillopt.coevolution_v3.executor import AVAILABLE_BUILTINS, RepoTask

VERSION = "coevolution-v3-authored-repositories-v1"
MODES = ("local-update", "full-policy-replacement")
PHASES = ("learn0", "learn0", "gate0", "learn1", "learn1", "gate1") + ("holdout",) * 6
RUNTIME = (
    'Deliver only a JSON object {"files": {"allowed.py": "complete Python source"}}; '
    "one surrounding json code fence is also accepted, without commentary or other blocks. "
    "Return only files you change; omitted files keep their original bytes. Do not add, delete, "
    "or rename files. Preserve the interfaces and old-call behavior explicitly designated stable "
    "in the task contract; internal helpers are not automatically frozen. All caller input objects, nested types and "
    "dictionary insertion order must remain unchanged, also on an exception. Validator inputs are "
    "bounded JSON objects: at most 6000 serialized characters, 256 nodes including keys, depth 8, "
    "64 items per container, 2048 characters per string and absolute numeric magnitude 1000000, "
    "in addition to the task schema. api.solve(data) is "
    "the evaluation entrypoint; the visible input schema also permits novel validator inputs. "
    "Actual separate Python modules run under an OS filesystem/network/process sandbox. Local "
    "imports are absolute declared module names only: no relative, circular, wildcard, dynamic "
    "or underscore-prefixed from-imports. Each test starts a fresh module cache; imports within "
    "one test share their module object. No file IO, introspection, eval/exec/compile, dynamic "
    "attribute helpers, asynchronous code, decorators, inheritance/metaclasses or special methods "
    "except __init__. Modules are at most 60000 characters each and 180000 together. "
    "CPU 5 s, wall 12 s per batch, monitored RSS 384 MiB, file creation and network forbidden. "
    "Ordinary available builtins (print is a no-op): " + ", ".join(AVAILABLE_BUILTINS) + ". "
    "Restricted standard library APIs: copy.copy/deepcopy; json.loads/dumps/JSONDecodeError; "
    "decimal.Decimal/InvalidOperation/ROUND_HALF_EVEN/ROUND_HALF_UP/ROUND_DOWN/ROUND_UP; "
    "math.sqrt/isfinite/isclose/floor/ceil/fabs/fsum; re.match/fullmatch/search/sub/split/findall/compile "
    "and IGNORECASE/MULTILINE/DOTALL; hashlib.sha256; time.time (fixed clock); "
    "csv.reader/writer/DictReader/DictWriter; io.StringIO; sqlite3.connect (memory only)/Row/Error/IntegrityError; "
    "xml.etree.ElementTree.fromstring/tostring/Element/SubElement/ParseError. No other APIs are promised."
)


def _schema_valid(value, schema) -> bool:
    """Small documented JSON-schema subset, exact integer/bool discrimination."""
    if schema is True:
        return True
    if schema is False or not isinstance(schema, dict):
        return False
    if "anyOf" in schema and not any(_schema_valid(value, child) for child in schema["anyOf"]):
        return False
    if "oneOf" in schema and sum(_schema_valid(value, child) for child in schema["oneOf"]) != 1:
        return False
    if "allOf" in schema and not all(_schema_valid(value, child) for child in schema["allOf"]):
        return False
    if "enum" in schema and not any(type(value) is type(item) and value == item for item in schema["enum"]):
        return False
    if "const" in schema and not (type(value) is type(schema["const"]) and value == schema["const"]):
        return False
    kinds = {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }
    expected = schema.get("type")
    if expected and not any(
        kinds.get(kind, False) for kind in (expected if isinstance(expected, list) else [expected])
    ):
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if (
            not math.isfinite(value)
            or value < schema.get("minimum", -1000000)
            or value > schema.get("maximum", 1000000)
        ):
            return False
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            return False
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            return False
    if isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", 1000):
            return False
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            return False
    if isinstance(value, list):
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", 64):
            return False
        if schema.get("uniqueItems") and len({json.dumps(x, sort_keys=True) for x in value}) != len(value):
            return False
        if any(not _schema_valid(item, schema.get("items", {})) for item in value):
            return False
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value) or not set(schema.get("required", [])) <= set(value):
            return False
        if not schema.get("minProperties", 0) <= len(value) <= schema.get("maxProperties", 64):
            return False
        for key, item in value.items():
            child = schema.get("properties", {}).get(key, schema.get("additionalProperties", {}))
            if not _schema_valid(item, child):
                return False
    return True


@lru_cache(maxsize=1)
def _projects():
    from skillopt.coevolution_v3.tasks_development import build_projects as development
    from skillopt.coevolution_v3.tasks_holdout import build_projects as holdout

    projects = development() + holdout()
    if len(projects) != 12 or len({p["slug"] for p in projects}) != 12:
        raise ValueError("exactly twelve distinct authored project clusters are required")
    return projects


def _task_id(project, mode):
    return "repo-v3-" + project["slug"] + "-" + mode


def input_valid(task_id: str, value) -> bool:
    try:
        if isinstance(value, str):
            from skillopt.coevolution_v3.executor import _unique_object

            value = json.loads(value, object_pairs_hook=_unique_object)
        project = next(p for p in _projects() if task_id in {_task_id(p, mode) for mode in MODES})
        if not isinstance(value, dict) or len(json.dumps(value, allow_nan=False)) > 6000:
            return False
        nodes = 0

        def visit(item, depth=0):
            nonlocal nodes
            nodes += 1
            if nodes > 256 or depth > 8:
                raise ValueError("input exceeds fixed bound")
            if isinstance(item, dict):
                if len(item) > 64 or any(not isinstance(key, str) for key in item):
                    raise ValueError("input object exceeds JSON contract")
                for key, child in item.items():
                    visit(key, depth + 1)
                    visit(child, depth + 1)
            elif isinstance(item, list):
                if len(item) > 64:
                    raise ValueError("input array exceeds global bound")
                for child in item:
                    visit(child, depth + 1)
            elif isinstance(item, str):
                if len(item) > 2048:
                    raise ValueError("input string exceeds global bound")
            elif item is None or isinstance(item, bool):
                pass
            elif isinstance(item, (int, float)):
                if not math.isfinite(item) or abs(item) > 1000000:
                    raise ValueError("input number exceeds global bound")
            else:
                raise ValueError("input contains non-JSON types")

        visit(value)
        if not _schema_valid(value, project["input_domain"]):
            return False
        return project.get("input_validator", lambda _: True)(deepcopy(value)) is True
    except (TypeError, ValueError, KeyError, StopIteration, OverflowError, RecursionError):
        return False


@lru_cache(maxsize=1)
def _build():
    bundles = []
    for index, project in enumerate(_projects()):
        phase = PHASES[index]
        for mode in MODES:
            specification = project["modes"][mode]
            if len(specification["expected"]) != len(project["inputs"]):
                raise ValueError("independent expected outcomes do not match input library")
            cases = []
            for case_index, (value, expected) in enumerate(zip(project["inputs"], specification["expected"])):
                exception = None
                if isinstance(expected, dict) and set(expected) == {"__expected_exception__"}:
                    exception, expected = expected["__expected_exception__"], None
                cases.append(
                    {
                        "label": project["slug"] + "-case-" + str(case_index),
                        "input": deepcopy(value),
                        "expected": deepcopy(expected),
                        "exception": exception,
                        "dimension": "preserved_behavior"
                        if case_index in project["preserved_indices"]
                        else "requested_behavior",
                        "public": case_index in project["public_indices"],
                    }
                )
            controls = {
                kind: deepcopy(specification[key])
                for kind, key in (
                    ("reference", "reference_files"),
                    ("alternative", "alternative_files"),
                    ("semantic_mutant", "semantic_mutant_files"),
                    ("preservation_mutant", "preservation_mutant_files"),
                )
            }
            controls["starter"] = deepcopy(project["files"])
            metadata = {
                "version": VERSION,
                "project": project["slug"],
                "domain": "coding",
                "mode": mode,
                "authorship": "original diagnostic miniature repository, not a released benchmark",
                "independence": "two request modes share this project cluster; all tasks remain Coding",
                "oracle": "independently specified expected cases, not generated by executing reference source",
                "input_support": "bounded public schema, fixed independent regression cases; not exhaustive proof",
                "controls": controls,
            }
            task = RepoTask(
                _task_id(project, mode),
                "holdout" if phase == "holdout" else "dev",
                project["slug"],
                "repo-v3-" + project["slug"],
                specification["contract"] + "\n\n" + RUNTIME,
                deepcopy(project["files"]),
                deepcopy(specification["reference_files"]),
                list(project["editable_paths"]),
                deepcopy(project["input_domain"]),
                [c for c in cases if c["public"]],
                [c for c in cases if not c["public"]],
                metadata,
            )
            bundles.append(
                {
                    "task": task,
                    "phase": phase,
                    "context": project["context"],
                    "mode": mode,
                    "mechanism": "constraint_preservation",
                }
            )
    return bundles


def build_tasks() -> list[dict]:
    return deepcopy(_build())


def _task(value) -> RepoTask:
    if isinstance(value, str):
        return next(bundle["task"] for bundle in _build() if bundle["task"].id == value)
    return value["task"] if isinstance(value, dict) else value


def public_task(value) -> dict:
    task = _task(value)
    return task.public_task()


def controlled_fixtures(value) -> list[dict]:
    task = _task(value)
    return [
        {
            "kind": kind,
            "files": deepcopy(task.metadata["controls"][kind]),
            "response": json.dumps({"files": task.metadata["controls"][kind]}, ensure_ascii=False),
        }
        for kind in ("reference", "alternative", "starter", "semantic_mutant", "preservation_mutant")
    ]
