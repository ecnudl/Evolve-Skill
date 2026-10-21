"""The launch manifest (registration §0, §14 step 6) and the chain process's ``Setting`` built from it.

The manifest is one sealed JSON file; its hash is the run id written into every record. Its code map pins every file
under skillopt/ and scripts/ (``pin_code``; not only Python: the frozen learners read prompt files, the native runtime
has its Dockerfiles): the run executes from a checkout nobody edits while it runs. A chain process checks, when it
starts and before every stage, that the map holds every repository file the process has loaded (the coevo5 package, the
command line, the frozen modules they import) and that every pinned file still has its pinned hash, and that it runs on
the manifest's Python and openpyxl (the workbook structure checks, §0), and refuses to run otherwise; the research
archive's index (which holds every archived document's hash) and its record of addresses are bound by their hashes. The
``baseline`` block names the frozen learners' model, its frozen service, the credential repository and the pinned GEPA
checkout (§11); ``provenance`` names the records the other fields were taken from (the texts' generations, the
baselines' protocol and their settings compared with the solver's, the tolerance rule, the qualification's counts, the
smoke, the host's Python and openpyxl) and the GLM-5.3 tokens spent before the run, which the run's overall cap leaves
out (§13.3). This module reads a manifest;
``prelaunch.generate`` writes one.
"""
from __future__ import annotations

import hashlib
import sys
import threading
from pathlib import Path

from skillopt.continual_eval.core import read_json, require, safe_path

from . import baseline, data, qualify, research, texts
from .budget import Budget
from .calls import Slots
from .examiner import GENERAL, validate_rubric
from .protocol import DEEPSEEK_ROUTE, ORDER, OVERALL_CEILING, SLOTS, VERSION
from .units import Setting

REPO = Path(__file__).resolve().parents[2]
FIELDS = {"version", "root", "data", "sheet_qualification", "regression", "tolerance", "cards", "instructions",
          "rubrics", "runtime", "clients", "research", "baseline", "workers", "code", "provenance", "record_hash"}
CODE_ROOTS = ("skillopt", "scripts")
COMMAND = "scripts/run_coevo5.py"


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin_code():
    """The code map of a new manifest: every file under skillopt/ and scripts/ with its SHA-256 (bytecode caches
    excepted)."""
    return {path.relative_to(REPO).as_posix(): _sha(path) for root in CODE_ROOTS
            for path in sorted((REPO / root).rglob("*")) if path.is_file() and "__pycache__" not in path.parts}


def loaded_code():
    """The files a manifest must pin in this process: the coevo5 package, its command line, and every repository
    module under skillopt/ or scripts/ the process has loaded."""
    names = {path.relative_to(REPO).as_posix() for path in (REPO / "skillopt" / "coevo5").glob("*.py")} | {COMMAND}
    for module in list(sys.modules.values()):
        found = getattr(module, "__file__", None)
        path = Path(found).resolve() if isinstance(found, str) else None
        if path is not None and path.suffix == ".py" and path.is_relative_to(REPO) \
                and path.relative_to(REPO).parts[0] in CODE_ROOTS:
            names.add(path.relative_to(REPO).as_posix())
    return names


def environment():
    """The interpreter and the workbook library this process runs with (§0: frozen with the manifest)."""
    import openpyxl

    return {"python": sys.version.split()[0], "openpyxl": openpyxl.__version__}


def verify_code(manifest):
    """The code map holds every file this process has loaded, every pinned file still has its pinned hash, and the
    process runs on the manifest's Python and openpyxl (§0); raises otherwise: the run is refused."""
    found = environment()
    require(found == {key: manifest.get("provenance", {}).get(key) for key in found},
            "The interpreter or openpyxl differs from the launch manifest: %s" % found)
    missing = sorted(loaded_code() - set(manifest["code"]))
    require(not missing, "Files missing from the launch manifest: %s" % missing[:5])
    changed = [name for name, sha in sorted(manifest["code"].items())
               if not (REPO / name).is_file() or _sha(REPO / name) != sha]
    require(not changed, "Files differ from the launch manifest: %s" % changed[:5])


def client_config(repo, proxy, *, deepseek_env, router_env=None):
    """The clients of a smoke or a launch (zero calls; no credential file is read here): the GLM-5.3 credential
    repository, the gateway, and (v3 §9) the deepseek solver's route with its credential file; v1-v2's free-router env
    only when given."""
    value = {"repo": str(safe_path(repo)), "proxy": proxy, "deepseek_route": DEEPSEEK_ROUTE,
             "deepseek_env": str(safe_path(deepseek_env))}
    if router_env is not None:
        value["router_env"] = str(safe_path(router_env))
    return value


def _clients(config):
    from scripts.weak_solver_probe import GATEWAY, Client

    require(config["proxy"] in (None, GATEWAY), "Only the approved gateway")
    route = config.get("deepseek_route")
    require(route in (None, DEEPSEEK_ROUTE) and (route is None) == ("deepseek_env" not in config),
            "v3 §9: the deepseek solver's registered route, with its credential file")
    cache, lock = {}, threading.Lock()

    def make(model, max_tokens, read_timeout):
        with lock:
            key = (model, max_tokens, read_timeout)
            if key not in cache:
                routed = ({"route": route, "route_env": config["deepseek_env"]}
                          if route is not None and model == "deepseek-v4-flash" else {})
                cache[key] = Client(config["repo"], model, proxy=config["proxy"], max_tokens=max_tokens,
                                    router_env=config.get("router_env"), read_timeout=read_timeout, **routed)
            return cache[key]
    return make


def load(path, *, verify=True):
    """(manifest, Setting) of a launch manifest."""
    manifest = read_json(path, sealed=True)
    require(set(manifest) == FIELDS and manifest["version"] == VERSION + "-manifest", "Not a coevo5 manifest")
    if verify:
        verify_code(manifest)
    root = safe_path(manifest["root"])
    shared = root / "shared"
    pinned = manifest["data"]
    pools = {b: data.pool(pinned, b) for b in ORDER}
    sheet = qualify.load(manifest["sheet_qualification"]["path"])
    require(sheet["record_hash"] == manifest["sheet_qualification"]["record_hash"] and sheet["side"] == "train",
            "The training-side SpreadsheetBench qualification differs from the manifest")
    pools["spreadsheetbench"] = data.qualified(pools["spreadsheetbench"], sheet)
    rubrics = {b: validate_rubric(manifest["rubrics"][b], b) for b in (*ORDER, GENERAL)}
    require(set(manifest["research"]) == {"archive", "index_sha256", "sources_sha256", "proxy"},
            "The manifest binds the archive")
    archive = research.Archive(manifest["research"]["archive"])
    require(archive.index_sha256 == manifest["research"]["index_sha256"]
            and data.sha(archive.root / "sources.json") == manifest["research"]["sources_sha256"],
            "The research archive differs from the launch manifest")

    require(set(manifest["baseline"]) == set(baseline.CONFIG), "The manifest names the baselines' learning setup")
    prior = manifest["provenance"]["prior_glm_tokens"]["total"]
    require(type(prior) is int and 0 <= prior < OVERALL_CEILING, "The GLM-5.3 tokens spent before the run")

    def sources(store):
        return research.Sources(research.Wikipedia(proxy=manifest["research"]["proxy"]), archive, store)

    setting = Setting(
        run=manifest["record_hash"], root=root, shared=shared, pools=pools, regression=manifest["regression"],
        tolerance=manifest["tolerance"], cards=texts.solver_cards(manifest["cards"], manifest["runtime"]), rubrics=rubrics,
        instructions=manifest["instructions"], runtime=manifest["runtime"], clients=_clients(manifest["clients"]),
        budget=Budget(shared / "ledger"), slots={name: Slots(shared / "slots", name, count)
                                                for name, count in SLOTS.items()},
        sources=sources, workers=manifest["workers"],
        extra={"manifest": str(safe_path(path)), "pinned": pinned, "verify": lambda: verify_code(manifest),
               "baseline": manifest["baseline"], "overall": OVERALL_CEILING - prior})
    return manifest, setting
