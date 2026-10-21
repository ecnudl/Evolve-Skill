"""Before launch (registration §0, §2.1, §6, §7, §14 steps 5-7): the inputs the launch manifest freezes, and the
manifest itself. Run on the launch snapshot -- a checkout nobody edits while the run lasts -- with the interpreter the
chains will use (the manifest binds its Python and openpyxl), in one pre-launch directory P, in this order:

1. the SpreadsheetBench engine qualification for the snapshot (``scripts.replay_sheet_v6 qualify``, zero calls: the
   frozen v7 scorer binds the code path it was qualified from, §20.2), read by ``engine_runtime``;
2. ``qualify_training_sheet``: the training-side reference qualification (§2.1), zero model calls;
3. ``build_archive``: the research archive (§7) -- the fixed public documentation pages (``ARCHIVE_PAGES``; a redirect
   or any response but 200 stops) and the five public task cards; v2 (delta §8): the v1 archive's pages carried over
   byte for byte, the LibreOffice Calc help pages added;
4. ``prepare_texts`` in P/<name>: the five task-card instructions (the three existing generations, verified; the two
   missing ones written once each) and the six initial rubrics (§6), GLM-5.3; the first text that could not be written
   stops the preparation -- no further call -- and the owner decides (§22). v2 (delta §11): ``import_texts`` instead,
   the v1 texts verified in place under the rules they were written by and recorded in P/<name>, zero calls;
5. the smoke (``smoke.py``, §14 step 5) in P/<name>;
6. ``generate``: the launch manifest, zero calls -- the pinned data, the qualification with the regression panels and
   tolerances it implies, the texts, the runtime, the clients, the archive, the baselines' learning setup, the code map,
   the interpreter and every input's provenance -- once each input is checked against its source: the texts re-derived
   from their recorded replies under the current prompts and role settings (``verify_texts``), the archive against its
   registered roster (``check_archive``), the baselines' protocol (study F's) and learning model against the solver's
   (§11, ``baseline_settings``), both historical partitions of every baseline stage (§2.1: otherwise no launch), the I
   chains' starting Skill (§3) and the completed smoke; checked by loading it (which creates the run's empty ledger and
   slot directories);
7. ``check-baselines`` (``baseline.check``, zero calls): its record in the run is required before any chain runs;
8. ``record_consent``: the owner's consent to the test sets, verbatim, in the run's shared directory (§0).

Every GLM-5.3 call before the run -- every attempt of the texts and of the smoke -- is reserved and settled in P/ledger,
a ``budget.Budget`` like the run's (overall cap ``PRELAUNCH_CAP``): a breached reservation assumption halts it, and the
generator refuses while it is halted or a pre-launch process still holds a reservation. Its total is recorded in the
manifest and comes off the run's overall cap (§13.3 covers every coevo5 GLM-5.3 call, the smoke included).
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from copy import deepcopy
from types import SimpleNamespace

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import baseline, data, manifest, qualify, research, texts
from .budget import OVERALL, Budget
from .calls import Endpoint, Slots, _request_hash
from .examiner import GENERAL
from .protocol import (
    ANALYST_ATTEMPTS,
    BASELINE_BUDGET,
    BASELINE_PROTOCOL,
    DATA_SEED,
    ORDER,
    ROLE_MAX_TOKENS,
    ROLE_MODEL,
    ROLE_READ_TIMEOUT_SECONDS,
    RUNTIME,
    SLOTS,
    SOLVER_MAX_TOKENS,
    TITLES,
    TOLERANCE_FOCAL,
    TOLERANCE_REGRESSION,
    VERSION,
    M,
)
from .roles import Roles, parse
from .skill import Skill
from .units import CHAINS

EXISTING = ("searchqa", "officeqa", "livemath")  # instructions written before, from the same prompt and card
# The records an existing instruction comes from: the zero-shot generator's (scripts/generate_zero_shot_skill.py, which
# names its bench) and the OfficeQA and LiveMath headroom pilots' zero-shot generations (scripts/pilot_officeqa_headroom.py
# and its LiveMath twin; the same prompt, GLM-5.3), which name none: the card in the prompt identifies the bench.
EXISTING_VERSIONS = {"searchqa": ("zero-shot-initial-skill-v1",),
                     "officeqa": ("zero-shot-initial-skill-v1", "officeqa-headroom-pilot-v1:zero-shot"),
                     "livemath": ("zero-shot-initial-skill-v1", "livemath-headroom-pilot-v1:zero-shot")}
WRITTEN = ("spreadsheetbench", "alfworld")
PYTHON_DOCS = "https://docs.python.org/3.11/library/%s.html"
# the newest openpyxl documentation published (3.1.3); the sandbox has 3.1.5 (requirements-native.txt), a bug-fix
# release of the same API whose documentation was not published separately
OPENPYXL_DOCS = "https://openpyxl.readthedocs.io/en/3.1.3/%s.html"
OPENPYXL_PAGES = {"tutorial": "Tutorial", "usage": "Simple usage", "editing_worksheets": "Editing worksheets",
                  "formula": "Parsing formulas", "datetime": "Dates and times", "styles": "Working with styles",
                  "formatting": "Conditional formatting", "worksheet_tables": "Worksheet tables",
                  "filters": "Using filters and sorts", "validation": "Validating cells"}
# v2 delta §8: the help of the SpreadsheetBench recalculation engine's release (LibreOffice 25.2.3 in the image; the help
# is published per release branch): function syntax and the formula semantics the engine applies to the outputs
CALC_HELP = "https://help.libreoffice.org/25.2/en-US/text/%s.html"
CALC_PREFIX = "libreoffice-calc-25.2-"  # v2's added pages; every other page is carried from v1's archive
CALC_PAGES = {
    "spreadsheet-functions": ("scalc/01/04060109", "Spreadsheet Functions (lookup and reference)"),
    "logical-functions": ("scalc/01/04060105", "Logical Functions"),
    "information-functions": ("scalc/01/04060104", "Information Functions"),
    "mathematical-functions": ("scalc/01/04060106", "Mathematical Functions"),
    "array-functions": ("scalc/01/04060107", "Array Functions"),
    "statistical-functions-part1": ("scalc/01/04060181", "Statistical Functions Part One"),
    "statistical-functions-part3": ("scalc/01/04060183", "Statistical Functions Part Three"),
    "statistical-functions-part4": ("scalc/01/04060184", "Statistical Functions Part Four"),
    "statistical-functions-part5": ("scalc/01/04060185", "Statistical Functions Part Five"),
    "text-functions": ("scalc/01/04060110", "Text Functions"),
    "date-time-functions": ("scalc/01/04060102", "Date & Time Functions"),
    "operators": ("scalc/01/04060199", "Operators in LibreOffice Calc"),
    "wildcards-in-formulas": ("scalc/guide/wildcards", "Using Wildcards in Formulas"),
    "converting-text-to-numbers": ("scalc/guide/numbers_text", "Converting Text to Numbers"),
    "empty-cells": ("scalc/05/empty_cells", "Handling of Empty Cells"),
    "options-calculate": ("shared/optionen/01060500", "Calc Options - Calculate (wildcards, regular expressions, "
                                                      "whole-cell match, case sensitivity)"),
    "options-detailed-calculation": ("shared/optionen/detailedcalculation",
                                     "Calc Options - Detailed Calculation Settings (text-to-number conversion)"),
    "regular-expressions-list": ("shared/01/02100001", "List of Regular Expressions"),
    **{"func-" + f.lower(): ("scalc/01/func_" + f.lower(), f + " Function") for f in (
        "SUMIF", "SUMIFS", "COUNTIFS", "AVERAGEIF", "AVERAGEIFS", "XLOOKUP", "XMATCH", "IFS", "TEXT", "SEARCH",
        "TEXTJOIN", "DATEDIF", "WEEKDAY", "LEFT", "RIGHT", "MID", "LEN", "FIND", "SUBSTITUTE", "TRIM", "VALUE",
        "CONCATENATE", "CONCAT", "DATE", "YEAR", "MONTH", "DAY", "EOMONTH", "EDATE", "NETWORKDAYS", "SUM",
        "ROUNDDOWN")},
}
ARCHIVE_PAGES = {  # §7: fixed public documentation, no benchmark paper or dataset page
    **{"python-3.11-%s.html" % m: (PYTHON_DOCS % m, "Python 3.11 documentation: %s" % m)
       for m in ("decimal", "fractions", "math", "statistics", "datetime", "re")},
    **{"openpyxl-3.1.3-%s.html" % p: (OPENPYXL_DOCS % p, "openpyxl 3.1.3 documentation: %s" % title)
       for p, title in OPENPYXL_PAGES.items()},
    **{CALC_PREFIX + "%s.html" % slug: (CALC_HELP % path, "LibreOffice 25.2 Help: " + title)
       for slug, (path, title) in CALC_PAGES.items()},
}
CARRIED = "carried.json"  # v2: the previous archive and the pages taken from it
CARDS = {"card-%s.txt" % b: b for b in ORDER}  # the archived public task cards
CARD_SOURCE = "skillopt/coevo5/texts.py CARDS"
TOLERANCE_RULE = manifest.REPO / "docs" / "handoff" / "coevo5_power_sim_v2.py"  # data.sheet_tolerances runs it
LEDGER = "ledger"  # the pre-launch ledger, P/ledger
PRELAUNCH_CAP = 30 * M  # every GLM-5.3 call before the run: the texts and the smoke (its chain's learning caps, 13M)
TEXTS_SCOPE, TEXTS_CAP = "prelaunch:texts", 5 * M  # one preparation: at most 14 calls, each reserved at about 0.1M
SMOKE_RECORD, SMOKE_SUMMARY = "smoke.json", "summary.json"
TEXTS_VERSION = VERSION + "-texts"  # texts this version's ``prepare_texts`` wrote
IMPORTABLE = ("fivebench-coevolution-v1-texts",)  # v2 delta §11: texts written by v1, taken over unchanged
IMPORT_VERSION = VERSION + "-texts-import"
BASELINE_SOLVER = CHAINS["SkillOpt-glm"]["solver"]


def engine_runtime(qualification):
    """The frozen runtime (``protocol.RUNTIME``) with the SpreadsheetBench recalculation engine qualified for this
    snapshot: the qualification's path, file hash and record hash (the frozen adapter checks all three)."""
    path = safe_path(qualification)
    record = read_json(path, sealed=True)
    runtime = deepcopy(RUNTIME)
    runtime["spreadsheetbench"]["recalculation"].update(
        qualification_path=str(path), qualification_sha256=data.sha(path), qualification_hash=record["record_hash"])
    return runtime


def qualify_training_sheet(pinned, runtime, out):
    """§2.1, training side: every SpreadsheetBench training-pool item's references scored twice in ``out``/sheet
    (zero model calls; the native slots in ``out``/slots). Returns the sealed record."""
    out = safe_path(out)
    out.mkdir(parents=True)
    native = Slots(out / "slots", "spreadsheet-native", SLOTS["spreadsheet-native"])
    return qualify.qualify(data.pool(pinned, "spreadsheetbench"), out / "sheet", runtime["spreadsheetbench"],
                           side="train", native=native, workers=SLOTS["spreadsheet-native"])


# ---------------------------------------------------------------------------------------------------- archive
class _Refused(urllib.request.HTTPRedirectHandler):
    """A redirect is refused before any second request: the 3xx response itself raises (``HTTPError``)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetcher(proxy):
    """``fetch(url) -> bytes`` through the explicit ``proxy`` only (no environment proxy); a redirect or any response
    but 200 stops."""
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy} if proxy else {}), _Refused)

    def fetch(url):
        request = urllib.request.Request(url, headers={"User-Agent": research.USER_AGENT})
        with opener.open(request, timeout=60) as response:
            require(response.status == 200 and response.geturl() == url, "Unexpected response for " + url)
            return response.read()
    return fetch


def build_archive(out, *, fetch, previous=None):
    """§7: every fixed page downloaded once and the five public task cards, indexed by SHA-256 in a new directory
    (``sources.json``: each page's address). v2 (delta §8): ``previous``, an archive built before -- each of its pages
    registered at the same address is carried over byte for byte (as its index holds it) and only the other pages are
    downloaded; ``carried.json`` names the previous archive, its index hash and the pages taken from it. Returns the
    opened ``research.Archive``."""
    out = safe_path(out)
    require(not out.exists(), "The archive goes to a new directory")
    old = None if previous is None else research.Archive(previous)  # every page checked against its index
    before = {} if old is None else read_json(old.root / "sources.json")
    carried = sorted(n for n, (url, _) in ARCHIVE_PAGES.items() if old is not None and n in old.hashes
                     and before.get(n) == url)
    files = {}
    for name, (url, title) in sorted(ARCHIVE_PAGES.items()):
        if name in carried:
            raw = (old.root / name).read_bytes()
            require(hashlib.sha256(raw).hexdigest() == old.hashes[name], "A carried page changed: " + name)
            files[name] = (raw, title)
        else:
            files[name] = (fetch(url), title)
    files.update({name: (texts.CARDS[b].encode("utf-8"), "Public task card: " + TITLES[b]) for name, b in CARDS.items()})
    for raw, _ in files.values():
        raw.decode("utf-8")  # every archived document is UTF-8 text
    out.mkdir(parents=True)
    index, sources = {}, {}
    for name, (raw, title) in files.items():
        (out / name).write_bytes(raw)
        index[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "title": title}
        sources[name] = ARCHIVE_PAGES[name][0] if name in ARCHIVE_PAGES else CARD_SOURCE
    (out / "index.json").write_text(json.dumps(index, indent=1, sort_keys=True), encoding="utf-8")
    write_json(out / "sources.json", sources)
    if old is not None:
        write_json(out / CARRIED, {"archive": str(old.root), "index_sha256": old.index_sha256, "pages": carried})
    return research.Archive(out)


def check_archive(directory, *, carried=False):
    """§7: an archive holds exactly the registered documents -- each fixed page from its registered address, the five
    cards as registered -- each with its indexed hash. v2 (delta §8): a ``carried.json`` names every registered page
    the previous archive holds at the same address (``build_archive``), each still the previous archive's bytes, and
    never fewer than every page outside the Calc help (v1's); v3 (delta §11): built from v2's archive, it carries the
    Calc help too. ``carried`` (the launch) requires one. Returns (the opened ``research.Archive``, the SHA-256 of its
    sources record, which the manifest binds)."""
    opened = research.Archive(directory)
    require(set(opened.texts) == set(ARCHIVE_PAGES) | set(CARDS), "The archive holds other documents than §7's")
    require(all((opened.root / name).read_bytes() == texts.CARDS[b].encode("utf-8") for name, b in CARDS.items()),
            "An archived task card differs from the registered card")
    expected = {**{name: url for name, (url, _) in ARCHIVE_PAGES.items()}, **{name: CARD_SOURCE for name in CARDS}}
    require(read_json(opened.root / "sources.json") == expected, "The archive's addresses differ from §7's")
    found = opened.root / CARRIED
    require(found.exists() or not carried, "The v2 archive carries the previous archive's pages (--previous)")
    if found.exists():  # v2: each carried page is still the previous archive's
        record = read_json(found)
        old = research.Archive(record["archive"])
        before = read_json(old.root / "sources.json")
        held = sorted(n for n, (url, _) in ARCHIVE_PAGES.items() if n in old.hashes and before.get(n) == url)
        require(record["pages"] == held and {n for n in ARCHIVE_PAGES if not n.startswith(CALC_PREFIX)} <= set(held),
                "The archive does not carry every page of the previous archive")
        require(old.index_sha256 == record["index_sha256"]
                and all(opened.hashes[n] == old.hashes.get(n) for n in record["pages"]),
                "A carried page differs from the previous archive's")
    return opened, data.sha(opened.root / "sources.json")


# ------------------------------------------------------------------------------------------------------ texts
def ledger_of(directory):
    """The pre-launch ledger of a texts or smoke directory: ``ledger`` beside it, in the pre-launch directory."""
    return safe_path(directory).parent / LEDGER


def prelaunch_budget(directory, caps):
    """The pre-launch ledger of ``directory``, with ``caps`` declared beside its overall cap."""
    budget = Budget(ledger_of(directory))
    budget.declare({OVERALL: PRELAUNCH_CAP, **caps})
    return budget


def _existing(directory, bench):
    """An existing instruction: its completed generation by GLM-5.3, written from this card by this prompt."""
    from scripts import generate_zero_shot_skill as generator

    path, sha = generator.check(directory)
    record = read_json(safe_path(directory) / "generation.json", sealed=True)
    system, user = texts.instruction_prompt(bench)
    require(record.get("version") in EXISTING_VERSIONS[bench] and record.get("benchmark", bench) == bench
            and record.get("system") == system and record.get("user") == user,
            "The existing %s instruction was not written from this card by this prompt" % bench)
    require((record.get("learning_model_service") or {}).get("model") == ROLE_MODEL,
            "The existing %s instruction was not written by %s" % (bench, ROLE_MODEL))
    return path.read_text(encoding="utf-8"), {"source": "existing", "directory": str(safe_path(directory)),
                                              "version": record["version"], "skill_sha256": sha,
                                              "generation_hash": record["record_hash"]}


def prepare_texts(out, existing, client):
    """§0, §1, §6 in a new directory of the pre-launch directory: ``texts.json`` (the five instructions, the six initial
    rubrics, the cards they were written from, each text's provenance, the texts not written) and ``roles.json``
    (every call's record, written also when a stop of the calls is raised). ``existing``: {bench: generation
    directory} of the three existing instructions; ``client``: the GLM-5.3 client of the method roles, its calls
    charged to the pre-launch ledger. The first text that could not be written stops the preparation (§22)."""
    require(set(existing) == set(EXISTING), "The three existing instructions")
    found = {bench: _existing(existing[bench], bench) for bench in EXISTING}
    out = safe_path(out)
    out.mkdir(parents=True)
    budget = prelaunch_budget(out, {TEXTS_SCOPE: TEXTS_CAP})
    instructions = {bench: text for bench, (text, _) in found.items()}
    provenance = {bench: source for bench, (_, source) in found.items()}
    roles = Roles(Endpoint(client, model=ROLE_MODEL, max_tokens=ROLE_MAX_TOKENS,
                           slots=Slots(out.parent / "slots", ROLE_MODEL, SLOTS[ROLE_MODEL]), budget=budget,
                           scopes=(OVERALL, TEXTS_SCOPE)))
    rubrics, stopped = {}, None
    try:
        for bench in WRITTEN:  # written once each, never selected among alternatives
            label = "pre/instruction/" + bench
            instructions[bench] = texts.write_instruction(roles, bench, label=label)
            provenance[bench] = {"source": "written", "label": label}
            if instructions[bench] is None:
                stopped = "instruction:" + bench
                break
        for scope in (*ORDER, GENERAL) if stopped is None else ():
            rubrics[scope] = texts.write_rubric(roles, scope, label="pre/rubric/" + scope)
            if rubrics[scope] is None:
                stopped = "rubric:" + scope
                break
    finally:
        write_json(out / "roles.json", roles.calls)
    missing = (["instruction:" + b for b in WRITTEN if instructions.get(b) is None]
               + ["rubric:" + s for s in (*ORDER, GENERAL) if rubrics.get(s) is None])
    record = seal({"version": TEXTS_VERSION, "cards": texts.CARDS,
                   "instructions": {b: instructions.get(b) for b in ORDER}, "rubrics": rubrics,
                   "provenance": provenance, "missing": missing, "stopped": stopped, "ledger": str(ledger_of(out)),
                   "roles_sha256": data.sha(out / "roles.json")})
    write_json(out / "texts.json", record)
    return record


def _expected_calls():
    """{label: (role, request hash)} of every call a preparation may make under the current prompts."""
    expected = {}
    for bench in WRITTEN:
        system, user = texts.instruction_prompt(bench)
        expected["pre/instruction/" + bench] = ("instruction_writer", _request_hash(system, user))
    for scope in (*ORDER, GENERAL):
        system, payload = texts.rubric_prompt(scope)
        request = _request_hash(system, json.dumps(payload, ensure_ascii=False, sort_keys=True))
        for attempt in range(1, ANALYST_ATTEMPTS + 1):
            expected["pre/rubric/%s/attempt%d" % (scope, attempt)] = ("rubric_writer", request)
    return expected


def _reply(call):
    return call["sends"][-1]["receipt"]["response"]


def verify_texts(path):
    """The pre-launch texts of this version: written by ``prepare_texts`` (``_verify_written``) or imported
    (``import_texts``) -- the import's source verified again, the texts still the source's, the import charged to the
    ledger beside it (the smoke's). Returns the sealed record (an import's: its own, naming the source)."""
    path = safe_path(path)
    record = read_json(path, sealed=True)
    if record["version"] != IMPORT_VERSION:
        return _verify_written(path, (TEXTS_VERSION,))
    source = record["imported"]
    found = _verify_written(source["path"], IMPORTABLE)
    require(found["record_hash"] == source["record_hash"] and found["version"] == source["version"]
            and found["ledger"] == source["ledger"] and record["ledger"] == str(ledger_of(path.parent))
            and all(record[k] == found[k] for k in ("cards", "instructions", "rubrics")),
            "The imported texts differ from their source or are charged elsewhere")
    return record


def import_texts(out, source):
    """v2 delta §11: the v1 pre-launch texts taken over unchanged -- verified in place under the rules they were
    written by (their prompts, cards and role settings are this version's too) and recorded with their path, version,
    ledger and record hash in a new directory ``out`` of the v2 pre-launch directory. No call; the source is neither
    rewritten nor relabelled. Returns the sealed record."""
    out = safe_path(out)
    require(not out.exists(), "The import goes to a new directory")
    source = safe_path(source)
    found = _verify_written(source, IMPORTABLE)
    out.mkdir(parents=True)
    record = seal({"version": IMPORT_VERSION, "cards": found["cards"], "instructions": found["instructions"],
                   "rubrics": found["rubrics"], "ledger": str(ledger_of(out)),
                   "imported": {"path": str(source), "record_hash": found["record_hash"],
                                "version": found["version"], "ledger": found["ledger"],
                                "provenance": found["provenance"], "roles_sha256": found["roles_sha256"]}})
    write_json(out / "texts.json", record)
    return record


def _verify_written(path, versions):
    """Texts as ``prepare_texts`` writes them (§0, §22), of one of ``versions``: complete, from the registered cards;
    every recorded call made under the current prompts and role settings and charged to a ledger; each written text the
    one its recorded reply gives (a rubric: its scope's last attempt, the only valid one); each existing instruction
    still its completed generation's. Returns the sealed record."""
    path = safe_path(path)
    written = read_json(path, sealed=True)
    require(written["version"] in versions and not written["missing"] and written["stopped"] is None
            and written["cards"] == texts.CARDS and list(written["instructions"]) == list(ORDER)
            and set(written["rubrics"]) == {*ORDER, GENERAL} and written["ledger"] == str(ledger_of(path.parent)),
            "The pre-launch texts are incomplete, were written from other cards or charged elsewhere")
    require(data.sha(path.parent / "roles.json") == written["roles_sha256"], "The texts lost their calls' record")
    for bench in EXISTING:
        text, source = _existing(written["provenance"][bench]["directory"], bench)
        require(text == written["instructions"][bench] and source == written["provenance"][bench],
                "The existing %s instruction differs from its generation" % bench)
    expected, calls = _expected_calls(), read_json(path.parent / "roles.json")
    labels = [call["label"] for call in calls]
    require(len(set(labels)) == len(labels) and set(labels) <= set(expected), "Calls the preparation never makes")
    for call in calls:
        role, request = expected[call["label"]]
        require(call["role"] == role and call["request_sha256"] == request and call["sends"]
                and all(send["model"] == ROLE_MODEL and send["max_tokens"] == ROLE_MAX_TOKENS
                        and send["request_sha256"] == request and "charged" in send for send in call["sends"]),
                "A pre-launch call made under other prompts or settings: " + call["label"])
    by_label = {call["label"]: call for call in calls}
    for bench in WRITTEN:
        call = by_label.get("pre/instruction/" + bench)
        require(call is not None and call["valid"] and texts.instruction_text(_reply(call)) == written["instructions"][
            bench] and written["provenance"][bench] == {"source": "written", "label": call["label"]},
                "The %s instruction is not its recorded reply" % bench)
    for scope in (*ORDER, GENERAL):
        tried = [by_label[label] for label in ("pre/rubric/%s/attempt%d" % (scope, n)
                                               for n in range(1, ANALYST_ATTEMPTS + 1)) if label in by_label]
        require(tried and tried[-1]["valid"] and not any(call["valid"] for call in tried[:-1])
                and texts._rubric(scope)(parse(_reply(tried[-1]))) == written["rubrics"][scope],
                "The %s rubric is not its recorded reply" % scope)
    return written


# ---------------------------------------------------------------------------------------------------- manifest
def tolerances(pools):
    """(t_k by bench, {bench: {"items", "tolerance": t_b}}) by the registered rules (§2.1, §5.5) from the actual pools
    (SpreadsheetBench: its qualified items); a bench without a regression panel has no t_b, and SpreadsheetBench below
    the qualified minimum has neither."""
    focal, regression = {}, {}
    for bench in ORDER:
        items = [item["task_id"] for item in data.regression_items(pools[bench], bench, DATA_SEED)]
        t_k, t_b = TOLERANCE_FOCAL[bench], TOLERANCE_REGRESSION.get(bench)
        if bench == "spreadsheetbench":
            t_k, t_b = data.sheet_tolerances(len(pools[bench])) or (None, None)
        focal[bench] = t_k
        regression[bench] = {"items": items, "tolerance": t_b if items else None}
    return focal, regression


def prior_usage(directory):
    """GLM-5.3 tokens spent before the run (§13.3: the overall cap covers every coevo5 GLM-5.3 call, the smoke
    included): the pre-launch ledger's overall total -- every attempt's calls, a reservation whose process ended
    without a receipt at its whole amount. Refused while a pre-launch process still holds a reservation, or while the
    ledger is halted (a breached reservation assumption, a ledger failure: the owner decides, §13.4)."""
    budget = Budget(directory)
    require(budget.close_orphans() == 0, "A pre-launch process still holds reservations")
    found = budget.snapshot()
    require("halted" not in found, "The pre-launch ledger is halted: the owner decides first (§13.4)")
    require(OVERALL in found, "No pre-launch ledger at " + str(directory))
    return {"ledger": str(safe_path(directory)), "total": found[OVERALL]["settled"]}


def baseline_settings(protocol):
    """§11: the baselines' learning model and frozen service -- study F's protocol, as registered -- checked item by
    item against the GLM-5.3 solver's (``scripts.weak_solver_probe``, which also sends temperature 0): provider,
    model, reasoning effort, thinking, temperature and output cap (the frozen learner's truncation recovery apart).
    Returns the compared settings."""
    from scripts.weak_solver_probe import MODELS

    require(protocol["record_hash"] == BASELINE_PROTOCOL, "Not study F's protocol (§11)")
    backend, thinking, effort, _, _ = MODELS[BASELINE_SOLVER]
    model, service = protocol["model"], protocol["learning_model_service"]
    pairs = {"provider": (model["provider"], backend), "model": (model["name"], BASELINE_SOLVER),
             "service_model": (service["model"], BASELINE_SOLVER), "reasoning_effort": (model["reasoning_effort"], effort),
             "service_reasoning_effort": (service["reasoning_effort"], effort),
             "thinking": (service["thinking"], {"type": thinking}), "temperature": (service["temperature"], 0),
             "max_tokens": (model["max_tokens"], SOLVER_MAX_TOKENS[BASELINE_SOLVER]),
             "learner_max_tokens": (BASELINE_BUDGET["solver_max_tokens"], SOLVER_MAX_TOKENS[BASELINE_SOLVER])}
    differ = sorted(name for name, (found, solver) in pairs.items() if found != solver)
    require(not differ, "The baselines' learning model differs from the solver's: %s" % differ)
    return {name: found for name, (found, _) in pairs.items()}


def _smoke(directory, ledger, code):
    """§14 step 5: the smoke before this launch, charged to the same pre-launch ledger and complete; with the files
    changed since it ran (each returns to its batch's review, §14)."""
    directory = safe_path(directory)
    spec = read_json(directory / SMOKE_RECORD, sealed=True)
    summary = read_json(directory / SMOKE_SUMMARY)
    require(spec["version"] == VERSION + "-smoke" and ledger_of(directory) == ledger
            and summary["run"] == spec["record_hash"] and summary["status"] == "complete",
            "The smoke did not complete in this pre-launch directory")
    changed = sorted(name for name in set(spec["code"]) | set(code) if spec["code"].get(name) != code.get(name))
    return {"path": str(directory), "record_hash": spec["record_hash"], "chain": spec["chain"],
            "status": summary["status"], "changed_since": changed}


def generate(out, *, root, sheet_qualification, engine_qualification, texts_record, smoke, archive, baseline_protocol,
             repo, gepa_source, proxy, research_proxy, workers, deepseek_env, router_env=None, data_config=None):
    """The launch manifest at ``out`` for a run in the new directory ``root`` (zero calls); ``smoke``: the smoke's
    directory. Returns the sealed manifest, after loading it with the code check."""
    out, root = safe_path(out), safe_path(root)
    require(not out.exists() and not root.exists(), "A new manifest for a run in a new directory")
    pinned = data.pin(deepcopy(data.DEV_MACHINE if data_config is None else data_config))
    runtime = engine_runtime(engine_qualification)
    for bench in ORDER:
        state = backends.readiness(bench, runtime[bench])
        require(state["status"] == "ready", "%s is not ready: %s" % (bench, state.get("reason")))
    pools = {b: data.pool(pinned, b) for b in ORDER}
    sheet = qualify.load(sheet_qualification)
    require(sheet["side"] == "train" and sheet["recalculation"] == runtime["spreadsheetbench"]["recalculation"]
            and sheet["task_hashes"] == {t["task_id"]: digest(t) for t in pools["spreadsheetbench"]},
            "The training-side qualification belongs to other items or another engine")
    pools["spreadsheetbench"] = data.qualified(pools["spreadsheetbench"], sheet)
    feasible = SimpleNamespace(extra={"pinned": pinned}, pools=pools)
    for bench in ORDER:  # §2.1: every baseline stage has historical train and val items, else no launch
        baseline.learning_panel(feasible, bench)
    focal, regression = tolerances(pools)
    written = verify_texts(texts_record)
    Skill.seeded(written["instructions"])  # §3: the I chains' start is five nonblank seeds within the Skill limit
    ledger = ledger_of(safe_path(texts_record).parent)
    code = manifest.pin_code()
    ran = _smoke(smoke, ledger, code)
    prior = prior_usage(ledger)
    opened, sources = check_archive(archive, carried=True)
    protocol = read_json(baseline_protocol, sealed=True)
    settings = baseline_settings(protocol)
    value = {
        "version": VERSION + "-manifest", "root": str(root), "data": pinned,
        "sheet_qualification": {"path": str(safe_path(sheet_qualification)), "record_hash": sheet["record_hash"]},
        "regression": regression, "tolerance": focal, "cards": texts.CARDS, "instructions": written["instructions"],
        "rubrics": written["rubrics"], "runtime": runtime,
        "clients": manifest.client_config(repo, proxy, deepseek_env=deepseek_env, router_env=router_env),
        "research": {"archive": str(opened.root), "index_sha256": opened.index_sha256, "sources_sha256": sources,
                     "proxy": research_proxy},
        "baseline": {"model": protocol["model"], "service": protocol["learning_model_service"],
                     "repo": str(safe_path(repo)), "gepa_source": str(safe_path(gepa_source))},
        "workers": workers, "code": code,
        "provenance": {
            "texts": {"path": str(safe_path(texts_record)), "record_hash": written["record_hash"],
                      "imported": written.get("imported")},
            "smoke": ran,
            "baseline_protocol": {"path": str(safe_path(baseline_protocol)), "record_hash": protocol["record_hash"]},
            "baseline_settings": settings,
            "tolerance_rule": {"path": str(TOLERANCE_RULE.relative_to(manifest.REPO)), "sha256": data.sha(TOLERANCE_RULE)},
            "sheet_qualification": qualify.summary(sheet), "prior_glm_tokens": prior, **manifest.environment()}}
    record = seal(value)
    write_json(out, record)
    manifest.load(out)
    return record


def record_consent(shared, *, date, note):
    """The owner's consent to read the test sets for evaluation, including the SpreadsheetBench test-side
    qualification (§0, §2.1), written once with the owner's words."""
    require(type(note) is str and note.strip() and type(date) is str and date.strip(), "The owner's words and date")
    value = {"test_evaluation": True, "sheet_test_qualification": True, "by": "owner", "date": date, "note": note}
    write_json(safe_path(shared) / "consent.json", value)
    return value


def role_client(repo, proxy):
    """The GLM-5.3 client of the pre-launch role calls (``scripts/weak_solver_probe.Client``)."""
    from scripts.weak_solver_probe import Client

    return Client(repo, ROLE_MODEL, proxy=proxy, max_tokens=ROLE_MAX_TOKENS, read_timeout=ROLE_READ_TIMEOUT_SECONDS)
