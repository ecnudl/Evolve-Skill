"""One learning stage of a chain (registration §4, §5, §13.4): the units before the stage's evaluation.

``train``: the parent Skill solves the stage's training execution. ``prepare`` (the method work before the gate, §4
steps 2-8): the seeded halves, the examiner's revision and diagnosis, the analyst's proposals, the research rewrite with
its pre-dispatch leakage check, the leakage and own-placement length checks and the frozen trigger items. v3
(registration delta §7): ``selftest`` -- every supported rule on its own proposal-half evidence items against the
parent, one batch revision of the rules that fail and a second round for the revised texts -- then, for a similar
candidate, the full similar placement (every checkable similar target of the stage, or none) with its forward panels and
the similar arm's length check; its record is the plan of the units after it. ``screen`` and ``confirm``: the gate's two rounds (fresh calls; the rule arms, the
parent and four same-placement controls per placement). ``composite``: the composition round on the fixed text S when
two or more rules are confirmed. ``merge``: the accepted text, exactly as tested (no model call). Every unit's record
names its inputs (the parent Skill and the record of the unit before it).

Cells are keyed by item: ``<bench>/<task id>`` for a pool item, ``fwd:<rule>:<target>:<n>`` for a forward item. A
round's cells run in a seeded order; the gate reads their final tokens (``stats.bounds``), and C3's format violations
from the stored predictions (a rule arm's unknown cells count as violations, the parent's do not).

v2 (registration delta §5): every arm of C1 runs ``TRIGGER_RUNS`` times on trigger items (the rule on its own, the
parent on the union of the round's, the controls on their placement's union); on a regression panel the parent runs
``PARENT_REGRESSION_RUNS`` times, a rule (or composite) arm once. The criteria stay sums of per-item rates, and format
violations are counted per item as the violating share of its runs. Composite rounds still have no controls.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from copy import deepcopy
from fractions import Fraction

from skillopt.continual_eval.core import read_json, require, safe_path, write_json
from skillopt.validator_pilot.api import digest

from . import analyst, checks, examiner, forward, gate, leakage, outcomes, research, sheetview
from .cells import Pause, cell_id, run_cells, run_parallel
from .data import training_items
from .protocol import (
    ANALYST_CONTEXT_CHARS,
    APPLIES_WHEN,
    DATA_SEED,
    FORWARD_RUNS,
    GATE_RUNS,
    MAX_RULE_CHARS,
    MAX_UNKNOWN_SHARE,
    MIN_TRIGGER,
    ORDER,
    PARENT_REGRESSION_RUNS,
    PLACEBOS_CONFIRM,
    PLACEBOS_SCREEN,
    REGRESSION_RUNS,
    REQUIRED_FORMAT,
    ROLE_INPUT_BYTES,
    SELFTEST_ATTEMPTS,
    SELFTEST_RUNS,
    SELFTEST_SHOWN,
    SHEET_MIN_QUALIFIED,
    TITLES,
    TRAIN_ROLLOUT,
    TRIGGER_RUNS,
    similar_targets,
)
from .roles import Invalid, Roles, fields, items, message_bytes, text
from .skill import Rule, Skill
from .stats import bounds, total, unknown_share
from .units import cell_context, endpoints, run_unit, unit_path

UNKNOWN_TOKENS = ("unknown", "unknown_artifact")


# --------------------------------------------------------------------------------------------------- items
def key(bench, task_id):
    return "%s/%s" % (bench, task_id)


def bench_of(item):
    return item.split(":")[2] if item.startswith("fwd:") else item.split("/", 1)[0]


def _order(values, tag):
    return sorted(values, key=lambda v: hashlib.sha256(json.dumps([DATA_SEED, tag, v]).encode()).hexdigest())


def pool_tasks(setting, benches):
    return {key(b, t["task_id"]): {"public": t["public"], "private": t["private"], "task_id": t["task_id"]}
            for b in benches for t in setting.pools[b]}


def regression_keys(setting, stage):
    """{earlier bench: its regression panel's item keys} (benches without a panel are absent)."""
    return {b: [key(b, t) for t in setting.regression[b]["items"]]
            for b in ORDER[:stage - 1] if setting.regression.get(b, {}).get("items")}


def _prediction(store, record):
    sha = record["attempts"][-1]["prediction"]["sha256"]
    return read_json(safe_path(store) / "artifacts" / (sha + ".json"))


def _identity(chain, stage, name, parent, before=None):
    return {"unit": "%s/s%d/%s" % (chain, stage, name), "chain": chain, "stage": stage, "benchmark": ORDER[stage - 1],
            "parent_sha256": digest(parent.to_json()), "after": before}


# ---------------------------------------------------------------------------------------------- the cells
def run_round(setting, attempt, endpoint, unit, arms, schedule, tasks, *, tag):
    """Every cell of a round. ``arms``: {arm: Skill text}; ``schedule``: {arm: [(item, runs)]}. Returns {(arm, item):
    [record per run]}; a stop of the run pauses the unit after the cell's record is written."""
    jobs = []
    for arm, plan in schedule.items():
        for item, runs in plan:
            for run in range(runs):
                cell = {"id": cell_id(unit, arm, item, run), "unit": unit, "arm": arm, "benchmark": bench_of(item),
                        "task_id": item, "run": run}
                jobs.append((cell, {"public": tasks[item]["public"], "private": tasks[item]["private"]}, arms[arm]))
    jobs = [jobs[i] for i in _order(list(range(len(jobs))), tag + ":" + unit)]
    records = run_cells(cell_context(setting, attempt, endpoint), jobs, workers=setting.workers)
    out = {}
    for (cell, _, _), record in sorted(zip(jobs, records), key=lambda pair: (pair[0][0]["arm"], pair[0][0]["task_id"],
                                                                              pair[0][0]["run"])):
        out.setdefault((cell["arm"], cell["task_id"]), []).append(record)
    return out


def table_of(cells):
    return bounds({k: [r["final"]["token"] for r in v] for k, v in cells.items()})


def _infrastructure(records):
    return sum(r["final"]["outcome"] == "unknown" and r["final"]["kind"] in ("infrastructure", "unclassified")
               for r in records)


def answered(record):
    """v3 §3: whether the provider delivered any reply in this cell (a receipt the call wrapper would not re-send)."""
    return any(isinstance(send.get("receipt"), dict) and not outcomes.undelivered(send["receipt"])
               for send in record.get("sends") or [])


def shared_unanswered(cells, items):
    """v3 §3: the pool items (never forward items) on which no arm of the round that scheduled them got any reply:
    every cell of every such arm is unknown and none delivered a reply (e.g. a provider's content filter). One mask
    for the whole round; such an item leaves every criterion of the round, the pause guard still counts its cells."""
    records = {}
    for (_, item), found in cells.items():
        records.setdefault(item, []).extend(found)
    return sorted(i for i in set(items) if records.get(i) and all(
        r["final"]["token"] == "unknown" and not answered(r) for r in records[i]))


def guard(cells, arms, unit):
    """§5.4: a round (or the training execution) whose parent or controls have more than 10% infrastructure-unknown
    cells is infrastructure-incomplete: the chain pauses (§13.4)."""
    for arm in arms:
        records = [r for (a, _), rs in cells.items() if a == arm for r in rs]
        if records and _infrastructure(records) > MAX_UNKNOWN_SHARE * len(records):
            raise Pause("infrastructure_incomplete", "%s: %d of %d cells" % (arm, _infrastructure(records),
                                                                             len(records)), unit)


def violations(store, cells, arm, items, bench, *, unknown_counts):
    """C3's format violations of an arm on a regression panel: a cell without an answer form (decision-table kind
    ``malformed``) or not passing a fixed format check (an unavailable output, e.g. a truncated reply, has no answer
    tag); unknown cells count for a rule arm, not for the parent. v2 §5.2: per item, the violating share of its runs
    (an exact fraction), summed over the panel -- so an arm's count keeps the scale of one run per item."""
    total = Fraction(0)
    for item in items:
        count, records = 0, cells[(arm, item)]
        for record in records:
            final = record["final"]
            if final["token"] in UNKNOWN_TOKENS:
                count += unknown_counts
                continue
            if final["kind"] == "malformed":
                count += 1
                continue
            prediction = _prediction(store, record)
            output = prediction.get("output") if prediction.get("status") == "available" else None
            count += any(checks.run({"name": name, "params": {}}, output) is not True
                         for name in REQUIRED_FORMAT[bench])
        total += Fraction(count, len(records))
    return total


def runs_plan(focal, triggers, bench, *, regression=(), regression_runs=REGRESSION_RUNS, forward=()):
    """v2 §5: one arm's schedule, [(item, runs)] in a fixed order: the focal panel at GATE_RUNS except ``triggers``
    (the items of the arm's C1) at TRIGGER_RUNS; each regression item at ``regression_runs``; each forward item at
    FORWARD_RUNS. An item is scheduled once."""
    hot = set(triggers)
    plan = [(i, TRIGGER_RUNS[bench] if i in hot else GATE_RUNS[bench]) for i in focal]
    plan += [(i, regression_runs) for i in regression] + [(i, FORWARD_RUNS) for i in forward]
    items = [i for i, _ in plan]
    require(len(set(items)) == len(items) and hot <= set(focal), "An arm schedules each item once")
    return plan


# ------------------------------------------------------------------------------------------------------ train
def train(setting, chain_root, chain, stage, parent):
    bench = ORDER[stage - 1]
    identity = _identity(chain, stage, "train", parent)
    items = training_items(setting.pools[bench], bench, DATA_SEED, size=setting.extra.get("draw", {}).get(bench))
    tasks = pool_tasks(setting, [bench])

    def work(attempt):
        solve, _ = endpoints(setting, chain, stage)
        schedule = {"train": [(key(bench, t["task_id"]), TRAIN_ROLLOUT[bench][1]) for t in items]}
        cells = run_round(setting, attempt, solve, identity["unit"], {"train": parent.render()}, schedule, tasks,
                          tag="train")
        guard(cells, ["train"], identity["unit"])
        return {"cells": {item: [r["cell"]["id"] for r in rs] for (_, item), rs in sorted(cells.items())},
                "tokens": {item: [r["final"]["token"] for r in rs] for (_, item), rs in sorted(cells.items())}}

    return run_unit(unit_path(chain_root, stage, "train"), run=setting.run, identity=identity, work=work)


# ---------------------------------------------------------------------------------------------------- prepare
def halves(tokens, *, chain, stage):
    """§4 step 2: the training items split into the proposal and check halves, stratified by "failed at least
    once"; in each stratum the first half of a seeded order (rounded up) proposes."""
    out = {}
    for failed in (True, False):
        stratum = _order(sorted(i for i, ts in tokens.items() if ("fail" in ts) == failed),
                         "halves:%s:%d:%s" % (chain, stage, failed))
        cut = (len(stratum) + 1) // 2
        out.update({i: "proposal" if n < cut else "check" for n, i in enumerate(stratum)})
    return out


def answers(store, result, tasks, bench, split):
    """The training execution's answers, as the examiner and the analyst read them: ``completion`` is the cell's
    completion-basis token (diagnoses and the analyst's failures), ``official`` the frozen scorer's own result, pass,
    fail or unknown (the rubric revision: e.g. a SpreadsheetBench program that wrote no workbook has failed on the
    completion basis but has no official score)."""
    out = []
    for item, ids in sorted(result["cells"].items()):
        for run, cid in enumerate(ids):
            record = read_json(safe_path(store) / "cells" / (cid + ".json"), sealed=True)
            out.append({**answer_of(store, record, tasks, bench, item, cid), "run": run, "half": split[item]})
    return out


def answer_of(store, record, tasks, bench, item, key):
    """One cell's answer as the examiner and the analyst read it (``answers``); v3 §6: a failed SpreadsheetBench
    answer also carries the answer-range cells the scorer compared (``sheetview``)."""
    prediction = _prediction(store, record)
    official = (record.get("official") or {}).get("status")
    score = record["attempts"][-1].get("score") or {}
    token = record["final"]["token"]
    return {"key": key, "item": item, "benchmark": bench, "completion": token,
            "official": official if official in ("pass", "fail") else "unknown", "kind": record["final"]["kind"],
            "output": prediction.get("output") if prediction.get("status") == "available" else None,
            "public": tasks[item]["public"], "private": tasks[item]["private"],
            "trace": prediction.get("trace"), "cases": score.get("cases"),
            "sheet_cells": (sheetview.cells(store, record, prediction, tasks[item]["private"])
                            if bench == "spreadsheetbench" and token == "fail" else None)}


def _alfworld_texts(found):
    texts = {}
    for answer in found:
        trace = answer.get("trace") or []
        if trace and isinstance(trace[0], dict) and isinstance(trace[0].get("observation"), str):
            texts.setdefault(answer["item"].split("/", 1)[1], trace[0]["observation"])
    return texts


def _research(roles, sources, proposal, corpus, label):
    """§4 step 5b for one proposal: the pre-dispatch check, one research request per admitted question, then one
    rewrite when a request found a qualified conclusion (a failed rewrite keeps the original text). v2 §7: a rule whose
    only mechanical hit is a single-word answer is kept but sends no research request."""
    record = {"id": proposal["id"], "original": proposal["text"], "questions": [], "rewrite": None}
    hit = leakage.mechanical(proposal["text"], corpus)
    if hit == "answer_word":
        return {**record, "status": "kept", "text": proposal["text"], "research": "skipped_answer_word"}
    if hit is not None:
        return {**record, "status": "dropped_pre_dispatch"}
    findings = []
    for n, question in enumerate(proposal["questions"], 1):
        if leakage.mechanical(question, corpus) is not None:
            record["questions"].append({"question": question, "status": "not_dispatched"})
            continue
        found = research.request(roles, sources, purpose="verify", question=question, rule=proposal["text"],
                                 label="%s/q%d" % (label, n))
        record["questions"].append(found)
        if found["status"] == "found":
            findings.append(found)
    text = proposal["text"]
    if findings:
        text, status = research.rewrite(roles, proposal["text"], findings, label=label + "/rewrite")
        record["rewrite"] = status
    return {**record, "status": "kept", "text": text}


def _forward(roles, sources, rule, target, label):
    """§8: the rule's forward panel on one forward target; every round's material request is kept with it."""
    log = []

    def material(round_index):
        return research.material(roles, sources, rule_text=rule["text"], style=target,
                                 label="%s/r%d/material" % (label, round_index), log=log)
    panel = forward.build_panel(roles, rule_id=rule["id"], rule_text=rule["text"], target=target, material=material,
                                label=label)
    return {**panel, "material": log}


def _admissible(roles, rule_id, text, corpus, parent, bench, values, label):
    """None when a rule's text may be tested, else why not: the mechanical leakage checks, the adjudicator (v2 §7: with
    a single-word collision's items; v3: an unseen condition, SpreadsheetBench's expected values) and the length of
    the bench's own placement."""
    hit = leakage.findings(text, corpus)
    if set(hit) - {"answer_word"}:
        return "leak_mechanical"
    if not leakage.adjudicate(roles, text, label=label, colliding=corpus.evidence(hit["answer_word"]) if hit else None,
                              values=values if bench == "spreadsheetbench" else None):
        return "leak_adjudicated_word" if hit else "leak_adjudicated"
    if not parent.fits(Rule(rule_id, text, bench)):
        return "overlength"
    return None


def prepare(setting, chain_root, chain, stage, parent, trained):
    bench = ORDER[stage - 1]
    identity = _identity(chain, stage, "prepare", parent, trained["record_hash"])
    tasks = pool_tasks(setting, [bench])

    def work(attempt):
        _, role_endpoint = endpoints(setting, chain, stage)
        roles = Roles(role_endpoint)
        unit = identity["unit"]
        store = unit_path(chain_root, stage, "train") / trained["attempt"]
        split = halves(trained["result"]["tokens"], chain=chain, stage=stage)
        found = answers(store, trained["result"], tasks, bench, split)
        out = {"halves": {h: sorted(i for i, v in split.items() if v == h) for h in ("proposal", "check")}}
        try:
            general = setting.rubrics["general"]
            revision = examiner.revise(roles, bench, setting.rubrics[bench], general, found, seed=setting.seed,
                                       tag="%s:%d" % (chain, stage), label=unit + "/examiner", workers=setting.workers)
            rubric = revision["rubric"]
            write_json(attempt / "revision.json", revision)
            out["revision"] = {"status": revision["status"], "accepted": revision["status"] == "accepted",
                               **{k: revision[k] for k in ("balanced_accuracy", "correct", "invalid") if k in revision}}
            failures = [a for a in found if a["completion"] == "fail"]
            diagnoses = examiner.diagnose(roles, bench, rubric, general, failures, label=unit + "/diagnose",
                                          workers=setting.workers)
            write_json(attempt / "diagnoses.json", diagnoses)
            out["rubric"] = rubric
            if bench == "spreadsheetbench" and len(setting.pools[bench]) < SHEET_MIN_QUALIFIED:
                return {**out, "status": "panel_insufficient", "rules": []}
            meanings = examiner.code_meanings(bench, rubric, general)
            proposal_failures = [a for a in failures if a["half"] == "proposal"]
            passed = [a for a in found if a["half"] == "proposal" and a["completion"] == "pass"]
            value = analyst.payload(bench, parent_text=parent.render(), failures=proposal_failures,
                                    diagnoses=diagnoses, meanings=meanings, cards=setting.cards, seed=setting.seed,
                                    tag="%s:%d" % (chain, stage), passed=passed)
            proposed = analyst.propose(roles, bench, value, stage=stage, codes=set(meanings),
                                       label=unit + "/analyst")
            out["analyst"] = {"status": proposed["status"], "attempts": proposed["attempts"],
                              "transfer": proposed["transfer"]}
            parent_texts = [r.text for r in parent.rules]
            rules = {p["id"]: {**p, "status": "invalid" if p["row_status"] != "ok" else "evidence_invalid"}
                     for p in proposed["proposals"] if p["evidence_status"] != "ok"}  # v2 §4, v3 §4: never tested
            proposals, duplicates = analyst.deduplicated(
                [p for p in proposed["proposals"] if p["evidence_status"] == "ok"], parent_texts)
            corpus = leakage.Corpus(bench, setting.pools[bench], alfworld_texts=_alfworld_texts(found)
                                    if bench == "alfworld" else None)
            sources = setting.sources(attempt / "research")
            researched = run_parallel(
                lambda p: _research(roles, sources, p, corpus, "%s/research/%s" % (unit, p["id"])), proposals,
                workers=setting.workers)
            write_json(attempt / "research.json", researched)
            rules.update({p["id"]: {**p, "status": "duplicate"} for p in proposed["proposals"] if p["id"] in duplicates})
            kept = []
            for proposal, done in zip(proposals, researched):
                if done["status"] != "kept":
                    rules[proposal["id"]] = {**proposal, "status": done["status"]}
                else:
                    kept.append({**proposal, "text": done["text"], "original": proposal["text"]})
            kept, again = analyst.deduplicated(kept, parent_texts)
            rules.update({p["id"]: {**p, "status": "duplicate_after_rewrite"} for p in proposals if p["id"] in again})
            check_failures = [a for a in failures if a["half"] == "check"]
            shown = {e["task_id"] for e in value["examples"]}
            values = leakage.answer_values([a for a in proposal_failures if a["item"] in shown])  # v3 §6
            supported = []
            for proposal in kept:
                status = _admissible(roles, proposal["id"], proposal["text"], corpus, parent, bench, values,
                                     "%s/leak/%s" % (unit, proposal["id"]))
                trigger = sorted({a["item"] for a in check_failures
                                  if diagnoses[a["key"]]["code"] in proposal["codes"]})
                if status is None and len(trigger) < MIN_TRIGGER:
                    status = "insufficient_support"
                rules[proposal["id"]] = {**proposal, "trigger": trigger, "status": status or "supported",
                                         "also": [], "forward": {}}
                if status is None:
                    supported.append(proposal["id"])
            # v3 §7: the similar placement and its forward panels come after the self-test (``selftest``)
            out.update(status="prepared", rules=[rules[p["id"]] for p in proposed["proposals"]],
                       supported=supported, duplicates=duplicates + again, answer_values=values)
            return out
        finally:
            write_json(attempt / "roles.json", roles.calls)

    return run_unit(unit_path(chain_root, stage, "prepare"), run=setting.run, identity=identity, work=work)


# --------------------------------------------------------------------------------------------------- selftest
SELFTEST_SYSTEM = (
    "You revise guidance rules -- parts of a \"Skill\" appended to the system prompt of a language model that solves "
    "tasks. Each rule below was written to fix the solver's failures on some training tasks, but when the solver used "
    "it, it still did not answer those tasks better than without it. You receive the current Skill, the section the "
    "rules belong to with its public task description, and for each rule its text, the failure codes it targets with "
    "their meanings, and a few of its tasks with the solver's answers given the rule and the reference. Rewrite each "
    "rule so that it would actually change the solver's behaviour on tasks like these, or drop it. A rule is one "
    "short, general instruction (at most 600 characters, no headings, no blank lines); never state a fact about one "
    "specific task or its answer, never steer the answer by how answers are usually distributed, and make the advice "
    "depend only on what the solver sees while solving -- never on the reference answer, on whether an answer is "
    "correct, or on a score. Reply with one JSON object only: {\"rules\": [{\"id\": the rule's id, \"text\": the "
    "revised rule} or {\"id\": the rule's id, \"drop\": true}, ...]}, one entry per rule.")


def _revisions(ids, benchmark, dropped):
    """v3 §7: the revision reply, validated entry by entry -- an invalid entry is appended to ``dropped`` and that rule
    is not revised; the reply is invalid when its envelope is malformed or no entry is valid. {id: text or None
    (dropped by the analyst)}."""
    def entry(row, seen):
        if type(row) is not dict or row.get("id") not in ids or row["id"] in seen:
            raise Invalid("rule id")
        if set(row) == {"id", "drop"} and row["drop"] is True:
            return None
        fields(row, ["id", "text"])
        return Rule("check", text(row["text"], limit=MAX_RULE_CHARS), benchmark).text

    def check(value):
        fields(value, ["rules"])
        out, bad = {}, []
        for index, row in enumerate(items(value["rules"], limit=len(ids), low=1)):
            try:
                out[row["id"] if type(row) is dict else None] = entry(row, out)
            except (ValueError, TypeError) as error:
                bad.append({"index": index, "reason": str(error)[:80] or type(error).__name__})
        dropped[:] = bad
        if not out:
            raise Invalid("no valid entry")
        return out
    return check


def _selftest_round(setting, attempt, endpoint, unit, parent, bench, arms, evidence, tasks, *, tag, with_parent):
    """One self-test round: every arm (``arms``: {arm: text}) on its own evidence items (``evidence``: {arm: items}) x
    SELFTEST_RUNS, the parent on their union when ``with_parent``. Returns the round's cells."""
    runs = SELFTEST_RUNS[bench]
    schedule = {arm: [(i, runs) for i in evidence[arm]] for arm in arms}
    texts = dict(arms)
    if with_parent:
        texts["parent"] = parent.render()
        schedule["parent"] = [(i, runs) for i in sorted({i for arm in arms for i in evidence[arm]})]
    cells = run_round(setting, attempt, endpoint, unit, texts, schedule, tasks, tag=tag)
    if with_parent:  # the pause rule reads the parent only (§5.4); a rule arm's unknowns decide its own outcome
        guard(cells, ["parent"], unit)
    return cells


def _passes(table, arm, parent_table, items):
    """v3 §7: (passed, rule sum L, parent sum H, the arm's unknown share) on the rule's evidence items."""
    rule, base = total(table, arm, items, "L"), total(parent_table, "parent", items, "H")
    share = unknown_share(table, arm, items)
    return rule > base and share <= MAX_UNKNOWN_SHARE, rule, base, share


def _revision_payload(setting, parent, bench, failing, cells, attempt, tasks, meanings):
    """The revision call's input: per failing rule its text, its codes and at most SELFTEST_SHOWN of its evidence items
    (seeded order) with the rule arm's answers and the reference; bounded (ROLE_INPUT_BYTES, the last tasks of the
    rules with the most tasks left out first, down to none; a payload still over the bound is never sent)."""
    rules = []
    for rule in failing:
        shown = _order(rule["evidence"], "selftest:%s" % rule["id"])[:SELFTEST_SHOWN]
        rows = []
        for item in shown:
            records = cells[(rule["id"], item)]
            found = [answer_of(attempt, r, tasks, bench, item, r["cell"]["id"]) for r in records]
            rows.append({"task_id": item,
                         "task": examiner.task_view(bench, tasks[item]["public"], trace=found[0].get("trace"),
                                                    context_chars=ANALYST_CONTEXT_CHARS.get(bench)),
                         "answers": [examiner.answer_text(bench, a["output"]) for a in found],
                         "reference": examiner.reference(bench, found[0])})
        rules.append({"id": rule["id"], "text": rule["text"],
                      "codes": [{"code": c, "meaning": meanings.get(c, "")} for c in rule["codes"]], "tasks": rows})
    value = {"section": TITLES[bench], "applies_when": APPLIES_WHEN[bench], "task_card": setting.cards[bench],
             "current_skill": parent.render(), "limits": {"rule_characters": MAX_RULE_CHARS}, "rules": rules,
             "tasks_omitted": 0}
    while message_bytes(value) > ROLE_INPUT_BYTES and any(r["tasks"] for r in rules):
        widest = max(range(len(rules)), key=lambda n: (len(rules[n]["tasks"]), n))
        rules[widest]["tasks"].pop()
        value["tasks_omitted"] += 1
    return value


def selftest(setting, chain_root, chain, stage, parent, prepared, trained):
    """v3 §7: every supported rule (at its own placement) on its own proposal-half evidence items, the parent on their
    union; the rules that fail get one batch revision (a new text or a drop), whose texts pass the leakage, duplicate
    and length checks again and a second round against the parent's first; then the similar placement and the forward
    panels of the similar candidates that remain. The plan every later unit of the stage reads (its rules and their
    statuses: a rule still "supported" is tested by the gate, with its final text)."""
    bench = ORDER[stage - 1]
    plan = prepared["result"]
    identity = _identity(chain, stage, "selftest", parent, prepared["record_hash"])
    tasks = pool_tasks(setting, [bench])
    backward, ahead = similar_targets(bench)
    targets = backward + ahead

    def work(attempt):
        solve, role_endpoint = endpoints(setting, chain, stage)
        roles = Roles(role_endpoint)
        unit = identity["unit"]
        rules = {r["id"]: deepcopy(r) for r in plan["rules"]}
        tested = [rules[i] for i in plan["supported"]]
        record = {r["id"]: {"evidence": list(r["evidence"])} for r in tested}
        try:
            arms = {r["id"]: parent.add(Rule(r["id"], r["text"], bench)).render() for r in tested}
            first = _selftest_round(setting, attempt, solve, unit, parent, bench, arms,
                                    {r["id"]: r["evidence"] for r in tested}, tasks, tag="selftest1", with_parent=True)
            table = table_of(first)
            failing = []
            for rule in tested:
                ok, mine, base, share = _passes(table, rule["id"], table, rule["evidence"])
                record[rule["id"]]["round1"] = {"rule_L": str(mine), "parent_H": str(base), "unknown_share": str(share),
                                                "passed": ok}
                if not ok:
                    failing.append(rule)
            revised = {}
            if failing:
                trained_store = unit_path(chain_root, stage, "train") / trained["attempt"]
                found = answers(trained_store, trained["result"], tasks, bench,
                                {i: "proposal" for i in trained["result"]["tokens"]}) if bench == "alfworld" else []
                corpus = leakage.Corpus(bench, setting.pools[bench],
                                        alfworld_texts=_alfworld_texts(found) if bench == "alfworld" else None)
                meanings = examiner.code_meanings(bench, plan["rubric"], setting.rubrics["general"])
                value = _revision_payload(setting, parent, bench, failing, first, attempt, tasks, meanings)
                dropped, reply = [], None
                over = message_bytes(value) > ROLE_INPUT_BYTES  # v3 §6: its fixed fields alone exceed the bound
                for n in range(1, 0 if over else SELFTEST_ATTEMPTS + 1):
                    reply = roles.ask("selftest_revise", SELFTEST_SYSTEM, value, label="%s/revise%d" % (unit, n),
                                      check=_revisions({r["id"] for r in failing}, bench, dropped))
                    if reply is not None:
                        break
                others = [r.text for r in parent.rules] + [r["text"] for r in tested if r not in failing]
                for rule in failing:
                    entry = record[rule["id"]]
                    if reply is None or rule["id"] not in reply:
                        entry["revision"] = ("input_overflow" if over else "reply_invalid") if reply is None \
                            else "not_revised"
                        rule["status"] = "selftest_failed"
                        continue
                    if reply[rule["id"]] is None:
                        entry["revision"], rule["status"] = "dropped", "selftest_dropped"
                        continue
                    new = reply[rule["id"]]
                    entry["revision"], entry["text"] = "revised", new
                    if analyst.normalized(new) in {analyst.normalized(t) for t in others}:
                        rule["status"] = "revision_duplicate"
                        continue
                    problem = _admissible(roles, rule["id"], new, corpus, parent, bench, plan.get("answer_values"),
                                          "%s/leak/%s" % (unit, rule["id"]))
                    if problem is not None:
                        rule["status"] = "revision_" + problem
                        continue
                    others.append(new)
                    revised[rule["id"]] = new
                record["_revision"] = {"status": "valid" if reply is not None else "input_overflow" if over
                                       else "invalid", "dropped": dropped,
                                       "omitted_tasks": value["tasks_omitted"]}
            if revised:
                arms = {i + ":revised": parent.add(Rule(i, text, bench)).render() for i, text in revised.items()}
                second = _selftest_round(setting, attempt, solve, unit, parent, bench, arms,
                                         {i + ":revised": rules[i]["evidence"] for i in revised}, tasks,
                                         tag="selftest2", with_parent=False)
                again = table_of(second)
                for i, text in revised.items():
                    ok, mine, base, share = _passes(again, i + ":revised", table, rules[i]["evidence"])
                    record[i]["round2"] = {"rule_L": str(mine), "parent_H": str(base), "unknown_share": str(share),
                                           "passed": ok}
                    if ok:
                        rules[i]["before_selftest"], rules[i]["text"] = rules[i]["text"], text
                    else:
                        rules[i]["status"] = "selftest_failed"
            supported = [i for i in plan["supported"] if rules[i]["status"] == "supported"]
            similar = [i for i in supported if rules[i]["placement"] == "similar" and targets]
            jobs = [(i, t) for i in similar for t in ahead]
            sources = setting.sources(attempt / "research")
            panels = run_parallel(lambda job: _forward(roles, sources, rules[job[0]], job[1],
                                                       "%s/forward/%s/%s" % (unit, job[0], job[1])),
                                  jobs, workers=setting.workers)
            for (i, target), panel in zip(jobs, panels):
                rules[i]["forward"][target] = panel
            for i in similar:
                rule = rules[i]
                if any(rule["forward"][t]["status"] != "ok" for t in ahead):
                    rule["similar_status"] = "forward_panel_short"
                elif not parent.fits(Rule(i, rule["text"], bench, targets)):
                    rule["similar_status"] = "similar_overlength"
                else:
                    rule["also"], rule["similar_status"] = list(targets), "similar_candidate"
            write_json(attempt / "selftest.json", record)
            return {**plan, "status": "selftested", "rules": [rules[r["id"]] for r in plan["rules"]],
                    "supported": supported,
                    "selftest": {i: {k: v for k, v in entry.items() if k != "evidence"}
                                 for i, entry in record.items()}}
        finally:
            write_json(attempt / "roles.json", roles.calls)

    return run_unit(unit_path(chain_root, stage, "selftest"), run=setting.run, identity=identity, work=work)


def selftest_counts(result):
    """v3 §7, description only: of a stage's plan (the self-test's record), the rules tested, passed in the first
    round, the revision reply and each rule's revision outcome, passed in the second round; None when no self-test
    ran."""
    tested = {i: e for i, e in (result.get("selftest") or {}).items() if not i.startswith("_")}
    if not tested:
        return None
    return {"tested": len(tested), "round1_passed": sum(e["round1"]["passed"] for e in tested.values()),
            "reply": (result["selftest"].get("_revision") or {}).get("status"),
            "revisions": dict(sorted(Counter(e["revision"] for e in tested.values() if "revision" in e).items())),
            "round2_passed": sum(e["round2"]["passed"] for e in tested.values() if "round2" in e)}


def plan_path(chain_root, stage):
    """v3 §7: the unit record the stage's gate reads -- its self-test's once that completed, else its prepare's."""
    path = unit_path(chain_root, stage, "selftest") / "unit.json"
    return path if path.exists() else unit_path(chain_root, stage, "prepare") / "unit.json"


# ------------------------------------------------------------------------------------------------------- gate
def forward_items(rule):
    return [item["id"] for target in sorted(rule["forward"]) if rule["also"]
            for item in rule["forward"][target]["items"]]


def forward_tasks(rules):
    return {item["id"]: {"public": item["public"], "private": item["private"]}
            for rule in rules for target in sorted(rule["forward"]) for item in rule["forward"][target]["items"]}


def _round(setting, chain_root, chain, stage, parent, plan, before, *, name, tested, placebos):
    """One gate round over ``tested`` = [(rule, [arm kinds])]: its cells, the verdict of every rule arm, the
    descriptive control diagnostics. Raises ``Pause`` when the round is infrastructure-incomplete."""
    bench = ORDER[stage - 1]
    identity = _identity(chain, stage, name, parent, before)
    targets = sum(similar_targets(bench), ())
    regression = regression_keys(setting, stage)
    focal = plan["focal"]
    tasks = {**pool_tasks(setting, [bench] + list(regression)), **forward_tasks(r for r, _ in tested)}
    panels = [i for b in regression for i in regression[b]]
    arms, schedule = {"parent": parent.render()}, {}
    groups = {"local": [], "similar": []}
    for rule, kinds in tested:
        for kind in kinds:
            arm = "%s:%s" % (rule["id"], kind)
            placed = Rule(rule["id"], rule["text"], bench, tuple(targets) if kind == "similar" else ())
            arms[arm] = parent.add(placed).render()
            schedule[arm] = runs_plan(focal, rule["trigger"], bench, regression=panels,
                                      forward=forward_items(rule) if kind == "similar" else ())
            groups[kind].append(rule)
    for kind, members in groups.items():
        if not members:
            continue
        union = sorted({i for rule in members for i in rule["trigger"]})
        for n, text in enumerate(placebos, 1):
            arm = "control:%s:%d" % (kind, n)
            arms[arm] = parent.text_with(Rule("control-%d" % n, text, bench,
                                              tuple(targets) if kind == "similar" else ()))
            schedule[arm] = [(i, TRIGGER_RUNS[bench]) for i in union]
    tested_triggers = sorted({i for rule, _ in tested for i in rule["trigger"]})
    parent_forward = list(dict.fromkeys(i for rule in groups["similar"] for i in forward_items(rule)))
    schedule["parent"] = runs_plan(focal, tested_triggers, bench, regression=panels,
                                   regression_runs=PARENT_REGRESSION_RUNS, forward=parent_forward)

    def work(attempt):
        solve, _ = endpoints(setting, chain, stage)
        cells = run_round(setting, attempt, solve, identity["unit"], arms, schedule, tasks, tag=name)
        guard(cells, [a for a in arms if a == "parent" or a.startswith("control:")], identity["unit"])
        table = table_of(cells)
        # v3 §3: pool items no arm of the round got any answer for leave every criterion
        excluded = set(shared_unanswered(cells, focal + [i for b in regression for i in regression[b]]))
        kept = {b: [i for i in regression[b] if i not in excluded] for b in regression}
        parent_violations = {b: violations(attempt, cells, "parent", kept[b], b, unknown_counts=False)
                             for b in regression}
        verdicts = {}
        for rule, kinds in tested:
            trigger = [i for i in rule["trigger"] if i not in excluded]
            # v3 §7: C2 also leaves out the rule's own (proposal-half) evidence items, on which it was self-tested;
            # they still count in the arm's unknown share
            own = set(rule["trigger"]) | set(rule.get("evidence") or ())
            rest = [i for i in focal if i not in own and i not in excluded]
            held = [i for i in focal if i in own and i not in rule["trigger"] and i not in excluded]
            for kind in kinds:
                arm = "%s:%s" % (rule["id"], kind)
                checks = {b: {"items": kept[b], "tolerance": setting.regression[b]["tolerance"],
                              "violations": (violations(attempt, cells, arm, kept[b], b, unknown_counts=True),
                                             parent_violations[b])} for b in regression}
                checked = None
                if kind == "similar":
                    checked = {b: kept[b] for b in similar_targets(bench)[0]}
                    checked.update({t: [item["id"] for item in rule["forward"][t]["items"]]
                                    for t in similar_targets(bench)[1]})
                found = gate.verdict(table, arm=arm, parent="parent",
                                     controls=["control:%s:%d" % (kind, n) for n in range(1, 5)],
                                     trigger=trigger, rest=rest, tolerance=setting.tolerance[bench],
                                     regression=checks, targets=checked, min_trigger=MIN_TRIGGER, held=held)
                verdicts[arm] = {**found, "margin": str(found["margin"]), "priority": str(found["priority"])}
        placebo = {kind: gate.placebo_passage(table, ["control:%s:%d" % (kind, n) for n in range(1, 5)],
                                              {r["id"]: [i for i in r["trigger"] if i not in excluded]
                                               for r in members}, "parent")
                   for kind, members in groups.items() if members}
        return {"verdicts": verdicts, "placebo": placebo, "excluded": sorted(excluded),
                "unknown": {arm: sum(r["final"]["token"] in UNKNOWN_TOKENS for (a, _), rs in cells.items()
                                     if a == arm for r in rs) for arm in arms}}

    return run_unit(unit_path(chain_root, stage, name), run=setting.run, identity=identity, work=work)


def screen(setting, chain_root, chain, stage, parent, prepared):
    plan = prepared["result"]
    rules = [r for r in plan["rules"] if r["status"] == "supported"]
    tested = [(r, ["local", "similar"] if r["also"] else ["local"]) for r in rules]
    record = _round(setting, chain_root, chain, stage, parent, {**plan, "focal": _focal(plan)},
                    prepared["record_hash"], name="screen", tested=tested, placebos=PLACEBOS_SCREEN)
    verdicts = record["result"]["verdicts"]
    tentative, priority = {}, {}
    for rule in rules:
        similar = verdicts.get(rule["id"] + ":similar")
        local = verdicts.get(rule["id"] + ":local")
        tentative[rule["id"]] = gate.placement(similar, local)
        if tentative[rule["id"]] is not None:
            priority[rule["id"]] = (similar if tentative[rule["id"]] == "similar" else local)["priority"]
    return record, tentative, priority


def _focal(plan):
    return sorted(plan["halves"]["proposal"] + plan["halves"]["check"])


def confirm(setting, chain_root, chain, stage, parent, prepared, screened, tentative):
    plan = prepared["result"]
    by_id = {r["id"]: r for r in plan["rules"]}
    verdicts = screened["result"]["verdicts"]
    tested = []
    for rule_id, placement in sorted(tentative.items()):
        kinds = gate.confirmation_arms(placement, verdicts.get(rule_id + ":local"))
        if kinds:
            tested.append((by_id[rule_id], kinds))
    record = _round(setting, chain_root, chain, stage, parent, {**plan, "focal": _focal(plan)},
                    screened["record_hash"], name="confirm", tested=tested, placebos=PLACEBOS_CONFIRM)
    final = {}
    for rule_id, placement in sorted(tentative.items()):
        final[rule_id] = gate.final_placement(placement, screen_local=verdicts.get(rule_id + ":local"),
                                              confirm_similar=record["result"]["verdicts"].get(rule_id + ":similar"),
                                              confirm_local=record["result"]["verdicts"].get(rule_id + ":local"))
    return record, final


def placed(rule, placement, bench):
    targets = sum(similar_targets(bench), ())
    return Rule(rule["id"], rule["text"], bench, tuple(targets) if placement == "similar" else ())


def composite(setting, chain_root, chain, stage, parent, prepared, confirmed, final, subset):
    """§5.7 step 6 on the fixed text S (``subset``, priority order, final placements)."""
    bench = ORDER[stage - 1]
    plan = prepared["result"]
    by_id = {r["id"]: r for r in plan["rules"]}
    identity = _identity(chain, stage, "composite", parent, confirmed["record_hash"])
    regression = regression_keys(setting, stage)
    focal = _focal(plan)
    members = [by_id[i] for i in subset]
    similar = [r for r in members if final[r["id"]] == "similar"]
    tasks = {**pool_tasks(setting, [bench] + list(regression)), **forward_tasks(similar)}
    panels = [i for b in regression for i in regression[b]]
    hot = sorted({i for r in members for i in r["trigger"]})
    ahead = list(dict.fromkeys(i for r in similar for i in forward_items(r)))
    text = parent.add(*[placed(r, final[r["id"]], bench) for r in members]).render()
    arms = {"parent": parent.render(), "composite": text}
    schedule = {"parent": runs_plan(focal, hot, bench, regression=panels, regression_runs=PARENT_REGRESSION_RUNS,
                                    forward=ahead),
                "composite": runs_plan(focal, hot, bench, regression=panels, forward=ahead)}

    def work(attempt):
        solve, _ = endpoints(setting, chain, stage)
        cells = run_round(setting, attempt, solve, identity["unit"], arms, schedule, tasks, tag="composite")
        guard(cells, ["parent"], identity["unit"])
        table = table_of(cells)
        excluded = set(shared_unanswered(cells, focal + [i for b in regression for i in regression[b]]))  # v3 §3
        kept = {b: [i for i in regression[b] if i not in excluded] for b in regression}
        triggers = {i for r in members for i in r["trigger"]}
        evidence = {i for r in members for i in r.get("evidence") or ()}  # v3 §7
        checks = {b: {"items": kept[b], "tolerance": setting.regression[b]["tolerance"],
                      "violations": (violations(attempt, cells, "composite", kept[b], b, unknown_counts=True),
                                     violations(attempt, cells, "parent", kept[b], b, unknown_counts=False))}
                  for b in regression}
        checked = {}
        for rule in similar:
            for b in similar_targets(bench)[0]:
                checked["backward:" + b] = kept[b]
            for t in similar_targets(bench)[1]:
                checked["forward:%s:%s" % (rule["id"], t)] = [item["id"] for item in rule["forward"][t]["items"]]
        found = gate.composite(table, arm="composite", parent="parent",
                               members=[{"id": r["id"], "trigger": [i for i in r["trigger"] if i not in excluded]}
                                        for r in members],
                               rest=[i for i in focal if i not in triggers | evidence and i not in excluded],
                               tolerance=setting.tolerance[bench], regression=checks, panels=checked,
                               min_trigger=MIN_TRIGGER,
                               held=[i for i in focal if i in evidence - triggers and i not in excluded])
        return {"verdict": found, "subset": list(subset), "excluded": sorted(excluded)}

    return run_unit(unit_path(chain_root, stage, "composite"), run=setting.run, identity=identity, work=work)


def merge(setting, chain_root, chain, stage, parent, before, accepted, placements, prepared):
    """§5.7 step 8: the accepted text exactly as tested (no model call); ``accepted``: rule ids in priority order."""
    bench = ORDER[stage - 1]
    by_id = {r["id"]: r for r in prepared["result"]["rules"]} if prepared is not None else {}
    identity = _identity(chain, stage, "merge", parent, before)
    child = parent.add(*[placed(by_id[i], placements[i], bench) for i in accepted])

    def work(_):
        return {"accepted": [{"id": i, "placement": placements[i]} for i in accepted], "skill": child.to_json(),
                "skill_sha256": hashlib.sha256(child.render().encode()).hexdigest()}

    return run_unit(unit_path(chain_root, stage, "merge"), run=setting.run, identity=identity, work=work)


def learn(setting, chain_root, chain, stage, parent):
    """Every learning unit of the stage, in order; returns (the stage's Skill, the merge record). v3 §7: when prepare
    leaves supported rules, the self-test's record is the plan every later unit reads."""
    bench = ORDER[stage - 1]
    trained = train(setting, chain_root, chain, stage, parent)
    prepared = prepare(setting, chain_root, chain, stage, parent, trained)
    if any(r["status"] == "supported" for r in prepared["result"]["rules"]):
        prepared = selftest(setting, chain_root, chain, stage, parent, prepared, trained)
    before, accepted, placements = prepared["record_hash"], [], {}
    supported = [r for r in prepared["result"]["rules"] if r["status"] == "supported"]
    if supported:
        screened, tentative, priority = screen(setting, chain_root, chain, stage, parent, prepared)
        before = screened["record_hash"]
        if any(p is not None for p in tentative.values()):
            confirmed, final = confirm(setting, chain_root, chain, stage, parent, prepared, screened,
                                       {i: p for i, p in tentative.items() if p is not None})
            before = confirmed["record_hash"]
            passed = [i for i, p in final.items() if p is not None]
            order = gate.priority({i: Fraction(priority[i]) for i in passed})
            by_id = {r["id"]: r for r in prepared["result"]["rules"]}
            subset = gate.fitting_subset(order, lambda ids: parent.size_with(*[placed(by_id[i], final[i], bench)
                                                                              for i in ids])) if order else []
            status = None
            if len(subset) >= 2:
                combined = composite(setting, chain_root, chain, stage, parent, prepared, confirmed, final, subset)
                before, status = combined["record_hash"], combined["result"]["verdict"]["status"]
            accepted = gate.accepted(subset, status)
            placements = {i: final[i] for i in accepted}
    merged = merge(setting, chain_root, chain, stage, parent, before, accepted, placements, prepared)
    require(merged["result"]["accepted"] == [{"id": i, "placement": placements[i]} for i in accepted],
            "The merge record differs from the gate's decision")
    return Skill.from_json(merged["result"]["skill"]), merged
