"""Small immutable evaluation plans and checkpoint registration.

Only explicit public task projections leave this module. Source provenance is
an operator declaration, not proof of uncontaminated pretraining or Skill
authorization. Frozen checkpoints do not acquire deployment permission here.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from skillopt.coevolution_v5.core import seal, verify
from skillopt.validator_pilot.api import digest, write_immutable_json

from . import VERSION

BENCHMARKS = ("bigcodebench", "spreadsheetbench", "searchqa", "korbench", "alfworld")
LONG_RESPONSE_VERSION = "continual-eval-v2"


def require(value, message):
    if not value:
        raise ValueError(message)


def safe_path(value):
    path = Path(value).absolute()
    require(".." not in path.parts, "Parent traversal is not supported")
    require(not any(p.is_symlink() for p in (path, *path.parents)), "Symlink paths are not supported")
    return path


def read_json(path, *, sealed=False):
    path = safe_path(path)
    require(path.stat().st_size <= 64_000_000, "Oversized JSON input")

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result

    def invalid(_):
        raise ValueError("Nonfinite JSON")

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs, parse_constant=invalid)
    return verify(value) if sealed else value


def write_json(path, value):
    write_immutable_json(safe_path(path), value)


def identifier(value):
    require(type(value) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value),
            "Invalid method/history identifier")
    return value


@contextmanager
def output_lock(root):
    """One local writer; a process crash releases the lock, not its intents."""
    import fcntl

    root = safe_path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = safe_path(root / ".writer.lock")
    with path.open("a", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("Another process owns this evaluation directory") from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def source_identity():
    # Freeze the new harness plus reused scorers/API, not unrelated experiments.
    package = Path(__file__).parent
    sources = list(package.glob("*.py"))
    sources += [package.parent / "envs/searchqa/evaluator.py",
                package.parent / "envs/spreadsheetbench/evaluator.py",
                package.parent / "validator_pilot/api.py",
                package.parent / "skill_validation/single_round.py",
                package.parent / "skill_validation/sandbox.py"]
    sources += list((package.parent / "envs/alfworld/vendor").glob("*.py"))
    sources += list((package.parent / "envs/alfworld/vendor").glob("*.yaml"))
    return {str(p.relative_to(package.parent)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(sources)}


def runtime_identity():
    packages = {}
    for name in ("alfworld", "textworld", "gymnasium", "gym", "numpy", "openpyxl", "httpx", "PyYAML"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {"python": platform.python_version(), "system": platform.system(), "packages": packages}


def validate_config(config):
    fields = {"version", "order", "panels", "partition", "methods", "histories", "repeats",
              "model", "runtime", "project_disjoint", "exposure_manifest"}
    require(type(config) is dict and set(config) == fields, "Unexpected evaluation configuration fields")
    require(config["version"] in {VERSION, LONG_RESPONSE_VERSION}, "Unsupported protocol version")
    require(type(config["order"]) is list and len(config["order"]) == 5
            and set(config["order"]) == set(BENCHMARKS), "Exactly five unique benchmarks required")
    require(type(config["panels"]) is dict and set(config["panels"]) == set(BENCHMARKS),
            "Declare all five panel paths (null allowed for readiness only)")
    require(all(v is None or (type(v) is str and v.strip()) for v in config["panels"].values()),
            "Invalid panel path")
    require(config["partition"] in {"development", "final"}, "Evaluation partition must be development or final")
    for key in ("methods", "histories"):
        require(type(config[key]) is list and config[key] and len(config[key]) == len(set(config[key])),
                "Nonempty unique method/history roster required")
        for value in config[key]:
            identifier(value)
    require("no_skill" in config["methods"], "An explicit no_skill baseline is required")
    require(type(config["repeats"]) is int and 1 <= config["repeats"] <= 20, "Invalid repeats")
    require(type(config["project_disjoint"]) is bool, "Explicit project isolation policy required")
    require(config["exposure_manifest"] is None or type(config["exposure_manifest"]) is str,
            "Invalid exposure manifest path")
    m = config["model"]
    model_fields = {"provider", "name", "max_tokens", "reasoning_effort"}
    long_response = config["version"] == LONG_RESPONSE_VERSION
    if long_response:
        model_fields.add("transport")
    require(type(m) is dict and model_fields <= set(m)
            and set(m) <= model_fields | {"proxy"},
            "Model configuration contains unsupported fields; never include credentials")
    require(m["provider"] in {"bigmodel", "pjlab", "fixture"}, "Unsupported model provider")
    require(m["name"] == ("fixture" if m["provider"] == "fixture" else "glm-5.3"), "Unsupported model")
    if long_response:
        require(m["provider"] in {"bigmodel", "fixture"}, "Long-response evaluation requires BigModel or fixture")
        transport = m["transport"]
        require(type(transport) is dict and set(transport) == {
            "stream", "read_timeout_seconds", "stream_wall_seconds", "initial_health_policy"},
            "Invalid long-response transport fields")
        require(transport["stream"] is True
                and type(transport["read_timeout_seconds"]) is int and transport["read_timeout_seconds"] == 300
                and type(transport["stream_wall_seconds"]) is int and transport["stream_wall_seconds"] == 1800
                and transport["initial_health_policy"] == "completed_response_v1",
                "The v2 transport is fixed to stream/read300/wall1800/completed_response_v1")
    require(type(m["max_tokens"]) is int and 1 <= m["max_tokens"] <= (65536 if long_response else 16000),
            "Invalid output budget")
    require(m["reasoning_effort"] in {"low", "high", "max"}, "Invalid reasoning effort")
    if "proxy" in m:
        from urllib.parse import urlsplit

        proxy = m["proxy"]
        require(type(proxy) is str and proxy == proxy.strip(), "Invalid explicit model proxy")
        parsed = urlsplit(proxy)
        from skillopt.validator_pilot.api import PJLAB_HTTP_PROXY_HOST

        require(m["provider"] == "bigmodel" and parsed.scheme == "http"
                and (parsed.hostname in {"127.0.0.1", "::1"}
                     or (parsed.hostname == PJLAB_HTTP_PROXY_HOST and parsed.port == 3128))
                and parsed.port is not None
                and 1 <= parsed.port <= 65535 and parsed.path in {"", "/"}
                and parsed.username is None and parsed.password is None
                and not parsed.query and not parsed.fragment,
                "Model proxy must be a credential-free local HTTP endpoint or the approved PJLAB gateway for BigModel")
    require(type(config["runtime"]) is dict and set(config["runtime"]) <= set(BENCHMARKS),
            "Unknown runtime benchmark")
    # Runtime is operator-controlled, never generated by an LLM. Credentials do
    # not belong in a frozen/publishable configuration.
    def no_credentials(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                require(not re.search(r"api.?key|password|secret|authorization|credential", key, re.I),
                        "Credentials are forbidden in evaluation manifests")
                no_credentials(value)
        elif isinstance(obj, list):
            for value in obj:
                no_credentials(value)
    no_credentials(config["runtime"])
    sheet_runtime = config["runtime"].get("spreadsheetbench", {})
    require(type(sheet_runtime) is dict, "Spreadsheet runtime must be a mapping")
    require("_score_context" not in sheet_runtime, "Score evidence context is host-owned, not configuration")
    if sheet_runtime.get("spreadsheet_scorer") == "qualified_lo_recalc_v5_v1":
        from .sheet_recalc_adapter import qualified_engine

        qualified_engine(sheet_runtime)
    elif sheet_runtime.get("spreadsheet_scorer") == "qualified_lo_recalc_v7_v1":
        from .sheet_numeric_adapter import qualified_engine

        qualified_engine(sheet_runtime)
    return deepcopy(config)


def _exposures(path):
    if path is None:
        return None
    value = read_json(path)
    require(type(value) is dict and set(value) == {"version", "records"}
            and value["version"] == "continual-exposure-v1", "Invalid exposure registry")
    require(type(value["records"]) is list, "Exposure records required")
    for row in value["records"]:
        require(set(row) == {"benchmark", "task_id", "family_id", "purpose"}
                and row["benchmark"] in BENCHMARKS, "Invalid exposure record")
        require(all(type(row[k]) is str and row[k] for k in ("task_id", "family_id", "purpose")),
                "Exposure identity is required")
    return value


def build_plan(config):
    from .datasets import load_panel, panel_hash

    config = validate_config(config)
    # Resolve once, relative to the launch directory, so resuming a frozen run
    # from another working directory cannot silently select another panel.
    config["panels"] = {k: str(safe_path(v)) if v is not None else None
                        for k, v in config["panels"].items()}
    if config["exposure_manifest"] is not None:
        config["exposure_manifest"] = str(safe_path(config["exposure_manifest"]))
    for runtime in config["runtime"].values():
        require(type(runtime) is dict, "Runtime settings must be a mapping")
        for key in ("kor_repo", "alfworld_data"):
            if key in runtime:
                runtime[key] = str(safe_path(runtime[key]))
    exposures = _exposures(config["exposure_manifest"])
    task_roster, panels, partitions, projects = [], {}, {}, {}
    for benchmark in config["order"]:
        path = config["panels"][benchmark]
        if path is None or not safe_path(path).is_file():
            panels[benchmark] = {"status": "missing", "path": path, "panel_hash": None}
            continue
        panel = load_panel(path)
        require(panel["benchmark"] == benchmark, "Panel benchmark mismatch")
        if config["model"]["provider"] != "fixture":
            require(panel["provenance"] == "natural", "Fixture tasks cannot enter a real baseline")
        panels[benchmark] = {"status": "present", "path": str(safe_path(path)),
                             "panel_hash": panel_hash(panel), "provenance": panel["provenance"],
                             "dataset_revision": panel["dataset_revision"]}
        for task in panel["tasks"]:
            for kind in ("task_id", "family_id"):
                key = (benchmark, kind, task[kind])
                require(partitions.setdefault(key, task["partition"]) == task["partition"],
                        "Original task/family crosses data partitions")
            if config["project_disjoint"]:
                require(task["project_id"], "Project-disjoint plans require project IDs")
                key = (benchmark, task["project_id"])
                require(projects.setdefault(key, task["partition"]) == task["partition"],
                        "Project crosses data partitions")
            if task["partition"] != config["partition"]:
                continue
            if exposures is not None and config["partition"] == "final":
                require(not any(r["benchmark"] == benchmark and
                                (r["task_id"] == task["task_id"] or r["family_id"] == task["family_id"])
                                for r in exposures["records"]), "Historically exposed task/family cannot enter final")
            task_roster.append({"benchmark": benchmark, **{k: task[k] for k in
                ("task_id", "family_id", "project_id", "partition")}, "task_hash": digest(task)})
    require(len({(r["benchmark"], r["task_id"]) for r in task_roster}) == len(task_roster), "Duplicate evaluation task")
    eligible = (all(p["status"] == "present" for p in panels.values())
                and all(any(t["benchmark"] == b for t in task_roster) for b in BENCHMARKS)
                and config["partition"] == "final" and exposures is not None
                and config["model"]["provider"] != "fixture")
    return seal({"version": config["version"], "config": config, "order": config["order"], "repeats": config["repeats"],
        "tasks": task_roster, "panels": panels, "source_identity": source_identity(), "host_runtime": runtime_identity(),
        "exposure_hash": digest(exposures) if exposures is not None else None,
        "protocol_complete": eligible, "evidence_kind": "engineering_fixture" if config["model"]["provider"] == "fixture"
            else "frozen_natural_evaluation" if eligible else "partial_or_development_evaluation",
        "score_feedback_allowed": False, "evolution_enabled": False, "deployment_authorized": False,
        "checkpoints": [{"method": method, "history": history, "stage": stage, "checkpoint_hash": None}
                        for method in config["methods"] for history in config["histories"] for stage in range(6)]})


def freeze_plan(config, root):
    plan = build_plan(config)
    root = safe_path(root)
    with output_lock(root):
        write_json(root / "plan.json", plan)
        for slot in plan["checkpoints"]:
            if slot["stage"] == 0:
                register_checkpoint(root, slot["method"], slot["history"], 0, "", provenance="common_empty_initialization",
                                    _plan=plan)
    return plan


def load_plan(root):
    plan = read_json(safe_path(root) / "plan.json", sealed=True)
    require(plan == build_plan(plan["config"]), "Frozen sources, assets, data or configuration changed; use a new run")
    return plan


def checkpoint_path(root, method, history, stage):
    identifier(method)
    identifier(history)
    require(type(stage) is int and 0 <= stage <= 5, "Stage must be 0..5")
    return safe_path(root) / "checkpoints" / method / history / f"s{stage}.json"


def register_checkpoint(root, method, history, stage, skill_text, *, provenance, _plan=None):
    plan = _plan or load_plan(root)
    path = checkpoint_path(root, method, history, stage)
    require(any(s["method"] == method and s["history"] == history and s["stage"] == stage
                for s in plan["checkpoints"]), "Unregistered checkpoint slot")
    require(type(skill_text) is str and len(skill_text.encode()) <= 6000, "Frozen Skill exceeds 6000-byte common budget")
    require(type(provenance) is str and 0 < len(provenance) <= 2000, "Checkpoint provenance declaration required")
    require(stage > 0 or skill_text == "", "Stage zero is the common empty initialization")
    require(method != "no_skill" or skill_text == "", "No-Skill cannot contain advice")
    parent = None
    if stage:
        parent = load_checkpoint(root, method, history, stage - 1, plan)["record_hash"]
    checkpoint = seal({"version": plan["version"] + "-checkpoint", "plan_hash": plan["record_hash"],
        "method": method, "history": history, "stage": stage, "skill_text": skill_text,
        "skill_hash": hashlib.sha256(skill_text.encode()).hexdigest(), "parent_hash": parent,
        "seen_benchmarks": plan["order"][:stage], "provenance": provenance,
        "exposure": "raw_frozen_skill", "provenance_independently_verified": False,
        "deployment_authorized": False})
    write_json(path, checkpoint)
    return checkpoint


def load_checkpoint(root, method, history, stage, plan):
    value = read_json(checkpoint_path(root, method, history, stage), sealed=True)
    require(value["version"] == plan["version"] + "-checkpoint", "Checkpoint protocol version mismatch")
    require(value["plan_hash"] == plan["record_hash"] and value["method"] == method
            and value["history"] == history and value["stage"] == stage, "Checkpoint binding mismatch")
    require(hashlib.sha256(value["skill_text"].encode()).hexdigest() == value["skill_hash"], "Skill hash mismatch")
    require(value["seen_benchmarks"] == plan["order"][:stage], "Invalid seen-domain declaration")
    require(stage > 0 or value["skill_text"] == "", "Initial checkpoint must be empty")
    require(method != "no_skill" or value["skill_text"] == "", "No-Skill checkpoint contains advice")
    if stage:
        parent = load_checkpoint(root, method, history, stage - 1, plan)
        require(value["parent_hash"] == parent["record_hash"], "Checkpoint ancestry changed")
    else:
        require(value["parent_hash"] is None, "Initial checkpoint cannot have a parent")
    return value


def panel_tasks(plan, benchmark):
    from .datasets import load_panel, panel_hash

    require(benchmark in plan["order"], "Unknown benchmark")
    entry = plan["panels"][benchmark]
    require(entry["status"] == "present", "Benchmark panel is missing")
    panel = load_panel(entry["path"])
    require(panel_hash(panel) == entry["panel_hash"], "Panel/asset changed during evaluation")
    return [t for t in panel["tasks"] if t["partition"] == plan["config"]["partition"]]


def public_view(task):
    # Whitelist, not deletion from a dictionary that may acquire new fields.
    return deepcopy(task["public"])
