"""Bounded multi-module Python execution; candidates never execute on the host.

Files remain separate Python modules with independent namespaces. A closed local
importer loads their original bytes inside the existing macOS OS sandbox. No
candidate file is written to disk, and no private expected outcome enters it.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any, Mapping

from skillopt.coevolution import executor as previous
from skillopt.validator_pilot import tasks as pilot

VERSION = "coevolution-v3-closed-module-executor-v1"
AVAILABLE_BUILTINS = previous.AVAILABLE_BUILTINS
MAX_ARTIFACT_CHARS = 180000


@dataclass(frozen=True)
class RepoTask:
    id: str
    split: str
    family: str
    cluster_id: str
    prompt: str
    files: dict[str, str]
    reference_files: dict[str, str]
    editable_paths: list[str]
    input_domain: dict[str, Any]
    public_cases: list[dict[str, Any]]
    private_cases: list[dict[str, Any]]
    metadata: dict[str, Any]
    entry_module: str = "api"
    entry_function: str = "solve"

    def to_dict(self) -> dict:
        return asdict(self)

    def public_task(self) -> dict:
        from copy import deepcopy

        return deepcopy(
            {
                key: getattr(self, key)
                for key in (
                    "id",
                    "prompt",
                    "files",
                    "editable_paths",
                    "input_domain",
                    "public_cases",
                    "entry_module",
                    "entry_function",
                )
            }
        )

    @classmethod
    def from_dict(cls, value: Mapping) -> "RepoTask":
        return cls(**{key: value[key] for key in cls.__dataclass_fields__ if key in value})


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _module_path(path: str) -> str:
    if not isinstance(path, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*\.py", path):
        raise ValueError("only declared flat canonical Python module paths are supported")
    return path[:-3]


def validate_files(task: RepoTask, files: Mapping[str, str]) -> None:
    if not isinstance(files, Mapping) or set(files) != set(task.files):
        raise ValueError("merged artifact must contain exactly the declared repository files")
    if not 2 <= len(files) <= 8 or sum(len(v) for v in files.values() if isinstance(v, str)) > MAX_ARTIFACT_CHARS:
        raise ValueError("repository size exceeds fixed limits")
    modules = {_module_path(path) for path in files}
    if task.entry_module not in modules or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", task.entry_function):
        raise ValueError("invalid trusted entrypoint")
    if modules & pilot.ALLOWED_IMPORTS:
        raise ValueError("local module shadows a restricted standard library module")
    for path, code in files.items():
        if not isinstance(code, str) or not code.strip() or len(code) > 60000:
            raise ValueError("each module must be nonempty and at most 60000 characters")
        tree = ast.parse(code, filename=path)
        nodes = list(ast.walk(tree))
        if len(nodes) > 12000:
            raise ValueError("module AST exceeds fixed limit")
        for node in nodes:
            if isinstance(node, ast.Import):
                if any(alias.name not in modules | pilot.ALLOWED_IMPORTS for alias in node.names):
                    raise ValueError("import is not a declared local or allowlisted library module")
            if isinstance(node, ast.ImportFrom):
                if (
                    node.level
                    or node.module not in modules | pilot.ALLOWED_IMPORTS
                    or any(a.name.startswith("_") or a.name == "*" for a in node.names)
                ):
                    raise ValueError("relative, wildcard, private or undeclared from-import")

        # Reuse every prior non-import AST restriction. Only the validation tree
        # has local imports replaced; the executed candidate source is untouched.
        class ValidationImports(ast.NodeTransformer):
            def visit_Import(self, node):
                kept = [a for a in node.names if a.name not in modules]
                return ast.copy_location(ast.Import(names=kept), node) if kept else ast.copy_location(ast.Pass(), node)

            def visit_ImportFrom(self, node):
                return ast.copy_location(ast.Pass(), node) if node.module in modules else node

        pilot.validate_code(ast.unparse(ast.fix_missing_locations(ValidationImports().visit(tree))))


def parse_patch(task: RepoTask, response: str | Mapping) -> dict[str, str]:
    """Strict bounded file replacement map; omitted files retain original bytes."""
    if isinstance(response, str):
        if len(response) > MAX_ARTIFACT_CHARS + 20000:
            raise ValueError("patch response too large")
        text = response.strip()
        if text.startswith("```"):
            match = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
            if not match or "```" in match.group(1):
                raise ValueError("only one complete JSON fence without commentary is permitted")
            text = match.group(1)
        response = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")),
        )
    if not isinstance(response, Mapping) or set(response) != {"files"} or not isinstance(response["files"], Mapping):
        raise ValueError('response must be exactly {"files": {"allowed.py": "complete source"}}')
    if not set(task.editable_paths) <= set(task.files):
        raise ValueError("trusted editable paths are not in repository")
    patch = response["files"]
    for path in patch:
        _module_path(path)
    if not set(patch) <= set(task.editable_paths):
        raise ValueError("patch changes an undeclared or protected path")
    files = {**task.files, **patch}
    validate_files(task, files)
    return files


# Use the reviewed original library proxies and builtin list, including divmod.
# The inherited sandbox profile and resource limits are unchanged. Source is
# pinned by previous._extend_runner; the unique loop anchor is checked here too.
if previous.CHILD_RUNNER.count("rows=[]\n") != 1:
    raise RuntimeError("audited child runner changed; review multi-module extension")
_PREFIX = previous.CHILD_RUNNER.split("rows=[]\n", 1)[0]
CHILD_RUNNER = (
    _PREFIX
    + r"""
def fingerprint(value):
    def typed(v):
        if isinstance(v,dict): return ('dict',tuple((typed(k),typed(x)) for k,x in v.items()))
        if isinstance(v,list): return ('list',tuple(typed(x) for x in v))
        if isinstance(v,tuple): return ('tuple',tuple(typed(x) for x in v))
        return (type(v).__name__,repr(v))
    return hashlib.sha256(repr(typed(value)).encode()).hexdigest()

def modules_for_case(files):
    sources={path[:-3]:(path,code) for path,code in files.items()}
    cache={}
    loading=set()
    def load(name):
        if name in loading: raise ImportError('circular local imports are not supported')
        if name in cache: return cache[name]
        if name not in sources: raise ImportError('unknown local module')
        loading.add(name)
        path,source=sources[name]
        module=types.ModuleType(name)
        local_builtins=dict(safe_builtins)
        def local_import(import_name,globals=None,locals=None,fromlist=(),level=0):
            if level: raise ImportError('relative import is not supported')
            if import_name in sources: return load(import_name)
            return safe_import(import_name,globals,locals,fromlist,level)
        local_builtins['__import__']=local_import
        module.__dict__.update({'__builtins__':local_builtins,'__name__':name})
        try:
            exec(compile(source,path,'exec'),module.__dict__,module.__dict__)
            cache[name]=module
            return module
        finally:
            loading.remove(name)
    return load

proxy_templates={name:dict(vars(module)) for name,module in proxies.items()}
rows=[]
for item in payload['inputs']:
    proxies={name:types.SimpleNamespace(**members) for name,members in proxy_templates.items()}
    et_proxy=proxies['xml.etree.ElementTree']
    data=copy.deepcopy(item)
    before=fingerprint(data)
    value=None
    exception=None
    message=None
    try:
        load=modules_for_case(payload['files'])
        module=load(payload['entry_module'])
        entry=getattr(module,payload['entry_function'])
        value=normalize(entry(data))
        json.dumps(value,allow_nan=False)
    except Exception as exc:
        value=None
        exception=type(exc).__name__
        message=str(exc)[:200]
    try:
        after=fingerprint(data)
    except Exception:
        after=None
    rows.append({'ok':True,'value':value,'exception':exception,'message':message,
                 'input_unchanged':before==after,'input_before_fingerprint':before,
                 'input_after_fingerprint':after})
encoded=json.dumps({'rows':rows},ensure_ascii=False,allow_nan=False)
if len(encoded)>250000: raise ValueError('output exceeds limit')
sys.stdout.write(encoded)
"""
)
RUNNER_SHA256 = hashlib.sha256(CHILD_RUNNER.encode()).hexdigest()
sandbox_probe = pilot.sandbox_probe


def run_payload(payload: Mapping) -> tuple[int, str, str]:
    import psutil

    proc = subprocess.Popen(
        pilot._command(CHILD_RUNNER),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/private/tmp",
        env={"PATH": "/usr/bin:/bin"},
        text=True,
    )
    start, first = time.monotonic(), json.dumps(payload, allow_nan=False)
    try:
        while True:
            try:
                out, err = proc.communicate(input=first, timeout=0.05)
                return proc.returncode, out, err
            except subprocess.TimeoutExpired:
                first = None
                if time.monotonic() - start > 12:
                    raise RuntimeError("candidate exceeded 12 second wall limit")
                try:
                    if psutil.Process(proc.pid).memory_info().rss > 384 * 1024 * 1024:
                        raise RuntimeError("candidate exceeded monitored RSS limit")
                except psutil.NoSuchProcess:
                    pass
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.communicate()


def execute_inputs(task: RepoTask, files: Mapping[str, str], inputs: list[dict]) -> list[dict]:
    """Concrete observations, not judgments; ordinary exceptions are observable."""
    try:
        validate_files(task, files)
        if not isinstance(inputs, list) or len(inputs) > 1024 or any(not isinstance(v, dict) for v in inputs):
            raise ValueError("execution requires at most 1024 JSON-object inputs")
        if len(json.dumps(inputs, allow_nan=False)) > 1000000:
            raise ValueError("input batch exceeds fixed bound")
    except (ValueError, TypeError, SyntaxError, RecursionError) as exc:
        return [
            {
                "ok": True,
                "value": None,
                "exception": "ArtifactContractError",
                "input_unchanged": False,
                "error_category": "candidate_contract_violation",
                "message": str(exc)[:200],
            }
            for _ in inputs
        ]
    if not inputs:
        return []
    try:
        returncode, output, _ = run_payload(
            {
                "files": dict(files),
                "inputs": inputs,
                "entry_module": task.entry_module,
                "entry_function": task.entry_function,
            }
        )
        if returncode:
            raise RuntimeError(f"sandbox child exited {returncode}")
        rows = json.loads(output)["rows"]
        if len(rows) != len(inputs) or any(not isinstance(row, dict) or row.get("ok") is not True for row in rows):
            raise RuntimeError("sandbox result schema or cardinality mismatch")
        return rows
    except (RuntimeError, OSError, subprocess.TimeoutExpired, ValueError, KeyError, TypeError) as exc:
        return [
            {
                "ok": False,
                "value": None,
                "exception": None,
                "input_unchanged": None,
                "error_category": "infrastructure_or_resource_failure",
                "message": str(exc)[:200],
            }
            for _ in inputs
        ]


def evaluate(task: RepoTask, response: str | Mapping, public_only: bool = False) -> dict:
    cases = task.public_cases + ([] if public_only else task.private_cases)
    result = {
        "correct": False,
        "hard": False,
        "execution_ok": False,
        "artifact_execution_ok": False,
        "public_observations": [],
        "private_diagnostics": [],
        "case_results": [],
        "dimensions": {
            name: {"passed": 0, "total": sum(c["dimension"] == name for c in cases)}
            for name in ("requested_behavior", "preserved_behavior")
        },
    }
    result["dimensions"]["preserved_behavior"]["total"] += len(cases)
    try:
        files = parse_patch(task, response)
    except (ValueError, TypeError, SyntaxError, RecursionError) as exc:
        result.update(
            execution_ok=True,
            public_pass=False,
            error_category="candidate_contract_violation",
            safety_error=str(exc)[:200],
        )
        for case in cases:
            for suffix, dimension in (("behavior", case["dimension"]), ("input_unchanged", "preserved_behavior")):
                result["case_results"].append(
                    {
                        "id": case["label"] + ":" + suffix,
                        "label": case["label"],
                        "dimension": dimension,
                        "passed": False,
                        "public": case["public"],
                    }
                )
        result.update(passed_tests=0, total_tests=sum(d["total"] for d in result["dimensions"].values()))
        return result
    result["files"] = files
    rows = execute_inputs(task, files, [case["input"] for case in cases])
    if any(row["ok"] is not True for row in rows):
        result.update(hard=None, error_category="infrastructure_or_resource_failure")
        return result
    result["execution_ok"] = True
    result["artifact_execution_ok"] = all(
        row["exception"] is None or c["exception"] is not None for c, row in zip(cases, rows)
    )
    for case, row in zip(cases, rows):
        passed = (
            row["exception"] == case["exception"]
            if case["exception"]
            else row["exception"] is None and pilot._same(row["value"], case["expected"])
        )
        preserved = row["input_unchanged"] is True
        result["dimensions"][case["dimension"]]["passed"] += int(passed)
        result["dimensions"]["preserved_behavior"]["passed"] += int(preserved)
        observation = {
            "label": case["label"],
            "input": case["input"],
            "passed": bool(passed and preserved),
            "actual": row["value"],
            "exception": row["exception"],
            "message": row.get("message"),
            "input_unchanged": preserved,
            "input_before_fingerprint": row.get("input_before_fingerprint"),
            "input_after_fingerprint": row.get("input_after_fingerprint"),
        }
        for suffix, dimension, flag in (
            ("behavior", case["dimension"], bool(passed)),
            ("input_unchanged", "preserved_behavior", preserved),
        ):
            result["case_results"].append(
                {
                    "id": case["label"] + ":" + suffix,
                    "label": case["label"],
                    "dimension": dimension,
                    "passed": flag,
                    "public": case["public"],
                }
            )
        if case["public"]:
            result["public_observations"].append(observation)
        elif not passed or not preserved:
            result["private_diagnostics"].append(
                {**observation, "expected": case["expected"], "expected_exception": case["exception"]}
            )
    result["correct"] = result["hard"] = all(d["passed"] == d["total"] for d in result["dimensions"].values())
    result["public_pass"] = all(row["passed"] for row in result["public_observations"])
    result["passed_tests"] = sum(d["passed"] for d in result["dimensions"].values())
    result["total_tests"] = sum(d["total"] for d in result["dimensions"].values())
    return result


def native_evaluation(task: RepoTask, response: str, target_ok: bool) -> dict:
    if not target_ok:
        return {
            "evaluation": {
                "hard": None,
                "execution_ok": False,
                "error_category": "target_unavailable",
                "public_observations": [],
                "case_results": [],
            },
            "files": None,
            "format_ok": False,
            "guard_reason": "target_unavailable",
            "extraction": None,
        }
    result = evaluate(task, response)
    files = result.get("files")
    guard = (
        "file_patch_contract_violation"
        if files is None
        else ("visible_test_failure" if result["execution_ok"] and result.get("public_pass") is False else None)
    )
    return {
        "evaluation": result,
        "files": files,
        "format_ok": files is not None,
        "guard_reason": guard,
        "extraction": {
            "ok": files is not None,
            "mode": "strict_file_map",
            "raw_sha256": hashlib.sha256(response.encode()).hexdigest(),
        },
    }
