"""The launch manifest of route B (registration §1, §2.6, §4.1, §9.3, §10, §21; implementation plan §2.9 and the manifest
row of §1): one sealed record of kind ``manifest`` whose ``record_sha256`` names the run. Copy of ``coevo5.manifest``
(manifest.py:33-151) with the route-B fields:

- ``pin_code`` / ``loaded_code`` / ``verify_code`` as coevo5 manifest.py:44-81: the code map pins every file under
  skillopt/ and scripts/ (bytecode caches excepted); a process refuses to run when a file it has loaded is not pinned,
  when a pinned file changed, or when its interpreter or openpyxl differs from the manifest's ``environment``. The
  loaded set starts from the whole ``skillopt/execskill`` package (sandbox/ and generators/ included) and
  ``scripts/run_execskill.py``.
- ``environment``: the interpreter, openpyxl, the docker server version, the pinned image's id read by a zero-call
  ``docker image inspect`` and the in-image library versions from ONE sandbox ping (the worker's ping reports python,
  numpy, openpyxl, pandas and sympy; their digest is ``in_image_pip_freeze_sha256``).
- ``verify_unit``: ``verify_code`` plus the zero-call image inspection before EVERY unit (plan §2.9). A mismatch raises
  ``ConfigurationError``; the chain runner writes ``chain-terminated.json`` (A12).
- ``make`` stamps the registered values (templates, lexicon, the engineer's and the describer's pinned prompt hashes
  next to it (``prompt_sha``, ticket A10-1 item 6), placebo corpus, seeds, sizes, thresholds, caps, importable
  versions, the sandbox's worker/policy/argv hashes) itself; the caller gives what only S0 and the operator know
  (data pins, qualification, cards, contracts, runtime, the S0 limits and measurements, clients, fixtures,
  provenance of the verified snapshot).
- the run adapters (ticket A13-1, C2-1 §1): ``setting_of(m, chain)`` -> ``units.Setting`` and ``services_of`` ->
  ``step.Services`` for chain G, chain D or the smoke (``RUNS``), from a verified manifest. The operator's ``data``
  pins hold, besides the ``exclusion`` records ``make-manifest`` binds: ``pools`` {bench: {"path", "sha256"}} for the
  benches of the configuration's order -- a JSON list of pool items (``task_id``, ``public``, ``private``; ALFWorld
  ``room``; SpreadsheetBench only its reference-qualified items), ordered here by ``supply.order``; ``searchqa_tail``
  {"path", "sha256"} when that order has SearchQA (the kept tail of its acceptance, M round 18:2x, bound with the
  SearchQA exclusion record as ``extra["searchqa_tail"]``); ``pinned`` (the frozen data
  pins the test read opens through ``data.test_panel``); ``research`` {"archive", "index_sha256"} (the frozen
  archive of §7.2); ``test_read_estimate`` {chain: S-E6-corrected tokens} (§9.3, chains G and D) and
  ``test_read_terms`` {chain: {bench: "p/q"}}, each chain's estimate as its exact per-bench terms (registrar addendum
  15:3x, ticket P2C-2: a relaunched read gate prices only the read units still to run). A smoke manifest is
  ``make-manifest`` on the smoke root with evidence "smoke": its items are the sealed smoke specification's
  (``<root>/smoke.json``), whose S0 limits and measurements (written before S1, plan §10 step 3) the manifest must
  carry unchanged.
- ``configuration`` (registrar "Owner instructions 2026-10-22 17:0x and 17:3x"): the run configuration
  (``protocol.CONFIGURATIONS``: the pilots "default" and "recommended", the five-bench "main") whose order, caps,
  test-read cells and cost-check rule the run follows. ``make`` stamps it with its caps (``budgets.caps``); ``check``
  refuses an unknown configuration, caps that are not its registered caps, and a real run's evidence label that is
  not the configuration's (``protocol.REAL_RUN_EVIDENCE``: ``pilot_real_run`` for a pilot, ``main_real_run`` for
  main); ``setting_of`` hands it to every consumer as ``setting.extra["configuration"]`` (``protocol.configuration_of``),
  never the module constants ``protocol.PILOT`` / ``protocol.ORDER``. A smoke manifest names the configuration its
  S-E6 projects.

The plan's ``record_hash`` is this protocol's ``record_sha256`` and every manifest carries ``evidence`` (plan §2: every
record).
"""
from __future__ import annotations

import functools
import hashlib
import math
import sys
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import BIGMODEL_HOST, digest

from scripts.weak_solver_probe import Client
from skillopt.coevo5.budget import Budget

from . import (budgets, client, describer, engineer, engines, examiner, notes, policy, research, routes,
               slots, step, supply, units)
from . import profiles as protocol
from .errors import ConfigurationError
from .generators import livemath
from .registry import Registry
from .sandbox import client as sandbox

REPO = Path(__file__).resolve().parents[2]
CODE_ROOTS = ("skillopt", "scripts")
PACKAGE = "skillopt/execskill"
COMMAND = "scripts/run_execskill.py"
KIND = "manifest"
GIVEN = frozenset({"root", "data", "sheet_qualification", "cards", "contracts", "runtime", "clients", "fixtures",
                   "provenance"})
FIELDS = GIVEN | {"version", "evidence", protocol.RECORD_HASH, "history_root", "slot_root", "templates",
                  "lexicon_sha", "prompt_sha", "placebo_corpus_sha", "sandbox", "seeds", "sizes", "thresholds", "caps",
                  "importable_versions", "code", "loaded_code", "environment", "configuration"}
SANDBOX_FIELDS = frozenset({"image_id", "worker_sha256", "policy_sha256", "docker_argv_template_sha", "limits",
                            "measured"})
MEASURED_FIELDS = frozenset({"vsz_kib", "rss_kib", "view_bytes_p99", "native_peak_rss_kib"})
SOLVER_FIELDS = frozenset({"backend", "model", "url_host", "env_path", "proxy", "reasoning_effort", "M", "B", "branch",
                           "longest", "read_timeout", "slots", "response_model_ids", "client_source_sha"})
ROLES = {"model": protocol.ROLE_MODEL, "max_tokens": protocol.ROLE_MAX_TOKENS,
         "read_timeout": protocol.ROLE_READ_TIMEOUT, "reasoning": protocol.ROLE_REASONING}
PROVENANCE_FIELDS = frozenset({"build_tree", "git_head", "snapshot_root", "sha256_list_sha256", "env_files_absent"})
ENVIRONMENT_FIELDS = frozenset({"python", "openpyxl", "docker", "image_digests", "in_image_libs",
                                "in_image_pip_freeze_sha256"})
IN_IMAGE_LIBS = ("python", "numpy", "openpyxl", "pandas", "sympy")
DOCKER_SECONDS = 30
RUNS = (*protocol.CHAINS, budgets.SMOKE)  # what ``setting_of`` builds: chain G, chain D or the smoke
SMOKE_EVIDENCE = "smoke"  # §10: every smoke record's evidence label
NATIVE_LOW_KIB = 2 * 1024 * 1024  # plan §5: native slots 3 -> 2 when the S0 native peak RSS exceeds 2 GiB
RESEARCH_FIELDS = frozenset({"archive", "index_sha256"})
ALFWORLD_CARD_IDENTITY = (2_301, "5ae6ea9b")  # frozen v3 import identity (CLI import-texts)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pin_code(repo=REPO):
    """The code map of a new manifest: every file under skillopt/ and scripts/ with its SHA-256 (coevo5
    manifest.py:44-48)."""
    return {path.relative_to(repo).as_posix(): _sha(path) for root in CODE_ROOTS
            for path in sorted((repo / root).rglob("*")) if path.is_file() and "__pycache__" not in path.parts}


def loaded_code(repo=REPO):
    """The files the manifest must pin in this process: the execskill package, its command line and every
    repository module under skillopt/ or scripts/ the process has loaded (coevo5 manifest.py:51-61)."""
    names = {path.relative_to(repo).as_posix() for path in (repo / PACKAGE).rglob("*.py")
             if "__pycache__" not in path.parts} | {COMMAND}
    for module in list(sys.modules.values()):
        found = getattr(module, "__file__", None)
        path = Path(found).resolve() if isinstance(found, str) else None
        if path is not None and path.suffix == ".py" and path.is_relative_to(repo) \
                and path.relative_to(repo).parts[0] in CODE_ROOTS:
            names.add(path.relative_to(repo).as_posix())
    return names


def _docker_text(docker, args):
    """One bounded zero-call docker CLI command's stdout (``sandbox.client.Docker``: PATH-only environment)."""
    if docker.binary is None:
        raise ConfigurationError("docker is not available")
    done = docker.run([docker.binary, *args], DOCKER_SECONDS)
    if done.code != 0:
        raise ConfigurationError("docker %s failed" % args[0])
    return done.stdout.decode("utf-8", "replace").strip()


def image_id(docker=None, image=sandbox.IMAGE):
    """The pinned image's id by ``docker image inspect`` (zero calls); ConfigurationError when it is missing or
    differs from the pin (§2.6)."""
    found = _docker_text(docker or sandbox.Docker(), ["image", "inspect", "--format", "{{.Id}}", image])
    if found != image:
        raise ConfigurationError("The pinned sandbox image is missing or differs: %s" % found[:80])
    return found


def _ping_empty():
    """One ping of an empty-package cell worker (lazy start, forced removal of its exact name on close)."""
    empty = SimpleNamespace(sha256=digest([]), procedures=())
    with sandbox.with_worker(empty, kind="cell") as worker:
        return worker.ping()


def environment(*, docker=None, ping=None):
    """The interpreter, openpyxl, docker, the pinned image's id and the in-image libraries (one sandbox ping).
    ``docker``: a ``sandbox.client.Docker``; ``ping``: a callable returning one worker ping (tests pass fakes)."""
    import openpyxl

    docker = docker or sandbox.Docker()
    found = (ping or _ping_empty)()
    libs = {name: found.get(name) for name in IN_IMAGE_LIBS}
    require(all(type(value) is str and value for value in libs.values()), "The sandbox ping names its libraries")
    return {"python": sys.version.split()[0], "openpyxl": openpyxl.__version__,
            "docker": _docker_text(docker, ["version", "--format", "{{.Server.Version}}"]),
            "image_digests": {"sandbox": image_id(docker)}, "in_image_libs": libs,
            "in_image_pip_freeze_sha256": digest(libs)}


def verify_code(manifest, repo=REPO):
    """The code map holds every file this process has loaded, every pinned file still has its pinned hash, and the
    process runs on the manifest's Python and openpyxl (coevo5 manifest.py:71-81); raises otherwise."""
    import openpyxl

    found = {"python": sys.version.split()[0], "openpyxl": openpyxl.__version__}
    require(found == {key: manifest["environment"].get(key) for key in found},
            "The interpreter or openpyxl differs from the launch manifest: %s" % found)
    missing = sorted(loaded_code(repo) - set(manifest["code"]))
    require(not missing, "Files missing from the launch manifest: %s" % missing[:5])
    changed = [name for name, sha in sorted(manifest["code"].items())
               if not (repo / name).is_file() or _sha(repo / name) != sha]
    require(not changed, "Files differ from the launch manifest: %s" % changed[:5])


def verify_unit(manifest, *, docker=None, repo=REPO):
    """Before EVERY unit (plan §2.9): ``verify_code`` and the zero-call image inspection against the manifest's
    image. ConfigurationError on any mismatch (the chain then writes chain-terminated.json)."""
    try:
        verify_code(manifest, repo)
    except ValueError as error:
        raise ConfigurationError(str(error)) from None
    image_id(docker, manifest["sandbox"]["image_id"])


def prompt_sha(configuration=None):
    """The pinned prompt hashes the manifest binds next to the lexicon hash (ticket A10-1 item 6, C6b-1 §3): the
    describer's, the engineer's and the examiner's three (policy, detectors, generators); for a run configuration that
    trains (``protocol.LEARNING``) also ``v2``: v2's engineer and examiner prompts (owner decision 2026-10-23 13:3x)
    and its analysts' (owner suggestion 2026-10-23 15:1x). A v1 configuration binds exactly the first three (Codex
    review 2026-10-23 #1)."""
    out = {"describer": describer.DESCRIBER_PROMPT_SHA256, "engineer": engineer.ENGINEER_PROMPT_SHA256,
           "examiner": dict(examiner.PROMPT_SHA256)}
    if protocol.is_v23(configuration):
        out["engineer"] = engineer.ENGINEER_PROMPT_SINGLE_V23_SHA256
    if protocol.LEARNING.get(configuration) == "train":
        out["v2"] = {"engineer": (engineer.ENGINEER_PROMPT_V23_SHA256 if protocol.is_v23(configuration)
                                          else engineer.ENGINEER_PROMPT_V2_SHA256), "analyst": engineer.ANALYST_PROMPT_SHA256,
                     "examiner": dict(examiner.PROMPT_V2_SHA256)}
    if protocol.is_zebra(configuration):
        out["engineer"] = (engineer.ENGINEER_PROMPT_SINGLE_ZPC_V28_SHA256 if protocol.is_v28(configuration) else
                           engineer.ENGINEER_PROMPT_SINGLE_ZPC_V27_SHA256 if protocol.is_v27(configuration) else
                           engineer.ENGINEER_PROMPT_SINGLE_ZPC_V26_SHA256 if protocol.is_v26(configuration) else
                           engineer.ENGINEER_PROMPT_SINGLE_ZPC_V25_SHA256 if protocol.is_v25(configuration) else
                           engineer.ENGINEER_PROMPT_SINGLE_ZPC_V24_SHA256 if protocol.is_v24(configuration)
                           else engineer.ENGINEER_PROMPT_SINGLE_ZPC_SHA256)
        out["v2"]["engineer"] = (engineer.ENGINEER_PROMPT_ZPC_V28_SHA256 if protocol.is_v28(configuration) else
                                 engineer.ENGINEER_PROMPT_ZPC_V27_SHA256 if protocol.is_v27(configuration) else
                                 engineer.ENGINEER_PROMPT_ZPC_V26_SHA256 if protocol.is_v26(configuration) else
                                 engineer.ENGINEER_PROMPT_ZPC_V25_SHA256 if protocol.is_v25(configuration) else
                                 engineer.ENGINEER_PROMPT_ZPC_V24_SHA256 if protocol.is_v24(configuration)
                                 else engineer.ENGINEER_PROMPT_ZPC_SHA256)
    if protocol.is_alfworld(configuration):
        out["engineer"] = (engineer.ENGINEER_PROMPT_SINGLE_ALF_V3_SHA256 if protocol.is_v28(configuration) else
                           engineer.ENGINEER_PROMPT_SINGLE_ALF_V2_SHA256 if protocol.is_alfworld_v2(configuration)
                           else engineer.ENGINEER_PROMPT_SINGLE_ALF_V1_SHA256)
        out["v2"]["engineer"] = (engineer.ENGINEER_PROMPT_ALF_V3_SHA256 if protocol.is_v28(configuration) else
                                 engineer.ENGINEER_PROMPT_ALF_V2_SHA256 if protocol.is_alfworld_v2(configuration)
                                 else engineer.ENGINEER_PROMPT_ALF_V1_SHA256)
    if protocol.is_v28(configuration):
        out["v28"] = {"fix": engineer.ENGINEER_PROMPT_FIX_V28_SHA256,
                      "format_retry": engineer.ENGINEER_PROMPT_FORMAT_RETRY_V28_SHA256}
    return out


def _plain(value):
    """Registered values as JSON: fractions as "p/q" text, tuples as lists."""
    if isinstance(value, Fraction):
        return "%d/%d" % (value.numerator, value.denominator)
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, frozenset, set)):
        items = [_plain(item) for item in value]
        return sorted(items) if isinstance(value, (frozenset, set)) else items
    return value


def registered(configuration=None):
    """The registered seeds, sizes and thresholds the manifest binds (values of ``protocol``)."""
    from . import protocol as historical
    p = protocol if protocol.is_zebra(configuration) else historical
    return _plain({
        "seeds": {"seed": p.SEED, "rooms_tag": p.ROOMS_TAG, "alfworld_env_seed": p.ALFWORLD_ENV_SEED,
                  "searchqa_fresh_seed": p.SEARCHQA_FRESH_SEED},
        "sizes": {"slices": p.SLICES, "g_acc": p.G_ACC, "smoke_real_items": p.SMOKE_REAL_ITEMS,
                  "smoke_fixtures": p.SMOKE_FIXTURES, "max_changes": p.MAX_CHANGES,
                  "max_twins_per_item": p.MAX_TWINS_PER_ITEM, "band_rounds": p.BAND_ROUNDS,
                  "selftest_passes": p.SELFTEST_PASSES, "min_astar": p.MIN_ASTAR, "min_astar_rooms": p.MIN_ASTAR_ROOMS},
        "thresholds": {"alpha": p.ALPHA, "harmful_sham_alpha": p.HARMFUL_SHAM_ALPHA,
                       "min_whole_batch": p.MIN_WHOLE_BATCH, "fault_share_max": p.FAULT_SHARE_MAX,
                       "format_margin_min": p.FORMAT_MARGIN_MIN, "format_margin_share": p.FORMAT_MARGIN_SHARE,
                       "infra_unknown_max": p.INFRA_UNKNOWN_MAX, "dup_alpha": p.DUP_ALPHA,
                       "holm_family": p.HOLM_FAMILY, "smoke_format_floor": p.SMOKE_FORMAT_FLOOR,
                       "smoke_format_margin": p.SMOKE_FORMAT_MARGIN,
                       "min_production_receipts": p.MIN_PRODUCTION_RECEIPTS}})


def _solver_fields(chain, env_path, branch, longest, configuration=None):
    """A solver block without its ledger bound B; ``longest`` (the S1 probes' longest completion, branch N only) is
    recorded so that B can be re-derived from the block alone (safety review finding 2)."""
    require(chain in protocol.CHAINS, "A registered chain")
    model = protocol.CHAINS[chain]
    elucid = model == client.ELUCID_MODEL
    require(branch in protocol.BRANCHES if elucid else branch is None, "Chain D names its S1 branch; chain G none")
    benches = protocol.active_benches(configuration)
    return {"backend": "elucid" if elucid else "bigmodel", "model": model,
            "url_host": client.ELUCID_HOST if elucid else BIGMODEL_HOST, "env_path": str(safe_path(env_path)),
            "proxy": protocol.GATEWAY, "reasoning_effort": protocol.REASONING_EFFORT if elucid else "low",
            "M": {b: protocol.solver_tokens(model, b) for b in benches}, "branch": branch, "longest": longest,
            "read_timeout": {b: protocol.read_timeout(model, b) for b in benches},
            "slots": protocol.SLOTS[model],
            "response_model_ids": sorted(client.ELUCID_RESPONSE_MODEL_IDS) if elucid else [model],
            "client_source_sha": _sha(Path(client.__file__))}


def solver_block(chain, *, env_path, branch=None, longest=None, configuration=None):
    """The ``clients.solver[chain]`` block (§4.1, §21; plan §2.9): the registered client of the chain's solver with
    its per-bench nominal M, ledger bound B (``protocol.ledger_bound``) and read timeout. ``env_path``: chain D's
    credential file, chain G's credential repository (read by path only, never here)."""
    fields = _solver_fields(chain, env_path, branch, longest, configuration)
    model = fields["model"]
    return {**fields, "B": {b: protocol.ledger_bound(model, b, branch=branch, longest=longest)
                            for b in protocol.active_benches(configuration)}}


def role_settings(configuration=None):
    """The frozen default role bound, plus v2.3's explicitly named train proposal bound (E1)."""
    return {**ROLES, "engineer_propose_max_tokens": protocol.ENGINEER_MAX_TOKENS[configuration]} \
        if protocol.is_v23(configuration) else dict(ROLES)


def check_clients(clients, *, configuration=None):
    """The clients block: one registered solver block per listed chain and the registered role settings. Every
    field of a solver block, the ledger bound B included, must equal ``solver_block`` re-derived from the block's own
    env path, branch and longest probe completion: B is the reservation size and the halting threshold, so a B that
    is merely at least M is refused (safety review finding 2). The optional ``routes`` (chain D's route-B pin,
    registrar row "deepseek route B") is ``routes.check_pins``'s, required in a ``main`` manifest."""
    require(isinstance(clients, dict) and set(clients) - {"routes"} == {"solver", "roles"},
            "clients holds solver and roles (and the route pins)")
    solvers = clients["solver"]
    require(isinstance(solvers, dict) and solvers and set(solvers) <= set(protocol.CHAINS), "Solver blocks per chain")
    for chain, block in solvers.items():
        require(isinstance(block, dict) and set(block) == SOLVER_FIELDS, "A solver block holds the registered fields")
        expected = solver_block(chain, env_path=block["env_path"], branch=block["branch"], longest=block["longest"], configuration=configuration)
        same = {key for key in SOLVER_FIELDS if block[key] == expected[key]}
        require(same == SOLVER_FIELDS, "The %s solver block differs from the registration: %s"
                % (chain, sorted(SOLVER_FIELDS - same)))
    require(clients["roles"] == role_settings(configuration), "The method roles' registered settings")
    routes.check_pins(clients, configuration=configuration)  # M4: route B (registrar 17:3x)


def check(manifest):
    """The field sets of a manifest record (raises ValueError)."""
    value = protocol.verified(manifest, KIND)
    require(set(value) == FIELDS, "Not a %s manifest" % protocol.VERSION)
    require(set(value["sandbox"]) == SANDBOX_FIELDS and set(value["sandbox"]["measured"]) == MEASURED_FIELDS,
            "The sandbox block holds the registered fields")
    require(set(value["environment"]) == ENVIRONMENT_FIELDS, "The environment block holds the registered fields")
    require(set(value["provenance"]) == PROVENANCE_FIELDS and value["provenance"]["env_files_absent"] is True,
            "The provenance names the verified snapshot without .env files")
    require(isinstance(value["prompt_sha"], dict)
            and set(value["prompt_sha"]) == set(prompt_sha(value.get("configuration"))),
            "The manifest binds the engineer's and the describer's prompt hashes")
    require(_card_texts(value["cards"], value["configuration"]), "The manifest's cards are the five card texts, not their hashes: cells.py "
            "hands cards[bench] to the solver as the card (registrar addendum 14:10 row 12)")
    configuration = value["configuration"]
    require(configuration in protocol.CONFIGURATIONS and value["caps"] == budgets.caps(configuration),
            "The manifest names a registered run configuration and carries its caps (registrar 17:0x)")
    real = set(protocol.REAL_RUN_EVIDENCE.values())
    require(value["evidence"] not in real or value["evidence"] == protocol.REAL_RUN_EVIDENCE[configuration],
            "A real run's evidence label is its configuration's: %s" % protocol.REAL_RUN_EVIDENCE[configuration])
    check_clients(value["clients"], configuration=configuration)
    if protocol.is_v23(configuration):
        require(value["sandbox"]["policy_sha256"] == policy.policy_sha256(
            version=protocol.POLICY_VERSIONS[configuration]), "The v2.3 sandbox policy is pinned")
        sheet = value["runtime"].get("spreadsheetbench")
        if sheet is None:
            if protocol.is_alfworld(configuration):
                return _check_alfworld(value)
            require(protocol.is_zebra(configuration), "Only a registered text-only profile omits sheet runtime")
            return _check_zebra(value)
        require(sheet.get("code_extraction_version") == protocol.CODE_EXTRACTION[configuration]
                and sheet.get("multiple_python_blocks") == protocol.MULTIPLE_PYTHON_BLOCKS[configuration],
                "The v2.3 extraction and multiple-block decision are pinned")
    if protocol.is_alfworld(configuration):
        return _check_alfworld(value)
    return _check_zebra(value) if protocol.is_zebra(configuration) else value


def _card_texts(cards, configuration=None):
    """Whether ``cards`` is {bench: card text} for every bench (pilot-runbook §3.1): non-empty texts, none of them a
    bare sha256 hex digest."""
    return isinstance(cards, dict) and set(cards) == set(protocol.active_benches(configuration)) and all(
        type(text) is str and text.strip() and not (len(text) == 64 and set(text) <= set("0123456789abcdef"))
        for text in cards.values())


def make(out, *, evidence, environment_found=None, limits=None, measured, configuration=protocol.PILOT, **given):
    """The sealed manifest at ``out`` (a new file; zero calls). ``given``: exactly ``GIVEN``; ``limits``: {kind:
    sandbox.Limits} registered from S0 (None: the start values); ``measured``: the S0 measurements
    (``MEASURED_FIELDS``); ``environment_found``: ``environment()`` (computed when None); ``configuration``: the run
    configuration (``protocol.CONFIGURATIONS``), stamped with its caps. Returns the record."""
    require(configuration in protocol.CONFIGURATIONS, "Unknown run configuration: %r" % (configuration,))
    out = safe_path(out)
    require(not out.exists(), "A new manifest file")
    require(set(given) == GIVEN, "The manifest's given fields: %s" % sorted(GIVEN))
    limits = dict(sandbox.LIMITS if limits is None else limits)
    require(set(limits) == set(sandbox.KINDS) and all(isinstance(v, sandbox.Limits) for v in limits.values()),
            "Registered limits for every sandbox kind")
    if protocol.is_v23(configuration) and "spreadsheetbench" in given["runtime"]:
        given = {**given, "clients": {**given["clients"], "roles": role_settings(configuration)},
                 "runtime": {**given["runtime"], "spreadsheetbench": {
                     **given["runtime"]["spreadsheetbench"],
                     "code_extraction_version": protocol.CODE_EXTRACTION[configuration],
                     "multiple_python_blocks": protocol.MULTIPLE_PYTHON_BLOCKS[configuration]}}}
    if protocol.is_zebra(configuration):
        from .zebralogic import CARD_VERSION
        given = {**given, "clients": {**given["clients"], "roles": role_settings(configuration)},
                 "data": {**given["data"], "zebra_pc_features": zebra_features(configuration)}}
    if protocol.is_alfworld(configuration):
        given = {**given, "clients": {**given["clients"], "roles": role_settings(configuration)},
                 "data": {**given["data"], "alfworld_features": alfworld_features(configuration)}}
    from . import protocol as historical
    fields = {
        **given, **registered(configuration), "history_root": historical.HISTORY_ROOT, "slot_root": historical.SLOT_ROOT,
        "templates": protocol.TEMPLATES_SHA256, "lexicon_sha": notes.lexicon_sha256(),
        "prompt_sha": prompt_sha(configuration),
        "placebo_corpus_sha": protocol.PLACEBO_CORPUS_SHA256, "configuration": configuration,
        "caps": budgets.caps(configuration),
        "importable_versions": ([*protocol.IMPORTABLE, CARD_VERSION]
                                if protocol.is_zebra(configuration) else [*protocol.IMPORTABLE, protocol.TEXTS_IMPORT]),
        "sandbox": {"image_id": sandbox.IMAGE, "worker_sha256": sandbox.worker_sha256(),
                    "policy_sha256": policy.policy_sha256(version=protocol.POLICY_VERSIONS[configuration]),
                    "docker_argv_template_sha": digest({k: sandbox.argv_template(k, v) for k, v in limits.items()}),
                    "limits": {k: asdict(v) for k, v in sorted(limits.items())}, "measured": measured},
        "code": pin_code(), "loaded_code": sorted(loaded_code()),
        "environment": environment() if environment_found is None else environment_found}
    suffix = ("-v2-8" if protocol.is_v28(configuration) else "-alf-v2" if protocol.is_alfworld_v2(configuration) else "-alf-v1" if protocol.is_alfworld(configuration) else
              "-v2-7" if protocol.is_v27(configuration) else "-v2-6" if protocol.is_v26(configuration)
              else "-v2-5" if protocol.is_v25(configuration)
              else "-v2-4" if protocol.is_v24(configuration)
              else "-v2-3" if protocol.is_v23(configuration) else "")
    record = check(protocol.record(KIND + suffix, evidence, fields))
    write_json(out, record)
    return record


def load(path, *, verify=True, docker=None):
    """The checked manifest at ``path``; with ``verify`` the code map, interpreter and image are verified first."""
    value = check(read_json(path))
    if verify:
        verify_unit(value, docker=docker)
    return value


def limits_of(manifest):
    """{kind: sandbox.Limits} registered in the manifest (the ``Worker(limits=...)`` input)."""
    return {kind: sandbox.Limits(**value) for kind, value in manifest["sandbox"]["limits"].items()}


def solver_config(manifest, chain, bench, route=None):
    """The ``client.solver_client`` config of ``chain``'s solver on ``bench``: the manifest block projected onto
    ``client.CONFIG_KEYS`` (A2's note). ``route``: chain D's route (``routes``; None or route A: the solver block,
    another route: its pin with the route named; registrar row "deepseek route B")."""
    if route is not None and route != routes.ROUTED[chain][0]:
        return routes.config(routes.block_of(manifest, chain, route), bench)
    block = manifest["clients"]["solver"][chain]
    if block["model"] == client.ELUCID_MODEL:
        return {"env_path": block["env_path"], "proxy": block["proxy"], "max_tokens": block["M"][bench],
                "read_timeout": block["read_timeout"][bench]}
    return {"repo": block["env_path"], "proxy": block["proxy"]}


# --------------------------------------------------------------------------------- the run adapters (A13-1)
def _solver_chain(chain, root):
    """The solver block a run on ``root`` uses: chain G's or chain D's own; the smoke's, the solver chain of its
    specification ``<root>/smoke.json`` (``smoke.solver_of``: chain D's model by default, §10, §21 (c); chain G's in a
    chain-G smoke, registrar addendum 2026-10-23 02:3x)."""
    require(chain in RUNS, "Chain G, chain D or the smoke")
    if chain != budgets.SMOKE:
        return chain
    from . import smoke  # imported here: smoke imports this module

    return smoke.solver_of(smoke.load(safe_path(root) / smoke.SPEC)).chain


def _smoke_example(root):
    """Whether the smoke specification at ``root`` lists v2's example stage SX."""
    from . import smoke  # imported here: smoke imports this module

    return "SX" in smoke.load(safe_path(root) / smoke.SPEC).get("stages", ())


def _items(entry, bench):
    """One bench's items from a pinned JSON list file (``{"path", "sha256"}``), in the bench's fixed order."""
    if bench == "zebralogic":
        from . import zebralogic
        return zebralogic.load_pool(entry["path"], expected_sha256=entry["sha256"])
    path = safe_path(entry["path"])
    require(_sha(path) == entry["sha256"], "The %s item file differs from its pin" % bench)
    found = read_json(path)
    require(isinstance(found, list) and found and all(isinstance(i, dict) and {"task_id", "public", "private"} <= set(i)
                                                      for i in found), "A %s item file lists pool items" % bench)
    return supply.order(bench, found)


def _smoke_pools(m, root):
    """The smoke's items: the sealed smoke specification's item sets, whose S0 limits and measurements the manifest
    carries unchanged (plan §10 step 3: registered before S1)."""
    from . import smoke  # imported here: smoke imports this module

    spec = smoke.load(root / smoke.SPEC)
    ours = smoke.solver_of(spec)  # registrar addendum 2026-10-23 02:3x: chain D's model, or glm-5.3 in a chain-G smoke
    require(spec["root"] == str(root) and spec["solver"]["model"] == protocol.CHAINS[ours.chain]
            and m["clients"]["solver"].get(ours.chain, {}).get("model") == ours.model, "The smoke's own spec")
    measured = spec["sandbox"]["measured"]
    shared = MEASURED_FIELDS & set(measured)  # the self-test has no native peak; the manifest no start latency
    require(spec["sandbox"]["limits"] == m["sandbox"]["limits"] and shared
            and all(m["sandbox"]["measured"][key] == measured[key] for key in shared),
            "The smoke manifest carries the S0 limits and measurements of the smoke specification")
    return {bench: _items(entry, bench) for bench, entry in sorted(spec["items"].items())}


def _pools(m, chain, root):
    if chain == budgets.SMOKE:
        return _smoke_pools(m, root)
    order = protocol.CONFIGURATIONS[m["configuration"]]["order"]
    pinned = m["data"].get("pools")
    require(isinstance(pinned, dict) and set(order) <= set(pinned), "The data pins name the pools of the "
            "configuration's order")
    return {bench: _items(pinned[bench], bench) for bench in order}


def _slot_sizes(m):
    """The registered pool-size changes from S0 (plan §5): native 3 -> 2 above a 2 GiB native peak RSS."""
    peak = m["sandbox"]["measured"]["native_peak_rss_kib"]
    require(type(peak) is int and peak > 0, "The S0 native peak RSS")
    return {slots.NATIVE: protocol.NATIVE_SLOTS_LOW_MEMORY} if peak > NATIVE_LOW_KIB else None


def _clients(m, chain, transport, route=None):
    """``Setting.clients(model, bench)``: the run's solver per bench (``client.solver_client`` with
    ``solver_config``) and, for ``bench`` None, the method roles' GLM-5.3 client with the registered role settings
    (``ROLES``), built as the v3 factory builds it (coevo5/manifest.py:95-112) from the credential repository of the G
    solver block (GLM-5.3 is chain G's solver and every role's model, §4.2-§4.3). ``route``: chain D's route this
    process runs on (``setting_of``); the chain's route history is read again at every solver client request -- every
    unit start -- and a route changed under the running process refuses it (``routes.check_bound``), so a unit never
    switches mid-unit (registrar row "deepseek route B")."""
    solvers, run = m["clients"]["solver"], _solver_chain(chain, m["root"])
    require(run in solvers and "G" in solvers, "The manifest names the run's solver and the roles' GLM-5.3 credentials")
    model, roles = solvers[run]["model"], m["clients"]["roles"]
    cache = {}

    def make(wanted, bench):
        if bench is not None and route is not None:  # M4: the chain D client factory reads the route at unit start
            routes.check_bound(safe_path(m["root"]) / run, route, run=m[protocol.RECORD_HASH], chain=run)
        key = (wanted, bench)
        if key not in cache:
            if bench is None:
                require(wanted == roles["model"], "Every method role is GLM-5.3")
                try:
                    cache[key] = client.unpooled(  # v2.1: no connection limit (client.POOL_LIMITS)
                        Client(solvers["G"]["env_path"], roles["model"], proxy=solvers["G"]["proxy"],
                               max_tokens=roles["max_tokens"], read_timeout=roles["read_timeout"],
                               transport=transport),
                        proxy=solvers["G"]["proxy"], read_timeout=roles["read_timeout"], transport=transport)
                except (SystemExit, OSError) as refusal:  # the frozen refusals carry no secret
                    raise ConfigurationError("glm-5.3 role credentials: %s" % refusal) from None
            else:
                require(wanted == model and bench in protocol.active_benches(m["configuration"]), "The run's solver on a known bench")
                cache[key] = client.solver_client(model, config=solver_config(m, run, bench, route),
                                                  transport=transport)
        return cache[key]

    return make


def _safety(setting, block):
    """The safety review's invariants (finding 6, ticket fixer-6 item 7) and the ledger bound (finding 2, fixer-6
    item 5): the slots are one ``slots.pools`` set, the workers get the live and per-call pools, and the ledger bound
    re-derived from the Setting's branch and longest is the manifest's B on every bench."""
    pools = setting.slots
    require(set(pools) == set(slots.POOL_SIZES) and all(isinstance(p, slots.OrderedSlots) for p in pools.values())
            and len({id(p.holdings) for p in pools.values()}) == 1, "The Setting's slots are one slots.pools set")
    require(pools[slots.LIVE] is not None and pools[slots.CALL] is not None, "Workers get the live and per-call pools")
    for bench in protocol.active_benches(protocol.configuration_of(setting)):
        require(protocol.ledger_bound(block["model"], bench, branch=setting.branch, longest=setting.longest)
                == block["B"][bench], "The Setting's ledger bound is the manifest's B on %s" % bench)


def setting_of(m, chain, *, path=None, docker=None, transport=None):
    """The ``units.Setting`` of ``chain`` (``RUNS``) from the verified manifest ``m`` (module docstring; ticket C2-1
    §1). Chains G and D run on their own ledgers (``budgets.ledger_root``; ``chain.run`` declares their caps), the
    smoke on ``<root>/shared/ledger`` with ``budgets.smoke_caps()`` declared here; the solver is the chain's (the smoke:
    its specification's, ``smoke.solver_of``: chain D's elucid model, or GLM-5.3 in a chain-G smoke, registrar
    addendum 2026-10-23 02:3x), every role GLM-5.3; ``branch`` / ``longest`` are the verified solver block's (fixer-6
    item 5). ``extra``: ``verify`` (``verify_unit`` before every unit), ``drain`` (the unit drain,
    ``sandbox.client.drain_unit``), ``slot_root``, ``configuration`` (the manifest's run configuration, which every
    consumer follows: ``protocol.configuration_of``), ``manifest`` (``path``, the file the read children are started
    with) and, for G and D, ``test_read_estimate`` and ``test_read_terms`` (ticket P2C-2) and, when the
    configuration's order has SearchQA, ``searchqa_tail`` (``data.searchqa_tail`` with the bound SearchQA exclusion
    record as ``exclusion``; M round 18:2x). Chain D runs on the route its history names now (``routes.current``; the
    smoke always on route A): that route's client, and ``branch`` / ``longest`` / B of its block (route B: the pin,
    branch N), with ``extra["route"]`` its id (registrar row "deepseek route B"). ``docker``: the docker CLI
    of the workers, the drain and the image check (a fake in tests); ``transport``: the clients' httpx transport
    (tests)."""
    require(chain in RUNS, "Chain G, chain D or the smoke")
    if protocol.is_zebra(m["configuration"]) and protocol.is_v27(m["configuration"]):
        require(chain in protocol.launchable_chains(m["configuration"]), "zebra-pc-v5 launches chain D only")
    if protocol.is_alfworld_v2(m["configuration"]):
        require(chain in protocol.launchable_chains(m["configuration"]), "ALFWorld v2 launches only chain D")
    require((m["evidence"] == SMOKE_EVIDENCE) == (chain == budgets.SMOKE)
            or ((protocol.is_zebra(m["configuration"]) or protocol.is_alfworld(m["configuration"]))
                and m["evidence"] == SMOKE_EVIDENCE),
            "The smoke runs on a smoke manifest and the chains on a pilot manifest")
    require(m["lexicon_sha"] == notes.lexicon_sha256() and m["prompt_sha"] == prompt_sha(m["configuration"]),
            "The lexicon or a pinned prompt differs from the manifest")
    if protocol.is_zebra(m["configuration"]):
        require(chain in m["data"].get("launchable_chains", protocol.CHAINS), "This chain needs its own passed smoke")
    if protocol.is_alfworld(m["configuration"]):
        require(chain in protocol.launchable_chains(m["configuration"])
                and chain in m["data"].get("launchable_chains", ()),
                "ALFWorld v2 launches only chain D" if protocol.is_alfworld_v2(m["configuration"])
                else "ALFWorld v1 launches only chain D")
    root, docker = safe_path(m["root"]), docker or sandbox.Docker()
    solver_chain = _solver_chain(chain, root)  # the smoke: its specification's (registrar addendum 2026-10-23 02:3x)
    route = routes.current(root / chain, run=m[protocol.RECORD_HASH], chain=chain) if chain in routes.ROUTED else None
    block = m["clients"]["solver"][solver_chain]
    bound = block if route is None else {**routes.block_of(m, chain, route), "model": block["model"]}  # M4
    pools = slots.pools(m["slot_root"], sizes=_slot_sizes(m))
    budget = Budget(budgets.ledger_root(root, chain))
    extra = {"verify": functools.partial(verify_unit, m, docker=docker),
             "drain": functools.partial(sandbox.drain_unit, docker=docker), "slot_root": m["slot_root"],
             "configuration": m["configuration"]}
    if path is not None:
        extra["manifest"] = str(safe_path(path))
    if route is not None:
        extra["route"] = route
    if chain == budgets.SMOKE:  # a smoke listing v2's example SX: the example caps
        budget.declare(budgets.smoke_caps(example=_smoke_example(root)))
    else:
        estimate = m["data"].get("test_read_estimate")
        require(isinstance(estimate, dict) and type(estimate.get(chain)) is int and estimate[chain] > 0,
                "The data pins hold the S-E6-corrected test-read estimate of chain %s" % chain)
        extra["test_read_estimate"] = {chain: estimate[chain]}
        terms = m["data"].get("test_read_terms")
        require(isinstance(terms, dict) and _read_terms(terms.get(chain), estimate[chain], m["configuration"]), "The data pins hold the "
                "per-bench terms of that estimate (data.test_read_terms[%s], {bench: \"p/q\"} whose sum rounds up to "
                "it; registrar addendum 15:3x, ticket P2C-2)" % chain)
        extra["test_read_terms"] = {chain: dict(terms[chain])}
        if "searchqa" in protocol.CONFIGURATIONS[m["configuration"]]["order"]:
            extra["searchqa_tail"] = _searchqa_tail(m["data"])
    setting = units.Setting(
        run=m[protocol.RECORD_HASH], root=root, shared=root / "shared", pools=_pools(m, chain, root),
        cards=dict(m["cards"]), runtime=dict(m["runtime"]), clients=_clients(m, chain, transport, route),
        budget=budget, slots=pools,
        sandbox={"docker": docker, "limits": limits_of(m), "image": m["sandbox"]["image_id"]},
        evidence=m["evidence"], branch=bound["branch"], longest=bound["longest"], extra=extra)
    _safety(setting, bound)
    return setting


def _searchqa_tail(data):
    """The SearchQA tail pin ``data.searchqa_tail`` {"path", "sha256"} with the bound SearchQA exclusion record
    (``data.exclusion.searchqa_test_exclusion`` {"path", "record_sha256"}) as ``exclusion`` (M round 18:2x; the step
    checks the file's sha256 and the exclusion record)."""
    _, searchqa_run = protocol.EXCLUSION_RUNS  # "searchqa_test_exclusion", as exclusion.SEARCHQA_RUN
    tail, bound = data.get("searchqa_tail"), (data.get("exclusion") or {}).get(searchqa_run)
    require(isinstance(tail, dict) and set(tail) == {"path", "sha256"} and type(tail["path"]) is str
            and type(tail["sha256"]) is str and len(tail["sha256"]) == 64, "The data pins hold the SearchQA tail "
            "(data.searchqa_tail {path, sha256}) of a configuration whose order has SearchQA")
    require(isinstance(bound, dict) and {"path", "record_sha256"} <= set(bound), "The data pins bind the SearchQA "
            "exclusion record (make-manifest --exclusion-root)")
    return {**tail, "exclusion": dict(bound)}


def _read_terms(terms, estimate, configuration=None):
    """Whether ``terms`` are the per-bench terms of the test-read ``estimate`` (``test-read-estimate``'s ``terms``,
    ``protocol.read_estimate_terms``): {bench: "p/q"} for every bench, each positive, the ceiling of their sum the
    estimate (registrar addendum 2026-10-22 15:3x, ticket P2C-2)."""
    if not (isinstance(terms, dict) and set(terms) == set(protocol.read_benches(configuration))
            and all(type(text) is str for text in terms.values())):
        return False
    try:
        values = [Fraction(text) for text in terms.values()]
    except (ValueError, ZeroDivisionError):
        return False
    return all(value > 0 for value in values) and math.ceil(sum(values)) == estimate


@dataclass(frozen=True)
class Services(step.Services):
    """``step.Services`` as ``services_of`` builds it (ticket C7d-2, registrar addendum 14:3x): LiveMath's checker
    (``generators.livemath.WorkerChecker``) is always made from this instance's own ``workers``. ``step._Step.unit``
    re-binds ``workers`` to the running unit's tag with ``dataclasses.replace``, which builds a new instance, so the
    checker a unit's generator sees starts its containers with that unit's tag and ``drain_unit`` finds them (ticket
    C5-1). Making a checker starts nothing (a container starts only in its ``solve`` or ``session``). A checker of
    another kind given explicitly (a fake) is kept."""

    def __post_init__(self):
        if self.sources is None:
            return  # selection-only profile: no LiveMath service
        if self.checker is None or (isinstance(self.checker, livemath.WorkerChecker)
                                    and self.checker.workers is not self.workers):
            object.__setattr__(self, "checker", livemath.WorkerChecker(self.workers))


def services_of(m, chain, *, setting, transport=None):
    """The ``step.Services`` of ``chain`` beside its ``setting`` (``setting_of(m, chain)``; ticket C2-1 §1): the
    consumption registry under the manifest's history root; the research sources over the frozen archive the data pins
    bind (its index hash checked), Wikipedia through the registered gateway, the fetched pages archived under
    ``<root>/shared/research/<chain>``; the sandbox worker factory bound to the Setting's sandbox options and its live
    and per-call pools (the step binds each unit's tag); ``item_workers`` None (derived from ``workers``, mounting a
    SpreadsheetBench item's public workbook). SpreadsheetBench's engines are ``engines.sheet_engines`` over the
    manifest's SpreadsheetBench runtime, the Setting's native pool and the manifest's evidence (tickets C6-1,
    PR-C61-1; building them starts nothing, and the runtime is revalidated at the first recalculation); LiveMath's
    checker is ``livemath.WorkerChecker`` over the unit's own ``workers`` (``Services``; tickets C6-1, C7d-2).
    ``step._build`` holds one ``checker.session()`` around each LiveMath ``examiner.build``, so one worker serves every
    solve of a set (ticket I1-2, registrar addendum 14:4x)."""
    require(chain in RUNS and setting.evidence == m["evidence"] and setting.run == m[protocol.RECORD_HASH],
            "The Setting of this manifest")
    if protocol.is_zebra(m["configuration"]) or protocol.is_alfworld(m["configuration"]):
        workers = functools.partial(sandbox.with_worker, **setting.sandbox, live=setting.slots[slots.LIVE],
                                    per_call=setting.slots[slots.CALL])
        return Services(registry=Registry(m["history_root"], evidence=m["evidence"]), sources=None, workers=workers)
    entry = m["data"].get("research")
    require(isinstance(entry, dict) and set(entry) == RESEARCH_FIELDS, "The data pins bind the research archive")
    archive = research.Archive(entry["archive"])
    require(archive.index_sha256 == entry["index_sha256"], "The research archive differs from the manifest")
    sources = research.Sources(research.Wikipedia(proxy=protocol.GATEWAY, transport=transport), archive,
                               safe_path(setting.root) / "shared" / "research" / chain)
    workers = functools.partial(sandbox.with_worker, **setting.sandbox, live=setting.slots[slots.LIVE],
                                per_call=setting.slots[slots.CALL])
    engine = engines.sheet_engines(setting.runtime["spreadsheetbench"], native=setting.slots[slots.NATIVE],
                                   evidence=m["evidence"])
    return Services(registry=Registry(m["history_root"], evidence=m["evidence"]), sources=sources, workers=workers,
                    engine=engine)


def _check_zebra(value):
    """The profile's experiment and sealed identities, checked by value without opening the panel."""
    from . import zebralogic
    require(value["data"].get("zebra_pc_features") == zebra_features(value["configuration"]), "The ZebraLogic feature family is pinned by value")
    require(value["data"].get("zebra_pc") == zebralogic.identity(), "The ZebraLogic registration is pinned by value")
    if protocol.is_v27(value["configuration"]):
        require(value["data"].get("launchable_chains") == ["D"], "zebra-pc-v5 launches chain D only")
    if value["evidence"] in (SMOKE_EVIDENCE, protocol.REAL_RUN_EVIDENCE[value["configuration"]]):
        require(value["data"]["pools"]["zebralogic"]["sha256"] == zebralogic.POOL_SHA256, "The registered pool hash")
    require(value["cards"] == {"zebralogic": zebralogic.CARD_TEXT}, "The registered grid card is pinned by value")
    require(set(value["runtime"]) == {"zebralogic"}, "The profile has only its grid runtime")
    require(set(value["data"].get("pools", {})) == {"zebralogic"}, "The profile names only its pool")
    require(value["data"].get("pinned") == zebralogic.identity()["sealed"], "The sealed panel identity is pinned externally")
    return value


def zebra_features(configuration=protocol.ZEBRA_PC_V1):
    """The new profile's inherited behavior, benchmark gates and active/read roster by value."""
    p, name = protocol, configuration
    require(p.is_zebra(name), "A registered ZebraLogic configuration")
    tables = ("LEARNING", "FIX_ECHO", "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES",
              "ENGINEER_MAX_TOKENS", "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING",
              "ENGINEER_RECORDS", "IDENTICAL_REQUEST_REUSE", "POLICY_VERSIONS", "CODE_EXTRACTION",
              "MULTIPLE_PYTHON_BLOCKS", "STAGE_READ", "ACCEPT_FRESHNESS")
    return _plain({"family": p.FEATURE_FAMILIES[name], "features": {key: getattr(p, key)[name] for key in tables},
                   "configuration": p.CONFIGURATIONS[name], "active": p.active_benches(name),
                   "read": p.read_benches(name), "namespaces": p.CHAIN_NAMESPACES[name],
                   "slices": p.SLICES["zebralogic"], "g_acc": p.G_ACC["zebralogic"],
                   "mde_points": p.MDE_POINTS["zebralogic"], "note_cap": p.MAX_NOTE_CHARS["zebralogic"],
                   "cell_anchors": p.CELL_ANCHORS["zebralogic"], "bindings": False,
                   "generator": "selection_only", "placebo_i": False, "j7": False,
                   **({"launchable_chains": p.launchable_chains(name)} if p.is_v27(name) else {}),
                   **({"outcome_engineer": outcome_engineer_features(name)} if p.is_v28(name) else {})})


def alfworld_features(configuration=protocol.ALFWORLD_V1):
    """The one-step ALFWorld registration, with the selected feature family pinned by value."""
    p = protocol
    require(p.is_alfworld(configuration), "A registered ALFWorld configuration")
    tables = ("LEARNING", "FIX_ECHO", "META_COUNTERFACTUAL", "TRAIN_SIGN", "PRUNE_NON_FIRING", "ACCEPT_RULES",
              "ENGINEER_MAX_TOKENS", "TRIM_PAYLOADS", "NORMALIZE_STRUCTURE", "CHECK_NON_FIRING",
              "ENGINEER_RECORDS", "IDENTICAL_REQUEST_REUSE", "POLICY_VERSIONS", "CODE_EXTRACTION",
              "MULTIPLE_PYTHON_BLOCKS", "STAGE_READ", "ACCEPT_FRESHNESS")
    return _plain({"family": p.FEATURE_FAMILIES[configuration],
                   "features": {key: getattr(p, key)[configuration] for key in tables},
                   "configuration": p.CONFIGURATIONS[configuration], "active": p.active_benches(configuration),
                   "read": p.read_benches(configuration), "namespaces": p.CHAIN_NAMESPACES[configuration],
                   "launchable_chains": p.launchable_chains(configuration), "slices": p.SLICES["alfworld"],
                   "g_acc": p.G_ACC["alfworld"], "mde_points": p.MDE_POINTS["alfworld"],
                   "note_cap": p.MAX_NOTE_CHARS["alfworld"], "cell_anchors": p.CELL_ANCHORS["alfworld"],
                   "max_steps": p.ALFWORLD_MAX_STEPS, "routing_view": p.ALFWORLD_ROUTING_VIEW,
                   "generator": "selection_only", "placebo_i": False, "j7": False, "notes_coverage": False,
                   **({"outcome_engineer": outcome_engineer_features(configuration)}
                      if p.is_v28(configuration) else {})})



def outcome_engineer_features(configuration):
    """V2.8 execution and admission contract, pinned only for new configurations."""
    require(protocol.is_v28(configuration), "A v2.8 configuration")
    return {
        "source_bytes": policy.source_limit(protocol.POLICY_VERSIONS[configuration]),
        "single_call_budget": protocol.ENGINEER_CALL_BUDGETS[configuration],
        "train_call_budget": protocol.TRAIN_ENGINEER_CALL_BUDGETS[configuration],
        "train_fixes": protocol.TRAIN_FIXES, "format_retries_per_reply": 1,
        "hashseed": protocol.V28_HASHSEED, "namespace": "fresh_per_item_or_episode",
        "replay_tests": "advisory", "replay_mismatches": "information",
        "faults": "no_note_on_item", "inert": "skip_training",
        "lexicon": "drop_reply_form_directives_only",
        "note_screen_sha256": notes.v28_screen_sha256(),
        "train_fault_guards": "information", "acceptance_j3": "information",
    }


def alfworld_registration_key(configuration):
    """The configuration's preparation metadata field; v1 retains its original schema."""
    require(protocol.is_alfworld(configuration), "A registered ALFWorld configuration")
    return ("alfworld_v3" if protocol.is_v28(configuration) else
            "alfworld_v2" if protocol.is_alfworld_v2(configuration) else "alfworld_v1")


def _check_alfworld(value):
    """Validate the preparation metadata linkage, without opening any test or pool file."""
    data = value["data"]
    label = ("ALFWorld v3" if protocol.is_v28(value["configuration"]) else
             "ALFWorld v2" if protocol.is_alfworld_v2(value["configuration"]) else "ALFWorld v1")
    require(data.get("alfworld_features") == alfworld_features(value["configuration"]),
            "The ALFWorld feature family is pinned by value")
    require(set(value["runtime"]) == set(value["contracts"]) == set(data.get("pools", {})) == {"alfworld"},
            "The profile names only ALFWorld runtime, contract and pool")
    require(value["sheet_qualification"] is None, label + " has no spreadsheet qualification")
    require(data.get("launchable_chains") == ["D"], label + " launches only chain D")
    require("research" not in data and "zebra_pc" not in data and "searchqa_tail" not in data,
            label + " has no unrelated benchmark data or research services")
    registered = data.get(alfworld_registration_key(value["configuration"]))
    require(isinstance(registered, dict) and set(registered) == {
        "preparation", "card_sha256", "contract_sha256", "runtime_sha256", "pool", "test", "split"},
        label + " binds the main preparation metadata")
    source = registered["preparation"]
    require(isinstance(source, dict) and set(source) == {"path", "sha256", "record_sha256"}
            and type(source["path"]) is str and source["path"]
            and all(_sha_text(source[key]) for key in ("sha256", "record_sha256")),
            "The main preparation file and record are pinned")
    for name in ("pool", "test", "split"):
        entry = registered[name]
        require(isinstance(entry, dict) and set(entry) == {"path", "sha256"}
                and type(entry["path"]) is str and entry["path"] and _sha_text(entry["sha256"]),
                "The ALFWorld %s identity is pinned" % name)
    card = value["cards"]["alfworld"]
    require(registered["card_sha256"] == hashlib.sha256(card.encode()).hexdigest(),
            "The ALFWorld card differs from its preparation pin")
    contract = value["contracts"]["alfworld"]
    require(isinstance(contract, dict) and set(contract) == {"text", "sha"}
            and type(contract["text"]) is str
            and contract["sha"] == registered["contract_sha256"] == hashlib.sha256(contract["text"].encode()).hexdigest(),
            "The ALFWorld contract differs from its preparation pin")
    require(registered["runtime_sha256"] == digest(value["runtime"]["alfworld"]),
            "The ALFWorld runtime differs from its preparation pin")
    require(data["pools"]["alfworld"] == registered["pool"], "The ALFWorld pool differs from its preparation pin")
    require(data.get("pinned") == {
        "paths": {"split": registered["split"]["path"], "test": {"alfworld": registered["test"]["path"]}},
        "sha256": {registered[key]["path"]: registered[key]["sha256"] for key in ("split", "test")}},
        "The ALFWorld test read has only its preparation split and test pins")
    if value["evidence"] in (SMOKE_EVIDENCE, protocol.REAL_RUN_EVIDENCE[value["configuration"]]):
        chars, prefix = ALFWORLD_CARD_IDENTITY
        require(len(card) == chars and registered["card_sha256"].startswith(prefix),
                "The frozen imported ALFWorld card")
    return value


def _sha_text(value):
    return type(value) is str and len(value) == 64 and set(value) <= set("0123456789abcdef")
