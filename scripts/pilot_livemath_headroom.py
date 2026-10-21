#!/usr/bin/env python3
"""Headroom pilot for LiveMathematicianBench with the frozen solver -- NOT a method result and NOT a benchmark port.

Question (design memo docs/handoff/benchmark-replacement-pilot-20261013.md): before LiveMathematicianBench replaces
a benchmark in the learning toolchain, does the frozen solver (the F study's model record: same model, effort,
transport and retry policy) leave room for a Skill there -- is the no-Skill pass rate above the floor of five-way
chance, and does a zero-shot instruction already close the gap to a Skill that was learned from experience?

    zeroshot --study F --repo R --output DIR            one call: an initial Skill from a public task card
    prepare  --study F --repo R --upstream U --id-split S --revision SHA --per-month N --seed K
             --skill name=none --skill name=f:/abs/file ... --output DIR   (zero calls)
    run      --output DIR                                 every arm solves every item once (no resume)
    report   --output DIR [--contrast a-b ...]            zero calls

Data discipline. Only items of months that have NO item in the published split of the SkillOpt paper
(data/livemathematicianbench_id_split: train, val and test are all excluded, by month) are eligible, so the paper's
test items are never read and the paper's checkpoint Skill has not seen any pilot item. The solver sees the
question and the five options in a frozen per-item order; ``theorem`` and ``sketch`` never leave the source files.
Upstream a record lists its four wrong options (B to E) and, separately, the correct one (always A), so the five
are put in an order drawn per item from a hash.

The solver prompt is the toolchain's own form (skillopt/continual_eval/backends.py ``solve``): the fixed sentence,
the optional "Frozen skill guidance" block, one output-contract line, and the public view as a JSON user message.
Calls go through the frozen client (``CachedAPI``) directly -- there is no learning ledger for a benchmark the
toolchain does not know yet -- with a length recovery like the solver role's. Every position writes a sealed
intent before its call and a sealed outcome right after it, so an interruption leaves the submitted positions
visible; nothing is ever resumed. Delivery is bounded BEFORE submission: a position is submitted only while the
margins still cover every position in flight at its worst case (positions without a usable reply, and HTTP
attempts that delivered nothing, six attempts being the worst case of one position). Submission is ROLLING -- up
to eight positions in flight, a new one as soon as one returns -- because a single reply can take half an hour
(a solve that reasons up to its token limit) and must not hold back the others. Scoring is strict: exactly one letter A-E inside the last answer tag;
a delivered reply in any other form is a wrong answer and is counted as ``invalid_format``.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import sys
from copy import deepcopy
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import generate_zero_shot_skill as zero  # noqa: E402
from scripts import run_fivebench_g_stage as tool  # noqa: E402
from skillopt.coevolution_v5.core import seal  # noqa: E402
from skillopt.continual_eval.core import output_lock, read_json, require, safe_path, write_json  # noqa: E402

VERSION = "livemath-headroom-pilot-v2"  # v2: rolling submission (v1 waited for whole batches)
KIND = "livemath-headroom-pilot-solver"
LABELS = "ABCDE"
CHANCE = 0.2  # five options: the upstream record lists four wrong options and, separately, the correct one
CONTRACT = "\nChoose exactly one of the listed options and return only its letter inside <answer>...</answer>."
TASK_CARD = (
    "Task kind: multiple-choice questions about research-level mathematics (the LiveMathematicianBench benchmark): "
    "each question is built from a theorem of a recent arXiv paper.\n"
    "Input the solver receives: a JSON object with two fields -- \"question\" (the statement to complete or decide) "
    "and \"choices\" (five options labelled A to E, separated by blank lines; exactly one is correct).\n"
    "Fixed instructions the solver always receives: \"Solve the supplied task using only the supplied public "
    "information.\" and \"Choose exactly one of the listed options and return only its letter inside "
    "<answer>...</answer>.\"\n"
    "Scoring (public metric): the letter inside the last <answer>...</answer> is compared with the letter of the "
    "correct option; a reply without such a tag, or with anything but one letter in it, counts as wrong. Anything "
    "outside the tag is ignored.")
MAX_UNDELIVERED = 16      # positions without a usable reply: the run stops (pending) before this can be exceeded
MAX_FAILED_ATTEMPTS = 96  # HTTP attempts that delivered nothing, over the whole run
WORST_ATTEMPTS = 6        # of one position: two client calls (the solve and its length recovery) of three attempts
CHUNK = 10                # items per rotation of the arm order
WORKERS = 8               # positions in flight at most
PROBE_SECONDS = 10.0      # the connectivity gate is asked again before a submission after this long


IMPLEMENTATION = ("skillopt/continual_eval/backends.py", "skillopt/continual_learning/recovery.py",
                  "scripts/generate_zero_shot_skill.py", "scripts/run_active_evidence_panel_eval.py")


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _digest(*parts):
    return hashlib.sha256(":".join(str(p) for p in parts).encode()).hexdigest()


def system_prompt(skill):
    """The system message of the toolchain's ``solve`` with this benchmark's output-contract line."""
    system = "Solve the supplied task using only the supplied public information."
    if skill.strip():
        system += "\n\nFrozen skill guidance (use only where applicable):\n" + skill
    return system + CONTRACT


def published_months(id_split):
    """Months that have an item in the paper's split (train, val or test) -- excluded as a whole."""
    months = set()
    for part in ("train", "val", "test"):
        for item in json.loads((safe_path(id_split) / part / "items.json").read_text(encoding="utf-8")):
            months.add(str(item["month"]))
    return months


def draw(upstream, excluded, per_month, seed):
    """(items, source file hashes): ``per_month`` items of every eligible month in a hash order, each with its
    options in a hash-drawn order. An item is {"id", "public": {question, choices}, "private": {answer}}."""
    items, files = [], {}
    for path in sorted((safe_path(upstream) / "data").glob("*/qa_*_final.json")):
        month = path.parent.name
        if month in excluded:
            continue
        files[str(path.relative_to(safe_path(upstream)))] = _sha(path)
        records = json.loads(path.read_text(encoding="utf-8"))
        require(type(records) is list and all(str(r["month"]) == month for r in records), "Unexpected monthly file")
        chosen = sorted(records, key=lambda r: _digest(seed, "item", month, r["no"]))[:per_month]
        require(len(chosen) == per_month, "A month has fewer items than requested")
        for record in chosen:
            mcq = record["mcq"]
            correct = mcq["correct_choice"]
            choices = [correct] + list(mcq["choices"])  # the wrong options are listed without the correct one
            require(len(choices) == len(LABELS) and len({c["label"] for c in choices}) == len(LABELS)
                    and all(type(c["text"]) is str and c["text"].strip() for c in choices)
                    and len({c["text"].strip() for c in choices}) == len(LABELS)
                    and type(mcq["question"]) is str and mcq["question"].strip(), "Unexpected multiple-choice record")
            name = "%s:%s" % (month, record["no"])
            order = sorted(choices, key=lambda c: _digest(seed, "order", name, c["label"]))
            items.append({"id": name,
                          "public": {"question": mcq["question"],
                                     # option texts can span several lines: a blank line separates the options
                                     "choices": "\n\n".join("%s. %s" % (LABELS[k], c["text"].strip())
                                                            for k, c in enumerate(order))},
                          "private": {"answer": LABELS[[c["label"] for c in order].index(correct["label"])]}})
    require(len({i["id"] for i in items}) == len(items) and items, "No eligible item")
    return items, files


def skill_spec(spec):
    """(name, text, provenance) of ``name=none`` or ``name=f:<absolute text file>``."""
    from skillopt.continual_learning.contracts import check_skill
    from skillopt.continual_learning.recovery import POLICY_V10

    name, separator, where = spec.partition("=")
    require(separator == "=" and name.isidentifier() and (where == "none" or where.startswith("f:")),
            "A Skill is given as name=none or name=f:<absolute text file>")
    if where == "none":
        return name, "", {"action": "empty_skill"}
    path = Path(where[2:])
    require(path.is_absolute() and safe_path(path).is_file(), "A Skill text is an existing absolute file")
    text = safe_path(path).read_text(encoding="utf-8")
    check_skill(text, POLICY_V10["skill_budget_bytes"])
    return name, text, {"action": "fixed_text", "file": str(path)}


def _model(study):
    root, protocol = tool._study(study)
    version, policy, budget = tool._protocol("v11")
    from skillopt.continual_learning.recovery import RETRY_POLICIES

    return root, protocol, {"model": deepcopy(protocol["model"]), "solver_max_tokens": budget["solver_max_tokens"],
                            "reflection_max_tokens": budget["reflection_max_tokens"],
                            "length_max_tokens": policy["length_max_tokens"],
                            "client_options": {"delivery_retry_policy": RETRY_POLICIES[version]},
                            "learning_model_service": protocol["learning_model_service"],
                            "native_lock": protocol["config"]["native_lock"]}


def prepare(study, repo, upstream, id_split, output, skills, *, revision, per_month, seed):
    root, protocol, service = _model(study)
    out = safe_path(output)
    require(not out.exists(), "Use a new directory")
    require(type(per_month) is int and per_month >= 1 and len(revision) == 40, "Invalid sample size or revision")
    excluded = published_months(id_split)
    items, files = draw(upstream, excluded, per_month, seed)
    named = [skill_spec(s) for s in skills]
    require(len(named) >= 2 and len({n for n, _, _ in named}) == len(named), "Give at least two distinct arms")
    out.mkdir(parents=True, mode=0o700)
    write_json(out / "items.json", seal({"items": items}))
    write_json(out / "skills.json", seal({"skills": [{"name": n, "skill": s} for n, s, _ in named]}))
    record = seal({"version": VERSION, "study": str(root), "protocol_hash": protocol["record_hash"],
                   "repo": str(safe_path(repo)), "benchmark": "livemathematicianbench",
                   "source": {"revision": revision, "files": files,
                              "id_split_manifest_sha256": _sha(safe_path(id_split) / "split_manifest.json")},
                   "implementation_sha256": {name: _sha(PROJECT_ROOT / name) for name in IMPLEMENTATION},
                   "sampling": "the same number of items from every eligible month: an equally weighted mixture of "
                               "those months, not the upstream proportions",
                   "excluded_months": sorted(excluded), "per_month": per_month, "seed": seed,
                   "items": len(items), "items_hash": read_json(out / "items.json", sealed=True)["record_hash"],
                   "skills_hash": read_json(out / "skills.json", sealed=True)["record_hash"],
                   "arms": [{"name": n, "skill_bytes": len(s.encode()),
                             "skill_sha256": hashlib.sha256(s.encode()).hexdigest(), **p} for n, s, p in named],
                   "system_contract": CONTRACT, **service,
                   "data_scope": "months without any item of the paper's split; theorem and sketch never read out",
                   "tool_sha256": _sha(Path(__file__))})
    write_json(out / "pilot.json", record)
    return record


def _client(record, root, workers):
    from skillopt.validator_pilot.api import CachedAPI

    model = record["model"]
    return CachedAPI(Path(record["repo"]), root / "api", provider=model["provider"], model=model["name"],
                     workers=workers, reasoning_effort=model["reasoning_effort"],
                     **model.get("transport", {"initial_health_policy": "completed_response_v1"}),
                     **({"proxy": model["proxy"]} if "proxy" in model else {}), **record["client_options"])


def reply(api, record, key, system, user, kind=KIND, cap=None, recover=True):
    """(text or None, reason, receipts, raised): one call, plus -- for a solve -- one length recovery when the first
    reply was a complete stream that ran into its token limit (as the solver role does). ``raised`` counts client
    calls that ended in an exception: they left no receipt, so what they spent is not known."""
    from skillopt.continual_eval.backends import _response
    from skillopt.continual_learning.recovery import is_closed_length

    receipts, raised = [], []

    def call(system, user, key=key, tokens=cap or record["solver_max_tokens"]):
        try:
            receipt = api.call(system, user, kind, key, max_tokens=tokens, repeat=0)
        except Exception:
            raised.append(key)
            raise
        receipts.append(receipt)
        return receipt

    text, _, reason = _response(call, system, user)
    if recover and not raised and receipts and is_closed_length(receipts[-1]):
        text, _, reason = _response(
            lambda s, u: call(s, u, key + ":length-recovery:1", record["length_max_tokens"]), system, user)
    return text, reason, receipts, len(raised)


def _known(usage):
    return type(usage) is dict and all(type(usage.get(k)) is int and usage[k] >= 0
                                       for k in ("prompt_tokens", "completion_tokens"))


HTTP_ATTEMPTS = 3  # of one client call (the frozen retry policy): the worst case of a call that left no receipt


def _usage(receipts, raised=0):
    """Costs of a position from ALL its HTTP attempts (as the learning ledger counts them): the tokens of every
    attempt that reported usage, and the number of attempts that did not. A client call that raised left no
    receipt: it is an ``unresolved_call`` whose spending is unknown, and it is charged to the failed-attempt margin
    at its worst case."""
    attempts = tokens = unmetered = 0
    failed = HTTP_ATTEMPTS * raised
    for receipt in receipts:
        rows = receipt.get("attempts")
        usages = [a.get("usage", {}) for a in rows] if type(rows) is list and rows else [receipt.get("usage", {})]
        count = receipt.get("http_attempt_count")
        count = count if type(count) is int and count >= len(usages) else len(usages)
        attempts += count
        failed += count - (receipt.get("ok") is True)
        tokens += sum(u["prompt_tokens"] + u["completion_tokens"] for u in usages if _known(u))
        unmetered += sum(not _known(u) for u in usages) + count - len(usages)
    return {"calls": len(receipts) + raised, "http_attempts": attempts, "failed_attempts": failed,
            "tokens_known_subtotal": tokens, "attempts_without_usage": unmetered, "unresolved_calls": raised}


def letter(text):
    """The answer of a reply under the strict contract: exactly one letter A-E inside the LAST answer tag
    (case, surrounding space and one trailing '.', ')' or ':' ignored); None for any other form."""
    found = re.findall(r"<answer>(.*?)</answer>", text, re.DOTALL | re.IGNORECASE)
    if not found:
        return None
    label = found[-1].strip().upper()
    label = label[:-1].strip() if label[-1:] in {".", ")", ":"} else label
    return label if len(label) == 1 and label in LABELS else None


def _position(item_id):
    return item_id.replace(":", "-") + ".json"


def solve_one(api, record, out, arm, skill, item):
    """One position: sealed intent, the call(s), sealed outcome -- written by the worker itself."""
    key = "%s:%s:%s" % (record["record_hash"][:16], arm, item["id"])
    intent = out / "intents" / arm / _position(item["id"])
    intent.parent.mkdir(parents=True, exist_ok=True)
    write_json(intent, seal({"pilot_hash": record["record_hash"], "arm": arm, "item": item["id"], "key": key}))
    text, reason, receipts, raised = reply(api, record, key, system_prompt(skill),
                                           json.dumps(item["public"], ensure_ascii=False))
    status, label = "unknown", None
    if text is not None:
        label = letter(text)
        status = "pass" if label == item["private"]["answer"] else "fail"
    row = seal({"pilot_hash": record["record_hash"], "arm": arm, "item": item["id"], "status": status,
                "invalid_format": text is not None and label is None, "reason": reason,
                "request_hashes": [r.get("request_hash") for r in receipts],
                "finish_reasons": [r.get("finish_reason") for r in receipts], **_usage(receipts, raised)})
    target = out / "calls" / arm / _position(item["id"])
    target.parent.mkdir(parents=True, exist_ok=True)
    write_json(target, row)
    return row


COSTS = ("calls", "http_attempts", "failed_attempts", "tokens_known_subtotal", "attempts_without_usage",
         "unresolved_calls")


def _published(directory):
    """Published records of a directory tree (the writer's dot-prefixed staging files are not records)."""
    return sorted(p for p in directory.glob("*/*.json") if not p.name.startswith(".")) if directory.exists() else []


def collect(out, record):
    """(statuses, per-arm counts, costs) from the sealed records on disk (never from memory). A position with an
    intent and no outcome was submitted and its fate is not known: it is ``unknown`` and counted as an open intent
    (its cost is not in the subtotals)."""
    items = read_json(out / "items.json", sealed=True)["items"]
    arms = [a["name"] for a in record["arms"]]
    statuses, invalid = {i["id"]: {} for i in items}, {a: 0 for a in arms}
    costs = {**{k: 0 for k in COSTS}, "open_intents": 0}
    for path in _published(out / "calls"):
        row = read_json(path, sealed=True)
        require(row["pilot_hash"] == record["record_hash"] and row["arm"] in arms and row["item"] in statuses
                and row["arm"] not in statuses[row["item"]] and path.parent.name == row["arm"]
                and path.name == _position(row["item"]), "Foreign or duplicate call record")
        statuses[row["item"]][row["arm"]] = row["status"]
        invalid[row["arm"]] += row["invalid_format"]
        for k in COSTS:
            costs[k] += row[k]
    for path in _published(out / "intents"):
        row = read_json(path, sealed=True)
        require(row["pilot_hash"] == record["record_hash"] and row["arm"] in arms and row["item"] in statuses,
                "Foreign intent record")
        if row["arm"] not in statuses[row["item"]]:
            statuses[row["item"]][row["arm"]] = "unknown"
            costs["open_intents"] += 1
    counts = {a: {s: sum(v.get(a) == s for v in statuses.values()) for s in ("pass", "fail", "unknown")} for a in arms}
    for a in arms:
        counts[a]["not_run"] = sum(a not in v for v in statuses.values())
        counts[a]["invalid_format"] = invalid[a]
    return statuses, counts, costs


def execute(queue, work, probe=None, *, clock=None):
    """Run ``work(job)`` for every job of ``queue`` (in order of submission) with at most WORKERS in flight, and
    return None, or the reason the run had to stop. A job is submitted only while, counting every job in flight
    at its worst case, the margins hold: positions without a usable reply stay at or below MAX_UNDELIVERED and
    undelivered HTTP attempts at or below MAX_FAILED_ATTEMPTS. Jobs already in flight are always awaited. ``probe``
    (the connectivity gate) only delays a submission; when it raises, nothing more is submitted and the error
    propagates after the jobs in flight have returned."""
    import time
    from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

    clock = clock or time.monotonic
    queue = list(queue)
    undelivered = failed = 0
    flying, reason, error, asked = set(), None, None, None
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        while queue or flying:
            while queue and reason is None and error is None and len(flying) < WORKERS:
                room = min(MAX_UNDELIVERED - undelivered,
                           (MAX_FAILED_ATTEMPTS - failed) // WORST_ATTEMPTS) - len(flying)
                if room < 1:
                    if not flying:
                        reason = "delivery_margin_exhausted"
                    break
                if probe is not None and (asked is None or clock() - asked >= PROBE_SECONDS):
                    try:
                        probe()
                    except Exception as exc:  # network unreachable for too long: stop submitting
                        error = exc
                        break
                    asked = clock()
                flying.add(pool.submit(work, queue.pop(0)))
            if not flying:
                break
            done, flying = wait(flying, return_when=FIRST_COMPLETED)
            for future in done:
                try:
                    row = future.result()
                except Exception as exc:  # a worker that could not even seal its outcome: stop, keep the first
                    error = error or exc
                    continue
                undelivered += row["status"] == "unknown"
                failed += row["failed_attempts"]
    if error is not None:
        raise error
    return reason


def run(output, *, fixture_api=None, probe=None):
    out = safe_path(output)
    record = read_json(out / "pilot.json", sealed=True)
    require(record["version"] == VERSION and record["tool_sha256"] == _sha(Path(__file__)), "Tool changed")
    items = read_json(out / "items.json", sealed=True)
    skills = read_json(out / "skills.json", sealed=True)
    require(items["record_hash"] == record["items_hash"] and skills["record_hash"] == record["skills_hash"],
            "Pilot inputs changed")
    fixture = record["model"]["provider"] == "fixture"
    require(fixture == (fixture_api is not None), "Fixture client only for a fixture study")
    texts = {s["name"]: s["skill"] for s in skills["skills"]}
    arms = [a["name"] for a in record["arms"]]
    with safe_path(record["native_lock"]).open("a") as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        with output_lock(out / "calls"):
            if (out / "result.json").exists():
                return read_json(out / "result.json", sealed=True)
            reason = None
            if (out / "started.json").exists():
                reason = "interrupted_run_no_automatic_resume"
            else:
                try:
                    if not fixture:
                        tool._sequence().check_client_service(
                            record["repo"], record["model"], out / "client-check",
                            record["learning_model_service"], client_options=record["client_options"])
                    write_json(out / "started.json", seal({"pilot_hash": record["record_hash"]}))
                    api = fixture_api if fixture else _client(record, out, 1)
                    try:
                        if not fixture:
                            write_json(out / "model_service.json", seal(api.service))
                            if probe is None:  # as the panel evaluation tool: only delays a batch
                                from scripts.run_active_evidence_panel_eval import bounded, network_gate, tunnel_probe

                                proxy, host = record["model"].get("proxy"), api.service["host"]
                                probe = network_gate(lambda: bounded(lambda: tunnel_probe(proxy, host), 20.0))
                        rows = items["items"]
                        queue = []
                        for start in range(0, len(rows), CHUNK):
                            shift = (start // CHUNK) % len(arms)
                            queue += [(arm, item) for arm in arms[shift:] + arms[:shift]
                                      for item in rows[start:start + CHUNK]]
                        reason = execute(queue, lambda job: solve_one(api, record, out, job[0], texts[job[0]], job[1]),
                                         probe)
                    finally:
                        if not fixture:
                            api.close()
                except Exception as exc:
                    reason = "error:" + type(exc).__name__
            statuses, counts, costs = collect(out, record)
            if reason is None and (any(c["not_run"] for c in counts.values()) or costs["open_intents"]):
                reason = "incomplete"
            result = seal({"version": VERSION, "pilot_hash": record["record_hash"],
                           "status": "completed" if reason is None else "pending", "reason": reason,
                           "items": len(statuses), "arms": counts, "costs": costs,
                           # False: some spending is not known (a call without a receipt, an attempt without usage)
                           "costs_complete": not (costs["unresolved_calls"] or costs["attempts_without_usage"]
                                                  or costs["open_intents"])})
            write_json(out / "result.json", result)
            return result


def wilson(passed, known, z=1.959964):
    """Wilson 95% interval of a pass rate (None without a known outcome)."""
    if known == 0:
        return None
    rate, half = passed / known, z * z / known
    centre = (rate + half / 2) / (1 + half)
    spread = z * ((rate * (1 - rate) + half / 4) / known) ** 0.5 / (1 + half)
    return [round(centre - spread, 4), round(centre + spread, 4)]


def report(output, contrasts=()):
    """Zero calls. Per arm: counts, pass rate over known outcomes with its Wilson interval (to be read against
    five-way chance), replies in an invalid form. Contrasts only for a COMPLETED run, over the planned items, with
    the coverage rule and the missing-outcome bounds of the panel evaluation tool's ``paired``."""
    from scripts.run_active_evidence_panel_eval import paired

    out = safe_path(output)
    record = read_json(out / "pilot.json", sealed=True)
    result = read_json(out / "result.json", sealed=True)
    require(result["pilot_hash"] == record["record_hash"], "Result of another pilot")
    statuses, counts, costs = collect(out, record)
    require(counts == result["arms"] and costs == result["costs"], "Records changed after the result was sealed")
    positions = [{"status": v} for v in statuses.values()]
    arms = {}
    for a in record["arms"]:
        c = counts[a["name"]]
        known = c["pass"] + c["fail"]
        arms[a["name"]] = {**c, "skill_bytes": a["skill_bytes"], "pass_rate": round(c["pass"] / known, 4) if known else None,
                           "wilson95": wilson(c["pass"], known)}
    value = {"status": result["status"], "reason": result["reason"], "items": len(positions), "chance": CHANCE,
             "arms": arms, "costs": costs, "costs_complete": result["costs_complete"], "contrasts": {}}
    require(not contrasts or result["status"] == "completed", "Contrasts are read from a completed run only")
    for spec in contrasts:
        a, _, b = spec.partition("-")
        require(a in counts and b in counts and a != b, "A contrast is arm-arm of two evaluated arms")
        value["contrasts"][spec] = paired(positions, a, b, len(positions))
    return value


def zeroshot(study, repo, output, *, fixture_api=None):
    """One call: the initial Skill a model writes from the public task card alone (generated once, never selected)."""
    from skillopt.continual_learning.contracts import check_skill
    from skillopt.continual_learning.recovery import POLICY_V10

    root, protocol, service = _model(study)
    out = safe_path(output)
    require(not out.exists(), "Use a new directory")
    out.mkdir(parents=True, mode=0o700)
    record = seal({"version": VERSION + ":zero-shot", "study": str(root), "protocol_hash": protocol["record_hash"],
                   "repo": str(safe_path(repo)), "system": zero.SYSTEM, "user": "Public task card:\n\n" + TASK_CARD,
                   "information": "public task card only: solver instructions, input fields, public metric; no task, "
                                  "no model answer, no score",
                   "selection": "generated once; never selected among alternatives", **service,
                   "tool_sha256": _sha(Path(__file__))})
    write_json(out / "generation.json", record)
    fixture = record["model"]["provider"] == "fixture"
    require(fixture == (fixture_api is not None), "Fixture client only for a fixture study")
    text, reason, receipts, raised = None, None, [], 0
    with safe_path(record["native_lock"]).open("a") as resource:
        fcntl.flock(resource.fileno(), fcntl.LOCK_EX)
        try:
            if not fixture:
                tool._sequence().check_client_service(
                    record["repo"], record["model"], out / "client-check", record["learning_model_service"],
                    client_options=record["client_options"])
            api = fixture_api if fixture else _client(record, out, 1)
            try:
                text, reason, receipts, raised = reply(api, record, record["record_hash"][:16] + ":zero-shot",
                                                       record["system"], record["user"],
                                                       kind="livemath-headroom-pilot-zero-shot",
                                                       cap=record["reflection_max_tokens"], recover=False)
            finally:
                if not fixture:
                    api.close()
        except Exception as exc:  # what was received before the failure stays in ``receipts``
            text, reason = None, "error:" + type(exc).__name__
    if text is not None:
        text = zero.skill_text(text)
        try:
            check_skill(text, POLICY_V10["skill_budget_bytes"])
        except ValueError:
            text, reason = None, "generated_skill_invalid"
    if text is not None:
        (out / "skill.md").write_text(text, encoding="utf-8")
    result = seal({"version": record["version"], "generation_hash": record["record_hash"],
                   "status": "completed" if text is not None else "pending", "reason": reason,
                   "skill_sha256": None if text is None else hashlib.sha256(text.encode()).hexdigest(),
                   "skill_bytes": None if text is None else len(text.encode()), **_usage(receipts, raised)})
    write_json(out / "result.json", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    z = sub.add_parser("zeroshot")
    p = sub.add_parser("prepare")
    for name in ("study", "repo", "output"):
        z.add_argument("--" + name, required=True)
        p.add_argument("--" + name, required=True)
    for name in ("upstream", "id-split", "revision"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--per-month", type=int, required=True)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--skill", action="append", default=[])
    sub.add_parser("run").add_argument("--output", required=True)
    r = sub.add_parser("report")
    r.add_argument("--output", required=True)
    r.add_argument("--contrast", action="append", default=[])
    args = parser.parse_args(argv)
    if args.command == "zeroshot":
        value = zeroshot(args.study, args.repo, args.output)
    elif args.command == "prepare":
        record = prepare(args.study, args.repo, args.upstream, args.id_split, args.output, args.skill,
                         revision=args.revision, per_month=args.per_month, seed=args.seed)
        value = {k: record[k] for k in ("version", "items", "excluded_months", "record_hash")}
        value["arms"] = [a["name"] for a in record["arms"]]
    elif args.command == "run":
        result = run(args.output)
        value = {k: result[k] for k in ("status", "reason", "items", "arms", "costs")}
    else:
        value = report(args.output, args.contrast)
    print(json.dumps(value, ensure_ascii=False))
    return 0 if args.command != "run" or value["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
