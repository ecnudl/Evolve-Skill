"""The smoke (registration §14 step 5): after the pre-launch texts, before the launch manifest -- training data only,
reduced draws, no evaluation. A chain's units run as a formal chain runs them, every GLM-5.3 call charged to the
pre-launch ledger under the chain's registered caps: chain E-glm (the GLM-5.3 solver and method roles), from its v2
start, the scaffold (v2 §2). v2 (delta §11): two stages, each on the first items of the registered seeded draw
(``DRAW``, ``step.train``'s smaller draw) -- SearchQA (the training execution, the examiner, the analyst with its
evidence, contrast examples and transfer slot, the research rewrite, the OfficeQA-style forward panels, the gate's
rounds with their repeated trigger runs, the merge), then OfficeQA from the Skill it merged, with SearchQA's regression
panel (the parent's two regression runs, the per-item format share, the backward similar check, the LiveMath forward
panels). The v1 smoke's ALFWorld execution is not repeated: v2 leaves that path unchanged. When the first stage's
replies reached no research request or no forward panel, ``paths`` runs them once outside the stage on the analyst's
first proposal (a unit of its own, after the stage's merge): a verify request for its first question (``QUESTION``
when it asked none) with the rewrite on what it found, and its OfficeQA forward panel.

The smoke's records name their own run (the hash of its specification, never a launch manifest's) in its own directory
of the pre-launch directory, and enter no formal chain. ``summary`` reads them (zero calls): per unit its attempts, the
duration of the completed one (its ``started.json`` to the unit record), its cells' final tokens and the tokens charged
for their solver calls, and its role calls (count, valid replies, seconds, charged tokens); which paths the stage reached; the pre-launch ledger; and the files
changed since the smoke's code map (a change returns to its batch's review, §14).

v3 (registration delta §2, §7, §11): chain I-ds (the deepseek solver through the PJLAB token route, every GLM-5.3 method
call charged as before, the solver's tokens to the deepseek scopes of the same ledger), from the instructions. Before
the stages, the format check (``format_check``, zero GLM-5.3 calls): a failed check ends the smoke there
("format_check_failed"; a launch manifest needs a complete smoke). The stages' later units read the self-test's plan;
``paths`` also sends one self-test revision call when the first stage's self-test made none (its reply is recorded,
never tested). The smoke runs on the launch's runtime (the snapshot's engine qualification).
"""
from __future__ import annotations

import json
import os
from collections import Counter
from copy import deepcopy
from fractions import Fraction

from skillopt.coevolution_v5.core import seal
from skillopt.continual_eval import backends
from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import chain, data, examiner, leakage, manifest, prelaunch, qualify, research, step, texts
from .budget import Budget
from .calls import Slots
from .cells import Pause, cell_id, exclusive
from .evaluation import attempts
from .examiner import GENERAL, validate_rubric
from .protocol import (
    DATA_SEED,
    ORDER,
    REQUIRED_FORMAT,
    ROLE_INPUT_BYTES,
    RUNTIME,
    SELFTEST_RUNS,
    SLOTS,
    TOLERANCE_FOCAL,
    TOLERANCE_REGRESSION,
    VERSION,
)
from .roles import Roles, message_bytes
from .skill import Skill
from .units import CHAINS as REGISTERED, Setting, endpoints, run_unit, solver_endpoint, unit_path

CHAIN = "I-ds"  # v3 §11: the deepseek solver, from the instructions
CHAINS = ("I-ds", "E-ds")
BENCHES = ORDER[:2]  # the two stages learned, in order: SearchQA, OfficeQA
FORWARD_TARGET = "officeqa"
DRAW = {"searchqa": 60, "officeqa": 50}
QUESTION = "How does Python's round() function round a number that lies exactly halfway between two integers?"
PATHS = "smoke-paths"
# v3 §2: the format check -- three Skills, the first items of each bench's registered training draw, one run each
FORMAT = "format-check"
FORMAT_BENCHES = ORDER[:4]
FORMAT_ITEMS = 20
FORMAT_FLOOR = Fraction(9, 10)  # a floored Skill's share of answers with the bench's answer form, on every bench
# After two checks (the owner, 2026-10-19 15:1x): the floor binds the method's starts; the empty Skill's share is
# reported and stays the margin's reference (on an unchanged prompt it went from 20/20 to 16/20 between two runs)
FORMAT_FLOORED = ("E", "I")
FORMAT_MARGIN = Fraction(1, 20)  # E's and I's share at most this far below the empty Skill's


def ready():
    """The benches whose runtime the smoke needs: its stages', the second stage's LiveMath forward items, the format
    check's."""
    return tuple(dict.fromkeys((*BENCHES, "livemath", *FORMAT_BENCHES)))


def make(out, *, texts_record, archive, repo, proxy, research_proxy, workers, deepseek_env, router_env=None, draw=None,
         data_config=None, chain_name=CHAIN, engine_qualification=None, sheet_qualification=None):
    """The smoke's specification in a new directory ``out`` of the pre-launch directory (zero calls): its hash names the
    smoke's run. v3: the runtime with the snapshot's engine qualification, and the training-side SpreadsheetBench
    qualification of the format check's items (both required while the check covers SpreadsheetBench). Returns the
    sealed record."""
    out = safe_path(out)
    require(not out.exists(), "A smoke runs in a new directory")
    require(chain_name in CHAINS, "The v3 smoke runs a deepseek learning chain (I-ds, E-ds)")
    draw = dict(DRAW if draw is None else draw)
    require(set(draw) == set(BENCHES) and all(type(n) is int and n > 0 for n in draw.values()), "A draw per bench")
    written = prelaunch.verify_texts(texts_record)
    require(prelaunch.ledger_of(out) == prelaunch.ledger_of(safe_path(texts_record).parent),
            "The smoke and the texts share the pre-launch directory (one ledger)")
    opened, sources = prelaunch.check_archive(archive)
    pinned = data.pin(deepcopy(data.DEV_MACHINE if data_config is None else data_config))
    runtime = deepcopy(RUNTIME) if engine_qualification is None else prelaunch.engine_runtime(engine_qualification)
    sheet = None
    if "spreadsheetbench" in FORMAT_BENCHES:
        require(engine_qualification is not None and sheet_qualification is not None,
                "v3 §2: the format check's SpreadsheetBench items need the engine and training-side qualifications")
        found = qualify.load(sheet_qualification)
        require(found["side"] == "train" and found["recalculation"] == runtime["spreadsheetbench"]["recalculation"]
                and found["task_hashes"] == {t["task_id"]: digest(t) for t in data.pool(pinned, "spreadsheetbench")},
                "The training-side qualification belongs to other items or another engine")
        sheet = {"path": str(safe_path(sheet_qualification)), "record_hash": found["record_hash"]}
    value = {"version": VERSION + "-smoke", "root": str(out), "chain": chain_name, "draw": draw, "data": pinned,
             "runtime": runtime, "sheet_qualification": sheet,
             "texts": {"path": str(safe_path(texts_record)), "record_hash": written["record_hash"]},
             "research": {"archive": str(opened.root), "index_sha256": opened.index_sha256, "sources_sha256": sources,
                          "proxy": research_proxy},
             "clients": manifest.client_config(repo, proxy, deepseek_env=deepseek_env, router_env=router_env),
             "workers": workers, "code": manifest.pin_code(), "environment": manifest.environment()}
    record = seal(value)
    out.mkdir(parents=True)
    write_json(out / prelaunch.SMOKE_RECORD, record)
    return record


def setting(path):
    """(the smoke's specification, its ``Setting``)."""
    spec = read_json(path, sealed=True)
    root = safe_path(spec["root"])
    require(spec["version"] == VERSION + "-smoke" and spec["chain"] in CHAINS
            and safe_path(path) == root / prelaunch.SMOKE_RECORD, "Not a coevo5 smoke")
    written = read_json(spec["texts"]["path"], sealed=True)
    require(written["record_hash"] == spec["texts"]["record_hash"], "The texts differ from the smoke's")
    archive = research.Archive(spec["research"]["archive"])
    require(archive.index_sha256 == spec["research"]["index_sha256"]
            and data.sha(archive.root / "sources.json") == spec["research"]["sources_sha256"],
            "The research archive differs from the smoke's")
    runtime = deepcopy(spec["runtime"])
    for bench in ready():
        state = backends.readiness(bench, runtime[bench])
        require(state["status"] == "ready", "%s is not ready: %s" % (bench, state.get("reason")))

    def sources(store):
        return research.Sources(research.Wikipedia(proxy=spec["research"]["proxy"]), archive, store)

    pools = {b: data.pool(spec["data"], b) for b in dict.fromkeys((*BENCHES, *FORMAT_BENCHES))}
    if "spreadsheetbench" in pools:
        sheet = qualify.load(spec["sheet_qualification"]["path"])
        require(sheet["record_hash"] == spec["sheet_qualification"]["record_hash"],
                "The training-side SpreadsheetBench qualification differs from the smoke's")
        pools["spreadsheetbench"] = data.qualified(pools["spreadsheetbench"], sheet)
    first = BENCHES[0]  # its regression panel as a launch draws it (§2), checked in the second stage
    regression = {first: {"items": [t["task_id"] for t in data.regression_items(pools[first], first, DATA_SEED)],
                          "tolerance": TOLERANCE_REGRESSION[first]}}
    return spec, Setting(
        run=spec["record_hash"], root=root, shared=root / "shared",
        pools=pools, regression=regression, tolerance=dict(TOLERANCE_FOCAL),
        cards=texts.solver_cards(written["cards"], runtime),
        rubrics={s: validate_rubric(written["rubrics"][s], s) for s in (*ORDER, GENERAL)},
        instructions=written["instructions"], runtime=runtime, clients=manifest._clients(spec["clients"]),
        budget=prelaunch.prelaunch_budget(root, {}),
        slots={name: Slots(root.parent / "slots", name, count) for name, count in SLOTS.items()}, sources=sources,
        workers=spec["workers"], extra={"draw": spec["draw"]})


def _plan(root, stage):
    """v3 §7: the record the stage's gate reads -- its self-test's when that ran, else its prepare's (or None)."""
    for name in ("selftest", "prepare"):
        path = unit_path(root, stage, name) / "unit.json"
        if path.exists():
            return read_json(path, sealed=True)
    return None


def _reached(root):
    """{"research": a verify request was dispatched (prepare), "forward": a forward panel was built, "revision": a
    self-test revision call was made (v3: both in the self-test)} in the first stage."""
    path = unit_path(root, 1, "prepare") / "unit.json"
    if not path.exists():
        return {"research": False, "forward": False, "revision": False}
    record = read_json(path, sealed=True)
    found = path.parent / record["attempt"] / "research.json"
    researched = read_json(found) if found.exists() else []
    plan = _plan(root, 1)["result"]
    return {"research": any("log" in q for r in researched for q in r["questions"]),
            "forward": any(r.get("forward") for r in plan.get("rules", [])),
            "revision": "_revision" in (plan.get("selftest") or {})}


def _revise_once(setting, root, chain_name, roles, label):
    """v3 §7: one revision call on the first rule the first stage's self-test ran, with its first-round answers, as the
    self-test sends it; the reply is recorded and never tested."""
    path = unit_path(root, 1, "selftest") / "unit.json"
    if not path.exists():
        return {"status": "no_selftest"}
    record = read_json(path, sealed=True)
    result, attempt, bench = record["result"], path.parent / record["attempt"], ORDER[0]
    tested = [i for i in result["selftest"] if not i.startswith("_")]
    if not tested:
        return {"status": "no_selftest"}
    rule = next(r for r in result["rules"] if r["id"] == tested[0])
    rule = {**rule, "text": rule.get("before_selftest", rule["text"])}
    unit = record["identity"]["unit"]
    cells = {(rule["id"], item): [read_json(attempt / "cells" / (cell_id(unit, rule["id"], item, run) + ".json"),
                                            sealed=True) for run in range(SELFTEST_RUNS[bench])]
             for item in rule["evidence"]}
    meanings = examiner.code_meanings(bench, result["rubric"], setting.rubrics["general"])
    value = step._revision_payload(setting, chain.start(setting, chain_name), bench, [rule], cells, attempt,
                                   step.pool_tasks(setting, [bench]), meanings)
    if message_bytes(value) > ROLE_INPUT_BYTES:  # v3 §6: never sent over its bound
        return {"status": "input_overflow", "rule": rule["id"]}
    dropped = []
    reply = roles.ask("selftest_revise", step.SELFTEST_SYSTEM, value, label=label + "/revise",
                      check=step._revisions({rule["id"]}, bench, dropped))
    return {"status": "valid" if reply is not None else "invalid", "rule": rule["id"], "reply": reply,
            "dropped": dropped}


def valid_proposals(rules):
    """v3 §4: the proposals whose own row passed validation (an invalid row keeps no usable text)."""
    return [r for r in rules if r.get("row_status", "ok") == "ok" and isinstance(r.get("text"), str)]


def paths(setting, root, chain_name=CHAIN):
    """§14's paths the stage's replies did not reach, once each on the analyst's first valid proposal (its own unit,
    after the stage's merge), under the production leakage screens (a path they forbid is recorded "not_dispatched").
    Returns its record, or None when the stage reached every path or the analyst proposed no valid rule."""
    prepared = read_json(unit_path(root, 1, "prepare") / "unit.json", sealed=True)
    reached, rules = _reached(root), valid_proposals(_plan(root, 1)["result"].get("rules") or [])
    if not rules or all(reached.values()):
        return None
    rule = rules[0]
    identity = {"unit": "%s/s1/%s" % (chain_name, PATHS), "chain": chain_name, "stage": 1, "benchmark": ORDER[0],
                "rule": rule["id"], "reached": reached, "after": prepared["record_hash"]}

    def work(attempt):
        _, role_endpoint = endpoints(setting, chain_name, 1)
        roles, label = Roles(role_endpoint), identity["unit"]
        sources = setting.sources(attempt / "research")
        out = {"rule": rule["id"]}
        # v2 §7: the production screens decide what may be sent -- a rule with any mechanical hit (a single-word
        # answer included) or dropped as a leak sends nothing; a question that hits is replaced by the fallback
        corpus = leakage.Corpus(ORDER[0], setting.pools[ORDER[0]])
        hit = leakage.mechanical(rule["text"], corpus)
        if hit is None and str(rule.get("status", "")).startswith("leak"):
            hit = rule["status"]
        try:
            if not reached["research"]:
                question = next((q for q in [*(rule.get("questions") or []), QUESTION]
                                 if leakage.mechanical(q, corpus) is None), None)
                if hit is not None or question is None:
                    out["research"] = {"status": "not_dispatched", "rule_hit": hit}
                else:
                    found = research.request(roles, sources, purpose="verify", question=question, rule=rule["text"],
                                             label=label + "/research")
                    write_json(attempt / "research.json", found)
                    out["research"] = {"question": question, "status": found["status"], "calls": found["calls"]}
                    if found["status"] == "found":
                        text, status = research.rewrite(roles, rule["text"], [found], label=label + "/rewrite")
                        out["rewrite"] = {"status": status, "before": rule["text"], "after": text}
            if not reached["revision"]:
                out["revision"] = _revise_once(setting, root, chain_name, roles, label)
            if not reached["forward"] and hit is not None:
                out["forward"] = {"status": "not_dispatched", "rule_hit": hit}
            elif not reached["forward"]:
                panel = step._forward(roles, sources, rule, FORWARD_TARGET, "%s/forward/%s" % (label, FORWARD_TARGET))
                write_json(attempt / "forward.json", panel)
                out["forward"] = {"status": panel["status"], "items": len(panel["items"]), "counts": panel["counts"]}
        finally:
            write_json(attempt / "roles.json", roles.calls)
        return out

    return run_unit(unit_path(root, 1, PATHS), run=setting.run, identity=identity, work=work)


def format_check(setting, root, chain_name):
    """v3 §2 (pre-launch step 6), the smoke's stage 0, zero GLM-5.3 calls: the chain's deepseek solver once on the first
    ``FORMAT_ITEMS`` items of each bench's registered training draw with each of three Skills -- chain E's scaffold,
    chain I's instructions, the empty Skill. A cell has the answer form when its output passes the bench's fixed format
    checks as C3 reads them (``REQUIRED_FORMAT``); a cell without a reply has none. Passes when E's and I's share on
    every bench is at least ``FORMAT_FLOOR`` (``FORMAT_FLOORED``; the empty Skill's is reported) and at most
    ``FORMAT_MARGIN`` below the empty Skill's."""
    skills = {"E": Skill(scaffold=True).render(), "I": Skill.seeded(setting.instructions).render(),
              "empty": Skill().render()}
    picked = {b: [step.key(b, t["task_id"]) for t in
                  data.training_items(setting.pools[b], b, DATA_SEED, size=FORMAT_ITEMS)] for b in FORMAT_BENCHES}
    identity = {"unit": "%s/s0/%s" % (chain_name, FORMAT), "chain": chain_name, "stage": 0, "items": picked,
                "skills_sha256": {name: digest(text) for name, text in skills.items()}}

    def work(attempt):
        solve = solver_endpoint(setting, REGISTERED[chain_name]["solver"], chain.deepseek_scopes(chain_name))
        items = [i for b in FORMAT_BENCHES for i in picked[b]]
        cells = step.run_round(setting, attempt, solve, identity["unit"], skills,
                               {name: [(i, 1) for i in items] for name in skills}, step.pool_tasks(
                                   setting, FORMAT_BENCHES), tag=FORMAT)
        shares, unknown, failing = {}, {}, []
        for name in skills:
            for bench in FORMAT_BENCHES:
                missing = step.violations(attempt, cells, name, picked[bench], bench, unknown_counts=1)
                share = 1 - missing / len(picked[bench])
                shares.setdefault(name, {})[bench] = str(share)
                unknown.setdefault(name, {})[bench] = sum(cells[(name, i)][0]["final"]["token"] in step.UNKNOWN_TOKENS
                                                          for i in picked[bench])
                if name in FORMAT_FLOORED and share < FORMAT_FLOOR:
                    failing.append({"skill": name, "bench": bench, "share": str(share), "criterion": "floor"})
        for name in ("E", "I"):
            for bench in FORMAT_BENCHES:
                if Fraction(shares[name][bench]) < Fraction(shares["empty"][bench]) - FORMAT_MARGIN:
                    failing.append({"skill": name, "bench": bench, "share": shares[name][bench],
                                    "criterion": "below_empty"})
        return {"shares": shares, "unknown": unknown, "required": {b: list(REQUIRED_FORMAT[b]) for b in FORMAT_BENCHES},
                "passed": not failing, "failing": failing}

    return run_unit(unit_path(root, 0, FORMAT), run=setting.run, identity=identity, work=work)


def run(path):
    """Run the smoke until it completes or pauses (a paused unit waits for the owner's decision, ``recover``; nothing
    resumes by itself) -- v3: or its format check fails. Writes and returns its summary."""
    spec, value = setting(path)
    name = spec["chain"]
    root = chain.chain_root(value, name)
    root.mkdir(parents=True, exist_ok=True)
    os.environ["ALFWORLD_DATA"] = value.runtime["alfworld"]["alfworld_data"]
    with exclusive(root / chain.RUNNER_LOCK):
        value.budget.declare(chain.caps(name, prelaunch.PRELAUNCH_CAP))
        status = {"status": "complete"}
        try:
            checked = format_check(value, root, name)["result"]
            if not checked["passed"]:
                status = {"status": "format_check_failed", "kind": FORMAT, "reason": checked["failing"]}
            else:
                learned, _ = step.learn(value, root, name, 1, chain.start(value, name))
                paths(value, root, name)
                step.learn(value, root, name, 2, learned)
        except Pause as pause:
            status = {"status": "paused", "kind": pause.kind, "reason": pause.reason, "unit": pause.cell}
    return write_summary(spec, status)


# ---------------------------------------------------------------------------------------------------- summary
def _seconds(unit_root, record):
    started = unit_root / record["attempt"] / "started.json"
    return round((unit_root / "unit.json").stat().st_mtime - started.stat().st_mtime, 1)


def _calls(path):
    """The role calls of one attempt by role: count, valid replies, seconds and charged tokens of their sends."""
    out = {}
    for call in read_json(path) if path.exists() else []:
        row = out.setdefault(call["role"], {"calls": 0, "valid": 0, "seconds": 0.0, "charged": 0})
        sends = call["sends"] or []
        row["calls"] += 1
        row["valid"] += bool(call["valid"])
        row["seconds"] = round(row["seconds"] + sum(s.get("seconds") or 0 for s in sends), 1)
        row["charged"] += sum(s.get("charged") or 0 for s in sends)
    return out


def _attempt(attempt, record):
    found = [read_json(p, sealed=True) for p in sorted((attempt / "cells").glob("*.json"))]
    cells = Counter(cell["final"]["token"] for cell in found)
    charged = sum(send.get("charged") or 0 for cell in found for send in cell.get("sends") or [])
    if record is not None and record["attempt"] == attempt.name:
        state = "complete"
    elif (attempt / "status.json").exists():
        state = read_json(attempt / "status.json", sealed=True)["kind"]
    else:
        state = "running_or_interrupted"
    return {"attempt": attempt.name, "status": state, "cells": dict(cells), "solver_charged": charged,
            "roles": _calls(attempt / "roles.json")}


def _stage(root, stage):
    """What a stage reached: proposals and their fates (v3: after the self-test), research, the self-test, similar
    candidates, forward panels, the gate's rounds with their shared-unknown exclusions, and the merge."""
    path = unit_path(root, stage, "prepare") / "unit.json"
    if not path.exists():
        return None
    record = read_json(path, sealed=True)
    result, attempt = _plan(root, stage)["result"], path.parent / record["attempt"]
    rules = result.get("rules", [])
    found = attempt / "research.json"
    researched = read_json(found) if found.exists() else []
    requests = [q for r in researched for q in r["questions"] if "log" in q]
    rounds = {name: read_json(unit_path(root, stage, name) / "unit.json", sealed=True)["result"]
              for name in ("screen", "confirm", "composite") if (unit_path(root, stage, name) / "unit.json").exists()}
    out = {"status": record["result"].get("status"), "revision": (result.get("revision") or {}).get("status"),
           "analyst": result.get("analyst"), "proposals": len(rules), "selftest": step.selftest_counts(result),
           "excluded": {name: len(r.get("excluded", [])) for name, r in rounds.items()},
           "placements": dict(Counter(r.get("placement") for r in rules)),
           "fates": dict(Counter(r["status"] for r in rules)),
           "research": {"requests": len(requests), "found": sum(q["status"] == "found" for q in requests),
                        "rewrites": dict(Counter(r["rewrite"] for r in researched if r.get("rewrite")))},
           "similar": {r["id"]: r.get("similar_status") for r in rules if r.get("similar_status")},
           "forward": {"%s:%s" % (r["id"], t): {"status": p["status"], "items": len(p["items"])}
                       for r in rules for t, p in sorted((r.get("forward") or {}).items())},
           "rounds": list(rounds)}
    merged = unit_path(root, stage, "merge") / "unit.json"
    if merged.exists():
        out["accepted"] = read_json(merged, sealed=True)["result"]["accepted"]
    return out


def summary(spec):
    """The smoke's record of what ran (zero calls; no score of any test item exists)."""
    root = safe_path(spec["root"]) / spec["chain"]
    units = {}
    for unit_root in sorted(p for p in root.glob("s*/*") if p.is_dir()):
        found = attempts(unit_root)
        if not found:
            continue
        record = read_json(unit_root / "unit.json", sealed=True) if (unit_root / "unit.json").exists() else None
        units["%s/%s" % (unit_root.parent.name, unit_root.name)] = {
            "complete": record is not None, "seconds": _seconds(unit_root, record) if record else None,
            "attempts": [_attempt(a, record) for a in found]}
    pinned = spec["code"]
    current = manifest.pin_code()
    changed = sorted(name for name in set(pinned) | set(current) if pinned.get(name) != current.get(name))
    paths_record = unit_path(root, 1, PATHS) / "unit.json"
    checked = unit_path(root, 0, FORMAT) / "unit.json"
    return {"chain": spec["chain"], "draw": spec["draw"], "units": units,
            "format_check": read_json(checked, sealed=True)["result"] if checked.exists() else None,
            "stages": {str(k): _stage(root, k) for k in range(1, len(BENCHES) + 1)},
            "paths": read_json(paths_record, sealed=True)["result"] if paths_record.exists() else None,
            "ledger": Budget(prelaunch.ledger_of(spec["root"])).snapshot(), "code_changed_since_smoke": changed,
            "environment_changed": manifest.environment() != spec["environment"]}


def write_summary(spec, status):
    out = {"run": spec["record_hash"], **status, **summary(spec)}
    path = safe_path(spec["root"]) / prelaunch.SMOKE_SUMMARY
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)
    return out
